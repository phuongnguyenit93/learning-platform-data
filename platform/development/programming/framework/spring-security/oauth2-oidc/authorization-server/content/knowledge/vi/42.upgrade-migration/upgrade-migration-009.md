# Triển khai theo giai đoạn, theo dõi sự cố và lập phương án rollback

Nâng cấp Spring Authorization Server là thay đổi ở một thành phần bảo mật trung tâm. Một phiên bản mới có thể thay đổi cách xác thực client, phát hành token, xử lý authorization code, đọc consent, công bố JWKS hoặc tương tác với database. Nếu triển khai đồng loạt mà không kiểm tra tương thích, lỗi có thể ảnh hưởng đến đăng nhập, cấp token và xác minh token của nhiều ứng dụng cùng lúc.

Triển khai theo giai đoạn giúp giới hạn phạm vi ảnh hưởng, phát hiện lỗi bằng tín hiệu vận hành và chỉ mở rộng khi phiên bản mới hoạt động ổn định. Phương án rollback cần được chuẩn bị trước, bao gồm code, schema, cấu hình, khóa ký và trạng thái OAuth/OIDC đã phát sinh trong thời gian rollout.

Bài học này hướng dẫn cách lập kế hoạch nâng cấp, triển khai canary hoặc blue-green, theo dõi sự cố và quay lại phiên bản ổn định cho một hệ thống Spring Authorization Server đang vận hành.

## 1. Xác định phạm vi thay đổi trước khi triển khai

Không phải mọi thay đổi đều có cùng mức độ rủi ro hoặc cùng cách rollback. Trước khi chọn chiến lược rollout, hãy phân loại thay đổi và xác định những thành phần có thể bị ảnh hưởng.

| Nhóm thay đổi | Ví dụ | Rủi ro cần đánh giá |
|---|---|---|
| Ứng dụng | Nâng Spring Boot, Spring Security hoặc Spring Authorization Server | API thay đổi, filter chain, converter hoặc token behavior khác |
| Database | Thêm cột, bảng, index hoặc thay đổi cách lưu authorization | Phiên bản cũ và mới có thể đọc/ghi không tương thích |
| Client registration | Thay metadata, auth method, redirect URI hoặc policy | Client hiện tại không thể xác thực hoặc đổi code lấy token |
| Token | Thay claim, audience, TTL, format hoặc customizer | Resource Server và client không xử lý được token mới |
| Khóa ký | Xoay signing key, thay thuật toán hoặc KMS | JWT cũ không còn xác minh được nếu public key bị gỡ sớm |
| Issuer và endpoint | Thay domain, issuer hoặc proxy route | Client từ chối token do issuer không khớp; discovery không nhất quán |
| Session và authorization state | Thay session store, serialization hoặc repository | Người dùng mất phiên; authorization code, consent hoặc PAR request bị mất |
| Hạ tầng | Thay ingress, TLS, DNS, service mesh hoặc network policy | Endpoint không truy cập được, mTLS hoặc forwarded header sai |

Tạo danh sách cụ thể về các luồng bị ảnh hưởng. Với Authorization Server, ít nhất cần xét:

- OIDC Discovery và JWKS.
- Authorization Code Flow, bao gồm PKCE.
- Token endpoint và refresh token.
- Client authentication tại token/PAR endpoint.
- UserInfo và consent.
- Revocation và introspection nếu được triển khai.
- Dynamic Client Registration và Pushed Authorization Requests nếu được bật.
- Session đăng nhập và kho authorization dùng chung.
- Các resource server đang xác minh JWT do Authorization Server phát hành.

Nếu thay đổi chỉ tác động đến một phần luồng, canary cần tập trung vào đúng phần đó. Nếu thay đổi issuer, khóa ký hoặc schema authorization, phạm vi kiểm tra phải rộng hơn vì nhiều client và resource server có thể bị ảnh hưởng.

## 2. Chuẩn bị trước khi rollout

### 2.1. Chốt phiên bản và điều kiện tương thích

Ghi nhận các phiên bản đang chạy và phiên bản dự kiến:

- Java runtime.
- Spring Boot.
- Spring Security.
- Spring Authorization Server.
- JDBC driver, database và migration tool.
- Redis/Spring Session nếu có.
- Thư viện JWT/JWK và thư viện tích hợp KMS.
- Container base image và Kubernetes version nếu thay đổi có liên quan.

Đọc release notes và migration guide của các phiên bản liên quan. Kiểm tra API đã deprecated hoặc bị loại bỏ, thay đổi default behavior, security chain, token settings, endpoint settings và cách serialize dữ liệu.

Không nâng nhiều lớp nền tảng cùng lúc nếu chưa có lý do rõ ràng. Ví dụ, nâng Java, Spring Boot, Spring Security, database và token schema trong cùng một lần sẽ làm khó việc xác định nguyên nhân khi rollout lỗi. Chia thay đổi thành các bước có thể kiểm chứng độc lập nếu điều kiện triển khai cho phép.

### 2.2. Tạo baseline từ phiên bản hiện tại

Trước khi phát hành, thu thập dữ liệu nền để biết hệ thống bình thường đang hoạt động như thế nào.

Các chỉ số nên có:

- Tỷ lệ request thành công và HTTP 5xx theo endpoint.
- Tỷ lệ lỗi OAuth như invalid_client, invalid_grant, invalid_scope, invalid_request và lỗi token.
- Độ trễ p50, p95, p99 của /oauth2/authorize, /oauth2/token, UserInfo, PAR và discovery.
- Tỷ lệ token issuance, refresh và revoke.
- Kết nối database, connection pool, transaction timeout và deadlock.
- Session store, cache hit/miss và lỗi đọc/ghi.
- Số pod ready, restart, CPU, memory và thời gian khởi động.
- Lỗi xác minh JWT tại các resource server, nếu có telemetry từ phía đó.

Phân biệt lỗi vốn đã tồn tại với lỗi mới phát sinh. Nếu baseline chưa được ghi nhận, rất khó kết luận phiên bản mới làm tỷ lệ lỗi tăng hay chỉ đang gặp một sự cố sẵn có.

### 2.3. Xác định người chịu trách nhiệm và đường liên lạc

Một lần triển khai Authorization Server thường liên quan đến đội ứng dụng, nền tảng, bảo mật, database và chủ sở hữu các client quan trọng. Trước khi bắt đầu, xác định:

- Người điều phối rollout và người có quyền quyết định dừng.
- Người theo dõi dashboard và log.
- Người quản lý database migration.
- Người phụ trách signing key/KMS.
- Người liên hệ các resource server hoặc client có thể cần phối hợp.
- Kênh thông báo sự cố và cách cập nhật trạng thái triển khai.

Chuẩn bị sẵn link dashboard, log query, deployment revision, image digest, commit SHA, migration version và runbook. Không để người trực sự cố phải tìm các thông tin này khi hệ thống đang lỗi.

### 2.4. Chuẩn bị artifact và điểm quay lại

Trước khi rollout, lưu lại:

- Image digest của phiên bản đang ổn định.
- Image digest và commit của phiên bản mới.
- Cấu hình triển khai đang chạy.
- Cấu hình mới đã được review.
- Database migration version hiện tại.
- Bản sao lưu hoặc snapshot theo chính sách database.
- Phiên bản secret reference, certificate và key ID đang dùng.
- Danh sách feature flag hoặc cấu hình có thể bật/tắt.

Ưu tiên định danh image bằng digest để tránh tag bị thay đổi sau khi triển khai. Xác nhận image cũ còn được lưu trong registry và có thể pull khi cần rollback.

Snapshot database là một lớp bảo vệ bổ sung. Nó không thay thế thiết kế migration tương thích ngược, vì khôi phục snapshot có thể làm mất các authorization, refresh token, consent hoặc client registration phát sinh sau thời điểm snapshot.

## 3. Thiết kế triển khai theo giai đoạn

Triển khai theo giai đoạn nghĩa là giới hạn lượng traffic hoặc số instance sử dụng phiên bản mới, quan sát kết quả, rồi mới mở rộng.

Một trình tự tham khảo:

~~~mermaid
flowchart TD
    A[Chuẩn bị artifact và baseline] --> B[Kiểm tra staging]
    B --> C[Triển khai một replica hoặc nhóm canary]
    C --> D{Health và luồng OAuth/OIDC đạt?}
    D -- Không --> E[Dừng rollout và phân loại sự cố]
    E --> F{Có thể rollback an toàn?}
    F -- Có --> G[Quay lại phiên bản ổn định]
    F -- Không --> H[Giữ traffic ở mức an toàn và sửa tiến]
    D -- Có --> I[Mở rộng canary]
    I --> J[Theo dõi các cửa sổ ổn định]
    J --> K{Chỉ số và nghiệp vụ ổn định?}
    K -- Không --> E
    K -- Có --> L[Rollout toàn bộ]
    L --> M[Theo dõi sau triển khai]
    M --> N[Đóng rollout và ghi nhận kết quả]
~~~

Các giai đoạn nên có điều kiện đi tiếp và điều kiện dừng cụ thể. Không dùng tiêu chí chung như “pod xanh” để quyết định mở rộng, vì readiness chỉ phản ánh khả năng nhận traffic tại thời điểm kiểm tra; nó không chứng minh luồng cấp token và tương thích client đều hoạt động.

### 3.1. Giai đoạn 0: kiểm thử staging

Staging nên gần production về phiên bản database, loại repository, session store, signing key integration, ingress và cấu hình TLS. Dùng key và credential riêng của staging.

Thực hiện tối thiểu:

1. Khởi động phiên bản mới với schema đã migrate.
2. Kiểm tra health, readiness và startup.
3. Đọc OIDC Discovery và JWKS.
4. Chạy authorization code flow với PKCE.
5. Đổi authorization code lấy token.
6. Dùng refresh token và kiểm tra rotation/reuse policy nếu bật.
7. Gọi UserInfo và xác minh claim sub.
8. Kiểm tra client authentication.
9. Kiểm tra revoke/introspection nếu hệ thống hỗ trợ.
10. Thử graceful shutdown và restart.
11. Thử rollback ứng dụng về phiên bản trước trên schema mới.
12. Kiểm tra resource server vẫn xác minh được token được phát hành trước và sau nâng cấp.

Một lần staging thành công không bảo đảm production sẽ thành công, nhưng nó giúp loại các lỗi cấu hình và tương thích có thể tái hiện.

### 3.2. Giai đoạn 1: triển khai canary

