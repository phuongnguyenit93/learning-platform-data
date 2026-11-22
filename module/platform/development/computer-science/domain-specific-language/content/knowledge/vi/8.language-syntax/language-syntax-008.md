# Khoảng trắng và chú thích

## Vai trò của khoảng trắng và chú thích trong cú pháp DSL

Khi thiết kế ngôn ngữ chuyên miền (domain-specific language, DSL), nhóm phát triển thường tập trung vào từ khóa, biểu thức, kiểu dữ liệu và cấu trúc câu lệnh. Tuy nhiên, khoảng trắng và chú thích cũng là một phần của cú pháp tổng thể. Chúng ảnh hưởng đến cách lexer nhận diện token, cách parser xác định ranh giới câu lệnh, khả năng đọc của mã nguồn, thông báo lỗi và trải nghiệm sử dụng ngôn ngữ.

**Khoảng trắng (whitespace)** là các ký tự dùng để phân tách hoặc trình bày nội dung, thường gồm dấu cách, tab, xuống dòng và ký tự trả về đầu dòng. **Chú thích (comment)** là phần văn bản được đặt trong mã nguồn để giải thích ý định, cung cấp tài liệu hoặc ghi chú cho người đọc. Trong nhiều DSL, chú thích không trực tiếp tham gia vào ngữ nghĩa thực thi, nhưng một số loại chú thích có thể được công cụ sử dụng làm metadata hoặc chỉ thị.

Đặc tả DSL cần trả lời rõ:

- Khoảng trắng nào được chấp nhận?
- Khoảng trắng có ý nghĩa phân tách token, kết thúc câu lệnh hay xác định cấu trúc khối không?
- Có cho phép nhiều dòng và dòng trống ở mọi vị trí không?
- Tab được xử lý như dấu cách hay có ý nghĩa riêng?
- Comment có dạng một dòng, nhiều dòng hoặc tài liệu không?
- Comment có thể xuất hiện ở đâu và có thể lồng nhau không?
- Comment có bị loại bỏ hoàn toàn hay được giữ lại để phục vụ tài liệu và công cụ?
- Formatter có được phép thay đổi cách xuống dòng và thụt lề mà vẫn bảo toàn ý nghĩa không?

Những quy tắc này nên được xác định trước khi triển khai lexer và parser. Nếu mỗi thành phần tự xử lý khoảng trắng theo một cách khác nhau, cùng một tệp DSL có thể được phân tích hoặc hiển thị không nhất quán.

## Khoảng trắng là gì?

Trong văn bản nguồn, khoảng trắng là các ký tự thường không hiển thị thành ký hiệu riêng khi đọc. Các ký tự phổ biến gồm:

| Ký tự | Tên | Cách dùng thường gặp |
|---|---|---|
| Space (` `) | Dấu cách | Phân tách từ khóa, định danh, literal và toán tử |
| Tab (`\t`) | Tab ngang | Thụt lề hoặc căn chỉnh nội dung |
| LF (`\n`) | Line Feed | Kết thúc dòng trên nhiều hệ thống hiện đại |
| CR (`\r`) | Carriage Return | Thường xuất hiện cùng LF trong CRLF |
| CRLF (`\r\n`) | Kết thúc dòng kiểu Windows | Biểu diễn một lần xuống dòng |
| Form feed (`\f`) | Ngắt trang | Hiếm dùng trong DSL hiện đại; cần quy định nếu chấp nhận |

Unicode còn định nghĩa nhiều ký tự có tính chất khoảng trắng khác, chẳng hạn non-breaking space. Một DSL có thể chỉ chấp nhận tập ký tự khoảng trắng ASCII để giảm nhầm lẫn, hoặc hỗ trợ một tập Unicode được xác định rõ. Không nên để hành vi phụ thuộc vào việc một thư viện runtime có coi ký tự nào đó là whitespace hay không.

### Khoảng trắng giữa các token

Trong phần lớn ngôn ngữ, khoảng trắng được dùng để tách các token. Ví dụ:

```text
WHEN order.total >= 1000000
```

Lexer có thể nhận diện các token `WHEN`, `order`, `.`, `total`, `>=` và `1000000` nhờ quy tắc từ vựng cùng các dấu phân cách. Nhiều dấu cách liên tiếp thường tương đương một dấu cách:

```text
WHEN    order.total    >=    1000000
```

Nếu DSL quy định khoảng trắng giữa token là không đáng kể, hai cách viết trên có cùng cấu trúc và ngữ nghĩa. Formatter có thể chuẩn hóa chúng về một cách trình bày thống nhất.

