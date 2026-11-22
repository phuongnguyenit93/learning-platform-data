# Vị trí nguồn

Trong một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL), **vị trí nguồn** (*source location* hoặc *source position*) cho biết một token, nút cú pháp, khai báo hay lỗi xuất phát từ đâu trong tài liệu nguồn. Thông tin này giúp công cụ chỉ ra chính xác chỗ sai, đưa người dùng đến đúng dòng trong trình soạn thảo, hiển thị gợi ý sửa, theo dõi nguồn gốc của cấu trúc và liên kết mã được sinh với chương trình DSL ban đầu.

Ví dụ, người dùng viết:

~~~text
policy OrderPolicy {
    when order.totla > 1000 then approveOrder;
}
~~~

Nếu mô hình miền `Order` không có thuộc tính `totla`, bộ kiểm tra ngữ nghĩa cần báo lỗi ngay tại tên thuộc tính đó. Thông báo chung như “chương trình không hợp lệ” buộc người dùng tự tìm lỗi. Một chẩn đoán hữu ích cần chỉ ra tệp, dòng, cột và đoạn văn bản liên quan, có thể kèm gợi ý `total`.

Để làm được điều này, lexer, parser, AST, bộ kiểm tra ngữ nghĩa và các công cụ biên tập cần chia sẻ một quy ước vị trí thống nhất. Nếu mỗi thành phần tính offset, dòng và cột theo cách khác nhau, thông báo lỗi có thể trỏ sai ký tự, nhất là khi tệp chứa Unicode, tab, nhiều kiểu xuống dòng, cú pháp mở rộng hoặc mã được sinh tự động.

## 1. Vị trí nguồn là gì?

Vị trí nguồn là thông tin định vị một phần trong đầu vào đã tạo ra một thành phần của chương trình. Phần đầu vào đó thường là tệp văn bản DSL, nhưng cũng có thể là tài liệu đồ họa, cấu hình trong cơ sở dữ liệu, một đoạn mã được sinh hoặc nội dung nhận từ một dịch vụ.

Với DSL văn bản, vị trí nguồn thường gồm:

- **Định danh nguồn:** tệp, URI, tên tài liệu hoặc ID của nguồn đầu vào.
- **Offset bắt đầu:** vị trí ký tự hoặc đơn vị mã nơi đoạn nguồn bắt đầu.
- **Offset kết thúc:** vị trí ngay sau ký tự cuối cùng của đoạn nguồn, nếu dùng quy ước khoảng nửa mở.
- **Dòng:** số dòng chứa vị trí hoặc đoạn nguồn.
- **Cột:** vị trí theo chiều ngang trong dòng.
- **Đoạn nguồn:** văn bản gốc được token hoặc nút cú pháp đại diện.
- **Phiên bản nguồn:** phiên bản tài liệu mà vị trí đang tham chiếu, hữu ích trong trình soạn thảo và xử lý gia tăng.

Ví dụ, token `totla` có thể được ghi nhận như sau:

~~~text
Source: policies/order.dsl
Start offset: 37
End offset: 42
Start line: 2
Start column: 20
End line: 2
End column: 25
Text: "totla"
~~~

Các con số chỉ mang tính minh họa; vị trí chính xác phụ thuộc vào nội dung đầy đủ của tệp và quy ước đếm được chọn.

### Source position và source range/span

Hai khái niệm thường được dùng cùng nhau:

- **Source position** là một điểm trong nguồn, ví dụ vị trí con trỏ hoặc điểm bắt đầu một token.
- **Source range** hoặc **source span** là một đoạn nguồn có điểm bắt đầu và kết thúc, ví dụ toàn bộ tên `totla` hoặc toàn bộ biểu thức `order.total > 1000`.

Một chẩn đoán thường cần một span để tô sáng đoạn có vấn đề. Một thao tác điều hướng có thể chỉ cần một position. Trong thiết kế API, nên phân biệt rõ để tránh truyền nhầm một điểm với một đoạn.

## 2. Vị trí nguồn được sử dụng ở đâu?

Vị trí nguồn không chỉ phục vụ thông báo lỗi. Nó là thông tin nền tảng xuyên suốt vòng đời xử lý DSL.

| Thành phần | Cách sử dụng vị trí nguồn |
|---|---|
| Lexer | Gắn vị trí bắt đầu/kết thúc cho từng token; báo ký tự không hợp lệ. |
| Parser | Xác định vị trí cấu trúc cú pháp; báo thiếu token hoặc cấu trúc sai. |
| CST và AST | Liên kết nút cú pháp với đoạn nguồn đã tạo ra nút. |
| Bộ phân giải tên | Trỏ đến tên biến, kiểu, thuộc tính hoặc hành động không tồn tại. |
| Bộ kiểm tra kiểu và ngữ nghĩa | Đánh dấu biểu thức sai kiểu, vi phạm quy tắc hoặc tham chiếu không hợp lệ. |
| Trình thông dịch | Ghi nhận vị trí quy tắc đang thực thi khi xảy ra lỗi lúc chạy. |
| Trình sinh mã | Tạo ánh xạ từ mã đích về nguồn DSL để gỡ lỗi. |
| IDE và Language Server | Hiển thị lỗi, điều hướng định nghĩa, hover, gợi ý và tô sáng đoạn mã. |
| Formatter và refactoring | Giữ comment, định dạng, thay tên hoặc di chuyển cấu trúc đúng vị trí. |
| Nhật ký và kiểm toán | Ghi lại quy tắc nguồn đã tạo ra một hành động hoặc quyết định. |

Nếu lexer không giữ vị trí token, parser có thể không xác định chính xác nơi một cấu trúc bắt đầu. Nếu AST bỏ toàn bộ thông tin nguồn, bộ kiểm tra ngữ nghĩa chỉ có thể báo lỗi ở mức chương trình hoặc phải tìm cách khôi phục vị trí bằng cơ chế khác. Vì vậy, vị trí nguồn nên được thiết kế ngay từ đầu thay vì bổ sung sau khi DSL đã có nhiều thành phần xử lý.

## 3. Các hệ tọa độ thường gặp

Một trong những vấn đề dễ gây lỗi nhất là “offset 10” hoặc “cột 10” có thể mang nhiều ý nghĩa khác nhau. Hệ thống phải định nghĩa đơn vị đo và quy ước sử dụng.

### Byte offset

Byte offset là số byte tính từ đầu chuỗi byte của tệp. Với UTF-8, một ký tự có thể chiếm từ một đến bốn byte. Byte offset phù hợp khi parser làm việc trực tiếp trên dữ liệu đã mã hóa, khi cần ánh xạ vào tệp nhị phân hoặc khi một thư viện parser trả vị trí theo byte.

