# Escape nối dòng: dùng dấu `\` để bỏ ký tự xuống dòng trong Java text block (Java 15+)

## 1. Vấn đề: muốn xuống dòng trong mã nguồn, nhưng không muốn xuống dòng trong `String`

Một **text block** cho phép viết chuỗi nhiều dòng một cách dễ đọc:

```java
String ordinary = """
        alpha
        beta
        """;
```

Giá trị của `ordinary` là `"alpha\nbeta\n"`: có một ký tự xuống dòng giữa `alpha` và `beta`, đồng thời có một ký tự xuống dòng cuối. Điều này đúng khi muốn biểu diễn nhiều dòng thật. Nhưng có trường hợp ta chỉ muốn **ngắt dòng trong *mã nguồn*** để dễ đọc, trong khi **giá trị `String` phải liên tục**, ví dụ một chuỗi lệnh dài, một thông điệp một dòng hoặc một đoạn query dài.

Java hỗ trợ **escape nối dòng** (*line continuation escape*): đặt **một dấu backslash `\` ngay trước ký tự kết thúc dòng nguồn**. Cặp **backslash + line terminator** được xử lý thành **không có ký tự nào** trong giá trị `String`:

```java
String joined = """
        alpha\
        beta
        """;
```

Giá trị của `joined` là `"alphabeta\n"`, **không có `\n` giữa hai từ**. Dòng `beta` vẫn còn `\n` cuối vì dấu đóng text block được đặt trên một dòng riêng.

Nếu muốn một khoảng trắng giữa hai từ, chủ động đặt khoảng trắng **trước dấu backslash**:

```java
String withSpace = """
        alpha \
        beta
        """;
```

Giá trị là `"alpha beta\n"`. Đây là khác biệt quan trọng: **escape nối dòng không tự tạo dấu cách**. Nó chỉ bỏ xuống dòng tại đúng ranh giới đặt escape. Khoảng trắng có hay không phụ thuộc nội dung hai bên và cách xử lý whitespace.

> **Phiên bản đang áp dụng:** Text blocks đã được chuẩn hóa ở **Java 15**, sau giai đoạn preview Java 13 và 14 ([JEP 378](https://openjdk.org/jeps/378)). Escape nối dòng `\` + kết thúc dòng nguồn là cú pháp chính thức trong Java 15+; không cần bật `--enable-preview`. Ví dụ trong bài sử dụng Java 17+ và vẫn phù hợp với các JDK hiện đại.

## 2. Cú pháp chính xác của escape nối dòng

Trong văn bản đặc tả Java, escape được ký hiệu là:

```text
\ LineTerminator
```

Đây là **mô tả ngữ pháp**, không phải chuỗi gồm dấu backslash, dấu cách và chữ `LineTerminator`. Nghĩa thực tế là: một dấu `\` **ngay sát** kết thúc dòng vật lý trong phần thân của text block. Kết thúc dòng có thể là LF, CR hoặc CRLF trong tệp nguồn; trước khi xử lý escape, text block chuẩn hóa kết thúc dòng theo quy tắc ngôn ngữ.

**Ba ví dụ khác nhau:**

```java
String a = """
        A
        B""";              // "A\nB"

String b = """
        A\
        B""";              // "AB"

String c = """
        A \
        B""";              // "A B"
