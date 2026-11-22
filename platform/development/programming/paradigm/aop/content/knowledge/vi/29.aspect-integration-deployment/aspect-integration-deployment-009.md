# Bật Aspect theo giai đoạn, giám sát và chuẩn bị phương án quay lui trong AOP

## 1. Tại sao AOP cần kế hoạch triển khai riêng?

Aspect-Oriented Programming (AOP) đưa các hành vi cắt ngang vào nhiều điểm của ứng dụng: ghi log, đo thời gian, kiểm soát truy cập, audit, giới hạn tần suất, retry hoặc xử lý lỗi. Một thay đổi rất nhỏ trong **pointcut** có thể tác động đến hàng trăm phương thức, kể cả những nhánh ít được kiểm thử. Với advice kiểu `around`, thay đổi còn có thể quyết định có gọi `proceed()`, gọi bao nhiêu lần hoặc có ném ngoại lệ, nên rủi ro không chỉ là tăng độ trễ mà còn ảnh hưởng trực tiếp kết quả nghiệp vụ.

Vì vậy, một đợt triển khai AOP an toàn cần giải quyết đồng thời ba câu hỏi:

1. **Bật ở đâu, cho ai và theo mức độ nào?** Chọn đơn vị canary, vùng phạm vi pointcut, nhóm máy/phiên bản và mức thực thi advice.
2. **Quan sát điều gì để biết nên tiếp tục hay dừng?** Đo cả hành vi advice và kết quả nghiệp vụ, so sánh với đường cơ sở, có correlation ID và kiểm tra tác động ngoài ý muốn.
3. **Nếu cần quay lui thì tắt bằng cách nào và mất bao lâu?** Việc tắt một nhánh advice ở runtime khác với loại bỏ proxy, hoàn nguyên bytecode đã dệt hoặc xử lý lớp đã được JVM nạp.

**Nguyên tắc:** chỉ tăng phạm vi khi đã có bằng chứng từ giai đoạn trước và phương án quay lui đã được kiểm chứng; không xem “ứng dụng vẫn khởi động” hoặc “không xuất hiện exception trong log” là đủ để xác nhận AOP an toàn.

## 2. Hiểu đúng những thứ có thể bật hoặc tắt

Trong AOP, **aspect** chứa các mối quan tâm cắt ngang; **pointcut** mô tả tập join point; **advice** thực thi tại các join point phù hợp. Tuy nhiên, “bật aspect” có thể mang nhiều nghĩa khác nhau:

| Cấp điều khiển | Có thể thay đổi | Điều chưa chắc được thay đổi |
| --- | --- | --- |
| Feature flag ngay trong advice | Bỏ qua hoặc áp dụng **logic do advice kiểm soát** ở lần gọi sau | Không tháo bytecode đã weave; không xóa overhead vào advice; không đảm bảo vô hiệu hóa hành vi khác |
| Predicate/pointcut động nếu engine hỗ trợ | Bật/tắt match theo ngữ cảnh, đối tượng hoặc đối số | Có thể vẫn có chi phí matcher/interceptor; không bảo đảm mọi join point có thể đổi lúc chạy |
| Cấu hình lắp chuỗi interceptor/proxy | Có thể thay interceptor cho các lời gọi mới theo vòng đời cấu hình | Các tham chiếu proxy/target đã phát tán hoặc tác vụ đang chạy có thể giữ trạng thái cũ |
| Compile-time weaving (CTW) | Phát hành artifact chứa class đã dệt hoặc artifact gốc | Một flag runtime không tự loại bỏ mã đã dệt |
| Post-compile/binary weaving (PCW) | Triển khai lại artifact trước/sau khi weave | Các instance cũ vẫn chạy bytecode cũ đến khi thay thế |
| Load-time weaving (LTW) | Điều chỉnh agent, cấu hình weave và khởi động tiến trình mới | Lớp **đã được định nghĩa** không tự “unweave” khi tắt cấu hình agent; phụ thuộc công nghệ nạp lại class |
| Proxy/interception AOP | Điều chỉnh đường gọi qua proxy hoặc chế độ interceptor | Lời gọi bỏ qua proxy vẫn không được advice xử lý; thay đổi reference không tự lan đến mọi caller |

Từ đó phải có **hai bản đồ** riêng: (a) nhóm phương thức sẽ chịu tác động của pointcut; (b) nhóm máy, tiến trình, classloader và artifact thực sự đang mang cơ chế AOP ấy. Một flag tắt logic advice chỉ tác động đúng nơi nó được kiểm tra; không phải nút hoàn nguyên chung cho tất cả công nghệ AOP.

## 3. Phân loại mức độ rủi ro trước khi rollout

Không nên triển khai mọi loại advice theo cùng chiến thuật.

