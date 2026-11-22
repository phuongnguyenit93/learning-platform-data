# Lọc dữ liệu bằng `filter` và các điều kiện kết hợp

> **Chương:** Lọc và biến đổi phần tử  
> **Module:** `JAVA_STREAM_API` — xử lý dữ liệu khai báo bằng Java Stream API qua pipeline lazy, `filter`, `map`, `reduce`, `collect`; mở rộng tới grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers, với sự chú ý tới trạng thái, tài nguyên và hiệu năng.

`filter` là một trong những phép toán được dùng nhiều nhất của Stream API. Thay vì duyệt danh sách bằng vòng lặp rồi tự thêm các phần tử đạt yêu cầu vào một danh sách khác, ta mô tả trực tiếp **điều kiện để một phần tử được giữ lại**. Trong thực tế, điều kiện thường không chỉ là “giá lớn hơn 100” mà còn kết hợp trạng thái, ngày tháng, quyền truy cập, từ khóa hoặc các lựa chọn tìm kiếm.

Sau bài học này, bạn có thể viết `filter` cho một điều kiện, kết hợp nhiều điều kiện bằng toán tử logic hoặc `Predicate`, tổ chức những điều kiện phức tạp theo cách dễ kiểm tra, đồng thời tránh các lỗi liên quan đến `null`, thứ tự xử lý và trạng thái dùng chung.

## 1. `filter` hoạt động như thế nào?

Chữ ký của phương thức trên `Stream<T>`:

```java
Stream<T> filter(Predicate<? super T> predicate)
```

- `Predicate<T>` là một functional interface có phương thức `boolean test(T value)`.
- Khi `predicate` trả về `true`, phần tử **được giữ lại**; trả về `false` thì **bị loại bỏ**.
- `filter` là **intermediate operation**: trả về một Stream để có thể nối tiếp các bước khác, không tự thu thập dữ liệu thành `List`.
- `filter` là phép toán **không trạng thái (stateless)** và **lazy**: mỗi phần tử có thể được kiểm tra độc lập, và quá trình xử lý thường chỉ bắt đầu khi có terminal operation.
- Với nguồn có encounter order như `List`, `filter` giữ nguyên thứ tự tương đối của những phần tử còn lại.

```java
import java.util.List;

List<Integer> numbers = List.of(9, 2, 7, 4, 8);

List<Integer> evenNumbers = numbers.stream()
        .filter(n -> n % 2 == 0)
        .toList();

System.out.println(evenNumbers);  // [2, 4, 8]
System.out.println(numbers);      // [9, 2, 7, 4, 8]
```

Trong ví dụ, `n -> n % 2 == 0` là một `Predicate<Integer>` được biểu diễn bằng lambda. `filter` tạo luồng kết quả mà không sửa danh sách `numbers`; `toList()` (Java 16+) là phép toán kết thúc tạo ra danh sách không cho phép sửa đổi qua các phương thức như `add` hoặc `remove`.

Sơ đồ logic:

```text
Nguồn List       filter(n -> n % 2 == 0)     toList()
   9          ────────── false ──────×
   2          ────────── true  ───────────→  2
   7          ────────── false ──────×
   4          ────────── true  ───────────→  4
   8          ────────── true  ───────────→  8
                                           [2, 4, 8]
```

## 2. Kết hợp điều kiện bằng `&&`, `||` và `!`

Một lambda `filter` có thể chứa biểu thức boolean với nhiều tiêu chí.

| Toán tử | Ý nghĩa | Ví dụ | Khi nào biểu thức là `true`? |
| --- | --- | --- | --- |
| `&&` | Và (AND) | `n > 0 && n < 10` | Cả hai điều kiện đúng. |
| `||` | Hoặc (OR) | `n < 0 || n > 100` | Ít nhất một điều kiện đúng. |
| `!` | Phủ định (NOT) | `!(n == 0)` | Điều kiện bên trong sai. |

Ví dụ lọc số nguyên dương, chẵn và nhỏ hơn 10:

```java
List<Integer> result = List.of(-4, 0, 2, 3, 8, 10, 12).stream()
        .filter(n -> n > 0 && n % 2 == 0 && n < 10)
        .toList();

// [2, 8]
```

Ví dụ lọc số **nằm ngoài** khoảng `[10, 20]`:

```java
List<Integer> outside = List.of(5, 10, 15, 20, 25).stream()
        .filter(n -> n < 10 || n > 20)
        .toList();

// [5, 25]
```

### Dùng dấu ngoặc để diễn đạt đúng nghiệp vụ

Java ưu tiên `!` trước `&&`, rồi mới tới `||`. Vì vậy, hai biểu thức sau **khác nhau**:

```java
// Nghĩa là: (đã thanh toán VÀ đủ giá trị) HOẶC là khách VIP.
paid && highValue || vip

// Nghĩa là: đã thanh toán VÀ (đủ giá trị HOẶC là khách VIP).
paid && (highValue || vip)
```

Nếu chính sách yêu cầu **mọi đơn đều phải thanh toán**, biểu thức thứ nhất sai: một đơn của khách VIP chưa thanh toán vẫn được giữ lại. Khi có cả AND và OR, hãy viết dấu ngoặc theo nhóm điều kiện nghiệp vụ ngay cả khi đã nhớ thứ tự ưu tiên toán tử.

### Short-circuit của các biểu thức logic

`&&` và `||` thực hiện *short-circuit evaluation* **trên từng phần tử**:

- Trong `a && b`, khi `a` là `false`, Java không cần đánh giá `b`.
- Trong `a || b`, khi `a` là `true`, Java không cần đánh giá `b`.

Ví dụ, `text != null && !text.isBlank()` an toàn nếu `text` là `null` vì Java sẽ không gọi `text.isBlank()` khi vế trái sai. Tránh thay `&&` thành `&` hoặc `||` thành `|` khi mục đích là short-circuit boolean: `&` và `|` luôn đánh giá cả hai vế.

Đây là short-circuit của **biểu thức điều kiện**. Nó khác với khả năng dừng sớm của **toàn pipeline** khi dùng `limit`, `findFirst`, `anyMatch` và các terminal operation phù hợp.

## 3. Ví dụ thực tế: tìm đơn hàng thỏa nhiều chính sách

Giả sử cần chọn đơn hàng theo quy tắc:

1. Trạng thái là `PAID`.
2. Tổng tiền ít nhất 100.
3. Ngày tạo từ **01/10/2026** trở đi (tính cả ngày đó).
4. Đồng thời phải là đơn ưu tiên **hoặc** có tổng tiền ít nhất 200.

Chương trình Java 17+ dưới đây chạy độc lập và có thể sao chép vào `FilterOrdersDemo.java`:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

