# Bắt, chuyển đổi hoặc truyền tiếp ngoại lệ trong around advice của AOP

## 1. Mục tiêu và bối cảnh

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP)**, **around advice** có thể bao quanh một join point được pointcut lựa chọn, thực hiện hành vi trước/sau và — nếu cơ chế AOP hỗ trợ — quyết định có tiếp tục đến phần xử lý gốc hay không. Thao tác tiếp tục thường được mô tả bằng khái niệm `proceed`.

Khi đoạn được tiếp tục ném một ngoại lệ, around advice có thể:

- **Truyền tiếp** ngoại lệ đó để caller nhìn thấy lỗi gốc.
- **Chuyển đổi** thành loại lỗi khác phù hợp ranh giới ứng dụng, thường giữ lỗi gốc làm `cause`.
- **Bắt và phục hồi** bằng giá trị dự phòng khi hợp đồng nghiệp vụ cho phép.
- **Thử lại** phần xử lý được tiếp tục, nếu việc lặp an toàn.
- **Bổ sung thông tin chẩn đoán** hoặc xử lý lỗi thứ cấp từ logging/cleanup.

Sức mạnh này tạo ra rủi ro: một thao tác gốc đã hoàn tất có thể bị báo lỗi chỉ vì advice chạy sau đó thất bại; một lỗi chính có thể bị che bởi lỗi kiểm toán; một retry sai thời điểm có thể nhân đôi tác dụng phụ.

**Bài học nằm ở phạm vi AOP tổng quát, cơ bản và nâng cao.** Những đoạn có từ khóa `around`, `pointcut` và `proceed` dưới đây là **mã giả**, không phải một cú pháp chuẩn chung cho mọi công cụ. Các ví dụ Java 17 được nêu riêng để quan sát luồng điều khiển mà không phụ thuộc một framework.

## 2. Around advice đứng ở đâu trong luồng thực thi?

Một hình dung:

```text
Caller
  |
  v
Around advice
  |-- before work
  |
  |-- proceed() ----------------------------+
  |                                         |
  |                                    Advice bên trong
  |                                         |
  |                                    Mã nghiệp vụ gốc
  |                                         |
  |<----------- kết quả hoặc ngoại lệ ------+
  |
  |-- xử lý kết quả/lỗi
  |-- finally nếu có
  v
Caller nhận kết quả hoặc ngoại lệ cuối cùng
```

**Điểm quan trọng:** `proceed()` thường tiếp tục tới **phần còn lại trong chuỗi advice và join point**, chứ không nhất thiết gọi trực tiếp phương thức nghiệp vụ. Vì vậy ngoại lệ ném ra từ `proceed` có thể bắt nguồn từ:

1. Thân phương thức nghiệp vụ.
2. Advice ở một lớp bên trong.
3. Cơ chế can thiệp hoặc adapter trung gian.
4. Tài nguyên được dùng trong phần thực thi được bao.

Không nên chỉ dựa vào việc bắt lỗi ở `proceed` để khẳng định “business failed”.

### 2.1. Mẫu cơ bản cho thao tác đồng bộ

```text
around selectedOperation(context):
    beforeStep(context)
    try:
        result = proceed(context)
        afterSuccessStep(result)
        return result
    catch error:
        reportFailure(error)
        throw error
    finally:
        finishStep()
```

Đây là mã giả. Cách viết trên **bắt cả lỗi từ `afterSuccessStep`**, không chỉ lỗi từ `proceed`. Nếu việc ghi metric thành công thất bại, `reportFailure` vẫn được gọi, dù nghiệp vụ đã chạy thành công. Phạm vi `try/catch` phải được thiết kế có chủ ý.

## 3. Truyền tiếp ngoại lệ gốc: rethrow/propagate

Khi aspect chủ yếu làm logging hoặc đo đạc, giữ nguyên ngoại lệ có thể là lựa chọn phù hợp:

```text
around operation:
    try:
        return proceed()
    catch original:
        recordErrorAccordingToPolicy(original)
        throw original
```

Về ý tưởng, `throw original` **ném lại cùng đối tượng lỗi**, để caller tiếp tục xử lý như hợp đồng gốc. Việc advice đã quan sát lỗi không làm mất nguyên nhân.

Java minh họa bằng wrapper thông thường:

```java
static String passthrough(java.util.concurrent.Callable<String> work)
        throws Exception {
    try {
        return work.call();
    } catch (Exception original) {
        System.out.println("observed:" + original.getClass().getSimpleName());
        throw original;
    }
}
```

Đây là mảnh Java hợp lệ khi đặt trong class; nó không phải một chương trình độc lập có `main`. `Callable.call()` chỉ đóng vai trò continuation minh họa, **không phải API around advice của một engine AOP**.

Ưu điểm truyền tiếp:

- Caller không phải thay đổi đường xử lý lỗi vốn có.
- Loại và thông điệp lỗi gốc được giữ.
- Có thể quan sát thêm mà không biến lỗi thành một tình trạng nghiệp vụ khác.
- Tránh vô tình biến lỗi input thành lỗi hệ thống, hoặc ngược lại.

Nhược điểm tiềm tàng: nếu hợp đồng ứng dụng **cần che lỗi hạ tầng** khỏi caller, truyền tiếp nguyên dạng có thể làm lộ chi tiết hoặc buộc tầng bên ngoài phụ thuộc API của nhà cung cấp. Khi đó nên cân nhắc chuyển đổi.

### 3.1. Nếu logger cũng ném lỗi thì sao?

Giả sử `recordErrorAccordingToPolicy` ném `AuditFailure` trước khi `throw original` được thực hiện. Lỗi gốc có thể bị che hoàn toàn.

Với telemetry tùy chọn, có thể quyết định lỗi logging không được thay thế lỗi nghiệp vụ. Với audit bắt buộc, yêu cầu có thể khác. Không có chính sách chung đúng cho mọi trường hợp; cần định nghĩa từ hợp đồng, không dựa vào việc `catch` có sẵn.

## 4. Chuyển đổi ngoại lệ: translation và wrapping

**Chuyển đổi ngoại lệ** nghĩa là ranh giới ứng dụng công bố một loại lỗi có ý nghĩa hơn thay cho lỗi thấp tầng.

Ví dụ: dịch lỗi truy cập tài nguyên thành lỗi “dịch vụ tạm thời không sẵn sàng”:

```text
around applicationBoundary:
    try:
        return proceed()
    catch LowLevelUnavailable original:
        throw ApplicationUnavailable("cannot complete request", cause=original)
```

Đoạn trên là mã giả, không mang cú pháp constructor chung. Trong Java, cách giữ nguyên nhân gốc có thể như sau:

```java
try {
    return remoteClient.fetch();
} catch (java.io.IOException original) {
    throw new IllegalStateException("remote data unavailable", original);
}
```

Đây là mảnh mã giả định có `remoteClient.fetch()`. Constructor của `IllegalStateException` nhận `original` làm cause, nên caller hoặc hệ thống chẩn đoán có thể gọi `getCause()`.

So sánh:

| Cách xử lý | Caller nhận | Thông tin nguyên nhân |
| --- | --- | --- |
| `throw original` | Lỗi gốc | Vẫn là đối tượng ban đầu |
| `throw new ApplicationFailure("...", original)` | Lỗi ứng dụng mới | Có cause trỏ về lỗi gốc |
| `throw new ApplicationFailure("...")` | Lỗi ứng dụng mới | Có thể mất liên hệ gốc |
| `return fallback` | Giá trị bình thường | Lỗi bị xử lý nội bộ, phải có hợp đồng |
| `retry proceed()` | Kết quả từ lần tiếp theo hoặc lỗi | Có nguy cơ lặp phần gốc |

### 4.1. Translation không phải thay mọi lỗi bằng một lỗi chung

Một anti-pattern:

```text
catch anyError:
    throw ServiceUnavailable()
```

Nó có thể biến cả lỗi bảo mật, thiếu dữ liệu, lỗi lập trình và lỗi cơ sở hạ tầng thành một thông báo duy nhất. Khi đó caller khó phân loại lỗi cần sửa input, lỗi cần đăng nhập và lỗi có thể retry.

Nên ánh xạ **những loại lỗi cụ thể có ngữ nghĩa đã biết**; với các lỗi chưa biết, cân nhắc truyền tiếp hoặc xử lý tại ranh giới có đầy đủ thông tin hơn.

### 4.2. Cause được giữ trong hệ thống không có nghĩa phải đưa mọi chi tiết cho người dùng

Một hệ thống có thể lưu cause và stack trace trong kênh quan sát có kiểm soát, đồng thời trả thông điệp an toàn và mã lỗi ổn định cho client. Không nên in mật khẩu, token, dữ liệu thanh toán hoặc thông tin truy vấn nhạy cảm trong phản hồi.

## 5. Bắt và phục hồi bằng fallback

Around advice có thể biến ngoại lệ thành **kết quả dự phòng**, nhưng chỉ khi chính sách cho phép.

Ví dụ hợp lý: thao tác tra cứu đề xuất tùy chọn được phép trả dữ liệu cache còn hiệu lực nếu nguồn bên ngoài tạm lỗi.

```text
around optionalRead:
    try:
        return proceed()
    catch TemporaryReadFailure:
        return validCachedValue
```

Không nên áp dụng máy móc cho:

- Chuyển tiền chưa biết trạng thái.
- Tạo đơn hàng đã có side effect.
- Thay đổi phân quyền.
- Ghi audit bắt buộc.
- Cập nhật kho hoặc ghi dữ liệu không idempotent.

