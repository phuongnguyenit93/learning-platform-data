# Thực hành Optional cho chuỗi thao tác có thể thiếu dữ liệu trong Java

## 1. Mục tiêu thực hành

Trong ứng dụng Java, một thao tác tra cứu có thể **không trả về giá trị**: khách hàng không tồn tại, hồ sơ chưa có địa chỉ, một mã không hợp lệ, người quản lý chưa được gán, hoặc kết quả tìm kiếm trống. Nếu cứ nối các lời gọi phương thức thông thường, ta dễ gặp `NullPointerException`:

~~~java
// CỐ Ý NGUY HIỂM khi một bước trung gian có thể trả null.
String city = repository.findUser(id).getProfile()
        .getAddress().getCity().strip();
~~~

Đây là mã minh họa, không phải chương trình độc lập. Bất cứ bước nào trả `null` có thể khiến bước tiếp theo dereference giá trị vắng mặt.

`Optional<T>` trong `java.util` biểu diễn rõ **có một giá trị kiểu `T` hoặc không có giá trị**. Khi sử dụng đúng, một chuỗi bước có thể được diễn đạt như phép biến đổi liên tục, và **nhánh rỗng được lan truyền** mà không dereference `null` ở từng chỗ.

Sau bài này, bạn sẽ biết:

1. Xác định nơi nên tạo `Optional` từ dữ liệu có thể null.
2. Nối các phép biến đổi **`T → U`** bằng `map()`.
3. Nối các phép tra cứu **`T → Optional<U>`** bằng `flatMap()`, tránh `Optional<Optional<T>>`.
4. Dùng `filter()` để loại giá trị không đạt điều kiện.
5. Chọn `orElse()`, `orElseGet()`, `or()`, `orElseThrow()` hoặc `ifPresentOrElse()` theo yêu cầu đầu ra.
6. Test đầy đủ trường hợp có dữ liệu, thiếu ở các tầng, giá trị rỗng, lỗi parse và fallback.
7. Phân biệt **“không có dữ liệu”** với **“dữ liệu có lỗi cần thông báo”**.
8. Tránh `get()` không kiểm tra, side effect ẩn, cách dùng Optional như collection hoặc kiểu trả về không cần thiết.

Bài dùng **Java 17+**. Những chương trình có tên file cụ thể đều chứa `main`, có thể lưu, biên dịch bằng `javac` và chạy bằng `java`. Các snippet khác được ghi rõ là **mã minh họa trong một ngữ cảnh đã khai báo biến/phương thức**, không chạy độc lập.

## 2. Mô hình tư duy: chuỗi thao tác có thể đứt ở bất kỳ tầng nào

Giả sử cần lấy tên thành phố từ một hồ sơ:

~~~text
customerId
   │
   ▼ tìm khách hàng (có thể thiếu)
Customer
   │
   ▼ lấy địa chỉ (có thể thiếu)
Address
   │
   ▼ lấy thành phố (có thể thiếu)
String
   │
   ▼ trim/strip rồi kiểm tra không rỗng
String hợp lệ
   │
   ▼ chuyển thành chữ in hoa
String kết quả
~~~

Nếu bất kỳ tầng nào không có dữ liệu, kết quả cuối nên là `Optional.empty()` thay vì cố tiếp tục gọi phương thức trên `null`. Một pipeline phù hợp:

~~~java
Optional<String> city = Optional.ofNullable(customers.get(id))
        .map(Customer::address)
        .map(Address::city)
        .map(String::strip)
        .filter(name -> !name.isEmpty())
        .map(name -> name.toUpperCase(Locale.ROOT));
~~~

Đây là **mã minh họa**, cần `customers` là một map có giá trị kiểu `Customer`, các record/class `Customer`/`Address` và import `Optional`, `Locale`. Trọng tâm là **thứ tự kiểu dữ liệu** và khả năng dừng khi không có giá trị.

Ở mỗi bước:

- `Optional.ofNullable(customers.get(id))` chuyển giá trị có thể null thành `Optional<Customer>`.
- `map(Customer::address)` từ `Optional<Customer>` sang `Optional<Address>`. Nếu `address()` trả `null`, kết quả được biến thành `Optional.empty()`.
- `map(Address::city)` chuyển địa chỉ thành tên thành phố khi có.
- `map(String::strip)` chuẩn hóa chuỗi.
- `filter(...)` loại kết quả rỗng sau khi chuẩn hóa.
- `map(...toUpperCase...)` chỉ chạy khi tất cả các bước trước có giá trị và filter đạt.
- Cuối cùng, caller có thể chọn fallback, ném exception, hoặc làm một hành động tùy yêu cầu.

**Quan trọng:** Optional không bảo đảm rằng dữ liệu nguồn sẽ không bị người khác sửa đồng thời; nó cũng không tự bắt mọi exception. Nó chỉ mô hình hóa **sự hiện diện/vắng mặt** của một giá trị ở các bước đã được biểu diễn bằng Optional.

## 3. Quy tắc chọn map hay flatMap

Với `Optional<T>`:

~~~java
<U> Optional<U> map(Function<? super T, ? extends U> mapper);

<U> Optional<U> flatMap(
        Function<? super T, ? extends Optional<? extends U>> mapper);
~~~

Đây là chữ ký rút gọn từ Java SE API, không phải mã tự định nghĩa lại `Optional`.

**Hỏi đúng một điều:** phương thức được gọi từ mapper trả kiểu gì?

| Kết quả mapper | API nên dùng | Kiểu sau phép biến đổi |
|---|---|---|
| `U` | `map` | `Optional<U>` |
| `Optional<U>` | `flatMap` | `Optional<U>` |
| `boolean` để giữ/bỏ giá trị | `filter` | `Optional<T>` |
| Muốn thực hiện hành động với giá trị nếu có | `ifPresent` | `void` |
| Muốn chọn một giá trị mặc định kiểu `T` | `orElse`/`orElseGet` | `T` |

Ví dụ:

~~~java
// Giả sử findUser(id) trả Optional<User>.
Optional<String> name = findUser(id).map(User::name);

// Giả sử findAddress(user) trả Optional<Address>.
Optional<Address> address = findUser(id)
        .flatMap(this::findAddress);
~~~

