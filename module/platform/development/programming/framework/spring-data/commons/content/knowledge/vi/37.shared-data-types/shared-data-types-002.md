# Kết hợp Range với giá trị thời gian, số hoặc điều kiện truy vấn

## 1. Mục tiêu và phạm vi

Trong chương **Kiểu dữ liệu dùng chung** của module **Spring Data Commons**, `Range<T>` biểu diễn một khoảng giá trị bằng biên dưới và biên trên. Mỗi biên có thể bao gồm đầu mút, loại trừ đầu mút hoặc không bị chặn.

Kiểu cần dùng là:

~~~java
org.springframework.data.domain.Range
~~~

Không nhầm với `java.util.stream.IntStream.range`, một range của thư viện khác hoặc kiểu interval riêng của database.

Sau bài học, bạn cần có khả năng:

- Chọn đúng biên đóng, mở hoặc không bị chặn.
- Biểu diễn bộ lọc giá, số lượng và thời gian bằng Range.
- Chuyển một ngày theo múi giờ thành khoảng Instant rõ ràng.
- Kiểm tra thứ tự và ý nghĩa của các đầu mút.
- Dịch từng biên thành toán tử truy vấn tương ứng.
- Phân biệt khả năng biểu diễn của Commons với khả năng thực thi của store.
- Kiểm tra các giá trị đúng tại đầu mút và độ chính xác khi lưu dữ liệu.

Ví dụ Java dùng Java 17 trở lên. Ví dụ truy vấn chọn Spring Data JPA với Criteria API Jakarta; đây là một cách áp dụng Range, không phải implementation truy vấn dùng chung cho mọi store.

## 2. Range mô tả khoảng, không tự tạo query

Một khoảng giá:

~~~java
import java.math.BigDecimal;

import org.springframework.data.domain.Range;

Range<BigDecimal> prices = Range.closed(
        new BigDecimal("100.00"),
        new BigDecimal("500.00"));
~~~

biểu diễn các giá trị từ 100.00 đến 500.00, có bao gồm cả hai đầu mút theo phép so sánh tương ứng.

Nó chưa:

- Chọn tên property cần lọc.
- Chọn đơn vị tiền tệ.
- Gọi repository.
- Tạo SQL, truy vấn MongoDB hoặc một ngôn ngữ store khác.
- Áp dụng phạm vi tenant hoặc quyền truy cập.
- Đặt giới hạn số kết quả.

Một mô hình lọc có thể giữ Range cùng các thông tin khác:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Currency;

import org.springframework.data.domain.Range;

public record OrderFilter(
        Range<Instant> createdAt,
        Range<BigDecimal> total,
        Currency currency) {
}
~~~

Record này chỉ gom dữ liệu đầu vào. Ứng dụng vẫn phải kiểm tra tính hợp lệ và xác định chính sách truy vấn cho từng thành phần.

## 3. Biên đóng, biên mở và đầu mút không bị chặn

Quy ước toán học:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `[a, b]` | Bao gồm a và b |
| `(a, b)` | Loại a và b |
| `(a, b]` | Loại a, bao gồm b |
| `[a, b)` | Bao gồm a, loại b |
| `[a, +∞)` | Có biên dưới, không có biên trên hữu hạn |
| `(-∞, b)` | Không có biên dưới hữu hạn, loại b |
| `(-∞, +∞)` | Không bị chặn ở cả hai phía |

Các factory tương ứng:

~~~java
Range<Integer> closed = Range.closed(10, 20);
Range<Integer> open = Range.open(10, 20);
Range<Integer> leftOpen = Range.leftOpen(10, 20);
Range<Integer> rightOpen = Range.rightOpen(10, 20);

Range<Integer> atLeastTen = Range.of(
        Range.Bound.inclusive(10),
        Range.Bound.unbounded());

Range<Integer> belowTwenty = Range.of(
        Range.Bound.unbounded(),
        Range.Bound.exclusive(20));

