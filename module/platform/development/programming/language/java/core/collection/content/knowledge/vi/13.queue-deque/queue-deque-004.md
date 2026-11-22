# Deque và thao tác thêm, xem, xóa ở hai đầu

## 1. Mô hình hai đầu: first và last

`Deque<E>` là hàng hai đầu — double-ended queue. Nó cho phép thêm, xem và lấy/xóa phần tử ở cả hai phía của một dãy.

Trong bài này, luôn vẽ:

```text
first / head                         last / tail
đầu trước       [A] [B] [C]           đầu sau
```

Với trạng thái đó:

- Thêm ở đầu trước đặt phần tử mới trước `A`.
- Thêm ở đầu sau đặt phần tử mới sau `C`.
- Xem đầu trước nhận `A` nhưng giữ nó trong deque.
- Lấy/xóa đầu sau nhận `C` và bỏ nó khỏi deque.

`first` và `last` là vị trí trong dãy hiện tại, không có nghĩa giá trị nhỏ nhất/lớn nhất hoặc cũ nhất/mới nhất trong mọi cách dùng. Chính cách chọn đầu thêm và đầu lấy tạo ra chính sách xử lý.

`Deque` cũng không cung cấp truy cập theo chỉ số như `List`. `getFirst()` không phải một cách viết của `get(0)` được giao diện `Deque` hỗ trợ; nó là phương thức chuyên biệt để xem đầu. [Deque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)

Một cách tạo để thực hành trong một luồng:

```java
Deque<String> values = new ArrayDeque<>();
```

Các ví dụ dùng API tương thích Java 17 và không lưu phần tử `null`.

## 2. Mười hai phương thức, nhìn theo ba việc và hai đầu

Mỗi việc ở mỗi đầu có hai cách báo một số tình huống không thực hiện được:

| Việc | Đầu trước: dạng ngoại lệ | Đầu trước: dạng giá trị đặc biệt | Đầu sau: dạng ngoại lệ | Đầu sau: dạng giá trị đặc biệt |
| --- | --- | --- | --- | --- |
| Thêm | `addFirst(e)` | `offerFirst(e)` | `addLast(e)` | `offerLast(e)` |
| Lấy và xóa | `removeFirst()` | `pollFirst()` | `removeLast()` | `pollLast()` |
| Xem, không xóa | `getFirst()` | `peekFirst()` | `getLast()` | `peekLast()` |

Đọc tên theo hai bước:

1. Phần động từ cho biết thêm, xem hay lấy/xóa.
2. `First` hoặc `Last` cho biết phía nhận thao tác.

Sau đó mới chọn cách muốn xử lý tình huống rỗng hoặc đầy:

| Tình huống | Dạng ngoại lệ | Dạng giá trị đặc biệt |
| --- | --- | --- |
| Không thêm được vì giới hạn dung lượng | `IllegalStateException` từ addFirst/addLast | `false` từ offerFirst/offerLast |
| Xem khi rỗng | `NoSuchElementException` từ getFirst/getLast | `null` từ peekFirst/peekLast |
| Lấy/xóa khi rỗng | `NoSuchElementException` từ removeFirst/removeLast | `null` từ pollFirst/pollLast |

Các cặp không chọn các phần tử khác nhau khi thao tác thành công. Chúng khác cách báo tình huống thất bại tương ứng.

“Dạng giá trị đặc biệt” không có nghĩa mọi lỗi đều được nuốt thành `false` hoặc `null`. Phần tử không hợp lệ vẫn có thể gây ngoại lệ theo hợp đồng triển khai. [Bảng phương thức Deque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)

## 3. Thêm ở hai đầu: addFirst/addLast và offerFirst/offerLast

### 3.1. Tác động lên thứ tự

Giả sử đang có `[B, C]`:

```text
addFirst("A") → [A, B, C]
addLast("D")  → [A, B, C, D]
```

Phần tử mới được đặt đúng phía chỉ định. Deque không tự sắp lại theo bảng chữ cái hoặc theo giá trị.

