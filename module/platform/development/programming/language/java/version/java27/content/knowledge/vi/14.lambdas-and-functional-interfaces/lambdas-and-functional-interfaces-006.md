# Optional trong thiết kế kết quả có thể vắng mặt — Java 27

Trong nhiều ứng dụng Java, một phương thức tra cứu có thể **tìm thấy** hoặc **không tìm thấy** dữ liệu. Ví dụ: tìm khách hàng theo mã, tra cấu hình tùy chọn, đọc email phụ của người dùng hoặc tìm phần tử đầu tiên thỏa điều kiện. Nếu trả về `null` để biểu diễn “không có kết quả”, người gọi rất dễ quên kiểm tra và gặp `NullPointerException`.

`java.util.Optional<T>` giúp thể hiện khả năng vắng mặt ngay trong **kiểu trả về**:

```java
Optional<User> findUserById(String id);
```

Nhìn vào chữ ký, người gọi biết không thể mặc định luôn có `User`. Họ phải quyết định cách xử lý hai trường hợp: có giá trị và không có giá trị.

Bài thuộc chương **Lambda và interface hàm**, tập trung vào việc thiết kế API với `Optional`, kết hợp `Function`, `Predicate`, `Consumer`, `Supplier`, lambda, method reference và Stream. Tất cả API chính dùng trong bài đều là tính năng chuẩn, còn được hỗ trợ trên **Java SE 27**; bài không yêu cầu bật preview.

## 1. Mô hình của Optional: có một giá trị hoặc không có giá trị

`Optional<T>` là một *container* có tối đa **một** giá trị kiểu tham chiếu `T`, và giá trị hiện diện **không bao giờ là `null`**.

```java
import java.util.Optional;

Optional<String> found = Optional.of("Java");
Optional<String> missing = Optional.empty();

System.out.println(found.isPresent());  // true
System.out.println(missing.isPresent()); // false
```

Có thể hình dung:

```text
Optional<String>
├── Có giá trị: "Java"
└── Vắng mặt: không chứa giá trị
```

`Optional.empty()` **không phải** một `Optional` “chứa `null`”. Hai trạng thái chính là có giá trị khác `null` hoặc vắng mặt.

Đây là **cách biểu diễn sự vắng mặt có chủ đích** trong kết quả phương thức, không phải cơ chế ngăn mọi lỗi `null` của chương trình. Một lời gọi chứa `Optional` vẫn có thể ném ngoại lệ, và một biến tham chiếu có kiểu `Optional<T>` về mặt ngôn ngữ vẫn có thể bị gán `null` nếu lập trình viên phá vỡ quy ước API.

### 1.1. Phân biệt “không tìm thấy”, “không hợp lệ” và “bị lỗi”

Ba tình huống dưới đây không nhất thiết có cùng ngữ nghĩa:

| Tình huống | Cách biểu diễn thông thường | Ví dụ |
| --- | --- | --- |
| Không có kết quả là điều **bình thường** | `Optional.empty()` | Tra mã khách hàng chưa tồn tại |
| Đầu vào vi phạm điều kiện tiên quyết | Từ chối bằng validation hoặc ngoại lệ thích hợp | Tham số `id` là `null` dù contract cấm |
| Không thể thực hiện thao tác do lỗi | Ngoại lệ hoặc kiểu kết quả mang thông tin lỗi | Database ngừng kết nối, truy vấn bị timeout |
| Có kết quả hợp lệ | `Optional.of(value)` | Tìm được khách hàng |

Nếu database gặp sự cố, **đừng mặc định nuốt lỗi rồi trả về `Optional.empty()`**: điều đó khiến người gọi hiểu nhầm rằng hệ thống đã tìm thành công nhưng không có dữ liệu.

Tương tự, `Optional.empty()` không mang thông tin vì sao vắng mặt. Nếu nghiệp vụ phải phân biệt “chưa tồn tại”, “không có quyền”, “đã bị khóa” và “đã xóa”, một kiểu kết quả tường minh (ví dụ mô hình trạng thái bằng `sealed interface` và `record`) hoặc ngoại lệ có chủ đích có thể phù hợp hơn.

### 1.2. Chỉ nên có một Optional, đừng trả null Optional

Đúng:

```java
static Optional<String> findNickname(boolean exists) {
    return exists ? Optional.of("Lan") : Optional.empty();
}
```

Sai về thiết kế hợp đồng:

```java
// Tránh:
// static Optional<String> findNickname(boolean exists) {
//     return exists ? Optional.of("Lan") : null;
// }
```

Nếu một phương thức cam kết trả `Optional<T>` thì nó phải trả về **một instance `Optional` khác `null`**, kể cả khi không có giá trị. Trả `null` phá vỡ mục đích của abstraction: người gọi sẽ phải kiểm tra `optional == null` *và* `optional.isEmpty()`.

## 2. Ba cách tạo Optional: `of`, `ofNullable`, `empty`

| Cách tạo | Ý nghĩa | Khi đầu vào là `null` |
| --- | --- | --- |
| `Optional.of(value)` | Khẳng định chắc chắn có giá trị hợp lệ | Ném `NullPointerException` |
| `Optional.ofNullable(value)` | Chuyển một tham chiếu có thể `null` thành Optional | Trả `Optional.empty()` |
| `Optional.empty()` | Biểu diễn vắng mặt một cách tường minh | Không có đối số |

