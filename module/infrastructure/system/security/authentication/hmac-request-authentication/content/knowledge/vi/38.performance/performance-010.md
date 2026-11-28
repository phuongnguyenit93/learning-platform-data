# Tối ưu đường đi request khi xác thực HTTP bằng HMAC

## 1. Bài toán: giảm độ trễ nhưng không bỏ một bước bảo mật nào

Trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, mỗi HTTP request từ client được xác thực bằng HMAC sử dụng **shared secret** và một **canonical request** do hai phía thỏa thuận. Hợp đồng ký có thể bao gồm method, URI, tập header và/hoặc digest của body. Hệ thống đồng thời xác minh timestamp và nonce để chống replay, quản lý key rotation, hoạt động qua proxy/gateway và **phân biệt xác thực với phân quyền**.

Chương **Performance** đặt câu hỏi: với cùng các bảo đảm bảo mật, làm sao **tối ưu đường đi request** từ gateway đến handler nghiệp vụ, để giảm p95/p99, tăng throughput và hạn chế việc các request giả tiêu thụ tài nguyên đắt?

Ví dụ: đối tác gọi `POST /api/signed/payments` với JSON body 8 KiB. Trong một implementation chưa tối ưu, filter có thể tạo nhiều bản sao body, parse JSON để tính chữ ký, truy vấn key store và Redis đồng bộ, gọi external secret manager mỗi request rồi vẫn chạy controller khi nonce store lỗi. Đây không chỉ là vấn đề latency; một số lựa chọn còn làm **mất bảo đảm xác thực**.

Sau bài này, người học có thể:

1. Vẽ **critical path** của HMAC verification và đo thời gian ở từng chặng thay vì phỏng đoán.
2. Phân biệt kiểm tra đầu vào rẻ trước xác thực với các phép **xác thực bắt buộc**, không để “fast path” biến thành bypass.
3. Giảm số lần serialize/hash/copy body, key lookup, network round-trip và cache miss một cách có giới hạn.
4. Thiết kế xử lý đồng thời và backpressure cho Servlet/Spring MVC và Spring WebFlux.
5. Kiểm thử hiệu năng lẫn tính đúng đắn qua gateway, khi replay, revoke key và phụ thuộc bị lỗi.

> Các đoạn code và con số minh họa được viết cho mục đích học tập. HMAC không tự định nghĩa một chuẩn canonical HTTP duy nhất; thứ tự kiểm tra, status, encoding và chính sách cache phải tuân theo **hợp đồng ký thực tế**, không tự thay đổi để tối ưu.

## 2. Quan sát đường đi request hoàn chỉnh

~~~mermaid
flowchart TD
    A[Client ký request] --> B[Gateway / ingress]
    B --> C{Route HMAC + giới hạn ban đầu}
    C -- Không hợp lệ / quá tải --> X[400 / 413 / 429 theo policy]
    C -- Qua --> D[Đọc canonical inputs và body có giới hạn]
    D --> E[Validate timestamp / headers]
    E -- Sai --> Y[401, dừng]
    E -- Hợp lệ --> F[Key lookup + trạng thái key]
    F -- Key sai --> Y
    F -- Store lỗi --> Z[503; fail closed]
    F -- Key hợp lệ --> G[Canonicalize + SHA-256 + HMAC]
    G -- Không khớp --> Y
    G -- Khớp --> H[Claim nonce nguyên tử]
    H -- Replay --> Y
    H -- Store lỗi --> Z
    H -- Thành công --> I[Tạo Authentication]
    I --> J{Authorization}
    J -- Không đủ quyền --> K[403]
    J -- Đủ quyền --> L[Handler nghiệp vụ]
~~~

Trong hệ thống thực, một số bước có thể đổi thứ tự hoặc được thực hiện song song **sau khi kiểm tra điều kiện tiền đề**. Ví dụ có thể bắt đầu lookup key cùng lúc với việc hash body nếu đã có giới hạn request, admission control và không làm tăng chi phí xử lý request giả vượt quá mức cho phép. Tuy nhiên **không claim nonce trước khi chữ ký HMAC hợp lệ** và không thực hiện nghiệp vụ trước authn/authz.

### 2.1. Bước nào thuộc đường găng?

| Công đoạn | Chi phí thường gặp | Giới hạn cần bảo đảm |
|---|---|---|
| TLS/gateway routing | Kết nối, proxy hops, queue, WAF | Không chấp nhận header original-target không đáng tin |
| Đọc headers / kiểm tra định dạng | Parse và validate chuỗi | Giới hạn số lượng/độ dài, từ chối trùng header ký |
| Đọc body | Network transfer, copy/buffer, memory | Không thu vô hạn; ký đúng byte theo hợp đồng |
| SHA-256 body và canonicalization | CPU theo số byte body | Không hash hai representation khác nhau |
| Key lookup | Cache, DB/Redis/KMS/HSM I/O | Không chấp nhận key stale/revoked hoặc lấy nhầm tenant |
| HMAC verify | CPU/crypto provider hoặc remote HSM | Dùng key chính xác, compare byte phù hợp |
| Timestamp/nonce | Clock, một lần atomic store claim | Không bỏ nonce vì timeout/chi phí |
| Security context/authorization | Tạo principal, policy/resource checks | Không coi HMAC là quyền truy cập |
| Handler | Logic nghiệp vụ và downstream I/O | Chỉ chạy sau khi authentication/authorization đạt |