Với `offerFirst` và `offerLast`, thứ tự khi thêm thành công cũng như vậy:

```java
// Đoạn minh họa.
boolean firstAdded = values.offerFirst("A");
boolean lastAdded = values.offerLast("D");
```

Nếu thành công, mỗi thao tác làm kích thước tăng `1` và trả về `true`.

### 3.2. addFirst/addLast trả void, không trả boolean

Chữ ký:

```java
void addFirst(E value);
void addLast(E value);

boolean offerFirst(E value);
boolean offerLast(E value);
```

Đây là mô tả chữ ký, không phải chương trình độc lập.

Vì `addFirst` và `addLast` trả `void`, không viết:

```java
// Sai kiểu trả về, không biên dịch:
boolean changed = values.addFirst("A");
```

Thành công của một lời gọi `addFirst` được thể hiện bằng việc lời gọi hoàn tất bình thường và phần tử đã được thêm. Nếu muốn nhận cờ để xử lý thiếu chỗ như một tình huống dự kiến, dùng phương thức `offer` tương ứng.

### 3.3. Có đầy hay không phụ thuộc triển khai

`Deque` hỗ trợ cả triển khai có giới hạn dung lượng lẫn triển khai không có một mức tối đa cố định như vậy.

`ArrayDeque` dùng mảng có thể tăng dung lượng. Tham số trong `new ArrayDeque<>(2)` không đặt giới hạn tối đa là hai phần tử.

Ngược lại, một `LinkedBlockingDeque<>(2)` có dung lượng giới hạn hai phần tử. Khi nó đã đầy, `offerFirst` hoặc `offerLast` một đối số trả `false`, còn `addFirst` hoặc `addLast` báo `IllegalStateException`.

Không suy ra hành vi “khi đầy” từ tên giao diện mà chưa biết đối tượng thực tế. [ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html), [LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html)

### 3.4. Thêm phần tử lặp vẫn là thêm

Deque không phải tập loại trùng. Với các triển khai trong bài, thêm `"A"` hai lần tạo hai phần tử có thể được lấy ra hai lần.

`offerFirst("A")` không có nghĩa “thêm nếu chưa có A”. Giá trị `false` trong tình huống đầy không mang nghĩa “A đã trùng nên bị từ chối”.

## 4. Xem hai đầu: get và peek không xóa dữ liệu

Với `[A, B, C]`:

```text
getFirst()  → A
peekFirst() → A

getLast()   → C
peekLast()  → C

deque sau các lần xem: [A, B, C]
size vẫn là 3
```

Khác biệt chỉ xuất hiện khi deque rỗng:

- `getFirst()`, `getLast()`: ném `NoSuchElementException`.
- `peekFirst()`, `peekLast()`: trả `null`.

Khi deque chỉ có `[B]`, cả đầu trước lẫn đầu sau đều là cùng phần tử `B`. Đây không phải hai bản sao. Lấy/xóa phần tử duy nhất ở một phía sẽ làm cả deque rỗng.

Phương thức xem trả về tham chiếu tới phần tử, không tự tạo một bản sao sâu của phần tử. “Không xóa” nói về thao tác của deque; nó không biến một đối tượng phần tử có thể sửa đổi thành bất biến.

Nếu muốn liên tục xử lý phần tử tiếp theo, chỉ gọi `peekFirst` trong vòng lặp là chưa đủ: nếu không có thao tác sửa đổi khác, nó vẫn nhìn cùng đầu trước.

## 5. Lấy và xóa ở hai đầu: remove và poll

### 5.1. Xóa đầu nào thì trả phần tử ở đầu đó

Từ `[A, B, C]`:

```text
removeFirst() → trả A; còn [B, C]
pollLast()    → trả C; còn [B]
removeLast()  → trả B; còn []
```

Với thao tác thành công, `removeFirst/removeLast/pollFirst/pollLast`:

- Trả chính phần tử được lấy.
- Loại phần tử đó khỏi deque.
- Làm kích thước giảm `1`.

