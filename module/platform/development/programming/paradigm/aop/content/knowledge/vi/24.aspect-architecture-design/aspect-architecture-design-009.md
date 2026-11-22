# Tài liệu hóa phạm vi, hợp đồng và các quyết định về thứ tự trong AOP

## 1. Mục tiêu và vấn đề cần giải quyết

Aspect-Oriented Programming (AOP) đưa những mối quan tâm cắt ngang như xác thực, phân quyền, ghi log, đo lường, transaction, retry và audit ra khỏi thân phương thức nghiệp vụ. Một **pointcut** mô tả tập *join point* được chọn; **advice** thực hiện hành vi tại những điểm đó; cơ chế **weaving**, instrumentation hay proxy khiến lời gọi thật đi qua advice.

Tuy nhiên, tách mã không có nghĩa tách trách nhiệm hoặc loại bỏ phụ thuộc. Một phương thức có thể trông như không liên quan đến audit, nhưng trong production lại phải có audit; một lời gọi có thể yêu cầu transaction trước khi truy cập dữ liệu; hoặc một kết quả bất đồng bộ cần giữ context tới khi hoàn tất. Nếu việc này chỉ tồn tại trong biểu thức pointcut và cấu hình thứ tự ở nơi khác, người sửa mã rất khó biết thay đổi nào làm mất hợp đồng.

**Tài liệu kiến trúc AOP cần trả lời được ba câu hỏi:**

1. **Phạm vi:** Những điểm thực thi nào phải, có thể hoặc tuyệt đối không được nhận advice? Đường lời gọi nào đi qua cơ chế AOP?
2. **Hợp đồng:** Advice được quan sát hoặc thay đổi những gì? Nó có thể bỏ qua thao tác gốc, gọi lại, thay đổi exception, ngăn access, mở transaction, cấp tài nguyên hay tạo side effect không?
3. **Thứ tự:** Khi nhiều advice cùng áp dụng, cái nào ở ngoài/trong, thứ tự vào/ra và thứ tự xử lý lỗi là gì; tại sao chọn như thế và cách xác minh ra sao?

Bài này tập trung vào **AOP nói chung**, không ràng buộc người học vào một thư viện hoặc cơ chế gắn advice nhất định. Cú pháp biểu thức pointcut và quy tắc ưu tiên cụ thể luôn phải được tra theo engine đang sử dụng; tài liệu kiến trúc cần nêu chính xác quy tắc của engine được chọn thay vì giả định mọi engine có cùng semantics.

## 2. Từ join point tới phạm vi áp dụng thực tế

### 2.1 Phân biệt các tầng phạm vi

- **Join point model:** những điểm mà engine có khả năng can thiệp: method execution, method call, constructor, field access hay các loại khác tùy engine.
- **Pointcut expression:** điều kiện khai báo chọn các join point trong mô hình đó: package, lớp, tên, chữ ký, annotation hoặc ngữ cảnh lời gọi.
- **Weaving/wiring:** cách thực sự gắn advice. Proxy qua interface thường chỉ can thiệp lời gọi tới đối tượng proxy; bytecode weaving có thể có bề mặt khác.
- **Runtime entrypoint:** đường mà chương trình thật gọi tới nghiệp vụ. Một phương thức xuất hiện trong danh sách match chưa có nghĩa mọi đường tới nó đều được chặn.
- **Logical operation:** đơn vị nghiệp vụ cần chính sách, chẳng hạn `order.place` hoặc `payment.capture`. Một operation có thể đi qua nhiều method và một method có thể phục vụ nhiều operation.

Đừng dùng một câu mơ hồ như “áp dụng cho toàn bộ service”. Cần xác định cụ thể tập đầu vào, các ngoại lệ, cách match và cách quan sát runtime.

### 2.2 Ghi phạm vi bằng danh mục operation

Một danh mục tốt có thể biểu diễn như bảng:

| Operation | Điểm vào / join point | Advice bắt buộc | Ngoại lệ / không áp dụng | Đơn vị |
| --- | --- | --- | --- | --- |
| `order.place` | Cổng nhận lệnh đặt hàng | Authorization, transaction, audit, metrics | Không áp dụng lên helper thuần túy | Một lệnh logic |
| `order.quote` | Cổng báo giá | Metrics, tracing | Không cần transaction ghi | Một lời gọi |
| `payment.capture` | Lệnh thu tiền | Authorization, idempotency, audit, metrics | Không tự retry thao tác không idempotent | Một ý định thanh toán |
| `invoice.preview` | Tạo bản xem thử | Metrics | Không ghi audit thay đổi dữ liệu | Một lần tạo preview |

Đây là **ví dụ kiến trúc**. Khi dùng trong dự án, mỗi hàng còn cần ID ổn định, owner, nơi khai báo pointcut, điểm giải quyết context, mức độ quan trọng và bộ test minh chứng. Tên method có thể xuất hiện để định vị code, nhưng **không tự trở thành căn cứ cấp quyền**.

### 2.3 Ghi danh sách bao phủ và khoảng trống

Có thể biểu diễn:

- `R`: tập operation/join point **bắt buộc** áp chính sách.
- `M`: tập join point **thực sự match và được instrument**.
- `R ∖ M`: những điểm cần chính sách nhưng bị bỏ sót (*false negative*).
- `M ∖ R`: những điểm bị áp dụng ngoài dự kiến (*false positive*).

Ví dụ pointcut dùng tên `save*` có thể bỏ sót `placeOrder` dù phương thức cũng ghi dữ liệu. Một pointcut dùng package có thể bắt nhầm utility thuần túy. Tài liệu cần ghi **điều kiện khớp** lẫn **danh sách kỳ vọng**, vì chỉ chép nguyên regex không nói được ý định.

Nếu engine không hỗ trợ xuất danh sách match, sử dụng integration test qua entrypoint thật với advice thử nghiệm để ghi các điểm thực thi được quan sát. Khi thay đổi pointcut, so sánh tập thực tế trước/sau.

### 2.4 Những đường gọi cần được ghi rõ

| Đường gọi hoặc trường hợp | Rủi ro tài liệu thường bỏ sót |
| --- | --- |
| Lời gọi từ bên ngoài qua proxy | Thường là đường dễ thấy nhất, nhưng cấu hình có thể thiếu |
| Target được gọi trực tiếp | Đi vòng proxy, advice không chạy |
| Self-invocation (`this.method()`) | Có thể không đi qua proxy tùy engine |
| Lớp/constructor/static/final/private method | Khả năng can thiệp phụ thuộc kỹ thuật weaving/proxy |
| Method overload, generic bridge, annotation trên interface | Resolver có thể chọn nhầm chữ ký hoặc không thấy metadata |
| Callback, task trên executor, consumer sự kiện | Đường vào khác với lời gọi HTTP/CLI ban đầu |
| Method trả future/publisher | Trả handle chưa đồng nghĩa hoàn tất công việc |
| Reflection và dynamic dispatch | Điểm chặn phụ thuộc vào đường gọi và engine thực tế |

Khi cần bảo vệ một tài nguyên quan trọng, tài liệu phải chỉ ra **ranh giới cưỡng chế** mà mọi đường tới tài nguyên đều bắt buộc đi qua, hoặc lớp kiểm soát bổ sung tại kho dữ liệu/resource. Không dựa vào giả định “advice áp dụng mọi nơi” khi chưa kiểm chứng.

## 3. Hợp đồng của một advice gồm những gì?

Một **advice contract** là mô tả rõ quyền và nghĩa vụ của mã cắt ngang. Nên ghi:

- **Precondition:** điều gì phải có trước khi advice chạy: principal đã xác thực, request context, deadline, transaction state, cấu hình metric.
- **Execution semantics:** advice có gọi thao tác gốc không, tối đa bao nhiêu lần, thời điểm nào; có được short-circuit hoặc retry không.
- **Success semantics:** caller nhận kết quả gốc hay kết quả biến đổi? Có ghi audit/commit/cache hay không?
- **Failure semantics:** exception gốc được giữ nguyên, chuyển đổi hay nuốt; lỗi instrumentation có được làm hỏng nghiệp vụ không?
- **Cancellation/interruption:** khi cancel, timeout hoặc thread bị interrupt, xử lý tài nguyên và tín hiệu như thế nào.
- **Ownership:** ai cấp và ai giải phóng lock, transaction, context scope, semaphore permit, span, buffer.
- **Side effects:** ghi log/audit, tạo telemetry, gọi dịch vụ phụ, retry, ghi cache, phát sự kiện; có thực hiện trước hay sau commit?
- **Invariants:** điều kiện bắt buộc giữ, ví dụ “một call được chấp nhận gây đúng một lần gọi gốc” hoặc “không side effect khi chưa được phân quyền”.
- **Non-functional properties:** overhead, allocation, timeout, giới hạn queue và hành vi khi backend telemetry lỗi.

Không phải advice nào cũng được phép “thực thi gốc đúng một lần”. Advice caching có thể trả cache hit mà không gọi gốc; retry advice có thể cố ý gọi nhiều lần. Điều quan trọng là **ngoại lệ khỏi nguyên tắc một lần phải được ghi rõ**, kèm idempotency, số lần tối đa và tác động side effect.

### 3.1 Bảng hợp đồng minh họa

| Aspect | Có thể chặn lời gọi? | Có thể gọi lại gốc? | Thay đổi kết quả/lỗi? | Tài nguyên và điều kiện |
| --- | --- | --- | --- | --- |
| Authorization | Có, khi deny | Không | Có thể trả lỗi từ chối định nghĩa trước | Principal/action/resource/context tin cậy |
| Metrics | Không, nếu quan sát thuần túy | Không | Không, theo chính sách cách ly telemetry | Bộ đếm/histogram, bộ đệm có giới hạn |
| Retry | Có thể dừng sau số lần thử | Có, theo chính sách | Có thể đưa lỗi cuối khi hết lượt | Idempotency, backoff, deadline, hủy |
| Transaction | Có thể rollback/đưa lỗi | Thường không | Theo hợp đồng transaction | Begin/commit/rollback, ownership |
| Audit bắt buộc | Có thể fail-closed | Không tự gọi lại nghiệp vụ | Có thể từ chối nếu audit không được đảm bảo | Kho audit có độ bền được định nghĩa |
| Tracing | Không, nếu chỉ quan sát | Không | Không, trừ chính sách đã công bố | Span/context scope, propagation |

