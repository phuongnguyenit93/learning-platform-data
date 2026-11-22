# `request(n)` và demand-driven consumption trong Java Flow

## 1. Vấn đề cần giải quyết

Giả sử một nguồn phát ra 100.000 sự kiện/giây nhưng thành phần xử lý chỉ theo kịp 2.000 sự kiện/giây. Nếu nguồn cứ đẩy dữ liệu và bên nhận cứ phải nhận, hàng đợi có thể lớn dần, tăng độ trễ, tiêu tốn bộ nhớ hoặc làm hệ thống quá tải. Cơ chế **backpressure** trong mô hình Publisher–Subscriber cho phép phía nhận chủ động cho biết mình sẵn sàng nhận thêm bao nhiêu phần tử.

Trong Java, API chuẩn `java.util.concurrent.Flow` (từ Java 9) mô tả giao thức này. Trọng tâm của bài là **`Flow.Subscription.request(long n)`**: Subscriber cấp thêm quyền gửi (demand) cho Publisher. Publisher chỉ được gọi `onNext` khi subscription còn demand và không được gửi nhiều phần tử hơn lượng đã được yêu cầu. Đây là cơ chế điều phối số lượng phần tử giữa hai phía, không phải cơ chế giới hạn tốc độ theo đơn vị thời gian.

## 2. Bốn vai trò và vòng đời của subscription

| Vai trò | Trách nhiệm |
|---|---|
| `Flow.Publisher<T>` | Nhận đăng ký qua `subscribe(subscriber)`, cung cấp các phần tử và tín hiệu kết thúc/lỗi. |
| `Flow.Subscriber<T>` | Nhận `onSubscribe`, `onNext`, `onError`, `onComplete`; quyết định khi nào yêu cầu thêm. |
| `Flow.Subscription` | Liên kết một Publisher với một Subscriber; cung cấp `request(n)` và `cancel()`. |
| `Flow.Processor<T,R>` | Vừa là Subscriber ở phía upstream, vừa là Publisher ở phía downstream; cần phối hợp demand qua hai phía. |

Một luồng tín hiệu thông thường:

```text
Publisher                   Subscription                  Subscriber
    |                            |                             |
    | -- onSubscribe(s) --------------------------------------> |
    |                            | <-------- request(2) ------- |
    | --------------------- onNext(item 1) ------------------> |
    | --------------------- onNext(item 2) ------------------> |
    |           (demand còn lại = 0; dừng gửi onNext)          |
    |                            | <-------- request(1) ------- |
    | --------------------- onNext(item 3) ------------------> |
    | --------------------- onComplete() --------------------> |
```

`onSubscribe` diễn ra trước các tín hiệu dữ liệu hoặc kết thúc. Một subscription **khởi đầu với demand bằng 0**: chỉ đăng ký chưa có nghĩa đã được phép gửi item. Sau `onError` hoặc `onComplete`, luồng tín hiệu đã kết thúc và không có `onNext` tiếp theo.

## 3. Chính xác `request(n)` có nghĩa gì?

`subscription.request(n)` với `n > 0` **cộng thêm** `n` quyền nhận phần tử vào demand *chưa được đáp ứng* của subscription đó. Mỗi lần Publisher phát thành công một `onNext`, nó tiêu thụ một quyền. Đây không phải lệnh “gửi đúng n phần tử ngay bây giờ”, cũng không phải đặt lại cửa sổ demand thành n.

Ví dụ tuần tự:

| Hành động | Demand chưa đáp ứng | Ý nghĩa |
|---|---:|---|
| `onSubscribe(s)` | 0 | Chưa được phép phát `onNext`. |
| `s.request(2)` | 2 | Tối đa hai item có thể được gửi. |
| Nhận một `onNext` | 1 | Một quyền đã được sử dụng. |
| `s.request(3)` | 4 | Cộng thêm 3 vào lượng còn lại là 1. |
| Nhận bốn `onNext` | 0 | Phải chờ yêu cầu mới để gửi tiếp. |

Các quy tắc cần nhớ:

- **`request(n > 0)` là cộng dồn.** Hai lần `request(3)` liên tiếp có thể cho phép tối đa sáu item, chứ không phải ba. Publisher có thể gửi ít hơn nếu chưa có dữ liệu, đã kết thúc hoặc bị hủy.
- **`request(0)` và `request(n < 0)` là sai giao thức.** Theo hợp đồng `Flow.Subscription`, Subscriber sẽ nhận `onError` với `IllegalArgumentException`. Muốn tạm ngừng cấp thêm demand, hãy *không gọi* `request`; không dùng `request(0)` để pause.
- **`request(Long.MAX_VALUE)` thường được xem như yêu cầu không giới hạn.** Chỉ dùng khi bên nhận thật sự có thể chịu được luồng dữ liệu hoặc có cách kiểm soát riêng.
- **Demand là theo từng subscription.** Hai Subscriber của cùng Publisher có thể có số quyền nhận khác nhau; không được lấy demand của Subscriber A để phát dữ liệu cho B.
- **Tín hiệu kết thúc không phải item.** `onComplete`/`onError` không tiêu thụ demand; một nguồn có thể kết thúc dù không còn phần tử được yêu cầu. Chúng chỉ được phát theo quy tắc vòng đời của Publisher.