Chúng không trả `boolean` để báo có thay đổi như một số thao tác xóa theo giá trị.

### 5.2. Chọn cách xử lý rỗng

Khi rỗng là trạng thái bình thường của luồng xử lý, có thể dùng `poll`:

```java
// Đoạn minh họa: values không chứa phần tử null.
String item = values.pollFirst();
if (item == null) {
    System.out.println("Chưa có phần tử để xử lý");
} else {
    System.out.println("Đã lấy: " + item);
}
```

Nếu thuật toán có điều kiện trước bảo đảm phải có phần tử và việc rỗng cần được phát hiện bằng ngoại lệ, một phương thức `remove` có thể diễn đạt yêu cầu đó.

Không bắt ngoại lệ liên tục như một cách mặc định để hỏi deque có phần tử hay không khi API đã cung cấp dạng `poll` phù hợp.

### 5.3. Cẩn thận khi mở hộp giá trị trả về

Với `Deque<Integer>` rỗng:

```java
// Có thể ném NullPointerException do tự mở hộp null:
int item = numbers.pollFirst();
```

`pollFirst` trả `Integer` là `null`; lỗi xảy ra khi chuyển thành `int`. Muốn xử lý trạng thái rỗng, nhận vào `Integer` rồi kiểm tra trước khi mở hộp.

Đừng nhầm lỗi này với `NoSuchElementException` mà `removeFirst` chủ động báo khi rỗng.

## 6. Chương trình đầy đủ: theo dõi các thao tác hai đầu

Lưu toàn bộ mã vào **DequeEndsDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.NoSuchElementException;

public class DequeEndsDemo {
    public static void main(String[] args) {
        Deque<String> values = new ArrayDeque<>();
        values.addLast("B");
        values.addFirst("A");
        System.out.println("offerLast C: " + values.offerLast("C"));
        System.out.println("initial: " + values);

        System.out.println("getFirst: " + values.getFirst());
        System.out.println("getLast: " + values.getLast());
        System.out.println("peekFirst: " + values.peekFirst());
        System.out.println("peekLast: " + values.peekLast());
        System.out.println("after inspections: " + values);
        System.out.println("size: " + values.size());

        System.out.println("removeFirst: " + values.removeFirst());
        System.out.println("after removeFirst: " + values);
        System.out.println("pollLast: " + values.pollLast());
        System.out.println("one element: " + values);
        System.out.println("one-element first: " + values.peekFirst());
        System.out.println("one-element last: " + values.peekLast());
        System.out.println("removeLast: " + values.removeLast());
        System.out.println("empty: " + values.isEmpty());

        System.out.println("empty peekFirst: " + values.peekFirst());
        System.out.println("empty peekLast: " + values.peekLast());
        System.out.println("empty pollFirst: " + values.pollFirst());
        System.out.println("empty pollLast: " + values.pollLast());
        try {
            values.getFirst();
        } catch (NoSuchElementException ex) {
            System.out.println("empty getFirst: NoSuchElementException");
        }
        try {
            values.removeLast();
        } catch (NoSuchElementException ex) {
            System.out.println("empty removeLast: NoSuchElementException");
        }
        try {
            values.offerFirst(null);
        } catch (NullPointerException ex) {
            System.out.println("null offerFirst: NullPointerException");
        }
    }
}
```

Biên dịch theo mức Java 17 và chạy:

```shell
javac --release 17 -encoding UTF-8 DequeEndsDemo.java
java DequeEndsDemo
```

Stdout:

```text
offerLast C: true
initial: [A, B, C]
getFirst: A
getLast: C
peekFirst: A
peekLast: C
after inspections: [A, B, C]
size: 3
removeFirst: A
after removeFirst: [B, C]
pollLast: C
one element: [B]
one-element first: B
one-element last: B
removeLast: B
empty: true
empty peekFirst: null
empty peekLast: null
empty pollFirst: null
empty pollLast: null
empty getFirst: NoSuchElementException
empty removeLast: NoSuchElementException
null offerFirst: NullPointerException
```

Cách đọc kết quả:

1. `addLast("B")` rồi `addFirst("A")` xác định rõ vị trí của từng phần tử.
2. `offerLast("C")` thành công và nối `C` ở cuối.
3. Các lần `get` và `peek` không thay đổi dãy hoặc kích thước.
4. Xóa đầu trước lấy `A`; xóa đầu sau lấy `C`.
5. Khi chỉ còn `B`, xem ở hai phía đều nhận `B`.
6. Khi rỗng, các phương thức `peek/poll` trả `null`; các phương thức `get/remove` tương ứng có thể báo `NoSuchElementException`.
7. `ArrayDeque` từ chối `null` bằng ngoại lệ ngay cả khi dùng `offerFirst`. Tên `offer` không làm phần tử không hợp lệ trở nên hợp lệ.

Trong các dòng in deque, đầu trước nằm ở bên trái, đầu sau nằm ở bên phải.

## 7. Deque dùng như Queue: thêm cuối, lấy đầu

`Deque` mở rộng `Queue`. Các phương thức hàng đợi có sẵn không chọn đầu một cách tùy ý; chúng có ánh xạ rõ:

| Phương thức Queue trên Deque | Đầu và thao tác tương ứng |
| --- | --- |
| `add(e)` | Thêm cuối như addLast |
| `offer(e)` | Thêm cuối như offerLast |
| `remove()` | Lấy/xóa đầu trước như removeFirst |
| `poll()` | Lấy/xóa đầu trước như pollFirst |
| `element()` | Xem đầu trước như getFirst |
| `peek()` | Xem đầu trước như peekFirst |

Lưu ý khác biệt chữ ký: `add(e)` trả `boolean`, trong khi `addLast(e)` trả `void`. Bảng mô tả vị trí và ý nghĩa thao tác, không có nghĩa mọi chữ ký giống hệt nhau.

Cách dùng FIFO điển hình:

```java
Deque<String> pending = new ArrayDeque<>();
pending.offerLast("A");
pending.offerLast("B");
pending.offerLast("C");

