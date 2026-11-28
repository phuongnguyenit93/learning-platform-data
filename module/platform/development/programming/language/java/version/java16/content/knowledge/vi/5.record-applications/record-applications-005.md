# Local record làm kết quả trung gian trong pipeline Stream

> **Học phần:** `JAVA_VERSION_JAVA16` · **Chương:** Ứng dụng record. Local record được chuẩn hóa từ Java 16 và vẫn hữu ích trong Java hiện đại khi một pipeline cần tạo ra dữ liệu trung gian có nhiều thành phần, tên rõ ràng và equality theo giá trị. Bài học tập trung vào cách khai báo và dùng local record bên trong phương thức xử lý Stream.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích local record là gì, phạm vi tồn tại và vì sao nó được ngầm định là static.
- Dùng local record để gom nhiều giá trị thành một đối tượng trung gian trong các bước `map`, `filter`, `sorted` và `collect`.
- Dùng local record làm khóa nhóm trong `Collectors.groupingBy` hoặc làm dữ liệu trung gian cho phép tổng hợp.
- Phân biệt local record với `Map.Entry`, tuple tự tạo bằng mảng/collection và record khai báo ở cấp class.
- Biết khi nào nên chuyển dữ liệu sang DTO/record công khai trước khi trả kết quả ra khỏi phương thức.

## 1. Local record là gì?

Local record là một record được khai báo bên trong một block, thường là thân phương thức. Nó tạo ra một kiểu dữ liệu có tên nhưng chỉ có thể được tham chiếu trong phạm vi block chứa khai báo đó.

Ví dụ:

```java
public class ReportService {
    public List<String> describe(List<Sale> sales) {
        record SaleView(String region, BigDecimal amount) {}

        return sales.stream()
                .map(sale -> new SaleView(sale.region(), sale.amount()))
                .map(view -> view.region() + ": " + view.amount())
                .toList();
    }
}
```

`SaleView` chỉ phục vụ pipeline bên trong `describe`. Người đọc thấy rõ mỗi phần tử trung gian gồm `region` và `amount`. Kiểu này không cần được công khai ở package hoặc trở thành một phần API của `ReportService`.

Local record là một loại local class đặc biệt. Nó có các đặc điểm của record: component, canonical constructor, accessor, `equals()`, `hashCode()` và `toString()` được sinh tự động. Nhưng phạm vi của tên kiểu được giới hạn trong block khai báo.

### 1.1. Local record được ngầm định là static

Local record được ngầm định là static và không phải inner class. Nó không giữ tham chiếu ngầm tới instance bao ngoài. Vì vậy:

- Không thể truy cập trực tiếp trường instance hoặc phương thức instance của đối tượng bao ngoài.
- Không capture biến local hoặc tham số của phương thức bao ngoài, kể cả khi biến đó là effectively final.
- Có thể dùng dữ liệu cần thiết nếu truyền chúng vào constructor như component.
- Có thể truy cập các thành viên static phù hợp của kiểu bao ngoài.
- Có thể khai báo tham số generic riêng cho chính record.

Ví dụ sau không hợp lệ vì local record cố dùng biến local `taxRate` mà không truyền nó qua component:

```java
import java.math.BigDecimal;
import java.util.List;

class TaxCalculator {
    public List<BigDecimal> calculate(List<BigDecimal> prices) {
        BigDecimal taxRate = new BigDecimal("0.10");

        record PriceWithTax(BigDecimal price) {
            BigDecimal total() {
                // Không hợp lệ nếu bỏ comment: local record không capture taxRate.
                // return price.multiply(BigDecimal.ONE.add(taxRate));
                return price;
            }
        }

        return prices.stream()
                .map(price -> new PriceWithTax(price).total())
                .toList();
    }
}
```

Cách đúng là truyền tỷ lệ thuế vào dữ liệu cần thiết hoặc tính trong lambda:

