# Chi phí tách, gộp, boxing và thao tác chặn nhập xuất trong Java Parallel Stream

`parallelStream()` và `stream().parallel()` cho phép Java Stream **phân chia công việc xử lý dữ liệu** để nhiều tác vụ có thể thực thi đồng thời. Tuy nhiên, **xử lý song song không mặc nhiên nhanh hơn xử lý tuần tự**. Với một pipeline nhỏ, một phép biến đổi quá nhẹ, nguồn khó chia, bước gộp đắt đỏ, nhiều boxing/unboxing hoặc nhiều thao tác I/O chặn, thời gian và tài nguyên phụ trội của parallel stream có thể lớn hơn phần công việc tiết kiệm được.

Bài học tập trung vào bốn nhóm chi phí:

1. **Tách (*splitting*)**: phân chia nguồn bằng `Spliterator`, tạo nhiều phần công việc đủ lớn và tương đối cân bằng.
2. **Gộp (*combining*)**: hợp nhất kết quả cục bộ của `reduce`, `collect` hoặc các thao tác có trạng thái; càng khó gộp càng dễ mất lợi ích song song.
3. **Boxing/unboxing**: chuyển qua lại giữa `int/long/double` và `Integer/Long/Double`, gây thêm đối tượng, truy cập bộ nhớ và áp lực GC trong một số pipeline.
4. **I/O chặn (*blocking input/output*)**: chờ tệp, mạng, database hoặc một tài nguyên bên ngoài, làm tác vụ chiếm thời gian chờ thay vì dùng CPU; có thể làm thiếu worker cho các công việc khác khi dùng pool chung.

**Nguyên tắc:** Song song thường phù hợp với lượng lớn dữ liệu **dễ chia**, xử lý **CPU-bound**, độc lập và có kết hợp kết quả hiệu quả. Hãy xem toàn bộ pipeline, nguồn, terminal operation và môi trường chạy trước khi chọn `parallel()`.

Các ví dụ được thiết kế cho **Java 17 trở lên**. Chúng minh họa hành vi và tính đúng; không suy ra tốc độ tăng bao nhiêu từ những ví dụ có dữ liệu nhỏ.

## 1. Pipeline song song thực sự làm gì?

Một `Stream<T>` có thể ở chế độ tuần tự (*sequential*) hoặc song song (*parallel*):

~~~java
// Đoạn minh họa trong một phương thức, data là List<Integer>.
long a = data.stream()
        .mapToLong(Integer::longValue)
        .sum();

long b = data.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

long c = data.stream()
        .parallel()
        .mapToLong(Integer::longValue)
        .sum();
~~~

Ba biểu thức cùng có mục tiêu là tính tổng theo `long`; khác biệt là **chế độ thực thi** của pipeline. `Collection.parallelStream()` tạo parallel stream từ collection; `stream().parallel()` đánh dấu pipeline hiện tại là parallel. `sequential()` có thể đổi chế độ về tuần tự.

Parallel stream **không phải** “mỗi phần tử một thread” và cũng không bảo đảm số thread bằng số lõi CPU. JDK thường thực thi các tác vụ bằng cơ chế fork/join, thường sử dụng **`ForkJoinPool.commonPool()`** cùng thread gọi ban đầu tùy tình huống. Số task, việc chia lại và cách lịch chạy là chi tiết của runtime, không phải hợp đồng cho code nghiệp vụ dựa vào.

Mô hình khái niệm:

~~~text
                         nguồn dữ liệu
                              │
                      Spliterator chia
                       ┌──────┴──────┐
                    phần A          phần B
                      │                │
                filter/map...     filter/map...
                      │                │
                 kết quả A        kết quả B
                       └──────┬───────┘
                           combiner
                              │
                         kết quả cuối
~~~

Không phải pipeline nào cũng dùng đúng một bước gộp. Những thao tác như `forEach` có thể thực hiện hành động độc lập; `reduce` và `collect` có thể có nhiều kết quả từng phần phải gộp; `sorted` có thể cần lưu và tổ chức một lượng dữ liệu đáng kể. **Chi phí là của cả pipeline**, không chỉ của lời gọi `parallel()`.

## 2. Mô hình chi phí: khi nào song song đáng giá?

Một mô hình gần đúng, để suy nghĩ chứ **không phải công thức thời gian chạy được JDK cam kết**:

~~~text
T_sequential ≈ T_work

T_parallel ≈ T_split + T_schedule
             + T_work_parallel
             + T_combine + T_sync
             + T_memory/boxing + T_other
~~~

Trong đó:

- `T_split`: tạo và chia việc thành những đoạn đủ nhỏ để xử lý song song.
- `T_schedule`: tạo/quản lý tác vụ, phối hợp và cân bằng tải.
- `T_work_parallel`: phần xử lý có ích, được rút ngắn nếu phân phối tốt lên nhiều lõi.
- `T_combine`: hợp các kết quả cục bộ.
- `T_sync`: chờ phối hợp, lưu giữ thứ tự, lock hoặc tranh chấp nếu có.
- `T_memory/boxing`: phân bổ đối tượng, băng thông bộ nhớ, boxing và garbage collection.
- `T_other`: I/O, cache miss, tải của hệ thống và các chi phí bên ngoài.