String first = pending.pollFirst(); // A
```

Nếu những người dùng cùng deque đều giữ quy tắc thêm cuối/lấy đầu, phần tử vào trước được lấy trước.

Không thể dùng thêm ở cả hai đầu tùy ý rồi suy ra dãy vẫn phản ánh một lịch sử FIFO duy nhất. Cần thống nhất quy tắc sử dụng. [Deque: ánh xạ Queue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)

## 8. Deque dùng như ngăn xếp: thêm và lấy cùng một đầu

Một cách dùng ngăn xếp:

```java
Deque<String> stack = new ArrayDeque<>();
stack.push("A");
stack.push("B");
stack.push("C");

String top = stack.pop(); // C
```

Các phương thức trên `Deque`:

| Phương thức | Tương ứng | Khi rỗng hoặc thiếu chỗ |
| --- | --- | --- |
| `push(e)` | `addFirst(e)` | Có thể báo IllegalStateException nếu không thêm được do giới hạn |
| `pop()` | `removeFirst()` | NoSuchElementException nếu rỗng |
| `peek()` | `peekFirst()` | null nếu rỗng |

Sau ba lần `push`, dãy nhìn từ đầu trước là `[C, B, A]`. `pop` lấy `C`, tức phần tử được đẩy vào gần nhất.

Trong cả cách dùng FIFO lẫn ngăn xếp, `peek()` của `Deque` đều nhìn đầu trước. Nó không tự đổi sang nhìn đầu sau khi người dùng gọi biến là `stack`.

Nếu muốn dùng ngăn xếp nhưng xử lý rỗng bằng `null`, có thể dùng `pollFirst` thay cho `pop` theo yêu cầu. Cần chọn rõ cách báo rỗng, không chỉ đổi tên biến.

Tài liệu `Deque` khuyến nghị dùng giao diện này cho cách dùng ngăn xếp thay vì lớp `Stack` cũ. [Deque: cách dùng LIFO](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)

## 9. Chương trình đầy đủ: ánh xạ phương thức và deque có giới hạn

Lưu mã vào **DequePoliciesAndCapacityDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.concurrent.LinkedBlockingDeque;

public class DequePoliciesAndCapacityDemo {
    public static void main(String[] args) {
        Deque<Integer> fifo = new ArrayDeque<>();
        fifo.offer(10);
        fifo.add(20);
        fifo.offerLast(30);
        System.out.println("queue aliases: " + fifo);
        System.out.println("queue peek: " + fifo.peek());
        System.out.println("queue element: " + fifo.element());
        System.out.println("queue poll: " + fifo.poll());
        System.out.println("queue remove: " + fifo.remove());
        System.out.println("queue remaining: " + fifo);

        Deque<String> stack = new ArrayDeque<>();
        stack.push("A");
        stack.push("B");
        stack.push("C");
        System.out.println("stack, first on left: " + stack);
        System.out.println("stack peek: " + stack.peek());
        System.out.println("stack pop: " + stack.pop());
        System.out.println("stack remaining: " + stack);

        Deque<String> bounded = new LinkedBlockingDeque<>(2);
        System.out.println("bounded offerLast A: " + bounded.offerLast("A"));
        System.out.println("bounded offerFirst B: " + bounded.offerFirst("B"));
        System.out.println("bounded full: " + bounded);
        System.out.println("full offerFirst X: " + bounded.offerFirst("X"));
        System.out.println("full offerLast Y: " + bounded.offerLast("Y"));
        try {
            bounded.addFirst("X");
        } catch (IllegalStateException ex) {
            System.out.println("full addFirst: IllegalStateException");
        }
        try {
            bounded.addLast("Y");
        } catch (IllegalStateException ex) {
            System.out.println("full addLast: IllegalStateException");
        }
        System.out.println("bounded after failures: " + bounded);
        System.out.println("bounded pollFirst: " + bounded.pollFirst());
        System.out.println("offerLast C after removal: " + bounded.offerLast("C"));
        System.out.println("bounded final: " + bounded);

        Deque<String> growing = new ArrayDeque<>(2);
        growing.addLast("A");
        growing.addLast("B");
        growing.addLast("C");
        System.out.println("ArrayDeque with initial hint 2: " + growing);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 DequePoliciesAndCapacityDemo.java
java DequePoliciesAndCapacityDemo
```

