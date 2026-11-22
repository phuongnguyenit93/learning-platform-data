# Nguyên tắc log hữu ích trong Java

Một dòng log có giá trị khi người đọc có thể dựa vào nó để **hiểu sự kiện, xác định phạm vi ảnh hưởng và quyết định bước điều tra hoặc xử lý tiếp theo**. Log không nên chỉ chứng minh rằng một dòng mã đã chạy; nó cần tạo ra bằng chứng có thể sử dụng khi ứng dụng đang vận hành, đặc biệt lúc không thể tái hiện lỗi ngay trên máy lập trình.

Trong Java, dù dùng `java.util.logging` (JUL), SLF4J kết hợp Logback hay Log4j 2, nguyên tắc thiết kế nội dung log gần như giống nhau. Sự khác biệt giữa API, mức log và cấu hình sẽ được nêu khi có ảnh hưởng thực tế.

## 1. Chọn đúng sự kiện để ghi

Hãy bắt đầu từ câu hỏi: **Nếu sự kiện này xuất hiện trong log lúc 3 giờ sáng, nó giúp trả lời điều gì?**

Ưu tiên những sự kiện tạo ra thay đổi hoặc quyết định đáng chú ý:

- **Vòng đời dịch vụ:** khởi động thành công/thất bại; cấu hình bắt buộc không hợp lệ; kết nối nguồn tài nguyên thiết yếu mất hoặc phục hồi.
- **Ranh giới xử lý nghiệp vụ:** một yêu cầu được tiếp nhận, hoàn tất, bị từ chối hoặc hủy; một thao tác quan trọng đổi trạng thái.
- **Tình huống bất thường:** phụ thuộc ngoài hết thời gian chờ, retry, chuyển sang phương án dự phòng, dữ liệu không hợp lệ vượt ngưỡng dự kiến.
- **Thất bại cần điều tra:** tác vụ không hoàn tất, ngoại lệ không được xử lý tại tầng chịu trách nhiệm, lỗi tài nguyên khiến giao dịch không đạt kết quả.
- **Thông tin vận hành cần thiết:** chế độ hoạt động, phiên bản triển khai, tên thành phần hoặc trạng thái sẵn sàng; tránh ghi dữ liệu cấu hình chứa bí mật.

Không cần log mọi lệnh gán biến, mỗi vòng lặp hoặc mọi request thành công ở mức `INFO`. Tùy lưu lượng, request thành công thông thường có thể được thu qua access log, trace, metric hoặc sampling. Ngược lại, sự kiện rất hiếm nhưng quan trọng cần có log rõ ràng dù không thường xuất hiện.

### Tập trung vào kết quả, không chỉ thao tác bắt đầu

| Log ít giá trị | Log có giá trị hơn | Vì sao |
| --- | --- | --- |
| `Start processing` | `event=payment.started requestId=req-17 paymentId=pay-42` | Biết thao tác và định danh để lần theo. |
| `Error occurred` | `event=payment.failed requestId=req-17 errorCode=UPSTREAM_TIMEOUT retryable=true` | Biết nguyên nhân phân loại được và hướng xử lý. |
| `Done` | `event=payment.completed paymentId=pay-42 outcome=accepted elapsedMs=28` | Biết đối tượng, kết quả và chi phí thời gian. |
| `Retrying...` | `event=inventory.retry requestId=req-17 attempt=2 maxAttempts=3 cause=timeout` | Biết retry thứ mấy và vì sao. |

Các ví dụ trên là **minh họa định dạng message**; định danh và thời gian không phải dữ liệu từ hệ thống thật. Một message chứa `key=value` vẫn chỉ là văn bản nếu backend chưa xuất dữ liệu theo cấu trúc.

## 2. Ghi đúng mức độ nghiêm trọng

Mức log phải dựa trên **ý nghĩa đối với người vận hành**, không dựa vào độ dài thông điệp hay cảm xúc của người viết mã.

