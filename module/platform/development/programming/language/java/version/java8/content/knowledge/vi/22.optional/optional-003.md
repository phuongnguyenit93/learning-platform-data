# Optional: isPresent, ifPresent và truy cập giá trị an toàn trong Java

`Optional<T>` trong `java.util` đại diện cho một kết quả **có thể chứa một giá trị khác `null` hoặc không có giá trị**. Nó giúp phương thức trả về nói rõ rằng việc tìm kiếm/đọc dữ liệu có thể không thành công, thay vì buộc nơi gọi tự đoán từ một giá trị `null`. Hai phương thức trọng tâm của bài là `isPresent()` (kiểm tra có giá trị) và `ifPresent(...)` (thực hiện hành động khi có giá trị). Tuy nhiên, “truy cập giá trị” cần lựa chọn đúng giữa `get()`, `orElse(...)`, `orElseGet(...)`, `orElseThrow(...)` và các phép biến đổi `map`/`flatMap`.

Tất cả thao tác cơ bản của `Optional` được giới thiệu từ **Java 8** và **vẫn được hỗ trợ trong các JDK hiện đại**. Bài cũng ghi rõ các phương thức bổ sung sau Java 8 như `ifPresentOrElse`, `isEmpty` và `orElseThrow()` không tham số; không nhầm API xuất hiện sau với API đã có ở Java 8.

## 1. Hiểu ba trạng thái dễ bị nhầm

`Optional<T>` chỉ có hai khả năng hợp lệ:

- **Có giá trị**: `Optional.of("Java")`, `Optional.ofNullable("Java")`. Khi ấy `isPresent() == true`.
- **Không có giá trị**: `Optional.empty()`, `Optional.ofNullable(null)`. Khi ấy `isPresent() == false`.

**Không có trạng thái “Optional chứa null”.** `Optional.of(null)` ném `NullPointerException` ngay khi tạo; `ofNullable(null)` trả đối tượng Optional rỗng. Và **chính biến kiểu `Optional<T>` không nên bằng null**: nếu có khả năng thiếu kết quả, trả `Optional.empty()`.

~~~java
Optional<String> present = Optional.of("Java");
Optional<String> absent = Optional.empty();
Optional<String> fromNullable = Optional.ofNullable(null);

System.out.println(present.isPresent());       // true
System.out.println(absent.isPresent());        // false
System.out.println(fromNullable.isPresent());  // false
~~~

Đây là đoạn **minh họa**; thêm `import java.util.Optional;` nếu đưa vào lớp chạy riêng. Tránh kiểm tra `optional == Optional.empty()`: API không cam kết `Optional.empty()` là đối tượng singleton. Muốn xem có giá trị, dùng `isPresent()`; muốn so sánh hai Optional về ngữ nghĩa, dùng `equals(...)` khi cần.

### Vì sao phương thức nên trả Optional?

Giả sử một hàm `findUserById(7)` trả về user nếu tìm thấy và rỗng nếu không. Ký hiệu `Optional<User>` giúp nơi gọi nhìn thấy khả năng thiếu dữ liệu ngay từ kiểu trả về:

~~~java
Optional<User> user = findUserById(id);
~~~

Đây là **mã minh họa**, giả sử lớp `User`, biến `id` và phương thức `findUserById` được định nghĩa. Khi đọc, người gọi có thể kiểm tra, thực hiện hành động khi có, chọn fallback hoặc ném lỗi theo chính sách nghiệp vụ. Ngược lại, khai báo `User findUserById(...)` nhưng đôi khi trả null dễ dẫn tới `NullPointerException` ở chỗ sử dụng.

`Optional` chủ yếu được thiết kế làm **kiểu trả về khi sự vắng mặt có ý nghĩa**. Không nên đưa Optional vào mọi field, tham số, entity hay DTO một cách máy móc; cân nhắc hợp đồng API, framework serialization và mô hình dữ liệu cụ thể.

## 2. `isPresent()`: kiểm tra trước khi truy cập

Chữ ký:

~~~java
boolean isPresent()
~~~

Trả `true` nếu Optional chứa giá trị khác null; trả `false` nếu rỗng. Cách viết có điều kiện hợp lệ:

~~~java
Optional<String> name = Optional.ofNullable(inputName);
if (name.isPresent()) {
    String actual = name.get();
    System.out.println(actual);
} else {
    System.out.println("Không có tên");
}
~~~