public class FilterOrdersDemo {
    record Order(
            String id,
            String customer,
            String status,
            BigDecimal total,
            LocalDate createdAt,
            boolean priority
    ) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("DH-01", "An", "PAID",
                        new BigDecimal("120.00"), LocalDate.of(2026, 10, 5), true),
                new Order("DH-02", "Binh", "PENDING",
                        new BigDecimal("500.00"), LocalDate.of(2026, 10, 6), true),
                new Order("DH-03", "Chi", "PAID",
                        new BigDecimal("80.00"), LocalDate.of(2026, 10, 6), true),
                new Order("DH-04", "Dung", "PAID",
                        new BigDecimal("250.00"), LocalDate.of(2026, 10, 2), false),
                new Order("DH-05", "Em", "PAID",
                        new BigDecimal("160.00"), LocalDate.of(2026, 9, 30), true),
                new Order("DH-06", "Giang", "PAID",
                        new BigDecimal("180.00"), LocalDate.of(2026, 10, 7), true)
        );

        BigDecimal minimum = new BigDecimal("100.00");
        BigDecimal largeOrder = new BigDecimal("200.00");
        LocalDate startDate = LocalDate.of(2026, 10, 1);

        List<String> selectedIds = orders.stream()
                .filter(o -> "PAID".equals(o.status())
                        && o.total().compareTo(minimum) >= 0
                        && !o.createdAt().isBefore(startDate)
                        && (o.priority()
                            || o.total().compareTo(largeOrder) >= 0))
                .map(Order::id)
                .toList();

        System.out.println(selectedIds);
    }
}
```

Kết quả mong đợi:

```text
[DH-01, DH-04, DH-06]
```

| Đơn | Trạng thái | Tổng tiền | Ngày tạo | Ưu tiên | Kết quả |
| --- | --- | ---: | --- | --- | --- |
| DH-01 | PAID | 120 | 05/10/2026 | Có | Giữ: ưu tiên, đủ tiền và đúng ngày. |
| DH-02 | PENDING | 500 | 06/10/2026 | Có | Loại: chưa thanh toán. |
| DH-03 | PAID | 80 | 06/10/2026 | Có | Loại: dưới 100. |
| DH-04 | PAID | 250 | 02/10/2026 | Không | Giữ: tổng tiền ít nhất 200. |
| DH-05 | PAID | 160 | 30/09/2026 | Có | Loại: trước ngày bắt đầu. |
| DH-06 | PAID | 180 | 07/10/2026 | Có | Giữ: đơn ưu tiên. |

Chú ý ba chi tiết trong ví dụ:

- Dùng `"PAID".equals(o.status())` để so sánh **nội dung chuỗi**, tránh `==` (so sánh tham chiếu) và tránh lỗi nếu `status` là `null`.
- Dùng `BigDecimal.compareTo(...) >= 0` cho phép so sánh số tiền theo giá trị; `BigDecimal.equals(...)` còn xét cả `scale`, nên không phải lựa chọn phù hợp cho kiểm tra ngưỡng.
- Dùng `!createdAt.isBefore(startDate)` để bao gồm chính `startDate`. Cần bảo đảm `createdAt` khác `null` trước khi gọi phương thức trên nó.

## 4. Tách điều kiện thành `Predicate` có thể tái sử dụng

Khi điều kiện dài hoặc xuất hiện ở nhiều chỗ, `java.util.function.Predicate<T>` giúp đặt tên cho từng quy tắc và kết hợp chúng một cách rõ nghĩa:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.function.Predicate;

BigDecimal minimum = new BigDecimal("100.00");
BigDecimal largeOrder = new BigDecimal("200.00");
LocalDate startDate = LocalDate.of(2026, 10, 1);

Predicate<Order> paid = o -> "PAID".equals(o.status());
Predicate<Order> atLeast100 = o -> o.total().compareTo(minimum) >= 0;
Predicate<Order> fromStartDate = o -> !o.createdAt().isBefore(startDate);
Predicate<Order> priority = Order::priority;
Predicate<Order> atLeast200 = o -> o.total().compareTo(largeOrder) >= 0;

Predicate<Order> eligible = paid
        .and(atLeast100)
        .and(fromStartDate)
        .and(priority.or(atLeast200));

List<String> ids = orders.stream()
        .filter(eligible)
        .map(Order::id)
        .toList();

// [DH-01, DH-04, DH-06]
```

Đoạn trên sử dụng `record Order` và biến `orders` đã khai báo trong ví dụ hoàn chỉnh ở mục 3. `Predicate` cung cấp ba phương thức quan trọng:

| Phương thức | Nghĩa | Tương đương khi kiểm tra một phần tử `x` |
| --- | --- | --- |
| `p.and(q)` | Kết hợp hai điều kiện bằng AND | `p.test(x) && q.test(x)` |
| `p.or(q)` | Kết hợp hai điều kiện bằng OR | `p.test(x) || q.test(x)` |
| `p.negate()` | Đảo kết quả điều kiện | `!p.test(x)` |

Giống `&&` và `||`, hai phương thức `and` và `or` được xác định để đánh giá điều kiện thứ hai **khi cần thiết**. `Predicate` cũng hỗ trợ method reference, ví dụ `Order::priority`, khi phương thức trả về `boolean`.

