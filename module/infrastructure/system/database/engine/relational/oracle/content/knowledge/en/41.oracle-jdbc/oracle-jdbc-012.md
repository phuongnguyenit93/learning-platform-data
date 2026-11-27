# REF CURSOR, OUT Parameters, ARRAY, and Object Types

Oracle JDBC enables Java to call procedures and functions in Oracle Database, receive query results, retrieve output parameter values, and exchange complex data structures. Four common mechanisms are **REF CURSOR**, **OUT parameters**, **ARRAY**, and **object types**.

- **OUT parameter** returns a scalar value or data structure from PL/SQL back to Java via CallableStatement.
- **REF CURSOR** returns an open cursor for a query result. Oracle JDBC exposes that result as a ResultSet.
- **ARRAY** represents a SQL collection defined in a schema, such as a nested table or VARRAY.
- **Object type** is a user-defined SQL data type created with CREATE TYPE ... AS OBJECT; JDBC can map it via Struct, SQLData, or Oracle APIs.

These types frequently appear together in a single PL/SQL API. For example, Java calls a procedure to find orders, passes a list of customer IDs using ARRAY, receives a REF CURSOR containing order rows, and also receives an OUT parameter with the total row count. To implement this reliably, you must understand how types are declared in the database, how parameters are registered in JDBC, how results are read, and how transactions and resources are managed.

## 1. Calling procedures and functions with CallableStatement

JDBC uses CallableStatement to call stored procedures or stored functions. Common call syntax:

~~~java
CallableStatement cs = connection.prepareCall(
    "{ call app.order_api.find_orders(?, ?) }"
);
~~~

For a procedure, the `?` placeholders represent parameters in the order declared in PL/SQL. For a function, the first placeholder is typically the return value:

~~~java
CallableStatement cs = connection.prepareCall(
    "{ ? = call app.order_api.count_orders(?) }"
);
~~~

Before calling:

- Use setXxx() or setObject() to bind IN parameters.
- Use registerOutParameter() to register OUT or IN OUT parameters.
- Call execute() or the appropriate execution method.
- Read OUT values using getXxx() or getObject().

Example procedure with IN, OUT, and IN OUT:

~~~sql
CREATE OR REPLACE PROCEDURE app.adjust_amount(
  p_order_id IN NUMBER,
  p_amount   IN OUT NUMBER,
  p_status   OUT VARCHAR2
) AS
BEGIN
  IF p_amount < 0 THEN
    p_status := 'INVALID';
    RETURN;
  END IF;

  UPDATE app.orders
  SET    total_amount = total_amount + p_amount
  WHERE  order_id = p_order_id;

  p_status := CASE
                WHEN SQL%ROWCOUNT = 1 THEN 'UPDATED'
                ELSE 'NOT_FOUND'
              END;

  p_amount := p_amount * 1.1;
END;
/
~~~

Java:

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement cs = connection.prepareCall(
         "{ call app.adjust_amount(?, ?, ?) }")) {

    cs.setLong(1, 1001L);
    cs.setBigDecimal(2, new BigDecimal("25.00"));
    cs.registerOutParameter(2, Types.NUMERIC);
    cs.registerOutParameter(3, Types.VARCHAR);

    cs.execute();

    BigDecimal adjustedAmount = cs.getBigDecimal(2);
    String status = cs.getString(3);

    // Use OUT results in the application.
}
~~~

For an IN OUT parameter, both bind the input value with setXxx() and register the output type with registerOutParameter(). JDBC does not infer the OUT type from the IN value alone.

### Parameter order and data types

Positions in CallableStatement start at 1. Order must match the procedure/function signature:

| PL/SQL mode | JDBC |
|---|---|
| IN | setXxx(index, value) |
| OUT | registerOutParameter(index, sqlType) |
| IN OUT | setXxx(index, value) and registerOutParameter(index, sqlType) |
| Function return | Register OUT at position 1, then bind input parameters starting at position 2 |

Example function returning NUMBER:

~~~sql
CREATE OR REPLACE FUNCTION app.order_count(
  p_customer_id IN NUMBER
) RETURN NUMBER AS
  l_count NUMBER;
BEGIN
  SELECT COUNT(*)
  INTO   l_count
  FROM   app.orders
  WHERE  customer_id = p_customer_id;

  RETURN l_count;
END;
/
~~~

Java:

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement cs = connection.prepareCall(
         "{ ? = call app.order_count(?) }")) {

    cs.registerOutParameter(1, Types.NUMERIC);
    cs.setLong(2, 200L);
    cs.execute();

    BigDecimal count = cs.getBigDecimal(1);
}
~~~

Oracle NUMBER is usually mapped safely to BigDecimal, especially when decimal precision must be preserved. Convert to long, int, or double only when value range and precision fit.

## 2. OUT parameters and reading returned values