Canary đưa một phần nhỏ instance hoặc traffic sang phiên bản mới. Với hệ thống nhiều replica, có thể tạo một nhóm pod mới, một deployment riêng hoặc dùng cơ chế phân luồng của ingress/service mesh.

Canary cần được giới hạn theo một hoặc nhiều tiêu chí:

- Một replica mới trong cụm.
- Một tỷ lệ traffic nhỏ.
- Một nhóm client nội bộ hoặc client kiểm thử.
- Một khu vực hoặc tenant được chọn.
- Một tập endpoint ít rủi ro trước khi mở các luồng cấp token quan trọng.

Với Authorization Server, chỉ chia tỷ lệ traffic ngẫu nhiên có thể chưa đủ. Một authorization flow thường gồm nhiều request liên tiếp: authorize, login, consent, token. Nếu các request bị phân tán giữa phiên bản cũ và mới, cả hai phiên bản phải tương thích với session và authorization state chung.

Nếu chưa bảo đảm được điều đó, hãy bắt đầu bằng một nhóm client thử nghiệm có thể định tuyến ổn định, hoặc triển khai canary nhưng chưa chuyển luồng người dùng thật. Tránh để một authorization code được tạo ở phiên bản mới nhưng token endpoint của phiên bản cũ không thể đọc trạng thái tương ứng.

### 3.3. Giai đoạn 2: mở rộng theo các nấc

Sau khi canary ổn định, tăng dần lượng traffic hoặc số replica. Mỗi nấc cần có thời gian quan sát đủ dài để bao phủ chu kỳ sử dụng thực tế.

Ví dụ kế hoạch có thể dùng các mức 1 replica, 5%, 20%, 50%, rồi 100%. Đây chỉ là ví dụ; số lượng và tỷ lệ phù hợp phụ thuộc vào lưu lượng, số replica, khả năng phân luồng và mức độ rủi ro.

Ở mỗi nấc:

- Kiểm tra health và readiness.
- So sánh error rate với baseline.
- Kiểm tra latency và saturation.
- Chạy synthetic authorization flow.
- Kiểm tra log OAuth error.
- Kiểm tra kết nối database, cache, session store và KMS.
- Xác nhận các resource server tiếp tục xác minh token.
- Ghi nhận quyết định tiếp tục, giữ nguyên hoặc rollback.

Không tăng traffic chỉ vì đã hết thời gian chờ. Chỉ mở rộng khi dữ liệu quan sát đáp ứng điều kiện đã thống nhất.

### 3.4. Giai đoạn 3: hoàn tất và giữ thời gian quan sát

Sau khi toàn bộ instance đã lên phiên bản mới:

- Xác nhận tất cả pod ready và không còn replica cũ.
- Kiểm tra deployment revision và image digest.
- Kiểm tra migration version.
- Chạy lại các luồng OAuth/OIDC quan trọng.
- Theo dõi trong một cửa sổ sau triển khai đủ dài.
- Giữ artifact, log, metric và cấu hình của cả hai phiên bản cho đến khi hết thời gian rollback đã định.
- Chỉ xóa tài nguyên cũ sau khi không còn phụ thuộc và đã có quyết định đóng rollout.

Không xóa signing key cũ, session compatibility hoặc schema cũ ngay sau khi pod cuối cùng được thay thế. Một số dữ liệu được tạo trước rollout vẫn còn hiệu lực sau đó.

## 4. Chọn chiến lược Rolling, Canary hay Blue-Green

| Chiến lược | Cách hoạt động | Ưu điểm | Rủi ro và điều kiện |
|---|---|---|---|
| Rolling update | Thay từng nhóm instance trong cùng deployment | Dễ vận hành, tận dụng cơ chế orchestration | Hai phiên bản cùng chạy; cần schema và state tương thích |
| Canary | Chuyển một phần traffic sang phiên bản mới | Giới hạn phạm vi ảnh hưởng, so sánh trực tiếp | Cần phân luồng và telemetry theo version/client |
| Blue-green | Chạy hai môi trường riêng, chuyển traffic qua switch | Có điểm chuyển rõ ràng, quay lại nhanh ở tầng routing | Tốn tài nguyên; state/database/keys vẫn dùng chung hoặc phải đồng bộ |
| Shadow traffic | Sao chép request để đánh giá phiên bản mới mà không dùng response cho người dùng | Có thể kiểm tra behavior và tải | Không được phát hành side effect hoặc ghi dữ liệu nghiệp vụ ngoài ý muốn |

### 4.1. Rolling update

Kubernetes Deployment có thể cấu hình chiến lược RollingUpdate:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: authorization-server
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  minReadySeconds: 15
  progressDeadlineSeconds: 600
~~~

maxSurge giới hạn số pod được tạo vượt quá số replica mong muốn trong quá trình cập nhật. maxUnavailable giới hạn số replica có thể unavailable. Cấu hình maxUnavailable bằng 0 yêu cầu duy trì số replica sẵn sàng theo mong muốn trong rollout, đồng thời cần đủ tài nguyên để tạo pod mới.

Các thông số này không thay thế readiness probe. Nếu readiness luôn trả thành công dù database hoặc signing key chưa sẵn sàng, Kubernetes vẫn có thể đưa pod mới vào Service quá sớm.

### 4.2. Canary

