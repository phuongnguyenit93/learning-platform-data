# Ánh xạ và kiểm tra kết quả bằng map, flatMap và filter

> **Chương:** Optional trong kết quả Stream  
> **Module:** JAVA_STREAM_API  
> **Mục tiêu:** Biết xử lý kết quả có thể vắng mặt từ các phép toán Stream bằng `Optional.map`, `Optional.flatMap` và `Optional.filter`; xây dựng chuỗi xử lý an toàn, phân biệt Optional với Stream, kiểm soát `null`, lỗi và giá trị mặc định.

Java Stream API hỗ trợ xử lý dữ liệu khai báo qua các pipeline lazy với `filter`, `map`, `reduce`, `collect` và nhiều phép toán khác. Một số phép kết thúc, chẳng hạn `findFirst()`, `findAny()`, `min()`, `max()` và `reduce(BinaryOperator)`, không bảo đảm có một giá trị trả về: Stream có thể rỗng hoặc không có phần tử thỏa điều kiện. Java dùng **`Optional<T>`** để mô tả kết quả có thể có hoặc không có giá trị mà không phải lấy `null` làm tín hiệu chính.

Sau khi có một `Optional<T>`, ta có thể **ánh xạ giá trị bên trong** bằng `map`, **nối thêm một phép tra cứu có thể vắng mặt** bằng `flatMap` và **chỉ giữ kết quả thỏa điều kiện** bằng `filter`. Đây là ba phép toán chủ đạo của bài này.

Kiến thức này còn giúp sử dụng đúng `Optional` trong các bài toán grouping, collector tùy chỉnh và xử lý song song của module **JAVA_STREAM_API**. Khi nguồn được cấp bởi `Spliterator` hoặc bởi các phép biến đổi Stream nâng cao như Stream Gatherers, kết quả cuối vẫn có thể là một giá trị tùy chọn; cách xử lý trạng thái rỗng và tài nguyên không thay đổi.

## 1. Optional xuất hiện ở đâu trong một pipeline Stream?

Ví dụ tìm đơn hàng đầu tiên có số tiền tối thiểu 100.000:

```java
import java.util.List;
import java.util.Optional;

record Order(String id, long amount) {}

List<Order> orders = List.of(
    new Order("O-01", 50_000),
    new Order("O-02", 180_000),
    new Order("O-03", 90_000)
);

Optional<Order> found = orders.stream()
    .filter(order -> order.amount() >= 100_000)
    .findFirst();

// found chứa Order("O-02", 180000).
```

Pipeline đầu tiên gồm nguồn `orders.stream()`, một phép trung gian `Stream.filter(...)` và phép kết thúc `Stream.findFirst()`. **`findFirst()` kết thúc Stream và trả `Optional<Order>`**, không phải `Stream<Order>`.

Sau đó ta tiếp tục xử lý kết quả:

```java
Optional<String> orderId = found
    .map(Order::id)
    .filter(id -> id.startsWith("O-"));

System.out.println(orderId.orElse("Không tìm thấy")); // O-02
```

Đoạn này gọi **`Optional.map` và `Optional.filter`** trên kết quả đã nhận, không quay lại tiêu thụ Stream cũ.

```text
orders.stream()
      │
      ▼
Stream<Order> ── filter(...) ── findFirst() ──► Optional<Order>
                                                  │
                                                  ▼
                                              map(Order::id)
                                                  │
                                                  ▼
                                             Optional<String>
                                                  │
                                                  ▼
                                            filter(predicate)
                                                  │
                                     ┌────────────┴────────────┐
                                     ▼                         ▼
                             Optional<String>           Optional.empty()
                               có giá trị
```

Nếu không có đơn hợp lệ, `found` là `Optional.empty()` và các hàm ánh xạ, kiểm tra phía sau không được gọi.

## 2. Optional là gì và khác Stream như thế nào?

`Optional<T>` là một đối tượng chứa **tối đa một giá trị khác `null`**. Nó có hai trạng thái:

- **Có giá trị (present):** `Optional.of(value)` với `value != null`.
- **Không có giá trị (empty):** `Optional.empty()`.

Không giống `Stream<T>`, `Optional<T>` không biểu diễn một nguồn nhiều phần tử và **không phải pipeline duyệt một lần**. Các phép `map`, `flatMap`, `filter` của Optional trả về Optional mới và chỉ làm việc trên tối đa một giá trị.

| Tiêu chí | `Stream<T>` | `Optional<T>` |
| --- | --- | --- |
| Số phần tử có thể biểu diễn | 0, 1 hoặc nhiều | 0 hoặc 1 |
| Mục đích chính | Xử lý một dãy phần tử | Biểu diễn một kết quả có thể vắng mặt |
| `map` | Ánh xạ từng phần tử của Stream | Ánh xạ một giá trị nếu hiện diện |
| `flatMap` | Ánh xạ phần tử thành Stream và làm phẳng | Ánh xạ giá trị thành Optional và tránh Optional lồng nhau |
| `filter` | Loại các phần tử không thỏa điều kiện | Giữ Optional đang có giá trị hoặc trả Optional rỗng |
| Tính lazy | Phép trung gian thường lazy, cần terminal | Lambda của `map`/`flatMap`/`filter` trên Optional có giá trị được thực thi khi gọi các phương thức đó |
| Tiêu thụ một lần | Có, một đối tượng Stream chỉ tiêu thụ một lần | Không, có thể gọi các phương thức của một Optional nhiều lần |

Ví dụ:

```java
Optional<String> name = Optional.of("An");

Optional<String> upper = name.map(String::toUpperCase);
Optional<Integer> length = name.map(String::length);

// upper = Optional[AN]
// length = Optional[2]
// name vẫn chứa "An".
```

Dù `name` có thể được dùng nhiều lần, nếu giá trị bên trong là một đối tượng mutable thì Optional **không tự biến đối tượng đó thành bất biến**. Cũng không nên dùng việc có thể tái sử dụng Optional để suy luận rằng Stream tạo ra nó có thể được tái sử dụng.

### 2.1. Những phép kết thúc Stream thường trả Optional

| Phép kết thúc | Kiểu kết quả | Vì sao có thể rỗng? |
| --- | --- | --- |
| `findFirst()` | `Optional<T>` | Nguồn không có phần tử hoặc đã lọc hết |
| `findAny()` | `Optional<T>` | Không có phần tử nào để chọn |
| `min(comparator)` | `Optional<T>` | Không có phần tử nào để so sánh |
| `max(comparator)` | `Optional<T>` | Không có phần tử nào để so sánh |
| `reduce(BinaryOperator<T>)` | `Optional<T>` | Không có phần tử và không cung cấp giá trị đồng nhất |
| `IntStream.min()/max()/findFirst()` | `OptionalInt` | Không có giá trị `int` |
| `LongStream.min()/max()/findFirst()` | `OptionalLong` | Không có giá trị `long` |
| `DoubleStream.average()` | `OptionalDouble` | Không thể tính trung bình từ nguồn rỗng |

