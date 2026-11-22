# Giới hạn buffer và chính sách xử lý consumer chậm trong Java Flow

Trong một pipeline bất đồng bộ, producer có thể phát dữ liệu nhanh hơn consumer xử lý. Nếu không có giới hạn và quy tắc điều tiết, dữ liệu chờ tích tụ, độ trễ tăng, bộ nhớ cạn hoặc producer bị kẹt. Bài này tập trung vào **Java concurrency nói chung**, đặc biệt là các giao diện chuẩn **java.util.concurrent.Flow** và lớp **SubmissionPublisher** (từ Java 9). Các ví dụ sử dụng Java 17+, không phụ thuộc framework.

## 1. Buffer, demand và backpressure là ba khái niệm khác nhau

- **Buffer** là nơi giữ phần tử đã phát nhưng chưa xử lý xong. Giới hạn buffer (bounded capacity) khống chế số phần tử có thể nằm chờ tại một điểm trong pipeline.
- **Demand** là số phần tử mà subscriber cho phép publisher gửi thêm qua lời gọi **Flow.Subscription.request(n)**. Khi nhận một phần tử qua **onNext**, demand chưa đáp ứng giảm tương ứng. Demand là cơ chế điều tiết theo giao thức, không phải dung lượng bộ đệm.
- **Backpressure** là việc sức xử lý ở phía nhận ảnh hưởng đến tốc độ phát/nhận, thay vì cứ đẩy phần tử không giới hạn. Trong Flow, subscriber chủ động yêu cầu thêm phần tử; publisher và các tầng trung gian còn phải quản lý lượng dữ liệu chờ.
- **Slow consumer** là subscriber xử lý chậm, ngừng yêu cầu thêm, bị nghẽn I/O, hết tài nguyên hoặc mắc lỗi khiến backlog tăng.

Hình dung: publisher tạo 1.000 sự kiện/giây, subscriber chỉ giải quyết 600 sự kiện/giây. Nếu cứ tiếp nhận mà không chặn hay bỏ bớt, backlog tăng xấp xỉ **400 sự kiện/giây** trong giai đoạn đó. Sau 30 giây, khoảng 12.000 sự kiện đang chờ. Nếu mỗi phần tử chiếm trung bình 2 KiB, riêng dữ liệu payload có thể gần 24 MiB, chưa kể đối tượng, node hàng đợi, tham chiếu và overhead JVM. Đây là phép ước lượng để thiết kế, không phải cam kết chính xác về heap.

**Điểm cần nhớ:** tăng buffer chỉ giúp hấp thụ burst ngắn; nếu tốc độ đến trung bình luôn lớn hơn tốc độ xử lý, không có kích thước buffer hữu hạn nào chữa được sự chênh lệch lâu dài.

## 2. Mô hình Flow chuẩn của Java

~~~text
Producer --submit/offer--> Publisher --queue riêng--> Subscriber A
                                 |                 request(n)
                                 +--queue riêng--> Subscriber B (chậm)
                                                   request(n)
~~~

Bốn interface liên quan:

| Thành phần | Trách nhiệm |
| --- | --- |
| **Flow.Publisher<T>** | Cho phép subscribe; phát tín hiệu theo hợp đồng Flow. |
| **Flow.Subscriber<T>** | Nhận **onSubscribe**, các **onNext**, rồi một tín hiệu kết thúc **onError** hoặc **onComplete**. |
| **Flow.Subscription** | Ràng buộc một subscriber với publisher; **request(n)** tăng demand, **cancel()** hủy đăng ký. |
| **Flow.Processor<T,R>** | Vừa là subscriber ở phía upstream, vừa là publisher ở phía downstream; phải điều tiết cả hai chiều nếu tự triển khai. |

Quy tắc quan trọng:

1. Subscriber phải nhận **onSubscribe(subscription)** trước **onNext**. Nó thường giữ subscription và gọi **request(n)** với n dương.
2. Mỗi lệnh **request(n)** *cộng thêm* n vào số lượng được yêu cầu nhưng chưa nhận; không phải đặt lại cửa sổ về n. **request(0)** hoặc số âm là lỗi giao thức và dẫn đến **onError(IllegalArgumentException)** theo hợp đồng Subscription.
3. Publisher không được gửi nhiều **onNext** hơn tổng demand còn hiệu lực. **Long.MAX_VALUE** thường biểu thị demand hiệu quả không giới hạn, nhưng **không đồng nghĩa buffer vô hạn**.
4. Một subscriber có thể **cancel()**; việc ngừng gửi là best effort, có thể vẫn có tín hiệu đang trên đường. Subscriber đã hủy không nhất thiết nhận callback kết thúc.
5. Tín hiệu và các callback cần tuân thủ trật tự của từng subscription. Đừng giả định nhiều subscriber cùng chạy với tốc độ hoặc ở cùng thread.

**SubmissionPublisher<T>** là cách dùng Flow có sẵn trong JDK: nó dùng Executor để chuyển sự kiện bất đồng bộ cho từng subscriber; **mỗi subscriber có buffer độc lập**. Tham số **maxBufferCapacity** trong constructor là mức trần yêu cầu cho *mỗi buffer*, không phải một quota tổng chung cho cả publisher. Dung lượng thực thi có thể được làm tròn lên lũy thừa của 2; dùng **getMaxBufferCapacity()** để biết mức thực tế. **Flow.defaultBufferSize()** cung cấp một giá trị khởi đầu tham khảo, không phải cấu hình phù hợp với mọi tải.

**Cần phân biệt:**
- Subscriber đã request nhiều chưa chắc xử lý nhanh; callback **onNext** có thể rất lâu.
- Producer gọi **submit** nhanh không có nghĩa phần tử đã xử lý xong; phương thức có thể chỉ enqueue phần tử.
- Buffer mỗi subscriber bảo vệ khỏi burst cục bộ, nhưng với **submit**, một subscriber chậm vẫn có thể làm nghẽn đường gửi chung khi buffer của nó đầy.

## 3. Điều gì xảy ra khi buffer đầy?

JDK cung cấp hai nhóm API có ý nghĩa chính sách khác nhau:

| Cách phát | Khi buffer subscriber đầy | Giá trị trả về và ý nghĩa |
| --- | --- | --- |
| **submit(item)** | Chờ đến khi có chỗ; hành vi chờ là *uninterruptible* theo tài liệu API. | Ước lượng lag lớn nhất giữa các subscriber; không phải số phần tử đã xử lý. |
| **offer(item, onDrop)** | Thử phát ngay; nếu không đủ chỗ, có thể bỏ item đối với subscriber bị đầy. | Số âm là âm của số lần drop; số không âm là ước lượng lag lớn nhất. |
| **offer(item, timeout, unit, onDrop)** | Chờ có giới hạn khi thiếu tài nguyên, rồi xử lý theo onDrop; có thể liên quan ngắt thread. | Cùng quy ước: âm biểu thị drop, không âm biểu thị lag ước lượng. |

Trong hai phiên bản **offer**, callback **onDrop(subscriber, item)** chạy khi việc phát gặp đầy buffer. **return false** chấp nhận bỏ phần tử đối với subscriber đó; **return true** cho thử phát lại **một lần**, không bảo đảm thử lại thành công. Callback nên ngắn và tránh công việc tốn thời gian hoặc blocking vì các hoạt động khác của publisher có thể bị chặn trong lúc callback chạy. Với nhiều subscriber, một phần tử có thể đến được người này nhưng bị drop ở người khác; không được suy ra giao hàng nguyên tử cho cả nhóm.

**Cực kỳ quan trọng:** **offer + onDrop** của **SubmissionPublisher** không tự động thực hiện chính sách "bỏ phần tử cũ nhất". Nó xử lý thất bại khi phát **phần tử đang offer**. Muốn **drop-oldest**, coalesce theo key hoặc giữ phần tử mới nhất, cần thiết kế queue/operator riêng; không nên mô tả onDrop như một lệnh xóa đầu hàng đợi.

Một giá trị **offerResult < 0** thể hiện có drop trong lần gọi đó; không thể lấy số không âm để kết luận lag hoặc xử lý hoàn toàn đồng bộ. Các hàm **estimateMaximumLag()** và **estimateMinimumDemand()** dành cho quan sát xu hướng, có thể là ảnh chụp xấp xỉ cũ; không dùng làm điều kiện đồng bộ chính xác.

