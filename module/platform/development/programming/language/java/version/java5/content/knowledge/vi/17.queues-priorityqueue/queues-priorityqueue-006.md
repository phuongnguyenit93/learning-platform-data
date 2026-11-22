# Thứ tự tự nhiên và Comparator tùy chỉnh trong PriorityQueue

## 1. PriorityQueue cần một quy tắc xác định phần tử đầu

PriorityQueue không lấy phần tử theo thứ tự thêm như một hàng đợi FIFO. Nó dùng một quy tắc so sánh để xác định phần tử nhỏ nhất theo quy tắc đó làm đầu hàng đợi.

Có hai cách cung cấp thứ tự:

- **Thứ tự tự nhiên (natural ordering)**: lớp phần tử định nghĩa bằng `Comparable<T>.compareTo`.
- **Comparator tùy chỉnh**: một đối tượng `Comparator<? super E>` được cung cấp khi tạo hàng đợi.

“Nhỏ nhất” luôn được hiểu theo quy tắc so sánh, không nhất thiết là nhỏ nhất về giá trị số. Nếu Comparator đảo thứ tự số, số lớn nhất sẽ đứng đầu vì nó được xem là nhỏ nhất theo Comparator đó.

Các quy tắc này vẫn được dùng trong Java hiện đại. Ví dụ trong bài chạy trên Java 17+.

## 2. Ý nghĩa kết quả so sánh

Với `compare(a, b)` hoặc `a.compareTo(b)`:

| Kết quả | Ý nghĩa |
| --- | --- |
| Âm | a đứng trước b theo thứ tự |
| 0 | a và b có cùng vị trí so sánh |
| Dương | a đứng sau b theo thứ tự |

Không cần trả đúng -1, 0 hoặc 1. Điều quan trọng là dấu và tính nhất quán của quan hệ.

PriorityQueue dùng kết quả này để duy trì phần tử đầu. Nó không cam kết toàn bộ mảng bên trong, kết quả `toString`, iterator hoặc stream đều theo thứ tự đã sắp.

Muốn quan sát thứ tự lấy ra, dùng poll lặp lại. Nếu cần duyệt có thứ tự mà giữ nguyên hàng đợi, hãy sao chép rồi poll bản sao, hoặc sao chép dữ liệu và sắp xếp bằng đúng quy tắc so sánh.

## 3. Thứ tự tự nhiên với Integer và String

Ví dụ:

```java
PriorityQueue<Integer> numbers = new PriorityQueue<>();
numbers.offer(30);
numbers.offer(10);
numbers.offer(20);
```

`Integer` triển khai Comparable theo giá trị số. Vì vậy, lần poll đầu trả 10, sau đó 20, rồi 30.

Với String, thứ tự tự nhiên là thứ tự từ điển theo các đơn vị UTF-16. Nó phân biệt hoa/thường và không phải quy tắc sắp tên tiếng Việt theo ngôn ngữ tự nhiên.

Nếu bài toán cần thứ tự theo ngôn ngữ hoặc quy tắc nghiệp vụ khác, phải chọn Comparator phù hợp thay vì mặc định xem mọi String đều được sắp theo kỳ vọng của người dùng.

Một PriorityQueue không được cung cấp Comparator chỉ có thể hoạt động đúng với các phần tử có khả năng so sánh tự nhiên với nhau. Thêm đối tượng không triển khai Comparable hoặc trộn các kiểu không so sánh được có thể gây `ClassCastException`.

Generic `PriorityQueue<E>` không tự ép E phải triển khai Comparable ngay tại khai báo lớp. Trách nhiệm chọn thứ tự phù hợp vẫn thuộc về người tạo hàng đợi.

## 4. Comparator cho thứ tự ngược hoặc quy tắc riêng

Để số lớn hơn được lấy trước:

```java
PriorityQueue<Integer> largestFirst =
        new PriorityQueue<>(Comparator.reverseOrder());
```

`Comparator.reverseOrder()` đảo thứ tự tự nhiên. Nó không đảo thứ tự các lần thêm.

