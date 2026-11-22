# Tách aspect độc lập khỏi aspect phải phối hợp trong AOP

Khi một chương trình sử dụng nhiều **aspect** trong lập trình hướng khía cạnh (*Aspect-Oriented Programming*, **AOP**), câu hỏi kiến trúc không chỉ là “aspect nào chạy trước?”. Cần xác định **những aspect có thể hoạt động độc lập** và **những aspect phải có hợp đồng phối hợp** để bảo toàn ngữ nghĩa nghiệp vụ, bảo mật, vòng đời tài nguyên và kết quả của lời gọi.

Một aspect ghi nhận số lần gọi có thể **độc lập về dữ liệu và mục đích** với aspect ghi trace. Trong khi đó, một aspect kiểm toán được thiết kế để chỉ ghi nhận *giao dịch đã qua xác thực* có thể phải nhận kết quả xác thực từ một aspect khác. Nếu chúng không có hợp đồng rõ, việc hoán đổi thứ tự, bật/tắt riêng hoặc xử lý ngoại lệ có thể làm mất sự kiện kiểm toán, ghi sự kiện không đúng hoặc khiến chương trình trả kết quả không còn tin cậy.

**Ý chính:** “Tách độc lập” là giảm những phụ thuộc **không cần thiết**, không phải tuyên bố mọi aspect có thể đảo thứ tự mà không đổi gì. “Phải phối hợp” là đưa những phụ thuộc **thực sự bắt buộc** thành một hợp đồng được diễn đạt, kiểm thử và kiểm soát vòng đời; không phải để các aspect bí mật đọc/ghi cùng một biến toàn cục.

Bài này giải thích kiến thức AOP cơ bản và nâng cao nói chung. Các công nghệ AOP khác nhau về join point, pointcut, precedence, `proceed`, binding và việc dùng weaving hay proxy; ví dụ Java 17 xây một **chuỗi interceptor qua JDK dynamic proxy** để làm rõ nguyên tắc thiết kế, không giả định mọi weaver có hành vi giống proxy đó.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Nhận diện aspect **độc lập về chính sách/dữ liệu** và aspect có **phụ thuộc thứ tự, kết quả, trạng thái hoặc vòng đời**.
2. Phân biệt **khả năng hoán đổi thứ tự** với **độc lập về module** và **không cần phối hợp về mặt nghiệp vụ**.
3. Viết hợp đồng cho quan hệ trước–sau, điều kiện chạy, quyền thay đổi đầu vào/kết quả và lỗi.
4. Xây một **đồ thị phụ thuộc có hướng** để kiểm tra precedence thay vì dựa vào thứ tự ngẫu nhiên.
5. Thiết kế ngữ cảnh theo **từng invocation** hoặc giao diện phối hợp tường minh, tránh field global/`ThreadLocal` không được dọn.
6. Phân tích sự tương tác giữa logging, metrics, authorization, cache, retry, transaction, audit và tài nguyên.
7. Biết khi nào nên tách aspect, khi nào cần một điều phối chung hoặc gộp hai chính sách có bất biến chặt.
8. Viết và chạy ví dụ Java 17 chứng minh một hợp đồng phối hợp bằng trạng thái invocation, đồng thời kiểm tra misordering thất bại có kiểm soát.
9. Kiểm thử cả đường thành công, từ chối, lỗi, short-circuit, retry, bypass và concurrency.

## 2. Các khái niệm nền

| Thuật ngữ | Vai trò |
| --- | --- |
| **Join point** | Điểm trong mô hình AOP có thể can thiệp, như thực thi phương thức khi công nghệ hỗ trợ |
| **Pointcut** | Điều kiện lựa chọn những join point cần áp dụng |
| **Advice** | Hành vi trước, sau, bao quanh hoặc theo nhánh lỗi của join point |
| **Aspect** | Đóng gói chính sách cắt ngang và những advice/pointcut liên quan |
| **Weaving/composition** | Kết hợp aspect với chương trình bằng compiler, bytecode hoặc đường gọi/proxy phù hợp |
| **Precedence/order** | Thứ tự có ý nghĩa khi nhiều aspect áp cùng điểm |
| **Invocation context** | Dữ liệu của một lượt gọi: phương thức, đối số, target, metadata và trạng thái nếu cơ chế cung cấp |
| **Proceed/next** | Tiếp tục tới phần bên trong chuỗi nếu loại advice/công cụ cho phép |
| **Short circuit** | Advice trả kết quả hoặc ném lỗi mà không chuyển tiếp đến phần còn lại |
| **Contract/invariant** | Quy tắc phải đúng dù thứ tự hoặc thành phần triển khai thay đổi |

Một **pointcut đúng** chỉ chứng minh điểm được lựa chọn theo bộ lọc; không tự chứng minh thứ tự hoặc việc **đường gọi thực tế có đi qua cơ chế can thiệp**. Với proxy, người gọi trực tiếp đối tượng gốc có thể bypass; với weaving bytecode, phạm vi lại phụ thuộc loại điểm và lớp đã được xử lý.

## 3. Độc lập có nhiều mức

Không nên dùng “độc lập” như một thuộc tính Boolean duy nhất. Một aspect có thể độc lập ở chiều này nhưng phụ thuộc ở chiều khác.

| Chiều đánh giá | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Chính sách** | Aspect có nhiệm vụ riêng, không biết logic của aspect khác? | Bộ đếm lời gọi |
| **Dữ liệu** | Có cần đọc dữ kiện do aspect khác tạo? | Audit yêu cầu kết quả xác thực |
| **Thứ tự** | Hoán đổi hai aspect có bảo toàn các bất biến được yêu cầu? | Timer đo tổng request vs từng attempt |
| **Luồng điều khiển** | Một aspect có thể ngăn aspect khác chạy? | Cache trả sớm trước authorization |
| **Lỗi** | Aspect có thay ngoại lệ hoặc chuyển lỗi thành fallback? | Retry hoặc exception mapper |
| **Vòng đời** | Aspect có chia sẻ tài nguyên/scope với aspect khác? | Transaction và resource cleanup |
| **Triển khai** | Có bật/tắt, phiên bản, cấu hình và kiểm thử riêng được không? | Metrics phụ trợ |
| **An toàn** | Nếu thiếu một aspect, hệ có còn thỏa bất biến quan trọng? | Quyền truy cập, kiểm toán bắt buộc |

**Một aspect có thể độc lập về mã nguồn nhưng không hoán đổi thứ tự được.** Ví dụ Timing không gọi trực tiếp Retry và ngược lại, nhưng `Timing(Retry(Target))` có thể đo **toàn bộ chuỗi thử lại**, trong khi `Retry(Timing(Target))` có thể đo **từng attempt**. Cả hai có thể độc lập về module; ý nghĩa metric lại phụ thuộc vị trí.

Vì thế trước khi phân loại, hãy viết **đơn vị quan sát** (*logical request*, *attempt*, *committed effect*) và **bất biến nghiệp vụ**.

