# Chi phí giữ trạng thái của `sorted()` và `distinct()` trong Java Stream

Trong Java Stream API, không phải mọi phép biến đổi trung gian (*intermediate operation*) đều có thể xử lý từng phần tử mà không lưu gì thêm. Hai thao tác thường gặp là **`sorted()`** và **`distinct()`** cần thông tin từ **nhiều phần tử**, nên được xếp vào nhóm *stateful intermediate operations*. Hiểu chi phí giữ trạng thái giúp dự đoán bộ nhớ, thời gian chờ kết quả, khả năng dừng sớm và tác động khi chạy stream song song.

Hình dung một pipeline:

~~~text
List<T> / nguồn dữ liệu
      |
      v
filter(...)       -- thường stateless: quyết định từng phần tử
      |
      v
distinct()        -- stateful: nhớ các giá trị đã thấy
      |
      v
sorted(...)       -- stateful: cần tổ chức nhiều phần tử để xác định thứ tự
      |
      v
limit(3)          -- chỉ lấy tối đa 3 kết quả ở vị trí này
      |
      v
toList()          -- terminal: yêu cầu kết quả
~~~

**Thông điệp chính:** cả `sorted` và `distinct` đều là phép trung gian và vẫn có tính *lazy* khi xây dựng pipeline, nhưng **lazy không đồng nghĩa không tốn bộ nhớ**, cũng không bảo đảm `limit` đặt phía sau sẽ làm mọi bước phía trước rẻ hơn. Chi phí thực tế phụ thuộc kích thước đầu vào, số giá trị khác nhau, đặc tính có thứ tự của nguồn, vị trí phép toán và cách thực thi tuần tự/song song.

## 1. Stateless và stateful trong một pipeline

**Stateless** (ví dụ `map`, `filter`) thường chỉ cần phần tử hiện tại và hàm người gọi đưa vào. Với pipeline tuần tự đơn giản, phần tử có thể đi qua nhiều bước stateless rồi tới terminal mà không cần tạo danh sách đầy đủ sau mỗi bước.

**Stateful** cần ghi nhớ trạng thái liên quan đến các phần tử khác:

- `sorted()` hoặc `sorted(comparator)` phải xác định vị trí các phần tử theo một thứ tự chung.
- `distinct()` cần biết phần tử tương đương đã xuất hiện hay chưa để không phát lại.
- `limit()` cũng giữ bộ đếm; nó là *short-circuiting stateful intermediate operation*, nhưng trạng thái thường nhỏ hơn một phép sắp xếp toàn bộ đầu vào. Phân biệt **cần nhớ bao nhiêu** với việc **có trạng thái hay không**.

Ví dụ ở mức ý tưởng:

~~~java
List<String> result = List.of("B", "A", "B", "C").stream()
        .filter(s -> !s.isEmpty())
        .distinct()
        .sorted()
        .toList();
// [A, B, C]
~~~

Cần import `java.util.List`; đoạn đặt trong một phương thức. `filter` kiểm tra từng giá trị. `distinct` phải loại lần xuất hiện thứ hai của `"B"`. `sorted` tạo thứ tự tăng dần. `toList()` là terminal kích hoạt quá trình đánh giá pipeline.

Một phép trung gian stateful **không nhất thiết luôn phải lưu toàn bộ nguồn**: `distinct` có thể nhớ tập khóa đã gặp và chuyển tiếp các phần tử chưa trùng dần dần; ngược lại `sorted` thường phải nhận hết đầu vào hữu hạn trước khi phát phần tử đã sắp xếp. Đây là khác biệt quan trọng về **thời điểm kết quả có thể xuất hiện**.

## 2. `sorted()`: vì sao thường cần buffer toàn bộ?

`Stream.sorted()` sắp xếp theo thứ tự tự nhiên của phần tử; `Stream.sorted(Comparator<? super T>)` dùng comparator người gọi cung cấp. Đây là **stateful intermediate operation**, không phải terminal, và nó **không sắp xếp trực tiếp collection nguồn**. Với `List`, muốn sửa list tại chỗ thì dùng `list.sort(comparator)`.

~~~java
List<Integer> descending = List.of(4, 1, 3, 2).stream()
        .sorted(Comparator.reverseOrder())
        .toList();
