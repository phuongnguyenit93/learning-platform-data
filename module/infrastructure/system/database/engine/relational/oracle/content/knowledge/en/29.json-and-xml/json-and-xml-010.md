# XMLType, XMLTABLE, XMLQUERY, and XMLEXISTS in Oracle Database

## 1. XML in a Relational Database

Many business systems exchange data using XML: purchase orders, electronic invoices, integration messages, profiles, configuration data, and documents from external systems. XML is hierarchical, supports namespaces, and can contain repeating elements. Meanwhile, Oracle Database stores relational data in tables, rows, columns, and SQL data types.

Oracle XML DB provides data types and SQL/XML functions to work with XML directly inside the database. Four key components are:

- **XMLType:** an Oracle data type used to store and represent XML.
- **XMLTABLE:** converts nodes in XML into relational rows and columns for JOINs, filtering, aggregation, or data loading.
- **XMLQUERY:** executes an XQuery expression over XML and returns an XMLType result.
- **XMLEXISTS:** checks whether an XQuery expression returns a non-empty sequence; commonly used as a filter condition in WHERE.

These components let you combine XML data with SQL without pulling the entire document into the application to parse with external code.

~~~text
XML document
     |
     v
  XMLType
     |
     +--------------------+
     |                    |
     v                    v
 XMLQUERY              XMLTABLE
 extract/transform     split nodes into rows/columns
     |                    |
     v                    v
 XMLType result       relational rows
     |                    |
     +---------+----------+
               |
               v
           SQL query
               |
               v
           XMLEXISTS
     filter by node existence
~~~

> This lesson uses Oracle Database 19c and standard SQL/XML functions. XMLType has multiple storage models; syntax and features may depend on the database version, XML kind, schema registration, and XML DB configuration. Examples should be run in a lab schema with privileges to create tables, indexes, and query relevant dictionary views.

## 2. XML Documents, Well-Formedness, and Validity

Before storing XML, distinguish two concepts.

### 2.1. Well-Formed XML

Well-formed XML adheres to XML syntax:

- Exactly one top-level document element when using an XML document.
- Opening and closing tags match properly.
- Elements nest in the proper order.
- Attributes are enclosed in quotes.
- Special characters are properly escaped.
- There are no multiple root elements in a single document.

Well-formed example:

~~~xml
<PurchaseOrder>
  <Reference>PO-1001</Reference>
  <Status>APPROVED</Status>
</PurchaseOrder>
~~~

Malformed example:

~~~xml
<PurchaseOrder>
  <Reference>PO-1001</Status>
</PurchaseOrder>
~~~

Opening tag Reference does not match closing tag Status.

### 2.2. Valid XML

An XML document can be well-formed yet invalid against an XML Schema (XSD). For example, the XSD requires Quantity to be a positive integer, while the XML contains abc.

- Well-formedness checks XML syntactic structure.
- Schema-validity checks whether the document conforms to type definitions, cardinality, namespaces, and constraints in the XSD.

Not every XMLType is automatically validated against an XML Schema. Distinguish non-schema-based XMLType from schema-based XMLType.

### 2.3. Namespaces Are Part of XML Names

Two elements with the same local name but different namespace URIs are two different names:

~~~xml
<a:Order xmlns:a="urn:company:order">
  <a:Id>100</a:Id>
</a:Order>
~~~

~~~xml
<b:Order xmlns:b="urn:partner:order">
  <b:Id>100</b:Id>
</b:Order>
~~~

a:Order and b:Order are not the same because their namespace URIs differ. Prefixes a or b are merely aliases; the true identifier is the namespace URI combined with the local name.

## 3. What Is XMLType?

XMLType is the Oracle data type for XML. It allows storing XML in a column or an XMLType table and provides SQL/XML functions to query, transform, and serialize its contents.

### 3.1. XMLType Column

Example creating an order storage table:

~~~sql
CREATE TABLE purchase_orders (
    po_id NUMBER PRIMARY KEY,
    document XMLTYPE
);
~~~

DOCUMENT is the XMLType column name. The table can still hold relational columns such as PO_ID, creation date, or customer ID alongside the XML.

### 3.2. XMLType Table

You can create a table where each row is an XMLType instance:

~~~sql
CREATE TABLE purchase_order_documents OF XMLTYPE;
~~~

This table style fits when the primary unit of data is the entire XML document. For applications needing relational keys, processing state, or business metadata, an XMLType column inside a relational table is usually more convenient.

### 3.3. XMLType vs. CLOB Containing XML

A CLOB column only stores text. The database does not inherently treat that content as an XML value when running normal SQL operations.

An XMLType column represents data using the XML model and can be used directly with XMLTABLE, XMLQUERY, XMLEXISTS, XMLCAST, and XMLSERIALIZE.

If XML is stored as CLOB, the application often has to parse or convert it to XMLType before querying with SQL/XML. For frequent XML workloads, evaluate storing XMLType instead of plain text strings.

### 3.4. XMLType Storage Models

Oracle supports several XMLType storage models, notably:

- **Binary XML:** represents XML in Oracle XML DB binary format; suits most general XML workloads and is the common choice for new designs.
- **Object-relational storage:** maps schema-based XML onto Oracle relational objects/columns; can be useful for certain schema-aware models and structured queries.
- **CLOB-based storage:** an older text-based model mainly found in legacy systems; evaluate carefully before choosing it for new designs.

Do not pick a storage model purely out of habit. Measure read/write workloads, document sizes, path query patterns, schema registration, compatibility requirements, and indexing options.

Example specifying Binary XML for an XMLType column:

~~~sql
CREATE TABLE purchase_orders_bin (
    po_id NUMBER PRIMARY KEY,
    document XMLTYPE
)
XMLTYPE COLUMN document STORE AS SECUREFILE BINARY XML;
~~~

This example only illustrates choosing storage. SecureFiles creation also depends on tablespace and database configuration.

## 4. Creating XMLType from Strings and Loading Data

### 4.1. Using the XMLType Constructor

In labs or when creating small test datasets, you can use the constructor:

~~~sql
INSERT INTO purchase_orders(po_id, document)
VALUES (
    1001,
    XMLTYPE(
        '<PurchaseOrder>
           <Reference>PO-1001</Reference>
           <Status>APPROVED</Status>
         </PurchaseOrder>'
    )
);
~~~

The constructor converts a string into XMLType. The input XML must be syntactically valid.

