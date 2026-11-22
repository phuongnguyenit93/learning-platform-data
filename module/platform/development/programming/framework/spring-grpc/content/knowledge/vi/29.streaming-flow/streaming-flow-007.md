# Không gọi onNext sau onError hoặc onCompleted

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả vòng đời hợp lệ của một gRPC stream observer.
- Phân biệt trạng thái đang mở, hoàn tất thành công, kết thúc bằng lỗi và bị hủy.
- Giải thích vì sao mọi lời gọi onNext phải dừng sau onError hoặc onCompleted.
- Phát hiện race condition khi nhiều worker cùng gửi message hoặc kết thúc RPC.
- Tuần tự hóa các callback và bảo đảm chỉ có một terminal event.
- Xử lý cancellation, deadline và lỗi bất đồng bộ an toàn trong dịch vụ Spring gRPC.

## 1. Quy tắc vòng đời của StreamObserver

Trong gRPC Java, **StreamObserver<T>** nhận message qua ba callback:

- **onNext(T)**: chuyển một message khi stream vẫn đang hoạt động.
- **onError(Throwable)**: kết thúc stream vì lỗi.
- **onCompleted()**: kết thúc stream thành công.

Một stream có thể nhận nhiều lần gọi onNext, nhưng chỉ có một lần kết thúc. Sau khi gọi onError hoặc onCompleted, sender phải xem observer đã kết thúc và không gọi thêm bất kỳ callback nào trên observer đó.

Quy tắc này áp dụng cho từng chiều của RPC. Trong server-streaming, service gửi response qua response observer. Trong client-streaming, client gửi request qua request observer mà async stub trả về. Không nhầm observer nhận request ở server với observer gửi response: mỗi observer có một vai trò và một chủ thể gọi khác nhau.

## 2. State machine của một stream

Vòng đời hợp lệ có thể mô tả bằng ba trạng thái chính:

~~~mermaid
stateDiagram-v2
  [*] --> OPEN
  OPEN --> OPEN: onNext
  OPEN --> COMPLETED: onCompleted
  OPEN --> FAILED: onError
  COMPLETED --> [*]
  FAILED --> [*]
~~~

**OPEN** là trạng thái duy nhất cho phép gửi onNext. **COMPLETED** và **FAILED** đều là trạng thái kết thúc. Không có chuyển tiếp hợp lệ từ một trạng thái kết thúc trở lại OPEN hoặc sang terminal state khác.

Ví dụ, chuỗi sau hợp lệ:

~~~text
onNext(A) -> onNext(B) -> onNext(C) -> onCompleted()
~~~

Các chuỗi sau không hợp lệ:

~~~text
onCompleted() -> onNext(D)
onError(error) -> onNext(D)
onCompleted() -> onError(error)
onError(error) -> onCompleted()
~~~

Trong thực tế, một số lỗi chỉ xuất hiện khi có nhiều callback bất đồng bộ. Vì vậy, cần quản lý trạng thái stream tại một điểm điều phối thay vì dựa vào việc mỗi worker tự nhớ đã kết thúc hay chưa.

## 3. Vì sao gọi onNext sau terminal event là lỗi?

Khi observer nhận onCompleted hoặc onError, gRPC coi chiều stream đó đã đóng. Một lần onNext tiếp theo vi phạm contract và có thể gây:

- Exception tại runtime hoặc lỗi nội bộ trong call.
- Message bị bỏ hoặc không được chuyển như ứng dụng mong đợi.
- Log lỗi khó truy nguyên vì producer vẫn tiếp tục chạy sau khi RPC kết thúc.
- Tài nguyên bị giữ lại do worker không dừng.
- Kết quả không xác định khi nhiều thread cùng gửi hoặc kết thúc stream.

Không dựa vào việc một transport cụ thể tình cờ bỏ qua callback thừa. Hành vi đúng phải được bảo đảm ở tầng ứng dụng trước khi gọi observer.

## 4. Hai terminal event có ý nghĩa khác nhau

| Callback | Ý nghĩa | Khi sử dụng |
| --- | --- | --- |
| **onCompleted()** | Kết thúc thành công, không còn message nào nữa | Producer đã hoàn thành và mọi response cần gửi đã được phát. |
| **onError(Throwable)** | Kết thúc do lỗi | Xảy ra lỗi nghiệp vụ, validation, upstream hoặc transport cần kết thúc RPC. |

Không gọi cả hai để “đảm bảo” stream kết thúc. Phải chọn đúng một terminal event. Nếu đã gọi onCompleted, không được gọi onError để báo lỗi phát hiện muộn. Nếu đã gọi onError, không được gọi onCompleted trong khối finally.

