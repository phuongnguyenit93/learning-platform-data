# Use key permission: Phân quyền sử dụng khóa mật mã

**Use key permission** là quyền cho phép một danh tính hoặc ứng dụng thực hiện một thao tác mật mã cụ thể bằng một khóa. Quyền này có thể cho phép mã hóa, giải mã, ký số, xác minh chữ ký, tạo MAC, wrap hoặc unwrap khóa. Nó cần được giới hạn theo khóa, mục đích, danh tính gọi và ngữ cảnh sử dụng.

Có một khóa hợp lệ trong KeyStore hoặc biết alias của khóa không đồng nghĩa với việc mọi ứng dụng đều được phép sử dụng khóa đó. Quyền đọc tệp, quyền lấy key handle, quyền gọi thao tác mật mã và quyền quản trị vòng đời là những lớp kiểm soát khác nhau. Một hệ thống quản lý khóa an toàn phải xác định rõ ai được dùng khóa nào, để làm gì, trong môi trường nào và trong khoảng thời gian nào.

Trong module quản lý khóa mật mã, phân quyền sử dụng khóa bảo vệ key material khỏi truy cập trái phép và giới hạn tác động khi một tài khoản hoặc workload bị xâm nhập. Nó cũng giúp phân tách quyền vận hành: ứng dụng có thể được phép ký bằng khóa nhưng không được xuất khóa riêng, thay đổi policy hoặc hủy khóa.

## 1. Use key permission là gì?

Use key permission là tập quyền gắn với thao tác được thực hiện trên một khóa. Thay vì cấp quyền chung chung như “được truy cập khóa”, chính sách cần chỉ rõ thao tác nào được phép và danh tính nào được thực hiện thao tác đó.

Ví dụ:

- Dịch vụ thanh toán được phép ký giao dịch bằng khóa ký của dịch vụ.
- Dịch vụ xác minh được phép đọc khóa công khai và xác minh chữ ký, nhưng không được ký.
- Dịch vụ lưu trữ được phép yêu cầu KMS giải mã DEK cho đúng tenant và đúng mục đích.
- Dịch vụ báo cáo chỉ được mã hóa dữ liệu đầu ra bằng khóa được chỉ định, không được giải mã dữ liệu khác.
- Nhóm vận hành được phép xem trạng thái và yêu cầu rotate khóa, nhưng không được export private key.

Quyền sử dụng nên gắn với danh tính đã xác thực như service identity, workload identity, người dùng hoặc role. Không nên cấp quyền chỉ dựa trên tên ứng dụng do caller tự khai báo; danh tính phải được xác minh bằng cơ chế tin cậy.

## 2. Các nhóm quyền trên một khóa

Một khóa có thể hỗ trợ nhiều thao tác. Key policy nên phân biệt quyền sử dụng dữ liệu (data plane) với quyền quản trị khóa (control plane).

### Quyền thao tác mật mã

| Quyền | Ý nghĩa | Ví dụ sử dụng |
|---|---|---|
| Encrypt | Mã hóa dữ liệu bằng khóa. | Dịch vụ ghi dữ liệu mới vào kho lưu trữ. |
| Decrypt | Giải mã dữ liệu đã được mã hóa. | Dịch vụ đọc hồ sơ hoặc mở DEK. |
| Sign | Tạo chữ ký số bằng khóa ký, thường là khóa riêng. | Dịch vụ ký token, hóa đơn hoặc artifact. |
| Verify | Xác minh chữ ký bằng khóa công khai. | API gateway kiểm tra token hoặc chữ ký webhook. |
| Generate MAC | Tạo mã xác thực thông điệp bằng khóa bí mật. | Xác thực thông điệp giữa hai dịch vụ. |
| Verify MAC | Kiểm tra MAC. | Xác minh dữ liệu nhận được. |
| Wrap | Bọc một khóa khác bằng khóa wrapping/KEK. | Bảo vệ DEK trước khi lưu hoặc truyền. |
| Unwrap | Mở gói một khóa đã được wrap. | Lấy DEK để giải mã dữ liệu. |
| Derive | Dẫn xuất khóa con hoặc bí mật theo cơ chế được phép. | Tạo khóa theo ngữ cảnh hoặc phiên. |
| Export | Xuất key material khỏi ranh giới bảo vệ. | Di chuyển khóa theo quy trình đặc biệt. |

