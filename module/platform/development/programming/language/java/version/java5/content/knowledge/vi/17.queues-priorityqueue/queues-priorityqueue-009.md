# Độ phức tạp của thêm, lấy và tìm phần tử

## 1. Bắt đầu từ thao tác cần làm, không chỉ từ tên Queue

Queue là interface mô tả hành vi hàng đợi. Nó không quy định mọi cài đặt có cùng thuật toán hoặc chi phí.

Trong phạm vi bài này:

- `PriorityQueue` dùng heap để giữ phần tử nhỏ nhất theo thứ tự tự nhiên hoặc Comparator ở đầu.
- `ArrayDeque` dùng mảng vòng và có thể dùng như hàng đợi FIFO.
- `n` là số phần tử đang có trong cấu trúc.

Khi nói O(1), O(log n), O(n), ta đang mô tả tốc độ tăng của lượng công việc khi n tăng, không phải số mili giây cố định. Các phân tích bên dưới giả định một lần so sánh hoặc kiểm tra equals có chi phí O(1), trừ khi nêu riêng.

Ví dụ dùng Java 17+ và các API vẫn áp dụng trong Java hiện đại.

## 2. Bảng chi phí quan trọng

| Thao tác | PriorityQueue | ArrayDeque dùng như FIFO Queue |
| --- | --- | --- |
| `offer(e)`, `add(e)` thêm phần tử | O(log n) cho duy trì heap; lưu ý mở rộng mảng | O(1) khấu hao |
| `peek()`, `element()` xem đầu | O(1) | O(1) |
| `poll()`, `remove()` không đối số lấy đầu | O(log n) | O(1) |
| `size()` | O(1) | O(1) |
| `contains(value)` | O(n) | O(n) |
| `remove(value)` có đối số | O(n) tổng thể | O(n) |

Tài liệu PriorityQueue liệt kê O(log n) cho thêm và lấy đầu, O(n) cho `contains(Object)` và `remove(Object)`, O(1) cho xem đầu và size.

Ở đây cần phân biệt thêm một chi tiết: PriorityQueue được lưu trong mảng có thể mở rộng. Một lần thêm đúng lúc hết sức chứa có thể phải sao chép O(n) phần tử. Do đó, không nên hiểu dòng O(log n) là cam kết “mọi lần offer đều chỉ làm tối đa một số bước log n kể cả cấp phát”. Phần duy trì heap là O(log n); chi phí tăng mảng được phân bổ khi phân tích chuỗi thao tác.

Tương tự, O(1) khấu hao của thêm vào ArrayDeque cho phép một lần riêng lẻ tốn O(n) khi cần tăng mảng. Khấu hao mô tả tổng chi phí trên một chuỗi thao tác, không phải lấy trung bình ngẫu nhiên giữa các dữ liệu đầu vào.

## 3. Vì sao thêm vào PriorityQueue là O(log n)?

PriorityQueue của JDK dùng một heap nhị phân được lưu trong mảng. Heap bảo đảm:

- Phần tử ở gốc là nhỏ nhất theo quy tắc so sánh.
- Mỗi nút cha không lớn hơn các nút con theo quy tắc đó.
- Không yêu cầu toàn bộ các vị trí trong mảng được sắp tăng dần.

Khi thêm một phần tử:

1. Đặt phần tử mới vào vị trí cuối phù hợp với hình dạng heap.
2. So sánh với nút cha.
3. Nếu thứ tự chưa đúng, đẩy phần tử lên trên.
4. Lặp cho đến khi đúng vị trí hoặc tới gốc.

Chiều cao của heap nhị phân là O(log n), nên phần tử chỉ đi qua tối đa một đường từ cuối lên gốc. Không cần so sánh với mọi phần tử.

Nếu Comparator của ứng dụng so sánh các chuỗi dài hoặc thực hiện nhiều công việc, mỗi bước không còn có chi phí hằng số. Khi ấy nên diễn đạt số lần so sánh O(log n) cùng chi phí của một lần so sánh, thay vì kết luận thời gian tổng chỉ phụ thuộc vào n.

