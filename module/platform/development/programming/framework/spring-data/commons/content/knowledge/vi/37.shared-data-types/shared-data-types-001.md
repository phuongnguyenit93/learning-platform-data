# Range, cận đóng/mở và khoảng không giới hạn

`org.springframework.data.domain.Range<T>` biểu diễn một khoảng giá trị bằng cận dưới và cận trên. Mỗi cận có thể nhận giá trị biên, loại giá trị biên hoặc không có giới hạn. Nhờ đó, điều kiện như “giá từ 100 đến dưới 500” được diễn tả rõ hơn một cặp biến mà người đọc phải tự đoán có lấy hai đầu hay không.

Bài học thuộc chương **Kiểu dữ liệu dùng chung** của module **SPRING_DATA_COMMONS**. Trọng tâm là ngữ nghĩa của khoảng và cách chuyển nó thành điều kiện dữ liệu đúng. Commons cung cấp value object dùng chung; việc một repository, derived query hay store cụ thể nhận và thực thi `Range` vẫn phụ thuộc khả năng tích hợp của mô-đun đó.

## 1. Một khoảng gồm hai cận có ý nghĩa độc lập

Với hai giá trị a và b, cần biết:

1. Cận dưới có tồn tại không?
2. Nếu có, giá trị bằng a được nhận hay bị loại?
3. Cận trên có tồn tại không?
4. Nếu có, giá trị bằng b được nhận hay bị loại?

Ký hiệu toán học thường dùng:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `[a, b]` | a ≤ x ≤ b |
| `(a, b)` | a < x < b |
| `(a, b]` | a < x ≤ b |
| `[a, b)` | a ≤ x < b |

Dấu ngoặc vuông nhận giá trị biên; dấu ngoặc tròn loại giá trị biên.

Ví dụ, khoảng giá `[100, 500)` nhận 100, 250 và 499.99 nhưng không nhận 500. Điều này khác `[100, 500]` ở đúng giá trị cận trên, một khác biệt nhỏ về ký hiệu nhưng có thể làm thay đổi kết quả truy vấn.

`Range` là value object biểu diễn các cận, không phải một collection chứa sẵn mọi giá trị ở giữa. Nó không tự sinh dãy số, tự tăng từng đơn vị hoặc truy cập database.

## 2. Tạo bốn loại khoảng hữu hạn

Import đúng kiểu của Spring Data:

```java
import org.springframework.data.domain.Range;
```

Các factory method tương ứng trực tiếp với ngữ nghĩa:

```java
Range<Integer> closed = Range.closed(5, 10);
Range<Integer> open = Range.open(5, 10);
Range<Integer> leftOpen = Range.leftOpen(5, 10);
Range<Integer> rightOpen = Range.rightOpen(5, 10);
```

| Biểu thức | Khoảng | Nhận 5? | Nhận 7? | Nhận 10? |
| --- | --- | --- | --- | --- |
| `Range.closed(5, 10)` | `[5, 10]` | Có | Có | Có |
| `Range.open(5, 10)` | `(5, 10)` | Không | Có | Không |
| `Range.leftOpen(5, 10)` | `(5, 10]` | Không | Có | Có |
| `Range.rightOpen(5, 10)` | `[5, 10)` | Có | Có | Không |

Trong tên `leftOpen`, “left” chỉ phía trái, tức cận dưới. Trong `rightOpen`, “right” chỉ phía phải, tức cận trên. Không đọc “open” thành “không giới hạn”: một cận mở vẫn có giá trị biên, chỉ không nhận chính giá trị đó.

Các factory và overload kiểm tra thuộc khoảng được công bố trong [Range API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Range.html).

### 2.1. Khoảng chứa đúng một số nguyên

```java
Range<Integer> exactlySeven = Range.just(7);

boolean containsSeven = exactlySeven.contains(7); // true
boolean containsEight = exactlySeven.contains(8); // false
```

