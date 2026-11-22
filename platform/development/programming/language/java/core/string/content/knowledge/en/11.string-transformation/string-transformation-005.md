# String.transform() và xây dựng chuỗi bước xử lý trong Java

Khi xử lý dữ liệu văn bản, một chương trình thường phải thực hiện nhiều thao tác liên tiếp: **cắt khoảng trắng ở hai đầu → chuẩn hóa khoảng trắng → đổi chữ hoa/thường → tách, kiểm tra hoặc chuyển kiểu**. Nếu viết tất cả trong một biểu thức lồng nhiều lời gọi, mã dễ khó đọc; nếu tạo hàng loạt biến trung gian, ý đồ luồng xử lý có thể bị phân tán.

Từ **Java 12**, `java.lang.String` cung cấp phương thức `transform(Function)`. Nó cho phép truyền **toàn bộ chuỗi hiện tại** cho một hàm biến đổi rồi nhận kết quả của hàm đó. Ghép nhiều lời gọi `transform(...)` tạo thành một *pipeline* xử lý mạch lạc, được thực thi **theo thứ tự từ trái sang phải**.

Điểm quan trọng: `transform` **không tự sửa nội dung, không tự chuẩn hóa chuỗi và không tự kích hoạt xử lý bất đồng bộ**. Nó chỉ gọi hàm do người lập trình cung cấp. Hàm có thể trả một `String` khác, cũng có thể trả **kiểu dữ liệu hoàn toàn khác** như `Integer`, `String[]` hoặc một đối tượng miền nghiệp vụ.

## 1. API của String.transform()

Chữ ký khái niệm từ `java.lang.String`:

```java
public <R> R transform(
        java.util.function.Function<? super String, ? extends R> f)
```

Trong đó:

- **`f`** là hàm nhận một `String` (hoặc kiểu cha phù hợp như `Object`) và trả một kết quả kiểu `R`.
- **`R`** là kiểu kết quả do trình biên dịch suy luận hoặc do ngữ cảnh gán xác định; nó **không bị giới hạn** ở `String`.
- **`? super String`** cho phép một hàm có kiểu đầu vào phù hợp với `String`; **`? extends R`** cho phép kết quả là kiểu `R` hoặc subtype của `R`.
- Phương thức là **phương thức instance**: gọi trên một đối tượng `String`, không phải phương thức static.
- Có từ **Java 12**; chạy bằng **Java 17+** không cần thêm thư viện.

Về ngữ nghĩa, một lời gọi thông thường tương đương với việc áp dụng hàm trực tiếp:

```java
String input = "  Hello  ";
String result1 = input.transform(String::strip);
String result2 = String::strip.apply(input); // Không hợp lệ: method reference không có apply trực tiếp
```

Dòng thứ hai chỉ nhằm minh họa **một lỗi cú pháp thường gặp**; nó không biên dịch được. Muốn viết tương đương chính xác, hãy tạo đối tượng `Function`:

```java
java.util.function.Function<String, String> cleanup = String::strip;
String result1 = input.transform(cleanup);
String result2 = cleanup.apply(input);
System.out.println(result1.equals(result2)); // true
```

Ba dòng trong khối hợp lệ khi `input` được khai báo như bên trên. Mỗi lần gọi `transform` sẽ thực thi tương tự `f.apply(input)` ngay lúc được gọi; không có cơ chế trì hoãn như một số thao tác trung gian của `Stream`.

> **Giữ sự đơn giản:** Nếu chỉ muốn gọi `strip()` thì viết `input.strip()` thường dễ hiểu hơn `input.transform(String::strip)`. `transform` đặc biệt hữu ích khi cần đưa chuỗi qua một hàm tùy biến, chuyển sang kiểu khác hoặc ghép nhiều bước mà cách gọi trực tiếp không có dạng chuỗi phương thức thuận tiện.

## 2. Pipeline transform hoạt động thế nào?

Một pipeline thường đọc theo luồng:

```text
String đầu vào
   |
   v
Bước 1: strip()             -> String
   |
   v
Bước 2: normalizeSpaces()   -> String
   |
   v
Bước 3: toUpperCase(ROOT)   -> String
   |
   v
Kết quả: "JAVA CORE"
```

Java cho phép nối lời gọi vì **kết quả của một bước còn là `String`**, nên có thể gọi tiếp `.transform(...)`:

```java
String result = raw
        .transform(String::strip)
        .transform(StringTransformDemo::normalizeSpaces)
        .transform(s -> s.toUpperCase(Locale.ROOT));
```

Đây là đoạn **minh họa bên trong lớp `StringTransformDemo`** ở mục 5, nơi `raw` và `normalizeSpaces` được định nghĩa. Nó thể hiện:

1. `raw` là chuỗi ban đầu.
2. `String::strip` bỏ khoảng trắng theo `Character.isWhitespace` ở hai mép.
3. `normalizeSpaces` (do ta định nghĩa) gộp các nhóm dấu cách ASCII và tab liên tiếp thành một dấu cách.
4. Lambda `s -> s.toUpperCase(Locale.ROOT)` chuyển chữ hoa theo locale xác định.

Các bước chạy **eager**, từng bước hoàn tất rồi mới tới bước tiếp. Nếu bước 2 ném exception, bước 3 không chạy. Nếu một bước trả `null`, lời gọi `.transform(...)` tiếp theo trên giá trị đó gây `NullPointerException`. Chương trình không tự bỏ qua lỗi hay hoàn tác các side effect trong hàm.

### Vì sao thứ tự bước quan trọng?

`strip` trước rồi gộp khoảng trắng giúp đầu ra sạch hai mép. Với ví dụ chỉ sử dụng dấu cách và tab, một số thứ tự có thể cho cùng giá trị; **không nên vì thế kết luận mọi phép biến đổi đều giao hoán**.

Chẳng hạn, “kiểm tra độ dài rồi cắt” không giống “cắt rồi kiểm tra độ dài”; “parse số rồi định dạng” cũng khác “định dạng rồi parse”. Nếu bước chuyển kiểu kết quả không còn là `String`, bạn chỉ có thể tiếp tục gọi các phương thức được hỗ trợ bởi **kiểu kết quả mới**.

## 3. transform không giới hạn kết quả ở String

### Chuỗi sang số nguyên

```java
int count = " 42 "
        .transform(String::strip)
        .transform(Integer::parseInt);

System.out.println(count); // 42
```

`String::strip` trả về `String`, nên bước tiếp theo được phép gọi `String.transform`. `Integer::parseInt` trả về `int`, được Java tự động boxing thành `Integer` khi thích hợp để đáp ứng `Function`; biến `count` nhận giá trị `int` nhờ unboxing. Nếu chuỗi sau khi cắt không phải số nguyên thập phân hợp lệ, `Integer.parseInt` ném `NumberFormatException`: `transform` không tự bắt lỗi này.

### Chuỗi sang mảng

```java
String[] items = " red,green,blue "
        .transform(String::strip)
        .transform(s -> s.split(","));
```

Sau bước thứ hai, kiểu trả về là `String[]`. Bạn có thể gọi phương thức của mảng hoặc các API làm việc với mảng, nhưng **không thể** gọi `.transform(...)` tiếp trên mảng, vì mảng không có phương thức instance `String.transform`.

### Chuỗi sang số lượng ký tự

```java
Integer length = "  hello  "
        .transform(String::strip)
        .transform(String::length);

System.out.println(length); // 5
```

`String::length` trả số **đơn vị mã UTF-16** sau khi strip. Nếu yêu cầu số **code point**, hãy dùng:

```java
int codePoints = "A\u0301"
        .transform(s -> s.codePointCount(0, s.length()));
```

Đoạn này trả 2 code point (chữ A và dấu kết hợp), không nhất thiết là 2 ký tự người dùng cảm nhận. Phương thức `transform` không làm thay đổi các quy tắc Unicode của `length` hoặc `codePointCount`.

## 4. Method reference, lambda và các hàm tùy biến

Tham số của `transform` là một đối tượng thực thi giao diện hàm `Function`, vì vậy có thể cung cấp nhiều cách viết:

| Cách truyền hàm | Ví dụ | Khi hữu ích |
|---|---|---|
| Method reference của instance method | `.transform(String::strip)` | Phương thức có sẵn nhận chính chuỗi hiện tại |
| Lambda một biểu thức | `.transform(s -> s.replace("-", "_"))` | Có tham số bổ sung hoặc logic ngắn |
| Method reference của static method | `.transform(Integer::parseInt)` | Chuyển String sang kiểu khác |
| Method reference đến hàm tự định nghĩa | `.transform(MyCleaner::clean)` | Tái sử dụng một bước nghiệp vụ |
| Biến `Function` | `.transform(cleanupPipeline)` | Cấu hình, kiểm thử, kết hợp và tái sử dụng nhiều bước |

