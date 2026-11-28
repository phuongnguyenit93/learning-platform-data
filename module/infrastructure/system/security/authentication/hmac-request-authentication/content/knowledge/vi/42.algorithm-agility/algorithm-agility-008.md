# Migration signature: chuyển đổi phiên bản chữ ký HMAC an toàn

## 1. Vấn đề thực tế: nâng cấp chữ ký mà không làm đứt kết nối client

Trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, client và server dùng **shared secret** để tạo và xác minh HMAC trên **canonical request** đã thỏa thuận. Hợp đồng ký có thể ràng buộc HTTP method, URI, một số header và/hoặc digest của body. Server còn phải chống replay bằng timestamp/nonce, quản lý vòng đời key, kiểm thử tuyến đi qua proxy/gateway và chỉ thực hiện **authorization** sau khi xác thực thành công.

Ở chương **Algorithm agility**, bài **Migration signature** bàn về cách thay đổi **signature suite** hoặc định dạng chữ ký khi đã có nhiều client sử dụng giao thức cũ. Một ví dụ là chuyển từ `HMAC-SHA256` profile V1 sang `HMAC-SHA512` profile V2; trong thực tế lý do chuyển đổi cũng có thể là chuẩn hóa canonical request, sửa một hợp đồng ký sai, đổi cách encode MAC, đáp ứng chính sách crypto hoặc ngừng hỗ trợ phiên bản cũ.

Đây không phải việc chỉ sửa:

~~~java
Mac.getInstance("HmacSHA256");
// thành
Mac.getInstance("HmacSHA512");
~~~

Nếu server đổi thuật toán mà không triển khai chuyển tiếp có kiểm soát, những SDK cũ sẽ gửi MAC không khớp. Nếu server cố “tự đoán” thuật toán hoặc thử từng key/thuật toán cho tới khi thành công, ứng dụng có thể vô tình tạo **downgrade path**, tăng tải, làm sai key/tenant mapping và khiến việc ngừng thuật toán cũ không thể hoàn tất.

**Mục tiêu học tập:**

1. Tách biệt **signature version**, **MAC algorithm**, **canonicalization version** và **key version**.
2. Thiết kế profile V1/V2 có định danh và **domain separation** rõ ràng, chỉ chấp nhận profile được server cho phép.
3. Lập kế hoạch rollout/overlap/cutover/deprecation/retirement với client cũ, có kiểm soát downgrade.
4. Giữ nguyên timestamp, nonce, key rotation, proxy compatibility và authorization trong suốt migration.
5. Viết Java 17 test signer/verifier, golden vector V1/V2 và các phép thử **negative**, concurrency và fail-closed.
6. Thiết kế metric và tiêu chí rollback để quan sát tiến độ chuyển đổi mà không tiết lộ secret.

> Trong bài này, “signature” là **HMAC message authentication code (MAC) chia sẻ bí mật**, **không phải chữ ký số bất đối xứng**. HMAC cung cấp xác thực nguồn đối với các bên cùng giữ secret và tính toàn vẹn dữ liệu; nó không cho phép một bên chứng minh không thể chối bỏ trước bên thứ ba như cơ chế chữ ký số có khóa riêng/khóa công khai.

## 2. Những khái niệm phải phiên bản hóa độc lập

| Khái niệm | Ví dụ | Tại sao phải tách? |
|---|---|---|
| Signature profile | `v1`, `v2` | Định nghĩa trọn bộ cách ký/xác minh một request |
| MAC algorithm | `HmacSHA256`, `HmacSHA512` trong JCA | Quy định primitive và kích thước output |
| Canonicalization version | `HMAC-V1-HS256`, `HMAC-V2-HS512` | Quy định bytes nào được ký và cách encode |
| Key ID | `partner-a-v1`, `partner-a-v2` | Chọn record khóa theo trust boundary |
| Secret material | Hai secrets độc lập, do server cấp | Bảo vệ quyền sử dụng MAC, cho phép revoke tách biệt |
| Key lifecycle | active, overlap, revoked, expired | Quyết định key có được phép dùng tại thời điểm verify |
| Client migration state | legacy, dual-capable, v2-required, retired | Quy định profile nào client được quyền dùng |
| Anti-replay state | timestamp window, nonce claim | Chặn phát lại request dù MAC vẫn đúng |
| Authorization policy | `payments:write`, tenant/resource ownership | Không phải bản thân profile HMAC |

**Key rotation** thay key/secret trong khi giữ nguyên thuật toán/hợp đồng ký; **signature migration** thay profile cách ký hoặc profile được hỗ trợ. Hai quá trình có thể diễn ra cùng nhau, nhưng không phải một. Nếu đổi cả thuật toán, canonicalization, key và gateway trong một đợt, sẽ rất khó xác định nguyên nhân của một làn sóng 401.

Ví dụ migration có kiểm soát:

~~~text
Trước:
  partner-a-v1 -> profile v1 -> HmacSHA256 -> secret S1

Trong overlap:
  partner-a-v1 -> profile v1 -> HmacSHA256 -> secret S1
  partner-a-v2 -> profile v2 -> HmacSHA512 -> secret S2

Sau cutover:
  partner-a-v1 -> REVOKED/RETIRED
  partner-a-v2 -> profile v2 -> HmacSHA512 -> secret S2
~~~

Từ đó thấy việc **cho phép** V1 trong một thời gian chỉ là cơ chế tương thích có hạn, không phải chính sách dự phòng vĩnh viễn.

## 3. Mô hình đe dọa khi hỗ trợ nhiều thuật toán

Một migration có thể gặp các lỗi sau:

1. **Algorithm downgrade:** kẻ tấn công sửa `X-Hmac-Version` từ `v2` thành `v1`; server tự hạ profile chỉ vì header yêu cầu.
2. **Algorithm confusion:** server tra key ID rồi thử `HmacSHA256`, `HmacSHA512` hay thuật toán khác tùy header không có whitelist.
3. **Canonical confusion:** V1 ký raw path, V2 ký normalized path; gateway và verifier lấy hai biểu diễn khác nhau dẫn tới xác minh một thao tác nhưng thực thi thao tác khác.
4. **Cross-version replay:** cùng một request và nonce hợp lệ được phát lại dưới profile còn được hỗ trợ, làm nghiệp vụ chạy hai lần.
5. **Key reuse:** dùng chung secret cho nhiều profile mà không có phân tách miền và không quản lý revoke riêng.
6. **Fallback oracle:** server trả phản hồi khác nhau giữa key tồn tại, profile được hỗ trợ, v1/v2 hay signature sai; attacker có thêm tín hiệu để dò credential hoặc policy.
7. **Retirement không đầy đủ:** một replica, region hoặc gateway vẫn chấp nhận profile đã bị cấm.
8. **Lỗi vận hành khi upgrade:** bật V2 sớm trước khi SDK có vector đúng, khiến request hợp lệ bị từ chối.