## 4. Chọn chính sách cho consumer chậm

Không có một chính sách tối ưu chung. Quyết định dựa vào khả năng mất dữ liệu, yêu cầu thứ tự, độ trễ và thời gian producer được phép chờ.

| Chính sách | Hành vi | Phù hợp | Đổi lại / lưu ý |
| --- | --- | --- | --- |
| **Block / backpressure producer** | Producer chờ chỗ trống, ví dụ **submit**. | Tác vụ cần giữ đủ phần tử, producer chịu được chờ. | Có thể tăng độ trễ; tuyệt đối tránh block thread nhạy với latency hoặc thread phải xử lý chính luồng giải phóng buffer. |
| **Bounded wait rồi drop/fail** | Chờ tối đa một khoảng với **offer(timeout, …)**. | Có deadline, ưu tiên không treo producer mãi. | Timeout không hứa tổng độ trễ end-to-end chính xác nếu có nhiều subscription/công đoạn. |
| **Drop newest** | Bỏ sự kiện mới khi đầy. | Telemetry, sampling hoặc cập nhật bỏ qua được. | Mất sự kiện; cần đếm drop và công bố rõ semantics cho người dùng. |
| **Drop oldest / keep latest** | Bỏ giá trị cũ, ưu tiên giá trị mới. | Giá trị trạng thái mới nhất như tiến trình, vị trí đo. | Cần hàng đợi/logic riêng; không phù hợp nhật ký giao dịch cần giữ thứ tự đầy đủ. |
| **Coalesce / deduplicate** | Gộp nhiều cập nhật cùng khóa thành một trạng thái. | UI state, đo lường có thể ghi đè. | Phải định nghĩa phép gộp, đồng bộ và bảo toàn semantics. |
| **Sample / throttle** | Giảm tần suất trước khi đến subscriber. | Dashboard, tín hiệu quan sát. | Chủ động bỏ độ phân giải; phải phân biệt lấy mẫu với bỏ ngẫu nhiên do quá tải. |
| **Fail fast / cancel** | Dừng subscriber hoặc pipeline khi vượt ngưỡng. | Hệ thống coi quá tải là lỗi cần phát hiện ngay. | Cần tuyến báo lỗi, retry và cơ chế khôi phục rõ ràng. |
| **Durable queue / spill to disk** | Ghi nơi lưu bền vững rồi tiêu thụ sau. | Event không được mất, producer và consumer cần tách vòng đời. | Phát sinh latency, giới hạn lưu trữ, đồng bộ, retry, duplicate và quản lý thứ tự. |

Nên viết ra một **hợp đồng overflow** trước khi triển khai: phần tử nào được phép mất, ai được block, block tối đa bao lâu, backlog lớn nhất, hành động khi timeout và cách quan sát. Với dữ liệu bắt buộc giao đủ, không chọn drop âm thầm. Với dữ liệu trạng thái liên tục được cập nhật, giữ "latest" có thể hợp lý hơn cố giao mọi mẫu cũ.

### Ví dụ tình huống

- **Audit event / lệnh thanh toán:** không được âm thầm drop; backpressure với hạn chờ và/hoặc hàng đợi bền vững, cơ chế retry/idempotency.
- **Số liệu CPU cập nhật 100 lần/giây lên giao diện chỉ vẽ 10 lần/giây:** sampling hoặc coalescing phù hợp vì trạng thái cũ nhanh chóng mất giá trị.
- **Pipeline phân tích batch:** bounded queue + giới hạn concurrency upstream; nếu consumer chậm liên tục, giảm tốc producer hoặc tăng năng lực consumer.
- **Nhiều subscriber khác nhau:** một subscriber cần dữ liệu đầy đủ, người khác chỉ cần latest. Đừng ép hai yêu cầu trái nhau vào một chính sách drop duy nhất.

## 5. Ví dụ Java 17+: chứng minh buffer đầy và drop có kiểm soát

Chương trình sau tạo **SubmissionPublisher** với một subscriber, **maxBufferCapacity = 1**, và một Executor một thread. Subscriber dừng có chủ ý tại phần tử **A** bằng CountDownLatch, tạo trạng thái có thể kiểm soát để chứng minh **B** chiếm buffer trong lúc **C** bị drop. Đây là mô phỏng kiểm thử sự chậm trễ, không phải cách nên khóa **onNext** trong ứng dụng thật.

