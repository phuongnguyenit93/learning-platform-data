# Đặt ranh giới giao dịch bằng advice theo khả năng nền tảng trong AOP

## 1. Bài toán: giao dịch là chính sách xuyên suốt lời gọi

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP), nhiều phương thức nghiệp vụ có cùng một chính sách: trước khi thực hiện một đơn vị công việc phải mở hoặc tham gia giao dịch, khi thực hiện thành công thì xác nhận, khi xảy ra lỗi thuộc chính sách rollback thì hủy những thay đổi chưa được xác nhận. Nếu lặp đoạn mã này trong mọi phương thức, logic nghiệp vụ bị trộn với điều phối giao dịch, khó kiểm tra và dễ bỏ sót đường lỗi.

**Transaction demarcation** là việc xác định chính xác **bắt đầu**, **phạm vi tham gia**, **kết thúc** và **người sở hữu kết thúc** một giao dịch. Một *around advice* có thể đặt chính sách ấy quanh lời gọi đến phương thức đích (*join point*):

~~~text
Bên gọi
   |
   v
[ Transaction advice ]
   | - chọn chính sách
   | - bắt đầu/tham gia giao dịch
   v
[ Phương thức nghiệp vụ ]
   | - gọi các tài nguyên tham gia
   v
[ Transaction advice ]
   | - commit, rollback hoặc rời giao dịch theo vai trò
   v
Bên gọi nhận giá trị / ngoại lệ
~~~

Tuy nhiên, **advice không tự cung cấp transaction manager, isolation, rollback hay khả năng khôi phục dữ liệu**. AOP chỉ là cơ chế đặt chính sách ở một ranh giới chương trình. Việc transaction thực sự có hiệu lực phụ thuộc khả năng intercept lời gọi của nền tảng AOP, transaction manager, sự hỗ trợ của tài nguyên (cơ sở dữ liệu, hệ thống thông điệp...) và hợp đồng đồng bộ/bất đồng bộ của API.

Nội dung bài học tập trung AOP tổng quát, từ mức khái niệm đến các giới hạn nâng cao khi áp dụng chính sách giao dịch bằng advice, không phụ thuộc một framework ứng dụng cụ thể.

## 2. Trước hết phải xác định “giao dịch” có nghĩa gì

Một giao dịch thường được kỳ vọng có các thuộc tính ACID trong phạm vi được tài nguyên hỗ trợ:

- **Atomicity (tính nguyên tử):** các thay đổi trong cùng transaction thành công như một đơn vị hoặc được rollback theo hợp đồng.
- **Consistency (tính nhất quán):** các ràng buộc dữ liệu vẫn được duy trì khi chuyển trạng thái hợp lệ; ứng dụng vẫn phải thực thi quy tắc nghiệp vụ.
- **Isolation (tính cô lập):** mức độ các giao dịch đồng thời có thể nhìn thấy thay đổi của nhau phụ thuộc isolation level thực tế.
- **Durability (tính bền vững):** sau commit thành công, tài nguyên bảo đảm độ bền theo cấu hình và hợp đồng của nó.

Không phải bất kỳ thao tác nào cũng có thể rollback: lời gọi HTTP đã phát ra, email đã gửi hoặc file đã đẩy tới dịch vụ ngoài **không tự quay ngược** chỉ vì cơ sở dữ liệu rollback.

Cần phân biệt ba tầng trách nhiệm:

| Tầng | Trách nhiệm | Không nên tự nhận |
| --- | --- | --- |
| **AOP/advice** | Chọn điểm áp chính sách, gọi begin/commit/rollback, phân loại outcome và bảo toàn ngữ nghĩa lời gọi | Không tự biến thao tác không có transaction thành thao tác nguyên tử |
| **Transaction manager / coordinator** | Tạo, liên kết, tạm ngưng, resume, commit/rollback transaction; quản lý trạng thái | Không tự làm mọi tài nguyên bên ngoài tham gia |
| **Resource/participant** | Thực hiện truy cập dữ liệu và cơ chế giao dịch thật theo connection/session/transaction | Không tự chia sẻ transaction với tài nguyên khác nếu không có protocol phù hợp |

Nếu một nền tảng chỉ có cơ chế AOP để chặn lời gọi mà không có transaction manager hay resource có khả năng giao dịch, advice vẫn có thể ghi log hoặc chặn thao tác, nhưng **không thể bảo đảm transaction thực** chỉ bằng `begin()` và `commit()` giả lập.

## 3. Tại sao *around advice* phù hợp nhất?

Các loại advice có khả năng khác nhau:

| Loại advice | Thông tin thời điểm | Vai trò thích hợp |
| --- | --- | --- |
| Before | Trước phương thức đích | Kiểm tra chính sách, khởi tạo context khi nền tảng hỗ trợ |
| After returning | Khi phương thức đích trả bình thường | Ghi nhận return, có thể đóng phạm vi nếu sở hữu giao dịch và đã xác định rõ lifecycle |
| After throwing | Khi phương thức đích ném lỗi đồng bộ | Ghi nhận ngoại lệ, đánh dấu rollback theo policy |
| After/finally | Sau khi lời gọi kết thúc bất kể outcome | Dọn context; không mặc định mọi outcome đều commit |
| **Around** | Bao trọn logic gọi `proceed()` và nhận outcome | Đặt đầy đủ begin/participate → proceed → commit/rollback → cleanup |

