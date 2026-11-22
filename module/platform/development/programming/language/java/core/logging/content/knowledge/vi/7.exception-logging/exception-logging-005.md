# Lỗi không thể xử lý — Exception logging trong Java

## 1. “Lỗi không thể xử lý” nghĩa là gì?

Trong một ứng dụng Java, **lỗi không thể xử lý tại một vị trí** là tình huống mà mã ở vị trí đó **không có cách hợp lý để tiếp tục hoặc phục hồi theo hợp đồng của nó**. Lỗi có thể được đẩy lên tầng cao hơn để tầng đó quyết định hủy yêu cầu, thất bại tác vụ, từ chối khởi động hoặc dừng tiến trình. **Exception logging** giúp ghi lại bằng chứng về sự thất bại để người vận hành hiểu nguyên nhân và phạm vi ảnh hưởng.

Cần phân biệt hai khái niệm thường bị đánh đồng:

- **Không xử lý được ở tầng hiện tại:** một phương thức không thể khôi phục, nên **ném tiếp ngoại lệ** cho tầng biết cách quyết định. Ngoại lệ vẫn có thể được xử lý đúng ở nơi khác.
- **Unhandled exception (ngoại lệ không được bắt):** ngoại lệ đi ra khỏi một ranh giới thực thi mà không có mã xử lý phù hợp. Với main thread, JVM thường in stack trace và kết thúc thread đó; với thread khác, hành vi phụ thuộc nơi chạy và uncaught-exception handler. Không phải mọi ngoại lệ không được bắt đều làm toàn bộ JVM dừng.
- **Unrecoverable failure (thất bại không thể phục hồi):** ở phạm vi đang xét, không có hành động an toàn để đạt mục tiêu. Ví dụ thiếu cấu hình bắt buộc khi khởi động, không thể hoàn tất một transaction hoặc trạng thái dữ liệu đã vi phạm bất biến nghiêm trọng.

Một yêu cầu HTTP có thể **không thể xử lý thành công** nhưng ứng dụng vẫn có thể **xử lý thất bại** bằng cách rollback, trả 5xx, ghi log tại ranh giới và tiếp tục phục vụ yêu cầu khác. Bởi vậy, “không xử lý được công việc này” **không mặc định** có nghĩa phải tắt cả tiến trình.

Ví dụ một sự cố được ghi có ngữ cảnh:

~~~text
SEVERE event=startup.failed component=database outcome=abort errorType=IllegalStateException
~~~

Đây là **dòng minh họa**, chưa phải output cố định của thư viện logging. Message cần nói rõ **cái gì thất bại, tác động là gì và chương trình quyết định làm gì**; thông tin Throwable/stack trace cần được lưu bằng API logging thích hợp.

## 2. Khi nào một lỗi thực sự không thể xử lý?

Điểm quyết định là **phạm vi trách nhiệm** của thành phần. Hãy hỏi: “Tầng này có thể khôi phục mà vẫn bảo đảm dữ liệu đúng, hợp đồng API đúng và hệ thống an toàn không?”

| Tình huống | Tầng có thể làm gì? | Logging thường phù hợp |
| --- | --- | --- |
| Người dùng gửi dữ liệu sai định dạng | Trả lỗi xác thực 4xx có nội dung an toàn | Không nhất thiết ghi ERROR; có thể ghi thông tin/metric theo chính sách |
| Cache không khả dụng nhưng database vẫn hoạt động | Chuyển sang nguồn dữ liệu chính | Có thể WARNING với mã sự kiện fallback |
| Dịch vụ ngoài timeout, retry đã được cho phép | Thử lại có giới hạn, sau đó thông báo thất bại nếu cần | Ghi thông tin retry có chọn lọc, không tạo một stack trace cho mỗi lần thử |
| Lệnh chuyển tiền không thể commit | Rollback và báo kết quả thất bại | Log một lần ở ranh giới có ngữ cảnh transaction |
| Thiếu cấu hình bắt buộc khi khởi động | Không thể khởi tạo an toàn | Log SEVERE/ERROR và kết thúc quá trình khởi động với trạng thái lỗi |
| Vi phạm bất biến nội bộ, trạng thái không đáng tin | Dừng tác vụ hoặc cô lập thành phần; có thể dừng ứng dụng nếu cần | Ghi lỗi nghiêm trọng và bảo toàn nguyên nhân |
| JVM hết bộ nhớ nghiêm trọng | Khả năng phục hồi/ghi log có thể không đáng tin | Ưu tiên cơ chế giám sát JVM, crash diagnostics; không giả định logger sẽ cứu được tình huống |