Với trường hợp này, `just(7)` tương ứng `[7, 7]`. Hai cận bằng nhau không tự làm khoảng rỗng; còn phụ thuộc kiểu đóng hay mở.

### 2.2. Không thể nhận biết mọi khoảng rỗng chỉ bằng cách so hai đầu

Với thứ tự thông thường:

```text
[7, 7]  có giá trị 7
(7, 7)  không có giá trị nào
[7, 7)  không có giá trị nào
```

Ngoài ra, `(5, 6)` không chứa số nguyên nào nhưng có chứa số thập phân như 5.5 nếu miền giá trị là số thập phân.

Một phép kiểm tra “khoảng có phần tử không?” phải xét cả miền dữ liệu, thứ tự và ngữ nghĩa cận. Không tự chuyển quy tắc của số nguyên sang tiền, ngày tháng hoặc một kiểu domain khác.

## 3. Range.Bound biểu diễn một cận

Có thể tạo cận tường minh:

```java
import org.springframework.data.domain.Range;
import org.springframework.data.domain.Range.Bound;

Bound<Integer> lower = Bound.inclusive(5);
Bound<Integer> upper = Bound.exclusive(10);

Range<Integer> range = Range.of(lower, upper);
```

Khoảng trên là `[5, 10)`. Một cách viết bằng builder:

```java
Range<Integer> range = Range
        .from(Bound.inclusive(5))
        .to(Bound.exclusive(10));
```

Hai cách giúp giữ riêng quyết định của mỗi cận, đặc biệt khi cận được tạo từ bộ lọc động.

### 3.1. Đọc trạng thái cận

```java
Range<Integer> range = Range.rightOpen(5, 10);

Bound<Integer> lower = range.getLowerBound();
Bound<Integer> upper = range.getUpperBound();

boolean lowerHasValue = lower.isBounded();   // true
boolean lowerIncludes = lower.isInclusive(); // true
Integer lowerValue = lower.getValue().orElseThrow(); // 5

boolean upperIncludes = upper.isInclusive(); // false
```

`getValue()` trả `Optional<T>`. Cần xét cận có giới hạn hay không trước khi yêu cầu một giá trị bắt buộc.

Đối với cận không giới hạn, không diễn giải riêng cờ inclusive như thể đang có một giá trị biên thực sự. Cận không có giá trị là trạng thái khác với cận đóng hoặc mở tại một giá trị cụ thể. Các phương thức này thuộc [Range.Bound API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Range.Bound.html).

### 3.2. Không dùng null để tạo cận hữu hạn

Các lời gọi tạo cận có giá trị yêu cầu giá trị không null:

```text
Bound.inclusive(null) không biểu diễn “không có cận”.
Range.closed(min, null) không phải khoảng chỉ có cận dưới.
```

Muốn bỏ một cận, dùng factory không giới hạn tương ứng. Điều này làm ý định rõ ràng và tránh nhập nhằng giữa dữ liệu thiếu với một giá trị miền hợp lệ.

## 4. Khoảng không giới hạn một phía hoặc cả hai phía

### 4.1. Không có cận dưới

```java
Range<Integer> atMostTen =
        Range.leftUnbounded(Bound.inclusive(10));

Range<Integer> lessThanTen =
        Range.leftUnbounded(Bound.exclusive(10));
```

Ý nghĩa:

| Biểu thức | Khoảng | Điều kiện |
| --- | --- | --- |
| `leftUnbounded(inclusive(10))` | `(-∞, 10]` | x ≤ 10 |
| `leftUnbounded(exclusive(10))` | `(-∞, 10)` | x < 10 |

### 4.2. Không có cận trên

```java
Range<Integer> atLeastFive =
        Range.rightUnbounded(Bound.inclusive(5));

Range<Integer> greaterThanFive =
        Range.rightUnbounded(Bound.exclusive(5));
```

Ý nghĩa:

| Biểu thức | Khoảng | Điều kiện |
| --- | --- | --- |
| `rightUnbounded(inclusive(5))` | `[5, +∞)` | x ≥ 5 |
| `rightUnbounded(exclusive(5))` | `(5, +∞)` | x > 5 |

