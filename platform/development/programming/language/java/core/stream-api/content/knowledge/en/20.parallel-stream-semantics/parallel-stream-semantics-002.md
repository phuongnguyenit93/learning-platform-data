# Chuyển chế độ bằng sequential và kiểm tra bằng isParallel

## 1. Hai chế độ thực thi của một Stream pipeline

Trong **JAVA_STREAM_API**, lập trình viên mô tả cách xử lý dữ liệu bằng pipeline như `filter`, `map`, `reduce` và `collect`. Pipeline có thể được thực thi ở chế độ **tuần tự (sequential)** hoặc **song song (parallel)**. Java cung cấp hai operation để chọn chế độ, cùng một phương thức để kiểm tra trạng thái được cấu hình:

- `parallel()`: yêu cầu Stream chuyển sang chế độ song song.
- `sequential()`: yêu cầu Stream chuyển sang chế độ tuần tự.
- `isParallel()`: cho biết chế độ song song hiện tại của Stream, trả `boolean`.

Cả `parallel()` và `sequential()` đều trả về một Stream để nối tiếp pipeline; chúng **không** phải terminal operation và không tự duyệt dữ liệu. `isParallel()` chỉ kiểm tra trạng thái cấu hình, **không** chạy pipeline.

~~~text
Nguồn dữ liệu
     │
     ├─ stream() ─────────────► sequential mặc định
     │
     └─ parallelStream() ─────► parallel mặc định
                                     │
                     parallel() / sequential()
                                     │
                                     ▼
                             Chế độ của pipeline
                                     │
                      filter → map → sorted → ...
                                     │
                                     ▼
                         terminal operation
                           reduce / collect / toList
                                     │
                                     ▼
                            Kết quả cuối cùng
~~~

Bài thuộc chương **Ngữ nghĩa xử lý song song**. Mục tiêu không chỉ là nhớ tên API mà còn hiểu **thời điểm chế độ có tác dụng**, vì sao `isParallel() == true` không chứng minh có nhiều thread hoạt động, và vì sao song song hóa không được thay đổi kết quả nghiệp vụ khi các callback tuân thủ hợp đồng của Stream.

Các ví dụ dưới đây áp dụng cho **Java 17+**. `parallel()`, `sequential()` và `isParallel()` đều có từ Java 8.

## 2. Các API liên quan và kiểu trả về

Ba phương thức trên được khai báo trong `BaseStream<T, S extends BaseStream<T, S>>`, nên không chỉ `Stream<T>` mà cả `IntStream`, `LongStream` và `DoubleStream` đều hỗ trợ.

~~~java
// Dạng khái niệm của API trong BaseStream:
S sequential();
S parallel();
boolean isParallel();
~~~

| Phương thức | Loại thao tác | Kết quả | Ý nghĩa |
| --- | --- | --- | --- |
| `parallel()` | Đổi chế độ của Stream | Stream cùng loại | Đặt pipeline ở chế độ parallel |
| `sequential()` | Đổi chế độ của Stream | Stream cùng loại | Đặt pipeline ở chế độ sequential |
| `isParallel()` | Truy vấn trạng thái | `boolean` | Kiểm tra Stream đang được cấu hình parallel hay không |

Chú ý: `parallel()` **không** tự khởi động các thread ngay tại thời điểm được gọi, còn `sequential()` **không** có nghĩa là “đưa kết quả đã tính song song trở về một thread”. Các phép biến đổi trong Stream thông thường đều mang tính lazy cho đến khi có terminal operation.

Ví dụ kiểm tra kiểu Stream và chế độ:

~~~java
import java.util.List;
import java.util.stream.Stream;

public class CheckStreamMode {
    public static void main(String[] args) {
        Stream<Integer> serial = List.of(1, 2, 3).stream();
        System.out.println(serial.isParallel()); // false

        Stream<Integer> parallel = serial.parallel();
        System.out.println(parallel.isParallel()); // true

        Stream<Integer> backToSerial = parallel.sequential();
        System.out.println(backToSerial.isParallel()); // false

        System.out.println(backToSerial.toList()); // [1, 2, 3]
    }
}
~~~

Ở đây mỗi bước nối tiếp xây dựng **một pipeline duy nhất**, cuối cùng chỉ có **một terminal operation** là `toList()`. Không dùng các biến `serial` và `parallel` như hai Stream độc lập để chạy những terminal operation riêng.

## 3. stream() và parallelStream(): chọn chế độ từ nguồn

Với Collection, ta có hai cách thường gặp để bắt đầu:

~~~java
import java.util.List;

List<Integer> values = List.of(5, 3, 8, 2);

var serial = values.stream();
var parallel = values.parallelStream();

System.out.println(serial.isParallel());   // false
System.out.println(parallel.isParallel()); // true
~~~

`Collection.stream()` tạo Stream tuần tự, còn `Collection.parallelStream()` tạo Stream song song. Tuy nhiên, chế độ ban đầu **có thể đổi**:

~~~java
List<Integer> values = List.of(5, 3, 8, 2);

var changedToParallel = values.stream().parallel();
var changedToSerial = values.parallelStream().sequential();

