# Tài liệu tự sinh

## 1. Tài liệu tự sinh là gì?

Tài liệu tự sinh (documentation generation) là quá trình tạo tài liệu từ mã nguồn, cấu trúc chương trình, schema, metadata hoặc mô hình ngữ nghĩa bằng công cụ tự động. Trong hệ sinh thái DSL (Domain-Specific Language), tài liệu tự sinh giúp biến các khai báo và quy tắc trong ngôn ngữ thành hướng dẫn, reference và mô tả có thể đọc được bởi developer, người vận hành hoặc chuyên gia nghiệp vụ.

Ví dụ, một DSL định nghĩa:

~~~text
namespace sales;

type Order {
    id: OrderId
    total: Money
    status: OrderStatus
}

rule high-value-order {
    description: "Yêu cầu kiểm tra thủ công với đơn hàng giá trị cao."
    when order.total > money(10000000, VND)
    then requireManualReview(order.id)
}
~~~

Một documentation generator có thể tạo:

- Trang reference cho kiểu Order, gồm các field, kiểu dữ liệu và mô tả.
- Trang giải thích rule high-value-order, điều kiện kích hoạt và hành động.
- Danh sách function được dùng trong DSL.
- Sơ đồ quan hệ giữa type, rule và module.
- Ví dụ mã nguồn và liên kết tới vị trí khai báo.

Tài liệu được sinh có thể ở dạng Markdown, HTML, JSON reference data hoặc định dạng phù hợp với hệ thống tài liệu của dự án. Điểm quan trọng là nội dung được tạo từ nguồn có cấu trúc, giúp giảm việc viết lại thông tin đã tồn tại trong DSL.

Tài liệu tự sinh không có nghĩa mọi nội dung đều phải được tạo hoàn toàn bằng máy. Một hệ thống tốt thường kết hợp mô tả do con người viết với thông tin máy có thể trích xuất như tên, kiểu, chữ ký, quan hệ, ví dụ và vị trí nguồn.

## 2. Vì sao DSL cần tài liệu tự sinh?

DSL thường chứa các quy tắc nghiệp vụ, khai báo kiểu, function, module và cấu hình mà nhiều nhóm cùng sử dụng. Khi chương trình phát triển, việc duy trì tài liệu thủ công dễ dẫn đến chênh lệch giữa tài liệu và hành vi thực tế.

Tài liệu tự sinh mang lại các lợi ích:

1. **Giảm thông tin trùng lặp:** tên, kiểu, chữ ký và cấu trúc có thể được trích xuất trực tiếp từ source hoặc symbol index.
2. **Giữ tài liệu đồng bộ:** thay đổi khai báo có thể làm tài liệu được tạo lại trong cùng pipeline.
3. **Tăng khả năng khám phá:** người dùng có thể tìm type, function, rule và module theo cấu trúc.
4. **Hỗ trợ onboarding:** người mới có thể xem API reference, ví dụ và quy ước của DSL.
5. **Hỗ trợ vận hành:** tài liệu rule giúp hiểu điều kiện và hành động được cấu hình.
6. **Tăng khả năng truy nguyên:** trang tài liệu có thể liên kết tới file và dòng nguồn.
7. **Hỗ trợ kiểm tra thay đổi:** diff tài liệu có thể cho thấy API hoặc schema công khai đã thay đổi.

Ví dụ, nếu function calculateTax đổi tham số từ Order sang Invoice, tài liệu API được sinh lại có thể thể hiện thay đổi chữ ký ngay trong pull request. Reviewer có thể nhận ra ảnh hưởng tới người dùng DSL trước khi phát hành.

## 3. Các loại tài liệu có thể được tạo

Một DSL có thể tạo nhiều loại tài liệu khác nhau:

| Loại tài liệu | Nội dung | Người đọc chính |
|---|---|---|
| Language reference | Keyword, expression, grammar và semantics | Developer DSL |
| API reference | Function, type, parameter, return type và error | Developer tích hợp |
| Schema reference | Record, field, enum, constraint và default | Developer và data engineer |
| Rule catalog | Rule, điều kiện, action, owner và mô tả | Analyst và operator |
| Module reference | Namespace, import, export và dependency | Developer |
| Configuration reference | Các trường cấu hình và giá trị hợp lệ | Người vận hành |
| Example gallery | Chương trình mẫu theo use case | Người học DSL |
| Architecture reference | Quan hệ giữa module, type và thành phần | Maintainer |
| Change reference | Thay đổi API, schema và language version | Người nâng cấp |

Không nên tạo một trang duy nhất chứa mọi thông tin nếu người đọc có nhu cầu khác nhau. Có thể sinh nhiều trang liên kết từ cùng một document model.

## 4. Nguồn dữ liệu cho documentation generator

Tài liệu có thể được tạo từ nhiều nguồn. Mỗi nguồn cung cấp một loại thông tin:

| Nguồn | Thông tin có thể trích xuất |
|---|---|
| DSL source | Khai báo, comment, literal và cấu trúc |
| AST/CST | Cây cú pháp, vị trí nguồn và quan hệ node |
| Symbol index | Tên, kind, chữ ký, visibility và references |
| Type system | Kiểu, constraint, overload và subtype |
| Schema registry | Field, enum, default và validation rule |
| Runtime registry | Function tích hợp, capability và hành vi |
| Metadata | Owner, version, category, stability và lifecycle |
| Example files | Chương trình mẫu và kết quả mong đợi |
| Build configuration | Module, dependency và phiên bản |

Một nguồn sự thật nên được xác định cho từng loại thông tin. Ví dụ, chữ ký function nên lấy từ declaration hoặc symbol model, trong khi mô tả nghiệp vụ có thể lấy từ documentation comment. Nếu cùng một thông tin được sao chép vào nhiều file, cần quy định nguồn nào được ưu tiên khi có xung đột.

### 4.1. Source comments và documentation comments

Comment thông thường có thể chỉ dành cho người đọc source. Documentation comment là comment được gắn với declaration và được generator trích xuất.

Ví dụ:

~~~text
/**
 * Calculates the tax for an order.
 *
 * The result uses the currency of the order.
 *
 * @param order Order to calculate.
 * @return Calculated tax amount.
 */
function calculateTax(order: Order): Money {
    ...
}
~~~

Generator có thể gắn comment này với symbol calculateTax. Khi render API reference, nó tạo phần mô tả, tham số và kiểu trả về.

### 4.2. Metadata có cấu trúc

Một số thông tin khó biểu diễn trong văn xuôi có thể được ghi bằng annotation hoặc metadata:

~~~text
@category "Order Processing"
@since "2.1"
@stability "stable"
@owner "Commerce Platform"
function calculateTax(order: Order): Money;
~~~

Metadata giúp generator tạo bảng phân loại, nhãn phiên bản, trạng thái ổn định hoặc thông tin sở hữu. Cần định nghĩa schema cho annotation để tránh các giá trị tùy ý và không nhất quán.

### 4.3. Runtime registry

Nếu DSL cho phép gọi function tích hợp được đăng ký từ ứng dụng chủ, một phần API không nằm trong source DSL. Documentation generator có thể lấy chữ ký và mô tả từ function registry hoặc extension metadata.

Không nên chỉ liệt kê function trong registry mà không xác định function đó có được export cho người dùng DSL hay không. Một runtime có thể chứa helper nội bộ không phải public API.

## 5. Pipeline tạo tài liệu

Một documentation pipeline điển hình:

~~~mermaid
flowchart TD
    A["DSL source and metadata"] --> B["Lexer and parser"]
    B --> C["AST and symbol model"]
    D["Schema and runtime registry"] --> E["Documentation model"]
    C --> E
    F["Examples and project config"] --> E
    E --> G["Link and reference resolution"]
    G --> H["Templates / renderers"]
    H --> I["Markdown / HTML / JSON"]
    I --> J["Validation and build checks"]
~~~

Các bước chính:

1. **Thu thập đầu vào:** xác định source, module, schema, metadata và example.
2. **Phân tích:** parse DSL và tạo AST hoặc CST.
3. **Trích xuất symbol:** thu thập declaration, type, signature, visibility và source location.
4. **Bổ sung ngữ nghĩa:** resolve import, type, reference và runtime function.
5. **Tạo document model:** chuyển thông tin thành cấu trúc trung gian dành cho tài liệu.
6. **Resolve links:** tạo liên kết tới type, function, module và source location.
7. **Render:** dùng template để tạo Markdown, HTML hoặc dữ liệu có cấu trúc.
8. **Validate:** kiểm tra liên kết, ví dụ, metadata và output.
9. **Đóng gói artifact:** chuẩn bị tập file tài liệu cho bước sử dụng tiếp theo.

Tách document model khỏi renderer giúp một nguồn dữ liệu có thể được xuất ra nhiều định dạng mà không phải viết lại logic trích xuất.

## 6. Tạo document model

Document model là cấu trúc trung gian mô tả nội dung cần hiển thị. Nó có thể gồm:

- Document và section.
- Heading, paragraph và list.
- Code example.
- API item hoặc schema item.
- Table.
- Link và cross-reference.
- Warning, note và deprecation notice.
- Source location.
- Metadata cho navigation hoặc search.

Ví dụ model cho function:

~~~text
ApiDocument
  title: calculateTax
  kind: Function
  qualifiedName: sales.tax.calculateTax
  summary: Calculates tax for an order.
  parameters:
    - name: order
      type: Order
      description: Order to calculate.
  returns:
    type: Money
    description: Calculated tax amount.
  since: 2.1
  source:
    file: src/sales/tax.dsl
    line: 12
~~~

Renderer có thể chuyển model này thành bảng Markdown, trang HTML có anchor hoặc JSON dùng cho search index.

Document model nên chứa dữ liệu đã resolve ở mức cần thiết. Ví dụ, parameter type Order có thể mang symbol reference tới trang Order thay vì chỉ lưu chuỗi "Order". Điều này giúp renderer tạo cross-link chính xác.

