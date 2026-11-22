# Rủi ro nuốt lỗi và che khuất nguyên nhân gốc trong AOP

> **Mục tiêu:** Hiểu tại sao advice của lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP) có thể làm mất thông tin lỗi từ phần nghiệp vụ gốc; phân biệt nuốt ngoại lệ, thay ngoại lệ, đánh mất nguyên nhân, làm sai stack trace và che lỗi bằng cleanup; biết bảo toàn hợp đồng return/throw khi kết hợp nhiều aspect. Nội dung thuộc AOP tổng quát, áp dụng cho những mô hình weaving và interception hỗ trợ các điểm can thiệp tương ứng, không giả định một framework riêng.

## 1. Khi nghiệp vụ thất bại nhưng caller tưởng thành công

Một phương thức có thể báo lỗi bằng exception:

~~~text
Caller -> Around advice -> Original operation
                              |
                              +-- throws IOException
~~~

Nếu một advice chỉ có nhiệm vụ ghi log mà bắt lỗi rồi trả về giá trị bình thường:

~~~text
try:
    return proceed()
catch exception:
    log("failure")
    return "SUCCESS"
~~~

thì caller không còn biết rằng thao tác thật sự thất bại. Đây là trường hợp **swallowing**: lỗi bị bắt nhưng tín hiệu lỗi không đi tiếp theo hợp đồng.

Nguy cơ đặc biệt lớn khi caller sử dụng exception để quyết định retry, rollback, ghi audit hoặc ngắt workflow. Một return bình thường không đồng nghĩa dữ liệu/thao tác đã thành công về mặt nghiệp vụ.

Tuy nhiên, có **recovery hợp lệ**: một policy có thể chuyển sang nguồn dữ liệu dự phòng rồi trả kết quả được định nghĩa rõ. Khác biệt nằm ở **hợp đồng của thao tác** và việc fallback có thật sự đáp ứng hợp đồng, không phải chỉ ở sự hiện diện của catch.

## 2. Hợp đồng phương thức gồm cả đường thất bại

Một phương thức Java có thể kết thúc theo hai kiểu:

- **Normal completion:** trả một giá trị hoặc kết thúc bình thường với void.
- **Abrupt completion:** ném exception hoặc Error.

Ví dụ chữ ký:

~~~java
interface Reader {
    String read() throws java.io.IOException;
}
~~~

Đây là mảnh khai báo minh họa, chưa phải chương trình độc lập.

Caller của Reader.read có thể phân biệt một chuỗi hợp lệ với IOException để thực hiện policy khác nhau. Nếu advice biến IOException thành String hợp lệ về kiểu nhưng sai ý nghĩa, caller sẽ không thể thực hiện nhánh xử lý lỗi cần thiết.

Trong AOP, advice không chỉ được phép quan sát log: một số quanh advice có quyền thay return, bỏ qua proceed hoặc chuyển ngoại lệ. Quyền năng đó làm **đường return/throw** trở thành thành phần quan trọng của hợp đồng khi kết hợp aspect.

## 3. Bốn khái niệm dễ bị gộp nhầm

| Hiện tượng | Mô tả | Rủi ro |
|---|---|---|
| **Swallowing** | Bắt exception rồi không đưa thất bại tiếp đến boundary cần thiết | Caller tin rằng normal completion xảy ra |
| **Masking** | Một exception mới thay thế exception ban đầu | Caller thấy sai điểm thất bại quan trọng |
| **Lost cause** | Tạo wrapper nhưng bỏ tham chiếu nguyên nhân | Không truy được chuỗi nguyên nhân |
| **Lost stack context** | Ném một lỗi mới hoặc làm thay stack context không hợp lý | Stack trace hướng về mã advice thay vì nguồn lỗi |

Một advice có thể gặp nhiều hiện tượng cùng lúc. Ví dụ: Original ném IOException, advice ghi audit bằng một formatter, formatter ném IllegalStateException rồi được truyền ra ngoài mà không gắn cause. Lỗi Original bị che, và log cấp trên chỉ có thông tin về formatter.

Để phân tích đúng cần hỏi: **Lỗi đầu tiên là gì? Lỗi nào caller nhìn thấy? Ai thay đổi luồng giữa hai thời điểm đó?**

## 4. Phân biệt loại lỗi Java

Trong Java có ba nhóm quan trọng:

1. **Checked exception:** các Exception phải tuân thủ quy tắc kiểm tra của compiler, trừ những nhánh unchecked.
2. **Unchecked exception:** RuntimeException và các subclass, không bắt buộc khai báo bằng throws.
3. **Error:** các trường hợp từ java.lang.Error và subclass, thường chỉ tình trạng nghiêm trọng hoặc lỗi nền tảng.

Một advice bắt Exception không bao phủ mọi Error. Một advice bắt Throwable bao phủ cả Exception và Error, nhưng **bắt được không có nghĩa phục hồi được**.

Đặc biệt, không nên bắt Throwable rồi tự trả fallback như thành công, bởi nó có thể che OutOfMemoryError, StackOverflowError hoặc các lỗi nghiêm trọng khác.

Một số hạ tầng cần finally hoặc catch(Throwable) để **dọn trạng thái và ném lại cùng lỗi**; đó là nhu cầu khác với nuốt tất cả exception. Không có catch-all nào bảo đảm logger vẫn hoạt động an toàn trong mọi lỗi của JVM.

## 5. Advice có thể thay đường điều khiển của phần gốc

