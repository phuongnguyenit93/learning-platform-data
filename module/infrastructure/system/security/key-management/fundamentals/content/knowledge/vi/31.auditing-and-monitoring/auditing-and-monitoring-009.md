# Unexpected export

**Unexpected export** là tình huống vật liệu khóa hoặc bản sao có khả năng dẫn đến việc sử dụng khóa được đưa ra khỏi nơi quản lý, ranh giới bảo vệ hoặc quy trình đã được phê duyệt ngoài dự kiến. Việc export có thể xảy ra qua KMS, HSM, Java KeyStore, công cụ backup, API quản trị, pipeline triển khai hoặc thao tác thủ công. Rủi ro cao nhất thường xuất hiện khi private key hoặc secret key được xuất ở dạng plaintext, nhưng cả bản export đã wrap, file keystore được mã hóa và thao tác export public key cũng cần được ghi nhận theo đúng mục đích và ngữ cảnh.

Một event export không tự động chứng minh đã xảy ra compromise. Có thể đó là backup, migration, key ceremony hoặc hoạt động DR hợp lệ. Tuy nhiên, mọi lần export phải có danh tính, key ID/version, loại vật liệu, đích đến, phương thức bảo vệ, policy decision và approval phù hợp. Khi một export không có trong lịch thay đổi, đi tới destination lạ hoặc được thực hiện bởi principal bất thường, tổ chức cần coi đó là tín hiệu cần điều tra.

Bài học thuộc phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chương **Audit và monitoring**. Nội dung kết nối unexpected export với vòng đời khóa: tạo, cấp phát, lưu trữ, sử dụng, backup, restore, xoay vòng, thu hồi và hủy; đồng thời xét mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, kiểm soát truy cập và kiểm toán.

## 1. Export khóa là gì?

Export khóa là hành động tạo hoặc chuyển một biểu diễn của khóa ra khỏi backend hoặc vùng lưu trữ đang quản lý nó. Tùy hệ thống, biểu diễn đó có thể là:

- Vật liệu khóa ở dạng plaintext, ví dụ private key hoặc secret key bytes.
- Vật liệu khóa đã được bọc (wrapped) bằng một wrapping key khác.
- File container như PKCS#12/PFX chứa private key và certificate.
- Backup package hoặc clone package do HSM/KMS tạo.
- Key object/handle được chuyển sang một hệ thống hoặc provider khác.
- Public key hoặc certificate được xuất để phân phối.

Các loại export này có mức rủi ro khác nhau. Export public key thường là hoạt động bình thường; export private key hoặc symmetric key ở dạng rõ có thể phá vỡ ranh giới bảo vệ quan trọng. Wrapped key vẫn là tài sản nhạy cảm vì nó có thể bị mở bọc nếu kẻ tấn công lấy được wrapping key hoặc quyền gọi dịch vụ unwrap.

Không đồng nhất export khóa với export dữ liệu đã mã hóa. Tải một ciphertext object không đồng nghĩa private key đã bị xuất. Ngược lại, một file backup chứa wrapped DEK có thể là key export dù không có plaintext dữ liệu.

## 2. Phân biệt các loại export

| Loại | Nội dung được đưa ra | Rủi ro chính | Kiểm soát thường cần |
|---|---|---|---|
| Plaintext private/secret key | Vật liệu khóa có thể sử dụng trực tiếp | Khóa có thể bị sao chép và dùng ngoài HSM/KMS | Mặc định cấm; ngoại lệ cần phê duyệt mạnh và bảo vệ end-to-end |
| Wrapped key | Khóa được mã hóa bằng wrapping key | Bị lộ package và có thể bị unwrap ở nơi khác | Kiểm soát wrapping key, destination, context và quyền unwrap |
| Encrypted keystore/container | Private key nằm trong file được bảo vệ bằng password/key | Password hoặc file có thể bị lộ; định dạng có thể mang nhiều entry | Mã hóa, tách password, giới hạn người nhận và audit |
| HSM backup/clone package | Dữ liệu backup theo cơ chế vendor | Có thể khôi phục khóa trong cùng security domain hoặc thiết bị tương thích | Quorum, backup domain, custody và quy trình restore |
| Public key/certificate | Dữ liệu khóa công khai và certificate | Thay thế/nhầm danh tính, phát tán certificate sai | Xác minh fingerprint, issuer và nguồn phân phối |
| Key handle/reference | Định danh hoặc tham chiếu đến khóa backend | Quyền truy cập theo handle có thể bị cấp sai | IAM, scope, expiry và audit consumer |

