# Dùng Deque làm hàng đợi FIFO hoặc ngăn xếp LIFO

## 1. Cùng một cấu trúc, hai quy tắc chọn việc tiếp theo

Một ứng dụng nhận các công việc A, B, C. Nếu cần xử lý công việc đến trước trước, thứ tự lấy ra là A, B, C. Nhưng khi lưu các thao tác để hoàn tác, thao tác mới nhất thường phải được lấy ra trước: C, B, A.

Hai yêu cầu dùng hai chính sách:

- **FIFO — First In, First Out:** vào trước, ra trước; thường gọi là hàng đợi.
- **LIFO — Last In, First Out:** vào sau, ra trước; thường gọi là ngăn xếp.

`Deque<E>` là giao diện cho một dãy có thể thêm, xem và lấy phần tử ở cả hai đầu. Tên là dạng rút gọn của “double-ended queue”, nghĩa là hàng đợi hai đầu. Vì có hai đầu thao tác, Deque có thể biểu đạt cả FIFO lẫn LIFO.

Điều quyết định hành vi không chỉ là tên lớp, mà còn là **cặp đầu thêm và đầu lấy**:

```text
FIFO: thêm ở một đầu, lấy ở đầu đối diện
LIFO: thêm và lấy ở cùng một đầu
```

Trong Java, quy ước phổ biến là:

```text
FIFO: offerLast / pollFirst
LIFO: push / pop, tương đương addFirst / removeFirst
```

Bài này dùng `ArrayDeque` làm triển khai cụ thể trong mã đơn luồng. Mục tiêu là chọn đúng thao tác, hiểu trường hợp rỗng và thấy chính sách FIFO/LIFO thay đổi cách một thuật toán xử lý dữ liệu.

## 2. Quy ước đầu và cuối phải rõ ràng

Hãy vẽ Deque theo thứ tự từ đầu đến cuối:

```text
head / first                          tail / last
     A  <------------>  B  <------------>  C
```

Các tên `First` và `Last` chỉ đầu của dãy hiện tại. “First” không có nghĩa tự động là phần tử được thêm sớm nhất: nếu liên tục thêm ở đầu, phần tử mới nhất sẽ đứng first.

Có ba nhóm thao tác ở mỗi đầu:

| Việc cần làm | Đầu first | Đầu last |
|---|---|---|
| Thêm | `addFirst`, `offerFirst` | `addLast`, `offerLast` |
| Lấy và gỡ | `removeFirst`, `pollFirst` | `removeLast`, `pollLast` |
| Chỉ xem | `getFirst`, `peekFirst` | `getLast`, `peekLast` |

Tên phương thức cho biết cả hành động lẫn đầu thao tác. Các cặp trong cùng ô khác nhau chủ yếu ở cách biểu đạt một thất bại thông thường như rỗng hoặc không đủ chỗ; phần sau sẽ phân biệt cụ thể.

Theo [Deque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html), giao diện này mở rộng Queue, đồng thời cung cấp các thao tác ở cả hai đầu. Deque không phải List có truy cập theo chỉ số.

Một cách khai báo:

```java
// Trích đoạn; cần import java.util.Deque và java.util.ArrayDeque.
Deque<String> pending = new ArrayDeque<>();
```

`Deque` diễn tả khả năng mà mã gọi cần; `ArrayDeque` chọn cách lưu trữ. Việc dùng một kiểu giao diện không làm đối tượng tự có thêm khả năng đồng bộ hoặc bất biến.

## 3. Dùng Deque làm hàng đợi FIFO

### 3.1. Quy tắc thêm cuối, lấy đầu

Đưa lần lượt A, B, C vào cuối:

```text
offerLast(A): [A]
offerLast(B): [A, B]
offerLast(C): [A, B, C]
```

Sau đó lấy ở đầu:

```text
pollFirst(): A       còn [B, C]
pollFirst(): B       còn [C]
pollFirst(): C       còn []
```

Bất biến cần giữ là: trong các phần tử đang chờ, phần tử được thêm sớm nhất đứng ở đầu lấy tiếp theo.

Mẫu sử dụng với ArrayDeque:

```java
// Trích đoạn minh họa xử lý FIFO trong một luồng.
Deque<String> jobs = new ArrayDeque<>();
jobs.offerLast("A");
jobs.offerLast("B");
jobs.offerLast("C");

String next;
while ((next = jobs.pollFirst()) != null) {
    process(next);
}
```

`process` là xử lý nghiệp vụ trong chương trình bao quanh, không phải hàm có sẵn của Java. Trích đoạn chưa phải chương trình độc lập.

Mẫu dùng null để kết thúc phù hợp ở đây vì ArrayDeque không chấp nhận phần tử null. `pollFirst` trả null nghĩa là không còn phần tử, không bị nhầm với một công việc null thật.

### 3.2. Có thể chỉ dùng giao diện Queue

Nếu mã chỉ cần FIFO, không cần nhìn thấy cả hai đầu:

```java
// Trích đoạn; cần import java.util.Queue và ArrayDeque.
Queue<String> jobs = new ArrayDeque<>();
jobs.offer("A");
jobs.offer("B");
String next = jobs.poll();  // "A"
```

