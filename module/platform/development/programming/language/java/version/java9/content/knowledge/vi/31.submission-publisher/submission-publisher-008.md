# Xây Processor chuyển đổi dữ liệu với Java Flow

Java 9 giới thiệu `java.util.concurrent.Flow`, bộ API chuẩn để xây dựng luồng dữ liệu bất đồng bộ có kiểm soát nhu cầu. Một `Flow.Processor<T, R>` là thành phần trung gian vừa nhận dữ liệu kiểu `T` như một subscriber, vừa phát dữ liệu kiểu `R` như một publisher. Processor thường dùng để biến đổi, lọc, xác thực, chuẩn hóa hoặc gom nhóm dữ liệu trước khi chuyển đến bước tiếp theo.

Ví dụ, một nguồn phát số nguyên có thể đi qua processor để chuyển từng số thành chuỗi, rồi đến subscriber ghi log hoặc lưu trữ. Khi subscriber xử lý chậm, processor cần phối hợp demand và buffer để không tiếp tục nhận dữ liệu vô hạn.

## 1. Vai trò của Processor trong Flow

`Flow.Processor<T, R>` kế thừa cả `Flow.Subscriber<T>` và `Flow.Publisher<R>`. Vì vậy, một processor có hai phía:

- **Upstream:** publisher cung cấp dữ liệu đầu vào `T`; processor nhận `onSubscribe`, `onNext`, `onError` và `onComplete`.
- **Downstream:** subscriber đăng ký vào processor để nhận dữ liệu đầu ra `R`; processor quản lý việc phát các tín hiệu theo hợp đồng publisher.

```text
Source Publisher<T>
       |
       | onSubscribe / onNext / onError / onComplete
       v
Flow.Processor<T, R>
       |
       | subscribe / onSubscribe / onNext / terminal signal
       v
Downstream Subscriber<R>
```

Ví dụ một pipeline:

```text
Publisher<Integer>
       |
       v
Processor<Integer, String>
       |  chuyển 42 thành "value-42"
       v
Subscriber<String>
```

Processor không nhất thiết phải chạy trên một thread riêng. Nó là một thành phần giao thức; việc thực thi đồng bộ hay bất đồng bộ phụ thuộc publisher, executor, buffer và cách processor được cài đặt.

## 2. Hợp đồng của bốn tín hiệu subscriber

Vì processor cũng là subscriber, nó phải xử lý đúng bốn callback:

| Callback | Trách nhiệm trong processor |
| --- | --- |
| `onSubscribe(subscription)` | Lưu subscription upstream và bắt đầu yêu cầu dữ liệu theo khả năng xử lý. |
| `onNext(item)` | Biến đổi hoặc xử lý một phần tử đầu vào rồi phát kết quả downstream. |
| `onError(error)` | Kết thúc luồng đầu ra bằng lỗi tương ứng. |
| `onComplete()` | Kết thúc bình thường luồng đầu ra sau khi xử lý dữ liệu đã nhận. |

Thứ tự tín hiệu tuân theo giao thức Flow: `onSubscribe` đến trước dữ liệu; `onError` hoặc `onComplete` là tín hiệu kết thúc; không phát `onNext` sau tín hiệu kết thúc. Các tín hiệu cho cùng một subscription phải được tuần tự hóa.

Processor phải giữ subscription upstream để có thể gọi `request(n)` khi sẵn sàng nhận thêm dữ liệu hoặc `cancel()` khi không thể tiếp tục.

## 3. Thiết kế một processor biến đổi dữ liệu

Một processor ánh xạ dữ liệu thường có ba phần:

1. Một hàm biến đổi từ `T` sang `R`, ví dụ `Function<T, R>`.
2. Một subscription upstream để điều tiết số phần tử đầu vào.
3. Một publisher downstream để phát các phần tử đã biến đổi.

Với một phép biến đổi một đầu vào thành đúng một đầu ra, chiến lược đơn giản là yêu cầu upstream một phần tử, biến đổi và phát phần tử đó, rồi mới yêu cầu phần tử tiếp theo. Nếu đầu ra được đưa vào buffer giới hạn, buffer đầy sẽ làm chậm việc nhận đầu vào.