Range<Integer> any = Range.unbounded();
Range<Integer> exactlyTen = Range.just(10);
~~~

Đọc tên cẩn thận:

- `leftOpen` mở phía trái: `(10, 20]`.
- `rightOpen` mở phía phải: `[10, 20)`.
- `just(10)` biểu diễn một giá trị theo ngữ nghĩa so sánh của kiểu được dùng.

Biên không bị chặn không được biểu diễn bằng một giá trị nghiệp vụ như 0 hoặc một ngày rất xa.

Không dùng `Range.closed(null, end)` để biểu diễn thiếu đầu mút. Dùng `Range.Bound.unbounded()` cho trường hợp không có biên hữu hạn.

## 4. Kiểm tra chứa giá trị và phân biệt các thao tác khác

Với kiểu Comparable phù hợp:

~~~java
Range<Integer> quantities = Range.rightOpen(10, 20);

boolean includesTen = quantities.contains(10);    // true
boolean includesNineteen = quantities.contains(19); // true
boolean includesTwenty = quantities.contains(20); // false
~~~

`contains` kiểm tra một giá trị trong bộ nhớ. Nó không chứng minh database đã áp dụng cùng quy tắc.

Range cũng không tự:

- Liệt kê mọi phần tử của khoảng.
- Xác định bước nhảy.
- Tính số phần tử cho mọi kiểu T.
- Tính Duration giữa hai giá trị thời gian.
- Cung cấp một giới hạn truy vấn tối ưu cho store.

Ví dụ, Range<Instant> có thể có độ phân giải rất nhỏ; việc coi nó như một danh sách thời điểm để lặp là một thiết kế khác hoàn toàn.

Đối với các kiểu không có thứ tự tự nhiên phù hợp, cần một quy tắc so sánh rõ ràng. Không tạo một Range của object tùy ý rồi giả định `contains` sẽ biết thứ tự nghiệp vụ.

## 5. Áp dụng với số lượng, điểm số và giá tiền

### 5.1. Số lượng nguyên

~~~java
Range<Integer> smallOrders = Range.closed(1, 10);
Range<Long> largeCounts = Range.of(
        Range.Bound.inclusive(1_000L),
        Range.Bound.unbounded());
~~~

Không dùng số âm làm dấu hiệu “không giới hạn” nếu đó không phải hợp đồng nghiệp vụ thực sự. Dấu hiệu không giới hạn đã có trong Bound.

Range<Integer> không tự cấm các giá trị âm. Nếu số lượng phải không âm, đó là validation miền dữ liệu.

### 5.2. Tiền và BigDecimal

~~~java
Range<BigDecimal> budget = Range.closed(
        new BigDecimal("100.00"),
        new BigDecimal("500.00"));

boolean eligible = budget.contains(
        new BigDecimal("100.0"));
~~~

Theo so sánh tự nhiên của BigDecimal, 100.00 và 100.0 có giá trị số bằng nhau.

Không thay phép so sánh miền bằng `equals` một cách máy móc: BigDecimal.equals còn xét scale, trong khi compareTo biểu diễn thứ tự số.

Khi cần dựng giá trị thập phân chính xác, dùng chuỗi hoặc một quy tắc chuyển đổi đã được kiểm soát. Tránh đưa sai số từ phép tính double vào đầu mút của bộ lọc tiền.

Range<BigDecimal> không giữ currency. Hai đầu mút phải cùng đơn vị và truy vấn phải lọc đúng loại tiền nếu dữ liệu có nhiều currency.

### 5.3. Số thực và giá trị đặc biệt

Nếu dùng Double hoặc Float, cần quyết định cách xử lý NaN, vô cực và sai số làm tròn. Không mặc định một giá trị mà Comparable sắp xếp được cũng là một đầu mút hợp lệ về nghiệp vụ.

Ví dụ nhiệt độ có thể cho số âm, còn số lượng tồn kho thì có thể không. Chính sách miền không được suy ra từ tên kiểu Range.

