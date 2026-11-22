# Đối chiếu vòng lặp với Stream tuần tự và song song trong Java

> **Module:** Java 8 — **Kiểm thử và tối ưu**. Bài học so sánh ba cách xử lý cùng một tập dữ liệu: **vòng lặp for**, **Stream tuần tự (stream())** và **Stream song song (parallelStream() hoặc parallel())**. Trọng tâm là giữ nguyên kết quả và semantics trước khi đo hiệu năng; hiểu chi phí pipeline, boxing, phân tách dữ liệu, kết hợp kết quả, ordering và contention; chọn cách phù hợp với workload thực tế; và benchmark đúng bằng **JMH**. Các API Stream từ Java 8 vẫn được sử dụng trong Java hiện hành.

## 1. Vì sao cần so sánh ba cách?

Cùng một yêu cầu — lọc các số chẵn rồi tính tổng một phép biến đổi — có thể viết theo ba phong cách:

~~~java
// 1. Vòng lặp
long sum = 0L;
for (int value : values) {
    if ((value & 1) == 0) {
        sum += score(value);
    }
}
~~~

~~~java
// 2. Stream tuần tự
long sum = values.stream()
        .filter(value -> (value & 1) == 0)
        .mapToLong(MyClass::score)
        .sum();
~~~

~~~java
// 3. Stream song song
long sum = values.parallelStream()
        .filter(value -> (value & 1) == 0)
        .mapToLong(MyClass::score)
        .sum();
~~~

Cả ba đều có thể đúng. Nhưng chúng khác nhau về cách diễn đạt, điều khiển luồng, chi phí runtime và cách tận dụng CPU:

- **Vòng lặp:** chương trình điều khiển trực tiếp thứ tự duyệt và cập nhật biến cục bộ.
- **Stream tuần tự:** mô tả pipeline filter–map–reduce; các phần tử được xử lý theo chế độ tuần tự.
- **Stream song song:** runtime phân tách nguồn thành các phần, xử lý một số phần đồng thời rồi kết hợp kết quả.

Không có quy tắc chung rằng vòng lặp luôn nhanh nhất, Stream luôn dễ tối ưu hơn, hoặc parallel stream luôn nhanh hơn. Kết quả phụ thuộc loại dữ liệu, số lượng phần tử, chi phí trên mỗi phần tử, khả năng phân tách nguồn, thứ tự cần giữ, số lõi CPU và tải của ứng dụng.

**Mục tiêu đúng của tối ưu:** trước tiên ba cách phải thực hiện cùng một công việc và trả kết quả đúng theo cùng một contract; sau đó mới đo hiệu năng trong điều kiện đại diện cho môi trường sử dụng.

## 2. Phân biệt Stream tuần tự và song song

### 2.1. Stream là pipeline xử lý, không phải collection mới

Stream không lưu trữ các phần tử như List hoặc Set. Nó truyền dữ liệu từ một source qua các operation:

~~~text
Source
  |
  v
Intermediate operations
  filter -> map -> distinct -> ...
  |
  v
Terminal operation
  sum / reduce / collect / count
  |
  v
Result
~~~

Các intermediate operations như **filter**, **map** và **distinct** trả về một Stream mới. Chúng thường lazy: pipeline chưa duyệt dữ liệu cho đến khi có terminal operation. Terminal operation như **sum**, **count**, **collect** hoặc **forEach** kích hoạt quá trình xử lý.

Một Stream đã thực hiện terminal operation thì được xem là đã tiêu thụ; muốn xử lý lại cùng source, tạo Stream mới từ source đó. Không tái sử dụng cùng một Stream instance cho nhiều lần đo.

### 2.2. Stream tuần tự

~~~java
long total = values.stream()
        .filter(value -> value > 0)
        .mapToLong(Integer::longValue)
        .sum();
~~~

**Collection.stream()** tạo Stream tuần tự. Các phần tử được xử lý theo chế độ sequential; Stream không tự chia công việc cho nhiều worker threads.

Stream tuần tự vẫn có pipeline abstraction, laziness, primitive streams và terminal operations. Nó không đồng nghĩa với parallelism.

### 2.3. Stream song song

~~~java
long total = values.parallelStream()
        .filter(value -> value > 0)
        .mapToLong(Integer::longValue)
        .sum();
~~~

**Collection.parallelStream()** tạo Stream ở chế độ parallel. Một cách khác là:

~~~java
long total = values.stream()
        .parallel()
        .filter(value -> value > 0)
        .mapToLong(Integer::longValue)
        .sum();
~~~

**BaseStream.parallel()** chuyển mode của pipeline sang parallel. **sequential()** có thể chuyển lại sang sequential. Mode được đặt gần nhất áp dụng cho toàn pipeline khi terminal operation chạy; không nên nghĩ mỗi stage có một pool hay một mode độc lập.

Có thể kiểm tra mode:

~~~java
boolean parallel = values.parallelStream().isParallel();
~~~

### 2.4. Parallel không có nghĩa mỗi phần tử có một thread riêng

Runtime chia nguồn thành các phần nhỏ hơn, lập task và phân phối công việc. Nhiều phần tử có thể được xử lý trên cùng worker thread; một phần tử không được bảo đảm gắn với một thread cố định.

Không viết code dựa vào giả định:

- Mỗi phần tử chạy trên một thread mới.
- Các phần tử được xử lý theo thứ tự đầu vào.
- Một lambda luôn chạy trên cùng thread.
- parallelStream() luôn dùng toàn bộ CPU cores.
- Số task luôn bằng số phần tử hoặc số cores.

Đó không phải các bảo đảm của Stream API.

## 3. So sánh tổng quan

| Tiêu chí | for loop | Sequential Stream | Parallel Stream |
| --- | --- | --- | --- |
| Cách diễn đạt | Imperative, điều khiển từng bước | Declarative pipeline | Declarative pipeline có parallel execution |
| Thứ tự duyệt | Code kiểm soát trực tiếp | Theo semantics của source/operation | Có thể xử lý song song; encounter order vẫn phụ thuộc operation |
| Chi phí điều phối | Thường thấp, không cần chia task | Có pipeline machinery | Có thêm splitting, scheduling, merging |
| Điều khiển break/continue | Trực tiếp | Dùng short-circuit operations hoặc cấu trúc khác | Short-circuit có thể cần phối hợp các task |
| Shared mutable state | Có thể dùng local state đơn giản | Có thể dùng local state trong loop/pipeline | Phải tránh race và contention |
| Tận dụng nhiều cores | Không tự động | Không | Có thể |
| Phù hợp với công việc CPU độc lập | Có | Có | Có thể có lợi nếu workload đủ lớn |
| Công việc I/O blocking | Có thể điều khiển bằng executor phù hợp | Tuần tự, dễ kiểm soát | Thường không phải lựa chọn mặc định |
| Độ rõ ràng | Tốt cho logic nhiều nhánh | Tốt cho biến đổi dữ liệu | Tốt nếu pipeline stateless và reduction hợp lệ |
| Kết quả hiệu năng | Phụ thuộc workload/JIT | Phụ thuộc workload/JIT | Phụ thuộc thêm phân tách, scheduling và contention |

### 3.1. Khi nào vòng lặp là lựa chọn tốt?

