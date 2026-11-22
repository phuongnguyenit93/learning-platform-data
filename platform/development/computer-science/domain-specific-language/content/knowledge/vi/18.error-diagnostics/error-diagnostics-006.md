# Thông báo lỗi dễ hiểu trong DSL

Một DSL (*Domain-Specific Language*) cần giúp người dùng viết mô tả cho một miền cụ thể, chẳng hạn truy vấn dữ liệu, khai báo chính sách, cấu hình hạ tầng, workflow hoặc công thức nghiệp vụ. Khi đầu vào sai cú pháp hoặc không hợp lệ trong miền, hệ thống phải giải thích rõ vấn đề. Một thông báo chỉ ghi “Syntax error” hoặc “Invalid input” cho biết có lỗi nhưng không giúp người viết tìm nguyên nhân.

**Thông báo lỗi dễ hiểu** (*clear diagnostics*) là thông tin được tạo ra khi lexer, parser, semantic analyzer, type checker, validator hoặc runtime phát hiện một vấn đề. Một diagnostic tốt cho biết lỗi nằm ở đâu, hệ thống mong đợi điều gì, đầu vào thực tế có gì và người dùng có thể làm gì tiếp theo.

Ví dụ, DSL cấu hình tác vụ có thể chứa:

```text
task "build" {
    command = "gradle build"
    timeout = "fast"
}
```

Nếu timeout yêu cầu kiểu Duration, thông báo “Invalid value” là chưa đủ. Người dùng cần biết thuộc tính timeout phải là thời lượng, giá trị hiện tại là chuỗi và có thể viết 30s hoặc 2m.

Thông báo lỗi là một phần của thiết kế ngôn ngữ và trải nghiệm sử dụng. Cách diễn đạt tốt giúp người dùng sửa lỗi nhanh, giảm trao đổi với nhóm phát triển và làm cho DSL đáng tin cậy hơn.

## 1. Diagnostic là gì?

**Diagnostic** là bản ghi mô tả vấn đề hoặc thông tin được phát hiện trong quá trình xử lý DSL. Diagnostic có thể là lỗi, cảnh báo hoặc thông tin hỗ trợ người dùng.

Các giai đoạn khác nhau có thể tạo diagnostic:

- **Lexer:** ký tự không hợp lệ, chuỗi chưa đóng, literal sai định dạng.
- **Parser:** thiếu dấu đóng block, toán tử ở sai vị trí, thiếu toán hạng.
- **Semantic analyzer:** tên thuộc tính không tồn tại, tham chiếu không hợp lệ, thao tác không được hỗ trợ.
- **Type checker:** kiểu dữ liệu không tương thích, đối số sai kiểu, phép toán không áp dụng được.
- **Domain validator:** giá trị nằm ngoài giới hạn nghiệp vụ, hai tùy chọn xung đột.
- **Runtime:** tài nguyên không truy cập được, dịch vụ từ chối thao tác hoặc điều kiện thực thi không còn đúng.

Diagnostic không nhất thiết đồng nghĩa với exception. Exception thường là cơ chế báo một tình huống bất thường trong quá trình chạy chương trình. Diagnostic là thông tin có cấu trúc được thiết kế để hiển thị cho người viết DSL, công cụ hoặc hệ thống khác. Ứng dụng có thể bắt exception rồi chuyển nó thành diagnostic phù hợp, nhưng không nên hiển thị stack trace nội bộ như thông báo lỗi cho người dùng.

### Diagnostic khác log như thế nào?

Log thường phục vụ vận hành và điều tra hệ thống. Diagnostic phục vụ người đang viết, kiểm tra hoặc thực thi DSL.

| Đặc điểm | Diagnostic | Log |
|---|---|---|
| Đối tượng đọc | Người viết DSL, editor, CLI | Nhà phát triển, vận hành |
| Mục tiêu | Giải thích vấn đề và cách xử lý | Ghi lại sự kiện và ngữ cảnh kỹ thuật |
| Vị trí nguồn | Thường rất quan trọng | Có thể không có |
| Cách diễn đạt | Theo ngôn ngữ miền | Có thể thiên về kỹ thuật |
| Định dạng | Có cấu trúc, hướng tới người dùng | Thường theo schema log |
| Dữ liệu nhạy cảm | Chỉ hiển thị phần cần thiết | Tuân theo chính sách logging |

Một diagnostic có thể được ghi vào log, nhưng hai loại thông tin nên có mục đích và mức chi tiết riêng.

## 2. Thành phần của một thông báo lỗi tốt

Không phải lỗi nào cũng cần mọi trường, nhưng một diagnostic hữu ích thường gồm:

1. **Severity:** mức độ như error, warning hoặc info.
2. **Error code:** mã ổn định để tra cứu và tham chiếu.
3. **Title hoặc message:** mô tả ngắn gọn vấn đề.
4. **Source location:** vị trí xảy ra lỗi trong tệp hoặc đầu vào.
5. **Source excerpt:** đoạn nguồn liên quan, nếu có thể hiển thị an toàn.
6. **Expected:** hệ thống đang mong đợi điều gì.
7. **Found:** hệ thống thực tế nhận được gì.
8. **Explanation:** vì sao cấu trúc hoặc giá trị không hợp lệ.
9. **Suggestion:** bước sửa có thể thực hiện.
10. **Related locations:** vị trí liên quan, chẳng hạn khai báo gốc hoặc tham chiếu gây xung đột.
11. **Documentation link:** tài liệu chi tiết nếu vấn đề phức tạp.

Ví dụ:

```text
error DSL-TYPE-014: timeout phải là giá trị Duration

  --> pipeline.dsl:3:15
   |
 3 |     timeout = "fast"
   |               ^^^^^^
   |
   = expected: Duration, ví dụ 30s hoặc 2m
   = found: String "fast"
   = help: đổi giá trị thành 30s nếu muốn chờ 30 giây
```

Thông báo này cho người dùng biết thuộc tính nào sai, sai ở đâu, kiểu nào được yêu cầu, kiểu nào đã nhận và cách sửa có thể áp dụng.

### Ưu tiên thông tin quan trọng

Người dùng thường cần biết vấn đề và vị trí trước khi đọc chi tiết kỹ thuật. Một cách sắp xếp hợp lý:

- Dòng đầu: vấn đề chính.
- Tiếp theo: vị trí và đoạn nguồn.
- Sau đó: điều mong đợi và điều thực tế.
- Cuối cùng: gợi ý hoặc liên kết tài liệu.

Không nên mở đầu bằng tên lớp parser, stack trace, tên production nội bộ hoặc mã nguồn compiler nếu những chi tiết đó không giúp người dùng sửa lỗi.

## 3. Viết message ngắn, cụ thể và hướng đến người dùng

Một thông báo dễ hiểu nên nói trực tiếp điều gì sai. Tránh những câu quá chung chung, bị động hoặc chỉ lặp lại tên lỗi nội bộ.

| Thông báo kém hữu ích | Thông báo rõ hơn |
|---|---|
| Invalid input | Thuộc tính timeout cần một giá trị thời lượng |
| Parse failed | Thiếu dấu đóng block task |
| Type mismatch | retries cần số nguyên; bạn đã nhập chuỗi "three" |
| Unknown symbol | Không tìm thấy trường customer.region trong kiểu Customer |
| Operation failed | Không thể đọc tệp cấu hình tại đường dẫn đã cung cấp |
| Unexpected token | Sau AND cần một điều kiện, nhưng gặp dấu đóng block |

### Dùng thuật ngữ của miền

Nếu người dùng DSL là chuyên viên vận hành, thông báo nên nói “tên môi trường” hoặc “dịch vụ” thay vì “AST node” hoặc “symbol table”. Nếu DSL hướng đến nhà phát triển, thuật ngữ như identifier, expression hoặc type có thể phù hợp.

Ví dụ:

- Với DSL nghiệp vụ: “Không tìm thấy mã khách hàng trong danh sách đã chọn.”
- Với DSL dành cho lập trình viên: “Identifier customerId chưa được khai báo trong phạm vi hiện tại.”

Cùng một lỗi có thể cần cách diễn đạt khác nhau theo nhóm người dùng. Từ vựng của diagnostic nên thống nhất với tài liệu và giao diện của DSL.

### Tránh đổ lỗi cho người dùng

Thông báo nên mô tả trạng thái của đầu vào hoặc yêu cầu của ngôn ngữ, không phán xét người viết. Nên viết “Giá trị này cần nằm trong khoảng 1 đến 10” thay vì “Bạn nhập sai”. Cách diễn đạt trung tính giúp người dùng tập trung vào việc sửa vấn đề.

## 4. Chỉ rõ vị trí lỗi trong mã nguồn

Một thông báo chỉ có nội dung mà không có vị trí thường buộc người dùng tìm kiếm thủ công. Với DSL dạng văn bản, source location là thành phần rất quan trọng.

Vị trí có thể gồm:

- Tên tệp hoặc nguồn đầu vào.
- Số dòng.
- Số cột.
- Offset bắt đầu và kết thúc.
- Phạm vi nguồn (*source span*) bao phủ đoạn liên quan.

Ví dụ:

```text
pipeline.dsl:8:12-8:18
```

Có thể hiểu là lỗi nằm trên dòng 8, từ cột 12 đến cột 18 theo quy ước hiển thị của công cụ.

### Đánh dấu đúng đoạn gây lỗi

Giả sử người dùng viết:

```text
task "deploy" {
    retries = "many"
}
```

Thông báo nên đánh dấu chuỗi "many" vì đây là giá trị có kiểu không phù hợp. Nếu chỉ đánh dấu cả dòng hoặc cả tệp, người dùng khó biết chính xác thành phần cần sửa.

### Vị trí có thể là một vùng, không chỉ một điểm

Một số lỗi liên quan đến nhiều đoạn nguồn. Ví dụ, một thuộc tính bị khai báo trùng có thể cần chỉ cả khai báo mới và khai báo đầu tiên:

```text
defaults {
    timeout = 30s
}

task "build" {
    timeout = 60s
    timeout = 90s
}
```

Diagnostic có thể trỏ vào khai báo thứ hai và liên kết tới khai báo thứ nhất để giải thích xung đột.

### Quy ước dòng và cột

Cần thống nhất:

- Dòng và cột bắt đầu từ 0 hay 1.
- Cột được tính theo byte, code point, UTF-16 code unit hay ký tự hiển thị.
- Tab được hiển thị như thế nào.
- Ký tự Unicode kết hợp được tính ra sao.
- Source span có bao gồm ký tự cuối hay dùng khoảng nửa mở.

Editor và CLI có thể dùng cách biểu diễn khác nhau, nhưng vị trí nội bộ cần có quy ước rõ để chuyển đổi nhất quán. Nếu văn bản có tiếng Việt hoặc ký tự Unicode, việc tính cột theo byte có thể khiến dấu gạch dưới hiển thị lệch khỏi ký tự người dùng nhìn thấy.

## 5. Giải thích điều mong đợi và điều thực tế

Một trong những cách hữu ích nhất để giải thích lỗi là nêu rõ **expected** và **found**.

Ví dụ:

```text
error: sau toán tử >= cần một biểu thức
  found: từ khóa then
```

Hoặc:

```text
error: thuộc tính retries cần Integer
  expected: số nguyên từ 0 đến 5
  found: String "three"
```

Thông tin này giúp người dùng hiểu quy tắc bị vi phạm mà không phải đọc toàn bộ đặc tả grammar.

### Expected không nên là danh sách kỹ thuật quá dài

Parser có thể có hàng chục token hợp lệ ở một vị trí. Hiển thị toàn bộ danh sách token nội bộ sẽ khiến message khó đọc.

Thay vì liệt kê IDENTIFIER, STRING, NUMBER, TRUE, FALSE, LPAREN, NOT, NULL và nhiều token khác, nên nhóm chúng theo khái niệm:

```text
Sau toán tử so sánh, cần một giá trị hoặc biểu thức.
```

Nếu người dùng cần thông tin chi tiết hơn, công cụ có thể hiển thị danh sách token trong phần mở rộng hoặc chế độ debug.

### Nêu rõ phạm vi giá trị

Thông báo “giá trị không hợp lệ” không đủ cụ thể. Nếu có ràng buộc, hãy đưa ra ràng buộc đó:

```text
error: retries phải nằm trong khoảng 0 đến 5
  found: 8
  help: chọn một số nguyên từ 0 đến 5
```

Với thuộc tính có đơn vị, cần nêu cả đơn vị:

```text
timeout cần giá trị thời lượng, ví dụ 500ms, 30s hoặc 2m.
```

## 6. Phân biệt các loại lỗi để chọn cách diễn đạt

Thông báo tốt phụ thuộc vào giai đoạn phát hiện lỗi. Không nên gọi mọi vấn đề là lỗi cú pháp.

### 6.1. Lỗi từ vựng (lexical error)

Lexer không thể nhận diện một chuỗi ký tự thành token hợp lệ.

```text
name = "catalog
```

Thông báo rõ:

```text
Chuỗi chưa được đóng dấu ngoặc kép.
Thêm dấu ngoặc kép ở cuối giá trị name.
```

### 6.2. Lỗi cú pháp (syntax error)

Token hợp lệ nhưng thứ tự hoặc cấu trúc không phù hợp grammar.

```text
when order.total >=
then shipping.fee = 0
```

Thông báo rõ:

```text
Sau toán tử >= cần một giá trị hoặc biểu thức.
Hiện tại parser gặp từ khóa then.
```

### 6.3. Lỗi tham chiếu (name resolution error)

Cấu trúc đúng cú pháp nhưng tên không tồn tại hoặc không nằm trong phạm vi.

```text
when order.totla > 100000
```

Thông báo:

```text
Không tìm thấy thuộc tính "totla" trong Order.
Bạn có muốn dùng "total" không?
```

### 6.4. Lỗi kiểu (type error)

Tên và cấu trúc có thể hợp lệ, nhưng kiểu dữ liệu không tương thích.

```text
retries = "three"
```

Thông báo:

```text
retries cần số nguyên, nhưng giá trị hiện tại là chuỗi.
Ví dụ hợp lệ: retries = 3
```

### 6.5. Lỗi ràng buộc miền (domain validation error)

Giá trị đúng kiểu nhưng vi phạm quy tắc nghiệp vụ.

```text
discount = 150%
```

Thông báo:

```text
discount không được vượt quá 100%.
Giá trị hiện tại là 150%.
```

### 6.6. Lỗi runtime

Cấu trúc đã qua parsing và validation nhưng thao tác không thể hoàn tất trong môi trường thực thi.

```text
Không thể kết nối tới dịch vụ vận chuyển.
Hãy kiểm tra trạng thái dịch vụ hoặc thử lại sau.
```