## 6. Khoảng thời gian thường nên dùng biên trên loại trừ

Một khoảng sự kiện:

~~~java
import java.time.Instant;

import org.springframework.data.domain.Range;

Instant from = Instant.parse("2026-11-25T00:00:00Z");
Instant until = Instant.parse("2026-11-26T00:00:00Z");

Range<Instant> period = Range.rightOpen(from, until);
~~~

có ý nghĩa:

~~~text
createdAt >= from
AND
createdAt < until
~~~

Đây là khoảng `[from, until)`.

Hai cửa sổ liên tiếp:

~~~text
[a, b)
[b, c)
~~~

không cùng chứa sự kiện tại đúng thời điểm b. Sự kiện đó thuộc cửa sổ thứ hai.

Cách này hữu ích cho báo cáo theo ngày, xử lý batch theo cửa sổ và truy vấn lịch sử.

### 6.1. Không cần tạo “thời điểm cuối cùng của ngày”

Tránh một hợp đồng kiểu:

~~~text
đầu ngày <= createdAt <= 23:59:59.999...
~~~

với số chữ số thập phân được chọn tùy ý.

Database, driver và kiểu dữ liệu có thể có độ chính xác khác nhau. Một mốc “cuối cùng” ở millisecond không bao phủ đúng dữ liệu microsecond hoặc nanosecond nếu chính sách xử lý không tương ứng.

Biên trên là đầu ngày kế tiếp và dùng `<` diễn tả ý định rõ ràng hơn.

Nó vẫn đòi hỏi dữ liệu được chuyển đổi và lưu với quy tắc thời gian nhất quán; Range không tự sửa sự khác biệt precision giữa Java và store.

### 6.2. Khoảng đóng vẫn có chỗ dùng

Nếu nghiệp vụ thật sự yêu cầu bao gồm cả thời điểm kết thúc, dùng `Range.closed` và ánh xạ sang `<=`.

Không chọn khoảng nửa mở chỉ vì đó là một thói quen. Điều quan trọng là ký hiệu, tên tham số và toán tử truy vấn cùng diễn đạt một hợp đồng.

## 7. Từ ngày theo múi giờ sang Range<Instant>

Ngày trên giao diện thường là LocalDate theo một múi giờ nghiệp vụ, không phải một ngày UTC mặc định.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

import org.springframework.data.domain.Range;

LocalDate day = LocalDate.parse("2026-11-25");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant start = day.atStartOfDay(zone).toInstant();
Instant end = day.plusDays(1).atStartOfDay(zone).toInstant();

Range<Instant> localDay = Range.rightOpen(start, end);
~~~

Hai biên được tính từ hai ngày lịch trong cùng một múi giờ.

Không thay quy tắc đó bằng:

~~~java
Instant guessedEnd = start.plusSeconds(24 * 60 * 60);
~~~

nếu ý định là “hết ngày lịch tại múi giờ được chọn”. Ở các múi giờ có chuyển đổi giờ theo mùa hoặc quy tắc lịch sử liên quan, một ngày không luôn tương đương đúng 24 giờ trên timeline.

### 7.1. Chọn kiểu thời gian theo ý nghĩa

| Kiểu | Ý nghĩa cần lưu ý |
| --- | --- |
| Instant | Một thời điểm trên timeline |
| LocalDate | Một ngày lịch, chưa có múi giờ/thời điểm cụ thể |
| LocalDateTime | Ngày giờ cục bộ, chưa xác định offset hoặc zone |
| OffsetDateTime | Ngày giờ kèm offset |
| ZonedDateTime | Ngày giờ kèm zone và quy tắc liên quan |

Khi trường database biểu diễn một thời điểm, thường cần chuẩn hóa đầu vào thành Instant hoặc một biểu diễn timeline tương thích trước khi so sánh.

Không gán một LocalDateTime vào UTC chỉ để làm code chạy nếu đầu vào thực sự được hiểu theo múi giờ người dùng.

