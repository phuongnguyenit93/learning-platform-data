# Tài liệu lỗi trong DSL

Một ngôn ngữ đặc tả miền (Domain-Specific Language, DSL) không chỉ cần cú pháp dễ học và runtime đáng tin cậy. Khi người dùng viết source, cấu hình, rule hoặc workflow, họ cũng cần hiểu điều gì đã xảy ra khi chương trình không hợp lệ hoặc không thể thực thi. Một compiler có thể phát hiện lỗi rất chính xác nhưng nếu chỉ trả về một dòng như "parse failed", người dùng vẫn không biết cần sửa ở đâu. Vì vậy, **tài liệu lỗi** là một phần quan trọng của trải nghiệm ngôn ngữ: nó giải thích các lỗi có thể xuất hiện, cách nhận diện, nguyên nhân thường gặp, cách khắc phục và cách tiếp tục làm việc.

Tài liệu lỗi (*error documentation*) là tập nội dung có cấu trúc mô tả diagnostics và failure modes của DSL. Nó liên kết mã lỗi ổn định với thông báo, vị trí source, ngữ cảnh, nguyên nhân, hướng sửa, ví dụ và thông tin phiên bản. Tài liệu này có thể được trình bày dưới dạng error reference, troubleshooting guide, hướng dẫn theo giai đoạn compiler/runtime, hoặc nội dung trợ giúp trực tiếp trong editor.

Tài liệu lỗi tốt giúp người dùng tự giải quyết vấn đề, giảm thời gian hỗ trợ và tạo sự nhất quán giữa compiler, runtime, API, CLI và IDE. Nó cũng giúp đội ngũ phát triển thay đổi diagnostics có kiểm soát: mã lỗi và semantics được quản lý như một phần của public contract thay vì chỉ là chuỗi thông báo tùy ý.

## 1. Vai trò của tài liệu lỗi

### 1.1. Giúp người dùng hiểu và sửa lỗi

Một lỗi hữu ích cần trả lời các câu hỏi:
- Điều gì không hợp lệ?
- Lỗi xuất hiện ở đâu?
- Vì sao hệ thống phát hiện lỗi?
- Người dùng có thể làm gì để sửa?
- Có trường hợp hợp lệ nào trông tương tự không?
- Nếu không thể sửa ngay, có cách nào tiếp tục hoặc thu thập thêm thông tin?

Thông báo ngắn giúp nhận biết vấn đề, còn tài liệu lỗi giải thích sâu hơn và đưa ra hướng xử lý.

### 1.2. Giảm thời gian chẩn đoán

Nếu mỗi lỗi có code ổn định và trang tài liệu tương ứng, người dùng có thể tìm theo code thay vì đoán từ một thông báo có thể thay đổi theo phiên bản hoặc ngôn ngữ.

### 1.3. Hỗ trợ nhiều công cụ

Cùng một diagnostic có thể xuất hiện trong:
- CLI.
- IDE hoặc language server.
- Build pipeline.
- API response.
- Runtime log.
- Web console.
- CI report.

Một taxonomy và error code thống nhất giúp các công cụ liên kết đến cùng nội dung.

### 1.4. Giữ hành vi nhất quán

Khi error code, severity và message structure được định nghĩa, compiler và runtime ít có khả năng dùng nhiều cách gọi khác nhau cho cùng một lỗi.

### 1.5. Hỗ trợ người mới học DSL

Người mới thường chưa biết phân biệt lỗi lexical, syntax, type và runtime. Tài liệu lỗi có thể giải thích giai đoạn phát hiện lỗi, cung cấp ví dụ trước/sau và chỉ ra kiến thức nền cần xem lại.

### 1.6. Hỗ trợ maintainers

Tài liệu lỗi cũng là công cụ nội bộ:
- Làm rõ semantics của validator.
- Giúp reviewer hiểu lý do phát sinh diagnostic.
- Hạn chế thay đổi mã lỗi tùy tiện.
- Làm cơ sở cho regression tests.
- Hỗ trợ phân tích issue và support ticket.

## 2. Error, exception và diagnostic

### 2.1. Error

Error là trạng thái hoặc điều kiện cho thấy thao tác không thể hoàn tất theo contract. Ví dụ source không đúng grammar, field không tồn tại, caller không có quyền hoặc database không khả dụng.

### 2.2. Exception

Exception là cơ chế kỹ thuật mà implementation dùng để truyền hoặc biểu diễn một tình huống bất thường. Không phải exception nào cũng nên được hiển thị trực tiếp cho người dùng.

Ví dụ, lỗi kết nối database có thể tạo SQLException nội bộ, nhưng API nên chuyển nó thành diagnostic hoặc error response có code ổn định.

### 2.3. Diagnostic

Diagnostic là bản ghi có cấu trúc mô tả một vấn đề hoặc cảnh báo trong source hoặc quá trình xử lý. Nó thường chứa:
- Code.
- Severity.
- Message.
- Source span.
- Related location.
- Context.
- Suggested fix.
- Documentation reference.

### 2.4. Warning và error

Warning cảnh báo về hành vi có thể không mong muốn nhưng không nhất thiết ngăn chương trình chạy. Error thường làm compilation, validation hoặc execution thất bại. Severity cần có semantics rõ.

### 2.5. Diagnostic không phải stack trace