Tuy nhiên, khoảng trắng có thể cần thiết để phân tách hai chuỗi ký tự vốn có thể bị hiểu thành một token. Ví dụ, `order total` có thể là hai định danh, còn `ordertotal` là một định danh duy nhất. Tương tự, `>=` có thể là một toán tử, trong khi `> =` có thể là hai token khác nhau hoặc là lỗi cú pháp tùy grammar.

### Khoảng trắng bên trong literal

Khoảng trắng bên trong chuỗi ký tự thường là dữ liệu và phải được giữ nguyên:

```text
message = "Payment is waiting for confirmation"
```

Chuỗi có một dấu cách giữa các từ. Nếu lexer hoặc preprocessor tự ý xóa mọi khoảng trắng, giá trị sẽ bị thay đổi thành `Paymentiswaitingforconfirmation`, làm sai dữ liệu.

Khoảng trắng trong literal số, ngày tháng hoặc đơn vị cần được quy định riêng. Ví dụ, DSL có thể cho phép `1000 VND` như một giá trị tiền tệ, nhưng không cho phép `1 000 VND` nếu ngữ pháp số không định nghĩa dấu cách phân nhóm hàng nghìn. Người thiết kế không nên suy luận rằng mọi khoảng trắng đều có thể bỏ qua.

### Khoảng trắng quanh toán tử và dấu phân cách

DSL có thể cho phép hoặc khuyến nghị khoảng trắng quanh toán tử để tăng khả năng đọc:

```text
order.total >= minimumTotal
```

So với:

```text
order.total>=minimumTotal
```

Hai cách viết có thể tương đương nếu lexer nhận diện được token `>=` và các định danh ở hai bên. Đặc tả nên nói rõ đây là quy tắc cú pháp bắt buộc hay chỉ là quy ước định dạng. Việc tách hai lớp này giúp parser không phụ thuộc vào phong cách trình bày.

## Hai mô hình xử lý khoảng trắng

Một quyết định quan trọng là khoảng trắng chỉ để trình bày hay còn mang ý nghĩa cấu trúc.

### Khoảng trắng không có ý nghĩa cấu trúc

Trong mô hình này, dấu cách, tab và phần lớn xuống dòng được xem là ký tự phân tách hoặc trivia (thông tin phụ). Parser dựa vào dấu ngoặc, từ khóa, dấu kết thúc câu lệnh và các token khác để xác định cấu trúc.

Ví dụ:

```text
RULE "VIP discount" WHEN customer.segment IS VIP THEN discount.rate = 10%
```

Có thể được trình bày trên nhiều dòng:

```text
RULE "VIP discount"
WHEN customer.segment IS VIP
THEN discount.rate = 10%
```

Nếu ngữ pháp cho phép, cả hai dạng đều biểu diễn cùng một rule. Mô hình này dễ định dạng lại, thuận lợi khi tạo mã và thường ít nhạy với cách người dùng xuống dòng.

Tuy nhiên, DSL vẫn cần một quy tắc kết thúc câu lệnh rõ ràng. Nếu không dùng newline, dấu `;` hoặc cấu trúc khối để phân tách, parser có thể không biết một biểu thức kết thúc ở đâu.

### Khoảng trắng có ý nghĩa cấu trúc

Một số DSL sử dụng xuống dòng để kết thúc câu lệnh hoặc dùng mức thụt lề để biểu diễn khối lệnh. Khi đó, khoảng trắng không chỉ là định dạng mà là thành phần của cú pháp.

Ví dụ một DSL giả định dùng thụt lề:

```text
RULE "VIP discount":
    WHEN customer.segment IS VIP:
        discount.rate = 10%
        shipment.fee = 0
```

Nếu mức thụt lề xác định phạm vi khối, dòng cuối cùng phải có quan hệ thụt lề đúng với dòng mở khối. Một dòng lùi vào sai mức có thể làm thay đổi cấu trúc hoặc gây lỗi parser.

Khi chọn mô hình này, cần xác định:

- Tab và dấu cách có được dùng thay thế nhau không?
- Có yêu cầu số lượng dấu cách cố định cho mỗi cấp không?
- Có cho phép tab trộn với dấu cách không?
- Dòng trống có ảnh hưởng đến mức thụt lề hiện tại không?
- Comment có được phép đứng riêng trong một khối không?
- Dòng nối tiếp biểu thức được nhận diện như thế nào?
- Khi thụt lề sai, thông báo lỗi chỉ ra dòng và cấp khối ra sao?

Mô hình thụt lề có thể tạo cú pháp gọn và dễ đọc, nhưng đòi hỏi lexer hoặc parser theo dõi cấu trúc dòng. Formatter cũng phải giữ đúng quan hệ thụt lề, không thể tùy ý căn chỉnh như trong ngôn ngữ bỏ qua whitespace.

## Vai trò của xuống dòng

