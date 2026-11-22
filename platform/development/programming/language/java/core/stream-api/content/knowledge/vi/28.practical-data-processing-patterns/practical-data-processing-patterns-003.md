# Tổng hợp đơn hàng theo khách hàng và khoảng thời gian

> **Chương:** Mẫu xử lý dữ liệu thực tế  
> **Module:** `JAVA_STREAM_API` — xử lý dữ liệu khai báo với pipeline lazy, `filter`, `map`, `reduce`, `collect`; thực hành grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers, đồng thời hiểu giới hạn về trạng thái, tài nguyên và hiệu năng.

Báo cáo bán hàng thường không chỉ hỏi **“tổng doanh thu là bao nhiêu?”** mà còn hỏi **“khách hàng nào đã mua trong quý này, mỗi tháng có bao nhiêu đơn và tổng tiền của từng khách là bao nhiêu?”**. Để trả lời đúng, chương trình phải giải quyết đồng thời việc lọc trạng thái, xác định ranh giới thời gian, chuyển múi giờ, phân nhóm nhiều chiều và cộng tiền chính xác.

Bài thực hành này hướng dẫn xây dựng một báo cáo tự chứa trên **Java 17+**. Nguồn là danh sách đơn hàng có `customerId`, thời điểm ghi nhận dưới dạng `Instant`, trạng thái và tiền thanh toán. Kết quả gồm thống kê **theo từng khách hàng và từng tháng**, thống kê **tổng của mỗi khách**, cùng **tổng toàn kỳ**. Chương trình có kiểm thử ranh giới ngày, đơn hủy, nguồn rỗng, đảo thứ tự nguồn và xử lý song song.

## 1. Xác định hợp đồng nghiệp vụ trước khi viết Stream

Giả sử báo cáo có các điều kiện:

1. Chỉ tính đơn có trạng thái `PAID`; đơn `CANCELLED` không đóng góp vào doanh thu hoặc số lượng.
2. Mỗi đối tượng `Order` đại diện **một đơn hàng duy nhất**; mã `id` được giả định không trùng. Nếu nguồn chứa nhiều sự kiện của cùng một đơn thì cần khử trùng hoặc tính trạng thái cuối theo quy tắc riêng.
3. Thời điểm `recordedAt` là một `Instant` (mốc thời gian tuyệt đối). Ngày và tháng báo cáo được xác định **theo múi giờ nghiệp vụ**.
4. Khoảng thời gian báo cáo là **nửa mở**: `[startInclusive, endExclusive)`. Lấy đúng thời điểm bắt đầu và **không** lấy thời điểm bắt đầu kỳ kế tiếp.
5. Doanh thu cộng bằng `BigDecimal`, không dùng `double` để đại diện tiền.
6. Đầu ra sắp theo **mã khách hàng tăng dần**, rồi **tháng tăng dần** để không phụ thuộc thứ tự duyệt của `HashMap`.

Ví dụ cần báo cáo từ **01/01/2026 đến hết 31/03/2026** theo múi giờ `Asia/Ho_Chi_Minh`. Thay vì biểu diễn ngày cuối là `31/03 23:59:59` (có thể bỏ sót phần mili giây/nano giây), hãy dùng:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant start = LocalDate.of(2026, 1, 1)
        .atStartOfDay(zone)
        .toInstant();
Instant end = LocalDate.of(2026, 4, 1)
        .atStartOfDay(zone)
        .toInstant();

// Bao gồm: start <= recordedAt < end.
```

Thời gian tuyệt đối của hai biên trên là `2025-12-31T17:00:00Z` và `2026-03-31T17:00:00Z`. Nhờ sử dụng `LocalDate.atStartOfDay(zone)`, cách tính vẫn phù hợp với những múi giờ có quy tắc thay đổi độ lệch theo ngày; không nên giả định mọi ngày ở mọi múi giờ luôn dài đúng 24 giờ.

## 2. Thiết kế dữ liệu và khóa phân nhóm

Mô hình dữ liệu dùng các kiểu:

```java
enum Status { PAID, CANCELLED }

record Order(
        String id,
        String customerId,
        Instant recordedAt,
        BigDecimal amount,
        Status status
) {}

