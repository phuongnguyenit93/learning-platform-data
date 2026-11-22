# Thực hành tổng hợp: xử lý kết quả bắt buộc bằng `Optional.orElseThrow()` (Java 10+)

## 1. Vấn đề cần giải quyết

Trong một ứng dụng Java, phương thức truy vấn dữ liệu không phải lúc nào cũng tìm được phần tử: một mã người dùng có thể không tồn tại, danh sách có thể rỗng, bộ lọc có thể không còn giá trị phù hợp. `java.util.Optional<T>` diễn đạt rõ hai khả năng: **có một giá trị không null** hoặc **không có giá trị**.

Nhưng có hai loại yêu cầu rất khác nhau:

- **Không có kết quả là bình thường:** ví dụ một trang tìm kiếm không thấy người dùng, hoặc chưa thiết lập ảnh đại diện. Caller có thể giữ `Optional.empty()` hay chọn fallback hợp lệ.
- **Phải có kết quả mới được xử lý tiếp:** ví dụ bước ghi hóa đơn đòi hỏi mã đơn hàng đã được xác nhận. Nếu dữ liệu thiếu, hệ thống phải dừng bước đó và báo lỗi rõ ràng, không bịa giá trị mặc định.

Đây là lý do **Java 10** bổ sung **`Optional.orElseThrow()` không tham số**: một thao tác trích xuất giá trị thể hiện rằng **điểm này bắt buộc phải có dữ liệu**.

~~~java
String name = findName("u1").orElseThrow();
~~~

Nếu kết quả tra cứu là `Optional.of("Lan")`, biến `name` nhận `"Lan"`. Nếu là `Optional.empty()`, chương trình ném `NoSuchElementException`.

**Tính thời sự:** API Oracle JDK 25/26 vẫn có `orElseThrow()` với nhãn **Since: 10**. Đây là kiến thức Java 10 **vẫn áp dụng đầy đủ ở Java hiện đại**. Bài thực hành chính biên dịch với Java 17+ và cũng tương thích `javac --release 10` trên compiler còn hỗ trợ target đó.

Sau bài này, bạn sẽ biết hợp đồng `orElseThrow()`, vị trí dùng trong pipeline, cách chọn exception mặc định hay exception nghiệp vụ, lazy supplier, kiểm tra đúng hai nhánh present/empty, các nguồn `Optional` từ `Map` và `Stream`, cùng những sai lầm về fallback, null và concurrency.

## 2. Hợp đồng chính xác của `orElseThrow()`

Chữ ký:

~~~java
public T orElseThrow()
~~~

Hành vi:

| Trạng thái | Kết quả |
| --- | --- |
| `Optional.of(value)` | Trả **value** có kiểu `T` |
| `Optional.empty()` | Ném `java.util.NoSuchElementException` |
| Biến Optional bản thân là `null` | Gọi method gây `NullPointerException`, không phải xử lý empty |
| `Optional.of(null)` | Ném `NullPointerException` **khi tạo Optional** |
| `Optional.ofNullable(null)` | Tạo empty; `orElseThrow()` sau đó ném `NoSuchElementException` |

`NoSuchElementException` kế thừa **`RuntimeException`** nên là **unchecked exception**. Phương thức Java gọi overload không tham số không bắt buộc khai báo `throws NoSuchElementException`, nhưng nếu không được xử lý, ngoại lệ vẫn có thể làm request, job hoặc thread thất bại.

Sơ đồ hành vi:

~~~text
Optional<T>
    |
    v
Có giá trị?
    | Có                     | Không
    v                        v
Trả T                    throw NoSuchElementException
    |                        |
    v                        v
Tiếp tục logic            Tìm exception handler hoặc kết thúc
~~~

Không có bước query database, kiểm tra mạng hoặc thực hiện lock mới bên trong `orElseThrow()`: nó chỉ quyết định dựa trên **Optional đã có**.

### Một ví dụ tối giản

~~~java
String present = Optional.of("ready").orElseThrow();
// present = "ready"

String missing = Optional.<String>empty().orElseThrow();
// ném NoSuchElementException; không có giá trị trả về
~~~

Hai đoạn trên là **minh họa trong một phương thức** với import `java.util.Optional`. Dòng `missing` phải được catch nếu muốn các câu lệnh sau tiếp tục chạy.

**Không nên kiểm thử bằng cách so văn bản thông điệp lỗi mặc định**: Oracle API bảo đảm loại `NoSuchElementException`; nếu cần message/mã nghiệp vụ do ứng dụng kiểm soát, dùng overload có supplier.

## 3. Vì sao không chỉ dùng `Optional.get()`?

`Optional.get()` đã có từ Java 8:

~~~java
String value = optional.get();
~~~

Nó cũng trả `T` khi present, hoặc ném `NoSuchElementException` khi empty. Tuy nhiên tên `get()` **không thể hiện ngay ý định fail nếu thiếu dữ liệu**.

~~~java
String value = optional.orElseThrow();
~~~

Cách thứ hai nói rõ hơn: trích xuất giá trị, **nếu không có thì ném ngoại lệ**. Oracle API hiện hành ghi chú ngay dưới `get()`: phương án ưu tiên là `orElseThrow()`.

**Phân biệt khuyến nghị và deprecation:** `Optional.get()` hiện vẫn tồn tại, **không bị đánh dấu deprecated** trong Oracle JDK 25. Không nói rằng `get()` đã bị xóa hoặc code cũ không còn chạy.

Mốc phiên bản cần nhớ:

- `Optional<T>`, `get()`, `orElse(T)`, `orElseGet(Supplier)`, `orElseThrow(Supplier)`: có từ Java 8.
- `Optional.stream()`, `Optional.or(Supplier<Optional>)`, `ifPresentOrElse`: có từ Java 9.
- **`Optional.orElseThrow()` không tham số**: **Java 10**.
- `Optional.isEmpty()`: Java 11. Không dùng nó trong source muốn chạy đúng Java 10.

