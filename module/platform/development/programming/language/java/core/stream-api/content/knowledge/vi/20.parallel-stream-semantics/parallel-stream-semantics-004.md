# Ảnh hưởng của kích thước nguồn, chi phí phần tử và cách chia

**Parallel Stream** cho phép Java xử lý nhiều phần tử của pipeline trên nhiều tác vụ cùng lúc. Nhưng `parallel()` không phải nút “tăng tốc” cho mọi bài toán. Một pipeline có thể chạy **chậm hơn** khi song song nếu dữ liệu quá ít, xử lý mỗi phần tử quá rẻ, nguồn khó phân chia hoặc kết quả cần nhiều bước phối hợp để bảo đảm thứ tự.

Trong module **JAVA_STREAM_API**, ta học xử lý dữ liệu theo lối khai báo bằng pipeline lazy với `filter`, `map`, `reduce` và `collect`; đồng thời cần hiểu giới hạn về trạng thái, tài nguyên và hiệu năng. Bài này thuộc chương **Ngữ nghĩa xử lý song song**, tập trung vào ba biến số quan trọng nhất khi cân nhắc parallel Stream:

1. **Kích thước nguồn:** có bao nhiêu phần tử hoặc khối công việc?
2. **Chi phí xử lý từng phần tử:** mỗi phần tử làm bao nhiêu việc, và chi phí có đồng đều không?
3. **Khả năng chia nguồn:** `Spliterator` có thể tạo các phần việc độc lập, cân bằng và ít tốn chi phí không?

Ngoài ba biến số này, ta sẽ xét ảnh hưởng của `ORDERED`, phép toán trung gian có trạng thái, combiner, contention và cách đo hiệu năng đúng. Các nguyên tắc cũng hữu ích khi dùng collector tùy chỉnh, `Spliterator` và những phép biến đổi nâng cao như Stream Gatherers.

## 1. Parallel Stream làm gì?

Một nguồn tuần tự:

~~~java
long total = java.util.stream.IntStream.range(0, 10_000)
    .mapToLong(n -> n * 2L)
    .sum();
~~~

Có thể được yêu cầu xử lý song song:

~~~java
long total = java.util.stream.IntStream.range(0, 10_000)
    .parallel()
    .mapToLong(n -> n * 2L)
    .sum();
~~~

Cả hai đều phải trả kết quả đúng: tổng của các số `2 * n` với `n` từ 0 đến 9.999. Thay `parallel()` bằng `sequential()` lại cho biết pipeline cần thực thi tuần tự.

**`parallel()` chỉ chỉ định chế độ thực thi của pipeline.** Nó không có nghĩa:

- Mỗi phần tử được cấp một thread riêng.
- Mọi phần tử luôn chạy đồng thời.
- Số thread luôn bằng số lõi CPU.
- Các callback chạy theo một thứ tự cụ thể.
- Bài toán chắc chắn kết thúc sớm hơn.

Thông thường, triển khai Stream trên JDK sử dụng cơ chế fork/join để chia và xử lý công việc. Số tác vụ, cách phân chia và lịch thực thi là chi tiết triển khai, nên không nên viết logic nghiệp vụ phụ thuộc vào các chi tiết đó.

### Sơ đồ tổng quát

~~~mermaid
flowchart TD
    A["Nguồn N phần tử"] --> B["Spliterator / chia việc"]
    B --> C1["Phần 1"]
    B --> C2["Phần 2"]
    B --> C3["Phần ..."]
    B --> C4["Phần k"]
    C1 --> D["Xử lý filter/map"]
    C2 --> D
    C3 --> D
    C4 --> D
    D --> E["Gộp reduce/collect"]
    E --> F["Kết quả cuối"]
~~~

Sơ đồ mô tả **khả năng** phân chia, không phải cam kết luôn có đúng bốn tác vụ. Một số nguồn rất khó chia; một số terminal operation buộc các nhánh phải đồng bộ hoặc giữ thứ tự.

## 2. Mô hình chi phí: tổng công việc và phần việc không song song hóa được

Thời gian chạy song song có thể được hình dung gần đúng:

~~~text
T_parallel ≈ T_sequential_part
           + T_parallelizable / effective_workers
           + T_split
           + T_schedule
           + T_merge
           + T_contention
           + T_allocation
~~~

Trong đó:

- `T_sequential_part` là phần bắt buộc chạy tuần tự hoặc phải chờ bước khác.
- `T_parallelizable` là thời gian của công việc có thể chia độc lập.
- `effective_workers` là mức song song thực sự tận dụng được, **không mặc định bằng số lõi**.
- `T_split` là chi phí chia nguồn thành các phần.
- `T_schedule` là chi phí điều phối và lấy công việc.
- `T_merge` là chi phí kết hợp kết quả.
- `T_contention` là chi phí tranh chấp CPU, bộ nhớ, khóa và tài nguyên khác.
- `T_allocation` là chi phí tạo các bộ chứa hoặc đối tượng trung gian.

Đây là **mô hình suy luận**, không phải công thức đo chính xác của một JVM. Nó cho thấy để parallel có lợi, **phần thời gian tiết kiệm được nhờ chia việc phải lớn hơn các chi phí bổ sung**.

### Định luật Amdahl

Nếu một chương trình có tỷ lệ `s` công việc không thể song song hóa, tốc độ tăng lý thuyết khi dùng `p` worker là:

\[
S(p) \leq \frac{1}{s + \frac{1-s}{p}}
\]

Ví dụ: nếu `s = 0{,}2` (20% công việc phải chạy tuần tự), dù có vô số worker thì tốc độ tăng tối đa theo mô hình này cũng chỉ tiến tới **5 lần**. Với 8 worker, giới hạn lý thuyết là:

\[
S(8) \leq \frac{1}{0.2 + 0.8/8} \approx 3.33
\]

Tốc độ thực tế còn thấp hơn vì chi phí chia, lập lịch, gộp, bộ nhớ và tranh chấp. Vì vậy, không thể lấy số lõi nhân với tốc độ chạy tuần tự rồi xem là kết quả chắc chắn.

## 3. Kích thước nguồn: số phần tử ít thường khó bù overhead

Xét hai pipeline cùng tính tổng:

~~~java
long small = java.util.stream.IntStream.range(0, 20)
    .parallel()
    .asLongStream()
    .sum();

long large = java.util.stream.IntStream.range(0, 2_000_000)
    .parallel()
    .asLongStream()
    .sum();
~~~

Nguồn 20 phần tử có rất ít công việc nếu phép toán là cộng số. Chi phí chia việc và kết hợp có thể cao hơn thời gian tính tổng tuần tự. Nguồn hai triệu phần tử có nhiều công việc hơn, nhưng **nhiều phần tử tự nó chưa bảo đảm parallel nhanh hơn**, vì cộng số vẫn là thao tác rất nhẹ và dữ liệu có thể bị giới hạn bởi băng thông bộ nhớ.

| Kích thước nguồn | Chi phí mỗi phần tử | Kỳ vọng cần kiểm chứng |
|---|---|---|
| Rất nhỏ | Rất nhẹ | Parallel thường khó có lợi |
| Rất nhỏ | Nặng | Có thể có lợi nếu đủ phần việc độc lập |
| Rất lớn | Rất nhẹ | Có thể bị overhead hoặc giới hạn bộ nhớ chi phối |
| Rất lớn | Nặng, độc lập | Là ứng viên hợp lý để thử parallel |
| Lớn nhưng nguồn khó chia | Bất kỳ | Khó tận dụng nhiều worker |
| Lớn, phải giữ thứ tự và gộp phức tạp | Bất kỳ | Chi phí phối hợp có thể cao |

Ngưỡng “nhỏ” và “lớn” không có một con số dùng chung cho mọi dự án. Nó thay đổi theo CPU, phiên bản JDK, cấu trúc dữ liệu, thuật toán và tải của máy chủ.

### 3.1. Nhiều phần tử không đồng nghĩa với nhiều phép tính

`IntStream.range(0, 1_000_000).count()` có thể được tối ưu bằng thông tin kích thước của nguồn. Đây không nhất thiết là một triệu lần gọi callback.

~~~java
long count = java.util.stream.IntStream.range(0, 1_000_000)
    .parallel()
    .count();

System.out.println(count); // 1000000
~~~

Nếu chỉ cần đếm nguồn có `SIZED`, `count()` có thể tránh traversal. Trong trường hợp này, tăng số phần tử không tương đương tăng số lượng công việc của pipeline. **Không dùng `peek` hoặc side effect trong `map` để giả định số lần callback bằng số phần tử.**

## 4. Chi phí phần tử: tính toán đủ nặng mới tạo cơ hội tăng tốc

Hai thao tác sau khác nhau rất lớn về lượng công việc:

~~~java
// Nhẹ: cộng một số.
.map(n -> n + 1)

// Nặng hơn: nhiều vòng biến đổi độc lập trên một giá trị.
.mapToLong(n -> expensiveCalculation(n))
~~~

Nếu mỗi phần tử chỉ có một hoặc hai phép toán số học, JVM có thể xử lý tuần tự rất nhanh. Khi đó, chi phí điều phối có thể chiếm tỷ lệ lớn. Nếu mỗi phần tử tốn nhiều phép tính CPU và không cần dùng trạng thái chung, việc chia cho nhiều worker có cơ hội bù overhead.

Tuy nhiên, **chi phí cao chưa đủ**: các phần tử còn phải xử lý được tương đối độc lập, nguồn chia được và phép tổng hợp kết quả không trở thành nút thắt.

### 4.1. Ví dụ minh họa hai loại công việc

~~~java
import java.util.stream.IntStream;

public class CostPerElement {
    static long simple(int n) {
        return n + 1L;
    }

    static long cpuWork(int value) {
        long x = value + 0x9E3779B97F4A7C15L;
        for (int i = 0; i < 100; i++) {
            x ^= x >>> 13;
            x *= 0xBF58476D1CE4E5B9L;
            x ^= x >>> 17;
        }
        // Giới hạn kết quả mỗi phần tử để tổng không tràn trong ví dụ.
        return x & 1023L;
    }

    public static void main(String[] args) {
        int size = 100_000;

        long cheap = IntStream.range(0, size)
            .mapToLong(CostPerElement::simple)
            .sum();

        long expensive = IntStream.range(0, size)
            .parallel()
            .mapToLong(CostPerElement::cpuWork)
            .sum();

        System.out.println(cheap > 0);      // true
        System.out.println(expensive >= 0);  // true
    }
}
~~~

Đây là chương trình giải thích **sự khác nhau về lượng công việc**, không phải benchmark so sánh tốc độ hai pipeline: một bên dùng phép tính khác hẳn bên còn lại. Muốn đánh giá parallel, phải so sánh **cùng một thuật toán và cùng đầu vào** ở hai chế độ; mục 12 cung cấp mẫu đo phù hợp hơn.

## 5. Chi phí không đồng đều: cân bằng tải quan trọng hơn đếm phần tử

Hai phần dữ liệu có số phần tử bằng nhau **không nhất thiết có tổng chi phí bằng nhau**.

Giả sử một tác vụ xử lý bản ghi `Order`:

- Đơn thường mất khoảng 1 đơn vị công việc.
- Đơn có nhiều dòng chi tiết mất khoảng 100 đơn vị công việc.
- Một nửa dữ liệu đầu chứa toàn đơn nặng, nửa sau toàn đơn nhẹ.

Nếu chia nguồn thành hai nửa theo vị trí, một worker có thể phải làm phần lớn công việc trong khi worker còn lại kết thúc sớm. Đây là **load imbalance**.

~~~text
Chia theo số phần tử:
  Nhánh A: 100 phần tử nặng  -> rất lâu
  Nhánh B: 100 phần tử nhẹ  -> xong sớm

Thời gian hoàn thành bị chi phối bởi nhánh chậm nhất.
~~~

Cơ chế fork/join có thể tiếp tục chia và cân bằng lại công việc trong những điều kiện phù hợp, nhưng **không bảo đảm tải tự cân bằng hoàn hảo**. Việc chọn kích thước tác vụ (*granularity*) và cách chia nguồn ảnh hưởng rất lớn đến thời gian chạy.

### 5.1. Nguyên tắc xử lý chi phí không đồng đều

