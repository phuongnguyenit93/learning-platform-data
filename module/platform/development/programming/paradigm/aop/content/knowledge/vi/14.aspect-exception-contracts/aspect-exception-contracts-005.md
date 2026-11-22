# Dọn dẹp tài nguyên khi advice hoặc mã gốc thất bại trong AOP

## 1. Tại sao cleanup là một phần của hợp đồng?

Trong **Aspect-Oriented Programming (AOP)**, một lời gọi nghiệp vụ có thể đi qua nhiều **advice**: before, after returning, after throwing, after/finally và around. Advice có thể mở kết nối, file, trace span, lock, resource lease, buffer, transaction context hoặc một scope dữ liệu theo thread. Mã nghiệp vụ gốc cũng có thể mở tài nguyên riêng.

Nếu lời gọi thất bại ở bất kỳ mắt xích nào, control flow không tiếp tục theo đường bình thường. Tài nguyên đã mở phải được đóng theo **ownership/lifecycle contract** ngay cả khi target throw, advice throw, hoặc chính bước cleanup gặp lỗi.

~~~text
Caller
  |
  v
Around A: acquire resource A
  |
  v
Around B: acquire resource B
  |
  v
Before advice -> Target method -> After advice
                     |
                 return / throw
                     |
                     v
                 B cleanup
                     |
                     v
                 A cleanup
                     |
                     v
               Caller result/error
~~~

Năm bất biến cần thiết:

1. **Không leak:** tài nguyên đã acquire phải được release hoặc chuyển giao ownership rõ ràng.
2. **Không double-release:** không đóng hai lần nếu resource không hỗ trợ.
3. **Không close khi chưa acquire:** lỗi trong acquisition cần chỉ dọn những thành phần đã thành công.
4. **Không làm mất primary exception:** lỗi cleanup thứ cấp cần có chỗ ghi nhận, ví dụ suppressed exceptions.
5. **Không thay đổi ngữ nghĩa nghiệp vụ vô tình:** logging, metrics hoặc trace cleanup không được tùy tiện đổi return/exception.

Mục tiêu không chỉ là viết finally, mà là **định nghĩa chính xác ai sở hữu resource, resource sống đến khi nào, exception nào caller nhìn thấy và các lỗi cleanup được bảo tồn như thế nào**.

Bài tập trung AOP cơ bản và nâng cao nói chung. Ví dụ Java 17 dùng các hàm bảo vệ mô phỏng các advice scopes, không tự triển khai compiler hay bytecode weaving. Các quy tắc cụ thể của một ngôn ngữ AOP và thứ tự advice cần được kiểm tra theo công cụ thực tế.

## 2. Đâu là vị trí có thể phát sinh lỗi?

| Vị trí | Dạng lỗi | Câu hỏi cleanup |
|---|---|---|
| Before advice | Authorization/validation throw | Tài nguyên trước đó có được release không? |
| Acquire resource | Mở file/kết nối thất bại | Những resources đã mở trước đó được dọn chưa? |
| Around trước proceed | Setup trace/context fail | Target chưa chạy, outer resources có owner không? |
| Target/proceed | Business exception | Resources trong mọi nested scopes có release không? |
| Around sau proceed | Convert result / telemetry throw | Target đã return nhưng caller thấy exception? |
| After returning | Reporter hoặc metric fail | Có đổi normal return thành error? |
| After throwing | Logger error | Có che exception gốc? |
| After/finally | Close/unlock throw | Giữ lỗi chính hay để lỗi cleanup thay thế? |
| Transaction completion | Commit/rollback fail | Có xác định được durable outcome không? |
| Async completion | Task fail sau khi method return | Có đóng resource quá sớm không? |
| Retry | Nhiều lần proceed | Resource cần sống per attempt hay per request? |

Một operation có thể có **hơn một lỗi**. Ví dụ target throw X, inner resource close throw Y, outer resource close throw Z. Không thể chỉ chọn ngẫu nhiên exception cuối cùng; phải xác định **primary/secondary policy**.

## 3. Một lời gọi, nhiều scopes và cleanup LIFO

Với around composition:

~~~text
A(B(Target))
~~~

A acquire resource A trước; B acquire resource B sau. Khi unwind, B cleanup trước rồi A cleanup.

~~~text
open A
  open B
    target
  close B
close A
~~~

Đây là mô hình **last-in, first-out (LIFO)**, tương thích nested try/finally hoặc try-with-resources.

**Đặt close sau proceed không đủ:**

~~~text
resource = acquire()
result = proceed()    // có thể throw
resource.close()      // sẽ bị bỏ qua khi throw
return result
~~~

Mẫu an toàn hơn:

~~~text
resource = acquire()
try:
    return proceed()
finally:
    resource.close()
~~~