### Có phải `orElseThrow()` luôn tốt hơn `get()`?

Khi bạn cần diễn đạt **bắt buộc có giá trị**, tên `orElseThrow()` rõ ràng hơn. Tuy nhiên không biến mọi `get()` thành `orElseThrow()` mà bỏ qua câu hỏi nghiệp vụ: nếu missing là kết quả bình thường, **cả hai** đều có thể là lựa chọn không phù hợp.

## 4. Nguồn Optional và cách tạo đúng

### `Optional.of(value)`

~~~java
Optional<String> value = Optional.of("Lan");
~~~

Dùng khi giá trị **không được null**. Nếu đối số null, `of` ném `NullPointerException` ngay tại bước tạo, **không** trở thành `Optional.empty()`.

### `Optional.ofNullable(value)`

~~~java
String fromMap = users.get(id);
Optional<String> found = Optional.ofNullable(fromMap);
~~~

- `fromMap != null` → Optional present.
- `fromMap == null` → Optional empty.

Đây là cách phổ biến để **đóng gói kết quả nullable** từ thư viện/API cũ. Tuy nhiên nếu `Map` cho phép lưu `null`, `Map.get` trả null có thể là **không có key** hoặc **key có value null**; `ofNullable` không tự phân biệt. Nếu điều đó quan trọng, contract nguồn hoặc `containsKey` cần xử lý riêng.

### `Optional.empty()`

~~~java
Optional<String> absent = Optional.empty();
~~~

Trả về rõ ràng rằng không có dữ liệu. **Đừng trả `null` thay vì một Optional instance**:

~~~java
// Tránh:
Optional<String> findSomething() {
    return null;
}
~~~

Oracle API nói biến thuộc kiểu `Optional` **không nên tự nó là null**. Null Optional sẽ gây NPE ở lời gọi `map`, `orElseThrow` hoặc các phương thức khác.

### Quy tắc chung

Hãy để **repository/nguồn dữ liệu** trả `Optional<T>` khi việc không tìm thấy là một kết quả có thể xảy ra. Tầng nghiệp vụ quyết định **bước nào cần chuyển empty thành ngoại lệ**.

## 5. Khi nào thiếu dữ liệu là lỗi?

Trước khi gọi `orElseThrow()`, đặt câu hỏi: **“Nếu không có kết quả, bước xử lý này có còn hợp lệ không?”**

| Nhu cầu | Thiếu dữ liệu | Cách tiếp cận |
| --- | --- | --- |
| Hiển thị kết quả tìm kiếm | Bình thường | Giữ Optional, danh sách rỗng hoặc `ifPresent` |
| Lấy màu chủ đề tùy chọn | Có fallback hợp lệ | `orElse(defaultColor)` |
| Khởi tạo dịch vụ cần cấu hình bắt buộc | Lỗi cấu hình | `orElseThrow(() -> new IllegalStateException(...))` |
| Bắt đầu thanh toán cần order ID | Vi phạm điều kiện tiếp tục | `orElseThrow(...)` |
| Tính `max()` từ tập có thể rỗng | Phụ thuộc contract | Giữ Optional hoặc báo lỗi |
| Truy vấn profile để hiển thị trang cá nhân | Có thể là 404 ở REST endpoint | Lựa chọn exception và HTTP mapping tại boundary |
| Lọc địa chỉ giao hàng hợp lệ | Thiếu địa chỉ phải dừng | `filter` rồi `orElseThrow(...)` |

**Không có quy tắc “mọi Optional rỗng phải throw”.** `Optional` là cách ghi rõ khả năng vắng mặt; quyết định lỗi hay fallback thuộc về **use case**.

Ví dụ không phù hợp nếu ID bắt buộc:

~~~java
String id = findOrderId().orElse("UNKNOWN");
capturePayment(id);
~~~

Nếu `"UNKNOWN"` không phải ID hợp lệ, việc chọn default chỉ **che mất lỗi dữ liệu**. Khi nghiệp vụ thực sự bắt buộc:

~~~java
String id = findOrderId().orElseThrow(
        () -> new IllegalStateException("Missing order ID"));
capturePayment(id);
~~~

Đây là **đoạn minh họa trong tầng nghiệp vụ**; `findOrderId` và `capturePayment` là các phương thức do ứng dụng cung cấp, không phải Java SDK APIs.

## 6. Chương trình Java 17+ độc lập: kiểm tra đầy đủ các nhánh

Chương trình sau sử dụng `Map.of`, `Optional.ofNullable`, `map`, `filter`, hai overload `orElseThrow`, `IOException`, lazy supplier và `Optional.stream()`. Các API cần thiết đều có trên Java 10, nên source có thể biên dịch bằng **`--release 10`**.

Lưu tên file **`OptionalRequiredDemo.java`**:

~~~java
import java.io.IOException;
import java.util.Locale;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

public final class OptionalRequiredDemo {
    private static final Map<String, String> USERS =
            Map.of("u1", "Lan", "u2", "  Minh  ", "u3", "   ");

    private OptionalRequiredDemo() {}

    public static Optional<String> findName(String id) {
        return Optional.ofNullable(USERS.get(id));
    }

    public static String requireName(String id) {
        return findName(id).orElseThrow();
    }

    public static String requireNormalizedName(String id) {
        return findName(id)
                .map(String::trim)
                .filter(name -> !name.isEmpty())
                .orElseThrow(
                        () -> new IllegalStateException(
                                "No usable name: " + id));
    }

    public static String requireNameWithContext(String id) {
        return findName(id).orElseThrow(
                () -> new IllegalArgumentException(
                        "Unknown user: " + id));
    }

