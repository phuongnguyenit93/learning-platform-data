# Secret rotation — Xoay vòng bí mật trong HMAC request authentication

## 1. Secret rotation là gì?

**Secret rotation** (xoay vòng bí mật) là quá trình thay một khóa bí mật đang được sử dụng bằng một khóa mới, có kế hoạch chuyển đổi để các bên liên quan tiếp tục xác thực request hợp lệ. Với **HMAC request authentication**, client và server cùng dùng một secret để tạo và kiểm tra chữ ký cho từng request. Khi secret cũ cần thay, cả hai phía phải chuyển sang secret mới theo một quy trình có kiểm soát.

Ví dụ: một dịch vụ đối tác gọi API thanh toán bằng HMAC-SHA-256. Mỗi request chứa key ID, timestamp và chữ ký HMAC được tạo từ method, path, body digest và một số header đã quy định. Secret của đối tác được luân chuyển định kỳ hoặc khi có dấu hiệu lộ. Server cần nhận diện đúng phiên bản secret, kiểm tra chữ ký, chống replay và từ chối secret cũ sau thời điểm kết thúc chuyển đổi.

Trong chương **HMAC request authentication** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, secret rotation liên quan trực tiếp tới quản lý credential, token, phiên, ranh giới tin cậy và xử lý sự cố. Người học cần biết thiết kế quy trình xoay vòng sao cho khóa mới được phân phối an toàn, client và server chuyển đổi đồng bộ, request được xác minh đúng phiên bản và secret bị lộ có thể bị thu hồi nhanh chóng.

**Rotation không chỉ là tạo một chuỗi secret mới.** Đó là thay đổi trạng thái tin cậy giữa client, server, kho bí mật, gateway, cache và các môi trường triển khai. Một quy trình thiếu đồng bộ có thể gây gián đoạn dịch vụ; một quy trình chấp nhận secret cũ vô thời hạn sẽ làm mất ý nghĩa của rotation.

## 2. HMAC request authentication hoạt động thế nào?

HMAC (*Keyed-Hash Message Authentication Code*) là cơ chế tạo mã xác thực thông điệp dựa trên hàm băm mật mã và một khóa bí mật dùng chung. Với HMAC-SHA-256, client và server dùng cùng secret để tính/kiểm tra MAC.

Một request khái niệm:

~~~http
POST /v1/payments HTTP/1.1
Host: api.example.org
X-Key-Id: partner-42-k3
X-Request-Timestamp: 2026-11-22T10:15:30Z
X-Request-Nonce: 8c2e...random...
X-Content-SHA256: <body-digest>
Authorization: HMAC-SHA256 <signature>
Content-Type: application/json

{"amount":125000,"currency":"VND"}
~~~

Client xây dựng chuỗi canonical theo một đặc tả thống nhất, sau đó tính HMAC:

~~~text
canonicalRequest =
    HTTP_METHOD + "\n" +
    CANONICAL_PATH_AND_QUERY + "\n" +
    CANONICAL_HEADERS + "\n" +
    BODY_DIGEST + "\n" +
    TIMESTAMP + "\n" +
    NONCE

signature = HMAC_SHA256(secret, canonicalRequest)
~~~

Server tra secret tương ứng với key ID, tự xây dựng lại canonical request từ dữ liệu nhận được và so sánh chữ ký bằng phép so sánh an toàn. Tên header, thứ tự, cách chuẩn hóa URL, encoding, dấu xuống dòng, cách xử lý query string và body digest phải được quy định rõ; hai bên không được tự diễn giải khác nhau.

### HMAC bảo vệ điều gì?

- **Integrity:** phát hiện nội dung request bị thay đổi sau khi ký, nếu mọi thành phần cần bảo vệ đều nằm trong canonical request.
- **Message authentication:** chứng minh request được tạo bởi bên biết secret, trong phạm vi hệ thống tin cậy secret đó.
- **Không cung cấp confidentiality:** HMAC không mã hóa body hoặc header. Vẫn cần HTTPS/TLS để bảo vệ dữ liệu trên đường truyền.
- **Không tự chống replay:** một chữ ký hợp lệ có thể bị gửi lại nếu server không kiểm tra timestamp, nonce hoặc cơ chế chống phát lại.
- **Không cung cấp non-repudiation:** cả client và server cùng biết secret nên cả hai đều có thể tạo HMAC hợp lệ. Nếu cần chữ ký có thể quy trách nhiệm một chiều, cần mô hình khóa bất đối xứng và quy trình phù hợp.

**HMAC là cơ chế khóa đối xứng.** Server cần có secret hoặc khả năng truy cập secret để xác minh. Vì thế, ai có quyền đọc secret phía server cũng có khả năng tạo request giả với danh nghĩa client đó. Secret phải được quản lý như credential có quyền truy cập API.

## 3. Vì sao phải xoay vòng secret?

