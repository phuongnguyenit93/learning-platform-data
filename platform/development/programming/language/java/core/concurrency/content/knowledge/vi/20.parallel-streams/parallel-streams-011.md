# Tránh nested parallel streams thiếu kiểm soát

**Nested parallel streams** là tình huống một pipeline stream chạy song song lại tạo và thực thi một hoặc nhiều pipeline song song khác trong tác vụ của nó. Ví dụ, vòng ngoài xử lý danh sách các nhóm bằng `parallelStream()`, rồi mỗi nhóm lại gọi `parallelStream()` ở vòng trong. Java cho phép viết như vậy, nhưng **không có nghĩa càng nhiều tầng `parallel()` thì càng nhanh**. Khi không tính toán ngân sách CPU, kích thước tác vụ và tài nguyên dùng chung, ứng dụng có thể tốn nhiều chi phí chia việc, điều phối, chờ hoàn tất, tranh chấp và bộ nhớ mà thông lượng không cải thiện.

Mục tiêu của bài học là nhận diện song song lồng nhau, hiểu vì sao nó có thể giảm hiệu năng, lựa chọn đúng mức song song và đo kiểm bằng Java thuần. Nội dung áp dụng cho Java 17+; các ví dụ đầy đủ bên dưới có thể chạy bằng **JDK 21**.

## 1. Nhận diện nested parallel streams

Ví dụ thường gặp:

```java
long total = groups.parallelStream()
        .mapToLong(group -> group.parallelStream()
                .mapToLong(value -> expensiveCpuWork(value))
                .sum())
        .sum();
```

Đây là **đoạn minh họa**, `groups` và `expensiveCpuWork` chưa được khai báo. Ta thấy hai cấp:

1. **Cấp ngoài:** `groups.parallelStream()` yêu cầu xử lý các nhóm song song.
2. **Cấp trong:** với mỗi nhóm đang được xử lý, `group.parallelStream()` lại yêu cầu xử lý các phần tử trong nhóm song song.
3. **Điểm chờ:** phép `sum()` của nhóm trong phải trả kết quả để lambda của phần tử ngoài hoàn tất. Phép `sum()` ngoài tiếp tục kết hợp các kết quả nhóm.

Hình dung 8 nhóm, mỗi nhóm 1.000 phần tử:

```text
groups (8 phần)
   |
   +-- nhóm A (outer task) -- inner parallel stream -- sum() --+
   +-- nhóm B (outer task) -- inner parallel stream -- sum() --+
   +-- nhóm C (outer task) -- inner parallel stream -- sum() --+--> tổng
   +-- ...                                                     |
   +-- nhóm H (outer task) -- inner parallel stream -- sum() --+
```

Một biểu thức dễ đọc có thể tạo **nhiều pipeline có chi phí lập lịch riêng**, trong khi số lõi CPU thực tế vẫn giữ nguyên. Để hiểu đúng, đừng suy ra “8 nhóm nhân 1.000 phần tử sẽ tạo 8.000 threads”: parallel stream không có cam kết tạo một thread cho mỗi phần tử.

### Tại sao vòng trong dùng `parallel()` lại có ý nghĩa?

`parallel()` đánh dấu pipeline có thể được xử lý song song, nhưng mức song song thực tế còn phụ thuộc vào `Spliterator` của nguồn, khối lượng công việc, cách chia mảnh, terminal operation và scheduler. Nếu phần tử ít hoặc việc quá nhẹ, việc chia thêm có thể đắt hơn phần tính toán.

`group.stream()` tạo pipeline **tuần tự**. Vì vậy:

```java
groups.parallelStream()
      .map(group -> group.stream().map(this::transform).toList())
      .toList();
```

Ở đây **chỉ pipeline ngoài** yêu cầu song song; bên trong mỗi nhóm xử lý tuần tự. Đoạn mã trên minh họa phương án kiến trúc, không phải chương trình biên dịch độc lập vì `groups` và `transform` chưa được khai báo.

## 2. Parallel stream dùng tài nguyên thực như thế nào?

