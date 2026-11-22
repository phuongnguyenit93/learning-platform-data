# Kiểm thử dữ liệu thiếu component trong Java record — Case study thực tế

## 1. Bối cảnh và mục tiêu

Giả sử một hệ thống xử lý hóa đơn nhận payload từ API hoặc message queue. Mô hình domain dùng `record`:

```java
record Invoice(String id, long cents, String currency) {}
```

Hợp đồng nghiệp vụ yêu cầu `id` và `currency` không rỗng, số tiền `cents` lớn hơn 0. Nhưng một payload từ bên ngoài có thể thiếu khóa `id`, có `"currency": null`, dùng `"cents": "500"` thay vì số, hoặc chứa dữ liệu sai trong record lồng nhau.

**Kiểm thử dữ liệu thiếu component** không phải là “gọi constructor record mà bỏ bớt một đối số”. Record có danh sách component cố định ở cấp source. Tình huống cần kiểm thử thực tế là **dữ liệu bên ngoài thiếu trường** hoặc **component của record đã tạo có giá trị không hợp lệ**, thường do mapping, deserialize, code legacy hay constructor/factory quá dễ dãi.

Kết thúc bài, người học có thể:

1. Phân biệt **thiếu trường đầu vào**, **trường tồn tại với `null`**, **sai kiểu**, **giá trị không hợp lệ** và **component lồng bị `null`**.
2. Hiểu record constructor, accessors và record patterns hoạt động khi component không đầy đủ.
3. Viết test phân loại từng tình huống bằng Java 21, có stdout xác định.
4. Đặt validation đúng chỗ: ranh giới dữ liệu, canonical constructor/factory và logic pattern matching.
5. Tránh tin rằng `record` hoặc `switch` exhaustive tự động bảo đảm mọi component có dữ liệu hợp lệ.

Các ví dụ dùng **Java 21 final** cho record patterns (JEP 440) và pattern matching for `switch` (JEP 441). Record classes đã final từ Java 16 (JEP 395).

## 2. “Thiếu component” có ít nhất năm nghĩa khác nhau

| Tình huống | Ví dụ | Có thể xảy ra ở đâu? | Cách kiểm tra |
| --- | --- | --- | --- |
| Thiếu đối số constructor trong mã Java | `new Invoice("I-1", 500L)` | Source Java | Compiler từ chối vì sai số lượng tham số |
| Thiếu khóa trong payload | Không có key `"currency"` | JSON/Map/request | `containsKey`, schema hoặc validation |
| Có khóa nhưng giá trị `null` | `"currency": null` | Payload hoặc record tham chiếu | Kiểm tra null/constructor |
| Giá trị sai kiểu | `"cents": "500"` | Parser, mapping, API | Type pattern hoặc conversion có quy tắc |
| Giá trị hợp kiểu nhưng sai nghiệp vụ | `cents = 0`, `id = " "` | Domain object | Invariant ở constructor/factory |
| Bản ghi lồng thiếu object | `customer.address == null` | Dữ liệu domain cũ/DTO | Test nested patterns và fallback |

**Nguyên tắc:** Java record định nghĩa **hình dạng tĩnh** (tên, kiểu, số lượng component). Nó không tự xác minh tính đầy đủ của dữ liệu nhận qua giao thức ngoài Java; càng không mặc nhiên cấm `null` ở component kiểu tham chiếu.

Chẳng hạn:

```java
record Pair(String left, String right) {}

// Hai dòng dưới đây minh họa hai trường hợp khác nhau:
new Pair("A", null); // HỢP LỆ nếu record không có validation.
new Pair("A");       // LỖI BIÊN DỊCH: thiếu đối số thứ hai.
```

Lệnh `new Pair("A")` là **negative compile example**, không được đặt vào tệp source production. Với record `Pair` không định nghĩa constructor bổ sung, canonical constructor có hai tham số tương ứng hai component.

Tương tự, pattern:

```java
// SAI trong Java 21: cần đúng hai component patterns.
if (value instanceof Pair(var left)) {
    System.out.println(left);
}
```

