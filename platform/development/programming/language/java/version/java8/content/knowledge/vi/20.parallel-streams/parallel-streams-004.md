# Điều kiện dữ liệu đủ lớn, dễ chia và tác vụ đủ nặng cho Stream song song

## 1. Khi nào nên dùng Stream song song?

Trong Java, `parallelStream()` hoặc `stream.parallel()` đặt một Stream pipeline vào **chế độ xử lý song song**. Thay vì một luồng thực thi xử lý toàn bộ phần tử, thư viện có thể chia nguồn thành nhiều phần, xử lý trên nhiều worker và kết hợp các kết quả. Chế độ song song **không bảo đảm** mỗi phần tử chạy trên một thread riêng, sử dụng hết mọi lõi CPU, hoặc nhanh hơn pipeline tuần tự.

Ba điều kiện quan trọng nhất để cân nhắc sử dụng Stream song song là:

1. **Dữ liệu đủ lớn** để thời gian xử lý hữu ích bù được chi phí khởi tạo, phân chia, điều phối và ghép kết quả.
2. **Nguồn dữ liệu dễ chia** thành các phần tương đối cân bằng, có thể duyệt độc lập với chi phí chia nhỏ thấp.
3. **Tác vụ trên mỗi phần tử đủ nặng**, thường là phép tính CPU độc lập, để có đủ công việc thực sự chạy trên các worker.

Đây là **điều kiện cần xem xét**, không phải ba phép kiểm tra bảo đảm có tăng tốc. Kết quả còn phụ thuộc thuật toán, phép toán kết thúc, bộ nhớ, yêu cầu thứ tự, số lõi CPU sẵn có và tải đồng thời của ứng dụng.

Ví dụ: tính số nguyên tố trong khoảng lớn là công việc CPU có thể tách theo từng số; trái lại chỉ cộng vài trăm số bằng `sum()` rất nhanh ở chế độ tuần tự, nên overhead của song song dễ lớn hơn phần thời gian tiết kiệm.

### 1.1. Mô hình chi phí để suy nghĩ đúng

Hãy xem tổng thời gian theo các thành phần gần đúng:

```text
T_sequential ≈ T_duyet_nguon + T_xu_ly

T_parallel   ≈ T_chia_nguon + T_dieu_phoi
             + T_xu_ly_tren_cac_nhanh
             + T_gop_ket_qua + T_dong_bo/bo_nho
```

Một cách diễn giải bằng ký hiệu:

```text
T_sequential ≈ N × C
T_parallel   ≈ O + (N × C) / P_hieu_dung + M
```

Trong đó `N` là số phần tử, `C` là chi phí xử lý một phần tử, `O` là overhead chia và điều phối, `P_hieu_dung` là mức song song hiệu dụng (không nhất thiết bằng số CPU), còn `M` là chi phí hợp nhất, đồng bộ và truy cập bộ nhớ. Đây chỉ là **mô hình để nhận diện yếu tố ảnh hưởng**, không phải công thức dự đoán thời gian chính xác của Java Stream.

Nếu tăng `N` nhưng `C` gần bằng không, overhead có thể vẫn trội. Nếu `N` vừa phải nhưng `C` lớn và nguồn chia rất đều, song song vẫn có thể hữu ích. **Không tồn tại ngưỡng chung như “trên 1.000/10.000 phần tử thì dùng parallel”.** Ngưỡng phải đo với chính dữ liệu, chức năng và môi trường vận hành.

## 2. Điều kiện thứ nhất: dữ liệu đủ lớn

### 2.1. “Đủ lớn” là lớn so với overhead

Chế độ song song cần chi phí để phân hoạch, đưa việc đến worker, điều phối, đôi khi cấp vùng chứa tạm và hợp nhất. Với các phép xử lý đơn giản:

```java
long sum = java.util.stream.LongStream.rangeClosed(1, 10_000)
    .parallel()
    .sum();
```

Pipeline có thể hoàn toàn chính xác nhưng chưa chắc nhanh hơn:

```java
long sum = java.util.stream.LongStream.rangeClosed(1, 10_000)
    .sum();
```

Một phép cộng trên `long` rất rẻ; thậm chí nếu đầu vào lớn hơn nhiều, băng thông bộ nhớ, tối ưu loop và chi phí worker vẫn có thể khiến bản tuần tự cạnh tranh tốt. Ví dụ minh họa trên chỉ là snippet, không phải khẳng định benchmark cho mọi máy.

### 2.2. Xét số phần tử trên từng nhánh, không chỉ tổng kích thước

Một tập một triệu phần tử có thể phù hợp khi mỗi phần tử tốn đủ CPU và chia cân bằng. Nhưng nếu phải tạo quá nhiều nhánh rất nhỏ, thời gian lên lịch và ghép có thể vượt lợi ích. Ở chiều ngược lại, ít phần tử nhưng mỗi phần tử là một phép tính CPU lớn có thể vẫn mang lại công việc đáng kể.

Ưu tiên kiểm tra:

- **Khối lượng công việc thực tế**: số phần tử nhân với chi phí tính toán của từng phần tử.
- **Tính đồng đều**: nếu có vài phần tử rất nặng còn đa số rất nhẹ, những worker làm xong sớm có thể chờ nhánh nặng nhất.
- **Số lõi thực sự có sẵn**: máy bị giới hạn CPU container, máy đang tải nặng hoặc dịch vụ phục vụ nhiều request đồng thời có thể không còn công suất dư.
- **Tỷ lệ công việc trong toàn request**: tăng tốc một bước xử lý chiếm rất ít thời gian tổng thể sẽ khó cải thiện latency chung đáng kể.

Ví dụ tổng thời gian request là 200 ms, trong đó 180 ms là I/O và chỉ 20 ms tính toán. Dù tăng tốc phần tính toán lên hai lần, latency lý tưởng chỉ giảm 10 ms (còn 190 ms), chưa tính overhead; không thể kết luận chỉ bằng số phần tử.

### 2.3. Đánh giá bằng nhiều kích thước đầu vào

Đừng chỉ đo một tập dữ liệu. Hãy thử các kích thước đại diện cho tải thật: nhỏ, trung bình, lớn và dữ liệu lệch phân bố. Theo dõi **thời gian xử lý**, CPU, áp lực cấp phát/GC, bộ nhớ và độ biến thiên của các lần chạy; giới hạn bộ nhớ hoặc contention có thể đảo chiều kết quả.

## 3. Điều kiện thứ hai: nguồn dữ liệu dễ chia bằng `Spliterator`

### 3.1. `Spliterator.trySplit()` tạo ra những phần việc riêng

Java Stream dựa vào `Spliterator` của nguồn để duyệt và hỗ trợ phân chia. `trySplit()` có thể trả về một `Spliterator` khác phụ trách một phần phần tử chưa duyệt, hoặc trả `null` khi không thể/không muốn chia tiếp. Nguồn phù hợp thường có khả năng:

- Chia với **chi phí thấp**, không phải duyệt phần lớn dữ liệu chỉ để xác định điểm cắt.
- Chia thành các phần **tương đối cân bằng** (theo lượng công việc thực tế), giảm tình trạng một worker còn bận trong khi worker khác đã rảnh.
- Cho các nhánh duyệt phần tử **độc lập**, ít khóa hoặc tranh chấp.
- Ước lượng đúng hoặc gần đúng số phần tử còn lại để hỗ trợ quyết định chia tiếp.

Các đặc tính `Spliterator.SIZED` và `Spliterator.SUBSIZED` giúp mô tả kích thước:

- **`SIZED`:** ước lượng kích thước của spliterator là chính xác theo hợp đồng khi chưa có thay đổi nguồn không hợp lệ.
- **`SUBSIZED`:** các spliterator con thu được khi chia cũng có `SIZED` và `SUBSIZED`.

