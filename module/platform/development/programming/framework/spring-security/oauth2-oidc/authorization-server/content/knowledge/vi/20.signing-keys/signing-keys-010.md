# Thu hồi khóa bị lộ, khôi phục khẩn cấp và kiểm toán truy cập khóa

## 1. Bối cảnh và mục tiêu

Trong **OAuth 2.0/OpenID Connect (OIDC) Authorization Server** xây dựng bằng **Spring Security**, **Spring Authorization Server** và **Spring Boot**, signing key là một trong những tài sản bảo mật quan trọng nhất. Khi private key dùng để ký JWT bị lộ hoặc bị một tác nhân không được phép sử dụng, kẻ tấn công có thể tạo token giả mang issuer, subject, audience, scope và thời hạn tùy ý trong phạm vi Resource Server tin cậy public key tương ứng.

Sự cố này khác với việc một public JWK xuất hiện trên JWKS endpoint. **Công bố public key là hành vi bình thường**: Resource Server cần nó để xác minh chữ ký. Rủi ro xuất hiện khi private key bị lộ, quyền gọi thao tác ký bị chiếm đoạt, hoặc một hệ thống trái phép có thể yêu cầu HSM/KMS ký dữ liệu tùy ý.

Ví dụ xuyên suốt: Authorization Server <code>https://auth.example.com</code> ký access token bằng RSA key có <code>kid=as-signing-k1</code>. Orders API và Billing API lấy public key K1 từ JWKS và xác minh JWT offline. Một cảnh báo cho thấy tài khoản vận hành bất thường đã gọi thao tác ký bằng K1, hoặc private JWK bị tìm thấy trong một artifact công khai. Đội vận hành phải cô lập key, chuyển sang key K2, cập nhật Resource Server, đánh giá token đã phát hành và lưu lại bằng chứng phục vụ điều tra.

Sau bài học, bạn có thể:

1. Phân biệt lộ public key với compromise private key hoặc quyền ký.
2. Nhận diện các dấu hiệu key compromise từ KMS/HSM, ứng dụng, JWKS và token issuance.
3. Thực hiện quy trình ứng phó: containment, tạo key mới, chuyển signer, chặn key cũ và khôi phục dịch vụ.
4. Hiểu vì sao xóa JWK khỏi JWKS không lập tức vô hiệu hóa JWT đã được Resource Server cache public key.
5. Thiết kế cách thu hồi token ký bằng key bị lộ, gồm key denylist, introspection, denylist theo token ID và TTL.
6. Bảo đảm khôi phục database/backup không vô tình kích hoạt lại key đã bị thu hồi.
7. Kiểm toán truy cập private key, quyền ký, quyền quản trị key và thao tác rotation.
8. Tích hợp quy trình với Spring Authorization Server, Spring Resource Server, KMS/HSM và hệ thống giám sát.
9. Kiểm thử emergency rotation, cache invalidation, key revocation và audit trail.

**Phạm vi phiên bản:** Các ví dụ sử dụng API thường gặp trong Spring Security 6.x và Spring Authorization Server 1.x trên Servlet stack. Những bản Spring Security mới tích hợp Authorization Server có thể thay đổi package hoặc cách cấu hình. Các interface như <code>CompromisedKeyRegistry</code> trong bài là abstraction do ứng dụng tự triển khai, không phải API có sẵn của Spring.

## 2. Phân loại sự cố khóa

Trước khi thu hồi, cần xác định chính xác điều gì bị lộ hoặc bị lạm dụng. Một cảnh báo “key exposed” có thể chỉ là public JWK được truy cập bình thường, cũng có thể là private key đã bị đánh cắp.

| Tình huống | Ý nghĩa | Mức độ xử lý |
| --- | --- | --- |
| Public JWK xuất hiện trên JWKS endpoint | Hành vi dự kiến; public key được công bố để xác minh chữ ký. | Không phải sự cố chỉ vì public key được truy cập. |
| Private JWK/PEM/keystore bị commit vào Git hoặc artifact | Kẻ có bản sao có thể ký token ngoài Authorization Server. | Coi là compromise; thu hồi private key và đánh giá token. |
| KMS/HSM báo thao tác ký từ principal hoặc workload lạ | Quyền ký có thể bị chiếm dù private material không export được. | Coi là sự cố nghiêm trọng; khóa quyền ký, điều tra danh tính và phạm vi request. |
| Tài khoản quản trị có thể export hoặc thay đổi key policy trái phép | Ranh giới quản trị key bị phá vỡ. | Thu hồi quyền, kiểm tra key material và audit control plane. |
| Một node dùng key khác với JWKS đang công bố | Có thể là lỗi triển khai, split-brain hoặc dấu hiệu key injection. | Ngăn node phát hành token, kiểm tra deployment và key inventory. |
| KMS/HSM bị gián đoạn nhưng chưa có dấu hiệu lộ key | Vấn đề availability; chưa đủ bằng chứng kết luận compromise. | Kích hoạt quy trình dự phòng; không tự hạ cấp sang key yếu. |
| Public JWKS cache bị cũ | Resource Server chưa nhận key mới hoặc chưa nhận trạng thái thu hồi. | Xử lý cache/distribution; không nhất thiết private key bị lộ. |

### 2.1. Private key compromise và signing oracle

Có hai dạng tấn công cần phân biệt:

- **Key material compromise:** attacker lấy được private key và có thể ký token ở ngoài Authorization Server.
- **Signing capability compromise:** attacker chưa lấy được private key nhưng chiếm tài khoản/ứng dụng có quyền gọi KMS/HSM ký. Kẻ tấn công vẫn có thể yêu cầu ký JWT tùy ý nếu API ký không giới hạn payload hoặc caller không bị ràng buộc.

Vì vậy, giữ private key không export được trong HSM là một biện pháp rất tốt nhưng **không đủ** nếu mọi workload có thể gọi <code>Sign</code> với dữ liệu tùy ý. Phải kiểm soát cả quyền sử dụng key, danh tính workload, chính sách ký và audit thao tác.

### 2.2. Khóa nào bị ảnh hưởng?

Không gộp tất cả credential vào một khái niệm “signing key”. Một hệ thống có thể có:

- Khóa ký JWT access token.
- Khóa ký OIDC ID Token.
- Khóa ký request object hoặc client assertion.
- Khóa mã hóa JWE.
- Khóa TLS cho HTTPS.
- Khóa xác thực client (ví dụ private key của một OAuth client).
- Khóa dữ liệu/KMS master key bảo vệ database hoặc backup.

Sự cố một loại key không tự động có nghĩa mọi loại key khác đều bị lộ. Tuy nhiên, nếu cùng một KMS role, secret store hoặc máy chủ bị compromise, phải đánh giá phạm vi liên quan thay vì chỉ xoay đúng một JWK.

## 3. JWT bị ký bằng private key lộ có thể gây hậu quả gì?

Giả sử Resource Server tin issuer <code>https://auth.example.com</code> và public key K1. Nếu attacker có private K1, họ có thể tạo một JWT mới:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "administrator",
  "aud": ["https://orders-api.example.com"],
  "iat": 1794800000,
  "exp": 1794803600,
  "scope": "orders.read orders.write orders.admin",
  "client_id": "orders-web"
}
~~~

Đây là payload minh họa, không phải token thật. Chữ ký giả có thể hợp lệ về mặt mật mã vì attacker dùng đúng private key. Nếu Resource Server chỉ kiểm tra chữ ký và claims cơ bản mà không có thêm trạng thái thu hồi, nó có thể chấp nhận token giả.

Hậu quả có thể gồm:

1. Giả danh user hoặc service principal.
2. Tự đặt scope rộng hơn quyền từng được consent.
3. Đặt audience vào API khác nếu API đó cùng tin issuer/key.
4. Tạo token có thời hạn dài hơn policy thực tế.
5. Giả mạo ID Token trong các OIDC client nếu cùng key được dùng ký ID Token.
6. Tạo token giả sau khi Authorization Server đã chuyển sang key mới nếu Resource Server vẫn tin public key cũ.

**Chữ ký hợp lệ không chứng minh token được Authorization Server phát hành thật.** Chữ ký chỉ chứng minh dữ liệu được ký bởi người nắm private key tương ứng. Khi private key đã bị compromise, cần thu hồi niềm tin vào key đó.

### 3.1. Phạm vi tác động không chỉ là token đã phát hành

Với key compromise, attacker có thể ký **token mới** trong suốt thời gian Resource Server còn chấp nhận key cũ. Do đó, chỉ tìm và revoke các token hợp lệ từng được Authorization Server lưu trong database chưa đủ: token giả do attacker tạo có thể không có record trong <code>OAuth2AuthorizationService</code>.

Đây là lý do cần cơ chế **từ chối toàn bộ token mang kid bị compromise** ở Resource Server, ngoài việc thu hồi các authorization/token hợp lệ đã phát hành nếu cần.

## 4. Hai quy trình khác nhau: rotation bình thường và emergency revocation

Rotation định kỳ và ứng phó key compromise có mục tiêu khác nhau:

| Tiêu chí | Rotation bình thường | Emergency revocation |
| --- | --- | --- |
| Tình trạng key cũ | Vẫn được tin cậy, chỉ ngừng ký token mới. | Không còn được tin cậy. |
| Public key cũ trong JWKS | Thường giữ đến khi token cũ hết hạn. | Gỡ khỏi JWKS và đồng thời triển khai chặn kid ở Resource Server. |
| Token cũ | Tiếp tục xác minh trong cửa sổ hiệu lực. | Bị từ chối theo chính sách incident, dù chưa hết hạn. |
| Mục tiêu | Chuyển đổi không gián đoạn. | Ngăn attacker tiếp tục tạo token được chấp nhận. |
| Tác động người dùng | Thường không cần đăng nhập lại. | Có thể buộc cấp token mới hoặc đăng nhập lại. |

Không áp dụng nguyên xi quy trình rotation thông thường cho key đã compromise. Nếu giữ public key cũ chỉ để các JWT còn hạn tiếp tục hoạt động, attacker vẫn có thể dùng private key lộ để ký token mới và được chấp nhận.

## 5. Quy trình ứng phó khẩn cấp

### 5.1. Các pha xử lý

~~~mermaid
flowchart TD
    A["Phát hiện nghi ngờ key compromise"] --> B["Kích hoạt incident và xác định kid/key version"]
    B --> C["Containment: chặn quyền ký và cô lập workload/tài khoản"]
    C --> D["Tạo key K2 mới trong KMS/HSM"]
    D --> E["Công bố public K2 và chuyển Authorization Server sang ký K2"]
    E --> F["Phân phối policy từ chối kid K1 đến mọi Resource Server"]
    F --> G["Gỡ public K1 khỏi JWKS và làm mới cache"]
    G --> H["Đánh giá token/authorization/session bị ảnh hưởng"]
    H --> I["Khôi phục dịch vụ, kiểm tra end-to-end và giám sát tăng cường"]
    I --> J["Bảo toàn bằng chứng, hậu kiểm và đóng incident"]
~~~

Trong sự cố nghiêm trọng, một số hành động có thể diễn ra song song theo runbook và khả năng hạ tầng. Thứ tự an toàn cần bảo đảm hai điều: **Authorization Server ngừng ký bằng K1** và **Resource Server ngừng tin token ký bằng K1**. Chỉ thay signer mà không cập nhật verifier vẫn để cửa cho token giả.

### 5.2. Pha 1 — Kích hoạt incident và xác định phạm vi

Ngay khi có dấu hiệu đáng tin:

1. Mở incident bảo mật và chỉ định người điều phối có quyền ra quyết định.
2. Xác định <code>kid</code>, key version, thuật toán, KMS/HSM resource và issuer bị ảnh hưởng.
3. Ghi nhận thời điểm nghi ngờ bắt đầu, thời điểm phát hiện, thời điểm cuối cùng key được sử dụng bình thường.
4. Xác định workload, service account, node, pipeline, người quản trị và hệ thống backup có thể truy cập key.
5. Bảo toàn audit log, IAM change log, signing request metadata, deployment artifact và bằng chứng liên quan.
6. Phân loại suspected hay confirmed compromise; với nguy cơ ký token trái phép, xử lý theo hướng **không tiếp tục tin key** trong lúc xác minh.