System.out.println(changedToParallel.isParallel()); // true
System.out.println(changedToSerial.isParallel());   // false
~~~

Hai cách sau có thể mô tả cùng yêu cầu:

~~~java
long a = values.parallelStream()
    .filter(n -> n > 2)
    .count();

long b = values.stream()
    .parallel()
    .filter(n -> n > 2)
    .count();

// a == b == 3
~~~

Tuy vậy, **cùng kiểu kết quả không đồng nghĩa luôn có cùng hiệu năng** trong mọi trường hợp. Chi phí tách nguồn, cách các bước được tối ưu, và độ nặng của từng phép tính vẫn cần được đánh giá riêng.

### Khi nào dùng cách nào?

- Dùng `stream()` khi muốn pipeline tuần tự theo mặc định.
- Dùng `parallelStream()` khi ngay từ đầu đã biết xử lý song song là một lựa chọn phù hợp.
- Dùng `parallel()` hoặc `sequential()` khi muốn chọn chế độ dựa trên cấu hình hoặc điều kiện trong mã.
- Nếu đầu vào đã là một `Stream` được truyền vào từ bên ngoài, có thể dùng `sequential()` để yêu cầu cách thực thi tuần tự hoặc `parallel()` để yêu cầu song song, nhưng phải tôn trọng **quyền sở hữu và vòng đời sử dụng một lần của Stream**.

## 4. Chuyển chế độ: lời gọi cuối quyết định cách thực thi pipeline

Một điểm quan trọng: trong một pipeline Stream, `parallel()` và `sequential()` **không tạo ranh giới chạy song song/tuần tự riêng cho từng đoạn**. Chế độ của pipeline tại terminal operation mới quyết định chiến lược thực thi.

~~~java
import java.util.List;

List<Integer> numbers = List.of(1, 2, 3, 4, 5);

// Kết thúc thiết lập chế độ bằng sequential().
List<Integer> first = numbers.stream()
    .parallel()
    .map(n -> n * 2)
    .sequential()
    .filter(n -> n > 4)
    .toList();

System.out.println(first); // [6, 8, 10]
~~~

Không diễn giải ví dụ này thành “`map` chạy song song rồi `filter` chạy tuần tự”. Chế độ cuối cùng là **sequential** cho toàn pipeline khi terminal bắt đầu.

Ở chiều ngược lại:

~~~java
List<Integer> second = numbers.stream()
    .sequential()
    .map(n -> n * 2)
    .parallel()
    .filter(n -> n > 4)
    .toList();

System.out.println(second); // [6, 8, 10]
~~~

Trong pipeline thứ hai, yêu cầu cuối cùng là **parallel**; `toList()` vẫn giữ encounter order từ nguồn `List`. Hai kết quả giống nhau vì `map` và `filter` thuần túy và không phụ thuộc thứ tự thực thi callback.

### 4.1. Kiểm tra trạng thái cuối

~~~java
import java.util.stream.IntStream;

IntStream a = IntStream.range(0, 10)
    .parallel()
    .sequential();

IntStream b = IntStream.range(0, 10)
    .sequential()
    .parallel();

System.out.println(a.isParallel()); // false
System.out.println(b.isParallel()); // true
~~~

Có thể hình dung quy tắc:

~~~text
stream()
  ├─ parallel()           → parallel
  ├─ sequential()         → sequential
  ├─ parallel()           → parallel
  └─ terminal operation   → thực thi ở chế độ parallel

parallelStream()
  ├─ sequential()         → sequential
  └─ terminal operation   → thực thi ở chế độ sequential
~~~

**Đừng lạm dụng chuyển qua lại** trong cùng một pipeline. Chọn một chế độ rõ ràng, ở một vị trí dễ đọc, sẽ giúp kiểm thử và bảo trì dễ hơn.

### 4.2. Muốn thực sự có hai giai đoạn với chế độ khác nhau?

Nếu bài toán bắt buộc một giai đoạn thực thi tuần tự và giai đoạn khác thực thi song song, cần có **ranh giới materialize** và hai pipeline riêng; một lời gọi `sequential()` ở giữa pipeline duy nhất không thực hiện điều này.

~~~java
import java.util.List;

// Pipeline 1: hoàn thành tính toán tuần tự.
List<Integer> normalized = List.of(1, 2, 3, 4).stream()
    .map(n -> n * 10)
    .toList();

// Pipeline 2: một Stream mới trên kết quả đã materialize.
long total = normalized.parallelStream()
    .mapToLong(n -> (long) n * n)
    .sum();

System.out.println(total); // 3000
~~~

Cách tách giai đoạn tạo ra một Collection trung gian, có chi phí bộ nhớ và cấp phát. Chỉ làm vậy khi thực sự có yêu cầu về ranh giới xử lý, không phải như một tối ưu mặc định.

## 5. isParallel() kiểm tra điều gì, và không kiểm tra điều gì?

`isParallel()` cho biết chế độ của đối tượng Stream tại thời điểm truy vấn. Nó trả `true` nếu Stream được cấu hình cho thực thi song song và `false` nếu được cấu hình tuần tự.