Bảng không áp đặt mọi dự án phải thực hiện như vậy; nó bắt người thiết kế **quyết định tường minh**. Một aspect đo lường có thể được thiết kế fail-open, còn một policy audit có thể fail-closed. Không được lấy chính sách tiện nhất cho telemetry áp dụng ngầm cho bảo mật.

### 3.2 Hợp đồng lỗi và `finally`

Một around advice đồng bộ thường đặt cleanup trong `finally`:

~~~java
long started = System.nanoTime();
try {
    return proceedOnce();
} finally {
    long elapsed = System.nanoTime() - started;
    recordMeasurement(elapsed);
}
~~~

Đây là **pseudocode Java**, các hàm `proceedOnce` và `recordMeasurement` chỉ biểu diễn ý tưởng. Cần lưu ý `recordMeasurement` có thể ném exception và che mất kết quả/lỗi nghiệp vụ nếu không cô lập lỗi đo đạc theo hợp đồng. Tương tự, transaction advice phải phân biệt thành công và exception, xử lý rollback/commit theo semantics thật.

Điều kiện đặc biệt như `Error` nghiêm trọng, huỷ tác vụ hoặc tiến trình bị dừng không thể được bảo đảm giải phóng tài nguyên chỉ bằng lời hứa “finally luôn chạy”. Tài liệu cần giới hạn mức bảo đảm và cơ chế khôi phục bên ngoài nếu có.

## 4. Thứ tự advice là một phần của hành vi quan sát được

Giả sử có ba decorator dạng around:

~~~text
A(B(C(operation)))
~~~

Khi thành công, thứ tự đi vào là:

~~~text
A enter
B enter
C enter
operation
C exit
B exit
A exit
~~~

Đây là **thứ tự lồng nhau dạng stack**, không phải “A rồi B rồi C và kết thúc”. Với `finally`, phần thoát thường diễn ra theo chiều ngược lại. Nếu một advice ném lỗi hoặc short-circuit, những advice nằm phía trong có thể **không hề chạy**.

### 4.1 Tài liệu phải dùng từ “outside/inside”

Câu “authorization trước transaction” vẫn có thể bị hiểu mơ hồ nếu engine có quy tắc ưu tiên ngược với cách viết danh sách. Ghi rõ:

~~~text
Outer -> inner:
  Audit -> Authorization -> Transaction -> Operation

Một lần thành công:
  audit-start
  authorization-check
  transaction-open
  business
  transaction-commit
  audit-success

Một lần bị deny:
  audit-start
  authorization-deny
  audit-failure
  (transaction không được mở, business không chạy)
~~~

Thứ tự này là **ví dụ hợp đồng đã chọn**, không phải thứ tự mặc định của mọi AOP engine. Engine nào cũng cần được kiểm tra mapping cụ thể từ cấu hình order/precedence sang chuỗi ngoài→trong.

### 4.2 Những thay đổi khi đổi vị trí aspect

**Authorization ngoài transaction:** chính sách phân quyền được kiểm tra trước khi mở transaction nghiệp vụ; từ chối quyền không mở transaction đó. Nếu policy cần đọc dữ liệu phải nhất quán với transaction, việc kiểm tra có thể cần cơ chế phối hợp khác; ghi rõ lựa chọn.

**Transaction ngoài authorization:** kiểm tra quyền nằm trong transaction, có thể giúp đọc resource state nhất quán, nhưng một request bị deny vẫn có chi phí transaction. Nếu quyền cần được kiểm tra trước bất kỳ side effect nào, các side effect khác ở tầng transaction/begin phải được đánh giá.

**Retry ngoài transaction:** mỗi attempt có thể mở transaction riêng. **Transaction ngoài retry:** nhiều attempt có thể nằm trong cùng một transaction tùy semantics; rollback, lock và khả năng retry của tài nguyên có thể khác. Không tự coi hai cách tương đương.

**Metrics ngoài retry:** thường đo latency của **logical operation**, gồm các lần thử và chờ backoff. **Metrics trong retry:** đo từng attempt. Cả hai đều có giá trị, nhưng **counter, mẫu số lỗi và tên metric** khác nhau.

**Audit ngoài cache:** có thể audit cả request cache hit. **Audit trong cache:** nếu cache trả về trước khi gọi gốc, advice bên trong có thể không chạy. Nếu audit là yêu cầu bắt buộc với mọi lần đọc nhạy cảm, thứ tự đó có thể vi phạm hợp đồng.

**Tracing ngoài async callback:** span có thể chỉ bao quanh thời gian tạo future. Muốn span end-to-end phải thiết kế closure tại completion và truyền context theo vòng đời.

Bởi vậy, “thứ tự” không chỉ là số ưu tiên. Tài liệu nên có **trace thời gian, semantics trong các nhánh success/deny/failure/cancel và lý do chọn**, rồi test với chính đường thực thi đó.

## 5. Ví dụ Java 17+: chứng minh thứ tự bằng composition tường minh

Để thấy cách **outside/inside** thay đổi hành vi, chương trình sau dùng interface và decorator thuần Java. Đây là mô hình minh họa cơ chế bao quanh tương đương với around advice; nó không phụ thuộc runtime weaving. Các hàm `audit`, `authorize` và `transaction` đại diện cho ba advice, còn `business` là hành vi gốc.

