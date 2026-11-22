# Làm phẳng danh sách đơn hàng và chi tiết sản phẩm

Một đơn hàng thường chứa nhiều dòng chi tiết sản phẩm (*order lines*), trong khi một báo cáo doanh thu hoặc tồn kho thường cần xử lý **tất cả dòng sản phẩm của mọi đơn hàng**. Java Stream API cung cấp `flatMap` để chuyển một nguồn có cấu trúc lồng nhau như `List<Order>`, trong đó mỗi `Order` có `List<OrderLine>`, thành một luồng phẳng các dòng chi tiết. Nếu cần biết dòng sản phẩm đến từ đơn nào, ta còn có thể kết hợp `flatMap` với `map` để **giữ thông tin của đơn cha**.

Đây là bài thực hành thuộc chương **Bài tập nền tảng và trung cấp** của module **JAVA_STREAM_API**. Mục tiêu là vận dụng `filter`, `map`, `flatMap` và `collect` để biến đổi dữ liệu thực tế, sau đó tổng hợp theo mã sản phẩm bằng `groupingBy` hoặc `toMap`. Bài cũng luyện cách dùng pipeline lazy, phân biệt số dòng chi tiết với tổng số lượng sản phẩm, xử lý nguồn rỗng/null và tránh tràn số khi tính doanh thu. Các kỹ thuật về collector tùy chỉnh, `Spliterator`, Stream song song và Stream Gatherers là hướng mở rộng, không bắt buộc để giải được phần nền tảng.

## 1. Đề bài và dữ liệu đầu vào

Hệ thống có một danh sách đơn hàng. Mỗi đơn có mã đơn, mã khách hàng và danh sách dòng sản phẩm. Mỗi dòng có mã sản phẩm (SKU), tên sản phẩm, số lượng và đơn giá tính bằng **cents**.

| Đơn hàng | Khách hàng | Các dòng chi tiết |
|---|---|---|
| O1 | C01 | P01: Bàn phím × 2, giá 15.000; P02: Chuột × 1, giá 8.000 |
| O2 | C02 | P01: Bàn phím × 1, giá 15.000; P03: Tai nghe × 3, giá 20.000 |
| O3 | C03 | Danh sách chi tiết rỗng |
| O4 | C04 | Danh sách chi tiết null |
| O5 | C05 | P02: Chuột × 2, giá 8.000 |

Quy tắc của bài:

- Một dòng chi tiết phải có SKU và tên sản phẩm; số lượng nguyên **lớn hơn 0**, đơn giá **không âm**.
- Danh sách chi tiết rỗng hoặc null được coi là **không có dòng sản phẩm** để làm phẳng.
- Phần tử `OrderLine` null trong danh sách được **bỏ qua có chủ đích**.
- Ví dụ sẽ lọc phần tử `Order` null trước khi truy cập thuộc tính. Với ứng dụng thật, có thể chọn chính sách báo lỗi thay vì lọc.
- Phép tính tiền dùng số nguyên ở đơn vị nhỏ nhất: `lineRevenueCents = quantity × unitPriceCents`.

**Yêu cầu thực hành:** từ danh sách đơn hàng, tạo danh sách dòng chi tiết phẳng, tính tổng số lượng và doanh thu, tổng hợp theo SKU, rồi đối chiếu các trường hợp đơn không có chi tiết.

Kết quả mong đợi về mặt nội dung:

| SKU | Tổng số lượng | Tổng doanh thu (cents) |
|---|---:|---:|
| P01 | 3 | 45.000 |
| P02 | 3 | 24.000 |
| P03 | 3 | 60.000 |
| **Tổng** | **9** | **129.000** |

Có **5 dòng chi tiết** được làm phẳng từ **5 đơn hàng**, nhưng số lượng sản phẩm cộng lại là **9**. Hai chỉ số này không giống nhau.

## 2. Nhắc lại map và flatMap: khác nhau ở hình dạng kết quả

Giả sử tồn tại kiểu `Order` với phương thức `getLines()` trả `List<OrderLine>`.

### 2.1. map giữ nguyên số tầng lồng nhau

```java
Stream<List<OrderLine>> nested = orders.stream()
        .map(Order::getLines);
```

`map` biến mỗi `Order` thành **một `List<OrderLine>`**. Kết quả vẫn là luồng các danh sách, không phải luồng các dòng chi tiết.

Nếu mỗi đơn có danh sách chi tiết riêng:

```text
Nguồn:
  Order O1 -> [Line P01, Line P02]
  Order O2 -> [Line P01, Line P03]
  Order O3 -> []

map(Order::getLines):
  Stream<List<OrderLine>>
  [[P01, P02], [P01, P03], []]
```

Nếu cần xử lý từng dòng sản phẩm, còn phải duyệt các danh sách con.

### 2.2. flatMap làm phẳng các Stream con

```java
Stream<OrderLine> flat = orders.stream()
        .flatMap(order -> order.getLines().stream());
```

Mỗi `Order` được ánh xạ thành **một `Stream<OrderLine>`**, sau đó `flatMap` nối nội dung các Stream con thành một luồng duy nhất:

```text
                  Stream<Order>
                  /     |     \
                O1      O2     O3
                 |       |      |
               [P01,   [P01,   []
                P02]    P03]
                  \      |     /
                       flatMap
                         |
       Stream<OrderLine>: P01, P02, P01, P03
```

Đoạn code này chỉ an toàn khi `orders` không có đơn null, `getLines()` không trả null và các dòng sản phẩm phù hợp với xử lý phía sau. Trong dữ liệu bài này có một đơn có danh sách null, nên cần phiên bản **null-safe** ở phần 4.

### 2.3. Bảng so sánh nhanh