### 4.2. Using XMLPARSE

XMLPARSE is the SQL/XML function for parsing XML text into XMLType:

~~~sql
INSERT INTO purchase_orders(po_id, document)
VALUES (
    1002,
    XMLPARSE(
        DOCUMENT
        '<PurchaseOrder>
           <Reference>PO-1002</Reference>
           <Status>PENDING</Status>
         </PurchaseOrder>'
    )
);
~~~

DOCUMENT is for an XML document with a single root element. CONTENT is for XML content/fragments per XML DB rules. For ordinary order documents, DOCUMENT is straightforward.

Do not use the WELLFORMED option casually. That option is an assertion from the caller that the data is already well-formed; it does not replace proper validation.

### 4.3. Loading XML from Bind Variables

In applications, pass XML payloads via bind variables instead of concatenating strings into SQL:

~~~sql
INSERT INTO purchase_orders(po_id, document)
VALUES (:p_po_id, XMLTYPE(:p_xml_text));
~~~

Bind variables separate data from SQL text, prevent quoting errors, and reduce SQL injection risks at the SQL layer.

### 4.4. COMMIT

~~~sql
COMMIT;
~~~

The INSERT examples above are standard DML. The application or calling script manages COMMIT/ROLLBACK according to transaction boundaries.

## 5. XMLSERIALIZE: Exporting XMLType as SQL Text

XMLType is an XML data type. When you need to display it, send it through an application, or write it to a file, use XMLSERIALIZE to serialize it into CLOB/BLOB or an appropriate character type.

~~~sql
SELECT XMLSERIALIZE(
           DOCUMENT document
           AS CLOB
           INDENT SIZE = 2
       ) AS xml_text
FROM purchase_orders
WHERE po_id = 1001;
~~~

Components:

- DOCUMENT: serializes an XML document.
- AS CLOB: returns the content as a CLOB.
- INDENT SIZE = 2: requests indented formatting for readability.

When processing XML content fragments rather than full documents, use the appropriate CONTENT form. Do not assume every XMLType value is a complete document.

### 5.1. Do Not Compare XML Based on Line Breaks

Two XML documents can represent the exact same data while differing in whitespace, namespace prefixes, or attribute order. Comparing serialized XML strings is not always equivalent to semantic XML comparison.

When business reconciliation is needed, extract meaningful nodes/values or use an XML-aware comparison mechanism. Do not rely solely on literal CLOB comparison to decide whether two documents are equivalent.

### 5.2. XMLSERIALIZE vs. Legacy Methods

In new code, prefer XMLSERIALIZE for exporting XMLType. Older methods such as getClobVal() may still appear in legacy code; avoid defaulting to those methods in new designs when SQL/XML functions meet the requirement.

## 6. XQuery and XPath in Oracle

XMLQUERY, XMLTABLE, and XMLEXISTS use XQuery expressions. XQuery is an XML query language with path expression syntax similar to XPath and supports variables, predicates, sequences, functions, and FLWOR expressions.

### 6.1. Path Expressions

Given the document:

~~~xml
<PurchaseOrder>
  <Reference>PO-1001</Reference>
  <Status>APPROVED</Status>
  <LineItems>
    <LineItem>
      <PartId>BK-01</PartId>
      <Quantity>2</Quantity>
    </LineItem>
  </LineItems>
</PurchaseOrder>
~~~

Sample paths:

| Path | Meaning |
| --- | --- |
| /PurchaseOrder | Root element |
| /PurchaseOrder/Reference | Direct Reference element |
| /PurchaseOrder/LineItems/LineItem | All LineItem elements under LineItems |
| //LineItem | LineItem at any depth below the context |
| @id | Attribute named id on the context element |
| text() | Text node of the element |

Use specific paths instead of broad // when the XML structure is known. Explicit paths document the schema for readers and can help the optimizer and indexes.

### 6.2. Predicates

Example selecting PurchaseOrder with Status APPROVED:

~~~xquery
/PurchaseOrder[Status = "APPROVED"]
~~~

Selecting LineItem with Quantity greater than 5:

~~~xquery
/PurchaseOrder/LineItems/LineItem[Quantity > 5]
~~~

### 6.3. FLWOR Expressions

XQuery supports for, let, where, order by, return:

~~~xquery
for $line in /PurchaseOrder/LineItems/LineItem
where xs:integer($line/Quantity) > 1
return $line
~~~

FLWOR is useful when filtering or restructuring a node sequence. For turning repeating nodes into relational rows and columns, XMLTABLE usually integrates more cleanly with SQL.

### 6.4. Context Items and XQuery Variables

XQuery can access the context item or variables passed via SQL PASSING. Example:

~~~xquery
$doc/PurchaseOrder[Status = $wanted_status]
~~~

In SQL, $doc and $wanted_status are bound via PASSING. This is safer and clearer than concatenating values directly into the XQuery string.

## 7. Namespaces in XML and XQuery

Namespaces are a common reason XML queries return empty results even though the element is visibly present.

### 7.1. XML Using a Default Namespace

Document:

~~~xml
<PurchaseOrder xmlns="urn:acme:purchase-order">
  <Reference>PO-1001</Reference>
  <Status>APPROVED</Status>
</PurchaseOrder>
~~~

The PurchaseOrder, Reference, and Status elements belong to namespace urn:acme:purchase-order. They are not in no-namespace.

The following path will not match:

~~~xquery
/PurchaseOrder/Reference
~~~

Because the query is searching for elements with no namespace.

### 7.2. Declaring Prefixes in XMLTABLE

XMLTABLE supports XMLNAMESPACES:

~~~sql
SELECT x.reference,
       x.status
FROM purchase_orders p
CROSS APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder'
    PASSING p.document
    COLUMNS
        reference VARCHAR2(30) PATH 'po:Reference',
        status    VARCHAR2(20) PATH 'po:Status'
) x;
~~~

The po prefix is chosen by the query; it does not have to match the prefix in the document. What matters is that the namespace URI matches.

### 7.3. Declaring Namespaces in XMLQUERY and XMLEXISTS

With XMLQUERY/XMLEXISTS, you can declare namespaces in the XQuery prolog:

~~~sql
SELECT XMLSERIALIZE(
           DOCUMENT XMLQUERY(
               'declare namespace po = "urn:acme:purchase-order";
                $d/po:PurchaseOrder/po:Reference'
               PASSING p.document AS "d"
               RETURNING CONTENT
           )
           AS CLOB
       ) AS reference_xml