```java
import java.util.Optional;

Optional<String> a = Optional.of("Java");
Optional<String> b = Optional.ofNullable("Java");
Optional<String> c = Optional.ofNullable(null);
Optional<String> d = Optional.empty();

System.out.println(a.isPresent()); // true
System.out.println(b.isPresent()); // true
System.out.println(c.isEmpty());   // true
System.out.println(d.isEmpty());   // true
```

### 2.1. Dùng `of` khi `null` là lỗi của người gọi

```java
static Optional<String> wrapRequiredCode(String code) {
    return Optional.of(code);
}
```

Nếu `code == null`, `Optional.of(code)` ném ngoại lệ ngay. Điều này chỉ phù hợp khi giá trị `null` **không được phép** theo hợp đồng của API.

### 2.2. Dùng `ofNullable` khi đang chuyển đổi API trả `null`

Giả sử một kho dữ liệu hoặc một API có trước trả về tham chiếu có thể `null`:

```java
static Optional<String> lookup(
        java.util.Map<String, String> source, String key) {

    return Optional.ofNullable(source.get(key));
}
```

Đây là cách đóng gói sự vắng mặt ở **ranh giới API**. Nhưng với `Map.get`, giá trị `null` có thể nghĩa là **không có khóa** hoặc **khóa ánh xạ tới `null`**. Khi nghiệp vụ phải phân biệt hai trường hợp, cần dùng `containsKey` hoặc thiết kế kiểu kết quả rõ hơn, thay vì vô tình gộp cả hai thành `Optional.empty()`.

### 2.3. Không so sánh identity với `Optional.empty()`

`Optional` là một *value-based class*. Đừng viết:

```java
// Sai về nguyên tắc:
// boolean missing = optional == Optional.empty();
```

API **không bảo đảm** mọi lời gọi `Optional.empty()` phải trả lại cùng một instance. Hãy dùng:

```java
boolean missing = optional.isEmpty();
boolean found = optional.isPresent();
```

Hai đối tượng `Optional` chứa những giá trị bằng nhau sẽ được so sánh bằng nhau qua `equals`; hai Optional đều rỗng cũng bằng nhau. Không khóa đồng bộ trên một đối tượng `Optional` bằng `synchronized(optional)` vì value-based instance không dành cho identity-sensitive operations.

## 3. Phương thức trả Optional: thiết kế hợp đồng rõ ràng

Giả sử muốn tìm người dùng theo ID:

```java
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

record User(String id, String displayName) {}

final class UserDirectory {
    private final Map<String, User> users;

    UserDirectory(Map<String, User> users) {
        this.users = Map.copyOf(users);
    }

    Optional<User> findById(String id) {
        Objects.requireNonNull(id, "id");
        return Optional.ofNullable(users.get(id));
    }
}
```

Người gọi:

```java
UserDirectory directory = new UserDirectory(
        Map.of("u1", new User("u1", "Lan"))
);

Optional<User> found = directory.findById("u1");
Optional<User> missing = directory.findById("u2");

System.out.println(found.map(User::displayName).orElse("(không có)"));
// Lan
System.out.println(missing.map(User::displayName).orElse("(không có)"));
// (không có)
```

Thiết kế trên tách hai trách nhiệm:

- **Bên cung cấp**: tìm dữ liệu; khi không có khóa hợp lệ, trả `Optional.empty()`.
- **Bên tiêu thụ**: quyết định dùng mặc định, tìm ở nguồn khác, bỏ qua, ghi log hay ném ngoại lệ nếu nghiệp vụ bắt buộc phải có.

Điều này đặc biệt hữu ích với API thư viện vì mỗi người gọi có thể có cách xử lý “không tìm thấy” khác nhau.

### 3.1. Tên phương thức nên thể hiện khả năng vắng mặt

Tên như `findById`, `lookup` hoặc `findFirst` thường dễ gợi ý rằng kết quả có thể vắng mặt. Tuy nhiên, **kiểu trả về mới là hợp đồng được compiler kiểm tra**. Đừng chỉ dựa vào tên.

Phân biệt hai API có thể cùng tồn tại:

```java
Optional<User> findById(String id);

User requireById(String id); // Ném ngoại lệ khi không tìm thấy.
```

API `find...` phù hợp khi vắng mặt là một khả năng dự kiến; API `require...` phù hợp khi người gọi đang khẳng định phải có dữ liệu. Hành vi ngoại lệ cần được mô tả trong tài liệu của phương thức.

## 4. Đọc giá trị: `orElse`, `orElseGet`, `orElseThrow`

`Optional` không ép người gọi dùng một cách đọc duy nhất. Có nhiều cách, phục vụ mục đích khác nhau.

| Phương thức | Khi có giá trị | Khi rỗng | Phù hợp |
| --- | --- | --- | --- |
| `orElse(defaultValue)` | Trả giá trị có sẵn | Trả giá trị mặc định | Mặc định đã có và rẻ |
| `orElseGet(supplier)` | Trả giá trị có sẵn | **Gọi supplier** để tạo mặc định | Fallback tốn công hoặc có tác dụng phụ |
| `orElseThrow()` | Trả giá trị có sẵn | Ném `NoSuchElementException` | Khẳng định bắt buộc có, không cần thông điệp riêng |
| `orElseThrow(exceptionSupplier)` | Trả giá trị có sẵn | Tạo và ném ngoại lệ thích hợp | Thiết kế lỗi nghiệp vụ |
| `get()` | Trả giá trị có sẵn | Ném `NoSuchElementException` | Có sẵn nhưng thường nên ưu tiên `orElseThrow()` |

