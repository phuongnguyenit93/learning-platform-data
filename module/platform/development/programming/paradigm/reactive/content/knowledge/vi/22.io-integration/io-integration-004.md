# Chuyển API hàm gọi lại sang nguồn có thể hủy

## Vì sao cần chuyển callback API thành nguồn reactive?

Nhiều thư viện Java cũ cung cấp API bất đồng bộ thông qua hàm gọi lại (callback). Ứng dụng đăng ký một callback, thư viện thực hiện I/O ở phía dưới rồi gọi lại khi có kết quả hoặc lỗi. Ví dụ thường gặp là client HTTP, SDK của nhà cung cấp, thư viện thiết bị, event listener, message consumer và API đọc dữ liệu theo sự kiện.

Callback API có thể bất đồng bộ, nhưng bản thân nó chưa cung cấp đầy đủ hợp đồng Reactive Streams. Caller thường phải tự quản lý callback, handle hủy, lỗi, thời điểm hoàn tất và việc giải phóng tài nguyên. Khi chuyển API này thành `Mono` hoặc `Flux`, ta có thể kết hợp nó với các toán tử Reactor, điều phối scheduler, kiểm soát demand và truyền cancellation xuyên suốt pipeline.

Một adapter tốt cần giữ đúng vòng đời của API gốc:

- Đăng ký callback khi có subscription, không thực hiện I/O ngay lúc dựng publisher.
- Chuyển callback thành `onNext`, `onComplete` hoặc `onError` phù hợp.
- Liên kết cancellation từ subscriber với thao tác hủy hoặc tháo đăng ký ở thư viện gốc.
- Giải phóng listener và handle khi hoàn tất, lỗi hoặc hủy.
- Có chính sách khi callback phát nhanh hơn khả năng tiêu thụ của downstream.

Nếu API bên ngoài đã triển khai `org.reactivestreams.Publisher` hoặc có adapter chính thức, hãy dùng trực tiếp adapter đó. Chỉ tự viết bridge khi API thực sự chỉ cung cấp callback hoặc một cơ chế bất đồng bộ khác chưa tương thích Reactive Streams.

## Chọn Mono hay Flux theo hợp đồng callback

Trước khi viết adapter, xác định API gốc có thể phát bao nhiêu kết quả và vòng đời của nó kết thúc như thế nào.

| Hợp đồng API gốc | Kiểu Reactor phù hợp | Tín hiệu cần chuyển đổi |
|---|---|---|
| Một kết quả thành công hoặc một lỗi | `Mono<T>` | Callback thành công gọi `sink.success(value)`; lỗi gọi `sink.error(error)` |
| Có thể thành công mà không có giá trị | `Mono<T>` | Gọi `sink.success()` để hoàn tất rỗng |
| Nhiều sự kiện rồi hoàn tất | `Flux<T>` | Mỗi callback gọi `sink.next(value)`; callback kết thúc gọi `sink.complete()` |
| Nhiều sự kiện và có thể lỗi | `Flux<T>` | Chuyển từng sự kiện bằng `next`, lỗi bằng `error` |
| Luồng sự kiện dài hạn, không có tín hiệu hoàn tất tự nhiên | `Flux<T>` | Hủy subscription phải tháo listener hoặc dừng consumer |

Không dùng `Mono` cho API có thể gọi callback thành công nhiều lần. `Mono` chỉ phát tối đa một phần tử; nếu API gốc có nhiều sự kiện, hãy dùng `Flux` và xác định rõ điều kiện hoàn tất.

## Chuyển một callback thành Mono.create

Giả sử một thư viện hồ sơ có API gọi lại và trả về `Disposable` để hủy request hoặc tháo callback:

```java
import reactor.core.Disposable;

interface ResultCallback<T> {
    void onSuccess(T value);
    void onFailure(Throwable error);
}

interface LegacyProfileClient {
    Disposable fetchProfile(String userId, ResultCallback<Profile> callback);
}
```

