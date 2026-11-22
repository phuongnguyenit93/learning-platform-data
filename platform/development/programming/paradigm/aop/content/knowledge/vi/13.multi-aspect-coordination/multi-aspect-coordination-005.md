# Phụ thuộc ngữ nghĩa giữa bảo mật, giao dịch và ghi nhật ký khi phối hợp nhiều aspect

## 1. Vì sao thứ tự aspect làm thay đổi kết quả?

Trong **Aspect-Oriented Programming (AOP)**, một method nghiệp vụ có thể cần đồng thời ba concern xuyên cắt:

- **Security:** xác thực chủ thể, kiểm tra quyền và từ chối thao tác trái phép.
- **Transaction:** tạo ranh giới làm việc với tài nguyên có commit/rollback và tính nhất quán dữ liệu.
- **Logging/Audit:** ghi nhận attempt, quyết định cho phép/từ chối, kết quả, ngoại lệ và sự kiện đã commit.

Một aspect có **pointcut** để chọn những **join point** và **advice** để bổ sung hành vi trước/sau/bao quanh điểm được chọn. Các concern có thể được mô tả độc lập ở mã nguồn nhưng **không độc lập về mặt ngữ nghĩa khi được kết hợp**.

Ba kiểu lồng nhau:

~~~text
Security(Logging(Transaction(Business)))
Logging(Security(Transaction(Business)))
Transaction(Logging(Security(Business)))
~~~

Có thể tạo hành vi khác nhau khi cùng nhận một request không có quyền:

- Security ngoài cùng từ chối trước khi Logging hoặc Transaction chạy, nên có thể **không có log denial** từ Logging nằm bên trong.
- Logging ngoài cùng có thể ghi attempt và denial trong khi Transaction không bắt đầu.
- Transaction ngoài cùng có thể **mở transaction cho một request sẽ bị từ chối**.
- Với request hợp lệ, nếu Logging ở **trong** Transaction, nó có thể ghi success khi Business trả về **trước khi commit thật xảy ra**.

Ngoài ra, nếu Logging catch và che một exception, Transaction ở bên ngoài có thể nhìn thấy normal return thay vì lỗi, từ đó đưa ra quyết định commit khác. Nếu Retry làm quanh Transaction, số transaction có thể nhiều hơn số request. Nếu transaction commit outcome không chắc chắn, log success hay retry cũng phải thận trọng.

**Thông điệp chính:** Thứ tự advice không chỉ ảnh hưởng trace và performance. Nó thay đổi **hợp đồng bảo mật, tính đúng của transaction outcome, ý nghĩa audit, exception propagation và khả năng quan sát**.

Đây là kiến thức AOP cơ bản và nâng cao nói chung; khả năng join point và quy tắc precedence của mỗi ngôn ngữ/bộ dệt khác nhau. Ví dụ Java 17 bên dưới là chương trình runnable mô phỏng **around composition**, không phải một trình biên dịch aspect thực.

## 2. Ôn lại join point, pointcut, advice và precedence

| Khái niệm | Ý nghĩa |
|---|---|
| **Join point** | Điểm thực thi mà ngôn ngữ AOP hỗ trợ nhận diện, ví dụ method call hoặc method execution |
| **Pointcut** | Quy tắc chọn tập join point cần áp dụng concern |
| **Before advice** | Chạy trước điểm, có thể ném lỗi từ chối |
| **After returning** | Quan sát join point được bao hoàn tất bình thường |
| **After throwing** | Quan sát ngoại lệ thoát khỏi join point được bao |
| **After/finally** | Hoạt động ở các đường rời nếu cơ chế hỗ trợ |
| **Around advice** | Bao toàn bộ continuation, có thể gọi hoặc không gọi tiếp |
| **Proceed** | Lệnh/contract chuyển quyền sang bước tiếp theo |
| **Precedence/order** | Xác định aspect nào nằm ngoài và aspect nào nằm trong |

Ký hiệu **A(B(Core))** nghĩa là lời gọi đến A trước, A có thể gọi tiếp B, rồi B gọi Core. Khi Core trả về bình thường, kết quả đi từ trong ra ngoài:

~~~text
Caller
  -> A.before
       -> B.before
            -> Core
       <- B.after
  <- A.after
Caller nhận result
~~~

Một around advice có thể short-circuit không gọi tiếp. Ví dụ Security từ chối ngay khi vào A sẽ khiến **không có hoạt động nào của B và Core**. Vì vậy không thể giả định mọi advice cùng khớp pointcut chắc chắn đều chạy.

Không tự suy thứ tự từ tên aspect, thứ tự khai báo hay thứ tự file. Một ngôn ngữ AOP có thể có precedence rules khác, và thứ tự before/after/around có thể phụ thuộc cách dệt. **Cần thiết lập hoặc xác minh precedence rõ ràng và kiểm tra integration tests.**

### 2.1. Chỉ so sánh cùng một boundary

Trong bài này biểu thức lồng nhau giả định các wrapper cùng bao **một operation**. Nếu Security được weave ở method execution, Logging ở call site và Transaction ở proxy, đó có thể là **các join point khác nhau** với thứ tự do đường thực thi quyết định. Trước khi chọn precedence, phải biết concern nào chặn loại join point nào và caller đi qua những lớp nào.

## 3. Security: bảo mật gồm nhiều nghĩa

