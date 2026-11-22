# Ngoại lệ phát sinh từ advice và ảnh hưởng tới lời gọi gốc trong AOP

## 1. Hiểu đúng vấn đề

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP)**, một **aspect** tập trung một mối quan tâm xuyên suốt, chẳng hạn kiểm toán, ghi log, kiểm soát quyền, theo dõi thời gian hoặc giám sát lỗi. Một **pointcut** chọn các **join point** mà công cụ AOP hỗ trợ; **advice** chứa hành vi được thực thi tại các điểm đã chọn thông qua cơ chế weaving hoặc interception.

Advice không nằm ngoài chương trình theo nghĩa “không thể gây lỗi”. **Advice cũng là mã chạy thật**, có thể tạo đối tượng, gọi API, truy cập bộ nhớ, làm I/O và **ném ngoại lệ**. Ngoại lệ từ advice có thể làm thay đổi điều mà mã gọi ban đầu nhận được, kể cả khi thân phương thức nghiệp vụ không hề có lỗi.

Hãy phân biệt ba nguồn thất bại:

1. **Thất bại của mã nghiệp vụ gốc:** phương thức được gọi ném lỗi khi đang xử lý dữ liệu.
2. **Thất bại trong advice:** mã trước/sau/bao quanh join point ném lỗi khi ghi log, kiểm toán, xác thực, dọn dẹp hoặc biến đổi kết quả.
3. **Thất bại của cơ chế can thiệp:** cấu hình weaving, bộ chặn, phản xạ hoặc các thành phần trung gian gây lỗi. Nguồn này cần phân tích riêng, không mặc định là lỗi nghiệp vụ.

Tùy **thời điểm** và **thứ tự** advice, một lỗi có thể:

- Làm phần nghiệp vụ **không được chạy**.
- Phát sinh **sau khi nghiệp vụ đã thực hiện thành công**, khiến caller vẫn nhận ngoại lệ.
- **Che khuất** ngoại lệ nghiệp vụ gốc.
- Được bao thành ngoại lệ mới có **cause** để lưu vết nguồn.
- Bị advice quanh thao tác **bắt rồi chuyển thành kết quả khác**, nếu hợp đồng và cơ chế cho phép.
- Tạo lỗi mới ở tầng dọn dẹp hoặc tầng advice ngoài cùng.

Trọng tâm không chỉ là câu hỏi “advice có thể ném lỗi không?”, mà còn là: **lỗi xuất hiện ở ranh giới nào, phần gốc có chạy hay chưa, caller nhận gì, và làm sao không làm mất thông tin quan trọng?**

## 2. Cần biết các vai trò trước khi lần theo ngoại lệ

| Thành phần | Vai trò | Liên hệ đến lỗi |
| --- | --- | --- |
| **Caller** | Gọi thao tác và quan sát kết quả/ngoại lệ | Hợp đồng caller có thể bị advice thay đổi |
| **Join point** | Điểm có thể can thiệp trong mô hình thực thi | Xác định ranh giới nào được quan sát |
| **Pointcut** | Chọn các join point cần advice | Chọn sai điểm có thể khiến lỗi lan tới nơi ngoài dự kiến |
| **Before advice** | Chạy trước phần được chọn | Có thể ngăn phần gốc chạy nếu ném lỗi |
| **After returning advice** | Chạy sau một phần thực thi hoàn tất bình thường | Lỗi của advice có thể biến một lần thành công thành thất bại bên ngoài |
| **After throwing advice** | Chạy trên đường kết thúc bằng ngoại lệ phù hợp | Có thể log lỗi gốc, nhưng cũng có thể ném lỗi riêng |
| **After/finally advice** | Chạy lúc kết thúc theo ngữ nghĩa công cụ | Lỗi khi dọn dẹp có thể che lỗi trước đó |
| **Around advice** | Bao quanh và kiểm soát việc tiếp tục | Có thể chuyển tiếp, bắt, thay thế hoặc bỏ qua kết quả/lỗi nếu được phép |
| **Weaving/interception** | Kết hợp advice với mã cần can thiệp | Quyết định đường gọi nào thực sự đi qua advice |

**Một nguyên tắc cốt lõi:** ngoại lệ được nhìn thấy ở một ranh giới chưa chắc là ngoại lệ được tạo ra bởi chính phần nghiệp vụ của ranh giới ấy. Advice phía trong có thể đã thay thế nó trước khi chuyển lên tầng ngoài.

## 3. Lỗi ở before advice: phần nghiệp vụ có thể chưa từng bắt đầu

Xét một thao tác `withdraw()` có kiểm tra chính sách trước khi xử lý:

```text
Caller
  |
  v
Before advice
  |
  +-- kiểm tra thành công --> business withdraw() --> kết quả
  |
  +-- ném lỗi -----------> caller nhận lỗi
                            business withdraw() không chạy
```

Ví dụ mã giả AOP, **không phải cú pháp Java độc lập**:

```text
before selectedWithdrawal(context):
    if not authorized(context.actor):
        throw AccessDenied("permission required")
```

Nếu before advice thực sự ở trên đường chuyển tiếp đến phần nghiệp vụ, nó có thể ném lỗi và chặn bước tiếp theo. Hậu quả:

- Thân nghiệp vụ có thể **không chạy**, nên không được suy rằng đã có một giao dịch rút tiền.
- Caller có thể nhận ngoại lệ phát sinh từ chính sách, không phải từ `withdraw()`.
- Một advice khác nằm **bên ngoài** có thể quan sát lỗi đó; advice ở **bên trong** chưa được bắt đầu có thể không chạy.
- Điều kiện retry của caller cần nhận biết đây là lỗi chính sách, không coi mọi lỗi đều đáng thử lại.

Không phải mọi cơ chế AOP đều cho một before advice cùng quyền kiểm soát như around advice. Nhưng trong các mô hình cho phép trước-advice ném ngoại lệ qua ranh giới join point, đó là một cơ chế ngăn tiếp tục tự nhiên.

### 3.1. Khi before advice ném lỗi có phải luôn là sai?

Không. **Kiểm soát quyền hoặc bảo vệ điều kiện tiền đề** có thể chủ động ném ngoại lệ để từ chối thao tác. Đây là hành vi có chủ ý nếu được mô tả trong hợp đồng.

Ngược lại, một before advice chỉ dùng để **ghi log kỹ thuật** nhưng lại ném lỗi vì hệ thống log tạm thời không hoạt động có thể làm dừng nghiệp vụ dù không phải mục tiêu thiết kế. Có nên coi log là bắt buộc hay không phải được quyết định rõ: audit pháp lý bắt buộc khác telemetry tùy chọn.

### 3.2. Kiểm tra “nghiệp vụ chưa chạy” bằng cách nào?