Ví dụ processor có thể kế thừa `SubmissionPublisher<R>` để có sẵn publisher bất đồng bộ với buffer riêng cho từng subscriber, đồng thời triển khai `Flow.Processor<T, R>` để nhận dữ liệu upstream.

```java
final class MappingProcessor<T, R>
        extends SubmissionPublisher<R>
        implements Flow.Processor<T, R> {
    // mapper, upstream subscription and callbacks
}
```

`SubmissionPublisher` tự nó là một `Flow.Publisher`, không phải `Flow.Processor`. Việc triển khai `Processor` ở đây là lớp kết hợp publisher có buffer với vai trò subscriber của nguồn đầu vào.

## 4. Kết hợp `SubmissionPublisher` để phát kết quả

`SubmissionPublisher<T>` là implementation có sẵn trong JDK từ Java 9. Nó phát dữ liệu bất đồng bộ qua một `Executor` và duy trì buffer riêng cho từng subscriber.

Constructor thường dùng:

```java
new SubmissionPublisher<T>(executor, maxBufferCapacity)
```

- `executor` quyết định nơi chạy các callback subscriber.
- `maxBufferCapacity` đặt giới hạn buffer cho mỗi subscriber; JDK có thể làm tròn dung lượng theo cách triển khai.
- `submit(item)` gửi phần tử đến các subscriber hiện tại. Nếu buffer của subscriber bị đầy, lời gọi có thể chờ cho đến khi có chỗ.
- `offer(item, onDrop)` cho phép áp dụng chính sách không chờ theo drop handler; phần tử có thể bị bỏ khi subscriber không theo kịp.

Với dữ liệu không được phép mất, `submit` là lựa chọn dễ hiểu vì nó tạo áp lực ngược bằng cách làm chậm producer khi buffer đầy. Nếu dùng `offer` và cho phép drop, phải ghi nhận việc mất dữ liệu và bảo đảm điều đó phù hợp nghiệp vụ.

## 5. Backpressure giữa upstream và downstream

Processor phải kiểm soát hai phía. Upstream có thể phát nhanh hơn downstream xử lý; nếu processor nhận dữ liệu không giới hạn rồi đưa vào một hàng đợi không giới hạn, áp lực ngược sẽ biến mất và bộ nhớ có thể tăng không giới hạn.

Một chiến lược đơn giản cho phép processor chỉ yêu cầu một phần tử upstream tại một thời điểm:

1. Trong `onSubscribe`, lưu subscription và gọi `request(1)`.
2. Trong `onNext`, biến đổi phần tử và gọi `submit(result)`.
3. Chỉ sau khi `submit` hoàn tất, gọi `request(1)` để nhận phần tử kế tiếp.

Với buffer đầu ra giới hạn, `submit` có thể chặn khi downstream chưa tiêu thụ dữ liệu. Trong thời gian đó processor chưa yêu cầu phần tử upstream mới, nhờ vậy áp lực được truyền ngược về nguồn.

Chiến lược này có một phần tử prefetch ban đầu và có thể có một phần tử đang được xử lý. Nó không có nghĩa demand downstream được chuyển tiếp chính xác từng con số lên upstream; nó dùng buffer giới hạn và việc chặn submit để điều tiết nguồn.

### Chọn executor để tránh deadlock

Không nên dùng cùng một single-thread executor cho cả callback upstream và callback downstream nếu `onNext` có thể gọi `submit` và bị chặn khi buffer đầy. Nếu chính thread đó cần chạy subscriber để giải phóng buffer, nó không thể tiến hành cả hai việc và pipeline có thể deadlock.

Trong ví dụ hoàn chỉnh, source publisher dùng `sourceExecutor`, còn processor dùng `processorExecutor`. Khi processor phải chờ buffer có chỗ, executor downstream vẫn có thể chạy subscriber và giải phóng buffer.

## 6. Cài đặt MappingProcessor

Đây là một implementation minh họa cho phép biến đổi một phần tử đầu vào thành một phần tử đầu ra:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Function;

