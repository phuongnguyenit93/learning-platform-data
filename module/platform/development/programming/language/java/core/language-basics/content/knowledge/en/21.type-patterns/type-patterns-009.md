# Phân biệt tính năng chính thức với cú pháp preview theo phiên bản — Java 17+

## 1. Mục tiêu và quy tắc quan trọng nhất

Trong Java, **tính năng chính thức/ổn định** (*final, permanent language feature*) là cú pháp đã được đưa vào đặc tả ngôn ngữ của phiên bản phát hành. Nó dùng được khi biên dịch đúng phiên bản mà **không cần** `--enable-preview`.

**Tính năng preview** là chức năng ngôn ngữ đã có trong một bản JDK để lập trình viên thử nghiệm, nhưng **chưa trở thành cú pháp ổn định** ở phiên bản ấy. Khi biên dịch và chạy code preview, phải bật tùy chọn phù hợp với **JDK đang dùng**; cú pháp/semantics của preview còn có thể thay đổi trước khi được ổn định.

Ví dụ liên quan đến **mẫu kiểm tra kiểu** (*type patterns*):

~~~java
// Ổn định trong Java 17: pattern matching cho instanceof.
if (input instanceof String text) {
    System.out.println(text.length());
}
~~~

Nhưng:

~~~java
// Java 21 trở lên: pattern matching cho switch đã ổn định.
switch (input) {
    case String text when text.length() >= 5 -> System.out.println("LONG");
    default -> System.out.println("OTHER");
}
~~~

**Đoạn thứ hai KHÔNG biên dịch trong Java 17 ổn định**. Java 17 từng có pattern matching cho switch ở dạng **preview**, nhưng guard của preview Java 17 dùng cú pháp khác: `case String s && condition`, **không phải `when`**.

**Nguyên tắc:** Khi gặp cú pháp mới trên mạng, xác nhận đồng thời **(1) phiên bản JDK**, **(2) trạng thái final/preview tại phiên bản đó**, **(3) cờ biên dịch/chạy**, và **(4) cú pháp đúng của phiên bản**.

## 2. Bảng mốc phiên bản cần biết

| Tính năng | Trạng thái theo mốc liên quan | Ghi nhớ khi học Java 17+ |
|---|---|---|
| **Switch expression** với `case ->` và `yield` | Ổn định từ **Java 14** | Có thể dùng ngay trên JDK 17, không cần preview |
| **Pattern matching cho `instanceof`** | Ổn định từ **Java 16** | `o instanceof String s` hợp lệ trên JDK 17 |
| **Record class** | Ổn định từ **Java 16** | `record Point(int x, int y) {}` khác với record *pattern* |
| **Sealed classes** | Ổn định từ **Java 17** | Có thể dùng `sealed`/`permits` trên JDK 17 |
| **Pattern matching cho `switch`** | Preview qua các bản **Java 17–20**; ổn định từ **Java 21** | Không dùng switch type patterns như tính năng final của Java 17 |
| **Guard `when` trong pattern switch** | Xuất hiện ở phiên bản preview sau Java 17 (Java 19/20); ổn định cùng pattern switch ở **Java 21** | Java 17 preview dùng `&&` trong nhãn guarded pattern, không dùng `when` |
| **Record patterns** | Preview trước Java 21; ổn định từ **Java 21** | Đừng nhầm `record` đã ổn định trong Java 17 với destructuring pattern của record |

**Cảnh báo quan trọng:** Một tính năng có thể là **preview ở phiên bản A** nhưng đã **final ở phiên bản B**. Không thể nói chung chung “pattern switch là preview” mà không gắn số phiên bản.

Các ví dụ trong bài dùng **Java 17** (ổn định và preview riêng biệt) và **Java 21** (cú pháp final) để so sánh. Nếu bạn đang dùng JDK khác, phải tra cứu trạng thái cú pháp ở JDK đó trước khi đổi lệnh.

## 3. Tính năng ổn định có thể biên dịch mà không bật preview

Mẫu `instanceof` ở Java 17:

~~~java
static String explain(Object value) {
    if (value instanceof String text) {
        return "TEXT:" + text;
    }
    return "NOT_STRING";
}
~~~