Sơ đồ:

~~~text
Caller
  |
  Trace around
    |
    Audit around
      |
      Recovery around
        |
        Original
~~~

Nếu Original ném IOException:

- Recovery có thể ném lại IOException.
- Recovery có thể chuyển thành một lỗi cấp cao có cause.
- Recovery có thể thực hiện fallback thật và trả bình thường.
- Recovery cũng có thể nuốt IOException rồi trả giá trị sai.

Trace và Audit ở ngoài **chỉ thấy kết quả từ các lớp bên trong**, không mặc định biết exception đầu tiên của Original.

Cùng một lỗi có thể được nhiều advice ghi nhận ở những thời điểm khác nhau mà caller chỉ thấy một lỗi hoặc thậm chí không thấy lỗi nào.

## 6. Short-circuit và swallowing không phải một

Short-circuit là khi một advice **không gọi phần còn lại**:

~~~text
Guard rejects input
  |
  returns REJECTED
  |
  Original never runs
~~~

Không có exception từ Original bị nuốt, vì Original chưa chạy.

Swallowing có thể xảy ra khi Original đã chạy và ném lỗi:

~~~text
Original executes
  |
  throws IOException
  |
  Recovery catches and returns REJECTED
~~~

Hai đường đều có thể trả REJECTED, nhưng chỉ đường thứ hai đã tạo ra lỗi từ phần gốc. Phân biệt này quan trọng với kiểm toán, transaction và việc đo số lần thực thi.

Khi debug, nên có cách xác định **Original đã được vào hay chưa**, thay vì suy từ dòng log của advice bên ngoài.

## 7. Nuốt exception làm hỏng retry

Caller có thể retry khi nhận một IOException tạm thời:

~~~text
try call operation
if transient IOException:
    retry within bounded policy
~~~

Nếu advice nằm bên trong bắt IOException rồi trả bình thường, caller **không nhận exception** và bỏ qua logic retry. Một hệ thống có thể âm thầm sử dụng kết quả thiếu dữ liệu.

Ngược lại, advice tự retry cũng có thể sai nếu caller hoặc hệ thống đã có một policy retry khác. Tác dụng phụ có thể lặp khi attempt đầu thực sự đã thay đổi trạng thái ngoài hệ thống nhưng bị mất phản hồi.

Không dùng nuốt lỗi hay retry như thủ thuật làm giảm log. Cần hiểu **loại lỗi, số lần Original chạy và tính idempotent**.

## 8. Nuốt lỗi và transaction

Trong nhiều thiết kế, kết thúc normal hoặc exceptional là tín hiệu quan trọng cho thành phần quản lý một đơn vị công việc. Nếu advice chuyển lỗi thành return, thành phần phía ngoài có thể quyết định dựa trên kết quả sai.

~~~text
Begin unit of work
    Original throws E
    Advice catches E and returns OK
Commit decision observes normal return
~~~

Sơ đồ này mô tả rủi ro trong **những hệ dùng return/throw làm tín hiệu**, không phải quy tắc commit/rollback chung của mọi transaction manager.

Ngoài ra, Original có thể đã tạo một phần side effect trước khi ném lỗi. Việc bắt rồi trả OK không khôi phục trạng thái, không tự rollback và không bảo đảm dữ liệu nhất quán.

## 9. Exception masking trong finally

Trong Java, finally thường được dùng để cleanup. Nhưng nếu finally ném lỗi mới khi try đã ném lỗi chính, lỗi mới có thể **thay thế lỗi chính** truyền ra caller.

~~~text
try:
    throw PrimaryIOException
finally:
    throw CleanupIllegalStateException
~~~

Caller có thể chỉ bắt CleanupIllegalStateException. Nếu exception gốc không được lưu trong cause hoặc suppressed, chuỗi truy nguyên có thể bị mất.

Đây là tình huống đặc biệt dễ gặp trong AOP, vì after/finally advice thường gọi logger, serializer, metric sink hoặc đóng resource. Nếu chính thao tác cleanup/observability thất bại, lỗi thứ cấp có thể che lỗi mà advice định quan sát.

## 10. Finally không có khả năng miễn lỗi

Cần xác định rõ:

- Nếu Original lỗi rồi cleanup lỗi, lỗi nào được ưu tiên?
- Lỗi cleanup có được gắn làm suppressed không?
- Nếu Original thành công nhưng cleanup lỗi, caller phải nhận tín hiệu nào?
- Cleanup là bắt buộc hay best-effort?
- Có nguy cơ lỗi formatter, serializer hoặc log sink che lỗi gốc?
- Liệu việc dùng finally ở một advice có thay đổi hợp đồng Error không?

Một observer chỉ đo thời gian thường muốn bảo toàn lỗi của Original, nhưng một resource bắt buộc đóng thành công có thể có hợp đồng xử lý lỗi khác. Không tự động catch mọi lỗi cleanup rồi im lặng khi resource đóng là điều kiện nghiệp vụ bắt buộc.

## 11. Cause và suppressed: hai quan hệ khác nhau

Trong Java, Throwable có thể giữ **cause**:

~~~text
DomainFailure
    caused by
IOException from storage
~~~

Cause nói rằng một lỗi cấp thấp dẫn tới lỗi được báo ở cấp cao.

Throwable cũng có thể giữ **suppressed exceptions**:

~~~text
Primary IOException
    suppressed:
      CleanupIllegalStateException