### 7.2. Bộ lọc ngày bao gồm ngày kết thúc

Nếu UI cho người dùng chọn từ ngày 01 đến hết ngày 30, có thể chuyển:

~~~text
fromDate -> đầu ngày 01
throughDate -> đầu ngày 31 làm biên trên loại trừ
~~~

Trong code, tính từ `throughDate.plusDays(1)` theo zone đã chọn.

Đặt tên tham số rõ ràng: `until` hoặc `toExclusive` không có cùng nghĩa với `throughDate` bao gồm cả ngày kết thúc. Không đổi tên mà giữ một ý nghĩa ngầm khác.

## 8. Kiểm tra đầu mút theo chính sách ứng dụng

Range không thay thế validation nghiệp vụ. Không dựa vào việc gọi được factory để kết luận rằng min không lớn hơn max hoặc khoảng đó có ý nghĩa đối với ứng dụng.

Một factory kiểm tra có thể chọn chính sách:

- Không nhận bound null.
- Nếu có cả hai đầu mút hữu hạn, lower không được lớn hơn upper.
- Nếu hai đầu mút bằng nhau, chỉ nhận khoảng bao gồm đầu mút ở cả hai phía.

~~~java
import java.util.Objects;
import java.util.Optional;

import org.springframework.data.domain.Range;

public final class CheckedRanges {

    private CheckedRanges() {
    }

    public static <T extends Comparable<? super T>> Range<T> of(
            Range.Bound<T> lower,
            Range.Bound<T> upper) {

        Objects.requireNonNull(lower, "lower");
        Objects.requireNonNull(upper, "upper");

        Optional<T> lowerValue = lower.getValue();
        Optional<T> upperValue = upper.getValue();

        if (lowerValue.isPresent() && upperValue.isPresent()) {
            int comparison = lowerValue.get()
                    .compareTo(upperValue.get());

            if (comparison > 0) {
                throw new IllegalArgumentException(
                        "Biên dưới không được lớn hơn biên trên");
            }

            if (comparison == 0
                    && (!lower.isInclusive()
                        || !upper.isInclusive())) {

                throw new IllegalArgumentException(
                        "Khoảng không chứa đầu mút chung");
            }
        }

        return Range.of(lower, upper);
    }
}
~~~

Chính sách từ chối khoảng rỗng là lựa chọn của ví dụ. Một ứng dụng khác có thể chấp nhận và trả tập kết quả rỗng, nhưng phải thực hiện nhất quán.

Hàm trên không phân tích toàn bộ độ rời rạc của miền. Ví dụ `(10, 11)` không chứa số nguyên nào, dù lower nhỏ hơn upper. Nếu cần phát hiện mọi khoảng không có giá trị trong một miền rời rạc, phải bổ sung logic riêng cho miền đó.

### 8.1. Khoảng bằng nhau

| Khoảng | Ý nghĩa với một giá trị a |
| --- | --- |
| `[a, a]` | Chứa a |
| `(a, a)` | Không chứa giá trị |
| `[a, a)` | Không chứa giá trị |
| `(a, a]` | Không chứa giá trị |

Không tự đảo hai đầu mút khi người dùng nhập min lớn hơn max nếu hợp đồng chưa cho phép. Việc tự sửa có thể biến lỗi input thành một truy vấn khác ngoài ý định của client.

### 8.2. Validation bổ sung

Đối với giá tiền, có thể cần:

- Hai đầu mút không âm.
- Currency xác định.
- Scale hoặc quy tắc làm tròn phù hợp.
- Khoảng giá không quá rộng theo chính sách endpoint.

Đối với thời gian, có thể cần:

- Múi giờ được xác định.
- Khoảng truy vấn không dài hơn giới hạn cho phép.
- Không chấp nhận mốc nằm ngoài khả năng biểu diễn/lưu trữ.
- Chính sách rõ ràng cho khoảng không có một đầu mút.