Không phải thuật toán hoặc loại khóa nào cũng hỗ trợ tất cả thao tác. Ví dụ, khóa công khai thường được dùng để xác minh chữ ký hoặc mã hóa; khóa riêng tương ứng được dùng để ký hoặc giải mã theo thuật toán. Khóa AES có thể được dùng cho encrypt/decrypt hoặc wrap nếu được tạo cho mục đích phù hợp.

### Quyền quản trị vòng đời

| Quyền quản trị | Ý nghĩa |
|---|---|
| View metadata | Xem alias, key ID, thuật toán, trạng thái, phiên bản và thời hạn. |
| Create/Generate | Tạo khóa mới. |
| Import | Đưa key material vào hệ thống nếu policy cho phép. |
| Change policy/Grant | Sửa quyền hoặc cấp quyền cho danh tính khác. |
| Rotate | Tạo phiên bản mới và chuyển hệ thống sang dùng phiên bản đó. |
| Disable/Enable | Tạm ngừng hoặc kích hoạt lại việc sử dụng khóa. |
| Revoke | Thu hồi khóa, chứng thư hoặc quyền sử dụng theo cơ chế của hệ thống. |
| Backup/Restore | Tạo hoặc phục hồi bản sao khóa theo quy trình được phê duyệt. |
| Destroy | Hủy khóa hoặc key material theo chính sách. |

Quyền quản trị có thể gián tiếp mở rộng quyền sử dụng. Ví dụ, người có quyền thay đổi key policy có thể cấp quyền decrypt cho chính mình. Vì vậy, quyền grant, policy update, import, export và destroy thường cần được giới hạn chặt hơn quyền xem metadata hoặc thực hiện một thao tác mật mã đã định trước.

## 3. Phân quyền theo nguyên tắc least privilege

**Least privilege** yêu cầu mỗi danh tính chỉ nhận những quyền tối thiểu cần để hoàn thành nhiệm vụ. Với khóa mật mã, nên áp dụng nguyên tắc này ở nhiều chiều:

- **Theo khóa:** chỉ cấp quyền trên key ID hoặc nhóm khóa cần thiết.
- **Theo thao tác:** chỉ cho phép encrypt, sign hoặc decrypt khi nhiệm vụ thực sự cần.
- **Theo danh tính:** ràng buộc với service account, workload identity hoặc người dùng đã xác thực.
- **Theo môi trường:** tách khóa và quyền của development, test, staging và production.
- **Theo tenant/dữ liệu:** giới hạn quyền theo tenant, phân loại dữ liệu hoặc encryption context.
- **Theo thời gian:** quyền tạm thời có thời hạn và tự hết hiệu lực khi hoàn tất tác vụ.
- **Theo điều kiện:** yêu cầu nguồn gọi, trạng thái workload, phê duyệt hoặc ngữ cảnh hợp lệ.

Ví dụ, một dịch vụ chỉ ghi dữ liệu có thể cần quyền encrypt nhưng không cần decrypt. Một dịch vụ chỉ kiểm tra chữ ký có thể dùng public key mà không được truy cập private key. Một dịch vụ xử lý hồ sơ của tenant A không nên được phép dùng khóa của tenant B.

Không cấp quyền wildcard trên toàn bộ khóa hoặc mọi thao tác nếu ứng dụng chỉ cần một tập nhỏ. Quyền rộng làm tăng blast radius khi token, máy chủ hoặc tài khoản dịch vụ bị xâm nhập.

## 4. Danh tính, role và mô hình cấp quyền

Quyền sử dụng khóa thường được quyết định từ danh tính caller kết hợp với policy. Có một số mô hình phổ biến:

### RBAC – Role-Based Access Control

