# Mốc phiên bản của pattern matching for instanceof trong Java

## 1. Mục tiêu học tập

Trong nhóm **Tương thích Java**, câu hỏi “Java nào hỗ trợ `instanceof` có biến pattern?” phải được trả lời theo **đúng mốc phát hành**: một tính năng có thể đã xuất hiện ở trạng thái *preview* trước khi chính thức trở thành ngôn ngữ ổn định. Đọc mã trên dự án Java 11, 14, 15, 16 hay 21 mà không phân biệt mốc này dễ dẫn đến lỗi biên dịch hoặc kết luận sai về yêu cầu nâng cấp.

Sau bài học, bạn có thể:

- Nhớ đúng chuỗi mốc **JDK 14 — preview lần 1 (JEP 305), JDK 15 — preview lần 2 (JEP 375), JDK 16 — chính thức (JEP 394)**.
- Phân biệt toán tử `instanceof` truyền thống với cú pháp **type pattern** như `obj instanceof String text`.
- Chọn đúng cách biên dịch/chạy mã preview trên **chính JDK lịch sử đó**, và biết khi nào không cần `--enable-preview`.
- Hiểu ý nghĩa của `javac --release` so với phiên bản JDK đang cài và phiên bản JVM triển khai.
- Không đánh đồng **pattern matching for instanceof** với **record patterns** hoặc **pattern matching for switch** được hoàn thiện ở Java 21.
- Chẩn đoán các lỗi migration liên quan tới source compatibility, API và scope của pattern variables.

**Thông điệp chính:** Cú pháp `obj instanceof String text` là tính năng **ổn định kể từ Java 16**. Java 14–15 có phiên bản preview, không nên giới thiệu chúng như các bản chính thức tương đương Java 16.

## 2. Toán tử instanceof cũ và type pattern là hai cấp độ khác nhau

Cách viết cổ điển, dùng được trên các Java rất cũ:

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Cách viết với **pattern matching for instanceof**:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Cả hai đều kiểm tra runtime xem giá trị `value` khác `null` và có kiểu phù hợp với `String` hay không. Điểm mới của pattern là **gộp kiểm tra kiểu và khai báo/bind biến đã kiểm tra**, loại bỏ cast thủ công.

Trong bản cũ, `instanceof String` có từ rất lâu; trong bản mới, **`String text` là type pattern**. Vì vậy thông báo “Java 8 có instanceof” **không đồng nghĩa** “Java 8 có pattern matching for instanceof”.

Đây là một cải tiến cú pháp và kiểm tra kiểu có giá trị: người viết không thể vô tình kiểm tra một kiểu nhưng cast sang kiểu khác trong cùng đoạn mã, và compiler biết nơi biến `text` chắc chắn đã được bind (*flow scoping*).

## 3. Bảng thời gian chuẩn: JDK 14 → 15 → 16

| Phiên bản | Trạng thái của pattern matching for instanceof | JEP | Cách hiểu |
|---|---|---|---|
| **Java 13 trở về trước** | Chưa có cú pháp type pattern này trong Java chuẩn | — | Dùng `instanceof` truyền thống + cast |
| **Java 14** | **Preview lần thứ nhất** | **JEP 305** | Phải chủ động bật preview khi biên dịch/chạy trên JDK 14 |
| **Java 15** | **Preview lần thứ hai** | **JEP 375** | Tiếp tục preview; về cơ bản không thay đổi tính năng so với bản preview Java 14 |
| **Java 16** | **Final / permanent** | **JEP 394** | Dùng `instanceof T t` không cần bật preview |
| **Java 17** | Vẫn là tính năng chính thức | JEP 394 đã hoàn tất trước đó | Dùng bình thường trong ứng dụng Java 17 |
| **Java 21** | Vẫn là tính năng chính thức; hệ thống pattern còn được mở rộng | JEP 394, cùng JEP 440/441 ở các mảng khác | Type pattern dùng bình thường; thêm record patterns và pattern switch chính thức |

Mốc dễ nhớ:

**14 → preview, 15 → preview lần hai, 16 → chính thức.**

Không có nghĩa “đến Java 21 mới có pattern matching for instanceof”. Java 21 là mốc của **record patterns** và **pattern matching for switch** ổn định, còn type pattern đơn giản trong `instanceof` đã sẵn sàng từ Java 16.

### 3.1. JDK 14 — JEP 305 (First Preview)

