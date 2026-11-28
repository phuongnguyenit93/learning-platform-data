# Áp dụng mẫu nguyên thủy trong switch với guard phù hợp

> **Chương:** Mẫu kiểu nguyên thủy  
> **Phiên bản trọng tâm:** Java 25 — JEP 507, lần preview thứ ba.  
> **Mục tiêu:** Dùng primitive type pattern trong `switch`, kết hợp guard `when` để phân loại giá trị theo miền nghiệp vụ và tránh ép kiểu làm mất thông tin.

## 1. Vì sao switch cần mẫu kiểu nguyên thủy?

Trước Java 25, `switch` hỗ trợ các selector như `byte`, `short`, `char`, `int`, enum, `String` và một số kiểu tham chiếu. Muốn phân loại `long`, `float`, `double` hoặc `boolean` theo nhiều miền giá trị, code thường phải kết hợp `if/else`, ép kiểu hoặc boxing.

Ví dụ, một hệ thống nhận điểm đo dạng `double` cần phân biệt:

- Giá trị không phải số (`NaN`).
- Giá trị nằm ngoài miền cho phép.
- Giá trị nguyên có thể chuyển chính xác sang `int`.
- Giá trị thập phân nằm trong miền hợp lệ.

Một chuỗi ép kiểu trực tiếp như `(int) value` có thể cắt phần thập phân, tràn miền hoặc biến `NaN` thành một giá trị số nguyên. Nếu mục đích là **kiểm tra xem phép chuyển kiểu có an toàn hay không**, ép kiểu trước rồi kiểm tra sau dễ tạo lỗi.

Primitive type patterns cho phép đưa kiểm tra kiểu và kiểm tra khả năng chuyển đổi vào quá trình pattern matching. Guard `when` bổ sung điều kiện nghiệp vụ sau khi pattern đã khớp.

### Kết quả cần đạt

Sau bài này, bạn có thể:

1. Dùng primitive type pattern trong `switch` statement và expression.
2. Dùng `when` để giới hạn giá trị khớp theo miền nghiệp vụ.
3. Phân biệt case constant với case pattern.
4. Hiểu phép testing conversion và điều kiện chuyển đổi chính xác.
5. Sắp xếp label tránh dominance và bảo đảm switch exhaustive.
6. Xử lý selector kiểu wrapper có thể là `null`.
7. Biên dịch và chạy ví dụ theo đúng preview flags của Java 25.
8. Xác định giới hạn khi nâng cấp sang JDK mới hơn.

## 2. Trạng thái tính năng: Java 25 vẫn là preview

Primitive types in patterns, `instanceof`, and `switch` được phát triển qua nhiều lần preview:

| JDK | JEP | Trạng thái |
|---|---|---|
| Java 23 | JEP 455 | Preview lần 1 |
| Java 24 | JEP 488 | Preview lần 2 |
| Java 25 | JEP 507 | Preview lần 3 |
| Java 26 | JEP 530 | Preview lần 4 |
| Java 27 | JEP 532 | Preview lần 5 |

Tại ngày 27-11-2026, tài liệu Java SE 27 vẫn đánh dấu tính năng này là preview. Vì vậy, đây là kiến thức vẫn đang được phát triển và có giá trị học tập, nhưng không được coi là cú pháp Java ổn định để mặc định đưa vào production.

Trong Java 25:

- Primitive type patterns là preview.
- Primitive values làm selector của `switch` (bao gồm `long`, `float`, `double` và `boolean` cùng các wrapper tương ứng) là preview.
- Guard `when` vốn đã có trong pattern switch từ Java 21; phần mở rộng cho primitive patterns thuộc JEP 507.
- Không cần nhầm tính năng này với một Java API hay thư viện bên ngoài.

**Quan trọng:** cú pháp preview có thể thay đổi giữa các JDK. Bài thực hành bên dưới nhắm đúng Java 25 và dùng JEP 507. Khi dùng Java 26/27, phải biên dịch lại theo preview của release đó và kiểm tra JEP tương ứng; không lấy class file preview của JDK 25 chạy trực tiếp trên JDK khác.