OUT parameters return scalar data or values of a SQL/PLSQL type supported by JDBC. A procedure can have multiple OUT parameters, such as status code, processed count, message, or timestamp.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE app.get_order_status(
  p_order_id IN  NUMBER,
  p_status   OUT VARCHAR2,
  p_amount   OUT NUMBER,
  p_paid_at  OUT TIMESTAMP
) AS
BEGIN
  SELECT status, total_amount, paid_at
  INTO   p_status, p_amount, p_paid_at
  FROM   app.orders
  WHERE  order_id = p_order_id;
EXCEPTION
  WHEN NO_DATA_FOUND THEN
    p_status  := 'NOT_FOUND';
    p_amount  := NULL;
    p_paid_at := NULL;
END;
/
~~~

Java:

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement cs = connection.prepareCall(
         "{ call app.get_order_status(?, ?, ?, ?) }")) {

    cs.setLong(1, 1001L);
    cs.registerOutParameter(2, Types.VARCHAR);
    cs.registerOutParameter(3, Types.NUMERIC);
    cs.registerOutParameter(4, Types.TIMESTAMP);

    cs.execute();

    String status = cs.getString(2);
    BigDecimal amount = cs.getBigDecimal(3);
    Timestamp paidAt = cs.getTimestamp(4);

    boolean amountWasNull = cs.wasNull();
}
~~~

wasNull() checks whether the most recently read OUT value was SQL NULL. Call it immediately after the getter being checked because subsequent reads overwrite this state.

### Registering the exact OUT type

The registered JDBC type must be compatible with the returned PL/SQL/SQL type:

| Oracle type | Common JDBC type |
|---|---|
| VARCHAR2, CHAR | Types.VARCHAR, Types.CHAR |
| NUMBER | Types.NUMERIC or Types.DECIMAL |
| DATE | Types.DATE or Types.TIMESTAMP depending on needed mapping |
| TIMESTAMP | Types.TIMESTAMP |
| CLOB | Types.CLOB |
| BLOB | Types.BLOB |
| REF CURSOR | Types.REF_CURSOR or OracleTypes.CURSOR |
| SQL collection | Types.ARRAY with collection type name |
| SQL object | Types.STRUCT with object type name |

For Oracle-specific data types, the driver may provide extended constants and APIs in package oracle.jdbc. When using extended APIs, ensure the Oracle JDBC driver version is compatible with the deployed database and JDK.

### NULL and OUT types

When an OUT parameter returns NULL, the corresponding getter normally returns null for object types or a default value for primitives. For example, getInt() returns 0 if the SQL value is NULL; call wasNull() to distinguish NULL from 0.

For an IN parameter with a NULL value, use setNull(index, sqlType):

~~~java
cs.setNull(1, Types.NUMERIC);
~~~

Registering the right SQL type helps the driver handle data conversions and avoid type-mismatch errors.

## 3. What is a REF CURSOR?

A REF CURSOR is a variable referencing an open cursor in PL/SQL. A procedure can open a cursor with a SELECT statement and return that cursor to Java via an OUT parameter. Java JDBC receives the result as a ResultSet and reads it row by row.

REF CURSOR fits when a procedure needs to return a multi-column result set whose row count varies with query conditions. Rather than declaring numerous OUT parameters per row, the procedure returns a single cursor.

Oracle commonly uses SYS_REFCURSOR for weak REF CURSORs:

~~~sql
CREATE OR REPLACE PROCEDURE app.find_orders(
  p_customer_id IN  NUMBER,
  p_result      OUT SYS_REFCURSOR
) AS
BEGIN
  OPEN p_result FOR
    SELECT order_id,
           order_date,
           status,
           total_amount
    FROM   app.orders
    WHERE  customer_id = p_customer_id
    ORDER BY order_date DESC;
END;
/
~~~

OPEN ... FOR SELECT opens the cursor and binds it to the query result. The procedure finishes while the cursor remains open and returned to the caller. Java can fetch rows from that cursor until exhausted or until the ResultSet is closed.

### Receiving a REF CURSOR in JDBC

A common approach with Oracle JDBC is registering the OUT parameter with OracleTypes.CURSOR:

~~~java
import java.math.BigDecimal;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;

import oracle.jdbc.OracleTypes;

try (Connection connection = dataSource.getConnection();
     CallableStatement cs = connection.prepareCall(
         "{ call app.find_orders(?, ?) }")) {

    cs.setLong(1, 200L);
    cs.registerOutParameter(2, OracleTypes.CURSOR);

    cs.execute();

    try (ResultSet rs = (ResultSet) cs.getObject(2)) {
        while (rs.next()) {
            long orderId = rs.getLong("ORDER_ID");
            Timestamp orderDate = rs.getTimestamp("ORDER_DATE");
            String status = rs.getString("STATUS");
            BigDecimal amount = rs.getBigDecimal("TOTAL_AMOUNT");

            // Map data to a DTO or process here.
        }
    }
}
~~~

Some driver versions support registering with the JDBC standard Types.REF_CURSOR:

~~~java
cs.registerOutParameter(2, Types.REF_CURSOR);
~~~