Đây là hai đoạn **minh họa bên trong một class có phương thức và kiểu liên quan**. Dùng `map` với hàm vốn trả `Optional<Address>` sẽ tạo **`Optional<Optional<Address>>`**, không thuận tiện để nối các phép biến đổi tiếp theo.

### 3.1. Cơ chế lan truyền trạng thái rỗng

Với một `Optional.empty()`:

- `map` không gọi mapper và trả Optional rỗng.
- `flatMap` không gọi mapper và trả Optional rỗng.
- `filter` không gọi predicate và giữ trạng thái rỗng.
- `ifPresent` không gọi action.
- `ifPresentOrElse` gọi nhánh `Runnable` dành cho trạng thái rỗng.
- `orElseGet` gọi supplier fallback.

Nhờ đó **không phải viết `if (value != null)` cho từng bước**. Tuy nhiên, nếu một mapper được gọi trên giá trị có mặt rồi ném exception, Optional **không biến exception thành empty**.

### 3.2. Khi mapper trả null

`Optional.map()` sử dụng semantics tương đương `ofNullable` đối với kết quả mapper: nếu mapper trả `null`, kết quả là `Optional.empty()`.

Ngược lại, mapper của `Optional.flatMap()` phải trả **một object `Optional` không null**. Nếu trả `null`, Java ném `NullPointerException`. Hãy trả `Optional.empty()` để diễn đạt việc không tìm thấy.

~~~java
// Đúng cho hàm thông thường có thể trả null:
Optional.of("abc").map(s -> null);        // Optional.empty()

// CỐ Ý SAI về hợp đồng flatMap:
Optional.of("abc").flatMap(s -> null);    // NullPointerException
~~~

Các dòng là minh họa; không nên viết mapper trả null chỉ để điều khiển flow khi đã có cách trả trạng thái rỗng tường minh.

## 4. Bài thực hành 1: tra cứu khách hàng → địa chỉ → thành phố

### 4.1. Yêu cầu

Một kho dữ liệu đơn giản chứa hồ sơ theo ID. Một hồ sơ có thể thiếu địa chỉ; địa chỉ có thể có thành phố trống. Viết một hàm:

~~~java
static Optional<String> findNormalizedCity(
        Map<String, Customer> customers,
        String id)
~~~

Hàm phải trả thành phố đã `strip()` và viết hoa bằng `Locale.ROOT` khi có dữ liệu hợp lệ; nếu thiếu khách hàng, thiếu địa chỉ hoặc thành phố chỉ gồm khoảng trắng, trả `Optional.empty()`.

### 4.2. Chương trình Java 17 hoàn chỉnh