Trong triển khai OpenJDK/JDK phổ biến, parallel stream thường tận dụng **Fork/Join framework**, điển hình là `ForkJoinPool.commonPool()`. Worker của pool sử dụng cơ chế *work stealing*: khi một worker hết việc riêng, nó có thể lấy việc sẵn sàng từ worker khác. Tại một thời điểm, mức song song hữu ích của công việc CPU-bound vẫn chịu giới hạn từ CPU cores/CPU quota đang có.

**Ba nhận định cần chính xác:**

- **Không có “một pool riêng cho mỗi `parallelStream()`”.** Khi đang chạy trên worker ForkJoinPool, các tầng stream lồng có thể chia sẻ cùng tài nguyên điều phối; lớp trong không tự tạo số lõi mới hay mặc định mở thêm vô hạn OS threads.
- **Không thể lấy công thức outer parallelism × inner parallelism để đo số threads.** Đó không phải hợp đồng API. Số tasks được chia, số worker thực chạy và lượng công việc còn đợi là các khái niệm khác nhau.
- **Không thể khẳng định mọi nested parallel stream sẽ deadlock.** Fork/Join được thiết kế để thực hiện các tác vụ đệ quy, có cơ chế phối hợp/join công việc. Vấn đề cần cảnh giác là overhead, chờ, tranh chấp, mất cân bằng tải và blocking không được quản lý; deadlock chỉ xuất hiện khi còn có điều kiện phụ thuộc/khóa gây kẹt thực sự.

Java Stream API cho phép quyết định stream là sequential hay parallel, **không đưa ra một hợp đồng công khai để gắn một pipeline stream cụ thể với một ForkJoinPool tùy chọn**. Cách đưa parallel stream vào một custom `ForkJoinPool` thông qua `pool.submit(() -> stream.parallel()...)` có thể vận hành theo cách bạn mong đợi trên bản JDK đang dùng, nhưng không nên mặc định đó là cơ chế kiểm soát pool ổn định cho mọi triển khai. Nếu cần quyền kiểm soát tài nguyên và vòng đời độc lập, sử dụng `ExecutorService` hoặc thiết kế `ForkJoinTask` trực tiếp.

**Blocking I/O còn nguy hiểm hơn CPU-bound:** nếu lambda trong parallel stream chờ socket/lock hoặc tác vụ khác, các workers dành cho CPU-bound work có thể bị chiếm và gây chậm các tác vụ khác dùng chung pool. ForkJoinPool có cơ chế `ManagedBlocker` cho một số tình huống blocking có thông báo, nhưng những lời gọi blocking tùy ý không tự bảo đảm được bù worker. Đối với I/O, cần chọn mô hình concurrency và giới hạn tài nguyên riêng.

## 3. Những nguyên nhân chính khiến nested parallel kém hiệu quả

| Nguyên nhân | Diễn biến | Dấu hiệu thường gặp |
|---|---|---|
| **Chi phí chia nhỏ việc** | Mỗi stream trong lại tạo cấu trúc pipeline, chia và kết hợp kết quả | Việc nhỏ nhưng CPU dành nhiều cho điều phối |
| **Nhiều điểm đồng bộ/join** | Outer task đợi terminal operation của inner pipeline | Thời gian chờ lớn hơn thời gian tính |
| **Tranh chấp cùng tài nguyên** | Nhiều nhóm dùng chung cores, cache, memory bandwidth hoặc pool | Throughput không tăng dù tăng parallelism |
| **Mất cân bằng độ lớn nhóm** | Một nhóm rất lớn, nhiều nhóm rất nhỏ | Worker nhàn rỗi trong khi nhóm nặng chạy lâu |
| **Áp lực bộ nhớ/GC** | Nhiều pipeline, object trung gian hoặc kết quả từng nhóm cùng sống | Allocation, GC hoặc heap tăng |
| **Blocking trong worker** | I/O/lock giữ workers của cơ chế CPU parallelism | Tác vụ khác chậm, CPU thấp nhưng chờ cao |
| **Side effects không an toàn** | Lambda sửa `ArrayList`, `HashMap`, counters dùng chung | Sai dữ liệu, kết quả không ổn định |
| **Ràng buộc thứ tự** | `sorted`, `limit`, `findFirst` trên nguồn ordered hoặc `forEachOrdered` | Mất bớt lợi ích của xử lý song song |

