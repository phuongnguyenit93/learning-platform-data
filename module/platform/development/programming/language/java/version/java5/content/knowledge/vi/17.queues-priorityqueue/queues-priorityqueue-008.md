# Phần tử có cùng độ ưu tiên và tính ổn định

Hai phần tử khác nhau có thể được comparator của `PriorityQueue` đánh giá là ngang nhau. Khi đó, hàng đợi vẫn giữ cả hai nhưng **không bảo đảm phần tử được thêm trước sẽ được lấy trước**.

Nếu nghiệp vụ yêu cầu công bằng theo thứ tự tiếp nhận trong cùng một mức ưu tiên, cần biểu diễn thứ tự đó thành dữ liệu và đưa nó vào comparator như một khóa phụ.

## 1. “Cùng độ ưu tiên” nghĩa là gì?

Giả sử các công việc có tên và mức ưu tiên:

```java
record Job(String name, int priority, long sequence) {
}

Comparator<Job> byPriority = Comparator.comparingInt(Job::priority);
```

Đây là đoạn minh họa đặt trong một lớp phù hợp, với `Comparator` đã được import.

Với hai công việc:

```java
Job first = new Job("A", 1, 0);
Job second = new Job("B", 1, 1);
```

`byPriority.compare(first, second)` trả 0 vì comparator chỉ đọc `priority`. Tên khác nhau và sequence khác nhau không tạo khác biệt nếu comparator không xét chúng.

Phân biệt ba câu hỏi:

| Câu hỏi | Cơ chế |
| --- | --- |
| Hai phần tử có cùng vị trí ưu tiên không? | Comparator trả 0 hoặc `compareTo` trả 0 |
| Hai giá trị có bằng nhau theo mô hình đối tượng không? | `equals` |
| Hai tham chiếu có trỏ đến cùng một đối tượng không? | `==` |

Ba kết quả này không bắt buộc giống nhau. Với `record Job` ở trên, `first.equals(second)` là `false`, trong khi comparator chỉ theo priority vẫn trả 0.

`PriorityQueue` không phải `Set`: comparator trả 0 không khiến nó tự loại phần tử trùng mức ưu tiên. Nếu thêm hai công việc hợp lệ, cả hai lần thêm vẫn có thể thành công và kích thước tăng hai lần.

## 2. Tính ổn định là giữ thứ tự nào?

Trong ngữ cảnh này, thứ tự ổn định nghĩa là: **giữa các phần tử bằng nhau theo khóa ưu tiên chính, thứ tự tương đối lúc tiếp nhận vẫn được giữ khi lấy ra**.

Giả sử tiếp nhận:

```text
A(priority=2)
B(priority=1)
C(priority=2)
D(priority=1)
```

Nếu ưu tiên số nhỏ trước và giữ FIFO trong từng mức, kết quả mong muốn là:

```text
B, D, A, C
```

`B` đứng trước `D` vì cả hai có priority 1 nhưng `B` được tiếp nhận trước. Tương tự, `A` đứng trước `C` ở priority 2.

Đây không phải FIFO cho toàn bộ hàng đợi. `A` đến trước `B` nhưng vẫn phải nhường do mức ưu tiên khác nhau.

`PriorityQueue` chỉ được cấu hình comparator theo priority không cam kết thứ tự tương đối `B/D` hoặc `A/C`. Kết quả quan sát ở một lần chạy không nâng điều đó thành hợp đồng.

## 3. Vì sao heap có thể đổi vị trí các phần tử đồng hạng?

Heap cần giữ quan hệ cha–con theo comparator để đầu hàng đợi là phần tử có ưu tiên đứng đầu. Nó không cần giữ lịch sử thêm của các phần tử mà comparator coi như nhau.

Khi lấy gốc:

1. Một phần tử ở cuối cấu trúc được đưa vào vùng cần điều chỉnh.
2. Thao tác đẩy xuống phục hồi quan hệ heap.
3. Các phần tử có thể đổi vị trí mà vẫn đúng cùng một thứ tự ưu tiên.

