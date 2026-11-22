# Kiểm thử pattern với generic record trong Java 21+

## 1. Mục tiêu kiểm thử

Khi dùng **generic record** cùng **record pattern**, ta kiểm thử nhiều hơn chuyện “record có đúng kiểu không”. Cần xác minh:

1. **Kiểu tĩnh được suy luận đúng** cho các biến `var` bên trong record pattern.
2. **Pattern lồng nhau** có khớp đúng từng tầng hay không.
3. **`null` ở record gốc, record con và component** có hành vi khác nhau thế nào.
4. **Generic type erasure** giới hạn khả năng kiểm tra kiểu lúc chạy ra sao.
5. **Case có guard và nhánh dự phòng** hoạt động đúng thứ tự và không bị che khuất.
6. **Mã cố tình sai phải bị trình biên dịch từ chối**, không chỉ kiểm thử các trường hợp chạy thành công.

Từ **Java 21**, record patterns chính thức được chuẩn hóa (JEP 440), có thể dùng với `instanceof` và `switch`. Pattern matching for `switch` cũng chính thức từ Java 21 (JEP 441). Các ví dụ trong bài chạy trên **JDK 21 trở lên** và không cần `--enable-preview`. `record` xuất hiện chính thức từ Java 16, nhưng **`record` hỗ trợ generic** không có nghĩa mọi phiên bản có record đều hỗ trợ **record pattern**.

Đề bài này thuộc nhóm **Kiểm thử**: các giải thích về generics và pattern đều gắn với ca test, đầu ra, failure modes và chiến lược xác nhận.

## 2. Model mẫu: generic record và kiểu dùng làm dữ liệu test

Ba generic records:

```java
record Box<T>(T value) {}
record Pair<L, R>(L left, R right) {}
record Envelope<T>(String id, Box<T> payload) {}
```

Với chúng, ta có thể tạo:

```java
Pair<String, Integer> scores = new Pair<>("ada", 9);
Envelope<String> message = new Envelope<>("E1", new Box<>("java"));
Box<?> unknown = new Box<>(42);
```

**Kiểu tĩnh** mang thông tin quan trọng:

- `Pair<String, Integer>` cho biết `left` có kiểu `String`, `right` có kiểu `Integer` khi code biên dịch.
- `Envelope<String>` cho biết `payload` có kiểu `Box<String>`, nếu các đối tượng tuân thủ ràng buộc generic được compiler kiểm tra.
- `Box<?>` chỉ bảo đảm đó là một `Box` với kiểu tham số chưa biết. `value()` có thể trả về `String`, `Integer`, `null` hoặc một giá trị tham chiếu khác; không thể coi giá trị đó luôn là `String`.

**Type erasure:** Java không lưu thông tin mọi đối số generic trong kiểu runtime của từng đối tượng theo cách cho phép kiểm tra `Box<String>` khác `Box<Integer>` bằng `instanceof` trên một `Object`. Việc **record pattern có thể suy luận kiểu từ ngữ cảnh biên dịch** không phải bằng chứng runtime rằng mọi object từ dữ liệu không tin cậy đều có đúng kiểu generic.

## 3. Kiểm thử suy luận kiểu của generic record pattern

Giả sử tham số phương thức có kiểu:

```java
Pair<String, Integer> pair
```

Ta có thể viết:

```java
return switch (pair) {
    case null -> "null-pair";
    case Pair(var name, var score) when name != null && score != null ->
            name.toUpperCase() + ":" + (score + 1);
    case Pair(var name, var score) -> "partial";
};
```

Đây là **đoạn minh họa nằm trong một phương thức trả về `String`**. Chương trình đầy đủ ở mục 7.

Điểm đáng kiểm thử:

- Pattern `Pair(var name, var score)` không ghi rõ `Pair<String, Integer>`; compiler dùng **ngữ cảnh kiểu tĩnh của selector** để suy luận tham số generic cho pattern.
- `name` được suy luận là `String` nên gọi `name.toUpperCase()` hợp lệ.
- `score` được suy luận là `Integer` nên có thể cộng `1` nhờ unboxing.
- Pattern không tự xác thực `null` của từng component: `new Pair<>(null, 9)` vẫn có thể khớp record pattern, nhưng **guard `when` không đạt**, và nhánh dự phòng trả `"partial"`.
- `case null` xử lý **selector `pair == null`**; không đồng nghĩa với việc từ chối mọi component null.
- Nhánh có guard phải đứng trước nhánh `Pair(...)` tổng quát, vì nhánh tổng quát đặt trước có thể làm nhánh guard phía sau bị che khuất (*dominated*).

Nếu thử gọi `score.toUpperCase()`, compiler sẽ báo lỗi vì biến đó là `Integer`, không phải `String`. Đây là một **negative compile test** hữu ích để xác nhận suy luận kiểu — xem mục 9.

## 4. Kiểm thử record pattern lồng trong generic record

Xét:

```java
Envelope<String> envelope =
        new Envelope<>("E1", new Box<>("java"));
```

Pattern:

```java
case Envelope(var id, Box(var content)) when content != null ->
        id + ":" + content.toUpperCase();
```

Có ba tầng ý nghĩa:

1. `Envelope(...)` kiểm tra kiểu record gốc và tách `id`, `payload`.
2. `Box(...)` yêu cầu `payload` là một record `Box` khác `null`.
3. `var content` lấy component `value`; nhờ ngữ cảnh `Envelope<String>`, compiler suy luận kiểu tĩnh của `content` là `String`.

**Kiểm thử `null` đúng tầng:**

| Dữ liệu | Tầng khớp | Kết quả mong đợi |
| --- | --- | --- |
| `Envelope("E1", Box("java"))` | Cả `Envelope` và `Box` khớp; guard true | `E1:JAVA` |
| `Envelope("E2", Box(null))` | Hai record khớp, `content == null`; guard false | `null-content` |
| `Envelope("E3", null)` | Record ngoài khớp, `Box(...)` không khớp | `missing-box` |
| `envelope == null` | Không khớp record ngoài; dùng `case null` | `null-envelope` |

Sự khác biệt quan trọng: `Box(var content)` **có thể khớp `new Box<>(null)`**, còn một **record pattern con** `Box(...)` **không khớp** nếu toàn bộ `payload == null`. Một test chỉ chứa dữ liệu hợp lệ sẽ bỏ sót lỗi phân biệt hai trường hợp này.

Trong code hoàn chỉnh, các case được tổ chức theo thứ tự: record lồng có guard → record lồng không guard → record ngoài tổng quát. Case cuối mới bao phủ tình huống `payload` là `null`.

## 5. Kiểm thử ở biên nhận dữ liệu kiểu Object và wildcard

Nếu một API nhận `Object input`, compiler **chưa thể biết** đối số generic cụ thể của đối tượng. Để kiểm tra một `Box` với tham số chưa rõ:

```java
if (!(input instanceof Box<?> box)) {
    return "not-box";
}
Object content = box.value();
```

`Box<?>` là kiểu có thể kiểm tra trong ngữ cảnh này; điều được kiểm tra là **đối tượng thuộc record `Box`**, không phải phần tử bên trong chắc chắn có kiểu `String`.

Sau khi lấy `content` kiểu `Object`, kiểm tra bằng pattern trên chính phần tử:

```java
return switch (content) {
    case null -> "null-value";
    case String s -> "String:" + s;
    case Integer n -> "Integer:" + n;
    default -> "other:" + content.getClass().getSimpleName();
};
```

Đây là **đoạn mã đặt trong phương thức trả về `String`**. Nhánh `case null` cần thiết nếu muốn xử lý content null như dữ liệu hợp lệ thay vì để `switch` báo lỗi. Trong nhánh `default`, `content` chắc chắn không phải null vì `case null` đã xử lý.

Ngoài ra, Java 21 cho phép dùng **record pattern với type argument được suy luận** trên một `Object`:

```java
if (input instanceof Pair(var left, var right)) {
    // Không được tự giả định left là String và right là Integer.
    System.out.println(left);
}
```

