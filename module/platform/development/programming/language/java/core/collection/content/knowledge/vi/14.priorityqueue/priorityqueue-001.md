# Hàng đợi ưu tiên và quan hệ với cấu trúc heap

## 1. Từ “đến trước” sang “cần xử lý trước”

Giả sử ứng dụng đang giữ các công việc chờ xử lý. A được gửi trước, B được gửi sau nhưng B khẩn cấp hơn. Nếu luôn lấy công việc đến trước, A được chọn. Nếu quy tắc là chọn công việc có mức khẩn cấp cao hơn, B phải được chọn dù đến sau.

**Hàng đợi ưu tiên (priority queue)** phục vụ câu hỏi: “Trong các phần tử hiện có, phần tử nào đứng trước theo quy tắc ưu tiên?” Trong Java, `PriorityQueue<E>` là một lớp cài đặt giao diện `Queue<E>` cho nhu cầu đó.

Cần phân biệt ba tầng:

| Tầng | Câu hỏi được giải quyết |
| --- | --- |
| Quy tắc nghiệp vụ | Thế nào là được ưu tiên: hạn chót sớm hơn, chi phí nhỏ hơn, mức khẩn cấp lớn hơn...? |
| Hàng đợi ưu tiên | Thêm phần tử, xem hoặc lấy phần tử đứng đầu theo quy tắc đó |
| Cấu trúc heap | Tổ chức dữ liệu để duy trì phần tử ưu tiên ở vị trí dễ lấy với chi phí cập nhật hợp lý |

Heap là cơ chế tổ chức bên trong, còn hàng đợi ưu tiên là hành vi mà người dùng cấu trúc dữ liệu cần. Một mô hình hàng đợi ưu tiên có thể được xây dựng theo nhiều cách; OpenJDK dùng heap nhị phân cho `PriorityQueue`.

Bài này đi từ ý nghĩa của đầu hàng đợi đến tính chất heap, cách thêm/lấy phần tử, chi phí và ví dụ Java 17+. Mục tiêu là giải thích được **vì sao lấy được phần tử ưu tiên nhanh mà toàn bộ dữ liệu chưa cần được sắp xếp hoàn toàn**.

## 2. Đầu hàng đợi là phần tử nhỏ nhất theo quy tắc so sánh

### 2.1. Nhỏ nhất theo comparator không nhất thiết là số nhỏ nhất

Với cấu hình mặc định cho số nguyên:

```java
PriorityQueue<Integer> queue = new PriorityQueue<>();
queue.offer(5);
queue.offer(1);
queue.offer(4);
```

Đây là đoạn lệnh minh họa đặt trong một phương thức, cần import `java.util.PriorityQueue`. `queue.peek()` trả 1: thứ tự tự nhiên của `Integer` coi 1 đứng trước 4 và 5.

Nếu dùng:

```java
PriorityQueue<Integer> queue =
        new PriorityQueue<>(Comparator.reverseOrder());
```

thì số 5 lại đứng trước 4 và 1 theo comparator đảo chiều. `peek()` trả 5. Cần import thêm `java.util.Comparator`.

Java vẫn lấy phần tử nhỏ nhất **theo thứ tự mà hàng đợi đang sử dụng**. Từ góc nhìn giá trị số ban đầu, trường hợp thứ hai hoạt động như hàng đợi lấy số lớn nhất trước.

Không có quy tắc mặc định rằng trường tên `priority` càng lớn thì càng được xử lý trước. Hãy viết rõ quy ước của ứng dụng rồi xây comparator tương ứng.

### 2.2. FIFO không phải bảo đảm của PriorityQueue

Thêm lần lượt `5, 1, 4` rồi lấy hết bằng `poll()` trên hàng đợi mặc định sẽ nhận `1, 4, 5`, không phải `5, 1, 4`.

Nếu hai phần tử bằng nhau về mức ưu tiên, `PriorityQueue` không tự bảo đảm thứ tự đến trước được lấy trước. Có thể cần tiêu chí phụ như một số thứ tự nhận việc. Hòa ưu tiên cũng không làm phần tử mới bị loại: hàng đợi có thể giữ nhiều phần tử cùng giá trị hoặc cùng mức ưu tiên.

Hợp đồng về phần tử đầu, hòa ưu tiên và thứ tự duyệt nằm trong [tài liệu PriorityQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).

