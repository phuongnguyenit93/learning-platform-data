# Kiểm thử exhaustive `switch` trong Java 21

## 1. Mục tiêu học tập

Một `switch` được gọi là **exhaustive** khi, theo kiểu tĩnh của biểu thức chọn (*selector*) và các quy tắc bao phủ kiểu của Java, tập các nhãn `case` có thể xử lý mọi giá trị mà compiler yêu cầu phải được bao phủ. Đối với `sealed` hierarchy, `enum` và record patterns, exhaustiveness đặc biệt hữu ích: khi mô hình domain có thêm một biến thể, compiler có thể phát hiện các nơi xử lý chưa cập nhật.

Nhưng **biên dịch thành công không có nghĩa logic của mọi nhánh đã đúng**. Kiểm thử exhaustive switch cần hai tầng độc lập:

1. **Kiểm tra tại compile time:** cố tình bỏ một `case` hoặc thêm một subtype và xác nhận `javac` từ chối `switch` chưa exhaustive.
2. **Kiểm thử hành vi tại runtime:** tạo từng biến thể hợp lệ, kiểm tra kết quả của từng `case`, điều kiện `when`, giá trị `null`, record lồng nhau và tình huống dữ liệu bất thường.

Trong bài này, chúng ta dùng **Java 21**: `sealed` types đã ổn định từ Java 17 (JEP 409), còn pattern matching for `switch` (JEP 441) và record patterns (JEP 440) là tính năng chính thức từ Java 21. Ví dụ biên dịch với `javac --release 21`, không cần `--enable-preview`.

## 2. Đâu là `switch` phải exhaustive?

Không nên nói đơn giản rằng “mọi `switch` của Java đều phải exhaustive”. Các cấu trúc có quy tắc khác nhau.

| Cấu trúc | Yêu cầu exhaustiveness trong Java 21 | Ghi chú |
| --- | --- | --- |
| **`switch` expression** (`return switch (...) { ... };`) | Bắt buộc | Phải cho kết quả phù hợp cho mọi đầu vào thuộc phạm vi cần bao phủ |
| **Enhanced `switch` statement** (statement có pattern hoặc các đặc trưng enhanced) | Bắt buộc | Pattern `switch` statement cũng cần exhaustive |
| **Legacy `switch` statement** chỉ có case hằng, ví dụ enum `case OPEN` | Không bắt buộc trong trường hợp legacy tương thích | Có thể thiếu hằng enum mà vẫn biên dịch; đây không phải bằng chứng đã bao phủ đủ |
| `switch` expression trên **sealed hierarchy** | Có thể exhaustive không cần `default` | Khi bao phủ tất cả subtype có thể xuất hiện |
| `switch` expression trên **enum** | Có thể exhaustive không cần `default` | Khi liệt kê mọi enum constant |
| `switch` trên `Object` với vài type patterns | Thường chưa exhaustive | Cần pattern bao phủ tất cả giá trị không-null, hoặc `default` phù hợp |

Ở một `switch` expression, các nhánh `case` có thể trả về biểu thức hoặc dùng block với `yield`; trình biên dịch kiểm tra kiểu kết quả và tính exhaustive. Ở enhanced `switch` statement, các nhánh có thể thực hiện hành động mà không trả về giá trị, nhưng vẫn phải bao phủ kiểu đầu vào.

**`default` không tự bao phủ `null`:** với reference selector, `switch` thường ném `NullPointerException` khi giá trị là `null` trừ khi có nhánh xử lý `null` thích hợp. Tính exhaustive theo kiểu không đồng nghĩa phép chọn này tự xử lý `null`.

## 3. Hai lời hứa khác nhau: “đủ case” và “đúng hành vi”

Giả sử domain có các kết quả thanh toán:

```java
sealed interface PaymentResult
        permits Approved, Declined, Pending {}

record Approved(String id, long cents) implements PaymentResult {}
record Declined(String id, String reason)
        implements PaymentResult {}
record Pending(String id) implements PaymentResult {}
```

Một `switch` với các case `Approved`, `Declined`, `Pending` không có `default` có thể được compiler xác nhận exhaustive vì root `PaymentResult` là `sealed` và ba record là `final`.

Tuy nhiên, cả ba nhánh đều có thể trả về nhầm chuỗi `"approved"` mà **compiler vẫn chấp nhận**. Bởi vậy:

- **Exhaustiveness do compiler chứng minh:** mọi biến thể thuộc kiểu tĩnh đã có đường xử lý.
- **Kết quả và side effects do test chứng minh:** mỗi biến thể được định tuyến đúng và tạo kết quả nghiệp vụ đúng.
- **An toàn phiên bản do integration test chứng minh:** consumer cũ, thư viện mới, dữ liệu trên wire và lộ trình triển khai có tương thích hay không.

