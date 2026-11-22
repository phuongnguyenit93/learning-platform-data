# Xây dựng báo cáo bán hàng với kiểm thử tính đúng và thứ tự

> **Chương:** Bài tập nâng cao và dự án  
> **Module:** `JAVA_STREAM_API` — xử lý dữ liệu khai báo bằng Java Stream API qua pipeline lazy, `filter`, `map`, `reduce`, `collect`; vận dụng grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và hiểu giới hạn về trạng thái, tài nguyên, hiệu năng.

Một báo cáo bán hàng có thể nhìn rất đơn giản: tổng doanh thu, số đơn, số sản phẩm bán ra và danh sách mặt hàng bán chạy. Nhưng triển khai đúng phải trả lời thêm các câu hỏi: **đơn hủy có được tính không, tiền có bị sai số không, dữ liệu cùng mã được gộp ra sao, và nếu doanh thu bằng nhau thì thứ tự xếp hạng được quyết định bằng gì?**

Bài thực hành này đi từ yêu cầu nghiệp vụ, mô hình dữ liệu, thiết kế pipeline cho tới **bộ kiểm thử có thể chạy độc lập bằng Java 17+**. Trọng tâm không phải viết Stream càng ngắn càng tốt, mà là biến các quy tắc thành phép tổng hợp và kiểm thử có thể giải thích, tái lập.

Sau khi hoàn thành, bạn có thể:

1. Viết pipeline lọc đơn hợp lệ và tính doanh thu với `BigDecimal`, không dùng `double` cho tiền.
2. Dùng `Collectors.toMap` có merge function và `groupingBy` có downstream collector để tạo báo cáo theo SKU và danh mục.
3. Phân biệt **thứ tự xuất hiện trong nguồn**, **thứ tự duyệt Map** và **thứ tự xếp hạng theo nghiệp vụ**.
4. Kiểm thử kết quả với dữ liệu có mã trùng, đơn bị hủy, rỗng, tiền thập phân, đồng hạng và nguồn bị đảo thứ tự.
5. So sánh tính đúng đắn của kết quả trên Stream tuần tự và song song mà không dựa vào thứ tự chạy của các lambda.

## 1. Bản đặc tả: thống kê cái gì, theo thứ tự nào?

Nguồn là một danh sách **dòng bán hàng**. Một hóa đơn có thể gồm nhiều dòng; một SKU có thể xuất hiện ở nhiều hóa đơn.

Mỗi dòng có:

| Trường | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `receiptId` | `R-01` | Mã hóa đơn, dùng để đếm số hóa đơn khác nhau. |
| `sku` | `PEN` | Định danh sản phẩm để gộp doanh thu và số lượng. |
| `category` | `STATIONERY` | Danh mục dùng cho báo cáo tổng doanh thu theo nhóm. |
| `quantity` | `2` | Số lượng của dòng, phải dương theo bài toán này. |
| `unitPrice` | `12.50` | Đơn giá dạng `BigDecimal`, không âm. |
| `status` | `PAID` | Trạng thái hóa đơn: `PAID` hoặc `CANCELLED`. |

Đầu ra gồm:

- **Số hóa đơn đã thanh toán:** số `receiptId` phân biệt, không phải số dòng.
- **Số dòng đã thanh toán:** số phần tử còn lại sau `filter`.
- **Số đơn vị đã bán:** tổng `quantity` trên các dòng `PAID`.
- **Tổng doanh thu:** tổng `quantity × unitPrice` trên các dòng `PAID`.
- **Doanh thu theo danh mục:** `Map<String, BigDecimal>`, duyệt theo thứ tự chữ cái của khóa.
- **Xếp hạng SKU:** doanh thu **giảm dần**; nếu hai SKU bằng doanh thu, dùng mã SKU **tăng dần** để phá hòa. Mỗi mục xếp hạng còn chứa tổng số lượng.
- **SKU theo lần xuất hiện đầu:** chỉ lấy lần xuất hiện đầu tiên trong các dòng `PAID`, giữ encounter order của nguồn `List`.

Quy tắc rõ ràng ngay từ đầu:

1. Dòng `CANCELLED` không tham gia **bất kỳ** chỉ số nào.
2. Dữ liệu tiền là số thập phân chính xác; không làm tròn trong mỗi phép cộng. Nếu hệ thống cần thuế, giảm giá hoặc hoàn tiền, phải đặc tả và mô hình hóa riêng.
3. Một SKU đại diện cùng một sản phẩm; bài thực hành giả định SKU được gán danh mục nhất quán trong dữ liệu nhập.
4. `receiptId`, `sku`, `category`, `unitPrice`, `status` không được `null`; `quantity > 0`, `unitPrice >= 0`.
5. Mọi danh sách được sắp xếp **theo quy tắc tường minh**, không dựa vào thứ tự mà một `HashMap` tình cờ trả về.

