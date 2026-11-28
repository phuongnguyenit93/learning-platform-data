# Key provisioning pipeline: Tự động hóa cấp phát khóa mật mã

**Key provisioning pipeline** là quy trình có kiểm soát để tiếp nhận yêu cầu, xác thực chủ thể, kiểm tra chính sách, tạo hoặc nhập khóa, đăng ký metadata, cấp quyền sử dụng, phân phối thông tin cần thiết, kiểm tra và kích hoạt khóa. Pipeline biến việc cấp phát khóa thành một quy trình lặp lại được, có thể kiểm toán và có thể phục hồi khi một bước thất bại.

Trong quản lý khóa mật mã, cấp phát không chỉ là tạo một chuỗi byte ngẫu nhiên. Một khóa chỉ sẵn sàng cho ứng dụng khi thuật toán và mục đích đã được phê duyệt, khóa được tạo trong ranh giới bảo vệ phù hợp, quyền được cấp đúng principal, metadata được ghi nhận, bên sử dụng có thể truy cập theo policy và trạng thái được kích hoạt một cách nhất quán.

Pipeline có thể phục vụ nhiều loại tài sản: KEK trong KMS/HSM, DEK cho envelope encryption, cặp khóa ký, khóa TLS, khóa HMAC hoặc chứng thư PKI. Mỗi loại có cách tạo và phân phối khác nhau. Ví dụ, khóa riêng dùng ký thường nên ở lại HSM; khóa công khai có thể được phân phối rộng hơn; DEK có thể được trả một lần ở dạng rõ cho ứng dụng cùng bản đã wrap để lưu trữ.

## 1. Mục tiêu và phạm vi của key provisioning pipeline

Một pipeline tốt cần đạt các mục tiêu:

- **Đúng danh tính:** chỉ principal đã xác thực và được cấp quyền mới có thể yêu cầu tạo hoặc nhận khóa.
- **Đúng mục đích:** thuật toán, kích thước, purpose, môi trường và phạm vi dữ liệu phải phù hợp chính sách.
- **Bảo vệ key material:** tạo khóa trong KMS/HSM khi phù hợp; hạn chế export và tránh đưa khóa rõ vào log hoặc kho cấu hình.
- **Phân quyền tối thiểu:** ứng dụng chỉ nhận quyền thao tác cần thiết trên đúng khóa.
- **Nhất quán trạng thái:** metadata, policy, grant và trạng thái khóa phản ánh cùng một kết quả provisioning.
- **Có thể kiểm toán:** mỗi bước quan trọng có request ID, actor, thời điểm, kết quả và bằng chứng.
- **Có khả năng phục hồi:** retry không tạo nhiều khóa ngoài ý muốn; lỗi giữa chừng có cách bù trừ và đối soát.
- **Có thể vận hành lâu dài:** hỗ trợ rotate, revoke, disable, backup, recovery và destroy theo vòng đời.

Pipeline có thể chạy khi tạo môi trường, triển khai dịch vụ, onboarding tenant, tạo chứng thư hoặc khi ứng dụng yêu cầu DEK. Không nên dùng một quy trình giống hệt cho mọi loại khóa. Hãy xây dựng các bước chung rồi áp dụng profile theo loại khóa và mục đích.

## 2. Các loại khóa và cách cấp phát khác nhau

Trước khi thiết kế pipeline, cần phân biệt tài sản nào đang được cấp:

| Loại tài sản | Cách tạo thường gặp | Điều được phân phối |
|---|---|---|
| KEK trong KMS/HSM | Tạo trực tiếp bên trong KMS/HSM. | Key ID/handle và quyền gọi wrap/unwrap hoặc encrypt/decrypt. |
| DEK cho dữ liệu | Sinh ngẫu nhiên trong ứng dụng hoặc qua API GenerateDataKey của KMS. | DEK dạng rõ trong thời gian ngắn và bản DEK đã wrap để lưu cùng ciphertext. |
| Cặp khóa ký | Sinh trong HSM/KMS nếu private key cần không thể xuất. | Handle khóa riêng cho thao tác sign và public key/certificate để xác minh. |
| Khóa TLS | Sinh private key trong workload/HSM, sau đó gửi CSR đến CA; hoặc theo quy trình PKI được phê duyệt. | Private key được bảo vệ tại nơi tạo và certificate công khai. |
| HMAC key | Sinh bằng CSPRNG hoặc KMS/HSM. | Handle hoặc key material được cấp cho thành phần được phép MAC/verify. |
| Khóa nhập từ bên ngoài | Import qua quy trình kiểm soát, có kiểm tra nguồn và định dạng. | Key ID/handle cùng metadata và policy tương ứng. |

