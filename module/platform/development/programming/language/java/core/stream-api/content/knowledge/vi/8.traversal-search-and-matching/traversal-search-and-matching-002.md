# Tìm cực trị bằng `min` và `max`

> **Chương:** Duyệt, tìm kiếm và đối sánh  
> **Module:** `JAVA_STREAM_API` — xử lý dữ liệu theo lối khai báo với Java Stream API, từ pipeline lazy, `filter`, `map`, `reduce`, `collect` đến grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers. Khi áp dụng cần hiểu giới hạn về trạng thái, tài nguyên và hiệu năng.

Trong ứng dụng, chúng ta thường phải trả lời các câu hỏi như: **sản phẩm nào rẻ nhất**, **đơn hàng nào có giá trị lớn nhất**, **nhân viên nào có thâm niên cao nhất**, hoặc **giá trị nhỏ nhất trong một luồng số là bao nhiêu**. Với Java Stream API, `min` và `max` giúp diễn đạt các yêu cầu đó mà không cần tự viết vòng lặp duyệt và cập nhật biến cực trị.

Sau bài học này, bạn có thể tìm cực trị của đối tượng bằng `Comparator`, làm việc an toàn với `Optional`, tìm cực trị trên các primitive stream, xử lý trường hợp đồng hạng và quyết định khi nào nên dùng `min`/`max` thay vì `sorted`.

## 1. `min` và `max` trả về gì?

Trên `Stream<T>`, hai phương thức có dạng:

```java
Optional<T> min(Comparator<? super T> comparator)
Optional<T> max(Comparator<? super T> comparator)
```

Chúng là **terminal operations** (phép toán kết thúc) và thuộc nhóm **reduction**: sau khi các phần tử của luồng được xử lý theo pipeline, chúng tổng hợp để chọn ra **một phần tử cực trị theo `Comparator` đã cung cấp**.

| Phép toán | Chọn phần tử nào? | Kiểu trả về |
| --- | --- | --- |
| `stream.min(comparator)` | Phần tử được coi là **nhỏ nhất** theo thứ tự của comparator | `Optional<T>` |
| `stream.max(comparator)` | Phần tử được coi là **lớn nhất** theo thứ tự của comparator | `Optional<T>` |
| `intStream.min()`, `intStream.max()` | Số nhỏ nhất / lớn nhất | `OptionalInt` |
| `longStream.min()`, `longStream.max()` | Số `long` nhỏ nhất / lớn nhất | `OptionalLong` |
| `doubleStream.min()`, `doubleStream.max()` | Số `double` nhỏ nhất / lớn nhất | `OptionalDouble` |

**Tại sao trả về `Optional`?** Vì Stream có thể rỗng (ví dụ sau `filter` không còn phần tử nào), nên khi đó không tồn tại cực trị. Thay vì tự giả định có một phần tử, người gọi phải quyết định xử lý kết quả vắng mặt.

Ví dụ ngắn:

```java
import java.util.Comparator;
import java.util.List;

List<Integer> numbers = List.of(7, 2, 9, 4, 2);

int minimum = numbers.stream()
        .min(Comparator.naturalOrder())
        .orElseThrow();

int maximum = numbers.stream()
        .max(Comparator.naturalOrder())
        .orElseThrow();

System.out.println(minimum); // 2
System.out.println(maximum); // 9
```

Ở ví dụ này, `Comparator.naturalOrder()` dùng thứ tự tự nhiên của `Integer`. Cả hai thao tác cần một Stream **mới** từ `numbers.stream()`, vì Stream đã được tiêu thụ bởi terminal operation không được dùng lại.

## 2. `Comparator` quyết định khái niệm “nhỏ nhất” và “lớn nhất”

Một `Comparator<T>` là quy tắc so sánh hai giá trị của kiểu `T`. Quy ước của phương thức `compare(a, b)`:

- Trả về số **âm** nếu `a` đứng trước `b`.
- Trả về **0** nếu được xem là tương đương theo quy tắc so sánh.
- Trả về số **dương** nếu `a` đứng sau `b`.

