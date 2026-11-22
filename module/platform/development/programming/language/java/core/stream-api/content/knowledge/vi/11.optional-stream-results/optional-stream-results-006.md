# Thiết kế kết quả cho nguồn rỗng và phần tử `null`

## 1. Vì sao phải thiết kế kết quả ngay từ đầu?

Trong module **JAVA_STREAM_API**, pipeline khai báo thường đi từ nguồn dữ liệu qua `filter`, `map`, `flatMap` rồi kết thúc bằng `findFirst`, `reduce`, `collect` hoặc một phép thống kê. Các bước trung gian phần lớn được thực thi lười (*lazy*). Vì vậy, kiểu dữ liệu trả về của **terminal operation** phải diễn đạt chính xác tình huống **không có phần tử để xử lý** và tình huống **có phần tử nhưng giá trị của nó bằng `null`**.

Hai câu hỏi này khác nhau:

1. **Nguồn hoặc tập kết quả rỗng:** pipeline không có phần tử nào đến bước kết thúc, ví dụ tất cả đơn hàng bị `filter` loại bỏ.
2. **Phần tử `null`:** pipeline có một vị trí dữ liệu, nhưng giá trị tại vị trí đó là `null`; một số phương thức chấp nhận, một số sẽ ném `NullPointerException`.

Ví dụ đơn giản:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> empty = List.of();
System.out.println(empty.stream().findFirst()); // Optional.empty

Stream<String> containsNull = Stream.<String>of((String) null);
// containsNull.findFirst() sẽ ném NullPointerException.
```

Hai stream đều không có chuỗi có thể sử dụng, nhưng **ngữ nghĩa không giống nhau**. `Optional.empty()` biểu diễn không tìm thấy giá trị; nó không thể chứa một giá trị `null` như một kết quả hiện diện.

Sau bài học, bạn có thể:

- Nhận diện kết quả của từng terminal operation khi stream rỗng.
- Hiểu `Optional<T>`, `OptionalInt`, `OptionalLong` và `OptionalDouble`.
- Phân biệt `Stream.ofNullable`, `Optional.ofNullable` và `filter(Objects::nonNull)`.
- Xác định chính sách **bỏ qua, báo lỗi, thay thế hoặc bảo toàn** phần tử thiếu dữ liệu.
- Thiết kế kiểu trả về phù hợp: `Optional`, collection rỗng, giá trị trung hòa, ngoại lệ hoặc kiểu kết quả có trạng thái tường minh.
- Viết pipeline có thể kiểm thử khi dữ liệu bị thiếu, khi không có kết quả và khi xử lý song song.

## 2. Bốn trạng thái cần phân biệt trong nghiệp vụ

Xét một thao tác tìm email của khách hàng. Các tình huống thường gặp:

| Trạng thái | Ý nghĩa nghiệp vụ | Cách biểu diễn phù hợp |
| --- | --- | --- |
| Không có khách hàng khớp điều kiện | Không tìm thấy bản ghi | `Optional.empty()` hoặc trạng thái `NOT_FOUND` |
| Có khách hàng và email hợp lệ | Tìm thấy giá trị | `Optional.of(email)` hoặc trạng thái `FOUND` |
| Có khách hàng nhưng trường email bằng `null` | Có bản ghi, thiếu thuộc tính | Trạng thái riêng `EMAIL_MISSING`, hoặc lỗi dữ liệu nếu hợp đồng không cho phép |
| Không thể truy cập nguồn dữ liệu | Tác vụ thất bại | Ngoại lệ/kiểu lỗi có nguyên nhân, không tự biến thành “không tìm thấy” |

Nếu dùng duy nhất `Optional<String>` cho email, cả “không có khách hàng” lẫn “khách hàng có email `null`” đều có thể bị biến thành `Optional.empty()`. Việc đó **chỉ đúng khi nghiệp vụ cố ý coi hai trường hợp tương đương**.

Tương tự, việc nguồn rỗng không tự chứng minh rằng **không có dữ liệu trong hệ thống**. Nó chỉ cho biết **stream được đưa vào pipeline hiện tại không có phần tử**. Một truy vấn thất bại, một bộ lọc quá chặt hay một bước chuẩn hóa đã loại mất dữ liệu là những vấn đề khác cần được xử lý ở ranh giới phù hợp.

## 3. Khi stream rỗng, terminal operation trả gì?

Các API khác nhau chọn những hợp đồng kết quả khác nhau:

| Terminal operation | Kết quả với stream rỗng | Ý nghĩa |
| --- | --- | --- |
| `count()` | `0L` | Không có phần tử |
| `findFirst()` / `findAny()` | `Optional.empty()` | Không tìm thấy phần tử |
| `min(comparator)` / `max(comparator)` | `Optional.empty()` | Không có cực trị |
| `reduce(accumulator)` | `Optional.empty()` | Không có kết quả giảm gọn |
| `reduce(identity, accumulator)` | `identity` | Giá trị trung hòa đã khai báo |
| `toList()` | Danh sách rỗng | Không có phần tử để thu thập |
| `collect(Collectors.toList())` | Danh sách rỗng | Bộ tích lũy tạo kết quả rỗng |
| `collect(Collectors.groupingBy(...))` | Map rỗng | Không có nhóm nào được tạo |
| `collect(Collectors.counting())` | `0L` | Collector đếm không phần tử |
| `anyMatch(predicate)` | `false` | Không tồn tại phần tử thỏa |
| `allMatch(predicate)` | `true` | Không tồn tại phần tử phản ví dụ |
| `noneMatch(predicate)` | `true` | Không tồn tại phần tử thỏa |
| `IntStream.sum()` | `0` | Tổng với giá trị trung hòa 0 |
| `IntStream.average()` | `OptionalDouble.empty()` | Không có trung bình |
| `IntStream.min()` / `max()` | `OptionalInt.empty()` | Không có cực trị |
| `IntStream.summaryStatistics()` | Đối tượng thống kê có `count == 0` | Phải xem count trước khi dùng các cực trị |

Ba phép `anyMatch`, `allMatch` và `noneMatch` trên nguồn rỗng là ví dụ của **chân trị rỗng** (*vacuous truth*): không có phần tử nào làm sai mệnh đề “tất cả đều thỏa”, nên `allMatch` trả `true`. Đừng suy rằng `true` đồng nghĩa với “đã kiểm tra ít nhất một phần tử”.

Ví dụ chạy trên **JDK 17 trở lên**:

```java
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

