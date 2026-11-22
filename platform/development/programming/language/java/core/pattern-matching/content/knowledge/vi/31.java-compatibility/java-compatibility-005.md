# Khác biệt syntax giữa các phiên bản Java: Pattern Matching và các cú pháp liên quan

## 1. Vì sao cùng một đoạn pattern code lại biên dịch ở máy này mà lỗi ở máy khác?

Java phát triển từng bước: một số cú pháp xuất hiện ở trạng thái **preview** trong vài phiên bản, rồi mới trở thành **tính năng chính thức (final)**. Vì thế mã hướng dẫn có chữ `switch`, `instanceof`, `record` hoặc `when` có thể cần **phiên bản ngôn ngữ khác nhau**, dù tất cả đều trông giống “Java hiện đại”.

Trong chủ đề **Java Core Pattern Matching**, các thay đổi quan trọng nhất là:

- Cách kiểm tra kiểu: `instanceof` truyền thống kèm cast → **type pattern** khai báo biến ngay trong phép kiểm tra.
- Cách phân nhánh: `switch statement` truyền thống → `switch expression` trả giá trị → **pattern matching for switch**.
- Cách tổ chức dữ liệu: class thường → `record` và `sealed` hierarchy → **record pattern** để tách component.
- Cách bỏ qua dữ liệu không cần dùng: khai báo biến rồi không sử dụng → **unnamed pattern** với ký hiệu `_` từ Java 22.

**Đề bài này tập trung vào khác biệt cú pháp, điều kiện phiên bản, lỗi thường gặp và cách migration.** Không nên hiểu rằng mọi chức năng có từ “pattern” đều xuất hiện cùng một lúc hoặc mọi tính năng Java 21 đều cần bật preview.

## 2. Bảng thời gian các cú pháp trọng tâm

| Phiên bản Java | Cú pháp/tính năng liên quan | Trạng thái ở phiên bản đó | Ghi chú |
| --- | --- | --- | --- |
| Java 8/11 | `instanceof Type` và cast, `switch` statement với `case:` | Ổn định từ trước | **Không có** type pattern `instanceof String s` hoặc pattern case chính thức |
| Java 12–13 | `switch expression` | Preview | Cú pháp thử nghiệm từng thay đổi; không bê nguyên ví dụ preview cũ vào code mới |
| **Java 14** | `switch expression`, `case ... ->` và `yield` | **Final** | JEP 361; arrow rule cũng có thể dùng trong `switch statement` |
| Java 14–15 | Type patterns trong `instanceof` | Preview | JEP 305/JEP 375; chỉ nên coi đây là tư liệu theo phiên bản |
| **Java 16** | `instanceof String s` và `record` | **Final** | JEP 394, JEP 395; record **chưa đồng nghĩa** record patterns |
| **Java 17** | `sealed` types; pattern `instanceof` | **Final** | JEP 409; pattern matching for `switch` vẫn **preview** |
| Java 17–20 | Pattern matching for `switch` | Preview qua nhiều vòng | Guard và các quy tắc có thay đổi; chưa phải cú pháp chuẩn để copy cho Java 21 |
| Java 19–20 | Record patterns | Preview | Java 21 mới chuẩn hóa |
| **Java 21** | Pattern matching for `switch`; record patterns, `when` | **Final** | JEP 441 và 440; ví dụ chính của bài chạy ở đây |
| **Java 22** | Unnamed patterns và variables với `_` | **Final** | JEP 456; Java 21 có bản preview riêng (JEP 443) nhưng không mặc định |

**Quan trọng:** `var` dành cho **biến cục bộ** đã chính thức từ **Java 10**; đừng nhầm với `var` bên trong record pattern `Point(var x, var y)`, chỉ là cú pháp record pattern khi phiên bản ngôn ngữ có hỗ trợ. Dấu gạch dưới `_` còn là một trường hợp khác, có quy tắc riêng.

Bảng trên liệt kê **các mốc cần thiết khi đọc và chuyển đổi pattern code**, không có ý định liệt kê toàn bộ tính năng của từng bản Java.

