# Kiểm thử hành vi tổng thể thay vì chỉ từng advice

## 1. Vấn đề: mọi advice đều đúng riêng lẻ, hệ thống vẫn có thể sai

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP)**, **pointcut** chọn *join point* có thể can thiệp và **advice** là hành vi bổ sung chạy tại điểm đã chọn. Khi nhiều aspect phối hợp trên một lời gọi, chúng tạo nên một tổ hợp có thể chứa **authorization, caching, retry, tracing, audit, metrics** hoặc xử lý ngoại lệ.

Kiểm thử riêng lẻ một hàm `authorize()` chứng minh nó có thể từ chối người dùng không được phép. Kiểm thử riêng `cache()` chứng minh nó trả lại giá trị đã lưu. Kiểm thử riêng `audit()` chứng minh nó ghi đúng sự kiện khi nhận kết quả. **Không kiểm thử nào trong ba điều đó chứng minh cấu trúc kết hợp đã an toàn**.

Xét hai chuỗi:

~~~text
ĐÚNG THEO CHÍNH SÁCH MINH HỌA:
Caller -> AUTH -> CACHE -> AUDIT -> BUSINESS

NGUY HIỂM NẾU CACHE TRẢ KẾT QUẢ TRƯỚC KHI KIỂM QUYỀN:
Caller -> CACHE -> AUTH -> AUDIT -> BUSINESS
~~~

Ở chuỗi thứ hai, **cache hit** có thể trả trực tiếp cho caller mà **không đi qua AUTH**. Mọi unit test riêng lẻ của `AUTH` và `CACHE` vẫn có thể PASS, nhưng hợp đồng end-to-end đã thất bại.

Tư duy của bài:

> Đối tượng cần kiểm thử không chỉ là từng advice, mà là **hành vi toàn bộ lời gọi qua đường can thiệp thật**, bao gồm thứ tự áp dụng, result/exception caller nhìn thấy, số lần nghiệp vụ chạy, side effects, đường bị bỏ qua và khả năng xảy ra lỗi.

Đây là chủ đề trong ngữ cảnh **phối hợp nhiều aspect**, không phải lời kêu gọi bỏ unit test. Unit test vẫn cần thiết để khoanh vùng lỗi trong từng thành phần; **integration/behavior tests bổ sung** để chứng minh các thành phần hợp tác đúng.

## 2. Phân biệt các lớp kiểm thử

| Lớp kiểm thử | Đối tượng xác nhận | Điều chưa được chứng minh |
| --- | --- | --- |
| **Unit test advice** | Logic nội bộ của một advice khi được cấp context/result giả lập | Advice có được engine gọi tại join point thật không? |
| **Pointcut matching test** | Bộ chọn match đúng/không match những signature cụ thể | Đường gọi runtime có đi qua proxy/weaver không? |
| **Integration test AOP** | Target + nhiều advice + proxy/weaving + thứ tự và kết quả | Toàn hệ thống nhiều service/external components có giống production không? |
| **End-to-end/system test** | Một workflow hoàn chỉnh qua entry point đáng tin, side effects và kết quả quan sát | Chưa chắc cô lập được lỗi từ từng advice |
| **Concurrency/stress test** | Tính ổn định khi nhiều lời gọi, retry, timeout và race | Không thay thế được các assertion ngữ nghĩa ở từng ca |
| **Deployment/compatibility test** | Artifact cuối, agent, classloader, JVM flags, policy version | Không chứng minh toàn bộ dữ liệu nghiệp vụ sản xuất |

Một test lý tưởng không cố gộp mọi việc thành một ca khổng lồ. Tạo **nhiều ca độc lập**, mỗi ca xác nhận một bất biến tổng thể, rồi thêm vài kịch bản end-to-end có ràng buộc thực tế.

### 2.1. Unit test quan trọng nhưng không đủ

Ví dụ, unit test `AuditAdvice.afterReturning("receipt:A")` có thể thành công. Nhưng khi chạy thật:

- Điểm can thiệp có thể **không khớp** method implementation.
- Caller có thể giữ **target gốc** thay vì proxy.
- Advice nằm **sau một cache short-circuit**, không chạy trên cache hit.
- Retry có thể khiến audit chạy **mỗi attempt** thay vì một lần trên toàn request.
- Advice bên trong có thể biến đổi kết quả trước khi audit đọc.
- Một advice khác ném exception sau target return, khiến caller thấy lỗi dù audit đã ghi success.

Do đó cần thử **cả đường invocation thật**, không chỉ gọi trực tiếp method của advice.

## 3. Viết “hợp đồng tổng thể” trước khi viết testcase

Trước khi kiểm thử, xác định các yêu cầu bằng câu có thể đo được. Với dịch vụ xử lý đơn hàng:

1. **Mọi caller chưa có quyền đều bị từ chối**, kể cả khi cache đã có dữ liệu.
2. **Mỗi cache miss hợp lệ** gọi target đúng một lần, nếu không có retry.
3. **Một cache hit** trả kết quả phù hợp mà không gọi lại target.
4. **Ngoại lệ nghiệp vụ** không bị một advice quan sát tự đổi thành thành công.
5. **Kết quả thất bại không được cache** nếu đó là chính sách.
6. **Audit per-execution** chỉ xảy ra khi target thật chạy; **audit per-request** có thể xảy ra dù cache hit — đó là hai hợp đồng khác nhau.
7. **Thứ tự event** phải nhất quán với precedence đã được công bố.
8. **Advice chỉ quan sát** phải giữ nguyên result, exception và số lần gọi target.
9. **Các join point không được chọn** không có side effect từ aspect.
10. **Cấu hình triển khai** phải thật sự kích hoạt đúng chain dự kiến.

Một test có thể kiểm tra **kết quả caller nhận**, **trace events** và **business execution counter**. Cả ba cung cấp những bằng chứng khác nhau. Thấy đúng kết quả nhưng target bị gọi hai lần có thể vẫn sai (ví dụ thao tác trừ tiền). Có đúng số target calls nhưng audit sinh hai events cũng có thể sai.

### 3.1. Đơn vị nào được đếm?

Phải phân biệt:

| Đơn vị | Ví dụ |
| --- | --- |
| **Logical request** | Một yêu cầu xử lý đơn hàng từ người dùng |
| **Method invocation** | Một lần gọi qua API boundary |
| **Target execution** | Một lần thân phương thức nghiệp vụ thực sự chạy |
| **Attempt** | Một lượt thử trong retry |
| **Advice entry** | Một lần một handler/advice cụ thể được vào |
| **Event emission** | Một event audit/metrics được phát đi |
| **Event delivery** | Một lần event đến consumer/sink |

