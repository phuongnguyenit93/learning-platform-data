# Dạng biểu diễn chuẩn

Một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL) thường được viết bằng cú pháp dễ đọc cho người làm nghiệp vụ, chẳng hạn câu lệnh mô tả quy tắc, workflow, mô hình dữ liệu hoặc cấu hình. Nhưng để lưu trữ lâu dài, trao đổi giữa công cụ, so sánh phiên bản, ký số hoặc xử lý bằng nhiều nền tảng, hệ thống cần một cách biểu diễn có cấu trúc và quy tắc thống nhất. Cách biểu diễn đó được gọi là **dạng biểu diễn chuẩn** (*canonical representation*).

Dạng biểu diễn chuẩn là một biểu diễn đã được xác định quy tắc về cấu trúc, kiểu dữ liệu, định danh, tham chiếu, thứ tự và cách mã hóa để các hệ thống có thể hiểu cùng một nội dung theo cùng một cách. Nó có thể là một định dạng văn bản như JSON, XML hoặc YAML; một định dạng nhị phân như CBOR hoặc Protocol Buffers; một AST/semantic model có schema; hoặc một cú pháp DSL đã được chuẩn hóa. Điểm cốt lõi không nằm ở phần mở rộng tệp, mà ở hợp đồng biểu diễn được công bố và có thể kiểm tra.

Ví dụ, hai cách viết DSL sau có thể mang cùng ý nghĩa:

~~~text
policy OrderApproval{when order.total>=1000 then approveOrder;}
~~~

~~~text
policy OrderApproval {
    when order.total >= 1000 then approveOrder;
}
~~~

Nếu khoảng trắng và xuống dòng không ảnh hưởng ngữ nghĩa, hai đoạn có thể được chuyển thành cùng một biểu diễn chuẩn. Khi đó, công cụ có thể so sánh, hash, ký hoặc lưu trữ nội dung mà không bị ảnh hưởng bởi cách trình bày bề mặt.

Một dạng biểu diễn chuẩn tốt giúp nhiều công cụ cùng trao đổi một mô hình, giảm sự phụ thuộc vào parser riêng, hỗ trợ kiểm tra schema, giữ được định danh và tham chiếu, đồng thời tạo cơ sở cho versioning và tương thích ngược. Tuy nhiên, chuẩn hóa phải bảo toàn ngữ nghĩa DSL. Không được sắp xếp lại biểu thức, loại bỏ thông tin hoặc chuyển đổi kiểu chỉ vì cách viết mới trông gọn hơn.

## 1. Dạng biểu diễn chuẩn là gì?

**Canonical representation** là biểu diễn có quy tắc xác định để một nội dung logic có một cách biểu diễn chuẩn trong phạm vi các lựa chọn được đặc tả. Tùy hệ thống, chuẩn có thể áp dụng cho cú pháp nguồn, mô hình ngữ nghĩa, cấu trúc dữ liệu trao đổi hoặc artifact đã biên dịch.

Một dạng biểu diễn chuẩn thường xác định:

- Cấu trúc tài liệu và schema.
- Tên trường, kiểu dữ liệu và trường bắt buộc.
- Cách biểu diễn giá trị số, chuỗi, ngày giờ, enum và giá trị rỗng.
- Quy tắc định danh phần tử và tham chiếu giữa phần tử.
- Thứ tự của collection và quy tắc sắp xếp các trường không có thứ tự ngữ nghĩa.
- Cách biểu diễn giá trị mặc định và trường bị lược bỏ.
- Encoding, newline và quy tắc Unicode.
- Phiên bản ngôn ngữ, schema và extension.
- Cách xử lý dữ liệu không biết, dữ liệu mở rộng và cấu trúc tương lai.
- Cách xác thực, chuẩn hóa và chuyển đổi sang mô hình nội bộ.

### Chuẩn hóa khác với định dạng hóa

Định dạng hóa (*formatting*) chủ yếu thay đổi cách hiển thị: thụt lề, khoảng trắng, xuống dòng, dấu nháy hoặc cách xuống dòng bảng. Chuẩn hóa (*canonicalization*) xác định một biểu diễn duy nhất hoặc một quy tắc biểu diễn ổn định cho cùng nội dung logic.

Ví dụ, formatter có thể chọn hai hay bốn dấu cách cho mỗi cấp thụt lề. Canonical serializer phải có một quy tắc xác định, chẳng hạn luôn dùng UTF-8, newline LF và thứ tự field được định nghĩa. Formatter có thể giữ comment và style cá nhân; canonical model có thể không chứa trivia nếu mục tiêu chỉ là trao đổi ngữ nghĩa.

### Chuẩn hóa khác với serialization

Serialization chuyển một cấu trúc trong bộ nhớ thành chuỗi byte hoặc văn bản để lưu trữ/truyền đi. Canonicalization xác định cách biểu diễn ổn định. Một serializer thông thường có thể ghi cùng object thành JSON với thứ tự key khác nhau ở mỗi lần chạy; canonical serializer phải áp dụng quy tắc để kết quả ổn định theo đặc tả.

### Chuẩn hóa khác với compilation

Compilation chuyển chương trình sang biểu diễn phục vụ thực thi như IR hoặc bytecode. Canonical representation phục vụ lưu trữ, trao đổi, so sánh hoặc liên tác. Hai mục tiêu có thể dùng chung một semantic model, nhưng artifact thực thi thường phụ thuộc phiên bản compiler, target và môi trường hơn dạng trao đổi.

## 2. Vì sao DSL cần dạng biểu diễn chuẩn?

### Trao đổi giữa công cụ

Một DSL có thể có editor, compiler, validator, runtime, hệ thống quản trị và công cụ sinh tài liệu do các nhóm khác nhau phát triển. Nếu mỗi công cụ tự diễn giải một định dạng riêng, việc trao đổi dễ sai khác. Một schema chuẩn giúp các thành phần hiểu cùng một cấu trúc.

### Lưu trữ lâu dài

Tài liệu DSL có thể tồn tại lâu hơn phiên bản editor hoặc compiler đã tạo ra nó. Một định dạng ổn định cùng quy tắc versioning giúp hệ thống đọc lại dữ liệu sau khi nâng cấp.

### So sánh và quản lý phiên bản

Hai tài liệu có thể khác khoảng trắng hoặc thứ tự field nhưng cùng ngữ nghĩa. Canonical representation giúp giảm nhiễu khi diff, review hoặc tạo fingerprint.

### Hash và chữ ký số

Nếu cùng nội dung logic luôn được mã hóa thành cùng byte sequence theo một quy tắc chuẩn, hệ thống có thể tính hash ổn định, xác minh integrity và ký số. Nếu serialization không xác định, cùng một mô hình có thể tạo hash khác nhau chỉ vì thứ tự key hoặc cách viết số.

### Tích hợp đa nền tảng

Tool viết bằng Java có thể trao đổi mô hình với tool viết bằng Python, Go hoặc JavaScript. Schema và encoding chuẩn giúp tránh phụ thuộc vào class serialization riêng của một runtime.

### Kiểm thử và tái lập

Canonical output có thể được dùng làm fixture, golden file hoặc đầu vào so sánh. Nó giúp phát hiện thay đổi ngữ nghĩa ngoài ý muốn khi parser, compiler hoặc serializer được nâng cấp.

## 3. Các tầng biểu diễn của một DSL

Một hệ thống DSL có thể có nhiều biểu diễn khác nhau, mỗi biểu diễn phục vụ một mục tiêu.

| Tầng | Biểu diễn | Mục tiêu |
|---|---|---|
| Source text | Văn bản DSL người dùng viết | Dễ đọc, chỉnh sửa và review. |
| Concrete syntax tree (CST) | Cây giữ cả token và trivia | Round-trip gần nguyên văn, formatter và editor. |
| Abstract syntax tree (AST) | Cây cú pháp đã loại bỏ chi tiết không cần thiết | Phân tích và biến đổi cú pháp. |
| Semantic model | Mô hình đã resolve tên, kiểu và quan hệ | Kiểm tra ngữ nghĩa, trao đổi mô hình logic. |
| Canonical interchange document | JSON/XML/binary theo schema chuẩn | Lưu trữ và trao đổi giữa hệ thống. |
| Intermediate representation (IR) | Biểu diễn trung gian đã hạ cấp | Tối ưu và thực thi. |
| Executable artifact | Bytecode hoặc mã đích | Chạy trên runtime cụ thể. |