Ở trường hợp selector là `Object` không có generic type argument cụ thể, hai biến con không được dùng như thể compiler đã chứng minh chúng là `String` và `Integer`. Hãy kiểm tra kiểu phần tử hoặc truyền model có kiểu tĩnh cụ thể qua API nội bộ. Bài kiểm thử so sánh riêng hai đường: `Pair<String,Integer>` đã typed và `Object` chưa typed.

## 6. Lập ma trận kiểm thử trước khi viết chương trình

Để xác minh **đúng cả kiểu lẫn hành vi**, cần các nhóm sau:

| Nhóm | Ca | Mục đích |
| --- | --- | --- |
| Generic record typed | `Pair<String,Integer>("ada",9)` | Suy luận kiểu, guard đúng, nhánh có giá trị |
| Typed + component null | `Pair<String,Integer>(null,9)` | Record khớp nhưng guard từ chối component |
| Typed + selector null | `pair == null` | Nhánh `case null` |
| Nested generic record | `Envelope<String>("E1", Box("java"))` | Suy luận `content` thành String, deconstruction nhiều tầng |
| Nested value null | `Envelope("E2", Box(null))` | Phân biệt giá trị null với record con null |
| Nested Box null | `Envelope("E3", null)` | Record con không khớp, fallback record ngoài |
| Nested selector null | `envelope == null` | Không chạy nhánh record pattern |
| Wildcard String | `Box<?>` chứa `"ok"` | Kiểm tra kiểu phần tử runtime |
| Wildcard Integer | `Box<?>` chứa `4` | Chứng minh generics không đồng nghĩa String |
| Wildcard null | `Box<?>` chứa `null` | Xử lý content null |
| Không phải Box | `input = "text"` | Nhánh `not-box` |
| Pair đến từ Object | `new Pair<>("x", 4)` | Record pattern trên Object chỉ cho biết cấu trúc, không tự xác thực generic args |

Thay vì chỉ in ra kết quả, chương trình bên dưới dùng **assertion tự triển khai**: nếu actual khác expected, ném `AssertionError`. Do đó một dòng “passed” chỉ xuất hiện khi tất cả ca trước đó đúng.

## 7. Chương trình đầy đủ và cách chạy

Tạo file **`GenericRecordPatternTests.java`** có nội dung:

```java
public class GenericRecordPatternTests {
    record Box<T>(T value) {}
    record Pair<L, R>(L left, R right) {}
    record Envelope<T>(String id, Box<T> payload) {}

    static void check(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    label + ": expected " + expected + " but got " + actual);
        }
        System.out.println(label + " => " + actual);
    }

    static String typed(Pair<String, Integer> pair) {
        return switch (pair) {
            case null -> "null-pair";
            case Pair(var name, var score) when name != null && score != null ->
                    name.toUpperCase() + ":" + (score + 1);
            case Pair(var name, var score) -> "partial";
        };
    }

    static String nested(Envelope<String> envelope) {
        return switch (envelope) {
            case null -> "null-envelope";
            case Envelope(var id, Box(var content)) when content != null ->
                    id + ":" + content.toUpperCase();
            case Envelope(var id, Box(var content)) -> "null-content";
            case Envelope(var id, var payload) -> "missing-box";
        };
    }

    static String wildcard(Object input) {
        if (!(input instanceof Box<?> box)) return "not-box";

        Object content = box.value();
        return switch (content) {
            case null -> "null-value";
            case String s -> "String:" + s;
            case Integer n -> "Integer:" + n;
            default -> "other:" + content.getClass().getSimpleName();
        };
    }

    static String destructureUnknown(Object input) {
        if (input instanceof Pair(var left, var right)) {
            String a = left == null
                    ? "null" : left.getClass().getSimpleName();
            String b = right == null
                    ? "null" : right.getClass().getSimpleName();
            return a + "/" + b;
        }
        return "not-pair";
    }

    public static void main(String[] args) {
        check("typed-ok", "ADA:10", typed(new Pair<>("ada", 9)));
        check("typed-null-component", "partial",
                typed(new Pair<>(null, 9)));
        check("typed-null-root", "null-pair", typed(null));

        check("nested-ok", "E1:JAVA",
                nested(new Envelope<>("E1", new Box<>("java"))));
        check("nested-null-value", "null-content",
                nested(new Envelope<>("E2", new Box<>(null))));
        check("nested-null-box", "missing-box",
                nested(new Envelope<>("E3", null)));
        check("nested-null-root", "null-envelope", nested(null));

        check("wild-string", "String:ok", wildcard(new Box<>("ok")));
        check("wild-int", "Integer:4", wildcard(new Box<>(4)));
        check("wild-null", "null-value", wildcard(new Box<>(null)));
        check("wild-wrong", "not-box", wildcard("text"));

        check("unknown-pair", "String/Integer",
                destructureUnknown(new Pair<>("x", 4)));

        System.out.println("12/12 passed");
    }
}
```