Các quy tắc này không được suy ra chỉ từ việc T là Instant hoặc BigDecimal.

## 9. Dịch từng biên sang toán tử truy vấn

Quy tắc nền:

| Bound | Điều kiện tương ứng |
| --- | --- |
| Lower inclusive a | `value >= a` |
| Lower exclusive a | `value > a` |
| Upper inclusive b | `value <= b` |
| Upper exclusive b | `value < b` |
| Lower unbounded | Không thêm điều kiện biên dưới |
| Upper unbounded | Không thêm điều kiện biên trên |

Các điều kiện hữu hạn được kết hợp bằng AND.

Với `Range.rightOpen(from, until)`:

~~~sql
WHERE created_at >= :from
  AND created_at < :until
~~~

Với giá tiền đóng hai đầu:

~~~sql
WHERE total >= :minimum
  AND total <= :maximum
~~~

SQL ở đây minh họa ý nghĩa toán tử, không phải tên bảng/cột bắt buộc cho mọi ứng dụng.

Không thay mọi Range bằng `BETWEEN` một cách máy móc. Một phép BETWEEN bao gồm hai đầu mút không giữ được hợp đồng biên trên loại trừ.

Không cần tạo ra các đầu mút cực trị giả để viết `OR :parameter IS NULL` nếu một query builder có thể bỏ hẳn điều kiện của bound không bị chặn.

## 10. Ví dụ adapter với JPA Specification

Giả định entity JPA `PurchaseOrder` có các property:

~~~text
id        : Long
tenantId  : Long
createdAt : Instant
total     : BigDecimal
~~~

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long>,
                JpaSpecificationExecutor<PurchaseOrder> {
}
~~~

Adapter nhận tên property do server lựa chọn và Range:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import jakarta.persistence.criteria.Path;
import jakarta.persistence.criteria.Predicate;

import org.springframework.data.domain.Range;
import org.springframework.data.jpa.domain.Specification;

public final class OrderSpecifications {

    private OrderSpecifications() {
    }

    public static <T extends Comparable<? super T>>
            Specification<PurchaseOrder> within(
                    String property,
                    Range<T> range) {

        Objects.requireNonNull(property, "property");
        Objects.requireNonNull(range, "range");

        return (root, query, builder) -> {
            Path<T> path = root.get(property);
            List<Predicate> conditions = new ArrayList<>();

            Range.Bound<T> lower = range.getLowerBound();
            Range.Bound<T> upper = range.getUpperBound();

            lower.getValue().ifPresent(value -> {
                Predicate condition = lower.isInclusive()
                        ? builder.greaterThanOrEqualTo(path, value)
                        : builder.greaterThan(path, value);

                conditions.add(condition);
            });

            upper.getValue().ifPresent(value -> {
                Predicate condition = upper.isInclusive()
                        ? builder.lessThanOrEqualTo(path, value)
                        : builder.lessThan(path, value);

                conditions.add(condition);
            });

            return builder.and(
                    conditions.toArray(Predicate[]::new));
        };
    }
}
~~~

Khi cả hai bound không bị chặn, adapter không thêm phép so sánh giá trị; conjunction không có điều kiện đóng vai trò đúng trong tổ hợp này.

Adapter không tự kiểm tra thứ tự đầu mút. Đầu vào cần được tạo qua chính sách validation đã chọn trước đó.

### 10.1. Kết hợp nhiều Range và phạm vi bắt buộc

~~~java
Range<Instant> period = Range.rightOpen(from, until);

Range<BigDecimal> budget = CheckedRanges.of(
        Range.Bound.inclusive(new BigDecimal("100.00")),
        Range.Bound.inclusive(new BigDecimal("500.00")));

Specification<PurchaseOrder> tenantScope =
        (root, query, builder) ->
                builder.equal(
                        root.get("tenantId"),
                        currentTenantId);

Specification<PurchaseOrder> specification =
        OrderSpecifications.within("createdAt", period)
                .and(OrderSpecifications.within("total", budget))
                .and(tenantScope);