Check driver compatibility before choosing the registration style. OracleTypes.CURSOR is an Oracle-specific constant commonly seen in longstanding Oracle JDBC examples; Types.REF_CURSOR is the standard JDBC type introduced in JDBC 4.2.

### Reading columns in a ResultSet

Columns can be read by column name or index:

~~~java
long orderId = rs.getLong("ORDER_ID");
String status = rs.getString("STATUS");
BigDecimal amount = rs.getBigDecimal("TOTAL_AMOUNT");
~~~

Using column names makes code easier to read, though names must not be duplicated or ambiguous in the SELECT list. When a query joins multiple tables with overlapping column names, assign explicit aliases:

~~~sql
SELECT o.order_id AS ORDER_ID,
       c.customer_name AS CUSTOMER_NAME,
       o.total_amount AS ORDER_AMOUNT
FROM   app.orders o
JOIN   app.customers c
  ON   c.customer_id = o.customer_id
WHERE  o.customer_id = p_customer_id;
~~~

JDBC getters return null or a default value depending on type. For nullable columns read as primitives, call wasNull() right after the getter:

~~~java
long maybeId = rs.getLong("OPTIONAL_ID");
boolean idIsNull = rs.wasNull();
~~~

### Multiple REF CURSORs in one procedure

A procedure can return multiple cursors—for example, one cursor for order headers and another for line items:

~~~sql
CREATE OR REPLACE PROCEDURE app.get_order_bundle(
  p_order_id IN  NUMBER,
  p_header   OUT SYS_REFCURSOR,
  p_items    OUT SYS_REFCURSOR
) AS
BEGIN
  OPEN p_header FOR
    SELECT order_id, customer_id, status, total_amount
    FROM   app.orders
    WHERE  order_id = p_order_id;

  OPEN p_items FOR
    SELECT product_id, quantity, unit_price
    FROM   app.order_items
    WHERE  order_id = p_order_id;
END;
/
~~~

Java registers two separate OUT cursors:

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement cs = connection.prepareCall(
         "{ call app.get_order_bundle(?, ?, ?) }")) {

    cs.setLong(1, 1001L);
    cs.registerOutParameter(2, OracleTypes.CURSOR);
    cs.registerOutParameter(3, OracleTypes.CURSOR);

    cs.execute();

    try (ResultSet header = (ResultSet) cs.getObject(2);
         ResultSet items = (ResultSet) cs.getObject(3)) {

        while (header.next()) {
            // Read header.
        }

        while (items.next()) {
            // Read item.
        }
    }
}
~~~

Each ResultSet must be closed after use. Do not close the CallableStatement before finishing reading all ResultSets it returned.

### REF CURSOR and transactions

A REF CURSOR is a handle to query results, not an independent copy of the data. Keep the Connection and CallableStatement open while fetching data. Never return a ResultSet outside the resource management scope if the connection has already been closed or returned to a pool.

If a procedure opens a cursor and the caller commits/rolls back or alters the transaction while fetching, read behavior and consistency depend on query type, isolation level, and transaction state. The simplest, easiest-to-control design is holding the connection until the ResultSet is fully read, then closing the ResultSet/statement and ending the transaction as required.

## 4. REF CURSOR vs. regular ResultSet

ResultSet is the JDBC interface for iterating over data. REF CURSOR is an Oracle-side cursor type that can be returned via PL/SQL. When Java receives a REF CURSOR, the driver provides a ResultSet.

| Criterion | REF CURSOR OUT | ResultSet from PreparedStatement |
|---|---|---|
| Where query is defined | Query lives in PL/SQL procedure/function | Query lives in Java |
| How it is called | CallableStatement | PreparedStatement |
| Result set delivery | Returned via OUT parameter | Returned by executeQuery() |
| Business encapsulation | Can group logic and permissions inside a package | SQL lives in the Java layer |
| Multiple result sets | Can return multiple REF CURSOR OUTs | Can use multiple ResultSets from separate statements |
| Reusability | Procedure can be called by multiple applications | Query logic is tied to calling code |

REF CURSOR is useful when database packages serve as the official data interface for multiple applications, or when query logic should be centralized in PL/SQL. PreparedStatement fits when SQL is managed in the application and does not need wrapping in stored procedures.

## 5. ARRAY and SQL collection types

Oracle SQL supports schema-level collection types. Two common kinds:

- **Nested table**: a collection with no declared upper bound like VARRAY; usable as a parameter type, object attribute, or table column.
- **VARRAY**: a collection with a declared maximum element count; preserves element order within the collection.

Example creating a nested table of NUMBER:

~~~sql
CREATE TYPE app.number_list_t AS TABLE OF NUMBER;
/
~~~

Example creating a VARRAY of up to 100 codes:

~~~sql
CREATE TYPE app.number_array_t AS VARRAY(100) OF NUMBER;
/
~~~