List<Integer> values = List.of();

System.out.println(values.stream().count());           // 0
System.out.println(values.stream().findFirst());       // Optional.empty
System.out.println(values.stream().reduce(Integer::sum)); // Optional.empty
System.out.println(values.stream().reduce(0, Integer::sum)); // 0
System.out.println(values.stream().toList());          // []
System.out.println(values.stream().allMatch(x -> x > 0)); // true
System.out.println(values.stream().anyMatch(x -> x > 0)); // false

Optional<Integer> first = Stream.<Integer>empty().findFirst();
System.out.println(first.isEmpty()); // true
```

**Điểm cần chọn rõ:** trả `0` khi tổng của nguồn rỗng là **đúng theo quy ước cộng**. Trả `0` cho “giá trị giao dịch gần nhất” lại có thể gây hiểu lầm, vì `0` là một số hợp lệ chứ không phải một giao dịch tồn tại. Với bài toán “tìm một phần tử”, `Optional` thường diễn đạt chính xác hơn giá trị mặc định.

## 4. `Optional<T>`: biểu diễn có hoặc không có kết quả

`Optional<T>` là container có thể chứa **một giá trị khác `null`**, hoặc rỗng. Những phương thức thường dùng:

| Phương thức | Mục đích |
| --- | --- |
| `Optional.empty()` | Tạo Optional không có giá trị |
| `Optional.of(value)` | Tạo Optional có giá trị; `value == null` gây `NullPointerException` |
| `Optional.ofNullable(value)` | Có giá trị nếu khác `null`, rỗng nếu bằng `null` |
| `isPresent()` / `isEmpty()` | Kiểm tra sự hiện diện |
| `ifPresent(consumer)` | Thực hiện hành động nếu có giá trị |
| `ifPresentOrElse(action, emptyAction)` | Rẽ nhánh theo có/không có giá trị, từ JDK 9 |
| `map(function)` | Chuyển đổi giá trị hiện diện; mapper trả `null` dẫn đến Optional rỗng |
| `flatMap(function)` | Chuyển đổi bằng hàm trả `Optional<U>`, tránh `Optional<Optional<U>>` |
| `filter(predicate)` | Chỉ giữ giá trị nếu điều kiện thỏa |
| `orElse(defaultValue)` | Dùng giá trị dự phòng nếu rỗng |
| `orElseGet(supplier)` | Tính giá trị dự phòng **chỉ khi rỗng** |
| `orElseThrow()` / `orElseThrow(supplier)` | Ném ngoại lệ khi rỗng |
| `stream()` | Chuyển thành stream có 0 hoặc 1 phần tử, từ JDK 9 |

### 4.1. Thiết kế một phương thức tìm kiếm

```java
import java.util.List;
import java.util.Optional;

record User(String id, String displayName) {}

static Optional<User> findUser(List<User> users, String id) {
    return users.stream()
        .filter(user -> user.id().equals(id))
        .findFirst();
}

// Trong phương thức gọi:
// Optional<User> result = findUser(users, "U-1");
// result.ifPresent(user -> System.out.println(user.displayName()));
```

Đoạn này giả định danh sách chỉ chứa đối tượng `User` hợp lệ và `id` của mỗi user không bằng `null`. Nếu nguồn có thể chứa phần tử `null`, cần xác định cách xử lý **trước khi** truy cập `user.id()`.

Không cần bắt buộc gọi `optional.get()` và tự xử lý `NoSuchElementException`. Hãy ưu tiên `ifPresent`, `map`, `orElseThrow`, `orElseGet` hoặc phối hợp `Optional.stream` theo tình huống.

### 4.2. `orElse` và `orElseGet` khác nhau ở thời điểm tính

```java
import java.util.Optional;

static String expensiveFallback() {
    // Trong ứng dụng thật có thể truy xuất I/O.
    return "DỰ PHÒNG";
}

Optional<String> found = Optional.of("Kết quả");

String a = found.orElse(expensiveFallback());
String b = found.orElseGet(() -> expensiveFallback());

System.out.println(a); // Kết quả
System.out.println(b); // Kết quả
```

`expensiveFallback()` trong lời gọi `orElse(...)` được đánh giá **trước khi** `orElse` được gọi, dù Optional đang có giá trị. Supplier của `orElseGet(...)` chỉ được gọi khi Optional rỗng. Nếu giá trị dự phòng là hằng như `"Không tìm thấy"`, `orElse` đơn giản là đủ.

### 4.3. `map` trên Optional có thể che mất `null` từ mapper

```java
Optional<String> maybeName = Optional.of("An");

Optional<String> hiddenMissingValue = maybeName
    .map(name -> (String) null);