FROM purchase_orders p;
~~~

XMLNAMESPACES in XMLTABLE is a SQL/XML clause; XMLQUERY and XMLEXISTS can use declare namespace inside the XQuery string. Do not mix the two syntaxes.

### 7.4. Nested Namespaces

A single document can use multiple namespaces:

~~~xml
<po:PurchaseOrder xmlns:po="urn:acme:po"
                  xmlns:addr="urn:acme:address">
  <po:Reference>PO-1001</po:Reference>
  <addr:ShipTo>
    <addr:City>Hanoi</addr:City>
  </addr:ShipTo>
</po:PurchaseOrder>
~~~

XMLTABLE:

~~~sql
XMLTABLE(
    XMLNAMESPACES(
        'urn:acme:po' AS "po",
        'urn:acme:address' AS "addr"
    ),
    '/po:PurchaseOrder'
    PASSING document
    COLUMNS
        reference VARCHAR2(30) PATH 'po:Reference',
        ship_city VARCHAR2(100) PATH 'addr:ShipTo/addr:City'
)
~~~

Each namespace URI must be declared with its corresponding prefix in the query.

## 8. XMLTABLE: Converting XML into Relational Rows and Columns

XMLTABLE is the most important tool when joining XML with relational data. It takes an XQuery row expression and a COLUMNS list. Each item in the resulting sequence produces one row.

### 8.1. General Syntax

~~~sql
XMLTABLE(
    [XMLNAMESPACES(...),]
    xquery_string
    [PASSING xml_expression [AS identifier], ...]
    COLUMNS
        column_name datatype PATH 'xquery_column_path',
        ...
)
~~~

Components:

- XMLNAMESPACES: declares namespace prefixes for XQuery/paths.
- XQuery row expression: determines which nodes/sequence generate rows.
- PASSING: passes XMLType and SQL values into XQuery.
- COLUMNS: maps nodes/attributes to SQL columns.

### 8.2. Extracting Header Information

Suppose purchase_orders.document contains:

~~~xml
<PurchaseOrder xmlns="urn:acme:purchase-order">
  <Reference>PO-1001</Reference>
  <Status>APPROVED</Status>
  <CustomerId>501</CustomerId>
  <LineItems>
    <LineItem>
      <PartId>BK-01</PartId>
      <Quantity>2</Quantity>
      <UnitPrice>15.50</UnitPrice>
    </LineItem>
    <LineItem>
      <PartId>PN-10</PartId>
      <Quantity>4</Quantity>
      <UnitPrice>3.25</UnitPrice>
    </LineItem>
  </LineItems>
</PurchaseOrder>
~~~

Extracting the header as a single row:

~~~sql
SELECT p.po_id,
       h.reference,
       h.status,
       h.customer_id
FROM purchase_orders p
CROSS APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder'
    PASSING p.document
    COLUMNS
        reference   VARCHAR2(30) PATH 'po:Reference',
        status      VARCHAR2(20) PATH 'po:Status',
        customer_id NUMBER       PATH 'po:CustomerId'
) h;
~~~

The row expression /po:PurchaseOrder returns a single root node, so XMLTABLE generates one row per document with a matching root.

### 8.3. Expanding Repeating Elements into Multiple Rows

To retrieve each LineItem:

~~~sql
SELECT p.po_id,
       h.reference,
       l.line_no,
       l.part_id,
       l.quantity,
       l.unit_price
FROM purchase_orders p
CROSS APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder'
    PASSING p.document
    COLUMNS
        reference VARCHAR2(30) PATH 'po:Reference'
) h
CROSS APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder/po:LineItems/po:LineItem'
    PASSING p.document
    COLUMNS
        line_no    FOR ORDINALITY,
        part_id    VARCHAR2(30) PATH 'po:PartId',
        quantity   NUMBER       PATH 'po:Quantity',
        unit_price NUMBER(12,2) PATH 'po:UnitPrice'
) l
ORDER BY p.po_id, l.line_no;
~~~

The relational output has one row per LineItem. FOR ORDINALITY generates the sequential number in the sequence returned by XMLTABLE.

### 8.4. The Row Expression Determines Row Count

If the XQuery row expression returns:

- Empty sequence: XMLTABLE produces 0 rows.
- One node: XMLTABLE produces 1 row.
- Multiple nodes: XMLTABLE produces one row per node.

This is the key distinction between the row expression and column PATHs. The row expression determines row cardinality; each PATH inside COLUMNS determines column values for each row.

### 8.5. Extracting Attributes

Given the XML:

~~~xml
<LineItem lineId="10">
  <PartId>BK-01</PartId>
  <Quantity>2</Quantity>
</LineItem>
~~~

XMLTABLE:

~~~sql
XMLTABLE(
    '/LineItem'
    PASSING document
    COLUMNS
        line_id NUMBER PATH '@lineId',
        part_id VARCHAR2(30) PATH 'PartId'
)
~~~

The @lineId notation accesses the attribute on the context element.

### 8.6. Returning an XMLType Column

Not every XMLTABLE column must be a scalar. You can return an XML subtree as XMLType:

~~~sql
XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder/po:LineItems/po:LineItem'
    PASSING document
    COLUMNS
        part_id VARCHAR2(30) PATH 'po:PartId',
        line_xml XMLTYPE PATH '.'
)
~~~

PATH '.' returns the current context item. An XMLType column is useful when child nodes need further processing via XMLQUERY or another XMLTABLE.

### 8.7. Preserving Documents Without Repeating Nodes

CROSS APPLY or an equivalent inner lateral join keeps only parent rows that have at least one matching node. To retain orders even when they have no LineItem, use OUTER APPLY:

~~~sql
SELECT p.po_id,
       l.part_id,
       l.quantity
FROM purchase_orders p
OUTER APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder/po:LineItems/po:LineItem'
    PASSING p.document
    COLUMNS
        part_id  VARCHAR2(30) PATH 'po:PartId',
        quantity NUMBER       PATH 'po:Quantity'
) l;
~~~

OUTER APPLY preserves the parent row and returns NULL for XMLTABLE columns when no matching item exists.

### 8.8. XMLTABLE and Bind Variables

You can pass SQL values into XQuery:

~~~sql
SELECT p.po_id,
       x.part_id,
       x.quantity
