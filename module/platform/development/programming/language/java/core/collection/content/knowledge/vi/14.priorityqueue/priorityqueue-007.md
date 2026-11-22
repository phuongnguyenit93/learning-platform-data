# Rủi ro sửa độ ưu tiên của đối tượng đang nằm trong queue

## 1. Setter có thể đổi dữ liệu mà không đổi vị trí trong heap

Giả sử một PriorityQueue chọn công việc có số priority nhỏ trước. Nó đang giữ A:10, B:20, C:30, D:40 và E:50. Sau đó, mã gọi sửa chính đối tượng D thành D:1.

Theo giá trị hiện tại, D phải được ưu tiên trước A. Nhưng PriorityQueue không tự nghe mọi setter của phần tử để đưa D lên đầu. Đối tượng vẫn nằm ở vị trí được chọn khi nó còn có priority 40.

Có ba tầng cần giữ riêng:

```text
tham chiếu được queue lưu
        |
        v
đối tượng và dữ liệu hiện tại của nó
        |
        v
quan hệ thứ tự mà comparator đọc

vị trí trong heap đã được tổ chức ở một thời điểm trước
```

Sửa trường của đối tượng thay đổi dữ liệu mà comparator có thể đọc, nhưng không tự thực hiện offer, remove hoặc một thao tác cập nhật heap.

Hậu quả thường là chọn sai công việc theo ưu tiên hiện tại, trong khi size vẫn đúng và đối tượng vẫn tồn tại trong queue.

Bài này giải thích rủi ro ấy, cách nhận biết và những cách cập nhật có thể kiểm soát. Các hợp đồng API liên quan được đối chiếu với [PriorityQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).

## 2. Bất biến heap cần đúng trước mỗi thao tác tiếp theo

Với min-heap theo số priority tăng dần, một bất biến cơ bản là:

```text
priority của cha <= priority của mỗi con
```

Một cấu trúc minh họa hợp lệ:

```text
             A:10
            /    \
         B:20    C:30
         /  \
      D:40  E:50
```

Sửa D:40 thành D:1 nhưng không cập nhật cấu trúc:

```text
             A:10
            /    \
         B:20    C:30
         /  \
       D:1  E:50
```

Quan hệ B:20 đứng trước D:1 không còn đúng. Vì D chưa được đưa lên, gốc A:10 cũng không còn là phần tử nhỏ nhất theo các giá trị hiện tại.

Đây là hình minh họa phù hợp với thí nghiệm tiếp theo, không phải hợp đồng về hình dạng nội bộ trên mọi JDK.

### 2.1. Đổi theo cả hai hướng đều có thể gây lỗi

Nếu giảm số priority của một phần tử phía dưới, nó có thể cần đi lên. Nếu tăng số priority của phần tử ở đầu, nó có thể cần đi xuống.

Ví dụ, gốc A:10 đổi thành A:100 có thể vẫn được peek trả về trước B:20, vì thao tác sửa trường không tự thực hiện sift-down.

Nên nói rõ quy ước: trong bài, **số nhỏ hơn được lấy trước**. Cụm “tăng ưu tiên” trong nghiệp vụ đôi khi lại có nghĩa giảm con số; tránh dùng từ mơ hồ khi giải thích thay đổi.

### 2.2. Một lần sửa có thể tình cờ chưa làm sai quan hệ

Không phải mọi giá trị thay đổi đều lập tức cho output sai trong mọi bố trí. Một phần tử có thể vẫn còn nằm trong miền hợp lệ giữa cha và con sau thay đổi nhỏ.

Điều đó không tạo ra một cơ chế tự cập nhật. Chỉ vì một test chưa thấy lỗi, không thể kết luận việc sửa tùy ý trường comparator đọc là an toàn.

Một quy tắc dễ kiểm soát là giữ dữ liệu quyết định thứ tự ổn định trong thời gian phần tử nằm trong queue, và thực hiện thay đổi qua một luồng cập nhật tường minh.

### 2.3. Poll không có nhiệm vụ kiểm tra lại toàn bộ dữ liệu

Poll dựa trên giả định rằng heap đang hợp lệ: lấy gốc, đưa phần tử cuối vào vị trí cần lấp rồi sửa một đường đi xuống.

Nó không quét mọi phần tử để tìm lại min theo dữ liệu vừa bị sửa bên ngoài. Một bất biến đã bị phá ở đường khác có thể tiếp tục sai sau một lần poll.

Cũng không dùng một offer bất kỳ như phép “làm mới toàn bộ”. Offer sửa đường của phần tử mới, không tự rà soát mọi đối tượng đã bị setter đổi.

## 3. Chương trình 1: contains vẫn đúng nhưng đầu ưu tiên sai

Lưu tệp `MutablePriorityFailureDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class MutablePriorityFailureDemo {
    static final class Task {
        private final String id;
        private int priority;

        Task(String id, int priority) {
            this.id = id;
            this.priority = priority;
        }

        int priority() {
            return priority;
        }

        void changePriority(int newPriority) {
            priority = newPriority;
        }

        @Override
        public String toString() {
            return id + ":" + priority;
        }
    }

    public static void main(String[] args) {
        Comparator<Task> order = Comparator.comparingInt(Task::priority);
        Task a = new Task("A", 10);
        Task b = new Task("B", 20);
        Task c = new Task("C", 30);
        Task d = new Task("D", 40);
        Task e = new Task("E", 50);
        List<Task> input = List.of(a, b, c, d, e);
        PriorityQueue<Task> tasks = new PriorityQueue<>(order);
        tasks.addAll(input);

        System.out.println("head before change = " + tasks.peek());
        d.changePriority(1);

        System.out.println("size after change = " + tasks.size());
        System.out.println("contains changed reference = " + tasks.contains(d));
        System.out.println("minimum by fresh scan = "
                + input.stream().min(order).orElseThrow());
        System.out.println("head after change = " + tasks.peek());
        System.out.println("first poll after change = " + tasks.poll());
        System.out.println("head after one poll = " + tasks.peek());

        List<String> output = new ArrayList<>();
        Task next;
        while ((next = tasks.poll()) != null) {
            output.add(next.toString());
        }
        System.out.println("remaining poll order = " + output);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 MutablePriorityFailureDemo.java
java MutablePriorityFailureDemo
```