Xuống dòng là trường hợp đặc biệt vì nó có thể vừa là khoảng trắng vừa là dấu phân tách câu lệnh. Có một số lựa chọn thiết kế thường gặp.

### Newline chỉ là whitespace

Trong DSL dùng dấu kết thúc câu lệnh hoặc dấu ngoặc, newline có thể tương đương dấu cách:

```text
SET order.priority = "HIGH";
SET shipment.fee = 0;
```

Người dùng có thể xuống dòng giữa biểu thức nếu grammar cho phép. Lexer có thể bỏ qua newline như whitespace thông thường.

### Newline kết thúc câu lệnh

Một DSL có thể quy định mỗi dòng là một câu lệnh, trừ khi biểu thức được nối tiếp bằng dấu hoặc cấu trúc rõ ràng:

```text
SET order.priority = "HIGH"
SET shipment.fee = 0
```

Lexer có thể phát sinh token `NEWLINE` hoặc parser dùng ranh giới dòng để nhận diện câu lệnh. Cần xác định cách xử lý dòng trống, comment cuối dòng và biểu thức nhiều dòng.

### Newline chỉ kết thúc khi biểu thức đã hoàn chỉnh

Một số DSL cho phép biểu thức tiếp tục qua dòng nếu cấu trúc đang mở, chẳng hạn sau toán tử hoặc trong dấu ngoặc:

```text
WHEN order.total >= minimumTotal
  AND customer.segment IS VIP
THEN shipment.fee = 0
```

Ngữ pháp cần quy định trường hợp nào được tiếp tục. Nếu chỉ dựa vào phán đoán của lexer, người dùng có thể gặp hành vi khó đoán khi chuyển một biểu thức từ một dòng sang nhiều dòng.

## Tab, thụt lề và căn chỉnh

Tab thường được dùng để thụt lề, nhưng chiều rộng hiển thị có thể khác nhau giữa editor. Một tab có thể chiếm 2, 4 hoặc 8 cột tùy cấu hình. Nếu DSL dùng indentation có ý nghĩa, khác biệt này có thể gây nhầm lẫn.

### Chọn quy tắc thụt lề

Đối với DSL không dùng indentation làm cú pháp, nhóm có thể khuyến nghị 2 hoặc 4 dấu cách cho mỗi cấp và để formatter chuẩn hóa. Tab có thể được chấp nhận như whitespace nhưng không được xem là một cấp cấu trúc.

Đối với DSL dùng indentation, nên chọn một chính sách nhất quán. Ví dụ:

- Chỉ dùng dấu cách để xác định cấp thụt lề.
- Mỗi cấp tương ứng đúng 4 dấu cách.
- Tab ở đầu dòng cấu trúc bị từ chối hoặc được chuẩn hóa theo quy tắc được công bố.
- Không cho phép trộn tab và dấu cách trong cùng một khối.
- Formatter luôn sinh ra dạng chuẩn.

Chính sách cụ thể có thể khác, nhưng cần tránh trường hợp cùng một tệp hiển thị giống nhau trong editor nhưng parser hiểu khác nhau.

### Căn chỉnh không đồng nghĩa với cấu trúc

Nếu DSL không dùng indentation làm cú pháp, người dùng có thể căn chỉnh dấu `=` hoặc giá trị để dễ đọc:

```text
name        = "VIP"
discount    = 10%
freeShipping = true
```

Các khoảng trắng bổ sung ở giữa có thể chỉ phục vụ trình bày. Parser nên hiểu cấu trúc dựa trên token và dấu phân cách, không dựa vào số cột căn chỉnh. Formatter có thể tạo lại căn chỉnh mà không ảnh hưởng đến ngữ nghĩa.

## Quy tắc comment trong DSL

Comment giúp người đọc hiểu mục đích của quy tắc, giải thích một quyết định nghiệp vụ hoặc ghi chú thông tin liên quan. Cú pháp comment cần đủ đơn giản, dễ nhận diện và không xung đột với toán tử hoặc literal.

### Comment một dòng

Một kiểu phổ biến là bắt đầu comment bằng ký hiệu `#` hoặc `//` và kéo dài đến hết dòng:

```text
# Áp dụng ưu đãi cho khách hàng VIP
RULE "VIP discount"
WHEN customer.segment IS VIP
THEN discount.rate = 10%  # Mức giảm theo chính sách hiện hành
```

Nếu DSL dùng `#`, lexer có thể bỏ qua từ dấu `#` đến trước newline. Nếu dùng `//`, cần xem xét xung đột với toán tử chia hoặc URL trong literal. Không nên chọn ký hiệu comment mà người dùng thường xuyên cần dùng trong biểu thức nếu không có cách escape rõ ràng.

### Comment nhiều dòng

Comment khối thường bắt đầu bằng một dấu mở và kết thúc bằng một dấu đóng:

```text
/*
  Quy tắc này áp dụng cho nhóm khách hàng VIP.
  Không áp dụng cho sản phẩm thuộc chương trình thanh lý.
*/
RULE "VIP discount"
WHEN customer.segment IS VIP
THEN discount.rate = 10%
```

Comment nhiều dòng hữu ích khi cần giải thích một khối quy tắc hoặc tạm thời ghi chú nhiều dòng. Đặc tả phải quy định comment khối có thể đi qua dòng, có được lồng nhau không và hành vi khi thiếu dấu đóng.

### Comment cuối dòng

Comment có thể đứng sau một câu lệnh:

```text
SET retry.limit = 3  # Giới hạn số lần thử lại
```

Nếu newline kết thúc câu lệnh, lexer phải nhận diện comment trước khi xác định phần còn lại của dòng. Comment cuối dòng không nên làm mất dấu kết thúc câu lệnh hoặc thay đổi cách parser nhóm các token phía trước.

### Comment tài liệu

Một số DSL cần comment có cấu trúc để sinh tài liệu hoặc hiển thị mô tả trong IDE. Ví dụ:

```text
/// Áp dụng ưu đãi miễn phí vận chuyển cho khách hàng VIP.
/// Điều kiện: tổng đơn hàng đạt ngưỡng tối thiểu.
RULE "VIP shipping"
WHEN customer.segment IS VIP
THEN shipment.fee = 0
```

Comment tài liệu có thể được gắn với khai báo ngay sau nó. Nếu có loại comment này, cần quy định comment gắn với rule, thuộc tính hay module nào; comment bị ngăn cách bởi dòng trống có còn được gắn hay không; công cụ lấy nội dung nào để sinh tài liệu.

### Comment có chỉ thị cho công cụ

Một số hệ thống dùng comment để truyền chỉ thị đặc biệt, chẳng hạn bỏ qua một cảnh báo, đánh dấu TODO hoặc yêu cầu công cụ sinh mã. Ví dụ giả định:

```text
// dsl:ignore RULE-UNREACHABLE -- Điều kiện được cung cấp từ cấu hình ngoài
RULE "Legacy fallback"
WHEN legacyMode IS true
THEN route = "compatibility"
```

Nếu comment có chỉ thị máy đọc được, nó không còn hoàn toàn là văn bản tự do. Đặc tả cần xác định cú pháp, phạm vi, quyền sử dụng và cách công cụ báo chỉ thị không hợp lệ. Không nên để các chuỗi giống chỉ thị trong comment thông thường vô tình làm thay đổi hành vi.

## Comment có được lồng nhau không?

Comment lồng nhau (nested comments) là trường hợp một comment khối chứa một comment khối khác. Ví dụ:

```text
/* Mô tả ngoài
   /* Ghi chú bên trong */
   Tiếp tục mô tả ngoài
*/
```

Nếu DSL hỗ trợ lồng nhau, lexer phải theo dõi độ sâu comment. Mỗi dấu mở tăng độ sâu và mỗi dấu đóng giảm độ sâu; comment kết thúc khi độ sâu trở về 0. Cần giới hạn độ sâu hoặc xử lý đầu vào quá sâu để tránh tiêu thụ tài nguyên bất thường.

Nếu DSL không hỗ trợ lồng nhau, dấu mở thứ hai có thể được xem là văn bản bình thường bên trong comment, hoặc bị báo lỗi theo quy tắc đã định. Điều này cần được mô tả rõ vì người dùng thường có thói quen đặt một đoạn mã đã comment bên trong một comment khác khi gỡ lỗi.

Một lựa chọn đơn giản là chỉ hỗ trợ comment một dòng và comment khối không lồng nhau. Lựa chọn này dễ triển khai, nhưng người dùng cần hiểu cách xử lý khi muốn tạm vô hiệu hóa một vùng có sẵn comment khối.

## Khoảng trắng và comment trong lexer

Lexer là thành phần chuyển chuỗi ký tự thành token. Nó phải phân biệt token có ý nghĩa với khoảng trắng và comment được bỏ qua hoặc lưu lại.

### Trivia và token stream

Khoảng trắng và comment thường được gọi chung là *trivia*: thông tin phụ không trực tiếp tham gia vào cấu trúc ngữ nghĩa. Một lexer có thể bỏ trivia khi tạo token stream cho parser, nhưng vẫn lưu nó nếu cần formatter, tài liệu hoặc IDE.

Ví dụ nguồn:

```text
RULE "VIP"  # nhóm ưu tiên
WHEN customer.segment IS VIP
THEN discount.rate = 10%
```

Token stream phục vụ parser có thể chỉ chứa `RULE`, chuỗi `"VIP"`, `WHEN`, các token biểu thức và `THEN`. Comment `# nhóm ưu tiên` và khoảng trắng có thể được lưu thành trivia gắn với token hoặc khoảng nguồn.