Vòng lặp thường phù hợp khi:

- Logic có nhiều nhánh, break, continue, return hoặc trạng thái cục bộ phức tạp.
- Cần dừng ngay theo một điều kiện đặc biệt.
- Muốn điều khiển rõ ràng index, buffer hoặc cập nhật nhiều biến.
- Đang xử lý primitive arrays với phép toán đơn giản.
- Pipeline Stream làm code khó đọc hơn.
- Đo đạc cho thấy loop phù hợp hơn với hot path.

Không nên chọn vòng lặp chỉ vì một niềm tin chung rằng loop luôn nhanh hơn Stream.

### 3.2. Khi nào Stream tuần tự phù hợp?

Sequential Stream phù hợp khi:

- Bài toán tự nhiên là filter–map–reduce.
- Pipeline ngắn, stateless và dễ đọc.
- Muốn dùng Optional, primitive streams, collectors hoặc short-circuit operations.
- Không cần tận dụng nhiều CPU cores.
- Workload nhỏ hoặc overhead của parallel execution không đáng đánh đổi.

### 3.3. Khi nào Parallel Stream đáng thử?

Parallel Stream đáng thử khi:

- Có đủ dữ liệu để bù chi phí phân tách và kết hợp.
- Mỗi phần tử có công việc CPU đáng kể.
- Công việc giữa các phần tử độc lập.
- Nguồn có thể chia thành các phần cân bằng.
- Phép tổng hợp có thể kết hợp đúng.
- Không có shared mutable state gây race hoặc contention.
- Ứng dụng còn CPU capacity và common execution resources không bị quá tải.

Dù đáp ứng các điều kiện này, vẫn phải benchmark và kiểm tra trên workload thật.

## 4. Giữ cùng semantics khi đối chiếu

So sánh hiệu năng sẽ vô nghĩa nếu ba cách làm khác công việc.

Ví dụ không công bằng:

~~~java
// Loop chỉ cộng các số dương.
long loopSum = 0L;
for (int value : values) {
    if (value > 0) {
        loopSum += value;
    }
}

// Stream cộng tất cả số.
long streamSum = values.stream()
        .mapToLong(Integer::longValue)
        .sum();
~~~

Hai kết quả không thể so sánh vì điều kiện lọc khác nhau.

Một đối chiếu đúng phải thống nhất:

1. Cùng source và cùng dữ liệu.
2. Cùng điều kiện lọc.
3. Cùng phép biến đổi trên mỗi phần tử.
4. Cùng kiểu số và overflow policy.
5. Cùng cách xử lý null/invalid values.
6. Cùng yêu cầu về thứ tự.
7. Cùng cách tổng hợp và kết quả quan sát được.

### 4.1. Dùng cùng một hàm xử lý phần tử

~~~java
private static long score(int value) {
    long result = value;
    for (int i = 0; i < 24; i++) {
        result = (result * 1664525L + 1013904223L)
                ^ (result >>> 13);
    }
    return result & 0xFFFFL;
}
~~~

Đây là hàm deterministic, không đọc/ghi shared state và tạo cùng kết quả với cùng input. Nó chỉ dùng làm workload CPU cho ví dụ, không phải thuật toán mã hóa hoặc hàm băm bảo mật.

### 4.2. Loop trên List

~~~java
long sum = 0L;
for (Integer value : values) {
    if ((value & 1) == 0) {
        sum += score(value);
    }
}
~~~

### 4.3. Sequential Stream trên cùng List

~~~java
long sum = values.stream()
        .filter(value -> (value & 1) == 0)
        .mapToLong(MyClass::score)
        .sum();
~~~

### 4.4. Parallel Stream trên cùng List

~~~java
long sum = values.parallelStream()
        .filter(value -> (value & 1) == 0)
        .mapToLong(MyClass::score)
        .sum();
~~~

Cả ba phiên bản dùng cùng List<Integer>, điều kiện số chẵn và score. Vì source là ArrayList, phép chia nguồn thường thuận lợi hơn các source có khả năng splitting kém.

### 4.5. Primitive array và boxing

Nếu dữ liệu thực tế là int[], dùng primitive stream:

~~~java
long sum = Arrays.stream(numbers)
        .parallel()
        .filter(value -> (value & 1) == 0)
        .mapToLong(MyClass::score)
        .sum();
~~~

IntStream xử lý primitive int, tránh boxing mỗi phần tử thành Integer như Stream<Integer>. Khi benchmark, đừng so loop trên int[] với Stream trên List<Integer> rồi kết luận chênh lệch chỉ do loop/Stream; kiểu source và boxing đã khác nhau.

## 5. Parallel Stream hoạt động như thế nào?

### 5.1. Phân tách bằng Spliterator

Stream source cung cấp Spliterator, một abstraction có khả năng:

- Duyệt từng phần tử.
- Duyệt nhiều phần tử.
- Ước lượng số phần tử còn lại.
- Chia phần dữ liệu thành một Spliterator khác thông qua trySplit().
- Công bố characteristics như ORDERED, SIZED, SUBSIZED, IMMUTABLE hoặc CONCURRENT khi phù hợp.

Mô hình khái quát:

~~~text
             Original source
                    |
                    v
                Spliterator
                    |
             trySplit / split
               /         \
              v           v
          Partition A  Partition B
             |             |
             v             v
           Worker        Worker
             |             |
             v             v
        Partial result  Partial result
               \         /
                \       /
                 combine
                    |
                    v
               Final result
~~~

Runtime có thể tiếp tục chia mỗi partition thành các phần nhỏ hơn. Sau khi xử lý, partial results được kết hợp để tạo kết quả cuối.

### 5.2. Chất lượng Spliterator ảnh hưởng khả năng song song

Một nguồn tốt để parallelize thường có:

- Kích thước có thể biết hoặc ước lượng tốt.
- Cách chia cân bằng.
- Chi phí trySplit() thấp.
- Các phần dữ liệu độc lập và không cần copy quá nhiều.
- Characteristics chính xác.

Arrays và một số collection có thể cung cấp splitting hiệu quả. Nguồn tự tạo dựa trên iterator không biết kích thước hoặc có Spliterator chia không cân bằng có thể khiến một worker làm nhiều việc hơn các worker khác.

Nếu một partition mất quá lâu, các worker khác có thể rảnh trong khi task cuối vẫn chưa xong. Chia nhiều task hơn không tự bảo đảm hiệu năng tốt; tạo quá nhiều task cũng có chi phí.

### 5.3. Fork/Join và work stealing

Trong OpenJDK/Oracle JDK, parallel stream thường được thực thi bằng cơ chế fork/join. ForkJoinPool dùng work stealing: worker có thể lấy task đang chờ từ queue của worker khác để cân bằng công việc.

Parallel Stream thường chia sẻ common pool trong implementation này. Common pool cũng có thể phục vụ các ForkJoinTask khác trong ứng dụng. **Đây là hành vi implementation cần hiểu khi vận hành, không phải cam kết rằng mỗi Stream có pool riêng hoặc mỗi phần tử có thread riêng.**

### 5.4. Parallelism không đồng nghĩa với tăng số cores

Một máy có nhiều cores không bảo đảm pipeline tận dụng được hết chúng. Các yếu tố khác gồm:

- Số phần tử và độ lớn công việc mỗi phần tử.
- Chất lượng source splitting.
- Các task có cân bằng hay không.
- Chi phí combine.
- Memory bandwidth và cache behavior.
- Contention với những công việc khác.
- Runtime/JIT/GC và cấu hình container.

## 6. Chi phí của ba cách xử lý

### 6.1. Vòng lặp

Loop có thể rất trực tiếp:

~~~java
long sum = 0L;
for (int value : numbers) {
    sum += value;
}
~~~

Không cần tạo pipeline hoặc chia task. Tuy vậy, compiler/JIT vẫn có thể tối ưu loop; hiệu năng thực tế phụ thuộc code, kiểu dữ liệu, branch, memory access và runtime.

### 6.2. Sequential Stream

Sequential Stream có thêm abstraction và pipeline traversal. Nhưng pipeline có thể được tối ưu, các intermediate operations lazy và có thể được fuse thành một lần duyệt với ít intermediate state.

Không phải cứ có nhiều stage thì sẽ tạo một collection mới cho mỗi stage. filter/map thường không materialize List trung gian.

### 6.3. Parallel Stream

Parallel Stream có thêm các chi phí:

- Tạo/split tasks.
- Schedule task.
- Worker coordination.
- Kết hợp partial results.
- Buffering hoặc giữ encounter order khi cần.
- Cạnh tranh CPU/cache/memory với các hoạt động khác.

Với workload nhỏ hoặc mỗi phần tử quá rẻ, overhead có thể lớn hơn lợi ích. Với workload CPU-bound đủ lớn và độc lập, chi phí này có thể được bù bằng xử lý đồng thời.

### 6.4. Boxing và unboxing

~~~java
List<Integer> values = ...;

long sum = values.stream()
        .mapToLong(Integer::longValue)
        .sum();
~~~

List<Integer> lưu references tới Integer objects. Pipeline có thể cần unbox để tính số học. Nếu dữ liệu là primitive, IntStream, LongStream hoặc DoubleStream tránh boxing trong phần pipeline tương ứng.

### 6.5. Memory allocation và garbage collection

Không chỉ thời gian CPU quan trọng. Pipeline có thể tạo object phụ trợ, lambda objects, buffers hoặc collector containers tùy implementation và operation. Parallel processing có thể tạo nhiều partial result containers rồi kết hợp.

Không đếm allocation chỉ bằng số lần xuất hiện -> trong source. Hãy đo allocation/GC trên đúng runtime và workload bằng profiler hoặc benchmark phù hợp.

## 7. Workload nào phù hợp với Parallel Stream?

| Workload | Đánh giá | Lý do |
| --- | --- | --- |
| Tính toán CPU độc lập trên mảng lớn | Đáng thử | Dữ liệu dễ chia, mỗi phần tử có đủ công việc |
| Filter/map/reduce stateless | Đáng thử | Có thể xử lý từng partition rồi kết hợp |
| Tổng hợp số với phép toán hợp lệ | Đáng thử | Reduction có identity/combiner đúng |
| Mảng nhỏ, phép tính rất rẻ | Thường không đáng | Overhead chia task có thể lớn hơn công việc |
| ArrayList lớn, source ổn định | Đáng thử | Có kích thước và splitting thuận lợi |
| Source iterator không biết kích thước | Cần đo kỹ | Có thể chia partition kém |
| Gọi HTTP/database/file cho mỗi phần tử | Thường không phải lựa chọn mặc định | Blocking có thể chiếm worker/common pool |
| Cập nhật một biến hoặc collection dùng chung | Không nên làm trực tiếp | Race hoặc contention |
| Cần side effects theo thứ tự chính xác | Cần cân nhắc | Parallel execution không đảm bảo thứ tự thực thi lambda |
| sorted, distinct, ordered limit | Cần đo kỹ | Stateful/order constraints có thể cần buffer/coordination |
| Công việc đang cạnh tranh common pool | Cần đo tải thực | Parallel stream có thể làm tăng contention |
| Cần break/continue phức tạp | Loop thường rõ hơn | Điều khiển luồng trực tiếp dễ hiểu |

### 7.1. CPU-bound và I/O-bound

**CPU-bound:** mỗi phần tử thực hiện tính toán, xử lý ảnh, biến đổi dữ liệu hoặc kiểm tra độc lập. Parallel execution có cơ hội tận dụng nhiều cores.

**I/O-bound:** mỗi phần tử chờ network, database, file hoặc dịch vụ bên ngoài. Worker có thể bị block trong khi chờ I/O. Parallel Stream không phải một framework tổng quát để điều phối hàng nghìn tác vụ I/O; hãy chọn concurrency model và executor được thiết kế cho workload blocking, có giới hạn concurrency, timeout và backpressure.

Không nên đổi một vòng lặp gọi database tuần tự thành parallelStream() chỉ để “tăng tốc”. Cách đó có thể tạo tải lớn hơn lên connection pool, service downstream và common pool.

### 7.2. Kích thước dữ liệu không phải điều kiện duy nhất

Một triệu phép cộng rất rẻ có thể không đáng parallelize. Một tập nhỏ hơn nhưng mỗi phần tử cần tính toán CPU nặng có thể hưởng lợi. Hãy xét cả:

- N (số phần tử).
- C (chi phí mỗi phần tử).
- S (chi phí split/schedule/combine).
- P (parallelism khả dụng).
- M (memory và cache behavior).

Không có một ngưỡng N cố định dùng đúng cho mọi ứng dụng và mọi máy.

## 8. Reduction phải có identity và tính kết hợp phù hợp

### 8.1. Vì sao sum parallel dễ biểu diễn?

~~~java
long sum = numbers.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();
~~~

Runtime có thể tính partial sums rồi cộng lại. Phép cộng có tính kết hợp theo số học integer Java (phép cộng long thực hiện theo modulo 64-bit nếu overflow), nên có thể kết hợp các partial sums mà không cần một biến shared mutable duy nhất.

Tuy nhiên, overflow vẫn có thể làm kết quả không phù hợp với domain. Nếu tổng không được phép vượt miền long, cần kiểm tra range hoặc dùng kiểu số phù hợp.

### 8.2. reduce phải dùng toán tử associative

~~~java
int sum = numbers.parallelStream()
        .reduce(0, Integer::sum);
~~~

Một reduction có identity và combiner hợp lệ có thể được chia thành nhiều phần. Với phép cộng, identity là 0.

Phép toán cần thỏa tính kết hợp:

~~~text
(a op b) op c == a op (b op c)
~~~

Nếu phép toán không associative, thay đổi cách nhóm phần tử có thể thay đổi kết quả.

### 8.3. Ví dụ không phù hợp: phép trừ

~~~java
int result = numbers.parallelStream()
        .reduce(0, (left, right) -> left - right);
~~~

Phép trừ không associative. Kết quả có thể phụ thuộc cách chia/nhóm dữ liệu. Không dùng một phép toán tùy ý trong reduce rồi cho rằng parallel sẽ luôn giống loop.

### 8.4. Floating-point có thể khác ở bit cuối