Điều quan trọng là **từng rủi ro phụ thuộc workload**. Nếu mỗi nhóm cực lớn, tính độc lập và hiệu năng chia việc tốt, một tầng song song ở trong có thể hữu ích; nhưng khi vòng ngoài cũng song song, phải đo lợi ích bổ sung trước khi giữ cả hai.

Một nguồn gồm vài chục phần tử với phép cộng đơn giản thường không đáng bật song song. Với nguồn lớn, phép tính nặng, dữ liệu chia đều và không có shared mutable state, parallel stream có thể đem lại lợi ích. Không tồn tại ngưỡng phần tử cố định đúng cho mọi ứng dụng.

## 4. Ví dụ runnable: ba cách xử lý cùng một bài toán

Giả sử có ba nhóm số nguyên. Ta cần tính tổng **bình phương** tất cả phần tử. Với dữ liệu từ 1 đến 9, kết quả phải là `1² + 2² + ... + 9² = 285`.

Tạo tệp **`NestedParallelComparison.java`**:

```java
import java.util.List;

public class NestedParallelComparison {
    public static void main(String[] args) {
        List<List<Integer>> groups = List.of(
                List.of(1, 2, 3),
                List.of(4, 5, 6),
                List.of(7, 8, 9));

        // Hai tầng parallel: hợp lệ, nhưng không tự động nhanh nhất.
        long nested = groups.parallelStream()
                .mapToLong(group -> group.parallelStream()
                        .mapToLong(x -> (long) x * x)
                        .sum())
                .sum();

        // Chỉ song song theo nhóm; mỗi nhóm xử lý tuần tự.
        long outerOnly = groups.parallelStream()
                .mapToLong(group -> group.stream()
                        .mapToLong(x -> (long) x * x)
                        .sum())
                .sum();

        // Làm phẳng nhóm và chỉ song song một pipeline.
        long flatOnce = groups.stream()
                .flatMap(List::stream)
                .parallel()
                .mapToLong(x -> (long) x * x)
                .sum();

        System.out.println("nested=" + nested);
        System.out.println("outerOnly=" + outerOnly);
        System.out.println("flatOnce=" + flatOnce);
    }
}
```

```bash
javac NestedParallelComparison.java
java NestedParallelComparison
```

Đầu ra xác định:

```text
nested=285
outerOnly=285
flatOnce=285
```

Cả ba phương án cho **cùng một kết quả toán học**. Ví dụ này cố ý không in thời gian vì dữ liệu quá nhỏ, JIT warm-up, scheduling và chi phí đo khiến microbenchmark từ `System.nanoTime()` dễ kết luận sai.

**Phương án nào nên dùng?**

- **`outerOnly`:** mỗi nhóm có ngữ nghĩa rõ, có đủ nhóm độc lập, công việc tính trong nhóm vừa phải hoặc việc ghép nhóm cần giữ ranh giới.
- **`flatOnce`:** phần tử có thể xử lý độc lập bất kể nhóm; muốn chỉ còn một pipeline song song; cần lưu ý chi phí `flatMap`, khả năng chia dữ liệu và thứ tự xử lý ở nguồn thực.
- **`nested`:** chỉ giữ khi kết quả đo chứng minh cần cả hai tầng trên workload thực tế, đồng thời không có contention/blocking làm hệ thống khác bị ảnh hưởng.

`parallel()` đặt sau `flatMap` làm **pipeline bên ngoài là parallel**; các stream trả bởi `List::stream` là nguồn bên trong dùng để flatten. Điều này không có nghĩa mỗi nhóm tạo một executor/pool mới. Nếu dữ liệu nhóm rất lệch, `flatMap` cũng không luôn cho mức cân bằng tốt nhất; việc chia mảnh của stream phụ thuộc nguồn và cách thực thi.