JEP 305 bổ sung cách kiểm tra và rút ra biến đã đúng kiểu bằng type pattern:

```java
if (obj instanceof String s) {
    System.out.println(s.length());
}
```

Tại thời điểm Java 14, đây là **preview language feature**. Cú pháp chưa phải lời cam kết ngôn ngữ đã ổn định; cần bật preview và phải dùng đúng JDK hỗ trợ bản preview đó. Cơ chế này được phát hành để thu thập phản hồi và hoàn thiện ngôn ngữ trước khi chuẩn hóa.

### 3.2. JDK 15 — JEP 375 (Second Preview)

JEP 375 đưa tính năng vào **preview lần hai**, tiếp nối bản JDK 14. Tài liệu Oracle xác nhận phần tính năng `instanceof` pattern trong lần preview này **không có thay đổi đáng kể về ngữ nghĩa so với Java 14**.

Dù một đoạn mã có thể giống hệt nhau giữa 14 và 15, khi chạy theo chế độ preview phải dùng công cụ phù hợp **phiên bản JDK tương ứng**. Không lấy classfile preview biên dịch trên JDK 14 rồi mặc định đem chạy JDK 15/16 và kỳ vọng tương thích.

### 3.3. JDK 16 — JEP 394 (Final)

JEP 394 chuẩn hóa tính năng. Kể từ Java 16, mã đơn giản:

```java
if (obj instanceof String s) {
    System.out.println(s.toUpperCase());
}
```

biên dịch và chạy **không cần `--enable-preview`**. Nếu dự án cần tính năng này, Java 16 là mốc tối thiểu cho **cú pháp type pattern ổn định**.

Hai thay đổi đáng chú ý khi chuyển từ preview sang final:

1. Pattern variables **không còn bị coi là implicitly final**. Khi nằm trong scope hợp lệ, biến pattern có thể được gán lại, giống một biến cục bộ thông thường, dù không nên lạm dụng vì làm mã khó đọc.
2. Quy tắc kiểm tra kiểu của `instanceof` pattern trong Java 16 chặn một số phép thử kiểu mà compiler coi là không cần thiết vì **kiểu tĩnh của selector đã là subtype của kiểu pattern**. Quy tắc applicability đã tiếp tục phát triển ở các phiên bản sau; không dùng thông báo của Java 16 để khẳng định mọi phiên bản về sau xử lý y hệt (xem mục 9).

Điểm thứ nhất được kiểm chứng trong chương trình chính: `text = text.trim()` biên dịch thành công với `--release 16`. Đừng nhầm “không implicitly final” với việc biến pattern tồn tại ở bất kỳ scope nào; **flow scoping vẫn được áp dụng**.

## 4. Bật preview cho đúng phiên bản, không dùng sai javac

### 4.1. Trên JDK 14 thật

Giả sử đang dùng **JDK 14** và có tệp `PreviewInstanceofDemo.java`:

```java
public class PreviewInstanceofDemo {
    static String describe(Object value) {
        if (value instanceof String text) {
            return "TEXT:" + text.length();
        }
        return "OTHER";
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(null));
    }
}
```

Dùng lệnh **trên toolchain JDK 14**, trong thư mục chứa tệp:

```bash
javac --enable-preview --release 14 PreviewInstanceofDemo.java
java --enable-preview PreviewInstanceofDemo
```

Hoặc dùng `--source 14` với `--enable-preview` khi thích hợp. Cờ `--enable-preview` là **bắt buộc ở Java 14** để dùng cú pháp preview; nếu bỏ, compiler sẽ từ chối tính năng khi biên dịch theo source release 14.

**Đây là cách sử dụng mang tính lịch sử**, không phải lời khuyên dùng JDK 14 trong ứng dụng mới. Các lệnh preview JDK 14 không được khẳng định đã chạy bằng JDK 14 trong môi trường kiểm tra của bài này.

### 4.2. Trên JDK 15 thật

Cùng mã nguồn minh họa, dùng **toolchain JDK 15**:

```bash
javac --enable-preview --release 15 PreviewInstanceofDemo.java
java --enable-preview PreviewInstanceofDemo
```

Với Java 15, `instanceof` pattern vẫn là preview. Chỉ việc đổi số ở `--release` khi đang dùng JDK khác **không đủ** để mô phỏng bản preview lịch sử.

