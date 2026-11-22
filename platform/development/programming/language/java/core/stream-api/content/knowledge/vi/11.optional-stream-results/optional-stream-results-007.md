# Kết hợp kết quả tìm kiếm với pipeline tiếp theo

> **Chương:** Optional trong kết quả Stream  
> **Module:** `JAVA_STREAM_API` — học cách xử lý dữ liệu khai báo bằng Java Stream API qua pipeline lazy, `filter`, `map`, `reduce`, `collect`, cùng các kỹ thuật grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers. Khi xây dựng pipeline cần lưu ý trạng thái, tài nguyên và hiệu năng.

Một câu hỏi rất thường gặp khi xử lý dữ liệu là: **Sau khi tìm được một đối tượng bằng Stream, làm thế nào tiếp tục lọc, biến đổi hoặc duyệt dữ liệu liên quan đến đối tượng đó?** Ví dụ, ta tìm một đơn hàng đã thanh toán, sau đó tìm khách hàng tương ứng; hoặc tìm một đơn hàng rồi lập danh sách mã sản phẩm từ các dòng hàng của nó.

Các thao tác tìm kiếm của Stream thường trả về `Optional<T>`, vì không thể bảo đảm sẽ có kết quả. Để nối tiếp một cách an toàn, cần phân biệt ba tình huống:

1. **Biến đổi một kết quả có thể vắng mặt:** dùng `Optional.map`.
2. **Chuyển từ một kết quả tìm kiếm sang một kết quả tìm kiếm khác:** dùng `Optional.flatMap`.
3. **Đưa kết quả có thể vắng mặt trở lại pipeline Stream:** dùng `Optional.stream()` (Java 9+).

Bài học sử dụng cú pháp Java 17+, đồng thời giải thích cách xử lý nguồn rỗng, giá trị `null`, các phép toán `findFirst`/`findAny`, `min`/`max`, và chi phí khi tìm kiếm lồng nhau.

## 1. Vì sao kết quả tìm kiếm là `Optional`?

Xét ví dụ tìm sản phẩm theo mã:

```java
import java.util.List;
import java.util.Optional;

record Product(String code, String name, int price) {}

List<Product> products = List.of(
        new Product("P-01", "Sổ tay", 40_000),
        new Product("P-02", "Bút", 15_000),
        new Product("P-03", "Cặp tài liệu", 180_000)
);

Optional<Product> found = products.stream()
        .filter(p -> p.code().equals("P-02"))
        .findFirst();
```

Sau `filter`, Stream có thể còn một hoặc nhiều phần tử, cũng có thể không còn phần tử nào. `findFirst()` là **terminal operation**: nó kết thúc pipeline và trả về một `Optional<Product>`, có thể chứa sản phẩm được tìm thấy hoặc rỗng nếu không có sản phẩm phù hợp.

| Terminal operation trên `Stream<T>` | Kiểu kết quả | Ý nghĩa |
| --- | --- | --- |
| `findFirst()` | `Optional<T>` | Lấy phần tử đầu tiên theo encounter order, nếu tồn tại. |
| `findAny()` | `Optional<T>` | Lấy một phần tử bất kỳ; có thể khác nhau khi xử lý song song. |
| `min(comparator)` | `Optional<T>` | Lấy một phần tử nhỏ nhất theo comparator. |
| `max(comparator)` | `Optional<T>` | Lấy một phần tử lớn nhất theo comparator. |

Với primitive stream, các phép tìm kiếm/cực trị tương ứng trả `OptionalInt`, `OptionalLong` hoặc `OptionalDouble`, chứ không phải `Optional<Integer>`, `Optional<Long>` hay `Optional<Double>`.

**Phân biệt đối tượng Stream và Optional:** `Stream<T>` có thể chứa nhiều phần tử và thường xử lý lazy; `Optional<T>` chỉ biểu diễn **không hoặc một giá trị**. `Optional.map` hoặc `Optional.flatMap` áp dụng ngay cho giá trị đang có nếu không rỗng; chúng không phải phép toán trung gian lazy của Stream.

## 2. `Optional.map`: biến đổi một kết quả tìm kiếm

Nếu tìm được một sản phẩm nhưng chỉ cần tên, hãy dùng `map` trên kết quả `Optional<Product>`:

```java
Optional<String> productName = found.map(Product::name);

System.out.println(productName.orElse("Không tìm thấy"));
// Bút
```

Nếu `found` là `Optional.empty()`, `Product::name` **không được gọi** và `productName` cũng rỗng. Không cần gọi `get()` hoặc viết `if (found.isPresent())` để truy cập thủ công.

Một chuỗi phép biến đổi có thể viết trực tiếp:

```java
String label = products.stream()
        .filter(p -> p.code().equals("P-02"))
        .findFirst()                       // Optional<Product>
        .map(Product::name)               // Optional<String>
        .map(name -> name.toUpperCase())  // Optional<String>
        .orElse("KHÔNG TÌM THẤY");       // String

System.out.println(label); // BÚT
```

Kiểu trả về thay đổi tại mỗi bước là điều quan trọng: `findFirst` không trả `Product`, `map(Product::name)` không trả `String`, và `orElse(...)` mới là bước giải nén thành `String`.

Với `Optional.map`, nếu mapper trả về `null` thì kết quả trở thành `Optional.empty()`. Tuy nhiên, nên định nghĩa rõ chính sách dữ liệu thiếu thay vì âm thầm dựa vào hành vi này khi `null` là lỗi dữ liệu.

### Thêm điều kiện bằng `Optional.filter`

Khi đã có một ứng viên và cần xét thêm điều kiện:

```java
Optional<Product> affordable = found
        .filter(p -> p.price() <= 20_000);

System.out.println(affordable.map(Product::code).orElse("không đạt"));
// P-02
```

`Optional.filter(predicate)` chỉ kiểm tra **tối đa một** giá trị đang chứa. Nếu predicate sai, kết quả là `Optional.empty()`. Nó khác `Stream.filter(predicate)`, vốn có thể kiểm tra nhiều phần tử trong một nguồn dữ liệu.

## 3. `Optional.flatMap`: nối hai bước tìm kiếm

Giả sử đã tìm thấy một đơn hàng. Mỗi đơn hàng có `customerId`; bước tiếp theo cần tìm đối tượng khách hàng tương ứng.

```java
Optional<Order> order = orders.stream()
        .filter(o -> o.id().equals(requestedId))
        .findFirst();

// Tìm khách hàng tạo ra một Optional<Customer> khác.
Optional<Customer> customer = order.flatMap(o ->
        customers.stream()
                .filter(c -> c.id().equals(o.customerId()))
                .findFirst()
);
```

Đoạn trên sử dụng `Order`, `Customer`, `orders`, `customers` và `requestedId` được định nghĩa đầy đủ trong chương trình ở mục 5.

Tại sao dùng `flatMap` thay vì `map`? Vì callback của lần tìm kiếm thứ hai **đã trả về `Optional<Customer>`**:

```java
// map tạo Optional lồng trong Optional:
Optional<Optional<Customer>> nested = order.map(o ->
        customers.stream()
                .filter(c -> c.id().equals(o.customerId()))
                .findFirst()
);

// flatMap làm phẳng còn một lớp Optional:
Optional<Customer> flattened = order.flatMap(o ->
        customers.stream()
                .filter(c -> c.id().equals(o.customerId()))
                .findFirst()
);
```

Quy tắc lựa chọn:

| Tình huống | Phép toán | Kiểu kết quả |
| --- | --- | --- |
| Hàm `T -> U` | `Optional<T>.map(...)` | `Optional<U>` |
| Hàm `T -> Optional<U>` | `Optional<T>.flatMap(...)` | `Optional<U>` |
| Hàm `T -> boolean` | `Optional<T>.filter(...)` | `Optional<T>` |

Nếu `order` rỗng, lambda bên trong `flatMap` không chạy, vì thế không phát sinh lần tìm khách hàng. Nếu có đơn hàng nhưng không tìm thấy khách hàng, `flatMap` trả `Optional.empty()`. `Optional.flatMap` yêu cầu mapper trả về một đối tượng `Optional` **không null**; mapper trả `null` sẽ gây `NullPointerException`.

## 4. `Optional.stream()`: chuyển về pipeline có 0 hoặc 1 phần tử

Từ Java 9, `Optional<T>` có phương thức:

```java
Stream<T> stream()
```

Nó tạo Stream chứa **một phần tử** nếu Optional có giá trị, hoặc Stream **rỗng** nếu Optional rỗng. Đây là cầu nối để tiếp tục dùng các thao tác Stream như `flatMap`, `filter`, `map`, `distinct`, `sorted` và `toList`.