## 4. Aspect độc lập: những đặc điểm thường có

Một aspect dễ tách độc lập khi:

- Nó sở hữu một mục tiêu rõ ràng, ví dụ ghi một chỉ số theo lời gọi, không điều khiển nghiệp vụ.
- Nó dùng dữ liệu **có sẵn tại join point** hoặc một hợp đồng chung ổn định, thay vì yêu cầu đọc field riêng của aspect khác.
- Nó không đổi đối số, không gọi `proceed` nhiều lần, không tùy tiện thay giá trị trả về hoặc ngoại lệ.
- Khi bị bỏ đi, nghiệp vụ cốt lõi vẫn đúng theo yêu cầu; nếu chính sách là bắt buộc, phải có một cơ chế khác bảo đảm yêu cầu ấy.
- Nó không giữ request/target trong trạng thái sống lâu ngoài nhu cầu thực tế.
- Nó có thể được kiểm thử bằng hợp đồng đầu vào/đầu ra của chính mình.
- Nó công bố chính xác **scope đo đạc**: lời gọi đã vào proxy, lời gọi đã khớp pointcut, attempt hay effect được cam kết.

Ví dụ một **counter** đếm số lần gọi tới pointcut có thể không cần biết nội dung của Trace. Tuy nhiên khi đặt bên trong Authorization, nó không đếm các request bị từ chối **trước** Authorization; do đó quyết định vị trí vẫn phải nằm trong hợp đồng của metric.

### 4.1. “Chỉ quan sát” cũng có thể làm sai chương trình

Một advice ghi log có thể ném lỗi khi `toString()` của đối số thất bại, chặn luồng vì I/O hoặc vô tình đưa dữ liệu nhạy cảm vào log. Một bộ đo thời gian có thể lưu object request vào static list và gây retention. Nếu logic quan sát được thiết kế là không ảnh hưởng nghiệp vụ, phải có chính sách cho **lỗi của cơ chế quan sát** và cho lượng dữ liệu được giữ.

“Observer độc lập” không đồng nghĩa “đương nhiên vô hại”.

### 4.2. Một ví dụ quan hệ độc lập

```text
Caller
  |
  v
Trace (xác định correlation ID)
  |
  v
Counter (đếm lời gọi)
  |
  v
Target
```

Nếu Trace không phụ thuộc Counter, Counter không phụ thuộc Trace và cả hai chuyển tiếp đúng một lần, chúng thường có thể phát triển riêng. Nhưng nếu Counter được yêu cầu chỉ đếm các **target execution thành công**, nó phải được đặt hoặc thiết kế phù hợp với định nghĩa thành công. Sự độc lập về *implementations* không thay thế tài liệu về **điều kiện đo**.

## 5. Aspect phải phối hợp: những dấu hiệu nhận biết

Một quan hệ phối hợp tồn tại khi có ít nhất một trong các tình huống:

1. **Phụ thuộc thứ tự bắt buộc:** chính sách B chỉ hợp lệ sau khi A đã thực hiện một kiểm tra hoặc mở scope.
2. **Phụ thuộc dữ liệu:** B phải dùng kết quả của A, ví dụ danh tính đã xác thực hoặc transaction identifier.
3. **Phụ thuộc trạng thái:** B cần biết một tác vụ đã chuẩn bị, đã cam kết, đã rollback hay chưa.
4. **Phụ thuộc vòng đời:** A mở tài nguyên mà B phải dùng/đóng trong đúng phạm vi.
5. **Phụ thuộc luồng lỗi:** A quyết định retry/fallback, B cần quan sát kết quả cuối hay từng attempt.
6. **Phụ thuộc độ phủ:** A phải bảo đảm kiểm soát quyền trước mọi con đường tới thao tác nhạy cảm; B không thể được đặt ở chỗ bypass chính sách đó.
7. **Phụ thuộc nguyên tử:** hai hành vi phải nhất quán trong một transaction hoặc qua một giao thức rõ, không thể chỉ dựa vào thứ tự callback.

Một ví dụ có chủ ý: **Authorization** đặt dấu xác minh nội bộ trong context của lượt gọi; **CommittedAudit** chỉ ghi sự kiện “đã qua kiểm tra quyền và đã tạo effect” nếu dấu ấy tồn tại và target trả kết quả xác nhận commit. Hai aspect ấy phải phối hợp theo **hợp đồng do kiến trúc thiết kế**, chứ không phải tất cả audit trong AOP đều mặc định phải phụ thuộc authorization.

### 5.1. Phụ thuộc thực sự và phụ thuộc do code viết kém

Hai aspect có thể “phải phối hợp” chỉ vì chúng cùng đọc/ghi một static Boolean như `lastAuthorized`. Đây thường là **phụ thuộc ngẫu nhiên và nguy hiểm**: hai request đồng thời sẽ tranh chấp cùng field.

Thay vì công nhận static field là hợp đồng, nên:

- Đưa dữ liệu vào một đối tượng context **theo invocation**;
- Định nghĩa rõ ai tạo, ai đọc, điều kiện hợp lệ và thời hạn tồn tại;
- Chỉ cấp quyền cập nhật cho thành phần được chỉ định;
- Nếu thông tin bắt buộc, **fail closed** khi thiếu context hoặc cấu hình sai;
- Kiểm thử concurrency và các đường không được aspect bao phủ.

Tốt hơn nữa, nếu hai chính sách phải luôn thành công/thất bại cùng nhau, cân nhắc một **đơn vị điều phối** thay vì hai interceptor ngầm kết nối.

## 6. Precedence: thứ tự là hợp đồng, không phải chi tiết trang trí

Trong chuỗi around advice, một cấu trúc:

```text
Outer(Inner(Target))
```

thường chạy theo trình tự:

```text
Outer before
    Inner before
        Target
    Inner after / catch / finally
Outer after / catch / finally
```

Nếu Outer không gọi `proceed`, cả Inner và Target có thể không chạy. Nếu Outer retry bằng cách gọi tiếp nhiều lần, Inner và Target có thể được thực thi lặp. Một số công nghệ giới hạn số lần hoặc ngữ nghĩa `proceed`, vì vậy không mặc định mọi mô hình AOP đều hỗ trợ retry bằng cách đó.

### 6.1. Quan hệ phụ thuộc có hướng

Giả sử một nghiệp vụ được thiết kế yêu cầu:

```text
Authorize trước khi chạy operation
Transaction scope bao quanh operation
CommittedAudit chỉ ghi sau khi biết effect đã commit
```

Ta có thể mô hình hóa các ràng buộc:

```text
Authorization -> Operation (must authorize before sensitive effect)
Transaction  -> Operation (must establish transaction scope)
CommitResult -> CommittedAudit (must have confirmed outcome)
```