final class MappingProcessor<T, R>
        extends SubmissionPublisher<R>
        implements Flow.Processor<T, R> {
    private final Function<? super T, ? extends R> mapper;
    private final AtomicReference<Flow.Subscription> upstream =
        new AtomicReference<>();

    MappingProcessor(
            ExecutorService executor,
            int maxBufferCapacity,
            Function<? super T, ? extends R> mapper) {
        super(executor, maxBufferCapacity);
        this.mapper = mapper;
    }

    @Override
    public void onSubscribe(Flow.Subscription subscription) {
        if (!upstream.compareAndSet(null, subscription)) {
            subscription.cancel();
            return;
        }
        subscription.request(1);
    }

    @Override
    public void onNext(T item) {
        try {
            submit(mapper.apply(item));
            upstream.get().request(1);
        } catch (RuntimeException error) {
            upstream.get().cancel();
            closeExceptionally(error);
        }
    }

    @Override
    public void onError(Throwable error) {
        closeExceptionally(error);
    }

    @Override
    public void onComplete() {
        close();
    }
}
```

Giải thích:

- `mapper` là hàm biến đổi; dùng `Function<? super T, ? extends R>` để chấp nhận hàm có kiểu tham số tổng quát phù hợp.
- `AtomicReference` lưu subscription upstream và ngăn nhận nhầm subscription thứ hai. Subscription đến sau bị hủy.
- `onSubscribe` yêu cầu một phần tử đầu tiên.
- `onNext` biến đổi phần tử, phát kết quả bằng `submit`, sau đó mới yêu cầu phần tử kế tiếp.
- Nếu hàm biến đổi hoặc thao tác submit ném `RuntimeException`, processor hủy upstream và kết thúc publisher đầu ra bằng `closeExceptionally`.
- `onError` chuyển lỗi thành tín hiệu lỗi downstream; `onComplete` đóng publisher để phát tín hiệu hoàn tất sau các phần tử đã nhận.

Đây là processor minh họa cho một subscription upstream và một phép biến đổi một-một. Ứng dụng production cần bổ sung chính sách rõ ràng cho downstream cancel, nhiều subscriber, lỗi khi đóng, giới hạn thời gian chờ và quản lý vòng đời executor. Khi có nhiều subscriber, một subscriber chậm có thể làm `submit` chờ vì buffer của subscriber đó đầy.

## 7. Chương trình hoàn chỉnh chạy với Java 17

Chương trình dưới đây tạo source publisher, nối qua processor đổi số nguyên thành chuỗi, rồi gửi đến subscriber. Subscriber yêu cầu từng phần tử một. Source và processor dùng hai executor riêng để tránh trường hợp producer bị chặn trên chính thread cần chạy subscriber.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Function;

public class Main {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService sourceExecutor = Executors.newSingleThreadExecutor(
            task -> new Thread(task, "source-worker"));
        ExecutorService processorExecutor = Executors.newSingleThreadExecutor(
            task -> new Thread(task, "processor-worker"));
        CountDownLatch completed = new CountDownLatch(1);
        AtomicInteger received = new AtomicInteger();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        MappingProcessor<Integer, String> processor =
            new MappingProcessor<>(processorExecutor, 1, value -> "value-" + value);

        try {
            processor.subscribe(new Flow.Subscriber<String>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription subscription) {
                    this.subscription = subscription;
                    subscription.request(1);
                }

                @Override
                public void onNext(String item) {
                    System.out.println("received: " + item);
                    received.incrementAndGet();
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable error) {
                    failure.set(error);
                    completed.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("completed: " + received.get());
                    completed.countDown();
                }
            });

            try (SubmissionPublisher<Integer> source =
                     new SubmissionPublisher<>(sourceExecutor, 8)) {
                source.subscribe(processor);
                for (int item = 1; item <= 5; item++) {
                    source.submit(item);
                }
            }

            if (!completed.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("processor pipeline did not complete");
            }
            if (failure.get() != null) {
                throw new AssertionError("processor pipeline failed", failure.get());
            }
            if (received.get() != 5) {
                throw new AssertionError("expected 5 items, got " + received.get());
            }
        } finally {
            processor.close();
            sourceExecutor.shutdown();
            processorExecutor.shutdown();
            if (!sourceExecutor.awaitTermination(5, TimeUnit.SECONDS)
                    || !processorExecutor.awaitTermination(5, TimeUnit.SECONDS)) {
                sourceExecutor.shutdownNow();
                processorExecutor.shutdownNow();
                throw new AssertionError("executors did not terminate");
            }
        }
    }

    private static final class MappingProcessor<T, R>
            extends SubmissionPublisher<R>
            implements Flow.Processor<T, R> {
        private final Function<? super T, ? extends R> mapper;
        private final AtomicReference<Flow.Subscription> upstream =
            new AtomicReference<>();

        MappingProcessor(
                ExecutorService executor,
                int maxBufferCapacity,
                Function<? super T, ? extends R> mapper) {
            super(executor, maxBufferCapacity);
            this.mapper = mapper;
        }

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            if (!upstream.compareAndSet(null, subscription)) {
                subscription.cancel();
                return;
            }
            subscription.request(1);
        }

        @Override
        public void onNext(T item) {
            try {
                submit(mapper.apply(item));
                upstream.get().request(1);
            } catch (RuntimeException error) {
                upstream.get().cancel();
                closeExceptionally(error);
            }
        }

        @Override
        public void onError(Throwable error) {
            closeExceptionally(error);
        }

        @Override
        public void onComplete() {
            close();
        }
    }
}
```

