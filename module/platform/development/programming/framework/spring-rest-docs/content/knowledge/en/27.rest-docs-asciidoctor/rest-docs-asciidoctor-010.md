# Formatting Columns and Avoiding Table Errors

## Learning Objectives

After this lesson, you will be able to:

- Write AsciiDoc tables using table delimiters and column specifications (colspec).
- Choose column width ratios using the cols attribute.
- Align left, center, and right and select the appropriate display style for each column.
- Configure headers, footers, frames, grids, widths, and autowidth.
- Handle long cells, multi-line cells, lists, code, and pipe characters inside content.
- Identify cell count errors, delimiter errors, cell span issues, and content that breaks table structure.
- Adjust Spring REST Docs snippet tables using custom snippet templates when needed.

## 1. What Are Tables in AsciiDoc Used For?

REST API documentation often includes tables describing path parameters, query parameters, request/response headers, JSON fields, error codes, and media types. Tables help readers quickly compare attributes that share a common structure.

Query parameter table example:

```asciidoc
[options="header"]
|===
|Name |Type |Required |Description

|page
|integer
|No
|Zero-based page number.

|size
|integer
|No
|Maximum number of items per page.

|sort
|string
|No
|Sort field and direction, e.g., createdAt,desc.
|===
```

In this example:

- options="header" marks the first line as the header row.
- |=== opens and closes the table block.
- Each pipe character at the start of a line starts a cell.
- Blank lines make the source easier to read and separate rows; they do not automatically create empty rows.

## 2. Configuring Column Widths with cols

The cols attribute defines column structure and ratios:

```asciidoc
[cols="1,2,3",options="header"]
|===
|Field |Type |Description

|id
|integer
|Unique identifier of the order.

|status
|string
|Current status, such as PENDING or COMPLETED.

|createdAt
|string
|Creation timestamp in ISO 8601 format.
|===
```

The numbers 1, 2, and 3 represent relative ratios. The third column is allocated three times as much width as the first column and 1.5 times as much width as the second column, within the table's total width. They are not pixel counts or absolute percentages.

### 2.1. Choosing Ratios Based on Content

| Content type | Suggested ratio | Reason |
| --- | --- | --- |
| Short field name, short type, long description | 1,1,3 | Allocate more space to the description |
| Error code, HTTP status, meaning | 1,1,3 | The meaning column usually contains long sentences |
| Header name and rule | 1,3 | Short header, longer explanation |
| Step, action, result | 1,2,3 | The result column usually requires more words |
| Columns with similar content | 1,1,1 | Distribute evenly for comparison |

This is a starting point. Render the table at the actual page size and adjust according to the longest content, not just the average character count.

### 2.2. cols with Percentages

```asciidoc
[cols="20%,25%,55%",options="header"]
|===
|Field |Type |Description
|id |integer |Identifier.
|createdAt |string |Creation timestamp in ISO 8601 format.
|===
```

When using percentages, the sum of widths should match the table width. Relative ratios like 1,2,3 are usually more flexible when tables render at multiple sizes; percentages are useful when explicit layout control is needed.

## 3. Column Alignment

Colspec can add alignment symbols:

- Less-than sign aligns left.
- Caret aligns center.
- Greater-than sign aligns right.

Example:

```asciidoc
[cols="<1,^1,>2",options="header"]
|===
|Field |Required |Description
|id |Yes |Identifier.
|page |No |Page number.
|total |Yes |Total number of items.
|===
```

The first column is left-aligned, the second column is center-aligned, and the last column is right-aligned. The numbers still express relative ratios.

| Content | Typically Suitable Alignment |
| --- | --- |
| Field name, header name, description | Left |
| HTTP status, short code, Yes/No | Center or left |
| Quantity, percentage, duration | Right |
| JSON path or code | Left, optionally monospace |

Do not center-align the entire table merely for visual symmetry. Technical content is usually easier to scan when text is left-aligned and numbers are right-aligned.

## 4. Table Width, Frame, and Grid

```asciidoc
[cols="1,3",options="header",width="100%",frame="topbot",grid="rows"]
|===
|Header |Description
|Authorization |Caller's bearer token.
|X-Request-Id |Request trace ID.
|===
```