Hai đặc tính này giúp một số thuật toán phân hoạch hiệu quả hơn, nhưng **không tự bảo đảm tăng tốc**; tính cân bằng và chi phí `trySplit()` vẫn quan trọng. Nguồn thiếu `SUBSIZED` cũng **không đồng nghĩa không thể song song**.

### 3.2. So sánh một số nguồn phổ biến

| Nguồn | Xu hướng phân chia | Nhận xét |
| --- | --- | --- |
| `IntStream.range(...)`, `LongStream.range(...)` | Thường chia nhanh theo khoảng chỉ số | Rất phù hợp để thử nghiệm tác vụ số học độc lập. |
| Array và `ArrayList` | Có truy cập theo chỉ số, biết kích thước | Thường dễ cắt thành các khoảng gần cân bằng. |
| `LinkedList` | Không có truy cập ngẫu nhiên hiệu quả; cách split có thể tốn chi phí hơn | Vẫn có khả năng `trySplit()`, nhưng đừng giả định ngang hiệu năng với array. |
| `HashSet`/`HashMap` | Có cơ chế split nhưng đặc tính và phân bố khác nguồn theo chỉ số | Cần đo trên kích thước, phân bố hash và phép xử lý thực tế. |
| Nguồn tạo động, iterator hay I/O | Có thể không biết kích thước hoặc chia kém hiệu quả | Không mặc định phù hợp chỉ vì có API `parallel()`. |

Khác biệt phụ thuộc loại nguồn **và** triển khai JDK. Tránh biến bảng này thành quy tắc tuyệt đối. Với nguồn bên ngoài như tệp, database, API, bottleneck I/O, kết nối và backpressure thường cần cách thiết kế riêng.

### 3.3. Kiểm tra đặc tính khi cần chẩn đoán

```java
Spliterator.OfInt split = IntStream.rangeClosed(2, 100_000)
    .spliterator();

boolean sized = split.hasCharacteristics(Spliterator.SIZED);
boolean subsized = split.hasCharacteristics(Spliterator.SUBSIZED);
```

Đoạn code sử dụng `java.util.Spliterator` và `java.util.stream.IntStream`. Có thể xem các flag bằng API trên, nhưng phép đo tốc độ mới trả lời liệu nguồn đó có thực sự phù hợp với bài toán cụ thể hay không.

**Không duyệt lại cùng một spliterator sau khi đã dùng để tạo kết quả khác.** Nó là cơ chế tiêu thụ từng phần tử cho một phép tính, tương tự Stream chỉ có thể chạy một terminal operation.

## 4. Điều kiện thứ ba: tác vụ trên mỗi phần tử đủ nặng

### 4.1. Công việc CPU độc lập là ứng viên rõ ràng

Các bài toán thường hợp với song song gồm tính toán số học tương đối nặng, kiểm tra nguyên tố, tính score độc lập theo phần tử, mô phỏng CPU hoặc xử lý ảnh theo các phần không giao nhau (khi có kiểm soát truy cập vùng nhớ).

Ví dụ tính số nguyên tố bằng phép thử ước số:

```java
static boolean isPrime(int number) {
    if (number < 2) return false;
    if (number == 2) return true;
    if (number % 2 == 0) return false;

    for (int divisor = 3; divisor <= number / divisor; divisor += 2) {
        if (number % divisor == 0) return false;
    }
    return true;
}
```

Mỗi số có thể được kiểm tra độc lập. Đây là phép tính CPU; khi tập số đủ lớn, các worker có thể xử lý nhiều phần tử mà không cần cập nhật biến dùng chung. Mã hoàn chỉnh ở mục 7 minh họa cả chế độ tuần tự lẫn song song.

### 4.2. Tác vụ nhẹ không tự nhiên nhanh hơn khi song song

Ví dụ chỉ kiểm tra số dương, cộng thêm 1 hoặc ánh xạ một trường đã có sẵn có thể mất ít thời gian hơn chi phí tổ chức worker. Đặc biệt `map(x -> x + 1)` trên `Stream<Integer>` có thể phát sinh boxing/unboxing; khi chỉ xử lý số nguyên, ưu tiên `IntStream`, `LongStream`, `DoubleStream` để hạn chế tạo đối tượng không cần thiết.