~~~

Suppressed hữu ích khi lỗi thứ cấp phát sinh trong lúc đang xử lý/đóng resource nhưng cần giữ lỗi chính làm lỗi truyền ra.

Không nên gộp mọi lỗi vào suppressed không suy nghĩ; cách lưu phải phản ánh ngữ nghĩa. Nhưng nếu một cleanup thất bại sau khi Original đã thất bại, hãy chủ động tránh **vứt mất cả primary lẫn secondary information**.

## 12. Bảo toàn stack trace và danh tính exception

Nếu advice chỉ quan sát, một lựa chọn thường tốt là:

~~~text
catch original E:
    record observation
    throw E
~~~

Việc ném lại cùng Throwable giúp giữ danh tính và thông tin mà Throwable đang chứa, thay vì tạo exception mới vô cớ.

Khi cần chuyển lỗi cấp thấp thành một ngoại lệ domain, nên có constructor nhận cause:

~~~java
final class DataFailure extends RuntimeException {
    DataFailure(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đây là khai báo Java minh họa.

Caller thấy DataFailure, nhưng đường getCause vẫn dẫn về lỗi cấp thấp. Ngược lại, new DataFailure("failed", null) chỉ cung cấp message mới mà có thể làm mất liên hệ tới IOException ban đầu.

### 12.1. Không biến việc thêm log thành việc thay exception

Một advice không nên tạo RuntimeException mới chỉ để ghi thêm một message trong khi hợp đồng caller cần IOException nguyên bản.

Nếu cần thay loại lỗi, đó phải là **quy tắc mapping được thiết kế, tài liệu hóa và kiểm thử**, không phải một phản ứng tùy ý tại catch.

## 13. Checked exceptions và hợp đồng throws

Xét API:

~~~java
interface Reader {
    String read() throws java.io.IOException;
}
~~~

Caller của API này có thể xử lý IOException. Một wrapper triển khai Reader không thể tùy tiện mở rộng throws checked exception thành Exception chung trong khai báo override.

Một aspect được weave vào đường thực thi cũng cần tôn trọng hợp đồng của ngôn ngữ/cơ chế được dùng. Nếu advice chuyển checked IOException thành unchecked RuntimeException, caller có thể bỏ lỡ nhánh xử lý IOException vốn đúng.

Một lỗi chuyển đổi có thể không bị compiler Java thông thường bắt nếu xảy ra qua reflection/proxy, nhưng nó vẫn làm thay đổi **API contract được quan sát**.

## 14. Java Dynamic Proxy và ngoại lệ bọc

Java Dynamic Proxy chuyển method invocation tới InvocationHandler. Nếu handler sử dụng **Method.invoke**, exception của method đích thường được bọc trong **InvocationTargetException**.

Ví dụ đoạn handler **chỉ là mảnh minh họa**:

~~~java
(proxy, method, args) -> {
    try {
        return method.invoke(target, args);
    } catch (java.lang.reflect.InvocationTargetException wrapped) {
        throw wrapped.getCause();
    }
}
~~~

Việc ném lại nguyên nhân gốc giúp tránh trả một wrapper reflection không được dự kiến. Nhưng phải nhớ: nếu handler đưa ra một checked exception **không tương thích throws của method giao diện**, Java Dynamic Proxy có thể bọc nó trong **UndeclaredThrowableException**.

Đó là quy tắc của một cơ chế proxy cụ thể, không phải quy tắc chung của mọi loại weaving AOP.

## 15. Ví dụ Java 17 số 1: lỗi được bảo toàn và lỗi bị nuốt

Ví dụ này lắp thủ công một chuỗi **Trace → Audit → Original**, sau đó thêm một **Swallow** ở giữa. Nó minh họa cách advice ngoài nhìn thấy exception hay normal return theo kết quả của advice trong.

**Đây là chương trình Java thuần mô phỏng around advice, không phải cú pháp của một công cụ weaving tự động.**

Lưu file **AdviceExceptionMaskingDemo.java**:

~~~java
import java.io.IOException;

public class AdviceExceptionMaskingDemo {
    @FunctionalInterface
    interface Next {
        String proceed() throws IOException;
    }

    interface Around {
        String invoke(Next next) throws IOException;
    }

    static final class Trace implements Around {
        @Override
        public String invoke(Next next) throws IOException {
            System.out.println("[trace] enter");
            try {
                String result = next.proceed();
                System.out.println("[trace] return " + result);
                return result;
            } catch (IOException error) {
                System.out.println("[trace] io " + error.getMessage());
                throw error;
            } catch (RuntimeException error) {
                System.out.println("[trace] runtime "
                        + error.getMessage());
                throw error;
            } finally {
                System.out.println("[trace] finally");
            }
        }
    }

    static final class Audit implements Around {
        @Override
        public String invoke(Next next) throws IOException {
            System.out.println("[audit] enter");
            try {
                String result = next.proceed();
                System.out.println("[audit] return " + result);
                return result;
            } catch (IOException error) {
                System.out.println("[audit] io " + error.getMessage());
                throw error;
            } catch (RuntimeException error) {
                System.out.println("[audit] runtime "
                        + error.getMessage());
                throw error;
            } finally {
                System.out.println("[audit] finally");
            }
        }
    }

    static final class Swallow implements Around {
        @Override
        public String invoke(Next next) throws IOException {
            try {
                return next.proceed();
            } catch (IOException error) {
                System.out.println("[bad] swallowed "
                        + error.getMessage());
                return "FALLBACK";
            }
        }
    }

    static String original(String mode) throws IOException {
        System.out.println("[business] " + mode);
        return switch (mode) {
            case "ok" -> "OK";
            case "io" -> throw new IOException("disk offline");
            case "runtime" ->
                    throw new IllegalArgumentException("invalid amount");
            default -> throw new IllegalArgumentException("unknown mode");
        };
    }

    static void runSafe(String mode) {
        System.out.println("== safe " + mode + " ==");
        try {
            String result = new Trace().invoke(
                    () -> new Audit().invoke(
                            () -> original(mode)));
            System.out.println("[caller] " + result);
        } catch (IOException | RuntimeException error) {
            System.out.println("[caller] "
                    + error.getClass().getSimpleName()
                    + ": " + error.getMessage());
        }
    }

    static void runSwallow() {
        System.out.println("== swallow io ==");
        try {
            String result = new Trace().invoke(
                    () -> new Swallow().invoke(
                            () -> new Audit().invoke(
                                    () -> original("io"))));
            System.out.println("[caller] " + result);
        } catch (IOException error) {
            System.out.println("[caller] IOException: "
                    + error.getMessage());
        }
    }

    public static void main(String[] args) {
        runSafe("ok");
        runSafe("io");
        runSafe("runtime");
        runSwallow();
    }
}
~~~

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

~~~bash
javac AdviceExceptionMaskingDemo.java
java AdviceExceptionMaskingDemo
~~~

**Stdout chính xác:**

~~~text
== safe ok ==
[trace] enter
[audit] enter
[business] ok
[audit] return OK
[audit] finally
[trace] return OK
[trace] finally
[caller] OK
== safe io ==
[trace] enter
[audit] enter
[business] io
[audit] io disk offline
[audit] finally
[trace] io disk offline
[trace] finally
[caller] IOException: disk offline
== safe runtime ==
[trace] enter
[audit] enter
[business] runtime
[audit] runtime invalid amount
[audit] finally
[trace] runtime invalid amount
[trace] finally
[caller] IllegalArgumentException: invalid amount
== swallow io ==
[trace] enter
[audit] enter
[business] io
[audit] io disk offline
[audit] finally
[bad] swallowed disk offline
[trace] return FALLBACK
[trace] finally
[caller] FALLBACK
~~~

### 15.1. Đường thành công

Trace vào trước Audit. Original trả OK; Audit ghi return/finally, Trace ghi return/finally, Caller nhận OK. Với observer thuần, các advice không cần thay kết quả.

### 15.2. Đường checked IOException

Original ném IOException. Audit và Trace đều ghi nhận rồi ném lại **cùng exception object**. Caller nhận IOException với message disk offline.

Điều đó không có nghĩa lỗi xảy ra nhiều lần. Một lỗi được quan sát ở hai boundary nên có hai thông điệp, nhưng chỉ một Original invocation đã ném lỗi.

### 15.3. Đường unchecked RuntimeException

Original ném IllegalArgumentException. Audit và Trace đều giữ nguyên loại và message. Caller có thể tiếp tục phân loại chính xác.

### 15.4. Đường Swallow

Original ném IOException, Audit ghi rồi ném lại. Swallow bắt và trả FALLBACK, nên Trace ở ngoài chỉ thấy normal return. Caller không còn nhận IOException.

Nếu FALLBACK là một kết quả đã được API định nghĩa là cách phục hồi hợp lệ, hành vi có thể đúng. Nếu Caller tưởng thao tác I/O thành công, nó là **che lỗi nguy hiểm**.

### 15.5. Giới hạn của ví dụ

Chương trình chỉ điều khiển một chain thủ công, không giải thích engine AOP nào chọn pointcut hoặc đặt precedence. Các catch minh họa IOException/RuntimeException, không catch Error. Trong hệ thật, lỗi logger, retry, transaction, async và chính sách phân quyền phải được kiểm thử riêng.

## 16. Một fallback chỉ hợp lệ khi đáp ứng hợp đồng

Không phải cứ bắt rồi trả kết quả là sai. Nhưng để gọi là **recovery**, cần ít nhất:

- API cho phép giá trị thay thế và caller nhận biết được semantics của nó.
- Chỉ những lỗi có thể phục hồi được bắt.
- Hành vi sau khi Original đã có một phần side effect được xác định.
- Không có yêu cầu rollback/retry ở ngoài bị phá.
- Có thông tin quan sát cần thiết về lần thất bại.
- Fallback không làm lộ hoặc biến dạng dữ liệu.
- Lỗi từ chính nguồn fallback được truyền/báo đúng.
- Không nuốt Error như một loại normal failure.

Một advice chỉ ghi metrics thường không sở hữu quyết định fallback. Một chính sách fallback nên là thành phần có **quyền và thông tin ngữ nghĩa đầy đủ**.

## 17. Try-with-resources và suppressed exceptions

Java có cơ chế **try-with-resources** giúp tránh lỗi đóng resource che lỗi chính trong một số trường hợp.

Khi thân try ném IOException và AutoCloseable.close cũng ném IllegalStateException, IOException được giữ làm **primary exception**; lỗi close được thêm vào danh sách **suppressed**.

Đây là cách tư duy tốt khi thiết kế cleanup trong advice: không để một lỗi phụ vô tình xóa thông tin về lỗi đã xảy ra trước.

Tuy nhiên không phải mọi resource có thể chuyển thành AutoCloseable, và không phải mọi thất bại thứ cấp nên được xử lý như nhau. Cần quyết định theo ranh giới trách nhiệm.

## 18. Ví dụ Java 17 số 2: masking và suppressed

Ví dụ dùng hai phương thức độc lập:

- **unsafe:** finally ném exception mới, che primary IOException.
- **safe:** try-with-resources giữ primary IOException và gắn lỗi close vào suppressed.

Lưu file **ExceptionSuppressionDemo.java**:

~~~java
import java.io.IOException;

public class ExceptionSuppressionDemo {
    @FunctionalInterface
    interface Action {
        void run() throws IOException;
    }

    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("[resource] close");
            throw new IllegalStateException("close failed");
        }
    }

