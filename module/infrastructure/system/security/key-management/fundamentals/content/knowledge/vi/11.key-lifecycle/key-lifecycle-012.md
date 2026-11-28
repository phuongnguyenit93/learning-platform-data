# Revoke key

> **Chương:** Key lifecycle  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Revoke key là gì?

**Revoke key (thu hồi khóa)** là hành động **chấm dứt hoặc rút lại quyền sử dụng hay sự tin cậy đối với một khóa mật mã**, theo phạm vi và thời điểm mà chính sách bảo mật quy định. Một khóa có thể bị thu hồi vì **private/secret key bị lộ**, chủ thể không còn được ủy quyền, chứng thư không còn đáng tin, thuật toán bị loại bỏ hoặc hệ thống cần ngừng chấp nhận khóa trước thời hạn dự kiến.

Trong key management, **thu hồi không chỉ là xóa một dòng database hoặc đổi nhãn `status`**. Cần trả lời rõ:

1. **Thu hồi đối tượng nào?** Cả logical key, **một key version**, chứng thư gắn public key, PSK của thiết bị hay quyền của một principal?
2. **Không cho phép thao tác nào?** `Encrypt`, `Decrypt`, `Wrap`, `Unwrap`, `Sign`, xác minh chữ ký mới hay tất cả?
3. **Có hiệu lực từ khi nào, tại những hệ thống nào?** KMS/HSM, ứng dụng, key registry, client đã cache, gateway, backup, node offline?
4. **Phải làm gì với dữ liệu và phiên trước đó?** Ciphertext, wrapped DEK, chữ ký lịch sử, TLS session/resumption secret hoặc token còn hạn?
5. **Làm sao kiểm chứng việc thu hồi đã được thực thi?** Audit, kiểm thử phủ định, cache invalidation, giám sát sử dụng khóa cũ?

**Cảnh báo cốt lõi:** revocation là việc **thay đổi quyền và niềm tin trong tương lai**; nó **không thể khiến người đã sao chép secret key quên đi các byte của khóa**. Nếu attacker đã có private key/DEK, thay metadata hoặc vô hiệu hóa một API không xóa được bản sao mà họ giữ. Vì thế, xử lý khóa bị lộ có thể đòi hỏi **thay khóa, rewrap hoặc re-encrypt dữ liệu, vô hiệu hóa các phiên/credential liên quan và điều tra tác động**.

### Ví dụ mở đầu

Một dịch vụ phát hành hóa đơn ký bằng RSA-PSS qua HSM. Phát hiện private key ký có nguy cơ bị lộ, nhóm an ninh thu hồi quyền `Sign` trong HSM, đánh dấu phiên bản `signing-v5` không còn được tin cho chữ ký mới, phát hành khóa/chứng thư mới và thông báo các bên xác minh. **Một chữ ký cũ vẫn có thể có giá trị theo chính sách xác minh lịch sử nếu có bằng chứng thời gian đáng tin**; ngược lại, chữ ký có `Signature.verify() == true` được tạo sau sự cố không tự được chấp nhận.

## 2. Đặt revocation vào vòng đời khóa

Một mô hình lifecycle thường có các bước: sinh → cấp phát → kích hoạt → sử dụng → ngừng dùng/thu hồi → lưu giữ có kiểm soát hoặc hủy. Tên trạng thái và API **khác nhau giữa tiêu chuẩn, KMS/HSM, PKI và ứng dụng**.

~~~mermaid
flowchart TD
    NEW[Generated / Created] --> PRE[Pre-active]
    PRE --> ACTIVE[Active]
    ACTIVE --> RETIRED[Retired / Deactivated]
    ACTIVE --> SUSP[Suspended: tạm dừng]
    SUSP -->|Được phê duyệt sau điều tra| ACTIVE
    ACTIVE --> REVOKED[Revoked: rút quyền / niềm tin]
    SUSP --> REVOKED
    RETIRED --> REVOKED
    RETIRED --> DESTROY[Destroyed]
    REVOKED --> MIGRATE[Đánh giá dữ liệu, bằng chứng, phiên còn phụ thuộc]
    MIGRATE --> DESTROY
~~~

Sơ đồ là **mô hình khái niệm**, không phải state machine bắt buộc của mọi sản phẩm. Khi đã xác định secret thực sự bị lộ, nhiều chính sách coi revocation là **quyết định không thể đảo ngược với vật liệu khóa đó**, dù nhà cung cấp vẫn hỗ trợ nút `Enable` để bật lại một đối tượng KMS.

### Phân biệt các hành động gần nhau

| Khái niệm | Ý nghĩa chính | Điều cần nhớ |
| --- | --- | --- |
| **Deactivate / retire** | Kết thúc việc tạo bảo vệ mới bằng khóa, thường theo kế hoạch | Có thể vẫn cho phép decrypt/unwrap dữ liệu cũ hoặc verify chữ ký lịch sử |
| **Suspend** | Tạm dừng vì rủi ro/chờ điều tra | Có thể khôi phục sau quy trình xác minh và phê duyệt |
| **Revoke** | Rút quyền dùng hoặc niềm tin vào khóa/chứng thư trong phạm vi chính sách | Cần phối hợp các bên dùng và kiểm tra hiệu lực thực tế |
| **Disable** | Tắt sử dụng khóa theo API nhà cung cấp | Không mặc nhiên đồng nghĩa cập nhật trust ở client hoặc thu hồi chứng thư |
| **Rotate** | Chuyển từ khóa/phiên bản cũ sang khóa mới | Không nhất thiết vô hiệu hóa khóa cũ ngay; phải xử lý phụ thuộc |
| **Delete / destroy** | Xóa/hủy vật liệu khóa theo quy trình | Có thể làm mất vĩnh viễn khả năng decrypt/restore nếu chưa di chuyển dữ liệu |
| **Revoke principal access** | Thu hồi quyền của một workload/người dùng với khóa | Khóa có thể vẫn Active cho các chủ thể hợp lệ khác |

**Rotation và revocation không tương đương.** Khi rotation định kỳ, khóa cũ chưa chắc bị lộ và vẫn có thể dùng để giải mã dữ liệu cũ; khi secret bị compromise, ta phải giả định đối thủ có thể sở hữu **bản sao khóa và những ciphertext đã thu thập**.

## 3. Thu hồi điều gì: vật liệu, quyền sử dụng hay niềm tin?

Một thiết kế trưởng thành phân biệt **ba lớp kiểm soát**:

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Vật liệu khóa (key material)** | Raw secret/private key có còn tồn tại và truy cập được ở đâu? | Key trong HSM, bản sao trong RAM, file backup, thiết bị ngoại tuyến |
| **Khả năng thực thi (use authorization)** | Ai còn gọi được `Sign`, `Decrypt`, `Unwrap`? | IAM policy, key policy, HSM partition, secret store, ứng dụng |
| **Niềm tin (trust / acceptance)** | Bên xác minh còn chấp nhận khóa/chứng thư/token không? | CA revocation, trust store, JWKS, registry, cache verifier |

