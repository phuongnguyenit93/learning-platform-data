# offer, peek, poll và độ phức tạp của PriorityQueue

## 1. Hàng đợi ưu tiên chọn phần tử tiếp theo theo thứ tự nào?

Một hệ thống đang chờ các công việc có mức ưu tiên khác nhau. Nó cần thêm việc mới, xem việc nào sẽ được chọn tiếp và lấy việc ấy ra để xử lý.

Ba phương thức cốt lõi là:

| Phương thức | Việc thực hiện | Có thay đổi số phần tử không? |
|---|---|---|
| `offer(e)` | Thêm e vào hàng đợi ưu tiên | Tăng một khi thêm thành công |
| `peek()` | Xem phần tử đầu theo thứ tự ưu tiên | Không |
| `poll()` | Lấy và gỡ phần tử đầu theo thứ tự ưu tiên | Giảm một nếu có phần tử |

Khác hàng đợi FIFO, PriorityQueue không mặc định chọn phần tử đến trước. Nó chọn phần tử **nhỏ nhất theo thứ tự đang dùng**. Thứ tự có thể là tự nhiên của kiểu dữ liệu hoặc do Comparator xác định.

Ví dụ, với thứ tự số nguyên tăng dần, thêm `7, 1, 5` thì peek là 1. Nếu nghiệp vụ muốn số lớn được lấy trước, cần một comparator tương ứng; không có khái niệm “số ưu tiên càng lớn luôn được xử lý trước” tự động áp dụng.

[Tài liệu PriorityQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html) xác định phần tử đầu, chính sách null, thứ tự và các cận chi phí thông dụng. Bài này nối những quy tắc đó với cơ chế heap để hiểu vì sao offer, peek và poll có chi phí khác nhau.

## 2. Gốc heap giải thích khác biệt giữa ba thao tác

PriorityQueue dùng heap để duy trì phần tử nhỏ nhất theo comparator tại gốc. `offer()` thêm vào vị trí cuối rồi sift-up khi cần; `peek()` đọc ngay gốc; `poll()` gỡ gốc, chuyển phần tử cuối lên rồi sift-down. Vì các đường sửa heap chỉ dài theo chiều cao cây, chúng không phải một lần sắp xếp toàn bộ n phần tử.

Min-heap có thể biểu diễn bằng `[1, 3, 2, 8, 5, 7, 4]`: các cạnh cha–con hợp lệ dù mảng không tăng dần. Mô hình này không ấn định thứ tự iterator hay bố trí nội bộ của JDK. Bài về cấu trúc heap trình bày từng bước sift-up/sift-down và chỉ số cha–con.
## 3. offer: thêm phần tử rồi khôi phục quan hệ heap

Lời gọi:

```java
// Trích đoạn; cần import java.util.PriorityQueue.
PriorityQueue<Integer> values = new PriorityQueue<>();
boolean accepted = values.offer(7);
```

thêm một lần xuất hiện của giá trị 7. Với PriorityQueue chuẩn, khi thao tác hoàn tất thành công, offer trả true.

### 3.1. Thêm vào cuối vùng dữ liệu

Trong mô hình heap dạng mảng, phần tử mới được đặt ở vị trí kế tiếp sau các phần tử hiện có. Vị trí ấy giữ hình dạng cây nhị phân gần đầy (complete binary tree): các tầng trước tầng cuối đều đầy, còn tầng cuối được lấp từ trái sang phải.

Sau đó có thể cần đưa phần tử đi lên để khôi phục quan hệ cha–con, thường gọi là sift-up.

Ví dụ thêm 0 vào heap minh họa:

```text
trước thêm:
[1, 3, 2, 8, 5, 7, 4]

đặt 0 vào vị trí mới:
[1, 3, 2, 8, 5, 7, 4, 0]

0 nhỏ hơn các cha trên đường đi:
0 vượt 8, rồi 3, rồi 1

một kết quả heap hợp lệ:
[0, 1, 2, 3, 5, 7, 4, 8]
```

Thuật toán không sắp xếp lại mọi cặp phần tử. Nó xử lý một đường từ vị trí mới về phía gốc, có số mức theo logarit của kích thước heap.

### 3.2. Phần tử trùng vẫn được thêm

PriorityQueue không phải Set. Thêm 1 hai lần có thể thành công cả hai lần và làm size tăng hai.