    static void unsafe() throws IOException {
        try {
            System.out.println("[business] fail");
            throw new IOException("primary");
        } finally {
            System.out.println("[cleanup] fail");
            throw new IllegalStateException("cleanup failed");
        }
    }

    static void safe() throws IOException {
        try (FailingResource resource = new FailingResource()) {
            System.out.println("[business] fail");
            throw new IOException("primary");
        }
    }

    static void show(String name, Action action) {
        System.out.println("== " + name + " ==");
        try {
            action.run();
        } catch (Exception error) {
            System.out.println("[caller] "
                    + error.getClass().getSimpleName()
                    + ": " + error.getMessage());
            Throwable[] secondary = error.getSuppressed();
            System.out.println("[caller] suppressed="
                    + secondary.length);
            for (int i = 0; i < secondary.length; i++) {
                Throwable value = secondary[i];
                System.out.println("[caller] suppressed[" + i + "] "
                        + value.getClass().getSimpleName()
                        + ": " + value.getMessage());
            }
        }
    }

    public static void main(String[] args) {
        show("unsafe", ExceptionSuppressionDemo::unsafe);
        show("resource", ExceptionSuppressionDemo::safe);
    }
}
~~~

Chạy với JDK 17:

~~~bash
javac ExceptionSuppressionDemo.java
java ExceptionSuppressionDemo
~~~