Một **profile selector** an toàn là điều kiện để chọn *một* bộ xác minh được phép, không phải mệnh lệnh từ client buộc server dùng thuật toán tùy ý.

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Validate header sizes / syntax / route]
    B --> C[Parse signature profile identifier]
    C --> D[Lookup key record và policy server]
    D --> E{Profile được phép cho key/client?}
    E -- Không --> R[401 chung; không fallback]
    E -- Có --> F[Canonicalize đúng profile + verify HMAC]
    F -- Không khớp --> R
    F -- Khớp --> G{Timestamp + nonce hợp lệ?}
    G -- Không --> R
    G -- Có --> H[Authentication từ key record đáng tin]
    H --> I{Authorization}
    I -- Không --> J[403]
    I -- Có --> K[Handler nghiệp vụ]
    D -- Store unavailable --> U[503; fail closed]
    G -- Nonce store unavailable --> U
~~~

Một số ứng dụng kiểm tra timestamp **trước** lookup/MAC để loại sớm request cũ; sơ đồ trên gom bước freshness với anti-replay để nhấn mạnh tính ràng buộc. Dù trình tự cụ thể thế nào, nonce phải được **claim nguyên tử sau khi MAC đã hợp lệ**, và dữ liệu từ header chưa có MAC không được coi là danh tính đã xác thực.

## 4. Định nghĩa hai signature profile bất biến

Giả sử hợp đồng ví dụ dùng:

| Thuộc tính | Profile V1 | Profile V2 |
|---|---|---|
| Header version | `X-Hmac-Version: v1` | `X-Hmac-Version: v2` |
| MAC JCA name | `HmacSHA256` | `HmacSHA512` |
| Domain prefix trong canonical | `HMAC-V1-HS256` | `HMAC-V2-HS512` |
| Body digest | SHA-256 raw body bytes | SHA-256 raw body bytes |
| MAC output | 32 bytes | 64 bytes |
| Signature wire encoding | Base64 chuẩn | Base64 chuẩn |
| Key ID ví dụ | `partner-a-v1` | `partner-a-v2` |
| Secret | `S1` | `S2`, khác S1 |
| Timestamp/nonce policy | Theo hợp đồng công bố | Cùng anti-replay security policy |

Trong bài này, **body digest SHA-256 không đổi** để tập trung vào việc migration thuật toán *HMAC*. Nếu cần đổi cả body digest, đó là thay đổi profile/canonicalization khác và phải có vectors/test tương ứng. **Không suy luận rằng HMAC-SHA512 mặc định đem lại lợi ích cần thiết so với HMAC-SHA256**; lựa chọn phụ thuộc yêu cầu bảo mật, hiệu năng, interoperability và chính sách của tổ chức.

### 4.1. Canonical request được ràng buộc bằng domain prefix

Ví dụ cả hai profile ký tám dòng, nối bằng LF, mã hóa UTF-8, không có LF kết thúc:

~~~text
<PROFILE_DOMAIN_PREFIX>
<METHOD_UPPERCASE>
<PUBLIC_RAW_PATH>
<PUBLIC_RAW_QUERY_OR_EMPTY>
<KEY_ID>
<UTC_TIMESTAMP>
<NONCE>
<LOWERCASE_HEX_SHA256_OF_RAW_BODY_BYTES>
~~~

Thay vì ký cùng một canonical text rồi chỉ đổi tên thuật toán trong header, prefix khác nhau làm **version/algorithm suite** trở thành một phần của input xác thực. Khi client đổi `X-Hmac-Version` mà giữ MAC cũ, bộ kiểm tra phải chọn profile khác và MAC **không thể hợp lệ** theo cùng hợp đồng.

**Domain prefix không thay thế policy.** Server vẫn phải biết key `partner-a-v2` **chỉ** được phép dùng profile V2; một header chưa ký không thể tự cấp quyền sử dụng V1.

### 4.2. Tại sao phải chọn một profile duy nhất?

Sai:

~~~java
// KHÔNG làm: client quyết định arbitrary JCA algorithm.
Mac mac = Mac.getInstance(request.getHeader("X-Hmac-Algorithm"));

// KHÔNG làm: thử lần lượt mọi phiên bản/key cho đến khi có MAC khớp.
for (String algorithm : allAlgorithms) {
    if (verifyUsing(algorithm, request)) {
        return authenticated;
    }
}
~~~

Đúng về tư duy:

~~~text
parse exact version token + key ID
  -> resolve server-owned key descriptor
  -> check key belongs to client/tenant and version policy
  -> select exactly one signature profile
  -> verify exactly one MAC under that profile
  -> check freshness and atomic nonce
  -> establish authenticated principal
~~~

Từ chối `v0`, `unknown`, `none`, field quá dài, header trùng, tên thuật toán không nằm trong allowlist và những tổ hợp `(keyId, profile)` không được server cấu hình chấp nhận. Không tự chuyển v2 → v1 khi HMAC v2 sai; lỗi chữ ký v2 phải dẫn đến **từ chối**, không phải một cơ hội cho thuật toán khác.

## 5. Ràng buộc signature profile với key và client policy

Một thiết kế mẫu là **key record thuộc đúng một profile**:

~~~text
keyId=partner-a-v1
client=partner-a
allowedProfile=v1
status=active during overlap, revoked after cutover

keyId=partner-a-v2
client=partner-a
allowedProfile=v2
status=active
~~~

Profile từ header được so sánh với profile gắn trong key record **trước** khi verify. Như vậy không có chuyện client tự lấy cùng key ID rồi đổi thuật toán. Khi profile V1 hết hỗ trợ đối với client, tất cả key V1 của client phải bị từ chối theo chính sách dù chữ ký SHA-256 còn đúng về mặt toán học.

Trong hệ thống multi-tenant, khóa tra cứu có thể cần scope tin cậy. Không sử dụng `X-Tenant-Id` chưa xác thực để cấp authority hoặc lấy secret của tenant khác. Một lựa chọn đơn giản là key ID global unique, sau khi MAC đúng thì lấy principal/tenant từ key record; một lựa chọn khác cần trusted route/client binding ngoài HMAC.

