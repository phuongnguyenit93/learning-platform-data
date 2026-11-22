# Backpressure khác buffering thế nào? — Java Concurrency

## 1. Câu trả lời cốt lõi

**Buffering (đệm dữ liệu)** là giữ tạm những phần tử chưa được xử lý trong bộ nhớ hoặc kho lưu trữ trung gian. Nó giúp bên tạo dữ liệu (producer) và bên xử lý dữ liệu (consumer) hoạt động lệch nhịp trong thời gian ngắn.

**Backpressure (điều tiết ngược)** là cơ chế để phía chậm hơn tác động trở lại phía gửi: cho biết mình còn có thể nhận bao nhiêu, hoặc buộc phía gửi giảm tốc/chờ khi không còn chỗ tiếp nhận. Mục tiêu là kiểm soát **lượng công việc đang tồn đọng**, đặc biệt khi tốc độ tạo dữ liệu vượt tốc độ xử lý.

Hai khái niệm không loại trừ nhau. Một pipeline Java có thể **vừa có buffer giới hạn vừa có backpressure**: buffer hấp thụ dao động ngắn; tín hiệu nhu cầu hoặc thao tác chặn producer ngăn lượng tồn đọng tăng vô hạn.

Ví dụ: bộ đọc sự kiện tạo 1.000 phần tử/giây, bộ xử lý chỉ hoàn thành 100 phần tử/giây.

- Nếu chỉ đưa sự kiện vào hàng đợi không giới hạn, backlog tăng xấp xỉ 900 phần tử/giây trong thời gian chênh lệch kéo dài. Thêm RAM chỉ trì hoãn sự cố.
- Nếu có buffer tối đa 1.800 phần tử, bắt đầu từ rỗng, không có chính sách điều tiết, bỏ dữ liệu hay thay đổi tốc độ, buffer sẽ đầy sau khoảng 2 giây. Buffer hữu hạn buộc hệ thống phải quyết định làm gì khi đầy.
- Nếu có backpressure và producer **có thể được làm chậm**, tốc độ tạo/đưa vào hệ thống phải giảm tương ứng; buffer chỉ cần đủ cho các đợt biến động ngắn. Nếu nguồn bên ngoài không thể dừng, vẫn phải có chính sách tràn: chặn tại ranh giới thích hợp, bỏ mẫu, lưu ra đĩa, từ chối hoặc báo lỗi.

Công thức trực giác khi tốc độ gần như không đổi:

~~~text
Tốc độ tăng backlog ≈ max(0, tốc độ đến − tốc độ xử lý)
Thời gian tới khi đầy ≈ sức chứa còn trống / tốc độ tăng backlog
~~~

Đây là mô hình ước lượng, không phải bảo đảm thời gian thực: tốc độ xử lý, phân phối sự kiện, bộ nhớ cho mỗi phần tử và việc chặn producer đều có thể thay đổi.

## 2. So sánh theo đúng câu hỏi

| Khía cạnh | Buffering | Backpressure |
|---|---|---|
| Câu hỏi giải quyết | “Dữ liệu chưa xử lý nằm ở đâu?” | “Bên nhận còn cho phép gửi bao nhiêu?” |
| Cơ chế | Queue, ring buffer, batch, bộ đệm nội bộ | Demand/credit, giới hạn in-flight, producer chờ khi đầy, điều tiết tốc độ |
| Vai trò chính | Hấp thụ độ lệch tốc độ tạm thời | Ngăn tốc độ/khối lượng công việc vượt quá khả năng tiếp nhận bền vững |
| Khi consumer chậm | Queue tiếp tục tăng đến khi chạm giới hạn | Producer được yêu cầu giảm gửi hoặc bị chặn tại một ranh giới |
| Rủi ro riêng | Đệm không giới hạn gây áp lực heap, GC và độ trễ | Tắc nghẽn có thể lan ngược; producer cũng có thể phải chờ |
| Khi đầy | Cần quy tắc block/drop/reject/spill/error | Phải có đường truyền tín hiệu hoặc hành động cưỡng chế giới hạn |
| Có đảm bảo không mất dữ liệu? | Không; phụ thuộc sức chứa và chính sách tràn | Không; phụ thuộc khả năng hợp tác của nguồn, chính sách tràn và độ bền lưu trữ |

