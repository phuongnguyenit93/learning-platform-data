# Phần tử đồng hạng, tính ổn định và khóa phụ

## 1. Bài toán: cùng mức ưu tiên thì ai đi trước?

Một hệ thống nhận ba công việc A, B, C theo đúng thứ tự đó. Cả ba có mức ưu tiên 2. Khi dùng `PriorityQueue`, người viết chương trình có thể mong đợi A rồi B rồi C được lấy ra, vì không có khác biệt về mức ưu tiên.

Nhưng mong đợi ấy chưa có trong quy tắc so sánh.

Nếu comparator chỉ xét mức ưu tiên, nó chỉ nói rằng A, B, C **đồng hạng**. Nó chưa nói phải chọn ai trước trong nhóm đó. `PriorityQueue` không tự bổ sung quy tắc “đến trước thì đi trước” cho những phần tử đồng hạng.

Bài này giải quyết ba câu hỏi:

- Khi nào hai phần tử được coi là đồng hạng?
- Vì sao hàng đợi ưu tiên không mặc nhiên ổn định?
- Làm thế nào dùng khóa phụ để có thứ tự đến trước trong từng nhóm ưu tiên?

Mục tiêu là viết được một quy tắc chọn đầu đầy đủ và kiểm chứng được nó. Các ví dụ dùng Java 17+, chạy trong một luồng và giữ khóa so sánh không đổi khi phần tử đang nằm trong hàng đợi.

## 2. Đồng hạng được xác định bởi phép so sánh

### 2.1. compare bằng 0 có nghĩa gì?

Giả sử một công việc có tên và mức ưu tiên. Quy ước của ví dụ là số ưu tiên nhỏ hơn được làm trước:

```java
// Các khai báo minh họa đặt trong một lớp:
record Job(String name, int priority) {}

Comparator<Job> byPriority = Comparator.comparingInt(Job::priority);
```

Cần import `java.util.Comparator`. Với `Job("A", 2)` và `Job("B", 2)`, comparator trả 0 vì nó chỉ đọc trường `priority`.

Bốn công việc có thể được chia thành nhóm:

| Công việc | Mức ưu tiên | Quan hệ do comparator quyết định |
| --- | --- | --- |
| urgent | 1 | Đứng trước mọi công việc mức 2 |
| A | 2 | Đồng hạng với B và C |
| B | 2 | Đồng hạng với A và C |
| C | 2 | Đồng hạng với A và B |

Trong nhóm mức 2, comparator hiện tại không chọn A, B hay C trước. Thứ tự các nhóm được xác định; thứ tự bên trong nhóm chưa được phân biệt.

Nếu dùng thứ tự tự nhiên qua `Comparable`, quan hệ đồng hạng tương tự đến từ `compareTo(...) == 0`. Nó không bắt buộc phải đến từ một comparator truyền riêng.

### 2.2. Đồng hạng không nhất thiết là bằng nhau theo equals

Hai Job có tên khác nhau nhưng cùng priority có thể thỏa:

```text
compare(A, B) == 0
A.equals(B) == false
```

Record `Job` mặc định xét cả `name` và `priority` trong phép bằng. Comparator ở trên chỉ xét một trường. Hai quan hệ phục vụ hai câu hỏi khác nhau:

| Quan hệ | Câu hỏi |
| --- | --- |
| `compare(a, b) == 0` | Hai phần tử có cùng hạng theo quy tắc thứ tự này không? |
| `a.equals(b)` | Hai đối tượng có bằng nhau theo mô hình dữ liệu không? |
| `a == b` | Hai tham chiếu có trỏ tới cùng đối tượng không? |

Không thay thế ba câu hỏi cho nhau.

Với `PriorityQueue`, đồng hạng không có nghĩa phần tử thứ hai bị loại bỏ. Hàng đợi vẫn có thể chứa nhiều đối tượng cùng hạng, nhiều đối tượng bằng nhau, hoặc nhiều lần xuất hiện của cùng một tham chiếu.

### 2.3. Tìm/xóa theo đối tượng còn dùng phép bằng

`contains(Object)` và `remove(Object)` tìm theo phép bằng của đối tượng. Chúng không dùng “cùng mức ưu tiên” làm định nghĩa của việc tìm thấy.

Nếu hàng đợi có A mức 2, tìm một Job X mức 2 chưa chắc trả `true`. Nếu Job bằng nhau theo cả tên và mức, X khác A nên không khớp.

Hợp đồng của lớp về đồng hạng, giữ phần tử và các thao tác theo đối tượng được mô tả trong [PriorityQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).

## 3. Tính ổn định: giữ thứ tự tương đối giữa các phần tử đồng hạng

### 3.1. Ổn định là một yêu cầu bổ sung