So sánh bằng 0 cũng không có nghĩa loại bỏ một phần tử tương đương như TreeSet. Heap có thể giữ nhiều phần tử cùng ưu tiên.

Nếu cần tránh trùng theo một khóa nghiệp vụ, đó là một yêu cầu bổ sung. Không đọc boolean true của offer thành “đã kiểm tra phần tử này chưa tồn tại”.

### 3.3. Offer không có nghĩa mọi lỗi đều thành false

PriorityQueue không nhận phần tử null, kể cả khi comparator nào đó có khả năng so sánh null. Offer null ném NullPointerException.

Phần tử không so sánh được theo thứ tự yêu cầu có thể gây ClassCastException. Một lớp chưa có Comparable cần comparator phù hợp nếu dùng làm phần tử.

PriorityQueue tự tăng sức chứa, nên không dùng false như một tín hiệu “đã chạm giới hạn số việc cấu hình” cho lớp này. Sức chứa ban đầu không phải giới hạn nghiệp vụ và không tạo cơ chế chờ khi đầy.

## 4. peek: đọc phần tử đầu mà không tiêu thụ

Peek trả phần tử ở đầu theo thứ tự ưu tiên nhưng không gỡ nó.

```text
heap có: 1, 3, 2, 8, 5, 7, 4 theo một bố trí hợp lệ
peek() -> 1
size không đổi
peek() lần nữa, nếu không có thay đổi -> vẫn 1
```

Trong triển khai dựa trên mảng của OpenJDK 17, peek đọc vị trí gốc. Không cần sift-up, sift-down hoặc gọi comparator để tìm lại phần tử nhỏ nhất.

### 4.1. Rỗng thì trả null

PriorityQueue cấm phần tử null, nên null trả về từ peek có thể được dùng để biểu đạt không có phần tử.

Nếu muốn việc thiếu phần tử là một lỗi rõ, phương thức element của Queue cũng chỉ xem đầu nhưng ném NoSuchElementException khi rỗng.

Đừng tự động mở hộp trước khi xét trường hợp rỗng:

```java
// Trích đoạn dễ lỗi: poll hoặc peek có thể trả null.
int next = values.peek();
```

Khi rỗng, phép mở hộp null thành int gây NullPointerException ở mã gọi. Có thể giữ Integer và kiểm tra null, hoặc dùng phương thức có chính sách lỗi phù hợp.

### 4.2. Peek không phải bước đã xử lý xong việc

Nếu vòng lặp cứ peek rồi xử lý mà không gỡ phần tử hoặc thay đổi điều kiện dừng, nó có thể xử lý mãi cùng một phần tử.

Nếu ý định là lấy việc tiếp theo để tiêu thụ, poll biểu đạt đúng thao tác hơn.

Tương tự, peek rồi poll là hai lời gọi. Trong mã có cập nhật xen vào giữa, không mặc định kết quả poll luôn là đúng đối tượng vừa xem. Hãy xử lý chính giá trị được lời gọi lấy phần tử trả về, với cơ chế phối hợp phù hợp nếu chia sẻ nhiều luồng.

## 5. poll: gỡ gốc rồi sửa đường đi xuống

Poll vừa trả về vừa gỡ phần tử đầu. Khi rỗng, nó trả null.

Trong mô hình heap mảng, nếu còn nhiều phần tử:

1. Giữ lại giá trị gốc để trả về.
2. Lấy phần tử cuối vùng dữ liệu làm ứng viên lấp gốc.
3. Giảm số phần tử và bỏ tham chiếu ở ô cuối cũ.
4. Đưa ứng viên xuống theo cây để khôi phục quan hệ heap.

Bước đưa xuống thường gọi là sift-down.

### 5.1. Phải chọn con phù hợp

Với min-heap, nếu hai con tồn tại thì cần xem con nào nhỏ hơn. Nếu ứng viên lớn hơn con nhỏ hơn, đưa con ấy lên và tiếp tục xử lý xuống dưới.

Chỉ so sánh với con trái mà bỏ qua con phải có thể phá quan hệ heap.

Từ heap minh họa ban đầu, poll 1 và dùng giá trị cuối 4:

```text
trước poll:
[1, 3, 2, 8, 5, 7, 4]

lấp gốc bằng 4, bỏ ô cuối:
[4, 3, 2, 8, 5, 7]

đưa 2 lên vì 2 là con nhỏ hơn của gốc:
[2, 3, 4, 8, 5, 7]
```