Phân biệt loại lỗi giúp người dùng biết cần sửa văn bản, cập nhật mô hình miền hay kiểm tra môi trường chạy.

## 7. Gợi ý sửa lỗi phải cụ thể và an toàn

Một diagnostic có thể có phần **help** hoặc **suggestion**. Gợi ý tốt chỉ ra một hành động có thể thực hiện, thay vì nói chung chung “hãy kiểm tra lại”.

Ví dụ:

- “Thêm dấu đóng block để kết thúc task.”
- “Đổi retries thành một số nguyên từ 0 đến 5.”
- “Tên trường đúng có thể là total.”
- “Thêm khai báo region trong block environment.”

### Phân biệt gợi ý với sửa tự động

Một số công cụ có thể đề xuất quick fix. Người dùng chọn chấp nhận thì editor mới thay đổi văn bản.

Ví dụ, với tên trường gần đúng:

```text
order.totla
```

công cụ có thể đề xuất thay totla bằng total. Đây nên là một gợi ý có thể xem trước, vì hệ thống không phải lúc nào cũng biết người dùng định viết trường nào.

### Chỉ đề xuất khi có đủ cơ sở

Không nên tạo gợi ý sửa chỉ dựa trên phỏng đoán yếu. Nếu có nhiều lựa chọn gần giống nhau, hãy liệt kê một số khả năng hoặc yêu cầu người dùng kiểm tra schema.

Ví dụ:

```text
Không tìm thấy trường "status".
Các trường có sẵn: state, statusCode, paymentStatus.
```

Trong trường hợp này, tự động thay bằng một trường bất kỳ có thể làm thay đổi ý nghĩa nghiệp vụ.

### Không tự ý sửa nội dung khi báo lỗi

Thông báo diagnostic nên giữ vai trò giải thích. Nếu editor hỗ trợ tự sửa, thao tác cần có preview hoặc sự chấp thuận rõ ràng của người dùng. Không nên âm thầm thay đổi chính sách, cấu hình hoặc quy tắc đang được biên tập.

## 8. Dùng mã lỗi ổn định

Mã lỗi (*diagnostic code*) giúp tham chiếu một loại vấn đề mà không phụ thuộc hoàn toàn vào câu chữ hiển thị.

Ví dụ:

| Code | Ý nghĩa |
|---|---|
| DSL-PARSE-001 | Thiếu dấu đóng block |
| DSL-NAME-004 | Không tìm thấy định danh |
| DSL-TYPE-014 | Kiểu giá trị không tương thích |
| DSL-DOMAIN-008 | Giá trị vượt giới hạn nghiệp vụ |
| DSL-RUNTIME-003 | Không thể truy cập dịch vụ |

Mã lỗi hữu ích cho tài liệu, tìm kiếm hỗ trợ, bộ lọc diagnostics, phân tích tần suất lỗi, tự động hóa và kiểm thử ổn định qua các phiên bản.

### Code cần ổn định

Nếu câu chữ được cải thiện hoặc dịch sang ngôn ngữ khác, code vẫn nên giữ nguyên nếu loại lỗi không thay đổi. Không nên tái sử dụng một code cũ cho ý nghĩa hoàn toàn khác vì công cụ bên ngoài có thể đang dựa vào nó.

Có thể tổ chức code theo nhóm parser, name resolution, type checking, validation và runtime. Mã cần đủ ngắn để người dùng tham chiếu và đủ rõ để tài liệu hóa.

## 9. Severity – mức độ nghiêm trọng

Diagnostic thường có một mức độ để người dùng biết vấn đề có ngăn cản xử lý tiếp hay không.

- **Error:** lỗi khiến mô tả không thể được chấp nhận hoặc thực thi an toàn.
- **Warning:** cấu trúc vẫn có thể xử lý, nhưng có nguy cơ tạo hành vi không mong muốn hoặc dùng tính năng sắp bị loại bỏ.
- **Info:** thông tin hỗ trợ người dùng hiểu trạng thái hoặc kết quả.
- **Hint:** gợi ý cải thiện tùy chọn.

| Severity | Ý nghĩa | Hành động thường gặp |
|---|---|---|
| Error | Không thể tiếp tục theo quy tắc hiện tại | Sửa trước khi chạy hoặc biên dịch |
| Warning | Có thể tiếp tục nhưng cần xem xét | Đánh giá rủi ro hoặc thay đổi |
| Info | Thông tin bổ sung | Đọc nếu cần |
| Hint | Gợi ý cải thiện | Có thể áp dụng hoặc bỏ qua |

Mức độ cần phản ánh đúng hậu quả. Nếu mọi thông báo đều là Error, người dùng khó phân biệt vấn đề nghiêm trọng với cảnh báo. Nếu lỗi thực sự lại chỉ là Warning, người dùng có thể bỏ qua và nhận kết quả sai.

## 10. Hiển thị ngữ cảnh và các vị trí liên quan