| Biểu thức | Kiểu phần tử kết quả | Ý nghĩa |
|---|---|---|
| `orders.stream()` | `Order` | Duyệt từng đơn |
| `orders.stream().map(Order::getLines)` | `List<OrderLine>` | Duyệt từng danh sách chi tiết |
| `orders.stream().map(o -> o.getLines().stream())` | `Stream<OrderLine>` | Luồng chứa những luồng con |
| `orders.stream().flatMap(o -> o.getLines().stream())` | `OrderLine` | Duyệt từng dòng chi tiết |
| `orders.stream().flatMap(o -> o.getLines().stream().map(...))` | Kiểu phần tử do `map(...)` tạo | Dòng chi tiết kèm ngữ cảnh đơn cha |

**Quy tắc:** `map` dùng khi một phần tử đầu vào tạo một giá trị đầu ra; `flatMap` dùng khi một phần tử đầu vào tạo **0, 1 hoặc nhiều giá trị đầu ra** qua một Stream con.

## 3. Bài tập nền tảng: làm phẳng trực tiếp dòng sản phẩm

Khi chỉ cần những thuộc tính đã nằm trong `OrderLine`, pipeline đơn giản là:

```java
List<OrderLine> allLines = orders.stream()
        .filter(Objects::nonNull)
        .flatMap(order -> {
            List<OrderLine> lines = order.getLines();
            return lines == null
                    ? Stream.<OrderLine>empty()
                    : lines.stream();
        })
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
```

Đoạn minh họa giả định các kiểu `Order` và `OrderLine` đã được định nghĩa; các import chính là `java.util.List`, `java.util.Objects`, `java.util.stream.Stream` và `java.util.stream.Collectors`.

Các bước:

1. `orders.stream()`: tạo Stream đơn hàng.
2. `filter(Objects::nonNull)`: loại phần tử đơn null trước khi truy cập getter.
3. `flatMap(...)`: với mỗi đơn, trả luồng dòng sản phẩm; danh sách null thành `Stream.empty()`.
4. `filter(Objects::nonNull)`: bỏ dòng sản phẩm null nếu có.
5. `collect(toList())`: kết thúc pipeline, lấy danh sách các dòng chi tiết.

Với bộ dữ liệu đề bài, danh sách phẳng có **5 phần tử** theo SKU: `[P01, P02, P01, P03, P02]`. Đơn O3 và O4 không tạo ra dòng sản phẩm nào.

### 3.1. Đơn không có chi tiết không phải lỗi của flatMap

`Stream.empty()` biểu diễn một đơn đóng góp **0 dòng**; `flatMap` xử lý việc đó một cách tự nhiên. Nếu sau này cần biết đơn nào không có chi tiết, đừng suy ra từ danh sách phẳng rằng **chúng chưa từng tồn tại**: việc làm phẳng đã bỏ thông tin về các đơn không phát ra phần tử con.

### 3.2. Một dòng chi tiết khác một đơn vị hàng hóa

Giả sử dòng P01 trong O1 có `quantity = 2`. Sau `flatMap`, nó vẫn là **một `OrderLine`**, chứ không tự nhân thành hai phần tử P01.

```java
long numberOfRows = allLines.stream().count();

long numberOfUnits = allLines.stream()
        .mapToLong(line -> line.getQuantity())
        .sum();
```

Khi số lượng là thuộc tính của dòng, tính tổng bằng `sum` hoặc collector; không nhân bản dòng theo số lượng trừ khi bài toán thực sự cần xử lý từng đơn vị vật lý.

## 4. Bài tập trung cấp: giữ thông tin đơn hàng khi làm phẳng

Sau khi làm phẳng trực tiếp thành `Stream<OrderLine>`, ta **không tự động còn biết** dòng đó thuộc đơn nào nếu `OrderLine` không lưu mã đơn. Vì vậy, với các báo cáo cần `orderId` hoặc `customerId`, hãy tạo một đối tượng biểu diễn dòng chi tiết **kèm ngữ cảnh đơn cha**:

```java
static Stream<LineView> flattenOneOrder(Order order) {
    List<OrderLine> lines = order.getLines();
    if (lines == null) {
        return Stream.empty();
    }
    return lines.stream()
            .filter(Objects::nonNull)
            .map(line -> new LineView(order, line));
}

Stream<LineView> views = orders.stream()
        .filter(Objects::nonNull)
        .flatMap(MyClass::flattenOneOrder);
```

Ở đây `MyClass` đại diện cho lớp chứa phương thức; ví dụ hoàn chỉnh ở phần 5 dùng tên `OrderLineFlatteningDemo`. `LineView` là một đối tượng kết quả có thể chứa:

```text
orderId
customerId
sku
productName
quantity
unitPriceCents
lineRevenueCents
```

Nhờ đó, mỗi dòng biết **đơn cha** và **thuộc tính chi tiết**, hỗ trợ nhóm theo khách hàng, mã đơn hoặc mã sản phẩm mà không phải tìm ngược dữ liệu.

### 4.1. Phân biệt hai vị trí của map

```java
orders.stream()
        .map(Order::getLines)
        .flatMap(List::stream);
```

Pipeline trên làm phẳng nhưng **đánh mất ngữ cảnh của Order** sau bước `map(Order::getLines)`. Nó cũng không an toàn nếu có danh sách con null.

Ngược lại:

```java
orders.stream()
        .flatMap(order -> order.getLines().stream()
                .map(line -> new LineView(order, line)));
```

Pipeline thứ hai tạo `LineView` **khi còn truy cập được `order`** qua lambda bên ngoài. Đây là kỹ thuật quan trọng trong các bài toán dữ liệu cha–con. Đoạn minh họa giả định danh sách con không null; hãy dùng phiên bản bảo vệ null khi xử lý dữ liệu của đề.

