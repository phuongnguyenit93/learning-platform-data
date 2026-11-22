# Ảnh hưởng của hàm băm và Comparator

## 1. Vì sao cùng một collection có thể nhanh, chậm hoặc cho kết quả bất ngờ?

Collection không tự biết hai đối tượng “giống nhau” theo nghiệp vụ hay đối tượng nào nên đứng trước. Nó phải gọi những quy tắc do kiểu dữ liệu hoặc chương trình cung cấp:

- `equals`: hai đối tượng có được xem là bằng nhau không?
- `hashCode`: đối tượng nên được đưa tới nhóm ứng viên nào trong bảng băm?
- `Comparator.compare` hoặc `Comparable.compareTo`: đối tượng nào đứng trước, đứng sau, hay cùng mức theo thứ tự?

Các quy tắc này ảnh hưởng đồng thời đến **tính đúng đắn** và **hiệu năng**. Một hàm băm trả cùng một số cho mọi khóa có thể vẫn đúng hợp đồng nhưng làm tra cứu chậm. Một comparator chỉ so điểm có thể sắp xếp danh sách đúng yêu cầu, nhưng khi dùng cho `TreeSet` lại khiến hai người khác nhau cùng điểm được xem là cùng phần tử.

Bài này dùng Java 17 để phân tích hai câu hỏi: collection gọi quy tắc nào, và mỗi lần gọi tốn bao nhiêu?

## 2. Nhìn đúng vai trò của từng quy tắc

| Cấu trúc/thao tác | Quy tắc quan trọng | Hệ quả |
| --- | --- | --- |
| `HashMap`, `HashSet` | `hashCode` để định vị; `equals` để phân biệt khóa/phần tử | Băm tốt giúp giảm số ứng viên cần xét |
| `LinkedHashMap`, `LinkedHashSet` | Cũng dùng băm và bằng nhau | Liên kết bổ sung phục vụ thứ tự duyệt |
| `TreeMap`, `TreeSet` | Comparator hoặc thứ tự tự nhiên | Kết quả so sánh bằng 0 quyết định cùng khóa/phần tử trong cây |
| `PriorityQueue` | Comparator hoặc thứ tự tự nhiên để duy trì heap | Quyết định phần tử được lấy trước; không loại trùng |
| `List.sort(comparator)` | Comparator | Quyết định thứ tự; danh sách vẫn giữ các phần tử cùng mức |

`HashMap` thông thường không nhận một `Comparator` để sắp xếp khóa. Ngược lại, cải thiện `hashCode` không làm `TreeMap.get` nhanh hơn vì đường tìm kiếm của cây dựa trên so sánh. Đừng chọn điểm tối ưu chỉ từ tên lớp; hãy xác định thao tác thực tế và quy tắc nó sử dụng.

## 3. Hàm băm: đúng hợp đồng trước, phân bố tốt sau

### 3.1. HashCode không phải mã định danh duy nhất

Một mã băm là số `int`. Nhiều đối tượng khác nhau có thể có cùng mã băm, gọi là va chạm (collision). Vì vậy:

~~~text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
a.hashCode() == b.hashCode()  không suy ra  a.equals(b) == true
~~~

Nếu thông tin dùng để so sánh bằng nhau không đổi, mã băm phải ổn định trong cùng một lần chạy chương trình. Java không yêu cầu mã băm phải giữ nguyên giữa hai lần chạy khác nhau.

Khi tự viết `equals`, phải viết `hashCode` nhất quán với cùng quan hệ bằng nhau. Không dùng số ngẫu nhiên hay thời gian hiện tại để làm mã băm mỗi lần gọi. Cũng không dùng mã băm để quyết định duy nhất hai bản ghi có trùng nghiệp vụ hay không. [Hợp đồng Object.hashCode và Object.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html)

### 3.2. Hai loại lỗi khác nhau

**Lỗi hợp đồng:** hai khóa bằng nhau nhưng có mã băm khác nhau. Collection có thể tìm ở vị trí không chứa khóa đã lưu, nên `contains`, `get`, `remove` không còn làm việc như mong đợi. Đây là lỗi dữ liệu và tính đúng đắn.