Không nên mặc định AST là dạng trao đổi chuẩn. AST thường phụ thuộc parser và có thể chứa node nội bộ, source span hoặc chi tiết triển khai không ổn định. Nếu nhiều công cụ cần trao đổi mô hình, nên định nghĩa semantic/interchange model độc lập với cấu trúc class của compiler.

### Luồng chuyển đổi

~~~mermaid
flowchart TD
    A[DSL source] --> B[Parser]
    B --> C[CST / AST]
    C --> D[Semantic analysis]
    D --> E[Canonical model]
    E --> F[Canonical serializer]
    F --> G[Stored / exchanged document]
    G --> H[Canonical parser and validator]
    H --> I[Canonical model]
    I --> J[Target tool / compiler / runtime]
~~~

Canonical model nên biểu diễn các khái niệm công khai của DSL, không để consumer phụ thuộc vào internal node class hoặc cấu trúc bộ nhớ của một compiler cụ thể.

## 4. Dạng biểu diễn chuẩn và semantic model

Một semantic model biểu diễn ý nghĩa của chương trình sau khi tên và quan hệ đã được xác định. Đây thường là nền tảng phù hợp để trao đổi giữa các công cụ vì nó tránh việc mỗi consumer phải tự phân tích lại cú pháp nguồn.

Ví dụ DSL:

~~~text
workflow OrderReview(order: Order) {
    if order.total >= 1000 {
        call ManagerApproval(order);
    }
}
~~~

Semantic model có thể biểu diễn:

~~~text
Workflow
  id: wf-order-review
  name: OrderReview
  parameters:
    - name: order
      typeRef: type-order
  body:
    - If
        condition: GreaterOrEqual
          left: PropertyAccess
            receiver: VariableRef(parameter-order)
            propertyRef: property-order-total
          right: DecimalLiteral(1000)
        then:
          - ActionCall(actionRef: action-manager-approval)
~~~

Các tham chiếu được lưu bằng ID hoặc reference object thay vì chỉ giữ tên văn bản. Nhờ đó, hai khai báo cùng tên trong các namespace khác nhau vẫn có thể được phân biệt.

### Semantic model có cần source location không?

Tùy mục tiêu. Một mô hình dùng cho editor và diagnostic cần source span hoặc source map. Một mô hình dùng làm interchange lâu dài có thể tách provenance ra metadata riêng để thay đổi format hoặc di chuyển tài liệu không làm thay đổi nội dung ngữ nghĩa.

### Semantic model có cần giữ comment không?

Comment thường không ảnh hưởng ngữ nghĩa, nhưng có thể chứa tài liệu, directive hoặc metadata do người dùng viết. Nếu cần round-trip hoặc trao đổi tài liệu có chú thích, hãy lưu comment trong một lớp annotation/documentation riêng. Không nên âm thầm loại bỏ thông tin mà consumer được kỳ vọng bảo toàn.

## 5. Chọn định dạng trao đổi

Một dạng biểu diễn chuẩn có thể được mã hóa bằng nhiều định dạng. Chọn định dạng dựa trên người dùng, kích thước dữ liệu, khả năng kiểm tra, yêu cầu streaming, versioning và hệ sinh thái công cụ.

| Định dạng | Ưu điểm | Hạn chế | Trường hợp phù hợp |
|---|---|---|---|
| JSON | Phổ biến, dễ hỗ trợ đa ngôn ngữ, cấu trúc rõ. | Không có comment chuẩn; kiểu số và thứ tự cần quy định thêm. | API, document interchange, semantic model. |
| YAML | Dễ đọc và viết tay, hỗ trợ comment và cấu trúc lồng. | Có nhiều quy tắc scalar/typing dễ gây khác biệt giữa parser. | Cấu hình và tài liệu cần chỉnh sửa thủ công. |
| XML | Schema, namespace, attribute và hệ công cụ trưởng thành. | Verbose, xử lý namespace và canonicalization cần hiểu kỹ. | Tích hợp hệ thống doanh nghiệp, schema-rich documents. |
| CBOR | Binary gọn, hỗ trợ kiểu dữ liệu phong phú, phù hợp truyền tải. | Khó đọc trực tiếp; cần profile canonical rõ. | API binary, thiết bị hoặc payload cần gọn. |
| Protocol Buffers | Schema rõ, code generation và evolution có quy tắc. | Phụ thuộc schema/compiler; field number và presence cần quản lý. | Service-to-service và message có contract. |
| MessagePack | Binary gọn, map/array thuận tiện. | Schema và canonical profile cần được quy định riêng. | Payload binary linh hoạt. |
| DSL canonical text | Người dùng đọc được, gần cú pháp gốc. | Parser/formatter phải có quy tắc ổn định; dễ trộn style và semantics. | Review, lưu source chuẩn và trao đổi với người viết DSL. |

Không có định dạng nào tự động trở thành canonical chỉ vì phổ biến. Ví dụ, JSON cho phép nhiều cách biểu diễn số và không buộc thứ tự key; YAML có thể diễn giải một số scalar khác nhau tùy schema; XML có namespace và các dạng biểu diễn tương đương. Canonical profile phải thu hẹp các lựa chọn này.

### JSON

JSON phù hợp với mô hình cây, API và document interchange. Một schema có thể định nghĩa object, array, string, number, boolean và null. Cần quy định trường bắt buộc, field không biết, cách biểu diễn decimal chính xác, reference và version.

### YAML

YAML thường tiện cho cấu hình viết tay. Tuy nhiên, nếu cần hash hoặc chữ ký, cần một bước parse sang data model chuẩn rồi serialize theo một encoding canonical. Không nên ký trực tiếp văn bản YAML tùy ý nếu không có canonicalization profile được xác định.

### XML

XML hỗ trợ namespace và schema validation. Khi cần chữ ký hoặc hash, có thể dùng một chuẩn XML canonicalization phù hợp với profile XML đang sử dụng. Cần xác định namespace, attribute, whitespace có ý nghĩa và cách xử lý entity.

### Định dạng nhị phân

CBOR, Protocol Buffers hoặc định dạng tương tự có thể giảm kích thước và chi phí parse. Nhưng người tích hợp cần schema, công cụ debug và quy tắc tương thích rõ. Định dạng nhị phân không tự động bảo đảm thứ tự byte ổn định nếu chưa chọn chế độ deterministic/canonical phù hợp.

## 6. Định nghĩa schema của dạng biểu diễn chuẩn

Schema mô tả cấu trúc dữ liệu được phép và các quy tắc kiểm tra. Một schema tốt không chỉ định nghĩa field mà còn mô tả kiểu, cardinality, default, reference, version và extension point.

Ví dụ một document workflow dạng JSON:

~~~json
{
  "format": "example.dsl-model",
  "formatVersion": "1.0",
  "languageVersion": "2.1",
  "id": "wf-order-review",
  "kind": "workflow",
  "name": "OrderReview",
  "parameters": [
    {
      "id": "parameter-order",
      "name": "order",
      "typeRef": "type-order"
    }
  ],
  "steps": [
    {
      "id": "step-approval",
      "kind": "actionCall",
      "actionRef": "action-manager-approval"
    }
  ]
}
~~~

Đây là ví dụ minh họa schema, không phải một chuẩn JSON phổ quát. Một hệ thống thực tế cần công bố chính xác field nào bắt buộc, kiểu ID, cách biểu diễn biểu thức, source map và các giá trị được phép.

### Schema và semantic validation