Không đặt I/O, truy vấn cơ sở dữ liệu hoặc công việc nặng vào Comparator rồi kỳ vọng hàng đợi vẫn nhanh chỉ nhờ tên gọi O(log n).

## 4. Vì sao xem đầu là O(1), còn lấy đầu là O(log n)?

### Xem đầu: peek và element

Gốc heap đã lưu phần tử đầu. Xem nó không cần tìm kiếm và không làm thay đổi cấu trúc.

`peek()` và `element()` khác cách xử lý rỗng, không khác việc phải sắp xếp lại hàng đợi:

- peek trả null khi rỗng.
- element ném `NoSuchElementException` khi rỗng.

### Lấy đầu: poll và remove()

Sau khi lấy gốc ra, PriorityQueue phải phục hồi tính chất heap. Có thể hình dung đưa phần tử cuối về gốc rồi đẩy nó xuống đường nhánh phù hợp.

Quãng đường đi xuống không vượt chiều cao heap, nên chi phí duy trì cấu trúc là O(log n).

`poll()` và `remove()` không đối số khác cách xử lý rỗng, nhưng đều lấy đầu. Không thể thay poll bằng peek để “tối ưu” nếu bài toán cần xóa phần tử; khi ấy hành vi đã đổi.

Với ArrayDeque ở chế độ FIFO, phần tử đầu được xác định bằng chỉ số trong mảng vòng. Lấy đầu chủ yếu cập nhật vị trí và xóa tham chiếu cũ, nên có chi phí O(1) cho thao tác đó trong cài đặt thông thường.

## 5. Vì sao PriorityQueue tìm theo giá trị vẫn là O(n)?

Heap chỉ cho biết quan hệ cha-con đủ để xác định phần tử nhỏ nhất. Nó không có một chỉ mục cho mọi giá trị bất kỳ.

Ví dụ, biết gốc là 10 không giúp xác định ngay một đối tượng cụ thể có nằm trong một nhánh nào hay không. Vì vậy:

```java
queue.contains(target);
```

có thể phải kiểm tra nhiều phần tử cho đến khi tìm được target hoặc duyệt hết hàng đợi.

Đừng dùng tìm kiếm nhị phân trực tiếp trên kết quả iterator hay mảng chưa sắp của PriorityQueue. Cấu trúc heap không phải một danh sách được sắp đầy đủ.

`contains(Object)` dựa trên equals theo hợp đồng collection, không chỉ dựa trên Comparator trả 0. Hai đối tượng có thể cùng mức ưu tiên nhưng không bằng nhau theo equals.

### remove(Object) gồm tìm và phục hồi

```java
queue.remove(target);
```

phải xác định một phần tử khớp target, sau đó xóa và điều chỉnh heap tại vị trí đó.

Có thể phân tích:

- Tìm vị trí: O(n).
- Phục hồi heap: O(log n).
- Tổng: O(n + log n) = O(n).

Không nhầm với `remove()` không đối số. Phiên bản không đối số biết ngay vị trí gốc và có O(log n), còn phiên bản có đối số phải tìm theo giá trị nên O(n).

Một phần tử xuất hiện nhiều lần không khiến remove(value) xóa tất cả. Nó xóa một lần xuất hiện phù hợp theo hợp đồng, và trả boolean cho biết có xóa được hay không.

## 6. Ví dụ chạy đầy đủ: quan sát hành vi, không giả làm benchmark