Ngược lại, `count()` trả `long` (có thể bằng 0), `IntStream.sum()` trả `int` và `collect(...)` trả kết quả theo hợp đồng collector. Các phép này không tự động trả `Optional<T>` chỉ vì Stream đầu vào rỗng.

## 3. Optional.map: biến đổi giá trị nếu hiện diện

Chữ ký rút gọn của `Optional.map`:

```java
<U> Optional<U> map(Function<? super T, ? extends U> mapper);
```

Ý nghĩa:

1. Nếu Optional đang **có giá trị**, áp dụng `mapper` lên giá trị đó.
2. Nếu `mapper` trả về giá trị khác `null`, kết quả là `Optional<U>` chứa giá trị mới.
3. Nếu `mapper` trả về `null`, kết quả là `Optional.empty()`.
4. Nếu Optional ban đầu rỗng, không gọi `mapper` và trả kết quả rỗng.

### 3.1. Ánh xạ từ một kiểu sang kiểu khác

```java
Optional<Order> first = orders.stream()
    .filter(order -> order.amount() > 100_000)
    .findFirst();

Optional<Long> amount = first.map(Order::amount);
Optional<String> label = first.map(order ->
    order.id() + " - " + order.amount()
);

// amount = Optional[180000]
// label = Optional[O-02 - 180000]
```

Ở đây `Order::amount` là method reference tương đương `order -> order.amount()`. Java dùng kiểu `Function<Order, Long>` làm kiểu đích cho `Optional.map`; giá trị `long` từ record được boxing thành `Long`.

Có thể ghép nhiều bước:

```java
Optional<String> normalizedId = first
    .map(Order::id)
    .map(String::trim)
    .map(String::toUpperCase);

// Optional[O-02]
```

Mỗi bước xử lý giá trị của Optional trước đó. Nếu bất kỳ bước nào tạo Optional rỗng, các bước sau sẽ bỏ qua mapper của mình.

### 3.2. Optional rỗng giúp tránh điều kiện kiểm tra lặp lại

```java
Optional<String> missing = Optional.<Order>empty()
    .map(Order::id)
    .map(String::trim);

System.out.println(missing.isEmpty()); // true
```

Không xảy ra `NullPointerException` do cố gọi `id()` trên đơn hàng không tồn tại. Nhưng điều này **không có nghĩa mọi ngoại lệ đều được Optional hấp thụ**: nếu mapper ném ngoại lệ, ngoại lệ vẫn lan truyền.

### 3.3. Mapper trả null thì sao?

`Optional.map` sử dụng ngữ nghĩa tương đương bọc kết quả mapper qua `Optional.ofNullable`:

```java
Optional<String> source = Optional.of("An");

Optional<Integer> result = source.map(name -> null);

System.out.println(result.isEmpty()); // true
```

Điều này hữu ích khi tích hợp API cũ có thể trả `null`. Tuy nhiên, tốt hơn nên xác định rõ tại ranh giới dữ liệu rằng `null` mang ý nghĩa “không có kết quả”. Nếu một phương thức phải luôn trả giá trị mà lại trả `null` do lỗi lập trình, ánh xạ thành Optional rỗng có thể che lấp nguyên nhân thực sự.

### 3.4. Lazy của Stream và việc gọi mapper của Optional

So sánh:

```java
Stream<String> stream = Stream.of("an")
    .map(value -> {
        System.out.println("Stream map: " + value);
        return value.toUpperCase();
    });

System.out.println("Đã tạo Stream");
// Lambda Stream.map chưa nhất thiết chạy.

Optional<String> optional = Optional.of("an")
    .map(value -> {
        System.out.println("Optional map: " + value);
        return value.toUpperCase();
    });
// Lambda Optional.map đã chạy trong lời gọi map vì Optional có giá trị.

List<String> values = stream.toList();
// Lúc này Stream được tiêu thụ, mapper được đánh giá khi cần.
```

Phân biệt thời điểm thực thi để không nhầm hai API cùng tên.

## 4. Optional.flatMap: nối thao tác cũng trả Optional

Chữ ký rút gọn:

```java
<U> Optional<U> flatMap(
    Function<? super T, ? extends Optional<? extends U>> mapper
);
```

`Optional.flatMap` dùng khi **hàm nhận giá trị bên trong rồi trả về một Optional khác**. Kết quả được trải phẳng thành một lớp Optional duy nhất.

### 4.1. Vấn đề Optional lồng nhau

Giả sử đối tượng khách hàng có phương thức trả email tùy chọn:

```java
record Customer(String id, Optional<String> email) {}

Customer customer = new Customer(
    "C-01",
    Optional.of("an@example.com")
);
```

Nếu dùng `map`:

```java
Optional<Customer> found = Optional.of(customer);

Optional<Optional<String>> nested =
    found.map(Customer::email);
```

`Customer::email` đã trả về `Optional<String>`. Khi `map` bọc nó, kiểu trở thành `Optional<Optional<String>>`. Mỗi lần lấy dữ liệu lại phải xử lý hai lớp có/không có, thường không cần thiết.

Dùng `flatMap`:

```java
Optional<String> flat =
    found.flatMap(Customer::email);

// flat = Optional[an@example.com]
```

Có thể đọc trực tiếp: “Nếu tìm thấy khách hàng, tiếp tục lấy email nếu có”.

### 4.2. Ví dụ tra cứu phụ thuộc hai bước

Giả sử một phương thức tìm khách hàng:

```java
static Optional<Customer> findCustomer(
        List<Customer> customers,
        String id
) {
    return customers.stream()
        .filter(customer -> customer.id().equals(id))
        .findFirst();
}
```

Từ đơn hàng có `customerId`:

```java
record Order(String id, String customerId, long amount) {}

Optional<String> email = orders.stream()
    .filter(order -> order.id().equals("O-01"))
    .findFirst()
    .flatMap(order -> findCustomer(customers, order.customerId()))
    .flatMap(Customer::email);
```

Các biến `orders` và `customers` ở ví dụ này là các danh sách nghiệp vụ tương ứng, sẽ được khai báo đầy đủ trong ví dụ tổng hợp ở mục 10. Chuỗi có thể rỗng ở từng bước: không tìm thấy đơn hàng, không tìm thấy khách hàng hoặc khách hàng chưa có email.

### 4.3. Không dùng flatMap cho hàm trả giá trị thường

Nếu muốn lấy tên khách hàng:

```java
record Customer(String id, String name, Optional<String> email) {}

Optional<Customer> found = Optional.of(
    new Customer("C-01", "An", Optional.of("an@example.com"))
);

Optional<String> name = found.map(Customer::name);
Optional<String> email = found.flatMap(Customer::email);
```

