# Ví dụ xuyên suốt: lọc, biến đổi và tổng hợp đơn hàng bằng Java Stream

## 1. Bài toán và mục tiêu

Một cửa hàng có danh sách đơn hàng. Mỗi đơn gồm mã đơn, khách hàng, trạng thái và các dòng sản phẩm (SKU, số lượng, đơn giá). Ta cần đi từ dữ liệu thô tới một báo cáo có thể kiểm tra:

1. **Lọc** các đơn đã thanh toán (`PAID`), bỏ qua đơn đang chờ (`PENDING`) và đã hủy (`CANCELLED`).
2. **Biến đổi** từng dòng hàng thành thành tiền, từng đơn thành tổng tiền và sắp xếp các đơn đã thanh toán theo giá trị giảm dần.
3. **Tổng hợp** doanh thu từ các đơn `PAID`, doanh thu theo khách hàng và số lượng sản phẩm đã bán theo SKU.
4. Giữ dữ liệu đầu vào nguyên vẹn, đưa logic nghiệp vụ vào những hàm nhỏ và đối chiếu kết quả bằng tay.

Ví dụ này thuộc **Java core – functional programming**: thực hành `Predicate`, `Function`, lambda, method reference, `Stream`, `map`, `flatMap`, `filter`, `sorted`, `reduce` và `Collectors`. Toàn bộ chương trình dùng Java 17 trở lên, không cần thư viện ngoài JDK.

> **Quy ước nghiệp vụ của ví dụ:** “doanh thu” ở đây là tổng tiền hàng của các đơn có trạng thái `PAID`, chưa xét thuế, phí vận chuyển, chiết khấu, trả hàng hoặc thời điểm ghi nhận doanh thu kế toán. Khi làm sản phẩm thực tế, phải định nghĩa và kiểm tra các quy tắc đó riêng.

## 2. Dữ liệu mẫu và kết quả cần đạt

| Mã đơn | Khách | Trạng thái | Dòng hàng | Tổng tiền |
| --- | --- | --- | --- | ---: |
| A01 | Lan | PAID | BOOK × 2 × 120000; PEN × 3 × 10000 | 270000 |
| A02 | Minh | PENDING | BOOK × 1 × 120000 | 120000 |
| A03 | Lan | PAID | BAG × 1 × 200000 | 200000 |
| A04 | An | PAID | PEN × 5 × 10000 | 50000 |
| A05 | Minh | CANCELLED | BAG × 2 × 200000 | 400000 |
| A06 | An | PAID | BOOK × 1 × 120000; BAG × 1 × 200000 | 320000 |

Ví dụ: tổng tiền đơn A01 = `2 × 120000 + 3 × 10000 = 270000`. Có **4 đơn PAID**: A01, A03, A04, A06. Tổng tiền của A02 và A05 không được cộng vào báo cáo. Theo tập dữ liệu trên:

- Doanh thu tổng: **840000** (= 270000 + 200000 + 50000 + 320000).
- Doanh thu khách **An: 370000**; **Lan: 470000**.
- Số lượng SKU **BAG: 2**, **BOOK: 3**, **PEN: 8**. Đây là số lượng bán, không phải doanh thu từng SKU.
- Thứ tự đơn theo tổng tiền giảm dần: **A06 → A01 → A03 → A04**.

Sơ đồ dòng dữ liệu:

```text
List<Order>
    │
    ├── filter(status == PAID) ──> List<Order> paidOrders
    │                                 │
    │                                 ├── sorted(total DESC) ─> danh sách hiển thị
    │                                 ├── map(total) + reduce ─> tổng doanh thu
    │                                 ├── groupingBy(customer,
    │                                 │       reducing(total)) ─> doanh thu/khách
    │                                 └── flatMap(lines)
    │                                         + groupingBy(sku,
    │                                           summingInt(quantity))
    │                                                      └── số lượng/SKU
    └── dữ liệu gốc giữ nguyên
```

## 3. Chương trình Java 17 hoàn chỉnh