Trong kiểm thử, dùng counter hoặc một target giả có thể ghi lại số lần được gọi. Với case từ chối hợp lệ, thường mong muốn:

```text
beforeEntered = 1
businessEntered = 0
callerReceived = AccessDenied
```

Đây là một kịch bản giả định. Nếu nhiều advice nằm lồng nhau, cần định nghĩa những counter nào được đo để tránh nhầm một advice chưa chạy với tất cả advice đều chưa chạy.

## 4. Lỗi ở after returning advice: thành công bên trong, thất bại bên ngoài

Giả sử phần gốc đã ghi đơn hàng và trả `"ORDER-123"`. Sau đó, after returning advice ném lỗi khi ghi metric:

```text
Caller
  |
  v
BusinessOperation
  |
  +-- lưu đơn thành công
  |
  +-- return "ORDER-123"
  |
  v
After returning advice
  |
  +-- metrics client ném MetricFailure
  |
  v
Caller nhận MetricFailure, không nhận "ORDER-123"
```

**Đây là một trong những tình huống nguy hiểm nhất khi xử lý ngoại lệ từ advice.** Caller có thể nhận lỗi dù phần nghiệp vụ đã có tác dụng phụ và hoàn tất. Nếu caller retry vô điều kiện, một thao tác không idempotent có nguy cơ được thực hiện lần nữa.

Ví dụ:

- Ghi đơn hàng xong rồi lỗi khi ghi metric.
- Gửi email thành công rồi lỗi lúc log sự kiện.
- Hoàn tất chuyển trạng thái rồi lỗi lúc ghi audit ngoài giao dịch.
- Gửi yêu cầu tới hệ thống ngoài được chấp nhận, sau đó advice ném lỗi.

Không được suy ra “caller nhận ngoại lệ” đồng nghĩa “nghiệp vụ chưa thực thi” hoặc “mọi tác dụng phụ đã rollback”. **Ngoại lệ không tự bảo đảm giao dịch được hoàn tác.**

### 4.1. Có phải mọi after returning advice luôn chạy trên mọi kết quả?

Không. Nó chỉ chạy trên **đường hoàn tất bình thường mà nó được thiết kế để quan sát**, với các điều kiện kiểu giá trị trả về nếu công cụ có cơ chế bind/lọc tương ứng. Nếu một advice bên trong đã chuyển kết quả thành lỗi, after returning ở tầng ngoài có thể không chạy; sau đó có thể phát sinh luồng after throwing ở tầng phù hợp.

Trong ví dụ bài này, cụm “after returning” dùng theo nghĩa tổng quát; vị trí chính xác và tương tác với các advice khác phụ thuộc hệ thống AOP.

## 5. Lỗi ở after throwing advice: mất dấu ngoại lệ gốc

Một after throwing advice thường dùng để ghi nhận sự cố:

```text
BusinessOperation -> throw OriginalFailure
                         |
                         v
                    After throwing advice
                         |
                         +-- ghi nhận được --> rethrow OriginalFailure
                         |
                         +-- tự ném AuditFailure
                                           |
                                           v
                                  Caller thấy AuditFailure
                                  (nếu không giữ OriginalFailure)
```

Nếu advice kết thúc bình thường, mô hình after throwing thường để ngoại lệ gốc **tiếp tục lan truyền** theo ngữ nghĩa công cụ. Nhưng nếu chính advice lại ném một lỗi mới, lỗi được quan sát ở ranh giới ngoài có thể khác.

Đoạn mã giả:

```text
afterThrowing operation(error):
    auditSystem.record(error)  // thao tác này có thể ném AuditFailure
```

Khi `auditSystem.record` thất bại, ta có **hai vấn đề**: lỗi nghiệp vụ `OriginalFailure` và lỗi của hệ thống kiểm toán `AuditFailure`. Nếu không thiết kế cách lưu nguyên nhân, caller hoặc hệ thống quan sát chỉ thấy lỗi sau.

### 5.1. After throwing không đồng nghĩa “được quyền nuốt lỗi”

Trong nhiều mô hình AOP, after throwing advice có chức năng **quan sát** nhánh thất bại; nó không tự biến lỗi thành một return thành công. Muốn chủ động bắt rồi chuyển lỗi thành kết quả dự phòng, thường cần một **around advice** hoặc tầng xử lý lỗi có quyền điều khiển quá trình tiếp tục.

Không nên giả định chỉ cần viết `return` bên trong thân của một advice sau lỗi thì phương thức gốc sẽ đổi thành công. Cách xử lý phụ thuộc loại advice và hợp đồng ngôn ngữ công cụ.

### 5.2. Lỗi nào cần ưu tiên?

Nếu đây là telemetry **không bắt buộc**, có thể muốn giữ `OriginalFailure` làm lỗi chính và ghi `AuditFailure` là lỗi phụ trợ. Nếu audit **bắt buộc** đến mức không có nhật ký thì toàn bộ thao tác phải thất bại, kết quả chính sách có thể khác. Cần thiết kế trước, không để một lỗi ngẫu nhiên trong advice tự quyết định thứ tự ưu tiên.

## 6. Lỗi trong after/finally advice: chuyện “mới” có thể che chuyện “cũ”

Một after/finally advice thường nhằm dọn dẹp hoặc ghi nhận khi phần được quan sát kết thúc. Nhưng **finally không có nghĩa là được phép ném ngoại lệ không kiểm soát**.

Ví dụ Java thông thường:

```java
static void example() {
    try {
        throw new IllegalArgumentException("original");
    } finally {
        throw new IllegalStateException("cleanup");
    }
}
```

Đây là **đoạn mã minh họa**, không phải chương trình độc lập. Nếu chạy, caller nhận `IllegalStateException("cleanup")`; ngoại lệ `IllegalArgumentException("original")` bị che khuất trừ khi được lưu lại ở nơi khác.

Điều tương tự có thể xảy ra khi một advice sau kết thúc ném ngoại lệ trong quá trình nhả tài nguyên, gửi log hoặc cập nhật trạng thái.

Bảng tình huống:

| Phần nghiệp vụ | Advice kết thúc | Kết quả quan sát có thể xảy ra |
| --- | --- | --- |
| Return thành công | Không lỗi | Caller nhận kết quả thành công |
| Return thành công | Ném `CleanupFailure` | Caller nhận lỗi từ advice |
| Ném `OriginalFailure` | Không lỗi | Caller nhận lỗi gốc |
| Ném `OriginalFailure` | Ném `CleanupFailure` | Lỗi cuối có thể che lỗi gốc |
| Không bắt đầu vì before lỗi | Advice ngoài có finally | Advice ngoài có thể chạy khi unwinding |

