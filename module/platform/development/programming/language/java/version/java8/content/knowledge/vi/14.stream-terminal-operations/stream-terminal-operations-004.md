# count(), min() và max() trong Stream API (Java 8+)

`count()`, `min()` và `max()` là ba **terminal operation (phép toán kết thúc)** của Java Stream. Chúng tạo kết quả từ các phần tử sau khi pipeline đã áp dụng những bước như `filter`, `map`, `distinct` hoặc `limit`. Khi một terminal operation kết thúc, stream đó đã được tiêu thụ; muốn tính một kết quả khác từ cùng nguồn dữ liệu, cần tạo stream mới.

Bài này tập trung vào cách **đếm phần tử**, **tìm phần tử nhỏ nhất/lớn nhất theo tiêu chí**, xử lý nguồn rỗng, và chọn cách tính phù hợp khi cần cả ba thống kê. Đây đều là API còn được hỗ trợ và sử dụng trong Java hiện đại.

## 1. Phân biệt nhanh ba phép toán

| Phép toán | Đối với `Stream<T>` | Ý nghĩa |
| --- | --- | --- |
| `count()` | Trả về `long` | Số phần tử đi tới phép toán kết thúc sau các bước trung gian |
| `min(comparator)` | Trả về `Optional<T>` | Phần tử nhỏ nhất theo `Comparator` được truyền vào |
| `max(comparator)` | Trả về `Optional<T>` | Phần tử lớn nhất theo `Comparator` được truyền vào |

Đối với các stream số nguyên thủy, `IntStream`, `LongStream` và `DoubleStream` đều có `count()` trả về `long`; `min()` và `max()` **không cần comparator** và trả về lần lượt `OptionalInt`, `OptionalLong`, `OptionalDouble`.

Điểm cần nhớ: với `Stream<T>`, **không có** lời gọi `stream.min()` hay `stream.max()` không tham số; phải cung cấp tiêu chí so sánh. Với `IntStream` thì `intStream.min()`/`max()` là hợp lệ.

## 2. `count()`: đếm kết quả của pipeline

`count()` đếm số phần tử còn lại sau khi các intermediate operation được áp dụng. Nó trả về `long`, kể cả khi số đếm nhỏ.

```java
List<Integer> numbers = Arrays.asList(5, 2, 9, 2, 7);

long all = numbers.stream().count();                    // 5
long atLeastFive = numbers.stream().filter(n -> n >= 5).count(); // 3
long unique = numbers.stream().distinct().count();      // 4
long firstTwo = numbers.stream().limit(2).count();       // 2
```

*Các dòng trên là đoạn minh họa; chương trình độc lập có thể chạy nằm ở mục 7.*

- `filter(predicate).count()` là cách đếm các phần tử **thỏa điều kiện**; bản thân `count()` không nhận predicate.
- `distinct()` làm số đếm phản ánh các giá trị khác nhau theo `equals`/`hashCode`; không tự đếm "bản ghi duy nhất" theo một khóa nghiệp vụ nếu không định nghĩa đúng tiêu chí.
- `flatMap(...)` có thể làm số phần tử tăng hoặc giảm; `limit(n)` có thể cắt bớt số phần tử đi tới `count()`.
- `count()` tính phần tử chứ không tính tổng giá trị của chúng. Để tính tổng số, dùng các phép tổng hợp như `sum()` trên primitive stream.

Nếu chỉ cần số phần tử của một `Collection` đã có trong bộ nhớ và **không có phép biến đổi nào**, `collection.size()` thường trực tiếp, rõ nghĩa hơn việc tạo stream để gọi `count()`. Khi cần đếm sau bước lọc hoặc tổ hợp pipeline, `filter(...).count()` phù hợp.

### Tối ưu hóa và tác dụng phụ

Ở các bản Java hiện đại, `count()` có thể suy ra số phần tử từ nguồn đã biết kích thước mà **không duyệt từng phần tử**. Do đó, không được trông chờ `peek(...)`, `map(...)` có tác dụng phụ, hoặc callback trung gian được gọi chỉ vì phía sau có `count()`. Ví dụ sau **không đảm bảo** in ra từng chuỗi:

```java
long size = Arrays.asList("A", "B", "C").stream()
    .peek(System.out::println) // Có thể không chạy
    .count();
```

Hãy dùng stream để biến đổi và tổng hợp dữ liệu, giữ các lambda **stateless** và **không can thiệp nguồn**; đừng gắn hành vi nghiệp vụ bắt buộc vào tác dụng phụ của intermediate operation.