Với `value = "Java"`, biểu thức `instanceof String text` kiểm tra kiểu và gán biến mẫu `text` trong luồng đã xác nhận khớp. Với null hoặc object không phải String, biểu thức trả false; Java không ném NPE chỉ vì kiểm tra `instanceof` trên null.

Tương tự, **switch expression** đã final trước Java 17:

~~~java
static String status(int code) {
    return switch (code) {
        case 1 -> "NEW";
        case 2 -> "RUNNING";
        default -> "UNKNOWN";
    };
}
~~~

Không có mẫu kiểu ở ví dụ này: các nhãn `case 1`/`case 2` là **hằng số thông thường**. Việc thấy từ khóa `switch`, `->` hoặc `yield` **không đồng nghĩa** đoạn code đang sử dụng tính năng preview.

## 4. Biên dịch preview đúng phiên bản

Với chương trình chứa cú pháp preview của **Java 17**, trên **JDK 17**, dùng:

~~~bash
javac --enable-preview --release 17 -encoding UTF-8 PreviewSwitch17.java
java --enable-preview -cp . PreviewSwitch17
~~~

**Giải thích:**

- `--enable-preview`: cho phép tính năng preview ở phiên bản đang biên dịch/chạy.
- `--release 17`: biên dịch theo API/ngôn ngữ mục tiêu Java 17.
- `java --enable-preview`: cần để chạy class sử dụng tính năng preview.
- Đối với preview, bản `javac` thông thường **chỉ cho bật preview của chính phiên bản JDK biên dịch**. Không dùng JDK 21 để cố bật preview của Java 17 bằng `--release 17`.
- Class được biên dịch với preview có đánh dấu class-file tương ứng; **không coi** nó là một class Java 17 ổn định có thể tùy ý chạy trên các JDK khác.

Với **code Java 17 ổn định**:

~~~bash
javac --release 17 -encoding UTF-8 StablePatterns17.java
java -cp . StablePatterns17
~~~

Không cần bật preview. Với **code Java 21 sử dụng pattern switch đã final**:

~~~bash
javac --release 21 -encoding UTF-8 FinalSwitch21.java
java -cp . FinalSwitch21
~~~

Không cần `--enable-preview` khi dùng các tính năng pattern switch chuẩn Java 21.

**Tránh ngộ nhận:** Cờ preview **không biến** cú pháp Java 21 `when` thành cú pháp hợp lệ trên Java 17. Cờ chỉ mở các tính năng preview **thực sự có trong phiên bản đó**.

## 5. Java 17 preview: guarded pattern dùng `&&`

Cú pháp guarded pattern trong JEP 406 (preview Java 17) có thể viết:

~~~java
// Chỉ hợp lệ khi dùng JDK 17 với --enable-preview:
return switch (value) {
    case String text && text.length() >= 5 -> "LONG";
    case String text -> "SHORT";
    default -> "OTHER";
};
~~~

- Selector cần có kiểu phù hợp, ở đây là `Object`.
- Phần `String text` là **mẫu kiểu**.
- Guard `&& text.length() >= 5` là cú pháp của **preview Java 17**, được xét sau khi mẫu `String` khớp.
- Nếu guard false, switch thử nhãn tiếp theo.
- Mẫu String không guard được đặt **sau** nhãn guarded để không che nhãn cụ thể.

Không viết `case String text when ...` trong file Java 17 rồi chỉ thêm `--enable-preview`: **`when` chưa phải cú pháp preview của Java 17**.

## 6. Java 21 final: guarded pattern dùng `when`

Trên JDK 21, biểu đạt logic tương ứng bằng:

~~~java
return switch (value) {
    case null -> "NULL";
    case String text when text.length() >= 5 -> "LONG";
    case String text -> "SHORT";
    default -> "OTHER";
};
~~~

Với cùng một giá trị String, các nhánh kiểu và guard quyết định kết quả như ví dụ Java 17 preview. Nhưng Java 21 dùng `when` để phân tách mẫu kiểu khỏi điều kiện bảo vệ.

| Ý định | Java 17 preview | Java 21 final |
|---|---|---|
| Chọn một String có độ dài ít nhất 5 | `case String s && s.length() >= 5 ->` | `case String s when s.length() >= 5 ->` |
| Chọn một String còn lại | `case String s ->` | `case String s ->` |
| Xử lý null | Nên guard null ở ngoài theo hợp đồng Java 17 | Có thể dùng `case null ->` |