Ví dụ, chuỗi `aéb` có ba ký tự Unicode nhưng khi mã hóa UTF-8 có thể chiếm bốn byte: `a` một byte, `é` hai byte và `b` một byte. Byte offset sau `é` khác chỉ số ký tự sau `é`.

### Character/code point offset

Character offset thường được dùng để chỉ số lượng ký tự tính từ đầu chuỗi. Tuy nhiên, “ký tự” cần được định nghĩa rõ. Trong Unicode, một code point là một giá trị mã Unicode; một ký tự mà người dùng nhìn thấy có thể được tạo bởi nhiều code point, ví dụ chữ cái kết hợp với dấu phụ.

Nếu đếm code point, một ký tự hiển thị có thể chiếm nhiều đơn vị. Điều này quan trọng khi DSL cho phép Unicode trong định danh hoặc chuỗi.

### UTF-16 code unit offset

JavaScript, Java và một số API trình soạn thảo sử dụng đơn vị mã UTF-16 trong biểu diễn chuỗi hoặc giao thức vị trí. Một code point ngoài Basic Multilingual Plane (BMP), chẳng hạn một số emoji, được biểu diễn bằng cặp surrogate và chiếm hai UTF-16 code unit.

Vì vậy, offset theo UTF-16 có thể khác offset theo byte UTF-8 và offset theo code point. Nếu parser viết bằng Rust trả byte offset nhưng IDE gửi vị trí theo UTF-16, cần chuyển đổi rõ ràng giữa hai hệ tọa độ.

### Dòng và cột

Dòng và cột dễ đọc với con người nhưng cũng có nhiều quy ước:

- Số dòng bắt đầu từ 0 hay từ 1?
- Số cột bắt đầu từ 0 hay từ 1?
- Cột được đếm theo byte, code point, UTF-16 code unit hay ô hiển thị?
- Tab được tính là một ký tự hay được mở rộng thành nhiều cột hiển thị?
- Ký tự kết hợp và ký tự có độ rộng hiển thị khác nhau được xử lý ra sao?

Không có một quy ước duy nhất phù hợp cho mọi giao diện. Điều quan trọng là quy ước nội bộ và quy ước ở ranh giới API phải được ghi rõ, đồng thời chuyển đổi đúng khi trao đổi với editor hoặc công cụ khác.

### Bảng so sánh

| Hệ tọa độ | Đơn vị | Trường hợp sử dụng thường gặp | Lưu ý |
|---|---|---|---|
| Byte offset | Byte | Đọc tệp, parser làm việc trên UTF-8, giao tiếp cấp thấp. | Không đồng nhất với chỉ số ký tự khi có Unicode nhiều byte. |
| Code point offset | Unicode code point | Xử lý chuỗi theo giá trị Unicode. | Không nhất thiết bằng số ký tự người dùng nhìn thấy. |
| UTF-16 offset | UTF-16 code unit | Java, JavaScript và nhiều API editor. | Code point ngoài BMP chiếm hai đơn vị. |
| Line/column | Dòng và đơn vị cột đã quy định | Chẩn đoán và điều hướng trong IDE. | Cần quy ước base, đơn vị cột và cách tính tab. |
| Visual column | Ô hiển thị | Tô sáng hoặc căn lề giao diện. | Phụ thuộc font, tab width và cách hiển thị Unicode. |

## 4. Quy ước offset và span

Một quy ước phổ biến là biểu diễn span bằng khoảng nửa mở (*half-open interval*): bắt đầu tại `start` và kết thúc ngay trước `end`. Span được viết là `[start, end)`.

Ví dụ, với chuỗi:

~~~text
approveOrder
~~~

nếu token bắt đầu ở offset 0 và có 12 đơn vị theo hệ đếm đang dùng, span là `[0, 12)`. Độ dài được tính bằng `end - start`, không cần cộng hoặc trừ thêm một đơn vị.

Ưu điểm của khoảng nửa mở:

- Span rỗng có thể biểu diễn bằng `start == end`.
- Hai span liền nhau có thể đặt `[0, 5)` và `[5, 9)` mà không chồng lấn.
- Độ dài luôn bằng `end - start`.
- Dễ dùng với các API cắt chuỗi phổ biến có chỉ số kết thúc loại trừ.

Một span có thể được mô hình hóa như sau:

~~~java
public record SourceSpan(int startOffset, int endOffset) {
    public SourceSpan {
        if (startOffset < 0 || endOffset < startOffset) {
            throw new IllegalArgumentException("Invalid source span");
        }
    }

    public int length() {
        return endOffset - startOffset;
    }
}
~~~

Đoạn mã này chỉ minh họa kiểu span với một hệ offset duy nhất. Trong hệ thống thực tế, cần biết offset thuộc tài liệu nào, phiên bản nào và đơn vị nào; không nên truyền một cặp số nguyên giữa các thành phần mà không có hợp đồng rõ ràng.

### Vị trí điểm và span rỗng

Một lỗi thiếu token thường không có đoạn ký tự sai để tô sáng. Ví dụ:

~~~text
when order.total > 1000
~~~

Nếu ngữ pháp yêu cầu `then Action ;`, parser phát hiện thiếu `then` tại cuối dòng. Có thể biểu diễn vị trí lỗi bằng span rỗng `[n, n)` ngay sau token cuối cùng. Editor có thể hiển thị dấu chèn tại vị trí đó và thông báo “Thiếu từ khóa `then`”.

Không nên tạo span giả bao trùm ký tự trước đó chỉ vì giao diện không biết hiển thị span rỗng. Tầng chẩn đoán nên giữ vị trí chính xác; giao diện có thể chọn cách trình bày phù hợp.

### Span của token và span của nút AST

Token thường có span hẹp đúng bằng phần văn bản tạo ra token. Nút AST có thể dùng span bao trùm toàn bộ cấu trúc.

Với:

~~~text
when order.total > 1000 then approveOrder;
~~~

- Token `when` có span của riêng từ khóa.
- Token `order` có span của tên `order`.
- Nút `GreaterThan` có span bao trùm `order.total > 1000`.
- Nút `ConditionalRule` có thể có span bao trùm từ `when` đến dấu `;`.

Việc định nghĩa span nút AST cần nhất quán. Thông thường, span của một nút bao trùm phần nguồn tạo ra cấu trúc đó, còn span của từng thành phần con được giữ riêng để có thể báo lỗi ở mức chính xác hơn.

## 5. Tính dòng và cột từ offset

Trong lexer hoặc parser, lưu offset thường đơn giản và hiệu quả hơn việc tính dòng/cột cho mọi ký tự. Khi cần chẩn đoán, hệ thống có thể chuyển offset thành dòng/cột bằng bảng vị trí bắt đầu của từng dòng.