System.out.println(hiddenMissingValue.isEmpty()); // true
```

Khi mapper trả `null`, `Optional.map` trả `Optional.empty()`. Nếu `null` biểu thị **dữ liệu lỗi**, hãy xác thực hoặc ném ngoại lệ rõ ràng trước khi đánh mất lý do vắng mặt. `Optional.flatMap` khác ở chỗ mapper phải trả một `Optional` **không bằng `null`**; trả tham chiếu Optional bằng `null` sẽ gây `NullPointerException`.

## 5. `null` trong nguồn: ba thao tác trông giống nhưng không tương đương

### 5.1. `Stream.ofNullable(value)` nhận một tham chiếu có thể bằng `null`

`Stream.ofNullable(T)` được bổ sung trong **JDK 9**:

```java
import java.util.List;
import java.util.stream.Stream;

String provided = null;

List<String> a = Stream.ofNullable(provided).toList();
System.out.println(a); // []

List<String> b = Stream.ofNullable("Java").toList();
System.out.println(b); // [Java]
```

`Stream.ofNullable(value)` tạo stream gồm **0 phần tử nếu `value == null`**, hoặc **1 phần tử nếu khác `null`**. Đây là chính sách “đầu vào `null` tương đương không có phần tử”.

Ngược lại, `Stream.of((String) null)` có thể tạo stream chứa **một phần tử `null`**:

```java
Stream<String> singleNull = Stream.<String>of((String) null);
System.out.println(singleNull.count()); // 1
```

Chú thích kiểu tường minh ở ví dụ giúp tránh nhầm lẫn với overload nhận mảng varargs của `Stream.of`. `count()` không cần truy cập nội dung nên có thể trả `1`; việc gọi một terminal operation khác như `findFirst()` trên stream đó có hợp đồng khác.

### 5.2. `filter(Objects::nonNull)` lọc các phần tử `null` *bên trong* stream

`Stream.ofNullable` chỉ kiểm tra **một tham chiếu được truyền vào nó**. Nó **không** tự đi vào một collection để bỏ các phần tử `null`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

List<String> raw = Arrays.asList("An", null, "Bình", null);

List<String> cleaned = raw.stream()
    .filter(Objects::nonNull)
    .toList();

System.out.println(cleaned); // [An, Bình]
```

Nếu đã có một `Stream<T>` chứa nhiều phần tử, `filter(Objects::nonNull)` mới là phép lọc từng phần tử. `List.of("An", null)` ném `NullPointerException` ngay khi **tạo list**, trong khi `Arrays.asList(...)` và `ArrayList` cho phép chứa `null`.

### 5.3. Nguồn collection có thể bằng `null`

Phân biệt **collection bằng `null`** với **collection có phần tử `null`**:

```java
import java.util.List;
import java.util.stream.Stream;

static Stream<String> itemsOrEmpty(List<String> items) {
    return items == null
        ? Stream.empty()
        : items.stream();
}
```

Đây là một **quy ước API có chủ đích**. Nếu danh sách `null` là lỗi lập trình hoặc lỗi dữ liệu, thay vì tự chuyển thành stream rỗng, hãy dùng `Objects.requireNonNull(items, "items")` và sửa dữ liệu tại nguồn.

## 6. Những terminal operation nào gặp rủi ro với phần tử `null`?

Một số terminal operation trả `Optional` sử dụng `null` như trạng thái không hợp lệ của **phần tử được lựa chọn**.

### 6.1. `findFirst` và `findAny`

Theo hợp đồng `Stream.findFirst()` và `Stream.findAny()`, nếu **phần tử được chọn** là `null`, phương thức sẽ ném `NullPointerException`:

```java
import java.util.Arrays;
import java.util.List;

List<String> data = Arrays.asList(null, "Java", "Stream");

// data.stream().findFirst(); // NullPointerException: phần tử đầu là null.

String firstNonNull = data.stream()
    .filter(java.util.Objects::nonNull)
    .findFirst()
    .orElse("Không có");

System.out.println(firstNonNull); // Java
```

Với stream không có encounter order, `findAny()` không đảm bảo chọn phần tử nào; nếu chọn `null`, nó cũng có thể ném ngoại lệ. Không nên dựa vào việc stream “có ít nhất một phần tử khác `null`” để kết luận `findAny` luôn an toàn.

### 6.2. `min`, `max` và `reduce`

Các phép chọn cực trị thường dùng comparator; comparator tự nhiên như `Comparator.naturalOrder()` không xử lý `null`. Đặc biệt, các phép giảm gọn trả `Optional` cũng không thể chứa kết quả bằng `null`; theo hợp đồng `reduce(BinaryOperator)`, kết quả giảm gọn bằng `null` gây `NullPointerException`.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

List<Integer> values = Arrays.asList(null, 4, 9, 2);

int max = values.stream()
    .filter(Objects::nonNull)
    .max(Integer::compareTo)
    .orElseThrow();

System.out.println(max); // 9
```

`Comparator.nullsFirst(...)` và `nullsLast(...)` có thể định nghĩa thứ tự cho `null` ở **bước so sánh**, nhưng vẫn cần cân nhắc kết quả cuối: `Optional` của `min`/`max` không thể biểu diễn một cực trị `null` thành giá trị hiện diện. Khi `null` có ý nghĩa riêng, lựa chọn comparator đơn thuần chưa đủ để thiết kế hợp đồng trả về.

### 6.3. `map`, `sorted`, `toList` và collector

| Bước | Gặp `null` có thể xảy ra điều gì? |
| --- | --- |
| `map(x -> x.toString())` | Ném `NullPointerException` khi dereference `x` |
| `map(x -> x == null ? "?" : x.toString())` | Thay thế theo quy tắc tường minh |
| `filter(Objects::nonNull)` | Bỏ mọi phần tử `null` đi qua bước lọc |
| `sorted()` theo thứ tự tự nhiên | Comparator tự nhiên thường không chấp nhận `null` |
| `Stream.toList()` (JDK 16+) | Có thể tạo danh sách chứa phần tử `null`; danh sách trả về không thể sửa đổi |
| `Collectors.toUnmodifiableList()` (JDK 10+) | Từ chối giá trị `null` bằng `NullPointerException` |
| `Collectors.toList()` | Không cam kết loại triển khai hoặc khả năng sửa đổi; không nên dùng làm “hợp đồng chấp nhận null” |
| `Collectors.groupingBy(classifier)` | Cần tránh khóa nhóm `null`; triển khai mặc định từ chối kết quả classifier bằng `null` |

Thử một trường hợp khác biệt quan trọng:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> nullable = Arrays.asList("A", null, "B");

List<String> preserved = nullable.stream().toList();
System.out.println(preserved); // [A, null, B]

// nullable.stream().collect(Collectors.toUnmodifiableList());
// NullPointerException do collector không cho phép phần tử null.
```