**Điểm phân biệt:** một queue lớn không tự tạo ra backpressure. Chỉ khi có cơ chế khiến bên gửi **không thể tiếp tục đẩy nhanh hơn khả năng nhận** (hoặc chủ động giảm gửi theo demand) mới có tác dụng điều tiết ngược. Ngược lại, một queue hữu hạn với thao tác chặn khi đầy vừa là buffering vừa tạo backpressure ở ranh giới queue.

## 3. Flow API trong Java: demand là tín hiệu backpressure

Từ Java 9, **java.util.concurrent.Flow** định nghĩa giao thức Publisher–Subscriber tiêu chuẩn trong JDK:

- **Flow.Publisher<T>**: nguồn phát sự kiện, đăng ký người nhận qua subscribe().
- **Flow.Subscriber<T>**: nhận onSubscribe(), onNext(), onError(), onComplete().
- **Flow.Subscription**: kết nối riêng giữa publisher và subscriber; request(n) tăng số phần tử được phép gửi, cancel() dừng đăng ký theo cơ chế best-effort.
- **Flow.Processor<T,R>**: vừa nhận từ upstream như Subscriber vừa xuất cho downstream như Publisher; cần tự quản lý demand cả hai chiều.

Trình tự cơ bản:

~~~text
Publisher                         Subscriber
    |                                 |
    | -------- onSubscribe(s) ------> |
    | <---------- s.request(2) ------ |
    | --------- onNext(A) ----------> |  còn 1 quyền nhận
    | --------- onNext(B) ----------> |  còn 0 quyền nhận
    |           chờ thêm demand       |
    | <---------- s.request(1) ------ |
    | --------- onNext(C) ----------> |
    | -------- onComplete() --------> |  sau khi nguồn kết thúc bình thường
~~~

**request(2)** là cấp thêm tối đa hai lần gọi onNext, không có nghĩa publisher lập tức sinh hai phần tử hay consumer đã hoàn tất hai tác vụ. Demand là quyền **giao sự kiện**, không phải lời hứa về throughput, độ bền lưu trữ hay “exactly once”.

Các quy tắc quan trọng:

1. Subscriber phải nhận onSubscribe trước khi nhận dữ liệu. Publisher đúng chuẩn không gọi onNext vượt quá tổng demand chưa sử dụng của đăng ký đó.
2. Mỗi lần onNext tiêu thụ một đơn vị demand. Các lần request(n) dương cộng dồn; request(Long.MAX_VALUE) thường được xem là nhu cầu gần như không giới hạn, tức subscriber tự bỏ giới hạn cấp phát theo demand.
3. request(0) hoặc request(số âm) là sai giao thức; subscriber nhận onError với IllegalArgumentException.
4. onError và onComplete là tín hiệu kết thúc; sau khi đã kết thúc sẽ không có thêm onNext hợp lệ. cancel() là best-effort nên một ít tín hiệu đang trên đường vẫn có thể xuất hiện.
5. Flow không bắt buộc mọi Publisher chạy bất đồng bộ. Lịch chạy, queue, thread và chính sách khi bộ đệm đầy thuộc về triển khai cụ thể; không được suy diễn từ interface Flow rằng nguồn sẽ tự động chậm lại.

### Ví dụ chạy được: subscriber yêu cầu từng phần tử

Lưu file **FlowDemandDemo.java** (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class FlowDemandDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch done = new CountDownLatch(1);

        try (SubmissionPublisher<Integer> publisher = new SubmissionPublisher<>()) {
            publisher.subscribe(new Flow.Subscriber<Integer>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription = s;
                    subscription.request(1);
                }

                @Override
                public void onNext(Integer value) {
                    System.out.println("Nhan " + value);
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable error) {
                    System.err.println("Loi: " + error);
                    done.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("Hoan tat");
                    done.countDown();
                }
            });

            for (int i = 1; i <= 5; i++) {
                publisher.submit(i);
            }
        }

        if (!done.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Subscriber chua ket thuc");
        }
    }
}
~~~

Chạy:

~~~bash
javac FlowDemandDemo.java
java FlowDemandDemo
~~~

Stdout khi chạy thành công:

~~~text
Nhan 1
Nhan 2
Nhan 3
Nhan 4
Nhan 5
Hoan tat
~~~

Giải thích:

- onSubscribe() gọi request(1): ban đầu chỉ cấp quyền nhận một item.
- onNext() xử lý một item rồi cấp thêm một quyền. Đây là mô hình **request từng phần tử**; trong ứng dụng thật, chỉ yêu cầu thêm sau khi đã hoàn thành phần công việc cần giới hạn.
- SubmissionPublisher phát bất đồng bộ. CountDownLatch giữ main sống đến khi nhận terminal signal; khối try đóng publisher sau khi submit các phần tử. Nếu xảy ra lỗi, nhánh onError in ra stderr nên kết quả trên là **đường chạy bình thường**.
- **Đừng hiểu sai ví dụ:** việc subscriber request(1) **không chứng minh** producer chỉ tạo một item mỗi lần. SubmissionPublisher vẫn có buffer riêng và vòng for có thể submit nhiều item trước khi subscriber xử lý chúng. Demand giới hạn việc **phát onNext**, còn buffer và hành vi submit quyết định backlog ở bên trong.

Ví dụ đơn giản này không dùng Thread.sleep() để “chứng minh” backpressure. Ngủ trong onNext chỉ làm chậm xử lý và kết quả timing dễ khác nhau theo máy; để kiểm tra giới hạn thật cần đo số item đã tạo, đã giao, đang đệm và tốc độ các giai đoạn.

## 4. Buffering độc lập với Flow: ví dụ queue hữu hạn

Lưu file **BufferingDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class BufferingDemo {
    public static void main(String[] args) {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);

        System.out.println(queue.offer(10));
        System.out.println(queue.offer(20));
        System.out.println(queue.offer(30));
        System.out.println(queue.poll());
    }
}
~~~

Chạy:

~~~bash
javac BufferingDemo.java
java BufferingDemo
~~~

Stdout:

~~~text
true
true
false
10
~~~

Điều này chứng minh **buffering**: queue có hai vị trí; offer(30) thất bại vì đầy, và poll() lấy phần tử 10. Bản thân offer() trả false **không làm producer chậm lại**; caller phải tự quyết định retry có giới hạn, bỏ, báo lỗi hoặc điều tiết đầu vào.

Thay offer() bằng **put()** sẽ khiến thread producer chờ khi queue đầy cho đến khi có chỗ (trừ khi bị ngắt). Một bounded BlockingQueue kết hợp put()/take() vì thế có cả buffer và backpressure **dạng chặn**. Không được gọi put() trong ví dụ một thread ở trên khi queue đang đầy mà không có consumer: chương trình sẽ chờ vô hạn.

Các biến thể phổ biến:

| Thành phần | Khi đầy | Điều gì cần hiểu |
|---|---|---|
| ArrayBlockingQueue.offer(x) | Trả false ngay | Có giới hạn đệm nhưng caller phải tự xử lý thất bại |
| ArrayBlockingQueue.put(x) | Producer chờ chỗ trống | Tạo điều tiết ngược dạng blocking khi consumer lấy item |
| ArrayBlockingQueue.offer(x, timeout, unit) | Chờ tối đa timeout, rồi false | Có giới hạn thời gian chờ, vẫn cần chính sách khi quá hạn |
| Queue không giới hạn thực tế hoặc không kiểm soát backlog | Có thể tăng đến áp lực tài nguyên | Hấp thụ tăng tải nhưng không bảo đảm an toàn bộ nhớ |
| Flow.Subscription.request(n) | Không cấp thêm quyền onNext khi demand đã hết | Backpressure **theo demand**; không phải một queue |

“Không giới hạn” ở đây chỉ là không đặt một capacity nghiệp vụ hữu hạn; mọi cấu trúc trong JVM vẫn chịu giới hạn heap, số phần tử hoặc tài nguyên thực tế.

## 5. SubmissionPublisher kết hợp cả hai cơ chế ra sao?

**SubmissionPublisher<T>** là triển khai Flow.Publisher có sẵn trong JDK. Nó dùng Executor để giao sự kiện bất đồng bộ và giữ **buffer riêng cho từng subscriber** khi cần. Do đó:

- **Subscriber** điều khiển quyền nhận qua Subscription.request(n); chưa đủ demand thì không được giao thêm onNext vượt quyền.
- **Publisher** có thể đã nhận dữ liệu bằng submit(), mặc dù subscriber chưa xử lý kịp; dữ liệu ở buffer trung gian.
- Buffer của từng subscriber có capacity tối đa. Constructor nhận maxBufferCapacity; sức chứa thực thi có thể được làm tròn đến lũy thừa 2, kiểm tra bằng getMaxBufferCapacity().
- **submit(item)** có thể chặn thread gọi khi bộ đệm subscriber đầy, đến khi có tài nguyên. Đây là backpressure ở ranh giới *bên gửi gọi submit*; method không tạo ra năng lực xử lý mới và việc chặn có thể lan tới upstream.
- **offer(item, onDrop)** hoặc overload có timeout có thể bỏ item khi tài nguyên không đủ và gọi callback xử lý drop. Đó là **chính sách mất dữ liệu có kiểm soát**, không đồng nghĩa với bảo đảm backpressure giữ nguyên mọi item.