### 4.3. Công việc chờ I/O không phải ứng viên mặc định

Gọi HTTP, JDBC hoặc đọc file blocking từ mỗi phần tử trong `parallelStream()` có thể làm nghẽn worker, gây tranh chấp pool kết nối và khó kiểm soát timeout/retry. Parallel Stream phù hợp nhất khi các hàm xử lý là **CPU-bound, stateless và không gây blocking kéo dài**. Nếu bottleneck là I/O, đánh giá mức đồng thời có giới hạn, pool kết nối và cơ chế bất đồng bộ/đồng thời phù hợp với ứng dụng; không dùng `parallel()` như cách tự động tăng tốc mọi tác vụ.

## 5. Điều kiện bổ sung: kết quả dễ gộp, ít tranh chấp, ít ràng buộc thứ tự

### 5.1. Phép gộp phải đúng và đủ rẻ

Các terminal operations như `sum()`, `count()`, `min()` hoặc các reduction bằng phép gộp có tính kết hợp thường thuận lợi vì mỗi nhánh tính kết quả tạm rồi ghép lại nhanh.

```java
long sum = LongStream.rangeClosed(1, 1_000_000)
    .parallel()
    .sum();
```

Bản thân phép gộp nhanh **không** có nghĩa ví dụ này tăng tốc; xử lý mỗi phần tử cũng rất nhẹ. Một phép gộp tốn thời gian cấp phát, hợp nhất hàng triệu mục trong `Map` hoặc yêu cầu khóa đồng bộ có thể xóa mất lợi ích xử lý nhiều nhánh.

Với `reduce(identity, accumulator)`, `identity` phải trung hòa và phép gộp phải kết hợp được. Với `Collector` tùy biến, supplier cần tạo vùng chứa độc lập, accumulator và combiner phải hợp đồng nhất quán; không cộng/ghi thêm một giá trị mặc định mỗi khi tạo nhánh. Chọn `Collectors.groupingByConcurrent` hoặc `toConcurrentMap` chỉ khi bài toán phù hợp cơ chế concurrent và không đòi hỏi bảo toàn thứ tự tương ứng; không xem chúng là bản thay thế mặc định cho mọi grouping.

### 5.2. Không dựa vào thứ tự hoàn thành các lambda

Stream có encounter order vẫn có thể xử lý các phần tử **không theo thứ tự thời gian** khi chạy song song. Những thao tác có ràng buộc encounter order như `forEachOrdered`, `findFirst`, `limit`, `skip` hoặc một số bước stateful như `sorted`/`distinct` có thể thêm chi phí đồng bộ/buffer và làm giảm lợi ích song song, tùy pipeline.

- `forEach()` trên stream song song **không bảo đảm thứ tự** tác dụng phụ.
- `forEachOrdered()` giữ thứ tự theo encounter order nhưng có thể giảm mức song song hữu ích.
- `findAny()` cho phép chọn bất kỳ phần tử phù hợp, khi ngữ nghĩa bài toán cho phép; `findFirst()` cần ưu tiên phần tử đầu theo encounter order.
- `unordered()` có thể giảm một số ràng buộc cho các phép toán cụ thể, **chỉ dùng khi kết quả không yêu cầu thứ tự**.
- `sorted()` hoặc `distinct()` vẫn có thể chạy song song nhưng có thể phát sinh chi phí trạng thái; không kết luận luôn chậm hoặc luôn nhanh.

Nếu phải thu kết quả theo đúng thứ tự, cần chọn terminal operation và collector có hợp đồng thứ tự tương ứng và **benchmark** cả đường đi đầy đủ.

### 5.3. Tránh trạng thái dùng chung và tranh chấp

**Sai:**

```java
List<Integer> result = new ArrayList<>();
numbers.parallelStream().forEach(result::add);
```

`ArrayList` không an toàn cho nhiều thread đồng thời thêm phần tử; có thể mất dữ liệu, làm hỏng cấu trúc hoặc cho kết quả khó dự đoán.