Các mũi tên mô tả **phụ thuộc ngữ nghĩa**, không phải tuyên bố một thứ tự tuyến tính duy nhất cho mọi AOP. Với một chuỗi around, “A bao ngoài B” có nghĩa A chạy phần before trước B, nhưng phần after của A chạy **sau** phần after của B. Cần xét **đúng vị trí trong before/proceed/after**, không chỉ một danh sách tên.

### 6.2. Khi nào cần đồ thị DAG?

Nếu có nhiều quan hệ `A trước B`, `B trước C` và `A trước D`, có thể biểu diễn thành **đồ thị có hướng không chu trình (DAG)** rồi kiểm tra một thứ tự hợp lệ. Khi xuất hiện vòng như `A phải hoàn tất trước B` và `B phải hoàn tất trước A` trong cùng giai đoạn, thiết kế có thể mâu thuẫn.

Không giải bằng cách chọn precedence tùy ý: có thể cần tách **prepare** và **finalize**, phát hành một kết quả bất biến, hoặc gộp hành vi trong một coordinator.

### 6.3. Một bảng ví dụ về mức phụ thuộc

| Cặp aspect | Quan hệ thường phải xem | Có thể hoán đổi tự do không? |
| --- | --- | --- |
| Trace và Counter đơn giản | Độc lập về state, cùng quan sát lời gọi | Về nghiệp vụ thường được, nhưng chi tiết log/count/timing có thể khác |
| Authorization và Cache | Cache có thể short-circuit quyền ở bên trong | Không nếu mọi cache hit phải được xác thực |
| Retry và Metrics | Một request hay mỗi attempt | Chỉ khi hợp đồng metric chấp nhận |
| Retry và Transaction | Mỗi attempt có transaction riêng hay dùng chung | Phụ thuộc trạng thái transaction và điều kiện retry |
| Transaction và CommitAudit | Lúc nào có bằng chứng commit | Phải phối hợp theo hợp đồng commit |
| Validation và Normalization | Normalization có đổi dữ liệu được xác thực? | Cần quy tắc về input canonical |
| Redaction và Logging | Không được ghi dữ liệu thô nhạy cảm | Cần phối hợp chính sách bảo vệ dữ liệu |
| Rate-limit và Retry | Retry có tiêu thụ quota mỗi attempt? | Cần định nghĩa đơn vị giới hạn |
| Cache và Business Operation | Có thể trả sớm thay vì thực hiện effect | Chỉ hợp lệ với những thao tác cho phép short circuit |

Một kết luận khác cũng quan trọng: **phối hợp không nhất thiết là dependency mã nguồn**. Hai aspect có thể không import nhau nhưng phải tuân theo một contract về precedence và dữ liệu.

## 7. Dữ liệu phối hợp nên đi qua đâu?

Một số lựa chọn, từ rõ ràng tới dễ gây lỗi:

### 7.1. Kết quả hoặc ngoại lệ của phần chuỗi bên trong

Một advice quanh có thể quan sát `result` của `proceed`, hoặc `Throwable` nếu lời gọi bị ném lỗi. Đây là **đường phối hợp tự nhiên** nếu thông tin cần thiết nằm trong hợp đồng phương thức đích.

Nhưng “phương thức trả bình thường” **không đồng nghĩa nghiệp vụ đã commit**. Một `Result.failure(...)` vẫn có thể là return bình thường; một lời gọi trả `CompletableFuture` chưa chắc công việc đã hoàn tất. Audit phải hiểu trạng thái nghiệp vụ thực, không suy đoán từ nhánh after-returning.

### 7.2. Invocation-scoped context

Khi hai interceptor cần dữ liệu trung gian, có thể dùng một context theo lượt gọi:

```text
context {
    requestId
    authorizationDecision
    operationStatus
    attemptNumber
}
```

Đây là **mô hình dữ liệu**, không phải API chuẩn của AOP. Phải quy định **ai cấp dữ liệu, ai được đọc, giá trị mặc định, giai đoạn hợp lệ và thời điểm dọn**. Một map `String → Object` không có kiểm soát kiểu có thể tạo xung đột tên/cast sai; với hợp đồng quan trọng nên dùng kiểu rõ ràng và giới hạn quyền sửa.

Context của request không được coi là một “kho tin cậy” chỉ vì có một cờ `authorized=true`; phải tin cậy **nguồn xác thực** và mọi đường tới effect.

### 7.3. Service hoặc giao diện phối hợp

Nếu hai aspect cần một giao thức nghiêm ngặt, có thể trích thành một interface rõ, ví dụ:

```text
Decision authorize(Command)
Receipt executeAuthorized(Decision, Command)
void recordConfirmed(Receipt)
```

Đây là **giả mã hợp đồng**, không phải Java chạy độc lập. Một coordinator điều phối thứ tự, kiểm tra bất biến và chuyển những dữ kiện đã xác nhận giữa các bước.

Một coordinator thường dễ kiểm thử hơn khi có chuỗi phụ thuộc sâu, nhiều rollback và nghĩa vụ bảo mật/kiểm toán. Dùng AOP để tổ chức hành vi cắt ngang, nhưng **không giấu quy trình nghiệp vụ cốt lõi trong những thứ tự interceptor khó nhìn thấy**.

### 7.4. Event với danh tính và trạng thái rõ

Một cặp aspect có thể phối hợp qua sự kiện kiểu `Authorized`, `Committed` hoặc `Failed` nếu sự kiện thật sự thể hiện trạng thái đáng tin. Tuy nhiên publish async có thể giao lại, mất phản hồi hoặc đến sai thứ tự theo mô hình phân tán.

Khi cần bảo đảm, hãy định nghĩa delivery, idempotency, retention và đối soát. Không suy rằng hai advice publish và consume một event là có transaction nguyên tử.

## 8. Ví dụ Java 17: độc lập Trace/Metrics, phối hợp Authorization/Audit

Chương trình dưới đây tự tạo một **interceptor chain** với JDK dynamic proxy:

- **Trace** ghi trước/sau/lỗi và không biết nội bộ Authorization, Audit hay Metrics.
- **Metrics** đếm lượt vào proxy cho thao tác `place`, không cần kết quả riêng từ aspect khác.
- **Authorization** kiểm tra token đơn giản rồi đặt dấu đã xác minh trong state **của lượt gọi**.
- **CommittedAudit** yêu cầu state đã xác minh **trước khi** cho chuỗi chạy tiếp, sau đó chỉ in sự kiện với kết quả `Receipt` do target trả.
- Một cấu hình sai đặt **Audit trước Authorization** bị từ chối rõ ràng thay vì âm thầm chạy.
- Lời gọi trực tiếp target minh họa đường **bypass proxy**: đây là lý do những biện pháp kiểm soát quyền thật phải được bảo vệ tại ranh giới đáng tin cậy, không chỉ dựa vào một proxy có thể bị bỏ qua.

