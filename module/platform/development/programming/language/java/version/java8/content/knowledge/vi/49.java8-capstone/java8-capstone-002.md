# Tổng hợp dữ liệu đơn hàng bằng Stream, collector và Comparator

**Chủ đề:** Java 8 → Thực hành → Tổng hợp dữ liệu đơn hàng bằng Stream, collector và Comparator.

Trong ứng dụng bán hàng, dữ liệu đơn hàng thường cần được lọc theo trạng thái, tính doanh thu, nhóm theo khách hàng/khu vực/sản phẩm, thống kê số lượng, tìm đơn hàng lớn nhất và xếp hạng theo nhiều tiêu chí. Java 8 cung cấp một bộ API phù hợp cho công việc này:

- **Stream** mô tả pipeline xử lý dữ liệu theo các bước `filter`, `map`, `flatMap`, `sorted` và các thao tác kết thúc.
- **Collector** mô tả cách tích lũy dữ liệu thành danh sách, bản đồ, số liệu tổng hợp hoặc kết quả tùy chỉnh.
- **Comparator** định nghĩa thứ tự so sánh, kể cả khi cần nhiều tiêu chí như doanh thu giảm dần rồi mã đơn tăng dần.

Bài thực hành xây dựng một bộ dữ liệu đơn hàng có dòng sản phẩm, trạng thái và ngày tạo. Từ cùng một nguồn, chương trình tạo nhiều báo cáo: tổng doanh thu đã thanh toán, doanh thu theo khách hàng, doanh thu/số lượng theo SKU, phân bố trạng thái, số đơn theo khu vực và top 3 đơn hàng.

**Các API chính được dùng đều có từ Java 8 và vẫn còn hiện hành.** Chương trình hoàn chỉnh tương thích Java 8; phần giải thích cuối bài phân biệt một số tiện ích Stream/Collectors được bổ sung ở Java 9, 10, 12 và 16 để bạn không vô tình đưa API mới hơn vào source target Java 8.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xây dựng pipeline Stream từ một danh sách đơn hàng.
2. Dùng `filter`, `map`, `flatMap`, `sorted`, `limit` và `collect`.
3. Phân biệt `map` với `flatMap` khi một đơn hàng chứa nhiều dòng sản phẩm.
4. Hiểu vai trò của `Collector`, downstream collector và mutable reduction.
5. Dùng `groupingBy` để nhóm theo khách hàng, trạng thái, khu vực và sản phẩm.
6. Dùng `partitioningBy` để chia dữ liệu thành hai nhóm đúng/sai.
7. Dùng `counting`, `summingInt`, `mapping`, `reducing`, `maxBy`, `minBy` và `collectingAndThen`.
8. Dùng `toMap` có merge function khi khóa bị trùng.
9. Tổng hợp tiền bằng `BigDecimal` thay vì `double`.
10. Xây dựng `Comparator` theo một hoặc nhiều khóa.
11. Sắp xếp doanh thu giảm dần và dùng mã đơn làm tiêu chí phụ ổn định.
12. Xử lý `Optional` khi truy vấn min/max trên tập dữ liệu có thể rỗng.
13. Chủ động chọn `TreeMap` hoặc `EnumMap` khi cần thứ tự kết quả dễ kiểm tra.
14. Tránh side effect, stream reuse và lỗi khi chạy parallel.
15. Thiết kế test cho dữ liệu rỗng, khóa trùng, giá trị null, tiền tệ và tie-breaker.

## 2. Bài toán và quy tắc nghiệp vụ

Ta có một tập đơn hàng. Mỗi đơn gồm:

- Mã đơn hàng.
- Khách hàng.
- Khu vực.
- Trạng thái: `PAID`, `PENDING` hoặc `CANCELLED`.
- Ngày đặt.
- Một hoặc nhiều dòng sản phẩm.

Mỗi dòng sản phẩm có SKU, số lượng và đơn giá. Thành tiền dòng được tính:

~~~text
lineTotal = unitPrice × quantity
~~~

Tổng tiền đơn hàng:

~~~text
orderTotal = sum(lineTotal của tất cả dòng trong đơn)
~~~

Trong bài này, quy tắc doanh thu là:

- Chỉ đơn có trạng thái `PAID` được tính vào doanh thu.
- `PENDING` và `CANCELLED` vẫn được tính vào báo cáo số lượng đơn/trạng thái, nhưng không được tính doanh thu đã thanh toán.
- Không cộng tiền của các đơn khác tiền tệ. Dataset chỉ dùng một đơn vị tiền để ví dụ tập trung vào Stream.
- Đơn giá được nhập bằng chuỗi thập phân để tạo `BigDecimal` chính xác.
- Số lượng dòng phải lớn hơn 0; đơn hàng phải có ít nhất một dòng.

Đây là quy tắc của ví dụ. Hệ thống thực tế cần xác định riêng cách xử lý hoàn tiền, đơn trả một phần, thuế, phí giao hàng, chiết khấu, tiền tệ và thời điểm ghi nhận doanh thu.

### 2.1. Dữ liệu đầu vào

| Mã đơn | Khách hàng | Khu vực | Trạng thái | Ngày | Các dòng sản phẩm | Tổng |
|---|---|---|---|---|---|---:|
| O-100 | Alice | North | PAID | 2025-03-02 | Keyboard 1 × 80.00; Mouse 1 × 40.50 | 120.50 |
| O-101 | Bob | South | PAID | 2025-03-02 | Monitor 1 × 75.00 | 75.00 |
| O-102 | Alice | North | CANCELLED | 2025-03-03 | Mouse 1 × 40.00 | 40.00 |
| O-103 | Carol | North | PAID | 2025-03-04 | Keyboard 1 × 120.50 | 120.50 |
| O-104 | Bob | South | PAID | 2025-03-05 | Monitor 2 × 100.00 | 200.00 |
| O-105 | Alice | North | PAID | 2025-03-06 | Mouse 2 × 40.00 | 80.00 |
| O-106 | Carol | North | PENDING | 2025-03-07 | Mouse 1 × 30.00 | 30.00 |

Kết quả cần tìm:

- Có 7 đơn hàng, trong đó 5 đơn đã thanh toán.
- Doanh thu đã thanh toán là `596.00`.
- Doanh thu theo khách hàng: Alice `200.50`, Bob `275.00`, Carol `120.50`.
- Doanh thu theo SKU: Keyboard `200.50`, Monitor `275.00`, Mouse `120.50`.
- Top 3 đơn đã thanh toán: O-104, O-100, O-103.
- Số đơn theo khu vực: North 5, South 2.

## 3. Stream pipeline: nguồn, bước trung gian và thao tác kết thúc

Một pipeline Stream có ba phần:

~~~text
Source
  |
  v
Intermediate operations
  filter -> map -> flatMap -> sorted -> limit
  |
  v
Terminal operation
  collect / count / reduce / max / min
  |
  v
Result
~~~

Ví dụ:

~~~java
List<Order> paid = orders.stream()
        .filter(Order::isPaid)
        .collect(Collectors.toList());
~~~

- `orders.stream()` tạo Stream từ danh sách.
- `filter` giữ lại đơn có trạng thái `PAID`.
- `collect` là terminal operation, thực thi pipeline và thu kết quả thành List.

### 3.1. Intermediate operations là lazy

Các bước `filter`, `map`, `flatMap`, `sorted` không tự tiêu thụ dữ liệu ngay khi được gọi. Chúng mô tả pipeline; terminal operation mới kích hoạt việc xử lý.

~~~java
Stream<Order> stream = orders.stream()
        .filter(Order::isPaid);

// Chưa có List kết quả tại thời điểm khai báo stream.
List<Order> paid = stream.collect(Collectors.toList());
~~~

**Stream không phải Collection.** Stream không cung cấp cách truy cập phần tử tùy ý hay thêm/xóa phần tử. Nó mô tả phép xử lý tổng hợp trên nguồn dữ liệu.