Lưu thành **BoundedFlowDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BoundedFlowDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch enteredA = new CountDownLatch(1);
        CountDownLatch releaseA = new CountDownLatch(1);
        CountDownLatch completed = new CountDownLatch(1);
        List<String> received = new CopyOnWriteArrayList<>();
        AtomicInteger drops = new AtomicInteger();

        try {
            try (SubmissionPublisher<String> publisher =
                         new SubmissionPublisher<>(executor, 1)) {

                publisher.subscribe(new Flow.Subscriber<>() {
                    private Flow.Subscription subscription;

                    @Override
                    public void onSubscribe(Flow.Subscription s) {
                        this.subscription = s;
                        s.request(1);
                    }

                    @Override
                    public void onNext(String item) {
                        received.add(item);
                        if (item.equals("A")) {
                            enteredA.countDown();
                            try {
                                releaseA.await();
                            } catch (InterruptedException e) {
                                Thread.currentThread().interrupt();
                                subscription.cancel();
                                completed.countDown();
                                return;
                            }
                        }
                        subscription.request(1);
                    }

                    @Override
                    public void onError(Throwable error) {
                        completed.countDown();
                    }

                    @Override
                    public void onComplete() {
                        completed.countDown();
                    }
                });

                publisher.submit("A");
                if (!enteredA.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Subscriber chua nhan A");
                }

                publisher.submit("B"); // A dang xu ly; B nam trong buffer.
                int offerResult = publisher.offer("C", (subscriber, item) -> {
                    drops.incrementAndGet();
                    return false;      // Chap nhan drop C, khong retry.
                });

                releaseA.countDown();
                publisher.close();
                if (!completed.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Subscriber chua ket thuc");
                }

                System.out.println("received=" + received);
                System.out.println("drops=" + drops.get());
                System.out.println("offerResult=" + offerResult);
            }
        } finally {
            releaseA.countDown();
            executor.shutdownNow();
        }
    }
}
~~~

Biên dịch/chạy bằng Java 17 trở lên:

~~~bash
javac BoundedFlowDemo.java
java BoundedFlowDemo
~~~

Stdout khi chạy bình thường:

~~~text
received=[A, B]
drops=1
offerResult=-1
~~~

**Giải thích từng bước:**

1. **onSubscribe** yêu cầu 1 phần tử, nên **A** được đưa đến **onNext**. Latch **enteredA** xác nhận A đã rời queue và callback đang đợi.
2. Khi A bị giữ trong callback, publisher phát **B** vào buffer còn trống. Vì dung lượng buffer là 1, buffer nay đầy.
3. **offer("C", …)** không chờ vô hạn: callback trả **false**, nên C bị drop và kết quả là **-1** vì có một subscriber bị drop.
4. Main mở latch cho A; subscriber request thêm demand, xử lý B và nhận **onComplete** sau **close()**. **completed.await** bảo đảm chỉ in kết quả sau khi callback kết thúc.
5. **ExecutorService** được đóng trong finally để không rò thread. Latch có timeout khi chờ xác lập/hoàn tất kịch bản; latch cố tình chặn A chỉ nhằm tạo phép thử xác định.

Trong ứng dụng thật, không nên giữ thread giao hàng trong **onNext** chỉ để chờ I/O dài hoặc dựa vào lịch chạy của thread. Khi xử lý chậm, cân nhắc tách task ra một executor có giới hạn, quản lý demand theo mức hoàn thành và định nghĩa nơi chịu backpressure. Nếu callback chuyển việc sang một queue khác rồi request tiếp ngay, chính queue đó có thể phình ra nếu không có giới hạn.

## 6. Điều khiển demand theo cửa sổ

Gọi **request(Long.MAX_VALUE)** là phù hợp khi subscriber thật sự có thể nhận rất nhanh hoặc tác vụ đã được giới hạn ở lớp khác. Đối với consumer chậm, hãy cấp demand theo lô nhỏ rồi bổ sung khi đã xử lý được các phần tử. Một lựa chọn thực dụng:

- Chọn **window = N** theo số việc có thể xử lý an toàn.
- Khi **onSubscribe**, gọi **request(N)**.
- Sau mỗi lô **N/2** phần tử đã xử lý, gọi **request(N/2)** để bổ sung. Tại mọi thời điểm, số demand chưa đáp ứng được giữ có kiểm soát theo thuật toán cửa sổ.
- Nếu xử lý bất đồng bộ, chỉ bổ sung demand **sau khi** công việc thật sự hoàn tất hoặc có capacity ở queue phía sau; đừng coi việc vừa enqueue vào hàng đợi nội bộ là đã hoàn thành.

Ví dụ logic **cửa sổ 8** cho subscriber xử lý đồng bộ, viết như class riêng trong chương trình thực tế (đoạn dưới minh họa cách cấp demand; hàm **process** là nghiệp vụ cần tự cài đặt):

~~~java
final class WindowSubscriber<T> implements Flow.Subscriber<T> {
    private Flow.Subscription subscription;
    private int processedSinceRequest;

    @Override
    public void onSubscribe(Flow.Subscription subscription) {
        this.subscription = subscription;
        subscription.request(8);
    }

    @Override
    public void onNext(T item) {
        process(item); // Hoan tat dong bo truoc khi cap them demand.
        if (++processedSinceRequest == 4) {
            processedSinceRequest = 0;
            subscription.request(4);
        }
    }

    private void process(T item) {
        // Xu ly nghiep vu dong bo, co gioi han tai nguyen.
    }

    @Override
    public void onError(Throwable error) {
        error.printStackTrace();
    }

    @Override
    public void onComplete() {
        // Ket thuc.
    }
}
~~~

Đoạn minh họa cần **import java.util.concurrent.Flow;** và được sử dụng cùng publisher để trở thành chương trình đầy đủ; nó không có **main** riêng. **window 8** không phải hằng số chuẩn. Điều chỉnh theo burst, thời gian xử lý, nhu cầu concurrency và heap thực tế. Nếu một **onNext** thất bại, cần chính sách lỗi/cancel phù hợp; không được giả định runtime tự retry an toàn.

### Demand không thay thế mọi giới hạn queue

Giả sử Subscriber A **request(8)** nhưng mất 2 giây mới xử lý mỗi item; Subscriber B **request(Long.MAX_VALUE)** nhưng xử lý nhanh. Có thể chọn buffer 16 cho mỗi subscription; đây là hai giới hạn khác mục đích. Nếu producer vượt sức xử lý của A, buffer của A vẫn đầy và **submit** sẽ phải chờ dù B đang rảnh. Hơn nữa, nếu A chuyển công việc từ **onNext** sang một queue phụ không giới hạn, buffer Flow nhỏ không còn bảo vệ tổng bộ nhớ của hệ thống. Cần chặn ở **mọi ranh giới bất đồng bộ**.

## 7. Tính dung lượng và ngưỡng chờ từ workload

Đầu tiên đo các đại lượng:

- **R_in**: tốc độ tới trung bình và peak, tính item/giây.
- **R_out**: throughput xử lý bền vững của consumer.
- **T_burst**: thời lượng burst cần hấp thụ.
- **S_item**: kích thước một phần tử thực tế trong bộ nhớ; nên đo, không chỉ lấy kích thước JSON trên mạng.
- **N_sub**: số subscriber và tính chất fan-out.
- **L_target**: độ trễ tối đa cho phép.

Khi R_in > R_out trong một đợt burst, ước lượng số item tích tụ:

~~~text
backlog_burst ≈ max(0, R_in - R_out) × T_burst
memory_payload ≈ capacity × S_item × N_sub
~~~

Ví dụ burst 1.200 item/giây trong 5 giây, consumer xử lý 900 item/giây thì backlog tăng khoảng **1.500 item**. Buffer 256 không đủ giữ toàn bộ burst nếu không giảm tốc hoặc drop. Chọn 2.048 có thể hấp thụ phần burst này, nhưng chỉ có ý nghĩa nếu consumer xử lý bù được khi đầu vào giảm. Với nhiều subscriber, đừng nhân máy móc mọi peak theo cùng một giả định; hãy tính từng buffer và đo heap, vì item có thể được tham chiếu chung còn cấu trúc queue lại riêng.

