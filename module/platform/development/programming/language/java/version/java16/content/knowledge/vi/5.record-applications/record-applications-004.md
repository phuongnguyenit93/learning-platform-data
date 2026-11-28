# Dùng record làm khóa ghép cho groupingBy và tra cứu dữ liệu

> **Học phần:** `JAVA_VERSION_JAVA16` · **Chương:** Ứng dụng record. Record được chuẩn hóa từ Java 16 và tiếp tục hữu ích trong Java hiện đại khi cần biểu diễn dữ liệu theo giá trị. Bài học này hướng dẫn dùng record làm **khóa ghép** (*composite key*) trong `Map`, `Collectors.groupingBy` và các thao tác tra cứu.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao khóa gồm nhiều trường cần quy tắc `equals()` và `hashCode()` nhất quán.
- Dùng record biểu diễn khóa ghép thay cho việc ghép chuỗi hoặc lồng nhiều `Map` khi không cần thiết.
- Nhóm dữ liệu theo nhiều chiều bằng `Collectors.groupingBy` và downstream collector.
- Tra cứu kết quả nhóm bằng một record key mới có cùng giá trị.
- Thiết kế component của khóa ổn định, chuẩn hóa dữ liệu và tránh lỗi do giá trị mutable hoặc quy tắc equality đặc biệt.

## 1. Khóa ghép là gì?

Một khóa đơn xác định một nhóm bằng một giá trị, ví dụ mã khách hàng. Nhưng báo cáo và thống kê thường cần nhiều chiều. Ta có thể nhóm doanh thu theo **khu vực và tháng**, số đơn theo **khách hàng và trạng thái**, hoặc số lượng sản phẩm theo **kho và mã hàng**.

Giả sử dữ liệu bán hàng có khu vực, tháng phát sinh, mã giao dịch và số tiền. Muốn nhóm theo khu vực *và* tháng, mỗi nhóm được xác định bởi một cặp giá trị:

```text
(region, month)
```

Nếu chỉ dùng `region`, các tháng khác nhau bị gộp. Nếu chỉ dùng `month`, các khu vực khác nhau bị gộp. Khóa ghép giữ cả hai chiều trong cùng một giá trị.

### 1.1. Vì sao không ghép chuỗi làm khóa?

Có thể viết:

```java
String key = region + "|" + month;
```

Cách này ngắn nhưng có nhược điểm:

- Phải tự quy định dấu phân cách và xử lý trường hợp dữ liệu chứa dấu đó.
- Mất thông tin kiểu: khu vực là chuỗi, tháng là `YearMonth`, nhưng sau khi ghép chỉ còn `String`.
- Khi tra cứu, phải tạo lại chuỗi đúng cùng quy tắc chuẩn hóa.
- Khi thêm chiều thứ ba, logic ghép và phân tích chuỗi trở nên khó bảo trì.

Record giữ từng thành phần đúng kiểu dữ liệu, đặt tên rõ ràng và tự sinh equality theo các component.

## 2. Thiết kế record làm khóa ghép

Một khóa khu vực-tháng:

```java
import java.time.YearMonth;
import java.util.Locale;
import java.util.Objects;

public record SalesKey(String region, YearMonth month) {
    public SalesKey {
        Objects.requireNonNull(region, "region");
        region = region.strip().toUpperCase(Locale.ROOT);
        if (region.isEmpty()) {
            throw new IllegalArgumentException("region must not be blank");
        }
        Objects.requireNonNull(month, "month");
    }
}
```

Ví dụ:

```java
SalesKey first = new SalesKey("bac", YearMonth.of(2026, 11));
SalesKey second = new SalesKey("BAC", YearMonth.of(2026, 11));

System.out.println(first.equals(second)); // true
System.out.println(first.hashCode() == second.hashCode()); // true
```

Record tự sinh `equals()` và `hashCode()` dựa trên các component. Compact constructor chuẩn hóa khu vực trước khi giá trị được gán vào trường, vì vậy hai cách viết `"bac"` và `"BAC"` trở thành cùng một khóa.

`YearMonth` thuộc `java.time` và là kiểu bất biến. Khóa ghép tốt nên dùng component có giá trị ổn định sau khi tạo, ví dụ `String` đã chuẩn hóa, enum, `UUID`, `LocalDate`, `YearMonth` hoặc kiểu value object bất biến.

