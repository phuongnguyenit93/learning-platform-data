# mapToInt, mapToLong, mapToDouble trong Java Stream

## 1. Mục tiêu học tập

Khi xử lý dữ liệu bằng Stream, ta thường bắt đầu bằng **Stream<T>** chứa đối tượng như Product, Order, String hoặc Integer, nhưng kết quả muốn tính lại là **số nguyên, số nguyên dài hoặc số thực**. Java 8 cung cấp ba intermediate operations chuyên dụng để chuyển từ object stream sang **primitive stream**:

- **mapToInt(ToIntFunction<? super T>)**: chuyển mỗi phần tử T thành **int**, tạo **IntStream**.
- **mapToLong(ToLongFunction<? super T>)**: chuyển mỗi phần tử T thành **long**, tạo **LongStream**.
- **mapToDouble(ToDoubleFunction<? super T>)**: chuyển mỗi phần tử T thành **double**, tạo **DoubleStream**.

Đây là các API vẫn áp dụng trên những phiên bản Java hiện đại. Cả ba giải quyết bài toán **ánh xạ một phần tử đầu vào thành một giá trị số nguyên thủy** (one-to-one mapping), đồng thời mở ra những terminal operations như **sum()**, **average()**, **summaryStatistics()**, **min()**, **max()** mà Stream<T> thông thường không có trực tiếp.

Bài học sẽ giải thích các chữ ký API, quan hệ với functional interfaces, tính lazy, kiểu suy luận, boxing/unboxing, xử lý null và chuỗi không hợp lệ, số học tràn, độ chính xác double, kết quả của luồng rỗng và cách chuyển đổi qua lại giữa object stream và primitive stream. Ví dụ độc lập được viết theo cú pháp Java 8, kèm lệnh javac/java và stdout. Những ghi chú về JDK hiện đại chỉ dùng các kiến thức còn hiệu lực.

## 2. Vị trí của ba phương thức trong Stream pipeline

Một pipeline có ba thành phần dễ nhận diện:

~~~text
Nguồn: List<Product> hoặc Stream<String>
                  |
                  v
          Stream<T> (object stream)
                  |
       mapToInt / mapToLong / mapToDouble
                  |
          +-------+--------+
          |       |        |
          v       v        v
      IntStream LongStream DoubleStream
          |       |        |
          +-------+--------+
                  |
     filter, map, sum, average, max,
     min, summaryStatistics, toArray...
                  |
                  v
           Kết quả cuối cùng
~~~

Ví dụ chuyển chuỗi số sang int:

~~~java
int total = java.util.stream.Stream.of("10", "20", "5")
    .mapToInt(Integer::parseInt)
    .sum();
~~~

**total = 35**. Ở đây:

1. **Stream.of(...)** tạo Stream<String>.
2. **Integer::parseInt** là hàm nhận String và trả **int**.
3. **mapToInt(...)** tạo IntStream, không phải Stream<Integer>.
4. **sum()** là terminal operation của IntStream.

Phương thức **mapToInt** không tự tính tổng; chính **sum()** mới tiêu thụ pipeline. Việc ánh xạ thường lazy: nếu chỉ khai báo IntStream mà chưa gọi terminal operation, parseInt chưa nhất thiết được thực thi.

### Nhắc lại quy tắc single-use

**Stream, IntStream, LongStream và DoubleStream đều chỉ được vận hành một lần.** Sau khi gọi sum() hoặc count(), không gọi terminal operation khác trên chính đối tượng stream ấy.

Sai:

~~~java
java.util.stream.IntStream ages =
    java.util.stream.Stream.of("18", "24")
        .mapToInt(Integer::parseInt);

int total = ages.sum();
long count = ages.count(); // Sai: dùng lại IntStream.
~~~

Đúng là tạo nguồn Stream mới hoặc tính nhiều thống kê trong một lượt:

~~~java
java.util.IntSummaryStatistics stats =
    java.util.stream.Stream.of("18", "24")
        .mapToInt(Integer::parseInt)
        .summaryStatistics();
~~~

Những đoạn mã trên minh họa API, chưa phải chương trình độc lập. **stats** chứa count, sum, min, max và average từ **một terminal operation**.

## 3. Chữ ký và functional interfaces

Trên **Stream<T>**, các chữ ký quan trọng là:

~~~java
IntStream mapToInt(ToIntFunction<? super T> mapper);

LongStream mapToLong(ToLongFunction<? super T> mapper);

DoubleStream mapToDouble(ToDoubleFunction<? super T> mapper);
~~~

Đây là chữ ký rút gọn nhằm giải thích API; các tên kiểu thuộc **java.util.stream** và **java.util.function**.

Mỗi functional interface có **một phương thức trừu tượng**:

~~~java
int applyAsInt(T value);

long applyAsLong(T value);

double applyAsDouble(T value);
~~~

Ví dụ ánh xạ qua lambda:

~~~java
List<String> numbers = Arrays.asList("4", "6", "9");

int sum = numbers.stream()
    .mapToInt(s -> Integer.parseInt(s))
    .sum();
~~~

Cũng có thể dùng method reference cho gọn:

~~~java
int sum = numbers.stream()
    .mapToInt(Integer::parseInt)
    .sum();
~~~

Cả hai trả **19**. Các đoạn này cần khai báo List và import Arrays, được đặt trong phương thức.

### Vì sao mapper nhận T nhưng trả primitive?

**ToIntFunction<T>** nhận một đối tượng đầu vào kiểu T và kết quả trả là **int**. Đây không phải **Function<T,Integer>** trả đối tượng Integer. Sự khác biệt giúp giảm nhu cầu boxing từng giá trị số trong những pipeline chỉ tính toán số học.

| Mapper | Kiểu đầu vào | Kiểu kết quả | Dùng với |
| --- | --- | --- | --- |
| **Function<T,R>** | T | R (reference type) | map(...) |
| **ToIntFunction<T>** | T | int | mapToInt(...) |
| **ToLongFunction<T>** | T | long | mapToLong(...) |
| **ToDoubleFunction<T>** | T | double | mapToDouble(...) |

**? super T** trong chữ ký cho phép truyền mapper xử lý T hoặc một supertype của T, phù hợp quy tắc variance của Java generics. Người dùng thường không cần khai báo wildcard thủ công khi viết lambda hoặc method reference; target typing của javac sẽ giải quyết.

## 4. mapToInt: từ đối tượng sang IntStream

Dùng **mapToInt** khi mỗi đối tượng có thể ánh xạ thành một giá trị int và bạn muốn thực hiện các phép toán số nguyên.

Các trường hợp phổ biến:

~~~java
List<String> words = Arrays.asList("Java", "API", "Stream");

int totalLength = words.stream()
    .mapToInt(String::length)
    .sum(); // 4 + 3 + 6 = 13
~~~

Hoặc:

~~~java
List<Integer> values = Arrays.asList(2, 5, 8);

int sum = values.stream()
    .mapToInt(Integer::intValue)
    .sum(); // 15
~~~

Với **List<Integer>**, bước **Integer::intValue** thực hiện unboxing thành int. Với danh sách Product, mapper có thể là **Product::getQuantity**, nếu getQuantity() trả int.

### Những terminal operations hữu ích trên IntStream

