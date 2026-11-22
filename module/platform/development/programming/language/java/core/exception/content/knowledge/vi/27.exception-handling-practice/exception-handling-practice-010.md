# Hoàn thiện ví dụ tích hợp với kiểm thử các tình huống thất bại — Java Core Exception

## 1. Bài thực hành tổng hợp: từ ngoại lệ đến hợp đồng nghiệp vụ

Một chương trình Java có thể biên dịch và chạy đúng ở đường thành công nhưng vẫn sai nghiêm trọng khi dependency lỗi, tài nguyên đóng thất bại, tác vụ bị hủy hoặc dữ liệu chỉ được ghi một phần. Vì vậy, khi hoàn thiện ví dụ tích hợp, không nên dừng ở việc bắt được một `Exception`. Cần kiểm tra cả **loại lỗi, nguyên nhân, ranh giới tài nguyên, tác dụng phụ và trạng thái mà caller thực sự nhận được**.

Bài này xây dựng một workflow tạo đơn hàng tối giản bằng Java 17+:

1. Nhận yêu cầu gồm mã hàng và số lượng.
2. Kiểm tra đầu vào **trước khi truy cập dependency**.
3. Mở session tới kho dữ liệu qua `AutoCloseable`.
4. Đọc đơn giá; phân biệt không tìm thấy, dữ liệu nguồn sai và sự cố I/O.
5. Tạo receipt có tổng tiền và ghi vào kho.
6. Gửi thông báo sau khi lưu.
7. Đóng session dù thành công hay lỗi.
8. Quan sát kết quả khi tác vụ được chạy qua `ExecutorService`.
9. Kiểm tra cancellation và các exception có thể phát sinh bất đồng bộ.

Các dependency được thay bằng **fake trong bộ nhớ**, không dùng database, mạng hoặc secret thật. Bộ kiểm tra vẫn bao gồm nhiều tình huống không thuận lợi nhằm xác minh **hợp đồng từng ranh giới**. Đây là chương trình có thể tự chạy với `javac`/`java`; sau đó ta đối chiếu với cách tổ chức JUnit 5 trong dự án.

**Kết quả mong muốn:** đường thành công trả đúng receipt; từng loại lỗi có mã khác nhau; nguồn I/O vẫn nằm trong `getCause()`; `try-with-resources` bảo toàn lỗi close; cancellation không bị biến thành thành công; đặc biệt, một thao tác đã lưu trước khi notifier lỗi **không được giả định là chưa lưu**.

## 2. Phạm vi và hợp đồng của ví dụ

Để bài tập có thể lặp lại và không phụ thuộc môi trường ngoài, ta dùng ba nhóm:

| Thành phần | Trách nhiệm | Loại trạng thái/lỗi |
| --- | --- | --- |
| `OrderService` | Validation, phối hợp đọc–tính–lưu–thông báo, dịch lỗi | `DomainFailure` có `Code` |
| `FakeStore` và `Session` | Mở session, đọc đơn giá, lưu receipt, đóng session | `IOException` ở những chế độ giả lập |
| `FakeNotifier` | Gửi thông báo sau khi receipt đã được lưu | `IOException` trong tình huống notify fail |
| `scenario(...)` | Chạy từng ca, assert code, số lần close và trạng thái đã lưu | Ném `AssertionError` nếu sai |
| `asyncFailure()` | Gọi workflow qua `submit()`, xác minh `ExecutionException.getCause()` | Cause là `DomainFailure` |
| `asyncCancellation()` | Chạy một tác vụ chờ có thể ngắt rồi gọi `cancel(true)` | `CancellationException` khi đọc Future |

Yêu cầu có một số **giả định cố ý**:

- `Session.save` đánh dấu `persisted=true` **trước** khi notifier được gọi. Fake không có transaction hoặc rollback.
- Đơn giá thành công là `25`, số lượng demo là `2`, nên tổng đúng là `50`.
- `NOTIFY_FAIL` xảy ra sau khi lưu thành công: đây là **thất bại có side effect**, không phải lỗi đồng nghĩa “chưa thực hiện”.
- `CLOSE_FAIL` xảy ra khi `close()` ném sau khi các thao tác khác đã hoàn tất. Lỗi đóng không tự undo trạng thái `persisted`.
- `READ_AND_CLOSE_FAIL` làm cả thao tác đọc và đóng lỗi, để kiểm tra primary/suppressed exception.
- Mỗi `scenario` tạo một fake mới; test không dùng chung trạng thái đã thay đổi giữa các case.
- Tác vụ hủy trong phần cuối chỉ chờ latch, không ghi dữ liệu nghiệp vụ, để minh họa interrupt mà không gây side effect bất định.

Không được xem fake này là một triển khai kho dữ liệu production. Đặc biệt, một DB thật có transaction, commit/rollback và connection pool; một notifier thật có thể gửi thành công nhưng mất ACK. Các phần tiếp theo nêu rõ những điểm phải kiểm thử thêm khi thay fake bằng dependency thật.

## 3. Sơ đồ đường thành công và đường thất bại

```text
Request(id, quantity)
        |
        v
Validate request
        | invalid ------------------> INVALID_REQUEST (chưa mở session)
        v
Store.open() -> Session
        |
        v
Session.read(id)
        | IOException -------------> DEPENDENCY_UNAVAILABLE
        | null --------------------> NOT_FOUND
        | unitPrice <= 0 ----------> INVALID_DATA
        v
Calculate Receipt(total)
        |
        v
Session.save(receipt)
        | IOException -------------> DEPENDENCY_UNAVAILABLE
        v
persisted = true
        |
        v
Notifier.send(receipt)
        | IOException -------------> NOTIFICATION_FAILED
        |                            persisted vẫn có thể true
        v
Return receipt
        |
        v
Session.close()                 (luôn được thử sau khi mở thành công)
        | IOException -------------> CLOSE_FAILED nếu không có lỗi trước
        | lỗi trước đã tồn tại ----> close error có thể được suppressed
        v
Caller nhận receipt / DomainFailure
```

Chú ý `Session.close()` diễn ra khi rời khối `try-with-resources`, **trước khi method hoàn tất trả về**. Vì thế code có câu `return receipt` trong thân `try` vẫn có thể **không trả receipt cho caller** nếu `close()` ném. Đây là lý do `CLOSE_FAIL` vẫn báo lỗi mặc dù receipt đã được lưu và thông báo đã gửi trong fake.

Tương tự, lỗi khi đọc dữ liệu có thể là primary, còn `close()` tạo lỗi thứ cấp. Nếu chỉ xem message của lỗi đóng mà bỏ qua `getSuppressed()` hoặc chỉ assert một mã lỗi, bài test có thể đánh giá nhầm nguồn sự cố.

