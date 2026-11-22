# onSubscribe(), onNext(), onError(), onComplete() trong Java Flow.Subscriber

## 1. Ngữ cảnh: Flow và backpressure trong Java SE

Từ Java 9, `java.util.concurrent.Flow` cung cấp các interface trao đổi dữ liệu bất đồng bộ theo mô hình Reactive Streams. Khi một nguồn tạo dữ liệu nhanh hơn bên nhận có thể xử lý, cơ chế **backpressure** cho bên nhận quyền điều tiết số lượng phần tử được chuyển tới.

- `Flow.Publisher<T>`: nguồn cung cấp phần tử kiểu `T`, cho phép một hoặc nhiều bên đăng ký.
- `Flow.Subscriber<T>`: bên nhận phần tử và các tín hiệu vòng đời.
- `Flow.Subscription`: quan hệ giữa Publisher và một Subscriber cụ thể; `request(long n)` xin nhận thêm phần tử, `cancel()` yêu cầu ngừng nhận.
- `Flow.Processor<T, R>`: vừa nhận dữ liệu kiểu `T` vừa phát kiểu `R`, nhưng không cần để hiểu Subscriber cơ bản.

Một `Flow.Subscriber<T>` cần hiện thực đầy đủ bốn callback:

```java
void onSubscribe(Flow.Subscription subscription);
void onNext(T item);
void onError(Throwable throwable);
void onComplete();
```

Các callback này **được Publisher/Subscription gọi**. Subscriber bình thường không tự gọi chúng để "đẩy" dữ liệu, mà chủ động gọi `request` hoặc `cancel` trên Subscription được trao. Mọi kiến thức dưới đây thuộc **Java concurrency nói chung**, không sử dụng API Spring.

| Callback | Ý nghĩa | Việc thường làm |
| --- | --- | --- |
| `onSubscribe(subscription)` | Đã thiết lập quan hệ nhận dữ liệu | Lưu subscription, yêu cầu demand ban đầu |
| `onNext(item)` | Đã có một phần tử hợp lệ để chuyển tới | Xử lý item, quyết định thời điểm xin thêm |
| `onError(error)` | Upstream gặp lỗi không thể tiếp tục | Ghi nhận lỗi, giải phóng tài nguyên, kết thúc |
| `onComplete()` | Upstream kết thúc bình thường | Dọn tài nguyên, báo hoàn thành |

## 2. Trật tự lời gọi và trạng thái của subscription

Trên **một subscription**, các callback tuân thủ luồng tín hiệu sau:

```text
subscribe(subscriber)
       |
       v
onSubscribe(subscription)
       |
       +-- request(n > 0) --> onNext(item) --> onNext(item) --> ...
       |                         ^                   |
       |                         +---- request thêm -+
       |
       +-- cancel() -------> ngừng nhận (best-effort)

Nhánh kết thúc bình thường: ... -> onComplete()
Nhánh kết thúc vì lỗi:      ... -> onError(throwable)
```

Những quy tắc quan trọng:

1. **`onSubscribe` được gọi trước** các callback khác của subscription tương ứng. Mỗi subscription có demand và vòng đời riêng.
2. **Không có `onNext` nếu không có demand** từ `request(n > 0)` với Publisher tuân thủ giao thức. Mỗi `onNext` tiêu thụ một đơn vị demand.
3. **Lời gọi callback trên cùng subscription có thứ tự nghiêm ngặt (happens-before)**. Chúng không chồng lấn như những lời gọi callback đồng thời cho cùng subscription; tuy nhiên không có bảo đảm tất cả chạy trên một thread cố định. Nhiều subscription khác nhau vẫn có thể chạy song song.
4. **`onError` và `onComplete` loại trừ nhau**: mỗi subscription nhận tối đa một tín hiệu kết thúc; sau tín hiệu terminal không có thêm callback. Một subscription chưa kết thúc hoặc đã bị hủy có thể không nhận terminal.
5. **`cancel()` là yêu cầu dừng best-effort**. Một số thông điệp đang chuyển vẫn có thể đến sau lệnh hủy, và lệnh hủy không bắt buộc sinh ra `onComplete` hay `onError`.

