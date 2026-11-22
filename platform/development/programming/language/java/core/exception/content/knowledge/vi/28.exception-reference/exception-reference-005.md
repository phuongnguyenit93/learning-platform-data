# Bảng chọn cách xử lý lỗi theo ranh giới API hoặc luồng

## 1. Mục đích của bảng tra cứu

Khi một lỗi xuất hiện trong Java, câu hỏi đầu tiên không nên là “viết catch ở đâu cho hết báo đỏ?”, mà là **“thành phần nào có đủ trách nhiệm và thông tin để quyết định điều gì xảy ra tiếp theo?”**. Tầng xử lý dữ liệu, service nghiệp vụ, controller, thread worker, callback, executor và caller của Future không có cùng hợp đồng. Một cách bắt lỗi phù hợp ở ranh giới này có thể làm sai nghĩa ở ranh giới khác.

README này là **bảng tra cứu quyết định xử lý exception theo ranh giới API hoặc luồng** trong Java Core. Nó giúp chọn một trong những hướng:

- **Lan truyền nguyên trạng** bằng throws hoặc throw e khi caller được phép và nên quyết định.
- **Chuyển đổi có cause** thành exception thuộc abstraction cao hơn khi ranh giới API yêu cầu.
- **Phục hồi bằng fallback** nếu có kết quả thay thế thật sự hợp lệ theo hợp đồng.
- **Dừng tác vụ, giữ interrupt flag** khi một callback không được phép ném InterruptedException.
- **Hủy hoặc ngừng chờ** theo chính sách riêng, không đánh đồng timeout, interruption và cancellation.
- **Dọn tài nguyên / rollback** theo ownership, đồng thời giữ primary và suppressed exceptions.
- **Ghi log, trả kết quả lỗi hoặc thông báo ra ngoài** ở boundary có trách nhiệm, không log lặp ở mọi lớp.

Bảng này là **khung lựa chọn**, không phải luật bắt buộc mọi hệ thống phải sử dụng một loại exception hoặc mã trạng thái cụ thể. Ví dụ HTTP status 400/503 trong chương trình là cách ánh xạ minh họa, không phải một quy tắc tự động của Java.

**Quy tắc định hướng:** Tầng trung gian thường nên **bảo toàn thông tin lỗi và chuyển nó tới tầng có thể quyết định**. Tầng sở hữu vòng đời request, job hay task mới quyết định dừng, retry, fallback, trả response hoặc chuyển thành cảnh báo.

## 2. Xác định ranh giới trước khi quyết định catch

Một **ranh giới** là nơi trách nhiệm hoặc hợp đồng thay đổi. Có thể là:

| Ranh giới | Ai đang gọi ai? | Điều bên nhận thực sự có thể quyết định |
| --- | --- | --- |
| Phương thức nội bộ | Helper → helper khác | Kiểm tra tiền điều kiện, cung cấp context, hoặc ném tiếp |
| Adapter I/O | Repository → filesystem/network/database | Chuyển lỗi I/O thành hợp đồng adapter, quản lý resource thuộc sở hữu |
| Service | Controller/job → business service | Quy tắc nghiệp vụ, tính nguyên tử, có phục hồi được hay không |
| API công khai | Client → public API | Loại exception cam kết hoặc kiểu kết quả lỗi ổn định |
| HTTP controller | Remote caller → endpoint | Mã phản hồi, nội dung lỗi an toàn, correlation ID |
| Runnable | Executor/thread → Runnable.run | Không thể khai báo checked exception trên run |
| Callable | Executor → Callable.call | Có thể ném Exception; executor có thể lưu lỗi trong Future |
| Future.get | Thread caller → Future | Chờ kết quả; thấy lỗi tác vụ qua ExecutionException |
| CompletableFuture.join | Thread caller → CompletionStage | Thấy exceptional completion qua CompletionException thông thường |
| Callback/event handler | Framework → callback | Tuân thủ chữ ký framework, tránh làm hỏng event loop |
| Thread boundary | Worker ↔ supervisor | Quan sát dừng, interruption, uncaught exception và vòng đời worker |
| Resource boundary | Chủ sở hữu → AutoCloseable | Đóng đúng lúc, bảo toàn lỗi chính/lỗi cleanup |
| Transaction boundary | Unit of work → database | Commit/rollback/compensation theo hợp đồng |
| Service-to-service | Ứng dụng → dependency | Deadline, retry có giới hạn, idempotency, lỗi hệ ngoài |

Một đoạn **catch** chỉ nên xuất hiện khi tầng đó làm được điều hữu ích: phục hồi đúng, chuyển abstraction, cleanup có trách nhiệm hoặc đưa lỗi tới hệ thống điều phối. **Catch rồi tiếp tục như chưa có gì xảy ra** không phải là lựa chọn mặc định.

## 3. Bảng quyết định nhanh — chọn cách xử lý theo tình huống

| Tình huống | Ranh giới chịu trách nhiệm | Lựa chọn ưu tiên | Tránh |
| --- | --- | --- | --- |
| Helper nhận input sai | Phương thức/API sở hữu validation | Ném loại lỗi đầu vào theo hợp đồng, thường IllegalArgumentException hoặc subtype | Ném lỗi I/O không liên quan; che dữ liệu sai bằng null |
| Caller gọi helper có thể throws IOException | Caller/tầng trên được phép nhận checked exception | Để IOException truyền lên nếu chưa thể quyết định | Catch rồi chỉ printStackTrace và trả thành công |
| Repository phát sinh lỗi tầng lưu trữ | Adapter/service boundary | Giữ IOException/SQLException hoặc wrap thành domain/infrastructure exception **có cause** theo contract | Tạo RuntimeException chung không cause |
| Service có fallback thực sự tương đương | Service được quyền recovery | Trả fallback hợp lệ và ghi nhận degraded mode khi cần | Fallback cho mọi lỗi, kể cả lỗi toàn vẹn dữ liệu |
| Service vi phạm invariant | Business boundary | Ném loại exception thể hiện trạng thái sai | Retry vô hạn một điều kiện không thể tự sửa |
| Controller nhận input sai | Controller/API boundary | Chuyển thành response lỗi client theo quy tắc API | Trả status thành công hoặc lộ stack trace |
| Dependency tạm thời không sẵn sàng | Boundary có policy retry | Retry có giới hạn **nếu thao tác an toàn/idempotent**, hoặc trả lỗi availability | Retry tất cả Throwable |
| Runnable gặp InterruptedException | Runnable.run không khai báo checked exception | Khôi phục Thread.currentThread().interrupt() và thoát theo contract | Nuốt interruption rồi tiếp tục vòng chờ |
| Method được phép throws InterruptedException | Tầng caller biết cách xử lý | Lan truyền nguyên trạng | Khôi phục cờ rồi tiếp tục blocking không có lý do |
| Callable ném exception | Callable.call có throws Exception | Để exception truyền ra nếu executor quản lý kết quả | Giả định caller Future.get nhận lỗi worker trực tiếp |
| Future.get báo ExecutionException | Thread caller đọc task | Xem getCause(), quyết định ở caller | Coi chính Future.get là nơi bug gốc |
| Future.get bị InterruptedException | Thread caller bị ngắt khi chờ | Lan truyền hoặc khôi phục flag tại boundary phù hợp | Coi task chắc chắn đã bị hủy |
| Future.get(timeout) báo TimeoutException | Caller hết hạn chờ | Ngừng chờ/áp dụng deadline, có thể cân nhắc cancel theo ownership | Tưởng timeout tự cancel task |
| CompletableFuture.join báo CompletionException | Consumer stage | Xem cause, phân biệt lỗi có thể recover | Bắt mỗi CompletionException và bỏ qua cancellation |
| Future đã canceled | Caller/worker boundary | Xử lý CancellationException và trạng thái cancel riêng | Khẳng định worker đã dừng hoặc rollback |
| try-with-resources body và close cùng lỗi | Resource boundary | Giữ lỗi body primary, close lỗi suppressed | Để finally close che lỗi body |
| Transaction thất bại | Chủ sở hữu transaction | Rollback/compensation phù hợp, giữ lỗi rollback | Cho rằng close tự rollback mọi thay đổi |
| Uncaught exception ở worker thread | Thread/supervisor boundary | Quan sát, đánh dấu job thất bại, quản lý worker lifecycle | Dựa vào main thread để luôn thấy lỗi worker |
| Error nghiêm trọng | Boundary chẩn đoán/vận hành | Để propagate và cleanup cần thiết khi an toàn | Catch(Throwable) rồi trả fallback như lỗi thường |

