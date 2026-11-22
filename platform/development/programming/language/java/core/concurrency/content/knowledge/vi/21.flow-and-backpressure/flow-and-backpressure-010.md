# Flow API của JDK so với BlockingQueue

## 1. Mục tiêu và bối cảnh

Trong Java, cả **Flow API** và **BlockingQueue** đều giúp kết nối nơi tạo dữ liệu với nơi xử lý dữ liệu khi tốc độ hai phía khác nhau. Chúng giải quyết bài toán này bằng những hợp đồng khác nhau:

- **BlockingQueue** là hàng đợi thread-safe theo mô hình **producer–consumer**. Producer chủ động đưa phần tử vào, consumer chủ động lấy phần tử ra. Với hàng đợi có sức chứa hữu hạn, producer có thể bị chặn khi hàng đợi đầy; consumer có thể bị chặn khi hàng đợi rỗng.
- **Flow API** (từ Java 9, gói **java.util.concurrent.Flow**) là bộ giao diện theo mô hình **Publisher–Subscriber**. Publisher đẩy sự kiện tới từng Subscriber, nhưng mỗi Subscriber thông báo trước số phần tử được phép nhận qua **Subscription.request(n)**. Cơ chế này gọi là **demand-driven backpressure**.

Câu hỏi chọn công cụ không đơn thuần là “cái nào nhanh hơn?” mà là: **cần một hàng đợi công việc để nhiều worker lấy việc, hay cần giao thức phát luồng dữ liệu có đăng ký, demand và tín hiệu kết thúc/lỗi?**

Nội dung dưới đây chỉ bàn về các API concurrency của JDK, không đi vào các framework khác.

## 2. BlockingQueue hoạt động thế nào?

**BlockingQueue<E>** là interface thuộc **java.util.concurrent**. Ví dụ triển khai:

- **ArrayBlockingQueue<E>**: dung lượng cố định, thứ tự FIFO; hữu ích khi cần giới hạn bộ nhớ và tạo áp lực ngược lên producer.
- **LinkedBlockingQueue<E>**: có thể đặt capacity; constructor không truyền capacity dùng giới hạn rất lớn (**Integer.MAX_VALUE**), vì thế không nên ngầm coi là queue có giới hạn thực tế.
- **PriorityBlockingQueue<E>**: ưu tiên theo thứ tự so sánh, không bảo toàn FIFO và không giới hạn dung lượng bằng một capacity cố định.
- **SynchronousQueue<E>**: không chứa phần tử tồn đọng; mỗi lần đưa phần tử vào cần ghép với một lần nhận tương ứng.

### 2.1. Các thao tác cần phân biệt

| Tình huống | Thao tác | Hành vi |
|---|---|---|
| Producer chờ chỗ trống | **put(e)** | Chờ nếu queue có giới hạn và đang đầy; có thể bị interrupt. |
| Producer không chờ | **offer(e)** | Trả **false** nếu hiện không thể chèn ngay. |
| Producer chờ có thời hạn | **offer(e, timeout, unit)** | Chờ tối đa theo timeout rồi trả kết quả. |
| Consumer chờ dữ liệu | **take()** | Chờ đến khi có phần tử; có thể bị interrupt. |
| Consumer không chờ | **poll()** | Trả **null** khi không có phần tử. |
| Consumer chờ có thời hạn | **poll(timeout, unit)** | Chờ tối đa theo timeout; có thể trả **null**. |

BlockingQueue không chấp nhận phần tử **null**. Một phần tử được **take()** sẽ bị lấy ra khỏi queue, nên hai consumer thông thường **cạnh tranh để nhận các phần tử khác nhau**. Queue không tự phát cùng một phần tử đến mọi consumer.

### 2.2. Áp lực ngược của hàng đợi có giới hạn

Giả sử queue có capacity = 2:

~~~text
Producer --put(A)--> [A,   ] --take()--> Consumer
Producer --put(B)--> [A, B]
Producer --put(C)--> [A, B]  (đợi vì đầy)
Consumer --take()--> [B,   ] (producer có thể tiếp tục put(C))
~~~

Sức chứa hữu hạn tạo **backpressure ở điểm chèn**: producer gọi **put()** phải đợi hoặc chọn chính sách timeout/drop/reject. Đây là cơ chế kiểm soát bằng **dung lượng buffer**, không phải việc consumer cấp từng “quyền nhận” cho producer. Nếu dùng queue gần như không giới hạn, backlog vẫn có thể tăng mạnh khi tốc độ tạo vượt tốc độ xử lý.

### 2.3. Ví dụ chạy được với Java 17+: hàng đợi có giới hạn

Tạo file **BlockingQueueDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public final class BlockingQueueDemo {
    private static final int END = -1;

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);

        Thread producer = new Thread(() -> {
            try {
                for (int n = 1; n <= 3; n++) {
                    queue.put(n);
                }
                queue.put(END);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");
        producer.start();

        while (true) {
            int item = queue.take();
            if (item == END) break;
            System.out.println("item: " + item);
        }
        producer.join();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 BlockingQueueDemo.java
java BlockingQueueDemo
~~~

Kết quả chuẩn:

~~~text
item: 1
item: 2
item: 3
~~~

**Vì sao đúng?** Producer gửi 1, 2, 3 theo thứ tự rồi gửi marker **END**. **ArrayBlockingQueue** bảo toàn FIFO; consumer in từng giá trị đến khi gặp marker. Capacity = 2 khiến producer phải đợi nếu buffer đầy nhưng không làm mất thứ tự. **producer.join()** đợi producer kết thúc.

**Giới hạn của ví dụ:** Marker **-1** là quy ước riêng của ứng dụng. Trong hệ thống có nhiều consumer, cần chiến lược shutdown phù hợp (chẳng hạn số marker tương ứng với số consumer hoặc một cơ chế dừng tập trung). Nếu producer thất bại trước khi gửi marker, consumer có thể đợi vô hạn; ứng dụng thực tế cần xử lý lỗi, timeout, interrupt và hủy công việc.

## 3. Flow API: Publisher, Subscriber, Subscription và Processor

**Flow** là lớp chứa bốn interface chính, không phải một queue hay một engine xử lý hoàn chỉnh:

| Thành phần | Vai trò |
|---|---|
| **Flow.Publisher<T>** | Nguồn phát; cung cấp **subscribe(subscriber)**. |
| **Flow.Subscriber<T>** | Nhận tín hiệu đăng ký, phần tử, lỗi và hoàn tất. |
| **Flow.Subscription** | Liên kết dành riêng cho một Subscriber; hỗ trợ **request(n)** và **cancel()**. |
| **Flow.Processor<T,R>** | Vừa là Subscriber đầu vào vừa là Publisher đầu ra, dùng xây stage chuyển đổi dữ liệu. |

Một luồng tín hiệu cơ bản:

~~~text
Publisher                   Subscriber
    |---- onSubscribe(s) ------>|
    |<------ request(2) --------|
    |--------- onNext(A) ------>|
    |--------- onNext(B) ------>|
    |<------ request(1) --------|
    |--------- onNext(C) ------>|
    |--------- onComplete() --->|
~~~

### 3.1. Demand là một quyền gửi có đếm được

- Khi gọi **subscription.request(n)** với **n > 0**, Subscriber cộng thêm **n** vào demand chưa được đáp ứng của chính subscription đó.
- Publisher chỉ được gọi **onNext** trong phạm vi demand. **request(3)** cho phép *tối đa* 3 lần **onNext** bổ sung, không buộc Publisher phải tạo đủ 3 phần tử ngay.
- Các yêu cầu là cộng dồn; số demand có thể được xem là gần như vô hạn nếu dùng **request(Long.MAX_VALUE)**.
- **request(0)** hoặc số âm là sai hợp đồng: Subscriber phải nhận **onError(IllegalArgumentException)**.
- **cancel()** yêu cầu hủy subscription theo hướng best-effort; có thể còn tín hiệu đang chạy và không bắt buộc có **onComplete()** sau hủy.

**Điểm cốt lõi:** Demand giới hạn số lần gọi **onNext**; nó **không tự động giới hạn lượng dữ liệu mà một Publisher đã sản xuất, đã giữ trong bộ nhớ hoặc đã đặt vào buffer**. Việc giữ dữ liệu, lịch thực thi, chính sách overload và cách đẩy ngược áp lực lên nguồn do implementation quyết định.

### 3.2. Giao thức tín hiệu và vòng đời

1. **onSubscribe(subscription)** đến trước các tín hiệu còn lại của subscription đó. Subscriber nên lưu subscription rồi yêu cầu demand ban đầu.
2. **onNext(item)** được gửi khi còn demand; các callback của **cùng một subscription** diễn ra tuần tự theo thứ tự, không đồng thời với nhau.
3. **onError(throwable)** là tín hiệu kết thúc do lỗi không thể phục hồi; hoặc **onComplete()** là tín hiệu kết thúc bình thường. Sau tín hiệu kết thúc, không có **onNext** tiếp theo của subscription đó.
4. **cancel()** là hành động từ phía Subscriber; không tương đương một **onComplete()** được bảo đảm.
5. Mỗi Subscriber có Subscription và demand riêng; khi Publisher hỗ trợ nhiều Subscriber, một Subscriber chậm có thể có demand và backlog khác Subscriber nhanh.

Đối với **Flow.Processor**, phải tách demand của upstream và downstream. Một Processor xử lý đúng sẽ giới hạn yêu cầu upstream theo khả năng lưu trữ và nhu cầu downstream, thay vì yêu cầu vô hạn rồi giữ hết dữ liệu trong bộ nhớ.

### 3.3. Flow có luôn bất đồng bộ hay không?

**Không.** Các interface của Flow xác định hợp đồng tín hiệu và demand; tự thân chúng không bắt buộc mọi Publisher dùng thread riêng hoặc tuyệt đối không blocking. Cách callback chạy phụ thuộc implementation. Một Publisher có thể dùng executor để giao sự kiện bất đồng bộ; implementation khác có thể thực thi khác. Vì thế cần đọc tài liệu của **Publisher cụ thể**.

## 4. SubmissionPublisher: triển khai sẵn của JDK

**SubmissionPublisher<T>** là triển khai **Flow.Publisher<T>** dùng cho tình huống phát phần tử đến các Subscriber bằng cơ chế giao bất đồng bộ, với buffer **riêng cho từng Subscriber**.

- **subscribe(subscriber)** đăng ký người nhận và gửi **onSubscribe** theo cơ chế của publisher.
- **submit(item)** đưa item đến các Subscriber hiện tại; **có thể chặn thread gọi** nếu tài nguyên/buffer cho một Subscriber không khả dụng. Nó **không** có nghĩa “fire-and-forget, không bao giờ chờ”.
- **offer(item, onDrop)** và overload có timeout cho phép lựa chọn chính sách khi buffer không nhận được dữ liệu; handler có thể yêu cầu thử lại theo hợp đồng. Khi cần không mất dữ liệu, phải thiết kế cách xử lý trường hợp offer không chấp nhận phần tử.
- **close()** kết thúc bình thường sau khi giao các phần tử tồn đọng theo cơ chế publisher; **closeExceptionally(cause)** truyền lỗi kết thúc.
- Buffer mặc định có thể tham khảo qua **Flow.defaultBufferSize()**, nhưng phải kiểm tra capacity và đặc tính thực của Publisher đang dùng; demand và buffer capacity là hai khái niệm tách biệt.

### 4.1. Ví dụ chạy được với Java 17+: nhận từng phần tử theo demand

Tạo file **FlowDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;

public final class FlowDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch completed = new CountDownLatch(1);

        try (SubmissionPublisher<Integer> publisher = new SubmissionPublisher<>()) {
            publisher.subscribe(new Flow.Subscriber<Integer>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription subscription) {
                    this.subscription = subscription;
                    subscription.request(1);
                }

                @Override
                public void onNext(Integer item) {
                    System.out.println("item: " + item);
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable error) {
                    System.err.println("error: " + error);
                    completed.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("done");
                    completed.countDown();
                }
            });

            for (int n = 1; n <= 3; n++) {
                publisher.submit(n);
            }
        }
        completed.await();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 FlowDemo.java
java FlowDemo
~~~

Kết quả chuẩn của lần chạy bình thường:

~~~text
item: 1
item: 2
item: 3
done
~~~

**Giải thích theo trình tự:**

1. Subscriber được cấp một **Subscription** tại **onSubscribe** và gọi **request(1)**.
2. Mỗi lần **onNext(item)** xử lý xong, nó xin tiếp một phần tử bằng **request(1)**. Theo cách này, mỗi lúc chỉ có tối đa một lượt giao **onNext** đang được cấp thêm demand trên subscription đó.
3. **submit()** đưa dữ liệu vào publisher; publisher có thể buffer trước khi callback chạy. Vì vậy, **request(1)** không có nghĩa producer phải đợi xong phần tử đầu mới được gọi **submit()** cho phần tử tiếp theo.
4. **try-with-resources** gọi **close()** trên publisher. **CountDownLatch** cho main thread đợi callback **onComplete** (hoặc **onError**) trước khi thoát, vì callback được giao bất đồng bộ.

Không dùng **Thread.sleep(...)** để “đợi đủ callback”: sleep tạo test chập chờn. Ví dụ sử dụng latch để quan sát việc kết thúc thực sự. Trong ứng dụng production, cần thêm chính sách timeout và hủy nếu nguồn không bao giờ kết thúc.

## 5. So sánh trực tiếp theo tiêu chí thiết kế

| Tiêu chí | Flow API / Publisher–Subscriber | BlockingQueue / Producer–Consumer |
|---|---|---|
| Hình thức giao tiếp | Publisher **đẩy** tín hiệu đến Subscriber có đăng ký. | Consumer **kéo** phần tử bằng **take()/poll()**. |
| Điều tiết tốc độ | Subscriber gửi **request(n)**: demand trên từng subscription. | Producer gặp giới hạn **capacity** khi **put/offer**. |
| Buffer | Không được bảo đảm bởi interface; tùy Publisher. **SubmissionPublisher** dùng buffer trên từng Subscriber. | Queue là buffer chia sẻ; capacity do implementation hoặc constructor quyết định. |
| Nhiều người nhận | Publisher hỗ trợ phát tới các Subscriber; tính broadcast cụ thể phụ thuộc implementation. | Nhiều consumer thường **chia việc**; một phần tử bị lấy ra đúng một lần. |
| Cách chạy | Tùy Publisher/executor; callback có thể bất đồng bộ, hợp đồng Flow không đảm bảo non-blocking. | **put/take** có thể chặn thread gọi. |
| Kết thúc bình thường | Tín hiệu **onComplete()**. | Không có tín hiệu complete chung; tự đặt marker/điều kiện dừng. |
| Kết thúc lỗi | Tín hiệu **onError(Throwable)**. | Không có kênh lỗi tích hợp; tự truyền lỗi qua kết quả, sentinel hoặc cơ chế phối hợp. |
| Hủy | **Subscription.cancel()**, theo best-effort. | Interrupt, cờ dừng, timeout, sentinel hoặc đóng lifecycle bên ngoài queue. |
| Áp dụng phổ biến | Event stream, pipeline theo tín hiệu, phân phối tới Subscriber, xử lý có demand. | Bounded work queue, worker pool, handoff giữa các thread, xử lý task theo từng phần tử. |
| Độ phức tạp | Cần tuân thủ lifecycle, demand, cancellation và terminal signals. | Đơn giản hơn cho một pipeline producer–worker, nhưng cần tự quản shutdown và lỗi. |

**Tránh nhầm lẫn “Flow hiện đại hơn nên luôn tốt hơn”.** Với một worker pool xử lý job theo kiểu mỗi job chỉ có một worker nhận, một **BlockingQueue hữu hạn** thường là cấu trúc trực tiếp và dễ kiểm soát hơn. Với giao diện muốn nhiều Subscriber quan sát dòng phần tử và chủ động cấp demand, **Flow** diễn đạt hợp đồng rõ hơn.

## 6. Hai cơ chế backpressure khác nhau ở đâu?

### 6.1. Ví dụ consumer tạm thời chậm

Giả sử producer có thể sinh 100 phần tử/giây, consumer xử lý 60 phần tử/giây.

**Với ArrayBlockingQueue capacity 200:**

- Khi backlog tăng đến capacity, **put()** bắt đầu chờ.
- Tốc độ thực tế của producer bị ghìm bởi việc chờ queue; nếu thay bằng **offer()**, ứng dụng phải quyết định khi **false** (thử lại, bỏ, log hay chuyển tuyến).
- Queue hữu hạn ngăn việc tồn đọng không giới hạn *trong chính queue*, nhưng không ngăn producer lưu dữ liệu ở một nơi khác trước khi put.

**Với Flow và request theo lô:**

- Subscriber có thể gọi **request(16)**, xử lý dần rồi request thêm khi có năng lực.
- Publisher không được giao **onNext** vượt demand của subscription; tuy nhiên nó vẫn có thể tạo/giữ dữ liệu trong buffer nội bộ trước thời điểm giao.
- Nếu Publisher có buffer hữu hạn, khi buffer đầy nó phải thực thi chính sách của mình: chờ, từ chối, bỏ hoặc điều tiết nguồn. **SubmissionPublisher.submit()** có thể chờ khi một Subscriber chậm làm đầy buffer.
- Một Subscriber khác có thể có demand khác, nên không thể suy ra một capacity hay backlog duy nhất của toàn hệ thống từ **request(n)**.

### 6.2. Backpressure không tự động loại bỏ mọi rủi ro

Cần kiểm soát **cả demand lẫn nơi tích tụ dữ liệu**. Những tình huống dễ gây lỗi:

- Subscriber gọi **request(Long.MAX_VALUE)** nhưng xử lý chậm: nó hầu như đã bỏ giới hạn demand; vẫn phải quản trị buffering.
- Publisher tự sinh hàng triệu item trước khi đọc demand: việc giao **onNext** đúng hợp đồng không cứu được bộ nhớ bị chiếm trước đó.
- Queue không đặt capacity: **put()** gần như không bao giờ chờ do đầy queue cho đến khi tài nguyên hệ thống có vấn đề.
- Subscriber gọi **request(1)** nhưng trong **onNext** lại khởi chạy công việc bất đồng bộ rồi request ngay: callback chỉ xác nhận đã *bàn giao* việc, không có nghĩa công việc thực sự hoàn tất. Demand nên gắn với số công việc đang được phép chạy hoặc giới hạn in-flight riêng.

Một công thức trực giác: nếu tốc độ đến lớn hơn tốc độ xử lý liên tục, backlog có xu hướng tăng. **Backpressure tốt phải truyền áp lực tới nơi tạo dữ liệu hoặc xác định chính sách từ chối/mất dữ liệu**, thay vì chỉ dời backlog sang lớp khác.

## 7. Lifecycle, lỗi, interruption và hủy

### Khi dùng BlockingQueue

- **InterruptedException** từ **put()/take()** là tín hiệu phối hợp dừng. Nếu bắt exception trong worker và không thể ném tiếp, thường cần **Thread.currentThread().interrupt()** và thoát theo chính sách của ứng dụng.
- Không có **queue.close()** chung. Quy ước marker độc lập với dữ liệu thật; nếu có nhiều worker, shutdown phải thức dậy được tất cả worker đang chờ.
- **poll(timeout)** và **offer(timeout)** cho phép tác vụ kiểm tra trạng thái dừng hoặc giới hạn thời gian chờ.
- Một task thất bại không tự báo lỗi tới mọi producer/consumer; cần cơ chế riêng như kết quả lỗi, future, supervisor hoặc shared state.

### Khi dùng Flow

- Nếu **onNext** xử lý đồng bộ lâu, tốc độ xử lý callback của subscription giảm. Nếu xử lý bất đồng bộ, cần quản lý số tác vụ đang chạy.
- Gọi **request(n)** trong **onSubscribe** hoặc sau khi xử lý item theo batch; tránh không request gì khiến luồng đứng yên dù publisher có dữ liệu.
- Với lỗi không thể phục hồi, Publisher/Subscription gửi **onError** rồi dừng; kết thúc bình thường dùng **onComplete**. **onError** và **onComplete** là hai đường kết thúc khác nhau.
- Khi ứng dụng không cần dữ liệu nữa, giữ Subscription và gọi **cancel()**; không chờ **onComplete()** như một lời hứa sau cancel.
- Không nên ném exception ra khỏi callback **onNext** rồi mặc định runtime sẽ retry hoặc xử lý như mong đợi; hành vi lỗi của callback có giới hạn theo hợp đồng và implementation. Cần xử lý hoặc chuyển lỗi có chủ đích.

## 8. Chọn thiết kế cho các trường hợp thực tế

### Trường hợp A: nhiều worker lấy job từ cùng một nguồn

**Chọn BlockingQueue hữu hạn** như **ArrayBlockingQueue** khi mỗi job cần một worker xử lý, số worker cố định và việc chờ hoặc từ chối khi đầy là hợp lý.

~~~text
Producer A --\
Producer B ----> [ bounded BlockingQueue ] ---> Worker 1
                                         \----> Worker 2
~~~

Cần đặt capacity, thời gian chờ, timeout/shutdown và quan sát queue depth. Nếu yêu cầu điều khiển tác vụ phức tạp hơn, cân nhắc các abstraction task execution của JDK, nhưng queue vẫn là thành phần trực tiếp cho handoff.

### Trường hợp B: một nguồn phát sự kiện cho nhiều người nghe

**Chọn Flow Publisher–Subscriber** khi mỗi người nghe cần tín hiệu riêng, muốn điều chỉnh demand độc lập và muốn nhận **onComplete/onError** theo giao thức rõ ràng.

~~~text
                       /--> Subscriber A (request 4)
Publisher --fan-out---<
                       \--> Subscriber B (request 1)
~~~

**SubmissionPublisher** phù hợp để học hoặc xây publisher cục bộ đơn giản. Với throughput lớn, lỗi phức tạp hoặc yêu cầu không mất dữ liệu, cần thiết kế thêm giới hạn buffer, chính sách overload, persistence/retry và kiểm thử thực tế; interface Flow không cung cấp tất cả những chức năng đó.

### Trường hợp C: biến một queue thành nguồn Flow

Có thể viết **Flow.Publisher** lấy dữ liệu từ queue, nhưng adapter đúng phải:

1. Đăng ký một Subscription riêng cho từng Subscriber và theo dõi demand an toàn giữa các thread.
2. Không lấy quá nhiều phần tử khỏi queue khi chưa có chỗ xử lý hoặc demand phù hợp.
3. Xử lý **cancel()**, terminal signals, interrupt, wake-up và shutdown.
4. Quy định rõ chuyển phát dạng **mỗi item một consumer** hay **mọi Subscriber đều nhận cùng item**; một queue dùng chung không tự broadcast.

Chiều ngược lại, nếu đưa **onNext** vào bounded BlockingQueue bằng **put()**, callback có thể chặn thread giao tín hiệu. Khi cần giữ callback ngắn, dùng **offer()** có chính sách overload rõ ràng và chỉ cấp thêm demand khi tài nguyên xử lý thực sự được giải phóng.

## 9. Lỗi nhận thức thường gặp

1. **“Flow là queue với tên khác.”** Sai: Flow định nghĩa giao thức phát luồng, Subscription, demand và terminal events; buffer là chi tiết implementation.
2. **“request(1) nghĩa là producer chỉ được tạo một item.”** Sai: nó hạn chế **onNext** đã giao, không tự hạn chế dữ liệu được tạo hay giữ trước đó.
3. **“SubmissionPublisher.submit không bao giờ chặn.”** Sai: khi không còn buffer cho Subscriber, **submit()** có thể chặn.
4. **“Nhiều consumer đọc BlockingQueue nghĩa là mỗi consumer nhận đủ mọi item.”** Sai: consumer cạnh tranh lấy phần tử.
5. **“onComplete có ngay sau khi gọi close rồi main thoát được.”** Không nên giả định callback bất đồng bộ đã chạy xong; cần đợi điều kiện hoàn tất thực sự khi cần.
6. **“BlockingQueue bất kỳ đều có backpressure nhờ giới hạn dung lượng.”** Sai: phải chọn implementation/capacity phù hợp và phương thức chèn có hành vi mong muốn.
7. **“request(Long.MAX_VALUE) là cách tối ưu mặc định.”** Có thể phù hợp khi không cần flow control, nhưng vô hiệu hóa giới hạn demand hữu ích trong luồng chậm.
8. **“cancel luôn gửi onComplete.”** Sai: cancel là best-effort và không bảo đảm terminal callback.
9. **“Flow tự xử lý mọi race condition.”** Sai: chỉ có những bảo đảm cụ thể về thứ tự callback/demand; trạng thái chia sẻ giữa các thành phần vẫn phải được đồng bộ đúng.
10. **“Chỉ cần cấu hình capacity là đảm bảo không mất dữ liệu.”** Sai: overload, lỗi process, restart và việc dùng **offer** đều cần chính sách đáng tin cậy.

## 10. Checklist khi áp dụng

- **Semantics:** mỗi item được *một worker* nhận, hay *mỗi Subscriber* nhận một tín hiệu?
- **Giới hạn:** capacity queue, capacity buffer từng Subscriber, số job đang xử lý và nguồn tạo dữ liệu đã được giới hạn chưa?
- **Overload:** khi downstream chậm, upstream phải đợi, retry, reject hay drop? Hành vi mất dữ liệu có được chấp nhận không?
- **Lifecycle:** bắt đầu, lỗi, timeout, cancel, interrupt và shutdown có đường đi rõ ràng không?
- **Quan sát:** theo dõi queue depth, thời gian chờ put/take, tốc độ item/giây, độ trễ xử lý, lỗi, dropped item và lag từng Subscriber nếu implementation hỗ trợ.
- **Kiểm thử:** thử consumer rất chậm, không có demand, queue đầy, callback ném lỗi, cancellation giữa chừng và stop khi worker đang chờ.

**Quy tắc chọn nhanh:** dùng **BlockingQueue hữu hạn** cho luồng công việc cần chia giữa các thread; dùng **Flow** khi cần hợp đồng Publisher–Subscriber với **demand, tín hiệu kết thúc/lỗi và khả năng nhiều subscription**. Cả hai đều cần chính sách buffer, tài nguyên và shutdown phù hợp.

## 11. Tài liệu JDK chính thức

- [Flow (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.html)
- [Flow.Subscriber (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html)
- [Flow.Subscription (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
- [SubmissionPublisher (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html)
- [BlockingQueue (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)