Một lỗi có thể phụ thuộc vào nhiều phần của DSL. Chỉ đánh dấu vị trí phát hiện cuối cùng đôi khi chưa đủ.

Ví dụ, hai thuộc tính cùng khai báo một khóa:

```text
environment "production" {
    timeout = 30s
}

task "publish" {
    timeout = 90s
    timeout = 120s
}
```

Nếu DSL không cho phép khai báo trùng trong cùng block, diagnostic nên trỏ tới dòng thứ hai và liên kết với dòng khai báo trước đó.

Một diagnostic có thể có:

- **Primary location:** vị trí chính cần người dùng xử lý.
- **Related location:** vị trí khác giúp giải thích nguyên nhân.
- **Context label:** mô tả vai trò của từng vị trí.
- **Origin information:** nguồn cấu hình hoặc khai báo được kế thừa.

Ví dụ:

```text
error DSL-CONFIG-006: timeout được khai báo nhiều lần

  --> task.dsl:7:5
   |
 7 |     timeout = 120s
   |     ^^^^^^^^ khai báo trùng

  --> task.dsl:6:5
   |
 6 |     timeout = 90s
   |     -------- khai báo đầu tiên ở đây

  help: giữ lại một giá trị timeout trong block task.
```

Với cấu hình kế thừa, diagnostic cũng có thể chỉ ra giá trị đến từ block cha hoặc profile nào. Điều này giúp người dùng hiểu vì sao giá trị hiệu lực khác với điều họ nhìn thấy ở vị trí hiện tại.

## 11. Tránh tạo quá nhiều lỗi dây chuyền

Một lỗi ban đầu có thể khiến parser hoặc semantic analyzer không hiểu phần còn lại. Nếu hệ thống tiếp tục phát ra hàng chục lỗi phụ, người dùng khó tìm ra nguyên nhân gốc.

Ví dụ, thiếu dấu đóng ngoặc có thể khiến nhiều dòng sau bị diễn giải sai. Thay vì báo từng token là lỗi độc lập, parser có thể báo lỗi đầu tiên và phục hồi tại một điểm đồng bộ.

### Root cause và cascading errors

- **Root cause:** lỗi gốc gây ra các vấn đề tiếp theo.
- **Cascading error:** lỗi phát sinh do parser hoặc analyzer đã mất cấu trúc đúng sau lỗi trước.

Một công cụ tốt nên ưu tiên lỗi gốc có độ tin cậy cao, tránh báo lại cùng một vấn đề dưới nhiều dạng, gắn lỗi phụ với lỗi gốc khi có thể, tiếp tục phân tích ở vùng có thể phục hồi an toàn và giới hạn số lượng diagnostics nếu đầu vào quá lỗi.

### Error recovery

Parser có thể bỏ qua token đến dấu đóng block hoặc dấu phân cách để tiếp tục. Sau khi phục hồi, nó cần đánh dấu vùng cấu trúc chưa đáng tin cậy để semantic analyzer không tạo quá nhiều lỗi giả từ node bị hỏng.

Thông báo phục hồi nên nói rõ parser đã bỏ qua hoặc không thể phân tích vùng nào. Người dùng cần biết một số kết quả hiển thị sau đó có thể bị ảnh hưởng bởi lỗi trước.

## 12. Diagnostic có cấu trúc và lớp hiển thị

Không nên xây dựng diagnostic chỉ dưới dạng một chuỗi văn bản hoàn chỉnh. Tốt hơn là lưu nội dung có cấu trúc rồi để CLI, IDE hoặc API hiển thị theo cách phù hợp.

Một mô hình khái quát:

```json
{
  "code": "DSL-TYPE-014",
  "severity": "error",
  "message": "timeout cần một giá trị Duration",
  "primaryLocation": {
    "source": "pipeline.dsl",
    "startOffset": 52,
    "endOffset": 58
  },
  "expected": "Duration",
  "found": "String",
  "suggestions": [
    {
      "description": "Dùng 30s nếu muốn chờ 30 giây"
    }
  ]
}
```

Mô hình này chỉ là ví dụ. Một triển khai có thể dùng class, record, protobuf hoặc schema riêng.

### Vì sao nên tách dữ liệu và cách hiển thị?

- CLI có thể in source excerpt và caret.
- IDE có thể gạch chân đoạn nguồn và hiển thị tooltip.
- API có thể trả JSON để client tự render.
- Công cụ CI có thể xuất định dạng tương thích với hệ thống báo cáo.
- Giao diện web có thể nhóm lỗi theo tệp hoặc severity.

Nếu diagnostic chỉ là một chuỗi đã định dạng, mỗi client phải phân tích ngược văn bản để lấy code hoặc vị trí. Điều này dễ hỏng khi câu chữ thay đổi hoặc được dịch.

Cùng một diagnostic có thể được hiển thị ngắn gọn trong editor, chi tiết trong CLI hoặc dưới dạng JSON trong API. Dữ liệu cốt lõi như code, severity và source span vẫn nhất quán.

## 13. Thiết kế diagnostics cho CLI và IDE