Khi thiết kế event schema, cần ghi loại export cụ thể. Một event chỉ có action=export không đủ để phân biệt public certificate download với private key plaintext export.

## 3. Vì sao unexpected export nguy hiểm?

Khi khóa rời khỏi vùng kiểm soát, các biện pháp bảo vệ ban đầu có thể không còn áp dụng. Ví dụ, private key được tạo non-exportable trong HSM có thể bị thay thế bằng một bản copy được tạo ở software store nếu có một quy trình import/export không được kiểm soát.

Hậu quả có thể gồm:

- Kẻ tấn công ký dữ liệu hoặc xác thực như chủ sở hữu private key.
- Giải mã dữ liệu lịch sử hoặc dữ liệu mới được bảo vệ bởi secret key.
- Mạo danh workload, service hoặc endpoint TLS.
- Giả mạo release, package hoặc artifact bằng code-signing key.
- Mở bọc DEK và truy cập dữ liệu trong nhiều backup.
- Duy trì quyền truy cập sau khi tài khoản nguồn đã bị khóa.
- Tạo bản sao khóa không được inventory, không được rotate hoặc không thể revoke tập trung.
- Làm mất bằng chứng về nơi khóa đã được sử dụng.

Một bản export có thể được tạo hợp lệ nhưng bị lưu sai nơi, gửi nhầm người hoặc giữ quá thời hạn. Vì vậy, kiểm soát cần bao phủ cả yêu cầu, phê duyệt, quá trình export, destination, custody, retention và destruction của bản sao.

## 4. Unexpected không đồng nghĩa với unauthorized

Một export có thể được authorization engine cho phép nhưng vẫn bất thường so với công việc thông thường. Ví dụ, một administrator có quyền export thực hiện thao tác ngoài change window, từ máy lạ hoặc gửi file tới storage cá nhân. Ngược lại, một request bị deny có thể là cấu hình sai hoặc dấu hiệu reconnaissance; chưa có vật liệu khóa nào được xuất.

Nên phân biệt:

- **Authorized and expected:** có quyền, có mục đích, đúng destination và đúng change/approval.
- **Authorized but unexpected:** policy cho phép nhưng hành vi khác baseline hoặc không có kế hoạch hợp lệ.
- **Unauthorized and denied:** request bị chặn; cần đánh giá ý đồ và nguồn request.
- **Unauthorized but completed:** export đã thành công ngoài policy; xử lý như sự cố nghiêm trọng.
- **Unknown outcome:** không xác định được export đã hoàn tất hay chưa do lỗi backend hoặc thiếu telemetry.

Không chỉ dựa vào trường outcome của một API. Cần xác minh event ở nguồn, trạng thái job, destination và việc file/object đã được tạo hay chưa.

## 5. Các nguồn có thể tạo ra export

Unexpected export có thể phát sinh từ nhiều đường:

- KMS API cho phép export hoặc wrap key.
- HSM management tool, vendor utility hoặc PKCS#11 operation.
- Java KeyStore API và công cụ keytool.
- Xuất file PKCS#12/PFX từ keystore hoặc certificate management console.
- Backup/restore, clone, migration hoặc disaster recovery workflow.
- CI/CD job tạo artifact chứa keystore hoặc private key.
- Script vận hành đọc key từ file rồi ghi ra thư mục khác.
- Cloud console, admin API hoặc support bundle.
- Secret manager export hoặc vault snapshot.
- Máy trạm quản trị, clipboard, temporary directory hoặc removable media.

Một số hệ thống không hỗ trợ export plaintext cho key loại nhất định. Điều đó không loại bỏ rủi ro từ backup package, wrapped export, quyền unwrap, file keystore khác hoặc một bản sao được tạo trước khi khóa được import vào backend.

## 6. Kiểm kê khả năng export của từng key

Mỗi key cần có metadata mô tả khả năng và chính sách export:

- Key ID và version.
- Key type: symmetric, private, public hoặc derived/data key.
- Algorithm, key size/curve và purpose.
- Backend: KMS, HSM, Java keystore, software provider hoặc OS store.
- Exportability: non-exportable, wrapped-only, exportable theo policy hoặc public-only.
- Wrapping key/backup domain được phép nếu có.
- Owner, consumer, environment và tenant.
- Quy trình phê duyệt, destination và retention được phép.
- Ngày tạo, cryptoperiod và trạng thái hiện tại.

