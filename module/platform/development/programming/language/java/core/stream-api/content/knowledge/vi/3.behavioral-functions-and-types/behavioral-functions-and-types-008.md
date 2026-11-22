# Thiết kế hàm thuần và hàm ánh xạ dễ kiểm thử

## 1. Vì sao hàm ánh xạ cần dễ kiểm thử?

Trong Java Stream API, một pipeline thường có dạng **nguồn dữ liệu → các phép toán trung gian → phép toán kết thúc**. Ví dụ, `filter` lựa chọn đơn hàng, `map` biến đổi đơn hàng thành dữ liệu hiển thị, `reduce` hoặc `collect` tổng hợp kết quả. Các phép toán trung gian phần lớn được thực thi **lười** (*lazy*): Java chỉ đánh giá chúng khi một phép toán kết thúc cần dữ liệu.

Điều đó đặt ra yêu cầu quan trọng: hàm được truyền vào `map` phải có hành vi rõ ràng ngay cả khi Java gọi hàm vào thời điểm khác dự kiến, bỏ qua một số lời gọi do tối ưu hóa, hoặc chia công việc cho nhiều luồng. Một **hàm thuần** (*pure function*) là cách thiết kế phù hợp: với cùng đầu vào, hàm trả cùng kết quả và không tạo tác dụng phụ có thể quan sát từ bên ngoài.

Mục tiêu của bài học:

- Phân biệt hàm thuần, hàm có trạng thái và hàm có tác dụng phụ trong Java.
- Thiết kế ánh xạ `T → R` thành phương thức nhỏ, có hợp đồng đầu vào/đầu ra rõ ràng.
- Biến các phụ thuộc như thời gian, thuế suất, cấu hình thành đầu vào tường minh.
- Kết hợp `Function`, `map`, `mapToLong` và `flatMap` mà không làm mất tính dễ kiểm thử.
- Kiểm thử trực tiếp từng hàm bằng JUnit 5, sau đó kiểm thử tích hợp trong pipeline.
- Nhận diện các giới hạn về dữ liệu mutable, lỗi, thứ tự, thực thi song song và hiệu năng.

## 2. Hiểu chính xác “thuần” trong Java

Hàm thuần cần đáp ứng hai điều kiện chính:

1. **Đầu ra chỉ phụ thuộc vào đầu vào**: cùng dữ liệu và cùng ngữ cảnh đã được truyền vào, hàm luôn trả kết quả có cùng giá trị.
2. **Không có tác dụng phụ quan sát được**: hàm không thay đổi trạng thái bên ngoài, không sửa đối tượng đầu vào, không ghi file, gửi yêu cầu mạng, cập nhật database, ghi log như một phần nghiệp vụ hoặc thay đổi bộ đếm dùng chung.

Ví dụ:

```java
static int square(int value) {
    return value * value;
}

static String normalizeRegion(String region) {
    return region.strip().toUpperCase(java.util.Locale.ROOT);
}
```

`square(4)` luôn cho `16`. `normalizeRegion(" hn ")` luôn cho `"HN"` vì locale được cố định bằng `Locale.ROOT`. Hai hàm tạo kết quả từ đầu vào mà không sửa trạng thái khác.

Ngược lại:

```java
static int counter = 0;

static int nextSequence(int value) {
    return value + ++counter;
}

static String normalizeUsingCurrentLocale(String value) {
    return value.toUpperCase(); // Phụ thuộc vào default locale của môi trường.
}
```

`nextSequence(4)` trả kết quả khác nhau giữa các lần gọi. `normalizeUsingCurrentLocale` có thể tạo kết quả khác nhau khi default locale thay đổi. Để làm hành vi rõ ràng và dễ kiểm thử, hãy truyền `Locale` vào hàm hoặc chọn `Locale.ROOT` khi nghiệp vụ yêu cầu phép chuẩn hóa độc lập ngôn ngữ.

**Phân biệt các tính chất thường bị nhầm:**

| Tính chất | Ý nghĩa | Có đồng nghĩa với hàm thuần không? |
| --- | --- | --- |
| Deterministic | Cùng đầu vào cho cùng đầu ra trong ngữ cảnh đã xác định | Chưa đủ: hàm vẫn có thể ghi log, tăng bộ đếm |
| Stateless | Không phụ thuộc vào trạng thái thay đổi giữa các lời gọi | Chưa đủ: hàm vẫn có thể sửa dữ liệu đầu vào |
| Non-interfering | Không can thiệp nguồn dữ liệu đang được Stream duyệt | Là yêu cầu quan trọng của Stream, nhưng chưa bao hàm mọi tác dụng phụ |
| Thread-safe | Có thể gọi đồng thời mà không làm hỏng trạng thái | Chưa đủ: `AtomicInteger.incrementAndGet()` an toàn luồng nhưng vẫn thay đổi trạng thái |
| Pure | Đầu ra phụ thuộc đầu vào, không có tác dụng phụ quan sát được | Đáp ứng cả tính quyết định và không có tác dụng phụ |