Việc một list **có thể chứa `null`** không có nghĩa các phép thao tác phía sau đều chấp nhận `null`. Khi thiết kế kết quả, hãy công bố rõ “có chấp nhận `null` không” và tránh phụ thuộc ngẫu nhiên vào implementation của collection.

## 7. Chọn chiến lược nghiệp vụ cho dữ liệu thiếu

Không có một chính sách phù hợp mọi tình huống. Hãy chọn trước khi viết lambda:

| Chính sách | Khi nào hợp lý? | Cách thể hiện |
| --- | --- | --- |
| **Từ chối** dữ liệu không hợp lệ | Thiếu dữ liệu khiến báo cáo hoặc giao dịch không đáng tin | Validate và ném ngoại lệ/ghi nhận lỗi có cấu trúc |
| **Bỏ qua** bản ghi `null` | Nguồn cho phép ô trống và bỏ qua được theo đặc tả | `filter(Objects::nonNull)` |
| **Thay thế** bằng giá trị rõ nghĩa | Có quy ước mặc định được nghiệp vụ chấp nhận | `map(x -> x == null ? fallback : x)` |
| **Giữ nguyên** giá trị `null` | API đích chủ động biểu diễn trường thiếu dữ liệu | Collection/DTO cho phép `null` cùng tài liệu rõ ràng |
| **Phân biệt ba trạng thái** | Cần biết “không thấy bản ghi” và “bản ghi thiếu thuộc tính” | Kiểu kết quả có trạng thái riêng |

Ví dụ grouping theo kênh bán hàng, với quy ước hợp lệ rằng kênh `null` được xếp vào `"UNKNOWN"`:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Sale(String channel, long amountVnd) {}

List<Sale> sales = List.of(
    new Sale("WEB", 1000),
    new Sale(null, 2000),
    new Sale("WEB", 3000)
);

Map<String, Long> totals = sales.stream()
    .collect(Collectors.groupingBy(
        sale -> sale.channel() == null ? "UNKNOWN" : sale.channel(),
        Collectors.summingLong(Sale::amountVnd)
    ));

System.out.println(totals.get("WEB"));     // 4000
System.out.println(totals.get("UNKNOWN")); // 2000
```

Nếu `"UNKNOWN"` có thể trùng khóa nghiệp vụ thật, dùng một kiểu khóa tường minh (ví dụ enum hoặc record) thay cho chuỗi mặc định. Đừng thay `null` bằng `0` hoặc chuỗi rỗng nếu giá trị dự phòng cũng là dữ liệu hợp lệ và sẽ làm sai thống kê.

## 8. Ví dụ hoàn chỉnh: báo cáo từ nguồn có phần tử `null`

Giả sử hệ thống bán hàng có một danh sách giao dịch theo thứ tự ghi nhận. Quy tắc của bài toán:

- Collection nguồn **phải khác `null`**; đầu vào `null` là lỗi API.
- Danh sách có thể có một số ô `null` do bước nhập liệu; **bỏ qua** những ô đó theo quy ước báo cáo.
- Chỉ thống kê giao dịch đã duyệt (`approved == true`).
- Các bản ghi giao dịch hiện diện có mã, kênh, đơn giá, số lượng hợp lệ; validate ngay tại lúc tạo.
- Không có giao dịch hợp lệ thì danh sách rỗng, tổng bằng `0` và giao dịch đầu tiên vắng mặt bằng `Optional.empty()`.

Mã đầy đủ chạy với **JDK 17 trở lên**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalLong;
import java.util.stream.Stream;

public class NullableSalesReport {

    public record Sale(
        String id,
        String channel,
        int quantity,
        long unitPriceVnd,
        boolean approved
    ) {
        public Sale {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(channel, "channel");
            if (id.isBlank() || channel.isBlank()) {
                throw new IllegalArgumentException("id/channel không được trống");
            }
            if (quantity <= 0 || unitPriceVnd < 0) {
                throw new IllegalArgumentException("quantity/price không hợp lệ");
            }
        }
    }

    public record SaleView(String id, String channel, long amountVnd) {}

    private static Stream<Sale> approvedSales(List<Sale> source) {
        Objects.requireNonNull(source, "source");
        return source.stream()
            .filter(Objects::nonNull)
            .filter(Sale::approved);
    }

    private static SaleView toView(Sale sale) {
        long amount = Math.multiplyExact(
            (long) sale.quantity(), sale.unitPriceVnd()
        );
        return new SaleView(sale.id(), sale.channel(), amount);
    }

    public static List<SaleView> allApproved(List<Sale> source) {
        return approvedSales(source)
            .map(NullableSalesReport::toView)
            .toList();
    }

    public static Optional<SaleView> firstApproved(List<Sale> source) {
        return approvedSales(source)
            .map(NullableSalesReport::toView)
            .findFirst();
    }

    public static OptionalLong largestApprovedAmount(List<Sale> source) {
        return approvedSales(source)
            .mapToLong(sale -> Math.multiplyExact(
                (long) sale.quantity(), sale.unitPriceVnd()
            ))
            .max();
    }

    public static long totalApprovedAmount(List<Sale> source) {
        return approvedSales(source)
            .mapToLong(sale -> Math.multiplyExact(
                (long) sale.quantity(), sale.unitPriceVnd()
            ))
            .reduce(0L, Math::addExact);
    }

    public static void main(String[] args) {
        List<Sale> source = Arrays.asList(
            new Sale("S1", "WEB", 2, 10_000L, true),
            null,
            new Sale("S2", "STORE", 1, 8_000L, false),
            new Sale("S3", "WEB", 1, 5_000L, true)
        );

        System.out.println(allApproved(source));
        // [SaleView[id=S1, channel=WEB, amountVnd=20000],
        //  SaleView[id=S3, channel=WEB, amountVnd=5000]]

        System.out.println(firstApproved(source));
        // Optional[SaleView[id=S1, channel=WEB, amountVnd=20000]]

        System.out.println(largestApprovedAmount(source));
        // OptionalLong[20000]

        System.out.println(totalApprovedAmount(source)); // 25000

        List<Sale> empty = List.of();
        System.out.println(allApproved(empty)); // []
        System.out.println(firstApproved(empty)); // Optional.empty
        System.out.println(largestApprovedAmount(empty)); // OptionalLong.empty
        System.out.println(totalApprovedAmount(empty)); // 0
    }
}
```