Bảng trạng thái gợi ý cho logic bên nhận:

| Trạng thái | Tín hiệu / hành động | Kết quả |
| --- | --- | --- |
| Chưa đăng ký | `Publisher.subscribe(...)` | Chờ `onSubscribe` |
| Đang hoạt động | `onSubscribe` → `request(n)` | Có quyền nhận tối đa n item |
| Đang hoạt động | `onNext` | Xử lý item, demand giảm 1 |
| Đang hoạt động | `request(n > 0)` | Demand chưa dùng tăng n |
| Đang hoạt động | `onError` | Kết thúc lỗi |
| Đang hoạt động | `onComplete` | Kết thúc thành công |
| Đang hoạt động | `cancel()` | Yêu cầu ngừng, không chờ terminal bắt buộc |

Publisher tùy biến có trách nhiệm giữ các bất biến này. Nếu Publisher vi phạm hợp đồng, Subscriber không thể mặc định tín hiệu nhận được vẫn hợp lệ.

## 3. onSubscribe(Flow.Subscription): nhận quyền điều khiển

`onSubscribe` được gọi đầu tiên, trao cho Subscriber một `Flow.Subscription`. Subscriber lưu nó để có thể yêu cầu dữ liệu hoặc hủy. Ví dụ là một phần của lớp `implements Flow.Subscriber<String>`:

```java
private Flow.Subscription subscription;

@Override
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    subscription.request(1);
}
```

`request(1)` cho phép Publisher gọi **tối đa một `onNext`** bổ sung. Nó không yêu cầu Publisher phải tạo ngay một phần tử, cũng không bảo đảm luôn có dữ liệu. Nếu Subscriber không gọi `request` thì Publisher tuân thủ giao thức sẽ không chuyển phần tử bằng `onNext`, kể cả khi nguồn đã có dữ liệu trong bộ đệm.

### request(n) được cộng dồn như thế nào?

`Flow.Subscription.request(long n)` cộng n vào demand chưa được phục vụ. Nếu đang có demand 2 và gọi `request(3)`, bên phát có thể chuyển tối đa 5 phần tử nữa trước khi cần demand mới. Tổng demand lớn có thể được giới hạn ở mức bão hòa, tránh tràn số học.

- `n > 0`: yêu cầu hợp lệ.
- `n == 0` hoặc `n < 0`: **không phải cách pause**. Hợp đồng yêu cầu phát `onError` với `IllegalArgumentException`.
- `n == Long.MAX_VALUE`: thường được xem là demand thực tế không giới hạn; chỉ nên dùng khi consumer chấp nhận cách cấp quyền này.

Không ghi đè field chứa một subscription đang hoạt động bằng một subscription mới nếu implementation có thể phục vụ nhiều đăng ký. Trong thiết kế đơn giản, dùng một Subscriber riêng cho từng Subscription. Nếu nhận subscription không mong muốn, cần chính sách từ chối/hủy phù hợp; không gộp trạng thái demand của hai luồng vào một biến.

## 4. onNext(T): xử lý item và bổ sung demand

`onNext(T item)` được gọi cho từng phần tử đã được cấp quyền bằng `request`. Với xử lý đồng bộ, mẫu dễ hiểu nhất là **xử lý xong rồi xin thêm một item**:

```java
@Override
public void onNext(String item) {
    System.out.println("Đã nhận: " + item);
    subscription.request(1);
}
```

Đoạn trên giả định field `subscription` đã được lưu ở `onSubscribe`; đây là một phương thức trong lớp Subscriber, chưa phải chương trình hoàn chỉnh.

Ví dụ diễn tiến:

| Sự kiện | Demand còn lại |
| --- | ---: |
| `onSubscribe` gọi `request(1)` | 1 |
| Nhận `onNext("A")` | 0 |
| Xử lý A xong, gọi `request(1)` | 1 |
| Nhận `onNext("B")` | 0 |
| Xử lý B xong, gọi `request(1)` | 1 |
| Nguồn hết dữ liệu, gửi `onComplete` | Kết thúc |

