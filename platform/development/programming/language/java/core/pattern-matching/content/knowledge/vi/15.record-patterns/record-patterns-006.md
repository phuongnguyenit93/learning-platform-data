# Null record và nested component trong Record Patterns (Java 21)

## Mục tiêu

Sau bài này, bạn có thể phân biệt `null` ở **đối tượng record bên ngoài**, ở **component chứa một record lồng bên trong**, và ở **giá trị của component lá**; dự đoán chính xác khi nào một record pattern khớp; xử lý các trường hợp này bằng `instanceof`, `switch` và `when` mà không dereference nhầm `null`.

**Phiên bản:** Record Patterns (JEP 440) và Pattern Matching for `switch` (JEP 441) là tính năng chính thức từ **Java 21**, không cần `--enable-preview`.

## 1. Ba vị trí có thể chứa null

Xét hai record:

```java
record Address(String city) {}
record Person(String name, Address address) {}
```

Cần tách ba trường hợp:

1. **Root/outer record là `null`:** biến `Person p = null;`, chưa có đối tượng `Person` để phân rã.
2. **Nested record component là `null`:** `new Person("An", null)`; `Person` tồn tại nhưng `address()` trả về `null`.
3. **Component bên trong nested record là `null`:** `new Person("An", new Address(null))`; cả `Person` lẫn `Address` đều tồn tại, riêng `city()` trả về `null`.

`record` là kiểu dữ liệu chứa các component có kiểu được khai báo rõ; **record không tự áp đặt non-null** cho component kiểu tham chiếu. Tính bất biến của record cũng không đồng nghĩa với việc mọi component khác `null`.

## 2. Quy tắc khớp pattern trong Java 21

Một record pattern có dạng `Person(String name, Address(String city))`. Java trước hết kiểm tra đối tượng đầu vào có phải một `Person` **khác `null`** hay không. Nếu có, Java gọi các accessor tương ứng và khớp từng component với pattern ở cùng vị trí. Các record pattern lồng nhau tiếp tục làm như vậy.

Có hai quy tắc dễ nhầm:

- **Bản thân record pattern không bao giờ khớp `null`.** Vì vậy `null instanceof Person(...)` là `false`; và `Address(String city)` không khớp khi `address` là `null`.
- **Type pattern trực tiếp cho một component có thể khớp `null`.** Trong Java 21, nó *null-matching* khi pattern đó *unconditional* đối với kiểu khai báo của component. Chẳng hạn, với component `String name`, các pattern `String name` hoặc `var name` đều nhận được `null` và gán `null` cho biến. Với component `Address address`, `Address address` hoặc `var address` cũng vậy.

Điều này khác với type pattern ở cấp ngoài: `obj instanceof String s` luôn `false` nếu `obj == null`. Cơ chế *null-matching* nói trên áp dụng cho **type pattern trực tiếp trong danh sách component của record pattern**, không tự biến một nested record pattern thành null-matching.

### Khi kiểu khai báo khác kiểu pattern

```java
record Box(Object value) {}

// Giả sử obj là new Box(null):
obj instanceof Box(Object data)  // true, data == null
obj instanceof Box(var data)     // true, data == null
obj instanceof Box(String text)  // false
```

`Object data` và `var data` bao phủ mọi giá trị của component khai báo là `Object`, kể cả `null`. `String text` chỉ khớp một số giá trị của `Object`, nên **không** khớp `null`. Nếu giá trị thực tế là một `String` khác `null`, `Box(String text)` mới khớp.

## 3. Bảng các trường hợp quan trọng

Với `Person`, `Address` và `Box` được khai báo phía trên:

| Giá trị đang kiểm tra | Pattern | Kết quả | Giải thích |
|---|---|---|---|
| `null` | `Person(String n, Address a)` | Không khớp | Record bên ngoài là `null` |
| `new Person("An", null)` | `Person(String n, Address a)` | Khớp; `a == null` | `Address a` là type pattern trực tiếp, unconditional cho `Address` |
| `new Person("An", null)` | `Person(String n, Address(String c))` | Không khớp | Nested record pattern `Address(...)` không nhận `null` |
| `new Person(null, new Address(null))` | `Person(String n, Address(String c))` | Khớp; `n == null` và `c == null` | Hai record tồn tại; hai type pattern `String` trực tiếp khớp `null` |
| `new Box(null)` | `Box(Object x)` | Khớp; `x == null` | `Object x` unconditional đối với `Object` |
| `new Box(null)` | `Box(String s)` | Không khớp | `String s` không unconditional đối với `Object` |

Với nested pattern, **một nhánh không khớp không đồng nghĩa với `NullPointerException`**. `instanceof` trả về `false`, còn `switch` tiếp tục xét các `case` phù hợp. Ngoại lệ có thể phát sinh khi chính mã của bạn dereference biến bằng `null`, hoặc khi accessor có lỗi; hai điều này khác với hành vi khớp `null` của pattern.

## 4. Ví dụ Java 21 chạy độc lập

Tạo tệp **`NullRecordAndNestedDemo.java`**:

```java
public class NullRecordAndNestedDemo {
    record Address(String city) {}
    record Person(String name, Address address) {}
    record Box(Object value) {}

    static String nested(Object value) {
        if (value instanceof Person(String name, Address(String city))) {
            return "MATCH name=" + name + ", city=" + city;
        }
        return "NO MATCH";
    }

    static String status(Object value) {
        return switch (value) {
            case null -> "ROOT NULL";

            // Address phải khác null; city vẫn có thể null.
            case Person(String name, Address(String city)) ->
                    "NESTED city=" + city;

            // Bắt riêng nested record component là null.
            case Person(String name, Address address)
                    when address == null -> "ADDRESS NULL";

            default -> "OTHER TYPE";
        };
    }

    static boolean narrow(Object value) {
        return value instanceof Box(String text);
    }

    static boolean broad(Object value) {
        return value instanceof Box(Object data);
    }

    public static void main(String[] args) {
        System.out.println(nested(null));
        System.out.println(nested(new Person("An", null)));
        System.out.println(nested(new Person(null, new Address(null))));
        System.out.println(status(null));
        System.out.println(status(new Person("An", null)));
        System.out.println(status(new Person("An", new Address(null))));
        System.out.println(narrow(new Box(null)));
        System.out.println(broad(new Box(null)));
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên**:

```bash
javac --release 21 NullRecordAndNestedDemo.java
java NullRecordAndNestedDemo
```

Kết quả chuẩn:

```text
NO MATCH
NO MATCH
MATCH name=null, city=null
ROOT NULL
ADDRESS NULL
NESTED city=null
false
true
```

Diễn giải các dòng đáng chú ý:

- Dòng 1: `nested(null)` thất bại vì root không khớp record pattern.
- Dòng 2: `Person` tồn tại, nhưng component `address` bằng `null` nên `Address(String city)` thất bại.
- Dòng 3: `Address` tồn tại dù `city` bằng `null`; hai pattern `String` bên trong nhận `null`.
- Dòng 4: `switch` gặp selector `null` nên vào `case null`.
- Dòng 5: nhánh có guard `address == null` xử lý nested record bị thiếu.
- Dòng 6: `city` bằng `null` vẫn đi vào nhánh nested record.
- Hai dòng cuối phân biệt type pattern unconditional `Object` với type pattern thu hẹp `String` trên component khai báo `Object`.

## 5. Viết logic an toàn với instanceof

Khi chỉ quan tâm cấu trúc hoàn chỉnh, nested pattern giúp loại trừ `null` ở các **nút record**:

```java
static boolean hasAddressRecord(Object value) {
    return value instanceof Person(var name, Address(var city));
}
```

Hàm trên trả về `false` nếu `value` là `null` hoặc `address` là `null`. Tuy nhiên, nó trả về `true` nếu `city` là `null`. Để yêu cầu `city` có nội dung, cần kiểm tra thêm:

```java
static boolean hasUsableCity(Object value) {
    return value instanceof Person(var name, Address(String city))
            && city != null
            && !city.isBlank();
}
```

Toán tử `&&` đánh giá từ trái sang phải và dừng sớm. Vì vậy `city` chỉ được sử dụng sau khi pattern khớp và phép kiểm tra `city != null` thành công. Biến `city` cũng chỉ nằm trong phạm vi mà trình biên dịch biết pattern đã khớp.

Nếu muốn đọc `address` kể cả khi bằng `null`, dùng pattern trực tiếp `Person(var name, var address)` và xử lý null một cách tường minh:

```java
static String cityOrUnknown(Object value) {
    if (value instanceof Person(var name, var address)) {
        return address == null || address.city() == null
                ? "Unknown"
                : address.city();
    }
    return "Not a Person";
}
```

Đây là các phương thức minh họa, có thể đặt trong lớp chứa hai record `Person`, `Address` đã khai báo ở mục 1. Không cần gọi accessor của nested record trước khi biết component đó khác `null`.

## 6. switch: phân nhánh theo độ sâu của dữ liệu

Trong một `switch` sử dụng record pattern, đặt nhánh **cụ thể hơn trước**, nhánh tổng quát sau. Ví dụ:

```java
static String route(Object input) {
    return switch (input) {
        case null -> "Không có Person";
        case Person(var name, Address(var city))
                when city != null && !city.isBlank() ->
                "Địa chỉ: " + city;
        case Person(var name, Address(var city)) ->
                "Có Address nhưng city trống hoặc null";
        case Person(var name, var address)
                when address == null ->
                "Chưa có Address";
        default -> "Không phải Person";
    };
}
```

Phân biệt ba ý:

1. `case null` chỉ xử lý **selector** `input == null`. Nếu selector bằng `null` mà không có nhãn xử lý `null`, `switch` kiểu này sẽ ném `NullPointerException`; riêng `default` không tự bắt `null`.
2. `case Person(..., Address(...))` yêu cầu nested `Address` khác `null`. Guard `when` tiếp tục kiểm tra `city` sau khi pattern đã khớp.
3. `case Person(var name, var address) when address == null` giữ được reference `null` để xử lý nghiệp vụ thay vì cố phân rã nó.

**Lưu ý dominance:** nếu đặt `case Person(String name, Address address)` (không có guard) **trước** `case Person(String name, Address(String city))`, nhánh nested phía sau bị nhánh tổng quát bao phủ, dẫn đến lỗi biên dịch. Tương tự, đặt một `case` không guard trước `case` cùng pattern có guard sẽ làm nhánh sau không thể tới được.

Không thể viết `case Person(var name, null)` hoặc `case Person(var name, Address(null))` trong Java 21: danh sách thành phần của record pattern chứa **patterns**, không chứa `null` literal như một component pattern. Hãy bind component bằng `var`/kiểu cụ thể rồi kiểm tra `== null` trong `when` hoặc thân nhánh.

## 7. Có cần cho phép null ngay từ đầu?

Pattern matching giúp **đọc** dữ liệu thiếu, nhưng không quyết định domain có chấp nhận dữ liệu thiếu hay không. Nếu yêu cầu `address` phải tồn tại, hãy ràng buộc tại compact constructor:

```java
import java.util.Objects;

