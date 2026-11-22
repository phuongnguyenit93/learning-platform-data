# Không dùng Aspect để che giấu thiếu sót trong hợp đồng nghiệp vụ

## 1. Vấn đề cốt lõi

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming — **AOP**), một **Aspect** đóng gói hành vi xuất hiện ở nhiều vị trí thực thi: đo thời gian, ghi nhận sự kiện, quản lý ngữ cảnh truy vết, giới hạn tài nguyên hoặc áp dụng chính sách kỹ thuật đã được định nghĩa. **Advice** được chạy tại các **join point** do **pointcut** lựa chọn; tùy cơ chế AOP, advice có thể thực thi trước, sau hoặc bao quanh lời gọi/phần thực thi được chọn.

Khả năng chèn hành vi mà không sửa thân phương thức rất hữu ích, nhưng cũng nguy hiểm: chỉ một Aspect có thể thay đổi tham số, bỏ qua một lần gọi, nuốt exception, sửa giá trị trả về, tự retry hoặc làm phát sinh side effect. Nếu các thay đổi này ngầm “vá” một API không rõ nghĩa hay một mô hình nghiệp vụ thiếu điều kiện, người đọc mã nghiệp vụ sẽ không thấy hợp đồng thực sự đang được thực thi.

**Nguyên tắc:** hợp đồng nghiệp vụ phải tồn tại và được hiểu một cách tường minh ở nơi định nghĩa/người sử dụng API, dù việc kiểm tra một số điều kiện có được tái sử dụng qua cơ chế AOP hay không. Aspect không nên biến một thao tác sai theo hợp đồng thành một thao tác có vẻ thành công, hoặc bổ sung một nghĩa nghiệp vụ mới mà caller không hề biết.

Ví dụ, nếu chuyển tiền yêu cầu `amount > 0` và đủ số dư, một advice âm thầm biến `amount = -100` thành `100` không phải “xử lý kỹ thuật”; đó là đổi ý nghĩa lệnh chuyển tiền. Nếu một Aspect bắt lỗi `InsufficientFunds` rồi trả “thành công” mặc định, dữ liệu báo cáo và hành vi của khách hàng sẽ không còn khớp với số dư thực tế.

Bài này trình bày cách nhận diện ranh giới ấy trong **AOP nói chung**, cách thiết kế hợp đồng, cách phân loại chính sách thực thi, ví dụ Java 17+ chạy được và chiến lược kiểm thử đối với advice.

## 2. Hợp đồng nghiệp vụ là gì?

Hợp đồng mô tả điều bên gọi **được phép yêu cầu**, điều bên cung cấp **cam kết thực hiện**, và điều gì xảy ra khi yêu cầu không hợp lệ hoặc không thể hoàn thành. Nó bao gồm cả các quy tắc không được ghi bằng ngôn ngữ lập trình cụ thể.

### 2.1. Các lớp của hợp đồng

| Thành phần | Câu hỏi cần trả lời | Ví dụ trong chuyển tiền |
| --- | --- | --- |
| **Tiền điều kiện (preconditions)** | Lệnh đầu vào nào hợp lệ? | Số tiền dương, tài khoản nguồn/đích hợp lệ, không trùng nhau |
| **Bất biến (invariants)** | Trạng thái nào luôn phải được duy trì? | Không tạo số dư âm nếu sản phẩm cấm thấu chi; bảo toàn giá trị khi chuyển nội bộ |
| **Hậu điều kiện (postconditions)** | Sau thành công, điều gì phải đúng? | Ghi nợ nguồn và ghi có đích đúng số tiền |
| **Semantics của lỗi** | Thao tác thất bại được báo thế nào? | Lệnh không hợp lệ ném lỗi; thiếu tiền không chuyển phần còn lại |
| **Tính nguyên tử và side effect** | Khi lỗi ở giữa, phần việc nào được giữ? | Không ghi nợ nguồn nếu ghi có đích chưa thể thực hiện theo hợp đồng nguyên tử |
| **Idempotency** | Gửi lại cùng một lệnh có được tính lại không? | Cùng request key, cùng nội dung được trả lại kết quả cũ theo quy tắc đã công bố |
| **Quyền hạn** | Ai được thực hiện thao tác nào? | Chỉ chủ tài khoản hoặc chủ thể được ủy quyền |
| **Thời gian và đồng thời** | Timeout, thứ tự và cạnh tranh được xử lý ra sao? | Timeout không tự khẳng định giao dịch đã bị rollback |
| **Khả năng quan sát** | Caller nhìn thấy trạng thái nào? | Success, rejected, pending, unknown, duplicate |

Một phương thức có thể có hợp đồng bằng kiểu dữ liệu, tài liệu API, tên hành động, exception hoặc kết quả có cấu trúc. Hợp đồng không nhất thiết phải là một file tài liệu riêng, nhưng phải **có thể tìm thấy, kiểm chứng và hiểu** bởi người gọi lẫn người bảo trì.

### 2.2. “Chạy đúng” không có nghĩa “đúng hợp đồng”

Giả sử lệnh `reserve(item, quantity)` được gọi với `quantity = 0`. Một Aspect tự đổi thành `1` có thể làm thao tác “chạy được” và không ném lỗi, nhưng người gọi vừa bị đặt trước một hành vi khác với yêu cầu. Tương tự, nếu API hứa ném exception khi thiếu quyền, advice trả giá trị rỗng khiến lỗi quyền truy cập bị diễn giải thành “không có dữ liệu”.