## 4. Chọn các loại lỗi và mã lỗi có ý nghĩa

Ví dụ dùng enum:

```java
enum Code {
    INVALID_REQUEST, NOT_FOUND, INVALID_DATA,
    DEPENDENCY_UNAVAILABLE, NOTIFICATION_FAILED, CLOSE_FAILED
}
```

Đây là mảnh của chương trình đầy đủ ở phần sau.

| Mã | Điều kiện | Ý nghĩa |
| --- | --- | --- |
| `INVALID_REQUEST` | Mã hàng trống/null, số lượng không dương | Caller cung cấp input sai; chưa động tới repository |
| `NOT_FOUND` | Repository trả không có sản phẩm | Đã truy vấn được, nhưng không có dữ liệu |
| `INVALID_DATA` | Đơn giá từ nguồn không hợp lệ | Dependency trả được dữ liệu nhưng vi phạm invariant |
| `DEPENDENCY_UNAVAILABLE` | `read` hoặc `save` ném `IOException` | Không hoàn thành thao tác cần thiết với dependency |
| `NOTIFICATION_FAILED` | `send` ném sau khi `save` thành công | Lỗi sau bước lưu; không được tự kết luận chưa lưu |
| `CLOSE_FAILED` | Không có lỗi trước, nhưng `close()` ném `IOException` | Thao tác dọn dẹp/đóng tài nguyên thất bại |

Mã lỗi là hợp đồng giữa các tầng, **không phải** nguyên văn thông điệp từ hệ thống ngoài. `DomainFailure` sẽ giữ một `Code` và `Throwable cause` khi có lỗi I/O. Nhờ vậy, tầng trên có thể phân biệt lỗi input, nghiệp vụ và dependency mà không phải parse chuỗi message tự do.

Ở hệ thống thật, cần quyết định khi nào thông báo cho client là HTTP 400, 404, 409, 422, 503 hoặc trạng thái bất định. Đừng mặc định mọi `IOException` phải trả cùng mã 503: nó có thể đại diện cho nhiều điều kiện tùy contract và thời điểm xảy ra side effect.

## 5. Chương trình Java 17+ hoàn chỉnh

Tạo file **`OrderIntegrationDemo.java`** với nội dung sau. Chỉ dùng Java Standard Library và chạy được bằng JDK 17 trở lên.

```java
import java.io.IOException;
import java.util.concurrent.*;

public class OrderIntegrationDemo {
    enum Mode {
        OK, MISSING, READ_FAIL, BAD_PRICE, SAVE_FAIL,
        NOTIFY_FAIL, CLOSE_FAIL, READ_AND_CLOSE_FAIL
    }
    enum Code {
        INVALID_REQUEST, NOT_FOUND, INVALID_DATA,
        DEPENDENCY_UNAVAILABLE, NOTIFICATION_FAILED, CLOSE_FAILED
    }
    record Request(String id, int quantity) {}
    record Product(int unitPrice) {}
    record Receipt(String id, long total) {}

    static final class DomainFailure extends RuntimeException {
        final Code code;
        DomainFailure(Code code, Throwable cause) {
            super(code.name(), cause);
            this.code = code;
        }
    }

    static final class FakeStore {
        final Mode mode;
        int opens, reads, writes, closes;
        boolean persisted;

        FakeStore(Mode mode) { this.mode = mode; }

        Session open() {
            opens++;
            return new Session();
        }

        final class Session implements AutoCloseable {
            Product read(String id) throws IOException {
                reads++;
                if (mode == Mode.READ_FAIL || mode == Mode.READ_AND_CLOSE_FAIL) {
                    throw new IOException("read failed");
                }
                if (mode == Mode.MISSING) return null;
                return new Product(mode == Mode.BAD_PRICE ? -1 : 25);
            }

            void save(Receipt receipt) throws IOException {
                writes++;
                if (mode == Mode.SAVE_FAIL) {
                    throw new IOException("save failed");
                }
                persisted = true;
            }

            @Override
            public void close() throws IOException {
                closes++;
                if (mode == Mode.CLOSE_FAIL ||
                        mode == Mode.READ_AND_CLOSE_FAIL) {
                    throw new IOException("close failed");
                }
            }
        }
    }

    static final class FakeNotifier {
        final Mode mode;
        int sends;
        FakeNotifier(Mode mode) { this.mode = mode; }

        void send(Receipt receipt) throws IOException {
            sends++;
            if (mode == Mode.NOTIFY_FAIL) {
                throw new IOException("notify failed");
            }
        }
    }

    static final class OrderService {
        Receipt create(Request request, FakeStore store, FakeNotifier notifier) {
            if (request == null || request.id() == null ||
                    request.id().isBlank() || request.quantity() <= 0) {
                throw new DomainFailure(Code.INVALID_REQUEST, null);
            }
            try (FakeStore.Session session = store.open()) {
                Product product;
                try {
                    product = session.read(request.id());
                } catch (IOException ex) {
                    throw new DomainFailure(Code.DEPENDENCY_UNAVAILABLE, ex);
                }
                if (product == null) {
                    throw new DomainFailure(Code.NOT_FOUND, null);
                }
                if (product.unitPrice() <= 0) {
                    throw new DomainFailure(Code.INVALID_DATA, null);
                }
                Receipt receipt = new Receipt(request.id(),
                        (long) product.unitPrice() * request.quantity());
                try {
                    session.save(receipt);
                } catch (IOException ex) {
                    throw new DomainFailure(Code.DEPENDENCY_UNAVAILABLE, ex);
                }
                try {
                    notifier.send(receipt);
                } catch (IOException ex) {
                    throw new DomainFailure(Code.NOTIFICATION_FAILED, ex);
                }
                return receipt;
            } catch (IOException closeFailure) {
                throw new DomainFailure(Code.CLOSE_FAILED, closeFailure);
            }
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static void scenario(String name, Mode mode, Request request,
            Code expectedCode, boolean expectedPersisted,
            int expectedSuppressed) {
        FakeStore store = new FakeStore(mode);
        FakeNotifier notifier = new FakeNotifier(mode);
        try {
            Receipt receipt = new OrderService().create(request, store, notifier);
            check(expectedCode == null, name + " unexpectedly succeeded");
            check(receipt.total() == 50, "wrong total");
            check(store.persisted && store.closes == 1 && notifier.sends == 1,
                    "wrong success side effects");
            System.out.println(name + ": SUCCESS total=" + receipt.total());
        } catch (DomainFailure ex) {
            check(ex.code == expectedCode, name + " wrong error code");
            check(store.persisted == expectedPersisted, "wrong persistence");
            check(ex.getSuppressed().length == expectedSuppressed,
                    name + " wrong suppressed count");
            if (ex.code == Code.INVALID_REQUEST) {
                check(store.opens == 0 && store.closes == 0,
                        "validation must happen before dependency");
            } else {
                check(store.opens == 1 && store.closes == 1,
                        "session must close exactly once");
            }
            if (ex.code == Code.DEPENDENCY_UNAVAILABLE ||
                    ex.code == Code.NOTIFICATION_FAILED ||
                    ex.code == Code.CLOSE_FAILED) {
                check(ex.getCause() instanceof IOException,
                        "IO cause not preserved");
            }
            System.out.println(name + ": " + ex.code
                    + " persisted=" + store.persisted
                    + " suppressed=" + ex.getSuppressed().length);
        }
    }

    static void asyncFailure() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<?> future = executor.submit(() ->
                    new OrderService().create(new Request("A", 2),
                            new FakeStore(Mode.READ_FAIL),
                            new FakeNotifier(Mode.READ_FAIL)));
            try {
                future.get(5, TimeUnit.SECONDS);
                throw new AssertionError("expected execution failure");
            } catch (ExecutionException ex) {
                check(ex.getCause() instanceof DomainFailure,
                        "wrong async cause");
                DomainFailure failure = (DomainFailure) ex.getCause();
                check(failure.code == Code.DEPENDENCY_UNAVAILABLE,
                        "wrong async code");
                System.out.println("ASYNC: " + failure.code);
            }
        } finally {
            executor.shutdownNow();
            check(executor.awaitTermination(5, TimeUnit.SECONDS),
                    "executor did not stop");
        }
    }

    static void asyncCancellation() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        try {
            Future<?> future = executor.submit(() -> {
                started.countDown();
                try {
                    new CountDownLatch(1).await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });
            check(started.await(5, TimeUnit.SECONDS), "task did not start");
            check(future.cancel(true), "cancellation was not accepted");
            check(finished.await(5, TimeUnit.SECONDS), "task did not stop");
            try {
                future.get();
                throw new AssertionError("expected cancellation");
            } catch (CancellationException expected) {
                System.out.println("CANCEL: CancellationException");
            }
        } finally {
            executor.shutdownNow();
            check(executor.awaitTermination(5, TimeUnit.SECONDS),
                    "executor did not stop");
        }
    }

    public static void main(String[] args) throws Exception {
        scenario("SUCCESS", Mode.OK, new Request("A", 2), null, true, 0);
        scenario("INVALID", Mode.OK, new Request("", 2),
                Code.INVALID_REQUEST, false, 0);
        scenario("MISSING", Mode.MISSING, new Request("A", 2),
                Code.NOT_FOUND, false, 0);
        scenario("READ_FAIL", Mode.READ_FAIL, new Request("A", 2),
                Code.DEPENDENCY_UNAVAILABLE, false, 0);
        scenario("BAD_PRICE", Mode.BAD_PRICE, new Request("A", 2),
                Code.INVALID_DATA, false, 0);
        scenario("SAVE_FAIL", Mode.SAVE_FAIL, new Request("A", 2),
                Code.DEPENDENCY_UNAVAILABLE, false, 0);
        scenario("NOTIFY_FAIL", Mode.NOTIFY_FAIL, new Request("A", 2),
                Code.NOTIFICATION_FAILED, true, 0);
        scenario("CLOSE_FAIL", Mode.CLOSE_FAIL, new Request("A", 2),
                Code.CLOSE_FAILED, true, 0);
        scenario("READ_CLOSE", Mode.READ_AND_CLOSE_FAIL, new Request("A", 2),
                Code.DEPENDENCY_UNAVAILABLE, false, 1);
        asyncFailure();
        asyncCancellation();
        System.out.println("INTEGRATION_CHECKS: PASS");
    }
}
```