Số thực dấu phẩy động có rounding. Phép cộng double không associative theo nghĩa toán học chính xác; các cách nhóm khác nhau có thể tạo khác biệt ở một vài bit cuối.

Nếu yêu cầu nghiệp vụ là so sánh số thực, xác định tolerance phù hợp. Nếu yêu cầu kết quả thập phân chính xác như tiền, chọn BigDecimal cùng scale/rounding policy rõ ràng. Đừng mặc định parallel floating-point sum sẽ luôn có cùng bit pattern với một loop tuần tự.

### 8.5. Collector phải tuân thủ contract

~~~java
List<String> names = people.parallelStream()
        .map(Person::getName)
        .collect(Collectors.toList());
~~~

collect với Collector phù hợp được thiết kế để hỗ trợ reduction. Runtime có thể tạo các container partial rồi kết hợp chúng theo contract của Collector.

Không tự thay bằng shared ArrayList bên ngoài rồi thêm phần tử từ nhiều worker.

## 9. Tránh side effects và shared mutable state

### 9.1. Lỗi race khi cập nhật một biến dùng chung

~~~java
long[] total = {0L};

numbers.parallelStream().forEach(value -> {
    total[0] += value;
});
~~~

Đây là code sai: nhiều thread có thể đọc và ghi total[0] đồng thời. Một số phép cộng có thể bị mất.

### 9.2. Dùng reduction thay cho shared accumulator

~~~java
long total = numbers.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();
~~~

Đây là biểu đạt đúng ý định: runtime quản lý partial results và combine.

### 9.3. Không mutate source collection trong pipeline

~~~java
// Không sửa collection nguồn trong lúc stream đang duyệt.
numbers.parallelStream()
        .filter(value -> {
            // numbers.remove(value); // Sai: interference.
            return value > 0;
        })
        .count();
~~~

Với source thông thường như ArrayList, không sửa collection trong khi pipeline đang thực thi. Interference có thể dẫn tới exception, kết quả sai hoặc behavior không phù hợp contract.

### 9.4. Không dùng synchronized để chữa mọi shared-state pipeline

Có thể khóa một accumulator dùng chung, nhưng lock contention có thể triệt tiêu lợi ích parallelism. Tốt hơn là dùng reduction/collector phù hợp để mỗi partition có accumulator riêng và kết hợp kết quả.

### 9.5. Lambda nên stateless và non-interfering

Một lambda stateless không phụ thuộc vào state thay đổi giữa các lần gọi. Non-interfering nghĩa là không làm thay đổi source theo cách ảnh hưởng traversal.

Các điều kiện này giúp pipeline cho kết quả nhất quán và hỗ trợ parallel execution an toàn.

### 9.6. Không dùng peek cho side effect nghiệp vụ

peek chủ yếu phục vụ quan sát/debug trong pipeline. Intermediate operations lazy; implementation có thể tối ưu/elide một số stage khi không ảnh hưởng kết quả terminal. Vì vậy không dùng peek để ghi dữ liệu bắt buộc, gửi message hoặc cập nhật trạng thái nghiệp vụ.

## 10. Encounter order và chi phí giữ thứ tự

### 10.1. Ordered source

List và arrays có encounter order. Một pipeline giữ order phải trả kết quả phù hợp với thứ tự đó khi operation yêu cầu.

Nhưng trong parallel execution, mapper/filter có thể chạy trên các thread và thời điểm khác nhau. **Encounter order của kết quả không đồng nghĩa với thứ tự gọi lambda.**

### 10.2. forEach và forEachOrdered

~~~java
numbers.parallelStream()
        .forEach(System.out::println);
~~~

forEach không đảm bảo in theo encounter order trong parallel stream.

~~~java
numbers.parallelStream()
        .forEachOrdered(System.out::println);
~~~

forEachOrdered đảm bảo thực hiện action theo encounter order, nhưng coordination để giữ thứ tự có thể làm giảm lợi ích song song.

### 10.3. unordered chỉ khi không cần thứ tự

~~~java
long count = numbers.parallelStream()
        .unordered()
        .distinct()
        .count();
~~~

unordered() cho phép bỏ ràng buộc encounter order nếu semantics của bài toán không cần thứ tự. Điều này có thể giúp một số stateful/terminal operations chạy hiệu quả hơn.

Không thêm unordered() chỉ vì thấy nó trong ví dụ tối ưu; nếu thứ tự là yêu cầu nghiệp vụ, bỏ order sẽ đổi semantics.

### 10.4. Stateful operations

Các operation như sorted() và distinct() có thể cần state/buffering. Ordered limit() cũng có thể cần phối hợp để đảm bảo lấy đúng những phần tử đầu tiên theo encounter order.

Nếu pipeline chủ yếu là stateless filter/map, parallel execution thường dễ chia hơn. Nếu pipeline có nhiều stateful operations, cần đo memory, buffering và thời gian combine.

## 11. Data source: ArrayList, LinkedList, array và custom source

### 11.1. Array và ArrayList

Arrays và ArrayList thường cung cấp size information và cách split tương đối thuận lợi. Chúng là source hợp lý để bắt đầu benchmark CPU-bound parallel operations.

### 11.2. LinkedList

Không giả định mọi collection đều split tốt như array. Một source cần đi qua nhiều node để tìm ranh giới partition hoặc có cách chia mất cân bằng có thể làm giảm lợi ích parallelism.

Hãy kiểm tra spliterator() và đo source thực tế thay vì chọn parallel mode chỉ theo số phần tử.

### 11.3. Iterator-based/custom Stream

Nếu tạo Stream từ một Iterator bằng Spliterators.spliteratorUnknownSize, runtime có thể thiếu thông tin size và bị giới hạn bởi cách split đơn giản. Parallel performance có thể kém.

Nếu tự triển khai Spliterator, phải thiết kế đúng trySplit, estimateSize và characteristics. Chỉ khai báo SIZED, SUBSIZED, ORDERED hoặc CONCURRENT khi semantics thực sự đáp ứng các đặc tính đó.

### 11.4. Source phải ổn định trong quá trình xử lý

Một source có thể thay đổi đồng thời sẽ tạo rủi ro interference. Nếu source là concurrent collection và Spliterator báo CONCURRENT, semantics khác với ArrayList thông thường. Không tự giả định mọi collection đều cho phép concurrent mutation.

## 12. Common ForkJoinPool và contention

### 12.1. Common pool là tài nguyên dùng chung

Trong OpenJDK, parallel stream thường dựa trên Fork/Join common pool. Pool này có thể được chia sẻ với các ForkJoinTask khác trong cùng JVM.

Nếu một ứng dụng có nhiều thành phần cùng chạy parallel tasks, chúng có thể cạnh tranh:

- CPU cores.
- Worker threads.
- Queue/task scheduling.
- Memory bandwidth và cache.
- Tài nguyên downstream nếu tác vụ có side effects/I/O.

### 12.2. Blocking I/O có thể làm worker không sẵn sàng

Fork/Join phù hợp với task có thể chia nhỏ và join. Nếu worker bị block lâu trên HTTP, database hoặc file I/O, pool có thể không còn worker sẵn sàng cho các tác vụ CPU khác.

Tài liệu ForkJoinPool cảnh báo không có bảo đảm duy trì đủ parallelism khi task bị block bởi I/O hoặc synchronization không được quản lý.

