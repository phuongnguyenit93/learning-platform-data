# Lỗi không thể giao cho bên nhận và cơ chế RxJavaPlugins

Trong RxJava, một lỗi thông thường được truyền xuống Subscriber bằng tín hiệu `onError`. Nhưng có những thời điểm Subscriber đã hủy subscription, luồng đã hoàn tất hoặc một lỗi khác đã kết thúc luồng. Khi đó, không còn bên nhận hợp lệ để tiếp nhận lỗi mới.

Những lỗi như vậy được gọi là **undeliverable errors** (lỗi không thể giao cho bên nhận). RxJava chuyển chúng đến cơ chế xử lý lỗi toàn cục `RxJavaPlugins.onError`. Cơ chế này giúp ứng dụng ghi nhận các lỗi đến muộn, vi phạm hợp đồng hoặc lỗi không có error consumer, thay vì để chúng biến mất âm thầm.

Cần phân biệt rõ hai nơi xử lý lỗi:

- Toán tử như `onErrorResumeNext` xử lý lỗi thuộc luồng và có thể thay thế hoặc phục hồi kết quả cho downstream.
- `RxJavaPlugins.setErrorHandler` xử lý lỗi không thể giao cho downstream hoặc lỗi được chuyển tới hook toàn cục.

Handler toàn cục không thay thế việc xử lý lỗi nghiệp vụ trong từng pipeline. Nó là tuyến quan sát và phân loại cuối cùng cho các lỗi không còn đường truyền hợp lệ.

## 1. Vòng đời tín hiệu và thời điểm lỗi không thể giao

Theo Reactive Streams, một subscription có thể phát nhiều `onNext`, sau đó kết thúc bằng đúng một tín hiệu terminal: `onComplete` hoặc `onError`. Sau terminal signal, subscription không được phát thêm tín hiệu dữ liệu hoặc terminal khác.

RxJava áp dụng nguyên tắc tương tự cho Observable, Flowable và các kiểu Publisher khác. Khi downstream đã dispose hoặc luồng đã kết thúc, một lỗi mới không thể được gửi qua `onError` của subscription đó.

Ví dụ về vòng đời hợp lệ:

~~~text
onSubscribe
    |
    v
onNext(value 1)
    |
    v
onNext(value 2)
    |
    v
onComplete
~~~

Ví dụ về tín hiệu đến muộn:

~~~text
onSubscribe
    |
    v
onNext(value)
    |
    v
dispose
    |
    v
onError(late failure)  ---> RxJavaPlugins.onError
~~~

Trong tình huống thứ hai, downstream đã hủy đăng ký. Lỗi đến sau không thể được gửi ngược vào một subscription đã bị dispose. RxJava chuyển lỗi đó tới error handler toàn cục.

Một lỗi không thể giao không nhất thiết là lỗi của thuật toán nghiệp vụ. Nó có thể phát sinh từ một callback bất đồng bộ hoàn tất muộn sau khi người dùng rời màn hình, một request mạng bị hủy hoặc một nguồn phát lỗi sau khi downstream đã nhận kết quả terminal.

## 2. Các nguyên nhân thường gặp

Một số tình huống có thể tạo undeliverable error:

| Tình huống | Vì sao không thể giao? |
|---|---|
| Callback gọi `onError` sau khi downstream dispose | Subscription không còn nhận tín hiệu. |
| Nguồn phát lỗi sau `onComplete` | Luồng đã kết thúc bình thường. |
| Một lỗi thứ hai xuất hiện sau `onError` đầu tiên | Terminal signal đã được gửi. |
| Nhánh `flatMap` khác phát lỗi sau khi một nhánh đã kết thúc toàn luồng | Downstream có thể đã nhận lỗi đầu tiên và các nhánh còn lại bị hủy. |
| `subscribe` không có error consumer và nguồn phát lỗi | Không có callback nghiệp vụ để tiếp nhận lỗi. |
| Callback bất đồng bộ báo lỗi sau khi request hoặc tác vụ đã bị hủy | Kết quả lỗi không còn nơi nhận ban đầu. |