Tạo tệp **`OrderPipelineDemo.java`** với nội dung sau. Tên tệp phải trùng tên `public class`.

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class OrderPipelineDemo {
    enum Status {
        PAID, PENDING, CANCELLED
    }

    record OrderLine(String sku, int quantity, BigDecimal unitPrice) {
        BigDecimal subtotal() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    record Order(String id, String customer, Status status, List<OrderLine> lines) {
        Order {
            lines = List.copyOf(lines);
        }

        BigDecimal total() {
            return lines.stream()
                    .map(OrderLine::subtotal)
                    .reduce(BigDecimal.ZERO, BigDecimal::add);
        }
    }

    private static BigDecimal money(String value) {
        return new BigDecimal(value);
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A01", "Lan", Status.PAID, List.of(
                        new OrderLine("BOOK", 2, money("120000")),
                        new OrderLine("PEN", 3, money("10000")))),
                new Order("A02", "Minh", Status.PENDING, List.of(
                        new OrderLine("BOOK", 1, money("120000")))),
                new Order("A03", "Lan", Status.PAID, List.of(
                        new OrderLine("BAG", 1, money("200000")))),
                new Order("A04", "An", Status.PAID, List.of(
                        new OrderLine("PEN", 5, money("10000")))),
                new Order("A05", "Minh", Status.CANCELLED, List.of(
                        new OrderLine("BAG", 2, money("200000")))),
                new Order("A06", "An", Status.PAID, List.of(
                        new OrderLine("BOOK", 1, money("120000")),
                        new OrderLine("BAG", 1, money("200000"))))
        );

        // 1. Hàm điều kiện được truyền cho filter.
        Predicate<Order> isPaid = order -> order.status() == Status.PAID;
        List<Order> paidOrders = orders.stream()
                .filter(isPaid)
                .toList();

        // 2. Hàm ánh xạ Order -> BigDecimal, có thể dùng lại.
        Function<Order, BigDecimal> totalOf = Order::total;
        List<Order> ranked = paidOrders.stream()
                .sorted(Comparator.comparing(totalOf)
                        .reversed()
                        .thenComparing(Order::id))
                .toList();

        System.out.println("Đơn PAID theo tổng tiền giảm dần:");
        ranked.forEach(order -> System.out.printf(
                "%s | %s | %s%n",
                order.id(),
                order.customer(),
                order.total().toPlainString()
        ));

        // 3. Cộng các giá trị BigDecimal.
        BigDecimal revenue = paidOrders.stream()
                .map(totalOf)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println("Tổng doanh thu: " + revenue.toPlainString());

        // 4. Nhóm theo khách và cộng tổng tiền các đơn thuộc nhóm.
        Map<String, BigDecimal> revenueByCustomer = paidOrders.stream()
                .collect(Collectors.groupingBy(
                        Order::customer,
                        TreeMap::new,
                        Collectors.reducing(
                                BigDecimal.ZERO,
                                Order::total,
                                BigDecimal::add
                        )
                ));

        System.out.println("Doanh thu theo khách:");
        revenueByCustomer.forEach((customer, total) ->
                System.out.printf("%s: %s%n",
                        customer, total.toPlainString()));

        // 5. Trải phẳng mọi dòng hàng của các đơn PAID rồi nhóm theo SKU.
        Map<String, Integer> quantityBySku = paidOrders.stream()
                .flatMap(order -> order.lines().stream())
                .collect(Collectors.groupingBy(
                        OrderLine::sku,
                        TreeMap::new,
                        Collectors.summingInt(OrderLine::quantity)
                ));

        System.out.println("Số lượng theo SKU:");
        quantityBySku.forEach((sku, quantity) ->
                System.out.printf("%s: %d%n", sku, quantity));
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```bash
javac --release 17 OrderPipelineDemo.java
java OrderPipelineDemo
```

Kết quả chuẩn (stdout):

```text
Đơn PAID theo tổng tiền giảm dần:
A06 | An | 320000
A01 | Lan | 270000
A03 | Lan | 200000
A04 | An | 50000
Tổng doanh thu: 840000
Doanh thu theo khách:
An: 370000
Lan: 470000
Số lượng theo SKU:
BAG: 2
BOOK: 3
PEN: 8
```