FROM purchase_orders p
CROSS APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder/po:LineItems/po:LineItem[po:Quantity > $min_qty]'
    PASSING p.document,
            :p_min_qty AS "min_qty"
    COLUMNS
        part_id  VARCHAR2(30) PATH 'po:PartId',
        quantity NUMBER       PATH 'po:Quantity'
) x;
~~~

The :p_min_qty value is passed as an XQuery variable. Never concatenate input values into the XQuery string.

## 9. XMLQUERY: Querying and Constructing XML Results

XMLQUERY runs an XQuery expression and returns XMLType. It is suitable when you want to extract a node, a sequence, or build a new XML structure.

### 9.1. General Syntax

~~~sql
XMLQUERY(
    'xquery_expression'
    [PASSING expr [AS identifier], ...]
    RETURNING CONTENT
)
~~~

RETURNING CONTENT specifies that the result is XML content. XMLQUERY does not return a standard SQL scalar; when VARCHAR2/NUMBER/DATE is needed, combine it with XMLCAST or use XMLTABLE.

### 9.2. Extracting a Node from XMLType

~~~sql
SELECT XMLSERIALIZE(
           CONTENT XMLQUERY(
               'declare namespace po = "urn:acme:purchase-order";
                $d/po:PurchaseOrder/po:Reference'
               PASSING p.document AS "d"
               RETURNING CONTENT
           )
           AS CLOB
       ) AS reference_xml
FROM purchase_orders p
WHERE p.po_id = 1001;
~~~

The XMLType result is the Reference node; XMLSERIALIZE converts the result to CLOB for display or transmission.

### 9.3. Returning a Node Sequence

~~~sql
SELECT XMLSERIALIZE(
           CONTENT XMLQUERY(
               'declare namespace po = "urn:acme:purchase-order";
                $d/po:PurchaseOrder/po:LineItems/po:LineItem'
               PASSING p.document AS "d"
               RETURNING CONTENT
           )
           AS CLOB
       ) AS line_items_xml
FROM purchase_orders p;
~~~

XQuery can return multiple LineItem nodes. Use CONTENT because the result may be a sequence/fragment rather than a single-rooted document.

### 9.4. Using FLWOR to Construct New XML

Example returning only lines with quantity greater than 1:

~~~sql
SELECT XMLSERIALIZE(
           CONTENT XMLQUERY(
               'declare namespace po = "urn:acme:purchase-order";
                for $line in $d/po:PurchaseOrder/po:LineItems/po:LineItem
                where xs:integer($line/po:Quantity) > 1
                return $line'
               PASSING p.document AS "d"
               RETURNING CONTENT
           )
           AS CLOB
           INDENT SIZE = 2
       ) AS filtered_lines
FROM purchase_orders p;
~~~

XQuery filters the sequence and returns matching nodes. This transforms the query result; it does not UPDATE the underlying data in the DOCUMENT column.

### 9.5. XMLQUERY Does Not Modify Stored XMLType

XMLQUERY only produces a query result. If you need to store the result, you must issue an explicit INSERT or UPDATE:

~~~sql
INSERT INTO archived_order_fragments(po_id, fragment)
SELECT p.po_id,
       XMLQUERY(
           'declare namespace po = "urn:acme:purchase-order";
            $d/po:PurchaseOrder/po:LineItems'
           PASSING p.document AS "d"
           RETURNING CONTENT
       )
FROM purchase_orders p
WHERE p.po_id = 1001;
~~~

Do not confuse XMLQUERY with the XQuery Update Facility or a SQL UPDATE statement.

## 10. XMLCAST: Converting an XML Result to a SQL Scalar

XMLCAST converts an XMLType value with compatible content into a SQL data type.

Example extracting Reference as VARCHAR2:

~~~sql
SELECT XMLCAST(
           XMLQUERY(
               'declare namespace po = "urn:acme:purchase-order";
                $d/po:PurchaseOrder/po:Reference/text()'
               PASSING p.document AS "d"
               RETURNING CONTENT
           )
           AS VARCHAR2(30)
       ) AS reference
FROM purchase_orders p;
~~~

Example extracting Quantity as NUMBER:

~~~sql
SELECT XMLCAST(
           XMLQUERY(
               'declare namespace po = "urn:acme:purchase-order";
                $d/po:PurchaseOrder/po:LineItems/po:LineItem[1]/po:Quantity/text()'
               PASSING p.document AS "d"
               RETURNING CONTENT
           )
           AS NUMBER
       ) AS first_quantity
FROM purchase_orders p;
~~~

If the XML text cannot be converted to the target type, the cast can raise an error. For partner data, control formatting, value ranges, and missing nodes.

### 10.1. Converting Date-Times with an Explicit Format

Do not depend on the session's NLS_DATE_FORMAT when converting date strings from XML. Extract the string and use TO_TIMESTAMP/TO_TIMESTAMP_TZ with an explicit format model.

Example string 2025-03-08T09:30:00+07:00:

~~~sql
TO_TIMESTAMP_TZ(
    l_timestamp_text,
    'YYYY-MM-DD"T"HH24:MI:SSTZH:TZM'
)
~~~

The actual format must match the lexical format of the XML schema/partner. Define time zone, offset, and handling for values lacking a time zone.

### 10.2. XMLTABLE Is Often More Convenient When Extracting Multiple Scalars

If you need five columns from the same node, using one XMLTABLE with five PATH expressions is usually cleaner than calling XMLQUERY/XMLCAST repeatedly for each column.

XMLCAST fits well when you only need to convert a single XML result into a scalar or when an XMLQUERY expression is already defined.

## 11. XMLEXISTS: Checking Existence of a Node/Sequence

XMLEXISTS evaluates XQuery and returns a SQL condition. It is commonly used in WHERE to filter XML documents by content.

### 11.1. General Syntax

~~~sql
XMLEXISTS(
    'xquery_expression'
    [PASSING expr [AS identifier], ...]
)
~~~

XMLEXISTS returns TRUE if XQuery returns a non-empty sequence; it returns FALSE if the sequence is empty.

### 11.2. Finding Orders with Status APPROVED

~~~sql
SELECT p.po_id
FROM purchase_orders p
WHERE XMLEXISTS(
    'declare namespace po = "urn:acme:purchase-order";
     $d/po:PurchaseOrder[po:Status = $wanted]'
    PASSING p.document AS "d",
            'APPROVED' AS "wanted"
);
~~~