Page<PurchaseOrder> result =
        orders.findAll(specification, pageable);
~~~

Snippet giả định `orders`, `pageable`, `from`, `until` và `currentTenantId` đã được xác định trong service, cùng các import Spring Data tương ứng.

`currentTenantId` phải đến từ phạm vi đã được xác thực của ứng dụng. Nó không được thay bằng một đầu vào client chưa được kiểm tra quyền.

Kết quả có ý nghĩa:

~~~text
đúng tenant
AND nằm trong cửa sổ createdAt
AND nằm trong khoảng total
~~~

Một Range không bị chặn phải bỏ riêng bộ lọc đó, không làm mất tenantScope.

### 10.2. Tên property và kiểu phải do ứng dụng kiểm soát

Trong snippet, `"createdAt"` và `"total"` là các hằng tên được server chọn.

Không nhận trực tiếp một tên property bất kỳ từ HTTP rồi đưa vào adapter này. Một hợp đồng lọc động cần allowlist và ánh xạ kiểu tương ứng.

Criteria API ở trên vẫn dùng tên property dạng chuỗi. Sai tên hoặc dùng Range<BigDecimal> cho property thời gian có thể chỉ được phát hiện khi xây/thực thi query. Có thể dùng metamodel tĩnh hoặc adapter chuyên biệt để tăng kiểm soát kiểu trong dự án.

### 10.3. Không áp dụng nguyên code JPA cho mọi store

`Specification`, CriteriaBuilder và JpaSpecificationExecutor thuộc tích hợp JPA. MongoDB, Elasticsearch, Cassandra hoặc một store khác cần điểm mở rộng và toán tử riêng mà mô-đun đó hỗ trợ.

Quy tắc chuyển bound thành phép so sánh có thể tái sử dụng về ý nghĩa, nhưng class API và khả năng thực thi không giống nhau.

Một mô-đun có thể hỗ trợ Range trực tiếp ở một số query method hoặc API truy vấn. Cần xác nhận hợp đồng cụ thể của mô-đun và phiên bản, thay vì suy từ việc Commons có lớp Range.

## 11. Derived query chỉ phù hợp khi chữ ký giữ đúng ngữ nghĩa

Với khoảng thời gian hữu hạn `[from, until)`, một method JPA có thể được khai báo tường minh:

~~~java
Page<PurchaseOrder>
        findByTenantIdAndCreatedAtGreaterThanEqualAndCreatedAtLessThan(
                Long tenantId,
                Instant from,
                Instant until,
                Pageable pageable);
~~~

Khi dùng chữ ký này, hai đầu mút phải hiện diện và có đúng chính sách inclusive/exclusive tương ứng.

Nó không thể tự xử lý mọi kiểu Range chỉ bằng cách truyền hai giá trị:

- Range có biên mở phía dưới cần `>`, không phải `>=`.
- Range có biên trên đóng cần `<=`, không phải `<`.
- Range một phía có thể cần một phương thức hoặc nhánh query khác.
- Range không bị chặn không có hai đầu mút để lấy.

Nếu đầu vào hỗ trợ linh hoạt cả bốn loại biên và các trường hợp không bị chặn, adapter query builder thường biểu diễn chính sách rõ hơn một method cố định.

Không mặc định khai báo `findByCreatedAtBetween(Range<Instant> range)` sẽ hoạt động trên mọi repository. Khả năng nhận Range trong derived query là hợp đồng của mô-đun cụ thể.

## 12. Chuyển đổi Range cần giữ nguyên ý nghĩa

Một phép biến đổi tăng theo thứ tự có thể thuận tiện:

~~~java
Range<Integer> original = Range.closed(10, 20);

Range<Integer> doubled = original.map(
        value -> Math.multiplyExact(value, 2));
~~~

Kết quả có các đầu mút tương ứng là 20 và 40, giữ loại bound theo cơ chế map của Range.