Với một Deque như ArrayDeque, các phương thức kế thừa từ Queue tương ứng:

| Qua Queue | Qua Deque |
|---|---|
| `add(e)` | `addLast(e)` |
| `offer(e)` | `offerLast(e)` |
| `remove()` | `removeFirst()` |
| `poll()` | `pollFirst()` |
| `element()` | `getFirst()` |
| `peek()` | `peekFirst()` |

Dùng kiểu Queue giúp phần mã ấy chỉ thao tác qua giao diện hàng đợi. Nó không ngăn một phần mã khác đang giữ cùng đối tượng Deque gọi thao tác ở đầu khác; quyền sở hữu và chia sẻ tham chiếu vẫn cần rõ.

Cũng không được suy rộng rằng mọi triển khai Queue đều FIFO. [Queue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html) còn có các chính sách khác, chẳng hạn hàng đợi ưu tiên. Ví dụ trong bài là FIFO vì đối tượng ArrayDeque và cặp thao tác đã chọn có quy tắc đó.

### 3.3. FIFO không tự sắp xếp theo giá trị

Nếu lần lượt thêm `"C"`, `"A"`, `"B"`, hàng đợi FIFO lấy ra C, A, B. Nó bảo toàn thứ tự chờ, không sắp xếp từ điển.

Nếu thêm hai công việc bằng nhau theo equals, Deque vẫn có thể giữ cả hai lần xuất hiện. Đây không phải Set khử trùng.

## 4. Dùng Deque làm ngăn xếp LIFO

### 4.1. Chọn đầu first làm đỉnh

Các phương thức quen dùng:

```java
// Trích đoạn minh họa LIFO.
Deque<String> history = new ArrayDeque<>();
history.push("A");
history.push("B");
history.push("C");

String top = history.peek();   // "C", chỉ xem
String removed = history.pop(); // "C", lấy và gỡ
```

Với Deque:

| Phương thức | Ý nghĩa |
|---|---|
| `push(e)` | Thêm ở đầu, tương đương `addFirst(e)` |
| `pop()` | Lấy và gỡ đầu, tương đương `removeFirst()` |
| `peek()` | Chỉ xem đầu, tương đương `peekFirst()`; null khi rỗng |
| `getFirst()` | Chỉ xem đầu, nhưng ném ngoại lệ khi rỗng |

Sau ba lần push:

```text
push(A): [A]
push(B): [B, A]
push(C): [C, B, A]
          ^
         top
```

Pop lần lượt lấy C, B, A. Bất biến là phần tử được push gần nhất trong những phần tử chưa lấy ra đứng tại đỉnh.

### 4.2. Đừng nhầm tên phương thức với vai trò biến

Một biến tên `queue` nhưng gọi `push` và `pop` vẫn có hành vi LIFO. Một biến tên `stack` nhưng thêm cuối rồi lấy đầu vẫn có hành vi FIFO.

Tên biến nên thể hiện ý định, nhưng cặp thao tác mới thực hiện ý định đó.

Nếu muốn lấy ở đỉnh mà xử lý rỗng bằng null, có thể dùng `pollFirst()` thay cho pop. LIFO vẫn đúng vì vẫn lấy ở chính đầu đang được dùng để thêm.

### 4.3. Có thể dùng đầu last làm đỉnh không?

Có. `addLast` với `removeLast`, hoặc `offerLast` với `pollLast`, cũng tạo LIFO. Cả thêm và lấy đều ở cùng đầu.

Tuy nhiên, khi dùng các tên `push`, `pop`, đỉnh theo quy ước API là first. Không push ở first rồi pop bằng removeLast nếu đang muốn LIFO.

Một bảng tự kiểm tra:

| Đầu thêm | Đầu lấy | Chính sách theo thứ tự thêm |
|---|---|---|
| Last | First | FIFO |
| First | Last | FIFO nếu nhất quán dùng cặp này |
| First | First | LIFO |
| Last | Last | LIFO |

Hai dòng FIFO đều hợp lý về toán học của dãy, nhưng quy ước Queue của Java dùng thêm last, lấy first. Chọn một quy ước rõ và giữ nhất quán giúp mã dễ đọc hơn.

## 5. Chương trình 1: cùng đầu vào, hai thứ tự đầu ra

Lưu tệp `DequeFifoLifoDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Queue;

public class DequeFifoLifoDemo {
    public static void main(String[] args) {
        List<String> input = List.of("A", "B", "C");

        Deque<String> fifo = new ArrayDeque<>();
        for (String item : input) {
            fifo.offerLast(item);
        }
        System.out.println("FIFO head to tail = " + fifo);
        System.out.println("FIFO next = " + fifo.peekFirst());
        System.out.println("FIFO size after peek = " + fifo.size());

        List<String> fifoOutput = new ArrayList<>();
        String item;
        while ((item = fifo.pollFirst()) != null) {
            fifoOutput.add(item);
        }
        System.out.println("FIFO output = " + fifoOutput);
        System.out.println("FIFO empty = " + fifo.isEmpty());

        Deque<String> lifo = new ArrayDeque<>();
        for (String value : input) {
            lifo.push(value);
        }
        System.out.println("LIFO head to tail = " + lifo);
        System.out.println("LIFO top = " + lifo.peek());

        List<String> lifoOutput = new ArrayList<>();
        while (!lifo.isEmpty()) {
            lifoOutput.add(lifo.pop());
        }
        System.out.println("LIFO output = " + lifoOutput);
        System.out.println("LIFO empty = " + lifo.isEmpty());

        Queue<String> queueApi = new ArrayDeque<>(input);
        List<String> queueOutput = new ArrayList<>();
        while ((item = queueApi.poll()) != null) {
            queueOutput.add(item);
        }
        System.out.println("Queue API output = " + queueOutput);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 DequeFifoLifoDemo.java
java DequeFifoLifoDemo
```

