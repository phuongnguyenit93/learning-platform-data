# remove(Object), contains và chi phí tìm phần tử

## 1. Chọn đầu ưu tiên nhanh không đồng nghĩa tìm mọi phần tử đều nhanh

Một PriorityQueue có thể nhanh chóng cho biết công việc nào đứng đầu theo mức ưu tiên. Nhưng nếu câu hỏi là “công việc beta có còn ở trong hàng đợi không?” hoặc “hãy xóa đúng công việc beta”, đó là một loại thao tác khác.

Heap ưu tiên được tổ chức để phục vụ việc chọn đầu. Nó không phải bảng tra cứu theo mọi thuộc tính của công việc và cũng không phải cây tìm kiếm có thể rẽ trái/phải theo một khóa bất kỳ.

Vì vậy, cần tách:

- `peek()`: xem đầu ưu tiên.
- `poll()` hoặc `remove()` không đối số: lấy ra đầu ưu tiên.
- `contains(Object)`: tìm xem có phần tử bằng giá trị được hỏi hay không.
- `remove(Object)`: tìm và xóa một phần tử bằng giá trị được hỏi.

Trong PriorityQueue chuẩn, contains và remove có đối số có chi phí tìm tuyến tính theo số thành viên. Nếu dùng chúng thường xuyên, phần tìm này có thể chiếm nhiều công việc hơn phần duy trì heap.

Bài học giải thích nhận diện bằng equals, bản trùng, các chữ ký dễ nhầm và cách đánh giá chi phí bằng một phép kiểm chứng có đếm thao tác. Chương trình đầy đủ dùng API có trong Java 17.

Bạn cần biết biến, đối tượng, phương thức và vòng lặp. Những quan hệ giữa equals, Comparator và heap sẽ được giới thiệu đúng phạm vi cần dùng.

## 2. Ba câu hỏi khác nhau về một phần tử

Xét các công việc có hai thuộc tính:

~~~text
id       : tên nhận diện trong ví dụ
priority : số ưu tiên; số nhỏ được chọn trước
~~~

Chương trình dùng `record Task(String id, int priority)`. Với record này, phép bằng nhau mặc định xét các thành phần, không chỉ id.

Khi có hai Task, hãy phân biệt:

| Câu hỏi | Cơ chế |
| --- | --- |
| Hai biến có trỏ tới chính cùng đối tượng không? | `==` |
| Hai giá trị Task có bằng nhau không? | `equals` |
| Hai Task có cùng mức trong quy tắc ưu tiên không? | `Comparator.compare(a, b) == 0` |

Nếu Comparator chỉ đọc priority, `Task("alpha", 2)` và `Task("beta", 2)` cho kết quả so sánh 0 nhưng không bằng nhau theo equals. Chúng cùng mức ưu tiên, không phải cùng một giá trị Task.

Ngược lại, `new Task("beta", 2)` là một đối tượng mới nhưng bằng một Task beta/2 đã lưu. Contains có thể tìm được nó dù hai tham chiếu khác nhau.

Không suy “đã có cùng mức ưu tiên” thành “đã có đúng công việc cần tìm”. Cũng không yêu cầu phải giữ chính tham chiếu ban đầu mới có thể tìm hoặc xóa theo giá trị, nếu equals của kiểu đã thể hiện quan hệ phù hợp.

## 3. contains dùng equals, không dùng nhóm ưu tiên

Hợp đồng của `PriorityQueue.contains(o)` kiểm tra có thành viên e mà `o.equals(e)` đúng hay không. Nó không hỏi có phần tử nào mà Comparator so sánh bằng 0 với o.

Ví dụ hàng đợi có beta/2:

~~~text
contains(new Task("beta", 2))   → true
contains(new Task("unknown", 2)) → false
~~~

Giá trị dò unknown/2 cùng priority 2, nhưng id khác nên equals khác. Comparator chỉ xét priority không làm giá trị dò ấy trở thành beta.

Contains chỉ đọc. Nó không xóa thành viên, không đưa phần tử được tìm thấy lên đầu và không làm mới ưu tiên.

Quy tắc equals thuộc về kiểu phần tử. Nếu lớp không ghi đè equals và dùng hành vi nhận diện đối tượng mặc định, một đối tượng mới có các trường nhìn giống nhau chưa chắc được tìm thấy. Nếu kiểu tự định nghĩa equals theo mã, phép tìm sẽ theo quan hệ đó.

