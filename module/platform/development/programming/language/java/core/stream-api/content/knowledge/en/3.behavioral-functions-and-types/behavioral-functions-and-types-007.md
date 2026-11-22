# Dùng Comparator để sắp xếp và chọn phần tử cực trị

Trong Java Stream API, `Comparator<T>` là cách diễn đạt **quy tắc so sánh hai đối tượng cùng kiểu**. Từ một quy tắc đó, ta có thể sắp xếp danh sách bằng `sorted(comparator)`, tìm phần tử nhỏ nhất/lớn nhất bằng `min(comparator)` và `max(comparator)`, hoặc tìm cực trị theo từng nhóm với `Collectors.minBy`/`maxBy`. Điều quan trọng là xác định **khóa so sánh, chiều tăng/giảm, cách phá hòa** và chi phí xử lý trước khi viết pipeline.

Bài thuộc chương **Hàm hành vi và kiểu dữ liệu**, module **JAVA_STREAM_API**. Đây là một phần của cách xử lý dữ liệu khai báo bằng pipeline lazy, `filter`, `map`, `reduce` và `collect`; việc hiểu Comparator cũng hữu ích khi chuyển sang grouping, collector tùy chỉnh, xử lý song song hoặc những bài toán có giới hạn về hiệu năng và trạng thái.

## 1. Comparator là gì?

`Comparator<T>` nằm trong `java.util`, là *functional interface* với phương thức:

```java
int compare(T left, T right);
```

Giá trị trả về có ý nghĩa về **dấu**, không phải trị tuyệt đối:

| Kết quả | Ý nghĩa khi sắp xếp tăng dần theo Comparator |
|---|---|
| Số âm | `left` đứng trước `right` |
| `0` | Hai phần tử ngang nhau **theo tiêu chí so sánh** |
| Số dương | `left` đứng sau `right` |

Ví dụ tạo Comparator từ lambda:

```java
Comparator<String> byLength = (a, b) ->
        Integer.compare(a.length(), b.length());
```

`Integer.compare` diễn đạt rõ so sánh số nguyên và tránh tràn số do viết `a.length() - b.length()`. Cách phổ biến hơn là khai báo *khóa sắp xếp* qua các factory method:

```java
Comparator<String> byLength = Comparator.comparingInt(String::length);
```

Hai ví dụ đều dùng `Comparator<String>`; biểu thức `String::length` là method reference đóng vai trò hàm lấy khóa từ chuỗi.

### Comparator và Comparable

| `Comparable<T>` | `Comparator<T>` |
|---|---|
| Định nghĩa **thứ tự tự nhiên** của đối tượng qua `compareTo` | Định nghĩa **quy tắc so sánh bên ngoài** qua `compare` |
| Lớp đối tượng tự triển khai interface | Có thể dùng lambda, method reference và các phương thức của `Comparator` |
| Phù hợp khi kiểu có thứ tự tự nhiên rõ ràng, ví dụ `Integer`, `String` | Phù hợp khi một kiểu cần nhiều cách sắp xếp: giá, tên, điểm đánh giá... |
| `stream.sorted()` đòi phần tử có thứ tự tự nhiên phù hợp | `stream.sorted(comparator)` sử dụng quy tắc được truyền vào |

Một lớp `Product` không cần triển khai `Comparable` để vẫn có thể sắp xếp theo giá, mã hay đánh giá bằng nhiều Comparator khác nhau.

## 2. Ví dụ thực tế: sản phẩm trong cửa hàng

Ta có danh sách sản phẩm với mã, tên, nhóm hàng, giá tính bằng đồng và điểm đánh giá. Ví dụ dưới đây chạy với **Java 8 trở lên** và có thể dán vào một tệp `ComparatorStreamDemo.java` để chạy trực tiếp.

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

public class ComparatorStreamDemo {
    static final class Product {
        private final String code;
        private final String name;
        private final String category;
        private final int price;
        private final double rating;

        Product(String code, String name, String category,
                int price, double rating) {
            this.code = code;
            this.name = name;
            this.category = category;
            this.price = price;
            this.rating = rating;
        }

        String getCode()     { return code; }
        String getName()     { return name; }
        String getCategory() { return category; }
        int getPrice()       { return price; }
        double getRating()   { return rating; }