- `Customer::name` trả `String` → dùng `map`.
- `Customer::email` trả `Optional<String>` → dùng `flatMap`.

**Quy tắc lựa chọn theo chữ ký:**

| Hàm cần gọi | Chọn | Kiểu kết quả |
| --- | --- | --- |
| `T -> U` | `optional.map(...)` | `Optional<U>` |
| `T -> Optional<U>` | `optional.flatMap(...)` | `Optional<U>` |
| `T -> boolean` | `optional.filter(...)` | `Optional<T>` |

### 4.4. flatMap không chấp nhận null từ mapper

Khác với `map`, `flatMap` **yêu cầu mapper trả về một đối tượng Optional khác null**. Nếu mapper trả `null`, Java ném `NullPointerException`:

```java
Optional<String> value = Optional.of("x");

// Ném NullPointerException:
// Optional<String> result = value.flatMap(x -> null);
```

Nếu một API cũ trả `String` hoặc `null`, hãy bọc bằng `Optional.ofNullable`:

```java
static String legacyLookup(String key) {
    return key.equals("ok") ? "Đã tìm thấy" : null;
}

Optional<String> found = Optional.of("missing")
    .flatMap(key -> Optional.ofNullable(legacyLookup(key)));

System.out.println(found.isEmpty()); // true
```

Phương thức `legacyLookup` ở ví dụ là phương thức độc lập có thể đặt trong một lớp Java. Không sử dụng `Optional.of(legacyLookup(...))` nếu kết quả có thể `null`, vì `Optional.of(null)` ném `NullPointerException`.

### 4.5. Hành vi khi Optional nguồn rỗng

```java
Optional<String> absent = Optional.<Customer>empty()
    .flatMap(Customer::email);

System.out.println(absent); // Optional.empty
```

Lời gọi `Customer::email` không diễn ra. Vì thế chuỗi xử lý phụ thuộc nhiều phép tra cứu có thể diễn đạt mà không cần mỗi bước kiểm tra `isPresent()` thủ công.

## 5. Optional.filter: chỉ giữ kết quả thỏa điều kiện

Chữ ký:

```java
Optional<T> filter(Predicate<? super T> predicate);
```

`Optional.filter` không thay đổi kiểu dữ liệu:

- Nếu Optional rỗng, trả Optional rỗng và **không gọi predicate**.
- Nếu có giá trị và predicate trả `true`, giữ nguyên giá trị.
- Nếu có giá trị và predicate trả `false`, trả Optional rỗng.
- Nếu predicate ném ngoại lệ, ngoại lệ được truyền ra ngoài.

### 5.1. Kiểm tra kết quả tìm kiếm

```java
Optional<Order> candidate = orders.stream()
    .filter(order -> order.id().equals("O-02"))
    .findFirst();

Optional<Order> approved = candidate
    .filter(order -> order.amount() >= 100_000);
```

Có ba khả năng: không có đơn phù hợp mã; có đơn nhưng số tiền chưa đạt; hoặc có đơn đạt điều kiện. Hai trường hợp đầu đều tạo `Optional.empty()`. Nếu nghiệp vụ cần **phân biệt “không tồn tại” với “tồn tại nhưng không đủ điều kiện”**, không nên dùng Optional rỗng làm trạng thái duy nhất; cần một kiểu kết quả mô tả lý do, ví dụ enum hoặc sealed result.

### 5.2. Lọc sau map hay trước map?

Giả sử cần tìm khách hàng có email không rỗng:

```java
Optional<String> email = foundCustomer
    .flatMap(Customer::email)
    .map(String::trim)
    .filter(text -> !text.isEmpty());
```

Ở đây `filter` nhận `String` vì `flatMap` và `map` đã tạo `Optional<String>`. Nếu kiểm tra cả đối tượng khách hàng trước:

```java
Optional<String> email = foundCustomer
    .filter(customer -> customer.active())
    .flatMap(Customer::email);
```

Thì `filter` nhận `Customer`. Đoạn ví dụ giả định kiểu `Customer` có phương thức `active()`; xem phần minh họa đầy đủ ở mục 10.

**Thứ tự thao tác thể hiện quy tắc nghiệp vụ.** Việc lọc theo trạng thái khách hàng trước khi lấy email khác với việc chỉ kiểm tra nội dung email.

### 5.3. Không biến filter thành xử lý ngoại lệ

`filter` chỉ nên kiểm tra một điều kiện. Ví dụ:

```java
Optional<String> valid = Optional.of("42")
    .filter(text -> text.chars().allMatch(Character::isDigit));
```

Nếu cần chuyển chuỗi thành số, `map(Integer::parseInt)` có thể ném `NumberFormatException` khi dữ liệu không hợp lệ. Optional không tự chuyển ngoại lệ ấy thành empty; phải xác định chiến lược kiểm tra đầu vào hoặc xử lý lỗi riêng.

### 5.4. So sánh Stream.filter và Optional.filter

```java
List<Integer> results = Stream.of(1, 2, 3, 4)
    .filter(n -> n % 2 == 0)
    .toList(); // [2, 4]

Optional<Integer> result = Optional.of(3)
    .filter(n -> n % 2 == 0); // Optional.empty
```

`Stream.filter` có thể giữ nhiều phần tử; `Optional.filter` chỉ giữ hoặc loại một giá trị đã có. Hai phương thức có cùng dạng điều kiện `Predicate<T>`, nhưng khác số lượng phần tử và vòng đời thực thi.

## 6. Kết hợp map, flatMap và filter trong một chuỗi

Giả sử nhận mã đơn hàng, cần tên miền email của khách hàng đang hoạt động có email hợp lệ tối thiểu:

```java
Optional<String> domain = findOrder(orderId)
    .filter(Order::paid)
    .flatMap(order -> findCustomer(order.customerId()))
    .filter(Customer::active)
    .flatMap(Customer::email)
    .map(String::trim)
    .filter(text -> text.contains("@"))
    .map(text -> text.substring(text.indexOf('@') + 1))
    .filter(text -> !text.isBlank());
```

Ở đây `findOrder` và `findCustomer` là các phương thức nghiệp vụ có kết quả `Optional`; `Order` có `paid()`, `Customer` có `active()` và `email()` trả `Optional<String>`. Đoạn mã minh họa hình dạng pipeline; cách định nghĩa đầy đủ các kiểu được trình bày ở mục 10.

Luồng dữ liệu về mặt kiểu:

```text
Optional<Order>
   │ filter(Order::paid)
   ▼
Optional<Order>
   │ flatMap(order -> findCustomer(...))
   ▼
Optional<Customer>
   │ filter(Customer::active)
   ▼
Optional<Customer>
   │ flatMap(Customer::email)
   ▼
Optional<String>
   │ map(String::trim)
   ▼
Optional<String>
   │ filter(text -> text.contains("@"))
   ▼
Optional<String>
   │ map(extractDomain)
   ▼
Optional<String>
   │ filter(text -> !text.isBlank())
   ▼
Optional<String>
```

