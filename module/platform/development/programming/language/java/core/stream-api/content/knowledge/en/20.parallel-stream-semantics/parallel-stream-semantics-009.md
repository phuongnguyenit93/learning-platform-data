# Tránh song song lồng nhau và lựa chọn điểm song song hóa

**Java Stream API** cho phép thay một pipeline tuần tự bằng pipeline song song qua `parallel()` hoặc `parallelStream()`. Cách sử dụng có vẻ đơn giản, nhưng hiệu năng không tăng chỉ vì có nhiều lời gọi `parallel()`. Một sai lầm phổ biến là **song song hóa cả vòng ngoài lẫn vòng trong** của dữ liệu phân cấp: nhóm dữ liệu, từng tệp, từng lô giao dịch hoặc từng hàng ma trận.

Bài học thuộc chương **Ngữ nghĩa xử lý song song**, tập trung vào hai quyết định:

1. **Có nên song song hóa không?** Công việc có đủ lớn, độc lập, tách được và không bị giới hạn chủ yếu bởi I/O hoặc trạng thái chia sẻ không?
2. **Nếu có, đặt ranh giới song song ở đâu?** Song song hóa theo lô ở ngoài, theo phần tử ở trong, hay tổ chức lại thành **một** tập công việc đủ mịn để chia?

Nguyên tắc khởi đầu: **ưu tiên một tầng song song hóa có chủ đích; chỉ dùng song song lồng nhau khi đo đạc cho thấy nó thật sự có lợi và không làm thay đổi ngữ nghĩa.**

## 1. Song song lồng nhau là gì?

Giả sử có nhiều lô số nguyên; mỗi lô cần tính tổng, rồi cộng tổng các lô. Chúng ta có một cấu trúc hai tầng:

```text
Dữ liệu:
  Lô A -> [1, 2, 3]
  Lô B -> [4, 5]
  Lô C -> [6, 7, 8]

Tầng ngoài: xử lý các lô A, B, C
Tầng trong: xử lý các phần tử của từng lô
```

Có bốn cách tổ chức:

| Tầng ngoài | Tầng trong | Ý nghĩa |
| --- | --- | --- |
| Tuần tự | Tuần tự | Đường cơ sở đơn giản nhất. |
| **Song song** | Tuần tự | Nhiều lô độc lập được phân chia; mỗi lô được tính tuần tự. |
| Tuần tự | **Song song** | Mỗi lần chỉ xử lý một lô, nhưng các phần tử trong lô có thể được phân chia. |
| **Song song** | **Song song** | Song song lồng nhau: nhiều pipeline bên trong cùng yêu cầu thực thi song song. |

Đoạn sau là ví dụ về **song song lồng nhau**:

```java
import java.util.Arrays;
import java.util.List;

List<int[]> batches = Arrays.asList(
    new int[] {1, 2, 3},
    new int[] {4, 5},
    new int[] {6, 7, 8}
);

long total = batches.parallelStream()
    .mapToLong(batch -> Arrays.stream(batch)
        .parallel()
        .asLongStream()
        .sum())
    .sum();

System.out.println(total); // 36
```

Code trên **không bị Java cấm** và có thể cho kết quả đúng. Vấn đề là số cấp yêu cầu song song tăng mà không chứng minh được có thêm tài nguyên tính toán hữu ích. Với vài mảng nhỏ như ví dụ, chi phí lập lịch và chia/gộp công việc rất có thể lớn hơn phép cộng.

**Phân biệt:** Một stream chỉ có `parallel()` một lần rồi đi qua nhiều phép `map`, `filter`, `reduce` **không phải** song song lồng nhau. Song song lồng nhau thường xuất hiện khi lambda của một pipeline tạo và chạy **một pipeline song song khác**.

## 2. `parallel()` là chế độ của pipeline, không phải một giai đoạn riêng

Trên cùng một pipeline, `parallel()` và `sequential()` đặt chế độ thực thi của **toàn pipeline khi terminal operation chạy**. Chúng không có nghĩa mọi phép toán đứng trước `parallel()` chạy tuần tự, rồi những phép toán đứng sau mới chạy song song.

```java
import java.util.stream.IntStream;

long value = IntStream.rangeClosed(1, 100)
    .map(n -> n * 2)
    .parallel()
    .filter(n -> n % 3 == 0)
    .asLongStream()
    .sum();
```

Trong ví dụ, `map` không trở thành một “giai đoạn tuần tự riêng” chỉ vì được khai báo trước `parallel()`. Java Stream dùng một chế độ tuần tự hoặc song song cho pipeline khi thực thi.