Canary phù hợp khi cần quan sát một nhóm nhỏ client hoặc traffic thật. Hãy gắn nhãn phiên bản vào metric và log để so sánh.

Ví dụ các chiều phân tích:

- service.version.
- deployment.environment.
- oauth.client_id ở dạng an toàn theo chính sách log.
- Endpoint hoặc grant type.
- Khu vực/tenant nếu được phép.
- Kết quả thành công/thất bại và loại OAuth error.

Không gắn access token, refresh token, authorization code hoặc client secret vào metric label. Tránh dùng client ID có cardinality quá cao làm label nếu hệ thống có hàng chục nghìn client; có thể nhóm theo client class hoặc allowlist client quan trọng.

### 4.3. Blue-green

Blue-green tạo hai môi trường ứng dụng, ví dụ blue là phiên bản hiện tại và green là phiên bản mới. Sau khi green vượt qua kiểm thử, load balancer chuyển traffic sang green. Nếu có sự cố, traffic có thể quay lại blue.

Đối với Authorization Server, chuyển traffic nhanh không tự động làm dữ liệu tương thích. Cả blue và green cần hiểu cùng:

- Database schema trong giai đoạn chuyển tiếp.
- Authorization code và refresh token đã tồn tại.
- Session được tạo từ môi trường còn lại.
- Client registration và consent.
- PAR request nếu đang có request chưa hết hạn.
- Signing key và JWKS.
- Issuer và public endpoint.

Nếu green phát hành token với định dạng mà blue không xác minh được, chuyển traffic về blue có thể khiến client và resource server lỗi. Hãy thiết kế token và key rotation để cả hai phiên bản cùng xác minh được trong cửa sổ rollback.

## 5. Giữ tương thích dữ liệu trong quá trình nâng cấp

### 5.1. Database migration theo expand-contract

Trong rolling/canary, phiên bản cũ và mới có thể cùng đọc/ghi database. Vì vậy migration cần tương thích với cả hai.

Quy trình expand-contract:

1. **Expand:** thêm cấu trúc mới mà phiên bản cũ vẫn có thể bỏ qua.
2. **Deploy tương thích:** phát hành phiên bản có thể đọc schema cũ và mới.
3. **Backfill:** chuyển dữ liệu theo lô, có checkpoint và khả năng tiếp tục.
4. **Switch:** chuyển ứng dụng sang sử dụng trường/cấu trúc mới.
5. **Contract:** chỉ xóa cấu trúc cũ sau khi không còn phiên bản hoặc consumer nào phụ thuộc.

Ví dụ:

- Release A thêm cột subject_key nullable, nhưng vẫn đọc user_id.
- Release B ghi cả user_id và subject_key, đồng thời có thể đọc cả hai.
- Job backfill điền subject_key cho dữ liệu cũ.
- Release C đọc subject_key làm nguồn chính nhưng vẫn giữ fallback trong cửa sổ tương thích.
- Release D mới xóa user_id nếu đã xác minh không còn consumer cần nó.

Đây là ví dụ khái niệm. Với schema authorization của Spring Authorization Server, phải kiểm tra SQL schema và converter thực tế trước khi thay đổi. Không tự thêm hoặc xóa cột trong bảng framework khi chưa hiểu cách serializer/repository sử dụng.

### 5.2. Không chạy migration phá hủy trong lúc pod khởi động

Nếu mỗi replica tự chạy migration có thể làm nhiều pod tranh chấp lock hoặc thay đổi schema trong khi phiên bản cũ vẫn đang phục vụ request.

Ưu tiên một bước migration được kiểm soát:

- Chạy migration job riêng trước rollout ứng dụng.
- Có lock để tránh nhiều job thực hiện đồng thời.
- Ghi nhận migration version.
- Kiểm tra kết quả và thời gian thực thi.
- Dừng rollout nếu migration thất bại hoặc vượt ngưỡng thời gian.

Migration expand thường có thể chạy trước khi triển khai code mới. Migration contract nên chạy ở release sau, khi phiên bản cũ đã được loại bỏ và cửa sổ rollback đã kết thúc.

### 5.3. Giữ authorization state tương thích

Authorization Server lưu các trạng thái có vòng đời riêng:

- Authorization code.
- Access token và refresh token.
- Consent.
- Authorization metadata và attributes.
- PAR request.
- Session đăng nhập nếu dùng Spring Session.

Nếu nâng cấp làm thay đổi cách serialize hoặc đọc các attributes, phiên bản cũ có thể không đọc được dữ liệu do phiên bản mới ghi. Hãy kiểm tra tương thích hai chiều trong giai đoạn hỗn hợp:

- Phiên bản cũ đọc được dữ liệu do phiên bản mới tạo.
- Phiên bản mới đọc được dữ liệu do phiên bản cũ tạo.
- Refresh token cũ vẫn có thể được xử lý theo policy.
- Authorization code đang còn hiệu lực không bị mất.
- Consent không bị reset ngoài ý muốn.
- PAR request còn hạn vẫn được giải quyết.
- Session serialization không làm người dùng bị đăng xuất hàng loạt.

Nếu không thể bảo đảm hai chiều, cần hạn chế việc trộn phiên bản hoặc thiết kế một giai đoạn chuyển tiếp để ngừng tạo loại state cũ trước khi rollout.

## 6. Giữ token và signing key có thể xác minh khi rollback