| Operation | Kiểu kết quả | Ý nghĩa |
| --- | --- | --- |
| **sum()** | int | Tổng các phần tử |
| **average()** | OptionalDouble | Trung bình nếu có phần tử |
| **min() / max()** | OptionalInt | Giá trị nhỏ nhất/lớn nhất khi có |
| **count()** | long | Số phần tử |
| **summaryStatistics()** | IntSummaryStatistics | Count, sum, min, max, average |
| **toArray()** | int[] | Gom các số nguyên thủy |
| **boxed()** | Stream<Integer> | Đổi lại object stream |
| **mapToObj(...)** | Stream<R> | Biến mỗi int thành đối tượng R |

Không phải mọi operation đều trả int. **average()** trả OptionalDouble vì trung bình có thể là số thực và luồng có thể rỗng; **count()** trả long để chứa số lượng phần tử lớn hơn phạm vi int.

## 5. mapToLong: số lượng lớn, tổng tiền theo đơn vị nguyên

Dùng **mapToLong** khi kết quả ánh xạ là long, đặc biệt với giá trị có thể vượt phạm vi int.

Ví dụ:

~~~java
List<Integer> amounts = Arrays.asList(1_000_000_000, 1_000_000_000);

long total = amounts.stream()
    .mapToLong(Integer::longValue)
    .sum(); // 2_000_000_000L
~~~

Một ứng dụng có thể dùng long để lưu **số cent** thay vì dùng double cho tiền. Chẳng hạn Order có method **getTotalCents()** trả long:

~~~java
long totalCents = orders.stream()
    .mapToLong(Order::getTotalCents)
    .sum();
~~~

Đây là đoạn minh họa; cần định nghĩa Order và orders.

### Nhân kiểu int với long: để ý nơi phép tính diễn ra

Xét đoạn mapper:

~~~java
long amount = order.getQuantity() * order.getUnitCents();
~~~

Nếu **getQuantity()** trả int và **getUnitCents()** trả long, phép nhân được thực hiện với long vì Java áp dụng binary numeric promotion. Nhưng nếu cả hai method đều trả **int**, biểu thức được nhân bằng int **trước** khi gán sang long, nên có thể tràn int.

Đúng khi cả hai đầu vào là int mà kết quả cần long:

~~~java
long amount = (long) order.getQuantity() * order.getUnitPrice();
~~~

Hoặc:

~~~java
long amount = Math.multiplyExact(
    (long) order.getQuantity(),
    (long) order.getUnitPrice());
~~~

Các đoạn này chỉ là minh họa, cần Order có method tương ứng. Việc chọn long rộng hơn **không tự bảo đảm không tràn**: long cũng có giới hạn, và **LongStream.sum()** không tự kiểm tra overflow.

## 6. mapToDouble: giá trị thực và trung bình

Dùng **mapToDouble** khi mỗi phần tử ánh xạ thành **double**, ví dụ điểm số, nhiệt độ hoặc phép đo.

~~~java
List<Double> temperatures = Arrays.asList(21.5, 22.0, 23.5);

double average = temperatures.stream()
    .mapToDouble(Double::doubleValue)
    .average()
    .orElse(Double.NaN);
~~~

Giá trị average là **22.333...** (đây chỉ là đoạn minh họa). **DoubleStream.average()** trả **OptionalDouble** vì một luồng rỗng không có giá trị trung bình.

Nếu một đối tượng SensorReading có getValue() trả double:

~~~java
double maxReading = readings.stream()
    .mapToDouble(SensorReading::getValue)
    .max()
    .orElseThrow(IllegalStateException::new);
~~~

Đây là đoạn minh họa, yêu cầu readings và SensorReading được định nghĩa. **orElseThrow(...)** phù hợp khi hợp đồng ứng dụng yêu cầu ít nhất một reading; **orElse(...)** chỉ hợp lý nếu giá trị mặc định có ý nghĩa nghiệp vụ rõ.

### Double không phải số thập phân chính xác tuyệt đối

**double** là kiểu số thực dấu chấm động nhị phân IEEE 754, nên nhiều phân số thập phân như 0.1 không được biểu diễn chính xác. DoubleStream.sum()/average() có hợp đồng riêng về độ chính xác số học, thứ tự cộng và giá trị đặc biệt như **NaN**.

Dùng **mapToDouble** cho các phép đo hoặc dữ liệu vốn có semantics floating-point. Với tiền cần độ chính xác thập phân, thường nên dùng:

- **long** biểu diễn đơn vị nhỏ nhất khi hợp đồng cho phép và phạm vi đủ lớn; hoặc
- **BigDecimal** với quy tắc scale/rounding được quy định.

Đừng mặc nhiên đổi BigDecimal sang double chỉ vì muốn gọi **DoubleStream.sum()**.

---

## 7. Chương trình hoàn chỉnh: ba phép ánh xạ trên đối tượng Product

Tạo tệp **PrimitiveMappingDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;

public class PrimitiveMappingDemo {

    static final class Product {
        private final String name;
        private final int quantity;
        private final long unitCents;
        private final double rating;

        Product(String name, int quantity, long unitCents,
                double rating) {
            this.name = name;
            this.quantity = quantity;
            this.unitCents = unitCents;
            this.rating = rating;
        }

        int getQuantity() {
            return quantity;
        }

        long getUnitCents() {
            return unitCents;
        }

        double getRating() {
            return rating;
        }
    }