Ví dụ **KMS `DisableKey`** (nếu nhà cung cấp hỗ trợ) có thể ngừng các thao tác KMS nhưng **không tự gỡ public key khỏi JWKS** của dịch vụ khác. Ngược lại, gỡ một public key khỏi JWKS có thể khiến verifier từ chối JWT ký mới nhưng **không trực tiếp hủy private key** trong HSM.

### Key ID, version và phạm vi tenant

Một logical key có thể chứa nhiều phiên bản. Nếu **chỉ `key-v4` bị lộ**, cần biết nhà cung cấp/policy hỗ trợ thu hồi phiên bản đó riêng hay phải xử lý **cả logical key**. Không sử dụng alias `current` làm bằng chứng rằng mọi bản ghi cũ đều dùng cùng phiên bản.

Khi ra quyết định, nêu rõ:

- `keyId`, **version/fingerprint** và thuật toán.
- Owner, tenant, môi trường (production/staging), purpose.
- **Effective time** và căn cứ thời gian đáng tin cậy.
- Loại thao tác bị cấm, ngoại lệ được phê duyệt nếu có.
- Danh sách hệ thống, bản sao và dữ liệu/đối tác phụ thuộc.

**Không nên thu hồi toàn bộ tenant hoặc cả hệ thống chỉ vì một service account bị mất quyền**, nếu có thể cô lập chính xác quyền của principal; ngược lại, không thu hồi hẹp một key alias nếu secret bị lộ còn được sử dụng ở nhiều hệ thống khác.

## 4. Khi nào cần revoke key?

### 4.1. Private/secret key bị lộ hoặc nghi bị lộ

Đây là tình huống khẩn cấp: ví dụ private key có trong Git, memory dump bị rò rỉ, token HSM bị lạm dụng, một KMS principal bị chiếm hoặc thiết bị chứa PSK bị mất. Cần **phân loại mức độ chắc chắn**, nhưng không đợi chứng cứ tuyệt đối khi tác động có thể nghiêm trọng.

Thu hồi quyền thực thi mới **không sửa được dữ liệu đã mất bí mật**. Nếu đối thủ có secret key và ciphertext, họ có thể giải mã ngoại tuyến ngay cả khi ứng dụng không còn cho gọi API decrypt.

### 4.2. Chủ thể không còn được ủy quyền

Nhân viên nghỉ việc, dịch vụ ngừng vận hành, thiết bị IoT bị thanh lý hoặc đối tác kết thúc hợp đồng. Có thể cần **thu hồi quyền truy cập của chủ thể**, thu hồi chứng thư hoặc PSK riêng, vô hiệu hóa session và token. **Chưa chắc phải hủy một KEK dùng chung hợp lệ** khi chỉ một principal không còn quyền.

### 4.3. Khóa/chứng thư sai danh tính hoặc phạm vi

Ví dụ CA cấp chứng thư cho sai hostname, registry gắn public key vào sai issuer, hoặc khóa staging được dùng nhầm ở production. Đây là lỗi **trust binding**, cần thu hồi sự công nhận khóa và sửa quy trình cấp phát, dù bản thân private key chưa được xác nhận là bị lộ.

### 4.4. Thuật toán, tham số hoặc thiết bị không còn đáp ứng chính sách

Một chính sách mới loại bỏ kích thước RSA yếu, chế độ cũ hoặc HSM không đáp ứng yêu cầu. Có thể **deactivate/retire theo kế hoạch** rồi thay bằng khóa mới; chỉ gọi đây là revocation nếu thực sự cần **rút quyền tin cậy/sử dụng theo policy**. Không đánh đồng hết cryptoperiod thông thường với compromise.

### Ma trận quyết định nhanh

| Tình huống | Hành động ưu tiên | Cần xem xét thêm |
| --- | --- | --- |
| Rotation định kỳ, không có dấu hiệu lộ | Active khóa mới, retire khóa cũ cho tạo dữ liệu mới | Rewrap, retention và decrypt dữ liệu cũ |
| Nghi private key ký bị lộ | Chặn `Sign`, kiểm tra compromise, xử lý chứng thư/trust | Chữ ký giả, thời điểm ký, verifier cache |
| DEK bị lộ | Ngừng dùng DEK, tạo DEK mới | **Re-encrypt** dữ liệu, ciphertext đã bị lấy |
| KEK bị lộ | Cô lập `Wrap/Unwrap`, thay KEK | Wrapped DEK có thể bị giải mã, đánh giá DEK và ciphertext |
| Một service account bị chiếm | Thu hồi credential/IAM, hủy session | Có bị lộ key material hoặc dữ liệu không? |
| Thiết bị dùng PSK riêng bị mất | Thu hồi PSK/chứng thư thiết bị, chặn kết nối | Session đang chạy, ticket/resumption |
| Key đã hết hạn policy | Ngừng sử dụng mới, kế hoạch retirement | Khả năng kiểm tra và khôi phục tài liệu cũ |

## 5. Quy trình revoke key an toàn theo từng bước

### Bước 1 — Phát hiện, phân loại và xác định phạm vi

Thu thập bằng chứng cần thiết: key ID/version, tenant, owner, loại khóa, nơi lưu, thời điểm nghi lộ, principal từng sử dụng, dấu vết ciphertext/chữ ký và dịch vụ phụ thuộc. **Không chép secret vào ticket, chat hoặc log để minh họa sự cố**.

Phân biệt **nghi lộ key material** với việc **một user có quyền quá rộng**. Hai loại có thể cần đối sách khác nhau. Khi chưa xác định hết phạm vi, ưu tiên chặn **đường gây hại trực tiếp** với độ rộng phù hợp.

### Bước 2 — Containment: chặn sử dụng trái phép

- Vô hiệu hóa thao tác không được phép trong KMS/HSM/secret manager, hoặc thu hồi IAM/credential của principal bị chiếm.
- Ngừng tạo ciphertext/chữ ký mới bằng key version có rủi ro.
- Thu hồi chứng thư, binding registry hoặc tập public key được tin cậy **nếu phạm vi đòi hỏi**.
- Vô hiệu hóa token/PSK/session liên quan theo mô hình giao thức, kể cả đường resumption khi cần.
- Giữ đủ chứng cứ audit nhưng không lưu key dạng rõ ngoài vùng được phê duyệt.