## 2. Dữ liệu mẫu và kết quả dự kiến

| Hóa đơn | SKU | Danh mục | Số lượng | Đơn giá | Trạng thái | Thành tiền được tính |
| --- | --- | --- | ---: | ---: | --- | ---: |
| R-01 | PEN | STATIONERY | 2 | 12.50 | PAID | 25.00 |
| R-01 | BOOK | BOOKS | 1 | 80.00 | PAID | 80.00 |
| R-02 | PEN | STATIONERY | 3 | 12.50 | PAID | 37.50 |
| R-03 | BAG | ACCESSORY | 1 | 62.50 | PAID | 62.50 |
| R-04 | BAG | ACCESSORY | 9 | 62.50 | CANCELLED | **Không tính** |

Từ bốn dòng `PAID` ta suy ra:

```text
Số hóa đơn đã thanh toán: 3 (R-01, R-02, R-03)
Số dòng được tính:         4
Số đơn vị đã bán:          7 = 2 + 1 + 3 + 1
Tổng doanh thu:            205.00 = 25.00 + 80.00 + 37.50 + 62.50

Theo danh mục:
  ACCESSORY  = 62.50
  BOOKS      = 80.00
  STATIONERY = 62.50

Theo SKU:
  BOOK: 1 đơn vị, doanh thu 80.00
  BAG:  1 đơn vị, doanh thu 62.50
  PEN:  5 đơn vị, doanh thu 62.50
```

**Vì sao BAG xếp trước PEN?** Cả hai cùng doanh thu `62.50`; theo quy tắc phá hòa, `"BAG"` nhỏ hơn `"PEN"` khi so sánh chuỗi tăng dần. **Vì sao `firstSeenSkus` lại là `[PEN, BOOK, BAG]`?** Đây là yêu cầu khác: nó phản ánh thứ tự lần đầu các SKU xuất hiện ở nguồn `List` sau lọc, **không** phải thứ tự doanh thu.

## 3. Thiết kế pipeline: một nguồn, nhiều đại lượng

Ta chia bài toán thành những bước nhỏ, rõ kiểu dữ liệu:

```text
List<SaleLine> (nguồn có encounter order)
             │
             ▼
   filter(status == PAID)
             │
             ▼
       List<SaleLine> paid
             │
             ├── receiptId → distinct → count
             ├── quantity  → mapToLong → reduce(addExact)
             ├── amount    → BigDecimal::add → tổng doanh thu
             ├── category  → groupingBy → reducing → Map theo danh mục
             ├── sku       → toMap(merge) → tổng hợp theo SKU
             │                           └── sorted(revenue DESC, sku ASC)
             └── sku       → distinct → SKU theo lần xuất hiện đầu
```

`filter`, `map`, `mapToLong`, `distinct`, `sorted` là các phép toán trung gian; `count`, `reduce`, `collect`, `toList` là terminal operations. Một `Stream` không dùng lại được sau terminal operation; vì vậy mỗi chỉ số phải tạo **Stream mới từ danh sách `paid`**, hoặc kết hợp chúng vào một collector tùy chỉnh trong phiên bản nâng cao.

Trong bài này, ta cố ý tạo danh sách `paid` một lần để việc xác định tập dữ liệu hợp lệ trở nên dễ quan sát, và để dễ viết kiểm thử. Với dữ liệu cực lớn, việc giữ danh sách trung gian có chi phí bộ nhớ; mục 9 phân tích các hướng thay thế.

## 4. Chương trình Java 17+ đầy đủ