Schema có thể xác nhận cấu trúc: `formatVersion` là chuỗi, `parameters` là array, `id` không rỗng. Semantic validation cần xác nhận `typeRef` trỏ đến một type tồn tại và `actionRef` trỏ đến action tương thích. Hai bước bổ sung cho nhau.

### Closed schema và open schema

**Closed schema** từ chối field không được định nghĩa. Nó giúp phát hiện typo và giảm nguy cơ consumer hiểu sai dữ liệu.

**Open schema** cho phép field mở rộng hoặc extension namespace. Nó hỗ trợ tiến hóa và metadata của công cụ khác, nhưng cần quy định cách bảo toàn field không biết.

Một chiến lược thường dùng là schema lõi nghiêm ngặt cộng vùng `extensions` được namespace hóa:

~~~json
{
  "id": "wf-order-review",
  "kind": "workflow",
  "extensions": {
    "com.example.editor": {
      "collapsed": false,
      "color": "blue"
    }
  }
}
~~~

Consumer không hiểu extension có thể giữ nguyên nó khi đọc rồi ghi lại, thay vì xóa mất.

## 7. Quy tắc canonicalization

Canonicalization chuyển các cách biểu diễn tương đương theo hợp đồng DSL về một biểu diễn ổn định. Quy tắc phải được đặc tả cụ thể và áp dụng nhất quán ở mọi implementation.

Các khía cạnh thường cần chuẩn hóa:

1. Encoding và newline.
2. Tên field và thứ tự field.
3. Thứ tự collection.
4. Kiểu số và cách viết literal.
5. Chuỗi và Unicode.
6. Giá trị mặc định, null và field vắng mặt.
7. Enum và identifier.
8. Reference và ID.
9. Thứ tự annotation hoặc metadata.
10. Cách biểu diễn extension và unknown field.

Canonicalization chỉ nên chuẩn hóa những khác biệt không ảnh hưởng semantics. Nếu thứ tự có ý nghĩa, phải giữ nguyên.

## 8. Encoding, newline và Unicode

Một canonical text format nên quy định encoding. UTF-8 là lựa chọn phổ biến cho tài liệu trao đổi văn bản. Nếu cho phép BOM, cần nói rõ có được giữ hay loại bỏ trong canonical output.

### Newline

Có thể quy định canonical text dùng LF (`\n`) dù source ban đầu dùng CRLF. Nếu vị trí nguồn được lưu theo offset, việc đổi newline làm thay đổi offset; vì vậy provenance cần ánh xạ hoặc được tách khỏi nội dung canonical.

### Unicode normalization

Một chuỗi hiển thị giống nhau có thể có nhiều cách mã hóa Unicode, ví dụ ký tự dựng sẵn hoặc ký tự cơ sở cộng combining mark. Nếu schema quy định Unicode normalization như NFC, serializer và validator cần áp dụng cùng quy tắc. Không nên tự chuẩn hóa identifier hoặc string literal nếu semantics DSL yêu cầu giữ nguyên code point.

### Identifier và string literal

Có thể có quy tắc normalization riêng cho identifier nhưng không áp dụng cho string literal. Ví dụ, tên biến có thể được so sánh sau NFC, trong khi chuỗi dữ liệu phải giữ chính xác nội dung người dùng nhập. Cần phân biệt hai loại này.

### Encoding lỗi

Nếu byte sequence không phải UTF-8 hợp lệ trong format yêu cầu UTF-8, parser nên từ chối với diagnostic cụ thể. Thay ký tự lỗi bằng replacement character rồi tiếp tục có thể làm thay đổi ID hoặc nội dung dữ liệu mà không được người dùng nhận biết.

## 9. Chuẩn hóa số và giá trị số học

Số là nguồn gây khác biệt giữa các serializer. Một giá trị có thể được viết `1`, `1.0`, `1e0` hoặc `1.000`. Nếu DSL coi chúng là cùng một decimal value, canonical form có thể chọn một cách biểu diễn duy nhất.

### Decimal chính xác

Với dữ liệu tài chính, có thể dùng decimal representation thay vì binary floating point. Schema cần quy định precision, scale, rounding mode và cách biểu diễn exponent.

Ví dụ, nếu `1.00` và `1` có cùng giá trị nhưng scale có ý nghĩa nghiệp vụ, canonicalization không được tự loại bỏ scale. Nếu scale không có ý nghĩa, có thể chuẩn hóa thành một dạng xác định.

### Integer và decimal

Không nên tự chuyển `1.0` thành integer `1` nếu schema phân biệt kiểu. `Integer(1)` và `Decimal(1)` có thể có cùng giá trị toán học nhưng khác kiểu, overload hoặc serialization contract.

### Giá trị đặc biệt

JSON tiêu chuẩn không biểu diễn `NaN`, `Infinity` hoặc `-Infinity` như number hợp lệ. Nếu DSL hỗ trợ chúng, cần quy định một representation rõ ràng, chẳng hạn tagged value hoặc từ chối khi serialize sang profile JSON.

### Negative zero

Một số kiểu số phân biệt `-0.0` và `0.0` ở một số phép toán hoặc bit representation. Canonical form phải giữ hoặc chuẩn hóa theo semantics đã công bố.

## 10. Chuỗi, escape và giá trị rỗng

Chuỗi có thể được serialize bằng nhiều cách escape tương đương. Canonical JSON chẳng hạn có thể chọn cách escape thống nhất cho dấu nháy, dấu gạch chéo ngược và control character. Cần bảo đảm sau parse, giá trị chuỗi không đổi.

### Null, missing và empty

Ba trạng thái này thường khác nhau:

- **Missing:** field không xuất hiện.
- **Null:** field xuất hiện nhưng có giá trị null.
- **Empty:** field có giá trị rỗng, ví dụ `""`, `[]` hoặc `{}`.

Ví dụ:

~~~json
{}
~~~

~~~json
{"description": null}
~~~

~~~json
{"description": ""}
~~~

Schema cần định nghĩa ba trường hợp có cùng ý nghĩa hay khác nhau. Với patch/update format, missing thường có nghĩa “không thay đổi”, còn null có thể có nghĩa “xóa giá trị”. Nếu canonicalizer tự chuyển chúng thành một dạng, có thể làm thay đổi semantics cập nhật.

### Default value

Nếu field có default, cần quyết định canonical serializer luôn ghi default hay lược bỏ khi bằng default. Cả hai có thể hợp lệ nhưng phải nhất quán. Khi default thay đổi giữa schema version, lược bỏ field có thể làm tài liệu cũ được diễn giải khác.

Một lựa chọn an toàn cho dữ liệu lưu trữ lâu dài là ghi rõ những giá trị ảnh hưởng semantics hoặc gắn schema version để default được xác định theo đúng phiên bản.

## 11. Thứ tự field và collection

JSON object và một số map không có thứ tự ngữ nghĩa. Serializer có thể cần sắp xếp key theo quy tắc xác định để tạo output ổn định. Nhưng array hoặc sequence thường có thứ tự và không được tự sắp xếp.

### Field order

Canonical profile có thể quy định thứ tự field theo schema hoặc thứ tự từ điển trên tên field. Tất cả implementation phải dùng cùng quy tắc, bao gồm cách so sánh Unicode và byte encoding nếu dùng lexical ordering.

### Array có thứ tự

Ví dụ danh sách bước workflow:

~~~json
{
  "steps": [
    {"id": "validate", "kind": "action"},
    {"id": "approve", "kind": "action"},
    {"id": "ship", "kind": "action"}
  ]
}
~~~

Thứ tự này là semantics thực thi. Không được sắp xếp theo ID hoặc tên.

### Collection không có thứ tự

Một tập capability hoặc nhãn có thể không có thứ tự. Nếu schema xác định collection là set, canonicalizer có thể sắp xếp theo một khóa ổn định và loại bỏ duplicate theo identity. Nếu schema chỉ gọi nó là array, không thể tự giả định thứ tự không quan trọng.

### Map key