### CLI

CLI thường hiển thị danh sách lỗi theo thứ tự tệp và vị trí. Cần cân nhắc:

- Màu sắc không phải cách duy nhất để biểu thị severity.
- Giữ thông tin đọc được khi terminal không hỗ trợ màu.
- Có thể hiển thị source excerpt và dấu mũ.
- Cho phép chế độ ngắn gọn hoặc chi tiết.
- Có thể xuất JSON hoặc định dạng máy đọc được.

Ví dụ:

```text
error[DSL-NAME-004]: không tìm thấy thuộc tính "totla"
 --> rules.dsl:12:15
  |
12 | when order.totla > 100000
  |             ^^^^^
  |
help: có thể bạn muốn viết "total"
```

### IDE hoặc editor

Editor có thể cung cấp gạch chân đoạn lỗi, tooltip chứa message, danh sách diagnostics có thể lọc, điều hướng tới vị trí liên quan, quick fix và cập nhật diagnostics khi văn bản thay đổi.

Editor thường cần parser chịu được đầu vào chưa hoàn chỉnh, vì người dùng có thể đang gõ dở một block hoặc biểu thức. Error recovery và incremental parsing vì vậy đặc biệt hữu ích.

### API và công cụ CI

API nên trả code, severity, message hoặc message key, vị trí nguồn và related locations dưới dạng có cấu trúc. Công cụ CI có thể chuyển chúng thành annotation trên pull request hoặc báo cáo build.

Không nên để client phụ thuộc vào việc so khớp nguyên văn câu message. Code và schema mới là hợp đồng ổn định.

## 14. Quốc tế hóa và ngôn ngữ hiển thị

DSL có thể có từ khóa tiếng Anh nhưng người dùng viết và đọc diagnostics bằng tiếng Việt hoặc ngôn ngữ khác. Vì vậy, cần tách message data khỏi ngôn ngữ hiển thị.

Một diagnostic có thể lưu code và tham số:

```text
code = DSL-TYPE-014
parameters = {
    field: "timeout",
    expectedType: "Duration",
    actualType: "String"
}
```

Lớp hiển thị dùng message template theo locale:

- Tiếng Việt: “Thuộc tính {field} cần kiểu {expectedType}, nhưng nhận được {actualType}.”
- English: “Property {field} expects {expectedType}, but received {actualType}.”

### Những điểm cần chú ý

- Dùng message catalog thay vì ghép chuỗi rải rác trong parser.
- Giữ thuật ngữ nhất quán với tài liệu.
- Xử lý số nhiều và cách sắp xếp câu theo từng ngôn ngữ.
- Không ghép câu bằng cách nối các đoạn dịch riêng lẻ.
- Giữ code lỗi ổn định giữa các locale.
- Hiển thị identifier, literal và source excerpt nguyên bản, trừ khi cần escape để bảo vệ giao diện.

Thông báo được dịch cần giữ đúng ý nghĩa kỹ thuật. Không nên dịch tên token hoặc code nội bộ theo cách làm người dùng không thể tìm kiếm tài liệu tương ứng.

## 15. Bảo mật và quyền riêng tư trong diagnostics

Thông báo lỗi có thể chứa một phần đầu vào hoặc dữ liệu môi trường. Cần hiển thị đủ để người dùng sửa nhưng không làm lộ thông tin nhạy cảm.

Ví dụ, một cấu hình có thể chứa:

```text
database {
    username = "app"
    password = "secret-value"
}
```

Nếu lỗi nằm ở password, không nên in toàn bộ giá trị bí mật ra terminal, log hoặc CI report. Diagnostic có thể chỉ hiển thị tên thuộc tính và loại lỗi:

```text
Giá trị password không đáp ứng chính sách bảo mật.
Không hiển thị nội dung trường này trong thông báo lỗi.
```

Các nguyên tắc:

- Che hoặc bỏ qua secret, token, mật khẩu và dữ liệu cá nhân.
- Không đưa stack trace hoặc đường dẫn nội bộ nhạy cảm vào message dành cho người dùng.
- Escape ký tự điều khiển và nội dung không tin cậy trước khi hiển thị terminal hoặc HTML.
- Giới hạn độ dài source excerpt.
- Không để nội dung DSL điều khiển định dạng terminal hoặc markup.
- Tách thông tin chẩn đoán nội bộ khỏi thông tin công khai.
- Kiểm soát quyền truy cập tới diagnostics và log chi tiết.

Trong môi trường phát triển, chế độ debug có thể cung cấp thêm thông tin kỹ thuật cho người có quyền. Chế độ người dùng cuối nên chỉ hiển thị nội dung cần thiết để hiểu và sửa lỗi.

## 16. Đề xuất và sửa lỗi tự động

Một hệ thống có thể hỗ trợ nhiều mức trợ giúp:

1. **Explanation:** giải thích quy tắc bị vi phạm.
2. **Suggestion:** đưa ra cách sửa có thể cân nhắc.
3. **Quick fix:** cung cấp thao tác chỉnh sửa cụ thể để người dùng chấp nhận.
4. **Automatic fix:** tự áp dụng thay đổi trong ngữ cảnh mà người dùng đã cho phép.

Ví dụ, nếu thiếu dấu phẩy trong danh sách:

```text
regions = ["north" "south"]
```

parser hoặc analyzer có thể đề xuất:

```text
regions = ["north", "south"]
```

Quick fix cần có vùng thay thế rõ ràng và có thể xem trước. Một thay đổi cú pháp đơn giản thường dễ đề xuất hơn một thay đổi nghiệp vụ như đổi mức chiết khấu hoặc thay tên trường.

Nếu tên trường gõ sai nhưng có nhiều trường gần giống, công cụ có thể đưa danh sách gợi ý. Cần sắp xếp theo độ phù hợp và tránh đưa quá nhiều lựa chọn không liên quan. Nếu không có lựa chọn đủ chắc chắn, message nên hướng dẫn tra schema thay vì tự động sửa.

## 17. Nhóm, sắp xếp và giới hạn diagnostics

Một tệp DSL lớn có thể tạo ra nhiều lỗi. Cách sắp xếp ảnh hưởng đến khả năng tìm và xử lý vấn đề.

Các cách nhóm phổ biến:

- Theo tệp và vị trí nguồn.
- Theo severity.
- Theo loại lỗi hoặc error code.
- Theo lỗi gốc và lỗi phụ.
- Theo block hoặc tài nguyên miền.

Một thứ tự thường hữu ích là lỗi ngăn cản parsing trước, sau đó đến lỗi tham chiếu, kiểu và validation. Tuy nhiên, nếu một lỗi ở đầu tệp gây ra nhiều lỗi giả phía sau, nên ưu tiên lỗi gốc thay vì chỉ sắp xếp theo loại.

Nếu có hàng nghìn lỗi, hệ thống có thể hiển thị một số lỗi đầu tiên và cho biết còn bao nhiêu lỗi, nhóm lỗi cùng nguyên nhân, ẩn lỗi dây chuyền có độ tin cậy thấp, cho phép mở rộng danh sách đầy đủ hoặc cung cấp bộ lọc. Không nên âm thầm bỏ lỗi mà không nói rằng kết quả đã bị giới hạn.

## 18. Duy trì chất lượng diagnostics

Thông báo lỗi là một phần của API người dùng, vì vậy cần được duy trì khi grammar và semantics thay đổi.

### Ví dụ lỗi có chủ đích

Mỗi nhóm lỗi quan trọng nên có ví dụ đầu vào và diagnostic mong đợi. Ví dụ giúp duy trì vị trí, code và ý nghĩa thông báo.

### Kiểm tra vị trí nguồn

Với đầu vào có Unicode, tab, comment hoặc nhiều dòng, cần bảo đảm source span trỏ đúng đoạn người dùng nhìn thấy. Cách tính offset và cột cần thống nhất giữa lexer, parser và renderer.

### Giữ message code ổn định

Có thể thay câu chữ để dễ hiểu hơn nhưng cần tránh đổi code hoặc ý nghĩa code tùy tiện. Client và tài liệu bên ngoài có thể phụ thuộc vào mã đó.

### Kiểm tra nhiều locale và định dạng

Một diagnostic nên được hiển thị hợp lý trong CLI, IDE và JSON. Nếu hỗ trợ nhiều ngôn ngữ, cần bảo đảm tham số được chèn đúng và không làm hỏng cấu trúc câu.

### Bảo vệ dữ liệu nhạy cảm

Các trường secret hoặc dữ liệu riêng tư không được xuất hiện ngoài ý muốn trong source excerpt, message hoặc log. Nội dung người dùng cung cấp cần được escape trước khi render.

## 19. Quản lý message khi DSL thay đổi phiên bản

Grammar, type rules và domain model có thể thay đổi. Khi đó, diagnostics cũng cần được quản lý.

Ví dụ, một phiên bản DSL có thuộc tính timeout kiểu số giây, còn phiên bản mới dùng Duration có đơn vị. Một lỗi kiểu cần được diễn đạt theo phiên bản đang xử lý:

- Phiên bản cũ: “timeout cần số giây.”
- Phiên bản mới: “timeout cần giá trị thời lượng như 30s hoặc 2m.”

Một số nguyên tắc:

- Gắn diagnostic với phiên bản grammar hoặc schema phù hợp.
- Giữ mã lỗi ổn định khi ý nghĩa lỗi không đổi.
- Cập nhật message khi quy tắc hoặc thuật ngữ miền thay đổi.
- Nêu rõ tính năng deprecated và phiên bản dự kiến loại bỏ.
- Không để một code cũ mang ý nghĩa khác mà không có kế hoạch tương thích.
- Tài liệu hóa các thay đổi có thể ảnh hưởng tới automation hoặc editor.

Nếu client tự xử lý code lỗi, schema diagnostic cũng cần có version hoặc chính sách tương thích rõ ràng.