Lưu ý nhiều subscriber: mỗi subscriber có bộ đệm và demand riêng. Một subscriber chậm có thể ảnh hưởng đến việc submit() dùng chung; một item có thể giao được cho người nhận này nhưng bị drop ở người nhận khác nếu dùng offer(). Hãy xác định rõ yêu cầu fan-out: có phải mọi subscriber đều cần đủ dữ liệu hay mỗi người có thể bỏ mẫu riêng?

Ví dụ cấu hình có giới hạn (đây là **đoạn minh họa**, không phải chương trình standalone):

~~~java
ExecutorService executor = Executors.newFixedThreadPool(2);
SubmissionPublisher<String> publisher =
        new SubmissionPublisher<>(executor, 8);

// ... subscribe, submit/offer và xử lý các terminal signal ...
// Khi hoàn tất, đóng publisher rồi shutdown executor theo vòng đời ứng dụng.
~~~

Không suy ra rằng request(1) đồng nghĩa “buffer chỉ có đúng một chỗ”. Hai đại lượng này độc lập:

- **Demand** = số lần onNext còn được phép phát.
- **Capacity** = số item có thể chờ trong buffer theo triển khai.

Dùng submit() trong một callback đang nắm tài nguyên mà consumer cần, hoặc dùng cùng một executor quá ít thread cho cả producer và consumer chặn nhau, có thể gây starvation/deadlock. Chọn ranh giới chặn, executor và thứ tự đóng tài nguyên cẩn thận.

## 6. Các chính sách khi consumer không theo kịp

**(a) Hấp thụ burst ngắn.** Dùng bounded queue/buffer. Cho phép tồn đọng nhất thời, đo queue depth và thời gian chờ. Không kỳ vọng buffer giải quyết việc nguồn luôn nhanh hơn consumer.

**(b) Giảm tốc nguồn có thể hợp tác.** Trong Flow, subscriber cấp demand theo khả năng xử lý; một publisher/processor đúng chuẩn tôn trọng demand. Với queue, bounded put() hoặc semaphore giới hạn in-flight có thể ngăn producer tiến quá xa. Phải quyết định việc chờ có phù hợp với thread hiện tại không.

**(c) Nguồn không thể giảm tốc.** Chẳng hạn một luồng nhận dữ liệu từ bên ngoài không có cơ chế pause/ack. Backpressure ở pipeline nội bộ không thể “ép” nguồn ngoài dừng. Cần chính sách rõ: reject, sample, drop-oldest/drop-latest, chuyển sang storage bền vững hoặc báo quá tải. Việc chọn policy phụ thuộc mức độ chấp nhận mất dữ liệu và yêu cầu thứ tự.

**(d) Nhiều bước xử lý.** Nếu producer → parser → aggregator → writer, demand ở downstream phải được quản lý xuyên qua từng bước. Một processor chuyển mọi item vào queue không giới hạn rồi lập tức request(Long.MAX_VALUE) từ upstream có thể phá vỡ mục tiêu giới hạn backlog, dù interface vẫn mang tên Flow.

**(e) Bảo toàn dữ liệu.** Backpressure không thay thế durable queue, transaction, retry, idempotency hay acknowledgment. Nếu ứng dụng phải chịu crash và không được mất item, phải thiết kế cơ chế lưu/khôi phục riêng.

## 7. Chọn chiến lược theo điều kiện thực tế

| Tình huống | Hướng xử lý phù hợp | Vì sao |
|---|---|---|
| Lưu lượng đến tăng trong vài trăm mili-giây rồi giảm | Buffer hữu hạn, đo peak | Hấp thụ dao động tạm thời mà không cần tạo hàng đợi khổng lồ |
| Tải đến luôn cao hơn công suất xử lý | Backpressure/rate limit + buffer hữu hạn | Điều chỉnh tốc độ bền vững; thêm buffer chỉ kéo dài thời gian tới quá tải |
| Producer và consumer là các thread Java độc lập | Bounded BlockingQueue với put/take hoặc offer có timeout | Dễ áp dụng giới hạn bộ nhớ và trạng thái khi đầy |
| Dòng dữ liệu dùng giao thức Flow | request(n) có chủ đích; kiểm tra cách publisher xử lý buffer | Giới hạn giao item theo demand, nhưng cần hiểu thiết kế publisher |
| Không thể trì hoãn nguồn; có thể bỏ mẫu | Bounded buffer + drop/reject policy rõ | Không tích lũy vô hạn, đổi lại có khả năng mất item |
| Không thể mất item và nguồn không thể dừng | Cần giới hạn đầu vào và lưu trữ bền vững/ack phù hợp | Flow hay queue trong heap không tự đảm bảo durability |