**Chạy bằng JDK 21+:**

```bash
javac --release 21 GenericRecordPatternTests.java
java GenericRecordPatternTests
```

**Stdout chính xác:**

```text
typed-ok => ADA:10
typed-null-component => partial
typed-null-root => null-pair
nested-ok => E1:JAVA
nested-null-value => null-content
nested-null-box => missing-box
nested-null-root => null-envelope
wild-string => String:ok
wild-int => Integer:4
wild-null => null-value
wild-wrong => not-box
unknown-pair => String/Integer
12/12 passed
```

Bản ví dụ đã chạy trong **JShell của JDK 24** và cho đúng toàn bộ 12 kết quả cùng dòng tổng kết. Các tính năng cú pháp được dùng là tính năng chính thức trong Java 21; lệnh `javac --release 21` thể hiện target biên dịch dành cho người học.

**Cách biết test thật sự có giá trị:** thay tạm `"ADA:10"` thành `"ADA:11"` ở expected, hoặc đổi `score + 1` thành `score + 2` trong hàm `typed`: chương trình phải báo `AssertionError`. Không chỉ dựa vào việc chương trình chạy xong không có exception để khẳng định mọi pattern đã cho kết quả đúng.

## 8. Kiểm thử trường hợp lỗi biên dịch (negative compilation)

Một số sai lầm **không thể** kiểm chứng bằng chạy chương trình, bởi compiler phải từ chối chúng trước. Các đoạn bên dưới **cố tình sai**, không đưa vào file chương trình ở mục 7. Nếu chạy bằng JShell hoặc đặt trong file Java có đủ khai báo `Box` và `Pair`, chúng phải bị từ chối.

### 8.1. Không kiểm tra được `Box<String>` từ Object

```java
// CỐ TÌNH SAI: tham số generic String không thể kiểm tra runtime theo cách này.
static boolean bad(Object input) {
    return input instanceof Box<String> box;
}
```

Với selector là `Object`, kiểu `Box<String>` không phải một kiểu reifiable cho phép kiểm tra như trên. Compiler báo không thể cast một cách an toàn từ `Object` sang `Box<String>`. **Cách sửa:** dùng `Box<?>` để kiểm tra record gốc, rồi kiểm tra `box.value()` bằng một type pattern riêng nếu cần `String`.

Đừng khái quát sai rằng “mọi generic type đều không dùng được với `instanceof`”. Ví dụ `Box<?>` phù hợp; và khi compiler có ngữ cảnh kiểu hẹp hơn, những kiểm tra được ngôn ngữ cho phép có thể khác. Ở đây tình huống được kiểm tra cụ thể là **`Object` sang `Box<String>`**.

### 8.2. Sai số component của record pattern

```java
// CỐ TÌNH SAI: Box chỉ khai báo một component.
static boolean badArity(Object input) {
    return input instanceof Box(var first, var second);
}
```

`Box<T>` có **một** record component `value` nên pattern phải có đúng **một** pattern con. Compiler báo sai số nested patterns. Record pattern tuân theo **số lượng, thứ tự và kiểu component theo khai báo**, không dựa vào tên biến mà người viết tự chọn.

### 8.3. Suy luận thành Integer không cho gọi phương thức String

```java
// CỐ TÌNH SAI: score là Integer, không có toUpperCase().
static String badInference(Pair<String, Integer> pair) {
    return switch (pair) {
        case null -> "none";
        case Pair(var name, var score) -> score.toUpperCase();
    };
}
```