Kết quả của lần chạy kiểm chứng:

```text
head before change = A:10
size after change = 5
contains changed reference = true
minimum by fresh scan = D:1
head after change = A:10
first poll after change = A:10
head after one poll = B:20
remaining poll order = [B:20, D:1, C:30, E:50]
```

Đây là thí nghiệm cố ý làm mất bất biến heap. Mã dùng ngôn ngữ và API có ở Java 17 trở lên, được biên dịch với `--release 17` và chạy kiểm chứng bằng Azul OpenJDK 24.0.2. Cơ chế được đối chiếu với mã nguồn OpenJDK 17.

Các dòng chọn phần tử sau thay đổi là quan sát của triển khai đã chạy, không phải một hợp đồng rằng mọi JDK phải sai theo đúng cùng chuỗi ấy.

### 3.1. Size và contains không kiểm tra thứ tự heap

Size vẫn là 5. Contains với đúng tham chiếu d vẫn trả true. Điều này phù hợp với việc queue còn giữ đối tượng ấy.

Nhưng hai câu hỏi khác nhau:

```text
Đối tượng có còn ở trong queue không?
Queue có đang chọn đúng đối tượng ưu tiên nhất không?
```

Fresh scan dùng dữ liệu hiện tại tìm được D:1. Peek của heap cũ vẫn trả A:10. Việc tồn tại thành viên không chứng minh chỉ mục ưu tiên còn đúng.

### 3.2. Một poll chưa sửa hết vấn đề

Sau khi poll A:10, đầu tiếp theo vẫn là B:20 dù D:1 còn chờ. Chuỗi còn lại là B:20, D:1, C:30, E:50, cho thấy không thể dựa vào việc poll một lần để chữa toàn bộ heap.

Trong mô hình minh họa, sau lần poll đầu có thể còn quan hệ:

```text
        B:20
       /    \
     D:1    C:30
     /
   E:50
```

Đường sửa cục bộ đã làm công việc của nó theo giả định cũ, nhưng đầu vẫn không nhỏ hơn mọi phần tử.

### 3.3. Không có ngoại lệ không có nghĩa đúng ưu tiên

Setter không thêm hoặc gỡ một mục của queue. Không có một yêu cầu chung buộc nó phải tăng bộ đếm thay đổi cấu trúc hay ném ConcurrentModificationException.

Chương trình có thể chạy hết, trả đủ các đối tượng, nhưng thứ tự xử lý đã sai. Đây là lỗi của bất biến sắp xếp dữ liệu, không nhất thiết là một lỗi thiếu phần tử hoặc một ngoại lệ truy cập bộ nhớ.

## 4. Vì sao queue không tự chụp hoặc theo dõi priority?

### 4.1. Queue giữ tham chiếu tới phần tử

Nếu đưa một đối tượng khả biến vào PriorityQueue, queue không mặc định clone toàn bộ đối tượng hay lưu sẵn một bản priority bất biến độc lập.

Một tham chiếu khác vẫn có thể gọi setter. Khi comparator được gọi lại, nó thấy dữ liệu mới; nhưng các quan hệ vị trí được tạo trước đó chưa chắc phù hợp dữ liệu mới.

Vì vậy, việc comparator đọc được số mới không đồng nghĩa cấu trúc đã được đặt lại đúng chỗ.

### 4.2. Comparator đúng tại từng thời điểm vẫn chưa đủ

Comparator dùng Integer.compare cho một trường priority có thể hợp lý về dấu và tính bắc cầu tại từng trạng thái dữ liệu.

Vấn đề vòng đời là quan hệ so sánh giữa những phần tử đang nằm trong heap đã thay đổi mà không đi qua thao tác duy trì cấu trúc.

Cần kiểm tra cả hai tầng:

1. Comparator có biểu đạt một quan hệ thứ tự hợp lệ không?
2. Dữ liệu mà quan hệ ấy dựa vào có được giữ ổn định giữa các lần cập nhật queue không?

Sửa một công thức so sánh không tự giải quyết một setter đang thay dữ liệu ngoài luồng quản lý.

### 4.3. final và record chỉ bảo vệ điều chúng thực sự giữ

`final PriorityQueue<Task>` chỉ ngăn gán biến đó sang một queue khác. Nó không làm phần tử Task bất biến.

`final Comparator<Task>` chỉ cố định tham chiếu comparator. Nếu comparator đọc một Map cấu hình có thể đổi, kết quả thứ tự vẫn có thể đổi.

Record cũng không tự bất biến sâu. [Tài liệu Record Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html) mô tả record là bất biến nông: một thành phần tham chiếu có thể trỏ tới đối tượng còn sửa được.

Ví dụ, record chứa một PriorityState khả biến vẫn có thể đổi kết quả so sánh khi PriorityState đổi. Một record chỉ có số nguyên và String bất biến như ví dụ an toàn bên dưới dễ giữ ổn định hơn.

### 4.4. Thay đổi gián tiếp cũng cần được rà soát

Đường làm đổi ưu tiên có thể là:

- Setter trực tiếp của trường priority.
- Đối tượng lồng bên trong mà comparator đọc.
- Một Map ngoài được comparator dùng tra cứu mức hiện tại.
- Một cờ cấu hình làm đảo hoặc đổi tiêu chí so sánh.
- Một quy tắc tính điểm theo trạng thái bên ngoài làm hai công việc đổi tương quan.