**Fallback không chứng minh phần gốc chưa chạy.** Nếu lỗi xảy ra sau khi phần gốc đã thực hiện một phần hoặc đã tạo side effect, caller nhận fallback có thể hiểu sai hệ thống.

Một fallback hợp lệ phải:

1. Đúng kiểu và hợp đồng trả về.
2. Đúng ngữ nghĩa nghiệp vụ, không giả mạo thành công.
3. Có quy tắc độ mới và tính nhất quán nếu dùng cache.
4. Có cách nhận biết degraded mode khi cần.
5. Có kiểm thử phục hồi bình thường và thất bại lặp lại.

## 6. Lỗi trước và sau `proceed` khác nhau thế nào?

Xét:

```text
around operation:
    auditStart()            // lỗi ở đây xảy ra trước phần gốc
    result = proceed()      // lỗi từ chuỗi bên trong
    auditSuccess(result)    // lỗi ở đây sau khi đã có result
    return result
```

Các ranh giới có hậu quả khác nhau:

| Thời điểm lỗi | Phần gốc đã chạy? | Rủi ro |
| --- | --- | --- |
| `auditStart` ném lỗi | Chưa, nếu chặn trước `proceed` | Caller có thể nhận lỗi phụ trợ thay vì chạy nghiệp vụ |
| `proceed` ném lỗi | Có thể có hoặc chưa | Cần phân biệt nguồn và trạng thái side effect |
| `auditSuccess` ném lỗi | Phần được tiếp tục đã trả bình thường | Caller nhận lỗi dù phần gốc có thể hoàn tất |
| `finally` ném lỗi | Tùy đường đi trước đó | Che kết quả/lỗi đang lan truyền |

Ví dụ thực tế: một lệnh cập nhật đơn hàng thành công, nhưng advice ghi metric sau đó ném ngoại lệ. Nếu caller retry chỉ vì nhìn thấy exception, lệnh cập nhật có thể bị thực hiện lại.

### 6.1. Thu hẹp phạm vi `try/catch`

Để chỉ bắt lỗi thoát từ phần được tiếp tục:

```text
around operation:
    auditStartAccordingToPolicy()

    try:
        result = proceed()
    catch continuationError:
        auditContinuationFailureAccordingToPolicy(continuationError)
        throw continuationError

    auditSuccessAccordingToPolicy(result)
    return result
```

Điều này không tự xử lý lỗi của `auditStart` và `auditSuccess`; nó chỉ làm ranh giới rõ ràng hơn. Nếu cần phân biệt lỗi từ business và advice con, còn phải có cách xác định nguồn ở tầng tương ứng.

## 7. Ví dụ Java 17 độc lập: propagate, translate, fallback

Java thông thường không tự cung cấp cú pháp khai báo aspect và pointcut. Để học cơ chế kiểm soát ngoại lệ, ta dùng wrapper thủ công giống một around advice và một đối tượng nghiệp vụ.

Lưu tệp `AroundExceptionFlowDemo.java`:

```java
public class AroundExceptionFlowDemo {
    interface Operation {
        String run(String mode);
    }

    static final class BusinessFailure extends RuntimeException {
        BusinessFailure(String message) {
            super(message);
        }
    }

    static final class ApplicationFailure extends RuntimeException {
        ApplicationFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class BusinessOperation implements Operation {
        int calls;

        @Override
        public String run(String mode) {
            calls++;
            System.out.println("business:" + mode);

            if (!"ok".equals(mode)) {
                throw new BusinessFailure("backend:" + mode);
            }

            return "OK:" + mode;
        }
    }

    static String around(Operation target, String mode) {
        System.out.println("around:enter:" + mode);

        try {
            String result;

            try {
                result = target.run(mode);
            } catch (BusinessFailure original) {
                System.out.println("around:caught:" + original.getMessage());

                if ("translate".equals(mode)) {
                    throw new ApplicationFailure(
                            "operation unavailable", original
                    );
                }

                if ("fallback".equals(mode)) {
                    System.out.println("around:recover:" + mode);
                    return "CACHED";
                }

                throw original;
            }

            System.out.println("around:success:" + result);
            return result;
        } finally {
            System.out.println("around:exit:" + mode);
        }
    }

    public static void main(String[] args) {
        BusinessOperation target = new BusinessOperation();

        for (String mode : new String[] {
                "ok", "propagate", "translate", "fallback"
        }) {
            System.out.println("case:" + mode);

            try {
                String result = around(target, mode);
                System.out.println("caller:result:" + result);
            } catch (RuntimeException error) {
                System.out.println("caller:error:"
                        + error.getClass().getSimpleName()
                        + ":" + error.getMessage());

                if (error.getCause() != null) {
                    System.out.println("caller:cause:"
                            + error.getCause().getClass().getSimpleName()
                            + ":" + error.getCause().getMessage());
                }
            }
        }

        System.out.println("business:calls:" + target.calls);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac AroundExceptionFlowDemo.java
java AroundExceptionFlowDemo
```

