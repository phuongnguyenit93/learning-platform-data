# Kiểm thử nested record pattern trong Java 21

## 1. Mục tiêu bài học

**Nested record pattern** là record pattern chứa một hoặc nhiều record pattern khác trong danh sách component, cho phép kiểm tra một cấu trúc dữ liệu nhiều tầng và bind các giá trị nằm sâu bên trong. Ví dụ một `Order` chứa `Customer`, `Customer` chứa `Address`:

```java
record Address(String city, String zip) {}
record Customer(String id, Address address) {}
record Order(String number, Customer buyer, List<String> items) {}
```

Một pattern có thể đi xuyên qua ba tầng:

```java
case Order(var number,
           Customer(String customerId, Address(String city, String zip)),
           var items) -> ...
```

Đoạn này minh họa nhãn trong `switch`, giả định đã import `java.util.List` và định nghĩa các record bên trên. Vấn đề kiểm thử không chỉ là "đối tượng có đúng kiểu không". Phải kiểm tra: **pattern ngoài match hay không, các record lồng nhau match hay không, biến bind nhận giá trị nào, component `null` được xử lý theo quy tắc nào, guard có chạy hay không, thứ tự nhánh ra sao và accessor có tạo side effect/exception không**.

Sau bài học, bạn sẽ:

1. Xây dựng **ma trận test dương/âm, biên và null** cho nested record pattern.
2. Phân biệt **top-level type pattern**, **nested type pattern**, **nested record pattern** và cơ chế *null-matching* của Java 21.
3. Test pattern trong `instanceof` và `switch` với guard `when`, ưu tiên nhánh, dominance và exhaustiveness.
4. Xác minh **giá trị bind**, **thứ tự đánh giá**, **số lần accessor chạy**, ngoại lệ `MatchException`.
5. Viết test **tự động chạy được chỉ với JDK 21**, dùng các assertions không phụ thuộc `-ea`.
6. Biết cách dùng unit test framework, test theo bảng, test thuộc tính và negative compiler tests khi dự án cần.

**Mức Java:** Record patterns (JEP 440) và pattern matching cho `switch` (JEP 441) là tính năng chuẩn của **Java 21**. Không dùng tính năng preview, không cần `--enable-preview`. Type pattern với `instanceof` đã chuẩn từ Java 16 (JEP 394).

## 2. Hiểu chính xác điều được kiểm thử

Một nested record pattern có hai loại thành phần quan trọng:

- **Record pattern**, ví dụ `Address(String city, String zip)`: giá trị phải là một record `Address` không `null`, rồi Java tiếp tục match từng component.
- **Type pattern**, ví dụ `String city`: bind giá trị vào biến `city` khi match; ở vị trí **trực tiếp là component của record pattern**, quy tắc match `null` có thể khác với type pattern ở cấp ngoài.

Xét mẫu:

```java
input instanceof Order(
        var number,
        Customer(String customerId, Address(String city, String zip)),
        var items)
```

Java kiểm tra đối tượng ngoài `Order`, rồi tách các component. Component `buyer` phải match **record pattern `Customer(...)`**; tiếp theo `address` phải match **record pattern `Address(...)`**. Nếu `buyer` hoặc `address` bằng `null`, record pattern tương ứng không match.

**Điểm đặc biệt của Java 21:** type pattern lồng trực tiếp trong component record có thể **null-matching** nếu nó *unconditional* đối với kiểu khai báo của component đó. Vì `Address.city` được khai báo `String`, pattern `String city` là unconditional cho kiểu `String`, và có thể bind **`null`**. Vì vậy, **`Address(String city, String zip)` không tự bảo đảm `city` hoặc `zip` khác `null`**.

Đây không phải một suy đoán từ cú pháp: Java Language Specification SE 21 §14.30.1/§14.30.2 định nghĩa type pattern *null-matching*. Test thực tế bên dưới sẽ chứng minh điều đó.

### Hai câu dễ nhầm

- `null instanceof String s` là `false`: ở **top-level**, type pattern không match `null`.
- `new Address(null, "10000")` có thể match `Address(String city, String zip)`: `String city` nằm **trực tiếp trong record pattern** của component đã khai báo kiểu `String`, nên bind `city == null`.

Ngược lại, nếu component khai báo kiểu `Object`, pattern `String s` **không unconditional** cho `Object`, nên `record Narrow(Object payload) {}` với `Narrow(String s)` **không match `Narrow(null)`**. Cần test cả hai trường hợp; không dán nhãn tất cả nested `String` pattern là luôn từ chối hoặc luôn chấp nhận `null`.

## 3. Thiết kế test theo từng cấp cấu trúc

Ví dụ miền dữ liệu:

```java
record Address(String city, String zip) {}
record Customer(String id, Address address) {}
record Order(String number, Customer buyer, List<String> items) {}
```

Với input đầu vào thuộc kiểu `Object`, hãy phân loại các nhóm:

| Nhóm test | Đầu vào mẫu | Điều cần xác minh |
| --- | --- | --- |
| **Match đầy đủ** | `Order("O1", Customer("C1", Address("Hanoi","10000")), List.of("book"))` | Binds đúng ID, city, zip; guard đạt; nhánh ready |
| **Record ngoài sai kiểu** | `"hello"` | Không match `Order(...)`; nhánh fallback |
| **Selector null** | `null` | Không match record pattern; xử lý `case null` |
| **Buyer null** | `Order("O", null, items)` | Nested `Customer(...)` không match |
| **Address null** | `Order("O", Customer("C",null), items)` | Nested `Address(...)` không match |
| **ID component null** | `Customer(null, Address(...))` | `String id` có thể bind null; guard phải kiểm tra |
| **City component null** | `Address(null,"10000")` | `String city` có thể bind null; không dereference ngay |
| **Zip component null** | `Address("Hue",null)` | Guard phải chặn null trước `matches(...)` |
| **String blank** | `city = " "` | Pattern vẫn match; nghiệp vụ guard từ chối |
| **Zip sai định dạng** | `zip = "bad"` | Pattern match, guard sai |
| **Items rỗng** | `List.of()` | Pattern match; guard sai nếu yêu cầu có item |
| **Items null** | `items = null` | `var items` bind null; guard phải chặn |
| **Order number null** | `number = null` | `var number` bind null; guard phải chặn |
| **Đồng thời nhiều lỗi** | `id=null` và `address=null` | Chọn nhánh theo thứ tự pattern; không NPE |
| **Accessor bất thường** | Accessor tự tăng biến đếm hoặc ném exception | Đo lường side effect và loại exception |

Ma trận trên chưa thay thế yêu cầu nghiệp vụ; với API thật, thêm các tổ hợp kiểu con/generic, validation khác, collection mutable và hành vi cạnh tranh nếu chúng có ý nghĩa.

**Mẹo:** Mỗi test nên có tên diễn đạt một giả thuyết: `nullAddressFallsBack`, `nullCityIsBoundThenRejectedByGuard` hoặc `guardIsNotCalledIfNestedRecordFails`. Tên như `test1` làm giảm giá trị chẩn đoán khi test đỏ.

## 4. Null-matching: trường hợp bắt buộc kiểm thử kỹ

### 4.1. Record pattern không match selector hoặc nested record bằng null

```java
record Address(String city, String zip) {}
record Customer(String id, Address address) {}

Object absent = null;
boolean top = absent instanceof Customer(var id, var address);
// top == false

Object missingAddress = new Customer("C1", null);
boolean nested = missingAddress instanceof Customer(
        var id, Address(var city, var zip));
// nested == false: Address record pattern không match null
```

Hai đoạn được minh họa trong phương thức hoặc khối hợp lệ; biến `id` ở hai biểu thức khác nhau phải đặt trong scope không xung đột nếu ghép lại thành một file. Kết luận là **record pattern không match `null`**, cả ở top-level lẫn khi lồng trong record khác.

### 4.2. Type pattern trong component có thể bind null

```java
record Address(String city, String zip) {}

Object value = new Address(null, "10000");
if (value instanceof Address(String city, String zip)) {
    System.out.println(city == null); // true trong Java 21
}
```

Lý do: component `city` đã có kiểu khai báo `String`; `String city` là type pattern unconditional cho kiểu đó, nên ở vị trí component nó là *null-matching*. **Không viết `city.isBlank()` trước khi kiểm tra `city != null`**.

So với component có kiểu `Object`:

```java
record Narrow(Object payload) {}

boolean a = new Narrow(null) instanceof Narrow(String text);    // false
boolean b = new Narrow("hello") instanceof Narrow(String text); // true
boolean c = new Narrow(42) instanceof Narrow(String text);      // false
```

Ở đây `String text` **không unconditional** cho `Object`, nên `null` không match và một `Integer` cũng không match. Khi copy các dòng vào cùng một scope, cần đổi tên biến pattern hoặc tách chúng thành các statement/method độc lập theo quy tắc scope.

### 4.3. `var` không tự kiểm tra khác null

```java
record Customer(String name, Address address) {}

if (obj instanceof Customer(var name, var address)) {
    // name và address có thể null.
    // Kiểm tra null trước khi dereference.
}
```

Với biến `var`, compiler suy ra kiểu từ component. Nếu component là reference type, giá trị `null` vẫn có thể được bind. Pattern không phải validator nghiệp vụ.

**Checklist null tối thiểu:** `null` ở selector; `null` ở mỗi cấp record trung gian; `null` ở từng component reference; `null` trong collection nếu domain cho phép; một trường hợp component khai báo `String` với nested `String s` và một trường hợp khai báo `Object` với nested `String s`.

## 5. Pattern thành công khác guard thành công

Xét một phương thức phân loại, tên thuộc nghiệp vụ đơn hàng:

```java
static boolean valid(
        String number, String id, String city,
        String zip, List<String> items) {
    return number != null && !number.isBlank()
            && id != null && !id.isBlank()
            && city != null && !city.isBlank()
            && zip != null && zip.matches("[0-9]{5}")
            && items != null && !items.isEmpty();
}
```

Đây là **predicate nghiệp vụ**, không phải bản thân record pattern. Nó kiểm tra dữ liệu đã bind và ngăn `NullPointerException` bằng short-circuit `&&`.

```java
static String classify(Object input) {
    return switch (input) {
        case Order(var number,
                   Customer(String id, Address(String city, String zip)),
                   var items)
                when valid(number, id, city, zip, items) ->
                "ready:" + id + ":" + city + ":" + items.size();

        case Order(var number,
                   Customer(String id, Address(String city, String zip)),
                   var items) ->
                "invalid-fields";

        case Order(var number, Customer(var id, var address), var items) ->
                "missing-address";

        case Order(var number, var buyer, var items) ->
                "missing-customer";

        case null -> "null-order";
        default -> "not-order";
    };
}
```

Đoạn này chạy khi các record và `java.util.List` ở trên đã được khai báo. Các nhánh được xếp từ **hẹp đến rộng**:

1. Match ba record `Order → Customer → Address`, rồi guard `valid(...)` phải đúng → `ready`.
2. Match cùng chuỗi record nhưng guard trước sai → `invalid-fields`.
3. Vẫn có `Customer`, nhưng `Address(...)` không match, chẳng hạn address null → `missing-address`. Tên trạng thái ở đây là cách phân loại của ví dụ; nếu hệ thống thật có kiểu địa chỉ khác, cần phân biệt cụ thể.
4. Có `Order` nhưng `Customer(...)` không match, chẳng hạn buyer null → `missing-customer`.
5. `null` và object không phải `Order` có fallback riêng.

**Điểm kiểm thử:** `id=null`, `city=null` hoặc `zip=null` vẫn có thể match **nhánh record thứ nhất**, sau đó `valid(...)` trả `false` và rơi xuống nhánh `invalid-fields`. Nhưng `address=null` không match nested `Address(...)`, nên rơi xuống nhánh `missing-address`.

Nếu thay đổi nhãn fallback, thay `String id` thành `var id` hoặc đổi thứ tự case, hãy kiểm tra lại ma trận; đó có thể là thay đổi hành vi.

## 6. Đo guard có được đánh giá đúng lúc không

Một guard chỉ chạy **sau khi pattern của chính case đó đã match**. Để test thứ tự này, có thể thêm biến đếm trong fixture:

```java
static int validationCalls;

static boolean valid(String number, String id, String city,
                     String zip, List<String> items) {
    validationCalls++;
    return number != null && !number.isBlank()
            && id != null && !id.isBlank()
            && city != null && !city.isBlank()
            && zip != null && zip.matches("[0-9]{5}")
            && items != null && !items.isEmpty();
}
```

Nếu thử 12 input của chương trình cuối bài, guard được gọi **8 lần**: các trường hợp có đủ ba tầng record `Order/Customer/Address`, kể cả khi component String null hoặc không hợp lệ. Các ca `address=null`, `buyer=null`, selector `null`, object khác kiểu **không gọi guard** đó.

**Không đánh đồng:** Guard trả `false` khác pattern không match, dù cùng có thể dẫn tới nhánh sau. Biến đếm giúp kiểm tra điều đó. Nhưng bộ đếm ở đây dùng cho **test fixture tuần tự**, không phải cách nên thiết kế predicate production: predicate nên thuần và không gây side effect nếu có thể.

### 6.1. Chứng minh short-circuit an toàn

Với `instanceof` kết hợp nested pattern:

```java
static boolean hasKnownCity(Object input) {
    return input instanceof Order(
            var number,
            Customer(String id, Address(String city, String zip)),
            var items)
            && city != null
            && !city.isBlank();
}
```

Chỉ khi `Order/Customer/Address` match mới đánh giá `city != null`. Nếu `city==null`, `&&` bỏ qua lời gọi `isBlank()`. Phương thức trả `false` thay vì NPE.

Cẩn trọng với kiểu viết chỉ có `&& !city.isBlank()`: **chưa an toàn** khi nested `String city` là null-matching. Kiểm thử null thành phần bắt được lỗi này.

## 7. Test biến pattern bind đúng dữ liệu

Một lời gọi `instanceof`/`switch` thành công không đủ; test cần xác minh dữ liệu được bind đúng thứ tự và đúng nguồn. Ví dụ:

```java
case Order(var number,
           Customer(String id, Address(String city, String zip)),
           var items)
        when valid(number, id, city, zip, items) ->
        "ready:" + id + ":" + city + ":" + items.size();
```

Với dữ liệu `new Order("O1", new Customer("C1", new Address("Hanoi","10000")), List.of("book","pen"))`, kết quả chính xác là `"ready:C1:Hanoi:2"`.

Test nên phân biệt component bằng các giá trị **khác nhau**, ví dụ `number="O1"`, `id="C1"`, `city="Hanoi"`, `zip="10000"`. Nếu tất cả đều dùng `"test"`, việc tráo component có thể không làm test thất bại.

Một checklist đơn giản:

- Test thứ tự component đúng theo record declaration.
- Test việc lấy component lồng nhau qua nhiều cấp.
- Test giá trị primitive như `int`, `boolean` và số âm/zero khi record có chúng.
- Test các component reference `null`.
- Test giá trị có nhiều khoảng trắng, Unicode hoặc định dạng bất thường khi nghiệp vụ xử lý chúng.
- Test collection rỗng/non-null/null, và nội dung của nó nếu guard kiểm tra phần tử.

Nếu component là mảng hay collection mutable, pattern **không tự copy** dữ liệu. Đối với code quan sát/mutate collection, test aliasing và trạng thái sau lời gọi nếu hợp đồng yêu cầu.

## 8. Test lỗi và side effect của record accessor

Record patterns sử dụng **accessor** để lấy giá trị component. Record mặc định có accessor đơn giản, nhưng tác giả record có thể khai báo accessor tường minh, ví dụ đếm số lần gọi hoặc ném exception.

### 8.1. Test accessor có bị gọi thêm không

```java
record Metered(String value) {
    static int reads;
    @Override public String value() {
        reads++;
        return value;
    }
}
record Container(Metered payload) {}

static boolean typeOnly(Object input) {
    return input instanceof Container;
}

static boolean deconstruct(Object input) {
    return input instanceof Container(Metered(String value));
}
```

Với `Container(new Metered("ok"))`:

- `typeOnly(...)` chỉ kiểm tra kiểu; **không cần gọi** `Metered.value()`, nên `reads` không tăng.
- `deconstruct(...)` đọc component sâu hơn; `Metered.value()` được gọi, nên `reads` tăng lên 1.
- Với `Container(new Metered(null))`, nested `String value` **vẫn null-matching** vì component được khai báo `String`; `deconstruct(...)` trả `true` và accessor chạy thêm một lần.

Một test chỉ so `boolean` có thể bỏ sót chi phí/side effect từ accessor. Khi cần chứng minh tương đương hành vi sau refactor, kiểm tra số lần gọi và ngoại lệ.

### 8.2. Accessor ném exception: test loại exception thật

```java
record Unstable(String value) {
    @Override public String value() {
        throw new IllegalStateException("accessor failure");
    }
}
record Wrapper(Unstable inner) {}
```

Khi match `Wrapper(Unstable(String value))`, Java gọi accessor của record bên trong. Theo JLS Java 21 §14.30.2, một ngoại lệ do invocation của accessor trong quá trình deconstruction được bọc trong **`MatchException`** với ngoại lệ gốc ở `getCause()`.

```java
try {
    Object object = new Wrapper(new Unstable("x"));
    boolean matched = object instanceof Wrapper(Unstable(String value));
    throw new AssertionError("Unexpected result: " + matched);
} catch (MatchException ex) {
    System.out.println(ex.getCause().getClass().getSimpleName());
    // IllegalStateException
}
```

Đoạn này được trích từ bối cảnh thử nghiệm; `Unstable` và `Wrapper` đã khai báo. Ở trường hợp này, lời gọi `Unstable.value()` ném `IllegalStateException`; quá trình pattern matching ném `MatchException` có cause là lỗi đó. Không nên giả định nested pattern luôn chỉ trả `false` khi accessor thất bại.

**Test cần quan sát exception, không bỏ qua bằng catch rộng rồi trả `false`.** Nếu cấu trúc record lấy giá trị bằng I/O hoặc trạng thái mutable, nguy cơ còn liên quan đến ổn định và tính nhất quán; với cấu trúc dữ liệu thuần, tác dụng phụ ít hơn nhưng vẫn cần hiểu semantics.

## 9. Negative compiler tests: lỗi phát hiện trước runtime

Một số trường hợp không thể kiểm tra bằng unit test chạy bình thường vì **Java từ chối biên dịch**. Cần negative compilation tests riêng, hoặc dựa vào bước `javac --release 21` của CI và kiểm tra diagnostics.

### 9.1. Nhánh record rộng che nhánh nested hẹp

```java
record Point(int x, int y) {}
record Holder(Point value) {}

// CỐ Ý SAI trong switch:
return switch (input) {
    case Holder(var p) -> "wide";
    case Holder(Point(var x, var y)) -> "narrow"; // dominated
    default -> "other";
};
```

`Holder(var p)` đứng trước bao phủ mọi `Holder` non-null, kể cả những đối tượng chứa `Point` hợp lệ. Case nested phía sau không thể được chọn; compiler báo `this case label is dominated by a preceding case label`.

**Sửa:** đặt `Holder(Point(var x,var y))` trước `Holder(var p)`.

### 9.2. Sai số lượng component

```java
record Point(int x, int y) {}

// CỐ Ý SAI:
boolean match = input instanceof Point(var x);
```

Record `Point` có **hai** component, nhưng pattern chỉ có một. Java 21 báo lỗi tương đương `incorrect number of nested patterns`, vì không thể tự bỏ qua component thứ hai bằng cách thiếu vị trí.

**Sửa:** viết `Point(var x, var y)`, hoặc nếu chỉ cần x, vẫn phải có component pattern thứ hai như `Point(var x, var ignoredY)`. Đừng nhầm việc không dùng component với việc không khai báo vị trí.

### 9.3. Trùng tên biến bind

```java
// CỐ Ý SAI:
boolean match = input instanceof Point(var x, var x);
```

Hai component pattern cùng khai báo biến `x` trong cùng record pattern. Java 21 báo lỗi tương đương `illegal attempt to redefine an existing match binding`.

**Sửa:** dùng tên khác nhau, chẳng hạn `Point(var x, var y)`.

### 9.4. Dùng biến pattern khi chưa chắc match

```java
// CỐ Ý SAI: nếu pattern không match, city không được bind.
return input instanceof Order(var no,
        Customer(var id, Address(var city, var zip)),
        var items)
        || city.isBlank();
```

Vế phải `||` chỉ chạy khi phép match ở vế trái là `false`; lúc đó không thể dùng `city`. Nếu muốn yêu cầu match và city nonblank, dùng `&& city != null && !city.isBlank()`.

**Lưu ý:** Ba lỗi đầu có thể được phát hiện trực tiếp bằng `javac` trên Java 21; ví dụ này minh họa quy tắc flow scoping của pattern variables (JLS §6.3) và không được đưa vào source file runnable.

## 10. Chương trình Java 21 hoàn chỉnh để kiểm thử

Tạo tệp **`NestedRecordPatternTestDemo.java`** với nội dung sau. Mã này chỉ dùng Java standard library, có **12 test phân loại theo bảng**, các phép đo guard/accessor, ba ca narrow type pattern và test ngoại lệ của accessor. Nếu một kỳ vọng bị sai, chương trình ném `AssertionError`; không cần bật `-ea`.

