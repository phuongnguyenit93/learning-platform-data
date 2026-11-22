# Viết mẫu văn bản nhiều dòng có kiểm thử khoảng trắng trong Java

> **Chủ đề cha:** Java 14 → Thực hành tổng hợp. **Trọng tâm:** tự xây một mẫu văn bản nhiều dòng bằng **Java text blocks**, rồi viết kiểm thử chính xác cho **thụt lề đầu dòng, khoảng trắng cuối dòng, dòng trống, tab và ký tự xuống dòng cuối**. Text blocks được thử nghiệm trong giai đoạn Java 13/14 và **trở thành tính năng chính thức từ Java 15 (JEP 378)**; bài thực hành dùng **Java 17+** và cú pháp chuẩn hiện hành, không yêu cầu hay hướng dẫn dùng chế độ preview cũ.

## 1. Kết quả cần đạt

Sau bài này bạn sẽ:

1. Viết một **template nhiều dòng thực tế** bằng `"""`, truyền tham số bằng `String.formatted(...)` và so sánh với một chuỗi kỳ vọng độc lập.
2. Phân biệt **incidental indentation** của mã nguồn và **essential indentation** thuộc dữ liệu văn bản.
3. Hiểu vì sao text block có thể **thêm LF cuối**, và cách bỏ LF cuối khi định dạng đầu ra đòi hỏi.
4. Biết ký tự nào bị loại bỏ khỏi cuối dòng và cách giữ dấu cách bằng `\s`, `\040` hoặc phương pháp thay thế ký tự.
5. Dùng `\` ngay trước line terminator để **nối dòng** thay vì tạo `\n`.
6. Hiểu quy tắc chuẩn hóa **CR, CRLF thành LF** trong text blocks.
7. Viết bộ kiểm thử tự chạy không cần thư viện ngoài, so sánh `String.equals` và có thông báo lỗi hiển thị khoảng trắng ẩn.
8. Kiểm tra các edge cases: dòng rỗng, tab, dấu ngoặc kép, template formatting, `stripIndent`, `translateEscapes`, `indent`, `lines` và `split`.
9. Chạy `javac --release 17 -Xlint:text-blocks` để phát hiện một số lỗi thụt lề không đồng nhất và khoảng trắng cuối dòng bị compiler loại bỏ.
10. Nhận biết tình huống không nên dùng text block: một chuỗi một dòng đơn giản, SQL động không dùng prepared statements, JSON tạo bằng nối chuỗi không escape đúng.

**Kết luận cốt lõi:** Text block trả về **`java.lang.String`**, nhưng những gì người đọc *nhìn thấy* trong source chưa chắc giống từng ký tự trong string runtime. Vì vậy bài này kiểm thử **nội dung chính xác** chứ không chỉ in ra terminal để nhìn bằng mắt.

## 2. Bối cảnh: Text blocks là cách viết String nhiều dòng

Nếu không dùng text block, một mẫu thông báo có thể được viết bằng nhiều literal và dấu cộng:

```java
String notice = "THÔNG BÁO\n"
        + "Mã: A-17\n"
        + "\n"
        + "  Nội dung: Xong\n"
        + "Kết thúc.\n";
```

Đoạn này **hợp lệ**, nhưng khi mẫu dài, các dấu `\n`, `+` và việc escape dấu ngoặc kép dễ che khuất cấu trúc văn bản.

Text block giúp viết gần với văn bản cần xuất:

```java
String notice = """
        THÔNG BÁO
        Mã: A-17

          Nội dung: Xong
        Kết thúc.
        """;