**Lưu ý:** “after/finally advice” trong một công cụ AOP và khối `finally` trong Java có thể khác về **ranh giới** mà chúng bao quanh. Vì thế hàng cuối phụ thuộc vào advice nào đã được kích hoạt và thuộc lớp bao nào. Không có lời hứa chung rằng mọi after advice đều chạy nếu một before advice khác đã ngăn tiến tới điểm cần can thiệp.

### 6.1. Cleanup cũng có thể có tác dụng phụ

Một advice nhả khóa có thể ném lỗi do cơ sở hạ tầng. Nếu cleanup buộc phải hoàn tất để duy trì bất biến hệ thống, không thể chỉ “bỏ qua ngoại lệ để giữ log đẹp”. Cần phân loại lỗi nghiêm trọng và xây hợp đồng phục hồi phù hợp.

Điểm chung vẫn là **bảo toàn thông tin nguyên nhân** và không đưa quyết định fail-open/fail-closed vào một `catch` tùy tiện.

## 7. Around advice có thể thay đổi toàn bộ đường đi của ngoại lệ

Around advice có quyền điều khiển việc chuyển tiếp tới phần được chọn theo ngữ nghĩa công cụ: gọi tiếp (`proceed`), bắt lỗi, thay đổi giá trị trả về hoặc không chuyển tiếp.

Mã giả trung lập công cụ:

```text
around selectedOperation(context):
    beforeWork(context)
    try:
        result = proceed(context)
        afterSuccessWork(context, result)
        return result
    catch error:
        afterFailureWork(context, error)
        throw error
    finally:
        finalWork(context)
```

Đây là **mã giả AOP**, không phải Java độc lập. Trong mã trên, `catch` bao gồm cả `afterSuccessWork`; nếu after-success tự ném lỗi thì `catch` cũng bắt lỗi đó. Việc gọi `afterFailureWork` vì vậy **không tự chứng minh lỗi bắt được phát sinh từ phần nghiệp vụ gốc**.

Đây là một bẫy quan trọng khi lập trình around advice.

### 7.1. Cần phân biệt nguồn lỗi theo ranh giới

Nếu chính sách yêu cầu `afterFailureWork` chỉ chạy khi **phần được tiếp tục** thất bại, mã giả phải chia phạm vi `try/catch`:

```text
around selectedOperation(context):
    beforeWork(context)
    try:
        result = proceed(context)
    catch operationError:
        afterFailureWork(context, operationError)
        throw operationError

    afterSuccessWork(context, result)
    return result
```

Đoạn thứ hai cho phép phân biệt lỗi `proceed` với lỗi từ `afterSuccessWork`. Dĩ nhiên `proceed` có thể bao gồm **advice ở lớp bên trong**, chứ không nhất thiết chỉ phần thân nghiệp vụ gốc. Muốn phân biệt sâu hơn cần quan sát đúng ranh giới.

### 7.2. Nuốt lỗi để trả fallback chỉ khi hợp đồng cho phép

Mã giả:

```text
around queryOperation(context):
    try:
        return proceed(context)
    catch KnownTransientReadError:
        return cachedFallback
```

Đây có thể là chiến lược hợp lệ cho một phép đọc có fallback rõ ràng. Nhưng với thanh toán, cập nhật dữ liệu hoặc cấp quyền, chuyển mọi ngoại lệ thành `success` có thể đánh lừa caller và phá hợp đồng nghiệp vụ.

Các câu hỏi phải được trả lời: lỗi nào có thể phục hồi, kết quả fallback có đúng kiểu/ý nghĩa, tác dụng phụ đã xảy ra chưa và caller có cần biết sự cố không?

## 8. Ví dụ Java 17 chạy được: sáu đường đi của ngoại lệ

Java thuần không có một cú pháp aspect tích hợp. Để quan sát chắc chắn tác động của các lỗi advice, ví dụ dùng **bộ chặn viết tay** với các hàm mang vai trò before/after-returning/after-throwing/finally. Nó minh họa **luồng điều khiển**, không phải hiện thực của một ngôn ngữ AOP cụ thể và không có pointcut/weaving tự động.

Tạo tệp `AdviceExceptionDemo.java`:

```java
public class AdviceExceptionDemo {
    interface Service {
        String process(String mode);
    }

    static final class BusinessService implements Service {
        @Override
        public String process(String mode) {
            System.out.println("business:" + mode);
            if ("business-fail".equals(mode) || "audit-fail".equals(mode)) {
                throw new IllegalArgumentException("business failed");
            }
            return "OK:" + mode;
        }
    }

    static void before(String mode) {
        System.out.println("before:" + mode);
        if ("before-fail".equals(mode)) {
            throw new SecurityException("blocked by advice");
        }
    }

    static void afterReturning(String mode, String result) {
        System.out.println("afterReturning:" + mode);
        if ("after-return-fail".equals(mode)) {
            throw new IllegalStateException("after failed");
        }
    }

    static void afterThrowing(String mode, RuntimeException original) {
        System.out.println("afterThrowing:" + mode
                + ":" + original.getClass().getSimpleName());
        if ("audit-fail".equals(mode)) {
            throw new IllegalStateException("audit failed");
        }
    }

    static void afterFinally(String mode) {
        System.out.println("finally:" + mode);
        if ("cleanup-fail".equals(mode)) {
            throw new IllegalStateException("cleanup failed");
        }
    }

    static String intercepted(Service target, String mode) {
        try {
            before(mode);

            String result;
            try {
                result = target.process(mode);
            } catch (RuntimeException original) {
                afterThrowing(mode, original);
                throw original;
            }

            afterReturning(mode, result);
            return result;
        } finally {
            afterFinally(mode);
        }
    }

    public static void main(String[] args) {
        Service service = new BusinessService();
        String[] modes = {
                "ok", "before-fail", "business-fail",
                "after-return-fail", "audit-fail", "cleanup-fail"
        };

        for (String mode : modes) {
            System.out.println("case:" + mode);
            try {
                String result = intercepted(service, mode);
                System.out.println("caller:result:" + result);
            } catch (RuntimeException error) {
                System.out.println("caller:error:"
                        + error.getClass().getSimpleName()
                        + ":" + error.getMessage());
            }
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac AdviceExceptionDemo.java
java AdviceExceptionDemo
```

Đầu ra mong đợi:

```text
case:ok
before:ok
business:ok
afterReturning:ok
finally:ok
caller:result:OK:ok
case:before-fail
before:before-fail
finally:before-fail
caller:error:SecurityException:blocked by advice
case:business-fail
before:business-fail
business:business-fail
afterThrowing:business-fail:IllegalArgumentException
finally:business-fail
caller:error:IllegalArgumentException:business failed
case:after-return-fail
before:after-return-fail
business:after-return-fail
afterReturning:after-return-fail
finally:after-return-fail
caller:error:IllegalStateException:after failed
case:audit-fail
before:audit-fail
business:audit-fail
afterThrowing:audit-fail:IllegalArgumentException
finally:audit-fail
caller:error:IllegalStateException:audit failed
case:cleanup-fail
before:cleanup-fail
business:cleanup-fail
afterReturning:cleanup-fail
finally:cleanup-fail
caller:error:IllegalStateException:cleanup failed
```