### Comment không được làm dính hai token

Khi bỏ comment, lexer hoặc preprocessor phải giữ đúng ranh giới token. Ví dụ:

```text
customer/* ghi chú */segment
```

Nếu comment bị xóa thành chuỗi rỗng, kết quả có thể thành `customersegment`, tức một định danh khác. Cách xử lý an toàn thường là coi comment như một vùng phân tách tương đương whitespace, hoặc xử lý comment ở lexer trong khi vẫn giữ token hai bên riêng biệt.

Đặc tả cần quy định comment có thể xuất hiện giữa hai token hay chỉ ở ranh giới token. Với DSL thông thường, cho phép comment tại vị trí whitespace thường dễ sử dụng hơn.

### Thứ tự nhận diện comment và chuỗi literal

Ký hiệu comment có thể xuất hiện bên trong chuỗi. Ví dụ:

```text
url = "https://service.example/api"
message = "Use // to start a comment in this example"
```

Lexer phải nhận diện chuỗi literal theo quy tắc của nó để `//` hoặc `/*` bên trong chuỗi không bị hiểu nhầm là comment. Tương tự, chuỗi escape và raw string cần được xử lý đúng trước khi nhận diện ký hiệu comment nằm trong nội dung literal.

Không nên triển khai comment bằng thao tác xóa chuỗi từ `//` đến hết dòng trên toàn bộ văn bản mà không hiểu trạng thái chuỗi. Cách làm đó có thể phá hỏng URL, nội dung văn bản và biểu thức chứa ký hiệu tương tự.

## Giữ comment trong AST, CST và công cụ

Comment thường không ảnh hưởng đến kết quả thực thi, nhưng có giá trị đối với người đọc và các công cụ phát triển. Việc có giữ chúng hay không phụ thuộc mục tiêu của DSL.

### Bỏ comment sau khi phân tích

Với một DSL cấu hình đơn giản chỉ cần nạp dữ liệu, lexer có thể loại bỏ comment trước khi parser xử lý. Cách này làm AST gọn hơn và giảm bộ nhớ. Tuy nhiên, công cụ không thể khôi phục comment khi định dạng lại hoặc ghi nội dung về tệp.

### Giữ comment như trivia

Một cách phổ biến là giữ comment và khoảng trắng trong cấu trúc phụ, gắn với token hoặc node gần nhất. Parser vẫn làm việc với token ngữ nghĩa, còn formatter và IDE có thể lấy lại trivia để hiển thị hoặc ghi lại nguồn.

### Dùng concrete syntax tree

Concrete Syntax Tree (CST) giữ các chi tiết cú pháp như dấu ngoặc, dấu phân cách, comment và khoảng trắng. Từ CST, hệ thống có thể tạo AST gọn hơn cho phân tích ngữ nghĩa.

Mô hình này hữu ích cho IDE, refactoring, formatter và công cụ chỉnh sửa mã nguồn vì nó giữ được cấu trúc gần với văn bản ban đầu. Đổi lại, CST thường phức tạp và lớn hơn AST.

### Gắn comment tài liệu với khai báo

Nếu comment tài liệu được gắn vào rule hoặc module, frontend cần xác định quy tắc liên kết. Một cách thường dùng là comment tài liệu phải đứng ngay trước khai báo, có thể có một số dòng comment liên tiếp và không có dòng trống ngăn cách. Cách khác là dùng annotation hoặc metadata riêng.

Không nên dựa vào vị trí gần nhất một cách mơ hồ. Nếu comment nằm giữa hai khai báo hoặc sau một block, công cụ phải biết nó mô tả khai báo nào.

## Quy tắc định dạng và phong cách viết

Đặc tả cú pháp mô tả điều gì hợp lệ; quy ước định dạng (style guide) mô tả cách viết được khuyến nghị. Hai lớp này nên được phân biệt.

Ví dụ, parser có thể chấp nhận cả hai dạng:

```text
WHEN order.total>=minimumTotal AND customer.segment IS VIP
```

```text
WHEN order.total >= minimumTotal
  AND customer.segment IS VIP
```

Style guide có thể khuyến nghị dấu cách quanh toán tử, một điều kiện trên mỗi dòng khi biểu thức dài và thụt lề cố định. Formatter tự động có thể chuyển biểu thức về dạng chuẩn.

Một style guide thường quy định:

- Số dấu cách cho mỗi cấp thụt lề.
- Vị trí xuống dòng trong biểu thức dài.
- Khoảng trắng quanh toán tử và sau dấu phẩy.
- Vị trí dấu ngoặc mở và đóng.
- Cách viết tên từ khóa, định danh và literal.
- Vị trí comment đầu dòng và comment cuối dòng.
- Độ dài dòng khuyến nghị nếu cần.
- Cách nhóm các rule, khai báo và phần cấu hình.