Ứng viên 4 đã phù hợp với con 7 nên dừng. Đây là một quá trình sửa cục bộ, không phải sắp xếp lại toàn bộ dãy.

### 5.2. Rỗng hoặc chỉ có một phần tử

Nếu rỗng, không có gốc để gỡ và poll trả null.

Nếu chỉ có một phần tử, sau khi lấy nó thì hàng đợi trở thành rỗng; không cần một đường sift-down dài. Cận logarit mô tả quy mô tổng quát, không nói mọi lần gọi có đúng một số bước như nhau.

### 5.3. Poll khác remove(Object)

`remove()` không có đối số của Queue cũng lấy và gỡ đầu, nhưng ném ngoại lệ khi rỗng.

`remove(x)` có đối số là một yêu cầu khác: tìm một phần tử bằng x theo equals rồi gỡ một lần xuất hiện. Nó có thể phải quét hàng đợi và có chi phí tuyến tính.

Không suy từ “poll O(log n)” ra “mọi lời gọi có tên remove trên PriorityQueue đều O(log n)”.

## 6. Chương trình 1: offer, peek, poll và phần tử trùng

Lưu tệp `PriorityQueueApiDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.PriorityQueue;

public class PriorityQueueApiDemo {
    public static void main(String[] args) {
        PriorityQueue<Integer> values = new PriorityQueue<>();
        for (int value : new int[] {7, 1, 5, 1, 3}) {
            System.out.println("offer " + value + " = " + values.offer(value));
        }

        System.out.println("size after offers = " + values.size());
        System.out.println("peek one = " + values.peek());
        System.out.println("peek two = " + values.peek());
        System.out.println("size after peeks = " + values.size());
        System.out.println("poll first = " + values.poll());
        System.out.println("size after one poll = " + values.size());

        List<Integer> output = new ArrayList<>();
        Integer next;
        while ((next = values.poll()) != null) {
            output.add(next);
        }
        System.out.println("remaining poll order = " + output);
        System.out.println("empty = " + values.isEmpty());
        System.out.println("empty peek = " + values.peek());
        System.out.println("empty poll = " + values.poll());

        try {
            values.offer(null);
        } catch (NullPointerException ex) {
            System.out.println("offer null = " + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 PriorityQueueApiDemo.java
java PriorityQueueApiDemo
```

Kết quả của lần chạy kiểm chứng:

```text
offer 7 = true
offer 1 = true
offer 5 = true
offer 1 = true
offer 3 = true
size after offers = 5
peek one = 1
peek two = 1
size after peeks = 5
poll first = 1
size after one poll = 4
remaining poll order = [1, 3, 5, 7]
empty = true
empty peek = null
empty poll = null
offer null = NullPointerException
```

Các chương trình trong bài dùng ngôn ngữ và API có ở Java 17 trở lên, được biên dịch với `--release 17` và chạy kiểm chứng bằng Azul OpenJDK 24.0.2.

Có năm lần offer thành công, kể cả giá trị 1 xuất hiện hai lần. Size bằng 5 xác nhận đây là hàng đợi lưu các lần xuất hiện, không phải tập hợp loại trùng.

Hai lần peek đều trả 1 và không làm giảm size. Poll đầu tiên gỡ một giá trị 1; lần poll tiếp theo vẫn còn một giá trị 1 khác.

Khi lấy hết, peek và poll cùng trả null. Nhưng lý do không phải chúng làm cùng việc: trên một hàng đợi không rỗng, peek chỉ xem còn poll làm thay đổi dữ liệu.

Mã thu kết quả từ poll vào List để bảo vệ thứ tự. Nó không dựa vào thứ tự iterator của PriorityQueue.

## 7. Độ phức tạp: tách heap, mảng và chi phí so sánh

Javadoc PriorityQueue công bố O(log n) cho các thao tác thêm/lấy cơ bản, O(1) cho peek/element/size, và O(n) cho contains hoặc remove theo đối tượng.

Để hiểu đầy đủ một lần gọi thực tế, cần tách ba loại công việc:

```text
quản lý vùng lưu trữ
    +
sửa quan hệ heap
    +
chi phí mỗi lần so sánh
```

### 7.1. Chi phí sửa heap