Finally có cơ hội chạy khi return/throw theo control-flow thông thường, nhưng **close tự nó vẫn có thể throw**, hoặc process có thể crash trước khi cleanup. Không được biến “finally đã bắt đầu” thành “resource release đã thành công”.

### 3.1. Trường hợp outer/inner advice cùng throw

Giả sử B.close throw trong khi Target đã throw. Outer A vẫn phải chạy cleanup nếu nó có finally thích hợp. Nếu A.close cũng throw, phải giữ đủ thông tin của tất cả lỗi cần chẩn đoán. Ngôn ngữ Java cho phép lưu các lỗi thứ cấp qua **suppressed exceptions**, nhưng một try/finally viết tay không tự bảo đảm điều đó.

### 3.2. Không có thứ tự áp dụng AOP phổ quát

Thứ tự trước/sau/around giữa nhiều aspect phụ thuộc **precedence**, loại join point và engine. Không suy ra một outer advice cố định chỉ từ tên class, thứ tự file hay annotation. Bài dùng mô hình A(B(Target)) để làm rõ semantics, không khẳng định đây là thứ tự mặc định của mọi bộ dệt.

## 4. Before advice có thể làm mọi inner advice biến mất

Before advice có thể ném exception **trước khi proceed hoặc target bắt đầu**. Khi ấy các advice nằm sâu bên trong có thể chưa từng được kích hoạt.

~~~text
Outer around: acquire A
  Before security: throw AccessDenied
Outer around: finally close A
Caller receives AccessDenied
~~~

Nếu trước khi throw, before advice tự acquire resource và không có local finally thì tài nguyên có thể rò. Không được mặc định after returning/after throwing của một join point sẽ bù lại lỗi phát sinh **trong chính before advice trước khi join point chạy**; semantics thật phụ thuộc cấu trúc.

Thiết kế tốt là bao các thao tác dễ lỗi bằng **một around scope có cleanup rõ**, hoặc bảo vệ từng resource do before advice acquire tại chỗ.

### 4.1. Nếu before advice chưa acquire?

Không close tài nguyên chưa tồn tại. Nếu before validation throw trước khi mở file, close(file) sẽ không có ý nghĩa. Nếu acquire thất bại giữa chừng, code tạo resource phải dọn những phần đã sở hữu trước khi lỗi phát ra.

## 5. After returning, after throwing và after/finally khác nhau

**After returning** thích hợp để ghi nhận một join point được quan sát đã trả bình thường. Nó **không** bảo đảm chạy khi target throw, nên không đủ cho cleanup tài nguyên cần dọn trên mọi đường.

**After throwing** ghi nhận exception thoát khỏi join point; nó **không** dọn trên normal return, vì thế cũng không đủ làm cleanup duy nhất.

**After/finally** thường bao cả hai đường exit theo semantics engine, phù hợp cho thao tác cần chạy dù thành công hay thất bại. Tuy nhiên nếu chính finally advice throw, nó có thể che lỗi cũ nếu không có cơ chế giữ secondary error.

**Around** bao toàn bộ continuation và có thể kiểm soát vòng đời acquire/use/release. Nó còn có thể short-circuit hoặc proceed nhiều lần (tùy engine); do đó cần test resource lifetime cho từng kiểu flow.

### 5.1. Không đồng nhất after returning với operation success

Business method có thể return OK nhưng outer transaction còn chưa commit, hoặc resource close về sau throw. Một after returning gắn tại method body không chứng minh **toàn bộ transaction/operation hoàn tất**.

Ghi log rõ mốc **business-returned**, **resource-closed** hay **transaction-committed**, thay vì dùng một nhãn SUCCESS mơ hồ.

## 6. Java try/finally: bảo đảm gọi cleanup theo control-flow

~~~java
Lease lease = acquire();
try {
    return execute();
} finally {
    lease.close();
}
~~~

Đây là snippet minh họa, không độc lập vì chưa định nghĩa Lease/acquire/execute. Khi execute return hoặc throw thông thường, finally chạy trước khi control flow rời operation.

**Nhưng nếu finally throw, nó có thể thay thế exception gốc**:

~~~java
try {
    throw new IllegalStateException("core-failed");
} finally {
    throw new IllegalStateException("cleanup-failed");
}
~~~

Caller có thể chỉ thấy cleanup-failed. Lỗi core-failed không tự trở thành suppressed trong dạng finally này. Đây là lý do nên xem xét try-with-resources hoặc một cơ chế ghi nhận primary/secondary được viết/test đúng.

Không cam kết finally luôn chạy dưới mọi tình huống vật lý. JVM/process crash, termination đột ngột, lỗi hệ thống hoặc mất điện có thể cắt ngang cleanup.

## 7. Java try-with-resources và AutoCloseable

Try-with-resources gọi close() trên tài nguyên **AutoCloseable** khi kết thúc block. Những resources đã khai báo được đóng theo thứ tự ngược lúc khởi tạo thành công.