Nếu map key là chuỗi, có thể sắp xếp theo quy tắc canonical. Nếu key là kiểu phức tạp, cần một canonical encoding cho key trước khi sắp xếp. Không nên dựa vào thứ tự iteration mặc định của hash map.

## 12. Chuẩn hóa biểu thức và thứ tự đánh giá

Chuẩn hóa biểu thức cần thận trọng vì các biểu thức trông tương đương về đại số có thể không tương đương trong ngữ nghĩa DSL.

Ví dụ, `a + b` và `b + a` chỉ tương đương nếu phép cộng có tính giao hoán trong miền kiểu đang xét và việc đánh giá hai toán hạng không có tác dụng phụ ảnh hưởng thứ tự.

### Có thể chuẩn hóa

Nếu DSL quy định khoảng trắng không có ý nghĩa ngoài string/comment, formatter có thể chuẩn hóa khoảng trắng. Nếu số literal có nhiều cách viết nhưng cùng kiểu và cùng giá trị, canonical serializer có thể chọn một dạng. Nếu tên field trong object không có thứ tự ngữ nghĩa, có thể sắp xếp.

### Không được chuẩn hóa tùy tiện

- Không đổi thứ tự các statement trong sequence.
- Không hoán đổi toán hạng nếu semantics không chứng minh tương đương.
- Không rút gọn biểu thức có side effect.
- Không thay `and` bằng `or` hoặc thay đổi precedence.
- Không gộp literal nếu có thể thay đổi kiểu hoặc overflow.
- Không bỏ qua dấu ngoặc nếu chúng ảnh hưởng parse.
- Không thay alias hoặc tên hiển thị nếu chúng là một phần contract công khai.

### AST canonicalization

Có thể chuẩn hóa AST bằng cách loại bỏ node cú pháp không cần thiết, chuyển alias về node chuẩn hoặc chuẩn hóa representation literal. Nhưng mỗi phép biến đổi phải bảo toàn observable behavior và source mapping nếu consumer cần điều hướng về văn bản gốc.

### Canonical form không phải optimizer

Canonicalization hướng đến biểu diễn ổn định, còn optimization hướng đến thực thi nhanh hơn. Một optimizer có thể inline, reorder hoặc eliminate computation dựa trên giả định ngữ nghĩa. Không nên trộn hai bước nếu consumer cần một dạng trao đổi dễ hiểu và ổn định.

## 13. Định danh ổn định cho phần tử

Trong tài liệu có nhiều phần tử cùng tên hoặc được tham chiếu từ nhiều nơi, cần ID ổn định.

Ví dụ:

~~~json
{
  "elements": [
    {
      "id": "entity-customer",
      "kind": "entity",
      "name": "Customer"
    },
    {
      "id": "entity-order",
      "kind": "entity",
      "name": "Order"
    }
  ]
}
~~~

ID cho phép tham chiếu đến phần tử mà không phụ thuộc tên hiển thị. Rename có thể thay `name` nhưng giữ `id`, giúp tham chiếu tiếp tục trỏ đúng đích.

### ID có thể được tạo thế nào?

- UUID hoặc ULID.
- ID do repository cấp.
- ID ổn định theo namespace và tên nếu quy tắc cho phép.
- Content-derived ID nếu identity được định nghĩa theo nội dung bất biến.

Không có lựa chọn phù hợp cho mọi trường hợp. ID ngẫu nhiên dễ tạo nhưng không ổn định khi export/import nếu không giữ nguyên. ID theo tên dễ đọc nhưng rename có thể làm thay đổi identity. Content-derived ID phù hợp với artifact bất biến nhưng không phù hợp với đối tượng có identity lâu dài dù nội dung thay đổi.

### Identity và equality

Hai phần tử có cùng nội dung không nhất thiết là cùng identity. Ví dụ hai workflow có nội dung giống nhau nhưng thuộc hai dự án hoặc hai tenant khác nhau. Schema cần phân biệt identity, structural equality và version identity.

### Scope của ID

ID có thể duy nhất trong một document, workspace, tenant hoặc toàn hệ thống. Reference phải mang đủ context để xác định đúng đích, chẳng hạn document ID cộng element ID hoặc URI đầy đủ.

## 14. Tham chiếu giữa phần tử

Canonical representation cần mô tả reference rõ ràng để tránh phụ thuộc vào cách tra cứu tên riêng của từng consumer.

Ví dụ reference bằng ID:

~~~json
{
  "id": "action-call-17",
  "kind": "actionCall",
  "actionRef": "action-approve-order"
}
~~~

Ví dụ reference bằng URI:

~~~json
{
  "target": "model://sales/Order#entity-order"
}
~~~

### Local reference và external reference

Local reference trỏ đến phần tử trong cùng document hoặc resource set. External reference trỏ đến resource khác qua URI, registry key hoặc repository identity.

Schema cần quy định:

- Cú pháp reference.
- Phạm vi phân giải.
- Quy tắc URI resolution và base URI.
- Phiên bản đích hoặc version range.
- Hành vi khi target không tồn tại hoặc chưa tải.
- Chính sách truy cập và trust.
- Cách giữ reference khi export/import.

### Dangling reference

Một reference có thể tồn tại trong document nhưng không tìm được target. Canonical parser có thể kiểm tra cú pháp reference; semantic validator cần resolve target và báo lỗi nếu đích không tồn tại theo chính sách.

### Reference cycle

Mô hình có thể chứa tham chiếu tạo chu kỳ. Serialization phải có cách biểu diễn graph mà không đệ quy vô hạn. Thường dùng ID/reference thay vì lồng toàn bộ object đích vào mỗi vị trí. Validator sau đó quyết định loại quan hệ nào được phép có cycle.

## 15. Biểu diễn đồ thị thay vì cây

JSON hoặc YAML thường được dùng như cấu trúc cây, nhưng semantic model của DSL có thể là graph: nhiều phần tử cùng tham chiếu một đích, hoặc có quan hệ hai chiều và chu kỳ.

Một cách biểu diễn graph là tách danh sách node và danh sách edge:

~~~json
{
  "nodes": [
    {"id": "start", "kind": "startEvent"},
    {"id": "approve", "kind": "approvalTask"},
    {"id": "ship", "kind": "shipmentTask"}
  ],
  "edges": [
    {"id": "edge-1", "from": "start", "to": "approve"},
    {"id": "edge-2", "from": "approve", "to": "ship"}
  ]
}
~~~

Ưu điểm:

- Node có identity độc lập.
- Nhiều edge có thể trỏ cùng node.
- Có thể biểu diễn cycle mà không lồng vô hạn.
- Dễ kiểm tra cardinality, reachability và graph constraints.
- Có thể cập nhật một node mà không sao chép toàn bộ nhánh lồng nhau.

Hạn chế là consumer phải resolve ID và có thể cần nhiều lần tra cứu. Với mô hình nhỏ dạng cây, nested representation có thể dễ đọc hơn. Lựa chọn phụ thuộc cấu trúc quan hệ của DSL.

## 16. Versioning của format và language

Một tài liệu trao đổi cần cho biết nó tuân theo phiên bản schema nào và phiên bản ngôn ngữ nào. Hai khái niệm này nên được tách biệt.

- **Format version:** cấu trúc serialization, field, encoding và reference representation.
- **Language version:** cú pháp và semantics DSL.
- **Compiler version:** implementation đã tạo hoặc tiêu thụ artifact.
- **Model version:** version nghiệp vụ hoặc revision của một tài liệu cụ thể.

Ví dụ:

~~~json
{
  "format": "example.dsl-model",
  "formatVersion": "2.0",
  "languageVersion": "3.1",
  "modelVersion": "revision-42"
}
~~~

Một thay đổi JSON field không nhất thiết là thay đổi semantics ngôn ngữ; ngược lại, semantics có thể thay đổi dù format giữ nguyên.

### Backward compatibility

Consumer mới đọc được tài liệu cũ. Có thể hỗ trợ bằng default, migration hoặc adapter. Nhưng default cần gắn với version để tránh thay đổi ý nghĩa của dữ liệu cũ.