**Không vội xóa vĩnh viễn key material** khi đang cần điều tra hoặc dữ liệu/backup còn phụ thuộc, trừ khi mô hình đe dọa và phương án phục hồi yêu cầu khác. Việc **cô lập lập tức** và việc **hủy không thể khôi phục** là hai quyết định riêng.

### Bước 3 — Thu hồi niềm tin và truyền đạt hiệu lực

Gửi trạng thái đến các **verifier, key registry, CA/PKI, gateway, CDN, đối tác và node** đang dùng khóa. Với hệ thống phân tán cần TTL/đường invalidation rõ ràng. **Không tuyên bố đã revoke toàn hệ thống chỉ vì bảng metadata ở một node đã đổi**.

Nếu chứng thư bị thu hồi, cần tuân thủ quy trình của CA và hiểu thực tế là **không phải mọi client đều kiểm tra trạng thái thu hồi giống nhau**. Khi rủi ro cao, dùng thêm biện pháp chặn/rotate hoặc các cách giảm tác động ở tầng ứng dụng.

### Bước 4 — Tạo khóa thay thế và chuyển lưu lượng

Sinh khóa mới bằng nguồn entropy/KMS/HSM phù hợp; cấp IAM tối thiểu, key usage và cryptoperiod rõ. Công bố public key/chứng thư mới qua kênh tin cậy khi cần. Chỉ đưa khóa mới vào Active sau khi xác minh đúng identity, scope và khả năng tương thích.

**Không dùng lại cùng vật liệu secret bị nghi lộ dưới alias mới.** Rotation có ý nghĩa thay đổi bí mật nếu key material cũ đã compromised.

### Bước 5 — Đánh giá dữ liệu cũ: rewrap hay re-encrypt?

Kiểm kê encrypted records, wrapped DEK, backups, snapshots và các bản sao đã có thể bị thu thập. Chọn thao tác dựa trên **khóa nào thực sự bị lộ**. Có trường hợp chỉ cần rewrap DEK; trường hợp khác **phải thay DEK và mã hóa lại dữ liệu**. Chi tiết ở mục 8.

### Bước 6 — Kiểm chứng, giám sát và kết thúc sự cố

Kiểm tra tình huống phủ định (**negative tests**): yêu cầu `Sign/Encrypt/Unwrap` bằng khóa đã thu hồi phải bị chặn theo chính sách; verifier không được chấp nhận chữ ký/token mới bằng khóa không còn tin cậy. Kiểm tra các node ở nhiều vùng, cache, hàng đợi retry, offline clients và lịch xử lý batch.

Ghi audit **ai ra quyết định, căn cứ, thời điểm hiệu lực, hành động, kết quả kiểm tra và những ngoại lệ chưa xử lý**. Có kế hoạch triage và rollback dịch vụ **không được tái kích hoạt key đã xác định compromised**.

~~~mermaid
flowchart TD
    A[Phát hiện hoặc nghi vấn cần thu hồi] --> B[Định danh key/version + scope]
    B --> C{Có nguy cơ compromise?}
    C -->|Có hoặc chưa loại trừ được| D[Containment / block thao tác nguy hiểm]
    C -->|Không, retire theo policy| E[Ngừng sử dụng mới theo lịch]
    D --> F[Revoke use + trust nơi cần thiết]
    E --> G[Chuẩn bị khóa thay thế]
    F --> G
    G --> H[Chuyển key version / phân phối trust mới]
    H --> I{Dữ liệu và phiên cũ phụ thuộc?}
    I -->|Có| J[Rewrap / re-encrypt / revoke token / giữ bằng chứng]
    I -->|Không| K[Kiểm chứng hiệu lực]
    J --> K
    K --> L[Audit, giám sát và hủy theo retention]
~~~

## 6. Revoke từng loại khóa: tác động rất khác nhau

| Loại khóa | Tác động thu hồi | Điều cần giải quyết |
| --- | --- | --- |
| **DEK đối xứng** | Không còn dùng để mã hóa/giải mã dữ liệu theo policy | Nếu bị lộ, cân nhắc thay DEK và **re-encrypt** ciphertext |
| **KEK / wrapping key** | Chặn wrap/unwrap DEK mới hoặc cũ tùy chế độ | Wrapped DEK cũ, backup, khả năng rewrap; rủi ro nếu KEK bị lộ |
| **Private key RSA giải mã** | Chặn key transport/unwrap mới | Ciphertext/wrapped DEK gửi cho public key tương ứng có thể bị giải mã nếu attacker giữ private key |
| **Private key ký số** | Không được tạo chữ ký mới đáng tin hoặc gọi `Sign` | Phân phối thông tin thu hồi; chứng từ cũ và bằng chứng thời gian |
| **Public key/chứng thư** | Bên xác minh rút niềm tin vào binding danh tính–khóa | PKI/CRL/OCSP, cache, trust store, chuỗi chứng thư |
| **PSK/HMAC key** | Chặn xác thực hoặc tạo MAC mới bằng secret | Thiết bị còn offline, các bên cùng dùng secret, message/replay |
| **TLS session/resumption secret** | Kết nối hoặc phiên khôi phục có thể không còn được chấp nhận | Đóng session, ticket key, resumption policy, giới hạn hiệu lực |
| **JWT signing key** | Verifier không nên tin chữ ký mới theo key bị thu hồi | JWKS cache, thời hạn token, claim `kid`, quy tắc xác minh lịch sử |

**Không có thao tác `revokeKey()` chung nào bảo đảm giải quyết mọi dòng trong bảng**. Ví dụ, thu hồi quyền KMS không tự làm một thiết bị IoT ngừng tin PSK đã lưu cục bộ; thay chứng thư TLS không tự vô hiệu mọi JWT đã ký bằng một key khác.

### 6.1. Private signing key bị lộ

Một private key RSA-PSS, ECDSA hoặc Ed25519 bị lộ cho phép đối thủ **tạo chữ ký toán học hợp lệ** bằng chính key đó. Thu hồi phải giải quyết cả **khả năng ký mới** và **niềm tin của bên xác minh**, không chỉ đưa private key vào một thư mục "revoked".

Điều không thể làm là “thu hồi” byte signature đã được lưu để khiến phép toán `Verify` tự trả false; thuật toán xác minh vẫn có thể trả true dưới public key tương ứng. **Quyết định tin cậy** phải xét trạng thái key/certificate, ngữ cảnh, chính sách và bằng chứng thời gian.

### 6.2. Secret dùng cho giao thức

PSK bị lộ có thể ảnh hưởng nhiều phiên, đặc biệt khi nó được chia sẻ cho nhiều thiết bị. Với các giao thức thỏa thuận khóa có forward secrecy nhờ (EC)DHE, lộ khóa xác thực dài hạn **về sau** không nhất thiết làm lộ bản ghi lưu lượng cũ; nhưng **PSK-only**, session ticket/resumption và endpoint bị chiếm có mô hình rủi ro khác.

