# Stream.parallel() và parallelStream() trong Java

## 1. Mục tiêu bài học

**Parallel Stream** cho phép Java Stream API thực thi các phần của một pipeline trên nhiều luồng xử lý, chủ yếu nhằm khai thác nhiều lõi CPU khi dữ liệu đủ lớn và mỗi phần tử có công việc độc lập. Hai cách khởi tạo thường gặp là **`stream().parallel()`** và **`parallelStream()`**. Cả hai đều hướng đến pipeline có *chế độ parallel*, nhưng khác vị trí API, kiểu nguồn có thể sử dụng và thời điểm thay đổi chế độ.

Sau bài này, bạn sẽ hiểu cách dùng đúng hai API; biết điều gì được bảo đảm về kết quả, thứ tự và luồng thực thi; tránh race condition khi dùng trạng thái chia sẻ; lựa chọn `reduce`/`collect` an toàn; và xác định khi nào song song thật sự có lợi. Phạm vi là Java SE và concurrency của JDK, **không phụ thuộc Spring**. Ví dụ chương trình dùng Java 17+.

## 2. Câu trả lời trực tiếp: khác nhau ở đâu?

~~~java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);

var first = numbers.stream().parallel();
var second = numbers.parallelStream();
~~~

Đây là đoạn code minh họa bên trong phương thức, giả định đã import `java.util.List`. Với danh sách chuẩn của JDK, hai biểu thức đều tạo pipeline được đánh dấu **parallel**. Khác biệt cơ bản:

| Tiêu chí | `numbers.stream().parallel()` | `numbers.parallelStream()` |
| --- | --- | --- |
| Xuất phát từ | `Collection.stream()` tạo stream tuần tự, rồi `BaseStream.parallel()` chọn chế độ parallel | `Collection.parallelStream()` trực tiếp yêu cầu stream có thể chạy parallel |
| Vị trí API | `parallel()` là phương thức của `BaseStream`, dùng được trên `Stream`, `IntStream`, `LongStream`, `DoubleStream` | `parallelStream()` là phương thức của `Collection` |
| Đối tượng dùng được | Bất kỳ stream phù hợp đã có, kể cả stream từ mảng, `IntStream.range()`, `Stream.of()`, file, generator | Chỉ collection có `parallelStream()` |
| Có chạy tác vụ ngay khi gọi? | **Không** | **Không** |
| Trả về | Stream ở chế độ parallel, có thể là chính instance hiện tại theo contract | Stream từ collection; với một số implementation được phép trả stream tuần tự |
| Kết quả phép toán | Do cùng pipeline/source/terminal operation quyết định; chế độ parallel không tự đổi kết quả logic của các phép toán hợp lệ | Tương tự |

**Điểm tinh tế của đặc tả:** tài liệu `Collection.parallelStream()` ghi rõ *returns a possibly parallel Stream* và cho phép implementation trả về một stream tuần tự. Vì vậy với **custom collection**, không được suy luận tuyệt đối rằng mọi lần gọi `parallelStream()` đều khiến `isParallel()` là `true`. Với `ArrayList`, `List.of(...)` và các collection chuẩn thông thường, nó được triển khai theo hướng parallel.

Còn `parallel()` được dùng để **yêu cầu đổi execution mode** của một stream đã có. Bạn có thể xác nhận chế độ mong muốn bằng `stream.isParallel()`, nhưng đó **không phải phép đo số thread đã thực sự tham gia**, và không cam kết tác vụ sẽ chạy nhanh hơn.

## 3. Stream pipeline là lazy: parallel không kích hoạt xử lý tức thì

Một stream pipeline có ba thành phần:

1. **Source**: collection, array, `IntStream.range`, `Stream.of`, v.v.
2. **Intermediate operations**: `filter`, `map`, `sorted`, `distinct`, `parallel`, `sequential`...
3. **Terminal operation**: `sum`, `count`, `reduce`, `collect`, `toList`, `forEach`, v.v.

Các thao tác trung gian thường **lazy**: được mô tả trước và thực thi khi bắt đầu terminal operation. Gọi `parallel()` không tạo ngay một lô thread, không chạy `map` và không copy toàn bộ collection.

~~~java
// Trích đoạn trong một phương thức.
var pipeline = List.of(1, 2, 3, 4)
        .stream()
        .parallel()
        .map(n -> n * n); // Chưa chạy map vì chưa có terminal operation.