Stdout:

```text
queue aliases: [10, 20, 30]
queue peek: 10
queue element: 10
queue poll: 10
queue remove: 20
queue remaining: [30]
stack, first on left: [C, B, A]
stack peek: C
stack pop: C
stack remaining: [B, A]
bounded offerLast A: true
bounded offerFirst B: true
bounded full: [B, A]
full offerFirst X: false
full offerLast Y: false
full addFirst: IllegalStateException
full addLast: IllegalStateException
bounded after failures: [B, A]
bounded pollFirst: B
offerLast C after removal: true
bounded final: [A, C]
ArrayDeque with initial hint 2: [A, B, C]
```

Cách đọc từng nhóm:

1. `offer`, `add` và `offerLast` đều đưa phần tử vào cuối trong phần dùng hàng đợi.
2. `peek` và `element` nhìn đầu trước; `poll` và `remove()` lấy từ đầu trước.
3. `push` thêm đầu trước, nên thứ tự hiển thị ngăn xếp là `[C, B, A]`.
4. `LinkedBlockingDeque<>(2)` đã đầy sau hai lần thêm thành công.
5. Cả hai phía đều không nhận thêm bằng `offer` khi đầy, kết quả là `false`.
6. Cả hai dạng `add` báo `IllegalStateException` trong trạng thái đầy.
7. Các lần thêm thất bại không đưa `X` hoặc `Y` vào dãy.
8. Sau khi lấy `B`, thêm `C` vào cuối thành công.
9. `new ArrayDeque<>(2)` vẫn nhận được ba phần tử, chứng minh tham số đó không phải giới hạn tối đa hai phần tử.