### 2.3. Hàng đợi không tự thực thi công việc

Lấy một tác vụ từ `PriorityQueue` không làm Java tự tạo luồng hay tự chạy tác vụ đó. Ứng dụng vẫn phải quyết định khi nào gọi `poll()`, chạy công việc ở đâu và xử lý lỗi thế nào.

Nếu công việc ưu tiên cao liên tục được thêm, công việc ưu tiên thấp có thể chờ lâu. Đó là vấn đề chính sách xử lý của ứng dụng; bản thân heap không tự bổ sung cơ chế công bằng hay tăng ưu tiên theo thời gian.

## 3. Heap nhị phân: hình dạng đầy đủ, thứ tự từng nhánh

### 3.1. Hai điều kiện cần giữ

Với heap nhỏ nhất ở gốc (min-heap), hai điều kiện là:

1. **Hình dạng:** cây nhị phân hoàn chỉnh (complete binary tree). Các mức trước mức cuối được lấp đầy; mức cuối được điền từ trái sang phải.
2. **Thứ tự heap:** mỗi nút cha không đứng sau các nút con theo quy tắc so sánh.

Min-heap số nguyên có thể trông như sau:

```text
          2
        /   \
       5     3
      / \   /
     9   6 8
```

Các cạnh đều đúng: 2 ≤ 5, 2 ≤ 3, 5 ≤ 9, 5 ≤ 6, 3 ≤ 8. Vì phép so sánh có tính bắc cầu, gốc 2 không lớn hơn bất kỳ hậu duệ nào, nên 2 là một phần tử nhỏ nhất của toàn heap.

Cây này có hình dạng hoàn chỉnh vì mức cuối có ba vị trí được điền liên tiếp từ trái. Nó không cần có số nút con trái bằng số nút con phải ở mọi nút.

### 3.2. Heap không phải cây tìm kiếm nhị phân

Trong cây minh họa, nút con trái 5 lớn hơn gốc 2. Điều này hoàn toàn hợp lệ với min-heap. Không có điều kiện “mọi giá trị bên trái nhỏ hơn gốc” như cách người học thường nhớ về cây tìm kiếm nhị phân.

Giữa hai nút anh em 5 và 3, heap cũng không yêu cầu 5 phải nhỏ hơn 3. Giữa 6 và 8 ở hai nhánh khác nhau, không có một vị trí cố định nào được quyết định chỉ bởi thứ tự toàn cục của chúng.

Bất biến heap chỉ tạo ra đủ quan hệ để biết gốc là phần tử ưu tiên nhất. Nó không tạo ra đường tìm kiếm một giá trị bất kỳ giống cây tìm kiếm có thứ tự.

### 3.3. Heap không phải mảng đã sắp xếp

Đọc cây trên theo từng mức từ trái sang phải được:

```text
[2, 5, 3, 9, 6, 8]
```

Dãy này là một biểu diễn heap hợp lệ nhưng không tăng dần: 5 đứng trước 3, 9 đứng trước 6 và 8. Không thể kết luận heap sai chỉ vì mảng biểu diễn không được sắp xếp.

Một dãy tăng dần cũng thỏa điều kiện min-heap theo cách đánh chỉ số thông thường, nhưng điều ngược lại không đúng. Heap cho phép nhiều bố trí khác nhau cho cùng một tập phần tử.

Trong bài, các hình và mảng heap là **mô hình thuật toán để giải thích**. Chúng không phải khẳng định về thứ tự `toString()`, `iterator()` hay mảng nội bộ mà một bản JDK cụ thể bắt buộc phải trả.

## 4. Vì sao cây heap thường được lưu trong mảng?

### 4.1. Vị trí cha và con tính được từ chỉ số

Với mảng đánh chỉ số từ 0, nút ở chỉ số `i` có:

| Quan hệ | Công thức |
| --- | --- |
| Cha, khi `i > 0` | `(i - 1) / 2`, lấy phần nguyên |
| Con trái | `2 * i + 1` |
| Con phải | `2 * i + 2` |

Một chỉ số con chỉ tồn tại nếu nhỏ hơn số phần tử `n`.

Với heap minh họa:

```text
Chỉ số:    0  1  2  3  4  5
Giá trị:  [2, 5, 3, 9, 6, 8]
```

