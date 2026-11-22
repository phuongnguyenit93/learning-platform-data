# Quan hệ thứ tự giữa advice trước, sau và khi có lỗi trong phối hợp nhiều aspect

## 1. Mục tiêu của bài học

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)**, một **aspect** đóng gói hành vi xuyên suốt như kiểm toán, kiểm tra quyền, logging, đo thời gian, retry và điều phối giao dịch. **Pointcut** chọn các **join point** thuộc mô hình thực thi được công cụ AOP hỗ trợ; **advice** xác định việc cần làm tại điểm đã chọn.

Khi **nhiều aspect cùng áp dụng tại một join point**, chỉ biết “advice A và advice B đều khớp” là chưa đủ. Thứ tự hiệu lực có thể quyết định:

- Ai được kiểm tra quyền trước?
- Advice nào quan sát kết quả nghiệp vụ gốc và advice nào chỉ thấy kết quả đã biến đổi?
- Logging xảy ra trước hay sau khi một advice khác chuyển đổi exception?
- Một before advice ném lỗi có ngăn một advice khác chạy không?
- After returning, after throwing và after/finally chạy trong nhánh nào?
- Một after advice tự ném lỗi có thể khiến caller nhận gì?
- Advice bên ngoài có thấy lỗi phát sinh từ advice bên trong không?
- Một around advice không gọi tiếp có làm mất những advice dự kiến không?

Bài này cung cấp một **mô hình suy luận theo lớp bao (nested execution)**, các bảng đường đi thành công/thất bại, ví dụ Java 17 độc lập và chiến lược kiểm thử. **Không có một thứ tự cố định áp dụng cho mọi công cụ AOP**; khi nói về một quy tắc precedence riêng, bài nêu rõ ngữ cảnh công cụ.

## 2. Thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa | Ảnh hưởng tới thứ tự |
| --- | --- | --- |
| **Join point** | Điểm/sự kiện mà cơ chế AOP có thể can thiệp | Xác định ranh giới cùng được advice |
| **Pointcut** | Quy tắc chọn join point | Nhiều pointcut có thể cùng khớp |
| **Before advice** | Hành vi trước phần tiếp tục | Có thể chặn phần bên trong nếu ném lỗi |
| **After returning advice** | Hành vi trên đường hoàn tất bình thường | Chỉ chạy khi phần được quan sát trả bình thường theo ngữ nghĩa của nó |
| **After throwing advice** | Hành vi trên đường thoát bằng lỗi phù hợp | Có thể thấy lỗi nghiệp vụ hoặc lỗi từ tầng advice trong |
| **After/finally advice** | Hành vi ở điểm kết thúc | Thường có vai trò tương tự finally tại ranh giới được bao |
| **Around advice** | Bao quanh và điều khiển phần được tiếp tục | Có thể gọi, bỏ qua, gọi lại hoặc biến đổi kết quả nếu công cụ cho phép |
| **Precedence/priority** | Quan hệ ưu tiên giữa các advice/aspect | Xác định ai bao ai và ai chạy trước ở từng giai đoạn |
| **Proceed/continuation** | Chuyển điều khiển tới phần có thứ tự thấp hơn hoặc thao tác gốc | Quyết định có tới phần nghiệp vụ hay không |
| **Caller** | Mã ngoài quan sát return hoặc exception | Chỉ thấy kết quả sau các lớp advice |

**Ưu tiên cao hơn** không có nghĩa “mọi đoạn mã của aspect đó luôn chạy sớm hơn mọi đoạn mã của aspect ưu tiên thấp”. Trong mô hình bao quanh, **phần vào** có thể đi từ ngoài vào trong, còn **phần kết thúc** trở ra từ trong ra ngoài.

## 3. Mô hình xếp lớp: chìa khóa để hiểu thứ tự

Giả sử hai aspect cùng áp dụng cho thao tác `placeOrder()`:

- **Aspect A** ở lớp ngoài.
- **Aspect B** ở lớp trong.
- `BusinessOperation` là phần xử lý cuối.

Sơ đồ:

```text
Caller
  |
  v
Aspect A: enter / before
  |
  v
Aspect B: enter / before
  |
  v
BusinessOperation
  |
  v
Aspect B: after / exit
  |
  v
Aspect A: after / exit
  |
  v
Caller
```

Biểu thức tư duy:

```text
A(B(BusinessOperation))
```

Khi mọi tầng **chuyển tiếp bình thường**, thứ tự điển hình là:

```text
A.before
B.before
business
B.afterReturning
B.afterFinally
A.afterReturning
A.afterFinally
```

Nhưng không được đọc dòng trên như một đặc tả chung cho mọi DSL. Đó là **một chuỗi minh họa có thứ tự A ngoài, B trong**, mỗi lớp có các hook nhất định. Một công cụ có thể đặt một advice ở ranh giới khác hoặc có quy tắc precedence riêng.

### 3.1. Phân biệt thứ tự “đi vào” và “đi ra”

Hình dung `A` và `B` như hai cặp ngoặc:

```text
A.before (
    B.before (
        business()
    ) B.after
) A.after
```

Phần before xuất hiện theo hướng **ngoài → trong**. Phần after xuất hiện theo hướng **trong → ngoài**. Đây là một tính chất của **lồng nhau có thứ tự xác định**, không đơn thuần là danh sách các hàm chạy nối đuôi nhau.

### 3.2. Khi có ba aspect

Với `Security(Audit(Metrics(Business)))`:

```text
Security.before
Audit.before
Metrics.before
Business
Metrics.after
Audit.after
Security.after
```

Nếu `Security.before` từ chối trước khi tiếp tục, `Audit`, `Metrics` và `Business` có thể không được vào. Nhưng cleanup hoặc after của **một lớp ngoài đã bắt đầu bao quanh đường đi** vẫn có thể chạy tùy phạm vi của nó.

## 4. Before advice: thứ tự và quyền chặn phần tiếp tục

**Before advice** chạy trước phần mà nó quan sát. Nếu có nhiều before advice, công cụ có thể dùng precedence để quyết định thứ tự.

Trong một mô hình thứ tự ưu tiên:

```text
A.before -> B.before -> business
```

Nếu `A.before` ném `AccessDenied`:

```text
A.before -> throw AccessDenied
            B.before: chưa chạy
            business: chưa chạy
```

Nếu `B.before` ném lỗi:

```text
A.before
B.before -> throw ValidationFailure
            business: chưa chạy
            A.outerCatch/outerFinally: có thể quan sát khi unwinding
```