Thu hồi một PSK có thể yêu cầu **tái cấp phát vật liệu bí mật cho mọi bên liên quan**, chứ không chỉ thay một biến môi trường ở gateway.

## 7. Thu hồi chứng thư X.509: CRL, OCSP và xác minh lịch sử

Với PKI, **chứng thư X.509** liên kết một public key với danh tính/thuộc tính và được CA ký. **Certificate revocation** là việc CA hoặc cơ chế tin cậy liên quan thông báo chứng thư không còn được công nhận **trước khi hết hạn dự kiến**, theo phạm vi chính sách.

### 7.1. CRL và OCSP

| Cơ chế | Ý nghĩa | Giới hạn thực tế |
| --- | --- | --- |
| **CRL (Certificate Revocation List)** | Danh sách chứng thư đã bị thu hồi, được CA ký và công bố | Độ mới phụ thuộc chu kỳ phát hành và cache; client cần lấy/kiểm tra đúng |
| **OCSP (Online Certificate Status Protocol)** | Phương thức hỏi trạng thái chứng thư từ responder được ủy quyền | Có thể chịu lỗi mạng, latency, cache; policy xử lý trạng thái không xác định khác nhau |
| **OCSP stapling** | Máy chủ đính kèm phản hồi OCSP phù hợp trong handshake khi được hỗ trợ | Không thay việc client kiểm tra chuỗi tin cậy, danh tính và chính sách |
| **Short-lived certificate** | Giảm cửa sổ hiệu lực bằng chứng thư thời hạn ngắn | Cần tự động phát hành/triển khai, không thay thế toàn bộ quản trị sự cố |
| **Trust-store / registry update** | Gỡ một trust anchor/binding hoặc key được phê duyệt | Phải cập nhật client và cache; có thể ảnh hưởng nhiều hệ thống |

Độ tin cậy của việc xác minh phụ thuộc vào **policy bên nhận**: chain tới trust anchor được phê duyệt, hostname/identity, thời hạn, key usage/EKU, thuật toán và cơ chế thu hồi được yêu cầu. **Không nên giả định mọi ứng dụng Java tự bật kiểm tra revocation cho mọi đường dùng `X509Certificate`**; chính sách PKIX/OCSP/CRL cần được cấu hình và thử nghiệm trong môi trường thực.

### 7.2. Thu hồi chứng thư không đồng nghĩa xóa private key

Một chứng thư có thể đã bị revoke nhưng private key vẫn tồn tại trong HSM, file, backup hoặc thiết bị. Phải thu hồi **quyền sử dụng key material** và cập nhật các kênh tin cậy liên quan, tùy mô hình đe dọa. Ngược lại, xóa private key **không làm mọi verifier biết** rằng chứng thư không còn đáng tin.

### 7.3. Chữ ký lịch sử và thời gian ký

Một chữ ký số trên hóa đơn được tạo trước khi chứng thư bị revoke **có thể** tiếp tục được chấp nhận theo chính sách xác minh lịch sử, nhưng không thể khẳng định chỉ từ trường `signedAt` do chính người ký ghi. Hệ thống có thể cần:

- **Dấu thời gian đáng tin cậy (trusted timestamp)** hoặc chứng cứ thời gian tương đương.
- Chuỗi chứng thư, trạng thái CRL/OCSP tại mốc liên quan và chính sách xác minh dài hạn.
- Thông tin thời điểm compromise thực tế hoặc thời điểm biết/ghi nhận sự cố, nếu khác nhau.
- Quy tắc đánh giá chữ ký khi chứng thư đã hết hạn, bị thu hồi hoặc thuật toán suy yếu.

**Verify cryptographic signature = true không phải là kết luận pháp lý hay nghiệp vụ.** Cần phân biệt độ hợp lệ toán học, ràng buộc danh tính, trạng thái chứng thư và quyền ký.

## 8. DEK, KEK và envelope encryption khi revoke

Trong **envelope encryption**, ứng dụng dùng một **DEK** để mã hóa dữ liệu bằng AEAD như AES-GCM hoặc ChaCha20-Poly1305, rồi bảo vệ DEK bằng **KEK** thuộc KMS/HSM hoặc một cơ chế wrapping được phê duyệt.

~~~mermaid
sequenceDiagram
    participant Ops as Nhóm bảo mật
    participant App as Ứng dụng
    participant KMS as KMS/HSM
    participant DB as Kho dữ liệu
    Ops->>KMS: Khóa quyền use của KEK cũ theo sự cố
    Ops->>KMS: Tạo KEK mới + policy chặt
    Ops->>App: Ngừng ghi mới dưới key version cũ
    App->>DB: Liệt kê wrapped DEK phụ thuộc key cũ
    DB-->>App: Ciphertext + wrapped DEK + keyId/version
    App->>KMS: Mở bọc DEK cũ qua quy trình được phép
    KMS-->>App: DEK nếu policy/quy trình cho phép
    App->>KMS: Rewrap DEK dưới KEK mới hoặc thay DEK
    App->>DB: Cập nhật metadata và ciphertext khi cần
    Ops->>App: Kiểm thử decrypt/restore và negative tests
    Ops->>KMS: Đóng/hủy key cũ sau điều kiện đã phê duyệt
~~~

**Sơ đồ minh họa một kế hoạch migration có kiểm soát.** Nếu KEK bị xác định là đã lộ, **việc mở bọc bằng KEK cũ cần được xem là thao tác xử lý sự cố đặc biệt**, không được mặc nhiên mở lại quyền rộng rãi. KMS/HSM có thể không hỗ trợ trực tiếp rewrap hoặc trạng thái cho phép decrypt-only; khả năng thực tế tùy nhà cung cấp.

### Rewrap khác re-encrypt

| Hành động | Thay đổi gì? | Khi nào có thể đủ? |
| --- | --- | --- |
| **Rewrap DEK** | Giữ nguyên DEK và ciphertext; bọc lại DEK dưới KEK mới | Rotation KEK thông thường **không có lộ DEK**, đúng chính sách |
| **Re-encrypt bằng DEK mới** | Giải mã dữ liệu cũ rồi mã hóa lại bằng DEK mới và nonce/tag mới | DEK cũ bị lộ hoặc cần loại bỏ phụ thuộc vào nó |
| **Thay chỉ alias/key ID** | Đổi tham chiếu cấu hình, **không thay byte khóa** | Không giải quyết compromise vật liệu bí mật |
| **Destroy KEK** | Loại bỏ khả năng dùng vật liệu KEK (theo đảm bảo của nền tảng) | Chỉ sau khi xử lý dữ liệu/backup phụ thuộc hoặc quyết định crypto-erasure có chủ đích |