Kết quả của lần chạy kiểm chứng:

```text
FIFO head to tail = [A, B, C]
FIFO next = A
FIFO size after peek = 3
FIFO output = [A, B, C]
FIFO empty = true
LIFO head to tail = [C, B, A]
LIFO top = C
LIFO output = [C, B, A]
LIFO empty = true
Queue API output = [A, B, C]
```

Các chương trình trong bài dùng ngôn ngữ và API có ở Java 17 trở lên. Chúng được biên dịch với `--release 17` và chạy kiểm chứng bằng Azul OpenJDK 24.0.2.

Những điểm quan trọng:

- FIFO giữ đầu vào A, B, C ở thứ tự từ head đến tail, rồi lấy theo cùng thứ tự.
- LIFO push ở head nên dãy từ head đến tail là C, B, A.
- Peek không làm giảm size.
- Poll hoặc pop có lấy và gỡ phần tử.
- Dùng giao diện Queue trên ArrayDeque cho cùng hành vi FIFO như các thao tác last/first tương ứng.

Không đọc `[C, B, A]` của ngăn xếp thành “ArrayDeque tự đảo mảng khi in”. Đó là dãy logic được tạo bởi ba lần thêm ở đầu.

Cũng không nên chỉ kiểm tra rằng đã lấy đủ ba phần tử. Cả FIFO và LIFO đều có đủ A, B, C; điều khác biệt mà bài toán cần bảo vệ là thứ tự lấy ra.

## 6. Chọn cách xử lý rỗng và không đủ chỗ

Deque cung cấp các nhóm phương thức để thể hiện cách xử lý thất bại.

### 6.1. Lấy và xem khi rỗng

| Việc | Ném `NoSuchElementException` nếu rỗng | Trả null nếu rỗng |
|---|---|---|
| Xem đầu | `getFirst()` | `peekFirst()` |
| Xem cuối | `getLast()` | `peekLast()` |
| Lấy và gỡ đầu | `removeFirst()` | `pollFirst()` |
| Lấy và gỡ cuối | `removeLast()` | `pollLast()` |

`pop()` thuộc nhóm lấy đầu và ném ngoại lệ. `peek()` của **Deque** thuộc nhóm trả null.

Chọn dựa trên ý nghĩa của luồng xử lý:

- Hàng đợi tạm hết việc là tình huống bình thường: poll thường biểu đạt phù hợp.
- Thuật toán đã bảo đảm chắc chắn phải có phần tử: remove hoặc pop có thể làm lộ lỗi giả định.
- Chỉ cần nhìn việc tiếp theo: peek hoặc get, không dùng phương thức gỡ.

Không dùng ngoại lệ như cách lặp bình thường để phát hiện hết dữ liệu nếu có một phương thức trả trạng thái phù hợp.

### 6.2. Thêm vào cấu trúc có giới hạn dung lượng

`addFirst`/`addLast` có thể ném IllegalStateException nếu một triển khai có giới hạn không còn chỗ. `offerFirst`/`offerLast` có thể trả false trong tình huống không đủ chỗ như vậy.

Nhưng offer không có nghĩa “mọi lỗi đều được chuyển thành false”. Ví dụ, đưa null vào ArrayDeque vẫn ném NullPointerException.

ArrayDeque tự tăng sức chứa khi cần, không phải một hàng đợi có giới hạn cố định do tham số constructor đặt ra. Nếu bài toán cần giới hạn chờ hoặc chờ tới khi có chỗ, phải chọn triển khai và API phù hợp; Queue/Deque thông thường không tự cung cấp cơ chế chờ.

### 6.3. Không dùng null như dữ liệu công việc trong ArrayDeque

Null bị từ chối để các phương thức như poll và peek có thể dùng null làm dấu không có phần tử.

Nếu cần một công việc mang ý nghĩa “thiếu dữ liệu” hoặc “kết thúc”, hãy biểu diễn bằng một giá trị hoặc kiểu dữ liệu rõ ràng, không nhét null vào cấu trúc không chấp nhận nó.

Giao diện Deque có thể được triển khai bởi lớp có chính sách null khác, nhưng dùng null cho hàng đợi/ngăn xếp thường tạo mơ hồ với các phương thức trả null. Các mẫu trong bài dựa trên hợp đồng không null của ArrayDeque.

## 7. Chương trình 2: kiểm chứng API rỗng và null