### 5.1. Bí mật và phân tách khóa

Ưu tiên **secret độc lập** cho V2 thay vì tái sử dụng bytes của secret V1:

- Có thể revoke key V1 mà không vô hiệu hóa key V2.
- Giảm nguy cơ một profile cũ làm lộ key của profile mới qua thao tác vận hành hoặc cấu hình.
- Giúp key rotation, audit và giới hạn thời gian overlap có ranh giới rõ.
- Tránh phụ thuộc vào việc hai cơ chế khác nhau có diễn giải chung cùng vật liệu khóa hay không.

Nếu hệ thống chủ động **derive** keys từ một master secret, phải dùng KDF đã được thiết kế cho mục đích này, với salt/context separation, label chứa profile/client/key epoch và quản lý master secret phù hợp; không tự tạo secret V2 bằng cách đơn giản như nối chuỗi `"-v2"` hoặc hash tùy tiện. Việc chuẩn hóa KDF và key hierarchy cần thiết kế bảo mật riêng.

Mọi secret chỉ tồn tại ở phía client và thành phần verify được phân quyền; không xuất trong log, test production hoặc payload HTTP. Cache secret cần giới hạn TTL, bộ nhớ, quyền truy cập và cơ chế revoke; không coi cache hit là lý do bỏ kiểm tra trạng thái key.

## 6. Chọn cách migrate: một chữ ký hay hai chữ ký

Có ba chiến lược thường gặp:

| Chiến lược | Cách hoạt động | Điểm mạnh | Rủi ro/đánh đổi |
|---|---|---|---|
| **Server hỗ trợ song song, client gửi một profile** | Mỗi request có `X-Hmac-Version`, key ID và một MAC | Đơn giản, rõ ràng, dễ ratchet từng client | Server phải hỗ trợ V1 trong overlap |
| **Dual-signature request** | Một request mang MAC V1 và V2 ở hai header có định danh rõ | Có thể so sánh/rollout theo giai đoạn | Nguy cơ downgrade, parsing ambiguity, tăng chi phí |
| **Endpoint/route versioning** | V1/V2 tách route hoặc host theo hợp đồng | Phân vùng policy và quan sát rõ | Cần bảo vệ path, gateway mapping và authz cho cả route |

Trong nhiều trường hợp, **server nhận V1/V2 đồng thời nhưng mỗi request chỉ có đúng một signature profile** là lựa chọn dễ kiểm thử nhất. Server duy trì allowlist trên mỗi client/key và thu hẹp dần V1.

### 6.1. Chính sách bắt buộc cho dual-signature

Nếu một request phải chứa cả `X-Signature-V1` và `X-Signature-V2`, phải công bố rõ:

1. Những header nào bắt buộc ở từng trạng thái, thứ tự kiểm tra và kết quả khi một header bị thiếu/trùng/malformed.
2. Các chữ ký có dùng **cùng canonical request và cùng byte body** hay không; nếu khác, cả hai signed targets phải ánh xạ đến **cùng operation**.
3. Client nào yêu cầu **V2 hợp lệ**: ở trạng thái `v2-required`, không được “cứu” request bằng MAC V1 nếu V2 sai.
4. Nếu policy tạm yêu cầu **cả hai MAC hợp lệ**, phải verify cả hai theo đúng key tương ứng; không dùng biểu thức “V1 đúng **hoặc** V2 đúng” vô điều kiện.
5. Nonce được claim **một lần** theo authenticated client/operation, tránh side effect hai lần do kiểm tra cả hai signature.
6. Thời hạn bỏ hẳn header V1 sau khi chuyển đổi, không giữ dual-signature vĩnh viễn.

**Dual-signature không làm request an toàn hơn nếu server luôn chấp nhận V1 như đường dự phòng.** Đối với client đã chốt `v2-required`, V1 chỉ có thể phục vụ telemetry không quyết định authentication (nếu policy cho phép), tuyệt đối không được bypass V2.

## 7. State machine migration trên từng client

Một rollout an toàn cần **quy tắc trạng thái server sở hữu**, không suy từ header do client tự gửi:

| Trạng thái client | V1 được phép xác thực? | V2 được phép xác thực? | Quy định |
|---|---|---|---|
| `legacy` | Có, tới thời hạn công bố | Có thể chỉ ở môi trường thử hoặc khi enable | Chưa mặc định bắt client dùng V2 |
| `dual-capable` | Có tạm thời | Có | Client có SDK hỗ trợ V2; đo mức sử dụng thực |
| `v2-required` | **Không** | Có | Ratchet một chiều; không fallback |
| `retired/disabled` | Không | Không nếu client/key bị disable | Không cấp Authentication |

~~~mermaid
flowchart LR
    A[legacy] --> B[dual-capable]
    B --> C[v2-required]
    C --> D[retired/disabled]
    C -. Không tự fallback .-> B
    B -. Chỉ rollback theo policy có kiểm soát .-> A
~~~

Migration state là một **chính sách bảo mật**. Client không thể tự viết `X-Migration-State: legacy` để được dùng V1. Tương tự, key bị revoke và timestamp ngoài window vẫn phải bị từ chối dù profile khác có thể xác minh MAC.

### 7.1. Các giai đoạn triển khai

**Giai đoạn 0 — Inventory và baseline.** Xác định các đối tác/SDK, key ID, thuật toán, canonicalization hiện dùng, public routes qua gateway, tỷ lệ 401/403/replay, phụ thuộc KMS/nonce và chất lượng dữ liệu quan sát. Không dựa vào raw key ID từ request chưa xác thực để kết luận một đối tác đang sử dụng V1.

**Giai đoạn 1 — Publish V2 contract.** Đóng băng profile ID, key format, signed fields, encoding, timestamp/nonce, expected HMAC vectors, HTTP status và proxy semantics. Client SDK và server test cùng vectors độc lập.

**Giai đoạn 2 — Server triển khai V2 nhưng không thay đổi mặc định cho client cũ.** Bật parser/allowlist V2, có key V2 giả trong staging, test qua gateway và store. Một request mang phiên bản lạ hoặc chuyển thuật toán không được làm verifier fallback V1.

**Giai đoạn 3 — Cấp key V2 và rollout client theo nhóm.** Cấp **secret mới**, seed trạng thái `dual-capable`, SDK ký V2; theo dõi lỗi theo route/profile, replay và 503, không log MAC/secret. Cho phép quay lại V1 **chỉ** với client còn nằm trong cửa sổ overlap theo policy.