// [4, 3, 2, 1]
~~~

Cần import `List` và `Comparator`. Với đầu vào hữu hạn nhưng chưa được sắp xếp, `sorted` nói chung cần biết toàn bộ các phần tử để bảo đảm phần tử nào đứng trước phần tử nào: một giá trị nhỏ nhất có thể chỉ xuất hiện ở cuối nguồn.

### Chi phí điển hình

Nếu có **n phần tử** đầu vào:

| Tài nguyên | Xu hướng thường gặp |
| --- | --- |
| Thời gian | Sắp xếp so sánh tổng quát thường khoảng `O(n log n)` lượt/chi phí so sánh |
| Bộ nhớ làm việc | Thường cần `O(n)` tham chiếu/bộ đệm bổ sung để gom và sắp thứ tự các phần tử |
| Độ trễ ra phần tử đầu tiên | Có thể phải đợi đọc hết nguồn hữu hạn trước khi phát kết quả đã sắp xếp |
| Kết quả | Phần tử theo comparator hoặc thứ tự tự nhiên, không thay đổi nguồn |

Đây là **mô hình phân tích hữu ích**, không phải cam kết độ phức tạp hay lượng cấp phát cố định của đặc tả Stream API. Cách triển khai, nguồn đã có thứ tự, kích thước biết trước, loại phần tử, JDK và thuật toán sắp xếp đều ảnh hưởng hiệu năng. Chi phí của chính comparator cũng quan trọng: nếu comparator gọi xử lý chuỗi nặng hoặc trích xuất thuộc tính đắt đỏ, chi phí thực tế tăng theo số lần so sánh.

Với `IntStream`, `LongStream` hay `DoubleStream` có `sorted()` riêng cho primitive, có thể tránh boxing từng phần tử như khi sử dụng `Stream<Integer>`. Tuy nhiên, sắp xếp nhiều giá trị vẫn có chi phí.

### Tính ổn định và thứ tự

Với stream **ordered**, `sorted()` bảo đảm ổn định (*stable*): hai phần tử được comparator đánh giá ngang nhau giữ thứ tự tương đối đã gặp. Với stream **unordered**, đặc tả không đưa ra bảo đảm ổn định tương tự.

~~~java
record Task(String id, int priority) {}

List<Task> tasks = List.of(
        new Task("A", 1),
        new Task("B", 1),
        new Task("C", 2)
);
List<Task> ordered = tasks.stream()
        .sorted(Comparator.comparingInt(Task::priority))
        .toList();
// Task A đứng trước Task B vì cùng priority và nguồn List có thứ tự.
~~~

Đây là đoạn mã minh họa trong một phương thức, cần `List` và `Comparator`; `record Task` được đặt ở phạm vi lớp hoặc gần phương thức phù hợp. **Comparator trả 0 không đồng nghĩa hai đối tượng bằng nhau theo `equals`.** `sorted` sắp xếp, không loại trùng.

## 3. `distinct()`: cần nhớ các phần tử đã gặp

`Stream.distinct()` loại các phần tử trùng dựa trên `Object.equals(Object)`. Trên stream ordered, kết quả **giữ lần xuất hiện đầu tiên** của mỗi giá trị tương đương theo `equals`; trên stream unordered, không bảo đảm phần tử đại diện nào được giữ nếu các phần tử bằng nhau nhưng có khác biệt khác.

~~~java
List<String> names = List.of("Binh", "An", "Binh", "Chi", "An", "Dung");
List<String> unique = names.stream().distinct().toList();
// [Binh, An, Chi, Dung]
~~~

Để nhận biết `"Binh"` thứ hai bị trùng, một triển khai điển hình cần lưu cấu trúc tương tự `Set` với những giá trị đã gặp. Nếu có **n phần tử đầu vào** và **u giá trị phân biệt**:

| Tài nguyên | Xu hướng thường gặp |
| --- | --- |
| Bộ nhớ | Khoảng `O(u)` trạng thái để nhận biết những giá trị đã gặp |
| Thời gian | Với hash-based set thông thường và `hashCode`/`equals` hợp lý, trung bình khoảng `O(n)` cho quá trình kiểm tra trùng |
| Trường hợp xấu | Hash collision, `equals` đắt đỏ hoặc nguồn đặc biệt có thể làm chi phí tăng đáng kể |
| Độ trễ | Với pipeline tuần tự thích hợp, phần tử phân biệt có thể được phát khi tìm thấy, không nhất thiết đợi hết nguồn |

