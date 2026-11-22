# counting(), summingInt() và averagingDouble() trong Java Collectors

## 1. Mục tiêu bài học

Trong một ứng dụng có danh sách sản phẩm, hóa đơn hay điểm số, chúng ta thường cần ba loại thống kê cơ bản:

- **Đếm** có bao nhiêu phần tử đáp ứng điều kiện.
- **Cộng** một đại lượng nguyên từ từng phần tử, chẳng hạn số lượng hàng bán.
- **Tính trung bình** một đại lượng số, chẳng hạn giá bán trung bình của mỗi loại sản phẩm.

Java cung cấp ba factory method trong **java.util.stream.Collectors** để tạo **Collector** tương ứng:

~~~java
Collectors.counting()
Collectors.summingInt(ToIntFunction<? super T> mapper)
Collectors.averagingDouble(ToDoubleFunction<? super T> mapper)
~~~

Các Collector này hữu ích khi kết hợp với **Stream.collect(...)**, đặc biệt làm **downstream collector** trong **groupingBy**, **partitioningBy**, **mapping**, **filtering** hay **teeing**.

Sau bài học, bạn có thể:

1. Hiểu kiểu trả về của từng Collector và cách sử dụng trực tiếp.
2. Nhận biết trường hợp nên dùng **Stream.count()**, **IntStream.sum()** hoặc **average()** thay vì Collector.
3. Tính toán theo từng nhóm bằng **groupingBy(key, downstream)**.
4. Phân biệt tổng giá trị với trung bình trên số phần tử, và xử lý đúng **stream rỗng**.
5. Tránh tràn **int**, nhầm đơn vị tính, dữ liệu null, sai số số thực và giả định sai về thứ tự.
6. Thiết kế các mapper thuần, dễ kiểm thử và sử dụng an toàn trong parallel stream.

## 2. Collector là gì?

**Collector<T, A, R>** mô tả cách thu thập các phần tử kiểu T thành kết quả R, thông qua trạng thái tích lũy trung gian A. API Collector xác định các thành phần như **supplier**, **accumulator**, **combiner**, **finisher** và **characteristics**.

Thông thường bạn không cần tự triển khai Collector. Java có các factory method trong **Collectors**.

Ví dụ:

~~~java
List<String> values = List.of("Java", "Go", "C");

long total = values.stream()
        .collect(Collectors.counting());

System.out.println(total); // 3
~~~

Đây là mảnh ghép minh họa trong phương thức có import **List** và **Collectors**.

Luồng dữ liệu:

~~~text
List<String> (nguồn)
    |
    v
stream()
    |
    v
filter(...) / map(...) (nếu cần)
    |
    v
collect(Collectors.counting())
    |
    v
Long (kết quả)
~~~

**collect** là terminal operation: khi được gọi, pipeline được đánh giá đủ để trả kết quả. **Collectors.counting()** chỉ tạo ra một Collector, không tự bắt đầu duyệt dữ liệu.

### 2.1. Ba Collector cùng mô tả một kiểu tổng hợp

| Collector | Giá trị đầu vào cần thiết | Kiểu kết quả | Stream rỗng |
| --- | --- | --- | --- |
| **counting()** | Chỉ cần có phần tử | **Long** | **0L** |
| **summingInt(mapper)** | Mapper tạo **int** | **Integer** | **0** |
| **averagingDouble(mapper)** | Mapper tạo **double** | **Double** | **0.0** |

Lưu ý: Các kiểu hiển thị bên trên là kết quả **boxed** của Collector khi dùng với Stream<T>; khi gán cho biến nguyên thủy, Java thực hiện unboxing nếu phù hợp.

**Stream.count()** trả trực tiếp primitive **long**. **IntStream.sum()** trả primitive **int**. **DoubleStream.average()** trả **OptionalDouble**. Đó là các API khác nhau; không nên đoán chúng đều có cùng kiểu hoặc cùng cách xử lý tập rỗng.

## 3. counting(): đếm số phần tử

Factory method:

~~~java
static <T> Collector<T, ?, Long> counting()
~~~

Dùng:

~~~java
long numberOfWords = List.of("a", "b", "c").stream()
        .collect(Collectors.counting());

System.out.println(numberOfWords); // 3
~~~

**counting** đếm **số phần tử thực sự đi vào collector**, không tự phân biệt nội dung của phần tử.

### 3.1. Đếm sau khi filter

~~~java
List<Integer> values = List.of(-2, 0, 3, 4, 7);

long positives = values.stream()
        .filter(value -> value > 0)
        .collect(Collectors.counting());

System.out.println(positives); // 3
~~~

Ở đây ba giá trị **3, 4, 7** đi qua filter, nên kết quả đếm bằng 3.

**Đếm phần tử** khác với **đếm số loại giá trị**. Nếu muốn đếm những giá trị phân biệt, cần làm rõ semantics và có thể dùng **distinct()** trước counting:

~~~java
long unique = List.of("A", "A", "B").stream()
        .distinct()
        .collect(Collectors.counting());

System.out.println(unique); // 2
~~~

### 3.2. counting và Stream.count()

Nếu chỉ cần số phần tử của toàn stream, biểu thức:

~~~java
long n = source.stream().count();
~~~

thường ngắn gọn hơn:

~~~java
long n = source.stream().collect(Collectors.counting());
~~~

Cả hai trả số lượng phần tử theo hợp đồng. **counting()** đặc biệt có giá trị khi làm downstream, ví dụ đếm từng nhóm:

~~~java
Map<String, Long> counts = items.stream()
        .collect(Collectors.groupingBy(
                Item::category,
                Collectors.counting()));
~~~

Đây là mảnh ghép có kiểu **Item** và biến **items** phù hợp; chương trình hoàn chỉnh sẽ được trình bày bên dưới.

### 3.3. Không dùng callback để suy luận số lần duyệt

**Stream.count()** có thể tận dụng kích thước đã biết của nguồn mà không thực thi một số bước trước đó khi kết quả đếm không bị ảnh hưởng. Ví dụ:

~~~java
long n = List.of(1, 2, 3).stream()
        .peek(System.out::println)
        .count();
~~~