```java
import java.math.BigDecimal;
import java.util.List;

class TaxCalculator {
    public List<BigDecimal> calculate(List<BigDecimal> prices) {
        BigDecimal taxRate = new BigDecimal("0.10");

        record PriceWithTax(BigDecimal price, BigDecimal taxRate) {
            BigDecimal total() {
                return price.multiply(BigDecimal.ONE.add(taxRate));
            }
        }

        return prices.stream()
                .map(price -> new PriceWithTax(price, taxRate).total())
                .toList();
    }
}
```

Lambda ở ví dụ thứ hai có thể capture `taxRate` vì biến này effectively final. Local record không capture nó; lambda truyền giá trị vào constructor một cách tường minh. Sự khác biệt này giúp local record thể hiện đầy đủ dữ liệu mà đối tượng trung gian phụ thuộc.

### 1.2. Local record có thể có constructor và phương thức

Local record không chỉ là một cặp giá trị tạm. Nó có thể chuẩn hóa dữ liệu và cung cấp hành vi gắn với dữ liệu đó. Ví dụ, khai báo trong thân phương thức:

```java
import java.util.Locale;

public class UserProcessor {
    public void process() {
        record UserName(String value) {
            UserName {
                if (value == null || value.isBlank()) {
                    throw new IllegalArgumentException("Name is required");
                }
                value = value.strip();
            }

            String normalized() {
                return value.toLowerCase(Locale.ROOT);
            }
        }

        UserName user = new UserName("  Linh  ");
        System.out.println(user.normalized());
    }
}
```

Constructor bảo đảm component hợp lệ ngay khi tạo. Phương thức `normalized()` là hành vi tính toán từ component, không cần trạng thái mutable bổ sung. Quy tắc này giống record thông thường; khác biệt chính là phạm vi sử dụng của kiểu.

## 2. Vì sao dùng local record trong pipeline Stream?

Một pipeline thường chuyển dữ liệu qua nhiều hình dạng:

```text
Nguồn dữ liệu
    -> chuẩn hóa
    -> kết hợp các trường liên quan
    -> lọc
    -> nhóm / sắp xếp / tổng hợp
    -> kết quả cuối
```

Ở mỗi bước, đôi khi cần mang theo nhiều giá trị cùng lúc. Nếu chỉ dùng một component, có thể tiếp tục truyền giá trị đơn. Nhưng khi cần hai, ba hoặc nhiều giá trị liên quan, local record giúp đặt tên cho hình dạng dữ liệu trung gian.

Ví dụ cần chuẩn hóa tên khu vực, lấy tháng từ ngày giao dịch và giữ lại số tiền. Local record có thể biểu diễn một dòng doanh thu đã chuẩn hóa:

```java
record NormalizedSale(
        String region,
        YearMonth month,
        BigDecimal amount
) {}
```

Thay vì truyền một `Object[]` với các vị trí khó nhớ, pipeline làm việc với `row.region()`, `row.month()` và `row.amount()`. Compiler cũng kiểm tra kiểu dữ liệu ở thời điểm biên dịch.

### 2.1. So sánh với tuple tự tạo bằng mảng hoặc List

| Cách biểu diễn | Ưu điểm | Hạn chế |
|---|---|---|
| Local record | Có tên component, kiểu cụ thể, equality theo giá trị | Chỉ dùng được trong phạm vi khai báo |
| `Object[]` | Có thể chứa nhiều giá trị khác kiểu | Phải ép kiểu và nhớ vị trí phần tử |
| `List<Object>` | Dễ tạo động | Mất kiểu cụ thể, dễ nhầm thứ tự |
| `Map<String, Object>` | Có thể tra cứu theo tên | Không kiểm tra kiểu khi lấy, tên key dễ sai |
| `Map.Entry<K,V>` | Phù hợp cho một cặp key/value | Không diễn tả tốt ba hoặc nhiều thành phần có ý nghĩa |
| Record cấp package/class | Dùng lại được ở nhiều phương thức | Mở rộng phạm vi kiểu và có thể làm API nội bộ lớn hơn |

Local record là lựa chọn tốt khi dữ liệu trung gian có cấu trúc ổn định trong một phương thức và cần tên component rõ ràng. Không cần tạo một kiểu top-level chỉ để chuyển vài giá trị giữa các bước của một pipeline.