Kết quả:

```text
case:ok
around:enter:ok
business:ok
around:success:OK:ok
around:exit:ok
caller:result:OK:ok
case:propagate
around:enter:propagate
business:propagate
around:caught:backend:propagate
around:exit:propagate
caller:error:BusinessFailure:backend:propagate
case:translate
around:enter:translate
business:translate
around:caught:backend:translate
around:exit:translate
caller:error:ApplicationFailure:operation unavailable
caller:cause:BusinessFailure:backend:translate
case:fallback
around:enter:fallback
business:fallback
around:caught:backend:fallback
around:recover:fallback
around:exit:fallback
caller:result:CACHED
business:calls:4
```

### 7.1. Phân tích

- `ok`: phần gốc trả kết quả, wrapper truyền tiếp kết quả và chạy `finally`.
- `propagate`: wrapper bắt `BusinessFailure` để ghi thông tin rồi ném lại **cùng lỗi**.
- `translate`: wrapper tạo `ApplicationFailure` mới, giữ `BusinessFailure` làm `cause`.
- `fallback`: wrapper bắt lỗi và trả `CACHED`. Đây là **hành vi phục hồi giả định là được phép**; không nên áp dụng cho mọi nghiệp vụ.
- `business:calls:4`: cả bốn kịch bản đều đã gọi phần gốc **đúng một lần**, kể cả fallback.

Ví dụ cố ý không có weaving hay pointcut thật. Nó minh họa cách `try/catch/finally` hoạt động khi được dùng để mô phỏng các nhánh của around advice.

## 8. Rethrow, wrap, suppress và swallow không giống nhau

| Hành vi | Tác động |
| --- | --- |
| **Rethrow** | Giữ lỗi ban đầu cho caller |
| **Wrap** | Caller nhận lỗi mới, có thể mang cause gốc |
| **Translate** | Chuyển ý nghĩa lỗi sang hợp đồng tầng ứng dụng |
| **Add suppressed** | Giữ lỗi thứ cấp bên cạnh lỗi chính |
| **Swallow** | Nuốt lỗi mà không ném lại; có thể làm caller tưởng đã thành công |
| **Recover/fallback** | Trả giá trị thay thế có chủ đích |
| **Retry** | Có thể khiến phần gốc chạy thêm lần nữa |

Bắt được một lỗi không tự làm thay đổi trạng thái nghiệp vụ. Việc trả fallback hay wrap lỗi là một quyết định riêng; nó phải dựa vào yêu cầu thay vì thói quen “catch tất cả để hệ thống không crash”.

### 8.1. Cause của ngoại lệ mới

Java hỗ trợ tạo ngoại lệ mới kèm lỗi nguyên nhân:

```java
RuntimeException translated =
        new IllegalStateException("application error", original);
```

Đây là mảnh mã giả định `original` là một `Throwable`. `translated.getCause()` trỏ đến `original`. Có cause giúp truy vết nhưng không có nghĩa mọi tầng bên ngoài phải hiển thị nguyên stack trace cho end user.

### 8.2. Suppressed cho lỗi phụ

Nếu business đã ném lỗi `B` và cleanup lại ném lỗi `C`, có thể ưu tiên truyền tiếp `B` rồi gắn `C` là suppressed:

```java
try {
    doOriginalWork();
} catch (RuntimeException original) {
    try {
        recordFailure(original);
    } catch (RuntimeException reportingError) {
        original.addSuppressed(reportingError);
    }
    throw original;
}
```

Đây là mảnh mã Java, giả định hai phương thức trợ giúp tồn tại. Chính sách này phù hợp khi `recordFailure` là **hành vi phụ** không được phép che lỗi chính; một hoạt động audit bắt buộc có thể cần chính sách khác.

Không gọi `addSuppressed` để tự suppress chính ngoại lệ đó vào nó: Java không cho phép self-suppression.

## 9. Lỗi của `finally` có thể che lỗi gốc

Mảnh Java:

```java
static void example() {
    try {
        throw new IllegalArgumentException("original");
    } finally {
        throw new IllegalStateException("cleanup");
    }
}
```

Nếu gọi hàm này, caller nhận `IllegalStateException("cleanup")`, chứ không tự động nhận `IllegalArgumentException("original")` trong suppressed. Khi đưa dọn dẹp vào around advice, phải xác định nên xử lý như thế nào nếu cleanup thất bại trong lúc đã có lỗi chính.

### 9.1. Đối chiếu với `try-with-resources`

Java `try-with-resources` có cơ chế giữ ngoại lệ từ thân `try` làm **primary** và đưa lỗi đóng tài nguyên vào suppressed khi cả hai cùng thất bại.

```java
try (SomeResource resource = acquireResource()) {
    performOperation();
}
```