**Một lỗi kết hợp điều kiện phổ biến:**

```java
// Sai nếu chính sách yêu cầu mọi đơn đều đã thanh toán:
Predicate<Order> incorrect = paid.and(atLeast100).or(priority);

// Đúng: nhóm điều kiện OR phải nằm bên trong điều kiện AND:
Predicate<Order> correct = paid.and(atLeast100).and(priority.or(atLeast200));
```

Biểu thức `incorrect` chấp nhận đơn `PENDING` nếu `priority` đúng. Khi dùng chuỗi `.and(...).or(...)`, luôn kiểm tra cách nhóm tương đương với dấu ngoặc trong biểu thức logic; nếu cần, đặt tên cho từng nhóm `Predicate` trước khi kết hợp.

### Phủ định với `negate` và `Predicate.not`

```java
Predicate<Order> cancelled = o -> "CANCELLED".equals(o.status());
Predicate<Order> notCancelled = cancelled.negate();

List<Order> activeOrders = orders.stream()
        .filter(notCancelled)
        .toList();
```

Với Java 11+, `Predicate.not(...)` thuận tiện khi muốn phủ định một method reference ngay tại chỗ:

```java
List<String> nonBlank = List.of("Java", "  ", "Stream").stream()
        .filter(Predicate.not(String::isBlank))
        .toList();

// [Java, Stream]
```

Để chạy từng đoạn riêng biệt, khai báo/import kiểu và dữ liệu được nhắc tới; chương trình đầy đủ ở mục 3 không phụ thuộc các đoạn mở rộng này.

## 5. Kiểm tra `null`, chuỗi và dữ liệu thiếu

`filter` chỉ giữ hoặc loại phần tử theo predicate mà bạn viết; nó **không tự ngăn `NullPointerException`**. Hãy loại `null` trước những phép gọi phương thức, hoặc viết điều kiện có kiểm tra `null` ở vế trái của `&&`.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.function.Predicate;

List<String> raw = Arrays.asList(" java ", null, " ", "Stream", " api ");

List<String> cleaned = raw.stream()
        .filter(Objects::nonNull)
        .map(String::trim)
        .filter(Predicate.not(String::isBlank))
        .filter(s -> s.length() >= 3)
        .map(String::toLowerCase)
        .toList();

System.out.println(cleaned); // [java, stream, api]
```

Ở đây, `Objects::nonNull` loại giá trị `null` trước khi gọi `trim`; `Predicate.not(String::isBlank)` bỏ chuỗi rỗng hoặc toàn khoảng trắng; điều kiện độ dài được áp dụng **sau** khi đã chuẩn hóa khoảng trắng. `Arrays.asList` được dùng vì dữ liệu ví dụ có `null`; `List.of(...)` không chấp nhận phần tử `null`.

Lọc chuỗi không phân biệt chữ hoa/chữ thường có thể dùng `equalsIgnoreCase`:

```java
String requestedStatus = "paid";

List<Order> paidOrders = orders.stream()
        .filter(o -> requestedStatus.equalsIgnoreCase(o.status()))
        .toList();
```

Nếu input có thể là `null`, hãy xác định rõ chính sách xử lý: bỏ qua bộ lọc, loại phần tử thiếu dữ liệu, hay báo lỗi cho người gọi. Không thể mặc định cả ba cách là tương đương về nghiệp vụ.

## 6. Bộ lọc động theo tiêu chí tìm kiếm

Một màn hình tìm kiếm thường cho phép để trống trạng thái hoặc ngưỡng tiền. Trong trường hợp đó, ta có thể **xây dựng `Predicate` từng bước** thay vì tạo nhiều nhánh `if/else` bên trong pipeline:

```java
import java.math.BigDecimal;
import java.util.function.Predicate;

static Predicate<Order> buildOrderFilter(
        String requestedStatus,
        BigDecimal minTotal
) {
    Predicate<Order> result = o -> true;

    if (requestedStatus != null && !requestedStatus.isBlank()) {
        result = result.and(o -> requestedStatus.equals(o.status()));
    }

    if (minTotal != null) {
        result = result.and(o -> o.total() != null
                && o.total().compareTo(minTotal) >= 0);
    }

    return result;
}