Đây là **đoạn minh họa**: `inputName` là biến của chương trình bên ngoài. Trong nhánh `if`, `get()` an toàn **với chính đối tượng Optional đã kiểm tra**. Nhưng lặp mẫu `if (x.isPresent()) x.get()` ở nhiều nơi dễ tạo mã dài và một lỗi bỏ quên nhánh rỗng có thể gây ngoại lệ.

**Quy tắc:** dùng `isPresent()` khi việc kiểm tra nhánh là rõ nhất, ví dụ kiểm tra điều kiện tồn tại hoặc xử lý hai luồng nghiệp vụ khác nhau; **không bắt buộc kiểm tra rồi `get()`** nếu `ifPresent`, `map` hoặc `orElseThrow` biểu đạt ý định tốt hơn.

### Khác nhau giữa `isPresent()` và `isEmpty()`

- `isPresent()`: từ **Java 8**, true khi có giá trị.
- `isEmpty()`: từ **Java 11**, true khi **không** có giá trị.

Hai cách này tương đương logic:

~~~java
boolean missing1 = !optional.isPresent(); // Java 8+
boolean missing2 = optional.isEmpty();     // Java 11+
~~~

Đây là đoạn minh họa, `optional` là đối tượng `Optional<?>` đã được định nghĩa. Với dự án đặt `--release 8`, không dùng `isEmpty()` vì API này chưa tồn tại ở Java 8. Không có nghĩa `isPresent()` đã lỗi thời; cả hai vẫn được hỗ trợ.

## 3. `ifPresent(Consumer<? super T>)`: làm việc khi có giá trị

Chữ ký:

~~~java
void ifPresent(Consumer<? super T> action)
~~~

`ifPresent` **chỉ gọi `action.accept(value)` khi có giá trị**, và không gọi gì khi rỗng. Nó trả về `void`, **không trả boolean và không trả lại Optional**.

~~~java
Optional.of("Linh").ifPresent(
    name -> System.out.println("Xin chào " + name)
);

Optional.<String>empty().ifPresent(
    name -> System.out.println("Không xuất hiện")
);
~~~

Chỉ dòng `Xin chào Linh` được in. Action dành cho trường hợp có giá trị; nếu không có giá trị, `ifPresent` không tự chạy nhánh `else`.

**Khi nên dùng:** hành động đơn giản cần thực hiện khi tìm thấy kết quả, ví dụ ghi log, cập nhật một giao diện, gửi thông báo trong một luồng nghiệp vụ phù hợp. Nếu mục tiêu là **lấy một giá trị mới**, `ifPresent` với biến ngoài thường kém rõ ràng hơn `map` hoặc `orElse`.

~~~java
// Cách diễn đạt tốt hơn khi cần kết quả String:
String upper = Optional.of("Java")
    .map(String::toUpperCase)
    .orElse("UNKNOWN");
~~~

Thay vì:

~~~java
// Phản ví dụ về thiết kế: biến mutable ngoài chỉ để lấy một String.
StringBuilder result = new StringBuilder();
optional.ifPresent(value -> result.append(value.toUpperCase()));
~~~

Đoạn phản ví dụ giả sử `optional` đã tồn tại; không tự chạy độc lập. Nó không nhất thiết sai ở luồng tuần tự, nhưng tạo trạng thái ngoài không cần thiết và khó mở rộng/kiểm thử. `map` phù hợp hơn với **biến đổi giá trị**; `ifPresent` phù hợp hơn với **thực hiện hành động**.

**Nếu action ném ngoại lệ**, `ifPresent` không tự nuốt ngoại lệ: ngoại lệ truyền ra nơi gọi. Đừng giả định `ifPresent` tự xử lý lỗi của side effect.

### Cần cả hai nhánh: `ifPresentOrElse` (Java 9+)

Từ Java 9 có:

~~~java
optional.ifPresentOrElse(
    value -> System.out.println("Có: " + value),
    () -> System.out.println("Không có dữ liệu")
);
~~~

Đoạn minh họa này cần `optional` đã định nghĩa. `ifPresentOrElse` nhận **Consumer** cho nhánh có giá trị và **Runnable** cho nhánh rỗng, vẫn trả `void`.

**Nếu ứng dụng phải tương thích Java 8**, dùng `if (optional.isPresent()) { ... } else { ... }` hoặc cơ chế phù hợp khác, vì `ifPresentOrElse` chưa tồn tại ở Java 8. Đừng nhầm nó với `orElse(...)`: `ifPresentOrElse` thực hiện hành động; `orElse` **trả về một giá trị**.

## 4. `get()` và truy cập trực tiếp: hợp lệ nhưng dễ lỗi

