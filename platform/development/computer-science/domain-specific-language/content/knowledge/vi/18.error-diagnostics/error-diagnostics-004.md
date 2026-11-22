# Vị trí lỗi

Trong một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL), **vị trí lỗi** là thông tin cho biết vấn đề được phát hiện ở đâu trong chương trình hoặc tài liệu nguồn. Một chẩn đoán hữu ích không chỉ nói rằng chương trình sai; nó cần chỉ ra tệp hoặc tài liệu liên quan, đoạn văn bản cần chú ý, vị trí bắt đầu và kết thúc, cùng ngữ cảnh đủ để người dùng hiểu và sửa vấn đề.

Ví dụ, người dùng viết:

~~~text
policy OrderPolicy {
    when order.totla > 1000 then approveOrder;
}
~~~

Nếu kiểu `Order` không có thuộc tính `totla`, thông báo “Unknown property” chỉ thực sự hữu ích khi trỏ đúng vào `totla`, đồng thời có thể dẫn đến khai báo `Order` hoặc gợi ý tên `total`. Nếu chỉ đánh dấu cả tệp hoặc cả dòng, người dùng phải tự tìm vị trí sai. Nếu đánh dấu nhầm sang dấu `>` hoặc một ký tự phía trước, họ có thể sửa nhầm phần chương trình.

Vị trí lỗi được sử dụng xuyên suốt quá trình xử lý DSL: lexer phát hiện ký tự không hợp lệ, parser phát hiện cấu trúc sai, bộ phân giải tên phát hiện tham chiếu không tồn tại, bộ kiểm tra kiểu phát hiện phép toán không tương thích, bộ kiểm tra quy tắc miền phát hiện vi phạm nghiệp vụ và runtime ghi nhận lỗi khi thực thi. IDE, Language Server, formatter, quick fix và hệ thống log đều cần một mô hình vị trí thống nhất.

## 1. Vị trí lỗi là gì?

Vị trí lỗi (*error location* hoặc *diagnostic location*) là vị trí nguồn gắn với một vấn đề được phát hiện trong chương trình. Tùy loại lỗi, vị trí có thể là một điểm, một đoạn văn bản hoặc nhiều vị trí liên quan.

Các dạng phổ biến:

- **Vị trí đơn (point location):** một điểm trong nguồn, thường dùng khi thiếu token tại cuối câu lệnh hoặc cần chèn nội dung ở một vị trí.
- **Đoạn nguồn (source range/span):** một khoảng bắt đầu và kết thúc, thường dùng để tô sáng token, biểu thức hoặc câu lệnh có vấn đề.
- **Vị trí liên quan (related location):** một hoặc nhiều đoạn nguồn giúp giải thích nguyên nhân, chẳng hạn nơi khai báo đầu tiên của một tên bị khai báo trùng.
- **Vị trí nguồn gốc (origin location):** vị trí của macro, template, include hoặc cấu trúc DSL đã tạo ra nút gây lỗi.
- **Vị trí lúc chạy (runtime location):** vị trí của quy tắc hoặc hành động DSL đang được thực thi khi xảy ra lỗi.

Một diagnostic có thể có vị trí chính và nhiều vị trí liên quan. Không phải mọi lỗi đều có vị trí chính xác: lỗi đọc tệp, lỗi cấu hình môi trường hoặc lỗi kết nối dịch vụ có thể chỉ gắn với tài liệu hay thành phần cấu hình, không gắn với một span trong DSL.

### Ví dụ vị trí chính và vị trí liên quan

~~~text
entity Customer {
    id: CustomerId;
}

entity Customer {
    email: EmailAddress;
}
~~~

Nếu DSL cấm khai báo trùng tên `Customer` trong cùng namespace, vị trí chính có thể là tên ở khai báo thứ hai. Vị trí liên quan trỏ đến tên ở khai báo đầu tiên. Diagnostic khi đó giải thích được cả nơi xung đột lẫn nơi đã chiếm tên.

## 2. Phân biệt vị trí lỗi với các khái niệm liên quan

Vị trí lỗi có liên quan đến source position, source span và diagnostic, nhưng các khái niệm này không hoàn toàn đồng nhất.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Source position | Một điểm trong tài liệu nguồn. | Vị trí con trỏ ngay sau `then`. |
| Source range/span | Một đoạn nguồn có điểm bắt đầu và kết thúc. | Toàn bộ tên `totla`. |
| Diagnostic | Bản ghi mô tả một vấn đề. | Lỗi `Unknown property`. |
| Error location | Vị trí chính hoặc các vị trí liên quan của diagnostic. | Span của `totla` và span khai báo `Order`. |
| Stack trace | Chuỗi lời gọi dẫn đến lỗi lúc chạy. | Hàm runtime gọi từ rule `ApproveOrder`. |
| Source map | Ánh xạ vị trí giữa mã được sinh và nguồn DSL. | Dòng Java được ánh xạ về câu lệnh DSL. |

Một diagnostic có thể tồn tại mà không có source span, ví dụ lỗi không thể mở file cấu hình. Một source span cũng có thể được dùng cho tính năng không phải lỗi, chẳng hạn Go to Definition hoặc semantic highlighting.

## 3. Mô hình dữ liệu của vị trí lỗi

Một mô hình diagnostic thường cần nhiều thông tin hơn hai con số offset.

~~~text
Diagnostic
  code
  severity
  message
  primaryLocation
  relatedLocations
  notes
  suggestedFixes
  sourceVersion

DiagnosticLocation
  sourceId
  range
  label

SourceRange
  startOffset
  endOffset
~~~

Các trường này có thể được đặt tên khác nhau trong API, nhưng cần có hợp đồng rõ ràng.

| Trường | Vai trò |
|---|---|
| `code` | Mã ổn định để tra tài liệu, lọc lỗi hoặc viết kiểm thử. |
| `severity` | Mức độ như error, warning, information hoặc hint. |
| `message` | Mô tả vấn đề theo ngôn ngữ người dùng. |
| `primaryLocation` | Đoạn nguồn chính cần được làm nổi bật. |
| `relatedLocations` | Các vị trí khác giúp giải thích vấn đề. |
| `notes` | Thông tin bổ sung hoặc nguyên nhân có thể có. |
| `suggestedFixes` | Các thao tác sửa có thể áp dụng. |
| `sourceVersion` | Phiên bản tài liệu mà vị trí đang tham chiếu đến. |

`sourceId` xác định tệp hoặc tài liệu. Không nên giả định offset 50 của `orders.dsl` có cùng ý nghĩa với offset 50 của `customers.dsl`. Mọi range phải thuộc về một nguồn xác định.

### Mô hình bằng Java

~~~java
record SourceId(String value) {}