// Gọi trong một lớp có định nghĩa record Order:
Predicate<Order> search = buildOrderFilter("PAID", new BigDecimal("150"));
List<Order> matchingOrders = orders.stream().filter(search).toList();
```

`o -> true` là điều kiện ban đầu cho phép mọi phần tử đi qua. Mỗi tiêu chí được cung cấp sẽ được nối thêm bằng `.and(...)`. Nếu không có tiêu chí nào, mọi phần tử của nguồn được giữ lại.

Các đoạn mã ở mục 4 và 6 là phần mở rộng dựa trên `Order` trong ví dụ chính. Trong ứng dụng thực tế, hãy tổ chức hàm tạo predicate trong lớp chứa kiểu dữ liệu tương ứng; tránh để tiêu chí có thể thay đổi trong lúc Stream đang chạy.

## 7. `filter`, `map` và thứ tự các bước trong pipeline

Thông thường, nếu chỉ cần biến đổi các phần tử **đạt điều kiện**, hãy lọc trước khi thực hiện phép biến đổi tốn chi phí, miễn là điều kiện lọc vẫn được đánh giá trên đúng loại dữ liệu:

```java
List<String> names = orders.stream()
        .filter(o -> "PAID".equals(o.status()))
        .map(Order::customer)
        .toList();
```

Nếu biến đổi trước, điều kiện sau đó phải xét trên kiểu dữ liệu **đã biến đổi**:

```java
List<String> namesStartingWithA = orders.stream()
        .map(Order::customer)                 // Stream<String>
        .filter(name -> name.startsWith("A")) // Predicate<String>
        .toList();
```

Đừng tùy tiện đảo `filter` và `map`. Chẳng hạn, `filter(o -> o.total() >= ...)` cần đối tượng `Order`; nếu `.map(Order::customer)` chạy trước, dữ liệu đã thành `String` và không còn thông tin tổng tiền để kiểm tra.

**Một điểm tinh tế về tính lazy:** hai bước `filter` liên tiếp về mặt logic có thể viết thành một bước với `&&`:

```java
.filter(o -> "PAID".equals(o.status()))
.filter(o -> o.total().compareTo(new BigDecimal("100")) >= 0)

// Tương đương khi các predicate thuần, độc lập và không có side effect:
.filter(o -> "PAID".equals(o.status())
        && o.total().compareTo(new BigDecimal("100")) >= 0)
```

Sự tương đương này dựa trên **hành vi trả kết quả**, không phải cam kết tuyệt đối về số lần callback được gọi trong mọi tối ưu của Stream. Các lambda nên không phụ thuộc trạng thái thay đổi bên ngoài và không sửa nguồn dữ liệu trong khi duyệt.

## 8. `filter` khác `takeWhile` và các phép kiểm tra tồn tại

`filter` xét riêng từng phần tử; `takeWhile` (Java 9+) lấy **đoạn đầu liên tiếp** thỏa điều kiện trên Stream có thứ tự. Chúng không thể thay thế nhau:

```java
List<Integer> values = List.of(2, 4, 1, 6, 8);

System.out.println(values.stream()
        .filter(n -> n % 2 == 0).toList());
// [2, 4, 6, 8]

System.out.println(values.stream()
        .takeWhile(n -> n % 2 == 0).toList());
// [2, 4]
```

Ngoài ra, nếu mục tiêu chỉ là **trả lời có/không** thay vì tạo danh sách, dùng terminal operation phù hợp:

| Mục tiêu | Cách viết | Kết quả |
| --- | --- | --- |
| Lấy mọi phần tử phù hợp | `stream.filter(p).toList()` | `List<T>` |
| Có ít nhất một phần tử phù hợp? | `stream.anyMatch(p)` | `boolean` |
| Tất cả phần tử đều phù hợp? | `stream.allMatch(p)` | `boolean` |
| Không phần tử nào phù hợp? | `stream.noneMatch(p)` | `boolean` |
| Lấy phần tử phù hợp đầu tiên theo encounter order | `stream.filter(p).findFirst()` | `Optional<T>` |
| Đếm các phần tử phù hợp | `stream.filter(p).count()` | `long` |

Ví dụ:

```java
boolean hasExpensivePaidOrder = orders.stream()
        .anyMatch(o -> "PAID".equals(o.status())
                && o.total().compareTo(new BigDecimal("200")) >= 0);