## 5. Quy tắc thực tiễn: chọn một cấp song song chính

Đối với CPU-bound nested loops, hãy bắt đầu bằng **một cấp song song** rõ ràng:

### A. Song song cấp ngoài, tuần tự cấp trong

Phù hợp khi có nhiều nhóm tương đối cân bằng và mỗi nhóm đủ công việc:

```java
long result = groups.parallelStream()
        .mapToLong(group -> group.stream()
                .mapToLong(this::calculate)
                .sum())
        .sum();
```

Đoạn trên chỉ minh họa vì `groups` và `calculate` là thành phần giả định. Dấu hiệu nên xem xét: số nhóm ít hơn nhiều so với số cores, hoặc một nhóm nặng hơn hẳn nhóm khác; khi đó song song chỉ cấp ngoài có thể không cân bằng.

### B. Tuần tự cấp ngoài, song song cấp trong

Phù hợp khi chỉ có rất ít nhóm nhưng mỗi nhóm khổng lồ và muốn xử lý từng nhóm một:

```java
long result = groups.stream()
        .mapToLong(group -> group.parallelStream()
                .mapToLong(this::calculate)
                .sum())
        .sum();
```

Vòng ngoài `stream()` tuần tự; mỗi nhóm có thể dùng toàn bộ khả năng song song phù hợp trước khi chuyển sang nhóm tiếp theo. Điều này **không** bảo đảm nhanh hơn flatten; đôi khi lặp lại overhead parallel pipeline cho từng nhóm còn tốn kém. Đây cũng là mã minh họa với thành phần chưa khai báo.

### C. Làm phẳng và song song một lần

Khi từng phần tử độc lập và không cần giữ kết quả từng nhóm:

```java
long result = groups.stream()
        .flatMap(List::stream)
        .parallel()
        .mapToLong(this::calculate)
        .sum();
```

Khi còn cần kết quả theo nhóm, việc flatten có thể làm mất thông tin group nếu không mang theo group id; hãy chọn dạng phù hợp với ý nghĩa dữ liệu. Cũng cần xem `flatMap` tạo pipeline đủ dễ phân chia chưa; không có một cách áp dụng cho mọi source.

### D. Để tất cả tuần tự

Nếu công việc rất nhỏ, phụ thuộc thứ tự, khó chia đều hoặc chạy ngay trong một hệ thống CPU đã bận, `stream()` tuần tự có thể nhanh và dễ đoán hơn. Đây là phương án baseline quan trọng, không phải thất bại của concurrency.

**Quy tắc:** từ workload thật, chọn mức chia tác vụ đủ lớn để chi phí tính toán vượt đáng kể chi phí chia/join, và **chỉ một lớp chịu trách nhiệm chính về song song** trừ khi có benchmark tốt cho lựa chọn khác.

## 6. Khi cần giới hạn số worker rõ ràng: dùng ExecutorService

Nếu muốn điều khiển số tác vụ chạy đồng thời, tách biệt với stream internals, có thể lập lịch **một công việc cho mỗi nhóm** vào một executor hữu hạn. Bên trong mỗi task, dùng stream tuần tự. Đây là phương án Java chuẩn khi bạn cần chủ động sở hữu pool, shutdown, lấy `Future`, xử lý lỗi và theo dõi vòng đời.

Ví dụ độc lập Java 21, **`BoundedGroupExecutor.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class BoundedGroupExecutor {
    public static void main(String[] args) throws Exception {
        List<List<Integer>> groups = List.of(
                List.of(1, 2, 3),
                List.of(4, 5, 6),
                List.of(7, 8, 9));

        List<Future<Long>> futures = new ArrayList<>();

        // Đúng hai worker cho ba nhóm; không nested parallel streams.
        try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
            for (List<Integer> group : groups) {
                futures.add(executor.submit(() ->
                        group.stream().mapToLong(x -> (long) x * x).sum()));
            }

            long result = 0;
            for (Future<Long> future : futures) {
                result += future.get();
            }
            System.out.println("bounded=" + result);
        }
    }
}
```