Around advice hữu ích vì nó giữ quyền quyết định **có gọi đích hay không**, **gọi lúc nào**, **giữ trạng thái gì qua lời gọi**, **xử lý cả đường return và throw ra sao**. Trong thiết kế transaction thông thường, advice cần bảo đảm:

1. Chọn transaction policy trước `proceed()`.
2. Nếu cần giao dịch mới, yêu cầu manager tạo giao dịch; nếu đang có giao dịch, xác định tham gia/tách giao dịch theo propagation policy.
3. Đặt transaction context ở đúng tài nguyên và phạm vi thực thi.
4. Gọi `proceed()` **đúng một lần** trong đường đi thông thường, trừ khi hợp đồng chính sách chủ đích có retry.
5. Nếu thành công và advice sở hữu giao dịch: commit, xử lý commit failure.
6. Nếu ném lỗi: quyết định rollback hay commit theo chính sách và mức ownership.
7. Tháo ràng buộc transaction context, giải phóng hoặc trả connection, khôi phục transaction bị tạm ngưng, không che lỗi gốc.

**Không đồng nhất việc advice đã chạy với việc transaction đã được resource áp dụng.** Việc kết nối thật sự tham gia transaction mới quyết định rollback/commit có tác động dữ liệu hay không.

## 4. Ranh giới lời gọi phải trùng với ranh giới nghiệp vụ mong muốn

Một chính sách giao dịch cần định nghĩa rõ **đơn vị công việc**. Ví dụ chuyển tiền giữa hai tài khoản cùng cơ sở dữ liệu:

~~~text
transfer(A, B, amount)
   ├── kiểm tra A còn đủ tiền
   ├── giảm số dư A
   ├── tăng số dư B
   └── ghi lịch sử thay đổi
~~~

Nếu toàn bộ thao tác này phải thành công hoặc thất bại cùng nhau, một transaction có thể bao quanh `transfer(...)` **nếu cả ba thay đổi được thực hiện qua cùng tài nguyên tham gia transaction**. Ngược lại, nếu tách transaction ở `debit()` và `credit()` độc lập, commit của bước giảm tiền có thể đã xảy ra khi bước tăng tiền thất bại; hai transaction độc lập không tự trở thành một đơn vị nguyên tử.

Khi chọn method join point, hãy phân biệt:

- **Method-level boundary:** trước/sau lời gọi phương thức. Dễ hiểu, nhưng có thể quá nhỏ, quá lớn, hoặc không đi qua cơ chế interception.
- **Use-case boundary:** bao toàn bộ một thao tác nghiệp vụ có yêu cầu nhất quán. Thường là điểm thích hợp để lựa chọn method transactional.
- **Resource boundary:** connection/session/transaction thật. Phải khớp vòng đời resource với phương thức được bao.
- **Cross-system boundary:** qua nhiều dịch vụ/tài nguyên. Một method-level advice đơn lẻ không đủ bảo đảm tính nguyên tử phân tán.

Một giao dịch kéo dài qua nhiều lời gọi đích không nhất thiết là một transaction mới cho mỗi lời gọi. Nếu các lời gọi con cần cùng đơn vị nhất quán, transaction manager phải hỗ trợ cơ chế tham gia/gộp context phù hợp.

## 5. Khả năng nền tảng AOP quyết định phạm vi tác dụng

“AOP có thể đặt advice” không đồng nghĩa “mọi đường gọi đều được chặn”. Việc một method được instrument thực tế phụ thuộc kỹ thuật:

| Cơ chế AOP | Có thể can thiệp ở đâu? | Hệ quả với transaction boundary |
| --- | --- | --- |
| **Decorator thủ công** | Những lời gọi thực sự đi qua đối tượng bọc | Gọi trực tiếp đối tượng gốc sẽ bỏ qua advice |
| **Dynamic proxy theo interface** | Lời gọi qua proxy tới các method của interface được hỗ trợ | Phương thức ngoài interface hoặc gọi nội bộ trực tiếp thường không được intercept |
| **Proxy dựa trên subclass** | Các method có thể override theo giới hạn của ngôn ngữ/runtime | Method `final`, `private`, constructor, visibility và thiết kế lớp có thể hạn chế |
| **Bytecode weaving** | Các join point được bộ weaving và cấu hình hỗ trợ | Phạm vi có thể rộng hơn proxy, nhưng phụ thuộc build/load-time instrumentation và pointcut |
| **Instrumentation/runtime agent** | Điểm được runtime cho phép biến đổi và hook vào | Có ràng buộc class loader, module access, thứ tự instrumentation, chi phí và tương thích |

