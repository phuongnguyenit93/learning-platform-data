# PriorityQueue và cấu trúc heap ưu tiên

`PriorityQueue<E>` dùng khi cần liên tục lấy phần tử có mức ưu tiên đứng đầu, kể cả khi các phần tử mới được thêm xen kẽ. Nó không cam kết xử lý theo thứ tự đến như một hàng đợi FIFO.

Ý tưởng nền tảng là **heap ưu tiên**: duy trì vừa đủ quan hệ thứ tự để tìm phần tử đứng đầu nhanh, thay vì sắp xếp hoàn chỉnh toàn bộ dữ liệu sau mỗi lần thay đổi.

## 1. Đầu hàng đợi được quyết định bởi quy tắc so sánh

`PriorityQueue` chọn phần tử nhỏ nhất **theo quy tắc so sánh của hàng đợi** làm đầu:

- Không truyền comparator: dùng thứ tự tự nhiên của phần tử.
- Truyền `Comparator`: dùng thứ tự do comparator xác định.

Với `Integer` và thứ tự mặc định, số nhỏ nhất được lấy trước. Nếu comparator đảo thứ tự, số lớn nhất theo giá trị số có thể trở thành phần tử nhỏ nhất theo comparator và được lấy trước.

“Ưu tiên cao” không tự đồng nghĩa với “số lớn”. Nếu số 1 là mức khẩn cấp nhất của hệ thống, comparator tăng dần có thể phù hợp; nếu số 10 là khẩn cấp nhất, có thể cần thứ tự ngược lại.

Các thao tác chính:

| Thao tác | Vai trò |
| --- | --- |
| `offer(e)`, `add(e)` | Thêm một phần tử |
| `peek()` | Xem đầu hàng đợi, không lấy ra; trả null nếu rỗng |
| `poll()` | Lấy và loại bỏ đầu hàng đợi; trả null nếu rỗng |
| `element()`, `remove()` không đối số | Các biến thể báo lỗi khi hàng đợi rỗng |

`PriorityQueue` không cho phép phần tử `null`. Giá trị `null` từ `poll` hoặc `peek` vì thế có thể dùng để nhận biết rỗng.

## 2. Heap không phải một mảng đã sắp xếp

Mô hình heap nhị phân nhỏ nhất (min-heap) có hai thuộc tính:

1. Hình dạng là cây nhị phân hoàn chỉnh: các tầng được lấp từ trên xuống, tầng cuối từ trái sang phải.
2. Giá trị tại mỗi nút cha không lớn hơn các nút con theo comparator.

Ví dụ heap hợp lệ:

```text
        2
       / \
      5   4
     / \
    9   8
```

Quan hệ cần giữ là `2 <= 5`, `2 <= 4`, `5 <= 9`, `5 <= 8`. Không có yêu cầu `5 <= 4` vì hai nút này là anh em, không phải cha–con.

Do mọi đường từ gốc đi xuống đều không giảm theo comparator, gốc là phần tử nhỏ nhất. Nhưng duyệt ngang cây cho dãy `2, 5, 4, 9, 8`, không phải dãy tăng dần.

Đây là khác biệt quyết định:

- **Heap:** bảo đảm phần tử đầu và quan hệ cha–con.
- **Dãy sắp xếp:** bảo đảm quan hệ thứ tự giữa mọi phần tử liên tiếp trong dãy.
- **Cây tìm kiếm nhị phân:** có quy tắc phân vùng trái/phải theo khóa, khác quy tắc heap.

Không áp dụng thuật toán tìm kiếm nhị phân cho mảng heap chỉ vì nó có một phần tính chất thứ tự.

## 3. Biểu diễn cây bằng mảng

Mô hình heap nhị phân thường dùng một mảng liên tiếp thay vì tạo một đối tượng nút cho từng phần tử. OpenJDK 21 triển khai `PriorityQueue` theo hướng này.

Với chỉ số bắt đầu từ 0:

| Vị trí | Công thức |
| --- | --- |
| Gốc | `0` |
| Cha của nút `i > 0` | `(i - 1) / 2`, chia nguyên |
| Con trái | `2 * i + 1` |
| Con phải | `2 * i + 2` |

Cây ở trên có thể được biểu diễn:

```text
index:  0  1  2  3  4
value: [2, 5, 4, 9, 8]
```

Mỗi vị trí con chỉ tồn tại nếu chỉ số nhỏ hơn kích thước hiện tại. Hình dạng cây hoàn chỉnh cho phép tính vị trí liên quan bằng chỉ số.

Cần phân biệt **kích thước** là số phần tử đang chứa với **dung lượng** là số ô mà mảng lưu trữ hiện có. Dung lượng có thể lớn hơn kích thước.

Các hình và mảng trong bài minh họa cơ chế heap. Chương trình sử dụng API không nên phụ thuộc vào một bố cục mảng cụ thể: thứ tự nội bộ không phải kết quả sắp xếp được API cam kết cho người gọi.

## 4. Thêm phần tử: đẩy lên

Giả sử heap đang là `[2, 5, 4, 9, 8]` và cần thêm `1`:

1. Đặt phần tử mới ở vị trí cuối để giữ hình dạng hoàn chỉnh.
2. So sánh nó với cha.
3. Nếu nó nhỏ hơn cha, đưa nó lên và đưa cha xuống.
4. Tiếp tục đến khi cha không lớn hơn nó hoặc đã tới gốc.

Mô phỏng:

```text
Thêm ở cuối:       [2, 5, 4, 9, 8, 1]
1 đi lên qua 4:    [2, 5, 1, 9, 8, 4]
1 đi lên qua 2:    [1, 5, 2, 9, 8, 4]
```

