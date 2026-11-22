# Message passing để giảm shared mutable state trong Java

## 1. Vấn đề: nhiều thread cùng sửa một trạng thái

Khi các thread cùng đọc và ghi một đối tượng **có thể thay đổi** (shared mutable state), kết quả có thể phụ thuộc thứ tự chạy. Ví dụ một bộ đếm:

~~~java
// Minh họa tình huống có race; không phải chương trình độc lập.
int old = counter;
counter = old + 1;
~~~

Thao tác tăng số nguyên nhìn đơn giản nhưng gồm đọc, tính và ghi. Nếu hai thread cùng thấy `old == 10`, cả hai có thể ghi `11`, mất một lượt tăng. `volatile` có thể hỗ trợ visibility và một số bảo đảm thứ tự, nhưng không khiến phép tăng gồm nhiều bước trở thành atomic. `synchronized`, `Lock` hoặc `AtomicInteger` là những giải pháp hợp lệ tùy yêu cầu; khi dữ liệu phức tạp gồm nhiều trường liên quan, việc giữ toàn bộ invariant bằng các khóa có thể khó kiểm soát.

**Message passing** chọn cách tổ chức khác: **một thực thể sở hữu và thay đổi trạng thái**, các thực thể còn lại gửi **thông điệp yêu cầu thao tác** tới chủ sở hữu thay vì trực tiếp sửa trạng thái đó. Chủ sở hữu xử lý từng thông điệp trong một luồng điều khiển có quy tắc.

~~~text
Producer A ── Add(2) ─┐
                      ├──> Mailbox (thread-safe queue) ──> Owner ──> state
Producer B ── Read() ─┘                                │
                                                       └──> reply/result
~~~

Ví dụ owner giữ số dư, bộ đếm hoặc một phần dữ liệu ứng dụng. Producer gửi lệnh `Add(2)`; owner cập nhật trạng thái; nếu người gửi cần kết quả, owner trả lời qua `CompletableFuture` hoặc một queue phản hồi. Các producer không cần nắm tham chiếu tới chính state.

**Giảm shared mutable state không có nghĩa mọi thành phần đều bất biến hoặc không có đồng bộ.** Bản thân `BlockingQueue` và `CompletableFuture` là các cấu trúc phối hợp an toàn giữa thread; khác biệt là dữ liệu nghiệp vụ mutable được giới hạn trong phạm vi một owner, không bị nhiều thread cùng cập nhật tùy ý.

Bài học áp dụng cho Java concurrency nói chung, không phụ thuộc Spring hoặc cơ chế framework.

## 2. Bốn thành phần của thiết kế message passing

| Thành phần | Vai trò | Quy tắc quan trọng |
| --- | --- | --- |
| **Message** | Mang dữ liệu hoặc ý định thao tác | Ưu tiên immutable; có đủ thông tin để xử lý |
| **Sender / producer** | Tạo và gửi message | Không sửa state thuộc owner; xử lý trường hợp mailbox đầy/đóng |
| **Mailbox / channel** | Chuyển message giữa các thread | Thread-safe, có chính sách thứ tự và dung lượng rõ |
| **Owner / consumer** | Đọc message và cập nhật state của mình | Duy nhất một chủ thể sửa mỗi phần state; xử lý lỗi và phản hồi |

Message thường rơi vào hai nhóm:

- **Command:** yêu cầu thay đổi, chẳng hạn `Deposit(amount)`, `Reserve(id)`, `Add(delta)`. Nếu cần kết quả, command mang một reply channel hoặc correlation ID.
- **Query:** yêu cầu đọc, chẳng hạn `GetBalance(reply)`. Owner trả **snapshot hoặc giá trị bất biến**, thay vì trả về chính collection mutable nội bộ.

Trong Java 17, `record` rất phù hợp để khai báo message dữ liệu:

~~~java
record Deposit(long amount, String transactionId) {}
record BalanceSnapshot(long cents) {}
~~~

Các trường của record là `final` nhưng **record chỉ bảo đảm tính bất biến nông (shallow immutability)**. Nếu record giữ `ArrayList` hoặc mảng có thể sửa, caller vẫn có thể thay đổi nội dung sau khi gửi. Khi message chứa collection, dùng bản sao phòng vệ và view bất biến, ví dụ `List.copyOf(items)`, với điều kiện các phần tử cũng không bị thay đổi ngoài ý muốn.