### Forward compatibility

Consumer cũ gặp field hoặc enum value mới. Có thể từ chối, bỏ qua hoặc giữ nguyên unknown data. Lựa chọn phụ thuộc yêu cầu an toàn và khả năng round-trip.

### Breaking change

Đổi kiểu field, đổi meaning, xóa enum hoặc thay reference semantics có thể là breaking change. Nên tăng major format version hoặc tạo migration bắt buộc.

### Deprecation

Field cũ có thể được đánh dấu deprecated trong một khoảng thời gian, hỗ trợ đọc nhưng serializer mới không còn ghi. Cần tài liệu về thời điểm loại bỏ và công cụ migration.

## 17. Migration giữa phiên bản

Khi schema hoặc language version thay đổi, tài liệu cũ có thể cần được chuyển sang representation mới.

Migration có thể gồm:

- Đổi tên field.
- Chuyển scalar thành object có cấu trúc.
- Thay name reference bằng stable ID.
- Tách một loại node thành nhiều loại.
- Thêm default cho field mới.
- Chuyển enum cũ sang enum mới.
- Thay đổi cách biểu diễn decimal hoặc timestamp.
- Cập nhật reference URI hoặc dependency version.

### Migration phải có version nguồn và đích

Không nên chạy một chuỗi phép biến đổi không biết tài liệu đang ở version nào. Migration cần kiểm tra `fromVersion`, `toVersion` và có thể cần nhiều bước nhỏ theo thứ tự.

### Migration không luôn đảo ngược được

Nếu version cũ không có field mới hoặc đã gộp nhiều trạng thái thành một, không thể khôi phục chính xác mọi thông tin khi downgrade. Công cụ nên cảnh báo mất dữ liệu hoặc giữ extension/legacy metadata nếu cần.

### Lưu bản gốc

Với tài liệu quan trọng, có thể giữ bản gốc bất biến và tạo bản đã migrate như một revision mới. Điều này hỗ trợ audit, rollback và tái lập.

## 18. Unknown field và khả năng mở rộng

Khi consumer gặp field chưa biết, hành vi phải được quy định.

Các chiến lược:

- Từ chối tài liệu vì schema không tương thích.
- Bỏ qua field không biết khi đọc.
- Giữ field không biết trong extension bag để ghi lại sau.
- Từ chối field không biết trong namespace lõi nhưng chấp nhận extension namespace.

### Vì sao giữ unknown field quan trọng?

Giả sử Tool A phiên bản mới thêm metadata `layout`, còn Tool B cũ chỉ hiểu workflow semantics. Nếu B đọc rồi ghi lại mà xóa `layout`, thông tin của A bị mất dù B không có ý định chỉnh sửa nó.

Một consumer trung gian có thể bảo toàn unknown field bằng cách giữ raw node hoặc extension object. Tuy nhiên, nếu unknown field có thể ảnh hưởng semantics mà consumer không hiểu, không nên cho phép consumer đó thực thi tài liệu như thể đã xác thực đầy đủ.

### Namespace cho extension

Extension nên có namespace hoặc vendor identifier để tránh va chạm tên. Ví dụ `com.example.editor` hoặc URI namespace. Tránh thêm field tùy tiện vào root mà không có quy tắc ownership.

## 19. Round-trip và bảo toàn thông tin

Round-trip là quá trình đọc một biểu diễn vào mô hình nội bộ rồi ghi lại. Một hệ thống có thể cần hai mức bảo toàn.

### Semantic round-trip

Sau parse rồi serialize, ngữ nghĩa được bảo toàn dù văn bản hoặc thứ tự field thay đổi.

~~~text
source -> parse -> model -> serialize -> parse -> model2

semanticEqual(model, model2) == true
~~~

### Lossless/source round-trip

Sau parse rồi ghi lại, comment, khoảng trắng, dấu nháy, thứ tự field và chi tiết trình bày được giữ nguyên hoặc chỉ thay đổi theo formatter đã chọn.

~~~text
source -> lossless parse -> edit model -> print
~~~

Để đạt lossless round-trip, cần giữ CST, token trivia, raw scalar representation hoặc thông tin nguồn tương đương. AST thuần thường không đủ vì đã bỏ các chi tiết không ảnh hưởng semantics.

### Chọn mức round-trip

| Nhu cầu | Mô hình phù hợp |
|---|---|
| Chỉ trao đổi ngữ nghĩa | Semantic model + canonical serializer. |
| Cho phép tool đọc/ghi nhưng giữ metadata lạ | Semantic model + unknown field preservation. |
| Editor giữ comment và style | CST hoặc lossless syntax tree. |
| Hash/signature ổn định | Canonical byte representation theo profile. |
| Debug và provenance | Model + source map/provenance. |

Không nên tuyên bố lossless round-trip nếu parser loại bỏ comment, quote style hoặc unknown field.

## 20. Canonical serialization và byte stability

Nếu cần hash, signature hoặc content-addressable storage, điều quan trọng là cùng một mô hình canonical phải tạo cùng byte sequence.

Các yếu tố cần cố định:

- Encoding UTF-8 hoặc encoding được chọn.
- BOM có hay không.
- Newline.
- Thứ tự field và map key.
- Cách viết số và exponent.
- Escape chuỗi.
- Unicode normalization.
- Khoảng trắng giữa token.
- Quy tắc biểu diễn null/default/missing.
- Cách serialize timestamp và timezone.
- Cách biểu diễn binary data.

### Canonical JSON

JSON bản thân không bắt buộc mọi serializer phải tạo cùng byte sequence. Nếu dùng JSON để hash hoặc ký, cần chọn một canonicalization scheme như JSON Canonicalization Scheme (JCS) hoặc định nghĩa profile tương đương, rồi tuân thủ chính xác. Không nên tự viết một bộ sắp xếp key đơn giản và gọi đó là chuẩn nếu còn các trường hợp số, Unicode hoặc escape chưa được giải quyết.

### Canonical XML

XML có namespace, attribute và nhiều cách viết tương đương. Nếu cần chữ ký XML, phải dùng canonicalization method phù hợp với profile và xử lý namespace đúng. Chỉ format XML cho đẹp không tương đương XML canonicalization.

### Deterministic binary encoding

Với CBOR hoặc định dạng nhị phân, cần chọn deterministic encoding profile. Với Protocol Buffers, serialization byte order không nên được xem là canonical theo mặc định trong mọi trường hợp; nếu cần hash/signature, cần canonical layer được định nghĩa và kiểm thử.

### Hash semantic model hay hash serialized bytes?

Hash bytes trả lời câu hỏi “các byte có giống nhau không?”. Hash semantic model trả lời “các thành phần logic có giống nhau theo quy tắc so sánh đã chọn không?”. Có thể canonicalize model trước rồi hash canonical bytes. Cần nói rõ hash dùng cho integrity, cache, identity hay so sánh vì các mục đích có thể cần phạm vi dữ liệu khác nhau.

## 21. Chữ ký số và tính toàn vẹn

Canonical representation thường là đầu vào của hash và chữ ký số.

Quy trình khái quát:

1. Parse tài liệu và xác thực schema.
2. Chuẩn hóa theo canonicalization profile đã công bố.
3. Serialize thành byte sequence xác định.
4. Tính hash.
5. Ký hash bằng khóa ký.
6. Khi xác minh, canonicalize lại bằng cùng profile và kiểm tra chữ ký.

### Ký nội dung hay ký envelope?

Envelope có thể chứa metadata vận chuyển như thời điểm upload, người gửi hoặc thông tin routing. Nếu metadata này không thuộc nội dung cần bảo vệ, có thể ký phần payload canonical riêng. Nếu metadata có ý nghĩa bảo mật, nó cũng cần được ký hoặc ràng buộc bằng một chữ ký bao ngoài.

### Signature không thay thế validation

Chữ ký hợp lệ chứng minh dữ liệu được ký bởi khóa tương ứng và không bị thay đổi theo phạm vi ký. Nó không chứng minh DSL hợp lệ, logic an toàn hoặc người ký có quyền phê duyệt nội dung. Cần xác thực schema, semantics, danh tính và authorization riêng.