**Giai đoạn 4 — Ratchet client sang `v2-required`.** Khi traffic V2 ổn định, backend ghi chính sách bắt buộc V2. Từ đây, V1 phải bị từ chối ngay cả khi signature đúng.

**Giai đoạn 5 — Retire V1 toàn hệ thống.** Revoke/delete key V1 theo vòng đời, bỏ allowlist và code hỗ trợ khi không còn phụ thuộc; xác minh tất cả gateway/region/replica từ chối V1. Tiếp tục giám sát thử nghiệm negative cho V1 sau khi retire.

### 7.2. Rollback không đồng nghĩa downgrade mở

Rollback phần mềm vì crash hoặc lỗi V2 không tự đồng nghĩa được phép bật lại V1 cho những client đã chuyển hoàn toàn. Nếu chính sách bắt buộc V2 đã được phê duyệt, việc hạ policy là **một quyết định bảo mật riêng**, có owner, thời hạn, giới hạn client và audit. Có thể sửa lỗi SDK, dùng key V2 mới hoặc triển khai hotfix mà vẫn giữ `v2-required`.

Một rollback có phạm vi phải luôn ghi:

- Ai phê duyệt, vì sao, thời hạn kết thúc và client/route được ảnh hưởng.
- Key V1 nào còn hiệu lực; key V1 đã revoke vì lộ bí mật **không được** tự kích hoạt lại.
- Metric sẽ cho biết khi nào bỏ trạng thái tạm và quay về V2-only.
- Tác động lên nonce replay, idempotency và những request đang in-flight.

## 8. Đảm bảo timestamp/nonce không mất tác dụng trong migration

Một request có MAC đúng vẫn có thể bị phát lại. Chuyển thuật toán không được tạo một “cửa sổ chống replay mới” chỉ vì request dùng profile V2.

**Timestamp:** server dùng clock đáng tin, định dạng UTC theo contract, giới hạn window; V1/V2 phải có chính sách rõ. Nếu muốn thay cửa sổ đồng thời với signature migration, đó là thay đổi khác cần test biên và thông báo riêng.

**Nonce scope:** thông thường bao gồm **authenticated client/key identity** và nonce. Khi cùng client có hai profile cùng hoạt động, cần đánh giá replay/cross-version: một nonce nên được dùng ở phạm vi giúp ngăn request nghiệp vụ được chấp nhận hai lần. Ví dụ:

~~~text
GOOD (nếu policy coi cùng client chia sẻ nonce namespace):
    nonceKey = hmac:nonce:<authenticated-client-id>:<hashed-nonce>

RISKY (nếu vô tình cho phép reuse xuyên profile):
    nonceKey = hmac:nonce:<profile>:<key-id>:<nonce>
~~~

Không phải mọi hệ thống đều phải dùng cùng scope client, vì có thể cần tách key/tenant. **Quy tắc đúng phụ thuộc threat model**, nhưng phải có test cho một nghiệp vụ được gửi lặp lại bằng những profile còn chấp nhận. Nếu hai request ký bằng hai key khác nhau nhưng cùng nonce và có cùng principal/operation, scope theo profile có thể vô tình cho cả hai qua.

**Atomic claim:** sau MAC thành công, thực hiện thao tác atomic như Redis `SET ... NX PX` với TTL phù hợp window timestamp; không `GET` rồi `SET`. Nếu nonce store không sẵn sàng, trả 503/fail closed, không bỏ qua vì đang rollout V2.

**Idempotency:** một client retry request thanh toán với timestamp/nonce/MAC mới vẫn có thể gây side effect lặp; cần idempotency key riêng ở tầng nghiệp vụ. Migration không thay thế chính sách idempotency.

## 9. Java 17: một profile registry có whitelist rõ ràng

Đầu tiên định nghĩa các profile được phép ở phía server. Đây là code minh họa giao thức hai phiên bản, không có cơ chế “nhận thuật toán bất kỳ từ header”:

~~~java
public enum HmacSignatureProfile {
    V1("v1", "HmacSHA256", "HMAC-V1-HS256", 32),
    V2("v2", "HmacSHA512", "HMAC-V2-HS512", 64);

    private final String wireVersion;
    private final String jcaName;
    private final String canonicalDomain;
    private final int macBytes;

    HmacSignatureProfile(
            String wireVersion, String jcaName,
            String canonicalDomain, int macBytes) {
        this.wireVersion = wireVersion;
        this.jcaName = jcaName;
        this.canonicalDomain = canonicalDomain;
        this.macBytes = macBytes;
    }

    public String wireVersion() { return wireVersion; }
    public String jcaName() { return jcaName; }
    public String canonicalDomain() { return canonicalDomain; }
    public int macBytes() { return macBytes; }

    public static HmacSignatureProfile fromWire(String version) {
        // Exact match: không trim hoặc lowercase để tự chữa lỗi hợp đồng.
        if ("v1".equals(version)) return V1;
        if ("v2".equals(version)) return V2;
        throw new IllegalArgumentException("Unsupported HMAC profile");
    }
}
~~~

Đầu vào `X-Hmac-Version` cần có đúng **một** giá trị, độ dài giới hạn, ký tự hợp lệ. Header trùng/chuỗi bất thường phải bị từ chối trước khi gọi `fromWire`. Đừng đăng ký thêm profile “legacy” tùy tiện bằng chuỗi client cung cấp.