Giá trị được in bằng `BigDecimal.toPlainString()` để tránh ký pháp số mũ. `TreeMap` đảm bảo các khóa khách hàng và SKU được duyệt theo thứ tự từ điển, nên thứ tự những dòng tương ứng là ổn định. Câu lệnh `sorted` đảm bảo danh sách đơn được duyệt theo tổng tiền giảm dần; khi bằng tiền, `thenComparing(Order::id)` dùng mã đơn làm quy tắc phụ để kết quả không phụ thuộc vị trí dữ liệu đầu vào.

## 4. Phân tích pipeline theo từng bước

### Bước 1 — Mô hình hóa dữ liệu và tính thành tiền

- `OrderLine` là một **record** biểu diễn dòng hàng. `subtotal()` tính `unitPrice × quantity` và trả về `BigDecimal`.
- `Order` lưu thông tin đơn và danh sách dòng hàng. Compact constructor `Order { lines = List.copyOf(lines); }` tạo bản sao danh sách, giúp ngăn việc sửa danh sách bên ngoài sau khi tạo đơn. Các `OrderLine` là record, nhưng cách sao chép này chỉ là sao chép cấu trúc danh sách, không phải sao chép sâu mọi object.
- `Order.total()` xử lý từng dòng trong một đơn bằng `map(OrderLine::subtotal)`, sau đó `reduce(BigDecimal.ZERO, BigDecimal::add)`. Nếu đơn có danh sách dòng hàng rỗng, giá trị của `reduce` là `BigDecimal.ZERO`.
- `money("120000")` nhận chuỗi và tạo `BigDecimal` đúng giá trị thập phân. Trong bài toán tiền, tránh tạo `BigDecimal` từ literal `double` như `new BigDecimal(0.1)` vì `double` có sai số biểu diễn nhị phân.

Trong ứng dụng thực tế, cần kiểm tra `quantity > 0`, `unitPrice >= 0`, các trường bắt buộc và mã SKU hợp lệ ngay tại ranh giới tạo dữ liệu. Ví dụ tập trung vào pipeline nên dùng dữ liệu đã hợp lệ.

### Bước 2 — Lọc đơn bằng `Predicate` và `filter`

```java
Predicate<Order> isPaid = order -> order.status() == Status.PAID;
List<Order> paidOrders = orders.stream()
        .filter(isPaid)
        .toList();
```

`Predicate<Order>` mô tả một hàm kiểm tra từ `Order` sang `boolean`. `filter(isPaid)` chỉ cho những đơn trả về `true` đi tiếp. Dùng `==` ở đây đúng vì `Status` là `enum`. Dùng `equals` cho các giá trị như chuỗi khi kiểm tra nội dung, không dùng `==` để so sánh hai chuỗi.

`stream()` tạo luồng từ `orders`; `filter` là *intermediate operation* nên được thực thi khi `toList()` (*terminal operation*) chạy. `toList()` trong Java 17 trả về danh sách **không thể sửa** qua `add`/`remove`; không nhầm với việc đóng băng mọi object tham chiếu bên trong. `filter` không xóa đơn nào khỏi `orders`.

### Bước 3 — Biến đổi và sắp xếp

```java
Function<Order, BigDecimal> totalOf = Order::total;
List<Order> ranked = paidOrders.stream()
        .sorted(Comparator.comparing(totalOf)
                .reversed()
                .thenComparing(Order::id))
        .toList();
```

`Function<Order, BigDecimal>` là hàm chuyển `Order` thành tổng tiền. `Order::total` là *method reference* tương đương `order -> order.total()`. `Comparator.comparing(totalOf)` so sánh kết quả `BigDecimal` theo thứ tự tăng dần, `reversed()` đảo thành giảm dần, `thenComparing` xử lý trường hợp đồng hạng.