Ví dụ, giao diện đăng ký một nguồn dữ liệu dài hạn. Người dùng đóng màn hình và subscription bị dispose. Sau đó, callback từ thư viện bên ngoài trả về lỗi mạng. Lỗi đó không thể được giao cho màn hình đã đóng.

Một ví dụ khác là nhiều Publisher con chạy đồng thời. Nếu một nhánh lỗi và chính sách mặc định kết thúc toàn bộ pipeline ngay, các nhánh còn lại bị hủy. Một nhánh khác có thể đang hoàn tất với lỗi đúng vào thời điểm hủy, khiến lỗi thứ hai không còn downstream để nhận.

Không nên xem mọi lỗi xuất hiện gần thời điểm dispose là có thể bỏ qua. Một lỗi đến muộn vẫn có thể chỉ ra lỗi cấu hình, lỗi giao thức hoặc một sự cố hệ thống cần điều tra.

## 3. Phân biệt lỗi được giao với lỗi không thể giao

Lỗi được giao là lỗi xuất hiện khi subscription vẫn có thể nhận terminal signal. Downstream có thể xử lý bằng error consumer hoặc toán tử phục hồi:

~~~java
Observable<Order> orders = orderRepository.findOrders()
    .onErrorResumeNext(error -> {
        log.warn("Không tải được đơn hàng", error);
        return Observable.empty();
    });
~~~

Trong ví dụ, lỗi của nguồn được chuyển thành luồng rỗng. Downstream vẫn nhận một kết thúc bình thường sau khi toán tử xử lý lỗi.

Lỗi không thể giao xuất hiện khi đường truyền `onError` không còn hợp lệ. Ví dụ, downstream đã dispose trước khi callback lỗi được gọi:

~~~java
Observable<Order> orders = orderRepository.findOrders();

Disposable disposable = orders.subscribe(
    order -> render(order),
    error -> showError(error)
);

disposable.dispose();
// Một callback lỗi đến sau thời điểm này không thể được giao
// cho Subscriber vừa dispose.
~~~

Nếu một adapter nguồn tự gọi `RxJavaPlugins.onError` cho lỗi đến muộn, handler toàn cục sẽ nhận lỗi đó. Với các emitter do RxJava cung cấp, gọi `onError` sau dispose cũng có thể chuyển lỗi tới plugin.

Điểm quyết định không phải lỗi xảy ra ở tầng nào, mà là subscription còn một bên nhận hợp lệ hay không.

## 4. RxJavaPlugins.onError và setErrorHandler

`RxJavaPlugins` là điểm mở rộng toàn cục của RxJava. Ứng dụng có thể đăng ký error handler bằng `setErrorHandler`:

~~~java
import io.reactivex.rxjava3.plugins.RxJavaPlugins;

RxJavaPlugins.setErrorHandler(error -> {
    log.error("RxJava nhận lỗi không thể giao", error);
});
~~~

Sau khi handler được cài đặt, các lỗi được chuyển đến `RxJavaPlugins.onError` sẽ được gửi đến consumer này.

Nếu không có handler tùy chỉnh, RxJava dùng hành vi mặc định để in lỗi và chuyển nó đến uncaught exception handler của thread hiện tại. Vì vậy, một lỗi không thể giao vẫn có thể xuất hiện trong stderr hoặc log của runtime, ngay cả khi không có Subscriber nhận được nó.

`setErrorHandler` có phạm vi toàn cục trong JVM. Cần cài đặt một lần ở giai đoạn khởi động ứng dụng, nơi cấu hình RxJava được quản lý tập trung. Không nên gọi nó trong từng repository, service hoặc request vì các thành phần có thể ghi đè handler của nhau.

Ví dụ cấu hình ở tầng khởi động:

~~~java
import io.reactivex.rxjava3.exceptions.Exceptions;
import io.reactivex.rxjava3.exceptions.UndeliverableException;
import io.reactivex.rxjava3.plugins.RxJavaPlugins;

public final class RxJavaErrorConfiguration {
    private RxJavaErrorConfiguration() {}