Điều cần xem là quan hệ thứ tự có thay đổi không. Không phải mọi dữ liệu bên ngoài đều gây lỗi, nhưng mọi nguồn có thể làm đổi quan hệ cần một cơ chế cập nhật cấu trúc phù hợp.

## 5. contains, equals và comparator có vai trò khác nhau

PriorityQueue dùng comparator hoặc Comparable để tổ chức ưu tiên. Nhưng contains và remove(Object) tìm theo equals.

Trong ví dụ đầu, Task không override equals nên dùng đồng nhất đối tượng mặc định; contains(d) thành công với đúng tham chiếu. Lớp khác có equals theo id sẽ có cách nhận diện khác.

Các vai trò nên được ghi rõ:

| Việc | Quan hệ được dùng |
|---|---|
| Chọn đầu ưu tiên, sift-up/sift-down | Comparator hoặc Comparable |
| contains(x), remove(x) theo đối tượng | Equals |
| So cùng một đối tượng qua hai tham chiếu | Có thể dùng == khi chính thuật toán cần nhận diện tham chiếu |

Không giải thích lỗi PriorityQueue bằng quy tắc ngăn băm của HashSet. PriorityQueue không dùng hashCode để quyết định vị trí ưu tiên hoặc để thực hiện bước tìm tuyến tính của remove(Object).

### 5.1. Remove sau mutation có thể vẫn tìm được

Vì remove(Object) tìm theo equals, thay priority không nhất thiết làm nó mất khả năng tìm mục. Nếu equals hoặc đúng tham chiếu vẫn khớp, lời gọi có thể trả true.

Nhưng việc tìm được để gỡ không chứng minh khoảng thời gian trước đó queue đã trả đúng ưu tiên. Nếu đã có một poll sai xảy ra, gỡ được về sau không hoàn tác quyết định xử lý cũ.

Cách kiểm soát tốt hơn là gỡ khi dữ liệu cũ còn ổn định, xác nhận gỡ thành công, rồi đổi hoặc tạo giá trị mới và thêm lại.

### 5.2. Remove chỉ gỡ một lần xuất hiện bằng nhau

PriorityQueue cho phép phần tử trùng. Nếu cùng một đối tượng được offer nhiều lần, remove một lần không bảo đảm không còn tham chiếu ấy trong queue.

Nếu có nhiều đối tượng khác nhau mà equals xem là bằng nhau, remove(target) cũng không mặc định là một API gỡ theo đúng danh tính tham chiếu của target.

Trước khi dùng remove để cập nhật một công việc, cần một chính sách định danh và số lần xuất hiện rõ. Đừng giả định queue tự bảo đảm mỗi id chỉ có một bản ghi.

### 5.3. Tính chi phí đúng

Remove(Object) có thể cần tìm qua n phần tử nên là O(n) tổng quát, rồi còn duy trì heap quanh vị trí gỡ. Offer tiếp theo có chi phí phần heap O(log n).

Vì thế, cập nhật bằng remove rồi offer không tự có cận O(log n) cho toàn bộ yêu cầu. Nếu cập nhật ưu tiên là thao tác rất thường xuyên ở quy mô lớn, cần đánh giá cấu trúc hoặc mô hình cập nhật khác.

## 6. Cập nhật tường minh: gỡ trước, thay đổi hoặc thay thế rồi thêm

Một luồng cơ bản trong điều kiện đã kiểm soát:

```text
xác định đúng công việc đang chờ
    -> chuẩn bị và kiểm tra dữ liệu mới
    -> gỡ công việc cũ khi thông tin còn ổn định
    -> xác nhận đã gỡ
    -> đổi hoặc tạo giá trị mới
    -> offer giá trị mới
```

### 6.1. Nếu vẫn dùng đối tượng khả biến

Trích đoạn minh họa:

```java
// Trích đoạn trong luồng đơn, với phần tử duy nhất được quản lý.
if (!queue.remove(task)) {
    throw new IllegalStateException("Task is not queued");
}
task.changePriority(newPriority);
queue.offer(task);
```

Đây không phải một hàm cập nhật tổng quát cho mọi hệ thống. Nó giả định:

- Task cần cập nhật được nhận diện đúng.
- Không còn lần xuất hiện khác của cùng khóa khả biến trong queue.
- Không có queue khác đồng thời đang tổ chức theo cùng đối tượng bị sửa.
- Không có cập nhật chen vào giữa các bước.
- Dữ liệu mới và comparator đã đáp ứng hợp đồng cần dùng.

Nếu một đối tượng còn nằm trong nhiều cấu trúc ưu tiên, gỡ khỏi một nơi rồi sửa vẫn có thể làm nơi khác sai.

### 6.2. Thường dễ kiểm soát hơn khi tạo giá trị bất biến mới

Thay vì đổi đối tượng cũ, có thể biểu đạt yêu cầu mới bằng một giá trị khác:

```java
// Trích đoạn khai báo khóa thứ tự ổn định.
record Job(String id, int priority) {
}
```

Gỡ Job cũ rồi offer Job mới. Giá trị cũ không tự biến đổi trong bất kỳ nơi nào còn giữ nó.

Thiết kế này tách được hai việc: trạng thái nghiệp vụ có thể tiếp tục thay đổi, còn mục đã đưa vào heap có một khóa ưu tiên ổn định cho tới khi được thay thế.

Nếu công việc có nhiều dữ liệu mô tả có thể sửa, có thể để mục queue giữ id và bản chụp các trường cần so sánh, còn dữ liệu nghiệp vụ được quản lý ở nơi phù hợp.

### 6.3. Chuỗi cập nhật cần chính sách thất bại

Remove rồi offer là nhiều bước. Ví dụ nhỏ với kiểu số hợp lệ và comparator đơn giản có thể giữ luồng rõ, nhưng API không tự biến chuỗi thành giao dịch.