| Mục đích | SLF4J/Logback/Log4j 2 thường dùng | JUL gần tương ứng | Ví dụ |
| --- | --- | --- | --- |
| Thông tin rất chi tiết phục vụ điều tra | `TRACE` | `FINER`, `FINEST` | Các bước xử lý bên trong thuật toán; thường tắt ở production. |
| Thông tin chẩn đoán | `DEBUG` | `FINE` | Đường đi logic, quyết định nhánh, giá trị kỹ thuật đã kiểm soát. |
| Diễn biến bình thường nhưng có ý nghĩa | `INFO` | `INFO` | Dịch vụ sẵn sàng, tác vụ quan trọng hoàn tất. |
| Bất thường có thể phục hồi hoặc cần chú ý | `WARN` | `WARNING` | Phải fallback, retry lặp lại, gần hết tài nguyên. |
| Hoạt động thất bại và cần xử lý | `ERROR` | `SEVERE` | Thao tác không hoàn tất hoặc thành phần thiết yếu không hoạt động. |

**Đây là ánh xạ về ý nghĩa, không phải quan hệ một-một của API.** JUL còn có `CONFIG`, `OFF` và `ALL`. Hãy thống nhất quy ước trong nhóm thay vì tự tạo nghĩa mới cho từng thành phần.

Ví dụ, một HTTP 404 do người dùng yêu cầu đường dẫn không tồn tại thường không phải sự cố server mức `ERROR`; có thể do access log hoặc `INFO/DEBUG` ghi nhận tùy hệ thống. Ngược lại, 404 từ dịch vụ phụ thuộc trong trường hợp dữ liệu bắt buộc phải tồn tại có thể báo lỗi nghiệp vụ cần điều tra. **Ngữ cảnh quyết định severity.**

Một số lưu ý về level:

1. Log mang tính chẩn đoán thường dùng `DEBUG/FINE`; không nâng lên `INFO` chỉ vì muốn thấy ngay khi phát triển.
2. Retry tạm thời được xử lý thành công có thể là `DEBUG` hoặc `WARN` tùy tác động; không báo `ERROR` cho mọi lần thử nếu quy trình chưa thất bại.
3. Khi thao tác cuối cùng thất bại, nên có một sự kiện thất bại rõ ràng tại ranh giới xử lý và phân loại nguyên nhân.
4. Điều chỉnh level theo môi trường hoặc package bằng cấu hình. Mở toàn bộ `DEBUG/TRACE` dài hạn có thể tăng chi phí và rò rỉ dữ liệu.

## 3. Mỗi sự kiện phải có đủ ngữ cảnh để truy vết

Một thông điệp hữu ích thường trả lời được sáu câu hỏi: **khi nào, ở đâu, sự kiện gì, liên quan đến đối tượng nào, kết quả ra sao, và điều gì dẫn đến kết quả đó**.

Các trường nên cân nhắc:

| Trường | Vai trò | Gợi ý |
| --- | --- | --- |
| `timestamp` | Thời điểm sự kiện | Định dạng nhất quán, có timezone rõ ràng; trong hệ thống phân tán thường dùng UTC. |
| `level` | Phân loại mức độ | Giữ chuẩn theo quy ước, tránh nhiều biến thể cùng một nghĩa. |
| `logger` / `component` | Thành phần phát sinh | Tên package/class hoặc tên service ổn định. |
| `event` / `eventName` | Loại sự kiện | Ví dụ `order.accepted`, `inventory.fallback`, `payment.failed`; tên rõ nghĩa và ổn định. |
| `requestId` / `correlationId` | Ghép sự kiện trong cùng luồng xử lý | Truyền qua các tầng liên quan, nhưng xem xét tính đáng tin cậy và dữ liệu nhạy cảm. |
| `traceId` / `spanId` | Liên hệ log với distributed tracing | Chỉ ghi khi có trace context thực tế, không tự bịa giá trị. |
| `orderId` / `jobId` | Xác định đối tượng bị ảnh hưởng | Dùng định danh kỹ thuật phù hợp quyền truy cập. |
| `outcome` / `status` | Kết quả quan sát được | `success`, `rejected`, `fallback`, `failed` hoặc status code có ý nghĩa. |
| `durationMs` / `elapsedMs` | Chi phí thời gian đã đo | Ghi kèm đơn vị, đo bằng đồng hồ phù hợp; không đoán con số. |
| `errorCode` / `reason` | Nguyên nhân có thể phân loại | Mã ổn định như `TIMEOUT`, `VALIDATION_FAILED`; không phụ thuộc hoàn toàn vào văn bản exception. |

Không cần nhồi mọi trường vào mọi dòng. Một sự kiện thành công đơn giản có thể chỉ cần `event`, `requestId`, `outcome` và `elapsedMs`; một lỗi phụ thuộc mạng có thể cần thêm `dependency`, `attempt` và `errorCode`. Tên và kiểu dữ liệu nên nhất quán giữa các lớp để hệ thống tìm kiếm không phải xử lý các biến thể như `request_id`, `requestID`, `rid` cho cùng một ý nghĩa.

