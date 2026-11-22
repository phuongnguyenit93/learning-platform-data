# Bộ nhớ đệm và điều kiện lời gọi có thể bỏ qua thực thi gốc trong AOP

## 1. Câu hỏi trọng tâm

Một aspect trong lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP) thường được nghĩ đến như mã chạy trước hoặc sau phương thức: ghi log, đo thời gian, kiểm tra quyền. Tuy nhiên, **around advice** có một năng lực quan trọng hơn: quyết định **có tiếp tục lời gọi đến phương thức đích hay không**. Với bộ nhớ đệm (*cache*), nếu đã có kết quả phù hợp và còn hiệu lực, advice có thể trả về ngay **mà không thực thi phương thức gốc**.

Ví dụ, lời gọi `catalog.findLabel("A")` tốn thời gian đọc nguồn dữ liệu. Một advice có thể lưu kết quả của lần gọi đầu tiên. Ở lần gọi tiếp theo, nếu mọi yếu tố xác định kết quả không đổi và entry còn hợp lệ, advice trả giá trị đã lưu. Đây là *short-circuit* — rẽ nhánh kết thúc lời gọi sớm.

~~~text
Caller
  |
  v
Around advice
  |
  +--> Kiểm tra điều kiện bắt buộc mỗi lời gọi
  |
  +--> Được phép dùng cache?
  |       |
  |       +-- Không: BYPASS -> proceed() -> trả kết quả
  |
  +--> Tạo khóa, đọc entry
          |
          +-- HIT hợp lệ -> trả cached result
          |                  (không gọi target)
          |
          +-- MISS/stale -> proceed() -> target chạy
                                      |
                                      +--> nếu result được phép lưu: put
                                      +--> trả result
~~~

Mấu chốt không phải chỉ là “đã có dữ liệu trong map” mà là **có thể bỏ qua lời gọi gốc mà vẫn giữ đúng hợp đồng nghiệp vụ**. Caching sai có thể làm bỏ qua kiểm tra quyền, làm mất side effect bắt buộc, trả dữ liệu cũ hoặc sai tenant, nhân bản lỗi bất đồng bộ và che khuất thứ tự các aspect.

## 2. AOP can thiệp vào lời gọi ở mức nào?

Các khái niệm liên quan:

- **Join point:** điểm có thể được quan sát hoặc can thiệp, chẳng hạn một method call/execution theo khả năng công cụ.
- **Pointcut:** quy tắc chọn tập join point.
- **Advice:** hành vi chạy tại join point được chọn.
- **Around advice:** bao việc gọi đích, có thể quyết định gọi `proceed()`, trả giá trị thay thế hoặc ném ngoại lệ.
- **Proceed:** thao tác tiếp tục qua các advice tiếp theo hoặc target, tùy mô hình và API của nền tảng.
- **Aspect ordering:** thứ tự lồng nhau của nhiều advice, ảnh hưởng nhánh được thực thi khi cache hit.

Một *before advice* chạy trước target nhưng thông thường không tự thay thế return value. Một *after returning advice* nhận kết quả sau khi target đã chạy: nó có thể lưu kết quả vào cache nhưng không tiết kiệm được lần thực thi đó. **Around advice** hoặc một interceptor có quyền điều khiển invocation là chỗ phù hợp để **không gọi** target trên cache hit.

Pseudocode minh họa:

~~~text
around(invocation):
    if not eligible(invocation):
        return proceed()

    key = buildKey(invocation)
    entry = cache.find(key)

    if entry exists and entry is valid:
        return entry.value        # KHÔNG gọi proceed

    result = proceed()            # Target thực thi trên cache miss
    if mayStore(invocation, result):
        cache.put(key, result)
    return result
~~~

Đây là mã giả, không phải API Java có sẵn. Chính sách thực tế cần xử lý exception, null, trạng thái stale, quyền, đồng thời, timeout và kiểu return.

Một short-circuit còn có thể **bỏ qua những advice nằm phía trong caching advice**, vì nhánh đó không gọi `proceed()`. Do đó thứ tự cache với kiểm tra quyền, validation, transaction, audit, tracing và retry quyết định tính đúng đắn.

## 3. Phân biệt *hit*, *miss* và *bypass*

