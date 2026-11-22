# Phân biệt thụt lề trình bày với thụt lề có ý nghĩa trong Java text block

## Mục tiêu

Java text block là cách viết chuỗi nhiều dòng trực tiếp trong mã nguồn. Tuy nhiên, số dấu cách bạn **nhìn thấy** trong tệp `.java` không nhất thiết bằng số dấu cách có trong `String` ở runtime. Người học cần phân biệt:

- **Thụt lề trình bày** (*incidental indentation*): khoảng trắng đầu dòng chỉ để căn đoạn văn bản theo code style; Java tự loại phần lề chung.
- **Thụt lề có ý nghĩa** (*essential indentation*): phần thụt sâu hơn mức lề chung, được giữ trong giá trị chuỗi. Nó có thể là cấu trúc của YAML, khối lệnh Python hoặc căn cột văn bản.

Bài này làm rõ cách xác định lề chung, vai trò của dấu `"""` đóng, xuống dòng cuối, khoảng trắng cuối dòng, tab so với space và escape sequences. Bạn cũng sẽ chạy chương trình kiểm tra chính xác từng ký tự, thay vì chỉ nhìn giao diện hiển thị.

**Tính hiện hành:** Text blocks đã trở thành tính năng chính thức từ **Java 15**, tiếp tục được hỗ trợ trong Java hiện đại. Mã độc lập dùng **JDK 17 trở lên**, không yêu cầu `--enable-preview` và không dùng cách chạy text blocks preview cũ của Java 14.

## 1. Text block tạo ra một String bình thường

Ví dụ Java **bên trong method**:

```java
String message = """
    Hello
        Java
    """;
```

Về mặt giá trị, nó tương đương:

```java
String message = "Hello\n    Java\n";
```

Đây là hai cách khai báo **thay thế nhau**, không đặt đồng thời trong cùng phạm vi. Trong chuỗi runtime:

- Dòng đầu có `Hello`, **không có** bốn space ở đầu.
- Dòng thứ hai có **bốn space**, rồi `Java`.
- Dòng thứ hai được kết thúc bằng `\n`, vì dấu `"""` đóng nằm ở **dòng riêng** sau dòng nội dung cuối.

Ba dấu nháy kép mở phải được theo sau bởi line terminator trước khi nội dung text block bắt đầu; không thể viết `"""hello"""` như một text block hợp lệ. Dấu xuống dòng ngay sau delimiter mở không tự trở thành một dòng trống đầu tiên trong `String`.

Một text block vẫn là `java.lang.String`, không phải đối tượng có khả năng hiểu ngữ nghĩa HTML/YAML/Python. Java không tự chạy mã nhúng, không nội suy biến và không tự chọn độ thụt có ý nghĩa dựa vào định dạng đích.

## 2. Thụt lề trình bày là gì?

Hãy xem đoạn Java sau:

```java
String html = """
        <div>
            <span>Hello</span>
        </div>
        """;
```

Trong đúng code fence này, dòng `<div>` có tám dấu cách đứng trước, dòng `<span>` có mười hai dấu cách, còn `</div>` và dấu `"""` đóng đều có tám dấu cách. Compiler loại tám dấu cách **lề trình bày chung**, tạo ra chuỗi:

```text
<div>
    <span>Hello</span>
</div>
```

Ký hiệu `·` sau đây **chỉ dùng để quan sát một dấu cách** trong sơ đồ; không phải ký tự cần viết vào Java source:

```text
MÃ NGUỒN:
········<div>
············<span>Hello</span>
········</div>
········"""   (dấu đóng)

CHUỖI SAU KHI XỬ LÝ:
<div>
····<span>Hello</span>
</div>
```

Tám dấu cách để căn văn bản theo mức thụt của câu lệnh Java chỉ là incidental. Bốn dấu cách **tương đối** đứng trước `<span>` là essential: chúng được giữ vì dòng con sâu hơn dòng cha.

Nếu cả các dòng nội dung và delimiter được di chuyển sang phải cùng một lượng space, giá trị chuỗi thông thường không đổi. Nếu chỉ di chuyển nội dung hoặc delimiter, giá trị có thể đổi, dù những chữ cái của văn bản không thay đổi.

## 3. Dấu đóng quyết định phần nào là lề chung

### Trường hợp A — Dấu đóng ngang mức lề của dòng ngoài cùng

```java
String a = """
        root
            child
        """;
```

Giá trị `a` là `"root\n    child\n"`.