### 8.1. Tại sao sáu ca có kết quả khác nhau?

| Ca | Mã nghiệp vụ có chạy? | Nguồn lỗi (nếu có) | Caller nhận |
| --- | --- | --- | --- |
| `ok` | Có | Không | Kết quả `OK:ok` |
| `before-fail` | **Không** | Before advice | `SecurityException` |
| `business-fail` | Có | Nghiệp vụ | `IllegalArgumentException` |
| `after-return-fail` | Có và đã trả kết quả nội bộ | After-returning advice | `IllegalStateException` |
| `audit-fail` | Có và đã ném lỗi gốc | After-throwing advice | `IllegalStateException` thay lỗi gốc |
| `cleanup-fail` | Có và đã trả kết quả nội bộ | Finally advice | `IllegalStateException` |

Chú ý `finally:before-fail`: trong ví dụ, **toàn bộ hàm `intercepted` được bọc bởi một khối `finally` của Java**, kể cả before. Không được suy từ đó rằng mọi after/finally advice của mọi engine AOP đều chạy khi một before advice khác ném lỗi; mỗi loại advice có ranh giới riêng.

Tương tự, `afterThrowing` ở mã này chỉ bắt ngoại lệ từ `target.process`, không bắt ngoại lệ của `afterReturning`. Đây là **thiết kế rõ ranh giới nhằm minh họa nguồn lỗi**; cách phân lớp của engine AOP thực sẽ tùy mô hình và thứ tự precedence.

### 8.2. Vì sao `audit-fail` làm mất lỗi gốc?

Trong `afterThrowing`, ta cố tình ném `new IllegalStateException("audit failed")` mà **không giữ liên hệ** đến `original`. Sau đó `throw original` trong `intercepted` không chạy được vì advice đã ném trước.

Ở hệ thống thật, mất liên hệ tới `IllegalArgumentException("business failed")` khiến điều tra sự cố khó hơn. Không nên xây handling production theo mẫu mất dấu này; nó là **phản ví dụ để kiểm chứng tác hại**.

### 8.3. Điều gì không được suy từ ví dụ?

Không nên khẳng định mọi before/after/around advice dùng đúng thứ tự hoặc cú pháp như các hàm Java trên. Ví dụ chỉ minh họa **khối điều khiển tương đương** và cách Java truyền ngoại lệ qua `try/catch/finally`. Nếu cần hành vi chính xác của một công cụ AOP, phải kiểm tra loại join point, cú pháp advice, ưu tiên, quy tắc checked exceptions và phạm vi weaving của chính công cụ đó.

## 9. Phân biệt “throw”, “rethrow”, “wrap”, “suppress” và “swallow”

Khi advice gặp ngoại lệ, có nhiều cách xử lý. Tên các cách này nên dùng chính xác:

| Cách | Hành vi | Rủi ro/ý nghĩa |
| --- | --- | --- |
| **Throw new** | Tạo lỗi mới từ advice | Caller có thể thấy lỗi advice thay vì lỗi gốc |
| **Rethrow original** | Ném lại cùng đối tượng ngoại lệ gốc | Giữ kiểu và cause gốc, không nhất thiết giữ được mọi ngữ cảnh |
| **Wrap with cause** | Tạo ngoại lệ mới có `cause` là ngoại lệ gốc | Đổi hợp đồng lỗi nhưng vẫn liên kết nguyên nhân |
| **Add suppressed** | Gắn lỗi thứ cấp với lỗi chính | Giữ thứ tự ưu tiên nguyên nhân và thông tin lỗi phụ |
| **Swallow** | Bắt lỗi rồi bỏ qua | Có thể chuyển lỗi thành thành công giả hoặc làm mất dấu sự cố |
| **Return fallback** | Biến lỗi thành kết quả dự phòng | Chỉ đúng nếu hợp đồng và tính an toàn cho phép |

Ví dụ Java độc lập trong phạm vi một phương thức:

```java
try {
    runOriginal();
} catch (RuntimeException original) {
    throw new IllegalStateException("operation failed", original);
}
```

Đây là **đoạn minh họa**, giả sử có phương thức `runOriginal()`. Caller nhận `IllegalStateException`, nhưng `getCause()` trỏ tới lỗi gốc. Việc wrap là chủ động thay đổi kiểu ngoại lệ, nên phải có lý do rõ.

**Một phân biệt kỹ thuật:** `Throwable.addSuppressed(secondary)` **không** thay đổi cause của lỗi chính và **không** tự ném lại lỗi; nó chỉ bổ sung dữ liệu chẩn đoán. Ta vẫn cần ném lại lỗi chính nếu đó là hợp đồng mong muốn.

## 10. Giữ lỗi gốc khi công việc quan sát thất bại

Khi nghiệp vụ đã thất bại mà advice ghi log/audit phụ trợ cũng thất bại, thường có hai mục tiêu:

1. Không để lỗi phụ trợ **che nguyên nhân gốc**.
2. Không làm mất thông tin rằng hệ thống phụ trợ cũng bị lỗi.

Một chiến lược tổng quát:

```text
try:
    performOriginal()
catch original:
    try:
        reportFailure(original)
    catch reportingError:
        attachSecondaryError(original, reportingError)
    throw original
```

Đây là **mã giả**, cần điều chỉnh theo chính sách và công cụ.

Trong Java, có thể minh họa bằng hàm sau (đoạn phụ trợ, không phải chương trình độc lập):

```java
static void callPreservingPrimary() {
    try {
        throw new IllegalArgumentException("original failed");
    } catch (RuntimeException original) {
        try {
            throw new IllegalStateException("audit failed");
        } catch (RuntimeException audit) {
            original.addSuppressed(audit);
        }
        throw original;
    }
}
```

Caller nhận `IllegalArgumentException`; `getSuppressed()` có `IllegalStateException` từ audit. Việc ghi suppressed là quyết định thiết kế: không được coi mọi lỗi phụ trợ đều có thể tiếp tục an toàn, nhất là khi chính sách bảo mật hoặc kiểm toán bắt buộc yêu cầu từ chối hoạt động.

### 10.1. Không dùng một catch quá rộng cho mọi tình huống

Bắt `Throwable` một cách tùy tiện có thể bao gồm các lỗi nghiêm trọng không nên chuyển thành một kết quả bình thường; bắt `Exception` quá rộng có thể nuốt những loại lỗi mà hệ thống chưa có chiến lược phục hồi.

