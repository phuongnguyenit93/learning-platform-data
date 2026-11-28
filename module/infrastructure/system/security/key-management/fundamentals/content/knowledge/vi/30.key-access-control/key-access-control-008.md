# Export key permission

Trong hệ thống quản lý khóa, một ứng dụng có thể cần dùng khóa để mã hóa, giải mã, ký số hoặc xác minh chữ ký. Những thao tác này không đồng nghĩa với việc ứng dụng được phép lấy **key material** ra khỏi nơi lưu trữ. **Export key permission** là quyền cho phép một danh tính hoặc workload xuất dữ liệu khóa khỏi ranh giới quản lý ban đầu, dưới dạng rõ hoặc dưới dạng đã được bọc bằng một khóa khác.

Quyền xuất khóa có mức rủi ro cao vì người nhận có thể tạo thêm bản sao nằm ngoài sự kiểm soát của KMS/HSM. Nếu bản sao đó bị lộ, việc thu hồi quyền gọi API hoặc vô hiệu hóa khóa tại hệ thống gốc có thể không thu hồi được bản sao đã xuất. Vì vậy, thiết kế an toàn thường mặc định không cho xuất key material, chỉ cấp quyền khi có nhu cầu nghiệp vụ được phê duyệt và giới hạn rõ khóa, định dạng, đích nhận, thời hạn cùng người chịu trách nhiệm.

## 1. Export key permission là gì?

Export key permission là quyền thực hiện một thao tác đưa key material ra khỏi kho khóa hoặc thiết bị đang quản lý nó. Tùy nền tảng, thao tác có thể được gọi là export, unwrap, download, retrieve key material hoặc backup/export. Cần đọc đúng semantics của dịch vụ vì các tên gần giống nhau không nhất thiết có cùng hành vi.

Ví dụ:

- Một dịch vụ được phép yêu cầu KMS mã hóa dữ liệu bằng một key ID nhưng không được lấy key bytes.
- Một dịch vụ khác được phép giải mã ciphertext bằng KMS nhưng không được xuất khóa gốc.
- Một nhóm vận hành được phép export khóa dưới dạng wrapped key để di chuyển sang HSM khác.
- Một quy trình khôi phục được phép import hoặc restore bản sao khóa theo cơ chế dual control.

Quyền export cần được xem là quyền quản trị nhạy cảm. Nó có thể mở rộng phạm vi sử dụng khóa vượt ra ngoài policy, audit và ranh giới bảo vệ của hệ thống ban đầu.

## 2. Phân biệt quyền sử dụng khóa và quyền xuất key material

Một nguyên tắc quan trọng là **có quyền dùng khóa không có nghĩa là có quyền lấy khóa ra**.

| Quyền | Mục đích | Có làm lộ key material không? |
|---|---|---|
| `Encrypt` | Yêu cầu hệ thống mã hóa dữ liệu bằng khóa | Thông thường không |
| `Decrypt` | Yêu cầu hệ thống giải mã dữ liệu bằng khóa | Không nhất thiết; plaintext được trả về nhưng key material vẫn có thể ở trong KMS/HSM |
| `Sign` | Yêu cầu ký dữ liệu bằng khóa riêng | Không nhất thiết; thao tác ký có thể diễn ra trong HSM |
| `Verify` | Xác minh chữ ký bằng khóa công khai | Không làm lộ khóa bí mật |
| `WrapKey` | Bọc một khóa bằng khóa wrapping được phép | Không nhất thiết xuất khóa ở dạng rõ; đầu ra là wrapped key |
| `UnwrapKey` | Mở wrapped key trong một ranh giới được phép | Có thể trả key material rõ hoặc tạo key handle tùy API và provider |
| `ExportPlaintext` | Xuất key material ở dạng rõ | Có; đây là quyền rủi ro cao |
| `ExportWrapped` | Xuất key material đã được bọc bằng khóa đích | Có tạo bản sao khóa, nhưng bản sao được bảo vệ bằng wrapping key |
| `ImportKey` | Đưa key material vào kho quản lý mới | Không phải export, nhưng là thao tác nhạy cảm trong quy trình di chuyển |

