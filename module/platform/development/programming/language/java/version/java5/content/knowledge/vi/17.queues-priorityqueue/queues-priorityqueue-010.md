# Rủi ro thay đổi khóa so sánh sau khi thêm phần tử

`PriorityQueue` sắp xếp vị trí phần tử dựa trên thứ tự tự nhiên hoặc comparator. Sau khi phần tử đã vào hàng đợi, việc sửa một trường của đối tượng **không tự thông báo cho heap rằng thứ tự đã thay đổi**.

Hậu quả nguy hiểm là dữ liệu nhìn thấy trên đối tượng đã mới, nhưng vị trí của nó trong cấu trúc vẫn được xác lập từ trước. Phần tử đáng lẽ cần được lấy trước có thể nằm sâu bên dưới.

Nguyên tắc thực hành: **giữ ổn định các dữ liệu mà phép so sánh phụ thuộc trong thời gian phần tử nằm trong hàng đợi**.

## 1. Khóa so sánh là những dữ liệu nào?

Giả sử:

```java
Comparator<Job> order = Comparator.comparingInt(Job::priority);
```

Đây là đoạn minh họa khi đã có kiểu `Job` và import `Comparator`. Khóa so sánh là `priority`.

Nếu comparator là:

```java
Comparator<Job> order = Comparator
        .comparingInt(Job::priority)
        .thenComparingLong(Job::sequence);
```

thì cả `priority` và `sequence` ảnh hưởng quan hệ thứ tự. Sửa một trong hai đều cần được xem là thay đổi khóa.

Một trường khác chỉ để hiển thị, không được comparator hoặc `compareTo` đọc, có thể không ảnh hưởng heap. Tuy nhiên, nếu trường đó tham gia `equals`, nó vẫn có thể ảnh hưởng các thao tác tìm hoặc loại bỏ theo đối tượng.

Không chỉ trường trong phần tử mới là khóa. Comparator đọc từ bảng cấu hình ngoài, trạng thái hệ thống hoặc thời gian hiện tại cũng có thể thay đổi cách xếp thứ tự dù đối tượng công việc không bị sửa trực tiếp.

## 2. Heap cần một quan hệ ổn định

Với ưu tiên số nhỏ trước, giả sử heap:

```text
       A:10
       /  \
    B:20  C:30
```

Quan hệ cha–con đang đúng: 10 không lớn hơn 20 và 30.

Sau khi gọi một setter đổi C thành priority 1, các tham chiếu trong cấu trúc không tự đổi vị trí:

```text
       A:10
       /  \
    B:20  C:1
```

Quan hệ 10 không lớn hơn 1 đã sai. Hàng đợi không thể phát hiện mọi thay đổi bên trong mọi đối tượng mà nó đang giữ chỉ từ việc lưu các tham chiếu.

Các thao tác như thêm và lấy đầu có bước điều chỉnh heap liên quan. Nhưng sửa trường bằng setter là thao tác bên ngoài cơ chế ấy; `PriorityQueue` không có API nhận thông báo “khóa của phần tử này vừa đổi” hay thao tác `decreaseKey` chuyên dụng.

Vì thế, không nên trông chờ `peek` quét toàn bộ phần tử để tìm lại giá trị nhỏ nhất sau mỗi lần gọi. Cũng không trông chờ một lần `poll` hoặc thêm một phần tử bất kỳ sẽ sửa đúng toàn bộ cấu trúc đã bị phá vỡ.

## 3. Chương trình quan sát lỗi và cách cập nhật an toàn

Ví dụ chạy trên Java 17+. Phần đầu cố ý vi phạm điều kiện ổn định khóa để quan sát hành vi trên JDK 21 được dùng kiểm chứng. Phần sau loại phần tử trước khi đổi priority và thêm lại.