```java
import java.util.List;

public class NestedRecordPatternTestDemo {
    record Address(String city, String zip) {}
    record Customer(String id, Address address) {}
    record Order(String number, Customer buyer, List<String> items) {}
    record Container(Metered payload) {}
    record Metered(String value) {
        static int reads;
        @Override public String value() {
            reads++;
            return value;
        }
    }
    record Narrow(Object payload) {}
    record Unstable(String value) {
        @Override public String value() {
            throw new IllegalStateException("accessor failure");
        }
    }
    record Wrapper(Unstable inner) {}

    static int validationCalls;

    static boolean valid(String number, String id, String city,
                         String zip, List<String> items) {
        validationCalls++;
        return number != null && !number.isBlank()
                && id != null && !id.isBlank()
                && city != null && !city.isBlank()
                && zip != null && zip.matches("[0-9]{5}")
                && items != null && !items.isEmpty();
    }

    static String classify(Object input) {
        return switch (input) {
            case Order(var number,
                       Customer(String id, Address(String city, String zip)),
                       var items)
                    when valid(number, id, city, zip, items) ->
                    "ready:" + id + ":" + city + ":" + items.size();
            case Order(var number,
                       Customer(String id, Address(String city, String zip)),
                       var items) ->
                    "invalid-fields";
            case Order(var number, Customer(var id, var address), var items) ->
                    "missing-address";
            case Order(var number, var buyer, var items) ->
                    "missing-customer";
            case null -> "null-order";
            default -> "not-order";
        };
    }

    static boolean hasKnownCity(Object input) {
        return input instanceof Order(var number,
                Customer(String id, Address(String city, String zip)),
                var items) && city != null && !city.isBlank();
    }

    static boolean typeOnly(Object input) {
        return input instanceof Container;
    }

    static boolean deconstruct(Object input) {
        return input instanceof Container(Metered(String value));
    }

    static boolean narrow(Object input) {
        return input instanceof Narrow(String text);
    }

    static void check(String name, Object input, String expected) {
        String actual = classify(input);
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + ": expected=" + expected + ", actual=" + actual);
        }
        System.out.println(name + " -> " + actual);
    }

    public static void main(String[] args) {
        check("valid", new Order("O1", new Customer("C1",
                new Address("Hanoi", "10000")), List.of("book", "pen")),
                "ready:C1:Hanoi:2");
        check("blank-city", new Order("O2", new Customer("C2",
                new Address(" ", "10000")), List.of("book")), "invalid-fields");
        check("bad-zip", new Order("O3", new Customer("C3",
                new Address("Hue", "bad")), List.of("book")), "invalid-fields");
        check("empty-items", new Order("O4", new Customer("C4",
                new Address("Hue", "50000")), List.of()), "invalid-fields");
        check("null-number", new Order(null, new Customer("C5",
                new Address("Hue", "50000")), List.of("book")), "invalid-fields");
        check("null-id", new Order("O6", new Customer(null,
                new Address("Hue", "50000")), List.of("book")), "invalid-fields");
        check("null-city", new Order("O7", new Customer("C7",
                new Address(null, "50000")), List.of("book")), "invalid-fields");
        check("null-zip", new Order("O8", new Customer("C8",
                new Address("Hue", null)), List.of("book")), "invalid-fields");
        check("null-address", new Order("O9", new Customer("C9", null),
                List.of("book")), "missing-address");
        check("null-buyer", new Order("O10", null,
                List.of("book")), "missing-customer");
        check("null-selector", null, "null-order");
        check("other-type", "hello", "not-order");

        System.out.println("validation calls=" + validationCalls);
        Object known = new Order("O11", new Customer("C11",
                new Address("Hue", "50000")), List.of("book"));
        System.out.println("has city=" + hasKnownCity(known));
        System.out.println("null nested city=" +
                hasKnownCity(new Order("O12", new Customer("C12",
                        new Address(null, "50000")), List.of("book"))));

        Container good = new Container(new Metered("ok"));
        System.out.println("type only=" + typeOnly(good)
                + ", reads=" + Metered.reads);
        System.out.println("nested=" + deconstruct(good)
                + ", reads=" + Metered.reads);
        Container withNull = new Container(new Metered(null));
        System.out.println("nested null=" + deconstruct(withNull)
                + ", reads=" + Metered.reads);
        System.out.println("narrow null=" + narrow(new Narrow(null)));
        System.out.println("narrow text=" + narrow(new Narrow("hello")));
        System.out.println("narrow integer=" + narrow(new Narrow(42)));

        try {
            Object object = new Wrapper(new Unstable("x"));
            boolean matched =
                    object instanceof Wrapper(Unstable(String value));
            throw new AssertionError("Unexpected result: " + matched);
        } catch (MatchException ex) {
            System.out.println("accessor error="
                    + ex.getClass().getSimpleName()
                    + ", cause=" + ex.getCause().getClass().getSimpleName());
        }
        System.out.println("TESTS PASSED");
    }
}
```

**Biên dịch và chạy:** cần JDK 21 trở lên; trong thư mục chứa source:

```bash
javac --release 21 NestedRecordPatternTestDemo.java
java NestedRecordPatternTestDemo
```

**Kết quả thực tế (stdout):**

```text
valid -> ready:C1:Hanoi:2
blank-city -> invalid-fields
bad-zip -> invalid-fields
empty-items -> invalid-fields
null-number -> invalid-fields
null-id -> invalid-fields
null-city -> invalid-fields
null-zip -> invalid-fields
null-address -> missing-address
null-buyer -> missing-customer
null-selector -> null-order
other-type -> not-order
validation calls=8
has city=true
null nested city=false
type only=true, reads=0
nested=true, reads=1
nested null=true, reads=2
narrow null=false
narrow text=true
narrow integer=false
accessor error=MatchException, cause=IllegalStateException
TESTS PASSED
```

