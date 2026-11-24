# Rotate client secrets: quy trình xoay vòng credential cho OAuth client

## 1. Bối cảnh và mục tiêu

Trong OAuth 2.0, một confidential client cần chứng minh danh tính khi gọi token endpoint hoặc một endpoint được bảo vệ. Cách xác thực có thể dùng **client_secret**, chữ ký bằng private key (**private_key_jwt**), chứng chỉ TLS (mTLS) hoặc cơ chế workload identity khác. Credential của client có thể bị lộ qua cấu hình, CI/CD, log, bản sao lưu, máy developer hoặc một workload bị xâm nhập. Vì vậy, tổ chức cần quy trình **rotate client secrets**: thay credential đang sử dụng bằng credential mới, cập nhật các thành phần phụ thuộc và vô hiệu hóa credential cũ theo thời điểm đã kiểm soát.

Xoay vòng credential là một hoạt động vận hành vòng đời bảo mật. Mục tiêu là giảm thời gian một credential bị lộ còn có thể bị sử dụng, giới hạn phạm vi ảnh hưởng, duy trì khả năng xác thực của service và tạo được bằng chứng kiểm toán. Việc đổi chuỗi secret trong một file cấu hình chỉ là một phần nhỏ; nếu các replica, worker, pipeline hoặc môi trường khác vẫn dùng credential cũ thì rotation chưa hoàn tất.

Bài thuộc chương **Operations** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung gắn với mô hình tin cậy và vòng đời token bảo mật, phân biệt JWT/opaque token, access/refresh token, OAuth 2.0/OIDC, issuer, claims, scope, audience, lưu trữ, thu hồi và phòng chống token bị đánh cắp hoặc phát lại.

Sau bài này, người học có thể:

1. Phân biệt client secret, access token, refresh token, private key và chứng chỉ mTLS.
2. Lập kế hoạch xoay vòng credential theo mô hình overlap để hạn chế downtime.
3. Cập nhật secret an toàn qua secret manager, CI/CD, workload và authorization server.
4. Xác minh credential mới hoạt động trước khi thu hồi credential cũ.
5. Xử lý rollback, rotation khẩn cấp, nhiều replica và credential bị lộ.
6. Thiết lập audit, cảnh báo và kiểm thử để chứng minh rotation hoàn tất.

## 2. Credential nào cần được xoay vòng?

Không phải mọi token đều là client secret. Cần phân loại đúng đối tượng để chọn quy trình:

| Credential | Mục đích | Rotation thường diễn ra ở đâu? |
| --- | --- | --- |
| **OAuth client secret** | Confidential client xác thực với authorization server | Authorization server cấp secret mới; secret manager và ứng dụng client được cập nhật. |
| **Private key của private_key_jwt** | Client ký client assertion gửi tới token endpoint | Sinh key pair mới, đăng ký public key/JWK mới, triển khai private key mới rồi gỡ public key cũ. |
| **Chứng chỉ mTLS** | Xác thực client bằng TLS certificate và có thể ràng buộc access token với chứng chỉ | CA/PKI, trust store, client certificate và authorization server được cập nhật theo giai đoạn. |
| **Workload identity/federation** | Chứng minh workload qua môi trường/hạ tầng tin cậy | Xoay vòng trust configuration, signing key hoặc credential của nền tảng theo cơ chế nhà cung cấp. |
| **Access token** | Gọi resource server với audience/scope được cấp | Thường để token hết hạn hoặc revoke theo policy; không phải client secret. |
| **Refresh token** | Xin access token mới | Rotation/reuse detection hoặc revocation theo grant/session; không thay thế việc xoay client credential. |

**Client secret rotation không đồng nghĩa token rotation.** Đổi client secret không tự động thu hồi mọi access token đã phát hành. Ngược lại, thu hồi refresh token không làm client secret cũ biến mất. Đây là hai vòng đời riêng, có thể cần phối hợp khi xảy ra sự cố.

### 2.1. Client secret và token có quan hệ gì?

Một confidential client có thể dùng client secret để xác thực với authorization server khi xin access token:

~~~mermaid
sequenceDiagram
    autonumber
    participant App as OAuth Client
    participant AS as Authorization Server
    participant API as Resource Server

    App->>AS: client authentication + grant request
    AS->>AS: Xác minh client credential và policy
    AS-->>App: access token (audience/scope được cấp)
    App->>API: Authorization: Bearer access token
    API->>API: Xác minh access token và quyền
    API-->>App: Resource response
~~~

Secret chỉ xác thực client với authorization server trong chặng tương ứng. Resource server thường xác minh access token, không nhận client secret của ứng dụng. Không gửi client secret trong header Bearer, không gắn secret vào JWT claims và không chuyển secret sang downstream.

## 3. Khi nào cần rotation?