### Bảng line starts

Giả sử nội dung nguồn là:

~~~text
policy OrderPolicy {
    when order.total > 1000 then approveOrder;
}
~~~

Một bộ quản lý nguồn có thể lưu các offset bắt đầu dòng:

~~~text
lineStarts = [0, 21, 68]
~~~

Các số chỉ là ví dụ minh họa cho một văn bản cụ thể. Với một offset bất kỳ, tìm phần tử lớn nhất trong `lineStarts` không vượt quá offset đó để xác định dòng. Cột tương đối bằng offset trừ vị trí bắt đầu dòng, sau đó chuyển sang đơn vị cột mà giao diện yêu cầu.

Nếu dùng binary search trên `lineStarts`, việc chuyển đổi có thể thực hiện trong thời gian `O(log n)`, với `n` là số dòng. Với tài liệu nhỏ, quét tuyến tính cũng có thể đủ; với IDE xử lý tệp lớn và nhiều chẩn đoán, bảng dòng giúp truy vấn nhanh hơn.

### Các kiểu xuống dòng

Tệp văn bản có thể dùng:

- `LF` (`\n`), phổ biến trên Linux và macOS hiện đại.
- `CRLF` (`\r\n`), phổ biến trên Windows.
- `CR` (`\r`), xuất hiện trong một số tệp cũ.

Nếu lexer chỉ nhận diện `\n`, tệp dùng `CR` đơn có thể khiến tính dòng sai. Nếu xử lý `CRLF` như hai lần xuống dòng, mọi dòng sau đó sẽ bị lệch. Bộ quản lý nguồn cần xác định rõ quy tắc nhận diện newline và thường coi `CRLF` là một dấu kết thúc dòng logic duy nhất.

### Tab và cột hiển thị

Tab thường được lưu thành một ký tự `\t`, nhưng trên màn hình có thể chiếm nhiều ô tùy tab width. Nếu một tab được đặt tại cột 1 và tab width là 4, vị trí hiển thị tiếp theo có thể là cột 4 hoặc 5 tùy quy ước tính cột. Vì vậy, cột offset và cột hiển thị không nên bị đồng nhất.

Parser nên giữ vị trí theo một đơn vị ổn định. Editor hoặc lớp hiển thị mới tính visual column dựa trên tab width, font và cách hiển thị văn bản.

### Unicode và ký tự kết hợp

Một ký tự người dùng nhìn thấy có thể được biểu diễn bởi nhiều code point. Ví dụ chữ `é` có thể được lưu dưới dạng một code point dựng sẵn hoặc chữ `e` cộng với dấu sắc kết hợp. Hai chuỗi có thể nhìn giống nhau nhưng có số đơn vị mã khác nhau.

Do đó:

- Không nên giả định một cột hiển thị luôn tương ứng với một byte hoặc một code unit.
- Cần xác định có chuẩn hóa Unicode đầu vào hay không.
- Nếu chuẩn hóa, phải giữ ánh xạ về văn bản gốc để vị trí lỗi không bị sai.
- Nếu không chuẩn hóa, mọi thành phần cần dùng cùng một chuỗi nguồn gốc và quy ước offset.

## 6. Quản lý văn bản nguồn

Một DSL có thể được phân tích từ nhiều tệp hoặc nhiều tài liệu. Vì vậy, span không chỉ là hai số offset; nó cần gắn với một nguồn cụ thể.

### Source identity

Source identity xác định tài liệu mà span tham chiếu đến. Nó có thể là:

- Đường dẫn tệp tương đối hoặc tuyệt đối.
- URI như `file:///project/policy.dsl`.
- ID tài liệu do IDE hoặc máy chủ cấp.
- ID của nội dung được tải từ database hoặc dịch vụ.
- Tên nguồn ảo như `generated://policy/compiled`.

Không nên chỉ lưu tên tệp hiển thị nếu nhiều thư mục có thể chứa cùng tên. Nên tách định danh ổn định dùng nội bộ khỏi tên thân thiện dùng trong thông báo.

### Source file và SourceText

Một thiết kế thường gặp là có đối tượng quản lý văn bản nguồn:

~~~java
public record SourceId(String value) {}

public final class SourceText {
    private final SourceId id;
    private final String text;
    private final int[] lineStarts;

    public SourceText(SourceId id, String text, int[] lineStarts) {
        this.id = id;
        this.text = text;
        this.lineStarts = lineStarts.clone();
    }

    public SourceId id() { return id; }
    public String text() { return text; }
    public int[] lineStarts() { return lineStarts.clone(); }
}
~~~

Ví dụ chỉ minh họa cấu trúc dữ liệu; một triển khai thực tế cần xây dựng `lineStarts`, quy định đơn vị offset, xử lý newline và quản lý phiên bản nội dung. Nên tránh để nhiều thành phần tự đọc lại tệp theo các cách khác nhau vì nội dung có thể đã thay đổi giữa lúc phân tích và lúc hiển thị lỗi.

### Nhiều nguồn trong một chương trình

Một dự án DSL có thể gồm nhiều tệp:

~~~text
project/
  main.dsl
  models/customer.dsl
  policies/order.dsl
  policies/shipping.dsl
~~~

`main.dsl` có thể import hoặc include các tệp khác. Khi một quy tắc trong `shipping.dsl` tham chiếu đến kiểu khai báo trong `customer.dsl`, lỗi có thể phát sinh trong tệp này nhưng được kích hoạt bởi một tham chiếu ở tệp kia.

Hệ thống cần giữ source identity cho từng nút, thay vì chỉ dùng offset toàn cục. Có thể định nghĩa `SourceSpan` chứa `SourceId` và hai offset; hoặc định nghĩa `SourceRange` chứa hai `SourcePosition` thuộc cùng một nguồn.

### Nguồn ảo và nội dung được tạo trong bộ nhớ

Không phải mọi nguồn đều có đường dẫn tệp. DSL có thể được nhập trong một biểu mẫu, nhận qua API hoặc tạo từ một mẫu. Trong trường hợp đó, source identity có thể là ID phiên làm việc hoặc URI ảo. Chẩn đoán vẫn cần vị trí để giao diện biết vùng nhập liệu nào cần làm nổi bật.

## 7. Gắn vị trí nguồn cho token

Lexer là thành phần đầu tiên có đủ thông tin để gắn span chính xác cho từng token. Lexer nên ghi nhận vị trí trước khi tiêu thụ ký tự và vị trí sau khi tiêu thụ token.

Một token có thể được mô hình hóa:

~~~java
public enum TokenKind {
    IDENTIFIER, NUMBER, WHEN, THEN,
    DOT, GREATER_THAN, SEMICOLON, EOF
}