```java
import java.util.stream.IntStream;

boolean parallel = IntStream.range(0, 10)
    .parallel()
    .sequential()
    .isParallel();

System.out.println(parallel); // false
```

Nếu cần một giai đoạn tuần tự **hoàn tất thật sự** trước một giai đoạn song song, phải có một ranh giới xử lý rõ ràng, thường là materialize dữ liệu trung gian hoặc thiết kế hai pipeline độc lập. Cách đó có chi phí bộ nhớ và sao chép, nên chỉ dùng khi yêu cầu nghiệp vụ hoặc hiệu năng biện minh được.

## 3. Vì sao song song lồng nhau thường gây hại?

`parallelStream()` không có nghĩa tạo một nhóm CPU mới độc lập cho mỗi pipeline. Trong những ứng dụng Java thông thường, việc xử lý song song bằng Stream thường dựa trên cơ chế **fork/join** và `ForkJoinPool.commonPool()`. Hai pipeline lồng nhau có thể cùng tranh chấp tài nguyên thực thi.

Hình dung các lô đang được tính:

```text
CPU khả dụng:       [Core 1] [Core 2] [Core 3] [Core 4]

Tầng ngoài:          Lô A     Lô B     Lô C
                       |        |        |
Tầng trong:          split A   split B  split C
                       \        |       /
                 nhiều tác vụ cần chia/gộp và phối hợp
```

Những chi phí đáng chú ý:

1. **Phân mảnh công việc:** mỗi lô nhỏ lại tạo thêm những tác vụ con. Số tác vụ và số lần phối hợp có thể nhiều hơn số phép tính có ích.
2. **Tranh chấp tài nguyên:** các pipeline lồng nhau cạnh tranh cùng nhóm worker, cache CPU, băng thông bộ nhớ và tài nguyên đồng bộ.
3. **Tải không cân bằng:** một lô rất lớn và nhiều lô nhỏ có thể khiến việc chia theo lô không đủ tốt; song song thêm ở trong chưa chắc giải quyết được.
4. **Thời gian chờ và độ trễ:** tác vụ ngoài phải chờ terminal operation bên trong hoàn thành; các lô có thể chờ nhau theo lịch thực thi không kiểm soát.
5. **Áp lực bộ nhớ và GC:** tạo nhiều đối tượng trung gian, buffer hoặc tác vụ làm tăng cấp phát và hoạt động thu gom rác.
6. **Khó phân tích hành vi:** khi có hiệu ứng phụ, log, truy cập I/O hoặc phép tổng hợp không đúng hợp đồng, kết quả khó tái hiện hơn.

Đây là những **rủi ro**, không phải bảo đảm rằng mọi pipeline lồng nhau đều chậm hơn. Với dữ liệu và môi trường cụ thể, cách thực thi có thể khác nhau; kết luận về tốc độ cần dựa vào phép đo.

Tương tự, không nên khẳng định rằng hai lời gọi `parallel()` luôn tạo ra hai lần số thread, hay rằng song song lồng nhau tự nó luôn gây deadlock. Số worker và cách thực thi phụ thuộc runtime, pool, nguồn, workload và mã bên trong.

## 4. Ba phiên bản rõ nghĩa cho dữ liệu hai tầng

Dưới đây là một chương trình độc lập (Java 8+) để so sánh **ngữ nghĩa** các lựa chọn. Dùng `long` khi cộng các giá trị `int` để giảm nguy cơ tràn tổng 32 bit:

```java
import java.util.Arrays;
import java.util.List;

public class ChooseParallelLevel {
    static long sequential(List<int[]> batches) {
        return batches.stream()
            .mapToLong(batch -> Arrays.stream(batch)
                .asLongStream()
                .sum())
            .sum();
    }

    static long outerParallel(List<int[]> batches) {
        return batches.parallelStream()
            .mapToLong(batch -> Arrays.stream(batch)
                .asLongStream()
                .sum()) // Mỗi lô được xử lý tuần tự.
            .sum();
    }

    static long innerParallel(List<int[]> batches) {
        return batches.stream()
            .mapToLong(batch -> Arrays.stream(batch)
                .asLongStream()
                .parallel()
                .sum())
            .sum(); // Các lô được xử lý lần lượt.
    }

    public static void main(String[] args) {
        List<int[]> batches = Arrays.asList(
            new int[] {1, 2, 3},
            new int[] {4, 5},
            new int[] {6, 7, 8}
        );

        System.out.println(sequential(batches));    // 36
        System.out.println(outerParallel(batches)); // 36
        System.out.println(innerParallel(batches)); // 36
    }
}
```