**Truyền context qua luồng:** MDC/Thread Context trong một số framework thường gắn với luồng. Khi dùng `ExecutorService`, `CompletableFuture`, virtual thread hoặc reactive pipeline, context không mặc nhiên được truyền theo yêu cầu nghiệp vụ trong mọi trường hợp. Cần dùng cơ chế propagation tương ứng và dọn context sau khi xử lý để tránh lẫn định danh giữa các request. JUL cơ bản không có MDC chuẩn kiểu SLF4J/Logback.

## 4. Viết message chính xác, nhất quán và có thể hành động

Message nên mô tả **điều đã xảy ra**, tránh chỉ mô tả một cảm nhận chung. Dùng tên sự kiện ổn định và các thuộc tính rõ nghĩa, bởi con người và hệ thống tìm kiếm đều cần nhận ra cùng một sự kiện qua các lần triển khai.

Một cách thiết kế tốt:

- Dùng động từ và kết quả rõ ràng: `invoice.rejected`, `cache.refresh.failed`, `connection.recovered`.
- Nêu nguyên nhân phân loại được: `reason=quota_exceeded` hoặc `errorCode=UPSTREAM_TIMEOUT`.
- Chỉ ghi `success` khi thao tác thật sự thành công; đừng đặt `completed` ở cuối `finally` nếu luồng có thể ném lỗi.
- Nêu tình trạng retry/fallback khi thay đổi tính đúng đắn, thời gian phục vụ hoặc chất lượng dịch vụ.
- Phân biệt giá trị đo được với dự đoán: `elapsedMs=250` được đo; `estimatedRemainingMs` là ước tính nếu có.

Không nên đặt toàn bộ ý nghĩa vận hành vào một chuỗi exception tự do vì chuỗi có thể thay đổi theo phiên bản/thư viện. Dùng `errorCode` ổn định để nhóm lỗi, và đính kèm message/Throwable đã được kiểm soát để điều tra nguyên nhân.

Một event name không tự biến message thành dữ liệu có cấu trúc. Nếu cần tìm kiếm và tổng hợp theo trường, hãy cấu hình backend xuất JSON có trường riêng, thay vì chỉ trông chờ hệ thống tách chuỗi bằng biểu thức chính quy.

## 5. Ghi lỗi và ngoại lệ đúng nơi chịu trách nhiệm

Log lỗi hữu ích nhất khi kết hợp **bối cảnh nghiệp vụ + nguyên nhân kỹ thuật + kết quả cuối cùng**. Trong Java, ghi cả đối tượng `Throwable` khi cần stack trace; chỉ lấy `ex.getMessage()` sẽ thường mất chuỗi lời gọi và nguyên nhân lồng nhau.

Đoạn mã sau **minh họa cho một ranh giới xử lý**, giả sử đã có `logger`, `requestId` và phương thức `performCheckout()`; đây không phải chương trình độc lập:

```java
try {
    performCheckout();
} catch (RuntimeException ex) {
    // Chỉ log ở đây khi tầng này chịu trách nhiệm ghi nhận thất bại.
    logger.log(
        java.util.logging.Level.SEVERE,
        "event=checkout.failed requestId=" + requestId,
        ex
    );
    throw ex;
}
```

Nếu tầng gọi phía trên cũng luôn ghi cùng ngoại lệ, việc log rồi ném lại sẽ tạo **hai bản ghi lỗi** cho một nguyên nhân. Vì thế, nên quyết định rõ tầng nào chịu trách nhiệm ghi lỗi cuối cùng (ví dụ entrypoint, job runner hoặc exception handler). Tầng thấp có thể ném ngoại lệ có ngữ cảnh tốt hơn mà chưa cần log thêm.

Phân biệt ba tình huống:

- **Lỗi đã xử lý có kết quả hợp lệ:** ví dụ thử cache thất bại rồi lấy dữ liệu nguồn thành công; ghi thông tin fallback ở mức thích hợp thay vì mặc định `SEVERE`.
- **Lỗi khiến một thao tác thất bại:** ghi sự kiện cuối cùng tại ranh giới nghiệp vụ với `errorCode`, correlation ID và `Throwable` nếu có ích.
- **Lỗi dự kiến do dữ liệu đầu vào:** ví dụ xác thực từ chối; không biến mọi lỗi validation thành stack trace dài. Ghi loại từ chối đã chuẩn hóa và tránh lộ dữ liệu người dùng.