`Mono.create` cung cấp `MonoSink<T>` để chuyển callback thành tín hiệu reactive. Ví dụ sau trì hoãn việc gọi client đến khi có subscription và liên kết handle của client với vòng đời sink:

Các ví dụ giả định `legacyClient` và `eventClient` là dependency được inject vào adapter, còn `Profile` và `DomainEvent` là kiểu dữ liệu của ứng dụng.

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import reactor.core.Disposable;
import reactor.core.publisher.Mono;

Mono<Profile> findProfile(String userId) {
    return Mono.create(sink -> {
        AtomicReference<Disposable> callRef = new AtomicReference<>();
        AtomicBoolean cleanupRequested = new AtomicBoolean();

        Runnable cleanup = () -> {
            cleanupRequested.set(true);
            Disposable current = callRef.getAndSet(null);
            if (current != null) {
                current.dispose();
            }
        };

        // Cleanup chạy khi thành công, lỗi hoặc downstream hủy.
        sink.onDispose(cleanup::run);

        Disposable call;
        try {
            call = legacyClient.fetchProfile(userId, new ResultCallback<Profile>() {
                @Override
                public void onSuccess(Profile profile) {
                    if (profile == null) {
                        sink.success(); // Hoàn tất rỗng.
                    } else {
                        sink.success(profile);
                    }
                }

                @Override
                public void onFailure(Throwable error) {
                    sink.error(error);
                }
            });
        } catch (RuntimeException error) {
            sink.error(error);
            return;
        }

        // Callback có thể hoàn tất đồng bộ trước khi fetchProfile trả handle.
        if (!callRef.compareAndSet(null, call)) {
            call.dispose();
        }
        if (cleanupRequested.get()) {
            Disposable current = callRef.getAndSet(null);
            if (current != null) {
                current.dispose();
            }
        }
    });
}
```

Điểm quan trọng là callback có thể được gọi ngay trong lúc `fetchProfile` đang đăng ký, trước khi phương thức trả về handle. Khi callback gọi `sink.success` hoặc `sink.error`, `onDispose` có thể chạy trong khi `callRef` vẫn còn rỗng. Cờ `cleanupRequested` ghi nhận yêu cầu dọn dẹp; sau khi handle được trả về, adapter kiểm tra cờ và dispose handle ngay nếu subscription đã kết thúc. `getAndSet(null)` bảo đảm chỉ một đường dọn dẹp lấy được handle để giải phóng.

Ví dụ giả định `Disposable` do client trả về có thao tác `dispose()` idempotent và an toàn sau khi callback đã hoàn tất: nó hủy request nếu còn chạy và tháo đăng ký callback/tài nguyên liên quan. Nếu API gốc phân biệt `cancel request` với `unregister callback`, adapter nên giữ hai thao tác riêng: chỉ cancel khi downstream hủy, nhưng luôn unregister callback khi thành công, lỗi hoặc hủy. Nếu API không cung cấp handle hủy, adapter có thể ngừng chuyển callback sau cancellation nhưng không thể bảo đảm I/O vật lý dừng ngay.

### success, empty và error phải giữ đúng ngữ nghĩa

`MonoSink` có ba cách kết thúc thường dùng:

- `sink.success(value)` phát đúng một giá trị rồi hoàn tất.
- `sink.success()` hoàn tất mà không phát giá trị.
- `sink.error(error)` kết thúc bằng lỗi.

Không biến mọi trường hợp “không tìm thấy” thành lỗi nếu hợp đồng API gốc xem đó là kết quả rỗng. Ngược lại, không chuyển lỗi kết nối hoặc lỗi xác thực thành `success()` vì downstream sẽ hiểu nhầm rằng thao tác thành công nhưng không có dữ liệu.

Một callback one-shot đúng hợp đồng chỉ nên gọi một trong `onSuccess` hoặc `onFailure` một lần. Nếu thư viện có thể gọi callback lặp hoặc cạnh tranh giữa success và failure, adapter cần thêm cơ chế bảo vệ terminal bằng `AtomicBoolean` để chỉ chấp nhận tín hiệu kết thúc đầu tiên; các tín hiệu đến sau phải được bỏ qua hoặc ghi nhận theo chính sách lỗi của ứng dụng.

## Chuyển event listener thành Flux.create

Với API phát nhiều sự kiện, dùng `Flux.create`. Ví dụ một event client đăng ký listener và trả về handle để tháo listener:

```java
import java.util.function.Consumer;
import reactor.core.Disposable;

