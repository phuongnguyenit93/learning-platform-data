# DSL độc lập

## 1. Khái niệm DSL độc lập

Ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL) được thiết kế để biểu đạt các khái niệm và thao tác trong một miền vấn đề có ranh giới xác định. Có nhiều cách xây dựng DSL. Một cách là tận dụng cú pháp và cơ chế của ngôn ngữ lập trình chủ; cách khác là định nghĩa một ngôn ngữ có cú pháp riêng, được phân tích và xử lý bởi bộ công cụ dành cho ngôn ngữ đó.

Trong phạm vi phân biệt DSL nội bộ và DSL bên ngoài, **DSL độc lập** thường chỉ **DSL bên ngoài (external DSL)**: ngôn ngữ có cách viết, quy tắc cú pháp và cách diễn giải riêng, tách khỏi cú pháp của một ngôn ngữ lập trình chủ. Người dùng viết mô tả bằng ngôn ngữ này trong tệp hoặc môi trường chuyên biệt; một parser và các thành phần xử lý của DSL sẽ đọc, kiểm tra rồi chuyển mô tả thành kết quả.

Ví dụ, một nhóm có thể tạo DSL để khai báo pipeline xử lý dữ liệu:

```text
pipeline "customer-revenue" {
    source "orders.csv" format csv
    filter status == "PAID"
    group_by customer_id
    aggregate total = sum(amount)
    output "customer-revenue.csv" format csv
}
```

Đoạn mã trên là cú pháp giả định để minh họa, không phải cú pháp của một công cụ có sẵn. Người viết không cần đặt các biểu thức này bên trong Java, Kotlin hay Python. Một công cụ riêng có thể đọc tệp, phân tích cấu trúc, kiểm tra tên trường và kiểu dữ liệu, rồi tạo kế hoạch thực thi pipeline.

Từ “độc lập” ở đây nói đến **sự độc lập về cú pháp và mô hình ngôn ngữ đối với ngôn ngữ chủ**. Nó không có nghĩa DSL nhất thiết phải là một chương trình thực thi độc lập, không phụ thuộc thư viện hoặc không tích hợp với ứng dụng khác. Một DSL bên ngoài vẫn có thể được triển khai bằng Java, dùng thư viện Java và chạy bên trong một ứng dụng Java. Điều quan trọng là người sử dụng DSL viết theo ngữ pháp riêng của DSL thay vì viết các biểu thức theo ngữ pháp của Java.

## 2. Đặc điểm nhận biết

Một DSL độc lập thường có các đặc điểm sau:

1. **Có cú pháp riêng.** Ngôn ngữ định nghĩa các từ khóa, toán tử, dấu phân cách, quy tắc đặt tên và cách tổ chức câu lệnh.
2. **Có ngữ pháp có thể mô tả.** Cấu trúc hợp lệ có thể được đặc tả bằng EBNF, PEG hoặc một hình thức ngữ pháp khác.
3. **Có bộ phân tích riêng.** Công cụ đọc văn bản DSL và xây dựng cấu trúc cú pháp như AST (Abstract Syntax Tree).
4. **Có ngữ nghĩa thuộc miền.** Các cấu trúc cú pháp được diễn giải theo khái niệm, quy tắc và ràng buộc của miền.
5. **Có công cụ xử lý riêng.** Tùy mục tiêu, công cụ có thể kiểm tra, diễn giải, sinh mã, tạo cấu hình hoặc lập kế hoạch thực thi.
6. **Có thể được dùng từ nhiều môi trường.** Vì không gắn cú pháp với một ngôn ngữ chủ cụ thể, nhiều ứng dụng hoặc nhóm công nghệ có thể trao đổi cùng một định dạng DSL nếu cùng tuân theo đặc tả.

Không phải DSL độc lập nào cũng cần một trình biên dịch đầy đủ. Một DSL nhỏ có thể được xử lý bằng parser đơn giản và bộ thông dịch. DSL lớn hơn có thể cần hệ thống kiểu, mô hình trung gian, tối ưu hóa, sinh mã, runtime và công cụ phát triển.

## 3. DSL độc lập trong nhóm DSL nội bộ và bên ngoài

Hai hướng phổ biến là DSL nội bộ (internal hoặc embedded DSL) và DSL bên ngoài (external DSL). Chúng cùng phục vụ một miền nhưng khác nhau ở cách người dùng biểu đạt và cách công cụ xử lý.

### 3.1. DSL nội bộ

DSL nội bộ được xây dựng bên trong một ngôn ngữ chủ. Nó tận dụng cú pháp, hệ thống kiểu, hàm, đối tượng, biểu thức và công cụ của ngôn ngữ chủ để tạo ra cách diễn đạt gần với miền.

Ví dụ giả định bằng Java:

```java
Pipeline pipeline = pipeline("customer-revenue")
    .source("orders.csv")
    .filter(eq(field("status"), value("PAID")))
    .groupBy(field("customer_id"))
    .aggregate("total", sum(field("amount")))
    .output("customer-revenue.csv");
```

Đoạn mã này vẫn phải tuân theo cú pháp Java. Các hàm như `pipeline`, `field`, `sum` là API do thư viện cung cấp. Trình biên dịch Java xử lý cú pháp tổng thể; thư viện DSL cung cấp ý nghĩa miền.

### 3.2. DSL độc lập hoặc DSL bên ngoài

DSL độc lập có cú pháp tách khỏi ngôn ngữ chủ:

```text
pipeline "customer-revenue" {
    source "orders.csv"
    filter status == "PAID"
    group_by customer_id
    aggregate total = sum(amount)
    output "customer-revenue.csv"
}
```