## 3. Biên dịch và chạy preview trên JDK 25

Kiểm tra compiler/runtime:

~~~bash
java --version
javac --version
~~~

Với JDK 25, biên dịch chương trình dùng primitive patterns bằng:

~~~bash
javac --release 25 --enable-preview -d out PrimitiveSwitchDemo.java
~~~

Chạy bằng JDK 25 và bật preview:

~~~bash
java --enable-preview -cp out PrimitiveSwitchDemo
~~~

Hai điều kiện cần giữ đồng bộ:

- Khi compile, dùng `--enable-preview` và `--release 25` (hoặc source level 25).
- Khi run, dùng `--enable-preview` trên đúng JDK 25.

Nếu compiler báo preview feature không được bật, kiểm tra JDK thực tế và hai cờ trên. Nếu chạy class preview bằng JDK release khác, hãy biên dịch lại bằng release mục tiêu và preview flags của release đó.

## 4. Primitive type pattern trong switch hoạt động ra sao?

Một type pattern có dạng:

~~~java
case int value -> ...
~~~

Pattern khai báo biến `value` có kiểu `int`. Khi selector khớp pattern, biến được khởi tạo bằng giá trị đã chuyển đổi chính xác sang kiểu pattern.

Java 25 cho phép dùng tất cả primitive types làm selector `switch`:

| Selector | Ví dụ | Ghi chú |
|---|---|---|
| `byte`, `short`, `char`, `int` | `switch (count)` | Các kiểu đã được hỗ trợ từ trước; primitive patterns là phần preview mới |
| `long` | `switch (duration)` | Có thể dùng case constant và primitive type pattern |
| `float` | `switch (ratio)` | Case constant phải đúng kiểu `float` |
| `double` | `switch (measurement)` | Case constant phải đúng kiểu `double` |
| `boolean` | `switch (enabled)` | Có thể phân nhánh theo `true` và `false` |
| Wrapper tương ứng | `Long`, `Float`, `Double`, `Boolean`... | Có thể có giá trị `null`; phải xét semantics của reference selector |

Ví dụ với `long`:

~~~java
static String classifyDuration(long millis) {
    return switch (millis) {
        case 0L -> "zero";
        case long value when value < 0L -> "negative";
        case long value when value <= 60_000L -> "up to one minute";
        case long value -> "over one minute";
    };
}
~~~

Ở đây:

1. `case 0L` xử lý một giá trị cụ thể.
2. `case long value when ...` khớp primitive type pattern rồi kiểm tra guard.
3. `case long value` là pattern không guard, bắt mọi giá trị còn lại.
4. Vì pattern cuối bao phủ mọi giá trị `long`, switch expression là exhaustive.

Dùng hậu tố `L` cho hằng số `long`. Không viết `case 0` trong switch có selector `long`; với các selector `long`, `float` và `double`, case constants phải có đúng kiểu tương ứng.

## 5. Guard when: điều kiện được kiểm tra sau pattern

Guard có dạng:

~~~java
case int value when value >= 0 && value <= 100 -> ...
~~~

Trình tự xử lý:

1. JVM kiểm tra selector có khớp pattern `int value` bằng testing conversion chính xác hay không.
2. Nếu pattern không khớp, guard không được đánh giá; JVM xét label tiếp theo.
3. Nếu pattern khớp, biến `value` được khởi tạo.
4. Guard `when` được đánh giá.
5. Guard là `true` thì label được chọn; nếu `false` thì JVM xét label tiếp theo.

Sơ đồ:

~~~mermaid
flowchart TD
    A["Selector value"] --> B{"Khớp primitive pattern?"}
    B -->|Không| C["Xét case label tiếp theo"]
    B -->|Có| D["Khởi tạo pattern variable"]
    D --> E["Đánh giá when guard"]
    E -->|true| F["Chạy nhánh case"]
    E -->|false| C