## 7. Trích xuất API reference

API reference mô tả những thành phần mà người dùng DSL có thể gọi hoặc tham chiếu.

Với function, các thông tin thường gồm:

- Tên và qualified name.
- Chữ ký đầy đủ.
- Parameter và kiểu.
- Return type.
- Overload.
- Generic constraint nếu có.
- Visibility.
- Exception hoặc error có thể phát sinh.
- Side effect hoặc capability cần thiết.
- Mô tả, ví dụ và phiên bản xuất hiện.

Ví dụ:

~~~text
function requireManualReview(orderId: OrderId): ReviewRequest
~~~

Trang reference có thể hiển thị:

| Thành phần | Nội dung |
|---|---|
| Function | requireManualReview |
| Parameter | orderId: OrderId |
| Return | ReviewRequest |
| Capability | review:create |
| Side effect | Tạo yêu cầu xét duyệt |
| Stability | Stable |

Với overload, generator nên tạo một mục tổng quan và liệt kê từng signature. Không nên gộp các overload vào một chữ ký giả định vì điều đó có thể che giấu khác biệt về kiểu và hành vi.

## 8. Tạo tài liệu cho type và schema

Type reference mô tả record, class, enum, union, interface hoặc kiểu miền. Một trang type có thể chứa:

- Mô tả tổng quan.
- Field hoặc property.
- Kiểu của từng field.
- Optionality và default.
- Constraint hoặc validation rule.
- Quan hệ kế thừa hoặc composition.
- Ví dụ khởi tạo.
- Liên kết tới type liên quan.

Ví dụ:

~~~text
/**
 * Represents an order submitted by a customer.
 *
 * @invariant total is non-negative.
 */
type Order {
    /** Stable order identifier. */
    id: OrderId

    /** Total amount in the order currency. */
    total: Money

    /** Current processing state. */
    status: OrderStatus
}
~~~

Tài liệu sinh ra có thể tạo bảng:

| Field | Type | Mô tả |
|---|---|---|
| id | OrderId | Định danh ổn định của đơn hàng |
| total | Money | Tổng tiền theo currency của đơn |
| status | OrderStatus | Trạng thái xử lý hiện tại |

Nếu schema có constraint như total không âm, generator nên hiển thị constraint trong phần riêng. Không nên chỉ ghi kiểu Money nếu người dùng cần biết giới hạn giá trị.

## 9. Tạo rule catalog cho DSL nghiệp vụ

Với DSL dạng rule hoặc policy, tài liệu tự sinh có thể là catalog phục vụ cả developer lẫn người vận hành.

Một rule entry có thể gồm:

- Rule ID và tên hiển thị.
- Mô tả nghiệp vụ.
- Trigger hoặc điều kiện.
- Action.
- Input data.
- Dependency.
- Owner hoặc nhóm chịu trách nhiệm.
- Priority hoặc execution order.
- Trạng thái enabled/disabled.
- Version và ngày hiệu lực nếu có.

Ví dụ:

~~~text
@category "Fraud Prevention"
@owner "Risk Operations"
@since "3.0"
rule high-value-order {
    description: "Đưa đơn hàng có giá trị lớn vào quy trình kiểm tra."
    when order.total > money(10000000, VND)
    then requireManualReview(order.id)
}
~~~

Generator có thể tạo trang catalog:

| Thuộc tính | Giá trị |
|---|---|
| Rule | high-value-order |
| Category | Fraud Prevention |
| Owner | Risk Operations |
| Since | 3.0 |
| Condition | order.total lớn hơn 10.000.000 VND |
| Action | requireManualReview(order.id) |

Nếu condition được hiển thị dưới dạng câu tự nhiên, generator cần có bộ chuyển đổi có quy tắc. Không nên tự suy diễn diễn giải nghiệp vụ từ mọi biểu thức phức tạp nếu không thể bảo đảm đúng nghĩa. Trong trường hợp đó, dùng description do tác giả cung cấp và hiển thị source expression bên cạnh.

## 10. Documentation comments và tag conventions

Một quy ước comment thống nhất giúp generator tạo tài liệu có chất lượng.

Các tag có thể dùng:

| Tag | Ý nghĩa |
|---|---|
| @param | Mô tả tham số |
| @return | Mô tả giá trị trả về |
| @throws | Lỗi có thể phát sinh |
| @example | Ví dụ sử dụng |
| @see | Liên kết tới symbol liên quan |
| @since | Phiên bản xuất hiện |
| @deprecated | Trạng thái lỗi thời và hướng thay thế |
| @category | Nhóm tài liệu |
| @owner | Nhóm chịu trách nhiệm |
| @stability | Mức độ ổn định |
| @requires | Capability hoặc dependency cần có |

Đây là một convention minh họa; DSL có thể chọn tên tag khác. Điều quan trọng là tag phải được định nghĩa trong grammar hoặc metadata schema và được validate.

### 10.1. Kiểm tra tính đầy đủ