```

Hai đoạn trên tạo **cùng một String** nếu indentation trong nguồn được giữ đúng như minh họa. Text block **không tạo một kiểu dữ liệu mới**, không tự lưu template vào file và không tự xử lý escaping cho HTML/SQL/JSON.

### 2.1. Cú pháp bắt buộc

- Mở đầu bằng đúng ba dấu ngoặc kép `"""` và ngay sau đó là **line terminator** (có thể có các dấu cách trên dòng mở trước newline theo ngữ pháp).
- Nội dung bắt đầu trên **dòng tiếp theo**, không được nằm ngay sau `"""` mở.
- Kết thúc bằng ba dấu ngoặc kép `"""`.
- Dấu ngoặc kép đơn lẻ `"` bên trong thường không cần escape; chỉ khi một chuỗi dấu ngoặc kép có thể tạo thành delimiter mới thì phải escape phù hợp.
- Nội dung được compiler biến đổi trước khi trở thành `String`.

Ví dụ sai:

```java
// KHÔNG BIÊN DỊCH: nội dung nằm ngay sau opening delimiter.
String a = """hello""";

// KHÔNG BIÊN DỊCH: opening delimiter không có line terminator.
String b = """hello
        world""";
```

Ví dụ hợp lệ:

```java
String a = """
        hello
        """;
```

`a` tương đương `"hello\n"`, không phải `"hello"`. Dấu xuống dòng cuối là một phần của dữ liệu.

### 2.2. Bối cảnh phiên bản Java

| Phiên bản | Trạng thái liên quan |
| --- | --- |
| Java 13/14 | Text blocks từng là tính năng **preview**. Đây chỉ là bối cảnh lịch sử của chủ đề Java 14. |
| **Java 15** | Text blocks được **finalize** (JEP 378). |
| **Java 17+** | Sử dụng text blocks chính thức; `javac --release 17` biên dịch được, **không cần preview flags**. |
| Java SE 25 | Java Language Specification và Programmer's Guide vẫn mô tả đầy đủ hành vi này. |

Nhờ vậy bài không cần dạy lại cách bật preview cũ; hãy viết mã có thể dùng lâu dài trên bản Java ổn định.

## 3. Quy trình biến text block từ source thành String

Java Language Specification mô tả ba bước theo đúng thứ tự:

1. **Normalize line terminators:** Chuyển `CRLF` và `CR` trong nội dung thành `LF`, tức ký tự `\n` (`U+000A`).
2. **Remove incidental white space:** Loại thụt lề chung không mang ý nghĩa nội dung, đồng thời loại khoảng trắng cuối dòng thuộc incidental whitespace.
3. **Translate escape sequences:** Xử lý `\n`, `\t`, `\s`, `\\`, `\` nối dòng và các escape hợp lệ.

```text
Java source text block
        |
        v
[1] Normalize line endings -> LF
        |
        v
[2] Strip incidental indentation/trailing whitespace
        |
        v
[3] Translate escapes (bao gồm \s, \t, \040, continuation)
        |
        v
java.lang.String runtime
```

**Thứ tự là yếu tố quan trọng.** Vì `\s` được dịch **sau** bước xóa khoảng trắng cuối dòng, nó cho phép giữ một dấu cách ở cuối dòng mà một ký tự space thật trong source có thể bị loại bỏ.

### 3.1. Không phải toàn bộ dấu cách đầu dòng đều bị bỏ

Xét đoạn đặt trong một method:

```java
String text = """
        alpha
          beta
        """;
```

Ở đây ba dòng nội dung có mức thụt lề tương đối:

- `alpha`: 8 spaces trước chữ.
- `beta`: 10 spaces trước chữ.
- Dòng chứa closing delimiter: 8 spaces trước `"""`.

Phần thụt lề **chung** là 8 spaces, bị xóa. Hai spaces thêm trước `beta` là essential indentation nên **được giữ lại**.

Kết quả chính xác:

```java
"alpha\n  beta\n"
```

Đây là một literal bình thường dùng để biểu diễn chuỗi kết quả, không phải một text block nữa. Nếu dùng `String.equals` so hai giá trị, kết quả là `true`.

### 3.2. Vị trí closing delimiter có ý nghĩa

Hai cách đặt `"""` tạo kết quả khác nhau:

```java
String withFinalLf = """
        alpha
          beta
        """;

String withoutFinalLf = """
        alpha
          beta""";
```

- `withFinalLf` bằng `"alpha\n  beta\n"` — có LF cuối.
- `withoutFinalLf` bằng `"alpha\n  beta"` — không có LF cuối.

Bản thứ hai đưa closing delimiter lên **ngay cuối dòng `beta`**, khiến nội dung không bao gồm ký tự LF sau `beta`. Nó không dùng `trim()` hay `stripTrailing()` nên không vô tình xóa những khoảng trắng có chủ đích khác.

**Không suy ra text block luôn có LF cuối.** Kết quả phụ thuộc vị trí closing delimiter và escape continuation.

### 3.3. Chọn mức thụt lề có chủ đích

```java
String leading = """
            first
              second
        """;
```

Dòng closing delimiter ở mức 8 spaces; dòng nội dung đầu ở mức 12 spaces. Bốn spaces thêm trước `first` sẽ được **giữ** trong String, sáu spaces trước `second` cũng giữ.

Kết quả:

```java
"    first\n      second\n"
```

**Chú ý:** Trong một text block, dấu cách bạn thêm trước closing delimiter có thể đổi **lượng indentation bị xóa**. Không di chuyển closing delimiter chỉ để nhìn «đẹp» mà không chạy lại kiểm thử chuỗi chính xác.

## 4. Thực hành chính: tạo mẫu thông báo nhiều dòng có khoảng trắng

**Yêu cầu đầu ra:**

- Dòng thứ nhất: `THÔNG BÁO`.
- Dòng thứ hai: `Mã: A-17`.
- Dòng thứ ba: **rỗng**.
- Dòng thứ tư: **hai dấu cách đầu dòng** rồi `Nội dung: Xong`.
- Dòng thứ năm: `Kết thúc.`.
- Sau dòng cuối: **một LF**.
- Không có tabs hoặc spaces thừa ngoài những gì đã chỉ định.
- Mã và nội dung được truyền vào template qua `.formatted(...)`.

### 4.1. Chương trình Java chạy độc lập

Lưu file **`NoticeTemplateDemo.java`**:

```java
public final class NoticeTemplateDemo {
    public static void main(String[] args) {
        String pattern = """
                THÔNG BÁO
                Mã: %s

                  Nội dung: %s
                Kết thúc.
                """;

        String actual = pattern.formatted("A-17", "Xong");

        String expected = "THÔNG BÁO\n"
                + "Mã: A-17\n"
                + "\n"
                + "  Nội dung: Xong\n"
                + "Kết thúc.\n";

        if (!actual.equals(expected)) {
            throw new AssertionError("Incorrect whitespace");
        }

        System.out.println("text-equal=true");
        System.out.println("has-final-lf=" + actual.endsWith("\n"));
        System.out.println("has-blank-line=" + actual.contains("\n\n"));
        System.out.println("line-count=" + actual.lines().count());
    }
}
```

Chạy với **JDK 17+** (UTF-8 source):

```bash
javac --release 17 -encoding UTF-8 -Xlint:text-blocks NoticeTemplateDemo.java
java NoticeTemplateDemo
```

**Stdout chính xác:**

```text
text-equal=true
has-final-lf=true
has-blank-line=true
line-count=5
```

Ví dụ đã được biên dịch và chạy thử trên JDK hiện hành với `--release 17`.

### 4.2. Vì sao đây là kiểm thử khoảng trắng thật?

Đoạn `expected` được viết **độc lập với text block** bằng các literal `\n` và hai spaces rõ ràng. Nếu vô tình:

- Thêm một space trước `THÔNG BÁO`;
- Mất một trong hai spaces trước `Nội dung`;
- Bỏ dòng trống giữa `Mã` và `Nội dung`;
- Chuyển closing delimiter khiến mất LF cuối;

thì `actual.equals(expected)` trở thành `false` và chương trình ném `AssertionError`. Đây là kiểm thử chặt chẽ hơn `System.out.println(actual)`, vì terminal rất dễ che dấu spaces/tab cuối dòng.

### 4.3. Vì sao `line-count=5` dù chuỗi kết thúc bằng LF?

`String.lines()` tạo stream của những dòng nội dung, **không tạo một dòng rỗng bổ sung chỉ vì string kết thúc bằng một line terminator**. Trong mẫu này có năm dòng: hai dòng đầu, một dòng rỗng ở giữa, và hai dòng cuối.

Ví dụ:

```java
long lines = "A\nB\n".lines().count();      // 2
int parts = "A\nB\n".split("\n", -1).length; // 3
```

`split` với limit `-1` giữ **phần rỗng ở cuối**, nên có ba phần tử. Đừng dùng `lines().count()` để suy ra chuỗi có/không có LF cuối; kiểm tra trực tiếp `endsWith("\n")`.

### 4.4. Khi đổi dữ liệu trong `formatted`

`String.formatted(Object...)` thay các placeholders `%s`, `%d`,... giống `String.format`. Bản thân nó không đổi thụt lề/line endings của template nếu giá trị chèn vào không chứa ký tự điều khiển.

Ví dụ chèn `"Xong\nMới"` vào `%s` sẽ tạo **thêm dòng** trong output. Nếu dữ liệu đầu vào có thể chứa newline, cần quyết định có cho phép nhiều dòng hay phải validate/escape trước khi format.

**Bảo mật và tính đúng:** `formatted` không tự escape SQL/HTML/JSON. Với SQL, dùng `PreparedStatement`; với JSON dùng serializer; với HTML dùng escaping phù hợp. Text block chỉ tạo String đẹp ở source, không thay các biện pháp an toàn theo ngữ cảnh.

## 5. Cách kiểm tra từng ký tự khoảng trắng

So sánh `actual.equals(expected)` là điều kiện quyết định, nhưng khi fail, cần biết sai ở đâu. Một helper có thể biểu diễn dấu cách, tab, carriage return và line feed bằng ký hiệu nhìn thấy:

```java
static String visible(String text) {
    return text.replace(" ", "·")
               .replace("\t", "⇥")
               .replace("\r", "␍")
               .replace("\n", "␊\n");
}
```

Đây là **một method** để đặt trong class, không phải file hoàn chỉnh. Ký hiệu:

| Ký hiệu | Ý nghĩa trong output chẩn đoán |
| --- | --- |
| `·` | Một space thật (`U+0020`) |
| `⇥` | Một tab (`U+0009`) |
| `␍` | Một CR (`U+000D`) |
| `␊` | Một LF (`U+000A`), helper chèn thêm xuống dòng chỉ để hiển thị |

Ví dụ chuỗi `"A  \n\tB\n"` khi hiển thị sẽ nhìn thấy hai dấu `··` trước LF, một tab trước chữ B và một LF ở cuối. Trong bài thực hành, helper chỉ dùng để **in thông báo lỗi**, không thay đổi String đem so sánh.

### 5.1. `String.equals`, `length` và so từng vị trí

Nếu muốn xác định vị trí lệch chính xác:

```java
static void assertExact(String label, String actual, String expected) {
    if (actual.equals(expected)) return;

    int limit = Math.min(actual.length(), expected.length());
    int first = 0;
    while (first < limit &&
           actual.charAt(first) == expected.charAt(first)) {
        first++;
    }
    throw new AssertionError(
        label + ": firstDifferenceUTF16Index=" + first
        + ", expectedLength=" + expected.length()
        + ", actualLength=" + actual.length());
}
```

Đây là snippet đặt trong class. `String.length()` và `charAt` đo theo **UTF-16 code units**; với ký tự nằm ngoài BMP như emoji, một code point có thể chiếm hai units. Với bài tập spaces/LF/tab thông thường, cách này vẫn hữu ích. Nếu muốn chẩn đoán ký tự Unicode nâng cao, dùng `codePoints()`.

**Không so String bằng `==`** để kiểm tra giá trị. `==` kiểm tra object identity; dù hai literals có thể được intern, điều đó không thay thế `equals` để so nội dung generated template.

## 6. Bộ kiểm thử tổng hợp 17 tình huống — không cần thư viện ngoài

Để kiểm tra độc lập mọi quy tắc, chúng ta dùng **một file Java đầy đủ**. Từng phép `check` so chính xác String; `count` kiểm tra hành vi các API đếm dòng. Khi bất kỳ case nào sai, chương trình ném `AssertionError` với biểu diễn khoảng trắng rõ ràng.

Lưu file **`TextBlockWhitespaceLab.java`**:

```java
public final class TextBlockWhitespaceLab {
    static int checks = 0;

    static String visible(String text) {
        return text.replace(" ", "·").replace("\t", "⇥")
                   .replace("\r", "␍").replace("\n", "␊\n");
    }

    static void check(String label, String actual, String expected) {
        if (!actual.equals(expected)) {
            throw new AssertionError(label + "\nexpected: "
                    + visible(expected) + "\nactual: " + visible(actual));
        }
        checks++;
        System.out.println("PASS " + label + " length=" + actual.length());
    }

    static void count(String label, long actual, long expected) {
        if (actual != expected) {
            throw new AssertionError(label + ": " + actual + " != " + expected);
        }
        checks++;
        System.out.println("PASS " + label + " count=" + actual);
    }

    public static void main(String[] args) {
        String regular = """
                alpha
                  beta
                """;
        check("regular", regular, "alpha\n  beta\n");

        String noFinalLf = """
                alpha
                  beta""";
        check("no-final-lf", noFinalLf, "alpha\n  beta");

        String keepTrailing = """
                key:\s\s
                value\t\s
                """;
        check("escape-trailing", keepTrailing, "key:  \nvalue\t \n");

        String joined = """
                left\
                right
                """;
        check("continuation", joined, "leftright\n");

        String leading = """
                    first
                      second
                """;
        check("essential-indent", leading, "    first\n      second\n");

        String blank = """
                one

                three
                """;
        check("blank-line", blank, "one\n\nthree\n");

        String replace = """
                x$$
                """.replace('$', ' ');
        check("substitute-trailing", replace, "x  \n");

        String fence = """
                left···|
                right|
                """.replace("|\n", "\n").replace('·', ' ');
        check("fence-trailing", fence, "left   \nright\n");

        String tab = """
                A\tB
                """;
        check("tab", tab, "A\tB\n");

        String embedded = """
                say "hi"
                """;
        check("quote", embedded, "say \"hi\"\n");

        String formatted = """
                User: %s
                Score: %d
                """.formatted("Ada", 3);
        check("formatted", formatted, "User: Ada\nScore: 3\n");

        String translated = "a\\sb\\n".translateEscapes();
        check("translate-escapes", translated, "a b\n");

        String noFinal = "    red\n      blue".stripIndent();
        check("strip-indent-no-lf", noFinal, "red\n  blue");

        String withFinal = "    red\n      blue\n".stripIndent();
        check("strip-indent-with-lf", withFinal,
                "    red\n      blue\n");

        String addIndent = "A\nB".indent(2);
        check("indent-adds-lf", addIndent, "  A\n  B\n");

        count("lines-count", "A\nB\n".lines().count(), 2);
        count("split-preserve-trailing",
              "A\nB\n".split("\n", -1).length, 3);

        System.out.println("ALL_PASS=" + checks);
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 -Xlint:text-blocks TextBlockWhitespaceLab.java
java TextBlockWhitespaceLab
```

**Stdout chính xác khi mọi case đều PASS:**

```text
PASS regular length=13
PASS no-final-lf length=12
PASS escape-trailing length=15
PASS continuation length=10
PASS essential-indent length=23
PASS blank-line length=11
PASS substitute-trailing length=4
PASS fence-trailing length=14
PASS tab length=4
PASS quote length=9
PASS formatted length=19
PASS translate-escapes length=4
PASS strip-indent-no-lf length=10
PASS strip-indent-with-lf length=19
PASS indent-adds-lf length=8
PASS lines-count count=2
PASS split-preserve-trailing count=3
ALL_PASS=17
```

Bộ mã đã được biên dịch/chạy thử trên JDK hiện hành với `--release 17`. Toàn bộ **17 phép kiểm tra** đều PASS; lệnh biên dịch không cần một dependency ngoài JDK.

### 6.1. Điều gì xảy ra khi một phép kiểm tra thất bại?

Giả sử người học vô ý làm mất một space trong `"    first\n      second\n"` hoặc dịch chuyển closing delimiter. `check` gọi `equals` và ném `AssertionError`, trong đó helper `visible` chỉ ra số lượng spaces bằng dấu chấm giữa `·`.

Đây là mục tiêu của bài: **thay một kiểm tra bằng mắt không đáng tin bằng kiểm tra byte/character-level**. Với dữ liệu có ký tự Unicode bổ sung, có thể mở rộng sang code points; với file đầu ra, kiểm tra actual bytes và encoding.

### 6.2. Vì sao assert `length` cũng đáng quan tâm?

`length` giúp phát hiện khác biệt nhỏ ngay khi terminal hiển thị gần như giống nhau:

- `"alpha\n  beta\n"` có độ dài **13** UTF-16 units.
- `"alpha\n  beta"` có độ dài **12**.
- Hai space ở cuối dòng `key:` đều được tính trong `length=15` của `keepTrailing`.
- `\t` là **một ký tự tab**, không phải 4 hoặc 8 dấu cách, nên length của `"A\tB\n"` là **4**.

**Giới hạn:** Hai String khác nhau vẫn có thể cùng length; vì vậy `length` chỉ là diagnostic phụ. Kiểm thử chính vẫn là `equals`.

## 7. Khoảng trắng đầu dòng: incidental và essential

Về mặt compiler, `"""` không chỉ «copy nguyên xi» mọi dấu cách trong source. Nó xác định một **common indent** dựa trên các dòng có nội dung cùng dòng closing delimiter rồi loại phần incidental.

Ví dụ hình dung bằng dấu `·` thay cho space trong phần mô tả:

```text
Source (dấu · chỉ để nhìn, không đặt vào code thật):
········alpha
··········beta
········"""

Sau khi loại 8 spaces chung:
alpha
··beta
```

**Quy tắc thực hành:**

1. Đặt closing delimiter ở cùng mức thụt lề với các content lines «ít thụt nhất» nếu muốn phần nội dung bắt đầu tại cột 0.
2. Thụt **content lines vào sâu hơn closing delimiter** nếu muốn giữ khoảng trắng đầu dòng thực trong result.
3. Giữ toàn bộ indent bằng spaces hoặc toàn bộ bằng tabs nhất quán; **không trộn** tùy tiện.
4. Sau khi chỉnh code formatting, chạy test vì autoformatter có thể di chuyển delimiter hoặc nội dung.

### 7.1. Dòng trống và thụt lề

```java
String blank = """
        one

        three
        """;
```

Kết quả là `"one\n\nthree\n"`. Dòng trống ở giữa **vẫn tồn tại**; nó đóng góp một LF. Nếu dòng trống trong source chỉ chứa vài dấu cách incidental, phần dấu cách ấy bị loại bỏ theo quy tắc text block.

Một dòng blank có chứa non-whitespace marker, như `|`, lại là dòng có nội dung và có thể ảnh hưởng indent threshold. Đây là lý do mẹo **character fence** cần được kiểm tra thực tế thay vì suy đoán.

## 8. Khoảng trắng cuối dòng: vì sao không nên gõ space thật?

Text blocks coi trailing whitespace trên mỗi line là incidental và compiler loại bỏ nó. Điều này giúp code không bị thay đổi ngầm khi IDE auto-trim spaces cuối dòng, nhưng gây khó chịu nếu giao thức cần giữ spaces.

### 8.1. Giữ space bằng `\s` — cách nên ưu tiên khi cần rõ ý

```java
String keep = """
        key:\s\s
        value\t\s
        """;
```

Kết quả là:

```java
"key:  \nvalue\t \n"
```

Giải thích:

- `\s` tạo **một space** `U+0020` tại bước dịch escape.
- `\s\s` tạo **hai spaces** ở cuối dòng `key:`.
- `\t` tạo một tab, và `\s` theo sau tạo một space ở cuối dòng `value`.
- Những escape này được xử lý **sau** incidental stripping nên các spaces được bảo toàn.

**Lưu ý:** Ký hiệu `\s` trong Java text block là một escape mang giá trị **space đơn**, khác `\\s` là hai ký tự `\` và `s` trong runtime (thường dùng khi biểu diễn regex whitespace token).

### 8.2. Octal space `\040`

Java vẫn hỗ trợ octal escape `\040` biểu diễn space `U+0020`. Đây không phải cách bắt buộc; khi đọc template, `\s` thường dễ hiểu hơn.

```java
String keep = """
        value\040\040
        """;
```

Giá trị bằng `"value  \n"`. Hai ký tự spaces được tạo ở bước dịch escapes, sau khi compiler đã quyết định loại trailing spaces thật.

**Không dùng `\u0020` để thay cho `\s`.** Unicode escapes của Java được xử lý rất sớm trong quá trình đọc source, trước quá trình xác định text block/loại khoảng trắng incidental; kết quả có thể lại trở thành trailing space bị xóa.

### 8.3. Thay thế ký tự có chủ đích

```java
String keep = """
        x$$
        """.replace('$', ' ');
```

Kết quả `"x  \n"`. Cách này hữu ích khi một template dùng ký hiệu tạm để thể hiện vị trí dấu cách.

**Rủi ro:** Nếu `$` còn có ý nghĩa thực trong dữ liệu, `replace('$',' ')` sẽ thay cả những ký tự không phải placeholders. Hãy chọn marker không xuất hiện trong nội dung thực, hoặc dùng cách thay thế có scope rõ.

### 8.4. «Character fence» ở cuối dòng

```java
String keep = """
        left···|
        right|
        """.replace("|\n", "\n").replace('·', ' ');
```

Trong ví dụ, dấu `·` là **ký tự có thật trong source demo**, không phải spaces vô hình. Kết quả chính xác là `"left   \nright\n"`.

- `|` giúp giữ marker ở cuối content line khi compiler xử lý trailing whitespace.
- `replace("|\n","\n")` loại fence nằm ngay trước LF.
- `replace('·',' ')` tạo ba spaces cuối dòng như kỳ vọng.

Cũng như mọi cách dùng marker thay thế, phải bảo đảm marker không nằm trong dữ liệu tự nhiên. Với trường hợp chỉ cần một vài spaces, `\s` dễ đọc hơn.

## 9. Nối dòng bằng escape `\`

Text block hỗ trợ một **backslash ngay trước line terminator** để bỏ newline tại vị trí ấy:

```java
String joined = """
        left\
        right
        """;
```

Kết quả là `"leftright\n"` — **không** có dấu cách hoặc LF giữa `left` và `right`. Nếu muốn có một space giữa hai từ, cần chỉ định nó bằng một ký tự nội dung hợp lệ, ví dụ thêm `\s` trước chỗ nối dòng sau khi kiểm chứng kết quả.

### 9.1. Phân biệt `\n` và continuation

| Source | Ý nghĩa |
| --- | --- |
| Gõ newline bình thường trong text block | Tạo một LF trong String, sau chuẩn hóa line terminator. |
| `\n` | Escape Java tạo LF, dù xuất hiện trong cùng một dòng source. |
| `\` ngay trước newline | **Xóa** line terminator đó, nối nội dung với dòng tiếp theo. |
| `\s` | Tạo một space sau incidental whitespace removal. |
| `\t` | Tạo một tab. |

**Cẩn thận khi dùng continuation:** Không thêm space hoặc ký tự sau dấu backslash trước newline nếu muốn nó thật sự là escape nối dòng. Khi format/linter tự thay đổi dòng, hãy chạy lại test.

### 9.2. Bỏ LF cuối bằng continuation

Ngoài việc đặt closing delimiter trên cùng dòng cuối, có thể dùng:

```java
String withoutFinal = """
        red
        green
        blue\
        """;
```

Kết quả là `"red\ngreen\nblue"`. Continuation giúp closing delimiter nằm trên dòng riêng nhưng không làm sinh LF cuối. Đây là cách rõ ràng khi template style yêu cầu giữ delimiter riêng mà wire format không cần newline sau nội dung.

## 10. Line endings: CRLF, CR và LF

Một file `.java` trên Windows có thể dùng CRLF, trên Linux thường dùng LF. Java text blocks **chuẩn hóa** terminators trong nội dung thành **LF** `\n`, vì vậy text block giống nhau có thể tạo cùng String trên cả hai hệ điều hành.

Ví dụ:

```java
String text = """
        red
        green
        """;
```

Giá trị mong muốn là `"red\ngreen\n"` dù line endings của source file là CRLF hay LF.

**Không nhầm** với việc ghi file: `Files.writeString(path, text)` ghi đúng các ký tự trong String (theo charset đã chọn), nó không tự đổi LF thành CRLF chỉ vì đang chạy trên Windows.

Khi một hệ thống bên ngoài thực sự yêu cầu CRLF, chuyển đổi **có chủ đích**:

```java
String crlf = text.replace("\n", "\r\n");
```

Đây là snippet trong method. Nó chỉ nên dùng khi giao thức quy định CRLF; không nên thay mọi LF thành `System.lineSeparator()` nếu dữ liệu cần format ổn định, ví dụ tests hoặc giao thức byte-level dùng LF.

### 10.1. Dùng test để tránh lỗi qua nền tảng

So sánh literal expected có `\n` sẽ đáng tin hơn phụ thuộc `System.lineSeparator()` khi đánh giá **giá trị của text block**. Nếu user-facing console hoặc OS-specific file cần separator khác, kiểm thử tầng xuất file riêng.

### 10.2. Kiểm tra bytes khi bắt buộc chính xác

`String.equals` xác minh các ký tự Java. Nếu có yêu cầu file phải đúng bytes UTF-8, kiểm tra thêm:

```java
byte[] actualBytes = actual.getBytes(java.nio.charset.StandardCharsets.UTF_8);
byte[] expectedBytes = expected.getBytes(java.nio.charset.StandardCharsets.UTF_8);

if (!java.util.Arrays.equals(actualBytes, expectedBytes)) {
    throw new AssertionError("UTF-8 bytes mismatch");
}
```

Đoạn này là snippet trong method có `String actual, expected`, không phải file tự chạy. Lưu ý Unicode có thể có các biểu diễn ký tự tổ hợp/normalization khác nhau; byte comparison chặt hơn mắt thường.

## 11. Tabs và trộn indentation

Một ký tự tab là **một ký tự trong String**, không phải 2, 4 hoặc 8 spaces. Text block incidental-indent algorithm đếm mỗi whitespace character theo đơn vị ký tự, không đo độ rộng hiển thị trên editor.

Nếu source có một dòng bắt đầu bằng bốn spaces và dòng khác bắt đầu bằng một tab (hiển thị rộng bốn spaces), algorithm không nhất thiết coi chúng là cùng mức indent. Điều này gây ra String runtime lệch thụt lề dù nhìn trên IDE tưởng tương đương.

Ví dụ dùng escape để có tab rõ ràng:

```java
String tab = """
        A\tB
        """;
```

Kết quả `"A\tB\n"`, `String.length()==4`. Test kiểm tra một tab thật thay vì số spaces hiển thị.

**Khuyến nghị:** Với source text blocks, dùng **một loại ký tự indent nhất quán** (thường là spaces) và cấu hình IDE/formatter thống nhất cho cả đội.

## 12. Công cụ `javac -Xlint:text-blocks`

Java compiler có lint category dành cho text blocks:

```bash
javac --release 17 -encoding UTF-8 -Xlint:text-blocks TextBlockWhitespaceLab.java
```

Một số tình huống có thể bị cảnh báo:

- **Trailing whitespace will be removed:** Dòng text block có spaces/tab cuối mà compiler sẽ loại bỏ.
- **Inconsistent white space indentation:** Độ thụt lề trộn spaces/tabs tạo kết quả không nhất quán.

Bạn có thể dùng `-Werror` trong build khi muốn warnings làm build thất bại:

```bash
javac --release 17 -encoding UTF-8 \
      -Xlint:text-blocks -Werror TextBlockWhitespaceLab.java
```

**Phân biệt:** `-Xlint:text-blocks` hỗ trợ tìm một số lỗi. Nó **không chứng minh** template có đúng tất cả dấu cách, dòng rỗng và LF cuối. **Bộ test `equals` vẫn bắt buộc** đối với format có contract chặt.

### 12.1. Ví dụ cố ý sai (chỉ để hiểu warning)

Giả sử dòng `"hello"` có ba dấu cách **thật** sau chữ o trước line terminator:

```text
String example = """
    hello···
    """;
```

Trong đoạn hiển thị này, `·` chỉ là ký hiệu minh họa để thấy ba spaces, **không phải source Java thật**. Nếu gõ ba spaces thật vào cuối dòng text block, compiler có thể xóa chúng và `-Xlint:text-blocks` có thể cảnh báo. Cách sửa là viết `hello\s\s\s` nếu cần giữ chúng, thay vì cấm IDE trim trailing spaces.

### 12.2. Không dùng compiler warning làm phép đo output

Một chương trình có thể không có warning nào nhưng vẫn sai yêu cầu nghiệp vụ, ví dụ:
- Thiếu dòng trống;
- Thêm một space ở đầu `Mã:`;
- Bỏ LF cuối;
- Nối hai dòng nhầm bằng continuation;
- Dùng %s sai vị trí;
- Trộn String có CRLF bên ngoài với text block LF.

Những sai sót này chỉ rõ khi bạn so actual/expected, nên cần cả static diagnostics và runtime assertions.

## 13. `stripIndent()`, `indent()`, `translateEscapes()`: dùng đúng semantics

Text blocks đã được compiler xử lý indentation và escapes trong lúc biên dịch. Các String methods vẫn hữu ích khi xử lý **dữ liệu lấy từ bên ngoài**, nhưng đừng gọi một method nữa chỉ vì tưởng text block chưa được xử lý.

### 13.1. `String.stripIndent()`

`stripIndent()` loại incidental indentation khỏi một String tại runtime, nhưng cần chú ý **trạng thái dòng cuối**.

Các tests đã chạy:

```java
String noFinal = "    red\n      blue".stripIndent();
boolean a = noFinal.equals("red\n  blue");     // true

String withFinal = "    red\n      blue\n".stripIndent();
boolean b = withFinal.equals("    red\n      blue\n"); // true
```

**Chi tiết quan trọng:** Khi String đầu vào **kết thúc bằng line terminator**, dòng rỗng cuối có thể đưa ngưỡng incidental indent về **0**. Trên JDK hiện hành, chuỗi `"    red\n      blue\n"` trong ví dụ không mất common indentation khi gọi `stripIndent()`. Khi **không** có LF cuối, common indent 4 được loại bỏ.

Tại sao không mâu thuẫn với text block? Compiler xét **nội dung text block và vị trí closing delimiter** theo quy tắc ngôn ngữ trước khi tạo String. Không được suy luận «gọi `stripIndent()` trên mọi String đã có LF cuối sẽ cho đúng kết quả compiler tạo từ source text block có closing delimiter thụt lề».

**Khuyến nghị:** Nếu data đã là text block literal, đừng thêm `stripIndent()` như một thao tác «mặc định». Nếu đọc từ file, hãy xác định và kiểm thử chính xác trường hợp có/không LF cuối.

### 13.2. `String.indent(int)`

`indent(2)` thêm hai spaces vào đầu **mỗi dòng** của String. Nó có thể **thêm LF cuối** dù input không có final LF:

```java
String added = "A\nB".indent(2);
boolean ok = added.equals("  A\n  B\n"); // true
```

Đây là lý do `indent` không tương đương với việc chỉ thêm spaces trước hai dòng nhìn thấy, nhất là với các giao thức yêu cầu không có newline cuối.

`indent(-2)` có thể giảm tối đa hai indentation characters ở đầu mỗi dòng; không đảm bảo loại đúng một chuỗi prefix đặc biệt. Kiểm thử kết quả nếu có tabs.

### 13.3. `String.translateEscapes()`

Method này dịch các escape sequences trong **một String chứa backslashes thực**:

```java
String encoded = "a\\sb\\n";
String translated = encoded.translateEscapes();

boolean ok = translated.equals("a b\n"); // true
```

Ở `encoded`, `\\` biểu diễn backslash trong một Java string literal. Vì vậy runtime có các ký tự `a`, `\`, `s`, `b`, `\`, `n`. `translateEscapes()` chuyển `\s` thành space và `\n` thành LF.

**Không gọi `translateEscapes()` lần nữa lên text block đã có escapes được compiler dịch**, trừ khi dữ liệu chứa backslash sequences từ nguồn bên ngoài và đó thật sự là định dạng muốn chuyển. Gọi lại trên chuỗi JSON/regex/path có backslash cũng có thể làm hỏng nội dung nếu không đúng mục đích.

### 13.4. `String.formatted(...)`

`String.formatted(Object...)` trả String sau thay placeholders tương tự `String.format`. Nó đặc biệt tiện khi dùng text block:

```java
String result = """
        User: %s
        Score: %d
        """.formatted("Ada", 3);
```

Kết quả là `"User: Ada\nScore: 3\n"` (độ dài 19), đã được kiểm tra trong bộ test.

Nếu template cần **dấu phần trăm literal**, trong định dạng `String.format` dùng `%%`, ví dụ `"90%%"` để ra `"90%"`. Nếu source chứa `%s` nhưng dữ liệu thay vào không hợp lệ theo format, có thể ném exception định dạng; cần test những placeholder mà bạn thực sự dùng.

## 14. Thế nào là một bài test whitespace đáng tin?

Một bộ test có chất lượng nên kiểm các thuộc tính sau:

| Kiểu lỗi | Assertion phù hợp |
| --- | --- |
| Thừa/thiếu spaces đầu dòng | `assertExact(actual, expected)` hoặc `String.equals` |
| Spaces cuối dòng bị mất | Expected chứa `"x  \n"`, test chính xác |
| Nhầm tab với spaces | Expected chứa `\t` hoặc kiểm `charAt` |
| Thiếu LF cuối | `actual.endsWith("\n")` + `equals` |
| Dòng rỗng bị bỏ | `actual.contains("\n\n")` + `equals` |
| Dùng CRLF ngoài ý muốn | So exact String hoặc kiểm `\r` |
| Sai chuẩn hóa source line endings | Test dưới Linux/Windows hoặc fixture nguồn dùng CRLF |
| Template chèn dữ liệu có newline | Test input chứa `\n`, áp validation/escaping theo hợp đồng |
| Trim quá tay | Test chuỗi có spaces intentional, so với expected |
| Số dòng khác dự kiến | `lines().count()`, nhưng kiểm final newline riêng |
| Hidden Unicode mismatch | So code points hoặc UTF-8 bytes khi cần |
| Source có mixed tabs/spaces | `-Xlint:text-blocks` và code review |

### 14.1. Golden sample và kiểm tra output file

Nếu template dùng cho e-mail, báo cáo hoặc file, một cách test mạnh là **golden string/file** đã được xét duyệt. Tránh tạo expected bằng chính phép biến đổi của actual vì sẽ làm test mất tác dụng.

Ví dụ **kém**:

```java
String expected = actual.stripIndent();
if (actual.stripIndent().equals(expected)) {
    // Test này luôn đúng theo cách xây expected, không kiểm ý nghĩa.
}
```

Ví dụ **đúng hơn**: Viết expected độc lập như `NoticeTemplateDemo`; kiểm cả nội dung, LF và spaces. Nếu cần verify file bytes, so UTF-8 bytes với fixture có line endings được kiểm soát.

### 14.2. Không dựa vào `println` để nhìn LF cuối

`System.out.println(actual)` **tự thêm một line separator sau chuỗi**, nên dù `actual` không chứa final LF, console vẫn xuống dòng. Nếu `actual` có LF cuối, `println` còn có thể tạo một dòng trống phụ.

**Để kiểm tra chính xác** dùng `actual.endsWith("\n")`, `actual.length()` và `String.equals`; đừng chỉ quan sát terminal.

## 15. Trường hợp thực tế và các lưu ý an toàn

### 15.1. JSON mẫu

Text block phù hợp để viết JSON **tĩnh** trong unit tests:

```java
String json = """
        {
          "name": "Ada",
          "active": true
        }
        """;
```

Dấu `"` trong JSON không cần escape như trong literal bình thường. Tuy vậy, text block **không validate JSON** và không tự escape các chuỗi dữ liệu runtime. Nếu tạo JSON từ input bên ngoài, dùng JSON serializer/library đúng tiêu chuẩn thay vì ghép trực tiếp với `.formatted`.

### 15.2. SQL nhiều dòng

```java
String sql = """
        SELECT id, name
        FROM customer
        WHERE status = ?
        ORDER BY id
        """;
```

Chuỗi này tiện đọc, nhưng vẫn cần `PreparedStatement` để bind values. **Không chèn dữ liệu người dùng trực tiếp bằng `formatted` vào SQL** vì text block không chống SQL injection.

### 15.3. HTML/template email

Nội dung HTML nhiều dòng hoặc email template có thể cần **spaces cuối dòng, dòng trống và line endings** theo giao thức. Với HTML, cần escape dữ liệu đầu vào theo context; với giao thức yêu cầu CRLF, chuyển line endings có chủ đích khi xuất. Text block làm source dễ đọc nhưng không thay validator, sanitizer hoặc encoder.

### 15.4. Ví dụ Markdown

Markdown có quy tắc riêng đối với trailing spaces: hai spaces cuối một dòng đôi khi được dùng để tạo hard line break. Trong text block, hai spaces thật cuối dòng có thể bị compiler loại bỏ. Nếu bắt buộc giữ chúng, dùng `\s\s` và thêm assertion:

```java
String markdown = """
        line one\s\s
        line two
        """;

boolean ok = markdown.equals("line one  \nline two\n");
```

Đây là snippet trong method; kết quả `ok=true`. **Không** thay `\s\s` bằng việc gõ hai dấu space vô hình vào cuối dòng Java source.

### 15.5. Mẫu dùng backslashes

Một số đoạn mã như đường dẫn Windows hoặc regex cần backslash thật. Text blocks vẫn áp dụng **Java escape sequences**, nên ví dụ regex chứa `\d` không được đặt nguyên như một Java escape không hợp lệ; dùng `\\d` để có dấu backslash trong runtime, hoặc thiết kế escaping đúng theo định dạng đích.

**Đừng nhầm text block với raw string literal.** Text block chỉ giảm một số escaping khi chứa nhiều dấu ngoặc kép/newlines, **không bỏ toàn bộ quy tắc escape Java**.

## 16. Lỗi thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Đặt nội dung ngay sau `"""` mở | Ngữ pháp yêu cầu line terminator sau opening delimiter | Đưa nội dung xuống dòng kế |
| Cho rằng text block «copy nguyên mọi space» | Compiler loại incidental indentation/trailing spaces | Viết expected string độc lập, kiểm `equals` |
| Đếm spaces trong editor thay vì runtime | Tabs có độ rộng hiển thị khác nhau | Dùng `visible()`, `charAt`, `-Xlint:text-blocks` |
| Đổi vị trí closing delimiter mà không test | Có thể thay mức common indent hoặc final LF | Chạy lại whitespace tests |
| Coi LF cuối là không đáng kể | Exact file/protocol có thể phân biệt | Test `endsWith("\n")` và expected string |
| Gõ hai spaces thật ở cuối dòng | Compiler có thể loại bỏ | Dùng `\s\s` hoặc `\040\040` |
| Dùng `\u0020` để giữ trailing spaces | Unicode escape xử lý trước stripping | Dùng `\s` |
| Dùng `\` nối dòng rồi mong vẫn có LF | Continuation bỏ newline | Test exact expected |
| Gọi `stripIndent` lên mọi String | Có thể thay dữ liệu có chủ đích, khác nhau theo final LF | Chỉ gọi khi hợp đồng yêu cầu |
| Gọi `stripTrailing` để bỏ final LF | Có thể xóa thêm trailing spaces nội dung | Chọn closing delimiter/continuation phù hợp |
| Dùng `String.lines().count()` để kiểm LF cuối | Không tạo dòng cuối rỗng từ terminal LF | Dùng `endsWith` |
| So String bằng `==` | Kiểm identity, không kiểm content | Dùng `equals` |
| Chỉ nhìn `println` để xác minh spaces | Terminal che spaces/tab; println thêm newline | Dùng assertions và visible diagnostic |
| Dùng `String.formatted` cho input SQL trực tiếp | Không escape/bind dữ liệu | Dùng `PreparedStatement` |
| Dùng text block cho JSON động không escape | Không tự serialize JSON | Dùng JSON library |
| Quên kiểm source encoding | Dấu tiếng Việt có thể lỗi bytes khi compile/build | Dùng UTF-8 và `-encoding UTF-8` |
| Tin `-Xlint:text-blocks` bắt mọi lỗi | Linter chỉ phát hiện một số vấn đề lexical | Bổ sung exact-match unit tests |

## 17. Bài tập có đáp án

### Bài 1 — LF cuối

```java
String a = """
        one
        two
        """;