Không được coi ba dòng in từ **peek** là bắt buộc. Kết quả đếm vẫn là 3, nhưng Stream API cho phép các tối ưu hợp lệ.

**Collectors.counting()** mô tả một phép tổng hợp; bạn cũng không nên đặt hành động nghiệp vụ bắt buộc trong mapper, filter hoặc peek rồi tin rằng mọi callback chắc chắn chạy đúng một lần. Việc đếm và việc thực hiện hành động có side effect là hai trách nhiệm khác nhau.

## 4. summingInt(): cộng giá trị int rút ra từ mỗi phần tử

Factory method:

~~~java
static <T> Collector<T, ?, Integer> summingInt(
        ToIntFunction<? super T> mapper)
~~~

Đối số **mapper** nhận một phần tử T và tạo một **int**. Collector cộng các kết quả int ấy, trả **Integer**.

~~~java
record Order(String code, int quantity) { }

List<Order> orders = List.of(
        new Order("A", 2),
        new Order("B", 3),
        new Order("C", 4)
);

int units = orders.stream()
        .collect(Collectors.summingInt(Order::quantity));

System.out.println(units); // 9
~~~

Đây là đoạn minh họa cần đặt trong lớp/phương thức có import List và Collectors. Record Order có accessor **quantity()** do compiler tạo.

### 4.1. Giá trị được cộng là kết quả mapper

Với **summingInt(Order::quantity)**, đối tượng Order không được cộng trực tiếp. Java gọi mapper để lấy số lượng:

~~~text
Order("A",2) -> mapper -> 2
Order("B",3) -> mapper -> 3
Order("C",4) -> mapper -> 4
                           |
                           v
                         tổng = 9
~~~

Nếu mapper trả giá trị khác, collector cộng **giá trị đó**. Chẳng hạn:

~~~java
int doubleUnits = orders.stream()
        .collect(Collectors.summingInt(
                order -> order.quantity() * 2));

System.out.println(doubleUnits); // 18
~~~

Mỗi số lượng được nhân 2 trước khi cộng. Trước khi code, cần xác định **đơn vị của đại lượng**: số món, số tiền theo đơn vị nhỏ nhất, phút, điểm, v.v. Việc cộng các giá trị không đồng nhất về đơn vị là một lỗi nghiệp vụ dù mã vẫn biên dịch.

### 4.2. Khác biệt với IntStream.sum()

Nếu chỉ cần tổng trực tiếp trên một stream đã chuyển sang primitive:

~~~java
int units = orders.stream()
        .mapToInt(Order::quantity)
        .sum();
~~~

Kết quả bằng cách dùng **Collectors.summingInt** trong ví dụ. Cách này diễn đạt phép cộng primitive trực tiếp và thường đơn giản hơn khi không cần downstream collector.

Dùng **summingInt()** khi cần cấu trúc như:

~~~java
Map<String, Integer> unitsByCategory = orders.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.summingInt(Order::quantity)));
~~~

Mảnh ghép này giả định kiểu Order có thêm accessor **category()** và có import Map/Collectors; không phải record Order hai field trong ví dụ 4.1.

### 4.3. Tràn số nguyên

**summingInt** trả Integer và thực hiện tổng theo miền **int**. Nếu tổng thực vượt khoảng từ **Integer.MIN_VALUE** đến **Integer.MAX_VALUE**, kết quả có thể bị **overflow**.

~~~java
int total = Stream.of(Integer.MAX_VALUE, 1)
        .collect(Collectors.summingInt(Integer::intValue));

System.out.println(total); // -2147483648
~~~

Đây là hành vi số nguyên có dấu int theo quy tắc tràn của Java; nó không phải giá trị tổng toán học mong muốn.

**Không dùng summingInt cho tổng có thể vượt phạm vi int.** Chọn **Collectors.summingLong(mapper)**, **mapToLong(...).sum()** nếu miền long đủ, hoặc thiết kế tổng với **BigInteger/BigDecimal** và quy tắc kiểm soát overflow phù hợp.

Với tổng tiền theo đơn vị VND, việc mỗi mặt hàng có giá int **không có nghĩa** doanh thu của toàn hệ thống cũng vừa int.

### 4.4. Phép nhân trong mapper cũng có thể overflow

Nếu tính **số lượng × đơn giá** rồi cộng:

~~~java
Collectors.summingInt(order ->
        order.quantity() * order.unitPriceVnd())
~~~

**Phép nhân** có thể overflow **trước khi cộng**. Nếu cần số tiền đúng và trong miền long:

~~~java
Collectors.summingLong(order ->
        Math.multiplyExact(
                (long) order.quantity(),
                (long) order.unitPriceVnd()))
~~~

Mảnh ghép giả định kiểu Order có các accessor phù hợp. **Math.multiplyExact** kiểm tra tràn khi nhân long, nhưng phép cộng tổng trong summingLong vẫn có thể overflow nếu vượt miền long. Đối với tiền tệ có phần thập phân, nên xem xét **BigDecimal** theo chính sách làm tròn và đơn vị được định nghĩa.

## 5. averagingDouble(): lấy trung bình từ các giá trị double

Factory method:

~~~java
static <T> Collector<T, ?, Double> averagingDouble(
        ToDoubleFunction<? super T> mapper)
~~~

Mỗi phần tử được mapper chuyển thành một **double**, rồi Collector tính **trung bình cộng**.

~~~java
List<Integer> scores = List.of(8, 9, 10);

double average = scores.stream()
        .collect(Collectors.averagingDouble(
                Integer::doubleValue));

System.out.println(average); // 9.0
~~~

Kết quả 9.0 vì (8 + 9 + 10)/3 = 9.

### 5.1. Trung bình của số phần tử đi vào collector

Ví dụ:

~~~java
record Product(String name, double price) { }

List<Product> products = List.of(
        new Product("A", 10.0),
        new Product("B", 20.0),
        new Product("C", 30.0)
);

double averagePrice = products.stream()
        .collect(Collectors.averagingDouble(Product::price));

System.out.println(averagePrice); // 20.0
~~~

Collector này trả **trung bình số học đơn giản** trên các phần tử được chọn; mọi phần tử có trọng số bằng nhau.