    public static void install() {
        RxJavaPlugins.setErrorHandler(error -> {
            Throwable cause = error;

            if (error instanceof UndeliverableException
                    && error.getCause() != null) {
                cause = error.getCause();
            }

            Exceptions.throwIfFatal(cause);

            log.error("Undeliverable RxJava error", error);
        });
    }
}
~~~

RxJava có thể bọc lỗi không thể giao trong `UndeliverableException` để chỉ ra rằng không còn Subscriber phù hợp. Một số lỗi thuộc nhóm vi phạm hợp đồng hoặc lỗi lập trình có thể được chuyển trực tiếp. Vì vậy, handler nên chấp nhận mọi `Throwable`, kiểm tra wrapper khi cần phân loại và vẫn giữ exception gốc trong log.

`Exceptions.throwIfFatal` bảo đảm các lỗi fatal như lỗi máy ảo không bị xử lý như lỗi ứng dụng thông thường. Không nên bắt rồi bỏ qua mọi `Throwable` trong handler.

## 5. Phân loại lỗi đến muộn thay vì bỏ qua tất cả

Một số lỗi I/O có thể xuất hiện khi thao tác mạng bị hủy. Ví dụ, socket bị đóng trong lúc downstream dispose. Tùy driver và thời điểm hủy, callback có thể báo `IOException` hoặc một exception cụ thể của thư viện mạng.

Có thể phân loại những lỗi đã biết:

~~~java
RxJavaPlugins.setErrorHandler(error -> {
    Throwable cause = error instanceof UndeliverableException
            && error.getCause() != null
        ? error.getCause()
        : error;

    Exceptions.throwIfFatal(cause);

    if (isExpectedCancellationFailure(cause)) {
        log.debug("Bỏ qua lỗi I/O đến sau cancellation", cause);
        return;
    }

    log.error("Lỗi RxJava không thể giao cần điều tra", error);
    errorReporter.capture(error);
});
~~~

`isExpectedCancellationFailure` cần là quy tắc cụ thể của ứng dụng, dựa trên loại exception và bằng chứng cho thấy thao tác đã bị hủy. Không nên viết quy tắc kiểu `cause instanceof IOException` rồi bỏ qua mọi lỗi I/O: cùng loại exception đó cũng có thể biểu thị mất kết nối, lỗi DNS hoặc sự cố dịch vụ cần cảnh báo.

Một chính sách phân loại an toàn nên:

- Giữ lại exception gốc và stack trace.
- Chỉ hạ mức log cho các lỗi đến muộn đã biết và có thể giải thích.
- Gửi lỗi không rõ nguyên nhân đến hệ thống quan sát hoặc error reporter.
- Không bỏ qua lỗi fatal.
- Không thực hiện I/O chặn hoặc công việc kéo dài trong error handler.
- Tránh để chính handler ném lỗi mới.

Nếu handler ném exception, RxJava phải xử lý lỗi của handler theo cơ chế plugin và uncaught exception. Vì vậy, handler nên ngắn, ổn định và không phụ thuộc vào một service có thể đang lỗi.

## 6. OnErrorNotImplementedException và subscribe thiếu error consumer

Một nguyên nhân phổ biến khác là đăng ký Observable mà không cung cấp callback lỗi:

~~~java
source.subscribe(value -> render(value));
~~~

Nếu `source` phát lỗi, không có error consumer nghiệp vụ. RxJava phát sinh `OnErrorNotImplementedException` và chuyển lỗi tới cơ chế plugin toàn cục.

Cách viết an toàn hơn:

~~~java
source.subscribe(
    value -> render(value),
    error -> showError(error)
);
~~~

Hoặc giữ lỗi trong chuỗi toán tử và trả về một Publisher cho tầng gọi xử lý:

~~~java
Observable<Dashboard> dashboard = loadDashboard()
    .onErrorResumeNext(error -> {
        log.warn("Không thể tải dashboard", error);
        return Observable.just(Dashboard.unavailable());
    });
~~~