1. Nếu có thể chia thành **nhiều phần đủ lớn**, hệ thống có cơ hội phân phối lại việc.
2. Nếu mỗi phần quá lớn và không chia được, dễ có worker rảnh khi nhánh khác còn bận.
3. Nếu mỗi phần quá nhỏ, overhead tạo và quản lý tác vụ tăng.
4. Nếu phần tử rất nặng do I/O hoặc khóa, thêm thread có thể không giúp và còn làm nghẽn tài nguyên.

Cần đo cả **độ lệch thời gian giữa các nhánh**, không chỉ số phần tử. Đối với workload biến thiên mạnh, thuật toán phân vùng theo chi phí ước lượng hoặc một cơ chế điều phối phù hợp có thể hiệu quả hơn việc chia đôi theo chỉ số.

## 6. Spliterator quyết định nguồn chia dễ đến đâu

Parallel Stream dựa nhiều vào `Spliterator` của nguồn. Những phương thức quan trọng:

~~~java
boolean tryAdvance(Consumer<? super T> action);
Spliterator<T> trySplit();
long estimateSize();
int characteristics();
~~~

- **`tryAdvance`** duyệt một phần tử nếu còn.
- **`trySplit`** cố gắng tách một phần dữ liệu chưa duyệt thành Spliterator mới.
- **`estimateSize`** ước lượng số phần tử còn lại.
- **`characteristics`** mô tả đặc tính của nguồn để hệ thống có cơ sở tối ưu.

### 6.1. Một lần chia hợp lệ

~~~text
Nguồn có thứ tự [0, 8):

Trước:
  original = [0, 1, 2, 3, 4, 5, 6, 7]

Sau original.trySplit():
  returned = [0, 1, 2, 3]    (tiền tố)
  original = [4, 5, 6, 7]    (hậu tố)

estimateSize(returned) = 4
estimateSize(original) = 4
~~~

Với Spliterator có `ORDERED`, Spliterator được trả về từ `trySplit` phải chứa **một tiền tố** của phần chưa duyệt. Không được phát lại cùng phần tử ở hai nhánh hoặc bỏ sót phần tử. Sự đúng đắn này độc lập với việc chạy song song có nhanh hơn hay không.

**Không bắt buộc tách đúng một nửa.** `trySplit()` có thể tách theo lô, trả những tỷ lệ khác hoặc trả `null` nếu không tách được.

### 6.2. Thử quan sát một nguồn Java chuẩn

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

public class SplitObservation {
    public static void main(String[] args) {
        List<Integer> values = new ArrayList<>();
        for (int i = 0; i < 16; i++) {
            values.add(i);
        }

        Spliterator<Integer> rest = values.spliterator();
        System.out.println(rest.estimateSize()); // 16

        Spliterator<Integer> prefix = rest.trySplit();

        if (prefix != null) {
            long leftSize = prefix.estimateSize();
            long rightSize = rest.estimateSize();

            System.out.println(leftSize + rightSize); // 16

            // Chỉ kiểm tra đặc tính, không phụ thuộc số phần tử mỗi nửa.
            System.out.println(
                rest.hasCharacteristics(Spliterator.ORDERED)
            ); // true với ArrayList
        }
    }
}
~~~

Một số triển khai có thể chia 8–8 ở ví dụ này, nhưng **hợp đồng `Spliterator` không bắt buộc mọi nguồn hoặc mọi lần gọi đều chia như thế**. Điều quan trọng là khả năng tiếp tục chia, độ cân bằng và việc các nhánh không trùng nhau.

## 7. SIZED, SUBSIZED và thông tin kích thước hỗ trợ chia việc

Hai đặc tính liên quan trực tiếp đến kích thước:

- **`SIZED`:** số phần tử còn lại được biết chính xác theo hợp đồng nguồn.
- **`SUBSIZED`:** Spliterator và những Spliterator tạo ra bởi `trySplit` đều tiếp tục bảo đảm `SIZED` và `SUBSIZED`.

`SUBSIZED` là lời hứa mạnh hơn `SIZED`. Không phải nguồn nào biết kích thước ban đầu cũng có thể biết chính xác kích thước của mọi nhánh con.

| Đặc tính | Tác động đến suy luận hiệu năng |
|---|---|
| `SIZED` | Có thể giúp ước lượng lượng dữ liệu đầu vào và tối ưu một số terminal operation |
| `SUBSIZED` | Tạo điều kiện thuận lợi để phân vùng có kích thước xác định |
| `ORDERED` | Giúp xác định encounter order, nhưng có thể làm `limit`/`distinct` cần thêm phối hợp |
| `SORTED` | Cho phép framework biết dữ liệu có thứ tự, nếu khai báo và comparator đúng |
| `CONCURRENT` | Nguồn hỗ trợ một số hình thức thay đổi đồng thời theo hợp đồng riêng |
| `IMMUTABLE` | Nguồn có cam kết cấu trúc không bị biến đổi theo kiểu gây cản trở traversal |
| `DISTINCT` | Các phần tử khác nhau theo `equals`; có thể giúp tối ưu phép loại trùng |

Đừng khai báo đặc tính sai chỉ để tăng tốc. Ví dụ khai báo `SIZED` khi `estimateSize()` không chính xác có thể làm `count()` trả kết quả sai hoặc gây lỗi khi Stream cố phân bổ bộ nhớ. Hiệu năng không thể đánh đổi bằng việc làm sai hợp đồng nguồn.

### 7.1. Chi phí ước lượng kích thước

`estimateSize()` trả về `long`, và có thể trả `Long.MAX_VALUE` khi số lượng phần tử chưa biết hoặc không giới hạn. **Đó không phải yêu cầu cấp phát bộ nhớ cho bấy nhiêu phần tử.**

Với nguồn dạng khoảng `[start, end)`, việc tính `end - start` thường rẻ và chính xác nếu xử lý tràn số đúng. Với dữ liệu đến từ I/O hoặc bộ sinh phụ thuộc trạng thái, đếm chính xác trước khi duyệt có thể rất đắt hoặc bất khả thi.

## 8. So sánh nguồn dễ chia và nguồn khó chia