Ví dụ:

```java
Optional<String> nickname = Optional.empty();

String label = nickname.orElse("(chưa đặt tên)");
String generated = nickname.orElseGet(() -> "Khách-" + 1001);

System.out.println(label);     // (chưa đặt tên)
System.out.println(generated); // Khách-1001
```

### 4.1. Khác biệt quan trọng: `orElse` đánh giá đối số ngay

Trong Java, **đối số phương thức được đánh giá trước khi phương thức được gọi**.

```java
static String loadFallback() {
    System.out.println("Đang tải phương án dự phòng");
    return "fallback";
}

static void example() {
    Optional<String> value = Optional.of("primary");

    String a = value.orElse(loadFallback());
    System.out.println(a);
}
```

Đầu ra:

```text
Đang tải phương án dự phòng
primary
```

Dù `Optional` đang chứa `"primary"`, `loadFallback()` **vẫn chạy** để tính đối số truyền cho `orElse`. Giá trị nó trả về không được sử dụng.

Thay bằng `orElseGet`:

```java
Optional<String> value = Optional.of("primary");

String b = value.orElseGet(() -> loadFallback());
System.out.println(b); // primary; loadFallback() không chạy
```

Với `orElseGet`, một `Supplier<T>` được truyền vào; chỉ khi Optional **rỗng** thì Java mới thực thi supplier để tạo fallback.

**Quy tắc chọn lựa:** `orElse("chưa có")` cho hằng hoặc giá trị đã tính; `orElseGet(this::lookupDefault)` cho logic dự phòng đắt đỏ, cần truy vấn hoặc có tác dụng phụ.

### 4.2. `orElseThrow` thể hiện yêu cầu bắt buộc có dữ liệu

```java
User user = directory.findById("u1")
        .orElseThrow(() ->
                new IllegalArgumentException("Không tìm thấy người dùng u1"));
```

Supplier của ngoại lệ chỉ được gọi khi Optional rỗng. Ưu điểm của `orElseThrow(...)` so với `get()` là người viết code nêu rõ **ngoại lệ nào** phù hợp với nghiệp vụ.

`get()` không bị xóa khỏi Java 27, nhưng Javadoc khuyến nghị `orElseThrow()` khi muốn lấy giá trị hoặc ném `NoSuchElementException`. Cả hai đều sẽ ném khi rỗng; **không nên gọi không điều kiện** chỉ vì tin rằng “thường sẽ có giá trị”.

## 5. `map`: biến đổi giá trị nếu hiện diện

`map(Function<? super T, ? extends U>)` nhận một `Function`; khi Optional có giá trị, nó gọi hàm biến đổi và trả về `Optional<U>`. Khi rỗng, hàm biến đổi **không được gọi**.

```java
Optional<String> name = Optional.of("Lan");

Optional<Integer> length = name.map(String::length);

System.out.println(length.orElse(0)); // 3
```

Ví dụ với method reference:

```java
Optional<User> maybeUser = directory.findById("u1");

String label = maybeUser
        .map(User::displayName)
        .map(String::strip)
        .orElse("(không xác định)");
```

Nếu không có `User`, cả hai phép `map` đều bị bỏ qua và `label` nhận giá trị mặc định.

### 5.1. `map` chuyển kết quả mapper là `null` thành Optional rỗng

Điểm đáng chú ý của Javadoc:

```java
record Contact(String email) {}

Optional<Contact> contact =
        Optional.of(new Contact(null));

Optional<String> email = contact.map(Contact::email);

System.out.println(email.isEmpty()); // true
```

Với mapper trả về `null`, `Optional.map` hành xử như đưa kết quả vào `Optional.ofNullable`. Điều này hữu ích ở ranh giới dữ liệu legacy hay có trường nullable, nhưng không có nghĩa mọi code nên cố tình trả `null`. Nếu `null` biểu thị **lỗi**, nên kiểm tra và báo lỗi rõ ràng thay vì vô tình biến lỗi thành một kết quả vắng mặt.

### 5.2. `map` không giống `Stream.map` về thời điểm thực thi

`Optional.map` **gọi mapper ngay** khi được thực thi và Optional có giá trị. Nó không thiết lập một pipeline lazy chờ terminal operation như phần lớn phép biến đổi của Stream.

```java
Optional<String> value = Optional.of("ok");

Optional<String> transformed = value.map(text -> {
    System.out.println("map chạy");
    return text.toUpperCase();
});
// "map chạy" đã được in ở đây.
```

Do đó nên tránh đặt tác dụng phụ bắt buộc ở giữa một chuỗi `map`/`filter`: nếu giá trị vắng mặt hoặc bị lọc, các bước sau không chạy. Khi cần một hành động nghiệp vụ độc lập, trình bày nó thành câu lệnh riêng.

## 6. `filter`: giữ giá trị khi predicate đúng

`filter(Predicate<? super T>)` giữ nguyên giá trị hiện diện nếu predicate trả về `true`; ngược lại trả Optional rỗng.

```java
Optional<String> raw = Optional.of("  java  ");

Optional<String> normalized = raw
        .map(String::strip)
        .filter(text -> !text.isBlank());

System.out.println(normalized.orElse("(trống)")); // java
```

Nếu Optional ban đầu rỗng, predicate không chạy. Nếu giá trị có nhưng predicate trả `false`, kết quả cũng rỗng.