RBAC gán quyền cho role, sau đó gán người dùng hoặc workload vào role. Ví dụ:

- **payment-signer:** chỉ được ký bằng khóa của dịch vụ thanh toán.
- **document-reader:** được decrypt các DEK thuộc nhóm hồ sơ được giao.
- **key-auditor:** chỉ được xem metadata và audit log.
- **key-operator:** được rotate hoặc disable theo quy trình, không được export key material.

RBAC dễ quản trị khi tổ chức có vai trò ổn định. Tuy nhiên, role quá rộng hoặc có quá nhiều thành viên sẽ làm giảm hiệu quả least privilege.

### ABAC – Attribute-Based Access Control

ABAC quyết định quyền dựa trên thuộc tính của principal, khóa và request. Thuộc tính có thể gồm:

- Principal: service identity, team, workload, tenant hoặc environment.
- Resource: key ID, key purpose, classification, owner hoặc trạng thái.
- Action: encrypt, decrypt, sign, rotate hoặc destroy.
- Context: thời gian, nguồn gọi, workload attestation, request purpose hoặc encryption context.

Ví dụ, chỉ cho phép service identity của ứng dụng đơn hàng gọi decrypt trên khóa của tenant tương ứng khi request có encryption context khớp tenant và môi trường production. ABAC linh hoạt nhưng policy cần được kiểm thử để tránh điều kiện thiếu hoặc biểu thức quá rộng.

### ACL, resource policy và grant

Một hệ thống có thể dùng danh sách quyền trên từng khóa (ACL), resource policy gắn với key, hoặc grant tạm thời cho một principal. Grant hữu ích khi cần cấp quyền giới hạn trong một tác vụ, nhưng phải có thời hạn, phạm vi thao tác và quy trình thu hồi rõ ràng.

Dù dùng mô hình nào, policy nên mặc định từ chối (deny by default), chỉ mở quyền cần thiết và có cách thể hiện explicit deny cho thao tác bị cấm. Phải hiểu thứ tự đánh giá giữa identity policy, resource policy, organization policy, permission boundary và grant của nền tảng đang dùng.

## 5. Tách quyền sử dụng khóa khỏi quyền quản trị khóa

Một thiết kế an toàn thường chia thành hai nhóm:

**Data plane** xử lý các thao tác mật mã phục vụ nghiệp vụ: encrypt, decrypt, sign, verify, MAC, wrap và unwrap. Các ứng dụng chạy thường xuyên thường chỉ cần một phần nhỏ của nhóm này.

**Control plane** quản lý tài sản khóa: tạo, import, thay policy, cấp grant, rotate, disable, backup, restore và destroy. Các thao tác này thường do nhóm bảo mật hoặc vận hành khóa thực hiện qua quy trình được phê duyệt.

| Vai trò | Quyền phù hợp | Quyền cần hạn chế |
|---|---|---|
| Ứng dụng mã hóa | Encrypt với khóa của ứng dụng/tenant. | Grant, export, destroy, đổi policy. |
| Dịch vụ ký | Sign bằng khóa ký được chỉ định. | Export private key, tạo grant, thay mục đích khóa. |
| Dịch vụ xác minh | Verify bằng public key. | Sign, decrypt bằng khóa riêng hoặc khóa đối xứng. |
| Dịch vụ giải mã | Decrypt/unwrap trong phạm vi dữ liệu được giao. | Quản trị key policy và cấp quyền cho caller khác. |
| Key operator | Tạo, rotate, disable hoặc restore theo phê duyệt. | Tự ý dùng khóa để đọc dữ liệu nghiệp vụ hoặc export key. |
| Security administrator | Quản lý policy và phê duyệt grant. | Thực hiện đơn phương thao tác phá hủy không có kiểm soát. |
| Auditor | Xem metadata và audit event. | Encrypt/decrypt/sign, thay policy hoặc destroy. |

Việc tách vai trò giảm nguy cơ một tài khoản vừa tạo khóa, tự cấp quyền, sử dụng khóa để truy cập dữ liệu rồi xóa dấu vết. Với thao tác nhạy cảm như export hoặc destroy, có thể yêu cầu dual control, quorum hoặc phê duyệt độc lập.