Một lỗi xuất hiện sau khi stream đã hoàn tất có thể được ghi nhận bằng log/metric hoặc xử lý ở một workflow khác; không thể thay đổi terminal result của RPC đã kết thúc.

## 5. Mẫu lỗi thường gặp với xử lý bất đồng bộ

Ví dụ không an toàn:

~~~java
void streamPrices(StreamObserver<PriceUpdate> observer) {
    executor.execute(() -> observer.onNext(loadFirstPage()));

    if (isSourceFinished()) {
        observer.onCompleted();
    }
}
~~~

Producer được gửi sang executor, nhưng luồng hiện tại có thể gọi onCompleted ngay khi nguồn báo hoàn tất. Worker sau đó vẫn chạy và gọi onNext trên observer đã kết thúc.

Một lỗi khác là gọi onError trong catch rồi gọi onCompleted trong finally:

~~~java
try {
    observer.onNext(buildResponse());
} catch (RuntimeException ex) {
    observer.onError(ex);
} finally {
    observer.onCompleted(); // Sai: có thể gọi sau onError.
}
~~~

Khối finally phù hợp để giải phóng tài nguyên, không phải để luôn phát onCompleted. Terminal event phải nằm trong một nhánh điều khiển duy nhất.

## 6. Race condition khi nhiều thread cùng gửi

Kiểm tra một boolean riêng rồi gọi observer vẫn có thể sai:

~~~java
if (!terminated.get()) {
    observer.onNext(message);
}
~~~

Có thể xảy ra thứ tự:

1. Worker A đọc terminated là false.
2. Worker B gọi onCompleted và đặt terminated thành true.
3. Worker A tiếp tục gọi onNext sau khi stream đã hoàn tất.

AtomicBoolean chỉ làm thao tác đọc/ghi biến an toàn; nó không tự làm nguyên tử cả cặp thao tác “kiểm tra trạng thái rồi gọi observer”. Cần tuần tự hóa việc kiểm tra và phát callback như một thao tác duy nhất.

Một nguyên nhân khác là hai worker cùng phát terminal event. Nếu cả hai cùng phát hiện lỗi hoặc một worker hoàn tất trong lúc worker khác báo lỗi, observer có thể nhận hai terminal callback cạnh tranh nhau.

## 7. Bảo vệ observer bằng một cổng tuần tự

Với một luồng gửi đơn giản, có thể gom mọi lời gọi qua một lớp phát message có trạng thái được đồng bộ:

~~~java
final class SafeEmitter<T> {
    private enum State {
        OPEN, COMPLETED, FAILED, CANCELLED
    }

    private final StreamObserver<T> delegate;
    private State state = State.OPEN;

    SafeEmitter(StreamObserver<T> delegate) {
        this.delegate = delegate;
    }

    synchronized boolean next(T value) {
        if (state != State.OPEN) {
            return false;
        }
        try {
            delegate.onNext(value);
            return true;
        } catch (RuntimeException ex) {
            state = State.FAILED;
            throw ex;
        }
    }

    synchronized boolean complete() {
        if (state != State.OPEN) {
            return false;
        }
        state = State.COMPLETED;
        delegate.onCompleted();
        return true;
    }

    synchronized boolean fail(Throwable error) {
        if (state != State.OPEN) {
            return false;
        }
        state = State.FAILED;
        delegate.onError(error);
        return true;
    }

    synchronized boolean cancel() {
        if (state != State.OPEN) {
            return false;
        }
        state = State.CANCELLED;
        return true;
    }
}
~~~

Mọi producer phải dùng **SafeEmitter**, không giữ và gọi trực tiếp delegate ở nơi khác. Khóa đồng bộ bao trùm cả kiểm tra trạng thái và callback nên hai thread không thể chen một onNext vào sau terminal event. Callback observer cần được gọi nhanh; không thực hiện truy vấn database hoặc công việc dài trong vùng đồng bộ.

Nếu callback có thể chạy lâu hoặc cần tránh giữ lock khi gọi code bên ngoài, dùng một executor tuần tự làm nơi duy nhất phát tất cả event. Khi đó việc kiểm tra trạng thái và enqueue event cũng phải được đồng bộ; không chỉ đưa callback vào một executor nhưng để producer enqueue onNext sau khi terminal task đã được xếp hàng.