        @Override
        public String toString() {
            return code;
        }
    }

    public static void main(String[] args) {
        List<Product> products = Arrays.asList(
                new Product("P01", "Bút", "Văn phòng", 15_000, 4.5),
                new Product("P02", "Sổ", "Văn phòng", 32_000, 4.8),
                new Product("P03", "Bìa", "Văn phòng", 15_000, 4.4),
                new Product("P04", "Túi", "Phụ kiện", 90_000, 4.8),
                new Product("P05", "Cặp", "Phụ kiện", 32_000, 4.7)
        );

        // Giá tăng dần, nếu cùng giá thì mã tăng dần.
        Comparator<Product> priceAscThenCode =
                Comparator.comparingInt(Product::getPrice)
                        .thenComparing(Product::getCode);

        List<Product> priceSorted = products.stream()
                .sorted(priceAscThenCode)
                .collect(Collectors.toList());
        System.out.println("Giá tăng: " + priceSorted);
        // Giá tăng: [P01, P03, P02, P05, P04]

        Optional<Product> cheapest = products.stream()
                .min(priceAscThenCode);
        Optional<Product> mostExpensive = products.stream()
                .max(priceAscThenCode);

        System.out.println("Rẻ nhất: " +
                cheapest.map(Product::getCode).orElse("(không có)"));
        System.out.println("Đắt nhất: " +
                mostExpensive.map(Product::getCode).orElse("(không có)"));
        // Rẻ nhất: P01
        // Đắt nhất: P04

        // Điểm đánh giá giảm dần, giá tăng dần, mã tăng dần.
        Comparator<Product> bestRatedFirst =
                Comparator.comparingDouble(Product::getRating)
                        .reversed()
                        .thenComparingInt(Product::getPrice)
                        .thenComparing(Product::getCode);

        List<Product> ranked = products.stream()
                .sorted(bestRatedFirst)
                .collect(Collectors.toList());
        System.out.println("Xếp hạng: " + ranked);
        // Xếp hạng: [P02, P04, P05, P01, P03]

        Map<String, Optional<Product>> cheapestPerCategory =
                products.stream().collect(
                        Collectors.groupingBy(
                                Product::getCategory,
                                Collectors.minBy(priceAscThenCode)));

        cheapestPerCategory.forEach((category, product) ->
                System.out.println(category + ": " +
                        product.map(Product::getCode).orElse("(không có)")));
        // Văn phòng: P01; Phụ kiện: P05
        // Thứ tự in các nhóm không được bảo đảm.
    }
}
```

Các điểm cần đọc từ ví dụ:

- Cả `sorted`, `min` và `max` đều sử dụng **cùng quy tắc giá tăng, mã tăng**; không cần tự viết ba thuật toán riêng.
- P01 và P03 đều có giá 15.000, nhưng `thenComparing(Product::getCode)` chọn P01 đứng trước P03. Điều này giúp thứ tự và phần tử cực trị được xác định rõ khi khóa chính bằng nhau.
- P02 và P04 cùng đánh giá 4,8. Trong Comparator xếp hạng, giá là khóa phụ tăng dần nên P02 đứng trước P04.
- `groupingBy(..., minBy(...))` tìm sản phẩm có khóa nhỏ nhất **trong từng nhóm**. Kiểu kết quả của `minBy` là `Optional<Product>`.

## 3. Sắp xếp với Stream.sorted

`sorted()` là **thao tác trung gian có trạng thái** (*stateful intermediate operation*). Nó mô tả thứ tự kết quả và chỉ thực hiện khi pipeline có một terminal operation phù hợp. Với dữ liệu hữu hạn thông thường, việc sắp xếp cần thu thập/quan sát các phần tử để xác định thứ tự.

Hai dạng thường gặp:

```java
List<Integer> numbers = Arrays.asList(9, 2, 7, 2);

List<Integer> ascending = numbers.stream()
        .sorted() // Thứ tự tự nhiên: [2, 2, 7, 9]
        .collect(Collectors.toList());

List<Integer> descending = numbers.stream()
        .sorted(Comparator.reverseOrder()) // [9, 7, 2, 2]
        .collect(Collectors.toList());
