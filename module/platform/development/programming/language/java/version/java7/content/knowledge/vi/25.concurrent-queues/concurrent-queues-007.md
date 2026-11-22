# ConcurrentLinkedDeque cho thao tác hai đầu — Java Concurrent

## 1. Vì sao cần một deque đồng thời hai đầu?

Trong một chương trình nhiều luồng, đôi khi nhiệm vụ mới phải được thêm vào **đầu** hoặc **cuối** hàng đợi, và nhiều workers có thể lấy công việc từ **cả hai đầu**. Ví dụ: một hàng đợi công việc ưu tiên đơn giản (đầu là việc được xử lý sớm hơn), lịch sử thao tác có thể lấy mới nhất/cũ nhất, hoặc một pipeline mà nhiều producer và consumer chia sẻ một cấu trúc nhận–phát dữ liệu.

`java.util.concurrent.ConcurrentLinkedDeque<E>` là **deque không giới hạn dung lượng cố định** (*unbounded*), dựa trên các nút liên kết và được thiết kế cho truy cập **concurrent** từ nhiều threads. Cấu trúc này có từ **Java 7**, vẫn được hỗ trợ trong Java hiện hành. Các thao tác thêm/lấy ở mỗi đầu không đòi caller bọc toàn bộ deque bằng một `synchronized` lock chung.

~~~text
                    ConcurrentLinkedDeque
  Head / front                                     Tail / back
       |                                                |
       v                                                v
    [A] <-> [B] <-> [C] <-> [D] <-> [E]
       ^                                 ^              ^
  addFirst / pollFirst                     addLast / pollLast
  offerFirst / peekFirst                   offerLast / peekLast

Thao tác tại đầu và cuối có thể được gọi từ những threads khác nhau.
~~~

**Điểm cần phân biệt ngay:**

- **Thread-safe:** các hoạt động chèn/lấy/truy cập deque được thư viện phối hợp an toàn khi nhiều threads cùng dùng.
- **Non-blocking deque:** `pollFirst()` / `pollLast()` **không đợi** phần tử xuất hiện. Nếu rỗng tại thời điểm thao tác, chúng trả `null`.
- **Unbounded:** không có tham số capacity trong `ConcurrentLinkedDeque`; việc chèn không cung cấp backpressure mặc định. *Unbounded không phải RAM vô hạn.*
- **Two-ended:** `addFirst` và `addLast`, `pollFirst` và `pollLast` đều có, không chỉ FIFO một chiều.
- **Không phải transaction:** một chuỗi `peek() → xử lý → poll()` **không nguyên tử**. Các threads khác có thể xen vào.
- **Không có snapshot iterator:** iterator và spliterator *weakly consistent* khi có sửa đổi đồng thời.
- **Không nên dùng `size()` làm điều kiện đồng bộ:** tính kích thước phải duyệt các nút, có thể sai khi deque đang thay đổi.

**Tương thích:** Các ví dụ độc lập trong bài đã được biên dịch với `javac -encoding UTF-8 --release 17` và chạy trên JDK 17. Nội dung đối chiếu API Oracle Java SE 26 (hiện hành) và SE 17. Dùng đúng những kiến thức Java còn áp dụng; không dựa vào API legacy.

## 2. Deque, Queue và Stack: cùng một cấu trúc, nhiều cách sử dụng

`Deque` viết tắt của **double-ended queue** — hàng đợi hai đầu. Một `ConcurrentLinkedDeque<E>` triển khai `Deque<E>` và có thể được dùng như:

- **Queue (FIFO):** producer thêm vào cuối với `offerLast`; consumer lấy ở đầu với `pollFirst`.
- **Stack (LIFO):** thêm vào đầu với `push` / `addFirst` và lấy ở đầu với `pop` / `pollFirst`.
- **Two-ended queue:** producer hoặc consumer thao tác ở cả hai phía theo giao thức ứng dụng.

Không phải cứ dùng `pollLast` ở một thread là đã có “work stealing” giống bộ lập lịch của `ForkJoinPool`. Một deque chia sẻ có thể là thành phần của lịch công việc; **work-stealing scheduler** còn có chính sách ownership, lấy trộm công việc, task scheduling và quản lý hiệu năng riêng.

### 2.1. API hai đầu và hành vi khi rỗng

| Mục đích | Đầu (first) | Cuối (last) | Khi rỗng |
| --- | --- | --- | --- |
| Thêm | `addFirst(e)` | `addLast(e)` | Không áp dụng |
| Thêm trả boolean | `offerFirst(e)` | `offerLast(e)` | `true` nếu chèn thành công; không có capacity quota nội bộ |
| Xem nhưng không lấy | `peekFirst()` | `peekLast()` | Trả `null` |
| Xem, yêu cầu có phần tử | `getFirst()` | `getLast()` | Ném `NoSuchElementException` |
| Lấy và xóa | `pollFirst()` | `pollLast()` | Trả `null` |
| Lấy và xóa, yêu cầu có | `removeFirst()` | `removeLast()` | Ném `NoSuchElementException` |
| Xóa theo giá trị | `removeFirstOccurrence(o)` | `removeLastOccurrence(o)` | Trả `false` nếu không có giá trị |
| Duyệt | `iterator()` | `descendingIterator()` | Iterator rỗng |

**Quy tắc chọn:** Với consumer concurrent, thường ưu tiên `pollFirst()` / `pollLast()` vì một consumer khác có thể lấy phần tử cuối cùng trước bạn. Một `getFirst()` hoặc `removeFirst()` có thể ném exception khi rỗng; chỉ dùng kiểu này khi bạn thực sự muốn **rỗng được coi là lỗi**.

### 2.2. Những phương thức tương đương theo Queue/Stack

| Phương thức | Ý nghĩa tại ConcurrentLinkedDeque |
| --- | --- |
| `add(e)` / `offer(e)` | Thêm cuối — tương đương `addLast(e)` / `offerLast(e)` |
| `poll()` / `remove()` | Lấy và xóa đầu — tương đương `pollFirst()` / `removeFirst()` |
| `peek()` / `element()` | Xem đầu — tương đương `peekFirst()` / `getFirst()` |
| `push(e)` | Thêm đầu — tương đương `addFirst(e)` |
| `pop()` | Lấy và xóa đầu — tương đương `removeFirst()` |
| `remove(o)` | Xóa occurrence đầu tiên bằng `equals` |
| `iterator()` | Thường duyệt theo thứ tự first → last |
| `descendingIterator()` | Thường duyệt theo last → first |

**Lưu ý về lời gọi `remove`:** `remove()` **không đối số** là lấy phần tử đầu (ném lỗi nếu rỗng); `remove(Object o)` là xóa một phần tử **bằng giá trị**. Hai overload này có ý nghĩa khác nhau.

### 2.3. Không hỗ trợ null

`ConcurrentLinkedDeque` cấm giá trị `null`. Gọi `addFirst(null)`, `offerLast(null)` hoặc `push(null)` sẽ ném `NullPointerException`. Nhờ thế `pollFirst() == null` / `pollLast() == null` có ý nghĩa rõ là **không lấy được phần tử**.

Nếu domain thực sự có dữ liệu “vắng giá trị”, hãy biểu diễn nó bằng object chuyên biệt, `Optional` trong payload thích hợp, hoặc một dạng message có type rõ ràng, không dùng `null` làm item trong deque.

## 3. Cơ chế concurrent không đồng nghĩa mọi chuỗi lệnh đều nguyên tử

Một lần gọi `offerFirst` hoặc `pollLast` hoạt động theo hợp đồng concurrent collection. Nhưng **kết hợp nhiều method calls là câu chuyện khác**:

~~~java
if (!deque.isEmpty()) {
    E item = deque.pollFirst(); // Có thể là null!
}
~~~