**Đọc bảng theo thứ tự:** xác định **tình huống thật** → xác định **ai sở hữu công việc/tài nguyên** → chọn **hợp đồng lỗi** → xác định **có thể recover không** → bảo toàn **cause/interrupt/state** → đặt test kiểm chứng.

Bảng là định hướng theo Java 17+, không bảo đảm hành vi giống hệt khi dùng framework với policy riêng. Ví dụ có executor bắt exception, HTTP mapper tùy chỉnh hoặc API trả Result thay vì ném lỗi; khi đó ưu tiên contract chính thức của ứng dụng.

## 4. Sơ đồ quyết định bằng câu hỏi

Khi gặp một exception, tự hỏi tuần tự:

**Câu 1 — Đây là điều kiện bình thường có thể trả về kết quả không?** Nếu dữ liệu “không tìm thấy” là một trạng thái dự kiến, có thể dùng Optional/Result hoặc giá trị có ngữ nghĩa. Không cần tạo exception chỉ để biểu diễn mọi nhánh điều khiển.

**Câu 2 — Tầng này có quyền và khả năng recovery không?** Nếu biết một fallback hợp lệ, retry có kiểm soát hoặc một bước bù trừ đúng, có thể xử lý tại đây. Nếu không, truyền lỗi tới caller.

**Câu 3 — Lỗi có đổi abstraction không?** Ở một API công khai, không nhất thiết lộ loại SQLException/provider cụ thể. Có thể wrap thành exception mức domain hoặc infrastructure **nhưng phải giữ cause**.

**Câu 4 — Chữ ký có cho phép checked exception không?** Method bình thường có thể khai báo throws; Runnable.run và nhiều callback thì không. Khi không thể truyền trực tiếp, phải có policy chuyển đổi hoặc kết thúc rõ ràng.

**Câu 5 — Có liên quan timeout, interrupt hoặc cancel không?** Ba sự kiện này khác nhau. Timeout của lần chờ không chứng minh task kết thúc. Interruption thuộc thread đang chờ. Cancellation thuộc trạng thái Future hoặc cơ chế hủy tác vụ.

**Câu 6 — Có tài nguyên hoặc side effect nào cần dọn không?** Cleanup và rollback phải do owner xử lý; exception được lan truyền không tự đảo ngược trạng thái.

**Câu 7 — Ai log và ai báo kết quả cuối?** Tầng ở boundary có thể log một lần, trả API response, hoàn tất Future bất thường hoặc báo job status. Không log trùng chỉ vì mỗi tầng có catch.

Nếu trả lời “không biết” ở câu 2 hoặc 6, **đừng tự biến exception thành thành công**. Giữ thông tin nguyên nhân và để tầng có quyền quyết định xử lý.

## 5. Cách chọn giữa throws, throw e, wrap và fallback

| Cách làm | Khi phù hợp | Điều cần giữ |
| --- | --- | --- |
| Khai báo **throws IOException** | Caller có thể xử lý lỗi I/O; abstraction cho phép | Kiểu checked exception và stack trace ban đầu |
| Không catch, để exception tự lan truyền | Tầng trung gian không bổ sung policy | Không làm thay đổi Throwable |
| **catch(E e) { throw e; }** | Cần xử lý ngắn trước khi lan truyền | Chính object e và lỗi cleanup nếu có |
| **throw new DomainException(..., e)** | Ranh giới đổi từ lỗi hạ tầng sang nghiệp vụ | Cause, context phù hợp và contract mới |
| **return fallback** | Tầng có kết quả thay thế thật sự hợp lệ | Phân loại lỗi, ghi nhận degraded behavior khi cần |
| **completeExceptionally(e)** | API CompletableFuture chủ động biểu diễn lỗi | Throwable chính và semantics completion |
| **Thread.currentThread().interrupt(); return;** | Boundary không throws InterruptedException và policy là dừng | Interrupt flag và cleanup |
| **return Result.failure(code)** | API được thiết kế để biểu diễn thất bại bằng giá trị | Error code có cấu trúc, thông tin cho caller |
| **retry bounded** | Lỗi tạm thời, thao tác có thể retry an toàn | Budget, deadline, idempotency và nguyên nhân cuối |
| **try-with-resources** | Resource thuộc scope và AutoCloseable | Close trên mọi đường thoát, primary/suppressed |

Không nên **wrap một exception nhiều lần ở mọi tầng** nếu wrapper không thêm giá trị. Mỗi wrapper có thể khiến cây cause phức tạp và log khó đọc. Chỉ wrap ở nơi abstraction thật sự thay đổi hoặc caller cần thông tin ngữ cảnh mới.

Nếu wrapper có cause, caller cần kiểm tra **getCause()**. Việc chỉ ném **new RuntimeException(e.getMessage())** làm mất object lỗi gốc và stack trace/cause của nó.

## 6. Checked và unchecked theo ranh giới API

**Checked exceptions** như IOException, SQLException, InterruptedException, ExecutionException và TimeoutException yêu cầu caller catch hoặc khai báo theo quy tắc compiler.

