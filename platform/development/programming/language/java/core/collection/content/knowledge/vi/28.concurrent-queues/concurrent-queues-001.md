# ConcurrentLinkedQueue và ConcurrentLinkedDeque

## 1. Bài toán: nhiều luồng cùng đưa và lấy phần tử

Một luồng tạo công việc, một luồng khác lấy công việc; hoặc nhiều luồng cùng đẩy và lấy dữ liệu ở hai đầu. Cấu trúc chứa phải bảo vệ được việc liên kết, tìm và loại bỏ các phần tử khi các thao tác chồng lấp.

`ConcurrentLinkedQueue<E>` và `ConcurrentLinkedDeque<E>` là hai lựa chọn thuộc `java.util.concurrent`:

- **`ConcurrentLinkedQueue`** là hàng đợi đồng thời theo thứ tự FIFO: thêm ở đuôi, lấy ở đầu.
- **`ConcurrentLinkedDeque`** là hàng đợi hai đầu đồng thời: cho phép thêm, xem và lấy ở cả đầu lẫn đuôi.

Cả hai dựa trên các nút liên kết, không có giới hạn sức chứa nội tại và không nhận phần tử null. Các thao tác truy cập/cập nhật được thiết kế để sử dụng an toàn giữa nhiều luồng. [ConcurrentLinkedQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html), [ConcurrentLinkedDeque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html)

Điều cần học không chỉ là tên lớp. Bạn cần biết **thêm ở đâu, lấy ở đâu, làm gì khi đang trống và khi nào được kết luận không còn việc**. Collection bảo vệ thao tác chứa/lấy; giao thức xử lý công việc vẫn do ứng dụng xác định.

Ví dụ dùng Java 17 trở lên. Kiến thức nền gồm `Queue`, `Deque`, generic, tham chiếu đối tượng và vòng lặp. Phần đa luồng giải thích điều kiện phối hợp và kết thúc ngay trong bài.

### 1.1. Thuật ngữ và mối liên hệ

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| Đầu (head/first) | Phía lấy phần tử của một hàng đợi FIFO |
| Đuôi (tail/last) | Phía thêm phần tử mới của hàng đợi FIFO |
| FIFO | Phần tử được đưa trước được lấy trước theo thứ tự hàng đợi |
| LIFO | Phần tử được đưa sau được lấy trước, như ngăn xếp |
| Bên tạo/bên nhận | Tác vụ đưa phần tử vào và tác vụ lấy phần tử ra |
| Không có giới hạn nội tại (unbounded) | Không có hạn mức phần tử cố định do cấu trúc tự áp đặt |
| Thao tác không chờ dữ liệu | Lần gọi lấy trả kết quả ngay theo trạng thái quan sát, không đợi một phần tử tương lai xuất hiện |

“Không có giới hạn nội tại” không có nghĩa bộ nhớ vô hạn. “An toàn đa luồng” không có nghĩa nhiều bước của chương trình tự hợp thành một giao dịch.

## 2. Chọn đúng đầu và đúng kiểu kết quả

### 2.1. ConcurrentLinkedQueue: một đường FIFO

Mô hình cơ bản:

```text
lay o dau                              them o duoi
poll / peek  <- [viec-cu, viec-ke-tiep, viec-moi] <- offer
```

`offer(e)` đưa phần tử vào đuôi. `poll()` lấy và xóa phần tử ở đầu. `peek()` chỉ xem đầu, không lấy đi.

Có hai nhóm phương thức tùy cách xử lý queue trống:

| Ý định | Trả giá trị đặc biệt | Ném ngoại lệ nếu trống |
| --- | --- | --- |
| Lấy và xóa đầu | `poll()` trả null | `remove()` ném `NoSuchElementException` |
| Xem đầu, không xóa | `peek()` trả null | `element()` ném `NoSuchElementException` |

Đây là hợp đồng của các phương thức `Queue`. `remove()` không đối số khác `remove(object)`, vốn tìm và xóa một lần xuất hiện của đối tượng được chỉ định. [Queue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html)

Đối với `ConcurrentLinkedQueue` không giới hạn nội tại, `offer` trả true khi thêm thành công; nó không trả false vì “queue đã đủ N phần tử”. Không có cơ chế chờ chỗ trống như một hàng đợi có sức chứa được quản lý.

### 2.2. ConcurrentLinkedDeque: hai đầu độc lập trong giao diện

`Deque` là viết tắt của “double-ended queue”, tức hàng đợi hai đầu.

| Ý định | Đầu `First` | Đuôi `Last` |
| --- | --- | --- |
| Thêm | `offerFirst(e)` hoặc `addFirst(e)` | `offerLast(e)` hoặc `addLast(e)` |
| Lấy, trả null nếu trống | `pollFirst()` | `pollLast()` |
| Lấy, ném ngoại lệ nếu trống | `removeFirst()` | `removeLast()` |
| Xem, trả null nếu trống | `peekFirst()` | `peekLast()` |
| Xem, ném ngoại lệ nếu trống | `getFirst()` | `getLast()` |