**Đúng khi cần thu danh sách:**

```java
List<Integer> result = numbers.parallelStream()
    .map(x -> x * 2)
    .collect(Collectors.toList());
```

Đây là các đoạn code minh họa, giả sử đã khai báo/import `numbers`, `List`, `ArrayList` và `Collectors`. Dạng `collect` để thư viện xử lý các vùng chứa tạm và ghép chúng theo hợp đồng collector. Không dựa vào kiểu `List` cụ thể hay khả năng sửa `Collectors.toList()` trả về.

Có thể dùng cơ chế đồng bộ/atomic để tránh data race, nhưng các cập nhật liên tục vào một biến chung tạo **contention** và làm mất khả năng tăng tốc. Đối với phép tính tổng, thường nên dùng `mapToLong(...).sum()` hoặc `reduce` thuần túy.

**Bất kể tuần tự hay song song**, lambda phải non-interfering (không sửa nguồn đang duyệt nếu nguồn không có hợp đồng concurrent) và phần lớn phải stateless; tránh cache mutable, tăng biến toàn cục, hoặc phụ thuộc số lần/thứ tự gọi `map`/`filter`.

## 6. Hạn chế hệ thống có thể đảo ngược lợi ích

Song song sử dụng tài nguyên xử lý chung. Một chương trình batch chạy độc lập và một dịch vụ xử lý hàng trăm request đồng thời có thể nhận kết quả hiệu năng khác nhau trên cùng thuật toán.

- **CPU thực sự sẵn có:** `Runtime.getRuntime().availableProcessors()` chỉ cho biết số processor mà JVM nhìn thấy; đó không phải cam kết về phần CPU rảnh hoặc mức speedup.
- **JVM và môi trường:** implementation phổ biến dùng cơ chế Fork/Join, thường liên quan common pool; đừng giả định số thread, lịch chia hoặc chính sách worker cụ thể là hợp đồng cố định của `Stream`.
- **Tải đồng thời:** nhiều request cùng gọi `parallelStream()` có thể tranh chấp CPU và tài nguyên worker. Đo throughput toàn dịch vụ, latency ở các percentile, không chỉ một request riêng lẻ.
- **Bộ nhớ/GC:** nhiều nhánh có thể tạo thêm object tạm và vùng chứa trung gian; nếu pipeline bị giới hạn băng thông bộ nhớ, tăng thread có thể không giúp.
- **Độ lệch công việc:** số lượng phần tử được chia bằng nhau chưa chắc lượng CPU từng nhánh bằng nhau; có thể cần thiết kế phân hoạch khác nếu phần tử có chi phí rất lệch.

Không nên dựa vào `parallel()` để giới hạn số request đồng thời hoặc thay thiết kế hàng đợi. Phạm vi bài này là **quyết định dùng Stream song song cho phép tính tổng hợp có thể phân chia**.

## 7. Ví dụ Java hoàn chỉnh: so sánh kết quả tuần tự và song song

Bài toán tính số nguyên tố trong các khoảng `[2, 1_000]` và `[2, 100_000]`, dùng thuật toán kiểm tra nguyên tố độc lập trên từng số. `IntStream.rangeClosed` có nguồn biết kích thước, dễ phân chia theo các đoạn số. Terminal operation `count()` gộp số đếm của các nhánh, không yêu cầu thứ tự.

Lưu vào **ParallelStreamCriteriaDemo.java**. Ví dụ sử dụng API đã có từ Java 8, biên dịch được bằng `javac --release 8` trên JDK hỗ trợ tùy chọn này và chạy được trên JDK 17+.