Trong ví dụ, `LinkedBlockingDeque` chỉ được dùng một luồng để minh họa thiếu dung lượng. Các phương thức `offerFirst(e)` và `offerLast(e)` một đối số vẫn là thử thêm ngay, không tự chờ có chỗ chỉ vì tên lớp có chữ `Blocking`.

`BlockingDeque` có các phương thức chờ hoặc có thời hạn riêng, chẳng hạn `putFirst`, `putLast`, `takeFirst`, `takeLast` và các overload tương ứng. Đó là khả năng bổ sung, không thay đổi ý nghĩa của mười hai phương thức cơ bản. [BlockingDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingDeque.html)

Hai chương trình độc lập trong bài đã được biên dịch bằng `--release 17` và chạy để đối chiếu đúng stdout. Tùy chọn này kiểm tra mức ngôn ngữ/API và tạo bytecode tương thích Java 17; nó không khẳng định JVM thực thi chính là JDK 17.

## 10. Phân biệt xóa ở đầu với tìm và xóa theo giá trị

Tên gần giống nhau có thể diễn đạt những công việc khác:

| Lời gọi | Ý nghĩa |
| --- | --- |
| `removeFirst()` | Lấy/xóa phần tử đang ở đầu trước |
| `removeLast()` | Lấy/xóa phần tử đang ở đầu sau |
| `removeFirstOccurrence(x)` | Tìm lần xuất hiện đầu tiên của giá trị x theo chiều trước tới sau rồi xóa |
| `removeLastOccurrence(x)` | Tìm lần xuất hiện cuối cùng của giá trị x rồi xóa |
| `remove(x)` có đối số | Trên Deque, xóa lần xuất hiện đầu tiên của x |
| `remove()` không đối số | Lấy/xóa đầu trước |

Ví dụ với các bản sao cấu trúc riêng cùng bắt đầu từ `[A, B, A, C]`:

```text
removeFirst()              → trả A; còn [B, A, C]
removeFirstOccurrence("B") → trả true; còn [A, A, C]
removeLastOccurrence("A")  → trả true; còn [A, B, C]
```

Các phương thức `Occurrence` không bắt buộc chỉ xóa đúng ở đầu trước hoặc đầu sau; chúng tìm giá trị trong dãy. Kết quả trả về và chi phí cũng có thể khác thao tác lấy đầu.

Với `Deque<Integer>`, `remove(1)` là xóa giá trị truy vấn `1`, không phải xóa vị trí số 1. Giao diện này không có truy cập/xóa theo chỉ số như `List`. [Deque: các thao tác theo lần xuất hiện](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)

## 11. Duyệt, xem và lấy hết phần tử là ba việc khác nhau

### 11.1. Duyệt không tự xóa

Một vòng `for-each` thông thường trên deque duyệt theo thứ tự từ đầu trước tới đầu sau:

```java
// Đoạn minh họa.
for (String value : values) {
    System.out.println(value);
}
```

Nếu muốn duyệt chiều ngược, `descendingIterator()` cung cấp bộ duyệt từ sau về trước. Nó không tự đảo dãy đang lưu và cũng không tự lấy phần tử ra.

### 11.2. Muốn lấy hết, dùng thao tác lấy/xóa

Với `ArrayDeque<String>` không chứa `null`, xử lý lần lượt từ đầu trước:

```java
String value;
while ((value = values.pollFirst()) != null) {
    System.out.println("Đã lấy: " + value);
}
```

Đoạn này làm deque rỗng khi xử lý hết trong bối cảnh một luồng không có bên khác thêm dữ liệu. Nếu đổi thành `pollLast`, nó lấy từ phía sau.

Chỉ thay `pollFirst` bằng `peekFirst` mà không có thao tác xóa khác có thể làm vòng lặp liên tục gặp cùng một phần tử.

### 11.3. Không sửa cấu trúc tùy tiện qua đường khác trong for-each