Ví dụ, với proxy:

~~~java
class AccountOperations {
    public void outer() {
        inner(); // Lời gọi trực tiếp trên this, không đi qua proxy ngoài
    }

    public void inner() {
        // Công việc cần transaction.
    }
}
~~~

Đây là đoạn minh họa, không phải chương trình độc lập. Nếu chỉ `inner()` được proxy instrument nhưng `outer()` gọi `this.inner()`, lời gọi này thường **không đi qua proxy**, nên advice ở đường proxy của `inner()` không chạy. Nếu weaving intercept được execution join point tương ứng thì kết quả có thể khác. Phải xác minh đúng cơ chế đang dùng, không suy bằng tên annotation hoặc pointcut.

Cũng cần xét việc gọi từ constructor, phương thức static, method không thể override, gọi qua reflection và callback do runtime khác kích hoạt; mọi trường hợp chỉ được coi là có transaction khi công cụ AOP thực sự intercept được và resource tham gia đúng context.

## 6. Cơ chế chọn chính sách và propagation

Trước khi tạo giao dịch, advice phải biết policy cho join point. Policy có thể đến từ cấu hình bên ngoài, metadata/annotation tùy chọn, quy ước tên method, hoặc pointcut. Metadata chỉ có ý nghĩa nếu bộ chọn điểm cắt và bộ thực thi transaction **thực sự đọc và áp dụng** nó.

Một tập policy điển hình:

- **Propagation:** tham gia transaction đang có, bắt đầu transaction mới, yêu cầu phải có hoặc yêu cầu không có transaction.
- **Isolation:** mức cô lập theo khả năng resource/driver; không tự phát sinh chỉ vì policy gọi tên nó.
- **Timeout:** hạn giao dịch do coordinator/resource có thể thực thi; khác với timeout đợi của bên gọi.
- **Read-only:** có thể là hint tối ưu hoặc ràng buộc thật tùy hệ thống; không mặc nhiên chặn mọi lệnh ghi.
- **Rollback rules:** lỗi nào kích hoạt rollback, lỗi nào cho phép commit; phải ghi rõ cả trường hợp checked/unchecked.
- **Naming/correlation:** nhận diện giao dịch để debug và gắn trace.
- **Owner:** lời gọi hiện tại **sở hữu** transaction mới hay chỉ **tham gia** transaction của bên ngoài.

Propagation cần đặc biệt thận trọng:

| Chính sách khái niệm | Nếu đã có transaction | Nếu chưa có transaction | Lưu ý |
| --- | --- | --- | --- |
| **Join-or-create** | Tham gia hiện có | Tạo transaction mới | Phương thức con thường không tự commit giao dịch thuộc bên ngoài |
| **Create-new** | Tạm ngưng transaction hiện có và tạo cái mới nếu manager hỗ trợ | Tạo mới | Transaction con độc lập; commit của nó không tự rollback khi outer rollback |
| **Require-existing** | Tham gia | Báo lỗi chính sách | Không âm thầm tạo transaction |
| **Run-without** | Thực thi ngoài transaction nếu có thể, tạm ngưng nếu cần | Thực thi bình thường | Không đảm bảo mọi resource thật sự vô giao dịch |
| **Nested-savepoint** | Tạo phạm vi savepoint trong transaction hiện tại nếu hỗ trợ | Có thể tạo mới theo thiết kế | Rollback về savepoint không tương đương transaction độc lập |

Đây là **khái niệm chính sách**, không phải các tên enum được tất cả nền tảng hỗ trợ. Nếu manager không thể suspend/resume, không có savepoint hay resource không hỗ trợ mức isolation được yêu cầu, advice cần xử lý theo hợp đồng (thường từ chối hoặc báo không hỗ trợ), không giả vờ giao dịch đã có đầy đủ tính năng.

### Ownership: ai có quyền commit?

Ví dụ lời gọi `placeOrder()` mở transaction rồi gọi `reserveInventory()` tham gia cùng transaction. Advice của `reserveInventory()` có thể “rời phạm vi” nhưng **không nên tự commit** transaction đang thuộc về `placeOrder()`. Nếu method con có lỗi cần rollback, manager có thể đánh dấu toàn giao dịch là *rollback-only*; outer không được commit nhầm. Ngược lại, với transaction mới độc lập theo policy create-new, advice sở hữu giao dịch đó và cần kết thúc chính nó.

Đây là khác biệt giữa **thoát khỏi một advice** và **kết thúc transaction mà advice có quyền sở hữu**.

## 7. Ví dụ Java 17: mô phỏng *around advice* bằng dynamic proxy

Ví dụ sau chạy độc lập trên Java 17+, thể hiện cách advice bắt đầu context, gọi nghiệp vụ, commit nếu thành công và rollback nếu có exception. Nó dùng `java.lang.reflect.Proxy` (AOP ở mức proxy theo interface) và một sổ cái trong bộ nhớ. **Đây là mô hình transaction giáo dục**: không sử dụng database/transaction manager thực, không bảo đảm ACID dưới truy cập đồng thời hoặc sự cố tiến trình. Trong hệ thống thật, các lời gọi `begin/commit/rollback` phải được thay bằng coordinator/resource hỗ trợ transaction.