## 5. Chương trình Java 8 hoàn chỉnh

Chương trình sau có thể lưu thành `OrderLineFlatteningDemo.java` và chạy bằng JDK 8 trở lên. Nó tạo đủ bộ dữ liệu đề bài, làm phẳng để lấy các dòng có ngữ cảnh, thu thập thành `Map` theo SKU, tính tổng số lượng/doanh thu và đếm số dòng theo từng đơn.

Để tránh kết quả tiền tệ sai âm thầm khi nhân/cộng số nguyên, ví dụ dùng `Math.multiplyExact` và `Math.addExact`. Mã giả định tiền tệ đồng nhất, dữ liệu được tạo qua constructor hợp lệ; đây là cách dạy tính toán an toàn hơn việc dùng `double` cho số tiền.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class OrderLineFlatteningDemo {

    static final class OrderLine {
        private final String sku;
        private final String productName;
        private final int quantity;
        private final long unitPriceCents;

        OrderLine(String sku, String productName,
                int quantity, long unitPriceCents) {
            this.sku = Objects.requireNonNull(sku, "sku");
            this.productName = Objects.requireNonNull(
                    productName, "productName");
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity phải lớn hơn 0");
            }
            if (unitPriceCents < 0) {
                throw new IllegalArgumentException(
                        "unitPriceCents không được âm");
            }
            this.quantity = quantity;
            this.unitPriceCents = unitPriceCents;
        }

        String getSku() { return sku; }
        String getProductName() { return productName; }
        int getQuantity() { return quantity; }
        long getUnitPriceCents() { return unitPriceCents; }

        long getRevenueCents() {
            return Math.multiplyExact(
                    (long) quantity, unitPriceCents);
        }
    }

    static final class Order {
        private final String id;
        private final String customerId;
        private final List<OrderLine> lines;

        Order(String id, String customerId, List<OrderLine> lines) {
            this.id = Objects.requireNonNull(id, "id");
            this.customerId = Objects.requireNonNull(
                    customerId, "customerId");
            // Cho phép danh sách null để minh họa chính sách dữ liệu thiếu.
            this.lines = lines == null
                    ? null
                    : Collections.unmodifiableList(
                            new ArrayList<>(lines));
        }

        String getId() { return id; }
        String getCustomerId() { return customerId; }
        List<OrderLine> getLines() { return lines; }
    }

    // Một dòng chi tiết đã giữ được thông tin từ đơn hàng cha.
    static final class LineView {
        private final String orderId;
        private final String customerId;
        private final String sku;
        private final String productName;
        private final int quantity;
        private final long unitPriceCents;
        private final long lineRevenueCents;

        LineView(Order order, OrderLine line) {
            this.orderId = order.getId();
            this.customerId = order.getCustomerId();
            this.sku = line.getSku();
            this.productName = line.getProductName();
            this.quantity = line.getQuantity();
            this.unitPriceCents = line.getUnitPriceCents();
            this.lineRevenueCents = line.getRevenueCents();
        }

        String getOrderId() { return orderId; }
        String getCustomerId() { return customerId; }
        String getSku() { return sku; }
        String getProductName() { return productName; }
        int getQuantity() { return quantity; }
        long getUnitPriceCents() { return unitPriceCents; }
        long getLineRevenueCents() { return lineRevenueCents; }
    }

    // Trạng thái kết quả bất biến cho mỗi SKU.
    static final class ProductTotals {
        private final long quantity;
        private final long revenueCents;

        ProductTotals(long quantity, long revenueCents) {
            this.quantity = quantity;
            this.revenueCents = revenueCents;
        }

        static ProductTotals from(LineView view) {
            return new ProductTotals(
                    view.getQuantity(), view.getLineRevenueCents());
        }

        ProductTotals combine(ProductTotals other) {
            return new ProductTotals(
                    Math.addExact(quantity, other.quantity),
                    Math.addExact(revenueCents, other.revenueCents));
        }

        long getQuantity() { return quantity; }
        long getRevenueCents() { return revenueCents; }
    }

    // Một lần gọi tạo một pipeline mới; có thể dùng lại List nguồn.
    static Stream<LineView> flatten(List<Order> orders) {
        Objects.requireNonNull(orders, "orders");
        return orders.stream()
                .filter(Objects::nonNull)
                .flatMap(order -> {
                    List<OrderLine> lines = order.getLines();
                    Stream<OrderLine> children = lines == null
                            ? Stream.empty()
                            : lines.stream();
                    return children
                            .filter(Objects::nonNull)
                            .map(line -> new LineView(order, line));
                });
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("O1", "C01", Arrays.asList(
                        new OrderLine("P01", "Bàn phím", 2, 15_000L),
                        new OrderLine("P02", "Chuột", 1, 8_000L))),
                new Order("O2", "C02", Arrays.asList(
                        new OrderLine("P01", "Bàn phím", 1, 15_000L),
                        new OrderLine("P03", "Tai nghe", 3, 20_000L))),
                new Order("O3", "C03", Collections.emptyList()),
                new Order("O4", "C04", null),
                new Order("O5", "C05", Arrays.asList(
                        new OrderLine("P02", "Chuột", 2, 8_000L)))
        );

        // A. Xem từng dòng đã làm phẳng theo encounter order.
        List<LineView> rows = flatten(orders)
                .collect(Collectors.toList());

        System.out.println("Số dòng chi tiết: " + rows.size());
        // 5

        rows.forEach(view -> System.out.println(
                view.getOrderId() + " | "
                + view.getSku() + " | "
                + view.getQuantity() + " | "
                + view.getLineRevenueCents()));
        // O1 | P01 | 2 | 30000
        // O1 | P02 | 1 | 8000
        // O2 | P01 | 1 | 15000
        // O2 | P03 | 3 | 60000
        // O5 | P02 | 2 | 16000

        // B. Gộp theo SKU với toMap và hàm merge.
        Map<String, ProductTotals> bySku = flatten(orders)
                .collect(Collectors.toMap(
                        LineView::getSku,
                        ProductTotals::from,
                        ProductTotals::combine,
                        TreeMap::new));

        bySku.forEach((sku, totals) ->
                System.out.println(
                        sku + " -> quantity="
                        + totals.getQuantity()
                        + ", revenue="
                        + totals.getRevenueCents()));
        // P01 -> quantity=3, revenue=45000
        // P02 -> quantity=3, revenue=24000
        // P03 -> quantity=3, revenue=60000

        // C. Tính tổng số lượng và doanh thu từ các dòng.
        long totalUnits = flatten(orders)
                .mapToLong(view -> view.getQuantity())
                .reduce(0L, Math::addExact);
        long totalRevenue = flatten(orders)
                .mapToLong(LineView::getLineRevenueCents)
                .reduce(0L, Math::addExact);

        System.out.println("Tổng số lượng: " + totalUnits); // 9
        System.out.println("Tổng doanh thu: " + totalRevenue); // 129000

        // D. Đếm số dòng chi tiết của từng đơn.
        Map<String, Long> rowsByOrder = flatten(orders)
                .collect(Collectors.groupingBy(
                        LineView::getOrderId,
                        TreeMap::new,
                        Collectors.counting()));

        System.out.println(rowsByOrder);
        // {O1=2, O2=2, O5=1}; O3 và O4 không có dòng chi tiết.
        System.out.println(rowsByOrder.containsKey("O3")); // false
    }
}
```

### 5.1. Tại sao chương trình tạo nhiều Stream?

Các lời gọi `flatten(orders)` đều tạo **một đối tượng Stream mới** từ cùng `List<Order>`. Mỗi Stream chỉ được tiêu thụ một lần. Trong chương trình minh họa, việc duyệt lại List là hợp lệ và giúp quan sát riêng từng phép toán.

Nếu dữ liệu nguồn lớn hoặc chỉ được duyệt một lần, hãy **chọn chỉ số thực sự cần**, rồi tích lũy chúng trong cùng collector thay vì tạo nhiều pipeline. Ở đây, ví dụ nhóm SKU có thể thu thập trực tiếp từ `flatten(orders)` mà **không** phải tạo `rows` trước; `rows` chỉ dùng để xem kết quả phẳng.

### 5.2. Vì sao TreeMap xuất hiện trong toMap?

Overload bốn tham số:

```java
Collectors.toMap(
        keyMapper,
        valueMapper,
        mergeFunction,
        mapSupplier)