Phải chọn kiểu ngoại lệ tương thích với hợp đồng nghiệp vụ và nền tảng. Đừng dùng `catch` trống chỉ để "giữ cho hệ thống chạy tiếp": nó làm mất dấu sự cố và có thể vi phạm yêu cầu vận hành.

### 10.2. Cẩn thận khi tự thêm suppressed

Không được tự suppress một ngoại lệ vào chính nó; trong Java, `addSuppressed` không cho phép self-suppression. Cần kiểm tra quan hệ các đối tượng lỗi và không lặp gắn cùng một lỗi không cần thiết.

Trong nhiều trường hợp, chuẩn `try-with-resources` đã hỗ trợ suppressed cho lỗi khi đóng tài nguyên: không cần viết lại cơ chế thủ công trừ khi có ràng buộc thực sự khác.

## 11. Ví dụ Java 17 về primary và suppressed exceptions

Ví dụ độc lập dưới đây minh họa cách **Java tự giữ lỗi chính** khi một `AutoCloseable.close()` cũng thất bại. Đây không phải một aspect tự động; cơ chế này hữu ích để hiểu cách quản lý lỗi từ cleanup do advice hoặc nghiệp vụ điều phối.

Tạo `SuppressedExceptionDemo.java`:

```java
public class SuppressedExceptionDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("cleanup:close");
            throw new IllegalStateException("close failed");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("business:run");
            throw new IllegalArgumentException("business failed");
        } catch (RuntimeException error) {
            System.out.println("caller:primary:"
                    + error.getClass().getSimpleName()
                    + ":" + error.getMessage());

            for (Throwable secondary : error.getSuppressed()) {
                System.out.println("caller:suppressed:"
                        + secondary.getClass().getSimpleName()
                        + ":" + secondary.getMessage());
            }
        }
    }
}
```

Chạy:

```bash
javac SuppressedExceptionDemo.java
java SuppressedExceptionDemo
```

Kết quả:

```text
business:run
cleanup:close
caller:primary:IllegalArgumentException:business failed
caller:suppressed:IllegalStateException:close failed
```

Khi có lỗi trong thân `try`, cơ chế `try-with-resources` của Java **giữ ngoại lệ chính** và gắn lỗi đóng tài nguyên vào suppressed. Một `finally` thủ công ném lỗi mới không tự động làm điều này.

**Bài học dành cho aspect:** nếu advice thực hiện cleanup có khả năng thất bại, hãy chủ động thiết kế chính sách xác định **lỗi nào là chính**, **lỗi nào là phụ** và **caller cần nhìn thấy gì**. Không nên suy rằng mọi engine AOP tự quản lý suppressed như `try-with-resources`.

## 12. Ngoại lệ checked và unchecked khi advice can thiệp

Java phân biệt **checked exceptions** (thường phải khai báo hoặc xử lý) và **unchecked exceptions** (`RuntimeException` cùng các lớp con; `Error` là nhánh unchecked khác). Điều này ảnh hưởng đến điều gì một advice được phép ném qua join point.

Ví dụ:

```java
interface Lookup {
    String find(String id);
}
```

Nếu chữ ký `find` không khai báo một checked exception như `java.io.IOException`, việc chèn một advice ném checked exception ấy qua cùng ranh giới **có thể không hợp lệ hoặc bị biến đổi/bọc** tùy ngôn ngữ AOP, công cụ weaving, proxy và hợp đồng của phương thức.

Một số ngôn ngữ AOP có quy tắc kiểm tra **checked exceptions của advice** tương thích với chữ ký join point. Một số cơ chế proxy dùng reflection có thể có quy tắc riêng về việc bọc checked exception không khai báo. Vì vậy **không có quy tắc chung** rằng mọi advice đều ném được mọi loại checked exception mà caller sẽ nhìn thấy nguyên dạng.

Các khuyến nghị:

- Không để một advice chỉ phục vụ telemetry bất ngờ đưa thêm checked exception vào API đã công bố.
- Khi cần wrap lỗi thành unchecked, giữ `cause` nếu phù hợp và mô tả thay đổi hợp đồng.
- Khi advice kiểm soát nghiệp vụ có quyền từ chối thao tác, dùng loại lỗi ổn định, được caller hiểu rõ.
- Kiểm thử dưới đúng cơ chế weaving/interception, không chỉ với Java helper mô phỏng.

### 12.1. Vì sao `Error` cần đối xử riêng?

Các lỗi cấp môi trường như thiếu bộ nhớ hoặc lỗi liên kết không phải ngoại lệ nghiệp vụ bình thường. Đừng áp dụng một `catch(Throwable)` để âm thầm biến mọi thứ thành thành công. Cách xử lý phải tôn trọng tình trạng còn hoạt động được của tiến trình và hợp đồng nền tảng.

## 13. Nhiều aspect và thứ tự ưu tiên: ai thấy lỗi của ai?

Khi nhiều advice áp dụng tại cùng join point, nên hình dung các **lớp bao quanh**:

```text
Caller
   |
   v
OuterAudit.around
   |
   v
InnerMetrics.around
   |
   v
BusinessOperation
   |
   v
InnerMetrics kết thúc
   |
   v
OuterAudit kết thúc
   |
   v
Caller
```

Trong một cấu hình có thứ tự này:

```text
OuterAudit(InnerMetrics(BusinessOperation))
```

Nếu `InnerMetrics` ném `MetricFailure` sau khi nghiệp vụ trả kết quả, `OuterAudit` có thể nhìn thấy `MetricFailure` như một lỗi của phần `proceed` mà nó bao quanh, **dù thân nghiệp vụ đã thành công**.

Ngược lại, nếu `OuterAudit` ném lỗi sau khi lớp bên trong trả về, một advice nằm hoàn toàn bên trong không thể tự quan sát sự kiện xảy ra về sau ở lớp ngoài.

Từ đó:

1. Một after throwing advice ở **ranh giới ngoài** có thể nhìn thấy lỗi advice ở lớp trong, tùy thứ tự thực tế.
2. Không nên kết luận “đã thấy after throwing ⇒ nghiệp vụ gốc thất bại”.
3. Thứ tự advice có thể ảnh hưởng lỗi được nhìn thấy và liệu phần gốc có được chạy không.
4. Phải xác minh quy tắc ưu tiên riêng của công cụ; thứ tự khai báo trong file không luôn là thứ tự có hiệu lực.

### 13.1. Trường hợp hai advice cùng ném lỗi

Giả sử business ném `B`, advice trong ném `I`, advice ngoài ném `O`. Nếu mỗi lớp thay ngoại lệ đang được lan truyền bằng ngoại lệ của mình, caller cuối cùng có thể chỉ thấy `O`. Nhưng nếu các lớp giữ `cause` hoặc suppressed, chuỗi lỗi có thể chứa `B` và `I`.