Rotation nên có lịch định kỳ dựa trên chính sách tổ chức và mức độ rủi ro, đồng thời phải có trigger khẩn cấp. Một số tình huống điển hình:

- Đến hạn tuổi credential theo policy.
- Nhân sự có quyền truy cập secret rời nhóm hoặc thay đổi vai trò.
- Credential xuất hiện trong log, repository, artifact, ticket, screenshot hoặc chat.
- Máy/runner/container có thể đã bị xâm nhập.
- Nhà cung cấp, auditor hoặc incident response yêu cầu thay credential.
- Thay đổi thuật toán, key size, CA, trust configuration hoặc tiêu chuẩn xác thực client.
- Cần thu hẹp quyền hoặc tách credential đang dùng chung cho nhiều ứng dụng.

Không nên chỉ rotation theo lịch mà bỏ qua khả năng phát hiện lộ secret. Một credential có thể bị đánh cắp ngay sau khi vừa xoay; vì vậy cần kiểm soát truy cập, giám sát bất thường, giới hạn scope và khả năng revoke khẩn cấp.

### 3.1. Định nghĩa chính sách trước khi vận hành

Mỗi loại credential cần có:

| Thuộc tính | Câu hỏi cần trả lời |
| --- | --- |
| Owner | Team/service nào chịu trách nhiệm? |
| Client identity | Client ID/registration nào đang sử dụng credential? |
| Environment | Dev, test, staging, production có credential riêng chưa? |
| Credential type | Client secret, private key, certificate hay workload identity? |
| Expiration | Có thời hạn bắt buộc không? Ai nhận cảnh báo trước hạn? |
| Rotation interval | Chu kỳ dựa trên policy/risk nào? |
| Overlap support | Authorization server có cho phép hai credential hợp lệ đồng thời không? |
| Rollback | Có thể khôi phục credential trước trong khoảng nào và khi nào phải revoke ngay? |
| Revocation | Ai được phép disable credential cũ? |
| Evidence | Log, ticket, change ID, health check và kết quả kiểm thử nào chứng minh hoàn tất? |

Không ghi giá trị secret vào inventory. Chỉ lưu metadata như secret reference/version, fingerprint không đảo ngược phù hợp, ngày tạo/hết hạn, owner và trạng thái.

## 4. Nguyên tắc rotation không gián đoạn

Quy trình an toàn thường dùng **overlap**: credential mới được tạo và triển khai trước khi credential cũ bị vô hiệu hóa. Trong khoảng overlap, authorization server chấp nhận cả hai credential cho cùng client hoặc chấp nhận hai key/certificate theo trust configuration. Sau khi xác minh tất cả workload đã dùng credential mới, operator mới thu hồi credential cũ.

Không phải authorization server nào cũng hỗ trợ nhiều client secret đồng thời. Nếu chỉ cho phép một secret tại một thời điểm, cần dùng cơ chế staged credential/client registration riêng hoặc một cửa sổ bảo trì được kiểm soát; không giả định có thể bật overlap nếu nhà cung cấp không hỗ trợ.

### 4.1. Luồng rotation hai pha

~~~mermaid
flowchart TD
    A[Inventory credential và owner] --> B[Tạo credential mới]
    B --> C[Đăng ký/cho phép credential mới tại AS]
    C --> D[Đưa secret version mới vào secret manager]
    D --> E[Deploy/reload từng workload]
    E --> F[Health check và xác minh token request]
    F --> G{Tất cả instance dùng credential mới?}
    G -->|Chưa| H[Giữ credential cũ, xử lý rollout]
    H --> E
    G -->|Rồi| I[Disable/revoke credential cũ]
    I --> J[Kiểm tra credential cũ bị từ chối]
    J --> K[Đóng change và lưu evidence]
~~~

Hai pha chính:

1. **Pha thêm mới và chuyển đổi:** tạo credential mới, cho phép tại authorization server, phân phối qua secret manager, cập nhật tất cả consumer, xác minh hoạt động.
2. **Pha thu hồi:** xác nhận không còn workload hợp lệ dùng credential cũ, disable/revoke credential cũ, kiểm tra hành vi từ chối và cập nhật inventory.

Điều kiện quan trọng là không thu hồi credential cũ chỉ dựa vào một lần health check. Phải xác định tất cả consumer, kể cả scheduled job, worker ít chạy, autoscaling template, pipeline và môi trường dự phòng.

## 5. Quy trình vận hành chi tiết

### Bước 1: Lập inventory và xác định blast radius

Tìm các consumer của credential:

- Ứng dụng chính, background worker, cron job, consumer queue.
- Tất cả replica/pod/VM và autoscaling group.
- Pipeline build/deploy, migration job và automation.
- Secret reference trong từng environment và region.
- Bản sao cấu hình, backup, image hoặc artifact có thể chứa credential cũ.
- Authorization server/client registration, key store, certificate store và trust policy.