### 9.1. Canonicalizer và MAC chỉ nhận profile đã cố định

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacProfileCrypto {
    private HmacProfileCrypto() {}

    public static String canonical(
            HmacSignatureProfile profile,
            String method, String publicRawPath, String publicRawQuery,
            String keyId, String timestamp, String nonce, byte[] body)
            throws GeneralSecurityException {

        // HTTP adapter phải giới hạn kích thước và ngăn CR/LF injection
        // trong những field phân tách bằng newline.
        String digestHex = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(body));
        return String.join("\n",
                profile.canonicalDomain(),
                method,
                publicRawPath,
                publicRawQuery == null ? "" : publicRawQuery,
                keyId,
                timestamp,
                nonce,
                digestHex);
    }

    public static byte[] compute(
            HmacSignatureProfile profile, byte[] secret,
            String canonical) throws GeneralSecurityException {
        Mac mac = Mac.getInstance(profile.jcaName());
        mac.init(new SecretKeySpec(secret, profile.jcaName()));
        return mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8));
    }

    public static String signBase64(
            HmacSignatureProfile profile, byte[] secret,
            String canonical) throws GeneralSecurityException {
        return Base64.getEncoder().encodeToString(
                compute(profile, secret, canonical));
    }

    public static boolean matches(
            HmacSignatureProfile profile, byte[] secret,
            String canonical, String receivedBase64)
            throws GeneralSecurityException {
        if (receivedBase64 == null || receivedBase64.length() > 128) {
            return false;
        }
        final byte[] supplied;
        try {
            supplied = Base64.getDecoder().decode(receivedBase64);
        } catch (IllegalArgumentException malformed) {
            return false;
        }
        if (supplied.length != profile.macBytes()) {
            return false; // Không chấp nhận MAC bị truncate.
        }
        byte[] expected = compute(profile, secret, canonical);
        return MessageDigest.isEqual(expected, supplied);
    }
}
~~~

**Lưu ý bảo mật và phạm vi:**

- `MessageDigest.isEqual` giúp so sánh byte theo cách chống timing leak tốt hơn `Arrays.equals` thông thường; nó **không** biến toàn bộ HTTP/key lookup thành constant-time. Lỗi không tồn tại key, profile sai và backend timeout vẫn cần policy response/log thích hợp.
- Không cắt bớt MAC để khớp với signature ngắn; nếu hợp đồng thật sự quy định truncation, phải có chính sách/độ dài bảo mật rõ ràng và vectors riêng.
- Mỗi lần compute tạo một `Mac` mới; không tái sử dụng đối tượng `Mac` mutable chung giữa nhiều thread.
- `String.join` ở đây dựa vào field đã được validate nghiêm ngặt. Nếu allow CR/LF, delimiter injection có thể tạo canonical collision. Hãy định nghĩa escaping/length-prefix hoặc whitelist chính thức trong contract khi field phức tạp.
- Khi sử dụng WebFlux, tránh buffer body không giới hạn; cần lấy đúng byte body đã ký và replay downstream an toàn, hoặc dùng streaming digest/spooling với policy rõ.

### 9.2. Server verifier: không có nhánh “thử V1 nếu V2 sai”

Pseudocode điều phối:

~~~java
// HTTP adapter đã kiểm tra header singleton, size, route và body bound.
HmacSignatureProfile wireProfile =
        HmacSignatureProfile.fromWire(rawVersionHeader);

KeyRecord key = keyRepository.lookup(rawKeyId);
// Unknown/revoked/expired -> 401 chung; repository unavailable -> 503.

if (key.profile() != wireProfile
        || !clientProfilePolicy.permits(key.clientId(), wireProfile)
        || !key.isActive(clock.instant())) {
    rejectGeneric401AndReturn();
}

String canonical = HmacProfileCrypto.canonical(
        wireProfile, actualMethod, trustedPublicRawPath,
        trustedPublicRawQuery, rawKeyId, rawTimestamp, rawNonce, rawBody);

if (!HmacProfileCrypto.matches(
        wireProfile, key.secretBytes(), canonical, rawSignatureHeader)) {
    rejectGeneric401AndReturn();
}

if (!freshnessPolicy.accepts(rawTimestamp, clock.instant())) {
    rejectGeneric401AndReturn();
}

// Claim nonce trên phạm vi principal đã verify, cùng quy tắc giữa V1/V2.
if (!nonceStore.claimOnce(key.clientId(), rawNonce, expiryFromPolicy)) {
    rejectGeneric401AndReturn();
}

Authentication authenticated = principalFactory.fromVerifiedKey(key);
// Sau đó Spring Security tiếp tục thực hiện authorization.
~~~

Đây là **pseudocode**, không phải servlet filter hoàn chỉnh: thiếu định nghĩa `KeyRecord`, `clientProfilePolicy`, parser và error handler; lớp production phải quản lý exception/timeout và dừng filter chain đúng chỗ. **Đặc biệt**, nếu key store/nonce store lỗi thì không được biến exception thành `false` rồi tiếp tục hoặc trả thành công. Không tạo principal từ key ID/tenant header trước khi MAC đúng.

**Không có:**

~~~text
if verify(v2) fails:
    try verify(v1)
~~~

Nếu profile V2 sai, kết quả là credential rejection. Mọi thay đổi từ V2 sang V1 đều phải là **request mới** do client tạo và chỉ được server chấp nhận khi policy client vẫn cho phép V1; không phải fallback âm thầm của verifier.

## 10. Golden vectors để kiểm chứng V1 và V2 độc lập

Hai vector dưới dùng **secret giả chỉ dành cho test**. Cùng method/path/query/body/timestamp/nonce; key ID, domain prefix, secret và MAC algorithm khác nhau:

~~~yaml
request:
  method: POST
  public_raw_path: /public/v1/payments
  public_raw_query: account=A123&mode=preview
  timestamp: "2026-11-28T10:00:00Z"
  nonce: fixture-nonce-001
  body_utf8_no_trailing_newline: '{"amount":125000,"currency":"VND"}'
  body_sha256_lowerhex: ed6cd11906e5c888e772cfd89895fcf7d069d3cd6f47711466b021ad263f76b1

v1:
  version_header: v1
  key_id: partner-a-v1
  domain: HMAC-V1-HS256
  secret_utf8: fixture-secret-v1-hmac-only
  algorithm_jca: HmacSHA256
  canonical_utf8_length_bytes: 181
  expected_signature_base64: "EL0QZgqMASU2lIEmtNkiZPBtUGuvLuX6glfKmcoueLU="

v2:
  version_header: v2
  key_id: partner-a-v2
  domain: HMAC-V2-HS512
  secret_utf8: fixture-secret-v2-hmac-only
  algorithm_jca: HmacSHA512
  canonical_utf8_length_bytes: 181
  expected_signature_base64: "eIcwrhmH7M3a/XQFtI3CjBRGCs4FEibkHYR7KyxiFyAtIzTjyh48Ni0VltS7nBlssGzQXgmkBkd650yJrA4Vmg=="
~~~

Các expected signature đã được tính từ byte canonical cố định, **không kèm newline cuối**. Vector v1/v2 đều dài 181 byte vì domain/key ID có độ dài bằng nhau; MAC dài lần lượt 32 và 64 byte.