Không suy ra exportability chỉ từ tên thuật toán hoặc tên provider. Khả năng export được quyết định bởi key attributes, backend, policy và API cụ thể. Một key object Java có thể là handle không chứa vật liệu export được; một file PKCS#12 có thể chứa private key có thể khôi phục.

## 7. Non-exportable, sensitive và extractable

Nhiều HSM hoặc PKCS#11 token hỗ trợ thuộc tính hạn chế khả năng trích xuất key. Trong PKCS#11, các thuộc tính như CKA_SENSITIVE và CKA_EXTRACTABLE có thể ảnh hưởng việc đọc hoặc export vật liệu khóa. Cách áp dụng và khả năng chuyển đổi thuộc tính phụ thuộc loại object, token và policy của thiết bị.

Các nguyên tắc:

- Tạo private key và secret key với thuộc tính non-extractable nếu use case cho phép.
- Giữ thuộc tính nhạy cảm theo policy của HSM.
- Chặn quyền export/unwrap không cần thiết.
- Kiểm tra thuộc tính thực tế sau khi tạo/import key.
- Không giả định import key đã tự động trở thành non-exportable.
- Audit mọi thay đổi thuộc tính hoặc policy liên quan exportability.

Non-exportable là một lớp kiểm soát quan trọng, nhưng không thay thế bảo vệ identity, quyền sử dụng key, audit, firmware, backup domain và quy trình operator.

## 8. Java KeyStore và rủi ro export

Java KeyStore cung cấp API để truy cập entry. Với một số loại keystore/provider, private key có thể được lấy bằng getKey hoặc getEntry nếu caller có quyền và cung cấp password phù hợp. Sau đó, key object có thể hỗ trợ encoding; trong trường hợp đó, getEncoded có thể trả về vật liệu khóa. Với key HSM non-exportable, object trả về có thể chỉ là handle và không cung cấp encoding.

Vì behavior phụ thuộc keystore type và provider:

- Không giả định mọi PrivateKey đều export được.
- Không gọi getEncoded chỉ để debug hoặc ghi log.
- Không ghi key bytes vào file tạm, artifact hoặc support bundle.
- Không chuyển private key ra software provider chỉ để giải quyết lỗi tương thích.
- Chỉ export khi có yêu cầu được phê duyệt và định dạng/destination đã xác định.
- Audit thao tác đọc entry, export và tạo keystore file theo khả năng quan sát của provider.

KeyStore.store có thể tạo một file chứa các entry và vật liệu khóa được bảo vệ theo định dạng keystore. Đây là thao tác cần kiểm soát như một lần tạo backup/export; không nên coi file đầu ra là dữ liệu cấu hình thông thường.

## 9. Public key export khác private key export

Public key thường được phân phối để bên khác xác minh chữ ký, mã hóa dữ liệu hoặc thiết lập trust. Certificate X.509 cũng thường được công bố rộng rãi. Tuy vậy, vẫn cần xác minh:

- Public key thuộc đúng subject/owner.
- Certificate có issuer, chain, validity và key usage phù hợp.
- Fingerprint hoặc serial khớp nguồn tin cậy.
- File không bị thay bằng public key của attacker.
- Hệ thống nhận không vô tình tin một certificate chỉ vì file được export từ một vị trí nội bộ.

Public key không cần giữ bí mật, nhưng tính toàn vẹn và binding với danh tính rất quan trọng. Một certificate công khai sai có thể khiến client tin nhầm endpoint hoặc xác minh sai danh tính.

## 10. Wrapped export và envelope encryption

Wrapped export đưa key ra khỏi backend dưới dạng ciphertext được bảo vệ bởi một wrapping key. Đây thường là cách cần thiết cho backup hoặc chuyển khóa giữa các hệ thống được phép.

Một luồng điển hình:

~~~mermaid
flowchart TD
    A["Key trong KMS/HSM"] --> B["Kiểm tra export policy"]
    B --> C{"Approval và destination hợp lệ?"}
    C -- "Không" --> D["Deny + audit + alert"]
    C -- "Có" --> E["Wrap bằng wrapping key được phép"]
    E --> F["Wrapped key package"]
    F --> G["Destination được kiểm soát"]
    G --> H["Restore/unwrap có approval"]
    H --> I["Key trong backend đích"]
    E --> J["Audit export event"]
    H --> K["Audit import/unwrap event"]
~~~

Wrapped key không phải plaintext, nhưng vẫn cần bảo vệ:

- Wrapping key phải nằm trong miền bảo vệ độc lập.
- Chỉ destination và principal được phê duyệt mới có quyền unwrap.
- Package cần integrity/authentication và metadata chống nhầm key.
- Phải ràng buộc key purpose, environment hoặc encryption context nếu backend hỗ trợ.
- Retention và destruction của wrapped package phải được quản lý.
- Audit cả wrap, export, transfer, import và unwrap.

Nếu wrapping key hoặc quyền unwrap bị compromise, wrapped package có thể trở thành bản sao sử dụng được. Không ghi nhận wrapped export như một hoạt động vô hại.

## 11. Các dấu hiệu unexpected export

Một export cần điều tra khi xuất hiện một hoặc nhiều dấu hiệu:

- Principal chưa từng export key trước đó.
- Export xảy ra ngoài change window hoặc lịch backup.
- User/service account vừa được cấp role export hoặc admin.
- Destination nằm ngoài danh sách storage/region/tenant được phê duyệt.
- Export từ workstation, IP, cluster hoặc workload mới.
- Export nhiều key hoặc nhiều version trong thời gian ngắn.
- Export key production từ môi trường development/test.
- Key được đánh dấu non-exportable nhưng xuất hiện event export thành công.
- Wrapped key được gửi đến wrapping key hoặc recipient không nằm trong inventory.
- File PKCS#12/PFX hoặc archive mới xuất hiện ở thư mục, repository hay artifact bất thường.
- Audit logging bị tắt, policy bị thay đổi hoặc event pipeline bị gián đoạn ngay trước export.
- Export xảy ra sau khi principal có dấu hiệu bị chiếm quyền hoặc token bất thường.

Không dùng một tín hiệu đơn lẻ để kết luận compromise. Kết hợp identity, key purpose, operation, destination, approval, baseline và trạng thái backend.

## 12. Audit event cho key export

Event export cần mô tả chính xác vật liệu và đường đi mà không chứa vật liệu khóa:

| Field | Ý nghĩa |
|---|---|
| eventId / eventTime | ID và thời điểm phát sinh |
| principalId / principalType | Người hoặc workload yêu cầu |
| keyId / keyVersion | Khóa được export |
| keyType / algorithm / purpose | Loại key và mục đích |
| exportType | plaintext, wrapped, keystore, backup package, public key |
| exportFormat | PKCS#8, PKCS#12, vendor package hoặc format khác nếu áp dụng |
| sourceBackend | KMS, HSM, keystore hoặc provider nguồn |
| destination | Resource/account/tenant/region/recipient được phép |
| wrappingKeyId | Wrapping key được dùng nếu là wrapped export |
| policyDecision | Allow/deny và policy version |
| approvalRef | Change, ticket, ceremony hoặc recovery approval |
| outcome | success, denied, failure hoặc unknown |
| requestId / jobId | ID nối với workflow, transfer và restore |
| retention | Thời hạn giữ bản export nếu có |

Không ghi key bytes, plaintext DEK, password bảo vệ file hoặc token có thể sử dụng trực tiếp. Nếu destination chứa thông tin nhạy cảm, lưu theo identifier đã chuẩn hóa và giới hạn quyền đọc event.

## 13. Ví dụ event export được phê duyệt

Ví dụ JSON ghi nhận một wrapped export trong quy trình migration:

~~~json
{
  "eventId": "evt-01J8EX91K2",
  "eventTime": "2026-11-28T05:20:10Z",
  "eventType": "key.export",
  "outcome": "success",
  "principal": {
    "id": "spiffe://prod.example/ns/key-ops/sa/migration-job",
    "type": "workload"
  },
  "key": {
    "id": "kms://production/signing-key",
    "version": "v3",
    "type": "private",
    "algorithm": "RSA-3072",
    "purpose": "document-signing"
  },
  "export": {
    "type": "wrapped",
    "format": "vendor-wrapped-package",
    "wrappingKeyId": "hsm://migration/wrapping-key-v2",
    "destination": "hsm://dr-region/partition-a"
  },
  "approval": {
    "changeId": "CHG-4821",
    "approverCount": 2
  },
  "policy": {
    "decision": "allow",
    "policyVersion": "14"
  },
  "requestId": "req-9a8c10"
}
~~~

Ví dụ minh họa metadata, không phải schema bắt buộc của một KMS cụ thể. Hệ thống thật cần ghi đúng định dạng, destination và approval mà backend hỗ trợ; không ghi package hoặc key material vào event.

## 14. Export bị từ chối và export thất bại

Phân biệt các trạng thái:

- **Denied:** policy từ chối trước khi vật liệu được export.
- **Failure:** operation bắt đầu nhưng thất bại kỹ thuật; cần xác minh backend có tạo package một phần hay không.
- **Success:** backend xác nhận export hoàn tất; cần xác minh destination nhận được artifact.
- **Unknown:** không có đủ bằng chứng để xác định operation đã hoàn tất hay chưa.

Một event denied có thể cho thấy principal đang thử quyền vượt scope. Một event failure không tự chứng minh không có dữ liệu nào được tạo. Cần kiểm tra job state, object storage, temporary file và audit của backend.

Không retry export liên tục nếu chưa biết lần trước có tạo artifact hay không. Retry có thể tạo nhiều bản sao khóa và làm phức tạp việc xác định nơi lưu giữ.

## 15. Kiểm soát quyền export

Quyền sử dụng key và quyền export key nên được tách riêng. Một workload có thể cần decrypt bằng KMS nhưng không cần khả năng xuất key material.

Thiết kế quyền:

- Tách operation encrypt/decrypt/sign khỏi export/wrap/unwrap/backup.
- Không cấp export quyền rộng theo wildcard nếu chỉ cần một key cụ thể.
- Giới hạn principal, environment, tenant và key purpose.
- Giới hạn destination, region, account hoặc wrapping key nếu backend hỗ trợ.
- Dùng thời hạn ngắn cho quyền export đặc biệt.
- Yêu cầu approval hoặc dual control cho private/symmetric key.
- Tách người yêu cầu, người phê duyệt và người thực hiện.
- Rà soát định kỳ role có quyền export.

Không dùng cùng một service account để chạy ứng dụng hàng ngày và thực hiện key migration/backup. Workload runtime thường không cần quyền export.

## 16. Destination và data egress control

Một export chỉ an toàn khi destination được xác định và bảo vệ. Cần kiểm soát:

- Account/project/subscription đích.
- Region và security boundary.
- Recipient identity và owner.
- Storage encryption và access policy.
- Network path, proxy và transfer channel.
- Retention, versioning và immutable policy.
- Quyền download, copy, share và delete.

Các kiểm soát egress có thể phát hiện file archive hoặc key package rời khỏi vùng quản trị. Tuy nhiên, DLP không phải lúc nào cũng nhận diện được key package đã mã hóa hoặc format vendor. Vì vậy, cần kết hợp API audit, storage audit, identity và network telemetry.

Không gửi key package qua email, chat hoặc file-sharing cá nhân nếu quy trình không phê duyệt rõ. Nếu transfer cần thiết, dùng kênh được quản lý, xác thực người nhận và ghi nhận checksum/fingerprint của artifact.

## 17. Backup, migration và key ceremony

Backup hoặc migration có thể cần export hợp lệ. Để giảm rủi ro:

1. Xác định lý do, phạm vi key và hệ thống nguồn/đích.
2. Kiểm tra key exportability và quy trình được vendor hỗ trợ.
3. Dùng wrapping/backup mechanism được phê duyệt.
4. Yêu cầu dual control/quorum theo mức nhạy cảm.
5. Xác minh destination, recipient và security domain.
6. Ghi audit từ lúc bắt đầu đến khi hoàn tất transfer/import.
7. Xác minh key ID, attributes, policy và operation ở backend đích.
8. Xóa temporary package và bản sao trung gian theo policy.
9. Kiểm thử ký/giải mã hoặc operation cần thiết bằng key đích.
10. Cập nhật inventory, owner, version và retention.

Key ceremony cần danh sách người tham gia, vai trò, approval, thời điểm và bằng chứng kiểm soát. Không ghi PIN, share secret hoặc key component vào biên bản audit.

## 18. Kiểm tra export từ Java KeyStore

Trong Java, các thao tác có thể làm vật liệu khóa xuất hiện ngoài backend gồm:

- Lấy private key entry từ KeyStore bằng getKey hoặc getEntry.
- Gọi getEncoded trên key object nếu provider hỗ trợ export.
- Ghi keystore ra file bằng store.
- Dùng công cụ quản trị để chuyển entry sang PKCS#12 hoặc định dạng khác.
- Đóng gói thư mục chứa keystore vào artifact hoặc backup.

Không phải mọi provider đều trả về key bytes. HSM-backed key có thể là opaque handle và getEncoded có thể trả null. Nhưng việc key không export được qua một API không đảm bảo không có đường export khác trong công cụ quản trị hoặc quy trình backup.