```bash
javac BoundedGroupExecutor.java
java BoundedGroupExecutor
```

Kết quả:

```text
bounded=285
```

**Giải thích:** Pool có tối đa hai worker xử lý các tasks đã nộp trong ví dụ. Mỗi task xử lý một nhóm tuần tự, `Future.get()` thu kết quả; cộng kết quả theo thứ tự futures để output ổn định. `try-with-resources` với `ExecutorService` được hỗ trợ từ Java 19 và chạy được trên Java 21; `close()` đợi các tác vụ hoàn thành theo hợp đồng API.

**Cảnh báo về khối lượng nộp:** `newFixedThreadPool` sử dụng hàng đợi không bị ràng buộc kích thước theo factory chuẩn. Tạo một triệu tasks một lúc vẫn có thể gây áp lực bộ nhớ dù chỉ có hai worker. Nếu dữ liệu có thể đến vô hạn, dùng cơ chế giới hạn số tác vụ chờ/batch, bounded `ThreadPoolExecutor` hoặc backpressure. Việc giới hạn worker **không tự động giới hạn số tasks đang xếp hàng**.

Mẫu trên hợp lý khi từng nhóm đủ lớn. Nếu mỗi nhóm chỉ có vài phép cộng, overhead tạo `Future`, xếp hàng và scheduling có thể đắt hơn stream tuần tự.

### Không “khóa cứng” parallel stream bằng cách dựa vào custom ForkJoinPool

Có thể bắt gặp mã `customPool.submit(() -> data.parallelStream()...)`. Đừng coi hành vi chọn pool của một stream cụ thể là cam kết chung do Stream API cung cấp. Đặc biệt, nếu trong pipeline lại gọi `parallelStream()` ở cấp trong, bạn chưa giải quyết được việc phân chia lồng nhau, chỉ đổi bối cảnh lập lịch theo triển khai. Khi cần một cấu hình điều phối rõ ràng, `ExecutorService` hoặc `ForkJoinTask` tự thiết kế có contract và lifecycle phù hợp hơn.

## 7. Nếu inner computation là blocking I/O, hãy đổi mô hình

Parallel stream được dùng hiệu quả nhất cho phép biến đổi/giảm dữ liệu **độc lập, ít side effects và thường CPU-bound**. Một inner lambda gọi HTTP, JDBC hoặc file blocking trong pool Fork/Join có thể giữ các worker đang chờ I/O, khiến những phép tính khác chia sẻ common pool bị chậm.

Ví dụ dạng cần cân nhắc lại (chỉ minh họa):

```java
var result = orders.parallelStream()
        .map(order -> order.lines().parallelStream()
                .map(line -> remotePriceService.fetch(line)) // Blocking I/O.
                .toList())
        .toList();
```

Ở đây `orders`, `lines()` và `remotePriceService` giả định; đoạn mã không runnable độc lập. Nếu dịch vụ bên ngoài giới hạn 20 requests đồng thời, dù có 100 cores vẫn không nên gửi vô hạn requests.

Các lựa chọn tốt hơn gồm: **một executor được quản lý** kèm giới hạn số I/O đồng thời, một API async phù hợp, hoặc với Java 21 là một virtual thread cho mỗi tác vụ blocking I/O kèm `Semaphore`/connection pool theo quota. Virtual threads giảm chi phí thread trong nhiều tình huống chờ I/O, nhưng không tăng khả năng của database hay API phía sau. Đừng dùng nested parallel stream như cơ chế tự động kiểm soát request concurrency.

Không có lựa chọn nào mặc định đúng cho mọi I/O driver; timeout, cancellation, bounded queue, resource quota và workload thực tế vẫn cần được đo và xử lý.

## 8. Đúng dữ liệu trước khi nhanh: side effects và reduction

Khi thêm một tầng parallel, các lambda có thể chạy đồng thời và theo thứ tự khó dự đoán. Hãy ưu tiên **stateless operations** và các phép reduction an toàn.

### Một lỗi phổ biến

```java
List<Integer> results = new ArrayList<>();
groups.parallelStream().forEach(group ->
        group.parallelStream().forEach(results::add));
```