```

`TreeMap::new` yêu cầu Map kết quả duyệt khóa theo thứ tự tự nhiên của SKU. Nó không quyết định cách cộng số lượng/doanh thu và cũng không tự bảo vệ một hàm merge sai. Nếu không cần thứ tự khóa, có thể dùng overload ba tham số và không dựa vào thứ tự duyệt của Map mặc định.

### 5.3. Vì sao cần hàm merge?

Trong dữ liệu, P01 nằm ở O1 và O2, còn P02 nằm ở O1 và O5. Nếu viết `toMap(LineView::getSku, ProductTotals::from)` mà không truyền merge, sẽ xuất hiện khóa trùng và `Collectors.toMap` ném `IllegalStateException`.

`ProductTotals::combine` gộp cả **số lượng** và **doanh thu**. Phép cộng số nguyên phù hợp với việc chia nguồn thành nhiều nhánh khi không bị tràn; ví dụ dùng `Math.addExact` để phát hiện vượt phạm vi `long`.

## 6. Cách tổng hợp khác: groupingBy và các downstream collector

Không phải mọi báo cáo đều cần tự định nghĩa lớp `ProductTotals`. Nếu chỉ cần **tổng số lượng** theo SKU:

```java
Map<String, Long> unitsBySku = flatten(orders)
        .collect(Collectors.groupingBy(
                LineView::getSku,
                TreeMap::new,
                Collectors.summingLong(
                        view -> view.getQuantity())));

System.out.println(unitsBySku);
// {P01=3, P02=3, P03=3}
```

Nếu chỉ cần **doanh thu** theo SKU:

```java
Map<String, Long> revenueBySku = flatten(orders)
        .collect(Collectors.groupingBy(
                LineView::getSku,
                TreeMap::new,
                Collectors.summingLong(
                        LineView::getLineRevenueCents)));
// P01=45000, P02=24000, P03=60000
```

`Collectors.summingLong` diễn đạt phép tính rõ ràng nhưng không tự phát hiện tràn `long`. Trong ví dụ hoàn chỉnh, `Math.addExact` được sử dụng khi kết hợp kết quả để phát hiện tràn. Nếu ứng dụng yêu cầu tổng chính xác vượt phạm vi `long`, cần cân nhắc `BigInteger` hoặc `BigDecimal`, không chỉ đổi collector.

### 6.1. Đếm số dòng chi tiết theo SKU

```java
Map<String, Long> lineCountBySku = flatten(orders)
        .collect(Collectors.groupingBy(
                LineView::getSku,
                Collectors.counting()));
```

Với dữ liệu mẫu, P01 xuất hiện ở **2 dòng**, P02 cũng **2 dòng**, P03 **1 dòng**. Chỉ số này **khác tổng số lượng**: P03 một dòng nhưng `quantity = 3`.

### 6.2. Liệt kê các đơn có chứa một SKU

```java
Map<String, java.util.Set<String>> orderIdsBySku =
        flatten(orders).collect(Collectors.groupingBy(
                LineView::getSku,
                Collectors.mapping(
                        LineView::getOrderId,
                        Collectors.toSet())));