## 6. Quyền theo mục đích sử dụng và loại khóa

Khóa nên được tạo với mục đích rõ ràng. Không nên dùng cùng một khóa cho nhiều mục đích không liên quan chỉ vì thuật toán hỗ trợ.

| Loại khóa | Quyền thường cần | Quyền nên hạn chế |
|---|---|---|
| AES data encryption key | Encrypt/decrypt dữ liệu thuộc phạm vi được giao. | Export, dùng làm MAC key, chia sẻ giữa tenant. |
| Key Encryption Key (KEK) | Wrap/unwrap DEK theo policy. | Dùng mã hóa trực tiếp dữ liệu nghiệp vụ hoặc export. |
| RSA/EC signing private key | Sign theo thuật toán và mục đích đã định. | Decrypt nếu không cần, export private key, thay policy. |
| Public verification key | Verify chữ ký; đọc public key nếu cần. | Không có private operation; kiểm tra nguồn gốc và tính toàn vẹn. |
| TLS private key | Thực hiện thao tác handshake/ký phù hợp với chứng thư. | Dùng cho ký nghiệp vụ không liên quan hoặc export. |
| HMAC key | Tạo/kiểm tra MAC trong giao thức được chỉ định. | Dùng làm khóa AES hoặc chia sẻ cho bên không cần quyền xác thực. |

Nếu một khóa được phép dùng cho nhiều thao tác, cần có lý do thiết kế và policy thể hiện rõ. Tách khóa theo purpose giúp giới hạn tác động khi một ứng dụng hoặc giao thức bị xâm nhập.

## 7. Use key permission trong Java

Java KeyStore API cung cấp cơ chế nạp và truy cập mục khóa, nhưng **KeyStore không phải một hệ thống phân quyền hoàn chỉnh cho từng thao tác nghiệp vụ**. Khả năng gọi getKey hoặc dùng PrivateKey còn phụ thuộc quyền đọc tệp, mật khẩu, danh tính tiến trình, provider và nơi lưu khóa.

Nếu khóa riêng được xuất vào heap JVM, bất kỳ mã nào trong tiến trình có thể truy cập đối tượng đó đều có thể cố gắng dùng nó theo quyền của tiến trình. Việc đặt alias khó đoán hoặc giấu tên khóa không thay thế authorization. Nếu cần kiểm soát theo từng thao tác và từng caller, hãy thực thi quyền tại KMS/HSM hoặc một dịch vụ ký/giải mã có xác thực và policy ở phía server.

### Ví dụ dùng khóa cục bộ trong JCA

~~~java
import java.security.PrivateKey;
import java.security.Signature;

public byte[] sign(byte[] message, PrivateKey privateKey)
        throws Exception {
    Signature signature = Signature.getInstance("SHA256withRSA");
    signature.initSign(privateKey);
    signature.update(message);
    return signature.sign();
}
~~~

Đoạn mã minh họa thao tác ký. Nếu PrivateKey là khóa phần mềm có thể xuất, việc kiểm soát ai được gọi phương thức sign chủ yếu phải được thực hiện ở tầng ứng dụng và hệ điều hành. Nếu PrivateKey là handle do provider HSM cung cấp, provider có thể chuyển thao tác ký vào thiết bị; HSM có thể áp dụng policy riêng. Không được giả định chỉ dùng JCA là tự có phân quyền theo principal.

### Ví dụ gọi dịch vụ ký có authorization phía server

~~~java
public interface SigningService {
    byte[] sign(
            String keyId,
            String algorithm,
            byte[] message,
            RequestContext context) throws Exception;
}

public byte[] signInvoice(
        SigningService signingService,
        String keyId,
        byte[] invoiceDigest,
        RequestContext authenticatedContext) throws Exception {

    return signingService.sign(
            keyId,
            "SHA256withRSA",
            invoiceDigest,
            authenticatedContext);
}
~~~