Không xóa log, xóa key hoặc rebuild toàn bộ máy chủ trước khi bảo toàn bằng chứng cần thiết. Tuy nhiên, việc bảo toàn bằng chứng không được trì hoãn hành động containment khi attacker còn có khả năng ký token.

### 5.3. Pha 2 — Containment: chặn khả năng ký

Tùy nơi lưu key:

- **KMS:** vô hiệu hóa key version hoặc thu hồi quyền <code>Sign</code> của principal/workload bị compromise; kiểm tra key policy, IAM binding, grants và credential liên quan.
- **HSM:** vô hiệu hóa quyền sử dụng key hoặc session/role bị chiếm; áp dụng quy trình operator/dual control của HSM.
- **Keystore/file:** cô lập node, gỡ quyền đọc file, thu hồi secret/password và credential của workload; không coi xóa file trên một node là đủ nếu đã có bản sao.
- **Signing service:** dừng endpoint ký bị lạm dụng, chặn caller bất thường và chuyển traffic tới service đã được xác minh.

Không chỉ disable key nếu attacker vẫn có quyền tạo key mới hoặc thay đổi key policy. Thu hồi credential/IAM role bị chiếm, khóa session và kiểm tra quyền quản trị control plane.

### 5.4. Pha 3 — Tạo signing key mới

Tạo K2 trong KMS/HSM hoặc quy trình quản lý khóa được bảo vệ:

- Dùng thuật toán và kích thước/curve được chính sách cho phép.
- Tạo <code>kid</code> mới, duy nhất, không tái sử dụng ID K1.
- Xác minh public key đúng với key version thực sự được dùng để ký.
- Kiểm tra signer chỉ có thể dùng key K2 theo quyền tối thiểu.
- Lưu metadata, thời điểm tạo, owner, key version, thuật toán và approval record.
- Thực hiện test ký/xác minh trong môi trường kiểm soát trước khi chuyển production.

Không copy private K1 sang K2 hoặc “đổi kid” của cùng key material. Đổi <code>kid</code> không làm private key cũ an toàn trở lại. K2 phải là **key material mới**.

### 5.5. Pha 4 — Chuyển Authorization Server sang K2

Authorization Server cần chọn private K2 để ký token mới. Với Spring Authorization Server, signer thường được kết nối qua <code>JWKSource&lt;SecurityContext&gt;</code>, <code>JwtEncoder</code> và <code>JwtGenerator</code>. Khi dùng KMS/HSM, adapter ký phải trỏ đúng key version mới; public JWK công bố phải khớp với thao tác ký đó.

Sau khi chuyển:

- Kiểm tra JWT mới có <code>kid=K2</code>.
- Xác minh chữ ký token mới bằng public K2.
- Kiểm tra issuer, audience, scope và thời hạn.
- Kiểm tra tất cả instance Authorization Server dùng cùng trạng thái signer/JWKSource.
- Theo dõi log để bảo đảm không còn node phát hành token với K1.

Đừng chỉ sửa một file cấu hình ở một node. Trong cụm nhiều instance, cần rollout/feature flag/config version có kiểm soát, tránh split-brain giữa node ký K1 và node ký K2.

### 5.6. Pha 5 — Thu hồi niềm tin K1 ở Resource Server

Đây là bước thường bị bỏ sót. Resource Server có thể đang cache public K1 từ JWKS. Dù Authorization Server đã xóa K1 khỏi JWKS, Resource Server vẫn có thể xác minh token mới giả bằng K1 từ cache cũ.

Cần thực hiện đồng thời:

1. Đưa <code>kid=K1</code> vào **danh sách key bị thu hồi** được Resource Server kiểm tra trước khi chấp nhận JWT.
2. Phân phối policy tới mọi instance/API, gateway, batch worker và service có xác minh JWT.
3. Buộc refresh/invalidate JWKS cache theo cơ chế decoder/proxy thực tế.
4. Gỡ public K1 khỏi JWKS endpoint để các verifier tải mới không còn nhận key này.
5. Xác minh bằng một JWT test ký bằng K1: mọi Resource Server phải từ chối; token ký bằng K2 hợp lệ phải được chấp nhận.
6. Kiểm tra các verifier không lấy key từ JWKS cache riêng, file local, static config hoặc một nguồn thứ hai chưa được cập nhật.

**Chỉ gỡ K1 khỏi JWKS là chưa đủ để thu hồi ngay.** Việc gỡ chỉ ảnh hưởng khi verifier làm mới JWKS; nó không xóa public key đã được cache trong process hoặc gateway.

### 5.7. Pha 6 — Đánh giá và xử lý token/authorization bị ảnh hưởng

Phân loại:

- JWT access token ký bằng K1.
- OIDC ID Token ký bằng K1.
- JWT khác (request object, client assertion hoặc token nội bộ) nếu dùng chung K1.
- Refresh token và opaque access token nếu có quan hệ với authorization bị ảnh hưởng.
- Các authorization/consent/session liên quan đến client, principal hoặc khoảng thời gian compromise.

Nếu toàn bộ token mang K1 đều bị từ chối qua key denylist, token hợp lệ trước đó ký bằng K1 cũng bị từ chối. Đây là tác động chủ ý của emergency revocation. Người dùng/client có thể cần lấy token mới được ký bằng K2 hoặc thực hiện lại authorization.

Không giả định refresh token cũng bị ký bằng K1: refresh token trong Spring Authorization Server thường là opaque credential được lưu trong authorization store. Tuy nhiên, nếu attacker đã chiếm cả database, client secret, refresh token store hoặc user session thì phạm vi sự cố rộng hơn và cần revoke theo các credential đó.

### 5.8. Pha 7 — Khôi phục, giám sát và đóng incident

Chỉ khôi phục traffic đầy đủ khi:

- Không còn instance phát hành bằng K1.
- Tất cả Resource Server/gateway áp dụng deny K1.
- JWKS/discovery trả metadata đúng và không công bố private material.
- K2 ký/xác minh end-to-end thành công.
- Client có quy trình lấy token mới; API không chấp nhận token giả ký K1.
- IAM/KMS/HSM credential bị compromise đã được thu hồi hoặc thay thế.
- Audit log và bằng chứng đã được bảo toàn.
- Có người chịu trách nhiệm theo dõi hậu kiểm và cảnh báo tăng cường.