    public static String requireWithCheckedException(boolean found)
            throws IOException {
        Optional<String> candidate =
                found ? Optional.of("OK") : Optional.empty();
        return candidate.orElseThrow(
                () -> new IOException("Required value missing"));
    }

    public static void main(String[] args) throws Exception {
        System.out.println("present=" + requireName("u1"));
        System.out.println("normalized=" + requireNormalizedName("u2"));

        try {
            requireName("missing");
        } catch (NoSuchElementException error) {
            System.out.println("missing="
                    + error.getClass().getSimpleName());
        }

        try {
            requireNormalizedName("u3");
        } catch (IllegalStateException error) {
            System.out.println("blank=" + error.getMessage());
        }

        try {
            requireNameWithContext("u9");
        } catch (IllegalArgumentException error) {
            System.out.println("custom=" + error.getMessage());
        }

        try {
            requireWithCheckedException(false);
        } catch (IOException error) {
            System.out.println("checked="
                    + error.getClass().getSimpleName());
        }

        AtomicInteger supplierCalls = new AtomicInteger();
        String existing = Optional.of("ready").orElseThrow(() -> {
            supplierCalls.incrementAndGet();
            return new IllegalStateException("not reached");
        });
        System.out.println("lazy="
                + existing + "/" + supplierCalls.get());

        long presentCount = Stream.of("u1", "missing", "u2")
                .map(OptionalRequiredDemo::findName)
                .flatMap(Optional::stream)
                .count();
        System.out.println("streamCount=" + presentCount);
    }
}
~~~

### Cách biên dịch và chạy

Trên JDK 17+:

~~~bash
javac OptionalRequiredDemo.java
java OptionalRequiredDemo
~~~

Hoặc để kiểm tra mã nguồn hợp lệ với Java 10 trên JDK còn hỗ trợ target đó:

~~~bash
javac --release 10 OptionalRequiredDemo.java
java OptionalRequiredDemo
~~~

**Đầu ra chuẩn xác đã kiểm tra với OpenJDK 24.0.2 và `javac --release 10`:**

~~~text
present=Lan
normalized=Minh
missing=NoSuchElementException
blank=No usable name: u3
custom=Unknown user: u9
checked=IOException
lazy=ready/0
streamCount=2
~~~

**Kiểm chứng thực tế:** compiler trả exit code 0, chương trình chạy exit code 0. Bài không dựa vào network, filesystem hay random. Vì những exception được catch có chủ ý, chương trình in đủ tám dòng. Đây là ví dụ để **học rõ sự khác nhau giữa các nhánh**, không phải một khuyến nghị bắt mọi ngoại lệ rồi cho nghiệp vụ tiếp tục.

## 7. Phân tích từng dòng output

### 7.1. `present=Lan`

~~~java
findName("u1").orElseThrow()
~~~

Trong Map, `u1` có giá trị `"Lan"`. `ofNullable` tạo present Optional và `orElseThrow()` trả String bình thường.

### 7.2. `normalized=Minh`

~~~java
findName("u2")
        .map(String::trim)
        .filter(name -> !name.isEmpty())
        .orElseThrow(...)
~~~

Giá trị `"  Minh  "` được chuẩn hóa thành `"Minh"`, không bị filter loại. Cuối cùng `orElseThrow(...)` trả nó.

`String.trim()` được sử dụng vì **bài chạy được với Java 10**. Trong Java 11+ có `String.strip()` và `String.isBlank()` với semantics về khoảng trắng Unicode khác; chọn cách phù hợp business contract.

### 7.3. `missing=NoSuchElementException`

~~~java
findName("missing").orElseThrow()
~~~

Không thấy key nên `Map.get` trả null, `ofNullable` thành empty, no-arg overload ném `NoSuchElementException`. Chương trình in **tên class**, không dựa vào nội dung `getMessage()`.

### 7.4. `blank=No usable name: u3`

Map **có** key `u3`, nhưng value là chuỗi ba dấu cách. Nguồn Optional **present**, sau `trim()` và `filter(!isEmpty())` nó **empty**, vì vậy ném `IllegalStateException` được supplier tạo.

**Phân biệt:** “không có record” và “record tồn tại nhưng không đạt validation” có thể dẫn tới cùng một empty nếu pipeline đã dùng `filter`. Khi nghiệp vụ cần hai error codes riêng, phải tách bước xử lý hoặc lưu context.

### 7.5. `custom=Unknown user: u9`

`orElseThrow(() -> new IllegalArgumentException(...))` tạo **ngoại lệ có thông điệp theo ID**. Loại lỗi do ứng dụng chọn; `Optional` không tự biến mọi empty thành `IllegalArgumentException`.

### 7.6. `checked=IOException`

~~~java
return candidate.orElseThrow(
        () -> new IOException("Required value missing"));
~~~

Overload có `Supplier` có thể ném **checked exception**. Phương thức `requireWithCheckedException` khai báo `throws IOException`, và caller đã catch. Overload không tham số của Java 10 không có loại exception tùy chỉnh như thế.

### 7.7. `lazy=ready/0`

`Optional.of("ready")` là present, nên exception supplier **không được gọi**. Biến `supplierCalls` vẫn có giá trị 0. Điều này cho thấy **lazy exception creation**: tránh xây exception không cần thiết trong nhánh thành công.

### 7.8. `streamCount=2`

`"u1"` và `"u2"` có giá trị, `"missing"` không có. `Optional.stream()` (Java 9+) biến present thành stream một phần tử và empty thành stream không phần tử; `flatMap(Optional::stream)` loại empty trước khi đếm.

## 8. So sánh hai overload `orElseThrow`

~~~java
T orElseThrow()

<X extends Throwable> T orElseThrow(
        Supplier<? extends X> exceptionSupplier) throws X
~~~