Compiler bác lời gọi `score.toUpperCase()`. Đó là dấu hiệu `var score` **không phải Object tùy ý** và cũng không phải `String`, mà nhận kiểu được suy luận từ `Pair<String,Integer>`.

Ba ca negative compile trên đã được thử trong **JShell JDK 24** và đều bị từ chối như dự kiến: lần lượt lỗi generic không kiểm tra an toàn, sai số nested patterns, và không tìm thấy phương thức `toUpperCase()` trên kiểu Integer.

## 9. Cảnh giác với type erasure, raw types và dữ liệu không tin cậy

Vì Java generic chủ yếu dựa vào kiểm tra compile time, code dùng **raw type**, unchecked cast, reflection hoặc hệ thống nguồn ngoài có thể phá vỡ giả định về component.

Ví dụ minh họa nguy cơ (đặt trong một phương thức, không phải code nên dùng trong production):

```java
@SuppressWarnings({"rawtypes", "unchecked"})
static Pair<String, Integer> forgePair() {
    Pair raw = new Pair("ada", "not-an-integer");
    return (Pair<String, Integer>) raw;
}
```

Hàm trên sử dụng raw type và unchecked cast nên có thể tạo ra tham chiếu có **kiểu khai báo `Pair<String,Integer>` nhưng component thực tế không đúng `Integer`**. Khi code sau đó lấy hoặc sử dụng `score` như `Integer`, có thể phát sinh lỗi cast/runtime. Đừng xem việc match record pattern là validator đầy đủ của generic type arguments.

Một chiến lược phòng vệ ở ranh giới dữ liệu:

- Nhận `Object`/`Box<?>` và kiểm tra runtime type cho từng component nếu không tin cậy nguồn.
- Chuyển sang DTO/domain object đã validate và có generic type đúng trước khi gọi logic nội bộ.
- Không dùng raw type nếu có thể tránh; xem compiler warnings về unchecked conversions là tín hiệu cần sửa.
- Nếu dùng `List<?>` hoặc `Box<?>`, đừng ép tất cả phần tử thành String chỉ vì một phần tử mẫu đúng kiểu.

**Không phải mọi loại lỗi generic đều cần test runtime.** Sai kiểu rõ tại compile time nên có **negative compile tests**; sai kiểu do input ngoài/raw cast mới cần **runtime validation tests** ở boundary.

## 10. Các lỗi dễ bỏ sót trong bộ test

| Lỗi | Test giúp phát hiện |
| --- | --- |
| Chỉ thử `Pair("ada",9)`, không thử component null | `typed-null-component` cho thấy pattern vẫn match nhưng guard thất bại |
| Gộp `Box(null)` với `payload == null` | `nested-null-value` và `nested-null-box` có kết quả khác |
| Quên root null | `typed-null-root` và `nested-null-root` |
| Gọi `content.toUpperCase()` khi selector là `Object` | Negative compile hoặc yêu cầu kiểm tra runtime trước |
| Tin `Box<String>` có thể được xác nhận từ `Object` bằng `instanceof` | Negative compile test `bad(Object input)` |
| Nhầm `var score` là String | Negative compile test `badInference` |
| Pattern con có sai số lượng | Negative compile test `badArity` |
| Dùng case tổng quát trước case có `when` | Compiler có thể từ chối vì dominance hoặc logic guard không còn ý nghĩa |
| Dùng `Box<?>` rồi ép mọi content về `String` | Test cả `String`, `Integer`, `null`; validation component |
| Chỉ kiểm tra output bằng mắt | Hàm `check` tự so sánh expected/actual và ném `AssertionError` |

**Thứ tự test nên có chủ đích:** trước tiên xác minh một case hợp lệ để loại trừ lỗi model/cú pháp; sau đó thêm null theo từng tầng; cuối cùng thử wildcard, generic erasure và compile negatives. Nếu một thay đổi schema làm test thất bại, thông báo cần chỉ rõ tên ca để sửa đúng tầng.

## 11. Chiến lược test khi áp dụng vào codebase thật

