# Bài tập thực tế: Xây bounded producer–consumer bằng BlockingQueue trong Java

## 1. Đề bài và kết quả cần đạt

Xây một pipeline đa luồng trong **Java concurrency** gồm producer tạo công việc, consumer xử lý công việc và một hàng đợi **có giới hạn dung lượng** (bounded queue) ở giữa. Khi producer phát nhanh hơn consumer, hệ thống phải gây **backpressure** hoặc phản hồi tình trạng quá tải, thay vì giữ số lượng Work vô hạn trong heap.

Bài tập chỉ dùng Java standard library: **java.util.concurrent.BlockingQueue**, **ArrayBlockingQueue**, **ExecutorService**, **Future**, các kiểu đồng bộ và atomic. Nội dung độc lập với Spring hoặc framework.

Yêu cầu cụ thể:

1. Dùng **2 producer**, mỗi producer tạo 6 Work có ID riêng; tổng cộng **12 Work**.
2. Dùng **2 consumer** xử lý Work trên các thread riêng.
3. Dùng một **ArrayBlockingQueue capacity = 3** làm kênh chung.
4. Khi hàng đợi đầy, producer phải đợi bằng **put**; không tạo backlog riêng không giới hạn.
5. Chỉ phát tín hiệu dừng sau khi **tất cả producer** đã enqueue xong.
6. Mỗi consumer nhận một tín hiệu dừng riêng (**poison pill**) để thoát vòng lặp.
7. In một kết quả tổng kết **ổn định**, xác nhận số Work đã enqueue, đã xử lý và số ID duy nhất đều bằng 12.
8. Hợp tác với interruption và chuyển lỗi worker về thread main.

Sau bài này, bạn cần giải thích được vì sao queue bounded không đồng nghĩa toàn pipeline bounded, khác biệt **put/offer/take/poll**, cách tránh mất công việc trong khi shutdown và cách kiểm chứng overload.

## 2. Sơ đồ kiến trúc và các bất biến

~~~text
    producer-0 ──┐
                  │       ArrayBlockingQueue<Work>
                  ├─ put ─► [ 1 ] [ 2 ] [ 3 ] ─ take ─► consumer-0
    producer-1 ──┘                 capacity = 3  └ take ─► consumer-1

     buffer đầy: put phải chờ consumer take giải phóng slot
~~~

**Bất biến trong một phiên chạy hoàn tất bình thường:**

- Không có Work thường nào được thêm ngoài 12 Work dự kiến.
- Một Work chỉ được lấy khỏi queue một lần bởi một consumer, bởi thao tác **take** là nguyên tử đối với queue.
- Mỗi consumer chỉ được đánh dấu processed **sau khi xử lý xong**.
- Đến lúc các Future của consumer đều kết thúc, toàn bộ 12 ID được ghi nhận, và queue rỗng.
- Một poison pill không được tính là Work nghiệp vụ hay làm tăng bộ đếm processed.

Bài này không cam kết xử lý exactly-once khi JVM crash hoặc có side effect ngoài tiến trình. BlockingQueue là kênh **trong bộ nhớ**; muốn khôi phục khi crash cần cơ chế bền vững và idempotency ngoài phạm vi bài thực hành cơ bản.

### FIFO không có nghĩa hai consumer hoàn thành theo đúng thứ tự

ArrayBlockingQueue bảo toàn thứ tự nhận vào FIFO của các phần tử trong queue, nhưng sau khi hai consumer đã lấy hai phần tử khác nhau, thứ tự **kết thúc xử lý** còn phụ thuộc scheduler và thời gian làm việc. Vì vậy kết quả cuối chỉ nên in các bộ đếm và xác minh ID duy nhất, không in một chuỗi thứ tự xử lý được cho là cố định.

## 3. Hiểu API BlockingQueue