### Key rotation và algorithm agility

Envelope có thể chứa key ID và thuật toán chữ ký. Hệ thống cần chính sách xoay khóa, thu hồi khóa, kiểm tra thời điểm hiệu lực và nâng cấp thuật toán. Không nên hard-code một thuật toán vĩnh viễn vào format mà không có cơ chế tiến hóa.

## 22. Envelope cho tài liệu trao đổi

Một document trao đổi thường cần metadata bao quanh payload để consumer biết cách xử lý.

Ví dụ:

~~~json
{
  "envelopeVersion": "1",
  "mediaType": "application/vnd.example.dsl-model+json",
  "payload": {
    "formatVersion": "2.0",
    "languageVersion": "3.1",
    "id": "wf-order-review",
    "kind": "workflow",
    "name": "OrderReview"
  },
  "integrity": {
    "algorithm": "sha-256",
    "digest": "..."
  }
}
~~~

Envelope có thể chứa:

- Media type hoặc format identifier.
- Format version và language version.
- Document ID và revision.
- Producer/tool identity và version.
- Creation metadata nếu cần.
- Dependency manifest.
- Payload hoặc payload reference.
- Hash, signature hoặc encryption metadata.
- Provenance và import context.

Không phải mọi metadata đều nên nằm trong canonical payload. Thời điểm tạo hoặc đường dẫn máy cục bộ có thể thay đổi dù nội dung logic không đổi. Tách envelope khỏi payload giúp hash nội dung ổn định hơn.

## 23. Lưu trữ nhiều tài liệu và dependency package

Một dự án DSL có thể gồm nhiều document liên kết. Dạng biểu diễn chuẩn cần xác định package boundary và cách đóng gói dependency.

### Single document

Phù hợp khi mô hình nhỏ, không có nhiều reference ngoài hoặc có thể tự chứa toàn bộ dependency.

### Resource set

Một package có thể chứa nhiều document và manifest:

~~~text
package/
  manifest.json
  models/order.json
  models/customer.json
  workflows/fulfillment.json
  policies/approval.json
~~~

Manifest có thể liệt kê document ID, path tương đối, version, hash và dependency. Reference giữa document dùng ID hoặc URI ổn định, không nên phụ thuộc đường dẫn file tuyệt đối trên máy người tạo.

### Bundle và external dependency

Một bundle có thể nhúng toàn bộ dependency để dễ trao đổi ngoại tuyến. Một bundle khác chỉ chứa manifest và reference đến registry bên ngoài. Cần nói rõ dependency có được pin version và hash hay không.

### Import/export

Import cần kiểm tra ID xung đột, namespace, version, reference và quyền. Export cần xác định có bao gồm dependency, metadata riêng, comment và source map hay không.

## 24. Streaming và tài liệu lớn

Với DSL chứa hàng triệu node hoặc nhiều bản ghi, đọc toàn bộ document vào memory có thể không phù hợp. Định dạng trao đổi cần cân nhắc streaming.

### Streaming JSON

Một parser streaming đọc token tuần tự và có thể xử lý từng phần tử array mà không tạo toàn bộ object graph. Điều này phù hợp với export/import dữ liệu lớn, nhưng reference đến phần tử xuất hiện sau có thể cần một pass hoặc index riêng.

### NDJSON hoặc record stream

Một số hệ thống có thể trao đổi từng record JSON trên một dòng. Cần một envelope hoặc manifest để xác định schema, thứ tự, tính hoàn chỉnh và cách xử lý record lỗi.

### Binary stream

Định dạng binary có thể hỗ trợ length prefix hoặc framed message. Cần giới hạn kích thước frame, xác định cách phục hồi khi frame hỏng và cách xử lý phiên bản khác nhau.

### Forward reference trong streaming

Nếu một node tham chiếu đến node chưa được đọc, consumer có thể giữ unresolved reference tạm thời rồi resolve sau khi đọc xong, hoặc yêu cầu writer sắp xếp dependency trước. Quy tắc này phải được công bố để các implementation tương thích.

### Backpressure

Khi consumer xử lý chậm hơn producer, stream cần backpressure hoặc buffer giới hạn. Nếu không, memory có thể tăng không giới hạn.

## 25. Tương thích và liên tác giữa nhiều implementation

Hai implementation chỉ thực sự liên tác nếu chúng hiểu cùng schema và semantics, không chỉ parse được cùng cú pháp.

Các yếu tố cần chuẩn hóa:

- Cách so sánh identifier và tên.
- Kiểu số và phép chuyển đổi.
- Null, missing và default.
- Thứ tự statement, map và collection.
- Reference resolution và namespace.
- Enum value và unknown enum handling.
- Timezone, timestamp và duration.
- Error representation và diagnostic code.
- Extension namespace và unknown field preservation.
- Version negotiation và capability.

### Capability negotiation

Consumer có thể công bố các tính năng hỗ trợ như `workflow-v2`, `graph-reference`, `decimal-128` hoặc extension cụ thể. Producer chọn representation tương thích hoặc từ chối nếu tính năng bắt buộc không được hỗ trợ.

### Strict và permissive mode

Strict mode từ chối cấu trúc hoặc feature không được schema hỗ trợ. Permissive mode có thể giữ unknown metadata hoặc bỏ qua phần không ảnh hưởng. Với dữ liệu có tác động thực thi, strict mode thường phù hợp hơn; permissive mode có thể hữu ích cho editor trung gian hoặc công cụ hiển thị.

### Conformance suite

Một chuẩn cần bộ test chung để kiểm tra parser, serializer, canonicalization, version compatibility và edge cases. Nếu không có conformance suite, mỗi implementation có thể diễn giải một chi tiết khác nhau dù cùng tuyên bố hỗ trợ format.

## 26. Bảo mật khi đọc dạng biểu diễn chuẩn

Một file có schema hợp lệ vẫn có thể chứa payload rất lớn, reference độc hại hoặc cấu trúc khiến parser tiêu tốn tài nguyên quá mức. Canonical format cần có giới hạn và quy tắc xử lý an toàn.

### Giới hạn parser

- Giới hạn kích thước document và string.
- Giới hạn nesting depth.
- Giới hạn số node, field và collection item.
- Giới hạn số reference cần resolve.
- Giới hạn thời gian parse và validation.
- Từ chối số hoặc exponent vượt giới hạn được hỗ trợ.

### XML entity expansion

Nếu dùng XML, cần cấu hình parser an toàn, kiểm soát external entity và DTD theo threat model. Không nên cho tài liệu không tin cậy tự động đọc file cục bộ hoặc gọi URL thông qua entity resolution.

### YAML features

YAML có thể hỗ trợ tag, anchor và alias. Parser cần quy định tập tag được phép, giới hạn alias expansion và tránh cơ chế deserialize thành object tùy ý từ class name do tài liệu cung cấp.

### JSON parser

JSON đơn giản hơn về tính năng, nhưng vẫn cần giới hạn depth, size, duplicate key và xử lý number chính xác. Duplicate key có thể được các parser xử lý khác nhau; canonical profile nên từ chối hoặc quy định cách xử lý rõ ràng.

### Reference ngoài

Không tự động tải mọi URI xuất hiện trong tài liệu. External reference có thể dẫn đến SSRF, truy cập tài nguyên nội bộ hoặc dependency không tin cậy. Nên có resolver được cấu hình, allowlist, timeout và quyền truy cập.

### Deserialization an toàn

Không deserialize payload thành class tùy ý dựa trên type name do người gửi cung cấp. Dùng schema registry hoặc type discriminator nằm trong allowlist và kiểm tra kiểu trước khi tạo object.

## 27. Dạng biểu diễn chuẩn và provenance

Provenance là thông tin về nguồn gốc và lịch sử hình thành một phần tử hoặc tài liệu. Nó có thể gồm người tạo, tool tạo, source file, revision, import origin và transformation history.