Chữ ký Java 8:

~~~java
T get()
~~~

Nếu có giá trị, `get()` trả ra `T`. Nếu rỗng, nó ném **`NoSuchElementException`**.

~~~java
Optional<String> empty = Optional.empty();
empty.get(); // ném NoSuchElementException
~~~

Điều này **không phải `NullPointerException`**, vì biến `empty` bản thân nó là một Optional hợp lệ. Lỗi xuất phát từ việc yêu cầu lấy một phần tử không tồn tại.

**Khuyến nghị cho mã mới:** không dùng `get()` vô điều kiện. Khi bắt buộc phải có giá trị, dùng `orElseThrow(...)` để nói rõ ngoại lệ nghiệp vụ, hoặc `orElseThrow()` (Java 10+) để ném `NoSuchElementException`. Tài liệu API hiện hành cũng ghi `orElseThrow()` là lựa chọn được ưu tiên hơn `get()`. `get()` chưa bị xóa và vẫn hoạt động; điều nên tránh là **gọi mà không xử lý khả năng rỗng**.

### `orElseThrow(Supplier)` — có từ Java 8

~~~java
User required = findUserById(id).orElseThrow(
    () -> new IllegalArgumentException("Không tìm thấy user id=" + id)
);
~~~

Đây là đoạn minh họa; giả sử `User`, `findUserById` và `id` tồn tại. Khi có user, trả user. Khi rỗng, supplier tạo ngoại lệ. Chọn ngoại lệ phù hợp tầng ứng dụng (ví dụ `IllegalArgumentException`/exception nghiệp vụ theo hợp đồng), không luôn ném một loại chung cho mọi trường hợp.

### `orElseThrow()` — bổ sung từ Java 10

~~~java
User required = findUserById(id).orElseThrow();
~~~

Không có giá trị sẽ ném `NoSuchElementException`, tương tự `get()` nhưng cách đặt tên thể hiện rõ nhánh lỗi. **Chỉ dùng trong dự án Java 10+**; dự án Java 8 dùng overload nhận supplier hoặc kiểm tra một cách có chủ ý.

### So sánh lựa chọn truy cập

| Nhu cầu | API thích hợp | Khi Optional rỗng |
| --- | --- | --- |
| Chỉ muốn kiểm tra có giá trị | `isPresent()` | Trả `false` |
| Chạy một hành động nếu có | `ifPresent(action)` | Không làm gì |
| Chạy một trong hai hành động | `ifPresentOrElse(action, emptyAction)` (9+) | Gọi `emptyAction` |
| Trả giá trị mặc định đã có sẵn | `orElse(defaultValue)` | Trả `defaultValue` |
| Tạo giá trị mặc định khi cần | `orElseGet(supplier)` | Gọi supplier và trả kết quả |
| Bắt buộc có giá trị hoặc ném lỗi nghiệp vụ | `orElseThrow(exceptionSupplier)` | Tạo và ném ngoại lệ |
| Bắt buộc có giá trị hoặc `NoSuchElementException` | `orElseThrow()` (10+) | Ném `NoSuchElementException` |
| Lấy trực tiếp, người gọi tự đảm bảo tồn tại | `get()` | Ném `NoSuchElementException` |
| Biến đổi giá trị khi có | `map(mapper)` | Trả Optional rỗng |

## 5. `orElse` và `orElseGet`: khác biệt rất quan trọng về thời điểm đánh giá

Cả hai phương thức cùng mục đích nhận một giá trị `T` cuối cùng, nhưng **khác ở lúc tính fallback**.

~~~java
T value1 = optional.orElse(defaultValue);          // đối số đã được đánh giá
T value2 = optional.orElseGet(() -> createValue()); // supplier chỉ chạy khi rỗng
~~~

Đây là mã minh họa; `optional`, `defaultValue`, `createValue` là ký hiệu từ ứng dụng.

### `orElse(...)` đánh giá đối số ngay trước lời gọi

~~~java
String name = Optional.of("Linh")
    .orElse(expensiveFallback());
~~~

Vì Java đánh giá đối số trước khi gọi phương thức, `expensiveFallback()` vẫn **được thực thi dù Optional đã có `"Linh"`**; kết quả trả về vẫn là `"Linh"`. Nếu fallback gọi mạng, truy vấn DB, ghi log hoặc tính toán nặng, nó có thể gây chi phí không cần thiết và side effect không mong muốn.

### `orElseGet(...)` chỉ gọi supplier khi rỗng

