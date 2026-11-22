# Summary statistics theo kiểu số trong Java Stream

**Chủ đề:** Java 8 → Collector cơ bản → Summary statistics theo kiểu số.

Khi xử lý một danh sách đơn hàng, bản ghi cảm biến hay dữ liệu nhân sự, ta thường cần trả lời cùng lúc: **có bao nhiêu giá trị, tổng bằng bao nhiêu, nhỏ nhất/lớn nhất là gì và trung bình là bao nhiêu?** Java cung cấp các collector và đối tượng summary statistics để lấy năm số liệu này trong **một lần thu thập Stream**. Những API này xuất hiện từ Java 8 và vẫn hữu ích trong các phiên bản Java hiện hành.

Bài học dùng ví dụ độc lập **Java 17+**; các API Stream/Collector chính được học vẫn áp dụng với Java hiện đại. Các tiện ích ví dụ như **List.of** (Java 9+) và **record** (Java 16+) được dùng để mã ngắn, dễ đọc.

## 1. Mục tiêu và bản chất của summary statistics

Sau bài này, bạn có thể:

1. Chọn đúng **Collectors.summarizingInt**, **summarizingLong** hoặc **summarizingDouble** theo kiểu dữ liệu.
2. Trích xuất chính xác **count**, **sum**, **min**, **max**, **average** qua các phương thức **getCount()**, **getSum()**, **getMin()**, **getMax()**, **getAverage()**.
3. Phân biệt **Stream<T>.collect(Collectors.summarizing...)** với **IntStream/LongStream/DoubleStream.summaryStatistics()**.
4. Xử lý đúng **Stream rỗng**, đặc biệt là sentinel của min/max và average bằng 0.
5. Kết hợp summary statistics với **groupingBy** hoặc **partitioningBy** để thống kê từng nhóm.
6. Hiểu giới hạn **tràn số nguyên**, **sai số double**, các giá trị **NaN/Infinity** và cách sử dụng collector khi xử lý song song.

**Summary statistics** là dữ liệu tổng hợp từ một tập giá trị số. Trong thư viện Java, ba kiểu kết quả chỉ thu thập thống kê mô tả cơ bản, chưa phải một bộ công cụ thống kê tổng quát: chúng **không tự cung cấp phương sai, độ lệch chuẩn, median, phân vị hoặc trung bình có trọng số**.

Một pipeline điển hình:

~~~java
IntSummaryStatistics stats = people.stream()
        .collect(Collectors.summarizingInt(Person::age));
~~~

Đây là **đoạn minh họa**: giả sử đã có **people** kiểu **List<Person>**, **Person** có phương thức **age()**, và đã import **java.util.IntSummaryStatistics** cùng **java.util.stream.Collectors**. **collect(...)** là terminal operation; collector cung cấp cách tạo đối tượng kết quả, nạp từng giá trị và kết hợp các phần khi cần.

## 2. Ba collector cơ bản và kiểu kết quả

| Collector | Mapper cần có | Đối tượng trả về | Dữ liệu thích hợp |
|---|---|---|---|
| **Collectors.summarizingInt(mapper)** | **ToIntFunction<T>** trả **int** | **IntSummaryStatistics** | Tuổi, số lượng, điểm nguyên, số lần xuất hiện |
| **Collectors.summarizingLong(mapper)** | **ToLongFunction<T>** trả **long** | **LongSummaryStatistics** | Timestamp dạng số, tổng đơn vị nhỏ nhất, các giá trị nguyên lớn |
| **Collectors.summarizingDouble(mapper)** | **ToDoubleFunction<T>** trả **double** | **DoubleSummaryStatistics** | Số đo, thời gian, tỷ lệ hoặc điểm đánh giá có phần thập phân |

**Mapper** là hàm lấy giá trị số từ mỗi phần tử nguồn, chẳng hạn **Product::units** hoặc **person -> person.salaryCents()**. Khi truyền đối tượng vào **Stream<T>.collect(...)**, collector sẽ áp dụng mapper và ghi nhận từng giá trị được sinh ra.

Ba cách gọi thường gặp:

~~~java
// Giả sử List<Product> products đã có dữ liệu; Product là kiểu phù hợp.
IntSummaryStatistics units = products.stream()
        .collect(Collectors.summarizingInt(Product::units));

LongSummaryStatistics cents = products.stream()
        .collect(Collectors.summarizingLong(Product::revenueCents));

DoubleSummaryStatistics ratings = products.stream()
        .collect(Collectors.summarizingDouble(Product::rating));
~~~

Các đoạn trên chỉ minh họa cách dùng API; chương trình hoàn chỉnh với lớp **Product**, import và kết quả kiểm chứng ở phần 4.