String b = """
        one
        two""";
```

Hai String có bằng nhau không?

**Đáp án:** Không. `a` bằng `"one\ntwo\n"`, `b` bằng `"one\ntwo"`. Chúng khác một LF cuối.

### Bài 2 — Common indent

```java
String s = """
        A
          B
        """;
```

String thực tế?

**Đáp án:** `"A\n  B\n"`. Common indent của content và closing delimiter bị xóa; hai spaces thêm trước B được giữ.

### Bài 3 — Giữ ba spaces cuối dòng

Bạn cần output `"X   \n"` nhưng editor luôn xóa trailing spaces. Viết text block thế nào?

**Đáp án:**

```java
String s = """
        X\s\s\s
        """;
```

`\s` được dịch thành space sau khi stripping, nên đủ ba spaces.

### Bài 4 — Dòng rỗng

```java
String s = """
        one

        two
        """;
```

Số LF trong kết quả?

**Đáp án:** **Ba**: sau `one`, sau dòng trống và sau `two`. String là `"one\n\ntwo\n"`.

### Bài 5 — Không muốn xuống dòng giữa hai từ

```java
String s = """
        left\
        right
        """;
```

**Đáp án:** `"leftright\n"`. Continuation bỏ LF giữa hai source lines.

### Bài 6 — LF hay CRLF?

Source file là CRLF trên Windows. Kết quả text block sử dụng LF hay CRLF?

**Đáp án:** Compiler chuẩn hóa line terminators của text block thành **LF**, không tự giữ CRLF từ source. Nếu giao thức yêu cầu CRLF, chuyển đổi khi xuất file có chủ đích.

### Bài 7 — Tab

```java
String s = """
        X\tY
        """;