Stack trace phục vụ debugging implementation. Người dùng DSL thường cần message nghiệp vụ, source location và cách sửa. Stack trace có thể được lưu trong log nội bộ nhưng không nên trả thẳng cho client hoặc hiển thị mặc định.

### 2.6. Lỗi có thể phục hồi

Một số lỗi cho phép tiếp tục:
- Lexer bỏ qua ký tự sai và tiếp tục ở delimiter.
- Parser đồng bộ lại ở dấu chấm phẩy.
- Batch validator trả lỗi từng record.
- Runtime bỏ qua một rule optional theo policy.

Tài liệu cần nói rõ lỗi nào ngăn xử lý và lỗi nào có thể phục hồi.

## 3. Phân loại lỗi theo giai đoạn DSL

### 3.1. Lỗi encoding và source loading

Xảy ra trước hoặc trong khi đọc source:
- Encoding không được hỗ trợ.
- File không tồn tại.
- Không có quyền đọc.
- Source quá lớn.
- Include path không hợp lệ.
- File bị cắt hoặc không hoàn chỉnh.

### 3.2. Lỗi lexical

Lexer không thể nhận diện một chuỗi ký tự thành token hợp lệ:
- Ký tự không được hỗ trợ.
- String chưa đóng.
- Escape sequence sai.
- Numeric literal sai định dạng.
- Comment chưa kết thúc.

### 3.3. Lỗi syntax

Parser nhận token stream nhưng không thể xây dựng cấu trúc theo grammar:
- Thiếu dấu ngoặc.
- Thiếu keyword.
- Sai thứ tự thành phần.
- Biểu thức không hoàn chỉnh.
- Dấu phân cách thừa.

### 3.4. Lỗi semantic

Cấu trúc cú pháp hợp lệ nhưng ý nghĩa không hợp lệ:
- Tham chiếu biến chưa khai báo.
- Gọi function không tồn tại.
- Field không có trong type.
- Hai nhánh trả kiểu không tương thích.
- Rule có trạng thái không thể đạt tới.

### 3.5. Lỗi type checking

Các biểu thức dùng kiểu không phù hợp:
- So sánh Boolean với Money.
- Gán String vào Integer.
- Truyền sai kiểu argument.
- Trộn đơn vị không tương thích.
- Sử dụng nullable value như non-nullable.

### 3.6. Lỗi validation

Mô hình hoặc payload không thỏa constraint:
- Thiếu field bắt buộc.
- Giá trị ngoài range.
- Chuỗi vượt độ dài.
- Enum value không được hỗ trợ.
- Quan hệ dữ liệu không hợp lệ.

### 3.7. Lỗi compile và code generation

Chương trình có thể qua parse và type-check nhưng không thể tạo artifact:
- Backend không hỗ trợ node IR.
- Target platform không tương thích.
- Dependency không được resolve.
- Code generation thất bại.
- Artifact vượt giới hạn.

### 3.8. Lỗi runtime

Chỉ xuất hiện khi chương trình chạy:
- Chia cho zero.
- Dữ liệu tham chiếu không tồn tại.
- Timeout.
- Resource limit.
- External service unavailable.
- Plugin failure.
- State transition không hợp lệ.

### 3.9. Lỗi authorization và security

Ví dụ:
- Caller không có quyền gọi function.
- Resource thuộc tenant khác.
- Capability chưa được cấp.
- Plugin signature không hợp lệ.
- Runtime từ chối operation nguy hiểm.

### 3.10. Lỗi deployment và packaging

Ví dụ:
- Package manifest sai.
- Plugin version không tương thích.
- Thiếu runtime dependency.
- Checksum không khớp.
- Cấu hình môi trường thiếu.
- Migration không hoàn tất.

## 4. Thiết kế taxonomy và error code

### 4.1. Vì sao cần mã lỗi?

Thông báo có thể được viết lại, dịch hoặc điều chỉnh để dễ hiểu. Error code ổn định cho phép:
- Tìm trang tài liệu.
- Viết test không phụ thuộc wording.
- Thống kê theo loại lỗi.
- Liên kết support ticket.
- Giữ tương thích giữa CLI và IDE.

### 4.2. Cấu trúc mã

Một hệ thống có thể dùng prefix theo subsystem và nhóm lỗi:

~~~text
DSL-LEX-001   Ký tự không hợp lệ
DSL-PARSE-004 Thiếu dấu đóng ngoặc
DSL-TYPE-012  Kiểu argument không tương thích
DSL-RUN-003   Vượt thời gian thực thi
DSL-AUTH-002  Không có quyền truy cập resource
~~~

Định dạng này chỉ là ví dụ. Điều quan trọng là code duy nhất, ổn định và có quy tắc cấp phát.

### 4.3. Namespace

Có thể chia namespace theo:
- LEX: lexer.
- PARSE: parser.
- NAME: name resolution.
- TYPE: type checking.
- VALID: validation.
- COMPILE: compiler/backend.
- RUN: runtime.
- API: API contract.
- AUTH: authorization.
- PKG: package/deployment.

Không nên tạo prefix quá chi tiết nếu nó làm taxonomy khó quản lý.

### 4.4. Không tái sử dụng code

Một code đã được công bố không nên đổi nghĩa để dùng cho lỗi khác. Nếu diagnostic bị loại bỏ, giữ code ở trạng thái retired hoặc reserved để lịch sử và công cụ không diễn giải sai.

### 4.5. Mã lỗi và severity

Severity thường gồm:
- Error.
- Warning.
- Information.
- Hint.