Giá trị false từ next/complete/fail cho biết observer đã terminal hoặc bị hủy. Ứng dụng nên ghi nhận late emission như một lỗi logic, dừng producer và không cố gọi delegate lần nữa.

## 8. Phát response và kết thúc đúng thứ tự

Một server-streaming handler có thể tạo nhiều response bất đồng bộ. Luồng điều phối nên:

1. Tạo response.
2. Gửi response qua emitter khi stream còn OPEN.
3. Khi nguồn hoàn tất, yêu cầu emitter complete.
4. Khi có lỗi trước khi terminal event xảy ra, yêu cầu emitter fail.
5. Nếu một yêu cầu terminal đã thắng, các yêu cầu terminal đến sau không phát thêm callback.

Ví dụ:

~~~java
void publishPrice(
        SafeEmitter<PriceUpdate> emitter,
        PriceUpdate update) {

    if (!emitter.next(update)) {
        stopPriceProducer();
        recordLateEmission();
    }
}

void finishPrices(SafeEmitter<PriceUpdate> emitter) {
    emitter.complete();
}

void failPrices(
        SafeEmitter<PriceUpdate> emitter,
        Throwable error) {
    emitter.fail(Status.INTERNAL
        .withDescription("Price stream failed")
        .withCause(error)
        .asRuntimeException());
}
~~~

Trong code production, chọn status phù hợp với nguyên nhân thực tế thay vì luôn dùng INTERNAL. Không đưa thông tin nhạy cảm hoặc toàn bộ payload vào status description.

## 9. Kết hợp readiness với terminal state

Server-streaming thường dùng **ServerCallStreamObserver.isReady()** và **setOnReadyHandler()** để tránh đẩy quá nhiều response vào buffer gRPC. Readiness không thay đổi quy tắc terminal:

- Chỉ drain queue khi observer ready và emitter còn OPEN.
- Nếu emitter đã terminal, hủy drain task và không gọi onNext.
- Khi queue rỗng và producer hoàn tất, mới yêu cầu complete.
- Nếu producer lỗi trước khi hoàn tất, yêu cầu fail thay cho complete.

Không gọi onCompleted chỉ vì queue tạm thời rỗng; producer có thể vẫn tạo response tiếp theo. Cần có tín hiệu riêng cho biết nguồn đã hoàn tất.

## 10. Phân biệt terminal event với cancellation

Client hủy RPC hoặc deadline hết hạn có thể khiến server nhận tín hiệu cancellation. Đây không phải lý do để tiếp tục gửi onNext, và cũng không nên cố gọi thêm onError/onCompleted trên call đã bị hủy.

Với **ServerCallStreamObserver**, đăng ký cancellation handler:

~~~java
ServerCallStreamObserver<PriceUpdate> response =
    (ServerCallStreamObserver<PriceUpdate>) responseObserver;

SafeEmitter<PriceUpdate> emitter = new SafeEmitter<>(response);

response.setOnCancelHandler(() -> {
    emitter.cancel();
    stopPriceProducer();
    clearPendingWork();
});
~~~

Cancellation đóng đường phát message và dừng nguồn dữ liệu. Không gửi một terminal callback thứ hai chỉ để phản ánh cancellation đã do transport thông báo. Cleanup queue, subscription và tài nguyên phải an toàn khi được gọi nhiều lần.

## 11. Vai trò của client và server observer

Trong client-streaming hoặc bidirectional streaming, cần xác định ai đang gọi observer:

| Vị trí | Observer | Ai gọi onNext? |
| --- | --- | --- |
| Server nhận request stream | Request observer do service trả về | gRPC gọi callback của service khi client gửi request. |
| Server gửi response stream | Response observer được truyền vào service | Service gọi onNext/onError/onCompleted. |
| Client gửi request stream | Request observer do async stub trả về | Client gọi onNext/onError/onCompleted. |
| Client nhận response stream | Response observer client cung cấp | gRPC gọi callback của client. |

Quy tắc không gọi onNext sau terminal event áp dụng cho observer mà ứng dụng đang phát message. Với observer nhận callback từ gRPC, ứng dụng xử lý các callback theo đúng contract và không tự gọi chúng như thể đó là kênh gửi dữ liệu.

## 12. Kiểm thử terminal lifecycle

Các test nên bao phủ:

1. Nhiều onNext rồi đúng một onCompleted.
2. Nhiều onNext rồi đúng một onError.
3. Gọi next sau complete không chuyển thêm message đến delegate.
4. Gọi next sau fail không chuyển thêm message đến delegate.
5. Hai thread cùng yêu cầu complete/fail nhưng chỉ một terminal event được phát.
6. Race giữa next và complete không tạo callback sau terminal.
7. Cancellation dừng producer và ngăn mọi lần phát tiếp theo.
8. Lỗi trong worker không làm finally gọi onCompleted lần thứ hai.