| Nhánh | Nguyên nhân | Target được gọi? | Có thể lưu kết quả mới? |
| --- | --- | --- | --- |
| **Hit** | Có entry hợp lệ đúng ngữ cảnh và policy | **Không** | Thường không; có thể cập nhật access metadata nếu policy cho phép |
| **Miss** | Lời gọi đủ điều kiện dùng cache nhưng không có entry dùng được | **Có** | Có nếu kết quả đạt điều kiện ghi |
| **Stale** | Entry tồn tại nhưng hết hạn hoặc sai version/quyền | **Có** hoặc chính sách refresh riêng | Có thể thay entry hợp lệ |
| **Bypass** | Policy quy định lời gọi không được dùng cache | **Có** | Tùy chính sách; thường không ghi |
| **Rejected** | Input không hợp lệ, thiếu quyền hoặc policy cấm lời gọi | Không nhất thiết | Không; có thể ném lỗi trước target |

**Miss khác bypass.** Với miss, hệ thống đã thử dùng cache nhưng không có dữ liệu. Với bypass, hệ thống chủ ý tránh đọc cache, chẳng hạn yêu cầu dữ liệu realtime hoặc lời gọi không thuộc diện tái sử dụng kết quả. Bypass vẫn chạy phương thức gốc, trong khi hit hợp lệ mới là nhánh tiêu biểu được phép bỏ qua thực thi gốc.

**Rejected không phải một loại cache miss.** Nếu caller không được quyền truy cập, không nên trả giá trị cached hay tự động chuyển sang target khi policy buộc phải chặn.

Một cache hit đúng phải thỏa ít nhất:

~~~text
selectedJoinPoint
AND mandatoryChecksPassed
AND requestEligibleForCache
AND stableCacheKeyAvailable
AND entryFound
AND entryNotExpired
AND versionMatches
AND contextAndPermissionsMatch
AND returnContractCompatible
~~~

Không phải mọi hệ thống cần lưu tất cả metadata trên entry, nhưng hệ thống phải có cách bảo đảm những điều kiện ảnh hưởng correctness.

## 4. Phương thức nào thích hợp để cache?

Lý tưởng là một phép tính có đầu ra xác định bởi input và một snapshot/version dữ liệu rõ ràng, không có side effect phải xảy ra trên mỗi lượt gọi. Ví dụ:

- Tra cứu tên sản phẩm dựa trên mã và phiên bản catalog.
- Tính một kết quả số học đắt đỏ nhưng xác định.
- Đọc dữ liệu tham chiếu với TTL/invalidation phù hợp.
- Chuyển đổi định dạng hoặc phân tích cấu trúc dữ liệu bất biến.
- Tạo view theo tham số + locale + quyền đã xác định.

Phương thức **không nên bị short-circuit bằng read cache thông thường** nếu việc chạy nó chính là tác động nghiệp vụ:

- `chargeCard(request)` thực hiện thanh toán.
- `reserveInventory(sku, amount)` trừ tồn kho.
- `sendEmail(message)` gửi thông báo.
- `incrementCounter()` tạo số thứ tự hoặc tăng thống kê.
- `recordAccess()` ghi audit bắt buộc ở mỗi lần gọi.
- `refreshLease()` gia hạn trạng thái.
- `consumeOneTimeToken()` tiêu thụ token.

Một giá trị return có thể giống nhau ở hai lượt gọi nhưng **hợp đồng quan sát được khác nhau** vì side effect. Bỏ qua target khi hit sẽ làm hành vi sai. Với lệnh ghi cần chống gọi trùng, hãy dùng hợp đồng **idempotency key + trạng thái xử lý bền vững**, không tự xem nó giống cache kết quả đọc.

### Tính thời điểm và dữ liệu biến thiên

Các phương thức đọc thời gian hiện tại, số ngẫu nhiên, trạng thái mạng, tỷ giá trực tiếp hoặc dữ liệu nguồn thường xuyên đổi có thể vẫn cache được nếu hợp đồng cho phép *staleness* cụ thể, nhưng phải đưa tham số quyết định output vào key hoặc có version/TTL rõ ràng. Nếu hệ thống hứa dữ liệu mạnh về nhất quán, một TTL tùy ý có thể không đáp ứng hợp đồng đó.

### Kiểm tra bắt buộc ở mọi lời gọi