Formatter nên ổn định và có tính lặp lại: chạy nhiều lần trên cùng một nguồn đã định dạng không tiếp tục tạo ra thay đổi. Với DSL dùng indentation làm cú pháp, formatter phải bảo toàn cấu trúc khối và không chỉ căn chỉnh theo thẩm mỹ.

## Tác động đến parser và ngữ pháp

Lexer thường xử lý phần lớn whitespace và comment trước khi parser nhận token. Tuy nhiên, nếu newline hoặc indentation mang ý nghĩa, parser cần nhận được thông tin đó.

### Bỏ qua whitespace thông thường

Một lexer có thể bỏ qua dấu cách và tab giữa token, nhưng vẫn giữ newline nếu newline dùng để kết thúc câu lệnh. Ví dụ, grammar có thể mô tả:

```ebnf
program      = { statement, NEWLINE } ;
statement    = assignment | ruleDeclaration ;
assignment   = identifier, "=", expression ;
```

Đây là EBNF minh họa. Nếu newline không có ý nghĩa, token `NEWLINE` có thể không cần xuất hiện trong grammar và dấu phân cách khác phải xác định ranh giới statement.

### Indentation-sensitive lexer

Với DSL dùng indentation, lexer có thể phát sinh token `INDENT` và `DEDENT` khi mức thụt lề tăng hoặc giảm. Parser sau đó xử lý chúng như dấu mở và đóng block.

Ví dụ:

```text
RULE "VIP":
    WHEN customer.segment IS VIP:
        discount.rate = 10%
    ELSE:
        discount.rate = 0%
```

Token stream khái quát:

```text
RULE STRING COLON NEWLINE
INDENT
WHEN ... COLON NEWLINE
INDENT
IDENTIFIER DOT IDENTIFIER ASSIGN NUMBER NEWLINE
DEDENT
ELSE COLON NEWLINE
INDENT
IDENTIFIER DOT IDENTIFIER ASSIGN NUMBER NEWLINE
DEDENT
DEDENT
```

Chi tiết token phụ thuộc lexer và grammar. Cần xử lý dòng trống, comment đầu dòng, dòng nối tiếp và cuối tệp sao cho không phát sinh `INDENT` hoặc `DEDENT` sai.

### Comment trong grammar

Comment thông thường thường không được đưa vào grammar như một cấu trúc ngữ nghĩa. Lexer nhận diện rồi bỏ qua hoặc lưu dưới dạng trivia. Nếu có doc comment hoặc directive comment, chúng có thể được chuyển thành token hoặc metadata riêng để parser và các bước sau xử lý.

Điều quan trọng là xác định loại comment nào ảnh hưởng đến AST hoặc công cụ. Nếu tất cả comment đều bị bỏ trước parser, các bước sau không thể suy ra doc comment hoặc directive từ nguồn gốc trừ khi lexer đã lưu thông tin đó ở nơi khác.

## Vấn đề Unicode và ký tự dễ nhầm

Whitespace Unicode có thể gây ra khác biệt khó nhận biết bằng mắt. Ví dụ, dấu cách thông thường và non-breaking space có thể trông giống nhau nhưng có mã ký tự khác nhau. Một số ký tự zero-width không hiển thị rõ nhưng có thể xuất hiện trong văn bản được sao chép từ web hoặc tài liệu.

DSL cần quyết định:

- Chấp nhận những code point nào làm whitespace.
- Có từ chối ký tự điều khiển hoặc zero-width không.
- Có chuẩn hóa Unicode (ví dụ NFC) trong identifier hay chỉ trong literal.
- Cách hiển thị ký tự không hợp lệ trong diagnostics.
- Formatter có chuyển whitespace Unicode về dạng chuẩn hay không.

Không nên âm thầm chuẩn hóa nội dung chuỗi literal, vì các ký tự đó có thể là dữ liệu có ý nghĩa. Quy tắc chuẩn hóa identifier và quy tắc xử lý string literal cần được phân biệt.

## Tương tác giữa comment, tiền xử lý và chỉ thị

Một DSL có thể có preprocessor xử lý `include`, macro hoặc điều kiện môi trường. Nếu comment được loại bỏ trước khi preprocessor chạy, chỉ thị nằm trong comment sẽ không còn tác dụng. Nếu preprocessor xử lý văn bản trước khi lexer hiểu chuỗi, nó có thể vô tình thay đổi nội dung literal.

Do đó, thứ tự các bước cần được xác định:

1. Nhận diện encoding và chuẩn hóa phần đầu nguồn nếu được phép.
2. Nhận diện chuỗi literal, comment và chỉ thị theo quy tắc từ vựng đã định nghĩa.
3. Xử lý directive hoặc include ở đúng ngữ cảnh.
4. Giữ source map và ranh giới token sau biến đổi.
5. Chuyển token cho parser và các bước phân tích tiếp theo.

Thứ tự cụ thể có thể khác tùy thiết kế. Chẳng hạn, directive có thể là token cú pháp thông thường được parser xử lý, thay vì một tầng preprocessor riêng. Điều quan trọng là tránh xử lý văn bản thuần túy theo kiểu thay thế chuỗi khi chưa phân biệt comment, string và token.

Comment cũng có thể chứa chỉ thị cho formatter hoặc linter. Cần quy định công cụ nào đọc chúng và chúng có tác động đến quá trình build hay không. Một comment `TODO` thường chỉ là ghi chú; một comment `ignore` có thể thay đổi kết quả kiểm tra tĩnh. Hai trường hợp này cần chính sách và phạm vi rõ ràng.

## Ví dụ thiết kế quy tắc whitespace và comment cho một DSL

Giả sử xây dựng DSL khai báo quy tắc đơn hàng. Một đặc tả nhỏ có thể chọn:

- Dấu cách và tab giữa token là không đáng kể.
- Newline kết thúc câu lệnh ở cấp cao nhất.
- Biểu thức có thể tiếp tục dòng sau toán tử logic hoặc khi ngoặc chưa đóng.
- Indentation chỉ dùng để trình bày, không quyết định phạm vi block.
- Comment một dòng bắt đầu bằng `#` và kéo dài đến hết dòng.
- Comment khối dùng `/* ... */`, không hỗ trợ lồng nhau.
- Doc comment bắt đầu bằng `///` và gắn với khai báo tiếp theo nếu không có dòng trống.
- Comment được giữ trong trivia để formatter và IDE sử dụng.
- String literal giữ nguyên mọi khoảng trắng bên trong.

Ví dụ:

```text
/// Miễn phí vận chuyển cho khách hàng VIP đạt ngưỡng.
RULE "VIP shipping"
WHEN order.total >= 1000000 VND
  AND customer.segment IS VIP
THEN shipment.fee = 0 VND  # Không áp dụng với hàng cồng kềnh
```

Một phiên bản khác có thể viết cùng rule trên một dòng hoặc căn lề khác. Nếu grammar không dùng indentation, các cách trình bày này có cùng ý nghĩa. Comment tài liệu vẫn gắn với rule và comment cuối dòng chỉ giải thích action.

Ví dụ grammar rút gọn:

```ebnf
program          = { docComment | statement | NEWLINE } ;
docComment       = DOC_COMMENT, NEWLINE ;
statement        = ruleDeclaration ;
ruleDeclaration  = "RULE", STRING, NEWLINE,
                   "WHEN", expression, NEWLINE,
                   "THEN", action, NEWLINE ;
```

Grammar trên chỉ minh họa cấu trúc cấp cao. Lexer sẽ bỏ qua whitespace thông thường và comment thường, đồng thời lưu doc comment thành token hoặc metadata. Cần bổ sung quy tắc continuation, comment cuối dòng và biểu thức nhiều dòng trong grammar thực tế.

## Thông báo lỗi liên quan đến whitespace và comment

Lỗi whitespace thường khó nhìn thấy vì ký tự gây lỗi có thể vô hình hoặc trông giống ký tự hợp lệ. Diagnostics nên nêu rõ ký tự và vị trí.

Ví dụ thông báo:

```text
rules.dsl:8:1: error DSL-LEX-012
Unexpected indentation: expected 4 spaces, found a tab.
Replace the tab with spaces or run the DSL formatter.
```

Hoặc:

```text
rules.dsl:14:1: error DSL-LEX-021
Unterminated block comment. Expected '*/' before end of file.
```

Nếu một ký tự Unicode không được phép, công cụ có thể hiển thị tên hoặc mã code point của nó để người dùng nhận ra. Với comment chưa đóng, diagnostics nên trỏ đến vị trí mở comment và có thể chỉ thêm vị trí cuối tệp.

Với indentation-sensitive DSL, lỗi thụt lề nên chỉ rõ mức hiện tại và mức mong đợi, thay vì chỉ báo “syntax error”. Nếu tab và dấu cách trộn lẫn, thông báo cần giúp người dùng tìm ra ký tự không hiển thị.

## Kiểm thử whitespace và comment

Các quy tắc whitespace và comment cần có kiểm thử lexer, parser, formatter và tích hợp. Không nên chỉ kiểm tra một ví dụ đơn giản có dấu cách chuẩn.

### Kiểm thử tương đương định dạng