### 10.1. Đọc các kết quả cốt lõi

- **12 ca đầu** dùng hàm `check(...)`: nếu expected/actual khác nhau, chương trình ném `AssertionError`. Nên dòng `TESTS PASSED` chỉ xuất hiện khi toàn bộ kiểm tra trong chương trình kết thúc bình thường.
- `null-id`, `null-city`, `null-zip` đều là `invalid-fields`, **không phải** `missing-address`. Điều này xác nhận nested `String` type patterns có thể null-matching cho component cùng kiểu `String`.
- `null-address` và `null-buyer` đi vào các nhánh khác do **nested record patterns không match null**.
- `validation calls=8`: guard được chạy với các đối tượng có đủ tầng record, kể cả khi một `String` component bằng null; không chạy khi record nested thất bại.
- `has city=true` và `null nested city=false` cho thấy kiểm tra `city != null && !city.isBlank()` là cần thiết.
- `type only=true, reads=0` khác `nested=true, reads=1`: deconstruction gọi accessor thay vì chỉ kiểm tra runtime type.
- `nested null=true, reads=2` là minh họa nữa về null-matching type pattern lồng trong record.
- `Narrow(null)` không match `Narrow(String text)` vì component có kiểu khai báo `Object`, trong khi `Narrow("hello")` match và `Narrow(42)` không match.
- `MatchException` bọc `IllegalStateException` từ accessor; lỗi không tự chuyển thành `false`.
- Cuối cùng, `TESTS PASSED` chứng minh **các kỳ vọng đã kiểm tra**, không chứng minh mọi input ngoài miền test chắc chắn đúng.

### 10.2. Vì sao dùng `throw new AssertionError(...)`?

Trong Java, câu lệnh `assert condition;` chỉ hoạt động khi bật assertions, thường bằng cờ `java -ea ...`. Trong demo, kiểm tra expected/actual bằng điều kiện và ném `AssertionError` trực tiếp, nên **luôn chạy** dù JVM có hoặc không có `-ea`. Nếu dự án dùng JUnit, dùng `assertEquals(...)`, `assertThrows(...)` và test runner phù hợp thay vì tự in log.

## 11. Tích hợp với JUnit và bảng dữ liệu kiểm thử

Khi dự án đã có JUnit Jupiter (JUnit 5), có thể chuyển hàm kiểm thử thành parameterized test. Đoạn sau là **minh họa phụ thuộc JUnit và các record/hàm `classify` đã định nghĩa trong mã production**, không phải chương trình JDK độc lập.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.params.provider.Arguments;
import java.util.List;
import java.util.stream.Stream;

class OrderPatternTest {
    static Stream<Arguments> cases() {
        return Stream.of(
            Arguments.of(
                new Order("O1",
                    new Customer("C1", new Address("Hanoi", "10000")),
                    List.of("book")),
                "ready:C1:Hanoi:1"),
            Arguments.of(
                new Order("O2",
                    new Customer("C2", new Address(null, "10000")),
                    List.of("book")),
                "invalid-fields"),
            Arguments.of(
                new Order("O3", new Customer("C3", null), List.of("book")),
                "missing-address"),
            Arguments.of(null, "null-order")
        );
    }