`O(u)` là hướng phân tích thuật toán thường gặp, **không phải công thức cấp phát chính xác cho mọi JDK hoặc chế độ song song**. Khi `u` gần `n` (hầu hết phần tử đều khác nhau), tập trạng thái có thể lớn gần như toàn bộ đầu vào. Khi rất nhiều phần tử trùng nhau, `u` nhỏ hơn `n` đáng kể.

`distinct` không nhận comparator hay bộ trích xuất khóa. Nếu muốn loại trùng theo một trường `id` thay vì toàn bộ `equals` của đối tượng, cần **thiết kế phép biến đổi thành khóa**, dùng map/collector theo key, hoặc một cơ chế dedup có hợp đồng rõ ràng. Đừng giả định `sorted(comparator).distinct()` sẽ loại các phần tử comparator cho bằng 0: `distinct` vẫn dùng `equals`.

### Hợp đồng `equals` và `hashCode`

Với lớp tự tạo dùng để so sánh giá trị, phải thiết kế `equals` và `hashCode` nhất quán: nếu `a.equals(b)` thì `a.hashCode() == b.hashCode()`. `record` mặc định cung cấp các phương thức so sánh theo component phù hợp.

~~~java
record Entry(String id, int version) {}

List<Entry> entries = List.of(
        new Entry("A", 1),
        new Entry("A", 1),
        new Entry("A", 2)
);
List<Entry> distinctEntries = entries.stream().distinct().toList();
// Hai Entry("A", 1) gộp thành một; Entry("A", 2) vẫn riêng.
~~~

Đoạn mã trên chỉ mang tính minh họa, được đặt trong ngữ cảnh có import `List`. Nếu cần chỉ một phần tử cho mỗi `id`, `distinct` trên record gồm cả `version` không đáp ứng yêu cầu — phải mô tả quy tắc chọn phiên bản và dùng collector/map phù hợp.

Không nên sửa những field tham gia `equals`/`hashCode` trong lúc phần tử đang được kiểm tra qua cấu trúc hash: điều đó có thể phá tính nhất quán của phép nhận diện trùng.

## 4. Thứ tự các phép toán: đúng kết quả nhưng chi phí khác nhau

Với cùng các bước, đổi vị trí có thể thay đổi **giá trị kết quả**, **số phần tử phải xử lý** và **bộ nhớ**.

### `filter` trước `sorted`

~~~java
List<Integer> result = List.of(5, 1, 4, 2, 3).stream()
        .filter(n -> n % 2 == 0)
        .sorted()
        .toList();
// [2, 4]
~~~

`sorted` chỉ nhận hai số chẵn, thay vì phải xử lý cả năm số rồi mới lọc. Khi điều kiện lọc rẻ và độc lập với thứ tự, đặt `filter` sớm thường giúp giảm số phần tử đưa vào stateful operation. Tuy nhiên, không được thay đổi thứ tự nếu predicate phụ thuộc các bước chuẩn hóa trước đó hoặc làm thay đổi ngữ nghĩa.

### `distinct` trước `sorted` khi cần sắp xếp giá trị duy nhất

~~~java
List<String> uniqueSorted = names.stream()
        .distinct()
        .sorted()
        .toList();
// [An, Binh, Chi, Dung]
~~~

Trong ví dụ này, `distinct` giảm sáu phần tử đầu vào xuống bốn giá trị, nên `sorted` phải sắp xếp ít hơn. `distinct` vẫn trả chi phí giữ tập đã thấy; đây là trao đổi giữa việc nhớ các giá trị duy nhất và giảm số phần tử cần sort.

~~~java
List<String> sortedUnique = names.stream()
        .sorted()
        .distinct()
        .toList();
// [An, Binh, Chi, Dung]
~~~

Hai pipeline trên có cùng kết quả **trong dữ liệu String này**. Không áp dụng hoán đổi một cách mù quáng với mọi comparator, thứ tự quan sát hay yêu cầu chọn phần tử đại diện: `sorted` theo comparator và `distinct` theo `equals` là hai khái niệm khác nhau.