Đây là đoạn **minh họa chưa độc lập** trong một method có `Deque<E> deque`. Thread khác có thể lấy phần tử cuối giữa `isEmpty()` và `pollFirst()`. Đúng hơn:

~~~java
E item = deque.pollFirst();
if (item != null) {
    process(item);
}
~~~

Đây cũng là mã minh họa; `process` phải do ứng dụng định nghĩa. **Một lần `pollFirst` là thao tác quyết định** xem consumer nào nhận phần tử. Không dùng `peekFirst` để “đặt trước” phần tử vì peek không giữ khóa hay quyền sở hữu.

### 3.1. Không cần thêm synchronized vô cớ quanh từng offer/poll

Nếu mục tiêu chỉ là thread-safe insertion/removal, `ConcurrentLinkedDeque` đã hỗ trợ. Thêm một `synchronized(deque)` cho **tất cả** operations có thể làm mất lợi ích concurrent access và gây lock contention không cần thiết. Nhưng nếu domain yêu cầu một **transaction nhiều bước** (ví dụ kiểm tra điều kiện trên nhiều phần tử, di chuyển atomically giữa hai collections), chỉ dùng deque không cung cấp transaction đó; cần thiết kế synchronization khác.

### 3.2. Ordering và scheduling

- Trong trạng thái không có thay đổi đồng thời, `addFirst`/`addLast` và `pollFirst`/`pollLast` theo thứ tự hai đầu mong đợi.
- Khi nhiều producers cùng offer, thứ tự toàn cục phụ thuộc thứ tự các operations thực sự được thực hiện, **không** phụ thuộc id thread hay thứ tự bạn gọi `submit`.
- Dùng `pollLast` trong lúc một producer `addFirst` liên tục có thể tạo hành vi ưu tiên khác FIFO; cần kiểm soát starvation/fairness ở tầng ứng dụng.
- Deque không tự đặt priority number, deadline, fairness guarantee hay retry policy cho từng phần tử.

## 4. Bộ ví dụ Java 17+ có thể chạy độc lập

Các chương trình dưới đây đều có tên file trùng với `public class`. Với mỗi ví dụ, lưu nguyên đoạn `java` vào file tương ứng, rồi chạy đúng hai lệnh `javac` và `java`. Output đã kiểm tra trực tiếp trên JDK 17; phần thứ tự thread không được dùng làm output cố định.

Các ví dụ mô phỏng concurrency dùng `ExecutorService`, `Future.get(timeout)` và cleanup trong `finally`. Những lớp tạo dữ liệu lớn chỉ là **test chức năng**, không phải benchmark tốc độ.

## 5. Ví dụ 1 — Thêm, xem và lấy phần tử ở hai đầu

Ví dụ cơ bản nhất: tạo thứ tự `[START, A, B, C, D]` bằng các operations hai đầu, sau đó lấy một phần tử ở mỗi đầu. Các thao tác trong demo là tuần tự để dễ kiểm tra nghĩa của API.