## 3. Pipeline hoàn chỉnh: chuẩn hóa và tổng hợp doanh thu

Ta xây dựng một phương thức tổng hợp doanh thu theo khu vực và tháng. Đầu vào là các giao dịch có ngày phát sinh. Pipeline sẽ:

1. Sao chép và kiểm tra danh sách đầu vào.
2. Chuẩn hóa khu vực, chuyển ngày thành `YearMonth` và tạo dòng dữ liệu trung gian.
3. Bỏ các giao dịch có giá trị bằng không theo quy tắc báo cáo minh họa.
4. Nhóm theo khóa khu vực-tháng.
5. Tính tổng doanh thu cho mỗi nhóm.
6. Chuyển kết quả sang record công khai và sắp xếp.

File `SalesReport.java`:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

public final class SalesReport {
    private SalesReport() {}

    public record Sale(
            String region,
            LocalDate soldOn,
            BigDecimal amount
    ) {
        public Sale {
            Objects.requireNonNull(region, "region");
            Objects.requireNonNull(soldOn, "soldOn");
            Objects.requireNonNull(amount, "amount");

            if (amount.signum() < 0) {
                throw new IllegalArgumentException("amount must not be negative");
            }
        }
    }

    public record MonthlyTotal(
            String region,
            YearMonth month,
            BigDecimal total
    ) {}

    public static List<MonthlyTotal> totals(List<Sale> sales) {
        List<Sale> input = List.copyOf(
                Objects.requireNonNull(sales, "sales"));

        // Kiểu trung gian chỉ cần trong phương thức này.
        record NormalizedSale(
                String region,
                YearMonth month,
                BigDecimal amount
        ) {
            NormalizedSale {
                Objects.requireNonNull(region, "region");
                region = region.strip().toUpperCase(Locale.ROOT);
                if (region.isEmpty()) {
                    throw new IllegalArgumentException("region must not be blank");
                }
                Objects.requireNonNull(month, "month");
                Objects.requireNonNull(amount, "amount");
            }
        }

        // Khóa nhóm cũng chỉ có ý nghĩa trong phép tổng hợp này.
        record RegionMonth(String region, YearMonth month) {}

        Map<RegionMonth, BigDecimal> totals = input.stream()
                .map(sale -> new NormalizedSale(
                        sale.region(),
                        YearMonth.from(sale.soldOn()),
                        sale.amount()
                ))
                .filter(row -> row.amount().signum() > 0)
                .collect(Collectors.groupingBy(
                        row -> new RegionMonth(row.region(), row.month()),
                        Collectors.reducing(
                                BigDecimal.ZERO,
                                NormalizedSale::amount,
                                BigDecimal::add
                        )
                ));

        return totals.entrySet().stream()
                .map(entry -> new MonthlyTotal(
                        entry.getKey().region(),
                        entry.getKey().month(),
                        entry.getValue()
                ))
                .sorted(Comparator
                        .comparing(MonthlyTotal::region)
                        .thenComparing(MonthlyTotal::month))
                .toList();
    }
}
```

Sử dụng:

```java
List<SalesReport.Sale> sales = List.of(
        new SalesReport.Sale(
                "bac", LocalDate.of(2026, 11, 5),
                new BigDecimal("120000")),
        new SalesReport.Sale(
                "BAC", LocalDate.of(2026, 11, 18),
                new BigDecimal("80000")),
        new SalesReport.Sale(
                "nam", LocalDate.of(2026, 11, 20),
                new BigDecimal("150000")),
        new SalesReport.Sale(
                "bac", LocalDate.of(2026, 10, 9),
                new BigDecimal("50000"))
);