## 6. Thu hồi JWT đã ký bằng key bị lộ

### 6.1. Vì sao xóa JWK không đủ?

JWT self-contained có thể được xác minh offline. Resource Server thường:

1. Tải public key từ JWKS.
2. Cache public key theo <code>kid</code>/JWK Set URI.
3. Xác minh chữ ký và claims mà không hỏi Authorization Server ở mỗi request.

Khi public K1 bị gỡ khỏi JWKS, Resource Server có thể vẫn giữ K1 trong cache cho tới khi cache hết hạn hoặc bị làm mới. Vì vậy, token ký bằng K1 vẫn có thể được chấp nhận trong cửa sổ đó.

Ngay cả khi cache đã refresh, một verifier được cấu hình static public key hoặc pin key riêng vẫn có thể tiếp tục tin K1. Cần inventory toàn bộ nơi xác minh token.

### 6.2. Cơ chế thu hồi theo kid

Một cách phản ứng nhanh là duy trì danh sách <code>(issuer, kid)</code> bị compromise. Resource Server từ chối mọi JWT có cặp này, kể cả khi chữ ký toán học hợp lệ.

Ví dụ abstraction:

~~~java
public interface CompromisedKeyRegistry {
    boolean isRevoked(String issuer, String keyId);
}
~~~

Implementation cần đọc trạng thái từ nguồn được phân phối đáng tin cậy, có cache/invalidation rõ ràng và fail-safe khi không thể xác minh trạng thái thu hồi theo mức rủi ro của API. Không dùng một map local chỉ cập nhật ở một instance.

Một validator minh họa cho Spring Resource Server:

~~~java
OAuth2TokenValidator<Jwt> compromisedSigningKeyValidator(
        CompromisedKeyRegistry registry) {

    return jwt -> {
        String issuer = jwt.getIssuer() == null
            ? null : jwt.getIssuer().toString();
        String kid = jwt.getHeaders().get("kid");

        if (issuer != null && kid != null
                && registry.isRevoked(issuer, kid)) {
            OAuth2Error error = new OAuth2Error(
                OAuth2ErrorCodes.INVALID_TOKEN,
                "JWT signing key has been revoked",
                null);
            return OAuth2TokenValidatorResult.failure(error);
        }

        return OAuth2TokenValidatorResult.success();
    };
}
~~~

Đây là ví dụ validator; cần kết hợp với các validator mặc định về issuer, timestamp và audience của API. Đăng ký nó vào <code>JwtDecoder</code> sau khi cấu hình decoder từ issuer/JWKS. Không thay thế validator mặc định bằng một validator chỉ kiểm tra <code>kid</code>.

Ví dụ cấu hình ghép validator:

~~~java
NimbusJwtDecoder decoder =
    NimbusJwtDecoder.withIssuerLocation(issuer).build();

OAuth2TokenValidator<Jwt> defaults =
    JwtValidators.createDefaultWithIssuer(issuer);

OAuth2TokenValidator<Jwt> keyRevocation =
    compromisedSigningKeyValidator(compromisedKeyRegistry);

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(defaults, keyRevocation));
~~~

API builder có thể khác giữa các phiên bản Spring Security; đối chiếu version đang dùng. Nếu ứng dụng cần audience validator riêng, ghép thêm vào danh sách validator. Trong incident, đảm bảo policy denylist được tải trước khi mở traffic và được cập nhật trên **tất cả** verifier.

### 6.3. Denylist theo kid và denylist theo jti khác nhau

| Cơ chế | Phạm vi | Khi nào hữu ích |
| --- | --- | --- |
| **Kid denylist** | Từ chối mọi token được ký bằng key bị compromise. | Private signing key bị lộ hoặc quyền ký bị chiếm. |
| **JTI/token denylist** | Từ chối từng token cụ thể theo <code>jti</code>. | Một số token bị lộ hoặc cần revoke chọn lọc. |
| **Authorization/session revocation** | Thu hồi grant/authorization của principal hoặc client. | User bị khóa, consent bị revoke hoặc client bị compromise. |
| **Opaque token introspection** | Resource Server hỏi trạng thái token tại Authorization Server. | Cần trạng thái tập trung, revoke nhanh và chấp nhận network dependency. |
| **Short access token TTL** | Giới hạn thời gian token còn hữu dụng. | Giảm cửa sổ rủi ro, nhưng không phải thu hồi tức thì. |

Với signing key bị lộ, denylist theo <code>jti</code> một mình không đủ: attacker có thể tự tạo token giả với <code>jti</code> mới. **Chặn kid** là biện pháp trực tiếp hơn vì tất cả token do key đó ký đều bị từ chối.

### 6.4. JWT offline và giới hạn thu hồi tức thời

Không có cách thu hồi tức thì một JWT đã được xác minh offline nếu Resource Server chỉ dựa trên chữ ký, claims và public key cache mà không hỏi trạng thái tập trung. Để đạt mục tiêu phản ứng nhanh, cần ít nhất một trong các thiết kế:

- Key revocation registry được phân phối tới tất cả verifier và kiểm tra trên mỗi request.
- Opaque access token + introspection với trạng thái active/inactive.
- JWT có <code>jti</code> kết hợp denylist tập trung/được cache và cập nhật khẩn cấp.
- Kiểm tra authorization/session version hoặc account status ở một dịch vụ chính sách có độ trễ được kiểm soát.
- Access token TTL ngắn để giới hạn thời gian rủi ro còn lại.

Mỗi cách có trade-off về độ trễ, availability, tải, khả năng cache và mức độ phụ thuộc mạng. Không tuyên bố “JWT đã bị revoke ngay” nếu hệ thống vẫn cho phép verifier dùng key/status cache cũ.

## 7. Tích hợp quy trình với Spring Authorization Server

### 7.1. JWKSource và active signing key

Spring Authorization Server thường sử dụng bean <code>JWKSource&lt;SecurityContext&gt;</code> làm nguồn khóa cho JWT encoder và JWK Set endpoint. Một ứng dụng demo có thể dùng <code>ImmutableJWKSet</code>, nhưng production nên đọc trạng thái từ key manager/KMS adapter có kiểm soát.

Trong lúc rotation bình thường, JWKSource có thể cung cấp:

- Private K2 đang active cho ký.
- Public K1 chỉ dùng xác minh token cũ.
- Public K2 để Resource Server tải và chuẩn bị xác minh.

Trong emergency revocation, K1 không còn được tin cậy. Cần gỡ K1 khỏi JWKSource/JWKS public view và đảm bảo signer không còn chọn K1. Nếu một key manager vẫn giữ K1 cho audit/forensics, trạng thái đó không đồng nghĩa key được phép dùng để ký hoặc verify production.

### 7.2. Không dùng JWKS endpoint làm nơi quản trị key

JWKS endpoint là giao diện **công bố public key**. Không cung cấp chức năng tạo, kích hoạt, vô hiệu hóa hoặc xóa key qua một endpoint công khai không có authorization quản trị. Quản trị key nên đi qua control plane tách biệt, có xác thực mạnh, phân quyền, dual control và audit.

### 7.3. Kiểm tra JWT mới có kid đúng

Sau khi thay active key, hãy cấp token test qua grant thực tế và kiểm tra:

- Header <code>kid</code> là K2.
- <code>alg</code> nằm trong allow-list.
- JWT verify được bằng public K2 lấy từ JWKS.
- JWT không verify được bằng một public key khác không liên quan.
- Claims <code>iss</code>, <code>aud</code>, <code>exp</code>, <code>scope</code> vẫn đúng.
- Authorization Server không ghi private JWK hoặc raw token vào log.

Không chỉ kiểm tra file cấu hình chứa K2; phải xác minh token phát ra từ từng node sau deployment.

### 7.4. Các token type có thể dùng chung signing key

Một key có thể được dùng ký access token JWT, ID Token và các JWT khác tùy cấu hình. Khi compromise, kiểm kê theo <code>kid</code> trên toàn hệ sinh thái:

- Access token cho tất cả Resource Server.
- ID Token đã phát hành cho OIDC clients.
- JWT assertion hoặc request object nếu cùng key.
- JWT nội bộ giữa các service.

Không mặc định chỉ cần cập nhật Orders API. Một client OIDC có thể tiếp tục tin ID Token giả nếu verifier của nó vẫn chấp nhận public K1.

## 8. Khôi phục khẩn cấp và bảo vệ backup

### 8.1. Khôi phục không được tái kích hoạt key đã thu hồi

Một lỗi nguy hiểm xảy ra khi khôi phục database hoặc secret backup cũ: snapshot có thể chứa JWK K1 và trạng thái active trước incident. Nếu restore nguyên trạng, Authorization Server có thể lại ký bằng key đã compromise hoặc JWKS endpoint công bố public K1.

Do đó, trạng thái key revocation phải có nguồn lưu trữ và quy trình restore bảo đảm **không bị rollback**:

- Lưu key status/revocation event trong hệ thống audit/registry có version và retention độc lập với snapshot database chính.
- Duy trì danh sách kid bị cấm ngoài backup có thể khôi phục về thời điểm trước incident.
- Khi restore, đối chiếu key inventory với incident ledger trước khi bật signer/JWKS endpoint.
- Không tự động kích hoạt key chỉ vì một bản ghi database ghi <code>ACTIVE</code>.
- Thực hiện kiểm tra hậu restore: signer chỉ dùng K2, JWKS không chứa K1, Resource Server vẫn từ chối K1.

### 8.2. Backup private key

Backup key có thể cần cho disaster recovery, nhưng nó cũng là một bản sao có giá trị tương đương key gốc. Cần:

- Mã hóa backup bằng key bảo vệ độc lập.
- Hạn chế quyền tạo/đọc/restore và yêu cầu phê duyệt nhiều bên.
- Audit mọi lần export, backup, restore và kiểm tra backup.
- Lưu bản backup tách biệt về quyền quản trị và failure domain.
- Thực hiện restore drill trong môi trường cô lập.
- Sau compromise, đánh dấu mọi backup chứa K1 là **compromised material**, không dùng lại để ký.

Nếu key nằm trong HSM và non-exportable, quy trình backup/restore theo vendor có thể khác; vẫn phải kiểm toán thao tác clone/replicate, backup domain và quyền operator.

### 8.3. Khôi phục issuer và cấu hình

Issuer thường là định danh ổn định của Authorization Server; **không đổi issuer chỉ để xử lý key compromise** nếu không có lý do kiến trúc đặc biệt. Thay issuer có thể làm hỏng discovery, trust configuration, client registrations và Resource Server. Thông thường giữ issuer, thay key, thu hồi kid cũ và cập nhật verifier.

Kiểm tra cấu hình sau recovery:

1. Issuer giống giá trị công bố và giá trị <code>iss</code> của token mới.
2. JWK Set URI ổn định, HTTPS và thuộc issuer tin cậy.
3. Active signing key là K2 ở mọi node.
4. K1 vẫn bị đánh dấu revoked trong registry.
5. Backup/restore và autoscaling không làm mất trạng thái revocation.
6. KMS/HSM IAM đã được rà soát, không còn principal bị compromise.

## 9. Kiểm toán truy cập và sử dụng khóa

### 9.1. Những sự kiện cần ghi nhận

Audit cần bao phủ cả **data plane** (dùng key để ký) và **control plane** (quản trị key, IAM, policy, backup):

| Nhóm | Sự kiện nên audit | Câu hỏi điều tra |
| --- | --- | --- |
| Tạo khóa | Create/generate key, import, rotate, version creation | Ai tạo key, lúc nào, trong project/account nào? |
| Sử dụng khóa | Sign operation, decrypt nếu có, key version được gọi | Workload nào ký, tần suất và thời điểm ra sao? |
| Truy cập metadata | Get public key, describe key, list versions | Ai tra cứu key và từ đâu? |
| Quản trị | Enable/disable, schedule deletion, update key policy | Ai có thể làm key ngừng hoạt động hoặc thay quyền? |
| IAM | Grant/revoke role, access key/token creation, service account impersonation | Có principal mới được cấp quyền ký bất thường không? |
| Backup/restore | Export, backup, restore, clone/replicate | Có bản sao key nào được tạo hoặc di chuyển? |
| Ứng dụng | Sign latency, lỗi KMS, kid được dùng, node/instance | Node nào đã ký token bằng key nào? |
| JWKS | Thay đổi public key set, cache refresh, metadata publish | Key nào được công bố cho Resource Server? |

