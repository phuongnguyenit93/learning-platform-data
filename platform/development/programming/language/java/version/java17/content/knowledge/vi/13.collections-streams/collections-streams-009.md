# Lựa chọn xử lý tuần tự hay song song dựa trên phép đo trong Java 17

Java Stream API cho phép xử lý một nguồn dữ liệu theo hai cách: **sequential stream** và **parallel stream**. Chỉ cần gọi parallel() là một pipeline có thể được thực thi qua nhiều worker thread, nhưng điều đó không có nghĩa chương trình luôn nhanh hơn. Chia việc, lập lịch, phối hợp, đồng bộ và gộp kết quả đều có chi phí. Với dữ liệu nhỏ hoặc mỗi phần tử xử lý rất nhanh, overhead có thể lớn hơn lợi ích của việc dùng nhiều lõi CPU.

Lựa chọn đúng cần dựa trên **đặc điểm workload và số liệu đo trong môi trường gần với thực tế**. Một pipeline nên chạy song song khi công việc có thể chia hiệu quả, mỗi phần đủ lớn để bù chi phí điều phối, các thao tác độc lập và việc gộp kết quả không tạo nút thắt. Nếu chưa đo, sequential là điểm xuất phát đơn giản và dễ dự đoán.

Java 17 có Stream API và parallel streams ổn định. Bài này tập trung vào cách phân tích, đo benchmark và đưa ra quyết định; không dùng tính năng preview.

## 1. Sequential stream và parallel stream khác nhau ở đâu?

Sequential stream xử lý pipeline theo chế độ tuần tự. Các phần tử được xử lý trong một luồng thực thi của pipeline, theo encounter order khi nguồn và thao tác có quy định thứ tự.

~~~java
long total = values.stream()
        .filter(value -> value > 0)
        .mapToLong(Integer::longValue)
        .sum();
~~~

Parallel stream chia công việc thành các phần và thực thi các phần đó trên nhiều worker thread, thường thông qua ForkJoinPool.commonPool() đối với các stream song song thông thường.

~~~java
long total = values.parallelStream()
        .filter(value -> value > 0)
        .mapToLong(Integer::longValue)
        .sum();
~~~

Hai đoạn trên biểu đạt cùng một phép tính nếu pipeline tuân thủ các yêu cầu của Stream API. Kết quả tổng số nguyên trong miền không overflow là như nhau; thời gian chạy có thể khác nhau tùy kích thước dữ liệu, chi phí xử lý mỗi phần tử, phần cứng và môi trường.

### Parallel không đồng nghĩa với mỗi phần tử một thread

Parallel stream không tạo một thread mới cho mỗi phần tử. Nguồn dữ liệu được chia thành các phần, các phần được đưa vào cơ chế thực thi song song và worker có thể xử lý nhiều phần theo lịch của pool. Số thread không nhất thiết bằng số phần tử hoặc số chunk.

Một pipeline song song có thể:

1. Chia nguồn dữ liệu thành các phần nhỏ hơn.
2. Lập lịch các phần đó cho worker.
3. Thực hiện các thao tác trung gian trên từng phần.
4. Tính kết quả cục bộ.
5. Gộp kết quả cục bộ thành kết quả cuối.

Việc chia và gộp cũng tiêu tốn CPU, cấp phát object hoặc đồng bộ. Với tác vụ nhỏ, phần chi phí này có thể vượt quá thời gian tính toán hữu ích.

## 2. Mô hình chi phí: khi nào song song có cơ hội nhanh hơn?

Có thể hình dung thời gian chạy song song như:

~~~text
Thời gian song song
  = chi phí khởi tạo/điều phối
  + thời gian xử lý các phần
  + chi phí đồng bộ và tranh chấp
  + chi phí gộp kết quả
  + ảnh hưởng của bộ nhớ, GC và hệ thống
~~~

Trong khi đó, tuần tự chủ yếu có:

~~~text
Thời gian tuần tự
  = thời gian duyệt nguồn
  + thời gian thực hiện các thao tác
  + chi phí cấp phát và bộ nhớ liên quan
~~~

Parallel chỉ có lợi khi phần công việc có thể chia được đủ lớn để tiết kiệm thời gian nhiều hơn tổng overhead. Một phép nhân đơn giản trên vài trăm phần tử thường không có đủ công việc để bù chi phí chia task. Một phép tính CPU nặng trên hàng triệu phần tử độc lập có thể tận dụng nhiều lõi tốt hơn.

### Amdahl's Law và phần việc không thể song song hóa

Nếu tỷ lệ công việc có thể song song hóa là P, phần không thể song song hóa là 1 - P, và có N worker lý tưởng, speedup tối đa được mô tả gần đúng:

\[
S(N) = \frac{1}{(1-P)+\frac{P}{N}}
\]

