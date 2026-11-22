# Optional biểu diễn có hoặc không có kết quả trong Java

## 1. Mục tiêu bài học

Một phép tra cứu không phải lúc nào cũng tìm được dữ liệu: có thể không có người dùng với mã đã cho, không có email liên hệ, không có giá trị lớn nhất trong một tập rỗng. Nếu chỉ trả `null`, người gọi phải tự nhớ kiểm tra và dễ phát sinh `NullPointerException`.

**`java.util.Optional<T>`** là một kiểu **vỏ chứa có thể có hoặc không có một giá trị khác null**. Nó biểu diễn rõ hơn hợp đồng “**kết quả có thể vắng mặt**”:

- **Có kết quả (present):** `Optional` chứa một giá trị T khác null.
- **Không có kết quả (empty):** `Optional` không chứa giá trị.

Sau bài này, bạn có thể tạo Optional đúng cách, đọc và biến đổi giá trị mà không gọi `get()` mù quáng, kết hợp nhiều thao tác tra cứu bằng `map`/`flatMap`, dùng `orElse`/`orElseGet`/`orElseThrow`, làm việc với `Stream` và `OptionalInt`, thiết kế hợp đồng trả về hợp lý và nhận diện lỗi phổ biến.

## 2. Optional là gì, và không phải là gì?

`Optional<T>` là một final class thuộc `java.util`. Đây **không phải một T** và **không phải một collection chứa nhiều T**. Nó biểu diễn tối đa **một** giá trị T hoặc trạng thái rỗng.

Hình dung:

~~~text
Optional<User>
    |
    +-- present --> chứa User khác null
    |
    +-- empty ----> không có User
~~~

Một phương thức trả `Optional<User>` cho người gọi biết **phải xử lý tình huống không tìm thấy**. Ví dụ:

~~~java
Optional<User> findUserById(int id);
~~~

Đây chỉ là **chữ ký minh họa**, giả sử lớp `User` tồn tại; không phải chương trình Java độc lập.

Điều quan trọng:

- **Empty không nhất thiết là lỗi.** Ví dụ “không có kết quả tìm kiếm” có thể là tình huống hợp lệ.
- **Optional không tự mô tả lý do vắng mặt.** Không tìm thấy, không có quyền truy cập và database lỗi là ba tình huống khác nhau; không được tự động biến tất cả thành `Optional.empty()`.
- **Optional không thay thế mọi giá trị null trong toàn bộ ứng dụng.** Nó đặc biệt hữu ích ở **kiểu trả về** nơi vắng mặt là một kết quả được dự kiến.
- **Optional không bảo đảm object bên trong bất biến.** Nếu chứa một đối tượng mutable, các phương thức trên đối tượng đó vẫn có thể thay đổi trạng thái.
- **Optional không tự chạy bất đồng bộ.** Nó là đối tượng mô tả sự hiện diện của kết quả; khác với `Future`/`CompletableFuture` biểu diễn công việc có thể hoàn tất về sau.

### 2.1. Phân biệt empty, null và lỗi

| Tình huống | Cách biểu diễn thường phù hợp | Ý nghĩa |
| --- | --- | --- |
| Tìm user theo ID nhưng không tồn tại | `Optional.empty()` | Không có kết quả, có thể bình thường |
| Một API cũ trả null khi thiếu dữ liệu | `Optional.ofNullable(value)` tại ranh giới | Chuyển null thành empty |
| Người dùng nhập ID sai định dạng | Kết quả validation hoặc exception phù hợp | Đầu vào không hợp lệ |
| Database không kết nối được | Exception/kết quả lỗi có nguyên nhân | Thao tác thất bại, không đồng nghĩa user không tồn tại |
| Tìm giá trị lớn nhất trong stream rỗng | `OptionalInt.empty()` hoặc `Optional<T>.empty()` | Phép tổng hợp không có phần tử |

Vì `Optional` chỉ có hai trạng thái, khi ứng dụng cần lưu **lý do thất bại**, hãy tạo kiểu kết quả có trạng thái và thông tin lỗi hoặc ném exception đúng hợp đồng.

## 3. Tạo Optional: empty, of và ofNullable

Java cung cấp ba factory method cơ bản:

~~~java
Optional<String> none = Optional.empty();
Optional<String> known = Optional.of("Java");
Optional<String> maybe = Optional.ofNullable(null);
~~~

Kết quả:

- `none` là Optional rỗng.
- `known` chứa chuỗi `"Java"`.
- `maybe` là Optional rỗng vì đối số null.

### 3.1. Optional.of(value)