**Chú ý:** Đoạn mã Java 21 có thể còn yêu cầu các nhánh đủ để switch expression tạo kết quả. Với selector Object, `default` là một cách xử lý trường hợp không khớp các mẫu liệt kê.

## 7. Điều gì không thay đổi giữa các phiên bản?

Dù Java 17 preview viết guarded label bằng `&&` còn Java 21 final dùng `when`, guard chỉ được đánh giá **sau khi** type pattern khớp. Nếu guard false, switch thử nhãn tiếp theo; nếu nhiều nhãn cùng khớp, nhãn đứng trước được chọn. Biến mẫu chỉ hợp lệ ở nhánh và guard đã xác nhận kiểu.

Thứ tự còn liên quan **dominance**: đặt `case CharSequence cs` trước `case String s` làm nhãn String không thể tới; tương tự, nhãn `String` không guard có thể che nhãn String có guard phía sau. Đổi phiên bản cú pháp không giải quyết thứ tự sai. Trong Java 17 ổn định, chuỗi `if (value instanceof String s && ...)` diễn đạt guard mà không có phép kiểm tra dominance giữa các nhánh `if`.

## 8. Khi nào cần dùng preview?

**Ưu tiên code ổn định** nếu:

- Dự án phải biên dịch trên Java 17 bằng lệnh `javac --release 17` thông thường.
- Đang viết thư viện hoặc bài học cho nhiều môi trường JDK khác nhau.
- Muốn tránh phụ thuộc vào cú pháp có thể thay đổi.
- Hệ thống build, CI, IDE và runtime chưa bảo đảm cùng phiên bản và cờ preview.

**Chỉ nên cân nhắc preview** khi thực sự nghiên cứu tính năng mới ở đúng phiên bản, chấp nhận điều kiện triển khai và đã kiểm soát toàn bộ toolchain. Với bài học về pattern switch có guard:

- **JDK 17:** dùng `instanceof` pattern ổn định + `if`/`&&` là lựa chọn an toàn.
- **JDK 17 preview:** có thể thử guard dùng `&&`, nhưng phải bật preview cả lúc compile và run.
- **JDK 21 trở lên:** có thể dùng `when` final theo ngữ nghĩa JDK 21.

Không đổi ngôn ngữ đích hoặc nâng JDK chỉ vì một ví dụ trên mạng có vẻ ngắn hơn; cân nhắc chính sách tương thích của dự án.

## 9. Cách kiểm tra môi trường và lỗi thường gặp

Trước hết mở terminal:

~~~bash
java -version
javac -version
~~~

Hai lệnh cho biết **runtime** và **compiler** đang được gọi từ PATH. Trong một máy có nhiều JDK, chúng có thể vô tình trỏ tới phiên bản khác nhau; cần chọn đúng JDK qua `JAVA_HOME`, PATH hoặc cấu hình IDE/build tool.

| Biểu hiện | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `case String s when ...` lỗi cú pháp trên Java 17 | `when` không phải cú pháp ở bản này | Dùng `instanceof` Java 17 hoặc JDK 21 |
| Pattern switch Java 17 báo preview disabled | Chưa bật `--enable-preview` | Bật preview compile/run đúng trên JDK 17 |
| Java báo cần `--enable-preview` khi chạy class preview | Runtime chưa cho phép preview | Chạy `java --enable-preview ...` đúng JDK |
| Dùng JDK 21 kèm `--enable-preview --release 17` | Preview chỉ dành cho release của chính compiler | Dùng JDK 17 để thử preview 17; hoặc chuyển sang syntax final 21 |
| Compile Java 21 source bằng `--release 17` | Target Java 17 không biết tính năng Java 21 | Viết code tương thích 17 hoặc đổi target một cách chủ đích |
| Coi `record` và record pattern là cùng một tính năng | `record` ổn định trước record pattern | Tách mốc tính năng theo JEP/phiên bản |
| `instanceof String s` bị nhầm là preview Java 17 | Pattern instanceof đã final từ 16 | Bỏ cờ preview không cần thiết |
| `switch (int)` với `case ->` bị nhầm là preview | Switch expression/rules đã ổn định trước Java 17 | Phân biệt case hằng với type pattern |
| Dùng `case null` tùy tiện trên switch Java 17 ổn định | Khác khả năng và ngữ nghĩa của JDK 21 | Guard null bằng `if` trước |
| Mẫu String bao quát đứng trước mẫu guarded | Nhãn sau bị dominated | Nhãn cụ thể/guard trước nhãn chung |
| IDE báo lỗi nhưng CLI đúng, hoặc ngược lại | Chênh lệch language level/JDK/cờ preview | Đồng bộ project SDK, compiler, runtime và flags |

