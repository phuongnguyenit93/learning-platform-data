# Áp dụng các cải tiến cho luồng kiểu nguyên thủy trong Java

## Mục tiêu

Java cung cấp ba loại primitive stream chuyên biệt: **IntStream**, **LongStream** và **DoubleStream**. Chúng xử lý trực tiếp giá trị nguyên thủy, hỗ trợ các phép toán số học và tránh việc boxing/unboxing không cần thiết khi làm việc với số lượng lớn dữ liệu.

Từ Java 9, các primitive stream được bổ sung những thao tác hữu ích để xử lý dữ liệu theo thứ tự và tạo luồng có điều kiện dừng:

- **takeWhile(predicate)**: lấy phần đầu của luồng khi các phần tử liên tiếp còn thỏa điều kiện.
- **dropWhile(predicate)**: bỏ phần đầu của luồng khi các phần tử liên tiếp còn thỏa điều kiện.
- **iterate(seed, hasNext, next)**: tạo luồng từ giá trị đầu, tiếp tục sinh phần tử khi điều kiện còn đúng.

Các phương thức này có trên cả **IntStream**, **LongStream** và **DoubleStream**. Chúng vẫn là API hiện hành trong Java 17+.

## 1. Primitive stream là gì?

Primitive stream là một pipeline Stream được chuyên biệt hóa cho một kiểu số nguyên thủy:

| Interface | Kiểu dữ liệu | Ví dụ |
|---|---|---|
| **IntStream** | **int** | số lượng, tuổi, chỉ số, số đếm |
| **LongStream** | **long** | ID số, timestamp, tổng lớn |
| **DoubleStream** | **double** | giá trị đo, điểm số, trung bình |

Các interface này thuộc Java Stream API và mở rộng cơ chế của **BaseStream**. Chúng có các thao tác trung gian như **filter**, **map**, **peek**, **limit**, **skip**, **takeWhile**, **dropWhile** và các thao tác kết thúc như **forEach**, **sum**, **average**, **min**, **max**, **count**, **reduce** và **summaryStatistics**.

Primitive stream đặc biệt hữu ích khi phần lớn dữ liệu là số. Ví dụ, **IntStream.map(IntUnaryOperator)** nhận và trả về **int**; pipeline không cần chuyển từng giá trị thành **Integer** chỉ để áp dụng phép biến đổi số.

### So sánh với Stream<Integer>

```java
Stream<Integer> boxed = Stream.of(1, 2, 3, 4);
int total = boxed.mapToInt(Integer::intValue).sum();

IntStream primitive = IntStream.of(1, 2, 3, 4);
int primitiveTotal = primitive.sum();
```

Cả hai cách đều có thể tính tổng. Với **IntStream**, kiểu dữ liệu trong pipeline là **int**, nên không cần boxing mỗi giá trị thành **Integer** rồi unboxing để tính toán.

Boxing vẫn có thể cần khi tích hợp với API nhận object, lưu vào collection hoặc trả kết quả dưới dạng object. Mục tiêu là dùng primitive stream ở phần xử lý số khi phù hợp, sau đó chỉ chuyển kiểu tại ranh giới cần thiết.

## 2. Tạo primitive stream và các phép toán số học

Có nhiều cách tạo primitive stream:

```java
IntStream fromValues = IntStream.of(2, 4, 6);
IntStream fromRange = IntStream.range(1, 5);
IntStream inclusiveRange = IntStream.rangeClosed(1, 5);

LongStream longValues = LongStream.of(10L, 20L, 30L);
DoubleStream decimalValues = DoubleStream.of(1.5, 2.5, 3.5);
```

Khác biệt giữa **range** và **rangeClosed**:

- **range(start, end)** lấy từ **start** đến trước **end**.
- **rangeClosed(start, end)** lấy cả **start** và **end**.

Ví dụ **IntStream.range(1, 5)** tạo các giá trị 1, 2, 3, 4; còn **IntStream.rangeClosed(1, 5)** tạo 1, 2, 3, 4, 5.

Các thao tác kết thúc hữu ích:

| Phương thức | Kết quả |
|---|---|
| **sum()** | Tổng các phần tử |
| **average()** | **OptionalDouble** chứa trung bình nếu luồng có phần tử |
| **min()**, **max()** | **OptionalInt**, **OptionalLong** hoặc **OptionalDouble** tùy loại stream |
| **count()** | Số phần tử dưới dạng **long** |
| **summaryStatistics()** | Đối tượng thống kê như số lượng, tổng, min, max và trung bình |