Theo đó, `min` chọn phần tử đứng đầu và `max` chọn phần tử đứng cuối theo comparator. “Nhỏ hơn” không nhất thiết là số học: bạn có thể so theo độ dài chuỗi, giá tiền, ngày tạo, số lượng tồn kho hoặc nhiều khóa liên tiếp.

```java
List<String> words = List.of("Java", "API", "Stream", "JVM");

String shortest = words.stream()
        .min(Comparator.comparingInt(String::length)
                .thenComparing(Comparator.naturalOrder()))
        .orElseThrow();

// "API" (trong nhóm dài 3 ký tự, API đứng trước JVM).
```

`comparingInt(String::length)` so sánh trước theo độ dài; `thenComparing(...)` quy định cách phân thắng bại khi hai chuỗi có cùng độ dài. Nếu không cần tiêu chí phụ, có thể viết gọn `.min(Comparator.comparingInt(String::length))`, nhưng kết quả nào được chọn giữa các phần tử đồng hạng không nên bị mặc định là phần tử xuất hiện đầu tiên.

## 3. Ví dụ hoàn chỉnh: tìm sản phẩm rẻ nhất, đắt nhất và tồn kho nhiều nhất

Chương trình Java 17+ sau có thể lưu vào `StreamExtremaDemo.java` và chạy độc lập:

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

public class StreamExtremaDemo {
    record Product(String code, String name, BigDecimal price, int stock) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("P-01", "Java cơ bản",
                        new BigDecimal("210000"), 12),
                new Product("P-02", "Java Stream API",
                        new BigDecimal("295000"), 7),
                new Product("P-03", "Kỹ thuật JVM",
                        new BigDecimal("390000"), 5),
                new Product("P-04", "Tối ưu Java",
                        new BigDecimal("390000"), 9),
                new Product("P-05", "Lập trình hàm",
                        new BigDecimal("250000"), 18)
        );

        // So sánh giá trước; nếu bằng giá, so mã để kết quả rõ ràng.
        Comparator<Product> byPriceThenCode = Comparator
                .comparing(Product::price)
                .thenComparing(Product::code);

        Optional<Product> cheapest = products.stream()
                .min(byPriceThenCode);

        Optional<Product> mostExpensive = products.stream()
                .max(byPriceThenCode);

        Optional<Product> highestStock = products.stream()
                .max(Comparator.comparingInt(Product::stock));

        // Chỉ xét các sản phẩm có giá không vượt 350.000.
        BigDecimal priceCeiling = new BigDecimal("350000");
        Optional<Product> highestPriceUnderCeiling = products.stream()
                .filter(p -> p.price().compareTo(priceCeiling) <= 0)
                .max(byPriceThenCode);

        System.out.println("Rẻ nhất: "
                + cheapest.map(Product::code).orElse("không có"));
        System.out.println("Đắt nhất: "
                + mostExpensive.map(Product::code).orElse("không có"));
        System.out.println("Tồn kho nhiều nhất: "
                + highestStock.map(Product::code).orElse("không có"));
        System.out.println("Đắt nhất dưới ngưỡng: "
                + highestPriceUnderCeiling.map(Product::code).orElse("không có"));
    }
}
```

Kết quả:

```text
Rẻ nhất: P-01
Đắt nhất: P-04
Tồn kho nhiều nhất: P-05
Đắt nhất dưới ngưỡng: P-02
```

Vì `P-03` và `P-04` cùng giá 390.000, tiêu chí phụ `Product::code` khiến `max(byPriceThenCode)` chọn `P-04`, là mã lớn hơn theo thứ tự chuỗi. Việc lựa chọn này là **quy tắc nghiệp vụ do chúng ta chủ động đặt ra**, không phải hành vi “luôn lấy phần tử cuối nguồn” của `max`.

Ví dụ cũng cho thấy `filter` có thể thu hẹp tập ứng viên **trước** khi tìm cực trị. Sau khi lọc giá không quá 350.000, `P-03` và `P-04` không còn là ứng viên; giá cao nhất trong tập được phép là `P-02`.

## 4. So sánh đối tượng theo một trường bằng `comparing`

Những biến thể thường dùng của `Comparator`:

| API | Mục đích | Ví dụ |
| --- | --- | --- |
| `Comparator.naturalOrder()` | So kiểu có thứ tự tự nhiên (`Integer`, `String`, ...) | `min(Comparator.naturalOrder())` |
| `Comparator.reverseOrder()` | Đảo thứ tự tự nhiên | `max(Comparator.reverseOrder())` |
| `Comparator.comparing(extractor)` | So theo khóa là đối tượng `Comparable` | `comparing(Product::price)` |
| `Comparator.comparingInt(extractor)` | So theo khóa `int` | `comparingInt(Product::stock)` |
| `Comparator.comparingLong(extractor)` | So theo khóa `long` | `comparingLong(Event::timestamp)` |
| `Comparator.comparingDouble(extractor)` | So theo khóa `double` | `comparingDouble(Item::score)` |
| `thenComparing(...)` | Thêm khóa phụ nếu khóa trước bằng nhau | `comparing(Product::price).thenComparing(Product::code)` |
| `reversed()` | Đảo thứ tự của một comparator | `byPriceThenCode.reversed()` |

Các ví dụ `Event::timestamp` và `Item::score` là minh họa cú pháp; chúng yêu cầu các kiểu `Event` và `Item` có phương thức tương ứng trong chương trình thực tế.

Lưu ý về `reversed()`:

```java
Comparator<Product> byPrice = Comparator.comparing(Product::price);

