import uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from starlette import status
from starlette.responses import Response

from orders.app import app
from orders.api.schemas import (
    GetOrderSchema,
    CreateOrderSchema,
    GetOrdersSchema,
)

import psycopg2
import psycopg2.extras
psycopg2.extras.register_uuid()

try:
    conn = psycopg2.connect(
        dbname="testdb",
        user="postgres",
        password="postgres",
        host="db",
        port="5432"
    )
    cur = conn.cursor()
    conn.autocommit = True
    print('Connecting successful')

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orderItems (
    id SERIAL PRIMARY KEY,
    product VARCHAR(100) NOT NULL,
    size VARCHAR(50) NOT NULL,
    quantity INTEGER DEFAULT 1,
    CHECK
    ( size IN ('small', 'medium', 'big')
    ),
    CHECK
    ( quantity > 0)
    );

    CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY,
    status VARCHAR(100) NOT NULL,
    created TIMESTAMPTZ NOT NULL,
    orderItem_id SERIAL NOT NULL,
    CHECK
    ( status IN ( 'created', 'paid', 'progress',
                'cancelled', 'dispatched', 'delivered' )
    ),
    FOREIGN KEY ( orderItem_id )
        REFERENCES orderItems ( id )
        ON DELETE CASCADE
    );
    """)
except Exception as e:
    print('Connecting to database unsuccessful')
    print('Error: ', e)


def to_order(raw: tuple):
    order = dict()
    id, status, created, product, size, quantity = raw
    order['id'] = id
    order['status'] = status
    order['created'] = created
    order['order'] = [{
            'product': product,
            'size': size,
            'quantity': quantity
        }]
    return order


def change_status(order_id, status):
    cur.execute(f"""
            SELECT o.id, o.status, o.created, i.product, i.size, i.quantity
            FROM orders AS o
            JOIN orderItems AS i
            ON o.orderItem_id = i.id
            WHERE o.id = '{order_id}'
            ;""")
    raw_order = cur.fetchone()
    if raw_order is not None:
        order = to_order(raw_order)
        order['status'] = status
        cur.execute(
            """
            UPDATE orders
            SET status = %s
            WHERE id = %s
            ;""",
            (
                order['status'],
                order_id,
                )
            )
        return order
    raise HTTPException(
        status_code=404,
        detail=f"Order with ID {order_id} not found"
        )


@app.get("/orders", response_model=GetOrdersSchema)
def get_orders():
    orders = []
    cur.execute("""
                SELECT o.id, o.status, o.created, i.product, i.size, i.quantity
                FROM orders AS o
                JOIN orderItems AS i
                ON o.orderItem_id = i.id
;""")
    order = dict()
    for row in cur:
        order = to_order(row)
        orders.append(order)

    return {"orders": orders}


@app.post(
    "/orders",
    status_code=status.HTTP_201_CREATED,
    response_model=GetOrderSchema,
)
def create_order(order_details: CreateOrderSchema):
    order = order_details.dict()
    order["id"] = uuid.uuid4()
    order["created"] = datetime.now(timezone.utc)
    order["status"] = "created"
    cur.execute(
        """INSERT INTO orderItems (product, size, quantity)
        VALUES (%s, %s, %s) RETURNING id;""",
        (order['order'][0]['product'],
         order['order'][0]['size'].value,
         order['order'][0]['quantity'])
        )
    res = cur.fetchone()
    if res is not None:
        item_id = res[0]
        cur.execute(
            """INSERT INTO orders (id, status, created, orderItem_id)
            VALUES (%s, %s, %s, %s);""",
            (order['id'], order['status'], order['created'], item_id)
        )
        return order


@app.get("/orders/{order_id}", response_model=GetOrderSchema)
def get_order(order_id: UUID):
    cur.execute(f"""
            SELECT o.id, o.status, o.created, i.product, i.size, i.quantity
            FROM orders AS o
            JOIN orderItems AS i
            ON o.orderItem_id = i.id
            WHERE o.id = '{order_id}'
            ;""")
    raw_order = cur.fetchone()
    if raw_order is not None:
        order = to_order(raw_order)
        return order
    raise HTTPException(
        status_code=404,
        detail=f"Order with ID {order_id} not found"
        )


@app.put("/orders/{order_id}", response_model=GetOrderSchema)
def update_order(order_id: UUID, order_details: CreateOrderSchema):
    cur.execute(f"""
            SELECT id, status, created, orderItem_id
            FROM orders
            WHERE id = '{order_id}'
            ;""")
    raw_order = cur.fetchone()
    if raw_order is not None:
        order = order_details.dict()
        order['id'] = raw_order[0]
        order['status'] = raw_order[1]
        order['created'] = raw_order[2]
        orderItem_id = raw_order[3]
        print(order_details.dict())
        cur.execute(
            """
            UPDATE orderItems
            SET product = %s,
                size = %s,
                quantity = %s
            WHERE id = %s
            ;""",
            (
                order['order'][0]['product'],
                order['order'][0]['size'].value,
                order['order'][0]['quantity'],
                orderItem_id
                )
            )
        return order
    raise HTTPException(
        status_code=404,
        detail=f"Order with ID {order_id} not found"
        )


@app.delete(
    "/orders/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_order(order_id: UUID):
    cur.execute(f"""
                SELECT orderItem_id
                FROM orders
                WHERE id = '{order_id}'
                ;""")
    res = cur.fetchone()
    if res is not None:
        orderItem_id = res[0]
        cur.execute(f"""
                    DELETE FROM orderItems
                    WHERE id = '{orderItem_id}'
                    ;""")
        return
    raise HTTPException(
        status_code=404,
        detail=f"Order with ID {order_id} not found"
        )


@app.post("/orders/{order_id}/cancel", response_model=GetOrderSchema)
def cancel_order(order_id: UUID):
    return change_status(order_id, 'cancelled')


@app.post("/orders/{order_id}/pay", response_model=GetOrderSchema)
def pay_order(order_id: UUID):
    return change_status(order_id, 'progress')


@app.on_event("shutdown")
def shutdown_event():
    cur.close()
    conn.close()
    print('Connection closed')