### Thứ tự và tính đúng đắn

Một owner xử lý tuần tự các message lấy từ mailbox, nên không có hai thao tác cập nhật cùng chạy đồng thời **trong owner đó**. Với queue FIFO như `ArrayBlockingQueue`, message được lấy theo thứ tự đưa thành công vào queue. Khi có nhiều producer đồng thời, thứ tự giữa các lời gửi cạnh tranh phụ thuộc lịch chạy; đừng coi thứ tự viết trong log ở hai thread khác nhau là một thứ tự toàn cục đã được bảo đảm.

**Invariant** như “số dư không âm” hay “tổng đúng bằng tổng các giao dịch chấp nhận” cần được kiểm tra và cập nhật **ngay trong owner**. Chuyển cả chuỗi “đọc, kiểm tra, sửa” vào một command thống nhất; đừng tách thành query rồi command riêng nếu cần tính atomic giữa hai bước đó.

## 3. Java chuẩn có những công cụ nào?

Message passing là **mẫu thiết kế**, không phải một từ khóa riêng trong Java.

| API | Phù hợp khi | Điều cần nhớ |
| --- | --- | --- |
| `BlockingQueue<E>` | Producer/consumer trên nhiều platform thread | `put/take` chặn; dùng queue có giới hạn để tạo backpressure |
| `ArrayBlockingQueue<E>` | Cần dung lượng cố định, FIFO | Thread-safe; `put` có thể chờ khi đầy |
| `LinkedBlockingQueue<E>` | Cần queue có hoặc không có giới hạn | Constructor mặc định dùng capacity rất lớn; tránh tích backlog vô hạn |
| `CompletableFuture<T>` | Cần trả kết quả/lỗi cho người gửi | Complete future là trao kết quả, không tự dừng command đã gửi |
| `ExecutorService` | Cần quản lý thread thực thi consumer | Một single-thread executor dễ làm owner; cần đóng/shutdown |
| `Flow.Publisher/Subscriber` | Luồng bất đồng bộ có demand/backpressure protocol | Backpressure của `Flow` khác với thao tác chặn của `BlockingQueue` |
| `SynchronousQueue<E>` | Bàn giao trực tiếp cho thread đang nhận | Không lưu buffer; chỉ ghép cặp put/take thành công |

Một actor có mailbox là cách tổ chức message passing phổ biến, nhưng **Java không tự áp dụng actor isolation chỉ nhờ khai báo queue**. Bạn phải thực sự giữ state private, tránh trả tham chiếu mutable, giới hạn việc xử lý state trong owner và xác định vòng đời. Một queue thread-safe không khiến tự động mọi object nằm trong message trở thành thread-safe.

## 4. Ví dụ Java 17 hoàn chỉnh: CounterMailbox với một owner

Ví dụ này minh họa quy tắc sở hữu và phản hồi:

1. `CounterMailbox` giữ `int total` **chỉ trong stack của owner thread**.
2. Producer gửi `Add` hoặc `Snapshot` qua `ArrayBlockingQueue<Message>` capacity 2.
3. Mỗi command mang một `CompletableFuture<Integer>` làm kênh trả lời; owner là nơi hoàn tất future.
4. `Math.addExact` kiểm tra overflow. Nếu lỗi, owner trả về failed future và vẫn giữ giá trị cũ.
5. `Stop` là thông điệp dừng. Khi đóng, hệ thống xếp `Stop` **sau các message đã enqueue** và chờ owner hoàn tất.
6. `synchronized` chỉ bảo vệ thao tác **gửi và đóng mailbox**; nó không dùng để bảo vệ `total`, vì không thread nào ngoài owner trực tiếp truy cập `total`.

Lưu vào `MessagePassingDemo.java`:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;

public class MessagePassingDemo {
    private sealed interface Message
            permits Add, Snapshot, Stop {}

    private record Add(
        int delta, CompletableFuture<Integer> reply
    ) implements Message {}

    private record Snapshot(
        CompletableFuture<Integer> reply
    ) implements Message {}