    @ParameterizedTest
    @MethodSource("cases")
    void classifiesNestedRecords(Object input, String expected) {
        assertEquals(expected, classify(input));
    }
}
```

**Ghi chú sử dụng:** Cần khai báo các class `Order`, `Customer`, `Address` và truy cập `classify` tương ứng, cấu hình dependency `junit-jupiter-params`/test runner của dự án. Nếu các record được khai báo nested trong class production, hãy dùng tên đủ điều kiện hoặc import hợp lệ. Với một class test riêng, phiên bản `classify` phải được gọi qua lớp chứa nó nếu không phải static import hợp lệ.

**Ưu điểm:** Một bộ cases tách riêng đầu vào/kỳ vọng; khi thêm null hoặc boundary case chỉ cần thêm một dòng. **Hạn chế:** Nếu chỉ test giá trị trả về, vẫn cần test exception và side effects riêng.

### 11.1. Test accessor exception bằng JUnit

Trong một dự án dùng JUnit, có thể kiểm tra ngoại lệ bọc:

```java
MatchException ex = assertThrows(MatchException.class, () -> {
    Object object = new Wrapper(new Unstable("x"));
    boolean matched =
            object instanceof Wrapper(Unstable(String value));
});
assertInstanceOf(IllegalStateException.class, ex.getCause());
```

Đây là **mảnh code minh họa**, giả định đã import static `assertThrows`, `assertInstanceOf` và có các record đúng như ví dụ đầy đủ. Không dùng một catch `RuntimeException` rộng rồi coi mọi lỗi là đạt; phải xác minh **loại exception chính xác và cause** theo hợp đồng.

## 12. Kiểm thử theo thuộc tính và biến đổi (property/metamorphic testing)

Với nhiều tầng record, bảng test thủ công dễ bỏ sót tổ hợp. Có thể tăng độ tin cậy bằng **property-based testing** hoặc các bất biến định nghĩa được từ domain.

Một số bất biến có ý nghĩa:

- Nếu `buyer == null` và selector vẫn là `Order`, kết quả của ví dụ phải là `"missing-customer"`, bất kể `number` hay `items`.
- Nếu `buyer != null` nhưng `address == null`, kết quả là `"missing-address"`.
- Nếu đủ tầng record và `city == null`, `valid(...)` phải trả `false` mà không NPE.
- Nếu một `Order` có đầy đủ dữ liệu và đang ready, đổi `zip` từ năm chữ số thành `"bad"` phải làm nó không còn ready.
- Nếu chỉ thay đổi giá trị `items` từ list có phần tử thành list rỗng, guard nghiệp vụ ví dụ chuyển từ true sang false.
- Với `Narrow(Object payload)`, giá trị `null` không match nested `String text`, còn một `String` non-null match.

Nếu dùng generator, nên cố định random seed khi tái hiện lỗi, thu nhỏ input thất bại thành một case cụ thể và đưa regression case đó vào suite. Không tạo dữ liệu random hoàn toàn rồi chỉ kiểm tra "không có exception" — pattern matching có thể cho sai nhánh dù không ném lỗi.

### 12.1. Metamorphic tests giúp xác định tác động của một thay đổi

Ví dụ từ một đơn hàng `ready`:
1. Đổi `city` thành chuỗi toàn khoảng trắng → expected `invalid-fields`.
2. Đổi `address` thành `null` → expected `missing-address`.
3. Đổi `buyer` thành `null` → expected `missing-customer`.
4. Đổi selector thành `null` → expected `null-order`.

Các biến đổi này kiểm tra **sự khác nhau giữa guard thất bại và nested pattern thất bại**; đây thường là chỗ bug ẩn khi refactor từ `if/instanceof/cast` sang nested record pattern.

## 13. Coverage, mutation testing và kiểm soát hồi quy

**Branch coverage** trong `switch` rất hữu ích, nhưng không đủ nếu mỗi nhánh chỉ được test bằng một case đơn giản. Một bài kiểm thử nested record pattern tốt cần:

1. **Outer pattern success/failure:** đúng `Order`, khác kiểu, selector `null`.
2. **Từng cấp record:** `buyer=null` và `address=null`.
3. **Từng component reference:** non-null, null, blank/empty khi có ý nghĩa.
4. **Guard:** true/false; xác nhận guard không bị gọi khi pattern chưa match.
5. **Thứ tự case:** nested cụ thể trước record tổng quát; nếu đổi, compiler phải phát hiện dominance hoặc test phải phát hiện chọn nhánh sai.
6. **Accessor:** có/không có side effect, ném exception, và số lần đọc nếu hợp đồng yêu cầu.
7. **Regression:** cùng bộ input trên mã cũ và mã refactor, so kết quả cùng exception quan trọng.
8. **Compile checks:** `javac --release 21` với source thực tế và negative samples riêng khi cần đào tạo công cụ.

**Mutation testing** có thể giúp phát hiện test yếu, ví dụ thử đổi `zip.matches(...)` thành luôn true trong bản thử nghiệm, bỏ `city != null` hoặc đổi vị trí hai nhánh. Một bộ test hữu ích phải phát hiện ít nhất các mutation làm sai quy tắc nghiệp vụ đã xác định. Không áp dụng mutation vào source production hoặc dữ liệu thật mà không có isolation và quy trình review.

### Khi nào cần benchmark?

Record deconstruction gọi accessor và tạo logic match lồng nhau, nhưng **không nên tự suy ra** nó luôn chậm hơn kiểu cast cũ một tỷ lệ cố định. Nếu đoạn code nằm trên hot path, dùng JMH/benchmark phù hợp, đo trên môi trường đại diện và tránh kết luận chỉ từ một lần chạy. Ưu tiên tính đúng đắn, null semantics và exception trước khi tối ưu.

## 14. Checklist review cho nested record pattern tests

- [ ] Xác định rõ JDK 21+ cho record/switch patterns, biên dịch đúng `--release`.
- [ ] Có test *outer selector null* và *wrong type*.
- [ ] Có test từng **nested record bằng null**, không chỉ test một component String bằng null.
- [ ] Có test null-matching của **type pattern unconditional cho kiểu component**; không giả định `String city` loại mọi `null`.
- [ ] Có test nested type pattern **không unconditional** (ví dụ `Object payload` với `String s`).
- [ ] Guard có null checks trước khi dereference; case guard true/false đều được chạy.
- [ ] Có test phát hiện guard bị gọi khi pattern không match hoặc test bằng counter khi cần.
- [ ] Có test thứ tự case giữa nested hẹp và record rộng, không có nhánh bị dominated.
- [ ] Mỗi component bind được kiểm tra bằng giá trị riêng biệt, tránh tráo biến mà test vẫn xanh.
- [ ] Có test với collection `null`, rỗng, non-empty nếu record chứa list.
- [ ] Có test accessor side effect và `MatchException` nếu record type có accessor override.
- [ ] Không coi `AssertionError`/test fail là nhánh fallback bình thường của pattern.
- [ ] Test chạy trong CI trên phiên bản Java mục tiêu và không lẫn ví dụ **cố ý sai** vào source runnable.
- [ ] Kết quả kỳ vọng được xác định từ hợp đồng, không điều chỉnh để "làm xanh" test.

**Tiêu chí hoàn tất:** Có bộ ca dương/âm và biên phản ánh đúng cấu trúc record; hiểu chính xác null semantics; guard và biến bind được kiểm thử; lỗi accessor được xác nhận; các ví dụ build/chạy; sai phạm cú pháp, dominance và arity được compiler phát hiện. Khi các ca đều PASS, chỉ kết luận trong phạm vi đầu vào và hợp đồng đã kiểm thử.

## 15. Sai lầm thường gặp

### Sai lầm 1: Cho rằng `String s` trong mọi nested record đều không match null

Đây là lỗi có thể dẫn tới NPE. Nếu type pattern **unconditional** cho kiểu khai báo của component, Java 21 cho phép nó **null-matching**. Test `Address(null, "10000")` và `Narrow(null)` để thấy hai kết quả khác nhau.

### Sai lầm 2: Test `null` chỉ ở selector ngoài

`Order(null, Customer(...), items)`, `Order("O", null, items)`, `Customer("C", null)` và `Address(null, "10000")` có ý nghĩa khác. Thiếu một cấp null có thể bỏ sót nhánh không match hoặc exception.

### Sai lầm 3: Nhầm pattern không match với guard false

Đơn hàng có `address=null` không match nested `Address(...)`; đơn hàng có `city=" "` match cấu trúc nhưng guard sai. Test phải kỳ vọng nhánh khác nhau.

### Sai lầm 4: Dùng `assert` mà không bật assertions

Khi JVM không có `-ea`, câu lệnh `assert condition;` thường không chạy. Dùng framework hoặc kiểm tra chủ động với `AssertionError` cho demo JDK thuần.

### Sai lầm 5: Cho rằng mọi accessor record là pure

Có thể override accessor, làm side effect hoặc ném exception. Test deconstruction phải xét khả năng `MatchException` và sự khác nhau với type-only check.

### Sai lầm 6: Đặt case rộng trước case lồng hẹp

`case Order(var number, var buyer, var items)` trước `case Order(...Customer(...))` sẽ che nested case phía sau. Compiler Java 21 có phân tích **dominance**; đổi thứ tự để cụ thể trước tổng quát.

### Sai lầm 7: Chỉ kiểm tra output mà bỏ qua bind và side effect

Hai cách triển khai có thể cùng trả `"ready"` nhưng đã đọc accessor khác số lần, đổi thứ tự guard hoặc dùng nhầm component trong log. Dùng dữ liệu phân biệt và kiểm tra trạng thái/ngoại lệ quan trọng.

### Sai lầm 8: Đặt test kỳ vọng theo trực giác về null thay vì JLS

Khi một ca thử bất ngờ ném NPE, phải phân tích xem nested type pattern có match `null` hay không. Đừng "sửa" test bằng cách cho qua NPE nếu quy tắc nghiệp vụ muốn từ chối dữ liệu null an toàn. Áp dụng null check rõ ràng.

## 16. Câu hỏi tự kiểm tra

**1.** Nested record pattern khác type pattern ở điểm nào?  
*Đáp án:* Record pattern yêu cầu record object non-null có kiểu phù hợp rồi match component; type pattern bind một giá trị theo kiểu và có thể null-matching ở vị trí component nếu unconditional cho kiểu khai báo.

**2.** `new Customer("C1", null) instanceof Customer(var id, Address(var city, var zip))` là gì?  
*Đáp án:* `false`, vì `Address(...)` là record pattern và không match component `null`.

**3.** `new Address(null, "10000") instanceof Address(String city, String zip)` có thể trả true không?  
*Đáp án:* Có trong Java 21. `String city` là component type pattern unconditional cho thành phần được khai báo `String`, vì vậy có thể bind null.

**4.** Tại sao `new Narrow(null) instanceof Narrow(String text)` là false nếu `record Narrow(Object payload) {}`?  
*Đáp án:* `String text` không unconditional cho kiểu component `Object`, nên không phải null-matching ở vị trí đó.

**5.** Vì sao phải test `city != null && !city.isBlank()`?  
*Đáp án:* Pattern có thể bind `city==null`; short-circuit bảo đảm không gọi `isBlank()` trên null.

**6.** Guard `when valid(...)` có được gọi khi `address==null` và mẫu yêu cầu `Address(...)` không?  
*Đáp án:* Không, vì nested record pattern thất bại trước khi guard được đánh giá.

**7.** Khi accessor của record ném `IllegalStateException` trong quá trình deconstruction, điều gì có thể xảy ra?  
*Đáp án:* Pattern matching ném `MatchException` với cause là ngoại lệ accessor; không tự trả false.

**8.** Vì sao `case Holder(var p)` trước `case Holder(Point(var x,var y))` bị compiler từ chối?  
*Đáp án:* Pattern rộng bao phủ tất cả trường hợp match của nested pattern hẹp phía sau: dominance.

**9.** Có nên coi kết quả "TESTS PASSED" của một bộ 12 ca là chứng minh toàn bộ API đúng?  
*Đáp án:* Không. Nó chỉ chứng minh các ca được kiểm tra. Cần bổ sung ranh giới và hợp đồng của hệ thống thật.

**10.** Unit test framework có thay thế negative compilation tests không?  
*Đáp án:* Không. Các lỗi như sai arity, duplicate binding và dominated case xảy ra trước runtime; cần compile-time gate và mẫu lỗi tách biệt.

## Tham khảo chính thức

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Java SE 21 JLS §14.30.1 — Kinds of Patterns và null-matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.1)
- [Java SE 21 JLS §14.30.2 — Pattern Matching, accessor exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2)
- [Java SE 21 JLS §14.30.3 — Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3)
- [Java SE 21 JLS §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3)