```

Những comment trên mô tả **giá trị `String`**, không phải nội dung có dấu nháy kép hiển thị trong console. Ký tự `\` cuối dòng của `b`/`c` là một phần cú pháp escape; nó **không nằm lại trong dữ liệu**.

### Các điều kiện cần để escape hoạt động

1. Escape phải nằm **trong nội dung text block**. Text block mở bằng `"""` và dấu mở phải có ký tự xuống dòng trước nội dung.
2. Dấu `\` của escape nối dòng phải đứng **ngay trước kết thúc dòng nguồn**. Nếu editor chèn dấu cách hoặc tab **sau** backslash, không còn là escape nối dòng hợp lệ và thường dẫn đến lỗi biên dịch.
3. **Một cặp escape bỏ một lần xuống dòng**. Không hiểu nó là thao tác xóa mọi `\n` còn lại của text block.
4. Nếu muốn nối hai đoạn **không có khoảng trắng**, đặt `\` ngay sau ký tự cuối của dòng trước. Nếu muốn khoảng trắng, đặt dấu cách có chủ đích trước escape hoặc dùng `\s` khi cần bảo toàn chính xác.
5. Không dùng `\\` rồi kỳ vọng nó có cùng tác dụng. `\\` là **escape cho một backslash trong dữ liệu**; nó không có ý nghĩa bỏ xuống dòng.
6. Phần thụt lề của text block vẫn trải qua quy tắc loại bỏ *incidental indentation*; không kết luận rằng dấu cách dùng để căn mã nguồn ở đầu dòng sau luôn trở thành dấu cách của `String`.

## 3. Cơ chế xử lý: vì sao `\` làm biến mất newline?

Một text block được Java xử lý theo thứ tự khái quát:

1. **Chuẩn hóa kết thúc dòng:** các kiểu kết thúc dòng trong source được biểu diễn thành LF (`\n`).
2. **Xử lý khoảng trắng vô tình:** loại bỏ phần thụt lề chung và trailing whitespace theo quy tắc text block, tương tự cơ chế của `String.stripIndent()`.
3. **Dịch các escape:** xử lý escape như `\n`, `\t`, `\s`, `\\` và escape `\` ngay trước kết thúc dòng, tương tự `String.translateEscapes()`.

Trong **bước thứ ba**, escape `\` + line terminator được thay bằng **chuỗi rỗng**. Vì vậy, không có `\n`, cũng không có một ký tự `\` nào được thêm vào giá trị.

Xem chuỗi:

```java
String message = """
        Xin chào, \
        bạn đang học Java.
        """;
```

- Dấu cách sau dấu phẩy ở cuối dòng trước **được giữ** vì có escape `\` sau nó.
- Dấu `\` nối với ký tự xuống dòng **không tạo ký tự trong kết quả**.
- Mức thụt lề chung trước `bạn` bị loại bỏ theo quy tắc text block.
- Dấu đóng trên dòng riêng vẫn giữ `\n` sau dấu chấm cuối cùng.

Giá trị cuối cùng là `"Xin chào, bạn đang học Java.\n"`, không phải `"Xin chào, \nbạn đang học Java.\n"` và cũng không phải `"Xin chào,bạn đang học Java.\n"`.

**Lưu ý về source file:** Một editor có thể lưu dòng nguồn theo CRLF trên Windows, LF trên Linux hoặc macOS. Việc chuẩn hóa rồi dịch escape giúp quy tắc nối dòng nhất quán. Tránh dựa vào loại line ending của máy phát triển để suy đoán chuỗi runtime.

## 4. Ví dụ Java 17+ hoàn chỉnh và kết quả đã kiểm thử

Tạo tệp **`LineContinuationDemo.java`**:

```java
public class LineContinuationDemo {
    static void expect(String actual, String expected, String label) {
        if (!actual.equals(expected)) {
            throw new AssertionError(label + ": "
                    + actual.replace("\n", "\\n"));
        }
    }

    public static void main(String[] args) {
        // Không escape: giữ newline thật giữa các dòng.
        String normal = """
                alpha
                beta
                """;

        // Escape nối dòng: bỏ newline giữa alpha và beta.
        String joined = """
                alpha\
                beta
                """;

        // Giữ một dấu cách trước escape.
        String joinedWithSpace = """
                alpha \
                beta
                """;

        // Chuỗi dài trong source, nhưng một dòng trong kết quả.
        String request = """
                GET /rooms?\
                city=HCM&\
                available=true""";

        // Hai cách kiểm soát newline cuối.
        String withFinalNewline = """
                A\
                B
                """;
        String withoutFinalNewline = """
                A\
                B""";

        // \s bảo toàn hai dấu cách trước vị trí nối.
        String preservedSpaces = """
                X\s\s\
                Y""";

        // \n là escape sinh newline, đối lập với nối dòng.
        String explicitNewline = """
                alpha\nbeta""";

        // \\ tạo một backslash thật, không phải nối dòng.
        String literalBackslash = """
                C:\\temp\\notes.txt""";

        // Kết hợp: nối dòng đầu cho dễ đọc SQL.
        String sql = """
                SELECT id, \
                title
                FROM lessons
                WHERE active = ?
                """;

        expect(normal, "alpha\nbeta\n", "normal");
        expect(joined, "alphabeta\n", "joined");
        expect(joinedWithSpace, "alpha beta\n", "joinedWithSpace");
        expect(request, "GET /rooms?city=HCM&available=true", "request");
        expect(withFinalNewline, "AB\n", "withFinalNewline");
        expect(withoutFinalNewline, "AB", "withoutFinalNewline");
        expect(preservedSpaces, "X  Y", "preservedSpaces");
        expect(explicitNewline, "alpha\nbeta", "explicitNewline");
        expect(literalBackslash, "C:\\temp\\notes.txt", "literalBackslash");
        expect(sql,
               "SELECT id, title\nFROM lessons\nWHERE active = ?\n",
               "sql");

        System.out.println("normal=" + normal.replace("\n", "\\n"));
        System.out.println("joined=" + joined.replace("\n", "\\n"));
        System.out.println("withSpace=" + joinedWithSpace.replace("\n", "\\n"));
        System.out.println("request=" + request);
        System.out.println("finalNewline=" + withFinalNewline.endsWith("\n"));
        System.out.println("inlineCloseNewline="
                + withoutFinalNewline.endsWith("\n"));
        System.out.println("spacesLength=" + preservedSpaces.length());
        System.out.println("explicitNewline="
                + explicitNewline.replace("\n", "\\n"));
        System.out.println("path=" + literalBackslash);
        System.out.println("sql=" + sql.replace("\n", "\\n"));
    }
}
```

**Biên dịch và chạy:**

```bash
javac --release 17 -encoding UTF-8 LineContinuationDemo.java
java LineContinuationDemo
```

JDK 17+ hỗ trợ toàn bộ cú pháp được dùng. Không cần cờ preview. Phép `expect(...)` ném `AssertionError` nếu chuỗi thực không bằng chuỗi dự kiến, nên mã kiểm tra **giá trị thực**, không chỉ in ra màn hình.

**Standard output chính xác:**

```text
normal=alpha\nbeta\n
joined=alphabeta\n
withSpace=alpha beta\n
request=GET /rooms?city=HCM&available=true
finalNewline=true
inlineCloseNewline=false
spacesLength=4
explicitNewline=alpha\nbeta
path=C:\temp\notes.txt
sql=SELECT id, title\nFROM lessons\nWHERE active = ?\n
```

**Cách đọc output:** Trong những dòng có tên `normal`, `joined`, `withSpace`, `explicitNewline` và `sql`, chương trình dùng `replace("\n", "\\n")` để hiển thị **hai ký tự `\` và `n`** thay cho mỗi newline thật. Nhờ vậy, console phân biệt được ranh giới dòng mà không cần đoán từ hình thức xuống dòng.

### 4.1. `normal` và `joined`

- `normal` có giá trị `"alpha\nbeta\n"`. Hai dòng mã nguồn trở thành hai dòng dữ liệu.
- `joined` có giá trị `"alphabeta\n"`. Escape nối dòng bỏ đúng `\n` giữa `alpha` và `beta`, nhưng giữ `\n` cuối do cách đóng text block.
- `joinedWithSpace` có giá trị `"alpha beta\n"`; dấu cách được viết **trước** escape nên vẫn xuất hiện trong dữ liệu.

### 4.2. `request`: nhiều dòng source thành một dòng dữ liệu

```java
String request = """
        GET /rooms?\
        city=HCM&\
        available=true""";
```

Kết quả là `"GET /rooms?city=HCM&available=true"`. Có **hai** escape nối dòng, nên cả hai chỗ xuống dòng trong source đều không tạo newline trong `String`. Dấu đóng ngay sau `true` giúp không có newline cuối.

Đây chỉ là ví dụ **cú pháp một chuỗi văn bản**, không phải URL builder an toàn. Với query chứa dữ liệu người dùng, cần URL encoding và API thích hợp; không ghép trực tiếp input không tin cậy chỉ vì text block cho phép nối dòng.

### 4.3. `withFinalNewline` và `withoutFinalNewline`

Hai giá trị cùng bắt đầu bằng `"AB"` nhưng khác kết thúc:

```java
String withFinalNewline = """
        A\
        B
        """;

String withoutFinalNewline = """
        A\
        B""";
```

- Bản đầu là `"AB\n"`.
- Bản sau là `"AB"`.

**Vị trí dấu đóng** và những escape được đặt trước nó đều quan trọng. Muốn loại bỏ newline cuối **mà vẫn giữ dấu đóng trên một dòng riêng**, có thể đặt `\` ngay cuối dòng dữ liệu cuối:

```java
String noEndNewline = """
        A\
        B\
        """;
```

Giá trị là `"AB"`. Escape ở dòng `B` đã bỏ newline dẫn đến dòng dấu đóng. Cách này giúp giữ dấu đóng ở một vị trí dễ căn lề nhưng không thêm ký tự `\n` cuối. Đây là **mẫu hợp lệ trong Java 15+**, và không cần gọi `strip()`/`stripTrailing()` để thay đổi các ký tự khác của dữ liệu.

### 4.4. Khoảng trắng đặc biệt: `\s` và dấu cách trước `\`

Trong `preservedSpaces`:

```java
String preservedSpaces = """
        X\s\s\
        Y""";
```

`\s` chuyển thành một dấu cách. Hai `\s` cộng lại tạo hai dấu cách. Escape nối dòng đứng ngay sau hai `\s` bỏ newline, nên giá trị là `"X  Y"`, có độ dài **4**.

`\s` hữu ích khi cần biểu diễn chính xác dấu cách cuối một đoạn, vì Java xử lý escape **sau** khi loại bỏ trailing incidental whitespace. Không nên dùng các dấu cách “vô hình” ở cuối source rồi kỳ vọng editor hoặc code formatter luôn giữ lại.

### 4.5. `explicitNewline`, `literalBackslash` và `sql`

- `explicitNewline` sử dụng `\n`, nên **thêm** newline vào chuỗi; nó có ý nghĩa đối lập với `\` + line terminator, vốn **xóa** newline tại ranh giới đó.
- `literalBackslash` sử dụng `\\` để tạo một ký tự backslash trong đường dẫn `C:\temp\notes.txt`. Không có escape nối dòng ở đây.
- `sql` nối dòng nguồn `SELECT id,` với `title` bằng escape, đồng thời giữ newline giữa các câu SQL khác. `sql` vẫn có `\n` cuối vì dấu đóng trên dòng riêng.

## 5. Phân biệt bốn cơ chế dễ nhầm

| Trong mã Java | Giá trị `String` nhận được | Mục đích |
| --- | --- | --- |
| Xuống dòng trực tiếp trong text block, **không có `\`** | Chứa `\n` | Viết văn bản thật sự nhiều dòng |
| Dãy `\n` | Chứa **một** newline ở đúng vị trí escape | Chủ động tạo ký tự xuống dòng |
| Dấu `\` **ngay trước kết thúc dòng nguồn** | **Không chứa ký tự** cho cặp escape này | Chia source thành nhiều dòng mà không chia dữ liệu |
| Dãy `\\` | Chứa một backslash `\` | Biểu diễn đường dẫn, regex hoặc nội dung có backslash |
| Dãy `\s` | Chứa một dấu cách ASCII | Giữ khoảng trắng một cách tường minh |

Đặc biệt, **`\n` là dấu backslash theo sau bởi chữ `n`**, không phải dấu backslash trước kết thúc dòng nguồn. Chúng là **hai escape khác nhau**:

```java
String keepBreak = """
        A\nB""";       // Giá trị "A\nB".

String suppressBreak = """
        A\
        B""";         // Giá trị "AB".
```

Chỉ nhìn thấy “có dấu `\`” không đủ để đoán kết quả. Cần nhìn **ký tự đứng ngay sau backslash**.

### Escape nối dòng có dùng trong literal `"..."` thông thường không?

**Không.** Theo Java Language Specification hiện hành, `\` + line terminator là escape được phép xuất hiện trong **text block**; literal `"..."` và ký tự literal `'...'` không cho phép một line terminator vật lý xuất hiện bên trong, kể cả ở dạng escape đó.

Muốn chia một literal `String` truyền thống trên nhiều dòng mã nguồn, cách viết là nối các literal riêng:

```java
String oldStyle = "Một phần dài " +
        "và phần tiếp theo";
```

Trong Java 15+, nếu có lợi về khả năng đọc, một text block với escape nối dòng có thể diễn đạt cùng kết quả:

```java
String newStyle = """
        Một phần dài \
        và phần tiếp theo""";
```

Hai cách tạo `"Một phần dài và phần tiếp theo"`. Text block **không phải** cơ chế cho phép viết một literal `"..."` truyền thống xuyên qua nhiều dòng nguồn.

## 6. Thụt lề và khoảng trắng khi nối dòng

Text block không bê nguyên mọi khoảng trắng từ file mã nguồn. Trong Java, các line terminator được chuẩn hóa, **incidental indentation** được loại bỏ, rồi các escape mới được giải mã.

Ví dụ:

```java
static String buildLabel() {
    return """
            ID:\
            BK-42""";
}
```

Giá trị là `"ID:BK-42"`, không có dấu cách do căn lề trước `BK-42`. Các khoảng trắng đầu dòng phục vụ bố cục source đã bị loại bỏ.

Nếu muốn thành `"ID: BK-42"`:

```java
static String buildLabel() {
    return """
            ID: \
            BK-42""";
}
```

Điểm khác biệt là **dấu cách sau dấu hai chấm nhưng trước `\`**, không phải số lượng space được dùng để căn `BK-42` trong source.

### Những thay đổi định dạng có thể làm đổi chuỗi

1. **Dời dấu đóng `"""`:** có thể thay đổi mức indentation bị loại bỏ và việc có newline cuối.
2. **Thêm/xóa khoảng trắng ngay trước backslash:** có thể thay đổi dữ liệu do escape không tự thêm dấu cách.
3. **Thêm khoảng trắng sau backslash:** làm backslash **không còn đứng ngay trước line terminator**, có thể gây lỗi escape/biên dịch; cần tránh formatter tự động làm điều này.
4. **Chuyển từ CRLF sang LF trong source:** không làm thay đổi ý nghĩa escape nối dòng đúng cú pháp; line terminator được chuẩn hóa trước bước giải mã.
5. **Đưa một dòng trống giữa hai đoạn:** escape chỉ bỏ một line terminator, nên các newline khác có thể vẫn còn.
6. **Trộn tab và space:** thụt lề hiển thị trong editor có thể khác số ký tự thực tế; nên thống nhất style và kiểm tra chuỗi nếu layout cần chính xác.

Ví dụ một dòng trống còn lại:

```java
String withBlank = """
        one\

        two""";