## 3. Java 8/11: kiểm tra kiểu rồi cast thủ công

Trước khi có pattern matching cho `instanceof`, code thường viết:

```java
static String oldStyle(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return text.toUpperCase(java.util.Locale.ROOT);
    }
    return "other";
}
```

Đây là **phương thức minh họa**, cần đặt vào class để biên dịch. Cú pháp `value instanceof String` chỉ trả Boolean; nó **không tạo biến `text`**. Lập trình viên phải lặp lại phép cast dù nhánh `if` đã biết kiểu.

Với nhiều subtype, code cũ dễ dẫn đến:

```java
if (value instanceof String) {
    String s = (String) value;
    // ...
} else if (value instanceof Integer) {
    Integer n = (Integer) value;
    // ...
}
```

**Dùng được ở Java 8/11** nhưng có nhược điểm là lặp cú pháp và dễ chép nhầm kiểu cast. Khi codebase phải build với `--release 8` hoặc `--release 11`, đây vẫn là phương án hợp lệ. Không thể chỉ đổi `String text` thành type pattern rồi mong source Java 8 biên dịch.

## 4. Java 14: switch expression, arrow rules và yield

### 4.1. Từ `switch statement` sang `switch expression`

Dạng statement cổ điển:

```java
static String oldSwitch(String state) {
    String result;
    switch (state) {
        case "ON":
            result = "on";
            break;
        case "OFF":
            result = "off";
            break;
        default:
            result = "unknown";
    }
    return result;
}
```

Dạng biểu thức chính thức từ Java 14:

```java
static String newSwitch(String state) {
    return switch (state) {
        case "ON" -> "on";
        case "OFF" -> "off";
        default -> "unknown";
    };
}
```

Hai phương thức là các đoạn minh họa trong class, đều giả định `state` **khác `null`**. Với `null`, `switch` trên `String` kiểu này không tự có một nhánh null; để xử lý, dùng `if (state == null)` ở ngoài. Không đưa `case null` của pattern switch Java 21 vào ví dụ cần chạy Java 14.

Khác nhau về mục đích:
- `switch statement` điều khiển các câu lệnh và có thể `break;` ra khỏi switch.
- `switch expression` **tạo giá trị**, nên phải có đường xử lý giá trị phù hợp; các arrow rules trả trực tiếp kết quả.
- Trong arrow rules, không có fall-through tự động giữa các case. Với colon groups truyền thống, phải đặc biệt cẩn thận về `break` để tránh rơi qua nhóm case khác.

### 4.2. Block rule và `yield`

```java
static String withBlock(String state) {
    return switch (state) {
        case "ON" -> {
            String message = "enabled";
            yield message;
        }
        default -> "other";
    };
}
```

Ở đây `yield message;` phát ra giá trị của **switch expression**, không phải kết thúc toàn bộ phương thức. Không dùng `break message;` trong Java 14+; một số bài viết về preview Java 12 có thể dùng cú pháp `break value` lịch sử, nhưng **đó không phải cú pháp cuối cùng**.

Điểm mấu chốt: **`case ... ->` không đồng nghĩa với pattern matching**. Arrow rules và switch expression đã final từ Java 14; nhưng `case String s -> ...` trong pattern switch chưa final cho đến **Java 21**.

## 5. Java 16: type pattern với instanceof và record declaration

### 5.1. Type pattern chính thức

```java
static String newStyle(Object value) {
    if (value instanceof String text) {
        return text.toUpperCase(java.util.Locale.ROOT);
    }
    return "other";
}
```

`String text` là một **type pattern**. Khi `instanceof` khớp, biến `text` được ràng buộc với giá trị đã kiểm tra và có kiểu `String`. Không cần thêm cast.

Với điều kiện ngắn mạch:

```java
if (value instanceof String text && !text.isEmpty()) {
    System.out.println(text);
}
```

Vế phải của `&&` chỉ chạy nếu pattern ở vế trái thành công; điều này bảo đảm `text` khả dụng. Đây là **flow scoping**, khác phạm vi khối đơn thuần. Khi `value == null`, `instanceof` trả `false`, không ném `NullPointerException`.