XQuery returns the PurchaseOrder node if Status matches APPROVED; if not, it returns an empty sequence.

### 11.3. Checking Whether Any LineItem Has Quantity Greater Than 5

~~~sql
SELECT p.po_id
FROM purchase_orders p
WHERE XMLEXISTS(
    'declare namespace po = "urn:acme:purchase-order";
     $d/po:PurchaseOrder/po:LineItems/po:LineItem[
         xs:integer(po:Quantity) > 5
     ]'
    PASSING p.document AS "d"
);
~~~

There is no need to extract all LineItems to the application. The database simply evaluates the existence condition matching the query.

### 11.4. Pitfall: XMLEXISTS Does Not Check Boolean Value

XMLEXISTS checks whether the sequence contains any items, not whether an item is boolean TRUE or FALSE.

Example:

~~~sql
XMLEXISTS('false()' PASSING document)
~~~

The expression false() returns a sequence containing one boolean item with value FALSE. That sequence is still non-empty, so XMLEXISTS returns TRUE.

Similarly, do not write an XQuery returning a single boolean value expecting XMLEXISTS to check truthiness. Write the path/predicate so the result is a node sequence containing nodes when the condition holds and an empty sequence when it does not.

Correct example:

~~~xquery
$d/PurchaseOrder[Status = "APPROVED"]
~~~

The predicate makes the sequence empty when Status does not match.

### 11.5. XMLEXISTS and Missing Nodes

If the path finds no node, XQuery typically returns an empty sequence; XMLEXISTS returns FALSE. This is useful for checking optional elements:

~~~sql
WHERE XMLEXISTS(
    'declare namespace po = "urn:acme:purchase-order";
     $d/po:PurchaseOrder/po:Approval'
    PASSING document AS "d"
)
~~~

This condition only checks that the Approval element exists. To verify a specific value, add a predicate.

## 12. Comparing XMLTABLE, XMLQUERY, XMLEXISTS, and XMLCAST

| Component | Input | Result | When to Use |
| --- | --- | --- | --- |
| XMLType | XML text/schema/XML value | XMLType value | Storing and representing XML |
| XMLTABLE | XQuery row expression + XML | SQL rows/columns | Unnesting XML to JOIN, filter, aggregate |
| XMLQUERY | XQuery expression + XML | XMLType | Extracting or constructing XML results |
| XMLEXISTS | XQuery expression + XML | SQL condition | Filtering documents by node/condition existence |
| XMLCAST | XMLType value | SQL scalar | Converting an XML result to NUMBER/VARCHAR2/... |
| XMLSERIALIZE | XMLType value | CLOB/BLOB/character | Exporting XML as text/binary |
| XMLPARSE | XML text | XMLType | Parsing text into an XML value |

Combined example:

~~~sql
SELECT p.po_id,
       x.reference,
       x.status
FROM purchase_orders p
CROSS APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder'
    PASSING p.document
    COLUMNS
        reference VARCHAR2(30) PATH 'po:Reference',
        status    VARCHAR2(20) PATH 'po:Status'
) x
WHERE XMLEXISTS(
    'declare namespace po = "urn:acme:purchase-order";
     $d/po:PurchaseOrder[po:Status = "APPROVED"]'
    PASSING p.document AS "d"
);
~~~

XMLTABLE returns relational columns; XMLEXISTS filters documents. Combining them like this is often clearer when you need to display values while filtering on existence.

## 13. Schema-Based XML and Schema Validation

XMLType can be used with an XML Schema registered in Oracle XML DB. Schema-based XMLType binds documents to a namespace/schema and can leverage XSD data types, structures, and metadata.

### 13.1. Schema Registration

Oracle provides the DBMS_XMLSCHEMA package to register XML Schemas. Schema registration is an administrative operation requiring appropriate privileges and careful management of URIs, namespaces, dependencies, and storage options.

Conceptually:

1. Register the XSD in XML DB.
2. Create an XMLType column/table bound to the appropriate schema/element.
3. Load XML documents.
4. Validate against the schema when required by the workflow.
5. Query using XMLTABLE/XMLQUERY/XMLEXISTS.

Merely declaring an XMLType column does not make the database aware of a partner's XSD.

### 13.2. Well-Formed Does Not Mean Schema-Valid

XMLPARSE guarantees syntactic XML parsing. It does not automatically prove the XML satisfies all business constraints in an XSD.

If the integration contract requires schema validation, run validation via the corresponding XML DB mechanism before marking the payload valid.

### 13.3. Validation Has a Cost

Schema validation consumes CPU and can increase ingest latency. Decide where validation occurs:

- At the ingestion gateway.
- In the database before committing official records.
- In a verification batch before transitioning state.

Do not skip validation if it is a contract or compliance requirement. Conversely, avoid validating the same document redundantly across multiple layers without reason.

## 14. Storing XML and Data Model Design

### 14.1. XMLType Column Alongside Relational Metadata

A common design:

~~~sql
CREATE TABLE inbound_messages (
    message_id       NUMBER PRIMARY KEY,
    source_system    VARCHAR2(50) NOT NULL,
    received_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    processing_state VARCHAR2(20) NOT NULL,
    payload          XMLTYPE
);
~~~

Relational columns hold metadata frequently used for filtering/joining; the XMLType payload retains the source document structure.

### 14.2. Promoting Frequently Queried Attributes

If every query needs CustomerId, Status, or BusinessDate, consider:

- Storing those values as relational columns synchronized upon ingest.
- Using XMLTABLE to extract them when needed.
- Using an XMLIndex tailored to the path workload.

Do not extract and duplicate data without synchronization rules. If the XML payload and relational columns diverge, define which source is the source of truth.

### 14.3. Preserving Raw Payloads for Auditing

In integrations, you may need to store the exact original payload to:

- Troubleshoot errors from the sending system.
- Reconcile received contents.
- Replay messages.
- Support audits.

If an exact byte stream must be preserved, XMLType does not necessarily preserve every lexical detail verbatim, such as whitespace, prefixes, or serialization formatting. Store an additional original BLOB/CLOB when audit contracts require exact byte-for-byte payloads.

### 14.4. Null, Missing, and Empty Elements

XML states to distinguish:

~~~xml
<!-- Missing element -->
<Order><Reference>PO-1</Reference></Order>

<!-- Present but empty element -->
<Order><Status/></Order>