List<Integer> squares = pipeline.toList(); // Bắt đầu thực thi.
System.out.println(squares);                // [1, 4, 9, 16]
~~~

Với stream có **encounter order** như danh sách ở trên, `toList()` giữ thứ tự gặp ban đầu trong kết quả; không đồng nghĩa mọi lệnh `map` chạy tuần tự theo thứ tự đó.

Sau khi terminal operation tiêu thụ một stream, **không tái sử dụng cùng stream** cho terminal operation khác. Hãy tạo stream mới từ nguồn khi cần chạy phép tính tiếp theo.

## 4. Chương trình Java 17+ chạy độc lập

Lưu thành **`ParallelStreamBasics.java`**:

~~~java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ParallelStreamBasics {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4, 5);

        Stream<Integer> sequential = numbers.stream();
        Stream<Integer> switched = numbers.stream().parallel();
        Stream<Integer> direct = numbers.parallelStream();

        System.out.println("stream(): " + sequential.isParallel());
        System.out.println("stream().parallel(): " + switched.isParallel());
        System.out.println("parallelStream(): " + direct.isParallel());

        int sum = numbers.parallelStream()
                .mapToInt(Integer::intValue)
                .sum();
        System.out.println("sum: " + sum);

        List<Integer> squares = numbers.stream()
                .parallel()
                .map(n -> n * n)
                .toList();
        System.out.println("squares: " + squares);

        int firstEven = numbers.parallelStream()
                .filter(n -> n % 2 == 0)
                .findFirst()
                .orElse(-1);
        System.out.println("first even: " + firstEven);

        boolean lastMode = IntStream.rangeClosed(1, 5)
                .parallel()
                .sequential()
                .isParallel();
        System.out.println("after sequential(): " + lastMode);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ParallelStreamBasics.java
java ParallelStreamBasics
~~~

Kết quả dự kiến trên Java 17+ với `List.of` chuẩn:

~~~text
stream(): false
stream().parallel(): true
parallelStream(): true
sum: 15
squares: [1, 4, 9, 16, 25]
first even: 2
after sequential(): false
~~~

Đây là kết quả **xác định** của phép tính và contract sử dụng; số lượng/tên thread thực thi không được in vì phụ thuộc scheduler và runtime. Chương trình tạo ba stream để kiểm tra `isParallel()` rồi dùng các stream **mới** cho những terminal operation tiếp theo. `Stream.toList()` có từ Java 16 và trả list không thể sửa qua các phương thức biến đổi.

## 5. Chuyển execution mode bằng parallel() và sequential()

`BaseStream.parallel()` và `BaseStream.sequential()` điều chỉnh **chế độ của pipeline**. Khi một pipeline gọi nhiều lần để đổi mode, hãy hiểu mode hiệu lực tại terminal operation; **lệnh chọn mode cuối cùng** quyết định pipeline được yêu cầu xử lý tuần tự hay song song. Đừng diễn giải như từng stage có thể chạy với mode độc lập chỉ nhờ vị trí `parallel()` trong chuỗi.

~~~java
// Các biểu thức độc lập; không tái sử dụng stream đã tiêu thụ.
boolean a = List.of(1, 2, 3).stream().parallel().isParallel(); // true
boolean b = List.of(1, 2, 3).parallelStream().sequential().isParallel(); // false
boolean c = List.of(1, 2, 3).stream()
        .parallel()
        .sequential()
        .parallel()
        .isParallel(); // true
~~~

Một stream có `isParallel() == true` chỉ cho biết **execution mode**: JVM có thể dùng ít task nếu nguồn nhỏ hoặc không chia được, và thậm chí một số việc chạy trên thread gọi terminal operation. Bạn **không được** xem nó như một hợp đồng “mỗi phần tử chạy trên một thread” hay “luôn chạy đủ số core”.

`parallelStream()` chỉ xuất hiện trên collection. Khi nguồn không phải collection, dùng `parallel()`:

~~~java
long sum = IntStream.rangeClosed(1, 1_000_000)
        .parallel()
        .asLongStream()
        .sum();
~~~

Đoạn trên là minh họa bên trong phương thức. `IntStream.rangeClosed(...)` cho nguồn số nguyên chia được hiệu quả; `asLongStream()` trước `sum()` tránh tràn số ở miền `int` khi cộng một triệu số. Tổng toán học là **500000500000**.

## 6. Song song được triển khai như thế nào?

Đối với pipeline có khả năng parallel, Java Stream implementation thường:

- Dùng `Spliterator` của source để **chia dữ liệu** thành những phần nhỏ hơn.
- Đưa các phần việc độc lập vào cơ chế lập lịch fork/join.
- Chạy những phần việc trên nhiều thread khi có lợi và có tài nguyên.
- **Kết hợp** kết quả trung gian bằng `reduce`/`collect` hoặc quy tắc của terminal operation.

~~~text
Nguồn: [1, 2, 3, 4, 5, 6, 7, 8]
                 |
             split work
          /       |       \
       [1,2]    [3,4]   [5,6,7,8]
          \       |       /
           xử lý độc lập
                 |
          combine / collect
                 |
               kết quả
~~~

Ví dụ tính `sum()`: mỗi nhánh có thể tính tổng riêng rồi kết hợp. Điều này hiệu quả khi phép kết hợp **associative** và trạng thái từng nhánh không can thiệp lẫn nhau.

**Lưu ý về thread pool:** với OpenJDK hiện đại, parallel stream thông thường hay sử dụng worker của **`ForkJoinPool.commonPool()`** và có thể dùng cả thread gọi terminal operation. Tuy nhiên Streams API **không cung cấp hợp đồng** về số worker, tên thread hay một custom executor cho từng pipeline. Không thiết kế correctness dựa trên giả định “tất cả action luôn chạy trên commonPool worker” hoặc một mức parallelism cố định. Common pool là tài nguyên chia sẻ trong process; nhiều pipeline và tác vụ fork/join có thể ảnh hưởng lẫn nhau.

Có thể quan sát trên máy của bạn:

~~~java
// Đoạn minh họa; thứ tự và tập tên thread KHÔNG xác định.
IntStream.range(0, 10)
        .parallel()
        .forEach(i ->
                System.out.println(i + " / " + Thread.currentThread().getName()));
~~~

Không dùng thứ tự log của `forEach` để chứng minh lỗi: với pipeline parallel, thứ tự thực thi `forEach` là **không xác định**.

## 7. Encounter order và thứ tự thực thi

Đây là nguồn nhầm lẫn lớn nhất. **Encounter order** mô tả thứ tự logic của phần tử theo source/pipeline, không phải thứ tự các task được scheduler thực thi.

- `List` và `IntStream.range` thường **có encounter order**.
- Một số source như `HashSet` không hứa encounter order xác định.
- `parallel()` **không xóa** encounter order của source.
- `unordered()` cho phép pipeline bỏ ràng buộc về encounter order khi nghiệp vụ không yêu cầu; **không có nghĩa gọi `shuffle()`**.
- `forEach` trên parallel stream **không đảm bảo thứ tự xử lý**.
- `forEachOrdered` giữ thứ tự hành động theo encounter order nếu nguồn định nghĩa thứ tự, nhưng có thể làm giảm khả năng song song của phần terminal.
- `toList()`, `toArray()` và `findFirst()` tuân thủ semantics về thứ tự khi stream có encounter order phù hợp.
- `findAny()` cho phép trả **bất kỳ** phần tử khớp nào, hữu ích cho trường hợp không cần phần tử đầu tiên.

Ví dụ:

~~~java
List<Integer> data = List.of(5, 1, 4, 2, 3);

System.out.println(data.parallelStream().sorted().toList());
// [1, 2, 3, 4, 5]

System.out.println(data.parallelStream().filter(x -> x % 2 == 0)
        .findFirst().orElse(-1));
// 4: là số chẵn xuất hiện đầu tiên trong encounter order [5,1,4,2,3].

data.parallelStream().forEach(System.out::println);
// Có thể in các giá trị theo nhiều thứ tự khác nhau.

data.parallelStream().forEachOrdered(System.out::println);
// In 5,1,4,2,3 theo từng dòng đúng encounter order.
~~~

Đây là các đoạn đặt trong phương thức có import `java.util.List`, không phải ví dụ xác định stdout cho toàn bộ block vì dòng `forEach` biến thiên.

**Chi phí của việc giữ thứ tự:** `limit(n)`, `skip(n)`, `takeWhile`, `dropWhile` và `distinct` trên ordered parallel streams có thể cần phối hợp và buffering đáng kể. Khi bài toán cho phép bất kỳ (n) phần tử thay vì *n phần tử đầu*, có thể cân nhắc `unordered()` để giảm ràng buộc, nhưng **phải xác nhận nghiệp vụ chấp nhận thay đổi kết quả**.

## 8. Non-interference và stateless functions: điều kiện để song song an toàn