Một nguồn tốt cho song song không chỉ có nhiều phần tử mà còn cần chia được với chi phí phù hợp.

| Nguồn | Đặc điểm chia nguồn | Lưu ý |
|---|---|---|
| Mảng `int[]`, `long[]`, `double[]` | Có vị trí truy cập trực tiếp; thường chia theo khoảng chỉ số hiệu quả | Đừng sửa mảng khi pipeline đang duyệt |
| `ArrayList` | Truy cập theo chỉ số; Spliterator có khả năng phân vùng thuận lợi | Các phép toán vẫn có thể bị giới hạn bởi băng thông bộ nhớ |
| `IntStream.range(...)` | Biết ranh giới và kích thước; dễ tách thành các khoảng | Chỉ chia tốt chưa bảo đảm terminal operation nhanh |
| `HashSet` | Có Spliterator và khả năng chia, nhưng thứ tự không được bảo đảm | Đặc tính khác List; kết quả phụ thuộc yêu cầu thứ tự |
| `LinkedList` | Duyệt theo liên kết; việc chia thường phức tạp hơn và có thể theo lô | Không kết luận là không thể chia; cần đo |
| `Iterator` một chiều | Khó nhảy trực tiếp đến giữa; có thể gom batch trước khi chia | Chi phí chia/buffering ảnh hưởng lợi ích |
| Nguồn I/O / mạng | Có thể bị chờ dữ liệu hoặc giới hạn tài nguyên bên ngoài | Parallel Stream không tự biến I/O chặn thành nonblocking |
| `Stream.iterate(seed, next)` | Phần tử kế tiếp phụ thuộc phần tử trước; khó chia hiệu quả ở một số trường hợp | Cần xét giới hạn dừng và chi phí truy hồi |
| `Stream.generate(supplier)` | Giá trị từ supplier, có thể liên quan trạng thái/không có encounter order | Supplier phải tuân thủ hợp đồng khi dùng song song |

Bảng mô tả xu hướng thiết kế; khả năng thực tế còn tùy triển khai Spliterator và phiên bản JDK.

### 8.1. Cùng thuật toán, khác nguồn có thể khác hiệu năng

~~~java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

List<Integer> arrayList = new ArrayList<>();
List<Integer> linkedList = new LinkedList<>();

for (int i = 0; i < 100_000; i++) {
    arrayList.add(i);
    linkedList.add(i);
}

long fromArrayList = arrayList.parallelStream()
    .mapToLong(Integer::longValue)
    .sum();

long fromLinkedList = linkedList.parallelStream()
    .mapToLong(Integer::longValue)
    .sum();

System.out.println(fromArrayList == fromLinkedList); // true
~~~

Kết quả đúng phải giống nhau. Nhưng hai nguồn có cấu trúc, chi phí duyệt và chiến lược phân vùng khác nhau, nên thời gian có thể khác. Mục tiêu của ví dụ là **thấy nguồn dữ liệu quan trọng**, không phải khẳng định một nguồn luôn nhanh hơn trong mọi trường hợp.

## 9. Kích thước các phần việc: granularity và ngưỡng chia

Giả sử có `N` phần tử và mỗi tác vụ được giao khoảng `B` phần tử. Một cách suy luận đơn giản là số tác vụ vào khoảng `N / B`.

- `B` **quá lớn**: ít tác vụ, dễ mất cân bằng khi mỗi phần tử có chi phí khác nhau.
- `B` **quá nhỏ**: có nhiều tác vụ nhưng chi phí tạo, lập lịch, hợp nhất và đồng bộ tăng.
- `B` **phù hợp**: đủ nhiều công việc để sử dụng các worker, nhưng không quá nhiều để overhead chi phối.

~~~text
Tác vụ quá thô:
  [████████████████] [████]
  Worker 1 bận lâu, Worker 2 chờ.

Tác vụ quá nhỏ:
  [█][█][█][█][█][█][█][█][█]...
  Có thể tốn nhiều chi phí quản lý.

Tác vụ vừa đủ:
  [████][████][████][████]
  Có thể phân phối linh hoạt hơn.
~~~

Không có một ngưỡng chia cố định áp dụng cho mọi tập dữ liệu. Hãy cân nhắc tốc độ xử lý một phần tử, mức độ đồng đều, số worker thực sự có thể sử dụng, chi phí combiner và tài nguyên máy chủ.

### 9.1. Một Spliterator tùy chỉnh không nên chia vô hạn thành tác vụ bé

Ví dụ logic của `trySplit` cho một Spliterator quản lý đoạn `[current, fence)`:

~~~java
@Override
public Spliterator.OfInt trySplit() {
    long remaining = (long) fence - current;

    // Ví dụ: không tách tiếp khi còn dưới 2.048 phần tử.
    if (remaining < 2_048L) {
        return null;
    }

    int middle = (int) ((long) current + remaining / 2);

    Spliterator.OfInt prefix =
        new RangeSpliterator(current, middle);

    current = middle;
    return prefix;
}
~~~

Đây là **đoạn minh họa để thay phương thức `trySplit`** của một lớp `RangeSpliterator` quản lý khoảng số, không phải chương trình độc lập. Lớp đó phải triển khai `tryAdvance`, `estimateSize`, `characteristics` và lưu `current`/`fence` đúng hợp đồng. Ngưỡng 2.048 chỉ là ví dụ để thấy ý tưởng “không chia các đoạn quá nhỏ”; không có ý nghĩa tối ưu phổ quát.

Khi `ORDERED`, phần trả về là tiền tố; sau split, đối tượng gốc chỉ giữ hậu tố. Việc tính bằng `long` tránh tràn `int` với khoảng lớn. Một chiến lược chia khác có thể dùng batching, chia không đều hoặc không tách nếu nguồn không cho phép.

## 10. ORDERED và các thao tác stateful có thể làm parallel tốn kém

Một nguồn `ORDERED` có **encounter order**, chẳng hạn thứ tự phần tử của `List` hoặc dãy `IntStream.range`. Đối với nhiều bài toán, thứ tự rất quan trọng; nhưng giữ thứ tự khi xử lý song song có thể đòi hỏi phối hợp nhiều nhánh.

### 10.1. forEach và forEachOrdered

~~~java
import java.util.stream.IntStream;