record CustomerMonth(String customerId, YearMonth month) {}
record Stats(long orderCount, BigDecimal revenue) {}
```

Các kiểu này được khai báo đầy đủ, kèm kiểm tra dữ liệu đầu vào, trong chương trình ở mục 5.

**Tại sao dùng `CustomerMonth` thay vì một chuỗi ghép kiểu `"C-A_2026-01"`?**

- Record làm khóa có cấu trúc rõ: `customerId` và `YearMonth` là hai trường khác nhau.
- `equals`/`hashCode` được tạo theo giá trị của từng trường, phù hợp cho `groupingBy`.
- Không cần tự thiết kế dấu phân cách hoặc xử lý trường hợp ID chứa dấu `_`.
- Có thể viết comparator rõ ràng theo khách rồi theo tháng.

Khi phân nhóm:

```java
CustomerMonth key = new CustomerMonth(
        order.customerId(),
        YearMonth.from(order.recordedAt().atZone(zone))
);
```

**Tháng phải được xác định sau khi chuyển sang `zone`.** Một đơn ghi nhận lúc `2026-01-31T17:00:00Z` là **00:00 ngày 01/02/2026** tại Việt Nam, nên thuộc **tháng 2** của báo cáo địa phương, không phải tháng 1.

## 3. Pipeline xử lý theo các giai đoạn

Ta chia bài toán thành ba bước chính:

```text
List<Order>
    |
    v
filter(status == PAID)
    |
filter(start <= recordedAt < end)
    |
    v
List<Order> eligible
    |
    +---- groupingBy(CustomerMonth, reducing(Stats)) ----> Map<CustomerMonth, Stats>
    |                                                       |
    |                                                       v
    |                                               Tổng theo khách+tháng
    |                                                       |
    |                                                       v
    |                                        toMap(customerId, Stats::plus)
    |                                                       |
    |                                                       v
    |                                               Tổng theo khách
    |                                                       |
    |                                                       v
    +----------------------------------------------- reduce(Stats::plus)
                                                            |
                                                            v
                                                       Tổng toàn kỳ