~~~java
import java.util.stream.IntStream;

IntStream pipeline = IntStream.range(1, 6)
    .filter(n -> n % 2 == 1)
    .parallel();

System.out.println(pipeline.isParallel()); // true

int sum = pipeline.sum(); // 1 + 3 + 5 = 9
System.out.println(sum);  // 9
~~~

`isParallel()` **không có nghĩa**:

- Có bao nhiêu thread đang xử lý.
- Có thread mới đã được tạo.
- Mọi phép toán trung gian đều phải được gọi từ một thread khác.
- Parallel chắc chắn nhanh hơn sequential.
- Pipeline chắc chắn đã bắt đầu thực thi.
- Kết quả có thể thay đổi theo lịch thread mà vẫn đúng nghiệp vụ.

Một Stream được cấu hình parallel có thể thực hiện phần công việc trên chính thread gọi terminal operation; việc phân tách và lên lịch tùy thuộc JDK, môi trường và đặc điểm nguồn.

### 5.1. Không dùng tên thread để chứng minh chế độ API

~~~java
import java.util.stream.IntStream;

IntStream.range(0, 8)
    .parallel()
    .forEach(n ->
        System.out.println(Thread.currentThread().getName() + ": " + n)
    );
~~~

Đoạn mã có thể in nhiều tên thread và các số không theo thứ tự. Nhưng **đó chỉ là quan sát của một lần chạy**, không phải hợp đồng rằng luôn có số worker nhất định hay thứ tự in cố định. Ngược lại, thấy một thread trong một phép thử nhỏ cũng **không chứng minh `parallel()` bị bỏ qua**.

Nếu cần kiểm tra **trạng thái được cấu hình**, dùng `isParallel()`. Nếu cần kiểm tra **lợi ích hiệu năng**, đo với workload và dữ liệu đại diện. Nếu cần cam kết về thread, điều phối, giới hạn concurrency hoặc timeout, Stream parallel thường không phải API kiểm soát trực tiếp những yêu cầu ấy.

## 6. Chế độ thực thi không giống encounter order

**Parallel/sequential** và **ordered/unordered** là hai chiều khác nhau của pipeline.

- *Sequential/parallel* nói về chiến lược thực thi.
- *Ordered/unordered* nói về việc pipeline có phải giữ **encounter order** hay không.

| Cấu hình | Chế độ thực thi | Encounter order |
| --- | --- | --- |
| `list.stream()` | Sequential | Có từ nguồn `List` |
| `list.parallelStream()` | Parallel | Vẫn có từ nguồn `List` |
| `list.stream().unordered()` | Sequential | Bỏ ràng buộc |
| `list.parallelStream().unordered()` | Parallel | Bỏ ràng buộc |
| `list.parallelStream().sequential()` | Sequential | Vẫn có từ nguồn `List` |

`parallel()` **không tự gọi `unordered()`**. `sequential()` **không tự sắp xếp dữ liệu**. Nếu nghiệp vụ yêu cầu kết quả đầu ra theo thứ tự nguồn, phải xem xét encounter order của cả nguồn và pipeline.

### 6.1. toList() bảo toàn encounter order khi nguồn có thứ tự

~~~java
import java.util.List;

List<String> names = List.of("Chi", "An", "Bình");

List<String> result = names.parallelStream()
    .map(String::toUpperCase)
    .toList();

System.out.println(result); // [CHI, AN, BÌNH]
~~~

Mặc dù callback có thể được thực hiện song song, `toList()` phải bảo toàn encounter order khi Stream có thứ tự. Không dùng `parallel()` như cách xáo trộn danh sách.

### 6.2. forEach() và forEachOrdered() khác nhau

~~~java
import java.util.stream.IntStream;

// Không bảo đảm thứ tự thực thi action khi parallel:
IntStream.rangeClosed(1, 5)
    .parallel()
    .forEach(System.out::println);
~~~

Nếu cần action được thực thi theo encounter order, dùng:

~~~java
IntStream.rangeClosed(1, 5)
    .parallel()
    .forEachOrdered(System.out::println);

// In 1, 2, 3, 4, 5 theo thứ tự.
~~~

`forEachOrdered` giúp duy trì trình tự action theo encounter order, nhưng có thể hạn chế khả năng tăng tốc song song. Nếu mục tiêu chỉ là tạo một danh sách, `toList()` hoặc collector phù hợp thường là cách tốt hơn so với ghi vào một List mutable bên ngoài.

### 6.3. findFirst(), findAny() và short-circuit

~~~java
import java.util.List;
import java.util.Optional;

List<Integer> values = List.of(10, 20, 30, 40);

Optional<Integer> first = values.parallelStream()
    .filter(n -> n >= 20)
    .findFirst(); // Optional[20] vì nguồn ordered.

Optional<Integer> any = values.parallelStream()
    .filter(n -> n >= 20)
    .findAny(); // Có thể là 20, 30 hoặc 40.
~~~

`findAny()` cho phép lựa chọn phần tử bất kỳ, có thể thuận tiện cho song song. `findFirst()` phải tuân thủ encounter order khi có. Gọi `sequential()` hay `parallel()` không thay đổi yêu cầu đó.