**Phân bố kém:** các khóa khác nhau đều có cùng mã băm. Collection vẫn có thể phân biệt bằng `equals`, nhưng phải xét nhiều ứng viên hơn. Đây chủ yếu là vấn đề hiệu năng khi hợp đồng còn đúng.

Ví dụ, một lớp định nghĩa bằng nhau theo `id` có thể trả `id % 2` từ `hashCode`. Hàm này nhất quán với bằng nhau nhưng chỉ tạo hai mã băm, nên hầu hết lợi ích phân bố biến mất khi dữ liệu lớn.

Hàm băm tốt cho collection cần giữ hợp đồng, tính đủ rẻ và phân bố phù hợp với dữ liệu thực tế. Việc thêm nhiều phép tính phức tạp chưa chắc làm chương trình nhanh hơn.

### 3.3. Chi phí của một lần tra cứu

Có thể hình dung:

~~~text
Chi phí tra cứu =
    chi phí tính mã băm
  + chi phí xác định ngăn
  + chi phí kiểm tra các ứng viên trong ngăn
~~~

Nếu gọi:

- H là chi phí tính mã băm;
- E là chi phí một lần `equals`;
- q là số ứng viên cần kiểm tra;

thì một mô hình gần đúng là H + O(q) + O(qE), cộng các chi phí cấu trúc liên quan. Đây là mô hình phân tích, không phải số lần gọi phương thức được API bảo đảm. Một triển khai có thể tránh gọi `equals` nhờ kiểm tra tham chiếu hoặc mã băm trước. [Quy định Map về tra cứu và equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

Khi mã băm phân bố tốt và các phép tính trên có chi phí hằng, các thao tác cơ bản của `HashMap` có chi phí O(1) kỳ vọng. Nếu khóa rất lớn, H hay E có thể tăng theo kích thước khóa; O(1) theo số mục n không có nghĩa thao tác miễn phí.

### 3.4. Va chạm không được giải quyết bằng cách tăng capacity vô hạn

Tăng dung lượng có thể giúp khi nhiều mã băm khác nhau đang rơi vào các ngăn đông. Nếu mọi khóa đều có cùng mã băm, tăng dung lượng không tạo ra sự phân biệt mới giữa chúng.

Java có cơ chế giảm tác động của va chạm trong một số tình huống, có thể tận dụng thứ tự tự nhiên của khóa để phá hòa. Điều đó không biến mọi hàm băm kém thành hàm tốt, cũng không phải bảo đảm chung rằng mọi tra cứu đều O(1) hoặc trường hợp xấu nhất luôn O(log n).

Thêm khóa còn có thể kích hoạt tăng bảng và phân phối lại các mục. Chi phí khấu hao của chuỗi lần thêm phải phân biệt với độ trễ của một lần thêm. Dung lượng quá lớn cũng làm tốn bộ nhớ và có thể làm duyệt bảng chậm hơn. [Tài liệu hiệu năng HashMap của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

## 4. Khóa thay đổi và chi phí tính băm

### 4.1. Không thay đổi thông tin định danh khi khóa đang nằm trong bảng

Giả sử lưu một đối tượng `Customer` vào `HashSet`, trong đó `equals` và `hashCode` dùng `customerId`. Sau đó đổi `customerId`.

Nút lưu trữ vẫn đang ở vị trí được chọn khi thêm, trong khi lần tra cứu sau tính mã băm từ dữ liệu mới. Kết quả tra cứu có thể không tìm thấy đối tượng dù vòng lặp vẫn nhìn thấy nó. Không nên dựa vào một biểu hiện cụ thể của lỗi này vì hợp đồng collection đã bị vi phạm.

Cách xử lý tốt hơn:

- Dùng khóa bất biến, chẳng hạn một mã `long` hoặc một kiểu chỉ chứa các thành phần định danh bất biến.
- Nếu cần thay đổi khóa, xóa bằng trạng thái khóa cũ trước khi đổi, rồi thêm lại.
- Nếu chỉ thay đổi thuộc tính không tham gia bằng nhau/băm, đánh giá riêng tác động tới các cấu trúc khác như cây hoặc heap.

Một collection không cho thêm/xóa vẫn có thể chứa đối tượng thay đổi được; lớp bọc không biến các phần tử bên trong thành bất biến. [Cảnh báo về phần tử thay đổi được trong Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

### 4.2. Ghi nhớ kết quả băm chỉ có ích khi dữ liệu ổn định

Nếu mỗi lần `hashCode` phải quét cả một danh sách dài, việc định vị bảng nhanh không loại bỏ chi phí quét đó. Có thể cân nhắc dùng khóa nhỏ hơn hoặc tính trước giá trị khi tạo đối tượng bất biến.

Không ghi nhớ mã băm của một đối tượng còn thay đổi mà thiếu cơ chế duy trì tính nhất quán. Một mã băm cũ kết hợp với `equals` dựa trên dữ liệu mới còn nguy hiểm hơn một hàm băm chậm.

`record` giúp biểu diễn dữ liệu với các thành phần cuối cùng (final), nhưng không tự làm bất biến sâu những đối tượng được tham chiếu. Một thành phần kiểu `List` vẫn cần được bảo vệ nếu nội dung danh sách tham gia định danh.

## 5. Comparator: thứ tự phải là một quy tắc nhất quán

### 5.1. Chỉ dấu của kết quả có ý nghĩa

`compare(a, b)` trả:

- Số âm nếu a đứng trước b.
- 0 nếu a và b cùng mức theo comparator.
- Số dương nếu a đứng sau b.

Không bắt buộc phải trả đúng -1, 0 hoặc 1. Khi kiểm tra kết quả, dùng `< 0`, `== 0`, `> 0`.

Một comparator hợp lệ cần bảo đảm các tính chất như:

- Đổi hai đối số phải đổi dấu kết quả.
- Tính bắc cầu: nếu a lớn hơn b và b lớn hơn c, thì a phải lớn hơn c.
- Nếu a và b so sánh bằng 0, chúng phải có cùng quan hệ dấu khi so với một đối tượng thứ ba.
- Cùng dữ liệu và cùng quy tắc phải cho kết quả ổn định.

Không so theo trạng thái thay đổi ngẫu nhiên hay số lần comparator đã được gọi. Một bộ đếm chỉ để quan sát có thể tăng sau mỗi lần gọi, nhưng nó không được làm thay đổi kết quả so sánh.

### 5.2. Dùng phép trừ có thể làm hỏng thứ tự

Đoạn minh họa sau sai với một số giá trị biên:

~~~java
java.util.Comparator<Integer> unsafe = (a, b) -> a - b;
~~~

Với a = `Integer.MIN_VALUE`, b = 1, phép trừ tràn số và cho kết quả dương, dù a nhỏ hơn b.

Dùng `Integer.compare(a, b)` hoặc `Comparator.comparingInt` cho trường số nguyên; với `long` dùng `Long.compare` hay `comparingLong`. Không ép hiệu hai số `long` về `int` để tạo kết quả so sánh.

Tương tự, đảo thứ tự bằng `reversed()` rõ ràng hơn tự phủ định một kết quả tùy ý: số đối của `Integer.MIN_VALUE` vẫn bị tràn. [Hợp đồng và các hàm kết hợp Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)

## 6. So sánh bằng 0 có ý nghĩa khác nhau tùy nơi dùng

### 6.1. TreeSet và TreeMap dùng thứ tự để nhận diện trùng

Nếu comparator chỉ so điểm, hai người khác id nhưng cùng điểm có `compare(a, b) == 0`.

Trong `TreeSet`, phần tử thêm sau không tạo thêm một phần tử riêng. Trong `TreeMap`, một lần `put` với khóa cùng mức sẽ cập nhật ánh xạ đã có thay vì tạo khóa riêng theo thứ tự cây.

Vì vậy, comparator cho cây cần nhất quán với `equals` nếu muốn tuân thủ hợp đồng chung của `Set`/`Map`. “So sánh bằng 0” không chỉ là cách hiển thị hai đối tượng cạnh nhau. [TreeSet và quan hệ bằng nhau](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html), [TreeMap và thứ tự khóa](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

Có thể thêm tiêu chí phụ bằng `thenComparing`. Tuy nhiên, đây không phải cách sửa tự động mọi mô hình: nếu `equals` chỉ theo id nhưng comparator so điểm trước, hai đối tượng cùng id khác điểm vẫn có thể so sánh khác 0. Cần chọn rõ mô hình định danh; đôi khi nên lưu theo id trong một map và tạo một danh sách sắp xếp riêng để trình bày.

### 6.2. BigDecimal là ví dụ sẵn có trong Java

`new BigDecimal("1.0")` và `new BigDecimal("1.00")`:

- So sánh thứ tự tự nhiên cho kết quả 0 vì cùng giá trị số.
- `equals` cho kết quả `false` vì khác scale.

Do đó, với thứ tự tự nhiên, một `TreeSet<BigDecimal>` có thể giữ một phần tử trong khi `HashSet<BigDecimal>` giữ hai. Đây là khác biệt được tài liệu hóa, cần quyết định theo nghiệp vụ trước khi đổi collection. [Tài liệu BigDecimal của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)

### 6.3. PriorityQueue không dùng compare bằng 0 để loại trùng

Hai công việc có cùng mức ưu tiên vẫn có thể cùng nằm trong `PriorityQueue`. Hàng đợi không bảo đảm lấy các phần tử hòa theo thứ tự thêm. Nếu cần ưu tiên trước rồi FIFO khi hòa, thêm số thứ tự tăng dần làm tiêu chí phụ và duy trì số này đúng trong toàn bộ thời gian sử dụng.

`contains(x)` và `remove(Object)` của hàng đợi tìm theo bằng nhau, không phải “mọi đối tượng có comparator trả 0”. Việc duyệt iterator cũng không bảo đảm theo thứ tự ưu tiên. [Tài liệu PriorityQueue của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)

### 6.4. Sort giữ phần tử và có quy tắc ổn định riêng

Sắp xếp một danh sách theo điểm không xóa những người cùng điểm. `List.sort` là phép sắp xếp ổn định: phần tử cùng mức giữ thứ tự tương đối ban đầu.

Sự ổn định đó không được suy rộng thành FIFO của `PriorityQueue`, cũng không thay đổi cách `TreeSet` xác định trùng. Một comparator có thể phù hợp để trình bày danh sách nhưng không phù hợp làm thứ tự định danh cho tập cây. [Tài liệu List.sort](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator))

## 7. Comparator đắt làm chi phí cấu trúc tăng theo

Nếu một lần so sánh có chi phí C, những cận quen thuộc cần được đọc lại:

| Công việc | Số phép so sánh thường dùng để phân tích | Khi một lần so sánh tốn O(C) |
| --- | --- | --- |
| Tra/thêm/xóa khóa trong cây cân bằng | O(log n) | Phần chi phí so sánh là O(C log n) |
| Điều chỉnh heap khi thêm/lấy đầu | O(log n) | Phần chi phí so sánh là O(C log n) |
| Sắp xếp bằng so sánh trong trường hợp tổng quát | O(n log n) | Phần chi phí so sánh là O(C n log n) |

Bảng mô tả phần chi phí so sánh; không loại bỏ các chi phí khác như cấp phát hay tăng mảng nền khi thêm vào heap. Với sắp xếp, đầu vào gần có thứ tự và thuật toán cụ thể có thể dùng ít phép so sánh hơn cận tổng quát.

Nếu comparator mỗi lần đều phân tích một chuỗi ngày, chuẩn hóa tên, truy cập cơ sở dữ liệu hoặc đọc tệp, C có thể chi phối toàn bộ công việc. Một comparator trông chỉ có một dòng vẫn có thể rất đắt.

Cách cải thiện thường gặp:

1. Tính một khóa sắp xếp ổn định cho mỗi đối tượng trước khi sắp xếp.
2. So sánh các khóa đã tính trong comparator.
3. Dùng tiêu chí phụ đúng nghĩa khi hòa.
4. Chỉ cập nhật hoặc tính lại khóa khi dữ liệu nguồn thay đổi.

Ví dụ, nếu cần sắp theo tháng từ một chuỗi ngày đã kiểm tra hợp lệ, phân tích n chuỗi một lần rồi so sánh tháng thường hợp lý hơn phân tích lại trong mọi lần `compare`. Phải giữ nguyên quy tắc nghiệp vụ: xử lý múi giờ, ngôn ngữ hoặc dấu tiếng Việt không thể thay thế tùy tiện chỉ để comparator nhanh hơn.

`comparingInt` và `thenComparingInt` diễn đạt phép so sánh khóa nguyên thủy rõ ràng và tránh nhu cầu đóng hộp khóa `int` của một thiết kế dùng khóa đối tượng. Tác động thực tế vẫn cần đo trên đường chạy cần tối ưu.

## 8. Dữ liệu và quy tắc so sánh phải ổn định khi đang lưu

Đưa một công việc vào `PriorityQueue` rồi đổi trường ưu tiên không tự khiến heap được sắp lại. Tương tự, đổi trường tham gia comparator của một khóa `TreeMap` hoặc phần tử `TreeSet` có thể làm vị trí hiện tại không còn phù hợp với thứ tự mới.

Cách cập nhật là lấy/xóa mục theo trạng thái cũ, thay đổi hoặc tạo đối tượng mới, rồi chèn lại; khi không bảo đảm thao tác này an toàn, nên xây lại cấu trúc từ nguồn dữ liệu chuẩn. Không sửa comparator dùng cho cây bằng cách thay một cấu hình bên ngoài trong lúc cây còn dữ liệu.

Với `null`, có hai lớp quy tắc độc lập:

- Comparator có thể được thiết kế bằng `nullsFirst`/`nullsLast`.
- Bản thân collection có thể cấm `null`.

Chẳng hạn, comparator xử lý được `null` không làm `PriorityQueue` chấp nhận phần tử `null`. Nếu dùng thứ tự tự nhiên, cũng phải bảo đảm kiểu phần tử có thể so sánh đúng với nhau.

## 9. Chương trình minh họa Java 17

Ví dụ tách rõ va chạm băm, quan hệ trùng trong cây, hòa ưu tiên và tràn số. Nó kiểm tra kết quả hành vi, không dùng vài phần tử để kết luận tốc độ.

Lưu thành `HashComparatorDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.PriorityQueue;
import java.util.Set;
import java.util.TreeSet;

public class HashComparatorDemo {
    record BadHashKey(int id) {
        @Override
        public int hashCode() {
            return 0; // Hop dong dung, phan bo rat kem.
        }
    }

    record Student(int id, int score) {
    }

    public static void main(String[] args) {
        Set<BadHashKey> keys = new HashSet<>();
        keys.add(new BadHashKey(1));
        keys.add(new BadHashKey(2));
        keys.add(new BadHashKey(3));

        System.out.println("colliding keys size = " + keys.size());
        System.out.println("contains id 2 = "
                + keys.contains(new BadHashKey(2)));

        List<Student> students = List.of(
                new Student(1, 90),
                new Student(2, 90),
                new Student(3, 80)
        );

        Comparator<Student> byScore =
                Comparator.comparingInt(Student::score).reversed();

        Set<Student> scoreOnly = new TreeSet<>(byScore);
        scoreOnly.addAll(students);
        System.out.println("score-only tree size = " + scoreOnly.size());

        Comparator<Student> byScoreThenId =
                byScore.thenComparingInt(Student::id);
        Set<Student> fullOrder = new TreeSet<>(byScoreThenId);
        fullOrder.addAll(students);

        List<Integer> orderedIds = new ArrayList<>();
        for (Student student : fullOrder) {
            orderedIds.add(student.id());
        }
        System.out.println("score-and-id tree size = " + fullOrder.size());
        System.out.println("ordered ids = " + orderedIds);

        PriorityQueue<Student> queue = new PriorityQueue<>(byScore);
        queue.addAll(students);
        System.out.println("priority queue size = " + queue.size());

        List<Integer> scores = new ArrayList<>();
        while (!queue.isEmpty()) {
            scores.add(queue.poll().score());
        }
        System.out.println("polled scores = " + scores);

        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");
        System.out.println("decimal equals = " + a.equals(b));
        System.out.println("decimal compare = " + a.compareTo(b));
        System.out.println("decimal hash set size = "
                + new HashSet<>(List.of(a, b)).size());
        System.out.println("decimal tree set size = "
                + new TreeSet<>(List.of(a, b)).size());

        Comparator<Integer> unsafe = (x, y) -> x - y;
        Comparator<Integer> safe = Integer::compare;
        System.out.println("unsafe sign = "
                + Integer.signum(unsafe.compare(Integer.MIN_VALUE, 1)));
        System.out.println("safe sign = "
                + Integer.signum(safe.compare(Integer.MIN_VALUE, 1)));
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 HashComparatorDemo.java
java HashComparatorDemo
~~~

Stdout chính xác:

~~~text
colliding keys size = 3
contains id 2 = true
score-only tree size = 2
score-and-id tree size = 3
ordered ids = [1, 2, 3]
priority queue size = 3
polled scores = [90, 90, 80]
decimal equals = false
decimal compare = 0
decimal hash set size = 2
decimal tree set size = 1
unsafe sign = 1
safe sign = -1
~~~

Giải thích:

- `BadHashKey` dùng `equals` do record sinh theo id, còn mã băm luôn 0. Ba id vẫn được giữ riêng; va chạm không đồng nghĩa bằng nhau.
- Cây chỉ so điểm xem hai sinh viên 90 điểm là cùng phần tử. Comparator theo điểm rồi id phù hợp với record này vì đã xét đủ cả hai thành phần.
- Hàng đợi giữ đủ ba sinh viên. Chương trình chỉ in điểm khi lấy ra, không giả định sinh viên nào trong hai người cùng điểm được lấy trước.
- BigDecimal cho thấy khác biệt giữa bằng nhau và cùng giá trị theo thứ tự.
- Phép trừ trả dấu sai tại giá trị biên; `Integer.compare` xử lý đúng.

## 10. Kiểm tra và tối ưu có căn cứ

Trước khi tối ưu, kiểm tra hợp đồng trên các trường hợp có ý nghĩa:

- Hai đối tượng bằng nhau phải có cùng mã băm; va chạm giữa đối tượng khác nhau vẫn được phép.
- Comparator phải xử lý đúng giá trị nhỏ nhất/lớn nhất, đối tượng cùng mức và chuỗi ba đối tượng để kiểm tra tính bắc cầu.
- Quan hệ bằng 0 có đúng mục đích của nơi sử dụng không: sắp danh sách, tập duy nhất hay hàng đợi?
- Dữ liệu tham gia định danh và thứ tự có thể thay đổi khi đang lưu không?
- Quy tắc với `null`, chữ hoa/thường, ngôn ngữ và dữ liệu thiếu đã được xác định chưa?

Khi đo hiệu năng, dùng phân bố dữ liệu gần thực tế, gồm khóa trùng, nhiều khóa va chạm và các đối tượng có chi phí so sánh lớn. Tách thời gian chuẩn bị khóa, xây collection và truy vấn nếu cần hiểu từng phần; khi đánh giá công việc hoàn chỉnh thì phải cộng đủ tất cả.

Có thể đếm số lần gọi `hashCode`, `equals` hoặc `compare` để hiểu đường đi, nhưng số đếm không phải thời gian. Ghi log trong từng lời gọi sẽ làm nhiễu phép đo. Cũng không biến số lần gọi của một phiên bản JDK thành hợp đồng API.

Hàm băm tốt giúp thu hẹp ứng viên; comparator tốt giúp định hướng tìm kiếm và duy trì thứ tự. Chất lượng của chúng được đánh giá trước hết bằng quan hệ đúng, sau đó bằng tổng chi phí trên dữ liệu thật.
