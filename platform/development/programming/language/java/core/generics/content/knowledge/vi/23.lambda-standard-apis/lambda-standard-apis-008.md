# Generic trong `Optional` và quan hệ kiểu khi biến đổi dữ liệu (Java 17)

## 1. Vấn đề: một giá trị có thể không tồn tại, nhưng vẫn cần giữ kiểu

Trong Java, một phép tra cứu có thể **tìm thấy** hoặc **không tìm thấy** dữ liệu. Trả `null` trực tiếp khiến caller phải nhớ kiểm tra và dễ tạo `NullPointerException`:

```java
String name = repository.findName(id); // Có thể là null.
System.out.println(name.length());      // Có thể ném NullPointerException.
```

`java.util.Optional<T>` biểu đạt rõ hơn rằng kết quả có thể vắng mặt:

```java
Optional<String> name = repository.findName(id);
```

Ở đây:

- `Optional` là một generic class.
- `T` là kiểu **giá trị bên trong**, ví dụ `String`, `User`, `Integer`.
- Một `Optional<T>` có thể chứa một giá trị khác `null` thuộc `T`, hoặc **empty**.
- Caller xử lý sự có mặt/vắng mặt bằng các API như `map`, `flatMap`, `filter`, `orElseGet`, `orElseThrow`, `stream`.

Vấn đề Generics xuất hiện khi **biến đổi** dữ liệu: một `Optional<User>` có thể phải thành `Optional<String>`, hay một phép biến đổi có thể đã trả `Optional<Profile>` và cần tránh sinh `Optional<Optional<Profile>>`. Để làm tốt, cần hiểu **quan hệ kiểu giữa input, mapper và output**, cùng sự khác nhau giữa `map` và `flatMap`.

Bài này trình bày cơ chế Generics trong Optional, cú pháp Java 17, type inference, wildcard variance, tập hợp Optional, xử lý null và lỗi phổ biến. Ví dụ chính là một chương trình độc lập đã được biên dịch/chạy với `javac --release 17 -Xlint:all` và đối chiếu stdout.

## 2. Nhận diện đúng hợp đồng của `Optional<T>`

Một `Optional<String>` **không phải** một `String`. Nó là một container có khả năng chứa `String`.

```java
Optional<String> present = Optional.of("Java");
Optional<String> absent = Optional.empty();
```

Để đọc, bạn không thể gán trực tiếp:

```java
// Không biên dịch:
// String text = present;
```

Bạn phải chọn rõ chính sách khi có giá trị hoặc khi empty, chẳng hạn:

```java
String text = present.orElse("N/A");
```

Nhờ vậy, API không còn ngầm yêu cầu caller đoán xem return value có thể là `null` hay không.

### 2.1. Các factory methods

| API | Input | Nếu giá trị là `null` | Kết quả |
| --- | --- | --- | --- |
| `Optional.of(value)` | Một tham chiếu **bắt buộc khác null** | Ném `NullPointerException` | Optional có giá trị |
| `Optional.ofNullable(value)` | Tham chiếu có thể null | Trả `Optional.empty()` | Có giá trị hoặc empty |
| `Optional.empty()` | Không nhận input | Không áp dụng | Optional empty |

Ví dụ:

```java
Optional<String> a = Optional.of("x");
Optional<String> b = Optional.ofNullable(null);
Optional<String> c = Optional.empty();
```

`b` và `c` đều là empty. Không nên so sánh danh tính bằng `==` để phát hiện empty; dùng `isEmpty()`, `isPresent()`, hoặc các thao tác phù hợp.

### 2.2. Optional là value-based class

Tài liệu Java mô tả `Optional` là một **value-based class**. Đừng dựa vào identity, đồng bộ hóa trên Optional instance hoặc suy đoán rằng các empty instances luôn cùng tham chiếu. Quan tâm tới **giá trị/ngữ nghĩa** thông qua API của Optional, không phải việc wrapper object có identity nào.

### 2.3. `Optional` không thay thế mọi đối tượng và collection

Nếu kết quả tự nhiên là “không có phần tử nào”, một `List<T>` rỗng thường đủ rõ. `Optional<List<T>>` lại có **hai trạng thái khác nhau**:

- `Optional.empty()` — không có kết quả danh sách.
- `Optional.of(List.of())` — có kết quả danh sách, nhưng danh sách rỗng.

Chỉ dùng hai tầng này nếu sự phân biệt có ý nghĩa nghiệp vụ. Đừng biến mọi giá trị của codebase thành `Optional<T>` một cách máy móc.

## 3. `Optional<T>` là generic bất biến (invariant)

Java Generics không tự động covariant chỉ vì các type arguments có quan hệ subtype.

```java
Integer number = 7;
Number parent = number; // Hợp lệ.
```

Nhưng một biến đã xác định kiểu:

```java
Optional<Integer> integers = Optional.of(7);

// Không biên dịch:
// Optional<Number> numbers = integers;
```

`Optional<Integer>` **không phải subtype** của `Optional<Number>`. Điều này cũng tương tự `List<Integer>` không tự là `List<Number>`.

### 3.1. Vì sao `Optional<Number> x = Optional.of(7)` lại biên dịch?

Đây là chi tiết quan trọng về **generic method inference**:

```java
Optional<Number> numbers = Optional.of(7);
```

Đoạn này **hợp lệ** trên Java 17. `Optional.of` là generic factory method:

```java
public static <T> Optional<T> of(T value)
```

Khi suy luận `T`, compiler có thể cân nhắc **kiểu đích `Optional<Number>`** bên cạnh `Integer` value đã boxing. Nó chọn type argument đáp ứng các ràng buộc của lời gọi và assignment.

Điều đó **không làm Generic Java covariant**. Nếu kết quả đã được lưu vào một biến `Optional<Integer>`, bạn không thể gán biến đó thẳng sang `Optional<Number>`.

So sánh rõ:

```java
Optional<Number> direct = Optional.of(7); // Hợp lệ.

Optional<Integer> integers = Optional.of(7);
// Optional<Number> reassigned = integers; // Không hợp lệ.
```

Đây là khác biệt giữa **suy luận kiểu khi tạo một giá trị generic mới** và **quan hệ subtype giữa hai parameterized types đã xác định**.

### 3.2. Dùng wildcard khi chỉ cần đọc kiểu cha

Nếu một method chỉ cần đọc Number:

```java
static double doubled(Optional<? extends Number> input) {
    return input.map(n -> n.doubleValue() * 2).orElse(0.0);
}
```