```

Những quyết định quan trọng:

- `filter` chỉ giữ `PAID` trong đúng khoảng thời gian.
- `groupingBy` nhận khóa gồm **khách hàng + tháng địa phương**.
- Downstream `reducing` trả `Stats` chứa cả **số đơn** và **doanh thu**, giúp không phải nhóm và cộng hai lần độc lập.
- `Stats::plus` gộp các thống kê trung gian; nó cần có phần tử trung hòa và tính kết hợp để hoạt động đúng khi Stream được chia nhánh song song.
- `TreeMap` được chọn để duyệt kết quả theo thứ tự xác định; đặc tính thứ tự này là yêu cầu của báo cáo, không phải hiệu ứng phụ của một `HashMap`.

## 4. Dữ liệu mẫu và kết quả mong đợi

Các thời điểm trong bảng dưới đây hiển thị theo **giờ Việt Nam (UTC+07:00)** để thấy rõ ranh giới:

| Đơn | Khách | Ngày giờ địa phương | Trạng thái | Thành tiền | Có tính? |
| --- | --- | --- | --- | ---: | --- |
| O-01 | C-A | 01/01/2026 00:00:00 | PAID | 100.10 | Có, biên bắt đầu |
| O-02 | C-A | 15/01/2026 17:00:00 | PAID | 200.20 | Có |
| O-03 | C-B | 31/01/2026 23:59:59 | PAID | 40.00 | Có, tháng 1 |
| O-04 | C-A | 01/02/2026 00:00:00 | PAID | 70.00 | Có, tháng 2 |
| O-05 | C-B | 10/02/2026 09:00:00 | PAID | 10.50 | Có |
| O-06 | C-A | 25/02/2026 19:00:00 | PAID | 90.20 | Có |
| O-07 | C-B | 31/03/2026 23:59:59 | PAID | 30.00 | Có |
| O-08 | C-A | 01/04/2026 00:00:00 | PAID | 300.00 | Không, đúng biên kết thúc |
| O-09 | C-B | 05/02/2026 12:00:00 | CANCELLED | 999.00 | Không, đơn hủy |
| O-10 | C-C | 12/02/2026 10:00:00 | PAID | 0.30 | Có |
| O-11 | C-B | 31/12/2025 23:59:59 | PAID | 600.00 | Không, trước biên bắt đầu |

Từ đó, kết quả kỳ vọng:

| Khách | Tháng | Số đơn | Doanh thu |
| --- | --- | ---: | ---: |
| C-A | 2026-01 | 2 | 300.30 |
| C-A | 2026-02 | 2 | 160.20 |
| C-B | 2026-01 | 1 | 40.00 |
| C-B | 2026-02 | 1 | 10.50 |
| C-B | 2026-03 | 1 | 30.00 |
| C-C | 2026-02 | 1 | 0.30 |
| **Toàn kỳ** | **01–03/2026** | **8** | **541.30** |

Tổng theo từng khách là: **C-A = 460.50 (4 đơn)**; **C-B = 80.50 (3 đơn)**; **C-C = 0.30 (1 đơn)**. Các con số này dùng để viết kiểm thử độc lập với phương thức tổng hợp.

## 5. Chương trình Java 17+ tự chứa, có kiểm thử

Lưu mã sau vào `CustomerPeriodReportDemo.java`. Chương trình dùng duy nhất API có sẵn trong JDK 17; `main` vừa in báo cáo vừa gọi các phép kiểm tra tự động.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CustomerPeriodReportDemo {

    enum Status { PAID, CANCELLED }

    record Order(
            String id,
            String customerId,
            Instant recordedAt,
            BigDecimal amount,
            Status status
    ) {
        Order {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(customerId, "customerId");
            Objects.requireNonNull(recordedAt, "recordedAt");
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(status, "status");
            if (id.isBlank() || customerId.isBlank()) {
                throw new IllegalArgumentException("ID không được rỗng");
            }
            if (amount.signum() < 0) {
                throw new IllegalArgumentException("Tiền âm chưa được hỗ trợ");
            }
        }
    }

    record CustomerMonth(String customerId, YearMonth month) {}

    record Stats(long orderCount, BigDecimal revenue) {
        static Stats zero() {
            return new Stats(0L, BigDecimal.ZERO);
        }

        Stats plus(Stats other) {
            return new Stats(
                    Math.addExact(orderCount, other.orderCount),
                    revenue.add(other.revenue));
        }
    }

    private static final Comparator<CustomerMonth> CUSTOMER_MONTH_ORDER =
            Comparator.comparing(CustomerMonth::customerId)
                    .thenComparing(CustomerMonth::month);

    record Report(
            Map<CustomerMonth, Stats> monthly,
            Map<String, Stats> byCustomer,
            Stats grandTotal
    ) {
        Report {
            // Map không sửa được, vẫn có thứ tự duyệt ổn định.
            TreeMap<CustomerMonth, Stats> months =
                    new TreeMap<>(CUSTOMER_MONTH_ORDER);
            months.putAll(monthly);
            monthly = Collections.unmodifiableMap(months);
            byCustomer = Collections.unmodifiableMap(
                    new TreeMap<>(byCustomer));
            Objects.requireNonNull(grandTotal, "grandTotal");
        }
    }

    static Stream<Order> streamOf(List<Order> source, boolean parallel) {
        return parallel ? source.parallelStream() : source.stream();
    }

    static Report build(
            List<Order> source,
            LocalDate fromInclusive,
            LocalDate toExclusive,
            ZoneId zone,
            boolean parallel
    ) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(fromInclusive, "fromInclusive");
        Objects.requireNonNull(toExclusive, "toExclusive");
        Objects.requireNonNull(zone, "zone");
        if (!fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException(
                    "Khoảng ngày phải có from < to");
        }

        Instant start = fromInclusive.atStartOfDay(zone).toInstant();
        Instant end = toExclusive.atStartOfDay(zone).toInstant();

        // Chỉ nhận đơn PAID và trong khoảng [start, end).
        List<Order> eligible = streamOf(source, parallel)
                .map(o -> Objects.requireNonNull(o, "order"))
                .filter(o -> o.status() == Status.PAID)
                .filter(o -> !o.recordedAt().isBefore(start))
                .filter(o -> o.recordedAt().isBefore(end))
                .toList();

        // Khóa ghép (khách hàng, tháng) được tính trong zone nghiệp vụ.
        Map<CustomerMonth, Stats> monthly = streamOf(eligible, parallel)
                .collect(Collectors.groupingBy(
                        o -> new CustomerMonth(
                                o.customerId(),
                                YearMonth.from(o.recordedAt().atZone(zone))),
                        () -> new TreeMap<>(CUSTOMER_MONTH_ORDER),
                        Collectors.reducing(
                                Stats.zero(),
                                o -> new Stats(1L, o.amount()),
                                Stats::plus)
                ));

        // Tổng theo khách được cộng từ các nhóm tháng, tránh tính lại nguồn.
        Map<String, Stats> byCustomer = monthly.entrySet().stream()
                .collect(Collectors.toMap(
                        entry -> entry.getKey().customerId(),
                        Map.Entry::getValue,
                        Stats::plus,
                        TreeMap::new
                ));

        Stats grandTotal = byCustomer.values().stream()
                .reduce(Stats.zero(), Stats::plus);

        return new Report(monthly, byCustomer, grandTotal);
    }

    static List<Order> sample() {
        return List.of(
                new Order("O-01", "C-A",
                        Instant.parse("2025-12-31T17:00:00Z"),
                        new BigDecimal("100.10"), Status.PAID),
                new Order("O-02", "C-A",
                        Instant.parse("2026-01-15T10:00:00Z"),
                        new BigDecimal("200.20"), Status.PAID),
                new Order("O-03", "C-B",
                        Instant.parse("2026-01-31T16:59:59Z"),
                        new BigDecimal("40.00"), Status.PAID),
                new Order("O-04", "C-A",
                        Instant.parse("2026-01-31T17:00:00Z"),
                        new BigDecimal("70.00"), Status.PAID),
                new Order("O-05", "C-B",
                        Instant.parse("2026-02-10T02:00:00Z"),
                        new BigDecimal("10.50"), Status.PAID),
                new Order("O-06", "C-A",
                        Instant.parse("2026-02-25T12:00:00Z"),
                        new BigDecimal("90.20"), Status.PAID),
                new Order("O-07", "C-B",
                        Instant.parse("2026-03-31T16:59:59Z"),
                        new BigDecimal("30.00"), Status.PAID),
                new Order("O-08", "C-A",
                        Instant.parse("2026-03-31T17:00:00Z"),
                        new BigDecimal("300.00"), Status.PAID),
                new Order("O-09", "C-B",
                        Instant.parse("2026-02-05T05:00:00Z"),
                        new BigDecimal("999.00"), Status.CANCELLED),
                new Order("O-10", "C-C",
                        Instant.parse("2026-02-12T03:00:00Z"),
                        new BigDecimal("0.30"), Status.PAID),
                new Order("O-11", "C-B",
                        Instant.parse("2025-12-31T16:59:59Z"),
                        new BigDecimal("600.00"), Status.PAID)
        );
    }

    static void check(boolean ok, String reason) {
        if (!ok) {
            throw new AssertionError(reason);
        }
    }

    static void checkMoney(String name, BigDecimal actual, String expected) {
        check(actual != null
                        && actual.compareTo(new BigDecimal(expected)) == 0,
                "Sai tiền " + name + ": " + actual);
    }

    static Stats at(Report report, String id, int year, int month) {
        return report.monthly().get(
                new CustomerMonth(id, YearMonth.of(year, month)));
    }

    static void selfTest() {
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        LocalDate from = LocalDate.of(2026, 1, 1);
        LocalDate end = LocalDate.of(2026, 4, 1);
        List<Order> data = sample();

        Report sequential = build(data, from, end, zone, false);
        check(sequential.monthly().size() == 6, "Số nhóm khách/tháng");
        check(sequential.byCustomer().size() == 3, "Số khách");
        check(sequential.grandTotal().orderCount() == 8, "Số đơn toàn kỳ");
        checkMoney("Toàn kỳ", sequential.grandTotal().revenue(), "541.30");

        check(at(sequential, "C-A", 2026, 1).orderCount() == 2,
                "C-A tháng 1");
        checkMoney("C-A tháng 1",
                at(sequential, "C-A", 2026, 1).revenue(), "300.30");
        checkMoney("C-A tháng 2",
                at(sequential, "C-A", 2026, 2).revenue(), "160.20");
        checkMoney("C-B tháng 1",
                at(sequential, "C-B", 2026, 1).revenue(), "40.00");
        checkMoney("C-B tháng 2",
                at(sequential, "C-B", 2026, 2).revenue(), "10.50");
        checkMoney("C-B tháng 3",
                at(sequential, "C-B", 2026, 3).revenue(), "30.00");
        checkMoney("C-C tháng 2",
                at(sequential, "C-C", 2026, 2).revenue(), "0.30");

        check(sequential.byCustomer().get("C-A").orderCount() == 4,
                "C-A phải có 4 đơn");
        checkMoney("C-A", sequential.byCustomer().get("C-A").revenue(),
                "460.50");
        checkMoney("C-B", sequential.byCustomer().get("C-B").revenue(),
                "80.50");

        // Comparator xác định thứ tự, không dựa vào HashMap.
        List<CustomerMonth> expectedKeys = List.of(
                new CustomerMonth("C-A", YearMonth.of(2026, 1)),
                new CustomerMonth("C-A", YearMonth.of(2026, 2)),
                new CustomerMonth("C-B", YearMonth.of(2026, 1)),
                new CustomerMonth("C-B", YearMonth.of(2026, 2)),
                new CustomerMonth("C-B", YearMonth.of(2026, 3)),
                new CustomerMonth("C-C", YearMonth.of(2026, 2))
        );
        check(new ArrayList<>(sequential.monthly().keySet())
                .equals(expectedKeys), "Thứ tự nhóm");

        // Cùng dữ liệu: parallel và sequential phải cho báo cáo tương đương.
        Report parallel = build(data, from, end, zone, true);
        check(sequential.equals(parallel), "Khác kết quả parallel");

        // Đảo thứ tự đầu vào: phép cộng và nhóm không được thay đổi.
        List<Order> reversed = new ArrayList<>(data);
        Collections.reverse(reversed);
        check(sequential.equals(build(reversed, from, end, zone, true)),
                "Khác kết quả khi đảo đầu vào");

        // Nguồn rỗng và chỉ gồm đơn không được tính.
        Report empty = build(List.of(), from, end, zone, false);
        check(empty.monthly().isEmpty(), "Nhóm rỗng");
        check(empty.byCustomer().isEmpty(), "Khách rỗng");
        check(empty.grandTotal().orderCount() == 0, "Số đơn rỗng");
        checkMoney("Doanh thu rỗng", empty.grandTotal().revenue(), "0");
        check(build(List.of(data.get(7), data.get(8), data.get(10)),
                from, end, zone, false).equals(empty),
                "Đơn ngoài kỳ hoặc hủy vẫn được tính");

        // Đơn O-04 ở 01/02 theo giờ Việt Nam, không ở nhóm tháng 1.
        checkMoney("Ranh giới tháng 2",
                at(sequential, "C-A", 2026, 2).revenue(), "160.20");

        // Sửa ngoài không được làm biến đổi kết quả báo cáo.
        boolean rejected = false;
        try {
            sequential.byCustomer().put("C-Z", Stats.zero());
        } catch (UnsupportedOperationException expected) {
            rejected = true;
        }
        check(rejected, "Báo cáo phải không cho sửa Map");
    }

    public static void main(String[] args) {
        Report report = build(
                sample(),
                LocalDate.of(2026, 1, 1),
                LocalDate.of(2026, 4, 1),
                ZoneId.of("Asia/Ho_Chi_Minh"),
                false);

        report.monthly().forEach((key, stats) ->
                System.out.println(key.customerId() + " | "
                        + key.month() + ": " + stats.orderCount()
                        + " đơn / " + stats.revenue()));
        report.byCustomer().forEach((id, stats) ->
                System.out.println("Khách " + id + ": "
                        + stats.orderCount() + " đơn / " + stats.revenue()));
        System.out.println("Toàn kỳ: "
                + report.grandTotal().orderCount() + " đơn / "
                + report.grandTotal().revenue());

        // Các kiểm tra không phụ thuộc cờ -ea của lệnh java.
        selfTest();
        System.out.println("TEST PASS");
    }
}
```