Với một phép so sánh có chi phí hằng số:

| Thao tác | Công việc chính | Chi phí phần heap |
|---|---|---|
| offer | Đặt phần tử rồi sift-up | O(log n) |
| peek | Đọc gốc | O(1) |
| poll | Gỡ gốc, lấp bằng phần tử cuối, sift-down | O(log n) |
| size | Đọc số lượng đang giữ | O(1) |

Heap dạng cây nhị phân gần đầy có chiều cao O(log n). Sift-up đi một đường lên; sift-down đi một đường xuống. Mỗi mức dùng số phép so sánh có cận hằng số.

Peek rẻ vì công việc duy trì phần tử đầu đã được trả trong những lần cập nhật trước đó.

### 7.2. Một lần offer cần tăng mảng có thể O(n)

PriorityQueue có mảng nền tự tăng. [Mã nguồn PriorityQueue OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/PriorityQueue.java) cho thấy offer kiểm tra chỗ, tăng mảng khi cần rồi thực hiện sift-up; tăng mảng dùng sao chép các tham chiếu sang mảng mới.

Vì thế cần phân biệt:

- Cận O(log n) cho phần điều chỉnh heap.
- Một lần offer đúng lúc tăng mảng có thêm công việc O(n).
- Trên chuỗi thêm với cơ chế tăng theo tỷ lệ, chi phí tăng mảng được phân bổ khấu hao; phần sửa heap vẫn cho cận tổng quát O(log n) khấu hao mỗi lần thêm.

Đọc dòng độ phức tạp trong Javadoc không nên biến thành kết luận “mọi offer riêng lẻ đều có độ trễ không quá một số bước logarit, kể cả cấp phát”.

Sức chứa ban đầu phù hợp có thể giảm các lần tăng ở giai đoạn đầu, nhưng không thay cận của sift-up và không đặt giới hạn tối đa số phần tử.

### 7.3. Comparator có thể không rẻ

Nếu mỗi phép so sánh tốn C, phần sửa heap có thể được biểu đạt như O(C * log n).

Một comparator xét nhiều trường hoặc chuỗi dài có thể tốn hơn so sánh int. Không đặt truy vấn bên ngoài hoặc tác dụng phụ làm thay đổi dữ liệu ưu tiên vào comparator.

Peek trong mô hình triển khai này không phải trả lại chi phí comparator ở mỗi lần xem gốc; nhưng thay đổi thuộc tính mà comparator sử dụng vẫn có thể làm cấu trúc mất đúng đắn.

### 7.4. Lấy cả n phần tử không phải O(n)

Nếu cần tiêu thụ toàn bộ bằng poll, tổng chi phí tổng quát là O(n log n), vì mỗi lần còn phải duy trì heap cho những phần tử tiếp theo.

Duyệt iterator có thể đi qua n phần tử nhưng không bảo đảm thứ tự ưu tiên. Không so sánh hai cách như thể chúng trả cùng một loại kết quả.

Tương tự, thêm n phần tử bằng n lần offer có cận tổng quát O(n log n) cho sửa heap. Đừng gộp mọi cách khởi tạo từ một collection vào cùng lập luận từng-offer: triển khai có thể dùng một thuật toán xây heap theo lô riêng.

## 8. Chương trình 2: đếm so sánh của từng thao tác

Chương trình sau dùng comparator đếm số lần gọi, nhưng kết quả so sánh vẫn luôn là Integer.compare. Nó chuẩn bị đủ chỗ cho phần tử thêm tiếp để quan sát riêng việc sửa heap.

Lưu tệp `PriorityQueueComparisonCostDemo.java`:

```java
import java.util.Comparator;
import java.util.PriorityQueue;

public class PriorityQueueComparisonCostDemo {
    static final class CountingComparator implements Comparator<Integer> {
        private int calls;

        @Override
        public int compare(Integer left, Integer right) {
            calls++;
            return Integer.compare(left, right);
        }

        void reset() {
            calls = 0;
        }

        int calls() {
            return calls;
        }
    }

    public static void main(String[] args) {
        for (int n : new int[] {7, 31, 127, 511}) {
            CountingComparator order = new CountingComparator();
            PriorityQueue<Integer> values =
                    new PriorityQueue<>(n + 1, order);

            for (int value = 0; value < n; value++) {
                values.offer(value);
            }

            order.reset();
            values.offer(-1);
            int offerComparisons = order.calls();

            order.reset();
            Integer head = values.peek();
            int peekComparisons = order.calls();

            order.reset();
            Integer removed = values.poll();
            int pollComparisons = order.calls();

            System.out.println("n=" + n
                    + ", offerComparisons=" + offerComparisons
                    + ", peekComparisons=" + peekComparisons
                    + ", pollComparisons=" + pollComparisons
                    + ", peek=" + head
                    + ", poll=" + removed
                    + ", next=" + values.peek());
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 PriorityQueueComparisonCostDemo.java
java PriorityQueueComparisonCostDemo
```