**Authentication** xác định danh tính và độ tin cậy của actor. **Authorization** xác định actor có quyền thực hiện operation trên tài nguyên/đối tượng cụ thể hay không.

Một ví dụ đơn giản:

~~~text
actor = admin  -> cho phép
actor = guest  -> từ chối
~~~

Đây chỉ là policy minh họa. Trong hệ thống thực, quyền có thể phụ thuộc scope, tenant, owner, số dư, trạng thái bản ghi, version hoặc policy bên ngoài.

### 3.1. Thứ tự bảo mật và side effect

Một điều kiện an toàn căn bản là **không được thực hiện side effect nghiệp vụ không được phép**. Nếu Security nằm ngoài Business và có thể từ chối trước proceed, Business sẽ không chạy trên đường đó. Nhưng nếu caller có đường trực tiếp tới target mà bypass proxy, Security aspect tại proxy có thể không được kích hoạt.

Độ bao phủ của Security phải được kiểm chứng với direct call, self-invocation, callback và nhiều proxy, không chỉ happy path.

### 3.2. Kiểm tra trước transaction có luôn đúng?

Không luôn. Nếu quyền phụ thuộc vào **dữ liệu mutable**, kiểm tra quyền quá sớm có thể gặp **TOCTOU** (*time-of-check to time-of-use*):

~~~text
T1 kiểm tra record.owner = Alice -> cho phép
T2 sửa record.owner = Bob
T1 bắt đầu transaction và cập nhật record
~~~

Khi ấy quyết định ở T1 có thể đã lạc hậu trước lúc update. Một thiết kế có thể chia thành:

1. **Coarse check** bên ngoài transaction: danh tính, role hoặc scope không phụ thuộc record mutable.
2. **Resource-level authorization** bên trong transaction: kiểm tra owner/version/state trên dữ liệu nhất quán theo isolation/locking/optimistic concurrency hợp lý.
3. **Update có điều kiện** và database constraints bảo vệ invariant cuối.

Chỉ đưa check vào trong transaction **không tự bảo đảm không có race**; còn phải chọn isolation và conflict handling đúng. Vì vậy câu “Security luôn phải ngoài Transaction” không phải định luật phổ quát.

### 3.3. Denial có cần được audit?

Nếu audit mọi lần từ chối là bắt buộc, đặt Logging duy nhất bên trong Security có thể khiến denial không bao giờ vào Logging. Có thể dùng một **safe request audit** ngoài Security hoặc cho Security phát một security-decision event riêng.

Khi log trước authorization, **không ghi toàn bộ request payload, token, password, cookie hay thông tin nhạy cảm**. Chỉ ghi dữ liệu tối thiểu cần cho audit như correlation ID, operation label, actor ID hợp lệ nếu có, decision code và thời điểm.

## 4. Transaction: return khác commit

Một transaction advice dạng khái niệm:

~~~text
BEGIN
    result = proceed()
    COMMIT nếu policy cho phép
    return result
nếu lỗi:
    thực hiện xử lý rollback thích hợp
    ném lại lỗi
~~~

Đây là giả mã. Transaction thực có isolation, propagation, connection/resource state, rollback-only, nested/savepoint, commit failure và nhiều loại exception.

### 4.1. Đừng gọi mọi return là thành công

Xét:

~~~text
Transaction(
    Logging(
        Business
    )
)
~~~

Business trả OK. Logging bên trong ghi **SUCCESS**. Sau đó Transaction ngoài cùng **mới tiến hành COMMIT**. Nếu commit thất bại, log có thể báo thành công cho một thay đổi chưa được xác nhận bền vững.

Nên phân biệt:

- **BUSINESS_RETURNED:** method nghiệp vụ trả bình thường.
- **COMMIT_ATTEMPTED:** bắt đầu commit.
- **COMMIT_CONFIRMED:** transaction manager/storage báo commit thành công.
- **ROLLBACK_CONFIRMED:** rollback được xác nhận theo API.
- **OUTCOME_UNKNOWN:** không chắc commit có hoàn tất hay chưa.

Logging ngoài Transaction thường có thể quan sát transaction wrapper hoàn tất bình thường hay ném exception. Nhưng khi commit outcome chưa rõ, một wrapper ném lỗi **không tự chứng minh rollback đã hoàn tất**.

### 4.2. Rollback theo chính sách, không chỉ theo loại exception

Không có quy tắc AOP chung rằng mọi Throwable đều rollback:

- Một số transaction policy rollback trên một nhóm exception nhất định.
- Một số checked errors có thể được xử lý mà vẫn commit.
- Một advice trong cùng chain có thể swallow exception và trả fallback.
- Một rollback-only flag có thể được set ngay cả khi exception được catch.
- Một commit failure có thể xảy ra sau khi business method đã hoàn tất.

Phải định nghĩa **lỗi nào rollback**, **lỗi nào commit**, **lỗi nào trạng thái không xác định** và **ai chịu trách nhiệm báo cho caller**.

### 4.3. Bẫy catch-and-return

~~~text
Transaction(
    LoggingSwallows(
        Business throws
    )
)
~~~

Nếu LoggingSwallows catch lỗi rồi trả default value như một kết quả bình thường, Transaction ở ngoài có thể nghĩ operation thành công. Nếu transaction không được đánh dấu rollback-only bằng một cơ chế khác, nó có thể commit những thay đổi một phần.