Tạo file `TwoEndsDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;
public class TwoEndsDemo {
 public static void main(String[] args){
  ConcurrentLinkedDeque<String> q=new ConcurrentLinkedDeque<>();
  q.addFirst("B");q.addFirst("A");q.addLast("C");
  System.out.println("offerLast="+q.offerLast("D"));
  System.out.println("offerFirst="+q.offerFirst("START"));
  System.out.println("all="+new ArrayList<>(q));
  System.out.println("first="+q.peekFirst());
  System.out.println("last="+q.peekLast());
  System.out.println("removedFirst="+q.pollFirst());
  System.out.println("removedLast="+q.pollLast());
  System.out.println("remaining="+new ArrayList<>(q));
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 TwoEndsDemo.java
java TwoEndsDemo
~~~

Stdout đã được kiểm chứng:

~~~text
offerLast=true
offerFirst=true
all=[START, A, B, C, D]
first=START
last=D
removedFirst=START
removedLast=D
remaining=[A, B, C]
~~~

**Giải thích:** `addFirst(B)` rồi `addFirst(A)` đưa A lên trước B. `offerLast(D)` và `offerFirst(START)` thêm ở phía tương ứng. `peekFirst/peekLast` **không xóa**, còn `pollFirst/pollLast` lấy và xóa. `new ArrayList<>(q)` ở đây chỉ để hiển thị khi không có writer concurrent; nếu có modifications đồng thời, không coi bản sao là snapshot nguyên tử.

## 6. Ví dụ 2 — Phân biệt null khi rỗng với exception

Học cách chọn `poll/peek` so với `remove/get`. Đồng thời xác nhận `null` không hợp lệ làm item: gọi `push(null)` / `offerLast(null)` phải ném `NullPointerException`.

Tạo file `EmptyContractsDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;
public class EmptyContractsDemo{
 public static void main(String[] args){
  ConcurrentLinkedDeque<String> q=new ConcurrentLinkedDeque<>();
  System.out.println("pollFirstEmpty="+q.pollFirst());
  System.out.println("pollLastEmpty="+q.pollLast());
  System.out.println("peekFirstEmpty="+q.peekFirst());
  System.out.println("peekLastEmpty="+q.peekLast());
  boolean getFirstThrows=false,removeLastThrows=false,pushNullThrows=false,offerNullThrows=false;
  try{q.getFirst();}catch(NoSuchElementException e){getFirstThrows=true;}
  try{q.removeLast();}catch(NoSuchElementException e){removeLastThrows=true;}
  try{q.push(null);}catch(NullPointerException e){pushNullThrows=true;}
  try{q.offerLast(null);}catch(NullPointerException e){offerNullThrows=true;}
  System.out.println("getFirstThrows="+getFirstThrows);
  System.out.println("removeLastThrows="+removeLastThrows);
  System.out.println("pushNullThrows="+pushNullThrows);
  System.out.println("offerNullThrows="+offerNullThrows);
  System.out.println("isEmpty="+q.isEmpty());
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 EmptyContractsDemo.java
java EmptyContractsDemo
~~~

Stdout đã được kiểm chứng:

~~~text
pollFirstEmpty=null
pollLastEmpty=null
peekFirstEmpty=null
peekLastEmpty=null
getFirstThrows=true
removeLastThrows=true
pushNullThrows=true
offerNullThrows=true
isEmpty=true
~~~

**Giải thích:** Khi không có item, các lệnh `peek/poll` trả `null` mà không phải ngoại lệ; các lệnh `get/remove` tương ứng ném `NoSuchElementException`. Đừng gán ý nghĩa `null` là một payload hợp lệ, vì cấu trúc không chứa null.

## 7. Ví dụ 3 — Một deque hỗ trợ FIFO và LIFO

So sánh aliases của `Queue` (thêm cuối, lấy đầu) với aliases của `Stack` (push/pop ở đầu).

Tạo file `QueueStackAliasesDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;
public class QueueStackAliasesDemo{
 public static void main(String[] args){
  ConcurrentLinkedDeque<String> q=new ConcurrentLinkedDeque<>();
  q.offer("first");q.add("second");q.offerLast("third");
  System.out.println("queueView="+new ArrayList<>(q));
  System.out.println("pollQueue="+q.poll());
  q.push("top");
  System.out.println("stackView="+new ArrayList<>(q));
  System.out.println("popStack="+q.pop());
  System.out.println("element="+q.element());
  System.out.println("removeQueue="+q.remove());
  System.out.println("peekQueue="+q.peek());
  System.out.println("remaining="+new ArrayList<>(q));
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 QueueStackAliasesDemo.java
java QueueStackAliasesDemo
~~~

Stdout đã được kiểm chứng:

~~~text
queueView=[first, second, third]
pollQueue=first
stackView=[top, second, third]
popStack=top
element=second
removeQueue=second
peekQueue=third
remaining=[third]
~~~

**Giải thích:** `offer/add` thêm vào tail, `poll/remove` lấy head, `push` thêm head, `pop` xóa head. `element` chỉ xem head và ném nếu rỗng; `peek` xem head nhưng trả null nếu rỗng. Khi dùng trên nhiều threads, đừng suy từ thứ tự các println trong một demo tuần tự ra thứ tự thực thi toàn cục.

## 8. Ví dụ 4 — Xóa occurrence đầu và cuối, duyệt ngược

Khi deque có giá trị trùng lặp, `removeFirstOccurrence(x)` và `removeLastOccurrence(x)` xóa những occurrence khác nhau. `descendingIterator` duyệt từ last về first.

Tạo file `OccurrencesDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;
public class OccurrencesDemo{
 public static void main(String[] args){
  ConcurrentLinkedDeque<String> q=new ConcurrentLinkedDeque<>(List.of("a","b","a","c","b"));
  System.out.println("start="+new ArrayList<>(q));
  System.out.println("removedFirstA="+q.removeFirstOccurrence("a"));
  System.out.println("afterFirst="+new ArrayList<>(q));
  System.out.println("removedLastB="+q.removeLastOccurrence("b"));
  System.out.println("afterLast="+new ArrayList<>(q));
  List<String> reversed=new ArrayList<>();
  q.descendingIterator().forEachRemaining(reversed::add);
  System.out.println("reverse="+reversed);
  System.out.println("removedMissing="+q.removeFirstOccurrence("z"));
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 OccurrencesDemo.java
java OccurrencesDemo
~~~

Stdout đã được kiểm chứng:

~~~text
start=[a, b, a, c, b]
removedFirstA=true
afterFirst=[b, a, c, b]
removedLastB=true
afterLast=[b, a, c]
reverse=[c, a, b]
removedMissing=false
~~~

**Giải thích:** Cả hai occurrence methods trả boolean báo có phần tử bị xóa. Chúng không phải lệnh `poll` theo FIFO/LIFO mà phải **tìm kiếm bằng equality**; với nhiều phần tử có thể chi phí đáng kể. Nếu nhiều threads sửa đồng thời, không dùng kết quả một lần tìm/xóa để suy ra trạng thái toàn bộ deque bất biến.

## 9. Ví dụ 5 — Iterator của ConcurrentLinkedDeque hỗ trợ remove

Javadoc của class và iterator triển khai các optional methods của `Deque`/`Iterator`, kể cả `Iterator.remove()`. Ví dụ kiểm tra cả iterator xuôi và ngược khi không có sửa đổi đồng thời.

Tạo file `IteratorRemoveDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;
public class IteratorRemoveDemo {
 public static void main(String[] args){
  ConcurrentLinkedDeque<String> q=new ConcurrentLinkedDeque<>(List.of("a","b","c"));
  Iterator<String> it=q.iterator();
  System.out.println("firstByIterator="+it.next());
  it.remove();
  System.out.println("afterIteratorRemove="+new ArrayList<>(q));
  Iterator<String> desc=q.descendingIterator();
  System.out.println("lastByDescendingIterator="+desc.next());
  desc.remove();
  System.out.println("afterDescendingRemove="+new ArrayList<>(q));
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 IteratorRemoveDemo.java
java IteratorRemoveDemo
~~~

Stdout đã được kiểm chứng:

~~~text
firstByIterator=a
afterIteratorRemove=[b, c]
lastByDescendingIterator=c
afterDescendingRemove=[b]
~~~

**Giải thích:** `Iterator.remove()` loại phần tử cuối cùng mà iterator đã trả; không gọi `remove` trước `next()` hoặc hai lần liên tiếp nếu không có `next()` mới. Đây là test trên deque đứng yên, không khẳng định iterator có snapshot nguyên tử khi đồng thời bị thay đổi.

## 10. Ví dụ 6 — Weakly consistent iterator khi có thread sửa deque

Tạo iterator trước khi một worker khác thêm 100 mục và xóa 50 mục. Không in nội dung mà iterator duyệt, bởi nó **có thể thấy hoặc không thấy** các thay đổi đồng thời; chỉ kiểm tra kết thúc không ném ConcurrentModificationException và trạng thái khi mọi thread đã xong.

Tạo file `WeakIteratorConcurrentDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;
public class WeakIteratorConcurrentDemo {
 public static void main(String[] args)throws Exception{
  ConcurrentLinkedDeque<Integer> q=new ConcurrentLinkedDeque<>();
  for(int i=0;i<100;i++)q.offerLast(i);
  Iterator<Integer> it=q.iterator();
  ExecutorService e=Executors.newSingleThreadExecutor();
  CountDownLatch start=new CountDownLatch(1);
  try{
   Future<?> mutation=e.submit(()->{
    try{start.await();}catch(InterruptedException ex){Thread.currentThread().interrupt();return;}
    for(int i=100;i<200;i++)q.offerLast(i);
    for(int i=0;i<50;i++)q.pollFirst();
   });
   start.countDown();
   while(it.hasNext())it.next();
   mutation.get(5,TimeUnit.SECONDS);
   System.out.println("iteratorCompletedWithoutCME=true");
   System.out.println("mutatorCompleted="+mutation.isDone());
   System.out.println("quiescentRemaining="+q.size());
  }finally{e.shutdownNow();e.awaitTermination(2,TimeUnit.SECONDS);}
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 WeakIteratorConcurrentDemo.java
java WeakIteratorConcurrentDemo
~~~

Stdout đã được kiểm chứng:

~~~text
iteratorCompletedWithoutCME=true
mutatorCompleted=true
quiescentRemaining=150
~~~

**Giải thích:** Iterator weakly consistent **không fail-fast** khi có modifications đồng thời. Nó không khóa deque và không hứa là ảnh chụp trạng thái tại thời điểm tạo. Sau khi mutation future hoàn tất, deque có 100 ban đầu +100 thêm -50 lấy =150 phần tử; lúc đó `size()` được gọi khi không có writer để có số đếm ổn định.

## 11. Ví dụ 7 — Spliterator báo CONCURRENT, ORDERED và NONNULL

Xem các characteristics chính thức của `ConcurrentLinkedDeque.spliterator()` trên JDK 17. `ORDERED` phản ánh thứ tự duyệt; `CONCURRENT` cho phép duyệt đồng thời với thay đổi; `NONNULL` vì phần tử null bị cấm. Không báo `SIZED`.

Tạo file `SpliteratorFlagsDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;
public class SpliteratorFlagsDemo{
 public static void main(String[] args){
  ConcurrentLinkedDeque<String> q=new ConcurrentLinkedDeque<>(List.of("a","b","c"));
  int flags=q.spliterator().characteristics();
  System.out.println("CONCURRENT="+((flags&Spliterator.CONCURRENT)!=0));
  System.out.println("ORDERED="+((flags&Spliterator.ORDERED)!=0));
  System.out.println("NONNULL="+((flags&Spliterator.NONNULL)!=0));
  System.out.println("SIZED="+((flags&Spliterator.SIZED)!=0));
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 SpliteratorFlagsDemo.java
java SpliteratorFlagsDemo
~~~

Stdout đã được kiểm chứng:

~~~text
CONCURRENT=true
ORDERED=true
NONNULL=true
SIZED=false
~~~

**Giải thích:** Không suy ra parallel streams tự động nhanh từ các flags này. Javadoc `trySplit` của implementation cung cấp **limited parallelism**; hiệu năng stream phụ thuộc workload và mức thay đổi concurrent. Không nhầm ORDERED với snapshot hoặc global fairness của producers.

## 12. Ví dụ 8 — Ba producers, bốn consumers lấy ở hai đầu, 1.200 item

Bài concurrency thật dùng hai consumer lấy đầu và hai consumer lấy cuối. Mỗi producer tạo 400 id duy nhất; `ConcurrentHashMap.newKeySet()` xác minh không mất và không trùng, `CountDownLatch` đánh dấu khi tất cả producers đã hoàn tất, `Future.get(timeout)` giám sát tasks.

Tạo file `ProducerConsumerDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.concurrent.locks.*;
public class ProducerConsumerDemo {
 public static void main(String[] args)throws Exception{
  final int producers=3,perProducer=400,consumers=4,expected=producers*perProducer;
  ConcurrentLinkedDeque<Integer> q=new ConcurrentLinkedDeque<>();
  Set<Integer> unique=ConcurrentHashMap.newKeySet();
  AtomicInteger count=new AtomicInteger(),duplicates=new AtomicInteger();
  CountDownLatch producersDone=new CountDownLatch(producers);
  ExecutorService e=Executors.newFixedThreadPool(producers+consumers);
  List<Future<?>> tasks=new ArrayList<>();
  try{
   for(int p=0;p<producers;p++){
    final int producer=p;
    tasks.add(e.submit(()->{
     try{for(int i=0;i<perProducer;i++)q.offerLast(producer*perProducer+i);}
     finally{producersDone.countDown();}
    }));
   }
   for(int c=0;c<consumers;c++){
    final boolean fromFirst=(c%2==0);
    tasks.add(e.submit(()->{
     for(;;){
      Integer value=fromFirst?q.pollFirst():q.pollLast();
      if(value!=null){
       if(!unique.add(value))duplicates.incrementAndGet();
       count.incrementAndGet();
      }else if(producersDone.getCount()==0 && q.isEmpty())break;
      else LockSupport.parkNanos(100_000L);
     }
    }));
   }
   for(Future<?> f:tasks)f.get(20,TimeUnit.SECONDS);
   System.out.println("expected="+expected);
   System.out.println("consumed="+count.get());
   System.out.println("unique="+unique.size());
   System.out.println("duplicates="+duplicates.get());
   System.out.println("allPresent="+(unique.size()==expected));
   System.out.println("empty="+q.isEmpty());
  }finally{e.shutdownNow();e.awaitTermination(2,TimeUnit.SECONDS);}
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 ProducerConsumerDemo.java
java ProducerConsumerDemo
~~~

Stdout đã được kiểm chứng:

~~~text
expected=1200
consumed=1200
unique=1200
duplicates=0
allPresent=true
empty=true
~~~

**Giải thích:** Không dùng `queue.isEmpty()` một mình để xác nhận toàn bộ job đã xong, vì producer có thể offer thêm ngay sau khi consumer thấy rỗng. Chỉ dừng khi **producersDone==0 và deque rỗng**, trong điều kiện **không còn nguồn offer khác**. Thời gian `parkNanos` giúp tránh loop quay 100% CPU trong demo nhưng vẫn là polling; production cần cơ chế chờ/backpressure phù hợp khi không muốn poll.

## 13. Ví dụ 9 — peekFirst rồi pollFirst không phải một transaction

Hai threads cùng xem item duy nhất bằng `peekFirst()` trước một barrier nhân tạo; sau khi cả hai đã xem, cả hai mới gọi `pollFirst()`. Chỉ một thread lấy được, thread còn lại nhận null. Output có thể cố định dù thứ tự thread không xác định.

Tạo file `PeekPollRaceDemo.java`:

~~~java
import java.util.concurrent.*;
public class PeekPollRaceDemo{
 public static void main(String[] args)throws Exception{
  ConcurrentLinkedDeque<Integer> q=new ConcurrentLinkedDeque<>();
  q.add(42);
  CountDownLatch bothPeeked=new CountDownLatch(2);
  ExecutorService e=Executors.newFixedThreadPool(2);
  Callable<Boolean> work=()->{
   Integer peek=q.peekFirst();
   if(peek==null)throw new IllegalStateException("peek should see initial item");
   bothPeeked.countDown();
   if(!bothPeeked.await(5,TimeUnit.SECONDS))throw new TimeoutException("barrier");
   return q.pollFirst()!=null;
  };
  try{
   Future<Boolean> a=e.submit(work),b=e.submit(work);
   boolean x=a.get(5,TimeUnit.SECONDS),y=b.get(5,TimeUnit.SECONDS);
   int successes=(x?1:0)+(y?1:0);
   System.out.println("bothPeekedNonNull=true");
   System.out.println("pollSuccesses="+successes);
   System.out.println("pollMisses="+(2-successes));
   System.out.println("empty="+q.isEmpty());
  }finally{e.shutdownNow();e.awaitTermination(2,TimeUnit.SECONDS);}
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 PeekPollRaceDemo.java
java PeekPollRaceDemo
~~~

Stdout đã được kiểm chứng:

~~~text
bothPeekedNonNull=true
pollSuccesses=1
pollMisses=1
empty=true
~~~

**Giải thích:** Cả hai threads đều có thể xem 42 vì peek không xóa. Khi cùng poll, đúng một lần lấy thành công. Do vậy `if(peekFirst()!=null) { return pollFirst(); }` vẫn phải xử lý `null`; API không khóa/đặt chỗ phần tử giữa hai lời gọi. Phương án tiêu thụ an toàn là **một lần poll**, sau đó kiểm tra kết quả.

## 14. Ví dụ 10 — Happens-before khi truyền object qua deque

Producer ghi các field của object rồi mới offer; consumer ở thread khác poll và đọc các field. Javadoc concurrent collection đảm bảo actions trước đưa object vào deque *happen-before* actions sau truy cập/lấy object đó ở thread khác.

Tạo file `MemoryPublicationDemo.java`:

~~~java
import java.util.concurrent.*;
import java.util.concurrent.locks.*;
public class MemoryPublicationDemo {
 static final class Job{int number;String state;}
 public static void main(String[] args)throws Exception{
  ConcurrentLinkedDeque<Job> q=new ConcurrentLinkedDeque<>();
  ExecutorService e=Executors.newFixedThreadPool(2);
  try{
   Future<String> consumer=e.submit(()->{
    long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(5);
    Job job;
    while((job=q.pollFirst())==null){
     if(System.nanoTime()>=deadline)throw new TimeoutException("consumer");
     LockSupport.parkNanos(100_000L);
    }
    return job.number+":"+job.state;
   });
   Future<?> producer=e.submit(()->{
    Job job=new Job();job.number=42;job.state="ready";q.offerLast(job);
   });
   producer.get(5,TimeUnit.SECONDS);
   System.out.println("payload="+consumer.get(5,TimeUnit.SECONDS));
   System.out.println("empty="+q.isEmpty());
  }finally{e.shutdownNow();e.awaitTermination(2,TimeUnit.SECONDS);}
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 MemoryPublicationDemo.java
java MemoryPublicationDemo
~~~

Stdout đã được kiểm chứng:

~~~text
payload=42:ready
empty=true
~~~

**Giải thích:** `Job` có field không `volatile` nhưng được khởi tạo **trước** khi offer, sau đó consumer lấy và đọc. Đây là **safe publication** qua concurrent collection. Không đồng nghĩa Job trở nên thread-safe nếu producer tiếp tục thay đổi fields **sau** offer mà không đồng bộ.

## 15. Ví dụ 11 — Bulk operations hợp lệ nhưng không nguyên tử với concurrent writers

`addAll` và `removeIf` trong demo được chạy **khi không có writer khác**, nên có kết quả rõ. Khi có operations concurrent, Javadoc không bảo đảm toàn bộ batch được nhìn thấy/xóa như một transaction.

Tạo file `BulkOpsDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;
public class BulkOpsDemo{
 public static void main(String[] args){
  ConcurrentLinkedDeque<Integer> q=new ConcurrentLinkedDeque<>(List.of(2,1,2,3,4));
  System.out.println("addAllChanged="+q.addAll(List.of(5,6)));
  System.out.println("beforeFilter="+new ArrayList<>(q));
  System.out.println("removedEvens="+q.removeIf(x->x%2==0));
  System.out.println("afterFilter="+new ArrayList<>(q));
  int sum=0;for(int x:q)sum+=x;
  System.out.println("sumWhenQuiescent="+sum);
  q.clear();
  System.out.println("emptyAfterClear="+q.isEmpty());
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 BulkOpsDemo.java
java BulkOpsDemo
~~~

Stdout đã được kiểm chứng:

~~~text
addAllChanged=true
beforeFilter=[2, 1, 2, 3, 4, 5, 6]
removedEvens=true
afterFilter=[1, 3, 5]
sumWhenQuiescent=9
emptyAfterClear=true
~~~

**Giải thích:** `addAll`, `removeIf`, `forEach` và các phép duyệt/xóa nhiều phần tử có thể xen kẽ với writer khác; không bảo đảm atomic batch. `clear()` cũng không phải transactional deletion chặn producer mới; sau clear, threads khác vẫn có thể offer. Nếu cần snapshot/transaction nhiều phần tử, phải thêm giao thức đồng bộ ở tầng ứng dụng.

## 16. Ví dụ 12 — size() là O(n), toArray không tự bảo đảm snapshot nguyên tử concurrent

Khi không có writer, số phần tử ổn định và `toArray` trả một mảng độc lập. Nếu đang có concurrent updates, `size()` phải duyệt và có thể trả số đã lỗi thời; `toArray` không được xem là ảnh chụp nguyên tử tại một thời điểm.

Tạo file `SnapshotAndSizeDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;
public class SnapshotAndSizeDemo{
 public static void main(String[] args){
  ConcurrentLinkedDeque<String> q=new ConcurrentLinkedDeque<>(List.of("a","b","c"));
  String[] copy=q.toArray(new String[0]);
  System.out.println("sizeWhenQuiescent="+q.size());
  q.addFirst("z");
  System.out.println("snapshot="+Arrays.toString(copy));
  System.out.println("now="+new ArrayList<>(q));
  System.out.println("sizeAfterAddWhenQuiescent="+q.size());
  System.out.println("snapshotUnchanged="+Arrays.equals(copy,new String[]{"a","b","c"}));
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 SnapshotAndSizeDemo.java
java SnapshotAndSizeDemo
~~~

Stdout đã được kiểm chứng:

~~~text
sizeWhenQuiescent=3
snapshot=[a, b, c]
now=[z, a, b, c]
sizeAfterAddWhenQuiescent=4
snapshotUnchanged=true
~~~

**Giải thích:** Mảng `copy` không tự thay đổi theo deque sau đó. Nhưng demo hoàn toàn tuần tự; không được suy ra `toArray()` có bảo đảm atomic snapshot trong môi trường concurrent. Đừng gọi `size()` liên tục trong hot path để làm capacity/backpressure, bởi nó duyệt nodes và kết quả có thể thay đổi ngay.

## 17. Ví dụ 13 — LinkedBlockingDeque khi cần capacity và đợi dữ liệu

Khác `ConcurrentLinkedDeque` unbounded/non-blocking poll, `LinkedBlockingDeque<>(2)` có capacity 2. `offerLast` trả false khi đầy; timed `pollFirst(timeout)` có thể chờ rồi trả null. Đây là một API lựa chọn khác cho producer–consumer có backpressure.

Tạo file `BlockingContrastDemo.java`:

~~~java
import java.util.concurrent.*;
public class BlockingContrastDemo{
 public static void main(String[] args)throws Exception{
  BlockingDeque<String> q=new LinkedBlockingDeque<>(2);
  System.out.println("offerFirstA="+q.offerFirst("A"));
  System.out.println("offerLastB="+q.offerLast("B"));
  System.out.println("offerWhenFull="+q.offerLast("C"));
  System.out.println("remainingCapacity="+q.remainingCapacity());
  System.out.println("pollFirst="+q.pollFirst());
  System.out.println("pollLast="+q.pollLast());
  System.out.println("timedPollEmpty="+q.pollFirst(30,TimeUnit.MILLISECONDS));
  System.out.println("empty="+q.isEmpty());
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 BlockingContrastDemo.java
java BlockingContrastDemo
~~~

Stdout đã được kiểm chứng:

~~~text
offerFirstA=true
offerLastB=true
offerWhenFull=false
remainingCapacity=0
pollFirst=A
pollLast=B
timedPollEmpty=null
empty=true
~~~

**Giải thích:** `LinkedBlockingDeque` cho `putFirst/putLast` chờ khi đầy và `takeFirst/takeLast` chờ khi rỗng, hoặc timed `offer/poll`. `ConcurrentLinkedDeque` **không** có những lệnh BlockingDeque đó. Nếu phải giới hạn memory và tránh tự polling, chọn bounded BlockingDeque thay vì giả định linked deque tự áp backpressure.

## 18. Ví dụ 14 — Giới hạn công việc chờ bằng Semaphore bên ngoài

Dù ConcurrentLinkedDeque không có capacity tích hợp, ứng dụng có thể tự đặt **admission budget**. Demo dùng hai permits: chỉ offer khi lấy được permit, release khi item được dequeue. Nếu offer thất bại vì exception, phải trả lại permit.

Tạo file `SemaphoreBudgetDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;
public class SemaphoreBudgetDemo{
 static boolean offerLimited(
  ConcurrentLinkedDeque<String> q,Semaphore budget,String value){
  if(!budget.tryAcquire())return false;
  boolean published=false;
  try{q.offerLast(value);published=true;return true;}
  finally{if(!published)budget.release();}
 }
 static String pollRelease(ConcurrentLinkedDeque<String> q,Semaphore budget){
  String item=q.pollFirst();
  if(item!=null)budget.release();
  return item;
 }
 public static void main(String[] args){
  ConcurrentLinkedDeque<String> q=new ConcurrentLinkedDeque<>();
  Semaphore budget=new Semaphore(2);
  System.out.println("offerA="+offerLimited(q,budget,"A"));
  System.out.println("offerB="+offerLimited(q,budget,"B"));
  System.out.println("offerCWhileFull="+offerLimited(q,budget,"C"));
  System.out.println("queued="+new ArrayList<>(q));
  System.out.println("poll="+pollRelease(q,budget));
  System.out.println("offerCAfterPoll="+offerLimited(q,budget,"C"));
  System.out.println("remaining="+new ArrayList<>(q));
  System.out.println("permitsAvailable="+budget.availablePermits());
 }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 SemaphoreBudgetDemo.java
java SemaphoreBudgetDemo
~~~

Stdout đã được kiểm chứng:

~~~text
offerA=true
offerB=true
offerCWhileFull=false
queued=[A, B]
poll=A
offerCAfterPoll=true
remaining=[B, C]
permitsAvailable=0
~~~

**Giải thích:** Semaphore giúp chính sách ứng dụng có tối đa hai **items đang nằm trong deque** nếu **mọi producer/consumer đều đi qua wrapper**. Nó không biến bản thân ConcurrentLinkedDeque thành bounded, không điều phối các lệnh offer trực tiếp từ code khác. Release khi **dequeue**, không phải sau khi **xử lý xong**; nếu muốn giới hạn số jobs cả đang chờ và đang xử lý, phải chuyển thời điểm release tới lúc processing hoàn tất.


## 19. Phân tích sâu về hiệu năng và đặc tính concurrent

### 19.1. Không chặn không có nghĩa là không tốn CPU

`ConcurrentLinkedDeque` dùng thuật toán concurrent dựa trên linked nodes và các thao tác nguyên tử của JDK; không cần một lock lớn chung quanh từng offer/poll. Tuy vậy:

- Mỗi chèn có thể cấp phát hoặc liên kết node, gây allocation/GC pressure.
- Nhiều threads tranh cùng đầu có thể khiến các lần thử cập nhật trạng thái cạnh tranh và retry.
- Không phải mọi đường thực thi của một chương trình dùng deque đều **wait-free**; đừng diễn giải từ “non-blocking collection” thành SLA thời gian tuyệt đối cho mọi lời gọi.
- Khi queue rỗng, `pollFirst()` trả `null` ngay; nó **không tự ngủ/chờ** producer.
- Khi producer nhanh hơn consumer trong thời gian dài, deque có thể phát triển cho tới khi máy thiếu bộ nhớ.
- Dùng hai đầu không bảo đảm fairness giữa workers hay giữa các loại job.

### 19.2. Đo đúng workload

Nếu đo hiệu năng cho producer/consumer:

1. Dùng số producers/consumers phù hợp và cùng workload cho các implementation.
2. Đo cả latency khi rỗng, lượng backlog, throughput items/s, GC, CPU và memory.
3. Phân biệt poll nhanh trả null với thời gian worker *thực sự chờ được công việc*; một vòng lặp quay rất nhanh có thể tiêu CPU mà không tạo ra throughput.
4. Tạo input, threads và startup ngoài timed region nếu mục tiêu là steady-state throughput.
5. Có warmup JVM, nhiều lượt và đo độ biến thiên.
6. Thử cả producer burst, consumer burst, nhiều threads cạnh tranh một đầu và chia hai đầu.
7. Không in log trong hot loop; `System.out.println` tạo contention và chặn I/O.
8. Khi cần microbenchmark JVM đáng tin, dùng **OpenJDK JMH** và thiết kế nhóm worker benchmark không tự gây deadlock.
9. Không khẳng định phiên bản lock-free **luôn** nhanh hơn `LinkedBlockingDeque`; với workload cần blocking/backpressure, so semantics trước.
10. Với hàng đợi dùng work-stealing phức tạp, so với scheduler/executor chuyên dụng thay vì tự xây lại bằng deque chia sẻ nếu không có lý do rõ.

Tham khảo [OpenJDK JMH](https://github.com/openjdk/jmh). Các output trong bài là **kết quả chức năng**, không phải benchmark được chuẩn hóa.

### 19.3. Tại sao size() không phù hợp làm quota?

Javadoc ghi `size()` **không phải O(1)**: phải duyệt các phần tử, khoảng **O(n)** và có thể không chính xác nếu deque thay đổi trong lúc duyệt. Ví dụ:

~~~java
if (deque.size() < 1000) {
    deque.offerLast(job);
}
~~~

Đây là **mã minh họa sai về concurrency** nếu dùng để áp quota: giữa `size()` và `offerLast()`, thread khác có thể offer khiến kích thước vượt 1000. Ngay cả bản thân kết quả size có thể là con số tạm thời khi có concurrent changes.

Nếu cần limit chính xác số queued items, dùng `LinkedBlockingDeque(capacity)` hoặc một admission-control protocol độc lập (như Semaphore), đảm bảo **mọi đường thêm/bớt** đều tuân thủ.

## 20. Phân biệt tính nhất quán của iteration, snapshot và transaction

### 20.1. Weakly consistent iterator là gì?

Khi deque bị sửa đồng thời:

- `iterator()` và `descendingIterator()` có thể tiếp tục duyệt mà **không fail-fast bằng ConcurrentModificationException**.
- Chúng **không khóa** deque và không tạo snapshot nguyên tử ngay khi iterator được tạo.
- Có thể thấy hoặc không thấy những phần tử được thêm/xóa đồng thời, tùy thời điểm.
- Đừng lấy kết quả traversal làm chứng cứ mọi element tồn tại tại đúng **một thời điểm duy nhất**.
- `Iterator.remove()` được hỗ trợ; tuy vậy cần đúng protocol của iterator, không gọi trước `next()`.
- `spliterator()` weakly consistent, có flags `CONCURRENT`, `ORDERED`, `NONNULL`, **không** có `SIZED`.
- Parallel stream trên deque không có nghĩa toàn bộ iterations sẽ là snapshot, cũng không đảm bảo speedup cho workload nhỏ.

### 20.2. Bulk methods không atomic

Các thao tác `addAll`, `removeIf`, `forEach` và các bulk-style traversal/removals **không được đảm bảo nguyên tử**. Ví dụ một thread đang `forEach` trong khi thread khác `addAll` thì có thể thấy **một phần** của batch mới; không coi `addAll` là giao dịch publish toàn bộ danh sách.

Nếu cần xử lý batch nhất quán, có thể:

- Đưa batch vào một **message object duy nhất** thay vì nhiều items rồi publish một lần.
- Quy định writer pause/quiescence trước khi chụp dữ liệu.
- Dùng lock/protocol riêng ở mức ứng dụng nếu cần đa bước nguyên tử.
- Dùng queue/executor trong đó ownership mỗi item được chuyển giao một lần, thay vì iterating live data như một snapshot.

### 20.3. toArray() không giải quyết được tính atomic under concurrency

Trong lúc không có mutations, `toArray` trả một mảng nội dung hiện có. Nhưng nếu các threads thêm/xóa đồng thời, kết quả có thể phản ánh các thời điểm khác nhau theo traversal semantics. Hãy xác định nhu cầu:

- Nếu chỉ muốn snapshot để hiển thị **xấp xỉ**, có thể phù hợp.
- Nếu cần kết quả tài chính, kiểm toán hoặc bất biến nhất quán một thời điểm, phải có phase/quiescence hoặc synchronization contract rõ.
- Nếu cần đảm bảo đã drain hết tất cả items và producers sẽ không thêm nữa, hãy có completion signal riêng như `CountDownLatch`/Futures.

## 21. Hướng xử lý Producer–Consumer đúng

### 21.1. Quy tắc kết thúc không được chỉ dựa vào isEmpty()

Sai:

~~~java
while (!deque.isEmpty()) {
    Object item = deque.pollFirst();
    if (item != null) {
        process(item);
    }
}
~~~

Đây là **mã minh họa chưa độc lập**. Nếu deque đang trống tạm thời nhưng producer sẽ bổ sung item, consumer có thể thoát quá sớm. Cần biết **sẽ không còn producer mới** hoặc có một cơ chế báo kết thúc.

Trong demo 1.200 items:

~~~text
Producer 1,2,3: đăng ký hoàn tất bằng CountDownLatch(3)
Consumer 1,2: pollFirst()
Consumer 3,4: pollLast()

Dừng consumer khi:
  không lấy được item
  AND producersDone.getCount() == 0
  AND deque.isEmpty()

Sau khi toàn bộ Future tasks đã hoàn tất:
  count == 1200
  unique IDs == 1200
  duplicates == 0
  deque empty
~~~

Kết hợp `producersDone==0` là cần thiết vì tất cả producers chỉ countDown **sau khi đã hoàn thành offers**; không còn producer đang bổ sung. Tuy nhiên đây là giao thức phù hợp **chính xác trong test đó**: nếu ứng dụng còn nguồn offers khác, nó không đủ để chứng minh đã hết việc.

### 21.2. Polling và khả năng blocking

Nếu consumer muốn chờ dữ liệu nhưng deque rỗng:

- `ConcurrentLinkedDeque.pollFirst()` trả `null` ngay.
- Consumer có thể retry theo backoff/yield/park nhưng cần giới hạn CPU usage và shutdown signal.
- Nếu nghiệp vụ yêu cầu *chờ có việc*, lựa chọn tự nhiên là `BlockingDeque.takeFirst()/takeLast()` hoặc timed `pollFirst(timeout)`.
- Nếu cần giới hạn backlog, dùng `LinkedBlockingDeque<>(capacity)`.
- Nếu cần chỉ một đầu FIFO nhưng không chờ, cân nhắc `ConcurrentLinkedQueue` để code đơn giản hơn.
- Nếu tất cả thao tác nằm trong một thread, `ArrayDeque` thường đơn giản hơn và tránh overhead concurrent structure.

## 22. So sánh các lựa chọn tương tự

| Cấu trúc | Hai đầu? | Thread-safe? | Chờ khi rỗng? | Bounded? | Khi nên chọn |
| --- | --- | --- | --- | --- | --- |
| `ConcurrentLinkedDeque<E>` | Có | Có | Không | Không có capacity tự đặt | Nhiều threads, thao tác hai đầu, không cần blocking |
| `ConcurrentLinkedQueue<E>` | Không cung cấp hai đầu | Có | Không | Unbounded | Nhiều threads chỉ cần FIFO |
| `LinkedBlockingDeque<E>` | Có | Có | Có với `take/put` hoặc timed APIs | Có constructor capacity | Cần backpressure, bounded buffer, chờ dữ liệu |
| `ArrayDeque<E>` | Có | Không | Không | Tự tăng theo nhu cầu | Một thread hoặc đã có synchronization riêng |

**Chú ý:** `LinkedBlockingDeque()` không truyền capacity cũng được tạo với capacity mặc định rất lớn, nhưng trong production khi cần backpressure hãy dùng `new LinkedBlockingDeque<>(limit)` rõ ràng. `ConcurrentLinkedDeque` không có method `takeFirst()`, `putLast()` hoặc `remainingCapacity()`.

### 22.1. Các tình huống phù hợp

- **Task pool đơn giản:** producers có thể `offerLast`; consumers `pollFirst`. Dùng một completion flag/latch riêng.
- **Ưu tiên thô:** một số nhiệm vụ được `offerFirst` để được lấy trước nếu consumer pollFirst. Không có strict priority guarantee khi nhiều producers/consumers; nếu cần priority chuẩn, cân nhắc `PriorityBlockingQueue` hoặc scheduler riêng.
- **LIFO:** `push`/`pop` khi muốn xử lý items mới trước.
- **Two-ended scavenging:** workers có thể `pollFirst` hoặc `pollLast` theo policy; cần kiểm tra fairness và tính đúng; đừng nhầm với hoàn chỉnh một hệ work-stealing.
- **Window/history:** lưu các phần tử mới ở đầu và loại cũ ở cuối; khi cần giới hạn số lượng chính xác dưới concurrency, phải có synchronization hoặc admission-control protocol.

## 23. Memory consistency: object được publish an toàn

Javadoc ghi: **những actions trong một thread trước khi đưa object vào ConcurrentLinkedDeque happen-before các actions sau khi thread khác truy cập hoặc lấy object đó từ deque.**

Ví dụ:

~~~text
Producer thread:
  Job j = new Job()
  j.state = "READY"
  deque.offerLast(j)  -- publication

Consumer thread:
  Job j = deque.pollFirst()
  nếu j != null: đọc j.state
~~~

Nhờ cơ chế publication của concurrent collection, các writes **trước khi offer** được nhìn thấy theo happens-before ở consumer đã lấy object. Nhưng nếu sau offer producer vẫn thay đổi `j.state` và consumer cũng đọc/ghi field đó, đó là concurrency mới cần giao thức khác; deque không tự đồng bộ **mọi field mutation về sau**.

Thiết kế payload immutable/record khi phù hợp có thể giúp giảm rủi ro. Cũng đừng dùng mutable references được nhiều workers cùng share mà không xác định ownership.

## 24. Kiểm thử concurrency có độ tin cậy

Nên kiểm tra nhiều loại failure:

1. Dữ liệu rỗng, một phần tử, giá trị trùng.
2. `null` rejection, exception trên get/remove khi rỗng.
3. Concurrent producer/consumer nhiều lần, ids duy nhất.
4. So `count == unique.size() == expected`, `duplicates == 0`.
5. Hai consumers tranh phần tử cuối, một `poll` phải trả `null`.
6. Iterator đồng thời với writer không fail-fast; không assert danh sách snapshot cố định.
7. `size()` sau khi writers/consumers hoàn tất, **không** đọc kích thước đang thay đổi rồi coi là invariant.
8. Từ các seed/ids cố định để dễ tái lập.
9. Timeouts và exception propagation qua `Future.get()`.
10. Xác nhận producer completion trước khi consumer cho phép thoát.
11. Giới hạn memory khi producers đột ngột nhanh hơn consumers.
12. Đo queue throughput/latency trên workload thật thay vì suy diễn từ một test đúng.

**Nếu thấy test thi thoảng fail:** điều tra ownership, producerDone signal, double-consume logic, shared mutable payload, error handling và quiescence. Không “chữa race” bằng một `Thread.sleep` có thời gian ngẫu nhiên.

## 25. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gọi `offerLast(null)` | Ném NullPointerException | Dùng payload object hợp lệ |
| Dùng `removeFirst()` trong consumer mà không xử lý rỗng | Ném NoSuchElementException | Dùng `pollFirst()` và check null |
| Kiểm tra `isEmpty` rồi mới poll | Check-then-act race | Dựa trên kết quả **một lần poll** |
| Kiểm tra `peek` rồi nghĩ item được giữ | Thread khác vẫn có thể lấy | `poll` mới giành quyền sở hữu |
| Dừng workers khi deque tạm thời rỗng | Bỏ công việc mà producer sẽ thêm sau | Completion signal riêng |
| Dùng `size()` để giới hạn capacity | O(n), sai dưới concurrent updates | BlockingDeque(capacity)/Semaphore protocol |
| Coi `addAll` là transaction | Reader thấy một phần batch | Đóng gói batch thành một item hoặc có synchronization |
| Dùng iterator như snapshot | Đếm sai hoặc bỏ/thấy thêm concurrent changes | Quiescence hoặc định nghĩa semantics snapshot rõ |
| Coi `toArray` là snapshot nguyên tử | Có thể không tương ứng một thời điểm | Barrier/lock/protocol theo nghiệp vụ |
| Quên `Future.get()` | Lỗi worker có thể không được báo tới coordinator | Thu và kiểm tra Futures |
| Dùng polling loop không nghỉ | Ăn CPU dù không có item | BlockingDeque hoặc backoff |
| Không có giới hạn backlog | Tăng RAM/GC; nguy cơ OOME | Bounded queue/admission budget |
| Dùng `ArrayDeque` chia sẻ không đồng bộ | Data race/corruption | ConcurrentLinkedDeque hoặc synchronization |
| Gọi ConcurrentLinkedDeque là fairness queue | Không có strict scheduling fairness | Policy ở application/scheduler |
| Coi 2 ends là work-stealing scheduler đầy đủ | Thiếu policy/ownership/task control | Dùng executor/scheduler thích hợp |
| Dùng shared mutable payload sau offer | Publication chưa bảo đảm updates về sau | Immutable payload hoặc đồng bộ bổ sung |
| Benchmark bằng println trong hot loop | Timing sai nghiêm trọng | JMH/đo riêng |
| Nghĩ unbounded là vô hạn RAM | Không có backpressure, có thể OOME | Kiểm soát backlog |
| Release permit trước khi thực sự dequeue | Vượt queue budget | Nhất quán admission + removal protocol |
| Quên release permit khi offer lỗi | Rò rỉ permit khiến producers ngừng | try/finally như ví dụ |

## 26. Checklist khi review code production

**API và semantics**

- [ ] Đã chọn đúng đầu nhận/lấy: first hay last?
- [ ] FIFO/LIFO có phù hợp với nghiệp vụ?
- [ ] Dùng `poll/peek` hay `remove/get` theo hợp đồng rỗng?
- [ ] Không đưa null vào deque?
- [ ] Không nhầm `remove()` và `remove(Object)`?
- [ ] Không nhầm `push/pop` với `offerLast/pollFirst`?

**Concurrency**

- [ ] Mỗi job chỉ được một consumer xử lý sau khi poll thành công?
- [ ] Không có check-then-act trước poll?
- [ ] ProducersFinished/Shutdown signal rõ, không chỉ isEmpty?
- [ ] Bản thân payload có owner và memory-visibility contract?
- [ ] Không lấy size/toArray/iterator làm snapshot transaction?
- [ ] Bulk operations có được đánh giá non-atomic không?
- [ ] Iterator weakly consistent được giải thích đúng?
- [ ] Có xử lý exceptions và timeouts từ concurrent workers?

**Hiệu năng và vòng đời**

- [ ] Backlog tối đa và memory budget rõ ràng?
- [ ] Nếu cần blocking/bounded, đã xem LinkedBlockingDeque?
- [ ] Không spin mãi khi rỗng?
- [ ] Executor được shutdown/cleanup có thời hạn?
- [ ] Benchmark lấy đúng workload và có đo variance?
- [ ] Không tạo thêm thread pool mỗi item?
- [ ] Không dùng size() làm hot-path counter?
- [ ] Chỉ chọn hai đầu khi thật sự cần hai đầu?

## 27. Câu hỏi tự kiểm tra

**1. ConcurrentLinkedDeque thuộc API nào?** `java.util.concurrent`, từ Java 7 và vẫn hiện hành.

**2. Có hai đầu không?** Có, first/head và last/tail.

**3. `pollLast()` khi rỗng trả gì?** `null`.

**4. `removeLast()` khi rỗng trả gì?** Ném `NoSuchElementException`.

**5. Có lưu null được không?** Không, ném `NullPointerException`.

**6. FIFO bằng những method nào?** `offerLast` và `pollFirst`.

**7. LIFO bằng những method nào?** `push` và `pop` ở đầu.

**8. `peekFirst` có giữ chỗ phần tử không?** Không.

**9. `peekFirst` rồi `pollFirst` là transaction không?** Không.

**10. Vì sao `size()` có thể tốn chi phí?** Nó duyệt các nodes, không phải O(1).

**11. Khi concurrent updates, size có phải kết quả snapshot chính xác?** Không được bảo đảm.

**12. Iterator có fail-fast bằng ConcurrentModificationException không?** Không; nó weakly consistent.

**13. Iterator có thể xóa phần tử vừa next không?** Có, method `Iterator.remove` được hỗ trợ.

**14. Spliterator báo những flags nào?** CONCURRENT, ORDERED và NONNULL; không báo SIZED.

**15. `addAll` có atomic đối với thread duyệt không?** Không được bảo đảm.

**16. `forEach` có thấy toàn bộ batch mới khi đồng thời addAll không?** Không chắc.

**17. `toArray` khi concurrent updates có phải snapshot nguyên tử không?** Không có bảo đảm đó.

**18. ConcurrentLinkedDeque có method takeFirst không?** Không.

**19. Muốn chờ khi rỗng và giới hạn capacity thì dùng gì?** `LinkedBlockingDeque<>(capacity)`.

**20. Nếu chỉ cần FIFO concurrent, có thể dùng gì?** `ConcurrentLinkedQueue`.

**21. Nếu một thread thao tác hai đầu, có thể dùng gì đơn giản hơn?** `ArrayDeque`.

**22. Để đánh dấu không còn producer, dùng gì?** Ví dụ CountDownLatch/Future completion hoặc protocol tương ứng.

**23. Cần kiểm tra gì trong test nhiều consumers?** Count, uniqueness, duplicates, no missing, final empty.

**24. Có đảm bảo data field được ghi trước khi offer hiển thị ở consumer poll?** Có quan hệ happens-before khi consumer truy cập/lấy object từ deque.

**25. Nếu producer tiếp tục sửa payload sau offer, tự động thread-safe không?** Không.

**26. SemaphoreBudgetDemo giới hạn cái gì?** Số phần tử đã được đưa vào deque nhưng chưa dequeue theo protocol của ví dụ.

**27. Unbounded có nghĩa JVM không hết memory?** Không.

**28. Có thể khẳng định hai đầu luôn nhanh hơn một đầu?** Không; cần benchmark workload.

**29. Vì sao poll trả null dù một producer sẽ sớm offer?** Poll không chờ và chỉ phản ánh thao tác ở thời điểm đó.

**30. Ba nguyên tắc cần nhớ nhất?** **Chọn đúng first/last, xử lý null từ poll, và có completion/backpressure protocol ngoài deque khi cần.**

## 28. Tài liệu chính thức và đọc thêm

- [Oracle Java SE 26 — ConcurrentLinkedDeque](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html): tài liệu chuẩn về unbounded deque, two-ended operations, weakly consistent iterator, size, bulk atomicity và memory consistency.
- [Oracle Java SE 17 — ConcurrentLinkedDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html): API tương ứng các ví dụ chạy bằng JDK 17.
- [Oracle Java SE 7 — ConcurrentLinkedDeque](https://docs.oracle.com/javase/7/docs/api/java/util/concurrent/ConcurrentLinkedDeque.html): nguồn gốc API từ Java 7, không thay thế Javadoc hiện hành.
- [Oracle Java SE 26 — Deque](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Deque.html): bảng các method first/last, queue/stack equivalences.
- [Oracle Java SE 26 — Queue](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Queue.html): offer/poll/peek so với add/remove/element.
- [Oracle Java SE 26 — Iterator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Iterator.html): giao thức next/remove.
- [Oracle Java SE 26 — Spliterator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Spliterator.html): characteristics CONCURRENT/ORDERED/NONNULL/SIZED.
- [Oracle Java SE 26 — LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html): bounded capacity và blocking methods.
- [Oracle Java SE 26 — BlockingDeque](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/BlockingDeque.html): take/put/timed offer/poll.
- [Oracle Java SE 26 — ConcurrentLinkedQueue](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html): concurrent FIFO một đầu.
- [Oracle Java SE 26 — ArrayDeque](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ArrayDeque.html): deque không thread-safe cho môi trường đơn luồng.
- [Oracle Java SE 26 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `newKeySet()` để kiểm thử id uniqueness.
- [Oracle Java SE 26 — CountDownLatch](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html): completion signal cho producer.
- [Oracle Java SE 26 — Semaphore](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Semaphore.html): admission permits khi muốn giới hạn pending items.
- [Oracle Java SE 26 — ExecutorService](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit/shutdown và quản lý tác vụ.
- [Oracle Java SE 26 — Future](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html): get(timeout) và failure propagation.
- [Oracle Java SE 26 — LockSupport](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/LockSupport.html): parkNanos trong test polling.
- [OpenJDK JMH](https://github.com/openjdk/jmh): microbenchmark có warm-up và đo lặp trong JVM.

**Tóm tắt:** `ConcurrentLinkedDeque` là lựa chọn hiện hành khi **nhiều threads cần thêm/lấy ở hai đầu** mà không phải chờ dữ liệu theo BlockingDeque semantics. `offerFirst/offerLast` chèn, `pollFirst/pollLast` lấy hoặc trả null nếu rỗng. Dù các operations concurrent an toàn, **peek→poll không atomic**, `size` là O(n) và có thể lệch khi đang sửa, iterator weakly consistent, và bulk operations không tạo transaction. Để triển khai sản phẩm thực, phải có **completion signaling, backpressure/memory budget, payload ownership và kiểm thử concurrency**; khi cần blocking hoặc bounded capacity, chọn `LinkedBlockingDeque` hoặc protocol khác phù hợp.