<!-- Element with text -->
<Order><Status>OPEN</Status></Order>
~~~

Additionally, an XSD may allow xsi:nil="true" on nillable elements. Missing, empty, and nil do not always share the same business meaning.

When XMLTABLE maps to VARCHAR2, Oracle applies SQL NULL rules (an empty VARCHAR2 string is treated as NULL). If you must distinguish these states, check node existence separately with XMLEXISTS or extract the XMLType node before casting.

## 15. Indexes and XML Query Performance

### 15.1. Not Every XML Query Needs an XMLIndex

If the table is small or queries are infrequent, a full scan and XML evaluation may suffice. For large documents or frequent path-based workloads, inspect execution plans and measure performance before creating indexes.

### 15.2. XMLIndex

Oracle provides XMLIndex to accelerate XMLType queries. Basic XMLIndex creation example:

~~~sql
CREATE INDEX purchase_orders_xml_ix
ON purchase_orders(document)
INDEXTYPE IS XDB.XMLINDEX;
~~~

XMLIndex can be configured with structured components to optimize specific paths and data types. Index design should be driven by actual XQuery paths—simply creating an XMLIndex does not guarantee every XML query runs faster.

### 15.3. Indexing Relational Columns

If queries frequently filter on PO_ID, SOURCE_SYSTEM, or PROCESSING_STATE, relational indexes often deliver clearer benefits:

~~~sql
CREATE INDEX inbound_messages_state_ix
ON inbound_messages(processing_state, received_at);
~~~

Do not use XMLIndex as a substitute for relational indexes when the primary filter predicates are on relational columns.

### 15.4. Optimizing Path Expressions

- Use specific paths and exact namespaces.
- Avoid // when the structure is known and explicit paths can express it.
- Do not serialize XML to CLOB and use LIKE to search for nodes.
- Use XMLEXISTS for existence predicates.
- Use a single XMLTABLE to extract multiple columns instead of repeated XMLQUERY calls.
- Extract only needed nodes/columns.
- Measure execution plans, logical reads, elapsed time, and cardinality.

### 15.5. XMLIndex and Storage Models

XMLIndex capabilities depend on the XMLType storage model and index configuration. Consult the Oracle XML DB Developer's Guide before choosing a storage/index combination. Do not assume an XMLIndex works identically across every XMLType storage type or every path without restrictions.

### 15.6. Inspecting Execution Plans

~~~sql
EXPLAIN PLAN FOR
SELECT po_id
FROM purchase_orders
WHERE XMLEXISTS(
    'declare namespace po = "urn:acme:purchase-order";
     $d/po:PurchaseOrder[po:Status = "APPROVED"]'
    PASSING document AS "d"
);

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Check whether Oracle uses XMLIndex or an appropriate access path. EXPLAIN PLAN shows the estimated plan; for production workloads, inspect the cursor plan and runtime statistics when you have appropriate privileges and tools.

## 16. Security When Processing XML

XML is input data, not trusted code. Both the payload and the surrounding SQL/XQuery statements must be controlled.

### 16.1. Use Bind Variables in SQL and PASSING in XQuery

Do not concatenate user values into SQL text or XQuery strings. Example:

~~~sql
WHERE XMLEXISTS(
    'declare namespace po = "urn:acme:purchase-order";
     $d/po:PurchaseOrder[po:Reference = $ref]'
    PASSING document AS "d",
            :p_reference AS "ref"
)
~~~

The reference value is passed as an XQuery variable. This keeps query text stable and separates data from expressions.

### 16.2. Controlling Payload Size and Structure

For external XML:

- Enforce payload size limits.
- Control nesting depth and node counts if the application sets limits.
- Handle timeouts and parse errors.
- Validate schemas/contracts as needed.
- Avoid logging full sensitive payloads unnecessarily.

### 16.3. External Entities and DTDs

XML parsers can support features related to DTDs and external entities. When processing untrusted XML, review the parser/XML DB settings for your deployed version to prevent payloads from accessing external resources or causing uncontrolled entity expansion. Do not assume all environments share identical parser policies.

### 16.4. XML DB Privileges

Do not grant broad privileges on the XDB schema or XML DB components just to get an application running. Grant the minimum privileges required for tables, XML schema registration, XMLIndex, or actual administrative operations.

### 16.5. Do Not Treat XML Schema as Authorization

An XSD validates structure and data types; it does not prove the sender is authorized to create or modify an order. Authorization must still be enforced at the business and database layers.

## 17. Common Errors and Diagnostics

| Symptom/Error | Possible Cause | Resolution |
| --- | --- | --- |
| XMLTABLE returns 0 rows | Wrong row path, namespace mismatch, or missing node | Check XMLSERIALIZE, namespace URI, and path |
| XMLTABLE columns are all NULL | Wrong column PATH or element in another namespace | Declare XMLNAMESPACES and check context item |
| XMLQUERY returns NULL | XQuery returns empty sequence or input XML is NULL | Test simpler path and verify node existence |
| XMLEXISTS always TRUE | XQuery returns boolean FALSE item instead of empty sequence | Use a path expression returning a node sequence |
| ORA-31011 | XML parsing failed | Check well-formedness, encoding, and payload |
| ORA-19202 | General XML processing error; usually accompanied by detailed XML/XQuery error | Read the full error stack, check XQuery and XML input |
| ORA-19228 | XQuery static error, e.g., undeclared variable/namespace | Check prolog, PASSING aliases, and prefixes |
| ORA-19279 | XQuery dynamic type/cardinality error in certain expressions | Check node type, cast, and returned item count |
| ORA-19025 | Extract value encountered multiple nodes or non-scalar result in legacy API | Use XMLTABLE for multiple rows or a path selecting a single node |
| ORA-01400 after XMLTABLE | Element missing/null while target table column is NOT NULL | Validate data before INSERT or handle defaults |
| ORA-01722 | XML text cannot be converted to NUMBER | Inspect lexical value and cast/format |
| Wrong results when XML uses a default namespace | Query path does not declare a namespace | Declare prefix bound to the exact URI |
| Slow XML queries | Broad paths, repeated parse/extract, missing index, or poor cardinality estimation | Use specific paths, single XMLTABLE, check plan and XMLIndex |
| XML output differs from input string | XML was re-parsed/serialized, changing formatting/prefixes/whitespace | Compare XML semantics; store raw payload if byte-for-byte fidelity is required |