// Hai phép sau cùng chọn sản phẩm có giá nhỏ nhất,
// nếu xét cùng tập phần tử và không có quy tắc đồng hạng khác.
Optional<Product> a = products.stream().min(byPrice);
Optional<Product> b = products.stream().max(byPrice.reversed());
```

Dù `max(byPrice.reversed())` có thể cho cùng mức giá với `min(byPrice)`, cách đầu tiên `min(byPrice)` diễn đạt rõ ý định hơn. Với các phần tử bằng nhau theo comparator, cần bổ sung khóa phụ nếu kết quả cụ thể phải ổn định.

### So sánh `BigDecimal` và tránh comparator sai

Đối với giá tiền kiểu `BigDecimal`, dùng `Comparator.comparing(Product::price)` hoặc `price.compareTo(otherPrice)` để so **giá trị số**. `BigDecimal.equals` còn xét `scale`, vì vậy `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là `false` dù `compareTo` trả `0`.

Không nên so hai số `int` bằng cách trả về phép trừ:

```java
// Có thể tràn số nguyên; không nên dùng:
Comparator<Product> unsafe = (a, b) -> a.stock() - b.stock();

// An toàn và rõ nghĩa hơn:
Comparator<Product> safe = Comparator.comparingInt(Product::stock);
```

Nếu comparator không nhất quán hoặc phụ thuộc trạng thái thay đổi trong khi đang so sánh, kết quả cực trị có thể không phản ánh đúng thứ tự mong muốn. Đặt quy tắc so sánh ổn định, có tính bắc cầu (*transitive*) và tránh can thiệp vào nguồn Stream.

## 5. Đồng hạng: tại sao cần quy tắc phụ?

Xét hai sản phẩm có giá bằng nhau:

```text
P-03   390000
P-04   390000
```

Nếu chỉ dùng:

```java
products.stream().max(Comparator.comparing(Product::price))
```

thì cả `P-03` và `P-04` đều là phần tử cực đại hợp lệ theo comparator. Hợp đồng `min`/`max` **không bảo đảm** chọn phần tử xuất hiện trước hay sau khi có nhiều phần tử cùng cực trị, đặc biệt khi thực thi song song.

Khi nghiệp vụ cần lựa chọn lặp lại được, hãy định nghĩa thêm tiêu chí:

```java
Comparator<Product> byPriceThenCode = Comparator
        .comparing(Product::price)
        .thenComparing(Product::code);

Product selected = products.stream()
        .max(byPriceThenCode)
        .orElseThrow();

// selected.code() = "P-04"
```

Nếu mục tiêu là **lấy tất cả** sản phẩm đồng hạng cao nhất, `max` đơn lẻ chưa đủ vì chỉ trả về một đối tượng. Có thể tìm giá lớn nhất rồi lọc các phần tử bằng giá đó:

```java
Optional<BigDecimal> maxPrice = products.stream()
        .map(Product::price)
        .max(BigDecimal::compareTo);

List<Product> tiedForHighestPrice = maxPrice
        .map(price -> products.stream()
                .filter(p -> p.price().compareTo(price) == 0)
                .toList())
        .orElseGet(List::of);

// [P-03, P-04] nếu hiển thị theo code của mỗi sản phẩm.
```

Giải pháp này duyệt nguồn nhiều lần, phù hợp khi nguồn là `List` tái sử dụng được. Đối với nguồn chỉ cho phép duyệt một lần (ví dụ một Stream gắn với tài nguyên), cần thiết kế phép thu thập hoặc reduction riêng để xử lý đồng hạng trong một lượt.

## 6. Dùng `Optional` đúng khi Stream có thể rỗng

Ví dụ không có ứng viên:

```java
Optional<Product> expensive = products.stream()
        .filter(p -> p.price().compareTo(new BigDecimal("9999999")) > 0)
        .max(Comparator.comparing(Product::price));

System.out.println(expensive.isPresent()); // false
System.out.println(expensive.map(Product::code).orElse("không tìm thấy"));
// không tìm thấy
```

Một số cách tiếp nhận kết quả:

```java
// Chỉ thực hiện hành động khi có phần tử:
expensive.ifPresent(p -> System.out.println(p.name()));

// Lấy giá trị thay thế khi thiếu:
String code = expensive.map(Product::code).orElse("N/A");

// Hoặc báo lỗi khi thiếu là điều kiện bất thường:
Product required = expensive.orElseThrow(
        () -> new IllegalStateException("Không có sản phẩm phù hợp"));
```

Đoạn cuối **sẽ ném ngoại lệ** vì `expensive` rỗng, nên chỉ dùng ở đường xử lý thực sự yêu cầu phải có kết quả. Tránh `get()` khi chưa kiểm tra vì nó ném `NoSuchElementException` trên `Optional.empty()`. Trong hệ thống lớn, việc trả về `Optional<Product>` cho lớp gọi thường rõ nghĩa hơn việc tự chọn một sản phẩm giả hoặc tự đặt giá cực trị bằng `0`.

**Lưu ý:** `Optional` là một container của **không hoặc một giá trị không null**. Nếu phần tử của Stream có thể là `null`, hãy lọc chúng trước khi tính cực trị để tránh các lỗi không mong muốn.

## 7. `IntStream`, `LongStream`, `DoubleStream`: tìm cực trị không cần comparator

Các primitive stream có `min()` và `max()` **không nhận đối số**, trả về `OptionalInt`, `OptionalLong` hoặc `OptionalDouble`. Đây là lựa chọn phù hợp khi chỉ cần số cực trị, không cần giữ lại đối tượng gốc.

```java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.OptionalInt;

List<Integer> values = List.of(6, 3, 11, 4);

OptionalInt minValue = values.stream()
        .mapToInt(Integer::intValue)
        .min();

OptionalInt maxValue = values.stream()
        .mapToInt(Integer::intValue)
        .max();

System.out.println(minValue.orElseThrow()); // 3
System.out.println(maxValue.orElseThrow()); // 11
```

Với đối tượng `Product`, muốn **số lượng tồn kho nhiều nhất**:

```java
int maxStock = products.stream()
        .mapToInt(Product::stock)
        .max()
        .orElseThrow();

// 18
```

Nhưng muốn **sản phẩm có tồn kho nhiều nhất** thì phải giữ đối tượng:

```java
Product item = products.stream()
        .max(Comparator.comparingInt(Product::stock))
        .orElseThrow();

// item.code() = "P-05"
```

Không nên dùng `.mapToInt(Product::stock).max()` rồi cố truy ngược về sản phẩm nếu chỉ tiêu cần trả về ngay từ đầu là đối tượng. Với dữ liệu có nhiều ứng viên bằng nhau, truy ngược còn có thể gây mơ hồ.