**Ý nghĩa thiết kế:** sau khi gọi `filter`, Optional rỗng có thể là “không có giá trị đầu vào” **hoặc** “giá trị đầu vào không vượt qua điều kiện”. Nếu ứng dụng phải phân biệt hai lý do này, đừng gộp chúng vào cùng một `Optional.empty()`.

Ví dụ với `Predicate.not` của Java hiện hành:

```java
import java.util.function.Predicate;

Optional<String> nonBlank = raw
        .map(String::strip)
        .filter(Predicate.not(String::isBlank));
```

`Predicate.not` giúp diễn tả điều kiện phủ định khi dùng method reference, nhưng lambda tường minh cũng hoàn toàn hợp lệ.

## 7. `flatMap`: khi hàm biến đổi đã trả Optional

Giả sử một người dùng có ID nhóm, còn việc tra nhóm có thể không tìm thấy. Hai bước tra cứu đều có kết quả tùy chọn:

```java
record User(String id, String groupId) {}
record Group(String id, String label) {}

Optional<User> findUser(String id) { /* ... */ }
Optional<Group> findGroup(String id) { /* ... */ }
```

Nếu dùng `map` với một hàm vốn trả về Optional, kết quả sẽ bị lồng:

```java
Optional<Optional<Group>> nested =
        findUser("u1").map(user -> findGroup(user.groupId()));
```

Thông thường không cần mô hình hai lớp `Optional` như thế này. Thay bằng `flatMap`:

```java
Optional<Group> group =
        findUser("u1").flatMap(user -> findGroup(user.groupId()));
```

Quy tắc nhớ:

- **`map`** dùng khi hàm `T -> U`.
- **`flatMap`** dùng khi hàm `T -> Optional<U>`.

Nếu Optional đầu vào rỗng, mapper không chạy. Nếu có giá trị, `flatMap` dùng trực tiếp Optional do mapper trả lại, **không bọc thêm một lớp**.

### 7.1. `map` và `flatMap` xử lý `null` khác nhau

```java
Optional<String> text = Optional.of("abc");

Optional<String> a = text.map(s -> null); // Optional.empty()

// Dòng sau ném NullPointerException nếu được thực thi:
// Optional<String> b = text.flatMap(s -> null);
```

Mapper của `flatMap` phải trả về một **Optional không `null`**; nếu thiếu kết quả, trả `Optional.empty()`.

Đây là điều kiện quan trọng khi kết nối nhiều repository hoặc service. Mọi phương thức đã khai báo trả `Optional<T>` cần giữ đúng hợp đồng đó.

### 7.2. Chuỗi điều kiện lồng nhau rõ ràng hơn khi dùng Optional

```java
static Optional<String> normalizedEmail(Optional<User> user) {
    return user
            .map(User::email)
            .map(String::strip)
            .filter(email -> !email.isEmpty());
}
```

Đoạn trên minh họa trường hợp `User.email()` trả `String` có thể `null`. Nếu `email()` thay vì vậy trả `Optional<String>`, cần đổi `map(User::email)` thành `flatMap(User::email)` để tránh `Optional<Optional<String>>`.

Không dùng nhiều lớp Optional chỉ để né việc thiết kế rõ dữ liệu: nếu miền dữ liệu có trạng thái “email chưa khai báo”, cân nhắc cách biểu diễn trạng thái đó trong mô hình trước khi triển khai.

## 8. `or`: fallback tiếp tục trả về Optional

Đôi khi nguồn dữ liệu chính không có kết quả và ta muốn thử nguồn dự phòng **mà chưa vội biến Optional thành giá trị thô**.

```java
Optional<String> fromCache = Optional.empty();

Optional<String> result = fromCache
        .or(() -> Optional.of("giá trị từ cấu hình dự phòng"));

System.out.println(result.orElse("không tìm thấy"));
// giá trị từ cấu hình dự phòng
```

`or(Supplier<Optional<T>>)` chỉ chạy supplier khi Optional ban đầu rỗng. Supplier phải trả về một Optional khác `null`.

Phân biệt:

| Phương thức | Kết quả | Kết quả của supplier |
| --- | --- | --- |
| `orElse(value)` | `T` | Không dùng supplier |
| `orElseGet(() -> value)` | `T` | Một giá trị `T` |
| `or(() -> Optional.of(value))` | `Optional<T>` | Một `Optional<T>` |

Ví dụ chuỗi nguồn:

```java
Optional<String> title = findLocalTitle()
        .or(() -> findGlobalTitle())
        .or(() -> Optional.of("Mặc định"));
```

Tất cả `find...` trong đoạn này giả định trả Optional; chỉ những nguồn dự phòng thật sự cần mới được gọi. Thao tác này giữ lại khả năng **tiếp tục chuỗi biến đổi** vì kết quả vẫn là `Optional<String>`.

## 9. `ifPresent` và `ifPresentOrElse`: xử lý nhánh bằng Consumer/Runnable

Khi mục đích không phải tạo giá trị trả về, mà là **thực hiện hành động**, `ifPresent` và `ifPresentOrElse` thường dễ đọc.

```java
Optional<String> email = Optional.of("lan@example.com");

email.ifPresent(address ->
        System.out.println("Gửi thông báo tới " + address));
```

Tham số của `ifPresent` là `Consumer<T>`: nhận giá trị, thực hiện hành động và trả `void`.