record SourceSpan(
    SourceId sourceId,
    int startOffset,
    int endOffset
) {
    SourceSpan {
        if (startOffset < 0 || endOffset < startOffset) {
            throw new IllegalArgumentException("Invalid source span");
        }
    }
}

enum Severity {
    ERROR, WARNING, INFORMATION, HINT
}

record RelatedLocation(String message, SourceSpan span) {}

record Diagnostic(
    String code,
    Severity severity,
    String message,
    SourceSpan primarySpan,
    java.util.List<RelatedLocation> relatedLocations
) {}
~~~

Đây là mô hình minh họa. Trong hệ thống thực tế, cần quy định đơn vị offset, phiên bản tài liệu, khả năng không có primary span, cách lưu notes và cấu trúc code fix. Nếu `SourceSpan` có thể thiếu nguồn hoặc range, nên biểu diễn rõ bằng kiểu tùy chọn thay vì dùng giá trị giả như `0`.

## 4. Khoảng nguồn nửa mở

Một quy ước phổ biến là biểu diễn range bằng khoảng nửa mở `[start, end)`: bắt đầu tại `start` và kết thúc ngay trước `end`.

Ví dụ, với chuỗi:

~~~text
totla
~~~

nếu token bắt đầu ở offset 0 và có 5 đơn vị theo hệ đếm đang dùng, span là `[0, 5)`. Độ dài bằng `end - start`.

Ưu điểm của khoảng nửa mở:

- Độ dài được tính trực tiếp bằng `end - start`.
- Span rỗng được biểu diễn bằng `start == end`.
- Hai đoạn liền nhau có thể là `[0, 5)` và `[5, 9)` mà không chồng lấn.
- Phù hợp với nhiều API cắt chuỗi có chỉ số kết thúc loại trừ.

### Lỗi có span rỗng

Một lỗi cú pháp có thể phát sinh vì thiếu token:

~~~text
when order.total > 1000
~~~

Nếu DSL yêu cầu `then Action;`, parser có thể báo thiếu `then` tại cuối biểu thức. Không có ký tự sai để tô sáng, nên vị trí có thể là span rỗng `[n, n)` ngay sau token cuối cùng. Editor có thể hiển thị dấu chèn tại đó và thông báo “Expected `then`”.

Không nên mở rộng span sang ký tự trước đó chỉ để tránh range rỗng. Vị trí logic nên chính xác; giao diện có thể quyết định cách trình bày.

### Lỗi có span bao trùm

Đôi khi lỗi không nằm ở một token riêng mà ở toàn cấu trúc:

~~~text
transaction {
    reserveInventory(order);
    capturePayment(order);
~~~

Nếu khối chưa đóng khi đến EOF, diagnostic có thể trỏ đến điểm EOF và thêm related location tại dấu `{` mở khối. Cách này cho người dùng biết nơi cần chèn dấu `}` và cấu trúc nào đang chưa hoàn tất.

## 5. Đơn vị tọa độ: byte, Unicode và UTF-16

Một trong những nguyên nhân phổ biến làm vị trí lỗi lệch là các thành phần sử dụng đơn vị tọa độ khác nhau. “Offset 10” có thể là byte thứ 10, code point thứ 10 hoặc UTF-16 code unit thứ 10.

### Byte offset

Byte offset đếm số byte từ đầu dữ liệu đã mã hóa. Với UTF-8, một code point có thể chiếm từ một đến bốn byte. Byte offset phù hợp với parser làm việc trực tiếp trên buffer UTF-8, nhưng không thể dùng trực tiếp làm chỉ số ký tự trong một API UTF-16.

### Unicode code point offset

Code point offset đếm các giá trị mã Unicode. Một ký tự người dùng nhìn thấy có thể gồm nhiều code point, ví dụ chữ cái và dấu kết hợp. Do đó, số code point không nhất thiết bằng số ký tự hiển thị.

### UTF-16 code unit offset

Java và JavaScript biểu diễn chuỗi theo UTF-16 code unit. Một code point ngoài Basic Multilingual Plane (BMP) được biểu diễn bằng cặp surrogate và chiếm hai code unit. Nhiều API editor và giao thức ngôn ngữ cũng dùng UTF-16 cho trường vị trí ký tự.

### Line và column

Vị trí dòng/cột dễ đọc hơn offset, nhưng cần quy định:

- Dòng và cột bắt đầu từ 0 hay 1?
- Cột được đếm bằng byte, code point, UTF-16 code unit hay ô hiển thị?
- Tab được tính là một ký tự hay mở rộng theo tab width?
- CRLF được xem là một newline logic hay hai ký tự điều khiển riêng?
- Ký tự kết hợp được hiển thị và tính cột ra sao?

Không có một quy ước duy nhất phù hợp với mọi lớp. Cần chọn hệ tọa độ nội bộ và chuyển đổi chính xác tại ranh giới API.

| Hệ tọa độ | Đơn vị | Lưu ý |
|---|---|---|
| Byte offset | Byte | UTF-8 có ký tự nhiều byte. |
| Code point offset | Unicode code point | Một ký tự hiển thị có thể gồm nhiều code point. |
| UTF-16 offset | UTF-16 code unit | Code point ngoài BMP chiếm hai đơn vị. |
| Line/column | Dòng và đơn vị cột được quy định | Phải xác định base và cách tính cột. |
| Visual column | Ô hiển thị | Phụ thuộc tab width, font và Unicode. |

## 6. Chuyển offset thành dòng và cột

Compiler thường lưu offset vì nó ổn định và dễ gắn với token. Khi hiển thị diagnostic, công cụ chuyển offset thành dòng và cột.

### Bảng bắt đầu dòng

Một `SourceText` có thể lưu danh sách offset bắt đầu từng dòng:

~~~text
lineStarts = [0, 21, 68, 104, ...]
~~~

Với một offset, tìm phần tử lớn nhất trong `lineStarts` không vượt quá offset đó. Chỉ số phần tử cho biết dòng; cột tương đối được tính từ offset trừ vị trí bắt đầu dòng, sau đó chuyển sang đơn vị mà editor yêu cầu.

Nếu dùng tìm kiếm nhị phân, việc tìm dòng có thể thực hiện trong (O(\log n)), với `n` là số dòng. Với tài liệu lớn và nhiều diagnostic, line index giúp chuyển đổi hiệu quả hơn việc quét từ đầu tệp cho mỗi lỗi.

### LF, CRLF và CR

Tệp văn bản có thể dùng `LF` (`\n`), `CRLF` (`\r\n`) hoặc `CR` (`\r`). Bộ quản lý nguồn cần xử lý đúng các dạng newline. Nếu `CRLF` bị tính thành hai lần xuống dòng, tất cả vị trí phía sau có thể bị lệch. Nếu chỉ nhận diện `LF`, một tệp dùng `CR` đơn có thể cho số dòng sai.

### Tab và cột hiển thị

Tab là một ký tự nhưng có thể chiếm nhiều ô trên màn hình. Nếu tab width là 4, vị trí hiển thị sau tab phụ thuộc cột trước tab. Do đó, cột offset không nên bị đồng nhất với visual column. Parser lưu tọa độ ổn định; editor chịu trách nhiệm tính vị trí hiển thị.

### Unicode kết hợp

Chữ `é` có thể được biểu diễn bằng một code point dựng sẵn hoặc bằng `e` cộng dấu sắc kết hợp. Hai chuỗi nhìn giống nhau nhưng có số đơn vị mã khác nhau. Nếu DSL chuẩn hóa Unicode, cần giữ ánh xạ về văn bản gốc để diagnostic không trỏ sai. Nếu không chuẩn hóa, tất cả thành phần phải dùng cùng chuỗi nguồn và cùng quy ước offset.

## 7. Vị trí lỗi trong từng giai đoạn xử lý DSL

Mỗi giai đoạn phát hiện một loại vấn đề và thường có một cách chọn span phù hợp.

| Giai đoạn | Loại lỗi | Vị trí nên trỏ đến |
|---|---|---|
| Đọc/giải mã nguồn | Encoding không hợp lệ, không đọc được tệp | Byte offset hoặc định danh tài liệu; có thể không có span văn bản. |
| Lexer | Ký tự không hợp lệ, chuỗi escape sai | Ký tự hoặc lexeme gây lỗi. |
| Parser | Thiếu token, token sai vị trí, cấu trúc chưa đóng | Token không hợp lệ, vị trí chèn hoặc cấu trúc bao quanh. |
| Kiểm tra AST | Thiếu trường bắt buộc, sai bội số quan hệ | Nút hoặc khai báo không thỏa cấu trúc. |
| Name resolution | Tên chưa khai báo, trùng tên, tham chiếu mơ hồ | Tham chiếu hoặc khai báo xung đột. |
| Type checking | Sai kiểu, sai số lượng đối số | Biểu thức, toán hạng hoặc đối số không tương thích. |
| Kiểm tra ngữ nghĩa miền | Vi phạm bất biến hoặc chính sách | Cấu trúc hoặc giá trị DSL liên quan đến vi phạm. |
| Runtime | Lỗi khi thực hiện hành động hoặc truy cập dữ liệu | Câu lệnh/rule DSL đã kích hoạt thao tác. |
| Code generation | Không thể sinh cấu trúc đích | Nút AST/IR không được backend hỗ trợ. |

### Lỗi từ vựng

Ví dụ:

~~~text
let amount = 100 @ 5;
~~~

Nếu `@` không phải token hợp lệ trong ngữ cảnh này, lexer nên trỏ đến `@`. Nếu lexer có thể phục hồi và tiếp tục, nó có thể phát token lỗi cùng diagnostic.

### Lỗi cú pháp

~~~text
when order.total > 1000 approveOrder;
~~~

Nếu ngữ pháp yêu cầu `then` giữa điều kiện và hành động, parser có thể trỏ đến `approveOrder` là token xuất hiện khi đang chờ `then`, hoặc dùng span rỗng trước `approveOrder` để chỉ nơi cần chèn từ khóa. Diagnostic nên nói rõ token mong đợi.

### Lỗi phân giải tên

~~~text
when order.totla > 1000 then approveOrder;
~~~

Nếu `totla` không tồn tại trên kiểu `Order`, span chính nên bao trùm `totla`. Có thể thêm gợi ý `total` và related location đến khai báo kiểu `Order`.

### Lỗi kiểu

~~~text
when order.createdAt > 100 then approveOrder;
~~~

Nếu `createdAt` có kiểu `DateTime` còn `100` là `Integer`, diagnostic có thể trỏ đến toán hạng `100` hoặc toàn biểu thức so sánh, tùy cách giải thích lỗi. Một related location có thể trỏ đến khai báo `createdAt` để người dùng thấy kiểu thực tế.

### Vi phạm quy tắc miền

~~~text
approveOrder(order) when order.paymentStatus == PENDING;
~~~

Nếu chính sách miền cấm phê duyệt đơn chưa thanh toán, diagnostic cần trỏ đến điều kiện hoặc hành động gây vi phạm. Nếu vi phạm chỉ xuất hiện với dữ liệu lúc chạy, runtime cần gắn lỗi với rule nguồn và dữ liệu liên quan theo chính sách bảo mật.

## 8. Chọn span chính xác

Vị trí chính nên làm nổi bật phần nhỏ nhất đủ để người dùng hiểu và sửa lỗi. Span quá rộng làm nhiễu; span quá hẹp có thể không giải thích được vấn đề.

### Trỏ đến token sai

Nếu một token không được phép ở vị trí hiện tại, trỏ đến token đó.

~~~text
let total = ) 100;
             ^
~~~

### Trỏ đến vị trí thiếu token

Nếu parser chờ một token nhưng gặp EOF hoặc token kế tiếp, dùng point location hoặc zero-width span ở nơi cần chèn.

~~~text
when order.total > 1000
                        ^ expected `then`
~~~

### Trỏ đến toàn biểu thức

Nếu lỗi thuộc cấu trúc tổng thể, ví dụ toán tử không hợp lệ giữa hai biểu thức hoặc điều kiện không trả về boolean, span của cả biểu thức có thể phù hợp hơn.

### Trỏ đến tên khai báo

Khi có khai báo trùng, vị trí chính thường là tên ở khai báo mới; related location trỏ đến khai báo trước. Khi một tên chưa được khai báo, span chính là tên được tham chiếu.

### Trỏ đến cấu trúc cha khi lỗi không có token cụ thể

Một số lỗi là vi phạm bất biến của toàn khai báo. Ví dụ, một `Policy` bắt buộc phải có ít nhất một rule nhưng danh sách rule rỗng. Span của khai báo policy hoặc vị trí nơi nội dung cần được thêm có thể phù hợp.

## 9. Vị trí chính và vị trí liên quan

Diagnostic nhiều vị trí giúp giải thích các quan hệ giữa những đoạn nguồn.

### Khai báo trùng

~~~text
entity Order { ... }
entity Order { ... }
~~~

Vị trí chính: tên `Order` ở khai báo thứ hai. Vị trí liên quan: tên `Order` ở khai báo đầu tiên, kèm nhãn “First declaration is here”.

### Tham chiếu sai kiểu

~~~text
let createdAt: DateTime;
let age: Integer = createdAt;
~~~