Nếu đồng thời cần `count`, `min`, `max`, `sum` và `average` của **một luồng số**, `summaryStatistics()` sẽ giúp tổng hợp trong một lượt duyệt:

```java
IntSummaryStatistics stats = products.stream()
        .mapToInt(Product::stock)
        .summaryStatistics();

System.out.println(stats.getMin());   // 5
System.out.println(stats.getMax());   // 18
System.out.println(stats.getCount()); // 5
```

Với nguồn rỗng, `IntSummaryStatistics.getMin()` trả `Integer.MAX_VALUE` và `getMax()` trả `Integer.MIN_VALUE` vì đó là giá trị khởi tạo, **không phải cực trị có thật**. Luôn kiểm tra `getCount() > 0` trước khi diễn giải các giá trị này là kết quả của dữ liệu.

## 8. `min`/`max` so với `sorted`, `findFirst` và `reduce`

Tìm đúng **một** phần tử nhỏ nhất thường không cần sắp xếp cả nguồn:

```java
// Tìm một sản phẩm rẻ nhất:
Optional<Product> cheapest = products.stream()
        .min(Comparator.comparing(Product::price));

// Sắp xếp theo giá rồi lấy phần tử đầu:
Optional<Product> firstAfterSort = products.stream()
        .sorted(Comparator.comparing(Product::price))
        .findFirst();
```

Cả hai đều có thể cho một sản phẩm với **giá tối thiểu**, nhưng chúng không được bảo đảm trả cùng đối tượng khi nhiều phần tử đồng hạng. Với Stream có thứ tự, `sorted` là phép toán sắp xếp ổn định (*stable*) nên `findFirst` sau `sorted` có thể giữ phần tử xuất hiện đầu tiên trong nhóm cùng giá; `min` không có cam kết chọn theo thứ tự xuất hiện khi đồng hạng.

| Khía cạnh | `min(comparator)` / `max(comparator)` | `sorted(comparator).findFirst()` |
| --- | --- | --- |
| Mục tiêu chính | Chọn một phần tử cực trị | Sắp xếp rồi chọn phần tử đầu |
| Độ phức tạp điển hình trên nguồn hữu hạn chưa sắp xếp | `O(n)` lượt so sánh | Thường `O(n log n)` để sắp xếp |
| Bộ nhớ phụ điển hình khi tuần tự | Có thể giữ một ứng viên hiện tại: `O(1)` | Có thể cần bộ đệm chứa nhiều phần tử: `O(n)` |
| Kết quả khi rỗng | `Optional.empty()` | `Optional.empty()` |
| Nhiều phần tử đồng hạng | Cần tiêu chí phụ nếu muốn chọn đối tượng xác định | Sắp xếp ổn định trên Stream có thứ tự nhưng phải trả chi phí sắp xếp |

Đây là các đặc trưng thuật toán điển hình, không phải khẳng định một implementation cụ thể luôn sử dụng đúng lượng bộ nhớ hoặc số phép so sánh ấy. Stream implementation có thể tối ưu theo đặc tính nguồn và cách thực thi.

`min`/`max` cũng có thể được nhìn như một reduction. Tuy nhiên, `reduce` dưới đây thường dài dòng hơn và đòi hỏi tự quyết định cách xử lý Stream rỗng:

```java
Optional<Integer> minimum = List.of(7, 2, 9, 4).stream()
        .reduce(Integer::min);

// Optional[2]
```

Nếu bài toán chỉ là tìm một phần tử cực trị bằng comparator, hãy ưu tiên `min`/`max` để thể hiện ý định rõ ràng. `reduce` có ích hơn khi xây dựng các quy tắc tích lũy khác.

## 9. Kết hợp `filter`, `map` và giới hạn phạm vi xét cực trị

Thứ tự các phép toán có thể thay đổi ý nghĩa kết quả:

```java
List<Integer> values = List.of(100, 7, 8, 4);

int minOfFirstTwo = values.stream()
        .limit(2)
        .min(Comparator.naturalOrder())
        .orElseThrow();
// 7

int globalMin = values.stream()
        .min(Comparator.naturalOrder())
        .orElseThrow();
// 4
```