Ví dụ sử dụng private key HSM-backed để ký mà không yêu cầu ứng dụng lấy encoding của khóa:

~~~java
import java.security.GeneralSecurityException;
import java.security.Key;
import java.security.PrivateKey;
import java.security.Signature;
import java.util.Arrays;

// keyStore, hsmProvider, message và credentialProvider đã được cấu hình.
// Method bao quanh khai báo throws GeneralSecurityException.
char[] entryPassword = credentialProvider.getEntryPassword();
try {
    Key key = keyStore.getKey("document-signing", entryPassword);
    if (!(key instanceof PrivateKey)) {
        throw new GeneralSecurityException("Signing key is unavailable");
    }

    Signature signer =
            Signature.getInstance("SHA256withRSA", hsmProvider);
    signer.initSign((PrivateKey) key);
    signer.update(message);
    byte[] signatureBytes = signer.sign();
} finally {
    Arrays.fill(entryPassword, '\0');
}
~~~

Ví dụ giả định keyStore đã được nạp từ HSM provider, hsmProvider là provider được phê duyệt và credentialProvider cấp entry password/PIN theo cơ chế an toàn. Với provider HSM, key object có thể là handle để thiết bị thực hiện ký; API không cần export private key bytes. Cần kiểm tra tài liệu provider và audit event thực tế của thiết bị.

Không gọi getEncoded để kiểm tra key có export được hay không trong code production. Kiểm tra exportability bằng metadata/attribute và API quản trị được tài liệu hóa; nếu cần test, dùng key thử trong môi trường cô lập.

## 19. Các anti-pattern thường gặp

- Cấp quyền export cho role runtime chỉ vì thao tác backup cần quyền đó.
- Dùng cùng credential để đọc key, export key và xóa audit log.
- Export private key plaintext rồi mới mã hóa file sau đó.
- Lưu file PKCS#12 và password trong cùng thư mục hoặc cùng ticket.
- Ghi key bytes, password hoặc PIN vào log để debug.
- Gửi key package qua kênh chia sẻ không kiểm soát.
- Không ghi destination hoặc recipient trong audit.
- Xem wrapped export là không nhạy cảm.
- Cho phép export từ production sang development.
- Không theo dõi các bản sao và file tạm sau migration.
- Không rotate key sau khi có bằng chứng plaintext export bị lộ.
- Coi API trả về success là bằng chứng artifact đã đến đúng nơi và được bảo vệ.

## 20. Phát hiện export bất thường bằng SIEM

Nguồn dữ liệu nên kết hợp:

- KMS/HSM audit: export, wrap, unwrap, import, policy change.
- IAM audit: role grant, token issuance, MFA, session.
- Storage audit: object create, download, share, permission change.
- Workload telemetry: process, file creation, deployment và service identity.
- Network/DLP: egress, destination, file type và volume.
- Change management: backup window, migration, approval và incident.

Một số detection:

- Export private/symmetric key từ production mà không có approval.
- Principal mới hoặc role vừa được nâng quyền thực hiện export.
- Export nhiều key hoặc nhiều version trong một khoảng ngắn.
- Export tới destination ngoài allowlist.
- Export key non-exportable hoặc thay đổi exportability attribute.
- Export diễn ra ngay sau khi audit policy bị thay đổi.
- Wrapped key được gửi đến wrapping key/recipient mới.
- Export job chạy từ workstation thay vì workload backup chuyên dụng.
- File keystore xuất hiện trong repository, artifact hoặc home directory.

## 21. Ví dụ detection rule

Ví dụ pseudocode phát hiện private key export không có approval:

~~~text
IF
  eventType = "key.export"
  AND key.type IN ["private", "symmetric"]
  AND export.type IN ["plaintext", "keystore"]
  AND outcome = "success"
  AND NOT valid_approval(approvalRef, keyId, destination)
THEN
  alert = "unapproved_sensitive_key_export"
  severity = "critical"
  include = [principalId, keyId, keyVersion, destination, requestId]
~~~

Đây là logic minh họa, không phải cú pháp SIEM cụ thể. Hàm valid_approval phải kiểm tra approval còn hiệu lực, đúng key, đúng destination, đúng thời gian và đúng người thực hiện. Một ticket tồn tại nhưng không liên quan đến key/destination không đủ để coi export hợp lệ.

Rule khác có thể phát hiện role export vừa được cấp rồi có thao tác export trong một khoảng thời gian ngắn, hoặc export volume vượt baseline của backup job.