Đây chỉ là đoạn minh họa (chưa có `groups`). `ArrayList` không an toàn cho nhiều threads cùng `add`; dữ liệu có thể thiếu, sai hoặc gặp lỗi. Không sửa bằng cách chuyển sang `Collections.synchronizedList` rồi nghĩ rằng nested parallel chắc chắn nhanh: lock vẫn gây contention, thứ tự kết quả không nhất thiết như ý.

Cách diễn đạt kết quả bằng pipeline rõ hơn:

```java
List<Integer> results = groups.stream()
        .flatMap(List::stream)
        .parallel()
        .map(x -> x * 2)
        .toList();
```

Đoạn này giả định `groups` là `List<List<Integer>>`. `Stream.toList()` tập hợp kết quả theo encounter order nếu nguồn có thứ tự, trả danh sách không thể thay đổi bằng các thao tác mutate. Nó không cần một `ArrayList` chung được chỉnh từ nhiều worker. Nếu muốn kết quả theo nhóm, nên dùng phép `map` trả về một list riêng cho mỗi nhóm và thu thập ở pipeline ngoài.

### Tính đúng đắn của phép reduction

Phép `reduce` chạy song song dựa trên khả năng kết hợp các kết quả từng phần. Hàm tổ hợp nên **associative**, identity phải đúng, các lambda không can thiệp nguồn trong lúc duyệt. Phép cộng `long` với dữ liệu không tràn có thể kết hợp dễ kiểm soát; với `double`, thứ tự cộng thay đổi có thể gây khác biệt bit do sai số floating-point. `String` nối bằng phép cộng trong reduction có thể gây allocation lớn; cân nhắc `Collectors.joining()` nếu bài toán thích hợp.

**Thứ tự xử lý:** `forEach` trên parallel stream không bảo đảm encounter order; `forEachOrdered` giữ thứ tự nhưng có thể giảm throughput. Các pipeline ordered chứa `limit`, `skip`, `takeWhile`, `dropWhile`, `sorted` hoặc `distinct` có thể cần phối hợp thêm, tùy source và semantics. Chỉ dùng `unordered()` khi nghiệp vụ thật sự không cần thứ tự, không dùng chỉ để “tăng tốc” nếu làm sai kết quả.

**Short-circuiting:** `findAny()` có thể trả phần tử khác nhau giữa các lần chạy; `findFirst()` có ràng buộc thứ tự. Nested parallel short-circuiting có thể làm thêm việc trước khi hủy/phát hiện kết quả ở các branches; đừng dựa vào số lần gọi mapper như hợp đồng.

## 9. Mất cân bằng tải và kích thước tác vụ

Giả sử một nhóm có 100.000 phần tử, còn 100 nhóm khác có 5 phần tử. Nếu chỉ parallel cấp ngoài, một worker có thể gánh nhóm khổng lồ trong khi các nhóm nhỏ đã xong. Trước khi bật song song vòng trong, cân nhắc:

1. **Tách nhóm lớn thành các chunks** đủ đều để lập lịch ở **một cấp duy nhất**, giữ `groupId` nếu cần tổng hợp theo nhóm.
2. **Sử dụng một pipeline phẳng** nếu phần tử độc lập; đo xem source/`Spliterator` có hỗ trợ chia mảnh tốt không.
3. **Lập lịch nhiệm vụ theo nhóm/chunk trong executor** với số worker phù hợp để có quyền kiểm soát tài nguyên.
4. **Giữ tuần tự** nếu số phần tử nhỏ hoặc chi phí xử lý từng phần tử thấp.

Với bài toán một ma trận `rows × cols` cần thực hiện cùng phép tính độc lập trên từng ô, có thể biểu diễn thành **một dải chỉ số tuyến tính** (đoạn minh họa, không phải chương trình độc lập):

```java
long total = java.util.stream.LongStream
        .range(0, (long) rows * cols)
        .parallel()
        .map(index -> {
            int row = (int) (index / cols);
            int col = (int) (index % cols);
            return calculate(row, col);
        })
        .sum();
```