### 3.2. Một Stream chỉ nên được dùng một lần

Không dùng cùng một Stream cho hai terminal operations:

~~~java
Stream<Order> stream = orders.stream();

long count = stream.count();

// Sai: stream đã được tiêu thụ.
List<Order> list = stream.collect(Collectors.toList());
~~~

Nếu cần hai kết quả, tạo hai pipeline từ collection nguồn:

~~~java
long count = orders.stream().count();

List<Order> list = orders.stream()
        .filter(Order::isPaid)
        .collect(Collectors.toList());
~~~

### 3.3. Không thay đổi nguồn trong lúc pipeline đang xử lý

Các hàm truyền vào Stream nên không can thiệp vào nguồn và thường nên stateless. Tránh thêm/xóa phần tử của `orders` trong `filter`, `map` hoặc `forEach` của chính pipeline đó.

Không dùng side effect để thay thế collector:

~~~java
// Không nên: sửa một Map bên ngoài trong forEach.
Map<String, BigDecimal> totals = new HashMap<>();

orders.stream().forEach(order ->
        totals.merge(order.getCustomer(),
                order.getTotal(), BigDecimal::add));
~~~

Hãy dùng `groupingBy` hoặc `toMap` để Stream quản lý việc tích lũy, đặc biệt khi có thể chạy parallel.

## 4. Collector là gì?

`Collector<T, A, R>` mô tả cách biến các phần tử đầu vào kiểu `T` thành kết quả `R`, thông qua một container tích lũy trung gian `A`.

Một Collector có các thành phần:

| Thành phần | Vai trò |
|---|---|
| `supplier` | Tạo container tích lũy mới |
| `accumulator` | Thêm một phần tử vào container |
| `combiner` | Gộp hai container trung gian |
| `finisher` | Chuyển container trung gian thành kết quả cuối |
| `characteristics` | Mô tả đặc tính như `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH` |

Ví dụ `Collectors.toList()` tích lũy phần tử thành một List; `Collectors.groupingBy()` tạo nhóm theo khóa; `Collectors.counting()` đếm số phần tử; `Collectors.reducing()` gộp giá trị bằng một phép toán.

### 4.1. Các collector thường gặp

| Collector | Kết quả |
|---|---|
| `toList()` | List các phần tử |
| `toSet()` | Set các phần tử |
| `toCollection(...)` | Collection do ứng dụng chọn |
| `toMap(...)` | Map theo khóa và giá trị |
| `groupingBy(...)` | Nhóm theo classifier |
| `partitioningBy(...)` | Chia thành nhóm true/false |
| `counting()` | Số lượng phần tử |
| `summingInt(...)` | Tổng giá trị int |
| `summingLong(...)` | Tổng giá trị long |
| `mapping(...)` | Ánh xạ rồi dùng downstream collector |
| `reducing(...)` | Gộp các giá trị bằng BinaryOperator |
| `maxBy(...)`, `minBy(...)` | Phần tử lớn nhất/nhỏ nhất theo Comparator |
| `collectingAndThen(...)` | Chạy finisher sau collector khác |
| `joining(...)` | Ghép chuỗi |

Các collector chuẩn nêu trên là API Java 8, ngoại trừ những method có mốc phiên bản riêng được ghi ở phần cuối.

### 4.2. Downstream collector

Một collector có thể nhận một collector khác làm bước tích lũy bên trong. Ví dụ:

~~~java
Map<String, Long> countByCustomer = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getCustomer,
                Collectors.counting()));
~~~

`groupingBy` quyết định khóa nhóm; `counting` đếm các đơn thuộc mỗi khóa.

Đây là cách tổ chức báo cáo rất phổ biến: **collector ngoài xác định nhóm, collector trong xác định kết quả của từng nhóm**.

## 5. Comparator: xây dựng thứ tự sắp xếp

`Comparator<T>` định nghĩa cách so sánh hai đối tượng. Nó được dùng với `Stream.sorted`, `List.sort`, `Collections.sort`, `min`, `max` và các cấu trúc dữ liệu có thứ tự.

### 5.1. So sánh theo một khóa

~~~java
Comparator<Order> byDate =
        Comparator.comparing(Order::getOrderDate);

Comparator<Order> byAmount =
        Comparator.comparing(Order::getTotal);
~~~

`Comparator.comparing` nhận một hàm lấy khóa so sánh. Khóa phải có thứ tự tự nhiên hoặc có Comparator được cung cấp.

### 5.2. So sánh số nguyên bằng comparingInt

~~~java
Comparator<OrderLine> byQuantity =
        Comparator.comparingInt(OrderLine::getQuantity);
~~~

Dùng `comparingInt`, `comparingLong` hoặc `comparingDouble` cho primitive key. Không tự trừ hai số để tạo Comparator:

~~~java
// Không nên: phép trừ có thể overflow.
Comparator<Order> wrong =
        (a, b) -> (int) (a.getTotal().doubleValue()
                - b.getTotal().doubleValue());
~~~

Đối với số tiền, dùng `BigDecimal.compareTo` thông qua `Comparator.comparing(Order::getTotal)`.

### 5.3. Sắp xếp theo nhiều tiêu chí

Ví dụ yêu cầu:

1. Tổng tiền giảm dần.
2. Nếu tổng tiền bằng nhau, mã đơn tăng dần.

~~~java
Comparator<Order> topOrder =
        Comparator.comparing(Order::getTotal)
                .reversed()
                .thenComparing(Order::getId);
~~~

Ý nghĩa:

- `comparing(Order::getTotal)` tạo thứ tự tổng tiền tăng dần.
- `reversed()` đảo tiêu chí tổng tiền thành giảm dần.
- `thenComparing(Order::getId)` thêm tiêu chí phụ tăng dần khi tổng tiền bằng nhau.

**Vị trí gọi `reversed()` rất quan trọng.** Nếu gọi sau khi ghép tiêu chí phụ, cả thứ tự chính lẫn phụ đều bị đảo:

~~~java
// Cả total và id đều giảm dần.
Comparator<Order> descendingBoth =
        Comparator.comparing(Order::getTotal)
                .thenComparing(Order::getId)
                .reversed();
~~~

Nếu yêu cầu tổng tiền giảm dần nhưng ID tăng dần, dùng cách đầu tiên.

### 5.4. Xử lý null trong khóa so sánh

Nếu một thuộc tính có thể null, hãy chọn chính sách rõ ràng:

~~~java
Comparator<String> names =
        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER);
~~~

`nullsLast` xếp null sau các giá trị khác; `nullsFirst` xếp null trước. Không để Comparator vô tình ném NullPointerException khi dữ liệu nullable mà nghiệp vụ cần một thứ tự xác định.

### 5.5. Comparator và equals

Comparator có thể coi hai đối tượng là bằng nhau theo thứ tự (`compare(a,b)==0`) dù `a.equals(b)` là false. Điều này đặc biệt quan trọng với `TreeSet` và `TreeMap`: hai phần tử/khóa được Comparator coi là bằng nhau có thể được xem như cùng một vị trí.

Nếu cần xếp hạng đơn hàng duy nhất, thêm mã đơn làm tie-breaker để phân biệt các đơn có cùng tổng tiền.

### 5.6. Stream.sorted và List.sort

- `stream.sorted(comparator)` tạo một Stream có thứ tự sắp xếp; collection nguồn không bị thay đổi.
- `list.sort(comparator)` sắp xếp trực tiếp List.
- Với Stream có encounter order, `sorted` là stable sort: phần tử có khóa bằng nhau giữ thứ tự tương đối ban đầu.
- Nếu cần thứ tự kết quả rõ ràng giữa các lần chạy, hãy xây Comparator đủ tiêu chí thay vì dựa vào thứ tự tình cờ của nguồn Map.

