# Giá trị đặc biệt so với ngoại lệ khi rỗng hoặc đầy

## 1. Rỗng và đầy là trạng thái; mã gọi quyết định chúng có bất thường không

Một hàng đợi nhận công việc có thể chưa có gì để xử lý. Một bộ đệm có giới hạn có thể đã hết chỗ. Cả hai đều là những trạng thái có thể dự kiến trong hoạt động bình thường.

Nhưng ở một đoạn mã khác, chương trình có thể đã xác lập điều kiện “phải còn một phần tử để lấy”. Nếu điều kiện ấy sai, tiếp tục im lặng như không có chuyện gì lại che mất lỗi.

Java cung cấp hai cách biểu diễn tình trạng không thực hiện được thao tác với `Queue` và `Deque`:

- Trả một **giá trị báo hiệu**, thường là `null` khi không có phần tử hoặc `false` khi không thêm được vì dung lượng.
- Ném một **ngoại lệ**, chẳng hạn `NoSuchElementException` khi cần phần tử nhưng cấu trúc rỗng, hoặc `IllegalStateException` khi thêm vào cấu trúc đã đầy.

Hai cách này không tự thay đổi thực tế “hiện có phần tử hay không” hoặc “còn chỗ hay không”. Chúng thay đổi cách kết quả được chuyển tới mã gọi.

Bài học tập trung vào việc chọn và xử lý đúng tín hiệu ấy. Chúng ta sẽ kiểm chứng cả hai đầu Deque, phân biệt trạng thái đầy/rỗng với lỗi đầu vào, và xử lý các bẫy của null, số 0 và tự mở gói. Mọi ví dụ chạy được dùng API có trong Java 17.

Bạn cần biết biến, điều kiện, vòng lặp và lời gọi phương thức. Không cần biết cách mảng hay danh sách liên kết được tổ chức bên trong để hiểu các hợp đồng này.

## 2. Hai cách biểu diễn kết quả khác nhau ở luồng xử lý

Xét một hàng đợi không chứa phần tử null và đang rỗng.

Với `poll()`:

~~~text
gọi poll
   ↓
nhận null như một giá trị trả về bình thường
   ↓
mã gọi kiểm tra và chọn nhánh xử lý
~~~

Với `remove()`:

~~~text
gọi remove
   ↓
ném NoSuchElementException
   ↓
luồng thực hiện thông thường rời lời gọi;
ngoại lệ được xử lý ở một nơi bắt thích hợp hoặc tiếp tục truyền ra
~~~

Không có phần tử nào được trả về bình thường ở lời gọi remove trên cấu trúc rỗng. Ngoại lệ không phải một giá trị mà bạn so sánh bằng `== null`.

Ngược lại, null do poll trả về không tự kích hoạt một khối catch. Nếu mã sau đó tự mở gói null thành kiểu nguyên thủy và gây lỗi, đó là một sự kiện khác cần xác định đúng vị trí.

Một giá trị báo hiệu đòi hỏi mã gọi phải kiểm tra nó. Một ngoại lệ đòi hỏi hợp đồng của đoạn mã xác định nơi xử lý hoặc cho phép nó truyền ra. Không cách nào tự cung cấp chính sách nghiệp vụ như “thử lại”, “bỏ công việc” hay “dừng một giai đoạn”.

## 3. Bản đồ cơ bản của Queue

`Queue<E>` mô tả một cấu trúc chứa phần tử để lấy theo chính sách của lớp triển khai. Đầu hàng đợi là phần tử sẽ được lấy ra tiếp theo; không mặc định mọi Queue đều dùng cùng một quy tắc thứ tự.

Ba công việc có hai dạng:

| Công việc | Dạng báo bằng ngoại lệ | Dạng báo bằng giá trị |
| --- | --- | --- |
| Thêm phần tử | `add(e)` | `offer(e)` |
| Lấy ra và xóa đầu | `remove()` | `poll()` |
| Chỉ xem đầu | `element()` | `peek()` |

Với dữ liệu hợp lệ:

- Khi thêm được, add và offer đều trả true.
- Khi đầy do giới hạn dung lượng, add ném IllegalStateException, offer trả false.
- Khi rỗng, remove và element ném NoSuchElementException.
- Khi rỗng, poll và peek trả null.

Đừng bỏ qua phần “lấy ra” so với “chỉ xem”. Poll thành công làm mất một thành viên khỏi hàng đợi; peek thành công giữ nguyên nó. Thay tên phương thức để đổi cách báo rỗng không được làm bạn vô tình đổi luôn tác dụng lên dữ liệu. [Java 17: Queue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html).

Các dạng remove ở bảng đều **không có đối số**. Phương thức remove(Object) tìm theo giá trị là một chữ ký khác, không phải dạng báo rỗng của cặp remove/poll.

## 4. Deque áp dụng cùng nguyên tắc ở cả hai đầu

`Deque` mở rộng Queue để thao tác ở đầu trước và đầu sau. Hậu tố `First`/`Last` chọn phía; nhóm tên phương thức chọn công việc và cách báo không thực hiện được.