`limit(2)` chọn **hai phần tử đầu** trước, nên `min` chỉ xét phần dữ liệu đã đi qua. Ngược lại, nếu bỏ `limit`, `min` xét cả nguồn. Tương tự, `filter(...).max(...)` tìm cực đại **trong nhóm thỏa điều kiện**, không phải cực đại toàn cục.

Khi dùng `map`, cũng cần biết mình muốn trả về **giá trị** hay **đối tượng**:

```java
// Chỉ lấy giá bán lớn nhất:
BigDecimal highestPrice = products.stream()
        .map(Product::price)
        .max(BigDecimal::compareTo)
        .orElseThrow();

// Lấy chính sản phẩm có giá bán lớn nhất:
Product highestPricedProduct = products.stream()
        .max(Comparator.comparing(Product::price)
                .thenComparing(Product::code))
        .orElseThrow();
```

Ví dụ thứ nhất trả `BigDecimal`, còn ví dụ thứ hai trả `Product`. Điều này ảnh hưởng trực tiếp tới dữ liệu có thể sử dụng ở những bước tiếp theo.

## 10. `null`, dữ liệu vô hạn và Stream song song

### Xử lý `null` trước khi so sánh

Một Stream chứa phần tử `null` hoặc một thuộc tính dùng làm khóa so sánh có giá trị `null` dễ gây `NullPointerException`. Cách rõ ràng nhất khi dữ liệu thiếu **không đủ điều kiện** để xét cực trị là loại chúng trước:

```java
import java.util.Objects;

Optional<Product> cheapestValid = products.stream()
        .filter(Objects::nonNull)
        .filter(p -> p.price() != null)
        .min(Comparator.comparing(Product::price));
```

Nếu nghiệp vụ thực sự yêu cầu giữ các phần tử có khóa `null`, `Comparator.nullsFirst(...)` và `Comparator.nullsLast(...)` có thể dùng để định nghĩa thứ tự cho **khóa null**. Tuy nhiên, cần quyết định rõ việc khóa null có được coi là cực trị hay không; `min` hoặc `max` có thể sẽ chọn một đối tượng mà giá bị thiếu chỉ vì quy tắc sắp xếp đó.

### Nguồn vô hạn

Để xác nhận cực đại/cực tiểu trên nguồn không bị giới hạn, nói chung phải xem đủ mọi phần tử; một pipeline vô hạn như `Stream.generate(...).min(...)` thường không kết thúc. Nếu nghiệp vụ chỉ cần cực trị trong một cửa sổ hữu hạn, giới hạn nguồn trước:

```java
Optional<Integer> lowestOfFirst100 = java.util.stream.Stream
        .generate(() -> (int) (Math.random() * 100))
        .limit(100)
        .min(Comparator.naturalOrder());
```

Ví dụ chỉ minh họa việc giới hạn số phần tử; việc sinh dữ liệu ngẫu nhiên khiến kết quả cụ thể thay đổi theo lần chạy. Nếu cần kết quả tái lập, hãy dùng nguồn dữ liệu xác định.

### Xử lý song song

`min`/`max` có thể chạy với `parallelStream()`:

```java
Optional<Product> expensive = products.parallelStream()
        .max(Comparator.comparing(Product::price)
                .thenComparing(Product::code));
```

Khi comparator đúng, ổn định và xác định được thứ tự cho các ứng viên cần so, kết quả cực trị theo quy tắc đó có thể được kết hợp giữa các nhánh. Tuy nhiên, **song song không mặc nhiên nhanh hơn**: cần tính tới kích thước nguồn, chi phí so sánh, phân chia công việc và gộp kết quả. Không viết comparator có side effect hoặc phụ thuộc biến dùng chung thay đổi trong lúc pipeline chạy.