Đừng cố suy diễn một thứ tự cố định cho mọi loại advice; hãy vẽ chuỗi quanh điểm được chọn và kiểm thử từng đường thoát.

## 14. Retry và lỗi advice: nguy cơ lặp side effect

Một around advice có thể thử lại `proceed` khi có lỗi:

```text
around operation:
    try:
        return proceed()
    catch TemporaryFailure:
        return proceed()
```

Đây là mã giả; cơ chế cụ thể phải cho phép gọi lại `proceed`.

Nhưng nếu lỗi đầu tiên **xuất hiện sau khi business đã hoàn tất** — ví dụ từ metrics after-returning của một advice ở bên trong — retry ở lớp ngoài có thể gọi lại **toàn bộ chuỗi**, bao gồm nghiệp vụ đã có tác dụng phụ.

Ví dụ chuyển tiền:

```text
Lần 1: transfer thành công -> advice ghi metric lỗi
Retry quanh chuỗi
Lần 2: transfer được thực hiện lần nữa
```

Đây là mối nguy lớn: **lỗi kỹ thuật của advice không chứng minh thao tác nghiệp vụ an toàn để thử lại**.

Cần có:

- Phân loại lỗi theo **nguồn** và **giai đoạn**.
- Ràng buộc retry chỉ với thao tác được xác định có thể thử lại.
- Idempotency key và cơ chế chống lặp khi có side effect.
- Giới hạn số lần thử và chính sách backoff nếu cần.
- Kiểm thử “business thành công nhưng advice lỗi” chứ không chỉ “business ném lỗi”.

## 15. Giao dịch và tính nguyên tử: lỗi advice không đồng nghĩa rollback

Lỗi xảy ra trong advice có thể đi qua ranh giới giao dịch, nhưng tác động phụ thuộc vào cách ứng dụng quản lý giao dịch:

- Advice lỗi **trước** khi bắt đầu công việc: phần nghiệp vụ chưa chạy.
- Advice lỗi **trong** một giao dịch đang mở: có thể khiến giao dịch bị đánh dấu thất bại nếu cơ chế giao dịch và xử lý lỗi quy định vậy.
- Advice lỗi **sau khi commit** hoặc sau khi hệ thống ngoài đã xác nhận: dữ liệu có thể đã tồn tại, bất chấp caller nhận ngoại lệ.
- Advice ghi audit ở **kho dữ liệu riêng** có thể không tham gia cùng giao dịch với dữ liệu nghiệp vụ.

Không có bảo đảm AOP chung rằng một advice ném `RuntimeException` sẽ tự hoàn tác mọi thay đổi, nhất là đối với I/O mạng, email, hàng đợi hoặc hệ thống phân tán.

Nếu đòi hỏi nhất quán giữa nghiệp vụ và audit, cần thiết kế ranh giới giao dịch, outbox hoặc một cơ chế phối hợp đáng tin thay vì dựa vào việc ném exception.

## 16. Đường gọi đồng bộ và bất đồng bộ có ranh giới lỗi khác nhau

Với hàm đồng bộ, advice có thể ném lỗi trước khi phương thức trả về và caller bắt trực tiếp tại lời gọi.

Nhưng với hàm trả future hoặc handle:

```text
Caller -> startTask() -> Future được trả về
                         |
                         +-- công việc thực chạy về sau
                             -> Future success / failure
```

Các tình huống khác nhau:

1. **Before advice ném lỗi đồng bộ:** `startTask()` có thể không trả future.
2. **After returning advice ném lỗi:** phương thức gốc có thể đã tạo/lên lịch công việc rồi, nhưng caller không nhận được future như mong đợi.
3. **Công việc bất đồng bộ thất bại về sau:** lỗi có thể được lưu trong trạng thái future/completion, không thoát trực tiếp ở method return.
4. **Advice hoặc callback gắn vào completion ném lỗi:** trạng thái của stage phụ thuộc cách callback được nối vào pipeline và hợp đồng thư viện.

Không được mặc định một after throwing advice trên **method execution của phương thức tạo future** sẽ nhìn thấy mọi lỗi xảy ra về sau trong tác vụ. Cần chọn ranh giới hoàn tất phù hợp và xử lý truyền ngữ cảnh qua luồng/tác vụ.

### 16.1. Lỗi ở callback quan sát

Một callback dùng để ghi log lỗi của future có thể tự ném lỗi. Theo API bất đồng bộ cụ thể, nó có thể khiến **một completion stage mới** thất bại hoặc được xử lý theo quy tắc callback. Điều quan trọng là không lẫn lỗi callback với lỗi tác vụ ban đầu.

Khi kiểm thử, giữ riêng định danh `taskId`, lỗi tác vụ và lỗi hệ thống quan sát. Chỉ kết luận kết quả khi đã xác định stage nào caller thực sự chờ/nhận.

## 17. Thiết kế hợp đồng exception của aspect

Một aspect được dùng ở nhiều chỗ nên có chính sách lỗi thành văn thay vì để logic phụ trợ tự xử lý theo thói quen.

### 17.1. Ma trận chính sách gợi ý

| Mối quan tâm | Nếu advice lỗi | Định hướng kiểm thử |
| --- | --- | --- |
| Metrics tùy chọn | Có thể ghi nhận lỗi thứ cấp và giữ lỗi/kết quả nghiệp vụ | Metrics hỏng không đổi hợp đồng |
| Logging chẩn đoán | Hạn chế tác động, không log dữ liệu nhạy cảm | Logger lỗi hoặc đầy đĩa |
| Audit bắt buộc | Theo chính sách fail-closed/fail-open đã xác định | Từ chối đúng ranh giới, không che lỗi |
| Kiểm tra quyền | Chủ động từ chối khi điều kiện không đạt | Target không chạy |
| Cleanup tài nguyên | Không làm mất nguyên nhân gốc nếu đã có | Primary/suppressed/cause |
| Retry | Chỉ retry lỗi được phân loại và thao tác an toàn | Business đã thành công nhưng advice sau lỗi |
| Dịch ngoại lệ | Chuyển đổi có chủ đích, giữ cause | Caller nhận đúng kiểu thông báo |

Bảng không phải một tập quy tắc bắt buộc cho mọi hệ thống. Ví dụ, dữ liệu audit bắt buộc có thể có yêu cầu không được mất bản ghi; bỏ qua lỗi audit lúc đó là vi phạm chính sách.

### 17.2. Hợp đồng cho caller nên nói gì?

Tài liệu API hoặc thiết kế hệ thống nên làm rõ:

- Những lỗi từ điều kiện nghiệp vụ và những lỗi từ cơ sở hạ tầng có thể xảy ra.
- Khi nhận lỗi, tác dụng phụ đã xảy ra hay chưa và cách kiểm tra trạng thái.
- Caller có được retry không, và nếu có, dùng idempotency key nào.
- Lỗi gốc được giữ bằng `cause`, suppressed, error code hay trace ID như thế nào.
- Trường hợp nào advice có thể chủ động từ chối thao tác.