### 10.1. Test vector Java/JUnit 5

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class HmacSignatureMigrationVectorTest {
    private static final byte[] BODY =
            "{\"amount\":125000,\"currency\":\"VND\"}"
                    .getBytes(StandardCharsets.UTF_8);

    private String canonical(
            HmacSignatureProfile profile, String keyId) throws Exception {
        return HmacProfileCrypto.canonical(
                profile,
                "POST", "/public/v1/payments",
                "account=A123&mode=preview",
                keyId, "2026-11-28T10:00:00Z",
                "fixture-nonce-001", BODY);
    }

    @Test
    void v1MatchesPublishedVector() throws Exception {
        String message = canonical(
                HmacSignatureProfile.V1, "partner-a-v1");
        byte[] secret = "fixture-secret-v1-hmac-only"
                .getBytes(StandardCharsets.UTF_8);

        assertEquals(181, message.getBytes(StandardCharsets.UTF_8).length);
        assertEquals(
                "EL0QZgqMASU2lIEmtNkiZPBtUGuvLuX6glfKmcoueLU=",
                HmacProfileCrypto.signBase64(
                        HmacSignatureProfile.V1, secret, message));
    }

    @Test
    void v2MatchesPublishedVector() throws Exception {
        String message = canonical(
                HmacSignatureProfile.V2, "partner-a-v2");
        byte[] secret = "fixture-secret-v2-hmac-only"
                .getBytes(StandardCharsets.UTF_8);

        assertEquals(181, message.getBytes(StandardCharsets.UTF_8).length);
        assertEquals(
                "eIcwrhmH7M3a/XQFtI3CjBRGCs4FEibkHYR7KyxiFyAtIzTjyh48Ni0VltS7nBlssGzQXgmkBkd650yJrA4Vmg==",
                HmacProfileCrypto.signBase64(
                        HmacSignatureProfile.V2, secret, message));
    }
}
~~~

Golden vectors có ích vì so sánh với **expected literal**, không tự so sánh signer với chính signer. Để đạt contract testing đa ngôn ngữ, nên thêm vector được xác nhận bằng SDK **độc lập** (ví dụ Java ↔ Go/Node) và chạy qua HTTP verifier thật; một test chỉ gọi `HmacProfileCrypto` chưa xác nhận security chain/HTTP header parsing hoạt động đúng.

## 11. Ma trận kiểm thử signature migration

Những test cốt lõi cần có:

| Trường hợp | Fixture / thao tác | Kỳ vọng |
|---|---|---|
| V1 hợp lệ trong `legacy` | Key V1 active, MAC SHA-256 đúng | Authn thành công, theo authz |
| V2 hợp lệ trong `dual-capable` | Key V2 active, MAC SHA-512 đúng | Authn thành công, theo authz |
| V1 sau `v2-required` | MAC V1 đúng toán học nhưng policy cấm | **401**, không side effect |
| V2 sau `v2-required` | MAC V2 đúng | Authn thành công |
| Thay `X-Hmac-Version` V2→V1 | Giữ key ID/MAC V2 | **401**, không fallback |
| Thay `X-Hmac-Version` V1→V2 | Giữ key ID/MAC V1 | **401** |
| V1 key ID + V2 profile | Đổi version, không đổi key record | **401** |
| V2 key ID + V1 profile | Đổi version, không đổi key record | **401** |
| Unknown profile/algorithm | `none`, `v3`, tên JCA tùy ý | Từ chối, không gọi thuật toán tùy ý |
| Version header thiếu/trùng/quá dài | Giá trị input malformed | **400/401** theo contract, không handler |
| Signature sai Base64/truncated | Độ dài MAC không đúng | **401**, không fallback |
| Signed path/query/body đổi | Giữ MAC cũ | **401** nếu field được ký |
| Client chỉ có scope read | MAC profile hợp lệ, gọi route write | **403**, không side effect |
| Timestamp expired/future | MAC đúng, clock fixture | **401** |
| Nonce replay cùng profile | Gửi lại request đã nhận | **401**, chỉ một side effect |
| Nonce reuse xuyên V1/V2 | Hai MAC hợp lệ, cùng client/nonce | Theo anti-replay scope, không xử lý hai lần |
| Key V1 revoked | MAC V1 đúng | **401** trên mọi replica |
| Key V2 revoked | MAC V2 đúng | **401**, không tự chuyển V1 |
| Key store/nonce store down | Inject timeout/unavailable | **503**, fail closed |
| Proxy rewrite public path | Request V1/V2 qua ingress thật | Canonical target đúng, không route bypass |
| Stale policy cache | `v2-required` vừa được bật | Replica không tiếp tục cho V1 quá SLA propagation |
| Dual-signature V2 hỏng | V1 đúng, V2 sai, client V2-required | **401**, không OR/fallback |

Với mỗi trường hợp bị từ chối, assert thêm: **controller không chạy**, không ghi DB, không publish event nghiệp vụ, không thực hiện downstream write. Một 401 đơn lẻ chưa chứng minh anti-downgrade: test có thể vô tình fail vì timestamp hoặc nonce cũ. Dùng `Clock.fixed` và nonce mới/namespace test riêng để cô lập nguyên nhân.

### 11.1. Test “downgrade fail” phải kiểm tra policy server

~~~java
// Pseudocode integration test qua Spring Security filter thật.
serverFixture.setClientState("partner-a", "v2-required");
serverFixture.seedKey("partner-a-v1", "v1", activeV1TestSecret);
serverFixture.seedKey("partner-a-v2", "v2", activeV2TestSecret);

// V1 MAC chính xác, timestamp hợp lệ, nonce chưa dùng.
HttpResponse<?> response = sendRequestSignedWithV1(
        "/public/v1/payments", "fresh-v1-nonce");

assertEquals(401, response.statusCode());
assertEquals(0, paymentSpy.createCount());
assertEquals(0, eventPublisherSpy.publishCount());
~~~

Đây là **pseudocode** của test harness. Test quan trọng ở chỗ **chữ ký V1 phải được chứng minh hợp lệ về mặt crypto**; nếu cứ ký sai MAC V1 rồi nhận 401, test chưa chứng minh policy ngăn downgrade.

### 11.2. Kiểm thử nhiều replica và cache

Chạy request V1/V2 qua ít nhất hai replica khi có load balancer:

1. Cả hai replica ban đầu nhận V1/V2 cho client `dual-capable`.
2. Thay chính sách client thành `v2-required` ở nguồn đáng tin.
3. Kiểm tra mọi replica từ chối V1 **trong giới hạn đồng bộ policy đã công bố**; không giả định cache TTL bảo đảm revoke tức thì.
4. Gửi hai request profile khác nhau với nonce đã chọn để xác minh anti-replay scope theo principal.
5. Giả lập key store/cache invalidation message trễ, gateway restart hoặc rollout nửa cụm.
6. Khi policy store không khả dụng và server không thể xác minh profile/key state cần thiết, phải fail closed thay vì dùng trạng thái cũ trái policy.

Không biến bài kiểm thử downgrade thành bài kiểm thử key store timeout: từng fixture phải điều khiển riêng freshness, key state, policy version và nonce state.

## 12. Gateway/proxy và canonicalization trong migration

Nhiều sự cố V2 chỉ xuất hiện sau ingress:

~~~text
Client:
   POST /public/v1/payments?account=A123&mode=preview
             |
             v
Gateway rewrites to:
   POST /payments?account=A123&mode=preview
             |
             v
Service HMAC verifier:
   must reconstruct trusted public target
   or explicitly sign a logical target by contract
~~~

Nếu V1 dùng raw public path còn V2 muốn dùng logical route ID, đó là **thay đổi canonicalization có nguy cơ cao**. Cần tài liệu hóa:

- Public path/query được lấy ở hop nào; có decode, re-encode, sort query, normalize dot segments hay không?
- `X-Original-URI`/`Forwarded` do ai tạo; ingress có strip header do client tự khai không?
- Phần nào của body/header được ký và proxy có làm thay đổi content-encoding/bytes không?
- Khi HTTP/2 `:path` chuyển sang HTTP/1.1 request-target, hai profile giữ cùng semantics hay không?
- Security matcher và authorization dùng **cùng effective operation/resource** mà MAC đã bảo vệ hay không?

Một hệ thống có thể chọn xác minh HMAC ở gateway rồi chuyển tiếp assertion đã được bảo vệ. Khi đó backend phải xác minh assertion đến từ gateway đáng tin và gắn đúng request target/operation, không nhận header “already authenticated” do client gửi.

**Không sửa lỗi signature V2 bằng cách bỏ URI/header/body khỏi canonical.** Nếu gateway biến đổi signed fields, cần sửa hợp đồng/hop trust và chạy lại golden vectors qua proxy thật.

## 13. Error semantics và bảo vệ thông tin khi migration

| Kết quả | HTTP gợi ý | Ghi nhận nội bộ |
|---|---|---|
| Unknown/expired/revoked key hoặc MAC sai | `401 Unauthorized` | `CREDENTIAL_INVALID` chung |
| Profile client không được phép hoặc đã retired | `401` | `PROFILE_NOT_ALLOWED` trong audit được bảo vệ |
| Version/header/signature không đúng cú pháp | `400` hoặc `401` theo policy | `CREDENTIAL_MALFORMED` |
| Key/nonce/policy store unavailable | `503 Service Unavailable` | `VERIFICATION_UNAVAILABLE` |
| HMAC hợp lệ nhưng principal thiếu quyền | `403 Forbidden` | `AUTHORIZATION_DENIED` |
| Body vượt giới hạn | `413 Payload Too Large` | `INPUT_LIMIT_REJECTED` |

Với 401, server cần đưa `WWW-Authenticate` challenge thích hợp. Nếu dùng scheme riêng như `WWW-Authenticate: HMAC realm="signed-api"`, đây là quy tắc API tự định nghĩa, **không phải thuật toán được Spring Security tự kích hoạt**. Response công khai không nên tiết lộ “key ID này vẫn còn V1”, expected signature, key material hay thông tin tenant khác.

Nguyên tắc log:

- Chỉ ghi reason enum, profile enum, outcome, HTTP status, route ID và correlation ID được bảo vệ.
- Không ghi secret, full HMAC, canonical request nhạy cảm, raw body hoặc raw query chứa PII.
- Không lấy `X-Hmac-Version` chưa parse hoặc `X-Key-Id` chưa xác minh làm tag metric chưa giới hạn.
- Giới hạn kích thước header, số lần thử và số lookup để tránh request có version/key ID ngẫu nhiên gây DoS hoặc memory/cardinality explosion.
- Phân biệt `profile_not_allowed` với `verification_unavailable` **trong nội bộ** để vận hành không nhầm lỗi rollout với sự cố key store.

## 14. Metrics, quan sát rollout và tiêu chí cắt V1

Một nhóm metric hữu ích:

~~~text
hmac_auth_requests_total{
  service="payments",
  route="payments.create",
  profile="v2",
  outcome="accepted",
  reason="none"
}

hmac_auth_requests_total{
  service="payments",
  route="payments.create",
  profile="v1",
  outcome="rejected",
  reason="profile_not_allowed"
}
~~~

Chỉ dùng những label cố định (version đã parse, outcome enum, reason enum, route ID). Không tag theo raw key ID, nonce, signature, tenant tự khai, IP hoặc trace ID.

### 14.1. Dashboard và alert

| Tín hiệu | Mục đích | Cần kết hợp |
|---|---|---|
| Tỷ lệ request xác thực thành công theo V1/V2 | Theo dõi adoption | Tổng traffic và client state đã kiểm chứng |
| V2 credential failure rate | Phát hiện SDK/canonical mismatch | Gateway deploy, encoding, key activation |
| `profile_not_allowed` tăng | Phát hiện client chưa migrate hoặc downgrade attempt | Deadline và kênh hỗ trợ đối tác |
| Replay rejection theo profile | Phát hiện lỗi nonce scope hoặc retry | Shared nonce store, concurrency |
| Key/policy store unavailable | Phát hiện gián đoạn hệ thống | 503, health/timeout/circuit |
| p95/p99 authn duration theo profile | So sánh chi phí HmacSHA256 và HmacSHA512 | Body size, key lookup, nonce latency |
| V1 accepted ở region đáng lẽ V2-only | Cảnh báo vi phạm chính sách | Policy cache/invalidation và release version |

Đừng chọn mốc retire V1 chỉ vì tổng lưu lượng V1 giảm xuống gần 0 trong vài giờ. Client theo lịch batch ít chạy, vùng ít traffic hoặc SDK dùng trong công việc định kỳ có thể chưa gửi request trong khoảng quan sát ngắn. Cần inventory client đáng tin, thời hạn migration, test chủ động, giao tiếp đối tác và kế hoạch xử lý ngoại lệ.

### 14.2. Tiêu chí trước khi bật `v2-required`