| Attribute | Meaning |
| --- | --- |
| width | Table width, typically a percentage |
| frame | Outer border: all, sides, topbot, or none |
| grid | Cell/row dividers: all, cols, rows, or none |
| options="header" | First row is the header |
| options="footer" | Last row is the footer |
| options="autowidth" | Table shrinks/sizes to fit content |
| options="stretch" | Table stretches across its container in supported environments |

Frame/grid values may be interpreted differently by themes or converters. Verify on the HTML/PDF output that the project publishes.

### 4.1. When to Use autowidth?

autowidth fits small tables well:

```asciidoc
[options="header,autowidth"]
|===
|Status |Meaning
|200 |Success
|404 |Not found
|===
```

Tables with long descriptions are usually not suited for autowidth because columns can be compressed or stretched unpredictably by content. For field/description tables, set cols and width intentionally.

## 5. Configuring Display Styles for Columns and Cells

Colspec can control content style:

| Style | Purpose |
| --- | --- |
| a | AsciiDoc cell, allowing AsciiDoc content and blocks |
| e | Emphasis, emphasizes cell content |
| s | Strong, displays content in bold |
| m | Monospaced, suitable for code/identifiers |
| l | Literal, displays content verbatim |
| v | Verse, preserves line breaks in verse form |

Example where the first column displays in monospace:

```asciidoc
[cols="1m,3",options="header"]
|===
|Field path |Description
|customer.id |Customer ID.
|createdAt |Creation timestamp.
|===
```

You can combine ratios, alignment, and styles:

```asciidoc
[cols="<1m,^1,3",options="header"]
|===
|Field |Required |Description
|id |Yes |Identifier.
|updatedAt |No |Update timestamp.
|===
```

The first column is left-aligned and uses monospace; the second column is center-aligned; the description column uses the larger share of space. Do not overuse styles on every cell.

## 6. Multi-line Cells and Long Content

A cell can contain multi-line content. For simple content, continue in the same cell until a pipe character starts a new cell at the beginning of a line:

```asciidoc
[cols="1,3",options="header"]
|===
|Header |Description
|Authorization
|Caller's bearer access token.
The token must be sent over TLS and must not be logged.

|X-Request-Id
|Trace ID used for log correlation.
|===
```

When a cell needs multiple paragraphs, lists, or blocks, use an AsciiDoc cell with the a| prefix:

```asciidoc
[cols="1,3",options="header"]
|===
|Field |Description

|Authorization
a|
Request authentication header.

* Scheme: Bearer.
* Required for protected endpoints.
* Do not share real tokens in logs.

|X-Request-Id
a|
Request trace ID.

This ID can be used when contacting the support team.
|===
```

The a| cell style allows AsciiDoc blocks such as paragraphs and lists. It is useful when cell content is no longer a single plain line of text.

### 6.1. Code Content in Cells

For short code, use inline formatting or monospace cells:

```asciidoc
[cols="1,3",options="header"]
|===
|Header |Example
|Authorization |`Bearer <access-token>`
|Accept |`application/json`
|Content-Type |`application/problem+json`
|===
```

If a cell needs a multi-line code block, use an AsciiDoc cell:

```asciidoc
[cols="1,3",options="header"]
|===
|Field |Request example

|Authorization
a|
----
Authorization: Bearer <access-token>
----

|Content-Type
a|
----
Content-Type: application/json
----
|===
```

Keep code blocks inside cells short and purposeful. For long request/response examples, place the snippet outside the table instead of building a table containing an entire HTTP exchange.

## 7. Escaping Pipe Characters in Content

The pipe character is a structural delimiter that starts a cell. If content needs to contain the pipe character itself, it must be escaped so Asciidoctor does not interpret it as a new cell boundary.

Example describing a logical expression:

```asciidoc
[cols="1,3",options="header"]
|===
|Field |Description
|filter
|You can use the operator status \| priority according to the API's illustrative syntax.
|===
```

Inside table content, write a backslash before the pipe to represent that character. Inspect the output if the table has nested includes or cells containing literal/code blocks.

Another option is using the HTML entity &#124; when content is processed as text and needs to represent a pipe. Prefer escaping with AsciiDoc syntax in the source so maintainers recognize the intent.

### 7.1. Pipe Characters in Regex or Code

A regex containing pipes:

```text
^(GET|POST|DELETE)$
```

When placed inside a cell, escape the pipes:

```asciidoc
[cols="1,3",options="header"]
|===
|Pattern |Meaning
|`^(GET\|POST\|DELETE)$` |Accepts only one of the three HTTP methods.
|===
```