// true: có DH-04.
```

`anyMatch`, `allMatch`, `noneMatch` có thể dừng khi đã đủ thông tin xác định kết quả. Trên Stream rỗng, `anyMatch` là `false`, còn `allMatch` và `noneMatch` là `true` theo định nghĩa toán học (*vacuous truth*).

## 9. Lazy evaluation, dừng sớm và hiệu năng

`filter` là phép toán trung gian lazy. Ví dụ sau chỉ cần tìm hai số chẵn đầu tiên:

```java
List<Integer> firstTwo = List.of(1, 2, 3, 4, 5, 6).stream()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .toList();

// [2, 4]
```

Với pipeline tuần tự có thứ tự, khi tìm được `2` và `4`, `limit(2)` đã đủ kết quả nên thường không cần duyệt tới `5`, `6`. `filter` không yêu cầu lưu toàn bộ phần tử nguồn; nó chỉ quyết định giữ hay bỏ từng phần tử. Trong ví dụ trên, **`limit`** là bước giới hạn số lượng và tạo khả năng dừng sớm cho toàn pipeline.

Một vài quy tắc khi tối ưu:

- Đặt bộ lọc ít tốn chi phí hoặc có khả năng loại nhiều phần tử trước các bước xử lý nặng, **nếu** thứ tự đánh giá đó giữ nguyên ngữ nghĩa.
- Trên dữ liệu rất lớn, cân nhắc lọc trước các bước có trạng thái như `sorted()` hoặc `distinct()` nếu điều kiện lọc không phụ thuộc kết quả của các bước đó; nếu thứ tự bước ảnh hưởng kết quả, phải ưu tiên tính đúng đắn.
- `filter` tương đối phù hợp với Stream song song vì là phép toán không trạng thái, nhưng `parallelStream()` **không mặc nhiên nhanh hơn**. Kích thước dữ liệu, chi phí từng predicate, đặc tính nguồn và chi phí phân chia/gộp đều quan trọng.
- Với Stream có thứ tự như `List`, `filter(...).toList()` bảo toàn thứ tự các phần tử được giữ. Tuy nhiên, không nên dựa vào thứ tự **thực thi lambda** khi dùng Stream song song hoặc khi tối ưu có thể bỏ qua một bước.

Đừng sử dụng `peek`, phép tăng bộ đếm, ghi log hay cập nhật đối tượng bên ngoài như cơ chế bắt buộc để tính kết quả của một pipeline: một số callback có thể không được thực thi do tối ưu, còn pipeline song song có thể thực hiện callback trong các luồng khác nhau.

## 10. Những lỗi thường gặp

| Lỗi | Vì sao sai hoặc khó bảo trì? | Cách xử lý |
| --- | --- | --- |
| `status == "PAID"` | `==` so sánh tham chiếu của `String`. | Dùng `"PAID".equals(status)` hoặc so sánh enum phù hợp. |
| `name.isBlank()` khi `name` có thể `null` | Có thể gây `NullPointerException`. | Kiểm tra `name != null` trước hoặc `.filter(Objects::nonNull)`. |
| `a && b || c` khi yêu cầu `a && (b || c)` | OR có thể cho phép phần tử vi phạm điều kiện bắt buộc. | Nhóm điều kiện bằng ngoặc hoặc `Predicate` rõ tên. |
| Dùng `BigDecimal.equals` để lọc tiền theo ngưỡng | `equals` xét cả scale; không biểu diễn quan hệ lớn hơn/nhỏ hơn. | Dùng `compareTo`. |
| Dùng `filter(...).count() > 0` chỉ để kiểm tra tồn tại | Có thể phải đếm toàn bộ phần tử phù hợp. | Dùng `anyMatch(...)`. |
| Ghi vào danh sách ngoài trong `filter` | Tạo side effect, khó đoán khi lazy hoặc parallel. | Dùng `filter(...).toList()` hoặc `collect(...)`. |
| Dùng `filter` khi cần giữ tiền tố liên tiếp | `filter` vẫn tiếp tục kiểm tra phần tử sau vị trí không thỏa. | Xem `takeWhile` khi đúng ngữ nghĩa. |

Ví dụ **không nên dùng** trạng thái biến đổi bên ngoài để chọn phần tử:

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger position = new AtomicInteger();
List<Integer> unstable = numbers.parallelStream()
        .filter(n -> position.getAndIncrement() % 2 == 0)
        .toList();
```