| Tiêu chí | No-arg, từ Java 10 | Overload có Supplier |
| --- | --- | --- |
| Giá trị hiện diện | Trả `T` | Trả `T` |
| Empty | Ném `NoSuchElementException` | Ném exception từ supplier |
| Có message tùy chỉnh? | Không có đối số để đặt message | Có thể tạo message, cause và error type |
| Checked exception? | Không | Có thể có, theo `X` |
| Chi phí tạo exception | Chỉ khi ném | Supplier chỉ gọi khi empty |
| Mục đích | Yêu cầu giá trị có mặt, lỗi mặc định đủ dùng | Domain/API boundary cần lỗi có ngữ cảnh |

Ví dụ thiếu bản ghi nhưng cần mã lỗi nghiệp vụ:

~~~java
User user = userRepository.findById(id)
        .orElseThrow(() -> new UserNotFoundException(id));
~~~

**Đây là snippet thiết kế**, `User`, `userRepository`, `UserNotFoundException`, `id` do hệ thống của bạn định nghĩa. Nó không phải chương trình độc lập có thể chạy khi chưa khai báo những thành phần đó.

Nếu cần một thông báo thống nhất cho lỗi bất biến nội bộ:

~~~java
String required = result.orElseThrow();
~~~

Có thể dùng overload không tham số cho code ngắn gọn. Nhưng nếu log cần biết **ID nào** thiếu, `orElseThrow(Supplier)` thường giúp chẩn đoán tốt hơn.

### Cẩn thận với `null` supplier

~~~java
Optional.<String>empty().orElseThrow(null);
~~~

Khi Optional empty và supplier là `null` (hoặc supplier trả `null`), API có thể ném **`NullPointerException`** thay vì một domain exception. Không dùng `null` để yêu cầu hành vi mặc định: dùng **`orElseThrow()` no-arg**.

## 9. Supplier lazy: tại sao quan trọng?

Một đối số `Supplier` là lambda hoặc method reference được gọi **chỉ khi cần exception**:

~~~java
String value = Optional.of("OK").orElseThrow(
        () -> new IllegalStateException("not reached"));
~~~

Ở trên `"OK"` được trả; lambda không chạy. Những lợi ích:

- Không tạo exception và stack trace vô ích ở nhánh thành công.
- Không format thông điệp dài khi không có lỗi.
- Cho phép gắn ID/context lúc error thật sự xảy ra.
- Dễ kiểm thử tính lazy bằng counter như chương trình phần 6.

Tuy nhiên supplier nên **chỉ tạo lỗi**. Tránh gửi network requests, cập nhật database hay ghi state không liên quan trong exception supplier, vì side effects chỉ xảy ra khi empty và làm luồng lỗi khó kiểm soát.

**An toàn thông tin:** thông điệp lỗi không nên chứa mật khẩu, access token hay dữ liệu nhạy cảm chỉ vì lambda có thể capture request. Ở API boundary, có thể dùng mã lỗi dành cho client và nội dung log nội bộ được kiểm soát.

## 10. `orElseThrow` không đồng nghĩa các phương thức fallback

| Phương thức | Khi present | Khi empty | Loại kết quả |
| --- | --- | --- | --- |
| `get()` | Trả T | `NoSuchElementException` | T |
| `orElseThrow()` | Trả T | `NoSuchElementException` | T |
| `orElseThrow(supplier)` | Trả T | Ngoại lệ tùy chọn | T hoặc exception |
| `orElse(other)` | Trả T | Trả `other` | T |
| `orElseGet(supplier)` | Trả T | Tạo T từ supplier | T |
| `or(supplier)` | Trả Optional present | Lấy Optional dự phòng | Optional<T> |
| `ifPresent(action)` | Thực thi action | Không làm gì | void |
| `ifPresentOrElse(a,b)` | Thực thi a | Thực thi b | void |
| `stream()` | Stream có 1 phần tử | Stream rỗng | Stream<T> |

### `orElse` eager, `orElseGet` lazy

~~~java
String result = Optional.of("real")
        .orElse(expensiveFallback());
~~~

**`expensiveFallback()` được gọi dù Optional present** vì Java đánh giá method arguments trước khi gọi `orElse`.

~~~java
String result = Optional.of("real")
        .orElseGet(() -> expensiveFallback());
~~~

Ở đây supplier chỉ chạy khi empty. Nhưng **cả hai** dùng để lấy default value, không thể hiện rằng **thiếu dữ liệu là lỗi**.

### `or` chọn nguồn Optional khác

~~~java
String name = lookupPrimary(id)
        .or(() -> lookupSecondary(id))
        .orElseThrow();
~~~

**Đoạn mã minh họa** này yêu cầu hai phương thức tìm kiếm trả Optional. Nó thể hiện: **thử nguồn chính → thử nguồn dự phòng → mới yêu cầu có giá trị**. Gọi `orElseThrow` ngay sau nguồn chính sẽ bỏ qua fallback hợp lệ.

### `ifPresent` cho thao tác tùy chọn

~~~java
optional.ifPresent(System.out::println);
~~~

Khi không cần giá trị để tiếp tục và chỉ muốn side effect nếu present, `ifPresent` thích hợp hơn force unwrap rồi catch exception.

## 11. `map`, `filter`, `flatMap`: chọn điểm chốt bắt buộc

Một luồng có thể trông như:

~~~text
Optional<User> từ repository
        |
        v
map / filter / flatMap
        |
        v
Optional<ValidResult>
        |
        v
orElseThrow(...)
        |
        v
ValidResult hoặc exception
~~~

**`map`** chuyển một giá trị hiện diện. Nếu source empty, mapper không chạy. Nếu mapper trả null, `Optional.map` tạo empty như `ofNullable`.

~~~java
Optional<String> upper = Optional.of("Lan")
        .map(String::toUpperCase);
~~~