Tên thao tác cụ thể tùy KMS/HSM. Bảng trên mô tả ý nghĩa khái niệm. Khi thiết kế IAM policy, cần dựa trên API và hành vi thực tế của nhà cung cấp, không chỉ dựa vào tên quyền.

Nếu ứng dụng chỉ cần mã hóa/giải mã hoặc ký số, nên cấp quyền gọi đúng thao tác đó. Không cấp quyền export chỉ để ứng dụng có thể tự thực hiện cùng phép toán bằng thư viện phần mềm.

## 3. Export plaintext và export wrapped khác nhau thế nào?

Có hai cách xuất thường gặp:

| Hình thức | Nội dung đầu ra | Rủi ro và yêu cầu |
|---|---|---|
| Plaintext export | Key material ở dạng rõ, có thể dùng trực tiếp với thuật toán tương ứng | Rủi ro rất cao; người nhận, bộ nhớ, file tạm, log và kênh truyền đều có thể làm lộ khóa |
| Wrapped export | Key material được mã hóa/bọc bằng một wrapping key được chấp thuận | Giảm nguy cơ lộ trên đường truyền và nơi lưu; vẫn tạo một bản sao khóa và cần kiểm soát wrapping key, đích nhận và quyền unwrap |

Wrapped export không đồng nghĩa với việc khóa không thể bị lộ. Nếu wrapping key bị lộ, hoặc bên nhận có quyền unwrap quá rộng, bản sao wrapped có thể được chuyển thành key material có thể sử dụng. Cần xác minh thuật toán wrapping, cách xác thực dữ liệu, key usage, key ID và khả năng tương thích giữa hai hệ thống.

Không nên dùng password do người dùng chọn làm wrapping key trực tiếp. Nếu giao thức cho phép password-based wrapping, phải dùng KDF phù hợp, salt và tham số đã được phê duyệt. Trong môi trường KMS/HSM, ưu tiên wrapping key được quản lý độc lập và có policy rõ ràng.

## 4. Vì sao quyền export có rủi ro cao?

Khi key material rời khỏi KMS/HSM, hệ thống gốc có thể không còn kiểm soát được:

- Ai đang giữ bản sao và họ đã tạo thêm bao nhiêu bản sao.
- Khóa được dùng ở máy chủ, container, thiết bị hoặc môi trường nào.
- Có bao nhiêu bản backup, snapshot, file tạm hoặc artifact chứa khóa.
- Bên nhận có tiếp tục chia sẻ khóa hoặc sử dụng ngoài mục đích đã duyệt hay không.
- Việc thu hồi quyền ở hệ thống gốc có thể tác động đến bản sao đã xuất hay không.

Nếu một private key ký số bị export, người giữ bản sao có thể ký dữ liệu bên ngoài HSM và không còn tạo audit event tại HSM. Nếu một DEK bị export, người giữ bản sao có thể giải mã ciphertext đã lấy mà không cần gọi KMS. Nếu KEK bị export, phạm vi ảnh hưởng có thể bao gồm nhiều DEK đã được bọc bằng KEK đó.

Do đó, exportability nên được quyết định ngay từ lúc tạo khóa nếu nền tảng hỗ trợ thuộc tính không thể thay đổi sau này. Với khóa gốc, khóa ký quan trọng hoặc KEK, lựa chọn non-exportable thường giảm đáng kể bề mặt rủi ro.

## 5. Non-exportable key và opaque key handle

**Non-exportable key** là khóa được cấu hình hoặc bảo vệ sao cho key material không thể được xuất ra khỏi ranh giới bảo vệ theo các API được phép. Ứng dụng vẫn có thể sử dụng khóa thông qua một handle hoặc đối tượng đại diện do provider cung cấp.

Ví dụ với HSM:

1. Khóa được tạo bên trong thiết bị.
2. HSM lưu key material trong ranh giới phần cứng.
3. Ứng dụng nhận một key handle hoặc đối tượng Java đại diện.
4. Ứng dụng gọi `sign`, `decrypt`, `unwrap` hoặc thao tác được policy cho phép.
5. HSM thực hiện phép toán nội bộ và trả kết quả, không cần trả private key bytes.