`requestCount=1` không đồng nghĩa `targetExecutionCount=1` khi có retry; `auditCount=1` không đồng nghĩa `eventDeliveredCount=1` nếu queue redeliver.

Đặt tên biến test theo đúng đơn vị: `businessCalls`, `attempts`, `auditEntries`, `logicalRequests`, tránh biến `count` mơ hồ.

## 4. Điểm nguy hiểm nhất: thứ tự advice đổi semantics

Giả sử hai handler đều đúng khi đứng riêng:

~~~text
AUTH:
  nếu actor không có quyền -> ném SecurityException
  nếu có quyền -> proceed()

CACHE:
  cache hit -> trả kết quả ngay
  cache miss -> proceed() rồi lưu kết quả trả bình thường
~~~

Hai cách lắp chain:

~~~text
Safe chain:
AUTH(
    CACHE(
        BUSINESS
    )
)

Unsafe chain:
CACHE(
    AUTH(
        BUSINESS
    )
)
~~~

Với cache hit đã tồn tại, ở chuỗi unsafe, `CACHE` có thể return mà không gọi `AUTH`. Đây là một **lỗi bảo mật do composition**, không phải một bug của từng hàm handler.

### 4.1. Test phải có trạng thái chuẩn bị phù hợp

Một testcase chỉ gửi request chưa có cache entry sẽ đi qua `CACHE miss → AUTH`, làm cả hai thứ tự trông có vẻ an toàn. Để lộ lỗi, phải:

1. Dùng một actor có quyền để tạo cache entry.
2. Gửi lại cùng resource ID bằng actor không có quyền.
3. Assert request thứ hai bị từ chối **kể cả khi cache đã có giá trị**.
4. Đếm target executions và audit events để biết cache đã short-circuit ở đâu.

Đây là ví dụ của **state-dependent integration test**: trạng thái trước ca kiểm thử là một phần bắt buộc của đặc tả.

### 4.2. Có cách thiết kế cache ngoài authorization an toàn không?

Có thể trong một số hệ thống, nếu cache boundary **đã tích hợp bảo vệ tương đương**, cache key bao gồm principal/permission scope, hoặc caller không thể truy cập resource trái quyền qua entry point ấy. Nhưng không được giả định tính an toàn chỉ vì “cache hit nhanh”. Mọi cách thiết kế phải chứng minh **authorization invariant** bằng test, bao gồm thay đổi quyền, hết hạn quyền, key collision, invalidate và đa tenant.

Với bài minh họa, chọn `AUTH` ngoài `CACHE` để dễ thấy bảo đảm “mỗi request phải qua authorization trước khi được đáp ứng”.

## 5. Around advice lồng nhau: assert cả đường vào và đường rút ra

Một chuỗi `A(B(C(target)))` bình thường đi:

~~~text
A.enter
B.enter
C.enter
TARGET
C.returning
B.returning
A.returning
CALLER
~~~

Đây là **thứ tự event** với giả định mỗi layer `proceed()` đúng một lần và target return bình thường. Lớp trong hoàn tất trước lớp ngoài vì outer đang chờ `proceed`.

Khi có ngoại lệ:

~~~text
A.enter
B.enter
C.enter
TARGET throws
C.throwing
C.finally
B.throwing
B.finally
A.throwing
A.finally
CALLER sees original exception
~~~

Đây là sơ đồ khái niệm; event nào thực sự xuất hiện phụ thuộc code và loại advice. Ví dụ `after-returning` không chạy trên exceptional completion, còn `finally` chạy khi rời scope theo ngữ nghĩa Java thông thường.

**Test đúng cần khẳng định cả thứ tự và loại outcome**. Không chỉ kiểm tra “có event A và B” vì hai event đúng nhưng thứ tự sai có thể thay đổi bảo mật, caching, result transformation hoặc transaction.

### 5.1. Asserting event list

Một cách thuận tiện khi kiểm thử đơn luồng là ghi sự kiện vào `List<String> events` và so với danh sách kỳ vọng:

~~~text
expected = [
  "AUTH allow alice",
  "CACHE miss O1",
  "AUDIT before O1",
  "BUSINESS O1",
  "AUDIT success O1"
]
~~~

Không nên chỉ assert `events.size()==5`; một chain sai vẫn có thể in đúng 5 events nhưng thứ tự hoặc loại event sai. Trong môi trường đồng thời, cần gắn invocation/correlation ID để không yêu cầu **mọi request toàn hệ thống** có thứ tự tuyệt đối.

## 6. Kết quả trả về và ngoại lệ: bảo toàn hợp đồng caller

Những tình huống dễ bị bỏ sót:

- **Reference return `null`:** method có thể hoàn tất bình thường và trả `null`. Không tự coi là exceptional completion.
- **`void`:** không có result object nghiệp vụ nhưng vẫn có thể hoàn tất bình thường.
- **Primitive `int`/`boolean`:** nếu around adapter trả `null` không tương thích, việc unboxing có thể thất bại.
- **`Optional.empty()`:** một object container rỗng, không phải thiếu normal return.
- **`Result.failure(...)`:** có thể là normal Java return nhưng biểu thị thất bại miền.
- **Target exception:** advice quan sát không tự thay bằng lỗi mới, trừ khi hợp đồng ghi rõ.
- **Advice exception:** target có thể đã chạy thành công nhưng caller nhận lỗi audit/metrics; cần nhận diện nguồn.
- **Fallback:** inner advice bắt lỗi rồi trả một result hợp lệ, khiến outer advice nhìn **normal completion**.

Do đó, testcase cần assert **kiểu và thông điệp ngoại lệ** khi hợp đồng yêu cầu, không chỉ `assertThrows(Exception.class)` mơ hồ. Với logic xử lý lỗi có chủ đích, cần assert policy chuyển đổi và xác định ranh giới nào nhận fallback.

### 6.1. Những phép biến đổi result không giao hoán

Giả sử `Normalize` và `Encode` cùng là around advices. Kết quả của:

~~~text
Encode(Normalize(result))
~~~

không nhất thiết giống:

~~~text
Normalize(Encode(result))
~~~

Vì vậy test phải kiểm **giá trị cuối caller nhìn thấy**, không chỉ test từng hàm transform. Với object mutable, một advice trả cùng reference nhưng sửa fields cũng là thay đổi trạng thái.

## 7. Cache, retry và short-circuit: đếm execution chính xác

