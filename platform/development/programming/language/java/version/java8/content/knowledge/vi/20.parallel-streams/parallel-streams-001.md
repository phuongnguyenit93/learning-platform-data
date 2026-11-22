# parallelStream(), parallel() và sequential() trong Java Stream

**Chủ đề:** Java 8 → Stream song song → parallelStream, parallel và sequential.

**Java Stream** cho phép mô tả phép biến đổi, lọc và tổng hợp dữ liệu dưới dạng một pipeline. Cùng một pipeline có thể được thực thi theo **chế độ tuần tự (sequential)** hoặc **chế độ song song (parallel)**. Ba API cốt lõi của bài là **Collection.parallelStream()**, **BaseStream.parallel()** và **BaseStream.sequential()**. Các API này xuất hiện từ Java 8 và vẫn áp dụng trong Java hiện đại.

Điểm cần nhớ ngay từ đầu: **chế độ parallel không cam kết chương trình nhanh hơn**, cũng không có nghĩa là mỗi phép toán trong pipeline chạy trong một thread riêng. Tính đúng đắn của kết quả, thứ tự phần tử, tác dụng phụ và chi phí chia/gộp công việc đều cần được xem xét.

Ví dụ độc lập sử dụng **Java 17+**. Những API phụ trợ được dùng như **List.of(...)** (Java 9+) và **Stream.toList()** (Java 16+) không được coi là tính năng xuất hiện ngay từ Java 8.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt việc **tạo** parallel stream từ Collection với việc **chuyển chế độ** của một stream đang xây dựng.
2. Giải thích giá trị của **isParallel()** và vì sao thao tác đổi chế độ sau cùng quyết định **toàn pipeline** khi terminal operation chạy.
3. Dự đoán đúng kết quả của **map**, **filter**, **sum**, **toList**, **findFirst** và **findAny** trong các ví dụ có thứ tự.
4. Phân biệt **encounter order** của nguồn với **thứ tự thread thực thi** và với thứ tự quan sát của **forEach**.
5. Viết lambda không can thiệp vào nguồn, không dựa vào shared mutable state; dùng **reduce/collect** đúng khi cần tổng hợp.
6. Quyết định khi nào thử song song, khi nào giữ tuần tự, và kiểm chứng bằng benchmark trên dữ liệu thực tế.

## 2. Sequential và parallel là chế độ của pipeline

**Sequential stream** xử lý một pipeline theo chế độ tuần tự. **Parallel stream** cho phép implementation chia dữ liệu thành phần, thực hiện các phần có thể chồng thời gian trên các thread và kết hợp kết quả theo hợp đồng của từng thao tác.

~~~text
Nguồn có thể chia phần
      │
      ├── sequential: pipeline được xử lý theo chế độ tuần tự
      │
      └── parallel:   nguồn → các phần dữ liệu
                           → xử lý song song khi có thể
                           → tổng hợp / duy trì hợp đồng kết quả
~~~

Đây là **sơ đồ ý niệm**, không phải khẳng định rằng luôn có đúng số thread bằng số phần dữ liệu. Parallel stream vẫn có thể chạy một phần công việc trên thread gọi và có thể không đạt thực thi song song hiệu quả vì nguồn không dễ chia, dữ liệu quá ít hoặc hạn chế tài nguyên.

**Stream pipeline lazy:** các thao tác trung gian như **filter**, **map**, **parallel** và **sequential** không tự duyệt hết dữ liệu. Công việc thường bắt đầu khi gọi terminal operation như **sum()**, **collect(...)**, **toList()**, **count()** hoặc **forEach(...)**.

**Đặc biệt:** **parallel() và sequential() thay đổi chế độ của pipeline**, chứ không phải ranh giới "những thao tác trước chạy kiểu A, những thao tác sau chạy kiểu B". Theo hợp đồng của **java.util.stream**, **lần thiết lập chế độ sau cùng** áp dụng cho **toàn pipeline** khi terminal operation được thực thi.

## 3. Ba API cần phân biệt

| API | Được gọi trên | Ý nghĩa | Giá trị trả về |
|---|---|---|---|
| **collection.parallelStream()** | **Collection<E>** | Tạo stream từ Collection với khả năng xử lý song song | **Stream<E>** |
| **stream.parallel()** | **BaseStream** / các stream cụ thể | Trả một stream tương đương ở chế độ **parallel** | Stream tương ứng |
| **stream.sequential()** | **BaseStream** / các stream cụ thể | Trả một stream tương đương ở chế độ **sequential** | Stream tương ứng |
| **stream.isParallel()** | **BaseStream** / các stream cụ thể | Kiểm tra pipeline **sẽ** ở chế độ song song nếu thực thi ngay tại đây | **boolean** |

### 3.1. parallelStream() là phương thức của Collection

~~~java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);

int total = numbers.parallelStream()
        .mapToInt(Integer::intValue)
        .sum();
~~~

Đây là **đoạn minh họa**; cần import **java.util.List**. Một nguồn List có thể được chia cho xử lý song song. Nếu không cần khả năng song song, dùng **numbers.stream()**.