### 2.1. Equality của record key hoạt động thế nào?

Với record:

```java
record CustomerStatusKey(long customerId, String status) {}
```

Hai instance bằng nhau khi từng component tương ứng bằng nhau theo quy tắc equality của kiểu component. Với primitive, Java so sánh giá trị tương ứng; với object, quy tắc `equals()` của component được dùng.

```java
CustomerStatusKey a = new CustomerStatusKey(42L, "ACTIVE");
CustomerStatusKey b = new CustomerStatusKey(42L, "ACTIVE");
CustomerStatusKey c = new CustomerStatusKey(42L, "LOCKED");

System.out.println(a.equals(b)); // true
System.out.println(a.equals(c)); // false
```

Quy tắc quan trọng của `Map` là: hai khóa bằng nhau phải có `hashCode()` bằng nhau. Record cung cấp cặp phương thức nhất quán này theo các component. Khi dùng record làm khóa `HashMap` hoặc kết quả nhóm, thông thường không cần tự viết lại `equals()`/`hashCode()`.

Hash code giống nhau chưa đủ để kết luận hai khóa bằng nhau. Hash map dùng `equals()` để phân biệt các khóa khi có va chạm hash; va chạm là tình huống hợp lệ và được cấu trúc dữ liệu xử lý.

### 2.2. Khóa ghép có ba hoặc nhiều chiều

Record không giới hạn ở hai component:

```java
import java.time.YearMonth;

public record InventoryKey(
        String warehouseCode,
        String productCode,
        YearMonth month
) {}
```

Khóa trên xác định tồn kho theo kho, sản phẩm và tháng. Hãy thêm component khi chiều đó thật sự tham gia định nghĩa một nhóm riêng. Nếu một trường chỉ là thông tin mô tả hoặc giá trị tổng hợp, không nên đưa nó vào khóa vì sẽ làm số nhóm tăng và thay đổi ý nghĩa equality.

## 3. Chuẩn bị dữ liệu minh họa

Ta dùng một kiểu `Sale` chứa dữ liệu bán hàng. `Sale` và `SalesKey` được đặt bên trong class tiện ích để ví dụ nằm gọn trong một file. Member record được ngầm định là static, nên không cần instance của class bao ngoài để tạo chúng.

File `SalesAnalytics.java`:

```java
import java.math.BigDecimal;
import java.time.YearMonth;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

public final class SalesAnalytics {
    private SalesAnalytics() {}

    public record Sale(
            String id,
            String region,
            YearMonth month,
            BigDecimal amount
    ) {
        public Sale {
            Objects.requireNonNull(id, "id");
            id = id.strip();
            if (id.isEmpty()) {
                throw new IllegalArgumentException("id must not be blank");
            }
            region = normalizeRegion(region);
            Objects.requireNonNull(month, "month");
            Objects.requireNonNull(amount, "amount");
            if (amount.signum() < 0) {
                throw new IllegalArgumentException("amount must not be negative");
            }
        }
    }

    public record SalesKey(String region, YearMonth month) {
        public SalesKey {
            region = normalizeRegion(region);
            Objects.requireNonNull(month, "month");
        }
    }

    public static Map<SalesKey, List<Sale>> groupSales(List<Sale> sales) {
        Objects.requireNonNull(sales, "sales");
        return sales.stream()
                .collect(Collectors.groupingBy(SalesAnalytics::keyOf));
    }

    public static Map<SalesKey, Long> countSales(List<Sale> sales) {
        Objects.requireNonNull(sales, "sales");
        return sales.stream()
                .collect(Collectors.groupingBy(
                        SalesAnalytics::keyOf,
                        Collectors.counting()
                ));
    }

    public static Map<SalesKey, BigDecimal> totalSales(List<Sale> sales) {
        Objects.requireNonNull(sales, "sales");
        return sales.stream()
                .collect(Collectors.groupingBy(
                        SalesAnalytics::keyOf,
                        Collectors.reducing(
                                BigDecimal.ZERO,
                                Sale::amount,
                                BigDecimal::add
                        )
                ));
    }

    private static SalesKey keyOf(Sale sale) {
        return new SalesKey(sale.region(), sale.month());
    }

    private static String normalizeRegion(String region) {
        Objects.requireNonNull(region, "region");
        String normalized = region.strip().toUpperCase(Locale.ROOT);
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("region must not be blank");
        }
        return normalized;
    }
}
```