Tuy nhiên, map không phải một bộ chứng minh rằng mọi hàm chuyển đổi đều bảo toàn thứ tự và ngữ nghĩa.

Ví dụ nhân với một số âm đảo thứ tự giá trị. Làm tròn thời gian hoặc tiền có thể đưa hai đầu mút khác nhau về cùng một giá trị, làm thay đổi ý nghĩa của khoảng mở.

Nếu đổi đơn vị, scale, precision hoặc múi giờ, hãy kiểm tra:

1. Hàm chuyển đổi có giữ thứ tự không.
2. Có mất độ chính xác hoặc overflow không.
3. Có làm hai đầu mút trùng nhau không.
4. Loại bound còn phù hợp không.
5. Store so sánh trên biểu diễn nào.

Không dùng map để âm thầm “sửa” một khoảng đầu vào không hợp lệ.

## 13. SQL NULL và bound không bị chặn là hai khái niệm khác nhau

Bound unbounded biểu diễn việc không đặt một giới hạn ở phía đó.

Nó không có nghĩa:

~~~sql
value IS NULL
~~~

Một điều kiện so sánh SQL với đầu mút thường không nhận các dòng có value NULL như một giá trị bình thường trong khoảng.

Nếu adapter bỏ cả hai phép so sánh của một Range không bị chặn, các dòng có field NULL có thể vẫn nằm trong tập kết quả theo những điều kiện khác của query. Range.unbounded không tự thêm `IS NOT NULL`.

Khi nghiệp vụ phân biệt “chưa có giá”, “có mọi mức giá” và “giá nằm trong khoảng”, cần một lựa chọn lọc NULL riêng, không dùng null endpoint để biểu diễn tất cả các trường hợp.

## 14. Kiểm tra đầu mút và truy vấn thực tế

### 14.1. Kiểm tra trong bộ nhớ

Với giá từ 100 đến dưới 500:

~~~java
Range<BigDecimal> prices = Range.rightOpen(
        new BigDecimal("100.00"),
        new BigDecimal("500.00"));

assertTrue(prices.contains(new BigDecimal("100.00")));
assertTrue(prices.contains(new BigDecimal("499.99")));
assertFalse(prices.contains(new BigDecimal("500.00")));
assertFalse(prices.contains(new BigDecimal("99.99")));
~~~

Snippet giả định static import assertion tương ứng. Nó xác minh lựa chọn loại bound, chưa xác minh query của store.

### 14.2. Kiểm tra khoảng thời gian liên tiếp

Cho hai cửa sổ `[a, b)` và `[b, c)`, tạo dữ liệu:

| Giá trị createdAt | Cửa sổ thứ nhất | Cửa sổ thứ hai |
| --- | --- | --- |
| Trước a | Không | Không |
| Đúng a | Có | Không |
| Giữa a và b | Có | Không |
| Đúng b | Không | Có |
| Giữa b và c | Không | Có |
| Đúng c | Không | Không |

Nếu record tại b xuất hiện trong cả hai truy vấn, cần kiểm tra biên trên có bị chuyển thành `<=` hoặc BETWEEN bao gồm hai đầu không.

### 14.3. Ma trận kiểm tra bổ sung

| Nhóm | Tình huống cần xác minh |
| --- | --- |
| Loại bound | Cả bốn tổ hợp đóng/mở |
| Thiếu đầu mút | Chỉ lower, chỉ upper, cả hai unbounded |
| Thứ tự | Lower nhỏ hơn, bằng và lớn hơn upper |
| Kiểu số | BigDecimal có scale khác nhau, âm theo miền dữ liệu |
| Thời gian | Ngày lịch theo zone đã chọn, các ngày có chuyển đổi offset nếu hỗ trợ |
| Precision | Giá trị đọc lại từ store sát đầu mút |
| NULL | Giá trị NULL được xử lý đúng hợp đồng riêng |
| Tổ hợp | Hai Range kết hợp bằng AND |
| Phạm vi | Range unbounded vẫn giữ tenant/quyền truy cập |
| Hiệu năng | Bộ lọc, chỉ mục, sort và page size phù hợp |