Nếu kiểm tra quyền chỉ nằm trong method đích, cache hit bỏ qua target cũng bỏ qua quyền. Cần đặt kiểm tra quyền ở một ranh giới luôn thực thi, hoặc thiết kế policy đảm bảo hit không thể lộ dữ liệu trái quyền. Thêm tenant/user ID vào key có thể cần thiết nhưng **không tự thay thế việc kiểm tra quyền còn hiệu lực**. Tương tự với quota, input validation và audit bắt buộc.

## 5. Ví dụ Java 17: dynamic proxy thực sự bỏ qua target

Chương trình sau dùng `java.lang.reflect.Proxy` để mô phỏng around advice ở các lời gọi đi qua interface. Một annotation tự định nghĩa đánh dấu method được phép cache. Ba nhánh được thể hiện rõ: hit bỏ qua target, miss chạy target rồi lưu, bypass luôn chạy target.

**Lưu ý:** ví dụ đơn luồng cố ý dùng `HashMap` và bộ đếm thường để dễ kiểm tra output. Nó không cung cấp TTL, persistence, thread safety hoặc distributed caching. Kết quả nghiệp vụ không phụ thuộc bộ đếm: số lần tính chỉ được in qua dòng `[target]` để chứng minh có hay không thực thi. Điều này giúp cache hit giữ đúng hợp đồng kết quả cho cùng `code` trong ví dụ.