## 11. Các lỗi phổ biến

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gọi `.get()` trên `Optional` có thể rỗng | Có thể ném `NoSuchElementException` | Dùng `orElseThrow`, `orElse`, `ifPresent` hoặc truyền `Optional` cho tầng gọi. |
| Nghĩ `max` tự chọn phần tử “cuối” khi trùng giá trị | Kết quả cụ thể giữa các phần tử đồng hạng không có bảo đảm | Thêm tiêu chí phụ với `thenComparing`. |
| Dùng `mapToInt(...).max()` khi cần trả lại đối tượng gốc | Chỉ còn số cực đại, mất tham chiếu sản phẩm | Dùng `max(Comparator.comparingInt(...))`. |
| Dùng `sorted().findFirst()` chỉ để tìm một cực trị | Thường phải sắp xếp và cấp phát nhiều hơn cần thiết | Dùng `min`/`max`. |
| Dùng phép trừ số nguyên trong comparator | Có thể bị overflow, cho thứ tự sai | Dùng `Integer.compare` hoặc `comparingInt`. |
| Không lọc khóa `null` trước `comparing` | Có thể ném `NullPointerException` | Xác định chính sách thiếu dữ liệu và lọc hoặc so sánh null có chủ đích. |
| Gọi `min`/ `max` nhiều lần trên cùng biến Stream | Stream đã bị tiêu thụ, có thể gây `IllegalStateException` | Tạo Stream mới từ nguồn cho mỗi terminal operation. |
| Tìm cực trị trên Stream vô hạn không có điểm dừng | Pipeline có thể không kết thúc | Giới hạn phạm vi bằng `limit` hoặc thiết kế bài toán theo cửa sổ hữu hạn. |

## 12. Tự kiểm tra

**Câu 1.** Với `[7, 2, 9]`, hai biểu thức `.min(Comparator.naturalOrder())` và `.max(Comparator.reverseOrder())` trả giá trị số nào?

**Đáp án:** Cả hai đều trả `2` (đóng trong `Optional<Integer>`), vì `reverseOrder` đảo định nghĩa phần tử đứng cuối.

**Câu 2.** Vì sao `products.stream().max(Comparator.comparing(Product::price))` không luôn đảm bảo trả về cùng một sản phẩm khi có nhiều sản phẩm đồng giá cao nhất?

**Đáp án:** Comparator xem chúng là tương đương, và hợp đồng `max` không quy định chọn phần tử đồng hạng nào. Muốn ổn định cần thêm khóa phụ như mã sản phẩm.

**Câu 3.** Nếu không có sản phẩm nào thỏa `filter`, `max` trả gì?

**Đáp án:** `Optional.empty()`. Không gọi `get()` nếu chưa xác nhận có phần tử.

**Câu 4.** Muốn lấy sản phẩm có `stock` lớn nhất, biểu thức nào đúng?

```java
// A: chỉ trả số lượng tồn kho lớn nhất
products.stream().mapToInt(Product::stock).max();

// B: trả chính đối tượng Product có tồn kho lớn nhất
products.stream().max(Comparator.comparingInt(Product::stock));
```

**Đáp án:** B đúng nếu cần trả `Product`; A đúng nếu chỉ cần số nguyên.

**Câu 5.** Vì sao `limit(3).min(...)` khác `min(...)` trên nguồn có hơn ba phần tử?

**Đáp án:** `limit(3)` làm thay đổi tập đầu vào của phép tìm cực trị: `min` chỉ xét ba phần tử đầu theo encounter order, không xét toàn bộ nguồn.

## Ghi nhớ

- `Stream.min(comparator)` và `Stream.max(comparator)` là **terminal reductions**, trả về `Optional<T>`, kể cả khi Stream rỗng.
- `Comparator` định nghĩa thứ tự xét cực trị. Dùng `comparing`, `comparingInt`, `thenComparing` để thể hiện đúng tiêu chí, đặc biệt khi nhiều ứng viên đồng hạng.
- Nếu chỉ cần cực trị số học, dùng primitive stream `min()`/`max()`; nếu cần giữ đối tượng, gọi `min`/`max` trên `Stream<T>` với comparator.
- Với nguồn hữu hạn chưa sắp xếp, tìm một cực trị thường cần quét dữ liệu một lượt và tiết kiệm bộ nhớ hơn sắp xếp toàn bộ.
- Kiểm tra trường hợp rỗng, khóa null, phạm vi sau `filter`/`limit`, và chi phí xử lý song song trước khi áp dụng vào dữ liệu thực tế.