**Unchecked exceptions** gồm RuntimeException và subclass (IllegalArgumentException, IllegalStateException, NumberFormatException, CancellationException, CompletionException), cùng Error. Compiler không buộc caller xử lý, nhưng điều đó không khiến lỗi tự biến mất.

Bảng chọn:

| Loại API | Thiết kế thường gặp | Lưu ý |
| --- | --- | --- |
| API Java Core có thao tác blocking interruptible | Khai báo **throws InterruptedException** | Cho caller quyền quyết định hủy/chờ |
| API đọc/ghi file | **throws IOException** hoặc kết quả lỗi rõ ràng | Đừng che I/O thành sai tham số |
| Helper validation | **IllegalArgumentException**/subtype | Phân biệt input sai với lỗi hệ thống |
| Phương thức có invariant bắt buộc | **IllegalStateException** hoặc loại riêng | Không tự đổi thành fallback mơ hồ |
| Public library API nhiều implementation | Loại exception ổn định theo contract | Đừng ép caller phụ thuộc exception vendor |
| Framework callback không checked throws | Kết thúc/khôi phục interrupt, hoặc unchecked wrapper khi contract cho phép | Không thêm throws vào method override trái chữ ký |
| Async API trả CompletableFuture | Exceptional completion/cancellation state | Consumer cần quan sát bằng get/join/handler |
| API hướng data với Result | Trả mã lỗi/thông tin cấu trúc | Đừng vừa trả success vừa báo thất bại không rõ ràng |

**Đừng phân loại bằng catch(Exception) chung rồi quyết định mọi lỗi đều retry.** Tính checked/unchecked chỉ là một chiều; điều quan trọng hơn là **nghĩa của exception trong hợp đồng cụ thể**.

## 7. Ranh giới đồng bộ: helper → repository → service → API

Một đường đi đơn giản:

~~~text
Caller / Controller
       |
       v
Application Service
       |
       v
Repository / Adapter
       |
       v
I/O, filesystem, network, database
~~~

Ở tầng repository, lỗi I/O có thể được truyền bằng IOException hoặc map sang infrastructure exception công khai của adapter. Ở service, nếu nghiệp vụ không thể tiếp tục, nên giữ nguyên lỗi hoặc thêm context cần thiết. Ở controller, có thể chuyển nó thành response lỗi bên ngoài.

Ví dụ minh họa:

~~~java
// Mã minh họa theo ngữ cảnh Java.
static String repository(String key) throws IOException {
    if (key.equals("down")) {
        throw new IOException("storage unavailable");
    }
    return "value:" + key;
}

static String service(String raw) throws IOException {
    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException("id required");
    }
    return repository(raw.trim());
}
~~~

Ở đây **service** không catch IOException vì ví dụ cho caller quyền quyết định. Khi caller là một boundary HTTP, nó có thể map IllegalArgumentException thành lỗi client và IOException thành lỗi availability.

**Cảnh báo về mã trạng thái:** HTTP status và payload phải dựa vào quy tắc API, bảo mật, semantics request và chính sách system. Không có một quy tắc Java Core rằng mọi IOException là 503 hoặc mọi IllegalArgumentException là 400. Trong ví dụ runnable kế tiếp, các con số chỉ giúp thấy *lựa chọn nằm ở boundary*.

## 8. Ví dụ Java 17+ hoàn chỉnh: các boundary và kết quả cụ thể

Chương trình sau dùng Java SE để tạo những trường hợp có thể kiểm tra độc lập:

1. Request boundary minh họa ánh xạ input sai và dependency không sẵn sàng.
2. Resource boundary giữ exception của công việc làm primary, close error làm suppressed.
3. Runnable boundary khôi phục interrupt flag và kết thúc.
4. Callable ném IOException trong executor; caller đọc Future nhận ExecutionException có cause.
5. CompletableFuture hoàn tất bất thường: **get** và **join** trả wrapper khác nhau nhưng cùng cause.
6. Canceled Future báo CancellationException; một lần timed get báo TimeoutException nhưng task chưa tự canceled.

Lưu file **ErrorBoundaryDecisionDemo.java**:

~~~java
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.CancellationException;
import java.util.concurrent.atomic.AtomicBoolean;

public class ErrorBoundaryDecisionDemo {
    static String repository(String key) throws IOException {
        if (key.equals("down")) {
            throw new IOException("storage unavailable");
        }
        return "value:" + key;
    }

    static String service(String raw) throws IOException {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("id required");
        }
        return repository(raw.trim());
    }

    static String requestBoundary(String raw) {
        try {
            return "200 " + service(raw);
        } catch (IllegalArgumentException badInput) {
            return "400 " + badInput.getMessage();
        } catch (IOException unavailable) {
            return "503 " + unavailable.getMessage();
        }
    }

    static final class BrokenClose implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void transactionLikeWork() throws IOException {
        try (BrokenClose resource = new BrokenClose()) {
            throw new IOException("work failed");
        }
    }

    static void interruptBoundary() throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);
        CountDownLatch gate = new CountDownLatch(1);
        AtomicBoolean restored = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            try {
                ready.countDown();
                gate.await();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                restored.set(Thread.currentThread().isInterrupted());
            }
        });
        worker.start();
        ready.await();
        worker.interrupt();
        worker.join();
        System.out.println("runnable restored=" + restored.get());
    }

    static void futureBoundary() throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<String> task = pool.submit(() -> {
                throw new IOException("task I/O");
            });
            try {
                task.get();
            } catch (ExecutionException failure) {
                System.out.println("future cause="
                        + failure.getCause().getClass().getSimpleName());
            }
        } finally {
            pool.shutdownNow();
        }
    }

    static void completionBoundary() throws InterruptedException {
        CompletableFuture<String> failed = new CompletableFuture<>();
        IOException original = new IOException("async I/O");
        failed.completeExceptionally(original);
        try {
            failed.get();
        } catch (ExecutionException wrapper) {
            System.out.println("get cause original="
                    + (wrapper.getCause() == original));
        }
        try {
            failed.join();
        } catch (CompletionException wrapper) {
            System.out.println("join cause original="
                    + (wrapper.getCause() == original));
        }

        CompletableFuture<String> canceled = new CompletableFuture<>();
        canceled.cancel(false);
        try {
            canceled.join();
        } catch (CancellationException failure) {
            System.out.println("canceled=" + failure.getClass().getSimpleName());
        }

        CompletableFuture<String> pending = new CompletableFuture<>();
        try {
            pending.get(1, TimeUnit.MILLISECONDS);
        } catch (ExecutionException failure) {
            throw new AssertionError("Unexpected completion", failure);
        } catch (TimeoutException expected) {
            System.out.println("timed wait=" + expected.getClass().getSimpleName());
        }
        pending.complete("later");
        System.out.println("after timeout=" + pending.join());
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("request ok=" + requestBoundary(" 42 "));
        System.out.println("request invalid=" + requestBoundary(" "));
        System.out.println("request storage=" + requestBoundary("down"));
        try {
            transactionLikeWork();
        } catch (IOException primary) {
            System.out.println("primary=" + primary.getMessage());
            System.out.println("suppressed="
                    + primary.getSuppressed()[0].getMessage());
        }
        interruptBoundary();
        futureBoundary();
        completionBoundary();
    }
}
~~~