Xác định client ID, owner, scope được cấp, audience/resource, grant type, endpoint sử dụng, tần suất gọi và phụ thuộc. Credential dùng chung cho nhiều service làm tăng blast radius; nếu khả thi, tách client registration/secret riêng theo workload trước hoặc trong một change có kế hoạch.

### Bước 2: Kiểm tra khả năng overlap và chuẩn bị rollback

Trước khi tạo credential mới, xác minh authorization server hỗ trợ:

- Nhiều client secret active đồng thời hay chỉ một secret.
- Nhiều public key/JWK được đăng ký cùng lúc.
- Nhiều certificate/trust anchor trong thời gian chuyển tiếp.
- Thời gian propagation của cấu hình tới mọi node.
- Cơ chế disable/revoke credential cụ thể.
- Audit event và cách truy vấn credential nào đã xác thực.

Chuẩn bị rollback trước khi deploy. Rollback có thể quay workload về secret version cũ trong thời gian overlap, nhưng không thể dùng credential cũ sau khi đã revoke. Với incident lộ secret, không rollback về credential bị lộ; phải xử lý nguyên nhân và dùng credential mới khác.

### Bước 3: Tạo credential mới

Tạo secret bằng chức năng quản lý credential của authorization server hoặc secret manager được phê duyệt. Dùng entropy/độ dài theo khuyến nghị của nhà cung cấp; không tự tạo secret bằng timestamp, UUID đơn giản, tên service hoặc password dễ đoán.

Với private key, tạo key pair mới trong HSM/KMS nếu hệ thống hỗ trợ. Private key không rời khỏi vùng bảo vệ nếu có thể; chỉ public key được đăng ký với authorization server. Với mTLS, yêu cầu certificate mới từ CA tin cậy và xác minh SAN/subject, EKU, validity, chain và client registration.

### Bước 4: Đăng ký credential mới tại authorization server

Đảm bảo credential mới gắn với đúng client ID và policy hiện hành. Không vô tình cấp client mới scope rộng hơn, audience khác hoặc grant type bổ sung chỉ để rotation dễ hơn.

Kiểm tra:

- Client ID không thay đổi ngoài kế hoạch.
- Grant type được phép giữ nguyên.
- Scope/resource/audience không bị mở rộng.
- Client authentication method được cấu hình đúng.
- Credential cũ vẫn active trong khoảng overlap được phê duyệt.
- Cấu hình đã propagate tới các node của authorization server.

### Bước 5: Lưu secret mới và phân phối

Đưa secret mới vào secret manager với version riêng. Workload chỉ được quyền đọc đúng secret reference mà nó cần. Dùng cơ chế version/alias có thể chuyển đổi có kiểm soát, chẳng hạn alias **current** trỏ tới version mới sau khi đã tạo và kiểm tra.

Không gửi secret qua email/chat, không paste vào ticket, không commit vào repository, không đặt trong Docker image hoặc build artifact. Pipeline nên lấy secret lúc runtime bằng workload identity hoặc credential broker phù hợp.

### Bước 6: Rollout workload

Deploy/reload từng nhóm instance theo chiến lược canary hoặc rolling update. Với mỗi instance:

1. Đọc secret version mới từ secret manager.
2. Khởi tạo OAuth client bằng credential mới.
3. Gọi token endpoint qua TLS và xác thực client.
4. Xác nhận token response hợp lệ và không log credential.
5. Thực hiện một health check nghiệp vụ an toàn bằng access token có audience/scope đúng.
6. Ghi nhận version reference đang dùng và trạng thái rollout.

Không ghi secret hoặc token ra health endpoint. Chỉ expose metadata không nhạy cảm như **credential_version**, **last_successful_authentication_at**, **client_id** hoặc trạng thái xác thực.

### Bước 7: Xác nhận không còn consumer dùng credential cũ

Kết hợp nhiều nguồn bằng chứng:

- Rollout status của toàn bộ replica, worker và scheduler.
- Secret access audit từ secret manager.
- Authorization server authentication event có credential/key identifier nếu hỗ trợ.
- Metrics lỗi **invalid_client**/client authentication.
- Job chạy theo chu kỳ đã được quan sát ít nhất một lần hoặc đã có kế hoạch kiểm chứng.
- Inventory xác nhận không còn config/automation tham chiếu version cũ.

Không thể chỉ dựa vào việc “không thấy request dùng secret cũ trong vài phút” nếu có job chạy mỗi ngày hoặc mỗi tuần. Cần đối chiếu chu kỳ chạy và consumer inventory.

### Bước 8: Thu hồi credential cũ