| Loại advice | Tác động thường gặp | Điều kiện triển khai cần quan tâm |
| --- | --- | --- |
| Tracing và metrics chỉ quan sát | CPU, memory allocation, cardinality, I/O của exporter | Tỷ lệ sampling, ngân sách overhead, mất dữ liệu có chấp nhận được không |
| Audit/ghi log nhạy cảm | I/O, dữ liệu cá nhân, độ trễ, nhân đôi bản ghi | Lọc dữ liệu, retry/idempotency, khả năng audit bắt buộc |
| Cache/circuit breaker/rate limiter | Thay đổi đường trả kết quả, timeout, từ chối request | Hành vi khi dependency lỗi, giới hạn phạm vi, fallback |
| Authorization/security | Cho phép hoặc chặn hành vi nghiệp vụ | Chính sách **fail-open hay fail-closed** phải được phê duyệt từ yêu cầu bảo mật |
| Retry/transaction advice | Gọi `proceed()` nhiều lần, thay đổi số lần side effect hoặc ranh giới giao dịch | Idempotency key, khả năng khôi phục dữ liệu và xử lý partial completion |

Đối với cơ chế quan sát thuần túy, có thể triển khai **shadow/observe-only**: vẫn tính predicate và ghi đo lường ở mức tối thiểu nhưng không thay đổi kết quả nghiệp vụ. Đối với kiểm soát quyền, shadow chỉ giúp so sánh chính sách mới và cũ; **không dùng nó làm biện pháp thay thế việc bắt buộc kiểm tra quyền**. Không được tắt logic bảo vệ có yêu cầu fail-closed chỉ để giảm báo lỗi.

Phải ghi rõ **bất biến (invariant)** trước khi rollout, ví dụ: một giao dịch thành công chỉ được tạo một bản ghi thanh toán; advice không được nuốt exception nghiệp vụ; audit không lưu credential; việc bật/tắt không làm sai thứ tự các advice bắt buộc.

## 4. Các giai đoạn triển khai đề xuất

Một tiến trình thực tế có thể dùng các trạng thái sau (tên trạng thái là thiết kế minh họa, không phải API chuẩn của AOP):

```text
DESIGNED
   |
   v
OFF / instrument-ready
   |
   v
SHADOW (đọc, quan sát, không đổi quyết định nghiệp vụ)
   |
   v
CANARY (một nhóm nhỏ, có tiêu chí dừng)
   |
   v
EXPAND (mở rộng từng nấc theo metric)
   |
   v
FULL (mọi đối tượng trong phạm vi đã phê duyệt)
   |
   +------> HOLD (dừng mở rộng, điều tra)
   |
   +------> ROLLBACK (quay về trạng thái an toàn đã biết)
```

### 4.1. OFF — đặt nền giám sát và xác định phạm vi

Trước khi bật logic mới:

- Khoanh **pointcut** theo lớp/gói/method cần thiết. Kiểm tra cả overload, implementation, annotation, interface, kiểu join point (`call`, `execution`, v.v.) và lời gọi nội bộ nếu cơ chế dệt hỗ trợ.
- Xác nhận số join point có thể bị ảnh hưởng từ báo cáo weaving, danh sách matched methods hoặc phép thử instrumentation. Không để một biểu thức wildcard vô tình bắt logging helper, serializer hoặc chính advice.
- Tạo số liệu baseline: p50/p95/p99 latency, error/timeout rate, request throughput, CPU, heap/GC, queue depth, số lần gọi nghiệp vụ, tỉ lệ side effect không mong muốn.
- Xác nhận có đường **rollback riêng** cho artifact, config, agent và data. Lưu version/hash của artifact hiện tại và câu lệnh triển khai ngược.
- Chuẩn bị quyền vận hành, dashboard, cảnh báo, trách nhiệm quyết định mở rộng/dừng và thời gian theo dõi.

Với CTW/PCW, ngay cả khi một flag đặt OFF, bytecode đã dệt vẫn khác bản trước. Cần đo baseline riêng giữa **artifact gốc** và **artifact woven ở chế độ OFF**, vì overhead hoặc lỗi weaving có thể tồn tại khi nhánh advice chính chưa bật.

### 4.2. SHADOW — quan sát nhưng không thay đổi kết quả

Trong shadow mode, advice có thể đánh giá điều kiện hoặc tính toán quyết định dự kiến mà không chặn lời gọi, không retry, không sửa tham số/return value, không tạo side effect nghiệp vụ và không thay thế exception. Ví dụ một policy guard có thể ghi số sự kiện “would deny”, nhưng vẫn để logic hiện hữu quyết định.

Kiểm tra trong shadow:

- Số lần match theo join point kind và chữ ký; so sánh với số invocation nghiệp vụ.
- Chênh lệch kết quả dự kiến giữa chính sách mới và hành vi thực tế; lưu **thống kê tổng hợp**, tránh dữ liệu nhạy cảm.
- Overhead do match, capture arguments, instrumentation, log và exporter gây ra.
- Có phát sinh recursion, advice lặp, thay đổi thứ tự hoặc context propagation lỗi không.
- Exception path có giữ nguyên stack, type và thứ tự cleanup như trước không.

Shadow **vẫn có thể gây hại** nếu advice tự gửi network request, tạo object lớn, gọi `toString()` trên tham số có side effect, hoặc gây quá tải hệ thống log. “Không sửa business result” không có nghĩa “không có rủi ro”.

### 4.3. CANARY — kích hoạt trên nhóm xác định

Chọn một phân vùng ổn định, chẳng hạn nhóm máy/instance, tenant thử nghiệm hoặc tập request được ánh xạ nhất quán. Nếu AOP được weave vào artifact, phát hành **canary artifact** cho một số instance; nếu advice hỗ trợ feature flag runtime, có thể bật logic cho nhóm được phê duyệt.

Các lưu ý:

- Cùng một tác vụ liên quan nhiều request hoặc nhiều service nên có **quy tắc phân nhóm nhất quán**; nếu bật ngẫu nhiên lại ở từng join point, workflow có thể nửa bật nửa tắt.
- Căn cứ tỷ lệ trên **đơn vị nghiệp vụ phù hợp** (ví dụ tenant hoặc session), không chỉ số lượng request.
- Nếu nhóm canary khác về tải, tính năng hoặc vùng mạng so với control group, không suy ra chênh lệch do aspect mà chưa kiểm soát khác biệt đó.
- Khởi động ở phạm vi có rủi ro được chấp nhận và mở rộng theo kế hoạch phê duyệt. Các tỷ lệ như 1% → 5% → 25% → 100% chỉ là **ví dụ**, không phải ngưỡng mặc định an toàn cho mọi hệ thống.

### 4.4. EXPAND — tăng dần sau khi vượt tiêu chí

Tại mỗi nấc, đợi đủ lưu lượng và khoảng quan sát để số liệu có ý nghĩa; không nhất thiết dùng một thời lượng cố định. So với baseline và control group trên cùng khoảng thời gian, xét cả giai đoạn cao tải, lỗi dependency và đường exception quan trọng.

Các điều kiện “go/no-go” cần được định nghĩa **trước** rollout: ngưỡng tăng latency, error, side effect, tài nguyên, queue depth, số lần advice/proceed và cảnh báo bảo mật. Nếu thiếu dữ liệu hoặc số mẫu chưa đủ, giữ nguyên nấc (**HOLD**) thay vì coi “chưa có lỗi” là bằng chứng thành công.

### 4.5. FULL — hoàn thành nhưng vẫn có cơ chế dừng

Khi rollout full, ghi lại phạm vi pointcut, version của advice, artifact hash, classloader/agent config, trạng thái flag và ngày giờ chuyển trạng thái. Duy trì giám sát sau triển khai để phát hiện trường hợp lưu lượng thấp, theo chu kỳ hoặc theo lô không xuất hiện trong canary.

## 5. Thiết kế feature flag đúng với AOP

Một advice có thể sử dụng **một snapshot cấu hình bất biến cho mỗi invocation**:

```text
join point entered
  -> capture rollout version/mode một lần
  -> determine target cohort
  -> OFF? proceed bình thường
  -> SHADOW? observe rồi proceed
  -> ON? áp dụng advice theo hợp đồng rồi proceed/return/throw
```

Các quy tắc quan trọng:

1. **Tính nhất quán theo invocation:** nếu mode thay đổi ngay giữa một `around`, nên dùng snapshot đã đọc lúc vào để việc cleanup và xử lý kết quả không bị nửa logic cũ, nửa logic mới.
2. **Tính nhất quán theo workflow:** một thao tác nhiều bước có thể cần cohort quyết định từ đầu và được truyền qua các lời gọi sau, không tính ngẫu nhiên lại.
3. **Chính sách lỗi cấu hình:** nếu hệ thống flags không truy cập được, fallback phải dựa trên yêu cầu nghiệp vụ/bảo mật. Quan sát metrics có thể chấp nhận OFF; authorization bắt buộc thường phải giữ chính sách bảo vệ, không tự động bỏ qua.
4. **Tránh gọi dịch vụ cấu hình trên từng join point:** dùng cache/snapshot theo phiên bản và cơ chế cập nhật không gây vòng advice trên đường truy xuất cấu hình.
5. **Giảm side effect trong SHADOW:** không nhân bản ghi dữ liệu, giao dịch, email, request thanh toán hay lệnh `proceed()`; so sánh quyết định bằng hàm thuần hoặc bản sao trạng thái an toàn.
6. **Tách flag của chức năng với kill switch:** flag rollout tăng/giảm cohort; kill switch nhằm vô hiệu hóa nhanh hành vi không bắt buộc khi vượt ngưỡng, với người chịu trách nhiệm và quyền truy cập rõ ràng.