Đoạn mã này không phải mã Java hợp lệ. Công cụ DSL cần lexer/parser hoặc một thư viện phân tích phù hợp để đọc cấu trúc riêng. Sau khi phân tích, ứng dụng có thể chuyển AST thành mô hình thực thi nội bộ.

### 3.3. Bảng so sánh

| Tiêu chí | DSL nội bộ | DSL độc lập / bên ngoài |
|---|---|---|
| Cú pháp | Dựa trên cú pháp ngôn ngữ chủ | Có ngữ pháp và cách viết riêng |
| Parser | Thường dùng parser của ngôn ngữ chủ | Cần parser riêng hoặc parser cho định dạng đã chọn |
| Hệ thống kiểu | Có thể tận dụng kiểu của ngôn ngữ chủ | Có thể định nghĩa kiểu riêng hoặc ánh xạ sang kiểu nền |
| Công cụ IDE | Thường được hưởng hỗ trợ của ngôn ngữ chủ | Có thể cần formatter, syntax highlighting, autocomplete và language server riêng |
| Khả năng biểu đạt | Bị giới hạn phần nào bởi cú pháp chủ | Có thể thiết kế cú pháp sát với miền hơn |
| Tích hợp với mã ứng dụng | Thường trực tiếp và thuận tiện | Cần giao tiếp qua parser, API, mô hình trung gian hoặc tệp |
| Người sử dụng | Thường cần biết ngôn ngữ chủ | Có thể hướng đến chuyên gia miền không dùng ngôn ngữ chủ |
| Chi phí ban đầu | Có thể thấp nếu API và ngôn ngữ chủ đã phù hợp | Thường cao hơn do phải xây dựng và duy trì công cụ ngôn ngữ |
| Tính di động | Có thể phụ thuộc ngôn ngữ và runtime chủ | Định dạng có thể được nhiều nền tảng xử lý nếu có triển khai tương thích |

Không có lựa chọn luôn tốt hơn. DSL độc lập phù hợp khi lợi ích của cú pháp riêng, khả năng sử dụng bởi nhiều nhóm hoặc yêu cầu kiểm soát ngôn ngữ đủ lớn để bù cho chi phí xây dựng công cụ. DSL nội bộ phù hợp khi người dùng đã quen ngôn ngữ chủ, việc tích hợp với mã nguồn quan trọng và API có thể diễn đạt miền rõ ràng.

## 4. Kiến trúc tổng quát của một DSL độc lập

Một công cụ xử lý DSL độc lập thường gồm nhiều giai đoạn. Không phải dự án nào cũng cần tất cả thành phần, nhưng việc tách trách nhiệm giúp ngôn ngữ dễ hiểu, kiểm thử và mở rộng.

```text
Tệp DSL
   |
   v
Lexer / Tokenizer
   |
   v
Parser
   |
   v
AST (cây cú pháp trừu tượng)
   |
   v
Phân tích ngữ nghĩa và kiểm tra ràng buộc
   |
   v
Mô hình trung gian (IR) hoặc kế hoạch thực thi
   |
   +--------------------+
   |                    |
   v                    v
Interpreter          Code Generator
   |                    |
   v                    v
Runtime / Engine     Mã nguồn hoặc cấu hình đích
   |                    |
   +---------+----------+
             |
             v
       Kết quả / Báo lỗi
```

### 4.1. Tệp nguồn DSL

Đây là nội dung do người dùng viết, thường được lưu với phần mở rộng riêng như `.pipe`, `.query`, `.flow` hoặc một phần mở rộng do dự án quy định. Phần mở rộng chỉ giúp nhận diện tệp; nó không tự định nghĩa cú pháp hay ngữ nghĩa.

Tệp nguồn có thể chứa một khai báo, nhiều khai báo, chú thích, tham chiếu đến tài nguyên hoặc các chỉ thị import. Quy tắc mã hóa ký tự, quy ước xuống dòng và cách xử lý tệp bao gồm cũng cần được xác định.

### 4.2. Lexer hoặc tokenizer

Lexer đọc chuỗi ký tự và gom chúng thành các token có ý nghĩa từ vựng. Ví dụ:

```text
filter status == "PAID"
```

Có thể được tách thành các token:

```text
FILTER_KEYWORD
IDENTIFIER("status")
EQUAL_EQUAL
STRING("PAID")
```

Lexer thường nhận diện từ khóa, tên định danh, số, chuỗi, toán tử, dấu ngoặc và chú thích. Nó cũng cần ghi nhận vị trí dòng/cột để parser và các giai đoạn sau có thể báo lỗi chính xác.

### 4.3. Parser

Parser nhận chuỗi token và kiểm tra chúng có tuân theo ngữ pháp hay không. Nếu hợp lệ, parser tạo cây cú pháp. Nếu không, nó phát hiện vị trí sai và có thể cố gắng phục hồi để tiếp tục báo thêm lỗi.

Ví dụ, nếu ngữ pháp yêu cầu `filter` theo sau bởi một biểu thức nhưng tệp chỉ có:

```text
filter
```

parser có thể báo thiếu biểu thức sau từ khóa `filter`.

### 4.4. AST — cây cú pháp trừu tượng

AST thể hiện cấu trúc có ý nghĩa của chương trình, bỏ qua nhiều chi tiết trình bày như khoảng trắng hoặc chú thích. Với ví dụ pipeline, AST có thể gồm một nút `Pipeline` chứa nút `Source`, `Filter`, `GroupBy`, `Aggregate` và `Output`.

