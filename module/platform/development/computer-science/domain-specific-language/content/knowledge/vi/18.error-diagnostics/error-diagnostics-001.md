# Lỗi từ vựng

## 1. Lỗi từ vựng trong DSL là gì?

Trong một ngôn ngữ chuyên biệt miền (*Domain-Specific Language — DSL*), lexer (*lexical analyzer*) đọc văn bản nguồn và chia chuỗi ký tự thành các token như keyword, identifier, literal, operator và dấu phân cách. **Lỗi từ vựng (*lexical error*)** xảy ra khi lexer không thể diễn giải một phần đầu vào theo bất kỳ quy tắc token hợp lệ nào của ngôn ngữ hoặc phát hiện một cấu trúc token bị viết sai.

Ví dụ, DSL quy định chuỗi phải được đóng bằng dấu nháy kép:

~~~text
message = "Hello
~~~

Lexer đã nhận dấu mở chuỗi nhưng đến cuối dòng hoặc cuối file vẫn không tìm thấy dấu đóng hợp lệ. Đây là lỗi từ vựng vì chuỗi không tạo thành một string token hoàn chỉnh theo lexical specification.

Một ví dụ khác:

~~~text
total = 10 @ 5
~~~

Nếu ký tự @ không được định nghĩa là token trong DSL, lexer không thể phân loại nó và phải phát lexical diagnostic.

Lỗi từ vựng khác với lỗi cú pháp và lỗi ngữ nghĩa:

| Giai đoạn | Câu hỏi | Ví dụ lỗi |
|---|---|---|
| Lexing | Các ký tự có tạo thành token hợp lệ không? | String chưa đóng, ký tự không hợp lệ |
| Parsing | Các token có tạo thành cấu trúc grammar hợp lệ không? | Thiếu dấu ngoặc, sai thứ tự từ khóa |
| Semantic analysis | Cấu trúc hợp lệ có ý nghĩa trong context không? | Identifier chưa khai báo, sai kiểu |
| Runtime | Thực thi có hoàn tất theo quy tắc không? | Chia cho 0, timeout, dịch vụ ngoài bị lỗi |

Ví dụ customer.age + có thể gồm những token hợp lệ nhưng thiếu toán hạng phía sau, nên đó thường là lỗi cú pháp. Ngược lại, customer.age @ 5 có thể chứa ký tự không có token tương ứng, nên lỗi xuất hiện ở lexer.

Việc phân loại đúng giúp công cụ đưa ra thông báo phù hợp và tránh yêu cầu người dùng sửa sai lớp.

## 2. Vì sao cần xử lý lỗi từ vựng rõ ràng?

Lỗi từ vựng thường là lỗi đầu tiên xuất hiện trong pipeline DSL. Nếu lexer không mô tả rõ lỗi và không có chiến lược phục hồi phù hợp, parser có thể nhận một token stream sai lệch, tạo ra nhiều lỗi dây chuyền hoặc dừng quá sớm.

Một cơ chế xử lý tốt cần:

- Xác định chính xác vị trí ký tự gây lỗi hoặc vùng token không hoàn chỉnh.
- Nêu nguyên nhân bằng thuật ngữ mà người viết DSL hiểu.
- Phân biệt lỗi thật với cảnh báo hoặc cú pháp chưa hoàn chỉnh khi đang gõ.
- Quy định lexer dừng hay tiếp tục sau lỗi.
- Cung cấp token lỗi hoặc thông tin phục hồi để parser có thể tiếp tục khi phù hợp.
- Giữ source location để editor đánh dấu đúng đoạn văn bản.
- Tránh làm lộ nội dung nhạy cảm trong diagnostics hoặc log.
- Bảo đảm lexer không treo hoặc tiêu thụ tài nguyên bất thường với input lỗi.

Trong môi trường CLI hoặc compiler, lexer có thể dừng khi gặp lỗi nghiêm trọng. Trong editor, việc tiếp tục phân tích phần còn lại thường hữu ích hơn vì người dùng cần thấy nhiều lỗi cùng lúc và vẫn sử dụng được code completion.

## 3. Các nhóm lỗi từ vựng thường gặp

### 3.1. Ký tự không hợp lệ

Lỗi này xảy ra khi một ký tự không bắt đầu được bất kỳ token nào tại vị trí hiện tại.

Ví dụ, nếu DSL không hỗ trợ ký hiệu @:

~~~text
discount = price @ rate
~~~

Lexer có thể phát:

~~~text
LEX-CHAR-001: Unexpected character '@'
~~~