Lưu thành `MutablePriorityDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class MutablePriorityDemo {
    static final class Job {
        private final String name;
        private int priority;

        Job(String name, int priority) {
            this.name = name;
            this.priority = priority;
        }

        int priority() {
            return priority;
        }

        void setPriority(int priority) {
            this.priority = priority;
        }

        @Override
        public String toString() {
            return name + ":" + priority;
        }
    }

    static PriorityQueue<Job> newQueue() {
        return new PriorityQueue<>(Comparator.comparingInt(Job::priority));
    }

    static List<String> drain(PriorityQueue<Job> queue) {
        List<String> result = new ArrayList<>();
        while (!queue.isEmpty()) {
            result.add(queue.poll().toString());
        }
        return result;
    }

    public static void main(String[] args) {
        PriorityQueue<Job> broken = newQueue();
        Job a = new Job("A", 10);
        Job b = new Job("B", 20);
        Job c = new Job("C", 30);
        broken.offer(a);
        broken.offer(b);
        broken.offer(c);

        System.out.println("before mutation: " + broken.peek());
        c.setPriority(1);
        System.out.println("root after mutation: " + broken.peek());
        System.out.println("C precedes root by comparator: "
                + (c.priority() < broken.peek().priority()));

        PriorityQueue<Job> safe = newQueue();
        Job x = new Job("A", 10);
        Job y = new Job("B", 20);
        Job z = new Job("C", 30);
        safe.offer(x);
        safe.offer(y);
        safe.offer(z);

        boolean removed = safe.remove(z);
        System.out.println("removed before update: " + removed);
        if (!removed) {
            throw new IllegalStateException("job is not queued");
        }
        z.setPriority(1);
        safe.offer(z);
        System.out.println("safe poll order: " + drain(safe));
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 MutablePriorityDemo.java
java MutablePriorityDemo
```

Stdout quan sát được trên JDK 21 dùng để kiểm chứng:

```text
before mutation: A:10
root after mutation: A:10
C precedes root by comparator: true
removed before update: true
safe poll order: [C:1, A:10, B:20]
```

### Đọc kết quả đúng cách

Sau khi C đổi priority, đối tượng C thật sự có giá trị 1, nhưng đầu cấu trúc vẫn là A trong lần chạy này. Dòng so sánh tiếp theo chứng minh có phần tử được phép so sánh xếp trước đầu hiện tại.

Đây là thí nghiệm về một cấu trúc đã bị làm sai giả định sử dụng. Không lấy stdout của phần `broken` làm hợp đồng rằng mọi triển khai hay mọi chuỗi thao tác sau khi sửa khóa đều phải biểu hiện giống hệt.

Phần `safe` không phá quan hệ heap: loại C khi khóa của nó vẫn là 30, cập nhật sau khi nó không còn trong hàng đợi, rồi thêm phiên bản trạng thái mới. Lần thêm lại được phép điều chỉnh vị trí theo priority 1.

Chương trình chạy trên một luồng và mỗi công việc chỉ có một lần xuất hiện trong từng hàng đợi. Các điều kiện này quan trọng khi áp dụng mẫu vào hệ thống lớn hơn.

## 4. Loại trước, sửa sau, thêm lại

Quy trình cập nhật đơn giản:

1. Xác định đúng phần tử đang nằm trong hàng đợi.
2. Loại phần tử đó và kiểm tra kết quả.
3. Thay đổi khóa khi phần tử không còn được cấu trúc quản lý.
4. Thêm lại để heap xác lập vị trí mới.

Không nên đổi khóa trước rồi mới coi `remove + offer` như một phép sửa tổng quát. Trong khoảng thời gian đó, cấu trúc đã không còn đáp ứng quan hệ heap; các thao tác đồng thời hoặc việc sửa thêm phần tử khác có thể làm tình huống phức tạp hơn.

### remove(Object) dùng equals, không dùng comparator để định danh

`PriorityQueue.remove(Object)` loại một phần tử bằng với đối số theo `equals`. Nó không có nghĩa “loại phần tử có cùng priority”.

Trong chương trình, `Job` không override `equals`, nên dùng tham chiếu đã giữ giúp chọn chính đối tượng đó. Trong mô hình khác, hai công việc có thể bằng nhau theo `equals` dù không phải cùng đối tượng; cần thiết kế nhận diện phù hợp.

Nếu một đối tượng được thêm vào hàng đợi nhiều lần, loại một lần không nhất thiết loại mọi tham chiếu đến nó. Sửa khóa sau đó vẫn ảnh hưởng những lần còn lại. Quy trình cần bảo đảm không còn lần xuất hiện nào chịu tác động, hoặc dùng bản ghi riêng cho từng lần tiếp nhận.