Đây là mảnh minh họa với kiểu/phương thức giả định. Không được suy từ ngữ nghĩa của `try-with-resources` rằng một `finally` thủ công trong advice cũng tự lưu lỗi phụ tương tự.

### 9.2. Cleanup có thể là hành vi bắt buộc

Nếu một lỗi cleanup chứng tỏ hệ thống mất ràng buộc nghiêm trọng, không nên chỉ giấu nó để ưu tiên lỗi business. Cần phân loại mức độ và quyết định rõ lỗi nào caller nhận, còn lỗi nào lưu ở cause/suppressed hay kênh giám sát.

## 10. Bắt lỗi từ `proceed` không đủ để xác định nguồn lỗi

Xét chuỗi:

```text
OuterAudit(
    InnerMetrics(
        BusinessOperation
    )
)
```

`BusinessOperation` trả kết quả bình thường, nhưng `InnerMetrics` ném `MetricFailure` trong phần sau. Khi `OuterAudit` gọi `proceed`, nó sẽ quan sát một ngoại lệ.

Với outer, đây là **continuation failure**, không mặc nhiên là “business failure”. Nếu outer chuyển tất cả lỗi thành `DomainFailure` thì nó có thể khiến một lỗi logging phụ trợ trông giống lỗi nghiệp vụ.

Kiểm thử nên ghi rõ:

- Body nghiệp vụ có chạy không?
- Body đã trả về bình thường chưa?
- Lỗi đến từ advice nào?
- Lỗi đã bị chuyển đổi bao nhiêu lớp?
- Caller nhận loại nào và có truy vết được cause không?

## 11. Thứ tự của nhiều aspect ảnh hưởng đến lỗi quan sát

Một outer advice có thể nhận giá trị/lỗi sau khi inner đã chuyển đổi:

| Inner xử lý | Outer nhận từ `proceed` |
| --- | --- |
| Ném lại lỗi `BusinessFailure` | `BusinessFailure` |
| Bọc thành `ApplicationFailure(cause=BusinessFailure)` | `ApplicationFailure` |
| Trả fallback | Kết quả bình thường |
| Ném lỗi metrics sau thành công | `MetricFailure` |

Ngược lại, lỗi do outer tạo ra **sau khi inner kết thúc** không thể được inner bắt lại từ quá khứ. Vì thế khi thiết kế audit/transaction/retry/error translation cần biết thứ tự có hiệu lực giữa các advice.

**Không dựa vào thứ tự viết trong file như cam kết toàn cục.** Công cụ AOP có thể có quy tắc precedence riêng; phải đọc hợp đồng công cụ và kiểm thử tình huống nhiều advice cùng khớp.

## 12. Retry là hành vi thay đổi luồng mạnh

Mã giả:

```text
around operation:
    try:
        return proceed()
    catch TransientFailure:
        return proceed()
```

Một số công cụ cho phép gọi lại `proceed`; các công cụ khác có giới hạn riêng. Nếu gọi được nhiều lần, phần gốc **có thể thực thi nhiều lần**.

Nguy cơ quan trọng:

```text
Lần 1:
  business hoàn thành và đã ghi đơn
  inner advice ghi metric ném lỗi

Outer catch:
  hiểu nhầm là lỗi tạm thời của nghiệp vụ
  gọi proceed lần 2

Lần 2:
  business có thể lại ghi đơn
```

Retry an toàn cần:

1. Phân loại lỗi phù hợp, không retry mọi `Exception`.
2. Biết thao tác có side effect và có idempotency hay không.
3. Giới hạn số lần thử, thời gian, backoff và điều kiện dừng.
4. Truy vết mỗi lần gọi để điều tra.
5. Phân biệt lỗi phát sinh **trước**, **trong** và **sau** phần gốc.
6. Kiểm thử cả “business đã thành công nhưng post-processing thất bại”.

Một quanh-advice chỉ muốn giám sát không nên tự phát động retry mà chưa được thiết kế nghiệp vụ chấp thuận.

## 13. Checked và unchecked exceptions trong Java

Trong Java, checked exception thường cần khai báo hoặc được xử lý; `RuntimeException` và `Error` thuộc các nhánh unchecked. Một advice quanh lời gọi Java có thể gặp giới hạn về việc ném checked exception qua chữ ký phương thức không khai báo nó.

Ví dụ:

```java
interface Lookup {
    String find(String key);
}
```

Nếu around advice muốn ném `java.io.IOException` mới qua ranh giới `find`, việc có hợp lệ hay bị bọc phụ thuộc ngôn ngữ AOP, cơ chế weaving hoặc proxy và hợp đồng của chữ ký. Không có quy tắc chung rằng mọi checked exception từ advice đều xuất hiện nguyên dạng ở caller.

Một phương án chuyển đổi có chủ đích:

```java
try {
    return loadExternal();
} catch (java.io.IOException original) {
    throw new IllegalStateException("external data unavailable", original);
}
```