Các hàm truyền vào `map`, `filter`, `reduce`… nên thỏa:

1. **Non-interfering:** không sửa source trong lúc pipeline đang chạy (trừ những nguồn được thiết kế đồng thời theo hợp đồng riêng).
2. **Stateless:** kết quả cho từng phần tử không phụ thuộc trạng thái có thể bị thread khác thay đổi trong quá trình thực thi.
3. **Thread-safe nếu có state chia sẻ:** nếu buộc phải có side effect, tự bảo đảm đồng bộ và chấp nhận chi phí/giới hạn xác định.

**Ví dụ sai** vì nhiều worker cùng ghi một `ArrayList`:

~~~java
// KHÔNG chạy làm mẫu thu thập dữ liệu.
List<Integer> shared = new ArrayList<>();
IntStream.range(0, 10_000).parallel().forEach(shared::add);
// Race condition: kích thước/nội dung có thể sai, có thể có lỗi runtime.
~~~

**Cách đúng** dùng reduction do Stream quản lý:

~~~java
List<Integer> result = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .toList();
// Không cần tự đồng bộ ArrayList dùng chung.
~~~

`toList()` trả list không thể thêm/xóa/sửa bằng thao tác biến đổi. Nếu cần một danh sách mutable sau khi pipeline hoàn tất:

~~~java
List<Integer> mutable = new ArrayList<>(
        IntStream.range(0, 10_000).parallel().boxed().toList());
~~~

Hai đoạn đúng là các trích đoạn trong phương thức, cần import `java.util.ArrayList`, `java.util.List`, `java.util.stream.IntStream`.

**Sửa source đang stream** nguy hiểm cả ở chế độ sequential và parallel:

~~~java
// Không làm như sau:
List<Integer> source = new ArrayList<>(List.of(1, 2, 3));
source.parallelStream().forEach(source::remove);
~~~

Đây là vi phạm điều kiện non-interference, có thể gây hành vi không xác định hoặc exception. Ngay cả khi cấu trúc collection là concurrent, bạn vẫn phải nắm đúng semantics của iterator/spliterator và yêu cầu nghiệp vụ.

### Side effect trong peek/map có thể không chạy như bạn tưởng

Stream implementation có thể bỏ một số stage nếu chứng minh được kết quả terminal operation không đổi. Vì vậy **không dựa vào `peek` như bước bắt buộc để ghi database, gửi message hoặc tăng biến đếm**. Chẳng hạn, với source có kích thước biết trước, `count()` có thể tính nhanh số phần tử mà không gọi `peek`:

~~~java
long size = List.of(1, 2, 3)
        .parallelStream()
        .peek(x -> System.out.println("seen " + x))
        .count();
// size == 3; không được bảo đảm "seen" xuất hiện.
~~~

`forEach` được đặc tả là terminal side-effect operation, nhưng trên parallel stream việc thực hiện action có thứ tự và thread không xác định. Đối với biến đổi dữ liệu, ưu tiên `map` + `collect`/`toList`.

## 9. Reduce: kết hợp kết quả phải đúng đại số

`reduce(identity, accumulator)` chỉ có thể chia/ghép an toàn khi:

- `identity` là **phần tử đơn vị** của phép kết hợp.
- `accumulator` **associative**: `(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)`.
- Hàm không gây side effect, không truy cập state biến đổi bên ngoài.

Ví dụ đúng:

~~~java
int sum = IntStream.rangeClosed(1, 100)
        .parallel()
        .reduce(0, Integer::sum); // 5050
~~~

`0` là identity của phép cộng; cộng số nguyên (với ngữ nghĩa Java `int`) có tính kết hợp. `reduce` bằng phép trừ là **không an toàn về semantics** vì phép trừ không associative:

~~~java
// Không dùng làm một phép reduction song song hợp lệ.
int unexpected = IntStream.rangeClosed(1, 4)
        .parallel()
        .reduce(0, (left, right) -> left - right);
~~~

Tùy cách chia/ghép, kết quả có thể khác phép tính tuần tự mong muốn. Với `double`/`float`, phép cộng thực thi dưới độ chính xác dấu phẩy động **không associative hoàn toàn**, nên tổng parallel có thể khác ít bit do thứ tự làm tròn; nếu cần kết quả số học ổn định/độ chính xác cao, phải thiết kế phương pháp phù hợp.