```

Đối tượng không có `Comparable` hoặc cần so sánh theo tiêu chí khác thứ tự tự nhiên thì truyền Comparator vào `sorted(comparator)`.

### 3.1. Chọn khóa bằng comparing và thenComparing

| Cách tạo Comparator | Ý nghĩa |
|---|---|
| `Comparator.comparing(Product::getName)` | Theo tên, dùng thứ tự tự nhiên của `String` |
| `Comparator.comparingInt(Product::getPrice)` | Theo giá kiểu `int`, tránh boxing khóa |
| `Comparator.comparingLong(...)` | Theo khóa kiểu `long` |
| `Comparator.comparingDouble(Product::getRating)` | Theo đánh giá kiểu `double` |
| `comparator.thenComparing(Product::getCode)` | Nếu khóa trước bằng nhau, so tiếp bằng mã |
| `comparator.reversed()` | Đảo chiều **toàn bộ** Comparator hiện có |

Khi dùng `Comparator.comparing(keyExtractor)`, `keyExtractor` thường là một `Function<T, U>`; còn `comparingInt`, `comparingLong`, `comparingDouble` nhận các hàm lấy khóa nguyên thủy như `ToIntFunction<T>`. Điều này liên kết Comparator với nhóm **kiểu hàm hành vi** trong Java.

### 3.2. Vị trí gọi reversed rất quan trọng

Giả sử hai sản phẩm cùng giá và ta muốn **giá giảm nhưng mã vẫn tăng**:

```java
Comparator<Product> priceDescCodeAsc =
        Comparator.comparingInt(Product::getPrice)
                .reversed()
                .thenComparing(Product::getCode);
// Giá giảm; các sản phẩm cùng giá có mã tăng.
```

Nếu viết khác vị trí:

```java
Comparator<Product> priceDescCodeDesc =
        Comparator.comparingInt(Product::getPrice)
                .thenComparing(Product::getCode)
                .reversed();
// Đảo cả quy tắc giá và quy tắc mã: hai khóa đều giảm.
```

`reversed()` tác động lên **Comparator đã được tạo đến thời điểm gọi nó**. Sự khác nhau thường chỉ lộ ra khi có nhiều bản ghi trùng khóa chính; vì vậy dữ liệu kiểm thử sắp xếp nên có trường hợp hòa.

### 3.3. Thứ tự ổn định và dữ liệu bằng nhau theo Comparator

Với Stream có *encounter order* (ví dụ Stream từ `List`), `sorted` **ổn định** (*stable*): những phần tử có `compare(a, b) == 0` giữ nguyên thứ tự gặp ban đầu. Với Stream không có encounter order, không có cam kết ổn định tương tự.

Tuy vậy, điều này chỉ nói về `sorted`. Không nên dựa vào “phần tử xuất hiện trước trong danh sách” khi gọi `min`/`max` với nhiều đối tượng có cùng khóa cực trị. Nếu nghiệp vụ cần chọn chính xác một bản ghi, hãy xây dựng khóa phụ mang tính quyết định, chẳng hạn mã duy nhất:

```java
Comparator<Product> byPriceThenCode =
        Comparator.comparingInt(Product::getPrice)
                .thenComparing(Product::getCode);
```

Đây cũng là cách dễ bảo đảm kết quả không phụ thuộc vào sự khác biệt của thứ tự duyệt trong một pipeline song song.

## 4. Tìm cực trị bằng min và max

`Stream.min(comparator)` và `Stream.max(comparator)` là **thao tác kết thúc**. Chúng lần lượt chọn phần tử nhỏ nhất/lớn nhất **theo chính Comparator truyền vào**, và trả về `Optional<T>` vì nguồn có thể rỗng.

```java
Optional<Integer> smallest = Arrays.asList(8, 3, 11)
        .stream()
        .min(Integer::compare); // Optional[3]

Optional<Integer> largest = Arrays.asList(8, 3, 11)
        .stream()
        .max(Integer::compare); // Optional[11]

Optional<Integer> absent = Collections.<Integer>emptyList()
        .stream()
        .min(Integer::compare); // Optional.empty