Một ước lượng đơn giản:

~~~text
request_security_latency ≈ critical_path(
    input validation,
    body capture/digest,
    key resolution,
    MAC verification,
    nonce claim,
    authz checks
)
~~~

Đây **không phải phép cộng số học bắt buộc**: nếu một số công việc chạy đồng thời, thời gian end-to-end phụ thuộc đường găng, hàng đợi và backpressure. Hãy dùng trace/span để đo đúng subscription/lifecycle thay vì cộng các timer vốn chồng lấn.

## 3. Quy tắc tối ưu quan trọng nhất: chặn sớm, không bỏ xác minh

**Early rejection** nên dành cho các điều kiện rẻ và có thể kiểm tra trước khi dùng tài nguyên đắt:

- Route không hỗ trợ hoặc method không được phép theo cấu hình server.
- Header bắt buộc không có, có nhiều giá trị trùng hoặc vượt giới hạn.
- `X-Key-Id`, version, timestamp, nonce và signature không đúng **cú pháp** (không cần biết secret để biết Base64 sai).
- Body vượt kích thước tối đa được API cho phép.
- Concurrency budget hoặc rate limit ở gateway/service đã vượt.

Các bước này **không phải bằng chứng client đã được xác thực**. Không lấy `X-Key-Id` hoặc `X-Tenant-Id` do client khai báo làm identity đáng tin trước khi verify HMAC. Thời gian trong header chưa ký cũng có thể bị giả: nếu kiểm tra timestamp sớm, metric và log phải hiểu đây là dữ liệu pre-auth.

Một thiết kế admission control hai tầng:

~~~text
Gateway:
    TLS + route + connection limit + header/body size cap
    + rate limit theo tín hiệu đáng tin có sẵn

Service:
    route matcher + parse strictly + local concurrency budget
    + HMAC verification + nonce + authorization
~~~

Gateway giảm tải, nhưng service vẫn kiểm tra ràng buộc của mình vì có thể có đường nội bộ, thay đổi cấu hình hoặc sai lệch giữa các proxy. Nếu request đến service bằng đường khác không được phép, phải chặn ở network/mTLS và lớp route policy; không để việc “gateway đã kiểm tra rồi” trở thành lý do bỏ HMAC.

### 3.1. Đừng tạo oracle khi làm fast reject

Kết quả “key ID không tồn tại”, “key bị revoke” và “MAC sai” có thể được gộp vào **401 Unauthorized** chung theo hợp đồng; tránh trả thông điệp cho biết key ID nào đang active. Thời gian xử lý cũng có thể khác nhau giữa cache hit và miss: đánh giá rủi ro enumeration và áp dụng giảm thiểu cần thiết, nhưng không hứa rằng mọi đường đi có thể đạt constant-time tuyệt đối qua network.

Nếu hạ tầng key/nonce không khả dụng, đó không phải bằng chứng credential sai. Phản hồi **503** (ví dụ) và **fail closed**; không trả 2xx bằng cách bỏ bước verification. Việc rate limit hợp lệ có thể trả **429** và body quá lớn có thể trả **413**. HMAC đúng nhưng principal thiếu quyền nên nhận **403** từ authorization.

## 4. Tối ưu canonical request và xử lý body

### 4.1. Một hợp đồng ký mẫu

Giả sử `HMAC-V1` thỏa thuận:

~~~text
HMAC-V1
<HTTP_METHOD_UPPERCASE>
<PUBLIC_RAW_PATH>
<PUBLIC_RAW_QUERY_OR_EMPTY>
<KEY_ID>
<UTC_TIMESTAMP>
<NONCE>
<LOWERCASE_HEX_SHA256_ORIGINAL_BODY_BYTES>
~~~

~~~text
bodyHash = SHA-256(body bytes)
canonical = joinWithLF(version, method, rawPath, rawQuery,
                       keyId, timestamp, nonce, lowerHex(bodyHash))
expected = HMAC-SHA256(secretBytes, UTF8(canonical))
~~~

Chữ ký phải dùng **cùng biểu diễn** ở client và server. `rawPath`, `rawQuery`, percent-encoding, signed headers, line ending, charset và cách xử lý query trùng đều phải được chuẩn hóa theo contract. Gateway rewrite `/public/v1/payments` thành `/payments` không được làm service dùng sai URI được ký; nếu nhận public target qua header nội bộ, service phải xác thực nguồn và đối chiếu route mapping.