**`filter`** giữ giá trị khi predicate đúng; ngược lại cho empty.

~~~java
String value = Optional.of("  Lan  ")
        .map(String::trim)
        .filter(name -> !name.isEmpty())
        .orElseThrow();
~~~

Đoạn trên trả `"Lan"`; nếu chuỗi chỉ toàn dấu cách, `filter` sẽ loại nó.

**`flatMap`** dùng khi mapper tự trả Optional, tránh `Optional<Optional<T>>`.

~~~java
Address address = findUser(userId)
        .flatMap(User::findAddress)
        .orElseThrow(
                () -> new IllegalStateException(
                        "Missing shipping address"));
~~~

Ở đây `findUser` và `User.findAddress` là các hợp đồng giả định đã được khai báo trong ứng dụng; ví dụ nêu **cách phối hợp** chứ không phải file Java độc lập.

**Quan trọng:** `flatMap` yêu cầu mapper trả một **Optional không null**; nó không được xem null mapper result là empty. Nếu mapper trả null, nó gây **`NullPointerException`**.

### Đừng làm mất phân biệt lỗi vô ý

Nếu muốn phân biệt rõ “user không tồn tại” và “user tồn tại nhưng thiếu địa chỉ”, viết:

~~~java
User user = findUser(userId)
        .orElseThrow(() -> new UserNotFoundException(userId));

Address address = user.findAddress()
        .orElseThrow(() -> new AddressMissingException(userId));
~~~

Ở đây exception types được ứng dụng định nghĩa. Cách này dài hơn một `flatMap` liên tiếp, nhưng giữ được **hai nguyên nhân khác nhau** cho error handling và metrics.

## 12. Dùng với `Stream.findFirst()`, `max()` và kết quả rỗng

Nhiều terminal operations của Stream trả Optional:

~~~java
String first = java.util.List.of("Lan", "Minh")
        .stream()
        .filter(s -> s.startsWith("L"))
        .findFirst()
        .orElseThrow();
~~~

Giá trị là `"Lan"`. Khi filter không cho phần tử, `findFirst()` tạo empty và `orElseThrow()` ném `NoSuchElementException`.

~~~java
int max = java.util.List.of(2, 5, 3)
        .stream()
        .max(Integer::compare)
        .orElseThrow(); // 5
~~~

Nếu đầu vào rỗng, `max()` trả empty. Việc ném lỗi hay giữ Optional phải dựa vào contract của bài toán; một phép thống kê có tập rỗng là hợp lệ không nhất thiết cần exception.

### Khi muốn bỏ qua những Optional rỗng

~~~java
long count = Stream.of("u1", "missing", "u2")
        .map(OptionalRequiredDemo::findName)
        .flatMap(Optional::stream)
        .count();
~~~

Đầu ra trong chương trình mẫu là **2**. Nếu yêu cầu là “chỉ lấy những giá trị có thật”, `Optional.stream()` phù hợp hơn gọi `orElseThrow()` cho từng phần tử.

Nếu yêu cầu là “tất cả IDs đều phải có”, có thể dùng `map(id -> requireName(id))` và xử lý exception thích hợp. **Lưu ý** Stream pipeline thường lazy: exception chỉ phát sinh khi có terminal operation tiêu thụ phần tử.

## 13. `OptionalInt`, `OptionalLong`, `OptionalDouble`

Các kiểu Optional dành cho primitive cũng cung cấp overload không tham số từ Java 10.

~~~java
int count = java.util.OptionalInt.of(42).orElseThrow();
long bytes = java.util.OptionalLong.of(100L).orElseThrow();
double ratio = java.util.OptionalDouble.of(1.5).orElseThrow();
~~~

| Container | `orElseThrow()` trả | Phương thức get còn tồn tại |
| --- | --- | --- |
| `Optional<T>` | T | `get()` |
| `OptionalInt` | `int` | `getAsInt()` |
| `OptionalLong` | `long` | `getAsLong()` |
| `OptionalDouble` | `double` | `getAsDouble()` |

Khi empty, cả ba dạng primitive **ném `NoSuchElementException`** thay vì trả 0, 0L hoặc 0.0.

Ví dụ:

~~~java
java.util.OptionalInt.empty().orElseThrow();
~~~

Dòng này ném ngoại lệ. **Empty không đồng nghĩa present `0`**; một phép đo hợp lệ bằng 0 có ý nghĩa khác việc không thu được phép đo.

## 14. Checked exception: một lợi thế của overload `Supplier`

Phương thức:

~~~java
static String requiredFileValue(
        Optional<String> candidate) throws java.io.IOException {
    return candidate.orElseThrow(
            () -> new java.io.IOException("Required file value missing"));
}
~~~

có thể dùng trong một class Java với `java.util.Optional` import. Vì supplier trả `IOException` là checked exception, caller phải catch hoặc khai báo `throws`.

Overload không tham số:

~~~java
static String required(Optional<String> candidate) {
    return candidate.orElseThrow();
}
~~~

không yêu cầu checked-exception handling. Nó không có chỗ truyền message riêng.

**Dùng checked exception khi phù hợp contract**: không chuyển mọi tình huống thiếu record thành `IOException` chỉ để có một exception khác. Lỗi I/O có semantics riêng, còn “không thấy dữ liệu” ở repository có thể cần exception nghiệp vụ khác.

## 15. Từ Repository đến Service đến API

Một cách phân chia trách nhiệm thường gặp:

~~~text
Repository:
    Optional<Order> findById(id)
            |
            v
Service:
    Order order = ...orElseThrow(customException)
            |
            v
Controller / boundary:
    Exception -> status/body/log theo API contract
~~~

Repository có thể trả `Optional.empty()` mà **không coi đó là lỗi truy vấn**. Service quyết định use case có được phép tiếp tục khi không có Order. Controller/framework ánh xạ exception thành phản hồi.