**Đừng nhầm với trung bình có trọng số.** Ví dụ giá trung bình của các giao dịch theo số lượng hàng bán không nhất thiết bằng trung bình đơn giá từng dòng. Nếu bán 1 món giá 10 và 100 món giá 20, trung bình đơn giá theo dòng là 15, còn giá bình quân theo từng món là **(1×10 + 100×20)/(1+100)**.

Để tính trung bình có trọng số, cần tổng **(trọng số × giá trị)** và tổng trọng số, rồi chia có kiểm soát. Một phép **averagingDouble(Product::price)** đơn giản không thực hiện logic trọng số.

### 5.2. Stream rỗng trả 0.0

~~~java
double avg = Stream.<Integer>empty()
        .collect(Collectors.averagingDouble(
                Integer::doubleValue));

System.out.println(avg); // 0.0
~~~

**0.0 ở đây là quy ước kết quả của Collector khi không có dữ liệu**, không phải một giá trị trung bình toán học đã được quan sát.

Nếu nghiệp vụ phải phân biệt **không có quan sát** và **trung bình thật sự bằng 0**, không dùng mỗi Double kết quả. Có thể kết hợp **counting()** cùng averagingDouble, hoặc dùng **DoubleStream.average()** trả **OptionalDouble**.

### 5.3. Khác với DoubleStream.average()

~~~java
OptionalDouble average = DoubleStream.of(4.0, 6.0)
        .average();

System.out.println(average.orElse(-1.0)); // 5.0

OptionalDouble noAverage = DoubleStream.empty()
        .average();

System.out.println(noAverage.isEmpty()); // true
~~~

**Collectors.averagingDouble** trả **Double**, rỗng là **0.0**. **DoubleStream.average** trả **OptionalDouble**, rỗng là **empty**. Chọn API phù hợp hợp đồng thiếu dữ liệu mà tầng gọi cần xử lý.

### 5.4. Sai số số thực và thứ tự tính

Phép tính **double** tuân theo IEEE 754, có giới hạn độ chính xác. Hợp đồng của **averagingDouble** không bảo đảm kết quả luôn chính xác tuyệt đối, và giá trị có thể thay đổi chút ít khi thứ tự tính thay đổi, đặc biệt khi xử lý song song.

Ví dụ: **0.1 + 0.2** có biểu diễn nhị phân không chính xác hoàn toàn, nên không nên so trung bình double với một giá trị kỳ vọng bằng phép so **==** nếu nghiệp vụ yêu cầu độ chính xác với phần thập phân.

**Lưu ý đặc biệt:** nếu dữ liệu có **NaN** hoặc **Infinity**, kết quả trung bình có thể là NaN/Infinity theo phép tính số thực. Một giá trị NaN thường làm kết quả tổng hợp không còn hữu ích; hãy xác định chính sách kiểm tra dữ liệu trước khi tổng hợp.

Đối với số tiền, nên ưu tiên phép tính chính xác với **BigDecimal** cùng **MathContext/RoundingMode** được quy định. **averagingDouble** thích hợp cho nhiều số đo, thống kê và tình huống chấp nhận sai số số thực.

## 6. Chọn API phù hợp theo mục tiêu

| Nhu cầu | Cách thường trực tiếp hơn | Khi nào dùng Collector |
| --- | --- | --- |
| Đếm mọi phần tử | **stream.count()** | **Collectors.counting()** khi làm downstream |
| Đếm phần tử đạt điều kiện | **filter(...).count()** | **filtering(..., counting())** trong grouping |
| Cộng số nguyên | **mapToInt(...).sum()** | **summingInt(mapper)** trong grouping/teeing |
| Cộng số long | **mapToLong(...).sum()** | **summingLong(mapper)** trong grouping |
| Tính trung bình double | **mapToDouble(...).average()** | **averagingDouble(mapper)** khi cần Double/downstream |
| Cần cùng lúc count, sum, min, max, avg | **summaryStatistics()** | **summarizingInt/Long/Double**, teeing hoặc collector tổng hợp |

Không có quy định “cứ dùng Stream là phải dùng Collectors”. Hãy chọn cách **diễn đạt rõ ý đồ** và trả kiểu kết quả mà caller cần.

## 7. groupingBy: thống kê theo từng nhóm

Giả sử cần thống kê số đơn, số lượng hàng và đơn giá trung bình cho từng danh mục. **groupingBy** phân loại phần tử theo khóa; **downstream collector** thực hiện tổng hợp trong mỗi nhóm.

### 7.1. Đếm mỗi nhóm

~~~java
Map<String, Long> countByCategory = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                Collectors.counting()));
~~~

Đây là đoạn minh họa dựa trên kiểu Sale có category() và danh sách sales. Mỗi category sẽ có một giá trị Long đếm số bản ghi thuộc nhóm đó.

### 7.2. Tổng số lượng mỗi nhóm

~~~java
Map<String, Integer> unitsByCategory = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                Collectors.summingInt(Sale::quantity)));
~~~

Các số quantity của từng Sale thuộc cùng category được cộng lại. Đừng gọi đây là “số lượng đơn”: **counting đếm bản ghi**, còn **summingInt(Sale::quantity) cộng số món**.

### 7.3. Đơn giá trung bình mỗi nhóm

~~~java
Map<String, Double> averagePriceByCategory = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                Collectors.averagingDouble(Sale::unitPriceVnd)));
~~~

Đây là trung bình **đơn giá của từng bản ghi** trong nhóm, không có trọng số theo số lượng. Với nhóm có nhiều bản ghi cùng sản phẩm nhưng quantity khác nhau, hãy chọn đúng định nghĩa trung bình mà nghiệp vụ yêu cầu.

### 7.4. Thứ tự của Map

Overload groupingBy mặc định **không cam kết thứ tự duyệt các entry trong Map trả về**. Nếu muốn một kết quả hiển thị có thứ tự khóa tự nhiên, dùng overload có **mapFactory**:

~~~java
Map<String, Long> ordered = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                TreeMap::new,
                Collectors.counting()));
~~~

Cần import Map, TreeMap, Collectors và có kiểu Sale. **TreeMap** giữ các khóa theo thứ tự so sánh; thứ tự này là của **khóa**, không phải thứ tự phần tử trong từng nhóm.