IntStream.range(1, 6)
    .parallel()
    .forEach(System.out::print);
// Có thể in các chữ số theo thứ tự không xác định.

System.out.println();

IntStream.range(1, 6)
    .parallel()
    .forEachOrdered(System.out::print);
// In 12345.
~~~

`forEach` trong Stream song song **không cam kết** thứ tự thực thi action. `forEachOrdered` giữ thứ tự gặp của nguồn, nhưng việc duy trì thứ tự đó có thể làm giảm lợi ích song song, nhất là khi bản thân action chứa I/O hoặc đồng bộ.

**Không dùng output console làm benchmark**, vì ghi console có thể rất chậm và bản thân I/O chia sẻ làm sai lệch quan sát hiệu năng.

### 10.2. distinct, sorted, limit

~~~java
List<Integer> firstThreeDistinct = List.of(3, 3, 2, 2, 1, 1)
    .parallelStream()
    .distinct()
    .limit(3)
    .toList();

System.out.println(firstThreeDistinct); // [3, 2, 1]
~~~

Với Stream có encounter order, `distinct` phải giữ đại diện xuất hiện đầu tiên; `limit(3)` cần chọn đúng ba giá trị đầu **sau khi loại trùng**. Các yêu cầu này có thể làm tăng chi phí phối hợp giữa các nhánh song song.

`sorted()` cũng là stateful intermediate operation: trên một nguồn lớn, nó cần xử lý tổ chức dữ liệu trước khi có thứ tự toàn cục. Nếu chỉ cần một giá trị nhỏ nhất, `min(...)` thường diễn đạt mục tiêu trực tiếp hơn `sorted().findFirst()`.

### 10.3. unordered() chỉ khi nghiệp vụ thật sự không cần thứ tự

~~~java
long count = List.of(3, 3, 2, 2, 1, 1)
    .parallelStream()
    .unordered()
    .distinct()
    .count();

System.out.println(count); // 3
~~~

`unordered()` bỏ yêu cầu giữ encounter order, có thể giúp một số pipeline song song chạy linh hoạt hơn. Nó **không tự xáo trộn dữ liệu** và không được dùng nếu báo cáo phải giữ “phần tử đầu tiên” hoặc thứ tự xuất hiện.

## 11. Phép tổng hợp và chi phí gộp nhánh

Parallel Stream thường cần **combiner** để hợp nhất các kết quả cục bộ.

### 11.1. Reduce với phép cộng associative

~~~java
long sum = java.util.stream.LongStream.rangeClosed(1, 100_000)
    .parallel()
    .reduce(0L, Long::sum);

System.out.println(sum); // 5000050000
~~~

Phép cộng số nguyên với identity 0 có tính kết hợp trong mô hình số nguyên của Java, nên có thể gộp các tổng từng nhánh theo cách hợp lệ. Chú ý tổng vẫn có thể **tràn `long`** nếu đầu vào cực lớn; Java không tự nâng số nguyên sang độ chính xác vô hạn.

### 11.2. Combiner đắt làm giảm lợi ích

Ví dụ thu thành danh sách:

~~~java
List<String> labels = java.util.stream.IntStream.range(0, 20_000)
    .parallel()
    .mapToObj(i -> "ID-" + i)
    .collect(java.util.stream.Collectors.toList());
~~~

Mỗi nhánh có thể xây bộ chứa cục bộ rồi hợp nhất. Việc tạo 20.000 chuỗi, cấp phát các bộ chứa và hợp nhất kết quả đều có chi phí. Nếu nhiệm vụ chính chỉ là biến một số thành một chuỗi ngắn, overhead có thể lớn so với tính toán.

`collect` vẫn là API đúng cho mutable reduction; ý nghĩa ở đây là **API đúng về mặt ngữ nghĩa không đồng nghĩa nhanh nhất ở chế độ song song**.

### 11.3. groupingBy có thể cần hợp nhất Map

~~~java
Map<Integer, Long> counts = java.util.stream.IntStream.range(0, 100_000)
    .parallel()
    .boxed()
    .collect(java.util.stream.Collectors.groupingBy(
        n -> n % 10,
        java.util.stream.Collectors.counting()
    ));
~~~

Kết quả có mười nhóm, mỗi nhóm có 10.000 số. Tuy nhiên, bộ chứa Map của nhiều nhánh có thể phải được hợp nhất. Với `groupingByConcurrent`, hợp đồng khác về concurrency và thứ tự; không nên thay thế tùy tiện nếu ứng dụng cần encounter order hay chính sách collector cụ thể.

Chi phí gộp và số lượng nhóm cần được xét cùng với kích thước nguồn.

## 12. Chương trình đo minh họa: cùng thuật toán, hai chế độ

Để so sánh hiệu năng một cách có ý nghĩa, **phải dùng cùng dữ liệu, cùng phép tính và cùng kết quả**. Chương trình sau so sánh sequential với parallel cho một công việc CPU thuần, không chia sẻ trạng thái mutable.

Ví dụ chạy trên **Java 17+**; API được dùng có từ Java 8.

~~~java
import java.util.stream.IntStream;

public class ParallelCostExperiment {

    // Hàm tính toán CPU thuần: không I/O, không sửa trạng thái ngoài.
    static long cpuWork(int value) {
        long x = value + 0x9E3779B97F4A7C15L;

        for (int i = 0; i < 100; i++) {
            x ^= x >>> 13;
            x *= 0xBF58476D1CE4E5B9L;
            x ^= x >>> 17;
        }

        return x & 1023L; // Kết quả từng phần tử từ 0 đến 1023.
    }

    static long calculate(int size, boolean parallel) {
        IntStream source = IntStream.range(0, size);
        if (parallel) {
            source = source.parallel();
        }

        return source
            .mapToLong(ParallelCostExperiment::cpuWork)
            .sum();
    }

    static long measureNanos(int size, boolean parallel) {
        long started = System.nanoTime();

        // Kết quả dùng để ngăn việc đo một lời gọi không cần thiết.
        long result = calculate(size, parallel);

        long elapsed = System.nanoTime() - started;
        System.out.println(
            (parallel ? "parallel" : "sequential")
                + ", size=" + size
                + ", result=" + result
                + ", elapsedNs=" + elapsed
        );
        return result;
    }