Lưu tệp `DequeEmptyPolicyDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.NoSuchElementException;

public class DequeEmptyPolicyDemo {
    static void showEmptyFailure(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected NoSuchElementException");
        } catch (NoSuchElementException ex) {
            System.out.println(label + " = " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        Deque<String> values = new ArrayDeque<>();

        System.out.println("empty peekFirst = " + values.peekFirst());
        System.out.println("empty peekLast = " + values.peekLast());
        System.out.println("empty pollFirst = " + values.pollFirst());
        System.out.println("empty pollLast = " + values.pollLast());
        System.out.println("size after empty reads = " + values.size());

        showEmptyFailure("empty getFirst", values::getFirst);
        showEmptyFailure("empty getLast", values::getLast);
        showEmptyFailure("empty removeFirst", values::removeFirst);
        showEmptyFailure("empty removeLast", values::removeLast);
        showEmptyFailure("empty pop", values::pop);

        try {
            values.offerLast(null);
        } catch (NullPointerException ex) {
            System.out.println("offer null = "
                    + ex.getClass().getSimpleName());
        }
        try {
            values.push(null);
        } catch (NullPointerException ex) {
            System.out.println("push null = "
                    + ex.getClass().getSimpleName());
        }

        System.out.println("offer X = " + values.offerLast("X"));
        System.out.println("peek X = " + values.peekFirst());
        System.out.println("size after peek X = " + values.size());
        System.out.println("pop X = " + values.pop());
        System.out.println("size after pop X = " + values.size());

        Deque<String> growing = new ArrayDeque<>(1);
        growing.offerLast("A");
        growing.offerLast("B");
        growing.offerLast("C");
        System.out.println("initial capacity is not limit = " + growing);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 DequeEmptyPolicyDemo.java
java DequeEmptyPolicyDemo
```

Kết quả của lần chạy kiểm chứng:

```text
empty peekFirst = null
empty peekLast = null
empty pollFirst = null
empty pollLast = null
size after empty reads = 0
empty getFirst = NoSuchElementException
empty getLast = NoSuchElementException
empty removeFirst = NoSuchElementException
empty removeLast = NoSuchElementException
empty pop = NoSuchElementException
offer null = NullPointerException
push null = NullPointerException
offer X = true
peek X = X
size after peek X = 1
pop X = X
size after pop X = 0
initial capacity is not limit = [A, B, C]
```

Hàm `showEmptyFailure` chỉ giúp tập trung phần kiểm tra ngoại lệ trong ví dụ. Nếu phương thức không ném ngoại lệ như mong đợi, nó ném AssertionError để không in ra một kết quả gây hiểu nhầm.

### 7.1. Phương thức trả null không làm thay đổi tập rỗng

Các lời gọi peek và poll trên Deque rỗng đều trả null, size vẫn bằng 0.

Đối với Deque có X, peek trả X và size vẫn bằng 1; pop trả X rồi size giảm về 0. Vì vậy, hai thao tác “nhìn” và “lấy” không thể thay thế nhau chỉ vì trả về cùng giá trị trong một ví dụ.

### 7.2. Offer vẫn có thể ném ngoại lệ

`offerLast(null)` ném NullPointerException. Không nên viết mã chỉ kiểm tra boolean rồi cho rằng đã xử lý mọi đầu vào sai.

Nếu mã nhận dữ liệu từ ngoài, xác định chính sách null trước khi đưa vào Deque. Việc kết thúc vòng lặp bằng poll trả null chỉ rõ ràng khi dữ liệu thành viên không thể null.

### 7.3. Sức chứa ban đầu không phải giới hạn

`new ArrayDeque<>(1)` vẫn chứa được A, B, C trong chương trình. Constructor chuẩn bị sức chứa ban đầu đủ cho nhu cầu được nêu; nó không thiết lập “chỉ được có một phần tử”.

Điều này quan trọng nếu Deque dùng để giữ việc đang chờ. Cần một giới hạn nghiệp vụ thực sự thì phải thiết kế hoặc chọn cấu trúc có hợp đồng giới hạn; không dùng initial capacity như một cơ chế chặn số lượng.

## 8. Vì sao ArrayDeque là lựa chọn thường dùng trong một luồng?

[ArrayDeque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html) mô tả nó là Deque dựa trên mảng có thể tăng sức chứa, không chấp nhận null và không tự an toàn cho truy cập đồng thời không có phối hợp.

Một mô hình hữu ích là mảng vòng: cấu trúc giữ vị trí hai đầu, nên thêm hoặc lấy ở đầu không cần dồn toàn bộ phần tử như cách bỏ phần tử đầu của một mảng tuyến tính ngây thơ.

Khi cần tăng mảng, một thao tác có thể phải cấp phát và chuyển dữ liệu. Vì thế, chi phí thường được phân tích theo **khấu hao** trên một chuỗi thao tác.

Với ArrayDeque, các thao tác ở hai đầu thông dụng phù hợp với chi phí hằng số khấu hao. Nhưng không suy rộng mọi phương thức của Deque đều O(1):