Một hàm có thể dùng **biến cục bộ**, tạo object mới hoặc dùng bộ đệm cục bộ mà vẫn thuần, miễn là chúng không làm rò rỉ trạng thái mutable hoặc thay đổi dữ liệu bên ngoài. Tính thuần nói về **hành vi có thể quan sát**, không có nghĩa là tuyệt đối không cấp phát bộ nhớ.

Ngoài ra, **idempotent** khác **pure**: `f(f(x)) == f(x)` là tính lũy đẳng, còn tính thuần nói về kết quả và tác dụng phụ. Hàm `square` thuần nhưng không lũy đẳng vì `square(square(2)) == 16` khác `square(2) == 4`.

## 3. Đọc chữ ký trước khi viết mapper

Phương thức cơ bản trên `Stream<T>` có dạng:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper)
```

- `T`: kiểu phần tử đầu vào của stream hiện tại.
- `R`: kiểu phần tử đầu ra sau ánh xạ.
- `Function<T,R>`: biểu diễn phép biến đổi một giá trị kiểu `T` thành một giá trị kiểu `R`.
- `? super T` và `? extends R`: cho phép các kiểu cha/kiểu con tương thích khi truyền hàm.
- `Stream<R>`: kết quả là một stream mới, chưa tự động chạy pipeline.

`map` là phép biến đổi **một phần tử thành một kết quả** mỗi khi mapper được đánh giá. Nếu muốn loại phần tử, thông thường dùng `filter`; nếu một phần tử có thể sinh ra không, một hoặc nhiều kết quả, cân nhắc `flatMap` hoặc `mapMulti`. Không sử dụng giá trị `null` để ngầm diễn tả “bỏ phần tử” khi có thể biểu diễn chính sách rõ ràng hơn.

Các functional interface thường gặp trong chương **Hàm hành vi và kiểu dữ liệu**:

| Interface | Dạng hàm | Cách dùng phổ biến trong Stream |
| --- | --- | --- |
| `Function<T,R>` | `T → R` | `map`, biến đổi bản ghi thành DTO |
| `UnaryOperator<T>` | `T → T` | Chuẩn hóa cùng kiểu |
| `Predicate<T>` | `T → boolean` | `filter`, `anyMatch` |
| `ToIntFunction<T>` / `ToLongFunction<T>` | `T → int/long` | `mapToInt`, `mapToLong` |
| `BinaryOperator<T>` | `(T,T) → T` | `reduce` với phép gộp cùng kiểu |
| `BiFunction<T,U,R>` | `(T,U) → R` | Biểu diễn ánh xạ cần hai đầu vào |
| `Consumer<T>` | `T → void` | `forEach`; thường chứa tác dụng phụ |
| `Supplier<T>` | `() → T` | Tạo giá trị/bộ tích lũy theo yêu cầu |

Đừng cho rằng mọi `Consumer` hay `Supplier` đều không thuần: cần đánh giá cách triển khai. Tuy nhiên, các mapper từ dữ liệu đầu vào sang giá trị đầu ra thường dễ làm thuần hơn các hàm chủ yếu phục vụ I/O.

## 4. Một mapper nghiệp vụ có hợp đồng rõ ràng

Giả sử dữ liệu bán hàng đầu vào gồm mã đơn, vùng, số lượng và đơn giá. Hệ thống muốn tạo đối tượng hiển thị với vùng được chuẩn hóa và thành tiền đã tính. Ta thiết kế ánh xạ:

```text
RawOrder(id, region, quantity, unitPrice)
              │
              ▼
      OrderMapper.toView
              │
              ▼