Trong ngữ cảnh này, mong muốn “ổn định” là: nếu hai lần gửi công việc có cùng mức ưu tiên, lần được tiếp nhận trước phải được lấy trước.

Ví dụ thêm theo thứ tự:

```text
A mức 2 → urgent mức 1 → B mức 2 → C mức 2
```

Một thứ tự lấy đáp ứng ưu tiên và FIFO trong nhóm là:

```text
urgent → A → B → C
```

Đây không phải FIFO toàn hàng đợi: urgent đến sau A nhưng vẫn được làm trước vì mức ưu tiên tốt hơn. Tính đến trước chỉ phân xử những phần tử hòa theo tiêu chí chính.

### 3.2. PriorityQueue không cam kết giữ FIFO trong nhóm

Nếu có nhiều phần tử cùng là nhỏ nhất theo thứ tự đang dùng, đầu hàng đợi có thể là một trong số đó. Không có bảo đảm chọn theo thứ tự chèn.

Một vài dữ liệu có thể vẫn cho kết quả đúng thứ tự đến. Điều đó chỉ cho thấy lần chạy ấy phù hợp, không chứng minh hàng đợi có hợp đồng ổn định.

Cũng không nên đổi phát biểu thành “PriorityQueue luôn đảo thứ tự đồng hạng” hoặc “luôn ngẫu nhiên”. Cả hai đều là những quy tắc không được lớp cam kết.

### 3.3. Vì sao heap có thể thay vị trí các phần tử hòa?

Một mô hình heap với ba công việc cùng mức:

```text
        A:2
       /   \
     B:2   C:2
```

Sau khi lấy A, một cách duy trì heap đưa phần tử cuối C lên gốc:

```text
        C:2
       /
     B:2
```

Vì C và B so sánh bằng 0, tính chất heap vẫn đúng. Heap không có thông tin rằng B được thêm trước C, nên không có điều kiện bắt buộc phải đổi C xuống dưới B.

Một cách xử lý hợp lệ vì thế có thể lấy A, C, B. Đây là minh họa vì sao bất biến heap và ổn định theo lịch sử chèn là hai yêu cầu khác nhau; không phải một lời hứa về bố trí mà mọi JDK phải dùng.

## 4. Chương trình quan sát: đồng hạng vẫn có thể đổi thứ tự