```

Với P01, tập mã đơn có nội dung `{O1, O2}`. `toSet` loại mã trùng nếu cùng một đơn có nhiều dòng cùng SKU, nhưng **không cam kết thứ tự duyệt**. Nếu cần giữ thứ tự xuất hiện và không trùng lặp, cân nhắc `toCollection(LinkedHashSet::new)` với nguồn có encounter order.

## 7. Làm phẳng trước hay nhóm trước?

Đây là khác biệt trung cấp thường ảnh hưởng trực tiếp đến báo cáo.

### 7.1. Làm phẳng trước rồi groupingBy

```java
Map<String, Long> linesPerOrder = flatten(orders)
        .collect(Collectors.groupingBy(
                LineView::getOrderId,
                Collectors.counting()));
```

O3 và O4 **không có khóa** trong kết quả vì không phát ra bất kỳ `LineView` nào. Điều đó **không có nghĩa không tồn tại đơn hàng O3/O4**.

### 7.2. Nhóm theo đơn hàng cha để giữ đơn rỗng (Java 8)

Nếu cần báo cáo số dòng của **mọi đơn**, kể cả đơn có chi tiết rỗng, hãy đếm trên chính `Order`:

```java
Map<String, Long> linesPerOrderIncludingEmpty =
        orders.stream()
                .filter(Objects::nonNull)
                .collect(Collectors.groupingBy(
                        Order::getId,
                        TreeMap::new,
                        Collectors.summingLong(order -> {
                            List<OrderLine> lines = order.getLines();
                            return lines == null
                                    ? 0L
                                    : lines.stream()
                                            .filter(Objects::nonNull)
                                            .count();
                        })));

System.out.println(linesPerOrderIncludingEmpty);
// {O1=2, O2=2, O3=0, O4=0, O5=1}
```

Nếu hệ thống có mã đơn trùng, collector `groupingBy` ở đây sẽ cộng số dòng của những bản ghi mang cùng mã; cần xác định đó có phải hành vi mong muốn hay không. Trong đề, mỗi mã đơn là duy nhất.

### 7.3. Nhóm cha và flatMapping downstream (Java 9+)

Từ Java 9, `Collectors.flatMapping` cho phép làm phẳng **bên trong một nhóm đã được tạo**:

```java
Map<String, Long> counts = orders.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.groupingBy(
                Order::getId,
                TreeMap::new,
                Collectors.flatMapping(
                        order -> order.getLines() == null
                                ? Stream.<OrderLine>empty()
                                : order.getLines().stream()
                                        .filter(Objects::nonNull),
                        Collectors.counting())));

// {O1=2, O2=2, O3=0, O4=0, O5=1}
```

Khác với `Stream.flatMap` trước `groupingBy`, downstream `flatMapping` không loại bỏ đơn cha trước khi phân nhóm. Khi đơn cha tồn tại nhưng không có dòng chi tiết, nhóm vẫn có giá trị đếm bằng 0.

**Lưu ý phiên bản:** `Stream.flatMap` có từ Java 8, còn `Collectors.flatMapping` có từ **Java 9**. Chương trình hoàn chỉnh ở phần 5 chỉ yêu cầu Java 8.

## 8. Lọc ở tầng đơn và tầng dòng: hai ý nghĩa khác nhau

Trong một dữ liệu lồng nhau, đặt `filter` ở đâu cũng có ý nghĩa riêng.

### 8.1. Lọc đơn hàng trước khi làm phẳng

Ví dụ chỉ xét đơn của khách C01:

```java
List<LineView> fromC01 = orders.stream()
        .filter(Objects::nonNull)
        .filter(order -> "C01".equals(order.getCustomerId()))
        .flatMap(order -> {
            List<OrderLine> lines = order.getLines();
            return (lines == null
                    ? Stream.<OrderLine>empty()
                    : lines.stream().filter(Objects::nonNull))
                    .map(line -> new LineView(order, line));
        })
        .collect(Collectors.toList());

System.out.println(fromC01.size()); // 2
```

Việc lọc trên đối tượng cha giúp bỏ toàn bộ các dòng của những đơn không phù hợp **trước** khi đọc danh sách con.

### 8.2. Lọc dòng sản phẩm sau khi làm phẳng

Ví dụ chỉ lấy các dòng SKU P01, không phụ thuộc khách hàng:

```java
List<LineView> keyboardLines = flatten(orders)
        .filter(view -> "P01".equals(view.getSku()))
        .collect(Collectors.toList());

System.out.println(keyboardLines.size()); // 2
```

Nếu một điều kiện cần cả thông tin đơn và dòng, `LineView` cho phép viết trực tiếp:

```java
List<LineView> selected = flatten(orders)
        .filter(view -> "C02".equals(view.getCustomerId())
                && view.getQuantity() >= 2)
        .collect(Collectors.toList());
// Chỉ dòng P03 của O2.
```

Để tránh quét chi tiết không cần thiết trong hệ thống lớn, ưu tiên lọc sớm ở tầng dữ liệu mà predicate có thể đánh giá chính xác. Tuy nhiên, đừng đẩy điều kiện về tầng cha nếu điều kiện thực sự thuộc từng dòng con.

## 9. Thứ tự, trùng lặp và distinct

`List<Order>` giữ encounter order theo vị trí đơn; `List<OrderLine>` trong mỗi đơn cũng có thứ tự. Với pipeline tuần tự:

```java
List<String> skus = flatten(orders)
        .map(LineView::getSku)
        .collect(Collectors.toList());