### Biên dịch và chạy

Tại thư mục chứa file:

```bash
javac -encoding UTF-8 OrderIntegrationDemo.java
java OrderIntegrationDemo
```

Chương trình in kết quả dưới đây khi các điều kiện kiểm tra đều đạt. **Standard output đã được kiểm chứng bằng javac/java**:

```text
SUCCESS: SUCCESS total=50
INVALID: INVALID_REQUEST persisted=false suppressed=0
MISSING: NOT_FOUND persisted=false suppressed=0
READ_FAIL: DEPENDENCY_UNAVAILABLE persisted=false suppressed=0
BAD_PRICE: INVALID_DATA persisted=false suppressed=0
SAVE_FAIL: DEPENDENCY_UNAVAILABLE persisted=false suppressed=0
NOTIFY_FAIL: NOTIFICATION_FAILED persisted=true suppressed=0
CLOSE_FAIL: CLOSE_FAILED persisted=true suppressed=0
READ_CLOSE: DEPENDENCY_UNAVAILABLE persisted=false suppressed=1
ASYNC: DEPENDENCY_UNAVAILABLE
CANCEL: CancellationException
INTEGRATION_CHECKS: PASS
```

**Quan trọng:** các output trên đến từ một demo giả lập với trạng thái được kiểm soát; chúng không là lời hứa về thứ tự completion trên mọi executor thực. Demo async chỉ in sau những điều kiện chờ bằng latch/Future; các thao tác thực tế có thể cần timeout khác theo môi trường.

## 6. Vì sao cấu trúc này là một ví dụ tích hợp?

Một unit test đơn lẻ có thể kiểm tra `validate(id)` hoặc một mapper riêng, nhưng bài tập trên kiểm tra **sự tương tác giữa nhiều ranh giới**:

- Validation phải chạy trước mở dependency.
- Đọc dữ liệu có thể trả “không có kết quả” hoặc ném lỗi I/O.
- Dữ liệu đọc thành công vẫn có thể vi phạm invariant.
- Ghi dữ liệu có thể thất bại trước khi đánh dấu persist.
- Gửi thông báo có thể thất bại **sau khi đã lưu**.
- Resource close có thể tự ném exception, kể cả khi thân đã thành công.
- Khi thân và close cùng lỗi, primary và suppressed phải được giữ.
- Khi chạy cùng workflow qua `ExecutorService`, exception xuất hiện tại `Future.get()` ở caller thay vì ném qua stack của thread nộp.
- Cancellation cần tín hiệu và kiểm tra kết thúc worker riêng.

Những khía cạnh này phù hợp với **component/integration-style test sử dụng fake ports**. Tuy nhiên, vì không dùng database thật hay server thật, không được gọi đó là integration test chứng minh toàn bộ môi trường production. Một test tích hợp thực sự với PostgreSQL, broker, HTTP client hoặc transaction manager còn phải kiểm tra semantics của những dependency đó.