Ví dụ:

```java
IntSummaryStatistics stats = IntStream.rangeClosed(1, 5)
        .summaryStatistics();

System.out.println(stats.getCount());
System.out.println(stats.getSum());
System.out.println(stats.getMin());
System.out.println(stats.getMax());
System.out.println(stats.getAverage());
```

Các giá trị thống kê tương ứng là 5, 15, 1, 5 và 3.0. Khi cần trung bình hoặc min/max, hãy xử lý trường hợp luồng rỗng vì các phương thức này trả về kiểu Optional phù hợp.

## 3. Cải tiến Java 9: takeWhile

**takeWhile(predicate)** là thao tác trung gian lấy các phần tử từ đầu luồng cho đến khi gặp phần tử đầu tiên không thỏa điều kiện.

Trên primitive stream, predicate dùng đúng kiểu nguyên thủy:

- **IntStream.takeWhile(IntPredicate)**
- **LongStream.takeWhile(LongPredicate)**
- **DoubleStream.takeWhile(DoublePredicate)**

Ví dụ:

```java
IntStream.of(1, 2, 3, 4, 5, 1, 2)
        .takeWhile(n -> n < 4)
        .forEach(System.out::println);
```

Kết quả:

```text
1
2
3
```

Khi gặp giá trị 4, điều kiện **n < 4** sai nên **takeWhile** dừng lấy phần tử. Các giá trị 5, 1, 2 phía sau không được xét để đưa vào kết quả, kể cả khi 1 và 2 thỏa điều kiện.

### takeWhile khác filter như thế nào?

**filter(predicate)** kiểm tra toàn bộ phần tử và giữ lại tất cả phần tử thỏa điều kiện. **takeWhile(predicate)** chỉ lấy đoạn liên tiếp ở đầu luồng còn thỏa điều kiện.

Với dữ liệu **1, 2, 3, 4, 5, 1, 2** và điều kiện **n < 4**:

- **takeWhile** trả về **1, 2, 3**.
- **filter** trả về **1, 2, 3, 1, 2**.

Dùng **takeWhile** khi điều kiện đánh dấu ranh giới kết thúc của một đoạn dữ liệu đã có thứ tự, chẳng hạn đọc các giá trị còn nằm trong một ngưỡng trước khi gặp mốc kết thúc.

## 4. Cải tiến Java 9: dropWhile

**dropWhile(predicate)** bỏ các phần tử liên tiếp ở đầu luồng khi chúng còn thỏa điều kiện. Khi gặp phần tử đầu tiên không thỏa, phần tử đó và toàn bộ phần còn lại được giữ lại.

Các chữ ký trên primitive stream:

- **IntStream.dropWhile(IntPredicate)**
- **LongStream.dropWhile(LongPredicate)**
- **DoubleStream.dropWhile(DoublePredicate)**

Ví dụ:

```java
IntStream.of(1, 2, 3, 4, 5, 1, 2)
        .dropWhile(n -> n < 4)
        .forEach(System.out::println);
```

Kết quả:

```text
4
5
1
2
```

Phần tử 4 là phần tử đầu tiên không thỏa **n < 4**. Vì vậy, Java bỏ 1, 2, 3 và giữ 4 cùng tất cả phần tử phía sau, kể cả các giá trị 1 và 2 cuối luồng.

### dropWhile khác filter như thế nào?

Với cùng dữ liệu và điều kiện:

- **dropWhile(n -> n < 4)** bỏ tiền tố 1, 2, 3 và trả về **4, 5, 1, 2**.
- **filter(n -> n >= 4)** kiểm tra toàn bộ dữ liệu và trả về **4, 5**.

Dùng **dropWhile** khi muốn bỏ phần mở đầu không cần thiết, ví dụ bỏ các bản ghi trước mốc bắt đầu rồi xử lý phần còn lại theo thứ tự.

### Trường hợp biên

- Nếu phần tử đầu tiên không thỏa điều kiện, **dropWhile** giữ nguyên toàn bộ luồng.
- Nếu tất cả phần tử đều thỏa điều kiện, **dropWhile** trả về luồng rỗng.
- Với **takeWhile**, nếu phần tử đầu tiên không thỏa điều kiện thì kết quả rỗng; nếu tất cả đều thỏa thì lấy toàn bộ luồng.