### Trường hợp B — Dòng nội dung dịch phải nhưng dấu đóng đứng nguyên

```java
String b = """
            root
                child
        """;
```

Giá trị `b` là `"    root\n        child\n"`.

Trong trường hợp B, dấu đóng đứng **ít thụt lề hơn** các dòng nội dung nên mức lề chung thấp hơn. Bốn dấu cách trước `root` nay không bị loại; chúng trở thành khoảng trắng có ý nghĩa. Tương tự, `child` còn tám dấu cách đầu dòng.

### Trường hợp C — Dấu đóng ngay sau nội dung cuối

```java
String c = """
        root
            child""";
```

Giá trị `c` là `"root\n    child"`, **không có `\n` cuối**. Vì dấu đóng không chiếm một dòng riêng, không có lề của dòng dấu đóng để tham gia mức thụt chung; các dòng nội dung có vai trò quyết định.

**Kết luận thực hành:** Đừng coi `"""` đóng là chi tiết trang trí. Tự động định dạng hoặc sao chép code có thể làm khác giá trị `String` nếu thay đổi quan hệ lề, ngay cả khi chữ trên các dòng vẫn như cũ.

## 4. Compiler xử lý text block theo thứ tự nào?

Theo đặc tả Java, những bước cần hiểu là:

1. **Chuẩn hóa line terminator** của nội dung: các cách xuống dòng trong Java source được chuẩn hóa thành `\n` trong text block.
2. **Loại incidental white space**: xác định lề chung từ các dòng không trống; nếu dấu đóng ở dòng riêng thì lề dấu đóng cũng tham gia. Mức lề chung được loại khỏi các dòng phù hợp và khoảng trắng cuối dòng được xử lý.
3. **Diễn giải escape sequences sau cùng**: ví dụ `\s`, `\040`, `\t`, `\n` hoặc backslash + line terminator được xử lý sau bước loại khoảng trắng.

Hệ quả:

- Một dòng nội dung thụt sâu hơn mức chung sẽ giữ **độ sâu chênh lệch**.
- Một dòng trắng hoặc chỉ có whitespace có quy tắc xử lý riêng, không nên dùng để phỏng đoán lề chung từ số cột hiển thị.
- Khoảng trắng cuối dòng thường bị loại; nếu đó là dữ liệu bắt buộc phải giữ, cần một cách diễn đạt tường minh như `\s`.
- Unicode escape như `\u0020` được xử lý sớm hơn giai đoạn xử lý text block nên **không** phải lựa chọn đáng tin để giữ trailing space.

Java không hỏi liệu một mức thụt lề có quan trọng với YAML hay không. Nó chỉ áp dụng thuật toán chuỗi. Điều quan trọng là bạn phải **tính được kết quả theo quy tắc, sau đó test giá trị runtime**.

## 5. Chương trình Java 17+ có kiểm chứng toàn bộ String

Tạo tệp **`TextBlockIndentDemo.java`**. Trong code sau, `visible` đổi space thành dấu `·` và newline thành hai ký tự `\` + `n` để bạn nhìn thấy chỗ chuỗi chứa khoảng trắng. Phương thức `expect` dùng `String.equals` để kiểm tra **từng ký tự**.

```java
public final class TextBlockIndentDemo {
    private TextBlockIndentDemo() {
    }

    private static String visible(String value) {
        return value.replace(" ", "·").replace("\n", "\\n");
    }