~~~

Guard phải có kiểu `boolean` hoặc `Boolean`. Biến local, parameter hoặc exception parameter được dùng trong guard phải là `final` hoặc effectively final theo quy tắc ngôn ngữ.

**Nên giữ guard thuần và dễ đọc.** Một guard nên kiểm tra range, trạng thái hoặc điều kiện nghiệp vụ. Tránh gọi API có side effect, ghi database hoặc gửi message trong guard; thứ tự case và việc guard được đánh giá chỉ sau khi pattern khớp có thể khiến các side effect khó dự đoán.

## 6. Ví dụ 1 — Phân loại số nguyên bằng guard

Một dịch vụ tính phí cần phân loại số tiền theo đơn vị cent:

- Giá trị âm: dữ liệu không hợp lệ hoặc khoản hoàn tiền cần xử lý riêng.
- 0: không phát sinh phí.
- 1 đến 100.000 cent: khoản nhỏ.
- Lớn hơn 100.000 cent: khoản lớn.

Tạo file `PrimitiveSwitchDemo.java`:

~~~java
public class PrimitiveSwitchDemo {

    static String classifyAmount(long cents) {
        return switch (cents) {
            case 0L ->
                "zero";

            case long value when value < 0L ->
                "negative";

            case long value when value <= 100_000L ->
                "small";

            case long value ->
                "large";
        };
    }

    public static void main(String[] args) {
        System.out.println(classifyAmount(-50));
        System.out.println(classifyAmount(0));
        System.out.println(classifyAmount(5_000));
        System.out.println(classifyAmount(250_000));
    }
}
~~~

Kết quả mong đợi:

~~~text
negative
zero
small
large
~~~

Phân tích:

- `case 0L` là case constant, xử lý chính xác giá trị 0.
- Guard đầu tiên bắt các giá trị âm.
- Guard thứ hai bắt giá trị còn lại không lớn hơn 100.000, tức khoảng 1 đến 100.000.
- Pattern `case long value` cuối là catch-all cho các giá trị còn lại.

Ví dụ dùng `long` để biểu diễn cent, tránh dùng `double` cho số tiền. Primitive patterns giúp phân loại giá trị; chúng không thay thế quy tắc biểu diễn tiền tệ chính xác của ứng dụng.

## 7. Ví dụ 2 — Kết hợp guard với kiểm tra chuyển đổi chính xác

Một điểm quan trọng của primitive patterns là **pattern không đồng nghĩa với ép kiểu thông thường**.

Giả sử selector có kiểu `double` nhưng một nhánh chỉ nhận số nguyên có thể biểu diễn chính xác bằng `int`:

~~~java
static String classifyMeasurement(double value) {
    return switch (value) {
        case double d when Double.isNaN(d) ->
            "not a number";

        case int whole when whole >= 0 && whole <= 100 ->
            "whole value in range";

        case double d when d < 0.0d ->
            "below range";

        case double d when d > 100.0d ->
            "above range";

        case double d ->
            "fractional value in range";
    };
}
~~~

Ví dụ:

~~~java
System.out.println(classifyMeasurement(42.0d));
System.out.println(classifyMeasurement(42.5d));
System.out.println(classifyMeasurement(-2.0d));
System.out.println(classifyMeasurement(150.0d));
System.out.println(classifyMeasurement(Double.NaN));
~~~

Kết quả:

~~~text
whole value in range
fractional value in range
below range
above range
not a number
~~~

Vì sao `42.0d` khớp `case int whole` nhưng `42.5d` không khớp?

- Chuyển `42.0d` sang `int` tạo ra 42 và không mất thông tin; testing conversion là exact.
- Chuyển `42.5d` sang `int` sẽ bỏ phần thập phân; testing conversion là inexact nên pattern không khớp.
- Nếu conversion inexact, kết quả chuyển đổi bị loại bỏ như thể pattern chưa từng khớp. Guard của pattern đó không được chạy.
- Các label sau tiếp tục được xét; pattern `double d` cuối cùng nhận các giá trị còn lại.