| Thao tác | Khi queue đầy/rỗng | Khi dùng |
| --- | --- | --- |
| **put(e)** | Đợi đến khi có chỗ; có thể bị interrupt | Muốn backpressure và không chủ động bỏ công việc |
| **offer(e)** | Trả false ngay nếu không có chỗ | Producer không được chờ |
| **offer(e, timeout, unit)** | Chờ tối đa timeout rồi trả false nếu vẫn không có chỗ | Producer có deadline |
| **add(e)** | Có thể ném IllegalStateException khi đầy | Muốn báo lỗi tức thì |
| **take()** | Đợi đến khi có phần tử; có thể bị interrupt | Consumer sống lâu |
| **poll()** | Trả null ngay khi rỗng | Thăm dò không blocking |
| **poll(timeout, unit)** | Đợi tối đa timeout, trả null khi hết hạn | Consumer cần kiểm tra điều kiện dừng định kỳ |
| **peek()** | Trả đầu queue mà không lấy ra hoặc null nếu rỗng | Quan sát tức thời, không dùng như giao thức claim Work |

**BlockingQueue không chấp nhận null** làm phần tử. Vì vậy không được dùng **put(null)** để báo kết thúc.

**ArrayBlockingQueue<>(3)** có kích thước mảng cố định 3 slot. **LinkedBlockingQueue<>(3)** cũng là bounded, nhưng **LinkedBlockingQueue<>()** không truyền capacity có giới hạn mặc định cực lớn (Integer.MAX_VALUE); đừng coi nó là một bounded queue vận hành an toàn. **SynchronousQueue** không chứa phần tử trong buffer và cần rendezvous giữa bên gửi và bên nhận; không phải mô hình capacity 3. **PriorityBlockingQueue** có cơ chế ưu tiên và không cung cấp giới hạn fixed-capacity tương tự.

## 4. Lời giải hoàn chỉnh: hai producer, hai consumer, capacity ba