Caller có thể truyền `Optional<Integer>` hoặc `Optional<Double>`:

```java
double a = doubled(Optional.of(7));
double b = doubled(Optional.of(1.5));
```

`? extends Number` biểu thị phần tử được đảm bảo là một subtype nào đó của `Number`, phù hợp với mục đích **producer**: ta đọc một `Number` và gọi `doubleValue()`.

Không viết `Optional<Number>` nếu thực tế method muốn nhận nhiều loại Optional chứa các subtype mà không có nhu cầu thay đổi wrapper/giá trị đầu vào.

### 3.3. Khi cần `Optional<Number>` thật sự

Bạn có thể biến đổi tường minh:

```java
Optional<Integer> ints = Optional.of(7);
Optional<Number> numbers = ints.map(n -> (Number) n);
```

Đây là **tạo một Optional mới về mặt kết quả API**, không phải một phép gán covariant giữa hai biến generic đã xác định. Lambda cho compiler biết kiểu trả về mapper là `Number`, dẫn tới `U = Number` cho `map`.

Một phương án khác trong ngữ cảnh phù hợp là type witness/cung cấp target type khi tạo Optional mới. Nhưng đừng xem type witness là cách bỏ qua mọi quan hệ generic bị cấm.

## 4. Chữ ký generic của `map`: từ `T` sang `U`

Trên Java 17, chữ ký quan trọng của `Optional<T>` là:

```java
public <U> Optional<U> map(
        Function<? super T, ? extends U> mapper)
```

Tách thành bốn phần:

1. `T` là **kiểu hiện tại** của Optional.
2. `<U>` là **type parameter mới của method `map`**: kiểu kết quả sau biến đổi.
3. `Function<? super T, ? extends U>` nhận một giá trị thích hợp cho `T`, trả một giá trị tương thích `U`.
4. `Optional<U>` là wrapper của **kết quả đã biến đổi**.

Ví dụ:

```java
Optional<String> name = Optional.of("Java");
Optional<Integer> length = name.map(String::length);
```

Trước `map`: `T = String`.

Mapper: `String -> Integer` (kết quả primitive `int` được boxing).

Sau `map`: `U = Integer`, kết quả là `Optional<Integer>`.

Không có cast trong mã caller. Compiler bảo toàn quan hệ kiểu qua functional interface và generic type inference.

### 4.1. Vì sao input của Function là `? super T`?

`? super T` cho phép mapper có thể nhận **một kiểu cha** của `T`, vì mapper đóng vai trò **consumer** của giá trị được Optional đưa vào.

Ví dụ:

```java
Function<Object, String> stringify = Object::toString;
Optional<String> input = Optional.of("Java");

Optional<String> output = input.map(stringify);
```

Dù mapper nhận `Object`, nó vẫn có thể xử lý một `String`. Không cần buộc `Function<String,String>` nếu một `Function<Object,String>` đã đủ năng lực.

### 4.2. Vì sao output của Function là `? extends U`?

Kết quả mapper là một **producer** của `U`: có thể trả một subtype phù hợp, chứ không nhất thiết phải có chữ ký trả đúng `U` ở mọi declaration.

Đây là cách dùng quy tắc **PECS**: *Producer Extends, Consumer Super*. Tuy nhiên PECS là mẹo nhớ hướng wildcard, không thay thế việc hiểu ngữ nghĩa của `Function` và ràng buộc inference.

### 4.3. Một generic helper dùng `map`

```java
static <T, U> Optional<U> transform(
        Optional<T> input,
        Function<? super T, ? extends U> mapper) {
    return input.map(mapper);
}
```

Caller:

```java
Optional<Integer> length =
        transform(Optional.of("abc"), CharSequence::length);
```

Ở đây `CharSequence::length` có thể nhận String vì String triển khai CharSequence. Kết quả được boxing thành `Integer`. Java 17 đã biên dịch ví dụ này và chương trình in:

```text
transform=3
```

Một thiết kế generic helper vẫn nên kiểm tra input hoặc mapper null theo contract riêng, thay vì cho rằng annotation type parameters tự động ngăn tham chiếu null.

## 5. `map` chỉ thực thi mapper khi có giá trị

Với:

```java
Optional<String> name = Optional.of(" Java ");
Optional<String> normalized = name.map(String::strip);
```

Mapper nhận `" Java "` và trả `"Java"`.

Nếu đầu vào empty:

```java
Optional<String> empty = Optional.<String>empty();
Optional<Integer> result = empty.map(String::length);
```

`result` vẫn empty; lambda/method reference không được gọi.

Đây là cách viết pipeline mà mỗi bước chỉ chạy khi các bước trước thực sự có dữ liệu. Không cần viết nhiều tầng `if (value != null)` chỉ để truyền kết quả qua các phép biến đổi tuần tự.

### 5.1. `map` nhận kết quả null thì sao?

Một khác biệt tinh tế:

```java
Optional<String> result =
        Optional.of("x").map(x -> (String) null);

System.out.println(result.isEmpty()); // true
```

`map` dùng ngữ nghĩa tương đương `ofNullable` trên **kết quả mapper**: nếu mapper trả `null`, Optional kết quả trở thành empty. Nó không tạo `Optional` “có giá trị null”.

Nhưng nếu **mapper argument là null**:

```java
// Không hợp lệ tại runtime:
// Optional.of("x").map(null);
```

method từ chối mapper null bằng `NullPointerException`. Hãy phân biệt “mapper trả null” và “mapper là null”.

### 5.2. `map` không tự nuốt exception

Nếu mapper ném `NumberFormatException`:

```java
Optional<Integer> number =
        Optional.of("not-an-int").map(Integer::parseInt);
```

Exception vẫn lan ra caller. Optional **không** chuyển mọi exception thành empty.

Nếu “không parse được” là trạng thái nghiệp vụ bình thường, hãy viết mapper hoặc helper chuyển đổi riêng có xử lý lỗi rõ ràng, ví dụ trả `Optional<Integer>` và dùng `flatMap`.

## 6. `filter`: lọc nhưng không thay kiểu `T`

Chữ ký tương ứng:

```java
public Optional<T> filter(Predicate<? super T> predicate)
```

`filter` chỉ kiểm tra điều kiện trên giá trị hiện có:

```java
Optional<String> candidate = Optional.of("  Java  ");

Optional<String> nonBlank = candidate
        .map(String::strip)
        .filter(s -> !s.isEmpty());
```