```java
import java.util.Optional;

List<String> present = Optional.of("java").stream()
        .map(String::toUpperCase)
        .toList();
// [JAVA]

List<String> absent = Optional.<String>empty().stream()
        .map(String::toUpperCase)
        .toList();
// []
```

Hãy phân biệt `optional.stream()` với `collection.stream()`:

- `collection.stream()` có thể chứa mọi phần tử của collection.
- `optional.stream()` có tối đa một phần tử, chính là giá trị đang được chứa trong Optional.
- Khi giá trị chứa trong Optional **là một collection**, phải gọi thêm `flatMap` hoặc các bước khác để duyệt **các phần tử của collection đó**.

Ví dụ:

```java
Optional<List<Integer>> maybeNumbers = Optional.of(List.of(5, 3, 8));

List<Integer> values = maybeNumbers.stream()   // Stream<List<Integer>>
        .flatMap(List::stream)                 // Stream<Integer>
        .filter(n -> n > 4)
        .sorted()
        .toList();

// [5, 8]
```

Nếu viết `maybeNumbers.stream().map(List::size)`, ta sẽ chỉ nhận kích thước của danh sách đang được chứa, thay vì duyệt các số bên trong.

## 5. Ví dụ hoàn chỉnh: tìm đơn hàng, tìm khách và xử lý các dòng hàng

Ví dụ Java 17+ sau minh họa **hai hướng đi tiếp từ cùng một `Optional<Order>`**: tra cứu khách hàng bằng `flatMap`, và chuyển về Stream để xử lý nhiều dòng hàng bằng `Optional.stream()`. Lưu thành `OptionalPipelineDemo.java`:

```java
import java.util.List;
import java.util.Optional;

public class OptionalPipelineDemo {
    record LineItem(String sku, int quantity) {}
    record Order(
            String id,
            String customerId,
            boolean paid,
            List<LineItem> items
    ) {}
    record Customer(String id, String name, boolean active) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("OD-101", "C-01", true, List.of(
                        new LineItem("BOOK", 2),
                        new LineItem("PEN", 4))),
                new Order("OD-102", "C-02", false, List.of(
                        new LineItem("PEN", 1))),
                new Order("OD-103", "C-03", true, List.of(
                        new LineItem("BOOK", 1),
                        new LineItem("BAG", 1)))
        );

        List<Customer> customers = List.of(
                new Customer("C-01", "An", true),
                new Customer("C-02", "Bình", true),
                new Customer("C-03", "Chi", false)
        );

        String requestedId = "OD-101";
        Optional<Order> foundPaidOrder = orders.stream()
                .filter(o -> o.id().equals(requestedId))
                .filter(Order::paid)
                .findFirst();

        // Optional<Order> -> Optional<Customer> -> Optional<String>
        Optional<String> customerName = foundPaidOrder
                .flatMap(order -> customers.stream()
                        .filter(c -> c.id().equals(order.customerId()))
                        .filter(Customer::active)
                        .findFirst())
                .map(Customer::name);

        // Optional<Order> -> Stream<Order> -> Stream<LineItem>
        List<String> skus = foundPaidOrder.stream()
                .flatMap(o -> o.items().stream())
                .filter(item -> item.quantity() > 0)
                .map(LineItem::sku)
                .distinct()
                .sorted()
                .toList();

        // Trường hợp không tìm thấy đơn hàng nào.
        Optional<Order> missing = orders.stream()
                .filter(o -> o.id().equals("OD-999"))
                .findFirst();
        List<String> skusWhenMissing = missing.stream()
                .flatMap(o -> o.items().stream())
                .map(LineItem::sku)
                .toList();

        System.out.println("Khách hàng: "
                + customerName.orElse("Không tìm thấy khách đang hoạt động"));
        System.out.println("Mã hàng: " + skus);
        System.out.println("Không có đơn: " + skusWhenMissing);
    }
}
```

Kết quả:

```text
Khách hàng: An
Mã hàng: [BOOK, PEN]
Không có đơn: []
```

Dòng chảy dữ liệu của ví dụ:

```text
orders.stream()
     │
     └── filter(mã + đã thanh toán)
                    │
                    └── findFirst() ──► Optional<Order>
                                             │
                      ┌──────────────────────┴────────────────────────┐
                      │                                               │
             flatMap(tìm khách)                                stream()
                      │                                               │
              Optional<Customer>                             Stream<Order> (0..1)
                      │                                               │
                map(Customer::name)                           flatMap(items.stream)
                      │                                               │
              Optional<String>                               Stream<LineItem> (0..n)
                      │                                               │
                 orElse(...)                                 filter/map/distinct/sorted
                      │                                               │
                    "An"                                        [BOOK, PEN]
```

Lưu ý `foundPaidOrder` là một **Optional**, có thể dùng `map` hoặc gọi `stream()` nhiều lần. Mỗi lần gọi `foundPaidOrder.stream()` tạo một Stream mới; từng Stream vẫn là **đối tượng dùng một lần**, không được tái sử dụng sau terminal operation.

Nếu `requestedId` không tồn tại, `foundPaidOrder` sẽ rỗng: đường tra cứu khách hàng không gọi các hàm bên trong và đường duyệt các dòng hàng trả danh sách rỗng. Nhờ vậy, ta tránh phải tạo đối tượng `Order` giả hoặc viết các nhánh kiểm tra `null` thủ công.

## 6. Nối nhiều kết quả tìm kiếm bằng `Stream<Optional<T>>`

Đôi khi cần tra cứu **nhiều mã đầu vào** nhưng không phải mã nào cũng tồn tại. Một cách diễn đạt rõ ràng là `map` mỗi mã thành `Optional<Order>`, sau đó dùng `flatMap(Optional::stream)` để bỏ những kết quả rỗng và giữ các đối tượng tìm thấy:

```java
List<String> requestedIds = List.of("OD-101", "OD-999", "OD-103");

List<String> paidOrderIds = requestedIds.stream()
        .map(id -> orders.stream()
                .filter(o -> o.id().equals(id))
                .findFirst())              // Stream<Optional<Order>>
        .flatMap(Optional::stream)         // Stream<Order>
        .filter(Order::paid)
        .map(Order::id)
        .toList();

System.out.println(paidOrderIds);
// [OD-101, OD-103]
```

**`flatMap(Optional::stream)` hoạt động ra sao?** Với từng Optional, nó nhận Stream có 0 hoặc 1 phần tử và nối các Stream con lại. Kết quả là Stream chỉ chứa các đơn hàng được tìm thấy.

| Mã tìm kiếm | Kết quả `findFirst()` | Sau `Optional.stream()` |
| --- | --- | --- |
| OD-101 | `Optional[Order(...)]` | Một `Order` |
| OD-999 | `Optional.empty()` | Không có phần tử |
| OD-103 | `Optional[Order(...)]` | Một `Order` |

Trong các đoạn ví dụ này, `orders` và các `record` là dữ liệu của chương trình ở mục 5. Việc viết `orders.stream()` **bên trong** lambda tạo Stream tra cứu mới cho mỗi mã. Điều này hợp lệ khi `orders` là một `List`, nhưng có thể tốn thời gian khi lượng dữ liệu lớn.

### Chi phí khi tra cứu nhiều lần

Nếu có `m` mã và `n` đơn, mỗi lần gọi `orders.stream().filter(...).findFirst()` có thể duyệt tối đa `n` đơn. Tổng chi phí trong trường hợp xấu có thể gần **O(m × n)**.

Với số mã lớn, xây dựng chỉ mục trước để tra cứu gần O(1) trung bình theo mã là một hướng phù hợp hơn:

```java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

// Yêu cầu id của Order là duy nhất.
Map<String, Order> orderById = orders.stream()
        .collect(Collectors.toMap(Order::id, Function.identity()));

List<String> ids = requestedIds.stream()
        .map(id -> Optional.ofNullable(orderById.get(id)))
        .flatMap(Optional::stream)
        .filter(Order::paid)
        .map(Order::id)
        .toList();

// [OD-101, OD-103]
```

`Collectors.toMap` ở đây ném `IllegalStateException` nếu có mã đơn hàng trùng nhau; cần chọn chính sách xử lý trùng mã nếu nguồn thực tế không bảo đảm duy nhất. Khi chỉ tra cứu một vài mã, cách dùng `findFirst()` trực tiếp thường dễ đọc hơn và không cần tạo chỉ mục.