~~~java
try (Lease lease = acquire()) {
    return execute();
}
~~~

Nếu body throw X và close throw Y:

- **X là primary exception**.
- **Y được lưu trong X.getSuppressed()**.
- Caller có thể phân tích cả hai mà không mất lỗi gốc.

Nếu body bình thường nhưng close throw Y:

- Toàn operation thoát bằng **Y**, không phải normal return.
- Một đoạn trong body ghi “business returned” có thể đã chạy, nhưng caller không nhận được kết quả bình thường.

Nếu acquire nhiều resources rồi bước khởi tạo resource sau thất bại, các resources đã mở thành công trước đó được đóng theo semantics try-with-resources. Nếu bản thân một constructor acquire tài nguyên nội bộ rồi throw trước khi trả object AutoCloseable, constructor/factory phải dọn phần nó đã sở hữu.

### 7.1. AutoCloseable có luôn idempotent?

Không được giả định. Một resource có thể cho phép close nhiều lần; một resource khác có thể báo lỗi hoặc sinh side effect nếu close lặp. Đọc hợp đồng implementation và tránh double ownership.

## 8. Primary, suppressed và cause: đừng nhầm

**Primary exception:** lỗi chính đi ra khỏi phạm vi.

**Suppressed exception:** lỗi phụ được gắn qua Throwable.addSuppressed/getSuppressed, thường do close thất bại khi body đã throw.

**Cause:** lý do gây ra một exception wrapper, được gắn bằng cause chain, không đồng nghĩa suppressed.

~~~text
IllegalStateException: core-failed
  suppressed:
    IllegalStateException: close-failed
~~~

Một try-with-resources có nhiều AutoCloseable có thể chứa **nhiều suppressed errors**. Không chỉ log primary rồi bỏ suppressed, vì đó có thể là dấu hiệu rò connection hoặc failure trong cleanup.

### 8.1. Những điều không nên giả định

- Primary luôn từ target: before, around, after hoặc close cũng có thể là primary.
- Finally throw tự động bị suppressed: không đúng với plain try/finally.
- Close throw chứng minh resource chưa từng được dọn: chỉ biết close đã báo lỗi, trạng thái cuối phụ thuộc resource.
- Close return bình thường chứng minh đã flush bền vững ra remote system: còn phụ thuộc contract I/O và durability.

## 9. Ví dụ Java 17 chạy được: sáu đường lỗi

Chương trình sau mô phỏng advice-like guard, before, target, after-like observation, Lease.close và outer finally. Dùng JDK 17 thuần; không phải một bytecode weaver hay một bộ công cụ AOP.

Tạo file **AdviceCleanupDemo.java**:

~~~java
public class AdviceCleanupDemo {
    static final class Lease implements AutoCloseable {
        private final String id;
        private final boolean failClose;

        Lease(String id, boolean failClose) {
            this.id = id;
            this.failClose = failClose;
            System.out.println("resource:open " + id);
        }

        @Override
        public void close() {
            System.out.println("resource:close " + id);
            if (failClose) {
                throw new IllegalStateException("close-failed");
            }
        }
    }

    static String operation(String id, boolean failBefore,
                            boolean failCore, boolean failClose,
                            boolean failAfter) {
        System.out.println("guard:enter");
        try {
            System.out.println("advice:before");
            if (failBefore) {
                throw new IllegalArgumentException("before-failed");
            }

            try (Lease lease = new Lease(id, failClose)) {
                System.out.println("core:execute");
                if (failCore) {
                    throw new IllegalStateException("core-failed");
                }
                System.out.println("advice:observed-core-return");
                if (failAfter) {
                    throw new IllegalStateException("after-failed");
                }
                return "OK";
            }
        } finally {
            System.out.println("guard:finally");
        }
    }

    static void scenario(String id, boolean before, boolean core,
                         boolean close, boolean after) {
        System.out.println("=== " + id + " ===");
        try {
            System.out.println("caller:result " +
                operation(id, before, core, close, after));
        } catch (RuntimeException error) {
            System.out.println("caller:error " + error.getMessage());
            for (Throwable suppressed : error.getSuppressed()) {
                System.out.println("caller:suppressed " + suppressed.getMessage());
            }
        }
    }