Tên “tích hợp” ở đây biểu thị **workflow end-to-end trong phạm vi các thành phần được nối với nhau**, không khẳng định đã test mọi phụ thuộc bên ngoài.

## 7. Kiểm tra đầu vào phải xảy ra trước side effect

Ở đầu `OrderService.create`:

```java
if (request == null || request.id() == null ||
        request.id().isBlank() || request.quantity() <= 0) {
    throw new DomainFailure(Code.INVALID_REQUEST, null);
}
```

Đây là mảnh của chương trình hoàn chỉnh. Điều kiện kiểm tra diễn ra **trước `store.open()`**.

Trong case `INVALID`, bộ kiểm thử xác nhận:

- `DomainFailure.code == INVALID_REQUEST`.
- `store.opens == 0`.
- `store.closes == 0`.
- `store.persisted == false`.
- Không có nỗ lực lưu hay thông báo.

Mục tiêu không chỉ là “có `IllegalArgumentException`”. Nếu một bug khiến code mở session trước khi validation, bài test phải phát hiện hành động không cần thiết đó. Tương tự, khi một hệ thống xử lý thanh toán, validation và authorization cần diễn ra trước side effect theo contract.

Một số validation có thể cần truy vấn DB để kiểm tra sự tồn tại hoặc quan hệ. Trong trường hợp đó không thể khẳng định mọi validation đều “zero I/O”; hãy định nghĩa rõ bước nào được phép đọc, bước nào không được phép ghi, và assert theo hợp đồng.

## 8. Tách “không tìm thấy” khỏi “phụ thuộc không sẵn sàng”

Giả sử repository có hợp đồng:

```java
Product read(String id) throws IOException;
```

Đây là chữ ký của fake ở ví dụ. Nó có hai khả năng không trả một `Product` hợp lệ:

1. **Trả `null`**: truy vấn đã diễn ra nhưng không có product → `NOT_FOUND`.
2. **Ném `IOException`**: không lấy được kết quả do lỗi dependency → `DEPENDENCY_UNAVAILABLE`.

Hai trường hợp có ý nghĩa khác nhau. Nếu mọi `IOException` bị biến thành `null` hoặc `Optional.empty()`, caller có thể trả 404 cho một sản phẩm thực ra có tồn tại nhưng DB đang lỗi. Nếu một mã sản phẩm không tồn tại bị diễn giải là downtime, caller sẽ retry vô ích.

Bài test:

```text
MISSING: NOT_FOUND persisted=false suppressed=0
READ_FAIL: DEPENDENCY_UNAVAILABLE persisted=false suppressed=0
```

cho thấy hai kết quả khác nhau dù đều không có receipt thành công. Khi xây API thật, nên có contract không mơ hồ cho “not found”; có thể dùng `Optional<Product>` thay vì `null`, nhưng vẫn giữ exception cho lỗi I/O.

## 9. Dữ liệu nguồn sai không giống tham số caller sai

Ở case `BAD_PRICE`, `FakeStore.Session.read` trả `Product(-1)`. Đây là **giá trị không hợp lệ từ dependency**, không phải request với quantity sai. `OrderService` phát hiện `unitPrice <= 0` và ném `INVALID_DATA` trước khi save.

Kiểm thử xác nhận:

- Request đầu vào hợp lệ.
- Session đã mở và sẽ được đóng.
- Product đã đọc được, không có lỗi I/O.
- Đơn giá vi phạm invariant nên không được tính lưu.
- `store.persisted == false`.
- Không nên thực hiện notification.

Sự phân biệt này quan trọng khi xử lý dữ liệu từ database, JSON, message queue hay SDK. Nếu một DTO hợp lệ về cú pháp nhưng sai business invariant, không nên ném bừa `NullPointerException` hoặc trả một receipt có tổng âm.

Ví dụ tính tiền bằng `long` trong demo để tránh overflow khi nhân hai `int` dương vào kiểu `int`. Trong ứng dụng thật, cần biểu diễn tiền tệ bằng kiểu và đơn vị phù hợp (chẳng hạn amount nguyên theo đơn vị nhỏ nhất hoặc `BigDecimal` với rounding policy), kiểm tra miền giá trị, currency và overflow. Không nên dùng số thập phân dấu phẩy động một cách tùy tiện cho phép tính tài chính.

## 10. Phân loại lỗi I/O ở đúng adapter/service boundary

Hai vị trí `read` và `save` đều có thể ném `IOException`, nhưng cùng được map thành `DEPENDENCY_UNAVAILABLE` trong hợp đồng demo:

```java
try {
    product = session.read(request.id());
} catch (IOException ex) {
    throw new DomainFailure(Code.DEPENDENCY_UNAVAILABLE, ex);
}
```

và:

```java
try {
    session.save(receipt);
} catch (IOException ex) {
    throw new DomainFailure(Code.DEPENDENCY_UNAVAILABLE, ex);
}
```

Đây là các đoạn được lấy từ chương trình. Vì handler sử dụng `new DomainFailure(code, ex)`, Throwable gốc vẫn truy cập được qua `getCause()`.

Bài test không chỉ assert code mà còn xác nhận `cause instanceof IOException`. Nếu bỏ cause, log vận hành khó biết lỗi I/O xảy ra ở đâu; nếu luôn in nguyên cause vào HTTP response, có nguy cơ lộ thông tin nội bộ. Vì vậy nên **giữ cause cho chẩn đoán nội bộ** nhưng **trả mã lỗi an toàn cho client**.

Một ứng dụng thật có thể có thêm lỗi permission, conflict, unique-constraint violation hay dữ liệu tạm khóa, cần map hẹp hơn thay vì coi tất cả như downtime. Bài tập lựa chọn `IOException` như một lớp lỗi fake để tập trung vào **ràng buộc exception translation và kiểm thử failure path**.

## 11. Lỗi thông báo sau khi đã lưu: ví dụ quan trọng nhất

Trong `OrderService.create`, thứ tự là:

```text
Session.save(receipt)
       ↓
persisted = true
       ↓
Notifier.send(receipt)
       ↓
IOException nếu notifier lỗi
       ↓
DomainFailure(NOTIFICATION_FAILED)
```

Vì notify xảy ra **sau save**, case `NOTIFY_FAIL` có kết quả:

```text
NOTIFY_FAIL: NOTIFICATION_FAILED persisted=true suppressed=0
```

Điều này chứng minh một nguyên tắc quan trọng: **kết quả là exception không có nghĩa chưa có side effect**. Nếu caller thấy `NOTIFICATION_FAILED` rồi retry toàn bộ lệnh tạo đơn mà không kiểm tra, có thể tạo đơn trùng hoặc gửi thông báo trùng.