## 22. Ứng phó khi phát hiện unexpected export

Khi có dấu hiệu export ngoài dự kiến:

1. Xác minh event nguồn, outcome, key ID/version và loại export.
2. Xác định principal, session, source workload và approval.
3. Xác định artifact có được tạo không, ở destination nào và ai đã tải.
4. Cô lập principal/session hoặc tạm dừng export workflow nếu cần.
5. Chặn quyền export tiếp theo và bảo toàn audit evidence.
6. Kiểm tra wrapping key, quyền unwrap, recipient và bản sao trung gian.
7. Nếu plaintext private/secret key có thể đã lộ, đánh giá key là compromised.
8. Tạo key mới, cập nhật consumer và rotate/re-encrypt dữ liệu theo dependency.
9. Với private key gắn certificate, đánh giá revoke certificate và phát hành certificate mới.
10. Xác định mọi bản backup, artifact, cache, temporary file và replica chứa key.
11. Thu hồi quyền, xóa bản sao theo quy trình và xác minh kết quả.
12. Ghi timeline, phạm vi ảnh hưởng, quyết định và bằng chứng.

Không xóa key nguồn ngay lập tức nếu việc đó làm mất khả năng giải mã dữ liệu hợp lệ hoặc phá hỏng điều tra. Cần đánh giá dependency, backup và kế hoạch chuyển đổi. Tuy nhiên, phải ngăn key bị nghi compromise tiếp tục dùng cho operation mới theo incident policy.

## 23. Đánh giá mức độ compromise

Mức độ ảnh hưởng phụ thuộc loại export và khả năng sử dụng artifact:

| Tình huống | Đánh giá ban đầu | Hành động thường cần |
|---|---|---|
| Public key/certificate export hợp lệ | Thường không phải bí mật bị lộ | Xác minh fingerprint, issuer và destination |
| Wrapped key đến destination được phê duyệt | Rủi ro phụ thuộc wrapping key và quyền unwrap | Xác minh recipient, policy và integrity |
| Wrapped key đến destination lạ | Có nguy cơ bị mở bọc nếu KEK/unwrap bị lộ hoặc quyền bị chiếm | Cô lập destination, kiểm tra unwrap, rotate nếu cần |
| Encrypted keystore bị lộ nhưng password/key bảo vệ còn an toàn | Có nguy cơ tấn công offline hoặc lộ nếu password yếu | Xác minh cipher/KDF, rotate password và đánh giá key |
| Plaintext private/secret key bị lộ | Compromise nghiêm trọng | Thay key, revoke certificate/credential, xử lý dữ liệu phụ thuộc |
| Export outcome không rõ | Chưa thể kết luận không có lộ lọt | Cô lập đường export và xác minh artifact/destination |

Không chỉ dựa vào file extension hoặc tên event. Cần xác định nội dung thực tế, khả năng unwrap, người nhận, quyền truy cập và thời gian artifact tồn tại.

## 24. Xoay vòng và xử lý dữ liệu phụ thuộc key bị export

Nếu plaintext key có thể đã lộ, tạo key mới không tự bảo vệ dữ liệu cũ:

- Với encryption key, cần xác định ciphertext nào được bảo vệ bởi key cũ; re-encrypt hoặc rewrap theo thiết kế.
- Với KEK, cần xác định DEK nào được bọc bởi KEK đó; rewrap DEK bằng KEK mới nếu phù hợp.
- Với signing key, cần xác định chữ ký nào được tạo trong khoảng compromise và cách xác minh/trust lại.
- Với TLS private key, thay key pair và certificate, cập nhật endpoint và trust chain nếu cần.
- Với API/client credential, revoke credential cũ tại hệ thống đích và phát hành credential mới.

Giữ key cũ ở trạng thái decrypt-only có thể cần cho dữ liệu lịch sử, nhưng phải đánh giá nguy cơ attacker tiếp tục sử dụng nó. Nếu key bị compromise, không mặc định giữ quyền decrypt vô thời hạn; cần có migration plan và thời hạn cụ thể.

## 25. Bảo vệ bằng chứng và xử lý artifact

Trong điều tra, cần bảo toàn:

- Audit event gốc từ KMS/HSM/provider.
- IAM/session/token issuance và policy change.
- Storage download/share/permission logs.
- File metadata, checksum/fingerprint và nơi tìm thấy artifact.
- Process, host, workload và network telemetry.
- Approval, change ticket, backup/restore job và người tham gia.
- Bằng chứng rotate/revoke/destroy và xác nhận từ backend.