OrderView(id, normalizedRegion, amount)
```

Mã hoàn chỉnh dưới đây chạy với **JDK 17 trở lên** (sử dụng `record` và `Stream.toList()`):

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

public class OrderMapper {

    public record RawOrder(
        String id,
        String region,
        int quantity,
        BigDecimal unitPrice
    ) {}

    public record OrderView(
        String id,
        String region,
        BigDecimal amount
    ) {}

    public static OrderView toView(RawOrder raw) {
        Objects.requireNonNull(raw, "raw");

        if (raw.id() == null || raw.id().isBlank()) {
            throw new IllegalArgumentException("id không được trống");
        }
        if (raw.region() == null || raw.region().isBlank()) {
            throw new IllegalArgumentException("region không được trống");
        }
        Objects.requireNonNull(raw.unitPrice(), "unitPrice");
        if (raw.quantity() <= 0) {
            throw new IllegalArgumentException("quantity phải dương");
        }
        if (raw.unitPrice().signum() < 0) {
            throw new IllegalArgumentException("unitPrice không được âm");
        }

        String normalizedRegion = raw.region()
            .strip()
            .toUpperCase(Locale.ROOT);
        BigDecimal amount = raw.unitPrice()
            .multiply(BigDecimal.valueOf(raw.quantity()));

        return new OrderView(
            raw.id().strip(),
            normalizedRegion,
            amount
        );
    }

    public static void main(String[] args) {
        List<RawOrder> rows = List.of(
            new RawOrder("O-1", " hn ", 2, new BigDecimal("100.00")),
            new RawOrder("O-2", "HN", 1, new BigDecimal("50.00")),
            new RawOrder("O-3", "hcm", 3, new BigDecimal("20.00"))
        );

        List<OrderView> views = rows.stream()
            .map(OrderMapper::toView)
            .toList();

        Map<String, BigDecimal> revenueByRegion = views.stream()
            .collect(Collectors.groupingBy(
                OrderView::region,
                Collectors.reducing(
                    BigDecimal.ZERO,
                    OrderView::amount,
                    BigDecimal::add
                )
            ));

        System.out.println(views.get(0));
        // OrderView[id=O-1, region=HN, amount=200.00]
        System.out.println(revenueByRegion.get("HN"));  // 250.00
        System.out.println(revenueByRegion.get("HCM")); // 60.00
    }
}
```

**Vì sao `toView` dễ kiểm thử?**

1. **Đầu vào duy nhất:** `RawOrder`, không truy cập database, đồng hồ hay biến toàn cục.
2. **Kết quả rõ kiểu:** `OrderView`, không trả cấu trúc mập mờ như `Object[]` hoặc `Map<String,Object>`.
3. **Không sửa đầu vào:** tạo `OrderView` mới, không viết vào `RawOrder`.
4. **Chuẩn hóa nhất quán:** `strip()` và `Locale.ROOT` cho đầu ra độc lập default locale.
5. **Quy tắc dữ liệu hiển thị:** lượng không dương, giá âm, mã/vùng rỗng được từ chối có chủ đích.
6. **Có thể gọi độc lập:** không cần tạo `Stream` để kiểm thử `toView`.

Trong ví dụ, `String` và `BigDecimal` đều bất biến (*immutable*) nên các thành phần chứa trong hai record an toàn trước việc sửa dữ liệu. Tuy nhiên **`record` chỉ bất biến ở mức tham chiếu trường**: nếu trường là `List` hoặc object mutable, cần sao chép phòng vệ khi tạo bản ghi và khi công khai dữ liệu nếu muốn bảo đảm bất biến thực sự.

`BigDecimal` phù hợp hơn `double` khi tính tiền để tránh sai số biểu diễn nhị phân. Phép tính `quantity × unitPrice` ở đây không làm tròn; nếu nghiệp vụ yêu cầu thuế/chiết khấu, phải chỉ rõ **thời điểm và quy tắc làm tròn**. Việc làm tròn từng dòng có thể khác làm tròn trên tổng.

## 5. Tách hàm nghiệp vụ khỏi pipeline

Viết nguyên toàn bộ công thức trong `map` có thể làm code ngắn nhưng khó đặt tên, tái sử dụng và kiểm thử:

```java
// Khó kiểm thử độc lập nếu biểu thức ngày càng phức tạp.
List<OrderMapper.OrderView> views = rows.stream()
    .map(row -> new OrderMapper.OrderView(
        row.id().strip(),
        row.region().strip().toUpperCase(Locale.ROOT),
        row.unitPrice().multiply(BigDecimal.valueOf(row.quantity()))
    ))
    .toList();
```

Lambda này cũng **bỏ qua phần kiểm tra dữ liệu** của `toView`. Khi nghiệp vụ phát triển, logic rải rác ở nhiều pipeline dễ bị lệch nhau. Cách rõ ràng hơn:

```java
List<OrderMapper.OrderView> views = rows.stream()
    .map(OrderMapper::toView)
    .toList();
```

Phương thức thuần làm nhiệm vụ chuyển đổi; pipeline chịu trách nhiệm **chọn nguồn, lọc, nhóm và tập hợp kết quả**. Một mapper có tên diễn đạt ý định giúp người đọc hiểu dữ liệu đang chuyển từ kiểu nào sang kiểu nào mà không phải phân tích một lambda dài.

### 5.1. Ghép các bước thuần với `Function`

`Function` có `compose`, `andThen` và `identity`:

```java
import java.util.Locale;
import java.util.function.Function;

Function<String, String> strip = String::strip;
Function<String, String> uppercase = s -> s.toUpperCase(Locale.ROOT);

Function<String, String> normalize = strip.andThen(uppercase);
Function<String, String> alsoNormalize = uppercase.compose(strip);

System.out.println(normalize.apply(" hn "));     // HN
System.out.println(alsoNormalize.apply(" hn ")); // HN
System.out.println(Function.<String>identity().apply("A")); // A
```

Với `f.andThen(g)`, Java thực hiện `g(f(x))`; với `g.compose(f)` cũng là `g(f(x))`. Khi các hàm thành phần thuần, việc ghép này vẫn thuần, đồng thời dễ viết test cho từng phép biến đổi.

Không phải mọi phép ghép đều hoán đổi được: `strip.andThen(uppercase)` có thể phù hợp, nhưng đổi thứ tự hai phép xử lý khác có thể làm thay đổi kết quả. Kiểm thử dựa trên **hợp đồng nghiệp vụ**, không giả định thứ tự là tùy ý.

### 5.2. Chọn đúng phép ánh xạ

| Nhu cầu | Phép toán | Ví dụ |
| --- | --- | --- |
| Mỗi đơn hàng → một DTO | `map` | `.map(OrderMapper::toView)` |
| Mỗi đơn hàng → một giá trị `long` | `mapToLong` | `.mapToLong(OrderMapper.RawOrder::quantity)` |
| Mỗi nhóm chứa nhiều phần tử → dãy phẳng | `flatMap` | `.flatMap(List::stream)` |
| Mỗi phần tử có thể phát 0–n kết quả qua `Consumer` | `mapMulti` (JDK 16+) | Dùng khi không cần tạo stream con cho mỗi phần tử |
| Chỉ giữ bản ghi thỏa quy tắc | `filter` | `.filter(row -> row.quantity() > 0)` |

Ví dụ phân biệt `map` và `flatMap`:

```java
List<List<String>> groups = List.of(
    List.of("A", "B"),
    List.of("C")
);

List<Integer> groupSizes = groups.stream()
    .map(List::size)
    .toList(); // [2, 1]

List<String> members = groups.stream()
    .flatMap(List::stream)
    .toList(); // [A, B, C]
```

## 6. Đưa phụ thuộc thay đổi thành tham số tường minh

Một mapper không nên tự tìm tỷ giá, đồng hồ hiện tại hoặc thuế suất trong lúc duyệt dữ liệu:

```java
// Thiết kế phụ thuộc bên ngoài; khó tạo kết quả ổn định khi kiểm thử.
// .map(order -> convert(order, rateService.currentRate()))
```

Nếu nghiệp vụ cho phép sử dụng **một thuế suất chụp tại thời điểm bắt đầu xử lý**, đọc thuế suất ở ranh giới I/O trước, rồi truyền giá trị cố định vào hàm:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

static BigDecimal priceWithTax(
    BigDecimal amount,
    BigDecimal taxRate
) {
    if (amount == null || taxRate == null) {
        throw new IllegalArgumentException("amount/taxRate không được null");
    }
    if (amount.signum() < 0 || taxRate.signum() < 0) {
        throw new IllegalArgumentException("giá trị không được âm");
    }
    return amount
        .multiply(BigDecimal.ONE.add(taxRate))
        .setScale(2, RoundingMode.HALF_UP);
}

BigDecimal fixedTaxRate = new BigDecimal("0.08");
List<BigDecimal> amountsWithTax = rows.stream()
    .map(OrderMapper::toView)
    .map(view -> priceWithTax(view.amount(), fixedTaxRate))
    .toList();
```

Đoạn trên minh họa phương thức `priceWithTax` đặt trong một lớp/hàm bao phù hợp và biến `rows` từ ví dụ trước. `BigDecimal` bất biến; biến `fixedTaxRate` không thay đổi trong pipeline, nên mapper không lệ thuộc vào giá trị biến thiên theo thời gian. Muốn hỗ trợ loại thuế, tỷ giá hoặc cách làm tròn khác nhau, hãy thêm tham số hoặc một **value object cấu hình bất biến**, rồi kiểm thử từng trường hợp.

Với thời gian, truyền `Instant`, `LocalDate` hoặc `Clock` một cách có chủ đích. Nếu nhận `Clock` và gọi `instant()` trong mapper, kết quả còn phụ thuộc thời điểm gọi; để ánh xạ thuần với “thời điểm xử lý”, hãy lấy một `Instant` cố định trước khi tạo pipeline và truyền trực tiếp vào mapper. Tương tự, nếu kết quả phụ thuộc timezone, truyền `ZoneId` thay vì âm thầm dùng timezone mặc định.

**Phân biệt capture an toàn và capture nguy hiểm:**

```java
String prefix = "ORDER-"; // String bất biến, giá trị cố định.
List<String> ids = List.of("1", "2").stream()
    .map(id -> prefix + id)
    .toList(); // [ORDER-1, ORDER-2]