`limit` và `skip` trên ordered parallel stream có thể đòi hỏi thêm phối hợp để xác định các phần tử đầu. Nếu không cần thứ tự, `unordered()` có thể giảm ràng buộc, nhưng đồng thời **thay đổi ngữ nghĩa**: `limit(3)` lúc đó có thể trả bất kỳ ba phần tử phù hợp.

## 7. Spliterator và nguồn quyết định khả năng chia việc

Stream không song song hóa bằng cách “tạo thread cho mỗi phần tử”. Khả năng phân hoạch dữ liệu phụ thuộc nhiều vào **`Spliterator` của nguồn** và cấu trúc pipeline.

~~~text
Collection / mảng / nguồn tùy chỉnh
                 │
                 ▼
             Spliterator
                 │
            trySplit()
           /          \
      Phần A          Phần B
         │               │
     xử lý riêng      xử lý riêng
         │               │
         └───────┬───────┘
                 ▼
             kết hợp
                 │
                 ▼
          terminal result
~~~

`Spliterator.trySplit()` có thể trả một Spliterator con hoặc `null` nếu không thể/không muốn chia. Các đặc tính như `SIZED`, `SUBSIZED` và `ORDERED` có thể ảnh hưởng đến chiến lược thực thi và chi phí phối hợp.

Ví dụ nguồn số có thể chia thành các khoảng:

~~~java
import java.util.stream.IntStream;

long total = IntStream.range(0, 100_000)
    .parallel()
    .asLongStream()
    .sum();

System.out.println(total); // 4_999_950_000
~~~

Một `IntStream.range` thường dễ phân hoạch hơn một nguồn dữ liệu tùy chỉnh phải gọi I/O tuần tự. Nhưng **không có cam kết `parallel()` luôn nhanh hơn**, kể cả với dải số: thời gian chia việc, kết hợp kết quả và khởi động xử lý có thể lớn hơn lợi ích khi phép toán quá đơn giản.

### Đặc tính nguồn không bảo đảm nhiều thread

Một nguồn có Spliterator **không chia được** vẫn có thể được cấu hình parallel:

~~~java
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.Iterator;
import java.util.List;
import java.util.stream.StreamSupport;

Iterator<Integer> iterator = List.of(1, 2, 3).iterator();

Spliterator<Integer> source =
    Spliterators.spliteratorUnknownSize(
        iterator,
        Spliterator.ORDERED
    );

var pipeline = StreamSupport.stream(source, true);
System.out.println(pipeline.isParallel()); // true

System.out.println(pipeline.toList()); // [1, 2, 3]
~~~

Trong ví dụ này, `true` xác định chế độ parallel. Nó không cam kết sẽ xử lý ba giá trị bằng ba thread hay nhanh hơn nguồn tương đương chạy tuần tự. Một số Spliterator còn có thể chia theo lô nội bộ dù không biết trước kích thước.

## 8. Các phép toán trung gian vẫn phải không trạng thái và không can thiệp

Một pipeline parallel đúng đòi hỏi các **behavioral parameters** (`Predicate`, `Function`, `BinaryOperator`, ...) tuân thủ yêu cầu của Stream API: **không can thiệp** vào nguồn đang được duyệt và, trong các trường hợp áp dụng, **không phụ thuộc state mutable dùng chung**.

### 8.1. Không dùng ArrayList chia sẻ để nhận kết quả

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

// Ví dụ CHỐNG CHỈ ĐỊNH: nguy cơ race condition.
List<Integer> shared = new ArrayList<>();

IntStream.range(0, 1000)
    .parallel()
    .forEach(shared::add);

// shared không thread-safe; kích thước/nội dung không được bảo đảm.
~~~

Ngay cả khi thay bằng một collection synchronized, thuật toán có thể vẫn bị tranh chấp lock và không còn lợi ích song song. Nếu muốn danh sách kết quả, hãy để Stream/collector quản lý:

~~~java
List<Integer> result = IntStream.range(0, 1000)
    .parallel()
    .boxed()
    .toList();

System.out.println(result.size()); // 1000
~~~

### 8.2. AtomicInteger không tự làm thuật toán stateless

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

// Ví dụ không phù hợp nếu mục tiêu là gán số thứ tự theo encounter order.
AtomicInteger counter = new AtomicInteger();

int[] labels = IntStream.range(0, 5)
    .parallel()
    .map(n -> counter.getAndIncrement())
    .toArray();
~~~

`AtomicInteger` làm thao tác tăng đếm an toàn ở mức nguyên tử, nhưng **giá trị gán cho từng phần tử phụ thuộc lịch thực thi**. Vì vậy, không thể kỳ vọng `labels` luôn là `[0, 1, 2, 3, 4]`. Đây là vấn đề về **tính xác định của nghiệp vụ**, không chỉ data race.

Nếu cần số thứ tự của phần tử, sử dụng chỉ số của nguồn:

~~~java
int[] labels = IntStream.range(0, 5).parallel()
    .map(n -> n)
    .toArray();