bị compiler từ chối khi `Pair` có hai component. Record pattern không có cú pháp “lược bỏ component cuối vì không dùng”. Muốn bỏ qua logic của component nhưng vẫn viết pattern, dùng `Pair(var left, var right)` trong Java 21 và chỉ dùng `left`, hoặc dùng `Pair pair` rồi gọi `pair.left()`.

## 3. Case study A: record lồng nhau có component thiếu giá trị

Xét một mô hình đơn hàng:

```java
record Address(String city) {}
record Customer(String name, Address address) {}
record Order(String id, Customer customer) {}
```

Trong phiên bản permissive, các record **không có validation**. Java chấp nhận:

```java
new Order("O-5", null);
new Order("O-4", new Customer("An", null));
new Order("O-2", new Customer("An", new Address(null)));
```

Mỗi lời gọi vẫn cung cấp **đủ tham số constructor**, chỉ có một component tham chiếu nhận giá trị `null`.

Đây là trường hợp thường gặp khi domain model được tạo trực tiếp từ dữ liệu chưa kiểm tra hoặc dữ liệu legacy. Người viết consumer có thể dùng nested record patterns, nhưng cần biết **pattern nào khớp, pattern nào không**.

## 4. Ví dụ hoàn chỉnh: kiểm thử nested record patterns và null

Lưu chương trình sau vào `MissingComponentDemo.java`:

```java
public class MissingComponentDemo {
    record Address(String city) {}
    record Customer(String name, Address address) {}
    record Order(String id, Customer customer) {}

    static String route(Order order) {
        return switch (order) {
            case Order(
                    var id,
                    Customer(var name, Address(String city)))
                    when id != null && name != null && city != null ->
                    "complete:" + id + ":" + name + ":" + city;

            case Order(
                    var id,
                    Customer(var name, Address(var city))) ->
                    "incomplete-city-or-fields:" + id;

            case Order(var id, Customer(var name, var address)) ->
                    "missing-address:" + id;

            case Order(var id, var customer) ->
                    "missing-customer:" + id;

            case null ->
                    "null-order";
        };
    }

    public static void main(String[] args) {
        System.out.println(route(
                new Order("O-1", new Customer(
                        "An", new Address("Hue")))));

        System.out.println(route(
                new Order("O-2", new Customer(
                        "An", new Address(null)))));

        System.out.println(route(
                new Order("O-3", new Customer(
                        null, new Address("Hanoi")))));

        System.out.println(route(
                new Order("O-4", new Customer(
                        "An", null))));

        System.out.println(route(new Order("O-5", null)));
        System.out.println(route(null));
    }
}
```

Biên dịch và chạy với JDK 21 trở lên:

```bash
javac --release 21 MissingComponentDemo.java
java MissingComponentDemo
```

**Stdout mong đợi:**

```text
complete:O-1:An:Hue
incomplete-city-or-fields:O-2
incomplete-city-or-fields:O-3
missing-address:O-4
missing-customer:O-5
null-order
```

### Giải thích lần lượt

- `O-1`: `Order`, `Customer`, `Address` có mặt và `id`, `name`, `city` không null nên nhánh đầu khớp.
- `O-2`: `Address` tồn tại nhưng `city == null`. Nhánh có guard đầu tiên không thành công; nhánh thứ hai nhận record này.
- `O-3`: tên khách hàng `null`; dù `city` hợp lệ, guard đầu tiên không đạt, nên nhánh thứ hai xử lý.
- `O-4`: `Customer` tồn tại nhưng `address == null`; nested record pattern `Address(...)` không khớp ở component đó. Nhánh `Customer(var name, var address)` nhận.
- `O-5`: `customer == null`; pattern `Customer(...)` không khớp, nhưng nhánh `Order(var id, var customer)` nhận.
- `null`: bản thân selector là null, được xử lý riêng bằng `case null`.

Các chuỗi trả về minh họa **phân loại**, không phải chính sách domain bắt buộc. Khi xây dựng sản phẩm, có thể chọn ném lỗi, từ chối yêu cầu hoặc ghi sự kiện quan sát tùy hợp đồng.

## 5. Một chi tiết Java 21 dễ gây nhầm: null-matching ở component type pattern

