# Catch rỗng và nuốt mất tín hiệu thất bại trong Java

## 1. Vì sao một khối `catch` rỗng nguy hiểm?

Trong Java, ngoại lệ (*exception*) là một **tín hiệu điều khiển** cho biết luồng xử lý bình thường đã bị gián đoạn. Khi code ném một exception, JVM tìm `catch` thích hợp trên call stack. Nếu một `catch` bắt được exception và **không ném lại, không trả trạng thái lỗi, không phục hồi, không báo lỗi theo hợp đồng**, luồng thực thi thường tiếp tục như thể vấn đề đã được xử lý.

Ví dụ:

~~~java
try {
    saveOrder();
} catch (IOException ignored) {
}
sendSuccessResponse();
~~~

Đây là **fragment minh họa**, với `saveOrder()` và `sendSuccessResponse()` giả định đã được khai báo. Nếu `saveOrder()` ném `IOException`, dòng `sendSuccessResponse()` vẫn được gọi, dù đơn hàng có thể chưa được lưu hoặc chỉ mới lưu một phần. `catch` rỗng không tự hoàn tác ghi file, transaction đã commit, lệnh HTTP hay thay đổi đối tượng trong bộ nhớ.

Đây là **nuốt lỗi** (*exception swallowing*). Nó có thể tạo ra ba loại hậu quả:

1. **Sai kết quả nghiệp vụ:** API trả `true`, `200 OK` hoặc “đã lưu” khi thật ra chưa biết công việc có hoàn tất hay không.
2. **Mất chứng cứ chẩn đoán:** exception class, message, stack trace và `cause` bị loại bỏ khỏi kênh người có trách nhiệm theo dõi.
3. **Sai điều phối:** caller không retry/rollback/compensate/alert vì không nhận tín hiệu thất bại; hệ thống giám sát có thể đếm request đó là thành công.

Không phải mọi `catch` đều phải ném lại. Một `catch` có thể **xử lý thành công** khi nó thật sự khôi phục được điều kiện cần, ví dụ fallback cache hợp lệ hoặc bỏ qua một file cấu hình tùy chọn theo hợp đồng. Vấn đề không phải riêng hai dấu `{}`, mà là **đánh mất thông tin thất bại mà caller/hệ thống phải biết**.

**Nguyên tắc xuyên suốt:** Bắt exception chỉ là bước tiếp nhận lỗi; muốn xem lỗi đã được xử lý, phải chứng minh được hậu điều kiện, cơ chế phục hồi và đường thông tin đi tới nơi chịu trách nhiệm.

## 2. Cơ chế của `try-catch`: sau catch, chương trình đi đâu?

Cấu trúc cơ bản:

~~~java
try {
    performOperation();
} catch (IOException e) {
    handle(e);
}
continueProcessing();
~~~

Đây là fragment với các hàm giả định. Nếu `performOperation()` ném `IOException` và `handle(e)` **kết thúc bình thường**, execution tiếp tục tại `continueProcessing()`. JVM không tự quyết định “lỗi này chưa giải quyết, hãy truyền tiếp”; từ quan điểm điều khiển chương trình, `catch` đã xử lý luồng ném exception.

Nếu `handle(e)` ném exception mới, hoặc `catch` thực hiện `throw e`, exception lại lan ra ngoài. Nếu `catch` `return`, phương thức hiện tại kết thúc theo nhánh trả về; nếu có `finally` liên quan, nó được thực thi theo quy tắc Java. Nếu `catch` gọi một hàm fallback và fallback thất bại, lỗi mới cũng phải được xem xét.

### 2.1. So sánh bốn cách bắt lỗi

| Hành động trong `catch` | Caller quan sát gì? | Điều kiện nên dùng |
| --- | --- | --- |
| `catch (IOException ignored) {}` | Không nhận exception đó; mã sau catch tiếp tục | Gần như chỉ khi việc bỏ qua được **chứng minh** là an toàn và có chủ đích |
| `throw e;` | Nhận chính exception đó nếu chữ ký/hệ thống type cho phép | Tầng hiện tại không thể xử lý, muốn giữ loại/cause/trace |
| `throw new ServiceException("...", e);` | Nhận exception mới với cause gốc | Chuyển lỗi sang hợp đồng của tầng khác, bổ sung ngữ cảnh |
| `return Result.failure(code, e);` | Nhận một trạng thái thất bại có cấu trúc | API chọn result type để thể hiện thất bại dự kiến/được phân loại |

Tùy API, việc log tại `catch` rồi **trả trạng thái lỗi** cũng hợp lý; log không phải yếu tố thay thế result. Một số lỗi có thể được phục hồi bằng fallback và trả giá trị thành công, nhưng fallback phải thỏa invariant và không nói sai rằng thao tác gốc đã hoàn tất.

### 2.2. Không thấy stack trace không đồng nghĩa không có lỗi

Exception có thể được tạo, ném, bị catch rồi bỏ qua mà không có bất cứ dòng log nào. Java **không có cơ chế mặc định in mọi exception đã bị bắt**. Chỉ các exception không được bắt và đi tới uncaught handler, hoặc các đường code chủ động log/đọc Throwable, mới có thể tạo biểu hiện dễ thấy. Vì vậy hệ thống có thể “không thấy lỗi trong log” trong khi một số bước đã thất bại.

## 3. Một ví dụ ngắn: kết quả báo thành công nhưng state đã thay đổi

Giả sử một thao tác gồm:
1. Ghi một bản ghi “đơn được tạo”.
2. Ghi audit bắt buộc để xác nhận quy trình hoàn tất.

