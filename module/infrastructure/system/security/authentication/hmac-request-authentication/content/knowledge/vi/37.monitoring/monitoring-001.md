# Metric request hợp lệ trong hệ thống xác thực HTTP bằng HMAC

## 1. Vì sao phải định nghĩa “request hợp lệ” trước khi đo?

Trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, HTTP client ký **canonical request** bằng shared secret. Canonical request có thể gồm method, URI, signed headers và digest của body theo hợp đồng. Server kiểm tra đúng key ID/secret, trạng thái credential, timestamp, nonce chống replay rồi tạo danh tính đã xác thực. Một yêu cầu đã xác thực sau đó vẫn phải đi qua **authorization** trước khi truy cập tenant, resource hoặc thực hiện nghiệp vụ.

Đề bài **Metric request hợp lệ** trong chương **Monitoring** đặt câu hỏi: khi dashboard báo “98% request hợp lệ”, **98% của tập nào, tại bước nào và có đảm bảo điều gì?**

Có nhiều cách hiểu dễ nhầm:

- HTTP trả `200 OK` chưa chắc HMAC được kiểm tra; endpoint có thể bị cấu hình bypass.
- HTTP trả `403 Forbidden` có thể là **HMAC hợp lệ** nhưng thiếu quyền tenant.
- HTTP trả `400 Bad Request` có thể là **HMAC hợp lệ** nhưng JSON/validation sai sau xác thực.
- HTTP trả `401 Unauthorized` có thể do HMAC sai, key bị REVOKED, timestamp quá hạn hoặc nonce đã dùng.
- HTTP trả `503 Service Unavailable` có thể do secret manager hoặc replay store hỏng, nên verifier **không thể kết luận** HMAC hợp lệ hay không.
- Gateway có thể trả `413`, `429` hoặc `502` **trước khi** request đến ứng dụng, nên metric của backend không phản ánh toàn bộ lưu lượng.

Do đó, cần **định nghĩa ngữ nghĩa của metric trước, sau đó mới cài instrumentation**. Một metric không có ranh giới đo rõ ràng dễ tạo dashboard đẹp nhưng che khuất lỗi bảo mật.

### Mục tiêu học tập

Sau bài này, người học có thể thiết kế metric HMAC có nghĩa, đặt điểm đo chính xác trong Spring Security, triển khai bằng Micrometer, quan sát bằng Prometheus, tính tỷ lệ request hợp lệ, xây dashboard/cảnh báo và kiểm thử để bảo đảm metric không bị đếm trùng, nhầm lỗi hạ tầng với request giả hoặc làm lộ thông tin credential.

## 2. Định nghĩa chuẩn: request HMAC hợp lệ là gì?

Trong bài này, một **request HMAC hợp lệ** là request đã vượt qua toàn bộ các điều kiện authentication bắt buộc của hợp đồng ký:

1. Đã được đưa vào **HMAC authentication chain** đúng endpoint/route.
2. Header/key ID, timestamp, nonce và các thành phần cần ký được parse theo format không mơ hồ; body nằm trong giới hạn hỗ trợ.
3. Registry tìm được **đúng credential version** và chứng minh credential, client (và trạng thái tenant liên quan) còn được phép xác thực theo chính sách.
4. Verifier dựng đúng **canonical bytes** từ request thực tế, dùng đúng shared secret và xác nhận HMAC bằng phép so sánh phù hợp về timing.
5. Timestamp nằm trong cửa sổ thời gian được chấp nhận.
6. Nonce được **claim nguyên tử thành công** trong miền chống replay theo scope đã xác định; request không bị phát lại.
7. Authenticator có thể tạo **principal tin cậy**. Điểm đo `valid` nằm ngay sau bước này và trước authorization.

Ta ký hiệu:

\[
V(r)=H(r)\land C(r)\land T(r)\land N(r)
\]

Trong đó:

- `H(r)`: HMAC hợp lệ trên canonical request.
- `C(r)`: credential/client và các ràng buộc authentication đủ điều kiện.
- `T(r)`: timestamp hợp lệ.
- `N(r)`: nonce được chấp nhận lần đầu bằng thao tác nguyên tử.

Để đơn giản, định dạng request và giới hạn đã được kiểm tra trước các điều kiện trên.

**`V(r)=true` không hàm ý authorization allowed hoặc business success.** Ví dụ client `partner-a` ký đúng một request tới `tenant-b`, nonce mới, nhưng không có delegated grant. Request được ghi nhận là **HMAC valid**, sau đó bị **authorization denied**. Đây không phải mâu thuẫn.

### Ranh giới trạng thái

| Điểm trong pipeline | Metric/kết luận | Có thể gọi là “HMAC valid”? |
| --- | --- | --- |
| Gateway nhận TCP/HTTP request | Request received | Chưa |
| Header có `X-Signature` | Signature provided | Chưa |
| Tra đúng key và MAC khớp | Signature verified | Chưa đủ nếu chưa kiểm tra timestamp/nonce/state |
| Timestamp hợp lệ | Freshness passed | Chưa đủ |
| Nonce claim thành công và credential ACTIVE | **Authentication valid** | **Có** |
| Authorization theo tenant/action/resource thành công | Authorization allowed | HMAC đã valid, thêm quyền |
| Controller trả 2xx | Business/API success | Không thay thế chứng cứ HMAC |
| DB transaction commit | Business effect committed | Không thay thế các bước bảo mật |

Không đặt tên metric `hmac_valid_requests` cho việc **chỉ khớp chữ ký** nếu replay hoặc key state còn chưa kiểm tra.

## 3. Xác định đơn vị đếm: một authentication attempt

Một `authentication attempt` được tính **một lần** khi request đi vào ranh giới HMAC authentication thuộc phạm vi giám sát, kể cả khi bị từ chối vì thiếu header hoặc chữ ký. Chỉ những route **bắt buộc xác thực HMAC** mới nằm trong tập đó.

Ví dụ phạm vi:

~~~text
/api/hmac/payments/**  → route=payments
/api/hmac/orders/**    → route=orders
/api/hmac/webhooks/**  → route=webhooks
các route khác        → không thuộc HMAC attempt metric
~~~

Không lấy chuỗi URI đầy đủ làm nhãn metric. Cả `/api/hmac/payments/1` và `/api/hmac/payments/999999` phải cùng đi vào bucket `payments` nếu cùng chính sách.

**Quy tắc đếm một lần:**

- Có một sự kiện terminal outcome cho mỗi attempt ở **điểm quyết định authentication cuối cùng**.
- Request đầu tiên vượt HMAC/replay → ghi `valid` **một lần**.
- Request bị replay → ghi `invalid` **một lần**, **không** đồng thời ghi `valid` vì HMAC cryptographic vẫn đúng.
- Lỗi secret manager/nonce store không biết kết quả → ghi `unavailable` hoặc `error`, **không đoán** `valid/invalid`.
- Body quá giới hạn và chưa thể hoàn tất xác thực → có thể ghi `not_evaluated` nếu request đã vào boundary; không ép nó là signature invalid.
- Các request bị ingress/gateway chặn **trước boundary** không xuất hiện trong counter ứng dụng này. Chúng thuộc metric của gateway.
- Nếu filter bị chạy hai lần trên cùng HTTP request, đó là lỗi cấu hình; cần phát hiện và sửa, không tự nhận số lần gọi filter là số lượng request thật.

### Ví dụ minh họa

`partner-a` gửi request HMAC hợp lệ, được principal A nhưng thiếu quyền tenant B:

~~~text
hmac.authentication.attempts{result="valid"}       +1
hmac.authorization.decisions{decision="deny"}      +1
http.server.requests{status="403"}                 +1
~~~

Nếu dashboard chỉ nhìn 403, nó sẽ kết luận “request không hợp lệ” dù **authentication thực tế thành công**. Vì vậy, ít nhất phải quan sát **authentication, authorization và HTTP outcome ở các metric tách biệt**.

## 4. Phân loại outcome chính xác

Một contract metric có thể quy định giá trị nhãn `result` hữu hạn:

| `result` | Điều kiện | Có tính là request hợp lệ không? |
| --- | --- | --- |
| `valid` | Credential, HMAC, timestamp và nonce đều thành công | **Có** |
| `invalid` | Bằng chứng/credential bị từ chối chắc chắn | Không |
| `not_evaluated` | Body quá lớn hoặc request bị loại trước khi đủ bằng chứng để xác minh | Không kết luận |
| `unavailable` | Phụ trợ xác thực bắt buộc không khả dụng hoặc kết quả không xác định | Không kết luận |
| `error` | Lỗi nội bộ ngoài dự kiến trong đường xác thực | Không kết luận |

`reason` là một nhãn **giá trị cố định** để phân tích nội bộ:

| `result` | `reason` ví dụ | Giải thích |
| --- | --- | --- |
| valid | `none` | Toàn bộ authentication conditions pass |
| invalid | `malformed` | Header/nonce/key ID sai cú pháp, trùng hoặc không chuẩn |
| invalid | `credential` | Key không tồn tại/expired/revoked, client disabled |
| invalid | `signature` | HMAC không khớp |
| invalid | `timestamp` | Signed timestamp ngoài cửa sổ |
| invalid | `replay` | Nonce đã được claim |
| not_evaluated | `body_limit` | Không kiểm tra chữ ký vì request body vượt ngưỡng |
| unavailable | `dependency` | Registry, secret manager, replay store mất khả dụng |
| error | `internal` | Lỗi logic/lỗi bất ngờ của verifier |

Không dùng `exception.getMessage()` làm `reason`: message có thể chứa key ID, nguyên nhân chi tiết không ổn định, URI hoặc secret. Lý do nội bộ có thể chi tiết hơn ở **security audit**, nhưng metric chỉ nên dùng tập nhãn giới hạn.

### “Valid” khác “safe”, “authorized” và “processed”

- `valid` chứng minh bằng chứng HMAC **được chấp nhận** trong lần gửi hiện tại.
- `authorized` chứng minh principal có quyền với tenant/action/resource theo policy hiện hành.
- `2xx` chứng minh HTTP handler đã trả response thành công theo API.
- `business_committed` có thể cần event/audit transaction riêng.

Bốn khái niệm **không nên gộp** thành một counter tên `success`.

## 5. Thiết kế metric contract cho Micrometer/Prometheus

Một tập instrument gọn, đủ để trả lời phần lớn câu hỏi vận hành:

| Logical metric | Loại | Labels có kiểm soát | Ý nghĩa |
| --- | --- | --- | --- |
| `hmac.authentication.attempts` | Counter | `route`, `result`, `reason`, `contract` | Mỗi HMAC attempt kết thúc bằng một outcome |
| `hmac.authentication.duration` | Timer | `route`, `result` | Thời gian xác thực từ lúc bắt đầu adapter đến quyết định terminal |
| `hmac.authorization.decisions` | Counter | `route`, `decision` | Policy allow/deny **sau** khi có principal |
| `hmac.authentication.inflight` | LongTaskTimer hoặc gauge có kiểm soát | `route` | Các attempt đang xử lý |
| `hmac.replay.store.operations` | Counter | `operation`, `outcome` | Claim nonce thành công, duplicate, timeout, unknown |
| `hmac.credential.lookup.duration` | Timer | `result` loại hữu hạn | Chi phí tìm trạng thái/secret |
| `hmac.credential.revocation.propagation` | Timer/histogram tổng hợp | `region` được quản lý | Độ trễ phát tán revoke tới verifier |
| `hmac.gateway.canonical.mismatch` | Counter | `route`, `gateway` hữu hạn | Mismatch trên test/probe đã xác minh nguyên nhân |

**Tên metric ở bảng là tên logic Micrometer**. Prometheus thường hiển thị counter dưới dạng `hmac_authentication_attempts_total` và Timer thành `hmac_authentication_duration_seconds_count`, `_sum`, có thể có `_bucket` nếu cấu hình histogram. Cần kiểm tra **tên thực tế từ exporter/phiên bản thư viện** thay vì đoán tên chính xác trên mọi deployment.

### Chọn contract version

Nếu signer và verifier có `HMAC-REQUEST-V1` và `V2`, `contract` có thể là `v1` hoặc `v2` **sau khi server đã parse và kiểm soát allowlist**. Không lấy bất kỳ chuỗi tự do nào từ `X-Signing-Version` rồi dùng ngay làm label; kẻ tấn công có thể tạo hàng triệu giá trị khác nhau.

Version contract giúp phân biệt lỗi canonicalization trong rollout. Để tránh metric cardinality tăng vô hạn, chỉ giữ một tập version nhỏ đang được hỗ trợ, và dùng `unknown` cho đầu vào ngoài danh sách.

## 6. Đặt điểm ghi metric ở đâu trong Spring Security?

Một ứng dụng Spring MVC dùng `SecurityFilterChain`/HMAC `OncePerRequestFilter`, `AuthenticationManager` và `AuthenticationProvider` có thể đặt instrumentation:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["SecurityFilterChain match HMAC route"]
    B --> C["Bắt đầu HMAC attempt timer"]
    C --> D["Parse + bounded body + canonical request"]
    D --> E["AuthenticationManager / HMAC provider"]
    E --> F["Credential state + HMAC + timestamp"]
    F --> G["Atomic nonce claim"]
    G --> H{"Quyết định HMAC authentication?"}
    H -->|Valid| I["Record result=valid một lần"]
    H -->|Invalid| J["Record result=invalid một lần"]
    H -->|Unknown dependency| K["Record result=unavailable một lần"]
    I --> L["SecurityContext principal"]
    L --> M["AuthorizationManager"]
    M --> N["Controller/service + HTTP result"]
~~~

**Vị trí lý tưởng:** ngay tại thành phần **sở hữu kết luận cuối cùng** của HMAC authentication. Không đo “valid” khi mới có `MessageDigest.isEqual() == true` nhưng chưa claim nonce.

Có hai phương án instrumentation:

1. **Decorator quanh authentication service/manager:** một component nhận request evidence, chạy đầy đủ credential/MAC/timestamp/nonce rồi trả kết quả hoặc typed failure. Decorator đo thời gian, phân loại và ghi **một terminal outcome**.
2. **Custom filter có một nhánh quyết định duy nhất:** adapter parse request, gọi manager, catch lỗi của **riêng khối authentication**, ghi outcome rồi mới truyền xuống `chain.doFilter`.

Đừng ghi `valid` cả trong provider, manager, filter và controller: cùng request sẽ thành bốn lần. Với endpoint có nhiều authentication provider, phải xác định đúng provider/challenge nào chịu trách nhiệm và tránh đếm các “thử provider” nội bộ như request độc lập.

### Chú ý ngoại lệ đi từ downstream

Không đặt logic ghi metric ở `finally` bao quanh toàn bộ `chain.doFilter` rồi đổi outcome từ `valid` thành `error` khi controller ném lỗi. Authentication đã hoàn tất **trước** controller; lỗi nghiệp vụ phải thuộc metric HTTP/business khác.

Nếu một custom filter nằm trước `ExceptionTranslationFilter`, exception authentication ném ngay trong filter có thể cần được nó tự chuyển tới `AuthenticationEntryPoint`. Instrumentation phải ghi kết quả trước/đồng thời bước này, nhưng response không được chạy qua controller sau khi authentication thất bại.

## 7. Ví dụ Java 17: Micrometer đếm HMAC authentication attempt

Đoạn sau là một implementation mẫu cho ứng dụng dùng **Micrometer**, áp giá trị label bằng enum phía server. Nó **không đọc bất kỳ secret hoặc dữ liệu nhạy cảm** nào làm tag.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

enum HmacRouteGroup {
    PAYMENTS("payments"),
    ORDERS("orders"),
    WEBHOOKS("webhooks"),
    OTHER("other");

    private final String tag;

    HmacRouteGroup(String tag) {
        this.tag = tag;
    }

    String tag() {
        return tag;
    }

    // Nhóm route do server kiểm soát.
    // Không dùng nguyên URI, resourceId, clientId làm label.
    static HmacRouteGroup fromTrustedRoute(String routePattern) {
        return switch (routePattern) {
            case "hmac-payments" -> PAYMENTS;
            case "hmac-orders" -> ORDERS;
            case "hmac-webhooks" -> WEBHOOKS;
            default -> OTHER;
        };
    }
}

enum HmacAttemptOutcome {
    VALID("valid", "none"),
    BAD_HEADER("invalid", "malformed"),
    BAD_CREDENTIAL("invalid", "credential"),
    BAD_SIGNATURE("invalid", "signature"),
    TIMESTAMP_REJECTED("invalid", "timestamp"),
    REPLAY_REJECTED("invalid", "replay"),
    BODY_TOO_LARGE("not_evaluated", "body_limit"),
    DEPENDENCY_UNAVAILABLE("unavailable", "dependency"),
    INTERNAL_ERROR("error", "internal");

    private final String resultTag;
    private final String reasonTag;

    HmacAttemptOutcome(String resultTag, String reasonTag) {
        this.resultTag = resultTag;
        this.reasonTag = reasonTag;
    }

    String resultTag() {
        return resultTag;
    }

    String reasonTag() {
        return reasonTag;
    }
}

public final class HmacAuthenticationMetrics {
    private final MeterRegistry registry;

    public HmacAuthenticationMetrics(MeterRegistry registry) {
        this.registry = Objects.requireNonNull(registry);
    }

    public void record(
            HmacRouteGroup route,
            HmacAttemptOutcome outcome,
            String contractVersion,
            long elapsedNanos) {

        // Đây là allowlist, không lấy header nguyên văn.
        String contract =
            "v1".equals(contractVersion) ? "v1"
            : "v2".equals(contractVersion) ? "v2"
            : "unknown";

        Counter.builder("hmac.authentication.attempts")
            .description("Completed HMAC authentication attempts")
            .tag("route", route.tag())
            .tag("result", outcome.resultTag())
            .tag("reason", outcome.reasonTag())
            .tag("contract", contract)
            .register(registry)
            .increment();

        Timer.builder("hmac.authentication.duration")
            .description("HMAC authentication decision latency")
            .tag("route", route.tag())
            .tag("result", outcome.resultTag())
            .publishPercentileHistogram()
            .serviceLevelObjectives(
                Duration.ofMillis(5),
                Duration.ofMillis(20),
                Duration.ofMillis(100),
                Duration.ofMillis(500))
            .register(registry)
            .record(Math.max(0, elapsedNanos), TimeUnit.NANOSECONDS);
    }
}
~~~

Giá trị route truyền vào `fromTrustedRoute` phải là **một route ID đã xác định từ cấu hình/matcher server**, không phải URL hoặc header do client trực tiếp gửi. Tham số `contractVersion` trong ví dụ vẫn là `String`, nhưng đã được chuẩn hóa qua allowlist trước khi dùng làm nhãn.

Micrometer cache meters đã đăng ký theo tên + tags. Tuy vậy, đăng ký bằng builder ở mỗi request vẫn có overhead; nếu throughput cao, có thể tạo trước các meters theo tập enum/route/contract cố định hoặc dùng `MeterProvider`/cache có kích thước giới hạn được kiểm thử. Không cache tự do theo key ID/nonce/URI.

### Khi nào gọi record?

Mẫu tích hợp tách riêng nhánh quyết định:

~~~java
long started = System.nanoTime();
HmacAttemptOutcome outcome = HmacAttemptOutcome.INTERNAL_ERROR;
Authentication authenticated = null;

try {
    // parseProof phải dùng method/URI/header/body thực tế;
    // manager phải verify key, MAC, timestamp và claim nonce.
    var proof = parseProof(request);
    authenticated = authenticationManager.authenticate(proof);
    if (authenticated == null || !authenticated.isAuthenticated()) {
        throw new BadCredentialsException("authentication_failed");
    }

    outcome = HmacAttemptOutcome.VALID;
} catch (MalformedHmacRequestException ex) {
    outcome = HmacAttemptOutcome.BAD_HEADER;
    throw ex;
} catch (HmacSignatureMismatchException ex) {
    outcome = HmacAttemptOutcome.BAD_SIGNATURE;
    throw ex;
} catch (HmacNonceAlreadyUsedException ex) {
    outcome = HmacAttemptOutcome.REPLAY_REJECTED;
    throw ex;
} catch (HmacDependencyUnavailableException ex) {
    outcome = HmacAttemptOutcome.DEPENDENCY_UNAVAILABLE;
    throw ex;
} finally {
    metrics.record(
        HmacRouteGroup.PAYMENTS,
        outcome,
        "v1",
        System.nanoTime() - started);
}

// Chỉ sau đây mới gắn SecurityContext và gọi chain.doFilter.
// Authorization/HTTP response không đổi outcome đã ghi.
~~~

Đây là **pseudocode Java bên trong authentication adapter**, không biên dịch độc lập: các exception và `parseProof` là thành phần dự án cần định nghĩa. Các exception chuyên biệt ở ví dụ nhằm tạo classification *phía server*. Thực tế có thể dùng một `HmacFailureReason` enum/typed result, rồi chuyển ra public `BadCredentialsException` hoặc exception an toàn; không dựa vào chuỗi exception message.

Nếu `parseProof` có thể trả `BODY_TOO_LARGE` hoặc `TIMESTAMP_REJECTED`, phải mở rộng catch/typed result đúng nhánh. Nếu một exception bất ngờ xảy ra, `INTERNAL_ERROR` được ghi một lần và pipeline phải fail closed; không tiếp tục nghiệp vụ.

**Điểm dễ sai:** trong `finally`, `metrics.record` không được là nơi làm hỏng xác thực nếu metrics registry/exporter gặp vấn đề. Các registry in-memory thường an toàn khi ghi, nhưng custom meter handler có thể ném lỗi; cần thiết kế quan sát sao cho **không biến lỗi telemetry thành bypass bảo mật** hoặc che nguyên nhân thật, và kiểm thử lỗi exporter.

## 8. Đo thời gian chính xác: không trộn thời gian nghiệp vụ

`hmac.authentication.duration` được tính từ lúc bước authentication bắt đầu đến khi có **quyết định terminal**, bao gồm:

- Parse header/canonical request ở adapter.
- Hash body bytes (nếu hợp đồng ký body).
- Tra credential và secret, kiểm tra trạng thái key/client.
- Tính HMAC/so sánh signature.
- Kiểm tra timestamp và atomic nonce claim.
- Hoàn tất tạo principal hoặc kết luận lỗi.

Không đưa controller, truy vấn DB nghiệp vụ, gọi payment provider hoặc serialize HTTP response vào Timer này. Những bước đó thuộc `http.server.requests` và metric nghiệp vụ khác.

Các điểm đo phụ giúp tìm bottleneck:

~~~text
HTTP server duration
  ├─ HMAC header parsing
  ├─ Canonicalization + body digest
  ├─ Credential lookup / vault lookup
  ├─ HMAC calculation
  ├─ Nonce claim latency
  ├─ Authorization policy latency
  └─ Business/controller duration
~~~

Đây là **sơ đồ phân tích latency**, không phải tổng cộng bắt buộc: nhiều bước có thể chạy song song, dùng cache hoặc được ghi nhận ở các điểm khác nhau. Đừng cộng tất cả timer như một phép toán luôn đúng.

### Histogram thay vì percentile theo mỗi instance

Với Prometheus, histogram buckets giúp tổng hợp latency qua nhiều instance:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, route) (
    rate(hmac_authentication_duration_seconds_bucket[5m])
  )
)
~~~

Query chỉ hợp lệ khi exporter thực sự phát metric bucket với tên trên và nhãn `le`. Nếu ứng dụng không bật histogram hoặc exporter dùng tên khác, phải đối chiếu `/actuator/prometheus`. Tránh lấy trung bình p95 từ từng instance rồi coi đó là p95 toàn cụm.

Các SLO buckets `5ms`, `20ms`, `100ms`, `500ms` trong code chỉ là ví dụ cần điều chỉnh theo latency thực và budget của các dependency.

## 9. Tính tỷ lệ request HMAC hợp lệ

Định nghĩa tại thời điểm/sổ quan sát:

\[
\operatorname{validRate} =
\frac{N_{\text{valid}}}
{N_{\text{valid}}+N_{\text{invalid}}}
\times 100\%
\]

Với hợp đồng bài này, **`not_evaluated`, `unavailable`, `error` không nằm trong mẫu số** của tỷ lệ này vì chưa có kết luận đúng/sai đáng tin. Tên dashboard cần nói rõ: *HMAC validity among conclusively evaluated attempts*. Không được diễn giải nó thành availability hoặc success rate của API.

Ví dụ trong 5 phút:

| Outcome | Số request |
| --- | ---: |
| valid | 9.200 |
| invalid | 300 |
| not_evaluated | 100 |
| unavailable | 350 |
| error | 50 |
| **Tổng** | **10.000** |

Khi đó:

\[
\operatorname{validRate}
= \frac{9200}{9200+300}\times 100\%
\approx 96{,}84\%
\]

Nhưng **500 request** (350 unavailable, 50 error và 100 not_evaluated) không thể được dùng để kết luận HMAC hợp lệ hay không. Báo thêm hai tỷ lệ:

\[
\operatorname{evaluatedCoverage} =
\frac{N_{\text{valid}}+N_{\text{invalid}}}{N_{\text{attempts}}}
\times 100\%=95\%
\]

\[
\operatorname{authenticationAvailability} =
\frac{N_{\text{attempts}}-N_{\text{unavailable}}-N_{\text{error}}}
{N_{\text{attempts}}}\times100\%=96\%
\]

Công thức availability ở đây là **định nghĩa vận hành minh họa**: nó đo tỷ lệ attempt không kết thúc bằng lỗi hạ tầng/verifier. Một API có thể chọn phân loại body quá lớn, client disconnect và lỗi gateway riêng; không sử dụng con số này thay SLO chung nếu chưa chốt phạm vi.

### PromQL mẫu

Tỷ lệ HMAC valid trên những attempt có kết luận:

~~~promql
sum(rate(hmac_authentication_attempts_total{result="valid"}[5m]))
/
clamp_min(
  sum(rate(hmac_authentication_attempts_total{result=~"valid|invalid"}[5m])),
  0.000001
)
~~~

Tỷ lệ phân tích theo nhóm route:

~~~promql
sum by (route) (
  rate(hmac_authentication_attempts_total{result="valid"}[5m])
)
/
clamp_min(
  sum by (route) (
    rate(hmac_authentication_attempts_total{result=~"valid|invalid"}[5m])
  ),
  0.000001
)
~~~

Nhân `100` nếu dashboard muốn hiển thị phần trăm thay vì 0–1. Các ví dụ này giả định Prometheus exporter dùng tên counter như trên. `clamp_min` chỉ tránh chia cho 0; **khi lưu lượng bằng 0, tỷ lệ không có ý nghĩa**. Dashboard nên hiển thị N/A hoặc dùng điều kiện traffic tối thiểu, không coi “0/0 được clamp” là bằng chứng hệ thống bị lỗi.

Tỷ lệ lỗi phụ trợ:

~~~promql
sum(rate(hmac_authentication_attempts_total{
  result=~"unavailable|error"
}[5m]))
/
clamp_min(
  sum(rate(hmac_authentication_attempts_total[5m])),
  0.000001
)
~~~

Một query tính theo `sum(rate(...))` cần thêm ràng buộc `job`, `environment` hoặc `cluster` từ cấu hình Prometheus khi nhiều môi trường được scrape chung, tránh vô tình gộp staging/production.

## 10. Đếm đúng trong môi trường gateway và nhiều instance

Giả sử client đi qua **gateway A → Spring Boot service B**. Nếu A và B đều ghi `hmac.authentication.attempts_total` vào một metric chung, biểu đồ tổng có thể đếm **hai lần**.

Cần đặt **measurement authority**:

- **Gateway xác minh HMAC:** gateway ghi metric HMAC authentication. Backend ghi metric `gateway_assertion.verification` hoặc authorization nội bộ; không coi mỗi assertion là một HMAC client attempt mới.
- **Backend xác minh HMAC:** backend ghi metric HMAC authentication. Gateway ghi request ingress/proxy metrics, không tự tuyên bố HMAC valid nếu chỉ forward.
- **Cả hai cùng verify:** cần định nghĩa metric tách theo `verification_layer` hoặc tên metric khác nhau. Dashboard “số client HMAC requests hợp lệ” chỉ dùng **một lớp được chỉ định**, không cộng cả hai.

Không suy ra “số request unique” bằng cách `sum` counter từ mọi hop mà không xác định đơn vị và đường đi.

### Ví dụ kiến trúc

~~~mermaid
flowchart LR
    C["Clients"] --> G1["Gateway A"]
    C --> G2["Gateway B"]
    G1 --> R["HMAC verification authority"]
    G2 --> R
    R --> N[("Shared nonce store")]
    R --> S["Backend service"]
    S --> P["Authorization policy"]
    G1 -.-> M["Ingress metrics"]
    G2 -.-> M
    R -.-> H["HMAC auth metrics"]
    S -.-> B["Service/authorization metrics"]
~~~

Nếu một request được gateway retry nội bộ, cần ghi rõ metric đang đếm **attempt xác thực tại verifier** hay **unique client request**. Một nonce replay bị chặn ở lần retry sẽ làm tăng `invalid{reason="replay"}`; điều đó phản ánh hành vi thực tế nhưng không nhất thiết có attacker. Cần correlation với retry của gateway và sự cố mạng.

### Load balancing và aggregation

Prometheus counter là **cumulative theo process**, vì vậy dùng `rate()` hoặc `increase()` khi tổng hợp. Không lấy giá trị counter thô cộng qua các instance có uptime khác nhau rồi coi là tổng request trong một cửa sổ. Lưu ý counter reset khi restart và các metric series bị mất khi pod rời cluster.

## 11. Monitoring chống replay và timestamp

Replay là một **nhánh invalid** quan trọng nhưng không nên đánh đồng với chữ ký sai:

| Tín hiệu | Diễn giải có thể |
| --- | --- |
| `invalid{reason="signature"}` tăng | Client dùng secret sai, canonicalization drift, proxy rewrite, tấn công đoán chữ ký |
| `invalid{reason="timestamp"}` tăng | Client clock skew, timestamp format sai, delay gateway hoặc replay cũ |
| `invalid{reason="replay"}` tăng | Request bị phát lại, client retry cùng nonce, filter double-run, nonce generator lỗi |
| `unavailable{reason="dependency"}` tăng | Replay store/registry/vault không thể xác nhận request |
| `valid` giảm và `replay` tăng cùng lúc | Có thể gateway đang retry mù hoặc filter chạy hai lần |

Timestamp phải nằm trong canonical request được ký; nonce cũng phải nằm trong dữ liệu ký. Replay store phải claim bằng thao tác **atomic insert-if-absent** sau khi HMAC hợp lệ và dùng chung giữa các verifier cần bảo vệ cùng credential.

### TTL phải phù hợp cửa sổ timestamp

Nếu cửa sổ là `±W`, TTL cố định của replay record nên bao phủ toàn bộ thời gian chữ ký còn được chấp nhận, ví dụ ít nhất `2W + margin` với thời điểm claim tại biên tương lai. Nếu TTL quá ngắn, có thể xảy ra **request HMAC cũ được chấp nhận lại** sau khi nonce record biến mất. Metric `replay` thấp không chứng minh an toàn nếu Redis đã evict hoặc TTL sai.

Cần monitor:

- Latency thao tác atomic claim.
- Timeout và kết quả claim không xác định.
- Eviction, memory pressure, replication/failover và TTL policy.
- Thời gian và trạng thái clock sync của gateway/verifier.
- Cửa sổ timestamp rejection theo route/region/contract version.
- Test probe định kỳ chứng minh **một nonce chỉ được chấp nhận một lần** trên các verifier được phép.

Không ghi toàn bộ nonce trong metric label. Nếu cần điều tra một trường hợp cụ thể, dùng audit bảo mật với định danh được hash/giới hạn quyền đọc.

## 12. Monitoring key rotation và thu hồi credential

Key rotation cho phép nhiều key version `ACTIVE` trong một cửa sổ chuyển tiếp, nhưng mỗi request phải được xác minh bằng **secret đúng key ID**. Khi key `K3` bị `REVOKED`, chữ ký được tính bằng secret K3 vẫn phải bị từ chối.

Đối với monitoring, phân biệt:

- **Migration progress:** bao nhiêu request hợp lệ tiếp tục dùng version cũ so với mới?
- **Revocation enforcement:** mọi verifier đã biết trạng thái `REVOKED` hay chưa?
- **Operational impact:** tỷ lệ `invalid{reason="credential"}` tăng sau deployment/rotation có do client chưa được cập nhật không?
- **Security incident:** key đã REVOKED có còn request được accept ở gateway nào không?

Không sử dụng `key_id`, `client_id` hoặc `tenant_id` làm label không giới hạn của counter. Nếu cần đo tiến độ migration theo nhóm, dùng **nhãn version hữu hạn** như `generation="legacy|current"`, chỉ sau khi server mapping từ registry. Với từng client cụ thể, sử dụng audit dữ liệu có quyền truy cập và retention phù hợp, hoặc hệ thống phân tích offline thay vì metric cardinality cao.

### Độ trễ propagate revoke

Một SLO có thể yêu cầu: “mọi verifier ngừng chấp nhận credential K3 sau thời điểm revoke theo hạn mức nhất định”. Đo và kiểm thử:

1. Thời điểm trạng thái REVOKED commit tại source of truth.
2. Thời điểm từng gateway/verifier nhận revision mới.
3. Thời điểm verifier **thực sự áp trạng thái mới** vào quyết định authentication.
4. Các test có chữ ký hợp lệ của K3 sau revoke đều bị từ chối theo thời hạn cam kết.

Metric event arrival không tự chứng minh verifier đã áp đúng revision; cần probe hoặc audit trên quyết định xác thực thực tế. Event bất đồng bộ + TTL không thể được gọi là “thu hồi tức thời” nếu vẫn tồn tại cửa sổ stale.

Nếu registry/secret manager không thể chứng minh state đủ mới, **fail closed** và ghi `unavailable` thay vì lặng lẽ chấp nhận credential dựa trên cache không đủ tin cậy.

## 13. Quan sát lỗi canonical request qua proxy/gateway

Một tỷ lệ `invalid{reason="signature"}` tăng đột biến sau khi bật reverse proxy hoặc đổi ingress có thể là **canonicalization drift**. Không kết luận ngay secret bị lộ hoặc bị brute force.

Các yếu tố thường khác nhau giữa client/gateway/backend:

| Trường | Nguyên nhân mismatch |
| --- | --- |
| Method | HTTP method bị rewrite hoặc method override ngoài hợp đồng |
| URI | External path khác internal route |
| Query | Thứ tự parameter, duplicate query, percent-encoding, `+` và `%20` |
| Host/scheme | `Host`, `Forwarded`, TLS termination |
| Header | Case, whitespace, duplicate value, proxy thêm/xóa |
| Body | JSON whitespace, charset, content encoding, compression, line ending |
| Timestamp/nonce | Proxy làm mất/thay đổi signed header |
| Key ID | Rotation/lookup key version không thống nhất |

Hãy giữ **hợp đồng ký có version** và dùng test vector chuẩn để so sánh client ↔ gateway ↔ backend. Không log raw canonical request hoặc body production vì có thể chứa dữ liệu nhạy cảm. Có thể log `contract_version`, `route_group`, `proxy_revision`, lỗi thuộc **nhóm thành phần** và correlation ID được quản lý.

Một biểu đồ hữu ích là so sánh `invalid{reason="signature"}` theo route, contract, region/gateway **có danh sách hữu hạn** trước và sau deploy. Không lấy toàn bộ raw URL, user-agent hoặc IP từng request làm labels.

## 14. Phân biệt public error, metric nội bộ và security audit

Một API HMAC có thể trả cùng một lỗi công khai:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
Cache-Control: no-store
WWW-Authenticate: HMAC realm="api"

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required or invalid.",
  "code": "AUTHENTICATION_FAILED",
  "requestId": "req-5b612"
}
~~~

Trong ví dụ này, `HMAC realm="api"` là challenge **theo scheme riêng đã được API định nghĩa**, không phải challenge HMAC mặc định của Spring Security. Cấu trúc problem JSON minh họa theo RFC 9457 với `code` và `requestId` là extension fields.

Một `401` chung có thể che các nguyên nhân chi tiết như key ID không tồn tại, signature sai, key revoked hoặc nonce reused để giảm **credential enumeration oracle**. Nội bộ vẫn cần phân loại `reason` cho metrics và audit.

### Ba kênh thông tin có mức nhạy cảm khác nhau

| Kênh | Mục tiêu | Được chứa gì? |
| --- | --- | --- |
| Public HTTP response | Cho client biết request không được chấp nhận | Status, public code chung, requestId đã chuẩn hóa |
| Metrics | Xu hướng, alert, dashboard | Các nhãn **hữu hạn**, không có định danh per request |
| Security audit/traces | Điều tra sự cố | Reason code chi tiết, reference có kiểm soát, correlation ID; không có secret |

Không log shared secret, chữ ký HMAC nguyên vẹn, full canonical string chứa body nhạy cảm, header xác thực hoặc raw payload nhạy cảm. Hash của body có entropy thấp cũng có thể giúp suy đoán dữ liệu; tránh coi digest là không nhạy cảm trong mọi trường hợp.

**Sampling:** có thể sampling một phần traces của request hợp lệ để giảm chi phí, nhưng không nên phụ thuộc vào sampled tracing để đếm chính xác request. Counter phải được ghi trên mỗi attempt nằm trong scope, còn tracing phục vụ điều tra. Audit bảo mật có thể cần retention/chính sách sampling khác nhau theo yêu cầu rủi ro.

## 15. Chống cardinality explosion và rò rỉ nhãn

Prometheus tạo một time series mới cho **mỗi tổ hợp label values**. Nếu gắn `client_id`, `tenant_id`, `key_id`, `nonce`, `request_id` hoặc nguyên URL vào counter, số series có thể tăng không giới hạn.

Ví dụ:

~~~text
10.000 clients × 500 tenants × 4 outcomes × 6 routes
= 120.000.000 label combinations (về lý thuyết)
~~~

Trong thực tế không phải mọi tổ hợp đều tồn tại, nhưng bề mặt tạo series rất lớn. Kẻ tấn công còn có thể gửi header tùy ý để tạo label mới nếu instrumentation dùng thẳng input.

### Quy tắc thiết kế labels

**Nên dùng (được quản lý):**

- `route`: `payments|orders|webhooks|other`.
- `result`: `valid|invalid|not_evaluated|unavailable|error`.
- `reason`: `none|signature|credential|timestamp|replay|malformed|body_limit|dependency|internal`.
- `contract`: `v1|v2|unknown`.
- `region`/`cluster`/`gateway_group`: từ deployment config có danh sách giới hạn.

**Không dùng làm metric labels:**

- `X-Key-Id`, `X-Client-Id`, `X-Tenant-Id`, `X-Nonce` từ request.
- Full URL/path chứa resource ID hoặc email.
- Chữ ký, token, body hash, raw canonical request.
- `exception.getMessage()`, arbitrary header values, user-agent nguyên bản.
- IP address từng client, request ID/trace ID.

Với cardinality hữu hạn, kiểm toán số series thực được scrape sau mỗi lần bổ sung nhãn mới. Alert khi số series tăng đột biến hoặc exporter bắt đầu bị nghẽn.

### Histogram và nhãn

Histogram có nhiều bucket, mỗi tổ hợp labels nhân thêm nhiều series `_bucket`. Do đó, với Timer nên dùng **ít nhãn hơn counter**; ví dụ code chỉ dùng `route` và `result`, không thêm `reason`/contract vào histogram latency.

## 16. Dashboard: nhìn một hệ thống HMAC hoàn chỉnh

Một dashboard production hữu ích nên có các nhóm thông tin cùng thời gian quan sát (ví dụ 5 phút và xu hướng 24 giờ):

### A. Authentication volume và chất lượng

- Tổng số authentication attempts/giây.
- Valid/invalid/not_evaluated/unavailable/error theo route.
- Tỷ lệ `valid/(valid+invalid)` và **coverage**.
- Tỷ lệ invalid theo reason cố định.
- So sánh cùng thời điểm tuần trước hoặc giai đoạn trước deploy.

### B. HMAC security posture

- Replay rejection rate.
- Timestamp rejection rate và clock skew.
- Credential invalid/revoked trends.
- Key rotation progress theo nhóm `legacy/current`.
- Số probe key-revoked được từ chối đúng sau source update.

### C. Tính sẵn sàng

- `unavailable` và `error` trong authentication attempts.
- Nonce store latency, timeout, eviction, failover.
- Credential registry/secret manager latency và lỗi.
- Tỷ lệ request bị gateway trả 413/429/502, đối chiếu với backend metrics.

### D. Latency và quyền

- HMAC authentication p50/p95/p99 hoặc histogram.
- HTTP server p95/p99 theo route; không nhầm với HMAC latency.
- Authorization allow/deny sau authentication.
- 401/403/429/503 theo tầng gateway/service.
- Business success/error hoặc payment idempotency conflict ở dashboard nghiệp vụ riêng.

**Không đặt “HMAC valid = 98%” làm chỉ số duy nhất.** Một tấn công tạo nhiều request HMAC sai có thể làm valid ratio giảm dù hệ thống **đang chặn đúng**. Ngược lại, tỷ lệ valid cao có thể che việc HMAC filter không được áp trên một route nguy hiểm. Cần dùng kết hợp coverage, probe chain, error/latency và policy checks.

## 17. Cảnh báo: chọn điều kiện hành động được

Đây là các ví dụ alert **để tùy chỉnh theo baseline và SLO**, không phải ngưỡng chuẩn chung:

| Alert | Tín hiệu | Hành động điều tra |
| --- | --- | --- |
| Authentication dependency unavailable | `result="unavailable"` tăng có ý nghĩa | Kiểm tra vault/registry/nonce store, fail closed |
| Replay spike | `reason="replay"` tăng so với baseline, đủ volume | Xem retry, client signer, filter double registration |
| Signature mismatch spike | `reason="signature"` tăng sau deploy | Kiểm tra canonical contract, proxy rewrite, key migration |
| Timestamp rejection spike | `reason="timestamp"` tăng | Clock sync, proxy delay, client SDK |
| HMAC p95 latency regression | Histogram p95 vượt SLO | Credential lookup, HMAC body buffering, nonce store |
| Revoked key accepted | Probe/audit thấy request bằng key revoked được chấp nhận | **Bảo mật nghiêm trọng**, kiểm tra stale cache/gateway |
| HMAC metrics silent | Không còn attempt metric dù ingress traffic còn | Kiểm tra filter chain, scrape/exporter, route bypass |
| Cardinality growth | Series count tăng bất thường | Kiểm tra label lấy từ raw input |
| Authorization denied spike | HMAC valid nhưng policy deny tăng | Tenant grants, resource owner, thay đổi policy |

### Một ví dụ PromQL alert theo số lượng

~~~promql
sum(
  increase(hmac_authentication_attempts_total{
    result="unavailable"
  }[5m])
) > 10
~~~

Ngưỡng 10 attempt/5 phút chỉ để minh họa. Với một API ít lưu lượng, 1 lần unavailable có thể rất quan trọng; với API nhiều triệu request, 10 lần có thể chưa đáng báo động. Nên phối hợp **số lượng tối thiểu + tỷ lệ + độ dài cửa sổ** theo đặc tính lưu lượng.

Ví dụ cảnh báo lỗi signature theo route:

~~~promql
sum by (route) (
  rate(hmac_authentication_attempts_total{
    result="invalid", reason="signature"
  }[10m])
)
/
clamp_min(
  sum by (route) (
    rate(hmac_authentication_attempts_total{
      result=~"valid|invalid"
    }[10m])
  ),
  0.000001
) > 0.10
~~~

`0.10` là **10%**. Cần thêm điều kiện lưu lượng đủ lớn và so với baseline; không tự gửi security incident chỉ vì một client mới ký sai 1–2 request.

### Theo dõi vắng mặt dữ liệu

Nếu HMAC attempt metric biến mất, tỷ lệ valid/invalid có thể không được tính — **không** được mặc định hiểu là hệ thống 100% hợp lệ. Quan sát thêm:

- Scrape `up` và freshness của sample.
- Counter HTTP ingress cho route bắt buộc HMAC.
- Filter chain matcher/registration trong deployment.
- Synthetics gửi request sai chữ ký phải bị từ chối.
- Synthetics gửi một request hợp lệ (với test credential và môi trường bảo vệ) phải được đo đúng một lần.

## 18. Synthetic probes và kiểm tra không bypass

**Metric chỉ đo những bước thật sự được instrument.** Nếu một route vô tình không đi qua HMAC filter, metric auth ở route đó có thể hoàn toàn im lặng trong khi HTTP handler vẫn xử lý request.

Do đó, bổ sung kiểm tra chủ động (*synthetic security probes*) trong môi trường được cấp phép:

1. Gửi request thiếu HMAC header tới endpoint bắt buộc → kỳ vọng 401, controller không chạy.
2. Gửi request key/test credential có chữ ký sai → kỳ vọng 401, metric invalid tăng.
3. Gửi request HMAC hợp lệ với nonce mới → metric valid tăng **đúng một**, nếu policy cho phép thực hiện một thao tác không có side effect hoặc dùng sandbox fixture.
4. Gửi lại cùng request/nonce → bị chặn replay, không có side effect.
5. Gửi một HMAC hợp lệ nhưng thiếu quyền tenant/resource → authentication valid và authorization deny, không rò dữ liệu.
6. Thử cùng test qua nhiều gateway/region để chứng minh nonce store và canonicalization nhất quán.
7. Thu hồi credential test rồi kiểm tra mọi verifier từ chối theo thời hạn cam kết.

**Không sử dụng key thật hoặc endpoint tạo payment sản xuất để làm probe tự động không kiểm soát.** Dùng tài khoản/credential thử nghiệm, route sandbox hoặc operation an toàn được định nghĩa trước. Những thao tác giám sát này vẫn phải tuân thủ authorization và rate limit phù hợp.

## 19. Kiểm thử Micrometer metric: đơn vị đếm và nhãn

Một unit test với `SimpleMeterRegistry` có thể chứng minh counter tăng đúng một lần, phân loại replay và tránh nhầm `valid` với `unavailable`.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import org.junit.jupiter.api.Test;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

class HmacAuthenticationMetricsTest {

    @Test
    void recordsValidAttemptExactlyOnce() {
        try (SimpleMeterRegistry registry =
                 new SimpleMeterRegistry()) {
            HmacAuthenticationMetrics metrics =
                new HmacAuthenticationMetrics(registry);

            metrics.record(
                HmacRouteGroup.PAYMENTS,
                HmacAttemptOutcome.VALID, "v1",
                12_000_000L);

            double count = registry
                .get("hmac.authentication.attempts")
                .tags(
                    "route", "payments",
                    "result", "valid",
                    "reason", "none",
                    "contract", "v1")
                .counter()
                .count();

            assertEquals(1.0, count);
        }
    }

    @Test
    void separatesReplayFromDependencyFailure() {
        try (SimpleMeterRegistry registry =
                 new SimpleMeterRegistry()) {
            HmacAuthenticationMetrics metrics =
                new HmacAuthenticationMetrics(registry);

            metrics.record(HmacRouteGroup.ORDERS,
                HmacAttemptOutcome.REPLAY_REJECTED, "v1", 6_000L);
            metrics.record(HmacRouteGroup.ORDERS,
                HmacAttemptOutcome.DEPENDENCY_UNAVAILABLE, "v1",
                8_000L);

            assertEquals(1.0, registry
                .get("hmac.authentication.attempts")
                .tags(
                    "route", "orders",
                    "result", "invalid",
                    "reason", "replay",
                    "contract", "v1")
                .counter().count());

            assertEquals(1.0, registry
                .get("hmac.authentication.attempts")
                .tags(
                    "route", "orders",
                    "result", "unavailable",
                    "reason", "dependency",
                    "contract", "v1")
                .counter().count());

            assertEquals(2L, registry
                .find("hmac.authentication.duration")
                .tag("route", "orders")
                .timers().stream()
                .mapToLong(timer -> timer.count())
                .sum());
        }
    }
}
~~~

Đoạn test dùng Micrometer và JUnit Jupiter. `registry.find(...).tag(...).timers()` truy vấn các Timer cùng tên và route nhưng có nhãn `result` khác nhau; khi nâng cấp Micrometer, cần kiểm tra hành vi tìm meter theo phiên bản thực tế trong dự án.

### Những trường hợp unit/integration quan trọng khác

- 100 lần record `valid` cho 100 attempts → counter đúng 100, không phụ thuộc response HTTP.
- 1 request bị HMAC sai → invalid một lần, không ghi thêm valid.
- 1 request HMAC đúng nhưng 403 do tenant policy → valid một lần, authorization deny một lần.
- 1 request HMAC đúng nhưng controller trả 500 → valid một lần, HTTP 500 metric riêng.
- 1 request HMAC đúng nhưng nonce duplicate → invalid/replay một lần.
- Replay store timeout → unavailable một lần, **không** invalid và không valid.
- Body quá lớn trước verify → not_evaluated nếu đã vào boundary, HTTP 413 riêng.
- Sai header version tùy ý → `contract="unknown"`, không sinh label mới.
- URI có hàng nghìn resource IDs → không sinh hàng nghìn `route` labels.
- MeterRegistry lỗi → không làm request chưa được xác thực đi tiếp và không che lỗi security.
- Filter chạy lại ở `ERROR`/async dispatch → không tạo attempt trùng.
- HMAC filter không chạy ở route protected → synthetic probe phát hiện bypass.

### Kiểm thử với MockMvc và gateway

Với `MockMvc` có Spring Security chain thực, dùng **signer độc lập** với verifier. Chụp giá trị meter trước/sau mỗi request trong `SimpleMeterRegistry` rồi assert chênh lệch. Dùng `Clock` cố định, nonce store có test fixture và secret test. Không chỉ mock `AuthenticationManager` trả authenticated cho mọi request rồi coi đó là kiểm thử HMAC thật.

Chạy thêm E2E qua đúng gateway/proxy production topology để xác minh phép đếm không bị double qua các hop, không mất metric khi gateway rewrite path và nonce replay giữa nhiều instance được phát hiện.

## 20. Bài tập tình huống: dashboard báo “99% request hợp lệ”

Một đội vận hành báo cáo:

~~~text
hmac_valid_requests_total = 9900
http_requests_total = 10000
valid_request_rate = 99%
~~~

Tuy nhiên trong một giờ, thực tế có các sự kiện:

- 500 request bị gateway từ chối `413` trước khi đến backend.
- 300 request có chữ ký HMAC sai.
- 200 request HMAC đúng nhưng nonce bị replay.
- 150 request HMAC đúng nhưng thiếu quyền tenant.
- 100 request verifier không thể truy cập Redis nonce store.
- 20 request được xử lý bởi một route mới **không đi qua HMAC filter** vì matcher cấu hình sai.
- 50 request HMAC đúng nhưng controller trả lỗi JSON validation.

Hãy giải thích:

1. Vì sao lấy `http_requests_total` làm mẫu số của `hmac_valid_requests_total` có thể sai phạm vi?
2. 150 request bị 403 có được tính HMAC valid không? Tại sao?
3. 50 request JSON validation sai có thể vẫn là HMAC valid không?
4. 100 request Redis store unavailable thuộc `invalid` hay `unavailable`?
5. 500 request bị gateway 413 có được tính vào counter auth backend không?
6. Một request replay có MAC khớp nên ghi `valid` hay `invalid` theo contract bài này?
7. Làm sao phát hiện 20 request bypass HMAC filter khi metrics auth không ghi?
8. Vì sao không dùng `X-Client-Id` hoặc `X-Nonce` làm label trên Prometheus?
9. Nếu gateway và backend cùng ghi counter tên `hmac_valid_requests_total`, việc `sum` làm sai thế nào?
10. Cần dashboard/cảnh báo nào để phân biệt tấn công, cấu hình proxy lệch và lỗi secret/replay store?

**Định hướng:** chốt attempt boundary và kết luận cuối của authentication; phân loại `valid/invalid/not_evaluated/unavailable/error` trước khi tính tỷ lệ. 403 và JSON validation có thể nằm sau HMAC valid. Gateway 413 và đường bypass cần đo/kiểm thử riêng. Nonce replay là authentication invalid theo hợp đồng này, không phải MAC invalid về mặt mật mã. Cardinality phải hữu hạn; đo một request ở một measurement authority và dùng probe để phát hiện đường thiếu filter.

## 21. Checklist đưa metric request hợp lệ vào production

- Có định nghĩa bằng văn bản về **HMAC-valid**: đúng credential/key state, canonical signature, timestamp và nonce claim; **không đồng nghĩa** HTTP 2xx/authorization.
- Có định nghĩa **attempt boundary** theo route và tầng đo; mỗi attempt kết thúc bằng đúng một outcome terminal.
- Outcomes có tập giá trị cố định; phân biệt `valid`, `invalid`, `not_evaluated`, `unavailable`, `error`.
- `reason` chỉ đến từ enum server-side, không lấy exception message hoặc header nguyên văn.
- Counter HMAC nằm ở đúng verifier authority; gateway/backend không cùng đếm một request vào cùng tổng.
- Authentication metrics được ghi trước controller, không đổi vì authorization/DB/HTTP error.
- Metric latency đo **riêng thời gian authentication**, không lẫn business processing.
- Prometheus exporter/tên counter/timer/histogram đã được xác nhận từ dữ liệu thực; query có namespace environment/cluster đúng.
- Dashboard có valid ratio **và** evaluated coverage; khoảng không có traffic hiển thị N/A.
- Label cardinality thấp: route group, result, reason, contract version, region có kiểm soát.
- Không có key ID, client ID, tenant ID, nonce, IP, signature, URL động hoặc request ID trong metric labels.
- Tracing/audit có correlation ID và retention/access control thích hợp, không log secret/body nhạy cảm.
- Replay store latency, error, eviction, TTL và failover được quan sát; không coi unavailable là invalid.
- Key rotation theo phiên bản được giám sát bằng nhãn hữu hạn; revocation enforcement có test và alert.
- Signature mismatch theo gateway/contract được quan sát để nhận diện canonicalization drift.
- Cảnh báo có lưu lượng tối thiểu và baseline; phân biệt lượng request giả tăng với verifier gặp lỗi.
- Có synthetic probes kiểm tra route bắt buộc HMAC không bị bypass, nonce replay bị chặn và key revoked thật sự bị từ chối.
- Unit tests kiểm tra **không double count** và classification; integration tests chạy credential, signer và nonce store thật.
- Gateway E2E tests kiểm tra ingress chặn trước backend, route rewrite, multi-instance replay và metric duplication.
- Hệ thống **fail closed** khi thiếu bằng chứng xác thực; không được dùng telemetry failure để nới chính sách.
- Chỉ số “request hợp lệ” được đặt cạnh authorization-denied và HTTP/transaction results để tránh kết luận sai về quyền và nghiệp vụ.

**Metric request hợp lệ chỉ hữu ích khi nó ghi nhận đúng một kết luận HMAC authentication ở đúng ranh giới tin cậy.** Hãy đo sau khi kiểm tra credential, chữ ký, timestamp và nonce, trước authorization; phân biệt lỗi client với lỗi hạ tầng và request chưa được đánh giá; giữ labels hữu hạn; kiểm chứng qua gateway và nhiều instance. Khi đó, dashboard không chỉ cho biết “bao nhiêu request hợp lệ”, mà còn giúp phát hiện lỗi ký request, replay, key rotation, thiếu quyền và sự cố vận hành mà không hy sinh an toàn dữ liệu.