```

`s.length()` bằng bao nhiêu?

**Đáp án:** **4**: `X`, tab, `Y`, LF. Tab là một ký tự chứ không phải nhiều spaces.

### Bài 8 — `stripIndent` với LF cuối

`"    red\n      blue".stripIndent()` và `"    red\n      blue\n".stripIndent()` có cùng output không?

**Đáp án:** Không. Trường hợp đầu thành `"red\n  blue"`, trường hợp hai trong ví dụ giữ `"    red\n      blue\n"` vì cuối chuỗi là LF và có một dòng cuối trống ảnh hưởng incidental indent. Đừng tự gọi `stripIndent` khi không biết input.

### Bài 9 — `String.lines()`

`"A\nB\n".lines().count()` là 2 hay 3?

**Đáp án:** **2**. Không có extra empty line chỉ vì terminal LF. `split("\n", -1)` lại giữ phần tử rỗng cuối và có ba phần tử.

### Bài 10 — Thay dữ liệu vào template

Một `%s` nhận giá trị `"line 1\nline 2"`. Output vẫn giữ nguyên số dòng?

**Đáp án:** Không. Giá trị có LF có thể tạo thêm dòng; nếu format cần cố định, validate/escape input trước khi gọi `formatted`.

### Bài 11 — Testing

Vì sao `actual.equals(actual.stripIndent())` không phải kiểm thử tốt về template kỳ vọng?

**Đáp án:** Nó chỉ so một biến thể của chính actual với actual, không xác định nội dung phải đúng những dòng nào. Cần một `expected` độc lập hoặc fixture đã chuẩn hóa.

### Bài 12 — Trailing spaces và Markdown

Muốn một line Markdown kết thúc hai spaces để tạo hard break. Nếu viết hai spaces thật trước newline trong text block có chắc được giữ không?

**Đáp án:** Không. Dùng `\s\s` và assert `"line  \n"`.

### Bài 13 — Dấu % literal

Text block đưa vào `formatted(...)` chứa `90%` thì cần thay đổi gì?

**Đáp án:** Dùng `90%%` trong format string để xuất literal `90%`, vì `%` là ký tự điều khiển format. Với dữ liệu không cần placeholders, không bắt buộc gọi `formatted`.

### Bài 14 — Output file bytes

Hai strings hiển thị giống nhau nhưng một chuỗi dùng CRLF, một dùng LF. `println` có giúp kiểm byte-level không?

**Đáp án:** Không. Dùng `String.equals` để phân biệt chars và so `getBytes(StandardCharsets.UTF_8)` khi hợp đồng là byte-level; kiểm encoding và line endings.

### Bài 15 — Kiểm tra lỗi sau autoformat

Sau khi IDE tự định dạng closing delimiter, test `actual.equals(expected)` fail. Nên bỏ test vì chỉ là «formatting»?

**Đáp án:** Không. Đối với text blocks, việc thay đổi delimiter indent/placement **có thể đổi String thật**. Hãy đọc visible diagnostic, xác định common indent và sửa source hoặc cập nhật expected **chỉ khi yêu cầu output đã thay đổi có chủ đích**.

## 18. Quy trình hoàn thành bài thực hành

1. Chọn một mẫu văn bản có **contract rõ**: dòng nội dung, số spaces đầu/cuối, blank lines và final newline.
2. Viết bản `expected` bằng literal `\n` và spaces rõ ràng hoặc fixture bytes độc lập.
3. Viết text block, đặt closing delimiter theo kế hoạch incidental indent.
4. Dùng `\s` nếu cần giữ spaces cuối dòng; dùng continuation nếu cần nối dòng.
5. Chỉ dùng `formatted` cho chỗ chèn biến; quyết định rõ việc cho phép input chứa newline.
6. Viết `actual.equals(expected)` và helper hiển thị spaces/tab/LF khi fail.
7. Thử trường hợp có/không final LF, blank line và tabs; kiểm `String.length()` như diagnostic phụ.
8. Biên dịch bằng `javac --release 17 -encoding UTF-8 -Xlint:text-blocks`.
9. Chạy `NoticeTemplateDemo` và `TextBlockWhitespaceLab`; kiểm đúng stdout và exit status.
10. Với file thực tế, kiểm UTF-8 bytes/CRLF nếu giao thức yêu cầu.
11. Nếu dùng JSON/SQL/HTML, áp serializer/parameter binding/escaping của định dạng đó.
12. Đưa các assertions vào CI để đổi source formatting không vô tình đổi output.

## 19. Tài liệu chính thức vẫn áp dụng

1. [JEP 378 — Text Blocks](https://openjdk.org/jeps/378): text blocks được finalize từ Java 15, quy trình xử lý whitespace/escape sequences và thiết kế ngôn ngữ.
2. [Oracle Java SE 25 — Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/25/text-blocks/index.html): cú pháp, delimiter, final LF, incidental/trailing whitespace, `\s`, line continuation, tabs, `-Xlint:text-blocks` và style guidance.
3. [Java SE 25 — JLS `3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6): quy trình chính thức **normalize line terminators → strip incidental whitespace → translate escapes**.
4. [Java SE 25 — JLS `3.10.7 Escape Sequences](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.7): `\s`, `\t`, `\n`, octal escapes và continuation.
5. [Java SE 25 — String API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): `equals`, `formatted`, `stripIndent`, `translateEscapes`, `indent`, `lines` và `split`.
6. [Java SE 25 — javac tool](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--release 17`, `-encoding UTF-8`, `-Xlint:text-blocks` và `-Werror`.
7. [Oracle Java SE 25 — Java Language Changes Summary](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-summary.html): xác nhận text blocks finalized Java 15, Java 14 ở trạng thái preview trong lịch sử.
8. [Java SE 25 — StandardCharsets.UTF_8](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html#UTF_8): mã hóa String thành bytes khi golden file có byte-level contract.

**Ghi nhớ cuối:** Text block là **String nhiều dòng có quy tắc whitespace rõ ràng**, không phải raw string vô điều kiện. Compiler có thể bỏ **common indent và trailing spaces**, giữ **essential indentation**, chuẩn hóa source CRLF thành LF và dịch `\s`/`\` ở bước cuối. Mỗi khi mẫu văn bản có yêu cầu khoảng trắng chính xác, hãy viết **expected string độc lập**, test **`equals`**, kiểm **LF cuối**, **dòng trống** và **spaces cuối dòng**, bật `-Xlint:text-blocks` và chạy kiểm thử trên Java 17+ trong CI.