**Giới hạn:** Ví dụ giả định target tạo kết quả `Receipt` chỉ khi thao tác đơn giản đã hoàn tất trong bộ nhớ; nó **không** cài đặt giao dịch cơ sở dữ liệu, audit bền vững hoặc một cơ chế bảo mật sản xuất. Token `"allow"` là dữ liệu học tập, không phải xác thực thật. Không dùng mẫu này làm dịch vụ tài chính mà chưa bổ sung hợp đồng nghiệp vụ, xác thực tại ranh giới và lưu trạng thái thích hợp.

Lưu toàn bộ vào tệp `AspectCoordinationDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class AspectCoordinationDemo {
    record Receipt(String id, int commitNumber) {}

    interface OrderPort {
        Receipt place(String token, String id);
        String inspect(String id);
    }

    static final class OrderService implements OrderPort {
        private final AtomicInteger commits = new AtomicInteger();

        @Override
        public Receipt place(String token, String id) {
            int n = commits.incrementAndGet();
            System.out.println("TARGET committed " + id + "#" + n);
            return new Receipt(id, n);
        }

        @Override
        public String inspect(String id) {
            return "VIEW:" + id;
        }

        int commitCount() {
            return commits.get();
        }
    }

    static final class State {
        boolean authorized;
    }

    @FunctionalInterface
    interface Terminal {
        Object call() throws Throwable;
    }

    @FunctionalInterface
    interface Interceptor {
        Object around(Invocation invocation) throws Throwable;
    }

    static final class Invocation {
        final Method method;
        final Object[] args;
        final State state;
        final List<Interceptor> chain;
        final int position;
        final Terminal terminal;

        Invocation(Method method, Object[] args, State state,
                   List<Interceptor> chain, int position,
                   Terminal terminal) {
            this.method = method;
            this.args = args;
            this.state = state;
            this.chain = chain;
            this.position = position;
            this.terminal = terminal;
        }

        Object proceed() throws Throwable {
            if (position == chain.size()) {
                return terminal.call();
            }
            Interceptor next = chain.get(position);
            Invocation remainder = new Invocation(
                    method, args, state, chain, position + 1, terminal);
            return next.around(remainder);
        }
    }

    static final class Trace implements Interceptor {
        @Override
        public Object around(Invocation invocation) throws Throwable {
            System.out.println("TRACE enter place");
            try {
                Object result = invocation.proceed();
                System.out.println("TRACE return");
                return result;
            } catch (Throwable error) {
                System.out.println("TRACE error "
                        + error.getClass().getSimpleName());
                throw error;
            } finally {
                System.out.println("TRACE finally");
            }
        }
    }

    static final class Metrics implements Interceptor {
        private final AtomicInteger attempts = new AtomicInteger();

        @Override
        public Object around(Invocation invocation) throws Throwable {
            System.out.println("METRIC attempt=" + attempts.incrementAndGet());
            return invocation.proceed();
        }

        int count() {
            return attempts.get();
        }
    }

    static final class Authorization implements Interceptor {
        @Override
        public Object around(Invocation invocation) throws Throwable {
            if (!"allow".equals(invocation.args[0])) {
                System.out.println("AUTH denied");
                throw new SecurityException("denied");
            }
            System.out.println("AUTH passed");
            invocation.state.authorized = true;
            return invocation.proceed();
        }
    }

    static final class CommittedAudit implements Interceptor {
        @Override
        public Object around(Invocation invocation) throws Throwable {
            if (!invocation.state.authorized) {
                throw new IllegalStateException(
                        "audit requires authorization");
            }
            Object result = invocation.proceed();
            if (result instanceof Receipt receipt) {
                System.out.println("AUDIT committed " + receipt.id()
                        + "#" + receipt.commitNumber());
            }
            return result;
        }
    }

    static Object invokeTarget(Method method, Object target, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapper) {
            throw wrapper.getCause();
        }
    }

    static OrderPort wrap(OrderPort target, List<Interceptor> chain) {
        return (OrderPort) Proxy.newProxyInstance(
                OrderPort.class.getClassLoader(),
                new Class<?>[] { OrderPort.class },
                (proxy, method, args) -> {
                    if (!method.getName().equals("place")) {
                        return invokeTarget(method, target, args);
                    }
                    Object[] values = args.clone();
                    State state = new State();
                    Terminal terminal = () -> invokeTarget(
                            method, target, values);
                    Invocation start = new Invocation(
                            method, values, state, chain, 0, terminal);
                    return start.proceed();
                });
    }

    public static void main(String[] args) {
        OrderService service = new OrderService();
        Metrics metrics = new Metrics();
        OrderPort protectedPort = wrap(service, List.of(
                new Trace(), metrics, new Authorization(),
                new CommittedAudit()));

        System.out.println("READY");
        Receipt ok = protectedPort.place("allow", "R-1");
        System.out.println("CALLER " + ok.id() + "#" + ok.commitNumber());

        try {
            protectedPort.place("deny", "R-2");
        } catch (SecurityException error) {
            System.out.println("CALLER_ERROR " + error.getMessage());
        }

        System.out.println("INSPECT " + protectedPort.inspect("R-1"));
        System.out.println("COMMITS " + service.commitCount());
        System.out.println("ATTEMPTS " + metrics.count());

        OrderPort wrongOrder = wrap(service, List.of(
                new CommittedAudit(), new Authorization()));
        try {
            wrongOrder.place("allow", "R-3");
        } catch (IllegalStateException error) {
            System.out.println("MISORDER " + error.getMessage());
        }
        System.out.println("COMMITS_AFTER_MISORDER "
                + service.commitCount());

        Receipt direct = service.place("allow", "R-4");
        System.out.println("DIRECT " + direct.id() + "#"
                + direct.commitNumber());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 AspectCoordinationDemo.java
java AspectCoordinationDemo
```

Đầu ra dự kiến chính xác:

```text
READY
TRACE enter place
METRIC attempt=1
AUTH passed
TARGET committed R-1#1
AUDIT committed R-1#1
TRACE return
TRACE finally
CALLER R-1#1
TRACE enter place
METRIC attempt=2
AUTH denied
TRACE error SecurityException
TRACE finally
CALLER_ERROR denied
INSPECT VIEW:R-1
COMMITS 1
ATTEMPTS 2
MISORDER audit requires authorization
COMMITS_AFTER_MISORDER 1
TARGET committed R-4#2
DIRECT R-4#2
```

### 8.1. Vì sao Trace và Metrics được xem là tách độc lập?

Cả hai chỉ làm việc với `Invocation` và `proceed()`, không đọc cờ xác thực hoặc dữ liệu riêng của CommittedAudit. Chúng không có dependency code với Authorization/Audit. Khi chuyển từ `Trace(Metrics(...))` sang `Metrics(Trace(...))`, kết quả nghiệp vụ cơ bản trong ca đơn giản vẫn có thể giữ nguyên.