Kết quả của lần chạy kiểm chứng:

```text
n=7, offerComparisons=3, peekComparisons=0, pollComparisons=4, peek=-1, poll=-1, next=0
n=31, offerComparisons=5, peekComparisons=0, pollComparisons=8, peek=-1, poll=-1, next=0
n=127, offerComparisons=7, peekComparisons=0, pollComparisons=12, peek=-1, poll=-1, next=0
n=511, offerComparisons=9, peekComparisons=0, pollComparisons=16, peek=-1, poll=-1, next=0
```

### 8.1. Vì sao offer dùng nhiều so sánh hơn khi n lớn?

Dữ liệu ban đầu là các số không âm. Offer -1 buộc phần tử mới đi lên về gốc. Khi heap cao hơn, đường đi có thêm mức.

Ở các kích thước đã chọn, lần chạy cho số so sánh offer là 3, 5, 7, 9. Đây là một quan sát về độ dài đường đi, không phải công thức số lần gọi comparator mà API cam kết.

Nếu offer một phần tử đã phù hợp với cha gần vị trí cuối, nó có thể dừng sớm. O(log n) không nói mọi đầu vào đều đi hết chiều cao heap.

### 8.2. Peek không gọi comparator trong ví dụ

Bộ đếm được reset ngay trước peek và kết quả là 0. Phần tử -1 đã ở gốc nhờ offer trước đó, nên peek chỉ đọc nó.

Không suy ra rằng dùng một comparator rất chậm là không quan trọng: offer và poll vẫn cần comparator để tổ chức lại dữ liệu.

### 8.3. Poll sửa đường đi xuống

Poll lấy -1 rồi phải khôi phục đầu tiếp theo là 0. Ở mỗi mức có thể cần so sánh hai con và so sánh ứng viên với con được chọn.

Vì vậy, không nên so số lần gọi của poll với offer rồi mong chúng luôn bằng nhau. Cả hai có cận theo chiều cao heap nhưng làm công việc khác nhau tại mỗi mức.

### 8.4. Đây không phải phép đo thời gian hoặc cấp phát

Constructor nhận n + 1, đủ chỗ cho n phần tử ban đầu và một offer -1. Bộ đếm không đo việc cấp phát, chuyển mảng hoặc số nanosecond.

Nếu một lần offer khác phải tăng mảng, comparator đếm được vẫn không phản ánh toàn bộ công việc ấy. Đây là lý do cần tách phép đếm so sánh khỏi tổng chi phí một lời gọi.

Các con số output đã được kiểm chứng trên môi trường nêu ở chương trình 1. Không đóng đinh chúng thành kiểm tra tương thích giữa các phiên bản JDK.

## 9. Quy tắc so sánh quyết định đầu hàng đợi

Với `Integer` theo thứ tự tự nhiên, `peek()` là số nhỏ nhất hiện tại; dùng `Comparator.reverseOrder()` thì đầu là số lớn nhất theo giá trị số. Heap vẫn chọn phần tử đứng trước nhất theo quy tắc mới.

Nếu hai phần tử so bằng 0, Queue vẫn giữ cả hai và không bảo đảm FIFO giữa chúng. Khi nghiệp vụ cần xử lý theo thứ tự đến trong nhóm đồng hạng, comparator phải ghép thêm một khóa tiếp nhận bất biến. `contains`/`remove(Object)` tìm theo `equals`; đổi trực tiếp trường quyết định ưu tiên không tự làm heap sắp lại. Đây là các điều kiện áp dụng khi diễn giải kết quả của `offer`, `peek` và `poll`.
## 10. Tình huống áp dụng ba thao tác với khóa ưu tiên ghép