// [0, 1, 2, 3, 4]
~~~

Hoặc tạo cặp chỉ số–giá trị một cách tường minh từ một `List` có thứ tự, không dựa vào counter được cập nhật trong callback.

### 8.3. Không cập nhật nguồn bên trong pipeline

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> source = new ArrayList<>(List.of(1, 2, 3));

// Không làm:
// source.parallelStream().forEach(source::add);
~~~

Việc sửa cấu trúc Collection trong khi Stream đang duyệt có thể dẫn đến lỗi, dữ liệu bị thiếu/lặp hoặc hành vi không được bảo đảm. `sequential()` cũng không tự làm việc can thiệp nguồn trở nên đúng; nguyên tắc không can thiệp vẫn áp dụng.

## 9. reduce và collect: tính kết hợp quan trọng hơn chế độ

Để pipeline có thể chia và kết hợp kết quả theo những nhóm khác nhau, các hàm reduction phải đáp ứng hợp đồng của API.

### 9.1. Phép cộng nguyên đúng miền giá trị

~~~java
import java.util.List;

List<Integer> numbers = List.of(10, 20, 30, 40);

long sequentialTotal = numbers.stream()
    .mapToLong(Integer::longValue)
    .sum();

long parallelTotal = numbers.parallelStream()
    .mapToLong(Integer::longValue)
    .sum();

System.out.println(sequentialTotal); // 100
System.out.println(parallelTotal);   // 100
~~~

`sum()` diễn đạt trực tiếp mục tiêu. Với dữ liệu đủ lớn, cả `int` và `long` đều có thể tràn; phải chọn miền số hoặc phép toán có kiểm tra theo yêu cầu.

### 9.2. Phép trừ không phải reduction kết hợp được

~~~java
import java.util.List;

// Đây là công thức không phù hợp để kỳ vọng tương đương khi parallel.
int wrong = List.of(10, 3, 2).parallelStream()
    .reduce(0, (left, right) -> left - right);
~~~

Phép trừ không có tính kết hợp và `0` không là identity hai phía cho phép trừ. Các cách chia nhóm khác nhau có thể dẫn tới kết quả khác nhau. Gọi `sequential()` để làm ví dụ “trông ổn” **không sửa tính toán học sai** nếu nó dự kiến dùng như một phép reduction tổng quát.

Nếu muốn lấy một số ban đầu trừ tổng các khoản giảm, hãy **cộng các khoản giảm trước**, rồi trừ đúng một lần:

~~~java
int base = 100;
int discounts = List.of(10, 3, 2).parallelStream()
    .mapToInt(Integer::intValue)
    .sum();

int payable = base - discounts;
System.out.println(payable); // 85
~~~

### 9.3. collect không phải tự động thread-safe với mutable state ngoài

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> result = List.of(1, 2, 3, 4).parallelStream()
    .map(n -> n * n)
    .collect(Collectors.toList());
~~~

Collector có supplier/accumulator/combiner để phối hợp các container trung gian theo hợp đồng. Không tự thay bằng một biến `ArrayList` mutable ngoài pipeline. `Collectors.toList()` **không cam kết** List trả về có thể sửa được; nếu thật sự cần `ArrayList`, dùng `Collectors.toCollection(ArrayList::new)`.

## 10. Các phép toán có trạng thái có thể làm parallel kém hiệu quả

`sorted`, `distinct`, `limit`, `skip` và một số operation khác có thể cần phối hợp giữa các phần dữ liệu. Chế độ parallel không loại bỏ chi phí thuật toán đó.

| Operation | Khi parallel có thể cần thêm | Lưu ý |
| --- | --- | --- |
| `sorted()` | Thu thập/sắp xếp, phối hợp kết quả | Có chi phí bộ nhớ và so sánh |
| `distinct()` | Loại trùng, giữ tính ổn định nếu ordered | `unordered()` đôi khi nới ràng buộc |
| `limit(n)` | Xác định n phần tử đầu theo encounter order | Nguồn ordered có thể hạn chế tốc độ |
| `skip(n)` | Bỏ chính xác n phần tử đầu | Có thể đòi hỏi phối hợp |
| `takeWhile()/dropWhile()` | Tìm tiền tố trên ordered stream | Unordered thay đổi ngữ nghĩa |
| `forEachOrdered()` | Giữ thứ tự action | Có thể làm giảm hiệu quả song song |

Ví dụ:

~~~java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> topFive = IntStream.range(0, 100_000)
    .parallel()
    .map(n -> 100_000 - n)
    .sorted()
    .limit(5)
    .boxed()
    .toList();

System.out.println(topFive); // [1, 2, 3, 4, 5]
~~~

`sorted` thiết lập thứ tự, sau đó `limit(5)` lấy năm giá trị đầu theo thứ tự đó. Nếu yêu cầu là “năm giá trị nhỏ nhất”, **không** thay `sorted().limit(5)` bằng `unordered().limit(5)`.

### parallel không luôn là lựa chọn nhanh hơn