**Không chọn collector theo tên thuộc tính mà theo kiểu số trả về sau mapping.** Nếu giá trị vốn là **long**, đừng ép xuống **int** chỉ để dùng **summarizingInt()**, vì phép ép kiểu có thể làm mất phần giá trị. Nếu đầu vào là số tiền thập phân cần tính chính xác, xem mục giới hạn số học thay vì vội chuyển thành **double**.

## 3. Năm phép đo trong một kết quả

Cả **IntSummaryStatistics**, **LongSummaryStatistics** và **DoubleSummaryStatistics** đều cung cấp:

| Phương thức | Ý nghĩa | Kiểu trả về |
|---|---|---|
| **getCount()** | Số giá trị đã ghi nhận | **long** ở cả ba lớp |
| **getSum()** | Tổng giá trị | **long** cho IntSummaryStatistics; **long** cho LongSummaryStatistics; **double** cho DoubleSummaryStatistics |
| **getMin()** | Giá trị nhỏ nhất | **int**, **long** hoặc **double** tương ứng |
| **getMax()** | Giá trị lớn nhất | **int**, **long** hoặc **double** tương ứng |
| **getAverage()** | Trung bình cộng của các giá trị | **double** ở cả ba lớp |

Nếu có các giá trị **2, 4, 6**, kết quả là:

~~~text
count = 3
sum = 12
min = 2
max = 6
average = 4.0
~~~

**Chi tiết rất dễ nhầm:** **IntSummaryStatistics.getSum() trả long**, có thể biểu diễn tổng lớn hơn giới hạn **int**. Trái lại, **IntStream.sum() trả int**, còn **Collectors.summingInt(...) trả Integer**; hai cách tính chỉ trả tổng kiểu int và có thể bị tràn trong trường hợp tổng lớn. Bản thân **IntSummaryStatistics** vẫn không kiểm tra tràn của **long getSum()** và **long getCount()**.

Với **LongSummaryStatistics**, tổng đã là **long** và vẫn có thể tràn nếu tổng vượt phạm vi **long**. Với **DoubleSummaryStatistics**, tổng và trung bình là **double**, vì vậy có sai số biểu diễn dấu chấm động.

### getAverage() có làm mất phần thập phân?

**getAverage()** trả **double** ngay cả khi dữ liệu đầu vào là **int** hoặc **long**. Ví dụ, với **1** và **2**, trung bình là **1.5**, không bị chia nguyên thành **1**. Tuy vậy, kết quả trung bình vẫn dùng phép toán dấu chấm động: không đảm bảo biểu diễn chính xác mọi phân số hoặc mọi số nguyên **long** có độ lớn rất lớn.

**getCount()** đếm số giá trị thực sự đến collector **sau khi các thao tác filter/flatMap xảy ra**. Nó không mặc định là số phần tử ban đầu, số phần tử khác nhau, hay số bản ghi trước lọc.

## 4. Ví dụ Java 17+ hoàn chỉnh: thống kê cả ba kiểu

Lưu mã sau vào **NumericSummaryDemo.java**:

~~~java
import java.util.DoubleSummaryStatistics;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.stream.Collectors;

public class NumericSummaryDemo {
    record Product(
            String category,
            int units,
            long revenueCents,
            double rating) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("books", 2, 1200, 4.5),
                new Product("books", 4, 2400, 3.5),
                new Product("tools", 6, 7500, 4.0)
        );

        IntSummaryStatistics units = products.stream()
                .collect(Collectors.summarizingInt(Product::units));

        LongSummaryStatistics revenue = products.stream()
                .collect(Collectors.summarizingLong(Product::revenueCents));

        DoubleSummaryStatistics ratings = products.stream()
                .collect(Collectors.summarizingDouble(Product::rating));

        System.out.println("units: count=" + units.getCount()
                + ", sum=" + units.getSum()
                + ", min=" + units.getMin()
                + ", max=" + units.getMax()
                + ", avg=" + units.getAverage());

        System.out.println("revenue: count=" + revenue.getCount()
                + ", sum=" + revenue.getSum()
                + ", min=" + revenue.getMin()
                + ", max=" + revenue.getMax()
                + ", avg=" + revenue.getAverage());

        System.out.println("rating: count=" + ratings.getCount()
                + ", sum=" + ratings.getSum()
                + ", min=" + ratings.getMin()
                + ", max=" + ratings.getMax()
                + ", avg=" + ratings.getAverage());

        Map<String, LongSummaryStatistics> byCategory =
                products.stream().collect(
                        Collectors.groupingBy(
                                Product::category,
                                Collectors.summarizingLong(Product::revenueCents)
                        )
                );

        System.out.println("books: count="
                + byCategory.get("books").getCount()
                + ", sum=" + byCategory.get("books").getSum());

        System.out.println("tools: count="
                + byCategory.get("tools").getCount()
                + ", sum=" + byCategory.get("tools").getSum());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 NumericSummaryDemo.java
