# Theo dõi dòng và cột

Trong quá trình phân tích từ vựng (lexical analysis), lexer đọc văn bản nguồn và chuyển các chuỗi ký tự thành token như từ khóa, tên định danh, số, chuỗi và toán tử. Ngoài loại token và giá trị của nó, lexer cần ghi nhận token xuất hiện ở đâu trong tài liệu. **Theo dõi dòng và cột (line and column tracking)** là cơ chế cập nhật vị trí nguồn khi đọc từng ký tự, để parser, bộ kiểm tra ngữ nghĩa, IDE và thông báo lỗi có thể trỏ chính xác đến phần mã liên quan.

Vị trí nguồn tưởng như chỉ là thông tin phụ, nhưng nó ảnh hưởng trực tiếp đến trải nghiệm sử dụng DSL. Khi người viết gặp lỗi như thiếu dấu ngoặc, dùng tên chưa khai báo hoặc truyền sai kiểu, thông báo “lỗi cú pháp” không đủ hữu ích. Công cụ cần chỉ ra tệp, dòng, cột và vùng văn bản gây lỗi. Để làm được điều đó nhất quán, mọi giai đoạn cần dùng chung quy ước về vị trí, độ dài token, cách xử lý xuống dòng, Unicode và tab.

## 1. Vị trí nguồn trong quá trình phân tích từ vựng

Một tài liệu DSL là chuỗi ký tự. Lexer thường duy trì một con trỏ (cursor) cho biết vị trí ký tự tiếp theo sẽ được đọc. Khi con trỏ tiến lên, lexer cập nhật các thông tin vị trí:

- **Offset:** vị trí trong chuỗi nguồn, thường tính bằng đơn vị mã hoặc byte theo quy ước đã chọn.
- **Line:** số dòng hiện tại.
- **Column:** vị trí cột hiện tại trong dòng.
- **Source ID:** định danh tệp hoặc tài liệu chứa đoạn mã, nếu dự án có nhiều nguồn.

Ví dụ:

```text
service "catalog" {
    replicas = 3
    port = 8080
}
```

Token `replicas` bắt đầu ở dòng 2, cột 5 nếu dòng và cột được đánh số từ 1. Token `3` nằm ở dòng 2, cột 16. Nếu người viết gõ `replicas =` rồi thiếu giá trị, lexer hoặc parser có thể báo lỗi tại vị trí dòng 2, cột 15 hoặc tại vị trí EOF, tùy điểm mà parser phát hiện thiếu token.

Vị trí thường được ghi nhận ngay khi bắt đầu quét token. Sau khi lexer nhận diện xong token, nó lưu cả vị trí bắt đầu và kết thúc. Các giai đoạn sau có thể dùng span này mà không phải tính lại từ đầu tệp.

## 2. Offset, dòng, cột và source span

### 2.1. Offset

Offset là chỉ số đánh dấu vị trí trong nguồn. Có nhiều quy ước:

- **Byte offset:** vị trí tính theo byte trong tệp đã mã hóa, ví dụ UTF-8.
- **Code-unit offset:** vị trí tính theo đơn vị mã của chuỗi, ví dụ UTF-16 code unit trong Java `String`.
- **Code-point offset:** vị trí tính theo Unicode code point.

Ba cách này không luôn có cùng giá trị. Với ký tự ASCII, mỗi ký tự chiếm một byte UTF-8, một UTF-16 code unit và một code point. Với ký tự ngoài BMP, một code point có thể chiếm hai UTF-16 code unit và bốn byte UTF-8.

Java `String` sử dụng UTF-16. Vì vậy, `String.length()` và chỉ số dùng cho `substring()` đếm UTF-16 code unit, không phải số ký tự người dùng nhìn thấy. Nếu lexer lưu offset để cắt chuỗi bằng `substring`, offset UTF-16 rất thuận tiện vì tương thích trực tiếp với API Java.

### 2.2. Dòng và cột

Dòng (line) xác định dòng văn bản. Cột (column) xác định vị trí bên trong dòng. Thông thường, cả hai được đánh số từ 1 để khớp với cách biên tập viên hiển thị: dòng đầu tiên là 1 và ký tự đầu tiên trên dòng là cột 1.