### 8.1. Vì sao ví dụ có nhiều kiểu kết quả?

| Phương thức | Kiểu trả về | Khi không có giao dịch duyệt |
| --- | --- | --- |
| `allApproved` | `List<SaleView>` | `[]`: tập hợp không có dòng |
| `firstApproved` | `Optional<SaleView>` | `Optional.empty()`: không có phần tử đầu |
| `largestApprovedAmount` | `OptionalLong` | `OptionalLong.empty()`: không có cực đại |
| `totalApprovedAmount` | `long` | `0L`: giá trị trung hòa của phép cộng |

Đây là những hợp đồng có ý nghĩa khác nhau; không nên buộc tất cả về cùng một kiểu hoặc một “mã lỗi” như `-1`. Nếu nghiệp vụ cần phân biệt **không có giao dịch** với **đã duyệt giao dịch có tổng bằng 0**, trả thêm `count` hoặc một kiểu kết quả tổng hợp chứa trạng thái đó.

### 8.2. Lưu ý kỹ thuật

- `Arrays.asList` ở `main` có thể chứa phần tử `null`, trong khi `List.of(...)` không cho phép.
- `filter(Objects::nonNull)` phải đứng **trước** `filter(Sale::approved)` để không dereference phần tử `null`.
- `firstApproved` giữ encounter order của `List`, còn `findAny` không cam kết chọn dòng đầu tiên nếu cần xử lý song song.
- `Math.multiplyExact` phát hiện tràn số khi nhân, và `Math.addExact` phát hiện tràn khi cộng. Không nên dùng `LongStream.sum()` nếu hợp đồng yêu cầu ném lỗi khi tổng vượt giới hạn `long`.
- Các phương thức mở stream mới từ `source` mỗi lần; một stream đã tiêu thụ không được dùng lại.
- `toList()` trả list không thể sửa đổi; mỗi `SaleView` là record gồm các trường bất biến trong ví dụ.

## 9. Kiểu kết quả tường minh khi phải giữ “có bản ghi nhưng thiếu thuộc tính”

Không phải mọi nghiệp vụ đều được phép bỏ các dòng thiếu dữ liệu. Nếu cần phân biệt **không tìm thấy** với **tìm thấy nhưng email chưa được cung cấp**, một kiểu kết quả tường minh rõ ràng hơn `Optional<String>`.

Ví dụ độc lập chạy với **JDK 17+**:

```java
import java.util.List;
import java.util.Objects;

public class EmailLookupDemo {

    record Customer(String id, String email) {}

    enum LookupStatus { NOT_FOUND, EMAIL_MISSING, FOUND }

    record EmailLookup(LookupStatus status, String email) {}

    static EmailLookup lookupEmail(List<Customer> customers, String id) {
        Objects.requireNonNull(customers, "customers");
        Objects.requireNonNull(id, "id");

        return customers.stream()
            .filter(Objects::nonNull)
            .filter(customer -> id.equals(customer.id()))
            .findFirst()
            .map(customer ->
                customer.email() == null
                    ? new EmailLookup(LookupStatus.EMAIL_MISSING, null)
                    : new EmailLookup(LookupStatus.FOUND, customer.email())
            )
            .orElseGet(() ->
                new EmailLookup(LookupStatus.NOT_FOUND, null)
            );
    }

    public static void main(String[] args) {
        List<Customer> customers = List.of(
            new Customer("U1", "u1@example.test"),
            new Customer("U2", null)
        );

        System.out.println(lookupEmail(customers, "U1").status()); // FOUND
        System.out.println(lookupEmail(customers, "U2").status()); // EMAIL_MISSING
        System.out.println(lookupEmail(customers, "U3").status()); // NOT_FOUND
    }
}
```

Ở đây `findFirst()` nhận một **đối tượng `Customer` khác `null`** vì đã lọc trước. Chỉ sau khi tìm được khách hàng, `map` mới xem trường `email` có bằng `null` không. Nhờ đó trạng thái **có bản ghi nhưng thiếu email** không bị nhập nhằng với **không tìm thấy bản ghi**.