### 14.4. Readback và precision của store

Một Instant ở Java có thể được lưu theo precision khác tùy kiểu cột, driver và cấu hình.

Trong kiểm tra tích hợp, hãy lưu fixture, đọc lại giá trị thực tế rồi xác minh truy vấn biên theo biểu diễn đã được hỗ trợ. Nếu chỉ dùng object trước khi lưu để suy ra vị trí chính xác của record, bạn có thể bỏ sót việc làm tròn hoặc cắt precision.

Tương tự, giá tiền cần được lưu theo scale và kiểu số phù hợp với hợp đồng.

Range giữ hai đầu mút trong Java; nó không tự đồng bộ quy tắc precision giữa Java và database.

## 15. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nhầm leftOpen với rightOpen | Bao gồm/loại sai đầu mút | Viết ký hiệu toán học trước khi chọn factory |
| Truyền null vào factory hữu hạn | Không biểu diễn được ý định không giới hạn | Dùng Bound.unbounded |
| Dùng BETWEEN cho mọi Range | Mất biên loại trừ | Dịch từng bound thành toán tử |
| Không kiểm tra lower/upper | Bộ lọc vô nghĩa hoặc rỗng ngoài ý muốn | Áp dụng validation miền |
| Dùng double tạo mốc tiền | Đầu mút có sai số ngoài hợp đồng | Dùng BigDecimal theo quy tắc rõ ràng |
| Cộng đúng 24 giờ cho mọi ngày lịch | Lệch cửa sổ tại một số zone/ngày | Tính đầu hai ngày lịch theo zone |
| Tạo mốc cuối ngày bằng millisecond | Bỏ sót dữ liệu precision cao hơn | Dùng đầu ngày kế tiếp làm biên loại trừ |
| Cho rằng Range tạo query tự động | Không có bộ lọc hoặc method không hỗ trợ | Dùng API của mô-đun cụ thể |
| Bỏ scope khi Range unbounded | Truy vấn rộng hơn phạm vi được phép | Giữ điều kiện bắt buộc độc lập |
| Coi unbounded là IS NULL | Sai ý nghĩa dữ liệu thiếu | Thiết kế bộ lọc NULL riêng |
| Map bằng hàm đảo thứ tự | Khoảng sau biến đổi sai | Kiểm tra và xây lại chính sách biên phù hợp |
| Chỉ test contains | Không phát hiện lỗi adapter/store | Kiểm tra thêm query tích hợp và readback |

## 16. Bài thực hành

1. Tạo Range<BigDecimal> cho giá bao gồm hai đầu và cho giá có biên trên loại trừ.
2. Tạo Range chỉ có biên dưới và giải thích vì sao không dùng một giá trị max giả.
3. Chuyển một ngày người dùng chọn thành Range<Instant> theo zone nghiệp vụ.
4. Chọn rõ hành vi khi lower lớn hơn upper hoặc hai đầu bằng nhau.
5. Viết adapter chuyển từng bound thành toán tử đúng cho store đang dùng.
6. Kết hợp khoảng thời gian, khoảng giá và phạm vi tenant bằng AND.
7. Kiểm tra các record đúng tại lower và upper.
8. Kiểm tra hai cửa sổ thời gian liên tiếp không cùng nhận một record tại biên chung.
9. Lưu và đọc lại fixture để kiểm tra precision thực tế.
10. Giải thích giới hạn nào thuộc Range, giới hạn nào thuộc validation và giới hạn nào thuộc mô-đun lưu trữ.

Bài thực hành đạt yêu cầu khi **kiểu dữ liệu, đầu mút và ký hiệu khoảng có cùng ý nghĩa**, đồng thời truy vấn thực tế giữ đúng **toán tử biên, phạm vi dữ liệu và chính sách precision** đã công bố.