Cơ chế này khác với `(int) value`: ép kiểu số học có thể làm mất phần thập phân hoặc thay đổi giá trị. Primitive pattern dùng kiểm tra exactness để chỉ khớp khi việc chuyển đổi giữ nguyên thông tin.

### Bảng minh họa exact conversion

| Selector `double` | Pattern `int n` có khớp? | Lý do |
|---:|---|---|
| `42.0d` | Có | Giá trị nguyên biểu diễn chính xác |
| `42.5d` | Không | Mất phần thập phân |
| `-2.0d` | Có | Chuyển chính xác sang -2; guard range quyết định nhánh |
| `1.0e20` | Không | Ngoài miền biểu diễn của `int` |
| `Double.NaN` | Không | Chuyển sang số nguyên không bảo toàn giá trị |
| `Double.POSITIVE_INFINITY` | Không | Không thể biểu diễn bằng `int` |

Lưu ý: `case int whole` chỉ quyết định khả năng chuyển đổi và khởi tạo biến. Guard vẫn phải kiểm tra miền nghiệp vụ. Ví dụ `-2.0d` khớp pattern `int`, nhưng guard `whole >= 0` là false; label tiếp theo mới xử lý giá trị âm.

## 8. Ví dụ 3 — Wrapper có thể null và primitive pattern

Một selector kiểu wrapper là reference, vì vậy nó có thể là `null`. Có thể kết hợp `case null` với primitive type pattern:

~~~java
static String classifyBoxed(Integer value) {
    return switch (value) {
        case null ->
            "missing";

        case int number when number < 0 ->
            "negative";

        case int number when number == 0 ->
            "zero";

        default ->
            "positive";
    };
}
~~~

Kết quả:

~~~java
System.out.println(classifyBoxed(null)); // missing
System.out.println(classifyBoxed(-3));   // negative
System.out.println(classifyBoxed(0));    // zero
System.out.println(classifyBoxed(8));    // positive
~~~

Ở selector `Integer`:

- `case null` xử lý reference null trước khi unboxing.
- `case int number` dùng testing conversion gồm unboxing từ `Integer` sang `int`.
- Guard chỉ được chạy khi pattern đã khớp.
- `default` nhận giá trị không được các guard trước xử lý.

Nếu selector reference là `null` mà switch không có `case null`, switch sẽ ném `NullPointerException`. Không giả định primitive pattern tự xử lý null thay cho nhánh null tường minh.

## 9. Case constants và kiểu selector phải tương thích

Với selector `long`, `float` hoặc `double`, case constant phải có cùng primitive type với selector. Java không tự mở rộng literal khác kiểu trong case constant của các selector này.

~~~java
static String describeTemperature(double temperature) {
    return switch (temperature) {
        case 0.0d -> "freezing point";
        case 100.0d -> "boiling point";
        case double t when t < 0.0d -> "below freezing";
        case double t when t > 100.0d -> "above boiling";
        case double t -> "between endpoints";
    };
}
~~~

Ví dụ sau không hợp lệ với selector `double`:

~~~java
switch (temperature) {
    case 0 -> "zero"; // Không dùng int literal cho double selector
    default -> "other";
}
~~~

Hãy viết `0.0d` hoặc `0d` để biểu thị hằng số kiểu `double`. Tương tự:

| Selector | Literal đúng kiểu |
|---|---|
| `long` | `0L` |
| `float` | `0.0f` |
| `double` | `0.0d` |
| `boolean` | `true` hoặc `false` |

Với selector `boolean`, hai case constants `true` và `false` có thể bao phủ toàn bộ miền giá trị. Không đặt thêm pattern hoặc default dư thừa sau một pattern không guard đã bao phủ mọi giá trị.

## 10. Thứ tự case, dominance và exhaustive switch