**Tệp: `AspectOrderDemo.java`**

~~~java
public class AspectOrderDemo {
    @FunctionalInterface
    interface Operation {
        String call(String id);
    }

    static Operation audit(Operation next) {
        return id -> {
            System.out.println("audit enter");
            try {
                String result = next.call(id);
                System.out.println("audit success");
                return result;
            } catch (RuntimeException error) {
                System.out.println("audit failure");
                throw error;
            } finally {
                System.out.println("audit exit");
            }
        };
    }

    static Operation authorize(Operation next) {
        return id -> {
            System.out.println("auth check");
            if (!id.startsWith("ok-")) {
                throw new SecurityException("denied");
            }
            return next.call(id);
        };
    }

    static Operation transaction(Operation next) {
        return id -> {
            // Đây chỉ là dấu vết thứ tự, không phải transaction ACID.
            System.out.println("tx begin");
            try {
                String result = next.call(id);
                System.out.println("tx commit");
                return result;
            } catch (RuntimeException error) {
                System.out.println("tx rollback");
                throw error;
            } finally {
                System.out.println("tx close");
            }
        };
    }

    static void invoke(Operation operation, String id) {
        try {
            System.out.println("caller=" + operation.call(id));
        } catch (SecurityException denied) {
            System.out.println("caller=DENIED");
        }
    }