**CreateKey** và **GenerateDataKey** thường có mục đích khác nhau. CreateKey tạo một khóa quản lý lâu dài như KEK; GenerateDataKey tạo khóa dữ liệu dùng cho một đối tượng hoặc phiên mã hóa. Với envelope encryption, ứng dụng có thể nhận DEK dạng rõ để mã hóa dữ liệu, đồng thời nhận wrapped DEK để lưu trữ. Ứng dụng phải xóa bản DEK rõ sau khi hoàn tất tác vụ theo khả năng kiểm soát bộ nhớ.

Không phân phối private key chỉ vì ứng dụng cần ký. Nếu KMS/HSM hỗ trợ ký bằng key handle, hãy để thao tác ký diễn ra trong ranh giới bảo vệ và chỉ cấp quyền sign cho workload.

## 3. Kiến trúc tổng thể của pipeline

Một pipeline điển hình gồm các thành phần:

~~~text
Ứng dụng / Platform / Tenant onboarding
                |
                v
         Provisioning request
                |
                v
      Identity authentication
                |
                v
       Policy and approval gate
                |
                v
       Key generation/import
          KMS / HSM / PKI
                |
                v
       Metadata registration
                |
                v
       Grant / access binding
                |
                v
    Handle / certificate / wrapped key
                |
                v
       Validation and activation
                |
                v
       Audit + inventory + monitor
~~~

Orchestrator điều phối các bước và lưu trạng thái workflow. KMS/HSM hoặc CA thực hiện thao tác mật mã. Registry lưu metadata và quan hệ phụ thuộc. IAM hoặc key policy quyết định principal nào được thao tác. Audit pipeline lưu bằng chứng độc lập. Ứng dụng chỉ nhận thông tin cần để sử dụng khóa.

Pipeline không nên trở thành một thành phần có quyền vô hạn. Tài khoản orchestrator cần được giới hạn theo loại khóa, môi trường, thao tác và phạm vi tài nguyên. Nếu một workflow có quyền tạo, cấp quyền, export và hủy mọi khóa, việc chiếm quyền orchestrator có thể ảnh hưởng toàn bộ hệ thống.

## 4. Mô hình trạng thái provisioning

Mỗi yêu cầu cần có trạng thái rõ ràng để vận hành và phục hồi. Tên trạng thái cụ thể có thể khác nhau, nhưng mô hình logic có thể gồm:

| Trạng thái | Ý nghĩa |
|---|---|
| REQUESTED | Yêu cầu đã được tiếp nhận và có request ID. |
| VALIDATING | Đang xác thực principal, kiểm tra input và policy. |
| APPROVAL_PENDING | Đang chờ phê duyệt nếu loại khóa yêu cầu approval. |
| GENERATING | KMS/HSM/CA đang tạo hoặc nhập khóa. |
| GENERATED | Backend trả về key ID hoặc handle. |
| REGISTERING | Đang ghi metadata và quan hệ sở hữu. |
| GRANTING | Đang cấp quyền cho workload hoặc role. |
| DISTRIBUTING | Đang phân phối handle, public key, certificate hoặc wrapped key. |
| VERIFYING | Đang kiểm tra thuộc tính, quyền và khả năng sử dụng. |
| ACTIVE | Khóa đã sẵn sàng theo policy và được phép dùng. |
| FAILED | Một bước không thể hoàn tất; cần xử lý hoặc retry. |
| COMPENSATING | Đang thu hồi grant, disable hoặc xử lý tài nguyên tạo dở. |
| CANCELLED | Workflow đã được hủy trước khi kích hoạt. |

Không chuyển sang ACTIVE chỉ vì API tạo khóa trả về thành công. Cần xác nhận metadata, quyền, policy và đầu ra đã được lưu đúng. Tương tự, trạng thái FAILED không có nghĩa tài nguyên đã tự biến mất: backend có thể đã tạo khóa trước khi một bước sau thất bại.

Mọi chuyển trạng thái nên ghi nhận thời điểm, actor hoặc service identity, request ID, kết quả và lỗi đã được chuẩn hóa. Trạng thái hiện tại cần có thể đối chiếu với backend thay vì chỉ tin vào bản ghi trong orchestrator.

## 5. Bước 1: Tiếp nhận và chuẩn hóa yêu cầu

Yêu cầu provisioning cần chứa đủ thuộc tính để policy engine quyết định. Một request có thể bao gồm:

- Chủ sở hữu nghiệp vụ và owner kỹ thuật.
- Principal hoặc workload identity sẽ dùng khóa.
- Mục đích: encrypt, decrypt, sign, verify, wrap, unwrap hoặc MAC.
- Loại khóa: symmetric, asymmetric, HMAC, KEK, DEK hoặc TLS/PKI.
- Thuật toán, key size, đường cong hoặc tham số được yêu cầu.
- Môi trường: development, test, staging hoặc production.
- Tenant, application, data classification và phạm vi tài nguyên.
- Yêu cầu exportability, backup, recovery và vị trí KMS/HSM.
- Cryptoperiod, TTL hoặc ngày hết hiệu lực nếu áp dụng.
- Request ID/idempotency key, lý do và change/approval reference.