`switch` xét các label theo thứ tự xuất hiện. Compiler cũng kiểm tra dominance: nếu một label trước đó chắc chắn bao phủ mọi giá trị của label sau, label sau là unreachable và gây compile-time error.

### Thứ tự khuyến nghị

Với selector số nguyên, nên đặt:

1. Case constants cụ thể.
2. Guarded patterns theo miền hẹp đến rộng.
3. Pattern không guard để nhận phần còn lại.

~~~java
static String category(int value) {
    return switch (value) {
        case 0 -> "zero";
        case int n when n < 0 -> "negative";
        case int n when n <= 100 -> "small positive";
        case int n -> "large positive";
    };
}
~~~

### Pattern không guard có thể dominate pattern sau

Đoạn sau không hợp lệ:

~~~java
switch (value) {
    case int n -> "any integer";
    case int n when n > 0 -> "positive"; // Bị pattern phía trên dominate
}
~~~

`case int n` đầu tiên là pattern không guard và khớp mọi giá trị `int`. Do đó, label phía sau không bao giờ được xét.

Đảo thứ tự để guard được đánh giá trước:

~~~java
switch (value) {
    case int n when n > 0 -> "positive";
    case int n -> "zero or negative";
}
~~~

Guarded pattern không được coi là dominate một unguarded pattern cùng kiểu chỉ vì cùng khai báo kiểu. Đây là cách phổ biến để phân loại một nhóm con trước, rồi dùng pattern không guard làm nhánh còn lại.

### Switch expression phải exhaustive

Switch expression luôn phải bao phủ mọi trường hợp. Một pattern không guard có thể làm nhánh cuối:

~~~java
static String label(long value) {
    return switch (value) {
        case long n when n < 0L -> "negative";
        case long n when n == 0L -> "zero";
        case long n -> "positive";
    };
}
~~~

Pattern cuối `case long n` là unconditional đối với selector `long`, nên switch expression đầy đủ. Với selector wrapper, phải xem xét cả `null`; pattern primitive không làm reference null trở thành một giá trị primitive hợp lệ.

## 11. Những lỗi thường gặp khi viết guard

| Lỗi | Vì sao sai hoặc khó bảo trì | Cách xử lý |
|---|---|---|
| Dùng `case int n` trước các guard cụ thể | Pattern không guard có thể dominate các case sau | Đặt guard cụ thể trước pattern tổng quát |
| Dùng `case 0` cho selector `double` | Case constant không cùng kiểu selector | Dùng `0.0d` |
| Cho rằng pattern là ép kiểu thông thường | Pattern chỉ khớp khi testing conversion exact | Kiểm tra miền và độ chính xác của phép chuyển |
| Bỏ qua `NaN` | So sánh `NaN < x` và `NaN > x` đều false | Xử lý `Double.isNaN` trước các range guard |
| Không xử lý infinity | Infinity có thể lọt qua các guard range nếu viết thiếu | Kiểm tra biên dưới/trên hoặc dùng guard tổng quát |
| Không xử lý null của wrapper | Switch selector null có thể ném NPE | Thêm `case null` nếu null là đầu vào hợp lệ |
| Guard có side effect | Guard chỉ chạy sau khi pattern khớp và theo thứ tự label | Giữ guard thuần, không thực hiện I/O |
| Guard gọi hàm có thể trả Boolean null | Unboxing kết quả guard có thể ném NPE | Trả primitive boolean hoặc bảo đảm không null |
| Trộn literal số không cùng kiểu | Java 25 yêu cầu case constant đúng kiểu cho long/float/double | Dùng hậu tố L, f, d phù hợp |
| Dùng preview mà quên cờ compile/run | Compiler hoặc JVM từ chối preview feature | Đồng bộ --release và --enable-preview |
| Dùng class preview của JDK25 trên JDK27 | Preview class file gắn với release tạo ra nó | Recompile bằng JDK mục tiêu và preview flags của release đó |

### Guard không phải nơi thay thế validation đầu vào