    public static void main(String[] args) {
        Operation business = id -> {
            System.out.println("business " + id);
            return "saved-" + id;
        };

        Operation auditOutside =
            audit(authorize(transaction(business)));
        System.out.println("=== audit outside ===");
        invoke(auditOutside, "ok-7");
        invoke(auditOutside, "bad-3");

        Operation authOutside =
            authorize(audit(transaction(business)));
        System.out.println("=== auth outside ===");
        invoke(authOutside, "bad-3");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AspectOrderDemo.java
java AspectOrderDemo
~~~

**Stdout chính xác:**

~~~text
=== audit outside ===
audit enter
auth check
tx begin
business ok-7
tx commit
tx close
audit success
audit exit
caller=saved-ok-7
audit enter
auth check
audit failure
audit exit
caller=DENIED
=== auth outside ===
auth check
caller=DENIED
~~~

**Phân tích:**

- Với `audit(authorize(transaction(business)))`, audit **bao ngoài** authorization và transaction. Khi `ok-7` được phép, cả ba lớp chạy theo thứ tự vào rồi thoát ngược.
- Với `bad-3` ở biến thể audit ngoài cùng, authorization từ chối trước khi transaction và business chạy. Audit vẫn ghi được một lần từ chối và `audit exit` luôn xuất hiện.
- Với `authorize(audit(transaction(business)))`, authorization nằm **ngoài** audit. Khi bị deny ngay từ authorization, audit không chạy. Chỉ thay đổi thứ tự đã làm thay đổi hành vi quan sát được.
- Code `transaction` **không mở transaction thật**, chỉ mô phỏng lifecycle để diễn giải thứ tự. Một implementation production còn phải quản lý commit/rollback/connection, transaction nesting và lỗi khi commit; không được suy ra tính nguyên tử dữ liệu từ các dòng in.
- Kiểm tra `id.startsWith("ok-")` chỉ là **điều kiện demo**, hoàn toàn không phải chính sách bảo mật thực tế. Authorization thật phải dùng principal đã xác thực, action, resource và context tin cậy; không được suy quyền chỉ từ ID hoặc prefix do caller gửi.

Khi dùng engine AOP thực tế, bạn không nhất thiết gọi decorator thủ công, nhưng **hợp đồng thứ tự** cần mô tả kết quả tương tự và được xác minh bằng test tích hợp qua điểm chặn thật. Nếu engine không cho phép đảm bảo thứ tự như yêu cầu, phải điều chỉnh thiết kế hoặc hợp đồng thay vì giả vờ thứ tự không quan trọng.

## 6. Mẫu tài liệu dành cho một aspect

Một bản ghi gọn nhưng đủ khả năng kiểm chứng có thể dùng cấu trúc sau:

~~~yaml
aspectId: order-audit
purpose: "Ghi nhận kết quả các lệnh thay đổi đơn hàng"
owner: "Nhóm sở hữu kiểm soát audit"
criticality: required
version: 1

scope:
  operationIds: ["order.place", "order.cancel"]
  joinPointKind: "method execution tại command boundary"
  pointcutBinding: "annotation/manifest đã kiểm tra"
  exclusions: ["health probes", "pure utilities"]
  runtimeEntrypoints: ["command gateway", "job consumer"]

contract:
  allowedToShortCircuit: false
  originalInvocationCount: 1
  success: "ghi audit sau kết quả được xác nhận theo chính sách"
  error: "ghi loại lỗi an toàn, giữ nguyên lỗi gốc"
  cancellation: "ghi canceled theo hợp đồng vòng đời"
  timeout: "có timeout rõ cho sink"
  dataClassification: "không ghi token, secret hoặc payload nhạy cảm"
  auditSinkFailure: "theo chính sách fail-closed đã được duyệt"

order:
  outside: ["authorization", "transaction"]
  inside: ["metrics"] 
  rationale: "ghi lại cả các kết quả bị từ chối trước thực thi"
  verifiedSequence: "xác nhận trong integration test"

verification:
  coverageTest: "đối chiếu danh mục operation với pointcut match"
  orderTest: "success, deny, exception, retry, cancellation"
  performanceTest: "overhead tại tải đỉnh"
~~~

**Đây chỉ là mẫu YAML minh họa**, không phải cấu hình thực thi của một framework. Giá trị `outside/inside` cần định nghĩa một quy ước nhất quán; ví dụ này đòi hỏi nhóm kỹ thuật phải suy ra thứ tự cụ thể cùng cơ chế mapping theo engine. Nếu có nhiều lớp nằm ngoài/trong, hãy ghi **một chuỗi lồng nhau đầy đủ** và không chỉ hai danh sách rời.

Một mô tả như “audit chạy sau transaction” cũng chưa đủ khi cần biết nó ghi trước commit, sau commit, sau rollback hay sau kết quả được công bố. Nếu yêu cầu lưu audit chắc chắn đi cùng thay đổi dữ liệu, phải xác định mô hình độ bền và atomicity của sink; chỉ gắn một advice ở “sau” không tự tạo bảo đảm giao dịch.

### Các trường tài liệu không thể thiếu

1. **Tên và trách nhiệm:** phân biệt aspect quan sát, aspect thay đổi semantics và aspect kiểm soát bắt buộc.
2. **Owner và đường tới code/config:** biết người chịu trách nhiệm sửa pointcut và cập nhật test.
3. **Operation contract:** chính sách tác động tới request logic, lời gọi method, attempt hay event?
4. **Join point/kỹ thuật gắn:** method execution hay call; proxy, weaving hoặc instrumentation; giới hạn các loại method.
5. **Điều kiện chọn:** biểu thức thực tế, annotation, manifest, danh sách exclude và đường bypass có thể xảy ra.
6. **Hành vi qua mọi trạng thái:** success, failure, deny, timeout, retry, cache hit, cancel, async completion.
7. **Thứ tự/tương tác:** đầy đủ outer→inner, ai nắm transaction/context, ai đếm logical operation và attempt.
8. **Ngưỡng vận hành:** timeout, overhead, budget memory/queue, logging rate, sampling và degraded mode.
9. **Test chứng minh:** nơi kiểm tra coverage/ordering, các lệnh chạy và kết quả kỳ vọng.
10. **Lý do quyết định:** các phương án đã cân nhắc, rủi ro, lúc nào phải xem xét lại.

## 7. ADR: ghi quyết định thứ tự bằng lý do, không chỉ cấu hình

**Architecture Decision Record (ADR)** phù hợp để ghi các quyết định ảnh hưởng toàn codebase. Nó cần có:

- **Bối cảnh:** hệ thống có những aspect nào, điểm nào chịu transaction, audit, retry, cache, tracing; lỗi thực tế nào cần ngăn.
- **Yêu cầu:** không có side effect trước authorization; audit phải ghi cả deny; retry phải có giới hạn; metrics end-to-end; deadline.
- **Các phương án:** authorization ngoài/ trong transaction, audit ngoài/trong authorization, retry ngoài/trong transaction.
- **Quyết định cụ thể:** outer→inner và semantic trên nhánh success/error/deny/cancel.
- **Lập luận:** vì sao thứ tự đó đúng cho mục tiêu dữ liệu/bảo mật/quan sát.
- **Hệ quả:** chi phí, bất lợi, những trường hợp vẫn chưa được bảo vệ.
- **Kiểm chứng:** integration test hoặc trace minh chứng, và điều kiện cần review lại.

Ví dụ ADR rút gọn:

~~~markdown
# ADR: Audit bao ngoài Authorization

## Trạng thái
Accepted

## Bối cảnh
Mọi lời gọi vào cổng đặt hàng cần ghi nhận kết quả cho phép/từ chối.

## Quyết định
Chuỗi outer -> inner: Audit -> Authorization -> Transaction -> Business.
Deny bởi Authorization không mở Transaction và không chạy Business.
Audit phát một bản ghi kết quả deny với dữ liệu đã được làm sạch.

## Hệ quả
Có chi phí audit cho các lời gọi bị từ chối.
Lỗi audit sink được xử lý theo chính sách riêng đã được phê duyệt.

## Kiểm chứng
Integration test xác nhận sequence khi success, deny, business failure.
~~~

Đây là **một mẫu tài liệu ADR**, không phải mô tả về một hệ thống đã triển khai. ADR phải được liên kết từ operation catalog và từ code/config pointcut để người refactor có thể truy ngược lý do.

## 8. Quy tắc đặt tên metric và định nghĩa mẫu số cũng là hợp đồng

Khi metrics được lồng cùng retry hoặc cache, thứ tự ảnh hưởng trực tiếp số đếm:

- `requests_total`: đếm yêu cầu logic ở biên; một yêu cầu có thể tạo nhiều attempts.
- `attempts_total`: đếm từng lần thử.
- `denied_total`: đếm các lần bị từ chối trước khi nghiệp vụ chạy.
- `operation_duration_seconds`: cần biết bao gồm queue/retry/backoff hay chỉ một attempt.
- `transaction_duration_seconds`: chỉ thời gian transaction thực tế, không tự tương đương thời gian end-to-end.

Với một request bị lỗi hai lần, rồi thành công lần ba, nếu metrics ở ngoài retry, nó có thể ghi một logical request thành công; metrics ở trong retry có thể ghi ba attempts với hai lỗi. Cả hai bộ số đều có thể đúng theo định nghĩa, nhưng không được trộn mẫu số của chúng.

**Tài liệu cần định nghĩa đơn vị đo, điểm bắt đầu/kết thúc, loại lỗi, cách xử lý timeout/cancel và cách aggregating qua nhiều instance.** Không nên dùng một tên metric cũ khi thay đổi semantics của advice; cân nhắc version hoặc tên mới để dashboard và cảnh báo không im lặng đổi ý nghĩa.

## 9. Hợp đồng cho lời gọi bất đồng bộ và stream

### 9.1 Future/CompletionStage

Một around advice bao quanh method trả về `CompletionStage<Result>` có thể kết thúc ngay lúc method trả stage, dù I/O và kết quả thật sẽ tới sau. Cần ghi rõ:

- **Giới hạn quan sát:** đo thời gian phương thức trả stage hay thời gian stage hoàn tất?
- **Thời điểm kết thúc:** success/exceptional completion/cancellation/timeout, có đúng một lần terminal không?
- **Resource ownership:** transaction, semaphore permit, trace span hoặc context scope được giải phóng ở đâu?
- **Failure mapping:** exception tại lúc tạo stage khác exceptional completion về sau.
- **Callback affinity:** callback có thể chạy trên thread hoàn tất stage; tránh I/O chặn hoặc ném lỗi telemetry làm thay đổi kết quả.
- **Context propagation:** `ThreadLocal` trên thread gọi không tự đi qua executor.

Không thể tự động bảo đảm một transaction nằm bên ngoài lời gọi tạo future sẽ bao trùm toàn bộ việc xử lý bất đồng bộ. Nếu cần transaction cho phần xử lý thực tế, chọn boundary ở nơi thực hiện thao tác dữ liệu và xác minh bằng test.

### 9.2 Publisher và luồng sự kiện

Một publisher có thể chưa chạy khi object được tạo, sau đó có nhiều subscription và nhiều phần tử. Tài liệu phải nói rõ **một operation** đang được tính theo lần tạo publisher, lần subscribe, từng `onNext` hay toàn vòng đời subscription.

Nếu advice can thiệp vào callback, phải bảo toàn số `request(n)`, `cancel`, tín hiệu terminal và thứ tự theo hợp đồng của giao thức. Một advice logging không được tự `subscribe` để “xem dữ liệu”, thay đổi demand hoặc tạo queue vô hạn rồi làm hỏng backpressure. Đối với nguồn dài vô hạn, không thể giả định “sẽ có onComplete” để đóng mọi tài nguyên.

### 9.3 Cancellation và timeout

Cần phân biệt **trạng thái đại diện** với **công việc nền thật sự đã dừng**. Ví dụ hủy một `CompletableFuture` không đảm bảo mọi I/O đã bị ngắt. Nếu một advice trả permit ngay khi future chuyển sang canceled nhưng job nền vẫn sử dụng tài nguyên, concurrency limiter có thể nhận thêm công việc quá capacity thực. Chính sách phải xác định “in-flight” theo tài nguyên thực tế và có cơ chế cleanup phù hợp.

## 10. Chi phí quan sát và giới hạn tài nguyên là một phần tài liệu

Thứ tự advice cũng thay đổi chi phí và hành vi khi quá tải:

| Aspect / vị trí | Ảnh hưởng có thể xảy ra |
| --- | --- |
| Tracing outer | Bao cả authorization, chờ retry và transaction; span tồn tại lâu hơn |
| Metrics inner | Ít đo overhead bên ngoài; có thể chỉ thấy attempts được phép |
| Audit outer | Ghi cả deny/cache hit nếu cơ chế bên trong có thể short-circuit |
| Rate limit outer | Chặn trước khi tạo tài nguyên tốn kém |
| Rate limit inner | Một lớp outer vẫn chạy, thậm chí tạo side effect trước khi bị từ chối |
| Retry outer | Có thể tạo nhiều lần vào các aspect bên trong |
| Transaction outer | Giữ transaction qua retry/backoff nếu thiết kế như vậy, có thể làm tăng lock time |

Không kết luận “outer luôn tốt hơn”: lựa chọn phải bám vào contract. Mỗi aspect có overhead; điểm cắt rộng còn có thể instrument thư viện metrics/logging và dẫn đến recursion. Tài liệu cần ghi scope exclude và cách kiểm soát cấp phát bộ nhớ, cardinality label, queue và I/O.

Đối với audit/logging không đồng bộ, định nghĩa queue capacity, timeout, retry, trường hợp collector lỗi và chính sách mất bản ghi. Nếu audit bắt buộc, một hàng đợi vô hạn không phải giải pháp bảo đảm độ bền; nó có thể dẫn tới OOM. Nếu telemetry chỉ phục vụ vận hành, có thể chấp nhận sampling hoặc bỏ log theo chính sách rõ.

## 11. Bản đồ phụ thuộc và ranh giới trách nhiệm

Một module có thể không import aspect nhưng vẫn trông chờ hành vi từ aspect. Tài liệu kiến trúc nên thể hiện các quan hệ như:

~~~mermaid
flowchart TD
  A[Entrypoint / command gateway] --> B[Chuỗi advice]
  B --> C[Business operation]
  C --> D[Repository / resource]
  E[Operation catalog] --> B
  F[Policy và hợp đồng] --> B
  G[ADR thứ tự] --> B
  H[Integration tests] --> A
  H --> B
  H --> D
~~~

Các nhãn ở sơ đồ biểu diễn **trách nhiệm**, không áp đặt một framework cụ thể. **Operation catalog** khai báo những gì cần bảo vệ; **policy** nói hành vi mong đợi; **ADR** giải thích thứ tự; **test** chứng minh điểm chặn hiện thực đúng; **resource boundary** giữ các bất biến sống còn.

Phân chia owner cũng cần rõ:

- Nhóm nghiệp vụ sở hữu ý nghĩa operation và thông tin tài nguyên.
- Nhóm hạ tầng AOP sở hữu cơ chế gắn pointcut, vòng đời advice và thứ tự thực thi.
- Nhóm bảo mật/dữ liệu sở hữu chính sách quyền, yêu cầu audit, transaction, độ nhất quán và các biên bảo vệ.
- Nhóm vận hành sở hữu metric/SLO và ngân sách chi phí; thay đổi semantics cần được phối hợp để tránh phá dashboard.

Đây là cách giảm “không ai biết ai sửa pointcut” khi một thay đổi nhỏ tác động nhiều module.

## 12. Kiểm thử tài liệu bằng hành vi thực thi

Một tài liệu chỉ có ý nghĩa nếu các điểm quan trọng được **kiểm chứng tự động**. Cần ít nhất ba lớp:

### 12.1 Kiểm tra coverage tĩnh hoặc khi khởi động

- Liệt kê operation yêu cầu advice và tập pointcut thực tế match.
- Phát hiện phương thức mới không được phân loại, binding thiếu, pointcut đã cũ.
- Kiểm tra overload, annotation trên interface/implementation, bridge/default method, static/final/private nếu engine liên quan.
- Kiểm tra exclude để ngăn chọn nhầm telemetry/runtime infrastructure.
- Phát hiện đường bypass được biết trước và kiểm soát entrypoint.

Khi một policy bắt buộc bị thiếu, CI/startup nên thất bại hoặc xử lý fail-closed theo kiến trúc, chứ không chỉ để một dòng cảnh báo khó thấy.

### 12.2 Integration test thứ tự và semantics

Test phải đi qua đường gọi như production, không chỉ gọi trực tiếp đối tượng nghiệp vụ. Dùng probe ghi sequence để so sánh với ADR:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Thành công | Thứ tự enter/exit và ownership đúng |
| Authorization deny | Không có side effect nghiệp vụ; audit có/không theo contract |
| Exception nghiệp vụ | Rollback/translation, audit/metrics và lỗi gốc đúng |
| Retry hai lần rồi thành công | Số transaction, số attempt, số audit và metric đúng |
| Cache hit | Những advice cần chạy vẫn được thực thi |
| Timeout/cancel | Tài nguyên và context được giải phóng đúng lifecycle |
| Gọi target trực tiếp hoặc self-invocation | Phát hiện bypass, hoặc chứng minh boundary không cho phép |
| Future hoàn tất thất bại về sau | Không ghi “success” ngay khi trả stage |
| Concurrent calls | Không rò context, không dùng chung state sai |
| Đổi thứ tự aspect | Test phát hiện khác biệt với sequence đã quyết định |

### 12.3 Regression khi refactor

Chạy kiểm tra sau các thay đổi sau: đổi tên method, di chuyển package, thêm overload, sửa annotation, thay interface, đổi proxy wiring, chuyển sync→async hoặc thay precedence. Diff tập join point và tập operation đã instrument phải được xem như một phần review. Test bảo mật/transaction cần kiểm tra **lời gọi thực sự**, không chỉ việc matcher nhìn thấy tên trên metadata.

Không có test đơn lẻ nào thay thế được cả ba tầng. Ví dụ unit test business có thể pass ngay cả khi audit advice không được gắn; integration test chỉ dùng case thành công có thể bỏ sót sai thứ tự xử lý deny/rollback.

## 13. Quy trình duy trì tài liệu cùng mã

Một quy trình dễ áp dụng:

1. **Khi tạo operation:** đặt ID nghiệp vụ, phân loại yêu cầu audit, quyền, transaction, retry, metrics và xác định chủ sở hữu.
2. **Khi khai báo pointcut:** nêu rõ join point model, biểu thức/mapping, exclusions, engine và giới hạn kỹ thuật.
3. **Khi triển khai advice:** viết hợp đồng kết quả, lỗi, side effects, số lần gọi gốc, cleanup và async semantics.
4. **Khi kết hợp aspect:** ghi chuỗi outer→inner và sequence cho các nhánh quan trọng, kèm ADR lý do.
5. **Khi viết test:** bao phủ operation phải match, không được match, nhánh deny/error, thứ tự và đường bypass.
6. **Khi refactor:** cập nhật operation catalog, pointcut diff và ADR nếu thứ tự/hợp đồng thay đổi.
7. **Khi triển khai:** đối chiếu số advice invocation, metric và dấu hiệu thiếu coverage, nhưng không dùng dashboard thay cho test.
8. **Khi đánh giá sự cố:** truy ngược operation → pointcut → advice contract → order ADR → test và resource boundary; ghi nhận nguyên nhân và sửa cơ chế phát hiện.

Đối với tài liệu dài hạn, nên đặt catalog/ADR cạnh code hoặc trong kho tài liệu có version, liên kết rõ commit/build và có người review. Mọi thay đổi pointcut hoặc thứ tự cần được coi như **thay đổi hành vi runtime**, kể cả khi không sửa dòng nào trong business method.

## 14. Checklist trước khi phê duyệt thay đổi AOP

- [ ] Xác định mục tiêu nghiệp vụ và mức độ bắt buộc của mỗi aspect.
- [ ] Danh mục operation và tập pointcut match được cập nhật, có ghi những trường hợp exclude.
- [ ] Cơ chế proxy/weaving và đường bypass được mô tả, kiểm tra bằng đường gọi thật.
- [ ] Hợp đồng advice ghi rõ có được short-circuit, retry, thay kết quả/lỗi hoặc sinh side effect không.
- [ ] Cách bắt đầu/kết thúc của transaction, metric, span, audit và concurrency slot được xác định.
- [ ] Thứ tự outer→inner và trình tự success/deny/error/cancel được viết rõ.
- [ ] Đã phân biệt logical operation với attempt, cache hit, method invocation và subscription.
- [ ] Có tài liệu riêng cho future/stream nếu hệ thống có ranh giới bất đồng bộ.
- [ ] Không có quyền mặc định khi thiếu annotation/policy cho thao tác nhạy cảm.
- [ ] Unit, integration, coverage regression và performance test phù hợp đã được chạy.
- [ ] ADR giải thích tại sao chọn thứ tự, hậu quả và điều kiện cần xem xét lại.
- [ ] Owner và nguồn sự thật của hợp đồng đã được xác định.

## 15. Những hiểu lầm phổ biến

**“Có pointcut là đã có tài liệu phạm vi.”** Không đủ: biểu thức khớp chỉ diễn tả điều kiện chọn, không nêu danh sách nghiệp vụ **phải được chọn** hay đường runtime có thể bỏ qua.

**“AOP loại bỏ coupling.”** AOP giảm các lời gọi lặp trong business code nhưng chuyển một phần phụ thuộc sang pointcut, cấu hình và semantics runtime. Coupling đó cần được thể hiện trong tài liệu và test.

**“Thứ tự advice là chi tiết triển khai.”** Không đúng khi nó quyết định audit có thấy deny, transaction có bao retry, metrics đếm request hay attempt, hoặc authorization xảy ra trước side effect.

**“Một bảng ghi A trước B là đủ.”** Thiếu ngữ nghĩa outside/inside, exit path, exception path và cách engine ánh xạ order. Hãy ghi chuỗi lồng nhau hoàn chỉnh cùng trace kỳ vọng.

**“Around advice chỉ quan sát.”** Nó có thể short-circuit, gọi nhiều lần, thay đổi kết quả/lỗi, quản lý tài nguyên và context. Từng khả năng cần hợp đồng rõ.

**“Unit test business đã đủ kiểm tra AOP.”** Lời gọi trực tiếp vào target có thể bỏ qua advice. Cần integration test qua entrypoint thật.

**“Thêm annotation là chắc chắn đã áp dụng.”** Annotation có thể bị quên hoặc không được engine nhìn thấy ở vị trí định nghĩa. Cần so sánh operation bắt buộc với coverage thực tế.

**“Đã bắt được lời gọi async tức đã đo được toàn thời gian.”** Method có thể trả stage/publisher trước khi công việc hoàn tất. Cần ghi rõ điểm đo theo vòng đời.

**“Audit và metrics đều là logging, lỗi sink thì bỏ qua hết.”** Yêu cầu vận hành và yêu cầu tuân thủ có thể rất khác nhau. Tài liệu phải định nghĩa cách phản ứng với lỗi sink theo từng contract.

## 16. Kết luận

Đối với AOP, **phạm vi – hợp đồng – thứ tự** là ba phần của cùng một quyết định kiến trúc. Phạm vi cho biết *đường thực thi nào được can thiệp*; hợp đồng cho biết *advice được phép làm gì và phải bảo toàn điều gì*; thứ tự cho biết *các hành vi tương tác như thế nào ở cả nhánh vào, nhánh ra, lỗi và hủy*. Tài liệu tốt cần có operation catalog, pointcut coverage, advice contract, chuỗi outer→inner, ADR giải thích lựa chọn, và test chứng minh trên đường gọi thật. Khi các phần này được quản lý cùng code và cấu hình, việc đổi tên, refactor, thêm aspect hoặc chuyển sang bất đồng bộ sẽ ít có nguy cơ làm thay đổi hành vi trong im lặng.