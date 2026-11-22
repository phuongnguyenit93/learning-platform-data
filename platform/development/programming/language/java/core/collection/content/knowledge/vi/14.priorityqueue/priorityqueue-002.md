# Thứ tự tự nhiên và Comparator tùy chỉnh

## 1. PriorityQueue chọn phần tử nào để xử lý tiếp?

Giả sử chương trình nhận các số `6, 2, 9, 1, 5`. Nếu dùng hàng đợi FIFO, số 6 đến trước sẽ được lấy trước. Nếu yêu cầu là luôn lấy giá trị nhỏ nhất hiện có, FIFO không mô tả đúng công việc.

`PriorityQueue` duy trì một đầu hàng đợi theo **quy tắc ưu tiên**. Quy tắc ấy có thể là thứ tự tự nhiên của kiểu phần tử hoặc một `Comparator` do bạn cung cấp.

Điểm phải đọc chính xác là: đầu hàng đợi là phần tử **nhỏ nhất theo quy tắc so sánh đang dùng**. Với thứ tự tự nhiên của số nguyên, đó là số nhỏ nhất. Với bộ so sánh đảo, đó lại là số lớn nhất về số học.

Không có một khái niệm “ưu tiên cao” chung cho mọi dữ liệu. Điểm cao có thể cần xử lý trước, nhưng thời hạn sớm thường có giá trị thời gian nhỏ hơn. Bộ so sánh phải biến ý nghĩa nghiệp vụ thành một thứ tự cụ thể.

Bài học đi từ số nguyên đến đối tượng công việc, xử lý trường hợp cùng ưu tiên và kiểm chứng trình tự lấy ra. Các ví dụ dùng API có trong Java 17.

Bạn cần biết cách tạo đối tượng, khai báo kiểu tổng quát và dùng vòng lặp. `Comparable`, `Comparator` và ý nghĩa kết quả so sánh sẽ được giới thiệu trước khi xuất hiện trong chương trình đầy đủ.

## 2. Thứ tự tự nhiên đến từ kiểu phần tử

Thứ tự tự nhiên (natural ordering) được kiểu phần tử cung cấp qua `Comparable<T>`, với phương thức `compareTo`.

Khi đọc `a.compareTo(b)`:

| Kết quả | Ý nghĩa theo thứ tự của kiểu |
| --- | --- |
| Nhỏ hơn 0 | a đứng trước b |
| Bằng 0 | a và b cùng mức về thứ tự |
| Lớn hơn 0 | a đứng sau b |

Chỉ dấu âm, 0 hoặc dương là ý nghĩa chung. Một phép so sánh hợp lệ không bắt buộc luôn trả đúng -1 hoặc 1.

Integer đã có thứ tự tự nhiên theo giá trị số. Vì vậy:

~~~java
PriorityQueue<Integer> numbers = new PriorityQueue<>();
~~~

tạo một hàng đợi có thể chọn số nhỏ nhất làm đầu mà không cần truyền quy tắc riêng. Đây là khai báo minh họa với kiểu `java.util.PriorityQueue`.

Sau khi đưa vào `6, 2, 9, 1, 5`:

~~~text
peek()          → 1, không lấy ra
poll liên tiếp  → 1, 2, 5, 6, 9
~~~

Thứ tự tự nhiên không có nghĩa “thứ tự dữ liệu xuất hiện” hoặc “tự tăng theo mọi trường”. Với một kiểu tự định nghĩa, tác giả kiểu phải quyết định thứ tự qua Comparable nếu muốn cung cấp thứ tự tự nhiên. [Java 17: Comparable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html).

Một record không tự có compareTo chỉ vì nó có các trường số, equals hoặc toString. Khi kiểu không có thứ tự tự nhiên phù hợp, có thể cung cấp một Comparator bên ngoài.

## 3. Comparator mô tả cách ưu tiên riêng của hàng đợi

`Comparator<T>` có phương thức chính:

~~~java
int compare(T left, T right);
~~~

Đây là chữ ký rút gọn để đọc ý nghĩa. Quy tắc nằm ở đối tượng so sánh bên ngoài thay vì nằm trong lớp phần tử.

Với `rule.compare(a, b)`:

~~~text
âm   → a phải được xếp trước b theo rule
0    → rule chưa phân biệt mức của a và b
dương→ a phải được xếp sau b theo rule
~~~

Khi truyền một Comparator khác null vào hàm khởi tạo PriorityQueue, chính quy tắc đó quyết định phần tử nhỏ nhất và đầu hàng đợi. Không có bước tự động dùng thứ tự tự nhiên làm tiêu chí phụ nếu Comparator trả 0.