Nếu comparator không có thông tin về thứ tự đến, quan hệ heap không có điều kiện nào buộc phần tử đến sớm hơn phải ở trước phần tử đến muộn hơn.

“Không bảo đảm” không có nghĩa mỗi lần chạy phải ngẫu nhiên hoặc kết quả phải thay đổi liên tục. Một JDK và cùng một chuỗi thao tác có thể cho kết quả lặp lại. Điều không hợp lệ là thiết kế chương trình dựa vào kết quả đó như một bảo đảm FIFO của API.

Cũng không dùng thứ tự vòng lặp `for-each`, iterator hoặc `toString()` để kiểm tra tính ổn định của việc lấy ưu tiên. Chúng không bảo đảm duyệt theo thứ tự `poll`.

## 4. Dùng khóa phụ sequence để biểu diễn thứ tự tiếp nhận

Mỗi công việc được gắn một số thứ tự tăng dần tại thời điểm tiếp nhận:

```text
A(priority=2, sequence=0)
B(priority=1, sequence=1)
C(priority=2, sequence=2)
D(priority=1, sequence=3)
```

Comparator:

```java
Comparator<Job> order = Comparator
        .comparingInt(Job::priority)
        .thenComparingLong(Job::sequence);
```

Cách đọc:

1. So sánh priority trước, số nhỏ được lấy trước.
2. Chỉ khi priority bằng nhau, so sánh sequence.
3. Sequence nhỏ hơn được lấy trước.

Các công việc khác nhau với sequence khác nhau không còn ngang nhau theo comparator đầy đủ, dù chúng vẫn cùng mức ưu tiên nghiệp vụ. Kết quả FIFO trong từng mức đến từ **quy tắc so sánh do chương trình cung cấp**, không phải vì `PriorityQueue` tự thay đổi thành cấu trúc ổn định.

Khóa phụ phải thực sự phản ánh điều muốn giữ. Tên công việc tăng dần tạo thứ tự từ điển, không phải thứ tự tiếp nhận. ID duy nhất nhưng được tạo không theo thứ tự đến cũng không tự mang nghĩa FIFO.

## 5. Chương trình hoàn chỉnh

Ví dụ dùng Java 17+. Phần đầu kiểm tra comparator và việc giữ đủ các phần tử; phần sau dùng một lớp nhận công việc trên một luồng, tự cấp sequence theo thứ tự gọi `submit`.

Lưu thành `EqualPriorityDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class EqualPriorityDemo {
    record Job(String name, int priority, long sequence) {
    }

    static final class StableInbox {
        private final PriorityQueue<Job> queue = new PriorityQueue<>(
                Comparator.comparingInt(Job::priority)
                        .thenComparingLong(Job::sequence));
        private long nextSequence;

        void submit(String name, int priority) {
            long sequence = nextSequence;
            nextSequence = Math.incrementExact(nextSequence);
            queue.offer(new Job(name, priority, sequence));
        }

        Job poll() {
            return queue.poll();
        }
    }

    public static void main(String[] args) {
        Comparator<Job> priorityOnly =
                Comparator.comparingInt(Job::priority);
        Job a = new Job("A", 1, 0);
        Job b = new Job("B", 1, 1);

        System.out.println("compare by priority: "
                + priorityOnly.compare(a, b));
        System.out.println("equals: " + a.equals(b));

        PriorityQueue<Job> tied = new PriorityQueue<>(priorityOnly);
        tied.offer(a);
        tied.offer(b);
        tied.offer(new Job("C", 1, 2));
        System.out.println("tied size: " + tied.size());

        List<Integer> priorities = new ArrayList<>();
        while (!tied.isEmpty()) {
            priorities.add(tied.poll().priority());
        }
        System.out.println("polled priorities: " + priorities);

        StableInbox inbox = new StableInbox();
        inbox.submit("low-A", 5);
        inbox.submit("critical-A", 1);
        inbox.submit("critical-B", 1);
        inbox.submit("low-B", 5);

        Job job;
        while ((job = inbox.poll()) != null) {
            System.out.println(job.name()
                    + " priority=" + job.priority()
                    + " sequence=" + job.sequence());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 EqualPriorityDemo.java
java EqualPriorityDemo
```