Khi thiết kế capacity, tính ít nhất: tốc độ cao điểm, thời gian xử lý trung bình và p95/p99, kích thước trung bình/tối đa mỗi item, số consumer, số subscriber, heap còn lại, nhu cầu giữ thứ tự và chính sách lỗi. **Độ trễ** phải được đo từ lúc sinh/nhận đến lúc xử lý xong; throughput tốt trên giấy vẫn có thể che backlog đang lớn lên.

Các tín hiệu vận hành hữu ích là số item chờ, tuổi item già nhất, demand còn lại (nếu có), thời gian producer bị chặn, số lần offer thất bại, drop count, mức sử dụng executor và latency cuối luồng. Đặt ngưỡng cảnh báo trước khi queue đầy hoặc thời gian xử lý vượt SLO.

## 8. Lỗi hiểu sai phổ biến

1. **“Tăng buffer sẽ hết backpressure.”** Sai. Buffer chỉ hoãn điểm nghẽn; khi chênh lệch tốc độ kéo dài, queue tiếp tục đầy.
2. **“Có queue là đã có backpressure.”** Chưa đủ. Queue không giới hạn, hoặc offer() trả false mà caller vẫn tiếp tục tạo việc, không điều tiết nguồn.
3. **“request(1) nghĩa là publisher chỉ tạo một item.”** Sai. Nó giới hạn delivery đến subscriber; publisher có thể có dữ liệu đã tạo nằm trong buffer.
4. **“request(Long.MAX_VALUE) giúp xử lý nhanh hơn.”** Không. Nó chỉ bỏ giới hạn demand; consumer vẫn có công suất hữu hạn.
5. **“submit() không bao giờ block vì nó bất đồng bộ.”** Sai. Giao onNext là bất đồng bộ nhưng submit() có thể block khi buffer cần thêm chỗ.
6. **“Backpressure đảm bảo không mất item.”** Sai. Hành vi drop, lỗi, crash và nguồn không hợp tác đều cần xử lý riêng.
7. **“Dùng sleep() trong demo là chứng minh được cơ chế.”** Không đáng tin. Cần quan sát demand, queue depth, số item đã gửi/xử lý và trạng thái đầy.
8. **“Cứ block producer là an toàn.”** Không luôn đúng. Block trong event loop, callback cần tiến triển hoặc executor bị chiếm hết có thể gây nghẽn/chết chờ.

### Tự kiểm tra kiến thức

- Với producer 500 item/s và consumer 400 item/s, hàng đợi còn 1.000 chỗ sẽ đầy sau khoảng bao lâu nếu bắt đầu rỗng và không điều tiết? **Khoảng 10 giây**.
- Subscriber đã request(3), nhận hai onNext, rồi request(2): còn tối đa mấy onNext chưa sử dụng? **3** (bỏ qua terminal/cancel và các lần request khác).
- ArrayBlockingQueue.offer() trả false khi đầy có tự tạo backpressure không? **Không** nếu caller bỏ qua false và tiếp tục sinh item; dùng put() hoặc một chiến lược điều tiết mới tạo phản hồi đáng kể lên producer.
- Trong SubmissionPublisher, request(1) có đảm bảo buffer bằng 1 item không? **Không**; demand và maxBufferCapacity là hai giới hạn khác nhau.

## 9. Ghi nhớ

**Buffering quản lý chỗ chờ; backpressure quản lý quyền/tốc độ đi vào chỗ chờ.** Một hệ thống tốt thường cần buffer có giới hạn để chịu burst, cơ chế điều tiết để không quá tải kéo dài, cùng chính sách rõ cho tình huống nguồn không thể hợp tác.

Phạm vi bài này là **Java Concurrency của JDK**; các tích hợp và abstraction riêng của Spring thuộc chương khác.

**Tham khảo JDK chính thức:** [Flow (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html), [Flow.Subscription (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html), [SubmissionPublisher (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html), [ArrayBlockingQueue (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html).