**Hai lưu ý:**

1. Việc một before advice ném lỗi có ngăn advice khác hay không phụ thuộc **vị trí thực tế trong chain**.
2. Không thể khẳng định “mọi after advice đều chạy dù before đầu tiên thất bại”. Nếu phần mà after bao chưa được bắt đầu, hook đó có thể không có cơ hội chạy.

### 4.1. Before được dùng để từ chối có chủ đích

Một advice bảo mật có thể phải chặn thao tác trước khi mã nghiệp vụ thực thi. Khi đó **sự vắng mặt của log business** là đúng. Kiểm thử cần xác minh target chạy **0 lần**, không chỉ assert loại exception.

### 4.2. Before chỉ dùng telemetry phải xử lý lỗi riêng

Nếu before chỉ ghi metric nhưng chính metric client ném lỗi, nó có thể làm gián đoạn nghiệp vụ ngoài ý định. Chính sách có thể yêu cầu:

- Metrics tùy chọn: giữ đường nghiệp vụ, báo lỗi phụ trợ an toàn.
- Audit bắt buộc: có thể fail-closed nếu không ghi được chứng cứ cần thiết.
- Kiểm soát quyền: lỗi kiểm tra không được mặc định chuyển thành “cho phép”.

Đây là quyết định thiết kế, không tự suy từ loại advice.

## 5. After returning: chạy sau khi phần được quan sát trả bình thường

Một **after returning advice** gắn với đường kết thúc **bình thường**. Nếu phần tiếp tục ném lỗi phù hợp, advice này thường **không chạy** cho đường thất bại đó.

Trong mô hình `A(B(Business))` thành công:

```text
A.before
B.before
Business -> return "OK"
B.afterReturning
A.afterReturning
Caller -> "OK"
```

Nếu business ném lỗi và không có tầng trong nào phục hồi, hai after returning trong mô hình trên sẽ không chạy.

### 5.1. “Trả bình thường” là tương đối theo lớp

Ví dụ:

```text
A(
    B(
        Business -> throw KnownFailure
    )
)
```

Nếu `B.around` bắt `KnownFailure` và trả giá trị fallback hợp lệ, thì từ góc nhìn `A`, `proceed` đã **trả bình thường**. Lúc đó after returning ở lớp ngoài **có thể chạy**, dù thân nghiệp vụ ban đầu ném exception.

Vì vậy đừng khẳng định “after returning chạy thì business chắc chắn thành công ở tầng gốc”. Nó chỉ cho biết **đường được advice đó quan sát** trả bình thường theo ngữ nghĩa engine.

### 5.2. After returning có thể tự thất bại

Giả sử business đã tạo đơn và trả ID, sau đó advice đo metric ném `MetricFailure`. Caller có thể nhận exception thay vì order ID, dù side effect đã xảy ra.

Đây là rủi ro quan trọng với retry: **caller nhận lỗi không đồng nghĩa nghiệp vụ chưa hoàn thành**. Khi phối hợp nhiều aspect, lỗi hậu xử lý của lớp trong có thể đến after throwing ở lớp ngoài.

## 6. After throwing: nhìn nhánh lỗi theo đúng ranh giới

**After throwing advice** được kích hoạt khi phần thực thi nó quan sát thoát bằng một exception **phù hợp điều kiện loại lỗi**, theo ngữ nghĩa công cụ.

Ví dụ mô hình:

```text
A.before
B.before
Business -> throw BusinessFailure
B.afterThrowing(BusinessFailure)
A.afterThrowing(BusinessFailure)
Caller catches BusinessFailure
```

Nhiều công cụ cho phép binding exception để ghi kiểu/message hoặc context.

Nhưng trong phối hợp nhiều aspect có ba biến thể cần phân biệt.

### 6.1. Advice trong ném lỗi mới thay vì ném lỗi gốc

```text
Business -> throw BusinessFailure
B.afterThrowing -> throw AuditFailure
A.afterThrowing -> sees AuditFailure
Caller -> AuditFailure
```

Tùy thiết kế, lỗi `BusinessFailure` có thể bị mất nếu `B` không giữ nó trong `cause` hoặc `suppressed`.

### 6.2. Advice trong trả fallback

```text
Business -> throw BusinessFailure
B.around catches -> return FALLBACK
A.afterReturning(FALLBACK)
Caller -> FALLBACK
```

Tại lớp ngoài, không còn nhánh thrown từ continuation nên after throwing ở lớp ngoài có thể không chạy; thay vào đó after returning phù hợp với kết quả đã được phục hồi.

### 6.3. Lỗi có thể từ advice, không phải business

```text
Business -> return "OK"
B.afterReturning -> throw MetricFailure
A.afterThrowing -> sees MetricFailure
```

Đừng dùng tên sự kiện “business-error” chỉ vì after throwing của lớp ngoài thấy lỗi; cần biết nguồn lỗi trong chain.

### 6.4. Bộ lọc theo kiểu lỗi

Nếu một after throwing chỉ nhận `IOException`, còn lỗi là `IllegalArgumentException`, advice đó có thể không khớp. Khi nhiều after throwing bắt các kiểu khác nhau, tập advice thực sự chạy phụ thuộc quan hệ kiểu exception, không chỉ precedence.

## 7. After/finally: khái niệm “luôn chạy” phải có ranh giới

Một **after/finally advice** thường mô tả công việc khi join point hoặc phần được bao quanh kết thúc **bình thường hoặc bằng exception**.

Với lớp đã được vào:

```text
try:
    proceed()
finally:
    finalizeForThisLayer()
```

Đây là **mã giả**; phạm vi `try` và vị trí before của mỗi engine cần được xét cụ thể.

Ví dụ khi business thất bại:

```text
A.before
B.before
Business -> throw
B.afterThrowing
B.afterFinally
A.afterThrowing
A.afterFinally
Caller -> exception
```

Nếu `B.before` ném lỗi **trước khi đi vào vùng try/finally của B**, `B.afterFinally` trong một implementation thủ công **sẽ không chạy**. Ngược lại, `A.afterFinally` vẫn có thể chạy vì lớp A đã thiết lập finally bao quanh lời gọi B.

**“Finally luôn chạy” chỉ đúng trong phạm vi điều khiển thật sự đã được thiết lập**, với những giới hạn ngôn ngữ/runtime tương ứng; không có lời hứa rằng mọi after advice trong cả hệ thống đều chạy sau bất cứ lỗi nào.