Both nested tables and VARRAYs can be passed through Oracle JDBC as java.sql.Array, provided the SQL type already exists in the schema. With Oracle JDBC, use OracleConnection.createOracleArray() to create arrays; Connection.createArrayOf() is not supported by Oracle JDBC in the standard way implemented by some other databases.

### Procedure accepting an ARRAY

Create a procedure accepting a collection and returning element count:

~~~sql
CREATE OR REPLACE PROCEDURE app.count_ids(
  p_ids   IN  app.number_list_t,
  p_count OUT NUMBER
) AS
BEGIN
  IF p_ids IS NULL THEN
    p_count := 0;
  ELSE
    p_count := p_ids.COUNT;
  END IF;
END;
/
~~~

Java creating and passing an ARRAY:

~~~java
import java.math.BigDecimal;
import java.sql.Array;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.Types;

import oracle.jdbc.OracleConnection;

try (Connection connection = dataSource.getConnection()) {
    OracleConnection oracleConnection =
        connection.unwrap(OracleConnection.class);

    Object[] values = new Object[] {
        new BigDecimal("10"),
        new BigDecimal("20"),
        new BigDecimal("30")
    };

    Array ids = oracleConnection.createOracleArray(
        "APP.NUMBER_LIST_T",
        values
    );

    try (CallableStatement cs = connection.prepareCall(
            "{ call app.count_ids(?, ?) }")) {

        cs.setArray(1, ids);
        cs.registerOutParameter(2, Types.NUMERIC);
        cs.execute();

        BigDecimal count = cs.getBigDecimal(2);
    } finally {
        ids.free();
    }
}
~~~

The type name passed to createOracleArray is the schema-level collection type name, not the element type name. Use uppercase schema and type names following Oracle's normal unquoted identifier storage, e.g., APP.NUMBER_LIST_T.

### Receiving an ARRAY from an OUT parameter

Procedure:

~~~sql
CREATE OR REPLACE PROCEDURE app.get_active_ids(
  p_ids OUT app.number_list_t
) AS
BEGIN
  SELECT CAST(
           MULTISET(
             SELECT customer_id
             FROM   app.customers
             WHERE  active_flag = 'Y'
             ORDER BY customer_id
           ) AS app.number_list_t
         )
  INTO p_ids
  FROM dual;
END;
/
~~~

Java:

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement cs = connection.prepareCall(
         "{ call app.get_active_ids(?) }")) {

    cs.registerOutParameter(1, Types.ARRAY, "APP.NUMBER_LIST_T");
    cs.execute();

    Array result = cs.getArray(1);
    if (result != null) {
        try {
            Object[] elements = (Object[]) result.getArray();

            for (Object element : elements) {
                BigDecimal id = (BigDecimal) element;
                // Process id.
            }
        } finally {
            result.free();
        }
    }
}
~~~

For NUMBER collections, elements are typically returned by the driver as BigDecimal. Exact Java types depend on the underlying SQL type, mapping, and driver. Verify runtime types when integrating with complex collection types.

### Iterating an ARRAY with ResultSet

java.sql.Array provides getResultSet() to iterate elements as a ResultSet. This can be helpful for large collections or when you do not want to materialize all elements into a Java array at once:

~~~java
Array ids = cs.getArray(1);

if (ids != null) {
    try (ResultSet elements = ids.getResultSet()) {
        while (elements.next()) {
            long index = elements.getLong(1);
            BigDecimal value = elements.getBigDecimal(2);
            // index is the collection position, value is the element.
        }
    } finally {
        ids.free();
    }
}
~~~

For very large collections, consider memory usage and fetch behavior. getArray() may materialize all elements in the JVM; getResultSet() provides a row-by-row interface, though driver behavior and data size still require testing.

## 6. Object types in Oracle SQL

An object type is a user-defined SQL data type. It can contain multiple attributes of different data types and be used as:

- Procedure IN/OUT parameter type.
- Collection element type.
- Table column type.
- Function return type.
- Data structure exchanged between Java and PL/SQL.

Example creating an address object type:

~~~sql
CREATE TYPE app.address_t AS OBJECT (
  street VARCHAR2(100),
  city   VARCHAR2(60),
  zip    VARCHAR2(15)
);
/
~~~

Procedure returning an object:

~~~sql
CREATE OR REPLACE PROCEDURE app.get_address(
  p_customer_id IN  NUMBER,
  p_address     OUT app.address_t
) AS
BEGIN
  SELECT app.address_t(street, city, zip)
  INTO   p_address
  FROM   app.customers
  WHERE  customer_id = p_customer_id;
END;
/
~~~

JDBC maps SQL objects via java.sql.Struct. Struct holds the SQL type name and the list of attributes in the declaration order of the object type.

### Receiving an object via OUT parameter using Struct

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement cs = connection.prepareCall(
         "{ call app.get_address(?, ?) }")) {

    cs.setLong(1, 200L);
    cs.registerOutParameter(2, Types.STRUCT, "APP.ADDRESS_T");
    cs.execute();

    Struct address = (Struct) cs.getObject(2);

    if (address != null) {
        Object[] attributes = address.getAttributes();

        String street = (String) attributes[0];
        String city = (String) attributes[1];
        String zip = (String) attributes[2];
    }
}
~~~