Đây là giao diện minh họa do ứng dụng định nghĩa. Trong triển khai thật, danh tính caller phải được xác minh bằng token/chứng thư hoặc workload identity; server/KMS phải tự đánh giá policy dựa trên danh tính đã xác thực. Không tin một trường principal hoặc role do caller tự gửi trong RequestContext nếu trường đó chưa được ràng buộc với thông tin xác thực.

Authorization phải được kiểm tra cho từng thao tác nhạy cảm tại ranh giới tin cậy. Không dựa vào một lần kiểm tra ở giao diện người dùng hoặc một biến boolean trong client, vì caller có thể bỏ qua client và gọi API trực tiếp.

## 8. X.509 KeyUsage khác với quyền truy cập khóa

Chứng thư X.509 có extension **KeyUsage** và **ExtendedKeyUsage (EKU)** để mô tả những mục đích mật mã mà khóa công khai trong chứng thư được phép phục vụ theo chính sách PKI.

Ví dụ KeyUsage có các bit:

- digitalSignature
- contentCommitment (nonRepudiation)
- keyEncipherment
- dataEncipherment
- keyAgreement
- keyCertSign
- cRLSign

EKU có thể chỉ định mục đích như serverAuth, clientAuth, codeSigning hoặc emailProtection.

Các extension này giúp bên xác minh đánh giá chứng thư có phù hợp với mục đích đang dùng hay không. Chúng **không tự cấp quyền truy cập cho một process hoặc user**. Một chứng thư có digitalSignature không có nghĩa mọi ứng dụng trên máy đều được phép ký bằng private key tương ứng. Quyền gọi thao tác ký vẫn phải được kiểm soát bởi KMS/HSM, hệ điều hành, provider hoặc dịch vụ ký.

Ngược lại, policy KMS cho phép một principal gọi sign cũng không thay thế việc kiểm tra chứng thư và mục đích sử dụng theo PKI. Cần áp dụng đồng thời:

1. Authorization: caller có quyền gọi thao tác trên key ID này không?
2. Key policy/algorithm constraints: khóa có được phép dùng cho thao tác và thuật toán đó không?
3. Certificate validation: chứng thư, chuỗi tin cậy, thời hạn, KeyUsage/EKU và danh tính có hợp lệ không?

## 9. Quyền truy cập theo ngữ cảnh và tenant

Trong hệ thống nhiều tenant, chỉ kiểm tra quyền trên key ID có thể chưa đủ. Request cần gắn với ngữ cảnh dữ liệu để tránh dùng một quyền decrypt hợp lệ cho dữ liệu của tenant khác.

Một số thuộc tính có thể được ràng buộc:

- Tenant ID hoặc customer ID.
- Environment như production hoặc staging.
- Application ID và workload identity đã xác thực.
- Data classification hoặc purpose.
- Encryption context/AAD đi cùng bản mã.
- Resource path hoặc loại dữ liệu.
- Thời điểm, nguồn gọi và trạng thái phê duyệt.

Ví dụ, một dịch vụ xử lý hồ sơ chỉ được gọi decrypt khi key thuộc tenant tương ứng và encryption context có tenant ID khớp với bản ghi. Encryption context cần được xác thực bởi cơ chế mật mã như AEAD hoặc được KMS ràng buộc theo semantics của dịch vụ; chỉ thêm một trường metadata không được xác thực là chưa đủ.

Không để caller tự chọn tùy ý key ID, tenant hoặc context mà không kiểm tra quyền. Server cần xác định phạm vi từ danh tính đã xác thực và dữ liệu nghiệp vụ, rồi kiểm tra policy trước khi thực hiện thao tác.

## 10. Quy trình cấp và thu hồi quyền sử dụng

Một quy trình cấp quyền nên có các bước:

1. **Xác định nhu cầu:** ứng dụng hoặc nhóm nêu rõ key ID/purpose, thao tác cần dùng, dữ liệu và thời hạn.
2. **Xác minh chủ sở hữu:** xác định owner của khóa và owner của workload.
3. **Đánh giá phạm vi:** chỉ định principal, operation, environment, tenant và điều kiện.
4. **Phê duyệt:** yêu cầu phê duyệt độc lập cho quyền decrypt diện rộng, sign quan trọng, export hoặc thay policy.
5. **Cấp quyền:** cập nhật IAM/key policy hoặc tạo grant có giới hạn.
6. **Kiểm thử:** xác nhận thao tác được phép thành công và thao tác ngoài phạm vi bị từ chối.
7. **Theo dõi:** ghi nhận grant, người phê duyệt, thời điểm, quyền và mục đích.
8. **Rà soát/thu hồi:** loại bỏ quyền khi workload đổi vai trò, ngừng hoạt động hoặc hết thời hạn.

Quyền tạm thời nên có TTL và cơ chế tự thu hồi. Quyền dài hạn cần được rà soát định kỳ, nhất là quyền decrypt, sign, export và quản trị policy.

Khi thu hồi quyền, cần xem xét propagation delay, token hoặc grant đã phát hành, cache authorization và session đang hoạt động. Không nên tuyên bố quyền đã mất hiệu lực tức thì nếu nền tảng có độ trễ lan truyền. Với sự cố khẩn cấp, cần có cơ chế disable key hoặc chặn principal ở lớp thực thi, đồng thời xác minh backend đã áp dụng thay đổi.

## 11. Mẫu policy minh họa

Mẫu sau mô tả ý tưởng phân quyền ở mức logic. Đây không phải cú pháp của một nhà cung cấp KMS cụ thể:

~~~yaml
key_id: payments-signing-v3
purpose: invoice-signing
default: deny

principals:
  - id: service:invoice-api
    allow:
      - sign
    conditions:
      environment: production
      algorithm: SHA256withRSA
      purpose: invoice-signing

  - id: service:invoice-verifier
    allow:
      - get-public-key
      - verify
    conditions:
      environment:
        - production
        - staging

  - id: group:key-auditors
    allow:
      - view-metadata
      - view-audit-events

administration:
  allow:
    - rotate: group:key-operators
    - change-policy: group:security-admins
    - destroy: group:security-admins
  require_approval:
    - change-policy
    - destroy
~~~

Mẫu thể hiện nguyên tắc: invoice API được ký, verifier chỉ xác minh, auditor chỉ xem metadata/log, còn quyền quản trị được giao cho nhóm riêng. Trong triển khai thật, cần ánh xạ principal sang danh tính đã xác thực, xác định cách đánh giá điều kiện và dùng cú pháp policy được KMS/HSM hỗ trợ.

## 12. Giám sát và audit việc sử dụng khóa

Audit log cần cho biết ai đã yêu cầu thao tác nào trên khóa nào, vào thời điểm nào và kết quả ra sao. Các trường thường hữu ích:

- Principal hoặc workload identity đã xác thực.
- Key ID và phiên bản khóa.
- Operation: encrypt, decrypt, sign, verify, wrap, unwrap, export hoặc admin action.
- Thời điểm, nguồn gọi, request ID và môi trường.
- Context/tenant đã được che hoặc chuẩn hóa phù hợp.
- Kết quả allow/deny và lý do policy ở mức không tiết lộ dữ liệu nhạy cảm.
- Grant hoặc approval ID nếu thao tác cần phê duyệt.

Không ghi plaintext, private key, DEK, password, token hoặc toàn bộ request chứa bí mật vào log. Audit log nên được bảo vệ khỏi sửa đổi, có quyền đọc riêng và được chuyển tới hệ thống giám sát độc lập.

Theo dõi các dấu hiệu bất thường:

- Một principal đột ngột gọi decrypt hoặc sign với tần suất tăng cao.
- Một workload yêu cầu khóa của tenant khác.
- Nhiều lần bị từ chối do policy hoặc thử key ID không thuộc phạm vi.
- Quyền export, policy update hoặc destroy được sử dụng ngoài lịch thay đổi.
- Một khóa được gọi từ môi trường hoặc danh tính chưa từng xuất hiện.
- Grant tồn tại lâu hơn thời hạn dự kiến hoặc không được thu hồi.