java NumericSummaryDemo
~~~

**Stdout:**

~~~text
units: count=3, sum=12, min=2, max=6, avg=4.0
revenue: count=3, sum=11100, min=1200, max=7500, avg=3700.0
rating: count=3, sum=12.0, min=3.5, max=4.5, avg=4.0
books: count=2, sum=3600
tools: count=1, sum=7500
~~~

**Giải thích:**

- Tất cả ba collector đều xử lý **ba bản ghi**, nhưng mỗi collector trích xuất một thuộc tính riêng.
- **units** ghi nhận các số **2, 4, 6** nên tổng là **12**, trung bình là **4.0**.
- **revenue** dùng **long** theo đơn vị cent: tổng **1200 + 2400 + 7500 = 11100**, trung bình **3700.0 cent**.
- **ratings** dùng **double** để tổng hợp ba điểm **4.5, 3.5, 4.0**.
- **groupingBy(...)** tạo map với mỗi khóa **category** gắn một **LongSummaryStatistics** riêng. Nhóm **books** có hai bản ghi, tổng doanh thu **3600 cent**; nhóm **tools** có một bản ghi, tổng **7500 cent**.
- Chương trình truy cập kết quả bằng tên nhóm cụ thể, vì **thứ tự duyệt của map từ groupingBy không được bảo đảm**. Không phụ thuộc vào thứ tự in của **Map.toString()**.

Cả ba pipeline thu thập riêng biệt trong ví dụ đều tạo **stream() mới**. Sau mỗi terminal operation **collect(...)**, Stream đã bị tiêu thụ và không được dùng lại.

## 5. Primitive Stream.summaryStatistics(): cách viết khác

Nếu pipeline đã chuyển sang các stream số nguyên thủy, dùng trực tiếp **summaryStatistics()**:

~~~java
// Đoạn minh họa; products và Product như chương trình phía trên.
IntSummaryStatistics units = products.stream()
        .mapToInt(Product::units)
        .summaryStatistics();

LongSummaryStatistics revenue = products.stream()
        .mapToLong(Product::revenueCents)
        .summaryStatistics();

DoubleSummaryStatistics ratings = products.stream()
        .mapToDouble(Product::rating)
        .summaryStatistics();
~~~

Các phương thức **IntStream.summaryStatistics()**, **LongStream.summaryStatistics()** và **DoubleStream.summaryStatistics()** đều là terminal operation và trả về ba kiểu đối tượng tương ứng.

So sánh hai cách viết cho cùng một thuộc tính:

~~~java
// A: Stream đối tượng + Collector
IntSummaryStatistics a = products.stream()
        .collect(Collectors.summarizingInt(Product::units));

// B: primitive stream + summaryStatistics
IntSummaryStatistics b = products.stream()
        .mapToInt(Product::units)
        .summaryStatistics();
~~~

Trong trường hợp nguồn và mapper giống nhau, hai cách có cùng ý nghĩa thống kê. Chọn cách **A** khi cần dùng **Collector** làm downstream của **groupingBy**, **partitioningBy** hoặc phép thu thập kết hợp khác. Chọn cách **B** khi pipeline đã làm việc trực tiếp với **IntStream/LongStream/DoubleStream** hoặc muốn sử dụng chuỗi phép toán primitive.

**Lưu ý:** Nếu chỉ cần **một số liệu**, chẳng hạn tổng hoặc trung bình, các terminal operation chuyên dụng như **sum()** hoặc **average()** có thể diễn đạt mục đích trực tiếp hơn. Không nhất thiết tạo đối tượng summary statistics để đọc duy nhất một trường.

## 6. Tập rỗng: không có số liệu không đồng nghĩa min/max bằng 0

Khi đầu vào không có phần tử, các đối tượng statistics vẫn được tạo nhưng chứa giá trị khởi tạo đặc biệt:

| Kết quả với tập rỗng | IntSummaryStatistics | LongSummaryStatistics | DoubleSummaryStatistics |
|---|---|---|---|
| **getCount()** | 0L | 0L | 0L |
| **getSum()** | 0L | 0L | 0.0 |
| **getAverage()** | 0.0 | 0.0 | 0.0 |
| **getMin()** | **Integer.MAX_VALUE** | **Long.MAX_VALUE** | **Double.POSITIVE_INFINITY** |
| **getMax()** | **Integer.MIN_VALUE** | **Long.MIN_VALUE** | **Double.NEGATIVE_INFINITY** |

**Sentinel** là giá trị kỹ thuật khởi tạo cho trường hợp chưa có phần tử; nó **không phải kết quả min/max có ý nghĩa nghiệp vụ**. Đặc biệt, giá trị **0.0** của **getAverage()** trên tập rỗng không chứng minh trung bình thực sự bằng 0: hai tình huống khác nhau cho cùng số 0.