Nếu từng phần tử chỉ cộng một số nguyên nhỏ, `T_work_parallel` quá ít so với các chi phí phụ; parallel có thể **chậm hơn**. Nếu mỗi phần tử thực hiện phép toán tính toán nặng, độc lập và nguồn chia hiệu quả, phần công việc có ích có thể đủ lớn để bù overhead.

Quy tắc Amdahl cũng cho thấy phần công việc không song song hóa được sẽ giới hạn mức tăng tốc. Nếu tỷ phần tuần tự là `s` và phần còn lại chạy lý tưởng trên `p` worker, giới hạn gần đúng là:

~~~text
speedup ≤ 1 / (s + (1 - s) / p)
~~~

Công thức giả định không có nhiều overhead và tải cân bằng; thực tế thường kém hơn vì tách/gộp, bộ nhớ và đồng bộ. **Không chọn `parallel()` chỉ vì dữ liệu có nhiều phần tử**; cần cả lượng công việc *trên mỗi phần tử* và khả năng chia/gộp phù hợp.

## 3. Chi phí tách: vai trò của `Spliterator`

`Spliterator<T>` là giao diện Java dùng để duyệt và **tách một nguồn** thành những phần có thể xử lý riêng. Những phương thức quan trọng:

- `trySplit()`: thử tách một phần dữ liệu khỏi phần hiện tại. Trả `null` nếu không thể tách phù hợp.
- `estimateSize()`: ước tính số phần tử còn lại trong phần hiện tại.
- `characteristics()` và `hasCharacteristics(...)`: mô tả đặc điểm như `SIZED`, `SUBSIZED`, `ORDERED`, `DISTINCT`, `SORTED`.

Nguồn như **mảng hoặc `ArrayList`** thường có khả năng chia theo đoạn có kích thước đã biết, giúp cân bằng tải. Một nguồn từ `Iterator` không biết trước kích thước hoặc một nguồn I/O tuyến tính có thể khó chia hơn, dù điều đó không có nghĩa mọi nguồn kiểu này đều không thể parallel.