Trong một hệ thống production, nên thiết kế một trong các chính sách có hợp đồng rõ:

- **Transactional outbox:** lưu dữ liệu nghiệp vụ và bản ghi “cần phát thông báo” trong cùng transaction DB; worker chuyên trách gửi thông báo và retry có kiểm soát.
- **Idempotency key:** mọi yêu cầu tạo đơn có ID ổn định, để retry không làm phát sinh bản ghi mới khi cùng giao dịch đã được xử lý.
- **Trạng thái phân bước:** `PERSISTED_NOTIFICATION_PENDING` hoặc trạng thái tương đương, cho phép theo dõi và đối chiếu.
- **Compensation:** nếu workflow phân tán không thể dùng một transaction, định nghĩa thao tác bù có thể thất bại và cần được theo dõi.
- **Đối chiếu:** khi notifier trả timeout hoặc mất ACK, không kết luận “chưa gửi”; có thể phải truy vấn/tracking ở hệ thống nhận.

Ví dụ cố tình **không tự rollback** trong fake vì không có transaction. Đó là bài học thiết kế, không phải tính năng thiếu có thể che bằng `catch (Exception)`.

## 12. Lỗi khi close sau thân thành công

`try-with-resources` sẽ gọi `close()` khi rời khối, bao gồm sau câu `return receipt` ở thân try. Với `Mode.CLOSE_FAIL`, các bước đọc, lưu và thông báo có thể đã hoàn tất; sau đó `close()` ném `IOException` và được handler ngoài cùng dịch thành `DomainFailure(CLOSE_FAILED, cause)`.

Đầu ra:

```text
CLOSE_FAIL: CLOSE_FAILED persisted=true suppressed=0
```

Vì vậy một exception khi close **không chứng minh thao tác lưu đã thất bại**. Trong hệ thống thật, một `close()` có thể flush, commit, trả connection về pool hoặc giải phóng file handle tùy contract. Tình trạng sau lỗi close phải được xác minh theo dependency cụ thể, không suy ra từ exception type đơn thuần.

Hợp đồng của fake ở đây: `save` đặt `persisted=true` ngay lập tức, `close` không hoàn tác điều đó. Bài test sử dụng giả định này một cách tường minh.

Đừng bắt `IOException` từ close rồi âm thầm bỏ qua nếu lỗi đóng có thể dẫn đến mất dữ liệu, file chưa flush hoặc tài nguyên rò rỉ. Tùy yêu cầu, có thể cần báo trạng thái **chưa chắc chắn** thay vì retry ngay.

## 13. Lỗi chính và suppressed exception khi read + close cùng thất bại

Case `READ_AND_CLOSE_FAIL` tạo hai exception:

1. `session.read` ném `IOException("read failed")`.
2. Service dịch thành `DomainFailure(DEPENDENCY_UNAVAILABLE, cause)`.
3. Khi rời `try-with-resources`, `session.close()` ném `IOException("close failed")`.
4. Java giữ `DomainFailure` làm **exception chính**, rồi gắn lỗi close vào mảng suppressed.

Kết quả:

```text
READ_CLOSE: DEPENDENCY_UNAVAILABLE persisted=false suppressed=1
```

Cần phân biệt:

- `getCause()` trả nguyên nhân của DomainFailure, ở đây là lỗi I/O khi đọc.
- `getSuppressed()` chứa Throwable từ việc đóng tài nguyên.
- Lỗi close không thay thế lỗi đọc trong case có primary trước đó.
- Không vì chỉ thấy `DEPENDENCY_UNAVAILABLE` mà kết luận cleanup đã hoàn toàn thành công.

Để test chặt hơn, ngoài số lượng suppressed, có thể kiểm tra:

```java
DomainFailure failure = /* failure from OrderService.create(...) */;
Throwable[] suppressed = failure.getSuppressed();
if (suppressed.length != 1 ||
        !(suppressed[0] instanceof IOException) ||
        !"close failed".equals(suppressed[0].getMessage())) {
    throw new AssertionError("Close failure was not retained");
}
```

Đây là **mảnh assert bổ sung**, không phải đoạn độc lập để biên dịch: biến `failure` phải được lấy từ case `READ_AND_CLOSE_FAIL` và `DomainFailure` ở trong class của chương trình. Với unit test thật, dùng JUnit `assertEquals`, `assertInstanceOf` nếu thích hợp.

Nếu có nhiều tài nguyên `AutoCloseable` trong một resource header, Java đóng theo thứ tự ngược thứ tự khởi tạo. Các lỗi close thứ cấp có thể được thêm suppressed theo thứ tự xảy ra; nên test cả event order, không chỉ `length`, khi thứ tự đóng có ý nghĩa.

## 14. Kiểm thử khác nhau giữa lỗi Arrange, Act và Assert

Ngay cả trong một ví dụ tích hợp, test không nên tạo false positive bằng cách kỳ vọng exception trên quá nhiều bước:

```java
assertThrows(DomainFailure.class, () -> {
    FakeStore store = createStoreFromExternalConfig();
    FakeNotifier notifier = setupNotifier();
    new OrderService().create(request, store, notifier);
});
```

Đây là **mảnh JUnit 5 sai về phạm vi** khi các helper setup có thể ném cùng loại DomainFailure. Nếu setup lỗi trước khi gọi `create`, test vẫn có thể xanh mà không kiểm tra SUT.

Mẫu tốt hơn:

```java
FakeStore store = new FakeStore(Mode.READ_FAIL);
FakeNotifier notifier = new FakeNotifier(Mode.READ_FAIL);
OrderService service = new OrderService();
Request request = new Request("A", 2);

DomainFailure failure = assertThrows(
        DomainFailure.class,
        () -> service.create(request, store, notifier));

assertEquals(Code.DEPENDENCY_UNAVAILABLE, failure.code);
assertInstanceOf(IOException.class, failure.getCause());
assertFalse(store.persisted);
assertEquals(1, store.closes);
```

Đây là mảnh **JUnit Jupiter**, cần import assertion và các class ứng dụng, không phải chương trình Java SE độc lập. `Arrange` tạo fake; `Act` là **duy nhất** `service.create` bên trong `assertThrows`; `Assert` kiểm tra code, cause và side effects.

Nếu công cụ tạo fixture ném lỗi, test phải **fail ở Arrange** thay vì được coi là một kết quả exception mong đợi của service. Điều này đặc biệt quan trọng khi tích hợp test database/container phức tạp.

## 15. Vì sao có các bộ đếm opens/reads/writes/closes?