**Stdout chính xác:**

~~~text
== unsafe ==
[business] fail
[cleanup] fail
[caller] IllegalStateException: cleanup failed
[caller] suppressed=0
== resource ==
[business] fail
[resource] close
[caller] IOException: primary
[caller] suppressed=1
[caller] suppressed[0] IllegalStateException: close failed
~~~

### 18.1. Vì sao unsafe làm mất primary?

Thân try chuẩn bị ném IOException, nhưng finally ném IllegalStateException. Lỗi finally được truyền ra. Trong code này, Throwable truyền ra không giữ IOException như cause hoặc suppressed, nên Caller không thể truy từ lỗi cuối về primary.

### 18.2. Vì sao safe giữ được primary?

Câu lệnh try-with-resources có quy tắc ưu tiên primary exception từ thân try và ghi lỗi close thành suppressed. Caller bắt IOException, còn Throwable.getSuppressed trả ra IllegalStateException do close.

### 18.3. Áp dụng cho advice

Nếu một advice xử lý resource khi Original lỗi, cần tránh một finally chứa I/O/serialization có thể tự ném và che nguyên nhân. Khi cleanup cũng có khả năng lỗi, nên chọn pattern bảo toàn primary và ghi nhận secondary phù hợp.

Nếu Original thành công nhưng cleanup thất bại, tùy hợp đồng cleanup failure có thể trở thành lỗi chính của toàn thao tác. Không tự nuốt lỗi của resource bắt buộc.

## 19. Logging rồi rethrow khác logging rồi return

Hai pattern khái niệm:

~~~text
Observer:
    catch E
    log E
    throw E
~~~

và:

~~~text
Swallowing:
    catch E
    log E
    return success-shaped value
~~~

Khác biệt là Caller có còn tín hiệu thất bại hay không.

Một dòng log không thay thế exception contract; caller có thể dựa vào exception type để retry, abort hoặc đánh dấu giao dịch thất bại.

Nếu policy cho phép return fallback, đừng dùng “OK” không phân biệt; nên có API hoặc kết quả thể hiện rõ trạng thái recovered/fallback.

## 20. Log đầy đủ ở mọi advice có tốt không?

Một IOException có thể đi qua nhiều quanh advice. Nếu Trace, Audit, Metrics và Caller đều in full stack trace, vận hành có thể thấy bốn log cho **một lỗi** và đếm sai tần suất lỗi.

Các vai trò nên được xác định:

- Aspect gần method có thể tăng metric theo loại lỗi.
- Aspect ở boundary có thể ghi một event lỗi đã chuẩn hóa.
- Boundary có quyền quan sát chi tiết có thể ghi stack trace đầy đủ.
- External API có thể gửi mã lỗi an toàn và correlation ID.

Không có một quy tắc chung cho mọi hệ rằng “chỉ log một lần”. Nhưng phải biết **mỗi log đại diện cho error occurrence, advice observation hay attempt**.

### 20.1. Stack trace có thể chứa dữ liệu nhạy cảm

Exception message có thể chứa đường dẫn, URL, identifier hoặc chuỗi từ input. Không tự động in raw arguments hoặc Throwable ở mọi sink. Cần phân loại dữ liệu, redaction, giới hạn kích thước và quyền truy cập phù hợp.

## 21. After-returning và after-throwing theo boundary riêng