Không có quy tắc cứng “từ 10.000 phần tử trở lên thì dùng parallel”. Lợi ích phụ thuộc chi phí mỗi phần tử, khả năng chia nguồn, số lõi và tải máy, thứ tự, độ phân bố dữ liệu, chi phí hợp nhất, cấp phát và GC. Phải đo workload thực tế.

## 11. Floating-point: cùng thuật toán chưa chắc cùng bit kết quả

Với `double`, phép cộng có sai số làm tròn. Sự khác nhau về cách nhóm các phép cộng khi thực thi tuần tự hoặc song song có thể làm kết quả chênh lệch ở các chữ số cuối:

~~~java
double a = 1e16;
double b = -1e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

Đây là tính chất số học IEEE 754, không phải dấu hiệu Stream API “làm sai”. Khi cần độ chính xác thập phân, có thể xem xét `BigDecimal` và chính sách scale/rounding rõ ràng. Khi kiểm thử phép tổng số thực, nên đặt sai số cho phép theo yêu cầu ứng dụng thay vì luôn so sánh bit nếu thuật toán không bảo đảm tính đồng nhất bit.

### Các hàm gộp có trạng thái khác cũng cần chú ý

Với thống kê trung bình, không thể chỉ lấy trung bình của các trung bình nhóm nếu số phần tử mỗi nhóm khác nhau. Phải giữ **tổng và số lượng**, hoặc dùng collector/terminal chuẩn như `averagingDouble` hay `summaryStatistics`, đồng thời hiểu giới hạn sai số số thực.

## 12. Viết hàm chọn chế độ theo cấu hình

Một ứng dụng có thể muốn chạy cùng phép biến đổi ở cả hai chế độ, chẳng hạn cho phép cấu hình bật parallel sau khi đã benchmark với dữ liệu phù hợp.

~~~java
import java.util.List;
import java.util.stream.Stream;

public class ConfigurablePipeline {
    static List<Integer> normalize(List<Integer> source, boolean parallel) {
        Stream<Integer> pipeline = source.stream();

        pipeline = parallel
            ? pipeline.parallel()
            : pipeline.sequential();

        return pipeline
            .filter(n -> n >= 0)
            .map(n -> n * 2)
            .toList();
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(3, -1, 5, 2);

        System.out.println(normalize(source, false)); // [6, 10, 4]
        System.out.println(normalize(source, true));  // [6, 10, 4]
    }
}
~~~

Điểm đúng của cấu trúc này:

1. Tạo **Stream mới** từ Collection mỗi lần gọi hàm.
2. Chỉ chọn chế độ một lần, trước terminal.
3. Các lambda không sử dụng state chia sẻ, không sửa nguồn.
4. `toList()` giữ encounter order của `List` dù chạy parallel.
5. Không cố chạy lại cùng một Stream cho hai chế độ.

### Kiểm tra mode trong hàm

~~~java
static long sum(List<Integer> values, boolean runParallel) {
    Stream<Integer> stream = values.stream();
    stream = runParallel ? stream.parallel() : stream.sequential();

    // Truy vấn mode, không kích hoạt traversal.
    boolean configuredParallel = stream.isParallel();
    if (configuredParallel != runParallel) {
        throw new IllegalStateException("Cấu hình mode không khớp");
    }

    return stream.mapToLong(Integer::longValue).sum();
}
~~~

`isParallel` hữu ích khi kiểm thử **lựa chọn cấu hình**. Nó không kiểm thử phần mềm có thực sự tăng tốc, đạt độ đồng thời mong muốn hay làm việc trên nhiều thread.

## 13. Kiểm thử ngữ nghĩa của sequential và parallel

Một kiểm thử cơ bản cần so sánh kết quả chức năng ở cả hai chế độ, đặc biệt đối với pipeline có `filter`, `map`, `sorted` hoặc các collector phức tạp.

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class ParallelSemanticsCheck {
    static List<Integer> process(boolean parallel) {
        IntStream stream = IntStream.rangeClosed(1, 100);

        stream = parallel
            ? stream.parallel()
            : stream.sequential();

        return stream
            .filter(n -> n % 3 == 0)
            .map(n -> n * n)
            .boxed()
            .toList();
    }

    public static void main(String[] args) {
        List<Integer> a = process(false);
        List<Integer> b = process(true);

        if (!a.equals(b)) {
            throw new AssertionError("Hai mode khác kết quả");
        }

        if (a.size() != 33) {
            throw new AssertionError("Số phần tử không đúng");
        }

        System.out.println("PASS");
    }
}
~~~

Mẫu kiểm thử này có tác dụng vì `IntStream.rangeClosed` là nguồn có thứ tự và các phép biến đổi đang xét là stateless, không can thiệp. `toList()` duy trì encounter order.

Đối với pipeline **không cần thứ tự** và trả `Set`, hãy so sánh nội dung Set thay vì `toString()` hoặc thứ tự duyệt. Đối với phép tính `double`, chọn chiến lược so sánh phù hợp chính sách độ chính xác. Khi kiểm tra concurrency, không lấy thứ tự log hoặc tên thread làm tiêu chí đúng/sai của thuật toán.

### Tránh kiểm thử bằng side effect của peek