Biên dịch và chạy JDK 17 trở lên:

~~~bash
javac --release 17 ErrorBoundaryDecisionDemo.java
java ErrorBoundaryDecisionDemo
~~~

Stdout đã được kiểm tra khi biên dịch/chạy:

~~~text
request ok=200 value:42
request invalid=400 id required
request storage=503 storage unavailable
primary=work failed
suppressed=close failed
runnable restored=true
future cause=IOException
get cause original=true
join cause original=true
canceled=CancellationException
timed wait=TimeoutException
after timeout=later
~~~

**Lưu ý về chương trình:** Không có HTTP server thật; chuỗi **200/400/503** là kết quả minh họa cho cách một boundary có thể map lỗi theo chính sách. **transactionLikeWork** chỉ mô phỏng một phạm vi tài nguyên, không triển khai transaction hay rollback thật. Cả hai được đặt tên để gợi nhớ responsibility boundary, không phải tuyên bố framework tự xử lý như vậy.

## 9. Diễn giải kết quả qua ranh giới

**request ok:** Service trả kết quả bình thường, boundary thêm tiền tố trạng thái thành công minh họa.

**request invalid:** Input rỗng khiến service ném IllegalArgumentException; boundary **có đủ thông tin** để chuyển thành trạng thái client error. Không để stack trace Java hiển thị như payload công khai.

**request storage:** Repository ném IOException. Service để lỗi truyền lên, boundary minh họa response 503. Trong ứng dụng thực, mapper phải xem lỗi có thực sự là temporary unavailability hay không; cùng IOException có thể do path sai, permission, disk failure hoặc dependency không sẵn sàng.

**primary/suppressed:** TWR giữ IOException **work failed** làm lỗi chính, còn **close failed** là suppressed. Nếu cuối cùng log ở controller chỉ ghi message primary mà không truyền Throwable, phần lỗi cleanup bị mất.

**runnable restored=true:** Worker đang chờ CountDownLatch nhận interrupt. Vì Runnable.run không được khai báo checked InterruptedException, catch đã khôi phục cờ rồi kết thúc. Main dùng join để quan sát kết quả sau khi worker đã kết thúc. Trong production, cần cleanup phù hợp với task thật.

**future cause=IOException:** Callable trong executor ném IOException. ExecutorService.submit giữ kết quả lỗi trong Future, và caller của Future.get bắt ExecutionException để tìm IOException trong cause.

**get/join cause original=true:** Hai API quan sát cùng CompletableFuture đã completeExceptionally bằng một IOException. get báo ExecutionException, join báo CompletionException, nhưng cause là cùng object IOException ban đầu.

**canceled:** Future đã bị canceled trực tiếp. join ném CancellationException; không thể kết luận từ dòng này worker nào đã dừng, bởi CompletableFuture ví dụ không có worker thực sự.

**timed wait/after timeout:** get có timeout chờ một CompletableFuture chưa được hoàn tất. TimeoutException chỉ làm lượt chờ kết thúc; sau đó **complete("later")** vẫn thành công và join nhận kết quả.

Các tình huống được dựng có điều khiển: latch và trạng thái Future rõ ràng, không dựa vào Thread.sleep ngẫu nhiên để hy vọng một race xảy ra.

## 10. Bảng chọn: Java method thường và API library

| Điều kiện | Hợp đồng method nên thể hiện | Xử lý ở tầng đang xét |
| --- | --- | --- |
| Input không hợp lệ | Exception input được định nghĩa rõ hoặc Result.failure | Validate sớm, message an toàn, test đúng subtype nếu cần |
| Method có thể bị ngắt khi chờ | throws InterruptedException khi hợp lệ | Để caller quyết định dừng/hủy |
| I/O thất bại | throws IOException hoặc lỗi infrastructure có cause | Không tự biến thành null nếu null có ý nghĩa bình thường |
| Invariant trạng thái bị vi phạm | IllegalStateException / loại domain riêng | Không retry mù quáng |
| Một operation optional có thể thiếu dữ liệu | Optional/result nếu missing là bình thường | Không dùng exception làm đường lặp phổ biến khi không cần |
| Code có thể thay đổi state trước khi lỗi | Contract exception safety/transaction | Chuẩn bị trước khi công bố, rollback nếu được bảo đảm |
| API công khai không muốn lộ vendor exception | Wrapper thuộc abstraction public | Giữ original trong cause, không mất stack trace |

**Lan truyền checked exception** thường hợp lý khi tầng trung gian chưa có đủ ngữ cảnh. Ngược lại, API public cần một vocabulary lỗi ổn định có thể wrap lỗi từ thư viện dưới, nhưng phải giữ nguyên nhân và tài liệu hóa nghĩa.

**Không nên ném RuntimeException chung chỉ để khỏi khai báo throws.** Đây là quyết định thiết kế hợp đồng, không phải cách né compiler. Một RuntimeException không có cause có thể khiến caller và hệ thống log mất thông tin quan trọng.

## 11. Bảng chọn: Throwable type cho kết quả lỗi

| Loại được quan sát | Thường mô tả | Hướng xử lý |
| --- | --- | --- |
| IllegalArgumentException | Caller vi phạm tiền điều kiện | Sửa input, trả lỗi validation tại API boundary |
| NumberFormatException | Chuỗi chuyển số không hợp lệ | Nêu lỗi định dạng; không coi là lỗi hạ tầng |
| IllegalStateException | Trạng thái object không cho phép thao tác | Xem invariant/lifecycle; sửa logic hoặc từ chối hợp lệ |
| IOException | Lỗi I/O theo hợp đồng API | Phân loại transient/permanent dựa trên cause và ngữ cảnh |
| SQLException | Lỗi theo JDBC/database contract | Chính sách transaction, timeout, retry dựa trên SQLState/provider |
| InterruptedException | Thread caller/worker đang chờ nhận interrupt | Lan truyền khi được phép hoặc khôi phục cờ tại boundary |
| TimeoutException | Lượt chờ quá hạn hoặc lỗi timeout được biểu diễn | Xem deadline và task ownership, phân biệt wrapper |
| ExecutionException | Future.get báo lỗi task | Phân tích getCause() |
| CompletionException | CompletionStage/join truyền exceptional completion | Phân tích getCause() |
| CancellationException | Future đã canceled hoặc completion bị hủy | Phân biệt cancellation với lỗi nghiệp vụ |
| Error | Điều kiện lỗi nghiêm trọng của runtime | Tránh catch thành fallback; cleanup an toàn khi thích hợp |