Không bước nào gọi `get()`. Khi thiếu một mắt xích, các bước sau tự bỏ qua xử lý giá trị.

**Chú ý:** kiểm tra `contains("@")` chỉ là minh họa đơn giản, **không phải bộ xác thực địa chỉ email hoàn chỉnh**. Với nghiệp vụ thực tế, chính sách kiểm tra và chuẩn hóa phải phù hợp yêu cầu hệ thống.

## 7. Cách xử lý kết quả cuối của Optional

Ba phép `map`, `flatMap`, `filter` vẫn trả Optional. Khi cần trả dữ liệu cho người gọi hoặc hiển thị kết quả, hãy chọn chính sách cho trạng thái rỗng.

### 7.1. orElse: giá trị thay thế được đánh giá trước

```java
String label = Optional.of("An")
    .map(String::toUpperCase)
    .orElse("Không có tên"); // AN
```

`orElse(other)` luôn nhận **một giá trị đã được tính**. Nếu biểu thức tạo giá trị mặc định tốn kém, nó vẫn được đánh giá trước khi phương thức `orElse` được gọi:

```java
static String expensiveFallback() {
    System.out.println("Tạo fallback");
    return "Mặc định";
}

String name = Optional.of("An")
    .orElse(expensiveFallback());

// In "Tạo fallback" dù Optional đã có "An".
```

### 7.2. orElseGet: chỉ gọi supplier khi rỗng

```java
String name = Optional.of("An")
    .orElseGet(() -> expensiveFallback());

// Không gọi expensiveFallback() vì Optional có giá trị.
```

Cùng giá trị kết quả, nhưng `orElseGet` phù hợp khi tạo giá trị thay thế tốn chi phí hoặc có tác động phụ. Khi giá trị mặc định chỉ là hằng số như `"N/A"`, `orElse` thường đơn giản hơn.

### 7.3. orElseThrow: trạng thái rỗng là lỗi

```java
Order required = orders.stream()
    .filter(order -> order.id().equals("O-02"))
    .findFirst()
    .orElseThrow(() ->
        new IllegalArgumentException("Không tìm thấy đơn hàng")
    );
```

Dùng `orElseThrow` khi **hợp đồng nghiệp vụ thực sự yêu cầu phải có dữ liệu**. Không nên tùy tiện biến kết quả không tồn tại hợp lệ thành lỗi.

### 7.4. ifPresent và ifPresentOrElse: hành động ở rìa hệ thống

```java
Optional<String> name = Optional.of("An");

name.ifPresent(System.out::println);

name.ifPresentOrElse(
    System.out::println,
    () -> System.out.println("Không có tên")
); // Java 9+
```

`ifPresent` và `ifPresentOrElse` trả `void`. Chúng phù hợp cho hành động cuối cùng như hiển thị hoặc cập nhật một thành phần bên ngoài khi yêu cầu có tác động. Nếu cần tiếp tục **biến đổi và truyền kết quả**, giữ Optional qua `map`, `flatMap`, `filter` sẽ rõ ràng hơn.

### 7.5. Vì sao không lạm dụng get?

`Optional.get()` ném `NoSuchElementException` nếu rỗng. Mẫu này dễ tạo mã dài và bỏ sót xử lý:

```java
// Dài và dễ bị thay đổi sai trong quá trình bảo trì:
if (maybeName.isPresent()) {
    String upper = maybeName.get().toUpperCase();
}
```

Khi mục tiêu là biến đổi giá trị, dùng:

```java
Optional<String> upper = maybeName.map(String::toUpperCase);
```

Nếu kết quả phải có, dùng `orElseThrow` với thông báo và loại ngoại lệ phù hợp. Mục tiêu của Optional là buộc người viết mã suy nghĩ về trường hợp vắng mặt, thay vì chỉ dời nguy cơ lỗi sang một lời gọi `get()` khác.

## 8. Optional.stream: đưa kết quả có/không có trở lại pipeline Stream

Từ Java 9, `Optional<T>` có phương thức:

```java
Stream<T> stream();
```

Phương thức này trả:

- Stream **một phần tử** nếu Optional có giá trị.
- Stream **rỗng** nếu Optional không có giá trị.

Ví dụ:

```java
List<String> present = Optional.of("Java")
    .stream()
    .toList(); // [Java]

List<String> missing = Optional.<String>empty()
    .stream()
    .toList(); // []
```

### 8.1. Biến một Stream<Optional<T>> thành Stream<T>

Một bài toán thực tế là nhiều phép tra cứu độc lập, mỗi phép trả Optional:

```java
List<Optional<String>> emailLookups = List.of(
    Optional.of("an@example.com"),
    Optional.empty(),
    Optional.of("chi@example.com")
);

List<String> emails = emailLookups.stream()
    .flatMap(Optional::stream)
    .toList();

// [an@example.com, chi@example.com]
```

Nếu chỉ dùng `map(optional -> optional.orElse(null))`, danh sách có thể chứa `null`, khiến các bước sau dễ phát sinh lỗi và mất ý nghĩa có/không có. `flatMap(Optional::stream)` giữ đúng các giá trị hiện diện.

### 8.2. Kết hợp một danh sách đầu vào với hàm trả Optional

```java
static Optional<Integer> parsePositiveInt(String raw) {
    try {
        int value = Integer.parseInt(raw);
        return value > 0 ? Optional.of(value) : Optional.empty();
    } catch (NumberFormatException e) {
        return Optional.empty();
    }
}

List<Integer> values = Stream.of("12", "x", "-3", "7")
    .map(OptionalLesson::parsePositiveInt)
    .flatMap(Optional::stream)
    .toList();

// [12, 7]
```

`OptionalLesson` là tên lớp minh họa chứa phương thức `parsePositiveInt`. Ví dụ này cố ý chọn chính sách “chuỗi không hợp lệ thì bỏ qua”; nếu ứng dụng cần thông báo chính xác dòng lỗi, nên dùng kiểu kết quả riêng chứa thông tin thành công/thất bại thay vì chuyển mọi lỗi thành Optional rỗng.

Có thể viết gọn:

```java
List<Integer> values = Stream.of("12", "x", "-3", "7")
    .flatMap(text -> parsePositiveInt(text).stream())
    .toList();
```

Lưu ý **`Stream.flatMap` nhận một hàm trả Stream**, còn **`Optional.flatMap` nhận một hàm trả Optional**. `Optional.stream()` chính là cầu nối để hai hệ thống phối hợp.

### 8.3. Đưa nhiều kết quả tìm kiếm độc lập vào xử lý tiếp