Vị trí chính: biểu thức `createdAt` ở phép gán. Vị trí liên quan: khai báo `createdAt`, nơi kiểu `DateTime` được xác định.

### Gọi hàm sai số lượng đối số

~~~text
function send(to: Email, subject: Text, body: Text);

send("ops@example.test", "Alert");
~~~

Vị trí chính có thể là toàn lời gọi `send(...)`, vì lỗi liên quan đến số lượng đối số. Related location trỏ đến khai báo hàm để người dùng xem chữ ký mong đợi.

### Chu kỳ phụ thuộc

Nếu hai module import lẫn nhau và DSL cấm chu kỳ, diagnostic có thể liệt kê nhiều vị trí import tạo thành chu kỳ. Vị trí chính có thể là cạnh import phát hiện chu kỳ; related locations ghi các cạnh còn lại trong đường đi.

Không nên gửi quá nhiều related locations không cần thiết. Chọn các vị trí giúp người dùng hiểu nguyên nhân hoặc điều hướng đến khai báo liên quan.

## 10. Vị trí lỗi ở EOF và cấu trúc chưa hoàn chỉnh

Trong IDE, người dùng thường dừng giữa chừng khi gõ. Lexer và parser phải báo lỗi hữu ích dù tài liệu chưa hoàn chỉnh.

Ví dụ:

~~~text
policy OrderPolicy {
    when order.total > 1000 then
~~~

Parser có thể đang chờ một `Action` sau `then`. Vị trí lỗi là EOF. Diagnostic nên nói “Expected an action after `then`”, thay vì chỉ nói “Unexpected end of file”.

Với dấu ngoặc chưa đóng:

~~~text
transaction {
    reserveInventory(order);
~~~

Diagnostic có thể đặt primary location tại EOF và related location ở dấu `{` mở khối. Cách này giải thích rằng dấu đóng còn thiếu thuộc khối bắt đầu ở đâu.

### Token tổng hợp và vị trí chèn

Parser có thể tạo token tổng hợp (*missing token*) để tiếp tục phân tích. Token tổng hợp không có lexeme thực trong nguồn, vì vậy nên mang zero-width span tại vị trí chèn. Không nên giả vờ token đó có một đoạn văn bản thật.

### Tránh nhiều lỗi dây chuyền

Một lỗi cú pháp đầu tiên có thể khiến parser phát sinh nhiều lỗi thứ cấp. Vị trí của lỗi thứ cấp có thể gây nhiễu nếu parser chưa phục hồi được cấu trúc. Parser nên dùng chiến lược recovery phù hợp và có thể giảm hoặc đánh dấu diagnostic suy diễn từ lỗi gốc.

## 11. Vị trí lỗi và phục hồi cú pháp

Parser có thể phục hồi sau lỗi bằng cách bỏ token, chèn token giả hoặc đồng bộ tại một token mốc như `;`, `}` hoặc từ khóa bắt đầu câu lệnh tiếp theo.

Ví dụ:

~~~text
when order.total > then approveOrder;
when order.isPaid then capturePayment;
~~~

Parser có thể phát hiện thiếu biểu thức sau `>` và đồng bộ tại `then`, sau đó tiếp tục phân tích rule tiếp theo. Diagnostic đầu tiên nên trỏ đến vị trí `then` hoặc vị trí trống trước nó, tùy chính sách. Lỗi ở rule thứ hai không nên bị gán nhầm về vị trí của lỗi đầu tiên.

### Recovery span

Một số parser giữ span của vùng token đã bỏ qua để thông báo “Unexpected tokens in this statement”. Span này có thể bao trùm nhiều token. Khi recovery kết thúc, parser cần xác định lại vị trí của cấu trúc tiếp theo.

### Diagnostic gốc và diagnostic phụ

Nếu một dấu `)` thiếu khiến nhiều biểu thức sau bị phân tích sai, có thể phát một lỗi chính tại vị trí thiếu dấu đóng và hạn chế các lỗi phụ do recovery. Điều này giúp người dùng sửa nguyên nhân gốc trước.

## 12. Vị trí lỗi trong AST và kiểm tra ngữ nghĩa

Parser thường gắn span vào token hoặc nút CST/AST. Bộ kiểm tra ngữ nghĩa dùng các span này khi phát hiện vấn đề.

### Span của nút AST

Một nút AST có thể lưu span bao trùm toàn bộ cấu trúc nguồn tạo ra nó. Các nút con giữ span riêng để diagnostic có thể trỏ chính xác hơn.

Ví dụ:

~~~text
GreaterThan
├── left: PropertyAccess(order.total)
└── right: NumberLiteral(1000)
~~~

Span của `GreaterThan` bao trùm toàn biểu thức; span của `PropertyAccess` bao trùm `order.total`; span của tên thuộc tính có thể riêng là `total`. Khi thuộc tính không tồn tại, dùng span tên thuộc tính thường hữu ích hơn span cả phép so sánh.

### Nút tổng hợp

Một số nút AST được tạo trong quá trình desugaring hoặc normalization không có đoạn nguồn trực tiếp. Nút có thể kế thừa span của cú pháp gốc hoặc lưu origin riêng. Nếu lỗi phát sinh từ nút tổng hợp, diagnostic cần ánh xạ về cú pháp mà người dùng đã viết.

### Kiểu và tham chiếu đã phân giải

Khi AST được gắn kiểu hoặc liên kết symbol, metadata này giúp diagnostic trỏ đến cả nơi dùng lẫn nơi khai báo. Ví dụ, lỗi “Cannot compare DateTime with Integer” có thể có primary span tại toán hạng không tương thích và related location tại khai báo kiểu của toán hạng còn lại.

## 13. Vị trí lỗi trong macro, template và include

Macro và template có thể sinh ra cấu trúc không xuất hiện trực tiếp trong văn bản gọi. Một diagnostic cần phân biệt nơi người dùng gọi, nơi định nghĩa và nơi lỗi được tạo ra sau expansion.

### Call site và definition site

~~~text
// macros/order.dsl
macro approveIfPaid(order) {
    when order.payment.status == ACCEPTED then approveOrder;
}

// policies/main.dsl
approveIfPaid(order);
~~~

Nếu macro expansion tạo ra lỗi, công cụ có thể cung cấp:

- Primary location tại lời gọi macro trong `main.dsl`.
- Related location tại phần biểu thức trong định nghĩa macro ở `order.dsl`.
- Vị trí đối số nếu lỗi liên quan đến `order` được truyền vào.

### Origin chain

Khi một cấu trúc trải qua nhiều lần biến đổi, có thể giữ chuỗi nguồn gốc:

~~~text
Generated node
  <- expanded from invocation at policies/main.dsl:8
  <- defined by macro at macros/order.dsl:2
  <- argument supplied at policies/main.dsl:8
~~~

Diagnostic có thể chọn vị trí phù hợp nhất làm primary location và cung cấp các bước còn lại dưới dạng related locations hoặc notes.

### Include và import

Mỗi nút từ tệp được include nên giữ source identity của tệp đó. Không nên chuyển tất cả span về tệp gốc chỉ vì tệp gốc đã include nó. Nếu lỗi nằm trong `common/rules.dsl`, người dùng cần được dẫn đến đúng tệp này.

## 14. Vị trí lỗi trong mã được sinh

DSL có thể được biên dịch thành Java, SQL, JavaScript, cấu hình workflow hoặc một định dạng đích khác. Khi lỗi xảy ra trong mã đích, người dùng thường cần biết câu lệnh DSL nào đã tạo ra nó.

### Source map

Source map ánh xạ vị trí trong artifact được sinh về vị trí nguồn DSL. Ví dụ:

DSL:

~~~text
when order.total > 1000 then approveOrder;
~~~

Java được sinh:

~~~java
if (order.getTotal().compareTo(new BigDecimal("1000")) > 0) {
    orderService.approve(order);
}
~~~

Nếu `orderService.approve` ném exception, stack trace Java có thể trỏ đến dòng mã sinh. Source map cho phép IDE hoặc runtime liên kết lỗi với câu lệnh DSL ban đầu.

### Ánh xạ một-nhiều và nhiều-một

Một câu lệnh DSL có thể sinh nhiều dòng mã; nhiều câu lệnh DSL có thể được gộp thành một đoạn mã đích. Vì vậy, source map không nhất thiết là ánh xạ một-một. Một đoạn mã sinh có thể cần liên kết đến toàn bộ khai báo nguồn hoặc đến một nút cha.

### Mã hỗ trợ không có nguồn trực tiếp

Compiler có thể sinh hàm khởi tạo, helper hoặc mã kiểm tra không tương ứng với một dòng DSL cụ thể. Các phần này nên được đánh dấu generated hoặc liên kết đến khai báo bao quanh, không nên gán một vị trí nguồn giả.

## 15. Vị trí lỗi lúc chạy

Lỗi lúc chạy xuất hiện sau khi chương trình đã qua một phần hoặc toàn bộ kiểm tra tĩnh. Ví dụ: dịch vụ kho không phản hồi, dữ liệu thực tế vi phạm giả định, phép chia cho 0 hoặc một hành động nghiệp vụ bị từ chối.

### Gắn runtime failure với câu lệnh DSL

Nếu interpreter đang thực thi:

~~~text
reserveInventory(order);
~~~

và dịch vụ kho trả lỗi, runtime nên ghi nhận span của `reserveInventory(order)` cùng mã lỗi từ dịch vụ. Diagnostic hoặc log có thể hiển thị:

~~~text
policies/order.dsl:18:5: error DSL-R401: Inventory reservation failed.
  Source action: reserveInventory(order)
  Cause: inventory service rejected the reservation.
~~~

Vị trí nguồn giúp người vận hành tìm rule gây ra thao tác. Nguyên nhân bên ngoài có thể được hiển thị riêng, tránh nhầm lẫn giữa lỗi cú pháp DSL và lỗi của dịch vụ.

### Call stack DSL

Nếu một rule gọi một action, action gọi workflow con, workflow con gọi hàm DSL khác, runtime có thể lưu call stack ở mức DSL. Điều này hữu ích hơn stack trace nội bộ của interpreter vì nó thể hiện các bước người dùng đã khai báo.

~~~text
DSL execution trace:
  OrderPolicy at policies/order.dsl:4
  -> ApproveOrder at workflows/approval.dsl:12
  -> reserveInventory at actions/inventory.dsl:7
~~~

### Lỗi bất đồng bộ

Một action có thể khởi chạy tác vụ bất đồng bộ và lỗi chỉ xuất hiện sau khi luồng thực thi ban đầu đã kết thúc. Runtime cần giữ correlation ID hoặc execution context để liên kết lỗi về rule và span đã khởi chạy tác vụ. Không nên dựa vào stack frame của thread hiện tại nếu tác vụ đã chuyển sang thread khác.

## 16. Lỗi ở nhiều tệp và nhiều nguồn

Một dự án DSL thường gồm nhiều tệp. Vị trí lỗi phải gắn với source identity, không chỉ với offset.

Ví dụ:

~~~text
project/
  main.dsl
  models/order.dsl
  policies/approval.dsl
  workflows/shipping.dsl
~~~

`approval.dsl` có thể tham chiếu đến kiểu `Order` được khai báo trong `models/order.dsl`. Nếu thuộc tính không tồn tại, vị trí chính thường ở tham chiếu trong `approval.dsl`; related location có thể trỏ đến khai báo `Order` trong `order.dsl`.

### Diagnostic xuyên module

Một lỗi có thể liên quan đến nhiều nguồn:

- Nơi sử dụng tên.
- Nơi khai báo tên.
- Nơi import hoặc alias tên.
- Nơi định nghĩa kiểu hoặc quy tắc bị vi phạm.

Diagnostic nên phân biệt vai trò từng vị trí bằng label như “Referenced here”, “Declared here”, “Imported here” hoặc “Conflicting declaration”.

### Nguồn ảo

Không phải mọi tài liệu đều có đường dẫn tệp. DSL có thể được viết trong một biểu mẫu, editor nhúng, cấu hình lấy từ database hoặc tài liệu sinh trong bộ nhớ. Khi đó, source ID có thể là URI ảo hoặc ID tài liệu do ứng dụng cấp. Diagnostic vẫn cần định danh đủ để giao diện đưa người dùng đến đúng vùng nhập liệu.

## 17. Vị trí lỗi trong IDE và Language Server

IDE sử dụng vị trí lỗi để tô sáng, hiển thị tooltip, điều hướng và áp dụng quick fix. Language Server Protocol (LSP) là giao thức phổ biến để cung cấp các dịch vụ này.

Trong LSP, tài liệu được xác định bằng URI. Diagnostic chứa range với `start` và `end`; mỗi position có `line` và `character` bắt đầu từ 0. Theo quy ước UTF-16 của LSP, `character` được tính bằng UTF-16 code unit.

Nếu lexer nội bộ dùng byte offset UTF-8, server phải chuyển đổi byte offset sang line và UTF-16 column trước khi gửi diagnostic. Không được gửi byte offset trực tiếp vào trường `character`.

### Tính năng IDE dựa trên vị trí lỗi

| Tính năng | Sử dụng vị trí |
|---|---|
| Diagnostics | Tô sáng range và hiển thị thông điệp. |
| Problems panel | Liệt kê lỗi cùng file, dòng và cột. |
| Go to Location | Đưa con trỏ đến đoạn nguồn. |
| Related Information | Hiển thị vị trí khai báo hoặc nguyên nhân liên quan. |
| Quick Fix | Thay thế hoặc chèn văn bản tại range. |
| Hover | Hiển thị chi tiết diagnostic khi rê chuột. |
| Code Lens | Hiển thị thông tin bổ sung gắn với khai báo hoặc dòng nguồn. |

### Phiên bản tài liệu

Trong editor, người dùng có thể sửa văn bản trong khi server đang phân tích. Diagnostic từ version cũ có thể trỏ nhầm sau khi chèn hoặc xóa ký tự ở phía trước. Server cần gắn kết quả phân tích với version đầu vào và bỏ qua kết quả đã lỗi thời khi công bố.

Nếu một quick fix được tạo từ version cũ, client cần kiểm tra range và ngữ cảnh trước khi áp dụng. Không nên dùng span cũ trên văn bản mới mà không có mapping.

## 18. Vị trí lỗi và code action

Một code action hoặc quick fix là thao tác sửa có thể áp dụng dựa trên diagnostic. Vị trí lỗi chính xác là điều kiện để thao tác chỉ sửa đúng phần cần thiết.

Ví dụ:

~~~text
when order.totla > 1000 then approveOrder;
~~~

Diagnostic có primary span của `totla` và đề xuất thay bằng `total`.

~~~text
CodeAction
  title: Replace 'totla' with 'total'
  edit:
    range: span(totla)
    newText: "total"
~~~

Một quick fix có thể:

- Thay thế một token.
- Chèn token còn thiếu tại zero-width range.
- Xóa token thừa.
- Thêm import hoặc qualified name.
- Đổi tên một khai báo và các tham chiếu theo symbol identity.
- Tạo nhiều text edit trên một hoặc nhiều tệp.

### Phân biệt quick fix và refactoring

Quick fix thường giải quyết một diagnostic cụ thể. Refactoring có thể thay đổi nhiều vị trí và nhiều tệp dựa trên mô hình ngữ nghĩa. Cả hai cần range và source identity chính xác; refactoring còn cần bảo đảm các tham chiếu được cập nhật theo symbol, không phải thay chuỗi văn bản đơn thuần.

## 19. Vị trí lỗi trong cú pháp đồ họa và biểu mẫu

Không phải DSL nào cũng được viết bằng văn bản. Một DSL đồ họa có thể dùng hộp, nút, đường nối và thuộc tính; DSL biểu mẫu có thể dùng trường nhập liệu hoặc hàng trong bảng.

### DSL đồ họa

Một lỗi có thể gắn với:

- ID của node hoặc edge.
- Vùng hình học trên canvas.
- Thuộc tính của node.
- Đường nối không hợp lệ.
- Cạnh hoặc nút tạo chu kỳ không được phép.

Ví dụ, một workflow có node `ApproveOrder` nhưng không có nhánh xử lý khi điều kiện thất bại. Diagnostic có thể gắn với node quyết định hoặc cổng đầu ra còn thiếu.

### DSL dạng biểu mẫu

Một lỗi có thể trỏ đến trường `ShippingMethod`, hàng dữ liệu số 4 hoặc ô chứa giá trị không hợp lệ. Source identity khi đó có thể là ID form, ID row hoặc ID cell thay vì tệp văn bản.

### Mô hình chẩn đoán thống nhất

Có thể dùng một mô hình location tổng quát với các loại locator khác nhau:

~~~text
TextLocation(sourceId, range)
GraphLocation(documentId, elementId, propertyId)
FormLocation(formId, rowId, fieldId)
~~~

Lớp giao diện chuyển loại location tương ứng thành cách điều hướng và tô sáng phù hợp.

## 20. Vị trí lỗi và dữ liệu nhạy cảm

Diagnostic cần đủ thông tin để sửa lỗi nhưng không nên vô tình tiết lộ dữ liệu nhạy cảm. Ví dụ, một lỗi xảy ra khi xử lý một đơn hàng có thể liên quan đến email, địa chỉ hoặc mã khách hàng. Thông điệp hiển thị cho người dùng không nhất thiết phải chứa toàn bộ giá trị dữ liệu.

Một số nguyên tắc:

- Ưu tiên trỏ đến biểu thức DSL hoặc khai báo gây lỗi thay vì nhúng dữ liệu thực tế vào message.
- Che hoặc loại bỏ token, giá trị bí mật và thông tin định danh khỏi log không dành cho người có quyền.
- Phân biệt diagnostic dành cho người viết DSL với log vận hành dành cho người được cấp quyền.
- Giữ correlation ID để tra cứu chi tiết trong hệ thống kiểm soát truy cập.
- Không đưa secret hoặc nội dung nhạy cảm vào quick fix hay related location.

Ví dụ, thay vì hiển thị “Payment failed for card 4111…”, diagnostic có thể nói “Payment authorization failed for this action” và cung cấp mã tham chiếu có thể tra cứu theo quyền.

## 21. Vị trí lỗi và nguồn gốc sau biến đổi

Một chương trình DSL có thể trải qua desugaring, normalization, lowering và code generation. Nút gây lỗi ở giai đoạn sau có thể không còn tương ứng trực tiếp với đoạn văn bản ban đầu.

### Kế thừa span

Khi một nút được thay bằng nút tương đương, nút mới có thể kế thừa span của nút nguồn. Ví dụ `UnlessRule` được chuyển thành `ConditionalRule` với điều kiện `Not(...)`; toàn bộ cấu trúc mới có thể giữ span của câu lệnh `unless`.

### Nút tổng hợp

Một phép biến đổi có thể tạo nhiều nút mới từ một cú pháp rút gọn. Các nút có thể cùng trỏ về span gốc hoặc lưu origin riêng để phân biệt nguồn tạo ra chúng.

### Không có vị trí trực tiếp

Một số nút được tạo bởi tối ưu hóa, chẳng hạn temporary variable hoặc helper call, không có đoạn nguồn riêng. Có thể gắn origin của nút cha, đánh dấu generated hoặc lưu liên kết đến các nút đầu vào. Không nên tùy tiện gán offset 0 hoặc một dòng bất kỳ.

### Mapping qua nhiều pass

Nếu AST trải qua nhiều pass, thông tin origin phải được truyền hoặc cập nhật xuyên suốt. Nếu một pass tạo nút mới nhưng bỏ metadata nguồn, diagnostic của pass sau có thể chỉ còn vị trí IR hoặc mã đích mà người dùng không hiểu.

## 22. Vị trí lỗi trong dự án nhiều phiên bản

Vị trí nguồn luôn gắn với một snapshot tài liệu cụ thể. Khi tài liệu thay đổi, range cũ có thể không còn đúng.

### Versioned diagnostics

Mỗi kết quả phân tích nên ghi nhận document version. Nếu version hiện tại của editor khác version diagnostic, client hoặc server cần bỏ qua, tính lại hoặc ánh xạ vị trí theo một cơ chế được xác định.

### Incremental edits

Khi người dùng chèn ký tự ở đầu tệp, offset của mọi đoạn phía sau có thể tăng. Khi xóa một đoạn, offset có thể giảm. Một span cũ không thể được dùng nguyên trạng trên văn bản mới.

### Snapshot bất biến

Một cách thiết kế là tạo snapshot nguồn bất biến cho mỗi lần phân tích. Token và AST tham chiếu đến snapshot tương ứng. Khi có version mới, hệ thống tạo snapshot mới và kết quả cũ không bị diễn giải lại trên văn bản mới.

### Điều hướng đến vị trí cũ

Với log lịch sử hoặc báo cáo build, vị trí có thể tham chiếu đến commit hoặc version cụ thể. Giao diện cần mở đúng revision hoặc nói rõ rằng vị trí thuộc phiên bản cũ, thay vì mở file hiện tại rồi nhảy đến offset không còn tương ứng.

## 23. Định dạng diagnostic cho người dùng

Một thông báo lỗi tốt cần trả lời nhanh ba câu hỏi: vấn đề gì, ở đâu và nên xem xét điều gì tiếp theo.

Ví dụ:

~~~text
policies/order.dsl:2:20: error DSL2003: Unknown property 'totla' on type 'Order'.
  2 |     when order.totla > 1000 then approveOrder;
    |                   ^^^^^
  help: Did you mean 'total'?
  note: 'Order' is declared in models/order.dsl:4.
~~~

Một định dạng hữu ích thường có:

- Đường dẫn hoặc tên tài liệu.
- Dòng và cột dễ đọc.
- Severity và mã lỗi.
- Message ngắn, nói rõ vấn đề.
- Đoạn nguồn có dấu chỉ vị trí.
- Gợi ý sửa nếu có căn cứ.
- Related location khi cần giải thích thêm.

### Độ dài span và cách hiển thị

Với lỗi token, dấu chỉ có thể bao trùm token. Với lỗi thiếu token, dấu chỉ có thể đặt tại vị trí chèn. Với lỗi cả câu lệnh, giao diện có thể dùng underline hoặc highlight nhẹ thay vì vẽ caret dài khó đọc.

### Ngôn ngữ thông báo

Message nên dùng thuật ngữ nhất quán với tài liệu DSL. Mã lỗi ổn định có thể dùng để tra cứu ngay cả khi message được dịch sang nhiều ngôn ngữ. Không nên để logic chương trình phụ thuộc vào việc so sánh chuỗi message.

## 24. Chẩn đoán nhiều lỗi và thứ tự hiển thị

Một tệp có thể có nhiều lỗi. Compiler hoặc IDE cần quyết định cách sắp xếp và nhóm diagnostic.

### Sắp xếp theo vị trí nguồn

Một lựa chọn phổ biến là sắp xếp theo source URI, start offset và severity. Cách này giúp người dùng đọc lỗi theo thứ tự xuất hiện trong tài liệu.

### Nhóm lỗi liên quan

Nhiều diagnostic có thể xuất phát từ một nguyên nhân gốc. Ví dụ thiếu dấu `}` có thể tạo nhiều lỗi parser ở các dòng sau. Có thể nhóm chúng dưới một lỗi gốc hoặc đánh dấu lỗi suy diễn để giảm nhiễu.

### Giới hạn số lượng

Với tài liệu lỗi nặng, parser có thể tạo hàng nghìn diagnostic. IDE có thể giới hạn số lỗi hiển thị hoặc ưu tiên lỗi gần con trỏ. Tuy nhiên, giới hạn giao diện không nên làm mất dữ liệu diagnostic cần cho báo cáo build hoặc kiểm thử.

### Vị trí trùng nhau

Hai lỗi khác nhau có thể cùng trỏ đến một span. Giao diện cần hiển thị cả hai hoặc gộp thông tin mà không làm mất mã và severity. Không nên tự ý thay diagnostic có severity cao bằng diagnostic có severity thấp.

## 25. Kiểm thử vị trí lỗi

Một chương trình có thể được phân tích đúng nhưng diagnostic trỏ sai vị trí. Vì vậy, kiểm thử nên xác nhận cả loại lỗi, message hoặc code và range.

### Kiểm thử lexer

Đầu vào:

~~~text
let amount = 10 @ 2;
~~~

Kỳ vọng diagnostic lexer trỏ đúng ký tự `@`, không bao trùm `10` hoặc `2`.

### Kiểm thử parser

Đầu vào:

~~~text
when order.total > 1000
~~~

Kỳ vọng diagnostic chỉ ra vị trí cần `then` hoặc EOF theo quy ước của parser.

### Kiểm thử name resolution

Đầu vào:

~~~text
when order.totla > 1000 then approveOrder;
~~~

Kỳ vọng primary span là `totla`; related location có thể trỏ đến khai báo `Order`.

### Kiểm thử khai báo trùng

Đầu vào có hai khai báo cùng tên. Xác nhận primary location là khai báo gây xung đột và related location là khai báo trước.

### Kiểm thử Unicode

Đặt ký tự tiếng Việt hoặc ký tự ngoài BMP trước token gây lỗi. Xác nhận offset nội bộ, dòng/cột và vị trí editor trỏ cùng một token. Chỉ kiểm thử ASCII là chưa đủ vì các hệ tọa độ thường trùng nhau trong trường hợp ASCII.

### Kiểm thử newline và tab

Chạy cùng bộ kiểm thử với LF, CRLF, CR, tab và không có newline cuối tệp. Xác nhận dòng/cột không bị lệch.

### Kiểm thử source map

Sinh mã từ DSL, cố ý tạo lỗi lúc chạy trong một hành động được sinh và xác nhận vị trí được ánh xạ về câu lệnh DSL tương ứng.

### Kiểm thử version

Tạo diagnostic trên version cũ, chèn văn bản trước span rồi gửi kết quả cũ. Xác nhận hệ thống không hiển thị diagnostic tại vị trí sai của version mới.

## 26. Ví dụ kiểm thử range trong Java

Một kiểm thử đơn giản có thể xác nhận span của token:

~~~java
@Test
void unknownPropertyDiagnosticPointsToPropertyName() {
    String source = "when order.totla > 1000 then approveOrder;";

    Diagnostic diagnostic = analyze(source).stream()
        .filter(d -> d.code().equals("DSL2003"))
        .findFirst()
        .orElseThrow();

    SourceSpan span = diagnostic.primarySpan();
    assertEquals("totla", source.substring(
        span.startOffset(), span.endOffset()
    ));
}
~~~

Đoạn mã minh họa giả định offset dùng cùng đơn vị với `String.substring` của Java, tức UTF-16 code unit. Nếu parser dùng byte offset UTF-8, cần chuyển đổi trước khi cắt chuỗi Java.

Một bộ kiểm thử đầy đủ có thể kiểm tra thêm source ID, version, severity, related locations và nội dung code action.

## 27. Những lỗi thiết kế thường gặp

**Chỉ lưu dòng và cột.** Việc cập nhật vị trí sau edit và ánh xạ giữa encoding trở nên khó khăn. Offset và source identity thường là nền tảng tốt hơn; dòng/cột có thể được tính khi cần.

**Không định nghĩa đơn vị offset.** Lexer dùng byte nhưng IDE dùng UTF-16 có thể làm diagnostic lệch khi gặp Unicode.

**Nhầm base 0 và base 1.** API nội bộ thường dùng chỉ số bắt đầu từ 0, còn thông báo cho người dùng thường hiển thị dòng/cột bắt đầu từ 1. Chuyển đổi phải được thực hiện ở ranh giới.

**Dùng span quá rộng hoặc quá hẹp.** Tô sáng cả tệp cho một lỗi token gây nhiễu; tô sáng một ký tự không liên quan có thể khiến người dùng sửa sai.

**Không có source identity.** Offset không gắn với tệp hoặc tài liệu cụ thể không đủ để điều hướng.

**Không giữ related locations.** Các lỗi khai báo trùng, sai kiểu hoặc chu kỳ phụ thuộc khó giải thích nếu chỉ trỏ một vị trí.

**Gán vị trí giả cho nút tổng hợp.** Nút sinh tự động cần origin hoặc trạng thái generated, không nên trỏ tùy tiện về đầu tệp.

**Dùng diagnostic cũ sau khi tài liệu đổi.** Version cũ có thể làm editor tô sáng sai vùng.

**Bỏ qua newline và Unicode.** Chương trình chạy đúng với ASCII/LF có thể báo lỗi sai trong tệp tiếng Việt hoặc tệp CRLF.

**Để message chứa dữ liệu nhạy cảm.** Vị trí lỗi và log cần đủ hữu ích nhưng phải tuân theo quyền truy cập và chính sách bảo vệ dữ liệu.

**So sánh message thay vì mã lỗi.** Message có thể được dịch hoặc cải thiện; code ổn định hơn cho kiểm thử và công cụ.

## 28. Quy trình thiết kế vị trí lỗi cho DSL

Một quy trình thực tế có thể gồm:

1. **Định nghĩa source identity:** tệp, URI, tài liệu ảo hoặc ID của mô hình đồ họa.
2. **Chọn hệ tọa độ nội bộ:** byte, code point hoặc UTF-16; xác định rõ đơn vị và khoảng nửa mở.
3. **Xây dựng source manager:** lưu snapshot, encoding, line index và version.
4. **Gắn span vào token và AST:** lexer ghi span token; parser lan truyền span đến nút; pass biến đổi giữ source origin.
5. **Chuẩn hóa diagnostic:** code, severity, message, primary location, related locations và fixes.
6. **Xác định quy tắc chọn span:** token sai, vị trí thiếu, biểu thức, khai báo hoặc cấu trúc cha.
7. **Xử lý nhiều nguồn:** import, include, macro, template và mã sinh.
8. **Tích hợp IDE/LSP:** chuyển đổi đúng sang range của giao thức và điều hướng theo URI.
9. **Quản lý version:** bỏ diagnostic lỗi thời và bảo đảm quick fix áp dụng trên snapshot phù hợp.
10. **Bảo vệ dữ liệu:** kiểm soát nội dung message, related information và log.
11. **Kiểm thử tọa độ:** Unicode, newline, tab, EOF, nhiều tệp, source map và edit liên tục.

## 29. Mẫu checklist cho một diagnostic

Khi một thành phần DSL phát hiện lỗi, có thể xem xét các câu hỏi:

- Diagnostic có mã ổn định và severity phù hợp không?
- Có source identity rõ ràng không?
- Primary location có trỏ đúng phần người dùng cần xem không?
- Range có dùng đúng đơn vị và quy ước start/end không?
- Nếu thiếu token, vị trí chèn có được biểu diễn đúng không?
- Có khai báo hoặc vị trí liên quan nào giúp giải thích nguyên nhân không?
- Message có nói rõ điều kiện sai và dùng thuật ngữ miền nhất quán không?
- Có quick fix an toàn và đủ thông tin để áp dụng không?
- Vị trí có thuộc đúng version của tài liệu không?
- Nếu lỗi phát sinh từ macro hoặc mã sinh, source origin có được giữ không?
- Message và related locations có tránh tiết lộ dữ liệu nhạy cảm không?
- Kiểm thử có xác nhận range với Unicode, newline và tab không?

## 30. Kết quả cần có sau khi thiết kế vị trí lỗi

Một thiết kế chẩn đoán vị trí đầy đủ thường tạo ra:

- **Mô hình nguồn:** source ID, snapshot, version, encoding và line index.
- **Quy ước tọa độ:** offset, range nửa mở, base dòng/cột và đơn vị ký tự.
- **Thông tin vị trí:** span của token, CST/AST, nút tổng hợp và runtime action.
- **Mô hình diagnostic:** mã, severity, message, primary location, related locations và code fixes.
- **Cơ chế ánh xạ:** Unicode, LSP/editor, macro/include và source map của mã sinh.
- **Quy tắc recovery:** vị trí lỗi cú pháp, EOF, token tổng hợp và lỗi dây chuyền.
- **Chính sách version:** cách xử lý diagnostic và quick fix khi tài liệu thay đổi.
- **Bộ kiểm thử:** lỗi từ mọi giai đoạn, nhiều nguồn, Unicode, newline, source map và vị trí version cũ.

Vị trí lỗi là cầu nối giữa phân tích nội bộ của DSL và người đang viết hoặc vận hành chương trình. Khi source identity, range, đơn vị tọa độ, version và nguồn gốc được định nghĩa rõ, compiler có thể đưa ra chẩn đoán chính xác, IDE có thể điều hướng và sửa đúng đoạn, còn runtime có thể liên kết sự cố với quy tắc đã kích hoạt nó. Một diagnostic tốt không chỉ nói điều gì sai; nó giúp người dùng tìm đúng nơi, hiểu quan hệ liên quan và biết bước tiếp theo cần thực hiện.