Bảng này không thay thế API contract. Ví dụ một **TimeoutException** có thể là exception trực tiếp từ get(timeout) hoặc là **cause** của ExecutionException khi CompletableFuture bị **orTimeout** hoàn tất bất thường. Cùng một class có thể xuất hiện ở hai boundary với ý nghĩa xử lý khác nhau.

## 12. Ranh giới Runnable: không được ném checked exception

**Runnable.run()** có chữ ký không khai báo checked exception:

~~~java
// Chữ ký khái niệm của Runnable.
void run();
~~~

Một lambda Runnable muốn gọi method throws InterruptedException cần bắt exception hoặc chuyển đổi theo contract. Policy phổ biến khi interruption mang nghĩa yêu cầu dừng:

~~~java
// Mã minh họa bên trong một Runnable.
try {
    blockingOperation();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
}
~~~

**Tại sao khôi phục cờ?** Nhiều blocking APIs như CountDownLatch.await() xóa trạng thái interrupt khi ném InterruptedException. Nếu không thể truyền checked exception qua run, khôi phục cờ giúp giữ tín hiệu để code điều phối hoặc các tầng có quyền quan sát sau đó.

**Không khôi phục cờ rồi tiếp tục một vòng lặp blocking vô hạn** trừ khi có chính sách cụ thể; các blocking calls tiếp theo có thể ném ngay hoặc task tiếp tục hoạt động trái yêu cầu dừng. Catch rồi bỏ qua làm mất signal và có thể khiến shutdown bị kẹt.

Nếu callback không thể return theo thiết kế, có thể dùng adapter hoặc unchecked wrapper có cause theo contract framework. Tuy nhiên, đừng dùng **IllegalStateException** như một “loại cancellation chuẩn” không có tài liệu; cơ chế hủy của framework có thể có kiểu/semantics riêng.

## 13. Ranh giới Callable, ExecutorService và lỗi task

**Callable<V>.call()** khai báo **throws Exception**, nên một Callable có thể truyền checked IOException hoặc InterruptedException ra khỏi call.

~~~java
// Mã minh họa với ExecutorService pool đã có.
Future<String> future = pool.submit(() -> {
    throw new IOException("remote failure");
});
~~~

Khi task đã hoàn tất bất thường, caller quan sát bằng **future.get()** thường nhận **ExecutionException** chứa IOException trong **getCause()**. Không phải chính caller nhận IOException trực tiếp qua chữ ký Future.get.

| API khởi chạy | Nơi lỗi được quan sát thường gặp | Lưu ý |
| --- | --- | --- |
| Thread.start với Runnable | Uncaught exception handler nếu lỗi thoát khỏi run | Không trả Future tự động |
| ExecutorService.execute(Runnable) | Theo executor/thread factory/uncaught handler/logging policy | Không cung cấp Future từ execute |
| ExecutorService.submit(Runnable) | Future.get báo ExecutionException khi task ném lỗi | Lỗi có thể được capture, không đi tới uncaught handler theo cách người viết mong |
| ExecutorService.submit(Callable) | Future.get báo ExecutionException với cause từ Callable | Callable được phép throws Exception |
| invokeAll | Danh sách Future; cần xem get trên từng Future | Không suy ra tất cả task thành công chỉ vì invokeAll trả list |
| invokeAny | Trả kết quả của một task thành công; có exception nếu không đạt contract | Cần đọc semantics và cancellation của các task còn lại |

**Không dựa vào Thread.UncaughtExceptionHandler như cơ chế duy nhất bắt lỗi của task submit.** Executor thường ghi nhận lỗi vào Future. Nếu caller không bao giờ gọi get hay có callback quan sát, lỗi có thể bị bỏ qua về mặt vận hành dù Future đã hoàn tất bất thường.

Tương tự, **execute** không cam kết có cùng cách báo lỗi với **submit**. Một implementation có thể ghi log, chuyển cho handler hoặc quản lý thread riêng. Khi chọn chính sách, cần xác định executor implementation, thread factory, error handler và nơi caller thực sự quan sát kết quả.

## 14. Bảng chọn: Future.get và thread caller

| Tình huống | get / get(timeout) biểu hiện | Thao tác tại caller |
| --- | --- | --- |
| Task hoàn tất bình thường | Trả T | Xử lý kết quả |
| Task ném lỗi thông thường | ExecutionException | Kiểm tra getCause; quyết định recovery hoặc báo thất bại |
| Future đã canceled | CancellationException | Xử lý trạng thái hủy, không coi là result |
| Thread caller bị interrupt khi đang chờ | InterruptedException | Lan truyền/khôi phục cờ và kết thúc theo contract |
| get(timeout) hết thời gian | TimeoutException | Dừng chờ, tùy owner quyết định cancel hoặc trả deadline error |
| Future chưa hoàn tất nhưng caller ngừng chờ | Task có thể vẫn chạy | Không suy ra side effects đã dừng |

**Hai hướng interruption phải tách biệt:**

1. **Caller bị interrupt trong future.get()** → chính method get có thể ném InterruptedException trực tiếp.
2. **Callable của worker tự ném InterruptedException** → nếu task được lưu như failure và chưa canceled, get thường ném ExecutionException với **cause là InterruptedException**.

Chỉ nhìn thấy chữ InterruptedException trong log mà không xác định object nào ném nó có thể dẫn đến chính sách sai. Lỗi của worker không phải lúc nào cũng là yêu cầu dừng thread đang chờ kết quả.

Nếu cần deadline, hãy cân nhắc **get(timeout, unit)** và budget tổng thể. Một loạt retry có timeout riêng không đảm bảo deadline tổng thể nếu tổng thời gian vượt quá budget của request.

## 15. Bảng chọn: CompletableFuture và CompletionStage

| Cách dùng | Lỗi được biểu diễn | Policy thường gặp |
| --- | --- | --- |
| **completeExceptionally(failure)** | Future hoàn tất bất thường với Throwable | Tầng tạo Future báo lỗi chủ động |
| **CompletableFuture.get()** | ExecutionException khi exceptional completion thông thường | Caller checked exception; lấy cause |
| **CompletableFuture.join()** | CompletionException khi exceptional completion thông thường | Caller unchecked exception; lấy cause |
| **cancel(...)** trên Future gốc | CancellationException khi quan sát canceled Future | Không khẳng định computation chắc chắn bị ngắt |
| **exceptionally(fn)** | Có thể chuyển failure thành fallback stage | Chỉ recovery loại lỗi được phép |
| **handle((value,error) -> ...)** | Chạy khi success hoặc failure | Phân biệt value/error, tránh vô tình nuốt cancellation |
| **whenComplete((value,error) -> ...)** | Callback quan sát, thường không recovery giá trị | Không để logging ném exception mới khi không cần |
| **orTimeout(...)** | Có thể hoàn tất chính Future bất thường với TimeoutException | Phân biệt với get(timeout) chỉ hết lượt chờ |
| **completeOnTimeout(value,...)** | Có thể hoàn tất chính Future bình thường bằng fallback | Không khẳng định supplier bên dưới đã dừng |
| **allOf(...)** | Future tổng hợp hoàn tất khi các Future tương ứng hoàn tất | Khi cần kết quả từng phần, quan sát từng Future |