Lưu đoạn sau vào tệp `SalesReportProject.java`. Chương trình có **dữ liệu mẫu, hàm tạo báo cáo, hàm in kết quả và bộ kiểm thử tự động**. Không cần thư viện ngoài JDK; phương thức `main` tự gọi các kiểm thử.

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class SalesReportProject {

    enum Status {
        PAID, CANCELLED
    }

    record SaleLine(
            String receiptId,
            String sku,
            String category,
            int quantity,
            BigDecimal unitPrice,
            Status status
    ) {
        SaleLine {
            Objects.requireNonNull(receiptId, "receiptId");
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(category, "category");
            Objects.requireNonNull(unitPrice, "unitPrice");
            Objects.requireNonNull(status, "status");

            if (receiptId.isBlank() || sku.isBlank() || category.isBlank()) {
                throw new IllegalArgumentException("Mã và danh mục không rỗng");
            }
            if (quantity <= 0 || unitPrice.signum() < 0) {
                throw new IllegalArgumentException("Số lượng/đơn giá không hợp lệ");
            }
        }

        BigDecimal amount() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    record ProductTotal(String sku, long units, BigDecimal revenue) {}

    record SalesReport(
            long paidReceipts,
            long paidLines,
            long soldUnits,
            BigDecimal totalRevenue,
            Map<String, BigDecimal> revenueByCategory,
            List<ProductTotal> rankedProducts,
            List<String> firstSeenSkus
    ) {
        SalesReport {
            // Phòng thay đổi từ bên ngoài sau khi trả kết quả.
            // Bản sao TreeMap bảo đảm thứ tự khóa tăng dần.
            revenueByCategory = Collections.unmodifiableMap(
                    new TreeMap<>(revenueByCategory));
            rankedProducts = List.copyOf(rankedProducts);
            firstSeenSkus = List.copyOf(firstSeenSkus);
        }
    }

    static Stream<SaleLine> view(List<SaleLine> rows, boolean parallel) {
        return parallel ? rows.parallelStream() : rows.stream();
    }

    static SalesReport buildReport(List<SaleLine> source, boolean parallel) {
        Objects.requireNonNull(source, "source");

        // Một danh sách có encounter order từ List nguồn.
        List<SaleLine> paid = view(source, parallel)
                .map(line -> Objects.requireNonNull(line, "sale line"))
                .filter(line -> line.status() == Status.PAID)
                .toList();

        // Hai dòng của cùng hóa đơn chỉ tính thành một hóa đơn.
        long paidReceipts = view(paid, parallel)
                .map(SaleLine::receiptId)
                .distinct()
                .count();

        long soldUnits = view(paid, parallel)
                .mapToLong(SaleLine::quantity)
                .reduce(0L, Math::addExact);

        // Cộng tiền chính xác bằng BigDecimal, không dùng double.
        BigDecimal totalRevenue = view(paid, parallel)
                .map(SaleLine::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        // Mỗi danh mục có một tổng tiền; TreeMap sắp xếp khóa.
        Map<String, BigDecimal> revenueByCategory = view(paid, parallel)
                .collect(Collectors.groupingBy(
                        SaleLine::category,
                        TreeMap::new,
                        Collectors.reducing(
                                BigDecimal.ZERO,
                                SaleLine::amount,
                                BigDecimal::add)
                ));

        // Gộp các dòng trùng SKU bằng một phép merge có tính kết hợp.
        Map<String, ProductTotal> bySku = view(paid, parallel)
                .collect(Collectors.toMap(
                        SaleLine::sku,
                        line -> new ProductTotal(
                                line.sku(), line.quantity(), line.amount()),
                        (left, right) -> new ProductTotal(
                                left.sku(),
                                Math.addExact(left.units(), right.units()),
                                left.revenue().add(right.revenue()))
                ));

        // Xếp hạng xác định: doanh thu giảm dần, SKU tăng dần.
        Comparator<ProductTotal> rankingOrder =
                Comparator.<ProductTotal, BigDecimal>comparing(
                        ProductTotal::revenue,
                        Comparator.reverseOrder())
                        .thenComparing(ProductTotal::sku);

        List<ProductTotal> rankedProducts = bySku.values().stream()
                .sorted(rankingOrder)
                .toList();

        // Đây là thứ tự lần xuất hiện đầu, KHÁC với bảng xếp hạng.
        List<String> firstSeenSkus = view(paid, parallel)
                .map(SaleLine::sku)
                .distinct()
                .toList();

        return new SalesReport(
                paidReceipts,
                paid.size(),
                soldUnits,
                totalRevenue,
                revenueByCategory,
                rankedProducts,
                firstSeenSkus);
    }

    static List<SaleLine> sample() {
        return List.of(
                new SaleLine("R-01", "PEN", "STATIONERY", 2,
                        new BigDecimal("12.50"), Status.PAID),
                new SaleLine("R-01", "BOOK", "BOOKS", 1,
                        new BigDecimal("80.00"), Status.PAID),
                new SaleLine("R-02", "PEN", "STATIONERY", 3,
                        new BigDecimal("12.50"), Status.PAID),
                new SaleLine("R-03", "BAG", "ACCESSORY", 1,
                        new BigDecimal("62.50"), Status.PAID),
                new SaleLine("R-04", "BAG", "ACCESSORY", 9,
                        new BigDecimal("62.50"), Status.CANCELLED)
        );
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void checkMoney(
            String name, BigDecimal actual, String expected) {
        check(actual.compareTo(new BigDecimal(expected)) == 0,
                name + ": expected " + expected + ", actual " + actual);
    }

    static List<String> rankedSkus(SalesReport report) {
        return report.rankedProducts().stream()
                .map(ProductTotal::sku)
                .toList();
    }

    static void selfTest() {
        List<SaleLine> data = sample();
        SalesReport sequential = buildReport(data, false);

        // Tính đúng: chỉ có ba hóa đơn PAID và bốn dòng hợp lệ.
        check(sequential.paidReceipts() == 3, "Số hóa đơn");
        check(sequential.paidLines() == 4, "Số dòng");
        check(sequential.soldUnits() == 7, "Số lượng");
        checkMoney("Tổng doanh thu", sequential.totalRevenue(), "205.00");
        checkMoney("BOOKS",
                sequential.revenueByCategory().get("BOOKS"), "80.00");
        checkMoney("STATIONERY",
                sequential.revenueByCategory().get("STATIONERY"), "62.50");
        checkMoney("ACCESSORY",
                sequential.revenueByCategory().get("ACCESSORY"), "62.50");

        // Thứ tự báo cáo: sắp hạng với tiêu chí phá hòa.
        check(rankedSkus(sequential).equals(
                List.of("BOOK", "BAG", "PEN")), "Ranking");
        check(sequential.firstSeenSkus().equals(
                List.of("PEN", "BOOK", "BAG")), "Encounter order");
        check(new ArrayList<>(sequential.revenueByCategory().keySet())
                .equals(List.of("ACCESSORY", "BOOKS", "STATIONERY")),
                "Category key order");
        check(sequential.rankedProducts().get(2).units() == 5,
                "Gộp số lượng PEN");

        // Cùng nguồn, xử lý song song không làm đổi kết quả.
        SalesReport parallel = buildReport(data, true);
        check(sequential.equals(parallel), "Parallel != sequential");

        // Đảo encounter order: các tổng không đổi,
        // nhưng lần xuất hiện SKU đầu tiên có thể thay đổi.
        List<SaleLine> reversed = new ArrayList<>(data);
        Collections.reverse(reversed);
        SalesReport changedOrder = buildReport(reversed, true);
        checkMoney("Tổng sau đảo nguồn",
                changedOrder.totalRevenue(), "205.00");
        check(changedOrder.rankedProducts().equals(
                sequential.rankedProducts()), "Ranking đổi khi đảo nguồn");
        check(changedOrder.revenueByCategory().equals(
                sequential.revenueByCategory()), "Group đổi khi đảo nguồn");
        check(changedOrder.firstSeenSkus().equals(
                List.of("BAG", "PEN", "BOOK")), "Thứ tự SKU sau đảo");

        // Nguồn rỗng và nguồn chỉ gồm đơn hủy.
        SalesReport empty = buildReport(List.of(), false);
        check(empty.paidReceipts() == 0, "Empty receipts");
        check(empty.paidLines() == 0, "Empty lines");
        check(empty.soldUnits() == 0, "Empty units");
        checkMoney("Empty revenue", empty.totalRevenue(), "0");
        check(empty.revenueByCategory().isEmpty(), "Empty categories");
        check(empty.rankedProducts().isEmpty(), "Empty ranking");
        check(empty.firstSeenSkus().isEmpty(), "Empty appearance");
        check(buildReport(List.of(data.get(4)), true).equals(empty),
                "Cancelled-only report");

        // Tiền thập phân: không cộng bằng double.
        List<SaleLine> cents = List.of(
                new SaleLine("R-A", "A", "SMALL", 1,
                        new BigDecimal("0.10"), Status.PAID),
                new SaleLine("R-B", "A", "SMALL", 1,
                        new BigDecimal("0.20"), Status.PAID)
        );
        checkMoney("Decimal amount",
                buildReport(cents, true).totalRevenue(), "0.30");

        // Kết quả đã trả ra không cho sửa danh sách.
        boolean rejected = false;
        try {
            sequential.firstSeenSkus().add("X");
        } catch (UnsupportedOperationException expected) {
            rejected = true;
        }
        check(rejected, "Result list must be unmodifiable");
    }

    public static void main(String[] args) {
        SalesReport report = buildReport(sample(), false);
        System.out.println("Hóa đơn PAID: " + report.paidReceipts());
        System.out.println("Dòng PAID: " + report.paidLines());
        System.out.println("Số lượng: " + report.soldUnits());
        System.out.println("Doanh thu: " + report.totalRevenue());
        System.out.println("Theo danh mục: " + report.revenueByCategory());
        System.out.println("Xếp hạng SKU: " + rankedSkus(report));
        System.out.println("SKU xuất hiện đầu: " + report.firstSeenSkus());

        // Luôn chạy check; không phụ thuộc cờ -ea của Java assert.
        selfTest();
        System.out.println("TEST PASS");
    }
}
```

Chạy bằng Java 17+ tại nơi đã lưu tệp, nếu bạn muốn thực hành:

```text
javac SalesReportProject.java
java SalesReportProject
```

Đầu ra kỳ vọng:

```text
Hóa đơn PAID: 3
Dòng PAID: 4
Số lượng: 7
Doanh thu: 205.00
Theo danh mục: {ACCESSORY=62.50, BOOKS=80.00, STATIONERY=62.50}
Xếp hạng SKU: [BOOK, BAG, PEN]
SKU xuất hiện đầu: [PEN, BOOK, BAG]
TEST PASS
```

Đầu ra là kỳ vọng rút ra từ dữ liệu mẫu; mục tiêu quan trọng hơn việc so sánh chuỗi console là **kiểm tra giá trị và thứ tự qua từng thuộc tính** trong `selfTest()`.

## 5. Vì sao dùng `BigDecimal` và `Math.addExact`?

### Tiền không nên cộng bằng `double`

Giá trị thập phân như `0.1` hoặc `0.2` không luôn biểu diễn chính xác ở dạng nhị phân. Khi xử lý tiền, viết:

```java
BigDecimal a = new BigDecimal("0.10");
BigDecimal b = new BigDecimal("0.20");
BigDecimal total = a.add(b);

System.out.println(total); // 0.30
```

Không viết `new BigDecimal(0.1)` nếu mong nhận đúng giá trị thập phân `0.1`; cách xây dựng từ `String` hoặc đơn vị nhỏ nhất dạng số nguyên đáng tin cậy hơn.

Trong ví dụ, `SaleLine.amount()` nhân số nguyên dương với `BigDecimal`. Khi giảm nhiều dòng:

```java
BigDecimal totalRevenue = paid.stream()
        .map(SaleLine::amount)
        .reduce(BigDecimal.ZERO, BigDecimal::add);
```

`BigDecimal.ZERO` là giá trị trung hòa của phép cộng. `BigDecimal::add` cho kết quả số học chính xác, và phép cộng có tính kết hợp **về giá trị số**, nên phù hợp để kết hợp các nhánh song song. Tuy nhiên, không suy ra mọi logic làm tròn đều có tính kết hợp: nếu làm tròn sau **mỗi** phép cộng, kết quả có thể khác nhau theo cách phân chia nguồn.

### Vì sao `checkMoney` dùng `compareTo`?

`BigDecimal.equals` xét cả **scale**:

```java
new BigDecimal("2.0").equals(new BigDecimal("2.00"));    // false
new BigDecimal("2.0").compareTo(new BigDecimal("2.00")); // 0
```

Với báo cáo cần so sánh **giá trị tiền về mặt số học**, `compareTo(...) == 0` thường thích hợp hơn. Nếu nghiệp vụ yêu cầu cố định đúng hai chữ số thập phân, hãy kiểm tra **thêm** scale và áp dụng quy tắc định dạng/làm tròn tại ranh giới đã định.

### Số lượng có thể tràn

`IntStream.sum()` trả `int`, có thể tràn khi tổng lớn. Bài dùng:

```java
long units = paid.stream()
        .mapToLong(SaleLine::quantity)
        .reduce(0L, Math::addExact);
```

`Math.addExact` ném `ArithmeticException` nếu tổng vượt miền `long`; như vậy lỗi lộ rõ thay vì âm thầm quấn vòng. Phép cộng này vẫn có thể dùng trong reduction song song khi miền đầu vào và quy tắc nghiệp vụ cho phép. Với lượng vượt `long`, hãy thiết kế kiểu số lớn hơn, thay vì bỏ qua overflow.

## 6. Hai loại thứ tự thường bị nhầm

### Thứ tự xuất hiện lần đầu (*encounter order*)

Với nguồn `List`, Stream mặc định có encounter order. Dạng:

```java
List<String> firstSeen = paid.stream()
        .map(SaleLine::sku)
        .distinct()
        .toList();
```

trả danh sách các SKU khác nhau theo **lần xuất hiện đầu** trong nguồn có thứ tự. Ở dữ liệu mẫu, kết quả là `[PEN, BOOK, BAG]`. Bước `distinct` trên Stream có thứ tự giữ phần tử đầu trong các phần tử bằng nhau; trên nguồn unordered, không được kỳ vọng quy tắc “đầu tiên”.

Nếu đổi thứ tự dòng đầu vào, danh sách này có thể đổi mà **tổng doanh thu vẫn đúng**. Vì vậy, không nên kiểm thử nó bằng cách sắp xếp tùy ý rồi đòi giữ nguyên.

### Thứ tự xếp hạng (*business ranking*)

```java
Comparator<ProductTotal> rankingOrder =
        Comparator.<ProductTotal, BigDecimal>comparing(
                ProductTotal::revenue,
                Comparator.reverseOrder())
                .thenComparing(ProductTotal::sku);
```

Comparator này có hai tiêu chí:

1. Doanh thu **giảm dần** bằng `Comparator.reverseOrder()`.
2. Khi hai doanh thu bằng giá trị số, SKU **tăng dần** bằng `thenComparing`.

`BigDecimal.compareTo` được dùng khi so sánh doanh thu trong comparator, nên `62.5` và `62.50` có cùng giá trị số. Không dựa vào thứ tự duyệt `Map.values()` khi chưa gọi `sorted`.

**Không nhầm** cách này với việc gọi `comparator.reversed()` sau cùng: đảo cả comparator sẽ đảo luôn tiêu chí phụ, làm SKU đồng hạng thành giảm dần. Cách nêu trên chỉ đảo tiêu chí doanh thu, để SKU vẫn tăng.

### Thứ tự khóa trong Map

Việc dùng `TreeMap::new` cho thống kê danh mục tạo thứ tự khóa tăng dần; bước sao chép qua `new TreeMap<>(...)` và bọc `Collections.unmodifiableMap(...)` trong record giúp giữ thứ tự đó khi công bố kết quả.

`HashMap` mặc định của một số collector **không cam kết** thứ tự lặp. Hai Map có thể bằng nhau theo `Map.equals` dù có thứ tự duyệt khác nhau; nếu thứ tự là yêu cầu, hãy kiểm tra danh sách `keySet()` theo quy tắc được công bố.

## 7. Kiểm thử những gì để báo cáo đáng tin cậy?

Đừng chỉ kiểm tra rằng chương trình in được vài dòng. Một báo cáo có thể có **tổng đúng nhưng thứ tự sai**, hoặc **thứ tự đúng nhưng đã tính cả đơn hủy**. Mỗi yêu cầu nghiệp vụ cần được chuyển thành kiểm thử độc lập.

| Nhóm kiểm thử | Tình huống | Kết quả phải xác minh |
| --- | --- | --- |
| Lọc | Một dòng `CANCELLED` có số lượng lớn | Không đóng góp vào số hóa đơn, số lượng và doanh thu. |
| Đếm | Hai dòng thuộc cùng `receiptId` | Một hóa đơn, nhưng hai dòng bán hợp lệ. |
| Gộp SKU | `PEN` xuất hiện hai lần | 5 đơn vị, doanh thu 62.50. |
| Nhóm danh mục | `PEN` và `BOOK` có category khác | Đúng tổng cho mỗi category. |
| Tổng | Tất cả dòng `PAID` | 205.00, không tràn hoặc sai số `double`. |
| Đồng hạng | `BAG` và `PEN` cùng doanh thu | `BAG` đứng trước `PEN` theo SKU. |
| Thứ tự đầu vào | Danh sách xuất hiện PEN, BOOK, BAG | `firstSeenSkus` có cùng thứ tự. |
| Hoán vị nguồn | Đảo ngược danh sách dòng | Các tổng và ranking không đổi; `firstSeenSkus` đổi theo encounter order. |
| Song song | `parallel = true` trên cùng nguồn | Toàn bộ report bằng report tuần tự. |
| Rỗng | Danh sách rỗng hoặc chỉ có `CANCELLED` | Số đếm 0, doanh thu 0, các Map/List rỗng. |
| Thập phân | 0.10 và 0.20 | Tổng bằng 0.30 theo giá trị số. |
| Bất biến đầu ra | Thử thêm SKU vào danh sách công bố | Bị từ chối bằng `UnsupportedOperationException`. |

Trong `selfTest()`, `check(boolean, message)` ném `AssertionError` khi sai. Khác với câu lệnh `assert` của Java, cơ chế kiểm tra này **không phụ thuộc cờ `-ea`** khi chạy chương trình. Nó phù hợp để tự học trong một tệp; trong dự án có bộ kiểm thử chuyên nghiệp, hãy đặt các trường hợp tương ứng vào test riêng bằng JUnit hoặc framework của dự án.

### Kiểm thử hoán vị dữ liệu là một phép kiểm tra mạnh

Vì phép cộng và phép gộp theo SKU là độc lập với thứ tự, ta kỳ vọng:

```text
report(source).totalRevenue == report(reverse(source)).totalRevenue
report(source).rankedProducts == report(reverse(source)).rankedProducts
```

Tuy nhiên:

```text
report(source).firstSeenSkus
    có thể KHÁC report(reverse(source)).firstSeenSkus
```

Đây là **kiểm thử tính bất biến theo hoán vị** cho các đại lượng không phụ thuộc thứ tự, đồng thời chứng minh thứ tự xuất hiện **thực sự** được xử lý theo ngữ nghĩa nguồn. Nếu kiểm thử ép hai danh sách `firstSeenSkus` bằng nhau sau đảo nguồn, chính kiểm thử mới là thứ sai.

## 8. Tuần tự, song song và hợp đồng đúng đắn

`parallelStream()` có thể chia nguồn và gộp kết quả theo các nhóm khác nhau. Bài thực hành dùng những phép gộp có tính kết hợp:

- Số lượng: `Math.addExact` khi tổng thuộc miền `long`.
- Tiền: `BigDecimal::add`, không làm tròn trung gian.
- Gộp theo SKU: cộng số lượng và doanh thu, với SKU cố định cho mỗi khóa.
- Xếp hạng: sắp theo comparator tường minh sau khi gộp.
- SKU xuất hiện đầu: giữ encounter order của nguồn `List` khi dùng `distinct`.

Đừng dùng một `ArrayList` bên ngoài rồi thêm phần tử từ `parallelStream().forEach(shared::add)`: nó tạo tranh chấp dữ liệu và thứ tự không được bảo đảm. Các collector của Stream quản lý vùng tích lũy và phép gộp phù hợp hơn.

```java
// Không nên:
// List<SaleLine> shared = new ArrayList<>();
// source.parallelStream().forEach(shared::add);

// Nên:
List<SaleLine> paid = source.parallelStream()
        .filter(s -> s.status() == Status.PAID)
        .toList();
```

Với nguồn `List` có encounter order, `Stream.toList()` giữ thứ tự phần tử trong kết quả, dù các phần tử có thể được xử lý bởi các thread khác nhau. **Thứ tự gọi lambda** không nhất thiết là thứ tự trong List kết quả.

### Có nên dùng `parallel = true` trong sản xuất?

Không nên quyết định chỉ vì kết quả kiểm thử giống nhau. Song song có chi phí chia nguồn, lập lịch và kết hợp các Map trung gian. Ở ví dụ nhỏ, `parallelStream()` có thể **chậm hơn** tuần tự. Nếu phần tính toán là CPU-bound, stateless và dữ liệu đủ lớn, hãy đo trên môi trường thật; nếu mỗi dòng gọi JDBC/HTTP chặn, cần mô hình điều phối I/O và giới hạn tài nguyên riêng thay vì mặc định dùng common pool.

Kiểm thử chức năng trả lời **“có đúng không?”**; benchmark và quan sát hệ thống mới giúp trả lời **“có nhanh hơn không?”**. Không lấy thời gian chạy một lần làm kết luận.

## 9. Giới hạn thiết kế và hướng mở rộng

### 9.1. Vật hóa danh sách `paid`

Giải pháp hiện tại lưu một danh sách trung gian, sau đó duyệt lại danh sách để tính các chỉ số. Cách này thuận tiện cho giáo trình và dữ liệu vừa phải, nhưng dùng thêm bộ nhớ theo số dòng `PAID`. Với dữ liệu cực lớn, có thể sử dụng một **collector tùy chỉnh** tích lũy nhiều thống kê trong một lượt, kết hợp `groupingBy`/downstream collector theo nhu cầu, hoặc tổng hợp tại cơ sở dữ liệu.

Không đồng nghĩa rằng một collector tùy chỉnh tự động ít bộ nhớ: nếu vẫn phải giữ Map cho từng SKU hoặc từng danh mục, bộ nhớ vẫn tăng theo **số khóa phân biệt**.

### 9.2. Dữ liệu lỗi, SKU trùng danh mục và ngoại lệ

Record `SaleLine` kiểm tra dữ liệu của **một dòng**, không kiểm tra quy tắc toàn bộ tập dữ liệu. Nếu cùng một SKU có hai `category` khác nhau, báo cáo theo SKU vẫn gộp được nhưng báo cáo theo danh mục có thể phản ánh tình trạng nguồn **không nhất quán**. Với hệ thống thật, hãy kiểm tra quy tắc `SKU -> category` tại tầng nhập dữ liệu hoặc trước khi lập báo cáo.

Quy tắc khác cũng cần xác định trước khi mở rộng:

- Hoàn tiền/đổi trả có được thể hiện bằng dòng âm hay trạng thái riêng?
- Đếm số đơn `PAID` theo toàn bộ đơn hay theo từng dòng? Bài này giả định trạng thái theo từng dòng phản ánh trạng thái đơn.
- Tiền thuế, chiết khấu, phí giao hàng được phân bổ cho SKU hay chỉ xuất hiện trong tổng hóa đơn?
- Múi giờ, kỳ báo cáo, tỷ giá và quy tắc làm tròn lấy theo ngày hay theo giao dịch?

Các câu hỏi này không có đáp án kỹ thuật duy nhất; phải xuất phát từ yêu cầu nghiệp vụ trước khi chọn `filter`, `map` hay collector.

### 9.3. Tính ổn định và thứ tự

Khi yêu cầu báo cáo theo “thời gian bán đầu tiên”, không thể chỉ dựa vào **vị trí dòng trong List** nếu List có thể nhập theo nhiều thứ tự. Hãy thêm trường `soldAt` hoặc sequence của sự kiện rồi sắp xếp bằng comparator, có **tiêu chí phá hòa** khi timestamp giống nhau.

Tương tự, khi xếp hạng theo nhiều tiêu chí, hãy cố gắng đưa ra một thứ tự hoàn chỉnh đủ để kết quả không phụ thuộc vào thứ tự duyệt Map hay thứ tự gộp các nhánh song song.

### 9.4. Nguồn Stream và quản lý tài nguyên

Nếu nguồn là một Stream trực tiếp từ tệp hoặc cursor cơ sở dữ liệu, `collect` có thể tiêu thụ nguồn nhưng **không thay thế việc đóng tài nguyên**. Với nguồn cần đóng, dùng `try-with-resources` theo API tương ứng. Một Stream không thể được dùng lại sau terminal operation; không tái sử dụng cùng đối tượng Stream để tính nhiều báo cáo.

## 10. Bài tập mở rộng cho dự án

**Bài 1 — Top N.** Viết phương thức trả ba SKU có doanh thu cao nhất. Khi có đồng hạng, giữ tiêu chí SKU tăng dần.

```java
List<ProductTotal> topThree = report.rankedProducts().stream()
        .limit(3)
        .toList();
```

`report` là biến `SalesReport` nhận từ `buildReport`. Vì danh sách đã được sắp theo comparator nghiệp vụ, `limit(3)` không cần sắp lại.

**Bài 2 — Phần trăm đóng góp.** Tính tỷ trọng doanh thu `BOOKS` trên tổng doanh thu, dùng `BigDecimal.divide(scale, roundingMode)` và làm tròn ở bước trình bày. Nếu tổng bằng 0, nêu rõ chính sách thay vì chia cho 0.

**Bài 3 — Phát hiện dữ liệu không nhất quán.** Thêm bước kiểm tra nếu cùng một SKU xuất hiện ở nhiều danh mục thì báo lỗi. Đừng im lặng hợp nhất hai SKU khác danh mục chỉ vì mã giống nhau.

**Bài 4 — Thứ tự theo thời gian.** Bổ sung trường `soldAt` và `lineId`. Tạo danh sách SKU theo thứ tự sự kiện bán đầu tiên, dùng thời gian tăng dần và `lineId` làm tiêu chí phụ. So sánh với việc dùng trực tiếp encounter order.

**Bài 5 — Đối chiếu độc lập.** Tạo một bộ dữ liệu nhỏ và tính tổng doanh thu bằng vòng lặp thông thường để so sánh với kết quả Stream. Với dữ liệu lớn ngẫu nhiên, kiểm thử bất biến theo hoán vị và thêm dữ liệu không ảnh hưởng (như đơn hủy) để phát hiện hồi quy.

**Bài 6 — Streaming theo lô.** Thảo luận cách xử lý khi có hàng triệu dòng bán hàng. Nếu chuyển sang collector tùy chỉnh, hãy xác định rõ `supplier`, `accumulator`, `combiner`, `finisher`, đặc biệt đảm bảo phép gộp vẫn đúng khi dùng `parallelStream()`.

## Ghi nhớ

- Báo cáo bán hàng đúng bắt đầu từ **hợp đồng nghiệp vụ**: trạng thái nào được tính, “số đơn” khác “số dòng”, tiền và số lượng được cộng thế nào.
- `filter` chọn dữ liệu hợp lệ; `map`/`reduce` tính tổng; `toMap` có merge function gộp SKU; `groupingBy` có downstream collector gộp doanh thu theo danh mục.
- Dùng **`BigDecimal`** cho tiền, `Math.addExact` khi cần phát hiện tràn số, và tránh làm tròn giữa các bước tổng hợp.
- **Encounter order**, **thứ tự khóa Map** và **xếp hạng nghiệp vụ** là ba khái niệm khác nhau: giữ thứ tự lần xuất hiện bằng `distinct`, dùng `TreeMap` cho khóa và comparator có phá hòa cho ranking.
- Kiểm thử phải bao phủ đơn hủy, mã trùng, nguồn rỗng, đồng hạng, đảo thứ tự, số thập phân và so sánh tuần tự/song song; **đúng chức năng không tự chứng minh hiệu năng tốt**.