**Không phải cứ có exception là “lỗi không thể xử lý”.** Một ngoại lệ dự kiến của nghiệp vụ hoặc một retry thành công không nên tự động biến thành cảnh báo sự cố nghiêm trọng. Ngược lại, nuốt một lỗi phá vỡ bất biến chỉ để chương trình “chạy tiếp” có thể làm tình hình xấu hơn.

## 3. Ba trách nhiệm khác nhau: phát hiện, chuyển giao và ghi nhận

Một quy trình lành mạnh thường gồm:

~~~text
Tầng thấp phát hiện lỗi
         |
         v
Có thể phục hồi an toàn tại đây?
     /               \
    Có              Không
    |                 |
Phục hồi đúng        Ném tiếp ngoại lệ
hợp đồng             (giữ cause)
    |                 |
    v                 v
Tiếp tục       Ranh giới request / job / main
                       |
                       v
              Rollback / trả lỗi / dừng an toàn
                       |
                       v
             Ghi một log có đủ ngữ cảnh
                       |
                       v
               Metric / cảnh báo nếu cần
~~~

Ba trách nhiệm cần tách biệt:

1. **Phát hiện:** tầng thấp nhận ra thao tác thất bại, ví dụ kết nối tới database không thể mở.
2. **Chuyển giao:** nếu tầng đó không có kế hoạch phục hồi hợp lệ, hãy **ném tiếp cùng ngoại lệ** hoặc bọc vào ngoại lệ phù hợp **có giữ cause**.
3. **Ghi nhận và quyết định:** tầng cuối có đủ ngữ cảnh về request/tác vụ/khởi động xác định kết quả thất bại, ghi log và thực hiện chính sách tiếp theo.

Nguyên tắc thực hành là **log ở ranh giới chịu trách nhiệm xử lý thất bại và có đủ ngữ cảnh**, thường chỉ một lần cho cùng nguyên nhân. Không phải mọi hệ thống đều có cùng ranh giới: framework HTTP có thể tự ghi ngoại lệ, còn worker xử lý tác vụ định kỳ có thể cần tự ghi khi tác vụ thất bại.

### Vì sao không nên log tại mọi catch?

Giả sử một thao tác đi qua controller → service → repository. Nếu cả ba tầng đều gọi logger.error(..., ex) rồi ném tiếp, hệ thống có thể tạo **ba stack trace cho một lỗi duy nhất**. Việc đếm log sẽ phóng đại số sự cố, công cụ tìm kiếm bị nhiễu và việc truy nguyên khó hơn.

Nếu tầng service **thêm thông tin rồi ném tiếp**, nó có thể bọc ngoại lệ và để tầng boundary ghi log. Nếu service **đã phục hồi thành công**, một log WARNING hoặc DEBUG có thể đủ, và boundary không phải nhận ngoại lệ. Nếu ngoại lệ đã được framework tự ghi, hãy kiểm tra cấu hình trước khi tạo thêm một bản ghi giống hệt.

## 4. Ghi ngoại lệ đúng cách: giữ Throwable và cause

Khi lỗi không thể xử lý, thông điệp “Đã có lỗi” hiếm khi đủ. Nên giữ:

- **Event code** ổn định: event=order.failed, event=startup.failed.
- **Phạm vi:** service/component, thao tác, requestId/traceId hoặc jobId nếu an toàn.
- **Tác động:** outcome=failure, action=abort, action=rollback, action=reject.
- **Nguyên nhân kỹ thuật:** exception type, cause chain và stack trace khi cần.
- **Thông tin giới hạn:** retryAttempt, dependency, thời gian; tránh dữ liệu không cần thiết.

Với Java chuẩn **java.util.logging (JUL)**, phương thức phù hợp là:

~~~java
// Đoạn minh họa trong lớp đã khai báo LOGGER và biến ex.
LOGGER.log(java.util.logging.Level.SEVERE,
        "event=order.failed action=rollback",
        ex);
~~~

Đây là **đoạn mã minh họa**, không phải chương trình độc lập. Đối số thứ ba là **Throwable**. JUL giữ Throwable trong **LogRecord.getThrown()** để formatter/handler có thể biểu diễn stack trace và chuỗi cause.