- Golden vectors V2 được client và server xác minh độc lập; HTTP integration test qua proxy xanh.
- Profile V2 có secret khác V1, key lifecycle và authz mapping được kiểm chứng.
- Không có lỗi 401/503 mới vượt ngưỡng quan sát ở những client được migrate.
- Nonce replay chạy nguyên tử trên toàn cụm, chống cross-version reuse đúng policy.
- Đã chuẩn bị truyền thông, cảnh báo, on-call, rollback có kiểm soát và tiêu chí retire key V1.
- Kết quả thử nghiệm `V1 signed correctly but v2-required => rejected` xanh trên mọi replica.

### 14.3. Sau khi retire V1

Không chỉ xóa mục trên dashboard. Cần từ chối đúng profile cũ ở tất cả ingress/service, gỡ key V1, xóa cấu hình allowlist và test một **MAC V1 hợp lệ về toán học** vẫn bị reject. Theo dõi metric `profile_not_allowed` để phát hiện client bị bỏ sót và thực hiện hỗ trợ có xác thực, không bật lại V1 đại trà.

## 15. Những lỗi triển khai phổ biến

**“Đã hỗ trợ V2 thì bỏ ngay V1”.** Nếu chưa inventory và phát key mới cho SDK cũ, nhiều request hợp lệ sẽ 401. Hãy có overlap có thời hạn, kế hoạch từng client và contract tests.

**“Thử lại bằng SHA-256 khi SHA-512 không khớp”.** Đây là fallback từ một request sai sang profile yếu/cũ mà client chưa chắc được phép dùng. Profile và key selection phải được server cho phép; một MAC sai phải kết thúc xác thực.

**“Header nói alg gì thì cứ Mac.getInstance(alg)”.** Đây là algorithm confusion: client chưa xác thực không được quyết định thuật toán JCA tùy ý. Dùng enum allowlist và map key → profile cố định.

**“Dùng lại secret cũ vì cùng client”.** Không tách được revoke/key lifecycle và tăng coupling giữa các profile. Ưu tiên secret V2 mới; nếu derivation, dùng KDF có domain separation được thiết kế riêng.

**“Version chỉ nằm ngoài canonical, không cần ký”.** Nếu thay version làm server chọn cách diễn giải khác, rủi ro confusion tăng. Dùng domain prefix/profile ID trong canonical và kiểm tra key-profile policy.

**“Mỗi version có nonce store riêng nên không cần test liên phiên bản”.** Request cùng principal có thể qua cả hai profile khi overlap; một nghiệp vụ phải không được nhân đôi vì namespace replay thay đổi.

**“Chấp nhận MAC đúng là đủ”.** HMAC thành công chưa chứng minh client được quyền gọi route/tenant/resource. Authorization vẫn tách riêng; một signature V2 hợp lệ có thể nhận 403.

**“Proxy sẽ giữ nguyên path/query/body”.** Thực tế gateway có thể rewrite hoặc normalize; cần contract tests qua proxy thật cho cả V1 lẫn V2, nhất là khi canonicalization thay đổi.

**“Policy cache stale thì cho dùng V1 thêm một chút”.** Nếu `v2-required` hoặc revoke cần có hiệu lực trong giới hạn nhất định, stale policy có thể thành downgrade. Cache/invalidation phải có policy và test nhiều replica.

**“Bỏ V1 theo doanh số/traffic tổng hợp”.** Một client batch hiếm khi chạy có thể chưa migrate. Cần danh sách client/key có quyền và kiểm tra theo chu kỳ sử dụng, không chỉ traffic aggregate.

## 16. Checklist thực hành

- [ ] Có tài liệu profile bất biến: wire version, JCA algorithm, canonical prefix, bytes ký, Base64, MAC length và parser limits.
- [ ] Server dùng allowlist profile cố định và key record gắn đúng profile, không nhận tên JCA tự do từ client.
- [ ] Version/algorithm suite được ràng buộc bởi canonical/domain separation; đổi version giữ MAC cũ phải thất bại.
- [ ] Secret V1/V2 độc lập hoặc được derive bằng thiết kế KDF/secret management được phê duyệt.
- [ ] Migration policy do server quản lý trên từng client/key: legacy → dual-capable → v2-required → retired.
- [ ] Sau v2-required không fallback V1, kể cả khi V2 MAC sai hoặc key store chậm.
- [ ] Có golden vectors Java/client SDK độc lập và server-side integration tests cho V1/V2.
- [ ] Có negative tests: wrong version, wrong key ID, malformed headers, truncated MAC, changed signed fields và unknown algorithm.
- [ ] Tất cả path/query/header/body trong canonical khớp contract xuyên gateway/proxy và security matcher.
- [ ] Timestamp dùng clock server; nonce claim nguyên tử sau MAC, scope chống replay được đánh giá xuyên phiên bản.
- [ ] Key revoke/key rotation/invalidation có test qua nhiều replica, kể cả rollout dở và store unavailable.
- [ ] 401 cho credential/profile không hợp lệ; 403 sau xác thực nhưng thiếu quyền; 503 khi không thể xác minh; không side effect.
- [ ] Log/metric có reason/profile enum, không log secret/full MAC/raw PII hoặc tạo high-cardinality labels.
- [ ] Có cảnh báo V1 usage sau cutover, V2 failure, replay anomalies, authn latency và policy propagation.
- [ ] Rollback có owner/thời hạn/ngoại lệ được phê duyệt, không tự hồi sinh key V1 đã revoke.
- [ ] Retire V1 bằng cả policy, key lifecycle và test negative ở mọi gateway/region/service.

## 17. Kết luận

**Migration signature** thành công không phải chỉ có hai dòng `Mac.getInstance(...)`. Nó đòi hỏi một **hợp đồng ký có version**, key và policy được gắn rõ với thuật toán, chiến lược rollout có thời hạn, test vectors độc lập, chống downgrade và cùng các bảo đảm **canonical request → HMAC verification → timestamp/nonce → Authentication → Authorization**.

Một migration an toàn cho phép client cũ tiếp tục hoạt động **chỉ trong khoảng overlap được chấp thuận**, đưa client mới sang V2 có secret riêng và cuối cùng **từ chối V1 một cách dứt khoát**. Các kết quả cần đo không chỉ là tỷ lệ V2 được dùng mà còn là mọi invariant: không downgrade, không cross-version replay, không bỏ qua revoke, không lộ credential và **không có request chưa được xác thực/phân quyền nào tạo ra side effect**.