interface EventListenerClient {
    Disposable listen(
        Consumer<DomainEvent> onEvent,
        Consumer<Throwable> onError,
        Runnable onComplete
    );
}
```

Adapter dưới đây dùng `Flux.create` để nhận callback có thể đến từ nhiều thread. Nó gắn cleanup với `onDispose`, xử lý cả trường hợp callback hoàn tất đồng bộ trong lúc đăng ký và chọn `LATEST` cho một luồng trạng thái mà giá trị mới nhất quan trọng hơn các trạng thái trung gian:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.publisher.FluxSink;

Flux<DomainEvent> watchStatus() {
    return Flux.create(sink -> {
        AtomicReference<Disposable> registrationRef = new AtomicReference<>();
        AtomicBoolean cleanupRequested = new AtomicBoolean();

        Runnable cleanup = () -> {
            cleanupRequested.set(true);
            Disposable current = registrationRef.getAndSet(null);
            if (current != null) {
                current.dispose();
            }
        };

        sink.onDispose(cleanup::run);

        Disposable registration;
        try {
            registration = eventClient.listen(
                event -> {
                    if (!sink.isCancelled()) {
                        sink.next(event);
                    }
                },
                sink::error,
                sink::complete
            );
        } catch (RuntimeException error) {
            sink.error(error);
            return;
        }

        if (!registrationRef.compareAndSet(null, registration)) {
            registration.dispose();
        }
        if (cleanupRequested.get()) {
            Disposable current = registrationRef.getAndSet(null);
            if (current != null) {
                current.dispose();
            }
        }
    }, FluxSink.OverflowStrategy.LATEST);
}
```

`onDispose` chạy khi sink hoàn tất, phát lỗi hoặc bị hủy, nên listener được tháo trong cả ba trường hợp. Cờ và `AtomicReference` xử lý race giữa thời điểm downstream hủy và thời điểm `listen` trả handle. Nếu cancellation đến trước khi handle được gán, cleanup ghi nhận yêu cầu; ngay khi handle xuất hiện, adapter dispose nó.

`LATEST` chỉ phù hợp khi các callback là snapshot trạng thái có thể thay thế nhau, ví dụ phần trăm tiến độ hoặc giá trị cảm biến hiện tại. Nếu mỗi sự kiện là một giao dịch, một message hoặc một audit record phải được giữ đầy đủ, không dùng `LATEST` hay `DROP`. Chọn chiến lược overflow theo hợp đồng dữ liệu, không chỉ theo hiệu năng.

## Chọn Flux.create, Flux.push và chiến lược overflow

`Flux.create` phù hợp với callback có thể được gọi từ nhiều thread. Nó hỗ trợ nhiều lần phát và cung cấp `FluxSink` để chuyển dữ liệu, lỗi, hoàn tất, demand và cancellation. `Flux.push` hướng đến nguồn phát từ một thread duy nhất; không dùng nó nếu thư viện có thể gọi listener đồng thời từ nhiều thread.

| Chiến lược | Hành vi khi downstream không theo kịp | Khi phù hợp |
|---|---|---|
| `BUFFER` | Đệm các phần tử chờ nhận | Chỉ khi lượng dữ liệu có giới hạn hoặc có cơ chế giám sát/giới hạn hàng đợi bên ngoài; buffer mặc định có thể tăng không giới hạn |
| `DROP` | Bỏ phần tử mới khi chưa thể chuyển tiếp | Sự kiện có thể bỏ qua mà không ảnh hưởng tính đúng đắn |
| `LATEST` | Giữ giá trị mới nhất thay cho giá trị chờ cũ | Snapshot trạng thái, tiến độ hoặc số đo mới nhất |
| `ERROR` | Phát lỗi khi không thể chuyển tiếp theo demand | Mất dữ liệu không được chấp nhận và cần báo quá tải rõ ràng |
| `IGNORE` | Không điều tiết tín hiệu theo demand ở sink | Chỉ khi downstream và nguồn có cơ chế kiểm soát khác; nếu downstream không theo kịp, có thể phát sinh lỗi thiếu backpressure |