Đoạn giả định có `loadExternal()`. Nó giữ cause trong một loại unchecked mới, nhưng vẫn **đổi hợp đồng lỗi** nên cần cân nhắc.

### 13.1. Đừng nuốt mọi `Throwable`

`catch(Throwable)` có thể chặn cả lỗi môi trường nghiêm trọng. Nuốt `OutOfMemoryError` rồi trả `null` không thể coi là chiến lược phục hồi đáng tin. Bắt những nhóm lỗi đã xác định, và nếu cơ chế buộc phải nhận `Throwable` thì phải phân loại và truyền tiếp có ý thức.

### 13.2. Với reflection có thể có lỗi bọc kỹ thuật

Nếu interceptor dùng `Method.invoke`, ngoại lệ từ phần đích thường được bọc trong `InvocationTargetException`. Khi đó có thể cần đọc `getCause()`. Đây là thuộc tính của cách triển khai dùng Java reflection, không phải quy tắc rằng mọi engine AOP đều để ngoại lệ reflection đi qua caller.

## 14. Lỗi bất đồng bộ nằm ngoài một `catch` đồng bộ

Giả sử phương thức trả về `CompletableFuture<Result>`:

```text
Caller
  |
  v
around -> proceed() trả Future chưa hoàn tất
  |
  v
around trả Future
  |
  v
tác vụ chạy về sau -> Future completed / failed
```

Một `try/catch` đồng bộ quanh `proceed()` chỉ thấy lỗi ném **trong chính lời gọi ấy**. Lỗi phát sinh về sau có thể được lưu trong future và xuất hiện khi future hoàn tất đặc biệt.

Muốn chuyển đổi lỗi bất đồng bộ cần quan sát **completion stage** tương ứng. Mảnh Java minh họa:

```java
CompletableFuture<String> normalized = original.handle((value, error) -> {
    if (error == null) {
        return value;
    }
    throw new IllegalStateException("async operation failed", error);
});
```

Giả định `original` là `CompletableFuture<String>` đã khai báo và có import phù hợp. `normalized` là **stage mới**; khi callback ném lỗi, stage đó thất bại theo ngữ nghĩa API. `error` có thể là một lớp bọc tùy đường completion; cần xem xét cause chain.

Kiểm thử ít nhất: hoàn tất bình thường, hoàn tất thất bại, hủy, timeout, callback lỗi, completion trên luồng khác và ngữ cảnh của từng request.

## 15. Ngoại lệ và side effect không đồng nhất

Đừng dùng một ngoại lệ từ quanh-advice để kết luận:

- Giao dịch đã rollback.
- Đơn hàng chưa được tạo.
- Thanh toán chưa được gửi.
- Một hệ thống bên ngoài chưa xử lý yêu cầu.
- Một task bất đồng bộ chắc chắn chưa hoàn tất.

Khi advice ném lỗi **sau** phần nghiệp vụ, side effect có thể đã được xác nhận bền vững. Khi advice ném lỗi **trước**, phần gốc có thể chưa chạy. Khi `proceed` ném lỗi, một phần xử lý có thể đã xảy ra.

Ở hệ thống cần retry, hãy có mã yêu cầu/idempotency key hoặc cách tra cứu trạng thái để caller không phải suy đoán từ kiểu exception đơn thuần.

## 16. Bảo mật, kiểm toán và lỗi phụ trợ

Không có quy tắc chung rằng lỗi logging luôn có thể bỏ qua. Cần phân loại mối quan tâm:

| Aspect | Nếu chính advice gặp lỗi | Điều cần cân nhắc |
| --- | --- | --- |
| Metrics tùy chọn | Có thể giữ nguyên kết quả/lỗi business | Tránh telemetry làm hỏng đường nghiệp vụ |
| Logging chẩn đoán | Có thể ghi ở kênh phụ hoặc giới hạn lỗi | Không để logger gây đệ quy |
| Audit bắt buộc | Có thể phải từ chối hoặc xác nhận trạng thái | Đảm bảo yêu cầu pháp lý/nghiệp vụ |
| Authorization | Thường không được ngầm cho phép khi hệ thống kiểm tra lỗi | Fail-open/fail-closed phải có hợp đồng |
| Error translator | Giữ cause và mã lỗi ổn định | Không rò rỉ dữ liệu nhạy cảm |
| Retry | Có thể gọi lại operation | Idempotency, phân loại lỗi |
| Cleanup | Có thể sinh lỗi thứ cấp | Primary/cause/suppressed |

Không tự động ghi toàn bộ tham số trong error handler. Chúng có thể chứa token, bí mật hoặc dữ liệu cá nhân; ngay cả `toString()` cũng có thể tốn chi phí hoặc ném lỗi. Thay vào đó dùng correlation ID và các trường đủ cho truy vết.

## 17. Kiểm thử riêng từng nhánh của around advice