Ví dụ nếu 90% thời gian có thể song song hóa, còn 10% là tuần tự, thì ngay cả với số worker rất lớn, speedup vẫn bị giới hạn bởi phần 10% đó. Trong thực tế, overhead, tranh chấp và giới hạn bộ nhớ còn làm speedup thấp hơn mô hình lý tưởng.

Không nên chỉ nhìn số lõi CPU để dự đoán. Một pipeline có thể bị giới hạn bởi băng thông RAM, cache miss, allocation/GC, I/O hoặc một lock dùng chung thay vì khả năng tính toán của CPU.

## 3. Những workload thường có lợi từ parallel stream

Parallel stream đáng thử khi có nhiều phần tử, thao tác trên từng phần tương đối tốn CPU và các phần tử có thể xử lý độc lập.

Ví dụ:

- Tính toán số học hoặc biến đổi dữ liệu thuần túy trên tập dữ liệu lớn.
- Phân tích, tổng hợp dữ liệu trong bộ nhớ.
- Chuyển đổi ảnh hoặc dữ liệu số theo từng khối độc lập, nếu thuật toán và thư viện được dùng an toàn luồng.
- Tính các đặc trưng trên từng bản ghi mà không cần truy cập tài nguyên dùng chung có tranh chấp.
- Mô phỏng hoặc xử lý batch có thể chia thành các phần độc lập và gộp kết quả hiệu quả.

~~~java
long count = values.parallelStream()
        .filter(value -> expensivePredicate(value))
        .count();
~~~

Nếu expensivePredicate là phép tính CPU thuần, tốn thời gian và không có tác dụng phụ, pipeline có cơ hội sử dụng nhiều lõi.

Tuy nhiên, chữ “nặng” không đủ để kết luận. Nếu phép tính gọi một thư viện đồng bộ nội bộ hoặc đọc dữ liệu từ một vùng nhớ dùng chung có lock, nhiều worker có thể chỉ chờ nhau. Phải đo phần việc thực tế.

## 4. Những workload thường nên giữ tuần tự

Sequential thường phù hợp hơn khi:

- Nguồn dữ liệu nhỏ.
- Mỗi phần tử chỉ thực hiện một phép toán rất rẻ.
- Pipeline tạo nhiều object trung gian hoặc boxing/unboxing.
- Các phần tử phụ thuộc kết quả của phần tử trước.
- Logic cần thứ tự thực hiện chặt chẽ.
- Có nhiều trạng thái mutable dùng chung hoặc lock.
- Công việc chủ yếu chờ I/O hoặc gọi dịch vụ ngoài.
- Việc chia nguồn và gộp kết quả phức tạp hơn phần tính toán.

Ví dụ:

~~~java
int total = smallList.stream()
        .mapToInt(Integer::intValue)
        .sum();
~~~

Với một danh sách nhỏ, parallel có thể thêm overhead mà không giảm đáng kể thời gian.

### I/O-bound không tự động phù hợp với parallel stream

Nếu mỗi phần tử gọi HTTP, đọc file hoặc truy vấn database, thời gian phần lớn là chờ I/O. Dùng parallel stream có thể chiếm worker trong common pool trong lúc chờ, ảnh hưởng các công việc khác cũng dùng pool. Ngoài ra, số request đồng thời có thể vượt giới hạn connection pool hoặc rate limit của dịch vụ.

Với I/O, hãy xem xét API bất đồng bộ, executor chuyên dụng có giới hạn, cơ chế backpressure hoặc thiết kế batch phù hợp. Java 17 chưa có virtual threads chính thức; không đưa tính năng virtual thread của Java 21 vào mã Java 17. Parallel stream chủ yếu hướng tới chia công việc xử lý dữ liệu, không phải một bộ quản lý I/O concurrency tổng quát.

## 5. Nguồn dữ liệu và khả năng chia nhỏ

Parallel stream dựa vào khả năng chia nguồn. Stream API sử dụng Spliterator để duyệt và chia nguồn dữ liệu thành các phần.

Một nguồn có thể chia đều và nhanh thường thuận lợi hơn nguồn khó phân chia. Ví dụ:

| Nguồn | Khả năng chia thường gặp | Nhận xét |
| --- | --- | --- |
| Mảng | Tốt | Có kích thước và chỉ số rõ, chia đoạn nhanh |
| ArrayList | Tốt | Có thể chia theo vùng chỉ số |
| IntStream.range | Tốt | Miền số có thể phân đoạn dễ |
| HashSet/HashMap | Tùy dữ liệu và cấu trúc | Có thể chia nhưng kích thước bucket/phân bố ảnh hưởng cân bằng |
| LinkedList | Kém hơn mảng/ArrayList | Truy cập theo vị trí và chia đoạn có thể tốn hơn |
| Iterator tự viết | Phụ thuộc Spliterator | Nếu không hỗ trợ trySplit hiệu quả, song song khó tận dụng |
| I/O stream hoặc nguồn tuần tự | Thường khó | Phải cân nhắc chi phí đọc và khả năng phân vùng |