AST giúp các giai đoạn sau làm việc với cấu trúc rõ ràng thay vì phải thao tác trực tiếp trên chuỗi ký tự. Nó cũng tạo điều kiện kiểm thử parser độc lập với runtime.

### 4.5. Phân tích ngữ nghĩa

Parser chỉ xác nhận cấu trúc phù hợp với ngữ pháp. Một chương trình có thể đúng cú pháp nhưng sai ý nghĩa miền. Ví dụ:

```text
aggregate total = sum(status)
```

Biểu thức này có thể đúng ngữ pháp, nhưng nếu `status` là chuỗi thì hàm `sum` không phù hợp. Bộ phân tích ngữ nghĩa cần kiểm tra tên trường, kiểu dữ liệu, phạm vi tham chiếu, số lượng đối số và các quy tắc miền.

### 4.6. Mô hình trung gian và kế hoạch thực thi

IR (Intermediate Representation) là biểu diễn trung gian giữa cú pháp người dùng và cách thực thi. IR có thể chuẩn hóa các cấu trúc cú pháp khác nhau về cùng một mô hình, làm đơn giản việc tối ưu hóa, sinh mã hoặc thực thi.

Ví dụ, một biểu thức `filter status == "PAID"` có thể được chuyển thành nút IR gồm phép so sánh bằng, tham chiếu trường `status` và hằng chuỗi `PAID`.

### 4.7. Interpreter, compiler và runtime

- **Interpreter (bộ thông dịch):** đọc AST hoặc IR và thực hiện các thao tác trực tiếp.
- **Compiler (bộ biên dịch):** chuyển DSL thành dạng đích khác, chẳng hạn mã Java, SQL hoặc cấu hình cho một engine.
- **Runtime (môi trường thực thi):** cung cấp các dịch vụ cần thiết khi chương trình DSL chạy, như đọc dữ liệu, quản lý tài nguyên, gọi hàm miền và báo lỗi.

Một DSL có thể vừa hỗ trợ thông dịch vừa hỗ trợ sinh mã. Việc lựa chọn phụ thuộc yêu cầu hiệu năng, khả năng gỡ lỗi, môi trường triển khai và độ phức tạp của miền.

## 5. Thiết kế cú pháp riêng

Khi có cú pháp riêng, nhóm thiết kế cần xác định cách người dùng viết các khái niệm miền. Cú pháp cần dễ đọc, nhất quán, có thể phân tích và đủ linh hoạt cho các trường hợp trọng tâm.

### 5.1. Từ khóa, định danh và literal

Một DSL thường có các nhóm thành phần từ vựng:

| Nhóm | Vai trò | Ví dụ |
|---|---|---|
| Từ khóa | Chỉ thị hoặc cấu trúc có ý nghĩa cố định | `pipeline`, `source`, `filter`, `output` |
| Định danh | Tên do người dùng đặt hoặc tham chiếu | `customer_id`, `total_amount` |
| Chuỗi | Giá trị văn bản | `"orders.csv"`, `"PAID"` |
| Số | Giá trị số | `10`, `3.14` |
| Toán tử | Biểu diễn phép so sánh hoặc tính toán | `==`, `!=`, `>=`, `+` |
| Dấu phân cách | Xác định ranh giới cấu trúc | `{`, `}`, `(`, `)`, `,` |
| Chú thích | Ghi chú không tham gia thực thi | `# dữ liệu đơn hàng` |

Quy tắc đặt tên cần được định nghĩa rõ: định danh có phân biệt hoa thường không, có hỗ trợ Unicode không, từ khóa có được dùng làm tên biến không và chuỗi được escape như thế nào.

### 5.2. Ngữ pháp hình thức

Ngữ pháp mô tả cấu trúc câu lệnh hợp lệ. Một phần ngữ pháp đơn giản cho ví dụ pipeline có thể viết bằng EBNF:

```ebnf
pipeline      = "pipeline", string, "{", statement, { statement }, "}" ;
statement     = source
              | filter
              | group_by
              | aggregate
              | output ;
source        = "source", string, [ "format", identifier ] ;
filter        = "filter", expression ;
group_by      = "group_by", identifier, { ",", identifier } ;
aggregate     = "aggregate", identifier, "=", function_call ;
output        = "output", string, [ "format", identifier ] ;
function_call = identifier, "(", expression, ")" ;
expression    = comparison ;
comparison    = identifier, comparison_operator, literal ;
comparison_operator = "==" | "!=" | ">" | "<" | ">=" | "<=" ;
literal       = string | number | "true" | "false" | "null" ;
```

Đây chỉ là ngữ pháp minh họa cho một tập con nhỏ. Ngữ pháp thực tế cần quy định thêm cách viết chuỗi, biểu thức lồng nhau, chú thích, dấu chấm phẩy, thứ tự khai báo và các trường hợp lỗi.

### 5.3. Độ ưu tiên và tính kết hợp của toán tử

Nếu DSL hỗ trợ biểu thức như:

```text
amount > 100 and status == "PAID" or priority == "HIGH"
```

phải xác định `and` và `or` được đánh giá theo thứ tự nào. Nếu không, người dùng có thể hiểu khác với parser. Có thể quy định `and` có độ ưu tiên cao hơn `or`, hoặc yêu cầu ngoặc để làm rõ:

```text
(amount > 100 and status == "PAID") or priority == "HIGH"
```

Quy tắc ưu tiên, kết hợp trái/phải và cách xử lý biểu thức đơn nguyên cần được ghi trong đặc tả ngôn ngữ và có kiểm thử tương ứng.

### 5.4. Cú pháp nên phản ánh miền