getAttributes() returns an array of attributes in the order declared in the SQL object type. Therefore, if a DBA changes attribute order or type structure, the Java mapping must be updated accordingly. Never rely on attribute order without managing schema versions.

You can inspect the SQL type name:

~~~java
String sqlTypeName = address.getSQLTypeName();
~~~

### Passing an object from Java to PL/SQL

With a JDBC driver supporting Connection.createStruct(), a Struct can be created from a SQL type name and attribute array:

~~~java
Object[] attributes = new Object[] {
    "12 Nguyen Hue",
    "Ho Chi Minh City",
    "700000"
};

Struct address = connection.createStruct(
    "APP.ADDRESS_T",
    attributes
);

try (CallableStatement cs = connection.prepareCall(
        "{ call app.save_address(?) }")) {

    cs.setObject(1, address, Types.STRUCT);
    cs.execute();
}
~~~

Example procedure:

~~~sql
CREATE OR REPLACE PROCEDURE app.save_address(
  p_address IN app.address_t
) AS
BEGIN
  INSERT INTO app.customer_addresses(street, city, zip)
  VALUES (
    p_address.street,
    p_address.city,
    p_address.zip
  );
END;
/
~~~

Connection.createStruct() is a standard JDBC API. For specific drivers or object types, Oracle APIs or custom mappings may be needed. Confirm support on the exact deployed driver version.

## 7. Mapping object types to Java classes with SQLData

If an application frequently works with the same SQL object type, manipulating raw Object[] directly becomes hard to maintain. JDBC provides the SQLData interface to map SQL objects to Java classes.

Example Java class:

~~~java
import java.sql.SQLData;
import java.sql.SQLInput;
import java.sql.SQLOutput;
import java.sql.SQLException;

public class Address implements SQLData {
    private String street;
    private String city;
    private String zip;

    public Address() {
    }

    public Address(String street, String city, String zip) {
        this.street = street;
        this.city = city;
        this.zip = zip;
    }

    @Override
    public String getSQLTypeName() {
        return "APP.ADDRESS_T";
    }

    @Override
    public void readSQL(SQLInput input, String typeName)
            throws SQLException {
        street = input.readString();
        city = input.readString();
        zip = input.readString();
    }