Không phải cứ có dấu `::` là có thể thay lambda trong mọi hoàn cảnh. Method reference phải tương thích với kiểu hàm mong đợi; ví dụ `String::strip` tương thích với `Function<String, String>`, còn các phương thức cần nhiều tham số có thể không phù hợp nếu chưa được đóng gói bằng lambda.

Ví dụ một phương thức tùy biến:

```java
static String normalizeSpaces(String input) {
    return input.replaceAll("[\\t ]+", " ");
}
```

Đây là **phương thức đặt bên trong một lớp**. Regex `[\\t ]+` tìm một hoặc nhiều dấu tab hoặc dấu cách ASCII và thay bằng đúng một dấu cách. Nó **không được định nghĩa để xử lý mọi loại Unicode whitespace**. Đây là lựa chọn cố ý để ví dụ có quy tắc đơn giản và kiểm thử rõ ràng.

Lưu ý **hai lớp escape**: mã Java `"[\\t ]+"` tạo regex `[\t ]+`; ký tự `\` trong Java literal phải được escape thành `\\` để gửi dấu backslash tới regex engine. Với dữ liệu Unicode phức tạp, chọn regex/`Pattern` và chính sách chuẩn hóa phù hợp với yêu cầu thực tế.

## 5. Chương trình Java 17+ hoàn chỉnh

Lưu vào tệp **`StringTransformDemo.java`**:

```java
import java.util.Arrays;
import java.util.Locale;
import java.util.function.Function;

public class StringTransformDemo {
    // Chuẩn hóa các nhóm dấu cách ASCII và TAB liên tiếp.
    static String normalizeSpaces(String input) {
        return input.replaceAll("[\\t ]+", " ");
    }

    // Chỉ dùng để in rõ TAB và dấu cách; không đổi dữ liệu nguồn.
    static String visible(String input) {
        return input.replace("\t", "<TAB>").replace(" ", "_");
    }