    public static void main(String[] args) {
        // Warmup đơn giản; chưa phải benchmark chuyên nghiệp.
        for (int i = 0; i < 3; i++) {
            calculate(30_000, false);
            calculate(30_000, true);
        }

        for (int size : new int[] {1_000, 30_000, 300_000}) {
            long sequential = measureNanos(size, false);
            long parallel = measureNanos(size, true);

            if (sequential != parallel) {
                throw new AssertionError(
                    "Sai kết quả tại size=" + size
                );
            }
        }
    }
}
~~~

Chương trình in **kết quả tổng bằng nhau** cho cùng `size`. Thời gian đo **không có một giá trị cố định**, vì phụ thuộc CPU, JDK, mức nóng JIT, điều kiện chạy, GC và tác vụ khác trên máy.

### 12.1. Cách đọc kết quả

Giả sử một lần chạy cho thấy:

~~~text
size=1000:   sequential nhanh hơn
size=30000:  hai cách gần tương đương
size=300000: parallel nhanh hơn
~~~

Đây chỉ là **một kịch bản giả định để luyện phân tích**, không phải kết quả thực nghiệm đã đo. Tập dữ liệu, số vòng xử lý trong `cpuWork`, phiên bản JDK và máy khác có thể đảo ngược thứ tự.

Điều cần rút ra không phải “300.000 phần tử là ngưỡng chuẩn”, mà là: **khi tổng lượng tính toán tăng, cơ hội bù chi phí song song cũng tăng**, miễn nguồn và phép gộp hỗ trợ tốt.

### 12.2. Vì sao đây chưa phải benchmark chuẩn?

Việc gọi `System.nanoTime()` một lần cho mỗi trường hợp chịu ảnh hưởng lớn của:

- **JIT warmup** và các tối ưu hóa theo lịch thực thi.
- **GC** và cấp phát bộ nhớ.
- **CPU turbo, nhiệt độ, tiết kiệm điện**, số lõi thực sự được cấp.
- **Các tiến trình khác** chạy đồng thời.
- **Thứ tự chạy mẫu** và kích thước tập dữ liệu.
- **Tần suất lặp và ngoại lệ thời gian đo**.

Đối với đánh giá có giá trị quyết định, hãy dùng **JMH** hoặc hệ thống benchmark có warmup, nhiều fork/iteration, kiểm soát đầu vào và thống kê kết quả. Bài học hiện tại chỉ trình bày một thí nghiệm minh họa, không coi các số đo đơn lẻ là bằng chứng hiệu năng.

## 13. Ngữ nghĩa và tính đúng đắn phải đứng trước việc tăng tốc

Một pipeline đúng khi tuần tự **có thể sai** khi chuyển sang song song nếu logic phụ thuộc tác dụng phụ, thứ tự callback hoặc trạng thái ngoài.

### 13.1. Không thu vào ArrayList dùng chung bằng forEach

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> broken = new ArrayList<>();

// Sai: nhiều thread có thể gọi add trên cùng ArrayList.
// IntStream.range(0, 10_000).parallel().forEach(broken::add);

// Đúng: dùng collector.
List<Integer> safe = IntStream.range(0, 10_000)
    .parallel()
    .boxed()
    .collect(java.util.stream.Collectors.toList());
~~~

`ArrayList` không thread-safe khi nhiều thread cập nhật đồng thời. Đổi sang `Collections.synchronizedList` có thể làm thao tác thêm an toàn hơn về mặt đồng bộ, nhưng không tự bảo đảm thứ tự yêu cầu và có thể tạo contention. `collect` thể hiện đúng ý định thu kết quả.

### 13.2. Reduce cần identity và tính kết hợp

~~~java
int sum = List.of(1, 2, 3, 4)
    .parallelStream()
    .reduce(0, Integer::sum); // 10
~~~

Phép cộng với identity 0 phù hợp để chia và gộp. Phép trừ không associative; không nên dùng `reduce(0, (a, b) -> a - b)` rồi kỳ vọng mọi cách phân nhóm đều trả cùng kết quả tuần tự.

Với `double`, phép cộng có thể cho sai khác nhỏ khi đổi thứ tự gộp do làm tròn dấu phẩy động. Nếu dữ liệu đòi hỏi tính tái lập tuyệt đối và chính xác (chẳng hạn tiền tệ), cần quy tắc số học/kiểu dữ liệu phù hợp.

### 13.3. Side effect khó dự đoán số lần và thứ tự

~~~java
long count = java.util.stream.IntStream.range(0, 100)
    .parallel()
    .peek(n -> {
        // Không đặt logic ghi dữ liệu bắt buộc ở đây.
    })
    .count();
~~~

Một số tối ưu hóa có thể khiến callback trung gian không được gọi cho mọi phần tử nếu terminal operation tính được kết quả mà không cần duyệt. Ngay cả khi callback được gọi, thứ tự và thread thực thi trong parallel Stream không được bảo đảm như tuần tự.

Do đó, **đừng dùng `peek`, `map` hay `filter` làm chỗ thực hiện I/O hoặc cập nhật trạng thái nghiệp vụ bắt buộc**. Những hàm trong pipeline nên không can thiệp vào nguồn và không dựa vào trạng thái ngoài có thể thay đổi.

## 14. CPU-bound, memory-bound và I/O-bound không giống nhau

Không phải công việc nào đắt cũng phù hợp với Parallel Stream.

### CPU-bound

Công việc chủ yếu tính toán, ít cần trạng thái chung:

~~~text
Giải mã dữ liệu độc lập, biến đổi số, tính hàm nặng, kiểm tra quy tắc.
~~~

Parallel có thể hữu ích nếu có đủ phần tử và nguồn chia tốt.

### Memory-bound

Công việc đọc/ghi dữ liệu rất nhiều nhưng ít phép toán:

~~~text
Duyệt mảng lớn để tính tổng hoặc sao chép dữ liệu.
~~~

Tốc độ có thể bị giới hạn bởi băng thông bộ nhớ hoặc cache. Thêm worker có thể không mang lại lợi ích tương ứng.

### I/O-bound