Ngược lại:

~~~java
LOGGER.severe(ex.getMessage());
~~~

Lệnh trên chỉ ghi **chuỗi thông điệp**, không chuyển đối tượng Throwable cho logger. Nếu exception message thiếu hoặc nhạy cảm, việc tìm lỗi có thể khó khăn hoặc gây rò rỉ dữ liệu.

Một lưu ý quan trọng: **việc Logger nhận Throwable không có nghĩa formatter nào cũng in stack trace**. Formatter tối giản có thể chỉ in level và message; với vận hành thật, cần cấu hình formatter/encoder hỗ trợ exception, có chính sách che dữ liệu và lưu trữ phù hợp.

## 5. Giữ nguyên nguyên nhân khi ném tiếp

### 5.1. Ném tiếp cùng ngoại lệ

Khi không thể xử lý và không cần đổi loại lỗi, có thể ném lại:

~~~java
try {
    saveTransaction();
} catch (java.io.IOException ex) {
    throw ex;
}
~~~

Đây là **đoạn minh họa** cần phương thức saveTransaction() và chữ ký throws phù hợp ở nơi sử dụng. Trong thực tế, nếu catch chỉ để ném lại mà không làm gì khác, thường có thể bỏ cả catch, để ngoại lệ tự truyền lên.

### 5.2. Bọc ngoại lệ nhưng giữ cause

Nếu cần chuyển ngoại lệ tầng hạ tầng thành lỗi ở ranh giới thành phần:

~~~java
try {
    saveTransaction();
} catch (java.io.IOException ex) {
    throw new IllegalStateException(
            "Cannot complete transaction", ex);
}
~~~

**new IllegalStateException(message, ex)** giữ ngoại lệ gốc trong chuỗi nguyên nhân; khi ghi stack trace, người điều tra có thể thấy cả lớp lỗi mới và nguồn ban đầu.

Không nên thay bằng:

~~~java
throw new IllegalStateException(ex.getMessage());
~~~

Cách này bỏ mất **cause**. Hơn nữa, message từ thư viện hoặc exception gốc đôi khi chứa dữ liệu nhạy cảm nên không được đưa nguyên văn vào thông báo trả cho client.

### 5.3. Log rồi ném tiếp có luôn sai?

Không tuyệt đối. Một tầng có thể cần log vì có ý nghĩa **riêng và không được ranh giới phía trên ghi lại**, ví dụ một tác vụ nền độc lập đã thực sự thất bại và hệ thống khác chỉ nhận tổng số thất bại. Nhưng nếu chỉ cùng một nguyên nhân và cùng ngữ cảnh, nên có **một nơi chịu trách nhiệm ghi log chính** để tránh trùng. Khi buộc ghi ở nhiều nơi, chúng cần có thông tin bổ sung khác nhau và lý do vận hành rõ ràng.

## 6. Ví dụ Java 17+ chạy được: không thể khởi động an toàn

Tình huống: ứng dụng cần cấu hình **DB_URL** để sẵn sàng phục vụ. Trong ví dụ, việc kiểm tra được cố định để mô phỏng **thiếu cấu hình bắt buộc**. Lớp khởi tạo ném IllegalStateException; tầng main bắt lỗi, ghi **SEVERE** một lần, flush log và kết thúc với **exit code 1**.

Ví dụ cố ý không đọc môi trường thật, để output luôn xác định. Nó dùng JUL có sẵn trong JDK, không cần thêm dependency.

Tạo tệp **CriticalStartupDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class CriticalStartupDemo {
    private static final Logger LOGGER =
            Logger.getLogger(CriticalStartupDemo.class.getName());

    public static void main(String[] args) {
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.INFO);

        Handler stdout = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                Throwable cause = record.getThrown();
                String detail = (cause == null)
                        ? ""
                        : " | " + cause.getClass().getSimpleName()
                                + ": " + cause.getMessage();

                return record.getLevel().getName() + " | "
                        + formatMessage(record) + detail
                        + System.lineSeparator();
            }
        });
        stdout.setLevel(Level.INFO);
        LOGGER.addHandler(stdout);

        try {
            initializeRequiredConfiguration();
            System.out.println("APP_READY");
        } catch (IllegalStateException ex) {
            LOGGER.log(Level.SEVERE,
                    "event=startup.failed component=config outcome=abort",
                    ex);

            // Bảo đảm StreamHandler ghi log trước khi dừng.
            stdout.flush();
            System.exit(1);
        }
    }

    private static void initializeRequiredConfiguration() {
        // Mô phỏng lỗi cố định để ví dụ có output xác định.
        throw new IllegalStateException(
                "Required setting DB_URL is missing");
    }
}
~~~