| Việc làm | Cách phân tích phù hợp với ArrayDeque |
|---|---|
| Thêm/lấy ở hai đầu | Hằng số khấu hao đối với các thao tác thông dụng |
| Xem hai đầu | Không phải quét toàn bộ dãy |
| `contains(x)` | Có thể cần tìm qua các phần tử |
| `remove(x)` theo giá trị | Có thể cần tìm và điều chỉnh dãy |
| Duyệt toàn bộ n phần tử | Cần xử lý n phần tử |
| Lưu n phần tử | Cần bộ nhớ cho cấu trúc và tham chiếu dữ liệu |

Nếu bài toán chủ yếu thêm và lấy ở hai đầu, Deque biểu đạt đúng thao tác. Nếu cần truy cập thường xuyên theo chỉ số hoặc sắp xếp theo một tiêu chí, hãy đánh giá cấu trúc khác thay vì cố dùng Deque cho mọi việc.

Không cần một benchmark tự chế bằng vài lời gọi đồng hồ để kết luận ArrayDeque luôn nhanh hơn mọi lớp khác. Chọn trước theo hợp đồng, thao tác và môi trường; đo khi hiệu năng thực tế cần được đánh giá.

### 8.1. So với Stack cũ

[Tài liệu Stack Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Stack.html) khuyến nghị dùng Deque và các triển khai của nó thay cho lớp Stack cũ để biểu đạt thao tác LIFO.

Một khai báo rõ ý định là:

```java
Deque<Integer> stack = new ArrayDeque<>();
```

Nếu chuyển mã cũ, phải kiểm tra cả chính sách rỗng. Deque.pop ném NoSuchElementException khi rỗng, và Deque.peek trả null. Không mặc định mọi chi tiết ngoại lệ hoặc hành vi của Stack cũ được giữ nguyên chỉ vì các phương thức cùng tên.

### 8.2. Hỗ trợ nhiều luồng là một quyết định riêng

Một ArrayDeque dùng đúng FIFO vẫn có thể được chia sẻ sai giữa nhiều luồng. Quy tắc lấy đầu nào không cung cấp tính nguyên tử cho các chuỗi thao tác.

Nếu cần nhiều bên tạo hoặc xử lý việc, cần chọn cơ chế phối hợp hoặc các collection đồng thời/chặn phù hợp. Không đổi sang một lớp khác chỉ vì tên có Queue rồi coi mọi yêu cầu về thứ tự, dung lượng và chờ đều đã được giải quyết.

Các ví dụ trong bài là mã một luồng; kiểm tra rỗng rồi pop là hợp lý trong giả định đó. Không mang nguyên giả định sang một ngữ cảnh có cập nhật đồng thời.

## 9. FIFO và LIFO thay đổi cách duyệt một cây

Xét cây nhị phân:

```text
          A
        /          B     C
      /           D   E     F
```

Giả sử khi phát hiện các nút con, ta muốn ưu tiên trái trước phải.

### 9.1. Hàng đợi FIFO: theo từng tầng

Bắt đầu với A. Sau khi xử lý A, thêm B rồi C ở cuối:

```text
lấy A -> hàng đợi [B, C]
lấy B -> hàng đợi [C, D, E]
lấy C -> hàng đợi [D, E, F]
```

Các nút đang chờ sớm hơn được lấy trước. Kết quả là:

```text
A, B, C, D, E, F
```

Đây là duyệt theo chiều rộng, thường gọi là breadth-first traversal.

### 9.2. Ngăn xếp LIFO: đi sâu theo nhánh

Sau khi xử lý A, muốn B được lấy tiếp thì phải push C trước, rồi push B:

```text
push C rồi B -> ngăn xếp [B, C]
pop B
push E rồi D -> ngăn xếp [D, E, C]
```

D được lấy trước E, và cả nhánh B được xử lý trước C. Kết quả:

```text
A, B, D, E, C, F
```

Đây là một kiểu duyệt sâu theo thứ tự trước, thường gọi là depth-first preorder traversal.

Điểm cốt lõi là: **với LIFO, thứ tự đẩy nhiều phần tử cần đảo lại nếu muốn thứ tự xử lý giống danh sách ưu tiên ban đầu**.

Cây chỉ là một ví dụ về cách chọn việc tiếp theo. Cùng ý tưởng xuất hiện khi duyệt thư mục, xử lý cấu trúc lồng nhau hoặc quản lý các bước tính toán đang chờ.

## 10. Chương trình 3: một cây, hai chính sách xử lý

Lưu tệp `DequeTreeTraversalDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;

public class DequeTreeTraversalDemo {
    record Node(String name, Node left, Node right) {
    }

    static List<String> breadthFirst(Node root) {
        if (root == null) {
            return List.of();
        }

        Deque<Node> pending = new ArrayDeque<>();
        List<String> result = new ArrayList<>();
        pending.offerLast(root);

        while (!pending.isEmpty()) {
            Node current = pending.removeFirst();
            result.add(current.name());

            if (current.left() != null) {
                pending.offerLast(current.left());
            }
            if (current.right() != null) {
                pending.offerLast(current.right());
            }
        }
        return result;
    }

    static List<String> depthFirst(Node root) {
        if (root == null) {
            return List.of();
        }

        Deque<Node> pending = new ArrayDeque<>();
        List<String> result = new ArrayList<>();
        pending.push(root);

        while (!pending.isEmpty()) {
            Node current = pending.pop();
            result.add(current.name());

            if (current.right() != null) {
                pending.push(current.right());
            }
            if (current.left() != null) {
                pending.push(current.left());
            }
        }
        return result;
    }

    public static void main(String[] args) {
        Node root = new Node("A",
                new Node("B",
                        new Node("D", null, null),
                        new Node("E", null, null)),
                new Node("C",
                        null,
                        new Node("F", null, null)));

        System.out.println("breadth first FIFO = " + breadthFirst(root));
        System.out.println("depth first LIFO = " + depthFirst(root));
        System.out.println("empty tree FIFO = " + breadthFirst(null));
        System.out.println("empty tree LIFO = " + depthFirst(null));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 DequeTreeTraversalDemo.java
java DequeTreeTraversalDemo
```