### Chi phí cập nhật

`remove(Object)` cần tìm phần tử tuyến tính: `O(n)`. Thêm lại có phần điều chỉnh heap `O(log n)`, nên cập nhật theo cách này có chi phí tổng thể `O(n)`.

Nếu hệ thống cần cập nhật ưu tiên theo ID với tần suất rất cao, có thể cần cấu trúc có chỉ mục hoặc một thiết kế hàng đợi khác. `PriorityQueue` thông thường không tự cung cấp bản đồ từ ID đến vị trí heap.

## 5. Dùng phần tử bất biến hoặc bản ghi chụp khóa

Một lựa chọn dễ kiểm soát hơn là lưu khóa bất biến:

```java
record QueueEntry(String jobId, int priority, long sequence) {
}
```

Thay đổi nghiệp vụ tạo bản ghi mới thay vì gọi setter trên bản ghi đang nằm trong heap.

Nếu công việc thực tế có trạng thái thay đổi được, không nên để comparator đọc trạng thái đó qua tham chiếu:

```java
// Có thể vẫn rủi ro nếu job.priority() thay đổi:
// record Entry(Job job) {}
// Comparator<Entry> order = Comparator.comparingInt(e -> e.job().priority());
```

Một record chỉ làm các trường tham chiếu của nó không gán lại được; nó không tự làm đối tượng được tham chiếu trở thành bất biến. Muốn chụp khóa, hãy lưu chính giá trị priority mà bản ghi hàng đợi phải sử dụng.

Khi thay bản ghi cũ bằng bản ghi mới, cần quyết định chính sách sequence:

- Giữ sequence cũ nếu muốn giữ vị trí tiếp nhận ban đầu trong nhóm đồng hạng.
- Cấp sequence mới nếu lần cập nhật được coi là lần tiếp nhận mới.

Không có một lựa chọn đúng cho mọi nghiệp vụ, nhưng lựa chọn phải được thể hiện rõ trong dữ liệu.

## 6. Dựng lại khi nhiều khóa hoặc comparator thay đổi

Nếu cần thay chính sách so sánh toàn bộ hàng đợi, hãy thu thập các phần tử và thêm vào một hàng đợi mới với comparator phù hợp:

```java
// Minh họa trong một phương thức, với source và newOrder đã được khai báo.
List<Job> items = new ArrayList<>(source);
PriorityQueue<Job> rebuilt = new PriorityQueue<>(newOrder);
rebuilt.addAll(items);
```

Việc duyệt nguồn không cần có thứ tự ưu tiên; mục đích là lấy đủ phần tử rồi để các lần thêm thiết lập heap mới.

Trong khi dựng lại, các khóa và comparator phải ổn định, và việc truy cập dữ liệu phải được điều phối nếu có nhiều luồng. Sau khi dựng xong, cần chuyển bên sử dụng sang cấu trúc mới một cách nhất quán.

Đừng mặc định `new PriorityQueue<>(source)` là API “sửa mọi heap đã bị đổi khóa”. Constructor sao chép có thể tận dụng cấu trúc của một hàng đợi nguồn; không nên dựa vào việc nó sẽ so sánh lại mọi phần tử để sửa một nguồn đã mất tính hợp lệ. Cách tạo hàng đợi rỗng rồi thêm toàn bộ thể hiện rõ ý định xác lập lại thứ tự.

Mẫu `addAll` vào hàng đợi rỗng có mức chi phí tối đa quen thuộc `O(n log n)` theo các lần thêm. Nếu việc dựng lại xảy ra thường xuyên, cần đánh giá thiết kế và chi phí thực tế.

## 7. Một hướng khác: bản ghi có phiên bản và bỏ qua bản cũ

Với số lượng cập nhật lớn, có thể dùng bản ghi bất biến mang `jobId`, priority đã chụp và số phiên bản:

1. Mỗi lần cập nhật tạo một bản ghi mới và thêm vào heap.
2. Lưu phiên bản mới nhất của từng công việc trong một bảng riêng.
3. Khi lấy ra, bỏ qua bản ghi không còn là phiên bản hiện hành.
4. Chỉ xử lý bản ghi còn hiệu lực.