## 3. `min(comparator)` và `max(comparator)`: so sánh theo thứ tự

Hai phép toán này chọn **phần tử**, không chỉ chọn một giá trị số. Với object stream, tiêu chí nhỏ/lớn được định nghĩa bởi `Comparator`.

```java
List<Integer> numbers = Arrays.asList(5, 2, 9, 2, 7);

Optional<Integer> smallest = numbers.stream()
    .min(Comparator.naturalOrder());  // Optional chứa 2

Optional<Integer> largest = numbers.stream()
    .max(Comparator.naturalOrder());  // Optional chứa 9
```

- `Comparator.naturalOrder()` dùng thứ tự tự nhiên của các phần tử có thể so sánh, chẳng hạn `Integer`, `Long`, `String`. Đối với chuỗi, đây là thứ tự so sánh chuỗi, **không phải** thứ tự số học của chữ số trong chuỗi.
- `Comparator.comparingInt(Product::getPrice)` so sánh đối tượng `Product` bằng thuộc tính `price` kiểu `int`. Với `long`/`double`, dùng `comparingLong`/`comparingDouble` phù hợp.
- `Comparator.reverseOrder()` **đảo chiều** thứ tự, nên `min(reverseOrder())` sẽ lấy giá trị lớn nhất theo thứ tự tự nhiên. Hãy xác định comparator trước rồi mới diễn giải "nhỏ nhất/lớn nhất".
- Khi nhiều phần tử có cùng khóa so sánh, không nên dựa vào việc `min`/`max` chọn một phần tử cụ thể trong nhóm bằng nhau. Thêm tiêu chí phá hòa bằng `thenComparing(...)` nếu việc chọn kết quả cần rõ ràng và lặp lại được.

Ví dụ nghiệp vụ: chọn sản phẩm rẻ nhất và đắt nhất, phá hòa bằng tên:

```java
Comparator<Product> byPriceThenName =
    Comparator.comparingInt(Product::getPrice)
              .thenComparing(Product::getName);

Optional<Product> cheapest = products.stream().min(byPriceThenName);
Optional<Product> mostExpensive = products.stream().max(byPriceThenName);
```

Đoạn này sử dụng kiểu `Product` được định nghĩa trong chương trình đầy đủ bên dưới. Nếu yêu cầu chỉ là giá thấp nhất chứ không phải **sản phẩm** rẻ nhất, phép `mapToInt(Product::getPrice).min()` sẽ thể hiện ý định rõ hơn.

### Comparator và dữ liệu bất thường

Comparator nên nhất quán, không giữ trạng thái thay đổi giữa các lần so sánh, và xác định thứ tự phù hợp dữ liệu. Nếu nguồn chứa `null`, hãy xác định quy tắc xử lý trước khi gọi `min`/`max`: ví dụ lọc bằng `filter(Objects::nonNull)`. `Optional` không thể biểu diễn kết quả là `null`; theo hợp đồng API, `Stream.min/max` có thể ném `NullPointerException` nếu phần tử được chọn là `null`. Không dùng kết quả so sánh theo chuỗi cho dữ liệu số đang lưu dưới dạng văn bản nếu mục tiêu là giá trị số.

## 4. Nguồn rỗng: tại sao `Optional` rất quan trọng?

`count()` trên stream rỗng trả về **0**. Nhưng không có phần tử nào để coi là nhỏ nhất hay lớn nhất, vì vậy `min()`/`max()` trả về `Optional.empty()` hoặc optional nguyên thủy rỗng.

```java
long count = Stream.<Integer>empty().count(); // 0

Optional<Integer> min = Stream.<Integer>empty()
    .min(Comparator.naturalOrder());          // Optional.empty()

int safeMin = min.orElse(-1);                  // -1 chỉ là giá trị mặc định do ta chọn
boolean hasMin = min.isPresent();              // false
```

Chọn một trong các cách theo nhu cầu:
- `ifPresent(...)` hoặc `isPresent()` khi kết quả không bắt buộc có.
- `orElse(defaultValue)` khi **có giá trị mặc định hợp lý về nghiệp vụ**.
- `orElseThrow(...)` khi không có dữ liệu là lỗi cần thông báo.

Không gọi `get()` hoặc `getAsInt()` khi chưa chắc chắn có giá trị: với optional rỗng, thao tác đó ném `NoSuchElementException`. Không mặc định rằng min/max của nguồn rỗng là `0`; đó là quyết định của ứng dụng, không phải ngữ nghĩa của API.

## 5. Dùng primitive stream khi so sánh giá trị số