Generator có thể phát cảnh báo nếu public function thiếu mô tả, parameter không có document hoặc type không có ví dụ. Đây là kiểm tra tài liệu, không phải thay thế kiểm tra cú pháp hay kiểu.

Chính sách có thể khác nhau theo visibility:

- Public API yêu cầu mô tả và ví dụ.
- Internal helper chỉ cần mô tả ngắn.
- Experimental API cần nhãn cảnh báo.
- Deprecated API cần chỉ dẫn thay thế.

Không nên tự tạo mô tả giả như "This function does something" chỉ để lấp trường trống. Thiếu tài liệu nên được thể hiện rõ để tác giả bổ sung.

### 10.2. Markdown trong documentation comment

Cho phép Markdown trong comment giúp tác giả viết danh sách, link và code block. Tuy nhiên, cần giới hạn hoặc sanitize HTML nhúng nếu output được render trên website.

Parser nên giữ source span của comment và biết comment gắn với declaration nào. Một comment nằm giữa hai declaration không nên tự động gắn vào cả hai nếu ngôn ngữ không định nghĩa như vậy.

## 11. Sinh ví dụ và code sample

Ví dụ là phần quan trọng của tài liệu DSL. Generator có thể lấy example từ:

- Code block trong documentation comment.
- File example riêng.
- Test fixture đã được xác nhận.
- Snippet được trích xuất từ source.
- Mẫu được tạo từ schema hoặc function signature.

Ví dụ function:

~~~text
/**
 * Calculates tax for an order.
 *
 * @example
 * let tax = calculateTax(order);
 */
function calculateTax(order: Order): Money;
~~~

Một example có thể mang metadata:

~~~yaml
id: calculate-tax-basic
title: Calculate tax for an order
source: examples/tax/basic.dsl
languageVersion: 2
expected: valid
~~~

### 11.1. Kiểm tra ví dụ có thể chạy

Nếu example được quảng bá là runnable, pipeline có thể:

1. Parse example.
2. Resolve dependency.
3. Type-check hoặc validate.
4. Chạy trong sandbox nếu cần.
5. So sánh output với kết quả mong đợi.

Không phải code block nào cũng là chương trình hoàn chỉnh. Có thể phân biệt snippet minh họa, snippet cần context và example chạy độc lập bằng metadata rõ ràng.

### 11.2. Không làm lộ dữ liệu thật

Example không nên lấy dữ liệu production có thông tin cá nhân hoặc bí mật. Dùng fixture tổng hợp, dữ liệu đã ẩn danh hoặc ví dụ giả lập. Generator không nên tự đưa giá trị từ database thật vào tài liệu.

## 12. Cross-reference và liên kết giữa các trang

Tài liệu API hữu ích khi người đọc có thể đi từ một symbol tới các symbol liên quan.

Ví dụ:

- Function calculateTax liên kết tới type Order.
- Field total liên kết tới type Money.
- Rule high-value-order liên kết tới function requireManualReview.
- Module sales.tax liên kết tới các declaration được export.

Một link model có thể chứa:

~~~text
Link
  targetSymbolId: symbol-order-01
  targetDocument: types/Order.md
  anchor: field-total
~~~

### 12.1. Resolve link

Link resolver cần:

1. Tìm symbol đích theo identity.
2. Xác định trang tài liệu được tạo cho symbol.
3. Tạo đường dẫn tương đối hoặc URL theo output format.
4. Tạo anchor ổn định.
5. Xác định cách xử lý symbol không có trang riêng.

Không nên tạo link chỉ bằng cách nối tên symbol vào file path nếu tên có ký tự đặc biệt hoặc nhiều symbol cùng tên.

### 12.2. Anchor ổn định

Anchor có thể dựa trên qualified name và symbol kind. Nếu chỉ dùng tên ngắn, hai overload hoặc hai module cùng tên có thể tạo anchor trùng nhau.

Khi symbol đổi tên, anchor có thể thay đổi. Nếu tài liệu được liên kết từ bên ngoài, có thể duy trì redirect hoặc alias anchor trong một khoảng thời gian.

### 12.3. Liên kết tới source

Trang tài liệu có thể liên kết tới file nguồn trong repository hoặc editor. Cần tạo URL theo repository và revision cụ thể nếu muốn link luôn trỏ đúng phiên bản. Link tới nhánh thay đổi liên tục có thể dẫn tới source khác với tài liệu đã sinh.

## 13. Sinh sơ đồ và biểu đồ quan hệ

Từ AST, symbol index hoặc dependency graph, generator có thể tạo sơ đồ:

- Module dependency.
- Type inheritance hoặc composition.
- Function call graph.
- Rule dependency.
- Data flow giữa các bước workflow.
- Quan hệ giữa schema và field.

Ví dụ dependency:

~~~mermaid
flowchart TD
    A["approval rule"] --> B["calculateTax"]
    A --> C["requireManualReview"]
    B --> D["Order"]
    B --> E["Money"]
~~~

Sơ đồ giúp người đọc hiểu cấu trúc nhanh, nhưng cần kiểm soát kích thước. Với graph lớn, nên tạo nhiều sơ đồ theo module hoặc cung cấp trang tương tác có khả năng lọc.