record SafePerson(String name, Address address) {
    SafePerson {
        Objects.requireNonNull(address, "address");
    }
}
```

Ví dụ này sử dụng record `Address` đã khai báo. Nó ngăn tạo `SafePerson` với `address == null`, nhưng **không** đảm bảo `name` hoặc `address.city()` khác `null`. Muốn đảm bảo điều đó, cần validate cả các component tương ứng (hoặc quy định rõ nullable trong hợp đồng API).

Khi nhận JSON, dữ liệu database, phản hồi từ dịch vụ ngoài, hoặc đối tượng legacy, đừng mặc định mọi nested record đều có mặt chỉ vì kiểu khai báo là một record.

## 8. Lỗi phổ biến và cách sửa

- **Nhầm `String s` luôn loại null.** Với `record Person(String name, ...)`, `Person(String s, ...)` nhận `name == null` vì type pattern này unconditional đối với `String`. Hãy kiểm tra `s != null` nếu logic cần.
- **Nhầm `Address(String city)` khớp `address == null`.** Đây là **record pattern**, nên không khớp. Dùng `Address address`/`var address` nếu muốn giữ reference có thể null.
- **Nhầm `case null` bắt mọi nested component null.** Nó chỉ bắt selector. Null tại component phải được xử lý bằng guard hoặc kiểm tra trong nhánh.
- **Gọi `city.isBlank()` khi `city == null`.** Pattern khớp không có nghĩa leaf component khác null. Kiểm tra trước khi dereference.
- **Đặt nhánh rộng trước nhánh hẹp trong `switch`.** Trình biên dịch có thể báo dominated case. Đưa nhánh nested/guard cụ thể lên trước.
- **Sao chép cú pháp Java preview sang Java 21 ổn định.** Record patterns và `switch` patterns không cần preview từ Java 21; riêng unnamed pattern `_` ở Java 21 vẫn là tính năng preview. Các ví dụ ở đây cố ý dùng biến có tên.
- **Cho rằng pattern luôn không thể ném exception.** Việc một nested component không khớp `null` thường chỉ làm khớp thất bại. Nhưng accessor được tùy biến và ném exception khi deconstruction sẽ khiến pattern matching ném `MatchException` bao bọc nguyên nhân theo đặc tả Java 21. Exceptions từ guard hoặc thân nhánh vẫn tuân theo hành vi của chính biểu thức đó.

## 9. Câu hỏi tự kiểm tra

Cho:

```java
record Child(String code) {}
record Parent(Child child) {}
Object a = new Parent(null);
Object b = new Parent(new Child(null));
```

1. `a instanceof Parent(Child(String code))` là gì? **`false`**, vì `Child(...)` không khớp component `null`.
2. `a instanceof Parent(Child child)` là gì? **`true`**, với `child == null`, vì component khai báo `Child` và type pattern trực tiếp `Child child` là unconditional.
3. `b instanceof Parent(Child(String code))` là gì? **`true`**, với `code == null`, vì cả hai record đều khác `null` và `String code` null-matching ở component khai báo `String`.
4. Cách viết điều kiện chỉ chấp nhận code có ít nhất một ký tự không phải khoảng trắng? **`b instanceof Parent(Child(String code)) && code != null && !code.isBlank()`**.
5. Nếu `Parent` không bao giờ được phép thiếu `child`, nên ngăn ở đâu? **Compact constructor hoặc bước validate đầu vào**, thay vì chỉ trông chờ vào pattern lúc đọc.

## Ghi nhớ

**Record pattern kiểm tra sự tồn tại và cấu trúc của từng đối tượng record; type pattern trực tiếp kiểm tra giá trị component theo kiểu khai báo.** Vì vậy `Person(..., Address(...))` đòi `Person` và `Address` khác `null`, nhưng các component lá như `String name` hay `String city` vẫn có thể là `null`. Với `switch`, xử lý selector bằng `case null`, xử lý nested record thiếu bằng guard và luôn kiểm tra trước khi gọi phương thức trên một biến có thể `null`.

## Tham khảo chính thức

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JLS Java SE 21, §14.30: Kinds of Patterns và Pattern Matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