Tạo file **BoundedProducerConsumer.java** với toàn bộ code sau. Chương trình chạy trực tiếp trên Java 17+.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class BoundedProducerConsumer {
    private static final int CAPACITY = 3;
    private static final int PRODUCERS = 2;
    private static final int CONSUMERS = 2;
    private static final int ITEMS_PER_PRODUCER = 6;

    private record Work(int id, boolean stop) {}

    private static final Work STOP = new Work(-1, true);

    public static void main(String[] args) throws Exception {
        BlockingQueue<Work> queue = new ArrayBlockingQueue<>(CAPACITY);
        ExecutorService producers = Executors.newFixedThreadPool(PRODUCERS);
        ExecutorService consumers = Executors.newFixedThreadPool(CONSUMERS);

        AtomicInteger produced = new AtomicInteger();
        AtomicInteger processed = new AtomicInteger();
        Set<Integer> uniqueIds = ConcurrentHashMap.newKeySet();

        List<Future<?>> producerTasks = new ArrayList<>();
        List<Future<?>> consumerTasks = new ArrayList<>();

        try {
            // Khởi động consumer trước để có thread nhận dữ liệu.
            for (int c = 0; c < CONSUMERS; c++) {
                consumerTasks.add(consumers.submit(() -> {
                    try {
                        while (true) {
                            Work work = queue.take();
                            if (work.stop()) {
                                return;
                            }

                            // Giả lập xử lý; thực tế có thể là tính toán/I/O.
                            TimeUnit.MILLISECONDS.sleep(15);
                            if (!uniqueIds.add(work.id())) {
                                throw new IllegalStateException(
                                        "Duplicate ID: " + work.id());
                            }
                            processed.incrementAndGet();
                        }
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(
                                "Consumer interrupted", e);
                    }
                }));
            }

            for (int p = 0; p < PRODUCERS; p++) {
                final int producerId = p;
                producerTasks.add(producers.submit(() -> {
                    try {
                        for (int i = 0; i < ITEMS_PER_PRODUCER; i++) {
                            int id = producerId * ITEMS_PER_PRODUCER + i;
                            queue.put(new Work(id, false));
                            produced.incrementAndGet();
                        }
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(
                                "Producer interrupted", e);
                    }
                }));
            }

            // Không được báo STOP khi producer còn đang enqueue.
            for (Future<?> future : producerTasks) {
                future.get(30, TimeUnit.SECONDS);
            }

            // Mỗi consumer cần nhận đúng một STOP.
            for (int i = 0; i < CONSUMERS; i++) {
                if (!queue.offer(STOP, 5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Cannot enqueue STOP");
                }
            }

            // Future.get() đưa exception của worker về main.
            for (Future<?> future : consumerTasks) {
                future.get(30, TimeUnit.SECONDS);
            }

            int expected = PRODUCERS * ITEMS_PER_PRODUCER;
            if (produced.get() != expected
                    || processed.get() != expected
                    || uniqueIds.size() != expected
                    || !queue.isEmpty()) {
                throw new IllegalStateException("Lost or duplicate work");
            }

            System.out.println("produced=" + produced.get());
            System.out.println("processed=" + processed.get());
            System.out.println("uniqueIds=" + uniqueIds.size());
            System.out.println("queueCapacity=" + CAPACITY);
            System.out.println("queueEmpty=" + queue.isEmpty());
        } finally {
            // Hợp tác với interruption khi xảy ra lỗi/timeout.
            producers.shutdownNow();
            consumers.shutdownNow();
        }
    }
}
~~~

**Biên dịch và chạy:**

~~~bash
javac BoundedProducerConsumer.java
java BoundedProducerConsumer
~~~

**Stdout chính xác khi chương trình hoàn tất thành công:**

~~~text
produced=12
processed=12
uniqueIds=12
queueCapacity=3
queueEmpty=true
~~~

Lịch thực thi có thể khác nhau giữa các lần chạy nhưng tổng kết này vẫn xác định vì chỉ in sau khi đợi tất cả Future hoàn tất. Nếu consumer hoặc producer lỗi/timeout, chương trình ném exception và không in thành công giả.

### Giải thích theo luồng thực thi

**Bước 1: tạo một queue với giới hạn rõ ràng.** Queue tối đa chứa 3 Work cùng lúc. Nếu đã đầy, **queue.put(work)** block thread producer cho đến khi một consumer gọi take thành công. Producer không tạo tiếp các Work khác trong khi đang chờ put, nên không tự dựng hàng đợi vô hạn ở phía gửi.

**Bước 2: consumer là worker sống lâu.** Mỗi consumer chạy vòng lặp take, xử lý một Work, rồi mới take tiếp. Mỗi consumer có tối đa một Work đã lấy ra nhưng còn đang xử lý trong ví dụ này. Khi gặp Work có stop=true, consumer thoát.

**Bước 3: ID không trùng nhau.** Producer 0 tạo ID 0..5; producer 1 tạo ID 6..11. Hash set đồng thời của ConcurrentHashMap cho phép hai consumer xác nhận các ID được xử lý duy nhất mà không có data race.

**Bước 4: counter có ý nghĩa cụ thể.** produced tăng sau khi put thành công, nên đây là số Work đã đi vào queue. processed tăng sau sleep mô phỏng xử lý và thao tác ghi nhận ID thành công. Khi chương trình vẫn chạy, produced có thể lớn hơn processed; đó là trạng thái hợp lệ khi queue có backlog.

**Bước 5: đóng nguồn trước khi dừng đích.** Main đợi toàn bộ producer Future.get thành công. Chỉ lúc đó mới enqueue STOP. Trong FIFO, các Work thường đã được enqueue trước STOP; không Work thường nào chưa được consumer take lại bị bỏ qua bởi STOP. Nhưng vì Work đã take có thể còn đang xử lý, phải tiếp tục đợi toàn bộ consumer Future.

**Bước 6: mỗi consumer một STOP.** Với 2 consumer, nếu chỉ gửi 1 STOP, consumer còn lại có thể tiếp tục chờ take vô hạn. Gửi STOP quá sớm có thể khiến consumer rời pipeline khi producer còn đang cố enqueue Work mới.

**Bước 7: lỗi được đưa về main.** ExecutorService.submit trả về Future; Future.get có thể báo ExecutionException hoặc TimeoutException. Khi lỗi xảy ra, finally gọi shutdownNow để cố interrupt worker đang chờ put/take/sleep. Điều này không thay thế quy trình khôi phục nghiệp vụ, nhưng giúp ví dụ không âm thầm mất lỗi.

**Lưu ý về queue nội bộ của ExecutorService:** Executors.newFixedThreadPool có hàng đợi task nội bộ không giới hạn theo mặc định. Chương trình này chỉ submit đúng **4 runnable worker sống lâu**, nên không phát sinh backlog Runnable tăng theo số Work. Nếu thay mỗi Work bằng một lệnh executor.submit riêng thì bounded BlockingQueue ở bên cạnh không còn giới hạn toàn bộ pipeline.

## 5. Thí nghiệm thứ hai: chứng minh khi queue đầy

Để quan sát ngay sự khác biệt giữa **offer** và thao tác chờ có timeout, tạo **FullQueueBehavior.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

public final class FullQueueBehavior {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);

        queue.put("first");
        System.out.println("offer=" + queue.offer("second"));
        System.out.println("timedOffer=" +
                queue.offer("second", 50, TimeUnit.MILLISECONDS));

        System.out.println("take=" + queue.take());
        System.out.println("offerAfterTake=" + queue.offer("second"));
        System.out.println("takeAgain=" + queue.take());
    }
}
~~~

