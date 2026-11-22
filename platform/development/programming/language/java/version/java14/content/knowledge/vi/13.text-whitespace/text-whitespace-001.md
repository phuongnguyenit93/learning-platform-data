# Chuẩn hóa ký tự xuống dòng trong text block (Java)

> **Phạm vi:** Bài thuộc **Java 14 → Khoảng trắng văn bản**, nhưng chỉ trình bày quy tắc còn áp dụng với Java hiện hành. Text block từng được thử nghiệm ở Java 13/14 và đã trở thành tính năng **chính thức từ Java 15** (JEP 378). Ví dụ dùng **Java 17+** và **không cần `--enable-preview`**. Trọng tâm là **chuẩn hóa CR/CRLF thành LF trong nội dung text block**, thứ tự xử lý của trình biên dịch, tương tác với escape sequences và cách kiểm tra byte/ký tự thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt các ký tự kết thúc dòng **LF**, **CR** và cặp **CRLF** theo Java Language Specification (JLS).
2. Giải thích vì sao nội dung text block có line ending LF ở thời điểm chạy ngay cả khi file `.java` được lưu theo kiểu CRLF của Windows hoặc chỉ CR.
3. Nêu đúng **ba phép biến đổi theo thứ tự** mà compiler áp dụng với text block: **normalize line terminators → strip incidental white space → interpret escape sequences**.
4. Hiểu tại sao `\r` escape nằm trong text block vẫn có thể tạo ra ký tự CR ở runtime dù các xuống dòng vật lý đã được chuẩn hóa về LF.
5. Xác định lúc nào text block **có hoặc không có LF cuối chuỗi** từ vị trí đóng `"""`; dùng ký tự `\` nối dòng khi muốn loại bỏ newline.
6. Viết chương trình kiểm tra chính xác các ký tự, tránh phụ thuộc cách terminal hiển thị hoặc line ending mặc định của hệ điều hành.
7. Xử lý đúng dữ liệu cần CRLF (ví dụ một định dạng giao thức) và dữ liệu cần LF, mà không nhầm chuẩn hóa **khi biên dịch** với việc chuẩn hóa **khi ghi file hoặc truyền mạng**.

## 2. Ba dạng kết thúc dòng cần phân biệt

Trong mã nguồn Java, JLS `3.4 định nghĩa line terminator là một trong ba dạng sau:

| Tên | Ký tự | Giá trị Unicode/ASCII | Dạng escape trong Java String | Thường gặp |
| --- | --- | --- | --- | --- |
| **LF** (line feed) | Một ký tự xuống dòng | `U+000A`, hex `0A` | `"\n"` | Nhiều file trên Unix/Linux/macOS hiện đại |
| **CR** (carriage return) | Một ký tự trở về đầu dòng | `U+000D`, hex `0D` | `"\r"` | Một số file/định dạng truyền thống |
| **CRLF** | Hai ký tự liền nhau: CR rồi LF | `U+000D U+000A`, hex `0D 0A` | `"\r\n"` | Các file và giao thức dùng quy ước CRLF |

Chú ý **CRLF gồm hai ký tự** ở cấp `String`/byte, nhưng được JLS nhận diện là **một line terminator** khi phân tích mã nguồn. Trong một `String` thông thường:

- `"A\nB"` chứa một LF giữa A và B.
- `"A\rB"` chứa một CR giữa A và B.
- `"A\r\nB"` chứa hai ký tự điều khiển liên tiếp, CR rồi LF.

**Không có quy tắc rằng mọi `String` trong Java tự chuyển CRLF thành LF.** Việc chuẩn hóa đang học là phép biến đổi dành riêng cho **nội dung một text block** tại thời điểm biên dịch. Chuỗi thông thường, dữ liệu đọc từ file, dữ liệu nhận từ mạng hay chuỗi được nối ở runtime có thể chứa CR, LF, CRLF tùy nguồn.

JLS chỉ dùng **ASCII CR và LF** trong quy tắc chuẩn hóa này. Các ký tự Unicode khác, chẳng hạn **LINE SEPARATOR U+2028** hoặc **PARAGRAPH SEPARATOR U+2029**, không tự được thay bằng LF bởi quy tắc chuẩn hóa CR/CRLF của text block.

## 3. Text block là một `String` có bước xử lý riêng

Một text block có mở và đóng bằng ba dấu nháy kép:

```java
String message = """
        First
        Second
        """;
```