## 6. Chương trình hoàn chỉnh: OrderAnalyticsDemo.java

Chương trình dưới đây tương thích **Java 8**. Nó dùng class thông thường thay cho record, `Arrays.asList` thay cho `List.of`, và `Collectors.toList()` thay cho `Stream.toList()` để có thể chạy với Java 8.

Lưu thành **`OrderAnalyticsDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class OrderAnalyticsDemo {
    enum Status {
        PAID, PENDING, CANCELLED
    }

    static final class OrderLine {
        private final String sku;
        private final int quantity;
        private final BigDecimal unitPrice;

        OrderLine(String sku, int quantity, String unitPrice) {
            this.sku = Objects.requireNonNull(sku);

            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }

            this.quantity = quantity;
            this.unitPrice = new BigDecimal(unitPrice);

            if (this.unitPrice.signum() < 0) {
                throw new IllegalArgumentException(
                        "unitPrice must not be negative");
            }
        }

        String getSku() {
            return sku;
        }

        int getQuantity() {
            return quantity;
        }

        BigDecimal getLineTotal() {
            return unitPrice.multiply(
                    BigDecimal.valueOf(quantity));
        }
    }

    static final class Order {
        private final String id;
        private final String customer;
        private final String region;
        private final Status status;
        private final LocalDate orderDate;
        private final List<OrderLine> lines;
        private final BigDecimal total;

        Order(String id, String customer, String region,
              Status status, LocalDate orderDate,
              OrderLine... lines) {

            this.id = Objects.requireNonNull(id);
            this.customer = Objects.requireNonNull(customer);
            this.region = Objects.requireNonNull(region);
            this.status = Objects.requireNonNull(status);
            this.orderDate = Objects.requireNonNull(orderDate);

            if (lines == null || lines.length == 0) {
                throw new IllegalArgumentException(
                        "order must contain at least one line");
            }

            this.lines = Collections.unmodifiableList(
                    new ArrayList<>(Arrays.asList(lines)));

            this.total = this.lines.stream()
                    .map(OrderLine::getLineTotal)
                    .reduce(BigDecimal.ZERO, BigDecimal::add);
        }

        String getId() {
            return id;
        }

        String getCustomer() {
            return customer;
        }

        String getRegion() {
            return region;
        }

        Status getStatus() {
            return status;
        }

        LocalDate getOrderDate() {
            return orderDate;
        }

        List<OrderLine> getLines() {
            return lines;
        }

        BigDecimal getTotal() {
            return total;
        }

        boolean isPaid() {
            return status == Status.PAID;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
            new Order("O-100", "Alice", "North", Status.PAID,
                LocalDate.of(2025, 3, 2),
                new OrderLine("Keyboard", 1, "80.00"),
                new OrderLine("Mouse", 1, "40.50")),

            new Order("O-101", "Bob", "South", Status.PAID,
                LocalDate.of(2025, 3, 2),
                new OrderLine("Monitor", 1, "75.00")),

            new Order("O-102", "Alice", "North", Status.CANCELLED,
                LocalDate.of(2025, 3, 3),
                new OrderLine("Mouse", 1, "40.00")),

            new Order("O-103", "Carol", "North", Status.PAID,
                LocalDate.of(2025, 3, 4),
                new OrderLine("Keyboard", 1, "120.50")),

            new Order("O-104", "Bob", "South", Status.PAID,
                LocalDate.of(2025, 3, 5),
                new OrderLine("Monitor", 2, "100.00")),

            new Order("O-105", "Alice", "North", Status.PAID,
                LocalDate.of(2025, 3, 6),
                new OrderLine("Mouse", 2, "40.00")),

            new Order("O-106", "Carol", "North", Status.PENDING,
                LocalDate.of(2025, 3, 7),
                new OrderLine("Mouse", 1, "30.00"))
        );

        // 1. Lọc các đơn đã thanh toán.
        List<Order> paid = orders.stream()
                .filter(Order::isPaid)
                .collect(Collectors.toList());

        // 2. Tổng doanh thu đã thanh toán bằng BigDecimal.
        BigDecimal paidRevenue = paid.stream()
                .map(Order::getTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        // 3. Đếm số đơn theo trạng thái.
        Map<Status, Long> countsByStatus = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::getStatus,
                        () -> new EnumMap<>(Status.class),
                        Collectors.counting()));

        // 4. Tổng doanh thu theo khách hàng.
        Map<String, BigDecimal> revenueByCustomer = paid.stream()
                .collect(Collectors.groupingBy(
                        Order::getCustomer,
                        TreeMap::new,
                        Collectors.reducing(
                                BigDecimal.ZERO,
                                Order::getTotal,
                                BigDecimal::add)));

        // 5. Chia đơn đã thanh toán và các đơn còn lại.
        Map<Boolean, BigDecimal> paidSplit = orders.stream()
                .collect(Collectors.partitioningBy(
                        Order::isPaid,
                        Collectors.reducing(
                                BigDecimal.ZERO,
                                Order::getTotal,
                                BigDecimal::add)));

        // 6. Làm phẳng các dòng sản phẩm và tính doanh thu theo SKU.
        Map<String, BigDecimal> revenueBySku = paid.stream()
                .flatMap(order -> order.getLines().stream())
                .collect(Collectors.groupingBy(
                        OrderLine::getSku,
                        TreeMap::new,
                        Collectors.reducing(
                                BigDecimal.ZERO,
                                OrderLine::getLineTotal,
                                BigDecimal::add)));

        // 7. Tính số lượng sản phẩm đã bán theo SKU.
        Map<String, Integer> quantityBySku = paid.stream()
                .flatMap(order -> order.getLines().stream())
                .collect(Collectors.groupingBy(
                        OrderLine::getSku,
                        TreeMap::new,
                        Collectors.summingInt(
                                OrderLine::getQuantity)));

        // 8. Xếp hạng tổng tiền giảm dần, mã đơn tăng dần.
        Comparator<Order> topOrder =
                Comparator.comparing(Order::getTotal)
                        .reversed()
                        .thenComparing(Order::getId);

        List<Order> topThree = paid.stream()
                .sorted(topOrder)
                .limit(3)
                .collect(Collectors.toList());

        String topIds = topThree.stream()
                .map(Order::getId)
                .collect(Collectors.joining(","));

        // 9. Cùng một báo cáo khách hàng bằng toMap + merge.
        Map<String, BigDecimal> revenueByCustomerWithMerge =
                paid.stream().collect(Collectors.toMap(
                        Order::getCustomer,
                        Order::getTotal,
                        BigDecimal::add,
                        TreeMap::new));

        // 10. Giá trị trung bình; dữ liệu mẫu có ít nhất một đơn PAID.
        BigDecimal averagePaid = paidRevenue.divide(
                BigDecimal.valueOf(paid.size()),
                2,
                RoundingMode.HALF_UP);

        // 11. Tìm đơn thanh toán có tổng tiền lớn nhất.
        Optional<Order> mostExpensive = paid.stream()
                .max(Comparator.comparing(Order::getTotal)
                        .thenComparing(Order::getId));

        // 12. Đếm đơn theo khu vực.
        Map<String, Long> countByRegion = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::getRegion,
                        TreeMap::new,
                        Collectors.counting()));

        System.out.println("orderCount=" + orders.size());
        System.out.println("paidCount=" + paid.size());
        System.out.println("paidRevenue=" + paidRevenue);
        System.out.println("countsByStatus=" + countsByStatus);
        System.out.println("revenueByCustomer=" + revenueByCustomer);
        System.out.println("paidVsOther=" + paidSplit);
        System.out.println("revenueBySku=" + revenueBySku);
        System.out.println("quantityBySku=" + quantityBySku);
        System.out.println("top3=" + topIds);
        System.out.println("averagePaid=" + averagePaid);
        System.out.println("mostExpensivePaid="
                + mostExpensive.get().getId());
        System.out.println("countByRegion=" + countByRegion);
        System.out.println("toMapMatchesGrouping="
                + revenueByCustomer.equals(
                        revenueByCustomerWithMerge));
    }
}
~~~

### 6.1. Biên dịch và chạy

Trên JDK 8:

~~~bash
javac -encoding UTF-8 OrderAnalyticsDemo.java
java OrderAnalyticsDemo
~~~

Nếu đang dùng JDK mới và muốn kiểm tra source/API tương thích Java 8:

~~~bash
javac --release 8 -encoding UTF-8 OrderAnalyticsDemo.java
java OrderAnalyticsDemo
~~~

`--release 8` yêu cầu JDK compiler hiện đại có hỗ trợ tùy chọn này; nó kiểm tra cả source language level và API surface của Java 8.

### 6.2. Stdout đã kiểm chứng

~~~text
orderCount=7
paidCount=5
paidRevenue=596.00
countsByStatus={PAID=5, PENDING=1, CANCELLED=1}
revenueByCustomer={Alice=200.50, Bob=275.00, Carol=120.50}
paidVsOther={false=70.00, true=596.00}
revenueBySku={Keyboard=200.50, Monitor=275.00, Mouse=120.50}
quantityBySku={Keyboard=2, Monitor=3, Mouse=3}
top3=O-104,O-100,O-103
averagePaid=119.20
mostExpensivePaid=O-104
countByRegion={North=5, South=2}
toMapMatchesGrouping=true
~~~

**Kết quả này được chạy kiểm tra với JDK 24.0.2 và biên dịch thành công ở chế độ `--release 8`.** Các giá trị tiền dùng `BigDecimal`, không chuyển qua `double`.

## 7. Phân tích từng báo cáo trong chương trình

### 7.1. Lọc đơn đã thanh toán

~~~java
List<Order> paid = orders.stream()
        .filter(Order::isPaid)
        .collect(Collectors.toList());
~~~

`filter` nhận Predicate và chỉ giữ phần tử có kết quả true. `Order::isPaid` tương đương:

~~~java
order -> order.isPaid()
~~~

Dùng method reference giúp biểu thức ngắn và nêu rõ quy tắc nghiệp vụ. `paid` là danh sách kết quả mới; `orders` ban đầu không bị sửa.

### 7.2. Tính tổng doanh thu bằng reduce

~~~java
BigDecimal paidRevenue = paid.stream()
        .map(Order::getTotal)
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

Quá trình:

1. `map` chuyển từng `Order` thành `BigDecimal total`.
2. `reduce` bắt đầu từ `BigDecimal.ZERO`.
3. `BigDecimal::add` cộng lần lượt các giá trị.
4. Nếu Stream rỗng, kết quả vẫn là `BigDecimal.ZERO`.

**Vì sao không dùng `Collectors.summingDouble`?** `double` dùng biểu diễn nhị phân, không thể biểu diễn chính xác mọi số thập phân. Với tiền tệ, dùng `BigDecimal` và xác định scale/rounding policy.

### 7.3. Đếm theo trạng thái bằng groupingBy + counting

~~~java
Map<Status, Long> countsByStatus = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getStatus,
                () -> new EnumMap<>(Status.class),
                Collectors.counting()));
~~~

Có ba tham số:

- Classifier: `Order::getStatus` chọn khóa nhóm.
- Map factory: `() -> new EnumMap<>(Status.class)` tạo Map có thứ tự enum.
- Downstream: `Collectors.counting()` đếm phần tử trong từng nhóm.

Nếu không cần Map factory, có thể viết ngắn:

~~~java
Map<Status, Long> counts = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getStatus,
                Collectors.counting()));
~~~

Khi không chỉ định map factory, **không nên giả định implementation hoặc thứ tự iteration của Map**. Chọn `EnumMap`, `TreeMap` hoặc `LinkedHashMap` khi hợp đồng kết quả yêu cầu kiểu/thứ tự cụ thể.

### 7.4. Doanh thu theo khách hàng bằng groupingBy + reducing

~~~java
Map<String, BigDecimal> revenueByCustomer =
        paid.stream().collect(Collectors.groupingBy(
                Order::getCustomer,
                TreeMap::new,
                Collectors.reducing(
                        BigDecimal.ZERO,
                        Order::getTotal,
                        BigDecimal::add)));
~~~

Cách đọc:

- Nhóm đơn theo tên khách hàng.
- Dùng `TreeMap` để kết quả hiển thị theo thứ tự tên.
- Với từng nhóm, ánh xạ đơn sang tổng tiền.
- Dùng `BigDecimal.add` để cộng các đơn trong nhóm.

`reducing(identity, mapper, op)` rất hữu ích khi kiểu dữ liệu cần tổng hợp không có collector chuyên dụng.

**Trong production, nên nhóm theo customer ID ổn định** thay vì tên hiển thị, vì tên có thể trùng hoặc thay đổi.

### 7.5. PartitioningBy: hai nhóm đúng/sai

~~~java
Map<Boolean, BigDecimal> paidSplit = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::isPaid,
                Collectors.reducing(
                        BigDecimal.ZERO,
                        Order::getTotal,
                        BigDecimal::add)));
~~~

`partitioningBy` chia dữ liệu theo một Predicate:

- Key `true`: đơn đã thanh toán.
- Key `false`: đơn không phải `PAID`.

Khác với `groupingBy`, key của `partitioningBy` luôn là Boolean. Collector partitioning tạo cả hai nhóm true/false, kể cả khi một nhóm không có phần tử.

### 7.6. flatMap: từ đơn hàng sang các dòng sản phẩm

Một đơn hàng có nhiều dòng sản phẩm. `map` trên `Order::getLines` sẽ tạo Stream của List:

~~~java
Stream<List<OrderLine>> nested = paid.stream()
        .map(Order::getLines);
~~~

Muốn xử lý tất cả dòng sản phẩm như một luồng phẳng, dùng `flatMap`:

~~~java
Stream<OrderLine> allLines = paid.stream()
        .flatMap(order -> order.getLines().stream());
~~~

Có thể hình dung:

~~~text
O-100 -> [Keyboard, Mouse]
O-101 -> [Monitor]
O-103 -> [Keyboard]

flatMap
  |
  v
[Keyboard, Mouse, Monitor, Keyboard]
~~~

Sau đó nhóm theo SKU:

~~~java
Map<String, BigDecimal> revenueBySku = paid.stream()
        .flatMap(order -> order.getLines().stream())
        .collect(Collectors.groupingBy(
                OrderLine::getSku,
                TreeMap::new,
                Collectors.reducing(
                        BigDecimal.ZERO,
                        OrderLine::getLineTotal,
                        BigDecimal::add)));
~~~

Đây là pattern phổ biến khi tổng hợp dữ liệu có quan hệ cha-con: đơn hàng → dòng sản phẩm, hóa đơn → chi tiết, phòng ban → nhân viên, bài viết → tag.

### 7.7. Đếm số lượng bán theo SKU

~~~java
Map<String, Integer> quantityBySku = paid.stream()
        .flatMap(order -> order.getLines().stream())
        .collect(Collectors.groupingBy(
                OrderLine::getSku,
                TreeMap::new,
                Collectors.summingInt(
                        OrderLine::getQuantity)));
~~~

`summingInt` nhận một ToIntFunction và trả tổng int. Nếu tổng số lượng có thể vượt giới hạn `int`, dùng `summingLong` và kiểu dữ liệu `long`.

### 7.8. Top 3 đơn hàng

~~~java
Comparator<Order> topOrder =
        Comparator.comparing(Order::getTotal)
                .reversed()
                .thenComparing(Order::getId);

List<Order> topThree = paid.stream()
        .sorted(topOrder)
        .limit(3)
        .collect(Collectors.toList());
~~~

Quy trình:

1. Lọc `PAID` trước khi xếp hạng.
2. Sắp xếp tổng tiền giảm dần.
3. Nếu tổng tiền bằng nhau, mã đơn tăng dần.
4. Lấy tối đa ba phần tử.

Nếu không thêm `thenComparing(Order::getId)`, thứ tự các đơn có cùng tổng tiền có thể phụ thuộc thứ tự đầu vào. Với báo cáo, API hoặc test cần kết quả ổn định, hãy xác định tie-breaker.

### 7.9. Tìm đơn hàng có giá trị lớn nhất

~~~java
Optional<Order> mostExpensive = paid.stream()
        .max(Comparator.comparing(Order::getTotal)
                .thenComparing(Order::getId));
~~~

`max` trả `Optional<Order>` vì Stream có thể rỗng. Trong chương trình dữ liệu mẫu có ít nhất một đơn PAID nên có thể gọi `get()` để in kết quả.

Trong code production, nên xử lý trường hợp rỗng:

~~~java
mostExpensive.ifPresent(order ->
        System.out.println(order.getId()));
~~~

Hoặc:

~~~java
Order selected = mostExpensive.orElseThrow(
        () -> new IllegalStateException(
                "No paid order found"));
~~~

Không gọi `Optional.get()` khi chưa xác định có giá trị.

### 7.10. Dùng toMap với merge function

Một cách khác để tính doanh thu theo khách hàng:

~~~java
Map<String, BigDecimal> revenueByCustomer =
        paid.stream().collect(Collectors.toMap(
                Order::getCustomer,
                Order::getTotal,
                BigDecimal::add,
                TreeMap::new));
~~~

Các tham số:

1. Key mapper: khách hàng.
2. Value mapper: tổng tiền đơn.
3. Merge function: cộng tiền nếu khách hàng đã xuất hiện.
4. Map factory: tạo TreeMap.

Nếu dùng overload hai mapper mà key bị trùng, `toMap` ném `IllegalStateException`. Merge function phải thể hiện đúng nghiệp vụ khi nhiều phần tử cùng khóa.

**Không dùng `BigDecimal::add` làm merge function cho mọi loại Map một cách máy móc.** Với map số lượng, có thể dùng `Integer::sum`; với map chọn bản ghi mới nhất, cần comparator/timestamp; với ID đơn hàng phải duy nhất, trùng key có thể là lỗi dữ liệu và nên được báo lỗi.

## 8. Các collector nâng cao cho báo cáo đơn hàng

### 8.1. Mapping: nhóm theo khách hàng nhưng chỉ lấy mã đơn

~~~java
Map<String, List<String>> orderIdsByCustomer =
        orders.stream().collect(Collectors.groupingBy(
                Order::getCustomer,
                TreeMap::new,
                Collectors.mapping(
                        Order::getId,
                        Collectors.toList())));
~~~

`mapping` chuyển từng `Order` thành `String id` trước khi downstream `toList()` tích lũy.

### 8.2. Nested grouping: khu vực rồi trạng thái

~~~java
Map<String, Map<Status, Long>> countByRegionAndStatus =
        orders.stream().collect(Collectors.groupingBy(
                Order::getRegion,
                TreeMap::new,
                Collectors.groupingBy(
                        Order::getStatus,
                        () -> new EnumMap<>(Status.class),
                        Collectors.counting())));
~~~

Kết quả có cấu trúc:

~~~text
North
  PAID      -> 3
  PENDING   -> 1
  CANCELLED -> 1

South
  PAID      -> 2
~~~

Nested grouping hữu ích cho báo cáo theo nhiều chiều: khu vực → trạng thái, tháng → khách hàng, cửa hàng → danh mục sản phẩm.

### 8.3. Đếm đơn theo tháng

~~~java
Map<YearMonth, Long> ordersByMonth = orders.stream()
        .collect(Collectors.groupingBy(
                order -> YearMonth.from(order.getOrderDate()),
                TreeMap::new,
                Collectors.counting()));
~~~

`YearMonth` phù hợp để nhóm theo tháng/năm mà không cần tự ghép chuỗi `"2025-03"`. `TreeMap` giúp tháng hiển thị theo thứ tự thời gian.

Cần import:

~~~java
import java.time.YearMonth;
~~~

### 8.4. Tìm đơn lớn nhất trong từng khách hàng

~~~java
Map<String, Optional<Order>> largestOrderByCustomer =
        paid.stream().collect(Collectors.groupingBy(
                Order::getCustomer,
                TreeMap::new,
                Collectors.maxBy(
                        Comparator.comparing(Order::getTotal)
                                .thenComparing(Order::getId))));
~~~

`maxBy` là downstream collector. Mỗi nhóm khách hàng có `Optional<Order>` để biểu diễn trường hợp nhóm không có phần tử; với `groupingBy` trên nguồn đã có phần tử thì mỗi khóa tạo ra sẽ có ít nhất một phần tử.

### 8.5. collectingAndThen: hoàn tất sau khi collect

Nếu muốn kết quả danh sách không cho sửa đổi:

~~~java
List<Order> immutableTopThree = paid.stream()
        .sorted(topOrder)
        .limit(3)
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                Collections::unmodifiableList));
~~~

`collectingAndThen` chạy một finisher sau downstream collector. Trong ví dụ, `toList()` tạo danh sách rồi `Collections.unmodifiableList` bọc danh sách thành view không sửa được.

Nếu cần một bản sao bất biến độc lập, hãy chọn cách copy phù hợp; `unmodifiableList` là wrapper, không tự tạo deep copy các phần tử.

### 8.6. Tính trung bình tiền

Không có `averagingBigDecimal` trong Collectors chuẩn. Có thể tính tổng và số lượng, sau đó chia theo scale/rounding policy:

~~~java
BigDecimal average = paidRevenue.divide(
        BigDecimal.valueOf(paid.size()),
        2,
        RoundingMode.HALF_UP);
~~~

Chỉ thực hiện phép chia khi `paid.size() > 0`. Với tập dữ liệu có thể rỗng, trả `Optional<BigDecimal>` hoặc định nghĩa kết quả rỗng rõ ràng.

`HALF_UP` ở đây là quy tắc nghiệp vụ được chọn cho ví dụ. Không có một rounding mode đúng cho mọi loại tiền tệ/nghiệp vụ.

## 9. BigDecimal trong tổng hợp đơn hàng

Đối với giá, thuế và tiền:

~~~java
BigDecimal price = new BigDecimal("19.90");
BigDecimal quantity = BigDecimal.valueOf(3);
BigDecimal lineTotal = price.multiply(quantity);
~~~

Không dùng:

~~~java
BigDecimal wrong = new BigDecimal(19.90);
~~~

Constructor nhận `double` chuyển giá trị binary floating-point hiện tại sang BigDecimal, có thể tạo biểu diễn dài ngoài mong muốn. Dùng chuỗi thập phân hoặc `BigDecimal.valueOf` nếu đầu vào thực sự là double theo semantics phù hợp.

### 9.1. equals và compareTo

~~~java
BigDecimal a = new BigDecimal("10.0");
BigDecimal b = new BigDecimal("10.00");

System.out.println(a.equals(b));
System.out.println(a.compareTo(b) == 0);
~~~

Stdout:

~~~text
false
true
~~~

`equals` xét cả scale; `compareTo` so sánh giá trị số. Khi xếp hạng tiền, `Comparator.comparing(Order::getTotal)` dùng natural ordering của BigDecimal, dựa trên `compareTo`.

### 9.2. Không cộng các loại tiền tệ khác nhau

Nếu dữ liệu có VND, USD, EUR, không được group chỉ theo khách hàng rồi cộng trực tiếp các số tiền. Cần nhóm theo cả khách hàng và currency hoặc quy đổi theo tỷ giá/định nghĩa thời điểm tỷ giá rõ ràng.

Ví dụ nhóm hai chiều:

~~~java
Map<String, Map<String, BigDecimal>> revenueByCustomerAndCurrency =
        orders.stream().filter(Order::isPaid)
                .collect(Collectors.groupingBy(
                        Order::getCustomer,
                        TreeMap::new,
                        Collectors.groupingBy(
                                Order::getCurrency,
                                TreeMap::new,
                                Collectors.reducing(
                                        BigDecimal.ZERO,
                                        Order::getTotal,
                                        BigDecimal::add))));
~~~

Đoạn này là ví dụ mở rộng: model `Order` phải có `getCurrency()` và currency code hợp lệ. Không copy trực tiếp vào chương trình chính nếu class chưa khai báo thuộc tính đó.

### 9.3. Rounding phải được thực hiện đúng tầng

Không round mỗi dòng một cách tùy tiện rồi mới cộng, nếu hợp đồng nghiệp vụ yêu cầu cộng trước rồi round tổng. Ngược lại, nếu quy định thuế yêu cầu làm tròn từng dòng, phải làm theo quy tắc đó.

Tách rõ:

- Precision đầu vào.
- Scale lưu trữ.
- Rounding của từng dòng.
- Rounding của tổng đơn.
- Rounding của báo cáo/hiển thị.

Stream/Collector chỉ thực hiện phép toán được cung cấp; nó không tự quyết định chính sách tiền tệ.

## 10. Dữ liệu rỗng, null và khóa trùng

### 10.1. Stream rỗng

Các terminal operations có hành vi khác nhau:

- `count()` trả `0`.
- `collect(toList())` trả danh sách rỗng.
- `reduce(identity, op)` trả identity.
- `max`/`min` trả `Optional.empty()`.
- `findFirst`/`findAny` trả `Optional.empty()`.

Ví dụ:

~~~java
Optional<Order> highest = Collections.<Order>emptyList()
        .stream()
        .max(Comparator.comparing(Order::getTotal));

System.out.println(highest.isPresent());
~~~

Stdout:

~~~text
false
~~~

### 10.2. Null trong nguồn

Không nên để `null` lọt vào pipeline rồi hy vọng collector tự xử lý.

~~~java
List<Order> validOrders = ordersWithNulls.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
~~~

Nếu một thuộc tính như customer có thể null, hãy định nghĩa rõ chính sách:

- Loại đơn không hợp lệ.
- Gán nhóm `"UNKNOWN"` nếu domain cho phép.
- Hoặc từ chối dữ liệu tại validation boundary.

`groupingBy` không nên nhận classifier trả về null; hãy chuẩn hóa/kiểm tra trước khi grouping.

### 10.3. Duplicate key trong toMap

~~~java
Map<String, Order> byCustomer = orders.stream()
        .collect(Collectors.toMap(
                Order::getCustomer,
                order -> order));
~~~

Nếu một khách hàng có nhiều đơn, khóa bị trùng và overload không có merge function sẽ ném `IllegalStateException`.

Nếu muốn lấy đơn mới nhất:

~~~java
Map<String, Order> latestByCustomer = orders.stream()
        .collect(Collectors.toMap(
                Order::getCustomer,
                order -> order,
                (left, right) ->
                        left.getOrderDate().isAfter(
                                right.getOrderDate())
                                ? left : right));
~~~

Nếu hai đơn có cùng ngày, ví dụ này chọn `right`; nếu cần kết quả xác định độc lập thứ tự nguồn, hãy thêm tie-breaker bằng timestamp chính xác hoặc order ID.

### 10.4. toList không cam kết loại List cụ thể

`Collectors.toList()` không cam kết loại List cụ thể, khả năng sửa đổi, khả năng serializable hoặc thread safety. Nếu cần `ArrayList` cụ thể:

~~~java
List<Order> mutable = orders.stream()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Nếu cần danh sách không sửa được, dùng `collectingAndThen` như ví dụ trước hoặc API unmodifiable tương ứng với phiên bản Java.

## 11. Hiệu năng và parallel streams

### 11.1. Không mặc định parallel nhanh hơn

~~~java
Map<String, BigDecimal> totals = orders.parallelStream()
        .collect(Collectors.groupingBy(
                Order::getCustomer,
                Collectors.reducing(
                        BigDecimal.ZERO,
                        Order::getTotal,
                        BigDecimal::add)));
~~~

`groupingBy` trong parallel có thể tạo nhiều Map trung gian rồi gộp chúng. Với số lượng dữ liệu nhỏ hoặc số khóa nhiều, chi phí combine có thể lớn hơn lợi ích song song.

Bắt đầu bằng sequential stream. Chỉ chuyển sang parallel khi đã đo workload thực tế và xác nhận collector/logic phù hợp.

### 11.2. groupingByConcurrent

Nếu không cần giữ encounter order và muốn concurrent grouping, có thể cân nhắc:

~~~java
ConcurrentMap<String, Long> counts =
        orders.parallelStream()
                .collect(Collectors.groupingByConcurrent(
                        Order::getCustomer,
                        Collectors.counting()));
~~~

Cần import `ConcurrentMap`. `groupingByConcurrent` trả concurrent map và có semantics về thứ tự khác `groupingBy`. Không dùng nó khi thứ tự output là một phần của hợp đồng.

### 11.3. Không chia sẻ mutable accumulator bên ngoài

Không dùng một `ArrayList` hoặc `HashMap` bên ngoài rồi sửa trực tiếp từ `parallelStream().forEach(...)`. Collector được thiết kế để framework quản lý các container trung gian và bước combine.

### 11.4. Giữ side effect ở ngoài pipeline

Không gửi email, ghi database, gọi API hoặc thay đổi trạng thái đơn hàng trong `map`/`filter` chỉ để tạo báo cáo. Các thao tác này có thể bị thực thi theo thứ tự/luồng khác khi pipeline thay đổi hoặc chạy parallel.

Stream phù hợp cho **biến đổi và tổng hợp dữ liệu**. Tác vụ side effect cần một luồng xử lý và transaction/error policy riêng.

## 12. Các phiên bản API cần phân biệt

| API | Phiên bản đầu tiên | Ghi chú |
|---|---:|---|
| Stream, `filter`, `map`, `flatMap`, `sorted`, `collect` | Java 8 | Pipeline cơ bản |
| `Collectors.groupingBy`, `partitioningBy`, `mapping`, `reducing`, `toMap` | Java 8 | Dùng trong bài |
| `Comparator.comparing`, `thenComparing`, `reversed`, `nullsFirst`, `nullsLast` | Java 8 | Dùng trong bài |
| `Collectors.filtering`, `Collectors.flatMapping` | Java 9 | Downstream collector bổ sung |
| `Collectors.toUnmodifiableList/Set/Map` | Java 10 | Collection kết quả không sửa được |
| `Collectors.teeing` | Java 12 | Kết hợp hai downstream collectors |
| `Stream.toList()` | Java 16 | Trả List không sửa được |
| `mapMulti` | Java 16 | Thay thế một số trường hợp flatMap |

Bài thực hành chính không yêu cầu API sau Java 8. Khi làm việc trong project Java 8, tiếp tục dùng `collect(Collectors.toList())`, `groupingBy`, `mapping`, `flatMap` và các method Comparator Java 8.

### 12.1. teeing trong Java 12+

Khi cần tổng hợp hai kết quả từ cùng một Stream pipeline, Java 12+ có `Collectors.teeing`. Ví dụ sau cần model có `getTotal()`:

~~~java
// Java 12+
Map<String, String> summary = orders.stream()
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.reducing(
                        BigDecimal.ZERO,
                        Order::getTotal,
                        BigDecimal::add),
                (count, total) ->
                        "count=" + count + ",total=" + total));
~~~

`teeing` nhận hai downstream collectors và một merger. Đây là API bổ sung; không đưa vào source Java 8.

## 13. Các lỗi thường gặp khi tổng hợp đơn hàng

1. **Quên filter trạng thái trước khi tính doanh thu.** Đơn `PENDING` hoặc `CANCELLED` có thể bị cộng nhầm.
2. **Dùng `map` thay cho `flatMap` với dòng sản phẩm.** Kết quả là Stream của List thay vì Stream của từng OrderLine.
3. **Dùng `double` cho tiền.** Có thể tạo sai số thập phân.
4. **Dùng `new BigDecimal(double)`.** Giá trị binary floating-point được chuyển nguyên trạng.
5. **Dùng `summingDouble` cho doanh thu.** Không phù hợp nếu cần tính tiền chính xác.
6. **Dùng `groupingBy` mặc định nhưng giả định Map luôn có thứ tự.** Chọn map factory nếu thứ tự quan trọng.
7. **Dùng `toMap` mà không có merge function khi key có thể trùng.** Collector ném `IllegalStateException`.
8. **Dùng merge function sai nghiệp vụ.** Không phải mọi duplicate key đều nên cộng giá trị.
9. **Sắp xếp nhiều tiêu chí nhưng đặt `reversed()` sai vị trí.** Có thể đảo cả tie-breaker.
10. **Comparator dùng phép trừ.** Có thể overflow với số nguyên lớn.
11. **Comparator không có tie-breaker.** Báo cáo top-N có thể không ổn định khi khóa chính bằng nhau.
12. **Gọi `Optional.get()` khi không có phần tử.** Có thể ném `NoSuchElementException`.
13. **Chia trung bình khi số lượng bằng 0.** Phải kiểm tra trước.
14. **Tái sử dụng một Stream.** Stream đã được tiêu thụ sau terminal operation.
15. **Sửa nguồn trong lúc pipeline chạy.** Có thể gây lỗi hoặc kết quả không xác định.
16. **Dùng side effect trong map/filter.** Làm pipeline khó dự đoán và khó chạy parallel.
17. **Dùng parallelStream chỉ vì dữ liệu lớn.** Phải đo chi phí combine và overhead.
18. **Không phân biệt `Collectors.toList()` với `Stream.toList()`.** Khác nhau về phiên bản và guarantee mutability.
19. **Nhóm theo tên hiển thị thay vì ID ổn định.** Tên trùng hoặc đổi tên làm sai tổng hợp.
20. **Cộng nhiều currency vào cùng một tổng.** Cần nhóm hoặc quy đổi tiền tệ trước.
21. **Không xác định quy tắc hoàn tiền/đơn hủy.** Báo cáo doanh thu có thể sai dù code Stream đúng.
22. **Không kiểm tra dữ liệu rỗng/null.** Có thể tạo lỗi ở collector hoặc sai kết quả nghiệp vụ.
23. **Dùng `peek` làm nơi thực hiện logic nghiệp vụ.** `peek` chủ yếu hỗ trợ quan sát pipeline; không dựa vào side effect.
24. **Tính tổng đơn nhiều lần trong nhiều collector.** Nếu phép tính tốn kém, cân nhắc lưu giá trị bất biến hoặc tạo projection/summary phù hợp.
25. **Không test dữ liệu có cùng tổng tiền.** Không phát hiện lỗi tie-breaker.
26. **Không kiểm tra dữ liệu trùng ID.** Có thể che lỗi chất lượng dữ liệu khi dùng `toMap` merge.

## 14. Kiểm thử kết quả tổng hợp

Một báo cáo nên được kiểm tra bằng các expected values cụ thể, không chỉ nhìn output có vẻ hợp lý.

Với dataset của bài:

~~~java
if (orders.size() != 7) {
    throw new AssertionError("order count");
}

if (paid.size() != 5) {
    throw new AssertionError("paid count");
}

if (paidRevenue.compareTo(
        new BigDecimal("596.00")) != 0) {
    throw new AssertionError("paid revenue");
}

if (!"O-104,O-100,O-103".equals(topIds)) {
    throw new AssertionError("top three");
}
~~~

Dùng `compareTo` cho kiểm tra giá trị tiền khi scale không phải một phần của contract. Nếu scale là yêu cầu, kiểm tra `scale()` riêng hoặc dùng `equals` với expected có scale chính xác.

### 14.1. Bộ test nên có

| Trường hợp | Kỳ vọng |
|---|---|
| Không có đơn | List rỗng, count 0, tổng BigDecimal.ZERO |
| Tất cả đơn PAID | Doanh thu bằng tổng các đơn |
| Không có đơn PAID | Không chia trung bình; Optional max rỗng |
| Nhiều đơn cùng khách hàng | Tổng khách hàng cộng đúng |
| Nhiều dòng cùng SKU | Doanh thu và số lượng SKU cộng đúng |
| Hai đơn bằng tổng tiền | ID tie-breaker quyết định thứ tự |
| Duplicate order ID | Báo lỗi hoặc merge theo policy đã định nghĩa |
| Customer null | Validation/filter/nhóm UNKNOWN theo contract |
| Số tiền scale khác nhau | So sánh theo policy BigDecimal |
| Đơn PENDING/CANCELLED | Không lọt vào doanh thu PAID |
| Nhiều currency | Không cộng chung nếu chưa quy đổi |
| Ngày ở nhiều tháng | Group theo YearMonth chính xác |

### 14.2. Kiểm tra tính nhất quán giữa hai cách tổng hợp

Trong chương trình, `revenueByCustomer` dùng `groupingBy + reducing`; `revenueByCustomerWithMerge` dùng `toMap + merge`.

~~~java
boolean same = revenueByCustomer.equals(
        revenueByCustomerWithMerge);
~~~

Stdout:

~~~text
toMapMatchesGrouping=true
~~~

Đây là một phép đối chiếu hữu ích khi có hai implementation cho cùng một báo cáo. Trong test suite thực tế, tách expected values ra thành fixture để tránh cả hai cách cùng lặp lại một lỗi nghiệp vụ.

## 15. Checklist khi viết báo cáo đơn hàng

- [ ] Đã định nghĩa trạng thái nào được tính doanh thu.
- [ ] Đã xác định dữ liệu nào được dùng làm nguồn: order header hay order lines.
- [ ] Tổng đơn được tính từ dòng sản phẩm theo quy tắc rõ ràng.
- [ ] Tiền sử dụng BigDecimal.
- [ ] Đã xác định scale và rounding mode.
- [ ] Không cộng các currency khác nhau nếu chưa quy đổi.
- [ ] Có validation cho quantity, price, customer ID và order ID.
- [ ] Đã lọc dữ liệu theo đúng trạng thái trước khi tổng hợp.
- [ ] Dùng flatMap khi cần chuyển đơn thành dòng sản phẩm.
- [ ] Chọn downstream collector đúng loại kết quả.
- [ ] Dùng TreeMap/EnumMap khi cần thứ tự iteration xác định.
- [ ] Có merge function cho duplicate key nếu nghiệp vụ cho phép.
- [ ] Có tie-breaker cho báo cáo xếp hạng.
- [ ] Đã xử lý Optional khi nguồn rỗng.
- [ ] Không chia trung bình cho 0.
- [ ] Không tái sử dụng Stream.
- [ ] Không sửa collection nguồn trong pipeline.
- [ ] Không dùng side effect trong intermediate operations.
- [ ] Đã đo trước khi chuyển sang parallel stream.
- [ ] Đã kiểm thử đơn rỗng, đơn hủy, đơn pending, khóa trùng và giá trị biên.
- [ ] Đã ghi rõ Java baseline để tránh gọi API mới hơn target runtime.

## 16. Bài tập thực hành

### Bài 1 — Tổng doanh thu theo khách hàng

Tạo `Map<String, BigDecimal>` tổng doanh thu đã thanh toán theo khách hàng. Dùng `groupingBy` và `reducing`.

### Bài 2 — Số đơn theo trạng thái

Dùng `groupingBy(Order::getStatus, counting())`. Chọn `EnumMap` để thứ tự trạng thái theo enum.

### Bài 3 — Số đơn theo khu vực

Dùng `TreeMap` và `counting`. So sánh kết quả với Map mặc định.

### Bài 4 — Doanh thu theo SKU

Dùng `flatMap` để làm phẳng OrderLine, sau đó `groupingBy` theo SKU và `reducing` BigDecimal.

### Bài 5 — Số lượng sản phẩm theo SKU

Dùng `summingInt`. Thử một sản phẩm xuất hiện trong nhiều đơn.

### Bài 6 — Top 5 đơn hàng

Sắp xếp tổng tiền giảm dần, mã đơn tăng dần rồi lấy 5 đơn. Thêm hai đơn có tổng tiền bằng nhau để kiểm tra tie-breaker.

### Bài 7 — Khách hàng có doanh thu cao nhất

Tạo Map doanh thu theo khách hàng rồi dùng `entrySet().stream().max(...)`. Xử lý Optional khi không có dữ liệu.

### Bài 8 — Thống kê theo tháng

Dùng `YearMonth.from(order.getOrderDate())` để nhóm số đơn theo tháng.

### Bài 9 — Group theo khu vực và trạng thái

Dùng nested `groupingBy` để tạo `Map<Region, Map<Status, Long>>`.

### Bài 10 — Duplicate key trong toMap

Thử dùng `toMap(Order::getCustomer, order -> order)` với nhiều đơn cùng khách hàng. Quan sát exception; sau đó thêm merge function chọn đơn mới nhất.

### Bài 11 — Average chính xác

Tính doanh thu trung bình theo khách hàng bằng BigDecimal. Xác định scale và rounding mode. Thử nhóm rỗng.

### Bài 12 — Null customer

Tạo một record có customer null. Xây validation hoặc policy nhóm `"UNKNOWN"` trước khi gọi `groupingBy`.

### Bài 13 — Multi-currency

Thêm thuộc tính currency. Nhóm theo customer và currency trước khi tính tổng.

### Bài 14 — Parallel collector

Chạy sequential và parallel trên dữ liệu lớn. So sánh kết quả, thời gian và chi phí combine. Không giả định parallel luôn nhanh hơn.

### Bài 15 — Immutable report

Dùng `collectingAndThen` để tạo danh sách top orders không thể sửa đổi. Kiểm tra `add` ném `UnsupportedOperationException`.

## 17. Câu hỏi ôn tập và đáp án

**1. Stream pipeline gồm những phần nào?** — Source, intermediate operations và terminal operation.

**2. Intermediate operations có thực thi ngay không?** — Không, chúng lazy cho đến khi có terminal operation.

**3. Một Stream có thể dùng lại sau `collect` không?** — Không nên; Stream là single-use.

**4. `filter` làm gì?** — Giữ các phần tử thỏa Predicate.

**5. `map` làm gì?** — Ánh xạ mỗi phần tử thành một giá trị.

**6. `flatMap` khác `map` thế nào?** — `flatMap` làm phẳng các Stream con thành một Stream duy nhất.

**7. Collector có những thành phần chính nào?** — Supplier, accumulator, combiner, finisher và characteristics.

**8. `groupingBy` dùng để làm gì?** — Nhóm phần tử theo classifier.

**9. Downstream collector là gì?** — Collector xử lý các phần tử bên trong từng nhóm.

**10. `counting()` trả kiểu gì?** — `Long`.

**11. `partitioningBy` dùng khóa nào?** — Boolean true/false.

**12. Khi nào dùng `mapping`?** — Khi muốn chuyển phần tử trước khi đưa vào downstream collector.

**13. `reducing(identity, mapper, op)` làm gì?** — Ánh xạ phần tử rồi gộp bằng phép toán và identity.

**14. `toMap` không có merge function sẽ ra sao khi key trùng?** — Ném `IllegalStateException`.

**15. `Comparator.comparing` làm gì?** — Tạo Comparator theo khóa trích xuất.

**16. `thenComparing` dùng khi nào?** — Khi cần tiêu chí phụ nếu tiêu chí trước bằng nhau.

**17. `reversed()` đảo gì?** — Đảo thứ tự mà Comparator hiện tại áp đặt.

**18. Vì sao nên thêm order ID vào Comparator top orders?** — Để kết quả có tie-breaker xác định.

**19. `max` trả về gì?** — `Optional<T>`.

**20. Vì sao dùng BigDecimal cho tiền?** — Để tránh sai số biểu diễn nhị phân của double.

**21. `BigDecimal.equals` và `compareTo` khác nhau thế nào?** — `equals` xét scale; `compareTo` so giá trị số.

**22. Vì sao `summingDouble` không phù hợp cho tiền chính xác?** — Vì dùng double.

**23. `TreeMap` giúp gì trong báo cáo?** — Duy trì thứ tự khóa theo Comparator/natural order.

**24. `EnumMap` phù hợp với gì?** — Key là enum.

**25. `Collectors.toList()` có cam kết List mutable không?** — Không cam kết implementation hoặc khả năng sửa đổi.

**26. `Stream.toList()` có từ Java nào?** — Java 16.

**27. `Collectors.teeing` có từ Java nào?** — Java 12.

**28. Có nên sửa collection nguồn trong `filter`/`map` không?** — Không.

**29. Có nên dùng parallel stream mặc định cho dữ liệu lớn không?** — Không; phải đo và đánh giá collector/chi phí combine.

**30. Làm sao tổng hợp các dòng sản phẩm từ nhiều đơn?** — `flatMap(Order::getLines...)` rồi group/reduce theo SKU.

## 18. Tổng kết

**Stream mô tả cách xử lý dữ liệu; Collector mô tả cách tích lũy kết quả; Comparator mô tả thứ tự so sánh.** Kết hợp ba API này giúp xây báo cáo đơn hàng rõ ràng và có thể kiểm thử.

Các điểm quan trọng:

1. Lọc trạng thái trước khi tính doanh thu.
2. Dùng `map` để chuyển một phần tử; dùng `flatMap` để làm phẳng dữ liệu con.
3. Dùng `groupingBy` để tạo nhóm và downstream collector để tổng hợp từng nhóm.
4. Dùng `partitioningBy` cho hai nhóm true/false.
5. Dùng `counting`, `summingInt`, `mapping`, `reducing`, `maxBy` và `collectingAndThen` theo kết quả mong muốn.
6. Dùng `toMap` với merge function khi duplicate key là hợp lệ.
7. Dùng `BigDecimal` cho tiền và xác định rounding policy.
8. Dùng `Comparator.comparing`, `reversed`, `thenComparing` để xây thứ tự nhiều tiêu chí.
9. Xử lý `Optional`, null, dữ liệu rỗng và duplicate keys rõ ràng.
10. Không giả định Map có thứ tự khi chưa chọn map factory.
11. Không dùng side effect hoặc sửa nguồn bên trong pipeline.
12. Chỉ chuyển sang parallel sau khi đo hiệu năng thực tế.
13. Kiểm tra Java baseline trước khi dùng API mới hơn Java 8.

### Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — Stream API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 26 — Collectors: groupingBy, partitioningBy, reducing, mapping, toMap và downstream collectors](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html)
- [Oracle Java SE 26 — Collector: mutable reduction và characteristics](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.html)
- [Oracle Java SE 26 — Comparator: comparing, reversed, thenComparing, nullsFirst và nullsLast](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html)
- [Oracle Java SE 26 — BigDecimal: exact decimal arithmetic, compareTo, equals và rounding](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigDecimal.html)
- [Oracle Java SE 26 — Map: key uniqueness, merge và map ordering contracts](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html)
- [Java Language Specification — Lambda Expressions and Method References](https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html)