Trong Java, `Key.getEncoded()` có thể trả về `null` nếu provider không hỗ trợ xuất encoding của khóa. Với khóa HSM không exportable, đối tượng Java thường hoạt động như một tham chiếu tới khóa trong thiết bị. Tuy nhiên, `getEncoded() == null` không phải bằng chứng độc lập đủ mạnh để kết luận khóa thực sự không thể export; cần kiểm tra thuộc tính và policy ở provider/HSM.

Một khóa non-exportable vẫn có thể bị lạm dụng nếu attacker chiếm được danh tính được phép gọi thao tác mật mã. Vì vậy, phải giới hạn quyền sử dụng, scope, số lần gọi, ngữ cảnh dữ liệu và giám sát hành vi bất thường.

## 6. Ai nên có quyền export key?

Quyền export chỉ nên cấp cho danh tính có nhiệm vụ cụ thể và được phê duyệt. Các ví dụ có thể cần quyền này gồm:

- Quy trình di chuyển khóa giữa hai KMS/HSM khi nhà cung cấp hoặc kiến trúc thay đổi.
- Khôi phục khóa từ bản backup được bảo vệ theo quy trình disaster recovery.
- Chuyển khóa đã được wrap sang một thiết bị hoặc miền bảo vệ khác.
- Tích hợp hệ thống cũ bắt buộc phải nhận key material và chưa thể thay đổi ngay.

Những đối tượng thường không nên có quyền export:

- Tài khoản ứng dụng chỉ cần gọi encrypt/decrypt/sign.
- Nhân viên phát triển hoặc CI job thông thường.
- Tài khoản quản trị hạ tầng không có nhiệm vụ quản lý key material.
- Workload production không cần đưa khóa ra ngoài KMS/HSM.

Không nên dùng tài khoản dùng chung cho thao tác export. Mỗi yêu cầu cần gắn với danh tính cá nhân hoặc workload xác định, ticket/change record, mục đích, key ID, đích nhận và thời hạn quyền.

## 7. Thiết kế IAM policy cho export

IAM policy cần tách quyền sử dụng khóa khỏi quyền export. Một mô hình policy khái niệm:

```json
{
  "principal": "key-migration-service",
  "resource": "key/prod/data-kek-v3",
  "actions": [
    "kms:DescribeKey",
    "kms:ExportWrappedKey"
  ],
  "conditions": {
    "destinationKey": "hsm://target-domain/migration-wrap-key",
    "exportFormat": "wrapped",
    "changeTicket": "approved",
    "expiresAt": "2026-12-31T23:59:59Z"
  }
}
```

Đây là policy minh họa, không phải cú pháp của một nhà cung cấp cụ thể. Tên action và condition phải được ánh xạ sang IAM model thực tế. Một policy tốt nên giới hạn:

- Principal cụ thể, ưu tiên workload identity ngắn hạn.
- Key ID và phiên bản khóa cụ thể, không dùng wildcard rộng.
- Chỉ loại export được phép, ưu tiên wrapped export.
- Wrapping key hoặc đích nhận được xác thực và phê duyệt.
- Mục đích, ticket, thời hạn và môi trường.
- Số lần hoặc hạn mức export nếu nền tảng hỗ trợ.
- Người yêu cầu và người phê duyệt tách biệt khi mức độ rủi ro yêu cầu.

Không cấp `Export*` trên toàn bộ key namespace cho một nhóm chỉ vì họ có vai trò quản trị KMS. Quyền quản lý metadata, rotate, disable, schedule deletion và export key material nên được tách riêng.

## 8. RBAC, ABAC và phân tách nhiệm vụ

**RBAC (Role-Based Access Control)** gán quyền theo vai trò, ví dụ `KeyOperator`, `KeyAuditor`, `KeyMigrationApprover`. Cách này dễ quản lý nhưng có thể cấp quyền quá rộng nếu vai trò chứa nhiều action nhạy cảm.

**ABAC (Attribute-Based Access Control)** quyết định dựa trên thuộc tính của principal, resource và request, chẳng hạn môi trường, key classification, owner, destination, ticket, thời hạn và trạng thái phê duyệt. ABAC hữu ích để giới hạn export theo từng tình huống.