`request(1)` sau mỗi item hỗ trợ kiểm soát nhịp nhận nhưng có overhead nếu mỗi item rất nhỏ. Có thể xin theo lô `request(16)` hoặc `request(32)`, theo dõi số phần tử đã tiêu thụ và cấp bù khi đạt một ngưỡng thích hợp.

**Cẩn trọng với công việc bất đồng bộ:** nếu `onNext` chỉ đưa item vào queue hoặc khởi động một `CompletableFuture` rồi xin item mới ngay, demand thể hiện tốc độ **đưa việc vào queue**, không phải tốc độ hoàn thành việc. Queue có thể tăng vô hạn nếu downstream chậm. Cần điều tiết số tác vụ đang chạy, cấp bù khi có năng lực xử lý và đồng bộ trạng thái với luồng hoàn tất công việc.

Không nên block callback quá lâu bởi I/O hoặc chờ khóa lẫn nhau. Việc giữ `onNext` bận có thể chặn tiến độ gửi các item tiếp theo và tín hiệu terminal.

## 5. onError(Throwable): kết thúc do lỗi upstream

Publisher hoặc Subscription gọi `onError` khi không thể tiếp tục một subscription vì lỗi. `Throwable` mang nguyên nhân, sau đó subscription đã kết thúc và không được nhận thêm `onNext` hay `onComplete`.

```java
@Override
public void onError(Throwable throwable) {
    System.err.println("Nguồn dữ liệu thất bại: " + throwable);
    finished.countDown();
}
```

Ở đây `finished` giả định là `CountDownLatch` thuộc phạm vi lớp Subscriber. Việc báo latch giúp luồng điều phối biết subscription đã có terminal. Trong ứng dụng thực tế, có thể hoàn tất một future bằng exception, ghi log có ngữ cảnh và thu hồi tài nguyên.

Phân biệt:

- **Lỗi do Publisher/Subscription báo**: Subscriber nhận `onError`.
- **Exception do code của Subscriber ném trong `onNext`**: Javadoc không bảo đảm exception ấy được chuyển ngược về **chính** `onError` của Subscriber. Ví dụ `SubmissionPublisher` hủy subscription nếu callback ném lỗi; handler lỗi tùy chọn của nó có thể được gọi.
- **Lỗi nghiệp vụ có thể phục hồi của từng item**: có thể xử lý/biểu diễn bằng dữ liệu tùy thiết kế, không nhất thiết phải kết thúc cả luồng.

Không gọi `onComplete` từ `onError` và không tiếp tục `request` sau terminal. Tránh để chính `onError` ném thêm exception vì hành vi khi callback terminal ném lỗi không được xác định.

## 6. onComplete(): kết thúc bình thường

`onComplete()` báo rằng subscription kết thúc bình thường và không còn callback nào nữa. Phương thức không có tham số:

```java
@Override
public void onComplete() {
    System.out.println("Đã nhận hết dữ liệu");
    finished.countDown();
}
```

`onComplete` không đồng nghĩa "mọi công việc ứng dụng đã hoàn tất": nếu `onNext` trước đó đã giao việc cho executor khác, những công việc đó có thể vẫn chạy. Ứng dụng phải tự theo dõi các tác vụ phụ này.

Với `SubmissionPublisher`, `close()` phát tín hiệu hoàn tất theo cách bất đồng bộ. **`close()` trả về không có nghĩa `onComplete` đã chạy xong.** Vì vậy ở ví dụ dưới, `CountDownLatch` được dùng để chờ terminal thực sự.

## 7. Ví dụ Java 17+ độc lập: quan sát toàn bộ vòng đời

Ví dụ chỉ dùng JDK, gồm `SubmissionPublisher<String>`, `Flow.Subscriber<String>` và `CountDownLatch`. `onError` được cài đặt nhưng đường đi bình thường không kích hoạt nó.

Tạo file `FlowLifecycleDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;

public class FlowLifecycleDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch finished = new CountDownLatch(1);

        try (SubmissionPublisher<String> publisher = new SubmissionPublisher<>()) {
            publisher.subscribe(new Flow.Subscriber<>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription subscription) {
                    this.subscription = subscription;
                    System.out.println("onSubscribe");
                    subscription.request(1);
                }

                @Override
                public void onNext(String item) {
                    System.out.println("onNext: " + item);
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable throwable) {
                    System.out.println("onError: " + throwable);
                    finished.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("onComplete");
                    finished.countDown();
                }
            });

            publisher.submit("A");
            publisher.submit("B");
            publisher.close();
            finished.await();
        }
    }
}
```