Spliterator có các đặc tính quan trọng:

- SIZED: biết chính xác số phần tử còn lại.
- SUBSIZED: các spliterator con cũng biết chính xác kích thước.
- ORDERED: có encounter order.
- DISTINCT: phần tử không trùng theo equals.
- SORTED: có thứ tự sắp xếp.
- IMMUTABLE: nguồn không thay đổi trong quá trình duyệt.
- CONCURRENT: nguồn hỗ trợ cập nhật đồng thời theo hợp đồng.

Các đặc tính này giúp Stream API lựa chọn chiến lược xử lý và tối ưu hóa. Không phải nguồn nào cũng có tất cả các đặc tính. Nếu viết Spliterator riêng, cần triển khai trySplit() có hiệu quả và khai báo characteristics() đúng với hành vi thực tế.

### Kiểm tra khả năng chia của nguồn

Có thể quan sát Spliterator:

~~~java
Spliterator<Integer> spliterator = values.spliterator();

System.out.println(spliterator.estimateSize());
System.out.println(spliterator.characteristics());

Spliterator<Integer> child = spliterator.trySplit();
System.out.println(child == null ? "Cannot split" : child.estimateSize());
~~~

Đây là công cụ tìm hiểu nguồn dữ liệu, không phải benchmark hoàn chỉnh. Việc trySplit() trả về một phần tử con không chứng minh pipeline song song sẽ nhanh hơn; còn phải đo chi phí thao tác và gộp.

## 6. Chi phí của các thao tác trung gian

Không phải pipeline có cùng số phần tử thì có chi phí như nhau. Hãy xem các yếu tố sau.

### Boxing và unboxing

Sử dụng Stream<Integer> có thể tạo chi phí boxing/unboxing so với IntStream:

~~~java
int boxedSum = values.stream()
        .mapToInt(Integer::intValue)
        .sum();

int primitiveSum = IntStream.of(array).sum();
~~~

Khi benchmark sequential và parallel, nên so sánh cùng một cách biểu diễn dữ liệu. Nếu một bên dùng primitive stream còn bên kia dùng boxed stream, kết quả đo không còn cô lập được ảnh hưởng của parallelism.

### Stateful operations

Các thao tác như sorted() hoặc distinct() có thể cần phối hợp dữ liệu giữa các phần. Chúng có thể tạo buffering, state hoặc chi phí gộp lớn.

~~~java
long count = values.parallelStream()
        .distinct()
        .sorted()
        .filter(this::expensivePredicate)
        .count();
~~~

Trong pipeline này, sorted() có thể không cần thiết nếu kết quả cuối chỉ là count. Việc loại bỏ thao tác không cần thiết thường có tác động lớn hơn chuyển sang parallel.

Hãy kiểm tra mục tiêu nghiệp vụ trước khi chọn chế độ thực thi. Không dùng parallel để che một pipeline có nhiều bước thừa.

### Giữ thứ tự

Các thao tác như forEachOrdered() giữ encounter order khi thực hiện hành động cuối, nhưng yêu cầu phối hợp và có thể hạn chế lợi ích song song.

~~~java
values.parallelStream()
        .map(this::transform)
        .forEachOrdered(this::writeResult);
~~~

Nếu đầu ra không cần thứ tự, forEach có thể giảm ràng buộc thứ tự, nhưng chỉ dùng khi tác dụng phụ và hợp đồng đầu ra cho phép. Không đổi forEachOrdered thành forEach nếu thứ tự là một phần yêu cầu.

Các thao tác như findFirst() cũng phải tôn trọng encounter order; findAny() có thể linh hoạt hơn trên pipeline song song nếu nghiệp vụ không cần phần tử đầu tiên.

## 7. Side effect, trạng thái dùng chung và tính đúng đắn

Parallel stream yêu cầu các thao tác không can thiệp trái phép vào nguồn và tránh stateful behavioral parameter. Predicate, Function, Consumer và các lambda nên càng thuần càng tốt: kết quả phụ thuộc vào đối số, không dựa vào trạng thái dùng chung thay đổi theo thời gian.

### Ví dụ sai: cập nhật ArrayList dùng chung

~~~java
List<Integer> results = new ArrayList<>();

values.parallelStream()
        .map(this::transform)
        .forEach(results::add); // Không an toàn
~~~

Nhiều thread cùng gọi add() trên ArrayList có thể gây race condition hoặc hỏng cấu trúc nội bộ. Không dùng collection mutable không thread-safe làm đích ghi chung trong forEach song song.

Dùng collector:

~~~java
List<Integer> results = values.parallelStream()
        .map(this::transform)
        .toList();
~~~

Stream.toList() có từ Java 16 và trả về danh sách không sửa được. Nếu cần list mutable:

~~~java
List<Integer> results = values.parallelStream()
        .map(this::transform)
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Collector thông thường có thể tích lũy vào các container cục bộ rồi kết hợp chúng theo hợp đồng collector. Đây là cách phù hợp hơn so với tự sửa một container dùng chung.

### Không dùng biến đếm mutable trong lambda song song

~~~java
long[] count = {0};

values.parallelStream().forEach(value -> {
    if (value > 0) {
        count[0]++; // Race condition
    }
});
~~~

Dùng count() hoặc reduction phù hợp:

~~~java
long count = values.parallelStream()
        .filter(value -> value > 0)
        .count();
~~~

Nếu cần thống kê nhiều giá trị, dùng collector hoặc reduction có accumulator/combiner đúng quy tắc thay vì sửa biến dùng chung.

### Collector và tính chất CONCURRENT

Collectors.toList() hoặc Collectors.toCollection() không yêu cầu một container mutable dùng chung được cập nhật đồng thời; framework có thể dùng các container cục bộ rồi gộp.

Collector có đặc tính CONCURRENT cho phép accumulator được gọi đồng thời trên cùng một container khi các điều kiện về collector và stream order phù hợp. Không tự gắn đặc tính này cho collector nếu container không hỗ trợ concurrent accumulation. Đặc tính UNORDERED cũng chỉ nên khai báo nếu kết quả không phụ thuộc encounter order.

### synchronized có thể xóa mất lợi ích song song

~~~java
Object lock = new Object();
List<Integer> results = new ArrayList<>();

values.parallelStream().forEach(value -> {
    int transformed = transform(value);
    synchronized (lock) {
        results.add(transformed);
    }
});
~~~

Đoạn mã có thể bảo vệ việc thêm vào list, nhưng tất cả thread vẫn phải tuần tự qua lock. Nếu phần lớn thời gian ở critical section, tăng số worker không tăng throughput. Ưu tiên collector được thiết kế đúng.

## 8. Đo hiệu năng đúng cách bằng JMH

Không nên quyết định sequential hay parallel bằng một lần gọi System.nanoTime() quanh pipeline. Kết quả có thể bị ảnh hưởng bởi:

- JIT compilation và tiered compilation.
- Class loading và khởi tạo dữ liệu.
- Warmup chưa đủ.
- Garbage collection.
- CPU frequency scaling và tải của hệ điều hành.
- Các tiến trình khác tranh CPU.
- ForkJoinPool.commonPool() đang bị tác vụ khác sử dụng.
- Kích thước dữ liệu hoặc cache state không đại diện.

JMH (Java Microbenchmark Harness) là công cụ chuyên dùng để benchmark JVM. Nó hỗ trợ warmup, measurement iterations, fork JVM, quản lý kết quả và các cơ chế giảm sai lệch benchmark.

### Ví dụ benchmark sequential và parallel

Ví dụ sau dùng mảng int cố định và tính tổng qua primitive stream. Đặt benchmark trong project riêng có dependency JMH phù hợp:

~~~java
import java.util.Arrays;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;

@State(Scope.Benchmark)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MILLISECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 8)
@Fork(3)
public class StreamModeBenchmark {

    @Param({"1000", "100000", "1000000"})
    public int size;

    private int[] values;

    @Setup(Level.Trial)
    public void setup() {
        values = new int[size];
        for (int i = 0; i < size; i++) {
            values[i] = (i * 31) % 1000;
        }
    }

    @Benchmark
    public long sequentialSum() {
        return Arrays.stream(values)
                .asLongStream()
                .sum();
    }

    @Benchmark
    public long parallelSum() {
        return Arrays.stream(values)
                .parallel()
                .asLongStream()
                .sum();
    }
}
~~~

JMH tiêu thụ giá trị trả về của benchmark để hạn chế việc JVM loại bỏ phép tính như dead code. Dữ liệu được tạo ở Level.Trial nên thời gian khởi tạo mảng không nằm trong mỗi lần đo pipeline. Cả hai benchmark dùng cùng mảng và cùng phép tính.

Để chạy, cấu hình JMH annotation processor và benchmark runner theo hướng dẫn của JMH trong build tool dự án. Kết quả AverageTime thường được đọc là thời gian trung bình mỗi invocation; cũng có thể chọn Throughput khi câu hỏi là số thao tác hoàn thành trong một đơn vị thời gian. Không so sánh hai số có mode hoặc đơn vị khác nhau.

### Những nguyên tắc khi dùng JMH