Xét các Job `(priority, arrival, name)`: `(5,0,routine)`, `(1,1,urgent-A)`, `(1,2,urgent-B)`, `(3,3,medium)`. Comparator so `priority` tăng rồi `arrival` tăng. Sau khi `offer()` cả bốn, `peek()` trả urgent-A mà không giảm kích thước 4.

Lấy lần lượt bằng `poll()` trả `urgent-A → urgent-B → medium → routine`. Hai urgent cùng priority nhưng được phân biệt bởi arrival; routine đến trước vẫn không được lấy trước do ưu tiên thấp hơn. Nếu chỉ muốn xem trước danh sách, poll một bản sao `new PriorityQueue<>(jobs)` thay vì tiêu thụ hàng đợi gốc.

Ví dụ này bổ sung tình huống cho hai chương trình chạy ở mục 6 và 8. Quy tắc ghép comparator, phần tử đồng hạng và cách xem kết quả theo thứ tự được triển khai đầy đủ trong các bài tương ứng.
## 11. Các mẫu sử dụng và tổng chi phí

### 11.1. Thêm khi có việc mới, lấy khi cần xử lý

Một mẫu một luồng:

```java
// Trích đoạn; Job và process được định nghĩa ở chương trình bao quanh.
PriorityQueue<Job> jobs = new PriorityQueue<>(order);
jobs.offer(newJob);

Job next = jobs.poll();
if (next != null) {
    process(next);
}
```

Giá trị next là công việc đã được gỡ và thực sự dành cho lần xử lý ấy. Không peek một công việc rồi bỏ qua giá trị được poll trả về.

Nếu việc xử lý có thể thất bại, quyền sở hữu, thử lại hoặc khôi phục công việc là chính sách của ứng dụng. Poll chỉ thay đổi collection; nó không tự xác nhận hoàn tất nghiệp vụ.

### 11.2. Chỉ cần biết việc tiếp theo

Dùng peek khi quyết định tiếp theo không muốn lấy việc ra ngay, ví dụ kiểm tra thông tin của đầu hiện tại.

Nhưng không coi một tham chiếu đã peek là một đặt chỗ. Nếu có các cập nhật khác sau đó, đầu có thể thay đổi. Với nhiều luồng, PriorityQueue thông thường không tự an toàn cho truy cập có thay đổi đồng thời.

Một mô hình một luồng sở hữu hàng đợi có giả định khác một hệ thống chia sẻ hàng đợi. Cần giữ điều kiện sử dụng rõ ràng.

### 11.3. Cần toàn bộ thứ tự xử lý

Hai hướng có ý nghĩa khác nhau:

- Poll trên nguồn: nhận thứ tự và tiêu thụ nguồn.
- Tạo bản sao rồi poll: nhận thứ tự nhưng giữ container gốc.
- Sao dữ liệu sang List rồi sort bằng comparator phù hợp: nhận một dãy sắp xếp riêng.

Không dùng for-each trên PriorityQueue như một cách tối ưu thay cho các hướng trên nếu vẫn cần thứ tự ưu tiên.

Tạo và giữ bản sao có chi phí bộ nhớ cho các tham chiếu. Poll toàn bộ có tổng công việc theo heap; sort cũng có chi phí sắp xếp. Không có phương pháp xem tất cả theo thứ tự mà miễn toàn bộ công việc tổ chức dữ liệu.

### 11.4. Nhiều peek không làm giảm size

Nếu ứng dụng có nhiều lần xem đầu xen giữa các lần cập nhật, ưu điểm O(1) của peek có giá trị: heap duy trì đầu khi thêm/lấy, còn việc xem lại không phải quét.

Nhưng một vòng xử lý cần tiến triển. Nếu điều kiện dừng là rỗng mà mã chỉ peek, size không giảm và vòng có thể không bao giờ kết thúc.

## 12. Những độ phức tạp hay bị gộp nhầm