Nếu nghiệp vụ đòi hỏi không mất công việc khi bước sau thất bại, cần một quy trình chuẩn bị, phục hồi và phối hợp phù hợp. Bỏ qua boolean của remove khiến mã có thể thêm một bản mới dù bản cũ chưa được gỡ đúng.

Không chữa một thất bại tìm bằng cách cứ offer cùng đối tượng đã đổi. Hành động ấy có thể để lại nhiều lần xuất hiện cho cùng một công việc.

## 7. Chương trình 2: thay thế một Job bất biến

Lưu tệp `ImmutablePriorityReplacementDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class ImmutablePriorityReplacementDemo {
    record Job(String id, int priority) {
        @Override
        public String toString() {
            return id + ":" + priority;
        }
    }

    static final Comparator<Job> ORDER =
            Comparator.comparingInt(Job::priority).thenComparing(Job::id);

    static Job replacePriority(
            PriorityQueue<Job> queue, Job oldJob, int newPriority) {
        Job replacement = new Job(oldJob.id(), newPriority);
        if (!queue.remove(oldJob)) {
            throw new IllegalStateException("Old job is not queued");
        }
        queue.offer(replacement);
        return replacement;
    }

    public static void main(String[] args) {
        Job a = new Job("A", 10);
        Job b = new Job("B", 20);
        Job oldC = new Job("C", 30);
        PriorityQueue<Job> queue = new PriorityQueue<>(ORDER);
        queue.addAll(List.of(a, b, oldC));

        Job newC = replacePriority(queue, oldC, 5);
        System.out.println("old immutable value = " + oldC);
        System.out.println("new immutable value = " + newC);
        System.out.println("size after replacement = " + queue.size());
        System.out.println("contains old value = " + queue.contains(oldC));
        System.out.println("contains new value = " + queue.contains(newC));
        System.out.println("head after replacement = " + queue.peek());

        try {
            replacePriority(queue, oldC, 1);
        } catch (IllegalStateException ex) {
            System.out.println("replace missing old value = "
                    + ex.getClass().getSimpleName());
        }
        System.out.println("size after rejected replacement = " + queue.size());

        List<String> output = new ArrayList<>();
        Job next;
        while ((next = queue.poll()) != null) {
            output.add(next.toString());
        }
        System.out.println("safe poll order = " + output);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 ImmutablePriorityReplacementDemo.java
java ImmutablePriorityReplacementDemo
```

Kết quả của lần chạy kiểm chứng:

```text
old immutable value = C:30
new immutable value = C:5
size after replacement = 3
contains old value = false
contains new value = true
head after replacement = C:5
replace missing old value = IllegalStateException
size after rejected replacement = 3
safe poll order = [C:5, A:10, B:20]
```

### 7.1. Giá trị cũ không bị sửa

OldC vẫn là C:30; newC là C:5. Sau thay thế, queue có ba phần tử, không còn giá trị cũ và có giá trị mới.

Đầu C:5 đúng theo comparator vì nó đã được đưa vào bằng offer như một phần tử mới hợp lệ.

Ví dụ có một Job cho mỗi id, không có bản ghi trùng và không có cập nhật đồng thời. Helper kiểm tra gỡ thành công trước khi thêm.

### 7.2. Thử thay một phiên bản cũ bị từ chối

Gọi lại helper với oldC sau khi oldC đã bị thay sẽ không tìm thấy giá trị ấy. Helper ném IllegalStateException và không offer một bản thay thế khác.

Đây là một kiểm tra quan trọng cho cập nhật dựa trên giá trị cũ: yêu cầu lỗi thời không nên âm thầm tạo thêm công việc.

### 7.3. Tính đúng và chi phí là hai câu hỏi riêng

Kết quả poll là C:5, A:10, B:20, phù hợp với ưu tiên của các giá trị mới.

Nhưng bước remove(oldC) vẫn có tìm tuyến tính. Mẫu này ưu tiên sự rõ ràng của vòng đời và phù hợp với điều kiện ví dụ; không được quảng bá như một thao tác cập nhật khóa O(log n) tổng quát.

## 8. Dựng lại heap sau nhiều thay đổi cần được thực hiện có chủ đích

Nếu đã có nhiều trường ưu tiên bị sửa, một hướng phục hồi là xác lập dữ liệu chuẩn rồi dựng một queue mới theo các giá trị ấy.

Trước khi làm, cần bảo đảm dữ liệu dùng để dựng không tiếp tục đổi trong lúc đang đọc. Nếu không, cấu trúc mới có thể được xây từ những quan hệ thứ tự khác nhau tại các thời điểm khác nhau.

Một quy trình rõ ràng:

```text
xác định nguồn dữ liệu chuẩn
    -> dừng hoặc phối hợp các cập nhật liên quan
    -> lấy các bản chụp khóa ưu tiên nhất quán
    -> tạo PriorityQueue mới với comparator đúng
    -> đưa các bản chụp vào bằng thao tác dựng phù hợp
    -> kiểm tra trước khi chuyển quyền sử dụng sang queue mới
```

### 8.1. Copy một PriorityQueue không có hợp đồng sửa heap hỏng

Một cách tưởng như đơn giản:

```java
// Không coi đây là một phép repair cho một heap đã mất bất biến.
PriorityQueue<Task> repaired = new PriorityQueue<>(broken);
```

không có hợp đồng tái đánh giá mọi khóa ưu tiên đã bị sửa.

Trong [mã nguồn PriorityQueue OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/PriorityQueue.java), đường sao chép từ một đối tượng có đúng lớp PriorityQueue có thể sao dữ liệu nền mà không heapify lại. Tối ưu ấy dựa trên giả định nguồn đã là một heap hợp lệ.

Vì vậy, nếu nguồn đã bị phá bất biến qua setter, chỉ đổi sang một container copy không tự trở thành một quy trình phục hồi đáng tin.