Công việc chờ đĩa, mạng hoặc hệ thống ngoài:

~~~text
Gọi HTTP cho từng phần tử, truy vấn database, đọc file chậm.
~~~

Parallel Stream không tự biến các lời gọi blocking thành nonblocking. Mức song song không được điều khiển để phù hợp giới hạn dịch vụ ngoài có thể làm cạn kết nối, nghẽn pool hoặc gây timeout.

Trong hệ thống I/O, thường cần một cơ chế quản lý concurrency/backpressure và giới hạn tác vụ rõ ràng hơn thay vì chuyển ngay sang `parallelStream()`.

## 15. Các yếu tố môi trường khiến kết quả đo khác nhau

Thử nghiệm parallel trên laptop có thể không phản ánh đúng môi trường production:

- **Số processor khả dụng** có thể khác số core vật lý.
- **Container CPU quota** có thể giới hạn CPU dù máy chủ có nhiều lõi.
- **Common fork/join pool** thường được dùng trong các triển khai Stream mặc định và có thể cạnh tranh với công việc khác trong cùng JVM.
- **Máy có tải đồng thời** khiến thêm tác vụ parallel làm tăng latency của toàn ứng dụng dù throughput một tác vụ đơn lẻ có vẻ tăng.
- **Bộ nhớ và GC** thay đổi khi `collect` tạo nhiều container trung gian.
- **Các phiên bản JDK khác nhau** có thể chọn chiến lược chia/điều phối khác nhau.

Không nên dùng `Runtime.getRuntime().availableProcessors()` để suy luận chắc chắn rằng pipeline sẽ sử dụng đúng bấy nhiêu thread, hoặc rằng tốc độ phải tăng bấy nhiêu lần.

Nếu tối ưu hóa một API server, hãy đo **throughput và độ trễ của nhiều request đồng thời**, không chỉ thời gian chạy một Stream trong môi trường không tải.

## 16. Quy trình quyết định khi nào thử parallel()

Dưới đây là checklist thực hành:

| Câu hỏi | Nếu câu trả lời là “không” |
|---|---|
| Kết quả tuần tự đã đúng và có kiểm thử chưa? | Đảm bảo tính đúng trước |
| Các hàm xử lý từng phần tử có thể chạy độc lập không? | Loại bỏ trạng thái chung/side effect trước |
| Phép `reduce`/`collect` có combiner đúng hợp đồng không? | Sửa logic tổng hợp |
| Nguồn có đủ việc để chia không? | Tiếp tục dùng sequential |
| Spliterator có thể chia nguồn hiệu quả không? | Cân nhắc đổi nguồn hoặc thuật toán |
| Chi phí phần tử đủ lớn để bù overhead không? | Benchmark; đừng mặc định có lợi |
| Có phải giữ encounter order khắt khe không? | Đánh giá chi phí `sorted`, `limit`, `forEachOrdered` |
| Tài nguyên CPU/bộ nhớ có dư không? | Không tranh chấp làm hại các tác vụ khác |
| Đã đo với dữ liệu và tải đại diện chưa? | Chưa đủ cơ sở quyết định |

Điểm quyết định là **tổng thời gian, throughput, độ trễ và tính đúng**. Chế độ parallel chỉ là một lựa chọn thực thi; nó không phải yêu cầu bắt buộc của Java Stream API.

## 17. Những hiểu nhầm và lỗi thường gặp

| Hiểu nhầm / lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| “Dữ liệu hơn 10.000 phần tử thì luôn bật parallel” | Ngưỡng tùy CPU, thuật toán và nguồn | Đo với dữ liệu thật |
| “Càng nhiều thread càng nhanh” | Overhead, contention, giảm cache locality | Quan sát effective parallelism |
| “Các phần tử xử lý giống nhau về chi phí” | Load imbalance nếu có phần tử rất nặng | Đánh giá phân bố chi phí |
| “`trySplit` bắt buộc chia đều” | Thiết kế giả định sai hợp đồng | Chấp nhận split không đều hoặc null |
| “`SIZED` chỉ giúp tăng tốc nên khai báo đại” | Có thể làm sai kết quả | Chỉ công bố đặc tính đúng |
| “`ArrayList` đủ an toàn khi `forEach` song song” | Race condition | Dùng `collect` hoặc kiến trúc đồng bộ thích hợp |
| “`findAny()` luôn lấy phần tử đầu tiên” | Kết quả không xác định | Dùng `findFirst()` khi có thứ tự và cần đầu tiên |
| “`forEachOrdered` chạy nhanh như `forEach`” | Chi phí duy trì thứ tự | Chỉ dùng khi cần thứ tự |
| “`sorted().limit(k)` luôn xử lý ít phần tử” | `sorted` có thể cần toàn bộ nguồn | Chọn thuật toán top-k phù hợp |
| “Một phép `count()` lớn nghĩa là đã duyệt n phần tử” | Nguồn `SIZED` có thể được tối ưu | Không đo công việc bằng side effect |
| “Parallel sẽ tăng tốc I/O chặn” | Nghẽn dịch vụ, cạn kết nối, timeout | Giới hạn concurrency và dùng mô hình I/O phù hợp |
| “Một lần chạy nhanh hơn là đủ để kết luận” | Kết quả nhiễu | Dùng benchmark lặp và nhiều môi trường |
| “Thứ tự in ra giống nhau nghĩa là parallel ổn định” | Phụ thuộc thứ tự lịch thực thi | Xác định encounter order và terminal contract |
| “Chia càng nhỏ càng tốt” | Tăng chi phí lập lịch/gộp | Chọn granularity phù hợp |

## 18. Bài tập thực hành: phân tích ba yếu tố trên cùng pipeline

**Bối cảnh:** một hệ thống cần tính tổng kết quả xử lý của nhiều mã công việc, mỗi mã áp dụng một hàm CPU thuần. Có ba thí nghiệm:

1. **Kích thước:** giữ nguyên hàm xử lý, thay `size` giữa 1.000 và 200.000.
2. **Chi phí phần tử:** giữ `size` cố định, thay số vòng tính trong hàm từ 5 thành 200.
3. **Cách chia:** quan sát Spliterator của nguồn, rồi mô tả ảnh hưởng nếu một custom Spliterator `trySplit` luôn trả `null`.

