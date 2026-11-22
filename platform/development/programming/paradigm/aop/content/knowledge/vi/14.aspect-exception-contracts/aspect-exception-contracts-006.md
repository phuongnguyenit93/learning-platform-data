# Tác dụng phụ và tính nguyên tử của thao tác

## 1. Mục tiêu: một lời gọi thất bại không có nghĩa mọi thay đổi được hoàn tác

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP)**, **pointcut** chọn những *join point* thuộc mô hình mà công cụ hỗ trợ, còn **advice** bổ sung hành vi như audit, logging, đo lường, kiểm quyền, retry hoặc caching. Một aspect có thể ảnh hưởng không chỉ kết quả trả về, mà còn **các tác dụng phụ** trước, trong và sau lần thực thi target.

Ví dụ:

~~~text
Caller -> AuditBefore -> Target
           |              |
        ghi sự kiện     tăng số dư
                          |
                          +-> ném ngoại lệ
                  |
Caller nhận ngoại lệ, nhưng audit và số dư đã thay đổi
~~~

**Java exception không tự rollback state.** Một `catch` nhìn thấy lỗi không chứng minh rằng nghiệp vụ chưa thực hiện thao tác ghi. Một `after-returning` chạy cũng không chứng minh mọi thay đổi đã commit bền vững, bởi giao dịch có thể nằm ở lớp bao ngoài hoặc tác vụ bất đồng bộ còn tiếp tục sau khi method return.

Bài này tập trung vào ba câu hỏi:

1. **Tác dụng phụ nào đã xảy ra?** DB update, cache, file, network request, event delivery, metrics, field mutable?
2. **Ai có trách nhiệm đảm bảo tính nguyên tử?** Advice, tài nguyên giao dịch, domain service hay workflow phối hợp nhiều hệ thống?
3. **Caller thực sự được hứa điều gì?** Trả result, ném exception, trạng thái sau lỗi, khả năng retry, idempotency và quyền quan sát?

Không có một “atomicity mặc định của AOP”. Around advice có thể đặt ranh giới transaction hoặc điều phối bù trừ, nhưng phải có **cơ chế tài nguyên thực sự** để đảm bảo thuộc tính được tuyên bố.

## 2. Các thuật ngữ cốt lõi

| Thuật ngữ | Diễn giải |
| --- | --- |
| **Side effect** | Thay đổi quan sát được ngoài giá trị trả về thuần của hàm |
| **Join point** | Vị trí/sự kiện chương trình mà mô hình AOP cho phép can thiệp |
| **Advice** | Hành vi trước, sau, khi lỗi hoặc bao quanh một điểm được chọn |
| **Proceed** | Thao tác chuyển tiếp từ around advice sang lớp bên trong/target, theo API của engine |
| **Atomicity** | Một tập thay đổi nằm trong ranh giới được áp dụng như một đơn vị theo bảo đảm đã xác định |
| **Commit** | Thời điểm cơ chế lưu trữ/giao dịch xác nhận trạng thái đã được ghi nhận |
| **Rollback** | Hủy thay đổi chưa được commit trong phạm vi giao dịch hỗ trợ |
| **Compensation** | Một thao tác nghiệp vụ mới bù lại tác dụng đã xảy ra |
| **Idempotency** | Lặp lại cùng logical request không nhân đôi hiệu quả đã được định nghĩa |
| **Unknown outcome** | Caller chưa xác định được commit đã xảy ra hay chưa |
| **Transactional outbox** | Ghi ý định phát event cùng transaction với thay đổi dữ liệu tại một DB |
| **Audit event** | Sự kiện quan sát có nghĩa cụ thể như attempted, committed, delivered |
| **Exception safety** | Mức bảo toàn trạng thái/invariant khi thao tác ném lỗi |

**Tác dụng phụ không nhất thiết có hại**: ghi audit, cập nhật giao dịch và gửi thông báo là nhu cầu thật. Rủi ro đến từ việc gắn sai **thời điểm và phạm vi** cho một hiệu quả, rồi diễn giải `return/throw` thành lời bảo đảm không tồn tại.

### 2.1. Các loại tác dụng phụ điển hình

- **Trong heap:** tăng counter, sửa field, thêm vào collection, cập nhật static cache.
- **Tài nguyên local:** ghi file, đóng/mở socket, khóa, thread, subscription.
- **Lưu trữ nghiệp vụ:** insert/update/delete bản ghi, đổi số dư, đặt trạng thái đơn.
- **Hệ thống khác:** HTTP call, gửi email/SMS, cổng thanh toán, message broker.
- **Quan sát:** ghi log, audit, metrics, trace, phát thông báo.
- **Điều khiển luồng:** retry khiến mục tiêu chạy nhiều lần, cache không gọi target, fallback biến lỗi thành return thành công.

Tác dụng phụ cuối cùng cũng có thể được tạo bởi chính **advice**, không chỉ target.

## 3. Atomicity không giống isolation, durability hay idempotency

Không được gọi tất cả các phẩm chất sau bằng từ “nguyên tử”:

| Thuộc tính | Hợp đồng | Không chứng minh |
| --- | --- | --- |
| **Atomicity** | Các thay đổi trong phạm vi commit cùng nhau hoặc không thay đổi theo contract | Không tự bao các resource bên ngoài phạm vi |
| **Consistency** | Invariant miền vẫn hợp lệ | Không thay thế validation đúng |
| **Isolation** | Các thao tác đồng thời không tạo quan sát trái mức cô lập đã hứa | Atomic commit chưa chắc serializable |
| **Durability** | Thay đổi đã commit tồn tại qua những sự cố được bảo đảm | State RAM và Java lock không tự bền vững |
| **Idempotency** | Lặp logical request không nhân đôi kết quả được định nghĩa | Không có nghĩa operation thực thi vật lý đúng một lần |
| **Compensation** | Thêm một nghiệp vụ bù trạng thái | Không tương đương undo atomically/invisibly |