Disable hoặc revoke credential cũ tại authorization server/PKI. Với client secret, dùng chức năng revoke/rotate của nhà cung cấp. Với **private_key_jwt**, gỡ public JWK cũ khỏi client registration sau khi hết overlap. Với mTLS, loại bỏ certificate cũ khỏi trust configuration hoặc client registration khi không còn consumer.

Thu hồi phải có xác nhận trạng thái. Nếu provider hỗ trợ, kiểm tra credential cũ không thể xác thực client nữa. Không chỉ xóa secret khỏi secret manager; authorization server có thể vẫn chấp nhận credential cũ nếu chưa disable.

### Bước 9: Xác minh và đóng change

Chạy kiểm thử:

- Credential mới xác thực thành công.
- Token mới được cấp với đúng scope/audience.
- Resource server chấp nhận access token hợp lệ.
- Credential cũ bị từ chối sau khi revoke.
- Tất cả workload vẫn healthy sau khi credential cũ bị thu hồi.
- Không có secret/token bị lộ trong log, trace hoặc artifact.

Lưu change ID, thời gian bắt đầu/kết thúc, credential version/reference, owner, phạm vi workload, kết quả kiểm tra, sự cố và người phê duyệt. Không đưa giá trị secret vào evidence.

## 6. Chiến lược theo loại credential

### 6.1. Xoay vòng OAuth client secret

Nếu authorization server hỗ trợ hai secret active:

1. Tạo secret mới cho cùng client ID.
2. Lưu secret mới ở version riêng.
3. Cập nhật client workloads theo rolling deployment.
4. Quan sát authentication thành công bằng secret mới.
5. Disable secret cũ.
6. Xác minh secret cũ không thể lấy token mới.

Nếu server chỉ hỗ trợ một secret active, đổi secret có thể làm mọi instance đang giữ giá trị cũ thất bại ngay. Khi đó cần:

- Dùng client registration thứ hai tạm thời với policy tương đương, sau đó chuyển consumer theo kế hoạch; hoặc
- Thực hiện maintenance window với dừng/đồng bộ consumer; hoặc
- Chọn cơ chế xác thực client hỗ trợ key overlap tốt hơn trong kiến trúc dài hạn.

Client registration tạm thời phải được giới hạn scope, audience, grant type, thời hạn và owner; không để lại client phụ sau khi rotation xong.

### 6.2. Xoay vòng private_key_jwt

Với private_key_jwt, client tạo client assertion và ký bằng private key; authorization server xác minh bằng public key/JWK đã đăng ký. Rotation thường là:

1. Sinh key pair mới trong KMS/HSM.
2. Đăng ký public JWK mới với kid riêng.
3. Giữ public key cũ trong overlap.
4. Triển khai private key mới cho client.
5. Xác minh assertion có iss, sub, aud, exp, jti theo profile và được ký bởi key mới.
6. Xác nhận mọi instance dùng key mới.
7. Gỡ public JWK cũ khỏi client registration và retire private key cũ.

Client assertion thường có thời hạn rất ngắn và là JWT dùng để xác thực client; nó không phải access token. Không tái sử dụng client assertion cũ, và không log assertion đầy đủ.

### 6.3. Xoay vòng mTLS certificate

Với OAuth mTLS client authentication:

- Phát hành certificate mới từ CA được tin cậy.
- Cập nhật trust chain và registration để chấp nhận certificate mới trong khoảng overlap.
- Triển khai certificate/private key mới đến workloads.
- Kiểm tra TLS handshake, client identity, SAN/subject mapping và token endpoint.
- Xác minh token-bound certificate nếu access token được ràng buộc với chứng chỉ.
- Thu hồi certificate cũ và cập nhật CRL/OCSP hoặc trust configuration theo PKI.

Nếu dùng certificate-bound access token (RFC 8705), resource server có thể so sánh certificate của request với binding trong token. Xoay certificate của workload có thể ảnh hưởng đến access token đã cấp; cần kiểm tra semantics của hệ thống và có thể phải xin token mới sau khi chuyển certificate.

### 6.4. Workload identity và federation

Nếu platform cấp identity ngắn hạn cho workload (managed identity, SPIFFE/SVID hoặc federation), thường không cần một client secret tĩnh do ứng dụng giữ. Rotation tập trung vào trust relationship, signing key, issuer allowlist, audience và thời hạn chứng thực. Vẫn phải có quy trình khi trust anchor hoặc key của nền tảng bị lộ.

Không gọi mọi credential là “secret” rồi áp dụng một lệnh đổi chung. Mỗi cơ chế có điểm tin cậy, quy trình rollover và cách xác minh riêng.

## 7. Zero-downtime rollout và nhiều instance

Một service có thể chạy hàng chục replica ở nhiều zone. Chỉ một phần instance cập nhật secret mới có thể khiến lỗi xác thực xuất hiện ngẫu nhiên theo load balancer.