Severity có thể khác theo context, nhưng code cần giữ semantics ổn định. Ví dụ một warning trong editor có thể được nâng thành error bởi strict build mode; điều này cần được ghi rõ.

### 4.6. Error code không phải thông điệp

Không nhúng toàn bộ nội dung message vào code. Code là định danh; message là cách diễn đạt. Không dùng message text làm API key vì wording có thể thay đổi.

### 4.7. Registry lỗi

Duy trì một registry trung tâm gồm code, title, subsystem, severity mặc định, introduced version, deprecated version, owner và documentation URL hoặc slug.

## 5. Cấu trúc một trang tài liệu lỗi

Một trang error reference nên có cấu trúc nhất quán.

### 5.1. Tiêu đề và code

Hiển thị code và tên ngắn:
- DSL-PARSE-004 — Thiếu dấu đóng ngoặc.

### 5.2. Thông báo mẫu

Đưa ra message thực tế mà người dùng có thể thấy, bao gồm vị trí:
~~~text
policy.dsl:12:5: error DSL-PARSE-004:
Expected ')' to close this expression.
~~~

### 5.3. Ý nghĩa

Giải thích lỗi biểu thị điều gì bằng ngôn ngữ rõ ràng, tránh lặp lại nguyên văn message.

### 5.4. Nguyên nhân thường gặp

Liệt kê các nguyên nhân có khả năng xảy ra. Phân biệt nguyên nhân chắc chắn với khả năng cần kiểm tra.

### 5.5. Cách khắc phục

Đưa ra các bước cụ thể theo thứ tự:
1. Mở file và đến vị trí báo lỗi.
2. Kiểm tra construct đang mở.
3. Thêm delimiter còn thiếu hoặc sửa biểu thức.
4. Chạy lại validator.

### 5.6. Ví dụ sai

~~~text
when (order.total >= 100000
then fee = 0
~~~

### 5.7. Ví dụ đúng

~~~text
when (order.total >= 100000)
then fee = 0
~~~

### 5.8. Ghi chú phiên bản

Nêu phiên bản bắt đầu có lỗi, thay đổi message hoặc behavior nếu có, và version có thể ảnh hưởng.

### 5.9. Liên kết liên quan

Liên kết đến:
- Grammar reference.
- Tutorial của construct.
- Type system guide.
- Troubleshooting.
- Release note hoặc migration guide.

### 5.10. Khi nào cần báo lỗi

Nếu đã làm theo hướng dẫn nhưng lỗi vẫn xảy ra, yêu cầu người dùng cung cấp error code, DSL version, tool version, source snippet đã loại bỏ dữ liệu nhạy cảm và reproduction steps.

## 6. Viết thông báo lỗi hữu ích

### 6.1. Mô tả điều hệ thống mong đợi

Thông báo nên nói expected token, type hoặc condition:
~~~text
Expected ')' after the condition.
~~~

Tốt hơn câu chung chung:
~~~text
Invalid syntax.
~~~

### 6.2. Nêu vị trí chính xác

Ưu tiên underline span liên quan. Nếu lỗi được phát hiện ở vị trí sau đó, thêm related location trỏ về nơi construct bắt đầu.

### 6.3. Dùng thuật ngữ của DSL

Dùng tên keyword, field và type mà người dùng thấy trong source. Tránh expose tên class hoặc method nội bộ.

### 6.4. Không đoán quá chắc

Nếu compiler không biết chính xác nguyên nhân, dùng wording như "The expression may be missing..." thay vì khẳng định một nguyên nhân duy nhất.

### 6.5. Đề xuất sửa có điều kiện

Suggested fix chỉ nên xuất hiện khi hệ thống có đủ bằng chứng. Một quick fix sai có thể làm thay đổi semantics.

### 6.6. Tránh message quá dài

Message inline nên ngắn. Giải thích sâu, ví dụ và nhiều nguyên nhân thuộc trang tài liệu liên kết.

### 6.7. Phân biệt expected và actual

Ví dụ:
~~~text
Expected Integer but found String.
Field: order.quantity
~~~

Thông tin expected/actual giúp người dùng hiểu type mismatch nhanh hơn.

### 6.8. Không đổ lỗi cho người dùng

Thông báo nên mô tả vấn đề trong source hoặc context, không dùng giọng phán xét như "You wrote this incorrectly".

### 6.9. Không hiển thị implementation detail

Không trả SQL query, stack trace, filesystem path nội bộ, secret, connection string hoặc class name nhạy cảm trong message công khai.

## 7. Source location và diagnostic span

### 7.1. File, line và column

Tài liệu lỗi cần giải thích quy ước vị trí:
- Line bắt đầu từ 1 hay 0.
- Column bắt đầu từ 1 hay 0.
- Offset tính theo byte, UTF-16 hay code point.
- Tab được hiển thị theo width nào.

### 7.2. Primary span

Primary span chỉ vị trí trực tiếp gây lỗi. Span nên đủ ngắn để người dùng biết cần nhìn vào đâu.

### 7.3. Related span

Một lỗi có thể liên quan đến hai vị trí. Ví dụ duplicate declaration cần highlight cả khai báo mới và khai báo trước.

### 7.4. EOF diagnostics

Khi thiếu dấu đóng ngoặc ở cuối file, vị trí có thể là EOF zero-width. Tài liệu nên giải thích rằng lỗi được phát hiện tại điểm parser cần token tiếp theo.

### 7.5. Generated source và source map

Nếu DSL được preprocess hoặc include, diagnostic cần chỉ ra file gốc hoặc cung cấp mapping. Tài liệu cần nói vị trí hiển thị là generated source hay source author viết.

### 7.6. Unicode

Offset của một ký tự Unicode có thể khác giữa UTF-8 byte và UTF-16 code unit. Nếu người dùng báo vị trí lệch, cần biết tool nào đang hiển thị và đơn vị offset.

## 8. Lỗi lexer và cách tài liệu hóa

### 8.1. Invalid character

Code mẫu: DSL-LEX-001.

Giải thích:
- Ký tự không thuộc character set của token hợp lệ tại vị trí hiện tại.
- Kiểm tra encoding, ký tự copy từ tài liệu hoặc ký tự Unicode gần giống.
- Nếu cần dùng ký tự đó, xem grammar của identifier hoặc string.

### 8.2. Unterminated string

Code mẫu: DSL-LEX-002.

Nguyên nhân:
- Thiếu quote kết thúc.
- Escape làm thay đổi cách lexer nhận delimiter.
- String multiline không được hỗ trợ.

Hướng sửa:
- Đóng string.
- Dùng escape sequence đúng.
- Chuyển sang multiline syntax nếu DSL hỗ trợ.

### 8.3. Invalid escape

Code mẫu: DSL-LEX-003.

Tài liệu cần liệt kê escape hợp lệ và cho ví dụ trước/sau. Không chỉ nói "invalid escape sequence".

### 8.4. Invalid numeric literal

Code mẫu: DSL-LEX-004.

Nêu format number được hỗ trợ, exponent, underscore, decimal separator và giới hạn. Phân biệt sai lexical format với overflow khi chuyển sang kiểu số.

### 8.5. Unterminated comment

Code mẫu: DSL-LEX-005.

Chỉ ra vị trí comment bắt đầu, delimiter kết thúc cần có và liệu nested comment có được hỗ trợ không.

### 8.6. Unicode identifier error

Giải thích character class được phép, normalization policy và cách thay ký tự không hợp lệ bằng tên hợp lệ.

## 9. Lỗi parser và cú pháp

### 9.1. Unexpected token

Tài liệu cần giải thích token nào xuất hiện, parser đang chờ nhóm token nào và ví dụ cấu trúc hợp lệ.

### 9.2. Missing delimiter

Ví dụ thiếu ), ], } hoặc dấu phẩy. Nêu nơi construct bắt đầu và nơi parser phát hiện thiếu delimiter.