System.out.println(skus);
// [P01, P02, P01, P03, P02]
```

`flatMap` phát các dòng theo thứ tự của từng danh sách con khi nguồn và danh sách con có thứ tự. Với parallel stream có nguồn có thứ tự, `collect(toList())` vẫn giữ encounter order của kết quả, dù các bước trung gian có thể được xử lý bởi nhiều worker.

### 9.1. Lấy các mã SKU phân biệt

```java
List<String> distinctSkus = flatten(orders)
        .map(LineView::getSku)
        .distinct()
        .collect(Collectors.toList());

System.out.println(distinctSkus); // [P01, P02, P03]
```

Không nên gọi `distinct()` trực tiếp trên `LineView` và mong nó tự deduplicate theo SKU. Nếu `LineView` không định nghĩa `equals`/`hashCode` theo quy tắc nghiệp vụ, các đối tượng khác nhau có thể vẫn được coi là khác nhau. Trong ví dụ, ta chuyển thành `String sku` **trước** khi gọi `distinct`.

### 9.2. Trùng SKU không phải bản ghi thừa

P01 xuất hiện trong hai đơn là dữ liệu hợp lệ: số lượng và doanh thu cần được **cộng gộp**, không được bỏ một dòng bằng `distinct`. Chỉ dùng `distinct` khi mục tiêu thực sự là danh sách mã sản phẩm phân biệt hoặc một báo cáo có quy tắc dedup cụ thể.

### 9.3. forEach và forEachOrdered khi song song

```java
flatten(orders)
        .parallel()
        .map(LineView::getSku)
        .forEachOrdered(System.out::println);
```

`forEachOrdered` giữ thứ tự hành động theo encounter order của nguồn. Nếu dùng `forEach` trên parallel stream, thứ tự in không được bảo đảm. Không dùng `forEach` để thêm dữ liệu vào một `ArrayList` bên ngoài khi nhiều worker có thể cùng sửa danh sách ấy; `collect(toList())` an toàn và đúng mục đích hơn.

## 10. Dữ liệu null, lỗi nghiệp vụ và chính sách rõ ràng

Có ít nhất ba loại null cần phân biệt:

| Trường hợp | Hành vi của ví dụ | Phương án khác theo nghiệp vụ |
|---|---|---|
| Phần tử `Order` là null | Lọc bằng `Objects::nonNull` | Ném lỗi và ghi nhận nguồn dữ liệu không hợp lệ |
| `order.getLines() == null` | Trả `Stream.empty()` | Phân biệt “chưa tải chi tiết” với “thực sự không có chi tiết” |
| Một phần tử `OrderLine` là null | Lọc khỏi Stream con | Báo dữ liệu thiếu hoặc đếm số dòng hỏng |
| SKU hoặc tên sản phẩm null | Constructor từ chối | Chuẩn hóa/đối chiếu nguồn trước khi collect |
| Số lượng không dương | Constructor từ chối | Hỗ trợ dòng trả hàng bằng kiểu giao dịch riêng |
| Đơn giá âm | Constructor từ chối | Mô hình hóa giảm giá/điều chỉnh bằng quy tắc riêng |

**Điểm quan trọng:** nếu null trong danh sách chi tiết có nghĩa **dữ liệu chưa được tải** thay vì “danh sách thực sự rỗng”, việc đổi null thành `Stream.empty()` sẽ làm báo cáo thiếu dữ liệu một cách im lặng. Quy tắc của đề cho phép cách xử lý này; ứng dụng thực tế phải chọn theo nghiệp vụ.

### 10.1. Stream con rỗng không tạo phần tử null

`Stream.empty()` là Stream có **0 phần tử**. Nó khác với `Stream.of((OrderLine) null)`, vốn chứa **một phần tử null**. Không thể dựa vào việc dùng `flatMap` để tự động loại mọi phần tử null trong các danh sách con.

### 10.2. Tràn số khi tính tiền

Không viết:

```java
int revenue = line.getQuantity()
        * (int) line.getUnitPriceCents();
// Dễ tràn hoặc mất dữ liệu khi ép về int.
```

Trong ví dụ hoàn chỉnh, lượng hàng `int` được chuyển sang `long` rồi nhân:

```java
long revenue = Math.multiplyExact(
        (long) line.getQuantity(),
        line.getUnitPriceCents());
```

Nếu kết quả không thể biểu diễn bằng `long`, `Math.multiplyExact` ném `ArithmeticException` thay vì trả doanh thu sai. Khi cộng tổng, dùng `Math.addExact` giúp phát hiện tổng tràn.

Đơn giá và doanh thu cùng tính bằng **cents**. Khi hiển thị tiền với dấu thập phân, nên chuyển đổi và làm tròn theo quy tắc tiền tệ rõ ràng; `double` không phải lựa chọn mặc định cho tính toán chính xác về tiền.

## 11. Độ phức tạp, bộ nhớ và nguồn dữ liệu lớn

Giả sử có `N` đơn hàng và tổng cộng `M` dòng chi tiết. Một phép duyệt `flatMap` về cơ bản cần đi qua từng đơn và từng dòng con: chi phí thường tương ứng `O(N + M)`, chưa tính chi phí của thao tác tổng hợp phía sau.

- `collect(toList())` lưu toàn bộ `M` dòng trong bộ nhớ, vì vậy bộ nhớ tăng theo số dòng.
- `groupingBy` hoặc `toMap` cộng dồn theo SKU chỉ cần bộ nhớ tỷ lệ theo **số SKU phân biệt** (và trạng thái tính toán), nếu không giữ từng dòng.
- Nếu cần nhóm thành `List<LineView>` theo SKU, tổng bộ nhớ cho dữ liệu vẫn tăng theo số dòng.
- Nếu nguồn là `Files.lines` hoặc nguồn I/O khác, phải quản lý Stream nguồn bằng `try-with-resources`; `collect` không tự đảm bảo đóng file.

Ví dụ không vật chất hóa toàn bộ danh sách `LineView`:

```java
Map<String, ProductTotals> report = flatten(orders)
        .collect(Collectors.toMap(
                LineView::getSku,
                ProductTotals::from,
                ProductTotals::combine));