    private static void expect(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    label + " expected=[" + visible(expected)
                    + "] actual=[" + visible(actual) + "]");
        }
    }

    public static void main(String[] args) {
        String presentation = """
                root
                    child
                """;

        String essential = """
                    root
                        child
                """;

        String noFinalNewline = """
                root
                    child""";

        String trailing = """
                A\s
                B\s
                """;

        String joined = """
                Good \
                morning
                """;

        expect("presentation", "root\n    child\n", presentation);
        expect("essential", "    root\n        child\n", essential);
        expect("noFinalNewline", "root\n    child", noFinalNewline);
        expect("trailing", "A \nB \n", trailing);
        expect("joined", "Good morning\n", joined);

        System.out.println("presentation=[" + visible(presentation) + "]");
        System.out.println("essential=[" + visible(essential) + "]");
        System.out.println("no-final-newline=["
                + visible(noFinalNewline) + "]");
        System.out.println("trailing=[" + visible(trailing) + "]");
        System.out.println("joined=[" + visible(joined) + "]");
    }
}
```

Lệnh biên dịch và chạy với JDK 17+ tại thư mục chứa tệp:

```bash
javac --release 17 TextBlockIndentDemo.java
java TextBlockIndentDemo
```

**Stdout mong đợi chính xác**, trong đó `·` đại diện một space:

```text
presentation=[root\n····child\n]
essential=[····root\n········child\n]
no-final-newline=[root\n····child]
trailing=[A·\nB·\n]
joined=[Good·morning\n]
```

Giải thích:

- `presentation` loại lề chung, giữ bốn dấu cách trước `child`, đồng thời giữ `\n` cuối chuỗi.
- `essential` có nội dung dịch phải bốn dấu cách so với delimiter: kết quả còn bốn space trước `root`, tám trước `child`.
- `noFinalNewline` đóng `"""` trên chính dòng `child` nên không có `\n` cuối.
- `trailing` dùng `\s`: mỗi dòng có một dấu cách **sau** `A` hoặc `B`, ngay trước `\n`.
- `joined` có backslash cuối dòng nguồn đầu tiên. Dòng thứ nhất và thứ hai được nối với nhau thành `"Good morning"`; dấu cách giữa hai từ được bảo toàn và `\n` cuối chuỗi vẫn tồn tại.

Khi thay đổi vị trí dấu đóng hoặc thêm/bỏ một dấu cách, `expect` sẽ phát hiện thay đổi dù mắt người đọc không dễ nhận ra. Đây là ví dụ **độc lập hoàn chỉnh** có `main`; các đoạn nhỏ khác trong bài chỉ là minh họa.

## 6. Khi độ thụt lề tương đối thực sự có ý nghĩa

### YAML

Ví dụ Java trong một method:

```java
String yaml = """
        server:
          host: localhost
          ports:
            - 8080
            - 8081
        """;
```

Giá trị chuỗi sau compile-time:

```yaml
server:
  host: localhost
  ports:
    - 8080
    - 8081
```

Các trường `host` và `ports` nằm dưới `server` với **hai space**, các mục danh sách nằm dưới `ports` với **bốn space**. Nếu vô tình làm phẳng nội dung, YAML có thể thay đổi cấu trúc mặc dù Java vẫn biên dịch.

### Python

```java
String python = """
        if ready:
            print("run")
        print("done")
        """;
```

Chuỗi tương đương `"if ready:\n    print(\"run\")\nprint(\"done\")\n"`. Khoảng cách trước `print("run")` biểu thị một khối lệnh của Python. Compiler Java không tự xác thực Python; nó chỉ tạo chuỗi.

Với HTML, SQL, XML hay dữ liệu preformatted, whitespace có thể có hoặc không có ảnh hưởng tùy vị trí và parser. Không nên coi mọi định dạng nhúng đều bỏ qua khoảng trắng. Hãy kết hợp **kiểm thử giá trị String** và **kiểm thử parser/hành vi** của định dạng đích khi cần.

## 7. Phân biệt leading whitespace và trailing whitespace

### Thụt lề đầu dòng

Leading indentation là phần khoảng trắng trước ký tự nội dung. Compiler loại mức chung và giữ phần chênh lệch. Đây là vấn đề trọng tâm của `incidental` so với `essential` indentation.

### Khoảng trắng cuối dòng

Trailing whitespace là dấu cách/tab đứng **sau ký tự cuối cùng nhìn thấy**, trước newline. Text block thông thường loại chúng. Dựa vào những dấu cách gõ trực tiếp cuối dòng rất dễ gây lỗi khi editor hoặc code formatter tự làm sạch.

**Cách giữ một dấu cách cuối dòng:**

```java
String text = """
        A\s
        B\s
        """;
```

Giá trị chính xác là `"A \nB \n"`. Escape `\s` đại diện một ký tự space, được dịch **sau** khi xử lý incidental white space. Nếu cần nhiều space, dùng số escape có chủ đích hoặc một cách tạo chuỗi minh bạch khác.

`\040` (octal escape cho space) cũng có thể dùng để tạo dấu cách sau bước xử lý lề. Ngược lại, `\u0020` không an toàn cho mục tiêu này vì Unicode escapes được thay thế sớm lúc Java đọc source.

Nếu muốn chứa **ký tự backslash + chữ s** trong chuỗi dữ liệu thay vì space, cần escape backslash trong Java source (ví dụ `\\s`); đừng nhầm escape của ngôn ngữ Java với ký tự bạn muốn truyền ra định dạng đích.

## 8. Dòng cuối và backslash nối dòng

### Dấu đóng riêng dòng

```java
String withFinalNewline = """
        first
        second
        """;
```

Nó bằng `"first\nsecond\n"`.

### Dấu đóng cuối dòng nội dung

```java
String withoutFinalNewline = """
        first
        second""";
```

Nó bằng `"first\nsecond"`.

### Nối hai dòng bằng backslash cuối dòng nguồn

```java
String joined = """
        Hello, \
        world!
        """;
```

Nó bằng `"Hello, world!\n"`: không có `\n` ở vị trí nối, nhưng có `\n` cuối vì dấu đóng ở dòng riêng. Space giữa `Hello,` và backslash được giữ.

Bạn cũng có thể bỏ newline cuối mà vẫn để dấu đóng ở dòng riêng:

```java
String noEnd = """
        first
        second\
        """;
```

Nó bằng `"first\nsecond"`. Các escape này là **tính năng chính thức**, không cần bật preview.

Các thay đổi tưởng như chỉ liên quan trình bày, ví dụ chuyển `"""` xuống dòng mới, có thể làm khác `String` ở runtime. Điều đó quan trọng với snapshot tests, nội dung tệp, giao thức và dữ liệu cần so sánh chính xác.

## 9. Tab và space: đếm ký tự khác với cột hiển thị

Java xét **số ký tự white space** trong thuật toán lề, không coi một tab là bốn hay tám cột theo thiết lập editor. Một dòng có một tab và một dòng có bốn space có thể **trông** thẳng hàng nhưng không có cùng lượng ký tự whitespace để compiler xử lý.

Vì vậy, đừng trộn tab với space khi tạo các text block nhạy cảm indentation như YAML/Python. Chọn một kiểu nhất quán — thông thường dùng space — rồi kiểm tra chuỗi sau biên dịch.

Có thể bật cảnh báo của `javac`:

```bash
javac --release 17 -Xlint:text-blocks TextBlockIndentDemo.java
```

Tùy nội dung source, compiler có thể cảnh báo về *inconsistent white space indentation* hoặc *trailing white space will be removed*. Cảnh báo giúp tìm lỗi tiềm ẩn, nhưng không thay thế test String và test parser.

## 10. stripIndent(), indent() và strip() không giống nhau

| API | Dùng để làm gì? | Lưu ý |
| --- | --- | --- |
| `String.stripIndent()` | Loại mức lề chung từ **một String ở runtime** | Text block vốn đã được xử lý lề ở compile-time; không nên gọi lặp vô điều kiện |
| `String.indent(int n)` | Chủ động tăng/giảm indentation từng dòng | Có quy tắc về line terminator; không bảo đảm giữ mọi ký tự trong trường hợp đặc biệt |
| `String.strip()` | Bỏ whitespace ở **hai đầu toàn chuỗi** | Không loại mức lề chung của mọi dòng và có thể xóa `\n` cuối |

Ví dụ đặt trong method:

```java
String input = "    A\n      B\n";
String normalized = input.stripIndent();
String indented = normalized.indent(2);
```

Trong trường hợp này, `normalized` là `"A\n  B\n"` và `indented` là `"  A\n    B\n"`. Cần kiểm chứng các ca có dòng trống, `\r\n` hoặc trailing whitespace trước khi áp dụng vào xử lý dữ liệu thật.

Cần phân biệt thêm `String.translateEscapes()`: phương thức này diễn giải một số escape Java **ở runtime**, không có nhiệm vụ xác định lề trình bày và cũng không phải parser mọi hệ thống escape như JSON.

## 11. Các lỗi thường gặp

**1. Tưởng mọi space trước nội dung đều được giữ.** Với `"""` đóng ngang lề dòng ngoài cùng, phần căn lề chung sẽ bị loại. Muốn giữ một mức thụt đầu dòng cố định, để nội dung lệch phải so với dấu đóng hoặc tạo lề một cách tường minh.

**2. Dịch dấu đóng trong lúc format.** Trong hai chuỗi sau, chỉ vị trí lề nguồn thay đổi, nhưng kết quả khác nhau:

```java
String a = """
        x
          y
        """;
String b = """
            x
              y
        """;
```

`a` là `"x\n  y\n"`; `b` là `"    x\n      y\n"`.

**3. Quên newline cuối.** Hai text blocks sau không bằng nhau:

```java
String a = """
        x
        """;
String b = """
        x""";
```

`a` bằng `"x\n"`; `b` bằng `"x"`.

**4. Gõ trực tiếp trailing spaces rồi mong compiler giữ.** Dùng `\s` hoặc cách thay thế rõ ràng để giữ những dấu cách có ý nghĩa.

**5. Trộn tab/space.** Độ rộng hiển thị trong editor không phải phép đếm mà compiler áp dụng. Dùng quy ước nhất quán.

**6. Dùng `strip()` thay cho `stripIndent()`.** Hai hàm xử lý phạm vi khác nhau: cả chuỗi so với lề từng dòng. Cách dùng sai có thể xóa newline cuối hoặc bỏ sót lề ở những dòng giữa.

**7. Nghĩ text block tự nội suy biến.** Nội dung của text block là văn bản; nó không tự thay các ký hiệu placeholder bằng biến Java. Cần dùng `String.formatted(...)`, `String.format(...)` hoặc cách tạo dữ liệu chuyên biệt nếu muốn ghép giá trị.

**8. Viết text block một dòng ngay sau dấu mở.** Đây là mã **cố ý sai**:

```java
String bad = """hello"""; // ERROR: phải có line terminator sau """
```

Nếu chỉ là chuỗi một dòng ngắn, dùng `"hello"` thay vì text block.

## 12. Checklist kiểm chứng chính xác khoảng trắng

1. Xác định kết quả `String` mong đợi: mỗi dòng có bao nhiêu space/tab đầu, có dấu cách cuối hay không, có `\n` cuối hay không.
2. Kiểm tra mức thụt của **các dòng nội dung không trống** và của dấu đóng `"""` nếu nằm trên dòng riêng.
3. Xác định phần lề chung sẽ bị loại và phần chênh lệch cần giữ.
4. Dùng `\s` cho trailing space cần bảo tồn; tránh ký tự whitespace vô hình không được bảo đảm sau format.
5. Khi nghi ngờ, bật `-Xlint:text-blocks`; không dựa vào lint để thay test.
6. So sánh `expected.equals(actual)` với giá trị chính xác, **không `trim()` hoặc `strip()` trước khi so sánh**, vì làm vậy có thể che mất lỗi.
7. Khi kết quả khác nhau, hiển thị dấu cách bằng `·`, tab bằng một ký hiệu rõ và newline bằng `\\n`.
8. Với văn bản nhúng có ngữ nghĩa như YAML/Python, cần thêm test parser hoặc test hành vi của định dạng đích.

## 13. Bài thực hành

Viết phương thức `static String yamlConfig()` tạo chuỗi:

```yaml
app:
  name: demo
  features:
    - search
    - export
```

Yêu cầu:

- Giữ đúng hai dấu cách trước `name`, `features` và bốn dấu cách trước hai mục `-`.
- Giữ đúng một ký tự `\n` cuối chuỗi.
- Căn lề text block theo method trong Java source, nhưng **không thay đổi** indentation tương đối của YAML.
- Viết phép kiểm tra:

```java
yamlConfig().equals(
        "app:\n  name: demo\n  features:\n    - search\n    - export\n");
```

Sau đó thử dịch delimiter đóng sang trái bốn dấu cách mà không đổi nội dung; dự đoán phần space nào sẽ được giữ thêm. Thêm phiên bản có `\s` ở cuối một dòng rồi so sánh với phiên bản không có escape; thử cả dấu đóng riêng dòng và dấu đóng cùng dòng nội dung.

**Tiêu chí đạt:** Giải thích được chỗ nào là **lề trình bày trong mã Java**, chỗ nào là **dữ liệu mang ý nghĩa** trong chuỗi, và tự kiểm tra được khác biệt mà mắt người không dễ nhận thấy.

## Tài liệu chính thức

- [Oracle Java SE 26 — Text Blocks](https://docs.oracle.com/en/java/javase/26/language/text-blocks.html): hướng dẫn hiện hành về incidental/essential whitespace, dấu đóng và các escape.
- [Oracle Java SE 17 — Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html): ví dụ về lề, newline cuối, tab và String methods.
- [Java Language Specification, `3.10.6 — Text Blocks](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-3.html#jls-3.10.6): đặc tả ngôn ngữ.
- [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378): tính năng ổn định từ Java 15.

**Ghi nhớ:** Compiler loại **mức thụt lề trình bày chung**, không xóa mọi khoảng trắng đầu dòng. **Độ thụt tương đối có ý nghĩa** được giữ trong String; dấu đóng, trailing spaces và escape có thể làm khác dữ liệu. Hãy kiểm chứng chuỗi runtime bằng test chính xác.