~~~java
import java.util.stream.IntStream;

// Không dùng bộ đếm trong peek làm bằng chứng bắt buộc
// mọi phần tử đã được mapper thực thi.
long count = IntStream.range(0, 100)
    .parallel()
    .peek(n -> System.out.println("Seen: " + n))
    .count();
~~~

Một số terminal operation như `count()` có thể tận dụng kích thước chính xác và tối ưu bỏ qua các bước trung gian không ảnh hưởng kết quả. Hành vi side effect của `peek` không phải bằng chứng tin cậy về việc duyệt bao nhiêu phần tử.

## 14. Ràng buộc về tài nguyên, I/O và quản lý vòng đời

Parallel stream thường phù hợp nhất với các phép tính **CPU-bound** có khả năng chia nguồn, chi phí mỗi phần tử đủ lớn và callback thuần túy. Với I/O chặn lâu như gọi HTTP hoặc truy vấn cơ sở dữ liệu, dùng `parallelStream()` có thể làm tăng số tác vụ chờ và ảnh hưởng các công việc khác; nếu cần quản lý số request đồng thời, timeout, retry hoặc backpressure thì nên dùng cơ chế điều phối chuyên dụng.

**Không có bảo đảm** parallel stream sử dụng một số thread cố định mà ứng dụng có thể cấu hình độc lập qua `parallel()`. Dù implementation thường tận dụng Fork/Join, không nên thiết kế correctness dựa trên tên pool, số thread hay việc task chạy luôn ở một pool nhất định.

### Stream từ tài nguyên vẫn cần đóng

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FileLineCounter {
    static long countNonBlankLines(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(path)) {
            return lines
                .parallel()
                .filter(line -> !line.isBlank())
                .count();
        }
    }
}
~~~

`try-with-resources` đảm bảo Stream được đóng sau khi terminal hoàn thành hoặc ném lỗi. `parallel()` và `sequential()` không thay thế nghĩa vụ quản lý tài nguyên; cũng không bảo đảm file sẽ được đọc/giải mã song song hiệu quả. Đối với nguồn có thứ tự hoặc dùng reader tuần tự, chi phí đọc nguồn có thể là nút thắt chính.

## 15. Những nhầm lẫn thường gặp

### Nhầm lẫn 1: parallel() ở đầu và sequential() ở giữa tạo hai giai đoạn

~~~java
var values = List.of(1, 2, 3).stream()
    .parallel()
    .map(n -> n * 2)
    .sequential()
    .toList();
~~~

Đây là **một pipeline thực thi tuần tự**; không phải `map` đã chạy song song rồi kết quả mới chuyển sang tuần tự. Muốn hai giai đoạn thật, tách thành hai terminal/pipeline và dùng dữ liệu trung gian phù hợp.

### Nhầm lẫn 2: isParallel() true nghĩa là đã có nhiều thread

`isParallel()` chỉ xác nhận chế độ được yêu cầu. Khả năng chia nguồn, kích thước dữ liệu và cách lên lịch quyết định công việc thực tế. Không dùng nó làm số đo throughput hoặc concurrency.

### Nhầm lẫn 3: parallel luôn phá thứ tự của toList

Với nguồn có encounter order như `List`, `parallelStream().toList()` vẫn giữ thứ tự. Chỉ khi nguồn/pipeline không có encounter order thì danh sách không cần giữ một thứ tự gốc đã được bảo đảm.

### Nhầm lẫn 4: sequential() sửa mọi race condition

Chuyển về tuần tự có thể làm một lỗi không còn bộc lộ, nhưng lambda sửa nguồn hoặc phụ thuộc vào state bên ngoài vẫn có thể vi phạm hợp đồng Stream và khiến code khó kiểm soát. Phải sửa nguyên nhân, không chỉ tắt song song.

### Nhầm lẫn 5: cộng Double luôn cho đúng bit như tuần tự

Phép cộng floating-point không kết hợp tuyệt đối do làm tròn. Chuyển chế độ có thể làm nhóm phép cộng khác; chọn mô hình số học/kiểm thử theo mục tiêu.

### Nhầm lẫn 6: có parallel là phải nhanh hơn

Với nguồn nhỏ, phép tính đơn giản hoặc pipeline có `sorted`, `limit`, `distinct`, chi phí chia/gộp có thể lấn át lợi ích. Chỉ quyết định sau khi đo tải thật.

### Nhầm lẫn 7: có thể chạy một Stream nhiều lần bằng cách đổi mode

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<Integer> once = List.of(1, 2, 3).stream();
long count = once.count();

// Không dùng lại: stream đã tiêu thụ.
// long other = once.parallel().count();
~~~

Stream không có cơ chế rewind mặc định. Nếu muốn so sánh hai chế độ, tạo hai Stream **mới** từ nguồn hoặc một Supplier tạo Stream hợp lệ:

~~~java
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

List<Integer> source = List.of(1, 2, 3);
Supplier<Stream<Integer>> factory = source::stream;

long sequentialCount = factory.get().count();
long parallelCount = factory.get().parallel().count();
~~~

### Nhầm lẫn 8: unordered() chính là sequential()