Chạy:

~~~bash
javac FullQueueBehavior.java
java FullQueueBehavior
~~~

**Stdout chính xác:**

~~~text
offer=false
timedOffer=false
take=first
offerAfterTake=true
takeAgain=second
~~~

Khi capacity=1 và queue đã chứa "first", offer ngay lập tức trả false, còn offer có timeout đợi tối đa 50 ms rồi trả false vì không có consumer. Sau khi take lấy "first", queue rỗng và offer lần tiếp theo trả true.

**Không thử thay offer("second") bằng put("second") trong cùng main thread trước khi take.** Chương trình sẽ đợi vì queue đầy và không có thread khác giải phóng slot. Nếu muốn chứng minh put block, tạo một thread producer riêng và cho consumer take sau khi queue đầy; sử dụng timeout để thử nghiệm không treo vô hạn.

## 6. Bounded queue tạo backpressure nhưng không giới hạn mọi bộ nhớ

Với capacity 3 trong lời giải:

- Tối đa **3 Work đang đợi trong queue**.
- Tối đa **2 Work được 2 consumer lấy ra để xử lý**.
- Tối đa **2 Work đang được 2 producer giữ tạm thời khi chờ put**.
- Ngoài ra có các object cho task, thread, Future, log và dữ liệu nghiệp vụ.

Giới hạn queue bằng 3 **không có nghĩa chỉ có 3 Work trên toàn heap**. Nếu producer xây sẵn List hàng triệu Work rồi mới lần lượt put, bộ nhớ vẫn tăng trước khi đưa vào queue. Nếu consumer sau take lại đưa công việc sang một executor có queue không giới hạn, backpressure đã bị phá vỡ ở ranh giới thứ hai.

Quan hệ hiệu năng: giả sử hai consumer, mỗi người xử lý được trung bình 20 Work/s, công suất xử lý lý tưởng gần **40 Work/s** nếu không vướng contention. Nếu producer muốn tạo 100 Work/s liên tục, queue sẽ nhanh chóng đầy và put bắt đầu chặn. Bounded queue làm producer chậm lại; nó **không tự nâng throughput consumer** từ 40 lên 100.