Một chiến lược hiệu quả là viết các ca độc lập với kết quả mong muốn:

| Ca | Business được gọi? | Around làm gì? | Caller mong đợi |
| --- | --- | --- | --- |
| Thành công | 1 lần | Chuyển tiếp result | Result ban đầu |
| Lỗi cần giữ | 1 lần | Rethrow | Cùng lỗi gốc |
| Lỗi cần dịch | 1 lần | Wrap | Loại lỗi mới, cause đúng |
| Lỗi có fallback | 1 lần | Return fallback | Giá trị hợp lệ |
| Before lỗi | 0 lần | Không proceed | Lỗi before |
| After lỗi | Business đã chạy | Bước sau ném | Không hiểu nhầm business chưa chạy |
| Cleanup đồng thời lỗi | Tùy trường hợp | Giữ thông tin lỗi chính/phụ | Có primary/cause/suppressed theo hợp đồng |
| Inner advice lỗi | Tùy trường hợp | Outer quan sát | Không gán nhãn sai nguồn |
| Retry | Có thể nhiều lần | Gọi proceed lại | Số lần hợp lệ, không lặp side effect |
| Async failure | Tác vụ chạy về sau | Xử lý completion | Đúng stage và cause |

### 17.1. Test identity của lỗi truyền tiếp

Với Java, khi hợp đồng yêu cầu rethrow đúng đối tượng, kiểm tra bằng identity thay vì chỉ so message:

```java
RuntimeException original = new IllegalArgumentException("bad");
// Sau khi gọi wrapper ở một bài test:
boolean sameObject = (caught == original);
```

Đây là mảnh mã minh họa, giả định `caught` là lỗi đã thu được. Với wrap, hãy kiểm tra `translated.getCause() == original` nếu đó là thiết kế.

### 17.2. Test đường không khớp pointcut

Một error translator dành riêng cho hoạt động thanh toán không được vô tình đổi lỗi của logger hoặc công việc hạ tầng khác. Cần kiểm thử cả tập join point **không nên can thiệp**, cũng như cách công cụ chặn lời gọi nội bộ.

### 17.3. Test thứ tự advice

Dựng hai advice giả (một cái dịch lỗi, một cái ghi audit) với thứ tự được xác định rõ; kiểm tra audit nhìn thấy lỗi trước hay sau dịch. Điều này giúp phát hiện lỗi phân loại khi triển khai các aspect lồng nhau.

## 18. Đồng thời, đệ quy và reentrancy

Một around advice xử lý lỗi theo từng invocation không nên lưu `currentError` vào một biến mutable dùng chung mà không quản lý. Hai request đồng thời có thể ghi đè cause, số lần retry hoặc correlation ID của nhau.

Với đệ quy, nhiều frame cùng kiểu join point có thể đang tồn tại. Giữ counter retry hoặc context theo từng lời gọi, không giả định chỉ một lỗi đang được xử lý tại mọi thời điểm.

Nếu advice báo lỗi qua một logger mà logger lại khớp cùng pointcut, có thể phát sinh vòng gọi advice. Giới hạn phạm vi pointcut hoặc dùng cơ chế chống tái nhập được thiết kế đúng; một cờ global đơn giản có thể chặn nhầm những invocation độc lập.

## 19. Quy trình thiết kế chính sách ngoại lệ

1. **Xác định hợp đồng nghiệp vụ:** thao tác nào, side effect gì, lỗi nào caller cần biết?
2. **Chọn đúng join point và pointcut:** method call hay execution, phạm vi weaving nào?
3. **Liệt kê các nguồn lỗi:** before, continuation, inner advice, after, cleanup, async completion.
4. **Xác định nguyên tắc ưu tiên:** lỗi nào là primary và có cần cause/suppressed không?
5. **Chỉ định nhóm lỗi được bắt:** tránh catch-all có thể nuốt bug và lỗi nghiêm trọng.
6. **Chọn rethrow/translate/fallback/retry theo từng nhóm:** không dùng một chính sách cho mọi lỗi.
7. **Thiết kế việc ghi thông tin:** không để logging tùy chọn che lỗi chính; tránh rò rỉ dữ liệu.
8. **Quy định checked/unchecked:** phù hợp Java và cơ chế AOP đang dùng.
9. **Kiểm thử đường thực thi thật:** cả lời gọi nội bộ, nhiều advice, tình huống lỗi và side effect.
10. **Kiểm thử concurrent/async:** context và lỗi thuộc đúng invocation/stage.

## 20. Những sai lầm thường gặp

**“Catch được lỗi là có thể trả kết quả mặc định.”** Không. Fallback có thể che side effect hoặc thông báo thành công giả.

**“Catch của proceed luôn nhận lỗi nghiệp vụ.”** Không. Inner advice hoặc interception cũng có thể là nguồn.