Guard thích hợp để chọn nhánh theo điều kiện. Nếu input cần được kiểm tra một lần, chuẩn hóa hoặc ghi log nghiệp vụ, hãy thực hiện trước switch. Đừng lặp lại cùng một validation có side effect ở nhiều guard.

## 12. Hiểu khác biệt giữa pattern matching và cast

| Cách viết | Hành vi |
|---|---|
| `int n = (int) value` | Thực hiện cast; có thể cắt phần thập phân hoặc làm mất thông tin |
| `if (value instanceof int n)` | Kiểm tra testing conversion exact; chỉ khởi tạo `n` nếu chuyển đổi chính xác |
| `case int n when ...` | Kiểm tra pattern exact trong switch, sau đó đánh giá guard |
| `case 10 -> ...` | So sánh selector với case constant theo quy tắc tương thích kiểu |

Ví dụ safe cast:

~~~java
static String safeInt(double value) {
    if (value instanceof int exact) {
        return "exact int: " + exact;
    }
    return "not exactly representable as int";
}
~~~

Đoạn này cũng dùng primitive pattern preview trong Java 25. Khi không khớp, chương trình không thực hiện phép cast gây mất dữ liệu.

Dùng pattern khi điều kiện cần là **giá trị có thể chuyển đổi chính xác**. Nếu nghiệp vụ muốn làm tròn, cắt phần thập phân hoặc chấp nhận sai số, hãy viết rõ chính sách bằng API số học phù hợp thay vì kỳ vọng pattern tự làm tròn.

## 13. Kiểm thử hành vi của switch và guard

Với preview feature, kiểm thử nên bao phủ:

- Biên dưới, biên trên và giá trị nằm ngay ngoài biên.
- Giá trị nguyên và giá trị thập phân.
- Giá trị có thể chuyển đổi chính xác và không chính xác.
- `NaN`, positive/negative infinity với selector floating point.
- `null` với selector wrapper.
- Nhánh guard false để xác nhận label tiếp theo được xét.
- Các giá trị case constant và pattern tổng quát.

Ví dụ test thủ công:

~~~java
static void verify() {
    assert classifyMeasurement(42.0d).equals("whole value in range");
    assert classifyMeasurement(42.5d).equals("fractional value in range");
    assert classifyMeasurement(-2.0d).equals("below range");
    assert classifyMeasurement(150.0d).equals("above range");
    assert classifyMeasurement(Double.NaN).equals("not a number");

    assert classifyBoxed(null).equals("missing");
    assert classifyBoxed(-1).equals("negative");
    assert classifyBoxed(0).equals("zero");
    assert classifyBoxed(1).equals("positive");
}
~~~

Các assertion trên minh họa các trường hợp cần xác minh; trong dự án thực tế, dùng JUnit hoặc test framework hiện hành để tự động hóa. Không chỉ test các giá trị thông thường: lỗi thường xuất hiện ở biên chuyển đổi kiểu, `NaN`, infinity và wrapper null.

## 14. Checklist và bài tập áp dụng

### Checklist

- [ ] Xác định rõ JDK mục tiêu; ví dụ trong bài nhắm JDK 25.
- [ ] Bật preview đúng lúc compile và run.
- [ ] Dùng primitive type pattern khi muốn kiểm tra kiểu hoặc khả năng chuyển đổi chính xác.
- [ ] Dùng guard `when` cho điều kiện miền nghiệp vụ sau khi pattern khớp.
- [ ] Đặt constant labels trước pattern tổng quát.
- [ ] Đặt guarded patterns trước unguarded catch-all pattern.
- [ ] Bảo đảm switch expression exhaustive.
- [ ] Kiểm tra `null` nếu selector là wrapper/reference.
- [ ] Kiểm tra `NaN` và infinity khi selector là `float`/`double`.
- [ ] Không dùng primitive pattern như phép ép kiểu có chủ ý làm mất thông tin.
- [ ] Không dùng guard để thực hiện side effect.
- [ ] Biên dịch lại khi đổi JDK release; không tái sử dụng preview class file từ release khác.