```java
Optional<String> name = Optional.empty();

name.ifPresentOrElse(
        value -> System.out.println("Tên: " + value),
        () -> System.out.println("Chưa có tên")
);
```

`ifPresentOrElse` nhận:

- `Consumer<T>` cho trường hợp có giá trị.
- `Runnable` cho trường hợp rỗng (không nhận đối số, trả `void`).

Chỉ một trong hai hành động được thực hiện.

**Lưu ý về tác dụng phụ:** gửi email, cập nhật trạng thái hoặc ghi log bên trong `ifPresent` chỉ diễn ra khi có giá trị. Nếu một hành động audit **phải luôn chạy**, hãy viết thành một câu lệnh tường minh nằm ngoài nhánh phụ thuộc vào Optional.

### 9.1. Không cố lấy giá trị trả về từ `ifPresent`

```java
// Không biên dịch: ifPresent trả void, không trả String.
// String result = email.ifPresent(e -> e.toUpperCase());
```

Nếu cần một giá trị `String`, dùng `map` và `orElse`/`orElseGet`. Nếu cần cả hai nhánh xử lý điều khiển phức tạp, một câu lệnh `if/else` thông thường cũng có thể dễ bảo trì hơn.

## 10. Kết hợp Optional với Stream

`Optional.stream()` trả về một `Stream<T>`:

- Có giá trị: stream tuần tự chứa **một phần tử**.
- Rỗng: stream **không có phần tử**.

Đây là cách hiện đại để loại bỏ những kết quả tra cứu không tồn tại mà không gọi `get()`:

```java
import java.util.List;
import java.util.Optional;

List<Optional<String>> names = List.of(
        Optional.of("Lan"),
        Optional.empty(),
        Optional.of("Minh")
);

List<String> presentNames = names.stream()
        .flatMap(Optional::stream)
        .toList();

System.out.println(presentNames); // [Lan, Minh]
```

Chuỗi phương thức:

1. `names.stream()` tạo stream gồm ba Optional.
2. `Optional::stream` chuyển mỗi Optional thành stream có 0 hoặc 1 phần tử.
3. `flatMap` ghép các stream con thành một stream giá trị hiện diện.
4. `toList()` thu thập các giá trị vào danh sách.

### 10.1. Các phép tìm kiếm trong Stream thường trả Optional

```java
import java.util.List;
import java.util.Optional;

List<String> tags = List.of("java", "jdk", "optional");

Optional<String> firstLongTag = tags.stream()
        .filter(tag -> tag.length() > 5)
        .findFirst();

System.out.println(firstLongTag.orElse("không có"));
// optional
```

`findFirst()` trả Optional vì có thể không tồn tại phần tử thỏa điều kiện. Với stream có thể xử lý song song, `findAny()` có thể chọn một phần tử bất kỳ thích hợp; không nên giả định luôn lấy phần tử đầu tiên.

Stream và Optional có vai trò khác nhau:

- `Stream<T>` mô tả một chuỗi dữ liệu có thể có nhiều phần tử, với các phép xử lý tổng hợp và thường là lazy.
- `Optional<T>` mô tả sự hiện diện/vắng mặt của **một giá trị**; `map`/`flatMap` của Optional hoạt động khi gọi, không trì hoãn toàn bộ pipeline tới terminal operation.

### 10.2. `Optional<List<T>>` và `List<T>` rỗng không giống nhau

Hãy xác định ý nghĩa nghiệp vụ:

```java
List<String> tasks = List.of(); // Danh sách đã biết và hiện rỗng.
```

Với API “lấy toàn bộ tác vụ” trong một trường hợp bình thường, trả danh sách rỗng thường rõ ràng hơn `Optional.empty()`.

Nhưng đôi khi cần phân biệt:

- **Chưa có dữ liệu**: không có snapshot để đọc.
- **Đã có dữ liệu**: snapshot hiện chứa 0, 1 hoặc nhiều bản ghi.

Khi cả hai trạng thái khác nhau về nghiệp vụ, `Optional<List<T>>` có thể có ý nghĩa. Đừng dùng nó chỉ để “an toàn hơn” khi trường hợp rỗng đã được `List.of()` biểu diễn đầy đủ.

## 11. Optional cho kiểu nguyên thủy: `OptionalInt`, `OptionalLong`, `OptionalDouble`

Java cung cấp các lớp chuyên biệt:

| Kiểu | Có giá trị | Lấy giá trị bắt buộc | Stream |
| --- | --- | --- | --- |
| `OptionalInt` | `OptionalInt.of(27)` | `getAsInt()` hoặc `orElseThrow()` | `IntStream` |
| `OptionalLong` | `OptionalLong.of(100L)` | `getAsLong()` hoặc `orElseThrow()` | `LongStream` |
| `OptionalDouble` | `OptionalDouble.of(3.14)` | `getAsDouble()` hoặc `orElseThrow()` | `DoubleStream` |

Các lớp này tránh phải bọc giá trị nguyên thủy trong `Integer`, `Long` hoặc `Double` chỉ để chứa trong Optional.

```java
import java.util.OptionalInt;

static OptionalInt findAge(boolean known) {
    return known ? OptionalInt.of(27) : OptionalInt.empty();
}

System.out.println(findAge(true).orElse(-1));  // 27
System.out.println(findAge(false).orElse(-1)); // -1
```