### 9.3. Missing keyword

Nếu block cần when hoặc then, giải thích thứ tự thành phần và ví dụ đúng.

### 9.4. Unexpected end of file

Nguyên nhân thường là block, string hoặc expression chưa hoàn chỉnh. Tài liệu nên liên kết đến trang về construct tương ứng.

### 9.5. Ambiguous syntax

Nếu grammar không xác định được cách parse, giải thích precedence hoặc yêu cầu dấu ngoặc để làm rõ.

### 9.6. Error recovery

Trong editor, parser có thể tiếp tục sau lỗi để hiển thị nhiều diagnostic. Tài liệu nên phân biệt diagnostic đầu tiên với lỗi phát sinh do recovery.

### 9.7. Quick fix

Nếu có thể tự thêm dấu đóng ngoặc, mô tả cách preview và áp dụng. Không tự động thay đổi source nếu người dùng chưa xác nhận theo policy của editor.

## 10. Lỗi name resolution và semantic

### 10.1. Unknown identifier

Code mẫu: DSL-NAME-001.

Thông báo cần nêu tên symbol và scope:
~~~text
Unknown field 'totla' on type Order.
Did you mean 'total'?
~~~

Gợi ý gần đúng chỉ nên hiển thị khi độ tin cậy đủ cao.

### 10.2. Undefined variable

Nêu nơi sử dụng, scope hiện tại và cách khai báo hoặc truyền parameter.

### 10.3. Duplicate declaration

Highlight khai báo trùng và khai báo gốc. Giải thích quy tắc uniqueness và phạm vi áp dụng.

### 10.4. Unknown function

Hiển thị function name, namespace và danh sách overload phù hợp nếu an toàn.

### 10.5. Invalid member access

Giải thích type của receiver và member không tồn tại. Ví dụ customer.address.zipCode nếu Address không có field zipCode.

### 10.6. Unreachable rule

Nếu analyzer phát hiện rule không bao giờ được chạy do rule trước bao phủ toàn bộ điều kiện, giải thích điều kiện xung đột và cách sắp xếp hoặc sửa rule.

### 10.7. Circular dependency

Nêu các symbol hoặc module tạo cycle, cách tìm dependency path và các cách phá vòng lặp.

## 11. Lỗi type checking

### 11.1. Type mismatch

Code mẫu: DSL-TYPE-001.

~~~text
Expected Integer but found String.
Expression: order.quantity
~~~

Tài liệu nên chỉ ra:
- Kiểu được mong đợi.
- Kiểu thực tế.
- Vị trí.
- Conversion được hỗ trợ nếu có.
- Vì sao không tự chuyển đổi.

### 11.2. Argument count mismatch

Hiển thị function signature, số argument mong đợi và số thực tế. Với overload, chỉ ra candidate gần phù hợp.

### 11.3. Nullability violation