Ba phương án cho cùng giá trị khi dữ liệu không bị sửa và tổng không tràn. Nhưng **chúng không đồng nghĩa về chi phí**:

- `sequential` thích hợp làm đường cơ sở và cho lô nhỏ.
- `outerParallel` phù hợp khi có **nhiều lô độc lập**, đủ công việc trong mỗi lô để bù chi phí lập lịch và kích thước các lô tương đối cân đối.
- `innerParallel` có thể phù hợp khi có **rất ít lô**, nhưng một lô chứa rất nhiều phần tử và nguồn trong lô hỗ trợ chia hiệu quả.

Không nên chọn chỉ dựa trên số lượng dòng code. Cần nhìn vào số lượng tác vụ, độ lớn và độ lệch giữa các lô.

## 5. Chọn điểm song song hóa theo độ hạt công việc

**Độ hạt** (*granularity*) là lượng công việc mà một tác vụ độc lập thực hiện. Nếu tác vụ quá nhỏ, chi phí phân phối lớn hơn lợi ích; nếu quá lớn hoặc phân bổ không đều, một vài worker có thể rảnh trong khi worker khác bận.

| Dạng workload | Lựa chọn khởi đầu | Lý do |
| --- | --- | --- |
| Vài chục phần tử, phép tính rất rẻ | **Tuần tự** | Overhead song song thường không đáng. |
| Hàng nghìn lô độc lập, mỗi lô đủ lớn | **Song song ở ngoài** | Chia theo lô; logic từng lô dễ hiểu và không lồng pool. |
| Một mảng nguyên thủy cực lớn | **Song song ở trong**, tức chính stream của mảng | Chỉ có một nguồn lớn cần phân chia. |
| Một vài lô cực lớn và nhiều lô rất nhỏ | **Thiết kế lại việc chia thành nhiều chunk cân đối** | Giảm tình trạng tác vụ lớn cuối cùng kéo dài toàn bộ công việc. |
| Nhiều phần tử nhưng bị giới hạn bởi đọc tệp, mạng, DB | **Cân nhắc mô hình I/O có kiểm soát riêng** | CPU parallel stream không mặc nhiên phù hợp với blocking I/O. |
| Phải giữ thứ tự hành động quan sát được | **Ưu tiên tuần tự**, hoặc song song có cơ chế gộp theo thứ tự | Chi phí duy trì thứ tự có thể triệt tiêu lợi ích. |
| Có trạng thái chia sẻ mutable | **Thiết kế lại để độc lập theo phần tử trước** | `parallel()` không làm code có race trở nên an toàn. |

Một quy trình thực dụng là:

1. Bắt đầu từ phiên bản tuần tự **đúng và có kiểm thử**.
2. Xác định phần tốn CPU bằng profiling hoặc số liệu thực tế.
3. Đánh giá nguồn có Spliterator hỗ trợ chia việc tốt không (mảng, dãy chỉ số, `ArrayList` thường thuận lợi hơn nguồn khó tách).
4. Chọn **một** tầng có đủ nhiều công việc độc lập.
5. Đo lại và kiểm tra **đúng kết quả** trước khi cân nhắc thêm tối ưu.

Nếu một tầng song song đã dùng gần hết tài nguyên CPU, thêm tầng khác thường không tạo thêm năng lực tính toán; nó chủ yếu thay đổi cách chia công việc và chi phí điều phối.

## 6. Tổ chức lại nguồn thay vì lồng song song

Nếu các lô là những phần tử độc lập, có thể thử tạo **một stream của tất cả phần tử** và song song hóa tại một điểm:

```java
import java.util.Arrays;
import java.util.List;

List<int[]> batches = Arrays.asList(
    new int[] {1, 2, 3},
    new int[] {4, 5},
    new int[] {6, 7, 8}
);

long total = batches.stream()
    .flatMapToInt(Arrays::stream)
    .asLongStream()
    .parallel()
    .sum();

System.out.println(total); // 36
```

Đây là **một pipeline song song duy nhất**, không có stream song song được tạo bên trong lambda. Cách mô tả rõ ràng khi mọi phần tử có chung phép xử lý và ta chỉ cần một phép tổng hợp cuối.

Tuy nhiên, `flatMap` không bảo đảm tự biến mọi nguồn phân cấp thành những chunk cân đối. Khi một lô khổng lồ và các lô khác rất nhỏ, khả năng chia của pipeline vẫn có thể bị giới hạn bởi cấu trúc nguồn. **Đừng coi flatten là mẹo tăng tốc luôn đúng**; phải đo và xem xét đặc tính Spliterator.