Các lớp chuyên biệt **không có tập phương thức hoàn toàn giống** `Optional<T>`; ví dụ, `OptionalInt` không cung cấp `map`/`flatMap` tổng quát như `Optional<T>`. Hãy đọc đúng API khi cần biến đổi dữ liệu.

Với kết quả từ stream nguyên thủy:

```java
OptionalInt minimum = java.util.stream.IntStream
        .of(4, 8, 2)
        .min();

System.out.println(minimum.orElseThrow()); // 2
```

**Không dùng giá trị lính canh** như `-1` nếu `-1` có thể là một giá trị hợp lệ và người gọi cần phân biệt vắng mặt. `OptionalInt.empty()` diễn tả rõ hơn trường hợp không có kết quả.

## 12. Thiết kế API: lúc nào nên và không nên dùng Optional?

Javadoc Java SE 27 ghi rõ `Optional` **chủ yếu dùng làm kiểu trả về của phương thức** khi có nhu cầu biểu diễn “không có kết quả” và việc dùng `null` dễ gây lỗi. Đây là định hướng API quan trọng, không phải quy tắc rằng mọi giá trị có thể `null` đều phải được bọc.

### 12.1. Những nơi thường phù hợp

- Phương thức `findById`, `findFirstMatching`, `lookupConfig` khi không tìm thấy là bình thường.
- Thuộc tính **tính ra từ phương thức** có thể không có, ví dụ `Optional<String> findPreferredEmail()`.
- Chuỗi biến đổi có nhiều bước phụ thuộc vào việc bước trước tìm thấy giá trị.
- Ranh giới giữa API có thể trả `null` và phần code mới muốn dùng kiểu biểu diễn sự vắng mặt tường minh.

### 12.2. Những nơi không nên mặc định dùng

**Tham số phương thức:** Thay vì:

```java
// Thường khó gọi hơn và ít rõ nghĩa:
// void sendNotice(String message, Optional<String> title);
```

Có thể cân nhắc overload, kiểu yêu cầu riêng hoặc một tham số nullable **được ghi rõ contract** ở ranh giới nội bộ phù hợp. Với dữ liệu có nhiều trường tùy chọn, một request object với validation hoặc mô hình trạng thái rõ ràng có thể hữu ích hơn ép mọi lời gọi phải viết `Optional.of(...)`.

**Trường của entity/DTO:** `Optional` không phải công cụ mặc định cho mọi field. Cần xét khả năng tương thích serializer, persistence framework và schema. `java.util.Optional` không triển khai `Serializable`. Với DTO/API JSON hoặc entity lưu trữ, hãy thiết kế biểu diễn nullability theo hợp đồng của framework và hệ thống, thay vì tự động khai báo mọi field là `Optional<T>`.

**Collection:** Nếu kết quả là “một danh sách có thể không có phần tử”, trả `List<T>` rỗng thường tốt hơn `Optional<List<T>>`.

**Lỗi:** `Optional.empty()` không chứa thông tin lỗi. Không biến timeout, lỗi kết nối, thiếu quyền hoặc dữ liệu sai thành “không có dữ liệu” mà không có quyết định thiết kế tường minh.

**Giá trị luôn tồn tại:** Không bọc vào `Optional` chỉ để trang trí. Nếu phương thức luôn trả giá trị và không thể vắng mặt, trả `T` và kiểm soát bất biến bằng validation.

### 12.3. Một bảng quyết định

| Yêu cầu trả về | Thiết kế nên xem xét | Lý do |
| --- | --- | --- |
| Tìm một bản ghi, có thể không tìm thấy | `Optional<Record>` | Vắng mặt là kết quả hợp lệ |
| Tìm tất cả bản ghi phù hợp | `List<Record>`, có thể rỗng | Không cần trạng thái thiếu kết quả riêng |
| Tính một giá trị luôn tồn tại | `T` | Không cần vỏ Optional |
| Tính min/max trên tập số có thể rỗng | `OptionalInt`/`OptionalLong`/`OptionalDouble` hoặc `Optional<T>` phù hợp | Tránh giá trị lính canh mơ hồ |
| Trả về dữ liệu hoặc lỗi với lý do cụ thể | Kiểu kết quả có các trạng thái tường minh, hoặc exception | `Optional` không có nhánh lỗi |
| Đầu vào có nhiều tùy chọn độc lập | Request object/overload/model riêng | Tránh danh sách tham số `Optional<T>` khó dùng |
| Entity/DTO dùng persistence/serialization | Mô hình theo schema và framework | `Optional` không tự giải quyết mapping |
| Dữ liệu đầu ra là chuỗi tùy chọn | `Optional<String>`, nhưng quyết định rõ chuỗi rỗng có được coi là vắng mặt không | `""`, chuỗi toàn khoảng trắng và absent có thể là các trạng thái khác nhau |

## 13. Chương trình hoàn chỉnh: tra cứu người dùng và email tùy chọn

Ví dụ sau có thể biên dịch bằng JDK 27, không dùng preview. Nó minh họa:

- `Optional<User>` ở API tra cứu.
- Một thuộc tính `email` có thể `null` trong mô hình nội bộ; phương thức tra cứu chuyển đổi sang `Optional<String>`.
- `map`, `filter`, `orElse`, `orElseGet`, `orElseThrow`, `ifPresentOrElse`.
- `Optional.stream()` trong pipeline.