Bật/tắt flag từ xa chỉ có ý nghĩa nếu **mọi tiến trình liên quan đều thực sự đọc được thay đổi**. Cần đo thời gian truyền cấu hình, trạng thái hiện tại của từng instance, khả năng tiến trình mất kết nối tiếp tục dùng bản cũ, và cách xử lý invocation đang chạy khi flag chuyển OFF.

## 6. Ví dụ Java 17 chạy độc lập: OFF → SHADOW → ON → ROLLBACK

Ví dụ sau dùng **JDK dynamic proxy** để minh họa một interceptor đóng vai trò advice có chế độ runtime. Đây là mô hình AOP qua delegation proxy, **không phải chương trình weaving** và không yêu cầu thư viện ngoài JDK. Tất cả trạng thái lưu trong một tiến trình để output có thể kiểm chứng.

Tạo file **`AopRolloutDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicReference;

public final class AopRolloutDemo {
    enum Mode { OFF, SHADOW, ON }

    interface PaymentService {
        void pay(String reference);
        void health();
    }

    static final class PaymentServiceImpl implements PaymentService {
        @Override
        public void pay(String reference) {
            System.out.println("target pay " + reference);
        }

        @Override
        public void health() {
            System.out.println("target health");
        }
    }

    private static final AtomicReference<Mode> MODE =
            new AtomicReference<>(Mode.OFF);

    private static Object invokeTarget(
            PaymentService target, Method method, Object[] args) throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException failure) {
            throw failure.getCause();
        }
    }

    public static void main(String[] args) {
        PaymentService target = new PaymentServiceImpl();
        PaymentService proxy = (PaymentService) Proxy.newProxyInstance(
            PaymentService.class.getClassLoader(),
            new Class<?>[] { PaymentService.class },
            (ignoredProxy, method, methodArgs) -> {
                // Pointcut minh họa: chỉ các lời gọi pay đi qua proxy.
                if (!method.getName().equals("pay")) {
                    return invokeTarget(target, method, methodArgs);
                }

                // Một snapshot trên mỗi invocation.
                Mode snapshot = MODE.get();
                if (snapshot != Mode.OFF) {
                    System.out.println(
                        "observe mode=" + snapshot + " ref=" + methodArgs[0]);
                }
                if (snapshot == Mode.ON) {
                    System.out.println("advice active ref=" + methodArgs[0]);
                }
                return invokeTarget(target, method, methodArgs);
            }
        );

        System.out.println("phase OFF");
        proxy.pay("P1");

        MODE.set(Mode.SHADOW);
        System.out.println("phase SHADOW");
        proxy.pay("P2");

        MODE.set(Mode.ON);
        System.out.println("phase ON");
        proxy.pay("P3");

        MODE.set(Mode.OFF); // Kill switch minh họa.
        System.out.println("phase ROLLBACK");
        proxy.pay("P4");
        proxy.health();
    }
}
```

Biên dịch/chạy:

```bash
javac AopRolloutDemo.java
java AopRolloutDemo
```

**Standard output chính xác:**

```text
phase OFF
target pay P1
phase SHADOW
observe mode=SHADOW ref=P2
target pay P2
phase ON
observe mode=ON ref=P3
advice active ref=P3
target pay P3
phase ROLLBACK
target pay P4
target health
```

Diễn giải:

- Với **OFF**, gọi `pay` vẫn đi qua proxy/interceptor nhưng không in phần quan sát/advice; target luôn được gọi đúng một lần.
- Với **SHADOW**, có marker quan sát và target chạy bình thường; không thay đổi hành vi nghiệp vụ.
- Với **ON**, chạy thêm phần advice minh họa rồi gọi target đúng một lần.
- Sau khi chuyển về **OFF**, lời gọi tiếp theo không còn chạy phần logic advice; proxy vẫn tồn tại.
- Method `health()` không khớp pointcut minh họa và được ủy quyền thẳng tới target.

Đây là **ví dụ kiểm thử điều khiển**, không đại diện cho một hệ thống config phân tán hay code bảo mật production. Trong thực tế, không đưa ID nhạy cảm vào log; dùng histogram/counter với nhãn cardinality thấp và correlation ID bảo vệ phù hợp. `AtomicReference` ở đây chỉ quản lý snapshot của **một JVM**. Nó không tự đồng bộ cờ giữa instance, không loại bỏ weaving và không chặn các caller đang giữ tham chiếu target gốc.