**Kiểm tra độ trễ:** một hàng chờ 2.000 item với throughput giải phóng 500 item/giây tương ứng khoảng **4 giây** chỉ riêng thời gian tháo hết queue nếu không có phần tử đến thêm. Dùng định luật Little (L = λW) cho dòng ổn định có điều kiện thích hợp, không áp dụng tùy tiện cho burst ngắn. Buffer lớn giúp giảm drop nhưng có thể kéo dài thời gian chờ và giữ dữ liệu cũ lâu hơn.

Đặt deadline cụ thể, chẳng hạn producer chỉ được chờ 20 ms, rồi báo lỗi/từ chối hoặc drop tùy tính chất dữ liệu. Nếu không có ngưỡng chờ, backlog có thể biến thành latency khó đoán. Với hệ thống yêu cầu đủ dữ liệu và không thể xử lý bù, tăng queue mãi chỉ trì hoãn quá tải.

## 8. Multi-subscriber, Executor và các điểm dễ gây nghẽn

**Fan-out:** mỗi subscriber của **SubmissionPublisher** có buffer và demand riêng. Một consumer chậm có thể dẫn đến drop chỉ trên subscription của nó khi dùng **offer**, nhưng với **submit** thì toàn bộ lời gọi producer có thể chờ vì bất kỳ buffer nào đầy. Cần xác định rõ contract giao hàng: tất cả subscriber bắt buộc đủ dữ liệu, hay mỗi subscriber có thể chọn chính sách mất dữ liệu khác nhau.

**Executor:** SubmissionPublisher giao callback bất đồng bộ qua Executor. Số thread, hàng đợi task của Executor và thời gian callback đều ảnh hưởng đến độ trễ. Constructor cần Executor có khả năng chạy task độc lập; đừng thiết kế executor chỉ có một thread rồi block chính thread ấy bằng task đang đợi task khác trên cùng executor. Thread pool/queue của executor cũng phải được đo và giới hạn theo workload; không coi maxBufferCapacity là trần của toàn bộ tài nguyên được sử dụng.

**Blocking:** **submit** có thể block producer. Nếu producer chạy trên thread nhạy latency hoặc callback nào đó cần đúng thread ấy để giải phóng chỗ, sẽ hình thành nghẽn hoặc deadlock do thiết kế. Dùng timeout hoặc cơ chế handoff thích hợp khi đó. Virtual thread (nếu sử dụng Java phiên bản hỗ trợ) có thể làm blocking rẻ hơn về mặt thread hệ điều hành trong một số trường hợp, nhưng **không tăng throughput consumer, không thay thế capacity và không làm dữ liệu tự hết tồn**.

**Exception và lifecycle:** **close()** báo hoàn tất cho subscriber hiện tại; **closeExceptionally(error)** báo lỗi. Nếu **onNext** ném ngoại lệ hoặc Executor từ chối task, cần đường báo lỗi/giám sát theo hợp đồng API; không được giả định phần tử đã phát thành công cho tất cả subscriber. Sau **close**, lệnh submit/offer mới không hợp lệ. Cần dọn tài nguyên Executor thuộc quyền sở hữu của ứng dụng.

## 9. Quan sát quá tải và kiểm chứng chính sách

Một thiết kế hoàn chỉnh cần tối thiểu:

1. **Đo input/output rate:** item được tạo, item được xử lý thành công mỗi giây.
2. **Đo độ trễ:** thời gian từ lúc tạo đến lúc xử lý xong, gồm cả thời gian chờ trong queue; ghi percentile thay vì chỉ trung bình.
3. **Đo backlog/lag:** dung lượng, lag hoặc số việc đang chờ ở từng tầng; các **estimate...()** của SubmissionPublisher chỉ là xấp xỉ để theo dõi.
4. **Đếm overflow:** số item drop, timeout, retry, cancel, callback lỗi và Executor rejection; gắn policy tương ứng.
5. **Theo dõi bộ nhớ:** heap, GC pause, tốc độ cấp phát và số lượng task/queue phụ.
6. **Kiểm thử tải thực:** consumer chậm hơn producer trong vài phút; burst rồi phục hồi; nhiều subscriber lệch tốc độ; một subscriber dừng request; lỗi giữa luồng; shutdown khi còn backlog.