Chạy thử khi thực hành trên JDK 17+:

```text
javac CustomerPeriodReportDemo.java
java CustomerPeriodReportDemo
```

Đầu ra kỳ vọng (rút gọn):

```text
C-A | 2026-01: 2 đơn / 300.30
C-A | 2026-02: 2 đơn / 160.20
C-B | 2026-01: 1 đơn / 40.00
C-B | 2026-02: 1 đơn / 10.50
C-B | 2026-03: 1 đơn / 30.00
C-C | 2026-02: 1 đơn / 0.30
Khách C-A: 4 đơn / 460.50
Khách C-B: 3 đơn / 80.50
Khách C-C: 1 đơn / 0.30
Toàn kỳ: 8 đơn / 541.30
TEST PASS
```

Kết quả trên được tính từ dữ liệu mẫu; mã kiểm tra được cung cấp để người học tự chạy. Việc ghi tài liệu **không đồng nghĩa** chương trình đã được biên dịch hoặc kiểm định tự động trong bước viết bài.

## 6. Tại sao dùng `groupingBy` cùng `reducing`?

Phần lõi của bài toán là:

```java
Map<CustomerMonth, Stats> monthly = eligible.stream()
        .collect(Collectors.groupingBy(
                o -> new CustomerMonth(
                        o.customerId(),
                        YearMonth.from(o.recordedAt().atZone(zone))),
                () -> new TreeMap<>(CUSTOMER_MONTH_ORDER),
                Collectors.reducing(
                        Stats.zero(),
                        o -> new Stats(1L, o.amount()),
                        Stats::plus)
        ));
```