Tuy nhiên, **chi tiết thứ tự log và số liệu tính toán** có thể đổi theo vị trí, đặc biệt khi đặt Metrics **sau** Authorization thì request bị từ chối sẽ không đi tới Metrics. Đây là sự khác biệt giữa **không cần state của nhau** và **bảo đảm hoàn toàn có thể hoán đổi**.

### 8.2. Vì sao Authorization và CommittedAudit cần phối hợp?

Trong thiết kế cố ý của ví dụ, CommittedAudit phải thấy `state.authorized=true` **trước khi chuyển tiếp**. Authorization là thành phần duy nhất đặt dấu này sau khi kiểm tra. Mỗi lời gọi `place` tạo một `State` mới; thông tin của `R-1` không rò sang `R-2`.

Nếu đảo thứ tự thành `CommittedAudit(Authorization(Target))`, CommittedAudit kiểm tra khi chưa có dấu xác minh và ném `IllegalStateException` **trước khi target chạy**. Dòng `COMMITS_AFTER_MISORDER 1` cho thấy lời gọi `R-3` không tạo thêm effect trong chương trình mẫu.

Đây là một **hợp đồng kiến trúc cụ thể**. Trong hệ thật, cờ Boolean mutable do interceptor truyền không phải chứng cứ an toàn độc lập cho quyền truy cập; cần nguồn xác thực đáng tin, mô hình kiểm soát quyền tại ranh giới nghiệp vụ và kiểu dữ liệu có bảo vệ phù hợp.

### 8.3. Vì sao audit không ghi cho request bị từ chối?

Authorization không gọi tiếp khi token không hợp lệ, vì vậy CommittedAudit nằm bên trong không được chạy. **Đây không có nghĩa sự kiện từ chối không cần audit**: nếu chính sách bắt buộc ghi cả truy cập bị từ chối, phải dùng một **DenialAudit** thích hợp ở ranh giới ngoài hoặc một giao thức audit có hai loại sự kiện rõ ràng.

Không đổi vị trí CommittedAudit lên ngoài Authorization chỉ để “có log” nếu điều đó phá hợp đồng **chỉ ghi commit đã qua kiểm tra**.

### 8.4. Vì sao `inspect` không có interceptor log?

Handler cố ý chỉ áp chain cho phương thức có tên `place`. `inspect` đi qua proxy nhưng được chuyển tiếp trực tiếp đến target. Nếu hệ thống có overload cùng tên hoặc nhiều phương thức nhạy cảm, bộ lọc chỉ theo tên là **quá hẹp hoặc quá rộng tùy trường hợp**; phải kiểm tra đầy đủ chữ ký và phạm vi.

### 8.5. Vì sao lời gọi trực tiếp là vấn đề nghiêm trọng?

`service.place("allow", "R-4")` bypass toàn bộ proxy, nên có dòng `TARGET committed` mà không có `AUDIT committed`. Điều này minh họa lỗi **coverage**, không chỉ lỗi precedence.

Với bất biến bảo mật hoặc kiểm toán bắt buộc, không nên xem một proxy tùy chọn là hàng rào duy nhất. Cần bảo vệ effect ở **ranh giới đáng tin**, kiểm soát cách cấp tham chiếu/đường gọi và kiểm thử những đường vòng tương ứng. Một weaver khác có phạm vi join point khác, nhưng cũng phải xác minh coverage thực.

### 8.6. Giới hạn kỹ thuật của ví dụ

- `Invocation` và `State` được viết thủ công, không phải API chuẩn của mọi AOP.
- `Receipt` xác nhận hoàn tất thao tác **trong bộ nhớ ví dụ**; không có database transaction, durable audit hay distributed commit.
- Trace/Metrics không xử lý lỗi I/O của logging hoặc metric backend; hệ thật cần chính sách lỗi của hệ quan sát.
- `State` thuộc từng invocation, tránh dùng field singleton cho dữ liệu người gọi.
- `args.clone()` chỉ sao chép mảng, không sao chép sâu từng đối tượng.
- JDK proxy chỉ intercept lời gọi qua giao diện, không tự chặn field access, constructor, phương thức private hoặc self-invocation trên target.
- Ví dụ không có retry; nếu thêm retry, cần xử lý các attempt, commit trùng và idempotency trước khi tuyên bố audit chính xác.

## 9. Tách theo sự kiện “đã cam kết”, không theo exception đơn giản

Một cặp transaction và audit là ví dụ điển hình cần đặc biệt thận trọng:

```text
Audit(Transaction(Target))
Transaction(Audit(Target))
```

Ở cấu trúc đầu, Audit ngoài có thể chạy sau khi Transaction đã trả về hoặc ném lỗi. Ở cấu trúc sau, Audit bên trong có thể ghi khi target đã trả về nhưng **transaction bên ngoài chưa commit**. Nếu commit sau đó thất bại, bản ghi audit “đã commit” có thể sai.

Ngay cả cấu trúc Audit ngoài cũng **không đủ** để bảo đảm audit luôn bền vững hoặc transaction commit toàn bộ hệ thống ngoài. Một transaction nội bộ trả thành công có thể còn phải phát event ra mạng; audit sink có thể thất bại riêng.

Nếu yêu cầu là “ghi audit bền vững **cùng** hiệu ứng nghiệp vụ”, cần thiết kế **ranh giới transaction, outbox hoặc cơ chế phối hợp đáng tin** thích hợp. Thứ tự aspect là một phần, không thay thế atomicity/đối soát.

### 9.1. “After-returning” không phải “business success”

Một phương thức trả `Result(status=REJECTED)` là nhánh trả về bình thường nhưng chưa tạo giao dịch. Một phương thức trả `Future<Result>` có thể kết thúc phần đồng bộ khi future chưa hoàn tất. Một audit aspect phải dùng **kết quả đã được xác nhận** theo hợp đồng cụ thể, không chỉ dựa vào việc không thấy exception.

### 9.2. Trạng thái không chắc chắn sau timeout

Một lần gửi yêu cầu có thể đã tạo effect ở bên nhận rồi mất phản hồi. Nếu aspect Retry gọi lại `proceed`, nó có thể tạo effect thứ hai. Audit dựa trên số lần reply thành công có thể thiếu hoặc thừa so với số effect thực sự.

Sự phối hợp an toàn cần nhận diện một **logical request**, idempotency key, quy tắc retry, khả năng đối soát và ranh giới commit. Không giải quyết được bằng cách đảo Logging và Retry.

## 10. Có nên cho các aspect biết trực tiếp nhau không?

Có một phổ thiết kế:

| Mức gắn kết | Hình thức | Khi nào cân nhắc |
| --- | --- | --- |
| **Độc lập hoàn toàn** | Chỉ dùng join point/proceed, không biết nhau | Logging và một số chỉ số |
| **Hợp đồng precedence** | Aspect không import nhau nhưng được đặt theo thứ tự rõ | Authorization và Cache |
| **Shared invocation contract** | Dùng dữ liệu theo một lần gọi, có kiểu/ownership | Verified identity cho audit |
| **Service/coordinator trung gian** | Cùng gọi qua một giao diện chính thức | Transaction + audit bền vững, nhiều bước |
| **Direct dependency** | Aspect A gọi public API của aspect B | Chỉ khi có lý do rõ, tránh coupling ngầm |
| **Một aspect thống nhất** | Gộp các hành vi không thể tách trách nhiệm | Bất biến phải duy trì nguyên tử trong một scope |