Graph generator cần tránh suy diễn quan hệ chỉ từ tên giống nhau. Cạnh trong sơ đồ nên dựa trên reference đã resolve hoặc dependency được xác định từ build model.

## 14. Output formats và template

Một document model có thể được render ra nhiều định dạng:

| Output | Mục đích |
|---|---|
| Markdown | Repository, code review và tài liệu dạng text |
| HTML | Website tài liệu có navigation và search |
| JSON | Search index, tooling và integration |
| XML | Hệ thống tài liệu hoặc pipeline yêu cầu XML |
| PDF | Tài liệu phát hành hoặc lưu trữ cố định |
| Man page | Tài liệu command-line |

Renderer có thể dùng template cho page header, API section, type table, example block và footer metadata.

Ví dụ cấu trúc Markdown:

~~~text
# calculateTax

Calculates tax for an order.

## Signature

    calculateTax(order: Order): Money

## Parameters

| Name | Type | Description |
|---|---|---|
| order | Order | Order to calculate |

## Returns

Money representing the calculated tax.
~~~

Template nên tách khỏi extraction logic. Nếu thay đổi giao diện website, không cần thay parser hoặc symbol model. Ngược lại, nếu grammar thay đổi, renderer không cần biết chi tiết cú pháp nếu document model vẫn giữ hợp đồng.

## 15. Navigation, search và mục lục

Với tài liệu lớn, generator nên tạo navigation:

- Trang tổng quan module.
- Danh sách type và function.
- Rule catalog theo category.
- Trang từng symbol.
- Index theo chữ cái hoặc prefix.
- Search index chứa tên, mô tả và metadata.

Search index có thể lưu:

~~~json
{
  "id": "sales.tax.calculateTax",
  "title": "calculateTax",
  "kind": "Function",
  "summary": "Calculates tax for an order.",
  "url": "api/sales/tax/calculateTax.html"
}
~~~

Search nên phân biệt symbol kind và module để kết quả có ngữ cảnh. Khi cùng tên xuất hiện ở nhiều nơi, người dùng cần biết qualified name hoặc container.

## 16. Source location và truy nguyên

Tài liệu tự sinh có thể ghi vị trí khai báo:

~~~text
Defined in: src/sales/tax.dsl, line 12
~~~

Source location hữu ích cho:

- Mở source từ trang reference.
- Điều tra lỗi hoặc hành vi rule.
- Review thay đổi.
- Truy nguyên tài liệu về revision cụ thể.

Nếu tài liệu được tạo từ source đã format hoặc từ AST, cần giữ source span qua pipeline. Nếu chỉ lưu tên symbol, có thể không xác định được vị trí chính xác khi có overload hoặc symbol trùng tên.

Khi sinh URL source, nên gắn commit hoặc revision ID. Với build local, có thể dùng đường dẫn tương đối thay vì đường dẫn tuyệt đối của máy.

## 17. Versioning tài liệu

Tài liệu nên chỉ rõ phiên bản DSL hoặc API mà nó mô tả. Một trang reference có thể hiển thị:

~~~text
Language version: 2
Runtime API: 3.1
Generated from revision: a1b2c3d
~~~

Các version cần được phân biệt:

- Language version: cú pháp và ngữ nghĩa DSL.
- Compiler version: phiên bản công cụ tạo artifact.
- Runtime API version: function và type có sẵn khi chạy.
- Schema version: cấu trúc dữ liệu được mô tả.
- Documentation template version: layout và rendering.

Nếu chỉ ghi compiler version, người đọc có thể không biết tài liệu áp dụng cho runtime API nào.

### 17.1. Tài liệu theo nhiều phiên bản

Khi hỗ trợ nhiều language version, có thể tạo một bộ tài liệu cho từng version hoặc một trang có bộ lọc version. Không nên trộn API của các version mà không đánh dấu, vì người dùng có thể sao chép ví dụ không chạy được trong project hiện tại.

### 17.2. Deprecated và removed API

Generator có thể hiển thị:

- Deprecated since.
- Replacement.
- Planned removal version nếu đã công bố.
- Migration note.

API đã bị loại bỏ không nên biến mất khỏi mọi tài liệu lịch sử nếu người dùng cần nâng cấp project cũ. Có thể giữ archive theo version.

## 18. Deterministic documentation generation

Một documentation generator tốt nên tạo output ổn định khi source, metadata, configuration và tool version giống nhau.

Tính xác định giúp:

- Git diff chỉ thể hiện thay đổi có ý nghĩa.
- Build tài liệu có thể tái lập.
- Cache hoạt động đáng tin cậy.
- Reviewer nhận ra API thay đổi.
- Không tạo thay đổi ngẫu nhiên mỗi lần build.

Các yếu tố có thể làm output không xác định:

- Duyệt map hoặc set không có thứ tự.
- Timestamp hiện tại.
- Đường dẫn tuyệt đối của máy build.
- Thứ tự file phụ thuộc filesystem.
- Locale hoặc timezone của môi trường.
- Phiên bản template hoặc formatter không được khóa.
- ID ngẫu nhiên trong anchor.