Chi tiết đường tối ưu có thể khác giữa triển khai hoặc kiểu nguồn. Điều nên giữ là không dựa vào constructor copy như một API repair cho trạng thái đã bị sử dụng sai.

### 8.2. Thêm vào queue mới bằng comparator rõ ràng

Một mẫu tổ chức lại theo giá trị hiện tại là:

```java
// Trích đoạn; currentValues là nguồn dữ liệu đã ổn định.
PriorityQueue<Task> rebuilt = new PriorityQueue<>(order);
rebuilt.addAll(currentValues);
```

Với queue mới, các phần tử được thêm theo comparator đã chọn. Nhưng nếu chúng vẫn là cùng các Task khả biến, lần sửa tiếp theo ở nguồn có thể làm rebuilt mất bất biến trở lại.

Tổ chức lại vị trí và đóng băng khóa ưu tiên là hai yêu cầu khác nhau.

### 8.3. Bản chụp khóa giúp tách vòng đời

Có thể dựng bằng một kiểu giá trị ổn định:

```java
// Trích đoạn khai báo; các thành phần nhận diện ưu tiên được giữ ổn định.
record QueueSnapshot(String id, int priority) {
}
```

Khi dựng queue mới, tạo QueueSnapshot từ trạng thái đã xác nhận của từng công việc. Comparator chỉ đọc các thành phần bất biến ấy.

Điều này giữ cấu trúc mới đúng theo **bản chụp đã tạo**. Nó không có nghĩa queue tự đồng bộ với mọi priority mới nhất của đối tượng nghiệp vụ về sau. Nếu nghiệp vụ đổi ưu tiên, vẫn cần một yêu cầu thay thế hoặc một cơ chế phiên bản rõ ràng.

## 9. Chương trình 3: copy trực tiếp, dựng lại chia sẻ và bản chụp

Lưu tệp `PriorityQueueRebuildDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class PriorityQueueRebuildDemo {
    static final class MutableTask {
        private final String id;
        private int priority;

        MutableTask(String id, int priority) {
            this.id = id;
            this.priority = priority;
        }

        int priority() {
            return priority;
        }

        @Override
        public String toString() {
            return id + ":" + priority;
        }
    }

    record Snapshot(String id, int priority) {
        @Override
        public String toString() {
            return id + ":" + priority;
        }
    }

    public static void main(String[] args) {
        Comparator<MutableTask> mutableOrder =
                Comparator.comparingInt(MutableTask::priority);
        MutableTask d = new MutableTask("D", 40);
        PriorityQueue<MutableTask> broken = new PriorityQueue<>(mutableOrder);
        broken.addAll(List.of(
                new MutableTask("A", 10),
                new MutableTask("B", 20),
                new MutableTask("C", 30),
                d,
                new MutableTask("E", 50)));
        d.priority = 1;

        PriorityQueue<MutableTask> directCopy = new PriorityQueue<>(broken);
        PriorityQueue<MutableTask> sharedRebuild =
                new PriorityQueue<>(mutableOrder);
        sharedRebuild.addAll(broken);

        Comparator<Snapshot> snapshotOrder =
                Comparator.comparingInt(Snapshot::priority)
                        .thenComparing(Snapshot::id);
        PriorityQueue<Snapshot> stable = new PriorityQueue<>(snapshotOrder);
        for (MutableTask task : broken) {
            stable.offer(new Snapshot(task.id, task.priority));
        }

        System.out.println("broken head = " + broken.peek());
        System.out.println("direct copy head = " + directCopy.peek());
        System.out.println("shared rebuild head = " + sharedRebuild.peek());
        System.out.println("snapshot rebuild head = " + stable.peek());

        d.priority = 100;
        System.out.println("shared rebuild after later change = "
                + sharedRebuild.peek());
        System.out.println("snapshot head after later change = " + stable.peek());

        List<String> output = new ArrayList<>();
        Snapshot next;
        while ((next = stable.poll()) != null) {
            output.add(next.toString());
        }
        System.out.println("snapshot poll order = " + output);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 PriorityQueueRebuildDemo.java
java PriorityQueueRebuildDemo
```

Kết quả của lần chạy kiểm chứng:

```text
broken head = A:10
direct copy head = A:10
shared rebuild head = D:1
snapshot rebuild head = D:1
shared rebuild after later change = D:100
snapshot head after later change = D:1
snapshot poll order = [D:1, A:10, B:20, C:30, E:50]
```

Phần broken và directCopy là quan sát sau một thay đổi cố ý phá bất biến, được kiểm chứng trên môi trường đã nêu. Không coi một hành vi sai cụ thể là điều mọi triển khai phải tái hiện giống hệt.

### 9.1. Copy trực tiếp vẫn có đầu A:10

D đã đổi thành D:1 nhưng broken.peek vẫn là A:10. DirectCopy cũng có đầu A:10 trong lần chạy.

Điều đó minh họa đường sao chép có thể tin bố trí heap của nguồn. Không có một lời gọi repair tự động chỉ vì constructor đã tạo đối tượng mới.

### 9.2. Dựng lại bằng addAll tổ chức theo các giá trị lúc đó

SharedRebuild được tạo rỗng với mutableOrder rồi thêm các tham chiếu hiện có. Đầu lúc ấy là D:1, phù hợp các giá trị hiện tại.

Nhưng D trong sharedRebuild chính là đối tượng D mà bên ngoài còn giữ. Khi priority của D đổi thành 100, peek của sharedRebuild trả D:100, lại sai so với A:10 đang chờ.

Một lần dựng lại đúng không bảo vệ được các lần sửa tương lai nếu khóa tiếp tục được chia sẻ khả biến.

### 9.3. Snapshot giữ nguyên ưu tiên đã ghi nhận

Stable chứa các Snapshot riêng, nên D trong đó vẫn là D:1 khi đối tượng gốc đổi thành D:100. Chuỗi poll là D:1, A:10, B:20, C:30, E:50.