Đừng mặc định rằng Java tự biến `NoSuchElementException` thành **HTTP 404**. Đó là quyết định/cấu hình ở framework và contract endpoint. Một trang tìm kiếm rỗng có thể trả 200 với danh sách rỗng; truy vấn resource ID không tồn tại có thể trả 404; trường hợp mất dữ liệu bắt buộc để hoàn thành transaction có thể cần lỗi khác.

### Tránh thông điệp nhạy cảm

Với exception supplier:

~~~java
.orElseThrow(() -> new IllegalArgumentException(
        "Unknown user: " + id))
~~~

đoạn trên phù hợp ID demo. Trong ứng dụng thật, thông điệp log/public API không nên tự động chứa **access token, mật khẩu, payload cá nhân hoặc secret**.

## 16. `NoSuchElementException` không phải transaction hoặc concurrency guard

Xét:

~~~text
T1: repository.findById(id) -> Optional.of(order)
T2: tiến trình khác xóa hoặc sửa order
T1: optional.orElseThrow() -> trả object order đã có
T1: update trạng thái -> dữ liệu có thể đã thay đổi
~~~

`orElseThrow()` **không** mở transaction, khóa bản ghi, refresh object từ database hoặc bảo đảm dữ liệu vẫn tồn tại lúc update. Đây là vấn đề **time-of-check to time-of-use (TOCTOU)**.

Khi cần invariant qua nhiều bước, dùng transaction boundaries, optimistic locking/version checks hoặc cơ chế concurrency control phù hợp. Không biến `orElseThrow` thành lời hứa bảo đảm atomicity của workflow.

## 17. `null` đầu vào khác Optional empty

Trong chương trình mẫu, `findName("missing")` đi tới `Optional.empty()`. Nhưng `findName(null)` có thể gây `NullPointerException` từ `Map.of(...).get(null)` vì immutable maps kiểu này không chấp nhận null keys theo hợp đồng.

Nếu API muốn tách biệt invalid input và missing data:

~~~java
static Optional<String> findName(String id) {
    java.util.Objects.requireNonNull(id, "id");
    return Optional.ofNullable(USERS.get(id));
}
~~~

Đây là một phiên bản minh họa trong class có `USERS` map, không thay thế file chương trình ở phần 6. Ý nghĩa:

- `id == null`: invalid argument.
- `id` hợp lệ nhưng không thấy: Optional empty.
- `id` có record: Optional present.

**Không bắt tất cả NPE rồi đổi thành `NoSuchElementException`**. NPE có thể là lỗi coding khác, không đồng nghĩa thiếu record.

## 18. Cách kiểm thử đúng

Một test tốt cần kiểm tra cả nhánh thành công và lỗi, thay vì chỉ chạy với record hiện diện.

### Test cases tối thiểu

| Trường hợp | Kỳ vọng |
| --- | --- |
| `Optional.of("Lan").orElseThrow()` | `"Lan"` |
| `Optional.empty().orElseThrow()` | `NoSuchElementException` |
| `ofNullable(null).orElseThrow()` | `NoSuchElementException` |
| `Optional.of(null)` | `NullPointerException` tại `of` |
| `orElseThrow(customSupplier)` present | Supplier không được gọi |
| `orElseThrow(customSupplier)` empty | Đúng exception type/message |
| `map/filter` làm kết quả rỗng | Throw ở bước cuối |
| Supplier tạo checked exception | Compiler buộc catch/`throws` |
| `OptionalInt.empty().orElseThrow()` | `NoSuchElementException` |

### Không dùng message mặc định làm contract

Một kiểm thử không phụ thuộc message:

~~~java
static void verifyMissing() {
    try {
        Optional.<String>empty().orElseThrow();
        throw new AssertionError("Expected NoSuchElementException");
    } catch (NoSuchElementException expected) {
        // Đúng loại exception.
    }
}
~~~

Đây là snippet nằm trong một class với imports `Optional` và `NoSuchElementException`. Lệnh `throw new AssertionError` hoạt động ngay cả khi JVM không bật `-ea`, khác với Java `assert` có thể bị tắt mặc định.

### Với JUnit 5

Nếu project có sẵn JUnit 5 dependencies/test runner:

~~~java
assertEquals("Lan", OptionalRequiredDemo.requireName("u1"));
assertThrows(NoSuchElementException.class,
        () -> OptionalRequiredDemo.requireName("missing"));
~~~

Đây là **đoạn minh họa**, không nằm trong chương trình Java độc lập ở phần 6. Không chạy nó nếu chưa có dependency và static imports tương ứng.

## 19. Optional là value-based class

Oracle mô tả `Optional` là **value-based** và khuyến nghị không dựa vào identity của nó.

~~~java
Optional<String> a = Optional.empty();
Optional<String> b = Optional.empty();
~~~

Đừng dùng `a == b` để kết luận empty/present. Không có hợp đồng buộc `Optional.empty()` là một singleton duy nhất. Dùng `isPresent()` hoặc `isEmpty()` ở Java 11+ khi thật sự cần hỏi trạng thái.

Cũng **không đồng bộ trên Optional instance**:

~~~java
// Tránh dùng synchronized(optional) { ... }
~~~

Optional chủ yếu dành cho **method return types** khi cần biểu diễn absence, không phải một kiểu bắt buộc phải dùng cho mọi field, parameter hay mô hình dữ liệu. Trong ORM, serialization và các framework có conventions riêng, Optional fields có thể khó tích hợp. `Optional` **không bảo đảm Java Object Serialization** chỉ vì nó là generic container.

## 20. Hiệu năng: đừng tối ưu bằng cách che lỗi

Exception creation/stack trace có chi phí. Tuy nhiên việc dùng `orElse(null)` thay `orElseThrow()` chỉ để “tránh ngoại lệ” có thể làm mất invariant và gây lỗi xa nguồn gốc hơn.