Với record Task của bài, hỏi bằng id giống nhưng priority khác cũng không phải hỏi cùng giá trị, vì cả hai thành phần tham gia equals. Nếu nghiệp vụ thật nhận diện công việc chỉ bằng id, cần một mô hình khóa hoặc phép bằng nhau phù hợp, không được suy từ tên trường id. [Java 17: PriorityQueue.contains](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html#contains(java.lang.Object)).

## 4. remove(Object) xóa một phần tử bằng nhau, không nhất thiết là đầu

`remove(o)` có đối số tìm một thành viên bằng o theo equals. Nếu có, nó xóa một lần xuất hiện và trả true. Nếu không có, nó trả false.

Ví dụ hàng đợi chứa:

~~~text
first/1
alpha/2
beta/2
later/9
~~~

Gọi `remove(new Task("beta", 2))` không có nghĩa “bỏ công việc ưu tiên cao nhất”. Nó tìm beta/2 và xóa giá trị ấy; first/1 vẫn có thể đứng đầu.

Một giá trị dò khác có cùng mức ưu tiên nhưng không bằng nhau không được dùng để xóa tùy ý một phần tử trong nhóm:

~~~text
remove(new Task("unknown", 2)) → false
~~~

Lời gọi này không tự chọn alpha/2 hoặc beta/2 để xóa thay.

Nếu có nhiều phần tử bằng nhau, remove(Object) chỉ xóa một lần xuất hiện. PriorityQueue cho phép bản trùng, kể cả việc đưa cùng một đối tượng vào nhiều lần. Không có cơ chế tự loại trùng khi thêm.

Đừng dựa vào remove(Object) để chọn “bản bằng nhau đến sớm nhất” hoặc “đúng tham chiếu này” khi có nhiều đại diện bằng nhau. Hợp đồng mô tả xóa một phần tử phù hợp equals, không cung cấp chính sách lịch sử cho các bản ấy. [Java 17: PriorityQueue.remove(Object)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html#remove(java.lang.Object)).

## 5. remove() và remove(Object) có mục đích, kết quả và chi phí khác nhau

| Chữ ký | Chọn phần tử bằng cách nào? | Kết quả | Khi không có đối tượng phù hợp |
| --- | --- | --- | --- |
| `remove()` | Chọn đầu theo ưu tiên | Phần tử bị lấy ra | Ném NoSuchElementException khi rỗng |
| `poll()` | Chọn đầu theo ưu tiên | Phần tử bị lấy ra | Trả null khi rỗng |
| `remove(Object o)` | Tìm theo equals với o | boolean | Trả false nếu không tìm thấy |
| `contains(Object o)` | Tìm theo equals với o | boolean | Trả false nếu không tìm thấy |

Điểm dễ gây nhầm với số nguyên:

~~~java
PriorityQueue<Integer> numbers =
        new PriorityQueue<>(List.of(5, 1, 3, 2, 4));

boolean removed = numbers.remove(3);
~~~

Đây là đoạn minh họa với các kiểu java.util tương ứng. PriorityQueue không có thao tác remove theo chỉ số. Giá trị int 3 được đóng gói để truyền vào phương thức nhận Object, và mã xóa một phần tử có giá trị 3.

Nó không xóa phần tử ở vị trí thứ ba của một danh sách. Kết quả là boolean, không phải phần tử bị lấy khỏi một chỉ số.

Sau đó `numbers.remove()` không đối số lại có nghĩa khác: lấy đầu nhỏ nhất hiện có. Luôn đọc cả dấu ngoặc và đối số khi đánh giá hành vi hoặc độ phức tạp.

## 6. Vì sao heap không đem lại tìm kiếm tùy ý O(log n)?

Một heap nhỏ nhất chỉ yêu cầu mỗi nút cha không đứng sau các con theo quy tắc ưu tiên. Nó không có quy tắc “mọi giá trị bên trái nhỏ hơn, mọi giá trị bên phải lớn hơn” như một cây tìm kiếm theo khóa.

Mô hình minh họa:

~~~text
        1
      /   \
     4     2
    / \   /
   8   7 3
~~~

Cả hai nhánh có thể chứa những phần tử phù hợp với một phép tìm theo giá trị. So sánh một khóa tìm với một nút không cung cấp cùng quy tắc rẽ nhánh như cây tìm kiếm.

Hơn nữa, contains phải tuân theo equals, trong khi heap được tổ chức bằng Comparator hoặc compareTo. Hai quan hệ không nhất thiết xem cùng một nhóm đối tượng là tương đương.

Vì vậy, PriorityQueue không dùng một phép tìm nhị phân trên toàn bộ dãy lưu trữ để thực hiện contains. Dãy nhìn thấy qua iterator hoặc toArray cũng không được cam kết đã sắp xếp, nên không thể đưa nó thẳng vào thuật toán tìm nhị phân rồi coi kết quả là đúng.

Tổ chức để chọn đầu và tổ chức để tra cứu theo định danh là hai yêu cầu dữ liệu riêng. Một cấu trúc tối ưu cho yêu cầu thứ nhất không tự cung cấp chỉ mục cho yêu cầu thứ hai.

## 7. Quá trình tìm rồi xóa có hai phần chi phí

Trong OpenJDK 17, contains và remove(Object) cùng dùng một bước tìm chỉ số bằng cách kiểm tra equals với các thành viên. Không tìm thấy thì kết thúc; tìm thấy để xóa thì chuyển sang bước sửa heap. [Mã nguồn PriorityQueue, OpenJDK 17](https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/util/PriorityQueue.java).

Có thể đọc theo sơ đồ:

~~~text
contains(o)
  → tìm một thành viên bằng o
  → trả có / không

remove(o)
  → tìm một thành viên bằng o
  → nếu không có: trả false
  → nếu có: xóa ở vị trí đã tìm, khôi phục heap, trả true
~~~

Tìm theo giá trị có thể phải xét toàn bộ n thành viên. Sau khi biết chỗ cần xóa, phần tử cuối được dùng để lấp chỗ và quan hệ heap được khôi phục theo hướng cần thiết.

Ví dụ mô hình trước khi xóa 2:

~~~text
        1
      /   \
     2     3
    / \   / \
   4   5 6   7
~~~

Đưa 7 vào chỗ của 2 chưa đủ: 7 đang đứng trước các con 4, 5 sai quan hệ. Cần sửa vị trí để một heap hợp lệ lại được duy trì. Đây là giải thích cơ chế, không khẳng định bố trí nội bộ của mọi hàng đợi phải giống sơ đồ.

Không phải mỗi lần xóa đều sắp xếp lại toàn bộ một danh sách. Bước sửa heap khác với bước tìm thành viên, và chính bước tìm làm cho remove(Object) có chi phí tuyến tính trong trường hợp xấu.

## 8. Đọc đúng bảng độ phức tạp

Với n là số thành viên đang có, mô tả chi phí của PriorityQueue:

| Thao tác | Chi phí theo mô tả của lớp |
| --- | --- |
| `peek` / `element` / `size` | O(1) |
| `offer` / `add` | O(log n) |
| `poll` / `remove()` | O(log n) |
| `contains(Object)` | O(n) |
| `remove(Object)` | O(n) |

Các dòng O(n) không có nghĩa mọi lời gọi luôn phải đi hết n phần tử. Nếu tìm thấy ngay, phần tìm có thể kết thúc sớm. Nếu phần tử vắng mặt hoặc nằm muộn trong vùng tìm, số lần kiểm tra có thể tăng tới n.

Đối với remove(Object), biết đúng vị trí ngay từ đầu vẫn còn bước sửa heap. Đếm chỉ một lần equals ở đầu không chứng minh toàn bộ phép xóa có thời gian hằng.

Trong bước tìm của cách triển khai được đối chiếu, n là size, không phải toàn bộ dung lượng mảng đã cấp phát. Không cần kiểm tra từng ô dự phòng không có thành viên.

Các ký hiệu trên thường tách khỏi độ phức tạp bên trong equals và Comparator. Nếu mỗi equals so sánh nhiều trường dài, chi phí thực tế của bước tìm còn gồm công việc đó. Với chi phí mỗi phép equals là C_eq và mỗi so sánh ưu tiên là C_cmp, có thể hình dung phần tìm/xóa gồm một chặn theo n·C_eq cộng với phần sửa heap theo log(n)·C_cmp.

Đây là cách phân tích số công việc, không phải cam kết một số mili giây cố định trên mọi máy. [Java 17: PriorityQueue, ghi chú chi phí thao tác](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).

## 9. Chương trình đầy đủ dùng Java 17

Lưu thành `PriorityQueueSearchDemo.java`. Chương trình có ba nhóm kiểm chứng:

1. Các Task cùng ưu tiên nhưng khác equals, và hai lần xuất hiện của beta.
2. Remove có đối số trên PriorityQueue<Integer>, không phải xóa theo chỉ số.
3. Một kiểu Key đếm số lần equals để quan sát việc tìm.

Key có equals/hashCode theo id. Bộ đếm tĩnh chỉ phục vụ bài thử một luồng; kết quả bằng nhau vẫn được quyết định bằng id. Chương trình không dùng bộ đếm như một phần quy tắc nhận diện.

Các danh sách id được sắp để đối chiếu nội dung. Chúng không được trình bày như thứ tự iterator hoặc thứ tự lấy ra khi có các Task bằng ưu tiên.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class PriorityQueueSearchDemo {
    record Task(String id, int priority) {}

    static final class Key {
        static int equalityCalls;
        final int id;

        Key(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            equalityCalls++;
            return other instanceof Key key && id == key.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    static List<String> sortedIds(PriorityQueue<Task> queue) {
        return queue.stream().map(Task::id).sorted().toList();
    }

    static long countEqual(PriorityQueue<Task> queue, Task probe) {
        return queue.stream().filter(probe::equals).count();
    }

    static List<Integer> drainPriorities(PriorityQueue<Task> queue) {
        List<Integer> result = new ArrayList<>();
        Task task;
        while ((task = queue.poll()) != null) {
            result.add(task.priority());
        }
        return result;
    }

    public static void main(String[] args) {
        Comparator<Task> byPriority = Comparator.comparingInt(Task::priority);
        PriorityQueue<Task> tasks = new PriorityQueue<>(byPriority);
        Task beta = new Task("beta", 2);
        tasks.addAll(List.of(
                new Task("alpha", 2),
                beta,
                new Task("later", 9),
                new Task("first", 1),
                beta));
        System.out.println("initial ids=" + sortedIds(tasks));
        System.out.println("initial size=" + tasks.size());
        System.out.println("head priority=" + tasks.peek().priority());

        Task equalProbe = new Task("beta", 2);
        Task samePriority = new Task("unknown", 2);
        System.out.println("equal probe is same reference=" + (equalProbe == beta));
        System.out.println("equal probe equals beta=" + equalProbe.equals(beta));
        System.out.println("contains equal probe=" + tasks.contains(equalProbe));
        System.out.println("same-priority comparison=" + byPriority.compare(samePriority, beta));
        System.out.println("same-priority equals=" + samePriority.equals(beta));
        System.out.println("contains same-priority probe=" + tasks.contains(samePriority));
        System.out.println("remove same-priority probe=" + tasks.remove(samePriority));
        System.out.println("size after missing removal=" + tasks.size());

        System.out.println("beta count before=" + countEqual(tasks, equalProbe));
        System.out.println("remove one beta=" + tasks.remove(equalProbe));
        System.out.println("beta count after one=" + countEqual(tasks, equalProbe));
        System.out.println("size after one=" + tasks.size());
        System.out.println("head priority after one=" + tasks.peek().priority());
        System.out.println("ids after one=" + sortedIds(tasks));
        System.out.println("still contains beta=" + tasks.contains(equalProbe));
        System.out.println("remove second beta=" + tasks.remove(equalProbe));
        System.out.println("remove beta again=" + tasks.remove(equalProbe));
        System.out.println("ids after both=" + sortedIds(tasks));
        System.out.println("remaining priorities poll=" + drainPriorities(tasks));
        System.out.println("contains null=" + tasks.contains(null));
        System.out.println("remove null=" + tasks.remove(null));

        PriorityQueue<Integer> numbers =
                new PriorityQueue<>(List.of(5, 1, 3, 2, 4));
        boolean removedByValue = numbers.remove(3);
        System.out.println("integer remove(3)=" + removedByValue);
        List<Integer> snapshot = new ArrayList<>(numbers);
        snapshot.sort(Comparator.naturalOrder());
        System.out.println("numbers after value removal=" + snapshot);
        System.out.println("contains text 4=" + numbers.contains("4"));
        System.out.println("remove text 4=" + numbers.remove("4"));
        System.out.println("remove() head=" + numbers.remove());
        System.out.println("poll head=" + numbers.poll());

        for (int n : new int[] {8, 16, 32}) {
            PriorityQueue<Key> counted =
                    new PriorityQueue<>(Comparator.comparingInt(key -> key.id));
            for (int id = 0; id < n; id++) {
                counted.offer(new Key(id));
            }

            Key.equalityCalls = 0;
            boolean found = counted.contains(new Key(-1));
            System.out.println("n=" + n + " contains missing=" + found
                    + " equals calls=" + Key.equalityCalls);

            Key.equalityCalls = 0;
            boolean removedMissing = counted.remove(new Key(-1));
            System.out.println("n=" + n + " remove missing=" + removedMissing
                    + " equals calls=" + Key.equalityCalls);

            Key.equalityCalls = 0;
            boolean removedMinimum = counted.remove(new Key(0));
            System.out.println("n=" + n + " remove minimum by value=" + removedMinimum
                    + " equals calls=" + Key.equalityCalls);
            System.out.println("n=" + n + " next minimum=" + counted.peek().id);
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 PriorityQueueSearchDemo.java
java PriorityQueueSearchDemo
~~~

Dùng JDK 17 trở lên. `--release 17` kiểm tra mã và API theo Java 17; tên tệp khớp lớp public.

Kết quả chuẩn:

~~~text
initial ids=[alpha, beta, beta, first, later]
initial size=5
head priority=1
equal probe is same reference=false
equal probe equals beta=true
contains equal probe=true
same-priority comparison=0
same-priority equals=false
contains same-priority probe=false
remove same-priority probe=false
size after missing removal=5
beta count before=2
remove one beta=true
beta count after one=1
size after one=4
head priority after one=1
ids after one=[alpha, beta, first, later]
still contains beta=true
remove second beta=true
remove beta again=false
ids after both=[alpha, first, later]
remaining priorities poll=[1, 2, 9]
contains null=false
remove null=false
integer remove(3)=true
numbers after value removal=[1, 2, 4, 5]
contains text 4=false
remove text 4=false
remove() head=1
poll head=2
n=8 contains missing=false equals calls=8
n=8 remove missing=false equals calls=8
n=8 remove minimum by value=true equals calls=1
n=8 next minimum=1
n=16 contains missing=false equals calls=16
n=16 remove missing=false equals calls=16
n=16 remove minimum by value=true equals calls=1
n=16 next minimum=1
n=32 contains missing=false equals calls=32
n=32 remove missing=false equals calls=32
n=32 remove minimum by value=true equals calls=1
n=32 next minimum=1
~~~

## 10. Đọc kết quả tìm kiếm và nhận diện

### 10.1. Khác tham chiếu nhưng bằng giá trị vẫn tìm thấy

`equal probe is same reference=false` cho biết equalProbe không phải chính đối tượng beta ban đầu.

`equal probe equals beta=true` và `contains equal probe=true` cho thấy equals đủ để tìm thấy một thành viên. Không cần giữ nguyên tham chiếu đã đưa vào hàng đợi nếu kiểu đã có phép bằng nhau phù hợp.

### 10.2. Cùng mức ưu tiên chưa phải cùng phần tử

`same-priority comparison=0` nhưng `same-priority equals=false`. Cả contains và remove với giá trị dò unknown/2 đều trả false.

`size after missing removal=5` xác nhận không có thành viên nào bị xóa thay từ nhóm priority 2. Remove theo giá trị không lựa ngẫu nhiên một phần tử có mức bằng giá trị dò.

### 10.3. Contains không phải thao tác lấy

Đầu có priority 1 trước các phép tìm. Việc đọc contains hoặc thất bại khi xóa giá trị dò không chuyển beta lên đầu và không rút first/1 ra.

Khi cần xử lý phần tử ưu tiên tiếp theo, dùng poll hoặc remove không đối số. Dùng contains để kiểm tra một giá trị không thay thế thao tác lấy đầu.

## 11. Xóa một lần xuất hiện và khôi phục heap

Ban đầu beta xuất hiện hai lần. Chương trình kiểm tra:

~~~text
beta count before=2
remove one beta=true
beta count after one=1
size after one=4
~~~

Kết quả không phải remove “chưa xóa đủ” theo một lỗi triển khai. Hợp đồng chỉ yêu cầu loại một lần xuất hiện phù hợp.

`still contains beta=true` sau lần xóa đầu là đúng vì còn một beta. Lần xóa thứ hai trả true; lần thứ ba mới trả false.

Đầu có priority 1 vẫn còn sau khi xóa beta/2. Điều này giúp phân biệt xóa một đối tượng chỉ định với lấy đầu.

Cuối cùng, `remaining priorities poll=[1, 2, 9]` cho thấy phần còn lại vẫn được lấy theo ưu tiên. Alpha/2 vẫn còn dù beta/2 cùng mức đã bị loại. Kiểm tra này xác nhận ý nghĩa thành viên và trình tự ưu tiên sau thao tác xóa trong ví dụ.

Nếu cần xóa **mọi** phần tử bằng một giá trị, phải chọn một hợp đồng riêng, chẳng hạn một phép loại theo điều kiện phù hợp. Lặp remove có thể đúng về chức năng nhưng mỗi lần có thể phải tìm lại; khi số lần xóa lớn, chi phí lặp không còn chỉ là một lần O(n).

Không dựa vào việc các bản bằng nhau được lưu cùng nhau hoặc được lấy theo thứ tự đến. PriorityQueue không cung cấp những bảo đảm ấy.

## 12. Contains và remove với null hoặc một kiểu giá trị dò khác

PriorityQueue cấm thêm thành viên null. Trong ví dụ, contains(null) và remove(null) đều trả false. Câu “không cho lưu null” không có nghĩa mọi phương thức nhận đối số null đều phải ném lỗi giống offer(null).

Các chữ ký tìm/xóa nhận Object, nên bạn cũng có thể viết:

~~~java
numbers.contains("4");
numbers.remove("4");
~~~

qua PriorityQueue<Integer>. Hai lời gọi trong chương trình trả false vì chuỗi “4” không bằng Integer 4 theo equals của các kiểu đó.

Chúng không cố chèn chuỗi vào hàng đợi, cũng không dùng Comparator tự nhiên để biến chuỗi thành số. Vì vậy, không nên gán chính sách so sánh khi chèn một kiểu sai cho mọi phép hỏi nhận Object.

Điều này không cho phép bỏ qua việc định nghĩa equals đúng. Một kiểu có equals bất thường, không đối xứng hoặc ném lỗi ngoài hợp đồng có thể làm hành vi tìm theo giá trị khó hiểu. Hãy giữ quy tắc bằng nhau là quan hệ hợp lệ và ổn định.

Với Task, record mặc định xét id và priority. Nếu bạn cần hủy theo id mà không biết priority đang được lưu, một Task tự tạo với id đúng nhưng priority đoán khác không tự khớp equals. Cần phương án nhận diện hoặc chỉ mục theo id rõ ràng.

## 13. Đếm thao tác để hiểu chi phí, không lấy một thời gian chạy làm kết luận

Chương trình tạo hàng đợi Key có 8, 16 rồi 32 phần tử. Mỗi Key có một id, còn Comparator sắp theo id. Sau khi tạo xong dữ liệu, bộ đếm equals được đặt về 0 trước mỗi phép thử.

Giá trị dò id -1 không tồn tại. Kết quả:

~~~text
n=8  : contains vắng → 8 lần equals
n=16 : contains vắng → 16 lần equals
n=32 : contains vắng → 32 lần equals
~~~

Remove với cùng giá trị dò vắng cũng cho số lần tương ứng. Nó cần xác nhận không có một thành viên bằng giá trị dò trước khi trả false.

Đây là quan sát ở cách triển khai đang chạy, phù hợp với bước quét được đối chiếu trong OpenJDK 17. Số lần equals chính xác không phải API mà ứng dụng nên buộc mọi phiên bản phải giữ; kết luận quan trọng để chọn cấu trúc là chi phí tìm tuyến tính được mô tả cho lớp.

Bài thử không cần dùng đồng hồ để thấy số kiểm tra tăng cùng số thành viên. Đo thời gian ở các kích thước nhỏ dễ bị ảnh hưởng bởi nhiều yếu tố ngoài phép tìm.

### Vì sao xóa phần tử nhỏ nhất chỉ đếm một equals?

Với giá trị dò id 0, phần tử phù hợp đang ở đầu vùng tìm của ví dụ. Equals khớp ngay nên bộ đếm bằng 1.

Nhưng sau khi xóa, hàng đợi vẫn cần sửa heap để đầu mới là id 1. Bộ đếm không đếm các lời gọi Comparator hoặc các lần di chuyển tham chiếu.

Vì thế:

~~~text
equals calls=1
~~~

không chứng minh toàn bộ remove(Object) có chi phí O(1). Nó chỉ mô tả phần công việc mà thiết bị đo trong ví dụ thật sự đếm.

Cùng nguyên tắc ấy, không thể đo ít lời gọi equals rồi kết luận tất cả thao tác trên PriorityQueue đều nhanh như xem đầu.

## 14. Tránh tìm hai lần khi chỉ cần kết quả xóa

Đoạn ý tưởng:

~~~java
if (queue.contains(probe)) {
    queue.remove(probe);
}
~~~

kiểm tra rồi xóa bằng hai thao tác tìm độc lập. Nó có thể làm lại công việc trong trường hợp phần tử tồn tại.

Nếu mục đích là “thử xóa và biết có xóa được không”, giá trị boolean từ remove đã trả lời:

~~~java
boolean removed = queue.remove(probe);
~~~

Đây là các đoạn minh họa với queue và giá trị dò đã khai báo. Không cần contains trước để được phép gọi remove; không tìm thấy thì remove trả false.

Contains trước cũng không dành riêng thành viên cho lần remove sau. Nếu có thao tác xen vào, trạng thái giữa hai lời gọi có thể thay đổi. PriorityQueue không được đồng bộ hóa sẵn để nhiều luồng tùy ý cùng sửa.

Điều này không có nghĩa một lần remove đã giải quyết mọi vấn đề cạnh tranh. Nó chỉ tránh một phép tìm thừa khi yêu cầu có thể được diễn đạt bằng chính kết quả của thao tác xóa.

Nếu chỉ muốn biết có mặt và hoàn toàn không sửa dữ liệu, contains vẫn là thao tác đúng về chức năng. Vấn đề là chọn đúng mục đích và hiểu chi phí.

## 15. Khi truy vấn theo định danh xuất hiện thường xuyên

Nếu ứng dụng chủ yếu thêm rồi lấy đầu theo ưu tiên, PriorityQueue có thể đáp ứng trực tiếp. Nếu mỗi công việc lại bị tìm hoặc hủy theo id nhiều lần, những lần quét O(n) có thể trở thành phần chi phí cần thiết kế lại.

Một chỉ mục phụ theo khóa có thể giúp hỏi về sự hiện diện theo khóa đó. Nhưng thêm một HashSet không tự làm remove(Object) của PriorityQueue tìm được vị trí nhanh hơn; hàng đợi vẫn không được cung cấp một địa chỉ phần tử từ HashSet.

Cũng phải xét bản trùng. Nếu cùng một giá trị xuất hiện hai lần, xóa một lần chưa làm giá trị ấy vắng mặt. Một tập khóa đơn giản có thể bị cập nhật sai khi bạn loại khóa ngay sau lần poll hoặc remove đầu tiên. Mô hình đếm số lần theo khóa có thể phù hợp hơn nếu sự trùng lặp được phép, cùng quy tắc cập nhật cho mọi đường thêm/lấy/xóa.

Đối với việc hủy, có thể có thiết kế đánh dấu không còn hiệu lực rồi bỏ qua khi phần tử lên đầu. Đó là xóa ở mức logic, không phải loại vật lý ngay khỏi PriorityQueue. Cần hiểu tác động lên dung lượng dữ liệu đang giữ và cách nhận diện những lần đưa lại cùng id.

Nếu cần xóa tùy ý nhanh bằng một địa chỉ hoặc chỉ mục vị trí, phải chọn một cấu trúc có khả năng đó hoặc xây mô hình chỉ mục được duy trì đúng. Không truy cập mảng riêng của PriorityQueue để coi một chỉ số nội bộ là ổn định; sửa heap có thể chuyển các phần tử.

Các lựa chọn này là thay đổi mô hình dữ liệu, không phải đổi tên một lời gọi contains thành remove. Trước khi thêm cấu trúc phụ, hãy xác định rõ khóa, bản trùng, cách cập nhật và tần suất truy vấn thực tế.

## 16. Sự hiện diện không chứng minh thứ tự ưu tiên còn hợp lệ

Một Task có thể được tìm thấy theo equals mà điều đó không chứng minh mọi quan hệ ưu tiên trong hàng đợi đang đúng với ý định.

Ví dụ, nếu dùng đối tượng có trường priority sửa được và đổi nó trực tiếp khi đối tượng còn trong heap, contains có thể vẫn tìm theo equals hoặc định danh. Nhưng PriorityQueue không tự nhận một sự kiện sửa heap chỉ vì trường nội bộ của phần tử đổi.

Hai vấn đề cần tách:

- Quy tắc nhận diện quyết định giá trị dò nào bằng phần tử.
- Quy tắc ưu tiên quyết định phần tử nào phải lên đầu.

Trong bài, Task là record có thành phần được xác lập khi tạo. Không có thao tác gán lại priority trong lúc lưu, nên phép thử tập trung vào ý nghĩa tìm/xóa.

Nếu cần đổi ưu tiên, thiết kế một quy trình cập nhật rõ ràng cho mục dữ liệu cụ thể. Nếu cùng một đối tượng hoặc giá trị được đưa vào nhiều lần, cũng cần hiểu tác động lên các lần xuất hiện ấy.

Không dùng kết quả contains=true như một phép kiểm tra đầy đủ về tính đúng của cấu trúc hoặc thuật toán xử lý. Nó chỉ trả lời sự hiện diện theo hợp đồng của phương thức.

## 17. Những nhầm lẫn thường gặp

| Nhầm lẫn | Điều cần kiểm tra |
| --- | --- |
| “Heap nên mọi tìm kiếm đều O(log n)” | Heap phục vụ chọn đầu; contains/remove(Object) của PriorityQueue tuyến tính |
| “Cùng priority thì contains true” | Contains dùng equals, không chỉ Comparator |
| “Phải cùng tham chiếu mới xóa được” | Một giá trị dò khác tham chiếu vẫn khớp nếu equals đúng |
| “Record có trường id nên mặc định chỉ xét id” | Record Task của bài xét cả id và priority |
| “Remove(Object) xóa hết bản trùng” | Mỗi lần chỉ xóa một thành viên phù hợp |
| “Remove(Object) luôn xóa đầu” | Đó là remove() không đối số; dạng có đối số tìm giá trị |
| “PriorityQueue<Integer>.remove(3) là chỉ số 3” | PriorityQueue không có remove theo chỉ số |
| “Một lần equals tức là toàn bộ phép xóa O(1)” | Còn bước sửa heap và các công việc không được bộ đếm đó đo |
| “Contains trước giúp remove tìm nhanh hơn” | Không có vị trí tìm được truyền qua hai lời gọi |
| “Dãy toArray đã sắp nên tìm nhị phân được ngay” | Dãy không được cam kết theo thứ tự ưu tiên đầy đủ |
| “Null bị cấm nên contains(null) cũng phải ném lỗi” | Chính sách lưu và hành vi tham số tìm kiếm khác nhau |
| “Thêm HashSet là xóa trong heap sẽ O(1)” | Có chỉ mục hiện diện không tự có chỉ mục vị trí của heap |
| “Tập khóa đủ cho mọi trường hợp có bản trùng” | Phải duy trì số lần hoặc mô hình duy nhất phù hợp |
| “Contains đúng nghĩa là heap chắc chắn được cập nhật sau sửa priority” | Sự hiện diện và cấu trúc ưu tiên là hai thuộc tính riêng |

Các câu hỏi nhanh khi xem lại mã là: chữ ký nào được gọi, dùng equals hay Comparator, xóa một lần hay mọi lần, và có tìm lặp lại không cần thiết không?

## 18. Thực hành có lời giải

### Bài 1: cùng ưu tiên nhưng khác giá trị

Hàng đợi có Task("A", 5). Comparator chỉ xét priority. Contains(Task("B", 5)) có true vì hai priority cùng bằng 5 không?

**Lời giải:** Không theo record Task của bài. Hai id khác nhau nên equals khác, dù Comparator trả 0. Contains không dùng nhóm ưu tiên làm định nghĩa của cùng phần tử.

### Bài 2: giá trị dò mới

Hàng đợi có một Task("A", 5). Bạn tạo một đối tượng mới với cùng hai thành phần. Có nhất thiết contains trả false do khác tham chiếu không?

**Lời giải:** Không. Record có equals theo các thành phần, nên giá trị dò mới vẫn bằng giá trị đang lưu và có thể được tìm thấy.

### Bài 3: bản trùng

Một Task bằng x có ba lần xuất hiện. Remove(x) thành công một lần. Contains(x) có bắt buộc false không?

**Lời giải:** Không. Vẫn còn hai lần xuất hiện. Remove(Object) không phải thao tác xóa hết.

### Bài 4: lấy đầu và xóa chỉ định

Hàng đợi có ưu tiên 1, 2, 9. Remove(Object) xóa công việc priority 9. Có bắt buộc đầu priority 1 cũng bị lấy ra không?

**Lời giải:** Không. Dạng có đối số tìm đúng giá trị cần loại. Poll hoặc remove không đối số mới lấy đầu theo ưu tiên.

### Bài 5: số nguyên và chỉ số

PriorityQueue<Integer> chứa 1, 2, 3, 4. Lời gọi remove(3) có nghĩa gì?

**Lời giải:** Xóa một giá trị Integer 3 nếu có và trả boolean. PriorityQueue không cung cấp xóa ở chỉ số 3.

### Bài 6: phần tử vắng

Một PriorityQueue có 10.000 thành viên và giá trị dò không tồn tại. Có thể coi contains chỉ cần khoảng log2(10.000) phép kiểm tra vì đây là heap không?

**Lời giải:** Không. Trong cách triển khai chuẩn được mô tả, contains tìm tuyến tính; trường hợp vắng có thể phải kiểm tra toàn bộ các thành viên.

### Bài 7: bộ đếm equals

Remove một giá trị ở đầu chỉ đếm một equals. Tại sao không được kết luận remove(Object) là O(1)?

**Lời giải:** Bộ đếm chỉ đo equals ở bước tìm. Sau khi xóa vẫn có thể cần các so sánh và di chuyển để sửa heap. Trường hợp đầu cũng không đại diện cho mọi vị trí hoặc giá trị dò vắng.

### Bài 8: tìm hai lần

Mã gọi contains(x), nếu true thì remove(x). Nếu chỉ cần biết xóa được hay không, có cách diễn đạt trực tiếp hơn không?

**Lời giải:** Dùng boolean của chính remove(x). Không tìm thấy trả false; tìm thấy và xóa trả true. Cách này tránh một bước tìm trước không truyền lại vị trí cho remove.

### Bài 9: nhận diện theo id

Task là record gồm id và priority. Bạn chỉ biết id của công việc cần hủy rồi tự chọn một priority khác để tạo giá trị dò. Giá trị dò có chắc khớp không?

**Lời giải:** Không. Equals mặc định của record xét cả hai thành phần. Muốn thao tác theo id cần mô hình khóa, phép bằng nhau hoặc chỉ mục phù hợp với yêu cầu.

### Bài 10: chỉ mục phụ và bản trùng

Bạn thêm một HashSet khóa bên cạnh PriorityQueue. Một khóa xuất hiện hai lần trong hàng đợi. Sau khi poll một lần, xóa ngay khóa khỏi HashSet có đúng không?

**Lời giải:** Không nếu còn một lần xuất hiện khác. Cần quy tắc duy trì tính duy nhất hoặc số lần xuất hiện. Chỉ mục phụ phải phản ánh đúng mọi đường cập nhật.

### Bài 11: kiểu giá trị dò khác

PriorityQueue<Integer> chứa số 4. Contains("4") trong ví dụ có true vì chuỗi có cùng ký tự số không?

**Lời giải:** Không. Chuỗi "4" và Integer 4 không bằng nhau theo equals. Phép hỏi nhận Object không tự phân tích chuỗi thành số hay chèn chuỗi vào hàng đợi.

### Bài 12: tìm thấy sau khi sửa đối tượng

Một đối tượng đang lưu bị thay priority trực tiếp nhưng contains vẫn true. Điều đó có chứng minh peek đang chọn đúng theo priority mới không?

**Lời giải:** Không. Contains chỉ kiểm tra sự hiện diện theo equals. Việc heap có được tổ chức đúng theo các giá trị ưu tiên hiện tại là vấn đề khác.

## 19. Cách áp dụng vào mã thật

Dùng contains khi câu hỏi thật sự là sự hiện diện theo equals và chấp nhận chi phí quét. Dùng remove(Object) khi cần thử xóa một giá trị cụ thể, đọc boolean của nó và nhớ mỗi lần chỉ loại một phần tử bằng nhau.

Khi công việc cần lấy đầu ưu tiên, dùng poll hoặc remove không đối số thay vì tìm lại một đối tượng đã biết ở đầu. Khi truy vấn theo id lặp lại nhiều, đánh giá mô hình chỉ mục riêng thay vì giả định heap đã cung cấp việc đó.

Độ phức tạp phải đi cùng chữ ký chính xác: tìm một giá trị bất kỳ, biết vị trí để sửa heap và chỉ xem đầu là ba loại công việc khác nhau.