```java
import java.util.Spliterator;
import java.util.stream.IntStream;

public class ParallelStreamCriteriaDemo {
    static boolean isPrime(int number) {
        if (number < 2) {
            return false;
        }
        if (number == 2) {
            return true;
        }
        if (number % 2 == 0) {
            return false;
        }
        for (int divisor = 3; divisor <= number / divisor; divisor += 2) {
            if (number % divisor == 0) {
                return false;
            }
        }
        return true;
    }

    static long countPrimes(int upperBound, boolean parallel) {
        IntStream candidates = IntStream.rangeClosed(2, upperBound);
        if (parallel) {
            candidates = candidates.parallel();
        }
        return candidates
            .filter(ParallelStreamCriteriaDemo::isPrime)
            .count();
    }

    public static void main(String[] args) {
        int[] bounds = {1_000, 100_000};

        for (int n : bounds) {
            long sequentialCount = countPrimes(n, false);
            long parallelCount = countPrimes(n, true);
            System.out.println("N=" + n
                + ", sequential=" + sequentialCount
                + ", parallel=" + parallelCount
                + ", equal=" + (sequentialCount == parallelCount));
        }

        Spliterator.OfInt split =
            IntStream.rangeClosed(2, 100_000).spliterator();
        System.out.println("Range SIZED: "
            + split.hasCharacteristics(Spliterator.SIZED));
        System.out.println("Range SUBSIZED: "
            + split.hasCharacteristics(Spliterator.SUBSIZED));

        boolean parallelMode =
            IntStream.rangeClosed(2, 10).parallel().isParallel();
        System.out.println("Che do parallel: " + parallelMode);
    }
}
```

Biên dịch/chạy trong thư mục chứa file:

```bash
javac -encoding UTF-8 ParallelStreamCriteriaDemo.java
java ParallelStreamCriteriaDemo
```

**Stdout:**

```text
N=1000, sequential=168, parallel=168, equal=true
N=100000, sequential=9592, parallel=9592, equal=true
Range SIZED: true
Range SUBSIZED: true
Che do parallel: true
```

**Diễn giải:**

1. `countPrimes` tạo **stream mới mỗi lần gọi**. Một đối tượng Stream đã chạy terminal operation không được dùng lại.
2. `isPrime` chỉ nhận số và trả `boolean`, không cập nhật trạng thái dùng chung. Các số nguyên tố được kiểm tra độc lập; công việc là CPU, phù hợp để thử song song.
3. `IntStream.rangeClosed` chia theo khoảng số và tránh boxing của `Stream<Integer>`; hai đặc tính `SIZED`/`SUBSIZED` quan sát được từ spliterator của khoảng.
4. `count()` cho kết quả giống nhau trong cả hai chế độ vì phép đếm không phụ thuộc thứ tự hoàn thành các số.
5. `parallel().isParallel()` trả `true` vì chế độ pipeline được bật; điều đó **không chứng minh** chương trình đã chạy nhiều thread hoặc tăng tốc.
6. Hai số lượng `168` và `9_592` là kết quả số học xác định cho các khoảng trên. Chương trình **chưa đo thời gian**, vì một kết quả đúng không thể tự chứng minh lợi ích hiệu năng.

### 7.1. Cách đo thời gian nhanh để khám phá, chưa phải benchmark kết luận

Có thể đo một lần để quan sát sơ bộ, nhưng **không cố định giá trị thời gian trong stdout** vì nó phụ thuộc máy, tải hệ thống và trạng thái JIT/GC:

```java
long start = System.nanoTime();
long answer = countPrimes(100_000, true);
long elapsedNanos = System.nanoTime() - start;
System.out.println("Ket qua: " + answer);
System.out.println("Elapsed ns: " + elapsedNanos);
```

Đây là đoạn minh họa đặt **bên trong `main` của `ParallelStreamCriteriaDemo`**; không phải chương trình độc lập. Nếu so hai chế độ, cần chạy cả `false` và `true` với cùng input; làm nóng JVM (warm-up) trước, đo nhiều lần và kiểm tra kết quả giống nhau. Đừng kết luận chỉ từ một lần `System.nanoTime()` vì tối ưu JIT, garbage collection, turbo boost và scheduler làm số đo dao động. Với so sánh microbenchmark đáng tin cậy, dùng **JMH (Java Microbenchmark Harness)** và cấu hình warmup, measurement, forks/blackhole phù hợp.