## 5. Cải tiến Java 9: iterate có điều kiện dừng

Trước Java 9, dạng **iterate(seed, next)** sinh một luồng vô hạn bằng cách liên tục áp dụng hàm **next**. Muốn giới hạn số phần tử, thường phải kết hợp với **limit**.

Java 9 bổ sung overload có ba tham số cho cả primitive stream:

- **IntStream.iterate(int seed, IntPredicate hasNext, IntUnaryOperator next)**
- **LongStream.iterate(long seed, LongPredicate hasNext, LongUnaryOperator next)**
- **DoubleStream.iterate(double seed, DoublePredicate hasNext, DoubleUnaryOperator next)**

Tham số:

1. **seed**: giá trị đầu tiên của luồng.
2. **hasNext**: điều kiện kiểm tra một giá trị có được đưa vào luồng hay không.
3. **next**: hàm tạo giá trị kế tiếp.

Điều kiện **hasNext** được kiểm tra trước khi phần tử được đưa vào luồng. Nó cũng được kiểm tra với **seed**. Nếu điều kiện sai ngay từ đầu, luồng rỗng. Khi điều kiện sai ở một giá trị, giá trị đó không được đưa vào và việc sinh phần tử dừng lại.

Ví dụ với **LongStream**:

```java
LongStream.iterate(1L, n -> n <= 16, n -> n * 2)
        .forEach(System.out::println);
```

Kết quả:

```text
1
2
4
8
16
```

Sau khi phát ra 16, hàm **next** tạo giá trị tiếp theo là 32. Predicate kiểm tra **32 <= 16** trả về false, vì vậy 32 không xuất hiện trong luồng và quá trình sinh kết thúc.

### So sánh iterate có điều kiện và iterate kết hợp limit

Với dãy số nhân đôi:

```java
LongStream.iterate(1L, n -> n * 2)
        .limit(5)
        .forEach(System.out::println);
```

Cách trên lấy đúng 5 phần tử. Còn overload ba tham số dừng theo giá trị:

```java
LongStream.iterate(1L, n -> n <= 16, n -> n * 2)
        .forEach(System.out::println);
```

Dùng **limit** khi biết trước số lượng phần tử cần lấy. Dùng **iterate(seed, hasNext, next)** khi điều kiện kết thúc phụ thuộc vào giá trị được sinh ra, ví dụ sinh lũy thừa đến một ngưỡng, tạo dãy ngày đến một ngày kết thúc hoặc sinh số cho đến khi vượt giới hạn.

Overload ba tham số trả về một luồng tuần tự có thứ tự. Hàm **next** nên tạo giá trị mới từ đối số và không sửa đổi đối số của nó.

## 6. Áp dụng tương ứng cho IntStream, LongStream và DoubleStream

Ba primitive stream có các thao tác tương ứng; khác biệt chính là kiểu nguyên thủy và functional interface mà chúng nhận:

| Thao tác | IntStream | LongStream | DoubleStream |
|---|---|---|---|
| Predicate | **IntPredicate** | **LongPredicate** | **DoublePredicate** |
| Hàm sinh phần tử kế tiếp | **IntUnaryOperator** | **LongUnaryOperator** | **DoubleUnaryOperator** |
| takeWhile | **takeWhile(IntPredicate)** | **takeWhile(LongPredicate)** | **takeWhile(DoublePredicate)** |
| dropWhile | **dropWhile(IntPredicate)** | **dropWhile(LongPredicate)** | **dropWhile(DoublePredicate)** |
| iterate có điều kiện | **iterate(int, IntPredicate, IntUnaryOperator)** | **iterate(long, LongPredicate, LongUnaryOperator)** | **iterate(double, DoublePredicate, DoubleUnaryOperator)** |

Ví dụ với **IntStream**:

```java
IntStream.iterate(1, n -> n <= 5, n -> n + 1)
        .map(n -> n * n)
        .forEach(System.out::println);
```

Kết quả là 1, 4, 9, 16, 25. **iterate** tạo các số từ 1 đến 5; **map** bình phương từng giá trị.

Ví dụ với **DoubleStream**:

```java
DoubleStream.of(1.5, 2.0, 2.5, 0.5, 3.0)
        .takeWhile(value -> value < 3.0)
        .forEach(System.out::println);
```