Một phiên bản production của `around` còn phải giữ nguyên exception, return value và số lần `proceed()` theo hợp đồng, đồng thời đặt ghi nhận thời gian/cleanup trong `finally` khi cần. Tắt một flag không cho phép bỏ qua advice bảo vệ bắt buộc.

## 7. Giám sát: quan sát cả advice lẫn kết quả nghiệp vụ

Chỉ theo dõi số log của advice là không đủ. Ít nhất cần bốn lớp đo lường:

| Lớp | Metric/sự kiện | Câu hỏi trả lời |
| --- | --- | --- |
| **Rollout/config** | `aspect_version`, `rollout_mode`, config revision, số instance theo cohort | Có bao nhiêu process thực sự nhận cấu hình mới? |
| **AOP engine** | Số join point match, advice enter/exit, exceptions, `proceed()` count, depth | Advice được chọn đúng nơi, đúng lần và đúng thứ tự chưa? |
| **Hiệu năng** | p50/p95/p99 latency, CPU, allocations, GC, queue, I/O, exporter backlog | Weaving và advice làm hệ thống chậm hoặc quá tải không? |
| **Nghiệp vụ và an toàn** | Tỉ lệ lỗi, timeout, từ chối hợp lệ, kết quả giao dịch, duplicate side effects | Có thay đổi quyết định hoặc tính đúng đắn không? |

Dữ liệu nên chia theo **phiên bản artifact**, **cohort**, **vùng triển khai**, **aspect/pointcut ID**, **nhóm join point**, **mode**, nhưng hạn chế gắn nhãn số lượng lớn như user ID, email, payment ID hoặc stack trace vào metric. Những thông tin chi tiết có thể nằm trong trace/log có phân quyền và retention thích hợp.

**Đừng lấy số lần advice làm mẫu số cố định bằng request count.** Một request có thể đi qua nhiều join point hoặc nhiều attempt; một `around` có thể gọi `proceed()` nhiều lần; async callback có thể thuộc invocation khác. Nên định nghĩa tỷ lệ riêng:

- `advice_invocations / eligible_join_point_invocations` để ước lượng coverage.
- `business_errors / business_attempts` để theo dõi tỷ lệ lỗi nghiệp vụ.
- `duplicated_side_effects / confirmed_business_operations` khi có dữ liệu xác nhận.
- Overhead tương đối từ canary so với control group, với workload tương đồng.
- `config_applied_instances / expected_instances` để theo dõi mức lan truyền flag.

Các phép đo ở trên là **công thức ý nghĩa**, không phải quy tắc xác định mẫu số cho mọi hệ thống. Khi lọc nhóm canary, phải dùng cùng cửa sổ thời gian, đơn vị đo và các điều kiện loại trừ trên hai nhóm so sánh.

### 7.1. Trace mẫu

```text
seq=01 req=R8 inv=I1 app=v17 cohort=canary mode=SHADOW advice=AuditCheck phase=enter
seq=02 req=R8 inv=I1 app=v17 cohort=canary mode=SHADOW advice=AuditCheck phase=decision decision=would-allow
seq=03 req=R8 inv=I1 app=v17 cohort=canary mode=SHADOW advice=AuditCheck phase=exit outcome=success
```

Đây là **định dạng log minh họa**, không phải output của chương trình Java. Nó cho phép so sánh cùng một `invocationId` qua nhiều pha và xác định mode tại thời điểm bắt đầu. Trong log thật, không ghi dữ liệu người dùng nhạy cảm ở trường `decision` hay `args`; gộp theo loại quyết định, lưu tham chiếu truy vết với cơ chế bảo vệ phù hợp.

### 7.2. Cảnh báo và tiêu chí dừng

Định nghĩa sẵn **ngưỡng cảnh báo và điều kiện rollback** từ mức chịu đựng lỗi và baseline cụ thể, chẳng hạn:

- Lỗi/timeout, p99 latency hoặc CPU tăng vượt ngân sách đã phê duyệt trong một khoảng đủ mẫu.
- Phát hiện side effect trùng, mismatch quyền truy cập, vi phạm invariant, advice gọi `proceed()` sai số lần, hoặc vòng recursion.
- Mất sự kiện audit bắt buộc hay xuất hiện dữ liệu nhạy cảm trong log.
- Weaving có dấu hiệu không nhất quán: một số instance thiếu aspect, khác checksum artifact, agent không bật, hoặc config lag lâu hơn giới hạn.
- Không đủ số liệu xác thực canary do telemetry mất dữ liệu.