Hướng này thường gọi là vô hiệu hóa trì hoãn (lazy invalidation). Nó tránh tìm tuyến tính để xóa từng bản cũ, nhưng đổi lại có thêm bộ nhớ, bản ghi quá hạn và yêu cầu dọn dẹp.

Kích thước heap khi ấy không còn đồng nghĩa với số công việc còn hiệu lực. Logic tiếp nhận, đếm, hủy và cập nhật đều phải hiểu phiên bản. Đây là một thiết kế riêng cần triển khai đầy đủ, không phải chỉ thêm một trường version là tự có độ đúng.

## 8. Rủi ro từ comparator phụ thuộc trạng thái ngoài

Ngay cả khi phần tử bất biến, comparator như sau vẫn có thể không ổn định:

```java
// Ý tưởng minh họa, không phải mã hoàn chỉnh:
// compare(a, b) đọc mức ưu tiên hiện tại từ một Map có thể thay đổi.
```

Khi map đổi, thứ tự giữa các phần tử đã có trong heap có thể đảo. Heap không tự quan sát map để cập nhật mọi vị trí.

Tương tự, comparator tính mức khẩn cấp từ thời gian hiện tại hoặc từ cấu hình có thể đổi trong mỗi lần so sánh dễ làm giả định thứ tự bị phá vỡ. Nếu quan hệ giữa hai phần tử thay đổi theo thời gian, cần một cơ chế tái lập thứ tự hoặc thuật toán lập lịch phù hợp.

Comparator nên vừa đáp ứng hợp đồng so sánh, vừa cho một quan hệ ổn định trong giai đoạn cấu trúc dựa vào nó.

## 9. Đồng bộ không tự giải quyết việc đổi khóa

Khóa một setter để chỉ một luồng sửa tại một thời điểm không tự làm heap sắp lại. Sau khi setter kết thúc, vị trí vẫn có thể sai.

Nếu dùng quy trình loại–đổi–thêm trong môi trường nhiều luồng:

- Bảo vệ toàn bộ quy trình theo cùng hợp đồng truy cập mà bên thêm và lấy tuân thủ.
- Ngăn bên khác thay đổi khóa qua những tham chiếu còn giữ.
- Xác định chính sách khi công việc đã được lấy ra trước khi yêu cầu cập nhật đến.

`PriorityBlockingQueue` cung cấp an toàn cho các thao tác cấu trúc theo hợp đồng của nó; nó không theo dõi setter trên từng đối tượng để tự định vị lại phần tử. Cấu trúc đồng thời không thay thế thiết kế khóa so sánh bất biến.

## 10. Thực hành

1. Trong phần `broken`, đổi A từ priority 10 thành 100; có được kỳ vọng `peek` tự chọn lại mọi phần tử không?
2. Sửa một trường mô tả không tham gia comparator có nhất thiết làm sai heap không?
3. Thêm cùng đối tượng Job hai lần rồi chỉ remove một lần trước khi đổi khóa có đủ không?
4. Một record chứa đối tượng Job thay đổi được có tự bảo vệ priority không?
5. Vì sao cần dựng hàng đợi mới khi thay một chính sách comparator ảnh hưởng mọi phần tử?

Đáp án:

1. Không; thao tác sửa trường không tự điều chỉnh heap.
2. Không nhất thiết, nhưng vẫn cần xét tác động đến `equals` và các hợp đồng khác.
3. Không; lần xuất hiện còn lại vẫn chịu thay đổi của cùng đối tượng.
4. Không; cần chụp giá trị khóa hoặc bảo đảm đối tượng được tham chiếu không đổi.
5. Quan hệ heap cũ được xác lập theo quy tắc trước đó và không tự chuyển sang quan hệ mới.

## Tài liệu đối chiếu

Xem hợp đồng và độ phức tạp của [PriorityQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PriorityQueue.html), quy tắc của [Comparator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html) và triển khai tham khảo [OpenJDK 21 PriorityQueue](https://github.com/openjdk/jdk21u/blob/master/src/java.base/share/classes/java/util/PriorityQueue.java). Thí nghiệm setter trong bài là mã minh họa được kiểm chứng, không phải một hợp đồng cho cấu trúc đã bị phá giả định.