Khi Aspect làm thay đổi dữ liệu quan trọng, sự thành công bề ngoài có thể che giấu:

- Thiết kế kiểu dữ liệu thiếu miền giá trị hợp lệ.
- Thiếu xác thực ở đầu vào thực tế (kể cả lời gọi nội bộ không qua advice).
- Sai bất biến ở tầng domain/service.
- Quy tắc idempotency không được khai báo.
- Lỗi side effect, transaction boundary, consistency hoặc timeout chưa có hợp đồng.
- Exception bị dịch sai từ “không được phép” sang “không tìm thấy” hoặc từ “chưa biết kết quả” sang “thất bại chắc chắn”.

Aspect không phải nơi thay thế việc định nghĩa các điểm trên.

## 3. Phân công trách nhiệm: domain, API và Aspect

Một cách kiểm tra thực tế là hỏi: **Nếu tắt cơ chế weaving hoặc gọi nghiệp vụ bằng một đường không đi qua Aspect, quy tắc đó có còn đúng không?** Với bất biến cốt lõi của domain, câu trả lời cần là **có**. Một Aspect có thể áp dụng thêm lớp kiểm tra ở ranh giới nhưng hệ thống không được mất tính đúng đắn của domain chỉ vì advice không chạy.

### 3.1. Quy tắc nên nằm ở domain/API

Các ví dụ điển hình:

- Tài khoản phải có đủ tiền trước khi ghi nợ.
- Không được đặt hàng với số lượng bằng 0 nếu hợp đồng yêu cầu số lượng dương.
- Trạng thái đơn hàng không được chuyển trực tiếp từ `CANCELLED` sang `SHIPPED`.
- Phép tính giá/thuế/chiết khấu phải đúng theo quy tắc nghiệp vụ.
- Yêu cầu tạo thanh toán cần khóa idempotency theo hợp đồng, không chỉ “đoán retry rồi tránh ghi trùng”.
- Đường chuyển đổi giữa thành công, từ chối và kết quả chưa rõ phải được mô tả cụ thể.

Những quy tắc này tác động đến **ý nghĩa** của hành động và dữ liệu; nên xuất hiện qua domain model, application service, API contract và bài kiểm thử tương ứng.

### 3.2. Mối quan tâm cắt ngang phù hợp với Aspect

Các ví dụ thường phù hợp hơn:

- Đo elapsed time, tăng counter, gắn trace/correlation context, ghi audit/diagnostic event theo chính sách đã công bố.
- Chuẩn hóa một cấu trúc telemetry không làm lộ tham số nhạy cảm.
- Kiểm soát kỹ thuật như rate limiting hoặc concurrency cap **khi contract đã nói rõ** lệnh có thể bị từ chối/quá tải.
- Quản lý tracing context, deadline hoặc cơ chế dọn dẹp tài nguyên thuộc lớp điều phối.
- Chuyển exception kỹ thuật thành một loại lỗi **đã nằm trong API contract** ở đúng ranh giới, giữ nguyên nguyên nhân và trạng thái nghiệp vụ.
- Thực thi chính sách kiểm tra truy cập **được đặc tả rõ** và được bao phủ bởi các đường gọi tin cậy.

Danh sách này không biến các chính sách thành “thuần kỹ thuật” trong mọi hệ thống. **Quyền truy cập, quota, deadline và transaction** đôi khi là một phần hợp đồng nghiệp vụ. Khi đó, hành vi nhìn thấy bởi caller phải được tài liệu hóa và kiểm thử như hợp đồng công khai, dù chi tiết thực thi có thể được tái sử dụng qua Aspect.

### 3.3. Bảng quyết định nhanh

| Nếu một advice đang… | Nguy cơ | Thiết kế tốt hơn |
| --- | --- | --- |
| Biến số tiền âm thành số dương | Đổi ngữ nghĩa lệnh | Kiểu `Money`/validation trong domain; trả lỗi rõ |
| Nuốt lỗi và trả đối tượng “OK” giả | Che lỗi và tạo thông tin sai | Giữ exception/kết quả lỗi theo hợp đồng |
| Retry thao tác có side effect | Có thể thực thi hai lần | Quy tắc retry và idempotency được đặc tả, chỉ retry thao tác an toàn |
| Đổi lỗi “chưa biết kết quả” thành “chắc chắn thất bại” | Caller gửi lại gây tác dụng kép | Trạng thái `UNKNOWN/PENDING` và cơ chế reconciliation |
| Tự mở/đóng transaction quanh một phần thao tác | Hiểu sai atomicity | Định nghĩa transaction boundary từ use case và nguồn dữ liệu |
| Tự thêm default value thiếu trong API | Che tiền điều kiện thiếu | API định nghĩa default rõ hoặc yêu cầu caller cung cấp |
| Tự gắn nhãn log và metric | Thường ít ảnh hưởng nghiệp vụ | Giữ telemetry độc lập và quan sát được lỗi của chính nó |
| Từ chối theo quota đã công bố | Là chính sách có thể nhìn thấy | Trả lỗi quá tải đã định nghĩa; nêu đơn vị tính/quota/retry-after |
| Kiểm tra quyền theo rule đã công bố | Có thể hợp lệ nhưng nhạy cảm | Giữ bảo vệ ở mọi đường truy cập, kiểm thử bypass và fail-closed đúng chính sách |

Điểm quyết định không phải tên gọi “business” hay “technical”, mà là **hợp đồng có thay đổi hay không, ai sở hữu quy tắc, người gọi có thể dự đoán và kiểm thử nó hay không**.