`addFirst/addLast` trả void; `offerFirst/offerLast` trả boolean. Với `ConcurrentLinkedDeque`, các thao tác offer ở hai đầu trả true khi thêm thành công, không bị từ chối do một giới hạn sức chứa nội tại. Phần tử null vẫn không hợp lệ.

Khi dùng deque như queue, `offer/add` thêm ở đuôi, còn `poll/remove` lấy ở đầu. Khi dùng như stack, `push` tương ứng thêm đầu và `pop` tương ứng lấy đầu. [Deque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)

Do đó:

- `offerLast` rồi `pollFirst` tạo cách sử dụng FIFO.
- `push` rồi `pop`, cùng làm việc ở đầu, tạo cách sử dụng LIFO.
- Nếu chương trình trộn thêm/lấy hai đầu, thứ tự xử lý cần được mô tả theo quy tắc thực tế đó; không gọi toàn bộ cách dùng là FIFO một cách máy móc.

### 2.3. Có thể chứa phần tử trùng

Hai lần thêm cùng một giá trị tạo hai lần xuất hiện. Đây là queue/deque, không phải set.

Một lần lấy thành công loại bỏ một lần xuất hiện. Nếu cùng một tham chiếu được đưa vào hai lần, hai bên nhận có thể cùng nhận tham chiếu đó từ hai vị trí khác nhau. Điều này không chứng minh queue đã phát một vị trí hai lần.

Nếu nghiệp vụ cần mã công việc duy nhất, quy tắc chống trùng cần được xử lý riêng. Không lấy tính an toàn của hàng đợi làm cơ chế bảo đảm tính duy nhất.

## 3. Chương trình tuần tự để xác định thứ tự và ngoại lệ

Lưu thành **`LinkedEndpointsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedDeque;
import java.util.concurrent.ConcurrentLinkedQueue;

public class LinkedEndpointsDemo {
    public static void main(String[] args) {
        ConcurrentLinkedQueue<String> queue = new ConcurrentLinkedQueue<>();
        queue.offer("one");
        queue.offer("two");
        queue.offer("three");
        System.out.println("queue peek = " + queue.peek());
        System.out.println("queue drain = " + drain(queue));
        System.out.println("empty queue poll = " + queue.poll());
        expectEmpty("empty queue remove", queue::remove);

        ConcurrentLinkedDeque<String> deque = new ConcurrentLinkedDeque<>();
        deque.offerLast("B");
        deque.offerFirst("A");
        deque.offerLast("C");
        System.out.println("deque forward = " + new ArrayList<>(deque));
        List<String> reverse = new ArrayList<>();
        Iterator<String> iterator = deque.descendingIterator();
        iterator.forEachRemaining(reverse::add);
        System.out.println("deque reverse = " + reverse);
        System.out.println("deque ends = " + deque.peekFirst()
                + ", " + deque.peekLast());
        System.out.println("poll first = " + deque.pollFirst());
        System.out.println("poll last = " + deque.pollLast());
        System.out.println("middle remains = " + new ArrayList<>(deque));

        deque.push("X");
        deque.push("Y");
        System.out.println("stack pop = " + deque.pop());
        System.out.println("remove last = " + deque.removeLast());
        System.out.println("remaining = " + new ArrayList<>(deque));
        deque.clear();
        System.out.println("empty deque pollLast = " + deque.pollLast());
        expectEmpty("empty deque pop", deque::pop);
    }

    private static <T> List<T> drain(Queue<T> queue) {
        List<T> values = new ArrayList<>();
        T value;
        while ((value = queue.poll()) != null) {
            values.add(value);
        }
        return values;
    }

    private static void expectEmpty(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("expected NoSuchElementException");
        } catch (NoSuchElementException ex) {
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all LinkedEndpointsDemo.java
java LinkedEndpointsDemo
```

Stdout khi chạy thành công:

```text
queue peek = one
queue drain = [one, two, three]
empty queue poll = null
empty queue remove -> NoSuchElementException
deque forward = [A, B, C]
deque reverse = [C, B, A]
deque ends = A, C
poll first = A
poll last = C
middle remains = [B]
stack pop = Y
remove last = B
remaining = [X]
empty deque pollLast = null
empty deque pop -> NoSuchElementException
```

Chương trình cố ý chỉ dùng một luồng để tách việc hiểu API khỏi việc phân tích lịch chạy:

1. `peek` đọc `one` nhưng vẫn để nó ở đầu, nên lần xả sau đó vẫn lấy được đủ ba phần tử theo FIFO.
2. `poll` trên queue đã xả hết trả null, còn `remove` ném ngoại lệ.
3. Deque được tạo thành `A, B, C` bằng các thao tác ở hai đầu.
4. Iterator thường duyệt từ đầu tới đuôi; `descendingIterator` đi theo chiều ngược lại.
5. Lấy đầu A và đuôi C để lại B.
6. Đẩy X rồi Y ở đầu làm Y trở thành phần tử được `pop` trước.
7. Trạng thái rỗng cuối cùng cho thấy sự khác nhau giữa `pollLast` và `pop`.