### 7.1. Cache hit

Một cache hit có thể không gọi `proceed` tới lớp trong; test phải assert:

- Có result đúng.
- Những advice **ngoài cache** vẫn có thể chạy.
- Những advice **trong cache** không chạy nếu bị short-circuit.
- Target execution count không tăng.
- Không bỏ qua một chính sách bắt buộc ngoài ý định.

Một assertion như “target được gọi ít nhất một lần” quá yếu; với cache hit lần thứ hai, kỳ vọng thường là **không tăng**.

### 7.2. Retry

Với retry có hai attempts:

~~~text
Outer timing entry: 1
Inner target executions: 2
Inner audit entries: có thể 2
Outer timing completion: 1
~~~

Điều này không nhất thiết là double weaving. Khi test cần biết **retry policy**, những loại lỗi nào được retry, tối đa bao nhiêu lần, có backoff hay không, và side effects có idempotent không.

Không test retry bằng cách mặc định mọi exception đều được thử lại: một `SecurityException` do từ chối quyền thường không nên biến thành lỗi được retry nhiều lần. Thêm test **denial does not retry**.

### 7.3. Multiple proceeds

Trong một around advice, gọi `proceed()` hai lần có thể khiến target chạy hai lần. Nếu đó không phải retry/fan-out có chủ đích, đây là lỗi nguy hiểm với thao tác có side effects.

Test không chỉ assert output cuối; phải assert **businessCalls** và những side effects có thể đo. Nếu giao dịch tạo hai bản ghi rồi trả result giống nhau, chỉ test return value sẽ bỏ sót lỗi.

### 7.4. Audit per-attempt khác audit per-request

Nếu audit phải tạo một event cho **mỗi request**, nên có test khi cache hit và khi retry. Nếu audit phải ghi **mỗi target execution**, test có thể dự kiến event bằng số attempts. Trước khi viết assertion “audit phải xuất hiện đúng một lần”, cần xác định đơn vị đo.

## 8. Ví dụ Java 17 chạy độc lập và có assertion tự động

Chương trình sau dựng một interceptor chain bằng Java thuần, **không dùng một AOP framework cụ thể và không tự nhận là bytecode weaving**. Nó giúp kiểm chứng một bài toán phối hợp nhiều aspect:

- `authorization`: chỉ actor `alice` được phép.
- `caching`: cache theo `orderId`, lưu duy nhất các kết quả return bình thường.
- `auditing`: ghi before/success/failure cho các lời gọi đi qua nó.
- `business`: thực thi logic chính, có biến đếm độc lập và nhánh exception.
- `run()`: xây chain theo thứ tự **ngoài → trong** bằng cách duyệt danh sách từ cuối.
- `expectEvents`: so sánh toàn bộ chuỗi event **theo đúng thứ tự**, không chỉ số lượng.

Các testcase bao gồm **authorized cache miss**, **authorized cache hit**, **unauthorized cache hit bị từ chối**, **business exception không bị cache**, và một test **cố ý lắp thứ tự unsafe để chứng minh lỗ hổng**. Test unsafe là một phép đối chứng trong môi trường cô lập, **không phải thiết kế sản xuất được đề xuất**.