Không được viết quy tắc tổng quát “mọi `String s` pattern đều không khớp `null`”. Java 21 phân biệt **type pattern được dùng trực tiếp trong `instanceof`** với **type pattern unconditional nằm trong danh sách component của record pattern**.

Ví dụ:

```java
record Address(String city) {}
Object input = new Address(null);
```

Với component tĩnh `String city`, pattern:

```java
input instanceof Address(String city)
```

**có thể khớp** ngay cả khi component `city` là null. Trong JLS Java 21, một type pattern nằm trực tiếp ở vị trí component record, **unconditional đối với kiểu component**, là *null-matching*. Pattern variable có thể được gán `null`.

Trong khi đó:

```java
Object input = null;
input instanceof Address(var city)
```

là `false`, vì **bản thân record reference** là null. Một record pattern không khớp record reference null.

Và:

```java
Object value = null;
value instanceof String s
```

cũng là `false` với `instanceof` trực tiếp.

Do đó trong `MissingComponentDemo`, nhánh đầu **cố ý có guard**:

```java
when id != null && name != null && city != null
```

Nếu chỉ viết `Address(String city)` rồi tin rằng mọi `city` là non-null, test có thể bắt được lỗ hổng. **Một successful record pattern match không thay thế validation các reference components.**

Điều kiện null-matching của component type pattern phụ thuộc kiểu tĩnh của component và tính unconditional của pattern. Đừng suy diễn rằng mọi type pattern trong mọi record đều nhận null; ví dụ type pattern `String s` đặt cho component khai báo là `Object` là một bài toán khác. Xem JLS Java 21 §14.30.1–§14.30.3.

## 6. Case study B: dữ liệu đầu vào dạng Map không có đủ trường

Ở ranh giới JSON/API, ta thường chưa có `Invoice`. Ta có thể nhận một cấu trúc tương đương `Map<String, Object>`:

```java
{
    "id": "I-7",
    "cents": 500,
    "currency": "VND"
}
```

Đoạn trên là **mô tả dữ liệu JSON**, không phải cú pháp Java. Một số request có thể bỏ hẳn key `"cents"`; một số có key đó với `null`; và một số đưa chuỗi `"500"` thay cho số.

Trong `Map`, kiểm tra:

```java
map.get("currency") == null
```

**không phân biệt được** hai tình huống:

1. Map **không có key** `"currency"`.
2. Map có key `"currency"` nhưng giá trị **là null**.

Muốn phân biệt, phải kiểm tra:

```java
map.containsKey("currency")
```

rồi mới phân loại giá trị.

Đây là chi tiết rất quan trọng nếu hợp đồng API muốn đưa ra mã lỗi khác nhau cho `missing field` và `explicit null`. Nếu payload đã được deserialize trực tiếp thành record, thư viện mapping có thể đã biến hai trường hợp thành một giá trị giống nhau, tùy cấu hình; vì vậy nên kiểm tra schema hoặc representation trung gian nếu cần bảo toàn sự khác biệt này.

## 7. Thiết kế record chặt chẽ: compact canonical constructor

Record không tự bảo đảm `id` không blank, số tiền dương hoặc `currency` hợp lệ. Đặt validation ở compact canonical constructor sẽ khiến mọi lệnh gọi constructor chuẩn **tự kiểm tra invariant**.

```java
record Invoice(String id, long cents, String currency) {
    Invoice {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("invalid:id");
        }
        if (cents <= 0) {
            throw new IllegalArgumentException("invalid:cents");
        }
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException("invalid:currency");
        }
    }
}
```

Đây là **đoạn minh họa type declaration**. Compact constructor nhận giá trị các component như tham số ngầm. Khi constructor kết thúc bình thường, Java thực hiện gán các component field tương ứng.

Lợi ích:

- `new Invoice(null, 500L, "VND")` bị từ chối.
- `new Invoice("I-7", 0L, "VND")` bị từ chối.
- `new Invoice("I-7", 500L, " ")` bị từ chối.
- Những nơi khác tạo `Invoice` qua canonical constructor cùng chịu một bộ invariant.