`Optional.of(value)` dùng khi **value chắc chắn khác null**. Nếu truyền null, nó **ném `NullPointerException` ngay tại lúc tạo**.

~~~java
String language = "Java";
Optional<String> result = Optional.of(language);

// Không làm thế khi giá trị có thể null:
// Optional<String> wrong = Optional.of(null);
~~~

Dùng `of` thể hiện kỳ vọng mạnh: null ở vị trí đó là sai hợp đồng, cần được phát hiện thay vì âm thầm coi là vắng mặt.

### 3.2. Optional.ofNullable(value)

`Optional.ofNullable(value)` dùng khi nguồn có thể trả null:

~~~java
String legacyValue = null;
Optional<String> result = Optional.ofNullable(legacyValue);

System.out.println(result.isEmpty()); // true
~~~

Đây là công cụ phù hợp để chuyển đổi từ API cũ có thể trả null sang phần xử lý dựa trên Optional. Nó **không tự kiểm tra nội dung** của chuỗi: `""` hoặc `"   "` vẫn là chuỗi **khác null** và vì vậy vẫn được chứa.

### 3.3. Optional.empty()

`Optional.empty()` nói rõ “không có giá trị”. Khi trả về từ một phương thức, hãy dùng:

~~~java
static Optional<String> findNickname(boolean available) {
    return available ? Optional.of("Lan") : Optional.empty();
}
~~~

Đây là phương thức minh họa, cần đặt trong một lớp và import `Optional`.

**Không nên trả về `null` từ phương thức có kiểu trả về `Optional<T>`**: khi đó người gọi vẫn phải kiểm tra null của chính Optional, đánh mất phần lớn lợi ích hợp đồng.

## 4. Kiểm tra trạng thái có hoặc không

Các phương thức:

- **`isPresent()`**: true nếu chứa giá trị.
- **`isEmpty()`**: true nếu không chứa giá trị (Java 11+).
- **`ifPresent(Consumer<? super T>)`**: chạy hành động nếu có giá trị.
- **`ifPresentOrElse(Consumer<? super T>, Runnable)`**: chạy một trong hai nhánh (Java 9+).

~~~java
Optional<String> name = Optional.of("An");

System.out.println(name.isPresent()); // true
System.out.println(name.isEmpty());   // false

name.ifPresent(value -> System.out.println("Hello " + value));
~~~

`isPresent()` là một phép kiểm tra, **không lấy ra giá trị**. Có thể viết `if (opt.isPresent()) { use(opt.get()); }`, nhưng khi chỉ cần xử lý kết quả, `ifPresent`, `map`, `flatMap` hoặc `orElse...` thường làm ý định rõ hơn và tránh việc rải `get()` trong code.

### 4.1. Hai nhánh có ý nghĩa nghiệp vụ

~~~java
Optional<String> nickname = Optional.empty();

nickname.ifPresentOrElse(
        value -> System.out.println("Name: " + value),
        () -> System.out.println("No nickname")
);
~~~

Kết quả: `No nickname`. Đây là ví dụ có side effect in console. Với hàm tính toán cần **trả một giá trị**, ưu tiên `map` và một phương thức lấy fallback phù hợp thay vì viết vào biến mutable bên ngoài lambda.

### 4.2. Optional không tạo ra giá trị mới khi chỉ kiểm tra

Một sai lầm là dùng `isPresent` ở nhiều nơi và thực hiện lại cùng một phép tra cứu:

~~~java
// Không nên truy vấn lại nhiều lần chỉ để kiểm tra rồi đọc.
// if (repository.find(id).isPresent()) {
//     return repository.find(id).get();
// }
~~~

Giữa hai lần gọi, dữ liệu có thể thay đổi; đồng thời còn tốn chi phí truy vấn. Hãy **lấy một Optional**, xử lý chính giá trị đó và quyết định cách phản hồi.

## 5. Lấy giá trị an toàn: orElse, orElseGet, orElseThrow

### 5.1. orElse(defaultValue)

`orElse` trả giá trị có sẵn, hoặc dùng giá trị mặc định khi Optional rỗng:

~~~java
String display = Optional.<String>empty()
        .orElse("Khách vãng lai"); // "Khách vãng lai"
~~~

Khi gọi `opt.orElse(expression)`, Java **đánh giá expression trước khi gọi phương thức**, bất kể opt có chứa dữ liệu hay không. Vì vậy nếu biểu thức fallback tính toán tốn kém hoặc có side effect, nó vẫn chạy ngay cả khi không cần.

### 5.2. orElseGet(supplier)

`orElseGet` nhận một `Supplier<? extends T>` và chỉ gọi `get()` khi Optional rỗng:

~~~java
String value = Optional.of("Saved")
        .orElseGet(() -> loadDefaultName()); // Chỉ gọi fallback khi empty.
~~~

Đây là đoạn minh họa cần có phương thức `loadDefaultName()` trong ngữ cảnh. Nếu Optional chứa `"Saved"`, supplier **không được gọi**.

So sánh rõ:

~~~java
String direct = known.orElse(expensiveFallback());
String lazy = known.orElseGet(() -> expensiveFallback());
~~~

Trong ví dụ, `known` giả định là Optional<String> và `expensiveFallback()` trả String. Với `orElse`, fallback được đánh giá trước. Với `orElseGet`, fallback được thực thi **khi cần**. Nếu fallback chỉ là hằng số rẻ như `"N/A"`, `orElse` hoàn toàn hợp lý.

### 5.3. orElseThrow()

`orElseThrow()` (không tham số, Java 10+) trả giá trị nếu có, ngược lại ném `NoSuchElementException`. Bản nhận supplier cho phép tạo exception có nghĩa nghiệp vụ:

~~~java
String required = Optional.of("ready").orElseThrow();

String user = Optional.<String>empty().orElseThrow(
        () -> new IllegalArgumentException("Missing user")
);
~~~

Đoạn minh họa thứ hai **sẽ ném** `IllegalArgumentException`; không phải phép gán tạo thành công biến `user`.

Dùng `orElseThrow` khi theo hợp đồng **phải có giá trị tại thời điểm ấy**. Nếu không tìm thấy là một trạng thái bình thường, đừng ném exception tùy tiện; hãy chọn fallback hoặc trả Optional tiếp cho tầng gọi.

### 5.4. Tránh get() không có kiểm tra

~~~java
Optional<String> value = Optional.empty();
// String invalid = value.get(); // Ném NoSuchElementException.
~~~

`get()` vẫn tồn tại để truy cập giá trị khi biết chắc nó có mặt, nhưng kiểu `Optional` chính là tín hiệu cần cân nhắc empty. Với Java hiện đại, `orElseThrow()` diễn đạt kỳ vọng “phải có” rõ hơn, còn `orElse`/`orElseGet` diễn đạt fallback.

## 6. Biến đổi Optional bằng map

`map` áp dụng một `Function<? super T, ? extends U>` **nếu Optional đang chứa giá trị**, rồi trả `Optional<U>`. Nếu empty, mapper không được gọi và kết quả vẫn empty.

~~~java
Optional<String> raw = Optional.of("  Java  ");

Optional<Integer> length = raw
        .map(String::strip)
        .map(String::length);

System.out.println(length.orElse(0)); // 4
~~~

Các bước:

1. `raw` có chuỗi `"  Java  "`.
2. `String::strip` tạo chuỗi `"Java"`.
3. `String::length` cho kết quả int 4, được boxing thành Integer trong `Optional<Integer>`.
4. `orElse(0)` trả 4.

Nếu `raw = Optional.empty()`, `strip` và `length` không chạy, sau đó `orElse(0)` trả 0.

### 6.1. Mapper trả null

Theo hợp đồng của `Optional.map`, kết quả mapper được bọc như `Optional.ofNullable`. Do vậy **nếu mapper trả null, kết quả map là Optional.empty()**:

~~~java
record Profile(String email) { }

Optional<Profile> profile =
        Optional.of(new Profile(null));

Optional<String> email =
        profile.map(Profile::email);

System.out.println(email.isEmpty()); // true
~~~

Đây là đoạn minh họa cần đặt trong lớp Java có import `Optional`. Không cần tự gọi `ofNullable` ở giữa `map` khi mapper vốn trả một giá trị có thể null.

Điểm này **khác với flatMap**: `flatMap` yêu cầu chính mapper phải trả một đối tượng Optional **khác null**, như sẽ trình bày sau.

## 7. Chỉ giữ giá trị phù hợp bằng filter

`filter(Predicate<? super T>)` giữ nguyên Optional nếu giá trị đang có **đạt điều kiện**; ngược lại trả empty.

~~~java
Optional<String> validCode = Optional.of(" A01 ")
        .map(String::strip)
        .filter(code -> !code.isBlank());

Optional<String> blankCode = Optional.of("   ")
        .map(String::strip)
        .filter(code -> !code.isBlank());

System.out.println(validCode.orElse("missing")); // A01
System.out.println(blankCode.isEmpty());         // true
~~~

`filter` không chuyển đổi kiểu dữ liệu; nó kiểm tra xem giá trị hiện có nên tiếp tục được xem là kết quả hợp lệ hay không.