**groupingBy** thông thường không cho phép classifier trả null; nếu category có thể null, cần quyết định chính sách xử lý hoặc chuẩn hóa trước khi grouping. Không nên dùng null như một khóa tùy tiện rồi coi đó là một nhóm hợp lệ nếu API từ chối.

## 8. partitioningBy: thống kê theo điều kiện đúng/sai

Một dạng nhóm đặc biệt là **phân hoạch theo boolean**:

~~~java
Map<Boolean, Long> byPaid = sales.stream()
        .collect(Collectors.partitioningBy(
                Sale::paid,
                Collectors.counting()));
~~~

Kết quả có khóa boolean **true** và **false**, tương ứng số đơn đã và chưa thanh toán.

Trong các phép thống kê theo điều kiện, **partitioningBy** thường diễn đạt trực tiếp hơn groupingBy(s -> s.paid()) và có thể giúp bạn luôn nhìn thấy cả hai phía phân hoạch, kể cả một phía có kết quả đếm 0.

**Không dựa vào thứ tự in của HashMap/Map không có hợp đồng thứ tự.** Muốn tạo báo cáo xác định, đọc riêng **byPaid.get(true)** và **byPaid.get(false)** hoặc sắp khóa trước khi trình bày.

## 9. filtering downstream khác filter trước groupingBy

Đây là tình huống quan trọng khi cần giữ mọi nhóm nhưng thống kê chỉ các phần tử đạt điều kiện.

### 9.1. Lọc trước groupingBy

~~~java
Map<String, Long> paidOnly = sales.stream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
                Sale::category,
                Collectors.counting()));
~~~

Nếu một category chỉ có đơn chưa thanh toán, category đó **không xuất hiện** trong Map kết quả, vì đã bị loại trước khi grouping.

### 9.2. Lọc trong downstream bằng Collectors.filtering

~~~java
Map<String, Long> paidCounts = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                Collectors.filtering(
                        Sale::paid,
                        Collectors.counting())));
~~~

**Collectors.filtering(predicate, downstream)** có từ Java 9. Trong cách này, nhóm được hình thành trước, rồi phần tử trong nhóm đi qua filtering downstream. Một category có toàn đơn chưa thanh toán vẫn có thể xuất hiện với count **0L** thay vì biến mất.

**Ví dụ ý nghĩa nghiệp vụ:** dashboard cần hiển thị mọi category, kể cả loại không có đơn đã thanh toán, để báo cáo một con số 0 thay vì thiếu cả dòng.

Không nên tự động thay thế một cách viết bằng cách kia nếu việc **giữ khóa với giá trị 0** có ý nghĩa cho người dùng.

## 10. Kết hợp các Collector bằng teeing

Từ Java 12, **Collectors.teeing** cho phép lấy **một dòng phần tử** và tổng hợp bằng hai downstream collector, sau đó kết hợp hai kết quả thành một object.

Ví dụ đếm số đơn và tổng số lượng:

~~~java
record Totals(long orders, int units) { }

Totals totals = sales.stream()
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingInt(Sale::quantity),
                Totals::new));
~~~

Đoạn này cần đặt trong lớp/phương thức có record Totals, kiểu Sale và import Collectors. **counting** tạo Long; **summingInt** tạo Integer; constructor **Totals(long,int)** nhận được chúng qua unboxing.

Với cùng một dòng dữ liệu, teeing tạo kết quả **hai chỉ số** trong một terminal operation, không cần caller chạy hai pipeline riêng. Một nhược điểm là ba hoặc nhiều chỉ số có thể khiến **teeing lồng nhau** khó đọc. Khi đó, **summarizingInt** hoặc một collector custom được thiết kế cẩn thận có thể rõ hơn.

### 10.1. Tương quan với summarizingInt

~~~java
IntSummaryStatistics stats = sales.stream()
        .collect(Collectors.summarizingInt(Sale::quantity));

System.out.println(stats.getCount());
System.out.println(stats.getSum());
System.out.println(stats.getAverage());
~~~

**Collectors.summarizingInt** trả **IntSummaryStatistics**, chứa count, sum, min, max, average. Hãy chọn nó khi đúng các chỉ số cần thiết và muốn tránh tổ hợp nhiều collector không cần thiết.

Một điều cần lưu ý: sum của **IntSummaryStatistics** được biểu diễn bằng **long**, trong khi **summingInt** có kết quả Integer/int. Đây là khác biệt có thể quan trọng nếu dữ liệu nhiều và tổng số lượng vượt miền int.

## 11. Ví dụ Java 17 hoàn chỉnh

Ta có năm bản ghi bán hàng. Mỗi bản ghi chứa:

- **id**: mã bản ghi.
- **category**: nhóm hàng.
- **quantity**: số món trong giao dịch.
- **unitPriceVnd**: đơn giá theo VND, dùng giá trị int cho ví dụ nhỏ.
- **paid**: trạng thái thanh toán.

Bài toán:

1. Đếm tổng số bản ghi.
2. Cộng tổng số lượng món.
3. Tính trung bình số lượng trên một bản ghi.
4. Tính tổng doanh thu theo **quantity × unitPriceVnd**.
5. Tính đơn giá trung bình theo bản ghi.
6. Thống kê ba chỉ số theo category, sắp khóa để đầu ra xác định.
7. Đếm số giao dịch đã và chưa trả tiền.
8. Thống kê số giao dịch **đã thanh toán** theo category bằng downstream filtering.
9. Minh họa count/sum/avg trên stream rỗng và teeing count+sum.