Các bản `ArrayList` trong ví dụ chỉ phục vụ in cấu trúc lúc không có bên khác sửa. Chúng không phải cách biến một nguồn đang cập nhật thành ảnh chụp nhất quán toàn cục.

Hàm `drain` dừng khi `poll` trả null. Điều đó phù hợp ở đây vì không có bên tạo nào còn hoạt động. Không suy rộng điều kiện dừng này sang mọi hệ thống có phần tử được thêm về sau.

## 4. Dùng kết quả của lần lấy, không giữ một quan sát cũ

### 4.1. `isEmpty` rồi `remove` có khoảng tranh chấp

Đoạn minh họa cố ý có vấn đề khi nhiều bên cùng lấy:

```java
if (!queue.isEmpty()) {
    String value = queue.remove();
    System.out.println(value);
}
```

Một luồng thấy queue còn phần tử. Trước khi nó gọi `remove`, luồng khác lấy mất phần tử cuối cùng. Lần `remove` sau đó gặp queue trống và có thể ném `NoSuchElementException`.

Mỗi thao tác riêng đều có thể hoàn toàn đúng. Điều sai là chương trình xem kết quả kiểm tra trước như một quyền giữ lại phần tử.

### 4.2. Một lần `poll` vừa thử nhận vừa trả kết quả

Đoạn minh họa không độc lập, với `queue` là `ConcurrentLinkedQueue<String>`:

```java
String value = queue.poll();
if (value != null) {
    System.out.println("Da nhan: " + value);
} else {
    System.out.println("Lan nay chua co phan tu");
}
```

Vì lớp không nhận phần tử null, null có thể dùng làm tín hiệu lần lấy không nhận được phần tử. Không cần một `isEmpty` trước đó.

Tương tự, một `peek` khác null không giữ quyền lấy phần tử ấy bằng lần `poll` tiếp theo. Nếu nhiều bên cùng lấy, kết quả quan sát đầu có thể trở nên cũ ngay sau khi phương thức trả về.

Hai luồng cùng lấy phần tử cuối bằng `pollFirst`/`pollLast` trên deque không được nhận cùng một lần xuất hiện; một bên có thể nhận phần tử, bên kia nhận null. Không cần tự khóa chỉ để thực hiện một lần gọi lấy đúng hợp đồng.

### 4.3. Null tạm thời và điều kiện kết thúc là hai vấn đề

Một bên nhận thấy null khi queue đang trống, nhưng bên tạo có thể thêm phần tử sau đó. Vì vậy, null không tự có nghĩa:

- Mọi bên tạo đã hoàn tất.
- Sẽ không còn công việc mới.
- Mọi công việc đã lấy ra đều xử lý thành công.
- Hệ thống có thể đóng toàn bộ nhóm luồng ngay.

Một giao thức kết thúc có thể dùng số lượng việc đã biết, tín hiệu hoàn tất phối hợp đúng, hoặc phần tử điều khiển khác null. Phải xác định trước điều kiện mà ứng dụng cần chứng minh.

## 5. Chương trình hai bên tạo, hai bên nhận với ConcurrentLinkedQueue

### 5.1. Giao thức được chọn cho thí nghiệm

Ví dụ sau tạo đúng 2.000 công việc có mã riêng. Hai tác vụ đưa việc vào đuôi; hai tác vụ lấy từ đầu.

Để bên nhận biết khi nào được dừng, luồng chính chờ cả hai bên tạo hoàn tất rồi thêm **hai phần tử điều khiển STOP khác null**, mỗi bên nhận lấy một STOP thì kết thúc.

Giao thức đúng trong phạm vi ví dụ vì:

1. Mọi công việc được thêm xong trước khi luồng chính thêm STOP.
2. Cả công việc và STOP đều được thêm ở đuôi, còn bên nhận chỉ lấy từ đầu FIFO.
3. Có đúng hai tác vụ nhận và hai STOP; mỗi tác vụ trả về ngay sau khi lấy một STOP.
4. Luồng chính chờ cả hai tác vụ nhận hoàn tất trước khi kiểm tra tổng kết.

STOP là cùng một tham chiếu được thêm hai lần. Queue cho phép hai lần xuất hiện này; nó không dùng null để báo dừng.

### 5.2. Chương trình đầy đủ