Với đối tượng có nhiều thuộc tính, Comparator cho phép chỉ rõ quy tắc mà không bắt lớp phải có một thứ tự tự nhiên duy nhất:

```java
Comparator<Job> order = Comparator
        .comparingInt(Job::priority)
        .reversed()
        .thenComparingLong(Job::sequence);
```

Quy tắc này là:

1. Mức priority lớn hơn được lấy trước.
2. Nếu cùng priority, sequence nhỏ hơn được lấy trước.

Hàng đợi vẫn lấy phần tử nhỏ nhất **theo order**. Dấu đảo ở tiêu chí thứ nhất làm mức priority lớn hơn được xem là đứng trước.

Tên “priority cao” tự nó không quyết định số lớn hay nhỏ đứng trước. Phải quy định rõ: hệ thống có thể dùng số 1 là khẩn nhất, hoặc số lớn là khẩn hơn. Comparator cần bám theo quy ước đó.

## 5. Chương trình đầy đủ

Lưu thành `PriorityOrderingDemo.java`:

```java
import java.util.Comparator;
import java.util.PriorityQueue;

public class PriorityOrderingDemo {
    record Task(int priority, long sequence, String name)
            implements Comparable<Task> {
        @Override
        public int compareTo(Task other) {
            int byPriority = Integer.compare(priority, other.priority);
            if (byPriority != 0) {
                return byPriority;
            }
            return Long.compare(sequence, other.sequence);
        }
    }

    record Job(int priority, long sequence, String name) {
    }

    public static void main(String[] args) {
        PriorityQueue<Integer> natural = new PriorityQueue<>();
        natural.offer(30);
        natural.offer(10);
        natural.offer(20);
        System.out.println("natural=" + drain(natural));

        PriorityQueue<Integer> reversed =
                new PriorityQueue<>(Comparator.reverseOrder());
        reversed.offer(30);
        reversed.offer(10);
        reversed.offer(20);
        System.out.println("reversed=" + drain(reversed));

        PriorityQueue<Task> tasks = new PriorityQueue<>();
        tasks.offer(new Task(2, 3, "C"));
        tasks.offer(new Task(1, 2, "B"));
        tasks.offer(new Task(1, 1, "A"));

        StringBuilder taskOrder = new StringBuilder();
        Task task;
        while ((task = tasks.poll()) != null) {
            append(taskOrder, task.name());
        }
        System.out.println("natural tasks=" + taskOrder);

        Comparator<Job> customOrder = Comparator
                .comparingInt(Job::priority)
                .reversed()
                .thenComparingLong(Job::sequence);

        PriorityQueue<Job> jobs = new PriorityQueue<>(customOrder);
        jobs.offer(new Job(1, 1, "normal"));
        jobs.offer(new Job(5, 3, "urgent-later"));
        jobs.offer(new Job(5, 2, "urgent-first"));

        System.out.println("custom head=" + jobs.peek().name());
        StringBuilder jobOrder = new StringBuilder();
        Job job;
        while ((job = jobs.poll()) != null) {
            append(jobOrder, job.name());
        }
        System.out.println("custom jobs=" + jobOrder);
    }

    static String drain(PriorityQueue<Integer> queue) {
        StringBuilder result = new StringBuilder();
        Integer value;
        while ((value = queue.poll()) != null) {
            append(result, value.toString());
        }
        return result.toString();
    }

    static void append(StringBuilder result, String value) {
        if (result.length() > 0) {
            result.append(",");
        }
        result.append(value);
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 PriorityOrderingDemo.java
java PriorityOrderingDemo
```

Kết quả:

```text
natural=10,20,30
reversed=30,20,10
natural tasks=A,B,C
custom head=urgent-first
custom jobs=urgent-first,urgent-later,normal
```

Task có thứ tự tự nhiên do chính lớp định nghĩa: priority nhỏ trước, cùng mức thì sequence nhỏ trước.