### 6.1. Không gỡ public key quá sớm

Khi xoay signing key, token được ký bằng khóa cũ vẫn có thể còn hiệu lực. Nếu gỡ public key cũ khỏi JWKS ngay sau khi bắt đầu ký bằng khóa mới, resource server có thể không xác minh được token cũ.

Quy trình an toàn thường gồm:

1. Tạo key mới với kid duy nhất.
2. Công bố public key mới trong JWKS.
3. Chờ các resource server có thời gian tải/cập nhật JWKS.
4. Chuyển hoạt động ký sang key mới.
5. Tiếp tục giữ public key cũ trong JWKS ít nhất đến khi token ký bằng key cũ hết hạn, cộng clock skew và cache duration.
6. Chỉ gỡ key cũ khi không còn token hợp lệ cần key đó.

Khi rollback code, phiên bản cũ cũng phải biết cách xác minh token được ký bằng key mới nếu những token đó vẫn có thể xuất hiện trong hệ thống. Giữ key material và verifier tương thích trong thời gian rollback là điều kiện quan trọng.

### 6.2. Không đổi issuer cùng lúc với nâng cấp code nếu không cần

Issuer là định danh của Authorization Server. Thay issuer có thể làm client từ chối ID Token và resource server từ chối access token. Nếu bắt buộc thay domain/issuer, coi đây là một migration riêng có kế hoạch cho discovery, client configuration, token validation và thời gian chuyển tiếp.

Trong một đợt nâng cấp ứng dụng thông thường, giữ issuer ổn định giúp giảm số biến thay đổi và đơn giản hóa rollback.

### 6.3. Token claims và format phải tương thích

Nếu phiên bản mới đổi claim custom, audience, thời hạn, token format hoặc thuật toán ký, hãy kiểm tra các resource server đang xác minh token.

Ví dụ, nếu token mới bổ sung claim tenant_id, resource server cũ nên bỏ qua claim lạ nếu thiết kế cho phép. Nếu token mới thay sub hoặc iss, đó là thay đổi có ảnh hưởng lớn hơn và cần migration phối hợp.

Nếu chuyển JWT sang opaque token hoặc ngược lại, không coi đây là một thay đổi deploy thông thường. Cần cập nhật resource server, introspection, cache và khả năng xác minh trước khi phát hành token theo định dạng mới.

## 7. Theo dõi sức khỏe và sự cố trong rollout

### 7.1. Kết hợp health check với metric nghiệp vụ

Health endpoint trả lời liệu instance có thể nhận traffic hay không. Nó không thay thế metric của các luồng OAuth/OIDC.

Theo dõi các nhóm sau:

| Nhóm | Metric/log cần quan sát | Dấu hiệu bất thường |
|---|---|---|
| Availability | Request count, HTTP 5xx, readiness, restart | Pod ready giảm hoặc 5xx tăng |
| Latency | p50/p95/p99 theo endpoint | Token hoặc authorize chậm hơn baseline |
| Authentication | invalid_client, lỗi assertion, mTLS handshake | Một phương thức auth lỗi tăng đột biến |
| Authorization | invalid_grant, redirect URI mismatch, consent failure | Authorization code hoặc refresh token bị từ chối bất thường |
| Token | Issuance, refresh, revoke, signature validation | Token issuance giảm hoặc resource server báo signature failure |
| Database | Pool usage, timeout, deadlock, query latency | Authorization persistence chậm hoặc lỗi |
| Session | Read/write errors, expired session, login success | Người dùng bị yêu cầu đăng nhập lại bất thường |
| JWK/KMS | Key lookup, signing latency, KMS error, JWKS fetch | Không ký được token hoặc verifier không tìm thấy kid |
| PAR/DCR | PAR success/failure, invalid_request_uri, registration errors | Client không thể bắt đầu authorization flow |
| Runtime | CPU, memory, GC, thread pool | Pod quá tải hoặc restart do OOM |

Phân loại metric theo endpoint, phiên bản ứng dụng và loại grant. Điều này giúp nhận biết phiên bản mới chỉ lỗi ở refresh token, private_key_jwt hoặc PAR thay vì toàn bộ hệ thống.

### 7.2. Thiết lập cảnh báo dựa trên baseline và SLO

Không dùng một ngưỡng cố định cho mọi hệ thống. Xác định SLO, baseline và ngưỡng vận hành trước rollout.

Một quy tắc cảnh báo nên có:

- Metric và phạm vi đo.
- Cửa sổ thời gian.
- Ngưỡng cảnh báo.
- Ngưỡng dừng rollout.
- Người nhận cảnh báo.
- Hành động dự kiến.

Ví dụ tiêu chí có thể cấu hình theo hệ thống:

- HTTP 5xx tăng vượt ngưỡng so với baseline trong nhiều cửa sổ liên tiếp.
- Tỷ lệ invalid_client tăng mạnh sau khi nâng client authentication.
- Tỷ lệ invalid_grant tăng sau thay đổi authorization repository hoặc refresh token.
- p95 của token endpoint vượt SLO.
- Pod mới liên tục restart hoặc readiness flapping.
- Resource server báo không xác minh được kid mới.
- Database pool cạn hoặc timeout tăng.
- Login success giảm trong khi số request authorize vẫn giữ ở mức bình thường.