    public static void main(String[] args) {
        scenario("success", false, false, false, false);
        scenario("before-fails", true, false, false, false);
        scenario("core-fails", false, true, false, false);
        scenario("core-and-close-fail", false, true, true, false);
        scenario("close-fails", false, false, true, false);
        scenario("after-and-close-fail", false, false, true, true);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 AdviceCleanupDemo.java
java AdviceCleanupDemo
~~~

**Stdout chính xác đã được kiểm chứng:**

~~~text
=== success ===
guard:enter
advice:before
resource:open success
core:execute
advice:observed-core-return
resource:close success
guard:finally
caller:result OK
=== before-fails ===
guard:enter
advice:before
guard:finally
caller:error before-failed
=== core-fails ===
guard:enter
advice:before
resource:open core-fails
core:execute
resource:close core-fails
guard:finally
caller:error core-failed
=== core-and-close-fail ===
guard:enter
advice:before
resource:open core-and-close-fail
core:execute
resource:close core-and-close-fail
guard:finally
caller:error core-failed
caller:suppressed close-failed
=== close-fails ===
guard:enter
advice:before
resource:open close-fails
core:execute
advice:observed-core-return
resource:close close-fails
guard:finally
caller:error close-failed
=== after-and-close-fail ===
guard:enter
advice:before
resource:open after-and-close-fail
core:execute
advice:observed-core-return
resource:close after-and-close-fail
guard:finally
caller:error after-failed
caller:suppressed close-failed
~~~

### 9.1. Success

Resource được mở, core chạy, đoạn quan sát core return chạy, close thực thi rồi outer finally chạy. Caller nhận OK.

### 9.2. Before fail

Before ném lỗi **trước khi Lease tồn tại**, vì vậy không có open/close. Outer finally vẫn chạy. Nếu before tự acquire một resource phần nào rồi fail, nó vẫn phải cleanup phần đó, nhưng demo không có phần acquire trước lỗi này.

### 9.3. Core fail

Core throw **core-failed**, try-with-resources vẫn close và finally vẫn chạy. Đoạn quan sát core return không chạy.

### 9.4. Core fail và close fail

Core error là primary. Close error được giữ trong **getSuppressed()**, nên caller in cả core-failed và close-failed.

### 9.5. Core thành công nhưng close fail

Đoạn after-like nhận thấy core return, nhưng close throw và caller không nhận OK. Điều này cho thấy **body returned không đồng nghĩa overall operation returned**.

### 9.6. After-like và close cùng fail

After-like ném **after-failed** trước lúc rời try-with-resources. Close throw tiếp, nhưng after-failed là primary; close-failed suppressed.

**Lưu ý:** after-like là code Java đặt trong try block để minh họa, không phải một advice implementation có semantics chung cho mọi engine AOP.

## 10. Ownership: phân biệt own và borrow

**Owner của resource** là scope/component có trách nhiệm cuối cùng để release. Một resource nên có ownership rõ, thay vì mọi advice có reference đều nghĩ có quyền close.

| Resource | Owner ví dụ | Cleanup |
|---|---|---|
| File mở trong advice | Advice đó | try-with-resources |
| Temporary buffer | Scope tạo nó | release/recycle nếu contract yêu cầu |
| Trace span mở tại boundary | Scope tạo span | mark error/end |
| Lock do advice acquire | Advice giữ lock | unlock đúng thread/scope |
| Transaction context | Boundary transaction | commit/rollback/restore/release |
| Connection do caller cấp cho target | Caller hoặc owner đã thỏa thuận | Advice chỉ borrow |
| Stream được trả cho caller | Caller sau khi ownership transfer | Caller close theo API |

**Mượn resource không đồng nghĩa sở hữu nó.** Nếu advice chỉ nhận connection từ transaction đang hoạt động, đóng connection trước khi transaction owner kết thúc có thể phá operation.

### 10.1. Khi resource được trả ra ngoài

Nếu target trả một InputStream để caller đọc tiếp, advice không được mở stream rồi **close ngay trong finally trước khi caller dùng**, trừ khi API cố ý trả dữ liệu đã đọc vào memory hoặc một abstraction khác. Vòng đời stream cần kéo dài qua caller usage hoặc ownership phải được chuyển cho caller.

### 10.2. Ownership transfer và close-once

Chuyển ownership cần một hợp đồng chính xác: khi nào transfer thành công, nếu transfer fail ai close, có còn holder cũ sử dụng hay không. Một wrapper close-once không tự sửa lỗi race hoặc transfer không rõ.

## 11. Resource acquisition có thể thất bại từng phần

Giả sử một aspect:

1. Mở connection A.
2. Mở file B.
3. Đăng ký listener C.

Nếu bước 2 throw, A cần release. Nếu bước 3 throw, cả A/B cần cleanup.

~~~text
acquire A
try:
    acquire B
    try:
        acquire C
        try:
            proceed
        finally:
            release C
    finally:
        release B
finally:
    release A
~~~

Đây là giả mã minh họa LIFO, không phải Java chạy độc lập.

Nested try-with-resources có thể thực hiện việc đóng những AutoCloseable đã được khởi tạo thành công khi resource khai báo sau thất bại. Nhưng nếu constructor/factory cấp phát một số native handles rồi throw trước khi trả object, phải tự dọn những handles đó bên trong acquisition implementation.

## 12. Khi resource close cũng thất bại

Một lỗi cleanup có hai chiều:

- **Độ tin cậy:** tài nguyên có thể đã/ chưa được release, cần cảnh báo/đo trạng thái.
- **Ngoại lệ:** caller có thể cần xem failure theo error contract.

### 12.1. Target đã throw

Ưu tiên giữ target exception khi nó là lỗi nghiệp vụ chính, đính kèm close failure thành secondary/suppressed. Try-with-resources cung cấp cấu trúc phù hợp cho AutoCloseable.

### 12.2. Target bình thường

Nếu close là điều kiện để operation hoàn tất, close throw có thể là primary và caller không nhận normal result. Ví dụ flush buffer hoặc close stream có thể phát hiện lỗi I/O sau khi body đã ghi dữ liệu.

### 12.3. Logger fail trong cleanup

Nếu mục tiêu của logger chỉ là observability best-effort, lỗi exporter thường không nên vô tình che business error. Với audit bắt buộc, failure có thể yêu cầu fail-closed, nhưng phải là chính sách rõ, không do IOException tình cờ từ reporter.

### 12.4. Cleanup failure không luôn retry được

Nếu close có thể commit/flush tác vụ đã xảy ra, retry toàn bộ business operation khi close throw có thể tạo duplicate. Hãy xác minh resource state, idempotency và error recovery semantics.

## 13. Lock và Semaphore: release chỉ khi đã acquire

Với lock, resource contract khác file:

~~~java
lock.lock();
try {
    return proceed();
} finally {
    lock.unlock();
}
~~~

Đây là snippet minh họa, chưa có lock/proceed. Cách đặt try ngay sau lock.lock phù hợp nếu lock() chỉ return sau khi acquire thành công theo contract. Với tryLock trả boolean hoặc lockInterruptibly ném InterruptedException, cần kiểm tra có thực sự acquire trước khi unlock.

Với Semaphore, chỉ **release permit đã acquire**. Nếu acquire throw/interrupted trước khi lấy permit mà finally vẫn release, số permit có thể sai.

### 13.1. Thread affinity

Một số lock chỉ được unlock bởi thread owner. Nếu advice mở resource ở thread A nhưng cleanup callback chạy ở thread B, có thể vi phạm contract. **Không di chuyển cleanup sang thread khác** chỉ vì dùng future callback mà chưa xác minh resource hỗ trợ.

## 14. ThreadLocal context: restore thay vì clear tùy tiện

Một nested advice có thể ghi trace/security context vào ThreadLocal:

~~~text
Trước inner advice: Context = A
Trong inner advice: Context = B
Sau inner advice: Context phải trở về A
~~~

Nếu inner finally chỉ **remove** mà không biết A tồn tại, nó phá outer context. Với scope lồng nhau, hãy lưu previous value và restore trong finally.

Với một request scope do chính bạn tạo mới, remove có thể đúng nếu không có prior value. Hãy tài liệu hóa rõ khác biệt.

Không để context từ request cũ rò sang request mới trên worker thread tái sử dụng. Các thread-local state có thể ảnh hưởng tracing, security, locale hoặc transactional routing; lỗi cleanup context là lỗi correctness, không chỉ sai log.

## 15. Retry làm thay đổi resource lifetime

Xét:

~~~text
Retry(Resource(Target))
~~~

Nếu Retry gọi proceed ba lần, mỗi attempt có thể vào Resource mới, acquire và close mới. Điều này phù hợp nếu mỗi attempt cần một transaction/connection scope độc lập.

Ngược lại:

~~~text
Resource(Retry(Target))
~~~

Có thể chỉ mở một resource rồi chạy nhiều attempts trong cùng scope. Điều này có thể không phù hợp nếu resource đã ở trạng thái lỗi hoặc transaction bị đánh dấu rollback-only.

### 15.1. Idempotency khi retry

Một attempt có thể tạo side effect rồi throw lúc close/commit. Caller không biết outcome cuối có thành công không. Retry mà không có idempotency key/reconciliation có thể nhân đôi order, payment hoặc message.

### 15.2. Lỗi của các attempts trước

Nếu chỉ ném exception của attempt cuối, lỗi cleanup ở các attempts trước có thể bị mất. Logging/trace có thể giữ attempt ID và secondary diagnostics, hoặc error contract có thể tổng hợp các lỗi; nhưng không được tự tạo cause/suppressed cycle.

## 16. Async và cancellation

Một around advice đơn giản:

~~~text
resource = open()
try:
    return proceed()  // trả CompletableFuture rất nhanh
finally:
    resource.close()
~~~

Nếu future vẫn đang chạy và cần resource ấy, close đã xảy ra **quá sớm**. Cần thiết kế vòng đời resource theo **actual task completion**, không chỉ thời điểm method trả handle.

Nhưng không được tùy tiện chuyển lock/transaction/thread-bound context sang async callback: thread affinity và resource manager constraints có thể khiến việc dọn trên thread khác sai.

### 16.1. Cancellation không đồng nghĩa task đã dừng

Cancel request có thể tới khi task đang thực thi, hoặc khi child operations vẫn giữ resource. Hãy xác định:

- Khi nào task thật ngừng sử dụng resource?
- Ai được quyền cancel và release?
- Release có được gọi đúng một lần qua race giữa complete/error/cancel?
- Cleanup có blocking không?
- Có cần interrupt signal không?
- Context/correlation ID được truyền bằng cách nào?

### 16.2. InterruptedException

Nếu code bị InterruptedException, thường cần rethrow khi API cho phép hoặc restore interrupt flag nếu phải catch và tiếp tục theo policy; không nuốt interruption để che cancellation. Resource cleanup nên chạy trong finally nếu đã acquire.

## 17. Reflection và hợp đồng exception

Proxy/interceptor qua reflection có thể nhận **InvocationTargetException** bọc lỗi target. Nếu handler chuyển thẳng wrapper, caller có thể nhận loại exception khác với hợp đồng method.

Khi cần preserve target error, lấy cause theo contract, đồng thời bảo toàn suppressed exceptions và stack/context cần thiết. Không catch Throwable rồi biến tất cả thành một RuntimeException không có cause.

**Checked exceptions** còn phụ thuộc method signature và invocation API; với JDK dynamic proxy, undeclared checked exception có quy tắc wrapping riêng. Hãy kiểm tra interface contract trước khi translate error.

### 17.1. Error nghiêm trọng

Finally thường được thực hiện trong stack unwinding thông thường kể cả khi một Error được throw, nhưng các tình huống process termination/crash không cho bảo đảm. Không tự swallow mọi Error rồi giả vờ resource cleanup làm chương trình an toàn để tiếp tục.

## 18. Resource management và transaction

Transaction aspect có thể phải phân biệt:

~~~text
begin transaction
try:
    result = proceed()
    commit
    return result
catch:
    rollback nếu policy cho phép
    rethrow
finally:
    restore transaction context
    release connection
~~~

Commit, rollback, context restore và connection release là những bước **khác nhau**.

- Business throw trước commit: rollback có thể được thực hiện theo policy.
- Commit throw: durable outcome có thể không chắc chắn; rollback attempt không chứng minh rollback đã thành công.
- Rollback throw: phải giữ thông tin về business error và rollback error.
- Release connection throw: có thể khiến caller nhìn thấy lỗi sau khi transaction đã xong.
- Logging trong finally throw: có thể che lỗi quan trọng.

Không coi close() của một connection bất kỳ là đồng nghĩa commit/rollback. Khi transaction manager có state machine riêng, phải tuân thủ API và visibility của nó.

### 18.1. Side effects ngoài transaction

Một email gửi đi, HTTP call hoặc event publish trước khi target throw không tự được hoàn tác bằng database rollback. Cleanup resource đúng **không tạo atomicity cho mọi side effect**. Outbox, idempotency hoặc compensation cần được thiết kế theo nghiệp vụ.

## 19. Reentrancy và các advice tự gọi chính nó

Một logging advice có thể gọi logger.write. Nếu pointcut chọn cả logger.write, hệ thống có thể rơi vào recursion:

~~~text
logging advice
  -> logger.write
      -> logging advice
          -> logger.write
              -> ...
~~~

Các hướng phòng tránh:

- Exclude infrastructure methods khỏi pointcut phù hợp.
- Dùng reentrancy guard có scope đúng nếu engine hỗ trợ.
- Restore guard trong finally dù logger throw.
- Tránh global mutable guard không thread-safe.
- Test nested calls, multi-thread và trường hợp logger throw.

Nested advice hợp lệ vẫn có thể cần nhiều scopes. Phân biệt nested business operations có chủ ý với recursion vô hạn do instrumentation.

## 20. Observability: đo cleanup đúng tầng

Nếu chỉ log **finally entered**, không chứng minh resource release thành công. Theo dõi:

| Sự kiện | Ý nghĩa |
|---|---|
| acquire.start | Bắt đầu lấy quyền sở hữu |
| acquire.success | Resource thuộc ownership của scope |
| release.attempt | Cleanup được gọi |
| release.success | Cleanup báo thành công |
| release.failure | Cleanup báo lỗi |
| operation.primary.failure | Lỗi chính |
| operation.suppressed.failure | Secondary error |
| operation.completed | Scope hoàn tất theo định nghĩa |

Có thể gắn **requestId, attemptId, resourceId, ownerScope, joinPointKind, exceptionType**. Không lưu credentials, token hoặc dữ liệu nhạy cảm trong exception messages.

Số acquire bằng số release **attempts** chỉ chứng minh release được gọi, không chứng minh hệ thống đã giải phóng tài nguyên vật lý. Phân biệt success/failure/unknown theo contract.

## 21. Ma trận kiểm thử

| Tình huống | Cleanup | Caller/diagnostic |
|---|---|---|
| Before fail trước acquire | Không close resource chưa có | Before error |
| Acquire một phần rồi fail | Dọn phần đã acquire | Acquire error, close secondary nếu có |
| Target return | Close đúng một lần | Return khi close success |
| Target throw | Close đúng một lần | Target primary |
| Target throw + close throw | Attempt close | Target primary, close suppressed |
| Target return + close throw | Attempt close | Close error có thể là primary |
| After-like throw | Outer cleanup chạy | After primary |
| After-like + close throw | Attempt close | After primary, close suppressed |
| Hai resources lồng nhau | Đóng inner trước outer | Giữ primary và các suppressed |
| Advice short-circuit | Không proceed | Cleanup resource đã mở |
| Retry ba attempts | Acquire/release đúng scope | Attempt metrics/exception chain |
| Async chưa hoàn tất | Không close quá sớm | Future completion semantics |
| Cancellation | Không use-after-close | Cancel/error contract |
| ThreadLocal nested | Restore giá trị trước | Không context leak |
| Logger throw trong catch | Không vô tình che lỗi gốc | Original error còn truy vết |
| Commit/rollback error | Cleanup context theo policy | Không đoán outcome |
| Lock không acquire | Không unlock sai | Permit/ownership invariant |
| Multi-thread | Không release sai thread/race | Test concurrency |

### 21.1. Fault injection

Hãy cố ý gây lỗi tại các giai đoạn: trước acquire, giữa nhiều acquires, trong target, trong after-like, trong inner close, trong outer close, khi logging failure, trong retry và khi async callback xử lý. Với từng ca kiểm tra:

1. Resource nào đã thật sự được mở.
2. Resource nào đã được close attempt.
3. Thứ tự close có đúng ownership/LIFO không.
4. Caller nhận primary exception nào.
5. Suppressed/cause có còn đầy đủ.
6. Không có double close/use-after-close.
7. ThreadLocal/lock state được restore.
8. Không có side effect trái policy.

## 22. Những lỗi thường gặp

**Lỗi 1 — Đặt close sau proceed.** Proceed throw sẽ bỏ qua close.

**Lỗi 2 — Dọn chỉ trong after returning.** Target throw làm mất cleanup.

**Lỗi 3 — Chỉ dùng after throwing.** Normal return vẫn cần release.

**Lỗi 4 — Finally throw che lỗi gốc.** Cần policy primary/secondary, try-with-resources khi phù hợp.

**Lỗi 5 — Cho rằng finally luôn chạy dù JVM/process crash.** Không đúng.

**Lỗi 6 — Gọi close dù acquire fail trước đó.** Có thể NPE hoặc release sai resource.

**Lỗi 7 — Không dọn khi acquire được một phần.** Tài nguyên mở trước bước lỗi có thể leak.

**Lỗi 8 — Close resource chỉ được mượn.** Gây use-after-close cho owner thực.

**Lỗi 9 — Close hai lần và cho rằng idempotent.** Không được giả định từ AutoCloseable chung.

**Lỗi 10 — Coi suppressed là cause.** Hai quan hệ exception khác nhau.

**Lỗi 11 — Logging failure làm thay exception nghiệp vụ.** Có thể ảnh hưởng rollback/caller.

**Lỗi 12 — Return stream đã bị finally close.** Resource lifetime không khớp ownership transfer.

**Lỗi 13 — Retry trong một resource scope đã hỏng.** Có thể dùng lại transaction rollback-only.

**Lỗi 14 — Async method trả future nên close ngay.** Task có thể vẫn cần resource.

**Lỗi 15 — Cleanup lock trên thread khác.** Có thể vi phạm thread ownership.

**Lỗi 16 — Remove ThreadLocal phá outer context.** Nested scope cần restore previous value.

**Lỗi 17 — Audit chỉ đo finally entered.** Không biết release có thành công.

**Lỗi 18 — Logger bị pointcut intercept chính nó.** Gây reentrancy/recursion.

**Lỗi 19 — Coi close/rollback như nhau.** Transaction outcome khác connection/resource cleanup.

**Lỗi 20 — Tin cleanup đúng nghĩa mọi side effect được undo.** External effects cần idempotency/compensation/outbox.

## 23. Checklist triển khai

1. **Liệt kê resource** mà mỗi advice và target có thể acquire.
2. **Chỉ định owner** cụ thể, phân biệt borrow/transfer.
3. **Chọn lifetime** theo invocation, request, attempt hoặc async completion.
4. **Đọc contract** của close/unlock/commit/rollback/context restore.
5. **Dùng scope cleanup đúng**: try-with-resources hoặc finally phù hợp.
6. **Bảo vệ acquire một phần** và chỉ release các resources đã có.
7. **Quy định primary/secondary exceptions** và logging không che lỗi.
8. **Kiểm tra advice precedence**, short-circuit và proceed nhiều lần.
9. **Xem xét concurrency/async** và thread affinity.
10. **Xác định retry/idempotency** cho failure tại close/commit.
11. **Kiểm tra reentrancy** nếu advice gọi infrastructure.
12. **Viết tests success, target throw, advice throw và close throw**.
13. **Theo dõi metrics release success/failure**, không chỉ finally count.
14. **Tài liệu hóa giới hạn** của engine AOP và tài nguyên.

## 24. Câu hỏi ôn tập

**Câu 1.** Vì sao resource.close sau proceed mà không có finally có thể leak?

**Đáp:** Nếu proceed throw, control flow bỏ qua close.

**Câu 2.** Finally có đảm bảo close thành công không?

**Đáp:** Không, nó chỉ tạo cơ hội gọi cleanup trên đường rời scope thông thường; close có thể throw.

**Câu 3.** Body throw X, close throw Y trong try-with-resources: caller thấy gì?

**Đáp:** X là primary, Y thường ở X.getSuppressed().

**Câu 4.** Body return OK, close throw Y: caller nhận OK không?

**Đáp:** Không; operation thoát bằng Y.

**Câu 5.** Before throw trước khi Lease được tạo: có close Lease không?

**Đáp:** Không. Chưa acquire thì không close.

**Câu 6.** Acquire A thành công, acquire B throw: A phải thế nào?

**Đáp:** A cần cleanup theo ownership contract; nested try-with-resources giúp việc này.

**Câu 7.** After returning có thể thay thế finally để release resource không?

**Đáp:** Không, vì nó không bao đường target throw.

**Câu 8.** Tại sao logging exception trong finally nguy hiểm?

**Đáp:** Nó có thể che primary và thay outcome của tầng ngoài.

**Câu 9.** Retry(Resource(Target)) khác Resource(Retry(Target)) ra sao?

**Đáp:** Cấu trúc đầu có thể acquire/close mỗi attempt, cấu trúc sau dùng một scope cho nhiều attempts.

**Câu 10.** CompletableFuture chưa completed nhưng around finally close resource ngay: có nguy cơ gì?

**Đáp:** Async task có thể use-after-close; cần scope theo lifetime thực.

**Câu 11.** Có thể unlock bất kể lock.lockInterruptibly có thành công không?

**Đáp:** Không; chỉ unlock sau khi đã acquire hợp lệ.

**Câu 12.** Nested ThreadLocal scope chỉ remove trong finally có luôn đúng?

**Đáp:** Không, nếu outer scope có context cũ thì phải restore nó.

**Câu 13.** Suppressed exceptions có phải cause chain không?

**Đáp:** Không, suppressed lưu lỗi thứ cấp trong lúc unwind/cleanup.

**Câu 14.** Commit throw có đồng nghĩa database chắc đã rollback không?

**Đáp:** Không; outcome có thể uncertain.

**Câu 15.** Aspect trả InputStream đã đóng do finally thì sai ở đâu?

**Đáp:** Resource ownership/lifetime không phù hợp với API caller cần sử dụng.

**Câu 16.** Vì sao cần đếm release.success riêng release.attempt?

**Đáp:** Bước release có thể chạy nhưng throw; không được kết luận resource đã dọn thành công.

## 25. Sơ đồ ghi nhớ

~~~text
Caller
  |
  v
Outer around: acquire A
  |
  +-- try
       |
       v
     Inner around: acquire B
       |
       +-- try-with-resources
              |
              v
          Before / Target / After-like
                 |
               return / throw
                 |
                 v
            close B (can throw)
                 |
                 v
            primary + suppressed
       |
       v
     outer finally: cleanup A
  |
  v
Caller result/error

Bất biến:
- Owner rõ, scope rõ.
- Dọn những resource đã acquire.
- Đóng inner trước outer khi phù hợp.
- Không vô ý che primary exception.
- Đừng coi cleanup attempt là cleanup success.
~~~

**Kết luận:** khi advice hoặc mã gốc thất bại, việc dọn tài nguyên phải được thiết kế theo **ownership, scope, exception contract và precedence**. Với Java, dùng try/finally và try-with-resources đúng chỗ, tận dụng suppressed exceptions để bảo tồn lỗi cleanup thứ cấp. Với retry, transaction, thread-local context và async, hãy mở rộng phân tích từ method return tới **vòng đời thật của tài nguyên** và kiểm thử fault injection đầy đủ.

## Tài liệu đối chiếu

- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): vòng đời close và AutoCloseable contract.
- [Java Language Specification SE 17 — try](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): try/finally và try-with-resources.
- [Java SE 17 — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): suppressed exceptions và cause.
- [Java SE 17 — InvocationTargetException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): reflection exception wrapper.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): completion/cancellation trong async APIs.
- [AspectJ Programming Guide](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): mô hình join point, advice và precedence ở một ngôn ngữ AOP cụ thể.