Ở đây `rows` và `cols` phải dương, `calculate` là hàm giả định trả `long`; cần đảm bảo chỉ số phù hợp miền `int` và tích `(long) rows * cols` không tràn. Dạng này tạo **một cấp parallel** thay vì `rows` parallel bên ngoài và `cols` parallel bên trong, đồng thời có thể cho phép nguồn chỉ số liên tiếp chia tác vụ đều hơn. Nhưng nếu tính toán giữ state theo từng hàng, việc biến đổi có thể phải xét lại điều kiện an toàn và ngữ nghĩa.

## 10. Đánh giá hiệu năng bằng số đo, không bằng số lần gọi `parallel()`

Cần so sánh ít nhất **bốn phiên bản tương đương về kết quả**:

1. Tuần tự hoàn toàn.
2. Chỉ parallel tầng ngoài.
3. Flatten / chỉ parallel một tầng hợp lý.
4. Nested parallel, chỉ để kiểm chứng có lợi ích bổ sung hay không.

Đo với workload đủ lớn và đại diện, không dùng 9 số nguyên của ví dụ giáo khoa để kết luận về throughput. Sử dụng **JMH** cho microbenchmark Java vì JIT, dead-code elimination, warm-up và GC có thể làm sai kết quả khi tự đo bằng một vòng lặp `System.nanoTime()`. Với workload ứng dụng, còn phải xem CPU utilization, throughput, tail latency, allocation, GC, số task waiting và contention.

Thiết kế thử nghiệm:

- Chạy cùng JVM/JDK, cùng số CPU cores/quota, cùng dữ liệu, cùng terminal operation và logic tính.
- Warm up trước; lặp nhiều lần, xem phân bố kết quả thay vì chỉ lần nhanh nhất.
- Đảm bảo kết quả được sử dụng để JIT không loại bỏ tính toán; xác nhận output của mọi phiên bản đúng.
- Thử ít/giữa/nhiều nhóm; nhóm cân bằng và nhóm lệch; công việc mỗi phần tử nhẹ và nặng.
- Đo cả khi hệ thống có **tải khác sử dụng common pool**, vì benchmark độc lập có thể bỏ qua sự tranh chấp trong môi trường thực.
- Nếu có I/O, đo quota và tình trạng bên ngoài, đặt timeout; không so sánh bằng dữ liệu ngẫu nhiên hoặc dịch vụ thay đổi liên tục mà không kiểm soát.

Một cách đọc kết quả: nếu phiên bản nested dùng nhiều CPU hơn nhưng throughput không tăng, đó có thể là overhead/contended resource. Nếu CPU thấp và thời gian chờ cao, điều tra blocking/locking và nguồn dữ liệu. Nếu flatten chậm, xem lại `flatMap`, locality và cách chia việc trước khi kết luận “nested luôn tốt”.

**Không điều chỉnh** `-Djava.util.concurrent.ForkJoinPool.common.parallelism` trên toàn JVM chỉ để tối ưu một đoạn code nếu các thành phần khác cùng dùng common pool. Thuộc tính này thay đổi tài nguyên chung và không phải giải pháp cho việc chia quá nhỏ, pipeline sai semantics hoặc blocking. Nếu cần phân vùng tải có hợp đồng rõ ràng, thiết kế executor riêng.

## 11. Các lỗi thiết kế thường gặp và cách xử lý