Nếu predicate trả true, giữ giá trị; nếu false, chuyển thành empty. Nếu Optional đã empty, predicate không chạy.

**Kiểu kết quả vẫn là `Optional<T>`**, khác với `map` có thể đổi `T` thành `U`.

Ví dụ:

```java
Optional<Integer> positive = Optional.of(7)
        .filter(n -> n > 0);
```

`positive` là `Optional<Integer>`, không có `U` mới được tạo bởi `filter`.

### 6.1. Thứ tự thao tác có ý nghĩa

```java
Optional<String> cleaned = Optional.of("  ")
        .map(String::strip)
        .filter(s -> !s.isBlank());
```

Chuỗi `"  "` được strip thành `""`, rồi filter loại bỏ. Với một pipeline khác hoặc điều kiện khác, dữ liệu có thể được xử lý khác. `map` và `filter` không phải phép hoán đổi thứ tự tùy ý.

## 7. `map` tạo Optional lồng nhau khi mapper đã trả Optional

Giả sử tìm thông tin User:

```java
record Profile(String city) {}
record User(String name, Optional<Profile> profile) {}

static Optional<User> findUser(int id) {
    if (id == 1) {
        return Optional.of(new User(
                "Lan", Optional.of(new Profile("Hanoi"))));
    }
    return Optional.empty();
}
```

Bạn muốn tìm `Profile` từ `Optional<User>`.

Nếu dùng `map`:

```java
Optional<Optional<Profile>> nested =
        findUser(1).map(User::profile);
```

Vì method `User.profile()` **đã trả `Optional<Profile>`**, generic inference của `map` xác định:

- Input `T = User`.
- Mapper result `U = Optional<Profile>`.
- Return `Optional<U> = Optional<Optional<Profile>>`.

Hai tầng Optional có nghĩa hai cấu trúc vắng mặt được lồng nhau. Trường hợp này thường **không cần thiết** trong pipeline tra cứu dữ liệu.

### 7.1. Phân biệt hai `map` có chữ ký giống tên

`Optional<User>.map(User::name)` hợp lý nếu `User.name()` trả một `String`.

Nhưng `Optional<User>.map(User::profile)` sinh nested Optional nếu `User.profile()` trả `Optional<Profile>`.

Sự khác biệt đến từ **kiểu trả về thật của mapper**; không phải compiler ngẫu nhiên thêm một lớp Optional.

## 8. `flatMap`: phép biến đổi đã trả Optional

Chữ ký `flatMap` trong Java 17:

```java
public <U> Optional<U> flatMap(
    Function<? super T, ? extends Optional<? extends U>> mapper)
```

Điều quan trọng nhất:

- Mapper nhận một giá trị tương thích `T`.
- Mapper **phải trả `Optional`** chứa kiểu tương thích với `U`.
- `flatMap` không bọc Optional thêm một tầng nữa; kết quả cuối là `Optional<U>`.

Ví dụ:

```java
Optional<Profile> profile =
        findUser(1).flatMap(User::profile);
```

Thay vì `Optional<Optional<Profile>>`, ta nhận trực tiếp `Optional<Profile>`.

Muốn lấy city:

```java
Optional<String> city = findUser(1)
        .flatMap(User::profile)
        .map(Profile::city);
```

Pipeline làm ba việc theo kiểu tĩnh:

1. `findUser(1)` có kiểu `Optional<User>`.
2. `.flatMap(User::profile)` thành `Optional<Profile>`.
3. `.map(Profile::city)` thành `Optional<String>`.

Nếu một bước empty, các bước sau không nhận giá trị để chạy và toàn pipeline trả empty.

### 8.1. Tại sao chữ ký của `flatMap` có hai dấu `extends`?

`? super T` biểu đạt mapper có thể chấp nhận một kiểu rộng hơn `T`.

`? extends Optional<? extends U>` biểu đạt mapper có thể tạo một subtype hợp lệ của kiểu Optional container, bên trong chứa subtype tương thích với `U`. Signature giúp nhiều cách viết mapper và quan hệ subtype không phải cast thủ công.

Để dùng hiệu quả, thường không cần học thuộc nguyên văn cả signature; chỉ cần ghi nhớ **Function phải trả Optional** và compiler có thể suy luận `U` từ kiểu của giá trị bên trong.

### 8.2. `flatMap` từ chối mapper trả null

Khác với `map`:

```java
Optional.of("x")
        .flatMap(s -> (Optional<String>) null);
```

với Optional có giá trị sẽ ném `NullPointerException`. Mapper của `flatMap` phải trả một **Optional object** khác null: có giá trị hoặc `Optional.empty()`.

Nếu muốn biểu thị vắng mặt, trả:

```java
Optional.<String>empty()
```

Không trả `null`.

### 8.3. `flatMap` không phải `map` có tên khác

Nếu mapper trả một giá trị thường, ví dụ `Integer.parseInt(s)` có kiểu `int`/`Integer`, thì dùng:

```java
Optional<Integer> number =
        Optional.of("7").map(Integer::parseInt);
```

Không dùng:

```java
// Không biên dịch:
// Optional.of("7").flatMap(Integer::parseInt);
```

Compiler báo `int cannot be converted to Optional<? extends U>` vì chữ ký `flatMap` yêu cầu mapper trả Optional.

## 9. Chọn `map` hay `flatMap` theo kiểu trả về mapper

| Kiểu ban đầu | Mapper | Dùng | Kiểu kết quả |
| --- | --- | --- | --- |
| `Optional<String>` | `String -> Integer` | `map` | `Optional<Integer>` |
| `Optional<User>` | `User -> String` | `map` | `Optional<String>` |
| `Optional<User>` | `User -> Optional<Profile>` | `map` | `Optional<Optional<Profile>>` |
| `Optional<User>` | `User -> Optional<Profile>` | `flatMap` | `Optional<Profile>` |
| `Optional<Profile>` | `Profile -> String` | `map` | `Optional<String>` |
| `Optional<T>` | `T -> boolean` | `filter` dùng `Predicate` | `Optional<T>` giữ hoặc empty |

Một mẹo kiểm tra nhanh:

- Mapper trả **`U`** → `map`, Optional sẽ bọc `U`.
- Mapper trả **`Optional<U>`** → `flatMap`, tránh wrapper lồng nhau.
- Chỉ kiểm tra đúng/sai trên `T` → `filter`.

Không thay `flatMap` bằng `.map(...).get()` để “bóc” Optional. `.get()` trên empty ném `NoSuchElementException`, làm mất lợi ích của pipeline an toàn.