Nếu dữ liệu vốn đã ở **một mảng nguyên thủy lớn**, có thể dùng chính nguồn mảng để chia trực tiếp:

```java
import java.util.Arrays;

int[] values = {1, 2, 3, 4, 5, 6, 7, 8};

long sum = Arrays.stream(values)
    .asLongStream()
    .parallel()
    .sum();

System.out.println(sum); // 36
```

Với bài toán nhiều lô nhưng rất mất cân bằng, một lựa chọn khác là **tạo danh sách chunk/đơn vị công việc độc lập** trước khi gọi stream, sao cho mỗi chunk có lượng xử lý đủ lớn nhưng không quá chênh lệch. Bước chuẩn bị chunk có thể tiêu tốn bộ nhớ và thời gian; chỉ đáng làm nếu phép đo cho thấy lợi ích.

## 7. Một ví dụ theo lô: xử lý đối tượng mà không lồng song song

Giả sử dữ liệu là `List<List<Integer>>` và cần báo cáo tổng từng lô theo đúng thứ tự của lô gốc. Có thể song song hóa từng lô, xử lý nội dung trong lô tuần tự:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<List<Integer>> groups = Arrays.asList(
    Arrays.asList(1, 2, 3),
    Arrays.asList(4, 5),
    Arrays.asList(6, 7, 8)
);

List<Long> sums = groups.parallelStream()
    .map(group -> group.stream()
        .mapToLong(Integer::longValue)
        .sum())
    .collect(Collectors.toList());

System.out.println(sums); // [6, 9, 21]
```

`groups` là một `List` có encounter order, và `Collectors.toList()` giữ thứ tự gặp phần tử trong kết quả. **Thứ tự tính toán các lô có thể khác**, nhưng kết quả được đặt đúng thứ tự lô.

Trường hợp khác, nếu mỗi lô phải gọi dịch vụ bên ngoài rồi cập nhật trạng thái dùng chung, đây không còn là phép xử lý CPU thuần túy. Cần kiểm soát giới hạn kết nối, retry, timeout, tính idempotent và thứ tự commit. Không nên tự động thêm `parallelStream()` chỉ vì các lô trông độc lập.

## 8. Hợp đồng hàm hành vi và reduction quan trọng hơn số thread

Trong pipeline song song, `map`, `filter` và các lambda khác nên **không can thiệp nguồn** (*non-interfering*) và **không dựa vào trạng thái chia sẻ có thể thay đổi** (*stateless*). Sai lầm thường gặp là giữ một bộ đếm hoặc `ArrayList` bên ngoài:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> output = new ArrayList<>();

// VÍ DỤ SAI: nhiều worker sửa ArrayList không thread-safe.
IntStream.range(0, 1000).parallel()
    .forEach(output::add);
```

Việc này có thể làm mất dữ liệu, thay đổi thứ tự hoặc gây lỗi cấu trúc. Thay vì đẩy kết quả ra biến mutable ngoài pipeline, dùng collector:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> output = IntStream.range(0, 1000)
    .parallel()
    .boxed()
    .collect(Collectors.toList());

System.out.println(output.size()); // 1000
```

`collect` quản lý các kết quả tích lũy và combiner. Không cần một danh sách dùng chung cho mọi worker.

### Combiner phải đúng hợp đồng

Đối với `reduce`, phép kết hợp phải có **identity** và **tính kết hợp** phù hợp. Ví dụ cộng số nguyên (nếu không tràn) phù hợp; phép trừ không có tính kết hợp:

```java
import java.util.stream.IntStream;

int sum = IntStream.rangeClosed(1, 4)
    .parallel()
    .reduce(0, Integer::sum);

System.out.println(sum); // 10