### `sorted().limit(k)` khác `limit(k).sorted()`

~~~java
List<String> smallestThree = names.stream()
        .sorted()
        .limit(3)
        .toList();
// [An, An, Binh]
~~~

Vì cần biết ba phần tử nhỏ nhất của **toàn bộ nguồn**, `sorted` đứng trước và có thể xử lý tất cả phần tử trước khi `limit(3)` nhận dữ liệu.

~~~java
List<String> sortedFirstThree = names.stream()
        .limit(3)
        .sorted()
        .toList();
// [An, Binh, Binh]
~~~

Ở đây chỉ ba phần tử **đầu nguồn** (`Binh, An, Binh`) được đưa vào `sorted`. Thường rẻ hơn nhưng đáp án là "sắp xếp ba phần tử đầu", **không phải** "ba phần tử nhỏ nhất của toàn bộ nguồn".

**Lưu ý:** dùng `limit(k)` *sau* `sorted` không có nghĩa Java API bảo đảm chỉ cần bộ nhớ `O(k)`. Nếu mục tiêu của bài toán thực sự là tìm top-k từ n giá trị mà k nhỏ hơn nhiều n, cân nhắc thuật toán top-k chuyên biệt (ví dụ priority queue kích thước k) thay vì sort toàn bộ rồi limit.

### `distinct().limit(k)` có thể đọc nhiều hơn k phần tử nguồn

~~~java
List<String> firstThreeUnique = names.stream()
        .distinct()
        .limit(3)
        .toList();
// [Binh, An, Chi]
~~~

Nguồn phải đi qua hai lần gặp `Binh` mới tìm được `Chi` (là phần tử phân biệt thứ ba). Đổi vị trí:

~~~java
List<String> uniqueWithinFirstThree = names.stream()
        .limit(3)
        .distinct()
        .toList();
// [Binh, An]
~~~

Cách thứ hai chỉ xét ba giá trị đầu và cho ra hai giá trị khác nhau. Nếu mục tiêu là giới hạn **ngân sách đọc dữ liệu** trước khi dedup, đặt `limit` trước. Nếu mục tiêu là tìm đủ k phần tử duy nhất, đặt `distinct` trước `limit` nhưng cần tính đến khả năng nguồn không có đủ k giá trị khác nhau.

## 5. Short-circuit và nguồn vô hạn: điều kiện dừng thực sự

Hai ví dụ cố ý **không được chạy**:

~~~java
// Không kết thúc theo nghĩa hữu hạn đầu ra:
// Stream.iterate(1, n -> n + 1)
//       .sorted()
//       .limit(3)
//       .toList();

// Nguồn vô hạn toàn giá trị 1, chỉ có một giá trị duy nhất:
// Stream.generate(() -> 1)
//       .distinct()
//       .limit(2)
//       .toList();
~~~

Trường hợp đầu: `sorted` đứng trước `limit`; nó cần xử lý một nguồn không kết thúc để biết thứ tự đầy đủ. Trường hợp sau: `distinct` chỉ phát phần tử `1` đầu tiên, nhưng `limit(2)` vẫn đợi phần tử phân biệt thứ hai vốn không tồn tại.

Đặt giới hạn đầu nguồn hữu hạn:

~~~java
List<Integer> topThreeOfHundred = Stream.iterate(1, n -> n + 1)
        .limit(100)
        .sorted(Comparator.reverseOrder())
        .limit(3)
        .toList();
// [100, 99, 98]
~~~

Đây là **ba số lớn nhất trong một trăm giá trị đầu**, không phải ba số lớn nhất của dãy tăng vô hạn. Nếu nguồn có thể vô hạn nhưng câu hỏi yêu cầu một tập mẫu hữu hạn, hãy nêu rõ phạm vi mẫu trước khi thực hiện phép sort.

~~~java
List<Integer> uniqueSample = Stream.generate(() -> 1)
        .limit(10)
        .distinct()
        .toList();
// [1]
~~~