    @Override
    public void writeSQL(SQLOutput output)
            throws SQLException {
        output.writeString(street);
        output.writeString(city);
        output.writeString(zip);
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public String getZip() {
        return zip;
    }
}
~~~

Register the type map on the connection:

~~~java
Map<String, Class<?>> typeMap = new HashMap<>(connection.getTypeMap());
typeMap.put("APP.ADDRESS_T", Address.class);
connection.setTypeMap(typeMap);
~~~

When reading the object from JDBC results, the driver can use the type map to map the SQL type to the corresponding Java class:

~~~java
Object value = cs.getObject(2);
Address address = (Address) value;
~~~

Mapping depends on the driver and type map configuration. SQL type names in the map must match the schema/type names. In large applications, encapsulate type map registration in the data access layer and test when connections are borrowed from a pool.

SQLData fits portable JDBC mapping. Oracle also offers extended APIs such as OracleData/OracleDataFactory for cases needing Oracle JDBC-specific capabilities.

## 8. Collections containing object types

A SQL collection can hold scalars like NUMBER or object types. This represents a list of composite structures.

Create the collection type:

~~~sql
CREATE TYPE app.address_list_t AS TABLE OF app.address_t;
/
~~~

Procedure accepting a list of addresses:

~~~sql
CREATE OR REPLACE PROCEDURE app.save_addresses(
  p_addresses IN app.address_list_t
) AS
BEGIN
  FOR i IN 1 .. p_addresses.COUNT LOOP
    INSERT INTO app.customer_addresses(street, city, zip)
    VALUES (
      p_addresses(i).street,
      p_addresses(i).city,
      p_addresses(i).zip
    );
  END LOOP;
END;
/
~~~

Java creates each Struct, then wraps them in an Oracle Array:

~~~java
OracleConnection oracleConnection =
    connection.unwrap(OracleConnection.class);

Struct a1 = connection.createStruct(
    "APP.ADDRESS_T",
    new Object[] { "12 Nguyen Hue", "Ho Chi Minh City", "700000" }
);

Struct a2 = connection.createStruct(
    "APP.ADDRESS_T",
    new Object[] { "1 Le Loi", "Ho Chi Minh City", "700000" }
);

Array addresses = oracleConnection.createOracleArray(
    "APP.ADDRESS_LIST_T",
    new Object[] { a1, a2 }
);

try (CallableStatement cs = connection.prepareCall(
        "{ call app.save_addresses(?) }")) {
    cs.setArray(1, addresses);
    cs.execute();
} finally {
    addresses.free();
}
~~~

This example illustrates two layers of types:

1. APP.ADDRESS_T is the SQL object type; each element is represented as a Struct.
2. APP.ADDRESS_LIST_T is the SQL collection type holding objects; Java constructs the collection with createOracleArray().

Do not pass APP.ADDRESS_T to createOracleArray() when the procedure expects APP.ADDRESS_LIST_T. That parameter requires the collection type name, not the element type name.

## 9. SQL objects/collections vs. PL/SQL records/associative arrays

A common point of confusion is that schema-defined SQL types and types declared only inside a PL/SQL package are not the same.

| Type | Declaration | JDBC capability |
|---|---|---|
| SQL object type | CREATE TYPE ... AS OBJECT | Mappable with Struct/SQLData |
| SQL nested table | CREATE TYPE ... AS TABLE OF ... | Mappable with java.sql.Array and Oracle JDBC API |
| SQL VARRAY | CREATE TYPE ... AS VARRAY(...) OF ... | Mappable with java.sql.Array and Oracle JDBC API |
| PL/SQL RECORD | TYPE ... IS RECORD inside PL/SQL | Not a standard SQL STRUCT; needs dedicated support API or wrapper |
| PL/SQL associative array | TYPE ... IS TABLE OF ... INDEX BY ... | Needs Oracle-specific API; not identical to SQL ARRAY |
| SYS_REFCURSOR | Oracle cursor variable | JDBC receives as a ResultSet |

If a procedure declares parameters using a type that only exists inside a package, Java cannot by default register it as Types.STRUCT or Types.ARRAY. For a stable JDBC API, it is usually cleaner to publish schema-level SQL object/collection types, or create a PL/SQL wrapper using JDBC-supported types.

Oracle JDBC provides dedicated APIs for binding PL/SQL associative arrays in supporting versions. Exact methods and registration types depend on the driver, e.g., OracleCallableStatement APIs for PL/SQL index tables. Never assume createOracleArray() automatically accepts every associative array type.

## 10. Combining OUT parameters, REF CURSOR, and ARRAY in one API

A package can expose multiple result types in the same procedure. For example, a procedure takes a list of customer IDs, returns a REF CURSOR of orders, and returns an OUT parameter with the count of requested customers.

Create collection type:

~~~sql
CREATE TYPE app.customer_id_list_t AS TABLE OF NUMBER;
/
~~~

Create package:

~~~sql
CREATE OR REPLACE PACKAGE app.order_api AS
  PROCEDURE find_orders(
    p_customer_ids IN  app.customer_id_list_t,
    p_orders       OUT SYS_REFCURSOR,
    p_row_count    OUT NUMBER
  );
END order_api;
/
~~~

Package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY app.order_api AS
  PROCEDURE find_orders(
    p_customer_ids IN  app.customer_id_list_t,
    p_orders       OUT SYS_REFCURSOR,
    p_row_count    OUT NUMBER
  ) AS
  BEGIN
    IF p_customer_ids IS NULL OR p_customer_ids.COUNT = 0 THEN
      p_row_count := 0;

      OPEN p_orders FOR
        SELECT order_id, customer_id, status, total_amount
        FROM   app.orders
        WHERE  1 = 0;

      RETURN;
    END IF;

    SELECT COUNT(DISTINCT column_value)
    INTO   p_row_count
    FROM   TABLE(p_customer_ids);

    OPEN p_orders FOR
      SELECT order_id,
             customer_id,
             status,
             total_amount
      FROM   app.orders
      WHERE  customer_id IN (
        SELECT column_value
        FROM   TABLE(p_customer_ids)
      )
      ORDER BY order_id;
  END find_orders;
END order_api;
/
~~~

Java:

~~~java
import java.math.BigDecimal;
import java.sql.Array;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;

import oracle.jdbc.OracleConnection;
import oracle.jdbc.OracleTypes;

public void findOrders(DataSource dataSource) throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        OracleConnection oracleConnection =
            connection.unwrap(OracleConnection.class);

        Object[] customerIds = {
            new BigDecimal("101"),
            new BigDecimal("202"),
            new BigDecimal("303")
        };

        Array idArray = oracleConnection.createOracleArray(
            "APP.CUSTOMER_ID_LIST_T",
            customerIds
        );

        try (CallableStatement cs = connection.prepareCall(
                "{ call app.order_api.find_orders(?, ?, ?) }")) {

            cs.setArray(1, idArray);
            cs.registerOutParameter(2, OracleTypes.CURSOR);
            cs.registerOutParameter(3, Types.NUMERIC);

            cs.execute();

            BigDecimal requestedCustomerCount = cs.getBigDecimal(3);

            try (ResultSet rs = (ResultSet) cs.getObject(2)) {
                while (rs.next()) {
                    long orderId = rs.getLong("ORDER_ID");
                    long customerId = rs.getLong("CUSTOMER_ID");
                    String status = rs.getString("STATUS");
                    BigDecimal total = rs.getBigDecimal("TOTAL_AMOUNT");

                    // Map result row to DTO.
                }
            }
        } finally {
            idArray.free();
        }
    }
}
~~~