`sorted` tạo một luồng có thứ tự mới, không hoán vị `orders` hay `paidOrders`. Mỗi lần gọi `total()` lại duyệt các dòng hàng của đơn; với tập lớn và phép tính đắt, có thể lưu một bản chiếu `(order, total)` để tính tiền **một lần** trước khi sắp xếp.

### Bước 4 — Cộng doanh thu với `map` và `reduce`

```java
BigDecimal revenue = paidOrders.stream()
        .map(totalOf)
        .reduce(BigDecimal.ZERO, BigDecimal::add);
```

`map(totalOf)` đổi `Stream<Order>` thành `Stream<BigDecimal>`. `reduce` gộp nhiều giá trị thành một: bắt đầu với `0` rồi cộng từng tổng đơn. Phép cộng của `BigDecimal` tạo giá trị mới; không thay đổi hai toán hạng. Phép cộng này có phần tử đơn vị `ZERO` và có tính kết hợp về giá trị số, phù hợp với cách rút gọn của stream.

**Phân biệt:** `map` biến đổi **mỗi phần tử thành đúng một phần tử kết quả**; `filter` có thể giữ hoặc bỏ phần tử; `reduce` cho ra **một giá trị tổng hợp**. Không dùng `map` chỉ để sửa biến đếm ngoài luồng vì sẽ tạo tác dụng phụ và khó xử lý song song.

### Bước 5 — Nhóm và tổng hợp theo khách bằng `Collectors.groupingBy`

```java
Map<String, BigDecimal> revenueByCustomer = paidOrders.stream()
        .collect(Collectors.groupingBy(
                Order::customer,
                TreeMap::new,
                Collectors.reducing(
                        BigDecimal.ZERO, Order::total, BigDecimal::add
                )
        ));
```

Ba tham số của `groupingBy` lần lượt là:

1. **Hàm tạo khóa nhóm:** `Order::customer`. Ví dụ A01 và A03 đều vào nhóm `Lan`.
2. **Nhà cung cấp Map:** `TreeMap::new` để thứ tự duyệt khóa ổn định theo thứ tự tự nhiên của `String`.
3. **Downstream collector:** `reducing` chuyển từng `Order` thành `Order.total()` rồi cộng tất cả đơn trong từng nhóm.

Kết quả là `Map<String, BigDecimal>`: mỗi khách gắn với **tổng doanh thu**, không phải danh sách đơn. Nếu chỉ dùng `groupingBy(Order::customer)`, giá trị mặc định là `List<Order>`; nếu dùng `counting()`, giá trị là **số đơn**, không phải doanh thu. Chọn downstream collector theo đúng câu hỏi nghiệp vụ.

### Bước 6 — Trải phẳng dòng hàng với `flatMap` rồi đếm số lượng SKU

```java
Map<String, Integer> quantityBySku = paidOrders.stream()
        .flatMap(order -> order.lines().stream())
        .collect(Collectors.groupingBy(
                OrderLine::sku,
                TreeMap::new,
                Collectors.summingInt(OrderLine::quantity)
        ));
```

Mỗi `Order` có một danh sách `OrderLine`. Nếu dùng `map(Order::lines)`, kiểu kết quả sẽ là `Stream<List<OrderLine>>`: vẫn còn các danh sách lồng nhau. `flatMap(order -> order.lines().stream())` tạo `Stream<OrderLine>` duy nhất, nối các dòng của **những đơn đã lọc** vào cùng luồng.

`summingInt(OrderLine::quantity)` cộng `quantity` theo SKU. Với đơn đã thanh toán, BAG xuất hiện ở A03 và A06, nên có `1 + 1 = 2`; BOOK có `2 + 1 = 3`; PEN có `3 + 5 = 8`. Nếu muốn **doanh thu theo SKU**, phải tổng hợp `OrderLine::subtotal` bằng `BigDecimal`; `summingInt` ở đây chỉ phù hợp với **số lượng**. Trong hệ thống có tổng số lượng rất lớn, kiểm tra nguy cơ tràn `int` và cân nhắc `summingLong` hoặc kiểu số thích hợp.

## 5. Vì sao cách viết này là functional programming?