Tên từ khóa và cấu trúc nên xuất phát từ từ vựng người dùng hiểu. Nếu người dùng nói “lọc đơn hàng”, cú pháp `filter` có thể phù hợp hơn một tên hàm kỹ thuật khó hiểu. Tuy nhiên, không nên biến mọi thuật ngữ thành từ khóa. Các cấu trúc quá dài hoặc có quá nhiều từ khóa làm DSL khó học và khó mở rộng.

Một cú pháp tốt cân bằng ba yếu tố: khả năng đọc của người dùng, tính nhất quán của ngôn ngữ và độ đơn giản của công cụ phân tích. Cú pháp ngắn nhất chưa chắc dễ hiểu nhất; cú pháp giống ngôn ngữ tự nhiên cũng chưa chắc ít mơ hồ.

## 6. Thiết kế ngữ nghĩa

Ngữ nghĩa xác định một cấu trúc DSL có ý nghĩa gì và công cụ phải xử lý nó ra sao. Cùng một cú pháp có thể được hiểu khác nhau nếu đặc tả ngữ nghĩa không rõ.

### 6.1. Ngữ nghĩa tĩnh và ngữ nghĩa động

- **Ngữ nghĩa tĩnh** được kiểm tra trước khi chạy, chẳng hạn tên trường có tồn tại không, kiểu dữ liệu có tương thích không, biến có được khai báo trong phạm vi không.
- **Ngữ nghĩa động** mô tả hành vi khi thực thi, chẳng hạn phép lọc xử lý `null` thế nào, lỗi đọc tệp có làm dừng pipeline không và thứ tự ghi đầu ra ra sao.

Nên kiểm tra càng nhiều lỗi càng sớm càng tốt nếu có đủ thông tin. Tuy vậy, một số điều kiện chỉ có thể biết lúc chạy, như tệp có tồn tại hay dịch vụ bên ngoài có sẵn sàng hay không.

### 6.2. Hệ thống kiểu

DSL có thể định nghĩa kiểu riêng hoặc ánh xạ sang kiểu của nền tảng. Với DSL xử lý dữ liệu, các kiểu cơ bản có thể gồm:

- `String`: chuỗi ký tự.
- `Integer`: số nguyên.
- `Decimal`: số thập phân có độ chính xác được xác định.
- `Boolean`: đúng hoặc sai.
- `Date` và `DateTime`: ngày và thời điểm.
- `Null`: giá trị không có hoặc chưa được xác định.
- `List<T>`: danh sách các giá trị cùng kiểu hoặc theo quy tắc cho phép.

Hệ thống kiểu giúp kiểm tra toán tử và hàm. Ví dụ, `sum(amount)` chỉ hợp lệ nếu `amount` có kiểu số được hỗ trợ; phép so sánh `date > "tomorrow"` cần có quy tắc chuyển đổi hoặc phải bị từ chối.

### 6.3. Phạm vi tên và tham chiếu

Nếu DSL hỗ trợ biến, hàm, module hoặc alias, cần quy định nơi tên được khai báo và phạm vi có thể tham chiếu. Cần xử lý rõ trường hợp tên trùng, tham chiếu chưa khai báo, import vòng và thứ tự phân giải tên.

Với DSL nhỏ, có thể không cần biến hoặc module. Không nên thêm cơ chế phạm vi chỉ vì ngôn ngữ lập trình tổng quát thường có chúng; chỉ bổ sung khi bài toán cần.

### 6.4. Thứ tự thực thi và lỗi

Ngữ nghĩa cần trả lời các câu hỏi:

- Các câu lệnh được thực hiện theo thứ tự văn bản hay theo đồ thị phụ thuộc?
- Nếu một bước thất bại, các bước tiếp theo có chạy không?
- Có cơ chế thử lại không, và thử lại có thể tạo tác dụng phụ trùng lặp không?
- Kết quả một phần có được giữ lại không?
- Lỗi được gắn với bước, biểu thức hay toàn bộ chương trình?

Những quyết định này đặc biệt quan trọng với DSL điều phối quy trình, build hoặc triển khai hệ thống.

## 7. Quy trình xử lý một tệp DSL

Một luồng xử lý phổ biến có thể mô tả như sau:

1. Đọc tệp nguồn và xác định phiên bản ngôn ngữ.
2. Tokenize nội dung thành token, đồng thời ghi nhận vị trí nguồn.
3. Parse token theo ngữ pháp và tạo AST.
4. Kiểm tra cấu trúc và các quy tắc ngữ nghĩa.
5. Phân giải tên, kiểu dữ liệu, import và tham chiếu tài nguyên.
6. Chuyển AST thành IR hoặc kế hoạch thực thi đã chuẩn hóa.
7. Thực thi IR hoặc sinh mã/cấu hình đích.
8. Thu thập kết quả, cảnh báo và lỗi để hiển thị cho người dùng.

Không phải DSL nào cũng cần một giai đoạn IR riêng. Với ngôn ngữ nhỏ, parser có thể tạo trực tiếp cấu trúc dữ liệu mà interpreter sử dụng. Với DSL lớn, IR thường hữu ích vì tách cú pháp bề mặt khỏi runtime và cho phép tối ưu hóa hoặc hỗ trợ nhiều backend.

## 8. Ví dụ xử lý từ văn bản đến kết quả

Xét biểu thức:

```text
filter status == "PAID"
```

### 8.1. Token

Lexer có thể tạo chuỗi token:

```text
FILTER
IDENTIFIER("status")
EQ_EQ
STRING("PAID")
```

### 8.2. AST minh họa

Parser tạo một nút biểu thức:

```text
FilterNode
  predicate:
    EqualsExpression
      left: FieldReference("status")
      right: StringLiteral("PAID")
```

### 8.3. Kiểm tra ngữ nghĩa

Bộ kiểm tra tra cứu lược đồ của nguồn dữ liệu và xác nhận:

- Trường `status` tồn tại.
- Kiểu của trường có thể so sánh với chuỗi.
- Toán tử `==` được phép cho cặp kiểu này.
- Biểu thức trả về kiểu Boolean.

Nếu `status` không tồn tại, công cụ báo lỗi ngữ nghĩa tại vị trí tham chiếu thay vì đợi đến lúc chạy.

### 8.4. Thực thi

Interpreter duyệt các bản ghi và chỉ giữ bản ghi thỏa biểu thức. Quy tắc với giá trị `null` phải được đặc tả. Ví dụ, DSL có thể dùng logic ba giá trị và loại bản ghi khi kết quả điều kiện là `UNKNOWN`; một DSL khác có thể quy định hành vi riêng. Điều quan trọng là hành vi đó nhất quán và được kiểm thử.

## 9. Các cách triển khai DSL độc lập

Có nhiều lựa chọn để xây dựng parser và công cụ xử lý. Nên chọn theo độ phức tạp ngữ pháp, năng lực nhóm, ngôn ngữ triển khai và yêu cầu bảo trì.

### 9.1. Parser viết thủ công

Với DSL nhỏ, nhóm có thể viết lexer và parser thủ công. Một số kỹ thuật phổ biến là recursive descent và Pratt parser.

Ưu điểm:

- Kiểm soát trực tiếp cách phân tích và thông báo lỗi.
- Có thể bắt đầu với một tập cú pháp nhỏ.
- Không cần phụ thuộc vào công cụ sinh parser lớn.

Hạn chế:

- Dễ phát sinh lỗi khi ngữ pháp tăng độ phức tạp.
- Cần tự duy trì quy tắc ưu tiên toán tử, phục hồi lỗi và vị trí nguồn.
- Ngữ pháp có thể khó đọc nếu logic parser phân tán trong mã.

### 9.2. Dùng parser generator

Parser generator nhận một đặc tả ngữ pháp và sinh mã phân tích. Ví dụ công cụ trong hệ sinh thái JVM có ANTLR và JavaCC.

Ưu điểm:

- Ngữ pháp được mô tả tập trung.
- Có thể sinh parser và một số cấu trúc hỗ trợ như visitor/listener.
- Phù hợp với ngôn ngữ có nhiều quy tắc cú pháp.

Hạn chế:

- Nhóm cần học cách viết và gỡ lỗi ngữ pháp của công cụ.
- Cấu hình sinh mã và phiên bản công cụ cần được quản lý.
- Thông báo lỗi mặc định có thể cần tùy chỉnh để phù hợp với thuật ngữ miền.

### 9.3. Dùng định dạng có sẵn làm cú pháp

Một DSL có thể sử dụng YAML, JSON, XML hoặc TOML làm cú pháp bề mặt. Khi đó, thư viện parser của định dạng đảm nhiệm việc đọc cấu trúc cơ bản; nhóm tập trung định nghĩa schema và ngữ nghĩa miền.

Ví dụ cấu hình YAML:

```yaml
pipeline:
  name: customer-revenue
  source:
    path: orders.csv
    format: csv
  steps:
    - filter:
        field: status
        operator: equals
        value: PAID
    - group_by:
        fields: [customer_id]
    - aggregate:
        name: total
        function: sum
        field: amount
  output:
    path: customer-revenue.csv
    format: csv
```

Định dạng có sẵn giúp tận dụng parser và công cụ phổ biến. Tuy nhiên, YAML hay JSON chỉ cung cấp cú pháp cấu trúc dữ liệu; chúng không tự định nghĩa ngữ nghĩa pipeline. Nhóm vẫn cần schema, validator, quy tắc tham chiếu, kiểm tra kiểu và cơ chế thực thi.

### 9.4. Chọn chiến lược thực thi

Sau khi phân tích, DSL có thể được xử lý theo nhiều cách:

| Chiến lược | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Interpreter | Duyệt AST/IR và thực hiện từng thao tác | Ngôn ngữ nhỏ, cần phản hồi nhanh, dễ gỡ lỗi |
| Sinh mã | Chuyển DSL thành mã của ngôn ngữ hoặc nền tảng khác | Có runtime đích mạnh hoặc muốn tận dụng compiler có sẵn |
| Sinh cấu hình | Chuyển DSL thành JSON/YAML/XML hoặc định dạng công cụ khác | DSL đóng vai trò lớp mô tả thân thiện cho hệ thống hiện hữu |
| Lập kế hoạch | Tạo đồ thị hoặc kế hoạch, sau đó engine thực hiện | Truy vấn, pipeline dữ liệu và hệ thống điều phối |

Các chiến lược có thể kết hợp. Chẳng hạn, DSL có thể được phân tích thành IR, tối ưu hóa rồi chuyển thành truy vấn SQL cho cơ sở dữ liệu.

## 10. Tổ chức dự án cho DSL độc lập

Với một dự án triển khai bằng Java, có thể chia thành các phần theo trách nhiệm:

```text
my-dsl/
├── grammar/
│   └── Pipeline.g4
├── src/main/java/
│   └── example/dsl/
│       ├── frontend/
│       │   ├── SourceLoader.java
│       │   ├── AstBuilder.java
│       │   └── Diagnostic.java
│       ├── model/
│       │   ├── Pipeline.java
│       │   ├── Step.java
│       │   └── Expression.java
│       ├── validation/
│       │   ├── SemanticAnalyzer.java
│       │   └── TypeChecker.java
│       ├── ir/
│       │   └── PipelinePlan.java
│       ├── runtime/
│       │   └── PipelineExecutor.java
│       └── Main.java
├── src/test/
│   └── ...
└── examples/
    └── customer-revenue.pipe
```