- **Unit tests cho logic pattern:** mỗi case/rule có input và expected output rõ ràng. Không nhất thiết phụ thuộc framework; tuy nhiên có thể chuyển hàm `check` thành assertions trong JUnit khi dự án đã có sẵn JUnit.
- **Test dữ liệu biên:** sinh các record với component null theo hợp đồng, collection rỗng, chuỗi blank, giá trị giới hạn; phân biệt invalid domain data và non-match của pattern.
- **Tests với nguồn kiểu rộng:** nhận `Object`, wildcard hoặc dữ liệu parse từ JSON; không tự giả định generic parameter. Giữ dữ liệu không tin cậy ở boundary.
- **Negative compile tests:** đặt các snippet sai trong một target kiểm thử riêng nhằm khẳng định compiler từ chối; không trộn chúng vào source đang build thành công.
- **Test khi refactor model:** nếu đổi thứ tự/thêm component của record, kiểm thử lại pattern theo thứ tự component. Với sealed hierarchy/switch exhaustive, compiler giúp phát hiện một phần trường hợp thiếu nhánh nhưng không thay thế test nghiệp vụ.
- **Runtime/phiên bản:** dùng JDK 21+ cho code record patterns; khai báo toolchain/`--release` tương ứng. JShell JDK 24 xác nhận hành vi mẫu, còn dự án nên chạy CI trên JDK mục tiêu thực sự.

Nếu dùng property-based testing, có thể sinh dữ liệu `Pair<String,Integer>` hợp lệ theo các điều kiện đã định và kiểm tra tính bất biến của output. Nhưng việc kiểm thử type erasure vẫn cần các ca cố ý sai kiểu từ biên/raw conversion; generator kiểu tĩnh thông thường có thể không tạo ra được những trường hợp đó.

## 12. Bài tập thực hành

Cho:

```java
record Result<T>(String code, T data) {}
record Page<T>(java.util.List<T> items) {}
```

Yêu cầu:

1. Viết `describe(Result<Page<String>> result)` sử dụng record pattern lồng để lấy `code` và `items`. Nếu `result == null`, trả `"missing-result"`.
2. Nếu `data == null`, trả `"missing-page"`. Nếu `Page.items == null`, trả `"missing-items"`.
3. Nếu danh sách khác null, trả `code + ":" + items.size()`.
4. Viết test cho danh sách rỗng, danh sách có hai phần tử, null ở ba tầng và code null (quyết định quy tắc hiển thị trước khi viết test).
5. Viết một negative compile test cố gắng kiểm tra `Result<Page<String>>` trực tiếp bằng `instanceof` từ một biến `Object`, rồi giải thích vì sao phải dùng wildcard và validate nội dung ở runtime.

**Gợi ý nhánh switch** (đặt trong phương thức trả `String` có tham số `Result<Page<String>> result`):

```java
return switch (result) {
    case null -> "missing-result";
    case Result(var code, Page(var items)) when items != null ->
            code + ":" + items.size();
    case Result(var code, Page(var items)) -> "missing-items";
    case Result(var code, var page) -> "missing-page";
};
```

Đây là code minh họa cho các record trên, không phải file độc lập. Thứ tự pattern nhằm phân biệt **giá trị của component null** và **record con null**. Đừng cố ép `List<String>` thành một pattern runtime chỉ nhờ tham số generic; nếu cần kiểm tra từng phần tử, hãy lặp và dùng type pattern riêng.

## 13. Ghi nhớ

**Generic record patterns kiểm tra hình dạng record và suy luận kiểu dựa trên ngữ cảnh tĩnh, không khôi phục type arguments đã bị xóa ở runtime.** Test cần bao phủ typed context, Object/wildcard, các mức null khác nhau, thứ tự guard/case và cả mã bị compiler từ chối. Bộ kiểm thử ở trên có **12 ca runtime có expected output** và **3 ca negative compile**, từ đó chứng minh rõ ràng giới hạn và khả năng của pattern matching trong Java 21.

Tài liệu chính thức:

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Java SE 21 Language Guide — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Java SE 21 Language Guide — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JLS 21 `4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.7)