Lưu **`OptionalCityChainDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Map;
import java.util.Optional;

public class OptionalCityChainDemo {
    record Address(String city, String postalCode) {}
    record Customer(String name, Address address) {}

    static Optional<String> findNormalizedCity(
            Map<String, Customer> customers,
            String id) {
        return Optional.ofNullable(customers.get(id))
                .map(Customer::address)
                .map(Address::city)
                .map(String::strip)
                .filter(city -> !city.isEmpty())
                .map(city -> city.toUpperCase(Locale.ROOT));
    }

    public static void main(String[] args) {
        Map<String, Customer> customers = Map.of(
                "c1", new Customer("An",
                        new Address("  Ha Noi  ", "100000")),
                "c2", new Customer("Binh", null),
                "c3", new Customer("Chi",
                        new Address("   ", "200000"))
        );

        System.out.println("c1=" +
                findNormalizedCity(customers, "c1"));
        System.out.println("c2=" +
                findNormalizedCity(customers, "c2"));
        System.out.println("c3=" +
                findNormalizedCity(customers, "c3"));
        System.out.println("unknown=" +
                findNormalizedCity(customers, "missing"));

        String visible = findNormalizedCity(customers, "c2")
                .orElse("CHUA CO DIA CHI");
        System.out.println("visible=" + visible);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac OptionalCityChainDemo.java
java OptionalCityChainDemo
~~~

Stdout:

~~~text
c1=Optional[HA NOI]
c2=Optional.empty
c3=Optional.empty
unknown=Optional.empty
visible=CHUA CO DIA CHI
~~~

### 4.3. Giải thích từng nhánh

**Khách hàng `c1`:**

1. `customers.get("c1")` trả một `Customer`.
2. `Customer::address` trả `Address` có thành phố `"  Ha Noi  "`.
3. `Address::city` trả một `String`.
4. `String::strip` loại khoảng trắng đầu/cuối thành `"Ha Noi"`.
5. `filter` giữ giá trị không rỗng.
6. `toUpperCase(Locale.ROOT)` trả `"HA NOI"`; kết quả là `Optional[HA NOI]`.

**Khách hàng `c2`:** `address()` là `null`, nên `map(Customer::address)` đưa kết quả thành `Optional.empty()`. Các mapper sau **không được gọi**. Không có `NullPointerException` do thiếu địa chỉ.

**Khách hàng `c3`:** địa chỉ tồn tại nhưng thành phố là khoảng trắng. Sau `strip()`, chuỗi trở thành `""`; `filter` loại nó, kết quả rỗng.

**ID `missing`:** `Map.get` trả `null`; `ofNullable` tạo Optional rỗng từ đầu.

Ở cuối, `orElse("CHUA CO DIA CHI")` trả một **chuỗi mặc định** chỉ khi Optional rỗng. Nếu cần biết **vì sao** không có thành phố (khách hàng không tồn tại, thiếu địa chỉ, hay thành phố trống), `Optional.empty()` **không chứa đủ thông tin lỗi**; cần kiểu kết quả chứa nguyên nhân, không nên cố “đọc ngược” nguyên nhân từ empty.

### 4.4. Bài mở rộng

Hãy tự bổ sung một khách hàng có địa chỉ `new Address("  Da Nang ", "550000")` và kiểm tra kết quả là `Optional[DA NANG]`. Thử thêm trường hợp `new Address(null, "...")`: `map(Address::city)` có thể tạo trạng thái rỗng từ `null`. Nếu việc một `Address` có `city == null` là **lỗi dữ liệu**, đừng mặc định coi nó là “không tìm thấy”; hãy bổ sung validation ở ranh giới input.

## 5. Bài thực hành 2: nối hai phép tra cứu trả Optional bằng flatMap

### 5.1. Yêu cầu

Hệ thống có danh sách người dùng và ID người quản lý. `findUser(id)` trả `Optional<User>`. Muốn tra cứu quản lý từ một user, ta cũng có một hàm trả `Optional<User>` vì quản lý có thể không tồn tại.

Dạng hợp đồng:

~~~java
Optional<User> findUser(String id)
Optional<User> findManager(User user)
Optional<String> findManagerId(String employeeId)
~~~

Muốn nối chuỗi `employeeId → user → manager → managerId`, dùng `flatMap` ở bước tìm manager, bởi `findManager` **đã trả Optional**.

### 5.2. Chương trình chạy độc lập

Lưu **`OptionalManagerDemo.java`**:

~~~java
import java.util.Map;
import java.util.Optional;

public class OptionalManagerDemo {
    record User(String id, String managerId) {}

    private final Map<String, User> users;

    OptionalManagerDemo(Map<String, User> users) {
        this.users = users;
    }

    Optional<User> findUser(String id) {
        return Optional.ofNullable(users.get(id));
    }

    Optional<User> findManager(User user) {
        return Optional.ofNullable(user.managerId())
                .flatMap(this::findUser);
    }

    Optional<String> findManagerId(String employeeId) {
        return findUser(employeeId)
                .flatMap(this::findManager)
                .map(User::id);
    }

    public static void main(String[] args) {
        Map<String, User> data = Map.of(
                "u1", new User("u1", "u2"),
                "u2", new User("u2", null),
                "u3", new User("u3", "missing")
        );
        OptionalManagerDemo directory = new OptionalManagerDemo(data);

        System.out.println("u1=" + directory.findManagerId("u1"));
        System.out.println("u2=" + directory.findManagerId("u2"));
        System.out.println("u3=" + directory.findManagerId("u3"));
        System.out.println("absent=" +
                directory.findManagerId("unknown"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac OptionalManagerDemo.java
java OptionalManagerDemo
~~~

Stdout:

~~~text
u1=Optional[u2]
u2=Optional.empty
u3=Optional.empty
absent=Optional.empty
~~~

**Đọc kết quả:**

- `u1` có `managerId="u2"`, và `u2` tồn tại. `flatMap(this::findManager)` nối phép tra cứu thành một Optional, rồi `map(User::id)` lấy mã quản lý.
- `u2` không có ID quản lý, nên `Optional.ofNullable(null)` trả empty.
- `u3` có `managerId="missing"` nhưng không tìm thấy user đó; `findUser` trả empty.
- `unknown` không có user bắt đầu, nên ngay lời gọi `findUser` đầu đã rỗng.

**Điểm cần nhớ:** mã của `findManagerId` không cần có nhiều `if (obj != null)` vì mỗi hàm trả Optional mô hình hóa trường hợp vắng mặt.

### 5.3. Tại sao map không phải lựa chọn phù hợp ở bước tra cứu?

Nếu viết:

~~~java
Optional<Optional<User>> nested =
        directory.findUser("u1").map(directory::findManager);
~~~

ta có **hai tầng Optional**: ngoài là việc có tìm được nhân viên hay không; bên trong là kết quả tra cứu quản lý. Lúc này muốn gọi `User::id` sẽ phải mở tầng Optional bên trong.

Với `flatMap`:

~~~java
Optional<User> flat =
        directory.findUser("u1").flatMap(directory::findManager);
~~~

kết quả là một `Optional<User>`. Đây là khác biệt quan trọng trong thực hành nối những phép tra cứu có khả năng thiếu dữ liệu.

Hai đoạn trên **chỉ là minh họa** cần đặt trong phạm vi có `directory` kiểu `OptionalManagerDemo` và import `Optional`.

## 6. Bài thực hành 3: chuẩn hóa, kiểm tra và parse đầu vào

### 6.1. Yêu cầu

Một tham số từ request có thể:

- Bằng `null`.
- Chứa khoảng trắng hai đầu.
- Là chuỗi rỗng hoặc chỉ chứa khoảng trắng.
- Không phải số nguyên.
- Là số `0` hoặc âm, không hợp lệ theo nghiệp vụ.
- Là số dương nhưng vượt miền `int`.

Cần viết:

~~~java
static Optional<Integer> parsePositiveInt(String raw)
~~~

Trả `Optional.of(n)` nếu `raw` biểu diễn một số nguyên dương hợp lệ; còn lại trả empty. Trong ứng dụng thật, việc mọi lỗi đều bị gom thành empty có thể không đủ để thông báo nguyên nhân; ví dụ này dùng Optional vì mục tiêu là **thực hành chuỗi có thể thiếu**.

### 6.2. Chương trình Java 17 hoàn chỉnh

Lưu **`OptionalParseDemo.java`**:

~~~java
import java.util.Optional;

public class OptionalParseDemo {
    static Optional<Integer> parsePositiveInt(String raw) {
        return Optional.ofNullable(raw)
                .map(String::strip)
                .filter(text -> !text.isEmpty())
                .flatMap(text -> {
                    try {
                        int parsed = Integer.parseInt(text);
                        return parsed > 0
                                ? Optional.of(parsed)
                                : Optional.empty();
                    } catch (NumberFormatException ex) {
                        return Optional.empty();
                    }
                });
    }

    public static void main(String[] args) {
        System.out.println("valid=" + parsePositiveInt(" 12 "));
        System.out.println("zero=" + parsePositiveInt("0"));
        System.out.println("negative=" + parsePositiveInt("-3"));
        System.out.println("text=" + parsePositiveInt("abc"));
        System.out.println("blank=" + parsePositiveInt("  "));
        System.out.println("null=" + parsePositiveInt(null));
        System.out.println("overflow=" +
                parsePositiveInt("999999999999999999999"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac OptionalParseDemo.java
java OptionalParseDemo
~~~

Stdout:

~~~text
valid=Optional[12]
zero=Optional.empty
negative=Optional.empty
text=Optional.empty
blank=Optional.empty
null=Optional.empty
overflow=Optional.empty
~~~

### 6.3. Vì sao đoạn parse dùng flatMap?

`Integer.parseInt(text)` trả `int` hoặc ném `NumberFormatException`. Ta **chủ động** chuyển lỗi parse mà nghiệp vụ này chấp nhận thành `Optional.empty()`, vì vậy lambda chứa `try/catch` và trả `Optional<Integer>` ở cả nhánh thành công lẫn thất bại.

Do lambda đã trả `Optional<Integer>` nên phải dùng `flatMap` để tránh tạo `Optional<Optional<Integer>>`. Với `raw == null` hay chuỗi sau `strip` rỗng, lambda parse hoàn toàn **không chạy**.

**Bảo đảm hiện có:**

- `parsePositiveInt(" 12 ")` → `Optional[12]`.
- `parsePositiveInt("-3")` → empty vì không phải số dương.
- `parsePositiveInt("abc")` → empty do `NumberFormatException`.
- Chuỗi số vượt miền `int` → empty khi parse không thành công.
- Input null → empty ở bước `ofNullable`.

**Điều không được bảo đảm:** caller không biết chính xác nguyên nhân thất bại. Nếu cần trả lỗi cụ thể như `MISSING`, `NOT_INTEGER`, `OUT_OF_RANGE` hoặc `NOT_POSITIVE`, hãy thiết kế kiểu kết quả riêng (ví dụ sealed interface/record/enum) thay vì lạm dụng `Optional.empty()`.

### 6.4. Tránh bắt mọi ngoại lệ

Không nên viết `catch (Exception ex) { return Optional.empty(); }` để che mọi lỗi trong mapper. Nếu có bug bất ngờ, lỗi I/O hoặc lỗi lập trình, biến tất cả thành “vắng dữ liệu” sẽ làm khó debug. Ở ví dụ trên, chỉ **`NumberFormatException`** được xem là thất bại parse có thể dự đoán.

## 7. Khi nào filter hợp với điều kiện nghiệp vụ?

`filter(Predicate<? super T>)` chỉ giữ giá trị nếu predicate trả true:

~~~java
Optional<String> nonBlank = Optional.of("  Java  ")
        .map(String::strip)
        .filter(s -> !s.isBlank());
// Optional[Java]
~~~

Dùng `filter` khi điều kiện không cần **biến đổi** giá trị, chỉ cần **giữ hoặc loại bỏ**. Nếu điều kiện có ý nghĩa lỗi nghiêm trọng mà caller cần biết nguyên nhân, việc filter chuyển thành empty có thể làm mất thông tin.

Các ví dụ minh họa:

~~~java
Optional<Integer> age = Optional.of(20)
        .filter(n -> n >= 18);

Optional<String> validCode = Optional.ofNullable(rawCode)
        .map(String::strip)
        .filter(code -> code.matches("[A-Z0-9]+"));
~~~

Đoạn thứ hai yêu cầu `rawCode` được khai báo ở phạm vi bên ngoài và chính sách mã chỉ cho chữ hoa A–Z, số 0–9. Chuỗi chữ thường sẽ bị loại: đây là quyết định nghiệp vụ, không phải đặc tính của Optional.

**Không thay filter bằng get + if khi có thể diễn đạt trực tiếp**. Nhưng khi điều kiện phức tạp hoặc phải tạo một tập lỗi có cấu trúc, hãy tách một hàm `validate` với result đúng mục đích.

## 8. Chọn cách kết thúc chuỗi Optional

Một Optional có thể được xử lý theo nhiều cách. Hãy xác định **caller cần giá trị, cần tiếp tục giữ Optional, cần lỗi hay cần thực hiện hành động**.

| Nhu cầu | API | Trả gì? | Điểm khác biệt |
|---|---|---|---|
| Có giá trị thì lấy, không có dùng một giá trị định trước | `orElse(T other)` | `T` | Biểu thức đối số `other` được đánh giá trước lời gọi |
| Có giá trị thì lấy, không có mới tính fallback | `orElseGet(Supplier<? extends T>)` | `T` | Supplier được gọi **chỉ khi Optional rỗng** |
| Có giá trị thì dùng, không có trả Optional dự phòng | `or(Supplier<? extends Optional<? extends T>>)` | `Optional<T>` | Giữ kiểu Optional; fallback cần trả Optional không null |
| Có giá trị thì lấy, thiếu thì ném lỗi | `orElseThrow()` hoặc overload supplier | `T` | Không có giá trị trở thành exception |
| Có giá trị thì thực hiện hành động | `ifPresent(Consumer)` | `void` | Rỗng không làm gì |
| Có/rỗng thực hiện hai hành động khác nhau | `ifPresentOrElse(Consumer,Runnable)` | `void` | Nhánh rỗng không nhận giá trị |
| Giữ trạng thái có/rỗng để caller quyết định | Không unwrap | `Optional<T>` | Hợp khi vắng dữ liệu là bình thường |

### 8.1. orElse và orElseGet: khác nhau ở thời điểm tính fallback

Đây là lỗi phổ biến:

~~~java
String result = optional.orElse(expensiveDefault());
~~~

Nếu `expensiveDefault()` là phương thức có chi phí hoặc side effect, Java **đánh giá đối số trước** khi gọi `orElse`, kể cả khi `optional` đã có giá trị. Nếu không muốn tính fallback khi đã có dữ liệu:

~~~java
String result = optional.orElseGet(() -> expensiveDefault());
~~~

Đây là hai đoạn minh họa trong phương thức có `optional` kiểu `Optional<String>` và `expensiveDefault()` trả `String`.

### 8.2. Chương trình Java 17: đo chính xác thời điểm fallback

Lưu **`OptionalFallbackDemo.java`**:

~~~java
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public class OptionalFallbackDemo {
    static String expensiveDefault(AtomicInteger calls) {
        int number = calls.incrementAndGet();
        return "fallback-" + number;
    }

    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();

        Optional<String> ready = Optional.of("ready");
        String eager = ready.orElse(expensiveDefault(calls));
        System.out.println("eager=" + eager);
        System.out.println("afterEager=" + calls.get());

        String lazy = ready.orElseGet(
                () -> expensiveDefault(calls));
        System.out.println("lazy=" + lazy);
        System.out.println("afterLazy=" + calls.get());

        String missing = Optional.<String>empty()
                .orElseGet(() -> expensiveDefault(calls));
        System.out.println("missing=" + missing);
        System.out.println("afterMissing=" + calls.get());

        Optional<String> backup = Optional.<String>empty()
                .or(() -> Optional.of("backup"));
        System.out.println("backup=" + backup);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac OptionalFallbackDemo.java
java OptionalFallbackDemo
~~~

Stdout:

~~~text
eager=ready
afterEager=1
lazy=ready
afterLazy=1
missing=fallback-2
afterMissing=2
backup=Optional[backup]
~~~

**Giải thích:**

1. `orElse(expensiveDefault(calls))` trả `"ready"` nhưng vẫn gọi `expensiveDefault` để tạo đối số, nên bộ đếm tăng lên `1`.
2. `orElseGet(() -> expensiveDefault(calls))` cũng trả `"ready"`, **không gọi** supplier vì Optional đã có giá trị.
3. Với Optional rỗng, `orElseGet` gọi supplier một lần và trả `"fallback-2"`.
4. `or(...)` khác hai API trên: nó trả **một `Optional<String>`**, không trực tiếp trả `String`. Nếu nguồn rỗng, supplier mới được gọi để lấy Optional dự phòng.
5. `AtomicInteger` chỉ dùng để làm bộ đếm minh họa, không có nghĩa mọi fallback phải dùng atomic hoặc thực thi song song.

### 8.3. orElseThrow khi vắng dữ liệu là lỗi

~~~java
User user = findUser(id).orElseThrow(
        () -> new IllegalArgumentException("Unknown user: " + id));
~~~

Đây là mã minh họa trong class có `findUser` trả `Optional<User>`. Khi không có user, supplier tạo exception. Khi có user, exception supplier không được gọi.

Nếu vắng mặt là trạng thái hợp lệ, **không nên** ném exception chỉ để tránh trả `Optional`. API nào phù hợp phụ thuộc hợp đồng nghiệp vụ.

### 8.4. ifPresentOrElse dùng khi cần hành động, không cần giá trị trả về

~~~java
findUser(id).ifPresentOrElse(
        user -> renderUser(user),
        () -> renderNotFound(id)
);
~~~

`Consumer<User>` nhận người dùng khi có; `Runnable` không nhận đối số ở nhánh thiếu. Cả `ifPresent` và `ifPresentOrElse` trả `void`, **không nên dùng** để mong lấy một `String` hay object mới từ biểu thức.

## 9. Optional và việc tạo dữ liệu khi cần bằng Supplier

Chuỗi Optional không đơn thuần là một tập các hàm chống null. Nó còn giúp mô tả **khi nào** một giá trị dự phòng mới cần được tạo.

Giả sử:

~~~java
Optional<Config> config = findConfig(id);

Config chosen = config.orElseGet(() -> loadDefaultConfig());
~~~

Đây là mã minh họa. Nếu `findConfig(id)` có giá trị, `loadDefaultConfig()` không được gọi. Nhưng **bản thân lời gọi `findConfig(id)` đã diễn ra** trước khi `orElseGet`. Supplier chỉ trì hoãn **fallback**, không tự làm lazy mọi thao tác trước đó.

Nếu muốn fallback vẫn là một Option để tiếp tục nối các bước:

~~~java
Optional<Config> selected = findConfig(id)
        .or(() -> findSystemConfig())
        .filter(Config::enabled);
~~~

Ở đây `or` được dùng ở Java 9+, supplier trả `Optional<Config>`. Nếu user config có mặt, không thử system config, kể cả user config bị `filter` loại **ở bước sau**. Thứ tự quan trọng:

~~~java
findConfig(id).filter(Config::enabled)
        .or(() -> findSystemConfig())
~~~

Dạng thứ hai mới thử cấu hình hệ thống khi cấu hình người dùng không tồn tại **hoặc bị loại vì không enabled**. Đó là **hai quy tắc nghiệp vụ khác nhau**.

**Thực hành:** Trước khi chọn thứ tự `filter` và `or`, hãy nói bằng ngôn ngữ tự nhiên liệu “cấu hình có mặt nhưng bị tắt” nên làm hệ thống fallback hay nên được coi là một quyết định dừng.

## 10. Kết hợp Optional với Stream

Khi có một collection chứa nhiều Optional, đôi lúc muốn lấy **chỉ các giá trị có mặt**. Từ Java 9, `Optional.stream()` trả stream có **0 hoặc 1 phần tử**.

~~~java
List<Optional<String>> maybes = List.of(
        Optional.of("a"),
        Optional.empty(),
        Optional.of("b")
);

List<String> values = maybes.stream()
        .flatMap(Optional::stream)
        .toList();
// values = [a, b]
~~~

Đây là đoạn minh họa, cần `List` và `Optional`. `flatMap(Optional::stream)` chuyển `Stream<Optional<String>>` thành `Stream<String>` và bỏ qua các Optional rỗng.

**Đừng nhầm `Optional.flatMap` với `Stream.flatMap`.** Cả hai đều tránh lồng container, nhưng một bên xử lý `Optional<T>` và một bên xử lý `Stream<T>`.

Ví dụ với nhiều ID:

~~~java
List<User> existing = ids.stream()
        .map(this::findUser)
        .flatMap(Optional::stream)
        .toList();
~~~

Đoạn minh họa trong class có `ids` kiểu `List<String>` và `findUser` trả `Optional<User>`. Đây là cách lấy các user tồn tại. Nhưng nếu nghiệp vụ cần **báo lỗi cho từng ID bị thiếu**, bỏ qua empty là chưa đủ: phải giữ ID gốc trong result hoặc trả một cấu trúc chứa trạng thái của từng lần tra cứu.

## 11. Kiểm thử chuỗi Optional theo bảng trường hợp

Khi kiểm thử một chuỗi có thể thiếu ở nhiều tầng, không chỉ thử một ca thành công và một ca null ở đầu. Nên lập **bảng quyết định**.

### 11.1. Bảng ca cho bài Customer → Address → City

| Đầu vào | Customer | Address | City | Kỳ vọng |
|---|---|---|---|---|
| `c1` | Có | Có | `"  Ha Noi  "` | `Optional[HA NOI]` |
| `c2` | Có | `null` | — | `Optional.empty` |
| `c3` | Có | Có | `"   "` | `Optional.empty` |
| `missing` | Không | — | — | `Optional.empty` |
| City null | Có | Có | `null` | `Optional.empty` nếu policy cho phép |
| City `"Da Nang"` | Có | Có | Hợp lệ | `Optional[DA NANG]` |

Điểm quan trọng là **mỗi nguyên nhân vắng mặt tại một tầng đều được thử**. Nếu chỉ test ID không tồn tại, sẽ bỏ sót lỗi khi địa chỉ null hoặc thành phố rỗng.

### 11.2. Bảng ca cho parse số dương

| Input | Kết quả |
|---|---|
| `"12"` | `Optional[12]` |
| `" 12 "` | `Optional[12]` |
| `"0"` | Empty |
| `"-3"` | Empty |
| `"abc"` | Empty |
| `""` hoặc khoảng trắng | Empty |
| `null` | Empty |
| Số vượt giới hạn `int` | Empty |

Nếu thay luật cho phép `0`, chỉ cần sửa predicate/chính sách parse số dương; bảng kiểm thử sẽ giúp phát hiện khác biệt.

### 11.3. Kiểm thử thời điểm gọi fallback

Không chỉ kiểm tra **giá trị trả về**, hãy kiểm tra **supplier fallback có được gọi đúng khi cần**. Một cách là dùng `AtomicInteger` như `OptionalFallbackDemo`. Nhưng với mã production, không nên phụ thuộc vào side effect của callback để tính kết quả; kiểm thử side effect ở đây chỉ nhằm xác nhận **hợp đồng lazy của `orElseGet`**.

### 11.4. Unit test không cần database thật

Nếu hàm tra cứu có interface được tách riêng, có thể truyền vào map giả hoặc repository test double. Các hàm chuẩn hóa như `String::strip`, `filter`, `map` có thể kiểm thử bằng dữ liệu bất biến và các ca biên, không cần server hay network.

## 12. Những sai lầm thường gặp trong chuỗi Optional

### Sai lầm 1: Lấy get trước khi kiểm tra

~~~java
// KHÔNG AN TOÀN khi Optional có thể empty:
String name = findUser(id).get().name();
~~~

`Optional.get()` ném `NoSuchElementException` nếu rỗng. Thay bằng:

~~~java
Optional<String> name = findUser(id).map(User::name);
~~~

Hoặc nếu vắng người dùng là lỗi nghiệp vụ:

~~~java
User user = findUser(id).orElseThrow(
        () -> new IllegalArgumentException("User not found"));
~~~

Các đoạn minh họa yêu cầu các kiểu/phương thức tương ứng.

### Sai lầm 2: Dùng map cho hàm trả Optional

~~~java
// Dễ tạo Optional<Optional<Address>>.
Optional<Optional<Address>> nested =
        findUser(id).map(this::findAddress);
~~~

Nếu `findAddress` trả `Optional<Address>`, dùng:

~~~java
Optional<Address> address =
        findUser(id).flatMap(this::findAddress);
~~~

### Sai lầm 3: Trả null từ flatMap

~~~java
// CỐ Ý SAI:
Optional.of("abc").flatMap(value -> null);
~~~

Nếu mapper đã được gọi mà trả `null`, `Optional.flatMap` ném `NullPointerException`. Trả `Optional.empty()` khi không có kết quả.

### Sai lầm 4: Tưởng map bắt mọi exception

~~~java
Optional<String> text = Optional.of("abc");
Optional<Integer> number = text.map(Integer::parseInt);
~~~

Code sẽ ném `NumberFormatException`, không trả empty. Optional chỉ xử lý **vắng mặt**, không tự chuyển mọi lỗi thành empty. Nếu việc parse thất bại là trạng thái dự kiến, viết một hàm xử lý lỗi có chủ đích như bài `parsePositiveInt`.

### Sai lầm 5: Gọi orElse với fallback tốn kém

`orElse(expensive())` **đánh giá đối số ngay**. Dùng `orElseGet(() -> expensive())` khi fallback chỉ nên chạy lúc Optional rỗng. Với giá trị hằng rẻ như `"UNKNOWN"`, `orElse("UNKNOWN")` hoàn toàn phù hợp.

### Sai lầm 6: Dùng ifPresent để cố trả giá trị

`ifPresent` và `ifPresentOrElse` trả `void`; chúng dành cho hành động. Nếu muốn thu chuỗi, dùng `map` rồi `orElse`/`orElseGet`, hoặc giữ `Optional<String>` cho caller.

### Sai lầm 7: Lạm dụng Optional cho mọi field và tham số

`Optional` hữu ích nhất như **kiểu trả về** của phương thức có thể không có kết quả. Không phải mọi field đều nên có kiểu `Optional<T>`, và việc dùng `Optional` làm tham số có thể làm API dài dòng khi kiểu miền dữ liệu hoặc overload rõ hơn.

Trong ví dụ record có trường `Address` có thể null, ta dùng `Optional.ofNullable` tại **ranh giới xử lý**. Trong production, tốt hơn nên định nghĩa quy tắc không-null, validation hoặc kiểu giá trị thích hợp ngay tại model tùy yêu cầu.

### Sai lầm 8: Dùng empty để che lỗi cần phân biệt

Nếu sản phẩm phải trả lời “không có hồ sơ”, “chưa có địa chỉ”, “thành phố trống”, hoặc “không được phép truy cập”, một `Optional.empty()` duy nhất **làm mất thông tin**. Hãy dùng kiểu kết quả có enum/record nguyên nhân, hoặc exception đúng nghĩa, thay vì nhầm các trạng thái lỗi với vắng mặt bình thường.

### Sai lầm 9: Chain quá dài che ý nghĩa nghiệp vụ

~~~java
Optional<String> result = find(id)
        .flatMap(this::fetchSomething)
        .map(this::convert)
        .filter(this::check)
        .flatMap(this::lookupOther)
        .map(this::render);
~~~

Đây là minh họa. Nếu người đọc khó biết từng bước có tác dụng gì, nên đặt tên hàm/biến trung gian, hoặc tạo helper có hợp đồng rõ. **Ngắn hơn không đồng nghĩa dễ hiểu hơn.** Optional là công cụ làm rõ dữ liệu có thể thiếu, không phải mục đích tự thân của thiết kế.

### Sai lầm 10: Không xét null bên trong mapper

`map(String::strip)` chỉ an toàn khi Optional hiện có chứa một `String` khác null. `Optional` không thể chứa giá trị null; nếu một bước trước trả null, `map` biến nó thành empty. Nhưng nếu mapper gọi method trên **một thành phần null khác** không được bảo vệ, nó vẫn có thể ném `NullPointerException`. Ví dụ `map(user -> user.profile().city())` sẽ dereference `null` nếu `profile()` trả null. Tách thành `map(User::profile).map(Profile::city)` khi đúng ngữ nghĩa.

## 13. Optional, dữ liệu mutable và side effect

Các phép biến đổi trên Optional thường được dùng theo phong cách functional. Tuy nhiên, `Optional.map()` không biến mapper thành pure function và không clone các đối tượng đang có.

~~~java
Optional<StringBuilder> builder =
        Optional.of(new StringBuilder("a"));

Optional<StringBuilder> same = builder.map(x -> x);
same.ifPresent(x -> x.append("b"));
~~~

Đây là ví dụ minh họa. `builder` và `same` có thể chứa **cùng reference `StringBuilder`**; hành động `append` thay đổi object mutable. Nếu cần một giá trị tách rời, chuyển thành `String` hoặc DTO/value object mới.

**Hãy giữ riêng logic giá trị và hiệu ứng:**

- `map`, `flatMap`, `filter` chủ yếu dùng để tính toán/tra cứu.
- `ifPresent`, `ifPresentOrElse` dùng khi caller thực sự cần **hành động**.
- Với database transaction, gửi email hay ghi event bắt buộc, một service/orchestrator có hợp đồng rõ thường dễ kiểm soát lỗi hơn việc nhét side effect vào một mapper.
- Trong môi trường đồng thời, Optional không tự cung cấp synchronization hay snapshot; các object chứa bên trong có thể vẫn mutable và phải được chia sẻ theo Java Memory Model.

## 14. Lưu ý về null và API boundary

### 14.1. of, ofNullable và empty

| Phương thức | Khi dùng | Đặc điểm |
|---|---|---|
| `Optional.of(value)` | Chắc chắn `value != null` | Truyền null → `NullPointerException` |
| `Optional.ofNullable(value)` | `value` có thể null | Null → `Optional.empty()` |
| `Optional.empty()` | Cố ý biểu diễn không có giá trị | Không chứa `null` như một phần tử |
| `Optional.map(f)` | Mapper trả giá trị thường `U` | Mapper trả null → Optional rỗng |
| `Optional.flatMap(f)` | Mapper trả `Optional<U>` | Mapper trả null → `NullPointerException` |

Một phương thức được khai báo trả `Optional<T>` **không nên trả `null`**. Nếu kết quả có thể rỗng, trả `Optional.empty()`. Trả null phá vỡ hợp đồng mà caller dùng để nối `map/flatMap`.

### 14.2. Đừng dùng Optional để giấu precondition sai

Ví dụ một API bắt buộc ID không được null. Nếu caller truyền null, có thể hợp lý khi API ném `IllegalArgumentException`/`NullPointerException` thay vì xem như “không tìm thấy”. Đó là quyết định hợp đồng, không phải quy tắc mọi null đều phải thành Optional.empty.

Nên phân biệt:

- **Input sai hợp đồng:** lỗi sử dụng API hoặc precondition.
- **Dữ liệu hợp lệ nhưng không tìm thấy:** Optional.empty.
- **Trạng thái nghiệp vụ có nhiều nguyên nhân lỗi:** result type có thông tin lỗi.
- **Tác vụ I/O lỗi:** exception hoặc kết quả lỗi được định nghĩa rõ.

## 15. Bài tập tổng hợp và hướng dẫn giải

### Bài tập A — Thành phố và mã vùng

Dữ liệu là `Optional<Customer>`. Nếu có Customer, Address và postalCode khác rỗng, trả mã vùng đã chuẩn hóa:

~~~java
Optional<String> postal = maybeCustomer
        .map(Customer::address)
        .map(Address::postalCode)
        .map(String::strip)
        .filter(code -> !code.isEmpty());
~~~

Nếu thiếu bất kỳ tầng nào, kết quả empty. Đây là snippet minh họa trong ngữ cảnh có `Customer`/`Address` như bài thực hành 1.

**Tự mở rộng:** thêm `filter(code -> code.matches("[0-9]{6}"))` nếu hợp đồng mã vùng đúng sáu chữ số ASCII. Nếu cần báo rõ “mã sai định dạng”, hãy dùng result validation thay vì chỉ empty.

### Bài tập B — Có người quản lý thì lấy ID, không có thì fallback

~~~java
String managerId = directory.findManagerId("u1")
        .orElse("NO_MANAGER");
~~~

Kết quả `"u2"` với bộ dữ liệu ở `OptionalManagerDemo`. Nếu đổi thành `"u3"`, kết quả `"NO_MANAGER"`. Mặc dù cả thiếu ID quản lý và trỏ tới ID quản lý không tồn tại đều cho empty, chúng có **nguyên nhân khác nhau** mà API hiện tại không phân biệt.

### Bài tập C — Tạo câu thông báo chỉ khi parse thành công

~~~java
Optional<String> message = parsePositiveInt(" 8 ")
        .map(n -> "quantity=" + n);
~~~

Kết quả là `Optional[quantity=8]`. Với `parsePositiveInt("-1")`, mapper tạo message không chạy và kết quả empty.

### Bài tập D — Chọn API sau khi có Optional

Bạn muốn:

- Hiển thị user nếu tìm thấy, nếu không hiển thị lỗi: `ifPresentOrElse`.
- Lấy giá trị cấu hình mặc định tính tốn chi phí khi vắng: `orElseGet`.
- Chọn nguồn Optional thứ hai nếu nguồn thứ nhất rỗng: `or`.
- Bắt buộc tồn tại hồ sơ để tiếp tục: `orElseThrow`.
- Chuyển `Optional<User>` thành `Optional<String>` bằng tên: `map`.
- Từ `Optional<User>` tìm `Optional<Address>`: `flatMap`.

**Lưu ý:** Nếu default đơn giản là hằng, `orElse` không có vấn đề hiệu năng đáng kể; tránh biến mỗi fallback thành supplier dài dòng vô ích.

### Bài tập E — Tự viết thêm testcase

Hãy viết test cho `parsePositiveInt` với:

- `"001"` (parse thành số `1`, trả Optional có giá trị).
- `"+2"` (Java `Integer.parseInt` chấp nhận dấu cộng, trả `2`).
- `"2.5"` (không phải số nguyên, empty).
- `"2147483648"` (vượt `Integer.MAX_VALUE`, empty).
- `"-2147483648"` (không dương, empty).

**Điểm cần suy nghĩ:** Nếu sản phẩm không cho phép dấu `+` hoặc các số có số 0 đứng đầu, `Integer.parseInt` vẫn có thể chấp nhận chúng. Khi đó phải bổ sung **luật format** bằng một predicate trước bước parse; không nên coi toàn bộ cú pháp được parse thành công mặc định là hợp lệ về nghiệp vụ.

## 16. Checklist kiểm thử trước khi dùng Optional trong dự án

1. **Giá trị nào có thể thiếu?** Xác định từng tầng có khả năng null hoặc không tìm thấy.
2. **Có nên trả Optional ở ranh giới API không?** Vắng mặt có phải trường hợp bình thường?
3. **Bước nào trả object thường, bước nào trả Optional?** Chọn `map` hoặc `flatMap` đúng kiểu.
4. **Mapper trả null có được phép?** `map` đổi thành empty, `flatMap` không chấp nhận.
5. **Kết quả sau filter empty có làm mất nguyên nhân lỗi quan trọng không?**
6. **Fallback được tính khi nào?** Phân biệt `orElse` với `orElseGet`.
7. **Caller cần một value, Optional, lỗi hay action?** Chọn `orElse...`, `or`, `orElseThrow` hoặc `ifPresentOrElse`.
8. **Có dùng get() không kiểm tra không?** Nếu có, xem lại hợp đồng.
9. **Test đủ tầng thiếu dữ liệu chưa?** Thiếu đầu, thiếu giữa, dữ liệu rỗng, sai định dạng.
10. **Có exception bất ngờ không?** Optional không nuốt `NullPointerException` trong mapper hay `NumberFormatException` của parse.
11. **Có side effect trong mapper/filter không?** Hạn chế mutation và phụ thuộc state ngoài.
12. **Kết quả có chia sẻ object mutable với input không?** Optional không deep-copy.
13. **Chain có dễ đọc không?** Cần thì tách thành phương thức có tên.
14. **Có giới hạn kiểu dữ liệu/định dạng theo nghiệp vụ không?** Ví dụ parse int chấp nhận dấu cộng nhưng form có thể cấm.
15. **Có cần phân biệt absent với failure không?** Nếu có, dùng kiểu kết quả mạnh hơn Optional.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `Optional.ofNullable(null).map(String::strip)` trả gì?

**Câu 2.** Vì sao `findUser(id).flatMap(this::findManager)` đúng hơn `map` nếu `findManager` trả `Optional<User>`?

**Câu 3.** Với chuỗi `"   "`, vì sao `map(String::strip).filter(s -> !s.isEmpty())` trả empty?

**Câu 4.** `Optional.of("x").map(s -> null)` và `Optional.of("x").flatMap(s -> null)` khác nhau thế nào?

**Câu 5.** `Optional.of("ready").orElse(expensive())` có luôn bỏ qua `expensive()` không?

**Câu 6.** Khi nào `orElseGet` gọi supplier?

**Câu 7.** `or(Supplier<Optional<T>>)` trả `T` hay `Optional<T>`?

**Câu 8.** `parsePositiveInt("abc")` trong ví dụ trả gì? Nó có tự báo nguyên nhân lỗi cho caller không?

**Câu 9.** `ifPresentOrElse` phù hợp để tạo một `String` trả về không?

**Câu 10.** Nếu `Optional<User>` có user mà `map(user -> user.profile().city())` ném NPE, Optional có chuyển exception thành empty không?

**Câu 11.** Muốn gom những giá trị có mặt từ `List<Optional<T>>` bằng Stream, dùng phương thức nào?

**Câu 12.** Có nên dùng Optional.empty cho lỗi “không được phép truy cập” nếu API cần phân biệt nó với “không tồn tại” không?

**Đáp án:**

1. `Optional.empty`; mapper không được gọi.
2. Vì `flatMap` làm phẳng kết quả Optional từ mapper, tránh `Optional<Optional<User>>`.
3. `strip()` tạo `""`, rồi `filter` loại chuỗi rỗng.
4. `map` trả empty; `flatMap` ném `NullPointerException`.
5. Không. Biểu thức `expensive()` được đánh giá trước lời gọi `orElse`.
6. Chỉ khi Optional rỗng.
7. `Optional<T>`.
8. `Optional.empty`; API này không giữ nguyên nhân lỗi.
9. Không; nó trả `void`. Dùng `map`/`orElse` hoặc một API trả giá trị.
10. Không; exception do mapper ném vẫn được truyền ra.
11. `stream().flatMap(Optional::stream)`.
12. Không nếu cần phân biệt; phải có result/error type tương ứng.

## 18. Tài liệu đối chiếu chính thức

- [Java SE 17 — Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): `ofNullable`, `map`, `flatMap`, `filter`, `or`, `orElseGet`, `orElseThrow`, `ifPresentOrElse` và `stream`.
- [Java SE 17 — Function](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html): hợp đồng hàm ánh xạ.
- [Java SE 17 — Supplier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Supplier.html): supplier không tham số cho fallback.
- [Java SE 17 — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): `flatMap`, `toList` và cách xử lý nhiều Optional.
- [Java SE 17 — Integer.parseInt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#parseInt(java.lang.String)): cú pháp số nguyên và lỗi `NumberFormatException`.

**Ghi nhớ:** Trong một chuỗi thao tác có thể thiếu dữ liệu, dùng `Optional.ofNullable` ở ranh giới có thể null, `map` cho phép biến đổi trả **giá trị thường**, `flatMap` cho bước **đã trả Optional**, `filter` cho điều kiện giữ/bỏ giá trị; chọn `orElseGet`, `orElseThrow`, `or` hoặc `ifPresentOrElse` theo đúng nhu cầu đầu ra. Test từng tầng vắng mặt, không để `Optional.empty` che mất lỗi nghiệp vụ quan trọng, và đừng nhầm Optional với cơ chế bắt ngoại lệ hay bảo vệ object mutable.