Không nuốt ngoại lệ bằng `catch` chỉ để ghi một dòng rồi tiếp tục trả về “thành công”. Log không thay thế cơ chế xử lý lỗi và trả kết quả đúng.

## 6. Giảm nhiễu, log trùng và khối lượng dữ liệu

Log quá dày che mất sự kiện quan trọng, tăng chi phí lưu trữ, lưu chuyển và tìm kiếm. Hệ thống tải lớn càng cần phân biệt **dấu hiệu cần điều tra** với **dữ liệu thống kê liên tục**.

Các kỹ thuật thường dùng:

1. **Ghi ở ranh giới có ý nghĩa:** một kết quả cuối cùng mỗi thao tác, cộng với các bất thường hoặc chuyển trạng thái quan trọng. Không ghi “đã vào hàm X” tại mọi phương thức.
2. **Tránh log trùng một lỗi:** nếu một exception được chuyển qua năm lớp, không nhất thiết ghi năm stack trace giống nhau.
3. **Dùng metrics cho thống kê:** tổng request, tỷ lệ lỗi, latency p95/p99 và số retry thường phù hợp với counter/histogram hơn là một log `INFO` cho mọi lần.
4. **Sampling/rate limit hợp lý:** có thể lấy mẫu luồng thành công rất nhiều; cần thận trọng với sự kiện lỗi hiếm, audit hoặc sự kiện an ninh.
5. **Gộp hợp lý sự kiện lặp:** thay vì hàng nghìn dòng “connection failed” giống nhau, có thể báo số lần, thời điểm đầu/cuối và trạng thái phục hồi. Vẫn giữ bằng chứng cần thiết để điều tra.
6. **Tách level vận hành khỏi level chẩn đoán:** để thông tin chi tiết ở `FINE/DEBUG` và bật có kiểm soát khi cần, kèm thời hạn tắt.

Ví dụ: với 50.000 request/giây, ghi một dòng thành công cho mỗi request tạo ra 3 triệu dòng/phút. Cần cân nhắc access log, retention, sampling và lượng dữ liệu hữu ích trước khi thiết kế.

Tuy nhiên, log có thể bị loại do sampling, lỗi ghi, bộ đệm hoặc cấu hình. **Không coi log ứng dụng thông thường là sổ cái giao dịch hoặc bằng chứng audit đảm bảo không mất sự kiện**. Các yêu cầu audit/độ bền cao cần cơ chế lưu bền vững và kiểm soát riêng.

## 7. Quan tâm hiệu năng ngay từ lúc gọi logger

Ghi log có thể tốn chi phí tạo message, chuyển đổi object, thu stack trace, định dạng JSON, cấp phát bộ nhớ, đồng bộ I/O và gửi mạng.

Với JUL, ưu tiên truyền tham số thay vì ghép chuỗi tốn kém trước khi kiểm tra level:

```java
// Chỉ minh họa lời gọi; giả sử logger, orderId đã tồn tại.
logger.log(java.util.logging.Level.FINE, "Validating order {0}", orderId);
```

Trong JUL, placeholder theo kiểu `{0}`, `{1}`; với SLF4J cú pháp thông dụng là `{}`. Dùng đúng API. Parameterization **không đảm bảo mọi chi phí được trì hoãn**: biểu thức đối số vẫn được Java đánh giá trước khi gọi hàm. Nếu tính toán dữ liệu thật đắt, hãy kiểm tra level hoặc dùng API cung cấp `Supplier` nếu phù hợp:

```java
if (logger.isLoggable(java.util.logging.Level.FINE)) {
    logger.fine(() -> "diagnostic=" + computeExpensiveDiagnostic());
}
```

Đây là **đoạn minh họa**, giả sử `computeExpensiveDiagnostic()` là phương thức sẵn có. Khi sử dụng `logger.fine(Supplier<String>)`, supplier chỉ được gọi khi logger chấp nhận level tương ứng; không dùng để thay thế kiểm tra hậu quả phụ của hàm chẩn đoán. Đặt công việc tốn kém bên trong supplier mới có ích.