Với callback API không hỗ trợ pause/resume, `request(n)` từ downstream không thể tự động ngăn thư viện gọi callback. Khi đó, overflow strategy quyết định cách adapter ứng xử. Nếu API gốc hỗ trợ yêu cầu theo lô, acknowledgement hoặc pause/resume, hãy nối demand vào cơ chế đó thay vì chỉ đệm trong adapter.

`FluxSink.onRequest(LongConsumer)` cho phép phản ứng khi downstream yêu cầu thêm dữ liệu. Có thể dùng nó để gọi `request(n)` hoặc resume nguồn bên ngoài nếu API có hỗ trợ. `onCancel` phù hợp để dừng nguồn khi subscriber hủy; `onDispose` phù hợp cho cleanup cần chạy ở mọi kiểu kết thúc. Cần cài hook trước khi nguồn bắt đầu phát để không bỏ lỡ demand hoặc cancellation sớm.

## Nối demand với API callback có hỗ trợ pull

Một số API callback thực chất cung cấp handle có khả năng nhận yêu cầu theo số lượng. Khi đó, adapter có thể chuyển demand từ `FluxSink` sang nguồn. Mô hình tổng quát:

```java
import java.util.function.Consumer;
import reactor.core.Disposable;

interface DemandHandle extends Disposable {
    void request(long count);
}

interface PullCallbackClient {
    DemandHandle listen(Consumer<DomainEvent> onEvent,
                        Consumer<Throwable> onError,
                        Runnable onComplete);
}
```

Trong adapter, đăng ký `sink.onRequest(n -> handle.request(n))` để chuyển nhu cầu xuống nguồn và gắn `handle.dispose()` với cancellation/cleanup. Do handle chỉ có sau khi `listen` trả về, triển khai thực tế cần lưu demand đến sớm trong một bộ đếm an toàn đồng thời rồi chuyển phần demand còn lại sau khi handle được tạo. Nếu API có thể gọi callback đồng bộ ngay trong `listen`, vẫn phải xử lý race giữa phát dữ liệu, demand ban đầu và việc gán handle.

Không gọi `request(n)` lên API gốc nếu hợp đồng của nó không định nghĩa thao tác này. Với nguồn push không thể điều tiết, hãy chọn overflow strategy phù hợp, giới hạn lượng dữ liệu ở tầng nguồn nếu có thể và quan sát tình trạng quá tải.

## Chuyển callback blocking và callback bất đồng bộ khác nhau

Không phải API có callback nào cũng thực hiện I/O bất đồng bộ. Một số thư viện gọi callback ngay trên thread đăng ký hoặc thực hiện công việc blocking trước khi trả handle. Khi đó, việc đặt mã vào `Mono.create` không tự động làm thao tác đăng ký trở nên non-blocking.

Nếu lời gọi đăng ký callback là blocking, cần trì hoãn nó và điều phối trên scheduler phù hợp, ví dụ `Mono.fromCallable` với `subscribeOn(Schedulers.boundedElastic())` cho một thao tác blocking trả kết quả đơn. Với adapter `create`, cần bảo đảm phần đăng ký nguồn không giữ event loop; có thể thiết kế một publisher wrapper có `subscribeOn` hoặc thực hiện bước đăng ký trên scheduler chuyên dụng, đồng thời bảo toàn việc cleanup khi subscriber hủy trong lúc đăng ký.