List<SalesReport.MonthlyTotal> report = SalesReport.totals(sales);
report.forEach(System.out::println);
```

Kết quả có ba dòng tổng hợp:

| Khu vực | Tháng | Tổng |
|---|---|---:|
| BAC | 2026-10 | 50000 |
| BAC | 2026-11 | 200000 |
| NAM | 2026-11 | 150000 |

### 3.1. Vai trò của từng local record

`NormalizedSale` đại diện một giao dịch sau khi chuẩn hóa. Nó gom ba giá trị có quan hệ: khu vực, tháng và số tiền. Việc chuyển `LocalDate` thành `YearMonth` được thực hiện đúng một lần trong bước `map`.

`RegionMonth` đại diện khóa nhóm. Hai dòng `NormalizedSale` có cùng khu vực và tháng sẽ tạo ra hai `RegionMonth` bằng nhau theo giá trị component. Vì vậy `groupingBy` đưa chúng vào cùng một nhóm.

Cả hai kiểu chỉ cần tồn tại trong `totals()`. Nếu khai báo chúng thành public record ở cấp class, phạm vi kiểu sẽ rộng hơn mục đích sử dụng và tạo thêm hợp đồng phải bảo trì.

### 3.2. Vì sao sao chép danh sách đầu vào?

`List.copyOf` tạo một danh sách không thể sửa và từ chối phần tử `null`. Phương thức làm việc trên snapshot danh sách đầu vào trong suốt pipeline, tránh trường hợp bên gọi sửa cấu trúc danh sách trong khi xử lý.

Đây là bản sao nông. Ví dụ vẫn an toàn vì `Sale` là record chỉ chứa `String`, `LocalDate` và `BigDecimal`, đều là kiểu bất biến. Nếu phần tử là object mutable, sao chép danh sách không làm bản thân các object đó bất biến.

### 3.3. Ý nghĩa của bước filter

`filter(row -> row.amount().signum() > 0)` loại giao dịch có số tiền bằng không. Đây là quy tắc báo cáo được chọn cho ví dụ, không phải yêu cầu của `groupingBy`. Nếu báo cáo cần đếm cả giao dịch có tổng bằng không, hãy bỏ filter hoặc thay bằng điều kiện phù hợp.

Dữ liệu đầu vào từ `Sale` đã từ chối số tiền âm. Nếu hệ thống cần biểu diễn hoàn tiền, hãy xác định rõ quy tắc: cho phép số tiền âm trong cùng nhóm, hay mô hình hóa loại giao dịch riêng. Không áp dụng filter chỉ để che dữ liệu không hợp lệ.

### 3.4. Vì sao chuyển về public record trước khi trả kết quả?

`RegionMonth` là local record, vì vậy không thể xuất hiện như kiểu khai báo trong chữ ký phương thức công khai của `totals()`. Phương thức chuyển mỗi entry thành `MonthlyTotal`, một record được khai báo ở cấp class và có thể dùng làm kiểu trả về.

Đây là ranh giới tốt: kiểu nội bộ chỉ phục vụ thuật toán nằm trong phương thức; kiểu trả về mô tả hợp đồng mà caller được phép sử dụng.

## 4. Dùng local record để gom dữ liệu qua nhiều bước map/filter

Một tình huống khác là kết hợp dữ liệu từ nhiều component trước khi lọc. Ví dụ tính tổng dòng hàng gồm mã hàng, số lượng, đơn giá và thành tiền:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

record OrderLine(String sku, int quantity, BigDecimal unitPrice) {
    OrderLine {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");
        if (sku.isBlank() || quantity <= 0 || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid order line");
        }
    }
}

public class OrderLineReports {
    public List<String> expensiveLines(List<OrderLine> lines) {
        record PricedLine(
                String sku,
                int quantity,
                BigDecimal subtotal
        ) {}

        return lines.stream()
                .map(line -> new PricedLine(
                        line.sku(),
                        line.quantity(),
                        line.unitPrice().multiply(BigDecimal.valueOf(line.quantity()))
                ))
                .filter(row -> row.subtotal().compareTo(new BigDecimal("100000")) >= 0)
                .sorted((a, b) -> b.subtotal().compareTo(a.subtotal()))
                .map(row -> row.sku() + ": " + row.subtotal())
                .toList();
    }
}
```