// KHÔNG NÊN dùng phép trừ làm reduction song song:
// .reduce(0, (left, right) -> left - right)
```

Một kết quả tuần tự đúng trong tình huống nhỏ không chứng minh phép rút gọn sẽ đúng khi dữ liệu được tách/gộp song song. Tương tự, dùng `new ArrayList<>()` làm identity của `reduce` rồi sửa danh sách không phải thay thế hợp lệ cho `collect`.

### `AtomicInteger` không giải quyết bài toán thuật toán

Đổi bộ đếm `int[]` thành `AtomicInteger` có thể làm thao tác tăng an toàn luồng nhưng vẫn tạo **điểm tranh chấp**. Nếu predicate phụ thuộc vào thứ tự `getAndIncrement()`, phần tử nào được chọn sẽ còn phụ thuộc lịch làm việc của worker. Hãy dùng dữ liệu của phần tử để quyết định và để `count`, `sum`, `reduce` hoặc `collect` tổng hợp kết quả.

## 9. Thứ tự, ngắn mạch và các phép toán có trạng thái

Song song hóa có thể làm tăng chi phí khi pipeline cần giữ encounter order hoặc phải phối hợp giữa các phần nguồn:

| Phép toán | Điểm cần cân nhắc khi song song |
| --- | --- |
| `forEach` | Không bảo đảm thứ tự gọi action trên nguồn có thứ tự. |
| `forEachOrdered` | Giữ thứ tự gặp phần tử nhưng có thể tăng phối hợp, hạn chế lợi ích song song. |
| `findFirst` | Trên nguồn có thứ tự phải trả phần tử đầu tiên, dù phần tử sau xử lý xong trước. |
| `findAny` | Có thể trả một phần tử bất kỳ; phù hợp khi thật sự không cần “đầu tiên”. |
| `limit`, `skip` | Trên stream song song có thứ tự, duy trì tiền tố/phần bỏ qua chính xác có thể tốn chi phí. |
| `distinct` | Loại trùng cần theo dõi những phần tử đã gặp; ordered distinct có thể cần phối hợp/buffer. |
| `sorted` | Là phép toán có trạng thái, thường phải xử lý toàn bộ nguồn hữu hạn trước khi phát ra kết quả đã sắp xếp. |

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> firstTen = IntStream.range(0, 1000)
    .parallel()
    .boxed()
    .limit(10)
    .collect(Collectors.toList());

System.out.println(firstTen); // [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
```

`limit(10)` cần giữ **mười phần tử đầu theo encounter order** của nguồn. Pipeline có thể thực thi và hủy tác vụ ở những phần nguồn khác nhau; đừng suy ra rằng đúng mười lần lambda được gọi hoặc đúng mười phần tử được đọc ở mọi triển khai.

`unordered()` có thể giảm một số ràng buộc thứ tự trong pipeline nếu nghiệp vụ cho phép, nhưng thay đổi **hợp đồng kết quả**: ví dụ `findFirst()` sau `unordered()` không còn nghĩa là phần tử đầu theo nguồn gốc. Không dùng nó chỉ như mẹo hiệu năng khi thứ tự là yêu cầu thực.

## 10. Tính xác định của kết quả và phép cộng số thực

Ngữ nghĩa song song không nhất thiết làm kết quả **sai**; kết quả có thể đúng theo hợp đồng nhưng khác thứ tự quan sát hoặc khác một chút do số học:

```java
import java.util.stream.DoubleStream;

double sequential = DoubleStream.of(1e16, 1.0, -1e16)
    .sum();

double parallel = DoubleStream.of(1e16, 1.0, -1e16)
    .parallel()
    .sum();
```

Không nên viết bài kiểm thử đòi hai kết quả `double` phải có cùng từng bit cho mọi dữ liệu và mọi cách chia. Phép cộng `double` không có tính kết hợp tuyệt đối vì làm tròn nhị phân; ngay cả khi API dùng kỹ thuật tính tổng có bù sai số, cách gộp kết quả vẫn có thể tạo sai khác nhỏ.

Với tổng số nguyên, kết quả chính xác và ổn định hơn nếu không vượt phạm vi kiểu số và phép reduction đúng hợp đồng. Khi yêu cầu tiền tệ hoặc độ chính xác thập phân cao, chọn mô hình số thích hợp như đơn vị nguyên nhỏ nhất, `BigInteger` hay `BigDecimal`, kèm quy tắc làm tròn và kiểm tra tràn.

**Song song lồng nhau** không phải nguyên nhân duy nhất gây kết quả khó tái lập. Trạng thái chia sẻ, thứ tự `forEach`, bộ sinh số ngẫu nhiên dùng chung, I/O và phép gộp không kết hợp có thể gây vấn đề **ngay từ một pipeline song song**.

## 11. Các nguồn khác nhau có khả năng chia việc khác nhau

Stream chạy song song cần chia nguồn thành các phần độc lập. Khả năng ấy chịu ảnh hưởng lớn bởi **`Spliterator`** của nguồn:

- **Mảng, `ArrayList`, `IntStream.range`** thường có kích thước xác định và khả năng chia thuận lợi.
- **`LinkedList`** hoặc các nguồn duyệt tuyến tính có thể phát sinh chi phí chia khác, phụ thuộc triển khai và độ lớn nguồn.
- **`Stream.iterate`** có quan hệ trạng thái giữa các phần tử; không tự nhiên như dãy chỉ số độc lập.
- **`Stream.generate`** có nguồn không giới hạn nếu chưa cắt lát; dùng supplier có trạng thái chia sẻ có thể gây tranh chấp.
- **`Files.lines`**, nguồn mạng và cơ sở dữ liệu có thêm chi phí I/O, quản lý tài nguyên và tính nhất quán dữ liệu.