**Điểm chính xác theo API:** **Collection.parallelStream()** được đặc tả trả về một **possibly parallel Stream**; một Collection implementation **được phép trả stream tuần tự**. Implementation mặc định tạo parallel stream từ Spliterator. Vì vậy, không nên dựa vào giả định mọi implementation của Collection luôn trả **isParallel()==true**. Với một stream đang có, gọi **parallel()** để yêu cầu chế độ parallel.

**parallelStream()** không phải một phương thức của mọi Stream. Khi đã có **Stream<T>**, chọn **parallel()** hoặc **sequential()** trên stream đó.

### 3.2. parallel() chuyển một Stream sang chế độ song song

~~~java
long total = java.util.stream.IntStream.rangeClosed(1, 100_000)
        .parallel()
        .asLongStream()
        .sum();
~~~

**IntStream.rangeClosed(...)** tạo **IntStream** tuần tự, **parallel()** bật chế độ song song và **asLongStream()** mở rộng kiểu để tổng không tràn **int** trong ví dụ. Tổng toán học từ 1 đến 100.000 bằng **5.000.050.000**, lớn hơn **Integer.MAX_VALUE**; chuyển sang **long trước khi sum()** rất quan trọng.

**parallel()** được định nghĩa trong **BaseStream**, nên dùng được với **Stream<T>**, **IntStream**, **LongStream** và **DoubleStream**. Nó có thể trả về chính đối tượng stream hiện tại hoặc một stream tương đương; không giả định lời gọi luôn tạo đối tượng độc lập.

### 3.3. sequential() chuyển pipeline về tuần tự

~~~java
List<String> names = List.of("An", "Binh", "Chi");

List<String> normalized = names.parallelStream()
        .sequential()
        .map(String::toUpperCase)
        .toList();
~~~

Kết quả **[AN, BINH, CHI]** vì pipeline cuối cùng ở chế độ tuần tự, và List có encounter order. Nhưng kết quả cùng thứ tự cũng có thể có khi **map(...).toList()** được chạy song song trên List. Do đó **thứ tự List kết quả không phải phép đo chứng minh có bao nhiêu thread đã chạy**.

**sequential()** hữu ích khi muốn ép một pipeline về chế độ tuần tự, chẳng hạn để tránh chi phí chia/gộp không đáng có. Đừng gọi nó với kỳ vọng "chỉ từ vị trí này về sau chạy tuần tự"; chế độ áp dụng cho pipeline như một đơn vị.

### 3.4. isParallel() kiểm tra cờ chế độ, không đo thời gian chạy

~~~java
boolean parallel = numbers.stream()
        .parallel()
        .isParallel(); // true
~~~

**isParallel()** mô tả chế độ nếu terminal operation được thực thi, không đo số thread thực tế, mức sử dụng CPU hay tốc độ. **Không kiểm tra isParallel() trên một stream đã bị tiêu thụ bằng terminal operation**: hợp đồng API không đảm bảo kết quả có ý nghĩa trong trường hợp này.

## 4. Ví dụ độc lập: tạo stream, bật/tắt và kiểm tra chế độ

Lưu tệp **StreamModeDemo.java**:

~~~java
import java.util.List;