Cần phân biệt ký tự không hợp lệ với ký tự hợp lệ nhưng nằm sai vị trí. Ví dụ dấu đóng ngoặc có thể là token hợp lệ, nhưng nếu không có dấu mở tương ứng thì parser mới là thành phần phát hiện lỗi cấu trúc.

### 3.2. String literal chưa đóng

Một string chưa đóng xảy ra khi lexer gặp dấu mở chuỗi nhưng không tìm thấy dấu đóng theo quy tắc.

~~~text
title = "Monthly report
~~~

Các trường hợp cần xem xét:

- Hết dòng trước khi đóng chuỗi, nếu DSL cấm newline trong string.
- Hết file trước khi đóng chuỗi.
- Dấu nháy đóng bị escape nên không kết thúc string.
- String nhiều dòng chưa kết thúc.
- Dấu phân cách mở và đóng không khớp.

Diagnostic nên chỉ vị trí bắt đầu string hoặc vị trí cuối cùng lexer còn có thể chờ ký tự đóng.

### 3.3. Escape sequence không hợp lệ

Nếu DSL hỗ trợ escape trong string, lexer hoặc bước giải mã literal cần kiểm tra các chuỗi escape được phép.

Ví dụ hợp lệ tùy DSL:

~~~text
"line one\nline two"
"quote: \""
"folder\\file"
~~~

Ví dụ sai nếu DSL chỉ cho phép các escape newline, tab, quote và backslash:

~~~text
message = "Hello\q"
~~~

Lexer cần xác định escape không hợp lệ có làm token lỗi hay phát string token kèm diagnostic. Không nên âm thầm bỏ dấu backslash hoặc tự diễn giải thành ký tự khác vì điều đó có thể thay đổi dữ liệu người dùng.

### 3.4. Comment chưa đóng

Với comment nhiều dòng:

~~~text
/*
  temporary rule
~~~

nếu không có dấu đóng trước EOF, lexer cần phát lỗi comment chưa kết thúc.

Một DSL cần xác định comment có được lồng nhau không. Nếu không hỗ trợ nesting, chuỗi mở comment xuất hiện bên trong comment không tạo thêm mức lồng. Nếu có hỗ trợ, lexer cần theo dõi độ sâu comment và giới hạn độ sâu để tránh input độc hại gây tiêu thụ tài nguyên quá mức.

### 3.5. Number literal sai định dạng

Một literal số có thể sai do:

- Có nhiều dấu thập phân.
- Thiếu chữ số ở một phía của dấu thập phân theo grammar.
- Exponent không có chữ số.
- Dấu phân cách chữ số đặt sai vị trí.
- Hậu tố đơn vị không được hỗ trợ.
- Ký tự chữ xuất hiện liền sau số mà không có quy tắc phân tách.

Ví dụ:

~~~text
1.2.3
4e+
12__000
~~~

Cần xác định ranh giới giữa lỗi từ vựng và lỗi chuyển đổi giá trị. Chuỗi số rất lớn có thể khớp grammar số nguyên nhưng vượt miền của kiểu số đích. Lexer có thể tạo NUMBER token hợp lệ, còn bước chuyển literal sang giá trị hoặc type checking phát lỗi overflow. Tài liệu nên nêu rõ giai đoạn chịu trách nhiệm.

### 3.6. Identifier không hợp lệ

Nếu identifier chỉ được bắt đầu bằng chữ cái hoặc dấu gạch dưới, tên sau có thể không hợp lệ:

~~~text
2customer = "An"
~~~

Tuy nhiên, lexer có thể phát NUMBER 2 rồi IDENTIFIER customer; việc hai token xuất hiện liền nhau không nhất thiết là lexical error. Parser có thể báo lỗi vì cấu trúc khai báo không mong đợi hai token đó.

Đặc tả cần phân biệt:
- Ký tự không được phép xuất hiện trong identifier.
- Identifier bắt đầu bằng ký tự không được phép.
- Một chuỗi bị tách thành nhiều token hợp lệ nhưng không phù hợp grammar.
- Tên hợp lệ về từ vựng nhưng trùng keyword hoặc không được phép trong context.

### 3.7. Ký tự Unicode hoặc encoding không hợp lệ

Nguồn DSL có thể chứa ký tự Unicode không hợp lệ do lỗi giải mã, ký tự điều khiển bị cấm hoặc ký tự không thuộc tập identifier được hỗ trợ.

Cần phân biệt lỗi decoding ở bước đọc file với lỗi lexical trên chuỗi ký tự đã giải mã. Nếu byte sequence không hợp lệ theo UTF-8, lexer chưa thể nhận được ký tự Unicode tương ứng.

Nếu DSL hỗ trợ Unicode identifiers, cần quy định tập ký tự bắt đầu và tiếp tục, normalization và cách xử lý ký tự đồng hình. Không nên tự động loại bỏ ký tự lạ vì điều đó có thể khiến chương trình được hiểu khác với văn bản người dùng nhập.

### 3.8. Token không hoàn chỉnh khi người dùng đang gõ

Trong editor, người dùng thường tạm thời để lại văn bản chưa hoàn chỉnh:

~~~text
message = "
count = 1e
~~~

Đây có thể là trạng thái đang nhập thay vì lỗi cần hiển thị nổi bật. Lexer phục vụ editor có thể phát trạng thái incomplete token hoặc diagnostic có severity thấp, rồi cập nhật khi người dùng nhập tiếp.

Cần phân biệt chế độ phân tích file hoàn chỉnh với chế độ phân tích văn bản đang chỉnh sửa.

## 4. Xác định ranh giới lỗi: lexer, parser hay semantic analyzer?

Một lỗi có thể trông giống lỗi từ vựng nhưng thuộc giai đoạn khác. Hãy xét các ví dụ:

| Đầu vào | Phân loại thường gặp | Lý do |
|---|---|---|
| value = 10 @ 2 | Lexical | @ không có token hợp lệ |
| value = "open | Lexical | String không được đóng |
| value = 10 + | Syntax | Các token hợp lệ nhưng thiếu toán hạng |
| ) | Syntax | Dấu đóng là token hợp lệ nhưng không có cấu trúc tương ứng |
| unknown = 1 | Semantic, tùy quy tắc khai báo | Tên có thể hợp lệ nhưng chưa được khai báo |
| age + "old" | Type/semantic | Token và grammar có thể hợp lệ nhưng kiểu không tương thích |
| Số nguyên vượt miền kiểu | Literal conversion hoặc semantic | Pattern số hợp lệ nhưng giá trị có thể vượt miền kiểu |

Không phải mọi DSL đều phân chia các giai đoạn giống nhau. Điều quan trọng là đặc tả và implementation thống nhất về nơi phát hiện, loại diagnostic và khả năng phục hồi.

### 4.1. Nguyên tắc phân loại

- Nếu không thể tạo token theo lexical specification, lexer phát lỗi từ vựng.
- Nếu các token hợp lệ nhưng không khớp grammar, parser phát lỗi cú pháp.
- Nếu cấu trúc hợp lệ nhưng tham chiếu, kiểu hoặc ràng buộc không hợp lệ, semantic/model validator phát lỗi tương ứng.
- Nếu hành vi chỉ thất bại khi thực thi, runtime phát runtime error.

### 4.2. Tránh báo lỗi dây chuyền

Một lỗi từ vựng có thể làm parser nhìn thấy chuỗi token thiếu hoặc sai. Ví dụ string chưa đóng có thể khiến mọi ký tự phía sau bị xem là nội dung string. Lexer nên phát lỗi chính tại vị trí bắt đầu string hoặc nơi phát hiện thiếu dấu đóng; parser không nên tạo hàng chục lỗi phụ gây nhiễu.

Một diagnostic có thể đánh dấu là lỗi gốc (*primary error*), còn những lỗi phát sinh do phục hồi có thể được giảm severity hoặc ẩn nếu chúng không giúp người dùng sửa lỗi.

## 5. Quy trình phát hiện lỗi từ vựng

Lexer có thể kiểm tra lỗi ngay trong lúc quét token. Một quy trình khái quát:

1. Xác định trạng thái lexical hiện tại.
2. Kiểm tra ký tự đầu vào có thể bắt đầu token nào.
3. Thử nhận diện token theo quy tắc longest match và ưu tiên.
4. Nếu nhận diện được, tiêu thụ ký tự và tạo token.
5. Nếu nhận diện không được, xác định lỗi cụ thể thay vì chỉ trả một lỗi chung.
6. Ghi source span và diagnostic.
7. Áp dụng chiến lược phục hồi đã định nghĩa.
8. Tiếp tục đến EOF hoặc dừng theo chính sách.

Pseudocode:

~~~text
function scanNextToken():
    start = cursor
    startLocation = currentLocation()

    if isAtEnd():
        return makeEOF()

    if startsValidToken():
        return scanValidToken()

    badChar = currentChar()
    advance()

    reportLexicalError(
        code = "LEX-CHAR-001",
        span = [start, cursor],
        message = "Unexpected character"
    )

    return ERROR_TOKEN(badChar, startLocation)
~~~

Đây là pseudocode minh họa. Lexer thực tế cần tránh lặp vô hạn: khi không nhận diện được token, nó phải tiêu thụ ít nhất một đơn vị đầu vào hoặc kết thúc. Nếu không, cùng ký tự lỗi có thể bị xử lý lặp lại mãi.

## 6. Vị trí nguồn và source span

Thông báo lỗi chỉ hữu ích khi chỉ đúng đoạn văn bản.

### 6.1. Start và end offset

Mỗi token và diagnostic nên có offset bắt đầu và kết thúc. Quy ước có thể dùng khoảng nửa mở [start, end): start được tính, end không được tính. Cách này giúp độ dài vùng là end trừ start và thuận tiện cho thao tác chọn văn bản.

Ví dụ:

~~~text
total = 10 @ 2
           ^
           lỗi tại ký tự @
~~~

Nếu offset của @ là 11, vùng lỗi có thể là [11, 12).

### 6.2. Dòng và cột

Editor thường hiển thị vị trí theo dòng và cột. Lexer cần xử lý đúng:
- LF.
- CRLF.
- CR nếu được hỗ trợ.
- Tab.
- Ký tự Unicode ngoài BMP.
- Ký tự kết hợp dấu.

Cột có thể được tính theo byte, UTF-16 code unit, Unicode code point hoặc tab-expanded display column. Các hệ thống tích hợp editor phải thống nhất đơn vị hoặc chuyển đổi chính xác.

### 6.3. Vị trí lỗi khi token chưa hoàn chỉnh

Với string chưa đóng, có thể đánh dấu từ dấu mở đến EOF hoặc đến cuối dòng theo quy tắc DSL. Với escape sai, nên đánh dấu chính escape sequence. Với ký tự không hợp lệ đơn lẻ, đánh dấu đúng ký tự đó.

Không nên chỉ báo dòng 1 cột 1 cho mọi lỗi. Source span chính xác giúp người dùng sửa nhanh và hỗ trợ code action.

## 7. Thiết kế diagnostic cho lỗi từ vựng

Một diagnostic nên có cấu trúc ổn định thay vì chỉ là chuỗi thông báo.

Ví dụ mô hình:

~~~text
Diagnostic {
    code: "LEX-STRING-001",
    severity: ERROR,
    message: "Unterminated string literal",
    source: "rules.dsl",
    startOffset: 42,
    endOffset: 58,
    line: 4,
    column: 12,
    relatedInformation: [],
    suggestedFixes: []
}
~~~

Các trường quan trọng:

| Trường | Mục đích |
|---|---|
| Code | Mã lỗi ổn định để tài liệu, test và công cụ tham chiếu |
| Severity | Error, warning, info hoặc hint |
| Message | Giải thích ngắn gọn nguyên nhân |
| Source | File hoặc tài liệu phát sinh lỗi |
| Range | Vị trí bắt đầu và kết thúc |
| Related information | Vị trí liên quan, ví dụ dấu mở string |
| Suggested fix | Gợi ý sửa an toàn nếu có |
| Phase | Lexing, parsing hoặc giai đoạn khác |
| Recovery data | Thông tin nội bộ cho parser/editor nếu cần |

### 7.1. Mã lỗi ổn định

Một dự án có thể dùng bảng mã:

| Mã | Ý nghĩa |
|---|---|
| LEX-CHAR-001 | Ký tự không hợp lệ |
| LEX-STRING-001 | String chưa đóng |
| LEX-ESCAPE-001 | Escape sequence không hợp lệ |
| LEX-COMMENT-001 | Comment nhiều dòng chưa đóng |
| LEX-NUMBER-001 | Number literal sai định dạng |
| LEX-IDENT-001 | Identifier không hợp lệ |
| LEX-UNICODE-001 | Ký tự Unicode không được phép |
| LEX-LIMIT-001 | Token vượt giới hạn được hỗ trợ |

Mã là ví dụ minh họa; dự án cần quản lý danh mục mã để không tái sử dụng cùng mã cho các ý nghĩa khác nhau.

### 7.2. Message hữu ích

Thông báo tốt nên nêu:
- Điều gì sai.
- Sai ở đâu.
- Vì sao bị từ chối.
- Cách sửa có khả năng đúng.

Ví dụ:

~~~text
rules.dsl:4:12: error LEX-ESCAPE-001
Unsupported escape sequence "\q".
Use one of the supported escapes: \n, \t, \", or \\.
~~~

Thông báo chỉ nên liệt kê các escape thực sự được DSL hỗ trợ. Không nên đưa gợi ý phỏng đoán nếu chưa đủ thông tin.

### 7.3. Ngôn ngữ và tính ổn định của message

Mã lỗi có thể ổn định xuyên phiên bản, còn message có thể được bản địa hóa hoặc điều chỉnh. Test tự động nên ưu tiên kiểm tra mã, severity và range; tránh phụ thuộc toàn bộ vào câu chữ nếu thông điệp có thể được dịch.

## 8. Chiến lược phục hồi sau lỗi

Phục hồi (*error recovery*) quyết định lexer làm gì sau khi phát hiện lỗi. Mục tiêu là giúp các bước sau tiếp tục phân tích đủ để đưa ra thông tin hữu ích mà không giả vờ rằng input đã hợp lệ.

### 8.1. Dừng ngay

Lexer dừng tại lỗi đầu tiên và trả về diagnostics. Cách này đơn giản, phù hợp với compiler hoặc pipeline không cần tiếp tục khi source đã sai.

Ưu điểm:
- Dễ kiểm soát.
- Không tạo token giả.
- Tránh lỗi phụ từ token stream sai lệch.

Hạn chế:
- Người dùng phải sửa từng lỗi theo nhiều lượt.
- Editor khó cung cấp nhiều diagnostics cùng lúc.

### 8.2. Bỏ qua ký tự lỗi

Lexer phát diagnostic rồi tiêu thụ ký tự gây lỗi để tiếp tục.

Ví dụ:

~~~text
total = 10 @ 2
next = 5
~~~

Lexer có thể bỏ qua @ rồi tiếp tục quét 2 và dòng tiếp theo. Cách này giúp phát hiện lỗi khác phía sau, nhưng token stream đã phục hồi có thể không phản ánh chính xác ý định ban đầu.

### 8.3. Phát ERROR token

Lexer có thể tạo token đặc biệt ERROR chứa lexeme và source span:

~~~text
IDENTIFIER("total")
EQUAL("=")
NUMBER("10")
ERROR("@")
NUMBER("2")
~~~

Parser có thể nhận biết token lỗi và tiếp tục theo chiến lược của nó. Cách này giữ vị trí lỗi trong token stream và tránh làm parser nhầm ký tự đó là một token hợp lệ.

### 8.4. Đồng bộ tại ranh giới

Với một số lỗi, lexer có thể bỏ qua input đến một ranh giới phù hợp:
- Cuối dòng.
- Dấu chấm phẩy.
- Dấu đóng block.
- Ký hiệu kết thúc string hoặc comment.
- Token bắt đầu construct mới.

Không có một ranh giới chung cho mọi lỗi. Ví dụ, với string chưa đóng, nếu DSL cấm newline trong string, có thể đồng bộ tại newline. Nếu string nhiều dòng được phép, newline không phải điểm đồng bộ an toàn.

### 8.5. Phục hồi theo lexical mode

Khi lỗi xảy ra bên trong string hoặc comment, lexer cần biết cách thoát mode:
- String chưa đóng: có thể kết thúc tại newline hoặc EOF.
- Comment chưa đóng: có thể giữ mode đến EOF rồi phát một diagnostic.
- Interpolation lỗi: có thể tìm dấu đóng interpolation nếu quy tắc cho phép.
- Escape lỗi: tiêu thụ escape sai như một đơn vị và tiếp tục bên trong string.

Phục hồi phải nhất quán với grammar và không làm mất quá nhiều phần source hợp lệ.

## 9. Lỗi từ vựng trong editor và trong compiler

### 9.1. Chế độ compiler hoặc CLI

Trong compiler, đầu vào thường được xem là tài liệu hoàn chỉnh. Lexer có thể:
- Phát diagnostics.
- Tiếp tục để thu thập nhiều lỗi nếu recovery an toàn.
- Trả trạng thái thất bại để ngăn compile hoặc execution.
- Không cho chạy chương trình nếu lexical errors chưa được giải quyết.

### 9.2. Chế độ editor

Editor thường phân tích source đang nhập dở. Các trạng thái sau có thể là tạm thời:
- Dấu mở string chưa có dấu đóng.
- Identifier đang được gõ.
- Số mới có phần exponent chưa hoàn chỉnh.
- Comment đang mở.
- Dấu ngoặc chưa cân bằng.

Lexer/editor integration có thể đánh dấu diagnostic là provisional hoặc giảm severity cho đến khi người dùng hoàn tất token. Tuy nhiên, khi lưu hoặc compile, quy tắc của tài liệu hoàn chỉnh vẫn phải được áp dụng.

### 9.3. Incremental lexing

Khi người dùng sửa một vùng, lexer incremental chỉ cần quét lại phần bị ảnh hưởng và tiếp tục cho đến khi trạng thái lexical ổn định. Một thay đổi nhỏ có thể ảnh hưởng nhiều ký tự sau đó: thêm dấu mở string ở đầu dòng có thể khiến phần còn lại của file được xem là string.

Vì vậy, cache token cần gắn với trạng thái đầu vào và trạng thái đầu ra tại các điểm kiểm tra. Nếu trạng thái thay đổi, phải vô hiệu hóa vùng token phụ thuộc, không chỉ thay token nằm đúng vị trí con trỏ.

## 10. Unicode và các lỗi hiển thị khó nhận biết

### 10.1. Ký tự đồng hình

Hai ký tự từ bảng chữ cái khác nhau có thể trông giống nhau. Ví dụ chữ Latin a và ký tự tương tự trong bảng chữ cái khác có thể được nhìn gần như giống nhau nhưng có code point khác.

Nếu DSL cho phép Unicode identifier, lexer và công cụ nên cân nhắc cảnh báo ký tự đồng hình trong tên quan trọng. Không nên tự động gộp mọi ký tự giống hình dạng vì có thể làm thay đổi tên hợp lệ của người dùng.

### 10.2. Normalization

Một chữ có dấu có thể được biểu diễn bằng một code point dựng sẵn hoặc một chuỗi gồm chữ cái và dấu kết hợp. Nếu DSL so sánh tên theo chuỗi thô, hai cách viết có thể khác nhau dù hiển thị tương tự.

Chính sách normalization như NFC cần được áp dụng nhất quán ở khai báo và tham chiếu. Lexer nên giữ lexeme gốc để hiển thị và source mapping; bước chuẩn hóa để so sánh cần tuân theo đặc tả ngôn ngữ.

### 10.3. Ký tự điều khiển và ký tự vô hình

Một số ký tự không hiển thị hoặc điều khiển hướng văn bản có thể làm source khó review. DSL có thể từ chối chúng trong identifier hoặc phát warning. Diagnostic cần hiển thị cách nhận diện an toàn, chẳng hạn tên Unicode và code point, thay vì chỉ in một ký tự vô hình.

### 10.4. Byte sequence không hợp lệ

Lỗi UTF-8 hoặc encoding khác thường được phát hiện ở bước đọc/giải mã source, trước lexer. Hệ thống nên phân biệt:
- File không giải mã được.
- Source đã giải mã nhưng chứa code point bị DSL cấm.
- Code point hợp lệ nhưng không được phép trong loại token đang quét.

Sự phân biệt này giúp thông báo lỗi phản ánh đúng nguyên nhân.

## 11. Bảo mật và độ bền trước input lỗi

Lexer thường xử lý input do người dùng cung cấp. Vì vậy, lexical error handling cũng là một phần của độ an toàn hệ thống.

Các điểm cần chú ý:

- Giới hạn độ dài token, string, comment và identifier.
- Giới hạn độ sâu của mode stack hoặc interpolation.
- Tránh regex có backtracking bùng nổ.
- Bảo đảm mọi nhánh lỗi đều tiêu thụ input hoặc kết thúc.
- Không tạo vòng lặp vô hạn khi token pattern không khớp.
- Không ghi toàn bộ source có thể chứa mật khẩu hoặc dữ liệu cá nhân vào log.
- Giới hạn số diagnostics để input lỗi không tạo hàng triệu thông báo.
- Tránh xây dựng message bằng cách nối trực tiếp dữ liệu không tin cậy mà không escape.
- Xử lý đúng ký tự điều khiển và Unicode khó hiển thị.
- Không tiếp tục thực thi chương trình khi lexical errors làm thay đổi cách diễn giải source.

### 11.1. Regex denial of service

Một regex token pattern được viết thiếu cẩn thận có thể backtrack nhiều lần trên input đặc biệt. Khi lexer nhận source từ người dùng, một chuỗi được thiết kế để làm regex chạy rất lâu có thể gây từ chối dịch vụ.

Có thể giảm rủi ro bằng cách dùng automaton tuyến tính, tránh nested quantifiers nguy hiểm, giới hạn độ dài input và đo hiệu năng với trường hợp xấu.

### 11.2. Diagnostic flooding

Một ký tự lỗi có thể khiến lexer phát một diagnostic cho từng ký tự tiếp theo. Nên có giới hạn số lỗi, nhóm các lỗi liên tiếp hoặc dừng khi không còn khả năng phục hồi đáng tin cậy.

Giới hạn diagnostics không được âm thầm biến source thành hợp lệ. Kết quả vẫn phải mang trạng thái thất bại và chỉ rõ rằng số lỗi hiển thị đã bị giới hạn.

## 12. Ví dụ xử lý lỗi trong lexer viết tay

Một lexer viết tay có thể dùng token lỗi và diagnostic:

~~~java
Token scanUnexpectedCharacter() {
    int start = cursor;
    SourceLocation location = currentLocation();
    char bad = advance();

    diagnostics.add(Diagnostic.error(
        "LEX-CHAR-001",
        "Unexpected character: " + printable(bad),
        sourceSpan(start, cursor),
        location
    ));

    return new Token(
        TokenType.ERROR,
        String.valueOf(bad),
        null,
        sourceSpan(start, cursor)
    );
}
~~~

Hàm printable nên biểu diễn an toàn các ký tự không in được. Nếu ký tự có thể chứa dữ liệu nhạy cảm hoặc điều khiển terminal, không nên in nguyên văn mà cần escape.

Với string chưa đóng:

~~~java
Token scanString() {
    int start = cursor;
    advance(); // consume opening quote

    while (!isAtEnd() && peek() != '"') {
        if (peek() == '\\') {
            scanEscapeOrReportError();
        } else if (isNewline(peek())) {
            reportUnterminatedString(start, cursor);
            return errorToken(start, cursor);
        } else {
            advance();
        }
    }

    if (isAtEnd()) {
        reportUnterminatedString(start, cursor);
        return errorToken(start, cursor);
    }

    advance(); // consume closing quote
    return stringToken(start, cursor);
}
~~~

Đây là mã minh họa. Một triển khai thực tế cần xác định newline có được phép trong string hay không, xử lý CRLF, Unicode, escape, source span và chính sách phục hồi. Nếu string nhiều dòng được phép, điều kiện newline trong vòng lặp phải thay đổi.

## 13. Kiểm thử lỗi từ vựng

Lexer cần có test riêng cho từng loại lỗi, cả vị trí và hành vi sau lỗi.

### 13.1. Kiểm thử ký tự không hợp lệ

Input:

~~~text
value = 10 @ 2
next = 3
~~~

Kết quả mong đợi:
- Một diagnostic LEX-CHAR-001 tại ký tự @.
- Token lỗi hoặc hành vi bỏ qua theo recovery policy.
- Lexer tiếp tục đến dòng tiếp theo nếu chế độ recovery được bật.
- Không phát lại cùng lỗi vô hạn.

### 13.2. Kiểm thử string chưa đóng

Input:

~~~text
message = "unfinished
next = 10
~~~

Kết quả mong đợi phụ thuộc quy tắc string:
- Nếu string không được qua dòng, lỗi tại dấu mở hoặc cuối dòng.
- Nếu string nhiều dòng được phép, lỗi chỉ phát khi đến EOF mà chưa có dấu đóng.
- Lexer phải khôi phục mode đúng theo chính sách.

### 13.3. Kiểm thử escape

Input:

~~~text
message = "bad\qescape"
~~~

Kết quả mong đợi:
- Diagnostic LEX-ESCAPE-001.
- Range trỏ vào escape \q.
- Các ký tự còn lại được xử lý theo quy tắc recovery đã công bố.

### 13.4. Kiểm thử number literal

Các trường hợp nên có:

| Input | Kết quả kỳ vọng |
|---|---|
| 42 | Số nguyên hợp lệ |
| 12.5 | Số thập phân hợp lệ nếu grammar hỗ trợ |
| 1.2.3 | Lỗi định dạng hoặc token sequence dẫn đến syntax error theo lexical rule |
| 4e+ | Exponent sai định dạng nếu exponent được hỗ trợ |
| 1_000 | Hợp lệ nếu dấu phân cách số được cho phép |
| 1__000 | Lỗi nếu không cho phép dấu phân cách liền nhau |
| Số vượt miền kiểu | Literal conversion/type diagnostic nếu lexical pattern vẫn hợp lệ |

Test cần phân biệt tokenization với việc chuyển lexeme thành giá trị có thể biểu diễn.

### 13.5. Kiểm thử comment chưa đóng

Input:

~~~text
/* comment begins
still in comment
~~~

Kết quả mong đợi:
- Diagnostic LEX-COMMENT-001 tại comment mở hoặc EOF.
- Không phát token nội dung comment như code.
- Lexer kết thúc hoặc phục hồi theo chính sách.

### 13.6. Kiểm thử vị trí nguồn

Dùng source có:
- Nhiều dòng.
- CRLF và LF.
- Tab.
- Ký tự tiếng Việt.
- Ký tự ngoài BMP.
- Dấu kết hợp Unicode.

Xác nhận offset, line, column và range tương thích với editor. Không chỉ kiểm tra message; vị trí sai có thể khiến người dùng sửa nhầm ký tự.

### 13.7. Fuzz testing và property-based testing

Sinh input ngẫu nhiên gồm ký tự hợp lệ, ký tự lạ, dấu nháy, backslash, comment marker và Unicode. Các thuộc tính hữu ích:

- Lexer không crash.
- Lexer không lặp vô hạn.
- Cursor luôn tiến hoặc lexer kết thúc.
- Mọi token có source span hợp lệ.
- Số diagnostics không vượt giới hạn cấu hình.
- EOF được phát đúng một lần nếu API quy định như vậy.
- Chạy cùng input và cấu hình cho kết quả token/diagnostic xác định.

## 14. Ví dụ bảng mã lỗi từ vựng

Một dự án có thể duy trì bảng tham chiếu:

| Code | Tên lỗi | Nguyên nhân | Gợi ý |
|---|---|---|---|
| LEX-CHAR-001 | Unexpected character | Ký tự không có token tương ứng | Xóa hoặc thay bằng ký hiệu được hỗ trợ |
| LEX-STRING-001 | Unterminated string | Thiếu dấu đóng chuỗi | Thêm dấu nháy đóng |
| LEX-ESCAPE-001 | Invalid escape | Escape không thuộc tập cho phép | Dùng escape hợp lệ |
| LEX-COMMENT-001 | Unterminated comment | Thiếu ký hiệu kết thúc comment | Đóng comment |
| LEX-NUMBER-001 | Malformed number | Literal không khớp grammar số | Sửa dấu thập phân hoặc exponent |
| LEX-IDENT-001 | Invalid identifier character | Ký tự không được phép trong identifier | Đổi tên hoặc dùng quoted identifier |
| LEX-UNICODE-001 | Unsupported Unicode character | Code point bị cấm | Dùng ký tự được hỗ trợ |
| LEX-LIMIT-001 | Token too long | Vượt giới hạn token | Rút ngắn token |

Mã và tên lỗi phải được quản lý tập trung để tài liệu, implementation, editor và test dùng cùng một định danh.

## 15. Quy trình xử lý lỗi từ vựng

Một quy trình có thể triển khai theo các bước:

1. **Định nghĩa lexical specification:** ghi rõ token hợp lệ, ký tự được phép, escape và lexical modes.
2. **Lập danh mục lỗi:** phân loại ký tự lạ, literal sai, token chưa đóng, Unicode và giới hạn.
3. **Xác định source coordinate:** chọn đơn vị offset và quy tắc line/column.
4. **Thiết kế diagnostic:** mã lỗi, severity, message, range và related information.
5. **Chọn recovery policy:** dừng, bỏ qua, ERROR token hoặc đồng bộ theo ranh giới.
6. **Tách lỗi decoding khỏi lỗi lexing:** báo đúng giai đoạn phát hiện.
7. **Tích hợp parser/editor:** xác định cách token lỗi được truyền và cách diagnostics được cập nhật.
8. **Giới hạn tài nguyên:** độ dài token, nesting, regex và số diagnostics.
9. **Viết test:** từng nhóm lỗi, vị trí, recovery, input lớn và fuzz cases.
10. **Giữ hành vi ổn định:** quản lý mã lỗi và thông báo khi grammar hoặc lexical rules thay đổi.

Khi thay đổi lexical specification, cần xem xét tài liệu DSL đã lưu. Một ký tự trước đây bị từ chối nhưng nay trở thành token hợp lệ có thể làm thay đổi cách parser hiểu source cũ.

## 16. Kết luận

Lỗi từ vựng xảy ra khi lexer không thể tạo token hợp lệ từ một phần văn bản nguồn, chẳng hạn ký tự lạ, string hoặc comment chưa đóng, escape sai, number literal không đúng định dạng hay ký tự Unicode bị cấm. Cần phân biệt các lỗi này với lỗi cú pháp, ngữ nghĩa và runtime để chẩn đoán đúng nguyên nhân.

Một lexer đáng tin cậy cung cấp diagnostics có mã và source range rõ ràng, xử lý lỗi theo recovery policy nhất quán, bảo vệ parser khỏi token stream gây hiểu nhầm và giới hạn tài nguyên với input bất thường. Khi các trường hợp lỗi được tài liệu hóa và kiểm thử độc lập, người viết DSL có thể sửa lỗi nhanh hơn, còn editor, compiler và runtime có hành vi dự đoán được.