This example shows how they combine:

- ARRAY passes a set of values from Java to PL/SQL.
- REF CURSOR returns a set of rows from PL/SQL to Java.
- OUT NUMBER returns an additional scalar value.
- CallableStatement is the coordination point for the entire call.

In a real system, clarify whether the OUT parameter counts customers or orders. The example counts distinct customer IDs in the input collection; the returned row count may be larger because one customer can have multiple orders.

## 11. Transactions and Connection ownership

Procedure calls can read data, write data, or both. JDBC transactions are managed on the Connection.

When autoCommit is true, the driver can commit after statement completion per JDBC rules. For procedures with OUT REF CURSORs or multiple DML operations, actively manage transactions when business rules require atomicity:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (CallableStatement cs = connection.prepareCall(
            "{ call app.process_order(?, ?) }")) {

        cs.setLong(1, 1001L);
        cs.registerOutParameter(2, Types.VARCHAR);
        cs.execute();

        String result = cs.getString(2);

        connection.commit();
    } catch (SQLException e) {
        connection.rollback();
        throw e;
    }
}
~~~

Key principles:

- Procedures generally should not issue COMMIT themselves if the transaction is controlled by the calling application.
- If a REF CURSOR must be fetched, keep the Connection and statement open until reading completes.
- Never return a ResultSet outside after closing the Connection or returning it to a pool.
- When using ARRAY or STRUCT, manage object lifecycles and call free() on java.sql.Array when finished.
- For transactions involving DML, commit only after evaluating the procedure result and completing required business steps.

If the application uses a connection pool, the Connection obtained from DataSource is a pool-managed handle. Calling close() returns the connection to the pool; do not close the underlying physical connection directly.

## 12. Resource management and performance

REF CURSORs, ARRAYs, and object types can carry large data volumes. Design APIs and fetch behavior appropriately.

### REF CURSOR returning too many rows

A cursor can return millions of rows. If Java collects the entire result into a List, heap usage can spike rapidly. Process row by row, narrow scope with filters, paginate, or batch.

Fetch size can be tuned:

~~~java
cs.setFetchSize(500);
~~~

Or on ResultSet/Statement depending on call style:

~~~java
rs.setFetchSize(500);
~~~

Fetch size is a hint to the driver for rows fetched per round trip; it does not limit total rows. Optimal values depend on row width, network latency, memory, and processing speed. Avoid setting huge fetch sizes blindly.

### Oversized ARRAYs

Array.getArray() can materialize an entire collection in Java memory. For lists with hundreds of thousands or millions of elements, consider smaller batches, staging tables, global temporary tables, or dedicated loading mechanisms rather than passing one massive collection in a single call.

### Object types with many attributes

Object types can contain nested objects, collections, LOBs, or large attributes. Mapping to Struct and Object[] can require allocating many objects. Return only needed fields; if data is primarily flat tabular rows, a REF CURSOR with scalar columns may be easier to manage.

### Round trips and payload size

A procedure accepting an ARRAY can reduce database calls compared to invoking a procedure once per element. However, an overly large payload increases network round-trip size, PGA/UGA usage, parsing, or SQL collection processing costs. Measure by batch size and realistic workloads.

## 13. Handling JDBC and Oracle errors

When a procedure fails, JDBC typically throws SQLException. Record SQLState, vendor error code, and message details:

~~~java
try {
    cs.execute();
} catch (SQLException e) {
    System.err.println("SQLState: " + e.getSQLState());
    System.err.println("ErrorCode: " + e.getErrorCode());
    System.err.println("Message: " + e.getMessage());

    for (SQLException next = e.getNextException();
         next != null;
         next = next.getNextException()) {
        System.err.println("Next: " + next.getMessage());
    }

    throw e;
}
~~~

Common errors:

| Error | Possible cause |
|---|---|
| ORA-06550 / PLS-00306 | Wrong number or types of arguments calling procedure/function |
| ORA-00932 | Incompatible input data type |
| ORA-01008 | Missing bind variable |
| ORA-04043 | Object/type/package name does not exist or is not visible |
| ORA-06512 | PL/SQL line in stack trace, usually accompanying root error |
| ORA-17004 | Invalid column/parameter type in JDBC operation |
| ORA-17059 | Failed to convert data to type requested by driver |
| ORA-17071 | Data or operation exceeded driver/data-type limit in a specific case |

When encountering REF CURSOR errors, check OUT registration type, procedure name, EXECUTE privileges, and driver version. For ARRAY/STRUCT, check that the SQL type name includes full schema qualification, exists at schema level, and the connecting account has privilege to use the type.

### Inspecting SQL type metadata

Object types and collection types can be inspected in the data dictionary:

~~~sql
SELECT owner,
       type_name,
       typecode
