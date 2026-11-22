# Lồng đoạn mã có text block trong text block khác (Java 15+)

## 1. Hiểu đúng yêu cầu “lồng”

**Text block** là một cách viết `String` nhiều dòng bằng cặp dấu phân định `"""`, được chuẩn hóa thành tính năng chính thức từ **Java 15** và vẫn sử dụng trong Java hiện đại. Khi muốn viết **một đoạn mã Java chứa text block** ngay bên trong **một text block khác**, ta thường đang làm công việc **sinh mã nguồn**, tạo ví dụ minh họa, xây dựng template, hoặc tạo fixture cho kiểm thử.

Cần phân biệt ba lớp:

1. **Mã Java bên ngoài:** chương trình đang biên dịch, có một text block mang tên `generated`.
2. **Chuỗi `generated` tại runtime:** chứa **văn bản mã nguồn Java**, trong đó có các dấu `"""` của text block bên trong.
3. **Mã Java được sinh ra:** nếu lưu chuỗi ấy thành file `.java` rồi biên dịch, text block bên trong lúc này mới được Java phân tích như cú pháp nguồn; khi chạy, nó tạo ra một `String` khác.

Vì thế, đây **không phải** một cú pháp lồng trực tiếp hai String literal đang hoạt động cùng lúc. Ở lớp ngoài, nội dung bên trong chỉ là **ký tự của một chuỗi**. Nó chỉ trở thành mã Java thực sự khi được biên dịch riêng.