- Nếu **empty thường xuyên và hợp lệ**, API/logic nên biểu diễn nhánh đó như một kết quả bình thường, không ép throw rồi catch liên tục.
- Nếu **empty bất thường và cần dừng**, throw là hợp đồng đúng.
- Supplier giúp **không tạo exception khi present**.
- `Optional.orElseThrow()` không tự bảo đảm nhanh hơn `get()` hoặc một branch `if`; compiler/JIT có thể tối ưu theo workload. Cần benchmark thực tế trước khi kết luận.

Đừng dùng `Optional` chỉ như một cái hộp để chuyển qua lại liên tục với null trong code đường nóng mà không có nhu cầu thể hiện absence; hãy ưu tiên readability và API contracts, sau đó mới profile nếu có bottleneck thật.

## 21. Các lỗi suy luận thường gặp

| Sai lầm | Giải thích | Cách làm đúng |
| --- | --- | --- |
| “No-arg `orElseThrow` mới chỉ có ở JDK 25.” | Có từ **Java 10** | Dùng trên Java 10+ |
| “`get()` bị deprecated.” | Vẫn tồn tại; docs chỉ khuyên dùng `orElseThrow` | Không nhầm recommendation với deprecation |
| “No-arg cho custom message.” | Không có supplier | Dùng overload `orElseThrow(Supplier)` |
| “Cả hai overload đều ném checked exception.” | No-arg ném unchecked `NoSuchElementException` | Phân biệt overload |
| “`Optional.of(null)` tạo empty.” | Nó ném NPE | Dùng `ofNullable(null)` |
| “Có default là dùng `orElse` luôn.” | Default có thể che dữ liệu bắt buộc bị thiếu | Chọn theo business contract |
| “`orElse(expensive())` lazy.” | Đối số đánh giá trước lời gọi | Dùng `orElseGet` |
| “Supplier tạo exception luôn chạy.” | Chỉ chạy khi empty | Kiểm tra lazy execution |
| “`filter` giữ present mọi lúc.” | Predicate sai → empty | Xác định validation chính xác |
| “`flatMap` trả null thành empty.” | Mapper trả null gây NPE | Trả Optional hợp lệ |
| “`map` trả null làm Optional chứa null.” | `map` xử lý như `ofNullable` | Hiểu API contract |
| “`NoSuchElementException` tự tạo HTTP 404.” | HTTP mapping do framework/application | Thiết kế exception handler |
| “Throw xong vẫn tiếp tục thanh toán.” | Exception cắt luồng thường | Xác định transaction/rollback |
| “`OptionalInt.empty()` bằng giá trị 0.” | Empty khác present zero | Dùng primitive Optional đúng |
| “`orElseThrow` khóa dữ liệu nguồn.” | Chỉ trích xuất giá trị từ Optional | Dùng transaction/locking riêng |
| “Có thể test text message no-arg bất biến.” | API bảo đảm type, không hứa message cố định | Assert type |
| “Có thể dùng `Optional` làm monitor lock.” | Optional là value-based | Dùng lock riêng |
| “Tất cả missing đều là bug.” | Nhiều use cases cho phép không có dữ liệu | Phân định ở boundary |

## 22. Bài tập: áp dụng trong luồng đặt hàng

Một use case tạo vận đơn cần:

1. Tìm khách hàng theo ID.
2. Tìm địa chỉ giao hàng của khách hàng.
3. Chỉ tạo vận đơn nếu **cả khách hàng lẫn địa chỉ** tồn tại.

Hai hướng thiết kế:

**Cách A — giữ hai nguyên nhân lỗi khác nhau:**

~~~java
User user = repository.findById(userId)
        .orElseThrow(() -> new UserNotFoundException(userId));

Address address = user.findAddress()
        .orElseThrow(() -> new AddressMissingException(userId));

shippingService.createShipment(user, address);
~~~

**Cách B — gộp khi use case chỉ cần biết thiếu một trong hai:**

~~~java
Address address = repository.findById(userId)
        .flatMap(User::findAddress)
        .orElseThrow(() -> new IllegalStateException(
                "Cannot resolve shipping address"));
shippingService.createShipment(address);
~~~

Hai ví dụ là **minh họa kiến trúc**, cần các types, repository và service được định nghĩa trong project. Cách A dễ báo lỗi chính xác hơn; cách B gọn hơn nhưng có thể mất nguyên nhân “không thấy user” hay “thiếu address”.

**Không có một cách luôn tốt hơn mọi tình huống.** Quyết định dựa trên hợp đồng nghiệp vụ, API errors và khả năng quan sát.

## 23. Câu hỏi tự kiểm tra

### Câu 1
**Hỏi:** `Optional.orElseThrow()` không tham số có từ phiên bản Java nào?

**Đáp án:** **Java 10**.

### Câu 2
**Hỏi:** `Optional.of("x").orElseThrow()` trả gì?

**Đáp án:** `"x"`, không ném ngoại lệ.

### Câu 3
**Hỏi:** `Optional.<String>empty().orElseThrow()` ném ngoại lệ gì?

**Đáp án:** **`NoSuchElementException`** (unchecked).

### Câu 4
**Hỏi:** `Optional.of(null).orElseThrow()` ném `NoSuchElementException` không?

**Đáp án:** Không. `Optional.of(null)` ném **`NullPointerException` trước**.

### Câu 5
**Hỏi:** Làm cách nào có message `Unknown user: u9`?

**Đáp án:** `orElseThrow(() -> new IllegalArgumentException("Unknown user: u9"))`, hoặc domain-specific exception.

### Câu 6
**Hỏi:** Exception supplier có chạy nếu Optional present?

**Đáp án:** Không. Supplier chỉ được gọi khi empty.