### 4.3. Không giới hạn cả hai phía

```java
Range<Integer> allIntegers = Range.unbounded();

boolean containsNegative = allIntegers.contains(-100); // true
boolean containsPositive = allIntegers.contains(100);  // true
```

Cũng có thể tạo từ hai cận không giới hạn:

```java
Range<Integer> allIntegers = Range.of(
        Bound.<Integer>unbounded(),
        Bound.<Integer>unbounded());
```

Các ký hiệu ∞ ở đây chỉ mang ý nghĩa toán học. Không cần và không nên thay chúng bằng một giá trị giả như `Integer.MIN_VALUE`, `Integer.MAX_VALUE` hay một ngày rất xa để biểu diễn “không có cận”.

Một giá trị tối đa vẫn là giá trị hữu hạn của kiểu đó. Khi kiểu dữ liệu hoặc chính sách domain thay đổi, giá trị giả có thể không còn diễn đạt đúng ý định.

### 4.4. Không giới hạn không đồng nghĩa nhận null

`Range.unbounded()` không phải một yêu cầu rằng `contains(null)` phải trả true. API kiểm tra thuộc khoảng yêu cầu giá trị tham chiếu không null.

Nếu một cột database được phép null, ứng dụng phải định nghĩa riêng việc bộ lọc khoảng xử lý các bản ghi null ra sao. Bỏ điều kiện so sánh trong query và gọi `Range.contains` trong Java không tự tạo ra một hợp đồng null giống nhau.

## 5. Kiểm tra một giá trị có thuộc khoảng không

### 5.1. Kiểu có thứ tự tự nhiên phù hợp

```java
Range<Integer> interval = Range.rightOpen(5, 10);

boolean a = interval.contains(4);  // false
boolean b = interval.contains(5);  // true
boolean c = interval.contains(9);  // true
boolean d = interval.contains(10); // false
```

Về ngữ nghĩa, giá trị phải thỏa cả hai phía:

```text
Thỏa cận dưới AND thỏa cận trên
```

Nếu một phía không có giới hạn, phía đó không tạo thêm ràng buộc so sánh. Cách thực hiện được thể hiện trong [mã nguồn Range](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/domain/Range.java).

### 5.2. Dùng Comparator khi cần chỉ rõ thứ tự

`Range<T>` không buộc T phải triển khai một giao diện Comparable cụ thể ngay tại khai báo lớp. Có thể cung cấp comparator khi kiểm tra:

```java
import java.util.Comparator;

Range<String> names = Range.closed("an", "minh");

boolean included = names.contains(
        "Binh",
        String.CASE_INSENSITIVE_ORDER);
```

Kết quả được quyết định theo comparator đã chọn, không theo một khái niệm thứ tự “đúng cho mọi ngôn ngữ”. Với văn bản có dấu hoặc yêu cầu collation riêng, cần xác định chính sách so sánh tương ứng.

Một ví dụ với ngày:

```java
import java.time.LocalDate;
import java.util.Comparator;

Range<LocalDate> dates = Range.rightOpen(
        LocalDate.of(2026, 11, 1),
        LocalDate.of(2026, 12, 1));

boolean included = dates.contains(
        LocalDate.of(2026, 11, 25),
        Comparator.naturalOrder());
```

Overload tiện ích một tham số nhận `Comparable<T>`. Trong khi đó, `LocalDate` triển khai `Comparable<ChronoLocalDate>`, nên việc truyền comparator tường minh cũng tránh vướng khác biệt generic này. Hệ kiểu và ngữ nghĩa ngày không có múi giờ được mô tả trong [LocalDate API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html).

Dùng cùng một quy tắc thứ tự khi xác minh cận và khi kiểm tra giá trị. Đổi comparator giữa hai bước có thể làm “cận dưới” không còn đứng trước “cận trên”.

## 6. Tự kiểm tra tính hợp lệ của thứ tự cận