**Không dùng Logging advice để nuốt lỗi nghiệp vụ**, trừ khi thay đổi exception contract là một quyết định có chủ đích, có test transaction policy tương ứng.

## 5. Logging: operational trace, audit và event committed khác nhau

Logging có thể phát những record ở thời điểm khác nhau:

| Event | Câu hỏi nó trả lời |
|---|---|
| ATTEMPT | Một request đã tiến đến boundary chưa? |
| AUTH_ALLOWED/AUTH_DENIED | Quyết định cho phép/từ chối là gì? |
| EXECUTION_STARTED | Body nghiệp vụ đã bắt đầu chưa? |
| BUSINESS_RETURNED | Method đã trả bình thường chưa? |
| COMMIT_CONFIRMED | Giao dịch đã được báo commit thành công chưa? |
| ROLLBACK/OUTCOME_UNKNOWN | Rollback hoặc kết quả không chắc chắn? |
| ERROR | Lỗi nào được quan sát tại boundary? |

**Console log không tương đương audit log bền vững.** Một operational logger có thể ghi disk, stdout, queue hoặc collector với semantics riêng. Audit theo yêu cầu bảo mật/pháp lý thường cần độ bền, quyền truy cập, retention và khả năng phát hiện chỉnh sửa.

### 5.1. Logging nằm ngoài Security

Ưu điểm: có thể thấy cả attempt bị Security từ chối, không phải mở Transaction nếu Security từ chối trước proceed.

Rủi ro: logging quá sớm có thể ghi dữ liệu không được phép, lộ thông tin hoặc tạo overhead dưới lưu lượng tấn công. Cần **redaction, rate limiting theo policy, data minimization** và log message được cấu trúc rõ ràng.

### 5.2. Logging nằm trong Transaction

Nếu Logging chỉ in ra console hay gửi remote message, thông điệp đó **không tự rollback cùng database**. Nếu Logging insert một audit row trong cùng transaction, row có thể rollback với nghiệp vụ, đồng nghĩa denial hoặc failure record bị mất.

Vị trí advice không tự xác định **độ bền của bản ghi**; còn phụ thuộc sink và transaction mà sink tham gia.

### 5.3. Logging nằm ngoài Transaction

Logging ngoài Transaction có thể biết continuation đã commit thành công theo API hoặc throw khi commit fail. Nhưng write vào log sink vẫn có thể thất bại sau khi database đã commit. Do đó không có **atomicity mặc định** giữa business DB commit và ghi log ngoài DB.

## 6. Ba thứ tự điển hình và sự khác biệt

Ký hiệu:

- S = Security
- L = Logging
- T = Transaction
- B = Business

| Composition | Denial | Có transaction khi deny? | Có log denial từ L? | Success log trước hay sau commit wrapper? |
|---|---|---|---|---|
| **S(L(T(B)))** | S từ chối trước proceed | Không | Không | L sau T nếu được allow |
| **L(S(T(B)))** | L thấy attempt rồi S từ chối | Không | Có | L sau T nếu được allow |
| **T(L(S(B)))** | T begin, L attempt, S từ chối | Có | Có | L trước T.commit |

Đây là kết quả theo **mô hình wrapper cùng boundary**, với S ném lỗi khi deny, T begin trước proceed, L ghi khi vào/ra. Không phải thứ tự mặc định của một engine AOP bất kỳ.

### 6.1. S(L(T(B))) — Security ngoài cùng

~~~text
Request denied:
    Security.check -> DENY -> Caller
    Không chạy Logging hoặc Transaction bên trong
~~~

Hiệu quả từ chối sớm, nhưng không đáp ứng yêu cầu audit denial nếu chỉ có Logging ở trong Security.

Đường success:

~~~text
Security.check
-> Logging.attempt
-> Transaction.begin
-> Business
-> Transaction.commit
-> Logging.success
-> Caller
~~~

### 6.2. L(S(T(B))) — Logging ngoài cùng

~~~text
Request denied:
    Logging.attempt
    -> Security.check -> DENY
    -> Logging.failure
    -> Caller
~~~

Không mở transaction cho denial, đồng thời ghi được rejection nếu Logging catch exception. Tuy nhiên **an toàn dữ liệu ghi log phải được thiết kế**.

Đường success:

~~~text
Logging.attempt
-> Security.check
-> Transaction.begin
-> Business
-> Transaction.commit
-> Logging.success
~~~

### 6.3. T(L(S(B))) — Transaction ngoài cùng

~~~text
Request denied:
    Transaction.begin
    -> Logging.attempt
    -> Security.check -> DENY
    -> Logging.failure
    -> Transaction.rollback-attempt
    -> Caller
~~~

Có thể mở transaction không cần thiết. Với success, Logging bên trong T có thể báo business success **trước** commit. Điều này không nên được gọi là **committed success**.

### 6.4. Không có một thứ tự tối ưu chung

Nếu quyền phụ thuộc dữ liệu trong database, một phương án nhiều tầng có thể tốt hơn:

~~~text
Safe request audit
    -> Coarse authentication/authorization
        -> Transaction
            -> Resource-level authorization
                -> Business update
~~~

Cần xác minh pointcut, consistency, isolation và độ bền audit. Đây là một mô hình tư duy, không phải yêu cầu mọi hệ thống phải dùng.