```

Đây vẫn là một lần duyệt `flatten(orders)`, nhưng không tạo danh sách `rows` trung gian. Với sản phẩm có cùng SKU, hàm merge cần **kết hợp nhóm** để kết quả có ý nghĩa khi dữ liệu được chia thành nhiều nhánh.

### 11.1. Có nên bật parallelStream?

Chỉ thêm `parallel()` không bảo đảm nhanh hơn. Cần xem xét:

1. Nguồn có thể chia hiệu quả hay không.
2. Lambda có tránh trạng thái mutable dùng chung và can thiệp vào nguồn hay không.
3. Hàm merge/collector có thỏa hợp đồng **đơn vị, kết hợp và tương đương** hay không.
4. Có ràng buộc thứ tự, chi phí tạo đối tượng `LineView` hoặc tranh chấp tài nguyên hay không.
5. Kích thước và chi phí xử lý thực tế có đủ lớn để bù overhead song song hay không.

Với `List` và các đối tượng bất biến trong ví dụ, phép `ProductTotals::combine` dùng cộng số nguyên kiểm tra tràn, có tính kết hợp về kết quả số học trong miền dữ liệu hợp lệ. Do đó có thể nghiên cứu xử lý song song, nhưng với bộ dữ liệu năm đơn hàng, không có lý do hiệu năng để mặc định bật `parallel()`.

## 12. Những lỗi phổ biến

| Cách làm dễ sai | Hậu quả | Cách sửa |
|---|---|---|
| Dùng `map(Order::getLines)` rồi mong ra `OrderLine` | Vẫn là `Stream<List<OrderLine>>` | Dùng `flatMap` |
| `order.getLines().stream()` khi danh sách null | `NullPointerException` | Trả `Stream.empty()` hoặc xử lý dữ liệu thiếu |
| Làm phẳng xong mới tìm `orderId` trên một `OrderLine` không chứa mã đơn | Mất quan hệ đơn cha | Tạo `LineView(order, line)` bên trong lambda của `flatMap` |
| Dùng `count()` trên dòng để tính tổng số lượng | Đếm số dòng, không cộng quantity | `mapToLong(LineView::getQuantity).sum()` |
| Dùng `distinct()` trên dòng để tính doanh thu | Có thể bỏ giao dịch hợp lệ | Gộp bằng `groupingBy`/`toMap` theo SKU |
| Dùng `toMap` không có merge khi SKU lặp | `IllegalStateException` | Chọn hàm cộng số lượng/doanh thu |
| Chỉ cộng số lượng mà quên doanh thu trong merge | Báo cáo sai | Gộp mọi chỉ số trong `ProductTotals` |
| Dùng `int` cho phép nhân số lượng × đơn giá lớn | Tràn số | Dùng `long` và `Math.multiplyExact` |
| Đơn O3/O4 mất khỏi `groupingBy` sau khi đã làm phẳng | Không có dòng để phát ra khóa | Nhóm trên `Order` hoặc dùng downstream `flatMapping` (Java 9+) |
| Dùng `parallel().forEach(list::add)` với `ArrayList` chung | Race khi nhiều worker cùng sửa | `collect(toList())` hoặc collector thích hợp |
| Dùng lại một Stream sau terminal operation | `IllegalStateException` | Tạo Stream mới từ nguồn có thể duyệt lại |

## 13. Bộ bài tập vận dụng có đáp án

### Bài 1. Dự đoán đầu ra sau flatMap

Với O1 có hai dòng, O2 có hai dòng, O3 rỗng, O4 null và O5 có một dòng, `flatten(orders).count()` trả bao nhiêu?

**Đáp án:** `5L`. Các đơn O3 và O4 không đóng góp dòng nào; đếm trên Stream phẳng là đếm **dòng sản phẩm**, không đếm số đơn.

### Bài 2. Tổng số lượng sản phẩm

Viết pipeline tính tổng `quantity` của mọi dòng hợp lệ.

```java
long units = flatten(orders)
        .mapToLong(view -> view.getQuantity())
        .sum();
```

**Đáp án:** `9L`. P01 có 3, P02 có 3 và P03 có 3 đơn vị.

### Bài 3. Tổng doanh thu của SKU P02

Viết pipeline chỉ chọn P02 rồi cộng doanh thu từ các dòng chứa mã này.

```java
long mouseRevenue = flatten(orders)
        .filter(view -> "P02".equals(view.getSku()))
        .mapToLong(LineView::getLineRevenueCents)
        .sum();
```

**Đáp án:** `24_000L` từ O1 (8.000) và O5 (16.000). Trong ứng dụng cần phát hiện tràn số khi cộng, thay `sum()` bằng `reduce(0L, Math::addExact)`.

### Bài 4. Tìm các SKU phân biệt

```java
List<String> unique = flatten(orders)
        .map(LineView::getSku)
        .distinct()
        .collect(Collectors.toList());