Nếu quan tâm đến latency request sản xuất, còn phải đo khi nhiều request thực thi cùng lúc và khi hệ thống bị giới hạn CPU hoặc bộ nhớ. Một phép đo nhanh ở máy phát triển **không đủ** để quyết định cấu hình production.

## 8. Một số tình huống thực tế để lựa chọn

| Công việc | Dấu hiệu quan trọng | Hướng lựa chọn |
| --- | --- | --- |
| Cộng vài trăm/vài nghìn số nguyên | Mỗi phần tử quá nhẹ, `sum` rất rẻ | Bắt đầu bằng tuần tự; không bật song song chỉ vì có nhiều phần tử. |
| Kiểm tra nhiều số nguyên tố độc lập | CPU đáng kể; `range` dễ chia; `count` dễ gộp | Ứng viên hợp lý để benchmark song song. |
| Xử lý một `ArrayList` lớn bằng phép hash/đánh giá CPU thuần túy | Nguồn chia được, mỗi phần tử có chi phí tính đáng kể | Thử tuần tự và song song; đo CPU, GC và latency. |
| Duyệt `LinkedList` để lấy thuộc tính đơn giản | Chia kém thuận lợi hơn nguồn theo chỉ số; tác vụ nhẹ | Thường nên ưu tiên tuần tự hoặc xem lại cấu trúc dữ liệu; cần đo. |
| Truy vấn HTTP/JDBC cho mỗi phần tử | I/O blocking và giới hạn kết nối | Xem xét cơ chế concurrency/I/O có kiểm soát; không mặc định dùng parallel Stream. |
| `groupingBy` vào `Map` lớn | Hợp nhất các map tạm có thể tốn bộ nhớ/CPU | Đo cả thời gian combiner; cân nhắc thuật toán/collector đúng yêu cầu. |
| Xử lý có thứ tự bắt buộc, dùng `forEachOrdered` | Ràng buộc thứ tự có thể giảm lợi ích | Xác định chính xác chỗ cần thứ tự trước khi dùng song song. |
| Dịch vụ web đã bão hòa CPU | Các request tranh CPU với nhau | Đo throughput/latency toàn hệ thống; không thêm song song một cách máy móc. |

Bảng thể hiện **giả thuyết kỹ thuật để kiểm chứng**, không phải phán quyết hiệu năng cho mọi JDK và phần cứng.

## 9. Checklist quyết định và cách đọc kết quả đo

Trước khi đổi `stream()` thành `parallelStream()`, hãy trả lời tuần tự:

1. **Đúng kết quả chưa?** Phép tính trên từng phần tử độc lập, lambda stateless/non-interfering, giảm/gộp có tính kết hợp và phần tử trung hòa hợp lệ? Kết quả tuần tự/song song có tương đương theo yêu cầu nghiệp vụ?
2. **Dữ liệu đủ lớn chưa?** Số phần tử và độ nặng xử lý có đủ bù overhead? Dữ liệu có bị lệch khiến chỉ một vài nhánh rất nặng không?
3. **Chia có tốt không?** `Spliterator` có thể `trySplit()` nhanh, thành những đoạn tương đối cân bằng? Nguồn có dễ duyệt độc lập và không bị khóa/IO hạn chế?
4. **Tác vụ có đủ nặng và chủ yếu CPU không?** Có tránh blocking, contention, shared mutable state và boxing/cấp phát thừa?
5. **Gộp có rẻ không?** `reduce`/`collect` có khả năng song song đúng hợp đồng? Có một bước `sorted`, `distinct` hoặc ràng buộc thứ tự làm tăng đồng bộ/buffer?
6. **Môi trường có tài nguyên không?** Có đủ CPU thực sự sẵn dùng, bộ nhớ và mức tải đồng thời phù hợp?
7. **Có phép đo công bằng không?** Đã warm-up, lặp nhiều lần, chạy nhiều kích thước, so theo latency/throughput/GC trong môi trường gần thực tế và kiểm tra đáp án?
8. **Có lợi ích đáng giữ không?** Thời gian giảm đủ lớn và nhất quán để bù độ phức tạp, rủi ro contention và chi phí tài nguyên?