```java
Stream<Optional<Order>> searchResults = Stream.of(
    orders.stream().filter(order -> order.id().equals("O-01")).findFirst(),
    orders.stream().filter(order -> order.id().equals("O-99")).findFirst()
);

long foundCount = searchResults
    .flatMap(Optional::stream)
    .count(); // 1, nếu chỉ có O-01.
```

Mỗi `findFirst()` ở đây tiêu thụ **một Stream riêng** được tạo từ `orders`. `Optional` đã có kết quả, còn `searchResults` là Stream đang chứa hai Optional đó.

## 9. Optional<T> và các Optional cho số nguyên thủy

Các phép kết thúc của primitive stream có thể trả:

- `OptionalInt` cho `IntStream.findFirst()`, `min()`, `max()` hoặc `reduce(...)` không identity.
- `OptionalLong` cho các phép tương ứng của `LongStream`.
- `OptionalDouble` cho các phép tương ứng của `DoubleStream`, cũng như `average()` của cả ba primitive stream.

`OptionalInt`, `OptionalLong` và `OptionalDouble` **không cung cấp cùng đầy đủ `map`, `flatMap`, `filter` như `Optional<T>`**. Vì vậy mã sau không hợp lệ:

```java
OptionalInt score = IntStream.of(7, 9).max();

// Không có API OptionalInt.map(...) như Optional<T>:
// score.map(n -> n * 2);
```

### 9.1. Xử lý trực tiếp kết quả số nếu chỉ cần giá trị

```java
OptionalInt max = IntStream.of(7, 9, 6).max();

int value = max.orElse(0); // 9
System.out.println(value);
```

Nếu không có dữ liệu, `orElse(0)` dùng chính sách mặc định 0 do ứng dụng chọn. Không nên đồng nhất “không có điểm” với “điểm bằng 0” nếu hệ thống cần phân biệt hai trường hợp.

### 9.2. Chuyển sang object stream khi cần map rồi trả Optional<T>

Các Optional nguyên thủy có `stream()` từ Java 9. Có thể chuyển kết quả sang object stream và `findFirst()`:

```java
Optional<String> label = IntStream.of(7, 9, 6)
    .max()               // OptionalInt
    .stream()            // IntStream có 0 hoặc 1 giá trị
    .mapToObj(n -> "Điểm cao nhất: " + n)
    .findFirst();        // Optional<String>

// Optional[Điểm cao nhất: 9]
```

`mapToObj` ở đây chạy trên `IntStream` được tạo từ `OptionalInt.stream()`, không phải là phương thức của `OptionalInt`. Đây là một đường chuyển đổi có chủ đích khi cần kết quả là `Optional<String>`.

### 9.3. Kiểu dữ liệu số không tự có quy tắc null

Với `IntStream`, phần tử là `int` và không thể `null`. Khi kết quả bị thiếu, trạng thái đó nằm ở `OptionalInt.empty()`. Nếu cần giao diện giao tiếp chung có `Optional<Integer>`, có thể chuyển có kiểm soát:

```java
OptionalInt primitive = IntStream.of(4, 8).max();

Optional<Integer> boxed = primitive.isPresent()
    ? Optional.of(primitive.getAsInt())
    : Optional.empty();

// boxed = Optional[8]
```

Đây là trường hợp có thể chấp nhận `getAsInt()` vì đã kiểm tra `isPresent()` ngay trong cùng biểu thức. Khi làm việc chủ yếu với số, tiếp tục dùng `OptionalInt` và các API chuyên biệt sẽ tránh boxing không cần thiết.

## 10. Ví dụ Java hoàn chỉnh: truy email liên hệ cho đơn hàng

Bài toán: hệ thống có danh sách đơn hàng và khách hàng. Chỉ trả email khi thỏa tất cả điều kiện: đơn hàng tồn tại, đã thanh toán, đạt số tiền tối thiểu, khách hàng tồn tại và đang hoạt động, có email không trắng. Kết quả chuẩn hóa email bằng `strip()` và chuyển chữ thường theo `Locale.ROOT`.

Ví dụ độc lập chạy với Java 17+, lưu vào `OptionalPipelineDemo.java`:

```java
import java.util.List;
import java.util.Locale;
import java.util.Optional;

public class OptionalPipelineDemo {
    record Customer(
        String id,
        String name,
        boolean active,
        Optional<String> email
    ) {}

    record Order(
        String id,
        String customerId,
        long total,
        boolean paid
    ) {}

    static Optional<Customer> findCustomer(
            List<Customer> customers,
            String id
    ) {
        return customers.stream()
            .filter(customer -> customer.id().equals(id))
            .findFirst();
    }

    static Optional<String> normalizeEmail(Customer customer) {
        return customer.email()
            .map(String::strip)
            .filter(email -> !email.isBlank())
            .map(email -> email.toLowerCase(Locale.ROOT));
    }

    static Optional<String> emailForOrder(
            List<Order> orders,
            List<Customer> customers,
            String orderId
    ) {
        return orders.stream()
            .filter(order -> order.id().equals(orderId))
            .findFirst()
            .filter(Order::paid)
            .filter(order -> order.total() >= 100_000)
            .flatMap(order -> findCustomer(customers, order.customerId()))
            .filter(Customer::active)
            .flatMap(OptionalPipelineDemo::normalizeEmail);
    }

    public static void main(String[] args) {
        List<Customer> customers = List.of(
            new Customer("C-01", "An", true,
                Optional.of("  AN@Example.com  ")),
            new Customer("C-02", "Bình", true,
                Optional.empty()),
            new Customer("C-03", "Chi", false,
                Optional.of("chi@example.com")),
            new Customer("C-04", "Dung", true,
                Optional.of("   "))
        );

        List<Order> orders = List.of(
            new Order("O-01", "C-01", 150_000, true),
            new Order("O-02", "C-02", 200_000, true),
            new Order("O-03", "C-03", 220_000, true),
            new Order("O-04", "C-01", 90_000, true),
            new Order("O-05", "C-01", 300_000, false),
            new Order("O-06", "C-04", 250_000, true),
            new Order("O-07", "C-99", 250_000, true)
        );

        System.out.println(emailForOrder(
            orders, customers, "O-01"
        ).orElse("Không có email hợp lệ"));
        // an@example.com

        System.out.println(emailForOrder(
            orders, customers, "O-02"
        ).orElse("Không có email hợp lệ"));
        // Không có email hợp lệ

        System.out.println(emailForOrder(
            orders, customers, "O-99"
        ).orElse("Không có email hợp lệ"));
        // Không có email hợp lệ

        List<String> contactEmails = orders.stream()
            .filter(Order::paid)
            .filter(order -> order.total() >= 100_000)
            .map(order -> findCustomer(customers, order.customerId())
                .filter(Customer::active)
                .flatMap(OptionalPipelineDemo::normalizeEmail))
            .flatMap(Optional::stream)
            .distinct()
            .toList();

        System.out.println(contactEmails);
        // [an@example.com]
    }
}
```