```

Ví dụ này cần `import java.util.Collections;` cùng các import tương ứng. Không gọi `get()` trên một Optional khi chưa kiểm tra có giá trị; ưu tiên `ifPresent`, `orElse`, `orElseGet` hoặc `orElseThrow` khi vắng dữ liệu là lỗi nghiệp vụ.

### 4.1. max và min luôn theo chiều của Comparator

Đây là lỗi rất thường gặp:

```java
Comparator<Product> priceDescending =
        Comparator.comparingInt(Product::getPrice).reversed();

Optional<Product> firstInDescendingOrder =
        products.stream().min(priceDescending);
// Chọn giá cao nhất theo nghĩa nghiệp vụ.

Optional<Product> lastInDescendingOrder =
        products.stream().max(priceDescending);
// Chọn giá thấp nhất theo nghĩa nghiệp vụ.
```

Vì Comparator đã đảo chiều, **phần tử nhỏ nhất theo Comparator** lại là sản phẩm có giá lớn nhất. Cách dễ đọc hơn khi chỉ muốn giá lớn nhất là giữ Comparator tăng dần và gọi `max(Comparator.comparingInt(Product::getPrice))`.

Nếu muốn “sản phẩm đứng đầu bảng xếp hạng” trong ví dụ `bestRatedFirst`, hãy dùng `min(bestRatedFirst)` hoặc `sorted(bestRatedFirst).findFirst()`. Cách thứ nhất tránh việc sắp xếp toàn bộ khi chỉ cần một phần tử.

### 4.2. min/max hay sorted(...).findFirst()?

```java
// Chỉ cần một phần tử rẻ nhất:
Optional<Product> cheapest = products.stream()
        .min(Comparator.comparingInt(Product::getPrice));

// Cần toàn bộ danh sách theo thứ tự giá:
List<Product> sortedByPrice = products.stream()
        .sorted(Comparator.comparingInt(Product::getPrice))
        .collect(Collectors.toList());
```

Với `n` phần tử và phép so sánh có chi phí coi như hằng số:

| Nhu cầu | Cách làm | Chi phí điển hình |
|---|---|---|
| Lấy một phần tử cực trị | `min` hoặc `max` | `O(n)` phép so sánh; không cần giữ danh sách đã sắp xếp |
| Sắp xếp toàn bộ để hiển thị | `sorted` rồi `collect` | Thường `O(n log n)` thời gian, thêm bộ nhớ cho việc sắp xếp |
| Lấy `k` phần tử đầu theo thứ tự | `sorted(comparator).limit(k)` | Gọn và đúng cho nguồn hữu hạn, nhưng không mặc nhiên có chi phí `O(n log k)` |

Với tập cực lớn và chỉ cần `k` phần tử đứng đầu, một cấu trúc heap giới hạn kích thước có thể hiệu quả hơn sắp xếp toàn bộ. Không mặc định rằng đặt `limit(k)` sau `sorted` sẽ khiến Stream tự tối ưu thành thuật toán top-k.

Các phép duyệt như `min`, `max` và `sorted` cần tiêu thụ nguồn để biết kết quả; nguồn vô hạn có thể khiến phép tính không kết thúc. Việc thêm `limit` **trước** `sorted` giới hạn số đầu vào nhưng cũng thay đổi ý nghĩa: lúc đó chỉ chọn trong số phần tử đầu đã lấy.

## 5. Cực trị theo nhóm với Collectors.minBy/maxBy

Khi bài toán là “rẻ nhất **trong mỗi danh mục**” hoặc “đánh giá cao nhất **theo nhà cung cấp**”, một `min`/`max` đơn lẻ không đủ vì nó trả một kết quả cho toàn Stream. Dùng downstream collector:

```java
Comparator<Product> byPriceThenCode =
        Comparator.comparingInt(Product::getPrice)
                .thenComparing(Product::getCode);

Map<String, Optional<Product>> cheapestByCategory =
        products.stream()
                .collect(Collectors.groupingBy(
                        Product::getCategory,
                        Collectors.minBy(byPriceThenCode)));
```

`groupingBy` tạo các nhóm theo `category`, còn `minBy` chọn cực trị **trong từng nhóm**. Giá trị là `Optional<Product>` theo hợp đồng của collector, dù một nhóm được tạo từ các phần tử đầu vào thường không rỗng.

Tìm sản phẩm có điểm đánh giá cao nhất theo nhóm:

```java
Comparator<Product> byRatingThenCode =
        Comparator.comparingDouble(Product::getRating)
                .thenComparing(Product::getCode);