1. Dùng warmup iterations để JIT có thời gian tối ưu mã.
2. Dùng nhiều measurement iterations và nhiều fork để giảm phụ thuộc vào một trạng thái JVM.
3. Đưa dữ liệu/setup ra khỏi phương thức benchmark nếu setup không thuộc phần muốn đo.
4. Đo các kích thước dữ liệu khác nhau, không chỉ một trường hợp thuận lợi.
5. Trả kết quả hoặc dùng Blackhole để kết quả không bị loại bỏ.
6. Không chạy nhiều benchmark song song trên cùng máy nếu muốn so sánh CPU throughput một cách đáng tin cậy.
7. Ghi lại CPU, số core khả dụng, RAM, JDK, JVM flags, OS, container quota và phiên bản thư viện.
8. Lặp lại phép đo trên môi trường triển khai gần thực tế.

### Vì sao không nên benchmark bằng vòng lặp tự viết quá ngắn?

Một microbenchmark tự viết có thể vô tình đo thời gian JIT compile, allocation hoặc độ trễ của lần chạy đầu tiên. JIT có thể inline, constant-fold hoặc loại bỏ phần code không tạo kết quả quan sát được. Một lần đo ngắn có thể biến động nhiều hơn chênh lệch mà ta muốn phát hiện.

System.nanoTime() vẫn phù hợp để đo thời gian của một thao tác ứng dụng đủ dài trong profiling hoặc đo end-to-end, nhưng không phải cách đáng tin cậy để so sánh vi sai các pipeline JVM nhỏ. Với microbenchmark, dùng JMH.

## 9. Đo workload thực tế, không chỉ benchmark tổng hợp

Benchmark ví dụ giúp so sánh chi phí pipeline cơ bản, nhưng không đại diện mọi ứng dụng. Hãy đo với:

- Dữ liệu có kích thước và phân phối tương tự production.
- Cùng các bước filter/map/sort/reduce như pipeline thực tế.
- Cùng loại nguồn (ArrayList, mảng, map, file, v.v.).
- Cùng mức allocation và object graph.
- Cùng mức độ contention hoặc trạng thái dùng chung.
- Cùng giới hạn CPU, RAM và container quota.
- Cùng cấu hình common pool nếu ứng dụng phụ thuộc vào pool đó.

Ví dụ, pipeline lọc một triệu số nguyên có thể song song nhanh hơn, nhưng pipeline parse JSON lớn có thể bị giới hạn bởi allocation và GC. Pipeline đọc file có thể bị giới hạn bởi I/O. Một benchmark chỉ dùng phép cộng primitive sẽ không phản ánh các khác biệt này.

### Đo nhiều kích thước để tìm điểm hòa vốn

Không có một ngưỡng phần tử chung cho mọi máy và mọi pipeline. Một số workload có thể chỉ bắt đầu có lợi khi có hàng trăm nghìn phần tử; workload CPU nặng hơn có thể có lợi ở kích thước nhỏ hơn; thao tác rất nhẹ có thể không bao giờ có lợi đáng kể.

Hãy chạy benchmark với các mức tăng dần, ví dụ:

| Kích thước | Mục tiêu |
| ---: | --- |
| 100 | Nhìn thấy overhead cố định |
| 1.000 | Workload nhỏ |
| 10.000 | Workload trung bình |
| 100.000 | Workload lớn |
| 1.000.000 | Workload rất lớn |

Đây chỉ là các mức thử minh họa. Nên chọn phạm vi theo kích thước thật của dữ liệu ứng dụng. Vẽ hoặc ghi bảng thời gian theo kích thước để tìm nơi parallel bắt đầu có lợi, thay vì đo một kích thước rồi áp dụng kết luận cho tất cả.

## 10. Đọc kết quả benchmark

Giả sử benchmark thu được bảng minh họa:

| Số phần tử | Sequential (ms) | Parallel (ms) | Nhận xét |
| ---: | ---: | ---: | --- |
| 1.000 | 0,02 | 0,35 | Parallel chậm hơn vì overhead |
| 100.000 | 0,45 | 0,62 | Chưa bù được chi phí chia/gộp |
| 1.000.000 | 5,8 | 2,4 | Parallel có lợi ở workload này |
| 10.000.000 | 58 | 20 | Parallel tiếp tục có lợi, nhưng không đạt speedup lý tưởng |

Các con số trên chỉ là ví dụ minh họa, **không phải kết quả đo của một máy cụ thể và không dùng làm ngưỡng lựa chọn**. Khi đo thực tế, cần báo sai số hoặc độ biến động, không chỉ ghi một số trung bình.

### Speedup

Speedup được tính:

\[
\text{Speedup} = \frac{T_{sequential}}{T_{parallel}}
\]

Nếu tuần tự mất 20 ms và song song mất 5 ms, speedup là 4 lần. Điều đó không có nghĩa máy có bốn core hoặc thuật toán đã scale tuyến tính; chỉ là tỷ lệ thời gian trong phép đo đó.