```

Một biến được lambda capture phải là `final` hoặc *effectively final*; điều này **không bảo đảm object mà biến tham chiếu là bất biến**. Chẳng hạn `final List<String> shared` vẫn có thể bị sửa qua `shared.add(...)`. Hãy bảo đảm cả **giá trị và nội dung được capture** ổn định nếu cần hàm thuần.

## 7. Các phản ví dụ thường gặp

### 7.1. Sửa danh sách đầu ra trong mapper

```java
import java.util.ArrayList;
import java.util.List;

List<String> sharedResults = new ArrayList<>();
List<String> names = List.of("An", "Bình", "Chi");

// Tránh cách này:
names.stream()
    .map(name -> {
        sharedResults.add(name.toUpperCase());
        return name;
    })
    .toList();

// Dùng ánh xạ để tạo kết quả:
List<String> uppercaseNames = names.stream()
    .map(name -> name.toUpperCase(java.util.Locale.ROOT))
    .toList();
```

Biến `sharedResults` bị sửa từ lambda; khi đổi sang `parallelStream()`, `ArrayList` không an toàn cho nhiều luồng ghi đồng thời. Dù dùng collection concurrent, hàm vẫn có tác dụng phụ và khó kiểm thử độc lập. Nên để `map` trả giá trị, còn terminal operation như `toList` hay `collect` kết hợp kết quả.

### 7.2. Dựa vào số lần mapper được gọi

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger calls = new AtomicInteger();
long count = List.of("a", "b", "c").stream()
    .map(value -> {
        calls.incrementAndGet();
        return value.toUpperCase();
    })
    .count();

System.out.println(count); // 3
// Không được khẳng định calls == 3; map có thể được bỏ qua
// nếu count() xác định được kích thước từ nguồn.
```

Stream được phép tối ưu hóa để bỏ qua một số bước trung gian khi điều đó không ảnh hưởng kết quả được bảo đảm. `AtomicInteger` an toàn luồng về mặt cập nhật bộ đếm, nhưng không biến mapper thành hàm thuần. Vì vậy, kiểm thử **giá trị trả về**, không kiểm thử số lần gọi `map` như một quy tắc bắt buộc.

### 7.3. Thay đổi phần tử nguồn

```java
class MutableOrder {
    String region;
    MutableOrder(String region) { this.region = region; }
}

List<MutableOrder> source = new ArrayList<>();
source.add(new MutableOrder(" hn "));

// Tránh: thay đổi object của nguồn ngay trong phép ánh xạ.
List<MutableOrder> changed = source.stream()
    .map(order -> {
        order.region = order.region.strip();
        return order;
    })
    .toList();
```

Việc trả đúng tham chiếu `order` sau khi sửa khiến bước ánh xạ có tác dụng phụ đối với dữ liệu bên ngoài. Dù việc sửa trường không phải lúc nào cũng thay đổi **cấu trúc** của collection, nó vẫn làm mapper không thuần và có thể ảnh hưởng các phép toán khác đang đọc chung object. Hãy tạo đối tượng kết quả mới với dữ liệu đã chuẩn hóa.

### 7.4. Gọi I/O từ mapper

```java
// Ví dụ phản mẫu: mỗi phần tử kích hoạt truy vấn từ xa.
// .map(order -> remotePriceService.lookupPrice(order.id()))
```

Kiểu mapper này có thời gian chạy phụ thuộc mạng, có thể thất bại, gây N+1 request và tạo kết quả thay đổi theo thời điểm gọi. Nếu cần dữ liệu bên ngoài, ưu tiên truy xuất và kiểm soát lỗi ở tầng I/O, xây một snapshot dữ liệu rõ ràng, sau đó ánh xạ thuần từ snapshot sang kết quả. Không phải mọi truy vấn đều có thể gom trước; khi không thể, hãy xem bước I/O là một thao tác riêng có chính sách retry, timeout và quan sát lỗi, thay vì ngụy trang thành biến đổi thuần.

## 8. Thiết kế hợp đồng lỗi và dữ liệu thiếu

Hàm ánh xạ dễ kiểm thử cần nói rõ **đầu vào hợp lệ**, cách xử lý `null`, giá trị ngoài miền và hành vi khi lỗi.

Có ba hướng thường dùng:

| Chính sách | Khi nào dùng | Điều cần kiểm thử |
| --- | --- | --- |
| Fail fast bằng ngoại lệ | Dữ liệu sai khiến kết quả nghiệp vụ không đáng tin | Kiểu ngoại lệ, điều kiện phát sinh, không có kết quả sai âm thầm |
| Trả `Optional<R>` | Việc “không có kết quả” là trạng thái hợp lệ, có chủ đích | Có/không có kết quả, chính sách bỏ bản ghi |
| Trả một kiểu kết quả có thành công/thất bại | Cần gom lỗi có cấu trúc thay vì dừng toàn bộ | Giá trị thành công, mã lỗi, nguyên nhân và thứ tự xử lý |

`toView` ở trên chọn **fail fast** cho số lượng không hợp lệ, giá âm và dữ liệu bắt buộc trống. Đừng chuyển mọi ngoại lệ thành `Optional.empty()` rồi tự động bỏ bản ghi, vì điều đó có thể làm doanh thu được tính sai mà không ai biết. Nếu yêu cầu nghiệp vụ thật sự là “bỏ bản ghi thiếu dữ liệu tùy chọn”, có thể dùng:

```java
import java.util.List;
import java.util.Optional;

static Optional<String> normalizedOptionalRegion(String region) {
    if (region == null || region.isBlank()) {
        return Optional.empty();
    }
    return Optional.of(region.strip().toUpperCase(java.util.Locale.ROOT));
}

List<String> validRegions = List.of(" hn ", " ", "hcm").stream()
    .map(region -> normalizedOptionalRegion(region))
    .flatMap(Optional::stream)
    .toList(); // [HN, HCM]
```

Lúc này chính sách “bỏ vùng trống” được thể hiện tường minh. `Optional::stream` có từ JDK 9. Nếu muốn giữ lại lý do thất bại cho từng dòng, một kiểu kết quả có cấu trúc là lựa chọn rõ hơn `Optional`.

Lưu ý nguồn `List.of(...)` **không nhận phần tử `null`**; ví dụ trên có chuỗi trống, không có `null`. `Stream` có thể được tạo từ những nguồn chứa `null`, nên nếu dữ liệu thực tế có thể thiếu giá trị, kiểm thử khả năng đó tại ranh giới nhập liệu.

## 9. Kiểm thử hàm trước, pipeline sau

Với hàm thuần, unit test cần rất ít thiết lập: tạo đầu vào, gọi trực tiếp hàm, so sánh giá trị đầu ra. Không cần mock database hay HTTP để kiểm tra chuẩn hóa vùng và tính thành tiền.