Map<String, Optional<Product>> highestRatedByCategory =
        products.stream()
                .collect(Collectors.groupingBy(
                        Product::getCategory,
                        Collectors.maxBy(byRatingThenCode)));
```

Với quy tắc `byRatingThenCode`, nếu cùng điểm thì mã **lớn hơn** được chọn bởi `max`. Nếu nghiệp vụ muốn khi điểm bằng nhau chọn mã **nhỏ hơn**, phải điều chỉnh khóa phụ thay vì kỳ vọng `max` “tự lấy bản ghi đầu tiên”.

Các collector như `minBy`/`maxBy` cũng phù hợp với mô hình xử lý khai báo; không cần tự chia nhóm rồi viết vòng lặp duyệt từng nhóm.

## 6. Xử lý null và dữ liệu đặc biệt

Vì `Comparator.comparing(Product::getName)` cần khóa so sánh, giá trị `null` có thể gây `NullPointerException`. `Comparator.nullsFirst` và `Comparator.nullsLast` thể hiện rõ thứ tự mong muốn.

**Khóa tên có thể null, nhưng bản thân Product khác null:**

```java
Comparator<Product> byNullableName =
        Comparator.comparing(
                Product::getName,
                Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER));
```

**Phần tử Product trong Stream có thể null:**

```java
Comparator<Product> byPriceWithNullProducts =
        Comparator.nullsLast(
                Comparator.comparingInt(Product::getPrice));
```

Hai trường hợp khác nhau: cách thứ nhất xử lý **khóa trả về từ getter**; cách thứ hai xử lý **đối tượng đem so sánh**. Nếu cả đối tượng lẫn khóa có thể null, có thể kết hợp hai lớp Comparator tương ứng.

Đối với tiền tệ, nếu lưu bằng `BigDecimal`, có thể dùng `Comparator.comparing(Product::getAmount)` khi phương thức `getAmount()` trả `BigDecimal` không null; `BigDecimal.compareTo` so giá trị số theo thứ tự tự nhiên. Lưu ý hai `BigDecimal` có thể so sánh bằng `0` dù `equals` khác nhau vì thang đo (*scale*) khác.

Đối với khóa `double`, `comparingDouble` sử dụng quy tắc của `Double.compare`, trong đó `NaN` và `-0.0` có quy tắc thứ tự riêng. Nếu điểm đánh giá không được phép mang những giá trị này, hãy kiểm tra/chuẩn hóa dữ liệu theo quy tắc nghiệp vụ trước khi sắp xếp.

## 7. Hợp đồng Comparator và các lỗi khó thấy

Comparator đúng cần tuân thủ các quy tắc nhất quán, bao gồm:

1. **Đối xứng về dấu:** dấu của `compare(a, b)` phải đối lập dấu của `compare(b, a)`.
2. **Bắc cầu:** nếu `a > b` và `b > c` theo Comparator thì `a > c`.
3. **Nhất quán khi so sánh bằng 0:** nếu `compare(a, b) == 0` thì hai đối tượng phải cho cùng quan hệ thứ tự với một đối tượng thứ ba bất kỳ.

`compare(a, b) == 0` **không bắt buộc** đồng nghĩa `a.equals(b)`, nhưng nên hiểu hệ quả. Ví dụ `TreeSet` dựa vào Comparator để quyết định hai phần tử trùng nhau theo thứ tự, nên hai đối tượng khác nhau nhưng so bằng 0 có thể bị coi là cùng phần tử trong `TreeSet`. Trong `Stream.sorted`, chúng vẫn là hai phần tử của Stream nếu nguồn chứa cả hai.

Các lỗi phổ biến:

```java
// KHÔNG NÊN: phép trừ có thể tràn int.
Comparator<Product> unsafe = (a, b) -> a.getPrice() - b.getPrice();

// NÊN: so sánh số nguyên có hợp đồng rõ ràng.
Comparator<Product> safe =
        Comparator.comparingInt(Product::getPrice);