Dạng `reduce(identity, accumulator, combiner)` đòi hỏi thêm compatibility giữa accumulator và combiner. **Đừng** nhét một đối tượng mutable như `ArrayList` vào `reduce` rồi mutate nó trên nhiều nhánh; dùng `collect`.

## 10. Collect: tổng hợp an toàn mà không chia sẻ mutable state

`collect` hỗ trợ mutable reduction, tạo container trung gian cho các nhánh và ghép chúng theo hợp đồng collector.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> words = List.of("java", "stream", "cpu", "parallel", "jdk");

Map<Integer, List<String>> grouped = words.parallelStream()
        .collect(Collectors.groupingBy(String::length));
// Map các nhóm từ theo độ dài; không nên phụ thuộc thứ tự in của HashMap.
~~~

Đoạn này là ví dụ đặt trong một phương thức, không phải class hoàn chỉnh. `Collectors.groupingBy` thông thường **không phải concurrent collector**; JDK vẫn có thể collect parallel an toàn bằng cách tổng hợp các kết quả trung gian rồi merge. Đừng suy ra rằng mọi collector phải là thread-safe mới dùng được với parallel stream.

Khi cần kết quả dạng concurrent map và semantics cho phép, tham khảo `Collectors.groupingByConcurrent` hoặc `toConcurrentMap`. Chúng có trade-off về thứ tự và mức contention, không mặc nhiên nhanh hơn `groupingBy` trên mọi workload.

Một trường hợp phổ biến:

~~~java
List<Integer> squares = IntStream.rangeClosed(1, 5)
        .parallel()
        .map(x -> x * x)
        .boxed()
        .toList();
// [1, 4, 9, 16, 25]; vẫn giữ encounter order.
~~~

**Tránh nhầm lẫn:** `Stream.toList()` trả list unmodifiable; `Collectors.toList()` **không cam kết** kiểu list, khả năng sửa hay thread-safety của kết quả. Nếu cần loại container cụ thể, dùng `Collectors.toCollection(ArrayList::new)` hoặc copy rõ ràng sau pipeline.

## 11. Khi nào song song nhanh hơn? Chi phí ẩn

Parallel stream có lợi khi các điều kiện cùng thuận lợi:

- Dữ liệu **đủ lớn** để chi phí tách việc và merge được bù lại.
- Phần tử có xử lý **CPU-bound, độc lập, tương đối nặng**.
- Source có `Spliterator` **dễ chia cân bằng**, ví dụ array, `ArrayList`, `IntStream.range`.
- Ít contention trên shared lock, counter, cache hoặc memory allocator.
- Số core và tài nguyên cho phép chạy song song, không có workload cạnh tranh chiếm hết CPU.
- Terminal operation không đặt quá nhiều rào cản về thứ tự.

Các chi phí cần tính gồm **task scheduling, splitting, merging, allocation, cache locality, memory bandwidth, synchronization và contention**. Với danh sách vài chục phần tử và phép `x * 2`, `parallelStream()` thường chậm hơn vòng lặp hoặc stream tuần tự vì overhead lớn hơn lợi ích.

Ví dụ chọn tuần tự cho phép tính nhỏ:

~~~java
List<Integer> tiny = List.of(1, 2, 3, 4);
int sum = tiny.stream().mapToInt(Integer::intValue).sum();
~~~

Parallel stream **không dành riêng cho I/O**: trong JDK hiện đại, worker fork/join thường là tài nguyên dùng chung, nên nhiều tác vụ **block lâu do HTTP, JDBC, file, socket, khóa** có thể chiếm worker và làm giảm khả năng xử lý pipeline khác. Khi cần điều phối số lượng lớn công việc blocking độc lập, xem các cơ chế concurrency chuyên dụng: `ExecutorService`, `CompletableFuture`, hoặc từ JDK 21 `Executors.newVirtualThreadPerTaskExecutor()`, cùng chính sách giới hạn tài nguyên I/O. Đó là bài toán khác với parallel data processing.

**Không dùng parallel stream như cách “tăng tốc” server một cách mặc định.** Lời gọi này có thể làm các request tranh CPU nhiều hơn dù latency của một request cải thiện trong benchmark đơn lẻ.

### Amdahl's law

Nếu một phần công việc bắt buộc tuần tự, tốc độ tăng tối đa có giới hạn. Với phần công việc song song hóa được là `p` và `N` worker lý tưởng:

~~~text
speedup <= 1 / ((1 - p) + p / N)
~~~