    public static void main(String[] args) {
        List<Product> products = Arrays.asList(
            new Product("Pen", 2, 125L, 4.0),
            new Product("Book", 3, 425L, 5.0));

        int totalQuantity = products.stream()
            .mapToInt(Product::getQuantity)
            .sum();

        long totalCents = products.stream()
            .mapToLong(p -> p.getQuantity() * p.getUnitCents())
            .sum();

        double averageRating = products.stream()
            .mapToDouble(Product::getRating)
            .average()
            .orElse(Double.NaN);

        System.out.println("Total quantity: " + totalQuantity);
        System.out.println("Total cents: " + totalCents);
        System.out.println("Average rating: " + averageRating);

        int[] quantities = products.stream()
            .mapToInt(Product::getQuantity)
            .toArray();

        System.out.println(
            "Quantities: " + Arrays.toString(quantities));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 PrimitiveMappingDemo.java
java PrimitiveMappingDemo
~~~

Kết quả:

~~~text
Total quantity: 5
Total cents: 1525
Average rating: 4.5
Quantities: [2, 3]
~~~

**Giải thích từng pipeline:**

1. **products.stream()** tạo Stream<Product> từ List.
2. **mapToInt(Product::getQuantity)** cho các giá trị 2 và 3; sum là 5.
3. **mapToLong(...)** tạo long bằng cách nhân quantity với unitCents: 2×125 + 3×425 = 1525 cent.
4. **mapToDouble(Product::getRating)** tạo giá trị 4.0 và 5.0; trung bình là 4.5.
5. **toArray()** trên IntStream trả **int[]**, không phải Integer[].
6. Mỗi lần gọi **products.stream()** là một Stream mới. Không có pipeline nào được tiêu thụ lần thứ hai.

**Lưu ý:** tên field name được đưa vào để mô phỏng Product, nhưng không phải mọi field đều cần được ánh xạ. Chọn đúng thuộc tính cho primitive mapper, tránh trộn quantity và giá tiền.

## 8. map(...) và mapToInt(...) khác nhau ở đầu ra

Một pipeline dùng **map(String::length)**:

~~~java
Stream<Integer> boxedLengths = words.stream()
    .map(String::length);
~~~

Điều này tạo **Stream<Integer>**. Từng giá trị int trả bởi String.length() được boxing thành Integer để phù hợp với generic Stream<R>.

Còn:

~~~java
IntStream primitiveLengths = words.stream()
    .mapToInt(String::length);
~~~

tạo **IntStream**, là luồng primitive int. Điều này có thể giảm boxing khi chỉ thực hiện các phép toán số học.

| Tiêu chí | map(String::length) | mapToInt(String::length) |
| --- | --- | --- |
| Kiểu trả về | Stream<Integer> | IntStream |
| Giá trị phần tử | Integer object | int |
| Có **sum()** trực tiếp? | Không | Có |
| Có **summaryStatistics()** trực tiếp? | Không theo cùng API | Có |
| Có **collect(Collectors.toList())** trực tiếp? | Có | Không; cần boxed/mapToObj |
| Phù hợp khi | Cần đối tượng/generic pipeline | Tính toán số học primitive |

Không phải **map** là sai hoặc obsolete; đó là phép biến đổi đối tượng tổng quát. Khi đầu ra là dữ liệu số và cần tổng hợp, **mapToInt/Long/Double** thường rõ hơn.

### Khi cần quay lại đối tượng

Trên IntStream:

~~~java
Stream<Integer> integers = lengths.boxed();
~~~

Hoặc:

~~~java
Stream<String> labels = lengths.mapToObj(n -> "length=" + n);
~~~

Các đoạn này minh họa; cần một IntStream **chưa bị tiêu thụ** cho từng lời gọi. Không gọi cả hai trên cùng lengths nếu thao tác đầu đã liên kết/tiêu thụ nó trong một pipeline.

**boxed()** chuyển primitive stream thành object stream cùng wrapper tương ứng:

- IntStream.boxed() → Stream<Integer>.
- LongStream.boxed() → Stream<Long>.
- DoubleStream.boxed() → Stream<Double>.

Nếu cần String thay vì wrapper số, **mapToObj(...)** thích hợp hơn boxed() rồi map(...).

## 9. Ví dụ hoàn chỉnh: số học nguyên thủy và trở lại Stream đối tượng

Tạo tệp **MappingAndBoxingDemo.java**:

~~~java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public class MappingAndBoxingDemo {

    public static void main(String[] args) {
        List<String> words =
            Arrays.asList("Java", "API", "Stream");

        List<Integer> boxedByMap = words.stream()
            .map(String::length)
            .collect(Collectors.toList());

        int totalLength = words.stream()
            .mapToInt(String::length)
            .sum();

        IntSummaryStatistics stats = words.stream()
            .mapToInt(String::length)
            .summaryStatistics();

        List<Integer> boxedAgain = words.stream()
            .mapToInt(String::length)
            .boxed()
            .collect(Collectors.toList());

        List<String> labels = words.stream()
            .mapToInt(String::length)
            .mapToObj(n -> "#" + n)
            .collect(Collectors.toList());

        System.out.println("map: " + boxedByMap);
        System.out.println("sum: " + totalLength);
        System.out.println("boxed: " + boxedAgain);
        System.out.println("labels: " + labels);
        System.out.println("min/max: " +
            stats.getMin() + "/" + stats.getMax());
        System.out.println("average: " +
            String.format(Locale.ROOT, "%.2f",
                stats.getAverage()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 MappingAndBoxingDemo.java
java MappingAndBoxingDemo
~~~

Stdout:

~~~text
map: [4, 3, 6]
sum: 13
boxed: [4, 3, 6]
labels: [#4, #3, #6]
min/max: 3/6
average: 4.33
~~~

**Phân tích:**

- **map(String::length)** tạo Stream<Integer>; collector thu được [4, 3, 6].
- **mapToInt(String::length)** tạo IntStream; sum trực tiếp bằng 13.
- **summaryStatistics()** duyệt một lượt khác và cung cấp min=3, max=6, average=13/3.
- **boxed()** đưa các giá trị int trở lại Stream<Integer>.
- **mapToObj(...)** tạo Stream<String> chứa nhãn.
- **Locale.ROOT** giúp kết quả định dạng trung bình dùng dấu chấm như stdout nêu trên, không phụ thuộc locale mặc định của máy.

Một số người lạm dụng chuỗi **map(...).mapToInt(Integer::intValue)** dù chỉ cần String.length(). Nếu mục tiêu là tính số học, thường nên gọi **mapToInt(String::length)** ngay để tránh vòng boxing/unboxing trung gian.

---

## 10. Dùng mapper đúng kiểu: ToIntFunction, ToLongFunction, ToDoubleFunction

Các functional interfaces này có thể dùng qua lambda, method reference hoặc đối tượng function được tái sử dụng.

~~~java
ToIntFunction<String> length = String::length;

int total = words.stream()
    .mapToInt(length)
    .sum();
~~~

Đây là đoạn minh họa, cần import java.util.function.ToIntFunction và định nghĩa words. **ToIntFunction<T>** nhận một T và trả int.

Tương tự:

~~~java
ToLongFunction<String> parsedLong = Long::parseLong;

long total = numericTexts.stream()
    .mapToLong(parsedLong)
    .sum();
~~~

Và:

~~~java
ToDoubleFunction<String> parsedDouble =
    Double::parseDouble;

double total = decimalTexts.stream()
    .mapToDouble(parsedDouble)
    .sum();
~~~

Những ví dụ cần import ToLongFunction, ToDoubleFunction và khai báo collection nguồn thích hợp.

### Overload và method reference

**Integer::parseInt** có overload nhận String và String cùng radix int. Nhưng trong ngữ cảnh **ToIntFunction<String>**, compiler chọn một phương thức nhận một tham số String phù hợp.

Nếu lambda cần điều kiện, radix hoặc fallback, viết rõ:

~~~java
int result = Stream.of("FF", "10")
    .mapToInt(s -> Integer.parseInt(s, 16))
    .sum(); // 255 + 16 = 271
~~~

Khi converter có thể ném exception, method reference không tự biến lỗi thành Optional. Ví dụ **Integer.parseInt("oops")** vẫn ném NumberFormatException khi mapper thực thi.

### Generic target typing

Nếu nguồn là **Stream<? extends Number>**, một mapper có thể nhận Number và trả primitive:

~~~java
ToDoubleFunction<Number> asDouble =
    Number::doubleValue;
~~~

Rồi có thể dùng trên Stream<Number> hoặc Stream<? extends Number> theo quy tắc target typing phù hợp. **? super T** trong chữ ký mapToDouble giúp hỗ trợ những mapper xử lý loại đầu vào rộng hơn.

Đừng dùng raw types khi không cần thiết; khai báo generic rõ ràng giúp javac phát hiện mapping sai trước runtime.

## 11. Đặt filter trước hay sau mapToInt?

Về chức năng có thể có hai loại lọc:

- **Lọc đối tượng** theo thuộc tính của T trước khi chuyển đổi.
- **Lọc giá trị số** sau khi chuyển đổi.

Ví dụ minh họa:

~~~java
long count = users.stream()
    .filter(User::isActive)
    .mapToInt(User::getAge)
    .filter(age -> age >= 18)
    .count();
~~~

Đây là đoạn minh họa, cần định nghĩa User và users. filter trước dùng Predicate<User>; filter sau dùng IntPredicate.

**Khi nên lọc trước:** nếu điều kiện loại bỏ dữ liệu mà mapper xử lý tốn chi phí, lọc trước có thể tránh việc chuyển đổi không cần thiết. Chẳng hạn nếu muốn bỏ String rỗng trước khi parseInt, hãy lọc trước.

**Khi nên lọc sau:** nếu điều kiện dựa trực tiếp trên giá trị số đã chuyển đổi, dùng primitive filter để biểu đạt rõ yêu cầu.

Không được thay đổi thứ tự bừa bãi khi mapper có thể ném lỗi. Ví dụ **parseInt** sẽ thất bại với chuỗi không hợp lệ; nếu có những giá trị có thể bỏ qua được theo chính sách, chúng phải được xử lý trước mapper hoặc bằng parser trả kết quả có thể kiểm soát.

### mapToInt khác flatMapToInt

**mapToInt** ánh xạ **mỗi phần tử T thành một int**. Nếu mỗi đối tượng chứa **nhiều số** cần trải phẳng, dùng **flatMapToInt**.

Ví dụ minh họa:

~~~java
int total = groups.stream()
    .flatMapToInt(group -> group.getNumbers()
        .stream()
        .mapToInt(Integer::intValue))
    .sum();
~~~

Nếu group.getNumbers() là List<Integer>, mỗi group có thể đóng góp nhiều số, khác với mapToInt chỉ trả một int trên mỗi group.

Không dùng **mapToInt** để cố trả **int[]** hoặc **IntStream** từ mapper: chữ ký đòi kết quả **int**, không phải một luồng con hay mảng.

---

## 12. Xử lý null và chuỗi đầu vào không hợp lệ

Khi gọi:

~~~java
Stream.of("12", null, "8")
    .mapToInt(Integer::parseInt)
    .sum();
~~~

thì mapper sẽ gặp null và có thể ném lỗi. **mapToInt** không tự loại null hoặc tự sửa chuỗi không hợp lệ.

Một quy trình phù hợp với dữ liệu mà null/chuỗi trắng phải **bỏ qua**:

~~~java
int total = texts.stream()
    .filter(Objects::nonNull)
    .map(String::trim)
    .filter(s -> !s.isEmpty())
    .mapToInt(Integer::parseInt)
    .sum();
~~~

Đây là đoạn minh họa, cần java.util.Objects, texts phù hợp.

**Nhưng bỏ qua không luôn đúng.** Với các hệ thống quan trọng, dữ liệu null hoặc không hợp lệ có thể phải bị **từ chối** kèm thông báo rõ. Chính sách nên được định nghĩa trước khi viết pipeline.

Chú ý các trường hợp:

- **" 12 "**: parseInt(String) không tự bỏ dấu cách; trim() giúp nếu policy cho phép.
- **""**: parseInt ném NumberFormatException; bỏ qua hay báo lỗi tùy hợp đồng.
- **"12x"**: trim không biến thành số; vẫn không hợp lệ.
- **giá trị vượt phạm vi int**: Integer.parseInt ném NumberFormatException.
- **null Integer** khi gọi Integer::intValue: unboxing sẽ thất bại bằng NullPointerException.
- **Double.parseDouble** chấp nhận các biểu diễn đặc biệt như NaN/Infinity theo API; hãy kiểm tra nếu business rule chỉ cho phép số hữu hạn.

### Ví dụ hoàn chỉnh: pipeline dữ liệu đầu vào có điều kiện

Tạo tệp **NumericInputPipelineDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.stream.Stream;

public class NumericInputPipelineDemo {

    public static void main(String[] args) {
        List<String> raw = Arrays.asList(
            "10", null, " 20 ", "", "5");

        int sum = raw.stream()
            .filter(Objects::nonNull)
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .mapToInt(Integer::parseInt)
            .sum();

        OptionalDouble average = raw.stream()
            .filter(Objects::nonNull)
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .mapToDouble(Double::parseDouble)
            .average();

        OptionalInt emptyMax = Stream.<String>empty()
            .mapToInt(Integer::parseInt)
            .max();

        int emptySum = Stream.<String>empty()
            .mapToInt(Integer::parseInt)
            .sum();

        System.out.println("Sum: " + sum);
        System.out.println("Average: " +
            String.format(Locale.ROOT, "%.2f",
                average.orElse(0.0)));
        System.out.println("Empty max present: " +
            emptyMax.isPresent());
        System.out.println("Empty sum: " + emptySum);

        try {
            Stream.of("10", "oops")
                .mapToInt(Integer::parseInt)
                .sum();
        } catch (NumberFormatException ex) {
            System.out.println(
                "Invalid input: NumberFormatException");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 NumericInputPipelineDemo.java
java NumericInputPipelineDemo
~~~

Kết quả:

~~~text
Sum: 35
Average: 11.67
Empty max present: false
Empty sum: 0
Invalid input: NumberFormatException
~~~

**Giải thích:**

1. Pipeline bỏ null, trim khoảng trắng, bỏ chuỗi rỗng, sau đó parse "10", "20", "5".
2. Tổng là 35; trung bình là 35/3, được định dạng thành 11.67.
3. **max()** trên IntStream rỗng trả OptionalInt rỗng.
4. **sum()** trên IntStream rỗng trả **0**. Điều này không chứng minh nguồn thực sự chứa giá trị 0.
5. **Integer.parseInt("oops")** ném NumberFormatException khi terminal operation duyệt tới phần tử này; **mapToInt** không tự xử lý lỗi parse.

Nếu dữ liệu không hợp lệ phải được báo cáo theo từng dòng, một pipeline chuyển chuỗi sang đối tượng chứa kết quả và lỗi có thể phù hợp hơn việc bỏ qua bằng filter. Đừng nuốt ngoại lệ tùy tiện chỉ để tính được một tổng.

## 13. Luồng rỗng và OptionalInt, OptionalLong, OptionalDouble

Một số terminal operations trả primitive trực tiếp, trong khi những phép khác trả **Optional** chuyên dụng:

| Operation | IntStream | LongStream | DoubleStream |
| --- | --- | --- | --- |
| **sum()** | int, rỗng → 0 | long, rỗng → 0L | double, rỗng → 0.0 |
| **count()** | long | long | long |
| **average()** | OptionalDouble | OptionalDouble | OptionalDouble |
| **min()** | OptionalInt | OptionalLong | OptionalDouble |
| **max()** | OptionalInt | OptionalLong | OptionalDouble |
| **findFirst()** | OptionalInt | OptionalLong | OptionalDouble |
| **summaryStatistics()** | IntSummaryStatistics | LongSummaryStatistics | DoubleSummaryStatistics |

Điểm cần nhớ: một **OptionalDouble rỗng** không phải là một trung bình bằng 0. Nếu bạn dùng **orElse(0.0)**, đó là **chính sách fallback của ứng dụng**, không phải định nghĩa toán học của trung bình tập rỗng.

Ví dụ:

~~~java
OptionalDouble avg = Stream.<String>empty()
    .mapToInt(String::length)
    .average();

System.out.println(avg.isPresent()); // false
~~~

Đây là đoạn minh họa cần import OptionalDouble và Stream.

Nếu ứng dụng bắt buộc có ít nhất một phần tử, có thể dùng **orElseThrow(...)** với exception phù hợp. Với hệ thống phân tích dữ liệu, đôi khi nên giữ **OptionalDouble** để caller tự quyết định trường hợp không có dữ liệu.

### Những trường hợp nguồn chứa null khi đếm

Ví dụ **Stream.of((String) null).mapToInt(...)** có một phần tử null, nhưng mapper có thể gây lỗi khi được thực thi. **Stream.empty()** thì có **không phần tử**. Đừng nhầm luồng chứa null với luồng rỗng.

---

## 14. Tràn số: chuyển sang long đúng lúc

**IntStream.sum()** dùng số học int theo Java. Nếu tổng vượt phạm vi **Integer.MIN_VALUE .. Integer.MAX_VALUE**, kết quả có thể bị **overflow**, không tự ném exception.

Ví dụ:

~~~java
List<Integer> values =
    Arrays.asList(Integer.MAX_VALUE, 1);

int wrapped = values.stream()
    .mapToInt(Integer::intValue)
    .sum();
~~~

Giá trị **wrapped** là **Integer.MIN_VALUE** (-2147483648). Nếu mục tiêu là tổng toán học 2147483648, cần tăng kiểu trước khi cộng:

~~~java
long exact = values.stream()
    .mapToLong(Integer::longValue)
    .sum();
~~~

**exact** bằng 2147483648L.

### Chuyển kiểu sau sum là quá muộn

Sai:

~~~java
long stillWrong = (long) values.stream()
    .mapToInt(Integer::intValue)
    .sum();
~~~

Tổng đã tràn trong int trước, rồi mới được cast sang long; giá trị đã sai không thể phục hồi.

Đúng:

~~~java
long total = values.stream()
    .mapToLong(Integer::longValue)
    .sum();
~~~

Nếu chính các giá trị long cũng có thể tạo tổng vượt long, LongStream.sum() cũng có nguy cơ overflow. Khi cần kiểm tra:

~~~java
long checked = values.stream()
    .mapToLong(Integer::longValue)
    .reduce(0L, Math::addExact);
~~~

Đây là đoạn minh họa với values kiểu List<Integer>; **Math.addExact(long,long)** ném ArithmeticException nếu tổng vượt long. Nhưng trong **parallel stream**, quá trình reduce phải được cân nhắc với hợp đồng associativity và xử lý exception của phép toán; ưu tiên đơn giản, tuần tự và kiểm thử kỹ nếu tài chính hoặc số học cần exactness.

### Nhân trước khi ánh xạ

Nếu cần tính quantity × unitPrice mà cả hai là int, dùng **(long) quantity * unitPrice** trước khi mapToLong trả kết quả. Chỉ thay kiểu trả về của mapper sau một phép nhân int đã overflow sẽ không sửa lỗi.

## 15. BigDecimal cho tiền và giới hạn của double

**DoubleStream.sum()** rất hữu ích cho phép đo, nhưng không bảo đảm tính chính xác thập phân đối với các giá trị như 0.10 và 0.20. Khi dùng tiền, cân nhắc **BigDecimal**.

Ví dụ:

~~~java
BigDecimal total = money.stream()
    .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

Đây là đoạn minh họa, cần import BigDecimal và có danh sách money. **BigDecimal("0.10")** và **BigDecimal("0.20")** cộng đúng thành **0.30** theo số học thập phân.

Lưu ý:

- Nên tạo BigDecimal từ **chuỗi thập phân** hoặc các factory phù hợp khi cần giữ đúng giá trị decimal, không tùy tiện dùng **new BigDecimal(0.1)**.
- BigDecimal không phải primitive stream; nó được xử lý trong **Stream<BigDecimal>** với reduce hoặc collector thích hợp.
- Nếu miền nghiệp vụ dùng long theo đơn vị cent, **mapToLong** cũng có thể rất tốt khi các phép nhân/cộng được thiết kế tránh overflow.
- Đừng đổi BigDecimal thành double rồi khẳng định tổng tiền luôn chính xác.

### Ví dụ hoàn chỉnh: overflow và tiền

Tạo tệp **NumericOverflowDemo.java**:

~~~java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;

public class NumericOverflowDemo {

    public static void main(String[] args) {
        List<Integer> values =
            Arrays.asList(Integer.MAX_VALUE, 1);

        int wrapped = values.stream()
            .mapToInt(Integer::intValue)
            .sum();

        long widened = values.stream()
            .mapToLong(Integer::longValue)
            .sum();

        System.out.println("Int sum: " + wrapped);
        System.out.println("Long sum: " + widened);

        try {
            Math.toIntExact(widened);
        } catch (ArithmeticException ex) {
            System.out.println(
                "Narrowing: ArithmeticException");
        }

        List<BigDecimal> prices = Arrays.asList(
            new BigDecimal("0.10"),
            new BigDecimal("0.20"));

        BigDecimal exactMoney = prices.stream()
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        System.out.println("Exact money: " + exactMoney);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 NumericOverflowDemo.java
java NumericOverflowDemo
~~~

Stdout:

~~~text
Int sum: -2147483648
Long sum: 2147483648
Narrowing: ArithmeticException
Exact money: 0.30
~~~

**Phân tích:** int sum đã tràn; mapToLong giúp cộng bằng long; Math.toIntExact chỉ cho phép thu hẹp nếu giá trị nằm trong int. BigDecimal thực hiện phép cộng decimal đúng với hai input string.

**Không mở rộng kết luận:** mapToLong không tự giải quyết mọi bài toán về overflow hoặc precision. Nó chỉ đưa ra kiểu số nguyên có miền lớn hơn int.

---

## 16. Chuyển đổi giữa các primitive streams

Sau khi đã có IntStream, LongStream hoặc DoubleStream, bạn có thể tiếp tục biến đổi bằng các operation chuyên biệt.

Các API quen thuộc:

- **IntStream.map(IntUnaryOperator)**: int → int.
- **IntStream.mapToLong(IntToLongFunction)**: int → long.
- **IntStream.mapToDouble(IntToDoubleFunction)**: int → double.
- **IntStream.mapToObj(IntFunction<R>)**: int → R.
- **IntStream.asLongStream()** và **asDoubleStream()**: mở rộng giá trị sang primitive stream loại khác.
- **LongStream.mapToInt(LongToIntFunction)** hoặc **mapToDouble(LongToDoubleFunction)**.
- **DoubleStream.mapToInt(DoubleToIntFunction)** hoặc **mapToLong(DoubleToLongFunction)**.
- **boxed()**: chuyển primitive stream thành Stream wrapper.

Ví dụ:

~~~java
long total = Stream.of("2", "5", "8")
    .mapToInt(Integer::parseInt)
    .asLongStream()
    .sum();
~~~

**total = 15L**. Không có boxing bắt buộc chỉ để chuyển IntStream sang LongStream.

### Chuyển từ double sang int có thể mất dữ liệu

**DoubleStream.mapToInt(d -> (int) d)** thực hiện **narrowing conversion** theo Java: phần thập phân bị cắt về 0, giá trị ngoài phạm vi/NaN có những quy tắc chuyển đổi đặc biệt. Đây không phải phép làm tròn toán học gần nhất.

Nếu muốn rounding cụ thể, hãy dùng **Math.round(...)** và xác nhận kiểu/phạm vi kết quả:

~~~java
long rounded = Math.round(3.6); // 4L
~~~

Không trộn phép làm tròn với ép kiểu thu hẹp nếu dữ liệu nhạy cảm về độ chính xác.

### mapToObj khác boxed

- **boxed()** giữ giá trị số nhưng đưa vào wrapper: 3 → Integer(3).
- **mapToObj(...)** cho phép tạo bất kỳ đối tượng R: 3 → "3 items", một DTO, một record (nếu đang dùng JDK mới) hoặc một domain object.

Trong bài học Java 8, những ví dụ runnable dùng class thông thường thay vì record để giữ khả năng biên dịch ở JDK 8.

## 17. Ví dụ hoàn chỉnh: nối các phép biến đổi số

Tạo tệp **PrimitiveConversionDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public class PrimitiveConversionDemo {

    public static void main(String[] args) {
        List<String> texts = Arrays.asList("2", "5", "8");

        long sumAsLong = texts.stream()
            .mapToInt(Integer::parseInt)
            .asLongStream()
            .sum();

        double averageAsDouble = texts.stream()
            .mapToLong(Long::parseLong)
            .asDoubleStream()
            .average()
            .orElse(Double.NaN);

        List<Integer> squares = texts.stream()
            .mapToInt(Integer::parseInt)
            .map(n -> n * n)
            .boxed()
            .collect(Collectors.toList());

        List<String> formatted = texts.stream()
            .mapToDouble(Double::parseDouble)
            .mapToObj(n ->
                String.format(Locale.ROOT, "%.1f", n))
            .collect(Collectors.toList());

        System.out.println("Long sum: " + sumAsLong);
        System.out.println("Double average: " +
            averageAsDouble);
        System.out.println("Squares: " + squares);
        System.out.println("Formatted: " + formatted);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 PrimitiveConversionDemo.java
java PrimitiveConversionDemo
~~~

Stdout:

~~~text
Long sum: 15
Double average: 5.0
Squares: [4, 25, 64]
Formatted: [2.0, 5.0, 8.0]
~~~

**Giải thích:**

1. **mapToInt(Integer::parseInt)** chuyển String thành int; **asLongStream()** mở rộng thành long rồi tính tổng.
2. **mapToLong(Long::parseLong)** đọc String thành long; **asDoubleStream()** tạo double primitive values, average cho 5.0.
3. **map(n -> n*n)** trên IntStream là **IntStream.map**, vẫn trả IntStream; sau **boxed()**, collect cho List<Integer>.
4. **mapToDouble(Double::parseDouble)** tạo DoubleStream; **mapToObj** định dạng từng số thành String dùng Locale.ROOT.
5. Tất cả pipeline đều được tạo mới từ **texts.stream()**, không tái sử dụng một Stream đã có terminal operation.

## 18. Nhìn lại Stream.map và các phương thức mapTo* trên primitive stream

Đây là điểm phân biệt quan trọng khi đọc code:

~~~java
Stream<String> source = Stream.of("10", "20");
IntStream ints = source.mapToInt(Integer::parseInt);
~~~

Sau dòng thứ hai, đối tượng được giữ trong biến ints là **IntStream**. Nếu muốn chuyển **int thành long**, bạn không gọi **ints.mapToLong(Integer::longValue)** vì kiểu đầu vào giờ là primitive int, không phải Integer object. Trên IntStream, mapper tương ứng nhận **int**.

Dùng:

~~~java
LongStream widened = ints.mapToLong(i -> (long) i);
~~~

Hoặc đơn giản:

~~~java
LongStream widened = ints.asLongStream();
~~~

Đây là các đoạn minh họa thay thế: **không dùng lại cùng ints cho cả hai nhánh**. Việc gọi một intermediate operation có thể liên kết một Stream vào pipeline; tạo hai nhánh từ cùng một Stream không phải mô hình hợp lệ.

### Bảng chọn API theo kiểu hiện tại

| Kiểu nguồn hiện tại | Muốn kết quả | Chọn |
| --- | --- | --- |
| Stream<T> | Stream<R> | map(Function<T,R>) |
| Stream<T> | IntStream | mapToInt(ToIntFunction<T>) |
| Stream<T> | LongStream | mapToLong(ToLongFunction<T>) |
| Stream<T> | DoubleStream | mapToDouble(ToDoubleFunction<T>) |
| IntStream | IntStream | map(IntUnaryOperator) |
| IntStream | LongStream | mapToLong(IntToLongFunction) / asLongStream() |
| IntStream | DoubleStream | mapToDouble(IntToDoubleFunction) / asDoubleStream() |
| IntStream | Stream<R> | mapToObj(IntFunction<R>) |
| LongStream | Stream<Long> | boxed() |
| DoubleStream | Stream<Double> | boxed() |

Đây là lý do method reference cần có **chữ ký tương thích với functional interface của bước pipeline đang gọi**. Thay đổi từ Stream<Integer> sang IntStream khiến kiểu đầu vào của mapper chuyển từ Integer object sang int primitive.

---

## 19. Hiệu năng: lợi ích primitive stream và những giới hạn

Primitive streams giúp tránh **boxing/unboxing** không cần thiết trong các bước xử lý số, đặc biệt khi thao tác trên nhiều phần tử.

Ví dụ:

~~~java
int sum = values.stream()
    .mapToInt(Integer::intValue)
    .sum();
~~~

so với pipeline boxed tổng quát:

~~~java
int sum = values.stream()
    .reduce(0, Integer::sum);
~~~

Hai đoạn là lựa chọn thay thế, giả định values là List<Integer> không chứa null. Đoạn đầu rõ ý định chuyển về primitive rồi tính tổng. Đoạn sau vẫn hợp lệ nhưng dùng API generic reduce và có thể phát sinh thao tác boxing/unboxing.

**Không khẳng định mapToInt luôn nhanh hơn trong mọi hoàn cảnh.** Hiệu năng phụ thuộc nguồn dữ liệu, JIT, số lượng phần tử, độ phức tạp mapper, cách collect, việc dùng parallel và cấu trúc bộ nhớ. Hãy đo benchmark thực tế khi tối ưu hóa quan trọng.

Các yếu tố khác:

- Nếu đầu vào vốn là List<Integer>, những Integer objects đã tồn tại; mapToInt chỉ tránh boxing ở **các bước số học tiếp theo**, không làm dữ liệu đầu vào magically primitive.
- Nếu dữ liệu vốn nằm trong **int[]**, dùng **Arrays.stream(intArray)** trả IntStream trực tiếp, có thể đơn giản hơn tạo Stream<Integer>.
- **IntStream.range(...)** cung cấp dãy int theo khoảng; không cần tạo danh sách Integer chỉ để thực hiện vòng lặp số học.
- Với dữ liệu quá nhỏ, code rõ ràng và đúng hợp đồng thường quan trọng hơn chi phí boxing vi mô.

### Parallel không tự loại mọi chi phí

Có thể dùng **parallelStream().mapToInt(...).sum()**, nhưng không mặc nhiên nhanh hơn sequential. Mapper cần tránh mutable shared state và side effects; sự phân chia công việc, chi phí kết hợp và kích thước nguồn quyết định hiệu quả.

Với số thực, giảm/thay đổi thứ tự cộng trong xử lý song song có thể làm kết quả double khác biệt do tính không kết hợp tuyệt đối của floating-point arithmetic. Không dùng parallel như một cách bảo đảm kết quả double chính xác hơn.

## 20. Tính lazy và side effects của mapper

Một intermediate operation như **mapToInt** thường **lazy**:

~~~java
IntStream lengths = words.stream()
    .mapToInt(word -> {
        System.out.println("Mapping: " + word);
        return word.length();
    });
~~~

Chưa có terminal operation, mapper có thể chưa được gọi. Khi gọi sum()/toArray()/forEach(...), pipeline mới được tiêu thụ.

Tuy nhiên không nên dùng side effect trong mapper như một phần bắt buộc của business logic. Một số terminal operations có thể tối ưu dựa trên kích thước nguồn và bỏ qua việc chạy mapper nếu không cần đánh giá giá trị để sinh kết quả; cũng có short-circuit operations khiến không phải mọi phần tử đều được xử lý.

**Ví dụ cần tránh:** dùng mapToInt chỉ để ghi log cho từng phần tử, sau đó gọi count() và kỳ vọng mọi dòng log đều xuất hiện. Một pipeline có thể tối ưu số phần tử đầu ra mà không cần thực thi mapper trong một số ngữ cảnh hợp lệ.

Hãy ưu tiên **pure mapper**: cùng input cho cùng output, không sửa state dùng chung, không phụ thuộc thứ tự chạy. Nếu thực sự cần side effect, chọn một terminal operation phù hợp với yêu cầu và hiểu quy tắc thứ tự của nó.

## 21. Hợp đồng số học của double: NaN, Infinity và precision

Trong DoubleStream, các giá trị có thể gồm **NaN**, **positive Infinity** và **negative Infinity**. Các terminal operations như sum(), min(), max(), average() tuân theo hợp đồng số học floating-point của Java, không phải luôn giống quy tắc số thực toán học thông thường.

### NaN

Nếu mapper trả **Double.NaN**, kết quả thống kê liên quan có thể mang NaN theo hợp đồng API. Nếu ứng dụng không cho phép NaN, lọc hoặc từ chối rõ ràng:

~~~java
double total = readings.stream()
    .mapToDouble(SensorReading::getValue)
    .filter(Double::isFinite)
    .sum();
~~~

Đây là đoạn minh họa và **Double.isFinite(double)** có từ Java 8. Lọc bỏ NaN/Infinity là một **chính sách dữ liệu**, không tự động đúng cho mọi hệ thống. Nếu giá trị bất thường phải được báo lỗi thay vì bỏ qua, hãy validate trước.

### Floating-point summation

Do làm tròn nhị phân, **DoubleStream.sum()** có thể khác một tổng toán học thập phân chính xác. Đừng kiểm tra double bằng **==** khi cần so sánh gần đúng với tolerance có ý nghĩa. Với tiền, dùng BigDecimal hoặc integer minor units như đã nêu.

### Khác nhau giữa dữ liệu "không có" và NaN

- **average()** trên luồng rỗng trả **OptionalDouble.empty()**.
- **average()** trên luồng có dữ liệu NaN có thể trả **OptionalDouble có giá trị NaN**.

Hai tình huống không đồng nghĩa. **isPresent()** không phải phép kiểm tra dữ liệu hữu hạn; cần kiểm tra **Double.isFinite(...)** nếu hợp đồng yêu cầu.

---

## 22. Bảng so sánh ba phép ánh xạ

| Nội dung | mapToInt | mapToLong | mapToDouble |
| --- | --- | --- | --- |
| Đầu vào | Stream<T> | Stream<T> | Stream<T> |
| Mapper | ToIntFunction<T> | ToLongFunction<T> | ToDoubleFunction<T> |
| Mapper trả | int | long | double |
| Kết quả | IntStream | LongStream | DoubleStream |
| sum() trả | int | long | double |
| average() trả | OptionalDouble | OptionalDouble | OptionalDouble |
| min/max trả | OptionalInt | OptionalLong | OptionalDouble |
| toArray() trả | int[] | long[] | double[] |
| boxed() trả | Stream<Integer> | Stream<Long> | Stream<Double> |
| Ứng dụng ví dụ | Length, quantity, age | Id numeric, count lớn, cent | Temperature, score, measurement |
| Rủi ro đặc thù | Tràn int | Tràn long | Precision, NaN, Infinity |
| Có thể dùng lại sau terminal? | Không | Không | Không |

**Lựa chọn kiểu không chỉ dựa trên “kiểu nào lớn hơn”.** Chọn theo miền giá trị, cách đo, yêu cầu chính xác và hợp đồng nghiệp vụ.

## 23. Những lỗi phổ biến

| Lỗi | Vì sao xảy ra | Cách xử lý |
| --- | --- | --- |
| Dùng **map(String::length)** rồi gọi sum() | map trả Stream<Integer>, không có sum() trực tiếp | Dùng mapToInt |
| Dùng mapToInt nhưng mapper trả String | ToIntFunction phải trả int | Chuyển đổi/parse thành int |
| Dùng **mapToInt(Integer::parseInt)** với null | Mapper có thể gặp null | Validate/filter theo chính sách |
| Dùng parseInt trên chuỗi sai | NumberFormatException | Làm sạch/kiểm tra đầu vào, báo lỗi rõ |
| Mong mapToInt tự chạy ngay | Intermediate thường lazy | Cần terminal operation |
| Gọi hai terminal operations trên cùng IntStream | Stream single-use | Tạo Stream mới hoặc summaryStatistics |
| Cộng các giá trị lớn bằng IntStream.sum() | Int overflow | Widen sang long **trước** sum |
| Cộng long quá phạm vi | LongStream.sum cũng có thể overflow | Kiểm tra range/Math.addExact/BigInteger |
| Lấy **average().getAsDouble()** của luồng rỗng | OptionalDouble rỗng | Kiểm tra isPresent hoặc fallback có chủ đích |
| Dùng orElse(0) rồi coi trung bình rỗng là 0 thật | “Không có dữ liệu” khác giá trị 0 | Giữ Optional khi cần |
| Dùng double cho tiền chính xác decimal | Floating-point rounding | BigDecimal hoặc long minor units |
| Dùng **Double::isFinite** để âm thầm lọc mọi dữ liệu xấu | Có thể che giấu data issue | Chọn reject hay filter rõ ràng |
| Dùng **(int) doubleValue** rồi cho là Math.round | Cast cắt phần thập phân, có quy tắc biên | Dùng API rounding phù hợp |
| Dùng boxed() rồi quên boxing | Đưa primitive về object | Chỉ boxed khi cần Stream wrapper |
| Dùng mapToInt để trả nhiều số trên một item | mapToInt là one-to-one | flatMapToInt nếu cần flatten |
| Dùng parallel mà mapper sửa shared List | Data race, side effects | Dùng pure mapper/collector phù hợp |
| Dùng count() để bảo đảm mapper side-effect chạy | Có thể tối ưu, bỏ qua mapper | Không dùng side effect như invariant |
| Lấy toArray rồi gán Integer[] | IntStream.toArray trả int[] | Dùng int[] hoặc boxed |
| Dùng mapper thu hẹp long sang int không kiểm tra | Có thể mất dữ liệu | Dùng Math.toIntExact khi cần |
| Coi mapToDouble luôn tạo số chính xác | double vẫn là floating-point | Định nghĩa tolerance/BigDecimal |

## 24. Bài tập thực hành có đáp án

### Bài 1 — Chuyển độ dài String

Cho List<String> words = Arrays.asList("A","BB","CCC"). Dùng một pipeline tính tổng độ dài.

**Đáp án:**

~~~java
int total = words.stream()
    .mapToInt(String::length)
    .sum();
~~~

**total = 6**. Đoạn này cần import List/Arrays và khai báo trong method.

### Bài 2 — Tại sao map không có sum?

**Stream<String>.map(String::length)** có kiểu trả về gì?

**Đáp án:** Stream<Integer>. Dùng **mapToInt(String::length)** để nhận IntStream và gọi sum() trực tiếp.

### Bài 3 — Tính tổng tiền cent

Order có method **long getTotalCents()**. Tính tổng:

~~~java
long total = orders.stream()
    .mapToLong(Order::getTotalCents)
    .sum();
~~~

**Đáp án:** đây là đúng hướng nếu dữ liệu cent nằm trong miền long và hợp đồng cộng không bị overflow. Nếu dữ liệu có nguy cơ vượt long, cần cơ chế số học an toàn hơn.

### Bài 4 — Trung bình không có phần tử

Điều gì xảy ra với:

~~~java
OptionalDouble average = Stream.<String>empty()
    .mapToDouble(Double::parseDouble)
    .average();
~~~

**Đáp án:** OptionalDouble.empty(). Không nên gọi getAsDouble() mà không kiểm tra. Nếu dùng orElse(0.0), đó là chính sách fallback của ứng dụng.

### Bài 5 — Int overflow

Cho **Integer.MAX_VALUE** và 1. IntStream.sum() sẽ trả bao nhiêu?

**Đáp án:** **-2147483648** do overflow của số học int. Dùng mapToLong(Integer::longValue) trước sum để được **2147483648L**.

### Bài 6 — Parse chuỗi rỗng

Vì sao pipeline **Stream.of("12","","4").mapToInt(Integer::parseInt).sum()** có thể lỗi?

**Đáp án:** Integer.parseInt("") ném NumberFormatException. Xác định rõ trường hợp rỗng nên được bỏ qua, dùng giá trị mặc định hay báo lỗi.

### Bài 7 — mapToInt hay flatMapToInt?

Một Batch chứa List<Integer> items và bạn muốn stream tất cả số của nhiều Batch. Dùng gì?

**Đáp án:** **flatMapToInt(batch -> batch.getItems().stream().mapToInt(Integer::intValue))** nếu mỗi Batch đóng góp nhiều số. mapToInt chỉ trả một int cho mỗi Batch.

### Bài 8 — Boxing

**IntStream.boxed()** trả kiểu gì?

**Đáp án:** **Stream<Integer>**. Dùng khi cần collector hoặc API generic trên wrapper objects. Nếu chỉ cần sum/max/min, giữ primitive stream.

### Bài 9 — Định dạng kết quả double

Vì sao các phép cộng double không luôn trả đúng số thập phân lý tưởng?

**Đáp án:** biểu diễn floating-point nhị phân có sai số làm tròn. Với tiền chính xác, cân nhắc BigDecimal hoặc long theo minor unit thay vì mapToDouble.

### Bài 10 — Mutable state và parallel

Một mapper tăng một shared int variable trong **parallelStream().mapToInt(...)** có phải cách đáng tin để đếm phần tử?

**Đáp án:** không. Có nguy cơ data race và những vấn đề về side effects/optimization. Dùng **count()** hoặc collector/reduction phù hợp.

### Bài 11 — Hai lần sum và average

Bạn tạo **IntStream stream = products.stream().mapToInt(Product::getQuantity)** rồi gọi sum() và average() trên cùng stream. Hợp lệ không?

**Đáp án:** không. IntStream đã bị tiêu thụ bởi sum(). Dùng **summaryStatistics()** trong một lượt hoặc tạo Stream mới cho lượt thứ hai.

### Bài 12 — Lọc theo giá trị số

Muốn đếm người dùng active và từ 18 tuổi:

~~~java
long count = users.stream()
    .filter(User::isActive)
    .mapToInt(User::getAge)
    .filter(age -> age >= 18)
    .count();
~~~

**Đáp án:** filter đầu xét đối tượng; mapToInt chuyển sang age int; filter sau xét int; count trả long. Đoạn minh họa cần User/users được khai báo.

### Bài 13 — Long sang int

Cần chuyển một long về int nhưng muốn phát hiện overflow. Cách nào rõ hơn cast?

**Đáp án:** **Math.toIntExact(longValue)** ném ArithmeticException khi giá trị nằm ngoài int.

### Bài 14 — NaN

Một phép đo có thể là Double.NaN. **DoubleStream.average().isPresent()** có đủ để xác nhận đó là giá trị hữu hạn không?

**Đáp án:** không. OptionalDouble có thể có giá trị NaN. Nếu cần số hữu hạn, kiểm tra **Double.isFinite(...)** theo chính sách dữ liệu.

### Bài 15 — Nhìn kiểu API

Bạn đã có **IntStream**. Có nên gọi **mapToInt** của Stream<T> để nhân mỗi giá trị với 2 không?

**Đáp án:** không cần. Trên IntStream, dùng **map(n -> n * 2)**; nó vẫn trả IntStream.

## 25. Checklist thiết kế pipeline số học

**Trước khi ánh xạ:**

- Đầu vào đang là Stream<T>, IntStream, LongStream hay DoubleStream?
- Một phần tử đầu vào được ánh xạ thành **một** số hay **nhiều** số?
- Kiểu đúng của giá trị đầu ra là int, long, double hay BigDecimal?
- Có null, chuỗi trắng, chuỗi lỗi hoặc số vượt phạm vi không?
- Mapper có thể ném exception hoặc mang side effect không?

**Trong pipeline:**

- Dùng mapToInt/Long/Double với mapper trả đúng primitive.
- Đặt filter ở vị trí phù hợp để loại dữ liệu theo chính sách.
- Không tái sử dụng Stream hoặc primitive stream sau terminal operation.
- Không dùng boxing trung gian nếu mục tiêu chỉ là tổng hợp số.
- Nếu cần nhiều thống kê trong một lượt, cân nhắc summaryStatistics().
- Cẩn thận với chuyển kiểu trước/sau phép toán có thể overflow.
- Tránh shared mutable state trong parallel stream.

**Sau khi tính:**

- Kết quả rỗng được xử lý đúng qua OptionalInt/Long/Double?
- Có cần kiểm tra NaN/Infinity cho dữ liệu double?
- Số tiền có cần decimal exactness không?
- Có cần chuyển về Stream object bằng boxed/mapToObj?
- stdout và test có dùng locale phù hợp nếu định dạng số?
- Test các trường hợp: không dữ liệu, một phần tử, null, input lỗi, giá trị biên int/long và precision của double.

## Tổng kết

**mapToInt**, **mapToLong** và **mapToDouble** là các intermediate operations trên **Stream<T>** để ánh xạ mỗi đối tượng thành một giá trị primitive, lần lượt tạo **IntStream**, **LongStream** và **DoubleStream**. Chúng dùng **ToIntFunction**, **ToLongFunction** và **ToDoubleFunction**, phù hợp với lambda hoặc method reference có kiểu trả về tương ứng.

Primitive streams giúp code tính tổng, trung bình, cực trị và thống kê rõ ràng, đồng thời tránh boxing không cần thiết ở nhiều bước số học. Tuy nhiên, bạn vẫn cần chọn đúng miền số: **int** có thể overflow, **long** cũng có giới hạn, **double** có sai số và giá trị đặc biệt. Những operation trả **Optional** biểu diễn tình huống không có dữ liệu; không tự gán cho nó một ý nghĩa nghiệp vụ không được quy định.

Hãy dùng **mapToInt** khi cần int, **mapToLong** cho long, **mapToDouble** cho double; giữ primitive stream nếu tiếp tục tính số, dùng **boxed()/mapToObj()** khi cần quay lại đối tượng và dùng **flatMapToInt** khi mỗi đầu vào chứa nhiều số. Cuối cùng, nhớ rằng các pipeline vẫn **lazy**, **single-use**, không tự validate dữ liệu đầu vào và không biến các phép tính sai miền số thành chính xác.