**“Wrap bằng exception mới nhưng không lưu cause cũng được.”** Có thể làm mất dữ liệu chẩn đoán quan trọng.

**“Business ném lỗi thì after/cleanup không thể ném lỗi thứ hai.”** Có thể, và lỗi thứ hai có thể che lỗi chính.

**“Caller nhận exception thì business chắc chắn chưa chạy.”** Sai với lỗi trong after step.

**“Retry mọi exception sẽ cải thiện độ tin cậy.”** Có thể lặp side effect không an toàn.

**“Checked exception từ advice truyền nguyên dạng trong mọi công cụ.”** Không có cam kết chung.

**“Một around catch sẽ tự xử lý mọi lỗi CompletableFuture.”** Catch đồng bộ khác xử lý lỗi completion bất đồng bộ.

**“Thứ tự nhiều aspect luôn là thứ tự khai báo.”** Cần xác minh precedence thực tế.

**“Logger an toàn vì chỉ quan sát.”** Logger có thể ném lỗi, lộ dữ liệu và kích hoạt lại pointcut.

## 21. Câu hỏi luyện tập

**1.** `proceed` ném `BusinessFailure`, around advice `throw original`. Caller nhận gì?

Thông thường caller nhận cùng đối tượng `BusinessFailure` nếu không có một advice ngoài khác chuyển đổi tiếp.

**2.** Around advice tạo `ApplicationFailure("unavailable", original)`. Khác gì với `ApplicationFailure("unavailable")`?

Dạng đầu giữ `original` làm cause; dạng sau có thể làm mất liên hệ trực tiếp đến lỗi gốc.

**3.** Nghiệp vụ tạo đơn thành công, after step ném `MetricFailure`. Có nên retry ngay không?

Không thể kết luận. Phải xác minh đơn đã tạo và có idempotency hay không; lỗi metric không có nghĩa nghiệp vụ chưa thực hiện.

**4.** Inner advice đã đổi `IOException` thành `DomainFailure`. Outer bắt được lỗi nào từ `proceed`?

Outer nhìn thấy `DomainFailure` do inner đưa ra, trừ khi có tầng khác thay đổi tiếp. Có thể truy về `IOException` nếu cause được giữ.

**5.** Một Future hoàn tất lỗi sau khi method đã trả về. Catch đồng bộ quanh `proceed` có chắc bắt được không?

Không. Cần xử lý completion của Future/stage tương ứng.

**6.** Vì sao catch bao cả `logSuccess` dễ sai?

Vì lỗi từ chính logging sẽ được phân loại như lỗi của `proceed` hoặc business, dù phần gốc có thể thành công.

**7.** Nếu body đã ném lỗi chính và cleanup cũng ném, xử lý thế nào?

Xác định chính sách ưu tiên; có thể giữ lỗi chính và gắn lỗi cleanup bằng suppressed khi phù hợp, không để lỗi thứ cấp vô tình che lỗi chính.

## 22. Checklist trước khi triển khai

- [ ] Phân biệt rethrow, wrap, translate, fallback và retry.
- [ ] Catch chỉ những loại lỗi đã định nghĩa hợp đồng.
- [ ] Biết `proceed` đang bao những tầng advice nào.
- [ ] Đặt `try/catch` đúng phạm vi nguồn lỗi cần phân loại.
- [ ] Bảo toàn cause/suppressed theo chính sách.
- [ ] Không để logging/metrics tùy chọn vô tình che lỗi chính.
- [ ] Phân biệt lỗi trước và sau khi tạo side effect.
- [ ] Fallback hợp lệ và không tạo thành công giả.
- [ ] Retry an toàn, có giới hạn và idempotency.
- [ ] Checked/unchecked tương thích với Java/công cụ AOP.
- [ ] Kiểm thử từng đường lỗi và thứ tự nhiều aspect.
- [ ] Kiểm thử target không khớp, self-invocation và giới hạn weaving.
- [ ] Xử lý đúng completion bất đồng bộ.
- [ ] Không làm lộ bí mật từ args/exception trong log.
- [ ] Tránh lưu lỗi hoặc retry state chung giữa các invocation.

## 23. Kết luận

**Around advice có thể bắt, chuyển đổi hoặc truyền tiếp ngoại lệ, nhưng mỗi lựa chọn làm thay đổi hợp đồng tại ranh giới được bao quanh.** Truyền tiếp phù hợp khi cần giữ lỗi gốc; chuyển đổi phù hợp khi cần mô hình lỗi ổn định nhưng phải giữ nguyên nhân; fallback và retry chỉ hợp lệ khi nghiệp vụ và side effect cho phép.

Thiết kế đáng tin cậy cần xác định đúng **nguồn lỗi, thời điểm xảy ra, thứ tự advice và trạng thái thực tế của phần gốc**. Chỉ khi đó around advice mới thêm được giá trị xuyên suốt mà không làm caller hiểu sai kết quả nghiệp vụ.