Một after-returning advice bên ngoài Recovery có thể được kích hoạt khi Recovery chuyển IOException thành fallback, vì từ góc nhìn bên ngoài có **normal completion**.

Một after-throwing advice bên ngoài không nhất thiết thấy lỗi Original nếu lỗi đã được catch ở tầng trong.

~~~text
Original throws IOException
Inner returns FALLBACK
Outer after-returning observes FALLBACK
~~~

Hoặc:

~~~text
Original throws IOException
Inner converts to DomainFailure
Outer after-throwing observes DomainFailure
~~~

Điều này không chứng minh pointcut sai; đó là **hệ quả của exception flow** qua các lớp advice.

## 22. Advice có thể thất bại trước Original

Một before advice có thể ném lỗi khi chuẩn bị logging hoặc trích xuất ngữ cảnh. Khi đó Original chưa chắc được gọi.

~~~text
Before advice
   |
   +-- formatter throws
   |
   +-- Original not reached
~~~

Nếu Caller nhận IllegalArgumentException từ formatter, đó là lỗi ở advice, không phải bằng chứng nghiệp vụ gốc đã ném cùng loại lỗi.

Để phân biệt, có thể đặt một bộ đếm **Original invocation** trong ca thử tối thiểu; log của advice không đủ chứng minh Original đã chạy.

## 23. Retry và multiple proceed

Một quanh advice có thể retry bằng cách gọi continuation nhiều lần khi công cụ cho phép:

~~~text
Outer Trace
   Retry
     Attempt 1 -> Original throws E
     Attempt 2 -> Original returns OK
Outer Trace sees OK
~~~

Trace ở ngoài có thể ghi một lần normal return, trong khi một aspect nằm **bên trong Retry** ghi một attempt failure và một attempt success.

Do đó cần phân biệt:

- Số lời gọi của Caller.
- Số lần advice ngoài được vào.
- Số lần continuation của Retry được gọi.
- Số lần Original thực sự chạy.
- Số lần xảy ra side effect.

Retry không tự là swallowing, vì attempt sau có thể thành công thật. Nhưng retry thiếu idempotency và giới hạn lỗi có thể nguy hiểm như nuốt lỗi.

## 24. Async errors không xuất hiện trong cùng call stack

Một method Java trả **CompletableFuture** có thể return bình thường nhưng future hoàn thành exceptionally sau đó:

~~~text
submitAsync() returns future normally
                    |
                    +-- later: task fails
~~~

Một quanh advice đo tới lúc submitAsync return không nhất thiết thấy exception xảy ra lúc tác vụ chạy.

Các lỗi của CompletableFuture có thể được bọc trong CompletionException khi join, hoặc ExecutionException khi get. Cần kiểm tra **cause chain** để phân biệt wrapper và lỗi gốc.

Nếu một stage exceptionally bắt lỗi rồi trả fallback, stage sau có thể hoàn thành bình thường. Đây cũng có thể là recovery hợp lệ hoặc nuốt lỗi, tùy hợp đồng.

### 24.1. Không tin rằng fire-and-forget đã được quan sát

Nếu advice tạo một tác vụ nền và không quan sát future/completion, exception trong task có thể không truyền về Caller. Cần một policy failure sink hoặc completion callback có vòng đời phù hợp.

ThreadLocal dùng trong advice đồng bộ cũng không tự lan truyền tới mọi async continuation, nên correlation và exception mapping cần thiết kế riêng.

## 25. Fail-open và fail-closed của observability

Khi logging/metrics/audit sink thất bại, chính sách có thể:

- **Fail-open:** cho nghiệp vụ tiếp tục, có thể phù hợp telemetry best-effort.
- **Fail-closed:** không cho nghiệp vụ hoàn tất nếu không đáp ứng được yêu cầu quan sát/kiểm soát bắt buộc.

Không có đáp án phổ quát. Điều quan trọng là quyết định có căn cứ:

1. Event có bắt buộc không?
2. Người gọi cần tín hiệu lỗi nào?
3. Có thể ghi buffer hoặc retry sink không?
4. Rủi ro mất audit có được chấp nhận không?
5. Khi nghiệp vụ cũng lỗi, giữ primary như thế nào?
6. Có giới hạn thời gian hoặc tài nguyên cho việc quan sát không?

Một metrics advice không nên tự fail-closed chỉ vì logger ném RuntimeException bất ngờ; ngược lại một policy bảo mật bắt buộc không nên luôn fail-open chỉ để tránh exception.

## 26. Không tự addSuppressed mọi exception

Suppressed rất hữu ích nhưng phải dùng có chủ đích.

- Một Throwable không thể suppress chính nó.
- Một số Throwable có thể tắt suppression theo constructor.
- Một danh sách hàng nghìn suppressed errors có thể gây tăng bộ nhớ hoặc log khó đọc.
- Những lỗi retry khác nhau có thể cần báo dưới một aggregate exception riêng.

Nếu tạo domain failure từ một low-level failure, cause thường diễn đạt nguyên nhân tốt hơn. Nếu resource close lỗi trong lúc primary IOException đã tồn tại, suppressed có thể phù hợp hơn.

Chọn cấu trúc lỗi theo **quan hệ thực tế**, không theo cách làm cho stack trace trông dài hơn.

## 27. Không nhầm lỗi weaving với lỗi runtime advice

Một hệ AOP có thể thất bại ở nhiều tầng:

- Parser/validator pointcut từ chối biểu thức.
- Bộ dệt không thể xử lý class hoặc bytecode.
- JVM không nạp/liên kết được class sau biến đổi.
- Advice tự ném lỗi ở runtime.
- Original ném lỗi nghiệp vụ.
- Logger/cleanup của advice tạo lỗi thứ cấp.

Một RuntimeException hiện ở stack trace có tên interceptor chưa chứng minh interceptor gây ra lỗi; nó có thể chỉ là khung bao qua đó lỗi Original được truyền.

Cần truy cause/suppressed, vị trí phát sinh lỗi đầu tiên và số lần Original được vào.

## 28. Các kiểm thử tối thiểu cho hợp đồng ngoại lệ

| Ca thử | Điều cần xác minh |
|---|---|
| Original trả bình thường | Observer không thay return |
| Original ném IOException | Caller nhận đúng loại hoặc mapping được hợp đồng cho phép |
| Original ném RuntimeException | Không tự trả success giả |
| Original ném Error | Không bị catch-all nuốt |
| Advice lỗi trước proceed | Original chưa chạy và lỗi được phân loại đúng |
| Advice cleanup lỗi trong finally | Primary không bị che ngoài chính sách |
| Try-with-resources lỗi kép | Secondary nằm trong suppressed |
| Inner Recovery trả fallback | Outer thấy normal return có ý nghĩa rõ |
| Inner tạo domain exception | Cause chain giữ original |
| Multiple proceed do Retry | Original count và advice count đúng |
| Java Dynamic Proxy | Reflection wrapper và checked contract đúng |
| Future hoàn thành exceptionally | Lỗi được quan sát ở completion |
| Log sink thất bại | Fail-open/fail-closed đúng hợp đồng |
| Hai aspect cùng ghi lỗi | Không nhân số lỗi nghiệp vụ chỉ vì nhiều logs |

Không chỉ test success path. Các lỗi swallowing/masking thường chỉ lộ khi **Original và advice cùng đi qua exceptional flow**.

## 29. Kiểm thử exception identity, cause và suppressed

Trong một unit test, ta có thể tạo trước một exception E cho Original ném ra, rồi kiểm tra Caller nhận **cùng object** nếu advice chỉ quan sát.

Pseudocode:

~~~text
Original throws E
Caller catches C
assert C is same object as E
~~~

Nếu một policy chuyển lỗi thành D:

~~~text
Caller catches D
assert D.getCause() is E
~~~

Nếu cleanup thứ cấp ném S:

~~~text
Caller catches E
assert E.getSuppressed() contains S
~~~

Những kiểm thử này mạnh hơn việc chỉ kiểm tra một dòng “[ERROR]” có xuất hiện. Chúng giúp chứng minh **hợp đồng của lỗi tại ranh giới Caller**.

## 30. Quy trình điều tra khi mất nguyên nhân gốc

1. Bắt đầu từ exception **Caller thực sự nhận**.
2. Kiểm tra getCause và getSuppressed đầy đủ.
3. Xác định Original có thật sự chạy hay không.
4. Liệt kê các advice và thứ tự bao ngoài/bên trong.
5. Kiểm tra các catch quanh continuation.
6. Tìm catch kết thúc bằng return fallback.
7. Tìm catch tạo exception mới nhưng không truyền cause.
8. Tìm finally, resource close, serializer hoặc logger có thể ném.
9. Xác định exception đầu tiên phát sinh ở Original hay advice.
10. Kiểm tra reflection/proxy có wrapper không.
11. Kiểm tra retry, số lần proceed và số lần Original.
12. Kiểm tra async completion nếu phương thức trả future.
13. Đối chiếu throws contract với policy domain-level.
14. Tái hiện trường hợp lỗi kép (Original + cleanup).
15. Viết regression tests cho normal, checked, unchecked và Error paths.

Không thay đồng thời precedence, catch, retry và fallback. Khi đổi nhiều biến một lúc khó chỉ ra thay đổi nào làm lỗi không còn bị che.

## 31. Những lỗi thường gặp

**Lỗi 1 — catch(Exception) rồi trả mặc định:** che thất bại và làm Caller tưởng thành công.

**Lỗi 2 — finally ném lỗi phụ:** thay primary bằng lỗi cleanup.

**Lỗi 3 — Tạo RuntimeException không cause:** mất thông tin nguyên nhân.

**Lỗi 4 — Catch Throwable rồi nuốt Error:** có thể che sự cố JVM nghiêm trọng.

**Lỗi 5 — Chỉ in message:** không đủ stack/cause để chẩn đoán trong điều kiện cần thiết.

**Lỗi 6 — In full stack trace ở mọi aspect:** một lỗi gây nhiều log trùng và lộ dữ liệu.

**Lỗi 7 — Không giải bọc InvocationTargetException:** lỗi reflection che lỗi target.

**Lỗi 8 — Đưa checked exception ra ngoài chữ ký hợp đồng:** có thể gây wrapper proxy không dự kiến.

**Lỗi 9 — Retry không kiểm soát:** lặp side effect khi lần đầu thất bại sau khi đã thực hiện tác dụng phụ.

**Lỗi 10 — Coi Future return là task success:** bỏ sót lỗi async xảy ra sau.

**Lỗi 11 — Logger failure được coi là lỗi nghiệp vụ:** không phân biệt nguồn lỗi.

**Lỗi 12 — Catch rồi printStackTrace nhưng không ném lại:** logging không thay exception contract.