**Giới hạn:** Nếu bạn nhận JSON thiếu `"cents"`, primitive `long` không có giá trị null để biểu diễn “không được cung cấp”. Một mapper có thể gán mặc định `0`, từ chối sớm hoặc có hành vi khác tùy cấu hình. Đừng coi giá trị `0` luôn là bằng chứng trường bị thiếu: nó cũng có thể là giá trị được cung cấp rõ ràng nhưng không hợp lệ. Khi cần phân biệt, validate dữ liệu đầu vào **trước** khi dựng record.

## 8. Ví dụ chạy được: validate payload rồi tạo record

Chương trình sau là một bài kiểm thử nhỏ độc lập, **không cần thư viện JSON hay JUnit**. Nó kiểm tra đủ: payload hợp lệ, thiếu key, key có null, sai kiểu và giá trị blank.

Lưu thành `PayloadDecoderDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class PayloadDecoderDemo {
    record Invoice(String id, long cents, String currency) {
        Invoice {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("invalid:id");
            }
            if (cents <= 0) {
                throw new IllegalArgumentException("invalid:cents");
            }
            if (currency == null || currency.isBlank()) {
                throw new IllegalArgumentException("invalid:currency");
            }
        }
    }

    static Invoice parse(Map<String, ?> payload) {
        Objects.requireNonNull(payload, "payload");

        if (!payload.containsKey("id")) {
            throw new IllegalArgumentException("missing:id");
        }
        if (!(payload.get("id") instanceof String id)) {
            throw new IllegalArgumentException("invalid:id-type");
        }

        if (!payload.containsKey("cents")) {
            throw new IllegalArgumentException("missing:cents");
        }
        if (!(payload.get("cents") instanceof Long cents)) {
            throw new IllegalArgumentException("invalid:cents-type");
        }

        if (!payload.containsKey("currency")) {
            throw new IllegalArgumentException("missing:currency");
        }
        if (!(payload.get("currency") instanceof String currency)) {
            throw new IllegalArgumentException("invalid:currency-type");
        }

        return new Invoice(id, cents, currency);
    }

    static void check(String name, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + ": expected=" + expected
                            + " actual=" + actual);
        }
        System.out.println("PASS " + name);
    }

    static void reject(
            String name, Map<String, ?> payload, String expected) {
        try {
            parse(payload);
            throw new AssertionError(
                    "Expected invalid input: " + name);
        } catch (IllegalArgumentException ex) {
            check(name, expected, ex.getMessage());
        }
    }

    public static void main(String[] args) {
        Map<String, Object> good = new HashMap<>();
        good.put("id", "I-7");
        good.put("cents", 500L);
        good.put("currency", "VND");

        check("valid",
                "Invoice[id=I-7, cents=500, currency=VND]",
                parse(good).toString());

        Map<String, Object> missing = new HashMap<>(good);
        missing.remove("cents");
        reject("missing-cents", missing, "missing:cents");

        Map<String, Object> explicitNull = new HashMap<>(good);
        explicitNull.put("currency", null);
        reject("null-currency", explicitNull,
                "invalid:currency-type");

        Map<String, Object> wrong = new HashMap<>(good);
        wrong.put("cents", "500");
        reject("wrong-type", wrong, "invalid:cents-type");

        Map<String, Object> blank = new HashMap<>(good);
        blank.put("id", " ");
        reject("blank-id", blank, "invalid:id");

        System.out.println("ALL 5 PASS");
    }
}
```

Chạy:

```bash
javac --release 21 PayloadDecoderDemo.java
java PayloadDecoderDemo
```

**Stdout mong đợi:**

```text
PASS valid
PASS missing-cents
PASS null-currency
PASS wrong-type
PASS blank-id
ALL 5 PASS
```

### Phân tích vì sao test có giá trị

- **Valid:** payload có đủ key, đúng kiểu dữ liệu, hợp invariant nên tạo `Invoice`.
- **Missing:** `remove("cents")` xóa hẳn key, nên `containsKey` phát hiện `"missing:cents"`.
- **Explicit null:** map có `"currency"` nhưng giá trị null; `instanceof String` trả false và báo `"invalid:currency-type"`, không nhầm thành thiếu key.
- **Wrong type:** `"500"` là chuỗi, khác `Long`, bị từ chối trước khi vào constructor.
- **Business invalid:** `" "` vẫn là `String`, nên qua bước kiểm tra type nhưng bị compact constructor từ chối như giá trị không hợp lệ.