Không copy key material vào ticket hoặc báo cáo incident. Nếu cần giữ artifact để điều tra, phải lưu trong evidence vault được mã hóa, giới hạn quyền và có chain of custody. Các bản sao còn lại cần được xử lý theo legal hold và retention policy.

## 26. Kiểm thử kiểm soát export

Thực hiện kiểm thử bằng key và identity thử:

| Test | Kết quả mong đợi |
|---|---|
| Runtime workload yêu cầu export | Bị deny nếu policy không cấp quyền |
| Admin export không có approval | Bị deny hoặc tạo alert theo policy |
| Export wrapped trong change hợp lệ | Có approval, destination và audit đầy đủ |
| Export đến destination lạ | Bị chặn hoặc cảnh báo trước khi transfer |
| Key non-exportable | Backend từ chối export plaintext |
| Thay đổi exportability | Có event, approval và alert |
| Export job thất bại | Ghi failure và xác minh không có artifact mồ côi |
| Export thành công | Có event nguồn, destination receipt và inventory update |
| Temporary package cleanup | Không còn bản sao ngoài retention được duyệt |
| Audit pipeline gián đoạn | Có buffer/alert và không mất event quan trọng |

Kiểm thử cần đi qua nguồn audit, collector, SIEM và quy trình incident. Không thử export key production hoặc tạo quyền export trái phép trên môi trường thật nếu chưa có kế hoạch kiểm thử được phê duyệt.

## 27. Checklist kiểm soát Unexpected export

Trước khi vận hành hệ thống quản lý khóa, hãy xác nhận:

- [ ] Inventory ghi key ID/version, type, purpose, backend và exportability.
- [ ] Key được đặt non-exportable nếu use case cho phép.
- [ ] Quyền sử dụng key và quyền export được tách biệt.
- [ ] Plaintext private/secret key export bị cấm mặc định.
- [ ] Wrapped export chỉ dùng wrapping key, recipient và destination được phê duyệt.
- [ ] Export nhạy cảm có approval, dual control hoặc quorum.
- [ ] Event ghi principal, key ID/version, export type, destination, policy và outcome.
- [ ] Audit cả denied, failed, success và unknown outcome.
- [ ] Audit policy/exportability change, backup, migration và restore.
- [ ] SIEM phát hiện principal mới, volume bất thường và destination lạ.
- [ ] Không log key bytes, password, PIN hoặc wrapping secret.
- [ ] File keystore, artifact, temporary copy và backup có retention/cleanup rõ.
- [ ] Audit log được bảo vệ độc lập và không bị principal export xóa.
- [ ] Có quy trình incident để cô lập, đánh giá compromise, rotate/revoke và re-encrypt.
- [ ] Có kiểm thử định kỳ cho export policy, destination và audit pipeline.

## 28. Checklist điều tra một lần export bất thường

Khi nhận cảnh báo, hãy xác nhận:

- [ ] Event có phải từ nguồn audit tin cậy không?
- [ ] Operation thực sự là plaintext, wrapped, keystore, backup hay public-key export?
- [ ] Key ID/version, type, purpose và exportability là gì?
- [ ] Principal/session/workload nào thực hiện?
- [ ] Policy có cho phép và approval có đúng key/destination/thời gian không?
- [ ] Artifact đã được tạo và chuyển đến đâu?
- [ ] Ai có thể đọc artifact hoặc unwrap key?
- [ ] Có bản sao trong cache, temporary directory, CI artifact hoặc storage version không?
- [ ] Audit logging có bị thay đổi hoặc gián đoạn không?
- [ ] Key có cần được xem là compromised và rotate/revoke không?
- [ ] Dữ liệu, certificate, backup hoặc consumer nào phụ thuộc key?
- [ ] Bằng chứng đã được bảo toàn và mọi bản sao đã được xử lý chưa?

Unexpected export là tín hiệu cần điều tra vì nó có thể làm khóa rời khỏi ranh giới bảo vệ ban đầu. Kiểm soát hiệu quả bắt đầu từ inventory exportability, quyền export tách biệt, approval và destination rõ ràng; tiếp tục bằng audit event đủ ngữ cảnh và detection dựa trên baseline; kết thúc bằng containment, đánh giá compromise, rotation/revocation và xử lý mọi bản sao. Không ghi key material vào log và không coi wrapped export là vô hại: mọi bản sao khóa cần có owner, mục đích, thời hạn và đường khôi phục được kiểm soát.