Ví dụ, với `p = 0.8` và `N = 4`, speedup lý tưởng tối đa `1 / (0.2 + 0.8/4) = 2.5`, **chưa trừ chi phí scheduling, memory và contention**. Công thức là mô hình tư duy, không phải phép dự đoán chính xác throughput của ứng dụng Java.

## 12. Source và Spliterator quyết định khả năng chia việc

Parallel stream được nuôi bởi `Spliterator`. Khả năng `trySplit()`, ước lượng kích thước và những đặc tính như `SIZED`, `SUBSIZED`, `ORDERED`, `CONCURRENT` ảnh hưởng đến cách runtime phân hoạch.

| Source | Xu hướng |
| --- | --- |
| `ArrayList`, array, `IntStream.range()` | Kích thước biết trước, thường chia tốt |
| `HashSet` | Không có encounter order bảo đảm; việc phân chia phụ thuộc spliterator |
| `LinkedList` | Khả năng phân chia và locality thường kém thuận lợi hơn array |
| Source sinh vô hạn hoặc không biết trước kích thước | Có thể khó chia cân bằng; một số pipeline cần rào cản lớn |
| Dữ liệu từ I/O `Files.lines()` | Còn chi phí đọc/đóng resource và giới hạn I/O, không mặc nhiên có lợi khi parallel |

Chính xác cần dùng benchmark thực tế với kiểu dữ liệu, kích thước và runtime của ứng dụng. Đừng suy ra chỉ từ `isParallel() == true` rằng Spliterator đã tạo số phần bằng số core.

Nếu sử dụng stream bọc resource như `Files.lines(path)`, đóng đúng hạn dù chế độ sequential hay parallel:

~~~java
// Trích đoạn trong phương thức có thể ném IOException.
try (var lines = java.nio.file.Files.lines(path)) {
    long count = lines.parallel().filter(s -> !s.isBlank()).count();
    System.out.println(count);
}
~~~

Đây là ví dụ về quản lý resource, **không phải khuyến nghị luôn dùng parallel khi đọc file**. Bảo đảm `path` tồn tại và đánh giá chi phí đọc thực tế.

## 13. Những vấn đề concurrency cần hiểu trước khi dùng trong sản phẩm

**Side effects và shared state.** Không đưa thao tác tăng counter, ghi vào list chung, sửa object chung vào `map/forEach` nếu chưa có chiến lược đồng bộ. Kể cả dùng synchronized để “sửa” race, chi phí lock có thể làm mất lợi ích parallel. Ưu tiên pipeline thuần và reduction.

**ThreadLocal và transaction context.** Hàm `map/filter/forEach` có thể chạy trên những thread khác nhau, không có bảo đảm rằng `ThreadLocal` của thread gọi sẽ tự lan sang worker. Không dựa vào thread identity để truyền request context hoặc giữ tài nguyên theo từng phần tử.

**Exception.** Exception từ action có thể khiến terminal operation thất bại; không được dự đoán chính xác phần tử nào chạy xong trước hoặc có bao nhiêu side effect đã xảy ra trước khi lỗi lan ra. Parallel stream không có cơ chế rollback side effects. Nếu action gây tác dụng bên ngoài, thiết kế idempotency và handling rõ ràng.

**Cancellation/timeout.** Stream API không cung cấp một deadline hoặc cancellation token cho mỗi `parallelStream()` giống một executor task. `limit`/`findAny` có short-circuit semantics, nhưng không phải cơ chế hủy tức thì mọi side effect đã chạy. Nếu cần thời hạn cứng, giám sát và hủy tác vụ, cân nhắc mô hình điều phối khác.

**Nested parallel streams.** Khi một pipeline parallel tạo thêm nhiều pipeline parallel lồng nhau, task scheduling/merge có thể tốn nhiều tài nguyên và khó dự đoán; không mặc định rằng số cấp parallel sẽ nhân lợi ích hiệu năng.

**ForkJoin common pool.** Không nên thay đổi global property parallelism cho common pool chỉ để tối ưu một phép tính; điều đó có thể ảnh hưởng nhiều tác vụ khác trong JVM. Stream API không có một đối số executor chuẩn cho `parallel()`.

## 14. Cách đo để quyết định dùng parallel hay sequential

Benchmark phải trả lời đúng câu hỏi: “Với nguồn, phép toán, số phần tử và tải CPU hiện có, bản parallel có cải thiện **throughput/latency thực tế** hay không?”