Giải thích vì sao giá trị có thể null được dùng ở vị trí yêu cầu non-null. Đề xuất null check hoặc default có semantics rõ.

### 11.4. Unit mismatch

Ví dụ cộng Money VND với Money USD hoặc so sánh meter với kilogram. Nêu đơn vị mong đợi và conversion hợp lệ nếu có.

### 11.5. Generic type mismatch

Giải thích type parameter được suy luận và constraint không thỏa. Tránh chỉ hiển thị tên type nội bộ khó hiểu.

### 11.6. Ambiguous overload

Nêu các overload phù hợp và yêu cầu người dùng chỉ rõ kiểu hoặc chuyển đổi. Không chọn ngẫu nhiên một overload.

### 11.7. Conversion failure

Phân biệt conversion được cho phép nhưng giá trị cụ thể không chuyển được với conversion vốn không hợp lệ theo type system.

## 12. Lỗi validation và payload

### 12.1. Required field missing

Nêu field path, schema và cách cung cấp field. Phân biệt missing với null nếu API có semantics riêng.

### 12.2. Value out of range

Hiển thị constraint và actual value khi không nhạy cảm:
~~~text
Field 'quantity' must be between 1 and 1000.
Received: 0.
~~~

### 12.3. Invalid enum

Liệt kê các giá trị được hỗ trợ nếu danh sách không nhạy cảm và có kích thước hợp lý.

### 12.4. Invalid format

Nêu format kỳ vọng, ví dụ date theo ISO format, identifier hoặc currency code.

### 12.5. Cross-field validation

Nếu startDate phải trước endDate, nêu cả hai field và mối quan hệ vi phạm, không chỉ highlight field thứ hai.

### 12.6. Unknown field

Giải thích schema strict hay lenient. Nếu có field gần giống, đề xuất spelling phù hợp.

### 12.7. Schema version mismatch

Nêu schema version được yêu cầu, version được cung cấp và hướng migration.

## 13. Lỗi runtime và external dependency

### 13.1. Runtime failure

Tài liệu cần phân biệt lỗi do source, dữ liệu runtime, resource hoặc dependency ngoài. Cùng một source có thể chạy thành công với input khác.

### 13.2. Division by zero

Nêu expression, vị trí và điều kiện dữ liệu gây chia cho zero. Hướng sửa có thể là guard hoặc xử lý zero theo nghiệp vụ.

### 13.3. Missing runtime data

Nếu field hoặc record không có trong context, nêu data key, nguồn dự kiến và cách cung cấp. Không hiển thị dữ liệu nhạy cảm.

### 13.4. Timeout

Nêu operation bị timeout, limit hiện tại và cách kiểm tra query hoặc expression. Không khuyến khích tăng timeout vô hạn.

### 13.5. Resource limit

Giải thích limit CPU, memory, recursion, query rows hoặc output size. Đưa cách giảm complexity hoặc chia workload.

### 13.6. External service unavailable

Nêu dependency logic, request/correlation ID và retry policy. Phân biệt lỗi transient với lỗi cấu hình hoặc authorization.

### 13.7. Plugin failure

Nêu plugin ID và version, extension point, lifecycle phase và cách kiểm tra compatibility. Không hiển thị secret hoặc internal stack trace mặc định.

### 13.8. Non-deterministic failure

Nếu kết quả phụ thuộc thời gian, concurrency hoặc external state, hướng dẫn thu thập timestamp, policy version và correlation ID để tái hiện.

## 14. Lỗi authorization và security

### 14.1. Permission denied

Giải thích action và resource bị từ chối, nhưng không tiết lộ thông tin mà caller không được quyền biết.

### 14.2. Tenant boundary

Không tiết lộ resource có tồn tại trong tenant khác. Message có thể dùng wording chung và correlation ID để support điều tra.

### 14.3. Capability unavailable

Nêu capability cần thiết và cách admin cấp quyền theo policy. Không đề xuất vô hiệu hóa kiểm soát bảo mật để tránh lỗi.

### 14.4. Injection rejected

Nếu runtime từ chối expression hoặc query có cấu trúc không an toàn, giải thích input nào không được chấp nhận và cách dùng parameter hoặc API được hỗ trợ.

### 14.5. Signature hoặc package trust failure

Nêu package identity, version và loại xác minh thất bại. Không hướng dẫn bỏ qua signature validation trong môi trường production.

### 14.6. Security-sensitive diagnostics

Message công khai không nên tiết lộ:
- Stack trace.
- SQL hoặc command đầy đủ.
- Secret/token.
- Internal path.
- Hostname nội bộ.
- Dữ liệu cá nhân.
- Quy tắc bảo vệ có thể giúp vượt qua kiểm soát.

## 15. Lỗi API và CLI

### 15.1. Error response schema

API nên có cấu trúc nhất quán:
~~~json
{
  "type": "https://docs.example.invalid/errors/validation",
  "title": "Payload validation failed",
  "status": 400,
  "code": "DSL-VALID-002",
  "detail": "One or more fields do not satisfy the schema.",
  "correlationId": "req-902",
  "errors": [
    {
      "field": "order.quantity",
      "code": "MINIMUM_VALUE",
      "message": "Quantity must be at least 1."
    }
  ]
}
~~~

### 15.2. HTTP status và DSL error code

HTTP status mô tả lớp lỗi giao thức. DSL error code mô tả vấn đề cụ thể. Không nên dùng HTTP status như mã lỗi duy nhất.