Lưu thành `Main.java`, biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all Main.java
java Main
```

Stdout chính xác:

```text
received: value-1
received: value-2
received: value-3
received: value-4
received: value-5
completed: 5
```

Trong ví dụ, subscriber yêu cầu một phần tử trong `onSubscribe` và yêu cầu phần tử tiếp theo sau mỗi `onNext`. Processor chỉ yêu cầu thêm một phần tử upstream sau khi đã submit kết quả hiện tại. Buffer đầu ra có capacity yêu cầu là 1, nên nếu subscriber ngừng yêu cầu, processor chỉ có thể giữ một lượng dữ liệu giới hạn trước khi `submit` phải chờ.

## 8. Biến đổi dữ liệu theo nhiều kiểu

Processor không chỉ đổi số thành chuỗi. Cùng cấu trúc có thể áp dụng cho nhiều phép biến đổi:

### Chuẩn hóa chuỗi

```java
MappingProcessor<String, String> normalize =
    new MappingProcessor<>(executor, 16,
        value -> value == null ? "" : value.trim().toLowerCase(Locale.ROOT));
```

Trong ứng dụng thật, cần xác định rõ cách xử lý `null`; `SubmissionPublisher` không chấp nhận phần tử null, nên kết quả mapper không được null.

### Chuyển DTO sang sự kiện

```java
MappingProcessor<Order, OrderEvent> toEvent =
    new MappingProcessor<>(executor, 16,
        order -> new OrderEvent(order.id(), order.total()));