FROM   all_types
WHERE  owner = 'APP'
ORDER BY type_name;
~~~

Inspect object type attributes:

~~~sql
SELECT owner,
       type_name,
       attr_no,
       attr_name,
       attr_type_name,
       length,
       precision,
       scale
FROM   all_type_attrs
WHERE  owner = 'APP'
ORDER BY type_name, attr_no;
~~~

ALL_TYPES, ALL_TYPE_ATTRS, DBA_TYPES, and DBA_TYPE_ATTRS let you inspect type names, type kinds, and attribute structures subject to access privileges.

## 14. Privileges required to call PL/SQL APIs

The Java database account connecting to Oracle must have privileges to execute the package/procedure/function and use the associated types.

Example grants:

~~~sql
GRANT EXECUTE ON app.order_api TO app_runtime;
GRANT EXECUTE ON app.customer_id_list_t TO app_runtime;
GRANT EXECUTE ON app.address_t TO app_runtime;
GRANT EXECUTE ON app.address_list_t TO app_runtime;
~~~

If the package/procedure accesses tables in the same schema, definer-rights package permissions apply under PL/SQL rules. If the package uses invoker rights (AUTHID CURRENT_USER), execution privileges must be evaluated under the caller's privileges.

Do not grant direct privileges on every table to the application if API packages are already designed as the data access layer. Granting targeted EXECUTE privileges narrows the permission surface and keeps business logic in the database.

## 15. Choosing the right data return pattern

You do not always need REF CURSOR, ARRAY, and object types all at once. Choose the mechanism based on data shape and transfer direction:

| Need | Suitable mechanism |
|---|---|
| Return a status code, total amount, or count | Scalar OUT parameter |
| Return multiple query rows | REF CURSOR OUT |
| Pass a list of IDs or business codes | SQL nested table/VARRAY via ARRAY |
| Return a structure with multiple attributes | SQL object type via STRUCT or SQLData |
| Pass a list of object structures | SQL collection of object type |
| Return multiple independent result sets | Multiple REF CURSOR OUTs |
| Type existing only inside a PL/SQL package | SQL wrapper type or corresponding Oracle-specific API |

If only returning a flat set of rows, REF CURSOR is usually simpler than an object type. If passing a list of scalars, a SQL collection is often cleaner than generating many IN placeholders. If passing a structured, reusable record, a SQL object type may be appropriate.

## 16. Implementation workflow for Oracle JDBC with complex types

1. **Design the PL/SQL signature.** Identify IN, OUT, IN OUT, cursor, collection, and object type parameters.
2. **Create schema-level SQL types.** Create object types, nested tables, or VARRAYs if Java must pass/receive composite types.
3. **Create package/procedure/function.** Keep signatures stable and clearly define transaction ownership.
4. **Grant privileges.** Grant EXECUTE on packages and types to the application user.
5. **Select a compatible driver.** Use an Oracle JDBC driver compatible with JDK/database; verify REF_CURSOR, ARRAY, and object mapping support.
6. **Call via CallableStatement.** Bind IN, register OUT, and execute with exact parameter order.
7. **Read results with matching types.** REF CURSOR to ResultSet, ARRAY to java.sql.Array, objects to Struct/SQLData.
8. **Manage transactions.** Keep Connection open while fetching, and commit/roll back per business boundaries.
9. **Close resources.** Close ResultSet, CallableStatement, Array, and Connection via try-with-resources or finally.
10. **Test edge cases.** Test NULLs, empty collections, many elements, empty result sets, large payloads, PL/SQL errors, and schema type changes.

## 17. Key principles

- CallableStatement is the JDBC API for calling procedures/functions and registering OUT parameters.
- OUT parameters require registerOutParameter() before execute; IN OUT requires both setting value and registering type.
- REF CURSOR is usually registered using OracleTypes.CURSOR or Types.REF_CURSOR depending on driver, then read as a ResultSet.
- REF CURSOR is a database-side cursor; keep Connection/Statement open until fetching completes.
- ARRAY in Oracle JDBC requires a schema-level SQL collection type; use OracleConnection.createOracleArray() to construct arrays.
- createOracleArray() takes the collection type name, not the element type name.
- SQL object types map via Struct, or a class implementing SQLData/Oracle APIs.
- getAttributes() returns attributes in the declaration order of the SQL object type.
- SQL nested tables/VARRAYs differ from PL/SQL associative arrays; do not use SQL ARRAY APIs for every PL/SQL collection.
- Call Array.free() after use and close ResultSet/Statement/Connection in proper order.
- Use BigDecimal for Oracle NUMBER when precision must be preserved.
- Check EXECUTE privileges on packages and types, schema/type names, driver version, and transaction boundaries when errors occur.

Oracle JDBC provides rich mechanisms for exchanging data with PL/SQL. By properly understanding OUT parameters, REF CURSORs, ARRAYs, and object types, Java can call database APIs cleanly, pass lists or structured records efficiently, and keep transactions and connection resources under control.