Nếu whitespace không có ý nghĩa cấu trúc, tạo nhiều biến thể trình bày của cùng chương trình và xác nhận chúng tạo ra AST hoặc kết quả tương đương:

```text
WHEN order.total >= 1000 AND customer.active
```

```text
WHEN    order.total>=1000
    AND customer.active
```

```text
WHEN order.total >= 1000
AND customer.active
```

Chỉ những biến thể được grammar cho phép mới cần được xem là tương đương. Nếu newline kết thúc câu lệnh, ví dụ thứ ba có thể không hợp lệ và đó là kết quả cần kiểm tra.

### Kiểm thử literal và ranh giới token

Kiểm tra khoảng trắng trong chuỗi, số, định danh, comment nằm giữa token và ký hiệu comment xuất hiện bên trong chuỗi:

```text
message = "A  B"
url = "https://service.example/path"
name = customer/* note */segment
```

Xác nhận chuỗi giữ nguyên hai dấu cách giữa `A` và `B`; `//` trong URL không mở comment; comment giữa hai token không làm chúng dính thành một token.

### Kiểm thử comment

Bao gồm comment đầu dòng, comment cuối dòng, comment khối nhiều dòng, comment rỗng, comment chưa đóng, ký hiệu comment trong chuỗi và trường hợp lồng nhau nếu được hỗ trợ.

Nếu có doc comment, kiểm tra comment được gắn đúng khai báo, xử lý dòng trống và hành vi khi có nhiều comment liên tiếp.

### Kiểm thử line ending và Unicode

Chạy cùng nội dung với LF và CRLF nếu cả hai được hỗ trợ. Kiểm tra BOM, tab, dấu cách Unicode, ký tự zero-width và vị trí lỗi sau ký tự nhiều byte. Đảm bảo line/column được hiển thị nhất quán trong editor và diagnostics.

### Kiểm thử formatter

Formatter cần bảo toàn ngữ nghĩa, giữ comment ở đúng vị trí và không làm thay đổi string literal. Với DSL dùng indentation, cần kiểm tra formatter không đổi quan hệ khối. Chạy formatter lần thứ hai trên kết quả đã định dạng nên không tạo thêm thay đổi.

## Nguyên tắc thiết kế thực tế

Khi xây dựng quy tắc whitespace và comment, nên ưu tiên tính nhất quán và khả năng dự đoán. Một số nguyên tắc hữu ích:

1. **Phân biệt cú pháp với phong cách:** chỉ biến whitespace thành thành phần cú pháp khi nó thực sự giúp mô hình ngôn ngữ rõ hơn.
2. **Giữ quy tắc đơn giản:** hạn chế nhiều ngoại lệ cho tab, dòng nối tiếp và comment.
3. **Bảo toàn nội dung literal:** không áp dụng thao tác xóa hoặc chuẩn hóa whitespace một cách mù quáng.
4. **Không làm mất ranh giới token:** comment và phép biến đổi nguồn phải giữ được khoảng phân tách cần thiết.
5. **Giữ source location:** lỗi sau preprocessing vẫn cần truy ngược về tệp và vị trí ban đầu.
6. **Tách comment thường khỏi directive:** chỉ những comment có cú pháp đặc biệt được công cụ xử lý như chỉ thị.
7. **Hỗ trợ formatter:** cung cấp cách viết chuẩn để các nhóm chia sẻ và review mã thuận tiện.
8. **Kiểm thử ký tự khó nhìn:** tab, Unicode whitespace, line ending và comment trong string cần được kiểm tra riêng.
9. **Tài liệu hóa hành vi:** người dùng cần biết comment có bị giữ, bị loại bỏ hay được xuất ra tài liệu; khoảng trắng có ý nghĩa ở vị trí nào.

Một DSL dễ đọc không nhất thiết phải chấp nhận mọi loại whitespace Unicode hoặc mọi kiểu comment. Điều quan trọng là tập quy tắc được lựa chọn có chủ đích, được công bố rõ và được công cụ thực thi nhất quán.

## Kết luận

Khoảng trắng và chú thích là thành phần quan trọng của cú pháp tổng thể DSL. Khoảng trắng có thể chỉ dùng để phân tách và trình bày, hoặc mang ý nghĩa cấu trúc thông qua newline và indentation. Comment có thể là ghi chú thuần túy, tài liệu gắn với khai báo hoặc chỉ thị cho công cụ; mỗi loại cần quy tắc riêng.

Lexer và parser phải xử lý đúng ranh giới token, chuỗi literal, comment và dòng mới. Frontend nên giữ trivia, source location và source map khi cần phục vụ diagnostics, formatter và IDE. Một đặc tả rõ ràng cùng bộ kiểm thử cho whitespace, comment, Unicode và định dạng sẽ giúp DSL nhất quán, dễ đọc và dễ bảo trì.