Do đó cùng một phép `map(...).reduce(...)` có thể hưởng lợi từ song song trên mảng lớn nhưng không hưởng lợi trên nguồn khó tách hoặc dữ liệu nhỏ. Nếu tự viết Spliterator, `trySplit()`, `estimateSize()` và `characteristics()` phải đúng hợp đồng; không gắn `SIZED`/`SUBSIZED` tùy tiện để mong tăng tốc.

Với đầu vào cực kỳ lệch kích thước, ta có thể chuẩn bị các **chunk có độ hạt tương đối cân bằng** và dùng một `IntStream.range` trên chỉ số chunk. Đây là một lựa chọn tổ chức công việc, không bảo đảm tối ưu cho mọi workload.

## 12. Đừng dùng parallel stream làm bộ điều phối I/O có giới hạn

Xử lý CPU-bound và I/O-bound có nhu cầu điều phối khác nhau:

| CPU-bound | Blocking I/O |
| --- | --- |
| Phần lớn thời gian thực hiện phép tính. | Phần lớn thời gian chờ mạng, tệp hoặc DB. |
| Có thể hưởng lợi từ các core khi dữ liệu độc lập và đủ lớn. | Cần giới hạn số kết nối, timeout, retry, backpressure hoặc hủy tác vụ. |
| Stream parallel có thể là công cụ phù hợp. | Thường cần API bất đồng bộ, `ExecutorService` hoặc cơ chế điều phối I/O có kiểm soát. |

Ví dụ một pipeline dùng `parallelStream()` để gọi API ngoài cho từng bản ghi có thể **chiếm worker trong lúc chờ I/O**, làm ảnh hưởng các tác vụ CPU khác dùng chung tài nguyên. Khi các lời gọi chậm hoặc blocking lồng vào nhau, thời gian chờ có thể trở nên khó dự đoán.

Không nên tuyên bố mọi trường hợp blocking I/O trong parallel stream đều deadlock. Vấn đề đúng hơn là **thiếu kiểm soát concurrency và tranh chấp tài nguyên**, nhất là khi logic phụ thuộc các tác vụ khác đang cần cùng worker. Với ứng dụng cần giới hạn I/O rõ ràng, hãy chọn cơ chế thực thi có khả năng cấu hình số tác vụ đồng thời, timeout và hủy.

## 13. Common pool và giới hạn kiểm soát tài nguyên

Trong thực tế phổ biến, parallel stream dùng `ForkJoinPool.commonPool()`. Điểm cần nhớ:

1. **Pool là tài nguyên dùng chung trong quá trình thực thi ứng dụng**, không phải một pool mới cho mỗi `parallel()`.
2. Số worker hữu ích không thể tăng vô hạn theo số stream lồng nhau; số core, công việc blocking và cấu hình runtime đều có giới hạn.
3. Chạy nhiều request đồng thời, mỗi request lại mở một pipeline song song có thể gây tranh chấp ngay cả khi **không hề lồng nhau trong mã nguồn**.
4. Không có tham số chuẩn của `Stream.parallel()` để chọn một executor riêng hoặc giới hạn số worker theo từng request.

Một số dự án thử gọi parallel stream bên trong một tác vụ của `ForkJoinPool` tùy chỉnh để điều khiển pool. Hãy tránh xem đây là hợp đồng API phổ quát cho mọi JDK và mọi cách sử dụng; nếu cần quyền kiểm soát execution policy chặt chẽ, thiết kế trực tiếp với `ExecutorService`, `ForkJoinTask` hoặc thư viện phù hợp sẽ rõ ràng hơn.

Đặc biệt, đừng sửa cấu hình global common pool như một cách giải quyết vội vàng cho nested parallelism. Thay đổi đó có thể ảnh hưởng các phần khác của ứng dụng, không chỉ pipeline đang được tối ưu.

## 14. Đo hiệu năng đúng cách

Quyết định chọn tầng song song phải được xác minh trên **workload thật hoặc benchmark gần thực tế**. Những yếu tố cần đưa vào phép đo:

- Số lô, kích thước trung bình, phân phối kích thước lô và mức lệch giữa lô nhỏ/lớn.
- Chi phí tính toán trên từng phần tử: phép cộng đơn giản khác xa thuật toán CPU nặng.
- Kích thước nguồn và khả năng chia của Spliterator.
- Mức đồng thời bên ngoài (số request, thread, tác vụ khác).
- Tốc độ xử lý (*throughput*), độ trễ trung bình và độ trễ p95/p99, cấp phát bộ nhớ và GC.
- Cấu hình phần cứng, số core, phiên bản JDK và trạng thái warm-up của JIT.

Không dựa vào một lần gọi `System.nanoTime()` quanh đoạn stream để đưa ra kết luận cuối. JVM có warm-up, tối ưu JIT, biến động hệ thống và khả năng loại bỏ phép tính không được quan sát. Đối với benchmark vi mô Java, **JMH** là công cụ phù hợp hơn, với warm-up, nhiều iteration/fork và cách ngăn compiler loại bỏ công việc.

Thiết kế các phiên bản để so sánh:

```text
A. outer sequential + inner sequential
B. outer parallel   + inner sequential
C. outer sequential + inner parallel
D. outer parallel   + inner parallel   // phương án đối chứng
E. một stream phẳng song song hoặc chia thành chunk
```

Trong mọi phương án, hãy **kiểm tra kết quả có tương đương** trước khi so sánh thời gian. Với `double`, sử dụng tiêu chí sai số thích hợp; với dữ liệu có thứ tự, so sánh theo hợp đồng thứ tự thật sự yêu cầu.

### Cách diễn giải số đo

Nếu B nhanh hơn A nhưng D chậm hơn B, điều đó cho thấy **song song ở tầng ngoài là đủ** trong cấu hình thử nghiệm ấy. Nếu C nhanh hơn B khi chỉ có một lô rất lớn, hãy cân nhắc **song song hóa nguồn lớn**. Nếu E vượt D trên dữ liệu nhiều lô lệch kích thước, có thể việc phân chia thành chunk tốt hơn cách lồng. Các kết luận này phải gắn với workload và JDK cụ thể, không phải định luật chung.

## 15. Ví dụ chọn thiết kế theo mục tiêu nghiệp vụ

### Trường hợp A: xử lý nhiều hồ sơ độc lập

Mỗi hồ sơ có hàng chục trường; số hồ sơ rất nhiều. Chọn song song hóa **theo hồ sơ**, còn việc xử lý trường trong một hồ sơ là tuần tự:

```java
import java.util.Arrays;
import java.util.List;

List<List<Integer>> records = Arrays.asList(
    Arrays.asList(1, 2, 3),
    Arrays.asList(4, 5, 6),
    Arrays.asList(7, 8, 9)
);

long total = records.parallelStream()
    .mapToLong(record -> record.stream()
        .mapToLong(Integer::longValue)
        .sum())
    .sum();

System.out.println(total); // 45
```

Trong ví dụ, các hồ sơ không chia sẻ trạng thái tích lũy. `record.stream()` được tạo riêng cho từng hồ sơ và chạy tuần tự.

### Trường hợp B: một tập số rất lớn

Chỉ có **một nguồn dữ liệu lớn**, ví dụ mảng `int[]`. Chọn song song hóa **ngay trên mảng**:

```java
import java.util.Arrays;

int[] values = {10, 20, 30, 40, 50};
long total = Arrays.stream(values)
    .asLongStream()
    .parallel()
    .sum();

System.out.println(total); // 150
```

Mảng ở đây chỉ để minh họa cú pháp; với năm phần tử, tuần tự gần như luôn là đường cơ sở hợp lý. Bản thiết kế chỉ đáng thử song song khi khối lượng phép tính đủ lớn.

### Trường hợp C: nhiều lô lệch kích thước

Một lô có hàng triệu phần tử, các lô khác chỉ vài phần tử. Song song ở ngoài có thể không cân bằng tải; song song ở cả hai tầng có thể tạo thêm tác vụ mà vẫn không hiệu quả. Cân nhắc **chia lô lớn thành các chunk độc lập** và dùng một pipeline song song trên danh sách chunk.