Secret không nên tồn tại vô thời hạn. Rotation giúp giới hạn thời gian một khóa được sử dụng và tạo cơ hội thay khóa trước khi xảy ra sự cố nghiêm trọng.

Các lý do thường gặp:

1. **Rotation theo lịch:** chính sách tổ chức yêu cầu thay secret sau một chu kỳ xác định.
2. **Nghi ngờ bị lộ:** secret xuất hiện trong repository, log, ticket, file cấu hình hoặc thiết bị bị xâm nhập.
3. **Thay đổi nhân sự/đối tác:** người hoặc hệ thống có quyền truy cập secret không còn được phép.
4. **Thay đổi phạm vi quyền:** tách một secret dùng chung thành nhiều secret theo service, tenant hoặc môi trường.
5. **Thay đổi thuật toán/chính sách:** chuyển sang key length, thuật toán hoặc định dạng header mới theo lộ trình tương thích.
6. **Khắc phục sự cố:** thay khóa sau khi phát hiện request bất thường, lộ secret hoặc xâm nhập kho lưu trữ.

### Rotation định kỳ và rotation khẩn cấp

| Loại | Mục tiêu | Cách chuyển đổi |
| --- | --- | --- |
| **Định kỳ** | Giảm thời gian sử dụng của secret và duy trì kỷ luật vận hành. | Có kế hoạch, chuẩn bị key mới, giai đoạn overlap ngắn, kiểm tra client rồi thu hồi key cũ. |
| **Khẩn cấp** | Chặn secret đã lộ hoặc có nguy cơ bị lạm dụng. | Thu hồi nhanh, giới hạn hoặc dừng client bị ảnh hưởng, cấp secret mới qua kênh tin cậy và xác minh propagation. |

Không nên áp dụng cùng một overlap window cho hai tình huống. Rotation định kỳ có thể cần khoảng chuyển tiếp đủ để deploy nhiều client; khi secret đã bị lộ, việc tiếp tục chấp nhận key cũ có thể duy trì quyền truy cập của kẻ tấn công. Khi đó ưu tiên containment và thu hồi.

## 4. Mô hình dữ liệu: key ID và các phiên bản secret

Mỗi secret nên có một **key ID** công khai để server xác định bản ghi cần kiểm tra. Key ID không phải bí mật và không được dùng thay cho HMAC secret.

~~~text
HmacCredential
  credential_id:  partner-42
  owner_id:       partner-42-service
  tenant_id:      org-27
  environment:    production
  key_versions:
    - key_id:     partner-42-k2
      secret_ref: vault://hmac/partner-42/k2
      status:     retiring
      not_after:  <cutover deadline>
    - key_id:     partner-42-k3
      secret_ref: vault://hmac/partner-42/k3
      status:     active
      not_before: <activation time>
  allowed_algorithm: HMAC-SHA-256
  scopes:         [payments:create]
~~~

Đây là cấu trúc khái niệm; secret nên nằm trong secret manager/KMS hoặc kho được bảo vệ, không cần ghi bản rõ trong registry metadata. Bản ghi quản lý cần thể hiện:

- **Key ID:** định danh phiên bản, duy nhất trong phạm vi client/tenant thích hợp.
- **Secret reference:** vị trí hoặc handle truy cập secret được bảo vệ.
- **Status:** pending, active, retiring, revoked hoặc expired theo mô hình.
- **Validity window:** thời điểm bắt đầu và kết thúc chấp nhận nếu có.
- **Owner/tenant/environment:** chủ thể, tổ chức và môi trường được phép dùng.
- **Algorithm/policy:** thuật toán được cấu hình ở server, độ dài khóa và định dạng canonical request.
- **Audit metadata:** thời điểm tạo, kích hoạt, thu hồi, actor và lý do.

Secret HMAC nên được sinh ngẫu nhiên bằng CSPRNG, có độ dài phù hợp với thuật toán (ví dụ khóa ngẫu nhiên 256 bit cho HMAC-SHA-256 trong nhiều thiết kế). Không dùng mật khẩu con người làm HMAC key, không sinh secret từ timestamp hoặc tên dịch vụ, và không tái sử dụng một secret giữa staging/production hay giữa nhiều đối tác.

## 5. Quy trình rotation chuẩn với overlap có giới hạn

Rotation định kỳ thường cần một khoảng chuyển tiếp để client cập nhật mà không làm gián đoạn request. Một trình tự an toàn:

1. **Tạo secret mới:** server hoặc quy trình cấp phát sinh secret ngẫu nhiên mới và key ID mới.
2. **Phân phối an toàn:** gửi secret mới tới đúng owner/client qua secret manager, kênh bootstrap đã xác thực hoặc quy trình trao đổi bí mật được bảo vệ.
3. **Đăng ký phía server:** verifier lưu secret mới ở trạng thái pending/active theo lịch kích hoạt; chưa cần thu hồi secret cũ.
4. **Chuyển client:** client nhận secret mới và bắt đầu ký request bằng key ID mới. Mỗi request chỉ dùng một key ID/signature theo giao thức.
5. **Theo dõi:** server quan sát request dùng key mới, lỗi chữ ký, client còn dùng key cũ và độ trễ triển khai.
6. **Kết thúc overlap:** sau deadline, server từ chối key ID cũ và đánh dấu revoked/expired.
7. **Xác minh:** thử request bằng key mới thành công, key cũ bị từ chối ở mọi verifier/gateway/region.
8. **Dọn dẹp:** xóa hoặc vô hiệu hóa tham chiếu secret cũ theo retention policy; giữ audit metadata cần thiết.

~~~mermaid
flowchart TD
    A["Key k2 đang active"] --> B["Sinh key k3 + key ID mới"]
    B --> C["Lưu secret k3 an toàn<br/>đăng ký server-side"]
    C --> D["Phân phối k3 cho client"]
    D --> E["Client chuyển sang ký bằng k3"]
    E --> F["Theo dõi request k3 và client còn dùng k2"]
    F --> G{"Đã qua deadline<br/>và client chuyển đổi?"}
    G -->|"Chưa"| F
    G -->|"Rồi"| H["Từ chối k2 / revoke"]
    H --> I["Kiểm thử tất cả verifier"]
    I --> J["Rotation hoàn tất"]
~~~

Overlap là **thời gian server tạm thời chấp nhận cả key cũ và key mới**, không phải thời gian client gửi hai chữ ký để server tự chọn. Mỗi request phải có key ID rõ ràng và server chỉ xác minh bằng secret của đúng key ID đó. Không thử lần lượt mọi secret cho đến khi có chữ ký khớp: cách này làm tăng chi phí, mơ hồ về danh tính và mở rộng bề mặt tấn công.

### Điều kiện để overlap an toàn

- Thời gian bắt đầu/kết thúc được ghi rõ, có deadline và owner chịu trách nhiệm.
- Chỉ key ID đã đăng ký cho đúng client/tenant/environment được chấp nhận.
- Key cũ không được gia hạn vô thời hạn chỉ vì còn request đến.
- Server ghi nhận mức sử dụng từng key ID để biết client nào chưa chuyển.
- Khi overlap kết thúc, verifier từ chối key cũ ngay theo chính sách nhất quán.
- Nếu key cũ bị nghi lộ, bỏ qua overlap bình thường và áp dụng quy trình khẩn cấp.

## 6. Phân phối secret mới mà không làm lộ secret

Secret mới là credential có khả năng tạo request hợp lệ. Việc phân phối nó cũng quan trọng như việc sinh secret.

Các phương thức phù hợp tùy kiến trúc:

- **Secret manager/vault:** client workload được cấp quyền đọc đúng secret reference qua workload identity hoặc quyền truy cập có giới hạn.
- **Kênh trao đổi đã xác thực:** dùng một kênh bảo vệ, xác minh danh tính hai phía và hạn chế người nhận.
- **Bootstrap credential ngắn hạn:** dùng cơ chế cấp phát ban đầu để client lấy secret mới, sau đó bootstrap credential hết hiệu lực.
- **Quy trình đối tác có kiểm soát:** xác minh contact/owner, gửi secret qua phương thức được phê duyệt và yêu cầu xác nhận nhận secret.

Không gửi HMAC secret trong URL, query string, ticket hỗ trợ, email nhóm không mã hóa, chat công khai hoặc commit repository. Không hiển thị secret cũ để người dùng “copy lại”; thông thường chỉ hiển thị secret mới đúng lúc tạo hoặc cung cấp thông qua vault.

### Phân quyền truy cập secret

- Mỗi workload chỉ đọc secret của chính nó.
- Nhân viên vận hành không cần xem bản rõ nếu có thể thực hiện rotation qua quy trình tự động.
- Quyền đọc, tạo, kích hoạt và thu hồi secret nên tách biệt theo vai trò khi mức rủi ro yêu cầu.
- Secret manager cần audit truy cập và có khả năng phát hiện truy cập bất thường.
- Pipeline CI/CD không nên in secret ra console, artifact hoặc biến môi trường được dump khi lỗi.

**Không ghi secret vào log để debug lỗi HMAC.** Khi xác minh thất bại, log key ID, client ID, mã lỗi và request ID đã làm sạch; không log secret, chữ ký đầy đủ nếu không cần, hoặc canonical request chứa dữ liệu nhạy cảm.

## 7. Xác minh request trong giai đoạn rotation

Server nhận key ID và tìm đúng phiên bản secret. Việc xác minh phải kiểm tra cả trạng thái key và tính hợp lệ của request:

1. Đọc key ID từ header được quy định; từ chối nếu thiếu hoặc định dạng sai.
2. Tra credential trong đúng tenant/client scope.
3. Kiểm tra key status, not-before, expiry và thời điểm thu hồi.
4. Kiểm tra thuật toán theo cấu hình server; không để client tự chọn thuật toán yếu.
5. Kiểm tra timestamp trong cửa sổ cho phép và nonce chưa từng dùng.
6. Tự xây dựng canonical request từ request thực tế, bao gồm method, path/query, header cần ký và body digest.
7. Tính HMAC bằng secret đúng key ID; so sánh bằng hàm constant-time của thư viện.
8. Sau khi xác thực, kiểm tra scope, quota, owner và quyền truy cập resource.

~~~text
verifySignedRequest(request):
    keyId = readRequiredKeyId(request)
    record = lookupKeyForClientAndTenant(keyId, request.clientContext)
    if record is missing:
        return unauthorized()

    require record.status is acceptedForCurrentTime()
    require record.algorithm == serverConfiguredAlgorithm
    require timestampWithinAllowedWindow(request.timestamp)
    require nonceNotPreviouslyUsed(request.clientId, request.nonce)

    canonical = buildCanonicalRequestFromReceivedRequest(request)
    expected = HMAC(record.secret, canonical)
    if not constantTimeEqual(expected, request.signature):
        recordFailureWithoutSecret(keyId, request.id)
        return unauthorized()

    if not atomicallyConsumeNonce(request.clientId, request.nonce):
        return replayRejected()
    require authorizationAllows(record.owner, record.scopes, request.resource)
    return authenticatedPrincipal(record.owner)
~~~

Đây là mã giả để minh họa. Trong triển khai thực tế, phải xử lý race condition khi hai request cùng dùng một nonce: kiểm tra và ghi nonce cần nguyên tử. Nếu kiểm tra nonce trước rồi ghi sau bằng hai thao tác không nguyên tử, hai request song song có thể cùng vượt qua. Timestamp và nonce là lớp chống replay của request; **secret rotation không thay thế chúng**.

## 8. Chống replay trong khi chuyển secret

Một request HMAC hợp lệ có thể bị ghi lại và phát lại. Khi secret cũ và mới cùng được chấp nhận trong overlap, việc chống replay càng cần rõ ràng.

Một request nên ký ít nhất các thành phần phù hợp:

- HTTP method.
- Path và query đã canonicalize.
- Body digest hoặc nội dung body theo quy tắc nhất quán.
- Timestamp có cửa sổ chấp nhận ngắn.
- Nonce ngẫu nhiên duy nhất trong phạm vi client.
- Các header nhạy cảm có ảnh hưởng đến cách xử lý request.

Server cần:

- Từ chối timestamp quá cũ hoặc quá xa trong tương lai theo clock-skew policy.
- Lưu nonce đã dùng trong một khoảng ít nhất bằng cửa sổ chấp nhận replay.
- Ràng buộc nonce với client/key ID hoặc transaction scope phù hợp.
- Dùng idempotency key ở tầng nghiệp vụ cho thao tác có thể retry, ví dụ tạo thanh toán.
- Không chấp nhận cùng chữ ký ở một endpoint khác nếu method/path/body không nằm trong canonical request.

**Rotation không tự ngăn replay:** nếu một chữ ký cũ vẫn nằm trong cửa sổ timestamp và nonce chưa bị đánh dấu đã dùng, server có thể chấp nhận nó dù client đã bắt đầu dùng key mới. Vì vậy, thiết kế replay protection và key version phải độc lập, cùng được kiểm tra.

## 9. Rotation trong hệ thống nhiều client và nhiều region

Một secret có thể được dùng bởi nhiều instance của cùng một workload hoặc nhiều client độc lập. Rotation cần xác định rõ phạm vi:

| Phạm vi | Cách tổ chức |
| --- | --- |
| Một client/đối tác | Mỗi đối tác có key ID và secret riêng; rotation không ảnh hưởng đối tác khác. |
| Một workload nhiều instance | Tất cả instance lấy secret mới từ cùng secret reference; deploy có kiểm soát và theo dõi phiên bản đang dùng. |
| Nhiều môi trường | Dev/staging/production dùng secret riêng; không chia sẻ cùng key ID hoặc secret. |
| Nhiều region/gateway | Registry hoặc event propagation đưa trạng thái key version tới mọi verifier; có kiểm tra độ trễ. |
| Nhiều phiên bản ứng dụng | Hỗ trợ cấu hình key ID mới trước khi client phát request bằng key đó; không yêu cầu mọi instance đổi cùng một mili giây. |

### Cập nhật cấu hình nguyên tử