Biên dịch bằng **JDK 17 trở lên** và chạy trong terminal:

~~~bash
javac -encoding UTF-8 CriticalStartupDemo.java
java CriticalStartupDemo
~~~

**Stdout chính xác** của chính chương trình này:

~~~text
SEVERE | event=startup.failed component=config outcome=abort | IllegalStateException: Required setting DB_URL is missing
~~~

Chương trình kết thúc với **mã thoát 1**. Để xem mã thoát trên bash, ngay sau lệnh java, chạy:

~~~bash
echo $?
~~~

Output của lệnh shell trên là:

~~~text
1
~~~

Trong PowerShell có thể xem mã thoát bằng **$LASTEXITCODE** sau khi chạy java; đây là giá trị shell cung cấp, **không phải dòng log do Java in ra**. Nếu kiểm tra bằng script bật chế độ dừng ngay khi command thất bại, cần dùng cách bắt mã thoát phù hợp với script đó.

Giải thích mã:

1. **initializeRequiredConfiguration()** báo không thể đáp ứng điều kiện bắt buộc, bằng cách ném IllegalStateException. Hàm này không log thêm, tránh trùng bản ghi.
2. Tầng **main** là ranh giới khởi động. Nó không thể công bố APP_READY; thay vào đó, bắt lỗi và ghi sự kiện **startup.failed**.
3. **LOGGER.log(Level.SEVERE, message, ex)** truyền nguyên đối tượng ngoại lệ. Trong JUL, Throwable được đưa vào LogRecord; **bản thân sự kiện vẫn giữ cause**.
4. Formatter được viết đơn giản chỉ in **loại ngoại lệ và message** để stdout luôn giống nhau; **nó không in stack trace đầy đủ**. Khi triển khai thật, hãy dùng formatter/encoder có xuất stack trace hoặc cơ chế chẩn đoán tương ứng nếu cần.
5. **setUseParentHandlers(false)** không để logger cha in thêm cùng bản ghi theo cấu hình khác; **StreamHandler(System.out, ...)** chủ động ghi stdout. ConsoleHandler mặc định của JUL thường ghi **stderr**.
6. **stdout.flush()** đẩy log còn trong bộ đệm trước khi System.exit(1). Trong hệ thống thật, ngay cả flush cũng không bảo đảm hệ thống thu thập từ xa đã nhận và lưu log bền vững.
7. **System.exit(1)** thể hiện chính sách của **entry point** cho lỗi khởi động bắt buộc. Không nên gọi System.exit từ thư viện, repository hoặc phương thức xử lý HTTP; các tầng đó phải chuyển lỗi cho tầng điều phối.

### Nếu muốn xem stack trace đầy đủ?

Có thể để **java.util.logging.SimpleFormatter** của JUL trình bày LogRecord và Throwable, hoặc cấu hình formatter/encoder của framework đang dùng để xuất trường exception và stack trace. Thời điểm, vị trí dòng và cách formatter trình bày stack trace có thể khác theo môi trường, nên ví dụ ở trên dùng formatter rút gọn để mô tả output chính xác.

Một lỗi không thể phục hồi ở ranh giới khởi động thường còn cần dọn tài nguyên, giải phóng kết nối đang mở và thông báo trạng thái không sẵn sàng cho hệ thống điều phối. Việc dùng exit code khác 0 là tín hiệu cho hệ thống bên ngoài biết tiến trình khởi động thất bại.

## 7. Các ranh giới xử lý lỗi trong ứng dụng Java

Không phải mọi lỗi đều nên dừng JVM. Chọn nơi logging và hành động theo **đơn vị công việc thất bại**.

### 7.1. HTTP request

Ví dụ service ném exception do cơ sở dữ liệu không khả dụng. **Exception handler ở ranh giới HTTP** có thể:

- Hoàn tất rollback nếu transaction cần hủy theo cấu hình/framework.
- Trả trạng thái HTTP thích hợp như 500 hoặc 503 với nội dung an toàn cho client.
- Ghi một log lỗi đủ ngữ cảnh, nếu framework chưa thực hiện việc đó.
- Tăng bộ đếm lỗi/ghi metric; các request độc lập khác có thể tiếp tục.