| Nhu cầu hoặc lời gọi | Chi phí/hành vi cần nhớ |
|---|---|
| Xem đầu bằng peek | O(1), không gỡ |
| Lấy đầu bằng poll | O(log n) trong trường hợp tổng quát phần heap |
| Lấy đầu bằng remove() | Cùng vai trò lấy đầu, khác chính sách rỗng |
| Gỡ một đối tượng bằng remove(x) | Có thể O(n) vì phải tìm |
| Kiểm tra contains(x) | O(n) tổng quát, không được lợi như tra cứu trên cây tìm kiếm |
| Thêm bằng offer | Sift-up O(log n); lưu ý tăng mảng |
| Duyệt iterator | Đi qua phần tử nhưng không hứa thứ tự ưu tiên |
| Poll hết n phần tử | O(n log n) tổng quát cho việc tiêu thụ theo ưu tiên |
| Đổi ưu tiên bằng gỡ đối tượng rồi thêm lại | Tính cả bước tìm tuyến tính nếu dùng remove(Object) |

Heap không phải cây tìm kiếm nhị phân. Quan hệ cha–con chỉ đủ để định vị phần tử ưu tiên nhất, không đủ để chọn duy nhất một nhánh khi tìm một giá trị tùy ý.

Đó là lý do contains không tự trở thành O(log n) chỉ vì hình heap có chiều cao logarit.

Khi n thay đổi trong một chuỗi thao tác, phân tích tổng bằng các kích thước tương ứng. Đừng lấy một size ở cuối rồi coi mọi lời gọi trong cả quá trình đã có đúng cùng chi phí.

## 13. Các lỗi sử dụng phổ biến

| Cách hiểu hoặc cách làm | Hậu quả | Cách sửa |
|---|---|---|
| Xem offer như thêm vào một hàng đợi FIFO | Công việc có thể được chọn theo ưu tiên khác thứ tự đến | Xác định comparator và hợp đồng lựa chọn |
| Nghĩ peek đã lấy phần tử | Có thể xử lý lặp cùng đầu | Dùng poll để tiêu thụ |
| Gán kết quả poll vào int ngay | Rỗng có thể gây lỗi mở hộp null | Giữ kiểu tham chiếu và xử lý vắng mặt |
| Nghĩ offer false khi phần tử trùng | PriorityQueue giữ nhiều lần xuất hiện | Quản lý tránh trùng riêng nếu cần |
| Trông chờ FIFO khi cùng ưu tiên | API không bảo đảm ổn định trong ties | Thêm tiêu chí phụ có ý nghĩa |
| Dùng iterator để in thứ tự ưu tiên | Heap không là dãy sắp xếp toàn bộ | Poll, bản sao hoặc sort phù hợp |
| Sửa trực tiếp trường priority đang ở trong queue | Heap không tự cập nhật vị trí | Dùng dữ liệu ổn định và quy trình cập nhật |
| Nghĩ mọi remove đều logarit | remove(Object) cần tìm theo giá trị | Phân biệt chữ ký phương thức |
| Coi mọi offer riêng lẻ đều logarit kể cả cấp phát | Bỏ qua tăng mảng | Tách sửa heap và lưu trữ; hiểu chi phí khấu hao |
| Đặt initial capacity làm giới hạn công việc | Queue vẫn tăng khi cần | Thiết kế giới hạn thực sự ở nơi phù hợp |
| Dùng comparator bằng phép trừ int | Có thể tràn và làm sai thứ tự | Dùng Integer.compare hoặc comparingInt |
| Chia sẻ PriorityQueue mà không phối hợp | Không có hợp đồng an toàn cập nhật đồng thời | Chọn mô hình đồng thời phù hợp |

Ưu tiên thay đổi theo thời gian cũng cần được thiết kế rõ. Một comparator đọc đồng hồ hoặc cấu hình ngoài biến đổi có thể làm quan hệ thứ tự đổi mà heap chưa được cập nhật.

Không cần mọi hệ thống đều có một cơ chế lịch phức tạp, nhưng cần biết thời điểm nào dữ liệu so sánh được giữ ổn định và lúc nào hàng đợi được tổ chức lại.

## 14. Kiểm chứng đúng API và đúng giả định

Một bộ kiểm tra cho mã dùng PriorityQueue nên dựa vào kết quả quan sát được:

1. Offer các giá trị có thứ tự đầu vào khác thứ tự ưu tiên.
2. Peek nhiều lần, kiểm tra size không đổi.
3. Poll một lần, kiểm tra size giảm và đầu tiếp theo đúng.
4. Poll hết, kiểm tra đầy đủ số lượng và thứ tự.
5. Thêm phần tử trùng, xác nhận mọi lần xuất hiện cần giữ còn tồn tại.
6. Kiểm tra rỗng và null đúng chính sách.
7. Kiểm tra comparator đảo nếu nghiệp vụ chọn số lớn trước.
8. Kiểm tra ties theo tiêu chí phụ nếu yêu cầu ổn định.
9. Kiểm tra thay đổi hoặc thay thế công việc theo quy trình cập nhật đã thiết kế.