Đoạn trên dùng các kiểu, biến và comparator được định nghĩa trong chương trình ở mục 5.

Thành phần có ý nghĩa:

| Thành phần | Vai trò |
| --- | --- |
| `o -> new CustomerMonth(...)` | Phân loại theo **hai chiều**, khách hàng và tháng. |
| `() -> new TreeMap<>(CUSTOMER_MONTH_ORDER)` | Chọn Map có thứ tự khóa theo comparator nghiệp vụ. |
| `Stats.zero()` | Trạng thái trung hòa: `0` đơn, `BigDecimal.ZERO` tiền. |
| `o -> new Stats(1L, o.amount())` | Chuyển một đơn thành thống kê của một đơn. |
| `Stats::plus` | Gộp hai thống kê bằng cách cộng số đơn và doanh thu. |

`reducing(identity, mapper, op)` là **downstream collector**: mỗi nhóm nhận các phần tử của nhóm đó, rồi được giảm thành một `Stats`.

### Vì sao không dùng `summingDouble` cho tiền?

`Collectors.summingDouble(Order::amount)` không phù hợp ở đây vì `amount` là `BigDecimal`, và việc chuyển sang `double` có thể tạo sai số. Với tiền, nên giữ kiểu chính xác hoặc một mô hình đơn vị nhỏ nhất dạng số nguyên được quy định.