Ví dụ JUnit 5; giả sử lớp `OrderMapper` ở mục 4 nằm cùng package với lớp test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderMapperTest {

    @Test
    void normalizesRegionAndComputesAmount() {
        var input = new OrderMapper.RawOrder(
            " O-1 ", " hn ", 2, new BigDecimal("100.00")
        );

        var actual = OrderMapper.toView(input);

        assertEquals(
            new OrderMapper.OrderView(
                "O-1", "HN", new BigDecimal("200.00")
            ),
            actual
        );
        assertEquals(" hn ", input.region()); // Không sửa nguồn.
        assertEquals(" O-1 ", input.id());
    }

    @Test
    void sameInputHasSameValue() {
        var input = new OrderMapper.RawOrder(
            "O-2", "hcm", 3, new BigDecimal("20.00")
        );

        assertEquals(OrderMapper.toView(input), OrderMapper.toView(input));
    }

    @Test
    void rejectsInvalidQuantityAndRegion() {
        var invalidQuantity = new OrderMapper.RawOrder(
            "O-3", "HN", 0, new BigDecimal("10.00")
        );
        var blankRegion = new OrderMapper.RawOrder(
            "O-4", " ", 1, new BigDecimal("10.00")
        );

        assertThrows(
            IllegalArgumentException.class,
            () -> OrderMapper.toView(invalidQuantity)
        );
        assertThrows(
            IllegalArgumentException.class,
            () -> OrderMapper.toView(blankRegion)
        );
    }

    @Test
    void worksInsideStreamPipeline() {
        List<OrderMapper.RawOrder> input = List.of(
            new OrderMapper.RawOrder(
                "O-1", " hn ", 2, new BigDecimal("100.00")
            ),
            new OrderMapper.RawOrder(
                "O-2", "hcm", 1, new BigDecimal("20.00")
            )
        );

        List<OrderMapper.OrderView> actual = input.stream()
            .map(OrderMapper::toView)
            .toList();

        assertEquals(
            List.of(
                new OrderMapper.OrderView(
                    "O-1", "HN", new BigDecimal("200.00")
                ),
                new OrderMapper.OrderView(
                    "O-2", "HCM", new BigDecimal("20.00")
                )
            ),
            actual
        );
    }
}
```

### 9.1. Ma trận test có giá trị

| Nhóm kiểm thử | Dữ liệu minh họa | Kỳ vọng |
| --- | --- | --- |
| Happy path | `" hn "`, lượng `2`, giá `100.00` | `HN` và `200.00` |
| Chuẩn hóa | `"hcm"`, `" Hn "` | Kết quả vùng thống nhất |
| Ranh giới miền | Số lượng `0` hoặc âm | Ngoại lệ theo hợp đồng |
| Giá trị không hợp lệ | Giá âm, mã/vùng trống, giá `null` | Lỗi rõ ràng |
| Tính bất biến | Giữ tham chiếu `RawOrder` trước/sau | Không có trường đầu vào bị sửa |
| Tính quyết định | Gọi cùng mapper hai lần | Giá trị kết quả bằng nhau |
| Pipeline | Nhiều đơn, nguồn rỗng, kết hợp `filter`/`collect` | Danh sách hoặc tổng hợp đúng |
| Hợp đồng tiền tệ | Số thập phân, quy tắc làm tròn | Kết quả đúng độ chính xác và scale đã thống nhất |

Khi kiểm thử `BigDecimal`, `equals` còn so sánh **scale**: `new BigDecimal("2.0")` và `new BigDecimal("2.00")` có giá trị số học bằng nhau nhưng không `equals`. Dùng `compareTo` nếu yêu cầu chỉ so sánh trị số; dùng `equals` nếu scale là một phần hợp đồng. Tránh thay đổi chiến lược so sánh tùy tiện giữa các bài test.

### 9.2. Tư duy kiểm thử thuộc tính

Ngoài ví dụ cụ thể, xác định các **bất biến**:

- Đầu vào hợp lệ có `quantity > 0` và `unitPrice >= 0` thì `amount` luôn không âm.
- `toView` không làm thay đổi `RawOrder` đầu vào.
- Cùng đầu vào trả cùng `OrderView`, bất kể pipeline có bao nhiêu phần tử khác.
- Với cùng vùng và giá không âm, tổng của hai dòng bằng tổng các `amount` tương ứng (nếu không áp dụng chính sách làm tròn từng bước làm thay đổi tổng).
- Duyệt theo thứ tự nào cũng không ảnh hưởng phép cộng `BigDecimal`; ngược lại, phép ghép chuỗi có thể phụ thuộc thứ tự.

Các thuộc tính này có thể được kiểm thử bằng nhiều bộ dữ liệu, kể cả công cụ property-based testing khi dự án sử dụng. Đừng viết test xác nhận số lần gọi lambda hoặc thứ tự chạy trong `parallel()` nếu điều đó không thuộc hợp đồng của API.

## 10. Tính thuần giúp gì cho Stream song song và các API nâng cao?

### 10.1. Song song không tự động nhanh hơn

```java
List<OrderMapper.OrderView> views = rows.parallelStream()
    .map(OrderMapper::toView)
    .toList();
```

`OrderMapper.toView` không chứa trạng thái dùng chung nên thích hợp về mặt hành vi khi nhiều luồng gọi đồng thời. Tuy nhiên `parallelStream()` không đảm bảo tăng tốc: nguồn nhỏ, chi phí phân chia dữ liệu, đồng bộ kết quả, thao tác có thứ tự và cấp phát object có thể khiến chương trình chậm hơn. Hãy đo trên khối lượng dữ liệu thực. Với nguồn `List` có encounter order, `toList()` vẫn giữ encounter order trong kết quả, dù thời điểm xử lý từng phần tử khác nhau.

**Hàm thuần chỉ giải quyết một phần bài toán an toàn song song.** Nguồn dữ liệu vẫn không được bị sửa đồng thời trái hợp đồng; collector cũng phải có bộ tích lũy và hàm combiner đúng. Các phép toán `sorted`, `distinct`, `limit`, `findFirst` có thể tăng chi phí khi stream chạy song song hoặc đòi hỏi duy trì thứ tự.

### 10.2. `reduce`, `collect` và phép gộp

`map` biến từng phần tử thành kết quả mới; `reduce` gom kết quả bằng một phép toán phù hợp. Phép gộp của `reduce` phải có tính kết hợp (*associative*), dùng identity thích hợp và tránh thay đổi accumulator dùng chung:

```java
BigDecimal total = rows.stream()
    .map(OrderMapper::toView)
    .map(OrderMapper.OrderView::amount)
    .reduce(BigDecimal.ZERO, BigDecimal::add);