Không phải gắn kết càng thấp luôn càng tốt. Nếu có một **bất biến không thể bảo đảm khi tách**, gộp chính sách hoặc tạo coordinator có thể giúp rõ ràng và kiểm thử được. Ngược lại, gộp mọi trace/metric/cache/security vào một “siêu aspect” làm hệ khó tái sử dụng, đổi thứ tự và phân tích lỗi.

### 10.1. Quy tắc quyết định

Hỏi theo thứ tự:

1. Hai aspect có thể vận hành mà không đọc kết quả hay state của nhau không?
2. Nếu hoán đổi thứ tự, những bất biến quan trọng có đổi không?
3. Nếu một aspect short-circuit, aspect kia có còn **bắt buộc** chạy không?
4. Nếu một aspect lỗi, thành phần kia phải fail-open, fail-closed hay ghi trạng thái không chắc chắn?
5. Có trạng thái cần tồn tại xuyên nhiều join point không? Ai sở hữu nó?
6. Nếu hai aspect cùng chạy trong retry, số lần effect có thay đổi không?
7. Khi bật/tắt riêng từng aspect, hệ thống còn đúng hợp đồng không?
8. Việc phối hợp có thuộc ngữ nghĩa nghiệp vụ cốt lõi đến mức phải **đưa ra khỏi AOP** không?

Nếu câu 2–8 bộc lộ phụ thuộc thật, hãy ghi nó thành contract và test, thay vì chỉ đặt thứ tự thủ công trong cấu hình.

## 11. Nguy cơ phụ thuộc vòng và thứ tự không thể thỏa

Xét hai lời hứa:

- A phải kết thúc hoàn toàn trước khi B bắt đầu.
- B phải kết thúc hoàn toàn trước khi A bắt đầu.

Nếu chúng áp cùng một lần gọi và không có phân chia giai đoạn, đây là **vòng phụ thuộc không thể thỏa**. Trong around advice, trước/sau tạo một cấu trúc lồng:

```text
A.before -> B.before -> target -> B.after -> A.after
```

Ta có thể yêu cầu `A.before` trước `B.before` nhưng đồng thời `B.after` trước `A.after` mà không mâu thuẫn. Vì thế đồ thị cần mô tả **sự kiện/giai đoạn** chứ không chỉ nút “A”, “B” mơ hồ.

### 11.1. Chia một aspect thành prepare/finalize

Một cách giải quan hệ phức tạp là chia chính sách thành:

```text
Authorization.prepare
Operation.execute
Commit.confirm
Audit.finalize
```

Các điểm có thể có hợp đồng dữ liệu bất biến và lỗi rõ ràng. Trong các giao dịch quan trọng, đôi khi quy trình này thích hợp hơn như **orchestrator nghiệp vụ**, trong khi aspect chỉ đóng vai trò observation hoặc guard ở các ranh giới thích hợp.

### 11.2. Đừng dựa vào thứ tự phát hiện tệp

Thứ tự lớp được nạp, file được liệt kê hay aspect được đăng ký không nên dùng thay cho hợp đồng precedence trừ khi công nghệ có **bảo đảm chính thức**. Khi thay công cụ/phiên bản hoặc refactor package, phải chạy test cho thứ tự và coverage.

## 12. Short-circuit và ảnh hưởng tới aspect bên trong

Nếu Cache bao ngoài Authorization:

```text
Cache(Authorization(Target))
```

một cache hit có thể trả kết quả ngay và **Authorization không chạy**. Nếu kết quả cache dành riêng cho người dùng, bỏ qua quyền có thể tạo lỗi bảo mật.

Nếu Authorization bao ngoài Cache:

```text
Authorization(Cache(Target))
```

kiểm tra quyền có thể chạy trước khi cache trả dữ liệu. Nhưng còn phải xét key cache có bao gồm tenant/user và dữ liệu có bị stale hay không. Chỉ đổi thứ tự không tự bảo đảm cấu hình cache an toàn.

Tương tự, một interceptor `Fallback` trả giá trị sau lỗi có thể khiến aspect ngoài thấy **return bình thường** thay vì ngoại lệ gốc. Nếu mục tiêu là log lỗi đích, điểm quan sát phải nằm **bên trong** fallback hoặc có một tín hiệu kết quả tường minh.

### 12.1. Hai loại audit thường khác nhau

- **Attempt/denial audit:** ghi nhận có ai thử thao tác, kể cả bị chặn.
- **Committed-effect audit:** ghi nhận thao tác đã xác nhận hoàn tất.

Chúng có thể dùng chung hạ tầng ghi sự kiện nhưng không nên ép về một nhánh advice duy nhất mà không định nghĩa rõ. Một aspect ghi nhận **tất cả attempts** có thể nằm ngoài Authorization; một aspect **confirmed commit** cần kết quả đáng tin ở phía sau.

## 13. Concurrency, ngữ cảnh và vòng đời

### 13.1. Shared field gây lẫn các lượt gọi

Một singleton aspect có:

```java
Object currentRequest;
```

không nên dùng field đó để phối hợp request A và B. Hai luồng có thể ghi đè state, và trường còn giữ tham chiếu tới request sau khi lời gọi xong.

State phối hợp nên được truyền qua **invocation context** hoặc một scope được định nghĩa rõ. Nếu dùng `ThreadLocal`, phải lưu/khôi phục parent cho nested scope và `remove()` khi kết thúc trên thread sống lâu.

### 13.2. Async không giữ nguyên call stack

Một phương thức trả `CompletableFuture` rồi việc thật xảy ra trên executor. Context lưu theo thread gọi không tự truyền sang worker thread. Nếu cố giữ toàn bộ object request trong callback để truyền thông tin, có thể tạo retention hoặc truy cập đồng thời không an toàn.

Cần tách **correlation metadata bất biến** khỏi tài nguyên mutable, xác định khi nào task hoàn tất, ai dọn context và khi nào audit/metrics ghi sự kiện. Vòng đời logical request có thể rộng hơn một lần method invocation đồng bộ.

### 13.3. Resource scope có owner

Nếu một aspect mở connection/lock/span còn aspect khác dùng hoặc đóng nó, cần hợp đồng:

- Ai tạo;
- Ai được phép dùng;
- Có thể chia sẻ qua retry/async không;
- Ai đóng trên return, throw, cancel và timeout;
- Nếu đóng lỗi, xử lý ngoại lệ gốc thế nào;
- Có cần scope riêng cho từng attempt không.