Bởi vậy, cùng dữ liệu có thể có nhiều hàng đợi phục vụ nhiều mục tiêu:

| Nhu cầu | Quy tắc cần diễn đạt |
| --- | --- |
| Lấy số nhỏ nhất | Thứ tự tự nhiên tăng dần |
| Lấy số lớn nhất | Ngược thứ tự tự nhiên |
| Công việc có mức khẩn lớn hơn đi trước | So sánh mức khẩn theo chiều giảm |
| Cùng mức khẩn thì công việc đến trước đi trước | Ghép số thứ tự đến theo chiều tăng |

Bạn không cần bắt một lớp thực hiện nhiều thứ tự tự nhiên khác nhau cho các màn hình hoặc quy trình khác nhau. Những quy tắc theo từng nhu cầu có thể được giữ ở các Comparator riêng.

## 4. Muốn số lớn nhất ở đầu: đảo quy tắc so sánh

Ví dụ:

~~~java
PriorityQueue<Integer> largestFirst =
        new PriorityQueue<>(Comparator.reverseOrder());
~~~

Với cùng đầu vào `6, 2, 9, 1, 5`:

~~~text
peek()         → 9
poll liên tiếp → 9, 6, 5, 2, 1
~~~

Theo bộ so sánh đảo, số 9 đứng trước số 6, nên 9 là phần tử nhỏ nhất **trong quan hệ do bộ so sánh định nghĩa**. Đây không phải PriorityQueue tự chuyển sang một API “lấy cuối”.

Các thao tác vẫn giống nhau: offer/add thêm, peek xem đầu, poll lấy và xóa đầu. Bạn thay quy tắc ưu tiên lúc tạo đối tượng, không đổi poll thành một phương thức khác.

Phương thức `comparator()` trả bộ so sánh tường minh hoặc null khi dùng thứ tự tự nhiên. Vì vậy:

~~~text
queue.comparator() == null
~~~

không có nghĩa “hàng đợi chưa có thứ tự”. Nó biểu thị không dùng một đối tượng Comparator riêng.

Cũng không suy từ comparator null rằng hàng đợi cho phép thành viên null. Đó là hai câu hỏi khác nhau.

## 5. Chuyển quy tắc nghiệp vụ thành Comparator

Trong bài, mỗi công việc có ba thành phần:

~~~text
id       : tên để nhận biết công việc trong ví dụ
urgency  : mức khẩn; số lớn cần được xử lý trước
sequence : số thứ tự khi công việc được đưa vào; số nhỏ đến trước
~~~

Mô hình:

~~~java
record Job(String id, int urgency, long sequence) {}
~~~

là một kiểu giá trị đơn giản. Nó không triển khai Comparable. Các thành phần dùng cho quy tắc được giữ ổn định sau khi đối tượng được tạo.

Để xử lý mức khẩn cao trước, rồi theo thứ tự đến trong cùng mức, dùng:

~~~java
Comparator<Job> executionOrder =
        Comparator.comparingInt(Job::urgency).reversed()
                .thenComparingLong(Job::sequence);
~~~

Đây là quy tắc được dùng trong chương trình hoàn chỉnh.

Cách đọc từng phần:

1. `Job::urgency` lấy mức khẩn của công việc.
2. `comparingInt` tạo quy tắc so sánh số nguyên theo mức khẩn.
3. `reversed` đảo riêng tiêu chí mức khẩn để số lớn đứng trước.
4. `thenComparingLong` chỉ dùng số thứ tự khi mức khẩn bằng nhau.

Hàng đợi được tạo với:

~~~java
PriorityQueue<Job> scheduled = new PriorityQueue<>(executionOrder);
~~~

Việc Job không có compareTo không gây trở ngại khi Comparator cung cấp so sánh hợp lệ cho các phần tử. Ngược lại, nếu bỏ bộ so sánh mà vẫn dùng Job này, bạn chưa cung cấp con đường tạo thứ tự cho hàng đợi.

## 6. Cùng mức ưu tiên chỉ có thứ tự đến khi đặt khóa phụ

Comparator chỉ đọc `urgency` sẽ trả 0 cho hai Job cùng mức. PriorityQueue vẫn giữ cả hai nhưng không hứa xử lý trước Job được thêm trước. Nếu yêu cầu mức khẩn cao trước và cùng mức thì người đến sớm trước, hãy so `urgency` giảm dần rồi `sequence` tăng dần như `executionOrder` ở mục 5.