Tạo file `OptionalDesignDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class OptionalDesignDemo {

    record User(String id, String displayName, String email) {
        User {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(displayName, "displayName");
            // email cố ý được phép null ở mô hình nội bộ.
        }
    }

    static final class UserRepository {
        private final Map<String, User> users = Map.of(
                "u1", new User("u1", "Lan", "lan@example.com"),
                "u2", new User("u2", "Minh", null)
        );

        Optional<User> findById(String id) {
            Objects.requireNonNull(id, "id");
            return Optional.ofNullable(users.get(id));
        }

        Optional<String> findEmail(String id) {
            return findById(id)
                    .map(User::email)
                    .map(String::strip)
                    .filter(email -> !email.isBlank());
        }

        String displayNameOrDefault(String id) {
            return findById(id)
                    .map(User::displayName)
                    .orElse("(không tìm thấy)");
        }

        String contactOrFallback(String id) {
            return findEmail(id).orElseGet(() -> "Liên hệ bộ phận hỗ trợ");
        }

        User requireUser(String id) {
            return findById(id).orElseThrow(
                    () -> new IllegalArgumentException("Không có người dùng: " + id)
            );
        }
    }

    public static void main(String[] args) {
        var repository = new UserRepository();

        System.out.println(repository.displayNameOrDefault("u1"));
        System.out.println(repository.displayNameOrDefault("u3"));

        System.out.println(repository.contactOrFallback("u1"));
        System.out.println(repository.contactOrFallback("u2"));

        repository.findEmail("u1").ifPresentOrElse(
                email -> System.out.println("Có email: " + email),
                () -> System.out.println("Không có email")
        );

        List<String> emails = List.of("u1", "u2", "u3")
                .stream()
                .map(repository::findEmail)
                .flatMap(Optional::stream)
                .toList();

        System.out.println(emails);
        System.out.println(repository.requireUser("u1").id());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 OptionalDesignDemo.java
java OptionalDesignDemo
```

Kết quả:

```text
Lan
(không tìm thấy)
lan@example.com
Liên hệ bộ phận hỗ trợ
Có email: lan@example.com
[lan@example.com]
u1
```

Phân tích:

1. ID `u1` tồn tại: `findById("u1")` trả `Optional<User>` có giá trị.
2. ID `u3` không tồn tại: trả `Optional.empty()`, sau đó `orElse` chọn nhãn mặc định.
3. Email của `u1` có giá trị, chuỗi `map`/`filter` giữ lại nó.
4. `u2` tồn tại nhưng `email == null`: `map(User::email)` trả Optional rỗng; fallback chỉ được tính khi cần.
5. `ifPresentOrElse` chọn hành động tương ứng, không phải biểu thức tạo `String`.
6. Stream chỉ giữ email hiện diện; không giữ Optional rỗng hoặc chuỗi `null`.
7. `requireUser` biến yêu cầu nghiệp vụ “phải có user” thành ngoại lệ mô tả rõ ràng nếu tra cứu thất bại.

**Điểm giới hạn có chủ ý:** `findEmail("u2")` và `findEmail("u3")` đều trả Optional rỗng, mặc dù nguyên nhân khác nhau (“user có nhưng không có email” và “không có user”). Trong hệ thống thực, nếu người gọi **cần phân biệt** hai trạng thái đó, hãy thiết kế kiểu kết quả riêng hoặc cho phép người gọi thực hiện tra cứu hai tầng một cách tường minh. Không nên tự suy diễn nguyên nhân từ `Optional.empty()`.

## 14. Kiểm thử hợp đồng Optional

Với một phương thức trả `Optional<T>`, các trường hợp cần nghĩ đến gồm:

1. **Có dữ liệu:** chứa đúng giá trị cần thiết.
2. **Không có dữ liệu:** trả Optional rỗng, không trả `null`.
3. **Đầu vào không hợp lệ:** có validation hoặc lỗi theo contract.
4. **Lỗi hạ tầng:** không bị giấu thành kết quả rỗng ngoài ý muốn.
5. **Chuỗi biến đổi:** `map`, `filter`, `flatMap` có đúng kết quả khi rỗng và khi có giá trị không?
6. **Fallback:** kiểm tra supplier tốn công chỉ được thực thi khi thực sự thiếu giá trị.
7. **Đồng bộ trạng thái nghiệp vụ:** nếu có nhiều lý do khiến kết quả rỗng, đã thực sự chấp nhận việc gộp chúng chưa?

Ví dụ kiểm tra đơn giản ngay trong Java:

```java
Optional<String> found = Optional.of("Java");
Optional<String> missing = Optional.empty();

assert found.map(String::length).orElse(-1) == 4;
assert missing.map(String::length).isEmpty();
assert missing.orElseGet(() -> "backup").equals("backup");
```

**Lưu ý:** Câu lệnh `assert` trong Java chỉ được thực thi khi bật assertions (ví dụ chạy `java -ea ...`), vì vậy các dòng trên là minh họa ngắn. Khi kiểm thử chính thức, nên dùng framework test mà dự án đã lựa chọn hoặc các kiểm tra thực thi không phụ thuộc việc bật `-ea`.

## 15. Những lỗi phổ biến cần tránh