**Giải thích quan trọng:** `javac` hiện đại như JDK 21 chỉ cho phép bật các preview features của **chính release mà javac đó hỗ trợ**, không có nghĩa `javac 21 --enable-preview --release 15` là “JDK 15 preview”. Phép thử với JDK 21 trong bài đã ghi nhận kết quả:

```text
javac --enable-preview --release 15
error: invalid source release 15 with --enable-preview
```

Thông báo có thể khác chút tùy JDK/IDE nhưng bản chất là **không thể dùng một compiler mới để bật lại preview của bản phát hành cũ**.

### 4.3. Từ JDK 16 trở đi

Khi chỉ dùng type pattern cho `instanceof` theo cú pháp đã chuẩn hóa:

```bash
javac --release 16 InstanceofMilestonesDemo.java
java InstanceofMilestonesDemo
```

Không thêm `--enable-preview`. Tính năng đã chính thức ở Java 16 nên không cần bật preview, kể cả khi mã nguồn được biên dịch bằng một JDK mới có hỗ trợ target Java 16.

Lưu ý **`--release 16` là tùy chọn nhắm tới API và classfile Java 16**, không cài JVM 16 cho bạn. Nếu build trên máy dùng JDK 21 và chạy bằng JVM 21, phép thử đó xác nhận tính tương thích nguồn với Java 16, chứ **không phải** thử nghiệm trực tiếp trên runtime JDK 16.

## 5. Ví dụ Java có thể biên dịch với --release 16

Tạo tệp **`InstanceofMilestonesDemo.java`**:

```java
import java.util.Objects;
import java.util.Locale;

public class InstanceofMilestonesDemo {
    static String legacy(Object input) {
        if (input instanceof String) {
            String text = (String) input;
            return "TEXT:" + text.length();
        }
        return "OTHER";
    }

    static String modern(Object input) {
        if (input instanceof String text) {
            return "TEXT:" + text.length();
        }
        return "OTHER";
    }

    static String nonBlank(Object input) {
        return input instanceof String text && !text.isBlank()
                ? "NONBLANK:" + text.length() : "NO";
    }

    static String guardClause(Object input) {
        if (!(input instanceof String text)) {
            return "NOT_STRING";
        }
        return "UPPER:" + text.toUpperCase(Locale.ROOT);
    }

    static String reassignPatternVariable(Object input) {
        if (input instanceof String text) {
            text = text.trim();
            return "TRIM:" + text;
        }
        return "NOT_STRING";
    }

    static void verify(String label, Object input, String expected,
            String expectedNonBlank, String expectedGuard, String expectedTrim) {
        String before = legacy(input);
        String after = modern(input);
        String predicate = nonBlank(input);
        String guarded = guardClause(input);
        String trimmed = reassignPatternVariable(input);
        if (!Objects.equals(before, expected)
                || !Objects.equals(after, expected)
                || !Objects.equals(predicate, expectedNonBlank)
                || !Objects.equals(guarded, expectedGuard)
                || !Objects.equals(trimmed, expectedTrim)) {
            throw new AssertionError(label + ": " + before + "/" + after
                + "/" + predicate + "/" + guarded + "/" + trimmed);
        }
        System.out.println(label + " => " + after + ", "
                + predicate + ", " + guarded + ", " + trimmed);
    }

    public static void main(String[] args) {
        verify("null", null, "OTHER", "NO", "NOT_STRING", "NOT_STRING");
        verify("integer", Integer.valueOf(4), "OTHER", "NO", "NOT_STRING", "NOT_STRING");
        verify("simple", "Java", "TEXT:4", "NONBLANK:4", "UPPER:JAVA", "TRIM:Java");
        verify("spaced", " Java ", "TEXT:6", "NONBLANK:6", "UPPER: JAVA ", "TRIM:Java");
        verify("empty", "", "TEXT:0", "NO", "UPPER:", "TRIM:");
        verify("blank", "  ", "TEXT:2", "NO", "UPPER:  ", "TRIM:");
    }
}
```

### Biên dịch và chạy

Với JDK 16+ có hỗ trợ tùy chọn `--release 16`:

```bash
javac --release 16 InstanceofMilestonesDemo.java
java InstanceofMilestonesDemo
```

**Stdout đã được kiểm chứng:**