**Sai thường gặp:**

```java
// Sai: vế phải của || có thể chạy khi pattern không khớp.
if (value instanceof String text || text.isEmpty()) {
    System.out.println("...");
}
```

Cần đổi logic (thường sang `&&`) hoặc đưa điều kiện vào trong nhánh đã biết `text` hợp lệ; không thể suy ra biến pattern luôn tồn tại bên ngoài.

### 5.2. Record declaration chưa phải record pattern

Java 16 đã cho khai báo:

```java
record Point(int x, int y) {}
```

Record định nghĩa một lớp mang dữ liệu; nó không tự bật cú pháp deconstruction:

```java
// Java 16/17: dùng type pattern + accessor.
if (value instanceof Point p) {
    System.out.println(p.x() + p.y());
}
```

Còn:

```java
// Chỉ stable từ Java 21, KHÔNG phải cú pháp Java 16/17.
if (value instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

**Chênh lệch cần nhớ:** `record Point(...)` là **khai báo record**; `Point(var x, var y)` bên trong `instanceof`/`case` là **record pattern**, có vòng đời phát triển ngôn ngữ khác.

## 6. Java 17: sealed types và giới hạn của pattern switch

`sealed` cho phép mô hình hóa một tập subtype được phép:

```java
sealed interface Signal permits Text, Metric {}
record Text(String content) implements Signal {}
record Metric(int count) implements Signal {}
```

Đây là các khai báo minh họa. Vì record tự là final và triển khai `Signal`, các subtype nêu trên phù hợp làm tập biến thể đóng.

**Java 17 final hỗ trợ:**
- `sealed interface` với `permits`.
- `record`.
- `instanceof String s`.
- `switch expression` với constant case thông thường.

**Nhưng Java 17 không có pattern matching for `switch` ở dạng final.** Một ví dụ như:

```java
// Java 21 final; trên Java 17 đây chưa phải cú pháp ổn định.
return switch (signal) {
    case Text t -> t.content();
    case Metric m -> Integer.toString(m.count());
};
```

không phải đoạn code có thể biên dịch dưới target `--release 17` theo chế độ ngôn ngữ ổn định. Khi cần Java 17, có thể xử lý bằng chuỗi `if (signal instanceof Text t) ... else if ...` hoặc dùng đa hình; hoặc nếu thích preview cho mục đích thử nghiệm, phải dùng cơ chế preview của chính JDK 17, hiểu rằng cú pháp đã có thể thay đổi sau đó.

**Không sử dụng preview cho code production chỉ vì một ví dụ blog viết được.** Cần xem version và JEP cụ thể, xác định build target, runtime target và chính sách sử dụng preview của dự án.

## 7. Java 21: switch pattern, record patterns và guard when đều final

Đây là mốc cho phép viết một `switch expression` trên object với **type pattern**, **record pattern** và **guard `when`**:

```java
return switch (signal) {
    case null -> "signal:missing";
    case Text(var content) when content != null && !content.isBlank() ->
            "text:" + content.toUpperCase(java.util.Locale.ROOT);
    case Text(var content) -> "text:empty";
    case Metric(var n) when n < 0 -> "metric:negative:" + n;
    case Metric(var n) -> "metric:" + n;
};
```

Đoạn này là **phần thân của phương thức trả `String`**, giả sử `Signal`, `Text`, `Metric` đã được khai báo như ở mục 6. Chương trình đầy đủ ở mục 9.

### 7.1. Record pattern tách component

`case Text(var content)` khớp một `Text` và lấy component `content`. `var content` được suy luận kiểu `String` theo kiểu component của record. `case Metric(var n)` lấy `int`.

Record pattern có quy tắc số lượng, thứ tự và kiểu của pattern con tương ứng với component record. Ví dụ `Text(var a, var b)` sai vì `Text` chỉ có một component.

**`null` cần nhìn đúng tầng:**
- `case null` xử lý **selector `signal == null`**.
- `case Text(var content)` vẫn có thể khớp một `Text` mà `content == null`.
- Pattern lồng như `Outer(Inner(...))` **không khớp** nếu component cần khớp `Inner` lại bằng `null`, dù `Outer` tồn tại.

### 7.2. Guard dùng `when`, không đặt điều kiện trực tiếp sau tên pattern bằng `&&`

Trong preview của pattern switch trên Java 17/18, ví dụ cũ có thể viết theo dạng như:

```java
// MINH HỌA CÚ PHÁP PREVIEW CŨ — KHÔNG dùng trong Java 21 final.
case String text && !text.isEmpty() -> "non-empty";
```

Từ các vòng preview sau, cú pháp guard chuyển sang `when`; trong **Java 21 final**:

```java
// Dùng trong switch trên Object hoặc kiểu selector tương thích.
case String text when !text.isEmpty() -> "non-empty";
```

Khác với cách viết trong `instanceof`:

```java
// Đúng: && là toán tử Boolean bên ngoài instanceof pattern.
if (value instanceof String text && !text.isEmpty()) {
    System.out.println(text);
}
```

**Phân biệt chính xác:** `when` là **phần guard trong nhãn `case`** của pattern switch; `&&` vẫn là toán tử Boolean hợp lệ **trong biểu thức điều kiện**, và có thể dùng bên trong `when` như `when content != null && !content.isBlank()`.

### 7.3. Dominance và exhaustiveness

Với sealed hierarchy, compiler kiểm tra `switch expression` bao phủ những subtype được phép. Trong chương trình mẫu, `Text` và `Metric` đã đủ, cộng `case null` theo yêu cầu xử lý null của ta; không cần `default`.

Thứ tự các case cũng quan trọng:

```java
// Đúng: nhánh đặc biệt trước nhánh tổng quát.
case Metric(var n) when n < 0 -> "negative";
case Metric(var n) -> "non-negative";
```

Nếu đặt `case Metric(var n)` không guard phía trên, case có guard ở dưới bị che (**dominated**) và có thể bị compiler từ chối. Một `default` tùy tiện trong switch của sealed hierarchy cũng có thể che cảnh báo khi sau này thêm subtype mới.

### 7.4. `switch` trên null khác `instanceof` trên null

`null instanceof String s` là `false`. Nhưng `switch (signal)` với selector null không tự động đi vào `default`; nếu không xử lý `null` theo quy tắc phù hợp, có thể gặp `NullPointerException`. Pattern switch final cho phép viết `case null -> ...` để chọn chính sách rõ ràng.

## 8. Java 22: unnamed patterns với ký hiệu underscore

Java 22 chuẩn hóa **unnamed patterns and variables** (JEP 456). Dấu `_` trong vị trí unnamed pattern nghĩa là giá trị tại vị trí đó **không cần ràng buộc vào một biến có thể sử dụng**.

Ví dụ dưới đây là **đoạn Java 22+**, được đặt trong một class có các kiểu `Text`/`Metric` đã định nghĩa:

```java
static String kind22(Signal signal) {
    return switch (signal) {
        case Text(_) -> "text";
        case Metric(_) -> "metric";
        case null -> "missing";
    };
}
```

Ở đây `Text(_)` và `Metric(_)` chỉ quan tâm record variant, không quan tâm component. Không có biến nào tên `_` để đọc sau đó, và không thể dùng `_` như giá trị trong guard.

**Không nhầm:**
- `Text(var content)`: ràng buộc component vào `content` để dùng tiếp.
- `Text(_)`: khớp nhưng **bỏ qua** component, dùng từ Java 22 final.
- `var` trong khai báo biến cục bộ đã có từ Java 10, **không phải** cú pháp `_`.
- Trong Java 21, unnamed patterns từng tồn tại dưới dạng **preview (JEP 443)**; ví dụ Java 21 final trong bài **không dùng `_`**, để không cần bật preview.

**Thử nghiệm trên JDK 24:** `kind22(new Text("x"))`, `kind22(new Metric(3))` và `kind22(null)` cho chuỗi `text/metric/missing` (nếu nối kết quả bằng dấu `/`). Đây là phần mở rộng Java 22+, **không chèn** vào file Java 21 ở mục 9.

Để kiểm tra riêng đoạn dùng `_` với target Java 22 trở lên:

```bash
javac --release 22 SomeJava22File.java
```

Dùng đúng tên file thực tế mà bạn tạo cho đoạn Java 22; ví dụ trên chỉ minh họa **tùy chọn compiler**, không phải chỉ dẫn biên dịch một file đã được cung cấp trong bài.

## 9. Một chương trình Java 21 thể hiện các mốc cú pháp

Tạo file **`PatternSyntaxTimelineDemo.java`**:

```java
public class PatternSyntaxTimelineDemo {
    sealed interface Signal permits Text, Metric {}
    record Text(String value) implements Signal {}
    record Metric(int value) implements Signal {}