Với các giá trị số, `IntStream`, `LongStream` và `DoubleStream` cho phép tính min/max trực tiếp, tránh boxing thành `Integer`/`Long`/`Double` khi không cần giữ cả đối tượng.

| Loại stream | `count()` | `min()` và `max()` |
| --- | --- | --- |
| `IntStream` | `long` | `OptionalInt` |
| `LongStream` | `long` | `OptionalLong` |
| `DoubleStream` | `long` | `OptionalDouble` |

```java
OptionalInt minInt = IntStream.of(8, 3, 12).min();  // OptionalInt[3]
OptionalInt maxInt = IntStream.of(8, 3, 12).max();  // OptionalInt[12]

OptionalInt minPrice = products.stream()
    .mapToInt(Product::getPrice)
    .min();
```

Mỗi dòng tạo stream riêng. Nếu dùng `DoubleStream`, hãy lưu ý dữ liệu `NaN` hoặc vô cực có thể ảnh hưởng tới thứ tự và kết quả; làm sạch hoặc quy định dữ liệu số đầu vào trước khi áp dụng cho báo cáo nghiệp vụ.

## 6. Cần cả `count`, `min`, `max`: tránh tiêu thụ cùng stream nhiều lần

Đây là lỗi phổ biến:

```java
Stream<Integer> stream = numbers.stream();
long count = stream.count();
// stream.min(Comparator.naturalOrder()); // Sai: stream đã được tiêu thụ
```

Một stream chỉ được dùng một lần cho terminal operation. Nếu dữ liệu nằm trong `List` có thể đọc lại, hãy gọi `numbers.stream()` **mới** cho mỗi phép toán. Mỗi lời gọi khi đó độc lập và có thể duyệt nguồn thêm một lượt.

Nếu phải lấy cùng lúc **số lượng, giá trị nhỏ nhất và lớn nhất của một thuộc tính số**, dùng `summaryStatistics()` trên primitive stream hoặc `Collectors.summarizingInt/Long/Double(...)` trên object stream để tổng hợp trong một lần duyệt:

```java
IntSummaryStatistics stats = products.stream()
    .collect(Collectors.summarizingInt(Product::getPrice));

if (stats.getCount() > 0) {
    long count = stats.getCount();
    int minPrice = stats.getMin();
    int maxPrice = stats.getMax();
}
```

`IntSummaryStatistics` cũng cung cấp tổng và trung bình. Tuy nhiên **cần kiểm tra `getCount() > 0`** trước khi diễn giải min/max: với nguồn rỗng, `getMin()` là `Integer.MAX_VALUE` và `getMax()` là `Integer.MIN_VALUE` (giá trị sentinel), không phải kết quả min/max thực của dữ liệu. Bộ thống kê nguyên thủy cho ra **giá trị thuộc tính** cực trị; nếu cần giữ lại **đối tượng** tương ứng, dùng `min(comparator)`/`max(comparator)` hoặc thiết kế phép gom phù hợp.

## 7. Chương trình Java hoàn chỉnh, chạy được

Tạo file `StreamCountMinMaxDemo.java` với nội dung sau. Chương trình dùng API Stream đã có từ Java 8 và chạy được với JDK hiện đại (bao gồm Java 17+).

```java
import java.util.*;
import java.util.stream.*;

public class StreamCountMinMaxDemo {
    static final class Product {
        private final String name;
        private final int price;

        Product(String name, int price) {
            this.name = name;
            this.price = price;
        }

        String getName() {
            return name;
        }

        int getPrice() {
            return price;
        }
    }

    public static void main(String[] args) {
        List<Integer> numbers = Arrays.asList(5, 2, 9, 2, 7);

        long countAtLeastFive = numbers.stream()
                .filter(n -> n >= 5)
                .count();
        int min = numbers.stream()
                .min(Comparator.naturalOrder())
                .orElseThrow(() -> new IllegalStateException("empty"));
        int max = numbers.stream()
                .max(Comparator.naturalOrder())
                .orElseThrow(() -> new IllegalStateException("empty"));

        System.out.println("count >= 5: " + countAtLeastFive);
        System.out.println("min: " + min);
        System.out.println("max: " + max);

        List<Product> products = Arrays.asList(
                new Product("Mouse", 200),
                new Product("Keyboard", 500),
                new Product("Monitor", 3000));

        Comparator<Product> byPriceThenName =
                Comparator.comparingInt(Product::getPrice)
                          .thenComparing(Product::getName);

        Optional<Product> cheapest = products.stream().min(byPriceThenName);
        Optional<Product> mostExpensive = products.stream().max(byPriceThenName);

        System.out.println("cheapest: " +
                cheapest.map(Product::getName).orElse("(empty)"));
        System.out.println("most expensive: " +
                mostExpensive.map(Product::getName).orElse("(empty)"));

        OptionalInt primitiveMin = IntStream.of(8, 3, 12).min();
        System.out.println("primitive min: " + primitiveMin.orElse(-1));

        IntSummaryStatistics stats = products.stream()
                .collect(Collectors.summarizingInt(Product::getPrice));
        System.out.println("stats count/min/max: " +
                stats.getCount() + "/" + stats.getMin() + "/" + stats.getMax());

        System.out.println("empty stream count: " + Stream.empty().count());
        System.out.println("empty stream min present: " +
                Stream.<Integer>empty()
                      .min(Comparator.naturalOrder())
                      .isPresent());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 StreamCountMinMaxDemo.java
java StreamCountMinMaxDemo
```