Tuy nhiên, “cột” cần được định nghĩa rõ. Nó có thể là:

- Số code unit từ đầu dòng.
- Số Unicode code point từ đầu dòng.
- Cột hiển thị sau khi mở rộng tab.
- Cột hiển thị theo độ rộng grapheme hoặc terminal.

Một DSL nên chọn quy ước ổn định và công bố cho công cụ. Cột code point dễ tính và không chia đôi một ký tự Unicode ngoài BMP; cột hiển thị phù hợp hơn khi vẽ dấu gạch dưới trong giao diện, nhưng phải tính đến tab, ký tự kết hợp và độ rộng ký tự theo font.

### 2.3. Source span

Source span là khoảng nguồn mà token hoặc nút cú pháp chiếm giữ. Một quy ước phổ biến là khoảng nửa mở (half-open): bao gồm offset bắt đầu và không bao gồm offset kết thúc.

\[
span = [startOffset, endOffset)
\]

Ví dụ, token `port` trong đoạn `port = 8080` có thể có span bắt đầu tại offset 4 và kết thúc tại offset 8 nếu chuỗi con được tính theo UTF-16 và phần đầu dòng là `port`. Độ dài token được tính bằng `endOffset - startOffset`.

Khoảng nửa mở có một số lợi ích:

- Token rỗng có thể biểu diễn bằng `startOffset == endOffset`.
- Hai token liền nhau có thể có span nối tiếp mà không chồng lấn.
- Có thể lấy văn bản bằng `source.substring(startOffset, endOffset)`.
- Điểm kết thúc chính là vị trí ngay sau token, thuận tiện cho parser và editor.

Một cấu trúc vị trí và span có thể được biểu diễn trong Java:

```java
record SourcePosition(int offset, int line, int column) {}

record SourceSpan(SourcePosition start, SourcePosition end) {}
```

Trong dự án nhiều tệp, span nên đi kèm `SourceId` hoặc tham chiếu đến tài liệu, vì offset 25 trong hai tệp khác nhau không chỉ cùng một vị trí.

## 3. Quy ước đánh số dòng và cột

Cần chọn một quy ước nhất quán trước khi triển khai lexer. Một lựa chọn phổ biến cho DSL là:

- Dòng bắt đầu từ 1.
- Cột bắt đầu từ 1.
- Offset dùng UTF-16 code unit nếu nguồn được lưu trong Java `String`.
- Cột đếm Unicode code point hoặc cột hiển thị theo tab stop đã công bố.
- Span dùng khoảng nửa mở `[start, end)`.
- Vị trí EOF là điểm ngay sau ký tự cuối cùng của tài liệu.

Không có một quy ước cột duy nhất phù hợp với mọi editor hoặc giao thức. Nếu DSL tích hợp với Language Server Protocol (LSP), cần chuyển đổi theo position encoding mà client và server đã thống nhất. Một số giao thức hoặc API cũ dùng UTF-16 code unit; hệ thống khác có thể dùng UTF-8 byte hoặc Unicode code point.

Điều quan trọng là không trộn lẫn các quy ước. Nếu lexer tính cột theo code point nhưng IDE hiểu cột là UTF-16 code unit, vị trí lỗi sẽ bị lệch sau khi gặp ký tự ngoài BMP.

## 4. Xử lý các kiểu xuống dòng

Tệp văn bản có thể dùng nhiều quy ước xuống dòng:

| Dạng | Ký hiệu | Cách biểu diễn thường gặp |
|---|---|---|
| Line Feed | LF | `\n` |
| Carriage Return | CR | `\r` |
| Carriage Return + Line Feed | CRLF | `\r\n` |

LF thường gặp trên Linux và macOS hiện đại; CRLF phổ biến trong tệp Windows; CR xuất hiện trong một số định dạng cũ. Một lexer chỉ tăng dòng khi gặp `\n` có thể xử lý sai tệp dùng CR đơn.

### 4.1. Coi CRLF là một lần xuống dòng

Trong CRLF, hai code unit `\r` và `\n` tạo thành một dấu xuống dòng logic. Nếu lexer tăng dòng hai lần, tất cả vị trí sau đó sẽ lệch một dòng. Cách xử lý thông dụng là:

- Khi gặp `\r`, tăng dòng một lần, đặt cột về 1 và nếu ký tự tiếp theo là `\n` thì tiêu thụ nó cùng lần xuống dòng đó.
- Khi gặp `\n` độc lập, tăng dòng một lần và đặt cột về 1.
- Khi gặp `\r` độc lập, cũng tăng dòng một lần và đặt cột về 1.

Ví dụ nguồn có CRLF:

```text
first\r\nsecond
```

Ký tự `s` của `second` bắt đầu ở dòng 2, cột 1, không phải dòng 3.

### 4.2. Chuẩn hóa hay giữ nguyên xuống dòng?

Lexer có thể chuẩn hóa CRLF và CR thành một dấu xuống dòng logic khi phân tích. Tuy nhiên, nếu cần bảo toàn chính xác văn bản, formatter hoặc công cụ chỉnh sửa cần giữ offset và văn bản gốc. Không nên thay đổi chuỗi nguồn trước khi lưu span nếu các offset sau đó cần trỏ về tệp ban đầu.

Một cách an toàn là giữ nguyên nguồn gốc, nhưng để cursor xử lý các dạng newline như cùng một sự kiện logic. Khi trích xuất token, dùng offset gốc để lấy đúng đoạn văn bản đã viết.

### 4.3. Các dấu phân dòng Unicode

Unicode có những ký tự phân dòng khác như Line Separator (U+2028) và Paragraph Separator (U+2029). DSL có thể hỗ trợ chúng như newline hoặc chỉ chấp nhận LF/CRLF/CR. Quyết định cần được ghi trong đặc tả lexer, bởi nó ảnh hưởng đến line tracking, chuỗi nhiều dòng và thông báo lỗi.

## 5. Cập nhật vị trí khi đọc ký tự

Lexer thường có một hàm duy nhất để tiến con trỏ và cập nhật vị trí. Mọi thao tác tiêu thụ ký tự nên đi qua hàm này, kể cả khi đọc khoảng trắng, chú thích, chuỗi nhiều dòng hoặc ký tự escape.

Một cursor có thể lưu:

```java
final class Cursor {
    private final String source;
    private final int tabWidth;
    private int offset;
    private int line = 1;
    private int column = 1;

    Cursor(String source, int tabWidth) {
        this.source = source;
        this.tabWidth = tabWidth;
    }

    boolean atEnd() {
        return offset >= source.length();
    }

    int peekCodePoint() {
        return atEnd() ? -1 : source.codePointAt(offset);
    }

    SourcePosition position() {
        return new SourcePosition(offset, line, column);
    }

    int advance() {
        if (atEnd()) {
            return -1;
        }

        int codePoint = source.codePointAt(offset);

        if (codePoint == '\r') {
            offset++;
            if (offset < source.length() && source.charAt(offset) == '\n') {
                offset++;
            }
            line++;
            column = 1;
            return '\n';
        }

        if (codePoint == '\n') {
            offset++;
            line++;
            column = 1;
            return codePoint;
        }

        offset += Character.charCount(codePoint);
        if (codePoint == '\t') {
            column = ((column - 1) / tabWidth + 1) * tabWidth + 1;
        } else {
            column++;
        }
        return codePoint;
    }
}
```

Trong ví dụ, offset tương thích với chỉ số UTF-16 của Java `String`; line và column bắt đầu từ 1; CRLF được tính là một newline; tab di chuyển đến tab stop tiếp theo. Cột đếm code point thông thường, còn tab được mở rộng theo `tabWidth`.

Đây là một cursor minh họa. Một triển khai thực tế cần xác thực `tabWidth` lớn hơn 0, quyết định cách xử lý U+2028/U+2029, quy định cột hiển thị cho ký tự kết hợp và cung cấp cách lưu/khôi phục trạng thái nếu parser có backtracking.

## 6. Theo dõi vị trí khi tạo token

Khi bắt đầu quét token, lexer lưu vị trí hiện tại. Sau khi tiêu thụ toàn bộ token, nó lưu vị trí kết thúc và tạo span.

Ví dụ giả mã:

```java
Token scanIdentifier() {
    SourcePosition start = cursor.position();
    StringBuilder text = new StringBuilder();

    while (isIdentifierPart(cursor.peekCodePoint())) {
        int cp = cursor.advance();
        text.appendCodePoint(cp);
    }

    SourcePosition end = cursor.position();
    return new Token(
        TokenType.IDENTIFIER,
        text.toString(),
        new SourceSpan(start, end)
    );
}
```

Việc dùng `appendCodePoint` bảo toàn ký tự ngoài BMP trong tên định danh nếu grammar cho phép. Điều kiện `isIdentifierPart` cũng cần nhận code point, không nên giả định mọi ký tự luôn chiếm một `char` Java.

Một token có thể lưu:

```java
record Token(
    TokenType type,
    String lexeme,
    SourceSpan span
) {}
```

Trong một lexer tối ưu, token có thể chỉ lưu loại và span, rồi lấy lexeme từ nguồn khi cần. Cách này tránh sao chép nhiều chuỗi, nhưng đòi hỏi nguồn vẫn còn tồn tại và span luôn hợp lệ.

## 7. Theo dõi vị trí trong lexer có lookahead

Lexer thường cần nhìn trước một hoặc nhiều ký tự để quyết định token. Ví dụ, khi gặp `=`, lexer cần kiểm tra ký tự tiếp theo để phân biệt `=` và `==`.

Có hai cách phổ biến:

- **Peek không tiêu thụ:** đọc ký tự ở offset hiện tại hoặc offset kế tiếp mà không thay đổi cursor. Đây thường là cách đơn giản nhất.
- **Mark và reset:** lưu toàn bộ trạng thái cursor trước khi thử một nhánh, rồi khôi phục nếu nhánh đó không phù hợp.

Nếu có reset, phải khôi phục tất cả thành phần vị trí: offset, line, column và mọi trạng thái phụ như vị trí sau tab hoặc trạng thái CRLF. Chỉ khôi phục offset mà quên line/column sẽ làm vị trí token sau đó sai.

Ví dụ trạng thái có thể được lưu:

```java
record CursorState(int offset, int line, int column) {}

CursorState mark() {
    return new CursorState(offset, line, column);
}

void restore(CursorState state) {
    offset = state.offset();
    line = state.line();
    column = state.column();
}
```

Với lexer chỉ dùng lookahead hữu hạn, peek thường ít lỗi hơn reset. Nếu parser hoặc lexer có backtracking phức tạp, trạng thái cursor cần được quản lý như một đối tượng bất biến hoặc snapshot rõ ràng.

## 8. Tab và cột hiển thị

Tab (`\t`) không nhất thiết chiếm một cột hiển thị. Editor thường mở rộng tab thành khoảng trắng đến tab stop tiếp theo. Nếu lexer chỉ tăng column thêm 1, vị trí báo lỗi có thể không trùng với cột mà người dùng nhìn thấy.

Giả sử tab width là 4 và cột được đánh số từ 1:

| Cột trước tab | Cột sau tab |
|---:|---:|
| 1 | 5 |
| 2 | 5 |
| 3 | 5 |
| 4 | 5 |
| 5 | 9 |

Công thức cập nhật trong ví dụ cursor là:

\[
nextColumn = \left\lfloor\frac{column - 1}{tabWidth}\right\rfloor \cdot tabWidth + tabWidth + 1
\]

Công thức này đưa vị trí đến đầu cột sau tab stop kế tiếp. Nếu editor cho phép tab width cấu hình theo dự án, lexer hoặc lớp hiển thị cần dùng cùng giá trị.

Một lựa chọn khác là lưu column logic theo số code point và chỉ tính cột hiển thị trong lớp diagnostics. Cách này tách ngữ nghĩa vị trí khỏi cách editor trình bày. Tuy nhiên, khi vẽ dấu `^` dưới lỗi trong terminal, lớp hiển thị phải mở rộng tab giống cách terminal hiển thị văn bản.

## 9. Unicode và khái niệm “một ký tự”

Unicode khiến việc đếm cột phức tạp hơn việc tăng biến đếm sau mỗi `char`.

### 9.1. Code unit và code point