~~~java
String name = Optional.of("Linh")
    .orElseGet(() -> expensiveFallback());
~~~

Trong ví dụ này supplier **không được gọi**. Khi Optional rỗng, nó mới gọi `expensiveFallback()` và dùng giá trị trả về.

**Chọn thế nào?** Nếu fallback là hằng hay đối tượng có sẵn, `orElse("UNKNOWN")` gọn và rõ. Nếu fallback cần tính toán, cấp phát lớn hoặc I/O, `orElseGet(() -> ...)` tránh làm việc khi không cần. Không có căn cứ để tuyên bố `orElseGet` luôn nhanh hơn; chọn theo chi phí và ngữ nghĩa, không dựa vào tên phương thức.

**Cẩn thận với null:** `orElse(null)` được API cho phép, nhưng có thể đẩy rủi ro `NullPointerException` sang nơi gọi và làm mất ý nghĩa Optional. Chỉ dùng khi đang tương tác với API legacy thật sự yêu cầu null; nếu có thể, giữ biểu diễn rõ ràng thay vì chuyển ngược về null.

## 6. `map`, `flatMap`, `filter`: tránh phải “mở hộp” quá sớm

Khi mục tiêu là đọc một **thuộc tính** của giá trị Optional, thường không cần `get()`:

~~~java
Optional<User> found = findUserById(7);

String displayName = found
    .map(User::getName)
    .orElse("Ẩn danh");
~~~

Đây là đoạn minh họa; `User` và `findUserById` được định nghĩa trong ví dụ hoàn chỉnh ở phần 8. Nếu không tìm thấy user, `map` không gọi `getName()`, Optional rỗng được chuyển tiếp đến `orElse`.

### `map(mapper)`

- Có giá trị: áp dụng mapper rồi bọc kết quả vào Optional.
- Rỗng: bỏ qua mapper và trả Optional rỗng.
- Nếu mapper trả **null**, `Optional.map` chuyển kết quả thành **`Optional.empty()`**, thay vì tạo Optional chứa null.

~~~java
Optional<String> result = Optional.of("x")
    .map(s -> (String) null);
// result.isPresent() == false
~~~

Có thể dùng map để biến chuỗi tên thành chữ hoa, lấy thuộc tính, hoặc tính toán một giá trị mới.

### `flatMap(mapper)`

Nếu mapper **đã trả một Optional**, dùng `flatMap` để tránh `Optional<Optional<T>>`:

~~~java
Optional<String> email = findUserById(7)
    .flatMap(User::email);
~~~

Đoạn minh họa này dùng `User::email` trả `Optional<String>`. Nếu viết `map(User::email)` sẽ được `Optional<Optional<String>>`, thường bất tiện. Khác với `map`, **mapper của `flatMap` trả null sẽ ném `NullPointerException`**; phải trả Optional hợp lệ kể cả khi rỗng.

### `filter(predicate)`

~~~java
Optional<User> matched = findUserById(7)
    .filter(user -> user.getId() > 0);
~~~

Chỉ giữ user nếu predicate true. Với Optional rỗng, predicate không chạy. Với giá trị không đạt điều kiện, kết quả chuyển thành Optional rỗng. Đây là cách diễn đạt gọn khi yêu cầu lọc một kết quả có thể vắng mặt, không cần if lồng nhiều tầng.

**Mô hình dễ đọc:** nhận `Optional<T>` → `filter/map/flatMap` nếu cần → cuối cùng chọn `ifPresent`, `orElse`, `orElseGet` hoặc `orElseThrow` đúng hành vi nghiệp vụ.

## 7. Ví dụ Java hoàn chỉnh: có/rỗng, callback và truy cập an toàn

Lưu mã sau vào tệp **`OptionalAccessDemo.java`**. Mọi Optional API trong chương trình chính đều đã có từ Java 8; có thể biên dịch và chạy bằng JDK 17+.

~~~java
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

public class OptionalAccessDemo {

    static final class User {
        private final int id;
        private final String name;
        private final String email;

        User(int id, String name, String email) {
            this.id = id;
            this.name = name;
            this.email = email;
        }

        int getId() {
            return id;
        }

        String getName() {
            return name;
        }

        Optional<String> email() {
            return Optional.ofNullable(email);
        }
    }

    static Optional<User> findUserById(int id) {
        if (id == 7) {
            return Optional.of(new User(
                    7, "Linh", "linh@example.com"));
        }
        if (id == 8) {
            return Optional.of(new User(
                    8, "Minh", null));
        }
        return Optional.empty();
    }