Trong ví dụ:

- `Sale` là dữ liệu một giao dịch.
- `SalesKey` định danh nhóm theo khu vực và tháng.
- `keyOf` chuyển một giao dịch thành khóa cho collector.
- `normalizeRegion` đảm bảo cùng một khu vực có cách biểu diễn nhất quán.

`amount` được giả định là doanh thu không âm. Hệ thống thực tế có thể biểu diễn hoàn tiền hoặc điều chỉnh bằng loại giao dịch riêng hoặc số tiền có dấu theo quy tắc nghiệp vụ đã xác định.

## 4. Dùng record key với `Collectors.groupingBy`

`groupingBy` nhận một hàm phân loại (*classifier*) để xác định khóa cho từng phần tử. Khi classifier trả về record key, collector nhóm các phần tử có key bằng nhau vào cùng một nhóm.

### 4.1. Nhóm các giao dịch thành danh sách

```java
List<SalesAnalytics.Sale> sales = List.of(
        new SalesAnalytics.Sale(
                "S-001", "bac", YearMonth.of(2026, 11),
                new BigDecimal("120000")),
        new SalesAnalytics.Sale(
                "S-002", "BAC", YearMonth.of(2026, 11),
                new BigDecimal("80000")),
        new SalesAnalytics.Sale(
                "S-003", "nam", YearMonth.of(2026, 11),
                new BigDecimal("150000")),
        new SalesAnalytics.Sale(
                "S-004", "bac", YearMonth.of(2026, 10),
                new BigDecimal("50000"))
);

Map<SalesAnalytics.SalesKey, List<SalesAnalytics.Sale>> grouped =
        SalesAnalytics.groupSales(sales);
```

Kết quả có ba nhóm:

| Khóa | Các giao dịch |
|---|---|
| `(BAC, 2026-11)` | S-001, S-002 |
| `(NAM, 2026-11)` | S-003 |
| `(BAC, 2026-10)` | S-004 |

Hai giao dịch đầu tiên cùng nhóm vì region đã được chuẩn hóa thành `BAC` và month giống nhau. Nếu chỉ nhóm theo region, các giao dịch tháng 10 và tháng 11 sẽ bị gộp, làm sai yêu cầu thống kê theo tháng.

### 4.2. Nhóm và đếm số phần tử

Nếu chỉ cần số giao dịch trong mỗi nhóm, không cần giữ toàn bộ danh sách:

```java
Map<SalesAnalytics.SalesKey, Long> counts =
        SalesAnalytics.countSales(sales);
```

Kết quả minh họa:

| Khóa | Số giao dịch |
|---|---:|
| `(BAC, 2026-11)` | 2 |
| `(NAM, 2026-11)` | 1 |
| `(BAC, 2026-10)` | 1 |

`Collectors.counting()` là downstream collector: `groupingBy` quyết định khóa, còn `counting` tính số phần tử trong từng nhóm. Cách này tránh tạo danh sách nếu ứng dụng chỉ cần số đếm.

### 4.3. Nhóm và tính tổng doanh thu

Với `BigDecimal`, dùng phép cộng chính xác theo kiểu số thập phân:

```java
Map<SalesAnalytics.SalesKey, BigDecimal> totals =
        SalesAnalytics.totalSales(sales);
```

Kết quả:

| Khóa | Tổng doanh thu |
|---|---:|
| `(BAC, 2026-11)` | 200000 |
| `(NAM, 2026-11)` | 150000 |
| `(BAC, 2026-10)` | 50000 |

Trong `totalSales`, downstream collector `reducing` bắt đầu từ `BigDecimal.ZERO` và cộng `Sale.amount()` của từng phần tử. Không dùng `double` cho phép tính tiền nếu cần độ chính xác thập phân.

### 4.4. Chuyển đổi phần tử trong mỗi nhóm

Có thể dùng `mapping` để chỉ giữ mã giao dịch trong mỗi nhóm:

```java
Map<SalesAnalytics.SalesKey, List<String>> idsByPeriod =
        sales.stream().collect(Collectors.groupingBy(
                sale -> new SalesAnalytics.SalesKey(
                        sale.region(), sale.month()),
                Collectors.mapping(
                        SalesAnalytics.Sale::id,
                        Collectors.toList()
                )
        ));
```

Ở đây:

- `groupingBy` phân loại theo `SalesKey`.
- `mapping` chuyển từng `Sale` thành `id`.
- `toList` gom các mã vào danh sách.

`Collectors.toList()` không cam kết danh sách kết quả là immutable. Nếu kết quả cần làm snapshot không sửa được, có thể dùng `Collectors.toUnmodifiableList()` hoặc sao chép bằng `List.copyOf` sau khi nhóm.

## 5. Tra cứu bằng một record key mới

Sau khi nhóm dữ liệu, ta thường cần lấy kết quả cho một khu vực và tháng cụ thể. Tạo một record mới có cùng component là đủ:

```java
SalesAnalytics.SalesKey lookupKey =
        new SalesAnalytics.SalesKey(
                "bac",
                YearMonth.of(2026, 11)
        );

List<SalesAnalytics.Sale> novemberSales =
        grouped.getOrDefault(lookupKey, List.of());

long novemberCount = counts.getOrDefault(lookupKey, 0L);
BigDecimal novemberTotal =
        totals.getOrDefault(lookupKey, BigDecimal.ZERO);
```

Dù `lookupKey` là một instance khác với key được collector tạo ra, `Map` vẫn tìm thấy nhóm vì `equals()` và `hashCode()` của hai record dựa trên cùng giá trị component.

Không cần lưu lại instance khóa ban đầu hoặc tự viết hàm so sánh hai trường mỗi khi tra cứu.

### 5.1. Dùng `containsKey` khi cần phân biệt không có nhóm và nhóm có giá trị mặc định

Với map chứa số đếm, `getOrDefault(key, 0L)` tiện cho thống kê. Nhưng nếu cần phân biệt “không tồn tại nhóm” với “nhóm tồn tại và giá trị bằng 0”, hãy kiểm tra `containsKey`:

```java
if (counts.containsKey(lookupKey)) {
    System.out.println("Nhóm đã xuất hiện trong dữ liệu");
} else {
    System.out.println("Không có giao dịch cho khóa này");
}
```

Với `Map<SalesKey, List<Sale>>`, một nhóm tồn tại thường có danh sách không rỗng. Cách phân biệt rõ ràng vẫn hữu ích khi dữ liệu có quy tắc đặc biệt hoặc map được tạo từ nguồn khác.

### 5.2. Tra cứu từ khóa do người dùng nhập

Dữ liệu đầu vào cần đi qua cùng quy tắc chuẩn hóa như dữ liệu đã nhóm. Ví dụ `"bac"` được chuyển thành `"BAC"` trong constructor của `SalesKey`. Nếu nhóm dữ liệu dùng chuẩn hóa nhưng lookup lại dùng một kiểu key khác hoặc không chuẩn hóa, kết quả có thể không tìm thấy.

Đặt quy tắc trong constructor của record key giúp mọi nơi tạo khóa đều có cùng hành vi.

## 6. Khóa ghép so với Map lồng nhau

Một cách khác là nhóm theo chiều thứ nhất rồi nhóm tiếp theo chiều thứ hai:

```java
Map<String, Map<YearMonth, Long>> countsByRegionThenMonth =
        sales.stream().collect(Collectors.groupingBy(
                SalesAnalytics.Sale::region,
                Collectors.groupingBy(
                        SalesAnalytics.Sale::month,
                        Collectors.counting()
                )
        ));
```

Tra cứu:

```java
String region = "BAC";
YearMonth month = YearMonth.of(2026, 11);

long count = countsByRegionThenMonth
        .getOrDefault(region, Map.of())
        .getOrDefault(month, 0L);
```

Cả hai cách đều hợp lệ, nhưng diễn tả cấu trúc khác nhau:

| Tiêu chí | Record key ghép | Map lồng nhau |
|---|---|---|
| Mô hình khóa | Một giá trị có tên và kiểu cho từng chiều | Một map cho mỗi cấp |
| Tra cứu theo đủ các chiều | Tạo một record rồi gọi `get` | Gọi `get` theo từng cấp |
| Truy vấn theo một chiều | Cần lọc key hoặc nhóm bổ sung | Có thể lấy map cấp đầu tiên |
| Dùng làm tham số phương thức | Một kiểu key rõ nghĩa | Phải truyền nhiều tham số hoặc map |
| Thêm chiều mới | Thêm component vào record key | Thêm một cấp map |
| Hợp đồng miền | Có thể đặt validation và chuẩn hóa trong constructor | Quy tắc key thường nằm ở nơi tạo map |

**Chọn record key** khi các chiều kết hợp tạo thành một đơn vị định danh và ứng dụng thường tra cứu theo toàn bộ bộ giá trị. **Chọn map lồng nhau** khi việc truy cập phân cấp là mục tiêu chính, chẳng hạn cần lấy tất cả tháng của một khu vực rồi tiếp tục thao tác trên tập con đó.

Không có cách nào luôn tốt hơn. Chọn cấu trúc phản ánh cách ứng dụng truy vấn dữ liệu.

## 7. Các downstream collector thường dùng

Record key kết hợp được với nhiều collector tiêu chuẩn:

| Nhu cầu | Downstream collector | Kiểu kết quả |
|---|---|---|
| Đếm số phần tử | `Collectors.counting()` | `Map<Key, Long>` |
| Tính tổng số nguyên | `Collectors.summingInt(...)` | `Map<Key, Integer>` |
| Tính tổng số dài | `Collectors.summingLong(...)` | `Map<Key, Long>` |
| Chuyển đổi phần tử | `Collectors.mapping(...)` | `Map<Key, Collection>` |
| Tạo thống kê nhiều chỉ số | `Collectors.collectingAndThen(...)` hoặc collector tùy chỉnh | `Map<Key, Result>` |
| Gom các phần tử | `Collectors.toList()` hoặc `toSet()` | `Map<Key, List/Set>` |

Ví dụ đếm số giao dịch theo khóa:

```java
Map<SalesAnalytics.SalesKey, Long> counts =
        sales.stream().collect(Collectors.groupingBy(
                sale -> new SalesAnalytics.SalesKey(
                        sale.region(), sale.month()),
                Collectors.counting()
        ));
```

Ví dụ gom mã giao dịch theo khóa:

```java
Map<SalesAnalytics.SalesKey, List<String>> ids =
        sales.stream().collect(Collectors.groupingBy(
                sale -> new SalesAnalytics.SalesKey(
                        sale.region(), sale.month()),
                Collectors.mapping(
                        SalesAnalytics.Sale::id,
                        Collectors.toList()
                )
        ));
```

Downstream collector không thay đổi cách xác định key. Nó chỉ quyết định cách tổng hợp các phần tử đã được phân nhóm.

## 8. Những lỗi quan trọng khi thiết kế composite key

### 8.1. Đưa component mutable vào key

Khóa dùng trong `HashMap`/`HashSet` phải giữ ổn định các giá trị tham gia `equals()` và `hashCode()` trong suốt thời gian được lưu trữ. Nếu component mutable đổi sau khi đưa key vào map, hash code có thể đổi và việc tra cứu có thể không còn tìm thấy entry.

Ví dụ thiết kế rủi ro:

```java
import java.util.List;

record MutableKey(List<String> tags) {}
```

Nếu danh sách `tags` bị sửa sau khi key đã được dùng trong map, equality và hash code của record có thể thay đổi vì `List` so sánh theo nội dung.

Nếu thật sự cần giữ collection trong key, hãy sao chép phòng vệ:

```java
import java.util.List;
import java.util.Objects;

record StableKey(List<String> tags) {
    StableKey {
        tags = List.copyOf(Objects.requireNonNull(tags, "tags"));
    }
}
```

Cách này ngăn sửa danh sách thông qua tham chiếu bên ngoài. Các phần tử của danh sách cũng phải bất biến hoặc được sao chép phù hợp; `List.copyOf` chỉ tạo bản sao nông.

### 8.2. Mảng không có equality theo nội dung mặc định

Không nên giả định hai mảng cùng phần tử sẽ làm hai record key bằng nhau:

```java
record ByteKey(byte[] bytes) {}

ByteKey first = new ByteKey(new byte[] {1, 2});
ByteKey second = new ByteKey(new byte[] {1, 2});

System.out.println(first.equals(second)); // false
```