```

Giá trị là `"one\ntwo"`. Escape sau `one` bỏ **một** newline, nhưng dòng trống kế tiếp vẫn tạo ra newline. Nó không biến mọi đoạn liên tiếp thành một dòng duy nhất.

## 7. Khi nào nên dùng escape nối dòng?

**Nên dùng** khi ta muốn bố cục nguồn có nhiều dòng nhưng dữ liệu đích chỉ có một dòng ở những vị trí đã xác định:

- Một **câu mô tả dài** cần ngắt dòng source để review mà không đưa `\n` vào màn hình hay API.
- Một đoạn **query string** hoặc command text dài mà văn bản giá trị không cần newline (cần xử lý encoding và bảo mật riêng).
- Một câu **SQL** hoặc đoạn DSL dài, nếu một ranh giới newline cụ thể phải biến mất trong giá trị `String`. Chỉ dùng khi không làm thay đổi cú pháp dữ liệu đích.
- **Không muốn newline cuối** ở text block có dấu đóng trên dòng riêng.
- Một chuỗi vừa có **dòng thật** vừa có **dòng chỉ để định dạng mã nguồn**, trong đó ta đặt escape ở đúng ranh giới cần nối.

**Không cần dùng** khi nội dung vốn là nhiều dòng có ý nghĩa: email, CSV/TSV, bảng văn bản, nội dung HTML hoặc SQL thường cần giữ xuống dòng để dễ kiểm tra. Text block **không có `\` nối dòng** đã giải quyết phần lớn nhu cầu giảm `\n` thủ công.

**Tránh lạm dụng**: đặt `\` ở cuối hầu hết mọi dòng có thể làm giá trị runtime khó suy đoán. Nếu chỉ cần một chuỗi ngắn, literal `"..."` có thể dễ hiểu hơn; nếu có dữ liệu nhiều phần được xây dựng động, cân nhắc `StringBuilder`, `String.join` hoặc API chuyên dụng.

### Những điều escape này không làm

- **Không phải interpolation:** `"""` không tự thay biến hay format placeholder.
- **Không làm JSON/SQL/HTML hợp lệ:** Java chỉ xử lý text block như một `String`, không phân tích cú pháp định dạng nhúng.
- **Không bảo vệ SQL injection:** giá trị động nên bind qua `PreparedStatement`, không nối thẳng từ input không tin cậy.
- **Không tạo dòng mới:** muốn newline thật, không dùng escape nối dòng tại ranh giới đó, hoặc chèn `\n` tường minh.
- **Không xóa nội dung ngoài ranh giới:** không tương đương `replace("\n", "")`, vốn xóa tất cả newline trong cả chuỗi.

## 8. So sánh với `replace`, `strip` và các API xử lý chuỗi

Giả sử text block chứa hai đoạn:

```java
String input = """
        first
        second
        """;
```

Các kỹ thuật khác nhau có ý nghĩa khác nhau:

| Kỹ thuật | Tác động |
| --- | --- |
| Đặt `\` trước một line terminator nguồn | Bỏ **đúng ranh giới newline đó** ngay khi biên dịch literal |
| `input.replace("\n", "")` | Bỏ **mọi ký tự LF** của chuỗi runtime, kể cả newline cần giữ |
| `input.stripTrailing()` | Bỏ các ký tự whitespace cuối chuỗi theo định nghĩa API, **không chỉ** một newline |
| `input.strip()` | Bỏ cả leading và trailing whitespace, có thể làm đổi dữ liệu có ý nghĩa |
| `String.join(" ", parts)` | Ghép các phần theo delimiter xác định; thích hợp khi có một danh sách các thành phần |

**Vì sao cần phân biệt?** Nếu yêu cầu chỉ là “đừng có newline giữa `first` và `second`”, escape nối dòng thể hiện ý định trực tiếp ở điểm viết literal; `replace("\n", "")` có thể đồng thời làm mất newline cuối hoặc newline ở những chỗ khác không liên quan. Nếu yêu cầu chỉ bỏ newline cuối, đặt dấu đóng phù hợp hoặc dùng `\` cuối dòng thường chính xác hơn việc `stripTrailing()` xóa cả dấu cách cuối có ý nghĩa.

Cũng cần phân biệt **thời điểm**: escape của text block được xử lý khi Java biên dịch literal; `replace`/`strip` xử lý một giá trị `String` khi chương trình chạy. Với văn bản xây dựng động, escape của literal không có tác dụng đối với những dòng mới được thêm vào sau đó.

## 9. Kiểm thử để refactor mà không làm đổi dữ liệu

Khi chuyển chuỗi được nối bằng `+` sang text block + escape nối dòng, hãy xác nhận **giá trị cuối cùng**, không chỉ nhìn mã nguồn.

Ví dụ:

```java
// Đoạn minh họa đặt trong thân phương thức.
String oldValue = "Hello, " +
        "Java developer!";

String newValue = """
        Hello, \
        Java developer!""";

if (!oldValue.equals(newValue)) {
    throw new AssertionError("Chuỗi mới khác chuỗi cũ");
}
```

Hai chuỗi đều là `"Hello, Java developer!"`. Dấu cách được giữ trước escape. Nếu vô tình thay thành `Hello,\` mà không có dấu cách, kết quả là `"Hello,Java developer!"` và phép so sánh sẽ phát hiện thay đổi.

**Checklist test:**

1. **Kết quả cần nối:** `String.equals` với giá trị mong đợi, bao gồm dấu cách giữa hai phần.
2. **Số newline thật:** dùng `contains("\n")`, `lines()` hoặc hiển thị escape rõ ràng bằng `replace("\n", "\\n")`.
3. **Newline cuối:** dùng `endsWith("\n")`; đừng coi dấu đóng nằm ở dòng riêng là không đáng kể.
4. **Khoảng trắng:** kiểm tra `length` và nội dung từng dòng khi có dấu cách quan trọng.
5. **Đường dẫn/regex:** kiểm tra ký tự backslash thật, tránh nhầm `\\` với escape nối dòng.
6. **Các phiên bản biên dịch:** dùng `javac --release 17` (hoặc phiên bản phù hợp, ít nhất Java 15) để kiểm tra syntax text block chuẩn.
7. **Định dạng đích:** nếu dùng SQL/JSON, kiểm tra parse/execution với dữ liệu thử nghiệm và yêu cầu escaping/binding.
8. **Tương thích source formatter:** sau khi formatter chạy, compile và test lại nếu nó có thể sửa line ending/whitespace.
9. **Đọc test khi lỗi:** diễn đạt ký tự newline như `\\n` trong thông báo để biết newline nào đã bị bỏ, còn các newline nào vẫn còn.

## 10. Lỗi phổ biến

| Lỗi / nhầm lẫn | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ text block tự bỏ newline giữa các dòng | Chuỗi thật vẫn có `\n` | Đặt `\` ngay trước những kết thúc dòng cần nối |
| Dùng `\n` khi mục tiêu là bỏ newline | `\n` **tạo** newline | Dùng `\` + line terminator |
| Đặt hai ký tự `\\` trước xuống dòng | `\\` tạo backslash thật, không phải line continuation | Phân biệt `\\` với `\` cuối dòng |
| Gõ dấu cách sau backslash | Escape không còn ngay trước line terminator, có thể lỗi compile | Để backslash là ký tự cuối của dòng nguồn |
| Xóa space trước backslash | `alpha beta` trở thành `alphabeta` | Quyết định rõ khoảng trắng cần giữ |
| Tin indent dòng sau sẽ tạo dấu cách | Incidental indent có thể bị xóa | Viết space trước escape hoặc `\s` |
| Không kiểm tra dấu đóng | Có thể thừa/thiếu newline cuối | Đóng cùng dòng cuối, hoặc dùng escape cuối dòng |
| Cho rằng một escape bỏ mọi dòng trống | Chỉ một line terminator bị bỏ | Kiểm tra từng ranh giới; giữ các newline có ý nghĩa |
| Dùng `replace("\n", "")` khi chỉ muốn nối một ranh giới | Có thể xóa cả newline cần thiết | Dùng escape đúng vị trí |
| Viết `\` + kết thúc dòng trong `"..."` thường | Không hợp lệ trong string literal thông thường | Dùng text block hoặc nối nhiều literal |
| Nghĩ text block là raw string | Backslash vẫn kích hoạt escape Java | Dùng `\\` cho backslash thật |
| Không test ký tự thực | Khó phát hiện mất space/newline | Dùng `String.equals` và in `\\n` khi debug |

## 11. Bài tập ngắn có đáp án

### Bài 1. Đoán giá trị

```java
String s = """
        Java\
        17""";
```

**Đáp án:** `"Java17"`. Escape nối dòng không tự thêm space.

### Bài 2. Giữ một dấu cách

```java
String s = """
        Java \
        17""";
```

**Đáp án:** `"Java 17"`. Dấu cách nằm ngay trước backslash được giữ.

### Bài 3. Phân biệt newline cuối

```java
String a = """
        A\
        B
        """;
String b = """
        A\
        B\
        """;
```

**Đáp án:** `a` là `"AB\n"`, còn `b` là `"AB"`. Dấu `\` sau `B` xóa newline trước dòng dấu đóng.

### Bài 4. Dấu `\n` và escape nối dòng khác nhau ra sao?

**Đáp án:** `\n` là hai ký tự trong source được Java dịch thành **một newline trong chuỗi**. Dấu `\` ngay trước kết thúc dòng source được dịch thành **không ký tự**, nên **bỏ** newline nguồn đó.

### Bài 5. Có được dùng escape này trong literal `"abc..."` thông thường không?

**Đáp án:** Không. String literal truyền thống không được chứa kết thúc dòng vật lý; muốn trải source qua nhiều dòng thì nối các literal hoặc dùng text block của Java 15+.

### Bài 6. Lời gọi `stripTrailing()` có phải cách hoàn toàn tương đương `\` bỏ newline cuối không?

**Đáp án:** Không. `stripTrailing()` xóa mọi trailing whitespace theo quy tắc của nó, có thể gồm nhiều space, tab và newline. Escape nối dòng chỉ loại bỏ đúng cặp escape/backslash + line terminator đã đặt.

## 12. Tài liệu chính thức

- [OpenJDK — JEP 378: Text Blocks](https://openjdk.org/jeps/378): text blocks là cú pháp chính thức của Java 15+, bao gồm escape nối dòng và `\s`.
- [Oracle — Programmer's Guide to Text Blocks (Java 17)](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html): phần *New Escape Sequences* giải thích escape `\` + line terminator, khoảng trắng và bố cục.
- [Java Language Specification, `3.10.6 — Text Blocks](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6): quy tắc chuẩn hóa line ending, loại bỏ indentation và dịch escape.
- [Java Language Specification, `3.10.7 — Escape Sequences](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.7): escape nối dòng có **không ký tự** trong kết quả, và chỉ hợp lệ trong text block.

**Ghi nhớ:** `\` ngay trước xuống dòng trong **text block Java 15+** là cách có chủ đích để **xuống dòng trong mã nguồn nhưng không thêm newline vào `String`**. Nó không tự tạo dấu cách và không bỏ mọi newline; phải kiểm tra indentation, khoảng trắng trước backslash, dấu đóng cuối và giá trị chuỗi thực tế.