**Ghi chú về tương thích:** `--release 17` dùng để yêu cầu biên dịch nhắm tới Java 17 và API chuẩn tương ứng, **không** phải lời hứa rằng mọi cú pháp preview mới hơn đều được “dịch ngược” về Java 17.

## 10. Chương trình 1 — Java 17 ổn định, không preview

Tạo file **`StablePatterns17.java`**:

~~~java
import java.util.Locale;

public final class StablePatterns17 {
    private StablePatterns17() {}

    static String describe(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "TEXT:" + text.strip().toUpperCase(Locale.ROOT);
        }
        if (value instanceof String) {
            return "BLANK_TEXT";
        }
        if (value instanceof Integer number) {
            return "INTEGER:" + number;
        }
        if (value == null) {
            return "NULL";
        }
        return "OTHER";
    }

    static String status(int code) {
        return switch (code) {
            case 1 -> "NEW";
            case 2 -> "RUNNING";
            default -> "UNKNOWN";
        };
    }

    public static void main(String[] args) {
        System.out.println("stable17 text=" + describe(" Java "));
        System.out.println("stable17 blank=" + describe("   "));
        System.out.println("stable17 int=" + describe(Integer.valueOf(7)));
        System.out.println("stable17 null=" + describe(null));
        System.out.println("stable17 other=" + describe(Boolean.TRUE));
        System.out.println("stable17 switch=" + status(2));
    }
}
~~~

**Bash (Linux/macOS), JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 StablePatterns17.java
java -cp . StablePatterns17
~~~

**PowerShell (Windows), JDK 17+:**

~~~powershell
javac --release 17 -encoding UTF-8 .\StablePatterns17.java
java -cp . StablePatterns17
~~~

**Exact expected stdout:**

~~~text
stable17 text=TEXT:JAVA
stable17 blank=BLANK_TEXT
stable17 int=INTEGER:7
stable17 null=NULL
stable17 other=OTHER
stable17 switch=RUNNING
~~~

Ở đây `instanceof` pattern và switch expression đều **ổn định trong Java 17**, nên không bật preview.

## 11. Chương trình 2 — switch pattern preview trên đúng JDK 17

Tạo file **`PreviewSwitch17.java`**, dùng preview JEP 406, không chứa `when`:

~~~java
public final class PreviewSwitch17 {
    private PreviewSwitch17() {}

    static String classify(Object value) {
        return switch (value) {
            case String text && text.isBlank() -> "BLANK";
            case String text && text.length() >= 5 -> "LONG";
            case String text -> "SHORT";
            case Integer number -> "INTEGER:" + number;
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println("preview17 blank=" + classify("  "));
        System.out.println("preview17 long=" + classify("World"));
        System.out.println("preview17 short=" + classify("Go"));
        System.out.println("preview17 int=" + classify(7));
        System.out.println("preview17 other=" + classify(Boolean.TRUE));
    }
}
~~~

**Bash (Linux/macOS), bắt buộc JDK 17:**

~~~bash
javac --enable-preview --release 17 -encoding UTF-8 PreviewSwitch17.java
java --enable-preview -cp . PreviewSwitch17
~~~

**PowerShell (Windows), bắt buộc JDK 17:**

~~~powershell
javac --enable-preview --release 17 -encoding UTF-8 .\PreviewSwitch17.java
java --enable-preview -cp . PreviewSwitch17
~~~

**Exact expected stdout của chương trình:**

~~~text
preview17 blank=BLANK
preview17 long=LONG
preview17 short=SHORT
preview17 int=INTEGER:7
preview17 other=OTHER
~~~

**Lưu ý về thông báo của compiler:** JDK 17 có thể in thêm **thông báo preview** trên stderr khi biên dịch; phần expected stdout trên chỉ là **đầu ra chương trình**. Không cần chỉnh lệnh để che thông báo đó.

Vì `classify(null)` không được gọi, không có nhánh xử lý null trong chương trình demo. Nếu cần nhận null, hãy kiểm tra **trước switch** theo hợp đồng API, thay vì giả định `default` bắt mọi giá trị.

## 12. Chương trình 3 — cú pháp final `when` trên JDK 21+

Tạo file **`FinalSwitch21.java`**:

~~~java
public final class FinalSwitch21 {
    private FinalSwitch21() {}