## 7. Java 17 runnable: mô phỏng ba thứ tự và hai loại lỗi

Chương trình dùng **Java 17 thuần**, mô phỏng quanh một operation bằng các **wrapper functions**. Nó không chạy AOP compiler hoặc tạo transaction database thật. Mục đích là làm rõ **semantics của precedence**, short-circuit và exception flow.

Các wrapper:

- Security kiểm tra actor == admin và throw SecurityException nếu không hợp lệ.
- Transaction in begin, thực thi continuation, in commit nếu không lỗi; với lỗi in **rollback-attempt** rồi rethrow.
- Logging in attempt; nếu thành công in success; nếu continuation throw thì in failure rồi rethrow.
- Business in core: execute và có thể ném lỗi mô phỏng.
- Có lỗi commit giả lập để phân biệt body return với transaction completion.

Tạo file **AspectSemanticsDemo.java**:

~~~java
public class AspectSemanticsDemo {
    record Request(String actor, boolean failBody, boolean failCommit) {}

    @FunctionalInterface
    interface Work {
        String run(Request request);
    }

    static Work core() {
        return request -> {
            System.out.println("core: execute");
            if (request.failBody()) {
                throw new IllegalStateException("business-failed");
            }
            return "OK";
        };
    }

    static Work security(Work next) {
        return request -> {
            System.out.println("security: check");
            if (!"admin".equals(request.actor())) {
                throw new SecurityException("denied");
            }
            return next.run(request);
        };
    }

    static Work transaction(Work next) {
        return request -> {
            System.out.println("tx: begin");
            try {
                String result = next.run(request);
                if (request.failCommit()) {
                    throw new IllegalStateException("commit-failed");
                }
                System.out.println("tx: commit");
                return result;
            } catch (RuntimeException e) {
                System.out.println("tx: rollback-attempt");
                throw e;
            }
        };
    }

    static Work logging(Work next) {
        return request -> {
            System.out.println("log: attempt");
            try {
                String result = next.run(request);
                System.out.println("log: success " + result);
                return result;
            } catch (RuntimeException e) {
                System.out.println("log: failure " + e.getMessage());
                throw e;
            }
        };
    }