**Ví dụ rất quan trọng:** nếu attacker đã lấy được **KEK cũ và một bản sao wrapped DEK cũ**, rewrap bản hiện tại sang KEK mới **không xóa** bản wrapped DEK mà attacker giữ. Họ vẫn có thể khôi phục **DEK cũ** và giải mã **ciphertext cũ đã thu thập**. Vì vậy, nếu có khả năng attacker đã lấy KEK cùng wrapped DEK, cần xem phạm vi DEK, ciphertext, backup và cân nhắc **DEK mới + re-encrypt**, đồng thời hiểu rằng dữ liệu đã bị đọc trước đó không thể lấy lại tính bí mật.

### Không bỏ quên metadata AEAD

Khi migration, phải giữ hoặc cập nhật đúng **algorithm/version, key ID/version, nonce/IV, authentication tag, AAD và quan hệ tenant–record**. Không tái mã hóa bằng **cùng cặp (key, nonce)** đối với AES-GCM/ChaCha20-Poly1305. Không cho phép metadata do attacker kiểm soát chọn tùy ý KEK hoặc tenant trước khi kiểm tra quyền.

## 9. KMS/HSM: revoke phải được thực thi ở đúng lớp

Mỗi KMS/HSM có API và state machine riêng. Một số cung cấp `Enabled/Disabled`, chờ xóa, key version, alias và IAM riêng. **Không được khẳng định `Disable` luôn chỉ cấm encrypt nhưng vẫn cho decrypt**: nhiều nền tảng từ chối **mọi thao tác mật mã** trên key bị disabled.

Để thiết kế revoke an toàn:

1. **Xác định key-state thực tế** của nhà cung cấp và sự khác biệt với trạng thái lifecycle của ứng dụng.
2. **Thu hồi quyền IAM/principal riêng** nếu sự cố chỉ liên quan quyền dùng; không tự ý hủy shared KEK còn phục vụ các principal hợp lệ.
3. Khi **key material bị lộ**, đánh giá cả bản sao ngoài KMS, dữ liệu/backup và đường sử dụng khác.
4. Có **operation-level policy** nếu yêu cầu `DECRYPT_OLD` trong migration, nhưng không giả định mọi sản phẩm hỗ trợ chế độ này.
5. Áp dụng **least privilege, separation of duties**: quyền quyết định revoke, thay policy, ký/giải mã và xóa khóa không tập trung không kiểm soát vào cùng một vai trò.
6. Theo dõi **key ID/version thực tế**, không chỉ alias logic hay key name.

### Crypto-erasure có phải revoke?

**Cryptographic erasure** là loại bỏ khả năng khôi phục khóa cần thiết để giải mã dữ liệu, với giả định không còn bản sao key ngoài sự kiểm soát và dữ liệu chỉ có thể được đọc nhờ khóa đó. Đây **không phải đồng nghĩa** với `Revoke` hoặc `Disable`: revoke rút quyền/niềm tin, còn crypto-erasure hướng tới **không còn khả năng giải mã**.

Nếu DEK/KEK còn trong backup, snapshot, export hoặc RAM đã bị sao chép, không được khẳng định crypto-erasure đã hoàn tất chỉ vì một đối tượng KMS bị xóa. Ngược lại, hủy khóa khi chưa kiểm tra retention có thể **làm mất dữ liệu hợp lệ không thể phục hồi**.

## 10. Cache, TOCTOU và hệ thống phân tán

Thu hồi hiệu lực ở một node nhưng chưa truyền đến node khác tạo ra **cửa sổ chấp nhận trái phép**. Đây là lý do revocation cần cả **control plane** lẫn **data plane**.

### Ví dụ lỗi

~~~text
10:00:00  Security ghi key-v3 = REVOKED vào registry.
10:00:01  Gateway A đã nhận sự kiện, từ chối sử dụng.
10:00:02  Gateway B còn cache trạng thái ACTIVE 10 phút.
10:00:03  Gateway B vẫn chấp nhận JWT/PSK/key-v3.
10:10:02  Cache B hết hạn, việc thu hồi mới có hiệu lực tại B.
~~~

Tính an toàn không chỉ nằm ở **thời gian DB ghi `REVOKED`**, mà còn ở **thời gian thực tế mọi điểm quyết định bảo mật đã ngừng chấp nhận**. Với quyền có rủi ro cao, xem xét:

- **Versioned revocation events** và cache invalidation chủ động, có replay/acknowledgement.
- **TTL ngắn**, khả năng làm mới hoặc tham vấn policy nguồn đối với thao tác nhạy cảm.
- **Deny on stale policy** khi rủi ro cao và có yêu cầu fail-closed; lập kế hoạch bảo đảm sẵn sàng.
- **Chặn ở nơi thực thi** (KMS/HSM, API signer, validator) thay vì chỉ ở UI.
- **Kiểm tra nhiều vùng**, node offline, workers chạy batch, hàng đợi retry, session/ticket cache.
- **Quan sát thời gian revoke propagation**: từ quyết định đến lúc mọi consumer được kiểm soát đã xác nhận.

### TOCTOU: kiểm tra đúng nhưng dùng sai thời điểm

**TOCTOU (time-of-check to time-of-use)** xảy ra khi ứng dụng kiểm tra key còn Active ở thời điểm A, nhưng trước khi `Sign` hoặc `Decrypt` thực thi, key đã bị revoke ở thời điểm B. Nếu app tin vào quyết định cache cũ, lệnh có thể vượt policy.

Giải pháp ưu tiên là **thực thi policy ở chính điểm thao tác mật mã** hoặc qua dịch vụ tin cậy kiểm tra state/permission ngay lúc dùng. Kiểm tra ở Java có ích cho UX, nhưng **không thay KMS/HSM authorization hoặc verifier trust policy**.

### Đường dự phòng không được hạ cấp bảo mật

Khi registry/KMS không sẵn sàng, tránh chuyển ngầm sang **khóa cũ bị revoke** hoặc **accept signature without checking revocation** để duy trì dịch vụ. Chính sách fail-open/fail-closed cần được xác định trước theo loại giao dịch và yêu cầu an toàn. Với tác vụ có thể gây thiệt hại cao, **fail closed** thường là hướng thận trọng hơn.

## 11. Ví dụ Java 17: policy gate cho khóa bị thu hồi

Ví dụ dưới đây mô hình hóa **một quyết định cho phép thao tác trước khi gọi KMS**, với `KeyState`, `Operation`, thời gian hiệu lực và `policyRevision`. Chương trình cố ý **từ chối mọi thao tác live khi `REVOKED` hoặc `SUSPENDED`**, trong khi key `RETIRED` có thể được **unwrap dữ liệu cũ** trong recipient-usage period nếu chính sách cho phép.