Nếu API callback vốn bất đồng bộ và việc đăng ký listener nhanh, không cần chuyển nó sang `boundedElastic` chỉ vì có callback. Để client quản lý event loop của nó; callback sẽ gọi sink khi dữ liệu sẵn sàng. Dùng `publishOn` nếu cần chuyển phần xử lý downstream sang scheduler khác, và chỉ dùng scheduler CPU cho phép tính CPU-bound.

## Cancellation phải đi đến API gốc

Khi downstream gọi `dispose()` hoặc một toán tử như `take`, `timeout`, `switchMap` hủy upstream, adapter phải nhận được yêu cầu đó. Việc chỉ kiểm tra `sink.isCancelled()` rồi bỏ qua callback sau hủy giúp ngăn phát tín hiệu không cần thiết, nhưng không dừng request mạng, listener hoặc consumer đang hoạt động.

Một adapter nên gắn từng tài nguyên với đúng subscription:

- Request one-shot: gọi thao tác cancel của request nếu còn đang chạy.
- Event listener: gọi remove/unregister bằng đúng instance listener đã đăng ký.
- Timer: hủy tác vụ đã lên lịch.
- Message consumer: dừng poll hoặc unregister consumer, đồng thời xử lý acknowledgement theo hợp đồng broker.
- Cursor hoặc stream file: đóng tài nguyên khi hoàn tất, lỗi hoặc hủy.

Nếu callback API không có thao tác cancel, hãy nêu rõ giới hạn của adapter: subscriber có thể ngừng nhận kết quả, nhưng I/O bên dưới có thể vẫn chạy đến khi hoàn tất hoặc timeout riêng của thư viện. Không được tuyên bố cancellation đã dừng tác vụ vật lý nếu API gốc không hỗ trợ.

## Lỗi khi đăng ký và lỗi trong callback

Có hai thời điểm lỗi cần xử lý:

1. **Lỗi đồng bộ khi đăng ký:** phương thức `listen` hoặc `fetch` ném exception ngay trong callback tạo nguồn. Bắt exception phù hợp và chuyển thành `sink.error(error)`.
2. **Lỗi bất đồng bộ:** thư viện gọi callback lỗi sau khi đăng ký thành công. Chuyển lỗi đó bằng `sink.error(error)` để downstream có thể dùng `onErrorResume`, `retryWhen` hoặc xử lý ở ranh giới ứng dụng.

Sau `sink.error` hoặc `sink.complete`, nguồn phải dừng callback và giải phóng handle. Nếu thư viện có thể phát nhiều terminal callback, adapter cần bảo vệ để chỉ terminal đầu tiên có hiệu lực. Các callback đến sau khi cancellation hoặc terminal phải được bỏ qua an toàn; không gọi tiếp `sink.next` như thể subscription vẫn hoạt động.

Không biến cancellation thành `onError`. Hủy là lệnh điều khiển; lỗi là tín hiệu terminal. Retry chỉ nên chạy khi publisher phát lỗi phù hợp với chính sách retry, không phải khi người gọi chủ động dừng subscription.

## Kiểm thử adapter callback

Adapter nên được kiểm thử với một fake client có thể điều khiển thời điểm callback và handle hủy. Các trường hợp tối thiểu gồm:

- Chưa subscribe thì client chưa được gọi.
- Thành công tạo đúng một giá trị; kết quả rỗng hoàn tất không có phần tử.
- Lỗi đồng bộ lúc đăng ký và lỗi bất đồng bộ từ callback đều đi xuống `onError`.
- Downstream hủy thì handle của client được dispose hoặc cancel.
- Nguồn hoàn tất hoặc lỗi thì listener/handle được cleanup.
- Callback hoàn tất đồng bộ trước khi hàm đăng ký trả handle vẫn không làm rò rỉ handle.
- Callback phát đồng thời không làm vi phạm hợp đồng sink hoặc gây cập nhật state không an toàn.
- Overflow strategy có hành vi đúng với loại dữ liệu và tốc độ nguồn.

Ví dụ kiểm tra cancellation bằng `StepVerifier` và một handle giả:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import reactor.core.Disposable;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