Test chỉ đo code coverage 100% cũng không thể thay thế compile-time exhaustiveness: một `default` quá rộng có thể chạy và che việc không có xử lý riêng cho subtype mới.

## 4. Ví dụ hoàn chỉnh: tự kiểm thử từng case mà không cần thư viện ngoài

Chương trình dùng `sealed interface`, các `record`, record patterns và guard `when`. Nó kiểm tra **hai đường đi khác nhau của `Approved`**, hai subtype còn lại, và `null`.

Lưu vào tệp `ExhaustiveSwitchDemo.java`:

```java
public class ExhaustiveSwitchDemo {
    sealed interface PaymentResult
            permits Approved, Declined, Pending {}

    record Approved(String id, long cents) implements PaymentResult {}
    record Declined(String id, String reason)
            implements PaymentResult {}
    record Pending(String id) implements PaymentResult {}

    static String render(PaymentResult value) {
        return switch (value) {
            case Approved(var id, var cents) when cents >= 1000 ->
                    "large:" + id;

            case Approved(var id, var cents) ->
                    "approved:" + id + ":" + cents;

            case Declined(var id, var reason) ->
                    "declined:" + id + ":" + reason;

            case Pending(var id) ->
                    "pending:" + id;

            case null ->
                    "missing";
        };
    }

    static void check(String name, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + " expected=" + expected + " actual=" + actual);
        }
        System.out.println("PASS " + name);
    }

    public static void main(String[] args) {
        check("approved-small", "approved:A-1:500",
                render(new Approved("A-1", 500)));

        check("approved-large", "large:A-2",
                render(new Approved("A-2", 1500)));

        check("declined", "declined:B-1:limit",
                render(new Declined("B-1", "limit")));

        check("pending", "pending:C-1",
                render(new Pending("C-1")));

        check("null", "missing", render(null));

        System.out.println("ALL 5 PASS");
    }
}
```

Chạy với JDK 21 trở lên:

```bash
javac --release 21 ExhaustiveSwitchDemo.java
java ExhaustiveSwitchDemo
```

**Stdout chính xác:**

```text
PASS approved-small
PASS approved-large
PASS declined
PASS pending
PASS null
ALL 5 PASS
```

Ở chương trình này, `check` tự ném `AssertionError` khi sai, nên **không phụ thuộc** vào việc có bật tùy chọn `-ea` cho câu lệnh `assert` của Java hay không.

### Vì sao đây là một `switch` exhaustive?

- `PaymentResult` là `sealed`, chỉ cho phép `Approved`, `Declined`, `Pending`.
- Mỗi subtype là `record`, tức không còn class con khác của chính record đó.
- Nhánh `Approved` đầu có `when cents >= 1000`, nên **không tự bao phủ mọi** `Approved`; nhánh `Approved` thứ hai không có guard xử lý phần còn lại.
- `Declined` và `Pending` đều có case.
- `case null` tạo chính sách rõ ràng cho selector `null`; đây là kiểm thử hành vi riêng, không phải thay cho việc xử lý các subtype.

**Thứ tự nhánh có ý nghĩa.** Nhánh `Approved` có guard nằm trước nhánh `Approved` tổng quát. Nếu đảo ngược, nhánh cụ thể có thể bị case rộng hơn *dominate* và gây lỗi biên dịch hoặc trở nên không thể tiếp cận theo quy tắc dominance.

### Test matrix của ví dụ

| Input | Case được chọn | Kết quả mong đợi |
| --- | --- | --- |
| `Approved("A-1", 500)` | `Approved` không guard | `approved:A-1:500` |
| `Approved("A-2", 1500)` | `Approved` với `when` đúng | `large:A-2` |
| `Declined("B-1", "limit")` | `Declined` | `declined:B-1:limit` |
| `Pending("C-1")` | `Pending` | `pending:C-1` |
| `null` | `case null` | `missing` |

Test matrix này kiểm tra **đường đi thực tế** của các case hiện tại. Việc compiler chấp nhận `switch` không có `default` xác nhận tính exhaustive ở compile time; hai kiểm tra bổ sung cho nhau.

## 5. Negative compile test: thêm subtype nhưng cố tình không thêm `case`

Một bài kiểm thử mạnh cho thiết kế domain là chứng minh **thiếu biến thể sẽ làm build thất bại**. Hãy dùng một fixture biên dịch âm tính riêng, **không trộn vào source production**.