public class StreamModeDemo {
    public static void main(String[] args) {
        List<Integer> values = List.of(1, 2, 3, 4, 5);

        boolean initial = values.stream().isParallel();
        boolean enabled = values.stream().parallel().isParallel();
        boolean disabled =
                values.parallelStream().sequential().isParallel();

        boolean lastSequential = values.stream()
                .parallel()
                .filter(x -> x > 0)
                .sequential()
                .isParallel();

        boolean lastParallel = values.stream()
                .sequential()
                .filter(x -> x > 0)
                .parallel()
                .isParallel();

        System.out.println("initial=" + initial);
        System.out.println("enabled=" + enabled);
        System.out.println("disabled=" + disabled);
        System.out.println("lastSequential=" + lastSequential);
        System.out.println("lastParallel=" + lastParallel);
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 StreamModeDemo.java
java StreamModeDemo
~~~

**Stdout:**

~~~text
initial=false
enabled=true
disabled=false
lastSequential=false
lastParallel=true
~~~

**Diễn giải:**

- **Collection.stream()** tạo sequential stream.
- **parallel()** chuyển sang chế độ parallel.
- **parallelStream().sequential()** trả về pipeline ở chế độ sequential, kể cả nếu stream nguồn ban đầu được tạo với khả năng parallel.
- Trong hai pipeline có nhiều lần đổi chế độ, **lần gọi sau cùng** quyết định kết quả kiểm tra. **filter** không tách pipeline thành hai chế độ.
- Mỗi dòng tạo **stream mới** từ **values**. Một stream đã dùng terminal operation không thể được sử dụng lại cho một terminal operation khác.

**Đừng dùng isParallel()==true làm bằng chứng pipeline đã chạy nhanh hoặc chắc chắn được chia thành nhiều thread.** Nó chỉ cho biết chế độ mà Stream API đã ghi nhận.

## 5. Ví dụ độc lập: cùng kết quả dữ liệu ở hai chế độ

Lưu tệp **ParallelPipelineDemo.java**:

~~~java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ParallelPipelineDemo {
    public static void main(String[] args) {
        List<Integer> numbers = IntStream.rangeClosed(1, 10)
                .boxed()
                .toList();

        List<Integer> sequentialSquares = numbers.stream()
                .filter(x -> x % 2 == 0)
                .map(x -> x * x)
                .toList();

        List<Integer> parallelSquares = numbers.parallelStream()
                .filter(x -> x % 2 == 0)
                .map(x -> x * x)
                .toList();

        long total = IntStream.rangeClosed(1, 100_000)
                .parallel()
                .asLongStream()
                .sum();

        System.out.println("sequential=" + sequentialSquares);
        System.out.println("parallel=" + parallelSquares);
        System.out.println("equal=" + sequentialSquares.equals(parallelSquares));
        System.out.println("total=" + total);

        Stream.of("A", "B", "C")
                .parallel()
                .forEachOrdered(System.out::print);
        System.out.println();
    }
}
~~~

~~~bash
javac -encoding UTF-8 ParallelPipelineDemo.java
java ParallelPipelineDemo
~~~

**Stdout:**

~~~text
sequential=[4, 16, 36, 64, 100]
parallel=[4, 16, 36, 64, 100]
equal=true
total=5000050000
ABC
~~~

**Vì sao kết quả xác định?** Với nguồn **List** có encounter order, **filter/map** là thao tác không thay đổi thứ tự logic phần tử và **Stream.toList()** giữ encounter order của stream có thứ tự. Phần cuối dùng **forEachOrdered(...)**, được yêu cầu quan sát các phần tử theo encounter order, nên in **ABC** dù pipeline ở chế độ parallel.

Không phải mọi thao tác terminal đều giữ thứ tự **thực thi tác dụng phụ**. Nếu đổi **forEachOrdered(...)** thành **forEach(...)** trong pipeline song song, thứ tự in có thể khác và phụ thuộc lập lịch thread. **Không viết stdout cố định** cho một ví dụ dùng **forEach** song song khi thứ tự là nondeterministic.

Ví dụ còn minh họa phép tổng phù hợp với kiểu số: nếu thay **asLongStream().sum()** bằng **IntStream.sum()** cho dãy 1 đến 100.000, tổng **int** sẽ bị tràn. Parallel không tự kiểm tra hoặc sửa overflow.

## 6. Encounter order không đồng nghĩa với thứ tự thực thi

**Encounter order** là thứ tự mà nguồn/pipeline quy định. Ví dụ:

- **List** và **mảng** có thứ tự phần tử rõ ràng.
- **HashSet** không cam kết một encounter order dùng để xác định "phần tử đầu tiên" theo nghiệp vụ.
- **sorted(...)** tạo thứ tự theo comparator; nếu cần lựa chọn ổn định khi nhiều giá trị cùng khóa, phải xác định quy tắc tie-break phù hợp.

Một parallel stream có thể xử lý các phần dữ liệu ở các thread, thời điểm và thứ tự khác nhau nhưng **kết quả logic của một thao tác ordered** vẫn phải tuân thủ hợp đồng tương ứng.

| Tình huống | Có cam kết thứ tự phần tử/tác dụng phụ? |
|---|---|
| **list.parallelStream().map(...).toList()** | Danh sách kết quả theo encounter order của List |
| **list.parallelStream().forEach(action)** | **Không** bảo đảm thứ tự gọi action |
| **list.parallelStream().forEachOrdered(action)** | Action chạy theo encounter order nếu stream có thứ tự |
| **list.parallelStream().findFirst()** | Trả phần tử đầu tiên theo encounter order, nếu có |
| **list.parallelStream().findAny()** | Trả một phần tử phù hợp bất kỳ; không cam kết phần tử đầu |
| **unordered().parallel()** | Không còn yêu cầu bảo toàn encounter order ở các thao tác được phép |

**forEachOrdered** bảo đảm trình tự quan sát các action, **không có nghĩa map/filter trước đó sẽ được gọi tuần tự ở một thread duy nhất**. Nếu muốn xử lý có thứ tự để tạo danh sách, thường nên biểu đạt kết quả bằng **toList()** hoặc **collect(...)**, thay vì thu thập thủ công qua side effect của **forEach**.

### 6.1. findFirst và findAny ở parallel stream

Lưu tệp **ParallelFindDemo.java**:

~~~java
import java.util.List;

public class ParallelFindDemo {
    public static void main(String[] args) {
        List<Integer> values = List.of(5, 6, 7, 8, 9, 10);

        int first = values.parallelStream()
                .filter(x -> x > 5)
                .findFirst()
                .orElse(-1);

        int any = values.parallelStream()
                .filter(x -> x > 5)
                .findAny()
                .orElse(-1);

        System.out.println("first=" + first);
        System.out.println("anyIsValid=" + List.of(6, 7, 8, 9, 10)
                .contains(any));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ParallelFindDemo.java
java ParallelFindDemo
~~~

**Stdout:**

~~~text
first=6
anyIsValid=true
~~~

**Giải thích:** **findFirst()** phải chọn 6 vì đó là phần tử đầu tiên theo encounter order của List thỏa điều kiện. **findAny()** có thể chọn một trong 6, 7, 8, 9, 10; ví dụ chỉ in tính hợp lệ của phần tử thay vì khẳng định một giá trị cụ thể. Nếu stream rỗng sau filter, cả hai trả **Optional.empty()**.

Nếu chỉ cần câu trả lời boolean "có phần tử phù hợp hay không?", **anyMatch(...)** thường diễn đạt mục tiêu trực tiếp hơn **findAny().isPresent()**.

### 6.2. unordered() là quyết định độc lập với parallel()

**BaseStream.unordered()** bỏ ràng buộc encounter order để một số thao tác có thể được tối ưu hơn. Nó **không tự trộn ngẫu nhiên dữ liệu**, **không biến stream thành parallel** và không phải cách khôi phục tuần tự. Bốn yếu tố nên phân biệt:

- **parallel()**: chế độ thực thi.
- **sequential()**: chế độ thực thi tuần tự.
- **unordered()**: bỏ yêu cầu thứ tự, nếu nguồn/pipeline có thứ tự.
- **forEachOrdered()**: terminal operation giữ encounter order của action nếu thứ tự tồn tại.

Ví dụ, khi bài toán **chỉ cần bất kỳ 100 phần tử** từ một nguồn lớn, không quan tâm 100 phần tử đầu theo thứ tự, việc bỏ ràng buộc thứ tự có thể làm **limit(100)** dễ tối ưu hơn. Nhưng nếu yêu cầu là **100 bản ghi đầu tiên sau sắp xếp**, không được bỏ thứ tự.

Các thao tác **limit**, **skip** và một số thao tác stateful khác có thể tốn kém hơn với nguồn ordered và parallel vì phải giữ ràng buộc thứ tự. Chỉ dùng **unordered()** nếu nghiệp vụ cho phép thay đổi ý nghĩa lựa chọn phần tử.

## 7. Tính đúng đắn: stateless, non-interfering và tránh shared mutable state

Parallel stream đem lại khả năng thực thi đồng thời, nên các lambda trong **map/filter/flatMap** cần tuân thủ hợp đồng:

- **Stateless**: kết quả cho một phần tử không phụ thuộc vào trạng thái mutable bị các phần tử khác cập nhật đồng thời.
- **Non-interfering**: không sửa cấu trúc nguồn dữ liệu đang được duyệt, trừ những trường hợp nguồn được thiết kế rõ ràng cho truy cập đồng thời.
- **Không giả định thứ tự gọi** của các lambda, không dựa vào thread hiện tại và không yêu cầu mỗi phần tử được xử lý vào thời điểm cố định.

### 7.1. Ví dụ sai: thêm vào ArrayList dùng chung trong forEach

~~~java
// Đoạn minh họa SAI, không dùng trong chương trình thật:
List<Integer> result = new ArrayList<>();

IntStream.range(0, 1_000)
        .parallel()
        .forEach(result::add);
~~~

Đoạn này cần import **java.util.List**, **java.util.ArrayList**, **java.util.stream.IntStream** nếu thử riêng. **ArrayList** không thread-safe: các action có thể cập nhật cùng một ArrayList đồng thời, gây mất phần tử, dữ liệu sai hoặc lỗi trong quá trình chạy. Có lúc chạy ra đủ 1.000 phần tử cũng không làm code trở nên an toàn.

**Cách đúng nếu cần danh sách kết quả:**

~~~java
List<Integer> result = IntStream.range(0, 1_000)
        .parallel()
        .boxed()
        .toList();
~~~

Đây là đoạn minh họa Java 17+; **toList()** tạo List kết quả không cho phép sửa. Vì nguồn **IntStream.range(...)** có encounter order, kết quả List theo thứ tự 0 đến 999. Stream framework tự thực hiện tổng hợp, không cần người dùng cho các thread sửa cùng một List.

Nếu thật sự cần danh sách mutable sau khi collect:

~~~java
List<Integer> mutable = IntStream.range(0, 1_000)
        .parallel()
        .boxed()
        .collect(java.util.stream.Collectors.toCollection(
                java.util.ArrayList::new));
~~~

Collector được thiết kế theo hợp đồng supplier/accumulator/combiner nên triển khai có thể thu thập vào trạng thái riêng ở từng nhánh rồi gộp an toàn. **Không cần thêm synchronized vào một ArrayList global để giả lập collector**.

### 7.2. Không dùng bộ đếm mutable ngoài pipeline

~~~java
// SAI: có data race khi chạy song song.
int[] count = {0};
items.parallelStream().forEach(item -> count[0]++);
~~~

Đây là đoạn minh họa, giả sử **items** là một Collection. **count[0]++** không atomic, có thể mất cập nhật. Ngay cả khi thay bằng **AtomicInteger** để tránh race, việc đếm từng phần tử bằng shared atomic state có thể gây contention và đi ngược ý định aggregate operation.

**Đúng:** dùng **items.parallelStream().count()**, hoặc các reduction/collector phù hợp nếu muốn thống kê phức tạp.

### 7.3. Không dùng side effect để kiểm thử thứ tự

~~~java
// Đoạn minh họa có thứ tự in KHÔNG được đặc tả:
IntStream.rangeClosed(1, 5)
        .parallel()
        .forEach(System.out::println);
~~~

Bạn có thể thấy 3, 4, 5, 1, 2 hoặc thứ tự khác, tùy JVM và tình trạng lập lịch. Nếu cần stdout thứ tự **1,2,3,4,5**, dùng **forEachOrdered(System.out::println)**. Nếu chỉ cần dữ liệu kết quả, sử dụng **toList()** là lựa chọn rõ ràng hơn.

**peek(...)** cũng không phải cơ chế audit đảm bảo gọi đúng một lần theo thứ tự; Stream có thể tối ưu bỏ qua việc sinh một số phần tử khi terminal operation không cần chúng. Dùng **peek** chủ yếu để quan sát/debug, không cất logic nghiệp vụ quan trọng vào đó.

## 8. Reduction đúng với xử lý song song

Khi dùng **reduce(identity, accumulator)**, accumulator cần phù hợp điều kiện **associative** và **stateless**; identity cần đúng với phép kết hợp. Khi tính tổng nguyên không tràn, phép cộng thường là lựa chọn tự nhiên:

~~~java
long total = LongStream.rangeClosed(1, 1_000)
        .parallel()
        .reduce(0L, Long::sum);
// total == 500500L
~~~

Đây là đoạn minh họa; cần import **java.util.stream.LongStream**. Hệ thống có thể tính từng tổng con và gộp chúng mà vẫn thu kết quả toán học tương đương khi phạm vi **long** đủ.

**Không sử dụng phép trừ như một reducer tổng quát khi mong kết quả giống cách tính trái sang phải:**

~~~java
// SAI về giả định tính kết hợp:
int value = IntStream.of(10, 3, 2)
        .parallel()
        .reduce(0, (a, b) -> a - b);
~~~

Phép trừ không associative: cách nhóm **(10 - 3) - 2** khác **10 - (3 - 2)**. Do đó đây không phải phép reduce phù hợp để kết quả không phụ thuộc cách chia/ghép. Câu hỏi ở đây là **phép kết hợp đúng**, không chỉ là bật hay tắt parallel.

### 8.1. double và sai số thứ tự cộng

Phép cộng **double** làm tròn theo IEEE 754; vì vậy tính kết hợp của số thực toán học không được bảo toàn hoàn toàn trong phép toán máy:

~~~java
double a = (1e16 + 1.0) + (-1e16); // có thể thành 0.0
double b = 1e16 + (1.0 + (-1e16)); // thường cũng thành 0.0

// Ví dụ rõ hơn về thứ tự:
double first = (1e16 + 1.0) - 1e16; // 0.0
double second = (1e16 - 1e16) + 1.0; // 1.0
~~~

Các biểu thức trên minh họa **sai số làm tròn**, không phải chương trình độc lập. Một parallel reduction tính tổng **double** có thể nhóm phép cộng khác với vòng lặp tuần tự và cho kết quả khác vài bit. Nếu cần tính tổng double thông thường, **DoubleStream.sum()** có thể dùng kỹ thuật cộng bù để cải thiện độ chính xác so với cách cộng ngây thơ, nhưng **không bảo đảm chính xác tuyệt đối hoặc cùng thứ tự cộng giữa mọi lần chạy**.

Nếu nghiệp vụ yêu cầu **thập phân chính xác** (đặc biệt tiền), nên chọn **BigDecimal** hoặc số nguyên theo đơn vị nhỏ nhất đã quy định; không dùng parallel như cách sửa sai số số thực.

### 8.2. Collector và combiner

**collect(...)** dùng collector hợp lệ có thể gom các phần tử song song mà không cần một container dùng chung không được bảo vệ. Ví dụ:

~~~java
Map<Integer, Long> counts = names.parallelStream()
        .collect(Collectors.groupingBy(
                String::length,
                TreeMap::new,
                Collectors.counting()));
~~~

Đây là đoạn minh họa; cần import **Map**, **TreeMap**, **Collectors** và một **List<String> names** đã khai báo. **groupingBy** sử dụng Collector để chia/gộp các kết quả; nó không đòi mọi thread trực tiếp cập nhật cùng một **TreeMap**.

**Collector tùy biến** phải có supplier tạo container mới, accumulator thêm phần tử, combiner gộp đúng trạng thái và finisher hợp lệ. **Đừng khai báo Collector.Characteristics.CONCURRENT** cho một ArrayList, HashMap hoặc StringBuilder mutable thông thường nếu không có cơ chế đảm bảo cập nhật đồng thời vào cùng một container.

## 9. Ví dụ hoàn chỉnh: đếm theo nhóm ở parallel stream

Lưu thành **ParallelGroupingDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class ParallelGroupingDemo {
    public static void main(String[] args) {
        List<String> names = List.of(
                "Java", "Kotlin", "Go", "Rust", "JavaScript"
        );

        Map<Integer, Long> counts = names.parallelStream()
                .collect(Collectors.groupingBy(
                        String::length,
                        TreeMap::new,
                        Collectors.counting()
                ));

        System.out.println("grouped=" + counts);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ParallelGroupingDemo.java
java ParallelGroupingDemo
~~~

**Stdout:**

~~~text
grouped={2=1, 4=2, 6=1, 10=1}
~~~

**Vì sao ổn định?** **TreeMap** sắp khóa tăng dần; **String.length()** có kết quả xác định đối với đầu vào này; mỗi tên được đếm đúng một lần. Việc sử dụng **parallelStream()** không buộc kết quả tổng hợp phải có thứ tự gộp thay đổi ở đầu ra.

Lưu ý: **groupingBy(...)** không phải collector concurrent mặc định; trên dữ liệu lớn nó có thể tốn chi phí gộp các map. Với một số bài toán, **groupingByConcurrent(...)** có thể phù hợp khi thứ tự không quan trọng, nhưng cần kiểm tra đặc tính kết quả và nhu cầu ứng dụng trước khi thay. Không thay chỉ vì thấy chữ "parallel".

## 10. Parallel stream sử dụng thread thế nào?

Trong các implementation JDK phổ biến, parallel stream thường dùng cơ chế **Fork/Join** và **ForkJoinPool.commonPool()** để thực hiện phần lớn công việc. Đây là chi tiết triển khai quan trọng khi phân tích hiệu năng, nhưng **API Stream không cam kết mọi lời gọi luôn sử dụng một tập thread cố định, đúng số CPU hay đúng một pool được chỉ định**.

Đừng coi **parallelStream()** là một API lập lịch background task, nơi có thể:
- kiểm soát chính xác thread nào thực thi từng phần tử;
- gán timeout/cancellation độc lập cho từng phần tử;
- buộc mỗi task đi vào một executor do ứng dụng quản lý;
- bảo đảm truy cập I/O được giới hạn đồng thời theo quota hoặc rate limit.

Nếu bài toán cần các cơ chế điều phối như **ExecutorService**, **CompletableFuture**, giới hạn truy cập dịch vụ ngoài, timeout hoặc chính sách retry, cần thiết kế lớp concurrency rõ ràng thay vì dựa vào parallel stream để tự giải quyết.

**Không nên mặc định dùng parallel stream cho những tác vụ blocking I/O** như truy vấn cơ sở dữ liệu từ xa, gọi HTTP mỗi phần tử, ghi file hoặc lock lâu. Các thao tác đó có thể chiếm worker, ảnh hưởng các phần việc khác và làm throughput tổng thể kém hơn.

## 11. Khi nào parallel có khả năng có lợi?

Parallel stream thường đáng thử khi hội đủ các điều kiện sau:

| Yếu tố | Tác động |
|---|---|
| **Nguồn đủ lớn** | Chi phí khởi tạo/chia/gộp công việc có thể được bù bằng lượng tính toán |
| **Tác vụ CPU-bound đủ nặng trên mỗi phần tử** | Có công việc độc lập có thể phân phối cho nhiều core |
| **Nguồn dễ chia** | Mảng, ArrayList, IntStream.range thường thuận lợi cho Spliterator |
| **Không có shared mutable state** | Tránh contention, race condition và kết quả bất định |
| **Phép gộp phù hợp** | Reduction/collector associative và combiner đúng |
| **Không bị ràng buộc thứ tự quá nặng** | Tránh chi phí của một số thao tác stateful ordered |
| **Còn tài nguyên CPU** | Tránh cạnh tranh quá mức với các tác vụ khác trong ứng dụng |

**Các tình huống nên ưu tiên sequential trước:**
- Tập dữ liệu nhỏ và phép xử lý rất rẻ như cộng vài chục số.
- Tác vụ phụ thuộc thứ tự/phần tử trước, có shared state hoặc cần thực hiện side effect nối tiếp.
- Nguồn khó chia hoặc pipeline có nhiều thao tác **sorted**, **limit**, **skip**, **distinct** phải giữ ràng buộc thứ tự.
- Có các lời gọi blocking/I/O, semaphore, transaction context hoặc trạng thái gắn với thread.
- Ứng dụng server đang có nhiều request đồng thời; thêm parallel ở mỗi request có thể khiến cả hệ thống tranh CPU.

Một thao tác **map đơn giản trên 100 phần tử** thường không đủ cơ sở để khẳng định parallel nhanh hơn. Ngược lại, một phép tính độc lập nặng trên hàng triệu phần tử có thể đáng benchmark. **Chỉ kết quả đo thực tế quyết định.**

### 11.1. Tại sao benchmark sơ sài dễ gây hiểu nhầm?

Lần đầu JVM chạy code có thể chịu tác động của **class loading, JIT compilation, cấp phát bộ nhớ và GC**. Nếu chỉ chạy một lần bằng **System.nanoTime()** rồi kết luận, kết quả dễ phụ thuộc vào nhiệt độ CPU, tải hệ thống, JIT warm-up và cách phát sinh dữ liệu.

Khi hiệu năng thực sự quan trọng:
1. Dùng tập dữ liệu đại diện cho production, bao gồm phân bố kích thước và tỷ lệ phần tử qua filter.
2. So sánh **cùng một thuật toán đúng**, chỉ thay chế độ sequential/parallel.
3. Warm up đủ, chạy nhiều lần và đo phân bố kết quả thay vì chỉ một con số.
4. Xem cả **throughput**, **latency**, CPU utilization, allocation và ảnh hưởng lên workload khác.
5. Với benchmark Java nghiêm túc, dùng công cụ phù hợp như **JMH** để hạn chế sai lệch do JVM tối ưu hóa.

Không đo bằng việc in tên thread ra console trong từng **map(...)**: bản thân logging/synchronization làm méo phép đo và không bảo đảm quan sát thứ tự.

## 12. Các câu hỏi và lỗi thường gặp

### 12.1. Gọi parallel() ở giữa rồi sequential() ở cuối thì sao?

~~~java
long sum = LongStream.rangeClosed(1, 1_000)
        .parallel()
        .filter(x -> x % 2 == 0)
        .sequential()
        .sum();
~~~

**Toàn pipeline cuối cùng ở chế độ sequential**, không có hợp đồng rằng phần **filter(...)** đã chạy parallel rồi riêng **sum()** chạy sequential. **parallel() và sequential() là chế độ của pipeline trước terminal operation.**

### 12.2. Gọi sequential() có luôn đổi kết quả không?

**Không.** Với pipeline thuần, các phép toán có hợp đồng xác định và nguồn có thứ tự, kết quả thường tương đương dù chế độ khác nhau. Tuy nhiên, những thao tác cố ý không xác định như **findAny**, side effect có thứ tự quan sát không được bảo đảm hoặc sai số làm tròn số thực có thể cho khác biệt phù hợp với hợp đồng API.

### 12.3. Gọi parallelStream() có chắc chắn nhanh hơn không?

**Không.** Đây là lời yêu cầu/khả năng thực thi song song, không phải bảo đảm về hiệu năng, số worker hay mức tăng tốc. Chỉ xác nhận bằng benchmark.

### 12.4. Có thể tái dùng Stream để thử hai chế độ không?

~~~java
// SAI nếu đã tiêu thụ pipeline:
Stream<Integer> stream = values.stream();
long a = stream.count();
long b = stream.parallel().count(); // Không được dùng lại Stream
~~~

Đây là đoạn minh họa lỗi, giả sử **values** là List và đã import Stream. Sau terminal operation, stream đã bị tiêu thụ; lần gọi terminal kế tiếp có thể ném **IllegalStateException**. Hãy tạo **values.stream()** mới cho mỗi lần thử.

### 12.5. Có thể giữ hai biến cùng một stream rồi chạy hai chế độ không?

Không nên rẽ nhánh/reuse cùng một pipeline để gọi nhiều terminal operation:

~~~java
// SAI về vòng đời Stream: hai biến có thể chia sẻ pipeline.
Stream<Integer> s = values.stream();
Stream<Integer> p = s.parallel();
Stream<Integer> q = s.sequential();
// Không dùng p và q cho hai lần terminal riêng.
~~~

**parallel()/sequential() có thể trả chính đối tượng stream hoặc thay đổi trạng thái pipeline**; hợp đồng không hứa luôn tạo pipeline mới độc lập. Tạo stream lại từ nguồn cho mỗi lần chạy.

### 12.6. Tại sao code với forEach chạy tuần tự đúng nhưng chạy song song sai?

Nếu accumulator/sink được chia sẻ và không thread-safe, các lần cập nhật có thể đồng thời. Thứ tự **forEach** song song cũng không được bảo đảm. Chuyển sang **map/filter rồi collect/toList**, hoặc dùng kiến trúc concurrency phù hợp khi cần side effect.

### 12.7. unordered() có giống sequential() không?

**Không.** **unordered()** thay đổi ràng buộc về encounter order; **sequential()** thay đổi chế độ thực thi. Một stream có thể **parallel và ordered**, **parallel và unordered**, **sequential và ordered**, hoặc **sequential và unordered**.

### 12.8. parallelStream có làm toàn bộ ứng dụng chạy song song không?

**Không.** Nó chỉ thiết lập chế độ cho pipeline đang tạo. Những phần việc khác của ứng dụng, các gọi API, database transaction hay các Stream khác không tự chuyển sang parallel.

### 12.9. Có nên nhét Thread.sleep hoặc HTTP call vào map để minh họa parallel?

Các ví dụ dùng sleep dễ khiến người học suy luận sai về tốc độ vì phụ thuộc pool, scheduling và I/O. Bài này ưu tiên ví dụ **thuần tính toán**, có kết quả xác định. Với mã sản phẩm, tránh trộn phép biến đổi dữ liệu của Stream với I/O blocking hoặc side effect khó kiểm soát.

### 12.10. Nếu parallel bị lỗi trong một nhánh thì các nhánh còn lại có ngay lập tức dừng?

Không nên xây dựng logic cần **chắc chắn không có tác dụng phụ nào khác xảy ra sau khi một nhánh thất bại**. Các phần việc khác có thể đang được triển khai. Hãy tránh side effect không idempotent trong pipeline và dùng cơ chế điều phối/cancellation chuyên dụng nếu bài toán đòi kiểm soát chặt.

## 13. Bài tập có đáp án

Cho nguồn:

~~~java
List<Integer> data = List.of(1, 2, 3, 4, 5, 6);
~~~

Giả sử đã import **java.util.List**.

**Câu 1.** Giá trị của **data.stream().parallel().sequential().isParallel()** là gì?

**Câu 2.** Giá trị của **data.stream().sequential().parallel().isParallel()** là gì?

**Câu 3.** Với **data.parallelStream().filter(x -> x % 2 == 0).toList()**, kết quả theo thứ tự nào?

**Câu 4.** Với **data.parallelStream().filter(x -> x > 2).findFirst()**, phần tử tìm được là bao nhiêu?

**Câu 5.** Có được khẳng định **data.parallelStream().filter(x -> x > 2).findAny()** luôn trả **3** không?

**Câu 6.** Vì sao dùng **ArrayList shared** trong **parallelStream().forEach(shared::add)** không an toàn? Chọn cách thay thế nào?

**Câu 7.** Nếu pipeline có **parallel().map(...).sequential().sum()**, đoạn **map** có được bảo đảm chạy song song không?

**Câu 8.** Khi tìm **100 phần tử đầu theo thứ tự**, có nên gọi **unordered()** chỉ để làm nhanh **parallel().limit(100)** không?

**Đáp án:**

1. **false**, vì lần đổi chế độ sau cùng là sequential.
2. **true**, vì lần đổi chế độ sau cùng là parallel.
3. **[2, 4, 6]**. Nguồn List có encounter order; kết quả toList bảo toàn thứ tự logic dù công việc có thể được thực hiện song song.
4. **3**, vì **findFirst** giữ quy tắc phần tử đầu theo encounter order.
5. **Không**; **findAny** có quyền trả **3, 4, 5 hoặc 6**.
6. **ArrayList** không thread-safe khi nhiều action ghi đồng thời. Dùng **filter(...).toList()** hoặc **collect(...)** với Collector phù hợp.
7. **Không**. Pipeline có chế độ cuối cùng là sequential; **parallel() ở trước không tạo một vùng thực thi riêng cho map**.
8. **Không**, vì bỏ thứ tự làm thay đổi yêu cầu "đầu theo thứ tự". Chỉ bỏ ràng buộc khi nghiệp vụ chấp nhận bất kỳ 100 phần tử nào.

## 14. Ghi nhớ và tài liệu chính thức

- **Collection.stream()** tạo sequential stream; **Collection.parallelStream()** trả stream **có thể** song song theo hợp đồng Collection.
- **BaseStream.parallel()** đặt chế độ parallel; **BaseStream.sequential()** đặt chế độ sequential; **isParallel()** kiểm tra chế độ mà một terminal operation sẽ dùng.
- **Lệnh đổi chế độ sau cùng chi phối toàn pipeline**. Cả hai là intermediate operation, không phải điểm chạy một phần pipeline ngay lập tức.
- **Parallel không phá vỡ mọi bảo đảm thứ tự**: phải đọc hợp đồng của từng thao tác. **toList/findFirst/forEachOrdered** có bảo đảm về encounter order khi nguồn có thứ tự; **forEach/findAny** không có bảo đảm tương ứng.
- **Tránh shared mutable state**; ưu tiên lambda stateless, không can thiệp vào nguồn, cùng các reducer/collector hợp lệ.
- **Chọn parallel dựa trên benchmark thực tế**, vì hiệu năng phụ thuộc kích thước nguồn, chi phí thao tác, khả năng chia dữ liệu, yêu cầu thứ tự và tải CPU.

Các API được trình bày đều đang có trong Java hiện hành:

- [BaseStream — parallel(), sequential(), isParallel(), unordered() (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/BaseStream.html)
- [Collection — stream() và parallelStream() (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collection.html)
- [Stream — forEach/forEachOrdered/findFirst/findAny/toList (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [java.util.stream — Parallelism, Ordering và Side-effects (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html)
- [IntStream và LongStream (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html)