### 9.2. Trường dữ liệu audit hữu ích

Một audit event có thể chứa:

~~~json
{
  "event_type": "SIGN_OPERATION",
  "timestamp": "2026-11-16T09:30:00Z",
  "issuer": "https://auth.example.com",
  "key_id": "as-signing-k2",
  "key_version": "version-17",
  "principal": "service-account/authorization-server",
  "workload": "authorization-server-prod-03",
  "operation": "SIGN",
  "source": "kms",
  "request_id": "audit-correlation-123",
  "result": "SUCCESS"
}
~~~

Đây là schema minh họa. Không đưa raw private key, secret, access token, refresh token hoặc payload chứa dữ liệu người dùng nhạy cảm vào audit. Nếu cần liên kết signing operation với token issuance, dùng request/correlation ID và metadata tối thiểu; không nhất thiết ghi toàn bộ JWT.

### 9.3. Bảo vệ audit trail khỏi sửa/xóa

Audit chỉ có giá trị điều tra nếu kẻ tấn công không thể dễ dàng sửa log sau khi chiếm ứng dụng. Nên:

- Gửi log sang hệ thống tập trung với quyền ghi tách khỏi quyền xóa.
- Bật retention/immutability hoặc write-once policy phù hợp.
- Đồng bộ thời gian giữa KMS/HSM, Authorization Server, gateway và Resource Server.
- Giới hạn ai được truy vấn log nhạy cảm; audit cả thao tác đọc log.
- Cảnh báo khi audit pipeline ngừng nhận sự kiện hoặc có khoảng trống bất thường.
- Giữ bản sao sự kiện control plane và data plane ở failure domain khác.

### 9.4. Phân tách nhiệm vụ và least privilege

| Vai trò | Quyền tối thiểu |
| --- | --- |
| Runtime signer | Gọi thao tác ký bằng key active; không export private key, không thay key policy. |
| JWKS publisher | Đọc public metadata và công bố JWKS; không có quyền ký. |
| Key custodian | Quản lý vòng đời/rotation theo phê duyệt; không tự ý cấp quyền truy cập rộng. |
| Security auditor | Đọc audit log và key inventory; không ký hoặc thay policy. |
| Resource Server | Đọc public JWKS; không truy cập private key/KMS signing permission. |
| Incident commander | Điều phối containment/recovery theo quyền khẩn cấp được kiểm soát và có audit. |

Trong hệ thống nhỏ, một người có thể kiêm nhiệm nhiều vai trò, nhưng thao tác rủi ro cao như export, disable, rotate hoặc destroy key nên có phê duyệt độc lập/dual control khi mức độ quan trọng yêu cầu.

## 10. Phát hiện truy cập bất thường

Không chỉ audit sau sự cố; cần cảnh báo chủ động. Những tín hiệu có thể hữu ích:

- Signing operation tăng đột biến so với baseline.
- Một principal chưa từng ký trước đây bắt đầu gọi key.
- Key được gọi từ workload, subnet, region hoặc account không dự kiến.
- Lệnh ký xuất hiện ngoài giờ vận hành hoặc trong lúc deploy không liên quan.
- Thao tác thay đổi key policy/IAM ngay trước khi signing volume tăng.
- Key version cũ tiếp tục ký sau khi đã chuyển active signer.
- Một instance phát token với <code>kid</code> không nằm trong inventory hiện hành.
- JWKS response thay đổi ngoài deployment/rotation window.
- KMS/HSM audit log có khoảng trống hoặc log delivery bị tắt.
- Có thao tác export/backup/restore bất thường đối với key material.

Alert cần có severity, owner, runbook và tiêu chí escalation. Một lần <code>GetPublicKey</code> không nhất thiết là bất thường vì public metadata được đọc thường xuyên; ngược lại, quyền <code>Sign</code> từ principal mới cần được điều tra ngay.

## 11. Ví dụ kiểm soát kid bị thu hồi trong Spring Resource Server

### 11.1. Registry dùng chung

Định nghĩa contract:

~~~java
public interface CompromisedKeyRegistry {
    boolean isRevoked(String issuer, String kid);
}
~~~

Implementation production có thể dùng database/cache phân tán hoặc policy service có khả năng push invalidation. Nên có version/epoch của policy, thời điểm cập nhật và health signal. Nếu không truy cập được registry trong lúc incident, quyết định fail-open hay fail-closed phải dựa trên risk của API; với API nhạy cảm, thường cần **fail closed hoặc chuyển sang chế độ bảo trì** cho đến khi xác minh được trạng thái.

### 11.2. Validator bổ sung

~~~java
OAuth2TokenValidator<Jwt> rejectCompromisedKid(
        CompromisedKeyRegistry registry) {

    return jwt -> {
        String issuer = jwt.getIssuer() == null
            ? null : jwt.getIssuer().toString();
        String kid = jwt.getHeaders().get("kid");

        if (issuer == null || kid == null) {
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(OAuth2ErrorCodes.INVALID_TOKEN));
        }

        if (registry.isRevoked(issuer, kid)) {
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    OAuth2ErrorCodes.INVALID_TOKEN,
                    "Signing key is revoked",
                    null));
        }

        return OAuth2TokenValidatorResult.success();
    };
}
~~~

Đoạn này kiểm tra key ID sau khi decoder đã parse/xác minh JWT theo cấu hình. Cần ghép validator với validator mặc định về issuer và thời gian, cộng audience validator của API. Với token thiếu <code>kid</code>, quyết định từ chối là chính sách phù hợp cho profile JWT có yêu cầu key identification; nếu hệ thống có token hợp lệ không mang kid thì phải có quy tắc tương thích được định nghĩa rõ.

**Không dùng validator này làm nguồn xác minh chữ ký.** Nó chỉ là lớp kiểm tra trạng thái thu hồi bổ sung; decoder vẫn phải xác minh chữ ký bằng key từ issuer tin cậy.

### 11.3. Phân phối thay đổi revocation

Để denylist có hiệu lực trên toàn cụm:

1. Ghi event <code>issuer + kid + revokedAt + reason + incidentId</code> vào registry có thẩm quyền.
2. Phát event invalidation đến Resource Server/gateway.
3. Mỗi instance cập nhật cache cục bộ và ghi nhận policy version.
4. Theo dõi số instance đã xác nhận áp dụng policy.
5. Chỉ mở traffic đầy đủ khi coverage đạt ngưỡng và kiểm thử token K1 thất bại trên từng vùng.
6. Lặp lại kiểm tra khi autoscaling hoặc node restart để bảo đảm policy được nạp trước khi nhận request.

Nếu một Resource Server không thể nhận policy mới, cần cách ly node hoặc chuyển traffic đi nơi khác. Không coi “đã publish event” là “mọi instance đã áp dụng”.

## 12. Runbook ứng phó mẫu

Runbook sau là cấu trúc tham khảo. Tên công cụ KMS/HSM, vai trò, command và thời gian SLA phải được thay bằng cấu hình thực tế của tổ chức.

| Thời điểm/pha | Hành động | Bằng chứng hoàn thành |
| --- | --- | --- |
| Phát hiện | Tạo incident, xác định issuer, kid và key version nghi ngờ. | Incident ID, owner, timestamp, alert source. |
| Containment | Chặn principal/workload bị chiếm và ngừng K1 signing. | KMS/HSM audit cho thấy quyền ký bị vô hiệu hóa; không còn sign success bằng K1. |
| Recovery key | Tạo K2 mới, kiểm tra public key và signer. | Key inventory, approval, test signature. |
| Server rollout | Chuyển tất cả Authorization Server instance sang K2. | JWT mới từ từng node có kid K2. |
| Verifier block | Thêm K1 vào revoked-kid registry và invalidate cache. | Resource Server test từ chối token K1 ở mọi vùng. |
| JWKS | Gỡ K1 khỏi public JWKS, xác nhận không có private material. | HTTP response kiểm tra và metadata version. |
| Token impact | Xác định authorization/session/client/user liên quan; thu hồi bổ sung khi cần. | Danh sách tác động và quyết định revoke/re-auth. |
| Audit | Bảo toàn KMS/HSM/IAM/app logs và evidence. | Log immutable, correlation timeline, chain of custody. |
| Khôi phục | Kiểm tra token K2, issuer/audience/scope, client flows và API health. | Integration tests và xác nhận từng service owner. |
| Hậu kiểm | Root cause, timeline, control gap, corrective actions. | Báo cáo incident và owner/deadline từng hành động. |

### 12.1. Các quyết định phải ghi lại

- Vì sao kết luận suspected/confirmed compromise?
- K1 có thể bị lộ từ thời điểm nào?
- Có token giả nào được phát hiện hoặc sử dụng không?
- Những issuer, audience, client, Resource Server và OIDC client nào bị ảnh hưởng?
- Có phải revoke authorization, refresh token hoặc session không?
- Có service nào vẫn cache K1 hoặc dùng static key không?
- Ai phê duyệt K2 và việc gỡ K1?
- Backup nào chứa K1 và cách đánh dấu chúng không được dùng lại?
- Những biện pháp giảm thiểu tạm thời nào sẽ được gỡ, khi nào và ai phê duyệt?

## 13. Kiểm thử và diễn tập sự cố

### 13.1. Ma trận kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| JWT ký K1 trước incident, K1 chưa bị revoke | Xác minh theo policy bình thường. |
| JWT ký K2 sau rotation | Xác minh thành công bằng public K2. |
| JWT ký K1 sau khi registry đánh dấu revoked | Resource Server từ chối dù chữ ký đúng. |
| JWKS đã gỡ K1 nhưng Resource Server còn cache K1 | Kid denylist vẫn chặn token K1. |
| Resource Server khởi động lại trong incident | Nạp revoked-kid policy trước khi nhận traffic. |
| Node mới autoscale | Không chấp nhận K1; policy version đã cập nhật. |
| Một Authorization Server node vẫn ký K1 | Monitoring phát hiện; node bị cách ly hoặc rollout thất bại. |
| KMS principal cũ tiếp tục gọi Sign | KMS/HSM từ chối và phát cảnh báo. |
| Key policy bị sửa trái phép | Audit/control-plane alert được tạo. |
| Restore DB snapshot cũ chứa K1 active | Startup/recovery gate từ chối kích hoạt K1. |
| Public JWKS chứa private parameters | Security test thất bại. |
| JWT K1 có jti mới do attacker tạo | Kid denylist vẫn từ chối; jti denylist riêng lẻ không đủ. |
| Token K2 sai issuer/audience | Resource Server từ chối. |
| Revocation registry không khả dụng | Hành vi fail-safe theo policy; không tự động tin K1. |
| Opaque token bị revoke | Introspection trả inactive theo trạng thái server. |
| OIDC ID Token ký K1 | Client verifier áp dụng chính sách key compromise tương ứng. |
| Một service dùng static K1 | Inventory/test phát hiện và service bị cập nhật hoặc cách ly. |

### 13.2. Chaos/incident drill

Ít nhất định kỳ, diễn tập trong môi trường staging:

1. Tạo K1 và cấp một số JWT test.
2. Mô phỏng K1 bị compromise, không dùng private material production.
3. Kích hoạt runbook: chặn signer K1, tạo K2, chuyển server.
4. Cập nhật revoked-kid registry và JWKS.
5. Đo thời gian đến khi từng Resource Server từ chối K1.
6. Xác nhận token K2 hoạt động và các grant chuẩn không bị hỏng.
7. Restore một snapshot trước rotation và xác nhận K1 không được tái kích hoạt.
8. Kiểm tra audit event đầy đủ, không chứa token/private key.
9. Ghi lại thời gian phát hiện, containment, verifier coverage và khôi phục.

Không thử nghiệm bằng cách export/đưa private key production vào môi trường diễn tập. Dùng key giả lập và data test.

## 14. Các lỗi vận hành thường gặp

### Lỗi 1: Chỉ đổi private key nhưng không cập nhật Resource Server

**Hậu quả:** Resource Server vẫn tin public K1 đã cache; attacker tiếp tục ký token giả được chấp nhận.

**Cách xử lý:** Phân phối revoked-kid policy, invalidate cache và xác minh mọi verifier.

### Lỗi 2: Chỉ xóa K1 khỏi JWKS

**Hậu quả:** Verifier đang cache key hoặc pin static key vẫn xác minh token K1.