Kết quả gồm 1.5, 2.0, 2.5 và 0.5. Phần tử 0.5 vẫn được lấy vì **takeWhile** làm việc theo thứ tự encounter, không sắp xếp dữ liệu. Khi gặp 3.0, điều kiện sai và luồng dừng lấy phần tử.

## 7. Chuyển đổi giữa object stream và primitive stream

Trong ứng dụng thực tế, dữ liệu thường bắt đầu từ object hoặc collection. Các phương thức chuyển đổi giúp chuyển sang primitive stream để tính toán:

- **mapToInt(ToIntFunction)** tạo **IntStream**.
- **mapToLong(ToLongFunction)** tạo **LongStream**.
- **mapToDouble(ToDoubleFunction)** tạo **DoubleStream**.
- **boxed()** chuyển primitive stream thành **Stream<Integer>**, **Stream<Long>** hoặc **Stream<Double>**.
- **mapToObj(...)** chuyển giá trị nguyên thủy thành object.
- **asLongStream()** và **asDoubleStream()** hỗ trợ chuyển đổi từ **IntStream** sang primitive stream tương ứng.

Ví dụ đọc chuỗi số:

```java
int total = Stream.of("12", "7", "5")
        .mapToInt(Integer::parseInt)
        .sum();

System.out.println(total);
```

Kết quả:

```text
24
```

**mapToInt** chuyển mỗi chuỗi thành **int**. Sau đó **sum** tính tổng trực tiếp trên primitive stream.

Nếu API tiếp theo yêu cầu collection, có thể dùng **boxed()**:

```java
List<Integer> values = IntStream.rangeClosed(1, 5)
        .boxed()
        .toList();
```

**Stream.toList()** có từ Java 16, nên ví dụ này chạy trên Java 17+. Nếu cần hỗ trợ phiên bản cũ hơn, có thể dùng collector phù hợp với phiên bản mục tiêu.

## 8. Thứ tự, parallel stream và hiệu năng

**takeWhile** và **dropWhile** có ý nghĩa dựa trên thứ tự encounter của luồng:

- Với ordered stream, chúng xử lý tiền tố dài nhất thỏa predicate.
- Với unordered stream, không có tiền tố xác định. Kết quả có thể là một tập con bất kỳ của các phần tử thỏa predicate, kể cả tập rỗng.

Vì vậy, chỉ gọi **unordered()** khi ứng dụng không cần giữ thứ tự và chấp nhận ngữ nghĩa này. Không thêm **unordered()** chỉ để tăng tốc nếu kết quả đúng phụ thuộc vào tiền tố ban đầu.

Trên ordered parallel stream, **takeWhile** và **dropWhile** có thể tốn chi phí vì implementation phải xác định ranh giới của tiền tố theo encounter order. Nếu dữ liệu không quá lớn hoặc thứ tự quan trọng, pipeline tuần tự thường dễ dự đoán hơn. Nếu thứ tự không quan trọng, có thể cân nhắc unordered stream sau khi xác nhận kết quả vẫn đúng.

Các thao tác stream là lazy: intermediate operation như **filter**, **map**, **takeWhile**, **dropWhile** chưa thực hiện toàn bộ phép tính cho đến khi có terminal operation. Một stream cũng chỉ được tiêu thụ một lần; không tái sử dụng cùng stream sau **sum**, **forEach** hoặc một terminal operation khác.

### Chọn đúng primitive stream

- Dùng **IntStream** cho phép tính trong phạm vi **int**.
- Dùng **LongStream** khi tổng, bộ đếm hoặc giá trị có thể vượt phạm vi **int**.
- Dùng **DoubleStream** cho phép tính dấu phẩy động.
- Chú ý tràn số nguyên: **IntStream.sum()** có thể tràn phạm vi **int**; hãy chuyển sang **LongStream** nếu tổng có thể lớn.
- Phép tính **double** có sai số biểu diễn nhị phân; không nên dùng so sánh bằng tuyệt đối cho các phép tính dấu phẩy động khi yêu cầu độ chính xác cao.

## 9. Ví dụ Java hoàn chỉnh

Ví dụ sau kết hợp các thao tác Java 9 trên cả ba primitive stream và phép chuyển đổi từ object stream. Mã sử dụng **Stream.toList()**, vì vậy cần Java 17+.

Tạo tệp **PrimitiveStreamImprovements.java**:

```java
import java.util.List;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.Stream;

public class PrimitiveStreamImprovements {
    public static void main(String[] args) {
        List<Integer> prefix = IntStream.of(1, 2, 3, 4, 5, 1, 2)
                .takeWhile(n -> n < 4)
                .boxed()
                .toList();
        System.out.println("takeWhile: " + prefix);

        List<Integer> remaining = IntStream.of(1, 2, 3, 4, 5, 1, 2)
                .dropWhile(n -> n < 4)
                .boxed()
                .toList();
        System.out.println("dropWhile: " + remaining);

        int filteredSum = IntStream.of(1, 2, 3, 4, 5, 1, 2)
                .filter(n -> n >= 4)
                .sum();
        System.out.println("filter sum: " + filteredSum);

        System.out.print("iterate: ");
        LongStream.iterate(1L, n -> n <= 16, n -> n * 2)
                .forEach(n -> System.out.print(n + " "));
        System.out.println();

        double average = DoubleStream.of(1.5, 2.0, 2.5, 0.5, 3.0)
                .takeWhile(value -> value < 3.0)
                .average()
                .orElse(0.0);
        System.out.println("double average: " + average);

        int parsedSum = Stream.of("12", "7", "5")
                .mapToInt(Integer::parseInt)
                .sum();
        System.out.println("parsed sum: " + parsedSum);
    }
}
```

Biên dịch và chạy:

```bash
javac PrimitiveStreamImprovements.java
java PrimitiveStreamImprovements
```

Stdout chính xác:

```text
takeWhile: [1, 2, 3]
dropWhile: [4, 5, 1, 2]
filter sum: 9
iterate: 1 2 4 8 16
double average: 1.625
parsed sum: 24
```

## 10. Lỗi thường gặp

1. **Nhầm takeWhile với filter**: **takeWhile** dừng tại phần tử đầu tiên không thỏa; **filter** tiếp tục kiểm tra phần còn lại.
2. **Nhầm dropWhile với filter ngược điều kiện**: **dropWhile** chỉ bỏ tiền tố thỏa điều kiện, sau đó giữ mọi phần tử còn lại.
3. **Giả định dữ liệu đã được sắp xếp**: stream không tự sắp xếp. Các thao tác while dựa trên encounter order, không dựa trên giá trị lớn nhỏ.
4. **Quên điều kiện áp dụng cho seed trong iterate**: nếu **hasNext(seed)** là false, stream rỗng.
5. **Dùng iterate hai tham số mà quên giới hạn**: overload **iterate(seed, next)** vẫn tạo luồng vô hạn; hãy dùng **limit** hoặc overload ba tham số có điều kiện dừng.
6. **Dùng predicate sai kiểu**: **IntStream** nhận **IntPredicate**, **LongStream** nhận **LongPredicate**, **DoubleStream** nhận **DoublePredicate**.
7. **Boxing không cần thiết**: chuyển sang **boxed()** quá sớm làm mất lợi ích xử lý primitive. Hãy giữ pipeline primitive cho đến khi thật sự cần object.
8. **Không xử lý luồng rỗng**: **average()**, **min()** và **max()** trả Optional; cần xử lý trường hợp không có kết quả.
9. **Quên tràn số**: dùng **IntStream.sum()** khi tổng có thể vượt giới hạn **int** dẫn đến kết quả tràn. Hãy dùng **LongStream** khi miền giá trị yêu cầu.
10. **Giả định unordered vẫn giữ tiền tố**: trên unordered stream, kết quả của **takeWhile** và **dropWhile** không đảm bảo tiền tố như ordered stream.

## Kết luận

Primitive stream giúp xử lý dữ liệu số trực tiếp bằng **int**, **long** và **double**, giảm boxing và cung cấp các phép toán số học chuyên biệt. Từ Java 9, **takeWhile**, **dropWhile** và overload **iterate(seed, hasNext, next)** giúp diễn đạt rõ việc lấy/bỏ tiền tố và sinh dữ liệu có điều kiện dừng.

Khi áp dụng, hãy chọn đúng primitive stream, hiểu sự khác nhau giữa while và filter, kiểm soát thứ tự encounter, xử lý Optional và phạm vi số học. Giữ pipeline ở dạng primitive trong phần tính toán và chỉ chuyển sang object khi API hoặc cấu trúc dữ liệu tiếp theo thực sự cần.