Có thể hình dung bất biến an toàn ở một subscription đang hoạt động là **số `onNext` đã gửi không vượt tổng số phần tử đã được yêu cầu** (với quy tắc xử lý bão hòa khi demand rất lớn). Trong implementation thực tế, bộ đếm phải chống tràn số và an toàn trước truy cập đồng thời; không tự cộng `long` theo cách có thể overflow sang số âm.

## 4. Ví dụ 1 — Nhìn thấy demand mở và đóng cửa gửi dữ liệu

Ví dụ sau dùng một Publisher tối giản, chạy **đồng bộ trên một thread**, để quan sát chính xác lúc nào item được phát. Nó dành cho học tập: không dùng implementation này như Publisher production đa luồng, vì chưa xử lý đồng thời/reentrancy khi `request` được gọi lồng nhau.

Lưu với tên `ManualDemandDemo.java`:

```java
import java.util.Objects;
import java.util.concurrent.Flow;

public class ManualDemandDemo {
    static final class FixedPublisher implements Flow.Publisher<Integer> {
        @Override
        public void subscribe(Flow.Subscriber<? super Integer> subscriber) {
            Objects.requireNonNull(subscriber);

            subscriber.onSubscribe(new Flow.Subscription() {
                private int next = 1;
                private boolean stopped;

                @Override
                public void request(long n) {
                    if (stopped) return;

                    if (n <= 0) {
                        stopped = true;
                        subscriber.onError(
                            new IllegalArgumentException("n must be > 0"));
                        return;
                    }

                    long delivered = 0;
                    while (delivered < n && next <= 3 && !stopped) {
                        subscriber.onNext(next++);
                        delivered++;
                    }

                    if (next > 3 && !stopped) {
                        stopped = true;
                        subscriber.onComplete();
                    }
                }

                @Override
                public void cancel() {
                    stopped = true;
                }
            });
        }
    }

    public static void main(String[] args) {
        Flow.Subscription[] subscription = new Flow.Subscription[1];

        new FixedPublisher().subscribe(new Flow.Subscriber<>() {
            @Override
            public void onSubscribe(Flow.Subscription s) {
                subscription[0] = s;
                System.out.println("Đăng ký; demand = 0");
            }

            @Override
            public void onNext(Integer item) {
                System.out.println("onNext " + item);
            }

            @Override
            public void onError(Throwable error) {
                System.out.println("onError " + error.getClass().getSimpleName());
            }

            @Override
            public void onComplete() {
                System.out.println("onComplete");
            }
        });

        System.out.println("request(2)");
        subscription[0].request(2);
        System.out.println("request(1)");
        subscription[0].request(1);
    }
}
```

Chạy với Java 17 trở lên:

```bash
javac ManualDemandDemo.java
java ManualDemandDemo
```

Kết quả chuẩn trong ví dụ đồng bộ:

```text
Đăng ký; demand = 0
request(2)
onNext 1
onNext 2
request(1)
onNext 3
onComplete
```

Sau lần `request(2)`, nguồn chỉ gửi 1 và 2 rồi dừng, dù còn sẵn giá trị 3. Lần `request(1)` tiếp theo mới mở quyền gửi giá trị 3. `onComplete` xuất hiện khi nguồn đã phát hết dữ liệu. Nếu thay `request(1)` cuối bằng `request(0)`, ví dụ phát `onError IllegalArgumentException`, không phải `onComplete`.

**Giới hạn của ví dụ:** vì `request` thực hiện vòng lặp ngay trên thread gọi, đừng cho `onNext` của ví dụ này gọi lại `request` hoặc gọi từ nhiều thread. Publisher dùng thực tế cần điều phối một vòng phát (drain loop), serialize các callback, giữ bộ đếm demand thread-safe và xử lý hủy/kết thúc đúng một lần.

## 5. Ví dụ 2 — Consumer chỉ xin phần tử tiếp theo sau khi xử lý xong

`SubmissionPublisher<T>` là implementation chuẩn có sẵn trong `java.util.concurrent`. Nó chuyển tín hiệu bất đồng bộ tới Subscriber và quản lý buffer theo từng Subscriber. Subscriber có thể bắt đầu bằng `request(1)`, rồi sau mỗi `onNext` xử lý xong mới `request(1)` tiếp.