    static String buildFallback(AtomicInteger calls) {
        calls.incrementAndGet();
        return "Guest";
    }

    public static void main(String[] args) {
        Optional<User> found = findUserById(7);
        Optional<User> missing = findUserById(99);
        Optional<User> noEmail = findUserById(8);

        System.out.println("found.isPresent=" + found.isPresent());
        System.out.println("missing.isPresent=" + missing.isPresent());

        found.ifPresent(user ->
                System.out.println("ifPresent=" + user.getName()));
        missing.ifPresent(user ->
                System.out.println("not printed"));

        // get() chỉ dùng sau khi kiểm tra đúng Optional.
        if (found.isPresent()) {
            System.out.println("checkedGet="
                    + found.get().getName());
        }

        String name = found.map(User::getName)
                .orElse("Anonymous");
        String absentName = missing.map(User::getName)
                .orElse("Anonymous");
        System.out.println("name=" + name);
        System.out.println("absentName=" + absentName);

        AtomicInteger fallbackCalls = new AtomicInteger();
        String eager = found.map(User::getName).orElse(
                buildFallback(fallbackCalls));
        String lazyPresent = found.map(User::getName).orElseGet(
                () -> buildFallback(fallbackCalls));
        String lazyMissing = missing.map(User::getName).orElseGet(
                () -> buildFallback(fallbackCalls));

        System.out.println("eager=" + eager
                + ", lazyPresent=" + lazyPresent
                + ", lazyMissing=" + lazyMissing);
        System.out.println("fallbackCalls="
                + fallbackCalls.get());

        System.out.println("email=" + found.flatMap(User::email)
                .orElse("not supplied"));
        System.out.println("noEmail=" + noEmail.flatMap(User::email)
                .orElse("not supplied"));
        System.out.println("nullableEmpty="
                + Optional.ofNullable(null).isPresent());

        System.out.println("positiveId="
                + found.filter(u -> u.getId() > 0).isPresent());

        try {
            missing.get();
        } catch (NoSuchElementException ex) {
            System.out.println("emptyGet=NoSuchElementException");
        }

        try {
            missing.orElseThrow(
                    () -> new IllegalStateException("user 99 missing"));
        } catch (IllegalStateException ex) {
            System.out.println("customError=" + ex.getMessage());
        }

        OptionalInt minimum = IntStream.of(10, 4, 8).min();
        OptionalInt noMinimum = IntStream.empty().min();
        System.out.println("primitiveMin=" + minimum.orElse(-1));
        System.out.println("emptyPrimitiveMin="
                + noMinimum.orElse(-1));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 OptionalAccessDemo.java
java OptionalAccessDemo
~~~

Đầu ra đầy đủ:

~~~text
found.isPresent=true
missing.isPresent=false
ifPresent=Linh
checkedGet=Linh
name=Linh
absentName=Anonymous
eager=Linh, lazyPresent=Linh, lazyMissing=Guest
fallbackCalls=2
email=linh@example.com
noEmail=not supplied
nullableEmpty=false
positiveId=true
emptyGet=NoSuchElementException
customError=user 99 missing
primitiveMin=4
emptyPrimitiveMin=-1
~~~

**Giải thích từng điểm quan trọng:**

1. `found` chứa user; `missing` rỗng. `isPresent()` phản ánh đúng hai trường hợp.
2. `missing.ifPresent(...)` không in dòng `not printed`; đó là hành vi được thiết kế, không phải bug.
3. `get()` chỉ được gọi an toàn trong nhánh `found.isPresent()`. `missing.get()` được thử riêng trong `try/catch` để thấy kiểu ngoại lệ chính xác.
4. `map(User::getName).orElse("Anonymous")` trả tên thật hoặc fallback, không cần lộ user object ra nơi gọi.
5. `buildFallback` được gọi một lần bởi `orElse(buildFallback(...))` **dù đã tìm thấy Linh**; `orElseGet` với found không gọi supplier, với missing thì gọi một lần. Tổng `fallbackCalls=2`.
6. `flatMap(User::email)` phù hợp vì phương thức `email()` đã trả `Optional<String>`. User `Minh` tồn tại nhưng email không có, nên kết quả email rỗng và fallback hiển thị.
7. `Optional.ofNullable(null)` trả rỗng. `filter` chỉ giữ user khi điều kiện đúng.
8. `orElseThrow(() -> new IllegalStateException(...))` cho lỗi nghiệp vụ rõ hơn; không phải mọi trường hợp thiếu user đều có chính sách ném lỗi giống nhau.
9. `OptionalInt` là dạng cho giá trị `int` nguyên thủy, thường đến từ `IntStream.min()`; `orElse(-1)` chỉ có ý nghĩa nếu `-1` là giá trị mặc định được nghiệp vụ chấp nhận. Không giả định sentinel `-1` luôn an toàn.

## 8. API bổ sung ở các phiên bản sau Java 8

Những phương thức sau **vẫn áp dụng hiện nay** nhưng cần phân biệt mức JDK tối thiểu:

| Phương thức | Xuất hiện từ | Mục đích |
| --- | --- | --- |
| `isPresent()`, `ifPresent(...)`, `get()` | Java 8 | Kiểm tra, chạy callback và lấy trực tiếp |
| `orElse(...)`, `orElseGet(...)`, `orElseThrow(Supplier)` | Java 8 | Fallback hoặc ném ngoại lệ có chủ ý |
| `map`, `flatMap`, `filter` | Java 8 | Biến đổi hoặc lọc giá trị có thể vắng mặt |
| `ifPresentOrElse(action, emptyAction)` | Java 9 | Xử lý cả hai nhánh bằng callbacks |
| `or(supplier)` | Java 9 | Chọn một Optional khác khi rỗng |
| `stream()` | Java 9 | Đưa 0 hoặc 1 giá trị của Optional thành Stream |
| `orElseThrow()` không tham số | Java 10 | Lấy giá trị hoặc ném `NoSuchElementException` |
| `isEmpty()` | Java 11 | Kiểm tra nhánh rỗng trực tiếp |

Ví dụ dưới đây yêu cầu **Java 11+** (trong đó `ifPresentOrElse` có từ 9, `orElseThrow()` từ 10, `isEmpty` từ 11):

~~~java
Optional<String> value = Optional.of("Java");

value.ifPresentOrElse(
        s -> System.out.println("Có: " + s),
        () -> System.out.println("Rỗng")
);

boolean empty = value.isEmpty();  // false
String required = value.orElseThrow(); // "Java"
~~~

Đây là **mã minh họa**, cần import `java.util.Optional` và đặt trong một phương thức. Nếu phải chạy với `--release 8`, giữ các API Java 8 ở ví dụ hoàn chỉnh; không nâng phiên bản chỉ vì muốn viết ngắn hơn.

Nếu có `Stream<Optional<T>>` ở Java 9+, có thể dùng `flatMap(Optional::stream)` để bỏ các Optional rỗng một cách gọn gàng:

~~~java
List<String> actual = Stream.of(
        Optional.of("A"),
        Optional.<String>empty(),
        Optional.of("B"))
    .flatMap(Optional::stream)
    .collect(Collectors.toList());
// actual = [A, B]
~~~

Đây là **đoạn minh họa**, cần import `List`, `Stream`, `Optional` và `Collectors`. Với Java 8, có thể thay bằng `filter(Optional::isPresent).map(Optional::get)` nếu hợp đồng cần làm thế, nhưng phần lớn trường hợp nên thiết kế pipeline để tránh tạo Stream chứa Optional không cần thiết.

## 9. Optional cho primitive: `OptionalInt`, `OptionalLong`, `OptionalDouble`

`IntStream.min()`, `LongStream.max()` hoặc `DoubleStream.average()` có thể trả một phiên bản Optional cho primitive:

~~~java
OptionalInt min = IntStream.of(8, 3, 5).min();
int answer = min.orElse(0); // 3

OptionalInt missing = IntStream.empty().min();
// missing.isPresent() == false
~~~

Bên cạnh `isPresent()` và `ifPresent(...)`, các lớp primitive có `getAsInt()`, `getAsLong()` hoặc `getAsDouble()` thay cho `get()`. Các phương thức lấy trực tiếp này cũng ném `NoSuchElementException` khi rỗng; hiện nay các API primitive cũng có `orElseThrow()` như một cách diễn đạt rõ yêu cầu bắt buộc có giá trị.

Hãy xử lý **stream rỗng** trước khi chọn default. Ví dụ, nếu đang tìm nhiệt độ tối thiểu, `0` có thể chính là giá trị hợp lệ; dùng `orElse(0)` sẽ khiến việc “không có dữ liệu” bị hiểu sai nếu chương trình không biểu diễn sự khác biệt ở nơi khác.

`OptionalInt` giúp tránh một số boxing/unboxing không cần thiết so với `Optional<Integer>` trong các pipeline nguyên thủy. Tuy nhiên, không cần chuyển tất cả kiểu trả về thành primitive Optional nếu mô hình nghiệp vụ thực chất cần object.

## 10. Những lỗi phổ biến và cách sửa

### Lỗi 1 — `get()` không kiểm tra

~~~java
// Sai khi dữ liệu có thể rỗng:
String name = maybeName.get();
~~~

Nếu `maybeName` rỗng, `NoSuchElementException` xảy ra. Nếu thiếu tên là trạng thái bình thường, dùng `orElse("Ẩn danh")`; nếu là vi phạm nghiệp vụ, dùng `orElseThrow(() -> new ... )`; nếu chỉ cần callback, dùng `ifPresent(...)`.

### Lỗi 2 — Viết Optional nhưng bản thân Optional lại null

~~~java
// Sai về thiết kế API:
Optional<String> name = null;
name.isPresent(); // NullPointerException
~~~

Hãy tạo `Optional.empty()` cho trường hợp không có dữ liệu. `Optional<T>` đã biểu diễn khả năng vắng mặt, không cần thêm “Optional chính nó null”.

### Lỗi 3 — Dùng `Optional.of(nullableValue)`

~~~java
// value có thể null: Optional.of(value) ném NullPointerException.
Optional<String> result = Optional.ofNullable(value);
~~~

Đây là mã minh họa, `value` là biến ngoài. `ofNullable` đúng khi null thật sự có nghĩa “không có dữ liệu”. Nếu null biểu thị bug không được phép, `Optional.of(value)` ném lỗi sớm có thể hợp lý hơn; không tự động đổi mọi `of` sang `ofNullable` để che lỗi đầu vào.

### Lỗi 4 — Dùng `ifPresent` để lấy giá trị, tạo biến ngoài

~~~java
// Khó đọc và không cần thiết:
String[] holder = new String[1];
maybeName.ifPresent(x -> holder[0] = x.toUpperCase());
~~~

Nếu cần kết quả, viết `maybeName.map(String::toUpperCase).orElse("UNKNOWN")`. `ifPresent` là terminal action trên Optional, **không có kết quả trả về**.

### Lỗi 5 — Nhầm `orElse` là lazy

~~~java
String result = maybeName.orElse(fetchFromDatabase());
~~~

`fetchFromDatabase()` chạy **ngay khi đánh giá đối số**, bất kể có giá trị hay không. Chỉ khi chính việc tính fallback phải làm lúc thiếu mới nên viết `maybeName.orElseGet(() -> fetchFromDatabase())`. Cũng cần cân nhắc lỗi, timeout và side effect của việc gọi DB; Optional không tự quản lý chúng.

### Lỗi 6 — Nhầm `map` với `flatMap`

`map(User::email)` cho `Optional<Optional<String>>` nếu `email()` đã trả Optional. `flatMap(User::email)` cho `Optional<String>`; lưu ý mapper của `flatMap` không được trả null.

### Lỗi 7 — Tưởng Optional xử lý tất cả ngoại lệ

`Optional.empty()` biểu thị vắng dữ liệu theo hợp đồng, **không phải hộp chứa lỗi**. Nếu hệ thống cần phân biệt “không tìm thấy”, “kết nối database thất bại” và “đầu vào không hợp lệ”, hãy để lỗi thật được ném/biểu diễn đúng thay vì biến mọi ngoại lệ thành `Optional.empty()`.

### Lỗi 8 — So sánh bằng `==` hoặc dùng Optional làm khóa đồng bộ

`Optional` là **value-based class**. Không phụ thuộc identity của đối tượng để kiểm tra rỗng, không dùng `synchronized(optional)`. Khi cần so hai Optional theo giá trị, dùng `equals`; khi cần kiểm tra hiện diện, dùng `isPresent`/`isEmpty`.

### Lỗi 9 — Đưa Optional vào mọi tham số/field bất kể ngữ cảnh

Khi một method có `Optional<User>` làm tham số hoặc entity có field Optional, có thể khiến caller/framework xử lý phức tạp hơn. API chính thức định hướng Optional chủ yếu cho **return type** biểu diễn việc thiếu kết quả. Hãy chọn thiết kế phù hợp các lớp persistence, JSON và giao diện bên ngoài thay vì bao mọi giá trị trong Optional.

### Lỗi 10 — Không xác định nghĩa nghiệp vụ của fallback

`orElse(0)`, `orElse("")` hay `orElse(null)` có thể hợp lệ về cú pháp nhưng không phải luôn đúng nghĩa: 0 có thể là số thực, chuỗi rỗng có thể là giá trị thật. Hãy quyết định liệu thiếu dữ liệu nên dùng default, bỏ qua hành động, hay báo lỗi. Optional chỉ cung cấp phương tiện diễn đạt, không thay nghiệp vụ lựa chọn.

## 11. Tình huống áp dụng thực tế

### Tra cứu user không bắt buộc tồn tại

~~~java
String label = findUserById(id)
    .map(User::getName)
    .orElse("Khách");
~~~

Thích hợp khi UI cho phép tên hiển thị dự phòng. Đoạn này là minh họa và giả định những định nghĩa trong ví dụ đầy đủ.

### Tra cứu user bắt buộc tồn tại

~~~java
User user = findUserById(id).orElseThrow(
    () -> new IllegalArgumentException("User không tồn tại: " + id)
);
~~~

Thích hợp khi thiếu user được xem là lỗi và phải chấm dứt thao tác. Chọn exception/HTTP status theo hợp đồng ứng dụng chứ không cứng nhắc một loại.

### Chỉ chạy tác vụ khi tìm thấy

~~~java
findUserById(id).ifPresent(
    user -> System.out.println("Đã tìm thấy " + user.getName())
);
~~~

Không cần viết nhánh `else` nếu không có gì phải làm khi vắng user.

### Có hai nhánh hành động ở Java 9+

~~~java
findUserById(id).ifPresentOrElse(
    user -> System.out.println("OK: " + user.getName()),
    () -> System.out.println("Không tìm thấy")
);
~~~

### Giữ tính lazy của fallback

~~~java
String label = findUserById(id)
    .map(User::getName)
    .orElseGet(() -> loadGuestNameFromConfiguration());
~~~

Đây là mã minh họa; `loadGuestNameFromConfiguration()` là phương thức của ứng dụng. Nó chỉ chạy khi Optional đã rỗng, giúp tránh tải cấu hình không cần thiết.

## 12. Checklist khi đọc hoặc viết Optional

1. **Biết Optional có thể rỗng:** `get()`/`getAsInt()` không kiểm tra sẽ ném `NoSuchElementException`.
2. **Muốn kiểm tra:** `isPresent()`; trên Java 11+ có thêm `isEmpty()`.
3. **Muốn thực hiện hành động:** `ifPresent(action)`; có cả hai nhánh và Java 9+ thì `ifPresentOrElse(action, emptyAction)`.
4. **Muốn lấy giá trị với default:** `orElse(value)` cho giá trị sẵn có; `orElseGet(supplier)` cho fallback cần tính khi rỗng.
5. **Muốn bắt buộc có kết quả:** `orElseThrow(supplier)` từ Java 8, hoặc `orElseThrow()` từ Java 10; chọn exception theo nghiệp vụ.
6. **Muốn biến đổi thuộc tính:** `map`; mapper đã trả Optional thì `flatMap`; lọc có điều kiện thì `filter`.
7. **Nguồn có thể null:** `ofNullable(value)`; `of(value)` dùng khi giá trị chắc chắn khác null.
8. **Tránh Optional tự nó null:** luôn trả `Optional.empty()` nếu thiếu.
9. **Đừng lẫn phiên bản API:** các method `isEmpty`, `ifPresentOrElse`, `orElseThrow()` và `stream()` không thuộc Java 8 gốc.
10. **Chọn theo ý nghĩa:** không phải mọi giá trị vắng mặt đều là lỗi, và default tùy tiện có thể làm mất thông tin nghiệp vụ.

**Ghi nhớ:** `isPresent()` là phép **kiểm tra**, `ifPresent(...)` là phép **thực thi hành động**, còn `get()` là phép **lấy trực tiếp có thể ném lỗi khi rỗng**. Khi cần một giá trị cuối cùng, ưu tiên `map`/`flatMap` rồi `orElse`, `orElseGet` hoặc `orElseThrow` cho ý định rõ ràng. Những nguyên tắc này vẫn đúng với Java hiện đại và không yêu cầu sử dụng API lỗi thời.

## Tài liệu chính thức

- [Oracle Java SE 25 — Optional<T>: isPresent, ifPresent, get, orElse, orElseGet và orElseThrow](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html)
- [Oracle Java SE 25 — OptionalInt](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalInt.html)
- [Oracle Java SE 25 — OptionalLong](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalLong.html)
- [Oracle Java SE 25 — OptionalDouble](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalDouble.html)
- [Oracle Java SE 25 — Stream: findFirst, findAny](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