~~~mermaid
flowchart TD
    S[Secret version v2 được tạo] --> A[Authorization Server chấp nhận v1 và v2]
    A --> P1[Canary instance đọc v2]
    P1 --> H1{Token request thành công?}
    H1 -->|Không| R[Giữ v1, dừng rollout, điều tra]
    H1 -->|Có| P2[Rolling update các instance còn lại]
    P2 --> H2{Tất cả consumer đã dùng v2?}
    H2 -->|Không| W[Kiểm tra worker/job/replica còn sót]
    W --> P2
    H2 -->|Có| D[Disable v1]
    D --> V[Kiểm tra v1 bị từ chối và service vẫn healthy]
~~~

### 7.1. Trạng thái credential nên quan sát

| Trạng thái | Ý nghĩa | Hành động |
| --- | --- | --- |
| CREATED | Credential mới đã được sinh | Chưa được xem là sẵn sàng cho workload. |
| REGISTERED | Authorization server đã chấp nhận credential mới | Có thể bắt đầu rollout. |
| DEPLOYING | Consumer đang được cập nhật | Theo dõi từng replica/worker. |
| ACTIVE_NEW | Consumer đã xác thực bằng credential mới | Tiếp tục kiểm chứng độ phủ. |
| OLD_DISABLED | Credential cũ đã bị vô hiệu hóa | Chạy negative test và kiểm tra service. |
| VERIFIED | Rotation đã có đủ evidence | Đóng change, cập nhật inventory. |
| FAILED/ROLLBACK | Có lỗi cần dừng hoặc quay lại trong overlap | Không thu hồi credential cũ nếu rollback hợp lệ và chưa có incident lộ secret. |

Tên trạng thái là gợi ý cho runbook nội bộ, không phải trạng thái OAuth tiêu chuẩn.

### 7.2. Xử lý instance không cập nhật

Nếu một replica vẫn dùng secret cũ:

- Xác định nó là instance đang phục vụ, worker nhàn rỗi hay node bị partition.
- Không disable secret cũ trước khi biết ảnh hưởng; nếu rotation do lộ secret, ưu tiên containment theo incident policy.
- Cordon/drain hoặc dừng instance cũ theo quy trình rollout.
- Kiểm tra image, environment, mounted secret, cache và process có reload version mới không.
- Sau khi disable credential cũ, tiếp tục quan sát lỗi invalid_client và authentication failure.

Không để một worker ít chạy giữ credential cũ vô thời hạn chỉ vì chưa thấy traffic.

## 8. Rollback và rotation khẩn cấp

### 8.1. Rollback trong rotation định kỳ

Nếu credential mới không hoạt động do cấu hình sai:

1. Dừng rollout.
2. Giữ credential cũ active nếu chưa bị lộ và policy cho phép.
3. Chuyển workload về version cũ đã được kiểm chứng.
4. Điều tra nguyên nhân: secret sai, client ID nhầm, auth method sai, propagation chậm, certificate chain lỗi hoặc permission bị thay đổi.
5. Sửa và tạo lại credential mới; không tái sử dụng một secret đã vô tình bị lộ.

Rollback phải có giới hạn thời gian. Nếu credential cũ đã đến hạn hoặc bị nghi lộ, không được kéo dài chỉ để giữ availability; cần chuyển sang phương án credential khác đã được phê duyệt.

### 8.2. Rotation khẩn cấp khi credential bị lộ

Trong incident, thứ tự ưu tiên khác rotation định kỳ:

1. Xác định client, credential version, environment và phạm vi có thể bị lộ.
2. Tạo credential thay thế trong kênh bảo mật nếu khả thi.
3. Cập nhật authorization server và workload tin cậy.
4. **Revoke credential bị lộ càng sớm càng tốt** theo incident policy; có thể chấp nhận gián đoạn có kiểm soát để ngăn lạm dụng.
5. Kiểm tra log/audit để phát hiện client authentication bất thường, token issuance và API access.
6. Xem xét revoke refresh token/grant và access token liên quan nếu có dấu hiệu bị lạm dụng.
7. Xóa/rotate bản sao trong CI, repo, artifact, image, backup và hệ thống lưu trữ theo quy trình.
8. Theo dõi sau incident và ghi lại bằng chứng.

Không chờ hết chu kỳ overlap thông thường nếu credential đang bị kẻ tấn công sử dụng. Overlap trong tình huống khẩn cấp chỉ tồn tại nếu cần thiết để chuyển dịch nhanh và được incident commander chấp thuận.

## 9. Tác động tới access token và refresh token

Xoay vòng client secret chủ yếu thay credential dùng để xác thực OAuth client. Nó không mặc nhiên:

- Thay chữ ký của JWT access token đã phát hành.
- Thu hồi mọi access token cũ.
- Thu hồi mọi refresh token của user.
- Xóa session OIDC của người dùng.
- Đổi audience hoặc scope của token đang tồn tại.

Nếu nghi client credential bị lộ và có khả năng kẻ tấn công đã xin token:

1. Thu hồi client credential bị lộ.
2. Kiểm tra audit của token endpoint để xác định token đã được cấp bất thường.
3. Revoke refresh token/grant hoặc client authorization liên quan theo khả năng của authorization server.
4. Đánh giá access token đã phát hành: opaque introspection, denylist, token lifetime ngắn hoặc cơ chế grant/session state.
5. Theo dõi resource server và điều tra request đáng ngờ.

JWT được xác minh offline có thể còn được chấp nhận tới exp nếu không có cơ chế thu hồi bổ sung. Vì vậy, không báo cáo “đã revoke secret nên mọi token lập tức vô hiệu” nếu chưa kiểm chứng từng lớp.

## 10. Ví dụ cấu hình an toàn trong ứng dụng

### 10.1. Lấy secret từ secret manager

Không hardcode credential trong source:

~~~yaml
security:
  oauth2:
    client:
      registration:
        inventory-worker:
          client-id: orders-inventory-worker
          client-secret: "<injected-secret-reference>"
          authorization-grant-type: client_credentials
~~~

Giá trị ở đây là placeholder minh họa. Trong production, nên ưu tiên secret manager hoặc workload identity để lấy credential ngắn hạn; bảo đảm environment, process dump và diagnostic endpoint không làm lộ giá trị.

### 10.2. Reload secret theo version

Pseudocode:

~~~java
public final class OAuthClientCredentialProvider {
    private final SecretManager secretManager;
    private final AtomicReference<ClientCredential> current =
        new AtomicReference<>();

    public void reload(String secretReference, String version) {
        char[] secret = secretManager.read(secretReference, version);
        ClientCredential candidate =
            ClientCredential.fromSecret(secret, version);

        // Kiểm tra cấu trúc và thực hiện một token request an toàn trước
        // khi chuyển reference đang hoạt động.
        verifyClientAuthentication(candidate);
        current.set(candidate);
        candidate.clearTemporaryCopies();
    }

    public ClientCredential current() {
        return current.get();
    }
}
~~~

Đây là pseudocode minh họa, không phải implementation production. String trong Java không thể xóa nội dung bất biến khỏi memory; char[] cũng chỉ giảm thời gian tồn tại nếu mọi bản sao được quản lý đúng. Nên dùng SDK secret manager/KMS, tránh copy credential không cần thiết và không expose nó qua toString(), debugger, heap dump hoặc exception.

Trong hệ thống thật, cần thiết kế atomic switch và lifecycle của client connection pool. Không thay credential trong một object đang được nhiều thread dùng mà không có cơ chế thread-safe; không để token request đang chạy bị đóng giữa chừng. Xác minh credential mới trước khi chuyển active reference.

### 10.3. Không log secret hoặc assertion

Ví dụ logger an toàn:

~~~java
log.info(
    "OAuth client credential reloaded: clientId={}, version={}, status={}",
    clientId,
    credentialVersion,
    "VERIFIED"
);
~~~

Không log:

~~~java
// SAI: không ghi credential hoặc token vào log.
log.info("Using client secret {}", clientSecret);
log.debug("Client assertion {}", signedClientAssertion);
log.debug("Token response {}", tokenResponse);
~~~

Không chỉ logger ứng dụng cần scrub. HTTP wire logging, reverse proxy, APM, tracing, exception handler, CI output và secret-manager audit cũng cần được cấu hình phù hợp.

## 11. Audit và giám sát rotation

Một rotation có thể kiểm toán nên tạo các event có cấu trúc:

| Event | Trường metadata nên có |
| --- | --- |
| client_credential.created | Client ID, credential version/reference, loại credential, actor/operator, thời điểm. |
| client_credential.registered | Authorization server/client registration, key ID/certificate fingerprint nếu phù hợp, policy version. |
| client_credential.deployed | Workload ID, environment, deployment version, secret version reference. |
| client_authentication.succeeded | Client ID, auth method, credential/key identifier nếu server cung cấp, timestamp, correlation ID. |
| client_authentication.failed | Client ID, reason code, source workload, timestamp; không ghi credential. |
| client_credential.revoked | Credential version/reference, actor, thời điểm và kết quả. |
| client_credential.rotation.completed | Change ID, consumer coverage, verification result và approver. |

Không log raw secret, private key, client assertion, access token, refresh token hoặc Authorization header. Với private key, lưu fingerprint/key ID thay vì nội dung key. Với certificate, có thể lưu serial/fingerprint và issuer theo policy.