**Capacity nhỏ** tiết kiệm bộ nhớ và giảm backlog tối đa nhưng producer dễ phải đợi khi có burst. **Capacity lớn** hấp thụ burst tốt hơn nhưng tăng thời gian Work nằm chờ. Chọn capacity cần dựa vào burst, memory, yêu cầu latency và chính sách quá tải, không chỉ chọn theo throughput trung bình.

Nếu dùng **Little's Law** trong trạng thái ổn định: L = λ × W, với L là số Work trung bình in-flight trong cùng ranh giới, λ là throughput và W là mean residence time. Phép tính giúp kiểm tra backlog; **không dùng mean L để kết luận queue capacity đủ cho mọi burst**.

## 7. Điều gì xảy ra nếu phải từ chối Work?

Lời giải chọn **put** để bảo toàn mọi Work trong phiên chạy bình thường. Nếu producer không được chờ mãi, thay bằng **offer(timeout)** và định nghĩa rõ chính sách khi false:

~~~java
// Đoạn minh họa, cần queue và work được khai báo trong phương thức gọi.
boolean accepted = queue.offer(work, 100, TimeUnit.MILLISECONDS);
if (!accepted) {
    // Ghi metric rejected; thông báo quá tải hoặc retry có giới hạn.
}
~~~

Đoạn trên là minh họa API, không phải chương trình độc lập. Nếu dùng kiểu này trong bài tập, **đừng tăng produced khi offer trả false**. Khi mọi producer và consumer hoàn tất không lỗi, bất biến phù hợp sẽ là:

~~~text
attempted = accepted + rejected
accepted  = processed
~~~

Trường hợp **false** thể hiện Work chưa được nhận vào queue; đừng bỏ qua kết quả rồi tuyên bố xử lý thành công.

| Chính sách | API | Hệ quả |
| --- | --- | --- |
| Chờ chỗ | put | Backpressure; caller có thể block đến khi có consumer |
| Từ chối ngay | offer | Caller phải xử lý false |
| Chờ trong deadline | offer(timeout) | Sau timeout có thể phản hồi lỗi/quá tải |
| Poll có hạn | poll(timeout) | Consumer có thể kiểm tra cờ dừng định kỳ |
| Bỏ bớt Work theo nghiệp vụ | Logic riêng | Phải xác định chính xác Work nào được phép mất và báo metric |

BlockingQueue **không mặc định drop-oldest**. Không được tùy tiện gọi poll để xóa phần tử cũ rồi offer phần tử mới khi yêu cầu nghiệp vụ phải xử lý đầy đủ, đặc biệt khi producer/consumer cùng chạy và có STOP marker.

## 8. Kết thúc an toàn và quản lý gián đoạn

### Vì sao không dùng queue.isEmpty() để quyết định dừng?

**queue.isEmpty()** chỉ là snapshot. Queue rỗng không chứng minh producer đã kết thúc; ngay sau đó producer có thể put thêm. Một consumer cũng có thể đang xử lý Work đã lấy khỏi queue. Vì vậy lifecycle phải được quy định tách khỏi trạng thái empty tức thời.

Giao thức của bài này:

1. Start consumers.
2. Start producers.
3. Wait all producer Future.
4. Enqueue chính xác một STOP cho mỗi consumer.
5. Wait all consumer Future.
6. Xác nhận processed, uniqueIds, queueEmpty.
7. Shutdown executor.

**Không dùng null** vì BlockingQueue không nhận null. Nếu cần ngữ nghĩa kết thúc khác như đóng từng producer hoặc báo lỗi cuối luồng, phải thiết kế message protocol phù hợp hơn là chỉ dựa vào số phần tử.

### InterruptedException và shutdownNow

Các lời gọi **put**, **take**, **offer(timeout)** và **sleep** đều có thể phản ứng với interrupt. Trong worker, bắt InterruptedException, khôi phục cờ bằng **Thread.currentThread().interrupt()** rồi thoát/truyền lỗi. Nuốt exception và quay lại vòng lặp vô hạn có thể khiến shutdown không hoạt động.