| Cách dùng | Vì sao có vấn đề | Cách phù hợp |
| --- | --- | --- |
| Phương thức trả `Optional<T>` nhưng đôi khi `return null` | Phá hợp đồng vắng mặt | Trả `Optional.empty()` |
| `Optional.of(nullableValue)` khi không chắc giá trị khác `null` | Có thể ném `NullPointerException` | Dùng `ofNullable` nếu `null` thật sự là absent |
| `optional.get()` mà chưa đảm bảo có giá trị | Ném `NoSuchElementException` | Dùng `orElse`, `orElseGet` hoặc `orElseThrow` rõ ý định |
| `orElse(expensiveFallback())` | Fallback được gọi ngay cả khi đã có giá trị | Dùng `orElseGet(() -> expensiveFallback())` |
| `map(x -> optionalReturningMethod(x))` | Sinh `Optional<Optional<U>>` | Dùng `flatMap` |
| `flatMap(x -> null)` | Mapper vi phạm hợp đồng, gây `NullPointerException` | Trả một Optional không `null` |
| `optional == Optional.empty()` | Phụ thuộc identity không được bảo đảm | `optional.isEmpty()` |
| `synchronized(optional)` | Value-based class không dành cho khóa identity | Dùng cơ chế đồng bộ riêng phù hợp |
| Dùng Optional để che mọi ngoại lệ | Mất thông tin lỗi, gây hiểu nhầm | Phân biệt absent với failure |
| `Optional<List<T>>` cho mọi danh sách có thể rỗng | Thêm trạng thái không cần thiết | Trả `List.of()` khi rỗng đã đủ |
| Dùng Optional làm field/parameter ở mọi nơi | Tăng độ phức tạp; có thể khó tích hợp framework | Ưu tiên dùng ở kiểu trả về, cân nhắc API cụ thể |
| Tin rằng `ifPresent` có thể trả giá trị | `ifPresent` trả `void` | Dùng `map`, `orElse` hay `if/else` |
| Đặt hành động bắt buộc bên trong `map`/`ifPresent` | Có thể bị bỏ qua khi Optional rỗng | Tách side effect bắt buộc khỏi nhánh tùy chọn |
| Biến `filter` sai thành `Optional.empty()` rồi coi như “không tồn tại” | Gộp hai trạng thái nghiệp vụ | Dùng kiểu kết quả giàu ngữ nghĩa hơn nếu cần |

## 16. Checklist lựa chọn Optional trong Java 27

Khi thiết kế một phương thức có thể không trả kết quả:

1. **Vắng mặt có phải là tình huống bình thường?** Nếu có, `Optional<T>` là một ứng viên tốt.
2. **Có cần giải thích vì sao vắng mặt?** Nếu cần nhiều trạng thái lỗi/thiếu, thiết kế kiểu kết quả khác.
3. **Có đang trả một tập dữ liệu nhiều phần tử?** Xem liệu collection rỗng đã diễn tả đầy đủ chưa.
4. **Kiểu trả về có thể tuyệt đối không `null` không?** Mọi nhánh trả về phải giữ hợp đồng này.
5. **Dữ liệu đầu vào có thể `null` không?** Dùng `ofNullable` tại ranh giới phù hợp và kiểm tra các trường hợp nhập sai.
6. **Hàm chuyển đổi trả `U` hay `Optional<U>`?** Chọn `map` hoặc `flatMap` cho đúng.
7. **Fallback có thể đắt hoặc có tác dụng phụ không?** Nếu có, dùng `orElseGet` hoặc `or` để tính khi cần.
8. **Kết quả rỗng có phải lỗi của người gọi?** Dùng `orElseThrow` nếu thực sự yêu cầu phải có dữ liệu ở bước đó.
9. **Chỉ muốn thực hiện một hành động?** Dùng `ifPresent`/`ifPresentOrElse` và bảo đảm các tác dụng phụ bắt buộc nằm ngoài nhánh bị bỏ qua.
10. **Có đang xử lý stream nhiều Optional?** `flatMap(Optional::stream)` là công cụ gọn để chỉ giữ các giá trị hiện diện.
11. **Có cần tối ưu primitive không?** Cân nhắc `OptionalInt`/`OptionalLong`/`OptionalDouble` cho kết quả dạng số.
12. **Có liên quan serialization, ORM hoặc JSON contract không?** Kiểm tra yêu cầu của nền tảng trước khi đưa Optional vào fields/DTO.

**Ghi nhớ:** `Optional<T>` giúp **người cung cấp API công khai rằng kết quả có thể vắng mặt** và **người sử dụng quyết định rõ cách xử lý vắng mặt**. Nó không thay thế validation, lỗi nghiệp vụ, thiết kế mô hình dữ liệu hay cơ chế đồng bộ hóa.

## 17. Tài liệu chính thức Java SE 27

- [`java.util.Optional<T>` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Optional.html): mục đích sử dụng, value-based class, `of`/`ofNullable`/`empty`, `map`, `flatMap`, `filter`, `or`, `orElse`, `orElseGet`, `orElseThrow`, `stream`.
- [`java.util.OptionalInt` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/OptionalInt.html): kết quả số nguyên có thể vắng mặt.
- [`java.util.OptionalLong` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/OptionalLong.html): kết quả kiểu `long` có thể vắng mặt.
- [`java.util.OptionalDouble` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/OptionalDouble.html): kết quả kiểu `double` có thể vắng mặt.
- [`java.util.function` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/function/package-summary.html): các interface hàm `Function`, `Predicate`, `Consumer`, `Supplier` được dùng trong Optional.
- [`java.util.stream.Stream` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html): `findFirst`/`findAny`, stream pipeline và các phép biến đổi.
- [`java.util.Map` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html): ý nghĩa `get` và `containsKey` khi cần phân biệt khóa vắng mặt với giá trị `null`.