Lưu thành tệp **`TransactionAdviceDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.LinkedHashMap;

public class TransactionAdviceDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface TxBoundary {}

    interface TransferService {
        @TxBoundary
        void transfer(String from, String to, int amount, boolean fail);
    }

    static final class Ledger {
        private final LinkedHashMap<String, Integer> committed =
                new LinkedHashMap<>();

        // Chỉ để minh họa transaction context cho một luồng.
        private final ThreadLocal<LinkedHashMap<String, Integer>> draft =
                new ThreadLocal<>();

        Ledger() {
            committed.put("Alice", 100);
            committed.put("Bob", 50);
        }

        void begin() {
            if (draft.get() != null) {
                throw new IllegalStateException("Nested transaction unsupported");
            }
            draft.set(new LinkedHashMap<>(committed));
            System.out.println("[tx] begin");
        }

        void move(String from, String to, int amount) {
            LinkedHashMap<String, Integer> data = draft.get();
            if (data == null) {
                throw new IllegalStateException("No active transaction");
            }
            if (amount <= 0 || data.get(from) < amount) {
                throw new IllegalArgumentException("Invalid transfer");
            }
            data.put(from, data.get(from) - amount);
            data.put(to, data.get(to) + amount);
        }

        void commit() {
            LinkedHashMap<String, Integer> data = draft.get();
            if (data == null) {
                throw new IllegalStateException("No active transaction");
            }
            committed.clear();
            committed.putAll(data);
            draft.remove();
            System.out.println("[tx] commit");
        }

        void rollback() {
            draft.remove();
            System.out.println("[tx] rollback");
        }

        String snapshot() {
            return "Alice=" + committed.get("Alice")
                    + ", Bob=" + committed.get("Bob");
        }
    }

    static final class TransferServiceImpl implements TransferService {
        private final Ledger ledger;

        TransferServiceImpl(Ledger ledger) {
            this.ledger = ledger;
        }

        @Override
        public void transfer(
                String from, String to, int amount, boolean fail) {
            System.out.println("[service] moving " + amount);
            ledger.move(from, to, amount);
            if (fail) {
                throw new IllegalStateException("Simulated failure");
            }
        }
    }

    static TransferService withAdvice(
            TransferService target, Ledger ledger) {

        return (TransferService) Proxy.newProxyInstance(
                TransferService.class.getClassLoader(),
                new Class<?>[] { TransferService.class },
                (proxy, method, args) -> {
                    if (!method.isAnnotationPresent(TxBoundary.class)) {
                        try {
                            return method.invoke(target, args);
                        } catch (InvocationTargetException ex) {
                            throw ex.getCause();
                        }
                    }

                    ledger.begin();
                    try {
                        Object result = method.invoke(target, args);
                        ledger.commit();
                        return result;
                    } catch (InvocationTargetException ex) {
                        ledger.rollback();
                        throw ex.getCause();
                    } catch (Throwable ex) {
                        ledger.rollback();
                        throw ex;
                    }
                });
    }

    public static void main(String[] args) {
        Ledger ledger = new Ledger();
        TransferService service =
                withAdvice(new TransferServiceImpl(ledger), ledger);

        System.out.println("initial: " + ledger.snapshot());

        service.transfer("Alice", "Bob", 30, false);
        System.out.println("after success: " + ledger.snapshot());

        try {
            service.transfer("Alice", "Bob", 10, true);
        } catch (IllegalStateException ex) {
            System.out.println("caught: " + ex.getMessage());
        }

        System.out.println("after failure: " + ledger.snapshot());
    }
}
~~~

Chạy:

~~~bash
javac TransactionAdviceDemo.java
java TransactionAdviceDemo
~~~

Đầu ra:

~~~text
initial: Alice=100, Bob=50
[tx] begin
[service] moving 30
[tx] commit
after success: Alice=70, Bob=80
[tx] begin
[service] moving 10
[tx] rollback
caught: Simulated failure
after failure: Alice=70, Bob=80
~~~

**Tại sao kết quả này đúng?**

- `withAdvice(...)` trả một dynamic proxy thực thi `TransferService`. Mỗi lời gọi `transfer(...)` từ bên ngoài đi qua `InvocationHandler`.
- Advice phát hiện metadata `@TxBoundary` trên method **interface**, bắt đầu bản sao trạng thái bằng `ledger.begin()` rồi gọi target đúng một lần qua reflection.
- Ở lần đầu, target giảm Alice từ 100 xuống 70 và tăng Bob từ 50 lên 80 trên bản nháp. Vì không có exception, advice commit bản nháp vào trạng thái chính thức.
- Ở lần sau, target thay đổi bản nháp rồi cố ý ném `IllegalStateException`. Reflection bọc exception trong `InvocationTargetException`; advice **unwrap cause**, rollback bằng cách bỏ bản nháp rồi ném lại nguyên nhân gốc. Trạng thái chính thức vẫn `Alice=70, Bob=80`.
- `ThreadLocal` chỉ minh họa việc liên kết context tới luồng gọi; **không phải cơ chế truyền transaction an toàn qua executor hoặc hệ thống phân tán**. Demo cũng không hỗ trợ nested transaction, retry, connection pooling, đồng thời, crash recovery hoặc isolation thực.
- Với method không có `@TxBoundary`, proxy minh họa chỉ forward. Nếu một method của đối tượng đích tự gọi phương thức khác của chính nó, đường gọi trực tiếp ấy có thể đi qua `this` và bỏ qua proxy.
- Exception trong ví dụ là unchecked, phù hợp kiểu method interface đã khai báo. Với checked exception, hợp đồng method/proxy phải khai báo hoặc bao lỗi đúng quy tắc ngôn ngữ; rollback policy phải định nghĩa riêng.

**Lưu ý khi đem ý tưởng vào ứng dụng thật:** cần transaction manager điều phối resource, xử lý failure ở commit/rollback, ownership và cleanup ngay cả khi có exception; không dùng thao tác sao chép toàn bộ map làm cơ sở transaction production. Ví dụ dùng một luồng tuần tự chỉ để cho thấy vị trí *advice* và sự khác nhau giữa commit/rollback.

## 8. Một khung xử lý lỗi production cần cân nhắc

Pseudocode sau diễn tả các bước điều phối; không phải API Java sẵn có và không phải chương trình độc lập:

~~~text
policy = resolvePolicy(joinPoint)
scope  = transactionManager.enter(policy)

try:
    value = proceedExactlyOnce()
    transactionManager.finishNormally(scope)
    return value
catch failure:
    transactionManager.finishWithFailure(scope, failure, policy.rollbackRules)
    rethrow original failure
finally:
    transactionManager.leaveScopeAndRestorePreviousContext(scope)
~~~

`finishNormally` **không nhất thiết là commit**: nếu chỉ tham gia transaction do outer sở hữu thì đơn giản có thể trả quyền điều khiển, commit ở outer. Tương tự, `finishWithFailure` có thể rollback transaction do lời gọi sở hữu, hoặc đánh dấu rollback-only đối với transaction tham gia bên ngoài.

Để tránh mất thông tin lỗi, hệ thống phải định nghĩa rõ ưu tiên và cách kết hợp các lỗi:

- **Lỗi nghiệp vụ** do `proceed()` ném.
- **Lỗi rollback** phát sinh khi đang xử lý lỗi nghiệp vụ.
- **Lỗi commit** sau khi logic nghiệp vụ chạy xong.
- **Lỗi cleanup/resume** khi khôi phục context hoặc đóng tài nguyên.

Không để lỗi rollback thứ cấp âm thầm che mất lỗi nghiệp vụ gốc. Có thể giữ lỗi đầu tiên làm nguyên nhân chính và ghi lỗi phụ qua `Throwable.addSuppressed(...)` khi thích hợp. Riêng commit failure có thể để lại outcome **không chắc chắn** tùy protocol/tài nguyên; không được tự tuyên bố transaction chắc chắn rollback thành công chỉ vì `commit()` đã ném.

Nếu manager đã phân loại transaction bị rollback-only, advice phía ngoài không được coi `proceed()` return bình thường là đủ điều kiện commit. Quyết định cuối phụ thuộc trạng thái coordinator.

## 9. Rollback policy không đồng nghĩa “bất kỳ lỗi nào cũng rollback”

AOP cho phép áp một chính sách thống nhất, nhưng chính sách phải được định nghĩa chặt:

1. **Exception ném ra khỏi method:** có thể là lỗi nghiệp vụ hoặc lỗi lập trình. Cấu hình rõ rollback cho toàn bộ lỗi hay tập loại cụ thể.
2. **Exception đã bị bắt và xử lý bên trong method:** advice ở ngoài không nhìn thấy lỗi đó nếu method return bình thường. Nếu nghiệp vụ muốn rollback, phải đánh dấu rollback-only hoặc báo thất bại qua hợp đồng được advice hiểu.
3. **Checked và unchecked exceptions:** có nền tảng phân biệt mặc định, có nền tảng không; AOP tổng quát không áp một quy tắc chung cho mọi bộ máy.
4. **Commit failure:** xảy ra sau khi `proceed()` trả bình thường. Không thể đồng nhất “business logic return” với “transaction committed”.
5. **Rollback-only khi tham gia transaction:** method con có thể không sở hữu quyền commit nhưng làm transaction lớn hơn không thể commit.
6. **Failure không được gửi ra bằng exception:** một method trả kiểu kết quả `Result.failure(...)` vẫn có thể return bình thường. Advice cần được thiết kế để hiểu outcome dạng giá trị nếu đó là chính sách mong muốn.

Ví dụ với method trả mã lỗi thay vì ném:

~~~java
Result transfer(...) {
    if (insufficientFunds) {
        return Result.failure("Insufficient funds");
    }
    // ...
    return Result.success();
}
~~~

Đây là mã minh họa, không phải chương trình Java độc lập. Advice chỉ kiểm tra “method có ném exception không?” sẽ xem mọi `return` là bình thường, bất kể `Result.failure`. Nếu hợp đồng nghiệp vụ yêu cầu thất bại dạng giá trị làm rollback, policy phải có predicate đánh giá kết quả hoặc method phải dùng cơ chế đánh dấu rollback-only đúng khả năng manager.

Không dùng rollback như cơ chế chung để đảo ngược side effect đã phát ra ngoài tài nguyên tham gia giao dịch.

## 10. Giao dịch và lời gọi bất đồng bộ: ranh giới return rất dễ sai

Một method trả `CompletionStage<T>` có thể chỉ đặt lịch tác vụ rồi return handle:

~~~text
advice begin
    method returns CompletionStage<T>
advice commit
    ... worker đang chạy ...
    worker ghi dữ liệu / thất bại
    stage hoàn tất
~~~

Nếu advice commit **ngay khi method trả handle**, transaction có thể kết thúc trước khi worker thật sự truy cập tài nguyên. Transaction context gắn với luồng gọi bằng `ThreadLocal` không tự động có mặt trên worker thread; ngay cả khi truyền một reference context sang luồng khác, manager/resource có thể cấm dùng đồng thời hoặc dùng sau khi transaction kết thúc.

Không được giải quyết bằng cách chặn `stage.join()` trong advice mà không xét hợp đồng: điều đó phá tính không chặn, có thể giữ connection/lock lâu và gây deadlock hoặc cạn tài nguyên.

**Các lựa chọn hợp lệ phải dựa trên khả năng nền tảng:**

- **Giao dịch bên trong worker:** mở/kết thúc transaction tại phần thực thi thật trên worker, đặt quanh thao tác tài nguyên. Đây thường là ranh giới dễ hiểu nếu framework giao dịch chủ yếu đồng bộ và gắn với luồng.
- **Transaction scope bất đồng bộ được hỗ trợ thật:** chỉ nếu coordinator và resource cung cấp API quản lý transaction xuyên callback/continuation/luồng, mới có thể thiết kế advice gắn với tín hiệu hoàn tất. Phải kiểm tra context propagation, thread safety, ownership, timeout và cancellation.
- **Chia thành các transaction ngắn:** nếu tác vụ có nhiều giai đoạn kéo dài, mỗi giai đoạn ghi dữ liệu sử dụng transaction độc lập và phối hợp kết quả bằng cơ chế nghiệp vụ phù hợp.
- **Bên gọi nhận handle không đại diện cho commit:** ghi nhận `method.returned` riêng với `transaction.committed` và `operation.completed`. Không suy ba sự kiện trùng nhau.

Chỉ gắn `whenComplete(...)` để gọi commit về sau **không đủ an toàn** nếu transaction manager không hỗ trợ giữ transaction đang hoạt động xuyên thời gian và thread của callback. Transaction kéo dài vô hạn còn có thể giữ lock/connection và gây nghẽn hệ thống. Với publisher, return publisher có thể xảy ra trước subscribe; phải gắn transaction với vòng đời subscription và tài nguyên nếu nền tảng hỗ trợ, tránh tự subscribe trong aspect làm phát sinh thêm công việc.

## 11. Khi nào transaction kéo qua nhiều tài nguyên?

Một advice có thể yêu cầu một coordinator kết thúc transaction, nhưng nếu công việc chạm **nhiều tài nguyên độc lập**, coordinator phải có cơ chế điều phối thực tế. Một số tình huống:

| Tình huống | Giới hạn | Hướng thiết kế |
| --- | --- | --- |
| Nhiều bảng trên cùng database/connection tham gia transaction | Thường có thể atomic nếu tài nguyên/hợp đồng hỗ trợ | Dùng một transaction manager và kết nối tham gia |
| Hai database/resource độc lập | Commit bên A và B không tự nguyên tử | Protocol giao dịch phân tán phù hợp nếu thực sự cần và được hỗ trợ |
| Ghi database + gửi email | Email không rollback bằng transaction database | Outbox, xử lý bất đồng bộ và idempotency |
| Ghi database + gọi API dịch vụ khác | Lời gọi HTTP không tự tham gia transaction local | Saga/compensating action hoặc giao thức phối hợp rõ |
| Publish message sau khi commit database | Có khe hở giữa commit và publish | Transactional outbox hoặc tích hợp nguyên tử thực sự nếu khả năng nền tảng có |

**Two-phase commit** hoặc giao thức tương tự có thể phối hợp tài nguyên hỗ trợ và được cấu hình đúng, nhưng làm tăng độ phức tạp, phụ thuộc availability và xử lý heuristic failure. **Saga/compensation** chỉ tạo sự nhất quán nghiệp vụ theo nhiều bước; nó không giống ACID rollback trên toàn bộ hệ thống.

Do đó, transaction advice là **điểm áp chính sách** tốt, nhưng không phải công cụ biến mọi side effect thành một đơn vị atomic phân tán.

## 12. Ordering với các aspect khác

Nhiều aspect có thể cùng áp lên một join point: authorization, validation, retry, cache, tracing, metrics, transaction. Thứ tự nesting thay đổi kết quả:

~~~text
A. Retry ngoài transaction:
retry {
    transaction {
        call business
    }
}

B. Transaction ngoài retry:
transaction {
    retry {
        call business
    }
}
~~~

Ở cấu hình A, mỗi lần retry có thể có transaction độc lập: một attempt thất bại rollback trước khi attempt mới bắt đầu. Ở cấu hình B, nhiều attempt có thể nằm chung một transaction; nếu attempt đầu đã đánh dấu rollback-only hoặc resource rơi vào trạng thái không thể tiếp tục, retry trong transaction ấy có thể không đạt ý định. Chọn A hoặc B phải xuất phát từ chính sách nghiệp vụ, retryability của lỗi và khả năng rollback/restore của tài nguyên.

Các điểm ordering khác:

- **Authorization** thường phải xảy ra trước thao tác nghiệp vụ; có thể tránh mở transaction khi chưa được phép.
- **Validation** trước transaction có thể giảm thời gian giữ lock, nhưng validation dựa trên dữ liệu đồng thời đôi khi cần kiểm tra lại bên trong transaction.
- **Cache** có thể bỏ qua lời gọi đích; nếu aspect transaction nằm phía trong cache thì cache hit không bắt đầu transaction.
- **Logging/metrics** đặt ngoài transaction đo end-to-end bao cả commit; đặt trong transaction có thể không đo chi phí commit.
- **Audit/outbox** phải quyết định dữ liệu audit cần commit/rollback cùng nghiệp vụ hay độc lập.
- **Locking** nếu tham gia resource transaction thường được giải phóng theo trạng thái commit/rollback; dùng transaction quá rộng dễ gây tranh chấp.

Đừng chỉ quan tâm “advice có chạy không?”; phải vẽ rõ **thứ tự nesting, owner và thời điểm tài nguyên được giải phóng**.

## 13. Transaction context, luồng và tài nguyên

Transaction manager đồng bộ thường liên kết context với luồng hoặc một cấu trúc scoped context. Điều đó có hệ quả:

- **Self-invocation:** đường gọi bỏ qua proxy có thể không tạo/đổi policy.
- **Thread switch:** chuyển sang executor khác có thể làm mất context nếu không có cơ chế truyền hợp lệ.
- **Thread pool reuse:** phải cleanup trong mọi đường đi; `ThreadLocal` còn sót có thể ảnh hưởng công việc tiếp theo trên cùng worker thread.
- **Connection ownership:** việc begin/commit phải nhất quán với connection/session thật; sử dụng nhầm connection không tham gia transaction có thể auto-commit ngoài ý định.
- **Context suspension:** propagation create-new hoặc run-without có thể cần tạm ngưng và khôi phục transaction trước đó, không chỉ ghi đè biến trạng thái.
- **Cancellation/interruption:** không mặc định hủy thread đồng nghĩa rollback được mọi tài nguyên; cần đường cleanup chắc chắn.
- **Transaction timeout:** có thể được manager/resource thực thi, nhưng timeout chờ kết quả ở phía caller không nhất thiết chấm dứt tác vụ.

Khi advice sở hữu transaction mới, cần giải phóng tài nguyên sau commit/rollback. Nếu chỉ tham gia transaction đang có, advice phải tránh đóng context/connection thuộc sở hữu của outer. Việc khôi phục sai context có thể nguy hiểm hơn bản thân exception ban đầu.

## 14. Kiểm thử đúng hơn việc chỉ nhìn log

Đối với transaction aspect, một vài bài kiểm thử có giá trị hơn việc kiểm tra “log begin đã in”:

| Kiểm thử | Điều cần chứng minh |
| --- | --- |
| Thành công | Mọi thay đổi thuộc transaction commit đúng một lần |
| Exception đồng bộ ở giữa công việc | Không có partial commit; nguyên nhân lỗi không bị mất |
| Exception bị bắt và trả mã lỗi | Kết quả commit/rollback đúng với policy cho lỗi dạng giá trị |
| Method con tham gia transaction | Method con không tự kết thúc transaction thuộc outer |
| Self-invocation qua proxy | Hành vi phù hợp với giới hạn interception thực của nền tảng |
| Commit hoặc rollback bị lỗi | Outcome và lỗi phụ được phản ánh chính xác; cleanup vẫn chạy nếu có thể |
| Concurrent calls | Isolation/ownership và việc tách context hoạt động đúng theo khả năng resource |
| Chạy từ executor/async callback | Transaction áp vào điểm thực thi thật, không bị kết thúc quá sớm |
| Retry + transaction | Mỗi attempt nhận transaction đúng policy, không giữ transaction đã rollback-only |
| Tài nguyên ngoài transaction | Side effect không được quảng bá sai là có rollback nguyên tử |

**Kiểm tra dữ liệu sau rollback** phải đi qua tài nguyên thật nếu mục tiêu là kiểm chứng transaction production. Mock advice hoặc log cho thấy callback `rollback()` được gọi chưa đủ để chứng minh database không có partial write. Kiểm tra thêm thời gian giữ lock/connection, timeout và mối quan hệ với pool khi chạy tải thực tế.

## 15. Những lỗi thiết kế thường gặp

| Sai lầm | Vì sao không đúng | Cách điều chỉnh |
| --- | --- | --- |
| Nghĩ annotation/pointcut tự tạo transaction | Metadata không có tác dụng nếu không có interceptor/manager/resource | Xác minh toàn chuỗi hỗ trợ thực tế |
| Commit trong method con đang tham gia outer | Phá ownership và tính nguyên tử use-case | Commit ở phạm vi sở hữu transaction |
| Mở transaction ở lời gọi không đi qua proxy | Advice không chạy tại điểm đó | Chọn boundary đi qua proxy hoặc cơ chế weaving được hỗ trợ |
| Bọc transaction quá rộng quanh I/O dài | Giữ lock/connection lâu, tăng contention | Thu hẹp phần cần nhất quán, dùng phối hợp nhiều bước nếu cần |
| Dùng rollback để “thu hồi” email/HTTP | Side effect ở ngoài resource không tham gia | Outbox/compensation/idempotency |
| Commit ngay khi async method trả stage | Worker có thể chưa chạy hoặc chạy ở luồng khác | Đặt transaction quanh phần thực thi thật hoặc dùng manager async phù hợp |
| Giả định mọi exception đều rollback | Chính sách rollback khác nhau tùy cấu hình | Xác định rõ checked/unchecked, rollback-only, failure dạng giá trị |
| Nuốt exception trong advice | Caller nhận thành công giả; transaction có thể đã sai | Truyền nguyên nhân gốc, giữ lỗi phụ |
| Tạo transaction mới cho mọi method lồng nhau | Chia vụn một đơn vị nghiệp vụ thành nhiều commit | Chọn propagation/ownership rõ ràng |
| Retry trong transaction không thể dùng lại | Context rollback-only hoặc resource đã lỗi | Sắp xếp retry và transaction phù hợp |
| Tin rằng `readOnly` luôn cấm ghi | Nhiều resource chỉ coi đây là hint | Kiểm tra enforcement ở resource |
| Chỉ test advice được gọi | Không chứng minh dữ liệu đã rollback | Test trạng thái resource thật và failure modes |

## 16. Checklist triển khai

Trước khi đặt transaction bằng advice, hãy trả lời:

1. **Đơn vị nghiệp vụ nào cần nguyên tử?** Có phù hợp dùng một transaction local không?
2. **Join point có thật sự được intercept?** Qua interface proxy, subclass proxy hay weaving? Các lời gọi nội bộ có bị bỏ qua không?
3. **Ai cung cấp transaction manager và resource?** Có begin/commit/rollback thật không?
4. **Phương thức nào sở hữu transaction?** Khi lồng nhau, propagation, rollback-only và savepoint xử lý thế nào?
5. **Khi nào transaction kết thúc?** Sau return đồng bộ, hay sau một tín hiệu completion với coordinator hỗ trợ async thực sự?
6. **Rollback policy gồm những outcome nào?** Checked/unchecked exception, result báo lỗi, cancel, timeout?
7. **Có side effect ngoài transaction không?** Nếu có, cần outbox, compensation hay cơ chế khác?
8. **Có aspect khác chen vào không?** Thứ tự retry, cache, validation, audit và tracing ảnh hưởng commit ra sao?
9. **Context có an toàn qua thread và request không?** Resource có được đóng và context được khôi phục ở mọi đường đi không?
10. **Bằng chứng kiểm thử là gì?** Có kiểm tra rollback thực tế, concurrent isolation, commit failure và async path không?

## 17. Kết luận kỹ thuật

**Around advice** là công cụ tự nhiên để áp chính sách transaction quanh một lời gọi, nhưng tính đúng đắn nằm ở sự ăn khớp giữa **ranh giới nghiệp vụ**, **join point được nền tảng AOP hỗ trợ**, **transaction manager sở hữu scope**, **resource thật sự tham gia** và **thời điểm công việc hoàn tất**. Advice có thể điều phối begin/commit/rollback, không thể tự tạo atomicity vượt qua khả năng của nền tảng hoặc biến một lời gọi bất đồng bộ đã return thành công việc đã commit.

Thiết kế tốt phải làm rõ ownership, propagation, rollback policy, error handling, ordering với các aspect khác và giới hạn liên luồng/liên hệ thống. Chỉ sau khi những điều kiện đó được thỏa mãn mới có thể coi ranh giới transaction đặt bằng advice là có hiệu lực đúng theo hợp đồng.