| Phía | Công việc | Dạng ngoại lệ | Dạng giá trị báo hiệu |
| --- | --- | --- | --- |
| Đầu | Thêm | `addFirst(e)` | `offerFirst(e)` |
| Cuối | Thêm | `addLast(e)` | `offerLast(e)` |
| Đầu | Lấy ra | `removeFirst()` | `pollFirst()` |
| Cuối | Lấy ra | `removeLast()` | `pollLast()` |
| Đầu | Chỉ xem | `getFirst()` | `peekFirst()` |
| Cuối | Chỉ xem | `getLast()` | `peekLast()` |

Các phương thức offer trả boolean. AddFirst và addLast trả void: việc hoàn thành bình thường biểu thị thao tác đã thêm xong, còn khi đầy chúng báo lỗi bằng ngoại lệ. Đừng gán kết quả của addLast vào một biến boolean chỉ vì Queue.add có kiểu trả về boolean.

Với deque rỗng, các phương thức poll/peek ở cả hai đầu trả null. Các phương thức remove/get ở cả hai đầu ném NoSuchElementException. Với deque bị giới hạn và đã đầy, offer ở phía nào cũng có thể trả false; add ở phía đó ném IllegalStateException.

Đầu và cuối không có hai kho dung lượng riêng. Một deque có sức chứa hai thành viên không thể chứa thêm ở đầu chỉ vì các thành viên cũ được thêm ở cuối. [Java 17: Deque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html).

## 5. Khi rỗng là một kết quả bình thường

Giả sử mỗi lượt chương trình lấy những công việc hiện có rồi kết thúc. Đến cuối lượt, việc không có phần tử tiếp theo là điều được chờ đợi.

Với hợp đồng không lưu null, poll phù hợp để diễn đạt:

~~~java
String task = pending.pollFirst();
if (task == null) {
    System.out.println("Chưa có công việc.");
} else {
    System.out.println("Đã lấy: " + task);
}
~~~

Đoạn minh họa giả sử `pending` là một Deque<String> không chứa null. Nó đọc đúng giá trị trả về của lần lấy vừa thực hiện.

Nhánh không có công việc không đồng nghĩa cấu trúc dữ liệu bị lỗi. Nó có thể chỉ có nghĩa lượt này chưa nhận gì. Không cần tự biến mọi kết quả rỗng thành một ngoại lệ của ứng dụng nếu bên gọi được phép gặp rỗng.

Tương tự, peek thích hợp khi bạn chỉ muốn hỏi có gì ở đầu mà không lấy ra. Nhưng peek không làm tiến độ xử lý thay đổi. Nếu cần xử lý hết, việc chỉ xem đi xem lại sẽ không làm cấu trúc cạn.

Điểm quan trọng là **bình thường hay bất thường do hợp đồng sử dụng quyết định**, không do bản thân từ “rỗng”. Cùng một ArrayDeque có thể được dùng ở hai nơi với hai kỳ vọng khác nhau.

## 6. Khi rỗng chứng tỏ một giả định bị phá vỡ

Một thuật toán có thể yêu cầu lấy đúng một phần tử mà bước trước đã xác lập phải tồn tại. Khi không có mã khác xen vào thay đổi cấu trúc, việc rỗng ở thời điểm ấy có thể cho thấy lỗi trong luồng chương trình.

Dùng removeFirst thể hiện giả định cần có phần tử:

~~~java
String required = pending.removeFirst();
System.out.println(required);
~~~

Đoạn minh họa giả sử pending thuộc một phần thuật toán có hợp đồng phải không rỗng. Nếu không đáp ứng điều kiện đó, NoSuchElementException xuất hiện ngay ở lời gọi lấy.

Nếu thay bằng pollFirst rồi bỏ qua null, lỗi có thể bị đẩy xa hơn: một phép dùng chuỗi mới gây NullPointerException, hoặc một nhánh sau đó lặng lẽ bỏ qua bước đáng lẽ phải chạy. Tín hiệu gần nguyên nhân thường giúp xem lại giả định dễ hơn.

Điều này không phải chỉ dẫn “luôn dùng ngoại lệ để kiểm tra rỗng”. Nếu việc hết công việc được phép xảy ra thường xuyên, dùng poll và nhánh phù hợp thường thể hiện ý định trực tiếp hơn. Ngược lại, nếu rỗng là vi phạm giả định, một lỗi rõ không nên bị đổi thành kết quả bình thường chỉ để tránh nhìn thấy ngoại lệ.

NoSuchElementException là một ngoại lệ thời gian chạy dùng khi phần tử được yêu cầu không tồn tại. Bạn cần đọc đúng phương thức phát sinh nó thay vì coi nó là một tín hiệu chung rằng “mọi thứ đều không thành công”. [Java 17: NoSuchElementException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NoSuchElementException.html).

## 7. Khi đầy là một nhánh cần xử lý, không phải chèn ngầm

Một bộ đệm có sức chứa cố định thường phải có chính sách khi không còn chỗ. Ví dụ, trả kết quả chưa nhận cho phía gửi hoặc thử lại trong một giai đoạn khác.

Với một `LinkedBlockingDeque` được tạo sức chứa 2 và chứa `[older, newer]`:

~~~text
offerFirst(urgent) → false
offerLast(later)   → false
~~~

Hai phần tử mới không được chèn. Không có chuyện urgent âm thầm đẩy newer ra để chiếm chỗ. Cũng không có một lệnh chèn bị từ chối đang chờ sẵn bên trong.

Nếu cùng trạng thái đầy mà gọi addFirst hoặc addLast, chúng ném IllegalStateException. Ví dụ trong bài đối chiếu nội dung trước/sau để xác nhận hai kiểu báo đều giữ nguyên các thành viên đang có trong những thao tác riêng đó.

Sau khi pollLast lấy newer ra, một lần offerFirst mới có thể nhận urgent:

~~~text
[older]
   ↓ offerFirst(urgent) thành công
[urgent, older]
~~~

Giá trị true thuộc về lần thử mới sau khi đã có chỗ. False trước đó không tự đổi thành true khi trạng thái về sau thay đổi.

LinkedBlockingDeque có thể được tạo với giới hạn dung lượng cụ thể. Bài chọn sức chứa 2 để tạo trạng thái đầy dễ quan sát và chỉ dùng một luồng. [Java 17: LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html).

## 8. Đừng bỏ qua false rồi xem như công việc đã được nhận

Khi chọn dạng trả giá trị, bạn đồng thời nhận trách nhiệm xử lý kết quả. Gọi offerLast rồi bỏ qua boolean làm mất thông tin quan trọng ở đúng điểm có thể từ chối phần tử.

Một phương thức minh họa có hợp đồng đơn giản:

~~~java
static boolean tryAccept(Deque<String> buffer, String task) {
    return buffer.offerLast(task);
}
~~~

Đây là phương thức để đặt trong lớp, giả sử task và buffer đáp ứng chính sách dữ liệu. Bên gọi vẫn cần dùng kết quả trả về; thêm một lớp bọc mà tiếp tục bỏ qua boolean không giải quyết vấn đề.

Nếu trả false, có thể báo chưa nhận hoặc giữ công việc ở phía gọi để áp dụng chính sách đã định. Không khẳng định đã xếp hàng thành công chỉ vì chương trình chưa đi qua catch.

Nếu trả true, thao tác thêm đã được chấp nhận. Nó chưa chứng minh phần tử được xử lý xong. Hàng đợi chỉ giữ dữ liệu; logic xử lý nằm ở bước khác.

Cũng không thử lại vô hạn bằng một vòng offer liên tục không có chính sách. Việc dùng giá trị báo hiệu không tự mang theo cơ chế giảm tải, chờ chỗ trống hay giới hạn số lần thử.

## 9. Lỗi đầu vào khác với tình trạng không có chỗ

Dạng offer không phải một phiên bản “không bao giờ ném lỗi”. Nếu lớp cấm null, offerFirst(null) hoặc offerLast(null) có thể ném NullPointerException dù cấu trúc đang rỗng và còn nhiều chỗ.

Trong ArrayDeque, null không phải phần tử hợp lệ. Lỗi đó nói về **đầu vào**, không phải số thành viên đã đạt giới hạn.

Tương tự, một Queue yêu cầu các phần tử so sánh được có thể báo lỗi khi nhận kiểu không phù hợp. Đổi từ add sang offer không sửa được quy tắc chấp nhận phần tử của lớp triển khai.

Vì vậy, hãy phân loại kết quả theo đúng nguyên nhân:

| Tín hiệu | Câu hỏi đầu tiên nên kiểm tra |
| --- | --- |
| offer trả false | Lời gọi không nhận phần tử; trạng thái dung lượng và chính sách chèn là gì? |
| NoSuchElementException từ remove/get | Đoạn mã có yêu cầu phần tử khi cấu trúc rỗng không? |
| IllegalStateException từ add ở trạng thái đầy | Giới hạn dung lượng có bị đạt tới không? |
| NullPointerException khi thêm null | Lớp có cấm phần tử null không? |
| NullPointerException sau poll | Mã gọi có dùng hoặc tự mở gói kết quả null không? |

Tên một ngoại lệ riêng lẻ chưa mô tả toàn bộ nguyên nhân. Vị trí phát sinh và hợp đồng của lời gọi mới cho biết nó thuộc nhóm nào.

Đừng bắt một ngoại lệ quá rộng rồi chuyển mọi nguyên nhân thành “đầy” hoặc “rỗng”. Điều đó làm lỗi dữ liệu trông giống trạng thái bình thường, và khiến việc sửa đúng nguyên nhân khó hơn.

## 10. Chương trình đầy đủ dùng Java 17

Lưu thành `QueueFailureSignalsDemo.java`. Chương trình kiểm chứng:

- Bốn phép poll/peek và bốn phép remove/get trên deque rỗng.
- Hai phía chèn trên deque bị giới hạn và đã đầy.
- Việc tạo chỗ rồi thử lại.
- Số 0 hợp lệ so với kết quả null.
- Lỗi tự mở gói và lỗi thêm null.
- Một lớp cho phép null để kiểm tra giới hạn của các kết luận.
- Một giả định phải có phần tử bị vi phạm.