Đây là kiểu kết quả minh họa tối giản. Trong hệ thống thực, nên bổ sung ràng buộc giữa `status` và `email` (ví dụ trạng thái `FOUND` phải có email khác `null`), hoặc thiết kế sealed type riêng cho từng nhánh để biểu diễn những trạng thái bất hợp lệ thành không thể khởi tạo.

## 10. `OptionalInt`, `OptionalLong`, `OptionalDouble` và thống kê số

Các primitive stream có những kết quả tùy chọn chuyên biệt để tránh boxing:

| Nguồn | Phép toán | Kết quả |
| --- | --- | --- |
| `IntStream` | `min()`, `max()`, `findFirst()` | `OptionalInt` |
| `LongStream` | `min()`, `max()`, `findAny()` | `OptionalLong` |
| `DoubleStream` | `min()`, `max()`, `average()` | `OptionalDouble` |
| `IntStream` | `average()` | `OptionalDouble` |
| `LongStream` | `average()` | `OptionalDouble` |

Ví dụ:

```java
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalInt smallest = IntStream.empty().min();
OptionalDouble average = IntStream.empty().average();

System.out.println(smallest.isEmpty()); // true
System.out.println(average.isEmpty());  // true

int fallbackForDisplay = smallest.orElse(0);
System.out.println(fallbackForDisplay); // 0
```

Trong ví dụ, `orElse(0)` chỉ là quyết định **hiển thị số mặc định**, không chứng minh cực tiểu bằng 0. Nếu đang tính giá trị nghiệp vụ cần chính xác, tốt hơn nên xử lý nhánh rỗng tường minh.

### 10.1. Trung bình của tập rỗng không phải 0

`IntStream.average()` trả `OptionalDouble.empty()` với nguồn rỗng, bởi không có mẫu để chia. Nếu chuyển thành `0.0` bằng `orElse(0)`, người đọc có thể nhầm rằng hệ thống đo được trung bình bằng 0:

```java
OptionalDouble mean = IntStream.empty().average();

String display = mean.isPresent()
    ? Double.toString(mean.getAsDouble())
    : "Chưa có dữ liệu";

System.out.println(display); // Chưa có dữ liệu
```

### 10.2. Đọc `summaryStatistics()` đúng cách

`IntSummaryStatistics` có `getCount()`, `getSum()`, `getMin()`, `getMax()` và `getAverage()`. Với nguồn rỗng, `count == 0` và `average == 0.0` theo hợp đồng của lớp thống kê; `min` và `max` dùng **giá trị khởi tạo đặc biệt** lần lượt là `Integer.MAX_VALUE` và `Integer.MIN_VALUE`.

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics stats = IntStream.empty().summaryStatistics();

System.out.println(stats.getCount()); // 0
System.out.println(stats.getAverage()); // 0.0

if (stats.getCount() == 0) {
    System.out.println("Không có số liệu để xác định min/max");
}
```

**Không** sử dụng `getMin()`/`getMax()` của tập rỗng như thể đó là giá trị đo thực tế. `summaryStatistics()` đặc biệt hữu ích nếu muốn đọc nhiều chỉ số trong **một lần duyệt**; cần định nghĩa rõ cách trình bày các chỉ số khi `count == 0`.

## 11. Kết hợp `Optional.stream()` và `flatMap` khi có nhiều kết quả tùy chọn

`Optional.stream()` (JDK 9+) chuyển Optional thành stream:

- `Optional.of(x).stream()` phát ra đúng một phần tử `x`.
- `Optional.empty().stream()` không phát ra phần tử nào.

Điều này hữu ích khi pipeline tạo **một Optional cho mỗi bản ghi**:

```java
import java.util.List;
import java.util.Optional;

record RawProduct(String id, String name) {}

static Optional<String> validName(RawProduct product) {
    if (product == null || product.name() == null
            || product.name().isBlank()) {
        return Optional.empty();
    }
    return Optional.of(product.name().strip());
}

List<RawProduct> source = java.util.Arrays.asList(
    new RawProduct("P1", "Bút"),
    new RawProduct("P2", null),
    null,
    new RawProduct("P3", "Sổ")
);

List<String> names = source.stream()
    .map(product -> validName(product))
    .flatMap(Optional::stream)
    .toList();

System.out.println(names); // [Bút, Sổ]
```

Mỗi sản phẩm tạo một `Optional<String>`; `flatMap(Optional::stream)` chỉ giữ các giá trị hiện diện. Mẫu này hợp lý nếu **“không có tên hợp lệ thì bỏ khỏi kết quả”** là quy tắc nghiệp vụ đã được chấp nhận. Nếu một bản ghi thiếu tên phải được báo lỗi, thay `validName` bằng bước xác thực và giữ lại thông tin lỗi.

Với `OptionalInt`/`OptionalLong`/`OptionalDouble`, `stream()` cũng có từ JDK 9 và trả về primitive stream tương ứng. Có thể kết hợp chúng khi cần gom nhiều kết quả số tùy chọn mà không boxing.

## 12. Tính lười, short-circuit và stream song song

Khi thiết kế xử lý `null`, cần lưu ý pipeline Stream API chỉ thực hiện những lời gọi thực sự cần thiết để tạo kết quả terminal:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

List<String> words = Arrays.asList("Java", null, "Stream");

String first = words.stream()
    .filter(Objects::nonNull)
    .findFirst()
    .orElse("Không có");

System.out.println(first); // Java
```

`findFirst()` là terminal operation có thể **short-circuit**, nên pipeline không cần xử lý tất cả phần tử phía sau. Không được dựa vào số lần `filter`/`map`/`peek` được gọi để ghi log nghiệp vụ bắt buộc hoặc tăng bộ đếm dùng chung.