Một quy trình có phân tách nhiệm vụ có thể gồm:

1. Người yêu cầu nêu key ID, lý do, đích nhận, định dạng export và thời gian cần quyền.
2. Key owner xác nhận nghiệp vụ và dữ liệu phụ thuộc.
3. Security/key custodian phê duyệt rủi ro và phương thức bảo vệ.
4. Hệ thống cấp quyền tạm thời cho đúng workload hoặc operator.
5. Một người/nhóm độc lập xác nhận thao tác nếu policy yêu cầu dual control.
6. Hệ thống ghi audit và tự thu hồi quyền sau thời hạn.

Người phê duyệt không nên tự phê duyệt yêu cầu của chính mình đối với khóa có mức phân loại cao. Dual control hoặc quorum approval giúp giảm nguy cơ một tài khoản đơn lẻ xuất khóa trái phép.

## 9. Kiểm soát ở KMS và HSM

KMS/HSM thường cung cấp các lớp kiểm soát khác nhau:

| Lớp kiểm soát | Câu hỏi cần xác minh |
|---|---|
| Key attributes | Khóa có được đánh dấu exportable/non-exportable khi tạo không? Có thể đổi thuộc tính sau này không? |
| IAM/policy | Principal nào được gọi export, wrap, unwrap, decrypt hoặc sign? |
| Key usage | Khóa có bị giới hạn mục đích như encrypt/decrypt, sign/verify hoặc wrap/unwrap không? |
| Wrapping policy | Chỉ wrapping key nào được phép bảo vệ khóa xuất ra? |
| HSM boundary | Key material có rời thiết bị không? Có cơ chế backup/clone an toàn riêng không? |
| Approval | Có hỗ trợ dual control, quorum hoặc phê duyệt ngoài băng không? |
| Audit | Có ghi principal, key ID, action, destination, result và thời gian không? |
| Lifecycle | Có thể disable, rotate, revoke hoặc destroy các bản sao/phiên bản không? |

Một số HSM hỗ trợ thuộc tính tương tự `CKA_SENSITIVE` và `CKA_EXTRACTABLE` trong mô hình PKCS#11. `CKA_SENSITIVE` biểu thị key material nhạy cảm; `CKA_EXTRACTABLE` điều khiển khả năng trích xuất theo semantics của token/provider. Cần kiểm tra tài liệu HSM và provider cụ thể; không giả định mọi thiết bị triển khai các thuộc tính giống hệt nhau hoặc cho phép thay đổi chúng sau khi tạo khóa.

Backup hoặc replication nội bộ của HSM không nhất thiết giống export thông thường. Nhà cung cấp có thể dùng domain key, wrapping key hoặc cơ chế quorum riêng để di chuyển/khôi phục khóa. Hãy xem đây là một quy trình đặc quyền và kiểm tra đúng mô hình bảo vệ của thiết bị.

## 10. Export key trong Java KeyStore và JCA

Java cung cấp API để truy xuất khóa, nhưng khả năng export phụ thuộc provider và loại khóa.

```java
import java.security.Key;
import java.security.KeyStore;

KeyStore keyStore = KeyStore.getInstance("PKCS11", hsmProvider);
keyStore.load(null, pin);

Key key = keyStore.getKey("payment-signing-key", null);
if (key == null) {
    throw new IllegalStateException("Key alias not found");
}

byte[] encoded = key.getEncoded();
if (encoded == null) {
    // Provider không cung cấp encoding của key qua API này.
    // Tiếp tục dùng key handle với Signature/Cipher theo policy.
} else {
    // Chỉ xử lý encoding nếu export đã được policy cho phép.
    java.util.Arrays.fill(encoded, (byte) 0);
}
```

Ví dụ trên chỉ minh họa hành vi API. Với HSM, cách nạp PKCS#11 và PIN phụ thuộc cấu hình provider; `load(null, pin)` không phải cách dùng phổ quát cho mọi provider. Không được xem việc `getEncoded()` trả về `null` là thay thế cho policy export của HSM. Ngược lại, nếu provider trả về byte array, ứng dụng phải coi đó là key material nhạy cảm và chỉ tiếp tục khi có quyền export được phê duyệt.