Mỗi phép biến đổi thể hiện một quyết định nhỏ, có thể đặt tên, tái sử dụng và kiểm thử riêng:

| Thành phần | Vai trò trong bài | Kiểu dữ liệu tiêu biểu |
| --- | --- | --- |
| `Predicate<Order>` | Kiểm tra đơn đã thanh toán | `Order -> boolean` |
| `Function<Order, BigDecimal>` | Tính tổng tiền một đơn | `Order -> BigDecimal` |
| `filter` | Chọn đơn đủ điều kiện | `Stream<Order> -> Stream<Order>` |
| `map` | Biến đổi đơn thành tổng tiền | `Stream<Order> -> Stream<BigDecimal>` |
| `flatMap` | Gom dòng hàng từ nhiều đơn | `Stream<Order> -> Stream<OrderLine>` |
| `sorted` | Sắp thứ tự các đơn | `Stream<Order> -> Stream<Order>` |
| `reduce` | Cộng thành một tổng | `Stream<BigDecimal> -> BigDecimal` |
| `collect(groupingBy(...))` | Gom phần tử theo khóa và tích lũy kết quả | `Stream<T> -> Map<K, V>` |

Luồng có mô hình **source → intermediate operations → terminal operation**. Các operation như `filter`, `map` và `sorted` không tạo ra báo cáo cho tới khi terminal operation (`toList`, `reduce` hoặc `collect`) tiêu thụ luồng. Một instance `Stream` chỉ nên tiêu thụ **một lần**; để tạo nhiều báo cáo, như chương trình trên, hãy tạo stream mới từ `paidOrders` mỗi lần. Việc tái sử dụng `List<Order>` làm nguồn cho nhiều stream là bình thường.

Ví dụ cố ý dùng các hàm không có tác dụng phụ: không sửa danh sách nguồn trong `map`/`filter` và không cập nhật một biến `revenue` dùng chung từ bên trong `forEach`. `forEach` chỉ được dùng để **in kết quả ở ranh giới cuối chương trình**. Khi cần thu thập kết quả, ưu tiên `reduce` hoặc `collect` thay vì tự thay đổi trạng thái bên ngoài pipeline.

## 6. Các góc cạnh và lỗi thường gặp

**Đơn rỗng hoặc không có đơn PAID.** `filter(...).toList()` có thể trả danh sách rỗng; `reduce(BigDecimal.ZERO, ...)` cho `0`; `groupingBy` cho map rỗng. Nếu cần báo cáo mọi khách kể cả khách chưa thanh toán, phải bổ sung định nghĩa nghiệp vụ và nguồn khách độc lập. Không tự tạo kết quả cho khách không có dữ liệu.

**Một pipeline có thể duyệt dữ liệu nhiều lần.** Chương trình tạo `paidOrders` một lần rồi sinh ba báo cáo từ đó. `Order.total()` được tính lại lúc sắp xếp, in, tính doanh thu và nhóm; với dữ liệu lớn có thể dùng record trung gian như `record PricedOrder(Order order, BigDecimal total) {}` và biến đổi đơn đã lọc thành danh sách `PricedOrder` để tránh tính tổng lặp lại. Cân nhắc tính dễ hiểu trước khi tối ưu.

**Thứ tự nhóm không phải mặc định.** `groupingBy(classifier)` thường cho `HashMap`, do đó không dựa vào thứ tự lặp mặc định để so sánh stdout. `TreeMap::new` được chọn có chủ đích; nếu cần thứ tự lần xuất hiện, cân nhắc `LinkedHashMap::new` cùng thứ tự stream nguồn có thể dự đoán.

**Phân biệt đơn và dòng hàng.** Gộp số tiền của các đơn (`Order.total()`) là tổng doanh thu đơn hàng. Gộp số lượng dòng hàng (`OrderLine.quantity()`) là tổng số sản phẩm. Dùng `count()` sau `flatMap` chỉ cho số *dòng hàng*, không phải tổng quantity; ví dụ A01 có hai dòng nhưng năm sản phẩm.