### 4.2. Tránh parse/serialize JSON trước khi hash

Không làm:

~~~java
// Không đúng nếu hợp đồng ký raw body bytes.
MyCommand command = objectMapper.readValue(rawBody, MyCommand.class);
byte[] reserialized = objectMapper.writeValueAsBytes(command);
byte[] digest = MessageDigest.getInstance("SHA-256")
        .digest(reserialized);
~~~

Ngay cả JSON có cùng ý nghĩa, serialization có thể khác thứ tự field, khoảng trắng, Unicode escape, số hoặc newline. Hãy hash **nguyên bytes đã được client ký** trước khi áp dụng validation nghiệp vụ. Khi cần JSON canonicalization, đó phải là **giao thức ký phiên bản hóa** được client và server cùng tuân thủ, không phải một thủ thuật tối ưu riêng ở server.

### 4.3. Giảm copy nhưng vẫn giữ body cho downstream

Hai trường hợp:

| Mô hình | Rủi ro khi filter đọc body | Hướng xử lý |
|---|---|---|
| Spring MVC/Servlet | `ServletInputStream` bị tiêu thụ; controller mất body | Wrapper có replay thực sự, giới hạn kích thước, quản lý bytes rõ ràng |
| Spring WebFlux | `Flux<DataBuffer>` có thể chỉ tiêu thụ một lần; pooled buffer rò bộ nhớ | Thu với hạn mức, release đúng buffer, `ServerHttpRequestDecorator` phát lại body |

`ContentCachingRequestWrapper` trong Servlet có chức năng lưu lại bytes đã đọc nhưng **không mặc nhiên làm request body có thể đọc lại** sau khi filter tiêu thụ input stream. Cần đánh giá wrapper/caching của stack cụ thể trước khi đưa vào security filter.

Với WebFlux, có thể dùng `DataBufferUtils.join(body, maxByteCount)` cho **request nhỏ có giới hạn**, copy bytes một lần để tính digest và cấp lại buffer mới cho downstream. Khi vượt giới hạn, trả 413, không chuyển tiếp handler. Nếu request là streaming hoặc file rất lớn, không thu vô hạn vào heap; cần phương án streaming digest/spooling có giới hạn và contract bảo đảm **xác thực trước mọi side effect**.

**Tối ưu “zero-copy” không mặc nhiên an toàn.** Khi dùng pooled buffers/Netty, phải chứng minh vòng đời, reference count và không sửa data trong lúc verify. Một bản copy có giới hạn rõ ràng thường đơn giản và an toàn hơn tối ưu sớm nhưng rò hoặc làm sai byte được ký.

### 4.4. Hash một lần, dùng lại kết quả hợp lệ

Nếu hợp đồng cần body digest để tạo canonical, hãy tính SHA-256 **một lần** cho bytes đã chụp và giữ digest trong phạm vi request:

~~~java
byte[] bodyHash = MessageDigest.getInstance("SHA-256")
        .digest(originalBodyBytes);
String bodyHashHex = HexFormat.of().formatHex(bodyHash);
// Dùng bodyHashHex khi tạo canonical request HMAC-V1.
~~~

Không lặp lại SHA-256 ở ba filter, interceptor, controller; nếu các thành phần khác cần hash thì chia sẻ kết quả nội bộ đã kiểm soát hoặc kiểm tra chúng có cùng representation hay không. Không dùng digest do client gửi để **thay thế** việc hash body thực tế: nếu hợp đồng chứa `Content-Digest`, verifier vẫn phải kiểm tra header digest bằng chính body nhận được và bảo đảm giá trị digest được ràng buộc bởi HMAC.

## 5. Key lookup: giảm remote I/O một cách có giới hạn

Truy vấn key theo `X-Key-Id` có thể phải đọc DB, Redis, secret manager hay HSM; độ trễ đuôi và quota dịch vụ thường đáng quan sát hơn vài phép nối chuỗi Java. Các cách tối ưu:

1. **Tra đúng một key ID có cú pháp hợp lệ**, không thử tuần tự mọi secret trong hệ thống.
2. **Cache có giới hạn** metadata/key reference hoặc secret nếu policy cho phép: có max size/weight, TTL và eviction.
3. **Single-flight per key** khi một cache entry hết hạn, tránh một nghìn request cùng miss tạo một nghìn lookup.
4. **Bulkhead/concurrency limit** và timeout cho remote lookup; bảo vệ hệ thống khi key store chậm.
5. **Negative cache có TTL ngắn và size cap** chỉ cho kết quả `NOT_FOUND` thực sự, không cache timeout như unknown key.
6. **Invalidation/versioning** phù hợp thời gian revoke tối đa cho phép; không tự cho dùng key stale khi store lỗi.