## 10. Biến đổi dữ liệu qua nhiều lớp Optional

Ví dụ tìm thành phố của User:

```java
static Optional<String> cityFor(int id) {
    return findUser(id)
            .flatMap(User::profile)
            .map(Profile::city);
}
```

Nếu `findUser(1)` có User, Profile và city, kết quả là `Optional.of("Hanoi")`.

Nếu `findUser(9)` empty, kết quả empty. Caller chọn giá trị fallback:

```java
String city = cityFor(9).orElse("?");
```

Nếu User tồn tại nhưng `profile()` empty, `flatMap` cũng cho empty. Đây là chain biến đổi **không cần** nhiều if/else lồng nhau.

### 10.1. Có thể mất thông tin về lý do vắng mặt

Một pipeline Optional thường chỉ ghi nhận “có giá trị” hoặc “empty”; nó không giải thích:

- User không tồn tại.
- User có nhưng chưa có Profile.
- Profile có nhưng city chưa được cung cấp.

Nếu ứng dụng cần phân biệt những trạng thái này cho log/API errors, `Optional<T>` có thể không đủ. Cân nhắc một kết quả domain có mã trạng thái, sealed hierarchy hoặc kiểu Result/Either do ứng dụng/thư viện cung cấp.

### 10.2. Đừng gọi Optional một “effect/exception monad” tùy tiện

`map`/`flatMap` mang mô hình biến đổi container hữu ích, nhưng `Optional` của Java không tự gói checked exceptions, không tích lũy lỗi validation và không có logging/transaction semantics. Khi cần những yêu cầu đó, bổ sung abstraction thích hợp thay vì lạm dụng `.orElse(null)`.

## 11. `Optional.or`: fallback cũng là Optional

Java 9+ có method:

```java
public Optional<T> or(
    Supplier<? extends Optional<? extends T>> supplier)
```

Nếu Optional hiện có giá trị, trả lại Optional hiện tại. Nếu empty, gọi Supplier để lấy một **Optional fallback**, không chỉ một giá trị `T`.

```java
Optional<String> result = Optional.<String>empty()
        .or(() -> Optional.of("alternate"));
```

`result` là `Optional<String>` có giá trị `"alternate"`.

Phân biệt:

- `orElse(T other)`: trả **T**; fallback được đánh giá trước lời gọi theo quy tắc Java.
- `orElseGet(Supplier<? extends T>)`: trả **T**; Supplier chỉ được gọi khi empty.
- `or(Supplier<? extends Optional<? extends T>>)`: trả **Optional<T>**; Supplier phải trả một Optional khác null khi được gọi.

`or` hữu ích cho chuỗi tìm nguồn khác:

```java
Optional<String> value = fromCache()
        .or(() -> fromDatabase());
```

Đây là đoạn minh họa khi hai helper `fromCache()` và `fromDatabase()` trả Optional tương thích. Nếu cache có giá trị, supplier thứ hai không chạy.

## 12. `orElse` và `orElseGet`: eager so với lazy

Giả sử:

```java
Optional<String> existing = Optional.of("ready");
```

Hai lệnh trông giống nhau về kết quả:

```java
String a = existing.orElse(computeFallback());
String b = existing.orElseGet(() -> computeFallback());
```

Nhưng cách đánh giá khác:

- `orElse(computeFallback())`: Java phải **đánh giá đối số `computeFallback()` trước khi gọi** `orElse`, kể cả khi Optional đã có giá trị.
- `orElseGet(() -> computeFallback())`: truyền Supplier; `computeFallback()` chỉ chạy nếu Optional empty.

Ví dụ dùng counter:

```java
AtomicInteger calls = new AtomicInteger();

String eager =
        existing.orElse(expensiveFallback(calls));
String lazy =
        existing.orElseGet(() -> expensiveFallback(calls));
```

Nếu `expensiveFallback` tăng counter, sau hai lệnh counter là `1`. Cả `eager` và `lazy` đều bằng `"ready"`, nhưng eager fallback đã chạy một lần.

Khi:

```java
Optional.<String>empty()
        .orElseGet(() -> expensiveFallback(calls));
```

supplier chạy và counter tăng thành `2`.

### 12.1. Quy tắc chọn đơn giản

Dùng `orElse("N/A")` cho constant hoặc giá trị rẻ, đã sẵn có.

Dùng `orElseGet(this::expensiveLookup)` khi fallback cần tính toán, truy cập hệ thống khác, ghi log, tạo object tốn kém hoặc có side effect chỉ nên thực thi lúc empty.

Không phải `orElseGet` “nhanh hơn tuyệt đối” trong mọi trường hợp; khác biệt cốt lõi là **thời điểm thực thi fallback** và semantic side effects.

### 12.2. `orElseThrow` khi thiếu là lỗi

Nếu giá trị bắt buộc phải tồn tại:

```java
String name = optionalName.orElseThrow(
        () -> new IllegalStateException("Name missing"));
```

Còn `optionalName.orElseThrow()` (Java 10+) ném `NoSuchElementException` nếu empty.

Dùng exception chỉ khi thiếu giá trị là trường hợp thật sự bất thường theo contract; không ném rồi catch ngay chỉ để mô phỏng điều kiện thường gặp.

## 13. `ifPresent`, `ifPresentOrElse` và `get()`

Đôi khi thay vì biến đổi Optional thành Optional khác, bạn muốn thực hiện tác vụ:

```java
optionalName.ifPresent(System.out::println);
```

`ifPresent` nhận `Consumer<? super T>`, trả `void`. Không nên dùng nó thay `map` khi bạn muốn giá trị biến đổi tiếp.

Java 9+ có:

```java
optionalName.ifPresentOrElse(
        value -> System.out.println(value),
        () -> System.out.println("missing"));
```

Một action chạy khi có giá trị và một Runnable chạy khi empty.

`Optional.get()` có thể trả giá trị khi present nhưng ném `NoSuchElementException` khi empty. Với code mới, thường rõ hơn nếu dùng `orElseThrow`, hoặc biến đổi bằng `map`/`flatMap` và xử lý fallback một lần ở ranh giới.

### 13.1. Anti-pattern: dùng `isPresent()` rồi `get()` khắp nơi

```java
if (maybeUser.isPresent()) {
    User user = maybeUser.get();
    // ...
}
```

Không phải lúc nào cũng sai, nhưng với một phép biến đổi đơn giản có thể rõ và nhất quán hơn:

```java
Optional<String> name = maybeUser.map(User::name);
```

`map` giữ logic trong pipeline, không phải viết kiểm tra empty ở mỗi bước. Dùng `ifPresent` khi thật sự muốn side effect thay vì biến đổi return value.

## 14. `Optional.stream()` giúp phối hợp với `Stream<T>`

Java 9+ bổ sung:

```java
Stream<T> stream()
```

- Optional có giá trị → Stream có đúng **một** phần tử.
- Optional empty → Stream rỗng.

Điều này giúp flatten một stream các Optional:

```java
List<Integer> found = Stream.of(
        Optional.of(2),
        Optional.<Integer>empty(),
        Optional.of(5))
    .flatMap(Optional::stream)
    .toList();
```

Java 17 in:

```text
stream=[2, 5]
```

Ở đây `Stream.flatMap` khác `Optional.flatMap` nhưng có ý tưởng tương tự: mapper tạo một structure phù hợp, còn `flatMap` gộp các structures kết quả để tránh các tầng lồng không cần thiết.

`Stream.toList()` có từ Java 16 và trả danh sách unmodifiable theo hợp đồng API. Nếu cần mutable list, chọn collector hoặc cấu trúc copy có chủ đích.

### 14.1. `List<Optional<T>>` so với `Optional<List<T>>`

`List<Optional<String>>` nghĩa là **nhiều vị trí**, mỗi vị trí có thể có hoặc thiếu string.

`Optional<List<String>>` nghĩa là **toàn bộ kết quả list có thể có hoặc thiếu**, nhưng nếu present thì phần tử của list được quy định bởi generic `String`.

Để bỏ vị trí empty trong `List<Optional<T>>`:

```java
List<String> names = optionals.stream()
        .flatMap(Optional::stream)
        .toList();
```

Đoạn này giả định `optionals` là `List<Optional<String>>`. Nó giữ các present values và bỏ các empty entries; do đó **mất thông tin vị trí nào ban đầu thiếu**. Nếu vị trí có ý nghĩa nghiệp vụ, không nên flatten kiểu này mà không lưu index hoặc trạng thái riêng.

## 15. Ví dụ Java 17 chạy được: biến đổi Optional và Generics

Tạo tệp **`OptionalGenericsDemo.java`**:

```java
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;
import java.util.stream.Stream;

public class OptionalGenericsDemo {
    record Profile(String city) {}
    record User(String name, Optional<Profile> profile) {}

    static Optional<User> findUser(int id) {
        if (id == 1) {
            return Optional.of(new User(
                    "  Lan  ", Optional.of(new Profile("Hanoi"))));
        }
        return Optional.empty();
    }

    static Optional<String> cityFor(int id) {
        return findUser(id).flatMap(User::profile)
                .map(Profile::city);
    }

    static <T, U> Optional<U> transform(
            Optional<T> input,
            Function<? super T, ? extends U> mapper) {
        return input.map(mapper);
    }

    static Optional<Number> toNumber(Optional<Integer> input) {
        return input.map(n -> (Number) n);
    }

    static double doubled(Optional<? extends Number> input) {
        return input.map(n -> n.doubleValue() * 2)
                .orElse(0.0);
    }

    static String expensiveFallback(AtomicInteger calls) {
        calls.incrementAndGet();
        return "fallback";
    }

    public static void main(String[] args) {
        Optional<String> raw = Optional.ofNullable("  Java  ");
        Optional<Integer> length = raw.map(String::strip)
                .filter(s -> !s.isEmpty())
                .map(String::length);
        System.out.println("length=" + length.orElse(-1));

        System.out.println("map-null-empty="
                + Optional.of("x")
                .map(x -> (String) null).isEmpty());

        Optional<Optional<Profile>> nested =
                findUser(1).map(User::profile);
        System.out.println("nested=" + nested.isPresent());
        System.out.println("city=" + cityFor(1).orElse("?"));
        System.out.println("missing-city=" + cityFor(9).orElse("?"));

        System.out.println("transform="
                + transform(Optional.of("abc"),
                        CharSequence::length).orElse(-1));

        System.out.println("number="
                + toNumber(Optional.of(7)).orElse(-1));
        System.out.println("covariant="
                + doubled(Optional.of(7)));

        List<Integer> values = Stream.of(
                Optional.of(2),
                Optional.<Integer>empty(),
                Optional.of(5))
                .flatMap(Optional::stream).toList();
        System.out.println("stream=" + values);

        Optional<String> restored = Optional.<String>empty()
                .or(() -> Optional.of("alternate"));
        System.out.println("or=" + restored.orElse("?"));

        AtomicInteger calls = new AtomicInteger();
        Optional<String> existing = Optional.of("ready");
        String eager = existing.orElse(expensiveFallback(calls));
        String lazy = existing.orElseGet(
                () -> expensiveFallback(calls));

        System.out.println("fallback=" + eager + ","
                + lazy + "," + calls.get());

        System.out.println("empty-lazy="
                + Optional.<String>empty()
                .orElseGet(() -> expensiveFallback(calls))
                + "," + calls.get());

        List<String> names = Stream.of("a", "", "bc")
                .map(OptionalGenericsDemo::nonBlank)
                .flatMap(Optional::stream).toList();
        System.out.println("names=" + names);

        try {
            Optional.of("x")
                    .flatMap(x -> (Optional<String>) null);
        } catch (NullPointerException e) {
            System.out.println("flatmap-null="
                    + e.getClass().getSimpleName());
        }

        try {
            Optional.ofNullable(null).orElseThrow();
        } catch (java.util.NoSuchElementException e) {
            System.out.println("empty-get="
                    + e.getClass().getSimpleName());
        }
    }

    static Optional<String> nonBlank(String text) {
        return Optional.ofNullable(text)
                .map(String::strip)
                .filter(x -> !x.isEmpty());
    }
}
```

Chạy từ thư mục chứa file:

```bash
javac --release 17 -Xlint:all OptionalGenericsDemo.java
java OptionalGenericsDemo
```

Chương trình đã được biên dịch thành công trên Java 17, không có warning với `-Xlint:all`. **Stdout chính xác**:

```text
length=4
map-null-empty=true
nested=true
city=Hanoi
missing-city=?
transform=3
number=7
covariant=14.0
stream=[2, 5]
or=alternate
fallback=ready,ready,1
empty-lazy=fallback,2
names=[a, bc]
flatmap-null=NullPointerException
empty-get=NoSuchElementException
```