- Cha của phần tử 8 tại chỉ số 5 là chỉ số 2, có giá trị 3.
- Con của chỉ số 1 là chỉ số 3 và 4, có giá trị 9 và 6.
- Chỉ số 2 có con trái tại 5, nhưng con phải tại 6 chưa tồn tại.

Do cây được điền liên tiếp theo mức, không cần khoảng trống giữa các nút đang dùng. Cũng không bắt buộc tạo một đối tượng nút có hai tham chiếu con cho mỗi phần tử.

`PriorityQueue` không cung cấp API đọc phần tử theo chỉ số của mảng heap. Công thức trên dùng để hiểu cách cài đặt, không biến hàng đợi thành `List`.

### 4.2. Chiều cao tăng chậm khi số phần tử tăng

Một cây nhị phân hoàn chỉnh có số mức tăng theo logarit của n. Khi thêm hoặc lấy đầu hàng đợi, phần tử cần sửa vị trí thường chỉ đi trên một đường giữa gốc và lá.

Đây là nguồn gốc của chi phí O(log n) cho bước duy trì heap: không phải sắp xếp lại mọi cặp phần tử sau mỗi lần thay đổi.

“Heap” trong cấu trúc dữ liệu này cũng không đồng nghĩa với vùng nhớ heap của JVM. Một đối tượng `PriorityQueue` và các phần tử của nó có thể được cấp phát trong vùng nhớ heap của JVM, nhưng tính chất cha–con đang học là tính chất của thuật toán, không phải quy tắc cấp phát bộ nhớ.

## 5. Thêm phần tử: đi lên để sửa thứ tự

### 5.1. Đặt cuối để giữ hình dạng

Bắt đầu với:

```text
[2, 5, 3, 9, 6, 8]
```

Cần thêm 1. Đặt 1 vào vị trí trống tiếp theo ở cuối mảng:

```text
[2, 5, 3, 9, 6, 8, 1]
```

Hình dạng cây vẫn hoàn chỉnh. Những quan hệ cũ vẫn đúng, nhưng cạnh giữa 3 và 1 đang vi phạm thứ tự min-heap.

### 5.2. Sift up: sửa theo đường đến gốc

So 1 với cha 3; đổi vị trí vì 1 đứng trước 3:

```text
[2, 5, 1, 9, 6, 8, 3]
```

Tiếp tục so 1 với cha 2; đổi vị trí:

```text
[1, 5, 2, 9, 6, 8, 3]
```

1 đã đến gốc. Mỗi bước chỉ cần xét nút đang di chuyển và cha của nó; không cần sắp xếp lại cả hai nhánh. Quá trình này thường được gọi là **đẩy lên (sift up)**.

Nếu thêm một giá trị lớn hơn hoặc bằng cha ngay từ đầu, có thể dừng sớm. Nếu thêm giá trị nhỏ nhất mới, có thể phải đi đến tận gốc.

### 5.3. Mã giả của mô hình

Đây là mã giả minh họa với mảng trừu tượng, không phải mã Java chạy độc lập hoặc mã nguồn được chép từ JDK:

```text
thêm x vào vị trí cuối
i = vị trí của x

trong khi i > 0:
    p = chỉ số cha của i
    nếu compare(heap[i], heap[p]) >= 0:
        dừng
    đổi heap[i] với heap[p]
    i = p
```

Hình thức cài đặt thực tế có thể giữ `x` ở biến tạm và dịch các nút cha xuống thay vì đổi từng cặp. Ý nghĩa duy trì bất biến vẫn như nhau.

## 6. Lấy gốc: dùng phần tử cuối rồi đẩy xuống

### 6.1. Không để một lỗ ở gốc

Tiếp tục với heap sau khi thêm 1:

```text
[1, 5, 2, 9, 6, 8, 3]
```

Khi lấy 1 ra:

1. Giữ 1 làm kết quả cần trả.
2. Đưa phần tử cuối 3 lên gốc.
3. Giảm số phần tử, bỏ vị trí cuối cũ.
4. Sửa quan hệ heap bắt đầu ở gốc.

Trạng thái tạm:

```text
[3, 5, 2, 9, 6, 8]
```

Hình dạng hoàn chỉnh được giữ, nhưng 3 ở gốc lớn hơn con phải 2.

### 6.2. Sift down: chọn con đứng trước

So hai con 5 và 2; chọn 2 vì nó nhỏ hơn theo thứ tự min-heap. Đổi 3 với 2:

```text
[2, 5, 3, 9, 6, 8]
```

Ở vị trí mới, 3 chỉ có con 8; vì 3 ≤ 8 nên dừng. Heap lại hợp lệ và phương thức trả 1 đã giữ trước đó.

Phải chọn con đứng trước trong hai con đang tồn tại. Nếu tùy ý đổi với 5, gốc mới có thể vẫn lớn hơn 2, làm bất biến tiếp tục sai ngay tại gốc.

Quá trình này gọi là **đẩy xuống (sift down)**. Mã giả:

```text
nếu heap rỗng:
    trả kết quả rỗng theo hợp đồng của phương thức

result = phần tử gốc
x = phần tử cuối
bỏ phần tử cuối

nếu vẫn còn phần tử:
    đặt x ở gốc
    i = 0
    trong khi i có con:
        c = chỉ số con đứng trước theo compare
        nếu compare(heap[i], heap[c]) <= 0:
            dừng
        đổi heap[i] với heap[c]
        i = c

trả result
```

Trường hợp chỉ có một phần tử không cần đẩy xuống sau khi lấy nó ra. Trường hợp chỉ có một con thì dùng con đó, không đọc một chỉ số con phải không tồn tại.

Cách lưu mảng, `siftUp`, `siftDown` và thao tác xây heap có thể đối chiếu trong [mã nguồn PriorityQueue của OpenJDK 17u](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/PriorityQueue.java). Khi dùng API, hãy dựa vào hợp đồng công khai thay vì phụ thuộc một bố trí nội bộ cụ thể.

## 7. Từ cơ chế heap sang các phương thức Java

### 7.1. Xem, lấy và xóa theo giá trị là các yêu cầu khác nhau

| Phương thức | Ý nghĩa | Khi rỗng hoặc không tìm thấy |
| --- | --- | --- |
| `offer(e)`, `add(e)` | Thêm e, duy trì hàng đợi ưu tiên | Với phần tử hợp lệ, thêm thành công và trả `true` |
| `peek()` | Xem đầu, không xóa | `null` |
| `element()` | Xem đầu, không xóa | `NoSuchElementException` |
| `poll()` | Lấy/xóa đầu | `null` |
| `remove()` | Lấy/xóa đầu | `NoSuchElementException` |
| `remove(Object)` | Tìm và xóa một phần tử bằng giá trị | `false` nếu không có |
| `contains(Object)` | Kiểm tra có phần tử bằng giá trị | `false` nếu không có |

`PriorityQueue` không cho phần tử `null`, nên `null` từ `peek()` hoặc `poll()` biểu thị rỗng. Đừng nhận kết quả vào kiểu nguyên thủy bằng cách tự động mở hộp mà không xét rỗng: mở hộp một `Integer` bằng `null` sẽ gây `NullPointerException`.

Phân biệt `remove()` không đối số với `remove(Object)` có đối số. Lấy đầu có thể khai thác gốc heap; tìm một giá trị cụ thể phải tìm vị trí trước.

### 7.2. Dung lượng khởi tạo không phải giới hạn số phần tử

`new PriorityQueue<Integer>(2)` không tạo hàng đợi “chứa tối đa hai phần tử”. Con số 2 là dung lượng ban đầu. Hàng đợi tăng dung lượng khi cần; chính sách tăng cụ thể không phải điều nên đưa vào logic ứng dụng.

Lớp được mô tả là không có giới hạn dung lượng cố định. Điều đó không có nghĩa có bộ nhớ vô hạn, và cũng không biến nó thành hàng đợi chặn khi đầy.

### 7.3. Bảng chi phí và lý do

| Thao tác | Chi phí thường dùng khi phân tích | Lý do |
| --- | --- | --- |
| `peek()`, `element()`, `size()` | O(1) | Xem gốc hoặc biến đếm |
| `offer()`, `add()` | O(log n) cho duy trì heap | Đẩy lên theo một đường |
| `poll()`, `remove()` | O(log n) | Đẩy xuống theo một đường |
| `contains(Object)` | O(n) | Heap không chỉ đường tìm một giá trị bất kỳ |
| `remove(Object)` | O(n) | Tìm tuyến tính trước khi sửa heap |
| Lấy hết bằng `poll()` | O(n log n) | Lặp lấy đầu trên kích thước giảm dần |
| Bộ nhớ chứa n phần tử | O(n) | Mảng và các tham chiếu phần tử |