Mảng dùng equality theo danh tính tham chiếu trong ngữ cảnh này, nên hai mảng riêng biệt không tự động bằng nhau theo nội dung. Nếu khóa cần so sánh nội dung nhị phân, hãy dùng một kiểu value object chuyên biệt có sao chép phòng vệ và triển khai `equals()`/`hashCode()` theo nội dung, hoặc chuyển dữ liệu sang dạng biểu diễn bất biến thích hợp.

### 8.3. `BigDecimal` phân biệt scale

`BigDecimal.equals()` xét cả giá trị và scale:

```java
record AmountKey(BigDecimal amount) {}

System.out.println(
        new AmountKey(new BigDecimal("10.0"))
                .equals(new AmountKey(new BigDecimal("10.00")))
); // false
```

Nếu nghiệp vụ xem hai số này là cùng một khóa, hãy chuẩn hóa khi tạo record:

```java
record NormalizedAmountKey(BigDecimal amount) {
    NormalizedAmountKey {
        Objects.requireNonNull(amount, "amount");
        amount = amount.stripTrailingZeros();
    }
}
```

Chỉ chuẩn hóa khi quy tắc nghiệp vụ xác định rõ scale không mang ý nghĩa. Với giá tiền, số chữ số thập phân hoặc đơn vị tiền có thể quan trọng; không nên tùy tiện bỏ scale nếu nó là một phần hợp đồng.

### 8.4. Chuẩn hóa chuỗi và locale

Nếu khóa không phân biệt chữ hoa/chữ thường, hãy chuẩn hóa một lần trong constructor. Khi chuẩn hóa mã định danh kỹ thuật, `toUpperCase(Locale.ROOT)` tránh phụ thuộc locale mặc định của máy chạy.

Không áp dụng chuẩn hóa tùy tiện cho mọi văn bản. Tên người, địa chỉ hiển thị hoặc nội dung ngôn ngữ tự nhiên có thể cần quy tắc khác. Equality phải phản ánh định nghĩa cùng giá trị của miền nghiệp vụ.

### 8.5. Xử lý null nhất quán

Không nên để một chiều của khóa lúc có giá trị, lúc `null` mà không có quy tắc rõ ràng. Trong ví dụ `SalesKey`, constructor từ chối region rỗng và month `null`.

`Collectors.groupingBy` yêu cầu classifier tạo ra key không `null`. Nếu classifier trả về `null`, thao tác nhóm có thể ném `NullPointerException`. Hãy xác thực dữ liệu đầu vào hoặc biểu diễn trạng thái chưa biết bằng một giá trị miền rõ ràng, chẳng hạn enum `UNKNOWN`, khi điều đó phù hợp nghiệp vụ.

## 9. Thứ tự kết quả và tính bất biến của Map

Overload thông thường `groupingBy(classifier)` không cam kết thứ tự duyệt của map kết quả. Nếu cần trình bày kết quả theo khu vực rồi theo tháng, hãy sắp xếp các entry khi đọc:

```java
import java.util.Comparator;

Comparator<SalesAnalytics.SalesKey> order =
        Comparator.comparing(SalesAnalytics.SalesKey::region)
                .thenComparing(SalesAnalytics.SalesKey::month);

counts.entrySet().stream()
        .sorted(Map.Entry.comparingByKey(order))
        .forEach(entry -> System.out.println(
                entry.getKey() + " -> " + entry.getValue()));
```

Có thể chọn map factory trong overload `groupingBy(classifier, mapFactory, downstream)` nếu cần một kiểu map cụ thể. Dù vậy, thứ tự hiển thị nên được quy định rõ ở tầng trình bày hoặc bằng comparator, thay vì dựa vào hành vi không được cam kết.

Map và các list được tạo từ collector `groupingBy` thường có thể thay đổi. Nếu cần trả snapshot không sửa được:

```java
Map<SalesAnalytics.SalesKey, List<SalesAnalytics.Sale>> immutableGroups =
        grouped.entrySet().stream()
                .collect(Collectors.toUnmodifiableMap(
                        Map.Entry::getKey,
                        entry -> List.copyOf(entry.getValue())
                ));
```