Điều này chứng minh heap ổn định theo dữ liệu snapshot, không chứng minh rằng nó đã tự áp dụng yêu cầu nghiệp vụ D:100 mới nhất.

Nếu yêu cầu mới là D phải được xử lý theo priority 100, ứng dụng phải thay snapshot hoặc làm phiên bản cũ không còn hợp lệ. Sự độc lập của bản chụp là một công cụ để quản lý thay đổi, không phải thay thế cho việc truyền thay đổi có chủ đích.

### 9.4. Chi phí dựng cần được tính theo cách thực hiện

Trong ví dụ, queue mới có comparator tường minh và nhận các phần tử bằng offer hoặc addAll. Có thể phân tích theo n lần thêm với cận tổng quát O(n log n) cho sửa heap.

Các thuật toán heapify theo lô có thể có chi phí tuyến tính trong những đường dựng phù hợp, nhưng không được suy ra rằng mọi constructor copy hoặc mọi addAll đều là một phép heapify mong muốn.

Khi mục tiêu là phục hồi đúng, trước hết xác định dữ liệu và ngữ nghĩa. Sau đó mới chọn cách dựng hiệu quả có cơ sở.

## 10. Khi cập nhật thường xuyên: tách mục queue khỏi trạng thái nghiệp vụ

Remove(Object) mỗi lần có thể quá tốn kém nếu số việc lớn và đổi ưu tiên liên tục. Có thể cân nhắc một mô hình khác, nhưng vẫn phải giữ khóa heap ổn định.

Một hướng là mục queue bất biến có phiên bản:

```java
// Trích đoạn kiểu dữ liệu, không phải scheduler hoàn chỉnh.
record QueueEntry(String taskId, int priority, long version) {
}
```

Ý tưởng:

1. Mỗi công việc có một phiên bản hiện hành được quản lý ở nguồn chuẩn.
2. Khi đổi ưu tiên, tạo QueueEntry mới với priority và version mới.
3. Comparator chỉ đọc priority cùng các tiêu chí phụ bất biến của entry.
4. Khi lấy entry ra, đối chiếu version với phiên bản hiện hành.
5. Nếu entry đã cũ, bỏ qua; nếu còn hiệu lực, xử lý theo chính sách của ứng dụng.

Cơ chế này không sửa khóa của một entry đang nằm trong heap. Nó thay việc tìm-gỡ ngay bằng việc nhận biết entry lỗi thời ở thời điểm sử dụng.

### 10.1. Đổi đánh đổi, không làm biến mất công việc

Những entry cũ vẫn có thể chiếm chỗ cho tới khi được lấy hoặc dọn. Chi phí heap phụ thuộc tổng số entry đang lưu, gồm cả entry lỗi thời, không chỉ số công việc còn hiệu lực.

Một lần yêu cầu lấy công việc có thể phải bỏ qua nhiều entry cũ. Vì vậy, không khẳng định mỗi lần xử lý nghiệp vụ chắc chắn chỉ có một poll O(log n).

Cần chính sách dọn, hủy, cấp phiên bản và giới hạn lưu trữ phù hợp. Nếu API có peek để xem việc hiệu lực tiếp theo, cũng phải xử lý các đầu đã lỗi thời; chỉ peek thẳng một entry cũ có thể cho quyết định sai.

### 10.2. Nguồn chuẩn và queue cần phối hợp

Thay phiên bản ở Map rồi thêm entry là nhiều bước. Trong hệ thống nhiều luồng, cần thiết kế quan hệ giữa chúng để không công bố trạng thái nửa chừng.

Không sao chép nguyên mô tả ý tưởng thành một cấu trúc đồng thời hoàn chỉnh. Nó là một cách tách khóa bất biến và tính hợp lệ hiện thời, cần được hiện thực theo yêu cầu cụ thể.

Một hướng khác là cấu trúc heap có hỗ trợ cập nhật khóa bằng chỉ mục/handle tường minh. Khi dùng API như vậy, phải đọc hợp đồng riêng; PriorityQueue chuẩn không tự cung cấp khả năng ấy chỉ nhờ có một tham chiếu tới phần tử.

## 11. Cập nhật gián tiếp và nhiều luồng không tự sửa được bằng khóa

### 11.1. Comparator đọc trạng thái bên ngoài

Giả sử comparator không đọc task.priority mà tra `priorities.get(task.id)` trong một Map. Đối tượng Task có thể bất biến nhưng quan hệ thứ tự vẫn đổi khi Map bị cập nhật.

Hoặc một cờ bên ngoài đổi từ “số nhỏ trước” sang “số lớn trước”. Cây heap cũ không được tổ chức lại chỉ vì cờ ấy thay đổi.

Khi rà soát rủi ro, hãy truy theo mọi dữ liệu comparator đọc, không chỉ tìm setter trong lớp phần tử.

### 11.2. Volatile hoặc một trường nguyên tử không thực hiện sift

Một cơ chế làm giá trị priority mới được nhìn thấy không tự di chuyển mục trong heap.

Có thể xảy ra tình huống mọi lần so sánh đều đọc đúng giá trị mới, nhưng bố trí được tạo theo giá trị cũ vẫn sai. Vì vậy, vấn đề hiển thị dữ liệu giữa luồng và vấn đề duy trì cấu trúc cần được giải quyết riêng.

### 11.3. Đồng bộ chỉ có giá trị khi bảo vệ đúng toàn bộ thay đổi

Nếu một luồng giữ khóa khi offer/poll nhưng luồng khác sửa trực tiếp priority mà không tuân thủ cùng quy trình, bất biến vẫn có thể bị phá.

Ngay cả khi tất cả thao tác được chạy tuần tự dưới cùng một khóa, một setter diễn ra lúc phần tử còn ở trong queue vẫn không tự sắp xếp lại heap. Khóa chỉ ngăn cập nhật chen nhau; luồng cập nhật vẫn phải gỡ/thay thế/dựng lại đúng.