Kết quả của lần chạy kiểm chứng:

```text
breadth first FIFO = [A, B, C, D, E, F]
depth first LIFO = [A, B, D, E, C, F]
empty tree FIFO = []
empty tree LIFO = []
```

### 10.1. Null của nút con không được đưa vào Deque

Các nút lá có liên kết con null. Mã kiểm tra liên kết trước khi thêm, nên ArrayDeque chỉ chứa các Node thật.

Root null được xử lý ngay bằng danh sách rỗng. Không cần nhét null vào hàng đợi như một nút đặc biệt.

Đây là sự khác nhau giữa một trường dữ liệu có thể null và chính phần tử được thêm vào Deque. Dữ liệu đầu vào của thuật toán có thể có liên kết trống, nhưng collection đang dùng vẫn giữ hợp đồng không nhận null.

### 10.2. Hàng đợi giữ thứ tự phát hiện

Trong breadthFirst, con trái rồi con phải được thêm ở cuối. Những nút đã chờ từ trước vẫn ở phía đầu, nên một nút ở tầng tiếp theo không chen lên trước các nút của tầng hiện tại.

Mỗi Node được xử lý một lần trong cây của ví dụ. Kết quả trả về tách riêng khỏi Deque đang dùng làm vùng chờ.

### 10.3. Ngăn xếp đảo thứ tự thêm các nút con

Trong depthFirst, mã push con phải trước, con trái sau. Con trái vì thế nằm ở đỉnh và được xử lý trước.

Nếu đổi hai khối if, chương trình vẫn dùng LIFO nhưng thứ tự ưu tiên nhánh sẽ đổi. “Dùng stack” không tự xác định muốn duyệt trái hay phải trước; thứ tự push còn là một quyết định của thuật toán.

### 10.4. Đây là cây, không phải bộ duyệt đồ thị tổng quát

Dữ liệu ví dụ là một cây hữu hạn, không có chu trình và không có nút con dùng chung qua nhiều đường. Vì thế không cần một tập đánh dấu đã thăm.

Với một đồ thị có chu trình hoặc nhiều đường dẫn tới cùng đỉnh, chỉ đổi Deque giữa FIFO và LIFO chưa đủ để có thuật toán đúng: cần chính sách đánh dấu và tránh lặp phù hợp.

Không áp dụng nguyên mẫu mã cây cho dữ liệu có chu trình rồi kết luận Deque bị lỗi khi chương trình không dừng.

### 10.5. Chi phí của hai mẫu

Với n nút, mỗi nút trong cây ví dụ được thêm, lấy và ghi nhận một lần, nên thời gian là O(n) khi thao tác đầu/cuối có chi phí khấu hao phù hợp.

Phần đang chờ có đặc điểm khác nhau:

- Duyệt rộng có thể phải giữ nhiều nút ở một tầng; bộ nhớ chờ phụ thuộc độ rộng của cây.
- Duyệt sâu ở cây nhị phân giữ đường đi và các nhánh chờ; có cận theo chiều cao cây cho kiểu triển khai này.
- Danh sách result còn giữ n tên, nên bản thân kết quả cần O(n) bộ nhớ.

Không bỏ qua bộ nhớ kết quả khi phân tích tổng chương trình. Deque chỉ là phần điều phối việc đang chờ.

## 11. Chọn FIFO hoặc LIFO theo yêu cầu, không theo thói quen

Một số quan hệ thường gặp:

| Yêu cầu | Chính sách phù hợp để cân nhắc | Lý do |
|---|---|---|
| Xử lý công việc theo thứ tự chờ | FIFO | Việc đã chờ trước được lấy trước |
| Duyệt theo từng tầng | FIFO | Các nút được phát hiện sớm hơn tiếp tục đứng trước |
| Hoàn tác thao tác gần nhất | LIFO | Thao tác sau cần được đảo trước |
| Duyệt sâu bằng cấu trúc tường minh | LIFO | Tiếp tục nhánh vừa được chọn |
| Khôi phục cấu trúc lồng nhau | LIFO | Mức lồng gần nhất thường được đóng trước |

Deque chỉ giữ thứ tự phần tử. Ví dụ, dùng nó cho hoàn tác không tự làm một hành động trở nên có thể đảo ngược. Phần tử cần chứa đủ thông tin để thực hiện hành động ngược theo nghiệp vụ.

FIFO cũng không tự cung cấp độ bền dữ liệu, xác nhận hoàn tất hoặc giao việc qua tiến trình. Một ArrayDeque trong bộ nhớ không trở thành một hệ thống hàng đợi bên ngoài chỉ vì tên biến là jobs.