1. **Thiết kế hai bản cho cùng phép tính**, một bản `stream()`, một bản `parallelStream()` hoặc `stream().parallel()`, cùng input và cùng semantics.
2. **Làm ấm JIT** trước khi đo; JVM có thể tối ưu code qua nhiều lượt.
3. **Dùng JMH** (Java Microbenchmark Harness) cho microbenchmark nghiêm túc; tự đo với `System.nanoTime()` một vài lần rất dễ sai do JIT, GC, thread scheduling và dead-code elimination.
4. **Kiểm tra kết quả** hai bản giống nhau trước khi so tốc độ; đặc biệt để ý thứ tự, số thực và shared state.
5. **Đo nhiều kích thước dữ liệu và loại công việc**: phép toán nhẹ, CPU nặng, có contention, có I/O; xem điểm crossover nơi parallel bắt đầu đáng giá.
6. **Đo ở mức hệ thống** nếu chạy trong server: throughput, p95/p99 latency, CPU, allocation/GC và tác động khi nhiều request gọi parallel stream đồng thời.

Một biểu thức tính CPU thường phù hợp để đưa vào benchmark:

~~~java
// Hàm tính thuần, không side effect, minh họa workload CPU.
static long compute(long x) {
    long value = x;
    for (int i = 0; i < 200; i++) {
        value = value * 1664525L + 1013904223L;
    }
    return value;
}

static long calculateSequential(int size) {
    return java.util.stream.IntStream.range(0, size)
            .mapToLong(ParallelBenchmarkCandidate::compute)
            .sum();
}

static long calculateParallel(int size) {
    return java.util.stream.IntStream.range(0, size)
            .parallel()
            .mapToLong(ParallelBenchmarkCandidate::compute)
            .sum();
}
~~~

Đây là **trích đoạn phương thức trong class tên `ParallelBenchmarkCandidate`**, không phải benchmark JMH hoàn chỉnh. Hai bản tính cùng kết quả vì `compute` thuần và phép cộng trên `long` phù hợp cho reduction. Muốn đánh giá hiệu năng thực tế, đưa vào JMH, truyền dữ liệu từ benchmark state và bảo đảm kết quả được sử dụng để tránh tối ưu loại bỏ phép tính. Không gắn một con số “x lần nhanh hơn” khi chưa đo.

## 15. Các lỗi phổ biến và cách sửa

| Cách làm dễ sai | Vì sao sai/không phù hợp | Cách sửa |
| --- | --- | --- |
| Cho rằng `parallelStream()` luôn nhanh hơn `stream()` | Chi phí fork/join, merge và contention có thể lớn hơn lợi ích | Benchmark với dữ liệu thật |
| Cho rằng gọi `parallel()` chạy mọi phần tử ngay | Intermediate operation lazy | Hiểu terminal operation kích hoạt pipeline |
| Dùng `forEach` thêm dữ liệu vào `ArrayList` chung | Data race, kết quả lỗi | `collect`/`toList` hoặc reduction phù hợp |
| Giả định `forEach` giữ thứ tự | Parallel `forEach` không hứa thứ tự | Dùng `forEachOrdered` khi semantics yêu cầu, chấp nhận trade-off |
| Dùng phép trừ trong `reduce` | Không associative | Thiết kế hàm associative với identity đúng |
| Dùng `findAny` rồi kỳ vọng phần tử đầu | `findAny` không giữ thứ tự chọn | Dùng `findFirst` nếu cần đầu tiên |
| Coi `unordered()` là xáo trộn ngẫu nhiên | Chỉ bỏ yêu cầu về encounter order | Dùng chỉ khi semantics chấp nhận kết quả không giữ thứ tự |
| Dựa vào `ThreadLocal` của thread gọi | Worker có thể khác thread | Truyền dữ liệu context như tham số rõ ràng |
| Làm I/O blocking dài trong `parallelStream()` | Dễ làm bận worker chung, khó điều khiển timeout | Dùng concurrency API chuyên cho I/O |
| Coi lỗi ở một task là rollback toàn pipeline | Side effect đã thực hiện có thể không được hoàn tác | Tránh side effect hoặc có chính sách idempotency |
| Tùy biến toàn cục common pool cho một pipeline | Tác động các task khác | Cân nhắc thiết kế điều phối phù hợp và đo |

## 16. Tình huống lựa chọn nhanh

**Tình huống A — Tổng hợp hàng triệu số với phép toán CPU nặng, độc lập:** thử `IntStream.range(...).parallel().mapToLong(...).sum()`, sau đó benchmark với bản sequential. Đây là ứng viên tốt vì nguồn chia được, phép biến đổi không có trạng thái chia sẻ và kết quả có reduction.