**Quan trọng:** **CompletableFuture.cancel(true)** không có cùng bảo đảm interrupt computation như cơ chế cancellation của FutureTask; theo hợp đồng CompletableFuture, tham số mayInterruptIfRunning không được dùng để điều khiển xử lý. Muốn dừng tác vụ thật sự, cần thiết kế cơ chế cooperative cancellation riêng hoặc quản lý Future/task thực thi bên dưới.

Với **get()**, checked exception của caller có thể là InterruptedException hoặc ExecutionException; với **join()**, không có throws checked InterruptedException trong chữ ký. Không chọn join chỉ để tránh phải nghĩ về cancellation hoặc failure.

### Quan sát lỗi ở stage đúng vị trí

Một dependent stage có thể nhận exceptional completion do upstream hủy và bọc CancellationException trong CompletionException. Vì vậy, **catch(CancellationException)** tại Future gốc và quan sát một downstream stage là hai ngữ cảnh khác nhau. Khi debug, xem **đúng Future** và quan hệ cause trước khi chọn branch.

## 16. Timeout, interruption và cancellation không được đánh đồng

Ba khái niệm thường xuất hiện cùng nhau nhưng khác semantics:

**Timeout:** Một lượt chờ hoặc operation vượt thời gian đã định. Với **Future.get(timeout)**, caller ngừng chờ nhưng Future chưa chắc completed hoặc canceled. Nếu áp dụng **CompletableFuture.orTimeout**, Future có thể được hoàn tất bất thường với TimeoutException; đây là một trạng thái completion khác.

**Interruption:** Một thread đã nhận yêu cầu ngắt. API blocking interruptible có thể ném InterruptedException và xóa flag theo hợp đồng. Caller/callback phải quyết định lan truyền hay khôi phục cờ.

**Cancellation:** Một Future hoặc tác vụ bị yêu cầu hủy. Future có thể chuyển trạng thái canceled trước khi worker thực sự dừng hoặc trước khi các side effects kết thúc. **cancel(true)** chỉ có thể yêu cầu interrupt trong những implementation thích hợp; nó không phải lệnh rollback.

Bảng quyết định:

| Quan sát | Không được suy ra | Hướng cần làm rõ |
| --- | --- | --- |
| get(timeout) ném TimeoutException | Task đã ngừng | Deadline, owner của Future, có cancel được không |
| Thread đang chờ ném InterruptedException | Future đã canceled | Caller có quyền hủy Future hay không |
| Future.isCancelled() true | Worker chắc chắn đã dừng | Cơ chế task có hợp tác với cancellation không |
| CompletableFuture orTimeout hoàn tất bất thường | Supplier bị interrupt | Cách chấm dứt công việc bên dưới |
| Future.get ném ExecutionException | Caller đang bị interrupt | Cause thực tế thuộc worker nào |

Không dùng “timeout” làm một lý do mặc định để retry mọi thao tác có side effect. Nếu server đã xử lý request nhưng caller chưa nhận response, retry có thể tạo giao dịch trùng. Dùng idempotency key và chính sách at-least-once/at-most-once phù hợp.

## 17. Chọn nơi recovery: fallback không phải luôn là thành công

Một fallback hợp lệ phải trả lời được: **khi dùng kết quả thay thế, những invariant và cam kết với caller có còn đúng không?**

Ví dụ hợp lý:
- Dịch vụ đọc dữ liệu không quan trọng có thể trả bản cache còn trong thời hạn chấp nhận.
- Một tính năng gợi ý optional có thể bỏ phần gợi ý nhưng giữ chức năng chính.
- Một job được phép retry sau lỗi mạng tạm thời, khi thao tác idempotent và chưa hết deadline.

Ví dụ nguy hiểm:
- Trả danh sách rỗng khi database timeout, khiến caller tưởng người dùng không có dữ liệu.
- Trả thành công sau lỗi commit, khi trạng thái transaction chưa chắc.
- Bỏ qua InterruptedException và xử lý tiếp dù supervisor yêu cầu dừng.
- Catch Throwable để chuyển mọi lỗi, kể cả OutOfMemoryError, thành fallback.
- Chuyển lỗi phân quyền thành “không tìm thấy” mà không có policy bảo mật rõ.

Một fallback nên có **semantic rõ**: dữ liệu stale được phép hay không, có đánh dấu degraded mode không, metric nào ghi nhận, và lỗi nào không được recovery.

Với CompletableFuture.exceptionally, callback nhận Throwable; nó có thể là wrapper hoặc cause tùy stage. Không chỉ kiểm tra **failure.getMessage()**. Phân loại bằng class/cause phù hợp, bảo toàn lỗi không recovery và đừng biến cancellation thành fallback nếu ứng dụng không cho phép.

## 18. Quy tắc retry theo loại lỗi và ownership

| Điều kiện | Retry? | Lý do |
| --- | --- | --- |
| Input sai ổn định | Không | Retry cùng input không tự sửa |
| Vi phạm invariant nội bộ | Không theo mặc định | Cần sửa logic hoặc state |
| Kết nối tạm thời lỗi | Có thể | Chỉ nếu retry an toàn và budget còn |
| Timeout sau request có side effect | Rất thận trọng | Kết quả từ xa có thể đã được commit |
| Deadlock/optimistic concurrency conflict | Theo contract | Có thể retry transaction từ đầu với giới hạn |
| InterruptedException từ request bị hủy | Thường dừng | Không phớt lờ yêu cầu ngắt |
| CancellationException | Thường không tự retry | Cần biết ai yêu cầu hủy |
| SQLException | Tùy SQLState/provider và transaction | Không phải mọi SQLException là transient |
| Error/JVM failure | Không retry kiểu nghiệp vụ | Có thể ảnh hưởng an toàn runtime |

Retry cần được **sở hữu ở một boundary rõ ràng**; tránh repository retry ba lần, service retry ba lần rồi HTTP gateway retry ba lần khiến tổng số thao tác tăng ngoài ý muốn.

Áp dụng hạn mức số lần, tổng deadline, backoff có jitter và idempotency khi cần. Khi retry hết, báo lại exception cuối và ngữ cảnh của các lần thử liên quan theo chính sách chẩn đoán; không chỉ “return null” hoặc bỏ cause.

Nếu một thao tác có transaction, có thể phải **bắt đầu lại một unit of work mới** thay vì tiếp tục dùng transaction/connection đã thất bại. Quyết định phụ thuộc hợp đồng API và trạng thái resource.