Lưu thành **`LinkedQueueTransferDemo.java`**:

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class LinkedQueueTransferDemo {
    private static final int PER_PRODUCER = 1_000;
    private static final Work STOP = new Work(-1);

    public static void main(String[] args) throws Exception {
        ConcurrentLinkedQueue<Work> queue = new ConcurrentLinkedQueue<>();
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            Future<List<Integer>> consumerA =
                    pool.submit(() -> consume(queue, start));
            Future<List<Integer>> consumerB =
                    pool.submit(() -> consume(queue, start));
            Future<?> producerA = pool.submit(() -> {
                produce(queue, start, 0);
                return null;
            });
            Future<?> producerB = pool.submit(() -> {
                produce(queue, start, PER_PRODUCER);
                return null;
            });
            start.countDown();

            producerA.get(20, TimeUnit.SECONDS);
            producerB.get(20, TimeUnit.SECONDS);
            queue.offer(STOP);
            queue.offer(STOP);

            List<Integer> a = consumerA.get(20, TimeUnit.SECONDS);
            List<Integer> b = consumerB.get(20, TimeUnit.SECONDS);
            Set<Integer> unique = new HashSet<>();
            long sum = 0;
            for (int id : a) {
                require(unique.add(id), "duplicate id");
                sum += id;
            }
            for (int id : b) {
                require(unique.add(id), "duplicate id");
                sum += id;
            }
            int total = 2 * PER_PRODUCER;
            require(a.size() + b.size() == total, "wrong processed count");
            require(unique.size() == total, "missing work");
            require(sum == (long) total * (total - 1) / 2, "wrong checksum");
            require(queue.isEmpty(), "queue must be drained");

            System.out.println("processed = " + (a.size() + b.size()));
            System.out.println("distinct ids = " + unique.size());
            System.out.println("id sum = " + sum);
            System.out.println("queue empty = " + queue.isEmpty());
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static void produce(ConcurrentLinkedQueue<Work> queue,
            CountDownLatch start, int firstId) throws InterruptedException {
        await(start);
        for (int i = 0; i < PER_PRODUCER; i++) {
            queue.offer(new Work(firstId + i));
        }
    }

    private static List<Integer> consume(ConcurrentLinkedQueue<Work> queue,
            CountDownLatch start) throws InterruptedException {
        await(start);
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(15);
        List<Integer> result = new ArrayList<>();
        while (true) {
            if (Thread.currentThread().isInterrupted()) {
                throw new InterruptedException("consumer interrupted");
            }
            if (System.nanoTime() - deadline >= 0) {
                throw new IllegalStateException("consumer timed out");
            }
            Work work = queue.poll();
            if (work == STOP) {
                return result;
            }
            if (work != null) {
                result.add(work.id());
            } else {
                Thread.onSpinWait();
            }
        }
    }

    private static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("start timed out");
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private record Work(int id) {}
}
```

Lệnh chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all LinkedQueueTransferDemo.java
java LinkedQueueTransferDemo
```

Stdout khi chạy thành công:

```text
processed = 2000
distinct ids = 2000
id sum = 1999000
queue empty = true
```

Mỗi tác vụ nhận giữ một `ArrayList` riêng; không có hai luồng cùng ghi một danh sách kết quả. Sau khi `Future.get` trả về, luồng chính mới đọc các danh sách và hợp chúng để kiểm tra mã trùng, số lượng và tổng mã.

Chương trình không in số việc của từng bên nhận vì không có cam kết phân chia đều. Một bên có thể nhận nhiều hơn bên còn lại. Điều cần kiểm tra là các mã 0 đến 1.999 xuất hiện đúng trong kết quả tổng hợp.

### 5.3. Những chi tiết quan trọng của mã

**Nhóm luồng có bốn luồng.** Nếu chỉ có hai luồng rồi cho hai tác vụ nhận chiếm hết chúng để quay chờ, hai tác vụ tạo có thể nằm trong hàng chờ của executor và không có cơ hội chạy. Đó là lỗi phối hợp tác vụ, không phải lỗi của queue.

**`poll` vẫn không chờ dữ liệu.** Khi thấy null, mã chạy một vòng chờ chủ động có kiểm tra ngắt và thời hạn. `Thread.onSpinWait` không biến nó thành `take`.

Vòng chờ này chỉ phục vụ thí nghiệm hữu hạn, nhỏ và có thời hạn. Với ứng dụng cần ngủ chờ việc, một `BlockingQueue` có thao tác chờ phù hợp thường diễn đạt nhu cầu rõ hơn. Không sao chép vòng quay này vào một vòng phục vụ lâu dài mà chưa có thiết kế chờ và sử dụng CPU.

**Mã kiểm tra ngắt và chuyển lỗi ra ngoài.** Nếu tác vụ không tiến triển, thời hạn làm bài thử thất bại thay vì treo vô hạn. `finally` yêu cầu nhóm luồng dừng và chờ kết thúc.

**“Xử lý” trong ví dụ là ghi nhận mã vào danh sách cục bộ.** Nhận khỏi queue không tự cung cấp xác nhận bền vững, hoàn tác hay thử lại cho một tác vụ bên ngoài. Nếu công việc thực tế thất bại sau khi đã lấy, ứng dụng phải định nghĩa cách xử lý tiếp.

### 5.4. Vì sao FIFO không bảo đảm thứ tự hoàn tất?

Queue bảo vệ thứ tự các lần lấy theo thứ tự hàng đợi. Nhưng sau khi A lấy việc trước, nó có thể bị tạm dừng; B lấy việc sau và hoàn tất xử lý trước A.

Tương tự, khi nhiều bên cùng `offer` chồng lấp, không dùng thời điểm gọi hàm đo ở bên ngoài để tự đặt một thứ tự tuyệt đối khác với thứ tự mà queue xác lập cho các thao tác. Những lời gọi nối tiếp không chồng lấp có quan hệ thứ tự rõ ràng hơn.

Không nên in nhật ký sau xử lý rồi lấy thứ tự nhật ký làm bằng chứng queue đã vi phạm FIFO. Cần phân biệt lúc đưa vào, lúc lấy khỏi và lúc hoàn tất công việc.

Một tác vụ nhận gặp STOP cũng không chứng minh tác vụ nhận khác đã xử lý xong mọi phần tử nó từng lấy. Đó là lý do luồng chính chờ cả hai kết quả nhận.

### 5.5. Không chuyển nguyên giao thức STOP sang cách dùng hai đầu khác

Nếu thêm STOP ở đuôi deque rồi lại lấy bằng `pollLast`, bên nhận có thể lấy STOP trước những việc cũ còn ở đầu. Khi ấy lập luận FIFO của chương trình không còn đúng.

Mỗi khi đổi đầu thêm/lấy hoặc đổi số bên nhận, cần xác định lại số tín hiệu kết thúc và vị trí của chúng so với công việc. Collection không tự biết một phần tử nào là dữ liệu hay tín hiệu dừng.

## 6. Chương trình ConcurrentLinkedDeque: cùng lấy từ hai đầu

### 6.1. Điều kiện kết thúc khác ví dụ trước

Ở ví dụ này, luồng chính đưa sẵn 1.000 số vào deque **trước khi gửi tác vụ**, và không còn bên nào thêm nữa. Một tác vụ lấy đầu, tác vụ kia lấy đuôi.

Vì nguồn đã đóng theo quy tắc của chương trình, khi một tác vụ nhận null, nó có thể dừng. Không cần STOP hay chờ một bên tạo tương lai.

Lưu thành **`OppositeEndsDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.ConcurrentLinkedDeque;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class OppositeEndsDemo {
    private static final int COUNT = 1_000;

    public static void main(String[] args) throws Exception {
        ConcurrentLinkedDeque<Integer> deque = new ConcurrentLinkedDeque<>();
        for (int i = 0; i < COUNT; i++) {
            deque.offerLast(i);
        }
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Set<Integer>> first =
                    pool.submit(() -> drain(deque, start, true));
            Future<Set<Integer>> last =
                    pool.submit(() -> drain(deque, start, false));
            start.countDown();

            Set<Integer> a = first.get(10, TimeUnit.SECONDS);
            Set<Integer> b = last.get(10, TimeUnit.SECONDS);
            Set<Integer> overlap = new HashSet<>(a);
            overlap.retainAll(b);
            Set<Integer> all = new HashSet<>(a);
            all.addAll(b);
            long sum = all.stream().mapToLong(Integer::longValue).sum();

            require(overlap.isEmpty(), "same occurrence claimed twice");
            require(all.size() == COUNT, "missing element");
            require(sum == (long) COUNT * (COUNT - 1) / 2, "wrong checksum");
            require(deque.isEmpty(), "deque not drained");

            System.out.println("opposite-end claimed = " + all.size());
            System.out.println("overlap = " + overlap.size());
            System.out.println("id sum = " + sum);
            System.out.println("deque empty = " + deque.isEmpty());
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static Set<Integer> drain(ConcurrentLinkedDeque<Integer> deque,
            CountDownLatch start, boolean fromFirst) throws InterruptedException {
        if (!start.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("start timed out");
        }
        Set<Integer> result = new HashSet<>();
        Integer value;
        while ((value = fromFirst ? deque.pollFirst() : deque.pollLast()) != null) {
            require(result.add(value), "local duplicate");
        }
        return result;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Lệnh chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all OppositeEndsDemo.java
java OppositeEndsDemo
```

Stdout khi chạy thành công:

```text
opposite-end claimed = 1000
overlap = 0
id sum = 499500
deque empty = true
```

Hai tập kết quả cục bộ không giao nhau và hợp lại đủ 1.000 phần tử. Khi chỉ còn một phần tử, cạnh tranh giữa `pollFirst` và `pollLast` không làm cùng một lần xuất hiện được trả cho cả hai tác vụ.

Một tác vụ có thể lấy hết trước khi tác vụ kia thực hiện nhiều thao tác; bài thử không yêu cầu hai phía chia đều 500/500. Các lớp này không hứa công bằng phân phối giữa các luồng.

### 6.2. Không gọi mọi cách dùng deque là FIFO

Nếu chỉ thêm đuôi/lấy đầu, deque dùng theo FIFO. Trong ví dụ hai đầu, một tác vụ lấy các phần tử phía đuôi trong khi tác vụ kia lấy phía đầu; đây là một quy tắc nhận việc khác.

Bài thử chỉ kiểm tra tính đúng của tập phần tử được lấy, không ép một thứ tự xử lý toàn cục theo thứ tự tăng của số. Nếu ứng dụng cần thứ tự hoàn tất tuyệt đối, phải có cơ chế điều phối công việc tương ứng.

Deque là khả năng truy cập hai đầu. Nó không tự trở thành một bộ lập lịch hoàn chỉnh, không tự phân chia quyền sở hữu công việc và không tự cung cấp chính sách ưu tiên hay công bằng.

## 7. Giới hạn về bộ nhớ, quan sát và phạm vi nguyên tử

### 7.1. Không giới hạn sức chứa không có nghĩa không cần điều tiết

Cả hai lớp không có một hạn mức phần tử cố định để `offer` trả false vì đầy. Nếu bên tạo liên tục nhanh hơn bên nhận, số nút và dữ liệu được giữ có thể tiếp tục tăng.

Đó không phải một cơ chế tự điều tiết áp lực đầu vào (backpressure). Bộ nhớ của JVM vẫn hữu hạn; sử dụng hàng đợi không giới hạn không thay thế việc kiểm soát tốc độ nhận việc, giới hạn số công việc đang xử lý hay chính sách quá tải.

`ConcurrentLinkedQueue` được tài liệu mô tả dùng thuật toán non-blocking. Ở mức cách dùng đang học, cả hai lớp không cung cấp `take`, `put` hay `poll(timeout, unit)` để chờ điều kiện dữ liệu/chỗ trống. Điều này không hứa mỗi thao tác có độ trễ cố định hay mỗi luồng được phục vụ công bằng.

Không nên dùng từ “không chặn” để suy ra “không tốn CPU khi chưa có việc”. Một vòng `while (poll() == null)` vẫn do chính chương trình lặp lại và có thể dùng CPU liên tục.

### 7.2. `size` không phải phép đọc hằng thời gian

Đối với cả hai lớp, `size()` phải duyệt để đếm; tài liệu nêu rõ nó không có chi phí hằng thời gian. Khi cấu trúc thay đổi trong lúc đếm, kết quả có thể không chính xác so với trạng thái tại một thời điểm mà bạn muốn dùng. [ConcurrentLinkedQueue — size](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html#size()), [ConcurrentLinkedDeque — size](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html#size())

Không nên đặt `size()` trong vòng lặp nóng chỉ để biết có lấy được phần tử không. Dùng kết quả của `poll` cho lần lấy; nếu chỉ theo dõi tình trạng, vẫn phải hiểu dữ liệu quan sát có thể tạm thời.

Các mẫu sau không tạo giao thức nguyên tử:

- `size() > 0` rồi lấy.
- `size() < limit` rồi thêm.
- `contains(x)` rồi xóa hoặc xử lý x như thể nó còn được giữ lại.
- `peek()` rồi `poll()` và giả định chắc chắn nhận đúng cùng đối tượng.

Nếu phải giữ một điều kiện qua nhiều bước hoặc nhiều collection, cần cơ chế phối hợp đủ cho toàn bộ điều kiện đó.

### 7.3. Iterator nhất quán yếu và thao tác nhiều phần tử

Iterator/spliterator của hai lớp là nhất quán yếu. Có thể duyệt trong khi các luồng khác cập nhật, nhưng không được xem đó là ảnh chụp cố định toàn bộ cấu trúc.

Với deque, iterator thường đi đầu tới đuôi và `descendingIterator` đi đuôi tới đầu. Chính sách quan sát thay đổi và thứ tự duyệt là hai đặc tính khác nhau: nhất quán yếu không có nghĩa mất mọi quy tắc thứ tự.

Các thao tác nhiều phần tử như `addAll`, `removeIf` và `forEach` không được cam kết nguyên tử như một khối duy nhất. Người đọc đồng thời có thể quan sát một phần tác động của một nhóm thêm. [ConcurrentLinkedDeque — chính sách duyệt và bulk operations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html)

Không có `ConcurrentModificationException` không chứng minh một bản báo cáo có mọi số cùng phiên bản. Tương tự, `toArray` hoặc sao chép sang một collection mới không tự nâng mức nhất quán của quá trình thu thập nguồn đang thay đổi.

Nếu cần bản chụp nhất quán, hãy xác định giao thức chung cho mọi bên cập nhật và bên chụp, hoặc thiết kế trạng thái theo phiên bản. Khóa bên ngoài một chỗ không tự làm các luồng chỉ gọi API của queue/deque phải lấy khóa đó.

### 7.4. Công bố phần tử không làm trạng thái bên trong tự đồng bộ mãi

Hợp đồng bộ nhớ của concurrent collection quy định các hành động trước khi đặt một đối tượng vào được sắp thứ tự happens-before với các hành động sau khi luồng khác truy cập/lấy đối tượng đó theo hợp đồng. Điều này hỗ trợ việc tạo dữ liệu rồi chuyển nó qua hàng đợi. [java.util.concurrent — Memory Consistency Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html#MemoryVisibility)

Tuy nhiên, queue/deque lưu và trả tham chiếu, không tự sao chép sâu đối tượng. Nếu bên tạo tiếp tục sửa các trường thường sau khi đưa vào trong lúc bên nhận đang đọc, các thay đổi tương lai đó vẫn cần cơ chế bảo vệ riêng.

Hai chương trình đa luồng dùng mã `Integer` hoặc record chỉ chứa `int`, nên tránh được trạng thái phần tử có thể bị sửa sau công bố. Với đối tượng nghiệp vụ có nhiều trường liên quan, nên định nghĩa quyền sở hữu hoặc tính bất biến/phối hợp trường rõ ràng.

### 7.5. Null bị cấm ở đầu vào, nhưng hợp lệ như tín hiệu trả về

Những lệnh minh họa sau cố ý vi phạm hợp đồng:

```java
queue.offer(null);       // NullPointerException.
deque.offerFirst(null);  // NullPointerException.
deque.offerLast(null);   // NullPointerException.
```

Các biến ở đây được hiểu là hai lớp đang học; đoạn này không phải chương trình độc lập. Constructor nhận collection cũng từ chối nguồn null hoặc phần tử null.

Ngược lại, `poll/peek` và các biến thể hai đầu trả null khi không có phần tử phù hợp trong lần gọi đó. Null đầu ra không phải một phần tử null đã được lưu.

Nếu dữ liệu nghiệp vụ thật sự có trạng thái “không có giá trị”, dùng một đối tượng phần tử khác null biểu diễn trạng thái đó theo thiết kế. Nếu cần tín hiệu dừng, dùng một phần tử điều khiển không thể nhầm với dữ liệu thông thường; không chèn null.

## 8. Xóa theo giá trị và chọn cấu trúc theo nhu cầu

### 8.1. Xóa đầu/đuôi khác xóa một lần xuất hiện

`pollFirst`/`pollLast` chọn theo vị trí đầu hoặc đuôi. `removeFirstOccurrence(x)`/`removeLastOccurrence(x)` tìm một phần tử bằng x theo chiều tương ứng.

Đoạn minh họa tuần tự, với import `Deque`, `List` và `ConcurrentLinkedDeque`:

```java
Deque<String> values = new ConcurrentLinkedDeque<>(
        List.of("A", "B", "A", "C", "A"));

values.removeFirstOccurrence("A"); // [B, A, C, A]
values.removeLastOccurrence("A");  // [B, A, C]
values.remove("A");                // [B, C]
```

`remove(Object)` của deque tương đương xóa lần xuất hiện đầu tiên. Nếu không tìm thấy giá trị, phép xóa theo giá trị trả false. Nó không có cùng ý nghĩa với `remove()` không đối số vốn lấy đầu và ném ngoại lệ khi trống.

Các phép tìm/xóa theo giá trị không chỉ chọn trực tiếp một đầu. Nếu ứng dụng chủ yếu tra cứu/xóa theo mã, cần xem một cấu trúc theo khóa hay một chỉ mục khác có phù hợp hơn không, thay vì coi queue như một map.

### 8.2. Bảng lựa chọn theo yêu cầu

| Nhu cầu | Cách tiếp cận nên xem xét | Điều phải xác định |
| --- | --- | --- |
| Nhiều luồng thêm đuôi/lấy đầu, lần lấy không chờ | `ConcurrentLinkedQueue` | Kết thúc, quá tải, lỗi xử lý sau lấy |
| Cần chọn cả đầu và đuôi đồng thời | `ConcurrentLinkedDeque` | Đầu thêm/lấy cụ thể và ý nghĩa thứ tự |
| Cần ngủ chờ tới khi có việc hoặc chờ có thời hạn | `BlockingQueue` phù hợp | Ngắt, thời hạn, kết thúc và có cần giới hạn sức chứa không |
| Cần chờ theo hai đầu | `BlockingDeque` phù hợp | Quy tắc đầu/đuôi và sức chứa |
| Dữ liệu chỉ do một luồng sở hữu | Cấu trúc thông thường phù hợp với nhu cầu | Không chia sẻ ngoài quyền sở hữu đó |
| Cần chống trùng theo mã | Giao thức có set/map hoặc cơ chế nhận việc phù hợp | Phạm vi chống trùng và vòng đời mã |
| Cần lưu việc bền vững/khôi phục sau lỗi tiến trình | Cơ chế lưu trữ và xác nhận tương ứng | Queue trong bộ nhớ không tự cung cấp yêu cầu này |

`BlockingQueue` bổ sung các thao tác như `take`, `put`, lấy/thêm có thời hạn; có triển khai có hoặc không có giới hạn sức chứa. `BlockingDeque` mở rộng ý tưởng đó tới hai đầu. [BlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html), [BlockingDeque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingDeque.html)

Không phải thêm chữ “concurrent” vào tên cấu trúc là chọn xong kiến trúc. Yêu cầu về chờ, giới hạn, thứ tự và vòng đời công việc cần được viết rõ trước.

### 8.3. Kiểm thử theo hợp đồng, không theo phân chia may rủi

Với nhiều luồng, hãy kiểm tra số phần tử cần nhận, tập mã, phần tử trùng, điều kiện kết thúc và việc lỗi tác vụ được quan sát.

Không khẳng định hai bên nhận phải được chia đều, không lấy nhật ký hoàn tất làm thứ tự lấy khỏi hàng đợi, và không dùng `sleep` để chứng minh rằng bên tạo đã chắc chắn hoàn tất.

Ba chương trình trong bài là minh chứng chạy được cho các giao thức đã định. Chúng không phải phép đo hiệu năng và không chứng minh mọi giao thức sử dụng hai lớp đều đúng. Khi thay cách thêm/lấy hay cách báo dừng, cần phân tích lại lịch xen kẽ và các điều kiện bất biến.

## 9. Luyện tập

### Bài 1 — Queue trống trong một khoảnh khắc

Một bên nhận gọi `poll()`, thấy null rồi dừng; bên tạo vẫn đang hoạt động.

**Câu hỏi:** Lần lấy có sai không? Giao thức dừng có đủ cơ sở không?

**Đối chiếu:** Lần lấy có thể hoàn toàn đúng vì queue đang trống ở thời điểm đó. Dừng vĩnh viễn cần biết không còn dữ liệu tương lai hoặc có một tín hiệu kết thúc khác; null tạm thời không cung cấp điều đó.

### Bài 2 — FIFO và thứ tự in kết quả

A lấy việc 1 rồi mất nhiều thời gian; B lấy việc 2 rồi in kết quả trước A.

**Câu hỏi:** Có thể kết luận `ConcurrentLinkedQueue` vi phạm FIFO không?

**Đối chiếu:** Không. Thứ tự lấy và thứ tự hoàn tất là hai sự kiện khác nhau. Cần quan sát đúng ranh giới mà hợp đồng FIFO mô tả.

### Bài 3 — STOP ở sai đầu

Chương trình thêm mọi việc bằng `offerLast`, sau đó thêm STOP bằng `offerLast`, nhưng bên nhận dùng `pollLast`.

**Câu hỏi:** Vì sao có thể dừng khi vẫn còn việc?

**Đối chiếu:** STOP nằm ở đuôi nên được lấy trước các việc cũ ở đầu. Giao thức chèn tín hiệu cuối dựa trên FIFO không còn phù hợp với cách lấy LIFO/ở đuôi đó.

### Bài 4 — Hai lần thêm cùng đối tượng

Một đối tượng công việc được đưa vào hai lần. Hai bên nhận cùng lấy được tham chiếu tới đối tượng đó.

**Câu hỏi:** Queue có nhất thiết phát trùng một lần xuất hiện không? Có cần xét trạng thái bên trong đối tượng không?

**Đối chiếu:** Có hai lần xuất hiện hợp lệ vì queue cho trùng. Hai lần lấy có thể nhận cùng tham chiếu từ hai vị trí khác nhau. Nếu cả hai cùng sửa đối tượng, trạng thái đối tượng cần giao thức riêng.

### Bài 5 — Giới hạn bằng `size`

Hai bên tạo cùng kiểm tra `queue.size() < 100` rồi thêm.

**Câu hỏi:** Có thể xem queue đã có sức chứa tối đa 100 không?

**Đối chiếu:** Không. Phép đếm có thể tốn thời gian và sai lệch khi cập nhật, còn kiểm tra–thêm là nhiều bước. Hai lớp đang học cũng không có giới hạn nội tại đó. Muốn giới hạn cần cơ chế tương ứng với yêu cầu.

### Bài 6 — Hai đầu nhưng chỉ một phần tử

Deque có một phần tử và không còn bên thêm. A gọi `pollFirst`, B gọi `pollLast`.

**Câu hỏi:** Hai bên có được nhận cùng một lần xuất hiện không? Một bên thấy null có được dừng trong điều kiện đã nêu không?

**Đối chiếu:** Chỉ một lần lấy nhận được phần tử; bên kia có thể nhận null. Vì đã biết không còn bên thêm, tác vụ đó được dừng, trong khi việc tổng kết vẫn cần chờ tác vụ còn lại hoàn thành xử lý phần tử đã lấy.

## 10. Tài liệu đối chiếu

- [ConcurrentLinkedQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html): FIFO, không nhận null, duyệt và giới hạn thao tác tổng hợp.
- [ConcurrentLinkedDeque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html): truy cập hai đầu, iterator hai chiều và xóa theo lần xuất hiện.
- [Queue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html), [Deque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html): ý nghĩa từng nhóm phương thức.
- [java.util.concurrent Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html): quan hệ công bố dữ liệu và các họ cấu trúc concurrent.
- [BlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html), [BlockingDeque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingDeque.html): đối chiếu nhu cầu chờ và giới hạn.