## 7. Xử lý Optional rỗng và chiến lược dự phòng

Để nối pipeline an toàn, nên **trì hoãn việc giải nén Optional** cho tới nơi nghiệp vụ thực sự cần giá trị không bọc. Các phương thức thường dùng:

| Phương thức | Khi Optional có giá trị | Khi Optional rỗng |
| --- | --- | --- |
| `map(f)` | Biến đổi giá trị bằng `f` | Trả Optional rỗng |
| `flatMap(f)` | Gọi `f` và nhận Optional mới | Trả Optional rỗng |
| `filter(p)` | Giữ khi `p` đúng | Trả Optional rỗng |
| `stream()` | Trả Stream có một phần tử | Trả Stream rỗng |
| `ifPresent(action)` | Thực hiện action | Không thực hiện action |
| `orElse(value)` | Lấy giá trị có sẵn | Lấy `value` |
| `orElseGet(supplier)` | Lấy giá trị có sẵn | Gọi supplier để lấy giá trị |
| `or(supplier)` | Giữ Optional hiện tại | Gọi supplier trả về Optional thay thế (Java 9+) |
| `orElseThrow(...)` | Lấy giá trị | Ném ngoại lệ |

Ví dụ dùng giá trị mặc định:

```java
String name = customerName.orElse("Khách chưa xác định");
```

### `orElse` khác `orElseGet`

`orElse` nhận **giá trị được tính trước** khi gọi phương thức, ngay cả khi Optional đã có giá trị. `orElseGet` chỉ gọi supplier khi Optional rỗng:

```java
String label = customerName.orElseGet(() -> createFallbackLabel());
```

Ở đây, `createFallbackLabel()` là tên hàm minh họa do ứng dụng cung cấp. Nếu việc tính nhãn dự phòng tốn tài nguyên hoặc có side effect, `orElseGet` giúp tránh gọi không cần thiết. Nếu chỉ là chuỗi cố định, `orElse("...")` là đủ.

Nếu muốn **tìm ở nguồn dự phòng**, `Optional.or` (Java 9+) giữ kiểu Optional mà chưa cần ép về giá trị:

```java
Optional<Product> result = products.stream()
        .filter(p -> p.code().equals("P-999"))
        .findFirst()
        .or(() -> products.stream()
                .filter(p -> p.price() <= 20_000)
                .findFirst());

// Optional chứa P-02 từ phép tìm dự phòng.
```

Supplier của `or` chỉ chạy khi phép tìm chính trả Optional rỗng. Đây là cách nối hai nguồn tìm kiếm hợp lý khi nguồn thứ hai là dự phòng, không phải là phép biến đổi kết quả từ nguồn thứ nhất.

### Khi nào nên ném ngoại lệ?

```java
Order required = orders.stream()
        .filter(o -> o.id().equals(requestedId))
        .findFirst()
        .orElseThrow(() -> new IllegalArgumentException(
                "Đơn hàng không tồn tại: " + requestedId));
```

Dùng `orElseThrow` khi thiếu dữ liệu là lỗi cần báo ngay. Nếu thiếu dữ liệu là tình huống bình thường (ví dụ người dùng tìm mã không tồn tại), tiếp tục trả `Optional`, danh sách rỗng hoặc thông báo dự phòng phù hợp hơn. Tránh gọi `get()` không kiểm tra, vì nó ném `NoSuchElementException` khi Optional rỗng.

## 8. `OptionalInt`, `OptionalLong`, `OptionalDouble` kết nối như thế nào?

`IntStream.findFirst()`, `IntStream.max()` và `IntStream.min()` trả `OptionalInt`; `LongStream` và `DoubleStream` có các Optional chuyên biệt tương ứng.

```java
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalInt largest = IntStream.of(3, 8, 5).max();

int doubled = largest.stream()
        .map(n -> n * 2)
        .findFirst()
        .orElse(0);

System.out.println(doubled); // 16
```

Từ Java 9, `OptionalInt.stream()` tạo `IntStream` chứa 0 hoặc 1 phần tử; `OptionalLong.stream()` và `OptionalDouble.stream()` tương tự. Các Optional nguyên thủy **không có toàn bộ API như `Optional<T>`**: ví dụ trong Java 17, `OptionalInt` không có `map` và `flatMap` kiểu tổng quát. Nếu cần pipeline biến đổi, chuyển về primitive stream bằng `.stream()` rồi gọi `IntStream.map` hoặc các phép khác.