| Sai lầm | Cách xử lý |
|---|---|
| Bật `parallelStream()` ở mọi tầng vì “có nhiều core” | Chọn một tầng song song, chứng minh lợi ích bằng benchmark |
| Cho rằng nested tự tạo pool riêng và vô hạn threads | Hiểu scheduler/common pool, đếm tasks/threads qua profiling thực tế |
| Mặc định nested parallel luôn deadlock | Chỉ kết luận deadlock khi có phụ thuộc/lock cycle cụ thể |
| Gọi I/O blocking trong Fork/Join workers | Dùng concurrency model cho I/O có timeout/quota rõ ràng |
| Inner stream xử lý vài phần tử nhưng vẫn parallel | Dùng `stream()` tuần tự để tránh overhead |
| `forEach` ghi vào mutable collection chung | Dùng stream reduction/`collect` đúng semantics hoặc dữ liệu phân vùng |
| Dữ liệu lệch nhưng chỉ parallel theo nhóm | Flatten/chunk hợp lý, đo lại độ cân bằng |
| Giới hạn fixed thread pool nhưng vẫn gửi vô hạn tasks | Bounded backlog, batching hoặc backpressure |
| Tự dùng custom FJP mà tưởng Stream API bảo đảm executor cụ thể | Xem đó là phụ thuộc triển khai; chọn API quản lý tác vụ rõ hợp đồng |
| So hiệu năng bằng một lượt `nanoTime` | Benchmark JMH hoặc load test có warm-up và đo nhiều lần |
| Dựa vào thứ tự `forEach` của parallel stream | Dùng reduction/collection hoặc `forEachOrdered` khi semantics yêu cầu |
| Đoán CPU concurrency bằng `availableProcessors()` rồi nhân số nested levels | Lấy CPU/quota thực tế làm ngân sách, tránh nhân mức song song |

### Checklist trước khi merge một nested stream

- Pipeline có **thật sự cần hai tầng song song** không? Vì sao một tầng không đủ?
- Các phần tử và groups có đủ lớn/độc lập để chia việc?
- Có I/O, lock, synchronized, `Future.get()` hoặc `join()` bên trong mapper không?
- Có nguồn shared mutable state, `ThreadLocal` hay side effects cần bảo vệ?
- Có ràng buộc encounter order, short-circuit hoặc reduction không associative?
- Có ai khác dùng cùng common pool?
- Đã có baseline tuần tự, một tầng song song và kết quả benchmark có thể lặp lại?
- Có tài nguyên khan hiếm hoặc task backlog cần giới hạn rõ ràng?

## 12. Bài tập tự kiểm tra

**Câu 1.** 20 groups, mỗi group 10 phần tử và phép tính chỉ là cộng số. Vì sao parallel ở cả hai tầng thường khó mang lại lợi ích?

**Câu 2.** 2 groups, mỗi group 5 triệu phần tử độc lập, tính toán CPU nặng. So sánh chiến lược parallel outer only, inner only, flatten một tầng và nguyên nhân cần benchmark.

**Câu 3.** Vì sao `groups.parallelStream().forEach(group -> group.parallelStream().forEach(sharedList::add))` có thể sai kết quả ngay cả khi bỏ qua tốc độ?

**Câu 4.** Một mapper gọi API HTTP cần chờ 200 ms, API giới hạn 10 requests đồng thời. Có nên tăng mức parallelism của common pool đến 500 không?

**Câu 5.** Thấy nested parallel làm chương trình chậm. Có thể kết luận chắc chắn deadlock, hoặc 1000 groups sẽ tạo 1000 OS threads không?

**Đáp án định hướng:** (1) overhead chia và ghép cao so với công việc; (2) outer only có ít nhóm để chia, inner only tận dụng nhóm lớn nhưng xử lý từng nhóm, flatten chia phần tử một cấp; đo cả overhead, locality và balance; (3) mutable list dùng chung không thread-safe; (4) không, cần mô hình I/O và giới hạn 10 lượt truy cập thực sự; (5) không, scheduler và số tác vụ khác số threads, phải chứng minh điều kiện kẹt cụ thể.

### Tài liệu chính thức

- [Java SE 21 — Stream API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html): `parallel()`, `flatMap()`, semantics của `forEach`, `reduce` và các toán tử.
- [Java SE 21 — java.util.stream package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html): stateless/non-interfering behavioral parameters, side effects, parallelism và reduction.
- [Java SE 21 — ForkJoinPool](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): common pool, work stealing, blocking và `ManagedBlocker`.
- [Java SE 21 — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): quản lý vòng đời, Future và bounded worker concurrency.
- [OpenJDK JMH project](https://openjdk.org/projects/code-tools/jmh/): công cụ benchmark Java chuyên dụng.