Không gọi `getEncoded()` chỉ để kiểm tra khóa trong production nếu ứng dụng không cần xuất khóa. Đối với thao tác ký số, hãy truyền đối tượng `PrivateKey` cho `Signature.initSign()` để provider có thể thực hiện ký bằng key handle trong HSM mà không cần xuất private key bytes.

## 11. Quy trình export wrapped key an toàn

Khi có nhu cầu di chuyển khóa, wrapped export thường giảm rủi ro so với export plaintext. Quy trình cần được thiết kế từ đầu đến cuối:

1. Xác nhận mục đích, key ID, version, owner, phân loại và đích nhận.
2. Xác minh hệ thống đích và wrapping key được phê duyệt.
3. Kiểm tra thuật toán wrapping, định dạng, key usage và khả năng tương thích.
4. Phê duyệt quyền export tạm thời theo RBAC/ABAC và dual control nếu cần.
5. Thực hiện export dưới dạng wrapped; không ghi plaintext key material ra file tạm.
6. Truyền gói wrapped qua kênh xác thực, mã hóa và có kiểm soát truy cập.
7. Import/unwrap tại HSM/KMS đích bằng danh tính và quyền đã được cấp.
8. Xác minh key ID, fingerprint/metadata, key usage và khả năng thực hiện thao tác dự kiến.
9. Thu hồi quyền export tạm thời và xác minh bản sao ngoài dự kiến đã được xử lý.
10. Ghi audit kết quả và cập nhật inventory/ownership.

Nếu định dạng export chứa metadata như algorithm, key size, usage hoặc origin, cần xác minh tính toàn vẹn và ràng buộc metadata với key material. Không cho phép bên nhận tự ý mở rộng key usage khi import.

## 12. Export, backup, replication và key wrapping

Các khái niệm này có liên quan nhưng không thể thay thế cho nhau:

| Hoạt động | Mục tiêu | Kiểm soát chính |
|---|---|---|
| Export | Đưa key material ra khỏi kho quản lý | Quyền export, đích nhận, định dạng, audit |
| Backup | Bảo đảm có thể phục hồi khi mất thiết bị hoặc dữ liệu | Mã hóa backup, phân tách quyền, quorum, retention và recovery test |
| Replication | Duy trì bản sao trong một miền dịch vụ/thiết bị khác | Trust relationship, đồng bộ trạng thái, policy và audit |
| Key wrapping | Mã hóa một khóa bằng một khóa wrapping khác | Thuật toán wrapping, wrapping key, integrity và metadata |
| Import | Đưa key material hoặc wrapped key vào kho đích | Quyền import, xác minh nguồn, usage và owner |

Một bản backup có thể được giữ hoàn toàn trong miền bảo vệ của HSM và không được xuất ra dạng key bytes. Một gói wrapped export có thể được dùng trong quy trình di chuyển nhưng không tự động là backup đầy đủ. Cần xác định rõ mục tiêu và semantics của từng thao tác.

## 13. Audit và phát hiện export bất thường

Mỗi thao tác export cần tạo audit event có thể truy vết. Tối thiểu nên ghi:

- Principal và workload thực hiện yêu cầu.
- Key ID, phiên bản, loại khóa và owner.
- Action: export plaintext, export wrapped, wrap, unwrap, import hoặc backup.
- Đích nhận hoặc wrapping key ID.
- Thời gian yêu cầu, phê duyệt, thực thi và kết quả.
- Ticket/change/incident reference, lý do và người phê duyệt.
- Policy version, request context và lỗi nếu có.

Không ghi key material, password, PIN hoặc plaintext secret vào audit log. Với wrapped export, vẫn cần phân loại gói dữ liệu là nhạy cảm vì người có wrapping key có thể mở nó.

Các dấu hiệu bất thường có thể gồm export ngoài giờ hoặc ngoài cửa sổ thay đổi, export số lượng lớn, principal mới, đích nhận không quen thuộc, export plaintext khi chỉ cho phép wrapped, lặp lại thất bại hoặc yêu cầu export khóa có phân loại cao. Nên đặt alert, rate limit và cơ chế tạm khóa khi phát hiện hành vi đáng ngờ.