### 15.1. Đọc `length=4`

`Optional.ofNullable("  Java  ")` có giá trị, nên `map(String::strip)` tạo `"Java"`, `filter` giữ giá trị khác rỗng, và `map(String::length)` đổi sang `Optional<Integer>` có giá trị `4`.

### 15.2. Đọc `map-null-empty=true`

Khi mapper trong `map` trả null, Optional kết quả empty. Đây là hành vi có chủ đích của `map`, không phải một Optional giữ một giá trị null.

### 15.3. Đọc `nested=true`

`findUser(1).map(User::profile)` có kiểu `Optional<Optional<Profile>>` vì `profile()` đã trả Optional. `nested.isPresent()` true cho biết outer Optional có giá trị, **không chứng minh inner Optional luôn present**. Nếu muốn Profile trực tiếp, dùng `flatMap`.

### 15.4. Đọc `city` và `missing-city`

`cityFor(1)` dùng `flatMap` rồi `map`, trả `Hanoi`. `cityFor(9)` empty ngay từ phép tìm User, nên fallback `"?"` được sử dụng.

### 15.5. Đọc `transform`, `number`, `covariant`

`transform` chấp nhận `CharSequence::length` trên String vì mapper có input wildcard `? super T`. `toNumber` đổi kết quả `Optional<Integer>` sang `Optional<Number>` bằng `map`, không cần cast wrapper. `doubled(Optional<? extends Number>)` nhận Optional chứa Integer và trả `14.0`.

### 15.6. Đọc `stream` và `names`

`Optional.stream()` biến mỗi Optional thành stream 0 hoặc 1 phần tử. `flatMap(Optional::stream)` bỏ các empty entries, tạo `[2, 5]`. Pipeline `nonBlank` tương tự bỏ chuỗi rỗng, giữ `[a, bc]`.

### 15.7. Đọc `fallback` và `empty-lazy`

Với Optional có giá trị `"ready"`, đối số của `orElse` được thực thi eagerly, làm counter tăng 1 dù không dùng fallback. `orElseGet` trên Optional present không gọi Supplier. Trường hợp empty tiếp theo mới gọi Supplier, khiến counter tăng thành 2.

### 15.8. Đọc hai exception cuối

`flatMap` không chấp nhận mapper trả null, ném `NullPointerException`. `orElseThrow()` trên Optional empty ném `NoSuchElementException`. Hai lỗi có nguyên nhân khác nhau và không nên biến mọi exception thành “Optional sai”.

## 16. Các ví dụ cố ý không biên dịch: hiểu lỗi inference và quan hệ kiểu

Các đoạn sau là **các tệp riêng**, không chép chung vào file chương trình chính.

### 16.1. `BadInvariant.java`: biến đã có kiểu cố định

```java
import java.util.Optional;

class BadInvariant {
    static void check() {
        Optional<Integer> integers = Optional.of(7);
        Optional<Number> numbers = integers;
    }
}
```

Chạy:

```bash
javac --release 17 BadInvariant.java
```

Compiler báo:

```text
error: incompatible types:
Optional<Integer> cannot be converted to Optional<Number>
```

Đây là **generic invariance**. Dùng `Optional<? extends Number>` cho code chỉ đọc Number, hoặc dùng `map` nếu thực sự cần biến đổi kết quả sang Optional<Number>.

Nhớ phân biệt ví dụ này với `Optional<Number> numbers = Optional.of(7)`, vốn **có thể biên dịch** nhờ inference từ kiểu đích.

### 16.2. `BadMapNested.java`: dùng `map` khi mapper trả Optional

```java
import java.util.Optional;

class BadMapNested {
    static Optional<Integer> make() {
        return Optional.of("7")
                .map(s -> Optional.of(Integer.parseInt(s)));
    }
}
```

Biên dịch:

```bash
javac --release 17 BadMapNested.java
```

Compiler báo lỗi về **incompatible bounds** cho inference variable `U`. Mapper trả `Optional<Integer>`, vì vậy `.map(...)` tạo `Optional<Optional<Integer>>`, không phải `Optional<Integer>` mà return type yêu cầu.

Sửa thành:

```java
return Optional.of("7")
        .flatMap(s -> Optional.of(Integer.parseInt(s)));
```

Nếu mapper chỉ trả `Integer`, dùng `map(Integer::parseInt)` còn đơn giản hơn.

### 16.3. `BadFlatMap.java`: mapper không trả Optional

```java
import java.util.Optional;

class BadFlatMap {
    static Optional<Integer> make() {
        return Optional.of("7")
                .flatMap(Integer::parseInt);
    }
}
```

Biên dịch:

```bash
javac --release 17 BadFlatMap.java
```

Compiler từ chối vì method reference có kết quả `int`, **không thể chuyển thành** `Optional<? extends U>` mà `flatMap` yêu cầu.

Sửa bằng `map(Integer::parseInt)` vì mapper trả một giá trị thường.

### 16.4. `BadMapType.java`: kiểu kết quả không khớp

```java
import java.util.Optional;

class BadMapType {
    static Optional<Integer> make() {
        return Optional.of("java")
                .map(String::toUpperCase);
    }
}
```

Chạy:

```bash
javac --release 17 BadMapType.java
```

`String::toUpperCase` trả `String`; method lại khai báo `Optional<Integer>`. Compiler báo incompatible bounds của inference variable `U` với các ràng buộc `Integer` và `String`.

Cần thay mapper để thật sự tạo `Integer`, hoặc đổi return type thành `Optional<String>` theo mục tiêu thiết kế.

### 16.5. Các lỗi này khác exception runtime

Bốn tệp trên **không biên dịch**. Chúng là lỗi hệ thống kiểu/inference. Trái lại, một mapper hợp lệ về kiểu nhưng ném `NumberFormatException`, hoặc `flatMap` trả null, là lỗi khi **chạy**.

Vì vậy khi debug cần phân biệt “compiler không suy luận được một `U` thỏa constraints” với “mapper chạy và thất bại vì dữ liệu”.

## 17. Tính liên kết kiểu trong các pipeline dài

Một pipeline:

```java
Optional<String> city =
        findUser(id)
            .flatMap(User::profile)
            .map(Profile::city)
            .filter(s -> !s.isBlank());
```

có thể viết bảng kiểu sau mỗi bước:

| Bước | Kiểu tĩnh | Ý nghĩa |
| --- | --- | --- |
| `findUser(id)` | `Optional<User>` | User có thể không tồn tại |
| `.flatMap(User::profile)` | `Optional<Profile>` | User có thể không có Profile |
| `.map(Profile::city)` | `Optional<String>` | Có city string nếu các bước trước có giá trị |
| `.filter(s -> !s.isBlank())` | `Optional<String>` | Loại city chỉ gồm whitespace |
| `.orElse("Unknown")` | `String` | Biến Optional thành giá trị thường với fallback |

Viết kiểu tĩnh sau từng bước là cách chẩn đoán rất hiệu quả khi `javac` báo inference bounds không tương thích.

### 17.1. Refactor bằng local variables để đọc lỗi dễ hơn

Nếu chain dài:

```java
var result = a.flatMap(...).map(...).flatMap(...).filter(...);
```

gặp diagnostic khó hiểu, tách thành:

```java
Optional<User> user = findUser(id);
Optional<Profile> profile = user.flatMap(User::profile);
Optional<String> city = profile.map(Profile::city);
```

Compiler sẽ xác định lỗi gần bước tạo type mismatch hơn, đồng thời tăng tính dễ đọc và test.

### 17.2. Không ép mọi bước vào một Optional

Nếu một bước cần log, thu thập nhiều lỗi hoặc xử lý bất đồng bộ, một chain Optional thuần có thể không biểu diễn đủ ngữ nghĩa. Bạn có thể tách xử lý hoặc chuyển abstraction. Mục tiêu là quan hệ kiểu rõ, không phải có một dòng code duy nhất.

## 18. Generic methods dùng `Optional<? extends T>` ở API boundary

Giả sử một hàm chỉ muốn đọc một số:

```java
static double doubled(Optional<? extends Number> input) {
    return input.map(n -> n.doubleValue() * 2)
            .orElse(0.0);
}
```

Nó nhận `Optional<Integer>`, `Optional<Long>`, `Optional<Double>` nhưng không tự biến input thành `Optional<Number>` cho việc gán.

Một generic helper khác:

```java
static <T, U> Optional<U> transform(
        Optional<T> input,
        Function<? super T, ? extends U> mapper) {
    return input.map(mapper);
}
```

có thể dùng để giữ quan hệ typed giữa input và output. Tuy nhiên đôi khi chỉ viết `input.map(mapper)` trực tiếp còn dễ hiểu hơn; không tạo generic abstraction mới nếu nó không đem lại giá trị thiết kế.

### 18.1. PECS trong Optional

PECS giúp nhớ:

- `? extends Number` trong `Optional<? extends Number>`: producer của Number.
- `? super T` trong `Function<? super T,...>`: mapper có thể tiêu thụ `T`.
- `? extends U` trong `Function<...,? extends U>`: mapper sản xuất `U` hoặc subtype.
- `? extends Optional<? extends U>` trong `flatMap`: mapper sản xuất một Optional chứa kiểu tương thích với `U`.

PECS không cho phép bạn thêm/mutate một giá trị tùy ý vào Optional; `Optional<T>` không có `set(T)`. Lý do dùng wildcard ở đây là **khả năng chấp nhận kiểu và suy luận**, không phải sửa nội dung container.

## 19. Tránh lạm dụng `Optional<T>` trong dữ liệu và API

### 19.1. Optional thường phù hợp cho kết quả có thể vắng mặt

Một ví dụ API rõ ý nghĩa:

```java
Optional<User> findById(long id);
```

Caller được nhắc phải xử lý trường hợp không tìm thấy. Điều đó thường rõ hơn việc trả `User` và tài liệu hóa bằng câu mơ hồ “có thể null”.

### 19.2. Cân nhắc khi dùng Optional làm field hoặc parameter

Nhiều codebase ưu tiên dùng Optional chủ yếu làm **return type** và dùng kiểu domain phù hợp cho fields/parameters, đặc biệt khi có các framework serialization/ORM không hỗ trợ Optional theo mong muốn. Đây là lời khuyên thiết kế theo ngữ cảnh, không phải lệnh cấm tuyệt đối của Java.

Một constructor param `Optional<String>` có thể buộc caller luôn bọc giá trị, kể cả khi chính sách có thể được diễn đạt gọn hơn qua overload/config object. Với field persisted, kiểm tra hỗ trợ của framework trước khi dùng Optional.

### 19.3. Không truyền `null` thay Optional empty

Một method trả `Optional<T>` không nên trả `null`:

```java
// Không nên:
// return null;
```

Nếu không có giá trị, trả `Optional.empty()`. Trả null ở chính wrapper Optional làm caller không còn bảo đảm được API xử lý vắng mặt bằng `map`/`flatMap`.

### 19.4. Không so sánh Optional với `==`

Optional là value-based, dùng equals/kiểm tra trạng thái chứ không dựa trên identity. Cũng không đồng bộ hóa trên Optional object.

## 20. Debug các lỗi và hiện tượng phổ biến

| Hiện tượng | Nguyên nhân hay gặp | Hướng xử lý |
| --- | --- | --- |
| `Optional<Integer> cannot be converted to Optional<Number>` | Generic invariance với biến đã xác định type argument | Dùng `Optional<? extends Number>` khi chỉ đọc, hoặc `map` để tạo Optional<Number> |
| `inference variable U has incompatible bounds` sau `map` | Mapper return type không khớp output mong đợi, hoặc trả Optional nested | Ghi rõ type sau mỗi bước; chọn `flatMap` hoặc sửa mapper/return |
| `int cannot be converted to Optional<? extends U>` sau `flatMap` | Mapper trả giá trị thường thay vì Optional | Chuyển sang `map`, hoặc trả Optional thật |
| `NoSuchElementException` | Gọi `get()`/`orElseThrow()` trên empty | Chọn fallback đúng hợp đồng hoặc xử lý empty trước |
| `NullPointerException` tại `Optional.of(null)` | `of` cấm null | Dùng `ofNullable` nếu null biểu thị vắng mặt |
| `NullPointerException` tại `flatMap` | Mapper/null argument hoặc mapper trả null | Không trả null; trả `Optional.empty()` |
| `map` trả empty dù đầu vào present | Mapper trả null | Xem logic mapper; `map` wrap bằng ofNullable |
| Fallback có side effect dù Optional present | Dùng `orElse(expensiveCall())` | Dùng `orElseGet(() -> expensiveCall())` |
| `Optional<Optional<T>>` ngoài mong muốn | Dùng `map` với mapper trả Optional | Dùng `flatMap` |
| `List<Optional<T>>` xử lý khó | Mỗi phần tử có trạng thái vắng mặt | Dùng `Optional.stream()` để lọc present nếu có thể bỏ vị trí |
| Chain che lý do không có dữ liệu | Optional chỉ giữ present/empty | Dùng domain Result/error type nếu cần nhiều trạng thái lỗi |