## 4. Advice có thể làm sai hợp đồng bằng cách nào?

### 4.1. Thay đổi tham số mà caller không biết

Around advice thường có khả năng thay lời gọi bằng một bộ tham số khác. Điều này hữu ích cho các hành động kỹ thuật rõ nghĩa, nhưng nguy hiểm nếu thao tác biến dữ liệu nghiệp vụ. Ví dụ sau là **đoạn minh họa anti-pattern, không phải chương trình độc lập**:

~~~java
// SAI: advice tu "chua" lenh chuyen tien sai nghia.
long amount = (long) args[2];
args[2] = Math.abs(amount);
return proceed(args);
~~~

Lệnh chuyển tiền `-100` đáng ra bị từ chối đã biến thành lệnh chuyển `100`. Ngoài ra, `Math.abs(Long.MIN_VALUE)` vẫn cho ra số âm do overflow, nên ngay cả “chuẩn hóa” này cũng không toàn vẹn. Giải pháp là để domain từ chối giá trị không hợp lệ và giải thích lỗi trong hợp đồng.

Một việc như trim một identifier theo chuẩn chung cũng chỉ được phép nếu hợp đồng nói rõ identifier được normalize thế nào. Không phải phép biến đổi “nhỏ” nào cũng vô hại: khoảng trắng, chữ hoa/thường và Unicode normalization có thể ảnh hưởng định danh, chữ ký hoặc khóa truy cập.

### 4.2. Nuốt, dịch sai hoặc làm mất nguyên nhân lỗi

Around advice có thể bắt exception; điều này không cấp quyền trả success giả. Xét lệnh `pay()` ném lỗi do không đủ tiền. Nếu advice bắt tất cả lỗi rồi trả `PaymentResult.success()`, caller sẽ xác nhận đơn hàng đã thanh toán dù chưa có tiền chuyển.

Dịch exception kỹ thuật có thể hợp lý ở **ranh giới đã quy định**: ví dụ một lỗi I/O đặc thù được đóng gói thành lỗi `STORAGE_UNAVAILABLE` theo API. Khi dịch, cần giữ `cause`, phân biệt lỗi tạm thời với lỗi do caller và không nuốt tín hiệu `InterruptedException`. `catch (Throwable)` rồi bỏ qua có thể vô tình che lỗi JVM nghiêm trọng.

Nếu một lần gọi bị timeout, có thể chưa biết side effect có được thực hiện ở hệ thống khác hay không. Không tùy tiện gán kết quả “không xảy ra”; hợp đồng có thể cần trạng thái “chưa rõ” và truy vấn/reconcile.

### 4.3. Retry làm thay đổi số lần thực hiện

Một advice retry có thể biến một lần gọi API thành nhiều lần chạy domain. Với lệnh đọc bất biến và an toàn, retry có thể hợp lệ trong ngân sách đã công bố. Với lệnh ghi:

~~~text
Caller gọi charge(100) một lần
   -> Advice gọi charge(100) lần 1: hệ thống từ xa đã ghi tiền,
      nhưng phản hồi bị mất
   -> Advice tự retry lần 2: hệ thống từ xa ghi tiền thêm lần nữa
   -> Caller nhận “thành công” nhưng bị tính tiền hai lần
~~~

Retry phải dựa vào **semantics của operation**, loại lỗi, deadline và idempotency token ổn định, chứ không chỉ việc một exception xuất hiện. Việc retry có thể nằm trong Aspect nhưng **chính sách retry, tính idempotent và tình huống kết quả chưa rõ phải có trong hợp đồng API**.

### 4.4. Cache che giấu trạng thái mới

Một Aspect cache không khai báo có thể trả dữ liệu stale cho nghiệp vụ đòi consistency mạnh, nhất là khi cập nhật quyền, tồn kho hoặc trạng thái giao dịch. Nếu domain cho phép eventual consistency hoặc stale-while-revalidate, hãy đưa tính chất đó vào hợp đồng: cache key, TTL, invalidation, chủ sở hữu và các lệnh buộc bypass.

Không giả định tất cả phương thức có cùng tên “get” đều có tính pure hoặc có thể cache. Các method getter đôi khi có side effect, context-dependent authorization hoặc dữ liệu theo thời gian.

### 4.5. Transaction và các ranh giới không cùng nhau

Advice bắt đầu và kết thúc một transaction kỹ thuật không tự giải quyết nguyên tử nghiệp vụ khi có nhiều nguồn dữ liệu, hàng đợi thông điệp hoặc dịch vụ từ xa. Nếu use case đòi “ghi đơn hàng và xuất sự kiện” có tính nhất quán, cần thiết kế outbox, compensation hoặc mô hình nhất quán tương ứng. Aspect bọc lời gọi không làm cho các side effect phân tán trở thành một transaction nguyên tử.

Trong lời gọi bất đồng bộ, transaction/resource context của luồng gọi có thể kết thúc trước khi worker hoàn tất. Cần định nghĩa rõ đơn vị công việc, luồng sở hữu tài nguyên và thời điểm kết thúc; không dùng around advice đồng bộ như lời hứa tự động “tất cả đều nằm trong một transaction”.

## 5. Ví dụ Java 17+: bảo toàn hợp đồng khi thêm Aspect quan sát

Ví dụ mô phỏng chuyển tiền đơn giản bằng số nguyên `long` biểu diễn **đơn vị nhỏ nhất của tiền**. Hợp đồng của `TransferService.transfer()`:

1. `amountCents` phải dương.
2. Hai tài khoản phải tồn tại, khác nhau và nguồn phải đủ số dư.
3. Nếu dữ liệu đầu vào sai, thao tác ném `IllegalArgumentException` và không sửa số dư.
4. Nếu không đủ tiền, thao tác ném `IllegalStateException` và không sửa số dư.
5. Thành công ghi nợ/ghi có đúng số tiền và trả một `Receipt`.
6. Aspect chỉ đo số lời gọi và số lỗi; không sửa input, không retry, không đổi kết quả hoặc exception.

Ví dụ chạy tuần tự để tập trung vào hợp đồng; một ledger dùng chung nhiều luồng cần bổ sung đồng bộ/transaction thích hợp. Tạo file `BusinessContractAspectDemo.java`:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

public class BusinessContractAspectDemo {
    interface TransferService {
        Receipt transfer(String from, String to, long amountCents);
    }

    record Receipt(String from, String to, long amountCents) { }

    static final class Ledger implements TransferService {
        private final Map<String, Long> balances = new HashMap<>();

        Ledger() {
            balances.put("A", 1_000L);
            balances.put("B", 100L);
        }

        @Override
        public Receipt transfer(String from, String to, long amountCents) {
            if (amountCents <= 0 || from == null || to == null
                    || from.equals(to) || !balances.containsKey(from)
                    || !balances.containsKey(to)) {
                throw new IllegalArgumentException("invalid transfer");
            }

            long available = balances.get(from);
            if (available < amountCents) {
                throw new IllegalStateException("insufficient funds");
            }

            // Tính và kiểm tra cả hai kết quả TRƯỚC khi thay đổi state:
            // nếu Math.addExact ném vì overflow, số dư vẫn nguyên.
            long newFrom = available - amountCents;
            long newTo = Math.addExact(balances.get(to), amountCents);
            balances.put(from, newFrom);
            balances.put(to, newTo);
            return new Receipt(from, to, amountCents);
        }

        long balance(String account) {
            return balances.get(account);
        }
    }

    static final class ObserveAdvice implements InvocationHandler {
        private final TransferService target;
        private final AtomicLong invocations = new AtomicLong();
        private final AtomicLong failures = new AtomicLong();

        ObserveAdvice(TransferService target) {
            this.target = target;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            invocations.incrementAndGet();
            boolean completed = false;
            try {
                Object result = method.invoke(target, args);
                completed = true;
                return result;
            } catch (InvocationTargetException e) {
                throw e.getCause();
            } finally {
                if (!completed) {
                    failures.incrementAndGet();
                }
            }
        }

        String counters() {
            return "calls=" + invocations.get()
                    + ", failures=" + failures.get();
        }
    }