Ví dụ `alert(5,1)` và `backup(5,2)` đều đứng trước `report(2,0)`; trong nhóm mức 5, alert đứng trước backup nhờ sequence. Nếu sequence không phân biệt được hai lần gửi, comparator vẫn cho phép hòa. Thứ tự nhận việc và chính sách cấp sequence được phân tích sâu ở bài về phần tử đồng hạng.
## 7. Đặt reversed sai vị trí sẽ đổi cả tiêu chí phụ

So sánh hai biểu thức:

~~~java
Comparator<Job> correctForThisExample =
        Comparator.comparingInt(Job::urgency).reversed()
                .thenComparingLong(Job::sequence);
~~~

và:

~~~java
Comparator<Job> differentRule =
        Comparator.comparingInt(Job::urgency)
                .thenComparingLong(Job::sequence)
                .reversed();
~~~

Biểu thức thứ nhất đảo urgency trước khi ghép sequence. Nó tạo “mức khẩn giảm, số thứ tự tăng”.

Biểu thức thứ hai ghép hai tiêu chí tăng rồi đảo toàn bộ. Nó tạo “mức khẩn giảm, số thứ tự giảm”. Trong nhóm cùng mức, công việc có số đến muộn hơn được xếp trước.

Không thể phát hiện lỗi này bằng mẫu mà mọi công việc đều khác mức khẩn. Hãy có ít nhất một cặp bằng urgency nhưng khác sequence để kiểm chứng ý định.