Không coi việc tạo được một `Range` là bằng chứng rằng cận dưới nhỏ hơn hoặc bằng cận trên.

Ví dụ:

```java
Range<Integer> reversed = Range.closed(10, 5);
```

Không dựa vào factory này để tự hoán đổi 10 và 5 hoặc tự phát sinh lỗi thứ tự cho ứng dụng. Trong implementation được dẫn, việc tạo khoảng tập trung vào hai đối tượng cận; chính sách kiểm tra thứ tự thuộc trách nhiệm sử dụng.

Một helper xác minh thứ tự có thể viết:

```java
import java.util.Comparator;
import java.util.Objects;
import java.util.Optional;

import org.springframework.data.domain.Range;

static <T> void requireOrdered(
        Range<T> range,
        Comparator<T> comparator) {

    Objects.requireNonNull(range);
    Objects.requireNonNull(comparator);

    Optional<T> lower = range.getLowerBound().getValue();
    Optional<T> upper = range.getUpperBound().getValue();

    if (lower.isPresent()
            && upper.isPresent()
            && comparator.compare(
                    lower.orElseThrow(),
                    upper.orElseThrow()) > 0) {

        throw new IllegalArgumentException(
                "Lower bound must not exceed upper bound");
    }
}
```

Đặt helper này trong một lớp của ứng dụng. Nó chỉ kiểm tra thứ tự hai giá trị hữu hạn, chưa khẳng định khoảng có phần tử.

Nếu use case cấm khoảng rỗng, cần thêm chính sách tương ứng. Hai đầu bằng nhau mà có cận mở là một trường hợp có thể kiểm tra; khoảng nguyên `(5, 6)` còn cần hiểu miền số nguyên. Không gộp mọi quy tắc này vào một khẳng định chung rằng “lower ≤ upper là đủ”.

Không tự sửa đầu vào đảo cận nếu hợp đồng API yêu cầu từ chối. Việc âm thầm đổi chỗ có thể làm một lỗi nhập liệu trở thành một truy vấn khác với ý định người dùng.

## 7. Ví dụ khoảng giá với BigDecimal

### 7.1. Dùng giá trị thập phân phù hợp

```java
import java.math.BigDecimal;

import org.springframework.data.domain.Range;

Range<BigDecimal> prices = Range.rightOpen(
        new BigDecimal("100.00"),
        new BigDecimal("500.00"));

boolean atLower = prices.contains(
        new BigDecimal("100.00")); // true

boolean atUpper = prices.contains(
        new BigDecimal("500.00")); // false
```

Với tiền, cần chọn kiểu và chính sách làm tròn phù hợp thay vì vô tình đưa sai số biểu diễn nhị phân vào cận. Đồng tiền, đơn vị và scale được chấp nhận vẫn là quy tắc domain; `Range<BigDecimal>` không tự biết hai số đang dùng cùng một đơn vị tiền.

`BigDecimal.compareTo` so sánh giá trị số, trong khi `equals` còn xét biểu diễn với scale. Vì vậy kiểm tra thuộc khoảng và so sánh bằng nhau của chính các value object không nên bị coi là cùng một phép toán. Xem [BigDecimal API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html).

### 7.2. Chuyển cận tùy chọn từ hợp đồng API

Giả sử một API có quy ước:

```text
minPrice có mặt -> cận dưới đóng
maxPrice có mặt -> cận trên đóng
Không có tham số tương ứng -> không giới hạn phía đó
Giá hữu hạn phải không âm
Nếu có cả hai -> minPrice không vượt maxPrice
```

Có thể chuyển sang Range:

```java
import java.math.BigDecimal;

import org.springframework.data.domain.Range;
import org.springframework.data.domain.Range.Bound;

static Range<BigDecimal> toPriceRange(
        BigDecimal minPrice,
        BigDecimal maxPrice) {

    if ((minPrice != null && minPrice.signum() < 0)
            || (maxPrice != null && maxPrice.signum() < 0)) {

        throw new IllegalArgumentException(
                "Price bounds must not be negative");
    }

    if (minPrice != null
            && maxPrice != null
            && minPrice.compareTo(maxPrice) > 0) {

        throw new IllegalArgumentException(
                "minPrice must not exceed maxPrice");
    }

    Bound<BigDecimal> lower = minPrice == null
            ? Bound.unbounded()
            : Bound.inclusive(minPrice);

    Bound<BigDecimal> upper = maxPrice == null
            ? Bound.unbounded()
            : Bound.inclusive(maxPrice);

    return Range.of(lower, upper);
}
```

Null ở đây chỉ là cách biểu diễn tham số vắng mặt tại ranh giới chuyển đổi. Sau chuyển đổi, trạng thái không giới hạn được mô tả bằng `Bound.unbounded()`, không phải một cận hữu hạn có giá trị null.

Nếu API cho phép chọn đóng hay mở, cần bổ sung đầu vào và validation riêng. Không đổi ngầm `maxPrice` thành cận mở chỉ vì một endpoint khác đang dùng khoảng nửa mở.

## 8. Khoảng thời gian nửa mở để chia giai đoạn

Một cách biểu diễn hữu ích cho báo cáo theo giai đoạn là:

```text
[start, nextStart)
```

Ví dụ hai khoảng liên tiếp:

```text
[2026-11-01, 2026-12-01)
[2026-12-01, 2027-01-01)
```

Một thời điểm đúng tại đầu tháng 12 chỉ thuộc khoảng thứ hai. Không phải trừ một nano giây khỏi mốc tháng sau để tránh trùng biên.

Nếu dữ liệu lưu theo `Instant`, cần chuyển ngày địa phương bằng múi giờ nghiệp vụ:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

import org.springframework.data.domain.Range;

ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant start = LocalDate.of(2026, 11, 1)
        .atStartOfDay(businessZone)
        .toInstant();

Instant endExclusive = LocalDate.of(2026, 12, 1)
        .atStartOfDay(businessZone)
        .toInstant();

Range<Instant> november =
        Range.rightOpen(start, endExclusive);
```

Không mặc định ngày địa phương là một mốc UTC. Với vùng có chuyển đổi giờ theo mùa, cũng không nên thay ngày bắt đầu kế tiếp bằng cách cộng cứng số giờ của một ngày vào một instant rồi coi mọi ngày đều giống nhau.

Độ chính xác thời gian của database và driver vẫn phải được xét khi chuyển cận sang truy vấn. Khoảng nửa mở giúp tránh phụ thuộc vào việc đoán “thời điểm cuối cùng có thể lưu” của một ngày.

## 9. Map chuyển giá trị cận, không tự chứng minh ngữ nghĩa mới

`Range.map` áp dụng hàm chuyển đổi lên các giá trị cận. Ví dụ:

```java
Range<Integer> input = Range.rightOpen(10, 20);

Range<Long> converted = input.map(Integer::longValue);
```

Phép đổi này giữ thứ tự giá trị, nên khoảng mới có ý nghĩa tương ứng `[10L, 20L)`.

Nhưng không phải hàm nào cũng giữ thứ tự:

```text
[10, 20) rồi đổi mỗi cận bằng x -> -x
    -> hai giá trị cận trở thành -10 và -20