Client có thể đọc secret từ file cấu hình hoặc secret manager. Không nên cập nhật hai biến riêng lẻ theo cách khiến một request lấy key ID mới nhưng secret cũ. Cần quản lý cặp \`key_id + secret_ref\` như một **cấu hình phiên bản nguyên tử**:

~~~text
HmacSigningConfig v12:
  key_id: partner-42-k2
  secret_ref: vault://partner-42/k2

HmacSigningConfig v13:
  key_id: partner-42-k3
  secret_ref: vault://partner-42/k3
~~~

Một instance chỉ chuyển từ v12 sang v13 sau khi đã tải và xác minh secret mới thành công. Mỗi request nên chụp một snapshot cấu hình để key ID và secret luôn thuộc cùng phiên bản. Tránh đọc key ID và secret ở hai thời điểm khác nhau trong lúc rotation.

### Theo dõi propagation

Server có thể theo dõi:

- Thời điểm key mới được tạo và kích hoạt.
- Số request theo key ID ở từng client, region và gateway.
- Instance nào vẫn dùng key cũ.
- Thời điểm verifier cuối cùng nhận trạng thái mới.
- Lỗi signature tăng đột biến sau cutover.

Không nên dựa vào một dashboard tổng hợp duy nhất nếu nó bỏ sót gateway/region. Cần kiểm thử trực tiếp tại từng điểm xác minh hoặc có telemetry đảm bảo độ phủ.

## 10. Rotation khẩn cấp khi secret bị lộ

Khi secret có khả năng bị lộ, mục tiêu chính là **chặn sử dụng trái phép càng sớm càng tốt**. Quy trình:

1. Xác định key ID, owner, tenant, environment, scope và verifier đang chấp nhận key.
2. Đánh giá secret có thể đã bị sao chép ở đâu: repository, log, pipeline, máy client, backup, ticket hoặc secret manager.
3. Thu hồi key cũ hoặc vô hiệu hóa ngay theo incident policy; không giữ overlap dài để chờ tất cả client tự cập nhật.
4. Cấp secret mới qua kênh tin cậy, có thể tạm dừng client hoặc endpoint nếu chưa thể cập nhật an toàn.
5. Cập nhật client và xác minh chữ ký bằng key mới.
6. Kiểm tra tất cả gateway/region từ chối key cũ; đo propagation latency.
7. Rà soát request đã dùng key bị lộ, dữ liệu đã truy cập và hành động đã thực hiện.
8. Kiểm tra credential hoặc token khác có thể đã được tạo bằng quyền của key.
9. Gỡ secret khỏi nơi lưu trữ hiện tại, xử lý repository/log/backup theo chính sách và cải thiện secret scanning.

Nếu secret đã bị lộ, **không thể coi nó an toàn chỉ vì chưa thấy request đáng ngờ**. Kẻ tấn công có thể giữ bản sao và chờ thời điểm phù hợp. Việc xóa secret khỏi Git history hoặc log không thu hồi bản sao đã tải xuống.

### Thu hồi và ảnh hưởng tới request đang xử lý

Thu hồi key chặn request mới sau thời điểm verifier áp dụng trạng thái. Nó không tự rollback một giao dịch đã được thực hiện trước đó. Nếu request đã được xác thực trước thời điểm thu hồi nhưng đang xử lý, hệ thống cần xác định điểm commit nghiệp vụ và có quy trình xử lý gian lận/điều tra riêng.

Đối với API cực kỳ nhạy cảm, có thể kiểm tra trạng thái key trực tuyến ngay tại điểm thực thi hoặc kiểm tra lại trước khi commit thao tác. Đánh đổi là độ trễ và phụ thuộc registry; quyết định phải phù hợp với threat model.

## 11. Rollback và xử lý lỗi rotation

Rotation có thể thất bại do secret manager không sẵn sàng, client chưa cập nhật, sai canonicalization, lệch đồng hồ hoặc gateway chưa nhận key mới.

| Lỗi | Hành vi an toàn | Hướng xử lý |
| --- | --- | --- |
| Client chưa nhận secret mới | Tiếp tục dùng key cũ chỉ trong overlap đã định (rotation thường). | Kiểm tra quyền truy cập vault và deploy client; không kéo dài vô hạn. |
| Client có key ID mới nhưng secret cũ | HMAC không khớp. | Cập nhật cặp config nguyên tử; không thử secret khác ngầm định. |
| Server chưa có secret mới | Từ chối key ID mới. | Phân phối registry/secret trước khi client cutover. |
| Cache region chưa cập nhật | Có thể gây từ chối key mới hoặc chấp nhận key cũ quá lâu. | Invalidate/reconcile, kiểm tra mọi region và propagation objective. |
| Canonical request khác nhau | Chữ ký thất bại dù hai bên có cùng secret. | Chuẩn hóa contract, kiểm thử vector chung, không nới kiểm tra chữ ký. |
| Đồng hồ lệch | Request bị từ chối do timestamp. | Đồng bộ thời gian; cửa sổ skew phải giới hạn. |
| Secret cũ bị lộ trong lúc overlap | Attacker vẫn có thể ký request bằng key cũ. | Dừng overlap, revoke khẩn cấp và điều tra. |
| Rollback deploy ứng dụng | Bản cũ có thể chỉ biết key ID cũ. | Không khôi phục secret bị thu hồi; deploy bản tương thích với key mới hoặc tạm dừng client. |

**Rollback phần mềm không đồng nghĩa rollback trạng thái tin cậy.** Nếu key cũ đã bị thu hồi do lộ, không được khôi phục nó chỉ để chạy lại phiên bản ứng dụng cũ. Cần sửa/triển khai client tương thích với key mới, hoặc tạo một key mới khác qua quy trình cấp phát an toàn.

## 12. Canonicalization và thay đổi giao thức trong rotation

Rotation thường được thực hiện cùng thay đổi thuật toán, header hoặc canonicalization. Gộp nhiều thay đổi vào cùng một lần chuyển đổi làm việc điều tra lỗi khó hơn. Nếu phải thay đổi giao thức, nên có version rõ ràng:

~~~text
X-Signature-Version: 1
X-Key-Id: partner-42-k3
X-Request-Timestamp: ...
X-Request-Nonce: ...
Authorization: HMAC-SHA256 ...
~~~

Server phải cấu hình trước các phiên bản được phép và ràng buộc từng key với thuật toán/phiên bản đã đăng ký. Không để request tự khai \`algorithm=none\` hoặc yêu cầu server thử nhiều thuật toán cho tới khi một chữ ký khớp.

Canonicalization phải xác định rõ:

- Method viết hoa hay giữ nguyên; path đã percent-decode/encode theo quy tắc nào.
- Query parameters được sắp xếp hay giữ thứ tự; xử lý tham số trùng ra sao.
- Header nào được ký; xử lý khoảng trắng, chữ hoa/thường và duplicate header thế nào.
- Body digest tính trên byte nào; encoding và content transformation được thực hiện ở đâu.
- Timestamp/nonce được biểu diễn và chuẩn hóa ra sao.
- Phiên bản giao thức và thuật toán được ràng buộc trong dữ liệu ký thế nào.

Không thay đổi cách chuẩn hóa một cách âm thầm khi rotation. Client và server cần test vectors giống nhau trước cutover; chữ ký phải khác nếu một trường đã được ký bị thay đổi.

## 13. Mã giả: rotation có giai đoạn overlap

Mã giả sau minh họa quy trình quản lý phiên bản secret; đây không phải code production:

~~~text
prepareRotation(clientId):
    require rotationPolicy.allows(clientId)
    newKeyId = allocateUniqueKeyId(clientId)
    newSecret = secureRandomBytes(requiredKeyLength)

    storeSecretInVault(newKeyId, newSecret)
    createKeyRecordAtomically(
        clientId = clientId,
        keyId = newKeyId,
        secretRef = vaultReference(newKeyId),
        status = "pending",
        algorithm = configuredHmacAlgorithm
    )
    deliverSecretThroughApprovedChannel(clientId, newKeyId)
    return newKeyId

activateNewKey(clientId, newKeyId, activationTime):
    require ownerConfirmedReceipt(clientId, newKeyId)
    require serverCanLoadAndVerifySecret(newKeyId)
    atomically:
        markKeyActive(newKeyId, activationTime)
        markOldKeyRetiring(clientId, boundedOverlapDeadline)
    publishKeyRegistryChange(clientId)

retireOldKey(clientId, oldKeyId):
    require overlapDeadlinePassed(oldKeyId)
    atomically:
        markKeyRevoked(oldKeyId)
        setRevocationTimestamp(oldKeyId, trustedClock.now())
    publishRevocationEvent(oldKeyId)
    verifyEveryVerifierRejects(oldKeyId)
~~~

Trong triển khai thực tế, không trả secret từ hàm quản trị hoặc log. \`deliverSecretThroughApprovedChannel\` cần xác thực người nhận và tránh ghi secret vào audit. Việc chuyển active/retiring cần có transaction và xử lý đồng thời; event có thể retry nhưng consumer phải idempotent. Với key đã lộ, gọi quy trình emergency revoke thay vì chờ overlap deadline.

## 14. Kiểm thử rotation và HMAC verifier

Một bộ kiểm thử nên bao gồm:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Request ký bằng key mới sau activation | Được xác minh nếu canonical request và policy hợp lệ. |
| Request ký bằng key cũ trong overlap | Chỉ được chấp nhận trong thời hạn và chính sách đã định. |
| Request ký bằng key cũ sau revoke/deadline | Bị từ chối ở mọi verifier. |
| Key ID không tồn tại hoặc thuộc client khác | Bị từ chối; không thử secret của client khác. |
| Key ID mới nhưng secret không khớp | Bị từ chối; không fallback ngầm sang key cũ. |
| Timestamp quá cũ/quá xa tương lai | Bị từ chối theo clock-skew policy. |
| Nonce đã dùng | Bị từ chối; xử lý nguyên tử khi request đồng thời. |
| Method/path/query/body thay đổi sau ký | HMAC không khớp. |
| Thuật toán không được cấu hình | Bị từ chối; không downgrade. |
| Gateway mất event invalidation | TTL/reconcile giới hạn thời gian chấp nhận trạng thái cũ. |
| Secret manager tạm thời không sẵn sàng | Không tự chấp nhận key chưa kiểm chứng; phản hồi lỗi theo policy. |
| Client rollback về phiên bản chỉ biết key cũ đã revoked | Request bị từ chối; cần deploy client tương thích key mới. |
| Secret xuất hiện trong log/trace | Kiểm thử phải phát hiện và pipeline phải ngăn việc ghi lộ. |
| Hai request dùng cùng nonce đồng thời | Chỉ một request có thể tiêu thụ nonce. |

### Test vectors và kiểm thử tương thích

Client và server nên chia sẻ test vectors gồm:

- Input key/secret giả lập chỉ dùng trong test.
- Method, path, query, header và body bytes.
- Canonical request kỳ vọng.
- HMAC signature kỳ vọng.
- Các trường hợp chỉ thay đổi một byte/field để xác nhận chữ ký không còn khớp.

Không dùng secret production trong test vector, tài liệu, CI log hoặc môi trường staging. Test vector phải kiểm tra chính xác byte encoding, newline, percent-encoding và body digest; nhiều lỗi HMAC xuất phát từ canonicalization không thống nhất hơn là thuật toán HMAC.

## 15. Audit và chỉ số vận hành

Các sự kiện rotation nên ghi:

- Client/owner, tenant, environment và key ID.
- Actor hoặc service identity tạo, kích hoạt, thu hồi key.
- Thời điểm tạo, thời điểm bắt đầu overlap, deadline và thời điểm revoke commit.
- Kết quả phân phối secret (chỉ trạng thái, không phải secret).
- Số request theo key ID, client/instance/region và tỷ lệ signature failure.
- Thời gian từ commit tới khi verifier cuối cùng áp dụng trạng thái mới.
- Request dùng key cũ sau deadline và lỗi cache/event propagation.

Không ghi secret, HMAC key, credential header đầy đủ hoặc payload nhạy cảm. Nếu cần điều tra một request, dùng request ID, key ID và metadata đã giảm thiểu.

Chỉ số hữu ích:

| Chỉ số | Ý nghĩa |
| --- | --- |
| **Rotation completion rate** | Tỷ lệ client đã chuyển sang key ID mới trước deadline. |
| **Old-key usage** | Số request còn dùng key cũ trong overlap và sau deadline. |
| **Revocation propagation latency** | Thời gian từ revoke commit đến khi mọi verifier từ chối key cũ. |
| **Signature failure rate** | Phát hiện lỗi canonicalization, cấu hình hoặc request giả. |
| **Unknown key ID rate** | Phát hiện client cấu hình sai hoặc request dò key ID. |
| **Secret access anomaly** | Phát hiện đọc secret bất thường từ vault/KMS. |

Không kết luận rotation thành công chỉ vì client chính đã đổi key. Phải kiểm tra mọi instance, gateway, region và batch worker có thể ký hoặc xác minh request.

## 16. Tình huống thực tế: đối tác tích hợp HMAC qua nhiều region

Một đối tác gọi API đơn hàng bằng HMAC-SHA-256. Client của đối tác chạy ở hai vùng triển khai; API của nhà cung cấp có gateway tại ba region. Secret \`k8\` đang hoạt động và cần thay bằng \`k9\` theo lịch.

### Kế hoạch chuyển đổi

1. Tạo \`keyId=k9\` và secret mới trong vault; chỉ cấp quyền đọc cho workload của đối tác.
2. Đăng ký \`k9\` ở cả ba region dưới trạng thái pending/active theo cùng lịch.
3. Xác minh các gateway có thể tra secret mới và có cùng canonicalization/version policy.
4. Đối tác triển khai cấu hình \`keyId + secretRef\` mới theo một snapshot nguyên tử ở cả hai vùng.
5. Theo dõi request \`k9\`, xác nhận chữ ký hợp lệ và phát hiện instance nào còn dùng \`k8\`.
6. Hết overlap, revoke \`k8\`, phát invalidation event và xác minh ba region từ chối request ký bằng \`k8\`.
7. Rà soát request cũ và dọn tham chiếu secret sau khi hoàn tất retention.

### Nếu một region chưa nhận event revoke

Không thể tuyên bố key cũ đã bị thu hồi toàn hệ thống. Cần:

- Kiểm tra consumer/event lag và trạng thái cache ở region đó.
- Chủ động reconcile registry hoặc invalidate cache qua kênh quản trị.
- Nếu chưa bảo đảm được trạng thái, tạm giới hạn traffic/endpoint liên quan theo incident policy.
- Đo thời điểm region bắt đầu từ chối key cũ và ghi nhận propagation latency.
- Điều tra vì sao event bị bỏ lỡ và thêm kiểm thử cho lỗi tương tự.

### Nếu secret cũ bị phát hiện trong log trước ngày rotation

Đây không còn là rotation định kỳ. Phải coi secret đã bị lộ, thu hồi theo quy trình khẩn cấp, cấp key mới và đánh giá request trong khoảng có thể bị khai thác. Không đợi hết overlap chỉ vì lịch rotation đã được phê duyệt.

## 17. Checklist thiết kế secret rotation

- [ ] Mỗi client/tenant/environment có HMAC secret riêng, ngẫu nhiên và đủ mạnh.
- [ ] Key ID không bí mật, duy nhất trong phạm vi phù hợp và gắn với owner/tenant.
- [ ] Secret nằm trong vault/KMS hoặc kho được bảo vệ; không commit hoặc log.
- [ ] Thuật toán HMAC, key length và canonical request version được cấu hình ở server.
- [ ] Timestamp, nonce và replay protection được kiểm tra độc lập với rotation.
- [ ] Rotation có trạng thái pending/active/retiring/revoked và thời hạn rõ.
- [ ] Secret mới được phân phối qua kênh xác thực, giới hạn đúng client/workload.
- [ ] Client chuyển key ID và secret reference nguyên tử.
- [ ] Overlap có deadline, chỉ chấp nhận key ID đã đăng ký và không kéo dài vô hạn.
- [ ] Rotation khẩn cấp bỏ qua overlap bình thường khi secret có nguy cơ bị lộ.
- [ ] Mọi gateway/region/cache nhận trạng thái mới; propagation latency được đo.
- [ ] Rollback phần mềm không làm sống lại secret đã bị thu hồi.
- [ ] Có test vectors chung và kiểm thử canonicalization, chữ ký, nonce, timestamp.
- [ ] Audit có actor/time/reason/key ID nhưng không có secret.
- [ ] Sau rotation, request bằng key cũ bị từ chối ở mọi verifier.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao HMAC secret mới cần key ID mới thay vì ghi đè secret cũ dưới cùng một định danh?

**Gợi ý:** Key ID cho phép server chọn đúng phiên bản, theo dõi overlap, xác định request đang dùng key nào và thu hồi riêng từng phiên bản.

**Câu 2.** Vì sao server có thể tạm chấp nhận key cũ và mới trong rotation định kỳ nhưng không nên làm vậy khi key cũ đã bị lộ?

**Gợi ý:** Overlap giúp client chuyển đổi không gián đoạn; khi key bị lộ, attacker vẫn có thể tạo chữ ký hợp lệ trong thời gian overlap nên cần thu hồi nhanh.

**Câu 3.** Secret rotation có tự ngăn replay một request HMAC đã ký không?

**Gợi ý:** Không. Cần timestamp, nonce, lưu trạng thái chống replay và idempotency ở tầng nghiệp vụ.

**Câu 4.** Tại sao client phải cập nhật key ID và secret như một cấu hình nguyên tử?

**Gợi ý:** Nếu một request dùng key ID mới với secret cũ (hoặc ngược lại), chữ ký sẽ thất bại; snapshot nguyên tử tránh cấu hình lai trong lúc deploy.

**Câu 5.** Nếu database đã đánh dấu key cũ revoked nhưng một gateway còn cache active, key đã bị vô hiệu hóa hoàn toàn chưa?

**Gợi ý:** Chưa. Phải xác minh mọi verifier áp dụng trạng thái hoặc có TTL/invalidation bảo đảm thời gian chấp nhận cũ bị giới hạn.

**Câu 6.** Vì sao rollback ứng dụng không được khôi phục secret đã bị thu hồi?

**Gợi ý:** Secret đã thu hồi có thể bị lộ; đưa nó trở lại active sẽ mở lại quyền cho kẻ tấn công. Cần cập nhật phần mềm tương thích secret mới.

## 19. Ghi nhớ

**Secret rotation trong HMAC request authentication là thay một credential khóa đối xứng bằng phiên bản mới, đồng bộ giữa client và mọi verifier, rồi vô hiệu hóa phiên bản cũ theo thời điểm được kiểm soát.** Một quy trình an toàn cần key ID riêng, secret ngẫu nhiên được bảo vệ, phân phối xác thực, overlap có giới hạn cho rotation định kỳ, thu hồi khẩn cấp khi bị lộ, propagation tới mọi gateway/region và kiểm thử key cũ bị từ chối. HMAC vẫn cần TLS, timestamp/nonce chống replay, canonicalization thống nhất và authorization theo scope. Rotation chỉ hoàn tất khi mọi điểm xác minh đã áp dụng key mới và không còn chấp nhận secret cũ.