**Tình huống B — Lấy 30 phần tử từ list và nhân đôi:** `list.stream().map(x -> 2 * x).toList()` thường đơn giản và ít overhead hơn. Không bật parallel chỉ vì viết được.

**Tình huống C — Gọi API cho từng phần tử:** không nên xem `parallelStream()` như một HTTP client concurrency manager có timeout/rate limit. Sử dụng cơ chế bất đồng bộ hoặc executor và giới hạn concurrency theo tài nguyên.

**Tình huống D — Phải giữ nguyên thứ tự kết quả:** `parallelStream().map(...).toList()` có thể trả đúng encounter order trong khi vẫn tính toán song song. Cân nhắc chi phí duy trì thứ tự; `forEachOrdered` khi cần thứ tự side effect nhưng thường giảm lợi thế song song.

**Tình huống E — Kết quả là Map hoặc nhóm dữ liệu:** ưu tiên `collect(Collectors.groupingBy(...))` hay collector phù hợp. Việc thu thập được thực hiện theo contract của collector, không cần tự tạo `HashMap` chung để mọi worker sửa cùng lúc.

## 17. Câu hỏi tự kiểm tra

**1. `collection.parallelStream()` khác gì `collection.stream().parallel()` về vị trí API?**  
`parallelStream()` thuộc `Collection`; `parallel()` thuộc `BaseStream` nên có thể bật parallel mode trên stream sinh ra từ nhiều loại source. Một custom collection được phép trả sequential stream từ `parallelStream()`.

**2. `list.stream().map(...).parallel()` có nghĩa phần `map` chạy sequential còn phần sau chạy parallel không?**  
Không. Execution mode là thuộc tính pipeline; cách cài đặt của stream có thể áp dụng cấu hình parallel cho việc xử lý toàn pipeline tại terminal operation.

**3. Vì sao `parallelStream().map(...).toList()` giữ thứ tự list nhưng `parallelStream().forEach(...)` có thể in lộn thứ tự?**  
`toList()` giữ encounter order của nguồn có thứ tự; `forEach` không yêu cầu tuân thủ thứ tự thực thi.

**4. `isParallel() == true` có đảm bảo nhiều thread được dùng không?**  
Không. Đó là chế độ được yêu cầu, không phải số worker đã thực thi.

**5. Nếu cần tìm phần tử đầu tiên thỏa điều kiện, dùng `findAny()` hay `findFirst()`?**  
`findFirst()` nếu nguồn có thứ tự và yêu cầu đúng phần tử đầu tiên. `findAny()` nếu kết quả bất kỳ đều chấp nhận.

**6. Tại sao `List<Integer> target = new ArrayList<>(); source.parallelStream().forEach(target::add)` nguy hiểm?**  
Nhiều thread có thể ghi `ArrayList` chung không đồng bộ. Dùng `collect`/`toList` thay vì side effect.

**7. Vì sao không luôn bật parallel trên server nhiều request?**  
Các pipeline có thể tranh CPU, worker fork/join, băng thông nhớ và tài nguyên downstream, làm p95/p99 latency xấu đi dù một request thử riêng có vẻ nhanh.

## 18. Tài liệu chính thức

- [Java SE 21 — Stream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html): pipeline, tính lazy, parallel operations, `forEach`, `forEachOrdered`, `reduce`, `collect`, `toList`.
- [Java SE 21 — BaseStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/BaseStream.html): `parallel()`, `sequential()`, `isParallel()`, `unordered()`.
- [Java SE 21 — Collection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collection.html): `stream()`, `parallelStream()` và điểm lưu ý “possibly parallel”.
- [Java SE 21 — java.util.stream package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html): stateless, non-interfering, reductions, ordering và performance.
- [Java SE 21 — Spliterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Spliterator.html): phân tách nguồn dữ liệu và các đặc tính.
- [OpenJDK — JMH](https://openjdk.org/projects/code-tools/jmh/): microbenchmark Java khi cần đo hiệu năng.

**Ghi nhớ:** `stream().parallel()` và `parallelStream()` thường đưa bạn đến cùng chế độ thực thi parallel trên collection chuẩn. Sự đúng đắn phụ thuộc vào pipeline thuần, không can thiệp nguồn, reduction hợp lệ và semantics thứ tự; hiệu năng chỉ được quyết định bằng phép đo với tải thực tế.