Lưu tệp **`CachingAdviceDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.HashMap;
import java.util.Map;

public class CachingAdviceDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface CacheableResult {}

    interface CatalogService {
        @CacheableResult
        String lookup(String code);
    }

    static final class CatalogServiceImpl implements CatalogService {
        private int calls;

        @Override
        public String lookup(String code) {
            calls++;
            System.out.println("[target] lookup " + code + ", call=" + calls);
            return "VALUE(" + code + ")";
        }

        int executions() {
            return calls;
        }
    }

    static Object proceed(
            Object target, Method method, Object[] args) throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException e) {
            throw e.getCause();
        }
    }

    static CatalogService withCachingAdvice(CatalogService target) {
        Map<String, Object> cache = new HashMap<>();

        return (CatalogService) Proxy.newProxyInstance(
                CatalogService.class.getClassLoader(),
                new Class<?>[] {CatalogService.class},
                (proxy, method, args) -> {
                    if (!method.isAnnotationPresent(CacheableResult.class)) {
                        return proceed(target, method, args);
                    }

                    String code = (String) args[0];
                    if (code == null || code.isBlank()) {
                        throw new IllegalArgumentException(
                                "code must not be blank");
                    }

                    if (code.startsWith("LIVE:")) {
                        System.out.println("[cache] bypass " + code);
                        return proceed(target, method, args);
                    }

                    String key = method.getName() + "|" + code;
                    if (cache.containsKey(key)) {
                        System.out.println("[cache] hit " + code);
                        return cache.get(key);
                    }

                    System.out.println("[cache] miss " + code);
                    Object result = proceed(target, method, args);
                    cache.put(key, result);
                    return result;
                });
    }

    public static void main(String[] args) {
        CatalogServiceImpl target = new CatalogServiceImpl();
        CatalogService service = withCachingAdvice(target);

        System.out.println("1=" + service.lookup("A"));
        System.out.println("2=" + service.lookup("A"));
        System.out.println("3=" + service.lookup("LIVE:X"));
        System.out.println("4=" + service.lookup("LIVE:X"));
        System.out.println("5=" + service.lookup("B"));
        System.out.println("[stats] target calls=" + target.executions());
    }
}
~~~

Chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac CachingAdviceDemo.java
java CachingAdviceDemo
~~~

Đầu ra xác định:

~~~text
[cache] miss A
[target] lookup A, call=1
1=VALUE(A)
[cache] hit A
2=VALUE(A)
[cache] bypass LIVE:X
[target] lookup LIVE:X, call=2
3=VALUE(LIVE:X)
[cache] bypass LIVE:X
[target] lookup LIVE:X, call=3
4=VALUE(LIVE:X)
[cache] miss B
[target] lookup B, call=4
5=VALUE(B)
[stats] target calls=4
~~~

**Giải thích từng nhánh:**

1. `withCachingAdvice` trả proxy triển khai `CatalogService`. Chỉ lời gọi đi qua `service` mới được handler quan sát.
2. Handler nhận metadata `@CacheableResult` trên method interface. Annotation này chỉ là dấu hiệu cho handler; **tự annotation không thể làm cache tự chạy**.
3. Lần gọi `lookup("A")` thứ nhất: key chưa có, advice gọi `proceed`, target tính `VALUE(A)` rồi được lưu.
4. Lần thứ hai `lookup("A")`: cache hit, handler return `VALUE(A)`. Target không chạy, nên không xuất hiện dòng `[target]` mới và bộ đếm không tăng.
5. Hai lần `lookup("LIVE:X")` đi vào nhánh bypass: handler **không tra cache**, luôn gọi target, vì vậy bộ đếm tăng lên 2 và 3.
6. `lookup("B")` là miss khác: target chạy lần thứ tư. Năm lần gọi proxy nhưng **chỉ bốn lần chạy target** — chứng cứ trực tiếp của short-circuit.
7. `proceed` unwrap `InvocationTargetException` để truyền đúng lỗi gốc từ target. `cache.put` chỉ được gọi sau khi target return bình thường; lỗi ném trực tiếp không biến thành success entry.
8. Nhánh kiểm tra input nằm **trước cache lookup**, do đó một lời gọi input rỗng không được trả cached result để lẩn tránh validation.

Giới hạn: key đơn giản chỉ gồm tên method và `code` vì demo có một method cache. Với overload hoặc nhiều interface, cần định danh đầy đủ method/signature. Không dùng `HashMap` chia sẻ giữa các luồng ở production; thêm versioning, TTL, authorization context, capacity bound và invalidation theo yêu cầu.

## 6. Cache key là điều kiện để hit thật sự hợp lệ

Một **hit** chỉ hợp lệ nếu lời gọi hiện tại được phép dùng cùng kết quả với lời gọi trước: cùng thao tác, tham số, ngữ cảnh bảo mật/tenant, locale, version hoặc yếu tố khác có khả năng làm đổi output. Key của demo là `method.getName() + "|" + code` **chỉ dành cho một method và một context cố định**; nó không phù hợp cho hệ thống nhiều tenant, overload hay kết quả phụ thuộc quyền.

Ví dụ `quote(tenant, sku, currency, priceVersion)` cần khóa dạng tuple bất biến, có namespace và các thành phần liên quan. Nếu hai tenant có giá khác nhau nhưng dùng chung khóa `sku`, đó là **lỗi tính đúng và có thể rò dữ liệu**. Phân quyền vẫn phải được kiểm tra tại ranh giới thích hợp kể cả khi có cache; TTL/invalidation cần bảo đảm freshness.

Không chuẩn hóa input bằng `trim`/`lowercase` nếu domain phân biệt các giá trị đó. Không đưa token hoặc dữ liệu nhạy cảm nguyên văn vào cache key/log. Với mảng và object mutable, phải chọn biểu diễn canonical ổn định, không dựa vào identity hoặc hash thay đổi theo thời gian.

Phần thiết kế key theo ngữ cảnh có nhiều chiều, versioning, canonicalization và kiểm thử phân vùng được phân tích chuyên sâu ở bài riêng; ở đây key đủ chính xác là **tiền điều kiện** để advice được phép short-circuit.

## 7. Điều kiện đọc và điều kiện ghi không giống nhau

**Read condition** thường được đánh giá *trước* `proceed` để quyết định có dùng cache không. Ví dụ chỉ đọc cache với request chế độ standard, không đọc khi user yêu cầu realtime.

**Write condition** được đánh giá *sau* khi đã có kết quả thực để quyết định có tạo entry không. Ví dụ chỉ cache một kết quả thành công có kích thước phù hợp và dữ liệu đủ ổn định.

~~~text
if invalidRequest:
    rejectAccordingToContract

if mustBypassCache:
    return proceed()

key = buildKey()
entry = readValidEntry(key)

if entry found:
    return entry.value

result = proceed()

if mayCacheResult(result):
    store(key, result, ttl)

return result
~~~

Điều kiện “cho đọc cache” có thể dựa trên input và ngữ cảnh. Điều kiện “cho ghi” có thể cần nhìn cả output, loại lỗi, kích thước, chính sách riêng tư, version nguồn và outcome của giao dịch liên quan.

Một số kết quả cần chính sách riêng:

- **`null`:** cache có thể cần sentinel riêng, vì “không có entry” và “entry có payload null” khác nhau. `ConcurrentHashMap` không cho null value.
- **Not found:** *negative caching* có ích với truy vấn lặp, nhưng cần TTL/invalidation khi dữ liệu mới xuất hiện.
- **Error:** mặc định không xem exception là success entry. Một policy có thể cache một số lỗi xác định, nhưng lỗi mạng/timeout tạm thời thường không nên bị giữ lâu.
- **Mutable value:** cần immutable snapshot hoặc defensive copy nếu caller có thể sửa dữ liệu đã cache.
- **Return object identity:** cache cùng object có thể phá hợp đồng nếu API hứa object mới ở mỗi lần gọi.

Đặt write condition sai có thể khiến cả một failure tạm thời được lưu và trả lại như kết quả hợp lệ trong nhiều giờ.

## 8. TTL, invalidation và giữ dữ liệu mới

Một entry có thể đã đúng tại thời điểm tạo nhưng sai khi nguồn dữ liệu thay đổi. Chính sách lifecycle thường gồm:

- **TTL:** hết hạn sau một khoảng tính từ lúc ghi/refresh.
- **Time-to-idle:** hết hạn khi không ai truy cập trong thời gian quy định.
- **Explicit invalidation:** xóa hoặc thay entry khi có sự kiện cập nhật nguồn.
- **Versioned key:** chuyển sang key version mới khi dữ liệu/logic thay đổi.
- **Refresh-ahead:** tải lại dữ liệu trước khi hết hạn.
- **Stale-while-revalidate:** cố ý cho phép đọc stale trong một khoảng nhỏ và refresh nền, nếu API chấp nhận.

TTL dài tăng khả năng hit nhưng có thể tăng stale latency; TTL ngắn tăng loader traffic. Nếu hợp đồng đòi nhất quán mạnh, một TTL tùy ý không đủ để thay cơ chế version/invalidation phù hợp.

Một race quan trọng:

~~~text
A: bắt đầu load dữ liệu phiên bản V1
B: cập nhật nguồn sang V2 rồi invalidate cache
A: hoàn tất việc đọc V1 và ghi lại V1 vào cache
C: cache hit nhưng nhận V1 đã lỗi thời
~~~

Cần xem xét version check, generation token hoặc conditional write để ngăn loader cũ tái điền entry sau invalidation. “Đã gọi invalidate” không tự bảo đảm mọi request sau đó đều đọc dữ liệu mới trong hệ thống đồng thời.

## 9. Đồng thời: cache stampede và single-flight

Nếu nhiều caller đồng thời gặp miss trên cùng key, mỗi caller có thể gọi target:

~~~text
Caller A --- miss ---> expensive target
Caller B --- miss ---> expensive target
Caller C --- miss ---> expensive target
~~~

Hiện tượng này gọi là *cache stampede*. Các hướng xử lý tùy hạ tầng:

| Cách | Cơ chế | Điểm phải chú ý |
| --- | --- | --- |
| Per-key lock | Một loader cho mỗi key tại một instance | Deadlock, timeout, giải phóng lock |
| Single-flight | Những caller cùng key chia sẻ một computation đang chạy | Failure, cancellation và ownership |
| Atomic compute | Đồng bộ hóa tạo entry theo API cache | Hạn chế loader trong critical section, reentrancy |
| Early refresh | Refresh trước khi hết hạn | Chi phí refresh |
| TTL jitter | Phân tán thời điểm hết hạn | Không hoàn toàn loại bỏ đồng thời |
| Distributed lock/coordinator | Phối hợp trên nhiều instance | Kết nối mạng, TTL lock, partial failure |

`ConcurrentHashMap` bảo đảm an toàn cho các thao tác được tài liệu của nó quy định, nhưng nếu code tự `get` rồi `put` thành hai bước riêng, nhiều luồng vẫn có thể cùng nhìn thấy miss. `computeIfAbsent` có thể giúp tình huống loader đồng bộ cụ thể; callback tính toán không được vi phạm ràng buộc như cập nhật đệ quy cùng map. Với phép tính bất đồng bộ, cần mô hình cache in-flight riêng.

Nếu nhiều caller chia sẻ cùng một `CompletableFuture` đang tính, một caller hủy không nhất thiết được quyền hủy tác vụ phục vụ các caller khác. Quy tắc ownership của cancellation/timeout phải tường minh.

## 10. Cache đối với phương thức bất đồng bộ

Với `CompletionStage<T>` hoặc `Future<T>`, phương thức có thể trả về handle **trước khi công việc hoàn tất**. Nếu caching advice lưu handle ngay khi method return:

~~~text
stage = proceed()  // chỉ là handle
cache.put(key, stage)
return stage
~~~

thì nó đã cache **đối tượng đại diện**, chưa chứng minh đã cache payload thành công. Đây có thể là lựa chọn có chủ đích để chia sẻ một phép tính đang chạy (*single-flight*), nhưng cần xem xét:

- Stage có thể thất bại, bị hủy, treo lâu hoặc timeout.
- Lưu future lỗi mãi sẽ khiến các caller mới nhận lại lỗi cũ.
- Hủy handle dùng chung có thể ảnh hưởng người gọi khác.
- Callback hoàn tất có thể chạy trên luồng khác, cần an toàn đồng thời và truyền ngữ cảnh.
- Invalidation chạy trong lúc task chưa xong có thể bị loader cũ ghi đè kết quả stale.
- Thay handle trả cho caller có thể làm đổi identity, cancellation/exception propagation.

Một cách khác là **chỉ cache payload sau successful completion**. Khi hit, advice có thể trả một stage đã hoàn tất với payload cached **nếu hợp đồng cho phép**. Cần xử lý đúng các trường hợp failure/cancel/timeout và giữ tính không chặn. Không gọi `join()` trong advice chỉ để lấy kết quả thật nếu API hứa trả ngay: làm bên gọi chờ và có thể gây nghẽn/deadlock.

Với publisher hoặc luồng dữ liệu lazy, return publisher chưa chắc kích hoạt công việc. Cùng publisher có thể có nhiều subscriber; cache publisher object không đồng nghĩa cache toàn bộ dữ liệu phát hoặc terminal outcome. Nếu muốn replay/share stream, phải có chính sách rõ về subscription, demand, backpressure, memory, lỗi và hủy. Aspect tự subscribe để “đổ dữ liệu vào cache” có thể kích hoạt tác vụ mới và làm thay đổi hành vi của caller.

## 11. Aspect ordering: caching có thể bỏ qua những gì khác?

Giả sử có authorization, metrics và caching:

~~~text
Cách A
authorization {
    metrics {
        cache {
            target
        }
    }
}

Cách B
cache {
    authorization {
        metrics {
            target
        }
    }
}
~~~

**Cách A:** mọi caller phải qua authorization và metrics, kể cả cache hit. **Cách B:** cache hit có thể không chạy authorization/metrics nằm phía trong. Nếu authorization bắt buộc ở mỗi lượt truy cập, cách B có thể vi phạm chính sách.

Tương tự:

- **Validation ngoài cache:** kiểm tra đầu vào ở mỗi lần; validation chỉ nằm trong target có thể bị skip trên hit.
- **Audit ngoài cache:** ghi mỗi lượt đọc nếu hợp đồng yêu cầu; audit trong target chỉ ghi các lần miss/bypass.
- **Tracing/metrics ngoài cache:** quan sát cả hit và miss; đặt bên trong cache chỉ đo target executions.
- **Retry ngoài hoặc trong cache:** thay đổi phạm vi attempt, lỗi và cache loader được retry; retry target có side effect cần chính sách riêng.
- **Transaction ngoài cache:** cache hit có thể mở một transaction không cần thiết; đặt transaction trong cache thì hit bỏ qua transaction.
- **Cache ghi kết quả trước commit:** có thể để lộ trạng thái chưa được xác nhận. Nên phối hợp invalidation/refresh sau commit hoặc chiến lược consistency phù hợp khi dữ liệu nguồn cần giao dịch.

Không có một thứ tự aspect phổ quát cho mọi hệ thống. Phải xác định chính sách nào áp cho **mọi lời gọi**, chính sách nào chỉ áp cho **lần target thực thi**, và thứ tự nesting thực tế của công cụ AOP.

## 12. Phụ thuộc vào khả năng nền tảng

**Không phải mọi đường gọi đều đi qua advice**. Điều kiện intercept khác nhau theo kỹ thuật:

| Kỹ thuật | Khả năng áp short-circuit | Giới hạn thường gặp |
| --- | --- | --- |
| Decorator thủ công | Wrapper có thể trả trực tiếp mà không gọi đối tượng gốc | Caller phải dùng wrapper |
| Dynamic proxy theo interface | Invocation handler có thể không gọi target | Chỉ những method/đường gọi đi qua proxy |
| Proxy dựa trên subclass | Có thể override/intercept method đủ điều kiện | `final`, `private`, constructor và visibility có thể giới hạn |
| Bytecode weaving | Có thể thay đổi hành vi tại join point được hỗ trợ | Cần cấu hình weaving/pointcut và quyền truy cập bytecode đúng |
| Runtime instrumentation | Có thể intercept/skip khi hook hỗ trợ thay return | Tùy runtime, classloader, module access và cơ chế instrument |

**Self-invocation:** nếu một method trong implementation gọi `this.otherMethod()`, lời gọi nội bộ ấy có thể không đi qua proxy bao ngoài, khiến cache advice của `otherMethod()` không được kích hoạt. Weaving intercept execution join point có thể cho hành vi khác. Phải kiểm chứng công cụ và điểm cắt thực, không chỉ nhìn annotation.

Một short-circuit phải trả giá trị **tương thích kiểu khai báo và hợp đồng**. Không trả `null` cho primitive, không thay ngoại lệ bằng một giá trị tùy tiện, không phá identity/side-effect constraints. Với `void` mà method tạo side effect bắt buộc, bỏ body không phải tối ưu caching vô hại.

Điểm cắt còn có thể khác nhau giữa call/execution, overload, bridge/synthetic methods, constructor và callback do runtime khác kích hoạt. Quyết định caching cần đặt trên phạm vi interception đã được xác minh.

## 13. Quan sát và vận hành

Một aspect cache tốt nên phân loại metrics:

| Metric | Diễn giải |
| --- | --- |
| `cache.hit` | Trả entry hợp lệ, target không chạy |
| `cache.miss` | Lời gọi hợp lệ phải chạy target do không có entry |
| `cache.bypass` | Bỏ cache theo policy và gọi target |
| `cache.stale` | Entry tồn tại nhưng không đủ freshness/version |
| `cache.load_success` | Loader thật đã hoàn tất thành công |
| `cache.load_failure` | Loader thật thất bại |
| `cache.invalidation` | Entry bị loại vì dữ liệu thay đổi |
| `cache.eviction` | Entry bị loại vì giới hạn sức chứa |
| `cache.inflight_shared` | Caller dùng chung computation đang chạy nếu có single-flight |

Hit rate thường tính hit/(hit+miss) cho các lượt đủ điều kiện; bypass có thể được báo riêng để không hiểu nhầm hiệu quả cache. Tách **latency của lookup cache**, **latency của loader** và **latency từ góc caller**. Một cache hit nhanh nhưng trả sai quyền hoặc stale ngoài mức cho phép vẫn là lỗi nghiêm trọng.

Giới hạn vận hành: cache không bounded gây tăng bộ nhớ/GC; key nhiều biến thể gây cardinality cao; TTL đồng loạt gây stampede; distributed cache có thể mất kết nối; dữ liệu sensitive có thể bị lộ nếu cache tier không được bảo vệ. Cần chính sách rõ nếu cache không khả dụng: có hệ thống có thể *fail open* bằng cách gọi target; có hệ thống không được làm vậy vì cache chính là một phần policy bảo mật hoặc chống lạm dụng.

## 14. Kiểm thử hành vi quan trọng

| Tình huống | Kiểm chứng |
| --- | --- |
| Lần đầu với key mới | Miss, target chạy đúng một lần |
| Lần sau cùng key, entry còn hợp lệ | Hit, không chạy target, kết quả đúng |
| Input khác | Không dùng nhầm entry |
| Bypass | Luôn gọi target, không “hit giả” |
| Input không hợp lệ | Bị từ chối trước cache hit nếu contract yêu cầu |
| Entry hết TTL / đổi version | Target chạy lại hoặc refresh theo policy |
| Tenant/quyền thay đổi | Không nhận dữ liệu sai phạm vi |
| Exception từ target | Truyền nguyên nhân gốc, không tạo success entry |
| Null/not-found | Có policy phân biệt negative entry và miss |
| Mutable return | Caller không thể sửa entry dùng chung ngoài hợp đồng |
| Concurrent miss cùng key | Số lần loader chạy đúng chính sách |
| Async failure/cancellation | Không giữ forever một exceptional/cancelled handle ngoài ý định |
| Invalidation trong khi loader chạy | Không tái điền stale entry sai version |
| Self-invocation | Hiểu đúng đường gọi bỏ qua proxy |
| Caching + authorization/transaction | Ordering không phá kiểm tra/commit |
| Cache outage | Fallback theo policy, không lộ dữ liệu |

Trong ví dụ Java, `[stats] target calls=4` chứng minh 5 lời gọi proxy chỉ chạy target 4 lần. Nhưng **giá trị trả về đúng và số lần target đúng** chỉ là bước đầu; triển khai thật còn cần kiểm thử freshness, concurrency, security, partial failure và nguyên tắc giới hạn cache.

## 15. Các lỗi thiết kế thường gặp

1. Chỉ kiểm tra `cache.containsKey(key)` mà không xác minh TTL, version và quyền.
2. Tạo key chỉ từ một phần tham số trong khi output còn phụ thuộc tenant, locale hoặc config.
3. Cache method tạo side effect rồi bỏ qua việc nghiệp vụ bắt buộc phải làm mỗi lần.
4. Đặt authorization/validation trong target nhưng cache hit xảy ra bên ngoài.
5. Nghĩ một annotation tự mang đến interception và cache.
6. Không hiểu self-invocation qua proxy nên kỳ vọng hit/miss không đúng.
7. Dùng `HashMap` không an toàn giữa nhiều luồng.
8. Làm `get` rồi `put` tách rời và tưởng concurrent loader chỉ chạy một lần.
9. Cache `null`, “not found” và lỗi như nhau mà không có policy.
10. Giữ future lỗi hoặc bị hủy mãi như một completed success cache entry.
11. Trả mutable cached object khiến caller sửa dữ liệu cho người khác.
12. Cache dữ liệu chưa commit hoặc invalidate trước khi transaction hoàn tất mà không xét race.
13. Tự subscribe publisher chỉ để “cache kết quả” và làm phát sinh side effect.
14. Đặt mục tiêu hit rate cao nhưng không kiểm tra correctness và bảo mật.
15. Đánh đồng “cache hit bỏ gọi target” với idempotency của lệnh ghi.

## 16. Checklist thiết kế caching advice

Trước khi cho phép around advice bỏ qua thực thi gốc, hãy trả lời:

1. Việc trả kết quả đã lưu có **tương đương về hành vi** với thực thi target theo hợp đồng hay không?
2. Nền tảng AOP có thật sự intercept đúng lời gọi và hỗ trợ return mà không `proceed()` không?
3. Policy bắt buộc nào phải thực thi **trên mọi lời gọi**, kể cả hit?
4. Điều kiện nào quyết định hit/miss/bypass/rejected?
5. Cache key có đủ input, tenant, locale, version, mode và context phụ thuộc kết quả không?
6. TTL/invalidation/version có đáp ứng mức freshness được cam kết không?
7. Loại outcome nào được cache: success, null, not-found, failure, future in-flight?
8. Giá trị trả về có mutable hoặc identity-sensitive không?
9. Có chính sách stampede, single-flight, timeout và cancellation đúng khi đồng thời không?
10. Cache có làm đổi semantics của transaction, retry, security, audit, tracing hoặc metrics không?
11. Cache backend gặp lỗi thì phải gọi target, trả lỗi hay chính sách khác?
12. Kiểm thử đã xác nhận cả **output**, **số lần target chạy** và **quyền/freshness** chưa?

## 17. Kết luận

Trong AOP, **around advice** có thể bỏ qua thực thi gốc bằng cách trả một cached result thay vì gọi `proceed()`. Điều kiện tiên quyết là entry còn hợp lệ, kết quả đúng với input/ngữ cảnh và việc không chạy target không vi phạm side effect hay chính sách phải thực hiện mỗi lần. Cache hit, miss và bypass là những nhánh khác nhau; chỉ hit hợp lệ mới là short-circuit thông thường.

Để sử dụng an toàn, cần hiểu khả năng interception của nền tảng, thiết kế key và lifecycle đúng, kiểm tra quyền trước khi trả cache, điều phối aspect ordering, xử lý đồng thời và trạng thái bất đồng bộ. Khi đó caching advice mới thực sự tối ưu việc thực thi mà vẫn giữ nguyên hợp đồng nghiệp vụ.