**Đây là demo của tầng policy, không phải thư viện mật mã, không thực hiện `Encrypt/Decrypt` thật và không có hệ thống phân quyền danh tính.** KMS/ứng dụng production vẫn phải enforce state tại thời điểm thực thi, kiểm tra owner/tenant, quyền của principal và revision policy nguồn. Xác minh chữ ký lịch sử là **bài toán trust riêng**, không được tự động cho phép chỉ nhờ ví dụ `UNWRAP_OLD`.

~~~java
import java.time.Instant;
import java.util.EnumSet;
import java.util.Set;

public final class RevokeKeyPolicyDemo {
    enum State {
        PRE_ACTIVE, ACTIVE, SUSPENDED, RETIRED, REVOKED, DESTROYED
    }

    enum Operation {
        ENCRYPT_NEW, WRAP_NEW, SIGN_NEW, UNWRAP_OLD
    }

    record KeyPolicy(
            String keyId,
            String version,
            State state,
            Instant activatedAt,
            Instant newUseUntil,
            Instant oldUseUntil,
            Instant revokedAt,
            long policyRevision,
            Set<Operation> allowedOps) {
        KeyPolicy {
            if (keyId == null || keyId.isBlank()
                    || version == null || version.isBlank()
                    || state == null || activatedAt == null
                    || newUseUntil == null || oldUseUntil == null
                    || !activatedAt.isBefore(newUseUntil)
                    || newUseUntil.isAfter(oldUseUntil)
                    || policyRevision < 1 || allowedOps == null) {
                throw new IllegalArgumentException("Invalid key policy");
            }
            allowedOps = Set.copyOf(allowedOps);
        }
    }

    static boolean mayUse(KeyPolicy key, Operation op, Instant now) {
        if (key == null || op == null || now == null
                || !key.allowedOps().contains(op)
                || now.isBefore(key.activatedAt())) {
            return false;
        }
        // Revocation có hiệu lực trước cả quyền và cryptoperiod.
        if (key.state() == State.REVOKED
                || key.state() == State.SUSPENDED
                || key.state() == State.DESTROYED
                || key.state() == State.PRE_ACTIVE
                || (key.revokedAt() != null
                    && !now.isBefore(key.revokedAt()))) {
            return false;
        }

        return switch (op) {
            case ENCRYPT_NEW, WRAP_NEW, SIGN_NEW ->
                    key.state() == State.ACTIVE
                    && now.isBefore(key.newUseUntil());
            case UNWRAP_OLD ->
                    (key.state() == State.ACTIVE
                        || key.state() == State.RETIRED)
                    && now.isBefore(key.oldUseUntil());
        };
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-12-01T00:00:00Z");
        Instant endNew = Instant.parse("2027-03-01T00:00:00Z");
        Instant endOld = Instant.parse("2027-09-01T00:00:00Z");
        Instant incident = Instant.parse("2027-01-20T12:00:00Z");
        Set<Operation> ops = EnumSet.allOf(Operation.class);

        KeyPolicy active = new KeyPolicy(
                "customer-kek", "v7", State.ACTIVE,
                start, endNew, endOld, null, 21, ops);
        KeyPolicy retired = new KeyPolicy(
                "customer-kek", "v7", State.RETIRED,
                start, endNew, endOld, null, 22, ops);
        KeyPolicy revoked = new KeyPolicy(
                "customer-kek", "v7", State.REVOKED,
                start, endNew, endOld, incident, 23, ops);

        Instant duringActive = Instant.parse("2027-01-15T00:00:00Z");
        Instant afterRotation = Instant.parse("2027-04-01T00:00:00Z");
        Instant afterIncident = Instant.parse("2027-01-21T00:00:00Z");

        if (!mayUse(active, Operation.WRAP_NEW, duringActive)) {
            throw new AssertionError("Valid active key rejected");
        }
        if (mayUse(retired, Operation.WRAP_NEW, afterRotation)) {
            throw new AssertionError("Retired key created new protection");
        }
        if (!mayUse(retired, Operation.UNWRAP_OLD, afterRotation)) {
            throw new AssertionError("Expected controlled old-data access");
        }
        if (mayUse(revoked, Operation.UNWRAP_OLD, afterIncident)
                || mayUse(revoked, Operation.SIGN_NEW, afterIncident)) {
            throw new AssertionError("Revoked key was accepted");
        }
        if (mayUse(active, Operation.WRAP_NEW, endNew)) {
            throw new AssertionError("Cryptoperiod boundary failed");
        }
        System.out.println("Revoke key policy checks passed");
    }
}
~~~

### Giải thích giới hạn của đoạn mã

1. **Deny by default:** `REVOKED`, `SUSPENDED`, `DESTROYED` hoặc `PRE_ACTIVE` bị chặn; chỉ những trạng thái cho phép mới tới nhánh thao tác.
2. **`revokedAt`** cho phép mô hình hóa thời điểm có hiệu lực, nhưng demo xử lý `State.REVOKED` như một **chỉ thị chặn hiện tại**, kể cả khi mô phỏng hỏi thời điểm quá khứ. Để kiểm tra chữ ký lịch sử cần **bản ghi trạng thái theo thời gian và bằng chứng tin cậy**, không dùng hàm này.
3. **`policyRevision`** giúp biểu diễn version của chính sách, nhưng demo **chưa kiểm tra revision mới nhất với registry**. Production phải chống stale cache và rollback revision.
4. **`UNWRAP_OLD`** khi `RETIRED` chỉ hợp lệ nếu **nhà cung cấp và policy thực tế cho phép**; việc dùng key bị xác định compromised cần quy trình incident response riêng.
5. **Không dùng đồng hồ do client cung cấp** để đưa ra quyết định bảo mật. Cần nguồn thời gian đáng tin và quy tắc timezone/clock skew.
6. **Không tạo đường bypass:** code kiểm tra local không thay thế quyền IAM/KMS, key usage và kiểm tra dữ liệu thuộc đúng tenant.

## 12. Revocation event và audit

Một lệnh revoke cần đủ thông tin để đối chiếu toàn bộ hệ thống. Mẫu metadata sau **không chứa vật liệu khóa**, chỉ minh họa:

~~~json
{
  "eventType": "KEY_REVOKED",
  "keyId": "customer-kek",
  "keyVersion": "v7",
  "reason": "SUSPECTED_COMPROMISE",
  "effectiveAt": "2027-01-20T12:00:00Z",
  "policyRevision": 23,
  "scope": "production/customer-data",
  "blockedOperations": ["ENCRYPT", "WRAP", "UNWRAP"],
  "changeTicket": "SEC-1234"
}
~~~