## 20. Quy trình thiết kế một thông báo dễ hiểu

Khi một thành phần DSL phát hiện lỗi, có thể đi theo trình tự:

1. Xác định giai đoạn phát hiện: lexer, parser, semantic analysis, type checker, validator hay runtime.
2. Xác định nguyên nhân gần nhất và phân biệt với lỗi dây chuyền.
3. Chọn source span chính xác và các vị trí liên quan.
4. Xác định điều hệ thống mong đợi.
5. Ghi nhận đầu vào thực tế, có che dữ liệu nhạy cảm nếu cần.
6. Viết message ngắn bằng thuật ngữ phù hợp với người dùng.
7. Thêm explanation nếu nguyên nhân chưa rõ từ message chính.
8. Đưa suggestion chỉ khi có cơ sở đủ tin cậy.
9. Gán severity và mã lỗi ổn định.
10. Chuyển diagnostic có cấu trúc cho CLI, IDE hoặc API.
11. Render theo locale và định dạng mà client hỗ trợ.
12. Giữ message, code và vị trí nhất quán qua các phiên bản.

Một message nên trả lời được ba câu hỏi: “Điều gì sai?”, “Nó nằm ở đâu?” và “Tôi có thể làm gì tiếp theo?”. Với lỗi phức tạp, thêm “Vì sao điều này không hợp lệ?” và “Nó liên quan tới phần nào khác?” sẽ giúp người dùng hiểu đầy đủ hơn.

## 21. Những nhầm lẫn thường gặp

**Chỉ ghi “Syntax error”.** Người dùng không biết parser đang mong đợi điều gì. Hãy nêu token hoặc cấu trúc cần có và vị trí lỗi.

**Hiển thị tên lớp hoặc production nội bộ.** Thông tin như RuleBlockContext có thể hữu ích cho người phát triển parser nhưng không giúp người dùng DSL. Hãy chuyển thành thuật ngữ miền.

**Không hiển thị source location.** Người dùng phải tìm thủ công trong tệp dài. Cần có dòng, cột hoặc source span.

**Trộn lỗi cú pháp và lỗi ngữ nghĩa.** Một thuộc tính không tồn tại không nhất thiết là lỗi parser. Gọi đúng loại lỗi giúp người dùng tìm đúng phần cần sửa.

**Hiển thị quá nhiều token mong đợi.** Danh sách nội bộ dài khiến message khó đọc. Nên nhóm theo khái niệm hoặc hiển thị chi tiết trong phần mở rộng.

**Đề xuất sửa sai quá tự tin.** Một tên gần giống không bảo đảm là tên người dùng định viết. Hãy đưa suggestion có căn cứ và cho phép xem trước.

**Báo nhiều lỗi dây chuyền.** Một lỗi gốc có thể làm các dòng sau bị phân tích sai. Cần phục hồi có kiểm soát và ưu tiên nguyên nhân chính.

**Để message phụ thuộc vào ngôn ngữ hiển thị.** Client không nên phân tích chuỗi tiếng Việt hoặc tiếng Anh để nhận diện lỗi. Hãy dùng diagnostic code và schema ổn định.

**Làm lộ secret trong source excerpt.** Chỉ hiển thị phần cần thiết, che dữ liệu nhạy cảm và escape nội dung không tin cậy.

**Dùng cùng một severity cho mọi vấn đề.** Người dùng cần phân biệt lỗi chặn thực thi với cảnh báo hoặc gợi ý.

## 22. Câu hỏi tự kiểm tra

1. Diagnostic là gì và khác log hoặc exception như thế nào?
2. Một diagnostic dễ hiểu thường có những thành phần nào?
3. Vì sao source span quan trọng với DSL dạng văn bản?
4. Expected và found giúp người dùng hiểu lỗi ra sao?
5. Phân biệt lỗi lexical, syntax, name resolution, type, domain validation và runtime.
6. Khi nào nên đưa suggestion hoặc quick fix?
7. Vì sao diagnostic code cần ổn định?
8. Error và warning khác nhau ở hậu quả nào?
9. Làm thế nào để liên kết một lỗi với các vị trí nguồn liên quan?
10. Vì sao parser cần tránh tạo quá nhiều cascading errors?
11. Tại sao nên lưu diagnostic có cấu trúc thay vì chỉ tạo một chuỗi?
12. CLI, IDE và API có thể hiển thị cùng diagnostic theo những cách nào?
13. Cần lưu ý gì khi hiển thị diagnostics bằng nhiều ngôn ngữ?
14. Làm thế nào để tránh làm lộ secret trong thông báo lỗi?
15. Một diagnostic tốt nên trả lời những câu hỏi nào để người dùng có thể tự sửa vấn đề?

Khi thiết kế được thông báo dễ hiểu, DSL không chỉ phát hiện lỗi chính xác mà còn giúp người dùng hiểu quy tắc của ngôn ngữ, xác định đúng vị trí cần sửa và tiếp tục công việc với ít gián đoạn hơn.
