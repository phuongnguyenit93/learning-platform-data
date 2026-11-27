# Customizing Tables in Asciidoctor

## 1. Why Customize Tables in REST API Documentation?

Spring REST Docs generates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Beyond request and response snippets, the framework can also generate tables describing request fields, response fields, headers, parameters, and hypermedia links. These tables are written as AsciiDoc tables, which Asciidoctor then processes to produce HTML, PDF, or other outputs.

Default tables are usually sufficient, but API documentation may need adjustments for better readability: wider description columns than field-name columns, preventing code content from wrapping excessively, prominent headers, consistent table borders, or alternating row stripes for long tables. Asciidoctor provides table attributes to format those tables.

Example of a response fields table generated from REST Docs:

```asciidoc
|===
|Path |Type |Description

|id
|Number
|Book ID

|title
|String
|Book title displayed to users
|===
```

When rendering, Asciidoctor converts the table structure into HTML or PDF. Table attributes can control column widths, alignment, borders, headers/footers, and how content is displayed.

## 2. Basic Structure of a Table Block

AsciiDoc uses the `|===` delimiter to open and close a table. Attributes are placed in a block attribute list immediately before the delimiter:

```asciidoc
[cols="1,3", options="header", stripes="even"]
|===
|Field |Description

|id
|Book ID

|title
|Book title
|===
```

Main components:

| Component | Role |
| --- | --- |
| `[cols="..."]` | Declares the number of columns and column width/style rules. |
| `options="header"` | Marks the first row as a header. |
| `stripes="even"` | Applies striped backgrounds to rows as selected. |
| `|===` | Delimiter opening/closing a table block. |
| `|Field` | Content of a cell; the `|` character starts a cell. |

In REST Docs snippets, the first row is usually already generated as a header. When including an existing snippet, do not manually add a second header row if the file already contains a header.

## 3. Adjusting Column Widths with `cols`

`cols` specifies the number of columns and their relative or percentage widths. For REST Docs tables that typically have name, type, and description columns, allocate more space to the description column.

### Relative Widths

```asciidoc
[cols="1,1,3", options="header"]
|===
|Path |Type |Description
|id |Number |Unique book identifier
|title |String |Book title displayed in lists and detail pages
|===
```

The numbers `1,1,3` are relative weights, not character counts. The third column is allocated more space than the first two columns.

### Percentage Widths

```asciidoc
[cols="20%,20%,60%", options="header"]
|===
|Path |Type |Description
|id |Number |Unique book identifier
|title |String |Book title displayed to users
|===
```

Percentages are useful when you want predictable layouts. The percentages should usually sum to 100% to avoid unexpected results.

### Combining Column Width and Style

You can attach a style to each column in the column spec:

```asciidoc
[cols="1m,1,3", options="header"]
|===
|Path |Type |Description
|`id` |Number |Book ID
|`publishedAt` |String |Release timestamp in ISO-8601
|===
```

The `m` style is commonly used for monospace. Columns can have other styles such as `a` (AsciiDoc content) or `l` (literal), depending on the content. Use an appropriate style so code/paths stand out from prose.

## 4. Choosing Between Content-Fitted and Full-Width Tables

Asciidoctor supports options related to how tables use space:

| Attribute | Purpose |
| --- | --- |
| `autowidth` | Bases table and column widths more on content, instead of expanding across the entire available area by default. |
| `width="100%"` | Requests the table to span the full available width. |
| `fit-content` | Layout option for fitting the table to its content in supported backends. |

Example of a full-width table:

```asciidoc
[cols="1,3", width="100%", options="header"]
|===
|Header |Description
|Authorization |Bearer token used to authenticate the request
|If-None-Match |ETag stored by the client to check whether the representation has changed
|===
```

Example of a compact table:

```asciidoc
[cols="1,1", options="header", autowidth]
|===
|Status |Meaning
|200 |OK
|404 |Not Found
|===
```

Do not force `autowidth` on every table. A column with long descriptions or JSON paths can make the table wider than the page, especially when exporting to PDF. For field tables with substantial content, allocating relative widths and letting descriptions wrap is usually easier to read.

## 5. Headers, Footers, and Captions

Table attributes control the first row, last row, or caption:

```asciidoc
.[Table 1] Book response fields
[cols="1,1,3", options="header,footer"]
|===
|Path |Type |Description
|id |Number |Book ID
|title |String |Book title
|Total |2 fields |Fields documented in this example
|===
```

A few notes:

- `options="header"` indicates that the first row is the header.
- `options="footer"` marks the last row as the footer.
- A caption line takes the form `.[Caption text]` and is placed immediately before the block attributes/table.
- Do not add `header` if the snippet already has the proper header structure; inspect the generated file content before wrapping/formatting.

For tables generated by Spring REST Docs, the header usually contains column names like `Path`, `Type`, and `Description`. If you want to change header labels or language, consider a custom snippet template rather than adding a duplicate header from the main documentation file.

## 6. Formatting Borders and Row Stripes

The `frame`, `grid`, and `stripes` attributes give tables a consistent visual hierarchy:

```asciidoc
[cols="1,1,3", options="header", frame="topbot", grid="rows", stripes="even"]
|===
|Path |Type |Description
|id |Number |Book ID
|title |String |Book title
|publishedAt |String |Release date
|===
```

| Attribute | Common Values | Meaning |
| --- | --- | --- |
| `frame` | `all`, `topbot`, `sides`, `none` | Outer border of the table. |
| `grid` | `all`, `cols`, `rows`, `none` | Dividing lines between cells. |
| `stripes` | `none`, `even`, `odd`, `all` | Striped background for rows. |

Choose a light, consistent style across the entire documentation. For instance, `frame="topbot"`, `grid="rows"`, and `stripes="even"` can make long tables easier to follow without too many lines. Exact rendering also depends on the backend and stylesheet.

## 7. Aligning Content in Columns and Cells

You can align horizontally per column using symbols in the column spec:

```asciidoc
[cols="^1,>1,<3", options="header"]
|===
|Status |Code |Description
|OK |200 |Request was processed successfully
|Created |201 |New resource was created
|===
```

Commonly used alignment symbols:

| Symbol | Alignment |
| --- | --- |
| `<` | Left |
| `^` | Center |
| `>` | Right |

Vertical alignment can be set with `.`/`<`/`^`/`>` combined with styles at the column or cell level using AsciiDoc syntax. For example, a cell can use the `.^|` or `^|` cell specifier for vertical centering, depending on the case.

For API tables:

- Paths, header names, and JSON fields are usually left-aligned.
- Status codes or short values can be center- or right-aligned.
- Long description columns should be left-aligned for readability.

Avoid center-aligning entire long descriptions because it makes eye movement harder when comparing rows.

## 8. Applying Table Attributes to Included Snippets

Spring REST Docs generates snippets such as `response-fields.adoc`, `request-fields.adoc`, `request-headers.adoc`, `path-parameters.adoc`, and `links.adoc`. These files typically contain complete AsciiDoc tables. You can try placing block attributes immediately before the include to style the included table:

```asciidoc
=== Response fields
[cols="1m,1,3", options="header", frame="topbot", grid="rows"]
include::{snippets}/books-get/response-fields.adoc[]
```

For a query parameters table:

```asciidoc
=== Query parameters
[cols="1m,1,3", options="header", stripes="even"]
include::{snippets}/books-list/query-parameters.adoc[]
```

Asciidoctor processes includes during preprocessing, so inspect the rendered HTML/PDF afterward to confirm the attributes attach to the table block as desired. If a snippet is generated with a different block structure or a processor version does not apply attributes across the include boundary as expected, inspect the post-expansion source or switch to a custom snippet template.

**Do not edit files directly inside `build/generated-snippets` or `target/generated-snippets`.** Those files will be regenerated on the next test run. If a snippet type needs a custom default format across the entire project, the sustainable solution is a custom snippet template or a build-managed post-processing step.

## 9. Creating a Custom Snippet Template When Full Control Is Needed

When attributes placed before an include are not enough, you can customize Spring REST Docs snippet templates to control the generated markup. Examples include changing column labels, adding captions, reordering columns, or attaching consistent table attributes to all response-fields snippets.

General workflow:

1. Identify the snippet to customize, such as `response-fields`.
2. Copy the matching default template from the exact Spring REST Docs version in use.
3. Place the template in the test resources directory following the module's template customization mechanism.
4. Modify markup/attributes while preserving the model values and escaping the template needs to render.
5. Run tests to generate snippets and inspect the output file.
6. Render Asciidoctor HTML/PDF to verify the table displays properly on the actual backend.

Do not rewrite a template just to change a simple presentation attribute. Customizing templates increases maintenance burden when upgrading Spring REST Docs versions; use it only when consistent formatting is needed that include attributes cannot solve.

## 10. Complete Example for API Fields and Headers

A `books-get.adoc` file can present:

```asciidoc
== Get book by ID

=== HTTP request
include::{snippets}/books-get/http-request.adoc[]

=== Path parameters
[cols="1m,1,3", options="header", stripes="even"]
include::{snippets}/books-get/path-parameters.adoc[]

=== HTTP response
include::{snippets}/books-get/http-response.adoc[]

=== Response fields
[cols="1m,1,3", options="header", frame="topbot", grid="rows"]
include::{snippets}/books-get/response-fields.adoc[]
```

This example applies different styles to the parameters table and the response fields table. Path parameters tables are usually short, whereas response fields have longer descriptions so more width is allocated to the last column.

For headers:

```asciidoc
=== Request headers
[cols="1m,1,3", options="header", stripes="even"]
include::{snippets}/books-create/request-headers.adoc[]

=== Response headers
[cols="1m,1,3", options="header", stripes="even"]
include::{snippets}/books-create/response-headers.adoc[]
```

Only include tables generated by tests. If there is no header descriptor in the test, there is no corresponding file to include.

## 11. Differences Between HTML and PDF

Asciidoctor can render the same table block to different backends. HTML can usually rely on CSS to handle responsive layout, stripe colors, and borders. PDF has constraints on page width, fonts, and page-breaking capability; a table with an overly wide description column or long code strings may overflow.

| Issue | HTML | PDF |
| --- | --- | --- |
| Wide tables | Can scroll or adjust with site CSS. | May overflow margins or shrink text too small. |
| Long content | Browsers can wrap text via CSS. | Needs verification of wrapping and page breaks. |
| Row stripes | Depends on stylesheet/theme. | Depends on PDF theme/backend. |
| Monospace column | CSS can style code fonts. | Needs a monospace font with matching glyphs. |

Therefore, do not judge a table purely by looking at the AsciiDoc source. Render the actual output and inspect long tables, long URIs, long JSON paths, and multi-line descriptions.

## 12. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Columns have unexpected widths | `cols` uses unsuitable weights or percentages. | Adjust ratios, re-render, and inspect long content. |
| Table overflows the page | `autowidth`, long URI/path, or poorly allocated columns. | Use `width="100%"`, adjust `cols`, consider trimming content or splitting the table. |
| Header appears twice | Added a header in the wrapper while the snippet already had a header. | Inspect the snippet file; use only one header row. |
| Attributes do not apply to included snippet | Include is not parsed as a table block at that position or snippet markup differs from expectations. | Inspect expanded source/output; use a custom template if needed. |
| Row stripes do not appear in HTML | Theme/CSS overrides them or backend does not render the style as expected. | Check HTML classes/styles and active stylesheet. |
| PDF text is too small | Table is too wide or column ratios are unsuitable. | Adjust `cols`, reduce columns, or use landscape/page layout where appropriate. |
| Edited generated file but changes vanish next run | Snippet is overwritten when tests run. | Edit test templates or source AsciiDoc files, never generated output. |
| Invalid column spec used | Spec count does not match column count or style syntax is wrong. | Count columns and check AsciiDoc syntax. |

## 13. Practice Checklist

- [ ] Identified which snippet the table belongs to: fields, headers, parameters, or links.
- [ ] Inspected the source snippet to know its header row and column count.
- [ ] `cols` has matching column count and width allocation suited to content.
- [ ] Selected width/autowidth suited to the target HTML/PDF.
- [ ] Frame, grid, and stripes used consistently without visual clutter.
- [ ] Header/footer/caption do not duplicate existing snippet content.
- [ ] Alignment of path/type/status/description helps readers compare easily.
- [ ] Attributes placed before includes verified on actual rendered output.
- [ ] If more stable formatting is needed, considered custom snippet templates instead of editing generated files.
- [ ] Final HTML/PDF has no overflowing tables, overly narrow columns, or hard-to-read content.

Asciidoctor lets you adjust tables with `cols`, `width`, `autowidth`, `frame`, `grid`, `stripes`, alignment, and header/footer attributes. With Spring REST Docs, start by applying table attributes to included snippets and inspecting rendered output; only customize snippet templates when deeper markup control is required. Never edit generated snippets directly, as they are regenerated outputs from HTTP tests.

## References

- [Asciidoctor – Tables](https://docs.asciidoctor.org/asciidoc/latest/tables/build-a-basic-table/)
- [Asciidoctor – Column Widths and Styles](https://docs.asciidoctor.org/asciidoc/latest/tables/assign-columns/)
- [Asciidoctor – Table Attributes](https://docs.asciidoctor.org/asciidoc/latest/tables/format-table/)
- [Spring REST Docs – Customizing Snippets](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