Chỉ assert mã lỗi có thể bỏ qua một bug về resource management. Ví dụ service trả `INVALID_REQUEST` đúng nhưng vẫn mở session hoặc gọi notifier trước validation: response đúng mà side effect đã sai.

Fake ghi các bộ đếm:

```java
int opens, reads, writes, closes;
boolean persisted;
```

Trong `scenario(...)`:

- Với `INVALID_REQUEST`, kỳ vọng `opens == 0` và `closes == 0`.
- Với những case đã mở session, kỳ vọng `opens == 1`, `closes == 1`.
- Với lỗi trước save, kỳ vọng `persisted == false`.
- Với `NOTIFY_FAIL` hoặc `CLOSE_FAIL`, kỳ vọng `persisted == true`.
- Với đường thành công, kỳ vọng tổng tiền đúng và notifier đã được gọi.

Khi chuyển thành test framework, có thể assert thêm `reads`, `writes`, `sends` chính xác để tăng độ bao phủ. Nhưng đừng assert các chi tiết nội bộ không thuộc hợp đồng: ví dụ nếu refactor gộp hai lần đọc thành một query khác mà hành vi công khai không đổi, test quá gắn vào triển khai có thể trở nên giòn.

**Bộ đếm chỉ hợp lý khi chính số lần gọi là yếu tố của hợp đồng**, ví dụ không được gửi thông báo trước khi lưu hoặc không được ghi khi input sai.

## 16. Một ma trận failure scenario cần có

| Tình huống | Error code | Persisted | Close | Điều cần chứng minh |
| --- | --- | --- | --- | --- |
| Đầu vào đúng, dependency hoạt động | Không lỗi | true | 1 | Receipt tổng `50`, notifier được gọi |
| Mã hàng rỗng | `INVALID_REQUEST` | false | 0 | Validation chặn I/O ngay từ đầu |
| Hàng không tồn tại | `NOT_FOUND` | false | 1 | Not found khác unavailable |
| Đọc lỗi `IOException` | `DEPENDENCY_UNAVAILABLE` | false | 1 | Cause I/O được giữ |
| Đơn giá không hợp lệ | `INVALID_DATA` | false | 1 | Không lưu dữ liệu sai |
| Lưu lỗi trước commit | `DEPENDENCY_UNAVAILABLE` | false | 1 | Không nhận thành công giả |
| Notifier lỗi sau save | `NOTIFICATION_FAILED` | true | 1 | Failure sau side effect |
| Close lỗi sau thân thành công | `CLOSE_FAILED` | true | 1 | Return của thân chưa phải return cuối |
| Đọc lỗi + close lỗi | `DEPENDENCY_UNAVAILABLE` | false | 1 | Lỗi close được suppressed |
| Task qua Executor lỗi | Cause `DomainFailure` | tùy case | theo fake | `get()` ném `ExecutionException` |
| Worker đang chờ bị cancel | Future canceled | không áp dụng | pool dừng | `get()` ném `CancellationException` |

Một bộ kiểm thử đầy đủ hơn với dependency thật cần bổ sung: mất ACK sau commit, timeout, retry trùng yêu cầu, transaction rollback thất bại, notifier gửi trùng, connection pool hết kết nối, đóng tài nguyên timeout, cạnh tranh nhiều request và quyền truy cập dữ liệu.

Mỗi case nên có **một mục tiêu rõ**: loại lỗi, tác dụng phụ hay lifecycle. Không kiểm tra “có exception nào đó” mà bỏ qua trạng thái cuối.

## 17. Java Future: lỗi trong worker không chạy vào catch quanh submit

Ví dụ chương trình gửi `OrderService.create` vào một executor:

```java
Future<?> future = executor.submit(() ->
        new OrderService().create(new Request("A", 2),
                new FakeStore(Mode.READ_FAIL),
                new FakeNotifier(Mode.READ_FAIL)));
```

Đây là mảnh từ `asyncFailure` của chương trình. Lỗi từ `create` xảy ra trong worker. Nó không tự đi vào một `catch` bao quanh `submit()` ở caller; thay vào đó Future hoàn tất bất thường.

Khi gọi:

```java
try {
    future.get(5, TimeUnit.SECONDS);
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    // Kiểm tra cause là DomainFailure có code DEPENDENCY_UNAVAILABLE.
}
```

đây là mảnh trong method đã quản lý checked exceptions. `Future.get()` ném `ExecutionException` với nguyên nhân là `DomainFailure`. Task đã lỗi theo hợp đồng, không phải lỗi mạng của thread caller.

Phân biệt:

- `ExecutionException`: tác vụ hoàn tất bất thường, xem cause.
- `InterruptedException`: thread đang **đợi** Future bị interrupt.
- `TimeoutException`: caller chờ quá thời hạn, không chứng minh task đã bị hủy.
- `CancellationException`: Future đã bị cancel.

Không dùng `catch (Exception)` rồi đổi mọi thứ thành lỗi dependency; một worker bug, timeout caller và cancellation là các tình trạng khác nhau.

## 18. Kiểm thử `cancel(true)` và interruption hợp tác

Phần `asyncCancellation()` tạo worker chờ trên `CountDownLatch.await()`. Caller đợi `started` rồi gọi:

```java
future.cancel(true);
```

Task đang chờ nên có thể phản ứng với interrupt bằng `InterruptedException`. Trong worker:

```java
try {
    new CountDownLatch(1).await();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
} finally {
    finished.countDown();
}
```

Đây là phần trích của chương trình đầy đủ. Handler khôi phục cờ và để task kết thúc, `finally` gửi tín hiệu `finished` để test xác nhận worker đã đi qua điểm cleanup.

Bài test xác nhận:

1. Worker **đã bắt đầu** trước khi gọi cancel.
2. `future.cancel(true)` trả true trong kịch bản xác định này.
3. Worker báo `finished` trong thời hạn test.
4. `future.get()` ném `CancellationException`.
5. Pool được yêu cầu shutdown và `awaitTermination` xác nhận chấm dứt.

**Quan trọng:** `Future.cancel(true)` là yêu cầu hủy. Với tác vụ không hợp tác hoặc I/O không interruptible, nó không cưỡng chế toàn bộ công việc dừng. Future có thể báo cancelled trong khi một số side effect còn tiếp diễn. Vì thế test dùng latch để xác minh worker đi qua cleanup thay vì chỉ dựa vào `future.isDone()`.

Nếu task đang thực hiện giao dịch thật, cần chính sách riêng về idempotency và trạng thái sau hủy; ví dụ demo không thực hiện giao dịch trong kịch bản cancellation để tránh kết quả không xác định.