## 19. Bảng chọn: HTTP/controller hoặc giao diện công khai

| Trạng thái/điều kiện | Response minh họa | Không nên làm |
| --- | --- | --- |
| Input sai cú pháp hoặc vi phạm validation | 400-series theo contract | Leak stack trace/SQL/path nội bộ |
| Không được phép theo quyền truy cập | 401/403 tùy nghĩa xác thực/phân quyền | Map tùy tiện mọi lỗi thành 404 |
| Resource không tồn tại | 404 nếu semantics endpoint phù hợp | Dùng 404 cho lỗi lưu trữ không xác định |
| Conflict trạng thái | 409 nếu contract quy định | Tự retry và giấu conflict không có policy |
| Dependency tạm thời không sẵn sàng | 503 hoặc mã lỗi được API định nghĩa | Mặc định coi mọi IOException là transient |
| Hệ thống xử lý lỗi ngoài dự kiến | 500-series, correlation ID | Trả HTTP 200 với payload giả thành công |
| Caller hủy/timeout | Theo contract gateway/server | Báo chắc chắn task đã rollback |
| Fallback được cho phép | Thành công có đánh dấu degraded nếu contract cần | Trả dữ liệu thiếu mà caller không được biết |

Bảng này nhằm minh họa nguyên tắc **dịch lỗi tại ranh giới giao tiếp**, không phải đặc tả REST bắt buộc. Một ứng dụng có thể chọn error code riêng, gRPC status hoặc Result object thay vì HTTP. Ở mọi lựa chọn, đừng để consumer phải đoán từ message tiếng Anh của một exception Java nội bộ.

Nên log **Throwable đầy đủ ở bên trong** với context không nhạy cảm; trả cho client **error code ổn định, thông tin phù hợp và request/correlation ID**. Không in exception stack trace, credential hoặc raw SQL ra response công khai.

## 20. Resource boundary: close đúng cách nhưng chưa phải rollback

Khi method **sở hữu AutoCloseable**, ưu tiên:

~~~java
// Mã minh họa theo ngữ cảnh; resource implements AutoCloseable.
try (Resource resource = openResource()) {
    process(resource);
}
~~~

Nếu process ném A và close ném B, Java giữ **A làm primary** và B thành **suppressed**, khi suppression được bật. Với nhiều resource, close theo thứ tự ngược khai báo và cố gắng dọn các resource đã mở thành công ngay cả khi mở resource tiếp theo thất bại.

Ngược lại:

~~~java
// Phản mẫu.
Resource resource = openResource();
try {
    process(resource);
} finally {
    resource.close();  // Có thể che lỗi process nếu close cũng ném.
}
~~~

Một lỗi cleanup có thể thay thế lỗi gốc. TWR giúp giữ thông tin chẩn đoán đúng hơn. Trong ví dụ runnable, work failed vẫn là primary, close failed là suppressed.

**Trường hợp không dùng TWR trực tiếp:** Resource caller cho mượn, resource dùng lâu hơn method, framework sở hữu vòng đời, một callback async còn cần sử dụng resource, hoặc API chỉ cung cấp unlock/release với semantics riêng. TWR đúng cú pháp nhưng sai ownership vẫn là bug.

**Transaction:** Đóng JDBC Connection không tự cam kết transaction rollback thành công trong mọi provider/pool. Cần chính sách **commit, rollback hoặc compensation** do transaction owner quản lý. Việc addSuppressed lỗi rollback bảo toàn thông tin lỗi; nó không chứng minh rollback đã hoàn tất.

## 21. Logging, metrics và observability theo ranh giới

Nên có một điểm chịu trách nhiệm **ghi nhận kết quả cuối** của request/job/task. Các tầng thấp có thể thêm context nếu thực sự hữu ích, nhưng không nhất thiết log cùng Throwable ở mỗi catch rồi throw lại.

Khi có wrapper:

~~~java
// Mã minh họa.
throw new IllegalStateException("Operation failed", original);
~~~

Đưa original vào cause giữ được nguồn lỗi. Ở boundary ghi log, logger nên nhận **Throwable object**, không chỉ string message. Nếu log chỉ ghi **failure.getMessage()**, thông tin **Caused by**, **Suppressed** và frame nguồn có thể biến mất.

Đối với công việc async, quan sát **exceptional completion** là bắt buộc nếu hệ thống cần biết task có thất bại hay không. Một Future không được await hoặc một CompletableFuture không có handler/monitor có thể hoàn tất bất thường mà boundary bên ngoài không tự phát hiện theo cách bạn tưởng.

Các trường nên có trong structured log khi thích hợp: operation, component, stage, type và cause của Throwable, request/job ID, retry count, deadline, trạng thái cancellation, elapsed time và mã lỗi nghiệp vụ. **Không đặt password, access token, dữ liệu cá nhân hoặc raw request nhạy cảm vào message/cause/log.**

Một nguyên tắc thực hành là **thêm ngữ cảnh ở tầng biết ngữ cảnh, quyết định ở tầng có trách nhiệm, log ở tầng thực sự quan sát kết quả cuối**.

## 22. Kiểm thử bảng quyết định bằng tình huống cụ thể

Một bộ test mạnh nên kiểm tra cả exception type và hệ quả của boundary. Ma trận tham khảo:

| Tình huống cần thử | Assertion quan trọng |
| --- | --- |
| Input null/blank | Exception input đúng loại hoặc response validation đúng contract |
| Repository ném IOException | Service không nuốt; API mapping đúng policy |
| Worker Callable ném IOException | Future.get ném ExecutionException, cause là IOException |
| Caller bị interrupt trong get | InterruptedException theo hợp đồng caller; chính sách cờ interrupt đúng |
| Runnable await bị interrupt | Runnable không nuốt, khôi phục flag/dừng theo contract |
| CompletableFuture completeExceptionally | get/join có wrapper thích hợp và giữ original cause |
| Future canceled | CancellationException/ trạng thái isCancelled đúng |
| get(timeout) trên pending Future | TimeoutException, Future không tự canceled |
| Body và close cùng ném | Body primary, close suppressed |
| Mở resource thứ hai thất bại | Resource đã mở trước vẫn được dọn |
| Retry lỗi tạm thời | Số lần giới hạn, deadline, không duplicate side effect |
| Fallback hợp lệ | Value/mode phù hợp, upstream failure vẫn được ghi nhận nếu cần |
| Transaction rollback thất bại | Lỗi chính và lỗi rollback được giữ; trạng thái không bị báo thành công giả |
| Public boundary | Error code/payload không lộ thông tin nhạy cảm |
| Async task không await trực tiếp | Có cơ chế quan sát thất bại theo contract |