Không nên cho caller tự chọn tùy ý thuật toán hoặc key size. Caller có thể nêu nhu cầu, nhưng pipeline phải đối chiếu với allowlist và profile đã phê duyệt. Các trường như owner, tenant và environment cần được lấy hoặc xác minh từ danh tính và hệ thống quản lý tài nguyên, không chỉ tin giá trị do client gửi.

Ví dụ request logic:

~~~yaml
request:
  request_id: req-2026-00421
  owner: payments-platform
  principal: service:invoice-api
  environment: production
  tenant: tenant-042
  key_profile: invoice-signing-rsa3072
  purpose: sign
  exportable: false
  approval_ref: change-2026-1182
~~~

Đây là cấu trúc minh họa. Cấu hình thực tế cần schema validation, giới hạn độ dài, allowlist enum và xác thực nguồn của từng thuộc tính.

## 6. Bước 2: Xác thực principal và kiểm tra policy

Trước khi tạo khóa, pipeline phải xác thực bên yêu cầu. Các cơ chế thường gặp gồm workload identity, cloud identity, service account, chứng thư mTLS hoặc token ngắn hạn. Tránh nhúng một token quản trị dài hạn trong source code hoặc container image để bootstrap mọi yêu cầu.

Sau authentication là authorization. Policy engine cần kiểm tra:

1. Principal có được yêu cầu tạo loại khóa này không?
2. Principal có thuộc owner hoặc tenant được chỉ định không?
3. Mục đích và môi trường có nằm trong phạm vi được phép không?
4. Thuật toán, kích thước và tham số có thuộc allowlist không?
5. Yêu cầu export, backup và recovery có được phép không?
6. Có cần approval độc lập hoặc dual control không?
7. Quota, giới hạn số lượng khóa và giới hạn tốc độ có bị vượt không?

Áp dụng default deny. Không cấp quyền tạo production key chỉ vì một workload có quyền đọc secret thông thường. Quyền tạo khóa, cấp grant, export và destroy cần được phân tách theo vai trò.

### Phê duyệt theo mức rủi ro

Không phải mọi yêu cầu đều cần người phê duyệt. Một DEK ngắn hạn cho workload đã được xác thực có thể đi theo policy tự động. Khóa ký phát hành, CA key, KEK production hoặc yêu cầu import/export có thể cần change approval, hai người phê duyệt hoặc quy trình quản trị đặc biệt.

Approval cần gắn với đúng key profile, owner, purpose, environment và request ID. Không tái sử dụng một approval chung cho yêu cầu khác hoặc thay đổi thuộc tính sau khi đã phê duyệt.

## 7. Bước 3: Sinh hoặc import khóa trong ranh giới phù hợp

Khi policy cho phép, pipeline gọi KMS/HSM/PKI để tạo khóa. Với khóa phần mềm, dùng CSPRNG và API chuẩn như SecureRandom, KeyGenerator hoặc KeyPairGenerator. Với khóa quan trọng, ưu tiên sinh bên trong HSM/KMS để private key hoặc KEK không phải xuất vào heap ứng dụng.

Các kiểm soát cần có:

- Chọn provider, thiết bị hoặc KMS endpoint được phê duyệt.
- Chỉ định thuật toán, key size, curve, usage và exportability.
- Xác nhận khóa được sinh từ nguồn ngẫu nhiên mật mã phù hợp.
- Kiểm tra backend trả key ID/handle hợp lệ và thuộc đúng account/project/partition.
- Không log key bytes, private key, DEK dạng rõ hoặc response chứa key material.
- Nếu import, xác minh nguồn, định dạng, checksum/manifest theo quy trình và quyền import.
- Ghi nhận provider, HSM partition hoặc key store location khi metadata được phép lưu.

### Ví dụ với khóa đối xứng và envelope encryption

Một ứng dụng cần mã hóa một hồ sơ có thể gọi KMS để tạo DEK gắn với KEK:

~~~text
Application -> KMS: GenerateDataKey(KEK, AES-256)
KMS -> Application: plaintext DEK + wrapped DEK
Application: encrypt record with plaintext DEK
Application: store ciphertext + wrapped DEK + key metadata
Application: clear plaintext DEK buffer
~~~

Wrapped DEK được lưu cùng ciphertext để sau này KMS có thể mở gói theo policy. Plaintext DEK chỉ tồn tại trong thời gian cần thiết và chỉ trong workload được phép. Khi đọc dữ liệu, ứng dụng gửi wrapped DEK đến KMS để unwrap, sau đó dùng DEK trong bộ nhớ để giải mã.

### Ví dụ với cặp khóa ký

Với khóa ký production, pipeline yêu cầu KMS/HSM tạo cặp khóa với usage sign. Private key ở lại thiết bị; ứng dụng nhận key ID/handle để gọi sign. Public key được xuất để tạo certificate hoặc phân phối cho bên xác minh. Không gửi private key qua secret manager nếu có thể dùng thao tác ký từ xa.