Một `synchronized` method giúp nhiều thread vào cùng object theo một thứ tự có kiểm soát, nhưng **không tạo transaction database, không rollback ghi trước đó khi throw và không bảo vệ nhiều node**.

Nếu nói “cập nhật số dư và audit là atomic”, phải hỏi **chúng nằm cùng database transaction nào, cùng object snapshot nào, hay chỉ cùng một Java call stack?** Chỉ trường hợp có cơ chế liên kết thực sự mới có bảo đảm.

## 4. Ngoại lệ qua advice không tự undo tác dụng phụ

Một chuỗi minh họa:

~~~text
Caller
  |
  +-> BEFORE: ghi "attempted"
       |
       +-> AROUND: mở scope
             |
             +-> TARGET: mutate state
                   |
                   +-> throw error
             |
             +-> AFTER_THROWING: ghi failure
       |
  +-> FINALLY: close scope
Caller <- exception
~~~

Trong chuỗi này có thể tồn tại ít nhất **ba tác dụng phụ**: audit attempted, mutation của target và event failure. Nếu target ném lỗi, chúng **không tự biến mất**.

**After-throwing** có thể biết exceptional completion ở một ranh giới, nhưng không có cơ chế thần kỳ để đảo ngược DB write, external HTTP call hay email đã gửi.

**Finally** thường phù hợp để giải phóng lock, restore ThreadLocal hoặc đóng resource. Nó cũng **không tự là rollback**. Nếu `close()` tự ném lỗi, caller có thể thấy lỗi cleanup thay vì nguyên nhân từ nghiệp vụ.

### 4.1. Before advice gây tác dụng phụ

Nếu `before` ghi `ORDER_SUCCESS` trước khi mục tiêu chạy, event không phản ánh sự thật khi target throw. Nếu nó ghi `ORDER_ATTEMPTED`, ý nghĩa có thể đúng. **Tên và phase của event phải phản ánh thời điểm xảy ra**, không suy diễn từ dự đoán outcome.

### 4.2. After-returning chưa chắc là sau commit

Một target return result bình thường nhưng outer transaction wrapper chưa commit. Nếu after-returning advice ghi `BUSINESS_COMMITTED` trước outer commit, event có thể bị sai nếu commit thất bại.

Ngược lại, một advice nằm **ngoài** transaction wrapper có thể chạy sau commit; nếu nó gửi external audit và lỗi, caller nhìn thấy exception **sau khi nghiệp vụ đã commit**.

### 4.3. After-throwing chưa chắc luôn được vào

Inner around advice có thể catch target exception và return fallback, khiến outer advice thấy normal return. Do đó một outer after-throwing không nhất thiết chạy dù target đã thất bại; điều này phụ thuộc **ranh giới quan sát**.

### 4.4. Return trong finally rất nguy hiểm

~~~java
try {
    throw new IllegalStateException("business failed");
} finally {
    // Không trả result ở đây: return sẽ che lỗi trước đó.
}
~~~

Đây là fragment minh họa chưa phải chương trình độc lập. Nếu `finally` có `return` hoặc ném exception mới, kết quả caller nhận có thể khác hẳn lỗi gốc.

## 5. Các mức bảo đảm an toàn khi ném ngoại lệ

Có thể mô tả bốn mức:

1. **No guarantee:** khi lỗi, state có thể không hợp lệ hoặc không biết đã xảy ra những gì.
2. **Basic guarantee:** invariant tối thiểu và ownership còn hợp lệ; state có thể thay đổi.
3. **Strong guarantee:** trong phạm vi xác định, thao tác lỗi không để lại thay đổi quan sát; tương tự một “commit hoặc không gì cả” ở phạm vi ấy.
4. **No-throw guarantee:** thao tác không để exception thoát ra theo hợp đồng của nó.

Không tự gán bất cứ mức nào cho một AOP engine. Mỗi advice phải được thiết kế:

- Một metrics observer có thể đặt mục tiêu **không ảnh hưởng kết quả nghiệp vụ** khi sink metrics lỗi.
- Một authorization advice có thể chọn **fail-closed** khi không xác thực được.
- Một transaction advice có thể cung cấp rollback cho tài nguyên được **enlist** đúng, không cho tất cả side effects ngoài transaction.
- Một around retry có thể làm target chạy nhiều lần: strong guarantee cho mỗi attempt **không tự đủ** nếu retry lặp external side effects.

Một invariant cơ bản cho advice chỉ quan sát là: **caller result/exception và business execution count vẫn theo hợp đồng**, trừ những side effects quan sát có chủ đích.

## 6. Nhìn theo vị trí phát sinh lỗi

| Vị trí lỗi | Target có thể đã chạy? | Side effects có thể tồn tại? |
| --- | --- | --- |
| Trước `proceed` | Chưa, nếu around chưa chuyển tiếp | Có thể từ before advice |
| Trong target trước mutation | Có | Có thể từ outer advice |
| Trong target sau mutation | Có | Rất có thể cả business mutation |
| Inner around ném sau target return | Đã có thể chạy thành công | Có thể target đã commit |
| Outer audit sink ném sau commit | Có thể đã commit | Business effect và audit intent có thể tồn tại |
| `finally` close ném | Tùy đường trước đó | Cleanup exception có thể che outcome |
| Network timeout khi commit | Không chắc caller biết | Có thể đã commit hoặc chưa |
| Future completes exceptionally sau method return | Method đã return | Async side effects có thể đã xảy ra một phần |

Không thể viết logic `catch (Exception e) { retry(); }` an toàn nếu không phân loại **lỗi và thời điểm commit**.

## 7. Around advice và `proceed()` thay đổi số lần tác dụng phụ

Một around advice có thể:

- Gọi `proceed` **một lần**: thông thường target chạy một lần nếu không có wrapper bên trong điều khiển thêm.
- **Không gọi**: cache hit, authorization deny hoặc circuit breaker short-circuit, target có thể không chạy.
- Gọi **nhiều lần**: retry/fan-out hoặc bug có thể làm side effects lặp.
- Catch rồi return fallback: caller có vẻ thành công dù target trước đó có thể đã sửa state rồi throw.
- Transform exception/result: thay hợp đồng mà caller quan sát.

Ví dụ:

~~~text
RETRY around
  attempt #1 -> TARGET commits -> response timeout
  attempt #2 -> TARGET commits again?
~~~

Nếu operation không idempotent, số lần gọi `proceed` có thể gây trùng thanh toán hoặc trùng bản ghi. Retry không phải một thao tác “chỉ thêm log”; nó thay luồng chạy và cần kiểm tra idempotency.

### 7.1. Transaction wrapper giả định

~~~text
beginTransaction
try:
    result = proceed
    commitTransaction
    return result
catch originalError:
    rollbackTransactionIfPossible
    rethrow originalError
finally:
    releaseResources
~~~

Đây là **pseudocode**, không phải API hoặc recipe đúng cho mọi bộ máy giao dịch. Cần xét những trường hợp:

- Target có dùng **cùng connection/transaction** hay không.
- Commit thất bại làm state unknown.
- Rollback cũng có thể thất bại.
- Nested transactions hoặc savepoints có semantic nào.
- Side effects ngoài transaction đã xảy ra chưa.
- Advice order khiến audit trong hay ngoài transaction.

Chỉ vì mã trông như `begin/proceed/commit` không có nghĩa atomicity đã tồn tại.

## 8. Ví dụ Java 17: khẳng định lỗi không tự rollback

Ví dụ bên dưới là chương trình **chạy độc lập bằng Java 17** không cần thư viện ngoài và **không mô phỏng rằng nó đã weave bytecode**. Nó kiểm thử ba cấp độ khác nhau:

1. **Unsafe mutation:** state thay đổi rồi target ném exception; caller thấy lỗi nhưng tác dụng phụ còn.
2. **In-memory snapshot publication:** chuẩn bị state mới rồi công bố cùng lúc `balance`, `idempotency keys` và `audit events` của một object dưới lock; lỗi trước publication không thay state.
3. **External side effect ngoài commit:** external audit sink lỗi sau khi Ledger đã cập nhật nội bộ; caller nhận lỗi nhưng dữ liệu nghiệp vụ vẫn ở trạng thái đã commit **trong RAM**.

**Ranh giới chính xác:** snapshot trên heap và `synchronized` minh họa atomic publication với những người quan sát qua object Ledger; không bảo đảm **durability sau khi process crash**, không bảo đảm **distributed atomicity** với remote sink và không phải database transaction.