Java `char` là một UTF-16 code unit. Một số ký tự Unicode ngoài Basic Multilingual Plane (BMP) được biểu diễn bằng cặp surrogate, tức hai `char` nhưng một code point.

Ví dụ:

```java
String text = "A😀B";
System.out.println(text.length());          // 4 UTF-16 code units
System.out.println(text.codePointCount(0, text.length())); // 3 code points
```

Nếu lexer tăng cột cho từng `char`, vị trí của `B` sẽ bị tính là cột 4 theo UTF-16 code unit, trong khi số code point trước nó chỉ là 2. Cả hai quy ước đều có thể dùng nếu được công bố, nhưng không được trộn lẫn.

### 9.2. Grapheme cluster

Một ký tự người dùng nhìn thấy đôi khi được tạo từ nhiều code point, chẳng hạn chữ cái kết hợp dấu phụ. Emoji cũng có thể gồm nhiều code point kết hợp bằng variation selector hoặc zero-width joiner. Vì vậy, số code point vẫn có thể khác số ký tự nhìn thấy.

Lexer thường không cần tính grapheme cluster để nhận diện token. Có thể giữ offset theo code unit và cột logic theo code point, rồi để editor tính cột hiển thị. Nếu cần gạch chân chính xác theo vị trí hiển thị, lớp giao diện cần dùng thuật toán phân đoạn grapheme và quy tắc độ rộng phù hợp.

### 9.3. Chuẩn hóa Unicode

Hai chuỗi có thể nhìn giống nhau nhưng được biểu diễn bằng chuỗi code point khác nhau, ví dụ ký tự có dấu có thể được mã hóa thành một code point dựng sẵn hoặc chữ cái cộng dấu kết hợp. Nếu DSL chuẩn hóa Unicode khi so sánh định danh, cần giữ ánh xạ từ tên chuẩn hóa về span gốc để thông báo lỗi vẫn trỏ đúng văn bản người dùng viết.

Không nên chuẩn hóa chuỗi nguồn một cách âm thầm rồi dùng offset trên chuỗi đã thay đổi để trỏ về tệp gốc. Nếu có bước chuẩn hóa, cần giữ source map hoặc quan hệ giữa offset trước và sau chuẩn hóa.

## 10. Vị trí trong chuỗi nhiều dòng và chú thích

Một chuỗi có thể chứa newline nếu DSL cho phép chuỗi nhiều dòng:

```text
message = "Dòng thứ nhất
Dòng thứ hai"
```

Lexer phải gọi cùng hàm cập nhật vị trí khi đọc bên trong chuỗi. Khi token kết thúc, span của token trải qua nhiều dòng; line/column cuối phải phản ánh vị trí sau dấu nháy đóng.

Chú thích cũng có thể kéo dài nhiều dòng:

```text
/*
  Cấu hình cho môi trường production.
  Người vận hành cần kiểm tra trước khi chạy.
*/
```

Nếu lexer bỏ qua chú thích mà không cập nhật line/column, mọi token phía sau sẽ sai vị trí. Do đó, dù whitespace và comment không được phát ra thành token chính, lexer vẫn phải tiêu thụ chúng qua cursor chung.

Một số DSL giữ comment như trivia để formatter và IDE có thể bảo toàn. Trong trường hợp đó, trivia cũng nên có source span giống token thông thường.

## 11. Vị trí token và thông báo lỗi

Token span cho phép parser báo lỗi chính xác. Ví dụ, nếu grammar yêu cầu `=` sau tên thuộc tính nhưng gặp số nguyên:

```text
replicas 3
```

Parser có thể báo:

```text
config.dsl:2:14: expected '=' after property name
replicas 3
         ^
```

Vị trí cột trong ví dụ là minh họa theo quy ước tab/Unicode đã chọn. Một diagnostic hữu ích thường chứa:

- Tên tệp hoặc URI nguồn.
- Vị trí bắt đầu và kết thúc của vùng lỗi.
- Mã lỗi ổn định để công cụ có thể phân loại.
- Thông điệp dễ hiểu.
- Token hoặc cấu trúc được mong đợi.
- Gợi ý sửa nếu có thể xác định an toàn.
- Vị trí liên quan khác, chẳng hạn nơi khai báo tên bị trùng.