### 15.3. CLI exit code

CLI có thể phân biệt:
- Source/compile error.
- Runtime error.
- Configuration error.
- Authentication/authorization error.
- Internal failure.

Tài liệu cần liệt kê exit code ổn định và cách dùng trong CI.

### 15.4. Machine-readable output

JSON diagnostic output giúp IDE và CI tích hợp. Schema output cần version và có ví dụ.

### 15.5. Correlation ID

Khi lỗi liên quan server, trả correlation ID để người dùng gửi support. ID không được chứa thông tin nhạy cảm.

### 15.6. Retry guidance

Chỉ gợi ý retry với lỗi transient. Validation, type mismatch hoặc permission denied thường không được giải quyết bằng retry.

## 16. Troubleshooting guide

### 16.1. Sắp xếp theo triệu chứng

Người dùng thường tìm theo điều họ thấy:
- Không parse được file.
- Không tìm thấy field.
- Type mismatch.
- Rule không chạy.
- Runtime timeout.
- Plugin không load.
- API trả 400 hoặc 403.

Trang troubleshooting có thể liên kết đến nhiều error code liên quan.

### 16.2. Cây quyết định

Ví dụ khi rule không tạo kết quả:
1. Source có compile thành công không?
2. Có diagnostic hoặc warning không?
3. Rule có được kích hoạt không?
4. Input có đủ field không?
5. Condition có đúng không?
6. Có conflict resolver không?
7. Runtime có lỗi dependency hoặc permission không?

### 16.3. Phân biệt lỗi và kết quả hợp lệ

Không có rule nào khớp có thể là kết quả hợp lệ nếu policy định nghĩa no-match. Không nên hiển thị nó như runtime error nếu đó là behavior dự kiến.

### 16.4. Thu thập reproduction

Hướng dẫn tạo reproduction tối thiểu:
- DSL snippet nhỏ.
- Input đã ẩn danh.
- DSL/compiler/runtime version.
- Command hoặc API request.
- Expected và actual result.
- Correlation ID nếu có.

### 16.5. Không yêu cầu dữ liệu bí mật

Không yêu cầu người dùng gửi token, password, production data hoặc file chứa thông tin cá nhân. Hướng dẫn redact trước khi chia sẻ.

## 17. Tổ chức website hoặc help center

### 17.1. Error reference index

Trang index có thể nhóm theo subsystem và hỗ trợ tìm theo code.

### 17.2. Trang theo code

Mỗi code có URL ổn định, ví dụ:
~~~text
/docs/errors/DSL-TYPE-001
~~~

Nếu URL thay đổi, cần redirect hoặc giữ alias.

### 17.3. Trang theo giai đoạn

Người học có thể đi theo:
- Source loading.
- Lexing.
- Parsing.
- Semantic analysis.
- Type checking.
- Compilation.
- Runtime.
- Deployment.

### 17.4. Search

Search nên tìm theo code, message fragment, keyword, subsystem và version. Error code cần được index chính xác.

### 17.5. Navigation

Từ error message trong IDE hoặc CLI có thể mở trang tương ứng. Trang tài liệu nên có breadcrumb về chủ đề và bài học liên quan.

### 17.6. Version selector

Tài liệu lỗi phải khớp DSL version. Người dùng phiên bản cũ không nên bị đưa đến hướng dẫn chỉ đúng cho version mới.

### 17.7. Offline documentation

Với môi trường air-gapped, có thể đóng gói error reference cùng toolchain hoặc cung cấp bản HTML/Markdown offline.

## 18. Localization và ngôn ngữ thông báo

### 18.1. Stable code, localized message

Code giữ ổn định; message và tài liệu có thể được dịch. Test nên dựa vào code và structured fields thay vì một chuỗi đã dịch.

### 18.2. Translation key

Có thể dùng key như DSL.TYPE.MISMATCH để quản lý message catalog. Key nội bộ không nhất thiết là public error code.

### 18.3. Terminology glossary

Duy trì glossary cho các từ như token, expression, scope, type, runtime và capability để bản dịch nhất quán.

### 18.4. Message interpolation

Placeholder cần có type và format rõ. Ví dụ expectedType và actualType không nên được ghép tùy tiện vào chuỗi làm hỏng ngữ pháp ở ngôn ngữ khác.

### 18.5. Fallback locale

Nếu không có bản dịch, dùng locale mặc định đã công bố. Không để thiếu translation làm mất diagnostic hoặc gây crash.

### 18.6. Documentation translation

Bản dịch cần theo version và trạng thái cập nhật. Có thể hiển thị ngày đồng bộ hoặc cảnh báo khi nội dung bản dịch cũ hơn bản gốc.

## 19. Versioning và lifecycle của error documentation

### 19.1. Error code registry version

Registry cần được version cùng sản phẩm hoặc đặc tả. Ghi nhận code mới, code deprecated và code retired.

### 19.2. Thay đổi message

Có thể cải thiện wording mà không đổi code nếu semantics không đổi. Tuy nhiên, message là một phần UX và có thể được test snapshot; cần release note khi thay đổi ảnh hưởng lớn.

### 19.3. Thay đổi semantics

Nếu cùng code bắt đầu mô tả một điều kiện khác, nên cấp code mới hoặc có migration rõ. Không âm thầm đổi nghĩa.

### 19.4. Deprecation