Tạo file `SpliteratorSplitDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

public class SpliteratorSplitDemo {
    public static void main(String[] args) {
        ArrayList<Integer> numbers = new ArrayList<>(
                List.of(1, 2, 3, 4, 5, 6, 7, 8));

        Spliterator<Integer> right = numbers.spliterator();
        boolean sized = right.hasCharacteristics(Spliterator.SIZED);
        boolean subsized = right.hasCharacteristics(Spliterator.SUBSIZED);
        Spliterator<Integer> left = right.trySplit();

        long totalEstimated = right.estimateSize()
                + (left == null ? 0 : left.estimateSize());

        System.out.println("sized=" + sized);
        System.out.println("subsized=" + subsized);
        System.out.println("split=" + (left != null));
        System.out.println("totalEstimated=" + totalEstimated);
    }
}
~~~

~~~bash
javac --release 17 SpliteratorSplitDemo.java
java SpliteratorSplitDemo
~~~

Kết quả với `ArrayList` trong Java 17:

~~~text
sized=true
subsized=true
split=true
totalEstimated=8
~~~

Kết quả này **không** có nghĩa luôn cần tách càng nhỏ càng tốt. Mỗi phần quá nhỏ tạo nhiều task và chi phí phối hợp; mỗi phần quá lớn có thể để worker rảnh trong khi một worker còn phải làm nhiều việc. Bộ lập lịch và Spliterator cố cân bằng hai phía đó.

Nếu dữ liệu có phân bố không đều (một phần tử cần 1 ms, phần tử khác cần 1 giây), số phần tử mỗi nhánh bằng nhau **chưa chắc** đồng nghĩa lượng tính toán bằng nhau. Cần xét độ lệch chi phí, tính locality và khả năng thực hiện chia lại công việc.

## 4. Không phải nguồn nào cũng chia và mở lại tốt

So sánh nhanh:

| Nguồn | Đặc điểm thường gặp khi parallel | Rủi ro cần xem |
| --- | --- | --- |
| `int[]`, `long[]`, mảng object | Kích thước biết trước, dễ chia theo đoạn | Phân bổ công việc quá nhỏ; băng thông bộ nhớ. |
| `ArrayList` | Truy cập theo chỉ số, dễ chia | Đối tượng mutable bị sửa trong lúc duyệt. |
| `HashSet` | Có thể chia nhưng unordered | Không có encounter order xác định; locality và phân bố. |
| `LinkedList` | Không truy cập ngẫu nhiên như array | Chi phí chia/duyệt và truy cập bộ nhớ có thể cao hơn. |
| `Iterator` một lần | Có thể thiếu thông tin kích thước | Khó phân chia hiệu quả; không được tự động replay. |
| `BufferedReader.lines()`, nguồn socket | I/O và trạng thái nguồn | Thường có chờ blocking; quản lý đóng nguồn và giới hạn concurrency. |

Không suy ra hiệu năng chỉ từ tên cấu trúc dữ liệu: cần biết triển khai Spliterator cụ thể, độ lớn và tính chất của phép toán. `SIZED` và `SUBSIZED` hữu ích với thuật toán chia việc nhưng **không phải bảo đảm về tốc độ**.

Với stream vô hạn hoặc nguồn khó xác định điểm kết thúc, terminal operation cần kết quả toàn bộ (như `sorted().toList()`) có thể không kết thúc hoặc ngốn tài nguyên; `parallel()` không giải quyết bản chất đó.

## 5. Chi phí gộp: `reduce()` và `collect()` không miễn phí

Phần việc song song thường tạo các **kết quả cục bộ**. Nếu mục tiêu chỉ là tính tổng, gộp hai tổng cục bộ khá rẻ; nhưng nếu phải gộp những danh sách lớn, xây dựng `Map`, sắp xếp hoặc giữ thứ tự, chi phí gộp có thể đáng kể.

Ví dụ:

~~~java
// Minh họa: một Stream<Integer> mới cho từng biểu thức.
long total = numbers.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

List<Integer> sorted = numbers.parallelStream()
        .sorted()
        .toList();
~~~

Ở biểu thức thứ nhất, phép tổng theo `long` có tính kết hợp và trạng thái gộp tương đối nhỏ. Ở biểu thức thứ hai, `sorted()` phải xác định thứ tự toàn cục; đây là thao tác *stateful* và có thể yêu cầu thêm bộ nhớ, di chuyển/gộp dữ liệu.

Một collector custom thường có **supplier → accumulator → combiner → finisher**:

~~~text
supplier()            tạo vùng tích lũy A mới, trung lập
accumulator(A,T)      đưa từng T vào vùng A
combiner(A,A)         kết hợp hai vùng A
finisher(A)           chuyển A thành kết quả R
~~~

Trong parallel reduction, combiner có thể được gọi để gộp nhiều vùng. Nếu nó phải sao chép liên tục một cấu trúc lớn, lợi ích chia công việc sẽ giảm. Không đưa trạng thái dùng chung mutable vào supplier chỉ để “tiết kiệm gộp”: điều đó thường phá tính đúng khi chạy song song.

## 6. Ví dụ chạy được: bộ tích lũy độc lập và gộp rẻ

Tạo file `ParallelSummaryDemo.java`:

~~~java
import java.util.List;
import java.util.stream.Collector;

public class ParallelSummaryDemo {
    record Event(int score) {}
    record Report(long count, long total) {}

    static final class Acc {
        long count;
        long total;

        void add(Event event) {
            count++;
            total += event.score();
        }

        Acc merge(Acc other) {
            count += other.count;
            total += other.total;
            return this;
        }

        Report finish() {
            return new Report(count, total);
        }
    }

    static Collector<Event, Acc, Report> reportCollector() {
        return Collector.of(
                Acc::new,
                Acc::add,
                Acc::merge,
                Acc::finish);
    }

    public static void main(String[] args) {
        List<Event> events = List.of(
                new Event(2), new Event(3),
                new Event(5), new Event(7));

        Report serial = events.stream()
                .collect(reportCollector());
        Report parallel = events.parallelStream()
                .collect(reportCollector());

        System.out.println("serial=" + serial);
        System.out.println("parallel=" + parallel);
    }
}
~~~

~~~bash
javac --release 17 ParallelSummaryDemo.java
java ParallelSummaryDemo
~~~

Kết quả:

~~~text
serial=Report[count=4, total=17]
parallel=Report[count=4, total=17]
~~~

Ở đây `Acc::new` tạo vùng có `count=0` và `total=0`; `Acc::add` cập nhật cục bộ; `Acc::merge` cộng hai vùng. Tổng và đếm theo `long` là phép kết hợp phù hợp trong miền dữ liệu ví dụ. Record `Report` là kết quả cuối, không phơi ra vùng tích lũy mutable.

Ví dụ **không dùng `CONCURRENT`**. Điều này không ngăn nó chạy song song: framework có thể sử dụng các vùng độc lập và gộp sau. Nếu đánh dấu `CONCURRENT` nhưng lại cho nhiều tác vụ cùng sửa `long count` và `long total` thường, dữ liệu có nguy cơ race condition. Ngược lại, dùng `AtomicLong` vô điều kiện cũng không miễn phí: contention có thể làm suy giảm hiệu năng.

**Đừng coi mã trên là benchmark.** Bốn phần tử quá ít để kết luận parallel nhanh hay chậm; mục tiêu là chỉ ra thiết kế combiner đúng.

## 7. `Collector` nào làm chi phí gộp tăng?

Nhìn cấu trúc kết quả để đoán nguồn overhead:

- `summingInt`, `counting`, `summarizingInt`: vùng tích lũy nhỏ và combiner tương đối đơn giản; thường hợp với phép rút gọn.
- `toList()`, `toSet()`: có thể cần kết hợp dữ liệu từ nhiều vùng; tăng chi phí copy/memory và sức ép cấp phát.
- `groupingBy()`: có thể tạo nhiều Map trung gian, sau đó kết hợp các khóa và downstream collections; việc gộp Map lớn có thể tốn kém.
- `toMap()`: khi khóa trùng phải áp dụng merge function; logic merge đắt hoặc có side effect gây vấn đề.
- `sorted()`, `distinct()`: là thao tác trung gian *stateful*, có thể yêu cầu lưu trạng thái phối hợp trên toàn pipeline.

`Collectors.groupingByConcurrent()` và `toConcurrentMap()` có thể hữu ích trong trường hợp phù hợp, nhưng **không mặc định nhanh hơn**: concurrent map, contention, phân bố khóa và yêu cầu về thứ tự có chi phí riêng. Trên dữ liệu có ít khóa rất “nóng”, nhiều tác vụ cạnh tranh cùng các bucket có thể làm lợi ích song song biến mất.

**Lưu ý ngữ nghĩa:** `reduce` và `collect` khi chạy song song cần hàm kết hợp đúng hợp đồng (đặc biệt associative, stateless, non-interfering). Không dùng phép trừ hoặc logic phụ thuộc thứ tự callback làm toán tử rút gọn vì cách nhóm tác vụ có thể thay đổi kết quả.

## 8. Boxing/unboxing: từ primitive sang wrapper có thể rất đắt

Một stream object như `Stream<Integer>` chứa **tham chiếu tới `Integer`**; các primitive stream như `IntStream`, `LongStream` và `DoubleStream` xử lý trực tiếp giá trị nguyên thủy. Với pipeline số lớn, boxing và unboxing thêm công việc:

~~~text
int                --boxing-->   Integer
Integer            --unboxing--> int

IntStream           .boxed()           → Stream<Integer>
Stream<Integer>     .mapToInt(...)      → IntStream
IntStream           .asLongStream()     → LongStream
Stream<T>           .mapToLong(...)     → LongStream
~~~

Phải phân biệt **kết quả kiểu dữ liệu** với **hiệu năng**: JVM có thể tối ưu một phần cấp phát/boxing trong những tình huống cụ thể, nên không khẳng định mỗi phần tử luôn gây ra đúng một allocation. Tuy nhiên, generic `Stream<Integer>` đòi dữ liệu ở dạng object và có thể thêm áp lực bộ nhớ/GC so với một pipeline `IntStream` được thiết kế hợp lý.

Ví dụ đường vòng kém trực tiếp hơn:

~~~java
// Minh họa phép tổng long; không phải đoạn cần dùng để benchmark.
long total = java.util.stream.IntStream.rangeClosed(1, 100_000)
        .boxed()
        .mapToLong(Integer::longValue)
        .sum();
~~~

Ở đây `boxed()` đổi `IntStream` thành `Stream<Integer>`, rồi `mapToLong` unbox để trở lại primitive long. Nếu không cần `Integer` object, có thể giữ primitive:

~~~java
long total = java.util.stream.IntStream.rangeClosed(1, 100_000)
        .asLongStream()
        .sum();
~~~

Hai phép tính cho kết quả toán học giống nhau trong ví dụ, nhưng cách primitive tránh bước boxing ở mức thiết kế API.

## 9. Ví dụ chạy được: hai pipeline cùng kết quả, kiểu khác nhau

Tạo file `BoxingCostDemo.java`:

~~~java
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class BoxingCostDemo {
    public static void main(String[] args) {
        long primitive = IntStream.rangeClosed(1, 100_000)
                .asLongStream()
                .sum();

        long boxed = IntStream.rangeClosed(1, 100_000)
                .boxed()
                .mapToLong(Integer::longValue)
                .sum();

        long parallel = LongStream.rangeClosed(1, 100_000)
                .parallel()
                .sum();

        System.out.println("primitive=" + primitive);
        System.out.println("boxed=" + boxed);
        System.out.println("parallel=" + parallel);
    }
}
~~~

~~~bash
javac --release 17 BoxingCostDemo.java
java BoxingCostDemo
~~~

Kết quả:

~~~text
primitive=5000050000
boxed=5000050000
parallel=5000050000
~~~

Tổng `1 + 2 + ... + 100000 = 5000050000` **vượt giới hạn `int`** nhưng nằm trong `long`. Vì vậy các pipeline trên dùng `LongStream` hoặc chuyển sang long trước khi tổng hợp. Nếu thay bằng `IntStream.rangeClosed(...).sum()`, tổng kiểu `int` có thể tràn và làm sai kết quả.

Đừng nhìn stdout bằng nhau rồi kết luận hiệu năng bằng nhau. Để so tốc độ/GC, cần benchmark thực tế có warmup, dữ liệu đủ lớn, môi trường ổn định và kiểm soát dead-code elimination; JMH là công cụ phù hợp.

### Khi nào `boxed()` vẫn cần thiết?

Không phải mọi `boxed()` đều là lỗi. Bạn có thể cần `List<Integer>`, `Map<Integer,V>` hoặc API generic nhận `Integer`:

~~~java
// IntStream -> Stream<Integer> -> List<Integer>.
List<Integer> numbers = java.util.stream.IntStream.range(0, 5)
        .boxed()
        .toList();
~~~

Đây là **lựa chọn do yêu cầu dữ liệu đầu ra**. Chỉ nên tránh những bước chuyển `int → Integer → int` không phục vụ mục đích nào, đặc biệt trong phần tính toán nặng chạy rất nhiều lần.

## 10. Boxing và cấu trúc dữ liệu ảnh hưởng bộ nhớ, cache, GC

Khi có nhiều phần tử `Integer`, ngoài các giá trị số còn có:

- Tham chiếu object trong cấu trúc `Stream<Integer>`/collection;
- Chi phí đại diện object khi phải cấp phát wrapper mới;
- Truy cập gián tiếp tới vùng nhớ chứa object, ảnh hưởng cache locality;
- Hoạt động của garbage collector và áp lực bộ nhớ nếu đối tượng được tạo nhiều.

Với `int[]` hoặc `IntStream`, dữ liệu primitive thường có tổ chức gọn và liên tục hơn, hỗ trợ CPU xử lý tuần tự hiệu quả. Kết quả thực tế còn phụ thuộc JIT, escape analysis, cách collection lưu trữ và luồng dữ liệu.

**Không nói `Integer.valueOf` luôn tạo object mới.** Java có cache wrapper cho một số giá trị; JVM cũng có thể tối ưu boxing. Kết luận đúng là **API đòi boxing tạo khả năng phát sinh overhead**, nên thiết kế pipeline primitive khi thích hợp và **đo** trước khi tối ưu.

Một pipeline `parallel().boxed().map(...)` có thể tốn cả overhead song song và overhead boxing. Nếu phép xử lý thực tế quá nhẹ, hai nhóm chi phí chồng lên nhau và việc thêm nhiều core không giúp nhiều.

## 11. Thao tác chặn I/O: chờ không giống tính toán

Một tác vụ **CPU-bound** sử dụng CPU để tính toán. Một tác vụ **I/O-bound** có thể dành phần lớn thời gian **đợi** hệ thống bên ngoài:

- Gọi HTTP đồng bộ hoặc truy vấn database chặn.
- Đọc dữ liệu chậm từ mạng/ổ đĩa.
- Chờ khóa, semaphore, tài nguyên giới hạn.
- Gọi API bên ngoài có timeout dài.

Viết:

~~~java
// Mã giả: fetchBlocking là lời gọi mạng/database đồng bộ.
List<Result> results = ids.parallelStream()
        .map(id -> fetchBlocking(id))
        .toList();
~~~

**Không phải** vì pipeline đó chạy song song mà các thao tác mạng được quản lý tốt. Parallel stream thường gắn với cơ chế fork/join dùng pool chung; khi worker bị I/O chặn, worker đó không làm công việc CPU hữu ích trong thời gian chờ. Nhiều lời gọi blocking đồng thời còn có thể:

- Chiếm tài nguyên dùng chung với những parallel streams hoặc ForkJoin tasks khác.
- Gây hàng đợi, giảm khả năng xử lý của các công việc CPU.
- Làm quá tải connection pool, giới hạn API, quota hoặc backend database.
- Kéo theo timeout, retry, tranh chấp lock và gây hiệu ứng đuôi dài (*tail latency*).
- Gây khó kiểm soát giới hạn concurrency và cách hủy tác vụ.

Fork/join có một số cơ chế bù cho tác vụ bị chặn, ví dụ `ForkJoinPool.ManagedBlocker` khi được tích hợp đúng, nhưng **không được giả định** mọi API I/O tùy ý đều tự khai báo blocking để pool bù worker đầy đủ. Đừng dùng chi tiết triển khai như một lời hứa hiệu năng.

**Hướng xử lý thường phù hợp hơn:** giới hạn số lời gọi I/O đồng thời, quản lý timeout/hủy, và dùng executor hoặc API bất đồng bộ được thiết kế cho loại công việc đó.

## 12. Ví dụ chạy được: giới hạn đồng thời cho công việc chờ

Để minh họa cấu trúc điều phối các tác vụ blocking, có thể dùng `ExecutorService` với thread pool có kích thước giới hạn. Ví dụ dưới đây dùng `Thread.sleep` để **mô phỏng thời gian chờ I/O**, không phải chương trình gọi mạng thực.

Tạo file `BoundedBlockingDemo.java`:

~~~java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class BoundedBlockingDemo {
    public static void main(String[] args) throws Exception {
        List<Callable<String>> tasks = List.of(
                () -> { Thread.sleep(20); return "A"; },
                () -> { Thread.sleep(20); return "B"; },
                () -> { Thread.sleep(20); return "C"; }
        );

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            List<Future<String>> results = pool.invokeAll(tasks);
            for (Future<String> future : results) {
                System.out.println(future.get());
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac --release 17 BoundedBlockingDemo.java
java BoundedBlockingDemo
~~~

Kết quả:

~~~text
A
B
C
~~~

Với `newFixedThreadPool(2)`, cùng một lúc có **tối đa hai task thực thi trên pool đó**, dù có ba task. `invokeAll` chờ các task được hoàn thành; danh sách `Future` tương ứng **thứ tự gửi task**, nên stdout được in A, B, C bất kể task nào kết thúc trước. `shutdown()` yêu cầu giải phóng tài nguyên executor sau khi dùng.

**Đây không phải mẫu production đầy đủ.** Các tác vụ mạng thật cần timeout, chiến lược hủy/interrupt, giám sát queue, giới hạn request và xử lý lỗi; `newFixedThreadPool` có hàng đợi có thể tăng lớn nếu gửi quá nhiều việc. Trong ứng dụng có tải cao, thiết kế bounded queue/backpressure và chọn kích thước pool dựa trên giới hạn upstream/downstream là cần thiết.

Java còn có các API bất đồng bộ như `HttpClient.sendAsync`, `CompletableFuture` và non-blocking I/O. Việc chọn executor riêng hay API async phụ thuộc loại thao tác, thư viện, giới hạn concurrency và hợp đồng xử lý lỗi. **Không dùng parallel stream như mặc định cho mọi truy vấn HTTP/JDBC.**

## 13. Ordered stream và các thao tác duy trì thứ tự làm tăng chi phí

Khi nguồn có **encounter order** (ví dụ `List`, `IntStream.range`), một số thao tác phải duy trì thứ tự đó:

- `forEachOrdered` giữ thứ tự gặp khi phát hành hành động, có thể hạn chế mức song song hữu ích.
- `findFirst` tôn trọng thứ tự đầu với ordered stream; `findAny` có thể chọn một phần tử bất kỳ và thường cho phép nhiều tự do hơn.
- `limit(n)`, `skip(n)` trên ordered parallel stream có thể tốn phối hợp để chọn đúng vị trí.
- `takeWhile` trên ordered parallel stream phải giữ **tiền tố dài nhất** thỏa predicate; không đơn giản giống filter từng phần tử độc lập.
- `sorted` cần thiết lập thứ tự toàn cục; `distinct` có thể phải phối hợp loại trùng và bảo toàn ổn định tùy đặc điểm stream.

Ví dụ `ParallelOrderDemo.java`:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class ParallelOrderDemo {
    public static void main(String[] args) {
        List<Integer> squares = IntStream.rangeClosed(1, 8)
                .parallel()
                .map(n -> n * n)
                .boxed()
                .toList();

        System.out.println(squares);
    }
}
~~~

~~~bash
javac --release 17 ParallelOrderDemo.java
java ParallelOrderDemo
~~~

Kết quả:

~~~text
[1, 4, 9, 16, 25, 36, 49, 64]
~~~

`IntStream.rangeClosed` có encounter order; `toList()` của `Stream` giữ encounter order khi có. **Kết quả có thứ tự không có nghĩa từng lambda `map` đã chạy theo thứ tự đó**: việc đánh giá có thể diễn ra ở các worker khác nhau. Đừng dựa vào side effect của mapper để suy ra thứ tự thực thi.

Với `parallel().forEach(System.out::println)`, thứ tự các dòng có thể thay đổi. Nếu buộc phải có thứ tự tác động, dùng `forEachOrdered` hoặc thu kết quả rồi xử lý có trật tự, đồng thời chấp nhận chi phí phối hợp.

## 14. Một pipeline có thể tự làm mất lợi ích song song

Xem mẫu:

~~~java
// Minh họa, data là List<String> đã tồn tại.
List<String> result = data.parallelStream()
        .filter(s -> !s.isBlank())
        .map(String::trim)
        .sorted()
        .distinct()
        .limit(100)
        .toList();
~~~

Mỗi phần có chi phí khác nhau:

1. `filter` và `map` thường có thể xử lý từng phần tử độc lập, nhưng ở đây thao tác khá nhẹ.
2. `sorted` cần biết thứ tự toàn bộ tập phần tử hợp lệ.
3. `distinct` phải nhận diện trùng lặp, có thể giữ trạng thái toàn cục.
4. `limit(100)` sau `sorted` không biến toàn bộ công việc sắp xếp trước đó thành việc chỉ xử lý 100 phần tử đầu nguồn.
5. Việc gom và phát kết quả theo encounter order có thể thêm chi phí phối hợp và bộ nhớ.

Khi dữ liệu nhỏ, pipeline tuần tự có thể nhanh và đơn giản hơn. Khi dữ liệu lớn, cần đo và có thể cân nhắc thay thuật toán (ví dụ cấu trúc giữ top-k nếu đúng nghiệp vụ), thay vì chỉ thêm `parallel()`.

Đặt `unordered()` có thể giảm một số ràng buộc thứ tự **khi nghiệp vụ thật sự không cần encounter order**. Nhưng `unordered()` có thể thay đổi ý nghĩa của `limit`, `findAny`, `takeWhile` hoặc các phép chọn đầu, nên không sử dụng như mẹo tối ưu vô điều kiện.

## 15. Bộ nguyên tắc tránh race condition và sai kết quả

Một pipeline parallel **phải đúng về ngữ nghĩa trước khi bàn hiệu năng**:

- Hàm `map`, `filter` và accumulator nên **stateless** và **non-interfering**, không sửa nguồn đang duyệt.
- Tránh cập nhật `ArrayList`, `HashMap`, biến `int` dùng chung hoặc state không thread-safe trực tiếp từ `forEach` song song.
- Dùng `collect(Collectors.toList())`, `groupingBy` hoặc collector được thiết kế đúng thay vì tự chia sẻ một `ArrayList` mutable.
- Reducer/combiner cần **tính kết hợp**; phép trừ hoặc phép xử lý phụ thuộc số lần callback chạy có thể thay đổi kết quả khi cách chia/gộp thay đổi.
- Nếu dùng `ConcurrentHashMap`, `AtomicLong` hoặc lock, vẫn phải đánh giá contention; đúng về đồng bộ **không có nghĩa nhanh**.
- Không tự gắn `Collector.Characteristics.CONCURRENT` khi container và accumulator không an toàn cho cập nhật đồng thời.
- Không dựa vào việc JDK gọi supplier, accumulator, combiner **bao nhiêu lần** hay trên worker nào.

Ví dụ **sai**:

~~~java
// Sai: ArrayList không an toàn cho các add đồng thời.
List<Integer> shared = new java.util.ArrayList<>();
java.util.stream.IntStream.range(0, 10_000)
        .parallel()
        .forEach(shared::add);
~~~

Đoạn trên không được dùng làm cách thu kết quả. Có thể xảy ra mất phần tử hoặc hỏng cấu trúc dữ liệu, dù một lần chạy nhỏ có vẻ đúng.

Ví dụ **đúng**:

~~~java
List<Integer> values = java.util.stream.IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .toList();
~~~

Collector/terminal operation chịu trách nhiệm thu kết quả theo cơ chế phù hợp của Stream. Với dữ liệu cần `List<Integer>`, boxing ở đây là hợp lý do **kiểu kết quả bắt buộc**; nếu chỉ cần tổng số, ưu tiên primitive reduction.

## 16. Đo hiệu năng: tránh benchmark sai

Không kết luận hiệu quả của parallel stream chỉ bằng chạy `System.nanoTime()` một lần và in kết quả:

~~~java
// Phác thảo cách đo đơn giản, KHÔNG phải benchmark đáng tin:
long start = System.nanoTime();
// chạy tác vụ ...
long elapsed = System.nanoTime() - start;
~~~

Các yếu tố làm phép đo sai lệch gồm:

- JIT compilation, warmup, inlining, escape analysis.
- GC và heap pressure khác nhau giữa boxing/object stream và primitive stream.
- CPU turbo/thermal throttling, băng thông bộ nhớ, số core thực và tác vụ hệ thống.
- Kích thước dữ liệu quá nhỏ, dữ liệu cache nóng/lạnh.
- Tránh kết quả bị tối ưu hóa bỏ nếu phép tính không được sử dụng.
- Khác biệt giữa tốc độ throughput và latency của một yêu cầu.
- Contention với `ForkJoinPool.commonPool()` đang được ứng dụng khác sử dụng.
- I/O, network jitter, timeout và quota khi benchmark trực tiếp backend.

Dùng **JMH** để microbenchmark CPU: có warmup, nhiều iteration, nhiều fork khi thích hợp, tiêu thụ kết quả, cùng đầu vào và thống kê phân bố thời gian. Đối với hệ thống có I/O thực, ngoài benchmark hàm cục bộ còn cần đo end-to-end **latency p95/p99, throughput, queue, saturation, CPU, GC, số kết nối và timeout**.

Benchmark cần so ít nhất:

~~~text
A. sequential, primitive, ít stateful operation
B. parallel,   primitive, cùng thuật toán và đầu vào
C. sequential, boxed,     nếu đây là lựa chọn cần cân nhắc
D. parallel,   boxed,     nếu pipeline thực sự có boxing
~~~

Không có “ngưỡng số phần tử luôn phải parallel” áp dụng cho mọi ứng dụng. Một triệu phần tử với phép toán siêu nhẹ và một nghìn phần tử với phép toán CPU rất nặng có thể có quyết định khác nhau.

## 17. Bảng quyết định: chọn tuần tự, song song hay executor I/O?

| Tình huống | Mặc định nên cân nhắc | Lý do |
| --- | --- | --- |
| Vài trăm phần tử, phép toán `map/filter` nhẹ | `stream()` tuần tự | Overhead tách/lịch/gộp dễ vượt lợi ích. |
| Mảng hoặc `ArrayList` lớn, biến đổi CPU nặng, độc lập | Benchmark `parallel()` | Nguồn dễ chia, công việc có ích đủ lớn. |
| Tổng `int/long/double` lớn | `IntStream/LongStream/DoubleStream` | Tránh boxing không cần thiết; reducer rẻ. |
| `groupingBy` có nhiều khóa trùng/nóng | Đo kỹ collector và contention | Gộp map hoặc cập nhật concurrent có thể rất đắt. |
| `sorted`, `distinct`, `limit` giữ encounter order | Xem lại toàn pipeline rồi benchmark | Phối hợp thứ tự và stateful operations có chi phí. |
| HTTP/JDBC/remote API đồng bộ, nhiều chờ | Executor I/O có giới hạn hoặc API async | Kiểm soát concurrency, timeout, backpressure tốt hơn. |
| Nguồn một lần từ network/socket | Xử lý một lượt hoặc pipeline I/O thích hợp | Không tự tạo khả năng chia/replay khi chỉ gọi parallel. |
| Yêu cầu thứ tự side effect nghiêm ngặt | Thiết kế tuần tự hoặc phối hợp rõ | `forEachOrdered` hạn chế tự do thực thi. |
| CPU và I/O trộn trong cùng pipeline | Tách giai đoạn nếu có giá trị | Mỗi giai đoạn có cách điều phối, giới hạn khác nhau. |

Một cách thiết kế dễ kiểm soát trong hệ thống thực là **đọc dữ liệu có giới hạn → xử lý CPU có thể song song → tổng hợp và ghi kết quả có kiểm soát**, thay vì vừa chạy parallel vừa gửi yêu cầu mạng chặn trong từng `map`.

## 18. Các lỗi thường gặp

1. **“Thêm `parallel()` luôn nhanh hơn.”** Sai: tách, schedule, combiner và GC có overhead.
2. **“Mỗi phần tử sẽ có một thread riêng.”** Sai: framework chia thành task và tái sử dụng worker; số task/thread là chi tiết thực thi.
3. **“ArrayList và iterator tách như nhau.”** Không: Spliterator và đặc tính nguồn quyết định hiệu quả chia việc.
4. **“Combiner không tốn thời gian.”** Sai: gộp Map/List lớn hoặc trạng thái có tranh chấp có thể rất đắt.
5. **“`Stream<Integer>` giống `IntStream` về chi phí.”** Chúng khác biểu diễn dữ liệu; object stream có thể có boxing/unboxing và pressure bộ nhớ.
6. **“`boxed()` luôn phải bỏ.”** Không: khi đầu ra cần `List<Integer>` hoặc API generic, boxing có lý do chính đáng.
7. **“`IntStream.sum()` không tràn.”** Sai: tổng `int` có thể overflow; chuyển sang long trước nếu cần.
8. **“Blocking HTTP/JDBC bên trong `parallel().map` sẽ tự mở rộng tốt.”** Không bảo đảm; common pool, connection pool, timeout và backend có giới hạn.
9. **“Chạy parallel trên collector custom mà không viết combiner đúng vẫn ổn.”** Có thể sai khi kết hợp các vùng tích lũy.
10. **“Đánh dấu `CONCURRENT` giúp collector luôn nhanh hơn.”** Sai khi accumulator không thread-safe hoặc contention cao.
11. **“Dùng `forEach` song song để thêm vào `ArrayList` chung.”** Không thread-safe; dùng collect phù hợp.
12. **“`forEach` song song giữ thứ tự nguồn.”** Không; nếu cần thứ tự side effect phải thiết kế lại/`forEachOrdered`.
13. **“`sorted().limit(10)` chỉ xử lý mười phần tử đầu.”** Không; sorted trước đó thường phải xử lý phạm vi lớn hơn để xác định top nhỏ nhất.
14. **“Một lần bấm đồng hồ xác định thuật toán nhanh nhất.”** Sai vì JIT, GC, môi trường và biến động hệ thống.
15. **“Tăng số worker vô hạn sẽ tăng throughput.”** Không: CPU, băng thông bộ nhớ, I/O, connection pool, lock và backend đều có giới hạn.

## 19. Checklist trước khi bật parallel stream

Hãy kiểm tra theo thứ tự:

1. Dữ liệu **lớn đến đâu** và mỗi phần tử cần **bao nhiêu tính toán CPU thực sự**?
2. Nguồn có **Spliterator dễ chia**? Có `SIZED/SUBSIZED` hoặc khả năng chia hợp lý không?
3. Phân bố chi phí giữa các phần tử có **cân bằng**? Có tác vụ rất chậm làm đuôi dài không?
4. Có thể **tránh boxing** bằng `IntStream/LongStream/DoubleStream` hoặc `mapToInt/mapToLong` không?
5. `reduce`/`collect` có **combiner rẻ, associative và đúng hợp đồng** không?
6. Có thao tác **stateful/ordered** nào làm hạn chế việc chạy đồng thời không?
7. Có gọi **HTTP/JDBC/file I/O chặn** trong mapper không? Có nên tách sang executor I/O với concurrency limit?
8. Nguồn và accumulator có tránh **shared mutable state**, race condition và side effect không?
9. Có rủi ro **overflow**, sai số `double`, thiếu bộ nhớ hoặc GC pressure không?
10. Đã đo **tuần tự so với song song** trên dữ liệu thực bằng benchmark thích hợp, quan sát throughput và latency chưa?

**Ghi nhớ:** hiệu năng parallel stream được quyết định bởi **lượng tính toán hữu ích trừ chi phí tách, lịch, gộp, boxing, bộ nhớ và chờ**. Chọn primitive stream khi tính toán số lớn, thiết kế combiner hiệu quả và tránh đưa blocking I/O không được kiểm soát vào common fork/join pool. Ưu tiên **tính đúng và phép đo thực nghiệm**, không mặc định `parallel()` là tối ưu hóa miễn phí.