    // Cú pháp instanceof + cast kiểu cũ, vẫn được Java 21 chấp nhận.
    static String legacy(Object input) {
        if (input instanceof String) {
            String text = (String) input;
            return "legacy:" + text.toUpperCase(java.util.Locale.ROOT);
        }
        return "legacy:other";
    }

    // Type pattern chính thức từ Java 16.
    static String typePattern(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            return "typed:" + text.toUpperCase(java.util.Locale.ROOT);
        }
        return "typed:other";
    }

    // Switch expression final từ Java 14, không dùng pattern case.
    static String status(String value) {
        if (value == null) return "status:missing";
        return switch (value) {
            case "ON" -> "status:on";
            case "OFF" -> "status:off";
            default -> "status:unknown";
        };
    }

    // Sealed hierarchy Java 17; record + switch patterns Java 21.
    static String classify(Signal signal) {
        return switch (signal) {
            case null -> "signal:missing";
            case Text(var content) when content != null && !content.isBlank() ->
                    "text:" + content.toUpperCase(java.util.Locale.ROOT);
            case Text(var content) -> "text:empty";
            case Metric(var n) when n < 0 -> "metric:negative:" + n;
            case Metric(var n) -> "metric:" + n;
        };
    }

    public static void main(String[] args) {
        System.out.println(legacy("java"));
        System.out.println(legacy(7));
        System.out.println(typePattern("java"));
        System.out.println(typePattern(" "));
        System.out.println(status("ON"));
        System.out.println(status(null));
        System.out.println(classify(new Text("hello")));
        System.out.println(classify(new Text(null)));
        System.out.println(classify(new Metric(-2)));
        System.out.println(classify(new Metric(4)));
        System.out.println(classify(null));
    }
}
```

**Yêu cầu JDK 21+**, biên dịch và chạy:

```bash
javac --release 21 PatternSyntaxTimelineDemo.java
java PatternSyntaxTimelineDemo
```

**Stdout chính xác:**

```text
legacy:JAVA
legacy:other
typed:JAVA
typed:other
status:on
status:missing
text:HELLO
text:empty
metric:negative:-2
metric:4
signal:missing
```

Đoạn chương trình đã được chạy trong JShell của **JDK 24** và trả đúng 11 dòng trên. Việc sử dụng `java.util.Locale.ROOT` giúp chuyển chữ hoa ổn định, tránh phụ thuộc locale máy chạy.

**Chú ý về câu “chạy được trên Java 14/16/17”:** File đầy đủ này **không thể** biên dịch với target thấp hơn Java 21, vì nó chứa cả record patterns và pattern switch final. Các nhãn chú thích trong file chỉ cho biết **thời điểm từng cú pháp riêng lẻ trở thành final**. Muốn xây ví dụ thực sự target Java 14/16/17 phải **loại bỏ hoặc thay** mọi cú pháp ra đời sau version đó, không chỉ đổi số trong `--release`.

### 9.1. Cách tự kiểm tra phiên bản compiler/runtime

```bash
javac -version
java -version
```

Nếu codebase cần phát hành cho Java 17, chỉ thay `java -version` trên máy local **không đủ** để bảo đảm tính tương thích. Hãy build bằng JDK thích hợp và `javac --release 17` (hoặc cấu hình toolchain của Maven/Gradle tương đương), đồng thời chạy test trên runtime Java 17.

`--release` kiểm soát target phiên bản source/API/class file tương ứng, nhưng **không tự chuyển cú pháp Java 21 thành cú pháp Java 17**. File Java 21 ở trên phải được refactor trước khi hạ target.

## 10. Các lỗi biên dịch thường gặp khi copy syntax sai phiên bản

| Triệu chứng | Nguyên nhân thường gặp | Hướng khắc phục |
| --- | --- | --- |
| `instanceof String text` bị báo lỗi dưới `--release 11` | Type pattern chưa final ở Java 11 | Dùng `instanceof String` + cast hoặc nâng target lên Java 16+ |
| `record Point(...)` không được nhận dưới `--release 11` | Record final từ Java 16 | Dùng class thường, hoặc nâng target |
| `Point(var x, var y)` lỗi dưới `--release 17` | Record patterns final Java 21 | Dùng `instanceof Point p` rồi `p.x()`/`p.y()` |
| `switch` với `case Text t ->` lỗi khi target 17 không preview | Pattern switch chưa final Java 17 | Dùng chuỗi `instanceof`/polymorphism, hoặc target 21+ |
| `case String s && test(s)` không biên dịch ở Java 21 | Guard syntax là preview cũ | Sửa thành `case String s when test(s) ->` |
| `case ... when ...` báo lỗi trong switch Java 14 | Pattern switch chưa final | Đưa điều kiện vào block hoặc nâng target 21 |
| `yield` trong switch expression lỗi với source Java 11 | Switch expression chưa final | Dùng switch statement + biến kết quả, hoặc nâng target 14 |
| `case null` của pattern switch lỗi với source cũ | Không có cơ chế pattern switch final tương ứng | Guard null trước switch; trên Java 21 dùng `case null` khi phù hợp |
| `case Text(_)` lỗi dưới `--release 21` chế độ final | Unnamed patterns final Java 22 | Dùng `case Text(var ignored)` hoặc nâng target 22+ |
| `var` dùng với field, tham số hay record pattern ở phiên bản không hỗ trợ | Nhầm `var` local với kiểu/pattern và version | Dùng khai báo kiểu rõ hoặc đúng cú pháp/phiên bản |
| `Class file version ... is newer`, `UnsupportedClassVersionError` | Chạy class được biên dịch cho Java mới trên runtime cũ | Build đúng `--release`, hoặc nâng runtime tương ứng |
| Build chỉ thành công khi bật preview | Code dùng tính năng preview của version đó | Quyết định chính sách preview; không coi là cú pháp final/portable |

### 10.1. Kiểm thử lỗi compile thay vì đoán

Hai đoạn sau **cố tình sai**, không được đưa vào file ví dụ chạy:

```java
// Sai số component: record Text chỉ có một component.
static boolean badArity(Object value) {
    return value instanceof Text(var first, var second);
}
```

```java
// Lỗi flow scoping: text có thể chưa được gán sau nhánh if.
static void badScope(Object value) {
    if (value instanceof String text) {
        System.out.println(text);
    }
    System.out.println(text); // Không hợp lệ.
}
```

Trong môi trường JDK 24, ca sai số component bị từ chối với lỗi `incorrect number of nested patterns`. Ca phạm vi biến cũng bị từ chối khi compiler không thể thấy `text` có giá trị ở dòng sau. Những đoạn này được thiết kế để kiểm tra kiến thức compile-time, không phải để tạo stdout runtime.

Đoạn guard preview cũ:

```java
// CỐ TÌNH SAI trong Java 21 final (và JDK 24).
case String s && !s.isEmpty() -> "text";
```

cũng đã được thử và bị trình biên dịch JDK 24 từ chối. Cần `case String s when !s.isEmpty() -> "text";` bên trong pattern switch tương thích.

## 11. Hiểu đúng preview features khi đọc mã nguồn cũ

Tính năng Java thường trải qua chu kỳ: đề xuất qua JEP, có thể **preview một hoặc nhiều vòng**, nhận phản hồi, thay đổi cú pháp/semantics, rồi **final**. Preview **không** có nghĩa “đã có từ version đó nên dùng mãi được”.

Với một dự án cố ý dùng preview ở đúng phiên bản JDK của nó, thường cần cờ preview tại thời điểm biên dịch/chạy, chẳng hạn minh họa kiểu lệnh:

```bash
# Chỉ khi code thực sự dùng một tính năng preview của Java 20:
javac --enable-preview --release 20 PreviewExample.java
java --enable-preview PreviewExample
```

`PreviewExample.java` là tên **giả định** cho ví dụ preview riêng, không phải file được cung cấp trong bài này. Cờ preview không “mở khóa” mọi cú pháp final của Java tương lai trên compiler cũ. Preview class files có quy tắc version/runtime riêng và có thể không chạy trên JDK phiên bản khác; không dùng một kết quả test trên JDK 24 để khẳng định mã preview Java 17 vẫn sẽ hợp lệ.

Cách đọc hướng dẫn trên mạng:

1. Xác định **Java version** mà bài sử dụng.
2. Phân biệt **preview** và **final** ở version đó.
3. Đối chiếu syntax guard, record pattern, `case null`, `yield` và `_` với **source level của dự án**.
4. Chọn hướng migration: giữ phiên bản đang được hỗ trợ với cú pháp tương ứng, hoặc nâng JDK/toolchain có kiểm thử.
5. Đọc **JEP final** để xác nhận semantics thay vì chép đoạn code preview đã lỗi thời.

## 12. Hướng nâng cấp source qua các mức Java

**Đích Java 8/11:** Dùng `instanceof Type` + cast, `switch statement` truyền thống. Không dùng record declaration, sealed hierarchy, record patterns hay switch patterns.

**Đích Java 14:** Có switch expression và `yield` final. Vẫn cần cast sau `instanceof`; không giả định type patterns đã final. `case ... ->` ở đây có thể chỉ là constant cases, không phải pattern matching.

**Đích Java 16:** Đổi các `instanceof` lặp cast thành `instanceof Type variable`. Có thể dùng record declarations, nhưng tách record component vẫn qua accessor.

**Đích Java 17:** Có sealed types final, thuận tiện cho domain model đóng; dùng type pattern trong `instanceof`, chưa dùng pattern switch final. Nếu có code Java 21 đang hạ cấp xuống 17, chuyển `switch` theo pattern thành `if/else instanceof` hoặc polymorphism.

**Đích Java 21:** Sử dụng record patterns và switch patterns final, nested deconstruction, `when` guards, `case null` và exhaustiveness với sealed hierarchy. Không cần cờ preview cho các tính năng này.

**Đích Java 22+:** Nếu muốn bỏ qua component không cần dùng bằng `_`, có thể dùng unnamed patterns final. Kiểm tra công cụ formatter, IDE và pipeline build đã hỗ trợ source level tương ứng.

### Bảng chọn cú pháp theo bài toán

| Bài toán | Java 8/11 | Java 16/17 | Java 21 | Java 22+ |
| --- | --- | --- | --- | --- |
| Kiểm tra Object có phải String | `v instanceof String` rồi cast | `v instanceof String s` | Cùng cách Java 16 | Cùng cách |
| Tạo kiểu dữ liệu nhỏ | Class thường | `record Point(...)` | Record | Record |
| Lấy hai component Point | `Point p = ...; p.x()/p.y()` | `instanceof Point p` rồi accessor | `instanceof Point(var x, var y)` | Cùng cách; có thể dùng `_` cho component bỏ qua |
| Phân nhánh nhiều subtype | `if` + cast, virtual dispatch | `if` + type pattern | `switch(object)` + pattern cases | Pattern cases, có thể thêm unnamed patterns |
| Guard trong pattern switch | Không có | Không phải cú pháp final trong 17 | `case T t when condition ->` | Cùng cách |
| Switch trả giá trị | `switch statement` + biến | `switch expression` | Switch expression có pattern | Như Java 21, thêm tính năng sau 21 nếu muốn |

Lưu ý dòng “Java 16/17”: nhóm này chỉ mô tả những cú pháp **chung đã final trong cả Java 16 và 17**. `sealed` riêng biệt final từ Java 17. Nhóm “Java 22+” chỉ khẳng định các cú pháp được nhắc tới đã tồn tại kể từ Java 22, không tuyên bố mọi tính năng preview khác ở các JDK mới đều đã final.

## 13. Bài tập: xác định phiên bản tối thiểu và sửa code

**Bài 1.** Cho:

```java
if (obj instanceof String text && text.length() > 2) {
    System.out.println(text);
}
```

Cú pháp pattern `String text` chính thức từ **Java 16**. Viết phiên bản Java 11: kiểm tra `obj instanceof String` rồi cast bên trong nhánh.

**Bài 2.** Cho:

```java
return switch (state) {
    case "OK" -> "success";
    default -> "error";
};
```

Nếu `state` là `String`, switch expression với arrow rules chính thức từ **Java 14**. Không cần pattern matching for `switch` để dùng dạng này. Với Java 11, viết statement + biến `result` hoặc `return` tương ứng.

**Bài 3.** Cho:

```java
return switch (point) {
    case Point(var x, var y) when x > 0 -> "right";
    case Point(var x, var y) -> "other";
    case null -> "missing";
};
```

Giả sử `Point` là record và selector có kiểu thích hợp, tổ hợp record pattern + pattern switch + `when` ở dạng final yêu cầu **Java 21**. Nếu phải chạy Java 17, thay bằng:

```java
// Trong phương thức có biến point kiểu Point.
if (point == null) {
    return "missing";
}
if (point.x() > 0) {
    return "right";
}
return "other";
```

**Bài 4.** Cho `case Point(var x, _) -> ...`. Hãy giải thích `_` là unnamed pattern final từ **Java 22**; trên Java 21 chế độ không preview phải thay bằng `case Point(var x, var ignored) -> ...` và không dùng `ignored`, hoặc bỏ việc deconstruct component không cần.

**Bài 5.** Thiết lập hai CI jobs cho dự án hỗ trợ Java 17 và 21: một job build/test với `--release 17`, job còn lại build/test Java 21. Nếu một file chứa `case Text(var content)`, hãy đưa vào job 21 hoặc viết lại cho job 17. Không “làm lơ” lỗi compiler bằng cách bật preview của JDK 17 mà không kiểm soát sự khác biệt cú pháp.

## 14. Tổng kết

- **Java 14:** switch expression, arrow rules và `yield` final.
- **Java 16:** type patterns cho `instanceof`, record declaration final.
- **Java 17:** sealed types final, nhưng pattern switch chưa final.
- **Java 21:** record patterns và pattern matching for `switch` final, guard dùng `when`.
- **Java 22:** unnamed patterns/variables `_` final.
- **Preview** là khả năng thử nghiệm của **phiên bản cụ thể**, không đồng nghĩa với syntax ổn định trên các phiên bản sau.
- **Compatibility phải kiểm tra cả source level, compiler/toolchain và runtime**. Đừng dựa vào việc một đoạn snippet biên dịch trên JDK mới rồi khẳng định nó chạy ở target cũ.

### Tài liệu chính thức

- [JEP 361 — Switch Expressions (Java 14)](https://openjdk.org/jeps/361)
- [JEP 394 — Pattern Matching for instanceof (Java 16)](https://openjdk.org/jeps/394)
- [JEP 395 — Records (Java 16)](https://openjdk.org/jeps/395)
- [JEP 409 — Sealed Classes (Java 17)](https://openjdk.org/jeps/409)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [JEP 443 — Unnamed Patterns and Variables, Preview (Java 21)](https://openjdk.org/jeps/443)
- [JEP 456 — Unnamed Patterns and Variables (Java 22)](https://openjdk.org/jeps/456)
- [Oracle Java 21 Language Guide — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 Language Guide — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