Nếu diagnostic không còn được phát, đánh dấu retired trong registry và giữ trang cũ để người dùng version cũ vẫn tra được.

### 19.5. Version-specific docs

Mỗi release cần liên kết đến error reference phù hợp. Có thể dùng /latest và /version/4.x, nhưng /latest không nên là link duy nhất trong diagnostic của artifact cũ.

### 19.6. Release notes

Nêu:
- Error code mới.
- Diagnostic được sửa.
- Severity thay đổi.
- Quick fix mới.
- Error behavior bị loại bỏ.
- Migration action.

## 20. Quy trình tạo và duy trì tài liệu lỗi

### 20.1. Từ diagnostic registry

Tạo trang lỗi từ registry có schema chuẩn để tránh thiếu code hoặc owner. Có thể sinh index và reference table tự động.

### 20.2. Documentation template

Mỗi trang nên dùng template thống nhất:
- Code và title.
- Severity.
- Affected versions.
- Message sample.
- Meaning.
- Causes.
- Resolution.
- Valid/invalid examples.
- Related diagnostics.
- Report issue instructions.

### 20.3. Đồng bộ với implementation

Khi thêm diagnostic trong code, pull request nên cập nhật:
- Registry.
- Message catalog.
- Tests.
- Documentation.
- Release note nếu cần.

### 20.4. Documentation tests

Có thể kiểm tra:
- Mỗi public code có trang.
- Mỗi trang tham chiếu code tồn tại.
- URL không bị hỏng.
- Code sample parse hoặc fail theo expected result.
- Version metadata đầy đủ.

### 20.5. Owner

Mỗi nhóm diagnostic cần owner hoặc team chịu trách nhiệm cập nhật khi semantics thay đổi.

### 20.6. Review

Review nội dung cần có developer hiểu diagnostic và technical writer hoặc người có khả năng diễn giải cho người dùng. Với lỗi domain, cần domain expert.

### 20.7. Feedback loop

Theo dõi search không có kết quả, support ticket lặp lại và diagnostic có tỷ lệ bị hiểu nhầm cao. Cập nhật tài liệu theo vấn đề thực tế.

## 21. Chỉ số đánh giá chất lượng tài liệu lỗi

### 21.1. Time to resolution

Thời gian từ lúc người dùng gặp lỗi đến lúc sửa được. Có thể đo qua support workflow hoặc user study.

### 21.2. Self-service resolution

Tỷ lệ vấn đề được giải quyết bằng tài liệu mà không cần support. Cần đo cẩn thận để không đánh đồng việc người dùng bỏ cuộc với tự giải quyết.

### 21.3. Search success

Tỷ lệ tìm được trang phù hợp theo error code hoặc message fragment.

### 21.4. Documentation coverage

Tỷ lệ public diagnostic có trang reference, example và resolution steps.

### 21.5. Diagnostic quality

Có thể khảo sát mức rõ ràng, độ chính xác vị trí và tính hữu ích của suggested fix.

### 21.6. Staleness

Theo dõi trang không được cập nhật sau nhiều release hoặc code sample không còn chạy.

### 21.7. Metrics cần được diễn giải

Số lượng lỗi giảm không nhất thiết chứng minh tài liệu tốt hơn; có thể do người dùng ít dùng tính năng. Kết hợp telemetry, feedback và review định tính.

## 22. Ví dụ end-to-end: tài liệu cho type mismatch

### 22.1. Diagnostic

~~~text
policy.dsl:8:17: error DSL-TYPE-001:
Expected Money but found Integer.
Expression: order.total + 100
~~~

### 22.2. Ý nghĩa

Biểu thức đang cộng một giá trị Money với Integer. DSL không tự suy ra đơn vị tiền tệ cho số nguyên.

### 22.3. Nguyên nhân

- Literal thiếu currency.
- Field có kiểu không như người viết nghĩ.
- Dữ liệu đầu vào được khai báo sai schema.
- Một conversion đã bị bỏ khỏi expression.

### 22.4. Cách sửa

Nếu số 100 là tiền VND, hãy tạo Money value rõ đơn vị:

~~~text
order.total + 100 VND
~~~

Nếu 100 là quantity hoặc một giá trị khác, không cộng trực tiếp với Money; hãy dùng phép toán phù hợp với domain model.

### 22.5. Ví dụ hợp lệ

~~~text
order.total + 100 VND
~~~

### 22.6. Ví dụ không hợp lệ

~~~text
order.total + 100
~~~

### 22.7. Test

- Expected type Money, actual Integer.
- Diagnostic code DSL-TYPE-001.
- Span trỏ vào literal 100 hoặc toàn biểu thức theo contract.
- Message không phụ thuộc locale.
- Link tài liệu mở đúng trang code.

## 23. Ví dụ end-to-end: lỗi runtime

### 23.1. Diagnostic

~~~text
policy.dsl:15:9: error DSL-RUN-003:
Evaluation exceeded the configured time limit.
Correlation ID: eval-701
~~~

### 23.2. Ý nghĩa

Evaluation chưa hoàn tất trong giới hạn thời gian đã cấu hình. Đây có thể là expression phức tạp, query tốn kém hoặc dependency phản hồi chậm.

### 23.3. Nguyên nhân có thể

- Rule có nhiều phép lặp hoặc recursion.
- Query không có filter đủ chọn lọc.
- Plugin gọi service ngoài chậm.
- Runtime quota thấp hơn workload cần thiết.