Không tự động rollback chỉ dựa trên một metric đơn lẻ nếu metric đó có thể phản ánh dữ liệu đầu vào sai hoặc một client lỗi riêng. Kết hợp nhiều tín hiệu và phân tích phạm vi ảnh hưởng.

### 7.3. Phân biệt lỗi hệ thống và lỗi riêng của client

Một client gửi redirect URI sai hoặc secret hết hạn có thể tạo OAuth error nhưng không nhất thiết là sự cố toàn hệ thống.

Phân tích theo:

- Phiên bản server xử lý.
- Client class và auth method.
- Grant type.
- Endpoint.
- Loại error.
- Thời điểm bắt đầu rollout.
- Khu vực hoặc tenant.
- Tỷ lệ request thành công trên tổng request của cùng nhóm.

Nếu chỉ một client bị lỗi sau khi metadata thay đổi, liên hệ chủ sở hữu client và giữ rollout ở mức hiện tại cho đến khi hiểu nguyên nhân. Nếu nhiều client độc lập cùng lỗi tại token endpoint, khả năng cao là regression ở server hoặc dependency dùng chung.

### 7.4. Kiểm tra synthetic flow liên tục

Trong rollout, chạy các luồng tổng hợp bằng client và user test:

1. Lấy OIDC Discovery.
2. Kiểm tra JWKS có key hợp lệ.
3. Thực hiện Authorization Code Flow với PKCE.
4. Đổi code lấy token.
5. Xác minh ID Token và access token.
6. Gọi UserInfo.
7. Dùng refresh token theo policy.
8. Thử client authentication method quan trọng.
9. Kiểm tra revoke/introspection nếu có.

Synthetic flow nên dùng tài khoản, client và redirect URI dành riêng cho kiểm thử. Không dùng thông tin đăng nhập của người dùng thật.

## 8. Xác định điều kiện dừng rollout

Trước khi triển khai, viết rõ điều kiện continue, hold và rollback.

| Quyết định | Điều kiện tham khảo | Hành động |
|---|---|---|
| Continue | Health ổn định, metric trong SLO, synthetic flow thành công, không có regression đáng kể | Mở rộng traffic theo nấc kế tiếp |
| Hold | Có tín hiệu bất thường nhưng phạm vi hoặc nguyên nhân chưa rõ | Giữ tỷ lệ canary, thu thập log/trace và điều tra |
| Rollback | Lỗi nghiêm trọng, lan rộng, ảnh hưởng bảo mật hoặc không thể khắc phục trong cửa sổ cho phép | Ngừng rollout, chuyển traffic về phiên bản ổn định theo runbook |
| Forward fix | Rollback không an toàn do dữ liệu/key đã thay đổi hoặc migration không thể đảo ngược | Giữ traffic ở mức an toàn và phát hành bản sửa tương thích |

Các trường hợp cần dừng ngay để đánh giá:

- Không thể xác minh chữ ký token hợp lệ.
- Token được phát hành với issuer sai.
- Private key hoặc secret bị lộ.
- Client không thể đổi authorization code hoặc refresh token trên diện rộng.
- Authorization state bị mất hoặc ghi sai.
- Database migration làm hỏng dữ liệu hoặc phiên bản cũ không thể hoạt động.
- User session bị mất hàng loạt.
- Một lỗi cấu hình khiến endpoint bảo mật mở rộng quyền truy cập ngoài ý muốn.

Sự cố bảo mật có thể cần quy trình ứng phó riêng: dừng phát hành token, thu hồi credential/key theo kế hoạch và phối hợp resource server. Chuyển image về bản cũ không tự khắc phục một key đã bị lộ hoặc token đã được phát hành sai.

## 9. Lập phương án rollback trước khi triển khai

Rollback không chỉ là chạy lại image cũ. Cần trả lời trước các câu hỏi:

- Image cũ có còn trong registry và có thể khởi động với schema hiện tại không?
- Phiên bản cũ có đọc được authorization/session state do phiên bản mới ghi không?
- Phiên bản cũ có xác minh được token được ký bằng key mới không?
- Có thay đổi issuer, redirect URI hoặc endpoint công khai không?
- Có migration phá hủy hoặc chuyển đổi dữ liệu không?
- Có feature flag nào cần đưa về giá trị cũ?
- Có secret/certificate nào đã được xoay và phiên bản cũ có dùng được không?
- Có client nào đã được cập nhật metadata trong thời gian rollout không?

Nếu chưa trả lời được các câu hỏi này, phương án rollback chưa đủ cụ thể.

### 9.1. Phân biệt rollback code, config và data

| Loại rollback | Ví dụ | Điều cần lưu ý |
|---|---|---|
| Code | Chuyển deployment về image cũ | Image cũ phải tương thích schema và state hiện tại |
| Config | Đưa feature flag hoặc property về giá trị trước | Cần biết config nào đã thay đổi và thứ tự hoàn nguyên |
| Routing | Chuyển traffic từ green về blue | Hai môi trường phải cùng đọc được state và token |
| Database | Khôi phục schema/data | Restore có thể làm mất authorization/token/client registration mới |
| Key/certificate | Quay lại key hoặc certificate cũ | Không xóa key mới khi token mới vẫn còn hiệu lực |
| Client metadata | Khôi phục redirect URI/auth method | Cần tránh vô hiệu hóa client đang hoạt động hoặc secret đã được xoay |