### 7.1. Tách điều kiện không có giá trị và điều kiện không hợp lệ

Có những nghiệp vụ yêu cầu **báo lỗi** nếu dữ liệu có mặt nhưng sai. Khi đó:

~~~java
Optional<String> code = Optional.of("invalid");
Optional<String> accepted = code.filter(c -> c.startsWith("A"));
~~~

`accepted` rỗng nhưng người gọi **không biết vì sao**: ban đầu không có code hay code có nhưng không đạt điều kiện? Nếu cần phân biệt, hãy dùng kiểu kết quả có thông tin validation, không chỉ dựa vào Optional sau filter.

## 8. Nối phép tra cứu bằng flatMap

`flatMap` giải quyết khi hàm mapper **đã trả Optional<U>**.

Giả sử:

~~~java
static Optional<User> findUser(int id) { /* ... */ }
static Optional<String> findEmail(User user) { /* ... */ }
~~~

Hai phương thức này chỉ là chữ ký giả định; phần thân `/* ... */` chưa triển khai.

Nếu dùng `map`:

~~~java
Optional<Optional<String>> nested =
        findUser(1).map(user -> findEmail(user));
~~~

Kết quả là **Optional lồng Optional**. Để giữ một lớp vỏ:

~~~java
Optional<String> email =
        findUser(1).flatMap(user -> findEmail(user));
~~~

`flatMap` gọi hàm chỉ khi Optional đầu chứa User; hàm phải trả một `Optional<String>`. Nếu kết quả từ hàm là `Optional.empty()`, toàn chuỗi empty.

### 8.1. Khác biệt quan trọng về null

- `map(user -> null)` có thể trả **Optional.empty()** theo `ofNullable`.
- `flatMap(user -> null)` **ném NullPointerException** nếu mapper được gọi, bởi `flatMap` không chấp nhận **đối tượng Optional trả về là null**.
- `flatMap(user -> Optional.empty())` là cách đúng để biểu diễn **không có kết quả** từ mapper dạng Optional.

Không nên viết phương thức khai báo `Optional<T>` nhưng đôi lúc trả null. Hợp đồng nhất quán phải luôn trả **Optional non-null**, bên trong present hoặc empty.

## 9. Chương trình Java 17 hoàn chỉnh: tra cứu User và email có thể vắng mặt

Bài toán minh họa:

- Mã 1 tồn tại với email cần chuẩn hóa.
- Mã 2 tồn tại nhưng email là null trong dữ liệu cũ.
- Mã 99 không có người dùng.
- Một đơn hàng có `userId` và cần lấy email chủ đơn.
- Cần vừa đọc kết quả đơn lẻ vừa gom những email có thật từ một tập ID.