### 10.1. Phân tích theo kiểu trả về

| Mã trong ví dụ | Kiểu kết quả | Vai trò |
| --- | --- | --- |
| `orders.stream().filter(...).findFirst()` | `Optional<Order>` | Đơn hàng có thể không tồn tại |
| `.filter(Order::paid)` | `Optional<Order>` | Bỏ đơn chưa thanh toán |
| `.filter(order -> order.total() >= 100_000)` | `Optional<Order>` | Bỏ đơn dưới ngưỡng |
| `.flatMap(order -> findCustomer(...))` | `Optional<Customer>` | Tra khách hàng; tránh `Optional<Optional<Customer>>` |
| `.filter(Customer::active)` | `Optional<Customer>` | Chỉ giữ khách hàng hoạt động |
| `.flatMap(OptionalPipelineDemo::normalizeEmail)` | `Optional<String>` | Lấy email có thể vắng mặt |
| `.map(String::strip)` | `Optional<String>` | Chuẩn hóa email nếu hiện diện |
| `.filter(email -> !email.isBlank())` | `Optional<String>` | Loại email trắng |
| `.flatMap(Optional::stream)` trên `Stream<Optional<String>>` | `Stream<String>` | Bỏ các Optional rỗng trong danh sách tra cứu |

`O-01` có email hợp lệ. `O-02` không có email, `O-03` có khách hàng ngừng hoạt động, `O-04` dưới ngưỡng, `O-05` chưa thanh toán, `O-06` chứa email trắng và `O-07` trỏ tới khách hàng không tồn tại. Tất cả những trường hợp không đạt sẽ được biểu diễn bằng `Optional.empty()`.

### 10.2. Những giới hạn có chủ đích của ví dụ

- Hàm `normalizeEmail` chỉ loại khoảng trắng đầu/cuối, từ chối chuỗi trắng và chuyển chữ thường. Nó **không xác thực cú pháp email đầy đủ**. Trong hệ thống thực, việc chuyển chữ thường toàn bộ email có thể không phù hợp với mọi chính sách địa chỉ; cần lựa chọn quy tắc chuẩn hóa theo yêu cầu hệ thống.
- `findCustomer` duyệt danh sách mỗi lần được gọi; trên dữ liệu lớn, nhiều đơn hàng và khách hàng nên cân nhắc lập chỉ mục khách hàng bằng `Map<String, Customer>` để tránh tra cứu tuyến tính lặp lại.
- Trả `Optional.empty()` cho nhiều lý do khác nhau giúp đơn giản hóa ví dụ. Nếu cần biết lý do thất bại để báo người dùng hoặc audit, hãy thiết kế kiểu kết quả chứa trạng thái/lỗi riêng.

## 11. Kết hợp Optional với grouping và các collector

Với bài toán thống kê, có thể tìm phần tử lớn nhất trong từng nhóm:

```java
record Product(String category, String name, long price) {}

List<Product> products = List.of(
    new Product("Sách", "Java", 200),
    new Product("Sách", "SQL", 150),
    new Product("Thiết bị", "Chuột", 300)
);

Map<String, Optional<Product>> mostExpensive = products.stream()
    .collect(Collectors.groupingBy(
        Product::category,
        Collectors.maxBy(
            Comparator.comparingLong(Product::price)
        )
    ));
```

Ví dụ cần import `java.util.Map`, `java.util.Comparator` và `java.util.stream.Collectors`.

`Collectors.maxBy(...)` là collector trả `Optional<Product>` cho từng nhóm theo hợp đồng collector. Với một nhóm rỗng nhân tạo trong quá trình tổng hợp hoặc khi nhận dữ liệu từ API có thể thiếu, Optional giúp biểu đạt khả năng không có phần tử thích hợp; các nhóm sinh ra bởi `groupingBy` từ phần tử đầu vào thông thường có ít nhất một phần tử.

Sau khi lấy `Optional<Product>` của nhóm “Sách”, có thể ánh xạ:

```java
Optional<String> name = mostExpensive
    .getOrDefault("Sách", Optional.empty())
    .map(Product::name);

System.out.println(name.orElse("Không có sản phẩm")); // Java
```

Nếu cần gom tên của các sản phẩm đắt nhất ở tất cả nhóm:

```java
List<String> names = mostExpensive.values().stream()
    .flatMap(Optional::stream)
    .map(Product::name)
    .sorted()
    .toList();

// [Java, Chuột] theo thứ tự chuỗi tự nhiên của Java.
```

Lưu ý: `Map.getOrDefault` khác `Optional.orElse`; phương thức thứ nhất xử lý khóa thiếu trong Map, còn phương thức thứ hai xử lý trạng thái rỗng của Optional.

### 11.1. Optional và collect không thay thế nhau

Một lỗi hiểu nhầm phổ biến là dùng Optional để tích lũy nhiều phần tử. Optional chỉ mang 0 hoặc 1 giá trị. Nếu cần thu nhiều đơn hàng, dùng `collect` hoặc `toList` trên Stream. Khi kết quả sau phép kết thúc có thể vắng mặt, dùng Optional để tiếp tục ánh xạ/kiểm tra.

Ví dụ tổng tiền từ nhiều đơn hàng:

```java
long total = orders.stream()
    .filter(Order::paid)
    .mapToLong(Order::total)
    .sum(); // long, không phải Optional<Long>
```

Nếu nghiệp vụ muốn phân biệt “không có đơn phù hợp” với “tổng bằng 0”, có thể dùng `reduce(Long::sum)` trên `LongStream` để nhận `OptionalLong`, hoặc một kiểu tổng hợp có số lượng và tổng tiền.

## 12. Null, ngoại lệ và tác động phụ

### 12.1. Tạo Optional đúng cách từ nguồn có thể null

```java
String legacyEmail = null;

Optional<String> safe = Optional.ofNullable(legacyEmail);
Optional<String> empty = Optional.empty();

// Ném NullPointerException:
// Optional<String> broken = Optional.of(legacyEmail);
```

- `Optional.of(value)` dành cho giá trị **được bảo đảm khác null**.
- `Optional.ofNullable(value)` cho phép chuyển `null` thành `Optional.empty()`.
- `Optional.empty()` biểu diễn trạng thái không có giá trị.

Không nên lưu `null` vào một biến khai báo `Optional<String>`, vì như vậy đối tượng Optional bản thân đã thiếu, và các lời gọi `map`/`flatMap` sẽ lỗi:

```java
Optional<String> maybe = null; // Tránh thiết kế này.
// maybe.map(String::trim);    // NullPointerException
```