`limit(10)` trước `distinct` giúp pipeline kết thúc mà không cần tìm đủ một số lượng giá trị duy nhất. Điều đó thay đổi ý nghĩa từ "tìm k giá trị phân biệt" sang "dedup trong m mẫu".

Ngoài ra, thao tác stateful nằm **sau** `limit` có thể xử lý số phần tử đã chặn, nhưng điều này không đảm bảo `Supplier` sẽ không block, hoặc không xuất hiện lỗi trong mapper/predicate.

## 6. Ví dụ Java 17+ đầy đủ và stdout đã kiểm chứng

Lưu file **`SortedDistinctCostDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class SortedDistinctCostDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Binh", "An", "Binh", "Chi", "An", "Dung");

        System.out.println("sorted=" + names.stream().sorted().toList());
        System.out.println("distinct=" + names.stream().distinct().toList());
        System.out.println("distinctThenSorted=" +
                names.stream().distinct().sorted().toList());
        System.out.println("sortedThenDistinct=" +
                names.stream().sorted().distinct().toList());
        System.out.println("sortedThenLimit=" +
                names.stream().sorted().limit(3).toList());
        System.out.println("limitThenSorted=" +
                names.stream().limit(3).sorted().toList());
        System.out.println("distinctThenLimit=" +
                names.stream().distinct().limit(3).toList());
        System.out.println("limitThenDistinct=" +
                names.stream().limit(3).distinct().toList());

        List<String> parallelDistinct = names.parallelStream().distinct().toList();
        System.out.println("parallelDistinct=" + parallelDistinct);

        List<String> byLength = List.of("aa", "bb", "c").stream()
                .sorted(Comparator.comparingInt(String::length))
                .distinct()
                .toList();
        System.out.println("lengthSortedDistinct=" + byLength);

        List<String> mutable = new ArrayList<>(names.stream().distinct().toList());
        mutable.add("E");
        System.out.println("mutableSize=" + mutable.size());
    }
}
~~~

Lệnh chạy (JDK 17 trở lên):

~~~bash
javac SortedDistinctCostDemo.java
java SortedDistinctCostDemo
~~~

**Stdout chính xác:**

~~~text
sorted=[An, An, Binh, Binh, Chi, Dung]
distinct=[Binh, An, Chi, Dung]
distinctThenSorted=[An, Binh, Chi, Dung]
sortedThenDistinct=[An, Binh, Chi, Dung]
sortedThenLimit=[An, An, Binh]
limitThenSorted=[An, Binh, Binh]
distinctThenLimit=[Binh, An, Chi]
limitThenDistinct=[Binh, An]
parallelDistinct=[Binh, An, Chi, Dung]
lengthSortedDistinct=[c, aa, bb]
mutableSize=5
~~~

Phân tích:

1. `sorted` tạo thứ tự từ điển tăng dần, **không tự loại trùng**.
2. `distinct` loại giá trị trùng nhưng trên `List` ordered giữ thứ tự xuất hiện đầu: `Binh, An, Chi, Dung`.
3. Hai tổ hợp `distinct→sorted` và `sorted→distinct` cho cùng kết quả **ở dữ liệu này**; mục đích giữ trạng thái và số phần tử cần xử lý có thể khác.
4. Đặt `limit` trước/sau thao tác stateful đổi tập đầu vào của thao tác đó và có thể đổi đáp án.
5. `parallelStream().distinct()` vẫn giữ kết quả xuất hiện đầu với nguồn `List` ordered; tuy nhiên chi phí phối hợp để bảo toàn thứ tự có thể cao.
6. `sorted(Comparator.comparingInt(String::length)).distinct()` vẫn giữ cả `"aa"` và `"bb"` vì chúng **không bằng nhau theo `equals`**, dù comparator so độ dài đều trả 0. `"c"` đứng trước vì ngắn hơn.
7. `Stream.toList()` tạo list không hỗ trợ sửa cấu trúc; `new ArrayList<>(...)` ở ví dụ giúp chủ động tạo bản có thể thay đổi trước khi thêm `"E"`.

Với JDK 17, toàn bộ chương trình biên dịch bằng `javac --release 17` và đầu ra trên được xác nhận bằng chạy thực tế.

## 7. Stream song song: vì sao stateful thường đắt hơn?

**Parallel stream** chia quá trình xử lý thành các phần việc. `map`/`filter` stateless thường tương đối thuận lợi cho phân tách, nhưng `sorted` và `distinct` cần **phối hợp giữa các phần**.

### `sorted()` song song

Muốn có thứ tự sắp xếp cuối cùng, các phần cần được hợp nhất theo comparator. Có thể tạo các bộ đệm trung gian, phân vùng dữ liệu và gộp lại. CPU nhiều lõi có thể hữu ích với nguồn đủ lớn, nhưng chi phí cấp phát, chia việc, đồng bộ và gộp dữ liệu có thể vượt lợi ích trên tập nhỏ.

Với nguồn có encounter order, `sorted` có nghĩa sắp xếp ổn định. Comparator phải nhất quán, không sửa dữ liệu và tốt nhất không có side effect. Tránh giả định các lời gọi comparator diễn ra tuần tự hoặc theo thứ tự nhất định trong quá trình thực thi song song.

### `distinct()` song song trên nguồn ordered

Khi phải giữ **lần xuất hiện đầu tiên** trong một stream có encounter order, các worker không thể luôn quyết định độc lập phần tử nào là đại diện đầu tiên mà không phối hợp. Điều đó có thể đòi hỏi xử lý đồng bộ/buffering đáng kể. Javadoc của `distinct` cũng cảnh báo xử lý song song trên nguồn có thứ tự có thể đắt đỏ vì yêu cầu giữ ổn định.

Nếu bài toán **không quan tâm thứ tự phần tử đại diện**, và chỉ cần tập giá trị phân biệt:

~~~java
List<String> result = names.parallelStream()
        .unordered()
        .distinct()
        .toList();
~~~

Đây là đoạn minh họa có biến `names` ở chương trình ví dụ. `unordered()` loại bỏ ràng buộc encounter order của pipeline, có thể giúp thực hiện `distinct` song song hiệu quả hơn; nhưng kết quả **không có thứ tự được bảo đảm**. Không áp `unordered()` khi ứng dụng cần "giữ bản ghi xuất hiện đầu" hoặc cần hiển thị thứ tự cố định.

Không nên khẳng định `parallelStream()` luôn nhanh hơn: hãy đo bằng dữ liệu đủ lớn, cấu hình JVM và môi trường thực thi phù hợp. Với mục tiêu benchmark đáng tin cậy, dùng JMH để kiểm soát warm-up, tối ưu JIT và phép đo; không dùng một lần `System.nanoTime()` rồi tổng quát hóa thành quy luật.

## 8. Lập kế hoạch chi phí từ số lượng đầu vào và độ chọn lọc

Giả sử có `n` phần tử nguồn, `m` phần tử qua `filter`, `u` phần tử phân biệt trong số `m`:

| Pipeline | Tác động dự kiến |
| --- | --- |
| `filter(p).sorted()` | `sorted` phải xử lý khoảng `m` phần tử thay vì `n` |
| `filter(p).distinct().sorted()` | `distinct` xem `m` phần tử và nhớ khoảng `u` khóa; `sorted` xử lý khoảng `u` phần tử |
| `sorted().filter(p)` | `sorted` có thể phải xử lý cả `n` phần tử trước khi filter giảm xuống `m` |
| `limit(k).sorted()` | Sort trên tối đa `k` phần tử được chuyển xuống từ nguồn |
| `sorted().limit(k)` | Thông thường vẫn phải sort toàn bộ đầu vào rồi mới lấy `k` phần tử |
| `limit(k).distinct()` | Dedup tối đa `k` phần tử đã lấy mẫu |
| `distinct().limit(k)` | Có thể phải đọc hơn `k` phần tử, thậm chí không kết thúc nếu nguồn vô hạn không có đủ giá trị phân biệt |

Bảng mô tả xu hướng xử lý, không phải số phép toán/byte cấp phát cụ thể. **Độ chọn lọc** của predicate quyết định `m`; **độ đa dạng** của dữ liệu quyết định `u`. Hai đại lượng này thường có tác động lớn tới chi phí, nên cần đo với dữ liệu đại diện thay vì chỉ dùng dataset giả có vài phần tử.

Trong pipeline nhiều bước, có thể có tối ưu của bộ máy Stream. Ví dụ một số terminal như `count()` trên nguồn biết chính xác kích thước có thể tính kết quả mà không thực thi mọi phép trung gian, miễn bảo toàn kết quả được yêu cầu. Vì vậy **không dựa vào side effect trong `peek`, `map`, comparator hoặc predicate để kết luận số lần chúng được gọi**. Để quan sát chi phí, hãy đo allocation/heap và thời gian cho một tác vụ nghiệp vụ thật, không làm cho phép đo phụ thuộc vào print trong pipeline.

## 9. Các phương án khi dữ liệu lớn

### Lọc và giảm dữ liệu trước stateful operation

Nếu `filter` có thể đẩy lên sớm mà không thay đổi ngữ nghĩa, loại dữ liệu không cần trước `sorted` hoặc `distinct`. Tương tự, nếu chỉ cần một phần nhỏ của một nguồn rất lớn, hãy xác định **phạm vi nguồn hữu hạn** từ đầu (thời gian, số bản ghi, khóa phân vùng, cửa sổ).

### Chỉ cần top-k thì dùng thuật toán top-k thích hợp

`sorted(comparator).limit(k)` ngắn gọn và đúng với nguồn hữu hạn, nhưng thường phải sắp toàn bộ. Nếu `k` nhỏ hơn rất nhiều `n`, dùng **priority queue kích thước k** có thể đạt khoảng `O(n log k)` thời gian và `O(k)` bộ nhớ cho top-k, rồi sort k kết quả cuối cùng. Đây là **thuật toán thay thế** cần cài đặt đúng quy tắc so sánh; Stream API `sorted` không hứa sẽ tự biến thành thuật toán top-k khi thấy `limit`.

~~~java
// Minh họa cấu trúc trong một phương thức:
// Giữ k giá trị lớn nhất bằng min-heap, sau đó xếp giảm dần.
PriorityQueue<Integer> heap = new PriorityQueue<>();
int k = 3;
for (int value : values) {
    if (heap.size() < k) {
        heap.add(value);
    } else if (value > heap.peek()) {
        heap.poll();
        heap.add(value);
    }
}
List<Integer> top = new ArrayList<>(heap);
top.sort(Comparator.reverseOrder());
~~~

Đây là **đoạn minh họa**, cần `java.util.PriorityQueue`, `List`, `ArrayList`, `Comparator` và một `Iterable<Integer> values` hữu hạn đã xác định; không phải chương trình tự chạy. Với k bằng 0 cần xử lý riêng trước vòng lặp; với k lớn hơn số phần tử, chỉ có bấy nhiêu giá trị. Heap không loại trùng nếu không bổ sung quy tắc.

### Cần distinct trên nguồn quá lớn

Dedup **chính xác trên toàn bộ một nguồn vô hạn có thể chứa vô số giá trị khác nhau** không thể mặc nhiên giữ trạng thái hữu hạn bằng `distinct()`. Có thể định nghĩa lại bài toán thành dedup theo từng batch/window, partition theo key, hoặc lưu trạng thái ra hệ thống ngoài. Nếu dùng Bloom filter hay kỹ thuật gần đúng, phải chấp nhận nguy cơ loại nhầm giá trị chưa thấy (*false positive*), không gọi đó là distinct chính xác.

### Chỉ cần đếm giá trị khác nhau

`stream.distinct().count()` diễn đạt đúng ý trên nguồn hữu hạn nhưng vẫn có thể tốn bộ nhớ để xác định các khóa phân biệt. Không giả định chỉ vì terminal `count()` trả một số đơn lẻ mà pipeline trước đó dùng `O(1)` bộ nhớ. Có thể chuyển sang thống kê gần đúng nếu nghiệp vụ cho phép, nhưng phải nêu rõ sai số.

## 10. Lỗi thường gặp và kiểm tra tính đúng

**Nhầm comparator với equality:** `sorted(comparator)` dùng comparator; `distinct()` dùng `equals`. Hai chuỗi cùng độ dài không trùng chỉ vì comparator theo length cho kết quả 0. Để dedup theo khóa, xây dựng thuật toán/collector cho khóa với chính sách chọn bản ghi.

**Đặt `limit` sau `sorted` trên vô hạn:** sorting vô hạn không thể hoàn tất như một phép sort toàn bộ. Giới hạn tập dữ liệu trước khi sort hoặc xác định lại yêu cầu.

**Đặt `limit` sau `distinct` khi không đủ giá trị phân biệt:** nguồn vô hạn toàn số 1 với `distinct().limit(2)` sẽ chờ vô hạn. Nếu cần giới hạn số lần đọc, đưa `limit` trước distinct, chấp nhận số giá trị phân biệt đầu ra có thể ít hơn k.

**Nghĩ `distinct` không cần bộ nhớ vì stream lazy:** nó phải nhận biết các khóa đã gặp. Dữ liệu càng nhiều giá trị phân biệt, trạng thái càng lớn.

**Tưởng `sorted` luôn cần ít bộ nhớ khi có `limit(10)` phía sau:** `limit` sau sort không xóa yêu cầu về thứ tự toàn bộ đầu vào.

**Tưởng mọi parallel stream cải thiện hiệu năng:** `distinct` ordered cần bảo toàn lần xuất hiện đầu tiên, `sorted` cần phối hợp/gộp dữ liệu; song song có thể chậm hơn và tiêu thụ thêm bộ nhớ.

**Lạm dụng side effect để đo pipeline:** `peek(System.out::println)` không phải công cụ đo ổn định; optimizer có thể bỏ qua traversal khi kết quả terminal cho phép. Hãy dùng các phép đo chuẩn, heap profiler/JFR hoặc JMH nếu cần kết luận hiệu năng.

**Sửa nguồn trong lúc xử lý:** non-interference là nguyên tắc quan trọng. Đừng thêm/xóa phần tử của `List` đang được Stream duyệt; tránh mutate các khóa tham gia comparator/`equals` khi sort/dedup đang chạy.

**Giả định có thể thay đổi kết quả `toList()`:** từ Java 16, `Stream.toList()` trả list không hỗ trợ sửa. Nếu cần sửa tiếp, tạo `new ArrayList<>(stream.toList())`.

**Đánh đồng việc sort với ổn định đầu ra:** nguồn unordered không cam kết thứ tự ban đầu, nên đừng yêu cầu "giữ phần tử đầu" từ `distinct` mà không có encounter order có ý nghĩa.

## 11. Checklist áp dụng

1. Xác định kích thước nguồn `n`, dữ liệu hữu hạn hay có thể vô hạn; có cần toàn bộ dữ liệu hay chỉ mẫu hữu hạn?
2. Ước lượng tỷ lệ qua filter và số khóa phân biệt `u`: nếu `u≈n`, `distinct` có thể giữ trạng thái lớn.
3. Kiểm tra ngữ nghĩa khi đặt `filter`, `distinct`, `sorted` và `limit` theo thứ tự khác nhau; không tối ưu bằng cách thay đổi đáp án.
4. Xem yêu cầu có cần **encounter order**, **stable sort** hoặc "bản ghi đầu tiên" không. Nếu không cần, nguồn unordered có thể cho phép một số tối ưu.
5. Đối với pipeline song song, chỉ chọn khi có benchmark đại diện; không trông chờ stateful steps luôn phân tán hiệu quả.
6. Nếu cần top-k với k nhỏ, xét priority queue thay vì sort toàn bộ; nếu cần dedup không giới hạn, xác định chính sách window/batch/external state.
7. Kiểm thử dữ liệu nhiều trùng và gần như không trùng, nguồn lớn, comparators có khóa ngang nhau, và đầu vào có thứ tự/không có thứ tự.

**Tóm lại:** `sorted()` giữ trạng thái để tạo thứ tự và thường cần bộ nhớ tỷ lệ số phần tử phải sắp; `distinct()` giữ thông tin khóa đã gặp, nên chi phí phụ thuộc số giá trị phân biệt. Đây đều là intermediate operations lazy khi xây pipeline nhưng có thể rất đắt khi terminal yêu cầu kết quả. Muốn giảm chi phí, hãy đưa dữ liệu không cần ra khỏi pipeline sớm, đặt giới hạn đúng vị trí, tận dụng hợp đồng về thứ tự, và dùng thuật toán chuyên biệt nếu yêu cầu là top-k hoặc dedup quy mô lớn.