## 19. Quản lý pool và tránh treo bài kiểm thử

Trong hai hàm async, executor được tạo bằng `Executors.newSingleThreadExecutor()`. Khi rời hàm:

```java
executor.shutdownNow();
check(executor.awaitTermination(5, TimeUnit.SECONDS),
        "executor did not stop");
```

Đây là mảnh của chương trình. `shutdownNow()` cố yêu cầu dừng các tác vụ còn chạy, thường qua interruption. `awaitTermination()` đợi executor kết thúc; nếu không chấm dứt trong hạn, bài kiểm tra phát hiện thất bại thay vì im lặng.

Trong code production thông thường:

- `shutdown()` là yêu cầu ngừng nhận task mới, cho tác vụ đã nộp hoàn tất theo chính sách.
- `awaitTermination(timeout, unit)` dùng để đợi có hạn.
- `shutdownNow()` là **best effort**, không bảo đảm mọi worker lập tức dừng.
- Nếu thread quản lý pool bị interrupt trong lúc chờ, nó cần tuân thủ chính sách hủy và thường restore interrupt flag nếu không truyền exception tiếp.
- Không shutdown shared executor mà framework hoặc module khác đang sở hữu.

Test có thể dùng timeout rộng hơn 5 giây trên CI quá tải, nhưng không nên dùng `Thread.sleep` tùy ý để đoán thread đã xong. `CountDownLatch`, `Future.get(timeout)` và `awaitTermination` cho tín hiệu rõ hơn.

## 20. Từ chương trình self-check sang JUnit 5

Chương trình dùng `check(...)` để có thể chạy độc lập, không cần build tool. Trong dự án thật, nên tổ chức thành các test JUnit Jupiter. Một ví dụ:

```java
@Test
void notificationFailureDoesNotUndoPersistedOrder() {
    FakeStore store = new FakeStore(Mode.NOTIFY_FAIL);
    FakeNotifier notifier = new FakeNotifier(Mode.NOTIFY_FAIL);
    OrderService service = new OrderService();

    DomainFailure failure = assertThrows(
            DomainFailure.class,
            () -> service.create(new Request("A", 2), store, notifier));

    assertEquals(Code.NOTIFICATION_FAILED, failure.code);
    assertInstanceOf(IOException.class, failure.getCause());
    assertTrue(store.persisted);
    assertEquals(1, store.closes);
    assertEquals(1, notifier.sends);
}
```

Đây là **mảnh JUnit 5**, cần đặt trong test class có imports/khả năng truy cập các kiểu bên trong `OrderIntegrationDemo`. Nó không phải chương trình chạy độc lập bằng `javac` nếu chưa thêm JUnit và điều chỉnh package/static imports.

Một test khác để kiểm tra suppression:

```java
@Test
void readFailureKeepsCloseFailureSuppressed() {
    FakeStore store = new FakeStore(Mode.READ_AND_CLOSE_FAIL);
    FakeNotifier notifier = new FakeNotifier(Mode.READ_AND_CLOSE_FAIL);

    DomainFailure failure = assertThrows(DomainFailure.class,
            () -> new OrderService().create(new Request("A", 2),
                    store, notifier));

    assertEquals(Code.DEPENDENCY_UNAVAILABLE, failure.code);
    assertInstanceOf(IOException.class, failure.getCause());
    assertEquals(1, failure.getSuppressed().length);
    assertEquals("close failed", failure.getSuppressed()[0].getMessage());
    assertFalse(store.persisted);
    assertEquals(1, store.closes);
}
```

Các assertion cần import `org.junit.jupiter.api.Test` và các static methods thuộc `org.junit.jupiter.api.Assertions`. Khi tách các class thành source files riêng, nên inject repository/notifier qua interface thay vì để service phụ thuộc trực tiếp vào fake. Đó là bước refactor tự nhiên khi chuyển demo học tập thành kiến trúc production.

## 21. Refactor sang ports/adapters để kiểm thử dễ bảo trì

Ở demo, `OrderService.create` nhận `FakeStore` và `FakeNotifier` trực tiếp để nội dung nằm trong một file có thể chạy. Trong dự án thật, nên chuyển dependency sang interface:

```java
interface OrderStore {
    Session open() throws IOException;
    interface Session extends AutoCloseable {
        Product read(String id) throws IOException;
        void save(Receipt receipt) throws IOException;
        @Override void close() throws IOException;
    }
}

interface Notifier {
    void send(Receipt receipt) throws IOException;
}
```

Đây là **mảnh thiết kế API**, với `Product`/`Receipt` thuộc domain đã định nghĩa trong ứng dụng. Nếu `open()` cũng có thể ném IOException, service cần map riêng lỗi khởi tạo session; không được nhầm với close failure.

Những lợi ích:

- Unit test dùng fake in-memory, kiểm soát rõ failure modes.
- Integration test dùng adapter thật kết nối DB/message broker.
- Service chỉ biết hợp đồng đọc/lưu/gửi, không cần biết JDBC/HTTP implementation.
- Dễ gắn retry, timeout, circuit breaker tại adapter với trách nhiệm rõ.
- Có thể kiểm thử API mapping và transaction boundary độc lập.

Tuy nhiên đừng tạo interface chỉ vì “mọi class đều cần interface”. Dùng abstraction khi nó giúp thay dependency, kiểm soát tác dụng phụ hoặc cải thiện testability thực tế.

## 22. Mở rộng kiểm thử với tình huống lỗi khi mở session

Demo giả lập lỗi ở `read`, `save` và `close`, nhưng `FakeStore.open()` luôn thành công. Một repository thật có thể lỗi ngay khi lấy connection.

Nếu thay chữ ký:

```java
OrderStore.Session open() throws IOException;
```

thì service phải phân biệt **mở không thành công** với **đóng thất bại**. Không nên có một `catch (IOException)` duy nhất đặt sau toàn bộ try-with-resources rồi mặc định mọi I/O error là close failure.

Ví dụ pattern:

```java
OrderStore.Session session;
try {
    session = store.open();
} catch (IOException ex) {
    throw new DomainFailure(Code.DEPENDENCY_UNAVAILABLE, ex);
}

try (session) {
    // Read, validate, save, notify.
} catch (IOException ex) {
    // IOException từ close nếu các thao tác trong body
    // đã được bắt/dịch sang domain error đúng chỗ.
    throw new DomainFailure(Code.CLOSE_FAILED, ex);
}
```