Một hàm đã công bố trả về `Optional<T>` nên trả về một Optional thực sự, dù là empty.

### 12.2. Optional không thay thế cơ chế quản lý lỗi

```java
Optional<Integer> number = Optional.of("abc")
    .map(Integer::parseInt); // NumberFormatException
```

Nếu dữ liệu sai định dạng, `map` không bắt và không tự chuyển ngoại lệ thành empty.

Dùng cách xử lý rõ ràng nếu muốn lỗi phân tích có thể được xem là “không có giá trị hợp lệ”:

```java
static Optional<Integer> tryParseInt(String text) {
    try {
        return Optional.of(Integer.parseInt(text));
    } catch (NumberFormatException e) {
        return Optional.empty();
    }
}

Optional<Integer> value = Optional.of("abc")
    .flatMap(OptionalLesson::tryParseInt);
```

`OptionalLesson` là tên lớp giả định chứa phương thức `tryParseInt`. Nếu cần hiển thị chính xác nguyên nhân lỗi, Optional rỗng thường không đủ: nên dùng một kiểu kết quả có thông tin lỗi hoặc cơ chế ngoại lệ phù hợp.

### 12.3. Không biến map và filter thành nơi chứa tác động phụ

Không nên dựa vào `map` hay `filter` để ghi trạng thái ngoài như một phần yêu cầu nghiệp vụ:

```java
List<String> audited = new ArrayList<>();

Optional<String> email = foundCustomer
    .flatMap(Customer::email)
    .map(value -> {
        audited.add(value); // Tác động phụ nên được tách rõ.
        return value;
    });
```

Đoạn mã dùng danh sách `audited` giả định có thể thay đổi; `ArrayList` nằm trong `java.util`. Trong ví dụ nhỏ, thao tác có thể chạy; nhưng luồng xử lý dễ bị gắn với trạng thái ngoài, và việc kết hợp với Stream song song hoặc thay đổi yêu cầu về thời điểm thực thi gây khó bảo trì.

Nếu chỉ cần quan sát kết quả sau cùng, dùng `ifPresent`. Nếu cần audit bắt buộc, thiết kế một bước nghiệp vụ rõ ràng và xác định chính sách khi thiếu dữ liệu. Đặc biệt, các hàm bên trong `Stream.map`/`filter` có thể bị bỏ qua do lazy evaluation, dừng sớm hoặc tối ưu của Stream; không nên đặt cập nhật bắt buộc ở đó.

## 13. Hiệu năng và vòng đời nguồn dữ liệu

`Optional.map`, `flatMap` và `filter` xử lý tối đa một giá trị, thường có chi phí nhỏ. Trong đa số trường hợp, chi phí lớn nằm ở **cách tìm giá trị ban đầu**:

```java
Optional<Customer> customer = customers.stream()
    .filter(c -> c.id().equals(targetId))
    .findFirst();
```

Lời gọi `findFirst` có thể duyệt một phần danh sách hoặc toàn bộ danh sách nếu không có khách hàng. Khi áp dụng trong vòng lặp nhiều đơn hàng, duyệt lại cùng danh sách nhiều lần có thể gây chi phí đáng kể. Với tra cứu lặp đi lặp lại, cân nhắc `Map` theo ID, cơ sở dữ liệu có chỉ mục hoặc thiết kế nguồn dữ liệu phù hợp.

### 13.1. Dừng sớm ở Stream khác với Optional đã có kết quả

`Stream.findFirst` và `Stream.findAny` có thể dừng sớm khi tìm được một phần tử. Khi đó:

```java
Optional<String> firstName = customers.stream()
    .filter(Customer::active)
    .findFirst()
    .map(Customer::name);
```

Stream có thể chỉ xử lý đến khách hàng hoạt động đầu tiên. Sau đó `Optional.map` áp dụng trên tối đa một kết quả tìm được; nó không phát lệnh duyệt tiếp nguồn.

Trong Stream song song, `findAny` có thể chọn một phần tử bất kỳ và kết quả giữa các lần chạy có thể khác nhau; `findFirst` tôn trọng *encounter order* nếu nguồn có thứ tự. Nếu quy tắc nghiệp vụ cần “khách hàng đầu tiên theo thời gian”, phải bảo đảm thứ tự nguồn hoặc sắp xếp rõ ràng trước phép tìm.

### 13.2. Optional không tự đóng tài nguyên của Stream

Nếu tìm kiếm trong tệp hay một Stream I/O, hãy đóng nguồn đúng cách:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

class FindFirstNonBlankLine {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("notes.txt");

        Optional<String> firstNonBlank;
        try (Stream<String> lines = Files.lines(path)) {
            firstNonBlank = lines
                .map(String::trim)
                .filter(text -> !text.isEmpty())
                .findFirst();
        }

        String upper = firstNonBlank
            .map(String::toUpperCase)
            .orElse("KHÔNG CÓ DÒNG");