**Cách xử lý:** Kết hợp JWKS removal với key denylist hoặc cơ chế revoke tập trung.

### Lỗi 3: Giữ public K1 để tránh làm gián đoạn token cũ

**Hậu quả:** Attacker tiếp tục dùng private K1 ký token mới cho đến khi mọi verifier ngừng tin key.

**Cách xử lý:** Với emergency revocation, ưu tiên containment; token hợp lệ cũ cũng có thể bị từ chối và người dùng phải lấy token mới.

### Lỗi 4: Đổi kid nhưng giữ nguyên key material

**Hậu quả:** Private key đã lộ vẫn ký được token, chỉ có tên key thay đổi.

**Cách xử lý:** Tạo key pair/version mới trong KMS/HSM; không dùng lại private material compromise.

### Lỗi 5: Quên ID Token hoặc service khác dùng chung key

**Hậu quả:** API được bảo vệ nhưng OIDC client hoặc một service khác vẫn tin token giả.

**Cách xử lý:** Kiểm kê toàn bộ token profile và verifier theo issuer/kid, không chỉ access token của một API.

### Lỗi 6: Dựa vào jti denylist cho key compromise

**Hậu quả:** Attacker tự tạo token giả với jti chưa từng thấy.

**Cách xử lý:** Từ chối theo kid bị compromise; jti denylist chỉ bổ sung cho token cụ thể.

### Lỗi 7: Restore backup làm sống lại key cũ

**Hậu quả:** Authorization Server ký lại bằng K1 hoặc JWKS công bố K1.

**Cách xử lý:** Giữ revoked-key ledger độc lập với snapshot và áp dụng recovery gate trước khi bật signer.

### Lỗi 8: Audit chỉ ghi sự kiện quản trị, bỏ qua sign operation

**Hậu quả:** Không xác định được workload nào đã dùng key, lúc nào và với tần suất bao nhiêu.

**Cách xử lý:** Bật audit data plane cho thao tác ký và liên kết với request ID/issuer/kid/workload.

### Lỗi 9: Tắt key nhưng không thu hồi quyền IAM

**Hậu quả:** Attacker có thể tạo key mới hoặc sửa policy để tiếp tục ký.

**Cách xử lý:** Thu hồi principal/credential bị chiếm, rà soát quyền quản trị và audit control plane.

## 15. Checklist production

| Lĩnh vực | Điều kiện cần có |
| --- | --- |
| Inventory | Có danh mục key, kid, issuer, key version, owner, thuật toán và nơi sử dụng. |
| Key custody | Private key nằm trong KMS/HSM/keystore bảo vệ; runtime không export nếu không cần. |
| Least privilege | Runtime signer không có quyền quản trị/export key; JWKS publisher chỉ đọc public metadata. |
| Audit | Có log create/sign/disable/rotate/policy/IAM/backup/restore và log bất biến. |
| Detection | Có alert cho sign bất thường, principal lạ, policy change và key version cũ. |
| Emergency key | Có quy trình tạo K2, chuyển signer và xác minh kid. |
| Verifier revocation | Có registry chặn kid và phân phối đến mọi Resource Server/gateway. |
| JWKS cache | Có cách invalidate/refresh và đo độ phủ trên mọi instance. |
| JWT impact | Có chính sách cho access token, ID Token và token profile dùng chung key. |
| Opaque tokens | Có introspection/revocation khi cần trạng thái tập trung. |
| Backup/restore | Snapshot không thể tái kích hoạt key đã compromise. |
| Recovery drill | Có diễn tập, RTO/RPO và người phê duyệt rõ ràng. |
| Incident evidence | Có quy trình bảo toàn log, timeline và chain of custody. |
| User/client recovery | Có hướng dẫn lấy token mới, đăng nhập lại hoặc rotate credential liên quan. |

## 16. Bài tập thực hành

Một Authorization Server có ba instance, ký access token và ID Token bằng RSA key K1. JWKS được cache 30 phút ở một số Resource Server. KMS phát cảnh báo một service account không thuộc nhóm vận hành đã gọi thao tác ký bằng K1. Có JWT còn hạn được phát hành trước incident.

Hãy thực hiện:

1. Xác định dữ liệu cần thu thập để phân biệt lộ private key với lạm dụng quyền ký KMS.
2. Viết runbook containment: thu hồi principal/permission, chặn K1 signing và bảo toàn audit.
3. Tạo K2 mới, công bố public key, chuyển signer ở cả ba node và xác minh JWT mới có kid K2.
4. Thiết kế <code>CompromisedKeyRegistry</code> dùng chung để mọi Resource Server từ chối JWT có <code>kid=K1</code>.
5. Giải thích vì sao gỡ K1 khỏi JWKS chưa đủ khi cache vẫn còn 30 phút.
6. Xây test chứng minh JWT ký bằng K1 bị từ chối nhưng JWT ký bằng K2 có issuer/audience hợp lệ được chấp nhận.
7. Đánh giá các OIDC client có thể đang xác minh ID Token bằng K1 và xây kế hoạch cập nhật.
8. Thiết kế recovery gate ngăn restore snapshot cũ làm K1 active trở lại.
9. Xây audit event cho thao tác ký và quản trị key, không lưu raw key/token.
10. Diễn tập emergency rotation trong staging và đo thời gian đến khi tất cả verifier từ chối K1.

**Tiêu chí đạt:** Có thể chứng minh rằng **Authorization Server không còn ký bằng K1**, **mọi verifier không còn tin token mang kid K1**, **K2 hoạt động thống nhất**, và **audit đủ dữ liệu để xác định ai đã sử dụng hoặc thay đổi quyền của key**.

## 17. Tài liệu đối chiếu

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK, JWK Set và public/private key parameters.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): ký và xác minh JWS.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT claims và thời hạn token.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile access token JWT, issuer, audience và token type.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata issuer và JWK Set URI.
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): vòng đời, bảo vệ, rotation và hủy khóa.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): quản lý secret, quyền truy cập và audit.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): <code>JWKSource</code>, <code>JwtEncoder</code> và token generation.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): JWK Set endpoint và cấu hình Authorization Server.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, issuer validation và JWK Set URI.
- [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): quản lý vòng đời và bảo vệ mật mã.