Nếu caller không thể phân biệt “chưa chạy” với “đã chạy nhưng post-processing lỗi”, hệ thống rất dễ có hành vi thử lại nguy hiểm.

## 18. Ghi nhận ngoại lệ an toàn và hữu ích

Một aspect ghi lỗi nên thu thập đủ dữ liệu để truy vết mà không tạo lỗi phụ không cần thiết.

Thông tin thường hữu ích:

- Loại join point và chữ ký của điểm được chọn.
- Một correlation ID phù hợp với yêu cầu/tác vụ.
- Giai đoạn lỗi: before, business/proceed, after returning, after throwing, finally.
- Kiểu ngoại lệ, thông điệp đã loại thông tin nhạy cảm.
- Cause và suppressed nếu phù hợp.
- Tình trạng tác dụng phụ khi hệ thống có thể xác nhận.
- Thời gian và định danh lần gọi.

Không nên `toString()` toàn bộ tham số/đối tượng trong một advice xử lý lỗi: phương thức `toString()` cũng có thể ném ngoại lệ, lộ thông tin nhạy cảm hoặc gây thêm I/O. Ngay cả thao tác ghi log cũng cần mức phòng thủ phù hợp với tầm quan trọng của hệ thống.

### 18.1. Không làm lỗi ghi log đệ quy qua pointcut

Nếu advice xử lý lỗi bằng cách gọi một logger mà chính logger cũng khớp pointcut đang áp dụng, chuỗi sau có thể xảy ra:

```text
business fails
   -> error advice
       -> logger.log()
           -> same pointcut
               -> error advice / logger...
```

Cần xác định phạm vi pointcut và biện pháp tránh tái nhập. Biện pháp không nên là một cờ global bất cẩn, vì nó có thể vô hiệu hóa advice của những invocation khác đang chạy đồng thời.

## 19. Cách kiểm thử tác động exception của advice

Đừng chỉ kiểm thử “advice có chạy” hoặc “caller nhận exception”. Cần kiểm tra **đúng nguồn**, **đúng số lần chạy nghiệp vụ**, **đúng thứ tự** và **đúng thông tin nguyên nhân**.

| Trường hợp | Business chạy? | Điều caller cần nhận theo hợp đồng |
| --- | --- | --- |
| Before bình thường, business thành công | Một lần | Kết quả nghiệp vụ |
| Before ném lỗi chủ động | Không | Lỗi từ chối đúng loại |
| Before logging lỗi ngoài ý muốn | Tùy chính sách | Không mất thông tin và không phá hợp đồng vô cớ |
| Business ném lỗi | Một lần | Lỗi gốc hoặc lỗi có cause gốc |
| After returning ném lỗi | Business đã chạy | Phân biệt lỗi hậu xử lý với thất bại nghiệp vụ |
| After throwing ném lỗi mới | Business đã lỗi | Cause/suppressed được bảo toàn nếu chính sách yêu cầu |
| Finally ném lỗi sau thành công | Business đã chạy | Nhận biết cleanup là nguồn lỗi |
| Finally ném lỗi khi business cũng lỗi | Business đã lỗi | Giữ lỗi chính và lỗi phụ |
| Hai aspect cùng khớp | Tùy chuỗi advice | Thứ tự và đối tượng lỗi rõ ràng |
| Around nuốt lỗi | Business có thể đã lỗi | Chỉ chấp nhận fallback hợp đồng |
| Around retry | Có thể nhiều lần | Không lặp side effect ngoài ý định |
| Tác vụ bất đồng bộ lỗi sau return | Công việc chạy về sau | Đúng completion boundary |

### 19.1. Kiểm thử số lần chạy nghiệp vụ

Dùng counter hoặc target giả để xác nhận:

- Before advice từ chối: **0 lần**.
- After-returning advice ném lỗi: **1 lần** trước khi caller nhận lỗi.
- Advice retry: xác nhận số lần `proceed`/thực thi gốc đúng với chính sách.
- Advice chain bị chặn bên ngoài: advice trong có thể chưa chạy, dù pointcut kỹ thuật của nó phù hợp.

### 19.2. Kiểm thử primary/cause/suppressed

Không chỉ so sánh message. Hãy kiểm tra:

```java
error.getClass()
error.getCause()
error.getSuppressed()
```

Đây là **ba lời gọi minh họa**, không phải đoạn Java độc lập. Với những trường hợp cần bảo toàn lỗi gốc, hãy dùng `assertSame`/so sánh identity hoặc kiểm tra đúng cause chain phù hợp, thay vì chỉ tìm một chuỗi văn bản trong log.

### 19.3. Kiểm thử đường không được can thiệp

Nếu một aspect chỉ nên áp dụng cho `PaymentService.pay()`, cần có ca âm tính để xác minh nó **không** áp dụng cho helper, logger, method nội bộ hoặc thành phần không thuộc chính sách. Chọn quá rộng có thể làm một lỗi advice lan tới hệ thống không liên quan.

### 19.4. Kiểm thử nhiều luồng

Nếu advice lưu đối tượng `currentError` trong biến dùng chung, hai invocation đồng thời có thể ghi đè nhau. Nên bảo đảm lỗi, correlation ID và thời điểm xử lý gắn với **đúng invocation**, không bị chia sẻ ngoài ý định.

## 20. Những hiểu nhầm cần tránh

**“Advice chỉ chạy bổ sung nên không thể ảnh hưởng kết quả.”** Sai. Một exception từ advice có thể là exception cuối cùng mà caller thấy.

**“Business trả thành công thì caller luôn nhận thành công.”** Sai khi có after-returning/finally advice ném lỗi hoặc around advice thay đổi kết quả.

**“Caller nhận exception nghĩa là business đã rollback.”** Không tự động. Tác dụng phụ, giao dịch và I/O bên ngoài có ranh giới riêng.

**“After throwing advice chắc chắn nhìn thấy mọi lỗi trong ứng dụng.”** Không. Nó chỉ áp dụng tại các join point và ranh giới đã chọn, theo loại lỗi/kiểu advice và khả năng công cụ.

**“Ngoại lệ thấy ở after throwing chắc chắn từ business.”** Không. Một advice ở lớp trong có thể là nguồn lỗi.

**“Dùng finally sẽ tự giữ ngoại lệ gốc.”** Không với `finally` thường nếu cleanup ném lỗi; `try-with-resources` có cơ chế suppressed riêng.

**“Bắt mọi lỗi trong around rồi return null là an toàn.”** Không. Có thể phá hợp đồng kiểu trả về, che sự cố và đánh lừa caller.