        System.out.println(upper);
    }
}
```

Ví dụ giả định `notes.txt` tồn tại. `Files.lines` gắn với tài nguyên phải đóng; `findFirst()` không tự đóng Stream. Sau khối `try-with-resources`, Optional chứa một `String` đã được lấy, có thể xử lý tiếp mà không cần tệp mở.

Nếu giá trị chứa trong Optional lại là một đối tượng giữ tài nguyên, việc xử lý vòng đời của đối tượng đó vẫn là trách nhiệm của ứng dụng.

### 13.3. Không tạo Optional chỉ để tránh mọi nhánh điều khiển

Optional hữu ích khi một kết quả thực sự có thể vắng mặt. Nếu phương thức luôn có giá trị thì trả đúng kiểu `T` có thể rõ hơn. Với hành động nhiều nhánh hoặc cần phân biệt nhiều nguyên nhân thất bại, một cấu trúc điều khiển rõ ràng hay một kiểu result riêng có thể phù hợp hơn chuỗi Optional quá dài.

## 14. Các lỗi thường gặp

| Sai lầm | Hệ quả | Cách giải quyết |
| --- | --- | --- |
| `optional.map(x -> findSomething(x))` khi `findSomething` trả `Optional<U>` | Tạo `Optional<Optional<U>>`. | Dùng `flatMap`. |
| `optional.flatMap(x -> x.getName())` khi `getName` trả `String` | Sai kiểu: `flatMap` chờ `Optional`. | Dùng `map`. |
| `optional.flatMap(x -> null)` | `NullPointerException`. | Trả `Optional.empty()` hoặc `Optional.ofNullable(...)`. |
| Gọi `Optional.of(null)` | `NullPointerException` ngay khi tạo. | Dùng `ofNullable` khi null hợp lệ. |
| Nghĩ `Optional.map` luôn trì hoãn lambda đến terminal | Optional không có terminal pipeline như Stream. | Hiểu rằng mapper chạy ngay nếu Optional có giá trị. |
| Viết `optional.get()` mà không xử lý empty | `NoSuchElementException`. | `map`, `flatMap`, `filter`, `orElseGet` hoặc `orElseThrow`. |
| Dùng `orElse(expensiveFallback())` để tránh tính fallback khi có giá trị | Fallback vẫn được tính trước lời gọi. | `orElseGet(() -> expensiveFallback())`. |
| Nghĩ `Optional.filter` trả boolean | Trả `Optional<T>`. | Dùng `isPresent()` để hỏi trạng thái cuối nếu cần boolean. |
| Mong `map(Integer::parseInt)` tự nuốt lỗi | `NumberFormatException` vẫn lan truyền. | Kiểm tra đầu vào hoặc chuyển lỗi theo chính sách rõ ràng. |
| Gọi `OptionalInt.map` tương tự `Optional<T>.map` | Primitive Optional không cung cấp API đó. | Dùng `stream().mapToObj(...).findFirst()` hoặc xử lý số trực tiếp. |
| Dùng `Stream.flatMap` với mapper trả Optional | Sai kiểu; Stream cần mapper trả Stream. | `flatMap(x -> maybeValue(x).stream())`. |
| Giả định Optional.empty giải thích lý do lỗi | Mất phân biệt nhiều trường hợp không đạt. | Dùng kiểu kết quả giàu thông tin khi nghiệp vụ cần. |
| Sửa trạng thái ngoài trong lambda của pipeline và dựa vào thứ tự gọi | Lazy/parallel/short-circuit có thể thay đổi hành vi. | Tách tác động phụ thành bước nghiệp vụ rõ ràng. |
| Nghĩ `findFirst` tự đóng tệp | Rò rỉ tài nguyên nguồn. | `try-with-resources`. |

## 15. Bài tập tự thực hành

**Bài 1 — Lấy mã bản ghi.** Cho `Stream<Product>` và điều kiện `price > 100_000`. Dùng `findFirst` nhận `Optional<Product>`, rồi `map(Product::id)` để có `Optional<String>`. Thử nguồn rỗng.

**Bài 2 — Hai lần tra cứu.** Cho `Optional<Order>` có `customerId`, và hàm `findCustomer(String)` trả `Optional<Customer>`. So sánh kiểu trả về khi dùng `map` và `flatMap`. Chuyển thành một chuỗi kết quả `Optional<String>` chứa tên.

**Bài 3 — Điều kiện sau ánh xạ.** Cho `Optional<String>` với giá trị `"  Java  "`. Dùng `map(String::trim)` rồi `filter(text -> text.length() >= 4)`, sau đó `orElse("Không đạt")`. Thử chuỗi trống hoặc Optional.empty.

**Bài 4 — Danh sách Optional.** Cho `List<Optional<Integer>>` chứa ba Optional có giá trị và hai Optional rỗng. Dùng `stream().flatMap(Optional::stream)` để thu `List<Integer>` chỉ gồm các số hiện diện.

**Bài 5 — Giá trị mặc định tốn chi phí.** Viết hàm tạo mặc định có log. So sánh số lần gọi hàm khi dùng `orElse(expensive())` và `orElseGet(() -> expensive())` trên Optional đã có giá trị.

**Bài 6 — Kết quả từ primitive stream.** Dùng `IntStream.of(4, 7, 2).max()`. Chuyển `OptionalInt` thành `Optional<String>` mô tả giá trị lớn nhất bằng `stream().mapToObj(...).findFirst()`. Kiểm tra với `IntStream.empty()`.

**Bài 7 — Lý do không hợp lệ.** Một đơn hàng có thể không tồn tại, chưa thanh toán hoặc chưa đạt ngưỡng. Thử viết `Optional<Order>` với `filter`. Sau đó đề xuất kiểu kết quả phân biệt được cả ba trạng thái và giải thích khi nào cần dùng thay Optional.

**Bài 8 — Nguồn cần đóng.** Đọc các dòng trong tệp bằng `Files.lines`, lấy dòng đầu tiên không rỗng với `findFirst` và chuẩn hóa bằng `Optional.map` sau khi đã đóng tệp. Xác định vị trí đặt `try-with-resources`.

Gợi ý Bài 4:

```java
List<Integer> present = optionals.stream()
    .flatMap(Optional::stream)
    .toList();
```

Trong đoạn này, `optionals` được giả định là `List<Optional<Integer>>` đã khai báo. Nếu danh sách chứa chính tham chiếu `null` thay vì `Optional.empty()`, cần làm sạch dữ liệu đầu vào vì `Optional::stream` không thể gọi trên `null`.

## 16. Ghi nhớ cốt lõi

- **`Optional<T>`** biểu diễn một kết quả có thể vắng mặt, thường nhận từ `findFirst`, `findAny`, `min`, `max` hoặc `reduce` không identity; nó không phải Stream nhiều phần tử.
- **`Optional.map`** dùng cho hàm `T -> U`; nếu giá trị hiện diện, nó áp dụng mapper và bọc kết quả bằng Optional. Mapper trả `null` làm kết quả rỗng.
- **`Optional.flatMap`** dùng cho hàm `T -> Optional<U>`; tránh tạo `Optional<Optional<U>>`. Mapper của `flatMap` phải trả đối tượng Optional khác `null`.
- **`Optional.filter`** kiểm tra `Predicate<T>` nếu có giá trị; điều kiện sai sẽ cho `Optional.empty()`, còn kiểu giá trị bên trong không đổi.
- **`map`, `flatMap`, `filter` trên Optional không lazy theo kiểu Stream pipeline.** Chúng xử lý tối đa một giá trị khi được gọi; nếu Optional rỗng, hàm hành vi không được gọi.
- **`Optional.stream()` (Java 9+)** là cầu nối thuận tiện để làm phẳng `Stream<Optional<T>>` bằng `flatMap(Optional::stream)`.
- **`orElse`, `orElseGet`, `orElseThrow` và `ifPresent`** biểu diễn chính sách cho kết quả cuối; phân biệt việc đánh giá sớm của `orElse` và đánh giá theo nhu cầu của `orElseGet`.
- **`OptionalInt`, `OptionalLong` và `OptionalDouble`** là các kiểu chuyên biệt với API khác `Optional<T>`; có thể dùng `stream()` và `mapToObj` khi cần chuyển sang kiểu đối tượng.
- **Optional không tự bắt ngoại lệ, không tự quản lý tài nguyên và không giải thích nhiều lý do thất bại.** Cần chọn kiểu kết quả, quy tắc xử lý lỗi, chiến lược tra cứu và vòng đời nguồn cho đúng bài toán.
- Khi kết hợp với pipeline lazy, grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers trong **JAVA_STREAM_API**, hãy giữ rõ ranh giới giữa **luồng nhiều phần tử** và **một kết quả tùy chọn**.