Lưu thành `QueueComplexityDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.PriorityQueue;
import java.util.Queue;

public class QueueComplexityDemo {
    public static void main(String[] args) {
        PriorityQueue<Integer> priority = new PriorityQueue<>();
        priority.offer(40);
        priority.offer(10);
        priority.offer(30);
        priority.offer(20);

        System.out.println("head=" + priority.peek());
        System.out.println("size after peek=" + priority.size());
        System.out.println("contains 30=" + priority.contains(30));
        System.out.println("remove value 30=" + priority.remove(30));
        System.out.println("remove head=" + priority.remove());
        System.out.println("priority remaining=" + drain(priority));

        Queue<Integer> fifo = new ArrayDeque<>();
        fifo.offer(40);
        fifo.offer(10);
        fifo.offer(30);
        fifo.offer(20);
        System.out.println("fifo order=" + drain(fifo));
    }

    static String drain(Queue<Integer> queue) {
        StringBuilder result = new StringBuilder();
        Integer value;
        while ((value = queue.poll()) != null) {
            if (result.length() > 0) {
                result.append(",");
            }
            result.append(value);
        }
        return result.toString();
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 QueueComplexityDemo.java
java QueueComplexityDemo
```

Kết quả:

```text
head=10
size after peek=4
contains 30=true
remove value 30=true
remove head=10
priority remaining=20,40
fifo order=40,10,30,20
```

Ví dụ làm rõ các thao tác đang so sánh:

- peek không lấy phần tử ra.
- remove(30) tìm và xóa theo giá trị.
- remove() lấy đầu.
- PriorityQueue và ArrayDeque có thứ tự xử lý khác nhau.

Chương trình không đo thời gian. Kích thước dữ liệu nhỏ và việc in ra màn hình không đủ để suy ra một cấu trúc nhanh hơn cấu trúc kia bao nhiêu lần.

## 7. Tính tổng chi phí cho một luồng xử lý

### Thêm n phần tử rời rồi lấy hết theo ưu tiên

Nếu gọi offer lặp n lần, cận trên cho phần duy trì heap là O(n log n). Lấy hết bằng poll cũng có tổng O(n log n).

Vì vậy, một luồng “thêm tất cả rồi lấy tất cả” qua các thao tác này có cận O(n log n), không phải O(log n) cho cả chương trình chỉ vì một lần poll có O(log n).

Chi phí tạo phần tử, so sánh, cấp phát, xuất kết quả hoặc xử lý công việc còn cần được cộng riêng.

### Poll từng phần tử rồi tìm một đối tượng khác

Nếu một vòng lặp chạy O(n) lần và mỗi lần gọi contains trên hàng đợi cỡ n, phần tìm kiếm có thể tiến tới O(n²). Chi phí này có thể lấn át các thao tác heap.

Không nên chỉ tối ưu offer/poll mà bỏ qua contains hoặc remove(value) trong vòng lặp lớn.

### Chỉ giữ k phần tử tốt nhất

Nếu bài toán duy trì một heap tối đa k phần tử và xử lý n đầu vào, mỗi lần cập nhật heap có thể tốn O(log k), dẫn tới cận O(n log k) cho các bước cập nhật.

Nhưng phải chọn đúng chiều Comparator và quy tắc giữ/bỏ phần tử. Kết luận O(n log k) không có nghĩa đưa toàn bộ n phần tử vào một heap rồi vẫn tính theo k.

## 8. Sức chứa ban đầu và giới hạn của tối ưu cấp phát

Có thể chỉ định sức chứa ban đầu:

```java
PriorityQueue<Integer> queue = new PriorityQueue<>(1000);
```

Điều này có thể giảm số lần mở rộng mảng khi ước lượng số phần tử hợp lý. Nó không:

- biến PriorityQueue thành hàng đợi có giới hạn 1000 phần tử;
- thay đổi contains thành O(log n);
- thay đổi cách chọn đầu;
- xóa chi phí so sánh và duy trì heap.

PriorityQueue vẫn có thể tăng kích thước nếu thêm quá sức chứa ban đầu. Đừng suy từ tham số constructor này ra cơ chế từ chối công việc khi đầy.

Cấp phát quá lớn cũng có thể lãng phí bộ nhớ. Chọn theo dữ liệu dự kiến và phép đo phù hợp.

Không áp dụng máy móc phân tích “offer lặp n lần” cho mọi constructor hoặc thao tác bulk: một cài đặt có thể xây heap theo thuật toán khác. Nếu cần cam kết chính xác về cách xây ban đầu, đọc hợp đồng và cài đặt của constructor đang dùng thay vì đoán nó luôn là một vòng offer.