    public static void main(String[] args) {
        String raw = " \tjava   core\t ";

        String normalized = raw
                .transform(String::strip)
                .transform(StringTransformDemo::normalizeSpaces)
                .transform(s -> s.toUpperCase(Locale.ROOT));

        System.out.println("raw: [" + visible(raw) + "]");
        System.out.println("normalized: [" + normalized + "]");
        System.out.println("raw unchanged: "
                + raw.equals(" \tjava   core\t "));

        String[] tokens = "  red,green,blue "
                .transform(String::strip)
                .transform(s -> s.split(","));
        System.out.println("tokens: " + Arrays.toString(tokens));

        Integer length = "  hello  "
                .transform(String::strip)
                .transform(String::length);
        System.out.println("length: " + length);

        int parsed = " 42 "
                .transform(String::strip)
                .transform(Integer::parseInt);
        System.out.println("number: " + parsed);

        String maybeNull = "input".transform(s -> null);
        System.out.println("may return null: " + (maybeNull == null));

        Function<String, String> cleanup = String::strip;
        cleanup = cleanup
                .andThen(StringTransformDemo::normalizeSpaces)
                .andThen(s -> s.toLowerCase(Locale.ROOT));

        System.out.println("function pipeline: "
                + "   A   B  ".transform(cleanup));
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 StringTransformDemo.java
java StringTransformDemo
```

Đầu ra:

```text
raw: [_<TAB>java___core<TAB>_]
normalized: [JAVA CORE]
raw unchanged: true
tokens: [red, green, blue]
length: 5
number: 42
may return null: true
function pipeline: a b
```

Đầu ra được viết bằng ASCII nên không phụ thuộc cách terminal hiển thị dấu tab. Trong hàm `visible`, `<TAB>` biểu thị **một tab thật** và ký tự `_` biểu thị **một dấu cách** trong chuỗi đầu vào. Hàm chỉ giúp nhìn thấy nội dung; `raw` vẫn giữ nguyên.

**Giải thích các dòng đáng chú ý:**

- Chuỗi gốc chứa một dấu cách, một tab, `java`, ba dấu cách, `core`, một tab và dấu cách cuối. `strip` bỏ whitespace ở mép; bước tiếp theo gộp các dấu cách giữa `java` và `core`; cuối cùng đổi thành `JAVA CORE`.
- Hai biến `raw` và `normalized` độc lập về giá trị xử lý. `String` bất biến; một lời gọi `transform` không sửa `raw`.
- `split(",")` tạo mảng ba chuỗi, nên `transform` có thể kết thúc với kiểu `String[]`.
- `String::length` tạo kết quả kiểu số (qua `Integer` trong giao diện `Function`).
- `Integer::parseInt` thể hiện một phép chuyển kiểu có thể thất bại đối với input không hợp lệ.
- Hàm `s -> null` minh họa `transform` **không áp đặt rằng kết quả phải khác null**.
- `Function.andThen` tạo một **hàm tổng hợp** rồi được áp dụng bằng một lần `"   A   B  ".transform(cleanup)`.

## 6. Kết hợp nhiều bước bằng Function.andThen() và compose()

Nếu cần tái sử dụng pipeline ở nhiều nơi, có thể lưu nó dưới dạng một `Function<String, String>`:

```java
Function<String, String> trimSides = String::strip;
Function<String, String> collapse = StringTransformDemo::normalizeSpaces;
Function<String, String> uppercase =
        s -> s.toUpperCase(Locale.ROOT);

Function<String, String> pipeline =
        trimSides.andThen(collapse).andThen(uppercase);

String value = " \tjava   core  ".transform(pipeline);
```

Các dòng trên là **đoạn minh họa bổ sung** (đặt trong lớp có thể truy cập `StringTransformDemo.normalizeSpaces` và import `java.util.function.Function`, `java.util.Locale`). Khi dùng `andThen`, hàm trước chạy rồi đến hàm sau, tương đương:

```text
pipeline.apply(text)
= uppercase.apply(collapse.apply(trimSides.apply(text)))
```

`Function.compose(before)` có thứ tự đọc **ngược** với `andThen(after)`:

```java
Function<String, String> pipeline2 =
        uppercase.compose(collapse).compose(trimSides);
```

Biểu thức `pipeline2.apply(text)` vẫn chạy **trimSides → collapse → uppercase**. Khi người đọc cần thấy rõ luồng xử lý, `andThen` thường thuận tiện hơn vì các bước được liệt kê từ trái sang phải theo thứ tự thực thi.

Phân biệt:

- `source.transform(pipeline)` **áp dụng** pipeline cho **một chuỗi cụ thể** và trả kết quả.
- `f.andThen(g)` **tạo một đối tượng Function kết hợp** có thể tái sử dụng.
- `source.transform(f).transform(g)` **áp dụng ngay** từng function lên kết quả của bước trước.

Chúng gần nhau về ý nghĩa với các hàm thuần, nhưng có khác biệt thiết kế quan trọng: nếu function có **side effect**, ném exception, dùng trạng thái mutable hoặc trả `null`, hành vi của pipeline phụ thuộc chính những function đó. Không nên coi `transform` như cơ chế đảm bảo transaction hoặc xử lý lỗi tự động.

## 7. Pipeline đổi kiểu: khi nào nên dừng chuỗi transform?

Một ví dụ hữu ích là tiền xử lý chuỗi xong rồi **chuyển kết quả sang một kiểu miền nghiệp vụ**:

```java
record ProductCode(String value) {}

ProductCode code = "  prd-042  "
        .transform(String::strip)
        .transform(s -> s.toUpperCase(Locale.ROOT))
        .transform(ProductCode::new);
```

Đây là đoạn mã **cần đặt trong môi trường có khai báo `record ProductCode`** (Java 17 hỗ trợ record). Kết quả là `ProductCode` có `value()` bằng `"PRD-042"`; sau bước cuối, kiểu static là `ProductCode` nên không thể gọi tiếp `String.transform` trên nó.

Một cách khác là dùng `Optional` để thể hiện rằng kết quả có thể vắng mặt:

```java
import java.util.Optional;

Optional<Integer> maybeNumber = " 12 "
        .transform(String::strip)
        .transform(s -> {
            try {
                return Optional.of(Integer.parseInt(s));
            } catch (NumberFormatException ex) {
                return Optional.<Integer>empty();
            }
        });
```

Đây là **đoạn mã minh họa**: `Optional` được trả về **do lambda tự tạo**, không phải vì `transform` hiểu hoặc tự bắt lỗi phân tích số. Với đầu vào `" 12 "`, kết quả là `Optional.of(12)`. Nếu muốn trả thông tin lỗi chi tiết thay vì chỉ trả rỗng, hãy thiết kế kiểu kết quả hoặc exception phù hợp.

**Giữ bước xử lý có trách nhiệm rõ ràng:** Một pipeline dễ đọc thường gồm những hàm tên đủ rõ, nhận một giá trị và tạo một kết quả xác định. Không nên gộp xác thực, lưu database, gửi HTTP, format giao diện và logging vào một chuỗi dài chỉ vì tất cả có thể được đóng gói bằng `Function`.

## 8. Null, exception và dữ liệu không hợp lệ

`String.transform` có các điểm cần chú ý:

| Tình huống | Điều xảy ra | Hướng xử lý |
|---|---|---|
| Tham chiếu receiver `source` là `null` | Gọi `source.transform(...)` gây `NullPointerException` | Xác thực `source` trước khi gọi |
| Tham số `f` là `null` | Không thể áp dụng hàm; ném `NullPointerException` | Truyền function hợp lệ |
| Hàm trả `null` | `transform` có thể trả `null` | Quy định null-contract trước khi nối thêm bước |
| Hàm ném `NumberFormatException`, `IllegalArgumentException`, v.v. | Exception lan ra cho caller theo quy tắc Java | Bắt ở ranh giới nghiệp vụ hoặc để caller xử lý |
| Một bước biến đổi làm mất thông tin | Không có hoàn tác tự động | Kiểm chứng yêu cầu về bảo toàn dữ liệu |
| Một hàm có side effect | Side effect xảy ra khi hàm được gọi | Ưu tiên hàm thuần, kiểm thử rõ ràng |
| Kết quả đổi kiểu khỏi `String` | Không còn gọi được `String.transform` trên kết quả | Tiếp tục bằng API của kiểu mới hoặc dùng function cho toàn pipeline |

Ví dụ null receiver:

```java
String raw = null;
// raw.transform(String::strip); // Nếu chạy, gây NullPointerException.
String safe = raw == null ? "" : raw.strip();
```

Dòng bị chú thích chỉ để minh họa lỗi; ba dòng tạo `raw` và `safe` có thể biên dịch. Việc thay `null` thành chuỗi rỗng là **quyết định nghiệp vụ**, không nên luôn áp dụng mặc định: đôi khi cần báo lỗi đầu vào còn thiếu.

Cũng cần lưu ý một function có thể trả `null` dù đầu vào hoàn toàn hợp lệ:

```java
String result = "hello".transform(s -> null);
System.out.println(result == null); // true
```

Sau đó gọi `result.transform(...)` sẽ ném `NullPointerException`. Nếu yêu cầu không được phép null, có thể chốt điều kiện hậu kiểm (ví dụ `Objects.requireNonNull`) hoặc chọn kiểu kết quả thể hiện rõ khả năng thiếu giá trị.

## 9. transform khác gì Stream.map(), replace() và các API String khác?

| API | Điểm khác biệt |
|---|---|
| `String.transform(f)` | Áp dụng **một Function cho toàn bộ String** và trả một giá trị kiểu `R` bất kỳ |
| `String.replace(...)` | Thay thế ký tự hoặc chuỗi con theo quy tắc của API; kết quả luôn là `String` |
| `String.replaceAll(regex, replacement)` | Thay theo regular expression; chú ý regex/escape và hiệu năng |
| `String.strip()` | Loại bỏ whitespace theo quy tắc Java ở hai mép; là một phép biến đổi cụ thể |
| `Stream.map(f)` | Áp dụng function **cho từng phần tử của Stream**, mang tính lazy ở giai đoạn trung gian |
| `Function.andThen(...)` | Kết hợp các function để **sử dụng về sau**; bản thân việc kết hợp chưa áp dụng chúng vào một String |
| `String.formatted(...)` | Định dạng chuỗi mẫu theo đối số được truyền; mục đích khác với function pipeline |

Ví dụ `"java".transform(String::toUpperCase)` là một bước biến đổi cho **toàn bộ chuỗi**. Trong khi đó, `Stream.of("java", "core").map(String::toUpperCase)` là phép biến đổi **từng chuỗi trong Stream** khi pipeline của Stream được thực thi bởi terminal operation.

Một ứng dụng cần đọc **nhiều dòng** có thể phối hợp cả hai cơ chế:

```java
List<String> lines = " a \n\n b "
        .transform(String::lines)
        .map(String::strip)
        .filter(s -> !s.isEmpty())
        .toList();
```

Đây là đoạn minh họa, cần import `java.util.List`. `String::lines` trả `Stream<String>`, nên **sau lời gọi `transform`, chúng ta đang gọi `Stream.map/filter/toList`**, không còn gọi `String.transform`. Với Java 17+, kết quả của ví dụ là danh sách `["a", "b"]`. Lệnh `toList()` là terminal operation của Stream.

## 10. Thiết kế một pipeline dễ bảo trì

Khi xây dựng chuỗi xử lý văn bản, nên phân định các bước rõ ràng:

1. **Chuẩn hóa cú pháp đầu vào:** cắt whitespace không mong muốn, gộp dấu phân tách, chuyển encoding khi thật sự cần.
2. **Chuẩn hóa nội dung theo quy tắc nghiệp vụ:** chuyển chữ hoa/thường với `Locale` rõ ràng, chuẩn hóa định danh, xử lý ký tự đặc biệt.
3. **Kiểm tra:** xác thực rỗng, độ dài, pattern, phạm vi ký tự được phép; báo lỗi với ngữ cảnh cụ thể.
4. **Chuyển kiểu cuối cùng:** từ `String` thành `Integer`, `record`, `List`, cấu trúc phân tích cú pháp hoặc một kiểu kết quả miền nghiệp vụ.

Đây là gợi ý **thiết kế**, không phải yêu cầu bắt buộc có bốn giai đoạn trong mọi chương trình. Một bước xử lý không hữu ích thì không cần thêm vào để tạo pipeline dài.

Các nguyên tắc áp dụng:

- **Hàm nhỏ, đặt tên rõ:** `normalizeSpaces`, `parseProductCode` và `validateInput` dễ hiểu hơn lambda nhiều lệnh, lồng điều kiện dày đặc.
- **Đơn vị kiểm thử ổn định:** có thể kiểm tra từng `Function` độc lập và sau đó kiểm tra pipeline tổng thể.
- **Không biến đổi âm thầm dữ liệu quan trọng:** Unicode normalization, thay đổi dấu tiếng Việt, xử lý không phân biệt hoa/thường và loại bỏ ký tự vô hình đều có thể thay đổi ý nghĩa dữ liệu. Chỉ áp dụng khi quy tắc nghiệp vụ yêu cầu.
- **Locale rõ ràng:** `toUpperCase(Locale.ROOT)`/`toLowerCase(Locale.ROOT)` cho kết quả không phụ thuộc default locale; nhưng ngôn ngữ cụ thể có thể cần locale cụ thể (như xử lý chữ cái tiếng Thổ Nhĩ Kỳ).
- **Giữ quy tắc regex được mô tả:** biểu thức `[\\t ]+` của bài chỉ gộp tab/space ASCII; để xử lý nhóm Unicode whitespace, cần xác định chính xác tập ký tự nào được phép và kiểm thử.
- **Không lạm dụng transformation có side effect:** `transform` chạy ngay và không đảm bảo rollback; các thao tác ngoại vi hoặc cập nhật shared state cần kiểm soát riêng.
- **Tối ưu sau khi có đo đạc:** nhiều bước biến đổi có thể tạo các đối tượng `String` trung gian; trong đường xử lý hiệu năng cao, xem xét việc gộp bước hoặc dùng `StringBuilder`/`Pattern` được tái sử dụng. Đừng đổi thiết kế chỉ vì giả định mọi lần gọi `transform` chắc chắn tạo một object mới.

### Có cần luôn dùng transform thay biến trung gian?

Không. Cả hai cách đều hợp lệ:

```java
String stripped = raw.strip();
String compact = normalizeSpaces(stripped);
String upper = compact.toUpperCase(Locale.ROOT);
```

Cách này thuận tiện nếu cần debug từng kết quả hoặc dùng lại kết quả trung gian. Dạng pipeline:

```java
String upper = raw
        .transform(String::strip)
        .transform(MyTextUtils::normalizeSpaces)
        .transform(s -> s.toUpperCase(Locale.ROOT));
```

là đoạn minh họa cần lớp `MyTextUtils` có static method tương ứng, và phù hợp khi muốn nhìn ngay **trình tự xử lý** trong một biểu thức. Chọn cách nào giúp nhóm đọc, kiểm thử và bảo trì rõ nhất.

## 11. Những lỗi thường gặp

| Lỗi/hiểu nhầm | Vì sao sai | Cách sửa |
|---|---|---|
| Nghĩ `transform` chỉ trả về `String` | Chữ ký dùng generic `<R>` | Có thể trả `Integer`, `String[]`, `List`, `Optional` hoặc kiểu riêng |
| Nghĩ `transform` mặc nhiên là lazy | `Function.apply` chạy ngay | Đừng suy luận theo `Stream.map` |
| Gọi `.transform(...)` tiếp khi bước trước đã trả `Integer` | `Integer` không có `String.transform` | Sử dụng API của `Integer` hoặc viết lại hàm |
| Bỏ kết quả của `source.transform(...)` mà chờ `source` đổi | `String` bất biến | Gán kết quả vào biến hoặc trả từ phương thức |
| Đầu vào `null` | Không có receiver hợp lệ | Xử lý null ở ranh giới |
| Hàm có thể trả `null` nhưng pipeline tiếp tục | Dẫn đến `NullPointerException` | Xác định hợp đồng null hoặc dùng `Optional` |
| Mong `transform` tự bắt lỗi `parseInt` | Exception do function phát ra vẫn lan ra | Thiết kế cơ chế báo lỗi phù hợp |
| Lạm dụng regex `\\s+` để “xóa mọi Unicode whitespace” | Tập ký tự mà regex nhận phụ thuộc cờ và quy tắc cụ thể | Chọn regex với định nghĩa ký tự đúng theo yêu cầu |
| Dùng `==` để kiểm tra chuỗi sau chuyển đổi | `==` so identity, không so nội dung | Dùng `equals` |
| Viết function vừa sửa dữ liệu vừa gửi HTTP/log nhiều nơi | Tạo side effect khó kiểm soát và khó test | Tách side effect khỏi bước chuẩn hóa khi có thể |

## 12. Tự kiểm tra

Cho:

```java
String original = "  blue,green  ";

String[] colors = original
        .transform(String::strip)
        .transform(s -> s.split(","));

int number = "  007  "
        .transform(String::strip)
        .transform(Integer::parseInt);

String upper = original
        .transform(String::strip)
        .transform(s -> s.toUpperCase(Locale.ROOT));
```

Hãy trả lời:

1. `colors.length` bằng bao nhiêu và các phần tử chứa gì?
2. `number` bằng bao nhiêu? Có còn giữ dạng chuỗi `"007"` sau bước `parseInt` không?
3. `upper` chứa nội dung nào và `original` có bị thay đổi không?
4. Nếu nối thêm `.transform(String::strip)` sau `Integer::parseInt` thì có biên dịch không?
5. Nếu đổi input của số thành `"  seven  "` thì `transform` có trả về 0, `null` hay ném lỗi?

**Đáp án:**

1. `colors.length == 2` với các phần tử `"blue"` và `"green"`.
2. `number == 7`; kiểu kết quả là số nguyên, không còn định dạng chuỗi có các số 0 đứng trước.
3. `upper` là `"BLUE,GREEN"`; `original` vẫn là `"  blue,green  "`.
4. Không, vì sau `parseInt` không còn receiver kiểu `String`.
5. `Integer.parseInt("seven")` ném `NumberFormatException`; `transform` để exception đi ra ngoài trừ khi lambda tự xử lý nó.

## 13. Tài liệu chính thức

- [Java SE 17 — `String.transform(Function)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#transform(java.util.function.Function)): chữ ký, kiểu kết quả và hợp đồng áp dụng function.
- [Java SE 17 — `Function`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html): `apply`, `andThen`, `compose` và `identity`.
- [Java SE 17 — `String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): các API `strip`, `replaceAll`, `split`, `lines` và `length`.

**Ghi nhớ:** `String.transform(f)` truyền **chuỗi hiện tại** cho `f` và trả **chính kết quả của hàm**, có thể là kiểu bất kỳ. Muốn viết pipeline rõ ràng, nối các bước trả lại `String` hoặc dùng `Function.andThen`; khi đã chuyển sang kiểu khác, tiếp tục bằng API của kiểu mới. `transform` không sửa chuỗi gốc, không tự bỏ null/exception và không thay người lập trình quyết định quy tắc chuẩn hóa dữ liệu.