Với vi phạm bảo mật hoặc dữ liệu, **có thể cần dừng ngay** theo quy tắc nghiêm ngặt hơn ngưỡng thống kê hiệu năng. Quyền gọi kill switch và trách nhiệm xử lý incident phải được xác định trước; không buộc người vận hành tự suy đoán lúc sự cố xảy ra.

## 8. Giám sát và điều khiển trong hệ thống nhiều thread

Với Java concurrent/async code, lời gọi advice trên thread khác có thể được tính vào cùng một nghiệp vụ nhưng xảy ra sau khi mode được chuyển. Vì vậy:

- Truyền `requestId`, `rollout cohort` và cấu hình snapshot qua các ranh giới async khi contract yêu cầu một workflow dùng một chế độ thống nhất.
- Không giả định `ThreadLocal` được tự động sao chép sang thread của executor khác. Nếu dùng `ThreadLocal` để chống reentrancy, dọn trong `finally`.
- Đảm bảo telemetry vẫn ghi khi advice ném exception hoặc code bị hủy sớm.
- Phân biệt thời điểm **cập nhật flag**, **tiếp nhận invocation mới**, và **kết thúc các invocation đang chạy**.
- Đo số workflow đang ở mode cũ trước khi tiến hành bước phụ thuộc vào việc toàn bộ hệ thống đã chuyển sang mode mới.

Ngay cả khi một flag runtime được đồng bộ ngay giữa các JVM, những invocation đã đọc snapshot ON có thể hoàn tất logic advice sau thời điểm operator bấm OFF. Kill switch có thể **ngăn việc bắt đầu tác động mới**, nhưng không tự động đảo ngược side effect đã xảy ra.

## 9. Chiến lược rollback theo cơ chế AOP

### 9.1. Runtime flag hoặc proxy/interceptor

Nếu điểm chặn còn hoạt động và logic advice tự kiểm tra flag:

1. Chuyển mode về cấu hình an toàn đã định trước, thường là OFF cho instrumentation không thiết yếu, hoặc chính sách bảo vệ cũ/được phê duyệt đối với security advice.
2. Kiểm tra số instance nhận được config revision mới; yêu cầu xác nhận từ hệ thống config/telemetry.
3. Theo dõi sự suy giảm của số invocation chạy nhánh ON và chờ các workflow đang chạy hoàn tất nếu business contract đòi hỏi.
4. Nếu sự cố vẫn tiếp diễn do overhead proxy hoặc weaving, dùng rollback artifact thay vì lặp đi lặp lại thao tác flag.

**Giới hạn:** OFF trong advice không loại bỏ hoàn toàn interceptor, các điểm đã weave hoặc chi phí đi vào advice; nếu lỗi nằm ở class verification, initialization, classloader hay bytecode dệt, runtime flag có thể không cứu được.

### 9.2. Compile-time và post-compile weaving

Rollback thường là **phát hành lại artifact đã xác thực trước đó**:

```text
known-good artifact A  -- rollout -->  woven artifact B
                                      |
                             incident detected
                                      |
                                      v
                         deploy verified artifact A
                         + restore matching config
                         + verify business invariants
```

Giữ file JAR/class artifact theo hash và dependency lock, không chỉ source tag. Đặc biệt tránh dựng lại “bản cũ” bằng một toolchain khác mà chưa kiểm chứng: bytecode, dependency hoặc kết quả weaving có thể khác. Khi rollback trong hệ thống phân tán, các instance B có thể còn xử lý tác vụ trong lúc A được triển khai lại; contract dữ liệu và giao thức phải tương thích trong cửa sổ chuyển đổi.

Nếu deployment có database migration hay external side effects, rollback code **không tự hoàn tác** thay đổi schema, trạng thái transaction hoặc thông điệp đã gửi. Chuẩn bị migration theo hướng tương thích tiến/lùi và quy trình bù trừ khi nghiệp vụ cho phép; không suy luận rollback bytecode đồng nghĩa rollback dữ liệu.

### 9.3. Load-time weaving

Với LTW bằng Java agent, rollback có thể đòi hỏi:

- Sửa startup flags để dùng lại bộ agent/aspect/config đã biết tốt hoặc chạy không agent nếu kiến trúc cho phép.
- Khởi động tiến trình mới từ artifact/config đã được xác nhận.
- Drain traffic khỏi các tiến trình cũ và thay thế chúng; **lớp đã load thường không tự mất weaving khi chỉ xóa agent flag ở hệ thống cấu hình**.
- Xác nhận agent, classloader, `META-INF/aop.xml`, include/exclude pattern và class version được áp dụng đúng tại thời điểm load.

Một số nền tảng có khả năng retransformation/redefinition nhưng giới hạn riêng; **không mặc định** có thể unweave mọi lớp đang chạy. Nên thiết kế rollback LTW theo nguyên tắc thay tiến trình/lớp từ trạng thái sạch, trừ khi công cụ có cam kết cụ thể đã được thử nghiệm.