**shutdownNow()** chỉ cố gắng dừng task bằng interrupt; không bảo đảm thread lập tức kết thúc nếu code đang chạy không hợp tác với interruption. Với hệ thống sản xuất, nên thiết kế signal dừng, deadline, xử lý task đang dở và chờ termination có giới hạn.

### Consumer lỗi khi producer đang put

Nếu một consumer chết do lỗi nghiệp vụ và các consumer còn lại cũng không xử lý kịp, producer có thể bị chặn. Coordinator nếu cố enqueue STOP bằng put cũng có thể bị chặn. Ví dụ dùng Future.get và offer(STOP, timeout) giúp tránh một số trường hợp treo, nhưng **không phát hiện ngay tất cả lỗi consumer khi producer còn đang chạy**. Ứng dụng thực tế nên giám sát lỗi consumer sớm, hủy pipeline và xác định rõ xử lý Work đã được lấy khỏi queue nhưng chưa hoàn tất.

### Thực sự exactly-once?

Queue chỉ đưa một object từ buffer tới một consumer bằng take, không lưu trạng thái bền vững của side effect. Nếu consumer ghi DB thành công rồi crash trước khi ghi nhận completed, retry có thể làm trùng kết quả. Nếu crash sau take và trước khi xử lý, Work có thể mất. Nên nói chính xác: bài tập kiểm tra **mỗi ID xử lý một lần khi chương trình kết thúc bình thường không lỗi**, không chứng minh exactly-once sau failure.

## 9. Hướng dẫn kiểm thử nâng cao

Hãy chạy bài tập theo những kịch bản sau. Khi cố ý tạo lỗi/treo, dùng timeout hoặc interrupt để kết thúc.

| Thay đổi | Kỳ vọng đúng | Cần quan sát |
| --- | --- | --- |
| CAPACITY=1 | Tổng kết vẫn 12/12/12 | Producer có thể đợi nhiều hơn, queue không quá capacity |
| CAPACITY=100 | Tổng kết vẫn không đổi | Queue có thể hấp thụ burst lớn hơn |
| Consumer sleep=200 ms | Tổng kết vẫn không đổi nếu chưa timeout | Tổng thời gian chạy tăng; put chờ nhiều hơn |
| CONSUMERS=3 | Cần gửi đúng 3 STOP | Mọi worker đều thoát, không kẹt take |
| Chỉ gửi 1 STOP cho 2 consumer | Một worker có thể kẹt | Cần phát hiện timeout và sửa protocol |
| Chuyển put sang offer(timeout) | Có thể có rejected | attempted=accepted+rejected và accepted=processed |
| Consumer ném lỗi cho ID cụ thể | Future.get phải báo lỗi hoặc timeout | Không in kết quả thành công |
| Producer bị interrupt khi put | Worker truyền lỗi ra Future | Không cộng số accepted cho Work chưa enqueue |

Tự bổ sung các phép đo:

- Lấy **System.nanoTime()** trước/sau put để tính thời gian producer bị chặn.
- Đo thời gian Work đợi từ lúc enqueue đến lúc take, nhưng phải đánh dấu chính xác thời điểm accepted; timestamp đặt trước put đã bao gồm cả thời gian chờ admission.
- Đo service time từ đầu xử lý đến khi xử lý xong.
- Đo throughput = processed / thời gian đo, không gộp rejected với completed.
- Lấy mẫu queue.size() đều theo thời gian; snapshot đơn lẻ không phải mean hoặc peak chính xác.
- Theo dõi p95/p99 latency, CPU/GC, thread states và các downstream bottleneck.

Thực hiện nhiều lần vì thread scheduling, JVM warm-up và sleep timing làm số đo thay đổi. Không đánh giá cấu hình dựa vào một lần chạy duy nhất.