Đừng viết một test chỉ **assertThrows(Exception.class)** rồi kết luận đã kiểm tra đủ mọi loại lỗi. **assertThrows** trong JUnit Jupiter chấp nhận subtype; **assertThrowsExactly** yêu cầu đúng runtime class khi phiên bản JUnit hỗ trợ. Khi API cam kết một họ exception, chấp nhận subtype có thể đúng; khi contract đòi exact class, assertion quá rộng có thể tạo false positive.

Với lỗi bất đồng bộ, ưu tiên điều khiển bằng CountDownLatch, CompletableFuture đã hoàn tất hoặc executor test phù hợp. Dùng Thread.sleep với thời gian đoán trước là nguồn test không ổn định.

## 23. Các phản mẫu phổ biến cần tránh

**Catch(Exception) rồi return null.** Null có thể được hiểu là “không có dữ liệu” thay vì “I/O thất bại”, làm tầng trên đi sai nhánh.

**Catch(Throwable) rồi phục hồi.** Error nghiêm trọng bị biến thành một fallback thông thường. Cleanup có thể cần chạy trong finally, nhưng không nên mặc định nuốt Error.

**Log rồi throw ở mọi tầng.** Cùng một failure tạo nhiều bản log, khó đếm và khó xác định boundary chịu trách nhiệm.

**Wrap không cause.** Chỉ giữ message làm mất stack trace và original Throwable.

**Nuốt InterruptedException.** Worker có thể tiếp tục chờ hoặc xử lý dù supervisor yêu cầu dừng.

**Re-interrupt rồi tiếp tục blocking vô thời hạn.** Cờ interrupt được đặt lại nhưng policy dừng không rõ, có thể gây vòng lỗi hoặc chặn.

**Coi timeout là cancellation.** Một lần get(timeout) quá hạn không tự dừng Future hoặc rollback side effect.

**Cho rằng cancel(true) của mọi Future bảo đảm task dừng.** Cancellation cần hợp tác và phụ thuộc implementation; với CompletableFuture, mayInterruptIfRunning không điều khiển computation.

**Bắt mỗi CompletionException để xử lý join.** Future canceled có thể ném CancellationException trực tiếp; dependent stage có thể wrap cancellation khác.

**Dựa vào uncaught handler để thấy lỗi ExecutorService.submit.** Lỗi task có thể đã được executor ghi vào Future.

**Dùng retry ở nhiều tầng.** Tổng số lần thực thi và side effects có thể tăng không kiểm soát.

**Cho rằng close tương đương rollback.** Cleanup resource và đảm bảo transaction/data consistency là hai hợp đồng khác nhau.

**Thay mọi lỗi thành HTTP 500/503.** Mất phân biệt input, conflict, permission và dependency; contract công khai trở nên kém hữu dụng.

## 24. Mẫu điều phối lỗi ở tầng phù hợp

Một thiết kế dễ kiểm soát chia trách nhiệm:

~~~text
Request boundary
    xác thực và chuẩn hóa input
    gọi application service
    map domain/infrastructure failure → error response
    log kết quả cuối một lần
          |
          v
Application service
    kiểm tra invariant
    quản lý transaction/unit of work nếu là owner
    fallback/retry có giới hạn nếu được phép
    giữ/đổi exception theo public contract
          |
          v
Repository / adapter
    gọi I/O, network, database
    đóng resource do adapter sở hữu
    không tự quyết policy retry của toàn request nếu không được giao
          |
          v
Executor / async worker
    làm việc theo task contract
    truyền lỗi qua Future/CompletionStage
    hợp tác interruption/cancellation
    có boundary quan sát completion
~~~

Đây là **một cách chia trách nhiệm điển hình**, không phải thiết kế bắt buộc cho ứng dụng đơn luồng hay thư viện nhỏ. Điều cần giữ là mỗi side effect/exception có một chủ thể sở hữu quyết định cuối, và thông tin lỗi không bị mất giữa các tầng.

### Khi nào nên dùng kiểu Result thay vì Throwable?

Nếu thất bại là trạng thái nghiệp vụ thường xuyên và caller cần xử lý nhánh đó như dữ liệu bình thường (ví dụ tìm kiếm không có kết quả), kiểu Result/Optional có thể phù hợp hơn exception. Nhưng **Result.failure** vẫn cần error code đủ rõ và không được biến một lỗi hệ thống bất thường thành kết quả thành công.

### Khi nào nên tự tạo checked exception?

Nếu một thư viện có một loại thất bại bắt buộc caller quyết định và muốn contract tường minh ở compile time, checked exception riêng có thể phù hợp. Nếu method override, lambda hoặc framework không cho phép checked throws, cần cân nhắc unchecked wrapper, callback failure channel hoặc Future. Không ép mọi interface thành **throws Exception** chung vì khó phân biệt lỗi.

## 25. Checklist một phút trước khi chọn catch/throw

1. **Đây là loại lỗi gì?** Input, state, I/O, dependency, task, timeout, interrupt, cancel hay Error?
2. **Ai sở hữu thao tác?** Helper, adapter, service, controller, executor, worker hay caller?
3. **Tầng hiện tại có đủ thông tin để phục hồi thật không?** Nếu không, truyền lên.
4. **Hợp đồng có cho phép checked exception?** Method thường, Runnable, Callable, callback hoặc CompletionStage?
5. **Có cần đổi abstraction?** Nếu wrap, đã giữ cause chưa?
6. **Đang đọc lỗi ở đúng thread/Future/stage?** Worker failure khác caller interrupted.
7. **Timeout có chỉ chấm dứt lượt chờ hay hoàn tất Future bất thường?**
8. **Cancellation có thật sự ngắt task không?** Đã phân biệt Future state với worker execution?
9. **Có side effect cần rollback/compensation không?** Close không tự làm việc đó.
10. **Có AutoCloseable do scope sở hữu không?** Ưu tiên TWR, xét suppressed và thứ tự close.
11. **Retry có idempotent, bounded và nằm trong deadline không?**
12. **Fallback có thỏa hợp đồng hay che dữ liệu sai?**
13. **Đã giữ cause/suppressed và log ở boundary phù hợp?**
14. **Test có phân biệt đúng exception type, cause, trạng thái và đường thành công không?**
15. **Boundary công khai có tránh lộ thông tin nhạy cảm không?**

**Kết luận:** Chọn cách xử lý lỗi theo **ranh giới sở hữu và hợp đồng**, không theo thói quen viết catch. Tầng thấp nên giữ đúng thông tin lỗi; tầng trung gian chỉ wrap hoặc recovery khi thật sự có trách nhiệm; caller của Future phải phân biệt lỗi worker với interruption của chính mình; callback không cho checked exceptions cần chính sách dừng/chuyển đổi rõ ràng; resource/transaction owner phải cleanup và giữ trạng thái nhất quán. Một bảng quyết định hữu ích nhất khi người đọc dùng nó để xác định **ai quyết định**, **lỗi được truyền theo kênh nào** và **những gì phải được bảo toàn sau thất bại**.