Lưu thành **EqualPriorityObservation.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class EqualPriorityObservation {
    record Job(String name, int priority) {}

    private static List<String> pollNames(PriorityQueue<Job> queue) {
        List<String> names = new ArrayList<>();
        while (!queue.isEmpty()) {
            names.add(queue.poll().name());
        }
        return names;
    }

    public static void main(String[] args) {
        Comparator<Job> byPriority = Comparator.comparingInt(Job::priority);
        Job a = new Job("A", 2);
        Job b = new Job("B", 2);
        Job c = new Job("C", 2);

        System.out.println("compare A and B: " + byPriority.compare(a, b));
        System.out.println("A equals B: " + a.equals(b));

        PriorityQueue<Job> observation = new PriorityQueue<>(byPriority);
        observation.addAll(List.of(a, b, c));
        System.out.println("inserted names: [A, B, C]");
        System.out.println("observed tied poll order: " + pollNames(observation));

        PriorityQueue<Job> lookup = new PriorityQueue<>(byPriority);
        lookup.addAll(List.of(a, b, c));
        System.out.println("size with three ties: " + lookup.size());
        System.out.println("contains equal B: " + lookup.contains(new Job("B", 2)));
        System.out.println("contains same-priority X: " + lookup.contains(new Job("X", 2)));
        System.out.println("remove same-priority X: " + lookup.remove(new Job("X", 2)));
        System.out.println("remove equal B: " + lookup.remove(new Job("B", 2)));
        System.out.println("size after removing B: " + lookup.size());

        PriorityQueue<Job> duplicates = new PriorityQueue<>(byPriority);
        duplicates.offer(a);
        duplicates.offer(a);
        System.out.println("same reference twice size: " + duplicates.size());
        System.out.println("same reference twice names: " + pollNames(duplicates));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 EqualPriorityObservation.java
java EqualPriorityObservation
```

Chương trình đã được biên dịch bằng `--release 17` và chạy trên OpenJDK 24.0.2. Stdout quan sát được:

```text
compare A and B: 0
A equals B: false
inserted names: [A, B, C]
observed tied poll order: [A, C, B]
size with three ties: 3
contains equal B: true
contains same-priority X: false
remove same-priority X: false
remove equal B: true
size after removing B: 2
same reference twice size: 2
same reference twice names: [A, A]
```

Dòng `observed tied poll order` ghi kết quả thực tế trên môi trường đó, không phải thứ tự cố định mà API bảo đảm trên mọi Java 17+. Cờ `--release 17` kiểm tra ngôn ngữ/API mục tiêu và tạo bytecode tương ứng; JVM chạy ví dụ vẫn là bản đã nêu.

Kết quả cần hiểu:

- A và B đồng hạng nhưng không bằng nhau theo record.
- Cả ba phần tử đồng hạng đều được giữ.
- Thứ tự quan sát A, C, B là một phản ví dụ cho giả định FIFO tự động.
- Tạo lại một Job bằng B vẫn tìm/xóa được B.
- Tạo một Job khác tên nhưng cùng priority không làm `contains` hay `remove` coi là có.
- Thêm cùng một tham chiếu hai lần tạo hai lần xuất hiện, không tự loại trùng.

Không dùng kiểm thử yêu cầu chính xác A, C, B để mô tả hợp đồng của PriorityQueue. Khi chưa có tiêu chí phụ, thứ tự danh tính của nhóm đồng hạng chưa được quy định.

## 5. Khóa phụ biến yêu cầu ngầm thành quy tắc tường minh

### 5.1. Từ một khóa thành một bộ khóa

Nếu cần FIFO trong nhóm, cấp cho mỗi lần tiếp nhận một số thứ tự tăng dần:

```text
khóa của một lần gửi = (mức ưu tiên, số thứ tự tiếp nhận)
```

So sánh theo thứ tự từ trái sang phải:

1. Nếu mức ưu tiên khác nhau, dùng mức ưu tiên để chọn.
2. Nếu mức ưu tiên bằng nhau, dùng số thứ tự.
3. Chỉ hòa hoàn toàn nếu mọi tiêu chí đang xét đều hòa.

Ví dụ:

| Lần gửi | Mức ưu tiên | Số thứ tự | Thứ tự lấy mong đợi |
| --- | --- | --- | --- |
| A | 2 | 0 | Sau urgent, trước B |
| urgent | 1 | 1 | Đầu tiên |
| B | 2 | 2 | Sau A, trước C |
| C | 2 | 3 | Cuối cùng trong nhóm mức 2 |

Các khóa `(2,0)`, `(1,1)`, `(2,2)`, `(2,3)` cho thứ tự `(1,1)`, `(2,0)`, `(2,2)`, `(2,3)`.

Khi số thứ tự đủ phân biệt các lần gửi còn trong hàng đợi, hai lần gửi cùng mức không còn đồng hạng theo **comparator hoàn chỉnh** nữa. Heap không cần tự nhớ lịch sử; lịch sử cần thiết đã trở thành một phần của khóa.

### 5.2. Cách ghép bằng thenComparingLong

Một mô hình dữ liệu trực tiếp:

```java
// Các khai báo minh họa đặt trong một lớp:
record QueuedJob(String name, int priority, long receivedOrder) {}

Comparator<QueuedJob> order =
        Comparator.comparingInt(QueuedJob::priority)
                  .thenComparingLong(QueuedJob::receivedOrder);
```

`thenComparingLong` chỉ được dùng khi tiêu chí trước hòa. Không phải cộng hai giá trị thành một điểm tổng.

Chẳng hạn, không viết `priority + receivedOrder` rồi so vì một số thứ tự lớn có thể làm đảo quyết định về mức ưu tiên. Quy tắc “ưu tiên là chính, số thứ tự chỉ phân xử hòa” phải được giữ bằng cách so lần lượt từng khóa.

### 5.3. Đảo chiều đúng tiêu chí

Nếu số ưu tiên lớn hơn được làm trước, nhưng số thứ tự nhỏ hơn vẫn được làm trước khi hòa:

```java
Comparator<QueuedJob> higherPriorityFirst =
        Comparator.comparingInt(QueuedJob::priority)
                  .reversed()
                  .thenComparingLong(QueuedJob::receivedOrder);
```

Nếu viết:

```java
// Khác yêu cầu: đảo cả thứ tự tiếp nhận.
Comparator<QueuedJob> reversedEverything =
        Comparator.comparingInt(QueuedJob::priority)
                  .thenComparingLong(QueuedJob::receivedOrder)
                  .reversed();
```

thì cả tiêu chí phụ cũng bị đảo. Trong nhóm cùng priority, lần có số thứ tự lớn hơn sẽ đi trước.

Quy tắc dấu, tính bắc cầu và ghép tiêu chí được mô tả trong [Comparator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

## 6. Đặt số thứ tự ở công việc hay ở lần gửi?

### 6.1. Một đối tượng có thể được gửi nhiều lần

Nếu gắn một số thứ tự cố định vào chính công việc rồi thêm lại cùng đối tượng, hai lần xuất hiện có thể dùng cùng khóa phụ. Khi đó chúng lại hòa theo comparator hoàn chỉnh.

Câu hỏi cần trả lời là: đang xếp các **công việc** hay xếp các **lần tiếp nhận công việc**?

Đối với FIFO trong nhóm theo lần tiếp nhận, số thứ tự thường thuộc về một bản ghi bao ngoài:

```text
Entry {
    value: công việc,
    sequence: số của lần tiếp nhận này
}
```

Cùng một `value` có thể xuất hiện trong nhiều Entry, mỗi Entry có sequence khác nhau. Cấu trúc dữ liệu không tự loại bỏ các lần gửi lại chỉ vì payload giống nhau.

### 6.2. Thời điểm cấp số là một phần của hợp đồng

Trong ví dụ một luồng, mỗi lời gọi `offer` hợp lệ cấp số kế tiếp ngay khi tiếp nhận công việc. Vì mọi lời gọi diễn ra nối tiếp, số nhỏ hơn tương ứng với lần tiếp nhận trước.

Nếu ứng dụng cấp số từ một danh sách công việc đã bị sắp xếp trước đó, số ấy mô tả thứ tự đang duyệt danh sách, không tự khôi phục lịch sử gốc đã mất.

Nếu dữ liệu được tải lại từ nơi lưu trữ, cần xác định muốn giữ số tiếp nhận cũ hay coi việc tải lại là những lần tiếp nhận mới. Không đặt một tên trường `sequence` rồi mặc nhiên coi nó có mọi ý nghĩa thời gian cần thiết.

## 7. Chương trình chạy: bao công việc bằng khóa thứ tự tiếp nhận

Lưu thành **StablePriorityQueueDemo.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;

public class StablePriorityQueueDemo {
    record Job(String name, int priority) {}
    private record Entry<E>(E value, long sequence) {}

    static final class StableQueue<E> {
        private final PriorityQueue<Entry<E>> entries;
        private long nextSequence;

        StableQueue(Comparator<? super E> byPriority) {
            Objects.requireNonNull(byPriority);
            entries = new PriorityQueue<>((left, right) -> {
                int result = byPriority.compare(left.value(), right.value());
                return result != 0
                        ? result
                        : Long.compare(left.sequence(), right.sequence());
            });
        }

        void offer(E value) {
            Objects.requireNonNull(value);
            if (nextSequence == Long.MAX_VALUE) {
                throw new IllegalStateException("sequence exhausted");
            }
            entries.offer(new Entry<>(value, nextSequence));
            nextSequence++;
        }

        E peek() {
            Entry<E> head = entries.peek();
            return head == null ? null : head.value();
        }

        E poll() {
            Entry<E> head = entries.poll();
            return head == null ? null : head.value();
        }

        int size() {
            return entries.size();
        }

        boolean isEmpty() {
            return entries.isEmpty();
        }
    }

    private static List<String> pollNames(StableQueue<Job> queue) {
        List<String> result = new ArrayList<>();
        while (!queue.isEmpty()) {
            result.add(queue.poll().name());
        }
        return result;
    }

    public static void main(String[] args) {
        StableQueue<Job> queue =
                new StableQueue<>(Comparator.comparingInt(Job::priority));
        queue.offer(new Job("slow-A", 3));
        queue.offer(new Job("urgent-A", 1));
        queue.offer(new Job("normal", 2));
        queue.offer(new Job("urgent-B", 1));
        queue.offer(new Job("slow-B", 3));
        queue.offer(new Job("urgent-C", 1));

        System.out.println("size: " + queue.size());
        System.out.println("head: " + queue.peek().name());
        System.out.println("stable poll names: " + pollNames(queue));

        Job a = new Job("A", 1);
        queue.offer(a);
        queue.offer(new Job("B", 1));
        System.out.println("removed before resubmit: " + queue.poll().name());
        queue.offer(a);
        System.out.println("after resubmit names: " + pollNames(queue));

        queue.offer(a);
        queue.offer(a);
        System.out.println("duplicate payload size: " + queue.size());
        System.out.println("duplicate payload names: " + pollNames(queue));
        System.out.println("empty peek: " + queue.peek());
        System.out.println("empty poll: " + queue.poll());
    }
}
```

Lệnh chạy:

```shell
javac --release 17 -encoding UTF-8 StablePriorityQueueDemo.java
java StablePriorityQueueDemo
```

Stdout chính xác:

```text
size: 6
head: urgent-A
stable poll names: [urgent-A, urgent-B, urgent-C, normal, slow-A, slow-B]
removed before resubmit: A
after resubmit names: [B, A]
duplicate payload size: 2
duplicate payload names: [A, A]
empty peek: null
empty poll: null
```

`StableQueue` trong ví dụ là một lớp nhỏ minh họa chính sách một luồng, không triển khai toàn bộ giao diện `Queue`. Những phương thức nó có đều thể hiện mục tiêu: tiếp nhận, xem/lấy đầu và kiểm tra kích thước.

Phần bao Entry giải quyết việc thứ tự thuộc về **lần gửi**, còn Job giữ dữ liệu công việc. Comparator của Entry trước tiên ủy quyền so mức ưu tiên cho `byPriority`; nếu hòa mới so sequence.

`Objects.requireNonNull` từ chối payload null. Do đó null từ `peek()` hoặc `poll()` biểu thị hàng đợi rỗng, không lẫn với một công việc null đang chờ.

Mã chặn việc tiếp nhận khi số kế tiếp bằng `Long.MAX_VALUE`, trước khi bộ đếm có thể quay vòng. Chính sách này cố ý không sử dụng giá trị cuối đó; nó chọn báo hết dải số thay vì âm thầm tạo khóa thứ tự sai.

## 8. Đọc từng nhóm trong kết quả

Sáu lời gọi đầu tiên cấp số:

| Công việc | Priority | Sequence | Khóa so sánh |
| --- | --- | --- | --- |
| slow-A | 3 | 0 | `(3,0)` |
| urgent-A | 1 | 1 | `(1,1)` |
| normal | 2 | 2 | `(2,2)` |
| urgent-B | 1 | 3 | `(1,3)` |
| slow-B | 3 | 4 | `(3,4)` |
| urgent-C | 1 | 5 | `(1,5)` |

Khi lấy ra:

```text
Nhóm priority 1: urgent-A → urgent-B → urgent-C
Nhóm priority 2: normal
Nhóm priority 3: slow-A → slow-B
```

slow-A được gửi đầu tiên nhưng không đứng đầu toàn hàng đợi, vì priority 3 kém ưu tiên hơn 1 và 2 theo quy ước này. Trong nhóm priority 3, slow-A vẫn đứng trước slow-B.

Đoạn gửi lại A thể hiện một chính sách khác cần nói rõ:

```text
tiếp nhận A → tiếp nhận B → lấy A → tiếp nhận A lần mới
```

Sau đó B phải đi trước lần A mới, nên kết quả là `[B, A]`. Đối tượng A có thể vẫn là cùng tham chiếu, nhưng Entry mới nhận sequence mới.

Lớp không đặt bộ đếm về 0 mỗi khi hàng đợi rỗng. Điều này giúp mô hình tiếp nhận đơn giản, không phải quản lý lại sự trùng số. Nếu một thiết kế khác muốn tái sử dụng số, nó phải bảo đảm không tạo khóa đụng với các lần gửi vẫn còn liên quan.

## 9. Chọn khóa phụ đúng ý nghĩa nghiệp vụ

### 9.1. Một khóa phụ không nhất thiết mang nghĩa FIFO

| Khóa phụ | Chính sách nó có thể diễn đạt | Có tự bảo đảm FIFO không? |
| --- | --- | --- |
| Số thứ tự tiếp nhận tăng dần | Đến trước trong cùng nhóm | Có, nếu cấp số đúng và đủ phân biệt |
| Hạn chót | Việc đến hạn sớm hơn trong cùng nhóm | Không nhất thiết |
| Tên công việc | Thứ tự từ vựng của tên | Không |
| Mã duy nhất | Một thứ tự xác định theo mã | Không nhất thiết |
| Dấu thời gian | Thứ tự theo giá trị thời gian được ghi | Chưa đủ nếu trùng hoặc không theo thứ tự tiếp nhận |

Khóa phụ giúp chọn người thắng khi tiêu chí trước hòa. Việc chọn khóa nào là một quyết định nghiệp vụ, không phải mẹo kỹ thuật có một đáp án cho mọi ứng dụng.

Một mã duy nhất giúp phân biệt hai công việc nhưng không tự nói công việc nào đến trước. Một dấu thời gian có thể trùng nhau giữa nhiều lần gửi; nguồn thời gian cũng có thể có giới hạn độ phân giải hoặc điều chỉnh.

Nếu nghiệp vụ thật sự yêu cầu “ưu tiên, sau đó hạn chót, cuối cùng thứ tự đến”, comparator phải xét đúng ba tiêu chí theo thứ tự ấy. Sequence lúc này chỉ phân xử khi cả ưu tiên và hạn chót đều hòa.

### 9.2. Vẫn có thể hòa ở tiêu chí cuối

Hai Entry có cùng priority và cùng sequence vẫn có thể so sánh bằng 0. Tên gọi “khóa phụ” không tự làm khóa trở thành duy nhất.

Nếu yêu cầu là thứ tự xác định giữa mọi lần gửi còn trong hàng đợi, cần một tiêu chí cuối đủ phân biệt hoặc một chính sách rõ ràng cho phần còn hòa. Ví dụ StableQueue làm điều đó bằng sequence không lặp trong các lời gọi được chấp nhận.

Không dùng số ngẫu nhiên để diễn đạt “đến trước”. Không dùng `System.identityHashCode` như thể nó là lịch sử tiếp nhận hoặc một mã chắc chắn không trùng. Hai giá trị đó không mang hợp đồng FIFO mà ứng dụng cần.

### 9.3. Giữ khóa ổn định khi đang chờ

Nếu priority hoặc sequence được đổi trực tiếp sau khi Entry đã nằm trong heap, vị trí hiện tại có thể không còn phù hợp. Hàng đợi không theo dõi mọi phép gán trường để tự sửa cấu trúc.

Hãy dùng dữ liệu khóa bất biến hoặc cập nhật qua một quy trình lấy/xóa phần tử cũ rồi thêm giá trị mới. Việc đổi ưu tiên còn đặt ra câu hỏi: giữ thứ tự tiếp nhận ban đầu hay cấp số mới? Cả hai có thể hợp lệ trong những nghiệp vụ khác nhau, nhưng phải chọn rõ.

Trong ví dụ, record Entry giữ sequence bất biến; Job chứa String và int cũng không đổi. Một payload khác có trường thay đổi được vẫn cần quy tắc riêng nếu comparator đọc trường ấy.

## 10. Comparator phải là một quy tắc nhất quán

### 10.1. Không tạo khóa phụ bằng phép trừ rồi ép kiểu

Ví dụ cần tránh khi sequence là long:

```java
// Ví dụ sai về cách so sánh:
int result = (int) (left.sequence() - right.sequence());
```

Phép trừ có thể tràn; ép từ long xuống int còn có thể mất thông tin. Khoảng cách lớn không liên quan đến yêu cầu chọn dấu so sánh.

Dùng:

```java
int result = Long.compare(left.sequence(), right.sequence());
```

Với priority kiểu int, dùng `Integer.compare` hoặc `Comparator.comparingInt`. Không viết `a.priority() - b.priority()` nếu muốn quy tắc đúng trên toàn miền int.

### 10.2. Không tính thứ tự phụ dựa trên trạng thái thay đổi mỗi lần gọi

Một comparator phải cho quan hệ nhất quán trong thời gian các khóa đang có hiệu lực. Những cách như “nếu hòa thì tăng bộ đếm ngay trong compare” hoặc “nếu hòa thì chọn ngẫu nhiên” không mã hóa lịch sử tiếp nhận.

Comparator có thể được gọi nhiều lần cho cùng cặp, ở các thời điểm và hướng khác nhau. Tạo sequence trong `offer`, lưu nó vào Entry, rồi chỉ đọc trong `compare`. Không tạo một sequence mới mỗi lần hai phần tử được so.

Nếu comparator không có tính bắc cầu hoặc không đảo dấu phù hợp khi đổi hai đối số, heap không có một thứ tự hợp lệ để duy trì. Thêm nhiều khóa không sửa được một quy tắc so sánh vốn mâu thuẫn.

## 11. Sort ổn định và PriorityQueue ổn định là hai hợp đồng khác nhau

`List.sort` có hợp đồng sắp xếp ổn định: các phần tử comparator coi là hòa giữ thứ tự tương đối của đầu vào. Xem [List.sort Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

Nhưng nếu đầu vào danh sách lấy từ iterator của PriorityQueue, thứ tự đó không được cam kết là lịch sử tiếp nhận. Sort ổn định chỉ giữ được thứ tự đầu vào nó nhìn thấy; nó không khôi phục lịch sử đã không được lưu.

Ví dụ:

```text
Lịch sử tiếp nhận:             A, B, C
Danh sách đầu vào một lần đọc: A, C, B
Cả ba có cùng priority
Sort ổn định chỉ theo priority:
                              A, C, B
```

Không có mâu thuẫn: phép sort đã ổn định đối với danh sách đầu vào, còn danh sách ấy không diễn đạt FIFO mong muốn.

Khi dùng khóa phụ sequence, lấy đầu bằng `poll()` cho thứ tự phù hợp. Một danh sách được sort bằng cùng comparator hoàn chỉnh cũng có cùng thứ tự đối với những Entry có khóa đủ phân biệt.

Iterator của PriorityQueue vẫn không tự duyệt theo ưu tiên sau khi đã thêm sequence. Khóa phụ sửa quy tắc chọn đầu, không thay đổi hợp đồng của iterator. Nếu cần xem theo thứ tự lấy, hãy sao chép rồi poll hoặc tạo danh sách và sort bằng đúng comparator.

## 12. Một luồng, nhiều luồng và ý nghĩa “đến trước”

Ví dụ StableQueue dùng bộ đếm long thông thường và PriorityQueue thông thường. Nó được thiết kế cho một luồng. Thay bộ đếm bằng `AtomicLong` không tự làm PriorityQueue trở thành an toàn cho nhiều luồng.

Ngay cả khi dùng một cấu trúc hàng đợi đồng thời thích hợp, cần nói rõ thứ tự nào được ghi nhận. Ví dụ:

```text
Luồng A lấy sequence 10 rồi bị tạm dừng.
Luồng B lấy sequence 11 và thêm vào hàng đợi trước.
Luồng A mới thêm sequence 10 sau đó.
```

Thứ tự cấp số là A trước B; thứ tự hoàn thành thao tác thêm là B trước A. Không được gọi cả hai là cùng một “thứ tự đến” mà không định nghĩa điểm tiếp nhận.

Nếu B đã được lấy ra trước khi A thực sự xuất hiện trong hàng đợi, một sequence nhỏ hơn được thêm sau không thể làm lại phần xử lý đã xảy ra. Quy tắc ưu tiên áp dụng trên các phần tử hiện đang chờ, không sắp xếp lại quá khứ.

`PriorityBlockingQueue` cũng không mặc định bảo đảm thứ tự giữa các phần tử bằng mức; tài liệu của nó gợi ý dùng một khóa phụ khi cần phân xử. Xem [PriorityBlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html).

Thiết kế tiếp nhận đồng thời cần chọn điểm ghi nhận thứ tự và cơ chế đồng bộ phù hợp. Phần này nêu ranh giới của ví dụ; không coi lớp StableQueue một luồng là một bộ lập lịch đồng thời hoàn chỉnh.

## 13. Kiểm thử điều cần bảo đảm

### 13.1. Khi chỉ có comparator ưu tiên

Đừng yêu cầu một thứ tự danh tính cụ thể cho nhóm hòa. Có thể kiểm tra:

- Mức ưu tiên lấy ra không đi ngược quy tắc.
- Không mất hoặc tự sinh thêm lần xuất hiện.
- Những phần tử khác nhóm tuân theo tiêu chí chính.
- Các thao tác tìm/xóa theo đối tượng dùng đúng mô hình bằng nhau.

Thấy A, B, C trên một lần chạy không đủ chứng minh ổn định; thấy A, C, B cũng không có nghĩa dữ liệu bị hỏng.

### 13.2. Khi đã có sequence

Có thể kiểm tra mạnh hơn:

- Trong cùng priority, sequence lấy ra tăng theo chính sách đã chọn.
- Priority vẫn là tiêu chí chính, sequence không lấn át nó.
- Mỗi lần gửi mới nhận khóa phụ phù hợp, kể cả cùng payload.
- Gửi lại một công việc có hành vi đúng với quy tắc giữ số cũ hay cấp số mới.
- Trường hợp tất cả đồng hạng vẫn giữ thứ tự tiếp nhận.
- Dữ liệu gần giới hạn số không làm comparator đổi dấu sai.

Các trường hợp biên hữu ích gồm hàng đợi rỗng, một phần tử, nhiều phần tử cùng mức, nhiều mức đan xen, gửi cùng tham chiếu nhiều lần và lấy ra rồi gửi lại.

Một lớp bao có thể che Entry để mã gọi chỉ nhìn payload; khi kiểm thử tính ổn định, có thể dùng các nhãn riêng cho từng lần gửi để biết chúng có được lấy đúng thứ tự hay không. Payload giống hệt nhau không giúp quan sát danh tính các lần xuất hiện chỉ qua chuỗi in ra.

## 14. Lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Cho rằng cùng ưu tiên tự FIFO | Comparator chưa ghi lịch sử chèn | Thêm khóa tiếp nhận |
| Cho rằng compare bằng 0 sẽ loại phần tử sau | PriorityQueue không phải tập hợp | Phân biệt hòa thứ tự với loại trùng |
| Dùng equals để dự đoán ai đứng đầu | Equals không quyết định thứ tự heap | Đọc comparator hoàn chỉnh |
| Gắn cùng sequence cho hai lần gửi | Hai lần vẫn có thể hòa | Cấp khóa cho lần tiếp nhận |
| Dùng timestamp như khóa chắc chắn duy nhất | Dấu thời gian có thể trùng | Có tiêu chí cuối đủ phân biệt |
| Cộng priority với sequence | Tiêu chí phụ có thể lấn tiêu chí chính | So lần lượt bằng thenComparing |
| Đảo cả comparator ghép | Đảo luôn thứ tự FIFO trong nhóm | Đảo đúng tiêu chí cần đảo |
| Tạo sequence bên trong compare | Kết quả phụ thuộc số lần so sánh | Cấp số khi tiếp nhận và giữ bất biến |
| Ép chênh lệch long sang int | Mất dấu hoặc mất thông tin | Dùng Long.compare |
| Sort ổn định từ iterator để phục hồi FIFO | Lịch sử đến không nằm trong iterator | Lưu sequence ngay từ nguồn |
| Thêm AtomicLong rồi chia sẻ PriorityQueue | Bộ đếm và cấu trúc có yêu cầu đồng bộ riêng | Thiết kế tiếp nhận đồng thời rõ ràng |

## 15. Bài tập tự kiểm tra có lời giải

### Bài 1: Ba quan hệ

A và B là hai record Job khác tên, cùng priority 2. Comparator chỉ xét priority. `compare(A,B)`, `A.equals(B)` và `A == B` có thể lần lượt là gì?

**Lời giải:** 0, false, false. Đồng hạng không có nghĩa bằng toàn bộ dữ liệu hay cùng tham chiếu. PriorityQueue vẫn có thể chứa cả hai.

### Bài 2: Chọn đầu trong nhóm hòa

Thêm A, B, C cùng mức vào PriorityQueue chỉ so priority. Một lần chạy lấy A, C, B. Đây có phải vi phạm API không?

**Lời giải:** không. Cả ba đồng hạng và lớp không cam kết FIFO trong nhóm. Cũng không được biến kết quả này thành một thứ tự cố định cho mọi lần chạy.

### Bài 3: So bộ khóa

Các lần gửi có khóa `A=(2,0)`, `B=(1,1)`, `C=(2,2)`, `D=(1,3)`. Số priority nhỏ hơn đi trước; khi hòa, sequence nhỏ hơn đi trước. Thứ tự lấy là gì?

**Lời giải:** B, D, A, C. Tiêu chí chính chọn nhóm priority 1 trước; trong nhóm ấy 1 trước 3. Sau đó nhóm priority 2 có 0 trước 2.

### Bài 4: Đảo chiều

Cần priority lớn trước và sequence nhỏ trước. Hai cách “đảo priority rồi ghép sequence” và “ghép cả hai rồi đảo” có tương đương không?

**Lời giải:** không. Cách sau đảo cả sequence, nên trong cùng priority sẽ lấy lần có số lớn hơn trước. Phải đảo tiêu chí priority trước khi ghép sequence tăng dần.

### Bài 5: Gửi lại cùng đối tượng

A và B cùng mức, được tiếp nhận theo thứ tự A rồi B. Lấy A ra, sau đó gửi lại A bằng lớp StableQueue của bài. Ai đi trước tiếp theo?

**Lời giải:** B. Lần gửi lại A có Entry và sequence mới. Nếu nghiệp vụ muốn giữ tuổi chờ cũ, đó là một chính sách khác phải được thiết kế riêng.

### Bài 6: Khóa phụ là tên

Dùng `thenComparing(Job::name)` có tạo FIFO trong nhóm không?

**Lời giải:** không. Nó tạo thứ tự theo tên khi priority hòa. A có thể đứng trước B vì tên, dù B đến trước. Nếu muốn FIFO, khóa phụ phải ghi nhận thứ tự tiếp nhận.

### Bài 7: Sort ổn định

Danh sách được đọc từ một PriorityQueue có thứ tự A, C, B; cả ba cùng priority. Sort ổn định chỉ theo priority có bắt buộc trả A, B, C không?

**Lời giải:** không. Nó giữ A, C, B của đầu vào. Tính ổn định của sort không khôi phục lịch sử chèn vào một cấu trúc khác.

### Bài 8: Hai điểm thứ tự trong nhiều luồng

A được cấp số 10 nhưng chưa thêm vào hàng đợi. B được cấp 11 và thêm trước. “A đến trước” có phải phát biểu đủ rõ không?

**Lời giải:** chưa đủ. Phải nói đang lấy thứ tự cấp số, thứ tự bắt đầu hay hoàn thành tiếp nhận, hoặc một điểm đồng bộ cụ thể. Khóa phụ chỉ có ý nghĩa khi ứng dụng định nghĩa nó ghi lại thứ tự nào.

## 16. Tài liệu đối chiếu

- [PriorityQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html): hợp đồng hòa ưu tiên và thao tác theo đối tượng.
- [Comparator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): phép so sánh và ghép tiêu chí.
- [List.sort Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)): hợp đồng ổn định của phép sắp xếp danh sách.
- [PriorityBlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html): giới hạn thứ tự giữa các phần tử cùng mức và ý tưởng phân xử bằng khóa phụ.

Muốn có thứ tự cụ thể trong nhóm đồng hạng, hãy ghi dữ liệu phân xử vào khóa và so sánh nó rõ ràng. Với yêu cầu FIFO theo lần tiếp nhận, sequence là lịch sử được lưu lại để comparator sử dụng, không phải một đặc tính tự phát của heap.