**Không so sánh tiền bằng `double`.** `BigDecimal` giúp tính tiền thập phân chính xác theo giá trị đã nhập; nếu tính tỷ lệ thuế/giảm giá hay phép chia không kết thúc, phải định nghĩa `scale` và `RoundingMode` theo yêu cầu nghiệp vụ. `BigDecimal.equals` còn xét scale (`1.0` khác `1.00` theo `equals`), còn `compareTo` so sánh giá trị số; comparator trong bài dùng `compareTo` thông qua `Comparator.comparing`.

**Tránh `null` trong nguồn.** `List.of` không nhận phần tử `null`; `TreeMap` theo thứ tự tự nhiên cũng không chấp nhận khóa `null`. Dữ liệu đi từ API/DB có thể thiếu trường: kiểm tra trước ở ranh giới vào, thống nhất quy tắc loại, báo lỗi hoặc thay thế; không lặng lẽ giả định đơn giá hoặc khách hàng bằng `0`/chuỗi rỗng.

**Không song song hóa vô điều kiện.** `parallelStream()` không đảm bảo nhanh hơn; nó làm tăng chi phí phối hợp và có thể thay đổi thứ tự thực thi tác dụng phụ. Với vài đơn hàng, stream tuần tự dễ giải thích, dễ kiểm chứng hơn. Nếu cần song song hóa, trước tiên phải đảm bảo các hàm không phụ thuộc trạng thái chung, phép tổng hợp phù hợp và đo hiệu năng trên dữ liệu thực.

**Không tái sử dụng một đối tượng Stream đã chạy.** Đoạn sau sai vì gọi hai terminal operation trên cùng một stream:

```java
// Minh họa lỗi: không đặt vào chương trình chạy ở trên.
var paidStream = orders.stream().filter(isPaid);
long count = paidStream.count();
// paidStream.toList(); // IllegalStateException: stream has already been operated upon or closed
```

Cách đúng: lưu kết quả trung gian dưới dạng `paidOrders` hoặc tạo `orders.stream()` mới cho pipeline thứ hai.

## 7. Tự kiểm tra và mở rộng bài toán

1. **Kiểm tra lọc:** bỏ đơn A06 khỏi đầu vào. Khi đó còn 3 đơn PAID; doanh thu tổng phải là `520000`, khách An còn `50000`, SKU BAG còn `1`, BOOK còn `2`.
2. **Kiểm tra lượng hàng:** thêm vào A04 một dòng `PEN × 2 × 10000`. Số lượng PEN thành `10`, doanh thu tổng thành `860000`, khách An thành `390000`; trạng thái và số lượng đơn PAID không thay đổi.
3. **Kiểm tra thứ tự ổn định:** tạo hai đơn có tổng tiền bằng nhau. `thenComparing(Order::id)` phải quyết định thứ tự mã đơn tăng dần trong nhóm cùng tổng tiền.
4. **Kiểm tra rỗng:** đổi mọi trạng thái thành `PENDING`; stdout vẫn có tiêu đề, `Tổng doanh thu: 0`, hai báo cáo nhóm không có dòng dữ liệu.
5. **Mở rộng:** thêm doanh thu theo SKU bằng `flatMap` và `Collectors.reducing(BigDecimal.ZERO, OrderLine::subtotal, BigDecimal::add)`. Phải tự xác định đầu ra chỉ từ các đơn PAID, rồi so lại tổng doanh thu theo SKU với `840000`.

Khi chuyển sang dữ liệu thực, trình tự hợp lý là: xác nhận điều kiện thanh toán và các định nghĩa tiền tệ → chuẩn hóa/kiểm tra các dòng đơn → lọc đúng tập đơn → biến đổi và tổng hợp theo đơn hoặc SKU → kiểm tra tổng số tiền và các số lượng → trình bày kết quả. Nhờ chia công việc thành những hàm rõ ràng, có thể thay nguồn dữ liệu từ `List` sang repository/API mà vẫn giữ được phần lớn logic phân tích, với điều kiện dữ liệu đã được nạp và bảo toàn đúng ngữ nghĩa.