Không viết kiểm tra rằng iterator phải cho cùng dãy tăng dần với poll. Đó không phải hợp đồng.

Cũng không buộc số lần comparator phải đúng bằng output của chương trình đếm trên mọi phiên bản JDK. Ví dụ đếm giúp giải thích công việc, còn tính tương thích của ứng dụng nên gắn với hành vi cần dùng.

Nếu chỉ thử size hoặc checksum, có thể bỏ qua đảo thứ tự. Nếu chỉ thử bằng một Set, còn có thể bỏ qua cả số lần xuất hiện. Hãy đối chiếu dãy kết quả khi thứ tự là yêu cầu cốt lõi.

Với đối tượng cùng ưu tiên, chỉ khẳng định thứ tự cụ thể khi comparator đã phân biệt đúng theo yêu cầu. Nếu không có tiêu chí phụ, kiểm tra phải chấp nhận các thứ tự hợp lệ trong nhóm tương đương.

## 15. Bài tập áp dụng

### Bài 1: phân biệt xem và lấy

Offer `4, 2, 7`, gọi peek hai lần rồi poll một lần. Size thay đổi thế nào?

**Gợi ý trả lời:** sau offer size là 3; hai peek không đổi size; poll thành công làm size còn 2. Theo natural order, các lần xem và lần lấy đầu đều hướng tới giá trị 2 khi không có thay đổi xen vào.

### Bài 2: phần tử trùng

Offer 1 hai lần. Lần thứ hai có trả false để báo đã tồn tại không?

**Gợi ý trả lời:** không. PriorityQueue không loại trùng; cả hai lần có thể thành công và tạo hai lần xuất hiện.

### Bài 3: đầu theo thứ tự đảo

PriorityQueue dùng reverseOrder, chứa `3, 9, 5`. Peek và poll đầu tiên là gì?

**Gợi ý trả lời:** đều là 9 nếu không có cập nhật xen vào; peek không gỡ, poll gỡ.

### Bài 4: heap cao logarit nhưng contains tuyến tính

Tại sao không thể kết luận contains O(log n) từ chiều cao heap?

**Gợi ý trả lời:** heap không có quy tắc mọi giá trị nhỏ nằm một phía và lớn nằm phía kia như cây tìm kiếm. Với một giá trị tùy ý, có thể phải xem qua nhiều vị trí.

### Bài 5: một offer chậm vì tăng mảng

Điều đó có mâu thuẫn với cách học offer O(log n) không?

**Gợi ý trả lời:** cần tách tầng chi phí. Sift-up logarit, còn một lần tăng mảng có thể tuyến tính; trên chuỗi thao tác có phân tích khấu hao cho lưu trữ.

### Bài 6: cùng ưu tiên, cần đến trước xử lý trước

Hai công việc có cùng priority. Chỉ comparator theo priority có đủ bảo đảm FIFO trong nhóm không?

**Gợi ý trả lời:** không. Cần một tiêu chí phụ biểu đạt thứ tự đến, chẳng hạn arrival nhất quán và phân biệt đúng các công việc.

### Bài 7: xem toàn bộ nhưng giữ nguồn

Có thể poll nguồn để lấy dãy rồi vẫn coi đó là thao tác chỉ xem không?

**Gợi ý trả lời:** không. Poll tiêu thụ nguồn. Có thể poll một bản sao phù hợp hoặc tạo dãy riêng và sắp xếp bằng comparator đúng.

### Bài 8: đổi priority trực tiếp

Một công việc đang nằm trong PriorityQueue được setter đổi mức ưu tiên. Queue có tự sift lại không?

**Gợi ý trả lời:** không. Cần dữ liệu so sánh ổn định hoặc một quy trình cập nhật có kiểm soát; khi dùng remove(Object) để gỡ, phải tính cả chi phí tìm tuyến tính.

Khi chọn giữa offer, peek và poll, hãy xác định rõ đang thêm, chỉ xem hay tiêu thụ. Khi đọc độ phức tạp, hãy nêu rõ phần heap, cấp phát mảng và chi phí comparator đang được tính thế nào.