Trong production, event cần **danh tính người/automation ra quyết định, phê duyệt, timestamp đáng tin, nguồn sự thật, integrity/authentication của event**, cùng cơ chế phát lại có kiểm soát. Không tin một sự kiện có thể bị giả mạo để disable khóa của toàn hệ thống.

### Audit nên trả lời được gì?

| Câu hỏi | Dữ liệu tối thiểu nên có |
| --- | --- |
| Ai revoke? | Principal, vai trò/phê duyệt, change/incident ID |
| Revoke khóa nào? | Key ID, version, algorithm, owner, môi trường |
| Khi nào? | Thời điểm quyết định, effective time, thời điểm từng consumer nhận |
| Vì sao? | Reason code, bằng chứng/đánh giá mà không lộ secret |
| Đã chặn gì? | Operation, principal, trust binding, KMS/HSM action |
| Ảnh hưởng đến đâu? | Tenant, service, backup, wrapped DEK, session, verifier |
| Đã kiểm chứng chưa? | Negative-test result, propagation lag, cache version |
| Phần nào chưa xử lý? | Offline client, dữ liệu cần re-encrypt, exception có thời hạn |

Audit phải hạn chế truy cập; **không ghi raw DEK, private key, PSK, access token, password hoặc plaintext**. Có thể dùng key ID/version/fingerprint phù hợp để tương quan sự kiện mà không tiết lộ bí mật.

### Chỉ số giám sát hữu ích

- Yêu cầu `Sign/Encrypt/Unwrap` vẫn dùng **key đã revoke**.
- Độ trễ từ revoke event tới **toàn bộ consumer xác nhận**.
- Tỷ lệ lỗi xác minh JWT/chứng thư sau khi thay key/trust.
- Số record/backup còn phụ thuộc KEK/DEK bị thu hồi.
- Số session/token/ticket còn có thể sử dụng sau sự cố.
- Số exception hoặc thao tác khẩn cấp còn chưa đóng.

## 13. Tình huống thực tế: revoke khóa sau khi mất quyền truy cập HSM

Một nền tảng thanh toán dùng **private key ký lệnh chi trả** trong HSM và **KEK** để bảo vệ DEK của dữ liệu khách hàng. Một service account có quyền ký và unwrap có dấu hiệu bị chiếm.

**Giai đoạn 1 — Containment:**

1. Vô hiệu hóa credential và session của service account bị chiếm, thu hồi IAM/KMS permissions liên quan.
2. Xác định **khả năng lộ private key/KEK hay chỉ lạm dụng API**. Nếu key material không xuất được, điều đó làm thay đổi mô hình rủi ro nhưng **không loại trừ chữ ký giả hoặc giải mã trái phép qua API khi attacker còn quyền**.
3. Tạm chặn các thao tác có thể gây thiệt hại, ghi chứng cứ HSM/KMS và ứng dụng an toàn.

**Giai đoạn 2 — Khóa ký:**

1. Tạo cặp khóa ký mới trong vùng bảo vệ được phê duyệt, cập nhật public key/chứng thư qua nguồn tin cậy.
2. Từ chối **lệnh chi trả mới** ký bằng key cũ theo policy; kiểm tra cache của các bên xác minh và hàng đợi giao dịch.
3. Đối chiếu các chữ ký trong giai đoạn bị ảnh hưởng với approval log, dữ liệu nghiệp vụ và bằng chứng thời gian. Không cho rằng `verify=true` có nghĩa giao dịch được ủy quyền.

**Giai đoạn 3 — Dữ liệu mã hóa:**

1. Liệt kê wrapped DEK bị ảnh hưởng; xác định liệu KEK thực sự bị lộ hay attacker chỉ dùng API `Unwrap`.
2. Nếu KEK/DEK bị lộ hoặc có nguy cơ ciphertext bị giải mã, thực hiện đánh giá thay DEK và **re-encrypt** dữ liệu phù hợp, thay vì chỉ đổi alias.
3. Kiểm tra khả năng đọc lại dữ liệu/bản sao lưu bằng key version mới; không delete khóa cũ thiếu kiểm chứng nếu dữ liệu hợp lệ vẫn phụ thuộc.

**Giai đoạn 4 — Kiểm chứng và phòng tái diễn:**

1. Chạy negative tests trên quyền ký/unwrap cũ, xác minh các vùng ứng dụng và client đã cập nhật.
2. Áp dụng **separation of duties**: service chỉ ký không đồng thời có toàn quyền giải mã dữ liệu; hạn chế phạm vi tenant.
3. Cảnh báo khi `Sign` hoặc `Unwrap` tăng bất thường; audit theo key ID/version và principal, không ghi nội dung nhạy cảm.

**Kết luận tình huống:** revoke quyền của một account, revoke niềm tin vào một signing key và thay KEK/DEK là **ba nhóm hành động khác nhau**. Chọn đúng phạm vi quyết định cả tính an toàn và khả năng phục hồi dịch vụ.

## 14. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Phòng tránh |
| --- | --- | --- |
| Đổi `status=REVOKED` trong DB rồi coi như xong | KMS/client vẫn chấp nhận key cũ | Kiểm tra enforcement, truyền trạng thái và negative tests |
| Xóa key ngay khi nghi lộ | Có thể mất vĩnh viễn ciphertext và backup | Containment trước, đánh giá phụ thuộc, phê duyệt hủy |
| Rotation alias nhưng giữ nguyên byte khóa bị lộ | Attacker vẫn giữ secret | Sinh vật liệu mới, xử lý các bản sao và ciphertext liên quan |
| Thu hồi chứng thư nhưng không chặn `Sign` | Private key có thể vẫn ký | Xử lý cả trust và khả năng thực thi ở signer |
| Disable key trong KMS nhưng JWKS cache vẫn tin public key | Verifier tiếp tục chấp nhận token/chữ ký | Cập nhật registry/cache và kiểm tra issuer/policy |
| Chỉ rewrap DEK khi KEK cũ đã bị lấy | Wrapped DEK cũ bị thu thập vẫn giải mã được | Đánh giá thay DEK/re-encrypt và dữ liệu đã lộ |
| Coi DEK bị lộ là đã an toàn sau revoke IAM | Kẻ giữ raw DEK giải mã offline | Thay DEK, re-encrypt và xử lý sự cố |
| Không phân biệt hết hạn, retirement và compromise | Xóa quá sớm hoặc tin khóa nguy hiểm | Ma trận quyết định theo lý do, thời gian và loại khóa |
| Không xét recipient period / backup | Không restore được dữ liệu | Kiểm kê phụ thuộc, rewrap/restore trước khi hủy |
| Chấp nhận `Verify=true` cho chữ ký sau compromise | Tin chữ ký giả của attacker | Kiểm tra key trust, thời điểm, quyền và bằng chứng |
| Nghĩ CRL/OCSP đồng bộ tức thời tới mọi verifier | Client có thể cache hoặc không kiểm tra | Chính sách thu hồi, propagation và biện pháp bổ sung |
| Dùng quyết định ACTIVE từ cache cũ | TOCTOU và bypass revoke | Revalidate gần nơi thực thi, revision và cache invalidation |
| Fallback sang key cũ khi KMS lỗi | Bypass revocation | Fail-closed theo mức rủi ro |
| Log private key/DEK làm chứng cứ | Mở rộng sự cố lộ secret | Chỉ log metadata an toàn, hạn chế truy cập audit |
| Xóa public key/cert lịch sử không lưu chứng cứ | Không thể kiểm tra chữ ký cũ theo policy | Lưu key binding, certificate chain, timestamp/OCSP-CRL khi cần |