Không trả stack trace, mật khẩu hoặc nội dung exception nội bộ trực tiếp cho client. Trạng thái **500** không có nghĩa phải dừng JVM. Ngược lại, nếu trạng thái toàn tiến trình không còn đáng tin, có thể cần ngừng nhận request và để hệ thống điều phối thay thế instance.

### 7.2. Scheduled job hoặc batch

Một tác vụ bị lỗi sau khi hết số lần retry cho phép có thể được ghi:

~~~text
ERROR event=job.failed jobType=sync-catalog jobId=job-52 attempts=3 outcome=failure
~~~

Đây là dòng minh họa. Tầng scheduler/worker quyết định cập nhật trạng thái job, có retry hay chuyển sang dead-letter queue hay không. Không để ngoại lệ bị nuốt khiến job bị đánh dấu thành công. Cũng không log stack trace riêng cho mỗi retry nếu một thông tin tổng hợp ở lúc thất bại cuối đã đủ.

### 7.3. Main/startup

Khi không có cấu hình hoặc dependency bắt buộc để vận hành, entry point nên ghi nguyên nhân rồi báo lỗi ra ngoài bằng mã thoát khác 0 hoặc cơ chế health/readiness thích hợp. **Không nên in “ready” nếu việc khởi tạo đã thất bại**.

### 7.4. Tầng thư viện hoặc repository

Các tầng thấp thường không biết nên dừng ứng dụng, trả HTTP nào hay cho retry bao nhiêu lần. Chúng nên ném exception có ngữ nghĩa phù hợp, cung cấp cause đầy đủ, và chỉ log nếu bản thân tầng đó thật sự xử lý hoặc có thông tin vận hành riêng không thể tái dựng ở trên.

## 8. Ngoại lệ không bắt trong thread, Future và CompletableFuture

Trong Java, **vị trí ngoại lệ xuất hiện quyết định ai có thể xử lý và ghi log**. Những ví dụ dưới đây là **đoạn minh họa cần ngữ cảnh/lớp bao quanh**, không phải các chương trình độc lập.

### 8.1. Thread thường

~~~java
Thread worker = new Thread(() -> {
    throw new IllegalStateException("Worker failed");
});
worker.setUncaughtExceptionHandler((thread, error) ->
        LOGGER.log(java.util.logging.Level.SEVERE,
                "event=worker.uncaught thread=" + thread.getName(),
                error));
worker.start();
~~~

Một ngoại lệ không bị bắt trong thread đó có thể tới **UncaughtExceptionHandler**. Nó không tự được catch bởi try/catch ở thread đã gọi worker.start(). Khi đặt handler, cần cẩn trọng về thông tin được ghi, trạng thái công việc và chính sách dừng/khởi động lại.

### 8.2. ExecutorService.submit và Future.get

~~~java
java.util.concurrent.ExecutorService pool =
        java.util.concurrent.Executors.newSingleThreadExecutor();
try {
    java.util.concurrent.Future<?> future = pool.submit(() -> {
        throw new IllegalStateException("Job failed");
    });
    future.get();
} catch (java.util.concurrent.ExecutionException ex) {
    LOGGER.log(java.util.logging.Level.SEVERE,
            "event=async.job.failed", ex.getCause());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    LOGGER.log(java.util.logging.Level.WARNING,
            "event=async.job.interrupted", ex);
} finally {
    pool.shutdown();
}
~~~

**submit(...)** thường lưu lỗi của tác vụ vào **Future**, còn **get()** thông báo qua ExecutionException; lúc này **ex.getCause()** là ngoại lệ gốc của tác vụ. Không giả định một uncaught-exception handler trên worker thread sẽ luôn bắt được lỗi của task gửi bằng submit(...). Nếu không quan sát Future, lỗi có thể bị bỏ qua ở tầng điều phối.

Khi bắt **InterruptedException**, nên **khôi phục cờ interrupt** nếu phương thức quyết định không ném tiếp, đồng thời tuân theo chính sách hủy công việc. Không biến yêu cầu hủy thành “lỗi nghiêm trọng” một cách máy móc.

### 8.3. CompletableFuture

~~~java
java.util.concurrent.CompletableFuture<String> future =
        java.util.concurrent.CompletableFuture.supplyAsync(() -> {
            throw new IllegalStateException("Remote call failed");
        });