### Vì sao `Stats::plus` phù hợp với song song?

Phép gộp hoạt động trên **bản ghi bất biến**:

```java
Stats left = new Stats(2, new BigDecimal("100.10"));
Stats right = new Stats(1, new BigDecimal("20.20"));
Stats total = left.plus(right);
// 3 đơn, 120.30
```

Trạng thái trung hòa `Stats.zero()` không thay đổi giá trị khi cộng. Phép cộng số đếm và tiền có tính kết hợp trong miền dữ liệu hợp lệ, nên dù `groupingBy` tạo nhiều Map trung gian để xử lý song song, kết quả số học vẫn tương đương. `Math.addExact` báo lỗi nếu tổng số đơn vượt `long`; ví dụ không làm tròn tiền ở các bước trung gian.

## 7. Ranh giới thời gian: lỗi thường gặp trong báo cáo

### Khoảng nửa mở `[start, end)`

Điều kiện an toàn:

```java
boolean within = !order.recordedAt().isBefore(start)
        && order.recordedAt().isBefore(end);
```

Với khoảng **01/01–01/04**, đơn đúng `01/01 00:00` được tính, đơn đúng `01/04 00:00` không tính. Nếu ngày kế tiếp là một kỳ khác, hai kỳ cạnh nhau có thể ghép lại **không chồng lắp, không bỏ trống ranh giới**.

Không nên viết `<= LocalDate.atTime(23,59,59)` cho mốc kết thúc nếu dữ liệu có phần lẻ mili giây/nano giây. Cũng không nên lấy `Instant.now()` nhiều lần ở từng predicate nếu yêu cầu báo cáo phải lặp lại và kiểm thử được.

### Khác nhau giữa `Instant` và `LocalDate`

- `Instant` mô tả một thời điểm tuyệt đối, phù hợp lưu trữ và so sánh các sự kiện.
- `LocalDate` mô tả **ngày theo lịch**, không gắn múi giờ; cần `ZoneId` khi chuyển thành biên `Instant`.
- `YearMonth` mô tả tháng báo cáo; phải chọn tháng sau khi chuyển `Instant` sang múi giờ nghiệp vụ.

Nếu tạo nhóm bằng `YearMonth.from(order.recordedAt().atZone(ZoneOffset.UTC))` trong khi báo cáo dùng `Asia/Ho_Chi_Minh`, những đơn sát ranh giới có thể bị phân vào **tháng khác** với yêu cầu.

### Múi giờ và giờ mùa hè

Với những múi giờ có DST, khoảng thời gian từ đầu ngày địa phương này đến đầu ngày địa phương kế tiếp có thể ngắn hoặc dài hơn 24 giờ. Cách chuyển **hai mốc ngày theo cùng `ZoneId`** rồi so sánh `Instant` tránh lỗi cộng cố định `Duration.ofDays(1)` cho mọi ngày.

Nếu hệ thống báo cáo theo tháng, hãy dùng `YearMonth.atDay(1)` và `plusMonths(1)` để tạo biên kỳ tháng ở múi giờ được chọn, thay vì dùng số ngày cố định như 30 ngày.

## 8. Kiểm thử tính đúng, thứ tự và sự ổn định

Một báo cáo có thể đúng tổng toàn kỳ nhưng **sai phân nhóm tháng**. Vì thế, nên kiểm tra cả kết quả tổng và những trường hợp biên.

| Nhóm kiểm thử | Dữ liệu | Điều cần khẳng định |
| --- | --- | --- |
| Biên bắt đầu | O-01 đúng `01/01 00:00` địa phương | Được đưa vào thống kê tháng 1. |
| Biên kết thúc | O-08 đúng `01/04 00:00` địa phương | Không thuộc báo cáo quý 1. |
| Trước kỳ | O-11 ngay trước mốc bắt đầu | Không được tính. |
| Ranh giới tháng | O-04 đúng `01/02 00:00` địa phương | Thuộc tháng 2, không thuộc tháng 1. |
| Đơn hủy | O-09 có tiền rất lớn | Không được tính vào bất kỳ tổng nào. |
| Nhiều đơn một khách/tháng | C-A tháng 1 và tháng 2 | Đúng số đơn và tổng tiền từng tháng. |
| Nhiều khách | C-A, C-B, C-C | Tách nhóm chính xác, không cộng lẫn. |
| Nguồn rỗng | `List.of()` | Map rỗng, count 0, revenue 0. |
| Tiền thập phân | O-10 có `0.30` | Không mất độ chính xác do `double`. |
| Đảo thứ tự đầu vào | `Collections.reverse(...)` | Tổng và các nhóm vẫn bằng nhau. |
| Stream song song | `parallel = true` | Kết quả bằng bản tuần tự. |
| Thứ tự bản báo cáo | `TreeMap` và comparator | Khách tăng dần, tháng tăng dần. |