### Không chỉ nhìn thời gian trung bình

Trong ứng dụng server, latency ở percentile cao (p95/p99), throughput tổng thể, CPU utilization, allocation rate và GC pause cũng quan trọng. Một parallel stream có thể giảm thời gian của một request đơn lẻ nhưng làm nhiều request cạnh tranh common pool, khiến p99 của cả dịch vụ xấu đi.

Benchmark cần phản ánh mục tiêu tối ưu: thời gian của một batch, throughput toàn hệ thống, latency mỗi request hay mức tiêu thụ CPU.

## 11. ForkJoinPool.commonPool và ứng dụng server

Parallel stream thường dùng ForkJoinPool.commonPool(). Đây là pool dùng chung trong JVM cho nhiều hoạt động Fork/Join, bao gồm một số API khác. Vì thế, một pipeline parallel stream có thể cạnh tranh với công việc song song khác.

Trong server:

- Nhiều request cùng chạy parallel stream có thể tạo áp lực lên common pool.
- Một pipeline có blocking I/O có thể giữ worker trong thời gian chờ.
- Tác vụ khác dùng common pool có thể bị chậm theo.
- Giới hạn CPU của container có thể thấp hơn số CPU vật lý mà máy báo cáo.
- Tăng parallelism không làm tài nguyên CPU thực tế tăng lên.

Không nên mặc định parallel stream là một executor riêng cho từng request. Cần hiểu pool thực tế, tải đồng thời và giới hạn triển khai.

### Cấu hình parallelism

ForkJoinPool.commonPool() có thể bị ảnh hưởng bởi thuộc tính hệ thống java.util.concurrent.ForkJoinPool.common.parallelism, nhưng thay đổi thuộc tính này tác động tới common pool của JVM và có thể ảnh hưởng nhiều thành phần khác. Không chỉnh một cách tùy tiện chỉ để làm một benchmark nhanh hơn.

Nếu cần quản lý rõ executor, giới hạn concurrency, cô lập workload hoặc điều khiển vòng đời tác vụ, hãy cân nhắc tự xây dựng pipeline bằng ExecutorService/ForkJoinPool phù hợp. Parallel stream không cung cấp một API tổng quát để truyền executor tùy ý vào mọi pipeline.

Một số phiên bản JDK có hành vi triển khai cụ thể khi một terminal operation được gọi trong một ForkJoinPool khác, nhưng không nên dựa vào chi tiết triển khai không được API Stream bảo đảm để thiết kế isolation. Nếu cần executor là một phần hợp đồng ứng dụng, quản lý task trực tiếp bằng API concurrency.

## 12. Cân bằng tải và độ lớn chunk

Một phần tử mất 1 microsecond và một phần tử khác mất 100 milliseconds sẽ tạo ra workload không đều. Nếu các chunk được chia theo số phần tử mà chi phí mỗi phần tử rất khác nhau, một worker có thể làm xong sớm trong khi worker khác vẫn còn nhiều việc.

ForkJoinPool dùng work-stealing để worker rảnh có thể lấy task từ worker khác. Cơ chế này giúp cân bằng tải, nhưng vẫn có overhead và không giải quyết mọi dạng tác vụ blocking hoặc phụ thuộc tài nguyên.

Khi viết thuật toán chia công việc riêng:

- Chọn chunk đủ lớn để giảm overhead.
- Tránh một task cực lớn khiến các worker khác nhàn rỗi.
- Đảm bảo việc chia dữ liệu không lặp lại hoặc bỏ sót phần tử.
- Tránh chia sẻ mutable state giữa các chunk.
- Đo nhiều threshold/chunk size với dữ liệu đại diện.

Với Stream API, framework quyết định cách chia qua Spliterator và cơ chế thực thi; người dùng không trực tiếp đặt kích thước chunk trong pipeline thông thường. Nếu cần kiểm soát chi tiết, cân nhắc ForkJoinTask hoặc executor chuyên biệt.

## 13. Tính đúng đắn phải được xác nhận trước hiệu năng

Một phiên bản song song nhanh hơn nhưng cho kết quả sai không phải tối ưu hóa thành công. Trước khi so sánh thời gian:

1. Chạy cả hai phiên bản với cùng input.
2. So sánh kết quả theo đúng hợp đồng.
3. Kiểm tra side effect, thứ tự và exception.
4. Kiểm tra dữ liệu biên và tải đồng thời.
5. Đo benchmark sau khi đã xác nhận tính đúng đắn.

### Associativity của reduction