Không mặc định database rollback là bước an toàn. Với migration expand, thường có thể giữ schema mới và rollback code nếu phiên bản cũ vẫn tương thích. Với migration contract hoặc dữ liệu đã biến đổi không thể đảo ngược, có thể cần forward fix hoặc phục hồi có kiểm soát thay vì restore toàn bộ database.

### 9.2. Runbook rollback tham khảo

Một runbook nên có các bước rõ ràng và người chịu trách nhiệm:

1. Dừng rollout hoặc dừng tăng tỷ lệ canary.
2. Ghi lại thời điểm, deployment revision, image digest và error correlation ID.
3. Xác định lỗi thuộc code, config, database, key hay hạ tầng.
4. Kiểm tra tính tương thích của phiên bản ổn định với schema và state hiện tại.
5. Chuyển traffic về phiên bản ổn định hoặc scale down canary theo chiến lược đã chọn.
6. Giữ signing key/JWKS cần thiết để xác minh token đã phát hành.
7. Khôi phục cấu hình hoặc feature flag đã thay đổi nếu cần.
8. Xác nhận readiness, discovery, JWKS và các luồng OAuth/OIDC.
9. Theo dõi error rate, latency và token issuance sau rollback.
10. Thông báo trạng thái và mở điều tra nguyên nhân gốc.

Ví dụ với Kubernetes:

~~~bash
kubectl rollout history deployment/authorization-server
kubectl rollout undo deployment/authorization-server
kubectl rollout status deployment/authorization-server
kubectl get pods -l app=authorization-server
~~~

Các lệnh trên chỉ thao tác với revision của Deployment. Chúng không tự hoàn nguyên database migration, secret, issuer, key rotation hoặc thay đổi client metadata. Runbook cần có các bước riêng cho từng loại thay đổi đã thực hiện.

Nếu dùng Helm hoặc GitOps, rollback nên thực hiện qua công cụ quản lý nguồn cấu hình đang dùng. Không sửa trực tiếp tài nguyên trong cluster nếu hệ thống sẽ lập tức reconcile ngược về trạng thái Git.

### 9.3. Xác minh sau rollback

Sau khi traffic đã quay lại phiên bản ổn định, xác minh:

- Tất cả replica mong muốn đã ready.
- Image digest và config revision đúng phiên bản.
- OIDC Discovery trả issuer và endpoint đúng.
- JWKS vẫn công bố public key cần để xác minh token còn hiệu lực.
- Token mới có thể được phát hành.
- Token cũ và token được phát hành trong giai đoạn canary vẫn được xác minh theo policy.
- Authorization code và refresh token hợp lệ vẫn hoạt động.
- Session, consent và client registration còn nguyên vẹn.
- Database không có transaction dở dang hoặc dữ liệu bị chuyển đổi một phần.
- Metric lỗi và latency trở về gần baseline.

Không xóa pod canary hoặc môi trường green trước khi thu thập log và trạng thái cần cho điều tra. Không xóa key mới nếu token ký bằng key đó còn được chấp nhận.

## 10. Các tình huống rollback đặc thù của Authorization Server

### 10.1. Phiên bản mới đã phát hành token bằng signing key mới

Nếu token mới đã được phát hành, phiên bản cũ cần xác minh được token đó trong thời hạn còn hiệu lực. Giữ public key mới trong JWKS và bảo đảm verifier của phiên bản cũ hỗ trợ thuật toán đó.

Nếu phiên bản cũ không hỗ trợ thuật toán mới, việc dừng phát hành token mới chưa đủ xử lý các token đã được phát hành. Cần giữ verifier tương thích ở phiên bản rollback, chờ token đó hết hạn theo chính sách hoặc phát hành forward fix trước khi chuyển traffic hoàn toàn. Không xóa public key chỉ để đưa hệ thống về trạng thái cũ.

### 10.2. Schema đã được expand nhưng code mới lỗi

Nếu migration chỉ thêm cấu trúc tương thích, có thể giữ schema mới và rollback code. Kiểm tra phiên bản cũ không bị ảnh hưởng bởi cột/bảng bổ sung và không có migration contract đã chạy.

Không chạy migration down tự động nếu migration đó xóa dữ liệu được phiên bản mới tạo.

### 10.3. Schema đã contract hoặc dữ liệu đã chuyển đổi

Nếu migration đã xóa cột cũ hoặc đổi format không tương thích, phiên bản cũ có thể không chạy được. Khi đó:

- Dừng traffic mới vào phiên bản lỗi.
- Đánh giá khả năng forward fix.
- Nếu cần restore, xác định chính xác dữ liệu authorization/token phát sinh sau backup.
- Lập kế hoạch reconcile dữ liệu trước khi khôi phục.
- Phối hợp client/resource server nếu token hoặc authorization state bị ảnh hưởng.

Với hệ thống cấp token, restore database cũ có thể làm sống lại trạng thái revoke hoặc làm mất refresh token rotation state. Đây là rủi ro bảo mật cần được đánh giá trước khi thực hiện.

### 10.4. Phiên bản mới thay đổi subject hoặc issuer

Thay đổi sub hoặc iss có thể làm client coi người dùng là một identity khác hoặc từ chối ID Token. Rollback code có thể khiến token mới và token cũ cùng tồn tại với hai quy tắc subject.