Đây là một **biểu thức kiểu `String`**, không phải collection of lines hay một kiểu chuỗi mới. Theo JLS `3.10.6, delimiter mở là:

- Ba ký tự `"""`;
- Có thể tiếp theo bởi một lượng khoảng trắng hợp lệ;
- **Bắt buộc kết thúc bằng một line terminator** trước khi phần nội dung bắt đầu.

Do đó:

```java
// ĐÚNG: sau delimiter mở là newline.
String correct = """
        Hello
        """;
```

Trái lại:

```java
// CỐ Ý SAI: delimiter mở không theo sau bởi line terminator.
String incorrect = """Hello""";
```

Lệnh sai không phải vì `"Hello"` không được làm String mà vì cú pháp **text block opening delimiter** yêu cầu một line terminator.

**Newline ngay sau delimiter mở chỉ là một phần của delimiter và không được đưa vào đầu giá trị String.** Giá trị `correct` là `"Hello\n"` chứ không phải `"\nHello\n"`, với cách viết delimiter đóng nằm trên một dòng riêng như ví dụ.

## 4. Quy tắc quan trọng nhất: ba phép biến đổi theo đúng thứ tự

JLS `3.10.6 quy định rằng nội dung text block không được lấy nguyên xi từ các ký tự ở giữa hai delimiter. Compiler áp dụng **ba biến đổi** với nội dung, theo đúng thứ tự sau:

### Bước 1 — Normalize line terminators thành LF

Đây là trọng tâm bài:

| Line terminator trong **source text block** | Thay bằng trong giá trị text block |
| --- | --- |
| LF (`U+000A`) | LF (`U+000A`) |
| CRLF (`U+000D U+000A`) | **Một LF** (`U+000A`) |
| CR (`U+000D`) | **Một LF** (`U+000A`) |

Ví dụ hai bản file Java có nội dung hiển thị giống nhau:

```text
Bản A (source lưu LF):
"""<LF>
alpha<LF>
beta<LF>
""" 

Bản B (source lưu CRLF):
"""<CR><LF>
alpha<CR><LF>
beta<CR><LF>
"""
```

Ký hiệu `<LF>` và `<CR>` trong sơ đồ là **nhãn mô tả ký tự**, không phải code Java. Nếu các phần khác như indentation bằng nhau, cả hai text block đều biểu diễn cùng giá trị String sau chuẩn hóa:

```java
"alpha\nbeta\n"
```

Tương tự, file dùng **chỉ CR** làm dấu xuống dòng cũng tạo ra LF ở vị trí đó trong giá trị text block. Mục tiêu là **không làm nội dung text block phụ thuộc kiểu line ending của file nguồn**.

**Giới hạn cần nhớ:** Phép này chỉ chuyển **line terminators vật lý thuộc nội dung text block**, không phải quét kết quả String sau khi các escape sequences đã được giải mã. Do đó một escape `\r` có thể tạo CR ở bước cuối mà không bị đổi lại thành LF.

### Bước 2 — Loại bỏ incidental white space

Sau khi chuẩn hóa line ending, compiler loại bỏ khoảng trắng thụt lề phụ trợ, theo ngữ nghĩa tương đương `String.stripIndent()`. Bước này:

- Tính khoảng trắng thụt lề chung để xóa một cách hợp lý;
- Giữ mức thụt lề **tương đối** giữa các dòng có nội dung;
- Loại bỏ khoảng trắng cuối dòng theo quy tắc `stripIndent`;
- Không làm mất các LF chỉ vì đang loại bỏ indentation.

Ví dụ:

```java
String document = """
        <root>
            <item>one</item>
        </root>
        """;
```

Giá trị tương đương:

```java
"<root>\n    <item>one</item>\n</root>\n"
```

Không phải:

```java
"        <root>\n            <item>one</item>\n        </root>\n"
```

Khi copy ví dụ từ bài học hoặc đổi vị trí delimiter đóng, mức indentation thực tế có thể ảnh hưởng kết quả, nhưng **quy tắc CRLF/CR → LF vẫn diễn ra trước**.

### Bước 3 — Interpret escape sequences

Cuối cùng, compiler diễn giải các escape sequences tương đương `String.translateEscapes()`. Vì bước này ở **sau** chuẩn hóa, những escape như `\r` hoặc `\n` có thể thêm các ký tự điều khiển mới:

- `\n` → LF;
- `\r` → CR;
- `\t` → tab;
- `\s` → một khoảng trắng `U+0020`;
- Một dấu `\` ngay trước **line terminator** → **line continuation**, loại bỏ kết thúc dòng đó khỏi giá trị String.

Thứ tự này giải thích hiện tượng tưởng như mâu thuẫn: **«Java chuẩn hóa newline trong text block về LF nhưng text block vẫn có thể chứa CR ở runtime»**. Không mâu thuẫn, vì CR đó được **escape `\r` tạo sau khi đã hoàn tất normalize**.

Tóm tắt:

```text
Source text block content (CR, LF hoặc CRLF)
          |
          v
(1) Normalize line terminators -> LF
          |
          v
(2) Remove incidental indentation/trailing space
          |
          v
(3) Interpret \n, \r, \s, \<line-terminator>, ...
          |
          v
String cuối cùng ở runtime
```

## 5. Ví dụ Java hoàn chỉnh: xem chính xác LF, CRLF, dấu cuối dòng và continuation

Lưu dưới tên **`TextBlockNewlinesDemo.java`**:

```java
public class TextBlockNewlinesDemo {
    static String visible(String text) {
        return text.replace("\r", "<CR>")
                   .replace("\n", "<LF>");
    }

    public static void main(String[] args) {
        String normal = """
                alpha
                beta
                """;

        String noFinalLf = """
                alpha
                beta""";

        // Escape \r được xử lý SAU normalize.
        String explicitCrLf = """
                alpha\r
                beta\r
                """;

        // Backslash nối hai dòng vật lý, không tạo LF giữa chúng.
        String joined = """
                alpha\
                beta
                """;

        // \n trong text block được diễn giải như một LF.
        String escapedLf = """
                alpha\nbeta
                """;

        // \s cố ý giữ một dấu cách cuối dòng.
        String withSpace = """
                alpha\s
                beta
                """;

        System.out.println("normal=" + visible(normal));
        System.out.println("normal-equals=" + normal.equals("alpha\nbeta\n"));
        System.out.println("normal-cr=" +
                normal.chars().filter(ch -> ch == '\r').count());
        System.out.println("normal-lf=" +
                normal.chars().filter(ch -> ch == '\n').count());

        System.out.println("no-final-lf=" + visible(noFinalLf));
        System.out.println("ends-with-lf=" + noFinalLf.endsWith("\n"));

        System.out.println("explicit-crlf=" + visible(explicitCrLf));
        System.out.println("crlf-equals=" +
                explicitCrLf.equals("alpha\r\nbeta\r\n"));

        System.out.println("joined=" + visible(joined));
        System.out.println("escaped-lf-equals=" + escapedLf.equals(normal));
        System.out.println("trailing-space=" +
                visible(withSpace).replace(" ", "<SP>"));
    }
}
```

Biên dịch/chạy với JDK 17+ hỗ trợ target Java 17:

```bash
javac --release 17 TextBlockNewlinesDemo.java
java TextBlockNewlinesDemo
```

**Stdout dự kiến chính xác:**

```text
normal=alpha<LF>beta<LF>
normal-equals=true
normal-cr=0
normal-lf=2
no-final-lf=alpha<LF>beta
ends-with-lf=false
explicit-crlf=alpha<CR><LF>beta<CR><LF>
crlf-equals=true
joined=alphabeta<LF>
escaped-lf-equals=true
trailing-space=alpha<SP><LF>beta<LF>
```

**Cách đọc từng kết quả:**

1. **`normal`** có hai LF: một giữa `alpha`/`beta` và một sau `beta` do dấu `"""` đóng nằm trên dòng riêng. Không có CR trong giá trị.
2. **`noFinalLf`** có delimiter đóng nằm ngay sau `beta`, nên phần nội dung không bao gồm một newline sau chữ `beta`.
3. **`explicitCrLf`** chứa escape `\r` ở cuối mỗi dòng nội dung trước LF vật lý. Compiler chuẩn hóa LF vật lý trước, rồi mới thay mỗi `\r` thành CR: kết quả có **CRLF**, được hiển thị `<CR><LF>`.
4. **`joined`** dùng dấu `\` ở cuối dòng `alpha` để loại bỏ line terminator nối dòng. Kết quả `alphabeta\n`, vẫn có LF cuối vì delimiter đóng ở dòng riêng.
5. **`escapedLf`** chèn LF bằng `\n` escape ngay trong một dòng nguồn, sau đó còn một LF ở cuối từ line terminator vật lý. Giá trị bằng với `normal`.
6. **`withSpace`** dùng `\s` để giữ một dấu space ở cuối dòng `alpha`; nếu chỉ gõ space thông thường ở cuối dòng text block, bước `stripIndent` có thể xóa nó.

Bản thân `System.out.println` cũng ghi thêm một line terminator theo hệ thống, nhưng các ký hiệu `<LF>`/`<CR>` được in bởi hàm `visible` là **văn bản mô tả**, không phải ký tự xuống dòng thật. Vì vậy ví dụ cho phép kiểm tra kết quả mà không phụ thuộc cách console xử lý CR/LF.

**Lưu ý khi sao chép:** Với `joined`, dấu `\` phải đứng **ngay trước newline vật lý**. Nếu thêm space sau dấu `\`, bạn không còn có đúng escape line-continuation mong muốn. Với các đoạn text block, giữ nguyên mức thụt lề tương đối và vị trí delimiter đóng.

## 6. Cách xác định newline cuối text block

Người mới hay nhầm rằng đóng `"""` luôn thêm LF. Thực tế, **chính vị trí line terminator trong nội dung nguồn** quyết định.

### 6.1. Delimiter đóng trên dòng riêng → thường có LF cuối

```java
String withFinalNewline = """
        A
        B
        """;
```

Giá trị:

```java
"A\nB\n"
```

Dòng vật lý chứa `B` kết thúc bằng newline trước delimiter đóng, nên newline đó trở thành **LF**.

### 6.2. Delimiter đóng ngay sau nội dung → không có LF cuối

```java
String withoutFinalNewline = """
        A
        B""";
```

Giá trị:

```java
"A\nB"
```

Ký tự ngay trước delimiter đóng là `B`, không phải line terminator, nên text block không tự tạo newline cuối.

### 6.3. Muốn điều chỉnh tường minh bằng escape hoặc API

Nếu mục tiêu là bảo đảm có LF cuối, bạn có thể khai báo delimiter đóng trên dòng riêng, hoặc dùng một biểu thức String khác để thêm LF theo hợp đồng dữ liệu:

```java
String result = """
        A
        B""";
result = result + "\n";
```

Nếu muốn bỏ LF cuối của một giá trị cụ thể, hãy kiểm tra chính xác dấu kết thúc mà bạn muốn xử lý, thay vì xóa whitespace bừa bãi:

```java
// Đoạn đặt trong method, chỉ bỏ ĐÚNG một LF cuối nếu có.
static String removeOneFinalLf(String input) {
    return input.endsWith("\n")
            ? input.substring(0, input.length() - 1)
            : input;
}
```

Khác với `trim()` hoặc `strip()`, đoạn này không xóa dấu cách đầu/cuối hay nhiều ký tự xuống dòng cùng lúc. Nếu protocol yêu cầu giữ nguyên mọi byte, tốt nhất là mô tả newline mong đợi từ lúc tạo String, thay vì xử lý heuristic sau đó.

## 7. Sự khác biệt giữa newline vật lý và escape `\n` / `\r`

Xét ba ví dụ minh họa **độc lập**, cùng trả `String`:

```java
String a = """
        one
        two
        """;

String b = """
        one\ntwo
        """;

String c = """
        one\r
        two\r
        """;
```

Kết quả:

| Biến | Ký tự giữa hai từ | Ký tự sau `two` | Biểu diễn String tương đương |
| --- | --- | --- | --- |
| `a` | LF vật lý đã được normalize | LF | `"one\ntwo\n"` |
| `b` | LF do `\n` escape tạo ở bước 3 | LF vật lý | `"one\ntwo\n"` |
| `c` | CR do `\r` escape + LF từ nguồn | CR rồi LF | `"one\r\ntwo\r\n"` |

Vì cả `a` lẫn `b` đều có LF ở đúng vị trí, `a.equals(b)` là `true`. Nhưng `a.equals(c)` là `false` vì `c` chứa thêm CR.

Một lỗi phân tích hay gặp: «Bước normalize đã thay toàn bộ CR thành LF, vậy làm sao có CRLF sau cùng?» — Vì **bước normalize chỉ đi trước escape processing**. `\r` lúc đầu là hai ký tự nguồn `\` và `r`, không phải một ký tự CR; đến bước 3 nó mới trở thành CR.

### 7.1. Đừng nhầm `\\n` với `\n`

Nếu muốn **hiển thị hai ký tự backslash + chữ n** trong dữ liệu (chẳng hạn viết một ví dụ code), bạn phải escape backslash:

```java
String literalSlashN = """
        one\\ntwo
        """;
```

Kết quả ở đầu là các ký tự `o n e \ n t w o`, **không** phải một LF giữa `one` và `two`. Giá trị tương đương:

```java
"one\\ntwo\n"
```

So với:

```java
String realLineBreak = """
        one\ntwo
        """;
```

Kết quả của `realLineBreak` là `"one\ntwo\n"`. Đây là khác biệt giữa escape được giải mã thành LF và chuỗi ký tự mô tả escape.

### 7.2. Unicode escape không phải escape thường

Cú pháp Java `\u000A` và `\u000D` thuộc **Unicode escapes ở quá trình đọc source**, xảy ra rất sớm theo JLS `3.3, trước khi compiler chia mã nguồn thành token; chúng **không** được xử lý ở bước `String.translateEscapes`. Vì thế, không dùng `\u000A`/`\u000D` như cách thay thế vô điều kiện cho `\n`/`\r` trong Java string literal. Chúng có thể tác động trực tiếp tới phân tách dòng/token của source.

Khi muốn chỉ định line ending trong **giá trị String ở runtime**, hãy dùng escape thông thường `\n` và `\r` hoặc API xử lý ký tự. Khi muốn kiểm thử compiler normalize **line ending vật lý của source**, hãy thay đổi kiểu xuống dòng của **file nguồn**, chứ không chèn bừa các Unicode escapes.

## 8. Chuẩn hóa không phụ thuộc hệ điều hành hay `System.lineSeparator()`

`System.lineSeparator()` cho biết chuỗi phân cách dòng mặc định theo hệ thống chạy chương trình. Nó **không** điều khiển phép normalize text block của compiler.

Dù bạn:

- Viết source bằng editor trên Windows với CRLF;
- Biên dịch ở máy Unix/Linux có source LF;
- Chạy chương trình trên hệ điều hành khác;
- Ghi giá trị String vào `byte[]` hoặc gửi qua API;

thì **nội dung text block theo quy tắc JLS vẫn dùng LF cho các line terminator vật lý ban đầu**, trừ khi chính source có escape tạo CR hoặc chương trình sửa String sau đó.

**Không thay đổi String thành CRLF chỉ vì phát hiện `System.lineSeparator()` là CRLF.** Chỉ chuyển khi nơi tiêu thụ dữ liệu thật sự quy định CRLF. Rất nhiều định dạng hiện đại, kể cả payload dạng JSON, có ngữ nghĩa riêng về newline và escape; hãy dựa vào đặc tả của format/protocol thay vì giả định từ OS.

### 8.1. Nếu một định dạng đòi chính xác CRLF

Một text block viết với newline vật lý sẽ có LF. Nếu muốn chuỗi CRLF, có các cách chủ động:

**Cách 1 — Escape `\r` ngay trước LF vật lý**:

```java
String crlf = """
        line1\r
        line2\r
        """;
```

Giá trị là `"line1\r\nline2\r\n"`.

**Cách 2 — Chuyển LF thành CRLF sau khi tạo String**, chỉ khi đầu vào được biết không chứa CR cần giữ riêng:

```java
String lf = """
        line1
        line2
        """;
String crlf = lf.replace("\n", "\r\n");
```

Giá trị cũng là `"line1\r\nline2\r\n"`.

**Cách 3 — Dùng ordinary string literal** khi line ending cụ thể là một phần giao thức:

```java
String crlf = "line1\r\nline2\r\n";
```

**Không áp dụng phép `replace("\n", "\r\n")` một cách mù quáng cho dữ liệu chưa biết nguồn.** Nếu dữ liệu đã có CRLF, phép thay sẽ tạo CRCRLF (ba ký tự) vì nó thay LF nhưng giữ nguyên CR cũ. Phải có ranh giới đầu vào rõ ràng hoặc chuẩn hóa có chủ đích trước.

## 9. Kiểm tra bằng byte: text block không tự đổi newline khi ghi file

Dùng `System.out.println` để nhìn một chuỗi là chưa đủ: terminal có thể trình bày CR, LF và CRLF tương tự nhau. Khi cần giao thức hoặc file có byte chính xác, hãy kiểm tra ký tự hoặc byte được ghi.

Lưu **`TextBlockFileDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class TextBlockFileDemo {
    public static void main(String[] args) throws Exception {
        String payload = """
                A
                B
                """;

        Path temp = Files.createTempFile("java-text-block-", ".txt");
        try {
            Files.writeString(temp, payload, StandardCharsets.UTF_8);
            byte[] bytes = Files.readAllBytes(temp);

            long cr = 0;
            long lf = 0;
            for (byte b : bytes) {
                if (b == 13) {
                    cr++;
                } else if (b == 10) {
                    lf++;
                }
            }

            System.out.println("bytes=" + bytes.length);
            System.out.println("cr=" + cr);
            System.out.println("lf=" + lf);
            System.out.println("content-equals=" +
                    Arrays.equals(bytes,
                            "A\nB\n".getBytes(StandardCharsets.UTF_8)));
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
```

```bash
javac --release 17 TextBlockFileDemo.java
java TextBlockFileDemo
```

**Stdout chính xác:**

```text
bytes=4
cr=0
lf=2
content-equals=true
```

**Giải thích:**

- `A` và `B` là ASCII, mỗi chữ một byte UTF-8; mỗi LF cũng là một byte `0A` → tổng cộng **4 byte**: `41 0A 42 0A`.
- Không có byte `0D` vì text block này không dùng escape `\r`.
- `Files.writeString(..., UTF_8)` ghi **nội dung String mà bạn truyền**, không tự đổi các LF ấy thành CRLF theo OS.
- Dùng file tạm và xóa trong `finally` để minh họa mà không yêu cầu một đường dẫn cứng cụ thể trên máy.
- `Arrays.equals` giúp xác nhận bytes thực tế giống biểu diễn UTF-8 mong đợi.

Bạn có thể kiểm chứng tương tự với `explicitCrLf` ở chương trình trước, sẽ có thêm byte `0D` trước mỗi byte `0A`. Khi làm việc với Unicode ngoài ASCII, vẫn nên chọn charset rõ ràng và kiểm tra **bytes**, không suy luận chỉ từ `String.length()`.

## 10. Cách tự xác minh file source LF và CRLF cho cùng kết quả

Nếu muốn kiểm chứng **trực tiếp** rằng định dạng xuống dòng của `.java` không ảnh hưởng giá trị text block:

1. Tạo `TextBlockNewlinesDemo.java` từ chương trình ở phần 5 bằng editor hỗ trợ chọn line ending.
2. Lưu một bản nguồn với **LF**. Biên dịch bằng `javac --release 17` rồi chạy; ghi kết quả hiển thị bằng `visible()`.
3. Đổi kiểu line ending của **file nguồn** thành **CRLF** trong editor, không sửa nội dung chữ, escape, indentation hoặc delimiter.
4. Biên dịch lại bằng cùng JDK và chạy lại.
5. Hai kết quả phải giống nhau về **giá trị các String** và số lượng CR/LF ở runtime. Nếu khác, kiểm tra xem editor có tự sửa whitespace/indentation/escape không.

Lưu ý: Việc editor hiển thị nhiều dòng không chứng minh file đang dùng LF hoặc CRLF ở mức byte. Phải dùng chức năng line-ending của editor, trình kiểm tra hex hoặc công cụ đáng tin tương đương khi muốn xác minh loại line ending trong source.

Bạn cũng có thể so sánh đầu ra của hai bản bằng assertion:

```java
if (!normal.equals("alpha\nbeta\n")) {
    throw new AssertionError("Unexpected text block content");
}
```

Đây là **đoạn lệnh thêm vào `main` của chương trình phần 5**, không phải chương trình độc lập. Tạo unit test tương tự cho payload quan trọng trước khi thay đổi cấu hình editor, formatter hoặc CI.

## 11. Khoảng trắng cuối dòng và dấu `\s` liên quan đến newline thế nào?

Text block không chỉ normalize newline. Bước 2 `stripIndent` còn loại bỏ incidental whitespace, kể cả một số dấu cách **cuối dòng**. Vì vậy, text block có thể cho kết quả khác khi bạn dựa vào những space vật lý khó nhìn:

```java
String noTrailingSpace = """
        A
        B
        """;
```

Nếu bạn bí mật thêm vài dấu space vật lý sau chữ `A` trước khi xuống dòng, compiler thường loại bỏ chúng trong bước `stripIndent`. Muốn **chủ động giữ** một space cuối dòng, dùng `\s`:

```java
String keepTrailingSpace = """
        A\s
        B
        """;
```

Giá trị tương đương `"A \nB\n"`. Do escape `\s` được xử lý sau bước xóa trailing whitespace, space được tạo ra **không bị xóa ở bước 2**.

Điều này có ý nghĩa khi soạn dữ liệu mà dấu cách cuối dòng là thông tin (ví dụ mẫu hiển thị hoặc một số định dạng văn bản). Hãy kiểm tra bằng đánh dấu `<SP>` hoặc so sánh `String`, tránh kiểm tra bằng mắt thường.

**Không nhầm `\s` với newline:** Nó chỉ tạo ASCII space `U+0020`, không phải CR/LF. Sự xuất hiện của `\s` trong một line không làm đổi quy tắc normalize line terminators.

## 12. Line continuation: dấu `\` trước newline làm gì?

Java hỗ trợ escape **backslash ngay trước line terminator**, thường dùng trong text block để một chuỗi nguồn trải trên nhiều dòng nhưng **không có dấu xuống dòng ở vị trí đó** trong kết quả:

```java
String joined = """
        Hello,\
        world
        """;
```

Nếu không có space sau dấu phẩy và không có space trước backslash, giá trị tương đương:

```java
"Hello,world\n"
```

Vì thế nên chủ động thêm space trong source nếu muốn ngăn hai từ ghép liền:

```java
String joinedWithSpace = """
        Hello, \
        world
        """;
```

Giá trị tương đương:

```java
"Hello, world\n"
```

Line continuation **khác** với `\n`:

- `\n`: tạo **một LF** trong giá trị sau bước translate escapes.
- `\` + newline vật lý: loại bỏ line terminator ở vị trí đó khỏi giá trị.
- Xuống dòng vật lý **không có** backslash continuation: còn lại **LF** sau bước normalize.

**Thận trọng với formatter:** Đoạn có backslash cuối dòng dễ hỏng nếu công cụ chèn trailing whitespace hoặc di chuyển line break. Với văn bản yêu cầu byte chính xác, hãy có test kiểm tra ký tự thay vì chỉ dựa vào định dạng source.

## 13. Những điều normalize *không* làm

1. **Không chuyển đổi mọi String ở runtime:** Chỉ xử lý nội dung text block khi compiler tạo hằng `String`. Chẳng hạn `Files.readString` có thể trả CRLF nếu file đầu vào có CRLF.
2. **Không biến `System.lineSeparator()` thành LF:** Đây là API riêng về dấu xuống dòng mặc định của hệ thống.
3. **Không xóa mọi newline:** LF vật lý trở thành LF, trừ khi có escape continuation hoặc cách viết delimiter không đưa newline đó vào nội dung.
4. **Không xóa CR do `\r` escape tạo sau bước normalize:** CR này là kết quả xử lý escape, không phải CR nguồn đã được normalize.
5. **Không bảo đảm mọi dấu whitespace Unicode được chuẩn hóa:** Quy tắc line terminator ở JLS `3.4 dùng ASCII CR và LF.
6. **Không xử lý dữ liệu theo giao thức ứng dụng:** Nếu một protocol đòi `\r\n`, bạn vẫn phải tạo chuỗi với đúng các ký tự theo đặc tả.
7. **Không mặc định bỏ newline cuối:** Dấu `"""` đóng ở dòng riêng khiến newline vật lý ngay trước nó nằm trong nội dung; dấu đóng cùng dòng có thể không tạo newline đó.
8. **Không thay đổi ý nghĩa `\u000A` thành `\n`:** Unicode escape và String escape nằm ở các giai đoạn lexical khác nhau.
9. **Không đảm bảo hiển thị CR/LF khác nhau trên console:** Ký tự điều khiển có thể có cách hiển thị giống nhau. Dùng marker, đếm code unit hoặc kiểm tra hex/bytes.

## 14. Lỗi thường gặp và cách khắc phục

| Hiểu nhầm / lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| «Source file CRLF thì text block cũng có CRLF». | Payload khác dự kiến khi gửi giao thức đòi CRLF. | Text block normalize CRLF/CR thành LF; chèn `\r` hoặc convert chủ động nếu phải có CRLF. |
| «Java xóa toàn bộ CR của mọi String». | Dự đoán sai chuỗi chứa `\r` escape hoặc đọc từ file. | Phân biệt CR vật lý trong source text block và CR có ở runtime. |
| «Đổi hệ điều hành sẽ đổi dấu xuống dòng text block». | Đánh giá sai tính nhất quán khi build đa nền tảng. | Theo JLS, text block normalize về LF, không phụ thuộc `lineSeparator`. |
| «Delimiter đóng ở đâu cũng có LF cuối». | Thiếu/thừa newline cuối payload. | Xác định vị trí delimiter đóng so với dòng nội dung cuối. |
| «Newline ngay sau `"""` mở sẽ có ở đầu String». | Có thêm newline tưởng tượng trước dòng đầu. | Newline đó thuộc opening delimiter, không thuộc nội dung. |
| «Thêm space cuối dòng là đủ để giữ khoảng trắng». | Space bị `stripIndent` loại bỏ. | Dùng `\s` escape hoặc thiết kế literal tường minh. |
| «`\` cuối dòng nghĩa là ký tự backslash trong String». | Không hiểu vì sao newline biến mất. | Đây là line continuation khi đứng ngay trước line terminator. |
| «`\n` và `\\n` đều tạo LF». | Sai dữ liệu hoặc sai số lượng ký tự. | `\n` tạo LF; `\\n` tạo backslash + chữ n. |
| «Dùng `String.lines().count()` để biết chính xác số LF». | Có thể nhầm khi có LF cuối; `lines` không nhất thiết đưa dòng trống cuối thành một phần tử. | Đếm `chars().filter(ch -> ch == '\n').count()` khi cần số ký tự LF thực. |
| «`println` hiển thị là đủ xác nhận kiểu line ending». | Console có thể che giấu CR/LF thực. | Hiển thị `<CR>/<LF>` hoặc đọc byte trong file. |
| «Cứ `replace("\\n", "\\r\\n")` là đúng với mọi đầu vào». | Nếu đầu vào đã có CRLF có thể thành CRCRLF. | Chỉ convert dữ liệu **biết đang chuẩn LF** hoặc normalize đầu vào rõ ràng. |
| «Mọi line separator Unicode đều bị normalize». | Có thể giữ những ký tự separator khác LF/CR. | JLS quy định CR/CRLF/LF ASCII; xử lý Unicode separators theo nhu cầu riêng. |

## 15. Cách xử lý bài toán thực tế

Khi xây dựng chuỗi multiline dùng cho template, HTTP payload, file cấu hình hay golden test:

1. **Xác định định dạng đích:** LF hay CRLF? Cho phép LF cuối không? Có cấm trailing spaces không?
2. **Chọn text block hoặc ordinary String:** Text block phù hợp văn bản nhiều dòng dễ đọc; ordinary literal phù hợp một vài sequence line ending cần tuyệt đối chính xác.
3. **Viết rõ vị trí closing delimiter:** Dòng riêng thường tạo LF cuối; đặt liền sau nội dung khi không muốn newline cuối.
4. **Xác định nhu cầu escape:** Dùng `\r` để có CR; `\n` để chủ động thêm LF; `\` continuation để bỏ newline; `\s` để giữ space.
5. **Tách thời điểm xử lý:** Source line endings normalize lúc compile; runtime String/bytes chỉ thay đổi khi code hoặc API khác tác động.
6. **Kiểm thử bằng assertions/bytes:** So với `"a\nb\n"` hoặc `"a\r\nb\r\n"`; dùng charset cụ thể khi ghi file.
7. **Đảm bảo CI/editor không phá hủy source structure:** Formatter có thể di chuyển delimiter, đổi indent hoặc trailing spaces — những điều này có thể đổi nội dung String ngoài quy tắc normalize.
8. **Chỉ convert newline khi có yêu cầu:** Không tự động áp dụng `System.lineSeparator()` cho một giao thức chỉ định LF hoặc CRLF cố định.

## 16. Bài tập tự kiểm tra

### Bài 1 — Dự đoán String

```java
String s = """
        one
        two
        """;
System.out.println(s.equals("one\ntwo\n"));
```

**Đáp án:** `true`. Có LF giữa hai dòng và LF cuối do closing delimiter nằm trên dòng riêng.

### Bài 2 — Delimiter đóng cùng dòng

```java
String s = """
        one
        two""";
System.out.println(s.endsWith("\n"));
```

**Đáp án:** `false`. Nội dung chấm dứt ngay trước `"""`; không có LF sau `two`.

### Bài 3 — Escape tạo CRLF

```java
String s = """
        one\r
        two\r
        """;