Các hàm ghép Comparator mô tả thứ tự theo từng tiêu chí. Chỉ khi tiêu chí trước cho kết quả 0 thì tiêu chí sau mới quyết định. Hãy đọc phạm vi của mỗi reversed, không chỉ nhìn thấy từ khóa ấy rồi kết luận “đã là ưu tiên giảm”. [Java 17: Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

## 8. Đồng hạng không làm Queue loại trùng

Với `alpha` và `beta` cùng `urgency = 3`, phép so sánh theo mức khẩn cho 0 nhưng hai record khác nhau vẫn có thể cùng nằm trong PriorityQueue. Thêm lại một phần tử cũng tạo thêm một lần xuất hiện; hàng đợi không có hợp đồng khử trùng.

`contains(Object)` và `remove(Object)` tìm phần tử theo `equals`, không tìm bất kỳ Job nào cùng mức ưu tiên. Chương trình ở mục 10 kiểm chứng kết quả so sánh, phép bằng, kích thước và thao tác tìm một Job khác. Phân biệt rõ `remove()` lấy đầu ưu tiên với `remove(Object)` xóa một giá trị phù hợp.
## 9. Lượt duyệt không phải trình tự lấy đầu

Heap chỉ duy trì quan hệ cha–con đủ để biết phần tử đầu. `iterator()`, for-each, `toArray()` và cách in queue không được bảo đảm theo thứ tự ưu tiên. Muốn xem thứ tự xử lý, dùng `poll()` trên bản sao hoặc sắp một danh sách theo comparator thích hợp. Bài về iterator đi sâu vào các bảo đảm và cách kiểm thử.
## 10. Chương trình đầy đủ dùng Java 17

Lưu thành `PriorityQueueOrderingDemo.java`. Chương trình tránh in trình tự bất kỳ của iterator như một kết quả “đã sắp”. Với các trường hợp bằng ưu tiên chưa có tiêu chí phụ, nó chỉ kiểm tra số lượng và mức khẩn, không giả định thứ tự tên.

Job có toString riêng để kết quả ngắn gọn, theo dạng `id/urgency/sequence`. Thứ tự không được quyết định từ chuỗi hiển thị này; Comparator đọc các trường tương ứng.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;
import java.util.Queue;

public class PriorityQueueOrderingDemo {
    record Job(String id, int urgency, long sequence) {
        @Override
        public String toString() {
            return id + "/" + urgency + "/" + sequence;
        }
    }

    static <E> List<E> drain(Queue<E> queue) {
        List<E> result = new ArrayList<>();
        E next;
        while ((next = queue.poll()) != null) {
            result.add(next);
        }
        return result;
    }

    public static void main(String[] args) {
        List<Integer> input = List.of(6, 2, 9, 1, 5);
        PriorityQueue<Integer> natural = new PriorityQueue<>();
        natural.addAll(input);
        System.out.println("natural comparator is null=" + (natural.comparator() == null));
        System.out.println("natural peek=" + natural.peek());
        System.out.println("natural size after peek=" + natural.size());
        List<Integer> naturalSnapshot = new ArrayList<>(natural);
        naturalSnapshot.sort(natural.comparator());
        System.out.println("natural sorted snapshot=" + naturalSnapshot);
        System.out.println("natural copy drain=" + drain(new PriorityQueue<>(natural)));
        System.out.println("natural original size=" + natural.size());
        System.out.println("natural original poll=" + natural.poll());
        System.out.println("natural original size after poll=" + natural.size());

        PriorityQueue<Integer> reverse =
                new PriorityQueue<>(Comparator.reverseOrder());
        reverse.addAll(input);
        System.out.println("reverse comparator is null=" + (reverse.comparator() == null));
        System.out.println("reverse peek=" + reverse.peek());
        List<Integer> reverseSnapshot = new ArrayList<>(reverse);
        reverseSnapshot.sort(reverse.comparator());
        System.out.println("reverse sorted snapshot=" + reverseSnapshot);
        System.out.println("reverse drain=" + drain(reverse));
        System.out.println("reverse empty peek=" + reverse.peek());
        System.out.println("reverse empty poll=" + reverse.poll());

        Job alpha = new Job("alpha", 3, 0);
        Job beta = new Job("beta", 3, 1);
        Comparator<Job> urgencyOnly = Comparator.comparingInt(Job::urgency);
        PriorityQueue<Job> ties = new PriorityQueue<>(urgencyOnly);
        ties.offer(alpha);
        ties.offer(beta);
        System.out.println("tied comparison=" + urgencyOnly.compare(alpha, beta));
        System.out.println("tied equals=" + alpha.equals(beta));
        System.out.println("tied size=" + ties.size());
        Job probe = new Job("unknown", 3, 99);
        System.out.println("contains equal-priority probe=" + ties.contains(probe));
        System.out.println("remove equal-priority probe=" + ties.remove(probe));
        System.out.println("offer same job again=" + ties.offer(alpha));
        System.out.println("size with repeated job=" + ties.size());
        List<Job> tiedResults = drain(ties);
        System.out.println("tied drain count=" + tiedResults.size());
        System.out.println("all tied urgency=3="
                + tiedResults.stream().allMatch(job -> job.urgency() == 3));

        List<Job> jobs = List.of(
                new Job("report", 2, 0),
                new Job("alert", 5, 1),
                new Job("backup", 5, 2),
                new Job("cleanup", 1, 3));
        Comparator<Job> executionOrder =
                Comparator.comparingInt(Job::urgency).reversed()
                        .thenComparingLong(Job::sequence);
        PriorityQueue<Job> scheduled = new PriorityQueue<>(executionOrder);
        scheduled.addAll(jobs);
        System.out.println("scheduled peek=" + scheduled.peek());
        List<Job> scheduledSnapshot = new ArrayList<>(scheduled);
        scheduledSnapshot.sort(scheduled.comparator());
        System.out.println("scheduled sorted snapshot=" + scheduledSnapshot);
        System.out.println("scheduled copy drain="
                + drain(new PriorityQueue<>(scheduled)));
        System.out.println("scheduled original size=" + scheduled.size());

        PriorityQueue<Job> noRule = new PriorityQueue<>();
        try {
            noRule.offer(new Job("missing", 1, 0));
        } catch (ClassCastException exception) {
            System.out.println("missing natural ordering="
                    + exception.getClass().getSimpleName());
        }

        PriorityQueue<Integer> nullFriendlyRule =
                new PriorityQueue<>(Comparator.nullsFirst(Comparator.naturalOrder()));
        try {
            nullFriendlyRule.offer(null);
        } catch (NullPointerException exception) {
            System.out.println("null despite comparator="
                    + exception.getClass().getSimpleName());
        }
        System.out.println("null queue size=" + nullFriendlyRule.size());

        Comparator<Integer> unsafe = (left, right) -> left - right;
        System.out.println("unsafe edge sign="
                + Integer.signum(unsafe.compare(Integer.MIN_VALUE, Integer.MAX_VALUE)));
        System.out.println("safe edge sign="
                + Integer.signum(Integer.compare(Integer.MIN_VALUE, Integer.MAX_VALUE)));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 PriorityQueueOrderingDemo.java
java PriorityQueueOrderingDemo
~~~

Dùng JDK 17 trở lên. `--release 17` kiểm tra mã và API theo Java 17; tên tệp khớp lớp public.

Kết quả chuẩn:

~~~text
natural comparator is null=true
natural peek=1
natural size after peek=5
natural sorted snapshot=[1, 2, 5, 6, 9]
natural copy drain=[1, 2, 5, 6, 9]
natural original size=5
natural original poll=1
natural original size after poll=4
reverse comparator is null=false
reverse peek=9
reverse sorted snapshot=[9, 6, 5, 2, 1]
reverse drain=[9, 6, 5, 2, 1]
reverse empty peek=null
reverse empty poll=null
tied comparison=0
tied equals=false
tied size=2
contains equal-priority probe=false
remove equal-priority probe=false
offer same job again=true
size with repeated job=3
tied drain count=3
all tied urgency=3=true
scheduled peek=alert/5/1
scheduled sorted snapshot=[alert/5/1, backup/5/2, report/2/0, cleanup/1/3]
scheduled copy drain=[alert/5/1, backup/5/2, report/2/0, cleanup/1/3]
scheduled original size=4
missing natural ordering=ClassCastException
null despite comparator=NullPointerException
null queue size=0
unsafe edge sign=1
safe edge sign=-1
~~~

## 11. Đọc bằng chứng từ chương trình

### 11.1. Tự nhiên: số nhỏ ở đầu

`natural peek=1` đi cùng `natural size after peek=5` xác nhận việc xem đầu không xóa.

Ảnh chụp được sắp và bản sao được lấy hết đều cho `[1, 2, 5, 6, 9]`. `natural original size=5` cho thấy lấy hết trên bản sao không làm rỗng nguồn.

Sau khi thật sự gọi poll trên nguồn, kết quả là 1 và kích thước nguồn còn 4. Đó là thao tác thay đổi dữ liệu, khác với peek.

### 11.2. Đảo: số lớn ở đầu

`reverse peek=9` và `reverse drain=[9, 6, 5, 2, 1]` xác nhận quy tắc đảo đã đổi thứ tự lấy ra.

Hàng đợi reverse bị hàm drain lấy hết trực tiếp. Vì vậy, hai lời gọi xem/lấy sau đó trả null do rỗng. Không có một phần tử mặc định được tạo ra khi hết dữ liệu.

### 11.3. Cùng mức không bị bỏ

`tied size=2` và `size with repeated job=3` cho thấy hàng đợi giữ đủ cả các giá trị khác nhau cùng mức lẫn một lần đưa lại chính alpha.

Kết quả `tied drain count=3` và `all tied urgency=3=true` kiểm tra điều hợp đồng cho phép khẳng định. Chương trình không in thứ tự tên ở nhóm này, vì Comparator chưa đặt một tiêu chí phân biệt giữa các phần tử cùng mức 3.

### 11.4. Tiêu chí phụ tạo thứ tự mong muốn

`scheduled peek=alert/5/1` là đầu theo “mức khẩn giảm rồi sequence tăng”.

Ảnh chụp được sắp và bản sao được lấy hết cùng cho:

~~~text
alert/5/1, backup/5/2, report/2/0, cleanup/1/3
~~~

Alert đứng trước backup vì cả hai cùng mức 5 nhưng alert có sequence nhỏ hơn. Report không lên trước chỉ vì đến sớm hơn; urgency là tiêu chí chính.

`scheduled original size=4` cho thấy việc tạo ảnh chụp và lấy bản sao không rút dữ liệu khỏi nguồn.

## 12. Xem thứ tự mà không làm rỗng hàng đợi

Có hai cách trong chương trình, với mục đích kiểm chứng tương ứng.

**Cách thứ nhất: chụp thành danh sách rồi sắp.**

~~~java
List<Job> snapshot = new ArrayList<>(scheduled);
snapshot.sort(scheduled.comparator());
~~~

Danh sách ban đầu chưa được xem là có thứ tự ưu tiên. Lời gọi sort mới áp dụng quy tắc của nguồn cho ảnh chụp. Thay đổi trình tự danh sách không thay đổi thành viên của hàng đợi.

Đối với ví dụ số tự nhiên, comparator() trả null. `List.sort(null)` được định nghĩa là dùng thứ tự tự nhiên, nên cách viết tương tự vẫn phù hợp với các phần tử có thứ tự tự nhiên hợp lệ. [Java 17: List.sort](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

**Cách thứ hai: tạo PriorityQueue mới từ PriorityQueue nguồn rồi poll bản sao.**

~~~java
PriorityQueue<Job> copy = new PriorityQueue<>(scheduled);
List<Job> ordered = drain(copy);
~~~

Hàm khởi tạo từ PriorityQueue giữ quy tắc thứ tự của nguồn. Bản sao có cấu trúc thành viên độc lập, nên drain(copy) không lấy mất phần tử của scheduled.

Cả hai cách đều là sao chép nông đối với phần tử: danh sách hoặc hàng đợi mới vẫn có thể giữ cùng tham chiếu đối tượng Job. Trong bài, Job là giá trị record với các trường dùng cho ưu tiên ổn định, nên không có thao tác sửa phần tử gây nhiễu.

Nếu Comparator chưa phân biệt các phần tử cùng mức, một danh sách được sort có thể giữ một thứ tự giữa chúng theo đầu vào ảnh chụp, còn poll bản sao có thể chọn khác trong nhóm. Đừng coi một lần hai kết quả trùng nhau là cam kết ổn định của PriorityQueue.

## 13. Comparator phải tuân thủ hợp đồng thứ tự

Một quy tắc tốt cần nhất quán trong các lần so sánh:

- Đảo hai đối số phải đảo dấu kết quả.
- Quan hệ trước/sau phải bắc cầu.
- Khi hai phần tử so sánh bằng 0, chúng phải có quan hệ cùng dấu với một phần tử thứ ba.

Quy tắc phải áp dụng được cho mọi phần tử mà hàng đợi được phép nhận, không chỉ cho một cặp dữ liệu mẫu.

Đừng so sánh số nguyên bằng cách lấy hiệu nếu có thể tràn:

~~~java
Comparator<Integer> unsafe = (left, right) -> left - right;
~~~

Đây là đoạn minh họa lỗi, không được dùng để tạo hàng đợi trong chương trình.

Với Integer.MIN_VALUE và Integer.MAX_VALUE, phép trừ có thể tràn và tạo dấu ngược ý định. Chương trình in:

~~~text
unsafe edge sign=1
safe edge sign=-1
~~~

Dùng Integer.compare hoặc các hàm comparingInt để diễn đạt so sánh số nguyên thay vì dựa vào phép trừ. Khi đảo chiều, dùng reversed hoặc so sánh đúng chiều các đối số.

Đừng trả 1 chỉ để hai phần tử khác nhau không bị “trùng”. PriorityQueue không cần mẹo đó để giữ nhiều phần tử cùng mức, còn một Comparator vi phạm hợp đồng có thể khiến việc chọn đầu không còn đúng yêu cầu.

## 14. Khóa so sánh cần ổn định khi ở trong Queue

Việc sửa trực tiếp `urgency` của một đối tượng đang nằm trong queue hoặc thay đổi trạng thái ngoài mà comparator đọc không tự gọi sift-up/sift-down. `peek()` có thể vẫn trả đầu theo bố trí cũ. Record `Job` của ví dụ giữ các trường so sánh ổn định; nếu cần đổi ưu tiên, hãy thực hiện bước gỡ mục cũ rồi thêm giá trị mới có kiểm soát, đồng thời xét phần tử trùng và chi phí tìm kiếm.

Bài về thay đổi độ ưu tiên giải thích thêm các cách phục hồi heap và các ràng buộc khi cập nhật liên tục.
## 15. Không có thứ tự tự nhiên và không cho phép null

Có hai lỗi khác nhau được kiểm chứng ở cuối chương trình.

**Không có quy tắc so sánh cho Job.**

~~~java
PriorityQueue<Job> noRule = new PriorityQueue<>();
~~~

Job trong bài không triển khai Comparable. Khi không truyền Comparator, việc đưa Job vào dẫn đến ClassCastException trong ví dụ.

Khai báo PriorityQueue<Job> vẫn có thể biên dịch vì PriorityQueue phải hỗ trợ cả những kiểu không Comparable khi có bộ so sánh bên ngoài. Kiểu tổng quát không tự sinh compareTo cho Job.

**Một Comparator chấp nhận null không làm PriorityQueue chấp nhận null.**

Chương trình tạo một bộ so sánh bọc bằng nullsFirst rồi vẫn nhận NullPointerException khi offer(null). PriorityQueue cấm thành viên null theo hợp đồng của chính lớp, trước khi bạn có thể dùng quy tắc ưu tiên để lưu nó.

Không áp dụng suy luận “Comparator của tôi xử lý được null nên mọi cấu trúc nhận nó đều chứa được null”. Chính sách phần tử thuộc về cả lớp nhận, không chỉ hàm so sánh.

Khi hàng đợi hợp lệ rỗng, peek và poll dùng null làm kết quả không có phần tử. Đó là một vai trò khác với cố chèn null vào làm dữ liệu.

## 16. Những giới hạn cần nhớ khi chọn PriorityQueue

PriorityQueue phù hợp khi cần liên tục thêm và lấy phần tử ở đầu theo một thứ tự ưu tiên. Nó không tự cung cấp một danh sách đã sắp hoàn chỉnh cho mọi lượt duyệt.

API mô tả chi phí O(log n) cho các thao tác thêm/lấy như offer, add, poll và remove không đối số; các phép peek, element và size có thời gian hằng. Tìm hoặc xóa theo một đối tượng cụ thể qua contains/remove(Object) cần thời gian tuyến tính trong cách triển khai này.

Không dùng một phép in hoặc một lần đo nhỏ để suy ra những cam kết lớn hơn. Những con số trên mô tả lớp PriorityQueue, không phải mọi Queue có thể dùng trong Java.

Số dung lượng khởi tạo không phải một giới hạn cố định số công việc được nhận. PriorityQueue tự tăng dung lượng lưu trữ theo nhu cầu; chính sách tăng cụ thể không phải API mà mã ứng dụng nên phụ thuộc.

Đồng thời, lớp không được đồng bộ hóa sẵn để nhiều luồng cùng sửa tự do. Chọn Comparator đúng không thay thế thiết kế chia sẻ dữ liệu. Chương trình bài học dùng một luồng và các giá trị ổn định để kết quả có thể đối chiếu trực tiếp.

Nếu mục tiêu chỉ là lấy một ảnh chụp rồi hiển thị toàn bộ theo thứ tự, một danh sách được sort có thể thể hiện công việc đó rõ hơn. Nếu cần dữ liệu duy nhất theo một định nghĩa bằng nhau, phải bổ sung mô hình duy nhất phù hợp; PriorityQueue không tự loại trùng.

## 17. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách kiểm tra đúng |
| --- | --- |
| “Priority cao nghĩa là số lớn nhất luôn ra trước” | Xem Comparator; mặc định Integer nhỏ nhất ở đầu |
| “Poll đổi sang lấy cuối khi dùng reverseOrder” | Poll vẫn lấy đầu, quy tắc xác định đầu đã đổi |
| “Comparator trả null nghĩa là chưa có thứ tự” | Comparator() null biểu thị thứ tự tự nhiên |
| “Record tự có compareTo” | Cần Comparable hoặc Comparator thực sự |
| “Cùng mức ưu tiên sẽ FIFO” | Không có cam kết đó nếu chưa thêm tiêu chí thứ tự đến |
| “Compare bằng 0 thì phần tử mới bị bỏ” | PriorityQueue có thể giữ nhiều thành viên cùng mức và cả bản lặp |
| “Contains tìm mọi phần tử có cùng mức” | Nó tìm theo equals, không dùng nhóm ưu tiên làm nhận diện |
| “Iterator/toString thể hiện thứ tự poll” | Không có bảo đảm; kiểm chứng bằng poll hoặc sắp ảnh chụp |
| “Reversed ở đâu trong chuỗi cũng như nhau” | Đảo cuối chuỗi sẽ đảo cả tiêu chí phụ đã ghép |
| “Lấy hiệu hai số là so sánh an toàn” | Có thể tràn; dùng Integer.compare hoặc hàm chuẩn |
| “Sửa urgency trực tiếp là cập nhật hàng đợi” | Hàng đợi không tự theo dõi và đặt lại vị trí |
| “NullsFirst cho phép chèn null vào PriorityQueue” | Lớp vẫn cấm null |
| “Bản sao tạo đối tượng phần tử hoàn toàn mới” | Việc sao chép cấu trúc không tự nhân bản sâu Job |
| “Dung lượng ban đầu là số công việc tối đa” | Đó không phải giới hạn cố định của PriorityQueue |

Mẫu kiểm tra quan trọng nhất nên có một phần tử đến sớm nhưng ưu tiên thấp, hai phần tử cùng ưu tiên và những giá trị số ở biên. Ba nhóm ấy giúp phát hiện nhầm FIFO, thiếu tiêu chí phụ và lỗi so sánh bằng phép trừ.

## 18. Thực hành có lời giải

### Bài 1: thứ tự tự nhiên

Đưa `8, 3, 6, 1` vào PriorityQueue<Integer> mặc định. Peek trả gì? Lấy hết bằng poll theo thứ tự nào?

**Lời giải:** Peek trả 1 và không xóa. Poll lần lượt cho `1, 3, 6, 8`. Số 8 đến trước không làm nó được ưu tiên hơn.

### Bài 2: đảo quy tắc

Dùng cùng dữ liệu với Comparator.reverseOrder. Đầu và trình tự lấy hết là gì?

**Lời giải:** Đầu là 8. Poll cho `8, 6, 3, 1`. Quy tắc đảo khiến số lớn đứng trước, nhưng poll vẫn thực hiện thao tác lấy đầu.

### Bài 3: ưu tiên nghiệp vụ

Job A có urgency 2, sequence 0; Job B có urgency 5, sequence 1. Theo executionOrder trong bài, ai ra trước?

**Lời giải:** B ra trước vì urgency là tiêu chí chính theo chiều giảm. Sequence sớm hơn của A chỉ có tác dụng khi urgency bằng nhau.

### Bài 4: cùng mức

A và B cùng urgency 4, A đến trước B. Comparator chỉ xét urgency. Có thể kiểm thử rằng A chắc chắn được poll trước không?

**Lời giải:** Không theo hợp đồng PriorityQueue. Muốn thứ tự đến được bảo đảm, cần thêm một tiêu chí tương ứng như sequence tăng dần được cấp đúng cho từng lần đưa vào.

### Bài 5: đảo toàn bộ

Bạn ghép urgency tăng rồi sequence tăng, cuối cùng reversed toàn bộ. Trong nhóm cùng urgency, sequence nhỏ hay lớn đứng trước?

**Lời giải:** Sequence lớn đứng trước vì toàn bộ quy tắc đã bị đảo. Điều đó khác với đảo riêng urgency rồi ghép sequence tăng.

### Bài 6: phần tử cùng ưu tiên

Hai Job khác nhau theo equals nhưng Comparator trả 0. Thêm cả hai vào PriorityQueue có bắt buộc chỉ giữ một không?

**Lời giải:** Không. Cả hai có thể được giữ. PriorityQueue không dùng compare bằng 0 để loại thành viên như một tập sắp xếp.

### Bài 7: tìm theo probe cùng mức

Hàng đợi có alpha với urgency 3. Probe có id khác và sequence khác nhưng cũng urgency 3. Contains(probe) có true chỉ vì cùng mức không?

**Lời giải:** Không. Contains dùng equals. Record Job xét các thành phần, nên probe khác những giá trị ấy không được coi là cùng phần tử chỉ vì cùng urgency.

### Bài 8: hiển thị theo ưu tiên mà giữ nguồn

Bạn cần in toàn bộ Job theo executionOrder nhưng không làm rỗng scheduled. Có hai cách nào trong bài?

**Lời giải:** Chụp sang ArrayList rồi sort bằng comparator của scheduled; hoặc tạo PriorityQueue bản sao giữ cùng quy tắc rồi poll bản sao. Chỉ dựa vào iterator hoặc toString của nguồn không bảo đảm thứ tự ưu tiên.

### Bài 9: Job chưa có Comparable

Một record Job không triển khai Comparable được đưa vào PriorityQueue không truyền Comparator. Việc kiểu tổng quát biên dịch được có chứng minh hàng đợi dùng được không?

**Lời giải:** Không. Bạn vẫn phải cung cấp thứ tự tự nhiên hoặc Comparator hợp lệ. Chương trình minh họa ClassCastException khi thiếu cả con đường tự nhiên lẫn bộ so sánh riêng.

### Bài 10: null

Comparator được bọc bằng nullsFirst. Offer(null) vào PriorityQueue có được phép không?

**Lời giải:** Không. PriorityQueue cấm null theo hợp đồng lớp. Khả năng xử lý null của Comparator không thay đổi điều đó.

### Bài 11: thay đổi mức khẩn

Một đối tượng đang nằm trong hàng đợi bị gán urgency mới. Có thể giả định peek sau đó tự phản ánh vị trí mới không?

**Lời giải:** Không. Hàng đợi không tự theo dõi mọi phép gán bên trong. Dùng dữ liệu ổn định và một thao tác cập nhật ưu tiên được thiết kế rõ ràng.

### Bài 12: giá trị biên

Vì sao Comparator<Integer> viết bằng left - right có thể chọn sai đầu với số rất nhỏ và số rất lớn?

**Lời giải:** Phép trừ int có thể tràn, làm dấu kết quả sai. Integer.compare hoặc các hàm so sánh chuẩn diễn đạt thứ tự mà không cần lấy hiệu như vậy.

## 19. Tự kiểm tra khi viết quy tắc mới

Trước khi tạo PriorityQueue, hãy trả lời bằng lời phần tử nào phải ra trước và vì sao. Chuyển câu trả lời thành từng tiêu chí, xác định chiều của từng tiêu chí và cách giải quyết trường hợp bằng nhau.

Tiếp theo, kiểm tra bằng trình tự poll thực sự trên một mẫu có ý nghĩa. Nếu cần giữ nguồn, dùng ảnh chụp đã sắp hoặc bản sao có cùng quy tắc.

Cuối cùng, giữ riêng ba vấn đề: thứ tự ưu tiên, nhận diện phần tử theo equals và sự ổn định của dữ liệu trong thời gian lưu. Một Comparator đúng giúp chọn đầu; nó không tự cung cấp loại trùng, cập nhật ngầm hoặc FIFO cho các trường hợp mà quy tắc chưa phân biệt.