Nên lưu span thay vì chỉ lưu một cặp dòng/cột. Offset giúp editor chọn chính xác vùng văn bản; dòng/cột giúp hiển thị cho con người. Nếu tệp được chỉnh sửa, dòng/cột cũ có thể không còn đúng, trong khi span gắn với revision nguồn cho biết chẩn đoán thuộc phiên bản nào.

## 12. Vị trí trong AST và lỗi ngữ nghĩa

Vị trí nguồn không chỉ dành cho token. Mỗi nút AST hoặc mô hình trung gian nên giữ span của cấu trúc tương ứng khi có thể.

Ví dụ:

```text
service "catalog" {
    replicas = -2
}
```

Parser có thể tạo AST hợp lệ cho thuộc tính `replicas`. Semantic analyzer phát hiện số lượng không hợp lệ và báo lỗi tại span của literal `-2` hoặc toàn bộ thuộc tính. Nếu mô hình miền giữ liên kết về nút AST, thông báo lỗi có thể chỉ đúng vùng nguồn dù kiểm tra diễn ra ở giai đoạn sau.

Một nút tổng hợp có thể có span bao trùm các nút con. Ví dụ, span của `ServiceDeclaration` bắt đầu ở từ khóa `service` và kết thúc ngay sau dấu `}` cuối. Span của `replicas` chỉ bao phủ khai báo thuộc tính tương ứng.

Với lỗi liên quan nhiều vị trí, diagnostics có thể chứa một vị trí chính và các vị trí phụ. Ví dụ khai báo tên trùng có thể trỏ đến khai báo thứ hai và kèm vị trí khai báo đầu tiên.

## 13. EOF và vị trí thiếu token

Khi parser cần một token nhưng đã đến cuối tài liệu, lỗi thường được đặt tại EOF. EOF không phải một ký tự thực trong nguồn, nhưng vẫn có vị trí hợp lệ: điểm ngay sau ký tự cuối cùng.

Ví dụ:

```text
service "catalog" {
    replicas = 3
```

Parser cần dấu `}` nhưng đã hết đầu vào. Nếu tài liệu có hai dòng và dòng cuối kết thúc sau `3`, vị trí EOF là cột ngay sau ký tự `3` trên dòng 2. Nếu tài liệu kết thúc bằng newline, vị trí EOF nằm ở dòng kế tiếp, cột 1 theo quy ước cursor đã nêu.

Nên thống nhất cách tính EOF để parser, editor và diagnostics không đưa ra vị trí khác nhau. Một token EOF có thể có span rỗng `[n, n)` tại offset cuối.

## 14. Nguồn nhiều tệp và source map

Một dự án DSL có thể nhập nhiều tệp hoặc sinh cấu hình từ template. Khi đó, vị trí nguồn cần xác định cả tệp và đoạn văn bản.

Một cấu trúc source location có thể gồm:

```java
record SourceId(String uri) {}

record SourceLocation(
    SourceId source,
    SourceSpan span
) {}
```

Nếu một tệp được ghép từ nhiều nguồn, hoặc DSL được sinh từ template, source map ánh xạ vị trí trong văn bản sinh ra về vị trí trong nguồn ban đầu. Điều này giúp lỗi runtime hoặc lỗi parser trong tệp sinh ra vẫn trỏ về template hoặc cấu hình mà người dùng có thể sửa.

Ví dụ, template `service.template` có thể sinh `generated.dsl`. Nếu token ở offset 120 trong `generated.dsl` bắt nguồn từ dòng 8 của template, source map giữ quan hệ đó. Không nên giả định offset của hai tài liệu giống nhau.

## 15. Đồng bộ vị trí với IDE và LSP

IDE thường cần vị trí để tô màu token, đặt con trỏ, hiển thị hover, điều hướng đến khai báo và gạch chân lỗi. Các giao thức như LSP biểu diễn vị trí theo dòng và ký tự, thường dùng chỉ số bắt đầu từ 0 trong thông điệp giao tiếp. Trong khi đó, tài liệu hướng người dùng thường đánh số từ 1.