public record Token(
    TokenKind kind,
    String lexeme,
    SourceSpan span
) {}
~~~

Với lexer dùng một offset thống nhất, thuật toán cơ bản:

1. Ghi `start = currentOffset` trước khi đọc token.
2. Đọc ký tự và tiêu thụ toàn bộ token theo quy tắc từ vựng.
3. Ghi `end = currentOffset` sau ký tự cuối cùng.
4. Tạo token với span `[start, end)`.

Ví dụ giả mã:

~~~text
scanToken():
    start = currentOffset
    kind = scanNextTokenKind()
    lexeme = source.substring(start, currentOffset)
    return Token(kind, lexeme, Span(start, currentOffset))
~~~

Token EOF thường có span rỗng tại cuối nguồn. Điều này cho phép parser báo lỗi khi cần thêm token mà đầu vào đã kết thúc.

### Giữ lexeme hay chỉ giữ span?

Token có thể lưu cả chuỗi `lexeme` và span, hoặc chỉ lưu loại token cùng span rồi truy xuất văn bản gốc khi cần. Lựa chọn phụ thuộc vào hiệu năng, bộ nhớ và vòng đời nguồn:

- Lưu lexeme giúp xử lý thuận tiện nhưng có thể tạo nhiều chuỗi con.
- Chỉ lưu span giảm sao chép nhưng cần giữ văn bản nguồn tồn tại đủ lâu.
- Một số ngôn ngữ runtime tạo substring có sao chép; một số API có cơ chế slice/view. Cần đo đạc thay vì giả định chi phí.

Nếu lexer bỏ comment và khoảng trắng, có thể lưu chúng như trivia gắn với token trước/sau hoặc giữ trong CST để formatter và IDE không làm mất nội dung.

## 8. Gắn vị trí nguồn cho nút CST và AST

Parser kết hợp token thành cấu trúc lớn hơn. Mỗi nút có thể giữ span bao trùm các thành phần nguồn đã tạo ra nó.

Ví dụ kiểu AST:

~~~java
public sealed interface Expr
    permits NameExpr, NumberExpr, PropertyExpr, GreaterThanExpr {
    SourceSpan span();
}

public record NameExpr(String name, SourceSpan span) implements Expr {}

public record NumberExpr(long value, SourceSpan span) implements Expr {}

public record PropertyExpr(
    Expr target,
    String property,
    SourceSpan span
) implements Expr {}

public record GreaterThanExpr(
    Expr left,
    Expr right,
    SourceSpan span
) implements Expr {}
~~~

Ví dụ này dùng record để minh họa. Nút AST có thể giữ span của toàn biểu thức, trong khi các nút con có span riêng. Khi phát hiện `property` không tồn tại, bộ kiểm tra có thể trỏ đến span của `NameExpr` hoặc trường tên thuộc tính trong `PropertyExpr` thay vì tô sáng toàn bộ phép so sánh.

### Span của nút cha

Thông thường, span của nút cha bắt đầu tại vị trí đầu tiên của thành phần cú pháp thuộc nút và kết thúc ngay sau thành phần cuối cùng. Cần quy định rõ có bao gồm dấu ngoặc, dấu kết thúc hoặc từ khóa hay không.

Ví dụ, span của `ConditionalRule` có thể bao gồm `when` và dấu `;`, còn span của `condition` chỉ bao gồm biểu thức. Cách làm này cho phép một lỗi về toàn bộ cấu trúc trỏ đến cả câu lệnh, còn lỗi thuộc tính trỏ đến tên thuộc tính.

### Nút tổng hợp và nút không có nguồn trực tiếp

Một số nút AST được tạo ra trong quá trình chuẩn hóa hoặc desugaring mà không tương ứng trực tiếp với đoạn văn bản riêng. Ví dụ, cú pháp rút gọn `allowPaidOrders` có thể được mở rộng thành điều kiện và hành động chuẩn. Nút tổng hợp có thể:

- Kế thừa span của cấu trúc nguồn đã tạo ra nó.
- Mang một loại origin riêng chỉ ra nó được sinh từ cú pháp nào.
- Không có span trực tiếp nhưng giữ liên kết đến nút cha hoặc nguồn gốc.

Không nên gán một vị trí tùy tiện như offset 0 cho nút không có nguồn. Điều đó có thể làm lỗi xuất hiện ở đầu tệp và gây hiểu nhầm.

## 9. Chẩn đoán lỗi dựa trên vị trí nguồn

Một **diagnostic** là thông tin có cấu trúc mô tả vấn đề được phát hiện trong chương trình. Diagnostic thường có mức độ, mã lỗi, thông điệp, vị trí chính và các vị trí liên quan.

Các trường phổ biến:

| Trường | Ý nghĩa |
|---|---|
| Severity | `Error`, `Warning`, `Information` hoặc `Hint`. |
| Code | Mã ổn định để tra tài liệu hoặc lọc lỗi, ví dụ `DSL1004`. |
| Message | Mô tả ngắn gọn vấn đề theo ngôn ngữ người dùng. |
| Primary span | Đoạn nguồn chính cần được làm nổi bật. |
| Related spans | Các vị trí liên quan như khai báo gốc hoặc tham chiếu khác. |
| Notes | Giải thích thêm hoặc điều kiện gây lỗi. |
| Fixes | Gợi ý hoặc thao tác sửa có thể áp dụng. |

Ví dụ:

~~~text
policies/order.dsl:2:20: error DSL2003: Unknown property 'totla' on type 'Order'.
  2 |     when order.totla > 1000 then approveOrder;
    |                   ^^^^^
  help: Did you mean 'total'?
~~~

Vị trí hiển thị thường là dòng/cột bắt đầu từ 1 để người đọc dễ hiểu, trong khi API nội bộ có thể dùng chỉ số bắt đầu từ 0. Lớp trình bày cần chuyển đổi đúng.

### Primary span và related span

Một lỗi có thể liên quan đến nhiều vị trí. Ví dụ, một định danh bị khai báo trùng:

~~~text
entity Customer { ... }
entity Customer { ... }
~~~

Span chính có thể trỏ đến khai báo thứ hai; related span trỏ đến khai báo đầu tiên. Thông báo có thể nói “`Customer` đã được khai báo ở đây” và đưa người dùng đến vị trí gốc.

Với tham chiếu chưa được khai báo, span chính là nơi tham chiếu; related span có thể chỉ đến phạm vi tìm kiếm hoặc không có nếu không tồn tại khai báo phù hợp.

### Chẩn đoán cú pháp, ngữ nghĩa và lúc chạy