future.whenComplete((value, error) -> {
    if (error != null) {
        LOGGER.log(java.util.logging.Level.SEVERE,
                "event=async.operation.failed", error);
    }
});
~~~

**CompletableFuture** có thể hoàn tất **exceptionally**; callback whenComplete thấy lỗi nếu kết quả không thành công. Lỗi có thể được bọc trong CompletionException hoặc loại wrapper khác tùy đường đi. Một dự án cần thống nhất ranh giới chịu trách nhiệm ghi log để tránh ghi cả ở callback lẫn nơi gọi join()/get().

### 8.4. Không dùng catch(Throwable) ở mọi nơi

**Exception** và **Error** đều kế thừa Throwable, nhưng nhiều **Error** (ví dụ một số lỗi nghiêm trọng của JVM) không phải vấn đề có thể khôi phục như một nghiệp vụ bình thường. Không dùng catch(Throwable) để nuốt tất cả và tiếp tục xử lý trong trạng thái không an toàn.

Với **OutOfMemoryError**, hệ thống có thể không đủ tài nguyên để tạo string, stack trace hoặc gửi log. Việc dựa hoàn toàn vào logger lúc này là rủi ro; nên có metrics, thiết lập JVM và cơ chế crash/health diagnostics phù hợp từ bên ngoài.

## 9. Chọn log level khi lỗi không thể xử lý

Mức độ log nên thể hiện **tác động và điều kiện mong đợi** của lỗi, không chỉ dựa vào việc nó là checked hay unchecked exception.

| Tình huống | Level thường cân nhắc | Vì sao |
| --- | --- | --- |
| Thiếu cấu hình bắt buộc khiến ứng dụng không khởi động | SEVERE (JUL) / ERROR | Sự cố ảnh hưởng tính sẵn sàng |
| Request thất bại do lỗi hạ tầng, không khôi phục được | SEVERE / ERROR | Thao tác quan trọng thất bại |
| Fallback từ cache sang database thành công | WARNING hoặc INFO | Bất thường nhưng hệ thống vẫn phục hồi |
| Dữ liệu người dùng không hợp lệ, trả 400 có chủ đích | Có thể không cần ERROR | Đây có thể là kết quả nghiệp vụ dự kiến |
| Retry một lần và lần sau thành công | DEBUG hoặc WARNING tùy chính sách | Tránh cảnh báo lỗi đã được phục hồi |
| Một job hoàn toàn thất bại sau số lần retry cho phép | ERROR/SEVERE tại ranh giới job | Kết quả cuối của đơn vị công việc là thất bại |

JUL có **Level.SEVERE** và **Level.WARNING**, không có sẵn Level.ERROR. Nếu dùng **SLF4J**, cú pháp thường là **logger.error("...", exception)**. Trong JUL là **logger.log(Level.SEVERE, "...", exception)**; không chép nguyên tên API giữa các thư viện.

Mọi lần thất bại đều là lỗi nghiêm trọng trong *ngữ cảnh riêng* hay không còn tùy hệ thống. Một ứng dụng nhận nhiều input sai sẽ không nên tạo cảnh báo production cho mỗi lỗi validation như thể đó là lỗi hạ tầng.

## 10. Ghi lỗi sao cho có thể tìm kiếm và liên kết

Giả sử có nhiều yêu cầu thanh toán đồng thời. Một message thiếu ngữ cảnh:

~~~text
ERROR Something failed
~~~

khó xác định phạm vi. Một message tốt hơn:

~~~text
ERROR service=payment event=payment.failed requestId=req-84 orderId=ORD-25 dependency=bank-gateway errorCode=PAYMENT_TIMEOUT outcome=failure
~~~

Dòng trên là ví dụ minh họa, không phải output của chương trình ở mục 6.

**requestId/traceId** giúp tìm các log của cùng một yêu cầu; **event** và **errorCode** giúp phân nhóm vấn đề; **dependency** giúp khoanh vùng thành phần hỏng. Trong nhiều hệ thống, có thể dùng structured logging/JSON để các trường được truy vấn chính xác, thay vì chỉ ghép text tự do.

Các nguyên tắc:

- Sử dụng **tên sự kiện ổn định** như startup.failed, job.failed, payment.failed.
- **Không đưa ID riêng lẻ vào tên event**, để việc nhóm sự kiện được nhất quán.
- Mô tả **tác động** và **hành động**: retry exhausted, rollback, request rejected, startup aborted.
- Nếu có Throwable, truyền ngoại lệ cho API và xác minh formatter/encoder thực sự có cách lưu stack trace phù hợp.
- **Không đưa request body, access token, session cookie, API key, mật khẩu, thông tin thanh toán hoặc dữ liệu cá nhân nhạy cảm** vào log thô; cả exception message và stack trace cũng cần được kiểm soát.

## 11. Log, metrics và cảnh báo khi gặp lỗi không thể xử lý

**Log** cho biết lỗi nào đã xảy ra, tại bước nào, cho request/job nào và kèm nguyên nhân để điều tra. **Metrics** trả lời số request lỗi, tỷ lệ lỗi, số job thất bại hoặc mức độ ảnh hưởng theo thời gian. **Tracing** giúp thấy luồng qua nhiều service.

Một lỗi SEVERE đơn lẻ có thể đáng chú ý nhưng không đủ chứng minh toàn hệ thống đang suy giảm. Ngược lại, hàng nghìn dòng lỗi giống nhau có thể là một sự cố lặp lại cần một cảnh báo theo tỷ lệ/điều kiện nhất quán.

Ví dụ:

~~~text
log:     event=payment.failed requestId=req-84 errorCode=PAYMENT_TIMEOUT
metric:  payment_failures_total{reason="timeout"} 125
~~~

Dữ liệu ví dụ. Tên metric và nhãn cụ thể phụ thuộc hệ thống triển khai. **Không gắn requestId hoặc orderId duy nhất làm label của metrics**, vì tạo rất nhiều chuỗi thời gian khác nhau (*high cardinality*). ID chi tiết thường thuộc log/trace, còn metrics dùng nhãn có số giá trị hữu hạn.

Nếu một nguồn log bị lọc hoặc gửi thất bại, **thiếu dòng log không chứng minh mã chưa chạy**. Khi điều tra, đối chiếu cả trạng thái thực tế, metrics, traces và dữ liệu nghiệp vụ.

## 12. Xử lý tài nguyên và trạng thái khi thất bại

Ghi log là quan sát; **nó không thay thế rollback, giải phóng tài nguyên hay tính đúng đắn của ứng dụng**.

- Với kết nối/tệp, ưu tiên **try-with-resources** để giải phóng tài nguyên khi exception phát sinh.
- Với transaction, cần chính sách **rollback/commit** rõ ràng; logging thành công không đồng nghĩa transaction đã được rollback.
- Với retry, chỉ thử lại khi thao tác đủ an toàn, kiểm soát số lần và thời gian chờ; cân nhắc tính idempotent để tránh lặp tác dụng phụ.
- Với request không thể xử lý, trả kết quả lỗi rõ ràng và an toàn; tránh trả nguyên Throwable/stack trace cho client.
- Với khởi động thất bại, không công bố readiness thành công; nên kết thúc hoặc để orchestration thay thế instance khi cần.
- Với ứng dụng bất đồng bộ, cập nhật trạng thái **failed** cho job và truyền lỗi đến nơi giám sát, tránh kết thúc bình thường như thể đã hoàn thành.

Ngoài ra, log quá nhiều stack trace có thể tạo tải lớn. Đừng tắt thông tin chẩn đoán quan trọng chỉ để tiết kiệm dung lượng, nhưng nên chọn đúng ranh giới ghi, giới hạn lặp vô nghĩa và cấu hình retention theo yêu cầu vận hành.

## 13. Các lỗi lập trình thường gặp