### 9.4. Quay lui theo nhóm máy hoặc phân vùng

Dùng rolling/canary rollback khi rủi ro đã được cô lập; chuyển toàn bộ hệ thống về known-good version khi phát hiện lỗi nghiêm trọng ảnh hưởng dữ liệu hoặc bảo mật. Ưu tiên cách ly các instance lỗi, giữ đủ năng lực tải trên nhóm còn lại, không để canary “đã tắt” nhưng vẫn nhận traffic từ một scheduler hoặc hàng đợi chưa được drain.

## 10. Runbook khi có sự cố AOP

Một runbook tối thiểu nên có các bước tác nghiệp cụ thể và điều kiện ra quyết định.

| Bước | Hành động | Bằng chứng cần lưu |
| --- | --- | --- |
| 1. Nhận diện | Xác nhận symptom, giai đoạn rollout, version, cohort và phạm vi ảnh hưởng | Dashboard snapshot, error examples, timestamp |
| 2. Khoanh vùng | So với control/previous version; đối chiếu pointcut và method chịu tác động | Trace đã ẩn dữ liệu nhạy cảm, match summary |
| 3. Quyết định | HOLD, tắt advice runtime, giảm cohort, hoặc rollback artifact/agent | Tiêu chí dừng đã định, người quyết định |
| 4. Thực thi | Áp dụng kill switch hoặc redeploy known-good; giữ đường config/ops khả dụng | Change ID, checksum, config revision |
| 5. Xác nhận | Kiểm tra instance đã cập nhật, telemetry và invariant nghiệp vụ | Phần trăm rollout thực, kết quả smoke test |
| 6. Khôi phục | Xử lý giao dịch lỗi/duplicate side effect nếu có; theo dõi dài hơn | Danh sách vụ việc, đối soát và tác vụ bù |
| 7. Rút kinh nghiệm | Cập nhật pointcut test, threshold, detection và playbook | Regression test, kế hoạch rollout mới |

Runbook cần trả lời cả câu hỏi **“Ai có quyền rollback?”**, **“Tắt tại đâu?”**, **“Làm sao biết đã tắt ở mọi nơi?”** và **“Các tác vụ đang chạy được xử lý thế nào?”**. Chỉ viết “tắt flag khi lỗi” không đủ khi một số lớp đã được weave, một số instance chưa nhận config hoặc security guard không được phép fail-open.

## 11. Kiểm thử bắt buộc trước khi phát hành

### 11.1. Kiểm thử đúng phạm vi pointcut

- **Positive:** phương thức cần advice nhận đúng advice, đúng số lần, đúng kiểu join point.
- **Negative:** phương thức không thuộc phạm vi không có side effect từ advice.
- **Boundary:** overload, generic bridge method, interface/implementation, self-invocation, method modifiers và classloader khi cơ chế AOP liên quan.
- **Recursion:** helper được advice gọi không tạo vòng lặp advice vô hạn; các trường hợp `proceed()` nhiều lần phải có contract và idempotency rõ.
- **Ordering:** trước/sau với nhiều `around` và `before`/`after` theo precedence cụ thể; kiểm tra cả đường exception.

### 11.2. Kiểm thử chức năng các mode

Test một invocation đại diện trong `OFF`, `SHADOW`, `ON` và sau rollback, so:

- Số lần target được gọi, return value và loại exception.
- Side effect thực tế trong từng mode.
- Việc shadow có giữ nguyên quyết định nghiệp vụ.
- Thời điểm chuyển flag và hành vi của invocation đã bắt đầu.
- Log/metric có đúng version, mode, cohort, advice ID.

Không viết test “OFF không có advice” bằng cách chỉ kiểm tra **không xuất hiện log**; cần quan sát được cả việc đường nghiệp vụ diễn ra đúng và các thao tác có side effect không được thực thi.

### 11.3. Kiểm thử vận hành

- Triển khai canary nhỏ rồi quay lui trên môi trường tương đương production.
- Ngắt tạm dịch vụ cấp flag để kiểm tra fallback đã định.
- Tạo concurrency/async load để kiểm tra context, overhead, queue, latency, CPU và GC.
- Nếu CTW/PCW: xác nhận JAR/bytecode artifact đúng version; test chính artifact sẽ phát hành.
- Nếu LTW: test command line/agent/classloader y như khi deploy; reboot/restart để xác nhận điểm weave xuất hiện đúng.
- Đối với transaction/security advice: mô phỏng exception giữa chuỗi, dependency timeout và partial completion; kiểm tra không làm mất audit/quyền hoặc nhân bản side effect.

## 12. Những sai lầm thường gặp