Lưu đoạn cố tình sai sau thành `MissingCase.java`:

```java
public class MissingCase {
    sealed interface Signal permits Go, Stop, Pause {}

    record Go() implements Signal {}
    record Stop() implements Signal {}
    record Pause() implements Signal {}

    static int code(Signal value) {
        return switch (value) {
            case Go go -> 1;
            case Stop stop -> 2;
            // Cố ý không có case Pause.
        };
    }
}
```

Thực hiện:

```bash
javac --release 21 MissingCase.java
```

**Kết quả mong đợi:** `javac` trả **exit code khác 0**, và thông báo lỗi cho biết `switch` không bao phủ mọi input có thể có, ví dụ:

```text
the switch expression does not cover all possible input values
```

Văn bản chẩn đoán cụ thể có thể khác giữa các bản `javac`, vì thế trong bài kiểm thử công cụ nên **ưu tiên xác nhận compilation thất bại**, không bắt buộc so khớp tuyệt đối câu chữ stderr.

Đây là **negative test có chủ ý không biên dịch**, không phải mã ứng dụng hoàn chỉnh để chạy. Để sửa đúng, bổ sung:

```java
case Pause pause -> 3;
```

vào `switch` trong `MissingCase`. Sau đó biên dịch lại sẽ hợp lệ nếu không còn lỗi nào khác.

### Tại sao negative compile test có giá trị?

Một test chạy `render(new Pause())` chỉ có thể được viết và thực thi **sau khi code đã biên dịch được**. Negative compile test kiểm tra một hợp đồng khác: **compiler phải ngăn ứng dụng được build nếu mô hình có subtype mới mà logic lựa chọn chưa bổ sung**.

Trong CI, nên thiết lập một test compile-negative riêng hoặc dùng một framework kiểm thử compiler. Đừng đặt fixture cố ý sai trong cùng source set được build như code production; nó sẽ khiến toàn bộ pipeline luôn đỏ.

## 6. `default` có thể làm mất tín hiệu thiếu nhánh

Xét:

```java
static int code(Signal value) {
    return switch (value) {
        case Go go -> 1;
        case Stop stop -> 2;
        default -> -1;
    };
}
```

Đây là **mã minh họa trong phạm vi đã khai báo `Signal`, `Go`, `Stop`**. Nó biên dịch dù không có `case Pause`, vì `default` bao phủ các giá trị non-null còn lại.

Nếu domain thật sự yêu cầu xử lý `Pause` riêng, `default -> -1` đã biến lỗi thiếu nhánh được compiler phát hiện thành hành vi fallback có thể không đúng nghiệp vụ.

Đối với hierarchy `sealed` có số biến thể hữu hạn và cần xét riêng từng biến thể, nên ưu tiên **không đặt `default` chỉ để hết lỗi**. Thay vào đó, cập nhật logic khi thêm subtype.

Tuy nhiên, `default` không phải luôn sai. Nếu nghiệp vụ **cố ý** gom những biến thể chưa liệt kê vào một hành vi chung, đó là một thiết kế hợp lệ. Khi ấy, test phải xác nhận rõ chủ đích fallback và reviewer hiểu rằng compiler **không còn buộc cập nhật `switch` cho mọi subtype mới**.

`default` cũng **không tự bắt `null`**. Vì thế, “có `default`” không tương đương “an toàn với mọi giá trị reference”.

## 7. Kiểm thử `when` guard và nhánh dự phòng

Pattern `case T t when condition` chỉ khớp khi:

1. Pattern kiểu `T t` khớp input.
2. Biểu thức guard `condition` trả `true`.

Compiler **không thể xem một guard tùy ý là luôn đúng**. Nếu chỉ có nhánh:

```java
case Approved(var id, var cents) when cents >= 1000 ->
        "large:" + id;
```

thì những `Approved` có `cents < 1000` vẫn phải có đường xử lý. Một `switch` không có case bao phủ phần còn lại sẽ thiếu exhaustiveness.

Trong ví dụ hoàn chỉnh, nhánh thứ hai:

```java
case Approved(var id, var cents) ->
        "approved:" + id + ":" + cents;
```

đảm nhiệm việc đó.

**Kiểm thử cần có:** ít nhất một giá trị khiến guard đúng (`1500`), một giá trị khiến guard sai (`500`), và nếu cần ranh giới chính xác thì thử `999`/`1000`. Nếu guard kiểm tra chuỗi, ngày giờ, trạng thái hoặc phép tính, nên kiểm tra thêm các giá trị biên và trường hợp có thể ném ngoại lệ.

Một negative compile test khác:

```java
sealed interface Outcome permits Success, Failure {}
record Success(int n) implements Outcome {}
record Failure() implements Outcome {}

static String broken(Outcome value) {
    return switch (value) {
        case Success(var n) when n > 0 -> "positive";
        case Failure f -> "fail";
    };
}
```

Đây cũng là **mã cố ý không biên dịch**: chưa có case cho `Success` với `n <= 0`. Cách sửa là thêm `case Success(...)` không guard, hoặc một cơ chế bao phủ hợp lệ khác.

**Ghi nhớ:** có `case` cho một subtype không tự động đồng nghĩa đã bao phủ subtype đó nếu case bị ràng buộc bởi `when`.

## 8. Kiểm thử selector `null` độc lập với exhaustiveness

Đối với reference type, `null` là một trường hợp runtime quan trọng. Có hai chính sách chính:

- **Không chấp nhận `null`:** định nghĩa hợp đồng non-null và kiểm tra API boundary; một `switch` không có `case null` có thể ném `NullPointerException` nếu vẫn nhận `null`.
- **Chấp nhận `null`:** thêm `case null -> ...` và có test kiểm tra kết quả nghiệp vụ.

Ví dụ minh họa:

```java
static String normalize(Object value) {
    return switch (value) {
        case String text -> text.trim();
        default -> "other";
    };
}
```

`normalize(42)` trả `"other"`, nhưng `normalize(null)` ném **`NullPointerException`**, mặc dù có `default`.

Nếu muốn xử lý `null`, hãy viết:

```java
static String normalize(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> text.trim();
        default -> "other";
    };
}
```

Hai đoạn là **mã minh họa bên trong class**; chúng được trình bày riêng để so sánh, không đặt cả hai phương thức cùng tên/chữ ký vào cùng một class.

Test `null` phải phản ánh chính sách đã chọn: hoặc kỳ vọng `NullPointerException`, hoặc kiểm tra giá trị do `case null` trả về. Không kết luận “switch exhaustive” là “không thể NPE”.

## 9. Enum: kiểm tra đủ các hằng, phân biệt expression với statement legacy

`enum` là một nguồn *closed set* khác. Khi một `switch` expression liệt kê đủ các enum constants, compiler có thể chấp nhận mà không cần `default`.

Lưu vào `EnumExhaustiveDemo.java`:

```java
public class EnumExhaustiveDemo {
    enum Stage { OPEN, CLOSED, HOLD }

    static int score(Stage value) {
        return switch (value) {
            case OPEN -> 10;
            case CLOSED -> 0;
            case HOLD -> 5;
        };
    }

    public static void main(String[] args) {
        for (Stage stage : Stage.values()) {
            System.out.println(stage + "=" + score(stage));
        }
    }
}
```

```bash
javac --release 21 EnumExhaustiveDemo.java
java EnumExhaustiveDemo
```

Stdout:

```text
OPEN=10
CLOSED=0
HOLD=5
```

Duyệt `Stage.values()` có lợi vì nó **tự lấy danh sách enum constants** hiện có. Khi thêm một constant mới, phần kiểm thử runtime có thể phát hiện hành vi không mong muốn nếu code còn chạy được; còn chính `switch` expression không có `default` cũng sẽ buộc cập nhật case khi **biên dịch lại**.

**Phân biệt với statement cũ:** một statement như:

```java
switch (stage) {
    case OPEN -> System.out.println("opened");
}
```

có thể biên dịch như **legacy constant switch statement** dù thiếu `CLOSED`, `HOLD`. Với nhu cầu test exhaustiveness mạnh, ưu tiên `switch` expression hoặc pattern switch có quy tắc kiểm tra exhaustive, thay vì cho rằng mọi statement đều bị compiler kiểm tra giống nhau.

Với enum `switch` expression không có `case null`, input `null` vẫn có thể ném `NullPointerException`; `Stage.values()` không chứa `null`, nên cần test riêng nếu tham số có thể nullable.

## 10. Record pattern lồng nhau: exhaustive theo kiểu nhưng cần test dữ liệu `null`

Record pattern có thể giải cấu trúc component của record. Tuy nhiên, một pattern con là **record pattern** không khớp khi component tương ứng là `null`; do đó, với dữ liệu nested record, phải kiểm tra nhánh xử lý các trường hợp thiếu record con.

Lưu vào `RecordCoverageDemo.java`:

```java
public class RecordCoverageDemo {
    sealed interface Event permits Success, Failure {}

    record Payload(int amount) {}
    record Success(String id, Payload payload)
            implements Event {}
    record Failure(String reason) implements Event {}

    static String render(Event value) {
        return switch (value) {
            case Success(var id, Payload(var amount)) ->
                    "success:" + id + ":" + amount;

            case Success success ->
                    "missing-payload:" + success.id();

            case Failure(var reason) ->
                    "failure:" + reason;

            case null ->
                    "null-event";
        };
    }

    public static void main(String[] args) {
        System.out.println(render(
                new Success("O", new Payload(7))));
        System.out.println(render(new Success("O", null)));
        System.out.println(render(new Failure("no")));
        System.out.println(render(null));
    }
}
```

```bash
javac --release 21 RecordCoverageDemo.java
java RecordCoverageDemo
```

Stdout:

```text
success:O:7
missing-payload:O
failure:no
null-event
```

Phân tích:

- Với `Success` có `Payload`, Java khớp **record pattern lồng nhau** và ràng buộc `amount`.
- Với `Success("O", null)`, pattern `Payload(var amount)` **không khớp `null`**, nên Java chuyển xét `case Success success` tổng quát.
- `case Success success` bao phủ toàn bộ subtype `Success` chưa được xử lý ở các case trước.
- Với `Failure`, matching đi vào nhánh riêng.
- Với `null` ở selector ngoài cùng, `case null` được chọn.

Tính exhaustive ở cấp `Event` được duy trì vì `Success` và `Failure` đều có nhánh không bị guard hạn chế bao phủ; nhưng **thứ tự và kết quả của record patterns vẫn cần runtime tests**. Nếu chỉ kiểm tra `Success` luôn chứa `Payload` khác null, test sẽ bỏ sót nhánh đặc biệt.

Một type pattern như `String s` cũng không khớp component `null`; `var` pattern ở vị trí component có các quy tắc null-matching khác. Đừng suy ra mọi pattern lồng nhau đều có cùng hành vi với `null`.

## 11. Nhánh `non-sealed`: exhaustive ở cấp root không đồng nghĩa biết từng plugin

`sealed` kiểm soát các subtype trực tiếp. Nếu một nhánh con được khai báo `non-sealed`, tập class bên dưới nhánh đó được mở rộng.

Ví dụ:

```java
sealed interface Event permits Known, Extension {}
record Known(int code) implements Event {}
non-sealed interface Extension extends Event {}
record Plugin(String key) implements Extension {}
```

Một `switch` có thể exhaustive bằng cách bao phủ **cả nhánh** `Extension`:

```java
static String describe(Event value) {
    return switch (value) {
        case Known(var code) -> "known:" + code;
        case Extension extension -> "extension";
    };
}
```

Đây là **các đoạn mã minh họa cùng một phạm vi khai báo**, không phải chương trình độc lập. Một plugin mới trực tiếp hoặc gián tiếp triển khai `Extension` vẫn được nhánh tổng quát đó xử lý.

Khi kiểm thử, hãy chọn rõ hợp đồng:

- Nếu mọi `Extension` dùng chung một xử lý, test ít nhất một implementation đại diện và các bất biến của API extension.
- Nếu mỗi plugin có xử lý riêng, root switch `case Extension e` **không buộc compiler** phát hiện thiếu logic cho plugin mới; cần test định tuyến plugin, registry và versioning riêng.

Như vậy, exhaustive chỉ có nghĩa **mọi giá trị có đường xử lý được compiler chấp nhận**, không có nghĩa mỗi subtype ở một nhánh mở đều được phân biệt tường minh.

## 12. Generic sealed hierarchy: kiểm tra theo kiểu selector thực tế

Exhaustiveness còn có thể phụ thuộc vào **tham số kiểu của selector** đối với sealed hierarchy generic. Ví dụ về mặt ý tưởng, một sealed interface `Response<T>` có subtype chuyên biệt chỉ implements `Response<String>` và một subtype khác có thể implements `Response<T>` cho mọi `T`.

Với selector `Response<Integer>`, subtype chỉ áp dụng cho `Response<String>` có thể **không cần** được bao phủ, vì không thể có giá trị thuộc subtype đó mà đồng thời có kiểu phù hợp với `Response<Integer>` theo quan hệ kiểu được compiler biết.

Do đó, khi viết test exhaustive cho sealed generic types:

1. Biên dịch các consumer với **đúng static type của selector**, không thay đổi tất cả thành raw `Response`.
2. Test những parameterization có ý nghĩa nghiệp vụ (`Response<String>`, `Response<Integer>`...).
3. Kiểm tra cả các pattern có type arguments và pattern được compiler suy luận kiểu.
4. Không dùng unchecked cast/raw type để “giải quyết” lỗi compile-negative; cách đó có thể mất bảo đảm tĩnh và gây lỗi runtime.