    public static void main(String[] args) {
        Ledger ledger = new Ledger();
        ObserveAdvice advice = new ObserveAdvice(ledger);
        TransferService observed = (TransferService) Proxy.newProxyInstance(
                TransferService.class.getClassLoader(),
                new Class<?>[] { TransferService.class },
                advice);

        try {
            observed.transfer("A", "B", -50);
        } catch (IllegalArgumentException e) {
            System.out.println("rejected: " + e.getMessage());
        }

        System.out.println("after rejected: A=" + ledger.balance("A")
                + ", B=" + ledger.balance("B"));

        Receipt result = observed.transfer("A", "B", 250);
        System.out.println("accepted: " + result);
        System.out.println("after accepted: A=" + ledger.balance("A")
                + ", B=" + ledger.balance("B"));
        System.out.println("observed: " + advice.counters());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac BusinessContractAspectDemo.java
java BusinessContractAspectDemo
~~~

Kết quả mong đợi (**stdout chính xác khi chạy tuần tự**):

~~~text
rejected: invalid transfer
after rejected: A=1000, B=100
accepted: Receipt[from=A, to=B, amountCents=250]
after accepted: A=750, B=350
observed: calls=2, failures=1
~~~

Ý nghĩa của ví dụ:

- Từ chối lệnh âm là **quy tắc của `Ledger`**, không dựa vào proxy. Gọi trực tiếp `ledger.transfer(...)` vẫn có cùng hợp đồng.
- Aspect quan sát không biến `-50` thành `50`, không giấu `IllegalArgumentException`, không ghi “thành công” giả.
- Với JDK dynamic proxy, `InvocationTargetException` do reflection tạo ra được bóc để caller nhận **nguyên nhân gốc**. Việc bóc wrapper này bảo toàn semantics exception, khác với việc thay nguyên nhân nghiệp vụ.
- `invocations=2` và `failures=1` chỉ là telemetry; không ảnh hưởng số dư.
- Mã chỉ mô tả ledger in-memory cho mục đích học tập. Phép cộng được kiểm tra **trước cả hai lần cập nhật**, nên nếu phép cộng bị overflow, ví dụ tuần tự chưa sửa bất cứ số dư nào. Trong sản phẩm thực, vẫn cần định nghĩa lỗi số học trong hợp đồng, xử lý concurrency, durability, transaction và idempotency phù hợp.
- Proxy chặn **các lời gọi đi qua interface proxy**. Nó không tự động chặn mọi self-call trong đối tượng mục tiêu hay mọi đường gọi khác.

Một nguyên tắc hữu ích khi review code là so sánh hai lối gọi: `ledger.transfer(...)` trực tiếp và `observed.transfer(...)` qua Aspect. **Dữ liệu trả về, thay đổi trạng thái và exception theo hợp đồng phải tương đương**, ngoại trừ những tác dụng kỹ thuật được định nghĩa rõ như telemetry hoặc từ chối theo quota công khai.

## 6. Tách business validation và cross-cutting validation

Không phải cứ có “validation” là bắt buộc viết tay trong từng method, và cũng không phải mọi validation có thể đưa vào một Aspect chung. Cần phân biệt:

### 6.1. Validation mang nghĩa nghiệp vụ

Ví dụ:

- `amountCents > 0`.
- Trạng thái `PAID` chỉ được chuyển thành `REFUNDED` theo chính sách hoàn tiền.
- Sản phẩm thuộc một phân khúc khách hàng cụ thể mới đủ điều kiện đặt mua.
- Yêu cầu hoàn tiền không vượt phần tiền thực sự đã thanh toán.

Các quy tắc này thường phụ thuộc entity, trạng thái và use case. Chúng phải được thể hiện ở domain model hoặc application service, được kiểm thử độc lập và vẫn đúng trên các đường chạy không có weaving.

### 6.2. Kiểm tra tại ranh giới có thể dùng lại

Một kiểm tra về kích thước payload, định dạng headers hoặc bộ quy tắc ủy quyền chung có thể được áp dụng bởi interceptor/Aspect để tránh lặp mã. Tuy vậy:

- Phải có **đặc tả công khai** ở API hoặc policy mà caller có thể hiểu.
- Điểm chặn phải bao phủ **mọi đường truy cập yêu cầu bảo vệ**; bypass không được trở thành lỗ hổng.
- Một rule an toàn quan trọng không nên chỉ phụ thuộc vào một proxy dễ bị gọi vượt.
- Kết quả từ chối có mã lỗi rõ, không bị biến thành dữ liệu “rỗng” hay success giả.
- Các bất biến domain vẫn được kiểm tra tại nơi sở hữu dữ liệu khi cần thiết.

Nếu Aspect thực thi authorization, nó đang triển khai một hợp đồng có thể quan sát được; việc logic chạy qua advice không khiến yêu cầu phân quyền trở thành chi tiết ẩn. Trong những hệ thống có nhiều đường vào, cần phân lớp ranh giới kiểm tra và bảo vệ domain ở nơi thích hợp.

## 7. Cách viết hợp đồng trước khi gắn Aspect

Một quy trình ra quyết định hữu ích:

1. **Nêu use case và trạng thái:** lệnh làm gì, entity nào chịu tác động, invariant nào phải luôn đúng.
2. **Định nghĩa API rõ ràng:** kiểu tham số/giá trị trả về, tiền điều kiện, các loại lỗi, sự kiện phụ, chính sách retry, timeout và idempotency.
3. **Viết bài kiểm thử hợp đồng không cần Aspect:** đặc biệt với dữ liệu xấu, race condition và lỗi giữa chừng.
4. **Liệt kê mối quan tâm cắt ngang:** telemetry, tracing, quota chung, context propagation hoặc mapping lỗi kỹ thuật phù hợp.
5. **Thiết kế advice chỉ trong quyền hạn đã mô tả:** nêu rõ có được đổi args, chặn lời gọi, trả fallback hay retry không; mặc định không thực hiện những việc đó.
6. **Kiểm tra chênh lệch hành vi trước/sau khi weave:** input, output, exception, side effect, số lần thực thi và latency.
7. **Đảm bảo đường gọi ngoài advice không phá bất biến:** bao gồm internal calls, đường chạy test, tác vụ async hoặc lời gọi trực tiếp.
8. **Đưa chính sách vào tài liệu vận hành và observability:** người bảo trì biết vì sao một lời gọi bị từ chối/quá hạn và xác định được policy nào gây ra.

Một hợp đồng tốt có thể dùng cấu trúc sau:

~~~text
Operation: transfer(from, to, amount)
Preconditions: from/to ton tai va khac nhau; amount > 0
Success: tru from, cong to, tra Receipt
Failure: invalid transfer / insufficient funds / unknown outcome
Side effects: so du thay doi dung mot lan khi thanh cong
Retry: chi duoc phep khi co idempotency key theo hop dong
Timeout: khong tu suy ra rollback neu ket qua chua ro
Cross-cutting: tracing, counters; quota neu duoc API cong bo
~~~

Đây là tài liệu gợi ý, không phải lời hứa rằng đoạn ledger demo đã hỗ trợ retry, idempotency key hay hệ thống phân tán. Các trường chỉ nên được gán giá trị đúng với API thực tế; khi chưa được thiết kế phải ghi rõ là chưa hỗ trợ.

## 8. Exception translation, fallback và API compatibility

### 8.1. Khi nào được dịch lỗi?

Việc chuyển một lỗi hạ tầng cụ thể sang lỗi API ổn định có thể giúp caller không phụ thuộc thư viện thấp tầng. Ví dụ, hợp đồng có mã `STORAGE_UNAVAILABLE` cho lỗi kết nối storage. Advice ở đúng ranh giới có thể ánh xạ lỗi tương ứng, giữ cause để phân tích, ghi metric và không mất thông tin thành công/thất bại.

Không nên chuyển mọi `RuntimeException` thành “không tìm thấy dữ liệu”, vì những exception đó có thể là bug, lỗi validation hay lỗi authorization. Cách dịch phải có bảng ánh xạ cụ thể, và các trường hợp không nhận diện phải có hướng xử lý rõ.

### 8.2. Fallback là một kết quả nghiệp vụ

Một Aspect trả dữ liệu cache khi downstream lỗi đang áp dụng semantics **stale data được chấp nhận**. Điều đó phải được caller biết: dữ liệu cũ đến mức nào, có dấu hiệu stale không, những operation nào được phép fallback. Nếu API hứa dữ liệu tức thời, fallback lén có thể gây quyết định sai.

Nếu fallback thay thế một lệnh ghi, đặc biệt cần thận trọng: “giả lập success” cho một thao tác chưa được xác nhận thường không thể chấp nhận. Một trạng thái `QUEUED` hoặc `PENDING` có thể phù hợp hơn **nếu đã nằm trong hợp đồng** và có cơ chế hoàn tất về sau.

### 8.3. Hợp đồng cũ và tương thích ngược

Thêm một Aspect tưởng chỉ để “chuẩn hóa” có thể là breaking change:

- Một exception trước đây được ném nay bị nuốt.
- Caller trước đây nhận `null` nay bị ném exception, hoặc ngược lại.
- Một lệnh thành công trước đây nay bị giới hạn tốc độ.
- Tác vụ bị retry và có side effect gấp đôi.
- Khi tracing advice bổ sung context vào thread-local, luồng async nhận trạng thái khác nếu cleanup không đúng.

Đánh giá thay đổi theo **observable behavior** và API versioning. Không coi việc mã của method gốc không đổi là bằng chứng “không có thay đổi hợp đồng”.

## 9. Đặc biệt nguy hiểm tại ranh giới bất đồng bộ

Một method có thể trả `Future<Result>` ngay khi công việc chưa kết thúc. Around advice đồng bộ có thể quan sát được “trả handle thành công” nhưng không phải “business operation thành công”.

Ví dụ, advice:

~~~java
// Minh hoa logic sai, khong la chuong trinh doc lap:
Object handle = proceed();
audit("business-success"); // SAI neu handle chi la Future chua hoan tat
return handle;
~~~

Nếu worker sau đó thất bại, audit “business-success” sai thực tế. Muốn báo trạng thái nghiệp vụ, gắn observer vào **completion phù hợp**, giữ nguyên semantics hủy/lỗi và tránh để lỗi telemetry làm hỏng handle.

Những bẫy khác:

- **Timeout không đồng nghĩa rollback:** caller ngừng chờ không chứng minh thao tác nền hoặc lệnh từ xa đã dừng.
- **Cancel không đồng nghĩa resource đã đóng:** worker có thể còn đang xử lý dọn dẹp.
- **Callback có thể chạy trên luồng khác:** context/authorization/transaction không tự chuyển theo `ThreadLocal`.
- **Retry async có thể nhân side effect:** cùng operation ID/idempotency key phải được giữ theo contract, và chỉ retry khi trạng thái cho phép.
- **Tác vụ fan-out:** một nhánh lỗi không tự quyết định toàn bộ operation thất bại hoặc rollback; cần chính sách tổ hợp được đặc tả.

Đừng để một Aspect biến “đã nhận yêu cầu” thành “đã hoàn tất nghiệp vụ”. Nếu API mang kiểu `CompletionStage<Receipt>`, hợp đồng phải nói rõ stage thành công khi nào, exception nào được phát, trách nhiệm của cancellation và thời điểm side effect trở nên visible.

## 10. Chính sách thực thi có thể là một phần hợp đồng

Một số cơ chế AOP được gọi là “execution policy”, nhưng ảnh hưởng trực tiếp đến caller. Cần làm rõ trước khi thực thi.

| Chính sách | Điều caller có thể quan sát | Cần công bố |
| --- | --- | --- |
| Timeout/deadline | Lỗi timeout, kết quả chưa biết, dừng chờ | Mốc tính thời gian, nghĩa của timeout đối với side effect |
| Retry | Thời gian tăng, lệnh có thể chạy nhiều lần | Số lần tối đa, điều kiện retry, idempotency |
| Quota/rate limit | Request bị từ chối | Đơn vị quota, phạm vi, lỗi khi hết quota, khả năng thử lại |
| Cache | Giá trị có thể cũ | TTL/consistency, invalidation, cách yêu cầu dữ liệu mới |
| Authorization | Request bị chặn | Quyền hạn, mã lỗi, phạm vi bảo vệ |
| Circuit breaker | Downstream không được gọi | Điều kiện từ chối tạm thời, lỗi trả về |
| Bulkhead | Lệnh bị từ chối khi hết slot | Hành vi khi quá tải, thời gian chờ/queue |
| Logging/tracing | Thêm tác dụng phụ về quan sát | Trường dữ liệu, chi phí, quyền truy cập, retention |
| Transaction boundary | Thành công/lỗi gắn với đơn vị commit | Atomicity thực sự, phạm vi nguồn dữ liệu và consistency |

Ví dụ, **quota 100 lời gọi/giây** có thể là hạn mức tính phí của sản phẩm hoặc một mức bảo vệ nội bộ. Nếu caller được hứa “mọi yêu cầu hợp lệ đều được xử lý”, quota ẩn thay đổi lời hứa đó. Nếu API công bố có thể trả `TOO_MANY_REQUESTS`, cùng cơ chế có thể trở thành triển khai hợp lệ của chính sách đã định.

Đặt tên policy rõ ràng, version và kiểm thử tương thích. Tránh các pointcut quá rộng như “mọi method bắt đầu bằng `save`” nếu các method đó có semantics khác nhau.

## 11. Những chi tiết nâng cao khi triển khai AOP

### 11.1. Chính xác của pointcut và phạm vi weaving

Tùy cơ chế AOP, join point có thể bao gồm method execution, method call, constructor hoặc truy cập field. Với proxy, chỉ những lời gọi đi qua proxy mới chịu interception; **self-invocation** thường không qua proxy đó. Với bytecode weaving, tập điểm chặn có thể rộng hơn và cần kiểm soát lớp/thư viện được weave.

Nếu một invariant chỉ được enforce ở Aspect, một đường gọi bypass sẽ tạo trạng thái sai. Đây là lý do các **bất biến cốt lõi cần được bảo vệ tại domain**, còn Aspect dùng để tái sử dụng hành vi tại những boundary đã xác định.

### 11.2. Thứ tự advice và composition

Giả sử các lớp advice áp dụng như sau:

~~~text
TraceAspect
  -> RetryAspect
       -> ValidateBoundaryAspect
            -> TransferService
~~~

Một lời gọi caller có thể tạo **một trace logic** nhưng nhiều lần validation và nhiều lần thực thi domain. Nếu đổi thứ tự:

~~~text
RetryAspect
  -> TraceAspect
       -> TransferService
~~~

Mỗi lần retry có thể tạo một trace hoặc span riêng tùy cách truyền context. Thứ tự khác nhau có thể làm thay đổi số lần chạy, transaction scope, accounting metric và loại lỗi nhìn thấy. Một hệ thống phải có quy tắc composition được thử nghiệm, không dựa vào trật tự ngẫu nhiên khi load class.

Nếu authorization advice chạy ngoài cache, nó kiểm tra cả cache hit. Nếu authorization chạy chỉ trong đường gọi dữ liệu gốc, cache hit có thể bypass. Đây không chỉ là lựa chọn thứ tự kỹ thuật: nó liên quan đến hợp đồng bảo vệ dữ liệu.

### 11.3. Advice là mã có lỗi và chi phí

Aspect có thể ném exception, deadlock, làm rò thread-local, quá tải I/O log hoặc giữ lock lâu. Hãy:

- Giữ phần telemetry trong phạm vi lỗi độc lập, không nuốt exception nghiệp vụ.
- Tránh gọi `proceed()` hai lần nếu đó không phải chính sách replay được phép.
- Với around advice, bảo đảm trả đúng kết quả hoặc truyền đúng lỗi khi không chủ đích thay đổi contract.
- Đặt cleanup tài nguyên của advice trong `finally`, đồng thời xác định tài nguyên thực sự thuộc ai.
- Đo overhead và áp dụng sampling/rate limiting phù hợp cho log, không làm mất metric cần thiết.
- Kiểm soát recursion: log advice gọi vào cùng join point có thể dẫn tới advice tự chặn chính mình.

### 11.4. Không nhầm chính sách doanh nghiệp với bảo vệ hạ tầng

Một business rule có thể đi xuyên nhiều module, nhưng việc nó “cross-cutting” không làm nó trở thành chi tiết vô hình. Ví dụ chính sách tenant isolation hoặc chống gian lận có thể được thực thi ở nhiều điểm. Việc đóng gói kiểm tra bằng Aspect có thể tái sử dụng được, **nhưng** nguồn chính sách, mục tiêu bảo vệ, trường hợp từ chối và kiểm thử bypass phải được công bố trong mô hình an ninh/nghiệp vụ.

Tương tự, một hạn mức nghiệp vụ có thể được tính từ trạng thái khách hàng/thỏa thuận, khác với limiter kỹ thuật bảo vệ CPU. Hai cơ chế cần tên metric, lỗi và quyền điều chỉnh khác nhau để tránh vận hành một công tắc kỹ thuật làm thay đổi giá trị hợp đồng khách hàng.

## 12. Kiểm thử hợp đồng khi có và không có Aspect

Một chiến lược kiểm thử mạnh gồm bốn lớp.

**Lớp 1 — Domain/API trực tiếp.** Gọi implementation không qua Aspect với input hợp lệ, bất hợp lệ và các trạng thái biên. Xác nhận tiền/hậu điều kiện, bất biến và exception. Đây là nền tảng để không giấu thiếu sót hợp đồng trong advice.

**Lớp 2 — Advice độc lập.** Dùng target giả ghi số lần gọi/arguments và cho trước kết quả/exception. Kiểm tra advice gọi đúng một lần, không mutate input, không nuốt lỗi, không trả giá trị khác hợp đồng; test cả lỗi phát sinh bên trong telemetry.

**Lớp 3 — Tương đương hành vi.** Chạy cùng bộ case qua implementation trực tiếp và qua proxy/weaving. So sánh result, loại exception, state change và side effect. Với các policy được công bố như quota, kiểm thử trường hợp bị từ chối riêng thay vì đòi tương đương tuyệt đối.

**Lớp 4 — Composition và integration.** Kiểm thử retry + transaction + tracing + authorization + cache (nếu áp dụng), caller vượt boundary, đường async và công việc có side effect. Dùng giả lập lỗi sau khi downstream đã commit để phát hiện double charge, lost update và lỗi “unknown outcome”.

### 12.1. Ma trận các tình huống cần có

| Kịch bản | Kỳ vọng |
| --- | --- |
| Lệnh hợp lệ, Aspect quan sát hoạt động | Kết quả/state giống lời gọi trực tiếp; telemetry tăng |
| Lệnh sai tiền điều kiện | Từ chối đúng loại lỗi; không thay đổi state |
| Thiếu quyền | Bị từ chối ở mọi đường truy cập được bảo vệ, không lộ dữ liệu |
| Advice telemetry bị lỗi | Không biến success/failure nghiệp vụ thành trạng thái khác ngoài hợp đồng |
| Retry sau timeout không rõ kết quả | Không tự thực thi lại side effect nếu thiếu bảo đảm idempotency |
| Cache hit với quyền đã bị thu hồi | Không vô tình bypass authorization |
| Exception từ target | Giữ type/cause hoặc ánh xạ theo hợp đồng đã mô tả |
| Self-call/đường gọi không qua proxy | Bất biến domain vẫn đúng |
| Callback async thất bại sau khi trả Future | Không ghi nhận success nghiệp vụ tại mốc trả Future |
| Chèn thêm Aspect mới | Kiểm thử regression cho thứ tự và số lần proceed |

### 12.2. Kiểm thử mutation của hợp đồng

Một kỹ thuật hữu ích là cố tình viết một advice sai trong môi trường kiểm thử: sửa một input âm thành dương, thay exception bằng success, tự retry lệnh ghi hoặc bỏ validation. Bộ kiểm thử hợp đồng **phải thất bại** khi semantics bị đổi. Nếu test vẫn xanh, coverage có thể chỉ đo nhánh code mà chưa đo kết quả nghiệp vụ thực.

Không nhất thiết cần một thư viện mutation testing: có thể tạo fake advice để minh họa từng hành vi sai, sau đó so sánh trạng thái và lỗi. Điều quan trọng là kiểm thử đúng bất biến độc lập với cách triển khai.

## 13. Dấu hiệu cảnh báo khi review thiết kế

Kiểm tra kỹ nếu thấy những phát biểu hoặc cách viết sau:

- “Chúng ta không cần validate trong domain, Aspect sẽ lo hết.” → Nguy cơ bypass/thiếu trách nhiệm sở hữu invariant.
- “Có lỗi thì Aspect trả object mặc định để màn hình không bị đỏ.” → Có thể tạo success giả hoặc che lỗi phân quyền.
- “Retry mọi exception ba lần cho chắc.” → Có thể nhân side effect và tăng tải khi downstream suy yếu.
- “Method gốc không đổi nên hợp đồng không đổi.” → Around advice có thể thay đổi observable behavior.
- “Timeout nghĩa là giao dịch bị hủy.” → Có thể chỉ là caller dừng chờ, side effect vẫn xảy ra.
- “Tất cả `save*` đều có transaction giống nhau.” → Các thao tác khác nhau có ranh giới consistency khác nhau.
- “Không cần test trực tiếp object vì production luôn dùng Aspect.” → Không bảo vệ invariant ở đường gọi bị bypass hoặc cấu hình weaving bị lỗi.
- “Aspect đã check quyền nên mọi đường truy cập đều an toàn.” → Phải chứng minh pointcut/boundary và kiểm thử unauthorized path.
- “Bị rate limit là lỗi kỹ thuật nên caller không cần biết.” → Nếu caller có thể bị từ chối, cần hợp đồng về lỗi và retry.
- “Advice ghi log toàn bộ để audit là đủ.” → Logging/telemetry không tự bảo đảm tính đầy đủ, độ bền, quyền truy cập hay compliance của audit.

Bất cứ khi nào một Aspect thay đổi điều caller **có thể quan sát**, hãy coi đó là thay đổi yêu cầu, không chỉ là refactor hạ tầng.

## 14. Checklist ra quyết định trước khi phát hành

Trước khi chấp nhận một Aspect mới, hãy trả lời rõ:

1. **Hợp đồng ở đâu?** Preconditions, invariants, postconditions, lỗi và side effect được định nghĩa trong API/domain nào?
2. **Advice thêm hành vi gì?** Chỉ telemetry hay còn mutate args, alter return, throw, suppress, retry, cache hoặc từ chối?
3. **Có đường bypass không?** Direct call, self-call, worker, endpoint khác, background job hoặc weaving configuration thay đổi sẽ thế nào?
4. **Ai sở hữu quyết định nghiệp vụ?** Domain/service hay policy được công bố? Ai có quyền sửa quy tắc và kiểm thử nó?
5. **Các lỗi được giữ đúng chưa?** Có phân biệt input invalid, thiếu quyền, lỗi tạm thời và kết quả không rõ?
6. **Side effect có an toàn khi advice chạy lặp không?** Có idempotency key, deadline và giới hạn retry đúng hợp đồng?
7. **Thứ tự các Aspect có kiểm thử không?** Đặc biệt authorization, retry, cache, transaction, metrics.
8. **Có kiểm thử trước/sau weaving không?** So sánh observable behavior với phép đo state/exception đáng tin.
9. **Tác vụ bất đồng bộ được theo dõi đúng mốc chưa?** Kết thúc handle khác hoàn tất nghiệp vụ; cleanup thuộc đúng lifecycle.
10. **Người vận hành có phân biệt được lỗi domain và lỗi policy không?** Telemetry nêu được nguồn từ chối hoặc thông số policy mà không rò dữ liệu nhạy cảm.

AOP mạnh khi giúp thực thi nhất quán một **hợp đồng đã được xác định**, giảm lặp logic cắt ngang và tăng khả năng quan sát. Nó trở thành rủi ro khi khiến người đọc method tưởng đang có một hợp đồng, còn runtime âm thầm áp dụng một hợp đồng khác. Vì vậy, hãy giữ **quy tắc đúng/sai của nghiệp vụ tường minh và có kiểm thử độc lập**, rồi dùng Aspect để triển khai phần chính sách cắt ngang phù hợp trong những ranh giới đã được khai báo.