Không nên dựa vào `RxJavaPlugins.setErrorHandler` để thay thế error consumer cho các luồng nghiệp vụ. Handler toàn cục không biết request nào cần hiển thị thông báo, có nên retry hay cần trả mã lỗi HTTP nào. Những quyết định đó phải được xử lý ở pipeline hoặc tầng gọi phù hợp.

## 7. Dùng tryOnError khi adapter có thể nhận callback muộn

Khi tích hợp API callback, emitter có thể bị dispose trước khi callback lỗi được gọi. `ObservableEmitter` cung cấp `tryOnError` để thử gửi lỗi và trả về kết quả thành công hay thất bại.

~~~java
Observable<Data> data = Observable.create(emitter -> {
    CancellableCall call = legacyClient.fetch(
        result -> {
            if (!emitter.isDisposed()) {
                emitter.onNext(result);
                emitter.onComplete();
            }
        },
        error -> {
            if (!emitter.tryOnError(error)) {
                metrics.increment("rxjava.late_error");
                log.debug("Lỗi đến sau khi emitter đã kết thúc", error);
            }
        }
    );

    emitter.setCancellable(call::cancel);
});
~~~

`tryOnError` trả về `false` khi không thể gửi lỗi vì emitter đã dispose hoặc đã kết thúc. Khác với `onError`, phương thức thử này cho phép adapter tự quyết định cách xử lý trường hợp gửi thất bại mà không tự động chuyển lỗi đó tới plugin.

Điều này hữu ích khi adapter có chính sách riêng, ví dụ đếm metric hoặc gửi lỗi đến một error reporter. Nếu muốn tập trung tất cả lỗi đến muộn tại handler toàn cục, có thể gọi `RxJavaPlugins.onError(error)` khi `tryOnError` trả về `false`:

~~~java
if (!emitter.tryOnError(error)) {
    RxJavaPlugins.onError(error);
}
~~~

Không nên kiểm tra `isDisposed()` rồi mới gọi `onError` như một biện pháp bảo đảm tuyệt đối:

~~~java
if (!emitter.isDisposed()) {
    emitter.onError(error);
}
~~~

Giữa hai lệnh vẫn có thể xảy ra race: downstream dispose ngay sau lần kiểm tra. `tryOnError` phù hợp hơn khi cần biết chính xác việc phát lỗi có thành công hay không.

Với `FlowableEmitter`, cũng có API tương ứng để thử gửi lỗi. Khi tích hợp nguồn callback, cần đọc đúng hợp đồng của emitter và đảm bảo resource được hủy khi downstream dispose.

## 8. Lỗi từ các nhánh đồng thời

Các toán tử hợp nhất nhiều Publisher con có thể gặp nhiều lỗi gần nhau về thời gian. Với chính sách fail-fast mặc định, lỗi đầu tiên có thể kết thúc downstream và hủy các nhánh còn lại. Nếu một nhánh khác báo lỗi trong lúc hủy, lỗi đó có thể trở thành undeliverable.

~~~java
Observable<Result> results = ids
    .flatMap(id -> remoteClient.load(id));
~~~

Nếu nghiệp vụ cần thu thập lỗi từ các nhánh thay vì kết thúc ngay khi gặp lỗi đầu tiên, RxJava có các biến thể trì hoãn lỗi, chẳng hạn `flatMap` với `delayErrors` hoặc `flatMapDelayError` tùy kiểu nguồn và overload.

~~~java
Observable<Result> results = ids
    .flatMap(
        id -> remoteClient.load(id),
        true,
        8
    );
~~~

Trong ví dụ Observable, tham số `true` yêu cầu trì hoãn việc truyền lỗi cho đến khi các nhánh phù hợp kết thúc. Cần chọn overload theo kiểu nguồn và phiên bản RxJava đang dùng.

Trì hoãn lỗi không có nghĩa lỗi được bỏ qua. Nó thay đổi thời điểm lỗi được giao xuống downstream và có thể làm nhiều công việc tiếp tục chạy sau lỗi đầu tiên. Hãy dùng khi nghiệp vụ muốn thu thập kết quả/lỗi từ nhiều nhánh, đồng thời vẫn thiết kế cancellation và timeout cho các nhánh bị treo.