Lưu tệp **OptionalLessonDemo.java**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class OptionalLessonDemo {
    record User(int id, String name, String email) { }
    record Order(String code, int userId) { }

    static Optional<User> findUser(int id) {
        if (id == 1) {
            return Optional.of(
                    new User(1, " Lan ", " Lan@Example.com ")
            );
        }
        if (id == 2) {
            return Optional.of(new User(2, "An", null));
        }
        return Optional.empty();
    }

    static Optional<String> normalizedEmail(int id) {
        return findUser(id)
                .map(User::email)
                .map(String::strip)
                .filter(email -> !email.isBlank())
                .map(email -> email.toLowerCase(Locale.ROOT));
    }

    static Optional<String> ownerEmail(Order order) {
        return Optional.ofNullable(order)
                .flatMap(o -> normalizedEmail(o.userId()));
    }

    public static void main(String[] args) {
        System.out.println("lookup 1: "
                + findUser(1).isPresent());
        System.out.println("lookup 99 empty: "
                + findUser(99).isEmpty());

        System.out.println("email 1: "
                + normalizedEmail(1).orElse("<missing>"));
        System.out.println("email 2: "
                + normalizedEmail(2).orElse("<missing>"));
        System.out.println("email 99: "
                + normalizedEmail(99).orElseGet(() -> "no-email"));

        System.out.println("owner 1: "
                + ownerEmail(new Order("O-1", 1)).orElse("none"));
        System.out.println("owner 99: "
                + ownerEmail(new Order("O-2", 99)).orElse("none"));

        System.out.println("normalized name: "
                + findUser(1)
                        .map(User::name)
                        .map(String::strip)
                        .orElseThrow());

        findUser(2).ifPresentOrElse(
                user -> System.out.println("user 2: " + user.name()),
                () -> System.out.println("user 2: missing")
        );
        findUser(99).ifPresentOrElse(
                user -> System.out.println("user 99: " + user.name()),
                () -> System.out.println("user 99: missing")
        );

        long presentEmails = Stream.of(1, 2, 99)
                .map(OptionalLessonDemo::normalizedEmail)
                .flatMap(Optional::stream)
                .count();
        System.out.println("email count: " + presentEmails);

        OptionalInt max = IntStream.of(3, 8, 5).max();
        System.out.println("max: " + max.orElse(-1));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac OptionalLessonDemo.java
java OptionalLessonDemo
~~~

**Đầu ra chính xác:**

~~~text
lookup 1: true
lookup 99 empty: true
email 1: lan@example.com
email 2: <missing>
email 99: no-email
owner 1: lan@example.com
owner 99: none
normalized name: Lan
user 2: An
user 99: missing
email count: 1
max: 8
~~~

### 9.1. Diễn giải các trạng thái

1. **findUser(1)** trả Optional có User, nên `isPresent()` bằng true.
2. **findUser(99)** trả Optional.empty, nên `isEmpty()` bằng true.
3. **normalizedEmail(1)** lấy email, `strip()` bỏ khoảng trắng và `toLowerCase(Locale.ROOT)` chuẩn hóa thành `lan@example.com`.
4. **normalizedEmail(2)**: User tồn tại nhưng `email == null`; `map(User::email)` biến kết quả thành empty, các bước sau không chạy, `orElse("<missing>")` cung cấp fallback.
5. **normalizedEmail(99)**: ngay phép tra cứu User đã empty. `orElseGet` tạo fallback `no-email` khi cần.
6. **ownerEmail** dùng `flatMap` để nối một phép tra cứu User và một phép tra cứu email mà không tạo `Optional<Optional<String>>`.
7. **ifPresentOrElse** chọn hành động tương ứng cho User 2 (có) và User 99 (không có).
8. **Optional.stream()** trả stream có một phần tử khi present và stream rỗng khi empty. Sau `flatMap(Optional::stream)`, trong ba ID chỉ có email của ID 1 nên `count() == 1`.
9. **IntStream.max()** trả `OptionalInt` vì với stream rỗng sẽ không có giá trị lớn nhất. Với 3, 8, 5 thì kết quả là 8.

Chương trình giả lập dữ liệu trong bộ nhớ nên cho đầu ra xác định. Trong hệ thống thật, tra cứu database/API có thể gặp lỗi: **không được đổi mọi lỗi truy vấn thành empty** nếu nghiệp vụ phải phân biệt “không tìm thấy” và “hệ thống không thể truy cập dữ liệu”.

## 10. Optional.stream và pipeline dữ liệu

Từ Java 9, `Optional<T>.stream()` chuyển một Optional thành:

- Stream có **một phần tử** nếu present.
- Stream **không có phần tử** nếu empty.

Ví dụ:

~~~java
List<Optional<String>> values = List.of(
        Optional.of("A"),
        Optional.empty(),
        Optional.of("B")
);

List<String> available = values.stream()
        .flatMap(Optional::stream)
        .toList();

System.out.println(available); // [A, B]
~~~

`Optional::stream` đặc biệt hữu ích khi mỗi bản ghi có thể biến đổi thành **0 hoặc 1** giá trị hợp lệ. Trong pipeline, dùng `flatMap(Optional::stream)` giúp loại bỏ lớp vỏ Optional đồng thời bỏ những phần tử không có kết quả.

Nếu dữ liệu đầu vào là một stream và mapper trả Optional, có thể viết:

~~~java
List<String> emails = ids.stream()
        .map(thisService::lookupEmail)
        .flatMap(Optional::stream)
        .toList();
~~~

Đây là **mảnh ghép minh họa**, cần có biến `ids` và đối tượng `thisService` với phương thức `lookupEmail` tương ứng. Không nên suy diễn các phép tra cứu trong pipeline luôn an toàn khi thực thi song song; điều đó phụ thuộc repository, connection, side effect và chính sách lỗi.

## 11. Optional cho kiểu nguyên thủy

Java có ba loại Optional chuyên biệt:

| Kiểu | Khi present | Phương thức lấy giá trị |
| --- | --- | --- |
| **OptionalInt** | chứa primitive `int` | `getAsInt()` |
| **OptionalLong** | chứa primitive `long` | `getAsLong()` |
| **OptionalDouble** | chứa primitive `double` | `getAsDouble()` |

Chúng tránh boxing khi chỉ cần biểu diễn có/không có một giá trị nguyên thủy.

~~~java
OptionalInt maximum = IntStream.of(4, 9, 2).max();
System.out.println(maximum.orElse(-1)); // 9

OptionalInt none = IntStream.empty().max();
System.out.println(none.isEmpty());     // true
~~~

Các API primitive Optional có nhiều điểm tương đồng nhưng **không hoàn toàn giống `Optional<T>`**. Ví dụ chúng không cung cấp bộ `map`/`flatMap` chung như Optional<T>; khi cần pipeline biến đổi phong phú, cân nhắc Stream primitive hoặc kiểu dữ liệu khác phù hợp.

**Quan trọng:** `OptionalInt.empty()` không phải số 0; `OptionalInt.of(0)` biểu diễn một giá trị **có mặt và bằng 0**. Đừng dùng 0 hay -1 làm “không có” nếu chúng có thể là giá trị hợp lệ, trừ khi hợp đồng nghiệp vụ cho phép sentinel.

## 12. Khi nào nên trả Optional từ API?

Một nguyên tắc thực dụng: dùng `Optional<T>` làm **kiểu trả về** nếu việc thiếu kết quả là một tình huống được dự kiến.

~~~java
Optional<User> findById(long id);
Optional<String> findNickname(User user);
Optional<Order> findLatestOrderFor(User user);
~~~

Đây là các chữ ký API minh họa; kiểu User/Order chưa được định nghĩa cho những chữ ký này.

Cách đặt tên nên cho người gọi biết **điều gì có thể không tồn tại**. Với repository, phân biệt:

- `findById`: không tìm thấy → Optional.empty.
- `getRequiredById` hoặc `loadRequired`: không có dữ liệu → exception theo hợp đồng.
- `validate`: trả kết quả xác thực có nguyên nhân khi cần, không nhất thiết là Optional.

Khi API chắc chắn có giá trị, trả **T** thường đơn giản hơn `Optional<T>`. Không nên bọc mọi phương thức bằng Optional để “an toàn hơn” mà không có trường hợp vắng mặt thật sự.

### 12.1. Có nên dùng Optional làm tham số?

Ví dụ API:

~~~java
void sendMessage(Optional<String> nickname);
~~~

Về cú pháp là hợp lệ, nhưng nhiều API Java thông thường dễ sử dụng hơn với overload, giá trị mặc định rõ, hoặc một kiểu request chứa thông tin tùy chọn. Caller phải tự tạo Optional khi truyền tham số, đôi khi tạo thêm lớp vỏ không cần thiết. **Không có lệnh cấm tuyệt đối** dùng Optional làm tham số, nhưng nên cân nhắc lợi ích hợp đồng và quy ước codebase.

### 12.2. Có nên lưu Optional vào field?

Một field `Optional<String>` hợp lệ về mặt ngôn ngữ, nhưng không mặc nhiên tốt hơn field String có hợp đồng rõ hoặc model chuyên biệt. `Optional` được thiết kế chủ yếu cho **kết quả có thể thiếu**, không phải giải pháp phổ quát cho mọi optional property trong DTO/entity.

Chú ý vấn đề tương thích của framework, mapping và serialization. `Optional` **không implement Serializable** trong Java 17; đừng giả định đối tượng chứa field Optional có thể được Java serialization mặc định xử lý không cần cơ chế tùy chỉnh.

## 13. Giá trị có mặt không đồng nghĩa giá trị đúng

`Optional.of("")` và `Optional.of("   ")` đều present. Nếu nghiệp vụ xem chuỗi rỗng hoặc chỉ gồm khoảng trắng là không hợp lệ, hãy xử lý:

~~~java
Optional<String> normalized = Optional.ofNullable(input)
        .map(String::strip)
        .filter(text -> !text.isBlank());
~~~

Đây là mảnh ghép trong ngữ cảnh đã có biến `input` kiểu String. Chuỗi empty sau chuẩn hóa sẽ thành Optional.empty.

Nhưng nếu ứng dụng cần trả “chuỗi không đúng định dạng”, `filter` đã làm mất thông tin nguyên nhân. Hãy tách việc **có dữ liệu hay không** khỏi **dữ liệu có hợp lệ không** khi nghiệp vụ cần phân biệt hai câu hỏi.

### 13.1. Optional không làm một giá trị khác null trở thành bất biến

~~~java
List<String> mutable = new ArrayList<>();
Optional<List<String>> holder = Optional.of(mutable);

mutable.add("A");
System.out.println(holder.orElseThrow()); // [A]
~~~

Optional giữ một tham chiếu tới List; nó không sao chép sâu hay khóa trạng thái của List. Nếu nhiều luồng cùng sửa collection, cần đồng bộ hoặc dùng dữ liệu bất biến phù hợp.

## 14. Xử lý ngoại lệ và ranh giới lỗi

`Optional.empty()` chỉ nói **không có kết quả**. Khi một API mạng hoặc database lỗi, “không thể tra cứu” thường khác với “đã tra cứu và không có”. Nếu nuốt mọi exception rồi trả empty, hệ thống có thể hiểu nhầm sự cố thành một kết quả hợp lệ.

Không nên làm như sau nếu cần báo lỗi:

~~~java
// Phản ví dụ:
// try {
//     return repository.find(id);
// } catch (Exception ignored) {
//     return Optional.empty(); // Che giấu lỗi truy vấn.
// }
~~~

Hướng phù hợp hơn:

- Nếu **đã tra cứu thành công nhưng không có bản ghi**, trả empty.
- Nếu **đầu vào không hợp lệ**, phản hồi validation.
- Nếu **hệ thống thất bại**, ném exception có ý nghĩa hoặc dùng kết quả chứa lỗi, tùy hợp đồng tầng gọi.
- Nếu cần thông tin nguyên nhân vắng mặt (ví dụ “chưa duyệt”, “đã khóa”, “không đủ quyền”), dùng kiểu `Result` hoặc `Decision` có các trạng thái rõ thay vì chỉ Optional.

Một `Optional<T>` có thể kết hợp cùng `CompletableFuture` khi tác vụ bất đồng bộ, ví dụ một future cuối cùng hoàn thành với Optional<User>; nhưng hai lớp biểu diễn **hai trục khác nhau**: thời điểm hoàn tất và sự hiện diện của kết quả.

## 15. Những lỗi phổ biến

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gọi `optional.get()` không kiểm tra | `NoSuchElementException` nếu empty | `orElse`, `orElseGet`, `orElseThrow`, `map` hoặc `ifPresent` |
| Dùng `Optional.of(nullable)` | Có thể ném `NullPointerException` ngay khi tạo | `ofNullable` tại ranh giới nullable |
| Trả null từ phương thức khai báo Optional | Người gọi vẫn phải kiểm tra null | Luôn trả `Optional.of`, `ofNullable` hoặc `empty` |
| Coi empty là exception của database | Che khuất sự cố và nguyên nhân lỗi | Tách “không tìm thấy” khỏi “tra cứu thất bại” |
| Dùng `map` cho hàm đã trả Optional | Tạo `Optional<Optional<T>>` | Dùng `flatMap` |
| Trả null từ mapper của `flatMap` | `NullPointerException` khi được gọi | Mapper phải trả Optional không null |
| Dùng `orElse(expensive())` và tưởng lazy | Fallback vẫn được tính dù present | `orElseGet(() -> expensive())` |
| Dùng `Optional.of(0)` như empty | Lẫn số 0 hợp lệ và vắng mặt | Dùng `OptionalInt.empty()` hoặc Optional.empty() |
| Dùng Optional để thay mọi tham số/field | API khó đọc, tăng lớp bọc không cần thiết | Ưu tiên Optional tại kết quả có thể vắng mặt |
| Tin rằng Optional bảo đảm immutability sâu | Object bên trong vẫn có thể mutable | Quản lý ownership hoặc dùng immutable data |
| Đặt side effect cần chạy vào `map` | Pipeline khó dự đoán, khó test | Tách phép tính và hiệu ứng có chủ đích |

## 16. Cách kiểm thử Optional

Với một phương thức trả Optional, hãy kiểm tra tối thiểu cả **hai trạng thái**:

1. Tìm thấy dữ liệu → Optional present, giá trị đúng.
2. Không tìm thấy → Optional empty, không ném exception nếu đó là trường hợp bình thường.
3. Dữ liệu legacy trả null → `ofNullable` hoặc `map` chuyển thành empty đúng hợp đồng.
4. `filter` loại dữ liệu không đáp ứng điều kiện.
5. `flatMap` tránh Optional lồng nhau.
6. `orElseGet` chỉ thực thi fallback khi empty.
7. `orElseThrow` ném đúng loại exception khi bắt buộc có giá trị.
8. Lỗi hệ thống thật được phản hồi đúng, không bị đánh đồng với empty.

Ví dụ kiểm tra cơ chế lazy của `orElseGet` mà không cần service thật:

~~~java
java.util.concurrent.atomic.AtomicInteger calls =
        new java.util.concurrent.atomic.AtomicInteger();

String first = Optional.of("ready").orElseGet(() -> {
    calls.incrementAndGet();
    return "fallback";
});
String second = Optional.<String>empty().orElseGet(() -> {
    calls.incrementAndGet();
    return "fallback";
});

System.out.println(first);       // ready
System.out.println(second);      // fallback
System.out.println(calls.get()); // 1
~~~

Đây là đoạn minh họa cần đặt trong lớp/phương thức có import Optional. `AtomicInteger` chỉ để **đếm lần gọi fallback cho bài test**, không phải mẫu bắt buộc của logic nghiệp vụ. Việc xác nhận `calls == 1` cho thấy supplier không chạy khi `first` present.

## 17. Bài tập tự luyện

### Bài 1 — Chuyển null thành Optional

Một API cũ trả `String` có thể null. Hãy chuyển nó thành `Optional<String>`, cắt khoảng trắng và xem chuỗi rỗng là không có giá trị.

**Đáp án gợi ý:**

~~~java
Optional<String> cleaned = Optional.ofNullable(legacyValue)
        .map(String::strip)
        .filter(value -> !value.isEmpty());
~~~

`legacyValue` giả định là biến String đã khai báo. Nếu null → empty; nếu `"  Java  "` → Optional chứa `"Java"`; nếu `"   "` → empty.

### Bài 2 — Chọn orElse hay orElseGet

Có `Optional<String> cached`. Để lấy fallback bằng truy vấn tốn kém **chỉ khi dữ liệu không có**, dùng phương thức nào?

**Đáp án:** `cached.orElseGet(() -> queryFallback())`. Không dùng `cached.orElse(queryFallback())` nếu cần tránh truy vấn thừa, vì đối số của orElse được đánh giá trước.

### Bài 3 — map hay flatMap?

Cho `Optional<User> user` và hàm `Optional<String> findEmail(User u)`. Muốn có `Optional<String>`, dùng gì?

**Đáp án:**

~~~java
Optional<String> email = user.flatMap(thisService::findEmail);
~~~

Đây là mảnh ghép với `user` và `thisService` có sẵn. Nếu dùng `map` trong tình huống này sẽ nhận `Optional<Optional<String>>`.

### Bài 4 — Phân biệt 0 và vắng mặt

Có phép tìm số lượng tồn kho: kết quả **0 là hợp lệ**, còn **không có mặt hàng** mới là vắng mặt. Nên trả một `int` và dùng 0 làm sentinel hay trả OptionalInt?

**Đáp án:** `OptionalInt` (hoặc kiểu kết quả có thông tin domain hơn nếu cần) cho phép phân biệt **present và bằng 0** với **empty**. Không dùng 0 làm tín hiệu không tìm thấy khi 0 là số lượng hợp lệ.

### Bài 5 — Thiết kế hợp đồng API

Phân biệt ba tình huống của `findCustomer(id)`: không có khách hàng, ID không hợp lệ và kết nối database thất bại. Hãy thiết kế chữ ký hoặc quy tắc phản hồi sao cho chúng không bị trộn lẫn.

**Gợi ý:** có thể dùng `Optional<Customer>` cho kết quả tra cứu thành công nhưng không có dữ liệu, validation exception/kết quả lỗi cho ID sai, và database exception/kết quả lỗi có nguyên nhân cho thất bại truy vấn. Với ứng dụng cần trả một kết quả có cấu trúc cho mọi tình huống, dùng kiểu `Result<Customer,Error>` do dự án định nghĩa.

## 18. Ghi nhớ

**Optional<T> biểu diễn kết quả có hoặc không có một giá trị khác null.** Nó giúp contract của phương thức chỉ rõ khả năng “không tìm thấy”, nhưng không thay thế xử lý lỗi và không biến dữ liệu mutable thành bất biến.

- **Tạo:** `empty()`, `of(nonNull)`, `ofNullable(nullable)`.
- **Kiểm tra:** `isPresent()`, `isEmpty()`, `ifPresent(...)`, `ifPresentOrElse(...)`.
- **Xử lý hiện diện/vắng mặt:** `orElse` (fallback eager), `orElseGet` (fallback lazy), `orElseThrow` (bắt buộc có giá trị).
- **Biến đổi:** `map` khi mapper trả giá trị thông thường; `flatMap` khi mapper đã trả Optional; `filter` khi cần giữ giá trị đạt điều kiện.
- **Pipeline:** `Optional.stream()` để tạo 0 hoặc 1 phần tử; `OptionalInt`/`OptionalLong`/`OptionalDouble` để biểu diễn kết quả primitive có thể thiếu.

Hãy trả Optional khi **vắng mặt là một kết quả hợp lệ của API**. Xử lý empty rõ ràng, không gọi `get()` tùy tiện và không dùng empty để che giấu lỗi nghiệp vụ hay sự cố hệ thống.