Ví dụ:

~~~json
{
  "id": "workflow-fulfillment",
  "kind": "workflow",
  "provenance": {
    "sourceUri": "project://sales/workflows/fulfillment.dsl",
    "sourceRevision": "rev-42",
    "generatedBy": "dsl-compiler/5.2"
  }
}
~~~

Provenance giúp audit và điều hướng về nguồn. Tuy nhiên, metadata này có thể chứa path nội bộ hoặc thông tin người dùng. Cần phân loại phần nào thuộc canonical semantics, phần nào là metadata tùy chọn và phần nào không được export ra ngoài.

### Source map

Nếu semantic model được tạo từ DSL source, source map có thể liên kết node ID với file URI và range. Khi tool khác phát diagnostic trên model, nó có thể ánh xạ về đoạn DSL tương ứng.

### Provenance qua transformation

Khi một model được transform hoặc merge, provenance có thể lưu nhiều nguồn đầu vào. Không nên giả định một node sau transform luôn có một source span duy nhất.

## 28. Ví dụ chuẩn hóa một document DSL

Giả sử hai document JSON có thứ tự field khác nhau và một số khoảng trắng khác nhau:

~~~json
{
  "name": "OrderReview",
  "kind": "workflow",
  "id": "wf-17",
  "steps": ["validate", "approve"]
}
~~~

~~~json
{"steps":["validate","approve"],"id":"wf-17","kind":"workflow","name":"OrderReview"}
~~~

Nếu schema xác định object field order không có ý nghĩa và `steps` là sequence có thứ tự, canonicalizer có thể tạo cùng một byte representation bằng cách:

1. Parse cả hai document thành data model.
2. Xác thực field và kiểu.
3. Giữ nguyên thứ tự `steps`.
4. Sắp xếp field object theo canonical profile.
5. Chuẩn hóa string escaping và number representation.
6. Serialize theo encoding và whitespace đã định nghĩa.

Kết quả canonical có thể là:

~~~json
{"id":"wf-17","kind":"workflow","name":"OrderReview","steps":["validate","approve"]}
~~~

Ví dụ chỉ minh họa. Muốn dùng cho hash hoặc chữ ký, phải chọn một canonical JSON specification/profile chính xác và tuân thủ đầy đủ, thay vì dựa vào ví dụ rút gọn này.

## 29. Ví dụ Java: tách model khỏi serializer

Một thiết kế dễ bảo trì là dùng model trung gian độc lập với thư viện JSON/XML cụ thể.

~~~java
record WorkflowModel(
    String id,
    String name,
    String languageVersion,
    List<WorkflowStep> steps
) {}

sealed interface WorkflowStep
    permits ActionStep, ConditionStep {}

record ActionStep(
    String id,
    String actionRef
) implements WorkflowStep {}

record ConditionStep(
    String id,
    Expression condition,
    List<WorkflowStep> thenSteps,
    List<WorkflowStep> elseSteps
) implements WorkflowStep {}
~~~

Serializer có thể chuyển `WorkflowModel` sang JSON hoặc một định dạng khác. Parser của định dạng trao đổi tạo lại cùng model. Compiler không cần phụ thuộc vào class của JSON library.

### Canonical serializer dạng pseudocode

~~~text
serializeCanonical(model):
    validateModel(model)
    normalized = canonicalize(model)
    ordered = orderFieldsAndUnorderedCollections(normalized)
    encoded = encodeWithCanonicalProfile(ordered)
    return encoded
~~~

`canonicalize` phải áp dụng các quy tắc đã công bố. `orderFieldsAndUnorderedCollections` chỉ sắp xếp cấu trúc được xác định là không có thứ tự. `encodeWithCanonicalProfile` quyết định encoding, escape, number formatting và whitespace.

### Không serialize trực tiếp object runtime tùy ý

Class runtime có thể chứa cache, proxy, service handle, thread, callback hoặc trạng thái nội bộ không thuộc mô hình DSL. Nên chuyển về DTO hoặc canonical model trước khi serialize. Điều này giảm phụ thuộc implementation và tránh vô tình ghi dữ liệu không nên trao đổi.

## 30. Kiểm thử dạng biểu diễn chuẩn

Một format chỉ đáng tin khi parser, serializer và canonicalizer có thể được kiểm thử độc lập và liên implementation.

### Round-trip test

Kiểm tra:

~~~text
model1 = parseCanonical(bytes)
bytes2 = serializeCanonical(model1)
model2 = parseCanonical(bytes2)

assert semanticEqual(model1, model2)
assert bytes2 == serializeCanonical(model2)
~~~

Điều kiện cuối kiểm tra tính ổn định của canonical serialization sau lần chuẩn hóa đầu tiên.

### Golden file test

Lưu các document canonical làm fixture. Khi serializer thay đổi, so sánh byte output để phát hiện thay đổi không dự kiến. Nếu thay đổi là chủ ý, cần cập nhật format version hoặc fixture kèm lý do.

### Cross-implementation test

Serialize bằng implementation A, parse bằng B, serialize lại bằng B và so sánh semantic model hoặc canonical bytes theo hợp đồng. Đây là cách phát hiện khác biệt giữa ngôn ngữ lập trình và thư viện parser.

### Property-based test

Sinh model hợp lệ ngẫu nhiên, serialize, parse và so sánh. Có thể tạo các cấu trúc lồng sâu, graph có reference, collection rỗng, decimal biên, Unicode và extension field.

### Fuzzing

Fuzz parser với byte sequence hoặc document sai định dạng. Parser phải từ chối an toàn, không treo, không tiêu thụ tài nguyên vô hạn và không thực thi nội dung ngoài ý muốn.

### Compatibility test

Kiểm tra đọc tài liệu từ version cũ, xử lý field mới, enum value mới, unknown extension và migration. Cần test cả trường hợp downgrade nếu hệ thống có hỗ trợ.

## 31. Diff và merge trên canonical representation

Canonical representation có thể giảm nhiễu khi so sánh tài liệu, nhưng diff văn bản vẫn chưa chắc phản ánh đúng quan hệ ngữ nghĩa.

### Text diff

Text diff so sánh từng dòng hoặc từng byte. Canonical output ổn định giúp diff dễ đọc hơn vì serializer không thay đổi format tùy ý.

### Structural diff

Structural diff so sánh node theo ID, loại và thuộc tính. Nó có thể nhận diện một node được rename, một edge được thêm hoặc một field được cập nhật thay vì xem toàn bộ object là một khối văn bản.

### Semantic diff

Semantic diff xác định thay đổi có ảnh hưởng đến hành vi không. Ví dụ, đổi thứ tự bước workflow có thể là thay đổi semantics; đổi màu node trong editor có thể chỉ là metadata hiển thị.

### Merge conflict

Hai người dùng có thể cùng sửa một node hoặc hai phần tử tham chiếu lẫn nhau. Merge engine cần ID ổn định, quy tắc conflict resolution và bước semantic validation sau merge. Không nên chỉ nối hai file JSON rồi coi kết quả là hợp lệ.

## 32. Dạng biểu diễn chuẩn và lưu trữ bền vững

Lưu trữ lâu dài cần chú ý khả năng đọc lại, durability và migration.

### Atomic write

Khi ghi document, nên tránh để reader thấy file mới chỉ được ghi một phần. Có thể ghi vào file tạm, flush theo yêu cầu durability rồi rename nguyên tử nếu storage hỗ trợ.

### Revision và immutable snapshot

Một tài liệu có thể được lưu thành các revision bất biến. Mỗi revision có ID, parent revision, content hash và metadata. Cách này hỗ trợ audit, rollback và so sánh.

### Index

Repository có thể lập chỉ mục document ID, element ID, reference, type và version để tra cứu nhanh. Index cần được cập nhật cùng transaction hoặc có cơ chế rebuild từ canonical source.

### Backup và restore