```text
null => OTHER, NO, NOT_STRING, NOT_STRING
integer => OTHER, NO, NOT_STRING, NOT_STRING
simple => TEXT:4, NONBLANK:4, UPPER:JAVA, TRIM:Java
spaced => TEXT:6, NONBLANK:6, UPPER: JAVA , TRIM:Java
empty => TEXT:0, NO, UPPER:, TRIM:
blank => TEXT:2, NO, UPPER:  , TRIM:
```

Mỗi lời gọi `verify(...)` so kết quả của mã cast cũ, mã type pattern và các biến thể với các **expected values độc lập**; nếu khác, chương trình ném `AssertionError`. Nó còn cho thấy:

- `instanceof` trả false khi input null hoặc sai kiểu: không gọi phương thức của biến chưa bind.
- `&&` bảo đảm `text.isBlank()` chỉ chạy sau khi pattern String khớp.
- Pattern variable `text` được dùng sau guard clause phủ định vì nhánh không khớp đã `return`.
- Với Java 16+, pattern variable `text` được phép gán lại trong scope hợp lệ; sau `trim()`, đầu ra có thể khác độ dài/original value.
- Dữ liệu chuỗi rỗng/trắng cho kết quả khác chuỗi thông thường dù type pattern đều khớp.

### Ma trận build đã xác minh

Dùng compiler JDK 21 trên cùng chương trình, kết quả là:

| Lệnh | Kết quả | Ý nghĩa |
|---|---|---|
| `javac --release 14 InstanceofMilestonesDemo.java` | **Bị từ chối** | Type pattern là preview ở 14; hơn nữa chương trình cố ý có gán lại pattern variable vốn không phù hợp preview cũ |
| `javac --release 15 InstanceofMilestonesDemo.java` | **Bị từ chối** | Type pattern vẫn là preview ở 15 |
| `javac --release 16 InstanceofMilestonesDemo.java` | **PASS** | Cú pháp ổn định từ Java 16 |
| `javac --release 17 InstanceofMilestonesDemo.java` | **PASS** | Tương thích Java 17 |
| `javac --release 21 InstanceofMilestonesDemo.java` | **PASS** | Tương thích Java 21 |

Các bản build PASS đã chạy cùng runtime JDK 21 trong môi trường kiểm chứng và cho stdout giống nhau. Không diễn giải phép thử này như việc đã khởi chạy JVM 14, 15, 16 hay 17 thật. Để kiểm tra thực tế trên JDK runtime đích, hãy dùng JDK/container tương ứng trong CI.

**Cẩn trọng:** Không thể dùng **chính chương trình có gán lại pattern variable này** để minh họa preview 14/15 vì một số quy tắc đã thay đổi khi JEP 394 được chuẩn hóa. Khi thử lại cú pháp preview trên JDK 14/15, dùng `PreviewInstanceofDemo.java` ở mục 4.

## 6. Trước Java 16: legacy cast vẫn là lựa chọn tương thích

Nếu dự án yêu cầu **Java 8 hoặc Java 11**, bạn có thể giữ cú pháp truyền thống:

```java
public class LegacyOnlyDemo {
    static String size(Object value) {
        if (value instanceof String) {
            String s = (String) value;
            return "LENGTH:" + s.length();
        }
        return "OTHER";
    }
    public static void main(String[] args) {
        System.out.println(size("Java"));
        System.out.println(size(null));
    }
}
```

Tên tệp là **`LegacyOnlyDemo.java`**. Mã này không sử dụng pattern matching for `instanceof`, chỉ dùng toán tử `instanceof` truyền thống:

```bash
javac --release 8 LegacyOnlyDemo.java
java LegacyOnlyDemo
```

**Stdout đã xác minh** bằng compiler JDK 21 nhắm `--release 8` và runtime JDK 21:

```text
LENGTH:4
OTHER
```

Một JDK hiện đại có thể cảnh báo về tùy chọn source/target quá cũ, nhưng chương trình vẫn biên dịch. Với dự án production, lựa chọn phiên bản hỗ trợ phải xét cả lifecycle bảo trì/bản vá an ninh, không chỉ khả năng compiler chấp nhận cú pháp.

### Có nên “polyfill” type pattern cho Java 8?

Không có thư viện Java thông thường nào làm JDK 8 hiểu cú pháp ngôn ngữ `instanceof String s` trước khi biên dịch. Bạn cần **chỉnh mã nguồn về cú pháp cũ**, sử dụng công cụ chuyển đổi mã có quy trình build riêng, hoặc **nâng source level**. Việc chỉ thêm dependency không thay đổi bộ phân tích cú pháp của `javac --release 8`.