- **Lỗi từ vựng:** ký tự hoặc chuỗi ký tự không tạo thành token hợp lệ.
- **Lỗi cú pháp:** token không thể kết hợp theo ngữ pháp.
- **Lỗi cấu trúc:** AST không thỏa metamodel hoặc thiếu thành phần bắt buộc.
- **Lỗi phân giải tên:** tên được dùng nhưng không có khai báo phù hợp.
- **Lỗi kiểu:** biểu thức hoặc đối số không tương thích kiểu.
- **Vi phạm quy tắc miền:** cấu trúc hoặc dữ liệu vi phạm chính sách nghiệp vụ.
- **Lỗi lúc chạy:** thao tác thực thi thất bại; cần liên kết lỗi với quy tắc nguồn đã kích hoạt thao tác.

Mỗi loại lỗi nên gắn với span phù hợp. Không nên gán mọi lỗi vào toàn bộ dòng hoặc toàn bộ tệp.

## 10. Thông báo lỗi và gợi ý sửa

Vị trí chính xác là nền tảng để tạo trải nghiệm sửa lỗi tốt. Một diagnostic có thể cung cấp một hoặc nhiều gợi ý sửa (*code actions* hoặc *quick fixes*).

Ví dụ, DSL:

~~~text
when order.totla > 1000 then approveOrder;
~~~

Diagnostic có thể cung cấp thay thế `totla` bằng `total`. Để thực hiện, công cụ cần biết span chính xác của tên thuộc tính. Nếu chỉ biết dòng 2, việc thay thế có thể vô tình ghi đè cả biểu thức hoặc khoảng trắng.

Một gợi ý sửa nên chứa:

- Span cần thay đổi.
- Văn bản thay thế hoặc thao tác cấu trúc.
- Tiêu đề dễ hiểu.
- Điều kiện áp dụng, nếu chỉ hợp lệ trong một ngữ cảnh.

Ví dụ dạng dữ liệu:

~~~text
Diagnostic:
  code: DSL2003
  message: Unknown property 'totla' on type 'Order'
  span: [37, 42)
  suggestion:
    title: Replace with 'total'
    span: [37, 42)
    newText: "total"
~~~

Đây là dạng minh họa, không phải định dạng chuẩn của một giao thức cụ thể.

## 11. Vị trí nguồn trong Language Server và IDE

Một DSL thường cần tích hợp với trình soạn thảo để hiển thị lỗi và hỗ trợ người dùng khi viết mã. Language Server Protocol (LSP) là một giao thức phổ biến để tách logic ngôn ngữ khỏi IDE.

Trong LSP, tài liệu được định danh bằng URI. Vị trí được biểu diễn bằng dòng và ký tự, với chỉ số bắt đầu từ 0; trường `character` sử dụng UTF-16 code unit theo quy ước của giao thức. Diagnostic có range gồm vị trí bắt đầu và kết thúc.

Điều này tạo ra một yêu cầu quan trọng: nếu lexer hoặc parser lưu byte offset UTF-8, server phải chuyển byte offset sang dòng và UTF-16 column trước khi gửi diagnostic. Không được gửi byte offset trực tiếp vào trường `character`.

### Các tính năng IDE dùng vị trí nguồn

| Tính năng | Cách sử dụng vị trí |
|---|---|
| Diagnostics | Tô sáng đoạn có lỗi và hiển thị thông điệp. |
| Go to Definition | Điều hướng từ tham chiếu đến span khai báo. |
| Find References | Liệt kê span của mọi tham chiếu đến một định nghĩa. |
| Hover | Xác định token hoặc nút tại con trỏ để hiển thị kiểu và tài liệu. |
| Completion | Xác định vị trí và ngữ cảnh cú pháp hiện tại để gợi ý hợp lệ. |
| Rename | Tìm và thay các span tham chiếu chính xác. |
| Code Action | Thay thế hoặc chèn văn bản tại span cần sửa. |
| Semantic Highlighting | Ánh xạ token hoặc nút AST thành đoạn cần tô màu theo vai trò ngữ nghĩa. |

### Đồng bộ tài liệu và phiên bản nguồn

Trong IDE, người dùng có thể sửa tài liệu trong lúc server đang phân tích. Diagnostic được tính từ phiên bản cũ có thể trỏ sai sau khi người dùng chèn hoặc xóa văn bản ở phía trước.

Server cần gắn kết quả phân tích với phiên bản tài liệu. Khi nhận thay đổi mới, nó có thể hủy hoặc bỏ qua kết quả cũ và phân tích lại. Nếu gửi diagnostic cho phiên bản không còn hiện hành, giao diện có thể tô sáng nhầm vị trí.

## 12. Xử lý Unicode, encoding và BOM

Vị trí nguồn cần được thiết kế cùng với cách đọc văn bản. Tệp DSL có thể được mã hóa UTF-8, UTF-16 hoặc một encoding khác tùy quy ước dự án.

### Giải mã trước khi phân tích

Một kiến trúc thường gặp là:

1. Đọc byte từ tệp.
2. Nhận diện encoding theo quy ước hoặc cấu hình.
3. Giải mã thành chuỗi nội bộ.
4. Xây dựng ánh xạ giữa byte offset và offset chuỗi nếu cần.
5. Lexer làm việc theo hệ tọa độ đã chọn.

Nếu giải mã gặp chuỗi byte không hợp lệ, cần báo lỗi ở lớp đọc/giải mã và gắn vị trí byte nếu có thể. Không nên âm thầm thay ký tự lỗi bằng ký hiệu thay thế rồi tiếp tục như thể nội dung ban đầu vẫn chính xác, trừ khi DSL quy định rõ cách phục hồi.

### Byte offset và UTF-16 offset không thể thay thế nhau

Ví dụ, một tệp UTF-8 chứa ký tự tiếng Việt hoặc emoji có thể có số byte lớn hơn số code point. Nếu một thư viện trả về byte offset 20, còn IDE cần UTF-16 column 18, phải dùng ánh xạ dựa trên văn bản đã giải mã để chuyển đổi.

### Byte Order Mark

Một số tệp có BOM ở đầu. Hệ thống cần quyết định BOM có được xem là phần văn bản hay chỉ là dấu nhận diện encoding. Nếu lexer bỏ BOM, offset nguồn phải nhất quán với quy ước đó; nếu công cụ cần giữ nguyên tệp khi ghi lại, cần bảo toàn thông tin encoding/BOM ở lớp quản lý nguồn.

### Chuẩn hóa Unicode

Hai chuỗi có thể hiển thị giống nhau nhưng khác chuỗi code point do cách biểu diễn Unicode. Nếu DSL chuẩn hóa tên trước khi so sánh, cần xác định dạng chuẩn và giữ ánh xạ về đoạn nguồn gốc. Nếu không, việc báo lỗi hoặc đổi tên vẫn phải dựa trên văn bản nguyên gốc mà người dùng nhìn thấy.