`unordered()` bỏ **ràng buộc encounter order**. `sequential()` chọn **chế độ thực thi tuần tự**. Hai operation giải quyết hai vấn đề hoàn toàn khác nhau và có thể kết hợp khi nghiệp vụ phù hợp.

## 16. Bảng chọn chế độ theo yêu cầu

| Bài toán | Lựa chọn ban đầu | Lý do |
| --- | --- | --- |
| Danh sách nhỏ, `map`/`filter` rẻ | `stream()` | Tránh overhead song song |
| Nguồn lớn, CPU-bound, dễ chia, stateless | Cân nhắc `parallelStream()` hoặc `parallel()` | Có khả năng hưởng lợi nhưng cần benchmark |
| Phải giữ đúng thứ tự kết quả | Có thể dùng cả hai, giữ encounter order | `toList` và reduction đúng hợp đồng vẫn có thể giữ thứ tự |
| Phải thực thi side effect theo trình tự | Ưu tiên thiết kế tuần tự hoặc bước điều phối riêng | Tránh phụ thuộc lịch thread |
| Cần chọn một phần tử bất kỳ | `findAny()`, cân nhắc parallel | Không phải giữ phần tử đầu theo thứ tự |
| Cần phần tử đầu tiên | `findFirst()` với nguồn ordered | Đúng ngữ nghĩa, có thể tốn phối hợp khi parallel |
| Có `sorted` / `distinct` / `limit` phức tạp | Bắt đầu tuần tự rồi đo | Stateful operations có thể tốn gộp/đồng bộ |
| Đang có một Stream phải đưa về tuần tự | `sequential()` trước terminal | Chọn chế độ cho pipeline |
| Cần biết mode đã chọn | `isParallel()` | Kiểm tra cấu hình, không đo thread |
| Cần kiểm soát chặt thread pool, timeout, backpressure | Cơ chế concurrency riêng phù hợp | Stream mode không cung cấp hợp đồng điều phối chi tiết |

## 17. Câu hỏi tự kiểm tra

1. **`stream().isParallel()` mặc định trả gì?** `false` đối với `Collection.stream()`.
2. **`parallelStream().isParallel()` mặc định trả gì?** `true`.
3. **`stream().parallel().sequential().isParallel()` trả gì?** `false`, vì lần chọn chế độ cuối là `sequential()`.
4. **`stream().sequential().parallel().isParallel()` trả gì?** `true`.
5. **Gọi `parallel()` có bắt đầu ngay việc xử lý phần tử không?** Không; pipeline thường lazy đến terminal operation.
6. **`isParallel() == true` có bảo đảm nhiều thread đang xử lý không?** Không; đó là trạng thái cấu hình, không phải thông số thread.
7. **Có thể chạy `map` parallel rồi `filter` sequential trong một pipeline bằng cách chèn `sequential()` ở giữa không?** Không; mode là của cả pipeline khi thực thi.
8. **`parallelStream().toList()` có giữ thứ tự của `List` không?** Có, nếu pipeline vẫn có encounter order.
9. **`forEach()` trên parallel stream có cam kết thứ tự action không?** Không; nếu cần action theo encounter order dùng `forEachOrdered()`.
10. **`parallel()` có đồng nghĩa `unordered()` không?** Không; chúng điều khiển hai khía cạnh khác nhau.
11. **Vì sao `AtomicInteger` trong callback vẫn có thể sai nghiệp vụ?** Dù không race ở thao tác tăng, việc gán số thứ tự phụ thuộc lịch thread.
12. **Tại sao giảm trừ bằng `reduce(0, (a,b) -> a-b)` không phù hợp cho parallel reduction?** Phép trừ không kết hợp và `0` không là identity hai phía.
13. **Làm sao chạy cùng thuật toán ở hai chế độ để so sánh?** Tạo hai Stream mới từ cùng nguồn ổn định, một tuần tự và một song song.
14. **Vì sao Spliterator ảnh hưởng hiệu năng parallel?** Nó quyết định cách duyệt, chia việc và cung cấp metadata cho nguồn.
15. **Với phép cộng `double`, kết quả song song và tuần tự có thể lệch nhỏ không?** Có, vì sai số làm tròn và cách nhóm phép cộng khác nhau.
16. **`sequential()` có khiến File Stream tự đóng không?** Không; tài nguyên phải được đóng bằng `try-with-resources` hoặc cơ chế quản lý tương ứng.
17. **Khi nào nên bật parallel?** Khi callback đúng hợp đồng, nguồn chia được, chi phí xử lý đủ lớn và benchmark chứng minh có lợi.

**Ghi nhớ:** `parallel()` và `sequential()` đặt **chế độ thực thi cho toàn Stream pipeline**, còn `isParallel()` chỉ **báo chế độ đã cấu hình**. Chúng không tạo ranh giới giai đoạn, không tự quyết định thứ tự kết quả và không bảo đảm số thread hay tốc độ. Hãy giữ hàm xử lý không trạng thái, không can thiệp nguồn, dùng reduction đúng hợp đồng và đo hiệu năng thực tế trước khi song song hóa.