## 7. Java 21: phân biệt type pattern với các tính năng pattern khác

Không phải tất cả cú pháp có chữ “pattern” đều được chuẩn hóa ở cùng phiên bản.

| Tính năng | Ví dụ cú pháp | Mốc chính thức |
|---|---|---|
| **Pattern matching for `instanceof` với type pattern** | `obj instanceof String s` | **Java 16** (JEP 394) |
| **Pattern matching for `switch`** | `case String s -> ...` | **Java 21** (JEP 441) |
| **Record patterns** | `obj instanceof Label(String name)` | **Java 21** (JEP 440) |

Trước khi là tính năng chính thức, các thành phần khác có những giai đoạn preview riêng: pattern matching cho `switch` bắt đầu preview ở Java 17, còn record patterns bắt đầu preview ở Java 19. Nhưng **đừng chuyển các mốc này sang `instanceof` type pattern**.

### Minh họa Java 21 chỉ để so sánh

Tạo tệp **`LaterFeaturesDemo.java`**:

```java
public class LaterFeaturesDemo {
    record Label(String name) {}

    static String describe(Object source) {
        return switch (source) {
            case null -> "NULL";
            case Label(String name) -> "LABEL:" + name;
            case String text -> "STRING:" + text;
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        Object item = new Label("Java 21");
        System.out.println("record pattern -> "
                + (item instanceof Label(String name)));
        System.out.println(describe(item));
        System.out.println(describe(new Label(null)));
        System.out.println(describe("text"));
        System.out.println(describe(null));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 LaterFeaturesDemo.java
java LaterFeaturesDemo
```

**Stdout đã kiểm chứng:**

```text
record pattern -> true
LABEL:Java 21
LABEL:null
STRING:text
NULL
```

Chương trình này **không thể biên dịch với `--release 16`** vì sử dụng record patterns và pattern switch chỉ chính thức ở Java 21. Như vậy, dù dòng `item instanceof Label(String name)` có `instanceof`, việc nhận ra **record pattern** khác với type pattern `item instanceof Label label` là thiết yếu khi quyết định mốc Java tối thiểu.

Record `Label` cần tồn tại và khác null để pattern phân rã; nhưng component `name` là chuỗi có thể null, nên `Label(String name)` trong ngữ cảnh record deconstruction có thể bind `null`. Đây là semantics của record patterns Java 21, không nên dùng nó để suy đoán toàn bộ type patterns Java 16.

## 8. Source, javac, classfile và JVM: bốn khái niệm khác nhau

Một team thường nói chung “project chạy Java 17” nhưng cần tách:

1. **JDK/compiler đang dùng:** phiên bản chương trình `javac` thực sự chạy. Nó quyết định danh sách release được hỗ trợ và preview của chính JDK đó.
2. **Source language level:** phiên bản cú pháp mà mã nguồn được phép sử dụng. Với `--release 16`, type pattern chính thức hợp lệ, còn record patterns Java 21 không hợp lệ.
3. **API và classfile target:** `--release N` đồng thời giới hạn API công khai và tạo classfile phù hợp với Java N (khi compiler hỗ trợ N).
4. **Runtime JVM:** phiên bản máy ảo thực sự tải/thi hành classfile. JVM quá cũ không thể chạy classfile nhắm tới Java mới.

Ví dụ:

```bash
# JDK 21 biên dịch mã source/API/bytecode cho Java 16:
javac --release 16 InstanceofMilestonesDemo.java

# Kiểm tra Java đang chạy trên máy:
java -version

# Kiểm tra phiên bản compiler:
javac -version
```

Đoạn trên tạo classfile mục tiêu Java 16, nhưng `java -version` có thể vẫn báo Java 21. Muốn kiểm tra runtime Java 16 thật, cần chạy bằng Java 16 ở môi trường đó.

### Ma trận migration thực tế

| Yêu cầu deploy | Source pattern for instanceof được chọn | Kết luận |
|---|---|---|
| Runtime Java 8/11, không dùng transpiler | Cú pháp cũ với cast | Không viết `instanceof T t` trong source level đó |
| Toolchain JDK 14/15 đúng phiên bản, đang thử preview | Type pattern kèm `--enable-preview` | Chỉ dành cho thử nghiệm lịch sử; yêu cầu runtime preview tương ứng |
| Source/target từ Java 16 | Type pattern ổn định | Không cần preview |
| Source/target Java 17 | Type pattern ổn định | Sử dụng bình thường, không ngụ ý record pattern đã có |
| Source/target Java 21 | Type pattern, record pattern, switch pattern | Có thể sử dụng cả ba theo JEP tương ứng |