**Các phép kiểm chứng nên có:** tại thời điểm đầy, producer có bị block quá deadline không? Dữ liệu buộc phải giữ có bị mất không? Nếu drop, đó là item mới hay cũ? Subscriber còn lại có tiếp tục hoạt động không? Khi nguồn giảm tốc, backlog có về mức bình thường? Nếu không trả lời được, chính sách overflow chưa được kiểm thử đủ.

## 10. Những lỗi thường gặp

- **Nhầm request(100) với buffer có capacity 100.** Request chỉ tăng demand, còn buffer do publisher quyết định.
- **Tăng maxBufferCapacity vô hạn khi consumer không theo kịp lâu dài.** Đó là cách trì hoãn overflow và đổi lấy heap/latency cao hơn.
- **Gọi request(Long.MAX_VALUE) ngay rồi đẩy sang queue nội bộ không giới hạn.** Flow có demand nhưng pipeline tổng thể vẫn thiếu backpressure.
- **Cho rằng offer luôn giao tới mọi subscriber.** Kết quả âm cho biết có drop; mỗi subscription có thể thành công/thất bại khác nhau.
- **Cho rằng return true trong onDrop bảo đảm giao lại.** Chỉ có một lượt thử lại, vẫn có thể thất bại.
- **Cho rằng onDrop của SubmissionPublisher là drop-oldest.** Muốn loại phần tử cũ cần tự hiện thực chính sách cụ thể.
- **Block trong onNext hoặc submit trên đường xử lý nhạy latency mà không đo.** Có thể lan nghẽn sang thread khác hoặc deadlock.
- **Dùng estimateMaximumLag làm khóa đồng bộ/điều kiện tuyệt đối.** API chỉ hứa giá trị ước lượng phục vụ quan sát.
- **Drop sự kiện cần bảo toàn thứ tự và độ đầy đủ mà không có hợp đồng dữ liệu.** Đây là sai về nghiệp vụ ngay cả khi chương trình không lỗi.
- **Quên đóng publisher/executor hoặc xử lý onError/cancel.** Gây rò tài nguyên hoặc pipeline treo khi có lỗi.

## 11. Quy trình lựa chọn nhanh

**Bước 1 — phân loại dữ liệu:** cần đúng và đủ hay chỉ cần cập nhật mới nhất? Chỉ chọn drop khi đã biết mất dữ liệu nào là chấp nhận được.

**Bước 2 — tính tốc độ và burst:** đo R_in, R_out, thời gian xử lý, giới hạn heap; ước lượng backlog và thời gian tháo queue. Có thể cân nhắc tăng consumer concurrency, nhưng chỉ khi nghiệp vụ cho phép parallelism và thứ tự vẫn được bảo đảm.

**Bước 3 — đặt giới hạn end-to-end:** buffer cho từng subscriber, queue ở executor, queue tự triển khai, số task đang chạy, số publisher/subscriber. Một queue không giới hạn phá hỏng tổng bảo vệ.

**Bước 4 — chọn phương án khi đầy:** block, bounded wait, drop latest/newest, drop oldest, gộp theo key, hoặc từ chối. Nếu không được mất dữ liệu mà consumer chậm kéo dài, cần điều tiết nguồn hoặc lưu bền vững.

**Bước 5 — công bố và kiểm thử contract:** xác nhận request window, overflow behavior, callback lỗi, hủy, shutdown và các chỉ số cảnh báo. Thử với subscriber chậm thực sự và nhiều subscriber.

## Tài liệu chuẩn

- Java SE 21 — **Flow**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html
- Java SE 21 — **Flow.Subscription**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html
- Java SE 21 — **SubmissionPublisher**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html

**Kết luận:** Trong Java Flow, **request(n)** quản lý nhu cầu nhận, **buffer capacity** giới hạn phần tử chờ, còn chính sách **submit/offer/overflow** quyết định điều gì xảy ra khi người tiêu thụ chậm. Hãy xác định rõ việc được phép chờ hay mất dữ liệu, đo throughput và backlog thực tế, rồi áp dụng giới hạn ở mọi hàng đợi của pipeline.