Với `parallelStream()`:

- `findFirst()` giữ encounter order khi nguồn có thứ tự, nhưng có thể cần thêm phối hợp giữa các luồng.
- `findAny()` có thể chọn một phần tử bất kỳ và kết quả có thể khác giữa các lần chạy.
- Nếu nguồn có phần tử `null`, phải xử lý chúng **trước các thao tác không chấp nhận `null`**; chạy song song không làm dữ liệu null tự trở nên hợp lệ.
- Predicate, mapper và accumulator phải đáp ứng hợp đồng **non-interference** và **statelessness** theo yêu cầu của Stream; không sửa collection nguồn hay bộ đếm không được đồng bộ.
- Chế độ song song không mặc nhiên nhanh hơn; hãy đo trên dữ liệu và chi phí thao tác thực tế.

Ví dụ an toàn về mặt ngữ nghĩa:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

List<String> data = Arrays.asList("A", null, "B", "C");

List<String> result = data.parallelStream()
    .filter(Objects::nonNull)
    .map(String::toLowerCase)
    .toList();

System.out.println(result); // [a, b, c]
```

Với nguồn `List` có encounter order, `toList()` giữ thứ tự phần tử theo nguồn dù các phép biến đổi có thể chạy ở những thời điểm khác nhau. Việc lọc `null` ở đầu giúp `String::toLowerCase` không gặp một tham chiếu null.

## 13. Nguồn I/O rỗng, lỗi I/O và vòng đời tài nguyên

Không có dòng dữ liệu và **không đọc được tệp** là hai trạng thái khác nhau:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

static Optional<String> firstNonBlankLine(Path path) throws IOException {
    try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
            .map(String::strip)
            .filter(line -> !line.isEmpty())
            .findFirst();
    }
}
```

Với tệp hợp lệ nhưng rỗng (hoặc chỉ có các dòng trắng), hàm trả `Optional.empty()`. Nếu mở/đọc tệp gặp lỗi I/O, hàm **không** tự trả Optional rỗng mà cho lỗi được truyền tiếp theo cơ chế ngoại lệ của API. `Files.lines` tạo một stream giữ tài nguyên I/O; `try-with-resources` bảo đảm đóng tài nguyên kể cả khi `findFirst()` dừng sớm.

Với ứng dụng dùng `flatMap` để ghép nhiều stream file, cần đọc hợp đồng đóng **stream con** của `flatMap` và đóng stream nguồn có tài nguyên bằng `try-with-resources`. Đừng sử dụng `Optional.empty()` như một cơ chế thay thế cho ngoại lệ truy xuất dữ liệu.

## 14. Kiểm thử các trường hợp rỗng và `null`