### 11.1. Metrics và cảnh báo

Theo dõi:

- Số lần client authentication thành công/thất bại theo client ID và auth method.
- Tỷ lệ invalid_client trong rollout.
- Số workload còn tham chiếu secret version cũ.
- Tuổi credential và thời gian còn lại trước expiry.
- Thời điểm xác thực thành công cuối cùng bằng credential version mới.
- Số lần credential cũ bị thử sử dụng sau khi revoke.
- Tình trạng propagation của client registration/JWKS/trust store.

Không đưa secret, token hoặc dữ liệu cá nhân vào metric label. Dùng client ID, workload ID và version reference đã được chuẩn hóa.

## 12. Test matrix cho client secret rotation

| ID | Tình huống | Kiểm tra | Kết quả mong đợi |
| --- | --- | --- | --- |
| ROT-001 | Credential mới được tạo | Secret manager có version mới, quyền đọc đúng | Chỉ workload được phép mới đọc được version mới. |
| ROT-002 | Credential mới đăng ký | Client authentication với secret mới | Authorization server chấp nhận theo cấu hình. |
| ROT-003 | Credential cũ còn overlap | Xác thực bằng secret cũ trước cutover | Thành công trong khoảng overlap được phê duyệt. |
| ROT-004 | Canary dùng secret mới | Một instance thực hiện token request | Thành công; access token đúng scope/audience. |
| ROT-005 | Rolling deployment | Cập nhật mọi replica | Không có instance chạy version cũ sau khi hoàn tất. |
| ROT-006 | Worker ít chạy | Kích hoạt job/scheduler test | Worker đọc version mới và xác thực thành công. |
| ROT-007 | Thu hồi credential cũ | Disable/revoke secret cũ | Authorization server không chấp nhận secret cũ. |
| ROT-008 | Negative test sau revoke | Thử client authentication bằng secret cũ | Bị từ chối; không phát hành access token. |
| ROT-009 | Secret mới vẫn hoạt động | Token request sau khi secret cũ bị revoke | Thành công; service vẫn healthy. |
| ROT-010 | Sai client ID | Dùng secret mới với client registration khác | Bị từ chối. |
| ROT-011 | Sai secret | Một ký tự credential bị thay đổi | invalid_client hoặc lỗi theo contract; không có token. |
| ROT-012 | Secret manager unavailable | Workload không lấy được version mới | Không log secret cũ; hành vi fail-safe theo policy và cảnh báo. |
| ROT-013 | Secret version stale | Instance đọc version cũ từ cache | Phát hiện qua version/metrics; không báo rotation hoàn tất. |
| ROT-014 | Authorization server multi-node | Đăng ký/revoke qua node khác nhau | Tất cả node áp dụng trạng thái trong propagation SLO. |
| ROT-015 | Rollback trong overlap | Credential mới lỗi trước khi revoke cũ | Workload quay lại version cũ hợp lệ; change được đánh dấu rollback. |
| ROT-016 | Rollback sau revoke | Secret cũ đã disable | Không giả định secret cũ còn dùng được; phải có credential thay thế mới. |
| ROT-017 | Scope/audience regression | Token mới được cấp sau rotation | Không rộng hơn policy trước rotation nếu không có change riêng. |
| ROT-018 | Private key rollover | Public JWK mới được đăng ký, client ký bằng key mới | Assertion hợp lệ với kid mới; key cũ được gỡ sau overlap. |
| ROT-019 | mTLS certificate rollover | Client certificate mới được trust | TLS/client auth và token binding hoạt động theo policy. |
| ROT-020 | Log hygiene | Kiểm app log, proxy, APM, CI artifact | Không có secret, private key, assertion hoặc token raw. |
| ROT-021 | Credential cũ bị thử lại | Sau revoke có request dùng credential cũ | Bị từ chối và tạo audit/alert phù hợp. |
| ROT-022 | Autoscaling | Instance mới khởi tạo sau rotation | Instance đọc version hiện hành, không dùng secret bake trong image. |
| ROT-023 | Multi-region | Consumer ở region dự phòng chuyển sang secret mới | Không có region giữ credential cũ ngoài overlap. |
| ROT-024 | Scheduled job chưa chạy | Kiểm tra cấu hình và trigger test an toàn | Không còn reference tới version cũ; không bỏ sót consumer theo lịch. |