| Tình huống | Hành vi bắt buộc |
|---|---|
| Cache hit với key active | Vẫn kiểm tra hiệu lực/thu hồi theo policy và xác minh MAC trên request hiện tại |
| Cache miss, key tồn tại | Lookup từ nguồn tin cậy, verify key status, sau đó MAC |
| Key ID không tồn tại | 401 chung; không tiết lộ trạng thái key qua HTTP |
| Backend lookup timeout | Fail closed, thường 503; không coi là not found |
| Key vừa revoke | Không chấp nhận theo chính sách revoke đã công bố, kể cả replica có cache |
| Client liên tục gửi key ID ngẫu nhiên | Rate/concurrency limit, max negative entries; không làm phình metric/cache |

**Key ID là dữ liệu chưa xác thực.** Không dùng key ID raw làm metric tag vì cardinality và enumeration; không dựa vào `X-Tenant-Id` tự khai để cấp quyền hoặc trộn key giữa tenant. Nếu key ID chỉ unique trong tenant, lookup scope phải dựa vào dữ liệu có cơ sở tin cậy, không phải quyền tự khai của request.

### Key rotation không được hy sinh vì cache

Trong thời gian overlap, key `K1` và `K2` có thể đều còn hiệu lực theo policy. Sau khi `K1` bị thu hồi, bản cache cũ tại một replica có thể tạo lỗ hổng nếu vẫn cho ký bằng secret `K1`. TTL chỉ giới hạn **độ cũ**, không bảo đảm revoke tức thời. Nếu yêu cầu revoke tức thì, cần kiểm tra trạng thái online hoặc invalidation đáng tin cậy có chính sách cụ thể khi đường cập nhật bị lỗi.

**Không cache một `Authentication` thành công để dùng cho request mới.** Cùng key ID không có nghĩa HMAC của method, URI, body, timestamp, nonce trong request tiếp theo hợp lệ.

## 6. Nonce replay store: đường I/O bắt buộc

Sau khi MAC hợp lệ, verifier cần **claim nonce nguyên tử** theo scope key/client đã được xác thực. Với Redis, một lựa chọn là thao tác tương đương:

~~~text
SET hmac:nonce:<trusted-scope>:<hash(nonce)> 1 NX PX <ttl-ms>
~~~

`NX` và expiry phải được thực hiện **trong cùng thao tác atomic**, không dùng “GET rồi SET” trên hai lệnh rời; hai request đồng thời tới hai replica có thể cùng vượt qua nếu dùng check-then-write.

TTL phải bao phủ **toàn bộ thời gian một request đã được nhận có thể còn hợp lệ**. Ví dụ, với cửa sổ đối xứng `now ± W`, một request có timestamp sát biên tương lai có thể còn được chấp nhận thêm gần `2W` tính từ thời điểm ban đầu; TTL `W` tính từ lúc claim có thể quá ngắn. Chọn theo timestamp/clock contract và có safety margin.

**Không cache kết quả “nonce chưa tồn tại” ở local memory.** Đây là dữ liệu trạng thái thay đổi sau mỗi claim. Không bỏ qua thao tác Redis chỉ vì nó tăng latency; việc đó mở cửa cho replay của request có MAC hợp lệ. Khi store lỗi, trả 503/fail closed, không coi kết quả là `true`.

### Nonce và idempotency khác nhau

Một payment request đã được xử lý nhưng response bị mất không nên được retry bằng đúng cùng signature/nonce. Client thường tạo timestamp/nonce/chữ ký mới cho request kế tiếp; nghiệp vụ dùng **idempotency key riêng** để tránh tạo hai giao dịch. “Tối ưu” bằng cách chấp nhận nonce đã dùng lại nếu cùng body không tương đương idempotency và có thể làm mất bảo đảm chống replay.

## 7. Song song hóa: chỉ khi không làm hỏng điều kiện tiền đề

Một ý tưởng thường gặp: trong lúc đọc body, cho key lookup chạy song song để giảm tổng latency.

~~~text
Sequential:
  validate input → capture/hash body → lookup key → MAC → nonce → authz

Controlled overlap (chỉ khi policy cho phép):
  validate + enforce limits
           ├─ capture/hash body có giới hạn ─┐
           └─ key lookup có budget / timeout ┤
                                             v
                                      verify MAC → nonce → authz
~~~

**Lợi ích chỉ xuất hiện** khi body transfer/hash và lookup cùng nằm trên critical path và thực sự có thể chồng lấn. **Chi phí và rủi ro**: nhiều request giả có thể kích hoạt remote key lookup **trước khi body hợp lệ/đủ nhỏ**; concurrency tăng làm đầy connection pool/key store, thậm chí p99 tệ hơn. Hãy cân nhắc:

- Có rate-limit và concurrency budget **trước khi bắt đầu lookup**.
- Client/key ID đã được kiểm tra cấu trúc, không tạo lookup cho input malformed.
- Body có Content-Length và kích thước theo policy, nhưng vẫn phải giới hạn **byte thực đọc**, vì Content-Length có thể vắng/không đáng tin.
- Timeout/deadline và cancel được truyền đến các nhánh reactive; một nhánh thất bại phải dừng nhánh còn lại khi thích hợp.
- Key lookup được instrument để phân biệt số lookup thật và số request bị hủy.
- Chỉ triển khai sau benchmark chứng minh giảm p95/p99 ở tải có ý nghĩa.

Trong nhiều hệ thống, **tuần tự với giới hạn chặt** an toàn và dễ dự đoán hơn parallel quá sớm. Đừng tối ưu chỉ dựa trên tốc độ một request khi kho khóa đang rảnh.

## 8. Ví dụ Java 17+/Reactor: giữ đường xác thực rõ ràng

Ví dụ giả định filter WebFlux đã đọc body **một lần với giới hạn**, khôi phục body cho handler và trích xuất các header ký **đúng một giá trị** theo hợp đồng. Logic dưới đây không đọc body hoặc thao tác HTTP response; nó cho thấy cách nối các bước từ key lookup tới nonce mà **không block event-loop**.

~~~java
import java.time.Instant;

public record SignedRequestData(
        String method,
        String publicRawPath,
        String publicRawQuery,
        String keyId,
        String timestamp,
        String nonce,
        byte[] bodyBytes,
        byte[] receivedMac) {
    // Byte arrays là snapshot trong phạm vi request, không mutate sau khi ký.
}
~~~

~~~java
import org.springframework.security.core.Authentication;
import reactor.core.publisher.Mono;

public interface ActiveHmacKeyStore {
    // Trả key còn trong policy; unavailable -> Mono.error(...).
    Mono<HmacKey> findActive(String keyId);
}

public interface AtomicNonceStore {
    // true = claim mới thành công; false = replay.
    // Không thể truy cập store -> Mono.error(...), không default true.
    Mono<Boolean> claimOnce(String trustedScope, String nonce, Instant expiresAt);
}

public interface HmacCrypto {
    // Tính canonical và so sánh MAC từ byte với phương pháp phù hợp.
    // Không tự sửa path/query/body theo ý backend.
    boolean matches(HmacKey key, SignedRequestData request);
}

public interface HmacPrincipalFactory {
    Authentication authenticated(HmacKey verifiedKey);
}
~~~

Mẫu điều phối (giả định `HmacKey` chứa `keyId`, `clientId` và trạng thái hiệu lực được store kiểm tra):

~~~java
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import reactor.core.publisher.Mono;

public final class ReactiveHmacAuthenticationService {
    private final ActiveHmacKeyStore keys;
    private final AtomicNonceStore nonces;
    private final HmacCrypto crypto;
    private final HmacPrincipalFactory principals;
    private final HmacFreshnessPolicy freshness;

    public ReactiveHmacAuthenticationService(
            ActiveHmacKeyStore keys, AtomicNonceStore nonces,
            HmacCrypto crypto, HmacPrincipalFactory principals,
            HmacFreshnessPolicy freshness) {
        this.keys = keys;
        this.nonces = nonces;
        this.crypto = crypto;
        this.principals = principals;
        this.freshness = freshness;
    }

    public Mono<Authentication> authenticate(SignedRequestData request) {
        // validateFormatAndLimits do HTTP adapter làm trước khi vào đây.
        // freshness phải parse đúng hợp đồng, dùng clock từ server.
        return Mono.defer(() -> {
            if (!freshness.accepts(request.timestamp())) {
                return Mono.error(new BadCredentialsException(
                        "Invalid HMAC credentials"));
            }

            return keys.findActive(request.keyId())
                    .switchIfEmpty(Mono.error(
                            new BadCredentialsException(
                                    "Invalid HMAC credentials")))
                    .flatMap(key -> {
                        if (!crypto.matches(key, request)) {
                            return Mono.error(new BadCredentialsException(
                                    "Invalid HMAC credentials"));
                        }

                        // Scope và expiry lấy từ chính sách server/key đã verify.
                        String scope = key.clientId() + ":" + key.keyId();
                        Instant expiry = freshness.nonceExpiry(
                                request.timestamp());

                        return nonces.claimOnce(scope, request.nonce(), expiry)
                                .flatMap(claimed -> claimed
                                        ? Mono.just(principals.authenticated(key))
                                        : Mono.error(new BadCredentialsException(
                                                "Invalid HMAC credentials")));
                    });
        });
    }
}
~~~

**Đây là thiết kế minh họa, chưa phải code production hoàn chỉnh.** Các type `HmacKey` và `HmacFreshnessPolicy` được cố ý để dưới dạng hợp đồng; implementation phải áp dụng chuẩn hóa canonical, key rotation, đồng hồ server, bounds, tenant isolation, atomic nonce claim, response error và body replay. Tại lớp adapter:

- Lỗi key/nonce store phải được **phân loại riêng** và chuyển thành `AuthenticationServiceException` hoặc loại tương đương để trả 503; không biến lỗi này thành credential invalid rồi trả 401 hoặc bỏ qua.
- `HmacCrypto.matches` dùng `Mac` riêng theo request hoặc implementation thread-safe có kiểm chứng, so sánh MAC theo byte (ví dụ `MessageDigest.isEqual`).
- Chỉ kết quả `Authentication` đã xác thực và có authority từ dữ liệu phía server mới vào Spring Security; **authorization** kiểm tra scope, tenant và resource sau đó.
- Với WebFlux, filter tiếp tục chain bằng publisher và `ReactiveSecurityContextHolder`; không gọi `block()` hoặc `subscribe()` thủ công. Trong Spring MVC, filter/manager dùng API phù hợp và không để controller chạy sau lỗi.

### 8.1. Tránh biến onErrorResume thành bypass

Sai:

~~~java
// TUYỆT ĐỐI KHÔNG làm: khi Redis lỗi thì cho request qua.
return nonces.claimOnce(scope, nonce, expiry)
        .onErrorReturn(true);
~~~

Đúng về mặt chính sách:

~~~java
return nonces.claimOnce(scope, nonce, expiry)
        .onErrorMap(error -> new AuthenticationServiceException(
                "Nonce store unavailable", error));
~~~

Nếu `false` vì nonce đã có, trả credential error/replay theo hợp đồng; nếu store phát exception, trả lỗi hạ tầng và dừng. Không đẩy một `AuthenticationServiceException` bắt nguồn từ nonce store xuống nhánh kiểm tra credential thông thường.

## 9. Tối ưu trong Spring Security filter chain

**Chỉ bảo vệ đúng route:** sử dụng `SecurityFilterChain` / `SecurityWebFilterChain` với matcher rõ ràng. Mọi route bắt buộc HMAC phải đi qua verifier; không vì giảm latency mà chuyển route sang `permitAll` hoặc bỏ filter trước khi mapping được kiểm tra.

**Thứ tự filter:** đặt bước xác thực đủ sớm trước khi controller chạy, đủ muộn để các thành phần cần thiết của request đã tồn tại theo contract. Không đọc body trong nhiều filter khác nhau. Authentication failure phải dừng chain; authentication success mới đưa principal vào `SecurityContext` phù hợp.

**Tách authentication với authorization:** có thể tận dụng dữ liệu client ID/authority đã được xác minh từ key record, nhưng không bỏ kiểm tra quyền endpoint/resource. Mã lỗi 401 cho credential sai; 403 cho principal có xác thực nhưng thiếu quyền.

**Chống double registration:** với WebFlux, tránh đăng ký cùng một custom `WebFilter` toàn cục và thêm nó vào `SecurityWebFilterChain` một lần nữa. Với Servlet, xác định rõ registration và Spring Security filter ownership để không chạy HMAC hai lần.

**Không tái dùng Authentication giữa các request chỉ vì key ID giống nhau.** Một request mới có method/URI/body/timestamp/nonce riêng và cần HMAC verification riêng. Caching policy data khác với caching kết quả credential verification.

## 10. Đo hiệu năng bằng metrics và tracing, không đoán

### 10.1. Các span/timer đáng có

| Metric / span | Nội dung đo | Chú ý |
|---|---|---|
| `hmac_request_auth_duration` | Thời gian từ bắt đầu đến quyết định authn | Phân biệt accepted/rejected/unavailable |
| `hmac_body_capture_duration` | Thời gian thu/hash payload có giới hạn | Đi kèm kích thước body theo bucket kiểm soát |
| `hmac_key_lookup_duration` | Cache + remote key resolution | Outcome hit/miss/found/not_found/error |
| `hmac_crypto_duration` | Canonical/hash/MAC nếu cần phân rã | Đừng log canonical bytes hoặc secret |
| `hmac_nonce_claim_duration` | Atomic claim trên store | Ghi rejected/replay/unavailable |
| `hmac_authorization_duration` | Policy/resource ownership sau authn | Không gộp với “bad MAC” |
| `http_server_requests` | Toàn bộ độ trễ request, status và route | Theo route template, không raw URI |

Đối với request dùng HMAC, thời gian **hash body** có thể nằm trong bước body capture hoặc crypto timer; hãy mô tả ranh giới cụ thể để không cộng một thao tác hai lần. Metrics riêng có thể được đặt ở Spring filters, HTTP client, Redis/database driver hoặc Micrometer observation; tránh instrument trùng một dependency.

**Không dùng** `X-Key-Id`, `X-Nonce`, chữ ký, body hash, raw path/query, request ID hoặc client IP làm metric label. Chúng có cardinality lớn, có thể chứa dữ liệu nhạy cảm hoặc bị attacker điều khiển trước khi xác thực. Chọn route ID/template từ server và outcome/reason từ enum hữu hạn.