Lưu với tên `OneByOneDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class OneByOneDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch finished = new CountDownLatch(1);

        try (SubmissionPublisher<Integer> publisher = new SubmissionPublisher<>()) {
            publisher.subscribe(new Flow.Subscriber<>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription = s;
                    s.request(1); // Cấp một quyền nhận ban đầu
                }

                @Override
                public void onNext(Integer item) {
                    System.out.println("Nhận " + item);
                    // Chỉ cấp thêm quyền sau khi xử lý item hiện tại xong
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable error) {
                    System.err.println("Lỗi: " + error);
                    finished.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("onComplete");
                    finished.countDown();
                }
            });

            publisher.submit(1);
            publisher.submit(2);
            publisher.submit(3);
        } // close() thông báo không còn item mới

        if (!finished.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Subscriber chưa kết thúc");
        }
    }
}
```

Chạy:

```bash
javac OneByOneDemo.java
java OneByOneDemo
```

Khi hoàn tất bình thường, các dòng stdout theo thứ tự:

```text
Nhận 1
Nhận 2
Nhận 3
onComplete
```

Điểm cần phân biệt: `SubmissionPublisher.submit(item)` **có thể đặt item vào buffer ngay khi Subscriber chưa có demand để nhận**. Nó chỉ bảo đảm callback `onNext` tuân theo demand; không có nghĩa `submit` của Producer chỉ chạy sau mỗi `request(1)`. Khi buffer đầy, `submit` có thể block để chờ tài nguyên; `offer` có chính sách xử lý khác (có thể bỏ item). Vì vậy, `request(1)` hạn chế số item đang được trao tới Subscriber, **không tự động bảo đảm toàn bộ upstream không sản xuất trước, không có buffer hoặc không tiêu tốn bộ nhớ**.

Trong code bất đồng bộ, `CountDownLatch` giúp `main` chờ tín hiệu kết thúc. Đừng dùng `Thread.sleep(...)` để “đoán” rằng callback đã chạy xong.

## 6. Chọn chiến lược cấp demand

**Xin từng item:**

```java
@Override
public void onSubscribe(Flow.Subscription s) {
    subscription = s;
    s.request(1);
}

@Override
public void onNext(Event event) {
    process(event);        // xử lý đồng bộ; có thể tốn thời gian
    subscription.request(1); // chỉ xin tiếp sau khi xử lý thành công
}
```

Đoạn trên là **mã minh họa bên trong một Subscriber**, không phải lớp Java hoàn chỉnh. Phù hợp khi mỗi item đắt, muốn kiểm soát chặt, nhưng việc xin từng item có thể làm giảm throughput. Nếu `process` thất bại, phải có chính sách báo lỗi/hủy hoặc xử lý lỗi rõ ràng; không âm thầm làm mất item và cũng không cấp thêm demand vô điều kiện.

**Xin theo lô (window/batch):**

```java
private static final int BATCH_SIZE = 32;
private Flow.Subscription subscription;
private int processedInBatch;

@Override
public void onSubscribe(Flow.Subscription s) {
    subscription = s;
    s.request(BATCH_SIZE);
}

@Override
public void onNext(Event event) {
    process(event);
    if (++processedInBatch == BATCH_SIZE) {
        processedInBatch = 0;
        subscription.request(BATCH_SIZE);
    }
}
```

Đây cũng là đoạn trong một Subscriber, với `Event` và `process` do ứng dụng tự định nghĩa. Nó cho phép tối đa 32 quyền nhận đang mở, rồi bổ sung 32 quyền sau mỗi lô. Trong thực tế có thể bổ sung sớm hơn (ví dụ khi đã xử lý khoảng 75% cửa sổ) để tránh thời gian chờ giữa các lô. Chọn `BATCH_SIZE` theo bộ nhớ, chi phí mỗi item, độ trễ và thông lượng đo được.

**Yêu cầu không giới hạn:**

```java
subscription.request(Long.MAX_VALUE);
```

Cách này đơn giản nhưng không tạo cơ chế giới hạn demand phía Subscriber. Tránh dùng mặc định cho nguồn vô hạn hoặc công việc nặng.

Một Subscriber có thể yêu cầu thêm trong `onSubscribe`, `onNext` hoặc tại thời điểm khác khi tài nguyên sẵn sàng. Với xử lý async trong `onNext`, chỉ gọi `request` tiếp **sau khi thao tác async thật sự hoàn tất** nếu mục tiêu là giới hạn số công việc đang xử lý; gọi ngay sau khi enqueue task sẽ chỉ giới hạn số callback tức thời, không giới hạn số task đã enqueue.

## 7. Backpressure không đồng nghĩa mọi thứ đã an toàn

Cần phân biệt ba đại lượng:

| Đại lượng | Nó đo điều gì? | Do ai kiểm soát? |
|---|---|---|
| **Demand** | Số quyền phát `onNext` chưa dùng của một subscription. | Subscriber cấp qua `request(n)`; Publisher thực thi. |
| **Buffer/queue size** | Số item đã được tạo/nhận nhưng đang chờ phân phối hoặc xử lý. | Thiết kế Publisher/Processor, kích thước buffer, chính sách overflow. |
| **Processing concurrency/rate** | Bao nhiêu tác vụ đang chạy, xử lý nhanh đến đâu. | Executor, worker, giới hạn đồng thời, thuật toán ứng dụng. |

Khi ghép nhiều bước `Publisher -> Processor -> Subscriber`, mỗi liên kết có subscription và demand riêng. Processor phải vừa tôn trọng demand downstream, vừa quyết định lúc nào xin thêm upstream, và có thể cần buffer hữu hạn. Nếu Processor luôn `request(Long.MAX_VALUE)` ở upstream nhưng downstream xin từng item, buffer nội bộ vẫn có thể tăng mạnh.

Với nhiều Subscriber, `SubmissionPublisher` quản lý buffer/demand riêng cho từng người nhận; Subscriber chậm có thể ảnh hưởng tới chính sách submit/offer và tài nguyên tổng. Không coi “có Flow API” là chứng cứ tự động không thể quá tải.

## 8. Lỗi thường gặp và cách sửa

| Lỗi | Hệ quả | Cách đúng |
|---|---|---|
| Quên `request` trong `onSubscribe` và không xin ở đâu khác. | Không nhận `onNext` dù nguồn có item. | Cấp demand dương khi thực sự sẵn sàng. |
| Gọi `request(0)` để tạm dừng. | Vi phạm giao thức, dẫn tới `onError(IllegalArgumentException)`. | Ngừng xin thêm; xử lý những quyền đã cấp trước đó. |
| Hiểu `request(5)` là “phải nhận đúng 5 item ngay”. | Logic chờ sai, dễ treo khi nguồn chỉ có 3 item. | Hiểu là cho phép **tối đa** 5 item nữa; theo dõi tín hiệu terminal. |
| Gọi `request(1)` ngay khi mới enqueue xử lý async. | Công việc chờ xử lý vẫn có thể tích lũy. | Xin tiếp sau completion thực của công việc nếu giới hạn in-flight. |
| Dùng `request(Long.MAX_VALUE)` mặc định rồi nghĩ đã có backpressure hữu hạn. | Mất khả năng hạn chế item qua demand. | Dùng cửa sổ hữu hạn khi cần kiểm soát. |
| Viết Publisher tự chế với `long demand += n` không khóa/atomic. | Race condition hoặc tràn số, phát quá demand. | Dùng implementation tin cậy; nếu tự viết, cần atomic/saturating arithmetic và cơ chế drain serialize. |
| Tưởng `cancel()` dừng tất cả callback tức thì. | Có thể còn item đang in-flight. | Xem cancel là best-effort; xử lý an toàn callback đến sát thời điểm hủy. |

Một sự tinh tế: `onNext` cho cùng một Subscriber cần được phát tuần tự theo hợp đồng `Flow`, nhưng `request` và `cancel` có thể được gọi từ thread khác so với thread đang phát. Người viết Publisher cần đảm bảo an toàn bộ nhớ, đồng bộ hóa và không gửi vượt demand; người viết Subscriber không nên giả định các callback luôn chạy trên thread của `main`.

## 9. Tự kiểm tra hiểu biết

1. Ban đầu demand là 0; gọi `request(4)`, nhận 2 item, rồi gọi `request(3)`. **Còn bao nhiêu quyền?** Trả lời: `4 - 2 + 3 = 5`.
2. Đã gọi `request(10)`, nhưng nguồn chỉ còn 3 item rồi kết thúc. **Có phải lỗi không?** Không. Demand là giới hạn trên, không phải lời hứa sẽ có đủ dữ liệu; `onComplete` là hợp lệ.
3. `request(0)` có phải cách pause? **Không.** Đây là yêu cầu không hợp lệ, gây `onError`.
4. Vì sao một Subscriber `request(1)` vẫn có thể gặp memory pressure? Vì Producer/Processor có thể sản xuất trước, buffer dữ liệu hoặc tạo task async nhanh hơn tốc độ hoàn tất; demand chỉ là một phần của thiết kế.

**Ghi nhớ:** `request(n)` là tín hiệu “tôi cho phép nhận thêm tối đa n phần tử”, và các lần gọi cộng dồn vào demand còn lại. Một hệ thống ổn định cần kết hợp quy tắc demand với giới hạn buffer, chính sách overflow, kiểm soát tác vụ đang xử lý và xử lý đúng terminal/cancel.

## Tham khảo Java SE 17

- [`Flow` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.html)
- [`Flow.Subscription` — request/cancel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
- [`SubmissionPublisher` — buffer, submit, offer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html)