## 13. Các lỗi vận hành thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Thu hồi secret cũ trước khi rollout xong | Nhiều replica đồng loạt lỗi invalid_client | Dùng overlap và xác nhận consumer coverage trước khi revoke. |
| Chỉ cập nhật deployment chính | Cron/worker/region phụ vẫn dùng secret cũ | Inventory toàn bộ consumer, không chỉ web pods. |
| Cho rằng xóa secret khỏi vault là đã revoke | Authorization server vẫn có thể chấp nhận credential cũ | Disable/revoke tại nơi xác thực client. |
| Dùng cùng secret cho nhiều client | Lộ một nơi ảnh hưởng nhiều hệ thống | Tách credential theo workload/environment. |
| Copy secret vào image | Image cũ vẫn chứa credential và có thể bị kéo xuống | Lấy secret runtime, rebuild/retire artifact cũ theo policy. |
| Không có rollback plan | Rotation lỗi gây downtime kéo dài | Xác định overlap, rollback và thời điểm không thể rollback. |
| Rollback về secret bị lộ | Kẻ tấn công tiếp tục xác thực | Incident rotation phải revoke credential bị lộ, không khôi phục nó. |
| Không kiểm tra scope/audience | Rotation vô tình tạo client quyền rộng hơn | So sánh policy trước/sau và test token claims. |
| Log client assertion/token response | Credential và token bị rò qua log | Scrub ở app, HTTP client, proxy và APM. |
| Không quan sát node cũ | Secret cũ tiếp tục được dùng âm thầm | Version telemetry và negative test sau revoke. |
| Xoay key nhưng quên public JWKS cũ/mới | Client assertion lỗi xác minh | Overlap public key và rollout theo kid. |
| Xoay certificate nhưng quên trust store | TLS handshake hoặc token binding lỗi | Kiểm tra CA chain và certificate binding từng chặng. |

## 14. Checklist runbook trước, trong và sau rotation

### Trước rotation

- [ ] Xác định client ID, credential type, owner, environment và mọi consumer.
- [ ] Kiểm tra scope, audience, grant type và auth method hiện tại.
- [ ] Xác minh authorization server có hỗ trợ overlap hay cần client registration staged.
- [ ] Xác định thời hạn credential, lịch job và propagation delay.
- [ ] Chuẩn bị secret version mới, change ID, rollback plan và người chịu trách nhiệm.
- [ ] Kiểm tra không dùng credential production trong môi trường test.

### Trong rotation

- [ ] Tạo credential mới trong kênh tin cậy.
- [ ] Đăng ký credential mới mà không mở rộng quyền.
- [ ] Lưu credential vào secret manager và giới hạn quyền truy cập.
- [ ] Rollout canary rồi rolling update các consumer.
- [ ] Xác minh token request và health check bằng credential mới.
- [ ] Theo dõi invalid_client, replica còn cũ và job chưa chạy.
- [ ] Giữ credential cũ active chỉ trong khoảng overlap đã phê duyệt.

### Sau rotation

- [ ] Xác nhận tất cả consumer đã dùng version mới.
- [ ] Revoke/disable credential cũ tại authorization server hoặc PKI.
- [ ] Kiểm thử credential cũ bị từ chối và credential mới vẫn hoạt động.
- [ ] Kiểm tra scope/audience của token không bị thay đổi ngoài kế hoạch.
- [ ] Kiểm tra log/trace/CI artifact không chứa credential.
- [ ] Cập nhật inventory, expiry, owner, audit evidence và change record.
- [ ] Đặt cảnh báo cho lần rotation tiếp theo và xử lý bản sao credential cũ theo retention policy.

## 15. Kết luận và tài liệu tham khảo

Xoay vòng client secret là một quy trình có kiểm soát qua cả authorization server, secret manager, ứng dụng và mọi workload phụ thuộc. Cách làm phổ biến để giảm downtime là tạo credential mới, cho phép overlap, rollout từng nhóm, xác minh toàn bộ consumer rồi mới revoke credential cũ. Nếu hệ thống không hỗ trợ nhiều credential active, cần một chiến lược staged registration hoặc maintenance window; không giả định mọi OAuth provider có cùng khả năng.

Phải phân biệt client credential với access token và refresh token. Đổi client secret không tự thu hồi token đã phát hành; khi có incident lộ credential, cần điều tra token issuance và đánh giá việc revoke grant/access token liên quan. Rotation chỉ hoàn tất khi credential cũ bị vô hiệu hóa ở nơi xác thực, mọi consumer dùng credential mới và có bằng chứng kiểm thử.

Tài liệu tiêu chuẩn liên quan:

- **RFC 6749 — OAuth 2.0 Authorization Framework:** client authentication, token endpoint và grant.
- **RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol:** đăng ký metadata của OAuth client, tùy hệ thống hỗ trợ.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi access token/refresh token; phân biệt với việc disable client credential.
- **RFC 7523 — JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants:** client assertion và private_key_jwt.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** mTLS client authentication và certificate-bound token.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** khuyến nghị bảo vệ credential và token trong triển khai OAuth.
- **OWASP Secrets Management Cheat Sheet:** inventory, phân quyền, rotation, audit và quản lý vòng đời secret.