### Bài tập A — Phân loại thời gian xử lý

Viết hàm nhận `long elapsedMillis`:

- 0: `"instant"`.
- Âm: `"invalid"`.
- 1 đến 500: `"fast"`.
- 501 đến 5.000: `"normal"`.
- Lớn hơn 5.000: `"slow"`.

Dùng case constant và primitive pattern có guard. Đảm bảo pattern tổng quát ở cuối.

### Bài tập B — Chuyển đổi số đo an toàn

Viết hàm nhận `double`:

- `NaN`: dữ liệu không hợp lệ.
- Giá trị nguyên trong miền 0 đến 255: có thể chuyển chính xác sang `byte`.
- Giá trị ngoài miền: báo vượt ngưỡng.
- Giá trị có phần thập phân: báo không phải số nguyên.

Dùng `case byte b when ...` và giải thích tại sao 255.0 có thể khớp nhưng 255.5 không khớp pattern `byte`.

### Bài tập C — Wrapper có null

Viết hàm nhận `Long` để phân loại:

- `null`: thiếu dữ liệu.
- Số âm: số dư âm.
- 0: không có số dư.
- Số dương: có số dư.

Thử dùng primitive pattern `long n` sau nhánh `case null`.

### Câu hỏi tự đánh giá

1. Guard được đánh giá trước hay sau khi primitive type pattern khớp?
2. Nếu guard trả về false, switch xử lý thế nào?
3. Vì sao `42.0d` có thể khớp pattern `int n` nhưng `42.5d` không khớp?
4. Tại sao `(int) value` khác với `case int n`?
5. Vì sao `case 0` không dùng cho selector `double`?
6. Khi nào pattern không guard gây dominance error?
7. Vì sao switch với selector `Integer` cần xem xét `null`?
8. Primitive patterns trong Java 25 đã là tính năng permanent chưa?

## 15. Tài liệu chính thức

- [JEP 507 — Primitive Types in Patterns, instanceof, and switch (Third Preview)](https://openjdk.org/jeps/507): phạm vi và thay đổi của tính năng trong JDK 25.
- [Java SE 25 — Primitive Types in Patterns, instanceof, and switch JLS](https://docs.oracle.com/en/java/javase/25/docs/specs/primitive-types-in-patterns-instanceof-switch-jls.html): testing conversion, exactness, guard, dominance và exhaustiveness.
- [Oracle Java 25 — Type Patterns](https://docs.oracle.com/en/java/javase/25/language/type-patterns.html): ví dụ primitive type patterns và cách dùng trong switch.
- [Oracle Java 25 — Pattern Matching with switch](https://docs.oracle.com/en/java/javase/25/language/pattern-matching-switch.html): cú pháp guard `when`, pattern dominance và scope của pattern variable.
- [Oracle Java 25 — Java Language Changes Summary](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-summary.html): trạng thái JEP 507 là preview lần thứ ba.
- [JEP 530 — Primitive Types in Patterns, instanceof, and switch (Fourth Preview)](https://openjdk.org/jeps/530): thay đổi ở Java 26.
- [JEP 532 — Primitive Types in Patterns, instanceof, and switch (Fifth Preview)](https://openjdk.org/jeps/532): trạng thái tiếp tục preview trong Java 27.
- [Oracle Java 27 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html): xác nhận primitive patterns vẫn là preview lần thứ năm.

> **Ghi nhớ:** Primitive type pattern kiểm tra phép chuyển đổi có chính xác hay không; guard `when` tiếp tục giới hạn giá trị theo quy tắc nghiệp vụ. Trong Java 25, JEP 507 vẫn là preview nên phải bật preview khi biên dịch và chạy. Tính năng tiếp tục được preview trong JDK 26 và JDK 27; hãy kiểm tra JEP của đúng release trước khi dùng trong dự án.