## 8. Bước 4: Đăng ký metadata và inventory

Sau khi backend tạo khóa, pipeline cần ghi metadata vào registry hoặc inventory. Metadata giúp tìm owner, mục đích, trạng thái và các phụ thuộc mà không cần đọc key material.

Các trường thường cần:

| Trường | Mục đích |
|---|---|
| key_id / alias | Định danh backend và tên tra cứu. |
| version | Phiên bản khóa hoặc version đang hoạt động. |
| algorithm / key_size | Thuật toán và kích thước. |
| purpose / usage | Mục đích được phép. |
| owner / principal | Chủ sở hữu và workload được dùng khóa. |
| tenant / environment | Phạm vi dữ liệu và môi trường. |
| provider / location | KMS, HSM partition hoặc provider. |
| exportable | Khóa có thể xuất hay không theo metadata backend. |
| created_at / activated_at | Mốc thời gian trong vòng đời. |
| cryptoperiod / expires_at | Thời hạn sử dụng hoặc ngày rà soát. |
| status | Trạng thái provisioning và trạng thái backend. |
| approval_ref / request_id | Liên kết quy trình và bằng chứng phê duyệt. |
| dependencies | DEK, KEK, certificate, service hoặc dữ liệu phụ thuộc. |

Không lưu raw key material, private key, password hoặc plaintext DEK vào inventory. Nếu cần public key hoặc certificate, có thể lưu bản công khai cùng fingerprint và nguồn phát hành. Registry cần có quyền ghi hạn chế, lịch sử thay đổi và khả năng đối soát với KMS/HSM.

Metadata cần được ghi bền vững trước khi workflow công bố khóa ở trạng thái ACTIVE. Nếu backend tạo khóa thành công nhưng ghi metadata thất bại, pipeline phải đánh dấu tài nguyên ở trạng thái chưa hoàn tất và có cách tìm/đối soát khóa mồ côi.

## 9. Bước 5: Cấp quyền và ràng buộc principal

Sau khi đăng ký metadata, pipeline cấp quyền cho workload. Quyền phải giới hạn theo key ID, thao tác và ngữ cảnh. Ví dụ:

- Dịch vụ invoice được sign bằng khóa ký invoice.
- Dịch vụ xác minh chỉ được lấy public key và verify.
- Dịch vụ lưu trữ được encrypt hoặc decrypt dữ liệu của tenant đã được giao.
- Dịch vụ quản lý KEK được wrap/unwrap DEK nhưng không đọc dữ liệu nghiệp vụ.
- Auditor chỉ được xem metadata và audit event.

Không cấp quyền quản trị cho ứng dụng chỉ để nó có thể dùng khóa. Tách data plane khỏi control plane: ứng dụng thực hiện thao tác nghiệp vụ, còn quyền grant, đổi policy, import/export, disable và destroy thuộc nhóm quản trị riêng.

Nếu nền tảng hỗ trợ grant tạm thời, hãy đặt thời hạn và giới hạn operation. Với quyền dài hạn, có quy trình rà soát định kỳ và thu hồi khi workload ngừng hoạt động hoặc đổi owner.

## 10. Bước 6: Phân phối thông tin cần thiết

Pipeline không nhất thiết phân phối key material. Loại dữ liệu được trả cho caller phụ thuộc loại khóa:

| Loại khóa | Đầu ra phù hợp |
|---|---|
| KEK không exportable | Key ID/handle và quyền gọi KMS/HSM. |
| Private signing key không exportable | Key ID/handle để ký từ xa; public key/certificate để xác minh. |
| DEK trong envelope encryption | Plaintext DEK trong thời gian ngắn và wrapped DEK để lưu trữ. |
| Public verification key | Public key hoặc certificate qua kênh phân phối tin cậy. |
| TLS credential | Certificate và tham chiếu private key được bảo vệ tại nơi sinh. |
| HMAC key | Handle hoặc key material chỉ đến workload cần dùng, tùy thiết kế và provider. |

Kênh phân phối phải xác thực hai chiều khi cần, mã hóa khi truyền và giới hạn quyền đọc. Không đưa private key hoặc plaintext DEK vào biến cấu hình lâu dài, source code, image, log, ticket hoặc artifact CI/CD.

Nếu bắt buộc chuyển key material, cần có quy trình riêng: xác minh người nhận, bảo vệ kênh, mã hóa wrapping, kiểm soát bản sao, giới hạn thời gian lưu, xác nhận nhận và hủy bản tạm. Việc export phải được phê duyệt theo key policy.

## 11. Bước 7: Kiểm tra trước khi kích hoạt

Trước khi đánh dấu ACTIVE, pipeline nên xác minh:

- Key ID, version và owner khớp request.
- Thuật toán, key size, usage và exportability khớp profile.
- Trạng thái backend là usable/enabled theo semantics của nền tảng.
- Policy và grant đã gắn đúng principal, key ID và operation.
- Caller không thể thực hiện thao tác ngoài phạm vi.
- Caller thực hiện được thao tác cần thiết trong môi trường kiểm thử phù hợp.
- Public key/certificate có fingerprint và chuỗi tin cậy hợp lệ nếu có.
- Metadata đã được ghi và liên kết với request/approval.
- Audit event của các bước quan trọng đã được tiếp nhận hoặc có cơ chế đối soát.

Self-test phải tránh tạo tác dụng phụ hoặc làm lộ dữ liệu. Ví dụ, với khóa ký có thể ký một challenge ngẫu nhiên rồi xác minh bằng public key; với khóa mã hóa có thể kiểm tra encrypt/decrypt trên dữ liệu thử không nhạy cảm. Không ghi challenge chứa bí mật hoặc key material vào log.

Khi kiểm tra quyền, phải thử cả trường hợp được phép và bị từ chối. Một bài test chỉ chứng minh sign thành công chưa chứng minh principal không thể export private key hoặc gọi decrypt trái phép.

## 12. Bước 8: Kích hoạt và công bố trạng thái

Sau khi các bước trước thành công, pipeline cập nhật trạng thái ACTIVE trong registry và thông báo cho bên yêu cầu. Việc kích hoạt cần có tính nhất quán:

1. Backend key đã được tạo và enabled.
2. Metadata đã được ghi.
3. Grant/policy đã được áp dụng.
4. Thông tin cần thiết đã được phân phối.
5. Kiểm tra đã PASS.
6. Audit event và request status đã được cập nhật.

Nếu một bước thất bại, không công bố khóa là ACTIVE. Tùy loại khóa, pipeline có thể disable key, revoke grant hoặc giữ trạng thái generated/pending để xử lý. Không nên tự động destroy ngay mọi khóa tạo dở: hủy có thể không đảo ngược và cần theo policy, đặc biệt nếu backend có recovery window hoặc khóa đã được tham chiếu.

## 13. Idempotency, retry và xử lý lỗi giữa chừng

Provisioning là workflow nhiều bước và có thể gặp timeout sau khi backend đã thực hiện thao tác. Ví dụ, KMS tạo khóa thành công nhưng response bị mất; orchestrator retry và vô tình tạo thêm khóa. Vì vậy cần thiết kế idempotency và reconciliation.

### Idempotency

- Mỗi request có ID duy nhất hoặc idempotency key.
- Lưu trạng thái và kết quả theo request ID trước khi gọi backend.
- Nếu backend hỗ trợ idempotency token, truyền cùng token khi retry.
- Nếu không hỗ trợ, tìm tài nguyên đã tạo theo correlation metadata trước khi tạo lại.
- Không coi timeout là thất bại chắc chắn; truy vấn backend để xác định kết quả.
- Chặn hai workflow đồng thời xử lý cùng request hoặc cùng logical key.

### Retry

Retry chỉ phù hợp với lỗi tạm thời như throttling, network timeout hoặc backend unavailable. Dùng exponential backoff có jitter và giới hạn số lần thử. Không retry vô hạn với lỗi policy, invalid parameter hoặc approval bị từ chối.

### Compensation

Không có transaction phân tán nguyên tử giữa KMS, registry, IAM và secret delivery. Pipeline thường cần mô hình saga với hành động bù trừ:

| Lỗi | Hành động bù trừ có thể áp dụng |
|---|---|
| Tạo khóa thành công, ghi metadata thất bại | Đưa key ID vào hàng đợi reconciliation; disable hoặc giữ pending theo policy. |
| Metadata thành công, cấp grant thất bại | Giữ trạng thái chưa active; retry grant hoặc thu hồi metadata workflow. |
| Grant thành công, phân phối thất bại | Thu hồi grant nếu không còn cần; giữ khóa pending để xử lý. |
| Phân phối thành công, validation thất bại | Ngừng cấp quyền mới, revoke grant và disable theo mức rủi ro. |
| Audit sink không khả dụng | Không bỏ qua audit; lưu outbox bền vững và retry theo policy trước khi hoàn tất. |

Hành động bù trừ cần idempotent. Trước khi disable hoặc destroy, xác minh khóa chưa được một workflow khác kích hoạt hoặc tham chiếu hợp lệ.

## 14. Reconciliation và phát hiện drift

Ngay cả pipeline có retry cũng có thể để lại khác biệt giữa registry, IAM và backend. Reconciliation là công việc định kỳ so sánh trạng thái mong muốn với trạng thái thực tế.

Các trường hợp cần phát hiện:

- KMS có key ID nhưng registry không có metadata tương ứng.
- Registry ghi ACTIVE nhưng backend key đang disabled hoặc pending deletion.
- Backend policy có principal ngoài danh sách đã phê duyệt.
- Grant đã hết hạn nhưng chưa được thu hồi.
- Key version mới đã tạo nhưng ứng dụng vẫn dùng version cũ ngoài kế hoạch.
- Key không còn owner hoặc không có purpose rõ ràng.
- Backup/replica chưa được ghi nhận trong inventory.
- Một request ở trạng thái pending quá lâu.

Reconciliation không nên tự động xóa tài nguyên không rõ nguồn gốc. Trước khi sửa drift, cần phân loại nguyên nhân, kiểm tra owner và tạo audit event. Với thay đổi có thể gây mất dữ liệu, yêu cầu approval hoặc chế độ dry-run.

## 15. Tích hợp pipeline với CI/CD và Infrastructure as Code

CI/CD có thể tự động tạo role, key policy, KMS alias, audit subscription và quyền workload. Tuy nhiên, pipeline triển khai hạ tầng và pipeline cấp phát khóa runtime có mục đích khác nhau:

- **Infrastructure as Code:** định nghĩa cấu hình mong muốn, policy, role, network và tài nguyên nền tảng.
- **Runtime provisioning:** tạo key instance hoặc DEK khi workload, tenant hay tác vụ cần.
- **Key lifecycle automation:** rotate, disable, revoke, backup và destroy theo lịch hoặc sự kiện.

Không lưu secret hoặc private key trong repository, state file IaC, build log hay artifact. State của IaC có thể chứa giá trị nhạy cảm nếu module trả key material hoặc secret output; cần thiết kế output chỉ chứa key ID/handle và metadata công khai.

Với production, áp dụng review cho thay đổi key policy, tách quyền deploy khỏi quyền destroy, dùng approval gate cho thao tác rủi ro cao và lưu audit event độc lập với CI runner. Runner không nên có quyền export hoặc destroy mọi khóa chỉ vì nó có quyền triển khai ứng dụng.

## 16. Xoay vòng khóa và liên kết với provisioning

Rotation tạo phiên bản khóa mới hoặc thay khóa cũ theo cryptoperiod, sự kiện lộ khóa hoặc thay đổi thuật toán. Provisioning pipeline cung cấp cơ chế tạo và đăng ký khóa mới; rotation workflow điều phối chuyển đổi và kết thúc phiên bản cũ.

Một quy trình rotation có thể:

1. Tạo version mới theo profile hiện hành.
2. Kiểm tra metadata, policy, quyền và khả năng sử dụng.
3. Cập nhật ứng dụng hoặc alias để dùng version mới cho dữ liệu mới.
4. Duy trì khả năng giải mã/xác minh dữ liệu cũ bằng version cũ trong thời gian chuyển tiếp.
5. Rewrap DEK hoặc re-encrypt dữ liệu khi cần.
6. Theo dõi tỷ lệ sử dụng version cũ và xác nhận không còn phụ thuộc.
7. Disable, revoke hoặc destroy version cũ theo key policy.

Không được xóa version cũ ngay sau khi version mới ACTIVE nếu dữ liệu, chữ ký, backup hoặc client vẫn cần nó. Rotation và destruction phải có trạng thái, audit và phê duyệt phù hợp.

## 17. Ví dụ điều phối provisioning bằng Java

Ví dụ sau minh họa ranh giới giữa orchestrator, KMS và metadata registry. Đây là API trừu tượng do ứng dụng định nghĩa, không phải API chuẩn của JDK hay một nhà cung cấp KMS cụ thể.

~~~java
import java.util.Objects;

public final class KeyProvisioningService {
    private final PolicyService policyService;
    private final KeyBackend keyBackend;
    private final KeyRegistry registry;
    private final GrantService grantService;
    private final AuditPublisher auditPublisher;

    public KeyProvisioningService(
            PolicyService policyService,
            KeyBackend keyBackend,
            KeyRegistry registry,
            GrantService grantService,
            AuditPublisher auditPublisher) {
        this.policyService = policyService;
        this.keyBackend = keyBackend;
        this.registry = registry;
        this.grantService = grantService;
        this.auditPublisher = auditPublisher;
    }

    public ProvisionedKey provision(ProvisionRequest request)
            throws Exception {
        Objects.requireNonNull(request, "request");
        policyService.validate(request);
        auditPublisher.publishRequested(request);

        KeyHandle handle = keyBackend.create(
                request.idempotencyKey(),
                request.keyProfile());

        boolean registered = false;
        boolean granted = false;
        try {
            KeyMetadata metadata =
                    KeyMetadata.from(request, handle);
            registry.register(metadata);
            registered = true;

            grantService.grant(
                    handle.keyId(),
                    request.principal(),
                    request.allowedOperations());
            granted = true;

            keyBackend.verifyUsable(
                    handle,
                    request.allowedOperations());
            registry.activateWithAuditOutbox(
                    handle.keyId(), request.idempotencyKey());

            return new ProvisionedKey(
                    handle.keyId(), handle.version());
        } catch (Exception failure) {
            if (granted) {
                grantService.revokeBestEffort(handle.keyId(),
                        request.principal());
            }
            if (registered) {
                registry.markProvisioningFailed(handle.keyId());
            }
            keyBackend.disableBestEffort(handle);
            auditPublisher.publishFailed(
                    request, handle, failure.getClass().getSimpleName());
            throw failure;
        }
    }