Việc chọn phần tử ở đây phụ thuộc **thứ tự các luồng chạy predicate**, không nhất thiết là chỉ số ban đầu. `AtomicInteger` bảo đảm cập nhật nguyên tử nhưng không biến phép lọc này thành phép chọn theo vị trí ổn định. Nếu thực sự cần chỉ số, hãy diễn đạt theo `IntStream.range(0, list.size())` trên danh sách có truy cập chỉ số hiệu quả.

## 11. Tự luyện tập và kiểm tra hiểu bài

**Bài 1 — Khoảng giá trị và tính chẵn.** Cho `List.of(-2, 0, 3, 4, 9, 12)`. Giữ các số chẵn, lớn hơn `0` và không vượt quá `10`.

```java
List<Integer> answer = List.of(-2, 0, 3, 4, 9, 12).stream()
        .filter(n -> n > 0 && n <= 10 && n % 2 == 0)
        .toList();
// [4]
```

**Bài 2 — Kết hợp điều kiện OR trong một nhóm.** Chọn đơn đã thanh toán, đồng thời là đơn ưu tiên **hoặc** có tổng tiền ít nhất 200. Biểu thức phù hợp:

```java
Predicate<Order> rule = paid.and(priority.or(atLeast200));
```

**Bài 3 — Nhận biết short-circuit.** Điều gì xảy ra với `"abc".equals(s) || s.length() >= 5` khi `s` là `null`?

**Đáp án:** Vế trái trả `false`; Java tiếp tục đánh giá `s.length()` và ném `NullPointerException`. Hãy viết `s != null && ("abc".equals(s) || s.length() >= 5)` nếu muốn loại `null` an toàn.

**Bài 4 — Chọn terminal operation.** Muốn biết có đơn `PAID` giá trên 500 hay không, có cần `.filter(...).toList()` không?

**Đáp án:** Không cần tạo danh sách nếu chỉ muốn boolean. Dùng `orders.stream().anyMatch(o -> "PAID".equals(o.status()) && o.total().compareTo(new BigDecimal("500")) > 0)`.

## Ghi nhớ

- `filter(Predicate<T>)` **giữ phần tử khi điều kiện là `true`**, không sửa nguồn, giữ thứ tự tương đối trên Stream có thứ tự và hoạt động lazy.
- Kết hợp điều kiện bằng `&&`, `||`, `!`, và **dùng ngoặc** để thể hiện đúng luật nghiệp vụ; các toán tử `&&`/`||` short-circuit cho từng phần tử.
- Khi điều kiện dài, dùng `Predicate.and`, `or`, `negate` và đặt tên cho các quy tắc để giảm lỗi ưu tiên logic.
- Lọc dữ liệu thực tế cần xử lý rõ `null`, so sánh chuỗi bằng `equals`, so sánh `BigDecimal` bằng `compareTo` và tránh lambda có side effect.
- Chọn `anyMatch`, `allMatch`, `noneMatch`, `findFirst` hoặc `count` tùy loại kết quả cần nhận; sắp xếp thứ tự các bước theo **tính đúng đắn trước, hiệu năng sau**.