### Câu 7
**Hỏi:** Muốn dùng `IOException` cần gì?

**Đáp án:** Dùng overload **có supplier**, caller khai báo `throws IOException` hoặc catch nó.

### Câu 8
**Hỏi:** Sau `Optional.of("   ").map(String::trim).filter(s -> !s.isEmpty())`, Optional present hay empty?

**Đáp án:** **Empty**, vì chuỗi rỗng sau trim bị filter loại.

### Câu 9
**Hỏi:** `OptionalInt.empty().orElseThrow()` trả 0 hay exception?

**Đáp án:** **`NoSuchElementException`**.

### Câu 10
**Hỏi:** Vì sao `optional.orElse(expensive())` vẫn có thể tính `expensive()` dù present?

**Đáp án:** Java đánh giá method argument trước lời gọi `orElse`; dùng `orElseGet(() -> expensive())` nếu cần lazy default.

### Câu 11
**Hỏi:** Tại sao chương trình mẫu in `streamCount=2`?

**Đáp án:** Có 2 IDs trả present Optional; `flatMap(Optional::stream)` bỏ qua empty.

### Câu 12
**Hỏi:** `orElseThrow()` thành công có nghĩa order không thể bị thay đổi cho tới khi ghi database?

**Đáp án:** Không. Cần transaction/concurrency control riêng.

### Câu 13
**Hỏi:** Một API tìm kiếm không có kết quả có nên luôn ném exception không?

**Đáp án:** Không. Nếu không thấy là kết quả hợp lệ, giữ empty hoặc dùng fallback được thiết kế đúng.

### Câu 14
**Hỏi:** Oracle API có đánh dấu `Optional.get()` deprecated không?

**Đáp án:** Không; nhưng ghi chú API **ưu tiên `orElseThrow()`**.

## 24. Checklist triển khai

- [ ] Nguồn dữ liệu trả `Optional<T>` rõ ràng, **không trả null Optional**.
- [ ] Dùng `ofNullable` đúng khi lấy dữ liệu có thể null.
- [ ] Phân biệt **missing hợp lệ** và **required-value violation** trước khi throw.
- [ ] `orElseThrow()` được đặt ở **đúng điểm cần giá trị**.
- [ ] Nếu yêu cầu mã lỗi/message, dùng **`orElseThrow(Supplier)`** và exception nghiệp vụ phù hợp.
- [ ] Checked exceptions được khai báo/catch theo compiler.
- [ ] Exception supplier không tạo side effects không cần thiết.
- [ ] Không ghi bí mật hoặc thông tin nhạy cảm vào message/log.
- [ ] Không dùng default vô nghĩa để che lỗi dữ liệu bắt buộc.
- [ ] `map`, `filter`, `flatMap` không làm mất context cần cho error handling.
- [ ] Test đầy đủ present, empty, filtered-empty, custom exception và lazy supplier.
- [ ] Không test thông điệp mặc định của `NoSuchElementException` như một hằng bất biến.
- [ ] Kiểm tra JDK target: no-arg có từ Java 10; `isEmpty()` là API Java 11.
- [ ] Không nhầm `OptionalInt.empty()` với số 0 hợp lệ.
- [ ] Với Stream, xác định rõ “bỏ qua missing” hay “mọi phần tử bắt buộc”.
- [ ] Controller/framework có exception mapping theo API contract.
- [ ] Nếu nguồn dữ liệu có thể đổi, dùng transaction/locking/versioning chứ không dựa vào `orElseThrow`.
- [ ] Không dựa trên object identity của Optional hoặc dùng Optional làm monitor.

## 25. Tóm tắt và nguồn tài liệu hiện hành

**Hành vi cốt lõi:** `Optional.orElseThrow()` **trả `T` nếu present**, còn nếu **empty** thì **ném `NoSuchElementException`**. Overload không tham số có từ **Java 10** và tiếp tục được hỗ trợ trong JDK hiện hành.

Phân biệt nhanh:

- `get()`: cùng hành vi nhưng tên ít diễn đạt intent hơn; **chưa bị deprecated**.
- `orElseThrow(Supplier)`: trả `T` hoặc ném lỗi tự chọn, kể cả checked exception.
- `orElse(T)`: trả default, không phải biểu diễn invariant violation.
- `orElseGet(Supplier)`: tạo default lazily khi empty.
- `map/filter/flatMap`: tiếp tục xử lý khả năng có/không có giá trị trước khi chốt.
- `OptionalInt/Long/Double`: hỗ trợ no-arg `orElseThrow()` từ Java 10.

Tài liệu chính thức còn áp dụng:

1. [Oracle JDK 25 — Optional](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html): `Since: 10` của no-arg, exception và ghi chú `get()`.
2. [Oracle JDK 26 — Optional](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Optional.html): tiếp tục hỗ trợ API.
3. [Oracle JDK 17 — Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): API phù hợp JDK LTS.
4. [Oracle JDK 25 — OptionalInt](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalInt.html).
5. [Oracle JDK 25 — OptionalLong](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalLong.html).
6. [Oracle JDK 25 — OptionalDouble](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalDouble.html).
7. [Oracle JDK 25 — NoSuchElementException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NoSuchElementException.html).
8. [Oracle JDK 25 — Stream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html).
9. [Oracle JDK 25 — Supplier](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Supplier.html).

**Kết luận:** Sức mạnh thực tế của `orElseThrow()` không phải đơn thuần viết ngắn hơn `get()`; nó giúp đánh dấu **ranh giới nơi dữ liệu là bắt buộc**. Hãy giữ Optional ở nơi absence hợp lệ, chỉ trích xuất khi nghiệp vụ đã quyết định, dùng exception tùy chỉnh khi cần ngữ cảnh, và kiểm thử rõ cả nhánh thành công lẫn nhánh thiếu giá trị.