Điểm quyết định không phải “có bao nhiêu `parallel()`”, mà là **tổng số đơn vị công việc có ích** và khả năng chia đều chúng cho tài nguyên sẵn có.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Thêm `parallel()` ở cả outer và inner nhưng chậm hơn | Overhead phân chia/gộp và tranh chấp tài nguyên | Giữ một tầng song song; đo phiên bản còn lại. |
| Máy nhiều core nhưng stream gần như không nhanh hơn | Dữ liệu nhỏ, mapper rẻ, nguồn khó chia, băng thông bộ nhớ hoặc phối hợp lớn | Tăng độ hạt hữu ích, chọn nguồn tách được, xem profiling. |
| Nhiều request song song làm độ trễ tăng | Các request tranh chấp common pool hoặc CPU | Cân nhắc giới hạn concurrency ở mức ứng dụng. |
| Kết quả thay đổi giữa những lần chạy | Side effect, trạng thái chia sẻ, combiner sai hoặc thứ tự số thực | Dùng hàm stateless, collect/reduce đúng hợp đồng, xác định sai số. |
| Danh sách kết quả thiếu phần tử | `parallel().forEach(sharedArrayList::add)` | Dùng `collect` hoặc cấu trúc phối hợp đúng. |
| Log in ra khác thứ tự | `forEach` không bảo đảm encounter order | Chỉ dùng `forEachOrdered` khi thứ tự bắt buộc; chấp nhận chi phí. |
| `sorted`/`distinct`/`limit` gây chậm | Stateful/ordered operations yêu cầu thêm phối hợp | Tối ưu pipeline mà không đổi ngữ nghĩa; đo lại. |
| Blocking I/O làm các tác vụ CPU khác chậm | Worker bị giữ khi chờ ngoại vi | Dùng mô hình I/O có giới hạn đồng thời rõ ràng. |
| `parallel()` được gọi giữa pipeline nhưng không tạo “hai giai đoạn” như mong muốn | Chế độ thực thi áp dụng cho toàn pipeline | Dùng ranh giới xử lý thực nếu cần các pha tách biệt. |
| Nested parallelism chỉ nhanh trên máy phát triển | Phần cứng, JDK, tải khác nhau | Benchmark với nhiều kích thước và mức tải gần production. |

## 17. Bài tập thực hành

**Bài 1 — Nhận diện nested parallelism.** Cho:

```java
long result = batches.parallelStream()
    .mapToLong(batch -> Arrays.stream(batch)
        .parallel()
        .asLongStream()
        .sum())
    .sum();
```

Hãy chỉ ra hai pipeline song song độc lập về mặt cú pháp và viết lại để chỉ song song hóa ở **tầng ngoài**. Giải thích vì sao các lô nhỏ thường không đáng để song song riêng.

**Bài 2 — Chọn điểm song song hóa.** Với 10.000 lô, mỗi lô có 100 phần tử và một phép tính CPU tương đối nặng, hãy so sánh dự kiến giữa `outerParallel` và `innerParallel`. Nếu chỉ có **một** lô gồm 10 triệu phần tử, bạn sẽ đổi quyết định thế nào?

**Bài 3 — Flatten.** Viết một pipeline dùng `flatMapToInt(Arrays::stream).asLongStream().parallel().sum()` cho `List<int[]>`, kiểm tra kết quả giống phiên bản tuần tự. Giải thích vì sao việc flatten không bảo đảm dữ liệu được chia đều khi kích thước từng lô rất lệch.

**Bài 4 — Trạng thái chia sẻ.** Sửa ví dụ `parallel().forEach(output::add)` thành một collector hợp lệ. Việc đổi `ArrayList` thành `Collections.synchronizedList` giải quyết phần nào, và tại sao vẫn nên ưu tiên cách thu thập không dựa trên side effect bên ngoài?

**Bài 5 — Thứ tự và số thực.** Tạo `IntStream.range(0, 1000).parallel().boxed().limit(10).collect(toList())`. Kiểm tra danh sách nhận được theo encounter order. Sau đó thử `forEach` để quan sát thứ tự in, nhưng đừng viết test đòi `forEach` in cố định.

**Bài 6 — Benchmark.** Lập bảng đo thời gian và throughput cho năm cách A–E ở mục 14 với lô cân đối, lô lệch kích thước và dữ liệu nhỏ. Chạy warm-up và nhiều lần đo; kết luận dựa trên số liệu chứ không phải số lượng lời gọi `parallel()`.

**Ghi nhớ:** `parallel()` giúp khai thác nhiều tài nguyên tính toán khi công việc **độc lập, đủ lớn và chia được**. Song song hóa cả stream ngoài lẫn stream trong thường tăng chi phí điều phối và tranh chấp, không tạo thêm core CPU. Hãy chọn **một tầng song song hóa có độ hạt phù hợp**, dùng lambda không phụ thuộc trạng thái chia sẻ, bảo đảm reduction đúng hợp đồng và đo trên workload thực tế. Khi một lô quá lớn hoặc dữ liệu mất cân bằng, cân nhắc thiết kế lại đơn vị công việc thay vì tự động thêm một tầng `parallel()`.