## 15. Checklist triển khai revoke key

- [ ] Đã xác định **key ID/version**, thuật toán, owner, tenant, môi trường và purpose?
- [ ] Đã phân biệt **thu hồi quyền principal**, **key usage** và **niềm tin vào public key/chứng thư**?
- [ ] Lý do là retirement, nghi compromise, xác nhận compromise hay sai trust binding?
- [ ] Đã chặn đường sử dụng gây hại ở KMS/HSM/signer/app **trước khi** chờ mọi cache cập nhật?
- [ ] Có kế hoạch phân phối revoke event được xác thực, version/TTL và xử lý node offline?
- [ ] Chữ ký số/PKI có chính sách CA revocation, CRL/OCSP, key usage và xác minh lịch sử?
- [ ] JWT/JWKS có cơ chế refresh, `kid` trong đúng issuer và cách xử lý token chưa hết hạn?
- [ ] Đã xét PSK, session resumption, TLS ticket và các phiên còn sống nếu sự cố liên quan giao thức?
- [ ] Đã đánh giá ciphertext, wrapped DEK, backup, snapshot và bản sao có thể bị thu thập?
- [ ] Phân biệt **rewrap** khi chỉ rotation KEK với **re-encrypt** khi DEK có nguy cơ lộ?
- [ ] Khóa thay thế được sinh trong nguồn entropy/KMS/HSM tin cậy, purpose và IAM chính xác?
- [ ] Không tái kích hoạt raw key đã xác nhận compromised chỉ vì rollback?
- [ ] Đã chạy **negative tests**: thao tác bị thu hồi phải từ chối tại mọi điểm thực thi cần thiết?
- [ ] Đã kiểm tra khả năng đọc dữ liệu hợp lệ và restore backup theo chính sách retention?
- [ ] Audit có người quyết định, thời điểm, revision, phạm vi, kết quả và exception; **không chứa secret**?
- [ ] Có quy trình kết thúc sự cố, giám sát sau revoke và lịch hủy key material phù hợp?

## 16. Câu hỏi tự kiểm tra

**1. Revoke key có phải là xóa byte khóa khỏi mọi nơi không?**  
Không. Revoke rút quyền sử dụng hoặc niềm tin theo chính sách. Byte khóa có thể còn trong HSM, RAM, backup hoặc bản sao attacker đã lấy; xóa/hủy là hành động riêng.

**2. Rotation và revocation khác nhau như thế nào?**  
Rotation thay khóa/phiên bản theo kế hoạch hoặc để xử lý rủi ro; revocation rút quyền hoặc trust đối với khóa. Rotation thông thường có thể giữ decrypt-old, còn compromise cần xử lý nghiêm ngặt hơn.

**3. Nếu private key ký bị lộ, chỉ tắt API `Sign` đã đủ chưa?**  
Chưa. Phải xử lý trust của bên xác minh, chứng thư/key registry, các chữ ký có nguy cơ bị giả, phiên và cache có liên quan.

**4. Vì sao rewrap DEK không chắc sửa sự cố KEK bị lộ?**  
Vì attacker có thể đã giữ KEK cũ và wrapped DEK cũ. Họ vẫn khôi phục DEK để giải mã ciphertext đã thu thập. Cần xem xét thay DEK và re-encrypt.

**5. Chữ ký cũ có thể xác minh sau khi chứng thư bị revoke không?**  
Có thể theo chính sách lịch sử nếu có bằng chứng đáng tin về thời điểm ký, trạng thái chứng thư và các điều kiện khác. `Verify=true` một mình chưa đủ để chấp nhận.

**6. Vì sao xóa khóa có thể gây mất dữ liệu?**  
Vì ciphertext/backup cũ có thể chỉ được giải mã hoặc unwrap bằng key version đó. Phải kiểm kê và xử lý phụ thuộc trước khi destroy, trừ khi crypto-erasure chủ đích được phê duyệt.

**7. Revoke thành công trong KMS đã chắc các verifier JWT không chấp nhận chữ ký cũ?**  
Không. JWKS cache và logic xác minh có vòng đời riêng; phải cập nhật trust/claims và kiểm tra ở mọi verifier.

**8. Với PSK bị lộ, có thể chỉ thay PSK ở máy chủ không?**  
Không nhất thiết. Các thiết bị/client đang giữ PSK cần được thay theo quy trình an toàn; có thể cần vô hiệu session/ticket và xử lý offline clients.

**9. Vì sao quyết định `REVOKED` từ cache có thể chưa đủ?**  
Vì cache có thể cũ hoặc bị rollback, tạo cửa sổ TOCTOU. Cần enforcement ở nơi dùng khóa, policy revision và cơ chế invalidation.

## Ghi nhớ

**Revoke key là rút lại quyền sử dụng hoặc sự tin cậy đối với khóa mật mã trong một phạm vi xác định.** Nó khác **rotation, suspension, deactivation và destruction**, đồng thời **không làm biến mất bản sao khóa mà đối thủ đã lấy**. Một quy trình đúng phải **xác định key/version và phạm vi, chặn thực thi, thu hồi niềm tin, cấp khóa thay thế, xử lý ciphertext/chữ ký/PSK phụ thuộc, kiểm thử propagation và ghi audit**. Với **DEK/KEK**, phải phân biệt **rewrap** và **re-encrypt**; với chữ ký số, phải tách **xác minh mật mã** khỏi **chính sách trust, revocation và bằng chứng thời gian**. Phối hợp **mật mã đối xứng/bất đối xứng, KMS/HSM, envelope encryption, IAM, cryptoperiod, key lifecycle và kiểm toán** giúp thu hồi khóa thực sự bảo vệ dữ liệu thay vì chỉ thay đổi một nhãn trạng thái.