## 9. Chọn cấu trúc theo phần việc chiếm ưu thế

- Cần FIFO, thêm cuối và lấy đầu: ArrayDeque thường phù hợp cho chương trình một luồng.
- Cần liên tục nhận phần tử ưu tiên nhất: PriorityQueue phù hợp với offer/poll.
- Cần kiểm tra tồn tại theo khóa thường xuyên: có thể cần một cấu trúc chỉ mục khác, như Map/Set, cùng chính sách đồng bộ dữ liệu rõ ràng.
- Cần thay đổi ưu tiên và xóa bất kỳ rất thường xuyên: PriorityQueue thông thường không có thao tác decrease-key theo một handle; phải đánh giá cách quản lý vị trí hoặc cấu trúc khác.
- Chỉ cần một lần sắp toàn bộ dữ liệu rồi duyệt: một danh sách/mảng được sắp có thể phù hợp hơn một hàng đợi ưu tiên.

Các lựa chọn không thay thế nhau chỉ dựa trên một ô trong bảng Big-O. FIFO và ưu tiên là hai hợp đồng thứ tự khác nhau. Nếu dùng thêm Map/Set bên cạnh heap, phải giữ tính nhất quán khi thêm, lấy, hủy hoặc cập nhật phần tử; chi phí và độ phức tạp thiết kế cũng tăng.

Với ứng dụng nhiều luồng, còn phải chọn cấu trúc đồng thời hoặc cơ chế đồng bộ hóa. PriorityQueue và ArrayDeque thông thường không an toàn cho truy cập đồng thời không đồng bộ.

## 10. Đọc số liệu hiệu năng cùng với Big-O

Độ phức tạp giải thích xu hướng khi dữ liệu tăng. Thời gian thực còn phụ thuộc:

- Kích thước n và cách phân bố dữ liệu.
- Comparator, equals và kích thước đối tượng.
- Tỷ lệ thêm, xem, lấy và tìm.
- Cấp phát, mở rộng mảng, thu gom rác.
- JVM, mức tối ưu JIT và phần cứng.

Nếu phải đo các thao tác nhỏ, dùng một phương pháp benchmark JVM phù hợp, tách I/O ra khỏi phần đo, có làm nóng, nhiều lượt đo và dữ liệu đại diện. Không bịa một con số nanosecond cố định cho mọi offer hoặc poll.

Một tìm kiếm tuyến tính có thể đủ nhanh với n rất nhỏ; điều đó không làm nó trở thành O(1). Ngược lại, O(log n) cũng không bảo đảm nhanh hơn mọi O(n) ở mọi kích thước và mọi công việc.

## 11. Thực hành

1. Đếm số lần gọi contains trong một vòng xử lý thực tế. Nếu mỗi phần tử đầu vào lại tìm trong cả hàng đợi, hãy tính chi phí tổng thay vì chỉ chi phí một lần.
2. Giải thích vì sao remove() là O(log n) nhưng remove(value) là O(n) trong PriorityQueue.
3. Dùng Comparator có nhiều tiêu chí rồi phân biệt “số lần so sánh” với “thời gian của một lần so sánh”.
4. Thêm một sức chứa ban đầu lớn hơn vào ví dụ. Giải thích vì sao stdout và quan hệ thứ tự không đổi.
5. Nếu cần vừa FIFO vừa ưu tiên, viết rõ chính sách xử lý trước khi chọn cấu trúc; một thay đổi cấu trúc có thể làm đổi hành vi, không chỉ đổi hiệu năng.

## Tài liệu đối chiếu

- [PriorityQueue — Hợp đồng chi phí, thứ tự và sức chứa](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PriorityQueue.html).
- [ArrayDeque — Chi phí khấu hao và các thao tác tuyến tính](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayDeque.html).
- [OpenJDK — Cài đặt PriorityQueue](https://github.com/openjdk/jdk21u/blob/master/src/java.base/share/classes/java/util/PriorityQueue.java).