Các reduction song song cần phép kết hợp có tính associative theo hợp đồng toán học của accumulator/combiner. Cộng số nguyên có thể overflow theo quy tắc wraparound của Java; nếu nghiệp vụ yêu cầu không overflow, phải dùng Math.addExact hoặc kiểu/thuật toán phù hợp. Cộng double không có tính kết hợp do làm tròn, vì vậy kết quả có thể khác khi nhóm phép tính khác nhau.

Ví dụ:

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

Nếu pipeline dùng tổng double song song, cần xác định sai số chấp nhận và thuật toán cộng phù hợp. Không khẳng định kết quả double phải bằng bit với pipeline tuần tự nếu thứ tự cộng thay đổi.

### Encounter order và kết quả

Một số thao tác giữ encounter order; một số thao tác như forEach có thể thực hiện theo thứ tự khác trong parallel. Nếu kết quả yêu cầu thứ tự, dùng thao tác và collector giữ đúng hợp đồng, chấp nhận overhead tương ứng.

Không dùng side effect để tạo một chuỗi kết quả dựa vào thứ tự worker chạy. Nếu cần thứ tự xác định, biểu diễn thứ tự như dữ liệu đầu ra hoặc dùng collector/operation có cam kết phù hợp.

## 14. Ví dụ: so sánh tuần tự và song song với predicate CPU-bound

Ví dụ sau minh họa pipeline kiểm tra số nguyên tố. Nó chỉ dùng để trình bày cách tạo hai đường chạy tương đương; không nên coi thuật toán kiểm tra số nguyên tố này là benchmark đại diện cho mọi ứng dụng.

~~~java
import java.util.stream.IntStream;

public class PrimeCount {

    static boolean isPrime(int number) {
        if (number < 2) {
            return false;
        }
        if (number % 2 == 0) {
            return number == 2;
        }
        for (int divisor = 3;
             divisor <= number / divisor;
             divisor += 2) {
            if (number % divisor == 0) {
                return false;
            }
        }
        return true;
    }

    static long sequentialCount(int limit) {
        return IntStream.rangeClosed(2, limit)
                .filter(PrimeCount::isPrime)
                .count();
    }

    static long parallelCount(int limit) {
        return IntStream.rangeClosed(2, limit)
                .parallel()
                .filter(PrimeCount::isPrime)
                .count();
    }