```

Kiểu đầu ra nên thể hiện rõ dữ liệu mà downstream cần, tránh chuyển toàn bộ object nội bộ nếu subscriber chỉ cần một phần thông tin.

### Xác thực và biến đổi

Mapper có thể kiểm tra điều kiện rồi tạo object đầu ra. Nếu dữ liệu không hợp lệ, có thể ném exception để processor kết thúc bằng `onError`, hoặc thiết kế kiểu kết quả như `ValidationResult<R>` để biểu diễn lỗi của từng phần tử mà không kết thúc cả luồng.

Quyết định này phụ thuộc nghiệp vụ: một bản ghi lỗi có nên làm dừng toàn bộ pipeline hay chỉ bị đánh dấu và chuyển đến nhánh xử lý lỗi.

## 9. Lọc dữ liệu và phép biến đổi một-nhiều

Processor ở ví dụ trên ánh xạ một phần tử đầu vào thành đúng một phần tử đầu ra. Với bộ lọc, một phần tử có thể không tạo ra đầu ra. Với phép biến đổi một-nhiều, một phần tử đầu vào có thể tạo ra nhiều phần tử đầu ra.

Những trường hợp này làm việc điều tiết demand phức tạp hơn:

- **Filter:** nếu loại bỏ một phần tử, downstream chưa nhận được đầu ra tương ứng. Processor có thể phải yêu cầu thêm upstream để đáp ứng demand còn thiếu.
- **One-to-many:** một phần tử đầu vào có thể tạo ra nhiều kết quả; processor phải giữ các kết quả chưa phát trong buffer giới hạn và không vượt demand downstream.
- **Aggregation:** processor có thể cần nhiều đầu vào mới tạo một đầu ra; cần quyết định cách xử lý khi nguồn hoàn tất nhưng nhóm cuối chưa đủ phần tử.

Không thể luôn thay `request(1)` sau mỗi `onNext` bằng cùng một công thức cho filter, flat-map hoặc aggregation. Hãy tính quan hệ giữa số đầu vào, số đầu ra, demand downstream và kích thước buffer.

## 10. Truyền lỗi và hủy pipeline

Nếu upstream gọi `onError(error)`, processor nên kết thúc output publisher bằng `closeExceptionally(error)` để downstream nhận `onError`. Nếu upstream gọi `onComplete()`, processor gọi `close()` để downstream nhận `onComplete` sau khi các phần tử đã được phát.

Nếu mapper thất bại trong `onNext`, processor nên:

1. Ngừng yêu cầu dữ liệu mới.
2. Hủy subscription upstream nếu pipeline không thể tiếp tục.
3. Đóng publisher đầu ra bằng `closeExceptionally(error)`.
4. Ghi log hoặc metric phù hợp ở ranh giới ứng dụng.

Cancellation cần được thiết kế rõ ở cả hai phía. `SubmissionPublisher` quản lý subscription của các downstream subscriber, nhưng processor tùy chỉnh vẫn cần quyết định khi nào hủy upstream, đặc biệt khi mọi downstream đã cancel hoặc khi processor được đóng thủ công.

Ví dụ minh họa ở trên tập trung vào một subscriber và một upstream. Processor production hỗ trợ nhiều subscriber cần theo dõi subscriber còn hoạt động, demand, cancellation và buffer của từng nhánh; khi không còn downstream nào cần dữ liệu, thường nên hủy upstream để tránh làm việc vô ích.

## 11. `submit` hay `offer` trong processor?

| Phương thức | Khi buffer đầy | Hệ quả |
| --- | --- | --- |
| `submit(item)` | Có thể chờ đến khi buffer có chỗ | Giữ dữ liệu nhưng có thể chặn thread gọi |
| `offer(item, onDrop)` | Gọi drop handler và có thể bỏ phần tử | Không cần chờ theo cách của `submit`, nhưng có nguy cơ mất dữ liệu |

Với pipeline xử lý đơn hàng, giao dịch hoặc sự kiện bắt buộc đầy đủ, drop thường không phù hợp. Với telemetry hoặc trạng thái chỉ cần giá trị mới nhất, có thể dùng `offer` với chính sách drop được ghi nhận rõ ràng.

Không dùng `submit` trên thread duy nhất đang cần chạy subscriber của chính processor. Hãy tách executor hoặc chọn một thiết kế không chặn có queue giới hạn và cơ chế demand rõ ràng.

## 12. Kiểm thử Processor

Kiểm thử không chỉ xác nhận hàm mapper trả kết quả đúng. Cần kiểm tra giao thức và tài nguyên:

1. **Biến đổi cơ bản:** đầu vào `1, 2, 3` tạo đúng đầu ra theo mapper.
2. **Demand từng phần tử:** subscriber request `1` và chỉ nhận tối đa một phần tử trước request tiếp theo.
3. **Buffer đầy:** subscriber chậm; xác nhận processor không tích lũy dữ liệu vô hạn và producer bị điều tiết theo chính sách.
4. **Hoàn tất bình thường:** upstream đóng; processor chuyển `onComplete` xuống downstream sau khi dữ liệu đã xử lý.
5. **Lỗi upstream:** `onError` được chuyển xuống downstream đúng một lần.
6. **Lỗi mapper:** processor hủy upstream và downstream nhận lỗi.
7. **Cancel:** subscriber hủy; xác nhận processor dừng hoặc điều tiết upstream theo chính sách đã thiết kế.
8. **Nhiều subscriber:** xác nhận subscriber chậm không gây hành vi bất ngờ cho subscriber nhanh; hiểu rõ `submit` có thể bị ảnh hưởng bởi buffer của subscriber chậm.
9. **Executor:** xác nhận callback chạy trên executor dự kiến và không dùng chung single-thread executor theo cách gây deadlock.
10. **Đóng tài nguyên:** executor được shutdown sau khi pipeline kết thúc; publisher được đóng đúng lúc.

Đối với kiểm thử bất đồng bộ, dùng `CountDownLatch`, `CompletableFuture` hoặc cơ chế đồng bộ có timeout để chờ tín hiệu kết thúc. Tránh `Thread.sleep` để đoán thời điểm callback chạy.

## 13. Lỗi thường gặp

1. **Nghĩ `SubmissionPublisher` tự là Processor.** Nó chỉ là publisher; muốn biến đổi dữ liệu, cần triển khai `Flow.Processor` hoặc dùng một processor khác.
2. **Không lưu subscription upstream.** Processor không thể yêu cầu thêm dữ liệu hoặc cancel nếu không giữ subscription.
3. **Yêu cầu `Long.MAX_VALUE` ngay lập tức.** Cách này có thể khiến processor nhận dữ liệu nhanh hơn downstream và làm buffer tăng hoặc submit bị chặn lâu.
4. **Yêu cầu phần tử tiếp theo trước khi xử lý đầu ra hiện tại.** Với buffer giới hạn, việc yêu cầu quá sớm có thể làm tăng dữ liệu đang chờ.
5. **Dùng queue không giới hạn.** Điều này loại bỏ lợi ích của backpressure và có thể làm heap tăng không giới hạn.
6. **Dùng cùng một single-thread executor cho upstream và downstream khi submit có thể chặn.** Thread bị chặn có thể chính là thread cần chạy subscriber để giải phóng buffer.
7. **Nuốt exception trong mapper.** Nếu lỗi làm dữ liệu không thể tiếp tục, hãy chuyển thành tín hiệu `onError` hoặc biểu diễn lỗi như một phần tử đầu ra theo hợp đồng.
8. **Không đóng output publisher khi upstream kết thúc.** Downstream sẽ không nhận được tín hiệu hoàn tất.
9. **Không xử lý downstream cancel.** Processor có thể tiếp tục tiêu thụ nguồn dù không còn subscriber cần dữ liệu.
10. **Giả định mọi processor đều một đầu vào thành một đầu ra.** Filter, flat-map và aggregation cần quản lý demand/buffer theo quan hệ khác.
11. **Dùng `offer` nhưng không theo dõi drop.** Dữ liệu bị bỏ có thể làm sai kết quả nghiệp vụ nếu không được tính đến.
12. **Không kiểm tra nhiều subscriber.** Một subscriber chậm có thể làm buffer riêng của nó đầy và khiến `submit` bị chặn.

## 14. Ghi nhớ

1. `Flow.Processor<T, R>` vừa là subscriber của dữ liệu `T`, vừa là publisher của dữ liệu `R`.
2. Processor thường dùng để biến đổi, lọc, xác thực hoặc tổng hợp dữ liệu trong một pipeline.
3. `SubmissionPublisher` là publisher có sẵn từ Java 9; có thể kết hợp nó với `Flow.Processor` để phát dữ liệu bất đồng bộ có buffer.
4. Giữ subscription upstream để gọi `request(n)` và `cancel()`.
5. Chỉ yêu cầu thêm dữ liệu khi processor có khả năng xử lý; buffer giới hạn giúp truyền áp lực ngược về nguồn.
6. `submit` có thể chờ khi buffer đầy; `offer` cho phép drop theo chính sách.
7. Dùng executor riêng phù hợp khi submit có thể chặn, tránh deadlock do cùng một single-thread executor.
8. Chuyển `onError` và `onComplete` từ upstream xuống downstream đúng hợp đồng.
9. Filter, one-to-many và aggregation cần tính demand khác với phép biến đổi một-một.
10. Kiểm thử kết quả, demand, buffer, lỗi, cancellation, nhiều subscriber và vòng đời executor.