Đây là cách tổ chức tham khảo, không phải cấu trúc bắt buộc. Dự án nhỏ có thể gộp các package; dự án lớn có thể tách frontend, compiler, runtime và công cụ IDE thành module riêng.

Điểm quan trọng là không để mọi trách nhiệm nằm trong một lớp xử lý chuỗi lớn. Lexer/parser nên tập trung vào cú pháp; semantic analyzer xử lý quy tắc miền; runtime thực hiện thao tác; lớp giao diện dòng lệnh hoặc API điều phối các bước và hiển thị chẩn đoán.

## 11. Tích hợp DSL độc lập với ứng dụng

DSL độc lập về cú pháp vẫn cần một nơi sử dụng và một cách kết nối với hệ thống. Có thể tích hợp theo một số mô hình:

### 11.1. Công cụ dòng lệnh

Người dùng chạy một lệnh để kiểm tra hoặc thực thi tệp DSL:

```bash
domain-tool validate customer-revenue.pipe
domain-tool run customer-revenue.pipe
```

CLI phù hợp với pipeline CI/CD, script tự động hóa và người dùng kỹ thuật. Cần có mã thoát rõ ràng, thông báo lỗi dễ đọc, tùy chọn cấu hình và cách xuất log.

### 11.2. API trong ứng dụng

Một ứng dụng có thể gọi thư viện DSL để phân tích hoặc thực thi nội dung:

```java
String source = Files.readString(Path.of("customer-revenue.pipe"));
PipelinePlan plan = dslCompiler.compile(source);
PipelineResult result = pipelineEngine.execute(plan);
```

Đây là ví dụ minh họa. Ứng dụng chủ sử dụng API của công cụ DSL nhưng người dùng vẫn viết nội dung bằng cú pháp DSL riêng.

### 11.3. Dịch vụ xử lý DSL

Một dịch vụ trung tâm có thể nhận tệp DSL qua API, kiểm tra và trả kết quả hoặc trạng thái thực thi. Cách này hữu ích khi nhiều nhóm dùng chung một engine. Cần xác định xác thực, phân quyền, giới hạn tài nguyên, lưu vết và cách xử lý phiên bản ngôn ngữ.

### 11.4. Tích hợp vào IDE hoặc trình soạn thảo

Để DSL dễ dùng, có thể bổ sung:

- Syntax highlighting để phân biệt từ khóa, định danh và literal.
- Formatter để chuẩn hóa cách trình bày.
- Autocomplete cho từ khóa, tên trường và hàm miền.
- Kiểm tra lỗi trực tiếp khi người dùng gõ.
- Điều hướng đến khai báo và tài liệu.
- Language Server Protocol (LSP) để dùng lại dịch vụ ngôn ngữ trong nhiều editor.

Các tiện ích này không thay đổi ngữ nghĩa DSL nhưng ảnh hưởng lớn đến trải nghiệm phát triển và khả năng áp dụng.

## 12. Quản lý phiên bản và khả năng tương thích

Khi DSL được nhiều người sử dụng, cú pháp và ngữ nghĩa sẽ tiến hóa. Thay đổi có thể làm tệp cũ không còn phân tích được hoặc tạo kết quả khác trước. Vì vậy, nên có chính sách phiên bản từ sớm.

Một số quyết định cần làm rõ:

- Cách khai báo phiên bản trong tệp hoặc metadata.
- Phiên bản công cụ nào hỗ trợ phiên bản ngôn ngữ nào.
- Quy tắc xử lý cú pháp cũ đã bị thay thế.
- Có công cụ chuyển đổi tệp DSL cũ sang phiên bản mới không.
- Thay đổi nào được xem là tương thích và thay đổi nào cần migration.
- Cách kiểm thử lại các tệp DSL đã lưu khi nâng cấp engine.

Ví dụ khai báo phiên bản:

```text
language_version 1

pipeline "customer-revenue" {
    source "orders.csv"
    filter status == "PAID"
}
```

Không nhất thiết phải có từ khóa phiên bản trong mọi DSL; metadata bên ngoài cũng có thể thực hiện vai trò đó. Nhưng cách xác định phiên bản cần nhất quán và có thể truy vết.

## 13. Bảo mật và độ tin cậy

Một DSL có cú pháp giới hạn có thể giúp kiểm soát khả năng người dùng yêu cầu hệ thống thực hiện. Tuy nhiên, **có DSL riêng không tự động làm cho việc thực thi an toàn**. Rủi ro phụ thuộc vào các thao tác mà DSL cho phép và cách runtime thực hiện chúng.

Những điểm cần thiết kế:

- Chỉ cung cấp các thao tác miền được cho phép; tránh thực thi mã tùy ý nếu không có nhu cầu và cơ chế cô lập phù hợp.
- Kiểm tra quyền truy cập vào tệp, cơ sở dữ liệu, dịch vụ mạng và tài nguyên trước khi thực thi.
- Chuẩn hóa và kiểm soát đường dẫn để tránh truy cập ngoài vùng được phép.
- Không đặt bí mật như mật khẩu hoặc token trực tiếp trong tệp DSL; dùng cơ chế quản lý secret của môi trường.
- Giới hạn thời gian, bộ nhớ, số bản ghi, số bước và mức độ song song khi xử lý đầu vào không tin cậy.
- Kiểm tra dữ liệu và kiểu trước khi gọi backend hoặc sinh câu lệnh cho hệ thống khác.
- Tránh nối chuỗi đầu vào DSL trực tiếp vào câu SQL hoặc lệnh hệ điều hành; dùng API có tham số và cơ chế escape phù hợp.
- Ghi log đủ để truy vết nhưng không làm lộ dữ liệu nhạy cảm.