Cơ chế này thường gọi là đẩy lên (`sift up)). Nó chỉ cần đi trên đường từ nút mới đến gốc. Không phải sắp xếp lại toàn bộ mảng.

Chiều cao cây tăng theo bậc `log n`, nên số mức phải kiểm tra tối đa tăng theo `log n`. Chi phí so sánh và di chuyển của thao tác heap tương ứng là `O(log n)`.

## 5. Lấy đầu: đưa phần tử cuối lên và đẩy xuống

Từ heap `[1, 5, 2, 9, 8, 4]`, cần lấy `1`:

1. Ghi nhận gốc làm kết quả.
2. Đưa phần tử cuối `4` vào vị trí gốc và giảm kích thước.
3. So sánh nó với các con; chọn con nhỏ hơn.
4. Nếu nó lớn hơn con đó, đưa nó xuống.
5. Tiếp tục đến khi quan hệ heap được phục hồi.

Mô phỏng:

```text
Bỏ gốc, đưa 4 lên: [4, 5, 2, 9, 8]
Đẩy 4 xuống qua 2: [2, 5, 4, 9, 8]
Kết quả poll: 1
```

Cơ chế này gọi là đẩy xuống (`sift down`). Chọn con nhỏ hơn giúp nút được đưa lên không vi phạm quan hệ với người con còn lại.

Sau mỗi lần `poll`, heap được điều chỉnh. Vì thế, nhiều lần `poll` liên tiếp tạo ra một chuỗi đúng thứ tự ưu tiên, dù bố cục nội bộ ban đầu không phải một dãy sắp xếp.

## 6. Độ phức tạp gắn với mục đích sử dụng

| Thao tác | Chi phí chính |
| --- | --- |
| `peek`, `element` | `O(1)` |
| `size` | `O(1)` |
| Điều chỉnh heap khi thêm | `O(log n)` |
| `poll`, `remove()` không đối số | `O(log n)` |
| `contains(Object)` | `O(n)` |
| `remove(Object)` | `O(n)` do cần tìm phần tử |
| Lấy hết bằng `poll` | `O(n log n)` |

Bảng giả định một phép so sánh có chi phí hằng. Comparator thực hiện công việc tốn kém sẽ ảnh hưởng thời gian thực tế.

Một lần thêm có thể còn phải tăng mảng lưu trữ và sao chép các tham chiếu; lần tăng mảng đó có thể có chi phí tuyến tính. `O(log n)` mô tả chi phí điều chỉnh heap và mức đánh giá quen thuộc cho thao tác thêm khi xét chi phí tăng dung lượng theo cách phân bổ.

Heap thuận lợi cho bài toán liên tục lấy phần tử ưu tiên nhất. Nó không cung cấp tìm kiếm khóa bất kỳ nhanh như một cấu trúc có chỉ mục chuyên cho mục đích đó.

## 7. Chương trình hoàn chỉnh: thứ tự số và công việc ưu tiên

Ví dụ chạy trên Java 17+. Phần số nguyên cho thấy đầu hàng đợi và chuỗi lấy ra; phần công việc dùng comparator tùy chỉnh và khóa phụ để giải quyết các mức ưu tiên bằng nhau.

Lưu thành `PriorityHeapDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;
import java.util.Queue;

public class PriorityHeapDemo {
    record Job(String name, int priority, long sequence) {
    }

    public static void main(String[] args) {
        PriorityQueue<Integer> numbers = new PriorityQueue<>(1);
        for (int value : new int[] {8, 3, 5, 1, 3}) {
            numbers.offer(value);
        }

        System.out.println("size: " + numbers.size());
        System.out.println("head: " + numbers.peek());
        System.out.println("size after peek: " + numbers.size());

        PriorityQueue<Integer> copy = new PriorityQueue<>(numbers);
        List<Integer> ordered = new ArrayList<>();
        while (!copy.isEmpty()) {
            ordered.add(copy.poll());
        }
        System.out.println("poll order: " + ordered);
        System.out.println("original size: " + numbers.size());

        Comparator<Job> order = Comparator
                .comparingInt(Job::priority)
                .reversed()
                .thenComparingLong(Job::sequence);
        Queue<Job> jobs = new PriorityQueue<>(order);

        jobs.offer(new Job("low", 1, 0));
        jobs.offer(new Job("fast-B", 10, 2));
        jobs.offer(new Job("fast-A", 10, 1));

        while (!jobs.isEmpty()) {
            Job job = jobs.poll();
            System.out.println(job.name()
                    + " priority=" + job.priority()
                    + " sequence=" + job.sequence());
        }
        System.out.println("empty poll: " + jobs.poll());
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 PriorityHeapDemo.java
java PriorityHeapDemo
```

Stdout:

```text
size: 5
head: 1
size after peek: 5
poll order: [1, 3, 3, 5, 8]
original size: 5
fast-A priority=10 sequence=1
fast-B priority=10 sequence=2
low priority=1 sequence=0
empty poll: null
```

### Đọc bằng chứng từ chương trình

`peek` nhìn thấy số 1 mà không giảm kích thước. Hai số 3 đều được giữ: `PriorityQueue` không phải một set và không tự loại bỏ phần tử trùng.

Chuỗi đã sắp thứ tự được tạo bằng cách `poll` trên bản sao. Các lần lấy ra làm bản sao rỗng, còn hàng đợi gốc vẫn chứa 5 phần tử. Nếu dùng `poll` trên bản gốc, dữ liệu gốc sẽ bị tiêu thụ.

Comparator của `Job` đặt số priority lớn trước. Với cùng priority, `sequence` nhỏ trước. `fast-A` được thêm sau `fast-B` nhưng được lấy trước vì khóa phụ là 1 thay vì 2.

`sequence` là dữ liệu chủ động do chương trình cung cấp. Hàng đợi không tự sinh một quy tắc “đến trước được xử lý trước” cho các phần tử có ưu tiên bằng nhau.

## 8. Thứ tự duyệt không phải thứ tự ưu tiên

Các thao tác sau không bảo đảm cho ra toàn bộ phần tử theo thứ tự ưu tiên:

```java
// Minh họa, giả sử queue là một PriorityQueue đã có dữ liệu:
for (Integer value : queue) {
    System.out.println(value);
}

System.out.println(queue);
Object[] snapshot = queue.toArray();
```

Iterator, biểu diễn chuỗi qua việc duyệt và mảng xuất ra không được dùng thay cho quá trình `poll` để khẳng định thứ tự ưu tiên.

Nếu cần một ảnh chụp có thứ tự mà giữ dữ liệu gốc:

- Tạo bản sao hàng đợi rồi `poll` trên bản sao, như chương trình.
- Hoặc sao chép phần tử sang danh sách rồi sắp xếp bằng **cùng comparator**.

Đừng sắp xếp bằng thứ tự tự nhiên nếu hàng đợi dùng comparator riêng rồi gọi đó là cùng thứ tự ưu tiên.

## 9. Các điều kiện giữ heap đúng

### Comparator phải nhất quán

Comparator cần đáp ứng hợp đồng so sánh, đặc biệt tính bắc cầu và cách đổi dấu khi đảo hai đối số. Không dùng phép trừ tùy tiện như `a.priority() - b.priority()` vì số nguyên có thể tràn. `Comparator.comparingInt` hoặc `Integer.compare` diễn đạt so sánh an toàn hơn.

Comparator trả 0 cho hai phần tử không khiến `PriorityQueue` loại một phần tử. Nó chỉ cho biết hai phần tử có cùng thứ tự theo tiêu chí đó. Nếu không có khóa phụ, thứ tự lấy các phần tử đồng hạng không được bảo đảm ổn định.

### Không âm thầm thay đổi khóa ưu tiên của phần tử đã nằm trong hàng đợi

Nếu phần tử thay đổi trường mà comparator dùng, heap không tự nhận một thông báo để sắp lại vị trí. Kết quả lấy đầu có thể không còn phản ánh thứ tự mong muốn.

Ưu tiên dữ liệu khóa bất biến như `record Job` trong ví dụ. Nếu cần cập nhật mức ưu tiên, có thể loại phần tử rồi thêm phiên bản mới; cần tính cả chi phí tìm phần tử và điều phối cập nhật. `PriorityQueue` không cung cấp thao tác decrease-key chuyên dụng.

### Dung lượng và đồng thời

`initialCapacity` chỉ là dung lượng ban đầu, không đặt giới hạn phần tử tối đa. Mảng tự tăng theo chính sách triển khai; API không cam kết một công thức tăng cố định để ứng dụng phụ thuộc.

`PriorityQueue` không tự đồng bộ. Nếu nhiều luồng truy cập và có luồng sửa hàng đợi, cần cơ chế đồng bộ hoặc cấu trúc đồng thời phù hợp, chẳng hạn `PriorityBlockingQueue` khi hợp đồng của nó đáp ứng nhu cầu.

## 10. Thực hành

1. Thêm số 0 vào hàng đợi số trước khi gọi `peek`; đầu hàng đợi sẽ là gì?
2. Gọi `poll` trực tiếp trên `numbers` thay cho bản sao; kích thước gốc sau khi lấy hết còn bao nhiêu?
3. Bỏ `thenComparingLong(Job::sequence)`; có được dựa vào thứ tự thêm để dự đoán `fast-A` và `fast-B` không?
4. Đổi comparator số sang `Comparator.reverseOrder()`; số nào được lấy trước?
5. Vì sao `contains` không tự có chi phí `O(log n)` dù heap có chiều cao `log n`?

Đáp án:

1. Số 0.
2. Bằng 0.
3. Không; các phần tử đồng hạng không có bảo đảm thứ tự ổn định.
4. Số lớn nhất theo giá trị số trong dữ liệu hiện có.
5. Quan hệ heap không phân vùng đầy đủ vị trí một khóa bất kỳ; thao tác này phải tìm tuyến tính theo hợp đồng triển khai.

## Tài liệu đối chiếu

Xem [PriorityQueue — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PriorityQueue.html), hợp đồng [Comparator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html) và triển khai tham khảo [OpenJDK 21 PriorityQueue](https://github.com/openjdk/jdk21u/blob/master/src/java.base/share/classes/java/util/PriorityQueue.java) cho mảng heap và các thao tác điều chỉnh.