Tương tự, đổi sang một collection đồng thời không tự tạo một bộ theo dõi setter cho đối tượng nằm bên trong. Cần giữ ngữ nghĩa cập nhật ưu tiên tường minh.

### 11.4. Một đối tượng trong nhiều queue

Nếu cùng Task nằm trong hai PriorityQueue theo cùng hoặc khác tiêu chí, sửa Task có thể làm cả hai bị ảnh hưởng.

Gỡ khỏi queue thứ nhất trước setter chưa bảo vệ queue thứ hai. Tách mỗi mục queue thành một khóa/bản chụp riêng thường giúp xác định nơi nào phải được cập nhật và lúc nào.

Các snapshot ở nhiều nơi cũng cần cơ chế truyền yêu cầu thay đổi nếu mục tiêu là giữ chúng cùng phản ánh một phiên bản nghiệp vụ. Bất biến không có nghĩa tự đồng bộ dữ liệu.

## 12. Chọn cách xử lý theo tình huống

| Tình huống | Hướng cần cân nhắc | Điểm phải kiểm tra |
|---|---|---|
| Ưu tiên không đổi trong khi chờ | Entry bất biến | Comparator và tiêu chí phụ đều ổn định |
| Thỉnh thoảng đổi một việc ở quy mô vừa | Gỡ giá trị cũ rồi offer giá trị mới | Định danh, phần tử trùng, remove có thành công, chi phí O(n) |
| Nhiều khóa đã bị sửa hoặc cần thay quy tắc xếp hạng | Lấy dữ liệu chuẩn và dựng cấu trúc mới | Bản chụp nhất quán, comparator đúng, không tin copy heap hỏng |
| Cập nhật rất thường xuyên | Entry có phiên bản hoặc cấu trúc hỗ trợ update-key | Entry lỗi thời, bộ nhớ, tổng chi phí và tính nguyên tử |
| Một đối tượng được nhiều nơi lập chỉ mục | Tách khóa riêng theo cấu trúc | Không để setter chung âm thầm đổi mọi chỉ mục |
| Cần xử lý chia sẻ nhiều luồng | Thiết kế cả mô hình cập nhật và phối hợp | Đồng bộ không thay thế việc duy trì heap |

Không phải mọi thay đổi trạng thái của công việc đều làm sai queue. Nếu comparator chỉ đọc priority và id ổn định, đổi một ghi chú không tham gia thứ tự có thể không ảnh hưởng heap.

Nhưng khi id được dùng làm tiêu chí phụ, chính id cũng thuộc dữ liệu cần ổn định. Hãy liệt kê đầy đủ các thành phần so sánh, không chỉ trường mang tên priority.

Một lựa chọn đúng nên mô tả được: ai có quyền thay đổi, thay đổi xảy ra khi phần tử ở trạng thái nào, và cấu trúc được duy trì lại bằng thao tác nào.

## 13. Những cách chữa dễ tạo thêm lỗi

| Cách làm | Điều còn sai | Hướng xử lý |
|---|---|---|
| Setter priority rồi chờ peek tự tìm min | Peek chỉ đọc đầu đã được duy trì | Dùng cập nhật tường minh |
| Poll một lần để “refresh” toàn bộ | Poll sửa một đường, giả định heap đã hợp lệ | Không dùng như phép repair tổng quát |
| Offer lại cùng đối tượng đã sửa | Có thể tạo thêm lần xuất hiện của cùng tham chiếu | Kiểm soát định danh và gỡ đúng trước khi thay |
| Thấy contains true nên kết luận queue đúng | Thành viên và thứ tự là hai câu hỏi khác | Kiểm tra lựa chọn đầu và chuỗi poll |
| Nghĩ remove(Object) sau sửa chắc chắn luôn mất dấu | Tìm theo equals vẫn có thể thành công | Phân biệt tìm thành viên với duy trì heap |
| Gỡ một lần nhưng có nhiều lần xuất hiện | Các tham chiếu còn lại vẫn chịu setter | Quản lý số lần xuất hiện hoặc dùng entry riêng |
| Copy heap hỏng bằng constructor | Có đường copy không heapify lại | Dựng từ dữ liệu chuẩn bằng quy trình rõ |
| Dựng lại bằng cùng đối tượng rồi tiếp tục setter | Heap mới có thể sai lần nữa | Bảo vệ khóa hoặc dùng snapshot bất biến |
| Dùng record chứa một đối tượng priority khả biến | Bất biến chỉ ở tham chiếu trực tiếp | Kiểm tra dữ liệu lồng comparator đọc |
| Dùng synchronized/volatile như phép sắp xếp | Cơ chế bộ nhớ không thực hiện sift | Phối hợp đúng và giữ luồng cập nhật cấu trúc |
| Gọi remove-then-offer là O(log n) | Bước tìm theo đối tượng có thể O(n) | Tính đủ mọi bước |
| Snapshot không đổi nên nghĩ luôn là ưu tiên mới nhất | Snapshot giữ dữ liệu ở thời điểm tạo | Truyền yêu cầu thay thế hoặc phiên bản mới |

Không dùng việc một dữ liệu nhỏ tình cờ cho kết quả đúng để hợp thức hóa một đường sửa không giữ bất biến. Rủi ro thường lộ ra khi phần tử bị đổi nằm sâu hơn, thứ tự cập nhật khác đi hoặc có nhiều đối tượng liên quan.

## 14. Kiểm tra lỗi và giải pháp theo vòng đời

Bài kiểm tra nên theo chuỗi thao tác thực tế, không chỉ kiểm tra comparator trên hai đối tượng tĩnh.

### 14.1. Trước thay đổi

Xác nhận queue ban đầu hợp lệ theo yêu cầu:

- Peek đúng phần tử đầu.
- Dữ liệu priority có các giá trị khác nhau để tránh nhầm với tie.
- Số lượng và định danh của các công việc rõ.
- Comparator có một quy tắc ổn định.

Nếu cần cùng ưu tiên, thêm tình huống riêng theo tiêu chí phụ đã thiết kế. Không dùng một thứ tự tie không được bảo đảm để kết luận có hoặc không có lỗi mutation.

### 14.2. Thay đổi theo các vị trí khác nhau

Nên kiểm tra:

- Một phần tử không ở đầu được đổi thành giá trị phải lên trước.
- Phần tử đầu được đổi thành giá trị phải lùi.
- Nhiều công việc đổi ưu tiên.
- Một đối tượng có nhiều tham chiếu hoặc nhiều lần xuất hiện.
- Dữ liệu so sánh thay qua đối tượng lồng hay cấu hình ngoài.

Các thí nghiệm cố ý setter trong queue giúp tái hiện rủi ro; chúng không phải hành vi sai mà ứng dụng nên dựa vào như một API ổn định.

### 14.3. Kiểm tra giải pháp hợp lệ

Với luồng thay thế hoặc dựng snapshot:

1. Kiểm tra phiên bản cũ được gỡ hoặc vô hiệu hóa đúng.
2. Kiểm tra phiên bản mới có mặt đúng số lần.
3. Kiểm tra peek sau cập nhật.
4. Poll toàn bộ trên dữ liệu thử để đối chiếu thứ tự mong muốn.
5. Kiểm tra yêu cầu cập nhật cũ bị xử lý đúng.
6. Kiểm tra thay đổi nguồn về sau có ảnh hưởng snapshot theo đúng thiết kế không.

Dữ liệu kỳ vọng cần phản ánh mô hình đã chọn. Với snapshot, kết quả đúng theo phiên bản đã chụp; với yêu cầu “luôn mới nhất”, cần cả cơ chế cập nhật phiên bản và loại bỏ dữ liệu cũ.

### 14.4. Đừng chỉ kiểm tra size hoặc contains

Một queue có thể giữ đủ mọi đối tượng mà vẫn chọn sai thứ tự. Size và contains không thay thế kiểm tra đầu và chuỗi xử lý.

Iterator của PriorityQueue cũng không bảo đảm duyệt theo ưu tiên ngay cả khi heap đang đúng. Nếu muốn so dãy xử lý, dùng poll trên một queue thử hợp lệ hoặc một bản dữ liệu được xây đúng.

Không dùng một Set để xác nhận kết quả nếu thứ tự và số lần xuất hiện đều quan trọng.

## 15. Bài tập áp dụng

### Bài 1: sửa một phần tử ở dưới

Queue đang có A:10, B:20, C:30. Sửa C thành C:1 qua setter. Vì sao peek có thể vẫn trả A?

**Gợi ý trả lời:** setter đổi giá trị trong đối tượng nhưng không đưa mục C lên vị trí phù hợp. Gốc cũ vẫn ở đó và peek không quét lại min.

### Bài 2: sửa gốc

Nếu A:10 ở đầu đổi thành A:100, có cần xem lại heap không?

**Gợi ý trả lời:** có. A có thể phải đi xuống; sửa trường không tự sift-down.

### Bài 3: contains vẫn true

Một thử nghiệm contains(task) trả true sau đổi priority. Có chứng minh thứ tự xử lý vẫn đúng không?

**Gợi ý trả lời:** không. Contains kiểm tra tồn tại theo equals; heap chọn đầu theo comparator. Hai yêu cầu khác nhau.

### Bài 4: cùng tham chiếu được thêm hai lần

Gỡ task một lần, sửa priority rồi thêm lại. Có chắc mọi mục trong queue đều hợp lệ không?

**Gợi ý trả lời:** không. Một lần xuất hiện khác của cùng tham chiếu có thể vẫn ở trong queue và chịu setter. Cần quản lý số lần xuất hiện hoặc dùng entry ổn định riêng.

### Bài 5: constructor copy

Queue đã mất bất biến sau mutation. Có nên coi new PriorityQueue<>(broken) là phép sửa chắc chắn không?

**Gợi ý trả lời:** không. Có đường triển khai copy bố trí mà không heapify lại, dựa trên giả định nguồn hợp lệ. Cần dựng có chủ đích từ dữ liệu chuẩn.

### Bài 6: bản chụp giữ D:1

Sau khi tạo snapshot D:1, đối tượng nghiệp vụ đổi thành D:100. Snapshot vẫn trả D:1 có chứng minh nó đã cập nhật đúng ưu tiên mới nhất không?

**Gợi ý trả lời:** không. Nó ổn định theo phiên bản đã chụp. Muốn phản ánh 100 cần một yêu cầu thay thế hoặc cơ chế phiên bản.

### Bài 7: remove rồi offer có logarit không?

Vì offer và các thao tác đầu của heap là O(log n), có thể kết luận cập nhật một đối tượng bằng remove(Object) rồi offer cũng O(log n) không?

**Gợi ý trả lời:** không. Remove(Object) có thể tìm tuyến tính O(n), phải tính cả bước ấy.

### Bài 8: chỉ đổi ghi chú

Comparator không đọc ghi chú và mọi khóa so sánh khác giữ nguyên. Sửa ghi chú có tự làm sai heap không?

**Gợi ý trả lời:** không nhất thiết. Rủi ro đang xét đến từ thay đổi quan hệ so sánh. Cần kiểm tra đúng các dữ liệu comparator thực sự đọc.

Một thiết kế ưu tiên dễ kiểm soát giữ được hai việc cùng lúc: khóa trong heap ổn định, và mọi thay đổi nghiệp vụ đi qua một quy trình cập nhật rõ. Khi đó việc chọn đầu không phụ thuộc vào một setter âm thầm xảy ra ngoài cấu trúc.