Vì vậy, lớp tích hợp cần chuyển đổi rõ ràng:

- Lexer có thể dùng offset UTF-16 và line/column 1-based.
- API nội bộ có thể giữ span half-open.
- LSP adapter chuyển sang line/character 0-based và position encoding đã thương lượng.
- Giao diện có thể chuyển về cách hiển thị 1-based.

Không nên sửa quy ước nội bộ chỉ để khớp một giao thức. Tạo lớp chuyển đổi ở ranh giới giúp lexer không phụ thuộc vào editor cụ thể.

## 16. Phân tích gia tăng và vị trí sau khi chỉnh sửa

Trong IDE, người dùng có thể sửa một đoạn nhỏ của tài liệu. Các token và AST phía sau vùng sửa có thể cần được tính lại vị trí vì offset, dòng hoặc cột đã thay đổi.

Một hệ thống incremental lexer có thể:

1. Xác định vùng văn bản bị sửa và revision mới.
2. Tìm điểm bắt đầu an toàn để quét lại, thường là đầu token hoặc vùng lexical state ổn định trước thay đổi.
3. Quét lại các token bị ảnh hưởng.
4. Dịch chuyển hoặc tính lại span của các token sau vùng sửa.
5. Tiếp tục đến khi trạng thái lexer và chuỗi token khớp với một điểm đồng bộ cũ.
6. Cập nhật diagnostics gắn với revision mới.

Nếu chỉnh sửa thêm một newline, vị trí dòng của mọi token phía sau có thể tăng. Nếu chỉnh sửa chỉ thay một ký tự trong cùng dòng, offset và cột phía sau có thể thay đổi nhưng line không đổi. Cần dùng revision để tránh áp dụng kết quả phân tích cũ lên tài liệu mới.

Với DSL nhỏ, phân tích lại toàn bộ tệp thường đơn giản và đủ nhanh. Incremental lexing chỉ cần khi tài liệu lớn hoặc công cụ tương tác cần phản hồi nhanh.

## 17. Các lỗi thường gặp khi theo dõi vị trí

Một số lỗi triển khai phổ biến:

- Chỉ tăng dòng khi gặp LF nên xử lý sai CR đơn.
- Tính CRLF thành hai lần xuống dòng.
- Quên cập nhật vị trí khi bỏ qua whitespace hoặc comment.
- Tăng cột theo `char` trong Java và làm lệch vị trí sau surrogate pair.
- Dùng một quy ước cột cho lexer và quy ước khác cho IDE mà không chuyển đổi.
- Tính tab như một ký tự thông thường trong khi editor mở rộng tab.
- Lưu offset byte nhưng dùng trực tiếp làm chỉ số `String.substring()`.
- Reset con trỏ khi backtracking nhưng quên khôi phục line/column.
- Chỉ lưu dòng/cột mà không lưu offset hoặc source span.
- Tạo diagnostics từ revision cũ sau khi tài liệu đã thay đổi.
- Chuẩn hóa Unicode hoặc newline trước khi lưu source map.

Cách giảm lỗi hiệu quả là tập trung việc di chuyển cursor vào một API duy nhất, định nghĩa rõ đơn vị của từng trường vị trí và kiểm thử với nhiều dạng văn bản thay vì chỉ dùng ví dụ ASCII một dòng.

## 18. Kiểm thử line và column tracking

Bộ kiểm thử nên bao gồm các trường hợp có thể làm sai lệch vị trí:

| Trường hợp | Đầu vào hoặc tình huống | Điều cần xác nhận |
|---|---|---|
| ASCII một dòng | `a = 1` | Offset và cột tăng đúng |
| LF | Hai dòng phân cách bằng `\n` | Dòng sau bắt đầu ở line kế tiếp, column 1 |
| CRLF | Hai dòng phân cách bằng `\r\n` | Chỉ tăng line một lần |
| CR đơn | Hai dòng phân cách bằng `\r` | Newline được nhận diện theo đặc tả |
| Tab | Dòng có `\t` | Cột theo đúng tab width |
| Ký tự ngoài BMP | Tên hoặc chuỗi có emoji | Offset UTF-16 và cột code point nhất quán |
| Dấu kết hợp | Chữ cái cộng combining mark | Quy ước cột được áp dụng đúng |
| Comment nhiều dòng | Khối comment qua nhiều dòng | Token sau comment có vị trí đúng |
| Chuỗi nhiều dòng | Literal chứa newline | Span và vị trí cuối token chính xác |
| EOF | Tệp kết thúc ngay sau token hoặc newline | Vị trí EOF đúng quy ước |
| Backtracking | Lexer mark rồi restore | Toàn bộ trạng thái cursor được khôi phục |