    public static void main(String[] args) {
        int limit = 1_000_000;

        long sequential = sequentialCount(limit);
        long parallel = parallelCount(limit);

        System.out.println("Sequential: " + sequential);
        System.out.println("Parallel: " + parallel);
        System.out.println("Same result: " + (sequential == parallel));
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 PrimeCount.java
java PrimeCount
~~~

Hai phương thức cùng kiểm tra miền số và cùng trả về count. Phép kiểm tra là CPU-bound và không thay đổi trạng thái dùng chung, vì vậy parallel có cơ hội tận dụng nhiều lõi. Dù vậy, thời gian cụ thể phụ thuộc CPU, JDK, tải máy và kích thước limit. Đo bằng JMH nếu cần kết luận hiệu năng.

## 15. Quy trình quyết định dựa trên phép đo

Một quy trình thực tế:

### Bước 1: Xây dựng phiên bản tuần tự đúng

Viết pipeline rõ ràng, tránh các bước không cần thiết. Dùng primitive stream nếu phù hợp, giảm boxing, và xác định rõ thứ tự cùng hành vi ngoại lệ.

### Bước 2: Phân tích khả năng song song

Hỏi:

- Công việc có độc lập theo phần tử/chunk không?
- Nguồn có thể chia nhanh và cân bằng không?
- Mỗi phần có đủ công việc CPU không?
- Có shared mutable state, lock hoặc I/O blocking không?
- Kết quả có cần encounter order không?
- Reduction có hợp đồng kết hợp phù hợp không?

### Bước 3: Viết phiên bản song song tương đương

Chỉ thêm parallel() khi pipeline có thể giữ đúng hợp đồng. Không thay đổi đồng thời thuật toán, cấu trúc dữ liệu và chế độ thực thi, vì sẽ khó biết yếu tố nào tạo khác biệt.

### Bước 4: Kiểm chứng tính đúng

So sánh kết quả của sequential và parallel trên input thông thường, input biên và tập dữ liệu đại diện. Kiểm tra side effect, thứ tự, exception và các điều kiện cạnh tranh.

### Bước 5: Benchmark bằng JMH

Đo nhiều kích thước, warmup, measurement, fork và cấu hình môi trường. Chạy sequential và parallel với cùng dữ liệu và cùng công việc. Theo dõi cả độ biến động, allocation và CPU.

### Bước 6: Đo trong môi trường triển khai

Nếu chạy trong container hoặc server, đo với CPU quota, tải đồng thời và common pool thực tế. Một benchmark trên laptop nhàn rỗi không đủ để kết luận cho production.

### Bước 7: Chọn theo lợi ích thực tế

Giữ parallel nếu mức cải thiện ổn định và đáng giá so với độ phức tạp/tài nguyên. Nếu lợi ích nhỏ, không ổn định hoặc gây ảnh hưởng workload khác, sequential thường dễ vận hành hơn.

## 16. Bảng quyết định nhanh

| Đặc điểm workload | Lựa chọn ban đầu | Điều cần đo/xác nhận |
| --- | --- | --- |
| Danh sách nhỏ, phép tính rẻ | Sequential | Overhead cố định |
| Mảng lớn, tính toán CPU độc lập | Thử parallel | Speedup theo kích thước |
| Dữ liệu lớn nhưng mỗi phần tử rất nhẹ | Sequential trước | Điểm hòa vốn |
| Pipeline có sort/distinct/group phức tạp | Đo cả hai | Chi phí stateful và gộp |
| Công việc chủ yếu gọi database/HTTP | Thiết kế I/O concurrency riêng | Connection pool, rate limit, latency |
| Có shared mutable state hoặc lock | Sửa thiết kế trước | Contention và tính đúng |
| Cần thứ tự đầu ra nghiêm ngặt | Sequential hoặc parallel có order | Chi phí forEachOrdered/collector |
| Nguồn khó chia | Sequential trước | Chất lượng Spliterator/trySplit |
| Tác vụ CPU-bound lớn, chia cân bằng | Parallel là ứng viên | Throughput và CPU saturation |
| Server nhiều request đồng thời | Cần benchmark tải hệ thống | Common pool, p95/p99, starvation |

## 17. Những sai lầm thường gặp

| Sai lầm | Vì sao có vấn đề | Cách xử lý |
| --- | --- | --- |
| Cho rằng parallel luôn nhanh hơn | Bỏ qua overhead chia/gộp và scheduling | Đo nhiều kích thước dữ liệu |
| Benchmark một lần bằng nanoTime | JIT, GC và tải máy gây nhiễu | Dùng JMH cho microbenchmark |
| Dùng dữ liệu quá nhỏ | Không đại diện workload thật | Chọn kích thước theo production |
| Dùng chung ArrayList trong parallel forEach | Race condition | Dùng collector phù hợp |
| Tăng biến đếm mutable trong lambda | Race condition hoặc cần atomic contention | Dùng count/reduction |
| Dùng parallel stream cho I/O blocking | Chiếm worker của common pool | Dùng async API hoặc executor có giới hạn |
| Bỏ qua thứ tự của forEach | Thứ tự chạy không được bảo đảm như encounter order | Dùng forEachOrdered khi thật sự cần |
| Bỏ qua chi phí sorted/distinct | Stateful operation có thể cần phối hợp | Xem pipeline và đo từng bước |
| So sánh hai pipeline không tương đương | Kết quả benchmark không có ý nghĩa | Giữ cùng dữ liệu và logic |
| Chỉ nhìn thời gian một request | Bỏ qua throughput và p99 toàn hệ thống | Đo dưới tải đồng thời |
| Dùng số liệu laptop để quyết định server | CPU quota, pool và môi trường khác | Benchmark trên môi trường gần production |
| Coi cùng kết quả double phải bằng bit | Reduction có thể đổi thứ tự cộng | Xác định tolerance/thuật toán |
| Chỉnh common pool toàn JVM cho một pipeline | Có thể ảnh hưởng các thành phần khác | Quản lý executor riêng nếu cần isolation |

## 18. Nguyên tắc lựa chọn

Khi lựa chọn tuần tự hay song song trong Java 17:

1. Bắt đầu bằng pipeline tuần tự rõ ràng và đúng.
2. Chỉ cân nhắc song song khi công việc có thể chia độc lập và nguồn dữ liệu chia hiệu quả.
3. Ước lượng chi phí thao tác trên mỗi phần tử so với overhead chia, lập lịch và gộp.
4. Tránh shared mutable state, side effect không an toàn và blocking I/O trong common pool.
5. Xem xét encounter order, stateful operations và tính đúng đắn của reduction.
6. So sánh các kích thước dữ liệu bằng JMH với warmup, measurement và fork phù hợp.
7. Đo trong môi trường triển khai, dưới tải thực tế và theo đúng chỉ tiêu cần tối ưu.
8. Chỉ giữ parallel khi lợi ích đo được ổn định và không gây tác động xấu đến hệ thống.

Parallel stream là một lựa chọn thực thi, không phải dấu hiệu mặc định của mã tốt hơn. Đối với một pipeline cụ thể, quyết định đáng tin cậy đến từ **tính đúng đắn trước, mô hình workload tiếp theo và số liệu đo cuối cùng**. Khi chưa có bằng chứng rằng song song giúp ích, sequential thường là lựa chọn đơn giản, dễ hiểu và dễ vận hành.