Yêu cầu: giải thích trường hợp nào có cơ hội tăng tốc khi parallel, **không dựa vào một ngưỡng số phần tử cố định**.

### Lời giải tham khảo (Java 8+)

~~~java
import java.util.Spliterator;
import java.util.stream.IntStream;

public class ParallelThreeFactorsPractice {

    static long work(int value, int rounds) {
        long x = value + 1L;

        for (int i = 0; i < rounds; i++) {
            x = x * 1_664_525L + 1_013_904_223L;
            x ^= x >>> 11;
        }

        return x & 1023L;
    }

    static long sum(int size, int rounds, boolean parallel) {
        IntStream source = IntStream.range(0, size);

        if (parallel) {
            source = source.parallel();
        }

        return source
            .mapToLong(value -> work(value, rounds))
            .sum();
    }

    public static void main(String[] args) {
        for (int size : new int[] {1_000, 200_000}) {
            for (int rounds : new int[] {5, 200}) {
                long seq = sum(size, rounds, false);
                long par = sum(size, rounds, true);

                System.out.println(
                    "size=" + size
                    + ", rounds=" + rounds
                    + ", equal=" + (seq == par)
                ); // equal=true nếu cả hai tính đúng
            }
        }

        Spliterator.OfInt source = IntStream.range(0, 20)
            .spliterator();

        System.out.println(
            source.hasCharacteristics(Spliterator.SIZED)
        ); // true

        System.out.println(source.estimateSize()); // 20

        Spliterator.OfInt prefix = source.trySplit();

        if (prefix != null) {
            System.out.println(
                prefix.estimateSize() + source.estimateSize()
            ); // 20
        }
    }
}
~~~

Chương trình này **không in thời gian chạy**; nó kiểm tra điều quan trọng đầu tiên: cùng một thuật toán trên cùng đầu vào phải cho kết quả tương đương ở hai chế độ. Khi tự thực nghiệm thời gian, hãy dùng công cụ benchmark và kiểm soát các biến đã nêu ở mục 12.

### Diễn giải mong đợi

- Với `size = 1_000, rounds = 5`: ít công việc, nên overhead parallel dễ chi phối.
- Với `size = 200_000, rounds = 200`: lượng công việc CPU lớn và các phần tử độc lập, là ứng viên tốt hơn để thử parallel.
- Với `size = 1_000, rounds = 200`: mỗi phần tử nặng nhưng tổng số tác vụ có thể vẫn đủ lớn để có lợi; **phải đo**, không kết luận trước.
- Với `size = 200_000, rounds = 5`: rất nhiều phần tử nhưng công việc mỗi phần tử nhẹ, nên có thể bị chi phí gộp/lập lịch hoặc băng thông nhớ giới hạn.
- Nếu `trySplit()` luôn trả `null`: việc chia nguồn để xử lý song song bị hạn chế nghiêm trọng, dù `parallel` đã được bật.

### Câu hỏi tự kiểm tra

1. Ba yếu tố chính của bài là gì? — **Kích thước nguồn, chi phí phần tử và khả năng chia nguồn**.
2. `parallel()` có bảo đảm nhanh hơn `sequential()` không? — **Không**.
3. `trySplit()` trả gì khi không thể chia? — **`null`**.
4. `estimateSize()` có luôn chính xác không? — **Không**, chỉ khi nguồn có hợp đồng phù hợp như `SIZED`.
5. `SUBSIZED` bổ sung điều gì so với `SIZED`? — **Các nhánh tách ra tiếp tục có kích thước chính xác**.
6. Một nửa có công việc nặng hơn nhiều làm sao ảnh hưởng parallel? — **Nhánh chậm nhất có thể quyết định thời gian hoàn thành**.
7. `forEachOrdered` có giữ encounter order không? — **Có**, nhưng có thể tăng chi phí phối hợp.
8. Có thể dùng `ArrayList::add` vào một danh sách ngoài với `parallelStream().forEach` không? — **Không an toàn khi nhiều thread cập nhật chung**.
9. Khi một nguồn có `SIZED`, `count()` có thể tránh duyệt không? — **Có** trong những pipeline có thể tối ưu tương ứng.
10. Vì sao `Collectors.groupingBy` có thể tốn khi song song? — **Phải tạo và hợp nhất các Map trung gian**.
11. Nếu dữ liệu đến từ HTTP blocking, bật parallel có tự giải quyết I/O không? — **Không**.
12. Muốn kết luận nhanh hơn cần gì? — **Benchmark có warmup, lặp đủ lần, cùng dữ liệu, theo dõi hiệu năng của hệ thống thực**.

## 19. Tổng kết: ba biến số phải được đánh giá cùng nhau

Để đánh giá **parallel Stream**, đừng chỉ nhìn số phần tử hoặc số lõi CPU. Hãy xét ba biến số như một hệ thống:

- **Kích thước nguồn** quyết định tổng lượng việc và cơ hội tạo nhiều tác vụ.
- **Chi phí mỗi phần tử** quyết định khả năng tiết kiệm thời gian nhờ thực thi đồng thời; chi phí **không đồng đều** dẫn đến mất cân bằng tải.
- **Cách chia nguồn** qua `Spliterator.trySplit()`, `estimateSize()` cùng các đặc tính như `SIZED`/`SUBSIZED` ảnh hưởng trực tiếp đến số lượng, kích thước và độ cân bằng của các phần việc.

Sau khi nguồn được chia, các yếu tố khác vẫn quan trọng: `ORDERED`, `distinct`, `sorted`, `limit`, chi phí combiner, contention, trạng thái mutable và kiểu công việc CPU/memory/I/O. Vì vậy, **tính đúng phải được kiểm tra trước, hiệu năng phải được đo sau**.

Sử dụng `parallel()` là quyết định **dựa trên workload**, không phải quy tắc áp dụng đồng loạt cho mọi pipeline. Hiểu rõ cách phối hợp giữa kích thước, công việc và khả năng chia giúp bạn thiết kế Stream, custom `Spliterator` và các phép tổng hợp hiệu quả hơn mà không đánh đổi tính đúng đắn hoặc làm cạn tài nguyên hệ thống.