### 10.2. Ví dụ Micrometer Timer với Reactor

Một wrapper đo thời gian subscription của key lookup:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import reactor.core.publisher.Mono;

public final class KeyLookupTimer {
    private final MeterRegistry registry;
    private final ActiveHmacKeyStore delegate;

    public KeyLookupTimer(
            MeterRegistry registry, ActiveHmacKeyStore delegate) {
        this.registry = registry;
        this.delegate = delegate;
    }

    public Mono<HmacKey> findActive(String keyId) {
        return Mono.defer(() -> {
            long start = System.nanoTime();
            return delegate.findActive(keyId)
                    .doFinally(signal -> Timer.builder("hmac.key.lookup.duration")
                            .tag("phase", "repository")
                            .tag("signal", switch (signal) {
                                case ON_COMPLETE -> "complete";
                                case ON_ERROR -> "error";
                                case CANCEL -> "cancel";
                                default -> "other";
                            })
                            .register(registry)
                            .record(System.nanoTime() - start,
                                    TimeUnit.NANOSECONDS));
        });
    }
}
~~~

`ON_COMPLETE` trong code chỉ nói publisher **hoàn thành**, không phân biệt found và not-found; nếu cần phân loại, hãy đo thêm `doOnNext`/`switchIfEmpty` vào trạng thái đã kiểm soát. `doFinally` chạy khi kết thúc hoặc hủy subscription; khi operator bị subscribe lại do `retry`, mỗi lần subscribe có thể là một phép đo riêng. Việc này hợp lý cho metric **repository attempt**, nhưng khác metric **một HTTP request**. Phải công bố mẫu số trước khi tạo dashboard.

### 10.3. Cách đọc biểu đồ

Một bộ dashboard nên có:

- p50/p95/p99 toàn request và p95/p99 authentication, chia theo route template.
- Key cache hit ratio, remote lookup QPS, timeout, eviction và inflight.
- Nonce store p95/p99, replay rejection và unavailable rate.
- CPU/GC/memory/Netty event-loop hoặc Servlet thread pool saturation.
- Request 401/403/413/429/503 theo reason nội bộ đã kiểm soát.
- Thay đổi deployment, proxy route mapping, key rotation/revoke và baseline trước/sau.

Đừng kết luận key lookup là nút thắt vì p99 request cao nếu histogram cho thấy request đang phải đợi gateway queue hoặc đọc body. Tương tự, cache hit ratio cao không chứng minh cache an toàn khi revoke.

## 11. Benchmark thực tế và fault injection

### 11.1. Phương pháp

Để so sánh hai phiên bản, phải giữ nguyên:

- Cùng contract HMAC, thuật toán/encoding, kích thước body, headers được ký và đường đi qua gateway.
- Cùng số replica, backend key store/nonce store, TLS, network latency và connection pool.
- Cùng phân phối key hot/cold, tỷ lệ key không tồn tại, tính hợp lệ của timestamp/nonce và tỷ lệ request bị từ chối.
- Cùng concurrency, ramp-up, thời gian chạy, CPU/memory limit, timeout và chính sách retry.
- Có warm-up cho JIT/cache, sau đó quan sát TTL expiry, cache miss spike và key rotation chứ không chỉ chạy trong thời gian cache còn nóng.

**Không đưa số benchmark giả làm kết quả thực.** Đặt giả thuyết ví dụ “bounded cache giảm p99 lookup nhưng có thể tăng rủi ro stale key”, đo trước/sau và ghi rõ cả giới hạn bảo mật lẫn môi trường chạy.

### 11.2. Test matrix bắt buộc

| Workload / failure | Yêu cầu đúng đắn | Chỉ số cần đo |
|---|---|---|
| Request hợp lệ, body nhỏ | 2xx/201 theo API, đúng một side effect | Total p95/p99, auth latency |
| Request hợp lệ, body sát giới hạn | Body không mất, ký byte đúng | Body memory/copy, GC, throughput |
| Body vượt giới hạn | 413, không đọc/buffer vô hạn | Memory, early reject latency |
| Key hot, cache warm | HMAC được kiểm tra **mỗi request** | Cache hit, key lookup p99 |
| Key cold, cache miss | Không bỏ verify | Remote lookup p95/p99, inflight |
| Random key IDs chưa tồn tại | 401, không làm cạn key store/cache | Backend QPS, 429, max entries |
| Một key hot hết TTL cùng lúc | Không tạo stampede quá giới hạn | Inflight lookup, single-flight hit |
| Key rotation K1→K2 | Nhận đúng key còn hiệu lực theo policy | Refresh latency, cache invalidations |
| Key revoke tại tải cao | Mọi replica ngừng nhận key theo policy | Revocation staleness, reject rate |
| Key store timeout/down | Fail closed, 503, không side effect | Circuit/bulkhead, timeout rate |
| Nonce store down | Fail closed, 503 | Availability/error rate |
| Replay cùng nonce tại hai replica | Tối đa một request claim thành công | Nonce contention and latency |
| Timestamp quá cũ hoặc tương lai | 401; không tạo authentication | Early reject latency |
| Proxy rewrite path/query/body ngoài hợp đồng | Chữ ký sai, không chạy nghiệp vụ | HMAC failure, gateway mapping |
| HMAC đúng, authority sai | 403, không side effect | Authz latency and status |
| Client retry với nonce mới, idempotency key cũ | Không tạo hai giao dịch | Idempotency success |