## 13. Source location trong macro, include và cú pháp mở rộng

Một DSL có thể hỗ trợ macro, template, include, import, alias hoặc cú pháp rút gọn. Khi mở rộng một cấu trúc, AST kết quả có thể không còn ánh xạ đơn giản một-một với đoạn nguồn.

Ví dụ:

~~~text
standardOrderPolicy;
~~~

Macro `standardOrderPolicy` có thể mở rộng thành nhiều quy tắc. Nếu một quy tắc mở rộng gây lỗi, người dùng cần biết lỗi xuất phát từ macro ở tệp nào, dòng nào, và có thể cần xem cả định nghĩa macro.

### Nguồn gọi và nguồn định nghĩa

Với macro hoặc template, cần phân biệt:

- **Call site:** nơi người dùng gọi macro hoặc sử dụng template.
- **Definition site:** nơi macro hoặc template được định nghĩa.
- **Expansion site:** cấu trúc sau khi mở rộng, có thể không có đoạn văn bản độc lập.

Một chẩn đoán có thể chỉ ra vị trí gọi là vị trí chính, đồng thời thêm vị trí định nghĩa làm thông tin liên quan. Với lỗi do đối số truyền vào, span có thể trỏ đến đối số ở call site.

### Source origin chain

Khi cấu trúc được biến đổi nhiều lần, nên giữ chuỗi nguồn gốc (*origin chain*) thay vì chỉ giữ một span cuối cùng. Ví dụ:

~~~text
Generated node
  <- expanded from macro invocation at main.dsl:12
  <- macro defined at macros/order.dsl:4
  <- argument supplied at main.dsl:12
~~~

Chuỗi này giúp chẩn đoán giải thích cả nơi sử dụng lẫn nơi định nghĩa. Không phải lỗi nào cũng cần hiển thị toàn bộ chuỗi; diagnostic có thể chọn vị trí phù hợp và cung cấp các vị trí liên quan.

### Include và import

Khi một tệp include tệp khác, mỗi token hoặc nút AST phải giữ nguồn của chính nó. Không nên chuyển mọi vị trí về tệp gốc vì điều đó làm mất khả năng điều hướng đến nội dung thực sự gây lỗi.

Nếu một khai báo trong tệp A không hợp lệ vì xung đột với khai báo ở tệp B, diagnostic có thể có primary span ở B và related span ở A, tùy nơi phát hiện và quy tắc báo lỗi của DSL.

## 14. Source map cho mã được sinh

Một số DSL không được thực thi trực tiếp mà được chuyển thành Java, JavaScript, SQL, cấu hình hoặc mã của nền tảng khác. Khi lỗi xuất hiện trong mã đích, người dùng thường muốn biết dòng DSL ban đầu nào đã tạo ra đoạn mã đó.

**Source map** là cơ chế ánh xạ vị trí trong tài liệu được sinh hoặc biến đổi về vị trí trong nguồn gốc. Source map có thể liên kết:

- Vị trí trong tệp mã đích.
- Vị trí trong tệp DSL nguồn.
- Tên nguồn và tên định danh liên quan.
- Các bước biến đổi hoặc thông tin bổ sung nếu định dạng hỗ trợ.

Ví dụ, DSL:

~~~text
when order.total > 1000 then approveOrder;
~~~

có thể được chuyển thành Java:

~~~java
if (order.getTotal().compareTo(new BigDecimal("1000")) > 0) {
    orderService.approve(order);
}
~~~

Nếu dòng gọi `orderService.approve(order)` ném lỗi, stack trace Java chỉ cho biết vị trí trong mã sinh. Source map cho phép công cụ gỡ lỗi dẫn người dùng về câu lệnh DSL ban đầu.

### Ánh xạ một-nhiều và nhiều-một

Một câu lệnh DSL có thể sinh nhiều dòng mã đích; nhiều câu lệnh DSL có thể được gộp thành một đoạn mã đích. Vì vậy, ánh xạ không nhất thiết là một-một.

Ví dụ, một khai báo chính sách có thể sinh lớp Java, hàm kiểm tra, cấu hình và mã đăng ký. Nếu lỗi xảy ra trong một phần sinh ra, công cụ cần xác định nguồn DSL phù hợp nhất.

### Vị trí tổng hợp và mã sinh tự động

Một số mã đích không tương ứng trực tiếp với câu lệnh nguồn, chẳng hạn mã khởi tạo hoặc mã hỗ trợ. Công cụ có thể:

- Đánh dấu mã là generated và không gán span nguồn giả.
- Gắn mã với khai báo DSL bao quanh đã tạo ra cấu trúc.
- Cung cấp thông tin origin trong metadata hoặc source map.
- Ẩn một số frame mã sinh trong stack trace thân thiện với người dùng.

Không nên giả vờ rằng mọi dòng mã đích đều đến từ một dòng DSL cụ thể nếu thực tế không có quan hệ đó.

## 15. Vị trí nguồn trong formatter và refactoring

Formatter và refactoring thay đổi cách biểu diễn mã nhưng cần giữ ý nghĩa và nội dung mà người dùng không yêu cầu thay đổi.

### Formatter

Formatter đọc CST hoặc AST cùng thông tin nguồn để chuẩn hóa khoảng trắng, thụt lề, dấu ngoặc và xuống dòng. Nếu cần giữ comment, formatter phải có cách gắn comment với cấu trúc hoặc token liên quan.

Ví dụ:

~~~text
when(order.total>1000)then approveOrder;
~~~

có thể được định dạng thành:

~~~text
when order.total > 1000 then approveOrder;
~~~

AST có thể không đổi, nhưng văn bản nguồn và span của các token thay đổi. Sau khi formatter chạy, mọi vị trí được lưu từ phiên bản cũ không còn hợp lệ cho văn bản mới. Cần xây dựng lại hoặc cập nhật ánh xạ vị trí.

### Rename symbol

Khi đổi tên `approveOrder` thành `confirmOrder`, công cụ cần tìm mọi tham chiếu đúng với định nghĩa và thay đúng span. Không nên thay mọi chuỗi có cùng ký tự, vì một chuỗi literal hoặc comment có thể chứa cùng văn bản nhưng không phải tham chiếu.

### Di chuyển hoặc tái cấu trúc cấu trúc

Khi di chuyển một khai báo giữa các tệp, source identity và span của nó thay đổi. Các tham chiếu, lỗi và thông tin điều hướng phải được cập nhật dựa trên mô hình ngữ nghĩa mới.

## 16. Phân tích gia tăng và chỉnh sửa tài liệu

IDE thường không phân tích lại toàn bộ dự án sau mỗi ký tự người dùng gõ. Nó có thể nhận một vùng thay đổi và cập nhật lexer, parser, AST cùng chẩn đoán theo cách gia tăng.