## 8. Merging and Splitting Cells

AsciiDoc supports spanning cells across rows or columns. Example of a cell spanning two columns:

```asciidoc
[cols="1,1,2",options="header"]
|===
|Field |Type |Description
2+|Request metadata
|id |integer |Identifier.
|status |string |Status.
|===
```

The 2+| cell occupies two columns in the same row. This is useful for content groups or subheadings, though it should not be overused.

A cell can span multiple rows:

```asciidoc
[cols="1,1,2",options="header"]
|===
|Resource |Method |Purpose
.2+|Orders
|GET
|Read orders.
|POST
|Create an order.
|Users
|GET
|Read user profile.
|===
```

Cell spans cause the number of declared cells in a row to differ from the physical column count. Check the structure and HTML output carefully; rows missing or having extra cells can shift data across columns.

## 9. Headers, Footers, and Title Rows

A table can have a header row:

```asciidoc
[options="header"]
|===
|HTTP status |Meaning
|200 |Success
|400 |Invalid request
|404 |Resource not found
|===
```

It can have a footer row when a summary is needed:

```asciidoc
[options="header,footer"]
|===
|Metric |Value
|Endpoints |12
|Documented scenarios |28
|Total |40
|===
```

Footers are useful for total rows, but should not be used to repeat headers or insert long conclusions. For API reference tables, a clear header row is usually more important than a footer.

## 10. Organizing Tables for REST API Documentation

| Table | Suggested Columns | Notes |
| --- | --- | --- |
| Path/query parameters | Name, Type, Required, Description | Describe defaults, formats, and examples |
| Request/response headers | Header, Required, Description | Distinguish client-sent headers from server-returned headers |
| JSON fields | Path, Type, Optional, Description | Distinguish optional from nullable |
| Error catalog | Status, Code, Description | Code names must match actual responses |
| Multipart parts | Part, Media type, Required, Description | Distinguish file parts from JSON metadata |
| Links | Relation, Target, Description | Describe navigation relations |

Do not cram all information into a single table with many columns. If descriptions are too long, separate the identifier table from explanatory paragraphs.

### 10.1. Field Tables with Long Descriptions

```asciidoc
[cols="2,1,1,4",options="header",width="100%"]
|===
|JSON path |Type |Required |Description
|id |integer |Yes |Server-assigned order ID. Clients do not create or modify this value.
|status |string |Yes |Order lifecycle status. Valid values are listed in the Order status section.
|note |string |No |Optional note from the creator. Maximum length and character rules must follow API validation.
|===
```

If a description spans multiple sentences, use an AsciiDoc cell a| to create paragraphs or lists. Do not force a table into an ultra-wide row if the documentation is read on small screens.

## 11. Snippet Tables Generated by Spring REST Docs

Spring REST Docs generates many snippets in AsciiDoc format, such as request-fields, response-fields, request-headers, response-headers, and parameter tables. These snippets usually contain table markup produced by default templates.

Authors can include them directly:

```asciidoc
=== Response fields
include::{snippets}/orders-get/response-fields.adoc[]
```

Snippet tables are generated from descriptors in tests. Do not edit generated-snippets files after each test run because the files will be regenerated.

If the default table does not fit, there are two approaches:

1. Adjust the page layout around the snippet, placing explanatory text before/after the table.
2. Configure a custom snippet template to control the table markup that REST Docs generates.

### 11.1. Custom Snippet Templates

Spring REST Docs allows customizing snippet templates using the integration's template engine mechanism. For table-based snippets, the template can define cols, options, frame, grid, and cell structure.

An illustrative AsciiDoc template fragment:

```asciidoc
[cols="2,1,4",options="header",width="100%"]
|===
|Path |Type |Description

// Cell rows rendered from the snippet template's model.
|id |integer |Identifier.
|status |string |Current status.
|===
```

This is only a static layout example. A real template must iterate over the snippet's model, escape cell content, and handle missing/null cells properly. Do not copy a static example as an active template without adding the data-rendering logic.

When customizing templates:

- Keep the snippet filename that the AsciiDoc page includes, or update includes synchronously.
- Keep data pulled from descriptors; do not hard-code field contents.
- Escape characters with AsciiDoc syntactic meaning, especially the pipe character.
- Test multi-line descriptions and code paths.
- Run documentation tests to regenerate snippets from the template.