Đây là **mảnh kiến trúc**, không phải chương trình độc lập; `OrderStore` và `DomainFailure` phải được định nghĩa. Mục tiêu là tránh phân loại sai nguồn exception. Nếu các thao tác body còn có IOException chưa được dịch, catch bên ngoài vẫn có thể nhận chúng; do đó không được khẳng định mọi IOException tới catch cuối chắc chắn từ `close` nếu contract body không bảo đảm.

Test mở session thất bại cần xác nhận không gọi read/save/notify và không gọi close trên session chưa được khởi tạo thành công.

## 23. Những lỗi tích hợp không thể giả lập bằng một exception đơn

Một lỗi thực tế thường có nhiều trạng thái:

**Timeout sau lệnh ghi:** Caller đợi quá hạn, nhưng DB có thể đã commit. Retry phải dùng idempotency hoặc đối chiếu, không chỉ dựa vào `TimeoutException`.

**Mất ACK từ broker:** Thông báo có thể đã được gửi nhưng ứng dụng không nhận phản hồi. Không giả định `IOException` nghĩa là notification chưa được phát.

**Deadlock hoặc lock timeout:** Transaction có thể bị rollback bởi database, hoặc chỉ bị hủy một statement. Cần contract cụ thể của driver/DB.

**Bị interrupt trong I/O:** Một số API phản ứng với interrupt, số khác cần đóng socket/stream hoặc đặt timeout; không hứa mọi `cancel(true)` dừng ngay.

**Close lỗi sau thao tác thành công:** Có thể dữ liệu đã lưu một phần, flush chưa chắc thành công hoặc connection pool đang gặp vấn đề. Không tự suy ra “đã/không commit” nếu chưa biết semantics.

**Concurrent requests cùng key:** Một fake single-thread test không chứng minh uniqueness, transaction isolation, race freedom hoặc idempotency dưới tải.

**Lỗi trong bước test setup:** Không nhầm exception do tạo database/container/fixture với lỗi của SUT. Đặt Arrange ngoài lambda của `assertThrows`.

Bởi vậy một suite tốt thường có **unit tests cho mapping và nhánh điều khiển**, **component tests cho workflow**, **integration tests với dependency thật hoặc môi trường gần thật**, và một số **end-to-end tests** kiểm tra giao thức công khai. Mỗi tầng kiểm thử có mục đích riêng, không cần lặp toàn bộ trường hợp ở mọi tầng.

## 24. Thiết kế xử lý lỗi và phản hồi an toàn

`DomainFailure.code` có thể được map sang một response ở API boundary. Ví dụ thiết kế:

| Domain code | Response gợi ý | Lưu ý |
| --- | --- | --- |
| `INVALID_REQUEST` | 400 / `INVALID_REQUEST` | Không lộ raw input nếu chứa dữ liệu riêng tư |
| `NOT_FOUND` | 404 / `NOT_FOUND` | Phụ thuộc quyền truy cập và chính sách tránh enumeration |
| `INVALID_DATA` | 502 hoặc 500 tùy boundary | Dữ liệu nguồn sai khác với input caller sai |
| `DEPENDENCY_UNAVAILABLE` | 503 khi thực sự unavailable | Giữ cause ở log nội bộ được phân quyền |
| `NOTIFICATION_FAILED` | Trạng thái partial/pending có nghĩa nghiệp vụ | Không gợi ý retry toàn workflow một cách mù quáng |
| `CLOSE_FAILED` | Lỗi hoặc trạng thái chưa xác định | Không khẳng định save chưa diễn ra |

Đây là **gợi ý kiến trúc**, không phải mapping HTTP cố định cho mọi hệ thống. `INVALID_DATA` có thể là dữ liệu từ bên ngoài hay do chính ứng dụng tạo; cách gắn status phụ thuộc hợp đồng.

Phản hồi công khai nên có code ổn định, message an toàn và correlation ID không nhạy cảm. Không đưa nguyên `IOException.getMessage()`, stack trace, bearer token hoặc request body vào response. Các lỗi từ dependency có thể chứa dữ liệu không được phép xuất.

Trong logging, ghi operation, code, elapsed time, request ID và trạng thái có side effect theo schema. Không ghi cùng một Throwable ở mọi tầng chỉ vì đã có catch; xác định một nơi chịu trách nhiệm quan sát lỗi cuối cùng.

## 25. Checklist review trước khi coi bài thực hành hoàn chỉnh

1. **Đúng phạm vi:** Workflow có validation, đọc, tính, ghi, notification, đóng resource và caller async.
2. **Code runnable:** File/class name khớp, dùng API Java 17+, import đầy đủ, có lệnh `javac`/`java`.
3. **Đường thành công:** Có receipt chính xác, resource được đóng và dependency cần thiết đã được gọi.
4. **Validation:** Input sai không được mở session hay tạo side effect.
5. **Not found và I/O:** Không trộn “không có dữ liệu” với “không thể truy vấn”.
6. **Dữ liệu nguồn sai:** Không lưu output dựa trên đơn giá bất hợp lệ.
7. **Dependency cause:** Exception translation giữ `getCause()` để chẩn đoán.
8. **Partial success:** Notifier/close lỗi sau save không khiến test tự kết luận chưa lưu.
9. **Suppressed:** Khi body và close cùng lỗi, primary và `getSuppressed()` đúng.
10. **Executor:** `Future.get()` phân biệt `ExecutionException` với cancellation/interrupt/timeout.
11. **Cancellation:** Task hợp tác interrupt, test có signal xác nhận cleanup và đóng pool.
12. **Isolation:** Mỗi scenario có fake mới; không phụ thuộc thứ tự test hoặc dữ liệu từ case trước.
13. **Determinism:** Dùng latch/timeout có ý nghĩa, không dựa vào sleep ngắn ngẫu nhiên.
14. **Cleanup:** Pool và session có đường đóng, lỗi cleanup không bị che.
15. **Thông báo lỗi:** Client không nhận raw cause hoặc dữ liệu nhạy cảm.
16. **Retry:** Không tự retry thao tác đã có thể commit nếu thiếu idempotency và đối chiếu.
17. **Test boundaries:** Fixture setup, hành động SUT và assertion được phân tách.
18. **Khả năng mở rộng:** Ports/adapters cho phép chuyển từ fake sang dependency thật với integration tests phù hợp.

**Kết luận:** ví dụ Java chỉ thực sự hoàn thiện khi **đường thất bại được đặc tả và kiểm thử** như đường thành công. Hãy kiểm tra mã lỗi, cause, suppressed exceptions, số lần gọi dependency, trạng thái đã lưu, cách hủy task và việc đóng tài nguyên. Một exception được bắt đúng class nhưng làm mất thông tin hoặc che side effect vẫn là một lỗi thiết kế — nhất là khi tích hợp nhiều dependency và thực thi bất đồng bộ.