Job không triển khai Comparable, nhưng vẫn dùng được vì hàng đợi nhận customOrder. Quy tắc của Job cố ý khác Task: priority lớn trước, cùng mức thì sequence nhỏ trước.

Các số sequence trong ví dụ là giá trị được cung cấp tường minh. PriorityQueue không tự tạo chúng, cũng không tự biết thứ tự công việc đã đến hệ thống.

## 6. Phân biệt đảo một tiêu chí và đảo toàn bộ thứ tự

Hai biểu thức sau khác nhau:

```java
Comparator<Job> highPriorityThenOldest = Comparator
        .comparingInt(Job::priority)
        .reversed()
        .thenComparingLong(Job::sequence);

Comparator<Job> reverseEverything = Comparator
        .comparingInt(Job::priority)
        .thenComparingLong(Job::sequence)
        .reversed();
```

Ở biểu thức đầu, `reversed()` được gọi trước khi thêm tiêu chí sequence: chỉ thứ tự priority đang có bị đảo, rồi sequence vẫn tăng dần.

Ở biểu thức thứ hai, Comparator tổng hợp đã có cả hai tiêu chí rồi mới bị đảo: priority giảm dần và sequence cũng giảm dần.

Nếu cần công việc ưu tiên cao nhưng đến trước được xử lý trước, dùng biểu thức đầu với sequence phản ánh thứ tự đến. Đặt reversed sai vị trí có thể khiến công việc đến sau cùng mức được xử lý trước.

## 7. Comparator phải tuân theo một quan hệ nhất quán

### Không dùng phép trừ để so sánh số nguyên tùy ý

Cách viết dễ sai:

```java
// Không nên:
// (a, b) -> a.priority() - b.priority()
```

Phép trừ có thể tràn int, làm dấu kết quả sai. Với long, ép hiệu sang int còn có thể làm mất dữ liệu.

Dùng:

```java
Integer.compare(a.priority(), b.priority());
Long.compare(a.sequence(), b.sequence());
```

hoặc các hàm `Comparator.comparingInt`, `comparingLong`.

Không đảo thứ tự bằng cách lấy âm tùy tiện của một kết quả compare bất kỳ; giá trị nhỏ nhất của int có vấn đề khi đổi dấu. Dùng `reversed()` hoặc đổi chiều so sánh an toàn.

### Giữ đối xứng dấu và tính bắc cầu

Nếu a đứng trước b và b đứng trước c thì quan hệ không được tùy tiện nói c đứng trước a. Comparator phụ thuộc vào số ngẫu nhiên, thời gian thay đổi hoặc một trạng thái bên ngoài không ổn định có thể phá giả định của cấu trúc hàng đợi.

Khi compare trả 0 cho a và b, quan hệ so sánh của chúng với phần tử thứ ba cũng phải nhất quán theo hợp đồng Comparator. Không chỉ kiểm tra vài cặp rồi coi mọi quy tắc đều hợp lệ.

## 8. Phần tử cùng mức không được bảo đảm FIFO

Nếu Comparator chỉ xét priority:

```java
Comparator<Job> priorityOnly =
        Comparator.comparingInt(Job::priority);
```

hai Job cùng priority có compare bằng 0. PriorityQueue vẫn giữ được cả hai; nó không loại bỏ phần tử trùng mức như một tập hợp có thể làm.

Tuy nhiên, thứ tự lấy các phần tử cùng mức không được cam kết là thứ tự thêm. Nếu cần quy tắc ổn định, thêm một khóa phụ như sequence tăng dần.

Nếu sequence cũng trùng, kết quả so sánh có thể vẫn là 0; lúc đó vẫn không có cam kết chọn tên nào trước. Muốn thứ tự hoàn toàn xác định, bổ sung một khóa có ý nghĩa phù hợp hoặc bảo đảm khóa phụ là duy nhất.