Đây là cách phân tích của lớp được mô tả trong [tài liệu API PriorityQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html). Khi mảng phải tăng dung lượng, riêng lần thêm đó còn có thể tốn O(n) để sao chép các tham chiếu. Không nên diễn đạt rằng mọi lần `offer()` riêng lẻ đều bị chặn ở đúng O(log n) bất kể việc cấp phát; phần đẩy lên là O(log n), còn chi phí tăng mảng được xét khi phân tích cả chuỗi thao tác.

Các mức chi phí này thường giả định một phép so sánh có chi phí O(1). Nếu comparator làm công việc đắt tiền, chi phí đó cũng tham gia tổng thời gian.

### 7.4. Xây từ dữ liệu sẵn có khác thêm từng phần tử

Có thể tạo trực tiếp:

```java
PriorityQueue<Integer> queue =
        new PriorityQueue<>(List.of(9, 2, 6, 1, 5));
```

Đoạn lệnh minh họa cần import `List` và `PriorityQueue`. Hàng đợi được tạo chứa đủ dữ liệu; không có yêu cầu đầu vào phải được sắp xếp trước.

Về thuật toán, xây heap từ dưới lên bằng cách đẩy xuống các nút không phải lá có thể đạt O(n). Không phải mỗi nút đều đi từ gốc xuống độ cao log n: rất nhiều nút nằm gần lá và cần ít hoặc không cần sửa. OpenJDK 17u có bước `heapify` như vậy cho đường khởi tạo phù hợp từ một collection thông thường.

Ngược lại, gọi `offer()` n lần có chặn trên O(n log n) cho các bước duy trì heap. Việc cả hai cách cùng tạo một hàng đợi hợp lệ không buộc chúng phải tạo cùng mảng nội bộ.

Đừng biến nhận xét về một đường cài đặt thành bảo đảm rằng mọi constructor trong mọi bản cài đặt có cùng chi phí, hoặc việc xây heap đã sắp xếp toàn bộ mảng.

## 8. Chương trình chạy: ưu tiên nhỏ nhất và lớn nhất

Lưu thành **PriorityQueueBasicsDemo.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.PriorityQueue;

public class PriorityQueueBasicsDemo {
    private static <E> List<E> drain(PriorityQueue<E> queue) {
        List<E> result = new ArrayList<>();
        while (!queue.isEmpty()) {
            result.add(queue.poll());
        }
        return result;
    }