`PricedLine` biểu diễn kết quả của bước tính toán. Các bước sau không cần tính lại thành tiền hoặc giữ tham chiếu tới `OrderLine` chỉ để đọc ba giá trị. Tên component cho biết rõ dữ liệu nào được lọc và sắp xếp.

Trong một file thực tế, `OrderLine` có thể là kiểu domain hoặc record được khai báo ở cấp class/package. Local record `PricedLine` chỉ là hình dạng dữ liệu trung gian của phép xử lý này.

### 4.1. Local record làm khóa cho groupingBy

Khi cần nhóm theo nhiều chiều nhưng khóa chỉ dùng trong một phép thống kê, khai báo khóa ngay trong phương thức:

```java
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Collectors;

public class OrderStatistics {
    public record RegionStatusCount(
            String region,
            OrderStatus status,
            long count
    ) {}

    public List<RegionStatusCount> countByRegionAndStatus(List<Order> orders) {
        record RegionStatus(String region, OrderStatus status) {}

        Map<RegionStatus, Long> counts = orders.stream()
                .collect(Collectors.groupingBy(
                        order -> new RegionStatus(
                                order.region().strip().toUpperCase(Locale.ROOT),
                                order.status()
                        ),
                        Collectors.counting()
                ));

        return counts.entrySet().stream()
                .map(entry -> new RegionStatusCount(
                        entry.getKey().region(),
                        entry.getKey().status(),
                        entry.getValue()
                ))
                .toList();
    }
}
```

`RegionStatus` có equality theo cả khu vực và trạng thái. Map trung gian chỉ tồn tại trong phương thức. Trước khi trả về, dữ liệu được chuyển thành `RegionStatusCount`, một record được khai báo ở cấp class để caller truy cập từng chiều bằng kiểu cụ thể. Đoạn mã giả định các kiểu domain `Order` và `OrderStatus` đã có trong ứng dụng.

Ví dụ này giả định `Order` và `OrderStatus` là các kiểu domain đã có, và `region()` luôn trả chuỗi khác `null`. Trong mã thực tế, nên chuẩn hóa/kiểm tra khu vực tại constructor hoặc hàm chuyển đổi phù hợp để tránh lặp quy tắc.

## 5. Local record so với Map.Entry và các kiểu tuple

`Map.Entry<K,V>` rất phù hợp khi dữ liệu đúng nghĩa là một cặp key/value, chẳng hạn entry của map. Nhưng nếu dữ liệu trung gian có ba trường hoặc có ý nghĩa riêng, local record thường dễ hiểu hơn.

Ví dụ cặp giá trị có thể dùng `Map.entry`:

```java
Map<String, Integer> stock = Map.of("BOOK", 10, "PEN", 25);

List<Map.Entry<String, Integer>> entries = stock.entrySet().stream()
        .toList();
```

Nhưng với dữ liệu gồm mã hàng, số lượng và đơn giá, record giúp đặt tên cho cả ba thành phần:

```java
record StockLine(String sku, int quantity, BigDecimal unitPrice) {}
```

So sánh:

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Một cặp key/value đúng nghĩa | `Map.Entry<K,V>` |
| Hai hoặc nhiều giá trị có tên và ý nghĩa riêng, chỉ dùng trong một phương thức | Local record |
| Kiểu dữ liệu dùng chung giữa nhiều phương thức/package | Record cấp class hoặc package |
| Cần trạng thái thay đổi hoặc kế thừa class | Class thông thường |
| Chỉ cần một giá trị đơn giản | Truyền trực tiếp component |

Tránh dùng `Object[]`, `List<Object>` hoặc `Map<String,Object>` chỉ để né khai báo kiểu. Chúng làm mất tên component hoặc kiểm tra kiểu tĩnh, khiến pipeline khó đọc và dễ phát sinh lỗi ép kiểu.

## 6. Local record và generic Stream pipeline

Local record có thể khai báo tham số kiểu của riêng nó:

```java
public <T> List<String> describeAll(
        List<T> values,
        Function<T, String> formatter
) {
    record Formatted<U>(U original, String text) {}

    return values.stream()
            .map(value -> new Formatted<T>(
                    value,
                    formatter.apply(value)
            ))
            .filter(item -> !item.text().isBlank())
            .map(Formatted::text)
            .toList();
}
```