## 10. Những lỗi thường gặp

**Dùng queue mặc định không bounded.** LinkedBlockingQueue không truyền capacity có thể giữ rất nhiều Work. Hãy truyền capacity rõ ràng hoặc dùng ArrayBlockingQueue.

**Tạo queue bounded nhưng đặt một List hoặc executor queue không giới hạn bên ngoài.** Giới hạn phải tồn tại ở mọi ranh giới bất đồng bộ, nếu không memory vẫn tăng.

**Dùng produced để đếm Work vừa tạo trước put.** Khi put đang block hoặc bị interrupt, con số không còn đại diện cho Work accepted. Đếm sau khi put thành công hoặc ghi rõ loại metric khác.

**Chỉ nhìn queue.isEmpty() để thoát.** Producer có thể đang hoạt động và producer có thể gửi tiếp. Đóng nguồn rồi phát tín hiệu dừng rõ ràng.

**Gửi thiếu STOP marker.** Một số consumer sẽ chờ take vô hạn; gửi đúng số consumer.

**Gửi STOP quá sớm.** Consumer có thể rời đi trong khi Work thường vẫn đang được tạo.

**Dùng null làm poison pill.** Queue từ chối null; dùng đối tượng marker riêng.

**Nuốt InterruptedException hoặc bỏ qua Future.get.** Worker có thể lỗi âm thầm hoặc không dừng khi shutdown.

**Coi FIFO là thứ tự hoàn thành toàn cục.** Hai consumer có thể kết thúc Work lệch thứ tự; nếu nghiệp vụ cần thứ tự tuyệt đối, dùng một consumer hoặc thiết kế partition/reorder theo key.

**Coi queue capacity là bảo đảm không mất dữ liệu khi crash.** Queue trong bộ nhớ không bền vững; cần cơ chế persist/ack/retry/idempotency nếu nghiệp vụ yêu cầu.

**Dùng nhiều consumer hơn rồi mặc định throughput tăng.** Khóa, CPU, DB connections và I/O downstream có thể là giới hạn thực; phải benchmark.

## 11. Checklist tự đánh giá bài tập

- [ ] Queue có capacity hữu hạn và dương, không có hàng đợi phụ tăng vô hạn theo input.
- [ ] Producer chọn put hoặc kiểm tra kết quả offer, phân biệt attempted và accepted.
- [ ] Consumer xử lý Work trước khi ghi completed.
- [ ] ID không trùng và tập ID dùng cấu trúc thread-safe.
- [ ] Producer hoàn thành rồi mới phát STOP.
- [ ] Một STOP cho mỗi consumer và chờ tất cả Future.
- [ ] Khi worker lỗi/timeout, main không báo thành công giả.
- [ ] Có đường interrupt/shutdown để không treo vô hạn.
- [ ] Chạy được Java 17+ và stdout đúng trong trạng thái thành công.
- [ ] Giải thích được khi nào bounded queue thực sự tạo backpressure và khi nào hệ thống vẫn có nguy cơ hết bộ nhớ.

## Tài liệu chuẩn

- [BlockingQueue — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html): các hình thức add, offer, put, remove, poll, take và memory consistency.
- [ArrayBlockingQueue — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded FIFO và fairness.
- [ExecutorService — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): Future và lifecycle.
- [ThreadPoolExecutor — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): giới hạn worker/queue và cơ chế rejection.
- [Thread — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): interrupt.

**Tổng kết:** Bounded producer–consumer phải có queue giới hạn, cơ chế chờ hoặc từ chối rõ ràng khi đầy, giao thức kết thúc đủ cho mọi consumer và kiểm tra công việc đã hoàn tất. BlockingQueue xử lý đồng bộ liên thread, nhưng người thiết kế vẫn chịu trách nhiệm về giới hạn bộ nhớ toàn pipeline, lỗi worker và chính sách quá tải.