    public record ProvisionRequest(
            String idempotencyKey,
            String principal,
            String owner,
            String keyProfile,
            String purpose,
            String environment,
            java.util.Set<String> allowedOperations) {
    }

    public record KeyHandle(String keyId, String version) {
    }

    public record KeyMetadata(
            String keyId,
            String version,
            String owner,
            String purpose,
            String environment) {
        static KeyMetadata from(
                ProvisionRequest request, KeyHandle handle) {
            return new KeyMetadata(
                    handle.keyId(),
                    handle.version(),
                    request.owner(),
                    request.purpose(),
                    request.environment());
        }
    }

    public record ProvisionedKey(String keyId, String version) {
    }

    public interface PolicyService {
        void validate(ProvisionRequest request) throws Exception;
    }

    public interface KeyBackend {
        KeyHandle create(String idempotencyKey, String profile)
                throws Exception;
        void verifyUsable(
                KeyHandle handle,
                java.util.Set<String> operations) throws Exception;
        void disableBestEffort(KeyHandle handle);
    }

    public interface KeyRegistry {
        void register(KeyMetadata metadata) throws Exception;
        void activateWithAuditOutbox(
                String keyId, String requestId) throws Exception;
        void markProvisioningFailed(String keyId);
    }

    public interface GrantService {
        void grant(
                String keyId,
                String principal,
                java.util.Set<String> operations) throws Exception;
        void revokeBestEffort(String keyId, String principal);
    }

    public interface AuditPublisher {
        void publishRequested(ProvisionRequest request) throws Exception;
        void publishFailed(
                ProvisionRequest request,
                KeyHandle handle,
                String reason);
    }
}
~~~

Ví dụ dùng record nên yêu cầu JDK 16 trở lên. Các interface như KeyBackend, KeyRegistry và GrantService là abstraction do ứng dụng định nghĩa; implementation thực tế phải ánh xạ chúng tới API của KMS/HSM và hệ thống IAM đang dùng.

Đây là skeleton để minh họa trách nhiệm của từng thành phần. Production cần bổ sung schema validation, xác thực principal từ security context, approval, owner/purpose/environment lấy từ nguồn tin cậy, lưu workflow bền vững, idempotency, timeout, retry và xử lý lỗi của từng hành động bù trừ. Phương thức activateWithAuditOutbox biểu thị thao tác cập nhật trạng thái ACTIVE và ghi audit event vào transactional outbox trong cùng transaction của registry; worker riêng sẽ chuyển event ra audit sink và retry khi cần. Không dùng skeleton này như mã production nguyên trạng.

## 18. Kiểm thử pipeline

Kiểm thử không chỉ xác nhận khóa được tạo. Cần xác nhận cả đường thành công, đường từ chối và tình huống lỗi:

| Nhóm kiểm thử | Kịch bản |
|---|---|
| Input validation | Thiếu owner, purpose, environment hoặc profile không hợp lệ. |
| Authentication | Principal hết hạn, sai chữ ký, workload identity không hợp lệ. |
| Authorization | Caller yêu cầu key profile hoặc operation ngoài phạm vi. |
| Policy | Thuật toán, key size, exportability hoặc TTL không được phép. |
| Approval | Thiếu approval, approval hết hạn hoặc không khớp request. |
| Backend | KMS throttling, timeout, HSM unavailable, tạo khóa thành công nhưng mất response. |
| Registry | Metadata write lỗi, duplicate key ID hoặc database unavailable. |
| Grant | Cấp quyền thất bại, quyền cấp sai principal hoặc quyền rộng hơn request. |
| Distribution | Mất kết nối, certificate sai, wrapped key không đọc được. |
| Validation | Key không usable, thuật toán không tương thích hoặc thao tác bị từ chối. |
| Retry/idempotency | Cùng request gửi nhiều lần hoặc hai worker xử lý đồng thời. |
| Compensation | Revoke grant hoặc disable thất bại; workflow phải giữ trạng thái cần xử lý. |
| Reconciliation | Key mồ côi, metadata lệch backend hoặc grant không còn owner. |

Trong kiểm thử, dùng khóa và dữ liệu thử nghiệm. Không dùng private key production hoặc dữ liệu nhạy cảm thật để kiểm tra pipeline. Kiểm tra cả log và trace để bảo đảm key material không bị ghi ra ngoài.

## 19. Chỉ số vận hành và cảnh báo

Các chỉ số giúp đánh giá pipeline có ổn định và an toàn hay không:

- Số yêu cầu provisioning theo profile, principal, tenant và môi trường.
- Tỷ lệ thành công/thất bại theo từng bước.
- Thời gian từ request đến ACTIVE, tách riêng thời gian approval và backend.
- Tỷ lệ retry, timeout, throttling và idempotency conflict.
- Số key resource được tạo nhưng chưa đăng ký hoặc chưa kích hoạt.
- Số grant tồn tại nhưng không có metadata owner tương ứng.
- Số request pending quá SLA hoặc stuck ở một trạng thái.
- Số lần policy deny và số yêu cầu vượt quota.
- Số khóa không có owner, purpose hoặc cryptoperiod.
- Số event audit bị trễ hoặc không được gửi.

Đặt cảnh báo khi một principal tạo số lượng khóa bất thường, một profile production bị gọi từ môi trường không hợp lệ, provisioning thất bại hàng loạt, grant vượt phạm vi, hoặc có key resource mồ côi. Tránh đưa secret hoặc key material vào metric label.

## 20. Những sai lầm thường gặp

**Coi tạo khóa là hoàn tất provisioning.** Khóa chưa có metadata, policy và quyền đúng vẫn chưa sẵn sàng cho workload. Cần một trạng thái ACTIVE chỉ sau validation.

**Để caller tự chọn thuật toán và key size.** Request có thể bị lạm dụng để tạo tham số yếu hoặc không tương thích. Dùng profile được phê duyệt và policy gate.

**Xuất private key để dễ phân phối.** Điều này mở rộng số nơi có key material. Ưu tiên key handle và thao tác ký/giải mã từ xa trong KMS/HSM.

**Ghi key material vào log hoặc CI artifact.** Log, trace và build artifact thường có quyền truy cập rộng và thời gian lưu dài. Chỉ ghi key ID, request ID và metadata cần thiết.

**Không dùng idempotency.** Retry sau timeout có thể tạo nhiều khóa. Gắn request ID và đối soát backend trước khi tạo lại.

**Không có compensation.** Lỗi sau khi tạo khóa có thể để lại key resource hoặc grant mồ côi. Xác định hành động bù trừ và trạng thái chờ xử lý.

**Cấp quyền quản trị cho workload.** Ứng dụng chỉ cần sign hoặc decrypt nhưng được grant, export và destroy. Tách data plane/control plane.

**Kích hoạt trước khi kiểm tra.** Khóa có thể được dùng với sai principal hoặc sai thuật toán. Kiểm tra metadata, policy và thao tác allow/deny trước ACTIVE.

**Xóa khóa tạo dở ngay lập tức.** Hành động destroy có thể không đảo ngược hoặc ảnh hưởng workflow khác. Xác minh dependency và thực hiện theo quy trình hủy.

**Không đối soát registry với KMS/HSM.** Metadata cũ hoặc key mồ côi có thể tồn tại lâu dài. Chạy reconciliation định kỳ và xử lý drift có approval.

## 21. Checklist triển khai Key provisioning pipeline

- [ ] Request có ID duy nhất, owner, principal, purpose, profile và environment.
- [ ] Principal được xác thực bằng workload identity hoặc cơ chế tin cậy.
- [ ] Policy gate kiểm tra thuật toán, key size, usage, exportability và approval.
- [ ] Khóa được sinh trong KMS/HSM hoặc bằng CSPRNG/provider được phê duyệt.
- [ ] Phân biệt KEK, DEK, khóa ký, khóa TLS và HMAC để chọn cách cấp phát.
- [ ] Metadata được đăng ký mà không chứa key material.
- [ ] Grant giới hạn theo principal, key ID, operation, tenant và environment.
- [ ] Chỉ phân phối handle, public key/certificate hoặc wrapped key khi phù hợp.
- [ ] Có validation trước khi chuyển sang ACTIVE.
- [ ] Workflow có state machine, idempotency, retry và compensation.
- [ ] Có reconciliation để tìm key mồ côi, grant thừa và drift trạng thái.
- [ ] CI/CD không lưu secret hoặc private key trong source, state, log hay artifact.
- [ ] Rotation và destruction được điều phối theo vòng đời riêng.
- [ ] Audit event và metric bao phủ từng bước quan trọng.
- [ ] Đã kiểm thử lỗi backend, timeout, duplicate request, policy deny và phục hồi.

Key provisioning pipeline đưa việc cấp phát khóa vào một quy trình có danh tính, policy, metadata, quyền sử dụng, xác minh và kiểm toán rõ ràng. Tự động hóa chỉ thực sự an toàn khi pipeline kiểm soát được toàn bộ trạng thái từ yêu cầu đến kích hoạt, xử lý được lỗi giữa chừng và đối soát được tài nguyên thực tế với inventory. Nhờ vậy, khóa được tạo đúng mục đích, cấp đúng workload và sẵn sàng cho các bước sử dụng, xoay vòng, thu hồi và hủy trong vòng đời quản lý khóa.