System.out.println(s.equals("one\r\ntwo\r\n"));
```

**Đáp án:** `true`. Mỗi `\r` escape tạo CR sau khi newline vật lý đã được chuẩn hóa thành LF.

### Bài 4 — Cú pháp mở delimiter

```java
// CỐ Ý SAI:
String x = """one""";
```

**Đáp án:** Không biên dịch; opening delimiter của text block phải được theo sau bởi line terminator. Với một String một dòng như `"one"`, có thể dùng ordinary string literal.

### Bài 5 — Dấu `\s` làm gì?

```java
String s = """
        one\s
        two
        """;
System.out.println(s.equals("one \ntwo\n"));
```

**Đáp án:** `true`. Escape `\s` tạo một space sau bước stripIndent nên giữ được trailing space trước LF.

### Bài 6 — Khác biệt `\` continuation và `\n` escape

```java
String a = """
        one\
        two
        """;
String b = """
        one\ntwo
        """;
System.out.println(a.equals(b));
```

**Đáp án:** `false`. `a` là `"onetwo\n"`, còn `b` là `"one\ntwo\n"`.

### Bài 7 — Nếu file source đổi từ LF sang CRLF?

**Câu hỏi:** Text block `"alpha\nbeta\n"` có đổi thành `"alpha\r\nbeta\r\n"` khi editor lưu source CRLF không?

**Đáp án:** **Không.** JLS normalize source CRLF thành LF trước khi tạo String; hai bản nguồn (chỉ khác line terminators) cho cùng giá trị text block.

### Bài 8 — Vì sao test byte tốt hơn xem terminal?

**Đáp án:** Console/terminal có thể trình bày CR và LF tương tự, và `println` tự thêm line terminator. Test `String.equals`, đếm `'\r'`/`'\n'` hoặc so sánh `byte[]` giúp xác định chính xác nội dung.

## 17. Tài liệu chính thức còn hiệu lực

1. [JLS Java SE 25 — `3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6): mô tả ba bước xử lý và thứ tự **normalize CRLF/CR → LF → stripIndent → translateEscapes**.
2. [JLS `3.4 Line Terminators](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.4): CR, LF và CRLF là ba dạng line terminator của mã nguồn Java.
3. [JLS `3.10.7 Escape Sequences](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.7): ý nghĩa `\n`, `\r`, `\s` và line continuation.
4. [JLS `3.3 Unicode Escapes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.3): Unicode escape được xử lý trong pipeline lexical trước text block escape processing.
5. [Javadoc Java SE 17 — `String.stripIndent()` và `String.translateEscapes()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): giải thích removal of incidental whitespace và diễn giải escape sequences.
6. [JEP 378 — Text Blocks](https://openjdk.org/jeps/378): text blocks trở thành tính năng chính thức trong Java 15; dùng để hiểu mục tiêu thiết kế, không dùng preview implementation cho chương trình mới.

**Ghi nhớ:** **Dấu xuống dòng vật lý** trong nội dung text block, dù là CR, LF hay CRLF, được compiler **chuẩn hóa thành LF** trước khi strip indentation và xử lý escape. Nếu kết quả cần CRLF, phải **tạo CR chủ động** bằng `\r` hoặc chuyển đổi String theo hợp đồng đích. **Vị trí delimiter đóng**, **backslash continuation** và các escape sequences quyết định chính xác giá trị cuối cùng; hãy xác minh bằng test ký tự/byte thay vì nhìn xuống dòng trên màn hình.