Không đưa logic “ai rảnh thì đóng” vào nhiều advice độc lập. Ownership không rõ là nguồn lỗi double-close, leak hoặc dùng resource đã đóng.

## 14. Lỗi quan sát và fail-open/fail-closed

Không phải aspect nào lỗi cũng nên phá nghiệp vụ. Nhưng quyết định phải có căn cứ:

| Chính sách | Khi bản thân aspect lỗi | Gợi ý thiết kế |
| --- | --- | --- |
| Ghi metric phụ trợ | Có thể cần giữ nghiệp vụ chạy, tùy mức quan trọng | Tách lỗi telemetry và hạn chế tác động |
| Trace/log phụ trợ | Tương tự, chú ý dữ liệu nhạy cảm | Không để logger gây lỗi ngoài ý muốn |
| Authorization bắt buộc | Không được bỏ qua kiểm tra | Fail closed ở ranh giới đáng tin |
| Audit bắt buộc theo quy định | Không thể bỏ qua mất sự kiện một cách im lặng | Durable recording/coordinator và chiến lược lỗi |
| Cache tối ưu | Có thể rơi về đường tính toán gốc nếu an toàn | Không dùng fallback để bỏ qua quyền |
| Retry | Không được tự chạy vô hạn hoặc lặp effect | Chính sách lỗi, deadline, idempotency |

“Fail-open” và “fail-closed” chỉ có ý nghĩa trong **hợp đồng cụ thể**; không mặc định tất cả logging đều là optional, hay tất cả audit có thể hoàn thành ở background mà vẫn giữ nghĩa vụ.

## 15. Kiểm thử tính độc lập và sự phối hợp

Một bộ test nên tách **kết quả nghiệp vụ** khỏi **dấu vết của aspect**.

| Kịch bản | Điều cần chứng minh |
| --- | --- |
| Chỉ Trace bật | Kết quả/ngoại lệ gốc đúng; không có lệ thuộc Metrics |
| Chỉ Metrics bật | Bộ đếm theo đơn vị đã định đúng |
| Trace và Metrics hoán đổi | Bất biến nghiệp vụ giữ nguyên; semantics đo được đánh giá theo contract |
| Authorization rồi CommitAudit | Có tín hiệu xác thực trước khi audit được phép chạy |
| Đảo Audit trước Authorization | Cấu hình sai bị phát hiện trước tác dụng phụ |
| Token không hợp lệ | Target không chạy theo đường proxy được bảo vệ |
| Cache hit | Những guard bắt buộc không bị bypass |
| Target ném ngoại lệ | Log/audit không ghi nhầm commit |
| Transaction commit thất bại | Không ghi `committed` khi chưa có xác nhận |
| Retry nhiều lần | Phân biệt request/attempt/effect; không ghi audit trùng |
| Lời gọi trực tiếp target | Phát hiện đường bypass ngoài proxy |
| Nhiều lời gọi đồng thời | State không lẫn giữa người gọi |
| Lời gọi bất đồng bộ | Dữ liệu và sự kiện completion ở đúng lifecycle |
| Aspect phụ trợ bị lỗi | Kết quả theo đúng chính sách fail-open/closed |
| Tắt aspect bắt buộc | Hệ không âm thầm tiếp tục trái invariant |
| Thay đổi precedence | Các hợp đồng thứ tự vẫn được thỏa |

### 15.1. Property quan trọng hơn một thứ tự log cố định

Đối với những aspect được xem là độc lập, kiểm thử nên tập trung **invariants**:

- Mỗi lần gọi target có tác dụng phụ đúng số lần;
- Giá trị/ngoại lệ được bảo toàn nếu chỉ quan sát;
- Không dùng dữ liệu người gọi khác;
- Không có resource còn mở sau ranh giới bắt buộc;
- Kết quả nghiệp vụ không phụ thuộc việc hoán đổi thứ tự giữa các observer khi điều kiện đã định rõ.

Đối với aspect phải phối hợp, cần test **preconditions/postconditions**, không chỉ khẳng định A in dòng log trước B.

### 15.2. Mutation test cho thứ tự

Một cách phát hiện hợp đồng thiếu là **cố ý đảo** hai interceptor hoặc tắt một interceptor trong môi trường test. Nếu hệ vẫn cho effect chạy dù bỏ Authorization bắt buộc, coverage/hợp đồng chưa đủ.

Trong ví dụ Java 17, đặt `CommittedAudit` trước `Authorization` tạo lỗi `MISORDER` trước target — một tín hiệu hữu ích, nhưng không đủ để bảo đảm các đường khác không bypass proxy.

## 16. Các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Mọi aspect đều được coi độc lập vì nằm ở file khác | Phụ thuộc order/state bị ẩn | Kiểm kê invariant và precedence |
| Mọi aspect đều gọi trực tiếp nhau | Coupling cao, dễ tạo dependency cycle | Dùng contract/context/coordinator |
| Cho rằng đổi thứ tự observer luôn vô hại | Metric/timing có thể đổi nghĩa | Định nghĩa unit đo và scope |
| Đặt cache ngoài authorization thiếu kiểm tra | Bypass quyền khi cache hit | Bảo vệ quyền trước mọi đường trả kết quả |
| Audit `after-returning` được coi luôn là commit | Ghi sai trạng thái nghiệp vụ | Dùng confirmed outcome và durable strategy |
| Shared static field `authorized` | Lẫn trạng thái giữa requests | Context theo invocation, nguồn tin cậy |
| Một aspect nuốt exception của aspect khác | Che lỗi bắt buộc | Hợp đồng xử lý lỗi tường minh |
| Retry vô hạn hoặc mọi exception | Tải tăng và effect trùng | Giới hạn, filter, idempotency |
| Không kiểm tra đường bypass proxy | Thiếu chính sách ở đường gọi trực tiếp | Kiểm chứng coverage và ranh giới đáng tin |
| Tách tài nguyên khỏi owner cleanup | Leak/double-close | Chủ sở hữu rõ, finally/close |
| Lưu request vào aspect singleton | Retention và lộ dữ liệu | Context ngắn hạn hoặc dữ liệu tối thiểu |
| Đo `SUCCESS` ngoài retry rồi suy một effect | Bỏ qua duplicate commit | Đếm attempts và actual effects riêng |
| Phụ thuộc thứ tự phát hiện ngẫu nhiên | Hành vi thay khi refactor/deploy | Precedence được quy định và test |
| Gộp mọi chính sách vào một aspect lớn | Khó hiểu và khó kiểm thử | Tách trách nhiệm không phụ thuộc, gom chặt những phần thật sự không thể tách |

## 17. Checklist thiết kế

Trước khi cho hai aspect áp vào một điểm:

1. Viết **mục tiêu riêng** của từng aspect bằng một câu.
2. Xác định **join point, pointcut và cơ chế weaving/proxy** thực tế.
3. Liệt kê **dữ liệu đầu vào/đầu ra**, owner và phạm vi vòng đời.
4. Phân loại quan hệ: độc lập, precedence-only, shared data, shared resource hay atomic coordination.
5. Quy định thứ tự tương đối ở **before/proceed/after/throw**, không chỉ tên aspect.
6. Kiểm tra short-circuit, retry, fallback và kết quả/ngoại lệ.
7. Với effect nhạy cảm, xác định **ranh giới tin cậy** và cách tránh đường bypass.
8. Đặt state theo invocation hoặc context có lifecycle rõ; tránh static mutable request state.
9. Xác định ai dọn tài nguyên ở đường return/throw/cancel/async.
10. Cân nhắc coordinator nếu phụ thuộc tạo vòng hoặc đòi atomicity.
11. Test các hoán vị hợp lệ và cấu hình sai, đồng thời test ngoài pointcut.
12. Đo đơn vị thích hợp: logical request, attempt, successful return, committed effect.

## 18. Bài tập vận dụng và đáp án

### Bài 1 — Độc lập hay chỉ không import nhau?

Trace và Retry không gọi API của nhau. Nhưng Trace phải đo **mỗi attempt**, không phải tổng một logical request. Có thể đặt Trace ngoài Retry tùy ý không?

**Đáp án:** Không. Chúng độc lập về mã nhưng yêu cầu đo theo từng attempt khiến Trace cần ở bên trong chuỗi Retry trong mô hình retry có `proceed` chạy lại phần đuôi, hoặc phải nhận attempt event theo hợp đồng khác.

### Bài 2 — Cache và quyền

Một Cache interceptor có thể trả ngay mà không `proceed`. Authorization nằm bên trong. Rủi ro?

**Đáp án:** Cache hit có thể bỏ qua Authorization. Nếu quyền phải được kiểm tra với mọi lần truy cập, cần bảo vệ trước cache hoặc định nghĩa một ranh giới quyền không thể bypass; key cache cũng phải có scope quyền phù hợp.

### Bài 3 — Audit và commit

Một audit aspect chỉ thấy target trả bình thường nên ghi “payment committed”. Tại sao chưa đủ?

**Đáp án:** Return bình thường không tự là bằng chứng commit; kết quả có thể biểu thị từ chối, transaction ngoài chưa commit hoặc tác vụ async chưa hoàn thành. Phải có **tín hiệu nghiệp vụ đáng tin** và ranh giới durable phù hợp.

### Bài 4 — Dependency graph

A cần chuẩn bị dữ liệu trước B; B cần chạy trước operation; C chỉ ghi metrics độc lập. Quan hệ cứng nào cần ghi?

**Đáp án:** `A.prepare → B → operation`. C có thể là module riêng nhưng vị trí đo phải được định nghĩa, ví dụ ngoài B để đếm attempts bị từ chối. Không cần thêm dependency A↔C nếu chúng không dùng dữ liệu của nhau.

### Bài 5 — Shared static field

Authorization ghi `AspectState.authorized=true`, Audit đọc static field. Hai yêu cầu song song có an toàn không?

**Đáp án:** Không. Request B có thể đọc cờ do request A đặt, dẫn tới lỗi nghiêm trọng. State phải có ownership và phạm vi per-invocation/per-request đáng tin; với bảo mật cần kiểm soát ranh giới thực sự.

### Bài 6 — Misordering

Trong ví dụ Java 17, vì sao đưa CommittedAudit lên trước Authorization khiến lời gọi bị từ chối?

**Đáp án:** CommittedAudit kiểm tra precondition `state.authorized` trước khi chuyển tiếp; Authorization chưa chạy nên state mới vẫn false. Nó ném `IllegalStateException`, chặn target và làm lộ cấu hình sai thay vì im lặng.

### Bài 7 — Lỗi từ observer

Một aspect Metrics chỉ đo thời gian nhưng backend metrics ném lỗi. Có nên mặc định cho lỗi đó đi ra client?

**Đáp án:** Tùy hợp đồng. Với metrics phụ trợ, thường cần cô lập lỗi quan sát để không thay đổi kết quả nghiệp vụ; với chính sách bắt buộc, có thể cần fail-closed. Việc xử lý phải được thiết kế có chủ đích và test.

### Bài 8 — Retry và transaction

Với `Retry(Transaction(Target))` và `Transaction(Retry(Target))`, điều gì cần xác định trước khi hoán đổi?

**Đáp án:** Transaction được mở một lần hay mỗi attempt, trạng thái transaction sau lỗi có thể tái sử dụng không, effect ngoài transaction có an toàn retry không và commit được quan sát khi nào. Không có một đáp án đúng chung.

### Bài 9 — Tách bằng coordinator

Hai aspect A và B cần quyết định chung để ghi dữ liệu bền vững nguyên tử, đồng thời mỗi aspect phụ thuộc kết quả chưa có của bên kia. Nên làm gì?

**Đáp án:** Cần xem lại ranh giới thiết kế; thường nên có một service/coordinator và giao thức commit nhất quán, không cố giải bằng thứ tự ngẫu nhiên hoặc shared mutable flags trong interceptor.

### Bài 10 — Coverage

Authorization aspect đã chạy ở các integration test thông qua proxy. Có thể khẳng định mọi đường tới target được kiểm tra quyền chưa?

**Đáp án:** Không. Các lời gọi trực tiếp target, self-invocation hoặc đường nằm ngoài phạm vi weaver/proxy có thể không qua aspect. Cần kiểm soát ranh giới tin cậy và kiểm thử các đường bypass.

## 19. Ghi nhớ

- **Aspect độc lập** là aspect có trách nhiệm và dữ liệu riêng, không cần kết quả/trạng thái của aspect khác; điều đó **không tự bảo đảm hoán đổi thứ tự vô điều kiện**.
- **Aspect phải phối hợp** khi phụ thuộc precedence, state, kết quả, lỗi, vòng đời tài nguyên, độ phủ bảo mật hoặc tính nguyên tử.
- Xác định thứ tự bằng **hợp đồng sự kiện và giai đoạn**, xét cả before/proceed/after, không chỉ liệt kê tên.
- Dùng **invocation context hoặc giao diện phối hợp rõ** thay cho static request state; tránh giữ object ngắn hạn ngoài vòng đời.
- **Short-circuit, retry, fallback và transaction** là nơi phụ thuộc giữa aspect dễ lộ rõ nhất.
- **After-returning không đồng nghĩa committed**, và proxy không chứng minh được mọi đường gọi đều được bảo vệ.
- Nếu hai chính sách cần một bất biến nguyên tử hoặc tạo dependency cycle, cân nhắc **coordinator/biên nghiệp vụ** thay vì cố gắng giải mọi thứ bằng aspect order.
- Kiểm thử **thứ tự, cấu hình sai, kết quả/ngoại lệ, số lần effect, concurrency và đường bypass** trước khi coi việc tách/ phối hợp là an toàn.