Do not stop at the first ORA code if Oracle returns a deeper XML/XQuery error stack. The details usually reveal whether the fault lies in parsing, namespaces, static XQuery, or casting.

## 18. Self-Contained Lab: XMLType, XMLTABLE, XMLQUERY, and XMLEXISTS

The following steps create a dedicated table for testing. Do not run on live application tables.

### 18.1. Create an XMLType Table

~~~sql
CREATE TABLE po_xml_lab (
    po_id NUMBER PRIMARY KEY,
    document XMLTYPE
);
~~~

### 18.2. Load Documents with Namespaces

~~~sql
INSERT INTO po_xml_lab(po_id, document)
VALUES (
    1,
    XMLPARSE(
        DOCUMENT
        '<PurchaseOrder xmlns="urn:acme:purchase-order">
           <Reference>PO-1001</Reference>
           <Status>APPROVED</Status>
           <CustomerId>501</CustomerId>
           <LineItems>
             <LineItem>
               <PartId>BK-01</PartId>
               <Quantity>2</Quantity>
               <UnitPrice>15.50</UnitPrice>
             </LineItem>
             <LineItem>
               <PartId>PN-10</PartId>
               <Quantity>4</Quantity>
               <UnitPrice>3.25</UnitPrice>
             </LineItem>
           </LineItems>
         </PurchaseOrder>'
    )
);

INSERT INTO po_xml_lab(po_id, document)
VALUES (
    2,
    XMLPARSE(
        DOCUMENT
        '<PurchaseOrder xmlns="urn:acme:purchase-order">
           <Reference>PO-1002</Reference>
           <Status>PENDING</Status>
           <CustomerId>502</CustomerId>
           <LineItems>
             <LineItem>
               <PartId>HD-02</PartId>
               <Quantity>10</Quantity>
               <UnitPrice>8.00</UnitPrice>
             </LineItem>
           </LineItems>
         </PurchaseOrder>'
    )
);

COMMIT;
~~~

### 18.3. Read Back XML Using XMLSERIALIZE

~~~sql
SELECT po_id,
       XMLSERIALIZE(DOCUMENT document AS CLOB INDENT SIZE = 2) AS xml_text
FROM po_xml_lab
ORDER BY po_id;
~~~

### 18.4. Extract Header Using XMLTABLE

~~~sql
SELECT p.po_id,
       x.reference,
       x.status,
       x.customer_id
FROM po_xml_lab p
CROSS APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder'
    PASSING p.document
    COLUMNS
        reference   VARCHAR2(30) PATH 'po:Reference',
        status      VARCHAR2(20) PATH 'po:Status',
        customer_id NUMBER       PATH 'po:CustomerId'
) x
ORDER BY p.po_id;
~~~

### 18.5. Expand LineItems into Multiple Rows

~~~sql
SELECT p.po_id,
       l.line_no,
       l.part_id,
       l.quantity,
       l.unit_price
FROM po_xml_lab p
CROSS APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder/po:LineItems/po:LineItem'
    PASSING p.document
    COLUMNS
        line_no    FOR ORDINALITY,
        part_id    VARCHAR2(30) PATH 'po:PartId',
        quantity   NUMBER       PATH 'po:Quantity',
        unit_price NUMBER(12,2) PATH 'po:UnitPrice'
) l
ORDER BY p.po_id, l.line_no;
~~~

Expect three rows: two lines for PO-1001 and one line for PO-1002.

### 18.6. Filter with XMLEXISTS

~~~sql
SELECT po_id
FROM po_xml_lab p
WHERE XMLEXISTS(
    'declare namespace po = "urn:acme:purchase-order";
     $d/po:PurchaseOrder[po:Status = $s]'
    PASSING p.document AS "d",
            'APPROVED' AS "s"
);
~~~

Expect PO_ID = 1.

### 18.7. Test the Boolean Pitfall

~~~sql
SELECT po_id
FROM po_xml_lab p
WHERE XMLEXISTS('false()' PASSING p.document);
~~~

The expression above can return every row containing an XML document because false() is an item in the sequence, not an empty sequence. Use a path predicate to express existence conditions properly.

### 18.8. Extract a Scalar Using XMLQUERY and XMLCAST

~~~sql
SELECT p.po_id,
       XMLCAST(
           XMLQUERY(
               'declare namespace po = "urn:acme:purchase-order";
                $d/po:PurchaseOrder/po:Reference/text()'
               PASSING p.document AS "d"
               RETURNING CONTENT
           )
           AS VARCHAR2(30)
       ) AS reference
FROM po_xml_lab p
ORDER BY p.po_id;
~~~

### 18.9. Return an XML Fragment Using XMLQUERY

~~~sql
SELECT p.po_id,
       XMLSERIALIZE(
           CONTENT XMLQUERY(
               'declare namespace po = "urn:acme:purchase-order";
                $d/po:PurchaseOrder/po:LineItems/po:LineItem'
               PASSING p.document AS "d"
               RETURNING CONTENT
           )
           AS CLOB
           INDENT SIZE = 2
       ) AS lines_xml
FROM po_xml_lab p
WHERE p.po_id = 1;
~~~

### 18.10. Test OUTER APPLY

Insert a document without LineItems:

~~~sql
INSERT INTO po_xml_lab(po_id, document)
VALUES (
    3,
    XMLPARSE(
        DOCUMENT
        '<PurchaseOrder xmlns="urn:acme:purchase-order">
           <Reference>PO-1003</Reference>
           <Status>PENDING</Status>
           <CustomerId>503</CustomerId>
         </PurchaseOrder>'
    )
);

COMMIT;
~~~

Compare:

~~~sql
SELECT p.po_id, l.part_id
FROM po_xml_lab p
CROSS APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder/po:LineItems/po:LineItem'
    PASSING p.document
    COLUMNS part_id VARCHAR2(30) PATH 'po:PartId'
) l;
~~~

~~~sql
SELECT p.po_id, l.part_id
FROM po_xml_lab p
OUTER APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder/po:LineItems/po:LineItem'
    PASSING p.document
    COLUMNS part_id VARCHAR2(30) PATH 'po:PartId'
) l;
~~~

OUTER APPLY retains PO_ID = 3 even though it has no LineItem.

### 18.11. Clean Up Lab

~~~sql
DROP TABLE po_xml_lab PURGE;
~~~