Stdout:

```text
compare by priority: 0
equals: false
tied size: 3
polled priorities: [1, 1, 1]
critical-A priority=1 sequence=1
critical-B priority=1 sequence=2
low-A priority=5 sequence=0
low-B priority=5 sequence=3
```

### Tại sao phần đầu không in tên A, B, C theo một thứ tự cố định?

Comparator của `tied` chỉ xét priority. Việc lấy đủ ba mức 1 là kết quả được dùng trong bài; thứ tự tên của ba công việc đồng hạng không được API bảo đảm.

Chương trình chủ động không gán một stdout tên cụ thể cho phần đó. Thay đổi cách triển khai hợp lệ không nên khiến một ví dụ học tập trở thành lời khẳng định sai về FIFO.

Trong `StableInbox`, comparator có sequence nên các tên ở phần sau có thứ tự được xác định. Hai công việc khẩn cấp cùng priority được lấy theo sequence 1 rồi 2; hai công việc priority 5 theo sequence 0 rồi 3.

`Math.incrementExact` giúp tránh âm thầm quay vòng bộ đếm `long`. Nếu bộ đếm không thể tăng nữa, thao tác báo lỗi thay vì sinh sequence làm đảo trật tự. Hệ thống sống rất lâu cần chính sách rõ ràng cho tình huống giới hạn đó; không đặt lại bộ đếm khi hàng đợi còn phần tử cũ.

## 6. Đảo chiều ưu tiên mà vẫn giữ FIFO đồng hạng

Nếu số priority lớn hơn phải được xử lý trước:

```java
Comparator<Job> order = Comparator
        .comparingInt(Job::priority)
        .reversed()
        .thenComparingLong(Job::sequence);
```

`reversed()` ở đây áp dụng cho thứ tự priority, sau đó khóa sequence vẫn tăng dần.

Cẩn thận với:

```java
Comparator<Job> differentOrder = Comparator
        .comparingInt(Job::priority)
        .thenComparingLong(Job::sequence)
        .reversed();
```

Cách thứ hai đảo **toàn bộ** comparator, gồm cả sequence. Nó có thể làm công việc đến sau trong cùng priority đứng trước. Hai biểu thức nhìn gần giống nhưng chính sách đồng hạng khác nhau.

Không tự viết comparator bằng phép trừ như `(int) (a.sequence() - b.sequence())`: hiệu có thể tràn hoặc bị mất thông tin khi ép kiểu. Dùng `thenComparingLong` hoặc `Long.compare`.

## 7. Các điều kiện để chính sách ổn định đáng tin

### Sequence phải riêng cho từng lần tiếp nhận

Nếu thêm lại cùng một đối tượng có cùng sequence nhiều lần, comparator vẫn có thể coi những lần ấy ngang nhau. Muốn thứ tự theo **mỗi lần thêm**, hãy tạo một bản ghi bao ngoài mới và cấp sequence mới cho lần thêm đó.

Các hàng đợi khác nhau có thể có bộ đếm riêng nếu chỉ cần FIFO trong từng hàng đợi. Nếu gộp dữ liệu từ nhiều nguồn, cần xác định một thứ tự chung thay vì giả định các bộ đếm cục bộ không trùng.

### Khóa so sánh không được âm thầm thay đổi

Thay priority hoặc sequence của một phần tử đang nằm trong heap không tự làm nó được đưa về vị trí đúng. Dùng khóa bất biến như record trong chương trình, hoặc xây dựng quy trình loại bỏ rồi thêm lại phiên bản mới phù hợp.

Việc thử `peek` hoặc `poll` nhiều lần không phải cơ chế thông báo rằng khóa đã đổi.

### Nhiều luồng cần xác định rõ thứ tự “đến”

`PriorityQueue` không an toàn khi nhiều luồng cùng truy cập và có luồng sửa. Thay bộ đếm bằng `AtomicLong` không tự làm toàn bộ cấu trúc an toàn.