Tạo file **CollectorStatisticsDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectorStatisticsDemo {
    record Sale(
            String id,
            String category,
            int quantity,
            int unitPriceVnd,
            boolean paid) { }

    record Totals(long orders, int units) { }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("A", "Books", 2, 10_000, true),
                new Sale("B", "Books", 1, 16_000, false),
                new Sale("C", "Games", 3, 8_000, true),
                new Sale("D", "Games", 0, 12_000, true),
                new Sale("E", "Books", 4, 22_000, true)
        );

        long count = sales.stream()
                .collect(Collectors.counting());

        int units = sales.stream()
                .collect(Collectors.summingInt(Sale::quantity));

        double averageUnits = sales.stream()
                .collect(Collectors.averagingDouble(
                        sale -> sale.quantity()));

        int revenue = sales.stream()
                .collect(Collectors.summingInt(
                        sale -> Math.multiplyExact(
                                sale.quantity(),
                                sale.unitPriceVnd())));

        double averageUnitPrice = sales.stream()
                .collect(Collectors.averagingDouble(
                        Sale::unitPriceVnd));

        System.out.println("count: " + count);
        System.out.println("units: " + units);
        System.out.println("average units: " + averageUnits);
        System.out.println("revenue: " + revenue);
        System.out.println("average price: " + averageUnitPrice);

        Map<String, Long> countsByCategory = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        TreeMap::new,
                        Collectors.counting()));

        Map<String, Integer> unitsByCategory = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        TreeMap::new,
                        Collectors.summingInt(Sale::quantity)));

        Map<String, Double> averagePricesByCategory =
                sales.stream()
                        .collect(Collectors.groupingBy(
                                Sale::category,
                                TreeMap::new,
                                Collectors.averagingDouble(
                                        Sale::unitPriceVnd)));

        System.out.println("group counts: " + countsByCategory);
        System.out.println("group units: " + unitsByCategory);
        System.out.println("group avg prices: "
                + averagePricesByCategory);

        Map<Boolean, Long> paidCounts = sales.stream()
                .collect(Collectors.partitioningBy(
                        Sale::paid,
                        Collectors.counting()));

        System.out.println("paid: " + paidCounts.get(true)
                + ", unpaid: " + paidCounts.get(false));

        Map<String, Long> paidByCategory = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        TreeMap::new,
                        Collectors.filtering(
                                Sale::paid,
                                Collectors.counting())));

        System.out.println("paid by category: "
                + paidByCategory);

        Totals totals = sales.stream()
                .collect(Collectors.teeing(
                        Collectors.counting(),
                        Collectors.summingInt(Sale::quantity),
                        Totals::new));

        System.out.println("totals: " + totals);

        long emptyCount = Stream.<Sale>empty()
                .collect(Collectors.counting());

        int emptySum = Stream.<Sale>empty()
                .collect(Collectors.summingInt(
                        Sale::quantity));

        double emptyAverage = Stream.<Sale>empty()
                .collect(Collectors.averagingDouble(
                        Sale::unitPriceVnd));

        System.out.println("empty: " + emptyCount
                + "/" + emptySum + "/" + emptyAverage);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac CollectorStatisticsDemo.java
java CollectorStatisticsDemo
~~~

**Đầu ra chính xác:**

~~~text
count: 5
units: 10
average units: 2.0
revenue: 148000
average price: 13600.0
group counts: {Books=3, Games=2}
group units: {Books=7, Games=3}
group avg prices: {Books=16000.0, Games=10000.0}
paid: 4, unpaid: 1
paid by category: {Books=2, Games=2}
totals: Totals[orders=5, units=10]
empty: 0/0/0.0
~~~

### 11.1. Kiểm tra phép tính thủ công

Tổng số lượng:

~~~text
Books: A(2) + B(1) + E(4) = 7
Games: C(3) + D(0)        = 3
Tổng số lượng              = 10
~~~

Tổng doanh thu theo đơn vị VND:

~~~text
A: 2 × 10.000 =  20.000
B: 1 × 16.000 =  16.000
C: 3 ×  8.000 =  24.000
D: 0 × 12.000 =       0
E: 4 × 22.000 =  88.000
------------------------
Tổng             148.000
~~~

Trung bình đơn giá trên năm **bản ghi**:

~~~text
(10.000 + 16.000 + 8.000 + 12.000 + 22.000) / 5
= 68.000 / 5
= 13.600
~~~

Theo nhóm:

- **Books** có 3 bản ghi, 7 món; giá trung bình theo bản ghi = (10.000 + 16.000 + 22.000)/3 = **16.000**.
- **Games** có 2 bản ghi, 3 món; giá trung bình theo bản ghi = (8.000 + 12.000)/2 = **10.000**.
- **paid** có A, C, D, E → 4 bản ghi; **unpaid** có B → 1 bản ghi.
- Theo category, Books có A/E đã trả (2), Games có C/D đã trả (2).

Kết quả trung bình giá của mỗi nhóm được viết dạng Double với hậu tố **.0**. Điều này do kiểu kết quả của **averagingDouble**, không phải vì dữ liệu tiền đã thay đổi sang kiểu tài chính decimal chính xác.

### 11.2. Vì sao dùng TreeMap trong ví dụ?

**groupingBy(..., TreeMap::new, downstream)** đặt khóa **Books** trước **Games**, nên có thể nêu stdout chính xác. Nếu dùng groupingBy hai tham số mặc định, không nên cam kết thứ tự khi in một Map thông thường.

### 11.3. Vì sao revenue không phải số lượng món?

**summingInt(Sale::quantity)** cộng **số món**. **summingInt(sale -> quantity × unitPrice)** cộng **doanh thu**. Hai phép cộng khác nhau ở mapper và **đơn vị**. Một chương trình có thể trả số đúng về mặt tính toán nhưng sai báo cáo nếu mapper lấy nhầm trường.

### 11.4. Vì sao stream rỗng trả 0/0/0.0?

Đây là hợp đồng của ba Collector:

- Counting: **0L**.
- SummingInt: **0**.
- AveragingDouble: **0.0**.

Với trung bình trên dữ liệu rỗng, phải có chính sách ở tầng nghiệp vụ nếu bạn muốn hiển thị **“không có dữ liệu”** thay vì 0.0.

## 12. Phân biệt đếm giao dịch, tổng món và trung bình có trọng số

Một hệ thống thực tế thường có ba khái niệm:

| Chỉ số | Mẫu tính | Ý nghĩa |
| --- | --- | --- |
| Số giao dịch | **counting()** | Mỗi bản ghi được tính một lần |
| Tổng số món | **summingInt(Sale::quantity)** | Tổng quantity của các bản ghi |
| Đơn giá trung bình theo dòng | **averagingDouble(Sale::unitPriceVnd)** | Trung bình không trọng số |
| Đơn giá bình quân theo món | **Tổng (qty × unitPrice) / Tổng qty** | Trung bình có trọng số theo quantity |