Only run after finishing the lab when the data is no longer needed.

## 19. Checklist for Implementing XML in Oracle

1. **Is the XML well-formed?** Verify parsing and encoding.
2. **Is schema validation required?** Distinguish well-formedness from XSD-validity.
3. **Use XMLType or CLOB?** Choose based on workload and payload retention requirements.
4. **What is the storage model?** Binary XML, object-relational, or legacy storage.
5. **Are namespaces declared properly?** Match namespace URIs, not just prefixes.
6. **Is the XMLTABLE row path accurate?** Determine which nodes generate a SQL row.
7. **Are column PATHs in the right context?** Check relative paths and attributes.
8. **Is OUTER APPLY needed?** Retain parent rows when child nodes are absent.
9. **Need XMLQUERY or XMLTABLE?** XMLQUERY returns XML; XMLTABLE returns rows/columns.
10. **Need XMLEXISTS?** Use it to filter by non-empty node sequence; avoid returning boolean items.
11. **Need XMLCAST?** Control target types and conversion errors.
12. **Are missing, empty, and nil distinguished?** Do not collapse all states into a single meaning.
13. **Are bind variables / PASSING used?** Never concatenate input into SQL/XQuery strings.
14. **Is an appropriate index needed?** Measure the workload before creating an XMLIndex.
15. **Is the raw payload preserved?** Confirm audit/byte-for-byte retention requirements.
16. **Is untrusted XML controlled?** Size, depth, DTD/external entities, and privileges.
17. **Has the execution plan been checked?** Evaluate runtime behavior with representative data.
18. **Have namespaces and missing nodes been tested?** These are common edge cases to overlook.

## 20. Self-Check Questions

**Question 1.** How does XMLType differ from a CLOB containing XML?

**Question 2.** How do well-formed XML and schema-valid XML differ?

**Question 3.** What role does the namespace URI play when querying XML?

**Question 4.** How do an XMLType column and an XMLType table differ?

**Question 5.** When is XMLPARSE(DOCUMENT ...) used?

**Question 6.** What is the role of XMLSERIALIZE?

**Question 7.** What does the XMLTABLE row expression determine?

**Question 8.** What is FOR ORDINALITY used for?

**Question 9.** When is OUTER APPLY XMLTABLE needed?

**Question 10.** What data type does XMLQUERY return?

**Question 11.** What is XMLCAST used for?

**Question 12.** When does XMLEXISTS return TRUE?

**Question 13.** Why can XMLEXISTS('false()') return TRUE?

**Question 14.** Why does the path /PurchaseOrder/Reference fail to match XML with a default namespace?

**Question 15.** In what scenario is XMLTABLE usually more convenient than XMLQUERY/XMLCAST?

**Question 16.** Does XMLIndex replace indexes on relational columns?

**Question 17.** Why should user input not be concatenated into XQuery strings?

**Question 18.** Why does XMLType not necessarily preserve the exact original payload bytes?

<details>
<summary>Suggested Answers</summary>

1. CLOB is plain text; XMLType is an XML data type that can be used directly with SQL/XML operations.
2. Well-formed means valid XML syntax; valid means conforming to an XSD/contract schema.
3. The namespace URI is part of the expanded name; the prefix is merely an alias.
4. An XMLType column stores XML in a column of a relational table; an XMLType table has each row as an XMLType instance.
5. When parsing a string into a well-formed XML document.
6. Converts XMLType into a CLOB/BLOB/character representation for display or exchange.
7. The count and content of nodes generating each XMLTABLE row.
8. Generates sequential numbering for items in the sequence.
9. When you want to retain the parent row even if no matching child nodes exist.
10. XMLType.
11. Converts an XMLType result into a SQL scalar.
12. When the XQuery returns a non-empty sequence.
13. Because false() returns a boolean item; the sequence is still non-empty.
14. Because the elements belong to a namespace URI, while an unprefixed path searches for no-namespace elements.
15. When extracting multiple scalars from the same XML structure into SQL columns.
16. No. XMLIndex serves XML paths; relational indexes are still needed for relational predicates.
17. To prevent injection, quoting bugs, and keep query text stable; use PASSING/bind variables.
18. Parsing/serialization can alter whitespace, prefixes, or lexical representation even when XML semantics remain equivalent.

</details>

## 21. Official Oracle Documentation

1. [Oracle Database 19c XML DB Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/adxdb/): XML DB, XMLType, storage, XML schema, and SQL/XML.
2. [Oracle Database 19c XML DB Developer's Guide — Query and Update of XML](https://docs.oracle.com/en/database/oracle/oracle-database/19/adxdb/query-and-update-XML.html): querying XML with SQL/XML and XQuery.
3. [Oracle Database 19c SQL Language Reference — XMLTABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/XMLTABLE.html): XMLTABLE syntax, PASSING, XMLNAMESPACES, and COLUMNS.
4. [Oracle Database 19c SQL Language Reference — XMLQUERY](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/XMLQUERY.html): running XQuery and returning XMLType.
5. [Oracle Database 19c SQL Language Reference — XMLEXISTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/XMLEXISTS.html): XQuery sequence existence condition.
6. [Oracle Database 19c SQL Language Reference — XMLCAST](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/XMLCAST.html): converting XMLType values to SQL types.
7. [Oracle Database 19c SQL Language Reference — XMLSERIALIZE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/XMLSERIALIZE.html): serializing XMLType to SQL types.
8. [Oracle Database 19c SQL Language Reference — XMLPARSE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/XMLPARSE.html): parsing XML text into XMLType.
9. [Oracle Database 19c SQL Language Reference — XMLType](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/XMLTYPE.html): XMLType data type.
10. [Oracle Database 19c XML DB Developer's Guide — XMLIndex](https://docs.oracle.com/en/database/oracle/oracle-database/19/adxdb/indexes-for-XMLType-data.html): indexes for XMLType and path-based queries.
11. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_XMLSCHEMA](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XMLSCHEMA.html): registering and managing XML Schemas.

**Key Principle:** XMLType represents XML in the database; XMLTABLE turns nodes into relational rows and columns; XMLQUERY returns an XML result; XMLCAST converts results into scalars; XMLEXISTS filters by non-empty sequences; XMLSERIALIZE exports XML as text. Always declare namespaces with the exact URI, use PASSING/bind variables, distinguish well-formedness from schema-validity, and tune based on actual query paths and execution plans.