Tính tỷ lệ `speedup = T_sequential / T_parallel` từ các phép đo đáng tin. Ví dụ **giả định** `T_sequential=120 ms` và `T_parallel=60 ms` thì speedup là `2×`; nếu `T_parallel=150 ms` thì speedup là `0,8×` (chậm hơn). Đừng gọi một chênh lệch rất nhỏ là cải thiện thực sự nếu nó nằm trong độ nhiễu đo hoặc làm tăng mạnh tiêu thụ CPU toàn hệ thống.

Không đồng nhất **throughput** với **latency**: một request riêng lẻ có thể hoàn thành nhanh hơn khi dùng nhiều CPU, nhưng toàn hệ thống lại xử lý ít request mỗi giây hơn vì tranh tài nguyên.

## 10. Lỗi thường gặp và câu hỏi tự luyện

**Các lỗi dễ gặp:**

- Dùng ngưỡng số phần tử tùy ý như “hơn 10.000 là parallel” mà không xét chi phí xử lý, loại nguồn và máy.
- Cho rằng `parallel().isParallel()` xác nhận sử dụng nhiều lõi; thực tế chỉ xác nhận chế độ.
- Dùng stream song song rồi cập nhật `ArrayList` hoặc biến đếm dùng chung trong `forEach`.
- Dùng `reduce`/`Collector` có combiner sai hoặc phần tử trung hòa sai khiến kết quả tùy cách phân hoạch.
- Bỏ qua chi phí `groupingBy`, `sorted`, `distinct` hoặc `forEachOrdered` trong pipeline.
- Đo đúng một lần chưa warm-up, không kiểm tra đáp án hoặc so sánh dưới tải không tương đương.
- Tin rằng nguồn `SIZED/SUBSIZED` luôn mang lại tăng tốc, hoặc nguồn thiếu chúng không thể chạy song song.
- Bật parallel tại từng điểm trong một dịch vụ có nhiều request cùng tranh CPU mà không đo tác động toàn ứng dụng.

**Tự luyện:**

1. **Có 100 phần tử, mỗi phần tử tốn 20 ms CPU độc lập. Có chắc nên dùng parallel không?** Không. Có thể là ứng viên nếu nhiều CPU rảnh, chia tốt và combiner rẻ, nhưng phải đo. Độ lệch công việc và contention vẫn ảnh hưởng.
2. **Có mười triệu phần tử, mỗi phần tử chỉ cộng 1. Có chắc parallel nhanh hơn?** Không. Overhead điều phối, memory bandwidth và tối ưu tuần tự có thể lấn át.
3. **Vì sao `IntStream.range` thường dễ chia hơn một iterator tự xây không biết kích thước?** Vì nguồn biết chỉ số/giới hạn và có thể chia các khoảng nhanh thành các đoạn có kích thước dự đoán được.
4. **`forEachOrdered` có bảo toàn thứ tự không?** Có theo encounter order của nguồn khi có định nghĩa; chi phí thứ tự có thể làm giảm lợi ích song song.
5. **Hai phiên bản cho kết quả giống hệt thì có thể khẳng định parallel tốt hơn?** Không. Tính đúng đắn và hiệu năng là hai phép kiểm tra riêng, đều cần thiết.

## 11. Tài liệu API và đo hiệu năng

Các API dưới đây đã có từ Java 8 và vẫn được duy trì; liên kết dùng tài liệu JDK hiện đại để nắm đúng hợp đồng:

- [Java Stream package — Parallelism, non-interference, ordering](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html).
- [`Stream` — các thao tác trung gian, kết thúc và reduction](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html).
- [`Spliterator` — `trySplit`, `SIZED`, `SUBSIZED`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterator.html).
- [JMH — Java Microbenchmark Harness (OpenJDK)](https://openjdk.org/projects/code-tools/jmh/) cho việc đo microbenchmark với warmup/forks.