Ví dụ, người dùng chèn 5 ký tự ở đầu tệp. Mọi offset phía sau điểm chèn sẽ tăng thêm 5 đơn vị trong hệ tọa độ tương ứng. Nếu người dùng xóa một đoạn, các vị trí phía sau sẽ dịch ngược lại.

Một hệ thống phân tích gia tăng cần:

- Xác định span thay đổi trong phiên bản tài liệu cũ.
- Áp dụng chỉnh sửa theo thứ tự và quy ước offset của giao thức.
- Cập nhật bảng dòng và thông tin nguồn.
- Tái sử dụng token hoặc nút AST không bị ảnh hưởng nếu có thể.
- Vô hiệu hóa span và diagnostic thuộc phiên bản cũ.
- Phát hành kết quả mới gắn với phiên bản tài liệu hiện tại.

Không nên lưu một span rồi sử dụng vô thời hạn sau khi văn bản thay đổi. Span là vị trí trong một phiên bản nguồn cụ thể. Nếu cần giữ tham chiếu bền vững qua nhiều lần chỉnh sửa, cần dùng cơ chế tracking riêng như anchor, syntax node identity hoặc mapping giữa các phiên bản.

## 17. Hiệu năng và bộ nhớ

Lưu vị trí cho mọi token và nút AST làm tăng bộ nhớ, nhưng thường là chi phí cần thiết cho công cụ phát triển tốt. Có nhiều cách tối ưu:

- Lưu hai offset nguyên thay vì lặp lại cả dòng và cột trên mọi nút.
- Lưu `SourceId` ở cấp tài liệu hoặc trong bảng nguồn dùng chung.
- Dùng cấu trúc compact cho token nếu số lượng rất lớn.
- Tính dòng/cột khi cần dựa trên bảng line starts.
- Chỉ giữ CST đầy đủ khi cần formatter hoặc IDE; compiler đơn giản có thể giữ AST và span.
- Chia sẻ văn bản nguồn bất biến giữa các token thay vì sao chép lexeme liên tục.
- Dùng chỉ số hoặc ID nút để lưu liên kết nguồn gốc thay vì tạo nhiều đối tượng lặp lại.

Tối ưu hóa không nên làm mất khả năng chẩn đoán. Có thể chọn giữ thông tin nguồn chi tiết trong chế độ IDE/debug và giảm metadata trong bản phát hành thực thi, miễn là hành vi được quy định rõ.

## 18. Kiểm thử vị trí nguồn

Vị trí nguồn cần được kiểm thử độc lập với kiểm thử ngữ nghĩa. Một chương trình có thể phân tích đúng nhưng chẩn đoán sai dòng/cột, đặc biệt với Unicode hoặc newline khác nhau.

Các nhóm kiểm thử hữu ích:

| Nhóm | Trường hợp cần kiểm tra |
|---|---|
| Token cơ bản | Span của định danh, số, toán tử và từ khóa đúng đầu/cuối. |
| Span rỗng | EOF và vị trí thiếu token được biểu diễn chính xác. |
| Dòng | LF, CRLF, CR và tệp không có newline cuối. |
| Cột | Offset ở đầu dòng, cuối dòng, sau tab và trước/sau Unicode. |
| Encoding | UTF-8 nhiều byte, UTF-16 surrogate pair và BOM theo chính sách. |
| CST/AST | Span cha bao trùm con và span nút con đúng đoạn nguồn. |
| Nhiều tệp | Diagnostic trỏ đúng source identity khi import/include. |
| Biến đổi | Macro, desugaring và code generation giữ origin phù hợp. |
| IDE | Chuyển đổi đúng giữa offset nội bộ và vị trí LSP/editor. |
| Chỉnh sửa gia tăng | Span và diagnostic cũ không bị dùng sau khi tài liệu thay đổi. |
| Refactoring | Rename hoặc quick fix chỉ sửa đúng đoạn nguồn. |

### Ví dụ kiểm thử span

~~~java
@Test
void identifierTokenHasHalfOpenSpan() {
    SourceText source = source("order.total");
    Token token = lexer(source).nextToken();

    assertEquals(TokenKind.IDENTIFIER, token.kind());
    assertEquals("order", source.slice(token.span()));
    assertEquals(0, token.span().startOffset());
    assertEquals(5, token.span().endOffset());
}
~~~

Đây là ví dụ minh họa cho một lexer dùng offset theo đơn vị của chuỗi. Bộ kiểm thử đầy đủ cần xác định rõ helper `source`, quy tắc token hóa và đơn vị offset.

### Kiểm thử chuyển đổi Unicode

Giả sử nguồn chứa ký tự ngoài BMP trước một token cần báo lỗi. Hãy xác nhận:

1. Byte offset của token được tính đúng theo UTF-8 nếu lexer dùng byte.
2. UTF-16 offset được tính đúng khi gửi cho editor theo LSP.
3. Dòng và cột hiển thị trỏ đến đúng token.
4. Span cắt chuỗi nội bộ vẫn trả về đúng lexeme.

Không nên chỉ kiểm thử với văn bản ASCII vì mọi hệ tọa độ thường trùng nhau trong trường hợp đó và có thể che giấu lỗi chuyển đổi.

## 19. Những sai lầm thường gặp

**Không định nghĩa đơn vị offset.** Một thành phần dùng byte, thành phần khác dùng UTF-16 code unit. Kết quả là lỗi lệch cột hoặc span cắt sai văn bản.

**Trộn chỉ số bắt đầu từ 0 và bắt đầu từ 1.** API nội bộ và giao diện người dùng có thể dùng quy ước khác nhau. Chuyển đổi cần được thực hiện tại ranh giới và có kiểm thử.

**Coi cột là số ký tự hiển thị.** Unicode, tab và font có độ rộng khác nhau khiến visual column không đồng nhất với offset.

**Xử lý CRLF như hai dòng.** Nếu tăng số dòng cả ở `\r` và `\n`, mọi vị trí sau đó có thể bị lệch.

**Không giữ source identity.** Offset 100 trong `a.dsl` không có ý nghĩa tương đương offset 100 trong `b.dsl`.

**Dùng span của nút cha cho mọi lỗi.** Điều này khiến editor tô sáng cả câu lệnh dù lỗi chỉ nằm ở một tên thuộc tính hoặc một toán tử.

**Bỏ vị trí khi tạo AST.** Bộ kiểm tra ngữ nghĩa và interpreter không thể đưa người dùng trở lại đoạn nguồn có vấn đề.

**Gán vị trí giả cho nút sinh tự động.** Nút không có nguồn trực tiếp cần giữ origin hoặc vị trí gọi/định nghĩa, không nên trỏ tùy tiện đến đầu tệp.