Nên:

1. Sắp xếp module và symbol theo quy tắc ổn định.
2. Dùng qualified name hoặc stable ID cho anchor.
3. Không chèn thời gian build trừ khi thực sự cần.
4. Chuẩn hóa encoding và line ending.
5. Khóa phiên bản renderer và template.
6. Tránh đưa đường dẫn máy cục bộ vào output.

## 19. Incremental generation và cache

Với workspace lớn, tạo lại toàn bộ tài liệu sau mỗi thay đổi có thể tốn thời gian. Incremental generation chỉ tạo lại những trang bị ảnh hưởng.

Ví dụ:

- Thay đổi comment của function calculateTax: cập nhật trang function và có thể trang module index.
- Thay đổi public type Order: cập nhật trang Order, các trang tham chiếu chữ ký và search index liên quan.
- Thay đổi template chung: có thể phải render lại mọi trang.
- Thay đổi dependency graph: cập nhật module overview và sơ đồ liên quan.

Cache key có thể dựa trên:

- Hash nội dung declaration.
- Hash documentation comment.
- Symbol model version.
- Dependency hoặc link target version.
- Template version.
- Renderer version.
- Output format và configuration.

Không nên chỉ cache theo tên file. Một file có thể giữ nguyên tên nhưng thay đổi declaration hoặc comment. Ngược lại, một thay đổi không liên quan trong file không nhất thiết yêu cầu render lại mọi trang nếu document model hỗ trợ tách phần.

### 19.1. Dependency của tài liệu

Trang function có thể phụ thuộc trang type được dùng trong signature. Nếu type đổi tên hoặc chuyển module, link và nội dung reference có thể phải cập nhật dù comment của function không đổi.

Documentation dependency graph giúp xác định trang nào cần render lại khi symbol hoặc metadata thay đổi.

## 20. Validation tài liệu được sinh

Tài liệu được tạo tự động vẫn cần kiểm tra cấu trúc và liên kết. Các kiểm tra có thể gồm:

- Public symbol có đủ mô tả theo policy.
- Tag như param và return khớp chữ ký.
- Link nội bộ trỏ tới trang hoặc anchor tồn tại.
- Không có anchor trùng.
- Example được parse hoặc chạy nếu được đánh dấu runnable.
- Source link trỏ tới file và revision hợp lệ.
- Metadata version có mặt.
- Output không chứa secret hoặc thông tin không được công bố.
- Markdown/HTML hợp lệ theo renderer.

### 20.1. Broken link

Nếu function A liên kết tới type B nhưng B không có trang được tạo, link resolver cần có chính sách:

- Tạo trang B nếu symbol thuộc phạm vi public.
- Liên kết tới trang module chứa B.
- Hiển thị tên không link.
- Phát diagnostic tài liệu để tác giả xử lý.

Không nên âm thầm tạo URL giả rồi để người đọc gặp trang 404.

### 20.2. Documentation coverage

Có thể đo tỷ lệ public API có mô tả:

~~~text
documented public symbols / total public symbols
~~~

Coverage chỉ là chỉ số hiện diện, không đánh giá chất lượng nội dung. Một mô tả có thể tồn tại nhưng không hữu ích. Nên dùng coverage như tín hiệu hỗ trợ, không phải thước đo duy nhất.

### 20.3. Example validation

Nếu example được đánh dấu runnable, có thể chạy trong môi trường giới hạn và kiểm tra output. Nếu example chỉ minh họa một fragment, validator cần biết context hoặc fixture cần thiết.

## 21. Bảo mật và kiểm soát nội dung

Documentation generator có thể xử lý comment, annotation và metadata do nhiều người viết. Nội dung đó không nên mặc nhiên được tin cậy khi render ra HTML hoặc website.

Các rủi ro:

- HTML hoặc script độc hại trong comment.
- Link tới scheme nguy hiểm.
- Secret vô tình được ghi trong example hoặc metadata.
- Đường dẫn tuyệt đối làm lộ cấu trúc máy.
- Source snippet chứa dữ liệu khách hàng.
- Nội dung markdown gây lỗi hoặc làm hỏng navigation.

Biện pháp:

1. Escape hoặc sanitize HTML theo policy.
2. Chỉ cho phép URL scheme được hỗ trợ.
3. Kiểm tra example và metadata trước khi render.
4. Không đưa secret hoặc dữ liệu production vào tài liệu.
5. Chuẩn hóa source path thành đường dẫn tương đối.
6. Kiểm soát nội dung từ plugin hoặc extension.
7. Giữ quyền truy cập phù hợp với tài liệu nội bộ và public.

Nếu documentation được tạo cho nhiều audience, có thể phân loại public, internal và restricted. Không nên xuất mọi symbol trong runtime registry ra tài liệu public.

## 22. Tích hợp vào build và CI

Documentation generation thường được tích hợp vào build pipeline như một bước có thể tái lập:

1. Resolve project configuration và dependency.
2. Parse DSL source.
3. Chạy semantic analysis cần thiết.
4. Tạo document model.
5. Render các định dạng đã chọn.
6. Validate links, tags, examples và output.
7. So sánh diff hoặc kiểm tra artifact có cập nhật.
8. Lưu output như build artifact cho bước tiếp theo.

Có thể có hai chế độ:

- **Generate mode:** ghi tài liệu mới hoặc cập nhật output.
- **Check mode:** tạo output trong vùng tạm và báo lỗi nếu khác tài liệu đã commit.

Check mode hữu ích để phát hiện tài liệu cũ so với source. Pipeline này chỉ tạo và xác nhận artifact; việc phân phối hoặc công bố tài liệu là một hoạt động riêng có thể do hệ thống phát hành quản lý.

### 22.1. Khi nào tài liệu nên được commit?

Có dự án commit Markdown/HTML được sinh để review cùng source. Dự án khác chỉ lưu artifact trong build output. Quyết định phụ thuộc vào:

- Người dùng có cần đọc tài liệu ngay trong repository không?
- Diff tài liệu có hữu ích trong code review không?
- Output có ổn định và không quá lớn không?
- Có thể tái tạo từ source và tool version đã khóa không?
- Có yêu cầu lưu trữ theo release không?

Nếu commit output, cần tránh sửa trực tiếp file sinh. Hãy sửa source comment, metadata, example hoặc template rồi tạo lại.

## 23. Kiểm thử documentation generator

Generator cần được kiểm thử cả việc trích xuất thông tin lẫn kết quả render.

### 23.1. Extraction test

Tạo fixture DSL có function, type, enum, rule, overload và documentation comment. Xác nhận document model có đúng name, kind, signature, metadata và source location.

### 23.2. Golden-file test

Sinh tài liệu và so sánh với file kết quả mong đợi. Khi template thay đổi có chủ đích, diff cho reviewer thấy thay đổi layout.

### 23.3. Link validation test

Tạo symbol reference giữa nhiều module và xác nhận link, anchor, relative path được tạo đúng. Thêm trường hợp symbol không được export hoặc trang đích không có.

### 23.4. Example test

Parse hoặc chạy example có metadata runnable. Xác nhận output và lỗi được trình bày theo chính sách.

### 23.5. Determinism test

Chạy generator nhiều lần với cùng input và cấu hình. Output phải giống nhau theo quy tắc canonical đã chọn.

### 23.6. Incremental test

Thay đổi một declaration hoặc comment và xác nhận đúng các trang phụ thuộc được tạo lại. Trang không liên quan không nên thay đổi nếu cache và dependency model cho phép.

### 23.7. Security test

Thử comment có HTML, link scheme không được phép, metadata chứa đường dẫn bất thường và example có dữ liệu nhạy cảm giả lập. Xác nhận renderer escape hoặc từ chối theo policy.

## 24. Công cụ và hệ sinh thái

Có nhiều công cụ có thể hỗ trợ các phần của documentation generation:

| Công cụ hoặc nhóm công cụ | Thường dùng cho |
|---|---|
| Javadoc | Tài liệu API Java từ declaration và doc comment |
| Dokka | Tài liệu Kotlin và API reference |
| Sphinx | Tài liệu dự án, extension và API từ nhiều nguồn |
| Doxygen | Tài liệu API cho nhiều ngôn ngữ |
| TypeDoc | Tài liệu API TypeScript |
| rustdoc | Tài liệu crate và API Rust |
| MkDocs | Website tài liệu từ Markdown |
| Antora | Tài liệu kỹ thuật nhiều component/version |
| Custom AST generator | Reference chuyên biệt cho DSL |

Một số công cụ tập trung trích xuất API; một số tập trung render website. Có thể kết hợp parser DSL riêng với một hệ thống site generator. Không nhất thiết phải tự viết cả parser, template engine và website navigation.

Khi chọn công cụ, cân nhắc khả năng hiểu grammar DSL, hỗ trợ versioning, cross-reference, theme, plugin, license, tích hợp CI và khả năng tạo output ổn định.

## 25. Những lỗi thiết kế thường gặp

### Viết lại mọi thông tin thủ công

Tên và chữ ký trong tài liệu dễ lệch khỏi source. Trích xuất cấu trúc từ AST hoặc symbol model, chỉ giữ phần diễn giải do con người viết.

### Sinh tài liệu chỉ từ regex

Regex khó hiểu overload, scope, import và nested syntax. Dùng parser hoặc symbol index cho thông tin cấu trúc.

### Không có document model trung gian

Extraction logic bị trộn với template. Tạo document model để có thể render nhiều định dạng và kiểm thử độc lập.

### Không resolve cross-reference

Trang có nhiều link hỏng hoặc chỉ hiển thị tên không có ngữ cảnh. Dùng symbol identity và link resolver.

### Sinh mô tả nghiệp vụ không có căn cứ

Generator suy diễn ý nghĩa từ tên rule hoặc biểu thức và tạo tài liệu sai. Dùng description do tác giả cung cấp; chỉ tự diễn giải các cấu trúc có quy tắc rõ.