## 14. Ứng phó khi quyền export hoặc key material bị lạm dụng

Nếu phát hiện export trái phép, cần coi key material có thể đã rời khỏi ranh giới tin cậy. Các bước xử lý:

1. Chặn principal hoặc workload thực hiện export; thu hồi session và credential quản trị liên quan.
2. Disable quyền export ở policy và kiểm tra có thay đổi policy trái phép hay không.
3. Xác định key ID/version, loại export, wrapping key, đích nhận, thời gian và số lần thao tác.
4. Đánh giá key material có ở dạng rõ hay wrapped, ai có thể unwrap và có bản sao ở đâu.
5. Nếu khóa bị lộ hoặc không thể xác minh phạm vi bản sao, tạo khóa mới và chuyển workload/dữ liệu theo kế hoạch.
6. Với khóa ký, đánh giá chứng thư, chữ ký và nhu cầu thu hồi certificate.
7. Với DEK/KEK, xác định ciphertext và wrapped DEK phụ thuộc; rewrap hoặc re-encrypt khi rủi ro yêu cầu.
8. Bảo toàn audit log, HSM event và bằng chứng phê duyệt để điều tra.
9. Thu hồi hoặc destroy khóa cũ khi đã xử lý dữ liệu phụ thuộc và backup theo chính sách.
10. Cập nhật policy, kiểm thử kiểm soát và diễn tập lại quy trình export.

Chỉ xóa file export hoặc thu hồi quyền gọi API không đủ nếu bản sao đã được tạo ở nơi khác. Cần xác định người nhận và bản sao có thể tồn tại trong file system, backup, artifact, memory dump, log hoặc thiết bị ngoại vi.

## 15. Checklist thiết kế Export key permission

- Mặc định deny export; chỉ cấp khi có use case được phê duyệt.
- Tách quyền encrypt/decrypt/sign khỏi quyền export key material.
- Phân loại khóa và xác định có thể đặt non-exportable ngay khi tạo hay không.
- Ưu tiên HSM/KMS giữ khóa trong ranh giới bảo vệ và cung cấp crypto operation qua API.
- Nếu cần di chuyển, ưu tiên wrapped export với wrapping key và đích nhận được xác thực.
- Giới hạn principal, key ID/version, key usage, destination, thời hạn và số lần export.
- Dùng RBAC kết hợp ABAC; áp dụng dual control/quorum cho khóa nhạy cảm.
- Kiểm tra semantics export/backup/replication/import theo provider cụ thể.
- Bảo vệ file tạm, memory, transport và backup; không log plaintext key material.
- Ghi audit bất biến và cảnh báo export bất thường.
- Có quy trình xác minh import, thu hồi quyền tạm thời và xử lý bản sao.
- Có playbook rotation, revocation, re-encryption và destruction nếu key material bị lộ.

Export key permission là một trong những quyền nhạy cảm nhất trong access control cho khóa. Thiết kế tốt bắt đầu từ việc giữ key material trong ranh giới bảo vệ và cho phép ứng dụng thực hiện đúng thao tác mật mã cần thiết. Khi có nhu cầu xuất khóa hợp lệ, quyền phải được giới hạn theo danh tính, key ID, mục đích, định dạng, đích nhận và thời hạn; quy trình cần phê duyệt độc lập, audit và kế hoạch xử lý bản sao. Những kiểm soát này giúp tổ chức duy trì quyền kiểm soát khóa xuyên suốt quá trình cấp phát, sử dụng, di chuyển, xoay vòng và hủy.

## Tài liệu tham khảo

- [NIST SP 800-57 Part 1 Rev. 5: Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final)
- [NIST SP 800-130: A Framework for Designing Cryptographic Key Management Systems](https://csrc.nist.gov/pubs/sp/800/130/final)
- [OASIS PKCS #11 Cryptographic Token Interface Base Specification](https://docs.oasis-open.org/pkcs11/pkcs11-base/v3.1/os/pkcs11-base-v3.1-os.html)
- [Java SE API: `java.security.Key`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Key.html)
- [Java SE API: `java.security.KeyStore`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html)