**Giữ diagnostic của phiên bản tài liệu cũ.** Sau khi người dùng chỉnh sửa, span cũ có thể trỏ sang đoạn hoàn toàn khác.

**Không kiểm thử Unicode.** Chương trình chỉ chạy đúng với ASCII có thể thất bại khi người dùng viết tên tiếng Việt hoặc ký tự ngoài BMP.

## 20. Quy trình triển khai vị trí nguồn trong DSL

Một quy trình triển khai thực tế có thể gồm:

1. **Chọn mô hình nguồn:** định nghĩa `SourceId`, `SourceText`, `SourcePosition` và `SourceSpan`.
2. **Chọn hệ tọa độ nội bộ:** quy định offset theo byte, code point hoặc UTF-16 code unit; xác định rõ điểm bắt đầu và điểm kết thúc.
3. **Xác định encoding và newline:** quy định cách giải mã, BOM, LF/CRLF/CR và chính sách Unicode.
4. **Xây dựng bảng dòng:** lưu offset bắt đầu dòng và cơ chế chuyển đổi sang line/column.
5. **Gắn span cho token:** lexer ghi nhận vị trí trước và sau mỗi token.
6. **Lan truyền span vào CST/AST:** parser gắn span cho nút cha và giữ span riêng cho nút con.
7. **Giữ source origin:** xác định cách biểu diễn macro, include, cú pháp rút gọn và mã sinh.
8. **Chuẩn hóa diagnostic:** dùng cấu trúc chung gồm severity, code, message, primary span và related spans.
9. **Tích hợp editor:** chuyển đổi chính xác sang giao thức hoặc API vị trí của IDE.
10. **Kiểm thử ranh giới:** kiểm tra Unicode, newline, EOF, nhiều tệp, chỉnh sửa gia tăng và code generation.
11. **Tối ưu có kiểm soát:** giảm bộ nhớ hoặc tăng tốc tra cứu nhưng giữ đủ thông tin phục vụ chẩn đoán.

## 21. Mẫu mô hình dữ liệu vị trí nguồn

Một mô hình khái niệm có thể gồm các kiểu sau:

~~~text
SourceDocument
  id: SourceId
  uri: URI
  version: DocumentVersion
  encoding: Encoding
  text: SourceText
  lineStarts: List<Offset>

SourcePosition
  sourceId: SourceId
  offset: Offset

SourceSpan
  sourceId: SourceId
  startOffset: Offset
  endOffset: Offset

SourceOrigin
  primarySpan: SourceSpan?
  relatedOrigins: List<SourceOrigin>
  kind: Direct | MacroCall | MacroDefinition | Generated | Included

Diagnostic
  severity: Severity
  code: DiagnosticCode
  message: String
  primarySpan: SourceSpan?
  relatedSpans: List<RelatedSpan>
  fixes: List<CodeFix>
~~~

Đây là mô hình khái niệm, không phải một API bắt buộc. Dấu `?` biểu thị trường có thể không có giá trị. Một số diagnostic cấp hệ thống có thể không gắn với một span cụ thể, ví dụ lỗi không đọc được tệp hoặc lỗi cấu hình môi trường.

Khi triển khai, cần tránh để một `SourceSpan` tham chiếu đến phiên bản tài liệu khác với phiên bản mà diagnostic được tạo ra. Có thể lưu version trong `SourceDocument` và gắn diagnostic với version đó, hoặc tạo ID bất biến cho mỗi snapshot nguồn.

## 22. Vị trí nguồn trong các công cụ và giao thức

Các hệ sinh thái khác nhau có quy ước vị trí riêng. Khi tích hợp, cần đọc hợp đồng của công cụ thay vì giả định tất cả đều dùng cùng đơn vị.

| Môi trường | Dạng vị trí thường gặp | Điểm cần chú ý |
|---|---|---|
| Compiler/parser tự xây dựng | Byte hoặc character offset; có thể có line/column. | Ghi rõ đơn vị và quy ước span. |
| Java `String` | Chỉ số theo UTF-16 code unit. | Cần lưu ý surrogate pair khi so với code point hoặc UTF-8. |
| JavaScript string | Chỉ số theo UTF-16 code unit. | Không đồng nhất với số code point hoặc byte UTF-8. |
| Language Server Protocol | `line` và `character`, bắt đầu từ 0; `character` theo UTF-16 code unit trong quy ước cơ bản. | Cần chuyển đổi từ hệ tọa độ parser nếu khác. |
| Parser dựa trên UTF-8 | Thường trả byte offset. | Cần bảng ánh xạ sang editor hoặc chuỗi UTF-16. |
| Công cụ đồ họa | ID phần tử, tọa độ, vùng chọn hoặc vị trí trong tài liệu. | Phân biệt tọa độ hiển thị với định danh và cấu trúc ngữ nghĩa. |

Nếu DSL hỗ trợ nhiều editor hoặc nhiều client, nên đặt một mô hình vị trí nội bộ ổn định và viết adapter cho từng giao thức. Không nên để logic ngôn ngữ phụ thuộc trực tiếp vào một định dạng vị trí của giao diện cụ thể.

## 23. Kết quả cần có sau khi thiết kế vị trí nguồn

Một thiết kế vị trí nguồn đầy đủ thường tạo ra:

1. **Quy ước tọa độ:** định nghĩa offset, span, base của dòng/cột, đơn vị cột và newline.
2. **Mô hình nguồn:** định danh tài liệu, văn bản, encoding, phiên bản và bảng dòng.
3. **Thông tin token và AST:** cách gắn span cho token, CST, AST và nút tổng hợp.
4. **Cơ chế origin:** cách truy vết macro, include, desugaring và mã được sinh.
5. **Mô hình diagnostic:** mã lỗi, mức độ, thông điệp, vị trí chính, vị trí liên quan và gợi ý sửa.
6. **Bộ chuyển đổi vị trí:** ánh xạ giữa byte, code point, UTF-16, line/column và giao thức IDE.
7. **Bộ kiểm thử:** trường hợp ASCII, Unicode, tab, CRLF, EOF, nhiều tệp, chỉnh sửa và source map.

Vị trí nguồn là cầu nối giữa cấu trúc nội bộ của DSL và văn bản hoặc giao diện mà người dùng nhìn thấy. Khi định nghĩa rõ nguồn, đơn vị tọa độ, span, phiên bản và nguồn gốc của cấu trúc, các thành phần lexer, parser, AST, bộ kiểm tra và IDE có thể cùng chỉ đến một vị trí nhất quán. Điều đó giúp thông báo lỗi chính xác, hỗ trợ chỉnh sửa tốt và làm cho DSL dễ sử dụng, gỡ lỗi và bảo trì hơn.