### 23.4. Cách điều tra

1. Tìm evaluation bằng correlation ID.
2. Xác định phase và function đang chạy.
3. Xem query plan hoặc execution trace nếu có quyền.
4. Kiểm tra input size và rule revision.
5. Đối chiếu timeout policy.
6. Tối ưu expression hoặc dependency.

### 23.5. Không nên làm

Không tăng timeout vô hạn hoặc tắt resource limit như cách xử lý mặc định. Nếu workload cần thời gian dài, hãy đánh giá quota và kiến trúc phù hợp.

## 24. Những lỗi thường gặp khi viết tài liệu lỗi

### 24.1. Chỉ lặp lại message

Trang chỉ viết lại "Invalid syntax" không giúp người dùng hiểu hoặc sửa. Cần nguyên nhân, ví dụ và resolution.

### 24.2. Không có error code

Nếu chỉ có message text, người dùng khó tìm kiếm và test dễ bị phụ thuộc wording.

### 24.3. Code thay đổi tùy tiện

Tái sử dụng hoặc đổi nghĩa code làm hỏng link, dashboard và automation.

### 24.4. Hướng dẫn quá chung

"Check your configuration" không đủ. Nêu tên key, format, expected value và cách xác minh.

### 24.5. Không có ví dụ

Ví dụ sai và đúng giúp người học nhận ra khác biệt nhanh hơn mô tả trừu tượng.

### 24.6. Đề xuất sửa sai

Quick fix không nên được đưa ra nếu có thể thay đổi semantics. Nêu giả định hoặc yêu cầu người dùng xác nhận.

### 24.7. Trộn lỗi người dùng và lỗi hệ thống

Syntax error khác internal failure. Phân loại rõ giúp người dùng biết có thể sửa source hay cần báo support.

### 24.8. Tiết lộ thông tin nhạy cảm

Không đưa stack trace, secret, query hoặc internal path vào tài liệu hay message công khai.

### 24.9. Tài liệu không theo version

Người dùng phiên bản cũ có thể áp dụng cách sửa không tồn tại trong toolchain của họ. Luôn nêu affected version.

### 24.10. Không kiểm thử ví dụ

Code sample có thể sai cú pháp hoặc không còn chạy. Tự động hóa example validation khi khả thi.

## 25. Quy trình xây dựng error documentation

Một quy trình thực tế có thể gồm:
1. **Thu thập diagnostic:** inventory code từ lexer, parser, semantic analyzer, runtime, API và packaging.
2. **Chuẩn hóa taxonomy:** nhóm theo subsystem, severity và giai đoạn.
3. **Thiết kế registry:** code, title, meaning, owner, version và documentation slug.
4. **Định nghĩa diagnostic schema:** message, span, related location, context và suggested fix.
5. **Viết trang theo template:** meaning, causes, resolution, examples và related links.
6. **Liên kết từ công cụ:** CLI, IDE, API và build report mở đúng trang.
7. **Kiểm tra security:** redact secret và tránh lộ implementation detail.
8. **Kiểm tra version:** nội dung phù hợp DSL/compiler/runtime version.
9. **Tự động kiểm tra:** link, code sample, registry coverage và schema.
10. **Review với người dùng:** technical writer, developer và domain expert.
11. **Theo dõi hiệu quả:** search success, support ticket và time to resolution.
12. **Cập nhật theo release:** thêm, sửa, deprecate hoặc retire code có kiểm soát.

## 26. Câu hỏi tự đánh giá

1. Error, exception và diagnostic khác nhau như thế nào?
2. Vì sao error code nên ổn định trong khi message có thể thay đổi?
3. Những giai đoạn nào trong DSL pipeline có thể phát diagnostic?
4. Một trang tài liệu lỗi cần có những phần nào?
5. Primary span và related span khác nhau ra sao?
6. Làm thế nào viết message ngắn nhưng hữu ích?
7. Vì sao không nên hiển thị stack trace cho người dùng DSL?
8. HTTP status và DSL error code có vai trò khác nhau thế nào?
9. Tài liệu lỗi cần xử lý localization và versioning ra sao?
10. Làm thế nào giữ registry, implementation, tests và docs đồng bộ?
11. Những chỉ số nào giúp đánh giá khả năng tự giải quyết vấn đề?
12. Vì sao code sample trong error reference cần được kiểm tra tự động?

## Kết luận

Tài liệu lỗi là một phần của contract và trải nghiệm người dùng DSL. Nó cần giải thích diagnostics theo giai đoạn xử lý, cung cấp error code ổn định, message rõ ràng, source location chính xác, nguyên nhân có thể xảy ra, hướng sửa và ví dụ trước/sau. Các lỗi lexer, parser, semantic, type, validation, runtime, authorization, API và deployment cần được phân loại nhất quán.

Một error registry, template tài liệu, version policy và quy trình cập nhật theo release giúp compiler, runtime, CLI, IDE và help center dùng chung cách diễn giải. Tài liệu cần tránh tiết lộ dữ liệu nhạy cảm, phân biệt lỗi người dùng với lỗi hệ thống và cung cấp reproduction guidance an toàn. Khi diagnostics được thiết kế có cấu trúc và tài liệu được kiểm tra cùng implementation, người dùng có thể tìm nguyên nhân nhanh hơn, tự sửa nhiều vấn đề hơn và học DSL qua chính những lỗi họ gặp.