### 7.1. Một cleanup thất bại có thể che lỗi cũ

Trong Java:

```java
static void example() {
    try {
        throw new IllegalArgumentException("original");
    } finally {
        throw new IllegalStateException("cleanup");
    }
}
```

Đây là **mảnh Java minh họa**. Caller nhận `IllegalStateException("cleanup")`; lỗi `IllegalArgumentException("original")` không tự động được gắn vào cause/suppressed.

Khi nhiều aspect đều làm cleanup, một lỗi ở lớp ngoài có thể che lỗi của lớp trong. Cần thiết kế **ưu tiên lỗi chính/phụ** và chính sách bảo toàn nguyên nhân rõ ràng.

## 8. Precedence là thứ tự ưu tiên, không phải thứ tự tất cả các dòng log

Giả sử `A` có precedence cao hơn `B` tại cùng join point.

Với **mô hình nested advice** thông thường:

- Ở đường **vào**, `A.before` có thể chạy trước `B.before`.
- Ở đường **ra**, after của `B` có thể chạy trước after của `A`.
- `A.around` có thể có quyền quyết định có tiếp tục xuống phần `B` không.
- `A` có thể nhìn thấy kết quả hoặc lỗi đã được `B` biến đổi.

Hãy nghĩ đến **quyền bao phần thực thi bên dưới** hơn là bảng “A luôn trước B”.

Ví dụ:

```text
A [entry]
    B [entry]
        business
    B [exit]
A [exit]
```

Để biết thứ tự thật trong một công cụ cần đọc:

1. Quy tắc precedence giữa các **aspect khác nhau**.
2. Quy tắc giữa các advice **trong cùng aspect**.
3. Quy tắc cho before / after returning / after throwing / finally / around.
4. Thứ tự khi nhiều pointcut cùng khớp.
5. Trường hợp không có khai báo thứ tự rõ: công cụ có bảo đảm hay không?

### 8.1. Precedence không phải tổng thứ tự trong mọi mô hình

Một hệ thống có thể chỉ khai báo:

```text
Security trước Metrics
Audit trước Metrics
```

Nhưng **không nói** Security và Audit ai trước. Đó là **partial order**, không đủ để khẳng định một thứ tự duy nhất.

Nếu hai advice không có quan hệ precedence được xác định, kết quả có thể phụ thuộc công cụ hoặc không được bảo đảm. Không viết ứng dụng phụ thuộc vào thứ tự ngẫu nhiên của build, danh sách component hay thứ tự reflection.

## 9. Một công cụ AOP dùng để đối chiếu ngữ nghĩa precedence

Để minh họa việc **thứ tự là ngữ nghĩa được công cụ quy định**, có thể xem **AspectJ** như **một ví dụ cụ thể** (không phải quy tắc chung của mọi hệ thống AOP).

Trong ngữ nghĩa advice của công cụ này:

- Có thể khai báo quan hệ ưu tiên giữa các aspect bằng `declare precedence`.
- Một advice precedence cao hơn bao quanh việc chạy các advice precedence thấp hơn ở cùng join point theo các quy tắc của công cụ.
- Before ở precedence cao có thể ngăn advice thấp hơn nếu ném exception.
- After returning / after throwing / after thông thường hoạt động sau khi phần có precedence thấp hơn hoàn tất theo điều kiện kết thúc.
- Với advice nằm **trong cùng một aspect**, thứ tự khai báo và loại advice có quy tắc riêng; không suy từ “cùng aspect” rằng luôn là thứ tự viết trước.
- Khi hai aspect không có quan hệ precedence được xác định, thứ tự giữa chúng có thể **không được xác định** theo ngữ nghĩa của chính công cụ này.

Ví dụ **cú pháp đặc thù AspectJ**, không phải mã Java 17 thuần và không biên dịch bằng `javac` đơn lẻ:

```java
declare precedence: SecurityAspect, AuditAspect, MetricsAspect;
```

Đoạn trên minh họa khai báo ưu tiên, không phải một chương trình độc lập. Khi dùng DSL khác, phải sử dụng cơ chế cấu hình thứ tự tương ứng với công cụ đó, không sao chép cú pháp trên.

**Quan trọng:** không nên lấy quy tắc của một công cụ rồi áp đặt lên mọi engine proxy, compiler-based weaving hoặc interception middleware.