    private enum Stop implements Message {
        INSTANCE
    }

    private static final class CounterMailbox implements AutoCloseable {
        private final BlockingQueue<Message> inbox;
        private final Thread owner;
        private boolean closed;

        CounterMailbox(int capacity) {
            this.inbox = new ArrayBlockingQueue<>(capacity);
            this.owner = new Thread(this::runLoop, "counter-owner");
            this.owner.start();
        }

        CompletionStage<Integer> add(int delta)
                throws InterruptedException {
            CompletableFuture<Integer> reply =
                new CompletableFuture<>();
            enqueue(new Add(delta, reply));
            return reply.minimalCompletionStage();
        }

        CompletionStage<Integer> snapshot()
                throws InterruptedException {
            CompletableFuture<Integer> reply =
                new CompletableFuture<>();
            enqueue(new Snapshot(reply));
            return reply.minimalCompletionStage();
        }

        private synchronized void enqueue(Message message)
                throws InterruptedException {
            if (closed) {
                throw new IllegalStateException("Mailbox đã đóng");
            }
            // Chặn nếu queue đầy: producer chịu backpressure.
            inbox.put(message);
        }

        private void runLoop() {
            int total = 0; // Chỉ owner thread đọc và ghi.
            try {
                while (true) {
                    Message message = inbox.take();
                    if (message == Stop.INSTANCE) {
                        return;
                    }
                    if (message instanceof Add add) {
                        try {
                            int next = Math.addExact(total, add.delta());
                            total = next;
                            add.reply().complete(total);
                        } catch (ArithmeticException error) {
                            add.reply().completeExceptionally(error);
                        }
                    } else if (message instanceof Snapshot query) {
                        query.reply().complete(total);
                    }
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        }

        @Override
        public synchronized void close()
                throws InterruptedException {
            if (!closed) {
                // Đợi chỗ trống nếu cần, sau đó xếp Stop cuối queue.
                inbox.put(Stop.INSTANCE);
                closed = true;
            }
            owner.join();
        }
    }

    public static void main(String[] args) throws Exception {
        try (CounterMailbox counter = new CounterMailbox(2)) {
            CompletionStage<Integer> first = counter.add(2);
            CompletionStage<Integer> second = counter.add(3);
            CompletionStage<Integer> state = counter.snapshot();

            System.out.println("+2 -> " +
                first.toCompletableFuture().join());
            System.out.println("+3 -> " +
                second.toCompletableFuture().join());
            System.out.println("snapshot -> " +
                state.toCompletableFuture().join());

            CompletionStage<Integer> overflow =
                counter.add(Integer.MAX_VALUE);
            try {
                overflow.toCompletableFuture().join();
            } catch (CompletionException error) {
                System.out.println("overflow -> " +
                    error.getCause().getClass().getSimpleName());
            }

            System.out.println("after error -> " +
                counter.snapshot().toCompletableFuture().join());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 MessagePassingDemo.java
java MessagePassingDemo
~~~

Stdout:

~~~text
+2 -> 2
+3 -> 5
snapshot -> 5
overflow -> ArithmeticException
after error -> 5
~~~

Các dòng luôn theo thứ tự này dù owner chạy trên một thread khác: `main` đưa `Add(2)`, `Add(3)`, `Snapshot` vào queue theo thứ tự, sau đó in kết quả theo thứ tự chờ từng stage. `Math.addExact(5, Integer.MAX_VALUE)` ném `ArithmeticException`, còn `total` chỉ được gán sau khi phép cộng thành công, nên snapshot cuối vẫn là `5`.

### Vì sao thiết kế này giảm race?

Producer không được cấp tham chiếu tới `total`. Nó chỉ có thể mô tả thay đổi bằng `Add(delta)`. Mỗi lần xử lý `Add` trong owner gồm đọc, tính, kiểm tra overflow và ghi, trước khi owner xử lý message tiếp theo. Vì vậy không thể xảy ra **lost update giữa hai producer** khi chỉ owner được phép cập nhật state.

`ArrayBlockingQueue` cung cấp đồng bộ phù hợp để chuyển message giữa producer và consumer. Trong contract của `BlockingQueue`, các hành động trước khi thread đặt object vào queue xảy ra-before các hành động sau khi thread khác lấy object tương ứng ra khỏi queue. Điều đó giúp owner quan sát message đã được công bố đúng cách. Với kết quả, `CompletableFuture` là cơ chế phối hợp an toàn để producer nhận tín hiệu hoàn tất.

`minimalCompletionStage()` (Java 9+) trả về một view chỉ để compose, giúp caller khó can thiệp vào thao tác `complete` của future nguồn. Caller vẫn có thể gọi `toCompletableFuture()` để chờ kết quả của view, như ví dụ; thao tác trên future trả về từ view không phải quyền điều khiển trực tiếp future nội bộ của mailbox.

### Giới hạn của ví dụ

Đây là ví dụ **trong một JVM**, không lưu bền trên đĩa và không triển khai retry. Không có cơ chế restart owner nếu thread gặp sự cố nghiêm trọng. Đường `InterruptedException` trong owner minh họa việc giữ interrupt flag, nhưng ứng dụng production phải xử lý toàn bộ command còn đang chờ, hoàn tất các reply bằng lỗi, công bố trạng thái stop và quyết định retry/restart. Ví dụ chỉ gọi `close()` từ thread bên ngoài owner và không chủ động interrupt owner. Đồng bộ hóa `enqueue/close` đảm bảo không nhận thêm command sau khi đã xếp `Stop` trong trường hợp dùng đúng API lớp này.

## 5. Cân nhắc blocking và backpressure

Không nên dùng message passing như cái cớ để tạo queue vô hạn. Nếu producer gửi nhanh hơn owner xử lý, số message chờ sẽ tăng, dẫn đến tốn bộ nhớ và độ trễ.

Trong ví dụ, `ArrayBlockingQueue<>(2)` đặt giới hạn **hai message đang chờ trong queue** (không tính message owner đã lấy ra). Khi đầy, `put()` chặn producer cho tới khi có chỗ. Đó là một dạng **backpressure**: tốc độ tạo công việc bị điều tiết bởi tốc độ tiêu thụ.

Các lựa chọn chính:

| Cách gửi | Khi queue đầy | Trade-off |
| --- | --- | --- |
| `put(message)` | Chờ cho tới khi có chỗ; có thể bị interrupt | Đơn giản nhưng có thể chặn thread gọi |
| `offer(message)` | Trả `false` ngay | Cần chính sách từ chối, retry hoặc bỏ |
| `offer(message, timeout, unit)` | Chờ có giới hạn rồi trả `false` | Kiểm soát thời gian chờ, vẫn cần xử lý thất bại |
| `add(message)` | Ném `IllegalStateException` khi queue có giới hạn và đầy | Hợp cho trường hợp muốn fail-fast qua exception |

Không nên `put()` vào cùng mailbox từ **owner thread** nếu queue có thể đầy: owner sẽ tự chờ mình lấy message khỏi queue, gây deadlock. Tương tự, nếu một continuation của `CompletableFuture` chạy đồng bộ trên owner và tự gọi một operation chặn chờ owner, có thể tạo vòng chờ. Trong hệ thống có throughput cao, nên tách xử lý nặng/chặn I/O khỏi vòng lấy message của owner, hoặc dùng một thiết kế bất đồng bộ với backpressure rõ ràng.

Khi có overload, hãy xác định chính sách trên từng loại message: chờ, trả lỗi quá tải, bỏ loại message không quan trọng, gộp snapshot, hoặc chia partition. **Không tự động retry command thay đổi state** nếu chưa giải quyết idempotency; một lệnh có thể đã được xử lý dù caller timeout.

## 6. Request–reply: kết quả, lỗi, timeout và cancellation

Không phải message nào cũng cần phản hồi. Event kiểu “đã có thay đổi” có thể fire-and-forget **chỉ khi ứng dụng chấp nhận không biết kết quả ngay**. Với command cần cam kết, dùng reply:

~~~java
// Đoạn minh họa: một lớp nhận CompletionStage<Integer>
// từ CounterMailbox.add(...) của mục 4.
CompletionStage<String> report =
    counter.add(7).thenApply(value -> "total=" + value);
~~~

`thenApply` ở đây chỉ chạy khi `add(7)` thành công. Nếu owner hoàn tất future bằng lỗi, `report` cũng thất bại nếu không có handler phục hồi. Caller có thể dùng `handle`, `exceptionally` hoặc `whenComplete` tùy mục đích.

**Timeout của request–reply không đồng nghĩa message bị rút khỏi mailbox.** Nếu caller đợi một stage trong một khoảng thời gian rồi bỏ đợi, command có thể vẫn nằm trong queue hoặc đã xử lý. Tương tự, cancel future của caller không tự xóa message và không đảo ngược state đã thay đổi.

Để xử lý đáng tin cậy trong ứng dụng phức tạp, có thể thêm:

- `requestId`/correlation ID để ghép message và response.
- Deadline được kiểm tra tại owner trước khi thực thi nếu command quá hạn không còn giá trị.
- Idempotency key để retry không áp dụng cùng thay đổi hai lần.
- Trạng thái kết quả rõ ràng: accepted, rejected, committed, failed; phân biệt *đã enqueue* với *đã xử lý*.
- Giới hạn số request đang chờ phản hồi và cách dọn future bỏ rơi.

Ví dụ `CompletionStage` ở mục 4 biểu diễn **kết quả sau khi owner xử lý**, chứ không chỉ “đã bỏ vào queue”. Việc enqueue thành công và completion của reply là hai thời điểm khác nhau.

## 7. Dữ liệu immutable, ownership và tránh rò tham chiếu mutable

Giả sử owner giữ `Map<String, List<String>>`. Một query trả trực tiếp list nội bộ sẽ phá isolation:

~~~java
// Sai ý tưởng trong một owner quản lý mutable List:
reply.complete(internalList); // caller có thể sửa list!
~~~

Tốt hơn là tạo snapshot:

~~~java
// Minh họa, đặt trong owner; internalList thuộc owner.
reply.complete(java.util.List.copyOf(internalList));
~~~

`List.copyOf` tạo danh sách không cho sửa qua API của list trả về, nhưng nếu phần tử bên trong mutable và vẫn bị thay đổi ở nơi khác, dữ liệu chưa trở thành snapshot sâu. Khi cần cô lập hoàn toàn, sao chép cấu trúc lồng nhau hoặc trả DTO immutable chỉ chứa dữ liệu cần thiết.

Với message đầu vào cũng vậy:

~~~java
record SubmitBatch(java.util.List<String> items) {
    SubmitBatch {
        items = java.util.List.copyOf(items);
    }
}
~~~

Đây là record Java 17 hợp lệ: compact constructor biến `items` thành bản sao bất biến trước khi gán tự động vào field. `String` immutable nên ở ví dụ này không có vấn đề phần tử mutable.

Không gửi một `ByteBuffer` đang tiếp tục bị producer sửa trong khi owner đọc; không giữ object mutable được chia sẻ qua reference rồi cho rằng chỉ nhờ gọi `queue.put` đã hết race. Quy tắc ownership chỉ có hiệu lực nếu **không còn tác nhân khác đồng thời sửa object mà owner đang thao tác**.

## 8. Khi một owner trở thành nút thắt

Message passing đánh đổi quyền cập nhật state tập trung để có quy tắc dễ lý giải. Nếu mọi thao tác đều đi qua một owner, throughput cập nhật bị giới hạn bởi tốc độ owner xử lý từng message. Những cách mở rộng thường dùng:

1. **Partition theo khóa:** Ví dụ mỗi account ID được ánh xạ vào một mailbox/owner cố định. Mỗi owner xử lý state của một tập khóa riêng, giảm tranh chấp; các thao tác cần đồng thời chạm nhiều partition lại cần giao thức phối hợp riêng.
2. **Tách command và tính toán nặng:** Owner nhận kết quả tính toán dưới dạng message mới, thay vì chặn vòng xử lý trong lúc gọi network hoặc chạy tác vụ nặng. Cần bảo đảm kết quả muộn vẫn hợp lệ với phiên bản state hiện tại.
3. **Batching:** Gom nhiều command nhỏ khi ngữ nghĩa cho phép; xác định rõ thứ tự, điều kiện commit và cách phản hồi từng command.
4. **Coalesce:** Với trạng thái dạng “giá trị mới nhất”, đôi khi có thể thay nhiều update chờ bằng một update cuối. Không áp dụng cho command phải ghi nhận đủ từng lần, như chuyển tiền.
5. **Đọc snapshot:** Cung cấp bản immutable cho nhiều reader, nhưng phải nói rõ độ mới của snapshot. Snapshot có thể cũ so với các command vừa enqueue.

Một hệ thống có nhiều owner vẫn phải giải quyết message chuyển giữa các owner, thứ tự cross-partition, xử lý lỗi và tính nhất quán. Mô hình local queue trong cùng JVM không tự mang lại durability, exactly-once delivery hay transaction phân tán.

## 9. So sánh với synchronized, atomic và ThreadLocal

| Lựa chọn | Nơi state được cập nhật | Khi nên cân nhắc |
| --- | --- | --- |
| `synchronized` / `ReentrantLock` | Nhiều thread truy cập nhưng có khóa bảo vệ | State dùng chung nhỏ, invariant dễ bảo vệ và contention chấp nhận được |
| `AtomicInteger` / CAS | Nhiều thread update theo phép atomic | Một vài biến/operation độc lập, cần tránh lost update đơn giản |
| `ThreadLocal` | Mỗi thread giữ state riêng | Dữ liệu thật sự gắn với thread; cần cleanup khi thread pool tái sử dụng |
| **Message passing** | Một owner xử lý state, thread khác gửi message | Invariant phức tạp, cần serialize command và giảm diện tích shared mutable state |

Các kỹ thuật này không loại trừ nhau: mailbox dùng đồng bộ nội bộ; reply có thể dùng primitive an toàn; nhiều owner có thể dùng `AtomicLong` cho metric tổng hợp. Điều cần tránh là trộn ownership thiếu quy tắc, ví dụ vừa bắt owner xử lý `Add` qua queue vừa cho thread ngoài trực tiếp gọi `counter++`.

So với `ThreadLocal`, state của owner **gắn với một thành phần logic** và giao thức message, không mặc định gắn với thread bất kỳ xử lý request. Khi cần di chuyển công việc qua nhiều thread hoặc cần trao quyền truy cập có kiểm soát, message passing giúp thể hiện đường chuyển giao rõ ràng hơn.

## 10. Shutdown, lỗi bất ngờ và khả năng quan sát

Ví dụ `Stop` là **poison pill**: một message đặc biệt báo consumer dừng. Với một owner và queue FIFO, gửi `Stop` sau các message đã enqueue cho phép xử lý hết message trước đó. Nếu nhiều consumer cùng lấy từ một queue, một poison pill chỉ dừng **một** consumer; phải thiết kế số lượng tín hiệu hoặc cơ chế dừng phù hợp.

Cần xử lý các trường hợp sau trong ứng dụng thực:

- **Không nhận thêm message khi đóng:** kiểm tra closed và enqueue phải có cùng chính sách đồng bộ. Không để message đến sau `Stop`, vì sẽ không có ai xử lý.
- **Không bị kẹt khi consumer chết:** nếu owner dừng bất ngờ, các future còn chờ phải được complete exceptionally và queue cần được drain/reject. `close` với `put` có thể chặn mãi nếu consumer đã chết mà queue đầy.
- **Interrupt:** `BlockingQueue.put/take` có thể ném `InterruptedException`. Chọn fail/stop/retry rõ ràng và phục hồi interrupt flag nếu không xử lý tiếp. Không vô tình nuốt interrupt.
- **Lỗi business:** chỉ fail message liên quan nếu có thể tiếp tục an toàn, giữ invariant trước khi thông báo lỗi. Trong ví dụ, overflow không làm owner chết.
- **Callback nặng:** `CompletableFuture.complete` có thể chạy trực tiếp các dependent action không có hậu tố `Async` trên thread đang complete. Nếu consumer là owner, một continuation nặng có thể chặn cả mailbox; chuyển việc nặng sang executor phù hợp.
- **Metrics:** theo dõi độ dài queue, số message bị từ chối, thời gian chờ enqueue, thời gian từ enqueue đến xử lý, số lỗi và tuổi của message lâu nhất.
- **Giao thức kết thúc:** xác định liệu `close` phải drain tất cả message, từ chối ngay hay checkpoint state trước khi dừng. `Thread.join` là đợi owner kết thúc, không chứng minh message đã được lưu bền.

Một message được lấy khỏi queue mới chỉ thể hiện *đã chuyển giao vào owner*. Nếu owner chết trước khi commit, không nên báo người gửi rằng thao tác đã thành công. Khi yêu cầu độ bền sau crash, cần thêm lưu trữ/giao thức bền vững và xác nhận commit; queue trong bộ nhớ không giải quyết điều đó.

## 11. Lỗi thường gặp và cách kiểm thử

| Lỗi | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| Gửi tham chiếu mutable rồi producer tiếp tục sửa | Data race dù có queue | Immutable message hoặc chuyển giao ownership thật sự |
| Owner trả collection nội bộ | Caller phá invariant của owner | Trả immutable snapshot/DTO |
| Queue không giới hạn | Tồn đọng message và tăng bộ nhớ | Bounded queue, backpressure, overload policy |
| Producer giữ lock khác rồi chờ `put` | Có thể tạo deadlock với owner | Kiểm tra lock ordering; tránh blocking trong critical section |
| Owner gọi `join` trên reply do chính owner phải hoàn tất | Tự chờ mình, deadlock | Chuyển thành message/continuation không chặn |
| Chỉ kiểm tra kết quả enqueue | Báo thành công trước khi command được xử lý | Có acknowledgement sau xử lý |
| Caller timeout rồi gửi lại không idempotent | Cùng update được áp dụng hai lần | Request ID, deadline, idempotency |
| Chỉ một owner cho mọi dữ liệu không liên quan | Nút thắt hiệu năng | Chia partition theo khóa và quản lý cross-partition |
| Bắt mọi exception rồi bỏ qua | Stage treo, mất lỗi hoặc state hỏng | Fail reply, ghi nhận lỗi, chính sách restart |
| Gửi Stop trước các producer khác | Message nằm sau Stop không được xử lý | Đóng admission trước rồi xếp Stop, await shutdown |

Để tự kiểm thử bài này:

1. Chạy `MessagePassingDemo` và đối chiếu đúng năm dòng stdout.
2. Thêm nhiều lệnh `add(1)` từ các producer khác nhau, sau khi **tất cả lệnh đã enqueue** thì gửi `snapshot`; tổng phải đúng số lệnh thành công. Đừng khẳng định thứ tự từng producer nếu không có ordering protocol.
3. Thử `add(Integer.MAX_VALUE)` sau `5`: phải nhận lỗi overflow và total vẫn là `5`.
4. Giảm queue capacity xuống `1` và cho owner xử lý chậm có kiểm soát; kiểm tra `put` thực sự chờ hoặc `offer` trả `false` theo chính sách.
5. Thử `add` sau `close`: phải bị từ chối; không có thao tác nào được chấp nhận sau tín hiệu dừng.
6. Thử owner chết đột ngột trong một bản triển khai thử nghiệm: bảo đảm caller nhận failure thay vì chờ tương lai mãi mãi. Đây là yêu cầu production cần bổ sung cho demo.
7. Cho một message chứa collection mutable, thay đổi collection ở producer sau khi enqueue; xác minh vì sao cần bản sao phòng vệ.

## 12. Kết luận áp dụng

**Message passing giảm shared mutable state bằng cách biến quyền cập nhật thành trách nhiệm của một owner và biến tương tác thành các message có hợp đồng rõ.** Mấu chốt không nằm ở tên class queue: nó nằm ở ranh giới ownership, tính bất biến của dữ liệu chuyển giao, thứ tự xử lý và cách gửi kết quả/lỗi.

Với Java 17, `record`/`sealed interface` giúp mô tả message, `BlockingQueue` chuyển message an toàn giữa thread, và `CompletableFuture` cung cấp request–reply dễ ghép. Thiết kế hiệu quả còn cần queue có giới hạn, không chặn owner vô ý, dọn tài nguyên và hoàn tất các reply trong mọi đường lỗi. Khi owner giới hạn throughput, chia partition theo khóa thay vì quay lại cho nhiều thread tự ý sửa cùng một object.