`HashMap` được dùng vì **cho phép giá trị null**. `Map.of(...)` trong Java **không cho phép null key hoặc value**, nên không thích hợp để dựng trường hợp `explicit null` này.

**Chú ý đặc tả ví dụ:** parser yêu cầu giá trị tiền là Java `Long`. Một thư viện JSON có thể ánh xạ số nguyên sang `Integer`, `Long`, `BigInteger` hay kiểu khác tùy cấu hình. Trong ứng dụng thật, hãy định nghĩa đúng schema và chiến lược chuyển số (bao gồm range/overflow/precision) thay vì coi việc `instanceof Long` luôn là quy tắc chung cho JSON. Ở đây kiểm tra kiểu nghiêm ngặt được chọn có chủ đích để minh họa.

## 9. Nên kiểm thử missing và null như hai ca riêng

Một số test chỉ tạo:

```java
new Invoice(null, 500L, null)
```

rồi kiểm tra exception. Test ấy **không chứng minh** parser phát hiện key bị thiếu trong payload; đối tượng đã được tạo bằng lời gọi có đầy đủ vị trí tham số.

Với `Map`, nên xây dựng các fixtures riêng:

```java
Map<String, Object> absent = new HashMap<>();
absent.put("id", "I-7");
absent.put("cents", 500L);
// Không có key "currency".

Map<String, Object> presentNull = new HashMap<>();
presentNull.put("id", "I-7");
presentNull.put("cents", 500L);
presentNull.put("currency", null);
```

- `absent.containsKey("currency")` là `false`.
- `presentNull.containsKey("currency")` là `true`.
- `get("currency")` trả `null` ở **cả hai** trường hợp.

Nếu API phân biệt “không gửi field” với “gửi field null để xóa”, điều này càng quan trọng cho **PATCH/update request**. Đừng chỉ dùng `Optional<String>` để diễn đạt cả ba trạng thái **không gửi / gửi null / gửi giá trị** nếu API cần phân biệt chính xác; `Optional.empty()` không tự chứa thông tin về việc key có tồn tại hay không.

## 10. Record component là `null` không nhất thiết là lỗi compile

Một giả định sai là: “Record immutable nên không có component null”. Record cung cấp các component field `private final` và API accessors, nhưng kiểu tham chiếu vẫn có thể nhận `null` nếu constructor không kiểm tra.

Ví dụ:

```java
record Draft(String title, String note) {}

Draft draft = new Draft("Hello", null);
System.out.println(draft.note()); // In ra null.
```

Đây là **đoạn minh họa trong class/method**, không phải tệp độc lập. Sự hiện diện của `final` không tạo yêu cầu non-null.

Để bảo vệ domain:

- Nếu component **bắt buộc**, kiểm tra ở canonical constructor/factory.
- Nếu component **không bắt buộc**, ghi rõ chính sách `null` hoặc dùng một mô hình có ý nghĩa, ví dụ value object cho trạng thái đặc biệt.
- Nếu một `record` chứa collection/map mutable, record chỉ **shallowly immutable**: có thể cần `List.copyOf` hoặc `Map.copyOf` khi khởi tạo, sau khi đã xử lý policy về null.

Không nên thêm `Optional` vào mọi record component một cách máy móc. Thiết kế cần phản ánh domain và hợp đồng API, nhất là việc phân biệt missing và explicit null ở dữ liệu bên ngoài.

## 11. Bảng test matrix cho case study

Một bộ test đầy đủ có thể dựa vào bảng sau:

| ID | Tình huống | Tầng cần kiểm thử | Kỳ vọng |
| --- | --- | --- | --- |
| T01 | Có đủ key, đúng kiểu, hợp lệ | Payload + constructor | Tạo `Invoice` |
| T02 | Thiếu `"id"` | Payload parser | `missing:id` |
| T03 | Có `"id": null` | Payload parser | `invalid:id-type` |
| T04 | `"id": " "` | Constructor invariant | `invalid:id` |
| T05 | Thiếu `"cents"` | Payload parser | `missing:cents` |
| T06 | `"cents": null` | Payload parser | `invalid:cents-type` |
| T07 | `"cents": "500"` | Payload parser | `invalid:cents-type` |
| T08 | `"cents": 0L` | Constructor invariant | `invalid:cents` |
| T09 | Thiếu `"currency"` | Payload parser | `missing:currency` |
| T10 | `"currency": null` | Payload parser | `invalid:currency-type` |
| T11 | `"currency": ""` | Constructor invariant | `invalid:currency` |
| T12 | Nested `Address(null)` | Nested pattern | Nhánh xử lý giá trị chưa đầy đủ |
| T13 | Nested `Customer(..., null)` | Nested pattern | Nhánh `missing-address` |
| T14 | `Order(..., null)` | Nested pattern | Nhánh `missing-customer` |
| T15 | Selector `Order` null | `switch` | `case null` |
| T16 | Constructor thiếu đối số | Compile-negative | `javac` báo lỗi arity |
| T17 | Record pattern thiếu component | Compile-negative | `javac` báo lỗi pattern arity |

Không cần viết một phương thức riêng cho mọi dòng bằng tay; có thể dùng **parameterized tests** để chia nhóm đầu vào. Nhưng mỗi nhóm phải có assertion về lỗi/kết quả cụ thể, không chỉ kiểm tra “không bị crash”.

## 12. Compile-negative tests: đúng số component là ràng buộc tĩnh

Tạo file fixture `BadRecordArity.java` với mã **cố ý không biên dịch**:

```java
public class BadRecordArity {
    record Pair(String left, String right) {}

    public static void main(String[] args) {
        new Pair("only-left"); // Sai: record cần 2 đối số.
    }
}
```

Chạy riêng:

```bash
javac --release 21 BadRecordArity.java
```

**Kỳ vọng:** `javac` có exit code khác 0 vì constructor yêu cầu hai tham số. Không bao gồm fixture này trong source set production.

Fixture thứ hai cũng cố ý không biên dịch:

```java
record Pair(String left, String right) {}

static void wrong(Object input) {
    if (input instanceof Pair(var left)) {
        System.out.println(left);
    }
}
```

Đoạn thứ hai là **mã minh họa bên trong class** đã khai báo `Pair`; không phải file độc lập. Record pattern phải có **đúng số lượng component patterns** với record class; `Pair(var left)` chỉ có một pattern trong khi record có hai component.

Cách viết hợp lệ:

```java
if (input instanceof Pair(var left, var right)) {
    System.out.println(left);
}
```

Chú ý “bỏ qua component” ở cấp **logic sử dụng** khác với “bỏ component” ở cấp **pattern arity**. Compiler quản lý arity và type compatibility; runtime test quản lý giá trị thực sự của component.

## 13. `switch` exhaustive không bảo đảm component hợp lệ

Một sealed hierarchy có thể làm cho `switch` exhaustive về **loại record**, nhưng **không chứng minh** `String id` hay nested `Address city` là non-null/nonblank.

Ví dụ:

```java
sealed interface PaymentResult permits Paid, Rejected {}

record Paid(String id, long cents) implements PaymentResult {}
record Rejected(String reason) implements PaymentResult {}
```

Một `switch` có đủ `case Paid(...)` và `case Rejected(...)` có thể exhaustive, nhưng vẫn có thể xử lý `new Paid(null, -1)` nếu constructor không validate.

Nên kết hợp:

1. **Domain invariant** tại record constructor/factory.
2. **Pattern `switch`** để phân nhánh theo biến thể/định dạng.
3. **Boundary validation** để phân biệt missing, explicit null và sai kiểu từ dữ liệu bên ngoài.
4. **Unit/integration tests** để kiểm tra cả lỗi dữ liệu lẫn logic nghiệp vụ.

`case null` giải quyết selector null trong `switch`, **không thay thế** xử lý component null ở bên trong một record hợp lệ.

## 14. Vai trò của `when` guard trong dữ liệu thiếu component