Ngay cả với một hàng đợi đồng thời, cấp sequence trước khi thêm cũng có thể tạo khác biệt giữa “thứ tự cấp số” và “thứ tự thật sự thêm”: luồng nhận số nhỏ có thể bị dừng trong khi luồng nhận số lớn đã thêm xong.

Nếu cần FIFO theo một điểm tiếp nhận duy nhất, phải thiết kế thao tác cấp số và thêm phù hợp với điểm đó, chẳng hạn bảo vệ cả hai bằng cùng cơ chế đồng bộ. Bên lấy dữ liệu cũng cần tuân thủ hợp đồng đồng thời của cấu trúc.

`PriorityBlockingQueue` hỗ trợ truy cập đồng thời nhưng bản thân nó cũng không cam kết thứ tự giữa các phần tử bằng nhau về priority. Khóa phụ vẫn cần thiết nếu ứng dụng yêu cầu.

## 8. Ổn định không đồng nghĩa với mọi dạng công bằng

Một hàng đợi giữ FIFO trong cùng priority vẫn có thể trì hoãn công việc priority thấp khi công việc ưu tiên cao liên tục xuất hiện.

Khóa sequence trong comparator trên chỉ được xét sau priority. Nó không làm công việc cũ tự được tăng ưu tiên.

Nếu nghiệp vụ cần chống chờ quá lâu, có thể cần chính sách khác như chia lượt theo nhóm hoặc điều chỉnh ưu tiên theo tuổi chờ. Chính sách đó cần thuật toán riêng; comparator đọc thời gian thay đổi liên tục có thể làm quan hệ heap mất hiệu lực nếu các khóa đổi mà cấu trúc không được cập nhật.

Cũng cần phân biệt thứ tự lấy ra với thứ tự hoàn tất. Nhiều worker có thể lấy công việc theo thứ tự đã định nhưng hoàn thành khác thứ tự do thời gian xử lý khác nhau. Hàng đợi ổn định không tự tuần tự hóa toàn bộ quá trình thực thi.

## 9. Cách kiểm chứng đúng

| Điều muốn kiểm chứng | Cách quan sát |
| --- | --- |
| Không mất phần tử đồng hạng | Kiểm tra số phần tử và dữ liệu sau khi lấy hết |
| Đúng thứ tự priority | So sánh các khóa khi `poll` |
| FIFO trong từng priority | So sánh sequence tăng dần trong từng nhóm |
| Không phụ thuộc iterator | Dùng chuỗi `poll`, có thể trên bản sao |
| Có khóa phụ đầy đủ | Kiểm tra những cặp cùng priority nhưng khác thời điểm tiếp nhận |

Đừng viết bài kiểm tra đòi tên đồng hạng phải ra theo FIFO khi comparator chỉ xét priority. Khi đó, bài kiểm tra đang đòi một hợp đồng mà cấu trúc chưa được thiết kế để cung cấp.

## 10. Tự kiểm tra

1. Comparator trả 0 có khiến `PriorityQueue` bỏ một phần tử như tập hợp không?
2. Thấy A luôn ra trước B trong các lần chạy hiện tại có chứng minh FIFO được bảo đảm không?
3. Dùng tên tăng dần làm khóa phụ có giữ thứ tự tiếp nhận không?
4. Đặt `reversed()` sau cả chuỗi priority và sequence thay đổi điều gì?
5. Hàng đợi lấy ra theo FIFO đồng hạng có bảo đảm các công việc hoàn tất cùng thứ tự không?

Đáp án:

1. Không.
2. Không; cần dựa vào hợp đồng và comparator.
3. Không, trừ khi tên thật sự được thiết kế mã hóa thứ tự ấy.
4. Đảo cả khóa phụ, nên sequence lớn có thể đứng trước trong cùng priority.
5. Không; thực thi đồng thời và thời lượng xử lý là vấn đề riêng.

## Tài liệu đối chiếu

Xem hợp đồng đồng hạng của [PriorityQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PriorityQueue.html), phép ghép khóa của [Comparator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html) và ghi chú về khóa phụ của [PriorityBlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html).