Khi chuyển sang asynchronous logging, cần hiểu chính sách hàng đợi, tình huống tràn bộ đệm, shutdown/flush và khả năng mất log khi tiến trình chết. Logging bất đồng bộ có thể giảm chặn luồng xử lý, nhưng không tự bảo đảm mọi record được ghi bền vững hoặc giữ thứ tự tuyệt đối giữa nhiều tiến trình.

## 8. Bảo vệ dữ liệu và tránh log injection

Log có thể được nhiều hệ thống vận hành đọc, lưu lâu và chuyển sang hạ tầng bên thứ ba. Vì vậy phải xem log như một **đường truyền dữ liệu** cần kiểm soát.

**Không ghi thẳng:** mật khẩu, access/refresh token, cookie phiên, API key, private key, số thẻ thanh toán, nội dung xác thực và dữ liệu cá nhân không cần thiết. Tránh log toàn bộ request/response hoặc `toString()` của object nhạy cảm vì các trường mới có thể vô tình xuất hiện sau khi thay đổi mã.

Thay vào đó:

- Chỉ ghi **trường cần thiết**; ưu tiên mã lỗi, mã thao tác hoặc định danh nội bộ đã được duyệt.
- Mask/redact dữ liệu ở nguồn phát và ở hệ thống nhận khi có yêu cầu; không xem “đã mã hóa ở đường truyền” là lý do được phép ghi bí mật.
- Không tự động tin tưởng dữ liệu do người dùng cung cấp (ví dụ `userAgent`, đường dẫn, tiêu đề HTTP). Ký tự xuống dòng/điều khiển có thể làm giả dòng log. Với log dạng text, cần escaping/sanitization và giới hạn chiều dài; với JSON, dùng encoder chuẩn, không tự nối chuỗi JSON.
- Thiết lập phân quyền truy cập, retention và chính sách xóa phù hợp; sự kiện an ninh phải được xử lý theo chính sách riêng.

Ví dụ không nên dùng:

```java
// Sai vì có thể đưa bí mật vào hệ thống log.
logger.info("Login failed, token=" + accessToken);
```

Thay bằng thông tin chẩn đoán đã phân loại, ví dụ `event=auth.denied reason=expired_credential requestId=req-17`, miễn là `requestId` được kiểm soát. Không dùng token làm correlation ID.

## 9. Ví dụ Java 17 chạy được: thiết kế log ngắn, rõ và có ngữ cảnh

Ví dụ sử dụng **JUL có sẵn trong JDK**, mô phỏng một yêu cầu checkout được tiếp nhận, hệ thống inventory chuyển sang phương án dự phòng rồi checkout hoàn tất. Dữ liệu ví dụ đã được cố định để output có thể kiểm chứng.

Lưu toàn bộ đoạn sau thành **`UsefulLoggingDemo.java`**:

```java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class UsefulLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.checkout");

    public static void main(String[] args) {
        // Dùng formatter cố định để ví dụ có output ổn định.
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler output = new StreamHandler(
                System.out,
                new Formatter() {
                    @Override
                    public String format(LogRecord record) {
                        return record.getLevel().getName()
                                + " "
                                + formatMessage(record)
                                + System.lineSeparator();
                    }
                }
        );
        output.setLevel(Level.ALL);
        LOG.addHandler(output);

        String requestId = "req-17";
        String orderId = "ord-42";

        LOG.log(
                Level.FINE,
                "event=checkout.validation_started requestId={0}",
                requestId
        );

        LOG.log(
                Level.INFO,
                "event=checkout.accepted requestId={0} orderId={1}",
                new Object[]{requestId, orderId}
        );

        boolean inventoryUnavailable = true;
        if (inventoryUnavailable) {
            LOG.log(
                    Level.WARNING,
                    "event=inventory.fallback requestId={0} "
                    + "orderId={1} strategy={2}",
                    new Object[]{requestId, orderId, "cached"}
            );
        }

        long elapsedMs = 23L; // Giá trị mô phỏng, không phải đo thời gian thực.
        LOG.log(
                Level.INFO,
                "event=checkout.completed requestId={0} "
                + "outcome={1} elapsedMs={2}",
                new Object[]{requestId, "success", elapsedMs}
        );

        output.flush();
        LOG.removeHandler(output);
    }
}
```

Chạy trên JDK 17 trở lên:

```bash
javac UsefulLoggingDemo.java
java UsefulLoggingDemo
```

**Standard output chính xác:**