```

Ảnh đúng của khoảng ban đầu qua phép đổi dấu là `(-20, -10]`. Map hai cận như trên không tự tạo ra kết quả đó. Phải xem lại cả vị trí cận và kiểu nhận/loại biên nếu thực sự muốn biến đổi tập giá trị.

Cũng cần chú ý: nếu mapper trả null cho một giá trị cận, API chuyển cận tương ứng thành không giới hạn. Không dùng một hàm “parse lỗi thì trả null” để map cận rồi mặc định truy vấn vẫn giữ phạm vi ban đầu.

`map` không kiểm tra tính đơn điệu, đơn vị hay quy tắc nghiệp vụ của hàm chuyển đổi. Các chi tiết map cận, bao gồm trường hợp trả null, được công bố trong [Range.Bound.map](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Range.Bound.html#map(java.util.function.Function)).

## 10. Chuyển khoảng sang truy vấn phải giữ nguyên ngữ nghĩa

Đối với một property x:

| Cận | Điều kiện truy vấn tương ứng về ý nghĩa |
| --- | --- |
| Cận dưới đóng a | x ≥ a |
| Cận dưới mở a | x > a |
| Cận trên đóng b | x ≤ b |
| Cận trên mở b | x < b |
| Cận không giới hạn | Không thêm điều kiện của phía đó |

Hai phía được kết hợp bằng AND. Ví dụ `[100, 500)` phải giữ cận trên loại 500, không biến thành một phép so sánh nhận cả hai đầu chỉ vì tên truy vấn có chữ “between”.

Không giả định mọi phương thức derived query tên `Between` ở mọi store đều hiểu đủ cận đóng/mở hoặc nhận trực tiếp `Range<T>`. Cần kiểm tra hợp đồng của mô-đun cụ thể. Nếu store không có đường tích hợp đó, ứng dụng phải chuyển các cận sang criteria, predicate hoặc cách truy vấn được hỗ trợ.

Một số giới hạn cần giữ rõ:

- `Range` không tự đăng ký converter HTTP cho mọi kiểu T.
- Một property có kiểu `Range` không tự trở thành kiểu khoảng native của database.
- Query by Example không tự biến một field probe thành mọi loại điều kiện khoảng.
- Projection đầu ra không thay đổi ngữ nghĩa cận của truy vấn.
- Metadata auditing như thời điểm tạo chỉ lọc theo khoảng đúng khi dùng đúng kiểu thời gian, múi giờ và hỗ trợ truy vấn của store.

Không tải toàn bộ dữ liệu rồi gọi `contains` trong Java như một cách mặc định thay thế truy vấn có giới hạn. Lọc sau khi phân trang còn có thể làm nội dung và tổng số phần tử mô tả hai tập kết quả khác nhau.

Khoảng không giới hạn cũng không loại bỏ những điều kiện bắt buộc khác như tenant, quyền đọc hoặc phạm vi nghiệp vụ. Nó chỉ không đặt cận trên property đang xét.

## 11. Những tình huống cần xác nhận

Với một khoảng hữu hạn, các giá trị tại biên thường quan trọng hơn một giá trị nằm sâu bên trong:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Giá trị ngay dưới cận dưới | Không được nhận theo thứ tự đã chọn |
| Giá trị đúng cận dưới | Phụ thuộc cận đóng hay mở |
| Giá trị bên trong | Thỏa cả hai cận |
| Giá trị đúng cận trên | Phụ thuộc cận đóng hay mở |
| Một phía không giới hạn | Không phát sinh điều kiện so sánh phía đó |
| Hai phía không giới hạn | Không bị thay bằng các giá trị giả hữu hạn |
| Hai cận bằng nhau | Phân biệt khoảng một điểm với khoảng rỗng |
| Cận dưới vượt cận trên | Xử lý theo chính sách validation |
| Khoảng giữa hai số nguyên liên tiếp | Xét miền dữ liệu khi kết luận rỗng |
| Giá trị null | Có chính sách riêng, không coi là một điểm trong khoảng |
| Chuyển kiểu hoặc map cận | Giữ đúng thứ tự, đơn vị và kiểu cận |
| Chuyển xuống store | Ngữ nghĩa so sánh không bị đổi ở hai đầu |
| Chia thời gian thành các kỳ liên tiếp | Không lặp hoặc bỏ sót dữ liệu tại mốc tiếp giáp |

Chọn đúng kiểu cận giúp biến một điều kiện mơ hồ thành một hợp đồng rõ ràng. Sau đó, ứng dụng vẫn phải kiểm tra đầu vào và bảo đảm repository thực thi đúng khoảng đã được biểu diễn.