## 12. Common Errors and Fixes

| Error | Possible Cause | Fix |
| --- | --- | --- |
| Columns are misaligned | Cell count in a row does not match the cols structure | Check delimiters and cell spans in each row |
| Pipe character breaks the table | Content has an unescaped pipe | Put a backslash before the pipe or use literal representation |
| Description column is too narrow | Unsuitable cols ratio | Increase the weight of the description column or use an appropriate width |
| Table overflows the page | Unbreakable long string or too many columns | Reduce columns, expand description area, wrap content, or split the table |
| Multi-line content turns into extra cells | Continuation line starts with a pipe | Place pipes only at the start of new cells; use a| for blocks |
| Lists in a cell do not render | Cell does not use AsciiDoc style | Use a| for cells containing blocks |
| Code in a cell is interpreted as markup | Cell uses default style with unsuitable inline syntax | Use monospace/literal cell or delimit code clearly |
| Snippet table gets overwritten after build | Editing generated-snippets directly | Edit the custom template or AsciiDoc source |
| Include works but table still looks bad | Default template does not control layout | Use a custom snippet template and re-render |

## 13. Table Verification Workflow

When a table's layout breaks, inspect from structure up to visual rendering:

1. Count the columns in cols and the actual cells in each row.
2. Check whether cell spans alter the physical cell count.
3. Look for pipe characters in descriptions, regexes, code, or URLs.
4. Check multi-line cells: continuation lines must not unintentionally open new cells.
5. Switch a cell to a| if lists or AsciiDoc blocks are needed.
6. Adjust cols ratios and width according to the column with the longest content.
7. Render HTML/PDF at the target page size and see whether the table overflows or text is too small.
8. If the table is generated by REST Docs, determine whether the file is generated output or a custom template before editing.

Do not inspect only the AsciiDoc source. A table can be syntactically valid yet still hard to read in PDF or on narrow screens.

## 14. Table Formatting Checklist

- [ ] Table block opens and closes with exact delimiters.
- [ ] Header row is declared if the table needs column headings.
- [ ] Colspec reflects column count and content ratios.
- [ ] Description column has enough width for long sentences.
- [ ] Left/center/right alignment matches data types.
- [ ] Width, frame, and grid fit the theme.
- [ ] Pipes inside content are escaped.
- [ ] Cells with multiple paragraphs/lists/code blocks use AsciiDoc cells when needed.
- [ ] Row spans/col spans result in valid cell counts.
- [ ] Do not force binary files or long HTTP exchanges into table cells.
- [ ] Generated snippets are customized via templates, not by editing temporary output.
- [ ] HTML/PDF is rendered and verified before release.

## 15. Practice Exercise

You need to document the response of the GET /api/orders/{id} endpoint. The response has fields id, status, createdAt, customer, and items. Descriptions of customer and items are longer than the remaining fields.

Perform the following:

1. Create a four-column table: JSON path, Type, Required, and Description.
2. Set column ratios so description is widest; render and refine.
3. Left-align path/type, center-align required if the result remains easy to scan.
4. Use an AsciiDoc cell containing a list for the items description.
5. Add a header row and check surrounding headings/TOC.
6. Put an expression containing pipe characters into a description and escape them properly.
7. Include the response-fields snippet generated by REST Docs; compare the default layout with a custom template.
8. Build HTML/PDF and inspect the table at the actual page size.

**Self-check question:** If an AsciiDoc table renders successfully but the Description column is only as wide as the Type column, should you edit the snippet output after the build or adjust the source that creates the table? For hand-written tables, edit cols in AsciiDoc. For tables generated by Spring REST Docs, adjust the custom snippet template or page layout. Do not edit generated-snippets manually because the next build will overwrite it.

## Conclusion

Good column formatting helps readers look up parameters, headers, JSON fields, and error catalogs faster. Use cols to control ratios or percentages, alignment symbols according to data type, and width/frame/grid/options to complete the layout. For long cells or cells with lists/code, switch to AsciiDoc cells so content parses accurately; escape pipe characters so rows do not break. Tables generated by Spring REST Docs should be adjusted through custom snippet templates or Asciidoctor layout rather than editing temporary output. Finally, render HTML/PDF at real sizes and check width, wrapping, cell spans, and include links before publishing.