Trong một thuật toán, đổi FIFO sang LIFO có thể đổi cả ý nghĩa kết quả. Hãy xác định vì sao phần tử đang chờ nào cần được xử lý tiếp, rồi chọn cặp thao tác tương ứng.

### 11.1. Không trộn vai trò trên cùng một dãy mà thiếu quy tắc

Nếu một phần mã offerLast để giữ FIFO còn phần khác push ở đầu, công việc được push có thể chen trước những công việc đã chờ. Điều đó có thể là yêu cầu ưu tiên hợp lệ, nhưng khi ấy không còn là FIFO thuần theo thời điểm thêm.

Nếu một phần mã dùng đầu first làm đỉnh mà phần khác lấy last, trạng thái ngăn xếp có thể được tiêu thụ ngược mong đợi.

Nên giữ Deque trong một phạm vi sở hữu rõ, đặt tên theo vai trò và cung cấp các thao tác nghiệp vụ nhất quán. Dùng kiểu Queue cho một phần chỉ cần FIFO cũng giúp giảm khả năng gọi nhầm qua tham chiếu ấy.

### 11.2. Không dùng việc in Deque thay cho việc định nghĩa thứ tự

ArrayDeque được duyệt từ first tới last. Với stack dùng first làm đỉnh, iterator đi từ đỉnh xuống đáy.

Nhưng một vòng for-each chỉ đọc, không pop. In ra đúng thứ tự mong đợi chưa chứng minh vòng xử lý thực sự lấy ở đúng đầu hoặc gỡ phần tử sau xử lý.

Hãy kiểm tra chính dãy lấy ra bằng poll/pop, đặc biệt khi thuật toán thêm tiếp phần tử trong lúc đang xử lý.

## 12. Các lỗi thường gặp khi dùng Deque

| Cách làm | Hậu quả hoặc điểm nhầm | Cách sửa |
|---|---|---|
| Muốn FIFO nhưng addLast và pollLast | Lấy mới nhất trước, thành LIFO | Lấy ở đầu đối diện |
| Muốn LIFO nhưng push rồi removeLast | Lấy phần tử cũ ở đáy | Dùng pop hoặc pollFirst theo chính sách rỗng |
| Dùng peek trong vòng lặp nhưng không gỡ | Có thể xử lý mãi cùng một phần tử | Dùng poll/pop khi cần tiêu thụ |
| Dùng pop khi rỗng là bình thường | Phải xử lý ngoại lệ không cần thiết | Dùng pollFirst hoặc điều kiện phù hợp |
| Dùng poll khi rỗng là lỗi mà không kiểm tra | Có thể bỏ qua lỗi giả định | Xử lý null hoặc dùng phương thức ném ngoại lệ |
| Offer null rồi chờ false | ArrayDeque ném NullPointerException | Xác định dữ liệu không null |
| Coi initial capacity là giới hạn | Deque vẫn tăng và giữ thêm dữ liệu | Chọn cơ chế giới hạn thật |
| Cho rằng Queue nào cũng FIFO | Triển khai ưu tiên có chính sách khác | Đọc hợp đồng lớp đang dùng |
| Thêm trái rồi phải bằng push mà muốn xử lý trái trước | Phải được lấy trước vì nằm trên đỉnh | Push theo thứ tự ngược lại |
| Gọi remove(x) như lấy đầu | Đây là tìm và gỡ theo giá trị | Phân biệt remove() với remove(Object) |
| Pop trong vòng for-each trên cùng Deque | Có thể làm iterator phát hiện sửa đổi | Dùng vòng lấy phần tử trực tiếp |
| Chia sẻ ArrayDeque giữa nhiều luồng không phối hợp | Đúng cặp đầu vẫn chưa bảo đảm nhất quán | Chọn cơ chế đồng thời phù hợp |

Một bẫy đơn giản nhưng đáng kiểm tra là vòng lặp:

```java
// Trích đoạn lỗi nếu không có bước nào gỡ hoặc thay đổi head.
while (jobs.peekFirst() != null) {
    process(jobs.peekFirst());
}
```

Nếu process không gỡ hoặc làm thay đổi dãy, cùng một công việc ở đầu sẽ được xử lý mãi. Việc “đọc được phần tử” và “đã tiêu thụ phần tử” là hai trạng thái khác nhau.

Mẫu tiêu thụ FIFO với ArrayDeque là lấy bằng pollFirst, kiểm tra kết quả rồi xử lý chính giá trị đã lấy. Không peek lại và hy vọng đó luôn là cùng phần tử trong mọi ngữ cảnh chia sẻ dữ liệu.

## 13. Kiểm tra thứ tự bằng những tình huống bộc lộ được sai đầu

Một kiểm tra chỉ có một phần tử không phân biệt được FIFO và LIFO. Với A duy nhất, cả hai đều lấy A.

Nên có ít nhất các tình huống sau:

### 13.1. Ba phần tử khác nhau

```text
thêm A, B, C

FIFO phải lấy: A, B, C
LIFO phải lấy: C, B, A
```