### 12.3. Không tự điều chỉnh common pool như giải pháp đầu tiên

Common pool có system properties cấu hình parallelism và thread factory trong các runtime hỗ trợ. Thay đổi chúng ảnh hưởng đến các công việc khác dùng common pool, nên cần đánh giá toàn ứng dụng.

Nếu workload cần concurrency isolation, deadline, cancellation hoặc blocking I/O, dùng executor/concurrency model được thiết kế cho nhu cầu đó thay vì dùng parallel stream làm thread pool tổng quát.

### 12.4. Nested parallelism có thể làm khó dự đoán

Nếu một parallel stream gọi thêm một parallel stream trong mỗi phần tử, nhiều lớp task decomposition có thể cạnh tranh cùng tài nguyên. Không mặc định nested parallel stream sẽ nhân số cores hoặc tăng throughput.

Đo toàn bộ workload và ưu tiên một cấp phân chia công việc rõ ràng.

## 13. Benchmark đúng: vì sao không nên chỉ dùng System.nanoTime?

Một phép đo đơn giản:

~~~java
long start = System.nanoTime();
long result = calculate();
long elapsed = System.nanoTime() - start;
~~~

có thể hữu ích để đo latency của một đoạn ứng dụng đã được kiểm soát, nhưng **không đủ để kết luận microbenchmark loop vs Stream** nếu chạy một lần.

JVM là runtime tối ưu hóa thích nghi. Các yếu tố ảnh hưởng phép đo:

- Class loading và JIT compilation.
- Warmup và code profile.
- Dead-code elimination.
- Constant folding.
- Garbage collection.
- CPU frequency/power state.
- Thread scheduling và background load.
- Input size, data distribution và cache state.
- Runtime version và JVM flags.

### 13.1. Dùng JMH cho microbenchmark JVM

JMH (Java Microbenchmark Harness) là công cụ OpenJDK dành cho việc xây dựng và chạy benchmark JVM. Nó cung cấp cơ chế warmup, measurement, forks và xử lý kết quả để giảm nhiều sai lệch phổ biến.

JMH không làm một benchmark sai methodology tự động trở nên đúng; người viết vẫn phải bảo đảm workload công bằng và kết quả được sử dụng.

### 13.2. Đặt input preparation ngoài vùng đo

Nếu ứng dụng production nhận một mảng đã có sẵn, benchmark không nên tạo lại mảng trong từng invocation nếu mục tiêu là đo traversal. Dùng @Setup(Level.Trial) để chuẩn bị dữ liệu trước benchmark.

Nếu chi phí tạo dữ liệu là một phần của đường xử lý thật, tạo một benchmark khác bao gồm bước đó. Đừng trộn hai câu hỏi vào một phép đo.

### 13.3. Giữ cùng một phép tính

Mỗi benchmark method phải:

- Dùng cùng input.
- Cùng điều kiện filter.
- Cùng hàm tính toán.
- Cùng kiểu result.
- Cùng overflow/rounding semantics.
- Không thêm logging hoặc I/O.
- Không tạo thêm công việc ngoài ý định đo.

### 13.4. Warmup, measurement và forks

- **Warmup:** cho JVM thời gian chạy và tối ưu code trước khi đo.
- **Measurement:** thu thập các lần đo sau warmup.
- **Fork:** chạy benchmark trong JVM process riêng để giảm ảnh hưởng trạng thái từ benchmark khác.
- **Threads:** xác định số caller chạy đồng thời; benchmark một caller khác với tải nhiều request.

### 13.5. Không bỏ kết quả tính toán

Nếu benchmark không dùng result, JIT có thể loại bỏ phần computation không tạo ra observable effect. Một benchmark method trả về kết quả thường đủ để JMH consume result. Nếu benchmark method cần trả void hoặc tạo nhiều kết quả, dùng Blackhole theo hướng dẫn JMH.

### 13.6. Đo nhiều khía cạnh

Ngoài average time, xem xét:

- Throughput.
- Latency distribution.
- Allocation rate.
- GC activity.
- CPU utilization.
- Contention.
- Memory footprint.
- Ảnh hưởng đến các request khác.

Một biến thể nhanh hơn trong microbenchmark không nhất thiết làm toàn ứng dụng nhanh hơn nếu nó làm common pool hoặc downstream service quá tải.

## 14. Ví dụ JMH: đối chiếu loop, sequential Stream và parallel Stream

Đây là benchmark riêng, cần dependency và annotation processor của JMH. Nó không phải một file Java độc lập chỉ với JDK.

Tạo project theo Maven archetype JMH chính thức:

~~~bash
mvn archetype:generate \
  -DinteractiveMode=false \
  -DarchetypeGroupId=org.openjdk.jmh \
  -DarchetypeArtifactId=jmh-java-benchmark-archetype \
  -DgroupId=example \
  -DartifactId=loop-stream-bench \
  -Dversion=1.0
~~~

Thêm class **LoopVsStreamBenchmark.java** vào source folder của project được tạo:

~~~java
import java.util.Arrays;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Threads;
import org.openjdk.jmh.annotations.Warmup;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
@Threads(1)
public class LoopVsStreamBenchmark {
    @State(Scope.Thread)
    public static class Input {
        @Param({"1000", "100000", "1000000"})
        public int size;

        int[] values;

        @Setup(Level.Trial)
        public void setup() {
            values = new int[size];
            for (int i = 0; i < size; i++) {
                values[i] = i - size / 2;
            }
        }
    }

    private static long score(int value) {
        long result = value;
        for (int i = 0; i < 24; i++) {
            result = (result * 1664525L + 1013904223L)
                    ^ (result >>> 13);
        }
        return result & 0xFFFFL;
    }

    @Benchmark
    public long forLoop(Input input) {
        long sum = 0L;
        for (int value : input.values) {
            if ((value & 1) == 0) {
                sum += score(value);
            }
        }
        return sum;
    }

    @Benchmark
    public long sequentialStream(Input input) {
        return Arrays.stream(input.values)
                .filter(value -> (value & 1) == 0)
                .mapToLong(LoopVsStreamBenchmark::score)
                .sum();
    }

    @Benchmark
    public long parallelStream(Input input) {
        return Arrays.stream(input.values)
                .parallel()
                .filter(value -> (value & 1) == 0)
                .mapToLong(LoopVsStreamBenchmark::score)
                .sum();
    }
}
~~~

Trong benchmark này:

- Cả ba methods dùng cùng int[] và cùng score.
- Dữ liệu được tạo ở @Setup(Level.Trial), ngoài vùng đo.
- @Param cho phép đo nhiều kích thước dữ liệu.
- @Threads(1) giúp bắt đầu bằng kịch bản một benchmark caller; parallel stream vẫn có thể chia công việc bên trong.
- Các method trả long để kết quả được harness quan sát.
- Workload là CPU-bound có chủ đích, không phải ví dụ cho network/database I/O.

Build và chạy:

~~~bash
mvn clean verify
java -jar target/benchmarks.jar
~~~

Đây là lệnh chạy benchmark JMH. Không có một stdout thời gian cố định cho mọi máy; JMH sẽ báo kết quả dựa trên CPU, JVM, runtime flags, kích thước input và môi trường thực thi.