`Formatted<U>` có generic parameter riêng. Nó không lấy `T` từ phương thức theo kiểu capture; thay vào đó, phương thức truyền kiểu `T` vào generic record khi tạo instance. Cách này hữu ích khi pipeline cần giữ cả giá trị gốc và biểu diễn đã định dạng trong một số bước.

Ví dụ trên cần import `java.util.List` và `java.util.function.Function`. Kiểu `Formatted` chỉ được dùng trong phương thức, vì vậy caller không phải biết chi tiết triển khai trung gian.

## 7. Phạm vi, khả năng tái sử dụng và giới hạn

Local record chỉ phù hợp khi dữ liệu trung gian gắn với một phương thức hoặc một block. Hãy đưa record lên cấp class/package khi:

- Nhiều phương thức cần cùng một kiểu trung gian.
- Kiểu xuất hiện trong chữ ký phương thức, API hoặc module khác.
- Kiểu là một khái niệm miền có tên ổn định, cần tài liệu và kiểm thử riêng.
- Cần dùng làm payload lâu dài cho cache, message, persistence hoặc serialization.

Không nên đưa mọi kiểu trung gian thành public record. Điều đó làm lộ chi tiết triển khai và khiến thay đổi nội bộ có thể ảnh hưởng caller. Ngược lại, cũng không nên giữ local record nếu nhiều phương thức đang phải định nghĩa lại cùng một cấu trúc.

### 7.1. Local record không phải nơi giữ trạng thái pipeline

Record có component final, nên local record phù hợp để mang dữ liệu giữa các bước. Nếu thuật toán cần bộ đếm thay đổi, cache, accumulator mutable hoặc cập nhật trạng thái nhiều lần, hãy dùng collector phù hợp, một class quản lý trạng thái có kiểm soát hoặc các phép tổng hợp chuẩn của Stream.

Ví dụ, không nên tạo local record chỉ để chứa một biến đếm rồi thay đổi nó. Với tổng số, dùng `Collectors.counting()`; với tổng số nguyên, dùng `summingInt()`; với tổng tiền, dùng `reducing()` hoặc một collector phù hợp.

### 7.2. Tránh tạo local record quá nhỏ hoặc quá nhiều

Không cần khai báo record cho mọi phép map. Nếu chỉ chuyển một giá trị sang chuỗi hoặc lấy một component, lambda đơn giản là đủ. Local record phát huy tác dụng khi có nhiều giá trị liên quan, cần đặt tên, kiểm tra hợp lệ hoặc dùng equality theo giá trị.

Một pipeline có quá nhiều kiểu trung gian liên tiếp có thể cho thấy phương thức đang làm quá nhiều việc. Hãy tách thành các phương thức nhỏ hoặc tạo kiểu domain/DTO có tên nếu mỗi bước là một khái niệm độc lập.

## 8. Stream.toList() và kết quả pipeline trong Java hiện đại

Từ Java 16, `Stream.toList()` trả về một danh sách không thể sửa (*unmodifiable list*). API này tiếp tục phù hợp khi muốn lấy kết quả pipeline thành danh sách chỉ đọc:

```java
List<String> names = users.stream()
        .map(User::displayName)
        .filter(Objects::nonNull)
        .toList();
```

Danh sách trả về không hỗ trợ thao tác thêm, xóa hoặc thay thế phần tử. Đây là tính bất biến của cấu trúc danh sách, không phải sao chép sâu object bên trong. Nếu phần tử là mutable, trạng thái của phần tử vẫn có thể thay đổi.

Nếu caller cần danh sách mutable để thêm/xóa, hãy tạo rõ ràng:

```java
List<String> mutableNames = new ArrayList<>(
        users.stream()
                .map(User::displayName)
                .toList()
);
```

`Collectors.toList()` và `Stream.toList()` không có cùng cam kết về khả năng sửa: collector `toList()` không đảm bảo kiểu hoặc khả năng sửa cụ thể, trong khi `Stream.toList()` trả danh sách unmodifiable. Chọn API theo hợp đồng cần thiết.