Audit chỉ có giá trị nếu có quy trình rà soát và phản ứng. Đặt cảnh báo theo mức độ rủi ro, điều tra sự kiện, lưu bằng chứng và cập nhật policy khi phát hiện quyền thừa.

## 13. Các sai lầm thường gặp

**Cấp quyền trên toàn bộ key store.** Một ứng dụng chỉ cần một khóa nhưng được đọc mọi alias hoặc gọi mọi thao tác. Hãy giới hạn theo key ID, purpose và operation.

**Cho ứng dụng quyền quản trị để tiện triển khai.** Ứng dụng nghiệp vụ thường không cần tạo, export, grant, đổi policy hoặc destroy khóa. Tách data plane và control plane.

**Cho rằng alias bí mật là authorization.** Alias chỉ là tên tra cứu. Biết alias không nên đủ để sử dụng khóa; hệ thống phải xác thực caller và kiểm tra policy.

**Cho rằng KeyUsage thay thế IAM.** KeyUsage/EKU ràng buộc mục đích chứng thư trong PKI, không xác định process nào được quyền gọi private key.

**Cho phép decrypt quá rộng.** Quyền decrypt có thể làm lộ toàn bộ dữ liệu mà khóa bảo vệ. Giới hạn theo tenant, resource, context và workload; cân nhắc tách khóa.

**Cho phép export private key mặc định.** Export tạo bản sao key material nằm ngoài ranh giới bảo vệ. Chỉ cho phép khi có nhu cầu được phê duyệt, quy trình truyền và lưu trữ an toàn.

**Không thu hồi grant cũ.** Workload đổi vai trò hoặc ngừng hoạt động nhưng quyền vẫn còn. Rà soát quyền theo vòng đời danh tính và tài sản.

**Tin vào authorization ở client.** Kiểm tra quyền chỉ ở UI hoặc trong mã client có thể bị bỏ qua. Thực thi policy tại KMS/HSM hoặc dịch vụ tin cậy phía server.

**Không kiểm tra quyền sau khi đổi policy.** Policy mới có thể vô tình mở rộng hoặc chặn thao tác. Kiểm thử cả trường hợp allow và deny trước khi triển khai.

## 14. Checklist triển khai Use key permission

- [ ] Mỗi khóa có owner, purpose, algorithm, version và classification rõ ràng.
- [ ] Principal được xác thực bằng danh tính tin cậy; không dùng tên do caller tự khai báo.
- [ ] Quyền được cấp theo key ID, operation, environment và tenant cần thiết.
- [ ] Default deny; chỉ cấp thao tác tối thiểu.
- [ ] Data plane tách khỏi control plane.
- [ ] Quyền export, grant, policy change, disable và destroy được kiểm soát riêng.
- [ ] Dùng RBAC/ABAC/ACL phù hợp và kiểm tra thứ tự đánh giá policy.
- [ ] Có dual control hoặc phê duyệt độc lập cho thao tác rủi ro cao.
- [ ] Authorization được thực thi tại ranh giới tin cậy, không chỉ ở client.
- [ ] X.509 KeyUsage/EKU được kiểm tra riêng với IAM/KMS authorization.
- [ ] Quyền tạm thời có TTL; quyền dài hạn được rà soát định kỳ.
- [ ] Audit log ghi principal, key ID, operation, kết quả và approval nhưng không chứa key material.
- [ ] Đã kiểm thử cả allow, deny, revoke, policy propagation và tình huống khẩn cấp.

Use key permission xác định ai được thực hiện thao tác nào trên một khóa trong ngữ cảnh cụ thể. Khi quyền được ràng buộc theo danh tính, key ID, purpose, operation và tenant, ứng dụng chỉ có khả năng cần thiết để hoàn thành nhiệm vụ. Kết hợp least privilege, tách quyền sử dụng khỏi quản trị, kiểm soát export và audit độc lập giúp giảm rủi ro lộ khóa cũng như hạn chế tác động khi một workload bị xâm nhập.