    public static void main(String[] args) {
        PriorityQueue<Integer> minQueue = new PriorityQueue<>(2);
        for (int value : List.of(5, 1, 4, 2, 3, 1)) {
            minQueue.offer(value);
        }
        System.out.println("size: " + minQueue.size());
        System.out.println("peek: " + minQueue.peek());
        System.out.println("size after peek: " + minQueue.size());
        System.out.println("ordered copy: " + drain(new PriorityQueue<>(minQueue)));
        System.out.println("original size: " + minQueue.size());

        System.out.println("remove value 4: " + minQueue.remove(Integer.valueOf(4)));
        System.out.println("contains 4: " + minQueue.contains(4));
        System.out.println("remove value 99: " + minQueue.remove(Integer.valueOf(99)));
        System.out.println("poll order: " + drain(minQueue));
        System.out.println("empty peek: " + minQueue.peek());
        System.out.println("empty poll: " + minQueue.poll());

        try {
            minQueue.element();
        } catch (NoSuchElementException ex) {
            System.out.println("empty element: " + ex.getClass().getSimpleName());
        }
        try {
            minQueue.remove();
        } catch (NoSuchElementException ex) {
            System.out.println("empty remove: " + ex.getClass().getSimpleName());
        }
        try {
            minQueue.offer(null);
        } catch (NullPointerException ex) {
            System.out.println("null offer: " + ex.getClass().getSimpleName());
        }

        PriorityQueue<Integer> maxQueue =
                new PriorityQueue<>(Comparator.reverseOrder());
        maxQueue.addAll(List.of(5, 1, 4, 2, 3));
        System.out.println("reverse-order peek: " + maxQueue.peek());
        System.out.println("reverse-order poll: " + drain(maxQueue));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 PriorityQueueBasicsDemo.java
java PriorityQueueBasicsDemo
```

Stdout chính xác:

```text
size: 6
peek: 1
size after peek: 6
ordered copy: [1, 1, 2, 3, 4, 5]
original size: 6
remove value 4: true
contains 4: false
remove value 99: false
poll order: [1, 1, 2, 3, 5]
empty peek: null
empty poll: null
empty element: NoSuchElementException
empty remove: NoSuchElementException
null offer: NullPointerException
reverse-order peek: 5
reverse-order poll: [5, 4, 3, 2, 1]
```

Các kết quả cần giải thích được:

- Dung lượng ban đầu là 2 nhưng thêm được sáu phần tử. Hai giá trị 1 đều tồn tại.
- `peek()` trả 1 mà không giảm kích thước.
- Bản sao được lấy hết bằng `poll()` cho thứ tự tăng dần; hàng đợi gốc vẫn còn sáu phần tử.
- `remove(Integer.valueOf(4))` xóa giá trị 4, không phải lấy phần tử đầu và không phải xóa chỉ số 4.
- Khi rỗng, hai cặp xem/lấy đầu khác nhau ở cách biểu thị thất bại: `null` hoặc ngoại lệ.
- Comparator đảo chiều làm số 5 đứng đầu và tạo thứ tự lấy 5, 4, 3, 2, 1.

Các chương trình trong bài được biên dịch với `--release 17` và chạy trên OpenJDK 24.0.2. Cờ này kiểm tra mã theo ngôn ngữ/API Java 17 và tạo bytecode tương ứng; JVM dùng để chạy ví dụ vẫn là bản đã nêu.

## 9. Các giới hạn bắt nguồn từ bất biến heap

Heap chỉ biết chắc phần tử đứng đầu theo quy tắc so sánh. Do đó, `iterator()` không có nghĩa là `poll()` liên tiếp; muốn xem cả thứ tự mà giữ nguồn, có thể lấy đầu trên bản sao hoặc sắp một danh sách bằng đúng comparator.

Heap cũng không có đường tìm kiếm theo giá trị như cây tìm kiếm nhị phân: `contains(Object)` và `remove(Object)` trước hết cần tìm phần tử theo `equals`. Hai phần tử có `compare(a,b) == 0` vẫn có thể cùng tồn tại; mức ưu tiên hòa không mặc định kéo theo FIFO.

Cuối cùng, thứ tự đã thiết lập không tự được xây lại nếu một trường được comparator đọc bị sửa trực tiếp. Khi thay đổi khóa ưu tiên, ứng dụng cần tổ chức bước gỡ/cập nhật/thêm lại hoặc xây cấu trúc mới có kiểm soát. Các bài chuyên về Comparator, tìm/xóa, iterator, đồng hạng và khóa khả biến phân tích chi tiết từng giới hạn này.
## 10. Khi nào nên chọn hàng đợi ưu tiên?

### 10.1. Hợp với việc liên tục chọn phần tử tốt nhất hiện tại

Các tình huống thường có dạng:

- Mỗi lần chọn sự kiện có thời điểm sớm nhất trong các sự kiện đang chờ.
- Mỗi lần chọn công việc có hạn chót hoặc chi phí thấp nhất theo quy ước.
- Giữ một nhóm ứng viên và thường xuyên lấy ứng viên đứng trước.
- Trong một thuật toán, các phần tử mới xuất hiện xen kẽ với việc lấy phần tử ưu tiên hiện tại.

Điểm chung là dữ liệu thay đổi và ứng dụng cần đầu ưu tiên nhiều lần. Không phải lần nào cũng cần toàn bộ danh sách đã sắp xếp.

Nếu chỉ có một lô dữ liệu cố định và cần xuất tất cả theo thứ tự một lần, sắp xếp danh sách có thể dễ hiểu hơn. Nếu cần lấy theo đúng thứ tự đến, dùng hàng đợi FIFO phù hợp. Nếu cần tìm một giá trị tùy ý hoặc truy vấn khoảng thường xuyên, chỉ tính chất heap chưa đáp ứng những yêu cầu đó một cách hiệu quả.

### 10.2. Giới hạn của ưu tiên một đầu

Min-heap cho phép xem nhỏ nhất nhanh; nó không đồng thời đặt lớn nhất ở một vị trí công khai cố định. Không có `getLast()` để lấy phần tử “ưu tiên thấp nhất” chỉ vì cấu trúc mang tên queue.

Với `Comparator.reverseOrder()`, phần tử lớn nhất theo thứ tự tự nhiên được đưa lên đầu, nhưng khi đó nhỏ nhất theo thứ tự tự nhiên lại không còn là đầu. Cần chọn hướng theo câu hỏi chính của ứng dụng.

### 10.3. Truy cập đồng thời là một yêu cầu riêng

`PriorityQueue` không được đồng bộ hóa. Nếu nhiều luồng cùng truy cập và có luồng sửa dữ liệu, cần cơ chế đồng bộ hoặc cấu trúc đồng thời phù hợp với yêu cầu. Một comparator đúng không làm các thao tác trên hàng đợi trở thành an toàn cho nhiều luồng.

Đây là ranh giới cần nhận biết khi chuyển từ ví dụ thuật toán một luồng sang ứng dụng thực. Không nên suy ra các đặc tính chặn, đánh thức luồng hay xử lý tác vụ từ cấu trúc heap.

## 11. Bảng kiểm khi phân tích một heap

| Câu hỏi | Cách tự kiểm |
| --- | --- |
| Gốc có thật sự ưu tiên nhất? | Kiểm tra quan hệ cha–con dọc từng nhánh, theo comparator hiện hành |
| Mảng heap có tăng dần không? | Không bắt buộc; chỉ cần bất biến heap và hình dạng cây hoàn chỉnh |
| Thêm một giá trị mới sửa thế nào? | Đặt vào cuối, rồi sift-up trên đường đến gốc |
| Lấy gốc sửa thế nào? | Chuyển phần tử cuối lên, rồi sift-down với con được ưu tiên hơn |
| Vì sao thao tác sửa heap thường O(log n)? | Chiều cao heap nhị phân hoàn chỉnh tăng theo logarit số phần tử |
| Vì sao peek thường O(1)? | Phần tử đầu đã được duy trì tại gốc; peek không sắp xếp lại |

Không nên viết kiểm thử yêu cầu một mảng heap nội bộ cụ thể cho mọi JDK. Hãy kiểm tra phần tử đầu, tập phần tử còn lại và thứ tự các kết quả `poll()` khi quy tắc so sánh phân biệt được chúng.
## 12. Bài tập về bất biến heap (có lời giải)

**Bài 1.** `[2, 5, 3, 9, 6, 8]` là min-heap hợp lệ không, và có tăng dần không?

**Lời giải:** hợp lệ vì từng cha không lớn hơn con; không tăng dần vì 5 đứng trước 3. Heap không phải dãy đã sắp.

**Bài 2.** `[2, 5, 1, 9, 6, 8]` vi phạm ở đâu?

**Lời giải:** gốc 2 lớn hơn con phải 1; chỉ cần một cạnh sai là đủ để kết luận bất biến bị phá.

**Bài 3.** Với heap `[2, 5, 3, 9, 6, 8]`, thêm 1 rồi lấy đầu. Mỗi lần sửa xong mảng mô hình là gì?

**Lời giải:** sift-up cho `[1, 5, 2, 9, 6, 8, 3]`; lấy ra 1, thay bằng 3 rồi sift-down cho `[2, 5, 3, 9, 6, 8]`. Đây là trace của mô hình đã chọn, không phải hợp đồng mảng nội bộ.

**Bài 4.** Vì sao biết gốc là nhỏ nhất không đồng nghĩa `contains(8)` chạy trong O(log n)?

**Lời giải:** bất biến cha–con không chỉ ra 8 nằm ở nhánh nào; các nhánh không phân hoạch theo giá trị như cây tìm kiếm. Trường hợp xấu phải kiểm tra tuyến tính.
## 13. Tài liệu đối chiếu

- [PriorityQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html): hợp đồng lớp và các phương thức.
- [Comparator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): quy tắc so sánh, đảo chiều và ghép tiêu chí.
- [PriorityQueue trong OpenJDK 17u](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/PriorityQueue.java): đối chiếu cách tổ chức heap nhị phân và các bước duy trì cấu trúc.

Điểm cần giữ khi sử dụng là: comparator quyết định ai đứng trước; heap duy trì đủ quan hệ để đầu ưu tiên ở gốc; thao tác lấy đầu mới lần lượt tạo ra thứ tự ưu tiên. Không thay bước lấy đầu bằng một giả định rằng toàn bộ dữ liệu bên trong đã được sắp xếp.