Cách an toàn:

~~~java
IntSummaryStatistics stats = values.stream()
        .mapToInt(Integer::intValue)
        .summaryStatistics();

// values được giả sử có kiểu List<Integer> và không chứa null.
if (stats.getCount() == 0) {
    System.out.println("Không có dữ liệu để thống kê");
} else {
    System.out.println("Min = " + stats.getMin());
    System.out.println("Max = " + stats.getMax());
    System.out.println("Average = " + stats.getAverage());
}
~~~

Đây là đoạn minh họa có biến nguồn **values** được khai báo bên ngoài. Hãy dùng **getCount() == 0** để xác định rỗng, **không kiểm tra getMin() == Integer.MAX_VALUE**, vì **Integer.MAX_VALUE** cũng có thể là một giá trị đầu vào hợp lệ.

### Phân biệt với Optional của min(), max(), average()

Primitive Stream cung cấp các terminal operation:

~~~java
java.util.OptionalInt min =
        java.util.stream.IntStream.empty().min();

java.util.OptionalInt max =
        java.util.stream.IntStream.empty().max();

java.util.OptionalDouble avg =
        java.util.stream.IntStream.empty().average();
~~~

Kết quả trên lần lượt là **OptionalInt.empty()**, **OptionalInt.empty()** và **OptionalDouble.empty()**, thay vì sentinel hoặc average bằng 0. Đây có thể là lựa chọn rõ ràng hơn nếu chỉ cần một trong các chỉ số và yêu cầu phân biệt "không có dữ liệu" với "giá trị 0".

**Collectors.averagingInt(...)** và các collector trung bình tương tự trả **Double**, với giá trị **0.0** khi không có phần tử. Cần kiểm tra lượng bản ghi độc lập nếu muốn biết tập có rỗng hay không.

## 7. Ví dụ chạy đầy đủ: dữ liệu rỗng, tràn số và NaN

Lưu thành **SummaryEdgeCases.java**:

~~~java
import java.util.DoubleSummaryStatistics;
import java.util.IntSummaryStatistics;
import java.util.LongSummaryStatistics;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class SummaryEdgeCases {
    public static void main(String[] args) {
        IntSummaryStatistics empty =
                IntStream.empty().summaryStatistics();

        System.out.println("empty: count=" + empty.getCount()
                + ", sum=" + empty.getSum()
                + ", min=" + empty.getMin()
                + ", max=" + empty.getMax()
                + ", avg=" + empty.getAverage());

        int narrowSum = IntStream.of(Integer.MAX_VALUE, 1).sum();
        long widerSum = IntStream.of(Integer.MAX_VALUE, 1)
                .summaryStatistics()
                .getSum();

        System.out.println("sumInt=" + narrowSum);
        System.out.println("statsInt=" + widerSum);

        LongSummaryStatistics overflowLong =
                LongStream.of(Long.MAX_VALUE, 1L).summaryStatistics();

        System.out.println("statsLong=" + overflowLong.getSum());

        DoubleSummaryStatistics emptyDouble =
                DoubleStream.empty().summaryStatistics();

        System.out.println("emptyDouble: min=" + emptyDouble.getMin()
                + ", max=" + emptyDouble.getMax()
                + ", avg=" + emptyDouble.getAverage());

        DoubleSummaryStatistics withNaN =
                DoubleStream.of(2.0, Double.NaN).summaryStatistics();

        System.out.println("nanDouble: min=" + withNaN.getMin()
                + ", max=" + withNaN.getMax()
                + ", sum=" + withNaN.getSum());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SummaryEdgeCases.java
java SummaryEdgeCases
~~~

**Stdout:**

~~~text
empty: count=0, sum=0, min=2147483647, max=-2147483648, avg=0.0
sumInt=-2147483648
statsInt=2147483648
statsLong=-9223372036854775808
emptyDouble: min=Infinity, max=-Infinity, avg=0.0
nanDouble: min=NaN, max=NaN, sum=NaN
~~~

**Điểm mấu chốt:**

1. **summaryStatistics()** trên stream rỗng trả một đối tượng với các giá trị khởi tạo, không trả **Optional.empty()**.
2. **IntStream.sum()** có thể tràn trong **int**. **IntSummaryStatistics.getSum()** cộng và trả **long**, vì vậy ví dụ hai số nguyên này vẫn tính đúng **2.147.483.648**.
3. **LongSummaryStatistics** vẫn có thể tràn **long**, với tổng **Long.MAX_VALUE + 1** quay vòng thành **Long.MIN_VALUE**. Nó không tự ném ngoại lệ.
4. **DoubleSummaryStatistics** dùng vô cực làm sentinel cho min/max rỗng; không được trình bày chúng như các giá trị đo thực.
5. Khi có một phần tử **NaN**, thống kê double của tổng, min và max cũng trở thành **NaN** theo hợp đồng API.

Các phép tính trong chương trình đã được kiểm tra trên một JDK hiện hành; mã chỉ dùng API hợp lệ với Java 17+.

## 8. Dùng summary statistics làm downstream Collector

Khả năng kết hợp với **groupingBy(...)** là điểm nổi bật của **Collectors.summarizing...** so với một terminal operation chỉ dành cho primitive stream.

### 8.1. groupingBy: thống kê từng nhóm

Hình dạng tổng quát:

~~~java
Map<Key, IntSummaryStatistics> result = source.stream()
        .collect(Collectors.groupingBy(
                item -> /* chọn khóa nhóm */,
                Collectors.summarizingInt(item -> /* giá trị int */)
        ));
~~~

Dòng trên là **mẫu minh họa**, không biên dịch độc lập vì **Key**, **source** và phần mapper chưa được định nghĩa. Trong chương trình đầy đủ ở mục 4, nhóm **books** và **tools** đã trả về map chứa **LongSummaryStatistics** riêng cho mỗi nhóm.

Một số điều cần nhớ:

- Mỗi nhóm có **count/sum/min/max/average** riêng theo **các phần tử thuộc nhóm đó**.
- **Không có nhóm nào** với một khóa nhất định thì thường **không có entry** cho khóa đó trong kết quả **groupingBy**. Do đó **map.get(key)** có thể trả **null**; hãy kiểm tra sự tồn tại trước khi dùng getter.
- **getCount()** là số phần tử của nhóm **sau filter**. Ví dụ, nếu đã lọc đơn hàng lỗi trước khi grouping thì các đơn đó không tham gia thống kê.
- Thứ tự key của map không được bảo đảm bởi **groupingBy**. Muốn hiển thị theo thứ tự, sắp các entry hoặc chọn một map có thứ tự phù hợp theo yêu cầu.
- Đầu ra của hàm phân loại trong **groupingBy** không nên là **null**; hãy làm sạch hoặc quy định nhóm thiếu giá trị trước khi thu thập.

### 8.2. partitioningBy: hai nhóm true/false

**partitioningBy(predicate, downstream)** chia nguồn theo một điều kiện boolean và có **hai khóa** là **true** và **false**, kể cả khi một nhóm không có phần tử. Kết quả downstream của nhóm rỗng là một thống kê rỗng với **count=0**.

~~~java
// Giả sử products và Product đã được khai báo ở ví dụ mục 4.
Map<Boolean, IntSummaryStatistics> byLargeOrder =
        products.stream().collect(
                Collectors.partitioningBy(
                        product -> product.units() >= 10,
                        Collectors.summarizingInt(Product::units)
                )
        );

// byLargeOrder.get(true).getCount() == 0
// byLargeOrder.get(false).getSum() == 12
~~~

Ở đây các sản phẩm đều có số lượng dưới 10. Nhánh **true** vẫn tồn tại nhưng có count 0. Vì vậy khi đọc **min/max/average** của nhánh này, áp dụng quy tắc kiểm tra rỗng ở mục 6.

### 8.3. Có cần viết Collector tùy chỉnh?

Khi chỉ cần năm chỉ số cơ bản của cùng một giá trị số, collector có sẵn là lựa chọn đơn giản. Nếu muốn **trung bình có trọng số, median, phân vị, độ lệch chuẩn, hoặc phép cộng số thập phân chính xác bằng BigDecimal**, phải thiết kế phép tổng hợp phù hợp; không nên suy diễn rằng các phương thức **getAverage()** hoặc **getSum()** sẵn có đáp ứng tất cả.

## 9. Giới hạn số học và độ chính xác

### 9.1. IntSummaryStatistics có sum long, nhưng không phải số nguyên vô hạn

**IntSummaryStatistics.getSum()** là **long** nên một dãy các số **int** có thể có tổng lớn hơn **Integer.MAX_VALUE** mà vẫn thu được đúng. Nhưng nếu tổng toán học vượt **Long.MAX_VALUE** hay thấp hơn **Long.MIN_VALUE**, phép cộng thông thường của **long** vẫn tràn.

**LongSummaryStatistics.getSum()** cũng có nguy cơ như vậy. Các lớp statistics không cung cấp chế độ **checked arithmetic**. Nếu tổng chính xác là yêu cầu bắt buộc và miền dữ liệu có thể rất lớn:

- Xác định cận tổng dự kiến từ số lượng phần tử và biên từng giá trị.
- Dùng **Math.addExact(...)** trong phép tổng hợp được thiết kế để phát hiện tràn, hoặc **BigInteger** nếu muốn biểu diễn tổng nguyên vượt giới hạn **long**.
- Với giá trị tiền có đơn vị nhỏ nhất cố định, **long** biểu diễn cent có thể phù hợp khi đã bảo đảm giới hạn; nếu cần decimal chính xác hoặc vượt giới hạn, dùng **BigDecimal** và quy tắc làm tròn được xác định.

Cần phân biệt **getSum()** của summary statistics và các terminal operation **sum()** trên primitive streams; chúng có kiểu trả về khác nhau cho **int**.

### 9.2. DoubleSummaryStatistics là thống kê gần đúng

**double** theo IEEE 754 không biểu diễn chính xác mọi số thập phân, ví dụ **0.1**. Khi cộng nhiều giá trị, thứ tự cộng có thể ảnh hưởng sai số làm tròn. **DoubleSummaryStatistics.getSum()** có thể dùng **compensated summation** hoặc kỹ thuật khác để giảm sai số; thứ tự cộng không được đặc tả cố định, nên tổng và trung bình **không được bảo đảm chính xác tuyệt đối hay bất biến từng bit giữa mọi cách thực thi**.

Tình huống cần tránh:

~~~java
// Không nên chọn double cho phép cộng tiền cần chính xác theo cent.
DoubleSummaryStatistics money = java.util.stream.DoubleStream
        .of(0.1, 0.2)
        .summaryStatistics();

// Một số thập phân có thể có sai số biểu diễn;
// đừng dựa vào việc kiểm tra money.getSum() == 0.3 cho nghiệp vụ tiền.
~~~

Đây là ví dụ về **rủi ro kiểu số**, không phải khẳng định một giá trị bit cụ thể của **DoubleSummaryStatistics.getSum()** trên mọi JDK. Nếu đầu vào là tiền dạng decimal, nên giữ giá trị bằng **BigDecimal** hoặc đơn vị nhỏ nhất để tránh phụ thuộc phép cộng floating-point.

### 9.3. NaN, Infinity, -0.0 và +0.0

Với **DoubleSummaryStatistics**:

- **NaN** trong dữ liệu có thể làm **getSum()**, **getMin()** và **getMax()** trở thành **NaN**.
- Giá trị **Infinity/-Infinity** và hiện tượng tràn số thực có thể khiến tổng trở nên vô cực hoặc **NaN**; trung bình cũng có thể không hữu hạn.
- Trong min/max, **-0.0 được xem là nhỏ hơn +0.0**, dù toán tử số học **-0.0 == +0.0** trả **true**.
- Tập rỗng trả min/max là vô cực sentinel, khác với trường hợp dữ liệu thực sự có vô cực. **getCount()** giúp phân biệt rỗng.

Nếu hệ thống chỉ chấp nhận các số đo hữu hạn, **kiểm tra/validate** bằng **Double.isFinite(value)** trước khi thu thập. Chỉ **lọc bỏ** NaN/Infinity khi nghiệp vụ thật sự cho phép bỏ dữ liệu; với các hệ thống cần tính toàn vẹn, có thể phải từ chối bản ghi không hợp lệ thay vì âm thầm bỏ qua.

~~~java
// Giả sử measurements có kiểu List<Double> và các phần tử không null.
DoubleSummaryStatistics finiteOnly = measurements.stream()
        .mapToDouble(Double::doubleValue)
        .filter(Double::isFinite)
        .summaryStatistics();
~~~

Đây là đoạn minh họa; kết quả chỉ thống kê **các giá trị hữu hạn còn lại**, do đó **getCount()** không nhất thiết bằng số phần tử nguồn.

### 9.4. Trung bình có trọng số khác getAverage()

**getAverage()** lấy trung bình cộng đơn giản của **mỗi giá trị mapper trả về**. Ví dụ điểm của hai bài làm có hệ số 1 và 3 sẽ không được tính đúng nếu chỉ gọi **summarizingDouble(Exercise::score).getAverage()**.

Trung bình có trọng số cần được định nghĩa:

~~~text
weightedAverage = tổng(score × weight) / tổng(weight)
~~~

Cần quyết định kiểu số, phép cộng và xử lý tổng trọng số bằng 0. Với kết quả chính xác decimal, nên dùng **BigDecimal** và **RoundingMode** phù hợp; với đo lường có dung sai, có thể dùng **double** kèm chính sách kiểm tra sai số. Built-in summary statistics không trực tiếp cung cấp trọng số.

## 10. Collector, tính biến đổi và Stream song song

Ba lớp statistics là **mutable**: **accept(value)** thêm một giá trị vào thống kê và **combine(other)** gộp hai trạng thái. Điều này phục vụ cách collector thu thập và kết hợp kết quả.

~~~java
IntSummaryStatistics stats = new IntSummaryStatistics();
stats.accept(2);
stats.accept(4);
// count=2, sum=6, min=2, max=4, average=3.0
~~~

**Không chia sẻ cùng một IntSummaryStatistics/LongSummaryStatistics/DoubleSummaryStatistics cho nhiều thread cùng gọi accept/combine** mà không đồng bộ: bản thân các lớp này **không thread-safe**. Tuy nhiên, **Collectors.summarizingInt/Long/Double có thể dùng an toàn trong parallelStream().collect(...)** vì cơ chế thu thập phân tách trạng thái cục bộ và kết hợp kết quả theo hợp đồng Stream.

~~~java
// Đoạn minh họa; products và Product đã có trong mục 4.
IntSummaryStatistics parallelStats = products.parallelStream()
        .collect(Collectors.summarizingInt(Product::units));
~~~

Một số nguyên tắc:

- Viết mapper **thuần**, không cập nhật biến tổng bên ngoài hay sửa nguồn dữ liệu.
- Đừng giả định collector chạy mapper theo đúng thứ tự hoặc cùng một thread trên parallel stream.
- Với số nguyên không tràn, thống kê cộng/min/max cho cùng các giá trị thường có tính xác định. Với **double**, trình tự kết hợp có thể ảnh hưởng **getSum/getAverage**.
- Parallel không đồng nghĩa chạy nhanh hơn. Chi phí tách/gộp có thể lớn hơn lợi ích với tập dữ liệu nhỏ.
- Một đối tượng statistics đã trả về là mutable; nếu ứng dụng lưu trong cache hoặc chia sẻ, cần quản lý quyền sửa và luồng truy cập như mọi đối tượng mutable khác.

## 11. Dữ liệu thiếu, sai kiểu và kiểm thử

### 11.1. Mapper nhận null

Các collector sử dụng mapper kiểu nguyên thủy **ToIntFunction/ToLongFunction/ToDoubleFunction**. Nếu bạn cố unbox một **Integer**, **Long** hoặc **Double** đang **null**, chương trình có thể ném **NullPointerException**.

Ví dụ:

~~~java
// Đoạn minh họa có thể chạy nếu có import java.util.*,
// java.util.stream.*; giữ ví dụ ngắn để nhấn mạnh cách xử lý null.
List<Integer> values = java.util.Arrays.asList(2, null, 4);

IntSummaryStatistics stats = values.stream()
        .filter(java.util.Objects::nonNull)
        .collect(java.util.stream.Collectors.summarizingInt(
                Integer::intValue
        ));

// stats.getCount() == 2; stats.getSum() == 6
~~~

**Lọc null có nghĩa là bỏ bản ghi khỏi thống kê.** Hãy xác định trước: null là dữ liệu không hợp lệ phải báo lỗi, là giá trị thiếu được bỏ qua, hay là số 0 theo quy tắc nghiệp vụ. Không tự ý coi tất cả null là 0.

### 11.2. Những điều cần kiểm thử

Đối với code dùng statistics, kiểm thử theo yêu cầu cụ thể nhưng nên xem các lớp dữ liệu:

1. Nguồn **rỗng** và nguồn chỉ có **một phần tử**.
2. Giá trị **âm, 0, dương**, cực trị **MIN_VALUE/MAX_VALUE**.
3. Tổng **int** có thể vượt giới hạn và tổng **long** có thể tràn.
4. **NaN, Infinity**, số thực rất lớn/rất nhỏ nếu nguồn có thể chứa.
5. Nhiều **nhóm**, thiếu một nhóm, một nhóm không có phần tử trong **partitioningBy**.
6. **null** trong nguồn hoặc thuộc tính mapper, cùng chính sách xử lý.
7. Chạy tuần tự và song song nếu nghiệp vụ thực sự cần parallel, đặc biệt khi tổng **double** có dung sai.

**Không nên so sánh toàn bộ chuỗi stats.toString() để khẳng định output**, vì định dạng cụ thể của phương thức này không được API hứa sẽ cố định giữa mọi phiên bản. Kiểm thử từng getter và, với **double**, dùng mức sai số phù hợp nếu không cần khớp tuyệt đối từng bit.

## 12. Chọn API nhanh theo nhu cầu

| Câu hỏi nghiệp vụ | API phù hợp | Điều cần lưu ý |
|---|---|---|
| Cần **count/sum/min/max/average** của một thuộc tính int | **Collectors.summarizingInt** hoặc **IntStream.summaryStatistics()** | **getSum() là long**; min/max rỗng là sentinel |
| Cần năm chỉ số của thuộc tính long | **Collectors.summarizingLong** hoặc **LongStream.summaryStatistics()** | sum có thể tràn long |
| Cần năm chỉ số của thuộc tính double | **Collectors.summarizingDouble** hoặc **DoubleStream.summaryStatistics()** | sai số, NaN/Infinity và thứ tự cộng |
| Cần thống kê **theo nhóm** | **groupingBy(key, summarizing...)** | nhóm vắng mặt có thể không có key |
| Cần thống kê **theo hai nhánh boolean** | **partitioningBy(predicate, summarizing...)** | nhánh rỗng vẫn có stats với count 0 |
| Chỉ cần **trung bình** của primitive stream | **IntStream/LongStream/DoubleStream.average()** | trả **OptionalDouble** để biểu diễn dữ liệu rỗng |
| Chỉ cần **tổng** | **sum()** hoặc **Collectors.summing...** | kiểm tra phạm vi số, kiểu trả về và độ chính xác |
| Tổng tiền/decimal cần chính xác | **BigDecimal** hoặc long theo đơn vị nhỏ nhất, cùng phép gộp phù hợp | không ép thành double chỉ để dùng summarizingDouble |
| Cần median/variance/percentile/weighted average | Thuật toán/collector chuyên dụng | Không có sẵn trong ba summary statistics cơ bản |

## 13. Bài tập có đáp án

Cho danh sách:

~~~java
List<Integer> values = List.of(4, 8, 12);
~~~

Giả sử đã import **java.util.List**, **java.util.IntSummaryStatistics** và **java.util.stream.Collectors**.

**Câu 1.** Với **values.stream().collect(Collectors.summarizingInt(Integer::intValue))**, năm giá trị getter trả về gì?

**Câu 2.** Nếu thêm **filter(x -> x > 10)** trước collect, **getCount()**, **getSum()** và **getAverage()** thay đổi ra sao?

**Câu 3.** Với **values.stream().filter(x -> x < 0)** rồi summarizingInt, có được hiển thị **getMin()** như một giá trị nhỏ nhất hợp lệ không?

**Câu 4.** Kết quả của **IntStream.of(Integer.MAX_VALUE, 1).summaryStatistics().getSum()** là bao nhiêu, và khác gì **IntStream.of(Integer.MAX_VALUE, 1).sum()**?

**Câu 5.** Khi nhóm các đơn hàng theo **category**, API nào giúp mỗi nhóm cùng có đủ count/sum/min/max/average của **long revenueCents**?

**Câu 6.** Nếu dữ liệu chứa **Double.NaN**, liệu **getCount() == 0** có đúng không, và có nên dựa vào **getMin()** để xác định bản ghi hợp lệ?

**Đáp án:**

1. **count=3, sum=24, min=4, max=12, average=8.0**.
2. Chỉ còn **12**, nên **count=1, sum=12, average=12.0**.
3. **Không.** Stats rỗng có **count=0** và **getMin() == Integer.MAX_VALUE**, là sentinel chứ không phải min của một tập quan sát.
4. **getSum() == 2147483648L** vì IntSummaryStatistics dùng tổng **long**; **IntStream.sum() == -2147483648** vì phép cộng và kết quả **int** bị tràn.
5. **Collectors.groupingBy(Order::category, Collectors.summarizingLong(Order::revenueCents))**, giả sử **Order** có hai accessor tương ứng.
6. **Không:** có phần tử **NaN** thì count vẫn tăng như một giá trị đầu vào. Stats double có thể trả **NaN** cho min/max/sum. Cần xác định chính sách dữ liệu không hữu hạn và kiểm tra bằng **Double.isNaN/Double.isFinite** khi phù hợp.

## 14. Tổng kết và tài liệu tra cứu

**Summary statistics** cho phép lấy **năm chỉ số phổ biến trong một lần thu thập Stream**, với kiểu số tương ứng **int**, **long**, **double**. Nếu có một nguyên tắc cần nhớ, đó là: **luôn kiểm tra getCount() trước khi diễn giải min/max/average trên nguồn có thể rỗng**, rồi xem **giới hạn kiểu số** trước khi dùng kết quả cho nghiệp vụ. Khi cần nhóm dữ liệu, các **Collectors.summarizing...** rất hữu ích ở vị trí downstream trong **groupingBy/partitioningBy**.

Tài liệu API Oracle (Java SE 26, các hợp đồng API hiện hành):

- [Collectors.summarizingInt/Long/Double](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html)
- [IntSummaryStatistics](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/IntSummaryStatistics.html)
- [LongSummaryStatistics](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/LongSummaryStatistics.html)
- [DoubleSummaryStatistics](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/DoubleSummaryStatistics.html)
- [IntStream.summaryStatistics()](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html)
- [LongStream.summaryStatistics()](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/LongStream.html)
- [DoubleStream.summaryStatistics()](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/DoubleStream.html)