Trong dữ liệu ví dụ:

- Trung bình **đơn giá theo dòng** = 13.600 VND.
- Tổng doanh thu = 148.000 VND.
- Tổng số món = 10.
- Bình quân **đơn giá theo món** = **14.800 VND**, khác 13.600.

Nếu báo cáo cần **trung bình theo món**, không dùng một mình **averagingDouble(Sale::unitPriceVnd)**. Hãy tính đúng tử số và mẫu số rồi chia, kiểm tra trường hợp tổng lượng bằng 0.

**Đơn giá bình quân theo món** còn có thể khác “giá bán thực” nếu xuất hiện giảm giá, hoàn tiền hoặc thuế. Cần làm rõ quy tắc nghiệp vụ trước khi viết mapper.

## 13. Kiểm soát sai số và tính đúng đắn

### 13.1. Long của counting không phải vô hạn

**Collectors.counting()** trả Long để có miền rộng hơn int, nhưng **long** vẫn hữu hạn. Trong những hệ thống cực lớn, cần xác định giới hạn dữ liệu và việc lưu trữ. Đa số bài toán Java thông thường không đạt giới hạn long, nhưng “Long” không đồng nghĩa giá trị không thể tràn trong mọi kịch bản.

### 13.2. summingInt và summingLong

**summingInt** phù hợp khi chắc chắn tổng nằm trong miền int. Với số lượng giao dịch lớn, doanh thu hoặc những số đo có thể vượt giới hạn, dùng **summingLong** với mapper chuyển sang long:

~~~java
long total = sales.stream()
        .collect(Collectors.summingLong(
                sale -> (long) sale.quantity()));
~~~

Đây là mảnh ghép dựa trên record Sale đã có. Với phép nhân, ép lên long **trước khi nhân**:

~~~java
long revenue = sales.stream()
        .collect(Collectors.summingLong(
                sale -> (long) sale.quantity()
                        * sale.unitPriceVnd()));
~~~

Không được viết phép nhân int trước rồi mới ép sang long nếu cần tránh overflow của phép nhân int.

**summingLong vẫn có thể overflow**; nếu tổng vượt phạm vi long hoặc cần kiểm soát overflow chính xác, hãy dùng mô hình số phù hợp hơn thay vì giả định mọi phép sum đều tự phát hiện tràn.

### 13.3. Double không dùng cho tiền chính xác tuyệt đối

**averagingDouble** có ý nghĩa cho thống kê, không phải engine tiền tệ tuyệt đối chính xác. Với tiền có đơn vị lẻ, tiền nhiều loại hoặc quy tắc làm tròn bắt buộc:

- Chọn một biểu diễn số tiền rõ ràng (ví dụ số nguyên đơn vị nhỏ nhất, hoặc BigDecimal).
- Định nghĩa scale, rounding và thời điểm làm tròn.
- Tách số lượng phần tử, tổng tiền và trung bình có trọng số.
- Kiểm thử cả trường hợp 0 bản ghi, số âm, hoàn tiền và dữ liệu không hợp lệ.

Không chọn Double chỉ vì một Collector có tên “averaging”.

### 13.4. NaN, Infinity và dữ liệu không hợp lệ

Nếu mapper trả giá trị **Double.NaN**, **POSITIVE_INFINITY** hoặc **NEGATIVE_INFINITY**, kết quả trung bình có thể không hữu ích. Hãy quyết định liệu dữ liệu đó cần bị từ chối, lọc bỏ, ghi nhận lỗi hay phân nhóm riêng.

Ví dụ khi muốn chỉ thống kê giá trị double hữu hạn:

~~~java
double mean = measurements.stream()
        .mapToDouble(Measurement::value)
        .filter(Double::isFinite)
        .average()
        .orElse(Double.NaN);
~~~

Đây là mảnh ghép trong ngữ cảnh có kiểu Measurement và danh sách measurements; không phải file độc lập. **Double::isFinite** phù hợp với DoubleStream.filter vì method static nhận một primitive double và trả boolean.

**Chú ý:** lọc bỏ các giá trị không hợp lệ thay đổi **mẫu số trung bình**; cần minh bạch trong báo cáo rằng các bản ghi ấy đã bị loại.

## 14. Không dùng mapper có side effect hoặc state thay đổi

Một mapper phù hợp là phép đọc/tính từ phần tử và cấu hình ổn định:

~~~java
Collectors.summingInt(Sale::quantity)
Collectors.averagingDouble(Sale::unitPriceVnd)
~~~

Một mapper có side effect hoặc đọc bộ đếm mutable có thể cho kết quả sai tùy thứ tự gọi:

~~~java
AtomicInteger sequence = new AtomicInteger();

ToIntFunction<Sale> unstable =
        sale -> sequence.incrementAndGet();
~~~

Đây là mảnh ghép minh họa với Sale, AtomicInteger, ToIntFunction trong ngữ cảnh. **unstable** trả thứ tự gọi thay vì số lượng bán; khi chạy parallel, thứ tự callback có thể khác và số liệu không còn phản ánh Sale.

**AtomicInteger** khiến phép tăng nguyên tử, nhưng không làm mapper trở nên **stateless** hay đúng nghiệp vụ. Không dùng callback trong tổng hợp để cập nhật một global counter cần chính xác theo semantics nghiệp vụ.

### 14.1. Non-interference với nguồn

Không sửa list nguồn hoặc field của Sale từ mapper:

~~~java
// Phản ví dụ, không dùng trong production:
// Collectors.summingInt(sale -> {
//     sale.changeQuantity();
//     return sale.quantity();
// });
~~~

Nếu object nguồn mutable, việc đọc và ghi lẫn nhau trong khi pipeline đang duyệt có thể gây dữ liệu không nhất quán. Nên tạo snapshot thích hợp hoặc dùng immutable record và quản lý owner của dữ liệu rõ ràng.

## 15. Parallel stream và tính kết hợp