## 9. Không nhầm RxJavaPlugins với toán tử phục hồi lỗi

Hai cơ chế có mục đích khác nhau:

| Cơ chế | Phạm vi | Mục đích |
|---|---|---|
| `onErrorReturn` / `onErrorResumeNext` | Một pipeline | Thay lỗi bằng giá trị hoặc Publisher dự phòng. |
| `retry` | Một pipeline | Đăng ký lại nguồn theo chính sách retry. |
| `doOnError` | Một pipeline | Quan sát lỗi trước khi lỗi tiếp tục đi xuống. |
| `subscribe(onNext, onError)` | Một subscription | Giao lỗi terminal cho callback của bên nhận. |
| `RxJavaPlugins.setErrorHandler` | Toàn JVM | Quan sát và phân loại lỗi không thể giao hoặc lỗi được chuyển đến plugin. |

Ví dụ, lỗi dịch vụ có thể phục hồi bằng retry và fallback:

~~~java
Observable<Profile> profile = profileClient.load(userId)
    .retry(2)
    .onErrorResumeNext(error -> {
        log.warn("Không tải được hồ sơ", error);
        return Observable.just(Profile.guest());
    });
~~~

Nếu pipeline phục hồi thành công, downstream nhận giá trị thay thế. Handler toàn cục không cần tham gia.

Ngược lại, nếu callback báo lỗi sau khi downstream dispose, `onErrorResumeNext` trong pipeline đã bị hủy không còn cơ hội chạy. Khi đó adapter phải xử lý lỗi đến muộn hoặc chuyển nó tới `RxJavaPlugins.onError`.

## 10. Kiểm thử undeliverable error

`RxJavaPlugins` dùng cấu hình tĩnh toàn cục, vì vậy test cần khôi phục trạng thái plugin sau khi chạy. Không nên để handler của một test ảnh hưởng test khác; tránh chạy song song các test thay đổi plugin toàn cục nếu không có cơ chế cô lập.

Ví dụ kiểm tra emitter phát lỗi sau khi downstream dispose:

~~~java
import io.reactivex.rxjava3.core.Observable;
import io.reactivex.rxjava3.core.ObservableEmitter;
import io.reactivex.rxjava3.exceptions.UndeliverableException;
import io.reactivex.rxjava3.plugins.RxJavaPlugins;
import io.reactivex.rxjava3.observers.TestObserver;
import java.io.IOException;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

@Test
void loiSauDisposeDuocChuyenDenPluginHandler() {
    List<Throwable> received = new CopyOnWriteArrayList<>();
    AtomicReference<ObservableEmitter<Integer>> emitterRef =
        new AtomicReference<>();

    RxJavaPlugins.setErrorHandler(received::add);
    try {
        TestObserver<Integer> observer = Observable.<Integer>create(
            emitterRef::set
        ).test();

        observer.dispose();

        emitterRef.get().onError(new IOException("late callback"));

        assertEquals(1, received.size());
        assertInstanceOf(UndeliverableException.class, received.get(0));
        assertInstanceOf(IOException.class, received.get(0).getCause());
    } finally {
        RxJavaPlugins.reset();
    }
}
~~~

Phép thử xác nhận rằng downstream đã dispose nên lỗi từ emitter không thể được giao qua subscription. RxJava chuyển lỗi đến handler toàn cục; lỗi I/O gốc vẫn có thể được lấy từ cause của `UndeliverableException`.

Có thể kiểm thử `tryOnError` riêng:

~~~java
import io.reactivex.rxjava3.core.Observable;
import io.reactivex.rxjava3.core.ObservableEmitter;
import io.reactivex.rxjava3.observers.TestObserver;
import java.io.IOException;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;

@Test
void tryOnErrorTraVeFalseKhiEmitterDaDispose() {
    AtomicReference<ObservableEmitter<Integer>> emitterRef =
        new AtomicReference<>();

    TestObserver<Integer> observer = Observable.<Integer>create(
        emitterRef::set
    ).test();

    observer.dispose();

    boolean delivered = emitterRef.get()
        .tryOnError(new IOException("late callback"));

    assertFalse(delivered);
}
~~~