Với các triển khai như `ArrayDeque`, đang duyệt bằng một bộ duyệt rồi tự gọi thao tác thêm/xóa đầu có thể vi phạm quy tắc duyệt. Cơ chế fail-fast có thể phát hiện và báo `ConcurrentModificationException`, nhưng không nên dùng việc có hoặc không có ngoại lệ làm bằng chứng tính đúng.

Nếu mục đích là tiêu thụ dãy, một vòng lấy bằng `poll` thường thể hiện ý định rõ hơn. Nếu mục đích là xóa phần tử đang duyệt, dùng cơ chế bộ duyệt hỗ trợ và tuân thủ hợp đồng của nó. [ArrayDeque: bộ duyệt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html)

## 12. Chọn cách dùng và triển khai đúng phạm vi

Một vài câu hỏi thực tế:

| Yêu cầu | Cách chọn thao tác |
| --- | --- |
| Thêm công việc mới vào cuối danh sách chờ | offerLast hoặc addLast tùy chính sách thiếu chỗ |
| Chèn một phần tử vào phía trước theo quy tắc ứng dụng | offerFirst hoặc addFirst |
| Xem công việc tiếp theo mà chưa lấy | peekFirst hoặc getFirst |
| Lấy công việc tiếp theo từ phía trước | pollFirst hoặc removeFirst |
| Lấy phần tử mới nhất được đặt ở cuối | pollLast hoặc removeLast |
| Dùng ngăn xếp đặt đỉnh ở đầu trước | push, pop, peek hoặc các dạng First phù hợp |

Với một luồng và cách dùng deque thông thường, `ArrayDeque` cung cấp các thao tác hai đầu với thời gian hằng số khấu hao cho phần lớn thao tác liên quan, theo mô tả của lớp. Điều đó không có nghĩa mọi phương thức của mọi `Deque`, chẳng hạn tìm một giá trị bên trong, đều O(1).

Nếu cần giới hạn dung lượng hoặc chờ giữa các luồng, phải chọn triển khai và các phương thức tương ứng. `ArrayDeque` không tự đồng bộ cho nhiều luồng cùng sửa. Ngược lại, việc một triển khai hỗ trợ đồng thời cũng không biến một chuỗi nhiều lời gọi rời thành một thao tác nguyên tử của thuật toán.

Ví dụ, “peek rồi poll” là hai lời gọi, không phải một lệnh vừa kiểm tra vừa đặt quyền sở hữu phần tử. Chọn thao tác lấy trực tiếp và xử lý kết quả thường giúp mô tả rõ công việc cần làm.

Không suy ra từ việc dữ liệu nằm trong deque rằng nó đã được sắp xếp, loại trùng hoặc có quyền ưu tiên tự động. Các tính chất đó cần một mô hình hoặc quy tắc riêng.

## 13. Những lỗi thường gặp

| Cách hiểu hoặc cách viết | Vấn đề | Cách sửa |
| --- | --- | --- |
| Nhầm First/Last là nhỏ nhất/lớn nhất | Đó là vị trí hai đầu, không phải thứ tự giá trị | Vẽ dãy với first bên trái, last bên phải |
| Gán addFirst vào boolean | Phương thức trả void | Dùng offerFirst nếu cần cờ |
| Gọi get rồi mong phần tử biến mất | Get chỉ xem | Dùng remove hoặc poll để lấy/xóa |
| Dùng peek trong vòng lặp mà không xóa | Có thể nhìn cùng phần tử mãi | Dùng poll khi cần tiêu thụ |
| Nghĩ poll và remove khác đầu lấy | Cùng đầu tương ứng; khác cách báo rỗng | Tách lựa chọn đầu và lựa chọn báo lỗi |
| Nghĩ offer không bao giờ ném ngoại lệ | Phần tử không hợp lệ vẫn có thể gây lỗi | Phân biệt thiếu chỗ với vi phạm miền dữ liệu |
| Nghĩ ArrayDeque(2) chỉ chứa được hai phần tử | Nhầm dung lượng khởi tạo với giới hạn tối đa | Đọc hợp đồng triển khai |
| Gọi peek() để xem đầu sau | Peek của Deque nhìn đầu trước | Dùng peekLast |
| Nghĩ push thêm vào cuối | Push tương ứng addFirst | Xác định vị trí đỉnh ngăn xếp |
| Nhầm removeFirst với removeFirstOccurrence | Một bên lấy đầu, một bên tìm giá trị | Đọc đủ tên và chữ ký |
| Gán poll của Integer vào int khi có thể rỗng | Tự mở hộp null | Kiểm tra Integer trước |
| Dùng null như dữ liệu khi cũng dùng null làm dấu rỗng | Kết quả trở nên mơ hồ, một số lớp còn từ chối | Giữ miền phần tử không null khi phù hợp |