    static void scenario(String name, Work pipeline, Request request) {
        System.out.println("=== " + name + " ===");
        try {
            System.out.println("caller: " + pipeline.run(request));
        } catch (RuntimeException e) {
            System.out.println("caller: " + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        Request denied = new Request("guest", false, false);
        Request success = new Request("admin", false, false);
        Request businessFail = new Request("admin", true, false);
        Request commitFail = new Request("admin", false, true);

        Work securityOuter = security(logging(transaction(core())));
        Work loggingOuter = logging(security(transaction(core())));
        Work transactionOuter = transaction(logging(security(core())));

        scenario("SEC-LOG-TX denied", securityOuter, denied);
        scenario("LOG-SEC-TX denied", loggingOuter, denied);
        scenario("TX-LOG-SEC denied", transactionOuter, denied);
        scenario("LOG-SEC-TX success", loggingOuter, success);
        scenario("SEC-LOG-TX body failure", securityOuter, businessFail);
        scenario("LOG-SEC-TX commit failure", loggingOuter, commitFail);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 AspectSemanticsDemo.java
java AspectSemanticsDemo
~~~

**Stdout đã được kiểm chứng bằng Java 17:**

~~~text
=== SEC-LOG-TX denied ===
security: check
caller: SecurityException
=== LOG-SEC-TX denied ===
log: attempt
security: check
log: failure denied
caller: SecurityException
=== TX-LOG-SEC denied ===
tx: begin
log: attempt
security: check
log: failure denied
tx: rollback-attempt
caller: SecurityException
=== LOG-SEC-TX success ===
log: attempt
security: check
tx: begin
core: execute
tx: commit
log: success OK
caller: OK
=== SEC-LOG-TX body failure ===
security: check
log: attempt
tx: begin
core: execute
tx: rollback-attempt
log: failure business-failed
caller: IllegalStateException
=== LOG-SEC-TX commit failure ===
log: attempt
security: check
tx: begin
core: execute
tx: rollback-attempt
log: failure commit-failed
caller: IllegalStateException
~~~

### 7.1. Vì sao thứ tự thay đổi log denial?

Ở **SEC-LOG-TX denied**, Security throw trước khi gọi Logging, nên không có log attempt/denied.

Ở **LOG-SEC-TX denied**, Logging in attempt, Security throw, Logging catch và in failure denied. Transaction không được chạy.

Ở **TX-LOG-SEC denied**, Transaction begin trước khi kiểm tra quyền, nên có rollback-attempt dù nghiệp vụ chưa thực hiện.

### 7.2. Success phải sau transaction wrapper

Ở **LOG-SEC-TX success**, thứ tự:

~~~text
Logging.attempt
Security.check
Transaction.begin
Business
Transaction.commit
Logging.success
~~~

Về mặt continuation, Logging nằm ngoài T nhìn thấy commit wrapper đã hoàn tất. Tuy nhiên console log này **không là audit record atomic với DB commit**.

### 7.3. Body failure khác commit failure

Trong **body failure**, Core ném IllegalStateException trước khi hoàn tất; transaction wrapper in rollback-attempt, rồi Logging in failure.

Trong **commit failure**, Core đã trả OK nhưng wrapper gặp lỗi ở bước commit giả lập, nên Logging ở ngoài chỉ thấy failure. Trong database thật, commit error **có thể có kết quả không xác định**, và rollback-attempt không chứng minh rollback thành công.

### 7.4. Giới hạn của demo

Không có database, broker, distributed transaction, bytecode weaver hay một engine pointcut thật. Kết quả đo được chứng minh **wrapper ordering và exception propagation**, không chứng minh atomic commit/rollback hoặc default precedence của AOP tool.

## 8. Logger nằm trước commit có thể báo sai outcome

Xét:

~~~text
Transaction(
    Logging(
        Business
    )
)
~~~

Business return OK -> Logging ghi success -> Transaction mới commit. Nếu commit throw, success log đã xảy ra **quá sớm**.

Do đó log schema nên phân biệt:

~~~text
ATTEMPT
BUSINESS_RETURNED
COMMIT_ATTEMPTED
COMMIT_CONFIRMED
COMMIT_FAILED
OUTCOME_UNKNOWN
~~~

Đừng đặt tên event **TRANSACTION_COMMITTED** tại advice chỉ nhìn thấy Business returned. Đừng nhầm after-returning advice của method nghiệp vụ với “after commit” khi Transaction là một wrapper khác ở bên ngoài.

### 8.1. Sink log nào có thể rollback?

- Console/file: thường ngoài database transaction.
- Remote log collector: có thể lưu hoặc fail độc lập.
- Database audit row trong cùng transaction: có thể bị rollback với business update.
- Message gửi trực tiếp đến broker: không tự bị DB rollback.
- Outbox row trong cùng database transaction: có thể commit/rollback cùng business row khi thực sự tham gia cùng transaction.

Nếu rollback cũng xóa security-denial audit row, chính sách ghi nhận denial có thể bị phá. Nếu remote log sống sau rollback, “business success” ghi sớm có thể sai sự thật.

## 9. Transactional outbox: gắn event với commit

Khi một transaction thay đổi business data và phải gửi audit/business event sang hệ thống khác, có hai khoảng lỗi:

**Gửi sau commit:**

~~~text
UPDATE database -> COMMIT -> PUBLISH event
~~~

Process có thể crash giữa commit và publish; dữ liệu đã thay đổi nhưng không có event.

**Gửi trước commit:**

~~~text
PUBLISH event -> UPDATE database -> COMMIT
~~~

Nếu database rollback, event có thể nói về dữ liệu chưa từng commit.

**Transactional outbox** ghi business update và một outbox row trong **cùng transaction database**:

~~~text
BEGIN
    resource authorization
    update business rows
    insert outbox event with stable event ID
COMMIT
    |
    v
relay đọc outbox rows committed
    |
    v
publish (có retry)
    |
    v
consumer idempotent/deduplicate
~~~

Khi cùng transaction, outbox row không commit nếu business update rollback. Relay có thể publish trùng nếu crash sau gửi nhưng trước xác nhận. Vì thế **outbox không bảo đảm exactly-once end-to-end**; consumer idempotency và deduplication vẫn cần.

**Phân biệt** security denial audit với committed business event: denial có thể cần ghi vào kênh audit riêng không bị rollback bởi transaction nghiệp vụ, còn business event thường cần atomicity với thay đổi dữ liệu.

## 10. TOCTOU: authorization và transaction cần phối hợp

Nếu resource ownership hoặc hạn mức thay đổi theo thời gian, quyết định quyền có thể không còn đúng giữa check và update. Đề xuất khái niệm:

~~~text
Safe attempt logger
  |
  v
Authentication + coarse permission
  |
  +-- DENY -> safe audit, không vào business transaction
  |
  v
Transaction begin
  |
  v
Read resource under intended consistency/isolation
  |
  v
Resource-level authorization
  |
  +-- DENY -> xử lý transaction, audit denial theo policy
  |
  v
Conditional update + outbox record
  |
  v
Commit
~~~

Cần xác định isolation, optimistic locking, row locks hoặc constraints. Một transaction vẫn có thể gặp concurrent anomaly nếu isolation không đủ. **AOP precedence không tự thay thế thiết kế nhất quán database**.

### 10.1. Nếu security policy nằm ngoài transaction thì sao?

Có thể phù hợp với claim/token checks hoặc thông tin tương đối bất biến. Nhưng quyền theo record mutable có thể cần **revalidation** ngay tại update. Thiết kế chỉ check một lần ở ngoài cần chứng minh được không có TOCTOU theo threat model.

## 11. Exception propagation và quyết định rollback

Các tầng quanh nhau có thể ném, bắt, đổi hoặc nuốt exception.

**Security throw:** nếu Security ngoài T, T chưa chạy; nếu T ngoài Security, T đã begin và có thể thấy exception.

**Business throw:** Transaction nhận lỗi nếu exception đi qua không bị nuốt. Rollback behavior phụ thuộc policy.

**Logging throw:** operational logger có thể thay exception gốc hoặc khiến outer Transaction rollback, dù Business chạy thành công. Cần policy cố ý: fail-open cho observability không thiết yếu, hoặc fail-closed cho audit bắt buộc.

**Exception bị nuốt:** Logging nằm trong T catch lỗi và trả fallback có thể làm outer T tưởng continuation thành công. Đừng biến một logging advice thành nơi quyết định kết quả nghiệp vụ không rõ ràng.

**Commit throw:** Logging ở trong T đã chạy trước commit, nên không tự quan sát được commit failure; Logging ở ngoài T nhận lỗi wrapper nhưng không mặc nhiên biết kết quả durable.

### 11.1. Giữ lỗi gốc và ghi lỗi thứ cấp

Khi log failure cũng gặp lỗi, cần không che exception gốc một cách vô tình. Một chính sách vận hành có thể ghi lỗi logger bằng kênh dự phòng, thêm suppressed exception nếu phù hợp hoặc trả một error có cấu trúc rõ. Với security audit bắt buộc, có thể cần từ chối operation, nhưng quyết định đó phải được thiết kế/test, không tùy tiện.

## 12. After advice và ranh giới quan sát

**After returning** của Business chỉ biết Business method return. Nó **không biết transaction ngoài cùng đã commit**.

**After throwing** chỉ thấy exception thoát ra từ join point được bao; nếu một interceptor khác catch và return fallback thì không nhất thiết nhìn thấy lỗi ấy.

**After/finally** có thể chạy khi continuation return hoặc throw; nhưng advice finally cũng có thể throw và che lỗi gốc.

**Around** nhìn thấy toàn bộ continuation nó bao. Nếu muốn quan sát transaction wrapper normal completion, Logging around cần nằm ngoài transaction boundary hoặc đăng ký một callback sau commit do transaction mechanism cung cấp nếu có.

**Không dùng tên loại advice thay thế việc xác định chính xác điểm được chọn và thứ tự thực thi.**

## 13. Retry, idempotency và nhiều transaction

Giả sử thêm **Retry**:

~~~text
Logging(Retry(Transaction(Business)))
~~~

Logging ngoài có thể ghi một request attempt, trong khi Retry tạo nhiều transaction attempts.

~~~text
Retry(Logging(Transaction(Business)))
~~~

Logging nằm trong Retry có thể ghi một attempt/failure cho mỗi lần thử.

~~~text
Transaction(Retry(Business))
~~~

Retry ở trong một transaction có thể gặp transaction đã bị đánh dấu rollback-only và có thể giữ lock lâu hơn cần thiết. Không có thứ tự “an toàn” chung khi chưa biết loại lỗi và side effects.

Nếu commit outcome uncertain, retry có thể tạo một bản ghi/thanh toán/gửi message trùng. Cần **idempotency key**, database constraint hoặc reconciliation để nhận diện request đã được xử lý. Transaction không tự rollback email, HTTP request hoặc event publish đã được gửi trước đó.

Log nên phân biệt **request ID** và **attempt ID**. Một request có ba attempts không phải ba yêu cầu nghiệp vụ mới.

## 14. Async và context propagation

Một aspect có thể bắt đầu transaction trong thread A, nhưng Business chuyển công việc sang thread B.

~~~text
Caller thread:
    Security -> Transaction begin -> schedule async task -> return
    Transaction commit/close

Worker thread:
    async operation vẫn đang chạy
~~~

Nếu method trả một future/task handle, Logging after returning có thể thấy **scheduling thành công** chứ không phải hoàn tất nghiệp vụ. Transaction của caller có thể không bao toàn bộ công việc ở thread khác.

Không giả định thread-local security/transaction context tự chuyển qua async worker. Cần biết công cụ có context propagation hay không, dữ liệu nào được phép truyền, khi nào future hoàn tất, và transaction của từng phần công việc bắt đầu/kết thúc ở đâu.

Nếu operation thật sự bất đồng bộ, định nghĩa event theo **task accepted / task completed / task failed** và kiểm thử completion, không gán chung success cho mọi bước.

## 15. Multiple join points và logging hai lần

Security có thể chặn execution, Transaction gắn ở proxy, Logging chọn call site. Khi đó một request có thể sinh nhiều join points:

~~~text
Caller [call-site logging]
   |
   v
Proxy [authorization]
   |
   v
Woven target execution [transaction + logging?]
   |
   v
Business method
~~~

Nếu cả Logging ở call site và Logging ở execution đều ghi “operation success” không phân biệt, metric có thể bị đếm hai lần. Nếu target tự gọi một method có execution advice, còn có event nội bộ.

Cần log **join point kind, method signature, correlation ID** và đếm riêng request, attempt, transaction, target execution. Thứ tự event phải kiểm tra trên **đường runtime thực**, không chỉ trên danh sách advice.

### 15.1. Proxy bypass

Một Security aspect chỉ gắn vào proxy có thể không chạy nếu caller giữ target reference và gọi trực tiếp, hoặc target tự gọi method khác trên chính mình mà không quay qua proxy. Với chính sách bảo mật bắt buộc, cần kiểm tra bao phủ cả direct/self-invocation/callback hoặc chọn một cơ chế instrument khác phù hợp.

## 16. Kiểm soát độ bền và tính an toàn của log

Một audit pipeline đáng tin cần hỏi:

1. Ai được phép tạo audit record?
2. Request bị từ chối có bắt buộc được ghi không?
3. Ghi metadata nào là đủ? Có lộ secret không?
4. Record là attempt, authorization decision, business return hay commit outcome?
5. Sink thuộc cùng DB transaction hay độc lập?
6. Có thể mất record khi process crash/network partition không?
7. Có thể nhận duplicate do retries/outbox relay không?
8. Có retention, access control và tamper evidence phù hợp không?
9. Correlation/request/attempt/event IDs được sinh ở đâu?
10. Audit sink lỗi thì **fail-open** hay **fail-closed**?
11. Có giới hạn log flood trên denied requests không?
12. Có thể liên kết event với policy version hay transaction outcome không?

Không log raw credentials, session tokens, authentication secrets hoặc object.toString không kiểm soát. Dữ liệu audit và quyền truy cập audit cũng là một phần của thiết kế bảo mật.

## 17. Chi phí vận hành: thứ tự nào cũng có giá

- Transaction ngoài Security có thể tạo transaction không cần thiết cho denied requests.
- Logging ngoài Security có thể nhận lưu lượng rejected request lớn và phải redaction/rate limit.
- Resource-level authorization trong transaction có thể thêm truy vấn hoặc lock nhưng là chi phí bảo đảm consistency.
- Ghi remote audit đồng bộ có thể tăng latency và trở thành điểm lỗi.
- Outbox thêm bảng, relay, retention và deduplication nhưng hỗ trợ coupling bền vững với commit.
- Retry mở nhiều transaction có thể tăng lock contention và nguy cơ side effect trùng.

Không chọn precedence chỉ vì ít lời gọi advice nhất. **Đầu tiên xác định invariants và yêu cầu audit**, sau đó đo throughput, p95/p99 latency, transaction duration, queue lag và tỷ lệ error.

## 18. Checklist thiết kế precedence

1. **Invariant:** Không cập nhật dữ liệu khi không có quyền; không ghi commit success trước commit.
2. **Audit semantics:** Denial/attempt có cần bền vững không?
3. **Data minimization:** Logging ngoài Security có an toàn không?
4. **Authorization inputs:** Quyền có phụ thuộc database record mutable không?
5. **Transaction isolation:** Có chống TOCTOU/races theo yêu cầu không?
6. **Composition:** Aspect nào ngoài, aspect nào trong, precedence được khai báo/test ra sao?
7. **Rollback policy:** Exception nào rollback, exception nào không, lỗi bị swallow thì sao?
8. **Commit outcome:** Đã phân biệt confirmed/failed/unknown chưa?
9. **External side effects:** Có outbox, idempotency và retry policy không?
10. **Async:** Transaction/security context có theo đúng operation không?
11. **Logging failure:** Có che lỗi gốc hoặc đổi business result ngoài ý muốn không?
12. **Coverage:** Có direct call/proxy bypass/nested join points không?
13. **Diagnostics:** Request ID, attempt ID và policy ID có truy vết được không?
14. **Test cases:** Denial, business failure, commit failure, logger failure và concurrency đều được kiểm chứng.

## 19. Ma trận kiểm thử tối thiểu

| Kịch bản | Điều phải xác minh |
|---|---|
| Unauthorized request | Business không thực thi và không tạo side effect |
| S(L(T(B))) denied | L/T không chạy nếu S short-circuit |
| L(S(T(B))) denied | L ghi denial an toàn, T không begin |
| T(L(S(B))) denied | T bắt đầu trước S; rollback policy rõ |
| Authorized success | Thứ tự commit/success log như định nghĩa |
| Business body throws | T rollback theo policy; log failure chính xác |
| Commit fails | Không ghi committed success; xử lý unknown outcome |
| Logger throws | Exception policy rõ, không vô ý che lỗi nghiệp vụ |
| Inner advice swallows error | T không commit sai vì thấy normal return |
| Permission changed concurrently | Resource-level authorization không TOCTOU |
| Outbox transaction rolls back | Không có committed event row |
| Relay publishes twice | Consumer idempotent |
| Async task fails after return | Không log completion success quá sớm |
| Retry on uncertain commit | Không nhân đôi side effect |
| Proxy bypass/self-call | Security policy có được bao phủ không |
| Multiple logging join points | Tránh đếm trùng metric |
| Denied request with secrets | Audit không ghi token/password |
| Audit sink outage | Fail-open/closed đúng yêu cầu |

## 20. Lỗi phổ biến

**Lỗi 1 — Xem thứ tự aspect chỉ là chuyện hiệu năng.** Nó có thể thay đổi security coverage, transaction và outcome logs.

**Lỗi 2 — Cho Security luôn phải ngoài Transaction.** Quyền phụ thuộc dữ liệu mutable có thể cần recheck trong transaction.

**Lỗi 3 — Đặt Transaction ngoài tất cả để “chắc chắn”.** Có thể mở transaction cho denied requests.

**Lỗi 4 — Logging trong T ghi success trước commit.** Success ấy chỉ có nghĩa Business returned, không phải committed.

**Lỗi 5 — Logging ngoài T luôn là atomic audit.** DB commit và log sink độc lập có thể fail ở hai thời điểm.

**Lỗi 6 — Audit trong DB transaction luôn giữ denial.** Rollback có thể xóa audit row cùng transaction.

**Lỗi 7 — Rollback-attempt chứng minh rollback hoàn tất.** Outcome có thể không chắc chắn.

**Lỗi 8 — Mọi exception tự động rollback.** Phụ thuộc transaction policy.

**Lỗi 9 — Nuốt exception trong Logging không nguy hiểm.** Có thể làm Transaction ngoài commit sai.

**Lỗi 10 — Logger failure không thể đổi kết quả nghiệp vụ.** Advice throw có thể ảnh hưởng caller/rollback.

**Lỗi 11 — Log mọi arguments trước security là bình thường.** Có thể làm lộ dữ liệu.

**Lỗi 12 — Retry vô điều kiện khi commit fail.** Có thể tạo duplicate side effects.

**Lỗi 13 — Outbox bảo đảm exactly-once toàn hệ thống.** Relay/consumer vẫn cần dedup và idempotency.

**Lỗi 14 — Async method trả bình thường nghĩa công việc đã xong.** Có thể chỉ schedule task.

**Lỗi 15 — Tất cả aspects có chung điểm và luôn một event.** Call/execution, proxy và retries có thể tạo nhiều event.

**Lỗi 16 — Precedence mặc định có thể suy từ tên file.** Phải tra semantics công cụ và test.

## 21. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** Với S(L(T(B))), bị từ chối trước proceed, L có chạy không?

**Đáp:** Không trong mô hình này; S short-circuit trước L.

**Câu 2.** Với L(S(T(B))), request bị deny có vào transaction không?

**Đáp:** Không nếu S throw trước gọi T; L có thể ghi denial.

**Câu 3.** Với T(L(S(B))), denial có thể mở transaction không?

**Đáp:** Có vì T begin trước S.

**Câu 4.** Logging trong T ghi success sau Business return, vậy DB đã commit chưa?

**Đáp:** Chưa chắc; T.commit còn ở phía ngoài.

**Câu 5.** Logging ngoài T thấy T return, log bền vững được đảm bảo không?

**Đáp:** Không; log sink vẫn có thể thất bại độc lập với database.

**Câu 6.** Vì sao authorization có thể phải kiểm tra trong transaction?

**Đáp:** Khi quyền gắn với state mutable cần isolation/version validation để tránh TOCTOU.

**Câu 7.** Có nên kiểm tra coarse role trước transaction dù resource check cần ở bên trong?

**Đáp:** Có thể có ích để từ chối sớm; resource-level check vẫn cần khi dữ liệu mutable.

**Câu 8.** Nếu một interceptor catch lỗi business rồi return fallback, T ở ngoài có thể làm gì?

**Đáp:** Nó có thể commit nếu policy dựa normal return và không có rollback-only flag.

**Câu 9.** Commit failure có chắc rollback được không?

**Đáp:** Không; outcome có thể unknown, cần idempotency/reconciliation.

**Câu 10.** Outbox có giải quyết audit denial không?

**Đáp:** Không mặc định; denial có thể không có committed business transaction hoặc outbox row bị rollback, cần kênh phù hợp.

**Câu 11.** Vì sao cần request ID và attempt ID riêng?

**Đáp:** Một request có thể được retry nhiều lần, tạo nhiều transaction/advice events.

**Câu 12.** Một async operation đã schedule nhưng chưa hoàn tất, ghi success hoàn tất có đúng không?

**Đáp:** Không; chỉ nên ghi scheduled/accepted trừ khi quan sát được completion.

**Câu 13.** Khi Security nằm ở proxy, target self-invocation có thể bypass không?

**Đáp:** Có trong một số proxy models; phải test đúng mechanism.

**Câu 14.** Có một thứ tự Security/Transaction/Logging luôn đúng cho mọi hệ thống không?

**Đáp:** Không. Phải dựa vào invariants, nguồn authorization, audit durability, transaction scope và join points.

## 22. Sơ đồ ghi nhớ

~~~text
                      REQUEST
                         |
                         v
                Safe request logging
                         |
                         v
               Coarse security check
                  |             |
                DENY           ALLOW
                  |             |
                  v             v
              Safe audit    Transaction begin
                                 |
                                 v
                      Resource authorization
                                 |
                        +--------+--------+
                        |                 |
                      DENY               ALLOW
                        |                 |
                 error/rollback      Business update
                                          |
                                          v
                                  Outbox record
                                          |
                                          v
                                    Commit attempt
                                      |       |
                                      v       v
                                  Confirmed  Unknown/failed
                                      |       |
                                      v       v
                                 Durable     Reconciliation/
                                 delivery    error policy
~~~

**Kết luận:** Security, Transaction và Logging là ba mối quan tâm xuyên cắt có **phụ thuộc ngữ nghĩa rõ ràng**. Security quyết định quyền và điểm dừng, Transaction quyết định ranh giới nhất quán/commit/rollback, Logging phải gọi đúng tên những sự kiện nó thật sự biết và đảm bảo dữ liệu ghi được bảo vệ. Chọn precedence từ **invariant bảo mật và tính đúng dữ liệu**, kiểm chứng trên đường lỗi/retry/async/commit, sau đó mới tối ưu overhead.

## Tài liệu tham khảo

- [AspectJ Programming Guide](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): join point, pointcut, around advice và precedence trong một ngôn ngữ AOP cụ thể.
- [Java SE 17 — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): exception propagation, cause và suppressed exceptions.
- [Java Language Specification — Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): semantics của exception.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): lưu outbox row cùng database transaction rồi relay sự kiện.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): log nhạy cảm, security events và audit reliability.