### 14.1. Vì sao không đưa một con số thắng cuộc vào bài?

Một máy có ít cores, một máy nhiều cores, hoặc một container bị giới hạn CPU có thể cho kết quả khác nhau. Khi đổi JDK, GC, heap, data size hoặc số request đồng thời, thứ hạng cũng có thể đổi.

Hãy lưu benchmark result cùng metadata: CPU, số cores/CPU quota, OS, JDK vendor/version, JVM flags, JMH version, input size, benchmark mode và số threads.

### 14.2. So sánh thêm tải đồng thời

Benchmark @Threads(1) trả lời câu hỏi: “Một caller chạy từng phương án có hiệu năng ra sao khi parallel stream được phép dùng parallel workers?”

Nó không trả lời đầy đủ: “100 request đồng thời trong production sẽ ra sao?” Để trả lời câu hỏi thứ hai, cần benchmark/load test có mức concurrency tương ứng và theo dõi common pool, CPU, latency, queueing và downstream services.

### 14.3. Không dùng một microbenchmark làm quyết định kiến trúc

JMH phù hợp để cô lập hot path. Load test và production profiling giúp đánh giá hệ thống tổng thể. Dùng cả hai khi tối ưu một service quan trọng.

## 15. Cách đọc kết quả benchmark

### 15.1. Average time thấp hơn

Nếu Mode.AverageTime, score thường biểu diễn thời gian trung bình mỗi invocation theo đơn vị đã chọn. Giá trị thấp hơn nghĩa là nhanh hơn trong benchmark đó.

### 15.2. Throughput cao hơn

Nếu Mode.Throughput, score biểu diễn số operation mỗi đơn vị thời gian. Giá trị cao hơn nghĩa là nhiều operation hơn trong benchmark đó.

Không so trực tiếp các score nếu mode/unit khác nhau.

### 15.3. Error/confidence interval quan trọng

Nếu chênh lệch giữa hai phương án nhỏ hơn độ dao động của phép đo, không nên kết luận phương án này nhanh hơn một cách chắc chắn. Chạy đủ forks/iterations và lặp lại trong điều kiện ổn định.

### 15.4. Xem kết quả theo input size

Một phương án có thể thua ở 1.000 phần tử nhưng thắng ở 1.000.000 phần tử. Hãy đọc kết quả theo từng @Param, không lấy một kích thước rồi suy rộng cho tất cả.

### 15.5. Xem allocation và GC

Parallel Stream có thể tăng throughput nhưng cũng tăng allocation hoặc memory pressure trong một số pipeline. Nếu GC tăng làm latency p99 xấu đi, lợi ích average time chưa chắc phù hợp production.

## 16. Các sai lầm thường gặp và cách sửa

### Lỗi 1 — Nghĩ parallelStream luôn nhanh hơn stream

Parallel có overhead split/schedule/combine. **Sửa:** đo trên input và workload thật.

### Lỗi 2 — Nghĩ loop luôn nhanh hơn Stream

JIT có thể tối ưu cả loop và pipeline; kết quả phụ thuộc workload. **Sửa:** so sánh cùng semantics bằng benchmark.

### Lỗi 3 — So ba cách với ba bộ dữ liệu khác nhau

Kết quả không còn apples-to-apples. **Sửa:** dùng cùng source/input và cùng phép tính.

### Lỗi 4 — Đo cả thời gian tạo dữ liệu ở một phương án

Đã thêm chi phí không thuộc mục tiêu đo. **Sửa:** chuẩn bị input ngoài timed region hoặc đo riêng end-to-end.

### Lỗi 5 — Dùng System.nanoTime một lần làm kết luận

JIT/warmup/GC/scheduler có thể chi phối. **Sửa:** dùng JMH cho microbenchmark.

### Lỗi 6 — Benchmark không consume kết quả

JIT có thể loại computation không ảnh hưởng kết quả. **Sửa:** trả result hoặc dùng Blackhole.

### Lỗi 7 — Đưa System.out.println vào vòng benchmark

Console I/O áp đảo chi phí cần đo. **Sửa:** bỏ logging khỏi timed method.

### Lỗi 8 — Dùng input quá nhỏ

Chi phí split/schedule lớn hơn công việc. **Sửa:** đo nhiều kích thước.

### Lỗi 9 — Chỉ đo input rất lớn

Có thể bỏ lỡ workload thực tế nhỏ/vừa. **Sửa:** dùng phân phối kích thước gần production.

### Lỗi 10 — So List<Integer> với int[]

Boxing/unboxing và data layout khác nhau. **Sửa:** dùng cùng source type hoặc benchmark riêng hai representation.

### Lỗi 11 — Dùng LinkedList rồi suy ra mọi Stream song song chậm

Source splitting khác nhau. **Sửa:** đánh giá Spliterator và source thật.

### Lỗi 12 — Tạo shared accumulator trong parallel forEach

Có data race hoặc lost updates. **Sửa:** dùng sum, reduce hoặc Collector đúng.

### Lỗi 13 — Đồng bộ mọi update bằng synchronized rồi kỳ vọng tăng tốc

Lock contention có thể triệt tiêu parallelism. **Sửa:** dùng reduction/partition-local accumulation.

### Lỗi 14 — Dùng stateful lambda trong map/filter

Kết quả có thể phụ thuộc scheduling và thứ tự thực thi. **Sửa:** giữ behavioral parameters stateless.

### Lỗi 15 — Sửa source collection khi Stream đang chạy

Có thể gây exception hoặc kết quả không đúng. **Sửa:** không can thiệp source trong traversal.

### Lỗi 16 — Nghĩ parallel mapper chạy theo encounter order

Thứ tự xử lý lambda không được bảo đảm. **Sửa:** chỉ dựa vào encounter order của kết quả khi API operation bảo đảm.

### Lỗi 17 — Dùng forEach để in kết quả song song theo thứ tự

forEach không đảm bảo encounter order. **Sửa:** dùng forEachOrdered nếu thứ tự bắt buộc, và đo chi phí ordering.

### Lỗi 18 — Gọi unordered khi nghiệp vụ cần order

Kết quả có thể đổi semantics. **Sửa:** chỉ bỏ order khi không có yêu cầu thứ tự.

### Lỗi 19 — Quên tính chi phí sorted/distinct/limit

Stateful/order-sensitive operations có thể buffer và phối hợp nhiều hơn. **Sửa:** benchmark toàn pipeline.

### Lỗi 20 — Dùng phép toán không associative trong reduce

Kết quả phụ thuộc cách nhóm. **Sửa:** chọn identity, accumulator và combiner phù hợp.

### Lỗi 21 — Cho rằng double sum luôn giống loop từng bit

Floating-point rounding phụ thuộc thứ tự cộng. **Sửa:** xác định tolerance/reproducibility policy.

### Lỗi 22 — Dùng parallel stream cho blocking I/O

Worker có thể bị giữ khi chờ I/O và ảnh hưởng common pool. **Sửa:** chọn executor/concurrency model dành cho blocking tasks.

### Lỗi 23 — Nghĩ mỗi parallel stream có pool riêng