Nếu DSL có thể gọi hàm mở rộng hoặc plugin, cần có chính sách đăng ký, phân quyền và kiểm soát phiên bản của các hàm đó.

## 14. Kiểm thử DSL độc lập

Kiểm thử nên bao phủ cả ngữ pháp, ngữ nghĩa và hành vi thực thi.

| Nhóm kiểm thử | Nội dung | Ví dụ |
|---|---|---|
| Lexer | Nhận diện token và vị trí | Chuỗi có escape, số thập phân, chú thích |
| Parser | Xây dựng AST đúng với cú pháp | Pipeline thiếu dấu `}` phải báo lỗi |
| AST | Cấu trúc cây phản ánh đúng nguồn | Nút `Filter` có biểu thức điều kiện phù hợp |
| Semantic analysis | Phát hiện tham chiếu hoặc kiểu không hợp lệ | Trường không tồn tại, `sum` nhận chuỗi |
| Runtime | Kết quả xử lý đúng | Pipeline tạo tổng doanh thu mong đợi |
| Error handling | Chẩn đoán rõ và ổn định | Lỗi chỉ đúng dòng/cột và khái niệm miền |
| Compatibility | Tệp cũ vẫn được xử lý theo chính sách | Chạy bộ ví dụ của phiên bản ngôn ngữ trước |
| Security | Từ chối thao tác vượt quyền | Đường dẫn ngoài vùng cho phép bị chặn |

Nên duy trì bộ ví dụ miền làm bộ kiểm thử hồi quy. Mỗi khi thay đổi grammar, semantic analyzer hoặc runtime, hãy chạy lại các ví dụ đã được xác nhận để phát hiện thay đổi hành vi ngoài ý muốn.

## 15. Ưu điểm và chi phí của DSL độc lập

### 15.1. Ưu điểm

- **Cú pháp sát miền:** có thể chọn cách diễn đạt phù hợp với người dùng và thuật ngữ chuyên môn.
- **Giảm phụ thuộc vào ngôn ngữ chủ:** người viết không nhất thiết phải biết Java, Python hoặc một ngôn ngữ cụ thể.
- **Tách mô tả khỏi triển khai:** cùng một tệp DSL có thể được xử lý bởi các backend khác nhau nếu chúng tuân theo cùng ngữ nghĩa.
- **Kiểm soát tập thao tác:** công cụ chỉ cần hỗ trợ những biểu thức đã định nghĩa.
- **Có thể kiểm tra chuyên sâu:** parser và semantic analyzer có thể đưa ra chẩn đoán gắn với khái niệm miền.
- **Có thể phục vụ nhiều công cụ:** định dạng DSL có thể được dùng trong CLI, IDE, CI/CD hoặc dịch vụ.

### 15.2. Chi phí và hạn chế

- **Chi phí xây dựng cao hơn:** cần thiết kế cú pháp, ngữ nghĩa, parser, thông báo lỗi và runtime.
- **Phải duy trì công cụ riêng:** formatter, autocomplete, debugger hoặc language server có thể cần đầu tư thêm.
- **Đường cong học tập:** người dùng phải học một ngôn ngữ mới và hiểu quy tắc của nó.
- **Nguy cơ thiết kế sai:** cú pháp hoặc mô hình miền không phù hợp có thể làm người dùng khó biểu đạt nhu cầu.
- **Tương thích lâu dài:** thay đổi grammar và semantics có thể ảnh hưởng các tệp DSL đã tồn tại.
- **Tích hợp phức tạp:** cần kết nối với dữ liệu, API, runtime và quyền của hệ thống bên ngoài.

## 16. Khi nào nên chọn DSL độc lập?

DSL độc lập thường đáng cân nhắc khi:

1. Người dùng chính không phải lập trình viên của ngôn ngữ chủ và cần cách biểu đạt dễ tiếp cận hơn.
2. Miền có từ vựng, cấu trúc và quy tắc đủ đặc thù để cú pháp riêng tạo ra lợi ích rõ ràng.
3. Cùng một mô tả cần được dùng bởi nhiều ứng dụng hoặc nền tảng khác nhau.
4. Cần kiểm soát chặt tập biểu thức mà người dùng được phép khai báo.
5. Có nhu cầu kiểm tra, phân tích hoặc chuyển đổi mô tả trước khi thực thi.
6. Dự án có đủ nguồn lực để xây dựng và duy trì parser, ngữ nghĩa, runtime và công cụ hỗ trợ.

DSL độc lập có thể chưa phù hợp nếu:

- Công việc chỉ có vài biểu thức đơn giản và API của ngôn ngữ chủ đã đủ rõ.
- Người dùng đều là lập trình viên thành thạo ngôn ngữ chủ.
- Miền thay đổi liên tục đến mức khó ổn định khái niệm và quy tắc.
- Không có đủ tình huống thực tế để xác định cú pháp và ngữ nghĩa.
- Chi phí duy trì một ngôn ngữ riêng lớn hơn lợi ích mà nó mang lại.