Các Collector chuẩn được thiết kế để có thể hoạt động trong framework reduction. Nhưng để phép tính có ý nghĩa đúng, các mapper phải không can thiệp, không phụ thuộc trạng thái biến đổi. Đặc biệt:

- **counting** đếm số phần tử và thường ổn định theo dữ liệu nguồn đã xác định.
- **summingInt** thực hiện tổng int theo quy tắc số nguyên; overflow vẫn là rủi ro nghiệp vụ dù chạy tuần tự hay song song.
- **averagingDouble** chịu sai số floating-point; thứ tự kết hợp các subtotal có thể làm kết quả cuối thay đổi ở những chữ số thấp.
- **groupingBy** không tự bảo đảm thứ tự Map khi không có mapFactory; **groupingByConcurrent** có hợp đồng khác và không nên dùng nếu cần thứ tự khóa hoặc encounter order mà nó không bảo đảm.
- **Không tự dùng một Map hoặc accumulator mutable chung để cộng kết quả trong forEach** khi Collectors đã cung cấp đường tổng hợp an toàn hơn.

Ví dụ sau không phải cách tốt để tổng hợp:

~~~java
Map<String, Integer> totals = new HashMap<>();

sales.parallelStream().forEach(sale ->
        totals.merge(sale.category(),
                sale.quantity(), Integer::sum));
~~~

Đây là phản ví dụ với HashMap thường: cập nhật từ nhiều thread không an toàn. Ngay cả dùng ConcurrentHashMap, bạn phải làm rõ tính kết hợp, overflow, thứ tự và hợp đồng của mọi side effect. Nếu chỉ cần tổng số lượng theo category, dùng **groupingBy(..., summingInt(...))** diễn đạt đúng mục tiêu và dễ kiểm thử hơn.

## 16. Một số lựa chọn nâng cao

### 16.1. Tổng và trung bình của long

Nếu mapper tạo long, có các collector:

~~~java
Collectors.summingLong(ToLongFunction<? super T> mapper)
Collectors.averagingLong(ToLongFunction<? super T> mapper)
~~~

**summingLong** trả Long, **averagingLong** trả Double. Chúng có thể phù hợp hơn khi đầu vào là long; nhưng kết quả trung bình dạng double vẫn có giới hạn độ chính xác.

### 16.2. Tổng và trung bình của double

~~~java
Collectors.summingDouble(ToDoubleFunction<? super T> mapper)
Collectors.averagingDouble(ToDoubleFunction<? super T> mapper)
~~~

Hai Collector xử lý dữ liệu double, khác với summingInt vốn cộng int. Nếu cần lấy tổng nguyên từ các phần tử, không chọn summingDouble chỉ vì dữ liệu ban đầu có int và compiler có thể ép sang double: việc ép kiểu có thể làm mất độ chính xác với số rất lớn.

### 16.3. Tạo Map chỉ chứa chỉ số cần thiết

Nếu ứng dụng chỉ cần **Long** đếm số record theo nhóm, đừng collect cả List<Sale> rồi gọi size() trừ khi còn cần lưu danh sách. **groupingBy(category, counting())** có thể giảm lượng dữ liệu phải giữ và diễn đạt đúng yêu cầu.

Ngược lại, nếu sau đó thực sự cần truy cập mọi Sale trong mỗi nhóm, **groupingBy(category)** trả Map<String,List<Sale>> là phương án hợp lý. Đừng tối ưu quá sớm làm mất dữ liệu mà bước sau cần sử dụng.

### 16.4. Phân biệt grouping và partitioning với dữ liệu rỗng

**groupingBy** trên stream rỗng trả Map không chứa nhóm. **partitioningBy** có chính sách hai khóa boolean và downstream có giá trị danh định cho từng phía; với **counting**, hai phía có thể có kết quả 0L.

Nếu ứng dụng muốn báo cáo **tất cả category trong danh mục đăng ký**, kể cả category không xuất hiện trong nguồn, groupingBy không thể tự tạo category chưa gặp. Cần hợp nhất với danh mục category được định nghĩa bên ngoài; không suy diễn rằng “groupingBy + counting” tự phát sinh đầy đủ những khóa không có dữ liệu.

## 17. Kiểm thử các chỉ số tổng hợp

Kiểm tra tối thiểu:

1. **counting** trên nguồn rỗng, một bản ghi, nhiều bản ghi và sau filter.
2. **summingInt** trên số dương/0/âm, kiểm tra đơn vị và miền số.
3. **averagingDouble** trên tập rỗng, một phần tử, số đo đều nhau, số đo khác nhau và sai số.
4. **groupingBy** trên nhiều nhóm, nhóm chỉ có một phần tử, nhóm có quantity=0.
5. **partitioningBy** với toàn true, toàn false và dữ liệu hỗn hợp.
6. **filtering downstream** với nhóm không có phần tử đạt điều kiện; nhóm còn tồn tại với giá trị 0.
7. **teeing** cho kết quả count và sum trong cùng lần tổng hợp.
8. **Đầu ra theo khóa** phải xác định nếu báo cáo cần thứ tự; sử dụng TreeMap và so đúng Map thay vì dựa vào thứ tự HashMap.
9. **Mapper không sửa nguồn** và không dựa vào global mutable state.
10. Khi chạy parallel, xác định dung sai double; không đòi kết quả floating-point có mọi bit đồng nhất nếu thuật toán cho phép kết hợp theo thứ tự khác.

Ví dụ test đơn giản:

~~~java
long c = List.of(3, 5, 7).stream()
        .collect(Collectors.counting());

int s = List.of(3, 5, 7).stream()
        .collect(Collectors.summingInt(Integer::intValue));

double a = List.of(3, 5, 7).stream()
        .collect(Collectors.averagingDouble(
                Integer::doubleValue));

if (c != 3L || s != 15 || Math.abs(a - 5.0) > 1e-12) {
    throw new AssertionError("Unexpected statistics");
}
~~~

Đây là mảnh ghép trong phương thức có import List/Collectors. Nó kiểm tra trực tiếp ba chỉ số, không phụ thuộc side effect từ callback.