Khi kết quả đầu vào là `Stream<OptionalInt>`, có thể làm phẳng sang primitive stream:

```java
List<OptionalInt> matches = List.of(
        OptionalInt.of(4),
        OptionalInt.empty(),
        OptionalInt.of(7)
);

int sum = matches.stream()
        .flatMapToInt(OptionalInt::stream)
        .sum();

System.out.println(sum); // 11
```

Cách này tránh boxing khi cần tính tổng. Nếu bài toán chỉ cần giá trị thay thế, `largest.orElse(0)` thường ngắn hơn.

## 9. Những hiểu lầm dễ gặp về vòng đời, thứ tự và `null`

### Terminal operation đã kết thúc Stream cũ

```java
// Stream<Order> pipeline = orders.stream().filter(Order::paid);
// Optional<Order> first = pipeline.findFirst();
// pipeline.filter(o -> o.id().startsWith("OD-")); // Không hợp lệ
```

Sau `findFirst`, biến `pipeline` đã bị tiêu thụ; không được gọi thêm phép toán trên **cùng đối tượng Stream**. Muốn xử lý tiếp phần tử tìm được, dùng `first.map(...)`, `first.flatMap(...)` hoặc `first.stream()`. Muốn duyệt lại **nguồn**, tạo Stream mới nếu nguồn hỗ trợ. Với nguồn I/O chỉ đọc được một lần, cần lập kế hoạch khác và đóng tài nguyên theo đúng vòng đời.

### `findFirst` và `findAny` có hợp đồng khác nhau

Trên `List` có thứ tự, `findFirst` trả phần tử phù hợp đầu tiên theo encounter order. `findAny` được phép trả **bất kỳ phần tử phù hợp nào**, hữu ích khi ứng dụng không cần ưu tiên vị trí và đặc biệt khi chạy song song. Không dùng `findAny` nếu kết quả nghiệp vụ phụ thuộc vào bản ghi đầu tiên.

Nếu sau đó `flatMap` tiếp sang tìm kiếm khác, sự lựa chọn khác nhau ở bước đầu có thể dẫn đến kết quả cuối khác nhau. Hãy quyết định rõ việc chọn bản ghi đầu tiên hay bất kỳ bản ghi nào.

### Optional không tự giải quyết dữ liệu `null`

Đừng xem `Optional` là cơ chế tự sửa dữ liệu nguồn lỗi:

```java
import java.util.Objects;

List<String> namesWithNull = java.util.Arrays.asList(
        null, "An", "Bình");

Optional<String> firstValid = namesWithNull.stream()
        .filter(Objects::nonNull)
        .findFirst();
```

`findFirst`/`findAny` có thể ném `NullPointerException` nếu phần tử được chọn là `null`; ở ví dụ trên, `Objects::nonNull` loại các giá trị đó trước khi tìm kiếm. `Optional.of(null)` cũng ném `NullPointerException`, trong khi `Optional.ofNullable(null)` tạo `Optional.empty()`. Tại ranh giới dữ liệu thiếu có chủ đích, `ofNullable` phù hợp hơn.

### `Optional` không có nghĩa là được phép làm mọi thứ với side effect

Những phép toán `map`/`flatMap` trong Optional hoạt động trên giá trị hiện có; nhưng nếu callback của chúng mở nguồn I/O, sửa dữ liệu dùng chung hoặc phụ thuộc thời gian, việc lặp nhiều lần có thể tạo kết quả khác nhau. Trong các Stream lồng nhau, lambda nên không can thiệp vào nguồn và hạn chế trạng thái biến đổi, nhất là khi có `parallelStream()`.

## 10. Chọn hình thức nối pipeline phù hợp