Nên kiểm tra cả span của token và vị trí trong diagnostics. Ví dụ, với token `port`, xác nhận `source.substring(startOffset, endOffset)` trả đúng lexeme và line/column tương ứng với vị trí hiển thị.

Một số kiểm thử có thể kiểm tra tính chất tổng quát: offset luôn không giảm; line không giảm; column bắt đầu lại ở 1 sau newline; end offset không nhỏ hơn start offset; span của các token không chồng lấn nếu grammar không cho phép; và offset luôn nằm trong giới hạn nguồn.

## 19. Quy trình triển khai trong lexer

Có thể triển khai theo trình tự:

1. **Chọn quy ước vị trí:** xác định offset là byte, UTF-16 hay code point; line/column bắt đầu từ 0 hay 1; span đóng hay nửa mở.
2. **Xây cursor dùng chung:** cung cấp `peek`, `advance`, `position`, `mark` và `restore` nếu cần.
3. **Xử lý newline:** nhận diện LF, CRLF, CR và các dấu phân dòng được DSL hỗ trợ.
4. **Xử lý Unicode:** đọc code point đúng cách và định nghĩa cách tính cột.
5. **Xử lý tab:** thống nhất tab stop hoặc tách cột logic khỏi cột hiển thị.
6. **Gắn span vào token:** lưu vị trí bắt đầu và kết thúc ngay trong quá trình quét.
7. **Giữ vị trí trong AST:** liên kết nút cú pháp và mô hình với nguồn để diagnostics có thể trỏ ngược.
8. **Tạo adapter cho công cụ:** chuyển đổi sang định dạng vị trí mà IDE hoặc giao thức yêu cầu.
9. **Kiểm thử trường hợp biên:** dùng nhiều newline, Unicode, comment, chuỗi nhiều dòng, EOF và backtracking.
10. **Theo dõi revision:** nếu hỗ trợ chỉnh sửa tương tác, bảo đảm kết quả phân tích thuộc đúng phiên bản tài liệu.

## 20. Nguyên tắc thiết kế

- **Một nguồn cập nhật vị trí:** mọi thao tác tiêu thụ ký tự đều đi qua cursor chung.
- **Đơn vị được ghi rõ:** không dùng chung trường `offset` cho byte, code unit và code point.
- **Span nửa mở:** dùng `[start, end)` để trích xuất và kết hợp vùng nguồn thuận tiện.
- **Newline nhất quán:** CRLF được tính là một lần xuống dòng; CR và LF riêng được xử lý theo đặc tả.
- **Unicode có chủ đích:** phân biệt code unit, code point và grapheme cluster.
- **Tab phù hợp editor:** xác định tab width hoặc chuyển cột hiển thị ở lớp giao diện.
- **Giữ nguồn gốc:** token, AST và diagnostics cần biết tệp và revision tương ứng.
- **Không làm mất vị trí khi backtracking:** snapshot phải lưu đầy đủ trạng thái cursor.
- **Tách nội bộ khỏi giao thức:** chuyển đổi vị trí ở adapter thay vì để lexer phụ thuộc IDE.
- **Kiểm thử nhiều loại văn bản:** không chỉ dựa vào chuỗi ASCII một dòng.

Theo dõi dòng và cột là một phần cốt lõi của lexer vì nó kết nối cấu trúc chương trình với vị trí mà người viết nhìn thấy. Khi offset, line, column và source span được định nghĩa nhất quán; newline, tab và Unicode được xử lý có chủ đích; và vị trí được giữ qua AST, semantic analysis cùng công cụ IDE, DSL có thể đưa ra chẩn đoán chính xác và hỗ trợ chỉnh sửa đáng tin cậy.