Backup cần bao gồm payload, schema/format version, dependency manifest và các khóa hoặc metadata cần thiết để giải mã/xác minh. Khôi phục cần kiểm tra integrity và compatibility trước khi đưa dữ liệu vào runtime.

### Retention

Không phải mọi cache, source map và provenance đều cần lưu cùng thời hạn với canonical document. Cần chính sách retention theo mục đích và độ nhạy dữ liệu.

## 33. Lựa chọn canonical source of truth

Một hệ thống có thể giữ source DSL và canonical model song song. Cần xác định cái nào là nguồn sự thật.

### Source là source of truth

Canonical model được tạo lại từ source. Cách này phù hợp khi người dùng chỉnh sửa DSL text và semantic model chỉ là kết quả phân tích.

### Model là source of truth

Canonical model được chỉnh sửa bằng editor hoặc API; DSL text có thể được sinh để hiển thị hoặc export. Cách này phù hợp với graph editor, form-based DSL hoặc hệ thống model-driven.

### Hai chiều

Nếu cả source và model đều có thể được chỉnh sửa, cần quy tắc đồng bộ, conflict detection và round-trip fidelity. Không nên để hai bản trở thành hai nguồn sự thật độc lập mà không có revision hoặc merge protocol.

### Derived artifact

AST, IR, bytecode, index và cache thường là derived data có thể tái tạo từ source/model cộng với toolchain version. Chúng không nên được coi là canonical source nếu không có lý do rõ ràng.

## 34. Những sai lầm thường gặp

**Coi JSON/YAML là canonical theo mặc định.** Định dạng chỉ là container; schema và canonicalization profile mới xác định cách hiểu ổn định.

**Dùng AST nội bộ làm interchange contract.** Internal node class có thể thay đổi theo compiler release và chứa chi tiết không phù hợp cho consumer bên ngoài.

**Không phân biệt format version với language version.** Thay đổi cấu trúc serialization và thay đổi semantics ngôn ngữ là hai việc khác nhau.

**Sắp xếp mọi collection.** Thứ tự workflow, statement hoặc argument có thể mang ý nghĩa. Chỉ sắp xếp collection được đặc tả là unordered.

**Bỏ qua missing/null/default.** Ba trạng thái có thể khác nhau, đặc biệt trong patch và migration.

**Chuẩn hóa số làm mất kiểu hoặc precision.** `Integer`, `Decimal`, scale và negative zero có thể có semantics riêng.

**Không dùng stable ID.** Rename hoặc di chuyển phần tử có thể làm hỏng mọi reference dựa trên tên hoặc path.

**Serialize graph như cây đệ quy.** Reference cycle có thể gây vòng lặp vô hạn hoặc nhân bản đối tượng. Dùng ID và edge khi cần biểu diễn graph.

**Loại bỏ unknown field khi round-trip.** Tool trung gian có thể làm mất extension mà nó không hiểu.

**Ký văn bản chưa canonicalize.** Khác biệt whitespace, key order hoặc escape có thể làm signature không ổn định.

**Nhầm chữ ký hợp lệ với nội dung an toàn.** Signature không thay thế schema validation, semantic validation hoặc authorization.

**Không giới hạn parser.** Document độc hại có thể gây nesting sâu, alias expansion hoặc tải external reference ngoài ý muốn.

**Không kiểm thử liên tác.** Một serializer chạy tốt với parser cùng thư viện chưa chứng minh implementation khác có thể đọc cùng nội dung.

## 35. Quy trình thiết kế dạng biểu diễn chuẩn

Một quy trình thực tế có thể gồm:

1. **Xác định mục tiêu:** source round-trip, semantic interchange, hashing/signature, runtime artifact hay nhiều mục tiêu.
2. **Chọn tầng model:** CST, AST, semantic model hoặc graph model độc lập với compiler.
3. **Định nghĩa schema:** document, node, field, type, cardinality, reference và extension.
4. **Chọn encoding:** JSON, XML, YAML, binary hoặc canonical DSL text dựa trên consumer và workload.
5. **Định nghĩa canonicalization:** encoding, newline, field order, collection order, number, string, Unicode, null và default.
6. **Thiết kế identity/reference:** ID ổn định, URI, namespace, local/external target và cycle handling.
7. **Định nghĩa versioning:** format, language, model, compiler và dependency version.
8. **Thiết kế migration:** chuyển version, xử lý downgrade và bảo toàn legacy data.
9. **Quy định round-trip:** semantic, lossless hoặc unknown-field preservation.
10. **Thiết kế integrity:** hash, signature, encryption và trust boundary nếu cần.
11. **Thiết kế storage/package:** manifest, revision, dependency bundle, atomic write và index.
12. **Thiết kế parser an toàn:** giới hạn size/depth, entity/alias, external reference và deserialization.
13. **Xây dựng conformance suite:** round-trip, golden files, fuzzing, cross-implementation và compatibility.
14. **Công bố contract:** schema, canonicalization profile, version policy và ví dụ chuẩn.

## 36. Checklist cho một format DSL mới

Trước khi công bố dạng biểu diễn chuẩn, cần trả lời:

- Mục tiêu chính là lưu trữ, trao đổi, edit, hash/signature hay thực thi?
- Consumer cần semantic model hay source text lossless?
- Schema có định nghĩa field, type, default và cardinality đầy đủ không?
- Format version có tách khỏi language version không?
- Encoding, newline và Unicode normalization được quy định thế nào?
- Number, timestamp, duration, null và missing được biểu diễn ra sao?
- Field order và collection order có semantics không?
- Identifier có stable ID không? ID duy nhất trong phạm vi nào?
- Reference nội bộ và bên ngoài được biểu diễn và resolve thế nào?
- Graph cycle có thể xuất hiện không?
- Unknown field và extension được giữ hay từ chối?
- Round-trip cần semantic hay lossless fidelity?
- Canonical bytes được tạo theo profile nào nếu cần hash hoặc signature?
- Migration và compatibility được hỗ trợ qua những version nào?
- Parser có giới hạn và bảo vệ trước payload độc hại không?
- Có conformance test giữa nhiều implementation không?
- Có source map/provenance nếu consumer cần diagnostic hoặc audit không?
- Ai sở hữu schema, extension namespace và quy trình thay đổi chuẩn?

## 37. Kết quả cần có sau khi đặc tả dạng biểu diễn chuẩn

Một đặc tả hoàn chỉnh thường cung cấp:

- **Canonical model:** các khái niệm, node, thuộc tính và quan hệ công khai của DSL.
- **Serialization schema:** field, type, cardinality, default, null và extension.
- **Canonicalization profile:** encoding, Unicode, number, string, ordering và byte stability.
- **Identity/reference model:** stable ID, URI, namespace, graph edge và resolution rules.
- **Version policy:** format version, language version, compatibility và migration.
- **Round-trip contract:** semantic fidelity, lossless source fidelity và unknown-field preservation.
- **Integrity/security model:** hash, signature, encryption, trust, parser limits và safe deserialization.
- **Storage/interchange package:** envelope, manifest, dependency, revision và provenance.
- **Conformance suite:** golden files, round-trip, cross-implementation, fuzzing và compatibility tests.
- **Governance:** chủ sở hữu schema, extension namespace, deprecation và quy trình phát hành version.

Dạng biểu diễn chuẩn tạo ra hợp đồng chung để các công cụ DSL lưu trữ, trao đổi và hiểu cùng một mô hình. Muốn hợp đồng đó bền vững, cần tách semantic model khỏi chi tiết triển khai, định nghĩa schema và version rõ ràng, giữ identity/reference ổn định, đồng thời quy định chính xác canonicalization cho các giá trị và thứ tự. Nếu cần hash hoặc chữ ký, canonical bytes phải được tạo theo một profile xác định; nếu cần editor round-trip, phải giữ thêm trivia và metadata nguồn. Khi parser an toàn, migration có kiểm soát và conformance tests được dùng giữa nhiều implementation, dạng biểu diễn chuẩn trở thành nền tảng đáng tin cậy cho lưu trữ lâu dài và liên tác giữa các hệ thống.