Tạo file `AopIntegrationTestDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class AopIntegrationTestDemo {
    record Request(String actor, String orderId) {}

    @FunctionalInterface
    interface Proceed {
        String call() throws Exception;
    }

    @FunctionalInterface
    interface Around {
        String apply(Request request, Proceed next) throws Exception;
    }

    @FunctionalInterface
    interface Business {
        String execute(Request request) throws Exception;
    }

    static final class Harness {
        final List<String> events = new ArrayList<>();
        final Map<String, String> cache = new HashMap<>();
        int businessCalls;

        final Around authorization = (req, next) -> {
            if (!"alice".equals(req.actor())) {
                events.add("AUTH deny " + req.actor());
                throw new SecurityException("access denied");
            }
            events.add("AUTH allow " + req.actor());
            return next.call();
        };

        final Around caching = (req, next) -> {
            String cached = cache.get(req.orderId());
            if (cached != null) {
                events.add("CACHE hit " + req.orderId());
                return cached;
            }
            events.add("CACHE miss " + req.orderId());
            String result = next.call();
            cache.put(req.orderId(), result);
            return result;
        };

        final Around auditing = (req, next) -> {
            events.add("AUDIT before " + req.orderId());
            try {
                String result = next.call();
                events.add("AUDIT success " + req.orderId());
                return result;
            } catch (Exception ex) {
                events.add("AUDIT failure " + ex.getClass().getSimpleName());
                throw ex;
            }
        };

        final Business business = req -> {
            businessCalls++;
            events.add("BUSINESS " + req.orderId());
            if ("bad".equals(req.orderId())) {
                throw new IllegalStateException("storage unavailable");
            }
            return "receipt:" + req.orderId();
        };

        String run(Request request, List<Around> outsideToInside)
                throws Exception {
            Proceed chain = () -> business.execute(request);
            for (int i = outsideToInside.size() - 1; i >= 0; i--) {
                Around layer = outsideToInside.get(i);
                Proceed inside = chain;
                chain = () -> layer.apply(request, inside);
            }
            return chain.call();
        }

        void expectEvents(String label, String... expected) {
            List<String> want = List.of(expected);
            if (!events.equals(want)) {
                throw new AssertionError(label + " expected " + want
                        + " but was " + events);
            }
            events.clear();
            System.out.println("PASS " + label);
        }
    }

    static void equal(Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
    }

    public static void main(String[] args) throws Exception {
        Harness h = new Harness();
        List<Around> safe = List.of(h.authorization, h.caching, h.auditing);
        Request aliceA = new Request("alice", "O1");

        equal("receipt:O1", h.run(aliceA, safe));
        h.expectEvents("authorized miss",
                "AUTH allow alice", "CACHE miss O1", "AUDIT before O1",
                "BUSINESS O1", "AUDIT success O1");
        equal(1, h.businessCalls);

        equal("receipt:O1", h.run(aliceA, safe));
        h.expectEvents("authorized hit", "AUTH allow alice", "CACHE hit O1");
        equal(1, h.businessCalls);

        try {
            h.run(new Request("blocked", "O1"), safe);
            throw new AssertionError("expected SecurityException");
        } catch (SecurityException ex) {
            equal("access denied", ex.getMessage());
        }
        h.expectEvents("unauthorized blocked", "AUTH deny blocked");
        equal(1, h.businessCalls);

        for (int attempt = 0; attempt < 2; attempt++) {
            try {
                h.run(new Request("alice", "bad"), safe);
                throw new AssertionError("expected IllegalStateException");
            } catch (IllegalStateException ex) {
                equal("storage unavailable", ex.getMessage());
            }
            h.expectEvents("failure attempt " + (attempt + 1),
                    "AUTH allow alice", "CACHE miss bad",
                    "AUDIT before bad", "BUSINESS bad",
                    "AUDIT failure IllegalStateException");
        }
        equal(false, h.cache.containsKey("bad"));
        equal(3, h.businessCalls);

        List<Around> unsafe = List.of(h.caching, h.authorization, h.auditing);
        equal("receipt:O1", h.run(new Request("blocked", "O1"), unsafe));
        h.expectEvents("unsafe ordering exposed", "CACHE hit O1");
        equal(3, h.businessCalls);
        System.out.println("FINAL businessCalls=3 cachedOrders=" + h.cache.size());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 AopIntegrationTestDemo.java
java AopIntegrationTestDemo
~~~

Đầu ra chính xác đã xác minh bằng chạy thực:

~~~text
PASS authorized miss
PASS authorized hit
PASS unauthorized blocked
PASS failure attempt 1
PASS failure attempt 2
PASS unsafe ordering exposed
FINAL businessCalls=3 cachedOrders=1
~~~

### 8.1. Vì sao `authorized miss` là một integration test?

Ca đầu không chỉ thử một advice. Nó thực thi toàn chuỗi `AUTH → CACHE → AUDIT → BUSINESS` rồi đồng thời xác nhận:

- Actor hợp lệ được phép.
- Cache chưa có dữ liệu nên là miss.
- Audit before chạy **trước** business.
- Business chạy một lần.
- Audit success chạy **sau** business.
- Caller nhận `receipt:O1`.

Tất cả sự kiện phải đúng thứ tự. Nếu `audit` được lắp sai vị trí, có thể kết quả caller vẫn giống nhưng event list sẽ khác và test báo lỗi.

### 8.2. `authorized hit` bảo vệ số lần thực thi thật

Ca hai gửi lại cùng `O1`, kỳ vọng:

~~~text
AUTH allow alice
CACHE hit O1
~~~

Không có `AUDIT before` hoặc `BUSINESS` do audit nằm **bên trong cache**. `businessCalls` giữ nguyên bằng `1`. Điều này đúng theo policy của demo: audit là **per-target-execution**, không phải audit mọi API request.

Nếu yêu cầu audit mỗi lần caller yêu cầu dữ liệu, phải đổi vị trí/thiết kế audit và **cập nhật expected events tương ứng**; không đánh giá logic cũ bằng một hợp đồng mới.

### 8.3. `unauthorized blocked` kể cả khi cache đã có giá trị

Ca thứ ba gửi `actor="blocked"` và cùng `orderId="O1"`. Vì `AUTH` đứng ngoài cache, lời gọi bị từ chối ngay. Test xác nhận đúng `SecurityException`, đúng thông điệp, chỉ có `AUTH deny blocked`, không có `CACHE hit`, `AUDIT` hoặc `BUSINESS`.

Đây là **hợp đồng end-to-end về bảo mật**, không thể chứng minh chỉ bằng unit test `authorization` với một `next` giả.

### 8.4. Hai lần `bad` vẫn là cache miss

Target `business` với `orderId="bad"` ném `IllegalStateException`. `AUDIT` ghi failure rồi ném lại; `CACHE` không nhận một normal result để `put`. Vì thế thử lại `bad` lần thứ hai vẫn là **CACHE miss**, và `businessCalls` từ `1` lên `3` sau hai attempts.

Điều được test là **hai lần gọi độc lập** có cùng input lỗi; đây **không phải** một retry advice tự động. Nếu ứng dụng dùng around retry, cần test policy số attempts, backoff và loại lỗi được retry riêng.

### 8.5. `unsafe ordering exposed` cố ý xác nhận một lỗi thiết kế

Ca cuối đảo thứ tự sang:

~~~text
CACHE -> AUTH -> AUDIT -> BUSINESS
~~~

Vì cache đã có `O1` từ yêu cầu trước, actor `blocked` nhận ngay `receipt:O1` mà `AUTH` **không được gọi**. Test kiểm chứng trạng thái sai một cách rõ ràng để minh họa rằng **thứ tự các advice là yêu cầu chức năng**, không chỉ yêu cầu logging.

Đoạn này là **negative demonstration** trong chương trình học. Trong hệ thống thực, kết quả “người không có quyền nhận receipt” phải khiến test bảo mật **FAIL** và pipeline triển khai bị chặn, thay vì trở thành behavior được chấp nhận.

### 8.6. Giới hạn cần hiểu

- `HashMap`, `ArrayList` và `int businessCalls` được dùng trong **test đơn luồng**. Chúng không tự thread-safe; không sao chép thành shared handler cho production đa luồng.
- `authorization` chỉ so actor với chuỗi cố định để dễ tái hiện. Hệ thống thật cần principal/permission policy đáng tin cậy; không dùng chính actor người gọi tự khai để bảo vệ tài nguyên.
- `cache` chỉ minh họa kết quả non-null và một cache key đơn giản. Với multi-tenant data, quyền truy cập và cache key phải được thiết kế cẩn thận.
- `run()` xây chain bằng Java closures. Nó **không thực hiện bytecode weaving**, không có pointcut language tổng quát, không chứng minh engine AOP thật đã can thiệp vào target.
- Không có retry advice hoặc persistence thật; mỗi event và state đều nằm trong bộ nhớ test.
- Test unsafe chỉ được chạy ở ngữ cảnh cô lập với dữ liệu giả, nhằm chứng minh hậu quả của một chuỗi có thứ tự sai.

## 9. Kiểm thử điểm khớp, điểm không khớp và đường bypass

Một test tích hợp về AOP phải xác nhận **có advice khi cần** và **không có advice khi không được chọn**.

Ví dụ:

| Tình huống | Mục tiêu assertion |
| --- | --- |
| Public method có marker được chọn | Advice chạy đúng một lần |
| Method không có marker | Không có event của advice ấy |
| Overload khác signature | Không match nhầm nếu pointcut yêu cầu signature cụ thể |
| Method trả `void` | Advice quan sát normal completion mà không đòi result object |
| Method ném exception | Advice đúng nhánh exceptional, caller nhận lỗi theo contract |
| Caller đi qua proxy | Handler được kích hoạt |
| Caller giữ raw target | Xác nhận có/không có interception theo cơ chế thật |
| `this.method()` nội bộ | Kiểm tra self-invocation của mô hình proxy/weaving cụ thể |
| Class thuộc module khác | Kiểm tra weaving/classloader scope có bao gồm không |
| Bridge/synthetic method | Không đếm duplicate logical event ngoài ý định |
| Final/private/static/constructor | Chỉ test những điểm engine thật sự hỗ trợ |

**Đừng suy rằng pointcut được parse hợp lệ đồng nghĩa advice chạy.** Có thể pointcut không match, target nằm ngoài weaving scope, proxy bị bypass hoặc class đã nạp trước transformer.

### 9.1. Độ phủ proxy khác độ phủ biến đổi mã

Một JDK interface proxy thông thường nhận những lời gọi **qua proxy interface**. Gọi thẳng target hoặc gọi nội bộ qua `this.method()` có thể bỏ qua wrapper. Một engine dệt method execution vào bytecode có thể quan sát những đường ấy nếu class/join point được hỗ trợ và instrument.

Vì vậy, integration test cần mô phỏng **đúng đường caller thật**; gọi thẳng advice method để kiểm logic không chứng minh độ phủ.

### 9.2. Negative assertions quan trọng với bảo mật

Nếu một method không được phép bypass authorization, đừng chỉ assert request có quyền hoạt động. Cần assert **mọi đường thiếu quyền bị chặn**, kể cả cache hit, callback, gọi thẳng target theo các API cho phép, và đường khởi tạo object khác.

Nếu AOP là một lớp bảo vệ bắt buộc nhưng tồn tại đường bypass không thể kiểm soát, nên củng cố enforcement tại một ranh giới tin cậy khác thay vì chỉ dựa vào kết quả một unit test.

## 10. Kịch bản kiểm thử tổng hợp theo nhiều aspect

Dưới đây là ma trận gợi ý. Không cần ép tất cả vào một test duy nhất; chọn ca nhỏ nhưng kiểm được bất biến phối hợp.

| Ca | Setup | Assertions tổng thể |
| --- | --- | --- |
| 1. Authorized cache miss | Cache rỗng | Auth trước cache, target=1, audit đúng, return đúng |
| 2. Authorized cache hit | Cache đã có | Auth vẫn chạy, target không tăng, result đúng |
| 3. Unauthorized cache hit | Đã warm cache bằng actor hợp lệ | Deny, không đọc lộ result, không target |
| 4. Business exception | Target ném lỗi | Lỗi gốc truyền về, audit failure, không lưu cache |
| 5. Retry allowed | Lỗi transient với số attempts cố định | Target count và audit per-attempt đúng |
| 6. Retry forbidden | Security/validation failure | Không retry lỗi không được phép |
| 7. Around short-circuit | Cache hit hoặc deny | Các lớp trong không chạy, lớp ngoài theo hợp đồng vẫn chạy |
| 8. Two result transforms | Target trả giá trị xác định | Caller thấy đúng composition order |
| 9. After callback failure | Sink audit ném lỗi | Caller outcome theo fail-open/fail-closed đã định |
| 10. Nested business call | Method A gọi B | Tách invocation IDs, không nhầm advice nesting |
| 11. Direct target call | Bypass proxy được kiểm soát | Coverage được phát hiện, không giả định advice chạy |
| 12. Double instrumentation | Proxy và woven advice cùng policy | Đếm event để phát hiện duplicate ngoài ý định |
| 13. Asynchronous success | Future pending rồi completed | Phân biệt method return và task completion |
| 14. Asynchronous failure | Future completes exceptionally | Completion event và lỗi đúng policy |
| 15. Concurrent cache miss | Nhiều requests một key | Không race/bypass, business calls theo cache contract |
| 16. Dynamic config change | Bật/tắt một advice | Chuyển trạng thái trong giới hạn đã định |
| 17. Deployment change | Agent/classloader khác | Đúng join point, đúng precedence trên artifact cuối |

Các expected counts nên **tham số hóa theo chính sách**, ví dụ “cache stampede được phép thực thi nhiều lần để tối ưu đơn giản” khác “single-flight chỉ chạy một lần cho mỗi key”.

## 11. Test đôi và test thật: dùng fake ở đâu?

Một **fake target** hoặc **spy** giúp tạo kết quả có thể dự đoán:

- Trả `"ok"` để thử after-returning.
- Ném `IllegalArgumentException` để thử after-throwing.
- Ghi số lần thực thi để phân biệt duplicate advice và duplicate business call.
- Trả `CompletableFuture` pending để kiểm lifecycle.
- Ghi event trace để xác minh thứ tự.

Nhưng một spy **thay thế toàn bộ weaver/proxy bằng cách gọi lời advice thủ công** sẽ bỏ qua vấn đề rất quan trọng: advice có thật sự được cài vào join point hay không?

Cách làm cân bằng:

1. Dùng **fake nghiệp vụ** để cô lập AOP logic.
2. Chạy lời gọi **qua chính proxy hoặc woven artifact sẽ dùng**.
3. Assert fake target execution count + advice events + caller outcome.
4. Có thêm một số test với **implementation thật và các dependencies quan trọng**, đặc biệt nơi có transaction, caching state hoặc external side effects.

Đừng mock mọi interceptor cùng một lúc trong integration test rồi khẳng định đã kiểm tra sự phối hợp của chúng.

### 11.1. Kiểm thử result/exception không bị spy làm sai

Nếu spy trả `null` trong khi method khai báo primitive, proxy adapter có thể gặp lỗi không có trong nghiệp vụ thật. Fake phải giữ đúng hợp đồng kiểu trả về và ngoại lệ. Nếu muốn thử edge case này thì đặt tên test rõ ràng là **hợp đồng không hợp lệ**, không dùng nó như giả lập normal path.

## 12. Trạng thái test và tính độc lập

Bộ cache, registry, static aspect state hoặc thread-local context có thể tồn tại qua nhiều test. Nếu testcase phụ thuộc thứ tự chạy ngẫu nhiên, một lần xanh không chứng minh hệ thống đúng.

Thực hành tốt:

- Mỗi test tự tạo target/chain/config và tự thiết lập cache state cần thiết.
- Nếu test cần cache hit, **chủ động warm cache** trong chính test hoặc fixture rõ ràng.
- Reset counters, event lists và subscriptions khi kết thúc một ca.
- Không sử dụng cùng mutable singleton giữa những tests chạy song song nếu không có isolation.
- Không dựa vào `Thread.sleep(20)` để chứng minh event async đã hoàn tất.
- Dùng đồng bộ hóa test có deadline và assertion có nguyên nhân khi cần.
- Ghi rõ những input cấu hình ảnh hưởng precedence và pointcut.
- Với random/property tests, giữ seed để tái hiện lỗi.

Trong ví dụ Java, `Harness` giữ state theo một phiên test có chủ đích và `events.clear()` sau mỗi assertion. Trong một bộ test thật, có thể chia thành nhiều fixtures riêng để tránh test sau phụ thuộc vào test trước, **trừ khi đang kiểm cụ thể quy trình warm-cache rồi deny**.

## 13. Tính đúng đắn về concurrency và reentrancy

Unit test đơn luồng của `AuditAdvice` không chứng minh behavior khi nhiều request xen kẽ.

Các vấn đề nên kiểm:

### 13.1. Shared mutable advice state

Một singleton-like aspect lưu `startedAt` trong field chung có thể bị hai invocation ghi đè. Nếu advice đo thời gian:

~~~java
long started = System.nanoTime();
try {
    return next.proceed();
} finally {
    metrics.observe(System.nanoTime() - started);
}
~~~

Đây là **pseudocode Java không độc lập** (`next` và `metrics` thuộc hạ tầng test/app). Local variable `started` tách theo invocation; không cần field mutable singleton.

Test: hai lời gọi đồng thời, ép xen kẽ qua barrier, xác minh mỗi duration tương ứng đúng invocation thay vì chỉ assert “có metric”.

### 13.2. Cache stampede

Hai thread cùng request cache key còn trống có thể cùng thấy miss và gọi target hai lần. Đây có thể là behavior chấp nhận được hoặc vi phạm single-flight contract. Nếu policy yêu cầu một execution, test phải kiểm **số thực thi tối đa**, không chỉ final cache value.

### 13.3. Retry cộng timeout

Timeout ngoài retry khác timeout mỗi attempt. Cần assert giới hạn thời gian/attempts theo cấu trúc thực, tránh test dựa trên clock quá nhạy. Sử dụng clock giả hoặc controlled scheduler nếu architecture hỗ trợ.

### 13.4. Reentrancy và `ThreadLocal`

Một advice có thể được gọi lồng trên cùng thread do recursion hoặc callback. State dùng chung phải phân biệt invocation depth. Nếu dùng `ThreadLocal`, cần restore/remove trong `finally` để thread pool không giữ context của request trước.

### 13.5. Race trong bật/tắt interceptor

Khi cấu hình runtime thay đổi, một invocation đang chạy có thể tiếp tục dùng policy đã được đọc ở đầu. Test cần định nghĩa **điểm tuyến tính hóa** hoặc mức consistency kỳ vọng, không mặc định mọi in-flight call đổi trạng thái tức thì.

## 14. Async: method completion không phải task completion

Một method:

~~~java
CompletableFuture<String> loadAsync() {
    return new CompletableFuture<>();
}
~~~

trả về **một Future object** mà tác vụ có thể còn pending. Sau lời gọi method, một after-returning advice có thể chạy dù task chưa xong.

Nếu audit quan tâm kết quả **tác vụ**, cần gắn với completion/cancellation:

~~~java
CompletableFuture<String> future = startAsync();
future.whenComplete((value, error) -> {
    if (error == null) recordSuccess(value);
    else recordFailure(error);
});
~~~

Hai đoạn trên là **minh họa, không phải chương trình độc lập**, vì `startAsync` và `record...` cần định nghĩa.

Trong integration tests:

1. Tạo Future chưa hoàn tất.
2. Gọi API, assert **method-return event** đã xảy ra nhưng **task-completion event** chưa xảy ra.
3. Hoàn tất Future với value, assert completion thành công theo policy.
4. Tạo Future mới và hoàn tất exceptional, assert lỗi đúng loại.
5. Kiểm cancellation, timeout và callback lỗi nếu contract yêu cầu.
6. Nếu context chuyển thread, xác minh correlation ID/permissions không bị mất.

Không dùng `join()` ngay trong after-returning để biến API async thành synchronous chỉ nhằm thuận tiện testing.

## 15. Side effects, transaction và tính idempotent

Khi business operation có side effects thật, return value thường chưa đủ làm bằng chứng.

Một around retry có thể khiến thao tác ghi DB chạy hai lần. Nếu transaction advice bọc retry khác chiều, số transaction hoặc phạm vi rollback có thể thay đổi. Nếu audit trong retry, event có thể ghi mỗi attempt.

Các ca nên kiểm:

- Số dòng hoặc aggregate domain được tạo thực tế.
- Không commit hai lần khi thao tác phải exactly-once ở tầng nghiệp vụ.
- Khi lỗi, các side effects có được rollback/compensate theo hợp đồng?
- Audit event thể hiện event miền đã commit hay attempt chưa commit?
- External calls có bị lặp khi retry?
- Cache được invalidated đúng sau write thành công?
- Advice lỗi có thể ngăn transaction completion?
- Trường hợp partial success có được biểu diễn minh bạch?

**Không thể suy ra exactly-once business semantics từ việc một advice chỉ chạy một lần.** Một message queue có thể redeliver, network client có thể retry, target có thể tự gọi dịch vụ ngoài nhiều lần. End-to-end tests phải chọn ranh giới đủ rộng theo yêu cầu thực.

## 16. Metamorphic testing: thay đổi một yếu tố, giữ các bất biến

Một kỹ thuật hữu ích là **metamorphic testing**: tạo cặp hoặc bộ kịch bản khác nhau ở một khía cạnh và assert các thuộc tính phải giữ nguyên.

### Ví dụ 1 — bật/tắt observer

Nếu metrics advice chỉ quan sát, bật hoặc tắt nó phải không đổi `businessCalls`, kết quả trả về, ngoại lệ và side effect nghiệp vụ. Chỉ metrics output được phép khác.

### Ví dụ 2 — có/không cache

Hai lời gọi hợp lệ cùng resource cần trả kết quả cùng ngữ nghĩa; khi cache có hiệu lực, số target executions có thể giảm. Nhưng authorization phải vẫn đúng trong cả hai chế độ.

### Ví dụ 3 — thay precedence có chủ đích

Với AUTH ngoài CACHE vs CACHE ngoài AUTH, một test denial sau warm cache phải có kết quả khác nếu chuỗi sai. Đây là test phát hiện **chính sách thứ tự**.

### Ví dụ 4 — thay đổi loại exception

Gửi `IllegalArgumentException` vs `IllegalStateException` từ fake target để kiểm advice retry chỉ retry những lỗi được phép và giữ nguyên lỗi không retry.

### Ví dụ 5 — thay đổi join point

Gọi method được chọn vs một overload không được chọn để bảo đảm không match quá rộng.

### Ví dụ 6 — đổi thread/scheduler

Một workflow chạy cùng dữ liệu theo hai lịch xen kẽ không được làm lẫn context hoặc trả dữ liệu của người dùng khác.

Phương pháp này phát hiện sự tương tác khó mô tả bằng một expected stdout cứng, nhưng **không loại bỏ** nhu cầu kiểm thử kết quả chính xác tại các ca cốt lõi.

## 17. Kiểm thử kiến trúc AOP thật: proxy, weaving và triển khai

Ví dụ Java ở phần 8 chỉ xây Java chain. Với một công nghệ AOP thực tế, phải thêm kiểm thử cấu trúc deployment:

| Mô hình | Điều phải xác minh |
| --- | --- |
| **Interface proxy** | Caller nhận proxy, không giữ raw target ngoài ý định |
| **Subclass proxy** | Method có thể override, final/private không bị hiểu sai |
| **Compile-time weaving** | Artifact cuối là artifact đã dệt; test chạy trên bản ấy |
| **Binary weaving** | Raw/woven output không bị trộn; không dệt lặp ngoài ý định |
| **Load-time weaving** | Transformer/agent hoạt động trước khi class mục tiêu được định nghĩa |
| **Retransformation** | Runtime/agent hỗ trợ và thay đổi trong giới hạn hợp lệ |
| **Nhiều classloaders** | Class thật được test thuộc đúng defining loader |
| **Nhiều aspect cùng match** | Precedence và số lần advice đúng contract |
| **Cấu hình theo môi trường** | Agent, JVM flags, policy version và wiring tương đương release |

Một artifact đã dệt trong build nhưng test lại dùng raw classes sẽ cho kết quả không phản ánh production. Một unit test của handler qua `new Handler().invoke(...)` cũng không kiểm tra proxy thực được cấp cho caller.

### 17.1. Một test “sentinel join point”

Có thể thiết kế một method đặc trưng, ít side effects, được chọn bởi pointcut thật. Trong integration test của bản phát hành, gọi qua đường thực và assert advice marker chạy đúng một lần. Sentinel test giúp phát hiện agent không bật, proxy không được đăng ký hoặc policy bị thiếu.

Nhưng một sentinel duy nhất không chứng minh **toàn bộ** join points đều đúng. Cần thêm tests theo nhóm pointcut và các đường âm (negative coverage).

## 18. Quan sát thất bại và quản lý thông tin test

Khi testcase fail, thông báo nên trả lời:

- **Lời gọi nào?** Method/signature, principal giả, resource ID kiểm thử.
- **Kỳ vọng gì?** Result/exception, events và counters.
- **Thực tế gì?** Diff của event list, counts và outcome.
- **Aspect nào chạy?** Identity và vị trí outer/inner.
- **Join point nào?** Call/execution nếu công cụ phân biệt.
- **Dùng artifact/config nào?** Build hash, policy version, agent/proxy settings.
- **Có async/concurrency không?** Invocation ID, thread/task ID ở mức không nhạy cảm.

Không cần ghi token thật, mật khẩu, thông tin thanh toán hoặc toàn bộ payload khách hàng để debug AOP. Với log/metrics, giới hạn số loại label tránh cardinality tăng vô hạn.

### 18.1. Ghi sự kiện đáng tin

Một event list đồng bộ trong test đơn luồng rất hữu ích. Nhưng trong production, việc ghi log có thể bất đồng bộ, được batch hoặc vận chuyển qua queue. Nếu test muốn khẳng định **advice entry count**, nên đo tại điểm entry của advice chứ không chỉ đếm dòng log ở sink, tránh nhầm với retry/redelivery.

### 18.2. Chẩn đoán thứ tự thiếu nhất quán

Nếu test thỉnh thoảng fail vì event order thay đổi, có hai khả năng: thứ tự đúng phải được bảo đảm nhưng implementation có race, hoặc test đang áp một thứ tự không hề thuộc contract. Phải xác minh trước khi “sửa” bằng cách tăng timeout hoặc tắt chạy song song.

## 19. Một quy trình kiểm thử phối hợp nhiều aspect có thể áp dụng

**Bước 1 — Vẽ sơ đồ chain thực:** viết rõ outer→inner, những đoạn có thể short-circuit, retry hoặc biến đổi result.

**Bước 2 — Viết invariant ở cấp caller:** ai được truy cập, kết quả hợp lệ, ngoại lệ, số side effects và trạng thái cuối.

**Bước 3 — Phân biệt đơn vị event:** per-request, per-attempt, per-execution, per-task-completion.

**Bước 4 — Chọn đối tượng test:** target fake đủ controllable nhưng invocation đi qua chính cơ chế AOP cần kiểm.

**Bước 5 — Tạo ca normal path:** target return thành công; assert precedence, result và counts.

**Bước 6 — Tạo ca exceptional path:** target throw, advice throw, fallback, cleanup/finally nếu có.

**Bước 7 — Tạo ca short-circuit:** cache hit, deny, circuit breaker; assert inner layers có/không chạy theo contract.

**Bước 8 — Tạo ca repeated execution:** retry, nested calls, recursion; đếm target và advice entries riêng.

**Bước 9 — Test âm về pointcut/coverage:** nonmatching method, raw target call, self-invocation, overload, classloader.

**Bước 10 — Test concurrency/async theo nhu cầu:** state isolation, lifecycle, timeout, cancellation và context propagation.

**Bước 11 — Test artifact cuối:** cùng code, policy, weaver/proxy registration và JVM flags của release.

**Bước 12 — Tạo failure report dễ hiểu:** expected/actual event list, caller outcome, counters và config.

**Bước 13 — Giữ regression suite:** bất cứ thay đổi precedence, pointcut hay engine version đều phải chạy lại các bất biến tổng thể.

Quy trình này kết hợp **độ chính xác của unit tests** với **sức phát hiện lỗi tương tác của integration tests**.

## 20. Các lỗi thường gặp khi chỉ test từng advice

1. **Test `AUTH` riêng nhưng không test cache hit của actor bị từ chối:** có thể bỏ sót authorization bypass.
2. **Test `CACHE` bằng đúng result nhưng không đếm target executions:** có thể cache không hoạt động hoặc retry vô ý.
3. **Test `AUDIT` bằng số dòng log:** dễ nhầm event phát trùng ở sink với advice chạy trùng.
4. **Không assert thứ tự:** đúng tập event nhưng sai precedence.
5. **Không test exception path:** success xanh nhưng advice có thể nuốt/đổi lỗi gốc.
6. **Không test short-circuit:** lớp trong có thể bị bỏ qua hợp lệ hoặc bỏ qua sai.
7. **Không kiểm caller result:** audit thành công nhưng return bị transformer đổi ngoài ý định.
8. **Không kiểm side effects:** target chạy hai lần dù caller nhận một kết quả.
9. **Không phân biệt call và execution join point:** có thể đếm sai khi cả hai cùng khớp.
10. **Không kiểm đường gọi trực tiếp bỏ qua proxy:** pointcut đúng nhưng AOP không hoạt động ở đường dùng thực.
11. **Giả định mọi final/private/static method được instrument như nhau:** phạm vi phụ thuộc kỹ thuật.
12. **Mock luôn proxy/weaver trong integration test:** bỏ mất điều quan trọng cần kiểm.
13. **Dùng state cache từ testcase trước:** test chạy độc lập thất bại hoặc phụ thuộc thứ tự.
14. **Coi Future return là task success:** thiếu nhánh completion exceptional/cancellation.
15. **Dùng shared `ArrayList` trong test concurrency:** làm hỏng event collection và tạo false failures.
16. **Bắt `Exception` chung chung:** có thể chấp nhận lỗi sai loại, che regression.
17. **Đếm advice entries như đếm business requests:** sai khi retry, recursion, cache và short-circuit.
18. **Chỉ test happy path:** không phát hiện denial, timeout hoặc dọn dẹp khi lỗi.
19. **Thay policy mà không cập nhật expected invariants:** test xanh có thể phản ánh hợp đồng cũ.
20. **Bỏ qua artifact/config thực tế:** test trên raw code không chứng minh woven/proxy production behavior.
21. **Cho rằng hai log giống nhau là double weaving:** có thể do hai join points hoặc delivery.
22. **Cố làm mọi assertion trong một test dài:** khó cô lập nguyên nhân và tái hiện lỗi.
23. **Không kiểm negative coverage:** advice vô tình chặn thêm method không nên chặn.
24. **Không phân biệt business success với normal method return:** một `Result.failure` vẫn có thể trả bình thường.
25. **Bỏ qua classloader/agent startup:** LTW có thể không chạy dù cấu hình pointcut hợp lệ.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Unit test của `AUTH` và `CACHE` đều PASS. Vì sao người không có quyền vẫn có thể nhận dữ liệu?  
**Trả lời:** Nếu cache đứng ngoài auth, cache hit có thể short-circuit trước bước kiểm quyền. Phải test chuỗi tổng thể sau khi cache đã được warm.

**Câu 2.** Trong chuỗi `AUTH→CACHE→AUDIT→BUSINESS`, khi cache hit, audit có chạy không?  
**Trả lời:** Trong ví dụ, không. Audit nằm bên trong cache và cache hit không gọi `proceed`.

**Câu 3.** Hai lần gọi `bad` cùng throw, business count tăng hai; có chắc retry advice không?  
**Trả lời:** Không. Có thể là hai lời gọi độc lập, như ví dụ. Cần biết invocation/attempt IDs.

**Câu 4.** Vì sao test vừa assert return value vừa assert business count?  
**Trả lời:** Return đúng không bảo đảm target chỉ chạy đúng số lần; side effects có thể lặp.

**Câu 5.** Target ném lỗi nhưng một inner fallback trả kết quả, outer after-returning có thể chạy không?  
**Trả lời:** Có. Outer thấy normal return ở ranh giới của nó dù target trước đó thất bại.

**Câu 6.** Một unit test gọi `audit.afterReturning()` trực tiếp có chứng minh weaving hoạt động không?  
**Trả lời:** Không. Cần integration test gọi qua đúng proxy/woven join point.

**Câu 7.** Vì sao “audit đúng một lần” là yêu cầu chưa đủ rõ?  
**Trả lời:** Cần xác định đúng một lần trên mỗi request, attempt, target execution hay task completion.

**Câu 8.** Test chỉ chạy lúc cache rỗng có phát hiện lỗi auth bị bypass khi cache hit không?  
**Trả lời:** Không chắc. Phải chủ động tạo trạng thái cache hit với actor khác quyền.

**Câu 9.** Tại sao một điểm `after-returning` không đủ chứng minh async task đã thành công?  
**Trả lời:** Method có thể chỉ trả một Future pending; task completion xảy ra sau đó.

**Câu 10.** Proxy bị caller bỏ qua thì test handler trực tiếp có phát hiện không?  
**Trả lời:** Không; test phải dùng object graph/đường caller thật.

**Câu 11.** Khi hai advice đều đúng riêng nhưng đổi thứ tự làm data leak, lỗi nằm ở đâu?  
**Trả lời:** Ở **composition/precedence** và việc thiếu bảo đảm invariant ở toàn workflow.

**Câu 12.** Cần gì ngoài event list để kiểm một action có side effects?  
**Trả lời:** Result/exception caller nhìn thấy, số lần target thật chạy và trạng thái domain/external side effects sau lời gọi.

## 22. Tổng kết

**Kiểm thử nhiều aspect phải đánh giá cả hành vi tổng thể, không chỉ cộng kết quả unit test của từng advice.** Thứ tự outer/inner, `proceed()`, cache hit, retry, fallback, exception, async completion và ranh giới proxy/weaving có thể thay đổi **những gì caller nhìn thấy, những gì target thực thi và những gì hệ thống ghi nhận**.

Hãy bắt đầu bằng các invariant ở cấp workflow, tạo test vừa xác minh **outcome, event order, business execution count, side effects và negative coverage**, rồi thử cả các nhánh normal, exceptional, short-circuit và nhiều attempts. Dùng fake để dễ kích thích edge cases, nhưng vẫn cần gọi qua **cơ chế AOP thực sự** trong integration test. Cuối cùng, chạy tests trên cấu hình và artifact gần với release thật để phát hiện khác biệt từ precedence, classloader, agent, proxy wiring hoặc bytecode weaving. Mục tiêu không phải có thật nhiều test của từng aspect riêng biệt, mà là **chứng minh các aspect phối hợp bảo toàn đúng hợp đồng nghiệp vụ và an toàn khi tương tác**.