Các ngoại lệ dự kiến được bắt sát từng lời gọi để những nhóm ví dụ sau vẫn chạy. Mã không dùng một khối bắt lỗi chung cho toàn bộ chương trình.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedList;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.concurrent.LinkedBlockingDeque;

public class QueueFailureSignalsDemo {
    // Điều kiện: không lưu null và không có mã khác sửa deque trong lượt này.
    static List<String> consumeAvailable(Deque<String> pending) {
        List<String> consumed = new ArrayList<>();
        String task;
        while ((task = pending.pollFirst()) != null) {
            consumed.add(task);
        }
        return consumed;
    }

    public static void main(String[] args) {
        Deque<String> empty = new ArrayDeque<>();
        System.out.println("empty pollFirst=" + empty.pollFirst());
        System.out.println("empty pollLast=" + empty.pollLast());
        System.out.println("empty peekFirst=" + empty.peekFirst());
        System.out.println("empty peekLast=" + empty.peekLast());
        try {
            empty.removeFirst();
        } catch (NoSuchElementException exception) {
            System.out.println("empty removeFirst=" + exception.getClass().getSimpleName());
        }
        try {
            empty.removeLast();
        } catch (NoSuchElementException exception) {
            System.out.println("empty removeLast=" + exception.getClass().getSimpleName());
        }
        try {
            empty.getFirst();
        } catch (NoSuchElementException exception) {
            System.out.println("empty getFirst=" + exception.getClass().getSimpleName());
        }
        try {
            empty.getLast();
        } catch (NoSuchElementException exception) {
            System.out.println("empty getLast=" + exception.getClass().getSimpleName());
        }
        System.out.println("empty unchanged=" + empty.isEmpty());

        Deque<String> limited = new LinkedBlockingDeque<>(2);
        limited.addLast("older");
        limited.addLast("newer");
        List<String> before = new ArrayList<>(limited);
        System.out.println("full initial=" + limited);
        System.out.println("full offerFirst=" + limited.offerFirst("urgent"));
        System.out.println("full offerLast=" + limited.offerLast("later"));
        System.out.println("after false unchanged=" + before.equals(new ArrayList<>(limited)));
        try {
            limited.addFirst("urgent");
        } catch (IllegalStateException exception) {
            System.out.println("full addFirst=" + exception.getClass().getSimpleName());
        }
        try {
            limited.addLast("later");
        } catch (IllegalStateException exception) {
            System.out.println("full addLast=" + exception.getClass().getSimpleName());
        }
        System.out.println("after exceptions unchanged="
                + before.equals(new ArrayList<>(limited)));
        System.out.println("full peekFirst/peekLast="
                + limited.peekFirst() + "/" + limited.peekLast());
        System.out.println("full size after peeks=" + limited.size());
        System.out.println("make room pollLast=" + limited.pollLast());
        System.out.println("retry offerFirst=" + limited.offerFirst("urgent"));
        System.out.println("after retry=" + limited);
        System.out.println("consumed=" + consumeAvailable(limited));
        System.out.println("empty after consume=" + limited.isEmpty());

        Deque<Integer> numbers = new ArrayDeque<>();
        numbers.offerLast(0);
        Integer zero = numbers.pollFirst();
        System.out.println("zero value=" + zero);
        System.out.println("zero is present=" + (zero != null));
        Integer absent = numbers.pollFirst();
        System.out.println("absent value=" + absent);
        try {
            int unsafe = numbers.pollFirst();
            System.out.println("unboxed value=" + unsafe);
        } catch (NullPointerException exception) {
            System.out.println("unboxing empty result=" + exception.getClass().getSimpleName());
        }
        try {
            numbers.offerLast(null);
        } catch (NullPointerException exception) {
            System.out.println("invalid null input=" + exception.getClass().getSimpleName());
        }
        System.out.println("numbers size=" + numbers.size());

        Deque<String> nullable = new LinkedList<>();
        nullable.addLast(null);
        nullable.addLast("tail");
        System.out.println("nullable getFirst=" + nullable.getFirst());
        System.out.println("nullable size after get=" + nullable.size());
        System.out.println("nullable removeFirst=" + nullable.removeFirst());
        System.out.println("nullable size after remove=" + nullable.size());
        System.out.println("nullable remaining=" + nullable);

        Deque<String> required = new ArrayDeque<>();
        required.addLast("ready");
        System.out.println("required first removal=" + required.removeFirst());
        try {
            required.removeFirst();
        } catch (NoSuchElementException exception) {
            System.out.println("broken nonempty assumption="
                    + exception.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 QueueFailureSignalsDemo.java
java QueueFailureSignalsDemo
~~~

Dùng JDK 17 trở lên. `--release 17` kiểm tra mã và API theo Java 17. Tên tệp khớp với lớp public.

Kết quả chuẩn:

~~~text
empty pollFirst=null
empty pollLast=null
empty peekFirst=null
empty peekLast=null
empty removeFirst=NoSuchElementException
empty removeLast=NoSuchElementException
empty getFirst=NoSuchElementException
empty getLast=NoSuchElementException
empty unchanged=true
full initial=[older, newer]
full offerFirst=false
full offerLast=false
after false unchanged=true
full addFirst=IllegalStateException
full addLast=IllegalStateException
after exceptions unchanged=true
full peekFirst/peekLast=older/newer
full size after peeks=2
make room pollLast=newer
retry offerFirst=true
after retry=[urgent, older]
consumed=[urgent, older]
empty after consume=true
zero value=0
zero is present=true
absent value=null
unboxing empty result=NullPointerException
invalid null input=NullPointerException
numbers size=0
nullable getFirst=null
nullable size after get=2
nullable removeFirst=null
nullable size after remove=1
nullable remaining=[tail]
required first removal=ready
broken nonempty assumption=NoSuchElementException
~~~

## 11. Đọc kết quả theo trạng thái trước và sau

### 11.1. Deque rỗng nhưng không bị hỏng

Bốn dòng `empty pollFirst`, `pollLast`, `peekFirst` và `peekLast` đều trả null. Chúng không tạo ra một phần tử mặc định.

Bốn dạng remove/get báo NoSuchElementException. Sau tất cả các lời gọi, `empty unchanged=true` xác nhận deque vẫn rỗng.

Sự khác nhau nằm ở cách chuyển thông tin “không có phần tử” tới mã gọi, không nằm ở việc một phía tự sửa cấu trúc còn phía kia làm nó hỏng.

### 11.2. Từ chối vì đầy không xóa thành viên cũ

Hai lần offer trả false và hai lần add ném IllegalStateException. Chương trình chụp trình tự thành viên trước đó bằng ArrayList rồi so sánh sau từng nhóm:

~~~text
after false unchanged=true
after exceptions unchanged=true
~~~

Đây là phép kiểm tra nội dung và thứ tự trong ví dụ một luồng, không chỉ kiểm tra size. Cùng kích thước chưa đủ để chứng minh không đổi thành viên, nên ảnh chụp giúp đối chiếu rõ hơn.

Kết luận này nói về các lời gọi riêng đã kiểm chứng. Nó không có nghĩa một chuỗi nhiều thao tác khác nhau là một giao dịch sẽ được hoàn tác nếu bước cuối ném ngoại lệ.

### 11.3. Xem không giải phóng dung lượng

`full peekFirst/peekLast=older/newer` và `full size after peeks=2` cho thấy việc xem hai đầu không lấy gì ra.

Phải có thao tác thay đổi như pollLast mới tạo chỗ trong ví dụ. Sau khi lấy newer, offerFirst nhận urgent và thứ tự là `[urgent, older]`.

### 11.4. Hết công việc là điểm dừng hợp lệ

`consumed=[urgent, older]` cho biết hàm consumeAvailable đã lấy hai thành viên. Lần pollFirst tiếp theo trả null, vòng lặp kết thúc và `empty after consume=true`.

Hàm này có tiền điều kiện không chứa null và không có mã khác sửa deque trong lượt đang minh họa. Kết quả không được tự mở rộng thành bảo đảm cho mọi cấu trúc hoặc mọi cách dùng nhiều luồng.

## 12. Số 0 không phải dấu hiệu chuẩn của hàng đợi rỗng

`Queue<Integer>` hoặc `Deque<Integer>` lưu các đối tượng Integer. Một phần tử có giá trị 0 vẫn là phần tử thật.

Trong chương trình:

~~~text
zero value=0
zero is present=true
absent value=null
~~~

Lần pollFirst đầu lấy ra số 0. Lần sau mới không có phần tử và trả null. Nếu mã tự chọn điều kiện `value == 0` để biểu thị rỗng, nó đã làm mất khả năng biểu diễn một dữ liệu hợp lệ.

Không dùng một chuỗi rỗng, số âm hoặc một giá trị tùy tiện khác thay null nếu miền dữ liệu không dành riêng giá trị ấy bằng một hợp đồng tường minh. API đã định nghĩa kết quả báo rỗng; tự đổi ý nghĩa mà không kiểm soát miền đầu vào tạo thêm sự mơ hồ.

Cách kiểm tra an toàn trước khi mở gói trong ví dụ số:

~~~java
Integer next = numbers.pollFirst();
if (next != null) {
    int value = next;
    System.out.println(value);
}
~~~

Đoạn này giả sử numbers là một Deque<Integer> cấm null. Kiểm tra null diễn ra trước chuyển sang int.

## 13. Tự mở gói có thể làm bạn mất tín hiệu bình thường

Dòng:

~~~java
int value = numbers.pollFirst();
~~~

trông như một phép lấy số. Thực tế pollFirst trả Integer, rồi Java chuyển đối tượng đó thành int bằng quá trình tự mở gói (unboxing).

Nếu kết quả là null, quá trình chuyển gây NullPointerException. Trạng thái rỗng ban đầu vốn được API biểu diễn bằng một giá trị bình thường đã trở thành lỗi trong mã gọi.

Chương trình in `unboxing empty result=NullPointerException` để làm rõ đường đi này. Nó cũng in một NullPointerException khác khi cố thêm null vào ArrayDeque. Hai lỗi cùng tên nhưng xuất hiện vì hai nguyên nhân và ở hai thời điểm khác nhau.

Quy tắc ngôn ngữ xác định rằng mở gói tham chiếu null gây NullPointerException. Vì vậy, không thể tránh lỗi bằng cách chỉ đổi kiểu phần tử tổng quát sang Integer mà vẫn gán kết quả ngay vào int. [Java Language Specification 17: unboxing](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.8).

Đối với các phần tử kiểu tham chiếu khác, lời gọi phương thức ngay trên kết quả poll cũng gặp vấn đề tương tự nếu không kiểm tra null. Cần quyết định cách xử lý vắng phần tử trước khi dùng dữ liệu như chắc chắn tồn tại.

## 14. Phương thức dùng ngoại lệ không luôn bảo đảm giá trị trả về khác null

Trong đa số ví dụ của bài, ArrayDeque và LinkedBlockingDeque cấm null. Điều đó giúp null báo rỗng không bị lẫn với dữ liệu.

Nhưng LinkedList cho phép null. Chương trình cố ý tạo deque:

~~~text
[null, tail]
~~~

và nhận:

~~~text
nullable getFirst=null
nullable size after get=2
nullable removeFirst=null
nullable size after remove=1
nullable remaining=[tail]
~~~

GetFirst hoàn thành bình thường và trả một thành viên null, vì cấu trúc **không rỗng**. RemoveFirst cũng hoàn thành bình thường, lấy chính thành viên null đó ra.

Như vậy, “ném ngoại lệ khi rỗng” khác với “mọi lần hoàn thành bình thường đều trả giá trị khác null” nếu lớp triển khai cho phép null làm dữ liệu. Ngoại lệ được gắn với việc không có phần tử, không gắn với mọi kết quả null có thể tồn tại.

Với poll/peek trên một lớp cho phép null, null có thể là giá trị phần tử hoặc là tín hiệu không có phần tử. Chỉ bọc kết quả trong một kiểu khác hoặc đổi tên biến không tự khôi phục thông tin đã nhập nhằng.

Tài liệu Queue/Deque khuyến cáo tránh dùng null làm phần tử. Ví dụ LinkedList ở đây là cách kiểm chứng giới hạn của kết luận, không phải lựa chọn tốt để biểu diễn công việc trong hàng đợi. [Java 17: LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).

## 15. Chọn phạm vi xử lý ngoại lệ sát với hợp đồng

Nếu bạn chọn một phương thức có thể ném ngoại lệ khi rỗng, hãy biết chính xác đoạn nào được phép diễn giải là “không có phần tử”.

Một khối try quá rộng có thể bao cả bước lấy phần tử, bước phân tích dữ liệu và bước xử lý. Nếu phần xử lý cũng ném NoSuchElementException vì một nguồn dữ liệu khác, bắt nó rồi kết luận “deque rỗng” là diễn giải sai nguyên nhân.

Trong mã minh họa, mỗi khối try tập trung vào một lời gọi đang được kiểm chứng. Điều đó giúp liên hệ tín hiệu với trạng thái. Trong mã ứng dụng, bạn có thể cho phép lỗi truyền ra nếu nó là vi phạm giả định cần được sửa thay vì bắt để tiếp tục.

Nếu hết dữ liệu là tình huống dự kiến, poll và một nhánh rõ thường làm phạm vi kết quả vắng mặt dễ đọc hơn. Hàm sau là đoạn trích từ chương trình đầy đủ:

~~~java
static List<String> consumeAvailable(Deque<String> pending) {
    List<String> consumed = new ArrayList<>();
    String task;
    while ((task = pending.pollFirst()) != null) {
        consumed.add(task);
    }
    return consumed;
}
~~~

Hàm trả danh sách phần tử đã lấy ra và làm cạn deque đang được truyền vào trong ví dụ một luồng. Nó không phải phép xem hoặc tạo bản sao giữ nguyên dữ liệu nguồn.

Nếu xử lý phần tử xảy ra sau poll và bị lỗi, deque không tự trả phần tử về chỗ cũ. Việc khôi phục hay đánh dấu lỗi là một hợp đồng khác của ứng dụng, không được suy từ cách poll báo rỗng.

## 16. Không có giới hạn cố định thì đừng tự tạo trạng thái đầy giả

Phương thức offer có nhánh báo không nhận được không có nghĩa mọi lớp đều dễ xuất hiện trạng thái đầy theo cùng cách.

ArrayDeque có thể tăng dung lượng khi cần. Tham số của `new ArrayDeque<>(2)` không phải một giới hạn cứng hai thành viên. Bạn không thể dùng việc thêm phần tử thứ ba để chứng minh offer phải trả false.

LinkedBlockingDeque trong bài được tạo với sức chứa 2 nên tình huống đầy được xác định rõ. Không suy từ chữ “linked” hay “array” để đoán giới hạn; đọc hợp đồng hàm khởi tạo và lớp.

Không có giới hạn cố định theo API cũng không có nghĩa bộ nhớ máy là vô hạn. Các lỗi tài nguyên không phải một tín hiệu dung lượng phổ quát mà offer bắt buộc chuyển thành false. [Java 17: ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

Khi viết kiểm thử, trạng thái rỗng cần một cấu trúc không thành viên, còn trạng thái đầy cần một cách triển khai với giới hạn thực sự và phải lấp đủ số chỗ đó. Chọn dữ liệu nhỏ nhưng đúng điều kiện quan trọng hơn việc lặp nhiều lần trên một lớp không có giới hạn ấy.

## 17. Giá trị đặc biệt không phải một cơ chế chờ

Cả kiểu báo bằng giá trị lẫn kiểu báo bằng ngoại lệ đang học đều nói về thao tác tức thời theo các chữ ký cụ thể.

Tên LinkedBlockingDeque không khiến `offerFirst(e)` tự đợi đến khi có chỗ. `pollFirst()` không tự đợi một phần tử mới đến. Trong chương trình, mỗi lời gọi báo ngay trạng thái theo khả năng thêm/lấy mà không chờ điều kiện dung lượng hoặc dữ liệu thay đổi.

BlockingDeque có các phương thức bổ sung như put/take và các biến thể có thời hạn. Nếu yêu cầu là chờ hoặc chờ tối đa một khoảng thời gian, phải chọn đúng chữ ký và hiểu hợp đồng của nó. Không suy rằng việc chuyển từ add sang offer đã cung cấp một chính sách chờ. [Java 17: BlockingDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingDeque.html).

Cũng không coi “kiểm tra rồi làm” là một hành động nguyên tử:

~~~text
isEmpty cho false
   ↓
một tác nhân khác có thể lấy phần tử
   ↓
removeFirst vẫn có thể gặp rỗng
~~~

Tương tự, nhìn thấy một chỗ trống trước đó không bảo đảm một lần add sau vẫn có chỗ trong môi trường có thao tác xen vào.

Nếu việc chưa có phần tử là bình thường, hãy xử lý kết quả của chính lời gọi poll. Nếu cần chờ, chọn API chờ. Nếu cần bảo vệ cả một chuỗi thao tác, thiết kế cách phối hợp phù hợp. ArrayDeque tự nó không cung cấp việc chia sẻ và sửa dữ liệu an toàn giữa nhiều luồng.

Các ví dụ của bài chạy một luồng để kết quả trạng thái rõ ràng; chúng không phải phép thử cạnh tranh giữa các luồng.

## 18. Những nhầm lẫn cần phát hiện sớm

| Nhầm lẫn | Điều cần sửa |
| --- | --- |
| “Rỗng luôn là lỗi” | Xem hợp đồng: có thể là tình trạng bình thường của một lượt lấy công việc |
| “Không muốn lỗi thì cứ đổi mọi remove thành poll” | Có thể che giả định phải có phần tử và đẩy lỗi sang nơi khác |
| “Offer không ném ngoại lệ” | Đầu vào sai vẫn có thể báo lỗi |
| “Không có catch nghĩa là đã thêm thành công” | Phải đọc và xử lý boolean của offer |
| “False nghĩa là phần tử sẽ tự được thêm về sau” | Lần gọi đã không nhận phần tử; thử lại là một thao tác mới |
| “Peek tạo chỗ vì đã nhìn qua phần tử” | Peek/get chỉ đọc, không xóa |
| “Null mở gói thành số mặc định 0” | Mở gói null gây NullPointerException |
| “0 nghĩa là hàng đợi rỗng” | 0 có thể là một phần tử Integer hợp lệ |
| “Get/remove hoàn thành bình thường luôn trả khác null” | Một lớp cho phép null có thể trả chính thành viên null |
| “Đổi null thành chuỗi rỗng sẽ giải quyết mọi nhập nhằng” | Giá trị tự chọn cũng có thể thuộc miền dữ liệu nếu không có hợp đồng riêng |
| “AddFirst trả boolean giống Queue.add” | AddFirst/addLast trả void; offerFirst/offerLast mới trả boolean |
| “Deque có chỗ trống riêng ở mỗi đầu” | Giới hạn dung lượng áp dụng cho tổng số thành viên |
| “Trước đó kiểm tra không rỗng nên remove chắc chắn an toàn” | Cần xem có thay đổi xen vào hay không |
| “Một lệnh lỗi làm hoàn tác cả chuỗi trước đó” | Những thao tác đã hoàn thành không tự biến thành giao dịch |

Khi xem lỗi, giữ lại bốn thông tin: phương thức nào được gọi, trạng thái trước đó, tín hiệu thực nhận và trạng thái sau. Đừng chỉ ghi chung “thao tác thất bại”.

## 19. Thực hành có lời giải

### Bài 1: chọn tín hiệu cho lượt lấy hiện có

Một lượt xử lý được phép kết thúc khi chưa có công việc tiếp theo. PollFirst trả null trên deque cấm null. Có cần biến nó thành NoSuchElementException không?

**Lời giải:** Không nếu rỗng nằm trong hợp đồng bình thường của lượt này. Kiểm tra null và kết thúc hoặc chọn nhánh phù hợp. Ngoại lệ không cung cấp thêm dữ liệu trong trường hợp đã được dự kiến.

### Bài 2: giả định bắt buộc có phần tử

Một bước thuật toán phải lấy phần tử đã được bước trước tạo ra, không có thao tác xen vào. RemoveFirst ném NoSuchElementException. Nên hiểu gì trước tiên?

**Lời giải:** Kiểm tra giả định và luồng tạo/lấy phần tử. Không nên đổi ngay sang poll rồi bỏ qua null chỉ để lỗi biến mất; việc rỗng có thể là dấu hiệu thuật toán sai.

### Bài 3: đầy ở cả hai đầu

Deque sức chứa 2 đã có `[A, B]`. OfferFirst C và offerLast D lần lượt trả gì?

**Lời giải:** Cả hai trả false nếu không có thao tác tạo chỗ xen vào. Dung lượng áp dụng cho cả deque, không phải mỗi phía có hai chỗ.

### Bài 4: cùng trạng thái đầy nhưng dùng add

Vẫn `[A, B]` ở sức chứa 2, addFirst C và addLast D báo thế nào?

**Lời giải:** Mỗi lời gọi riêng ném IllegalStateException do không có chỗ. Trong điều kiện một luồng của ví dụ, thành viên cũ giữ nguyên sau từng lần bị từ chối.

### Bài 5: đọc có tạo chỗ không?

Deque đầy, bạn gọi peekFirst và getLast thành công. Offer sau đó có được bảo đảm true không?

**Lời giải:** Không. Hai lời gọi chỉ xem, không xóa thành viên. Nếu cấu trúc vẫn đầy thì offer vẫn có thể trả false.

### Bài 6: số 0 và vắng phần tử

Deque<Integer> cấm null chứa một số 0. PollFirst trả 0, lần sau trả null. Có thể dùng 0 làm điều kiện kết thúc không?

**Lời giải:** Không nếu 0 thuộc miền dữ liệu. Phải giữ Integer để kiểm tra null trước, rồi mới mở gói thành int khi có phần tử.

### Bài 7: tự mở gói null

Một biến int nhận trực tiếp pollFirst từ deque rỗng. Có nhận được 0 không?

**Lời giải:** Không. Kết quả Integer là null và tự mở gói gây NullPointerException. Không có giá trị int mặc định được trả thay.

### Bài 8: cùng tên lỗi, khác nguyên nhân

Một NullPointerException xuất hiện khi offerLast(null), một lỗi khác xuất hiện ở `int n = deque.pollFirst()`. Có phải cả hai đều nói deque đầy không?

**Lời giải:** Không. Trường hợp đầu có thể là vi phạm chính sách cấm null. Trường hợp sau là mở gói một kết quả null do không có phần tử. Phải xem đúng vị trí và hợp đồng của lời gọi.

### Bài 9: null thật trong LinkedList

Deque dùng LinkedList chứa `[null, X]`. GetFirst và removeFirst có bắt buộc ném lỗi không?

**Lời giải:** Không, vì cấu trúc không rỗng và LinkedList cho phép null. GetFirst trả null mà không xóa; removeFirst trả null và xóa thành viên ấy, để lại X.

### Bài 10: không có chỗ nhưng vẫn báo thành công

Hàm gọi offerLast rồi luôn trả true cho bên gửi. Khi deque đầy, điều gì sai?

**Lời giải:** Hàm bỏ qua false và báo nhận một phần tử chưa được chèn. Cần truyền hoặc xử lý kết quả thật, rồi áp dụng chính sách từ chối/thử lại đã xác định.

### Bài 11: giới hạn khởi tạo

Bạn tạo ArrayDeque với số 2 và kỳ vọng thành viên thứ ba gây IllegalStateException. Giả định nào cần sửa?

**Lời giải:** Số đó không phải sức chứa tối đa cố định của ArrayDeque. Muốn kiểm chứng đầy do giới hạn, dùng một lớp có giới hạn thật như LinkedBlockingDeque được tạo sức chứa 2 trong bài.

### Bài 12: kiểm tra trước khi lấy

Ở môi trường có tác nhân khác cùng lấy dữ liệu, isEmpty vừa trả false. Có thể bỏ qua khả năng removeFirst gặp rỗng không?

**Lời giải:** Không. Trạng thái có thể thay đổi giữa hai lời gọi. Xử lý kết quả của thao tác lấy thực sự, dùng API chờ nếu cần, hoặc bảo vệ chuỗi thao tác theo hợp đồng phối hợp phù hợp.

## 20. Câu hỏi cuối cùng trước khi chọn phương thức

Trước mỗi điểm đọc hoặc chèn, hãy hỏi: **trạng thái rỗng/đầy ở đây là một kết quả được phép hay là dấu hiệu giả định đã bị phá vỡ?**

Nếu là kết quả được phép, chọn dạng trả giá trị và xử lý đầy đủ false/null. Nếu là vi phạm giả định, giữ một tín hiệu lỗi rõ và xác định nơi nó được xử lý hoặc truyền ra.

Sau đó kiểm tra riêng chính sách dữ liệu, nhất là null, kiểu trả về và tác dụng xóa. Cách báo không thực hiện được không thay thế việc hiểu lớp đang dùng, và một giá trị bình thường chỉ hữu ích khi mã gọi giữ nguyên ý nghĩa của nó.