`Collectors.toUnmodifiableMap` tạo map không thể sửa; `List.copyOf` tạo danh sách không thể sửa cho từng nhóm. Trong ví dụ này, `SalesKey` và `Sale` đều chỉ chứa các kiểu bất biến, nên cấu trúc kết quả phù hợp để dùng như snapshot.

## 10. Khi nào nên dùng record key?

Dùng record làm khóa ghép khi:

- Một nhóm được định nghĩa bởi nhiều trường có tên và kiểu rõ ràng.
- Equality của nhóm chính là equality theo các component.
- Các component có giá trị ổn định, bất biến hoặc đã được chuẩn hóa.
- Ứng dụng cần truyền khóa giữa các phương thức hoặc dùng nó trong `Map`, cache hay tập hợp.
- Kiểu key riêng giúp tránh lặp logic ghép chuỗi và so sánh nhiều trường.

Cân nhắc cách khác khi:

- Chỉ có một chiều định danh: dùng trực tiếp component đó.
- Cần truy cập phân cấp thường xuyên: map lồng nhau có thể dễ đọc hơn.
- Khóa cần danh tính object hoặc trạng thái mutable: record key thường không phù hợp.
- Equality nghiệp vụ khác equality theo component: dùng một kiểu value object/class thiết kế equality có chủ đích.
- Khóa có component mutable hoặc quy tắc chuẩn hóa phức tạp: giải quyết invariant trước khi đưa vào map.

### Checklist

1. Record key có chứa đúng các chiều định nghĩa một nhóm không?
2. Component có kiểu dữ liệu phù hợp và ổn định không?
3. Constructor có chuẩn hóa và xác thực giá trị cần thiết không?
4. Quy tắc `equals()` được sinh có trùng với equality nghiệp vụ không?
5. Có component mảng, collection mutable hoặc kiểu mutable nào không?
6. Collector có downstream phù hợp để tránh giữ dữ liệu thừa không?
7. Cách tra cứu có tạo record key bằng cùng quy tắc chuẩn hóa không?
8. Thứ tự và khả năng sửa của map/list kết quả đã được xác định chưa?

## 11. Bài tập vận dụng

**Bài 1 — Đếm đơn hàng:** Tạo record `CustomerMonthKey(long customerId, YearMonth month)`. Dùng `groupingBy` và `counting` để đếm số đơn hàng theo khách hàng và tháng. Tra cứu số đơn của một khách hàng bằng một key mới.

**Bài 2 — Thống kê tồn kho:** Tạo `WarehouseProductKey(String warehouse, String productCode)`. Chuẩn hóa mã kho, mã sản phẩm trong constructor. Nhóm danh sách tồn kho theo khóa và tính tổng số lượng bằng downstream collector phù hợp.

**Bài 3 — Phân biệt map lồng nhau:** Cùng một tập dữ liệu, triển khai một lần với `Map<RegionMonthKey, List<Sale>>` và một lần với `Map<String, Map<YearMonth, List<Sale>>>`. So sánh độ rõ ràng khi tra cứu theo cả hai chiều và khi lấy toàn bộ dữ liệu của một khu vực.

**Bài 4 — Kiểm tra equality:** Thử tạo key với chuỗi khác chữ hoa/thường, `BigDecimal` khác scale và danh sách component bị sửa sau khi tạo. Giải thích kết quả equality và đề xuất cách chuẩn hóa hoặc sao chép phù hợp.

**Bài 5 — Snapshot kết quả:** Tạo map nhóm không thể sửa bằng `Collectors.toUnmodifiableMap` và `List.copyOf`. Kiểm tra thao tác sửa map, sửa list nhóm và thay đổi danh sách nguồn sau khi nhóm.

---

**Ghi nhớ:** Record cung cấp một cách khai báo khóa ghép rõ ràng, có kiểu và equality theo giá trị. Khi kết hợp với `Collectors.groupingBy`, downstream collector và `Map.get()`, ta có thể nhóm và tra cứu theo nhiều chiều mà không phải tự ghép chuỗi hoặc viết logic so sánh lặp lại. Chất lượng của khóa phụ thuộc vào việc chọn đúng component, chuẩn hóa nhất quán và giữ chúng ổn định trong suốt thời gian dùng làm key.