### Không kiểm tra example

Ví dụ cũ hoặc sai cú pháp làm người dùng mất thời gian. Gắn metadata runnable và kiểm tra trong môi trường phù hợp.

### Output không xác định

Thứ tự symbol, timestamp hoặc path máy làm diff thay đổi liên tục. Chuẩn hóa dữ liệu và khóa tool version.

### Không version hóa tài liệu

Người đọc dùng API của version khác với project. Gắn language, runtime và schema version vào trang.

### Xuất nhầm thông tin nội bộ

Symbol private hoặc runtime helper bị công bố. Áp dụng visibility và audience policy trước khi render.

### Sửa trực tiếp output được sinh

Thay đổi bị ghi đè ở lần build sau. Sửa source comment, metadata, example hoặc template.

## 26. Quy trình xây dựng tài liệu tự sinh cho DSL

Khi triển khai documentation generator, có thể đi theo trình tự:

1. **Xác định audience và loại tài liệu.** Chọn API reference, schema, rule catalog, language guide hoặc nhiều loại.
2. **Xác định nguồn sự thật.** Quy định thông tin nào đến từ source, AST, symbol index, registry hay metadata.
3. **Thiết kế documentation comment.** Chuẩn hóa mô tả, parameter, return, example và lifecycle tags.
4. **Tạo document model.** Tách extraction khỏi rendering.
5. **Resolve symbol và liên kết.** Dùng identity ổn định, qualified name và source mapping.
6. **Xây template và renderer.** Hỗ trợ Markdown, HTML hoặc output cần thiết.
7. **Sinh navigation và search index.** Nhóm theo module, category, kind và version.
8. **Kiểm tra nội dung máy đọc được.** Validate tags, links, anchors, examples và metadata.
9. **Bảo đảm output xác định.** Khóa tool version, sắp xếp ổn định và chuẩn hóa file.
10. **Tích hợp incremental build.** Dựa trên dependency graph để tạo lại phần bị ảnh hưởng.
11. **Áp dụng security policy.** Sanitize nội dung và lọc thông tin theo audience.
12. **Kiểm thử trong CI.** Golden files, link checks, runnable examples và determinism.

Nên bắt đầu với API reference từ symbol model và documentation comments. Khi nhu cầu tăng, có thể thêm rule catalog, schema pages, graph và search mà không phải thay đổi nguồn extraction cốt lõi.

## 27. Ví dụ end-to-end: sinh API reference từ DSL

Giả sử source:

~~~text
namespace sales.tax;

/**
 * Calculates tax for an order.
 *
 * @param order Order whose tax is calculated.
 * @return Tax amount in the order currency.
 * @example
 * let tax = calculateTax(order);
 */
function calculateTax(order: Order): Money;
~~~

Pipeline có thể:

1. Parser tạo FunctionDeclaration.
2. Symbol extractor tạo symbol sales.tax.calculateTax.
3. Type resolver xác nhận Order và Money.
4. Documentation parser gắn comment và tags với function.
5. Example collector trích code sample.
6. Link resolver liên kết Order và Money tới trang type.
7. Document model lưu signature, description, parameter, return, example và source span.
8. Markdown renderer tạo trang API.
9. Validator kiểm tra example và link.

Trang được tạo:

~~~markdown
# calculateTax

Calculates tax for an order.

**Qualified name:** sales.tax.calculateTax

## Signature

    calculateTax(order: Order): Money

## Parameters

| Name | Type | Description |
|---|---|---|
| order | Order | Order whose tax is calculated |

## Returns

Tax amount in the order currency.

## Example

    let tax = calculateTax(order);

**Source:** src/sales/tax.dsl
~~~

Khi chữ ký hoặc comment thay đổi, generator tạo lại trang. Khi type Order đổi tên, link resolver cập nhật trang function và các trang phụ thuộc. Nhờ document model và dependency graph, việc cập nhật có thể được thực hiện mà không phải viết lại logic template.

## 28. Kết luận

Tài liệu tự sinh chuyển thông tin có cấu trúc từ DSL source, AST, symbol index, schema, runtime registry và metadata thành tài liệu có thể đọc, tìm kiếm và truy nguyên. Nó đặc biệt hữu ích cho API reference, schema reference, rule catalog, module documentation và example gallery.

Một kiến trúc bền vững tách quá trình trích xuất khỏi document model và renderer; dùng symbol identity để tạo cross-reference; giữ source location; quản lý version; và tạo output xác định. Documentation comments và metadata có cấu trúc cung cấp phần diễn giải do con người kiểm soát, trong khi parser và symbol model cung cấp thông tin kỹ thuật chính xác.

Tài liệu tự sinh vẫn cần validation: kiểm tra tag, link, anchor, example, version và nội dung nhạy cảm. Khi được tích hợp vào build và CI với cache cùng incremental generation, tài liệu có thể theo sát thay đổi của DSL và trở thành một phần đáng tin cậy của quy trình phát triển.