Trong ví dụ `MissingComponentDemo`, guard:

```java
when id != null && name != null && city != null
```

đóng vai trò **điều kiện nghiệp vụ tại consumer**. Nó giúp không gắn nhãn `"complete"` cho record có component chưa đủ thông tin.

Tuy nhiên, guard không nên là **tuyến phòng thủ duy nhất** cho domain invariant. Nếu `Order` bắt buộc có `Customer`, `Address`, `city` không trống, lý tưởng là constructor/factory đã kiểm tra trước khi đưa record vào domain.

Guard có ích ở các trường hợp:

- Hệ thống đang đọc **legacy data** có thể không hợp lệ.
- Một DTO dùng cho form nhập chưa hoàn chỉnh, vì vậy null được cho phép có chủ đích.
- Consumer cần phân loại dữ liệu để trả lỗi thân thiện thay vì fail ngay lúc parse.

**Cẩn thận với guard:** một case có `when` **không bao phủ toàn bộ subtype**. Cần case không guard ở phía sau để xử lý phần dữ liệu còn lại nếu `switch` expression yêu cầu exhaustive. Đừng chỉ thêm `default -> "unknown"` mà che mất lý do dữ liệu thiếu.

## 15. Kiểm thử dữ liệu deserialize từ JSON

Cách mapping JSON vào record phụ thuộc thư viện: Jackson, Gson, JSON-B, framework binding hoặc custom serializer **không nhất thiết** xử lý field thiếu giống nhau. Một mapper có thể:

- Truyền `null` cho reference component không có trong payload.
- Dùng giá trị mặc định cho primitive component khi field bị thiếu, hoặc báo lỗi.
- Từ chối property không nhận diện được.
- Áp dụng validation annotation/configuration hoặc bỏ qua nếu không bật.

**Không được mặc định** rằng “field thiếu tự ném `MissingComponentException`” hoặc “record tự trả `Optional.empty`”. Java SE record mechanism không quy định toàn bộ hành vi của các JSON libraries.

Nếu production dùng một mapper cụ thể, cần integration tests tối thiểu cho:

- JSON object đủ trường.
- JSON thiếu một field bắt buộc.
- JSON có field với giá trị `null`.
- JSON có field sai kiểu.
- Primitive số sai định dạng hoặc ngoài phạm vi.
- Nested object thiếu và nested object `null`.
- Thứ tự property và unknown properties nếu contract có liên quan.

Test phải ghi **phiên bản thư viện mapping và cấu hình**; không thay một integration test bằng giả định dựa trên tên thư viện.

## 16. Schema evolution: thêm component có thể ảnh hưởng dữ liệu cũ

Giả sử một phiên bản domain cũ có:

```java
record Customer(String name) {}
```

Phiên bản mới thêm component:

```java
record Customer(String name, String email) {}
```

Ở source Java, `new Customer("An")` **không tự hợp lệ** sau khi thay đổi record nếu không có constructor bổ sung. Hãy thiết kế migration cụ thể: thêm constructor delegating với default **có chủ đích**, cập nhật caller, hoặc tách DTO tương thích.

Ví dụ source-level migration:

```java
record Customer(String name, String email) {
    Customer(String name) {
        this(name, "unknown@example.invalid");
    }
}
```

Đây là **đoạn minh họa**, không phải một địa chỉ email thật cần liên hệ. Default chỉ hợp lý khi business policy cho phép trạng thái đó; đừng tạo giá trị giả tùy tiện cho dữ liệu cá nhân hoặc nghiệp vụ có tính ràng buộc.

Với dữ liệu lưu trữ/JSON cũ không có `"email"`, vẫn cần schema versioning hoặc adapter. Constructor một tham số ở Java **không bảo đảm** mọi mapper JSON sẽ tự chọn đúng overload nếu không có cấu hình thích hợp.

Việc thay đổi record component list còn có thể ảnh hưởng đến canonical constructor signature, accessors và các record patterns trong consumer. Vì vậy phải có source compile tests, integration tests cho dữ liệu cũ và mới, cùng kế hoạch rollout.

## 17. Phân biệt lỗi do accessor với lỗi do dữ liệu thiếu