Các bài test JUnit 5 sau sử dụng lớp `NullableSalesReport` ở mục 8. Nếu tạo riêng file test, đặt lớp trong package có thể truy cập lớp báo cáo và thêm dependency JUnit Jupiter theo dự án.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class NullableSalesReportTest {

    @Test
    void emptySourceHasExplicitEmptyResults() {
        List<NullableSalesReport.Sale> empty = List.of();

        assertEquals(List.of(), NullableSalesReport.allApproved(empty));
        assertEquals(Optional.empty(),
            NullableSalesReport.firstApproved(empty));
        assertTrue(NullableSalesReport.largestApprovedAmount(empty).isEmpty());
        assertEquals(0L, NullableSalesReport.totalApprovedAmount(empty));
    }

    @Test
    void onlyNullRowsAreIgnoredByPolicy() {
        List<NullableSalesReport.Sale> source =
            Arrays.asList(null, null);

        assertEquals(List.of(), NullableSalesReport.allApproved(source));
        assertEquals(Optional.empty(),
            NullableSalesReport.firstApproved(source));
    }

    @Test
    void firstValidResultAfterNullIsPresent() {
        List<NullableSalesReport.Sale> source = Arrays.asList(
            null,
            new NullableSalesReport.Sale(
                "S1", "WEB", 2, 10_000L, true
            )
        );

        assertEquals(
            Optional.of(new NullableSalesReport.SaleView(
                "S1", "WEB", 20_000L
            )),
            NullableSalesReport.firstApproved(source)
        );
    }

    @Test
    void noApprovedRowsMeansNoMatchingResult() {
        List<NullableSalesReport.Sale> source = List.of(
            new NullableSalesReport.Sale(
                "S2", "STORE", 1, 8_000L, false
            )
        );

        assertEquals(List.of(), NullableSalesReport.allApproved(source));
        assertTrue(NullableSalesReport.firstApproved(source).isEmpty());
    }

    @Test
    void nullCollectionIsApiError() {
        assertThrows(
            NullPointerException.class,
            () -> NullableSalesReport.allApproved(null)
        );
    }

    @Test
    void invalidRecordFailsFast() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new NullableSalesReport.Sale(
                "S3", "WEB", 0, 100L, true
            )
        );
    }

    @Test
    void overflowIsNotSilentlyAccepted() {
        List<NullableSalesReport.Sale> source = List.of(
            new NullableSalesReport.Sale(
                "S4", "WEB", 2, Long.MAX_VALUE, true
            )
        );

        assertThrows(
            ArithmeticException.class,
            () -> NullableSalesReport.totalApprovedAmount(source)
        );
    }
}
```

### 14.1. Ma trận kiểm thử nên bổ sung

| Đầu vào | Cần xác minh |
| --- | --- |
| Collection rỗng | Mỗi terminal operation có kết quả rỗng/identity đúng hợp đồng |
| Collection chỉ chứa phần tử `null` | Chính sách lọc/báo lỗi được áp dụng nhất quán |
| `null` ở đầu, giữa và cuối | Mapper/terminal không vô tình dereference `null` |
| Có phần tử nhưng mọi phần tử bị `filter` loại | Kết quả giống nguồn rỗng theo hợp đồng tìm kiếm |
| Giá trị hợp lệ bằng `0` | Không bị nhầm thành “không có giá trị” |
| Mapper trả `null` | Phân biệt kết quả `Optional.map` với stream chứa phần tử `null` |
| Nguồn sắp thứ tự khác nhau | `findFirst` tuân theo encounter order, không suy luận thứ tự cho `findAny` |
| Truy cập nguồn thất bại | Lỗi được báo, không tự chuyển thành `Optional.empty()` |
| Phép tính số tràn | Chính sách lỗi hoặc kiểu số lớn hơn được kiểm tra |

Không viết unit test đòi hỏi một mapper được gọi **đúng số lần bằng độ dài nguồn**: tính lười, short-circuit và các tối ưu hóa của Stream có thể làm giả định đó sai.

## 15. Bài tập thực hành

**Bài 1 — Nguồn rỗng và ba kiểu kết quả.** Cho `List<Integer> values = List.of()`. Viết ba pipeline lần lượt dùng `findFirst`, `reduce(Integer::sum)` và `reduce(0, Integer::sum)`. Giải thích vì sao hai kết quả đầu là `Optional.empty()` còn kết quả sau là `0`.

**Bài 2 — Phần tử `null` và `findFirst`.** Tạo `List<String>` với ba phần tử `null`, `"A"` và `"B"` bằng `Arrays.asList`. Dự đoán kết quả `findFirst` trên stream nguyên bản và khi có `filter(Objects::nonNull)` trước đó. Kiểm thử ngoại lệ ở trường hợp đầu.

**Bài 3 — Thiết kế Optional.** Viết `Optional<String> findCode(List<String> codes, String prefix)`. Quy định xem phần tử `null` là dữ liệu cần bỏ hay lỗi; viết kiểm thử cho nguồn rỗng, mã phù hợp và không có mã phù hợp. Không dùng `null` làm giá trị trả về của chính phương thức.

**Bài 4 — Trung bình và số 0 hợp lệ.** Cho `IntStream.empty()` và `IntStream.of(0)`. Lấy `average()` của từng stream. Chứng minh vì sao `orElse(0.0)` có thể làm mất khả năng phân biệt “không có mẫu” với “trung bình thực sự bằng 0”.

**Bài 5 — Ba trạng thái email.** Viết lại ví dụ `EmailLookupDemo` sao cho kiểu kết quả không cho phép trạng thái `FOUND` với email `null`. Gợi ý dùng sealed interface và ba kiểu record đại diện cho `Found`, `EmailMissing`, `NotFound` (JDK 17+).

**Bài 6 — Grouping có khóa thiếu.** Với dữ liệu bán hàng có kênh `null`, chọn rõ giữa: từ chối đơn hàng, bỏ đơn hàng, hay nhóm vào `UNKNOWN`. Viết một pipeline `groupingBy` cho chính sách đã chọn và test kết quả khi mọi kênh đều `null`.

**Bài 7 — Tài nguyên.** Viết hàm trả `Optional<String>` cho dòng không trắng đầu tiên trong một tệp bằng `Files.lines`. Kiểm thử tệp rỗng và tệp có nội dung. Giải thích vì sao tệp không tồn tại cần báo lỗi thay vì trả `Optional.empty()`.

## 16. Bảng quyết định khi thiết kế kết quả

| Câu hỏi | Quyết định gợi ý |
| --- | --- |
| Kết quả phải có **một** phần tử nhưng có thể không tìm thấy? | `Optional<T>` hoặc primitive Optional tương ứng |
| Kết quả là **nhiều** phần tử? | Collection rỗng khi không có phần tử |
| Phép tính có identity đúng về mặt nghiệp vụ? | `reduce(identity, ...)` hoặc terminal operation chuyên dụng |
| Có bản ghi nhưng một thuộc tính thiếu? | Xem có cần trạng thái riêng, validate hay mặc định tường minh |
| Đầu vào `null` có nghĩa là “không có một giá trị”? | `Stream.ofNullable` hoặc `Optional.ofNullable` |
| Một stream đang chứa các phần tử `null`? | `filter(Objects::nonNull)` khi chính sách cho phép |
| Bước sau có trả `Optional` nhưng có thể gặp null? | Xử lý `null` trước `findFirst`/`findAny`/reduction |
| Dữ liệu số không có mẫu? | `OptionalInt`/`OptionalLong`/`OptionalDouble`, phân biệt với số 0 |
| Cần gom Optional phát sinh trong pipeline? | `flatMap(Optional::stream)` nếu được phép bỏ giá trị vắng mặt |
| Nguồn I/O bị lỗi? | Trả/lan truyền lỗi rõ ràng và đóng stream, không đánh đồng với nguồn rỗng |
| Kết quả có thể chạy song song? | Giữ mapper/predicate không can thiệp nguồn, không trạng thái dùng chung |

Thiết kế kết quả cho nguồn rỗng và phần tử `null` là một phần của **hợp đồng dữ liệu** trong Java Stream API. `Optional` diễn đạt việc có hay không có **giá trị khác `null`**; danh sách rỗng diễn đạt không có phần tử tập hợp; giá trị trung hòa phù hợp với phép gộp; còn `null` trong nguồn phải có chính sách rõ ràng. Khi những khác biệt đó được thể hiện ngay trong kiểu trả về, pipeline `filter`, `map`, `reduce`, `collect` và grouping vừa dễ kiểm thử vừa tránh làm sai số liệu do mất thông tin hoặc nuốt lỗi.