### 20.1. Dùng compiler để tìm sai quan hệ kiểu

Một quy trình thực tế:

1. Xác định `T` của Optional trước biến đổi.
2. Xác định return type **chính xác** của mapper.
3. Nếu mapper trả `U`, dùng `map`; nếu trả `Optional<U>`, dùng `flatMap`.
4. Viết type sau biến đổi: `Optional<U>` hay `Optional<Optional<U>>`?
5. So sánh với method return type hoặc assignment target.
6. Nếu dùng wildcard, phân tích nó là input consumer hay output producer.
7. Tách pipeline dài thành variables có kiểu tường minh.
8. Biên dịch bằng `javac --release 17 -Xlint:all` và test cả present, empty, null input, mapper sai và exception.

## 21. Bài tập có đáp án

### Bài 1. `map` đổi kiểu ra sao?

```java
Optional<String> name = Optional.of("Java");
var result = name.map(String::length);
```

**Hỏi:** kiểu tĩnh của `result` là gì?

<details>
<summary>Đáp án</summary>

`Optional<Integer>`. Input là String, mapper trả int (boxing thành Integer), nên generic method `<U> map(...)` suy luận `U = Integer`.

</details>

### Bài 2. Hai dạng assignment nào hợp lệ?

```java
Optional<Number> a = Optional.of(7);

Optional<Integer> ints = Optional.of(7);
// Optional<Number> b = ints;
```

<details>
<summary>Đáp án</summary>

Dòng đầu hợp lệ nhờ type inference có target type `Optional<Number>`. Dòng gán `ints` sang `b` không hợp lệ vì Java Generics invariant: `Optional<Integer>` không phải subtype của `Optional<Number>`.

</details>

### Bài 3. Phép biến đổi nào tránh Optional lồng nhau?

```java
Optional<User> user = findUser(1);
```

Nếu `User.profile()` trả `Optional<Profile>`, dùng method nào?

<details>
<summary>Đáp án</summary>

Dùng `user.flatMap(User::profile)` để nhận `Optional<Profile>`. Dùng `map` sẽ tạo `Optional<Optional<Profile>>`.

</details>

### Bài 4. Tại sao `flatMap(Integer::parseInt)` không hợp lệ?

<details>
<summary>Đáp án</summary>

`parseInt` trả `int`, trong khi `flatMap` yêu cầu mapper trả `Optional<? extends U>`. Dùng `map(Integer::parseInt)` nếu muốn `Optional<Integer>`.

</details>

### Bài 5. `map` và `flatMap` xử lý mapper trả null có giống nhau?

<details>
<summary>Đáp án</summary>

Không. Nếu mapper của `map` trả null trên Optional present, kết quả thành empty. `flatMap` yêu cầu mapper trả một Optional object khác null; nếu trả null, `NullPointerException`.

</details>

### Bài 6. Khi Optional đã có giá trị, fallback nào vẫn được đánh giá?

```java
present.orElse(costly());
present.orElseGet(() -> costly());
```

<details>
<summary>Đáp án</summary>

`costly()` trong `orElse(costly())` được đánh giá trước lời gọi dù Optional present. Supplier ở `orElseGet` chỉ được gọi nếu Optional empty.

</details>

### Bài 7. `List<Optional<T>>` và `Optional<List<T>>` khác nhau ở đâu?

<details>
<summary>Đáp án</summary>

`List<Optional<T>>` là nhiều vị trí, mỗi vị trí có thể thiếu. `Optional<List<T>>` là toàn bộ danh sách có thể thiếu; khi present, danh sách có thể rỗng. Hai mô hình dữ liệu không tương đương.

</details>

### Bài 8. Vì sao `Optional<? extends Number>` giúp nhận nhiều kiểu Optional khác nhau?

<details>
<summary>Đáp án</summary>

Wildcard `? extends Number` cho phép một Optional có type argument là subtype của Number như Integer/Double; code có thể đọc giá trị như Number. Không có nghĩa có thể gán một biến `Optional<Integer>` trực tiếp sang `Optional<Number>`.

</details>

### Bài 9. `Optional.stream()` làm gì với empty?

<details>
<summary>Đáp án</summary>

Nó trả một stream không có phần tử; Optional present tạo stream đúng một phần tử. Vì vậy `streamOfOptionals.flatMap(Optional::stream)` bỏ các empty values.

</details>

### Bài 10. Optional có tự bắt lỗi parse không?

<details>
<summary>Đáp án</summary>

Không. `Optional.of("bad").map(Integer::parseInt)` vẫn ném `NumberFormatException`. Nếu lỗi parse cần biểu diễn thành empty hoặc kết quả có lỗi rõ ràng, viết logic xử lý ngoại lệ riêng.

</details>

## 22. Kết luận

`Optional<T>` không chỉ là cách tránh `null`; khi kết hợp Generic, nó tạo một hợp đồng **có hoặc không có giá trị thuộc kiểu T**, cùng những phép biến đổi được compiler kiểm tra:

- `map(Function<? super T, ? extends U>)` đổi `Optional<T>` thành `Optional<U>`.
- `flatMap(Function<? super T, ? extends Optional<? extends U>>)` dùng khi mapper **đã trả Optional**, tránh Optional lồng nhau.
- `filter(Predicate<? super T>)` kiểm tra điều kiện nhưng giữ kiểu `Optional<T>`.
- `orElse` và `orElseGet` trả `T` với cách thực thi fallback khác nhau; `or` trả lại Optional.
- `Optional.stream()` kết hợp với Stream API để lấy các present values.
- `Optional<Integer>` không subtype của `Optional<Number>`; wildcard và inference ở factory methods giải quyết những nhu cầu khác nhau.

Hãy xác định **kiểu của dữ liệu trước bước biến đổi, kiểu kết quả mapper, kiểu Optional sau bước biến đổi**. Với pipeline dài, tách thành variables có kiểu tường minh để compiler báo lỗi đúng vị trí. Tránh lạm dụng `get()`, cast unchecked và `orElse(null)`; mục tiêu của Optional là để trạng thái vắng mặt và quan hệ kiểu được biểu đạt rõ ngay trong API.