Trường hợp generic này phụ thuộc vào quy tắc *type coverage* của JLS; không nên suy luận kiểu cần bao phủ chỉ từ tên subtype mà bỏ qua generic parameterization.

## 13. Binary evolution: khi compiler không có cơ hội kiểm tra lại

Một `switch` exhaustive **không phải bảo đảm bất biến trong mọi tổ hợp binary ở runtime**. Giả sử:

1. Thư viện domain phiên bản **v1** khai báo sealed `Event permits A, B`.
2. Ứng dụng consumer biên dịch `switch` exhaustive chỉ với hai case `A`, `B`.
3. Thư viện domain **v2** thêm permitted subtype `C`.
4. Hệ thống triển khai thư viện v2 nhưng **không biên dịch lại** consumer từ v1.
5. Nếu consumer cũ gặp một instance `C`, `switch` đã biên dịch trước đó có thể ném **`MatchException`**.

Theo quy tắc tương thích nhị phân Java 21, việc **thêm permitted direct subtype** nói chung là *binary compatible*: các binary cũ không nhất thiết lỗi liên kết ngay. Nhưng `switch` cũ gặp subtype mới có thể thất bại khi chạy, đây là rủi ro **migration compatibility**.

Kiểm thử phù hợp cho hệ thống nhiều module/service:

- **Source compatibility test:** build lại consumer với domain v2; compiler buộc cập nhật case thiếu.
- **Binary compatibility test:** chạy bộ consumer build từ v1 với thư viện/domain v2 trong môi trường cô lập; chú ý đường đi thực sự truyền subtype `C`.
- **Integration/contract test:** kiểm tra serializer, schema, message version, client/server và quy trình rollout khi có event mới.
- **Telemetry/error handling:** nếu vẫn có luồng sử dụng binary cũ, cần quan sát lỗi `MatchException` và rollback/upgrade thích hợp.

`MatchException` ở tình huống này khác với `NullPointerException` khi selector null. Cũng đừng dùng catch-all `default` chỉ để che sai khác version nếu nghiệp vụ cần hiểu subtype mới.

Một thay đổi tương tự có thể xảy ra khi thêm **enum constant** mà consumer cũ chứa exhaustive enum switch chưa được biên dịch lại. Việc test phiên bản cần phản ánh tổ hợp binary thực tế, không chỉ build sạch mã nguồn mới.

## 14. Kiểm thử âm tính và dương tính nên nằm ở đâu trong dự án?

Một cấu trúc kiểm thử thực tế có thể chia thành:

| Tầng kiểm thử | Đầu vào / thao tác | Kỳ vọng |
| --- | --- | --- |
| **Compile-positive** | Build production source với `--release 21` | Tất cả `switch` cần exhaustive đều biên dịch |
| **Compile-negative** | Fixture bỏ một permitted subtype khỏi `switch` expression | `javac` thất bại theo mong đợi |
| **Runtime per-case** | Tạo mỗi record/enum variant | Đúng nhánh và đúng kết quả |
| **Guard boundary** | Tạo giá trị vừa dưới, bằng, vừa trên ngưỡng `when` | Chọn đúng nhánh guard hoặc fallback |
| **Null policy** | Truyền `null` khi API cho phép hoặc có thể nhận | Đúng `case null`, hoặc lỗi được định nghĩa |
| **Nested record** | Payload bình thường và payload `null` | Đúng pattern lồng hoặc nhánh phủ |
| **Compatibility** | Consumer binary v1 gặp dữ liệu/domain v2 | Hành vi được nhận diện và chấp nhận theo kế hoạch nâng cấp |

`javac --release 21` quan trọng khi dự án vẫn phải chạy trên Java 21 dù máy phát triển dùng JDK mới hơn. Một testcase chỉ kiểm tra bằng cú pháp preview của JDK khác có thể tạo kết luận sai về tương thích source.

Nếu sử dụng JUnit, có thể chuyển hàm `check` trong ví dụ thành assertions (`assertEquals`, `assertThrows`) và tổ chức parameterized tests; đây là cách diễn đạt theo framework, **không thay đổi nghĩa exhaustiveness của compiler**. Các negative compile fixtures cần công cụ riêng để khẳng định compiler thất bại theo mong đợi.

## 15. Kiểm thử mutation: chủ động làm hỏng switch để xác nhận “hàng rào” hoạt động

Một kỹ thuật review đơn giản là **mutation test có kiểm soát**:

1. Tạo nhánh thử nghiệm hoặc fixture từ ví dụ đang biên dịch.
2. Xóa `case Pending` ở một `switch` expression **không có `default`**.
3. Chạy `javac --release 21`; build phải thất bại do không exhaustive.
4. Khôi phục `case Pending`; build phải thành công.
5. Đổi logic ở nhánh `Declined` thành một kết quả sai và chạy runtime tests; test cho `Declined` phải bắt được.
6. Đổi ngưỡng guard (`>= 1000` thành `> 1000`); boundary test tại `1000` phải bắt được thay đổi nếu hợp đồng quy định mức này đi vào nhánh lớn.

Các mutation này kiểm tra **hai hàng rào khác nhau**:

- Thiếu case → compiler chặn.
- Case có mặt nhưng logic sai → unit test chặn.

Không giữ các mutation cố ý sai trong branch phát hành. Có thể tự động hóa negative compilation trong một fixture test để đảm bảo hành vi kiểm tra của compiler không bị vô tình vô hiệu hóa bởi các thay đổi lớn như thêm `default` ở nhiều consumer.

## 16. Cạm bẫy khi diễn giải code coverage

Các công cụ đo coverage hữu ích nhưng cần đọc đúng ý nghĩa:

- **Line coverage 100%** không chứng minh mọi subtype domain có `case` riêng, nhất là khi có `default`.
- **Branch coverage cao** không chứng minh boundary values ở guard đúng nếu test chưa chọn ranh giới quan trọng.
- **Biên dịch thành công** không chứng minh return value/side effect của từng case đúng.
- **Duyệt toàn bộ enum constants** không tự kiểm tra `null`, dữ liệu ngoại lệ hoặc consumer nhị phân cũ.
- **Test mọi class hiện biết** không chứng minh mọi implementation tương lai của một nhánh `non-sealed` đều được xử lý đúng.

Nếu domain dùng sealed hierarchy, kết hợp exhaustive switch **không có `default` khi phù hợp** với bộ test từng biến thể sẽ tạo tín hiệu thay đổi mạnh hơn là chỉ theo đuổi một con số coverage.

## 17. Lỗi thường gặp và cách sửa

| Hiểu nhầm / lỗi | Điều thực sự xảy ra | Cách kiểm tra hoặc khắc phục |
| --- | --- | --- |
| “Có `default` là exhaustive theo cách compiler nhắc mình cập nhật mọi subtype” | `default` che subtype mới | Với domain đóng, cân nhắc bỏ `default` và liệt kê case tường minh |
| “Mọi `switch` statement đều bắt buộc exhaustive” | Legacy statement chỉ dùng hằng có ngoại lệ tương thích | Dùng expression/enhanced statement khi muốn compiler bắt thiếu case |
| “Có case được guard là đã bao phủ cả subtype” | Guard sai khiến case không khớp | Thêm case không guard hoặc fallback phù hợp, test boundary |
| “Exhaustive xử lý luôn `null`” | `null` thường ném `NullPointerException` nếu không có case phù hợp | Test riêng chính sách `null` |
| “Kiểm thử một object là đủ cho mỗi record type” | Record pattern có thể chọn nhánh khác khi component `null` | Test nested data, component null, điều kiện ràng buộc |
| “Test `default` cho một subtype là test xử lý nghiệp vụ subtype đó” | Fallback có thể làm sai logic domain | Xác định subtype cần case riêng và assert kết quả |
| “Compiler bảo đảm không bao giờ có `MatchException`” | Binary cũ có thể gặp subtype mới | Biên dịch lại và test migration/integration |
| “Sealed root bảo đảm biết từng plugin” | Nhánh `non-sealed` có thể mở vô hạn | Test hợp đồng extension/registry và mapping |
| “Test đủ enum constants nghĩa là code xử lý dữ liệu ngoài đúng” | Deserialization/schema version vẫn có thể lỗi | Tách domain validation và contract tests |
| “`assert` Java luôn chạy” | Assertions có thể bị tắt khi không có `-ea` | Dùng framework assertion hoặc ném `AssertionError` tường minh |
| “Không cần biên dịch source với target JDK cụ thể” | Preview và các bản Java khác có rule/cú pháp khác | Dùng `javac --release 21` cho bài Java 21 |

## 18. Quy trình CI khuyến nghị

Một pipeline có thể tổ chức theo ý nghĩa kiểm tra, không chỉ theo công cụ:

1. **Compile với mục tiêu Java 21:** không bật preview, xác nhận mọi exhaustive switch trong production source có đủ case.
2. **Chạy unit tests của consumer:** một test cho mỗi subtype và mỗi guard branch có nghiệp vụ riêng.
3. **Chạy compile-negative fixtures:** cố tình thêm subtype hoặc bỏ case, xác nhận non-zero exit code ở compilation fixture.
4. **Chạy test nullable/nested payload:** thử selector null, component null và các giá trị giới hạn hợp lệ.
5. **Chạy integration/contract tests:** khi thay đổi danh sách permitted subtype, enum constant, serialized representation hoặc shared domain module.
6. **Review các `default` rộng:** nếu chúng đang làm mất cơ chế nhắc cập nhật case của compiler, quyết định giữ/bỏ một cách có chủ đích.

Ví dụ các bước cho chương trình độc lập trong bài:

```bash
javac --release 21 ExhaustiveSwitchDemo.java
java ExhaustiveSwitchDemo

javac --release 21 EnumExhaustiveDemo.java
java EnumExhaustiveDemo

javac --release 21 RecordCoverageDemo.java
java RecordCoverageDemo
```

Ba lệnh biên dịch trên phải thành công khi mỗi chương trình được lưu **đúng tên tệp**, cùng cú pháp như đã cho. Negative fixture `MissingCase.java` được chạy **riêng** và việc biên dịch thất bại là **kết quả kiểm thử mong đợi**, không phải lỗi cần chữa bằng `default`.

## 19. Bài tập tự kiểm tra

**Bài tập 1 — Bổ sung subtype.** Trong ví dụ `ExhaustiveSwitchDemo`, thêm:

```java
record Refunded(String id, long cents)
        implements PaymentResult {}
```

và cập nhật danh sách `permits`. Trước khi sửa `render`, thử biên dịch: compiler phải phát hiện thiếu case. Sau đó thêm case `Refunded`, chạy test cho một khoản hoàn tiền và ghi nhận output kỳ vọng.

**Bài tập 2 — Guard.** Sửa ngưỡng từ `1000` sang `2000`, tạo test tại `1999`, `2000`, `2001`. Kết quả nào thuộc nhánh `"large:"`? Tại sao test chỉ chạy `500` và `2500` chưa đủ bảo vệ điều kiện biên?

**Bài tập 3 — Nested record.** Trong `RecordCoverageDemo`, bỏ `case Success success` rồi thử biên dịch. Sau đó thêm lại nhánh, chạy test với `new Success("O", null)` và giải thích vì sao `Payload(var amount)` không khớp.

**Bài tập 4 — Enum.** Thêm hằng `ARCHIVED` vào enum `Stage`; biên dịch lại `EnumExhaustiveDemo` và quan sát phản hồi của compiler. Sửa `score` để có xử lý rõ ràng, không thêm `default` chỉ nhằm bỏ qua nhánh mới.

## 20. Checklist khi review một exhaustive switch

Trước khi kết luận phần kiểm thử đã đủ, hãy tự hỏi:

- `switch` là **expression**, **enhanced statement** hay **legacy statement**?
- Selector có kiểu tĩnh nào: enum, sealed hierarchy, generic sealed hay interface mở?
- Có `default` đang che mất cơ hội compiler báo subtype mới không?
- Những `when` guard có đủ case không guard hoặc đường fallback cho giá trị không thỏa không?
- Đã test **mỗi subtype hiện tại** và kết quả nghiệp vụ cụ thể chưa?
- Đã test `null` ở selector, component record lồng nhau và các ranh giới điều kiện chưa?
- Với nhánh `non-sealed`, hợp đồng dành cho subtype/plugin tương lai được kiểm tra ở đâu?
- Khi thư viện domain thay đổi, consumer có được **biên dịch lại** không? Nếu có binary cũ, đã test migration chưa?
- Bộ negative compile test có thật sự thất bại vì thiếu coverage, thay vì vì lỗi cú pháp khác không?
- Các kết quả kỳ vọng có dùng assertion độc lập với cấu hình runtime không?

**Kết luận:** exhaustive switch là một **cam kết bao phủ được compiler kiểm tra**, đặc biệt hữu ích với `sealed` types và enums. Để cam kết đó có giá trị thực tế, cần kết hợp **compile-positive, compile-negative và runtime tests từng nhánh**, xử lý riêng `null`/guards/nested records và kiểm tra sự tương thích khi type hierarchy phát triển. Không có một loại kiểm thử nào trong số đó có thể thay thế hoàn toàn loại còn lại.

## Tài liệu chính thức

- [JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [Oracle Java SE 21 — Pattern Matching for `switch`](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java Language Specification 21 — §14.11 `switch` Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java Language Specification 21 — §15.28 `switch` Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [Java Language Specification 21 — §13.4 Binary Compatibility và sealed types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4)