| Lỗi | Hệ quả | Cách xử lý phù hợp |
| --- | --- | --- |
| catch(Exception) rồi bỏ qua | Công việc thất bại nhưng chương trình báo thành công | Xử lý thật sự hoặc ném tiếp cho ranh giới |
| Log lỗi ở mọi tầng rồi ném tiếp | Nhiều stack trace trùng cho một sự cố | Chọn một ranh giới chịu trách nhiệm log |
| Chỉ ghi ex.getMessage() | Mất throwable/cause và stack trace | Truyền Throwable cho API logging |
| Bọc exception mà không truyền cause | Mất đường dẫn tới nguyên nhân ban đầu | Sử dụng constructor nhận cause |
| Gọi logger.severe rồi tiếp tục dù trạng thái sai | Vi phạm bất biến hoặc lỗi lan rộng | Dừng/cô lập tác vụ theo chính sách |
| Mọi validation error đều ghi SEVERE | Tạo báo động giả và nhiễu log | Phân biệt lỗi dự kiến với lỗi hạ tầng |
| Ghi dữ liệu nhạy cảm trong message/exception | Rò rỉ qua log tập trung | Chỉ giữ trường cần thiết, che dữ liệu |
| Giả định System.exit luôn flush log từ xa | Có thể mất bản ghi đang đệm hoặc chưa được nhận | Flush phù hợp và dùng hạ tầng quan sát ngoài tiến trình |
| Bắt Throwable và cố chạy tiếp khi JVM lỗi nghiêm trọng | Hệ thống có thể không còn đáng tin | Chọn fail-fast/giám sát JVM phù hợp |
| Bỏ qua Future/CompletableFuture thất bại | Lỗi tác vụ chạy nền không được báo đúng | Quan sát kết quả, đặt ranh giới xử lý rõ ràng |
| Bắt InterruptedException rồi bỏ qua | Hủy tác vụ không hiệu quả | Truyền tiếp hoặc khôi phục cờ interrupt |

## 14. Tự kiểm tra kiến thức

**Câu 1.** Một repository ném IOException và service không có cách phục hồi hợp lệ. Service có nhất thiết phải log ERROR trước khi ném tiếp không?

**Đáp án:** Không. Nếu tầng boundary sẽ ghi một log đầy đủ, service có thể để ngoại lệ đi lên hoặc bọc có cause để bổ sung ngữ cảnh. Điều này tránh ghi trùng cho cùng một thất bại.

**Câu 2.** Một request bị lỗi không phục hồi được và trả 500. Có bắt buộc tắt toàn bộ JVM không?

**Đáp án:** Không. Ranh giới HTTP có thể rollback và trả 500 cho request đó, trong khi các yêu cầu khác tiếp tục. Chỉ dừng instance khi trạng thái hệ thống hoặc chính sách vận hành thực sự yêu cầu.

**Câu 3.** Sự khác nhau giữa LOGGER.severe(ex.getMessage()) và LOGGER.log(Level.SEVERE, "event=...", ex) là gì?

**Đáp án:** Cách thứ hai giữ đối tượng Throwable trong LogRecord để formatter/encoder có thể in stack trace và chuỗi nguyên nhân. Cách đầu chỉ truyền một chuỗi.

**Câu 4.** Vì sao bắt IOException rồi throw new IllegalStateException(ex.getMessage()) chưa tốt?

**Đáp án:** Nó làm mất cause. Nên dùng **new IllegalStateException("Mô tả ngữ cảnh", ex)** để giữ ngoại lệ gốc.

**Câu 5.** Một task gửi bằng ExecutorService.submit ném RuntimeException. try/catch ở nơi gọi submit có chắc bắt được ngoại lệ đó không?

**Đáp án:** Không. Lỗi được lưu trong Future; khi gọi **get()**, bên gọi có thể nhận **ExecutionException** và truy cập cause. Cần quan sát kết quả task ở ranh giới phù hợp.

**Câu 6.** Logger đã được gọi ở SEVERE nhưng không thấy stack trace. Có phải JUL bỏ mất Throwable không?

**Đáp án:** Chưa chắc. Formatter/handler có thể không hiển thị record.getThrown(). Phải kiểm tra cấu hình đầu ra; ví dụ Java chạy được ở mục 6 cố ý chỉ in loại ngoại lệ và message.

**Câu 7.** Tại sao chương trình không thể khởi động lại nên báo exit code khác 0?

**Đáp án:** Để shell, service manager hoặc orchestrator biết quá trình khởi động thất bại. Chỉ log một dòng SEVERE mà tiến trình trả exit code 0 có thể khiến công cụ ngoài hiểu nhầm là thành công.

**Ghi nhớ:** Khi một tầng Java **không thể xử lý lỗi an toàn**, hãy **giữ ngoại lệ/cause và chuyển lên ranh giới phù hợp**. Ranh giới đó chịu trách nhiệm **rollback hoặc cô lập công việc, ghi log một lần với đầy đủ ngữ cảnh, báo kết quả thất bại đúng và quyết định có cần dừng tiến trình hay không**. Logging giúp chẩn đoán, còn xử lý lỗi đúng quyết định tính an toàn của ứng dụng.