| Nhu cầu | Cách diễn đạt thường phù hợp | Lý do |
| --- | --- | --- |
| Tìm đơn hàng rồi lấy mã khách | `findFirst().map(Order::customerId)` | Hàm biến đổi trả giá trị trực tiếp. |
| Tìm đơn hàng rồi tìm đối tượng khách | `findFirst().flatMap(o -> customers.stream()...findFirst())` | Hàm tra cứu thứ hai trả Optional. |
| Tìm đơn hàng rồi duyệt các dòng hàng | `findFirst().stream().flatMap(o -> o.items().stream())` | Trở lại Stream 0 hoặc 1 đơn, sau đó mở rộng thành 0 hoặc nhiều dòng hàng. |
| Tìm nhiều mã, bỏ qua mã không tồn tại | `map(id -> lookup(id)).flatMap(Optional::stream)` | Làm phẳng Stream chứa nhiều Optional. |
| Tìm dự phòng khi không có kết quả | `findFirst().or(() -> alternativeFind())` | Vẫn giữ kiểu Optional; tìm dự phòng khi cần. |
| Chỉ cần một giá trị hiển thị, có mặc định | `findFirst().map(...).orElse("N/A")` | Chuyển về kiểu thường ở ranh giới hiển thị. |
| Thiếu dữ liệu là lỗi | `findFirst().orElseThrow(...)` | Làm rõ tiền điều kiện bắt buộc. |

Chọn phương án dựa trên **kiểu trả về của bước kế tiếp** và số lượng phần tử cần xử lý; không nên mặc định giải nén Optional ngay khi tìm thấy kết quả.

## 11. Bài tập tự kiểm tra

**Bài 1 — Biến đổi kết quả tìm kiếm.** Cho `Optional<String> value = Optional.of("java")`. Viết biểu thức tạo `Optional<Integer>` chứa độ dài chuỗi.

```java
Optional<Integer> length = value.map(String::length);
// Optional[4]
```

**Bài 2 — Kết quả tìm kiếm lồng nhau.** Vì sao `order.map(o -> customers.stream().filter(...).findFirst())` có kiểu `Optional<Optional<Customer>>`?

**Đáp án:** `findFirst` của Stream thứ hai đã trả `Optional<Customer>`. `Optional.map` lại bọc kết quả đó trong một Optional khác. Dùng `flatMap` nếu muốn thu được `Optional<Customer>` trực tiếp.

**Bài 3 — Optional không có dữ liệu.** Kết quả của đoạn sau là gì?

```java
List<Integer> result = Optional.<Integer>empty()
        .stream()
        .map(n -> n * 10)
        .toList();
```

**Đáp án:** Danh sách rỗng `[]`. Pipeline không gọi mapper vì Stream không có phần tử.

**Bài 4 — Nhiều Optional.** Với `[Optional.of(2), Optional.empty(), Optional.of(5)]`, làm sao lấy tổng `7` mà không gọi `get()`?

```java
int total = List.of(Optional.of(2), Optional.<Integer>empty(), Optional.of(5))
        .stream()
        .flatMap(Optional::stream)
        .mapToInt(Integer::intValue)
        .sum();
// 7
```

**Bài 5 — Phân biệt Stream và Optional.** Đoạn dưới có hợp lệ không?

```java
// Stream<String> s = List.of("An", "Bình").stream();
// Optional<String> first = s.findFirst();
// List<String> names = s.map(String::toUpperCase).toList();
```

**Đáp án:** Không. `findFirst` đã tiêu thụ `s`. Nếu muốn tạo luồng chỉ từ kết quả đã tìm được, dùng `first.stream().map(String::toUpperCase).toList()`; nếu muốn duyệt toàn bộ danh sách ban đầu, tạo Stream mới từ danh sách.

## Ghi nhớ

- `findFirst`, `findAny`, `min`, `max` là terminal operations trả `Optional<T>` vì có thể không tìm thấy phần tử.
- Dùng **`Optional.map`** khi bước tiếp theo trả giá trị thường; dùng **`Optional.flatMap`** khi bước tiếp theo đã trả Optional.
- Dùng **`Optional.stream()`** (Java 9+) để chuyển kết quả tìm kiếm thành Stream 0 hoặc 1 phần tử, rồi tiếp tục `filter`, `map`, `flatMap` hay `collect`.
- Dùng `Stream<Optional<T>>.flatMap(Optional::stream)` để bỏ các kết quả rỗng khi tìm kiếm nhiều mã; dùng `flatMapToInt(OptionalInt::stream)` khi dữ liệu là Optional nguyên thủy.
- Không dùng lại Stream sau terminal operation; xử lý thiếu dữ liệu có chủ đích bằng `orElse`, `orElseGet`, `or` hoặc `orElseThrow`, và cân nhắc chỉ mục để tránh tìm kiếm lồng nhau tốn chi phí.