Đây là bài kiểm tra cơ bản nhất cho việc chọn đầu thêm/lấy.

### 13.2. Thêm xen kẽ với lấy

FIFO:

```text
thêm A
thêm B
lấy -> A
thêm C
lấy tiếp -> B, C
```

LIFO:

```text
push A
push B
pop -> B
push C
pop tiếp -> C, A
```

Trường hợp xen kẽ giúp phát hiện mã chỉ xử lý đúng khi thêm hết rồi mới lấy hết.

### 13.3. Rỗng, một phần tử và phần tử trùng

Kiểm tra rõ:

- Khi rỗng, dùng phương thức trả null hay phương thức ném ngoại lệ?
- Peek có giữ nguyên size không?
- Poll/pop có gỡ đúng một phần tử không?
- Hai lần thêm cùng một giá trị có được giữ như hai lần xuất hiện không?
- Sau khi lấy hết rồi thêm lại, thứ tự vẫn đúng không?
- Null bị xử lý ở đâu trong hợp đồng đầu vào?

Không dùng Set để kiểm tra đầu ra nếu cần bảo vệ thứ tự hoặc số lần xuất hiện; Set có thể che cả hai loại lỗi ấy.

### 13.4. So sánh dữ liệu quan sát được

ArrayDeque không cung cấp phép equals theo dãy giống List. Hai ArrayDeque có cùng phần tử không vì thế mặc định equals bằng true.

Khi cần đối chiếu thứ tự, có thể thu các phần tử lấy ra vào List như chương trình 1, hoặc tạo một List từ iterator để kiểm tra dãy đọc. Hai cách kiểm tra hai ý khác nhau: một cách bảo vệ quá trình tiêu thụ, cách kia chỉ bảo vệ thứ tự duyệt hiện tại.

Cũng không dùng một giá trị thời gian chạy của ví dụ nhỏ làm tiêu chí đúng sai cho FIFO/LIFO. Đây là hợp đồng thứ tự, có thể kiểm tra trực tiếp bằng dữ liệu rõ ràng.

## 14. Bài tập áp dụng

### Bài 1: xác định chính sách

Lần lượt gọi `addLast(A)`, `addLast(B)`, `addLast(C)`, rồi liên tục `pollLast()`.

Đầu ra là gì, có phải FIFO không?

**Gợi ý trả lời:** C, B, A; đây là LIFO vì thêm và lấy ở cùng đầu.

### Bài 2: đổi cách xử lý rỗng mà giữ LIFO

Một stack dùng push. Muốn thao tác lấy trả null khi rỗng thay vì ném ngoại lệ.

Nên dùng phương thức nào?

**Gợi ý trả lời:** pollFirst. Đỉnh của push ở first, nên đổi chính sách lỗi không được đồng thời đổi đầu lấy.

### Bài 3: chỉ xem việc tiếp theo

Một hàng đợi dùng offerLast/pollFirst. Cần xem việc sẽ xử lý tiếp nhưng chưa gỡ.

**Gợi ý trả lời:** peekFirst hoặc peek. Nếu chắc chắn không được rỗng và muốn lỗi rõ khi vi phạm giả định, có thể dùng getFirst hoặc element.

### Bài 4: ba nút con theo ưu tiên

Muốn một stack xử lý các nút con theo thứ tự X, Y, Z. Phải push chúng theo thứ tự nào?

**Gợi ý trả lời:** Z, Y, X, để X được push cuối và nằm trên đỉnh.

### Bài 5: null và offer

Vì offer trả boolean, có thể đưa null vào ArrayDeque rồi dùng false để báo dữ liệu không hợp lệ không?

**Gợi ý trả lời:** không. ArrayDeque không nhận null và offer null ném NullPointerException. Boolean không thay thế hợp đồng đầu vào.

### Bài 6: giới hạn hàng đợi

Khởi tạo `new ArrayDeque<>(100)` có bảo đảm từ chối công việc thứ 101 không?

**Gợi ý trả lời:** không. Đó là sức chứa ban đầu được chuẩn bị, không phải giới hạn cố định. Cần cấu trúc hoặc quy trình giới hạn phù hợp.

### Bài 7: duyệt rộng hay duyệt sâu?

Trong cây ví dụ, sau A muốn xử lý B rồi C trước khi tới D. Nên giữ vùng chờ theo FIFO hay LIFO?

**Gợi ý trả lời:** FIFO, vì các nút cùng tầng đã vào chờ trước phải được lấy trước các nút tầng tiếp theo.

### Bài 8: một kết quả kiểm tra gây hiểu nhầm

Chương trình lấy đủ A, B, C nhưng kết quả là C, B, A trong khi yêu cầu FIFO. Kiểm tra bằng Set vẫn qua.

Sai ở đâu?

**Gợi ý trả lời:** cách kiểm tra đã bỏ mất thứ tự. Cần đối chiếu dãy đầu ra, không chỉ tập thành viên.

Khi dùng Deque trong một thuật toán, hãy ghi rõ đầu thêm, đầu lấy và hành vi lúc rỗng. Ba quyết định ấy nối trực tiếp yêu cầu FIFO/LIFO với từng lời gọi API và giúp giữ quy tắc xử lý ổn định khi mã phát triển.