Để tự kiểm tra một dòng mã, hãy trả lời ba câu: đang tác động đầu nào, có thay đổi dãy không, và khi không thực hiện được sẽ nhận ngoại lệ hay một giá trị đặc biệt?

## 14. Tự luyện và đối chiếu

### Bài 1: theo dõi dãy sau từng thao tác

Bắt đầu với deque rỗng:

```java
values.addLast("B");
values.addFirst("A");
values.offerLast("C");
values.offerFirst("X");
values.peekLast();
values.pollFirst();
values.removeLast();
```

Đối chiếu:

| Bước | Giá trị trả về cần chú ý | Dãy sau bước |
| --- | --- | --- |
| addLast B | void | `[B]` |
| addFirst A | void | `[A, B]` |
| offerLast C | true | `[A, B, C]` |
| offerFirst X | true | `[X, A, B, C]` |
| peekLast | C | `[X, A, B, C]` |
| pollFirst | X | `[A, B, C]` |
| removeLast | C | `[A, B]` |

### Bài 2: một phần tử và rỗng

Deque chỉ có `[7]`. Hãy dự đoán:

```text
peekFirst() → 7
peekLast()  → 7
pollLast()  → 7; deque rỗng
pollFirst() → null
getLast()   → NoSuchElementException
```

Giải thích vì sao xem ở hai đầu không có nghĩa đang có hai phần tử 7.

### Bài 3: chọn theo tình huống

1. Muốn thử thêm vào phía trước, đầy thì xử lý bằng một nhánh boolean: `offerFirst`.
2. Muốn xem phía sau, rỗng là trạng thái bình thường: `peekLast`.
3. Muốn lấy phía trước, rỗng là lỗi cần phát hiện bằng ngoại lệ: `removeFirst`.
4. Muốn lấy phía sau, rỗng thì nhận dấu không có kết quả: `pollLast`.

### Bài 4: phân biệt FIFO và ngăn xếp

Đưa A, B, C vào cuối rồi lấy đầu trước: A, B, C.

Đưa A, B, C bằng push rồi lấy bằng pop: C, B, A.

Cùng một kiểu `ArrayDeque` có thể phục vụ hai cách dùng. Các đầu được chọn mới quyết định chính sách.

### Bài 5: giới hạn dung lượng

Một `LinkedBlockingDeque<String>` dung lượng 2 đang có `[A, B]`.

- `offerLast("C")`: false, dãy giữ nguyên.
- `addFirst("C")`: IllegalStateException, không đưa C vào dãy.
- `pollLast()`: trả B, còn `[A]`.
- `offerFirst("C")`: true, thành `[C, A]`.

Không đổi sang một phương thức chờ nếu yêu cầu của bài chỉ là thử thêm ngay và xử lý kết quả.

## 15. Tài liệu tra cứu

- [Deque Java 17 — các thao tác hai đầu và ánh xạ Queue/ngăn xếp](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)
- [ArrayDeque Java 17 — dung lượng có thể tăng, null và bộ duyệt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html)
- [LinkedBlockingDeque Java 17 — giới hạn dung lượng và các phương thức hai đầu](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html)
- [BlockingDeque Java 17 — phân biệt thử ngay với thao tác chờ](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingDeque.html)