**Lỗi 13 — Chỉ unit test từng advice:** không kiểm tra kết hợp nhiều aspect, precedence và masking.

**Lỗi 14 — Không định nghĩa fail-open/fail-closed:** hệ thống phản ứng ngẫu nhiên khi sink lỗi.

## 32. Checklist trước khi dùng catch trong advice

- [ ] Advice này là observer hay có quyền phục hồi?
- [ ] Original có hợp đồng throws rõ ràng?
- [ ] Catch có quá rộng không?
- [ ] Có nuốt Error hoặc IOException quan trọng?
- [ ] Return fallback có ý nghĩa đúng trong API?
- [ ] Nếu chuyển exception, cause có giữ không?
- [ ] Nếu cleanup cũng lỗi, primary có bị che không?
- [ ] Có dùng suppressed thích hợp cho secondary failure?
- [ ] Có xử lý checked exception đúng khi qua proxy?
- [ ] Có giải bọc InvocationTargetException khi cần?
- [ ] Có theo dõi lỗi async ở đúng completion boundary?
- [ ] Có phân biệt attempt failure với request outcome?
- [ ] Có test số lần Original trong retry/short-circuit?
- [ ] Có quyết định fail-open/fail-closed cho logging và audit?
- [ ] Có giới hạn dữ liệu nhạy cảm trong exception/log?
- [ ] Có integration test nhiều aspect ở cả normal và exceptional paths?

## 33. Bài tập tự kiểm tra

### Câu 1. Bắt rồi trả OK

Original ném IOException, advice bắt rồi trả “OK”. Caller còn bắt IOException được không?

**Đáp án:** không, nếu advice kết thúc bình thường. Đây là swallowing nếu API không cho phép recovery kiểu đó.

### Câu 2. Lỗi kép trong finally

Original ném IOException A, finally ném IllegalStateException B. Caller có thể thấy lỗi nào?

**Đáp án:** B có thể che A nếu code không bảo toàn primary.

### Câu 3. Cause và suppressed

Một domain exception được sinh ra bởi IOException; quan hệ nào thường phù hợp? Cleanup cùng lúc thất bại thì sao?

**Đáp án:** cause cho chuỗi nguyên nhân; suppressed phù hợp để giữ lỗi cleanup thứ cấp khi primary vẫn được ném.

### Câu 4. Outer after-throwing

Inner bắt IOException và trả fallback. Outer after-throwing có chắc nhận IOException?

**Đáp án:** không. Outer có thể chỉ thấy normal return.

### Câu 5. Checked exception qua dynamic proxy

Handler ném thẳng một checked exception ngoài throws của interface method. Có thể xảy ra điều gì?

**Đáp án:** cơ chế Java Dynamic Proxy có thể dùng UndeclaredThrowableException để bọc lỗi.

### Câu 6. Catch Throwable

Một around advice catch Throwable và trả default trong mọi trường hợp. Nguy cơ chính?

**Đáp án:** nuốt cả Error, che tình trạng nghiêm trọng và báo success giả.

### Câu 7. Retry

Một lời gọi thất bại sau khi đã ghi một side effect; retry có an toàn mặc định không?

**Đáp án:** không. Cần idempotency, transaction semantics và giới hạn loại lỗi.

### Câu 8. Future

Method trả CompletableFuture bình thường nhưng task sau đó lỗi. After-returning quanh method có chắc quan sát lỗi task?

**Đáp án:** không, nếu chỉ quan sát thời điểm method return.

### Câu 9. Logger trong finally

Original ném IOException; logger trong finally ném RuntimeException. Vì sao Caller nhận lỗi logger?

**Đáp án:** exception mới từ finally có thể che primary.

### Câu 10. Hai log khác nhau

Audit trong ghi attempt failure, Trace ngoài ghi request success sau recovery. Có chắc thông tin mâu thuẫn?

**Đáp án:** không. Chúng quan sát hai ranh giới và hai loại outcome khác nhau.

## 34. Kết luận

**Swallowing** khiến Caller không còn tín hiệu thất bại mà phần gốc đã tạo. **Masking** khiến lỗi mới hoặc wrapper che đi nguyên nhân gốc. Trong AOP, nguy cơ tăng lên vì nhiều advice có thể cùng bao một join point và thay đổi đường return/throw trước khi Caller nhìn thấy kết quả.

Các nguyên tắc cốt lõi:

- Một observer không nên tự chuyển lỗi thành success-shaped return.
- Log không thay được exception contract.
- Mỗi advice chỉ nhìn thấy trạng thái mà phần bên trong truyền ra.
- Finally/cleanup có thể che primary nếu tự ném lỗi.
- Cause và suppressed giúp bảo toàn quan hệ giữa các lỗi khác vai trò.
- Java checked exceptions và proxy/reflection cần được xử lý đúng hợp đồng.
- Không catch Throwable rồi giả vờ thành công.
- Retry/short-circuit thay đổi số lần Original chạy và lỗi được nhìn thấy.
- Async failure phải được quan sát tại completion boundary.
- Kiểm thử đường lỗi quan trọng không kém kiểm thử đường thành công.

**Câu hỏi cuối cùng khi viết catch trong advice:** *Tôi đang thực sự phục hồi lỗi này theo hợp đồng, hay chỉ nên quan sát và giữ nguyên tín hiệu thất bại cho thành phần chịu trách nhiệm tiếp theo?*