Record pattern phải lấy giá trị các component thông qua accessor tương ứng. Trong Java 21, nếu accessor được override và ném exception khi deconstruct, pattern matching có thể hoàn tất đột ngột bằng **`MatchException`** chứa nguyên nhân. Đây là tình huống khác với:

- Dữ liệu component null nhưng pattern có thể match.
- Nested record reference null khiến nested record pattern không match.
- Constructor từ chối dữ liệu không hợp lệ với `IllegalArgumentException`.

Nếu dự án dùng record accessor tùy biến có side effects, nên kiểm thử exception/observability riêng; đừng gộp mọi lỗi thành “missing component”. Với domain record, nên giữ accessor đơn giản và đặt validation ở constructor/factory để tránh logic deconstruction khó đoán.

## 18. Dữ liệu thiếu ở PATCH request khác record snapshot

Một `record Invoice(String id, long cents, String currency)` thường biểu diễn **snapshot đầy đủ của một giá trị**. Nhưng một PATCH request có thể chỉ gửi những field muốn thay đổi:

```json
{ "currency": "USD" }
```

Trong ngữ cảnh PATCH, “thiếu `id`/`cents`” có thể **hợp lệ vì chúng không được thay đổi**, chứ không có nghĩa dữ liệu hóa đơn sai.

Không nên reuse ngay record `Invoice` làm PATCH DTO nếu nó ép mọi field phải có mặt. Có thể xây dựng `InvoicePatch` với **mô hình ba trạng thái** cho từng field: không gửi, gửi null, gửi giá trị. Khi nhận patch, hệ thống merge với domain object hiện hữu, validate record mới rồi mới lưu.

Việc dùng `Optional<T>` không tự giải quyết ba trạng thái trên. `Optional.empty()` vẫn cần được phân biệt với “không có property trong payload” nếu hợp đồng cho phép explicit null có nghĩa “clear field”.

Do đó **test missing component phải gắn với ngữ cảnh API**: thiếu field trong lệnh CREATE có thể là lỗi, còn thiếu field trong PATCH có thể là điều bình thường.

## 19. Checklist code review và test

- [ ] Đã phân biệt record constructor arity với field thiếu trong payload chưa?
- [ ] Đã kiểm thử **missing key** và **present-but-null** riêng chưa?
- [ ] Có kiểm tra sai kiểu dữ liệu và giá trị hợp kiểu nhưng vi phạm invariant không?
- [ ] Với primitive component, có xử lý rõ việc không thể biểu diễn null sau khi mapping không?
- [ ] Compact constructor/factory đã kiểm tra các component bắt buộc chưa?
- [ ] Có unit tests cho nested record reference null, component null và selector null không?
- [ ] Có nhớ rằng một component type pattern unconditional **có thể match null** không?
- [ ] Mọi `when` guard đều có test true/false và nhánh fallback phù hợp chưa?
- [ ] JSON mapper production có integration tests theo **version/config thực tế** không?
- [ ] Có dự phòng cho dữ liệu cũ khi thêm/đổi component của record không?
- [ ] Có phân biệt CREATE payload đầy đủ với PATCH payload từng phần không?
- [ ] Nếu dùng `Map.of`, có tránh đặt null vào đó khi tạo null-case fixture không?
- [ ] Đã tách compile-negative tests khỏi source build production chưa?

**Kết luận:** Record quy định **số lượng và kiểu component ở compile time**; nó không tự khắc phục field bị thiếu ở payload, reference null hay giá trị nghiệp vụ không hợp lệ. Kiểm thử tốt cần tách các trường hợp missing/null/wrong type, dùng constructor để giữ invariant, dùng record patterns có guard và fallback cẩn thận, rồi kiểm tra boundary mapper bằng dữ liệu thực tế. Với nested record patterns của Java 21, đặc biệt đừng giả định mọi component type pattern đều loại trừ null.

## Tài liệu tham khảo chính thức

- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java SE 21 JLS §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10)
- [Java SE 21 JLS §14.30 — Patterns, null-matching, unconditional patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Java SE 21 JLS §15.20.2 — Type Comparison Operator `instanceof`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2)
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