```text
INFO event=checkout.accepted requestId=req-17 orderId=ord-42
WARNING event=inventory.fallback requestId=req-17 orderId=ord-42 strategy=cached
INFO event=checkout.completed requestId=req-17 outcome=success elapsedMs=23
```

Điểm đáng chú ý:

1. `event` có tên ổn định, giúp người đọc hiểu **loại sự kiện**; `requestId` và `orderId` là ngữ cảnh nhất quán.
2. `checkout.accepted` và `checkout.completed` là hai trạng thái khác nhau; sự kiện `completed` chỉ xuất hiện sau khi mô phỏng xử lý thành công.
3. Fallback ở `WARNING` vì đây là điều kiện bất thường nhưng đã được phục hồi; không đánh dấu toàn bộ checkout là thất bại.
4. `FINE` không được in vì ngưỡng logger là `INFO`. Handler cho phép `ALL` không thể phục hồi sự kiện đã bị logger loại.
5. `elapsedMs=23` chỉ là số **mô phỏng**. Trong mã sản xuất cần đo bằng `System.nanoTime()` cho khoảng thời gian, thay vì lấy timestamp đồng hồ tường làm thước đo độ dài.
6. `formatMessage(record)` xử lý các tham số `{0}`, `{1}`, `{2}` của JUL; `flush()` đẩy output khỏi bộ đệm `StreamHandler`. Tắt parent handlers tránh dòng log lặp từ cấu hình JUL cấp cha.

Định dạng `key=value` ở đây vẫn là **text log**, được chọn để bài chạy không cần thư viện ngoài. Trong hệ thống thật, hãy cân nhắc formatter/encoder xuất trường JSON riêng và cơ chế truyền correlation/trace context. Không nên tự phát triển bộ nối JSON thủ công chỉ để ghi log.

## 10. Kiểm tra chất lượng log bằng tình huống thực tế

Khi rà soát một sự kiện mới, thực hiện phép thử sau:

| Câu hỏi kiểm tra | Dấu hiệu cần sửa |
| --- | --- |
| Khi sự cố xảy ra, dòng này giúp trả lời câu hỏi vận hành nào? | Chỉ có `Enter method`, `Hello`, `Done`. |
| Log phản ánh đúng **sự kiện, kết quả** và thời điểm ghi không? | Ghi “success” trước khi commit, hoặc ghi “completed” dù ném lỗi. |
| Có thể phân biệt hai request hoặc hai đối tượng cùng loại không? | Thiếu request/job ID cần thiết hoặc trường định danh không ổn định. |
| Severity có nhất quán với mức độ ảnh hưởng không? | Validation thông thường ghi `SEVERE`, lỗi không phục hồi ghi `DEBUG`. |
| Khi thất bại có đủ bối cảnh và nguyên nhân kỹ thuật không? | Chỉ ghi `ex.getMessage()`, thiếu error code, thiếu stack trace lúc cần. |
| Log có bị trùng hoặc tăng theo số vòng lặp mà không đem lại giá trị không? | Mỗi tầng log lại cùng stack trace; mỗi phần tử tạo một dòng `INFO`. |
| Thông điệp có phù hợp để tìm kiếm/tổng hợp không? | Tên trường biến đổi tùy lớp, không rõ đơn vị, toàn bộ trạng thái nằm trong text tự do. |
| Có thể lộ dữ liệu nhạy cảm hoặc bị làm giả dòng log không? | Token, object chứa thông tin cá nhân, input nhiều dòng được nối trực tiếp. |
| Có điều khiển được chi phí và lượng dữ liệu không? | Debug mặc định bật, formatter nặng, không có chính sách giữ và xoay log. |

**Ví dụ quyết định trước–sau:** Thay vì log `"Send request"` khi bắt đầu gọi inventory và `"Error"` khi có timeout, hãy phát sự kiện `inventory.timeout` tại nơi biết rõ kết quả, kèm `requestId`, `dependency`, `attempt`, `timeoutMs` và `outcome`; nếu có fallback, ghi riêng `inventory.fallback` khi fallback thật sự xảy ra. Từ đó người vận hành phân biệt được “một lần gọi thất bại nhưng request được cứu” với “toàn bộ request thất bại”.

Một nguyên tắc thực dụng: **log tốt có thể kiểm chứng, dùng được để điều tra và không tạo ra thêm rủi ro**. Hãy giữ thông điệp ngắn gọn nhưng đủ ngữ cảnh; cho phép metrics và traces làm phần công việc mà chúng thực hiện tốt hơn.