## 9. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ local record capture biến local | Code không biên dịch | Truyền giá trị cần thiết qua component |
| Dùng local record trong chữ ký public | Kiểu local không thể được tham chiếu ở ngoài block | Chuyển sang record cấp class hoặc đổi kết quả trả về |
| Dùng `Object[]` làm tuple | Phải nhớ index và ép kiểu | Tạo local record có component rõ nghĩa |
| Khai báo local record cho một giá trị đơn | Tăng độ phức tạp không cần thiết | Dùng trực tiếp giá trị hoặc lambda |
| Dùng local record chứa collection mutable làm key | Equality/hashCode có thể thay đổi | Sao chép phòng vệ và dùng phần tử bất biến |
| Tạo nhiều local record trùng cấu trúc ở nhiều phương thức | Lặp code, khó thống nhất | Đưa kiểu dùng chung lên cấp class/package |
| Trả local record ra ngoài qua Object | Caller không thể dùng kiểu một cách an toàn | Chuyển sang DTO/record công khai trước khi return |
| Nghĩ `Stream.toList()` là mutable | Có thể gặp UnsupportedOperationException khi sửa | Dùng `new ArrayList<>(stream.toList())` nếu cần sửa |

## 10. Checklist thiết kế

Trước khi thêm local record vào pipeline, hãy tự hỏi:

1. Dữ liệu trung gian có từ hai thành phần trở lên và mỗi thành phần có ý nghĩa riêng không?
2. Tên component có giúp pipeline dễ đọc hơn không?
3. Kiểu chỉ được dùng trong một phương thức/block hay cần chia sẻ rộng hơn?
4. Local record có đang cố truy cập biến local hoặc instance bên ngoài không?
5. Các component có bất biến hoặc được sao chép phòng vệ khi cần không?
6. Có thể dùng downstream collector thay cho việc tự giữ trạng thái mutable không?
7. Kết quả trả về đã được chuyển sang kiểu có thể truy cập từ caller chưa?
8. Danh sách kết quả có cần mutable hay unmodifiable?

## 11. Bài tập vận dụng

**Bài 1 — Thống kê đơn hàng:** Tạo phương thức nhận danh sách đơn hàng, khai báo local record `OrderMetric(orderId, customerId, total)`, dùng pipeline để lọc đơn có tổng lớn hơn ngưỡng, sắp xếp theo tổng giảm dần và trả về danh sách mã đơn.

**Bài 2 — Nhóm theo khu vực và tháng:** Khai báo local record `RegionMonth` bên trong phương thức thống kê. Dùng `groupingBy` để đếm số giao dịch theo cả hai chiều. Tra cứu một nhóm bằng cách tạo key mới.

**Bài 3 — Ghép dữ liệu đã định dạng:** Với danh sách nhân viên, tạo local generic record giữ object gốc và tên đã định dạng. Lọc những tên rỗng rồi chuyển thành danh sách chuỗi. Giải thích vì sao record không capture formatter từ phạm vi ngoài.

**Bài 4 — So sánh cách biểu diễn:** Cùng một pipeline, thử dùng `Object[]`, `Map.Entry` và local record để giữ ba giá trị. So sánh khả năng đọc, kiểm tra kiểu và bảo trì.

**Bài 5 — Ranh giới API:** Viết một phương thức dùng local record làm kiểu trung gian nhưng trả về public record `MonthlySummary`. Giải thích vì sao kiểu nội bộ không nên trở thành hợp đồng của caller.

---

**Ghi nhớ:** Local record là công cụ gọn để đặt tên cho dữ liệu trung gian có cấu trúc bên trong một phương thức. Trong Stream pipeline, nó giúp các bước map, filter, grouping và sorting làm việc với component có kiểu rõ ràng. Hãy dùng nó khi dữ liệu có ý nghĩa riêng và chỉ cần trong phạm vi cục bộ; chuyển sang record cấp class khi kiểu đó trở thành hợp đồng dùng chung.