```

- Không dùng Comparator trả kết quả ngẫu nhiên, phụ thuộc đồng hồ, hoặc đọc dữ liệu có thể bị sửa trong lúc sắp xếp.
- Tránh tự thêm side effect như ghi vào danh sách dùng chung trong Comparator. Một phép so sánh có thể được gọi nhiều lần, không có cam kết thứ tự gọi và có thể chạy trong các worker khác nhau nếu Stream song song.
- Không kỳ vọng kết quả đúng từ quy tắc không bắc cầu hoặc thứ tự thay đổi giữa chừng; thuật toán sắp xếp có thể cho kết quả vô nghĩa hoặc ném `IllegalArgumentException` trong một số trường hợp vi phạm hợp đồng.
- Không gọi `sorted()` không tham số trên kiểu thiếu thứ tự tự nhiên phù hợp; lỗi có thể chỉ bộc lộ khi terminal operation thực thi.

## 8. Comparator trong pipeline song song

`products.parallelStream().sorted(comparator)` vẫn sắp xếp theo quy tắc Comparator; với nguồn có encounter order, `sorted` tiếp tục có bảo đảm ổn định. Nhưng song song **không tự động nhanh hơn**:

- Sắp xếp và ghép các phần kết quả phát sinh chi phí điều phối, bộ nhớ và đồng bộ.
- Comparator cần an toàn khi được gọi từ nhiều worker. Nên dùng hàm thuần, lấy khóa từ đối tượng không đổi trong lúc xử lý.
- Nếu các phần tử khác nhau có khóa so sánh bằng nhau, `min`/`max` không nên được dùng để ngầm chọn phần tử “đến trước”. Bổ sung khóa phụ duy nhất khi cần kết quả xác định.
- `sorted(comparator).forEach(...)` trên Stream song song **không bảo đảm thứ tự hành động** do `forEach` không bảo đảm encounter order. Dùng `forEachOrdered(...)` nếu thực sự cần thứ tự, dù điều đó có thể giảm lợi thế song song.

Đối với tập dữ liệu nhỏ và phép lấy khóa rẻ, hãy bắt đầu với Stream tuần tự. Chỉ cân nhắc song song khi khối lượng đủ lớn, kiểm tra dữ liệu đầu vào, tính đúng của Comparator và đo hiệu năng thực tế.

## 9. Bài tập vận dụng

Cho một danh sách `Product` như ở ví dụ chính:

1. **Sắp xếp theo giá giảm, cùng giá theo mã tăng.** Gợi ý: `Comparator.comparingInt(Product::getPrice).reversed().thenComparing(Product::getCode)`. Đáp án mã: `[P04, P02, P05, P01, P03]`.
2. **Chọn sản phẩm rẻ nhất có điểm từ 4,6 trở lên.** Dùng `filter(p -> p.getRating() >= 4.6)` rồi `min(byPriceThenCode)`. Kết quả: P02 (P05 cùng giá nhưng mã lớn hơn).
3. **Lấy hai sản phẩm đầu bảng theo điểm giảm và giá tăng.** Dùng `sorted(bestRatedFirst).limit(2)`. Kết quả: `[P02, P04]`.
4. **Tìm sản phẩm đắt nhất trong từng danh mục.** Dùng `groupingBy(Product::getCategory, maxBy(byPriceThenCode))`. Với dữ liệu mẫu: Văn phòng → P02, Phụ kiện → P04.
5. **Nếu danh sách rỗng thì điều gì xảy ra?** `min`/`max` trả `Optional.empty()`; còn `sorted(...).collect(toList())` trả danh sách rỗng.

## 10. Ghi nhớ khi thiết kế pipeline

Khi cần thứ tự hiển thị, hãy mô tả thứ tự bằng `Comparator.comparing...`, kết hợp khóa bằng `thenComparing` rồi dùng `sorted(comparator)`. Khi chỉ cần **một** phần tử nhỏ nhất/lớn nhất, dùng `min` hoặc `max` để tránh sắp xếp không cần thiết. Khi cần cực trị **theo nhóm**, kết hợp `groupingBy` với `Collectors.minBy`/`maxBy`. Trong mọi trường hợp, hãy xác định chiều của Comparator, cách phá hòa, dữ liệu null, hợp đồng so sánh, khả năng giữ trạng thái và chi phí của pipeline.