## 18. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Nghĩ counting() trả Integer | Khai báo biến sai kiểu | Nhớ kết quả là Long |
| Nghĩ summingInt() trả Long | Sai kiểu hoặc chọn miền số chưa đủ | Dùng Integer; đổi sang summingLong nếu cần |
| Nghĩ averagingDouble() trả OptionalDouble | Không kiểm soát trường hợp rỗng | Nó trả Double; rỗng là 0.0 |
| Coi 0.0 nghĩa chắc chắn có quan sát | Nhầm dữ liệu rỗng với trung bình thật bằng 0 | Kèm counting hoặc dùng OptionalDouble |
| Cộng đơn giá bằng summingInt rồi gọi là doanh thu | Sai đơn vị | Mapper phải tính quantity × price |
| Tính trung bình đơn giá theo dòng rồi gọi là theo món | Sai trọng số | Tính tổng tiền / tổng quantity đúng định nghĩa |
| Không xem xét overflow int | Tổng trả giá trị sai | summingLong hoặc kiểu số lớn hơn |
| Nhân hai int trước khi ép lên long | Tràn xảy ra trước phép ép | Ép toán hạng trước khi nhân |
| Dùng averagingDouble cho tiền cần chính xác tuyệt đối | Sai số và khó bảo đảm rounding | BigDecimal/chính sách làm tròn |
| Bỏ qua NaN/Infinity | Kết quả tổng hợp có thể không hữu ích | Validation hoặc lọc có báo cáo |
| In groupingBy rồi tin thứ tự Map luôn cố định | Báo cáo không xác định | Dùng TreeMap/mapFactory hoặc sắp khi xuất |
| filter trước grouping và tưởng nhóm 0 vẫn xuất hiện | Nhóm toàn phần tử bị loại biến mất | Dùng filtering downstream khi muốn giữ khóa |
| Mapper có side effect hoặc mutable counter | Kết quả phụ thuộc thứ tự/thực thi | Dùng mapper thuần và dữ liệu ổn định |
| Tự cập nhật HashMap trong parallel forEach | Race condition | Dùng collector đúng hợp đồng |

## 19. Bài tập tự luyện

### Bài 1 — Đếm từng lớp học

Có danh sách Student với accessor **className()**. Hãy đếm số Student mỗi lớp bằng **groupingBy** và **counting**.

**Đáp án gợi ý:**

~~~java
Map<String, Long> counts = students.stream()
        .collect(Collectors.groupingBy(
                Student::className,
                Collectors.counting()));
~~~

Đoạn này cần các khai báo Student, students và import Map/Collectors.

### Bài 2 — Cộng số lượng đã bán

Có list Order với **quantity()** kiểu int. Viết pipeline trả tổng số lượng bằng **summingInt**.

**Đáp án:**

~~~java
int units = orders.stream()
        .collect(Collectors.summingInt(Order::quantity));
~~~

Nếu tổng có thể vượt miền int, đổi sang **summingLong** hoặc thiết kế miền số rộng hơn.

### Bài 3 — Trung bình thời gian xử lý

Một danh sách Job có **durationSeconds()** là double. Hãy tính trung bình và xử lý tình huống danh sách rỗng có ý nghĩa “chưa có dữ liệu”.

**Đáp án gợi ý:** dùng **mapToDouble(Job::durationSeconds).average()** trả OptionalDouble để biểu diễn sự vắng mặt, hoặc kết hợp **counting() + averagingDouble(...)** nếu API báo cáo cần cả số lượng và trung bình dạng Double.

### Bài 4 — Khác nhau giữa hai kiểu trung bình

Có hai giao dịch: **1 món × 10.000** và **3 món × 20.000**.

- Trung bình đơn giá theo dòng = (10.000 + 20.000)/2 = **15.000**.
- Trung bình theo món = (10.000 + 3 × 20.000)/(1 + 3) = **17.500**.

**Câu hỏi:** averagingDouble(Order::unitPrice) trả cái nào? **Đáp án:** trả **15.000**, vì mỗi Order đóng góp một quan sát, không theo trọng số quantity.

### Bài 5 — Giữ nhóm có count=0

Có danh sách đơn với category A, B; mọi đơn A đều chưa thanh toán. Cần một Map gồm A=0, B=số đơn đã thanh toán. Nên filter trước groupingBy hay dùng filtering downstream?

**Đáp án:** **groupingBy(category, filtering(isPaid, counting()))** để giữ khóa A và cho kết quả 0, trong khi filter trước grouping có thể loại mất nhóm A.

### Bài 6 — Kiểm tra dữ liệu rỗng và overflow

Hãy viết test cho ba collector khi stream rỗng. Sau đó tạo dãy có tổng **Integer.MAX_VALUE + 1** và quan sát summingInt. Giải thích vì sao kết quả tràn không phải một lỗi của cú pháp Collector mà là **giới hạn số học int**. Viết lại với summingLong.

## 20. Ghi nhớ

**Collectors.counting(), summingInt() và averagingDouble()** là ba công cụ rút gọn dữ liệu cơ bản:

- **counting()** trả **Long** đếm phần tử, rỗng là **0L**.
- **summingInt(mapper)** trả **Integer** cộng các giá trị int do mapper tạo, rỗng là **0**, có nguy cơ **overflow int**.
- **averagingDouble(mapper)** trả **Double** trung bình số học của các giá trị double do mapper tạo, rỗng là **0.0** và có thể có sai số floating-point.

Khi chỉ tính một chỉ số đơn giản, có thể dùng **count()**, **sum()**, **average()** trên Stream/primitive Stream. Khi cần thống kê **theo nhóm**, các Collector phát huy lợi thế làm **downstream của groupingBy hoặc partitioningBy**. Với **filtering downstream**, hãy phân biệt một nhóm có kết quả 0 với một nhóm bị loại khỏi Map.

Trước khi tạo báo cáo, hãy luôn xác định: **đang đếm bản ghi hay cộng đại lượng nào; trung bình có trọng số không; dữ liệu rỗng được hiểu thế nào; kiểu số có đủ miền và độ chính xác không?** Lựa chọn đúng Collector là điều kiện cần, nhưng **định nghĩa đúng phép thống kê** mới giúp kết quả có ý nghĩa.