Nếu audit thất bại **sau bước 1**, việc nuốt exception làm caller tưởng cả hai bước hoàn tất, trong khi trạng thái chỉ có phần đầu.

~~~text
Ghi đơn thành công
        |
        v
Ghi audit thất bại -> IOException
        |
        v
catch rỗng
        |
        v
trả "SUCCESS" dù audit chưa có
~~~

Quan trọng: ngay cả khi ta sửa `catch` để truyền exception, **phần ghi đơn trước đó không tự hoàn tác**. Có hai vấn đề độc lập:
- **Phát tín hiệu lỗi đúng:** caller biết quy trình chưa hoàn tất.
- **Bảo toàn/khôi phục trạng thái:** transaction, staging, outbox hoặc bù trừ được thiết kế theo phạm vi tài nguyên.

Nếu chỉ thêm `throw` mà bỏ qua tính nhất quán dữ liệu, bạn đã khôi phục được khả năng quan sát lỗi nhưng chưa bảo đảm toàn bộ nghiệp vụ nguyên tử.

## 4. Ví dụ Java 17 đầy đủ: nuốt lỗi, truyền cause và trả kết quả có nghĩa

Chương trình dưới đây dùng một `EventStore` trong bộ nhớ để quan sát trạng thái. Nó cố tình tạo lỗi I/O trong bước audit, rồi so sánh:
- Phương thức **`broken`** bắt rỗng và in thông báo thành công.
- Phương thức **`honest`** thêm ngữ cảnh, giữ cause và truyền exception lên caller.
- Hàm tìm kiếm trả `Optional.empty()` **chỉ khi không có dữ liệu**.
- Một phương thức thể hiện fallback có cấu trúc ở mức tối thiểu: trả boolean phản ánh bước audit thành công/thất bại, không tự tuyên bố thành công.

Lưu chính xác thành **`EmptyCatchLessonDemo.java`**:

~~~java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public class EmptyCatchLessonDemo {
    static final class EventStore {
        private final List<String> events = new ArrayList<>();
        void append(String value) { events.add(value); }
        List<String> snapshot() { return List.copyOf(events); }
    }

    static void writeAudit() throws IOException {
        throw new IOException("audit unavailable");
    }

    static void broken(EventStore store) {
        try {
            store.append("order-created");
            writeAudit();
        } catch (IOException ignored) {
        }
        System.out.println("broken: reported success");
    }

    static void honest(EventStore store) throws IOException {
        store.append("order-created");
        try {
            writeAudit();
        } catch (IOException cause) {
            throw new IOException("order may be partially processed", cause);
        }
    }

    static Optional<String> find(String id) {
        return "A".equals(id) ? Optional.of("Alice") : Optional.empty();
    }

    static boolean attemptWithFallback() {
        try {
            writeAudit();
            return true;
        } catch (IOException e) {
            return false;
        }
    }

    public static void main(String[] args) {
        EventStore first = new EventStore();
        broken(first);
        System.out.println("broken state: " + first.snapshot());

        EventStore second = new EventStore();
        try {
            honest(second);
        } catch (IOException e) {
            System.out.println("honest: " + e.getMessage());
            System.out.println("cause: " + e.getCause().getMessage());
        }
        System.out.println("honest state: " + second.snapshot());
        System.out.println("lookup: " + find("B").isEmpty());
        System.out.println("fallback: " + attemptWithFallback());
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên** trong thư mục chứa file:

~~~bash
javac --release 17 EmptyCatchLessonDemo.java
java EmptyCatchLessonDemo
~~~

Stdout đã kiểm chứng:

~~~text
broken: reported success
broken state: [order-created]
honest: order may be partially processed
cause: audit unavailable
honest state: [order-created]
lookup: true
fallback: false
~~~

### 4.1. Những điều output chứng minh

- **`broken: reported success`:** phương thức `broken` tiếp tục sau `catch` trống và in thành công dù `writeAudit` luôn ném `IOException`.
- **`broken state: [order-created]`:** phần ghi dữ liệu trong bộ nhớ đã xảy ra. `catch` rỗng không rollback trạng thái.
- **`honest: order may be partially processed`:** lỗi không bị mất; code bọc lại với ngữ cảnh rằng công việc có thể đã xử lý một phần.
- **`cause: audit unavailable`:** constructor `new IOException(message, cause)` giữ nguyên exception nền; caller có thể xem `getCause()` và stack trace tương ứng.
- **`honest state: [order-created]`:** truyền lại exception không đảo ngược tác động trước lỗi. Nếu nghiệp vụ đòi hỏi atomicity, phải thiết kế thêm cơ chế phù hợp.
- **`lookup: true`:** `Optional.empty()` thể hiện một kết quả tìm kiếm không thấy `"B"` trong trường hợp hợp lệ; không dùng nó để thay thế lỗi đọc storage.
- **`fallback: false`:** ví dụ boolean phản ánh rằng audit không thành công. Đây là một lựa chọn API tối giản, không phải lời khuyên dùng boolean cho mọi loại lỗi; hệ thống lớn nên cân nhắc result có mã nguyên nhân.

Với ứng dụng thực tế, cần chọn tên trả kết quả rõ hơn (ví dụ `auditSucceeded`), giữ lỗi để ghi nhận/đối soát khi cần, và bảo đảm dữ liệu không lộ thông tin nhạy cảm. Mẫu `attemptWithFallback` chỉ có thể xem là “đã xử lý” nếu hợp đồng công khai rằng `false` là **kết quả thất bại có ý nghĩa**, không phải `true` ở mọi trường hợp hoặc một biến bị bỏ qua.

## 5. Phân biệt “bắt rồi xử lý” với “bắt rồi nuốt”

Một `catch` là xử lý hợp lệ khi thực hiện ít nhất một hành động phù hợp với hợp đồng API:
- **Khôi phục thật:** retry có kiểm soát hoặc dùng nguồn dự phòng thỏa điều kiện, sau đó xác nhận kết quả đúng.
- **Truyền tiếp:** `throw` cùng exception, hoặc wrap với cause và ngữ cảnh.
- **Trả kết quả thất bại:** typed result, mã lỗi, trạng thái pending/unknown hoặc một checked outcome phù hợp.
- **Đánh dấu transaction rollback-only:** khi transaction manager thực sự hỗ trợ và chương trình còn trong phạm vi transaction.
- **Chấp nhận bỏ qua một tình huống không quan trọng:** có chính sách rõ, không ảnh hưởng invariant và có thể giải thích vì sao mất sự kiện đó an toàn.

Ví dụ bỏ qua hợp lý: cố xóa một **file tạm đã được xác định là không còn cần thiết**, gặp lỗi “file không còn tồn tại” trong một phương thức cleanup vốn được thiết kế **idempotent**. Tuy vậy, nên dùng API mang ý nghĩa trực tiếp như `Files.deleteIfExists(path)` và xử lý những lỗi khác (ví dụ permission denied) theo mức độ quan trọng; không catch cả `IOException` rồi giả định tất cả đều là “không tồn tại”.

### 5.1. Cách xác minh một fallback có thật sự phục hồi?

Hỏi:
1. Kết quả sau fallback có thỏa contract giống nhánh thành công hay được khai báo khác biệt?
2. Dữ liệu fallback có thể cũ hoặc thiếu? Caller có cần biết nguồn không?
3. Có side effect nào của bước gốc đã xảy ra trước khi lỗi ném?
4. Retry có tạo duplicate hay vi phạm idempotency không?
5. Nếu fallback cũng thất bại, tín hiệu nào được truyền tiếp?

Ví dụ đọc cache khi database mất kết nối có thể hợp lý đối với giao diện chỉ đọc chấp nhận dữ liệu cũ, nếu freshness được mô tả rõ. Nhưng cache fallback không hợp lý cho thao tác thanh toán cần kết quả commit chính xác.

## 6. Không dùng `Optional.empty()` hay `null` để che mọi lỗi

Cách sai:

~~~java
Optional<Customer> findCustomer(String id) {
    try {
        return repository.findById(id);
    } catch (Exception ignored) {
        return Optional.empty();
    }
}
~~~

Đây là **fragment minh họa không độc lập**, `Customer` và `repository` chưa được định nghĩa. Nó làm “không có khách hàng” không thể phân biệt với “database hỏng”, “không được phép truy cập” hay một bug `NullPointerException`. Caller có thể tự tạo khách hàng trùng, ghi nhầm trạng thái hoặc trả HTTP 404 thay vì 503.

Một contract rõ hơn:
- `Optional<Customer>` chỉ thể hiện **có hoặc không có khách hàng** khi truy vấn được thực hiện hợp lệ.
- Lỗi storage chưa được phục hồi thì truyền exception hoặc trả `Result.Error(code, cause)` riêng.
- Nếu cần biết sự khác biệt giữa “không tồn tại” và “chưa kiểm tra được”, một sealed result type như `Found`, `NotFound`, `Unavailable` có thể biểu đạt đầy đủ.

Dùng `null` cho cả vắng mặt và lỗi còn nguy hiểm hơn vì dễ gây `NullPointerException` ở tầng trên, làm mất thông tin về ngoại lệ gốc. Không lấy những giá trị mặc định `0`, `false`, chuỗi rỗng hoặc danh sách rỗng thay cho “lỗi đã xảy ra” nếu chúng đồng thời là kết quả hợp lệ.

## 7. Checked exception, unchecked exception và catch rộng

Các `IOException`, `SQLException` là **checked exceptions**, thường cần bắt hoặc khai báo `throws`; `NullPointerException`, `IllegalArgumentException`, `IllegalStateException` là **unchecked exceptions**. `Error` cũng thuộc `Throwable` nhưng là nhánh khác, thường báo lỗi nghiêm trọng không nên che.

~~~java
try {
    executeBusinessOperation();
} catch (Exception ignored) {
    // Anti-pattern: nuốt cả lỗi hạ tầng và bug RuntimeException.
}
~~~

Đây là mảnh minh họa, cần phương thức `executeBusinessOperation()`. Một `catch (Exception)` ban đầu nhằm bỏ qua lỗi I/O sau refactor có thể nuốt thêm NPE hoặc lỗi invariant. `catch (Throwable)` còn bắt cả `Error`.

**Trọng tâm ở đây:** `catch` rỗng làm mất tín hiệu thất bại. Phạm vi bắt và phân loại lỗi là vấn đề liên quan: chỉ gom nhiều ngoại lệ bằng multi-catch nếu chúng có cùng chính sách. Một supervisor/framework đặc biệt có thể bắt rộng để báo lỗi và kết thúc đơn vị công việc, nhưng **không được báo thành công** khi chưa phục hồi trạng thái.

## 8. Giữ nguyên nguyên nhân: rethrow, wrap và không tạo lỗi giả

Nếu `catch` không thể phục hồi, **đừng kết thúc bình thường**. Giữ cùng exception bằng `throw e;` khi chữ ký cho phép, hoặc dịch sang abstraction mới và giữ `cause`:

~~~java
try {
    persist();
} catch (IOException e) {
    throw new IllegalStateException("Could not persist order " + orderId, e);
}
~~~

Đây là mảnh minh họa có `persist()` và `orderId` từ ứng dụng; message cần tránh lộ dữ liệu nhạy cảm. Constructor `(String, Throwable)` giúp giữ lỗi gốc trong `getCause()`. Ngược lại, `new IllegalStateException("failed")` bỏ cause.

Nếu chỉ muốn để lỗi lan truyền và không có ngữ cảnh để thêm, **bỏ cả khối `catch`** thường tốt hơn. Bài chuyên về *ném ngoại lệ mới nhưng làm mất cause* sẽ giải thích kỹ cause chain và suppressed; điều cần nhớ ở đây là không **nuốt** lỗi rồi tạo ra thành công giả.

## 9. `InterruptedException` là tín hiệu hủy; nuốt nó đặc biệt nguy hiểm

Một lỗi thường gặp trong vòng lặp worker:

~~~java
while (running) {
    try {
        Thread.sleep(1_000);
        poll();
    } catch (InterruptedException ignored) {
    }
}
~~~

Đây là fragment minh họa, `running` và `poll()` chưa định nghĩa. Khi thread bị yêu cầu interrupt để hủy hoặc shutdown, `Thread.sleep` thường ném `InterruptedException` và xóa interrupt status. `catch` rỗng khiến vòng lặp tiếp tục; hệ thống có thể không dừng task dù executor đã yêu cầu hủy.

Mẫu hợp tác:

~~~java
Runnable worker = () -> {
    while (!Thread.currentThread().isInterrupted()) {
        try {
            Thread.sleep(1_000);
            pollOnce();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return;
        }
    }
};
~~~

Đây là fragment, `pollOnce()` chưa được khai báo. Việc khôi phục interrupt flag rồi thoát giúp tầng trên hoặc code teardown biết rằng thread đã nhận yêu cầu ngắt. Nếu phương thức hiện tại được phép khai báo `throws InterruptedException`, có thể truyền tiếp thay vì bắt.

Lưu ý: `Future.cancel(true)` không bảo đảm giết một task không hợp tác, và `CompletableFuture.cancel(true)` không phải lệnh interrupt supplier bên dưới theo hợp đồng `CompletableFuture`. Nuốt interrupt khiến những giới hạn này càng khó kiểm soát.

### 9.1. Vì sao không đánh đồng interrupt với “lỗi nghiệp vụ”?

`InterruptedException` thường biểu thị luồng đang đợi bị yêu cầu ngắt, không chứng minh task nào đó thất bại về dữ liệu. Một phương thức có thể trả trạng thái canceled, propagate interrupt hoặc restore flag tùy API. Nhưng đừng bắt nó rồi trả `true` như thể yêu cầu đã hoàn thành.

Khi worker có side effect, dừng sau interrupt cũng không tự hoàn tác các thay đổi đã xảy ra; cần transaction, idempotency, compensation hoặc báo trạng thái partial/unknown nếu cần.

## 10. Catch rỗng bên trong vòng lặp tạo “lỗi vô hình” và vòng retry nóng

Các đoạn kiểu:

~~~java
while (true) {
    try {
        consumeMessage();
    } catch (Exception ignored) {
    }
}
~~~

là fragment minh họa với `consumeMessage` chưa định nghĩa. Nếu `consumeMessage` liên tục thất bại ngay lập tức, vòng lặp có thể tiêu tốn CPU, tạo hàng nghìn lỗi bị nuốt, không backoff, không báo metric và không dừng được theo shutdown policy. Nếu message lỗi gây retry vô hạn, tiến trình có thể kẹt cùng một bản tin.

Một worker có chủ đích thường cần:
- phân loại lỗi recoverable vs permanent;
- giới hạn retry, delay/backoff và jitter hợp lý;
- dead-letter queue hoặc trạng thái failure terminal cho sự kiện không thể xử lý;
- idempotency/deduplication khi message có thể được redeliver;
- ngắt hợp tác, deadline và cleanup;
- ghi nhận lỗi có mã/ID tương ứng.

Không biến “có vòng retry” thành lý do bỏ qua mọi exception. Retry mà không có giới hạn, backoff và trạng thái vẫn là một dạng nuốt lỗi kéo dài.

## 11. Catch trong background task: caller có thể không bao giờ biết

Một `Runnable` tự catch mọi exception rồi return bình thường sẽ khiến cơ chế điều phối thấy task **đã hoàn tất bình thường**.

~~~java
Future<?> f = executor.submit(() -> {
    try {
        process();
    } catch (Exception ignored) {
    }
});
f.get(); // Có thể trả bình thường dù process() đã thất bại.
~~~

Đây là fragment, giả định `executor`, `process` và các checked exception từ `get()` được khai báo/xử lý. `ExecutorService.submit` ghi exception **thoát khỏi task** vào `Future`. Nếu task đã tự bắt và nuốt exception, Future không thể tự phát hiện thất bại đã bị giấu bên trong lambda.

Tương tự với `CompletableFuture`:

~~~java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(() -> {
            try {
                return remoteRead();
            } catch (RuntimeException ignored) {
                return "";
            }
        });
~~~

Fragment này giả định `remoteRead()` trả String và không ném checked exception chưa xử lý. Nếu một chuỗi rỗng là dữ liệu hợp lệ, `future.join()` có thể trả một kết quả “thành công” giả, làm `exceptionally` hoặc `whenComplete` ở tầng ngoài không thấy lỗi.

**Thiết kế tốt:** Nếu muốn chuyển exception thành result, hãy trả `Failed(ErrorCode, cause)`, không biến nó thành một `Success("")`. Nếu không có cách recovery đúng, để exception đi ra khỏi task để `Future.get()` hoặc `CompletableFuture.join()` truyền thông tin lỗi qua ranh giới luồng.

### 11.1. Không bỏ Future sau khi submit

Ngay cả khi worker **không** catch rỗng, nếu caller gọi `submit()` rồi không giữ/đọc Future, exception có thể được lưu bên trong handle và không có ai xử lý. Kết quả giống một “lỗi vô hình” ở cấp ứng dụng. Phải có người sở hữu kết quả: caller đọc `get()`, coordinator tổng hợp, callback xử lý `exceptionally`/`handle` hoặc bộ giám sát job có kênh trạng thái bền vững khi cần.

`UncaughtExceptionHandler` không thay thế `Future.get()` cho mọi task do executor chạy; `submit` thường bắt lỗi bên trong cấu trúc Future. Chỉ có handler cho raw thread mà không có kênh kết quả cũng không đủ để báo success/failure cho caller.

## 12. Có nên log ở mọi `catch` không?

Không. Một anti-pattern khác là:

~~~java
catch (IOException e) {
    logger.error("Repository failed", e);
    throw e;
}
~~~

Đây là fragment với logger giả định. Nếu service phía trên, controller và handler đều lặp lại “log rồi rethrow”, **một lỗi thực** có thể tạo bốn stack trace giống nhau. Hệ thống metric có thể đếm lỗi nhiều lần, còn người điều tra khó xác định bản ghi nào là kết quả cuối.

Một chính sách tốt:
- Tầng **có thể phục hồi**: ghi metric recovery hoặc warning theo nhu cầu, rồi tiếp tục với kết quả thật.
- Tầng **chỉ chuyển lỗi**: giữ cause, thêm ngữ cảnh nếu cần; không nhất thiết log mỗi lần.
- **Ranh giới chịu trách nhiệm trả kết quả/giám sát**: log lỗi một lần ở level phù hợp, kèm request/job ID, operation type và stack trace khi cần.
- Nếu thao tác phụ (audit, cleanup, metrics) lỗi riêng: phân biệt nguồn lỗi và nơi quan sát, không che exception chính.

Dù không log ở mọi tầng, tín hiệu lỗi vẫn phải **đi tới nơi có khả năng hành động**. “Không log trùng” không đồng nghĩa “nuốt exception”.

### 12.1. Đừng chỉ log message mà bỏ stack/cause

Ví dụ:

~~~java
logger.warn("failed: {}", e.getMessage());
~~~

Đây là fragment minh họa (API logging phụ thuộc framework); nó có thể bỏ mất stack trace và cause. Nếu ứng dụng cần chẩn đoán, truyền `Throwable` đúng vị trí mà logging framework hỗ trợ và bảo đảm dữ liệu nhạy cảm được kiểm soát. Nhưng thông điệp người dùng không nên chứa raw stack trace, password, token hoặc dữ liệu cá nhân.

## 13. Side effect đã xảy ra trước lỗi không tự biến mất

Một ví dụ nghiệp vụ:

~~~text
begin operation
   |
   +-- ghi file output thành công
   +-- commit transaction DB thành công
   +-- gửi HTTP tới payment service
   +-- timeout nhận response -> IOException
   |
   +-- catch rỗng
   +-- trả "OK"
~~~

Ngay cả nếu thay catch rỗng bằng `throw`, phần file và database đã commit vẫn không tự quay lại, còn payment service **có thể đã xử lý yêu cầu** dù client timeout.

Bốn trạng thái cần phân biệt:
1. **Lỗi xảy ra** — phải có thông tin exception/result.
2. **Thay đổi đã xảy ra** — có thể trước khi exception xuất hiện.
3. **Rollback còn khả thi không** — tùy transaction/file/protocol.
4. **Kết quả bên ngoài có chắc chắn không** — timeout có thể là trạng thái chưa biết.

Vì vậy, đừng trả “thất bại, chưa có gì xảy ra” một cách tự động. Nếu chưa thể xác định kết quả remote, trạng thái `UNKNOWN`/`PENDING` với operation ID và quy trình đối soát thường đúng hơn. Muốn retry an toàn các lệnh có side effect, dùng idempotency key được **server hỗ trợ thật**, không chỉ gửi một header đặt tên hấp dẫn.

### 13.1. Transaction rollback cần ranh giới đúng

Nếu dùng JDBC với `autoCommit=false` và thao tác trong một transaction hợp lệ, khi lỗi trước commit có thể gọi `rollback()`. Nhưng:
- `rollback()` không thu hồi những thay đổi đã commit trước đó;
- không tự rollback HTTP/email/file ngoài transaction;
- rollback cũng có thể thất bại;
- mất kết nối ngay lúc commit có thể khiến kết quả commit **không chắc chắn**.

Nuốt `SQLException` rồi tiếp tục dùng connection có trạng thái transaction không rõ có thể làm dữ liệu sai hoặc khiến request sau bị ảnh hưởng. Cần transaction manager/policy xử lý rõ ràng.

## 14. `try-with-resources`, `finally` và lỗi cleanup

Khối `catch` rỗng cũng có thể xuất hiện ở code đóng tài nguyên:

~~~java
try {
    writeOutput();
} finally {
    try {
        resource.close();
    } catch (IOException ignored) {
    }
}
~~~

Đây là fragment với `writeOutput` và `resource` giả định. Nếu `close()` fail, hệ thống có thể không biết dữ liệu đệm đã được flush hay chưa, hoặc resource thực sự được đóng hay không. Có tình huống việc đóng là best effort, nhưng phải có **hợp đồng và kênh chẩn đoán hợp lý**.

Với resource triển khai `AutoCloseable`, try-with-resources thường rõ hơn:

~~~java
try (OutputStream out = Files.newOutputStream(path)) {
    out.write(payload);
}
~~~

Đây là fragment; cần import `OutputStream`/`Files`, và `path`/`payload` chưa được khai báo. Nếu body và `close()` cùng ném exception, try-with-resources gắn lỗi đóng vào exception chính dưới dạng **suppressed exception** theo quy tắc Java. Dùng `e.getSuppressed()` để chẩn đoán nếu cần. Nếu tự catch rỗng quanh `close()`, bạn có thể đánh mất lỗi phụ đáng chú ý.

Tuy nhiên **đóng tài nguyên không phải rollback**. `close()` hoặc flush có thể làm dữ liệu đã đệm thực sự được ghi, không phải tự khôi phục file trước đó. Khi dùng giao thức file tạm và publish, chỉ dọn file tạm thuộc quyền sở hữu của thao tác; không xóa file chính trong `finally` một cách tùy tiện.

## 15. Chỉ bỏ qua exception khi hợp đồng thật sự cho phép

Có những việc “không thiết yếu” như cập nhật cache best effort, cố xóa file tạm đã không còn tồn tại, hoặc gửi một metric phụ. Việc không làm request chính thất bại **có thể là chính sách hợp lệ**. Nhưng nên diễn đạt chính sách rõ ràng:

| Tình huống | Bỏ qua có thể đúng? | Điều kiện |
| --- | --- | --- |
| Cache warm-up phụ trợ | Có thể | Miss/failure không đổi kết quả chính, có observability phù hợp |
| Xóa file tạm đã được dọn nơi khác | Có thể với trường hợp cụ thể | Phân biệt “file không tồn tại” với permission/I/O thực sự |
| Ghi metric không thiết yếu | Có thể | Được chấp nhận mất metric; không phá kết quả chính, có giới hạn lỗi |
| Lưu dữ liệu nghiệp vụ | Thường không | Caller cần biết trạng thái lưu thất bại |
| Ghi audit bắt buộc | Thường không | Vi phạm yêu cầu pháp lý/nghiệp vụ nếu mất dấu |
| Trừ tiền, tạo đơn, publish event quan trọng | Không thể nuốt chung | Cần kết quả/cancellation/idempotency/đối soát rõ |
| `InterruptedException` của worker | Thường không | Cần tôn trọng tín hiệu shutdown/hủy |
| `Error` nghiêm trọng của JVM | Không | Không được xem là lỗi thường rồi chạy tiếp mù quáng |

Kể cả khi được phép bỏ qua, có thể dùng:
- metric tổng hợp số lần lỗi để không mất khả năng cảnh báo;
- log có **rate limit** khi cần;
- trạng thái degraded/best-effort được mô tả trong API;
- cơ chế fallback không làm thay đổi invariant;
- kênh audit bền vững nếu lỗi phụ trở thành yêu cầu bắt buộc.

Đừng ép mọi tình huống đều phải log stack trace mức ERROR; log quá nhiều cũng che sự cố chính.

### 15.1. Exception có thể bỏ qua cần đúng loại, đúng thời điểm

Ví dụ `Files.deleteIfExists(path)` trả `false` khi file không tồn tại, nên thường không cần catch `NoSuchFileException` riêng cho tình huống bình thường. Nếu có race hoặc filesystem trả exception khác, bạn vẫn phải xem đó là vấn đề tài nguyên. Catch `IOException` rộng rồi bỏ hết có thể che permission denied hoặc disk failure mà hệ thống cần biết.

Tương tự, một thao tác bị hủy theo yêu cầu của người dùng có thể trả trạng thái `CANCELLED` thay vì exception hiển thị ra UI. Nhưng không vì thế mà nuốt mọi exception không liên quan trong đường hủy.

## 16. Result type là lựa chọn thay thế cho việc che lỗi

Trong một API cần xử lý nhiều tình huống dự kiến, có thể thiết kế result có kiểu:

~~~java
sealed interface SaveOutcome
        permits Saved, Rejected, TemporarilyUnavailable {}

record Saved(String id) implements SaveOutcome {}
record Rejected(String reason) implements SaveOutcome {}
record TemporarilyUnavailable(String code, Throwable cause)
        implements SaveOutcome {}
~~~

Đây là **fragment Java 17**, chưa có class ứng dụng bao quanh hoặc hàm save. Nó cho thấy:
- `Saved`: hoàn tất thực sự.
- `Rejected`: từ chối do quy tắc nghiệp vụ đã biết.
- `TemporarilyUnavailable`: lỗi hạ tầng được phân loại, kèm cause **nội bộ**.

Nếu một API trả `SaveOutcome`, caller phải xét từng nhánh, không chỉ `outcome != null` rồi cho thành công. Với external response, không serialize thẳng `Throwable`, stack trace hay thông tin nhạy cảm; chỉ đưa mã lỗi và thông báo an toàn.

Một result type không có phép màu: nếu phương thức đã swallow `IOException` rồi luôn tạo `new Saved(id)`, nó vẫn sai. Typed result chỉ hữu ích khi implementation **đặt đúng trạng thái dựa trên sự thật của công việc**.

### 16.1. Checked exception và contract của tầng trên

Nếu Java API chuyên dùng exception để biểu thị lỗi I/O, khai báo `throws IOException` và để caller quyết định recovery thường đơn giản hơn một hierarchy mới. Ngược lại, với API phải tổng hợp nhiều task và phân loại retry/rejected/not found, result có cấu trúc có thể rõ ràng hơn.

Không có nguyên tắc “mọi exception đều phải chuyển thành Result” hoặc “mọi lỗi phải ném unchecked”. Lựa chọn đúng phụ thuộc mức độ dự kiến của lỗi, quyền quyết định của caller và khả năng giữ thông tin khi đi qua boundary.

## 17. “Catch rỗng vì không muốn crash” thường tạo crash khó chẩn đoán hơn

Lập luận phổ biến là “nếu để exception lan ra, request/thread sẽ chết; bắt rỗng giúp ứng dụng ổn định”. Nhưng nếu một bước quan trọng thất bại:
- bộ nhớ/cache có thể không đồng bộ với database;
- khóa/transaction có thể vẫn ở trạng thái sai;
- caller sử dụng dữ liệu giả;
- các bước tiếp theo ném `NullPointerException` xa nguyên nhân thật;
- retry có thể nhân đôi side effect;
- hệ thống monitoring không biết cần can thiệp.

Vì vậy **cô lập thất bại** khác với **che thất bại**. Một worker supervisor có thể bắt exception ở ranh giới task, ghi nhận `FAILED`, đảm bảo cleanup và tiếp tục nhận công việc khác. Đó là thiết kế ổn định hơn việc nuốt lỗi ngay tại tầng xử lý nghiệp vụ.

Ví dụ một job handler:

~~~java
try {
    processJob(job);
    markCompleted(job.id());
} catch (IOException e) {
    markFailed(job.id(), "IO_ERROR", e);
}
~~~

Đây là fragment với các hàm giả định. Chính sách hợp lý nếu `markFailed` có cơ chế ghi trạng thái đáng tin, `processJob` không đã commit kết quả trái ngược, và caller phân biệt trạng thái failure. Nếu `markFailed` cũng ném exception, hệ thống phải có quy tắc xử lý/khôi phục. Không được xem catch đã hoàn thành nhiệm vụ chỉ vì có lời gọi `markFailed` trên giấy.

## 18. Empty catch bị công cụ phát hiện như thế nào?

Static analysis có thể phát hiện:
- `catch (Exception e) {}` hoặc block chỉ chứa comment;
- biến tên `ignored`/`unused` mà không có chính sách xử lý;
- `catch` trả giá trị thành công bất chấp exception;
- empty catch của `InterruptedException`;
- catching `Throwable`, broad exception;
- log-and-rethrow gây duplicate reporting;
- bỏ qua `Future` quan trọng.

Các IDE và công cụ như Checkstyle, PMD, SpotBugs hoặc Sonar có các rule/inspection liên quan, tùy cấu hình và phiên bản. **Không phụ thuộc một rule ID cố định** nếu chưa kiểm tra phiên bản công cụ đang dùng. Linter có thể bỏ qua trường hợp chứa comment “ignored”; comment đó không chứng minh thiết kế an toàn.

Một chính sách code review hiệu quả là yêu cầu tác giả của `catch` nói rõ:
1. Exception này thuộc loại nào, tại sao nó phát sinh?
2. Có còn side effect hoặc state chưa biết không?
3. Ai cần biết điều đó?
4. Tại sao recovery/fallback/return/throw được chọn?
5. Test nào chứng minh cả nhánh lỗi và nhánh thành công?

Những câu hỏi trên tốt hơn một lệnh cấm máy móc mọi `catch` không có log.

## 19. Kiểm thử để bắt lỗi bị nuốt

Chỉ kiểm tra rằng phương thức “không ném exception” là quá yếu. Cần **tiêm lỗi** vào dependency và khẳng định trạng thái kết quả:

| Điểm tiêm lỗi | Điều cần kiểm tra |
| --- | --- |
| Lỗi trước khi ghi dữ liệu | API báo thất bại; không phát thông báo thành công |
| Lỗi sau khi ghi một phần | Caller nhận partial/failed/unknown đúng hợp đồng |
| IOException từ repository | Không bị biến thành `Optional.empty()` hay danh sách rỗng giả |
| Callback audit lỗi sau commit | Không tuyên bố DB đã rollback; có trạng thái đối soát |
| `InterruptedException` trong worker | Tác vụ kết thúc/khôi phục flag hoặc propagate đúng chính sách |
| Future task ném exception | Caller/worker manager quan sát `ExecutionException.getCause()` |
| Retry gặp lỗi liên tiếp | Không chạy vòng nóng vô hạn; có giới hạn/backoff/metric |
| Lỗi cleanup | Không che mất lỗi chính; giữ suppressed/ghi nhận phụ khi phù hợp |
| Fallback cũng lỗi | Lỗi được truyền tiếp hoặc result phản ánh recovery thất bại |
| Log/metrics phụ gặp lỗi | Không vô tình đổi thành công nghiệp vụ thành thất bại nếu policy best effort |

### 19.1. Ví dụ unit test thể hiện tín hiệu lỗi phải tồn tại

JUnit 5 fragment sau giả định class `EmptyCatchLessonDemo` ở trên có sẵn:

~~~java
var store = new EmptyCatchLessonDemo.EventStore();

IOException thrown = assertThrows(IOException.class,
        () -> EmptyCatchLessonDemo.honest(store));

assertEquals("order may be partially processed", thrown.getMessage());
assertEquals("audit unavailable", thrown.getCause().getMessage());
assertEquals(List.of("order-created"), store.snapshot());
~~~

Đây là **fragment không độc lập**: cần dependency JUnit Jupiter, import `java.io.IOException`, `java.util.List` và static imports `assertThrows`, `assertEquals`. Test chứng minh caller biết lỗi và biết cause **ngay cả khi state đã thay đổi**. Điều đó giúp phân biệt yêu cầu phát tín hiệu thất bại với yêu cầu khôi phục toàn bộ state.

Nếu API hứa “mỗi lần save lỗi phải không có dữ liệu mới”, test phía trên phải yêu cầu snapshot rỗng và implementation phải dùng transaction/staging để đạt lời hứa. Đừng sửa expected test thành “hợp lệ” chỉ vì catch đã nuốt exception.

### 19.2. Test mất tín hiệu do worker nuốt lỗi

Với một `Callable<T>`, cấu hình dependency giả ném exception. Nếu task catch rồi trả mặc định, `Future.get()` sẽ trả giá trị bình thường. Test nên yêu cầu giá trị Result.Failed hoặc `ExecutionException`, tùy hợp đồng. Với `CompletableFuture`, kiểm tra `join()` báo `CompletionException` hoặc trả nhánh `Failed` khi ứng dụng cố ý phân loại, chứ không chỉ xem `isDone()`.

Đặc biệt, nếu bạn chỉ assert task đã kết thúc trong thời hạn, một task thất bại âm thầm có thể vẫn được tính là success.

## 20. Checklist khi review mỗi khối `catch`

- [ ] Loại exception bắt có **cụ thể** và phù hợp tầng xử lý không?
- [ ] Nếu catch rỗng hoặc bỏ qua, có **lý do nghiệp vụ đã kiểm chứng** chứ không chỉ comment “ignore”?
- [ ] Có thể xảy ra side effect hoặc partial state trước exception không?
- [ ] Sau catch, có dòng nào thông báo **thành công giả** không?
- [ ] Caller còn khả năng phân biệt thành công, vắng mặt, thất bại và chưa biết không?
- [ ] Nếu dùng fallback, dữ liệu fallback có đáp ứng invariant và freshness không?
- [ ] Nếu retry, có giới hạn/backoff và idempotency không?
- [ ] Nếu chuyển exception, có giữ `cause`/stack trace và ngữ cảnh không?
- [ ] Nếu gặp `InterruptedException`, có propagate hoặc restore flag/thoát phù hợp không?
- [ ] Nếu lỗi bên trong Future/CompletableFuture, có người sở hữu việc quan sát thất bại không?
- [ ] Nếu resource cleanup lỗi, có giữ suppressed hoặc tín hiệu chẩn đoán đúng mức không?
- [ ] Có log ở ranh giới phù hợp, không log trùng ở mọi tầng và không lộ bí mật?
- [ ] Unit/integration tests có tiêm lỗi và kiểm tra **trạng thái sau lỗi** không?
- [ ] Nếu bỏ qua lỗi phụ là chính sách, đã ghi rõ tính **best effort** và cách đo/giám sát suy giảm chưa?

## 21. Bài tập vận dụng

Một hệ thống nhận yêu cầu đặt hàng và thực hiện ba bước:

~~~text
(1) Save order to database
(2) Publish OrderCreated event
(3) Send confirmation email
~~~

Trong source có:

~~~java
try {
    saveOrder(order);
    publishEvent(order);
    sendEmail(order);
} catch (Exception ignored) {
}
return "ORDER_CREATED";
~~~

Đây là fragment với các hàm, biến giả định.

Hãy phân tích và sửa theo các tình huống:

1. `saveOrder` ném exception **trước commit**. Caller nên nhận gì? Nếu transaction còn mở thì rollback ở đâu?
2. `saveOrder` đã commit nhưng `publishEvent` ném exception. Vì sao không được khẳng định “order chưa tạo”?
3. `publishEvent` thực tế đã gửi sự kiện, nhưng client timeout; retry thế nào để tránh nhân đôi effect?
4. `sendEmail` thất bại nhưng yêu cầu chỉ bắt buộc lưu đơn, email là best effort. Nên biểu diễn điều này trong contract và monitoring như thế nào?
5. Nếu dùng `ExecutorService.submit` để gửi email, ai giữ Future/quan sát lỗi? Nếu task bắt rỗng, caller có biết không?
6. Viết unit test cố tình ném `IOException` ở từng bước, assert outcome/cause/trạng thái. Thêm test lỗi từ callback cleanup để không che lỗi chính.
7. Thiết kế một phương án lưu dữ liệu nghiệp vụ và bản ghi outbox trong **cùng DB transaction** khi cần phát event sau commit; giải thích vì sao outbox vẫn cần idempotent consumer khi retry.

## 22. Tóm tắt nguyên tắc

**Catch rỗng không đồng nghĩa đã giải quyết ngoại lệ.** Nó thường chỉ cắt đứt đường báo thất bại từ nơi xảy ra lỗi đến caller/hệ thống điều phối. Thao tác đã xảy ra trước exception vẫn có thể còn nguyên; việc tiếp tục và trả “thành công” có thể làm trạng thái sai lan sang các bước sau.

Khi viết hoặc review một `catch`, hãy chọn một trong các hành động có **hợp đồng rõ ràng**: phục hồi thực sự, truyền exception kèm cause, trả lỗi có cấu trúc, đánh dấu transaction thất bại, hoặc bỏ qua một lỗi không thiết yếu đã được chứng minh là an toàn. Với interruption và tác vụ bất đồng bộ, đừng nuốt tín hiệu hủy hay bỏ quên lỗi trong Future. Quan trọng nhất là kiểm thử **nhánh thất bại và trạng thái sau lỗi**, thay vì chỉ thấy chương trình không crash rồi kết luận nó hoạt động đúng.