Nếu đã phát hành token theo quy tắc mới, hãy giữ mapping tương thích và xác định thời gian tồn tại của token đó. Không tự động thay subject mới bằng subject cũ trong response mà không có mapping ổn định và chính sách identity rõ ràng.

### 10.5. Phiên bản mới thay đổi client authentication

Nếu đổi từ client_secret_basic sang private_key_jwt hoặc mTLS, các client có thể đã cập nhật credential hoặc metadata trong thời gian rollout. Rollback server có thể làm client mới không xác thực được.

Chuẩn bị kế hoạch chuyển tiếp cho cả hai phía:

- Giữ phương thức cũ trong thời gian tương thích nếu policy cho phép.
- Xác minh client registration và auth method đã được lưu.
- Không hạ cấp authentication method tự động khi credential mới thất bại.
- Có danh sách client đã thay đổi và cách đưa metadata về trạng thái tương thích.

## 11. Kế hoạch triển khai mẫu

Ví dụ kế hoạch rollout cho một bản nâng cấp Spring Authorization Server:

| Giai đoạn | Công việc | Điều kiện hoàn tất |
|---|---|---|
| T-7 ngày | Review release notes, API changes, schema, token, key và client compatibility | Có checklist và risk owner |
| T-3 ngày | Kiểm thử staging, load test, rollback rehearsal | Các luồng chính đạt và rollback đã diễn tập |
| T-1 ngày | Chốt image digest, migration, dashboard, alert và người trực | Artifact và runbook sẵn sàng |
| T0 - pre-deploy | Chụp baseline, kiểm tra database backup, key và dependency | Baseline được ghi nhận |
| T0 - canary | Triển khai nhóm nhỏ, chạy synthetic flow | Không có regression vượt ngưỡng |
| T0 - expansion | Mở rộng traffic từng nấc | Mỗi nấc đạt cửa sổ ổn định |
| T0 - completion | Hoàn tất rollout, kiểm tra replica và migration | Tất cả instance ở phiên bản mới |
| T+1 ngày | Theo dõi lỗi trễ, refresh token, client auth và resource server | Metric ổn định, không còn incident mở |
| Sau cửa sổ rollback | Chạy contract migration nếu phù hợp, dọn tài nguyên cũ | Có xác nhận không còn consumer phiên bản cũ |

Mốc thời gian là ví dụ. Với hệ thống có lưu lượng thấp hoặc token lifetime dài, cửa sổ theo dõi cần đủ để quan sát các luồng refresh, revoke và token validation thực tế.

## 12. Checklist trước, trong và sau rollout

### Trước rollout

- [ ] Đã chốt phiên bản Java, Spring Boot, Spring Security và Spring Authorization Server.
- [ ] Đã đọc release notes và migration guide.
- [ ] Đã ghi baseline availability, latency và OAuth error.
- [ ] Đã xác định luồng/client bị ảnh hưởng.
- [ ] Đã kiểm tra tương thích database schema giữa phiên bản cũ và mới.
- [ ] Đã kiểm tra authorization state, session và PAR persistence.
- [ ] Đã xác minh signing key, JWKS và issuer tương thích.
- [ ] Đã lưu image digest, config revision và migration version.
- [ ] Đã có backup/snapshot và hiểu giới hạn khôi phục.
- [ ] Đã diễn tập rollback code/config trong staging.
- [ ] Đã có dashboard, alert, runbook và người điều phối.

### Trong rollout

- [ ] Canary được giới hạn đúng phạm vi.
- [ ] Readiness và liveness phản ánh đúng tình trạng instance.
- [ ] Synthetic authorization flow chạy thành công.
- [ ] Token endpoint và refresh token không có regression.
- [ ] UserInfo, discovery và JWKS hoạt động.
- [ ] Client authentication method quan trọng hoạt động.
- [ ] Database, session store, cache và KMS ổn định.
- [ ] Metric được phân tích theo phiên bản.
- [ ] Mỗi nấc rollout có quyết định continue/hold/rollback.
- [ ] Không mở rộng traffic khi chưa hiểu một cảnh báo nghiêm trọng.

### Sau rollout

- [ ] Tất cả replica chạy đúng image digest và config revision.
- [ ] Error rate và latency nằm trong SLO.
- [ ] Token cũ và mới đều được xác minh theo policy.
- [ ] Authorization code, refresh token, consent và session hoạt động.
- [ ] JWKS giữ đủ key cho token còn hiệu lực.
- [ ] Database migration được xác minh.
- [ ] Không còn alert hoặc incident chưa được phân loại.
- [ ] Log, metric, decision và incident timeline được lưu.
- [ ] Chỉ chạy contract migration sau khi hết cửa sổ rollback.
- [ ] Đã ghi nhận bài học và cập nhật runbook.

Triển khai theo giai đoạn giúp giới hạn phạm vi ảnh hưởng và tạo thời gian kiểm chứng hành vi thực tế. Theo dõi sự cố cần kết hợp health check với metric nghiệp vụ như authorization, token, refresh, client authentication và xác minh JWT. Rollback chỉ an toàn khi code cũ còn tương thích với schema, state, issuer và signing key hiện tại; vì vậy phương án quay lại phải được thiết kế và diễn tập trước khi bắt đầu rollout.