**Kết quả cần đạt:** tạo đúng dấu `"""` trong mã được sinh ra; giữ đúng các dấu gạch chéo ngược (`\`), xuống dòng và lề; có thể lưu, biên dịch và chạy mã được sinh ra.

## 2. Vấn đề chính: ba dấu nháy kép trùng với delimiter của text block ngoài

Giả sử muốn sinh ra đoạn Java sau:

```java
String message = """
        Hello from inner text block
        """;
System.out.print(message);
```

Nếu chép nguyên cả hai cụm `"""` này vào phần nội dung của **text block ngoài**, Java có thể hiểu chúng là dấu **đóng của text block ngoài**, khiến những dòng sau trở thành các token không hợp lệ. Đó là lỗi cú pháp khi biên dịch chương trình sinh mã.

Cách giải quyết đúng theo đặc tả Java là **escape dấu nháy kép đầu tiên** trong mỗi cụm ba dấu nháy kép cần xuất hiện ở nội dung:

| Trong source của **text block ngoài** | Chuỗi được tạo ở runtime |
| --- | --- |
| `\"""` | `"""` |
| `String message = \"""` | `String message = """` |
| `\""";` | `""";` |

Trong `\"""`, dấu `\` áp dụng cho **dấu nháy đầu tiên**; hai dấu nháy tiếp theo được giữ nguyên. Khi Java xử lý escape, bốn ký tự nguồn gồm `\` và ba dấu `"` trở thành **ba dấu `"` trong chuỗi kết quả**. Cách viết này gọn và rõ hơn việc escape từng dấu nháy của cả bộ ba.

**Chỉ escape các cụm nháy kép tạo delimiter:** dấu nháy kép đơn lẻ trong một text block, như `String name = "Mai";`, thường **không cần** escape. Trong Java text block, dấu `"` riêng lẻ được phép xuất hiện nguyên dạng.

Ví dụ nguyên lý (chỉ là **đoạn minh họa**, chưa phải chương trình độc lập):

```java
String source = """
        String message = \"""
                Hello from inner text block
                \""";
        System.out.print(message);
        """;
```

Giá trị `source` **sau khi chương trình ngoài biên dịch** chính là đoạn mã Java đầu mục này, với dấu `"""` thật và không còn dấu `\` trước delimiter bên trong.

## 3. Ví dụ đầy đủ: chương trình ngoài sinh file Java chứa text block

Tạo file **`NestedTextBlockDemo.java`** với nội dung sau. Chương trình sử dụng các API chuẩn `java.nio.file`, không cần thư viện ngoài, tương thích từ Java 15 trở lên:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class NestedTextBlockDemo {
    public static void main(String[] args) throws IOException {
        String generated = """
                public class GeneratedSnippet {
                    public static void main(String[] args) {
                        String text = \"""
                                Xin chao tu text block ben trong!
                                \""";
                        System.out.print(text);
                    }
                }
                """;

        Path target = Path.of("GeneratedSnippet.java");
        Files.writeString(target, generated, StandardCharsets.UTF_8);

        System.out.println("Created: " + target.getFileName());
        System.out.println("Has triple quotes: "
                + generated.contains("String text = \"\"\""));
        System.out.println("Has unwanted slash: "
                + generated.contains("\\\"\"\""));
    }
}
```

Các điểm cần quan sát:

- `generated` là **một** text block hợp lệ của chương trình `NestedTextBlockDemo`.
- Hai chỗ `\"""` trong **nội dung** chính là dấu mở và đóng text block của file `GeneratedSnippet.java` sẽ được tạo ra. Chúng không đóng text block bên ngoài.
- `Files.writeString` ghi **nội dung chuỗi đã được Java xử lý escape**, chứ không ghi nguyên dấu `\` dùng để escape delimiter ở source ngoài. UTF-8 được đặt tường minh để ghi file ổn định.
- Dùng `System.out.print` trong mã được sinh ra vì `text` đã kết thúc bằng newline; nếu dùng `println` sẽ in thêm một newline nữa.
- Hai phép `contains` kiểm tra rằng mã nguồn sinh ra có `"""` và **không còn** `\` thừa ngay trước bộ ba dấu nháy.

Trong thư mục chứa file, dùng JDK có `javac` hỗ trợ mức `--release 15` (ví dụ một bản JDK LTS mới, được hỗ trợ) để biên dịch và chạy:

```bash
javac --release 15 -encoding UTF-8 NestedTextBlockDemo.java
java -cp . NestedTextBlockDemo
```

**stdout chính xác của chương trình ngoài:**

```text
Created: GeneratedSnippet.java
Has triple quotes: true
Has unwanted slash: false
```

Sau khi chạy, chương trình tạo file **`GeneratedSnippet.java`** với nội dung đúng như sau (đây là **kết quả sinh ra**, bạn không cần tự gõ lại file):

```java
public class GeneratedSnippet {
    public static void main(String[] args) {
        String text = """
                Xin chao tu text block ben trong!
                """;
        System.out.print(text);
    }
}
```

Tiếp tục biên dịch và chạy **file mới được sinh**:

```bash
javac --release 15 -encoding UTF-8 GeneratedSnippet.java
java -cp . GeneratedSnippet
```

**stdout chính xác của chương trình bên trong:**

```text
Xin chao tu text block ben trong!
```

Text block `text` trong chương trình sinh ra chứa `"Xin chao tu text block ben trong!\n"`, nên trên stdout có một ký tự LF ngay sau dấu `!`. Không cần `--enable-preview`: text blocks đã là tính năng **chính thức từ Java 15**.

Nếu sử dụng JDK mới để biên dịch ví dụ Java 15, `--release 15` giới hạn cú pháp, API Java SE và bytecode theo Java 15. Bài học này không yêu cầu cài hoặc triển khai một runtime Java 15 đã hết vòng đời hỗ trợ; có thể chạy các class trên một JVM hiện đại phù hợp.

## 4. Tại sao lề có thể thay đổi khi “lồng” hai text block?

Một text block Java không phải bản sao nguyên byte của những gì nhìn thấy trong editor. Trình biên dịch xử lý theo trình tự:

1. Chuẩn hóa các ký tự kết thúc dòng thành **LF**.
2. Loại **incidental indentation**, tức khoảng trắng lề mà Java xác định là do cách trình bày source, dựa trên các dòng và vị trí delimiter đóng.
3. Sau cùng mới giải mã các escape như `\"`, `\\`, `\n`, `\s` và `\t`.

Với ví dụ trước, **bước loại lề của text block ngoài** diễn ra trước, để tạo ra file có các dòng Java được thụt 0, 4, 8 và 16 dấu cách. Khi **biên dịch file được sinh**, trình biên dịch lại thực hiện bước loại lề **độc lập** cho text block bên trong. Sau hai lần xử lý, nội dung cuối cùng là dòng thông báo không còn lề thừa.

### Tác động của delimiter đóng

Thay đổi vị trí thụt lề của dấu `"""` **đóng** có thể thay đổi số space mà Java loại bỏ. Ví dụ sau là đoạn Java minh họa riêng lẻ:

```java
String a = """
        one
        two
        """;

String b = """
        one
        two
    """;
```

`a` chứa `"one\ntwo\n"`. `b` chứa `"    one\n    two\n"` vì delimiter đóng của `b` lùi trái **4 space** so với phần nội dung. Nếu chuỗi này là **mã nguồn được sinh ra**, bốn space thừa có thể khiến mã kém đọc hoặc ảnh hưởng dữ liệu nằm trong text block bên trong.

**Thực hành:** đặt delimiter đóng theo lề dự kiến; giữ các dòng text block dùng cùng một loại ký tự thụt lề (thường là space). **Một tab không phải bốn space** trong thuật toán xác định incidental indentation của Java; trộn tab và space có thể khiến kết quả không như mắt nhìn trên IDE.

### Dòng cuối và newline

Nếu delimiter đóng ở dòng riêng, text block thường có **LF ở cuối chuỗi**. Nếu delimiter đóng nằm ngay sau ký tự cuối của dòng nội dung, sẽ **không tự thêm** LF đó. Có thể chủ động dùng escape continuation `\` ngay trước xuống dòng để loại newline khi phù hợp, nhưng với đoạn mã Java sinh ra, thường dễ kiểm tra hơn khi kết thúc file bằng newline.

Chỉ dựa vào việc code được **tô màu hoặc trông đúng** trong editor là chưa đủ. Hãy in `generated` hoặc mở file đã ghi để kiểm tra thực tế mã nguồn sẽ được biên dịch.

## 5. Lưu ý hai tầng escape: dấu nháy, backslash và newline

Khi một source ngoài tạo ra source bên trong, một ký tự có thể đi qua **hai lần xử lý escape**, một lần ở mỗi lần biên dịch. Nên xác định mình muốn có gì ở từng lớp:

| Muốn có trong mã Java sinh ra | Viết trong text block **ngoài** | Lý do |
| --- | --- | --- |
| Delimiter text block: `"""` | `\"""` | Ngăn ba dấu nháy đóng sớm text block ngoài |
| Một literal trong source: `"Hi"` | `"Hi"` | Dấu nháy riêng lẻ không cần escape trong text block |
| Escape newline của source: `\n` (hai ký tự `\` và `n`) | `\\n` | Dấu `\` đầu là escape, kết quả còn `\n` cho compiler bên trong xử lý |
| Escape tab của source: `\t` (hai ký tự `\` và `t`) | `\\t` | Giữ nguyên escape cần có trong file được sinh |
| Backslash thật trong source: `\\` | `\\\\` | Mỗi lần xử lý escape `\\` tạo một backslash |
| Dấu phần trăm `%` trong source | `%` | Text block không có nội suy/format tự động; chỉ cần `%%` nếu sau đó thực sự đưa template qua `formatted`/`format` |

Minh họa ngắn về escape nhiều tầng (đoạn Java **chưa phải một chương trình độc lập**):

```java
String source = """
        String value = "A\\nB";
        """;
```

`source` chứa **một dòng mã Java**, trong đó đoạn `"A\nB"` là sáu ký tự nguồn tương ứng với dấu `"`, `A`, `\`, `n`, `B`, dấu `"`. Nếu lưu thành file Java hợp lệ và biên dịch, `String value` của chương trình bên trong sẽ chứa **newline thật giữa A và B**. Nếu trong text block ngoài dùng `"A\nB"`, Java sẽ chuyển `\n` thành ký tự LF **quá sớm** và có thể làm hỏng dòng Java được sinh.

Tương tự, muốn một text block được sinh ra chứa **ký tự backslash** nguyên dạng, hãy đếm đủ các tầng cần escape. Dùng `String.contains(...)`, độ dài chuỗi hoặc in mã nguồn ra file để kiểm tra.

**Không dùng Unicode escape như `\u0022` để “né” delimiter.** Unicode escapes trong Java có quy tắc xử lý rất sớm ở cấp mã nguồn và dễ gây lỗi tinh vi; `\"""` đã là cách được đặc tả và tài liệu Oracle khuyến nghị cho ba dấu nháy lồng.

## 6. Các lỗi phổ biến và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Hướng khắc phục |
| --- | --- | --- |
| `javac` báo lỗi text block chưa kết thúc hoặc các token lạ tại dòng mã lồng | Viết `"""` trực tiếp làm đóng text block **ngoài** | Đổi mỗi delimiter lồng thành `\"""` trong source ngoài |
| File được sinh vẫn có dấu `\` trước `"""` | Escape quá nhiều lần, ví dụ `\\\"""` | Đếm số lớp escape; kiểm tra file đầu ra có đúng ba dấu nháy không |
| File sinh ra biên dịch lỗi dù chương trình ngoài chạy thành công | Một `String` hợp lệ không bảo đảm **nội dung của nó** là source Java hợp lệ | Lưu file đúng tên `public class`, chạy `javac` riêng cho mã được sinh |
| Text block bên trong tạo chuỗi có khoảng trắng đầu dòng | Lề hoặc delimiter đóng không theo bố cục dự kiến | Kiểm tra raw file được sinh; chỉnh indentation và tránh trộn tab/space |
| Nội dung `\n` bị biến thành newline sớm | Chỉ escape một tầng, trong khi cần giữ escape cho compiler thứ hai | Trong text block ngoài dùng `\\n` để file sinh ra chứa `\n` |
| Chuỗi sinh ra có newline cuối không mong muốn | Đặt delimiter đóng ở dòng riêng | Điều chỉnh vị trí delimiter/continuation đúng mục tiêu; so sánh `length`, `endsWith("\n")` |
| Code sinh ra chứa giá trị người dùng làm vỡ dấu nháy hoặc cấu trúc source | Ghép trực tiếp dữ liệu vào Java source mà không escape/validate | Dùng biểu diễn literal Java chính xác, kiểm tra dữ liệu; với dữ liệu không tin cậy, tránh biên dịch/chạy mã sinh ra tùy ý |
| Trình biên dịch không nhận `--release 15` | JDK compiler không hỗ trợ mức source yêu cầu | Kiểm tra `javac -version` và `javac --help`; dùng JDK compiler phù hợp |

Lưu ý: có thể viết `\"\"\"` để escape **từng** dấu nháy trong ba dấu, nhưng điều đó làm code khó đọc hơn. Oracle khuyến nghị chỉ escape **dấu đầu tiên** của mỗi cụm ba nháy kép, tức `\"""`. Nếu đoạn mã chứa **nhiều hơn ba dấu nháy liên tiếp**, hãy phân tích toàn bộ chuỗi nháy để không vô tình tạo một delimiter khác.

## 7. Dùng cách nào khi dự án ngày càng lớn?

**Chỉ có vài đoạn Java nhúng, ví dụ tài liệu hoặc test:** dùng text block ngoài với `\"""` cho delimiter lồng và `\\` cho backslash cần giữ; giữ lề nhất quán và có kiểm thử so sánh nội dung file được sinh.

**Template Java lớn, có nhiều text block hoặc nhiều tầng lồng:** cân nhắc lưu mã mẫu trực tiếp trong file resource `.java` hoặc `.txt` riêng, rồi đọc bằng `Files.readString(path, StandardCharsets.UTF_8)`. File mẫu lúc đó chứa `"""` tự nhiên, không cần tăng số tầng escape trong chương trình sinh mã. Có thể dùng template engine đã được dự án quản lý nếu thật sự cần nội suy dữ liệu, nhưng đừng thêm dependency chỉ để né một bộ ba dấu nháy.

**Sinh mã theo cấu trúc:** khi phải tạo nhiều class, method hoặc expression từ dữ liệu, có thể dùng thư viện tạo Java source theo cấu trúc (nếu đáp ứng yêu cầu bảo trì của dự án) thay vì nối các chuỗi phức tạp. Điều quan trọng là bảo đảm mã sinh ra biên dịch được và đầu vào không được tùy ý biến thành mã thực thi.

**Kiểm thử tối thiểu:** chạy chương trình sinh mã; so sánh file đầu ra với nội dung mong đợi; biên dịch file đầu ra; chạy và khẳng định stdout hoặc giá trị trả về. Việc compiler ngoài chấp nhận một text block **không kiểm tra** chất lượng của Java source nằm trong chuỗi đó.

## 8. Checklist trước khi hoàn thành

1. Text block ngoài mở bằng `"""` theo sau bởi xuống dòng, đóng đúng vị trí lề.
2. **Mọi** delimiter `"""` cần xuất hiện bên trong mã được sinh đều được viết thành `\"""` trong source ngoài.
3. Dấu `\` có chủ đích trong mã sinh ra được escape đủ số tầng; đặc biệt kiểm tra `\n`, `\t` và đường dẫn.
4. Output thực tế không có `\` thừa trước bộ ba dấu `"""`.
5. File `.java` được sinh có tên phù hợp `public class`, encoding ổn định và indentation hợp lệ.
6. Biên dịch **cả chương trình sinh mã lẫn chương trình được sinh** trên Java phù hợp; chạy chương trình được sinh để đối chiếu stdout.
7. Chỉ dùng tính năng **text blocks đã chính thức từ Java 15**, không cần cơ chế preview, API đã loại bỏ hay một runtime Java 15 không còn được hỗ trợ.

## Tài liệu chính thức

- Java Language Specification, `3.10.6 Text Blocks`: https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6
- Oracle, *Programmer's Guide to Text Blocks*, phần **Embedded Triple Quotes**, **Translation of Escape Sequences** và hướng dẫn G8: https://docs.oracle.com/en/java/javase/25/text-blocks/index.html
- Oracle, *Text Blocks* trong tài liệu Java hiện đại: https://docs.oracle.com/en/java/javase/25/language/text-blocks.html

Các nguyên tắc này áp dụng với Java 15 và Java hiện đại. Đối với môi trường thực tế, dùng JDK/JVM còn được nhà cung cấp hỗ trợ, và đặt `--release` phù hợp khi muốn mã có thể biên dịch theo mức Java 15.