Tạo file `AdviceAtomicityDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class AdviceAtomicityDemo {
    static void equal(Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
    }

    static final class UnsafeState {
        int balance;
        final List<String> audit = new ArrayList<>();

        void runThenFail() {
            audit.add("AUDIT begin U-1");
            balance += 10;
            throw new IllegalStateException("target failed");
        }
    }

    record Snapshot(int balance, Map<String, Integer> applied,
                    List<String> events) {}

    static final class Ledger {
        private Snapshot state = new Snapshot(0, Map.of(), List.of());

        synchronized String submit(String id, int amount, boolean failBeforeCommit) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            Integer previous = state.applied().get(id);
            if (previous != null) {
                if (previous != amount) {
                    throw new IllegalArgumentException("idempotency key conflict");
                }
                return "duplicate:" + id;
            }
            if (failBeforeCommit) {
                throw new IllegalStateException("planned failure");
            }
            Map<String, Integer> applied = new HashMap<>(state.applied());
            applied.put(id, amount);
            List<String> events = new ArrayList<>(state.events());
            events.add("AUDIT committed " + id);
            state = new Snapshot(state.balance() + amount,
                    Map.copyOf(applied), List.copyOf(events));
            return "accepted:" + id;
        }

        synchronized Snapshot view() {
            return state;
        }
    }

    static void sendToExternalAudit(String id) {
        throw new IllegalStateException("external sink unavailable for " + id);
    }

    public static void main(String[] args) {
        UnsafeState unsafe = new UnsafeState();
        try {
            unsafe.runThenFail();
            throw new AssertionError("expected failure");
        } catch (IllegalStateException error) {
            equal("target failed", error.getMessage());
        }
        equal(10, unsafe.balance);
        equal(List.of("AUDIT begin U-1"), unsafe.audit);
        System.out.println("UNSAFE balance=10 audit=1 after exception");

        Ledger ledger = new Ledger();
        try {
            ledger.submit("A-1", 10, true);
            throw new AssertionError("expected failure");
        } catch (IllegalStateException error) {
            equal("planned failure", error.getMessage());
        }
        equal(0, ledger.view().balance());
        equal(0, ledger.view().events().size());
        System.out.println("PRECOMMIT failure balance=0 audit=0");

        equal("accepted:A-1", ledger.submit("A-1", 10, false));
        equal(10, ledger.view().balance());
        equal(List.of("AUDIT committed A-1"), ledger.view().events());
        System.out.println("COMMIT accepted:A-1 balance=10 audit=1");

        equal("duplicate:A-1", ledger.submit("A-1", 10, false));
        equal(10, ledger.view().balance());
        equal(1, ledger.view().events().size());
        System.out.println("RETRY duplicate:A-1 balance=10 audit=1");

        try {
            ledger.submit("A-1", 11, false);
            throw new AssertionError("expected conflict");
        } catch (IllegalArgumentException error) {
            equal("idempotency key conflict", error.getMessage());
        }
        System.out.println("CONFLICT rejected balance=10 audit=1");

        try {
            equal("accepted:B-2", ledger.submit("B-2", 5, false));
            sendToExternalAudit("B-2");
        } catch (IllegalStateException error) {
            equal("external sink unavailable for B-2", error.getMessage());
            System.out.println("EXTERNAL ERROR " + error.getMessage());
        }
        equal(15, ledger.view().balance());
        equal(2, ledger.view().events().size());
        System.out.println("AFTER EXTERNAL failure balance=15 internalAudit=2");
        equal("duplicate:B-2", ledger.submit("B-2", 5, false));
        equal(15, ledger.view().balance());
        System.out.println("RETRY duplicate:B-2 balance=15 internalAudit=2");
        System.out.println("ALL ASSERTIONS PASSED");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 AdviceAtomicityDemo.java
java AdviceAtomicityDemo
~~~

Đầu ra **đã kiểm chứng bằng biên dịch và chạy thực**:

~~~text
UNSAFE balance=10 audit=1 after exception
PRECOMMIT failure balance=0 audit=0
COMMIT accepted:A-1 balance=10 audit=1
RETRY duplicate:A-1 balance=10 audit=1
CONFLICT rejected balance=10 audit=1
EXTERNAL ERROR external sink unavailable for B-2
AFTER EXTERNAL failure balance=15 internalAudit=2
RETRY duplicate:B-2 balance=15 internalAudit=2
ALL ASSERTIONS PASSED
~~~

### 8.1. Nhánh unsafe: exception nhưng state đã đổi

`UnsafeState.runThenFail()` ghi audit và tăng balance trước khi ném `IllegalStateException`. Caller bắt đúng lỗi nhưng balance vẫn là `10`. Đây là bằng chứng thực tế rằng **throw không tự rollback**.

### 8.2. Lỗi trước commit giả lập

`Ledger.submit("A-1",10,true)` kiểm validation, sau đó ném `planned failure` **trước khi xây và công bố snapshot mới**. Vì thế `balance=0` và audit events trống.

Đây là một bảo đảm strong ở **phạm vi state của Ledger** cho kịch bản đã xét. Nếu code đã gọi network hoặc sửa một resource khác trước thời điểm đó, snapshot commit không đảo ngược chúng.

### 8.3. Công bố `balance` và audit trong một snapshot

`Ledger.submit` tạo hai copies `Map` và `List`, rồi đặt chúng cùng `balance` vào một `Snapshot`. Sự gán `state = new Snapshot(...)` xảy ra **một lần dưới synchronized monitor**; `view()` cũng dùng cùng monitor.

Bởi vậy caller đọc qua `Ledger.view()` sẽ thấy toàn bộ snapshot trước hoặc sau, chứ không thấy một balance mới kết hợp với danh sách audit cũ của cùng object. Điều này minh họa **atomic publication in-memory**, không phải disk durability hay DB ACID transaction.

### 8.4. Idempotency đơn giản

Khi `A-1` được gửi lần hai với amount bằng `10`, Ledger trả `duplicate:A-1`, không tăng balance và không thêm audit. Với cùng key `A-1` nhưng amount `11`, Ledger trả lỗi `idempotency key conflict`.

Trong hệ thống thật, key phải được gắn với **logical operation, tenant/actor scope, request fingerprint và vòng đời lưu key**. Một map in-memory của một process không đủ cho restart hay nhiều node.

### 8.5. External audit failure sau commit

`Ledger.submit("B-2",5,false)` đã cập nhật state nội bộ; tiếp đó `sendToExternalAudit` cố tình ném `IllegalStateException`. Caller thấy lỗi external sink **sau khi balance là 15**.

Retry `B-2` với cùng key không cộng balance nữa, nhưng external event vẫn chưa được gửi thành công. Muốn tin cậy phải có cơ chế xử lý delivery độc lập như **durable outbox + publisher + consumer idempotency**, không chỉ bảo vệ phần nghiệp vụ.

### 8.6. Giới hạn ví dụ cần nhớ

- Dữ liệu trong RAM **mất khi process chết**; `Snapshot` không thay thế database.
- `synchronized` chỉ bảo vệ các lời gọi qua cùng object và monitor; không bao external sink.
- `Map.copyOf`/`List.copyOf` tạo collection không cho sửa trực tiếp ở đây; kiểu `record` không bảo đảm mọi object graph luôn deep immutable.
- Số dư kiểu `int` chỉ phục vụ minh họa; production cần domain money type, kiểm overflow và định dạng chính xác.
- Test dùng một luồng, không kiểm throughput hay race đa node.
- Hàm remote sink trong demo cố tình luôn lỗi để cho thấy post-commit failure; không phải client thật.

## 9. Tại sao bố trí advice liên quan transaction lại khó?

So hai thứ tự:

~~~text
A: TRANSACTION( AUDIT( TARGET ) )
B: AUDIT( TRANSACTION( TARGET ) )
~~~

Trong A, audit nằm **bên trong wrapper transaction về mặt call stack**, nhưng chỉ thực sự tham gia transaction nếu nó dùng cùng resource/session/connection hoặc cơ chế enlistment được hỗ trợ. Trong B, audit bao ngoài transaction; code after của audit có thể chạy sau khi inner transaction đã commit.

Do đó **nested precedence** rất quan trọng nhưng chưa đủ. Cần trả lời:

- Transaction thật được mở ở đâu?
- Commit thực xảy ra ở đâu?
- Audit ghi vào cùng cơ sở dữ liệu hay gửi HTTP khác?
- Nếu audit ở trong transaction wrapper, có dùng đúng transaction context không?
- Nếu audit gửi message trước commit, consumer có nhận một sự kiện chưa commit?
- Nếu audit chạy sau commit và lỗi, caller nhận outcome gì?
- Nếu retry bao ngoài transaction, có tạo mỗi attempt một transaction riêng không?
- Nếu transaction bao ngoài retry, các attempts có share một transaction bị đánh dấu rollback-only không?

Đừng áp một sơ đồ duy nhất cho mọi backend. Engine AOP chỉ quyết định đường can thiệp; semantics transaction nằm ở tài nguyên thực.

### 9.1. Một vòng lifecycle ý niệm

~~~text
begin unit of work
  validate
  mutate business rows
  insert audit/outbox row in same transaction
commit
  |
  +-> publisher gửi event sau commit
~~~

Đây là **mẫu kiến trúc**, không phải câu lệnh của một công nghệ cụ thể. Nếu business rows và outbox row cùng một transaction thực, chúng có thể commit/rollback cùng nhau theo bảo đảm của DB. Nhưng delivery tới broker/email **không nằm trong transaction DB** nếu không có cơ chế phối hợp riêng.

## 10. Transactional outbox giải quyết điều gì?

**Dual-write problem** xảy ra khi một operation phải vừa cập nhật database vừa phát event sang một hệ thống khác:

~~~text
write DB
publish message
~~~

Nếu DB commit rồi publish lỗi, DB đã đổi nhưng message thiếu. Nếu publish trước commit, consumer có thể thấy event của dữ liệu cuối cùng rollback. Chỉ dùng `try/catch` không loại bỏ được cả hai rủi ro.

Một phương án là:

~~~text
BEGIN DB TRANSACTION
   update business data
   insert outbox(eventId, payload, status)
COMMIT

INDEPENDENT PUBLISHER:
   read committed outbox
   publish event
   record/ack delivery progress
~~~

Điểm mạnh: **business data và ý định publish được commit cùng một DB transaction**, nếu thật sự cùng phạm vi. Nhưng:

- Publisher có thể crash sau khi gửi nhưng trước khi ghi ACK; sẽ **gửi lại**.
- Consumer cần xử lý idempotent theo event ID hoặc business key thích hợp.
- Event đã lưu ở outbox chưa có nghĩa remote effect đã diễn ra.
- Cần theo dõi backlog, retry policy, dead letters, ordering và poison messages.
- Không tự tuyên bố exactly-once end-to-end chỉ vì có outbox.
- Giao dịch có thể có **unknown commit outcome**, cần kiểm chứng qua key/state trước khi retry.
- Một notification đã gửi khó “hoàn tác” chỉ bằng rollback DB.

Nếu một audit là điều kiện bắt buộc của commit, việc ghi **audit intent** cùng transaction là lựa chọn cần cân nhắc. Việc gửi external audit thực có thể là **eventual delivery**, với độ trễ và đường khôi phục được thiết kế.

## 11. Compensation khác rollback

Rollback thông thường đảo/hủy **các thay đổi chưa được commit trong cùng transaction hỗ trợ**. **Compensation** là một hành động nghiệp vụ mới nhằm bù hậu quả **đã xảy ra**.

Ví dụ:

~~~text
reserve inventory  -> thành công
charge account     -> thất bại
release inventory  -> compensation
~~~

Trong khoảng giữa hai việc, hàng hóa có thể đã được giữ chỗ. `release inventory` có thể lỗi, cần retry hoặc đối soát. Nó không phải “quay về quá khứ”: audit/log và tác động lên bên ngoài có thể đã xảy ra.

Một `after-throwing` advice có thể kích hoạt compensation, nhưng phải quản lý:

- Biết bước nào đã commit thành công.
- Idempotency của action và compensation.
- Số lần retry/bộ đếm/timeout.
- Trạng thái `PENDING_COMPENSATION` hoặc `MANUAL_REVIEW` khi bù thất bại.
- Giữ lại causal chain của exception gốc và lỗi bù.
- Không tuyên bố toàn workflow đã atomic chỉ vì gọi một hàm `undo`.

Đặc biệt với thanh toán, “refund” có thể là giao dịch mới với thời gian xử lý và phí, không tương đương giao dịch chưa từng xảy ra.

## 12. Retry và lỗi “không biết đã commit hay chưa”

Một request remote có thể commit nhưng client nhận timeout **trước khi ACK về**:

~~~text
Client          Remote service
   |  request       |
   |--------------->|
   |             COMMIT
   |                 |
   |      response lost
   |<--- timeout -----|
~~~

Nếu around advice retry mù, remote service có thể thực hiện **hai lần** cùng một logical operation.

Các chiến lược:

1. Tạo **idempotency key** nhất quán trước mọi attempt của cùng logical operation.
2. Tại nơi commit, lưu key và outcome cùng transaction đủ mạnh, dùng uniqueness/concurrency control.
3. Nếu ACK mất, truy vấn trạng thái/outcome theo key hoặc retry idempotently.
4. Phân biệt cùng key **cùng payload** với cùng key **khác payload**.
5. Không retry validation/authorization failure như transient server error.
6. Giới hạn attempts, backoff và deadline.
7. Đối với external audit delivery, retry delivery **độc lập với business operation** khi phù hợp.

### 12.1. Cần xác định key scope

Ví dụ một key đơn giản `request-123` có thể va chạm giữa hai tenants nếu không namespace phù hợp. Trong production, nên xét `tenant`, `actor/authority`, `operationType`, fingerprint/payload hash, trạng thái pending/committed và thời hạn giữ key.

Với hai requests đồng thời mang cùng key, chỉ kiểm key trong một `HashMap` trên từng JVM là chưa đủ nếu ứng dụng chạy nhiều nodes. Có thể cần database unique constraint, compare-and-set hoặc cơ chế phối hợp có hợp đồng cụ thể.

### 12.2. Không đánh đồng retry với double weaving

Một lời around advice có thể được vào một lần nhưng gọi `proceed` nhiều lần; target chạy nhiều attempts. Đây không nhất thiết là double instrumentation. Dùng các counters độc lập: `logicalRequests`, `attempts`, `businessExecutions`, `businessCommits`, `adviceEntries`.

## 13. Short-circuit, cache và side effects

Một cache advice có thể return mà **không gọi `proceed`**. Do đó target không chạy trên đường ấy, nhưng advice ngoài cache vẫn có thể ghi audit/metrics.

Cần định nghĩa event:

| Tên sự kiện | Ý nghĩa đúng |
| --- | --- |
| `REQUEST_ATTEMPTED` | Caller thử thực hiện thao tác |
| `REQUEST_DENIED` | Policy từ chối |
| `CACHE_HIT` | Phục vụ dữ liệu từ cache, không nhất thiết chạy target |
| `TARGET_RETURNED` | Method target hoàn tất bình thường |
| `BUSINESS_COMMITTED` | Hiệu quả nghiệp vụ đã commit ở ranh giới xác định |
| `DELIVERY_ENQUEUED` | Ý định gửi đã lưu, chưa hứa remote nhận |
| `DELIVERY_CONFIRMED` | Đã có ACK theo hợp đồng bên nhận, chưa tự đủ để chứng minh exactly-once side effects |

Nếu audit cần ghi **mỗi API request**, nên đặt sao cho cache hit vẫn được quan sát. Nếu audit cần ghi **mỗi business commit**, đừng ghi lại commit event chỉ vì cache trả kết quả cũ.

Tương tự, authorization cần bao mọi đường truy cập dữ liệu quan trọng: cache hit không được bypass quyền chỉ vì cache nằm ngoài lớp kiểm soát.

## 14. Async: method return không bằng task completion

Một method Java có thể trả một `CompletableFuture` chưa hoàn tất. Advice `after-returning` ở ranh giới method có thể chạy **trước** khi task commit hoặc throw.

~~~java
CompletableFuture<String> future = startAsync();
return future;
~~~

Đoạn này là ví dụ không độc lập vì `startAsync()` chưa được định nghĩa.

Nếu audit cần biết **completion của tác vụ**, phải gắn vào lifecycle của Future/task:

~~~java
future.whenComplete((value, error) -> {
    if (error == null) recordCompletion(value);
    else recordFailure(error);
});
~~~

Hai hàm `recordCompletion` và `recordFailure` là pseudocode chưa được định nghĩa. Cần xem semantics callback, cancellation, exceptional completion, thread switching và lỗi của chính callback.

**Đặc biệt:** task có thể đã phát external side effect rồi caller cancel Future, vì cancellation không phải phép undo mọi network operation. Một advice dùng `finally` khi method return cũng **không** kéo dài transaction tự động đến khi task thật hoàn tất.

## 15. Concurrency và phạm vi isolation

Một `synchronized` quanh thao tác đọc/cập nhật trong **một object** có thể giúp đồng bộ đúng giữa các thread gọi cùng object. Nhưng:

- Nó không đồng bộ các JVM/process khác.
- Nó không tạo tính bền vững qua crash.
- Nó không bảo vệ network calls hoặc database transaction ở tài nguyên khác.
- Một ThreadLocal transaction context **không tự lan truyền qua mọi executor/async callback**.
- Nếu target dùng connection khác không enlist, outer transaction có thể không bao được ghi của target.

Các lỗi concurrency cần test:

- **Lost update** khi read-modify-write trên shared state.
- **Duplicate key race** khi hai request cùng idempotency key tới đồng thời.
- **Cache stampede** khi nhiều threads cùng miss một key và gọi target nhiều lần.
- **Write skew** nếu ràng buộc dữ liệu trải nhiều rows dưới isolation không phù hợp.
- **Deadlock** nếu hai advices khóa resources theo thứ tự ngược.
- **Duplicate event delivery** nếu publisher retry sau khi ACK thất lạc.
- **Context leak** khi ThreadLocal không được restore/remove trong finally.

Không dùng test chỉ với một thread để kết luận hệ thống chịu tải đồng thời an toàn.

## 16. Exception propagation và lỗi advice có thể che lỗi gốc

Nếu target ném `E1`, inner advice catch rồi ném `E2`, outer advice/caller có thể nhìn thấy `E2`. Nếu `E2` là lỗi sink metrics không liên quan, việc thay thế này có thể làm mất tín hiệu rollback/retry quan trọng.

Các nguyên tắc:

1. Advice chỉ quan sát nên ưu tiên **không làm đổi lỗi/result nghiệp vụ** trừ khi policy bắt buộc.
2. Nếu chuyển exception, giữ causal chain khi phù hợp.
3. Nếu cleanup cũng lỗi, đảm bảo hiểu primary/suppressed exception.
4. Không `return` từ `finally` vì có thể che lỗi/result.
5. Không catch mọi `Throwable` rồi im lặng bỏ qua các lỗi nghiêm trọng.
6. Không ghi `BUSINESS_FAILED` chỉ vì metrics sink lỗi sau commit; phải phân biệt **target outcome** và **observation outcome**.
7. Nếu transaction commit lỗi với outcome chưa rõ, ghi trạng thái **unknown/pending reconciliation** thay vì khẳng định rollback.

### 16.1. Fail-open hay fail-closed?

| Concern | Phương án có thể phù hợp | Điều kiện |
| --- | --- | --- |
| Metrics/tracing best-effort | Lỗi sink không phá nghiệp vụ | Cần buffer/drop policy và giám sát |
| Authorization bắt buộc | Lỗi kiểm quyền có thể deny | Không để target chạy khi policy không xác minh được |
| Audit compliance bắt buộc | Ghi audit intent trong transaction hoặc chặn trước mutation | Định nghĩa đúng durability và trạng thái commit |
| Email notification | Queue để gửi sau commit | Chấp nhận eventual delivery và retry |
| Cache | Cache lỗi có thể bỏ cache rồi gọi target | Phải giữ auth/consistency |
| Retry | Chỉ retry những lỗi cho phép | Idempotency và giới hạn attempts |

Không có một lựa chọn chung cho mọi hệ thống. Nếu audit bắt buộc fail-closed mà code chỉ ném lỗi **sau khi target đã commit**, đó không phải “chặn toàn bộ giao dịch”.

## 17. Kiểm thử tích hợp các side effects và tính nguyên tử

Một unit test `AuditAdvice.afterThrowing()` có thể chứng minh hàm ghi đúng log khi được gọi. Nhưng nó chưa chứng minh **đường gọi thật**, thứ tự advice, transaction boundary hay việc caller nhìn thấy gì.

### 17.1. Ma trận tình huống

| Tình huống | Cần kiểm chứng |
| --- | --- |
| Validation error trước mutate | Không có business commit |
| Lỗi sau mutation nhưng trước commit | Rollback/strong guarantee theo contract |
| Success commit | Business state và audit/outbox intent nhất quán |
| Before advice throw | Target không chạy; effects của before được tính |
| After advice throw | Caller outcome và state commit có thể khác |
| Cleanup throw | Primary exception và suppressed errors đúng |
| Retry cùng key/payload | Không nhân đôi committed business effect |
| Retry cùng key nhưng payload khác | Reject conflict |
| Commit outcome unknown | Reconcile/idempotency, không blind retry |
| Cache hit | Target không chạy; audit đúng đơn vị |
| Short-circuit deny | Target không chạy và không có side effect trái quyền |
| Retry nhiều attempts | Counts của target, commit, audit được tách biệt |
| Concurrent same key | Chống duplicate commit theo contract |
| Publisher crash sau publish trước ACK | Consumer idempotent hoặc dedup |
| Async task fails sau method return | Không ghi committed khi chỉ mới trả Future |
| Multi-resource workflow | Compensation/recovery nếu resource không có chung transaction |
| Agent/proxy bypass | Xác minh advice chạy tại join point thực sự |
| Restart/redeploy | Kiểm tra durability và recovery bằng hạ tầng thích hợp |

### 17.2. Fault injection vào đúng thời điểm

Một test mạnh nên cố ý tạo lỗi tại:

~~~text
before any business effect
after first stage, before commit
during commit
after commit, before response ACK
before external publish
after publish, before delivery ACK
during rollback
during compensation
during resource cleanup
~~~

Với mỗi điểm, phải nêu expected **caller outcome, state lưu trữ, audit/outbox, side effects remote, khả năng retry**. Chỉ assert exception type không đủ.

### 17.3. Đếm nhiều tầng

Phân biệt:

- `adviceEntries`: số lần một advice được vào.
- `businessExecutions`: số lần target chạy.
- `businessCommits`: số lần hiệu quả nghiệp vụ được commit.
- `outboxInsertions`: số event intents được lưu.
- `deliveryAttempts`: số lần gửi event.
- `consumerEffects`: số side effects tại consumer.

Một request có thể có hai delivery attempts nhưng một business commit; hoặc hai advice entries nhưng target chỉ thực thi một lần. Không dùng chung một metric `count` không rõ nghĩa.

## 18. Kiểm thử thật qua proxy/weaving

Trong AOP, còn một bước khác trước khi xem transaction correctness: **advice có thật sự được gắn vào đúng join point không?**

- Với **interface proxy**, caller phải giữ proxy. Gọi thẳng target có thể bỏ qua advice.
- Với **subclass proxy**, method `final`/`private` không thể override như method bình thường.
- Với **bytecode weaving**, phải kiểm tra class/pointcut đã được dệt vào artifact thực.
- Với **load-time weaving**, agent/transformer phải chạy đúng lúc, classloader scope phải đúng; không mặc định mọi class đã load đều được instrument.
- Với **nhiều aspect**, precedence quyết định transaction nằm ngoài hay trong audit/retry.

Một test gọi trực tiếp `advice.handle()` rồi thấy PASS **không phải integration test của AOP**. Cần test đường caller thật, cả negative coverage, return/exception và side effect counts.

**Kết nối với ví dụ Java ở mục 8:** chương trình đó minh họa nguyên lý state/commit và retry, **không thực hiện bytecode weaving hoặc dynamic proxy**, nên không thể dùng riêng nó để chứng minh một pointcut hay transaction aspect thực tế đã được áp dụng.

## 19. Quy trình thiết kế thực tế

1. **Liệt kê side effects** của tất cả target và advice: heap, DB, network, audit, cache, message.
2. **Định nghĩa ranh giới atomicity**: những effects nào phải cùng commit/rollback?
3. **Vẽ chain outer→inner**: auth, retry, transaction, cache, audit và business nằm ở đâu?
4. **Xác định commit point thực**: before/after returning xảy ra trước hay sau commit?
5. **Chọn failure policy**: metrics fail-open, auth fail-closed, audit durable hay eventual?
6. **Chọn cơ chế resource**: transaction DB, staged state, outbox, compensation.
7. **Đặt idempotency key** theo logical request; kiểm same key/different payload và concurrency.
8. **Phân biệt attempts và commits**; không tính success chỉ theo normal method return.
9. **Dự trù unknown outcome** khi remote timeout và response lost.
10. **Thiết kế retry riêng cho event delivery** nếu business đã commit.
11. **Xử lý cleanup/finally** mà không che lỗi gốc.
12. **Đối với async**, quản lý completion và context propagation, không chỉ method return.
13. **Viết fault-injection tests** trước/sau commit, publish/ACK, rollback và compensation.
14. **Integration test trên artifact thật**, đúng proxy/weaver, pointcut scope và precedence.
15. **Giám sát vận hành**: outbox backlog, duplicate keys, failed compensation, unknown commits và event delivery lag.

## 20. Những sai lầm phổ biến

1. **“Target throw là tất cả side effects đã được rollback.”** Sai nếu không có mechanism thực.
2. **“Một around advice tự làm mọi thao tác atomic.”** Sai: cần transaction/resource boundary.
3. **“`synchronized` = ACID database transaction.”** Không; lock chỉ có phạm vi JVM/object.
4. **“Audit success trong before advice là đủ.”** Sai nếu target có thể thất bại.
5. **“After-returning là chắc chắn sau commit.”** Không nếu commit ở outer layer.
6. **“After-throwing tự bù được mọi thay đổi.”** Không đối với external side effects đã xảy ra.
7. **“Finally rollback được email đã gửi.”** Không.
8. **“Publish event trong DB transaction sẽ rollback theo DB.”** Không nếu broker không cùng transaction.
9. **“Commit timeout = chắc chắn chưa commit.”** Không; có thể lost ACK.
10. **“Retry mọi exception là an toàn.”** Không: business side effects có thể lặp.
11. **“Dùng cùng key khác payload thì cứ coi duplicate.”** Phải phát hiện conflict.
12. **“Map idempotency trong RAM đủ cho nhiều nodes.”** Không.
13. **“Outbox tự bảo đảm consumer chạy exactly-once.”** Không; cần dedup/idempotency downstream.
14. **“Compensation tương đương undo nguyên tử.”** Không; đó là business effect mới.
15. **“Chỉ test return value là đủ.”** Không; phải test committed state và side effects.
16. **“Advice chạy cùng call stack thì các resource cùng transaction.”** Không.
17. **“Cùng exception đồng nghĩa state chưa đổi.”** Không.
18. **“Cache hit là một lần target commit.”** Không nhất thiết target có chạy.
19. **“Future return bình thường chứng minh task thành công.”** Không.
20. **“Catch mọi Throwable giúp tăng ổn định.”** Có thể che lỗi nghiêm trọng.
21. **“Logging/metrics là hoàn toàn side-effect-free.”** Chúng có I/O, có thể block, throw hoặc lộ dữ liệu.
22. **“Đổi order các aspects chỉ đổi thứ tự log.”** Có thể đổi transaction scope và bảo mật.
23. **“ThreadLocal transaction tự theo mọi async thread.”** Không.
24. **“Một Java lock bảo vệ hệ thống phân tán.”** Không.
25. **“Lỗi audit sau commit nghĩa là business thất bại.”** Không nhất thiết; cần phân biệt outcome.
26. **“Rollback hoặc cleanup không bao giờ throw.”** Thực tế phải test cả lỗi thứ cấp.
27. **“Điểm `after-returning` là điểm ghi BUSINESS_COMMITTED mặc định.”** Chỉ đúng nếu contract thực sự đặt sau commit.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Target thay đổi `balance` rồi throw. Caller catch exception. Balance có tự quay về không?  
**Đáp án:** Không. Phải có rollback/undo/transaction thực sự bao thay đổi ấy.

**Câu 2.** `synchronized` quanh Ledger bảo đảm gì và không bảo đảm gì?  
**Đáp án:** Bảo vệ các truy cập đi qua cùng monitor trong process; không đảm bảo durability, database atomicity hoặc multi-node consistency.

**Câu 3.** Tại sao một external audit failure sau commit nguy hiểm?  
**Đáp án:** Caller có thể nhận exception dù business đã commit rồi retry gây side effects trùng nếu không idempotent.

**Câu 4.** Có thể lưu business row cùng outbox record trong một DB transaction để làm gì?  
**Đáp án:** Để commit cả state nghiệp vụ và ý định publish cùng một ranh giới, không tự bảo đảm delivery downstream exactly-once.

**Câu 5.** Khi publisher đã gửi event nhưng ACK thất lạc, có thể xảy ra gì?  
**Đáp án:** Publisher có thể gửi lại; consumer cần dedup/idempotency phù hợp.

**Câu 6.** Compensation khác rollback ở chỗ nào?  
**Đáp án:** Compensation là nghiệp vụ mới bù hậu quả đã xảy ra, có thể thất bại và cần retry; rollback hủy changes trong phạm vi transaction hỗ trợ.

**Câu 7.** Tại sao `after-returning` chưa chắc là sau business commit?  
**Đáp án:** Vì transaction có thể do wrapper ngoài kiểm soát hoặc công việc async chưa xong.

**Câu 8.** Retry cùng idempotency key nhưng amount khác nên làm gì?  
**Đáp án:** Từ chối conflict theo hợp đồng, không âm thầm coi là cùng request.

**Câu 9.** `finally` tự throw có thể ảnh hưởng caller thế nào?  
**Đáp án:** Có thể che exception/result trước đó, cần chính sách bảo toàn lỗi chính.

**Câu 10.** Trong demo, vì sao `PRECOMMIT failure` không đổi balance nhưng `UNSAFE` lại đổi?  
**Đáp án:** Demo safe chuẩn bị rồi chỉ công bố snapshot sau các điều kiện; unsafe ghi state trước khi throw.

**Câu 11.** Một task trả `CompletableFuture` pending, có nên ghi `BUSINESS_COMMITTED` ngay khi method return không?  
**Đáp án:** Không, cần chứng cứ commit/completion theo contract.

**Câu 12.** Test advice method riêng có chứng minh transaction pointcut thật đã hoạt động không?  
**Đáp án:** Không; cần integration test qua đúng proxy/weaver và resource transaction thật.

## 22. Tổng kết

**Tác dụng phụ và tính nguyên tử là một phần của hợp đồng tổng thể khi AOP can thiệp vào ứng dụng.** Advice có thể ghi audit trước target, retry làm target chạy lại, catch rồi fallback, hoặc ném lỗi sau khi nghiệp vụ đã commit. **Exception không tự xóa tác dụng phụ** và một `around` advice không tự tạo giao dịch nguyên tử.

Thiết kế đáng tin cần xác định **phạm vi atomicity** cụ thể, đặt transaction và advice theo thứ tự phù hợp, sử dụng idempotency cho retry, dùng outbox hoặc cơ chế phối hợp khi gửi event ra ngoài, và compensation/reconciliation khi side effects đã xảy ra ở nhiều tài nguyên độc lập. Cần phân biệt **attempt, method return, business commit và event delivery**, rồi kiểm thử bằng cách cố ý gây lỗi trước/sau commit và kiểm cả caller outcome lẫn state thực tế. Chỉ khi đó các aspect mới bổ sung hành vi cắt ngang mà không làm lệch kết quả và bảo đảm nghiệp vụ ngoài ý định.