Nguồn ngữ nghĩa để đối chiếu:
- [Eclipse AspectJ — Advice và advice precedence](https://eclipse.dev/aspectj/doc/released/progguide/semantics-advice.html)
- [Eclipse AspectJ — Khai báo precedence](https://eclipse.dev/aspectj/doc/released/progguide/semantics-declare.html)

## 10. Around advice là ranh giới có sức ảnh hưởng mạnh nhất

Một around advice có thể bao toàn bộ phần còn lại:

```text
around A:
    A.enter
    result = proceed()
    A.exit
    return result
```

`proceed` là ký hiệu có nghĩa **tiếp tục xuống phần có precedence phù hợp**, không mặc định chỉ gọi trực tiếp body nghiệp vụ.

Những tình huống đặc biệt:

### 10.1. Không gọi `proceed`

```text
A.around:
    if forbidden:
        return REJECTED
    else:
        return proceed()
```

Đây là mã giả. Nếu `A` không gọi `proceed`, những advice được xếp **bên trong** và business có thể không chạy.

### 10.2. Gọi `proceed` rồi biến đổi kết quả

```text
B.business returns 10
A.around proceed() returns 10
A.around returns 20
Caller sees 20
```

After returning **ngoài A** có thể thấy 20; after returning **bên trong A** có thể đã thấy 10. Không được nói mọi advice quan sát cùng một giá trị.

### 10.3. Bắt exception và trả fallback

```text
B/business throws TemporaryFailure
A.around catches -> return CACHED
Outside afterReturning -> sees CACHED
```

Một advice ngoài có thể coi nhánh này hoàn tất bình thường trong khi business gốc đã thất bại.

### 10.4. Retry `proceed`

Nếu mô hình cho phép, calling `proceed` nhiều lần có thể thực thi nhiều tầng advice và phần gốc nhiều lần. Mỗi lần còn có thể kích hoạt before/after tương ứng ở **bên trong**.

Với giao dịch không idempotent, retry vì lỗi metrics sau khi business đã thành công có thể tạo trùng side effect. Cần xác định điểm nào có thể an toàn thử lại.

## 11. Bảng tóm tắt thứ tự theo nhánh trong mô hình A ngoài – B trong

| Tình huống | Đường đi minh họa | Ghi chú |
| --- | --- | --- |
| Thành công | A.before → B.before → Business → B.afterReturning → A.afterReturning | Các after/finally thích hợp còn chạy theo phạm vi |
| Business ném lỗi | A.before → B.before → Business throws → B.afterThrowing → A.afterThrowing | Không chạy afterReturning của nhánh lỗi ấy |
| A.before ném lỗi | A.before throws | B và business có thể chưa bắt đầu |
| B.before ném lỗi | A.before → B.before throws → A xử lý lỗi | B.after có chạy hay không tùy ranh giới setup của B |
| B afterReturning ném lỗi | Business success → B afterReturning throws → A afterThrowing | Caller có thể thấy lỗi B |
| B afterThrowing ném lỗi mới | Business throws E → B throws F → A thấy F | E có thể bị che |
| B.around trả fallback | Business throws → B returns fallback → A afterReturning | Outer thấy normal return |
| A.around không proceed | A short-circuit → caller | Advice bên trong và body có thể không chạy |
| Cleanup ngoài ném lỗi | B/Business kết thúc → A finally throws G | Caller có thể thấy G thay vì outcome trước |
| Guard động không khớp một advice | Advice đó không chạy | Không suy ra mọi advice đều chạy chỉ từ precedence |

Bảng giả định các advice đã được sắp xếp theo lớp A ngoài, B trong và loại advice phù hợp. Nó không thay thế việc kiểm tra order do engine thật công bố.

## 12. Ví dụ Java 17 độc lập: mô phỏng chuỗi nhiều aspect

Java thuần không tích hợp ngôn ngữ pointcut và advice weaving. Để thấy **trật tự sự kiện một cách xác định**, ví dụ sau dùng **hàm wrapper thủ công** làm vai trò của các lớp advice.

Điểm thiết kế:

- `A` là lớp ngoài; `B` là lớp trong.
- Mỗi lớp ghi `before`, `afterReturning`, `afterThrowing`, `afterFinally`.
- `B.before` có thể từ chối trước khi bước vào vùng `try/finally` của B.
- Business có thể thành công hoặc ném lỗi.
- `B.afterReturning` có thể tự ném lỗi, và lỗi ấy đi ra tới catch của A.
- Catch của mỗi lớp chỉ bao **continuation**, để không gán nhãn sai chính lỗi `afterReturning` của lớp đó thành lỗi phần tiếp tục.

Tạo file `AdviceOrderDemo.java`:

```java
public class AdviceOrderDemo {
    interface Operation {
        String call(String mode);
    }

    static Operation layer(String name, Operation next) {
        return mode -> {
            System.out.println(name + ":before");

            if ("block".equals(mode) && "B".equals(name)) {
                throw new SecurityException("denied");
            }

            try {
                String result;
                try {
                    result = next.call(mode);
                } catch (RuntimeException error) {
                    System.out.println(name + ":afterThrowing:"
                            + error.getClass().getSimpleName());
                    throw error;
                }

                System.out.println(name + ":afterReturning");

                if ("postfail".equals(mode) && "B".equals(name)) {
                    throw new IllegalArgumentException("after failed");
                }

                return result;
            } finally {
                System.out.println(name + ":afterFinally");
            }
        };
    }

    public static void main(String[] args) {
        Operation business = mode -> {
            System.out.println("business:" + mode);
            if ("fail".equals(mode)) {
                throw new IllegalStateException("business failed");
            }
            return "OK:" + mode;
        };

        Operation chain = layer("A", layer("B", business));

        for (String mode : new String[] {
                "ok", "fail", "block", "postfail"
        }) {
            System.out.println("case:" + mode);
            try {
                System.out.println("caller:result:" + chain.call(mode));
            } catch (RuntimeException error) {
                System.out.println("caller:error:"
                        + error.getClass().getSimpleName()
                        + ":" + error.getMessage());
            }
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac AdviceOrderDemo.java
java AdviceOrderDemo
```

**Stdout chính xác của chương trình:**

```text
case:ok
A:before
B:before
business:ok
B:afterReturning
B:afterFinally
A:afterReturning
A:afterFinally
caller:result:OK:ok
case:fail
A:before
B:before
business:fail
B:afterThrowing:IllegalStateException
B:afterFinally
A:afterThrowing:IllegalStateException
A:afterFinally
caller:error:IllegalStateException:business failed
case:block
A:before
B:before
A:afterThrowing:SecurityException
A:afterFinally
caller:error:SecurityException:denied
case:postfail
A:before
B:before
business:postfail
B:afterReturning
B:afterFinally
A:afterThrowing:IllegalArgumentException
A:afterFinally
caller:error:IllegalArgumentException:after failed
```

### 12.1. Vì sao case `ok` có thứ tự này?

`A` in before rồi gọi `B`. `B` in before rồi gọi business. Business trả bình thường, nên `B` in afterReturning và afterFinally trước khi trả về `A`. Sau đó `A` in afterReturning và afterFinally.

Đây là mô hình **before ngoài trước, after trong trước** khi các tầng được bao quanh đúng thứ tự.

### 12.2. Vì sao case `fail` không in afterReturning?

Business ném `IllegalStateException`. `B` bắt ngoại lệ thoát từ `next.call`, in afterThrowing rồi ném lại. Finally của B in before khi lỗi lan lên `A`. Sau đó `A` bắt, in afterThrowing, chạy finally và để caller bắt lỗi gốc.

### 12.3. Vì sao case `block` không in `B.afterFinally`?

`B` ném `SecurityException` **trước khi vào khối try/finally của B**. Do đó finally của B **chưa được thiết lập**. `A` đã bước vào khối try bao lời gọi B nên catch/finally của A vẫn chạy.

Điều này minh họa quy tắc: **không thể nói after/finally của mọi advice luôn chạy nếu một advice trước đã chặn tiến trình**. Cần xem advice nào đã được tiến tới và ranh giới setup tương ứng.

### 12.4. Vì sao case `postfail` chỉ có `A.afterThrowing`?

Trong B, đoạn xử lý lỗi chỉ bao `next.call(mode)`; nó **không bao** chính `B.afterReturning`. Vì vậy khi B afterReturning in rồi ném `IllegalArgumentException`, catch của B không xử lý nhầm lỗi của chính mình. Nhưng continuation của A **bao toàn bộ B**, nên catch của A nhận lỗi ấy và in afterThrowing.

Điều cần hiểu: **đường lỗi ở mỗi lớp phản ánh kết quả phần được lớp đó quan sát**, không mặc định mọi lớp cùng nhìn thấy lỗi của cùng một nguồn.

### 12.5. Những gì chương trình không chứng minh

- Nó **không** tự phân tích pointcut hoặc tạo join point shadow.
- Nó **không** chứng minh AspectJ hay bất kỳ compiler AOP nào phát ra code y hệt.
- Nó **không** quy định thứ tự giữa advice nằm trong một aspect thật khi công cụ có quy tắc riêng.
- Nó chỉ minh họa **một thứ tự lồng nhau được khai báo rõ bằng Java**.

## 13. Phân biệt thứ tự “đăng ký”, “ưu tiên” và “thực thi”

Ba loại thứ tự thường bị nhầm:

### 13.1. Thứ tự đăng ký/khởi tạo

Một aspect hoặc interceptor có thể được đăng ký trước hay sau. Đây là chuyện tạo component, không tự bảo đảm ai bao ai khi runtime.

### 13.2. Thứ tự ưu tiên có hiệu lực

Công cụ có thể giải quyết precedence từ annotation, cấu hình, DSL, thứ bậc kế thừa, thứ tự khai báo hoặc quy tắc khác. Một số cặp có quan hệ rõ; số khác có thể không được đảm bảo.

### 13.3. Thứ tự sự kiện thực tế

Khi chạy, thứ tự còn phụ thuộc nhánh trả về, exception, guard, việc quanh-advice có proceed hay không và dữ liệu runtime.

Ví dụ `A` được ưu tiên cao hơn `B` nhưng trong ca lỗi:

```text
A.before
B.before
Business throws
B.afterThrowing
A.afterThrowing
```

Khi quan sát log, `B` xuất hiện sau business nhưng **trước** `A` trong phần thoát. Điều đó **không mâu thuẫn** với việc `A` là lớp ngoài ưu tiên cao.

## 14. Nhiều advice bên trong cùng một aspect

Một aspect có thể có **nhiều advice cùng khớp một join point**, thậm chí nhiều before, after hoặc around.

Đừng suy rằng:

- Chúng luôn chạy theo thứ tự tên method.
- Thứ tự source file tự quyết định ở mọi công cụ.
- Nhóm before/after có cùng quy tắc sort.
- Advice được khai báo cùng aspect được chạy đồng thời.
- Một method advice gắn nhiều pointcut sẽ được gọi đúng một lần bất kể số matching được mô hình hóa.

Trong **AspectJ** chẳng hạn, có quy tắc riêng khi **hai advice thuộc cùng aspect**: một số trường hợp liên quan `after` được xét khác với trường hợp không có after. Đặc tả cũng nói về các tình huống quan hệ precedence không xác định giữa các aspect.

Với công cụ dùng reflection để tìm advice methods, thứ tự xuất hiện của các method reflection **không nên được coi là cam kết về declaration order** trừ khi tài liệu công cụ bảo đảm.

**Khuyến nghị:** nếu thứ tự trong cùng một aspect ảnh hưởng correctness, hãy gom các bước phụ thuộc thứ tự thành **một đơn vị điều phối rõ ràng**, hoặc khai báo precedence qua cơ chế chính thức và kiểm thử nó.

## 15. Advice trước và sau có thể không “đối xứng”

Một hệ thống có thể có:

- `Security.before` nhưng **không có** Security.after.
- `Audit.afterReturning` và `Audit.afterThrowing` nhưng không có before.
- `Metrics.around` với `finally` đo thời lượng.
- `Transaction.around` mở và đóng phạm vi công việc.
- `Recovery.around` bắt một lỗi nhất định và trả fallback.

Vì thế không phải mỗi `before` đều có đúng một `after` “cùng cặp”.

Ngay cả khi có cặp, advice sau có thể chỉ áp dụng đường bình thường, chỉ đường lỗi, hoặc cả hai. Thứ tự quan sát phải gắn với **loại advice**, không tạo ra quy tắc “đảo ngược tất cả dòng log trước/sau” quá đơn giản.

## 16. After returning, after throwing, after finally: ma trận đường thoát

| Kết quả phần tiếp tục | After returning | After throwing | After/finally |
| --- | --- | --- | --- |
| Trả giá trị bình thường | Có thể chạy nếu điều kiện khớp | Không cho lỗi không tồn tại | Có thể chạy nếu advice/range đã thiết lập |
| Ném exception thuộc loại phù hợp | Không trên nhánh ấy | Có thể chạy | Có thể chạy |
| Ném exception không hợp type filter | Không trên nhánh ấy | Advice có filter không khớp sẽ không chạy | Có thể chạy |
| Around bên trong bắt lỗi, trả fallback | Với lớp ngoài là return bình thường | Không tại lớp ngoài nếu không có lỗi thoát | Có thể chạy |
| Before bên trong ném lỗi trước body | Tùy advice nào đã được vào | Lớp ngoài có thể quan sát lỗi | Tùy phạm vi finally thực tế |
| After returning bên trong tự ném | Lớp ngoài không nhận return bình thường | Lớp ngoài có thể nhận lỗi advice | Finally lớp đã thiết lập có thể chạy |
| Cleanup bên trong tự ném | Kết quả trước có thể bị che | Lớp ngoài có thể bắt cleanup error | Các finally ngoài có thể vẫn chạy |

**Lưu ý về chữ “có thể”:** bảng diễn tả điều kiện logic và ranh giới của mô hình. Đúng loại event chưa đủ nếu pointcut không khớp, runtime guard sai hoặc advice không nằm trên đường đã được thực thi.

## 17. Lỗi từ advice làm thay đổi thứ tự các advice còn lại

Tình huống:

```text
A.before
B.before
Business returns OK
B.afterReturning throws MetricFailure
A.afterThrowing receives MetricFailure
A.afterFinally
Caller receives MetricFailure
```

Những hệ quả:

1. Business **đã thành công**, nhưng caller nhận lỗi.
2. `A.afterReturning` không chạy trong mô hình này, dù business đã return.
3. `A.afterThrowing` chạy do **lỗi phát sinh từ B**, không từ business.
4. Nếu caller retry, side effect business có thể bị nhân đôi.
5. Nếu `A` chuyển đổi lỗi tiếp, exception cuối cùng có thể còn khác `MetricFailure`.

Vì vậy khi logging exception, cần ghi thêm **phase/source** (business, advice before, advice after, cleanup) nếu có chứng cứ, không gắn nhãn “business failed” cho mọi exception thoát từ continuation.

## 18. Giữ nguyên nhân lỗi qua nhiều tầng: cause và suppressed

Có ba lựa chọn thường gặp:

**Truyền tiếp nguyên dạng:**

```java
throw original;
```

Giữ đối tượng exception gốc. Đây là **mảnh Java**, giả định biến `original` đang được bắt và hợp đồng cho phép ném lại nó.

**Chuyển đổi có cause:**

```java
throw new IllegalStateException("audit failure", original);
```

Caller nhận lỗi mới, nhưng `getCause()` giúp truy nguyên lỗi trước.

**Giữ lỗi phụ bằng suppressed:**

```java
primary.addSuppressed(secondary);
throw primary;
```

Đây là mảnh Java, giả định cả hai là `Throwable` khác nhau và kiểu ném hợp lệ. `addSuppressed` không tự ném lại; cần thao tác `throw` sau đó.

### 18.1. Khi hai tầng đều ném lỗi

Giả sử business ném `E1`, advice B ném `E2` và advice A ném `E3`. Nếu mỗi tầng thay thế lỗi trước bằng lỗi mới **không có cause**, caller có thể chỉ thấy `E3`.

Điều đó làm chẩn đoán sai: lỗi `E1` quan trọng nhất có thể biến mất.

Một chính sách error model nên phân biệt:

- Lỗi nghiệp vụ chính.
- Lỗi của công việc quan sát/cleanup.
- Lỗi của cơ chế interception.
- Lỗi đang được dịch để công bố API.
- Thông tin chẩn đoán có thể ghi lại mà không tiết lộ bí mật.

### 18.2. Không phải mọi lỗi phụ trợ đều có thể bỏ qua

Metrics tùy chọn khác audit bắt buộc và kiểm soát quyền. Nếu business thất bại và audit cũng không lưu được, có thể cần một trạng thái lỗi tổng hợp hoặc cơ chế phục hồi được thiết kế riêng.

Không tùy tiện nuốt `Throwable` hoặc biến mọi lỗi thành kết quả thành công.

## 19. Transaction và advice order

Một ứng dụng có thể có nhiều mối quan tâm cùng áp dụng cho một operation:

```text
Authorization
   -> Transaction
       -> Audit
           -> Business
```

Ở đường thành công, ví dụ một thứ tự hiệu lực mong muốn là:

```text
authorize
open transaction
record audit intent
business
record audit outcome
commit/finish transaction
return caller
```

Nhưng một thiết kế khác có thể chủ đích ghi audit **sau commit**. Hai thiết kế mang ý nghĩa khác nhau về tính bền vững và nhất quán.

Cần quyết định:

- Audit thuộc cùng giao dịch hay kho dữ liệu khác?
- Khi business ném lỗi, transaction sẽ rollback theo chính sách nào?
- Advice audit có nhìn thấy lỗi gốc trước hay sau error translation?
- Khi commit thất bại **sau business return**, caller thấy lỗi nào?
- Logging `afterReturning` nằm trước hay sau commit của một wrapper bên ngoài?
- Có yêu cầu tránh side effect lặp lại khi caller retry?

Không có bảo đảm “hễ advice ném RuntimeException thì mọi side effect đều rollback”. Một email, HTTP request hoặc hệ thống ngoài giao dịch có thể đã xử lý yêu cầu.

## 20. Security và quan hệ ưu tiên

Kiểm tra quyền thường là hành vi **cần diễn ra trước** những thao tác không đáng tin, nhưng vị trí thật còn phụ thuộc mục tiêu chính sách.

Ví dụ:

```text
Security.before
Tracing.before
Business
Tracing.after
Security.after
```

Trong mô hình này, nếu Security từ chối, Tracing có thể **không có event của lần từ chối** vì nó chưa được vào. Nếu audit an ninh cần ghi **mọi attempt kể cả bị từ chối**, có thể cần một lớp ngoài Security:

```text
SecurityAudit(
    Security(
        Business
    )
)
```

Khi đó SecurityAudit có thể ghi nhận hành vi từ chối ở đường lỗi, với điều kiện audit wrapper đã vào và xử lý exception đúng.

Điều này cho thấy “aspect quan trọng nhất phải ưu tiên cao nhất” **chưa đủ để quyết định tất cả thứ tự**: hãy xuất phát từ **yêu cầu quan sát**, đường dữ liệu và ranh giới tin cậy.

### 20.1. Không dựa duy nhất vào proxy dễ bypass để bảo vệ bất biến

Nếu AOP chạy qua proxy, lời gọi trực tiếp target có thể đi vòng chuỗi advice. Một chính sách bảo mật bắt buộc phải được bảo vệ ở boundary phù hợp và kiểm thử cả đường bypass, không chỉ thứ tự khi đã ở trong chain.

## 21. Retry và thứ tự các lớp

Giả sử:

```text
RetryAround(
    MetricsAround(
        BusinessOperation
    )
)
```

Nếu Metrics ném lỗi **sau khi business đã thành công**, RetryAround có thể bắt lỗi đó và chạy lại `proceed`, khiến business thực hiện thêm lần nữa.

Đảo thứ tự thành:

```text
MetricsAround(
    RetryAround(
        BusinessOperation
    )
)
```

có thể thay đổi phạm vi đo metric, số lần log và loại lỗi mà retry quan sát. Ví dụ outer Metrics đo toàn bộ thời gian của mọi attempt, còn inner Metrics có thể đo từng attempt riêng, tùy cách code được triển khai.

Câu hỏi thiết kế:

- Retry được phép xử lý những kiểu lỗi nào?
- Lỗi sau commit/side effect có được phép retry không?
- Retry chạy lại cả chuỗi advice hay chỉ phần business?
- Metrics đếm request logic hay số attempt?
- Transaction được mở cho mỗi attempt hay bao toàn bộ?
- Có idempotency key hoặc cách kiểm tra trạng thái đã hoàn tất không?

**Thứ tự aspect là một phần của thiết kế nghiệp vụ**, không chỉ là cấu hình thẩm mỹ.

## 22. Những lưu ý riêng cho bất đồng bộ

Với Java, một method có thể trả `CompletableFuture<Result>`:

```text
Caller
 -> Advice trước
 -> Method returns Future
 -> Advice sau method-return
 -> Task completes later (success/failure)
```

Một after returning tại **method execution** có thể chạy khi Future **được trả ra**, không phải khi công việc bên trong Future hoàn tất.

Nếu task về sau ném lỗi, nó có thể được biểu diễn bằng **exceptional completion** ở stage tương ứng. Một after throwing quanh lời gọi tạo Future không tự động nhìn thấy lỗi ấy.

Muốn quan sát completion:

- Phải gắn handler tại đúng stage và hiểu việc handler tạo stage mới.
- Context/correlation ID cần được truyền qua task/thread.
- Callback quan sát có thể tự ném lỗi, tạo một nhánh lỗi khác.
- Không ghi “operation succeeded” chỉ vì method trả Future bình thường.
- Thứ tự completion giữa hai task độc lập không tự bảo đảm bởi precedence của advice tại method entry.

Với nhiều aspect bất đồng bộ, cần phân biệt **thứ tự đăng ký callback** và **thứ tự callback chạy thực tế** do API completion/thread scheduler quy định.

## 23. Thứ tự advice khi có nhiều join point khác nhau

Precedence của các advice **cùng một join point** không đồng nghĩa tổng thứ tự trên **mọi sự kiện của chương trình**.

Ví dụ một method `checkout` gọi `reserve` rồi `charge`. Advice cùng loại ở `reserve` và `charge` có thể xen kẽ theo call stack, không nhất thiết mọi before của toàn bộ chương trình chạy trước mọi after.

```text
checkout before
  reserve before
  reserve business
  reserve after
  charge before
  charge business
  charge after
checkout after
```

Nếu recursion hoặc async có mặt, log nhiều join point càng dễ xen kẽ.

Cần giữ **join-point identity** và **invocation ID** để phân tích thứ tự, không kết luận từ một stream log thiếu ngữ cảnh.

## 24. Kiểm thử thứ tự: không chỉ kiểm tra có log

Kiểm thử đúng nên thu event vào một danh sách với thứ tự xác định cho **một invocation đồng bộ**.

Ma trận đề xuất:

| Ca | Kỳ vọng kiểm thử |
| --- | --- |
| Thành công | Before ngoài → before trong → business → after trong → after ngoài |
| Business ném lỗi | Không có after returning trên nhánh thất bại; after throwing phù hợp chạy |
| Before ngoài từ chối | Inner/business chưa chạy |
| Before trong từ chối | Outer có thể nhận lỗi; không giả định inner finally đã thiết lập |
| Inner after returning lỗi | Outer thấy lỗi advice, không nhầm nguồn business |
| Inner after throwing lỗi | Outer thấy ngoại lệ mới/cause đúng |
| Around trong trả fallback | Outer thấy kết quả bình thường |
| Around ngoài không proceed | Inner/business không chạy |
| Cleanup lỗi sau business failure | Cause/suppressed/primary theo chính sách |
| Hai aspect không có precedence rõ | Test phát hiện không được phép phụ thuộc thứ tự ngẫu nhiên |
| Retry bao ngoài | Số lần business và advice phù hợp; không lặp side effect ngoài chủ đích |
| Transaction + audit | Quan sát đúng trước/sau commit, rollback và ngoại lệ |
| Async | Không nhầm return Future với task completion |
| Concurrent | Event nhóm theo invocation, không trộn request |

### 24.1. Event collector trong kiểm thử

Nên thu event như:

```text
A.before
B.before
business
B.afterReturning
B.afterFinally
A.afterReturning
A.afterFinally
```

rồi so sánh với expected list. Tránh phụ thuộc timestamp wall-clock để chứng minh thứ tự khi các event có thể có cùng độ phân giải thời gian.

### 24.2. Kiểm thử một phương thức không được advice

Ngoài ca dương tính, cần ca âm tính: điểm không khớp pointcut không được advice, dù aspect có precedence cao. Precedence **chỉ có ý nghĩa khi lời advice thực sự cùng áp dụng**.

### 24.3. Kiểm thử đường exception identity

Nếu policy là truyền tiếp nguyên ngoại lệ, so sánh identity `caught == original` khi phù hợp. Nếu policy là wrap, kiểm tra `getCause()`. Nếu cleanup thêm suppressed, kiểm tra `getSuppressed()`.

## 25. Làm sao tìm thứ tự khi kết quả chạy khác dự đoán?

Quy trình chẩn đoán:

1. **Xác định join point**: call, execution hoặc loại nào công cụ hỗ trợ?
2. **Liệt kê aspect thực sự khớp**: không phán đoán từ tên class.
3. **Kiểm tra pointcut/guard động**: advice không chạy có thể do không khớp.
4. **Xác định precedence có hiệu lực**: ưu tiên giữa aspect, trong cùng aspect, trường hợp không xác định.
5. **Vẽ lớp ngoài/trong**: ai gọi `proceed` tới ai?
6. **Đánh dấu mọi đường throw/return**: before fail, business fail, after fail, cleanup fail.
7. **Tìm advice short-circuit**: có quanh-advice không gọi tiếp không?
8. **Xác định loại after**: returning, throwing hay finally; binding type có khớp không?
9. **Phân biệt nguồn exception**: từ body, advice trong hay advice hiện tại.
10. **Kiểm tra proxy/weaving reachability**: lời gọi có thực sự đi qua lớp can thiệp không?
11. **Kiểm tra async/concurrency**: log nhiều invocation có bị xen kẽ không?
12. **Tái hiện với event collector nhỏ** và kiểm chứng chuỗi thực tế.

Khi chưa rõ nguyên nhân, không sửa cấu hình priority chỉ để “log nhìn đẹp hơn”. Nó có thể đổi ranh giới transaction, quyền kiểm soát truy cập và xử lý ngoại lệ.

## 26. Các hiểu nhầm phổ biến

**“Aspect ưu tiên cao luôn chạy mọi advice trước aspect ưu tiên thấp.”** Không. Với nesting, after có thể chạy theo chiều ngược của trước.

**“Sau khi business xong, mọi after advice đều chạy.”** Không. After returning/throwing có điều kiện theo đường thoát; pointcut và phạm vi còn quyết định.

**“After throwing chắc chắn thấy lỗi từ business.”** Không. Lỗi có thể do advice bên trong ném.

**“Business trả thành công nghĩa outer after returning chắc chắn chạy.”** Không nếu một advice trong ném lỗi sau business return.

**“Before ném lỗi thì mọi finally của mọi aspect vẫn chạy.”** Không. Chỉ những ranh giới đã được thiết lập và có semantics phù hợp mới có thể cleanup.

**“Đảo priority chỉ thay đổi thứ tự log.”** Không. Nó có thể thay đổi retry, transaction, security và loại lỗi cuối.

**“Thứ tự declaration luôn là thứ tự run.”** Không thể mặc định; phải xem quy tắc tool và loại advice.

**“Cùng một aspect thì thứ tự các advice chắc chắn ổn định.”** Không được tự suy; một số công cụ có quy tắc riêng hoặc trường hợp không xác định.

**“After finally luôn giữ exception gốc.”** Không. Cleanup ném lỗi có thể che nguyên nhân ban đầu.

**“Một after-returning trên Future nghĩa tác vụ thành công.”** Không. Đó có thể chỉ là return của method, không phải completion.

**“Tất cả advice khớp cùng pointcut luôn chạy.”** Không nếu around ngoài short-circuit, before chặn, guard không khớp hoặc đường gọi bypass proxy.

**“Đo thứ tự qua timestamp log toàn cục là đủ.”** Không trong concurrent/async; cần invocation ID và test per-call.

## 27. Bài tập tự luyện

### Bài 1 — Thành công với hai lớp

`A(B(Business))`, cả A và B có before/after returning/after finally; body trả bình thường. Hãy viết thứ tự.

**Gợi ý:** A.before → B.before → Business → B.afterReturning → B.afterFinally → A.afterReturning → A.afterFinally.

### Bài 2 — Lỗi từ business

Body ném `DomainFailure` và không có fallback. Những after nào chạy?

**Gợi ý:** after throwing của lớp đã vào và có type filter khớp, cùng các finally thích hợp; after returning trên nhánh đó không chạy.

### Bài 3 — Before lớp trong từ chối

A đã vào vùng try, nhưng B.before ném trước khi B thiết lập finally. Ai thấy lỗi, có chắc B.finally chạy không?

**Gợi ý:** A có thể catch và finally; B.finally của vùng chưa vào không chạy trong cấu trúc đã nêu.

### Bài 4 — After returning của B ném

Body trả `OK`, B.afterReturning ném `MetricFailure`. A có thể chạy advice nào?

**Gợi ý:** A có thể quan sát thrown branch từ phần B; không mặc định A.afterReturning chạy chỉ vì body thành công.

### Bài 5 — B bắt và chuyển lỗi thành fallback

Business ném `ReadFailure`, B.around trả `CACHED`. A thấy gì?

**Gợi ý:** phần tiếp tục của A trả bình thường; A.afterReturning có thể nhận `CACHED`.

### Bài 6 — Tracing quanh security

Nếu audit cần ghi lại cả request bị Security từ chối, nên đặt audit ngoài hay trong lớp Security?

**Gợi ý:** một lớp audit ngoài security có thể thấy attempt/từ chối, miễn nó thực sự đã bắt đầu và không bị bỏ qua bởi cơ chế khác.

### Bài 7 — Lỗi cleanup

Business ném `E1` và finally ném `E2`. Caller nhận gì trong Java finally thủ công nếu không bảo toàn `E1`?

**Gợi ý:** lỗi cleanup `E2` có thể thay thế `E1`. Cần chính sách cause/suppressed khi muốn giữ cả hai.

### Bài 8 — Retry và metrics

RetryOutside(MetricsInside(Business)), business đã tạo đơn nhưng metrics ném lỗi. Rủi ro?

**Gợi ý:** retry bao cả metrics có thể gọi business lần nữa, nhân đôi đơn hàng. Cần phân loại lỗi và idempotency.

### Bài 9 — Thứ tự không xác định

Hai aspect không có quan hệ precedence được công cụ bảo đảm, nhưng ứng dụng yêu cầu Audit luôn bao Security. Nên làm gì?

**Gợi ý:** khai báo quan hệ thứ tự tường minh hoặc thiết kế lại thành một orchestration rõ ràng và kiểm thử; đừng dựa vào thứ tự tình cờ.

## 28. Checklist áp dụng khi phối hợp nhiều aspect

- [ ] Đã liệt kê chính xác các join point và advice cùng khớp.
- [ ] Phân biệt before, after returning, after throwing, after/finally và around.
- [ ] Xác định precedence giữa những aspect có quan hệ phụ thuộc.
- [ ] Đã kiểm tra quy tắc thứ tự **trong cùng một aspect** của công cụ.
- [ ] Không phụ thuộc vào thứ tự không được công cụ bảo đảm.
- [ ] Có sơ đồ ai ngoài, ai trong, ai gọi `proceed`.
- [ ] Có kiểm thử cả đường return và đường throw.
- [ ] Có test before advice chặn trước khi body chạy.
- [ ] Có test advice sau tự ném exception sau khi business thành công.
- [ ] Có test exception filtering cho after throwing.
- [ ] Giữ cause/suppressed theo chính sách khi nhiều tầng cùng thất bại.
- [ ] Có chính sách rõ với audit, authorization và transaction.
- [ ] Retry chỉ áp dụng lỗi hợp lệ, kiểm soát idempotency.
- [ ] Phân biệt method return và async task completion.
- [ ] Trace có invocation ID để phân biệt log đa luồng.
- [ ] Có ca âm tính cho điểm không khớp hoặc đường proxy bypass.
- [ ] Có cơ chế kiểm tra chuỗi event theo từng invocation.
- [ ] Không để logic log/metrics làm mất lỗi chính ngoài ý định.
- [ ] Đã đo overhead của nhiều tầng interception khi cần.
- [ ] Có tài liệu về những thứ tự ảnh hưởng correctness, không chỉ hiệu năng.

## 29. Tổng kết

**Quan hệ thứ tự giữa advice trước, sau và khi có lỗi phải được hiểu như một chuỗi thực thi lồng nhau, không chỉ một danh sách hàm có số thứ tự.** Với A bao B, đường vào thường đi A → B → business, còn đường ra thường đi business → B → A. Nhưng nhánh **return**, **throw**, **fallback**, **short-circuit** và **lỗi do chính advice tạo ra** có thể thay đổi những advice nào thực sự chạy.

Một thiết kế AOP đáng tin cần xác định **precedence chính thức**, **ranh giới proceed**, **kiểu after advice**, **nguồn exception**, **tác dụng phụ** và **đường thực thi thật**. Kiểm thử nên xác minh cả thứ tự event lẫn kết quả/ngoại lệ mà caller quan sát, đặc biệt khi phối hợp security, transaction, retry, metrics và audit.