Cũng cần lưu ý: tính năng mới của ngôn ngữ không tự động biến mã đã biên dịch thành ứng dụng tương thích ngược với JVM cũ. Chuyển classfile hay đổi cờ runtime không làm một JVM 8 hiểu bytecode được biên dịch cho 16/21.

### Ví dụ thiết lập build tool

Nếu dự án Maven có Maven Compiler Plugin tương thích, một cấu hình source/API/bytecode rõ ràng là:

```xml
<properties>
    <maven.compiler.release>16</maven.compiler.release>
</properties>
```

Hoặc Gradle với Java Toolchains:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(16)
    }
}
```

Hai đoạn này là **mẫu cấu hình minh họa**, không phải chương trình chạy Java và không nhất thiết thích hợp cho mọi repository. Maven `release` yêu cầu compiler JDK hỗ trợ target đó; Gradle Toolchain yêu cầu có hoặc provision được JDK tương ứng và phiên bản Gradle đủ mới. Cần chạy CI trên toolchain và runtime thật mà ứng dụng hỗ trợ.

Nếu dự án dùng Java 17, đặt `release=17` thay vì 16 để phản ánh đúng API và ngôn ngữ yêu cầu. Đừng tăng version vì một lời cảnh báo IDE nếu ứng dụng vẫn bắt buộc triển khai trên JVM cũ.

## 9. Một thay đổi tinh tế: quy tắc loại bỏ pattern “luôn đúng” qua các release

Khi tra cứu tài liệu JEP 394 cho Java 16, bạn có thể gặp quy tắc: với pattern `instanceof`, biểu thức có kiểu tĩnh `S` là subtype của kiểu pattern `T` thì compiler bác bỏ vì phép kiểm tra luôn đúng với các đối tượng khác null.

Ví dụ:

```java
class SourceTypingVersionDemo {
    static boolean matches(String value) {
        return value instanceof CharSequence text;
    }
}
```

**Kết quả đã kiểm chứng với compiler JDK 21 ở các source release khác nhau**:

| Source release được truyền vào `javac --release` | Kết quả |
|---|---|
| `16` | Lỗi compile time |
| `17` | Lỗi compile time |
| `18` | Lỗi compile time |
| `19` | Lỗi compile time |
| `20` | Lỗi compile time |
| `21` | **Biên dịch thành công** |

Lý do phải đọc đúng JLS theo release: trong Java 21, mô hình pattern đã bổ sung khái niệm **unconditional type pattern** và quy tắc compatibility được diễn đạt lại trong hệ thống pattern tổng quát. Vì vậy không được lấy thông báo “test có kiểu luôn đúng nên lỗi” của một bản Java rồi gán cho mọi bản mới hơn.

Nếu chỉ cần kiểm tra `value` có khác null khi biến đã khai báo kiểu `String`, cách diễn đạt rõ hơn thường là:

```java
String value = "abc";
boolean present = value != null;
```

Tức là dù một pattern cụ thể có được compiler Java 21 cho phép hay không, **không cần dùng `instanceof` để thay cho null check** nếu kiểu của dữ liệu đã được biết.

**Không nhầm điều này với tình huống sai kiểu không thể cast:** ví dụ `String s; s instanceof Integer i` vẫn không hợp lệ ở các bản Java thông thường vì kiểu tĩnh không thể checked-cast-convertible sang Integer. Trước khi kết luận, hãy nhìn cả **kiểu tĩnh của selector** và **source release đang biên dịch**.

## 10. Những lỗi thường gặp khi nâng cấp hoặc hạ mục tiêu Java

### 10.1. Nhầm phiên bản xuất hiện với phiên bản ổn định

Phát biểu “có pattern matching for instanceof từ Java 14” cần bổ sung chữ **preview**. Khi chọn mốc tối thiểu cho sản phẩm không dùng preview, mốc đúng là **Java 16**.

### 10.2. Cho rằng bật preview trên JDK 21 là bật lại preview của JDK 14

Không đúng. Preview được gắn với phiên bản JDK cụ thể. Cặp `--enable-preview --release 15` dưới compiler JDK 21 bị từ chối trong kiểm chứng thực tế. Muốn thử lịch sử, hãy dùng JDK 15 đúng phiên bản.

### 10.3. Dùng cú pháp record deconstruction nhưng khai báo project Java 16

`obj instanceof Label(String name)` là **record pattern**, không phải type pattern cơ bản; mốc chính thức là Java 21. Với Java 16, chỉ dùng dạng như `obj instanceof Label label` nếu kiểu Label đã tồn tại và thích hợp.

### 10.4. Viết `when` sau `instanceof`

`when` là guard trong nhãn `case` của pattern `switch` Java 21. Với type pattern `instanceof`, dùng `&&`:

```java
if (obj instanceof String text && !text.isBlank()) {
    System.out.println(text);
}
```

Đoạn này hợp lệ từ Java 16 nếu các API sử dụng tương thích. Không viết `obj instanceof String text when ...`.

### 10.5. Bỏ qua flow scoping khi refactor

`text` chỉ có thể dùng khi compiler bảo đảm pattern đã khớp. Vì vậy:

```java
if (obj instanceof String text && text.length() > 3) {
    System.out.println(text);
}
```

hợp lệ, nhưng:

```java
// Không hợp lệ: vế phải của || có thể được chạy khi
// pattern bên trái không khớp, nên text chưa được bind.
if (obj instanceof String text || text.length() > 3) {
    System.out.println("value");
}
```

bị compiler từ chối. Đây là lỗi **scope** chứ không nhất thiết là lỗi do mốc phiên bản Java.

### 10.6. Nghĩ rằng chỉ cần JVM 16 là mã source 16 tự biên dịch

Không. Toolchain phải dùng javac hỗ trợ Java 16 và cấu hình source/target tương ứng. Với JDK 11, bạn không thể build mã pattern bằng cách yêu cầu `--release 16`, vì compiler cũ không hỗ trợ release tương lai. Runtime và compiler là hai phần riêng.

### 10.7. Tăng `--release` nhưng production vẫn dùng JVM cũ

Mã biên dịch thành công bằng `--release 21` không thể mặc định chạy trên JVM 17. Nếu có giới hạn runtime, cần giữ target đúng hoặc nâng runtime có kiểm soát; chú ý cả các thư viện và API đi kèm.

### 10.8. Tin rằng mã preview là API/syntax ổn định mãi

Preview features được phép thay đổi hoặc bị gỡ trước khi trở thành chính thức. Với dự án mới, ưu tiên JDK hỗ trợ tính năng final, thay vì phụ thuộc preview lịch sử 14/15 hoặc mang classfile preview sang runtime khác.

### 10.9. Nhầm quy tắc gán biến pattern của preview với Java 16+

Từ JEP 394, pattern variables không còn implicitly final; có thể gán lại. Tuy nhiên gán lại có thể làm người đọc nhầm giá trị được bind ban đầu với giá trị đã sửa. Dùng biến mới nếu việc biến đổi làm thay đổi ý nghĩa và cần bảo toàn dữ liệu gốc.

## 11. Checklist kiểm tra tương thích trong codebase

Trước khi đưa `instanceof T t` vào project, hãy xác nhận:

1. **Minimum supported JDK:** runtime thấp nhất được triển khai là phiên bản nào?
2. **Compiler thực tế:** CI, local và IDE có cùng cấu hình JDK không? Đọc `javac -version`.
3. **Target source/API/bytecode:** mốc `--release` hoặc cấu hình build tool đang dùng là bao nhiêu?
4. **Preview hay final:** nếu nhắm 14/15, có dùng đúng JDK và cờ preview không? Nếu nhắm 16+, preview không cần cho type pattern.
5. **Feature cụ thể:** code chỉ dùng type pattern trong `instanceof` hay còn dùng record patterns, pattern switch, guarded case?
6. **Scope và null:** biến pattern chỉ dùng nơi match; input null khiến root `instanceof` false.
7. **Các API ngoài syntax:** ví dụ dùng `String.isBlank()` (API có từ Java 11); cú pháp hợp lệ chưa đủ nếu API đang gọi vượt target.
8. **Tính tương thích nhị phân:** các service/jar có thể đang chạy JVM khác nhau; tránh triển khai classfile mới trên JVM cũ.
9. **Chạy test theo build target:** thử `javac --release N` hoặc cấu hình Maven/Gradle; nếu cần bảo đảm runtime, chạy thêm JVM N thật trong CI.
10. **Đọc lỗi compiler đúng loại:** thông báo có thể do thiếu preview, cú pháp mới hơn target, kiểu tĩnh không compatible, scope hoặc API không tồn tại.

Nếu tất cả kiểm tra đều qua, mới bắt đầu refactor cast thủ công thành type pattern ở những đoạn mã được phép thay đổi.

## 12. Bài tập tự kiểm tra

**Câu 1.** `pattern matching for instanceof` có ở Java 14 hay 16?  
**Đáp án:** Có bản **preview ở 14**; trở thành tính năng **chính thức ở 16**.

**Câu 2.** JEP nào tương ứng với mỗi mốc?  
**Đáp án:** **JEP 305 → Java 14 (preview); JEP 375 → Java 15 (second preview); JEP 394 → Java 16 (final)**.

**Câu 3.** Tại sao `javac 21 --enable-preview --release 15` không thay thế được JDK 15?  
**Đáp án:** Compiler JDK 21 không bật lại preview của release cũ; cần dùng toolchain JDK 15 thật.

**Câu 4.** Java 17 dùng được `input instanceof String text` không?  
**Đáp án:** Có. Tính năng đã chính thức ở Java 16, không yêu cầu preview trên Java 17.

**Câu 5.** Java 16 dùng được `obj instanceof Label(String text)` không?  
**Đáp án:** Không, đó là **record pattern** (chính thức Java 21), không phải type pattern cơ bản.

**Câu 6.** Java 8 có `instanceof` không?  
**Đáp án:** Có toán tử truyền thống; chưa có cú pháp bind pattern variable `instanceof String s`.

**Câu 7.** Nếu code dùng `instanceof` type pattern nhưng CI báo lỗi với `--release 11`, có thể giải quyết chỉ bằng thêm dependency không?  
**Đáp án:** Không. Đây là cú pháp ngôn ngữ không có ở source level 11; phải nâng target hoặc viết lại bằng cast truyền thống.

**Câu 8.** `--release 16` trên JDK 21 có chứng minh code chạy trên JVM 16 thật không?  
**Đáp án:** Chưa. Nó chứng minh khả năng biên dịch với source/API/bytecode mục tiêu; muốn xác nhận runtime hãy chạy test trên JVM 16 thật.

**Câu 9.** Java 16 thay đổi điều gì về pattern variable?  
**Đáp án:** Không còn bị implicitly final; có thể gán lại trong scope hợp lệ, khác với giai đoạn preview.

**Câu 10.** Vì sao ví dụ `String s; s instanceof CharSequence c` phải được xét theo `--release`?  
**Đáp án:** Quy tắc kiểm tra type pattern đã thay đổi theo phát triển ngôn ngữ; kết quả `--release 16–20` trong môi trường kiểm tra là lỗi, `--release 21` là hợp lệ. Kiểu tĩnh và JLS của release đều quan trọng.

## Kết luận

Có ba mốc không được nhầm:

- **Java 14 / JEP 305:** xuất hiện dưới dạng **preview đầu tiên**.
- **Java 15 / JEP 375:** **preview lần hai**.
- **Java 16 / JEP 394:** **chính thức, không cần preview**.

Java 17 và Java 21 sử dụng type patterns trong `instanceof` như tính năng ổn định. Record patterns và pattern switch là bước phát triển khác, được chuẩn hóa ở Java 21. Khi nói về “Java tối thiểu”, hãy xét đúng **feature, source level, compiler và runtime mục tiêu**, không chỉ nhìn câu lệnh `instanceof` trong mã.

## Tài liệu tham khảo chính thức

- [JEP 305 — Pattern Matching for instanceof (Preview, JDK 14)](https://openjdk.org/jeps/305)
- [JEP 375 — Pattern Matching for instanceof (Second Preview, JDK 15)](https://openjdk.org/jeps/375)
- [JEP 394 — Pattern Matching for instanceof (JDK 16)](https://openjdk.org/jeps/394)
- [Oracle — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [Oracle Java 21 — Pattern Matching for the instanceof Operator](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html)
- [JLS Java SE 21 — instanceof Operator §15.20.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2)
- [Oracle Java 21 — javac Command Options](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [JEP 440 — Record Patterns (JDK 21)](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch (JDK 21)](https://openjdk.org/jeps/441)