```

**Đáp án:** `[P01, P02, P03]` với nguồn List và pipeline có thứ tự. `distinct` trên mã SKU không làm mất dữ liệu giao dịch vì kết quả bài này chỉ yêu cầu **tập mã phân biệt**.

### Bài 5. Đếm số dòng kể cả đơn rỗng

`groupingBy(LineView::getOrderId, counting())` sau `flatten` có khóa O3 và O4 không?

**Đáp án:** Không. Muốn `O3=0` và `O4=0`, phải tổng hợp từ tầng `Order` hoặc dùng `Collectors.flatMapping` **bên trong** `groupingBy(Order::getId, ...)` từ Java 9. Ví dụ Java 8 đã trình bày ở phần 7.2.

### Bài 6. Tính doanh thu theo khách hàng

Thay vì nhóm theo SKU, hãy nhóm theo `customerId`.

```java
Map<String, Long> revenueByCustomer = flatten(orders)
        .collect(Collectors.groupingBy(
                LineView::getCustomerId,
                TreeMap::new,
                Collectors.summingLong(
                        LineView::getLineRevenueCents)));
```

**Đáp án:** `{C01=38000, C02=75000, C05=16000}`. Khách C03 và C04 không có dòng chi tiết nên không xuất hiện trong Map này. Với số tiền có thể vượt `long`, cần thiết kế phép cộng kiểm tra tràn.

### Bài 7. Vì sao toMap cần mergeFunction?

Đề xuất mã sau có hợp lệ khi dữ liệu gồm nhiều đơn chứa cùng SKU?

```java
Map<String, Long> quantities = flatten(orders)
        .collect(Collectors.toMap(
                LineView::getSku,
                view -> (long) view.getQuantity()));
```

**Đáp án:** Không phù hợp với nguồn đã cho vì SKU trùng; overload này ném `IllegalStateException` khi có khóa trùng. Viết:

```java
Map<String, Long> quantities = flatten(orders)
        .collect(Collectors.toMap(
                LineView::getSku,
                view -> (long) view.getQuantity(),
                Math::addExact));
// P01=3, P02=3, P03=3
```

### Bài 8. Giữ đơn cha và xử lý danh sách chưa tải

Nếu `getLines() == null` thực sự có nghĩa “chưa truy vấn chi tiết từ hệ thống”, có nên im lặng coi nó là danh sách rỗng trong báo cáo doanh thu không?

**Đáp án:** Không nên nếu nghiệp vụ đòi hỏi báo cáo đầy đủ. Cần báo lỗi, tải dữ liệu trước hoặc ghi nhận trạng thái thiếu dữ liệu riêng. `Stream.empty()` chỉ là một quyết định kỹ thuật; **ý nghĩa nghiệp vụ của null phải được xác định trước**.

## 14. Bài tập mở rộng: tự thiết kế báo cáo sản phẩm

Sau khi chạy được chương trình mẫu, hãy mở rộng `ProductTotals` thành một báo cáo chứa:

1. `sku` và `productName` đại diện.
2. Tổng số lượng đã bán.
3. Tổng doanh thu.
4. Số đơn khác nhau có chứa SKU.
5. Tập mã khách hàng đã mua SKU.

**Gợi ý thiết kế:**

- Tổng số lượng và doanh thu gộp bằng phép cộng.
- Số đơn khác nhau cần gộp các **tập mã đơn** rồi lấy kích thước, không chỉ cộng số dòng: một đơn có thể có nhiều dòng cùng SKU.
- Tập khách hàng có thể thu thập bằng `Collectors.mapping(LineView::getCustomerId, toSet())` khi `groupingBy` theo SKU.
- Nếu muốn mọi chỉ số trong **một kết quả theo SKU**, cân nhắc một Collector tùy biến lưu cả tổng số lượng, tổng tiền, tập orderId và tập customerId, với combiner gộp đủ các trạng thái.
- Không dùng một `HashSet` hoặc `HashMap` chung bên ngoài và tự cập nhật bằng `parallelStream().forEach(...)`.

Phiên bản nền tảng có thể làm bằng nhiều collector riêng trên một `List`; phiên bản nâng cao có thể tạo một accumulator riêng khi yêu cầu một lần duyệt và có khả năng xử lý song song.

## 15. Checklist trước khi hoàn thành bài

Hãy tự kiểm tra:

1. `map` và `flatMap` tạo ra **hình dạng Stream** khác nhau thế nào?
2. Đơn có danh sách rỗng/null đóng góp bao nhiêu dòng sau `flatMap`?
3. Làm thế nào để giữ `orderId` và `customerId` khi dòng con không có các trường đó?
4. Đã phân biệt **số dòng**, **tổng quantity** và **số SKU phân biệt** chưa?
5. Nếu khóa SKU trùng trong `toMap`, mergeFunction gộp đủ số lượng/doanh thu không?
6. Có cần giữ những đơn không có chi tiết trong báo cáo theo đơn không?
7. Dữ liệu null, số lượng không hợp lệ, đơn giá âm hoặc tràn số được xử lý theo quy tắc nào?
8. Nếu dữ liệu lớn, có thật sự cần lưu toàn bộ `LineView` vào `List` trước khi tổng hợp không?
9. Nếu dùng Stream song song, các lambda và collector có tránh mutable shared state và giữ đúng encounter order khi cần không?

**Kết luận:** `flatMap` là công cụ cốt lõi để chuyển `List<Order>` chứa các `List<OrderLine>` thành một luồng dòng chi tiết có thể lọc và tổng hợp. Muốn báo cáo còn biết dòng nào thuộc đơn hoặc khách hàng nào, hãy tạo đối tượng kết quả ngay trong lambda đang giữ tham chiếu `Order`. Sau khi làm phẳng, chọn `groupingBy` hoặc `toMap` theo yêu cầu, xác định rõ đơn vị đếm, chính sách với nhóm rỗng, quy tắc trùng SKU và phép tính tiền an toàn. Đó là nền tảng để tiếp tục xây dựng những pipeline phân tích đơn hàng phức tạp hơn bằng Java Stream API.