    static String classify(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String text when text.isBlank() -> "BLANK";
            case String text when text.length() >= 5 -> "LONG";
            case String text -> "SHORT";
            case Integer number -> "INTEGER:" + number;
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println("final21 null=" + classify(null));
        System.out.println("final21 blank=" + classify("  "));
        System.out.println("final21 long=" + classify("World"));
        System.out.println("final21 short=" + classify("Go"));
        System.out.println("final21 int=" + classify(7));
        System.out.println("final21 other=" + classify(Boolean.TRUE));
    }
}
~~~

**Bash (Linux/macOS), JDK 21+:**

~~~bash
javac --release 21 -encoding UTF-8 FinalSwitch21.java
java -cp . FinalSwitch21
~~~

**PowerShell (Windows), JDK 21+:**

~~~powershell
javac --release 21 -encoding UTF-8 .\FinalSwitch21.java
java -cp . FinalSwitch21
~~~

**Exact expected stdout:**

~~~text
final21 null=NULL
final21 blank=BLANK
final21 long=LONG
final21 short=SHORT
final21 int=INTEGER:7
final21 other=OTHER
~~~

Đây là tính năng **chính thức từ Java 21**, vì thế **không dùng** `--enable-preview` cho riêng pattern matching for switch của chương trình này.

## 13. Cách đọc sự khác nhau giữa ba ví dụ

| Tiêu chí | `StablePatterns17.java` | `PreviewSwitch17.java` | `FinalSwitch21.java` |
|---|---|---|---|
| JDK để biên dịch | 17+ với target 17 | **Đúng JDK 17** | 21+ với target 21 |
| `--enable-preview` | Không | **Có: compile và run** | Không |
| Pattern matching cho `instanceof` | Có | Không cần dùng riêng | Không cần dùng riêng |
| Pattern matching cho `switch` | Không | **Preview** | **Final** |
| Cú pháp guard | `instanceof T t && ...` trong `if` | `case T t && ...` | `case T t when ...` |
| Xử lý `null` | `if (value == null)` | Guard trước switch nếu cần | `case null` có thể dùng |
| Mục tiêu | Code Java 17 tương thích | Thử nghiệm cú pháp preview năm 2021 | Code switch pattern hiện đại ổn định |

Cùng một nhu cầu phân loại theo kiểu có thể có nhiều cách viết; **không có cách viết nào được phép “copy” giữa các bản JDK mà bỏ qua phiên bản**.

## 14. Các bẫy cần nhớ

1. **Final không đồng nghĩa tính năng đã tồn tại ở mọi JDK cũ:** cú pháp final của Java 21 vẫn không hợp lệ nếu target Java 17.
2. **Preview không phải cú pháp bất biến:** guard `&&` của switch preview Java 17 khác `when` của Java 21.
3. **Một file dùng preview có thể tạo class không chạy theo cách bình thường:** cần cờ runtime và JDK phù hợp.
4. **`case ->` không tự động là preview:** switch rules và switch expressions đã ổn định trước Java 17.
5. **Một Java 17 `record` hợp lệ không suy ra record patterns cũng final trong Java 17.**
6. **Đừng nhầm warning với lỗi chương trình:** compiler có thể cảnh báo preview, trong khi chương trình vẫn chạy với cờ đúng.
7. **Đừng tin `default` luôn bắt null** trong switch pattern: xử lý null riêng theo phiên bản và cú pháp.
8. **Thứ tự nhãn là ngữ nghĩa:** guard false thử case khác, nhưng pattern rộng không guard trước pattern hẹp có thể bị compiler báo dominated.
9. **Không ép dùng preview cho code production** chỉ để viết ít dòng hơn khi phiên bản ổn định đã có giải pháp rõ ràng.
10. **Đồng bộ IDE, build và CLI:** các tùy chọn language level khác nhau có thể khiến cùng file compile ở nơi này nhưng lỗi nơi khác.

## 15. Bài tập có đáp án

### Bài A — cú pháp nào chạy ổn định trên Java 17?

~~~java
Object obj = "Java";
if (obj instanceof String s) {
    System.out.println(s.length());
}
~~~

**Đáp án:** Chạy ổn định trên JDK 17, in `4`. `instanceof` pattern đã final từ Java 16; không cần preview.

### Bài B — sửa nhầm phiên bản

~~~java
// Người học dùng JDK 17:
// case String s when s.isBlank() -> "BLANK"
~~~

**Đáp án:** Java 17 **không hỗ trợ `when`**. Có thể dùng `if (obj instanceof String s && s.isBlank())` mà không cần preview. Nếu cố tình nghiên cứu preview Java 17, dùng `case String s && s.isBlank() -> ...` và bật `--enable-preview` đúng trên JDK 17. Nếu muốn `when` final, cần JDK 21+ và target 21 trở lên.

### Bài C — lệnh nào cho phép preview Java 17?

~~~text
A. javac --release 17 PreviewSwitch17.java
B. javac --enable-preview --release 17 PreviewSwitch17.java
C. javac --enable-preview --release 21 PreviewSwitch17.java
~~~

**Đáp án:** **B**, khi sử dụng **JDK 17**. Sau biên dịch, chạy `java --enable-preview -cp . PreviewSwitch17` trên JDK 17. Lựa chọn C không phải cách yêu cầu “preview Java 17”.

### Bài D — dominance và thứ tự nhãn

~~~java
// JDK 21, đoạn SAI về thứ tự:
switch (obj) {
    case CharSequence sequence -> System.out.println("SEQUENCE");
    case String text -> System.out.println("STRING");
    default -> System.out.println("OTHER");
}
~~~

**Đáp án:** `String` là một `CharSequence`, nên nhãn String phía sau bị che hoàn toàn; sửa bằng cách **đặt `case String text` trước `case CharSequence sequence`**.

### Bài E — tính năng đã final có cần preview không?

Một file JDK 21 chỉ dùng `case String s when s.length() > 3 -> ...` trong pattern switch đã final. Có cần `--enable-preview`?

**Đáp án:** **Không**. Dùng `javac --release 21 ...` và `java ...` trên JDK 21. Preview chỉ cần khi đang dùng một **tính năng khác** chưa ổn định của JDK cụ thể.

## 16. Checklist và kết luận

- [ ] Luôn gắn nhận định final/preview với **số phiên bản Java**.
- [ ] Biết `instanceof` pattern đã final từ Java 16, ổn định trên Java 17.
- [ ] Biết switch expression `->`/`yield` final từ Java 14.
- [ ] Biết pattern matching cho switch preview trên Java 17–20, final từ Java 21.
- [ ] Biết Java 17 switch preview dùng guard `&&`; Java 21 final dùng `when`.
- [ ] Biết `--enable-preview` cần bật ở **compile và run** nếu class dùng preview Java 17.
- [ ] Không cố yêu cầu JDK mới bật preview của release cũ.
- [ ] Biết kiểm tra `java -version`, `javac -version` và cờ `--release`.
- [ ] Phân biệt record class đã final với record patterns được final muộn hơn.
- [ ] Hiểu guard chỉ chạy khi type pattern khớp và thứ tự case có thể đổi kết quả.
- [ ] Hiểu dominance và null handling trong switch pattern theo phiên bản.
- [ ] Chạy `StablePatterns17.java`, `PreviewSwitch17.java` và `FinalSwitch21.java` trên các JDK tương ứng, đối chiếu expected stdout.

**Kết luận:** Một cú pháp trong Java có thể **preview ở bản trước và ổn định ở bản sau**, đồng thời **đổi cú pháp** khi hoàn thiện. Đối với mẫu kiểm tra kiểu, Java 17 dùng `instanceof` pattern ổn định; pattern switch của Java 17 là preview với guard `&&`, còn Java 21 đã final pattern switch cùng guard `when`. Muốn học hoặc triển khai đúng, hãy luôn kiểm tra **phiên bản, cú pháp, trạng thái và cờ compile/run** trước khi sử dụng.