Các kiểm thử fault injection cần xác định **ranh giới side effect**: không chỉ assert HTTP status mà còn kiểm tra DB write, event publish, calls downstream và audit. Nếu filter trả 401 nhưng controller vẫn chạy, đó là lỗi nghiêm trọng dù latency trông rất tốt.

### 11.3. Tối ưu theo thứ tự ưu tiên

Trình tự đề xuất, điều chỉnh theo profiling:

1. **Đúng và đo được**: contract canonical/test vector, anti-replay, key revoke, authentication/authorization, metrics end-to-end.
2. **Chặn input rẻ và bounded**: route matcher, format, header/body size, rate/concurrency limit.
3. **Bỏ công việc lặp lại**: một lần capture/hash body, không parse/serialize lại, không chạy filter hai lần.
4. **Giảm remote I/O thật sự**: key cache/invalidation có policy, single-flight, pool và timeout; nonce vẫn atomic.
5. **Đo và điều chỉnh concurrency**: backpressure, bulkhead, connection limits, event-loop/Servlet thread pool.
6. **Cân nhắc overlap/pipelining**: chỉ khi an toàn trước input không tin và benchmark chứng minh lợi ích.
7. **Tối ưu vi mô**: object allocation, buffer copies, cách dựng canonical string hoặc crypto provider nếu profiler cho thấy cần.

Thứ tự này tránh “tối ưu” vài allocation Java trong khi p99 đang bị chi phối bởi một remote key lookup hoặc nonce claim.

## 12. Checklist thiết kế trước production

- [ ] Hợp đồng canonical request được version hóa: method, public path/query, signed headers, body representation, timestamp/nonce, encoding và algorithm.
- [ ] Gateway/reverse proxy không làm sai byte/URI được ký; mọi forwarded original-target metadata phải đến từ hop đáng tin.
- [ ] Kiểm tra sớm header/route/body bounds nhưng không gán danh tính từ key ID chưa được xác thực.
- [ ] Hash/body capture đúng một representation và có giới hạn; Servlet/WebFlux downstream vẫn đọc được body cần thiết.
- [ ] Key lookup có timeout, concurrency budget, cache bounded và chính sách revoke/invalidation rõ ràng.
- [ ] Cache hit vẫn bắt buộc tính và so sánh MAC trên **request hiện tại**, không tái dùng authentication cũ.
- [ ] Timestamp check dùng clock tin cậy; nonce claim nguyên tử sau khi MAC hợp lệ, TTL đủ cho replay window.
- [ ] Key rotation/tenant isolation/revoke được kiểm chứng trên mọi replica; stale key không trở thành bypass.
- [ ] Kho key/nonce lỗi fail closed; 401/403/413/429/503 có semantics đã công bố.
- [ ] Authorization vẫn kiểm tra authority/resource ownership trước nghiệp vụ.
- [ ] Metrics/tracing phản ánh đúng request boundary, không dùng high-cardinality hoặc secret tags.
- [ ] Test load gồm cache warm/cold, stampede, unknown IDs, body lớn, replay concurrent, proxy rewrite và fault injection.
- [ ] Chỉ tối ưu song song/zero-copy khi benchmark chứng minh lợi ích và test xác nhận an toàn buffer/cancellation.
- [ ] Không log secret, full signature, nonce hay raw body; sự kiện lỗi dùng reason tổng quát có kiểm soát.

## 13. Kết luận

Tối ưu đường đi HMAC không phải tìm cách “bỏ bớt security filter”, mà là **giảm công việc dư thừa và round-trip không cần thiết trong khi giữ nguyên mọi kiểm tra bắt buộc**. Lợi ích lớn thường nằm ở kiểm soát body, giảm miss của key lookup, giới hạn concurrency và đo đúng điểm nghẽn; đôi khi chỉ cần sửa một proxy rewrite hoặc double filter đã giải quyết vấn đề.

Một hệ thống được xem là tối ưu tốt khi các **chỉ số latency/throughput có cải thiện đo được** mà mọi invariant vẫn đúng: canonical request nguyên vẹn, MAC được kiểm tra cho từng request, nonce chống replay nguyên tử, key rotation/revoke tôn trọng policy, authorization độc lập và mọi lỗi không xác minh được đều **fail closed**. Đây là tiêu chí quan trọng hơn một con số p99 đẹp nhưng kèm đường bypass bảo mật.