### Kiểm thử bất biến theo hoán vị

Khi phép gộp không phụ thuộc thứ tự, một phép thử có ích là đảo ngược dữ liệu:

```java
List<Order> reversed = new ArrayList<>(source);
Collections.reverse(reversed);

Report a = build(source, from, to, zone, false);
Report b = build(reversed, from, to, zone, true);
check(a.equals(b), "Khác báo cáo sau khi đảo nguồn");
```

Phép thử này dựa trên ngữ nghĩa nghiệp vụ **tổng hợp theo khóa, không theo vị trí xuất hiện**. Nếu về sau báo cáo bổ sung trường như “đơn đầu tiên” và dùng encounter order, kiểm thử phải được điều chỉnh: “đầu tiên” cần định nghĩa bằng timestamp/ID hoặc thứ tự nguồn rõ ràng.

### `Map.equals` không xác minh thứ tự

`Map.equals` so sánh ánh xạ khóa–giá trị, **không xác minh thứ tự duyệt khóa**. Bởi vậy `selfTest()` còn tạo danh sách `new ArrayList<>(monthly.keySet())` và so sánh với thứ tự mong đợi. Nếu thứ tự là một phần của hợp đồng báo cáo, cần kiểm tra nó riêng.

### `BigDecimal.equals` và `compareTo`

`new BigDecimal("1.0").equals(new BigDecimal("1.00"))` trả `false` vì khác scale; `compareTo(...) == 0` cho biết hai giá trị tiền bằng nhau **về số học**. Hàm `checkMoney` trong bài sử dụng `compareTo` để kiểm tra tiền, tránh phụ thuộc cách biểu diễn số chữ số thập phân. Nếu nghiệp vụ yêu cầu luôn đúng hai chữ số, phải bổ sung quy tắc scale hoặc formatter ở ranh giới xuất báo cáo.

## 9. Hiệu năng, tính lặp lại và giới hạn nguồn

### Có cần giữ danh sách `eligible`?

Ví dụ dùng:

```java
List<Order> eligible = streamOf(source, parallel)
        .filter(o -> o.status() == Status.PAID)
        .filter(o -> !o.recordedAt().isBefore(start))
        .filter(o -> o.recordedAt().isBefore(end))
        .toList();
```

Danh sách này giúp việc kiểm thử và tái sử dụng tập đã lọc rõ ràng. Tuy nhiên, nó tốn bộ nhớ theo số đơn đủ điều kiện. Với nguồn lớn, có thể nối `filter` trực tiếp vào `groupingBy` trong **một lần collect**, giảm việc vật hóa danh sách. Tùy mục tiêu cần đo xem cách nào thích hợp hơn.

Lưu ý trong bài, việc tổng hợp từ `monthly` lên `byCustomer` và `grandTotal` không đọc lại toàn bộ danh sách đơn hàng; nó chỉ duyệt các **nhóm đã thu thập**.

### Một Stream chỉ dùng cho một terminal operation

Sau `collect(...)`, đối tượng Stream đã được tiêu thụ. Nếu có danh sách `source`, gọi `source.stream()` lần khác sẽ tạo nguồn Stream mới. Với nguồn I/O chỉ đọc được một lần, phải thiết kế collector tích lũy đủ chỉ số cần thiết trong **một lượt** và tuân thủ cách đóng tài nguyên nguồn.

### Xử lý song song không tự nhanh hơn

`groupingBy` không phải concurrent collector: khi chạy song song, framework có thể thu thập vào nhiều Map trung gian và gộp chúng; việc này có chi phí. `groupingByConcurrent` có thể hữu ích khi không cần đảm bảo encounter order, nhưng không nên đổi khi chưa hiểu yêu cầu thứ tự và khả năng đồng thời của downstream collector.

Với tập dữ liệu nhỏ, `parallelStream()` thường không đem lại lợi ích rõ rệt. Hãy đo tốc độ và bộ nhớ trên dữ liệu thực tế; việc chuyển sang parallel **không thay thế** chính sách truy cập CSDL, timeout hoặc backpressure nếu nguồn thao tác I/O.

### Quản lý dữ liệu lỗi

Hệ thống thật cần quyết định cách xử lý:

- **Đơn trùng `id`:** nếu một hóa đơn xuất hiện nhiều lần trong dữ liệu, bài đang tính **mỗi record là một đơn**. Muốn đếm hóa đơn duy nhất phải kiểm tra trùng và chọn bản ghi hợp lệ; không tự `distinct()` toàn đối tượng nếu chúng có trường khác nhau.
- **Đơn hoàn tiền/đổi trả:** ví dụ chỉ có `PAID` và `CANCELLED`. Giá trị âm không được chấp nhận; cần thiết kế mô hình hoàn tiền riêng nếu nghiệp vụ yêu cầu.
- **Thiếu mã khách hàng:** record kiểm tra null và chuỗi rỗng. Tên hiển thị khách hàng nên tra ở nguồn khác có hợp đồng rõ, không trộn việc tổng hợp định danh với việc lấy tên.
- **Nhiều loại tiền:** không cộng trực tiếp USD, VND và EUR trong cùng một `BigDecimal`. Hãy nhóm theo currency hoặc chuyển đổi theo tỷ giá và kỳ có quy tắc.
- **Kỳ báo cáo rất dài:** số nhóm có thể tăng theo số khách nhân số tháng; bộ nhớ của `Map` phụ thuộc số khóa phân biệt, không chỉ số đơn đầu vào.

## 10. Bài tập mở rộng

**Bài 1 — Báo cáo theo ngày.** Thay `YearMonth` bằng `LocalDate`:

```java
record CustomerDay(String customerId, LocalDate day) {}

CustomerDay key = new CustomerDay(
        order.customerId(),
        order.recordedAt().atZone(zone).toLocalDate()
);
```

Chọn comparator theo `customerId` rồi `day`; giữ nguyên khoảng nửa mở và cách cộng tiền.

**Bài 2 — Báo cáo một tháng.** Viết hàm nhận `YearMonth month`, `ZoneId zone`; xây dựng `from = month.atDay(1)` và `to = month.plusMonths(1).atDay(1)`, sau đó gọi `build(...)`. Kiểm tra với đơn đúng 00:00 ngày đầu tháng kế tiếp.

**Bài 3 — Top khách hàng.** Từ `byCustomer`, tạo danh sách khách có doanh thu giảm dần và phá hòa bằng mã khách tăng dần:

```java
List<Map.Entry<String, Stats>> ranking =
        report.byCustomer().entrySet().stream()
                .sorted(Comparator
                        .<Map.Entry<String, Stats>, BigDecimal>comparing(
                                e -> e.getValue().revenue(),
                                Comparator.reverseOrder())
                        .thenComparing(Map.Entry::getKey))
                .toList();
```

Không dựa vào thứ tự duyệt Map để suy ra thứ hạng doanh thu.

**Bài 4 — Kiểm tra tính nhất quán.** Với từng khách, chứng minh tổng `Stats` của các tháng bằng `byCustomer.get(customerId)` cả về số đơn và số tiền. Thêm bộ dữ liệu có một khách không có đơn hợp lệ và xác định có hiển thị khách đó trong báo cáo hay không.

**Bài 5 — Dữ liệu trùng đơn.** Thêm hai record có cùng `id` nhưng khác thời điểm. Thiết kế chính sách hợp lệ: từ chối, lấy phiên bản mới nhất, hay tính theo lịch sử giao dịch? Sau đó mới viết pipeline `toMap` có merge function; không mặc định rằng `distinct()` sẽ giải quyết đúng nghiệp vụ.

**Bài 6 — Kiểm thử múi giờ khác.** Chạy cùng dữ liệu với `ZoneId.of("UTC")`. So sánh đơn `O-04` giữa tháng 1 UTC và tháng 2 Việt Nam; giải thích vì sao một thời điểm có thể thuộc hai tháng báo cáo khác nhau mà vẫn là cùng một `Instant`.

## 11. Ghi nhớ

- Xác định rõ **trạng thái hợp lệ, khóa khách hàng, múi giờ và khoảng nửa mở `[start, end)`** trước khi xây dựng pipeline.
- Lọc bằng `filter`, tạo khóa ghép `(customerId, YearMonth)`, dùng `groupingBy` và downstream `reducing` để tính số đơn cùng doanh thu trong mỗi nhóm.
- Dùng `BigDecimal` cho tiền và phép gộp có tính kết hợp, có giá trị trung hòa; không làm tròn giữa các phép cộng, không phụ thuộc thứ tự nhánh song song.
- Thứ tự duyệt báo cáo cần được **thiết kế bằng comparator/`TreeMap`**, không suy ra từ `HashMap`. Kiểm thử thứ tự riêng, không chỉ so sánh `Map.equals`.
- Kiểm thử cả **đơn ở ranh giới ngày/tháng, đơn hủy, nguồn rỗng, đảo thứ tự và parallel**; chỉ tối ưu khi kết quả nghiệp vụ đã được chứng minh đúng trên dữ liệu đại diện.