Ví dụ JUnit 5 với observer giả:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.stub.StreamObserver;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class SafeEmitterTest {
    @Test
    void doesNotEmitAfterCompletion() {
        List<String> events = new ArrayList<>();
        StreamObserver<String> delegate = new StreamObserver<>() {
            public void onNext(String value) {
                events.add("next:" + value);
            }
            public void onError(Throwable error) {
                events.add("error");
            }
            public void onCompleted() {
                events.add("completed");
            }
        };

        SafeEmitter<String> emitter = new SafeEmitter<>(delegate);
        assertTrue(emitter.next("first"));
        assertTrue(emitter.complete());
        assertFalse(emitter.next("late"));
        assertFalse(emitter.fail(new IllegalStateException("late error")));

        assertEquals(
            List.of("next:first", "completed"),
            events);
    }
}
~~~

Test trên xác nhận wrapper không gọi delegate sau completion. Bổ sung test đa luồng dùng latch/barrier để ép race giữa next và complete/fail; kết quả hợp lệ phải có một thứ tự tuyến tính và không có next sau terminal event.

## 13. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gọi onCompleted trong finally | Có thể chạy sau onError | Chỉ phát terminal event ở một nhánh điều khiển. |
| Kiểm tra AtomicBoolean rồi gọi onNext bên ngoài | Race giữa check và terminal callback | Đồng bộ cả kiểm tra lẫn phát callback hoặc dùng serial executor. |
| Nhiều worker cùng gọi observer | Hai terminal event hoặc next sau terminal | Một cổng phát callback tuần tự. |
| Tiếp tục producer sau cancellation | Tạo message không còn nơi nhận và giữ tài nguyên | Dừng producer, hủy upstream và cleanup. |
| Gọi onError sau onCompleted để báo lỗi muộn | Vi phạm observer contract | Ghi nhận lỗi ngoài RPC hoặc xử lý bằng workflow khác. |
| Coi queue rỗng là producer đã xong | Complete quá sớm, bỏ response đến sau | Theo dõi riêng trạng thái nguồn hoàn tất. |
| Gọi onNext trực tiếp từ nhiều callback | Sai thứ tự và khó kiểm soát concurrency | Enqueue và dùng một writer. |
| Nuốt late emission mà không quan sát | Lỗi logic bị che giấu | Ghi metric/log và dừng producer. |

## 14. Bài tập thực hành

Một service server-streaming phát tiến độ xử lý báo cáo:

1. Tạo một emitter có các trạng thái OPEN, COMPLETED, FAILED và CANCELLED.
2. Cho nhiều worker tạo progress update nhưng chỉ một cổng được quyền phát response.
3. Khi báo cáo hoàn tất, phát onCompleted đúng một lần sau update cuối.
4. Khi worker lỗi trước khi hoàn tất, phát onError và không phát onCompleted.
5. Cố tình tạo late emission sau terminal event và xác nhận delegate không nhận onNext.
6. Hủy client giữa stream; xác nhận producer dừng và không phát terminal callback thừa.
7. Viết test race giữa onNext và onCompleted bằng nhiều thread.

**Tiêu chí hoàn thành:** không có onNext sau terminal event, chỉ có một terminal event, race được tuần tự hóa và cancellation dừng công việc nền.

## 15. Ghi nhớ

- **onNext** chỉ hợp lệ khi observer còn OPEN.
- **onError** và **onCompleted** là terminal event; chỉ một trong hai được phát và không có callback tiếp theo.
- Kiểm tra trạng thái riêng rẽ bằng AtomicBoolean không đủ nếu check và callback có thể bị thread khác xen vào.
- Tuần tự hóa toàn bộ onNext/terminal event bằng lock có phạm vi phù hợp hoặc một serial executor.
- Không gọi onCompleted trong finally; cleanup và kết thúc RPC là hai trách nhiệm khác nhau.
- Cancellation/deadline phải dừng producer và ngăn phát message tiếp, không tạo terminal callback thứ hai.
- Kiểm thử cả đường thành công, lỗi, late emission và race đa luồng.

Tuân thủ vòng đời StreamObserver giúp dịch vụ Spring gRPC tránh callback sau khi stream đã đóng, loại bỏ race giữa các worker và bảo đảm kết quả streaming nhất quán cho client.