Trong OpenJDK, common pool thường được dùng. **Sửa:** đánh giá contention ở cấp JVM và không phụ thuộc pool riêng.

### Lỗi 24 — Tạo nested parallel streams không đo

Các tầng parallel tasks có thể cạnh tranh. **Sửa:** thiết kế một cấp phân chia công việc rõ ràng.

### Lỗi 25 — Chỉ xem average time

Latency tail, allocation, GC và throughput có thể xấu đi. **Sửa:** theo dõi metric phù hợp với SLA.

### Lỗi 26 — Chọn parallel chỉ vì server có nhiều cores

CPU quota, memory bandwidth, contention và workload có thể hạn chế. **Sửa:** benchmark trong môi trường deployment.

### Lỗi 27 — Benchmark JDK khác với production

JIT, GC và library implementation có thể khác. **Sửa:** dùng cùng runtime hoặc xác nhận trên runtime triển khai.

### Lỗi 28 — Chỉnh common pool toàn JVM để sửa một benchmark

Có thể ảnh hưởng những thành phần khác. **Sửa:** profile và đánh giá toàn ứng dụng trước khi đổi cấu hình.

### Lỗi 29 — Cho rằng parallel stream là thay thế cho executor quản lý task

Stream phù hợp cho aggregate data processing; không cung cấp đầy đủ queue, per-task timeout, retry, cancellation và isolation theo nhu cầu service. **Sửa:** dùng concurrency API phù hợp khi cần điều phối task.

### Lỗi 30 — Tối ưu trước khi biết bottleneck

Có thể hot path thực tế là I/O, database, lock hoặc serialization. **Sửa:** profile ứng dụng, xác định bottleneck rồi benchmark đoạn code liên quan.

## 17. Checklist trước khi chọn loop, sequential hoặc parallel

| Câu hỏi | Điều cần xác minh |
| --- | --- |
| Ba phương án làm cùng một việc? | Cùng input, filter, mapping, reduction |
| Kiểu dữ liệu giống nhau? | Primitive array/List và boxing rõ ràng |
| Kết quả có đúng không? | Unit test/correctness check trước benchmark |
| Có side effects trong lambda? | Loại bỏ hoặc quản lý rõ ràng |
| Có shared mutable state? | Dùng reduction/collector phù hợp |
| Phép toán có associative không? | Identity/accumulator/combiner hợp lệ |
| Có yêu cầu encounter order? | forEachOrdered/order constraints khi cần |
| Source có split tốt không? | Spliterator size và characteristics |
| Workload CPU-bound hay I/O-bound? | Chọn execution model phù hợp |
| Dữ liệu đủ lớn và công việc đủ nặng? | Đo nhiều input sizes |
| Có common pool contention? | Xem workload khác trong JVM |
| Có memory/GC pressure? | Đo allocation và GC |
| Có JMH warmup/forks? | Benchmark methodology đúng |
| Input setup có nằm trong timed region? | Tách hoặc benchmark riêng |
| Result có được consume? | Return value/Blackhole |
| Đã test concurrency production-like? | Load test theo số caller thực tế |
| Có so cùng JDK/CPU flags? | Ghi lại environment metadata |
| Chênh lệch có vượt measurement noise? | Xem error/variance |
| Cách nhanh hơn có dễ bảo trì? | Cân bằng performance và readability |

## 18. Chương trình Java 8 chạy độc lập: ba cách cho cùng kết quả

Chương trình **LoopVsStreamDemo.java** dưới đây dùng cùng một ArrayList<Integer>, cùng điều kiện lọc số chẵn và cùng phép tính score trong cả ba phương án.

1. Vòng lặp for-each.
2. Sequential Stream.
3. Parallel Stream.

Nó kiểm tra ba kết quả bằng nhau và in output deterministic. Chương trình **không đo thời gian**, nên không dùng kết quả này để tuyên bố cách nào nhanh hơn.

~~~java
import java.util.ArrayList;
import java.util.List;

public final class LoopVsStreamDemo {
    private static long score(int value) {
        long result = value;
        for (int i = 0; i < 24; i++) {
            result = (result * 1664525L + 1013904223L)
                    ^ (result >>> 13);
        }
        return result & 0xFFFFL;
    }

    private static long loopSum(List<Integer> values) {
        long sum = 0L;
        for (Integer value : values) {
            if ((value & 1) == 0) {
                sum += score(value);
            }
        }
        return sum;
    }

    private static long sequentialStreamSum(List<Integer> values) {
        return values.stream()
                .filter(value -> (value & 1) == 0)
                .mapToLong(LoopVsStreamDemo::score)
                .sum();
    }

    private static long parallelStreamSum(List<Integer> values) {
        return values.parallelStream()
                .filter(value -> (value & 1) == 0)
                .mapToLong(LoopVsStreamDemo::score)
                .sum();
    }

    public static void main(String[] args) {
        List<Integer> values = new ArrayList<Integer>(10000);
        for (int i = 0; i < 10000; i++) {
            values.add(i - 5000);
        }

        long loop = loopSum(values);
        long sequential = sequentialStreamSum(values);
        long parallel = parallelStreamSum(values);

        if (loop != sequential || loop != parallel) {
            throw new AssertionError("Results differ");
        }

        long evenCount = values.stream()
                .filter(value -> (value & 1) == 0)
                .count();

        System.out.println("input count = " + values.size());
        System.out.println("even count = " + evenCount);
        System.out.println("for-loop sum = " + loop);
        System.out.println("sequential stream sum = " + sequential);
        System.out.println("parallel stream sum = " + parallel);
        System.out.println("all results equal = true");
    }
}
~~~

Biên dịch với JDK mới có hỗ trợ target Java 8:

~~~bash
javac --release 8 LoopVsStreamDemo.java
java LoopVsStreamDemo
~~~

Trên JDK 8 trực tiếp:

~~~bash
javac LoopVsStreamDemo.java
java LoopVsStreamDemo
~~~

**Stdout đã được biên dịch và chạy xác minh:**

~~~text
input count = 10000
even count = 5000
for-loop sum = 162296697
sequential stream sum = 162296697
parallel stream sum = 162296697
all results equal = true
~~~

### 18.1. Vì sao ba kết quả bằng nhau?

- Cùng List 10.000 số.
- Điều kiện lọc là số chẵn trong cả ba cách.
- Hàm score giống nhau.
- Tổng dùng long.
- Reduction là phép cộng có thể kết hợp.
- Không có shared mutable accumulator trong parallel pipeline.

### 18.2. Vì sao chương trình không in thời gian?

Một lần chạy trên một máy không đại diện cho performance của workload thực. Để so sánh tốc độ, dùng JMH với nhiều input sizes, warmup, measurement, forks và cùng môi trường.

### 18.3. Nếu chuyển sang int[]?

Có thể đổi source sang primitive array và dùng Arrays.stream(values)/IntStream. Đây là một benchmark representation khác, nên so sánh riêng với List để nhìn rõ ảnh hưởng boxing và data layout.

## 19. Hỏi đáp tự kiểm tra

**Câu 1.** for loop, sequential Stream và parallel Stream khác nhau chính ở đâu?

**Đáp án:** Loop điều khiển trực tiếp traversal; sequential Stream dùng pipeline tuần tự; parallel Stream cho runtime phân tách và xử lý các phần dữ liệu đồng thời rồi combine.