1. **Bật trên 100% instance ngay sau unit test.** Unit test hiếm khi phản ánh số join point thực tế, contention và chi phí exporter dưới tải.
2. **Cho rằng flag OFF tháo bỏ weaving.** Nó chỉ bỏ hành vi có nhánh được kiểm tra; bytecode và interception boundary vẫn có thể tồn tại.
3. **Tính rollout 5% trên mỗi invocation độc lập.** Một workflow nhiều bước có thể chạy hai mode khác nhau, gây trạng thái không nhất quán.
4. **Chỉ nhìn metric của aspect.** Advice vẫn in log đúng nhưng có thể nhân đôi giao dịch, thay đổi exception hoặc tăng latency nghiệp vụ.
5. **Dùng user ID làm nhãn metric.** Cardinality cao và nguy cơ lộ dữ liệu; phân nhóm theo cohort và type, giữ định danh chi tiết trong trace có bảo vệ.
6. **Dùng shadow nhưng vẫn gọi `proceed()` hai lần để so sánh.** Có thể nhân đôi cập nhật dữ liệu; shadow phải tính toán không tạo side effect nghiệp vụ.
7. **Rollback code mà quên dữ liệu.** Side effect đã thực hiện, tin nhắn đã gửi và migration không tự đảo ngược.
8. **Không kiểm tra lớp đã load trong LTW.** Đổi file cấu hình không có nghĩa class hiện tại được unweave.
9. **Fail-open với authorization để giảm lỗi.** Phải tuân thủ chính sách an toàn đã định; việc rollback không được làm mất kiểm soát bắt buộc.
10. **Không truyền version/mode vào telemetry.** Không thể phân biệt cohort, instance hoặc advice cũ/mới khi xem trace.
11. **Lấy thiếu lỗi trong vài phút làm bằng chứng thành công.** Cần đủ mẫu và bao phủ các nhánh nghiệp vụ có ý nghĩa.
12. **Cho rằng mọi proxy đều giống nhau.** Giới hạn của delegation proxy, subclass interception và bytecode weaving khác nhau, nên thủ tục rollback cũng khác.

## 13. Checklist triển khai và quay lui

### Trước rollout

- [ ] Xác định rõ pointcut, loại join point, advice type và tập class/method dự kiến bị tác động.
- [ ] Phân loại advice là quan sát, thay đổi luồng điều khiển, ghi side effect hay bảo vệ bắt buộc.
- [ ] Khóa artifact version, cấu hình weaving, agent và policy; biết chính xác output production đang chạy.
- [ ] Thiết lập baseline và control group hợp lý, dashboard theo cohort/version, tiêu chí dừng đã thống nhất.
- [ ] Đã thử OFF → SHADOW → ON → OFF và smoke test dương/âm, exception, concurrency nếu có.
- [ ] Đã diễn tập rollback thực tế cho đúng cơ chế: flag, proxy config, CTW/PCW artifact hoặc LTW restart.
- [ ] Đã xác minh log/metric không tiết lộ dữ liệu nhạy cảm và không tạo recursion.

### Trong rollout

- [ ] Tăng tỷ lệ theo giai đoạn, cố định cohort cho workflow cần tính nhất quán.
- [ ] So sánh latency/error/side effects, số match, `proceed()` và mức lan truyền config trên từng nấc.
- [ ] HOLD khi thiếu telemetry/đủ mẫu hoặc khi vi phạm ngưỡng; không tự mở rộng ngoài tiêu chí.
- [ ] Có operator/owner trực và đã chuẩn bị sẵn lệnh rollback, artifact known-good.

### Sau rollback hoặc hoàn tất

- [ ] Xác nhận thực trạng từng instance, JVM/classloader và config revision; không dựa riêng vào “flag đã chuyển”.
- [ ] Kiểm tra hệ thống quay về chỉ số ổn định và business invariants được bảo toàn.
- [ ] Đối soát dữ liệu/tác vụ đã ảnh hưởng; xử lý bù trừ nếu nghiệp vụ yêu cầu.
- [ ] Lưu evidence: trace, log đã ẩn dữ liệu, artifact hash, các bước đã chạy và thời điểm.
- [ ] Bổ sung regression test và điều chỉnh phạm vi pointcut/giới hạn rollout trước lần bật tiếp theo.

**Ghi nhớ:** bật AOP theo giai đoạn là kiểm soát **phạm vi tác động của advice** và **phân bố phiên bản thực tế đang chạy**. Giám sát phải chứng minh nghiệp vụ đúng, còn rollback phải phù hợp với cách aspect được gắn vào luồng thực thi. Một nút OFF chỉ hiệu quả trong phạm vi mà cơ chế AOP và hợp đồng an toàn thực sự cho phép.