**“Retry khi có lỗi nào cũng đúng.”** Không. Lỗi từ advice hậu xử lý có thể xảy ra sau khi nghiệp vụ đã thành công.

**“Checked exception từ advice luôn đi qua caller như unchecked exception.”** Không thể giả định. Java và công cụ AOP có các giới hạn/hợp đồng riêng.

**“Một ca thành công đủ chứng minh xử lý lỗi đúng.”** Không. Cần kiểm thử đường before fail, business fail, post-processing fail, cleanup fail và kết hợp nhiều aspect.

## 21. Bài tập luyện phân tích luồng ngoại lệ

### Bài 1 — Before ném lỗi

`before` kiểm tra quyền ném `AccessDenied`; business chưa được gọi. Caller bắt được gì và bộ đếm thực thi business là bao nhiêu?

**Gợi ý đáp án:** caller nhận lỗi từ before (hoặc lỗi đã được lớp advice ngoài chuyển đổi theo hợp đồng); business được gọi **0 lần** nếu lỗi chặn trước khi chuyển tiếp.

### Bài 2 — After returning ném lỗi

`placeOrder` đã ghi đơn thành công, nhưng after returning ném `MetricsFailure`. Caller nên làm gì trước khi retry?

**Gợi ý đáp án:** xác minh trạng thái đơn và yêu cầu idempotency. Không nên giả định chưa có đơn chỉ vì caller nhận lỗi. Thiết kế error model nên phân biệt lỗi hậu xử lý.

### Bài 3 — Hai ngoại lệ liên tiếp

Business ném `IllegalArgumentException("B")`; after throwing advice ném `IllegalStateException("A")` mà không có cause. Caller thấy gì?

**Gợi ý đáp án:** ở chuỗi giả định lỗi advice được đẩy ra ranh giới ngoài, caller thấy `IllegalStateException("A")`; lỗi B có thể bị che khuất. Nếu dùng `new IllegalStateException("A", original)`, caller có thể truy vết B qua `getCause()`.

### Bài 4 — Finally che lỗi

Một `finally` ném `CleanupError` trong lúc đang lan truyền `OriginalError`. Nếu không dùng cơ chế bảo toàn, lỗi nào đến caller?

**Gợi ý đáp án:** trong Java `finally` thông thường, lỗi cleanup mới có thể thay thế lỗi đang lan truyền. Cần thiết kế primary/suppressed/cause nếu phải giữ cả hai.

### Bài 5 — Around catch quá rộng

Một around advice viết `try { proceed(); logSuccess(); } catch (Exception e) { logBusinessFailure(e); }`. Nếu `logSuccess` ném lỗi thì có gì sai?

**Gợi ý đáp án:** catch cũng bắt lỗi `logSuccess`, khiến hệ thống phân loại sai lỗi advice thành lỗi business. Cần thu hẹp phạm vi catch hoặc gắn rõ nguồn lỗi.

### Bài 6 — Retry nguy hiểm

Một outer advice retry toàn bộ `proceed` khi gặp lỗi. Business hoàn tất, inner advice ném lỗi khi xuất metric. Điều gì có thể xảy ra?

**Gợi ý đáp án:** outer retry có thể thực thi business thêm một lần, tạo side effect trùng. Cần phân loại lỗi và cơ chế idempotency.

### Bài 7 — Lỗi bất đồng bộ

Một phương thức `startTask()` trả `Future` bình thường; task hoàn tất lỗi sau đó. After throwing advice của method execution có chắc nhìn thấy lỗi task không?

**Gợi ý đáp án:** không. Nó quan sát ranh giới method return/throw; lỗi của tác vụ có thể nằm trong Future và xuất hiện ở completion sau đó.

## 22. Checklist thiết kế advice an toàn trước ngoại lệ

- [ ] Đã ghi rõ advice có thể ném những loại lỗi nào và theo chính sách gì.
- [ ] Đã phân biệt lỗi từ before, business/proceed, after returning, after throwing và cleanup.
- [ ] Đã biết thời điểm business có thể đã tạo side effect.
- [ ] Đã xác định lỗi nào là primary khi nhiều tầng cùng thất bại.
- [ ] Có chính sách giữ cause/suppressed thay vì vô tình che lỗi gốc.
- [ ] Không catch rộng hoặc nuốt lỗi mà không có hợp đồng phục hồi.
- [ ] Không retry thao tác có side effect chỉ vì lỗi hậu xử lý.
- [ ] Đã kiểm tra giới hạn checked exception theo công cụ AOP và chữ ký Java.
- [ ] Đã xác định thứ tự và ranh giới khi nhiều aspect cùng khớp.
- [ ] Đã kiểm thử cả đường thành công, before fail, business fail, after fail và finally fail.
- [ ] Đã kiểm tra các đường gọi ngoài phạm vi weaving hoặc qua proxy nếu có.
- [ ] Đã kiểm tra bối cảnh đồng thời, reentrancy và bất đồng bộ nếu liên quan.
- [ ] Telemetry không vô tình làm lộ dữ liệu nhạy cảm hoặc phá nghiệp vụ.
- [ ] Caller có hướng xử lý khi nhận lỗi nhưng side effect có thể đã xảy ra.

## 23. Kết luận

**Advice có thể thay đổi kết quả quan sát của một lời gọi bằng cách ném ngoại lệ, kể cả khi mã nghiệp vụ gốc không ném lỗi.** Vị trí phát sinh quyết định tác động: trước thao tác có thể ngăn phần gốc chạy; sau khi trả về có thể đổi thành công thành thất bại; trên nhánh lỗi hoặc lúc dọn dẹp có thể che ngoại lệ gốc.

Muốn dùng AOP an toàn cần **xác định đúng ranh giới**, **giữ nguyên nhân gốc khi phù hợp**, **phân loại lỗi theo nguồn**, **kiểm soát retry và side effect**, và **kiểm thử toàn bộ chuỗi advice**, không chỉ kiểm thử riêng từng phương thức. Đó là khác biệt giữa một aspect chỉ tiện lợi trên sơ đồ và một aspect đáng tin cậy khi chạy trong hệ thống thực.

### Tài liệu tham khảo để đối chiếu ngữ nghĩa của một công cụ AOP

- [AspectJ Programming Guide — Advice](https://eclipse.dev/aspectj/doc/released/progguide/semantics-advice.html)
- [AspectJ Programming Guide — The AspectJ Language](https://eclipse.dev/aspectj/doc/latest/progguide/language.html)

Các liên kết trên giúp tra cứu định nghĩa và giới hạn của một công cụ cụ thể. Những sơ đồ và ví dụ Java thuần trong bài dùng để giải thích **nguyên lý AOP tổng quát**, không ngụ ý mọi engine AOP có cùng API hay thứ tự chạy.