Kết quả chuẩn:

```text
count >= 5: 3
min: 2
max: 9
cheapest: Mouse
most expensive: Monitor
primitive min: 3
stats count/min/max: 3/200/3000
empty stream count: 0
empty stream min present: false
```

Giải thích: danh sách `[5, 2, 9, 2, 7]` có ba phần tử lớn hơn hoặc bằng 5 và có cực trị 2/9. `Product` được so sánh bằng giá rồi bằng tên; sản phẩm giá 200 là rẻ nhất, giá 3000 là đắt nhất. Bộ `IntSummaryStatistics` tính 3 bản ghi, giá thấp nhất 200 và cao nhất 3000 trong một phép gom. Trường hợp nguồn rỗng cho count bằng 0 và không có minimum.

## 8. Sai lầm thường gặp và cách chọn API

| Tình huống | Cách xử lý |
| --- | --- |
| Đếm số phần tử thỏa điều kiện | `stream.filter(condition).count()` |
| Đếm số giá trị duy nhất | `stream.distinct().count()` (theo `equals`/`hashCode`) |
| Cần đối tượng có thuộc tính nhỏ nhất/lớn nhất | `stream.min(Comparator.comparingInt(...))` / `max(...)` |
| Chỉ cần giá trị cực trị kiểu `int` | `stream.mapToInt(...).min()` / `max()` |
| Nguồn có thể rỗng | Xử lý `Optional`; không gọi `get()` thiếu kiểm tra |
| Cần count/min/max của một thuộc tính số trong một lượt | `summaryStatistics()` hoặc `Collectors.summarizingInt(...)`; kiểm tra count trước khi đọc extrema |
| Gọi hai terminal operation trên cùng một stream | Tạo stream mới từ nguồn hoặc gom thành một kết quả tổng hợp |
| Dùng `min` với comparator đảo chiều | Kết quả là cực trị theo **thứ tự đã đảo**, có thể khác ý định |
| Cần thứ tự rõ ràng khi giá bằng nhau | Bổ sung `thenComparing(...)` để xác định tiêu chí phá hòa |
| Chèn cập nhật trạng thái trong `peek`/`map` và đợi `count()` kích hoạt | Bỏ lệ thuộc tác dụng phụ; pipeline có thể được tối ưu không gọi callback |

Về độ phức tạp, tìm min/max của stream hữu hạn thông thường cần duyệt các phần tử phù hợp (thường `O(n)`); `count()` cũng có thể cần duyệt, nhưng được phép tối ưu khi biết kích thước nguồn. Mỗi terminal operation tự nó không đòi hỏi giữ tất cả phần tử trong bộ nhớ; chi phí thực tế còn phụ thuộc các intermediate operation như `sorted` hoặc `distinct`. Với nguồn không giới hạn, một phép `count/min/max` không có điều kiện kết thúc có thể chạy mãi; dùng nguồn hữu hạn hoặc giới hạn pipeline khi cần.

**Tự kiểm tra:** Với `List<Integer> values = Arrays.asList(8, 2, 2, 7);`, kết quả `values.stream().distinct().count()` là **3**, `min(Comparator.naturalOrder())` là **2**, `max(...)` là **8**; mỗi phép phải nhận một stream mới.

### Tài liệu tham khảo hiện hành

- [`Stream` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): hợp đồng `count`, `min`, `max` và khả năng tối ưu hóa pipeline.
- [`IntStream` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/IntStream.html): terminal operation với primitive `int`.
- [`IntSummaryStatistics` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/IntSummaryStatistics.html): count/min/max và giá trị trên nguồn rỗng.