**Câu 2.** Collection.stream() có tự chạy song song không?

**Đáp án:** Không. Nó tạo sequential Stream; muốn parallel cần parallelStream() hoặc parallel().

**Câu 3.** Parallel Stream có tạo một thread cho mỗi phần tử không?

**Đáp án:** Không. Runtime chia nguồn thành task/partition và phân phối trên worker threads.

**Câu 4.** Vì sao parallel stream có overhead?

**Đáp án:** Splitting, scheduling, coordination, buffering và combining partial results.

**Câu 5.** Workload nào thường đáng thử parallel?

**Đáp án:** CPU-bound, đủ lớn, phần tử độc lập, source split tốt và reduction kết hợp đúng.

**Câu 6.** Workload I/O-bound có nên chuyển thẳng sang parallelStream không?

**Đáp án:** Không mặc định. Blocking có thể chiếm worker/common pool; chọn executor/concurrency model dành cho I/O.

**Câu 7.** Spliterator có vai trò gì?

**Đáp án:** Cung cấp traversal và khả năng chia source thành các phần để parallel processing.

**Câu 8.** Vì sao source có size/splitting tốt quan trọng?

**Đáp án:** Runtime có thể tạo partition cân bằng với chi phí thấp hơn.

**Câu 9.** parallelStream().forEach(...) có giữ thứ tự List không?

**Đáp án:** Không đảm bảo encounter order. Dùng forEachOrdered nếu thứ tự bắt buộc.

**Câu 10.** Vì sao forEachOrdered có thể làm chậm parallel pipeline?

**Đáp án:** Nó phải phối hợp để thực hiện action theo encounter order.

**Câu 11.** unordered() có nên thêm vào mọi parallel stream?

**Đáp án:** Không. Chỉ dùng nếu bài toán không cần encounter order.

**Câu 12.** Vì sao reduce cần associative operation?

**Đáp án:** Runtime có thể nhóm các phần tử và kết hợp partial results theo nhiều cách; phép toán không associative có thể tạo kết quả khác.

**Câu 13.** Có nên cập nhật một long[] dùng chung trong parallel forEach?

**Đáp án:** Không. Có race/lost updates. Dùng primitive reduction hoặc Collector phù hợp.

**Câu 14.** Effectively stateless lambda có lợi gì?

**Đáp án:** Mỗi phần tử có thể được xử lý độc lập, tránh race và kết quả phụ thuộc scheduling.

**Câu 15.** Vì sao ArrayList<Integer> và int[] cho benchmark khác nhau?

**Đáp án:** List dùng Integer references/boxing; int[] dùng primitive contiguous data và IntStream có thể tránh boxing.

**Câu 16.** Parallel double sum có luôn bằng tuần tự ở từng bit không?

**Đáp án:** Không được bảo đảm vì floating-point rounding và thứ tự nhóm phép cộng có thể khác.

**Câu 17.** sorted() và distinct() có thể ảnh hưởng parallel performance ra sao?

**Đáp án:** Đây là stateful operations, có thể cần buffering hoặc phối hợp giữa các partition.

**Câu 18.** Vì sao không dùng peek cho side effect bắt buộc?

**Đáp án:** Intermediate operations lazy và implementation có thể elide stage nếu không ảnh hưởng kết quả terminal.

**Câu 19.** Common ForkJoinPool có phải pool riêng cho mỗi stream không?

**Đáp án:** Không. Trong OpenJDK, parallel stream thường sử dụng common pool dùng chung; đây là implementation detail cần xét khi vận hành.

**Câu 20.** JMH giải quyết vấn đề nào?

**Đáp án:** Cung cấp harness với warmup, measurement, forks và cơ chế benchmark JVM có kiểm soát hơn.

**Câu 21.** Vì sao cần return hoặc consume benchmark result?

**Đáp án:** Để computation có kết quả được quan sát và giảm nguy cơ JIT loại bỏ phần việc không cần thiết.

**Câu 22.** Có nên tạo input trong mỗi benchmark invocation không?

**Đáp án:** Chỉ khi mục tiêu đo bao gồm cả chi phí tạo input; nếu muốn đo traversal, chuẩn bị input trong setup ngoài timed region.

**Câu 23.** Một benchmark một thread có đại diện cho service 100 concurrent requests không?

**Đáp án:** Không. Cần benchmark/load test với concurrency và contention gần production.

**Câu 24.** Nếu parallel stream nhanh hơn trong benchmark nhỏ, có nên chuyển cả ứng dụng không?

**Đáp án:** Không. Xác định workload, bottleneck, common pool usage và latency/throughput toàn hệ thống trước.

## 20. Tổng kết

- **Vòng lặp, Stream tuần tự và Stream song song là ba cách biểu đạt/thi hành khác nhau cho cùng một bài toán.** Trước khi đo, phải đảm bảo cùng input, filter, transform, reduction và semantics.
- **Sequential Stream** phù hợp với pipeline declarative dễ đọc, không cần parallelism. **Vòng lặp** phù hợp với control flow phức tạp và local state rõ ràng.
- **Parallel Stream** có thể tăng tốc workload CPU-bound đủ lớn, độc lập và có source Spliterator chia tốt; nó phải trả thêm chi phí split, schedule và combine.
- Parallel execution không bảo đảm thứ tự gọi lambda, không tạo thread cho từng phần tử và không tự làm shared mutable state an toàn.
- Reduction phải có identity/combiner đúng và phép toán associative. Floating-point có thể khác ở các bit cuối khi nhóm phép cộng khác nhau.
- Data source, boxing, ordering, stateful operations, common pool contention, memory và GC đều có thể thay đổi kết quả benchmark.
- **JMH** là công cụ phù hợp cho microbenchmark JVM; cần warmup, measurement, forks, input đại diện và result được consume. Load test vẫn cần thiết để đánh giá ứng dụng nhiều request.
- Không có ngưỡng số phần tử hoặc phần trăm speedup chung cho mọi máy. Chọn cách thực thi bằng correctness tests, benchmark và profiling trên môi trường triển khai.
- Chương trình Java 8 demo đã biên dịch và chạy; cả ba phương án cho cùng tổng **162296697** trên 10.000 phần tử.

### Tài liệu tham khảo chính thức

- [Java SE 8 — Stream package summary](https://docs.oracle.com/javase/8/docs/api/java/util/stream/package-summary.html)
- [Java SE 8 — Stream API](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Stream.html)
- [Java SE 8 — BaseStream](https://docs.oracle.com/javase/8/docs/api/java/util/stream/BaseStream.html)
- [Java SE 8 — Spliterator](https://docs.oracle.com/javase/8/docs/api/java/util/Spliterator.html)
- [Java SE 8 — ForkJoinPool](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ForkJoinPool.html)
- [Java SE 26 — Stream package summary and parallelism contract](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html)
- [Java SE 26 — ForkJoinPool](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)
- [Dev.java — Parallelizing Streams](https://dev.java/learn/parallelizing-streams/)
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://openjdk.org/projects/code-tools/jmh)
- [OpenJDK JMH — README and recommended Maven workflow](https://github.com/openjdk/jmh)