Trong test này, `tryOnError` không tự gửi lỗi đến plugin. Adapter nhận `false` và có thể chọn ghi metric, log hoặc gọi `RxJavaPlugins.onError` theo chính sách ứng dụng.

Các trường hợp nên kiểm thử thêm:

- `onError` sau dispose được chuyển đến plugin handler.
- `tryOnError` trả về `false` khi emitter đã dispose hoặc kết thúc.
- Nguồn lỗi khi downstream còn hoạt động được giao cho error consumer thông thường.
- `subscribe` không có error consumer tạo lỗi `OnErrorNotImplementedException`.
- Nhiều nhánh lỗi được xử lý đúng theo chính sách fail-fast hoặc delay-errors.
- Handler được reset sau test và không làm rò cấu hình sang test khác.
- Lỗi fatal không bị phân loại thành lỗi có thể bỏ qua.

## 11. Cấu hình và vận hành handler toàn cục

Một handler hữu ích trong production cần có giới hạn và khả năng quan sát:

- Cài đặt một lần khi ứng dụng khởi động, trước khi các luồng cần cấu hình được chạy.
- Ghi exception gốc cùng stack trace; nếu có wrapper, giữ thông tin wrapper và cause.
- Gắn metric theo nhóm lỗi, module nguồn hoặc loại tích hợp nếu có thể xác định.
- Chỉ hạ mức log cho các lỗi đến muộn đã được xác nhận là hệ quả bình thường của cancellation.
- Tránh gọi API chặn, gửi mạng đồng bộ hoặc thực hiện retry trong handler.
- Không ném exception mới từ handler.
- Không dùng handler làm nơi phục hồi nghiệp vụ hoặc phát lại tín hiệu cho Subscriber đã dispose.

`RxJavaPlugins.reset()` xóa các hook plugin toàn cục, không chỉ error handler. Vì vậy, chỉ nên dùng nó trong test hoặc nơi quản lý vòng đời plugin có chủ đích. Không gọi reset tùy tiện trong một request hoặc trong thư viện dùng chung.

Nếu ứng dụng có nhiều module, hãy để một thành phần cấu hình cấp ứng dụng sở hữu handler. Các module khác có thể cung cấp bộ phân loại hoặc error reporter cho thành phần đó, nhưng không nên tự ý thay thế handler toàn cục.

## 12. Quy trình xử lý lỗi không thể giao

Khi nhận một lỗi từ `RxJavaPlugins`, hãy xử lý theo trình tự:

1. Giữ lại exception đầy đủ, gồm wrapper và cause.
2. Nếu cần phân loại, nhận diện `UndeliverableException` và đọc cause.
3. Gọi `Exceptions.throwIfFatal` để không nuốt lỗi fatal.
4. Xác định liệu lỗi có phải hậu quả đã biết của cancellation hay là dấu hiệu của lỗi hệ thống.
5. Ghi log và metric phù hợp; chuyển lỗi không rõ nguyên nhân tới hệ thống quan sát.
6. Kiểm tra lại vòng đời subscription và adapter nguồn để giảm callback đến muộn.
7. Bổ sung test cho race giữa dispose, terminal signal và callback bất đồng bộ.

Không phải mọi undeliverable error đều có thể ngăn chặn. Một callback bên ngoài có thể hoàn tất sau cancellation dù ứng dụng đã gọi cancel đúng cách. Điều quan trọng là phân loại có căn cứ, giữ được thông tin chẩn đoán và bảo đảm lỗi nghiệp vụ khi subscription còn hoạt động vẫn được giao qua pipeline bình thường.

`RxJavaPlugins` là cơ chế xử lý lỗi toàn cục cuối tuyến của RxJava. Dùng toán tử lỗi cho các tình huống nghiệp vụ, cung cấp error consumer cho subscription và cấu hình plugin để quan sát những lỗi không còn bên nhận. Khi hiểu rõ vòng đời terminal, cancellation và race của callback, ứng dụng có thể quản lý lỗi đến muộn mà không che giấu sự cố hoặc làm nhiễu các luồng xử lý khác.