AtomicBoolean cancelled = new AtomicBoolean();

Mono<String> source = Mono.create(sink -> {
    Disposable handle = () -> cancelled.set(true);
    sink.onDispose(handle::dispose);
});

StepVerifier.create(source)
    .thenCancel()
    .verify();

assert cancelled.get();
```

Kiểm thử này xác nhận cancellation đi đến handle đã đăng ký trong sink. Với adapter thật, fake client nên ghi nhận cả số lần đăng ký, số lần hủy và số lần tháo listener; kiểm tra thêm race khi cancellation xảy ra ngay trong quá trình đăng ký. Dùng virtual time nếu nguồn có timeout hoặc timer để tránh kiểm thử phụ thuộc thời gian thực.

## Những lỗi triển khai thường gặp

- **Gọi API gốc khi dựng publisher:** request chạy dù chưa có subscriber. Đặt thao tác đăng ký bên trong `Mono.create`, `Flux.create` hoặc `defer`.
- **Chỉ chuyển callback mà quên handle hủy:** downstream dispose nhưng request hoặc listener vẫn tồn tại. Gắn handle với `onCancel`/`onDispose`.
- **Chỉ cleanup khi cancel:** listener bị giữ lại sau `onComplete` hoặc `onError`. Dùng `onDispose` cho cleanup chung.
- **Bỏ qua race khi đăng ký:** subscriber hủy trước khi hàm đăng ký trả handle, khiến handle được tạo sau cleanup và bị rò rỉ. Ghi nhận yêu cầu cleanup và dispose handle ngay khi nó xuất hiện.
- **Dùng `Mono` cho callback nhiều lần:** phần tử sau terminal đầu tiên không thể được chuyển đúng. Dùng `Flux` cho luồng nhiều sự kiện.
- **Dùng `Flux.push` cho callback đa thread:** nguồn có thể phát đồng thời từ nhiều thread. Dùng `Flux.create` hoặc tuần tự hóa callback trước khi phát.
- **Chọn `BUFFER` không giới hạn cho nguồn push:** downstream chậm làm hàng đợi tăng liên tục. Chọn overflow theo nghiệp vụ và giới hạn ở tầng nguồn nếu có thể.
- **Xem `sink.isCancelled()` là thao tác hủy I/O:** kiểm tra cờ chỉ ngăn chuyển tiếp callback; cần gọi API cancel/unregister thực tế.
- **Nuốt lỗi đăng ký:** exception đồng bộ bị mất và subscriber không nhận tín hiệu kết thúc. Chuyển thành `sink.error`.
- **Gọi `subscribe()` lồng trong callback adapter:** tạo subscription tách rời, khó phối hợp demand, lỗi và cancellation. Trả publisher để caller ghép vào pipeline.

## Quy trình xây dựng bridge có thể hủy

Khi chuyển một callback API sang Reactor, trước hết xác định cardinality và terminal contract để chọn `Mono` hay `Flux`. Đặt thao tác đăng ký ở thời điểm subscription, chuyển callback thành tín hiệu đúng ngữ nghĩa và chuyển mọi exception phát sinh lúc đăng ký thành `onError`.

Tiếp theo, tìm handle hủy hoặc thao tác unregister của API gốc. Đăng ký cleanup trước khi khởi động nguồn, xử lý race giữa cancellation và việc nhận handle, rồi bảo đảm cleanup chạy khi complete, error và cancel. Với nguồn nhiều sự kiện, chọn `create` hay `push` theo số thread phát và xác định overflow strategy theo khả năng mất dữ liệu.

Cuối cùng, kiểm thử cả đường thành công, rỗng, lỗi, cancellation sớm, callback đồng bộ và callback đồng thời. Một bridge chỉ thực sự tích hợp tốt với Reactive Streams khi nó chuyển đúng tín hiệu, tôn trọng vòng đời subscription và truyền việc dừng công việc về API I/O bên dưới trong phạm vi API đó hỗ trợ.