Trong trường hợp chưa chắc chắn, nhóm có thể tạo nguyên mẫu nhỏ với một vài ví dụ đại diện. Hãy so sánh cách viết bằng DSL độc lập với cách viết bằng API hoặc cấu hình hiện tại theo tiêu chí dễ đọc, khả năng kiểm tra, độ linh hoạt và chi phí bảo trì.

## 17. Quy trình thiết kế DSL độc lập

Một quy trình thực hiện có thể gồm:

1. **Xác định bài toán và người dùng.** Ghi rõ công việc cần hỗ trợ, khó khăn hiện tại và đối tượng sẽ viết hoặc đọc DSL.
2. **Thu thập ví dụ miền.** Bao gồm trường hợp thông thường, biến thể, trường hợp biên và đầu vào không hợp lệ.
3. **Xây dựng mô hình miền.** Xác định khái niệm, thuộc tính, quan hệ, thao tác và quy tắc.
4. **Xác định phạm vi ngôn ngữ.** Chọn những khả năng cần hỗ trợ và nêu rõ phần nằm ngoài phạm vi.
5. **Thiết kế cú pháp bề mặt.** Chọn từ khóa, biểu thức, cách đặt tên, cấu trúc tệp và quy tắc ngữ pháp.
6. **Đặc tả ngữ nghĩa.** Định nghĩa kiểu, phạm vi tên, thứ tự xử lý, hành vi lỗi và kết quả của từng cấu trúc.
7. **Chọn kiến trúc xử lý.** Quyết định parser, AST, IR, interpreter hoặc code generator theo nhu cầu.
8. **Tạo nguyên mẫu.** Xử lý một tập ví dụ nhỏ xuyên suốt từ văn bản DSL đến kết quả.
9. **Kiểm thử với người dùng và ví dụ thật.** Kiểm tra khả năng đọc, mức độ biểu đạt, lỗi và kết quả.
10. **Bổ sung công cụ và tài liệu.** Tạo CLI, formatter, hướng dẫn, ví dụ và chẩn đoán hữu ích.
11. **Quản lý phiên bản và phát hành.** Xác định tương thích, migration, quy trình nâng cấp và hỗ trợ.

Các bước này thường lặp lại. Khi người dùng thử cú pháp, nhóm có thể phát hiện khái niệm miền chưa rõ. Khi runtime được xây dựng, nhóm có thể nhận ra ngữ nghĩa cần được điều chỉnh. Mỗi thay đổi cần được kiểm chứng bằng ví dụ và ghi lại trong đặc tả.

## 18. Những sai lầm thường gặp

### 18.1. Tạo ngôn ngữ mới chỉ vì có thể

Một parser riêng và cú pháp lạ mắt không tự tạo ra giá trị. Nếu API hiện tại đã dễ đọc, dễ kiểm tra và phù hợp với người dùng, DSL độc lập có thể chỉ làm tăng chi phí.

### 18.2. Thiết kế cú pháp trước khi hiểu miền

Nếu bắt đầu bằng việc chọn dấu ngoặc và từ khóa, nhóm có thể ép khái niệm miền vào một cấu trúc không phù hợp. Cần có ví dụ và mô hình miền làm cơ sở trước khi chốt grammar.

### 18.3. Chỉ kiểm tra cú pháp

Một tệp parse thành công chưa chắc hợp lệ về miền. Cần kiểm tra tên, kiểu, quan hệ, quyền và các ràng buộc khác trước khi thực thi.

### 18.4. Để logic miền nằm trong parser

Parser nên tập trung vào cấu trúc cú pháp. Nếu logic kiểm tra kiểu, truy cập dữ liệu hoặc thực thi được đặt trực tiếp trong parser, mã dễ rối và khó kiểm thử. Nên tách các giai đoạn theo trách nhiệm.

### 18.5. Không thiết kế thông báo lỗi

Người dùng DSL thường không đọc được mã nguồn parser. Lỗi nên dùng thuật ngữ miền, chỉ vị trí nguồn và giải thích cách sửa. Thông báo “syntax error” chung chung thường không đủ hữu ích.

### 18.6. Bỏ qua phiên bản

Khi DSL được dùng trong nhiều tệp và quy trình, thay đổi ngữ nghĩa có thể ảnh hưởng kết quả. Cần có chính sách tương thích và bộ kiểm thử hồi quy.

### 18.7. Coi DSL là ranh giới bảo mật hoàn chỉnh

Giới hạn cú pháp không thay thế việc kiểm soát quyền, tài nguyên và thao tác runtime. Một câu lệnh hợp lệ vẫn có thể gây tác động lớn nếu runtime cho phép truy cập quá rộng.

## 19. Câu hỏi tự kiểm tra

1. DSL độc lập là gì? Từ “độc lập” nói đến khía cạnh nào của ngôn ngữ?
2. Phân biệt DSL nội bộ với DSL độc lập bằng cú pháp, parser và cách tích hợp.
3. Vì sao một DSL độc lập vẫn có thể được triển khai bằng Java và chạy trong ứng dụng Java?
4. Trình bày vai trò của lexer, parser, AST, semantic analyzer, IR và runtime trong kiến trúc DSL.
5. Một biểu thức có thể đúng cú pháp nhưng sai ngữ nghĩa như thế nào? Hãy đưa ra ví dụ.
6. Nêu hai cách triển khai parser cho DSL độc lập và một ưu điểm, hạn chế của mỗi cách.
7. Khi nào nên dùng YAML hoặc JSON làm cú pháp bề mặt cho DSL? Vì sao vẫn cần kiểm tra ngữ nghĩa miền?
8. Hãy đề xuất một DSL độc lập cho một miền bạn biết, viết một ví dụ cú pháp và mô tả cách công cụ xử lý nó.