Biên dịch, chạy từ thư mục chứa file:

```shell
javac FlowLifecycleDemo.java
java FlowLifecycleDemo
```

Output đúng của ví dụ (một Subscriber):

```text
onSubscribe
onNext: A
onNext: B
onComplete
```

Đã kiểm thử đoạn mã này bằng JDK 24 (mã sử dụng API chạy được từ Java 17). Những điểm cần nhận ra:

1. `subscribe` thiết lập subscription, callback `onSubscribe` nhận nó và xin 1 item.
2. Hai lệnh `submit` đưa "A" rồi "B" vào publisher. Việc chuyển tới Subscriber là bất đồng bộ; không được coi `submit` đã đợi `onNext` hoàn tất.
3. Demand ban đầu cho phép nhận A; xử lý A xong Subscriber xin thêm 1, do đó được nhận B.
4. `close` thông báo không còn phần tử được phát; `onComplete` xuất hiện sau các item trong cùng subscription.
5. `finished.await()` khiến thread `main` chờ đến khi callback terminal đã chạy.
6. `SubmissionPublisher` có thể dùng thread khác thread gọi `submit`; **trật tự callback của một subscription vẫn được giữ**.

### Thử nhánh onError

Trong chương trình trên, thay **chính ba dòng**:

```java
publisher.submit("A");
publisher.submit("B");
publisher.close();
```

bằng:

```java
publisher.closeExceptionally(new IllegalStateException("upstream failed"));
```

Output kỳ vọng của lần chạy thay thế:

```text
onSubscribe
onError: java.lang.IllegalStateException: upstream failed
```

Ở lần này Publisher chủ động đóng bằng lỗi, vì vậy không có `onNext` và không gọi `onComplete`. Đây là ví dụ lỗi upstream được báo bằng `onError`, không phải chứng minh rằng exception tự ném trong `onNext` sẽ tạo ra cùng hành vi.

## 8. Cấp demand theo lô, hủy và giới hạn backpressure

**Cấp theo từng phần tử:** sử dụng `request(1)` trong `onSubscribe` rồi cấp bù từng item. Dễ lý giải, phù hợp khi xử lý item chậm hoặc cần kiểm soát sát năng lực tiếp nhận.

**Cấp theo lô:** có thể khởi đầu với `request(32)`, rồi mỗi khi xử lý 16 phần tử sẽ cấp bù `request(16)`. Khi đó lượng demand chưa được phục vụ dao động quanh một khoảng thay vì gọi `request` cho từng item. Ví dụ ý tưởng sau là *pseudocode*, không phải chương trình Java đầy đủ:

```text
onSubscribe:
    subscription.request(32)
    remaining = 32

onNext(item):
    process(item)
    remaining--
    if remaining == 16:
        subscription.request(16)
        remaining += 16

onError / onComplete:
    cleanup
    stop requesting
```

Khi dùng batch, cần định nghĩa "xử lý xong" là xử lý đồng bộ hay việc bất đồng bộ đã thực sự hoàn tất, vì đó là thời điểm thích hợp để bổ sung năng lực nhận.

**Hủy giữa chừng:** gọi `subscription.cancel()` khi không cần dữ liệu nữa, ví dụ người dùng hủy tác vụ. `cancel` là best-effort: tín hiệu đang bay tới có thể còn được chuyển và subscription không bắt buộc nhận terminal. Vì vậy logic hủy cần một đường thu hồi tài nguyên riêng.

**Demand không phải kích thước bộ đệm.** `request(n)` chỉ cấp quyền chuyển tối đa n item qua `onNext`; nó không ép mọi Publisher giới hạn nội bộ ở n item. `SubmissionPublisher` dùng bộ đệm riêng cho từng subscriber. Phương thức `submit` có thể chờ tài nguyên khi buffer đầy, còn `offer` có các chính sách từ chối/drop. Thiết kế hệ thống thực tế phải phối hợp demand, buffer, executor, tốc độ upstream và chính sách xử lý lỗi.