```

`BigDecimal::add` tạo đối tượng kết quả mới và có tính kết hợp về giá trị toán học đối với phép cộng thập phân chính xác. `Collectors.groupingBy(...)` trong ví dụ chính có thể dùng mutable accumulator **nội bộ do collector quản lý**; điều đó không làm cho mapper `toView` có tác dụng phụ. Với **collector tùy chỉnh**, phải đọc kỹ `supplier`, `accumulator`, `combiner`, `finisher`, cũng như `Collector.Characteristics` trước khi dùng với pipeline song song.

### 10.3. `Spliterator`, trạng thái và Stream Gatherers

`Spliterator` điều khiển cách duyệt và chia nguồn; các đặc tính như `ORDERED`, `SIZED`, `IMMUTABLE` hay `CONCURRENT` ảnh hưởng đến khả năng tối ưu và tính an toàn. Bất biến trong mapper không thay thế được hợp đồng của nguồn/spliterator.

**Stream Gatherers** được chuẩn hóa từ **JDK 24** và cung cấp phép biến đổi trung gian có thể **có trạng thái có chủ đích**, như tạo cửa sổ `Gatherers.windowFixed(...)`. Khi dùng `gather`, hãy tách logic ánh xạ phần tử có thể làm thuần khỏi phần quản lý trạng thái cửa sổ hoặc tích lũy của gatherer. Các yêu cầu của `Gatherer` về initializer, integrator, combiner và finisher cần được kiểm tra riêng; mã dùng `gather` sẽ không biên dịch trên JDK 17/21.

## 11. Quy trình thiết kế mapper dễ kiểm thử

Khi nhận một bài toán ánh xạ mới, thực hiện theo trình tự:

1. **Chốt hợp đồng kiểu:** xác định `T` và `R`; đầu ra có phải value object/DTO mới không?
2. **Liệt kê dữ liệu cần dùng:** đầu vào chính, cấu hình, locale, ngày xử lý, tỷ giá, chính sách làm tròn.
3. **Đưa phụ thuộc biến đổi ra ngoài:** đọc I/O, thời gian và dữ liệu có khả năng thay đổi ở ranh giới, truyền giá trị snapshot phù hợp vào phép ánh xạ.
4. **Định nghĩa dữ liệu hợp lệ và lỗi:** `null`, chuỗi trống, phạm vi giá trị, ngoại lệ hay kiểu kết quả tường minh.
5. **Viết hàm nhỏ có tên nghiệp vụ:** chỉ tính toán và tạo kết quả, không sửa nguồn hay cập nhật trạng thái dùng chung.
6. **Kiểm thử trực tiếp:** happy path, biên, lỗi, tính bất biến, tính quyết định, quy tắc số học.
7. **Ghép vào Stream:** sử dụng method reference như `.map(OrderMapper::toView)`; dùng `filter`, `flatMap`, `reduce`, `collect` theo đúng ngữ nghĩa.
8. **Đánh giá hợp đồng pipeline:** có cần encounter order, có terminal operation, có nguồn I/O cần đóng, có lý do chạy song song không?

### Bài tập áp dụng

**Bài 1.** Viết hàm thuần `normalizeCode(String code)`: bỏ khoảng trắng hai đầu, chuyển chữ hoa bằng `Locale.ROOT` và từ chối chuỗi trống. Viết ít nhất ba test: đầu vào thường, đầu vào toàn khoảng trắng và `null`.

**Bài 2.** Từ `List<RawOrder>`, lấy danh sách `OrderView` chỉ cho đơn có `quantity >= 2`. Đặt phép `filter` trước `map` để điều kiện số lượng nằm ở lớp dữ liệu nguồn; giữ `toView` là hàm ánh xạ độc lập. Kiểm thử nguồn rỗng và trường hợp không có đơn nào đạt điều kiện.

**Bài 3.** Thêm `discountRate` vào một hàm mới `discountedAmount(BigDecimal amount, BigDecimal rate)`. Quy định rõ khoảng hợp lệ `0 ≤ rate ≤ 1` và chiến lược làm tròn. Viết test cho `0`, `1`, giá trị giữa khoảng và giá trị ngoài khoảng. Tránh đọc mức giảm giá từ biến cấu hình toàn cục ngay trong hàm.

**Bài 4.** Một đồng nghiệp đề xuất `orders.parallelStream().map(o -> { count++; return toView(o); }).toList()`. Hãy chỉ ra vấn đề về shared state, race condition và vì sao bộ đếm số lần gọi mapper không phải hợp đồng của Stream. Viết lại bằng phép biến đổi thuần, rồi dùng kết quả của terminal operation để tính tổng số phần tử nếu thật sự cần.

Một mapper tốt có thể được kiểm tra như một phép toán `input → output`, không cần tạo stream, mock dịch vụ hay dựa vào thứ tự chạy. Khi kết hợp các mapper thuần, pipeline Java Stream API giữ được ưu điểm xử lý dữ liệu khai báo, dễ mở rộng sang `filter`, `reduce`, `collect` và grouping, đồng thời giảm rủi ro về trạng thái, tài nguyên và xử lý song song.