Compare bằng 0 cũng không bắt buộc đồng nghĩa equals bằng true đối với PriorityQueue. Record Task trong ví dụ so sánh priority và sequence nhưng equals còn xét name. Hai Task khác name vẫn có thể cùng mức so sánh. Chúng có thể cùng tồn tại trong hàng đợi.

Một điểm liên quan: `remove(Object)` và `contains(Object)` tìm theo equals, không xóa/tìm một phần tử bất kỳ chỉ vì Comparator trả 0. Nếu hai quan hệ khác nhau, hãy tài liệu hóa để bên dùng không nhầm “cùng ưu tiên” với “cùng đối tượng nghiệp vụ”.

## 9. Không sửa khóa ưu tiên khi phần tử còn trong hàng đợi

PriorityQueue không tự theo dõi việc thuộc tính của một đối tượng bị thay đổi.

Nếu một Job có thể thay đổi priority sau khi đã được thêm, sửa priority không tự làm cấu trúc bên trong sắp lại. Peek có thể không trả phần tử mong muốn theo giá trị mới.

Cách xử lý thường là:

1. Lấy hoặc xóa phần tử ra khỏi hàng đợi.
2. Thay đổi khóa so sánh.
3. Thêm lại phần tử.

Hoặc dùng đối tượng bất biến cho các khóa so sánh, như record trong ví dụ, rồi thay bằng một đối tượng mới theo quy tắc của ứng dụng.

Cũng không nên thay đổi trạng thái của Comparator làm nó diễn giải các phần tử đã có theo một thứ tự mới mà không dựng lại hàng đợi. Giữ Comparator cố định không có nghĩa nó tự sửa được các phần tử đã biến đổi.

Các thao tác xóa-sửa-thêm không tự là giao dịch nguyên tử trong bối cảnh đồng thời. PriorityQueue thông thường không an toàn cho truy cập đồng thời không đồng bộ hóa.

## 10. Null và lựa chọn thứ tự

PriorityQueue không chấp nhận phần tử null, kể cả khi Comparator được tạo bằng `Comparator.nullsFirst(...)` hoặc `nullsLast(...)`.

Các Comparator đó có thể hữu ích cho việc so sánh các **thuộc tính có thể null** của một phần tử không null, hoặc cho cấu trúc khác cho phép null. Chúng không thay đổi hợp đồng cấm phần tử null của PriorityQueue.

Với dữ liệu nghiệp vụ, nên quyết định riêng:

- Bản thân phần tử có thể null không? Với PriorityQueue: không.
- Thuộc tính dùng so sánh có thể null không? Nếu có, Comparator phải có chính sách rõ ràng.
- Giá trị bằng nhau có cần thêm khóa phụ không?

## 11. Cách áp dụng và tự kiểm tra

1. Viết bằng lời “phần tử nào cần được xử lý trước” trước khi viết Comparator.
2. Chọn thứ tự tự nhiên nếu lớp có một thứ tự chính hợp lý; chọn Comparator nếu cần nhiều cách xếp hoặc không sở hữu lớp phần tử.
3. Kiểm tra dấu so sánh, trường hợp biên của số, các phần tử cùng mức và chính sách null.
4. Không dùng iterator/toString để chứng minh thứ tự ưu tiên; kiểm tra chuỗi poll hoặc bản sao được sắp đúng Comparator.
5. Giữ các khóa so sánh ổn định trong thời gian phần tử nằm trong hàng đợi.

Bài tập: đổi vị trí `reversed()` trong chương trình sang cuối chuỗi Comparator. Khi đó hai công việc cùng priority 5 sẽ đổi thứ tự theo sequence. Sau đó bỏ tiêu chí sequence và giải thích vì sao không còn quyền khẳng định tên nào trong hai công việc đó sẽ ra trước.

## Tài liệu đối chiếu

- [PriorityQueue — Thứ tự tự nhiên, Comparator, phần tử đầu và phần tử cùng mức](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PriorityQueue.html).
- [Comparator — Hợp đồng so sánh và ghép nhiều tiêu chí](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html).
- [Comparable — Thứ tự tự nhiên](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Comparable.html).