## 9. Các lỗi hay gặp

| Lỗi hoặc triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Đăng ký rồi không nhận được item | Chưa gọi `request` | Xin demand dương trong `onSubscribe` |
| Nhận một item rồi "đứng" | Chỉ `request(1)` một lần | Xin tiếp sau khi đủ khả năng xử lý thêm |
| Nhận `IllegalArgumentException` qua `onError` | Gọi `request(0)` hoặc số âm | Chỉ dùng n dương; không dùng request(0) để pause |
| Queue tăng không kiểm soát | Xin quá nhiều hoặc cấp bù trước khi việc async xong | Giới hạn số việc đang xử lý và cấp bù theo năng lực thực |
| Chương trình thoát trước khi thấy callback cuối | Publisher phát tín hiệu bất đồng bộ | Chờ tín hiệu terminal bằng latch/future khi phù hợp |
| Chờ `onComplete` sau `cancel` | Hủy không bảo đảm terminal | Hoàn tất nhánh hủy bằng cơ chế riêng |
| Nghĩ callback luôn chạy trên một thread | Publisher dùng executor | Chỉ dựa vào thứ tự theo subscription; đồng bộ trạng thái chia sẻ với thread khác |
| Ném exception từ `onNext` và chờ `onError` | Không có bảo đảm chuyển tiếp lỗi theo cách đó | Quản lý lỗi downstream và cancellation rõ ràng |
| Vẫn gọi request sau `onComplete` | Không theo dõi terminal | Đánh dấu kết thúc, giải phóng tài nguyên |

## 10. Câu hỏi kiểm tra hiểu biết

**Q1. Vì sao `onSubscribe` thường gọi `request` ngay?** Vì khi chưa có demand, Publisher tuân thủ Flow sẽ không gọi `onNext`; đây là nơi Subscriber lấy quyền điều khiển nhịp nhận.

**Q2. `request(5)` có nghĩa chắc chắn nhận được năm phần tử không?** Không; chỉ cho phép **tối đa năm** `onNext` thêm. Publisher có thể không còn dữ liệu hoặc kết thúc trước đó.

**Q3. Có thể gọi `onComplete` sau `onError` không?** Không, nếu tuân thủ hợp đồng. Một subscription có tối đa một terminal.

**Q4. `onComplete` có đợi mọi `CompletableFuture` được tạo trong `onNext` không?** Không; ứng dụng cần quản lý những công việc bất đồng bộ riêng của mình.

**Q5. Stream chạy vô hạn có bắt buộc gọi `onComplete` không?** Không. Nếu còn hoạt động, có thể không có terminal; ứng dụng có thể dùng `cancel`, timeout hoặc cơ chế dừng khác.

**Q6. API này khác Java `Stream` như thế nào?** `Flow` mô tả giao tiếp bất đồng bộ và demand giữa nguồn và người nhận; `java.util.stream.Stream` chủ yếu cung cấp thao tác xử lý tập dữ liệu qua pipeline và không sử dụng bốn callback này.

## 11. Ghi nhớ và tài liệu tham khảo

- `onSubscribe`: nhận Subscription và yêu cầu demand dương.
- `onNext`: xử lý một item; chỉ cấp bù khi có năng lực xử lý thêm.
- `onError`: terminal vì lỗi; sau đó không có callback khác.
- `onComplete`: terminal thành công; sau đó không có callback khác.
- `request` điều tiết lượng dữ liệu có thể chuyển, `cancel` yêu cầu ngừng theo best-effort.
- Thứ tự callback bảo đảm theo **từng subscription**, không mặc định cùng thread; đừng nhầm demand với buffer hoặc việc hoàn thành callback với hoàn thành công việc async.

Đọc thêm Javadoc chính thức của Java SE:

- [`Flow`: mô hình và ví dụ backpressure](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html)
- [`Flow.Subscriber`: hợp đồng bốn callback](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html)
- [`Flow.Subscription`: `request` và `cancel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
- [`SubmissionPublisher`: phát bất đồng bộ và tín hiệu kết thúc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html)