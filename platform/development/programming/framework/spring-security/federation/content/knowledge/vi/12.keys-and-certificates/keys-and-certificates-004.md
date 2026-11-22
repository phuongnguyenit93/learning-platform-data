# Bảo quản private key bằng kho bí mật và giới hạn quyền đọc

> **Module:** Spring Security – federation. **Nhóm:** Khóa và chứng thư. Bài học trình bày cách bảo vệ **private key của SAML Service Provider (SP)** dùng ký thông điệp hoặc giải mã Assertion, từ lúc sinh khóa, lưu trữ trong secret manager/KMS/HSM, cấp quyền cho workload, nạp vào Spring Security, xoay khóa đến thu hồi. Ví dụ dùng **Java 17**, **Spring Boot 3.5.x**, **Spring Security 6.x** và môi trường Linux/Kubernetes. Một số cấu hình hạ tầng là trích đoạn minh họa, phải được điều chỉnh và kiểm thử theo nền tảng thực tế.

## 1. Mục tiêu và kiến thức đầu vào

Sau bài này, bạn cần có khả năng:

1. Xác định **private key nào thuộc SP**, private key nào thuộc IdP; phân biệt public signing certificate, public encryption certificate và private signing/decryption key.
2. Giải thích vì sao private key **không được đặt trong source code, Git, Docker image, application.yml, spreadsheet, log, ticket, CI artifacts** hoặc chia sẻ cho đối tác qua email.
3. Chọn mô hình lưu khóa phù hợp giữa **managed secret manager**, **Vault**, **KMS/HSM**, keystore và file secret được mount theo quyền tối thiểu.
4. Thiết kế **least privilege** cho người dùng, CI/CD, workload identity, service account, namespace/tenant và từng secret version.
5. Kiểm soát quyền file, quá trình khởi động, bộ nhớ, backup, audit, thời gian sống của credential và các luồng cấp phát/thu hồi.
6. Cấu hình private signing/decryption key trong **Spring Security SAML 2.0 Relying Party** mà không đưa key thô vào cấu hình công khai.
7. Lập kế hoạch **rotation có overlap** để không làm đứt SSO khi IdP/SP đổi khóa và xử lý incident khi nghi lộ khóa.
8. Chạy chương trình Java 17 để hiểu ký/xác minh mà không in private key, và kiểm thử quyền truy cập secret ở môi trường thực tế.

**Trước khi học:** Biết IdP/SP, SAML Metadata, `KeyDescriptor use="signing"` và `use="encryption"`, Java `PrivateKey`/`PublicKey`, chứng thư X.509, Spring `RelyingPartyRegistration` và kiến thức cơ bản về Linux permission, IAM hoặc Kubernetes RBAC.

**Nguyên tắc xuyên suốt:** Certificate công khai là thứ được **phân phối**; private key là thứ phải **giữ bí mật và giới hạn khả năng sử dụng**. Secret manager bảo vệ việc phân phối và lưu trữ, nhưng không thay thế việc bảo vệ process, host, tài khoản và dữ liệu trong bộ nhớ.

## 2. Private key làm gì trong SAML2?

Trong SAML Federation, khóa được nhìn từ **vai trò và chiều truyền thông**. Cùng một SP có thể dùng một private key để ký `AuthnRequest`, một private key khác để giải mã `EncryptedAssertion`. IdP có các private keys riêng cho việc ký assertion hoặc giải mã thông điệp gửi đến IdP.

| Hành động | Ai giữ **private key**? | Ai dùng public key/certificate? | Có cần đưa private key cho đối tác? |
| --- | --- | --- | --- |
| IdP ký `SAMLResponse` / `Assertion` | **IdP** | SP verify bằng public signing cert của IdP từ metadata đáng tin | **Không** |
| SP ký `AuthnRequest` / logout message | **SP** | IdP verify bằng public signing cert SP trong SP metadata/registration | **Không** |
| IdP mã hóa Assertion gửi SP | **SP** giữ decryption private key | IdP mã hóa cho **public encryption cert SP** | **Không** |
| SP mã hóa message cho IdP (nếu profile hỗ trợ) | **IdP** giữ decryption private key | SP dùng public encryption cert IdP | **Không** |
| SP xác minh IdP signature | SP chỉ cần **public verification certificate IdP** | SP thực hiện verify | Không cần IdP private key |

~~~text
                   IdP                                SP
       Signing private key (IdP)                 Public cert IdP
                 |                                      |
                 +-------- signed Assertion ----------->| verify
                                                        |
       Public encryption cert SP                 Decryption private key SP
                 |                                      |
                 +------- EncryptedAssertion ---------->| decrypt

               IdP                                    SP
       Public signing cert SP                   Signing private key SP
                 |                                      |
            verify |<------ signed AuthnRequest --------+
~~~

**Sai lầm thường gặp:** Đưa **IdP private key** vào ứng dụng SP để “verify SAML”. SP chỉ cần **public certificate của IdP**. Nếu một cấu hình yêu cầu nhập private key để verify chữ ký đến từ IdP, cần xem lại mô hình vì rất có thể đang nhầm signing và verification credentials.

### Private signing key và private decryption key có nên dùng chung?

Một cặp khóa RSA về mặt kỹ thuật có thể dùng cho nhiều mục đích, nhưng **khuyến nghị tách keypair theo mục đích**: signing và decryption có lịch sử sử dụng, tiêu chí revocation, permission và rotation khác nhau. Tránh dùng lại cùng private key cho TLS, SAML, SSH hay môi trường staging/production. Việc tách khóa giúp hạn chế phạm vi ảnh hưởng nếu chỉ một mục đích bị lộ và giúp IdP quản lý đúng `KeyDescriptor@use`.

Với signing key, việc lộ private key có thể cho phép kẻ tấn công ký thông điệp trông như SP (trong phạm vi IdP tin signer). Với decryption key, lộ khóa có thể làm mất bí mật của encrypted Assertion hiện tại hoặc ciphertext đã bị ghi lại. Đây là **hai loại tác động bảo mật khác nhau**.

## 3. Threat model: private key có thể bị lộ từ đâu?

Hãy coi private key là **secret có tác động cao**. Một cách lưu có vẻ an toàn vẫn có nhiều đường rò rỉ.

| Đường tấn công / sai cấu hình | Ví dụ | Kiểm soát cần thiết |
| --- | --- | --- |
| Source code và Git history | Copy nội dung `-----BEGIN PRIVATE KEY-----` vào repository | Secret scanning, deny commit, policy review, rotate ngay nếu bị lộ |
| Build/CI artifacts | Private key được đóng trong JAR, image layer hoặc log pipeline | Runtime injection, short-lived CI identity, không đưa key vào build context |
| CI/CD permissions quá rộng | Token CI được phép đọc toàn bộ secrets production | Tách job deploy khỏi job đọc secret; IAM theo path/role/env |
| Local file permissions | `/opt/app/sp.key` có mode `0644` | Chỉ workload runtime đọc được; volume read-only; hạn chế group/others |
| Environment variables | Secret xuất hiện trong process environment, crash diagnostics hoặc tool inspection | Ưu tiên file mount/IPC có bảo vệ hoặc hardware-backed operations; không echo env |
| Container/Kubernetes access | Người có quyền tạo pod hoặc exec vào pod đọc secret mount | Pod admission/RBAC, hạn chế exec/debug, privilege và image |
| Backup/snapshot | etcd backup, disk snapshot, artifact backup chứa secret | Encryption at rest, RBAC, retention/restore drills và kiểm kê bản sao |
| Debugging/APM/log | Stack trace, actuator env, heap dump hoặc HTTP trace ghi khóa | Masking, hạn chế endpoints/dumps, policy support có kiểm soát |
| Máy chủ bị xâm nhập | Root/privileged process đọc file hoặc memory | Hardening node/host, phân đoạn mạng, workload isolation, monitoring |
| Secret manager credential bị lộ | Token Vault dài hạn lưu trong config | Workload identity, token TTL ngắn, scope chặt, audit/revoke |
| Nhầm môi trường/tenant | Staging workload đọc private key production | Mỗi env/tenant có identity và key riêng, deny cross-scope |
| Luân chuyển khóa kém | Khóa cũ vẫn được tin hoặc giải mã vô thời hạn | Quản lý lifecycle, expiry, removal và secret versions |

**Secret không chỉ là chuỗi:** Private key trong PEM/PKCS#8/PKCS#12, Java `PrivateKey` object, memory, bản sao backup, keystore password và service-account token được dùng để tải key đều cần kiểm soát. Một key bị mã hóa trong kho vẫn có thể rò rỉ khi app lấy bản plaintext để ký/giải mã.

## 4. Chọn kho bí mật: Secret Manager, Vault, KMS hay HSM?

Không có một lựa chọn duy nhất cho mọi tổ chức. Hãy bắt đầu từ yêu cầu **key có được export ra ngoài không**, latency/availability, khả năng tích hợp Spring/OpenSAML và ràng buộc tuân thủ.

| Giải pháp | Thường làm gì? | Ưu điểm | Rủi ro/giới hạn |
| --- | --- | --- | --- |
| Managed secrets service (AWS Secrets Manager, Google Secret Manager, Azure Key Vault secrets) | Lưu phiên bản **secret blob** như PEM/PKCS#8/PKCS#12, cấp quyền đọc theo IAM | Encryption at rest, audit, versioning, replication theo dịch vụ | Ứng dụng vẫn có thể nhận plaintext key; quyền đọc và runtime compromise vẫn quan trọng |
| HashiCorp Vault KV / secret engine phù hợp | Lưu và phân phối key/secret cho workload có identity, policy và audit | Có thể quản lý path/version/lease và môi trường đa nền tảng | Cần bảo đảm Vault token, unseal, HA, network/authn, policy |
| Cloud KMS **symmetric envelope encryption** | Dùng data key được bảo vệ để mã hóa blob secret ở storage | Hạn chế plaintext at rest, policy với decrypt API | App có thể giải mã ra plaintext private key; không tự tạo non-exportable signing |
| KMS/HSM **asymmetric key operations** | Tạo/giữ private key **không xuất được**, ký/giải mã qua API/PKCS#11/provider | Giảm khả năng lấy bản private key thô | Không phải drop-in cho mọi OpenSAML/Spring API, binding và thuật toán; cần provider/adapter và test |
| PKCS#12 keystore trên disk đã bảo vệ | Lưu private key + certificate chain, khóa bằng passphrase | Hệ sinh thái Java hỗ trợ, quản trị tập trung ở file | Phải bảo vệ keystore **và** passphrase; password ở cùng nơi không giúp nhiều |
| Read-only secret volume / tmpfs mount | Cung cấp key tạm vào container qua volume | Dễ dùng với Spring `file:` Resource | Key plaintext có thể được đọc bởi process có quyền và privileged host/pod |
| Hệ thống tệp cục bộ không quản lý | Copy `.key` thủ công lên VM | Dễ khởi đầu thử nghiệm | Rủi ro sao chép, thay đổi không được audit, backup và rotation khó |

**Phân biệt KMS và Secret Manager:** Một secret manager có thể lưu **PEM private key dưới dạng secret**; cloud KMS có thể mã hóa blob đó (envelope encryption). Nếu đưa blob về runtime và giải mã, Java vẫn có key plaintext trong process. HSM/KMS asymmetric **non-exportable** giữ key trong backend mật mã và chỉ cho phép operations ký/giải mã, nhưng đòi hỏi thư viện hỗ trợ JCA/PKCS#11 hoặc API tích hợp. Không quảng cáo “đưa PEM vào KMS là private key không bao giờ rời KMS” nếu ứng dụng vẫn tải được PEM.

### 4.1. Tiêu chí chọn giải pháp

1. **Threat model:** Chống leak do Git/CI là tối thiểu; có cần chống root trên node, memory dump, insider hoặc side-channel không?
2. **Khả năng export:** Nếu private key tuyệt đối không được export, ưu tiên HSM/KMS bất đối xứng với provider tương thích thay vì lưu blob PEM.
3. **Quyền và identity:** Có workload identity theo service account/environment không? IAM có scope tới từng secret/key/version không?
4. **Audit:** Có log metadata ai/role nào đọc, dùng ký hoặc xoay khóa; log có thể chống sửa và không chứa plaintext?
5. **Vòng đời:** Hỗ trợ version, rotation, overlapping keys, revoked permissions và break-glass?
6. **Runtime:** Khi kho bí mật/KMS tạm không hoạt động, app sẽ khởi động/tiếp tục xử lý ra sao? Có timeout/cache policy không?
7. **Chi phí/độ trễ:** HSM/KMS remote signing có latency, quota và billing khác so với local `PrivateKey`; cần đo với traffic SSO thực.
8. **Tuân thủ:** Độ dài/loại thuật toán, FIPS, data residency, thời hạn bảo quản và tiêu chuẩn nội bộ.

### 4.2. Kiến trúc phân phối khóa ít đặc quyền

~~~text
Production SP workload identity
   |  (mTLS / OIDC workload identity / IAM role / Vault auth)
   v
Secret manager hoặc HSM/KMS
   |  kiểm policy: đúng app, đúng env, đúng purpose
   |  audit: ai, khi nào, secret version, allow/deny
   v
Cách A: inject PEM/PKCS#8 qua protected read-only volume
          |
       Java/Spring đọc key khi khởi động
          |
       ký AuthnRequest / giải mã Assertion

Cách B: HSM / KMS PKCS#11 / compatible JCA provider
          |
       Java giữ key handle, không export raw private key
          |
       crypto operation theo key purpose và policy
~~~

Trong cách A, hãy xem **file, runtime memory và host** là những điểm nhạy cảm. Trong cách B, hãy xem **quyền gọi signing/decryption API**, key handle, thuật toán và logs cũng nhạy cảm; một attacker chiếm process có thể lạm dụng quyền ký dù không tải được raw key.

## 5. Principle of least privilege: ai được phép xem private key?

Quyền cần thiết không phải đơn giản “có quyền đọc secrets” mà là **quyền tối thiểu theo vai trò, mục đích và môi trường**.

| Principal | Có thể làm | Không nên có |
| --- | --- | --- |
| SP runtime production | Đọc đúng signing/decryption key production hoặc gọi crypto operation cần thiết | List toàn bộ secrets, đọc staging, xóa key, cấp quyền IAM cho người khác |
| CI build/test | Build artifact, unit tests bằng **test-only keys** | Đọc production private keys |
| Deployment automation | Triển khai cấu hình đã phê duyệt, chỉ có permission cần thiết cho release | Đọc plaintext key nếu runtime tự nạp bằng workload identity |
| Security admin / key custodian | Tạo/rotate/revoke theo change control, audit | Sử dụng key cho login nghiệp vụ không có lý do |
| Developer | Đọc tài liệu, certificate công khai và dummy key test | Đọc prod private key qua ticket, Slack, kho repo, secret manager |
| IdP đối tác | Nhận SP **public** signing/encryption certificate | Private key của SP |
| Monitoring agent | Đọc metrics trạng thái/metadata đã sanitize | Dump private key, env, keystore, heap |
| SRE break-glass | Quyền khẩn cấp có approval, MFA, TTL ngắn, audit | Quyền vĩnh viễn vô hạn tới mọi môi trường |

### 5.1. Chia quyền theo key purpose

Giả sử kho bí mật có các đường dẫn logic:

~~~text
/org/prod/saml/portal/signing-key
/org/prod/saml/portal/decryption-key
/org/staging/saml/portal/signing-key
/org/prod/saml/payroll/signing-key
~~~

SP Portal production chỉ cần hai key đầu (hoặc chỉ decryption nếu thực tế không ký request). Dùng **deny by default**, grant read trên **đúng secret ARN/path/key ID**, tránh wildcard `/org/*` hoặc quyền quản trị tài nguyên. Nếu một app chỉ verify IdP signature, nó **không cần quyền đọc IdP private key**.

Trong secret manager có versioning, policy còn có thể giới hạn version/stage được dùng và thao tác `read/describe`; quyền `delete`, `update`, `grant`, `list` được cấp riêng cho pipeline rotation và key custodians. Không cấp quyền đọc toàn bộ secret versions chỉ để xử lý một release nếu có thể hạn chế.

### 5.2. Workload identity thay vì credential cố định

Với cloud/Kubernetes, workload nên xác thực tới secret manager bằng cơ chế danh tính của platform (service account liên kết IAM role, workload identity federation, managed identity, Vault Kubernetes auth và TTL ngắn), thay vì đặt một API token dài hạn trong YAML/env để tải private key. Nhưng workload identity chỉ an toàn khi:

- Service account không dùng chung nhiều ứng dụng có mức độ tin cậy khác nhau.
- Token bị giới hạn **audience, subject, TTL và scope**, không thể tùy tiện assume role khác.
- IAM role chỉ cho phép secret cụ thể và, nếu cần, key KMS cụ thể.
- Pod/node/CI có policy hạn chế ai được gắn service account hoặc deploy workload giả mạo.
- Việc thu hồi/rotation identity có đường xử lý và audit.

**Không nên xem Kubernetes namespace là một biên bảo mật tuyệt đối.** Quyền tạo/exec pod, thao tác admission, mount hostPath hoặc quyền cluster-admin có thể mở đường truy cập secret dù không có lệnh `kubectl get secret` trực tiếp. Luôn xét cả quyền **tạo Pod sử dụng Secret**.

## 6. Mẫu triển khai: đưa private key vào runtime an toàn

Một kiến trúc thực tế cho Spring Security trên VM/container:

1. **Sinh keypair** trong quy trình được phê duyệt; đủ độ mạnh, thuật toán phù hợp IdP và chính sách mật mã. Không dùng key production để làm bài tập.
2. Bảo vệ private key bằng secret manager/HSM. Nếu buộc xuất PEM, dùng PKCS#8 hoặc định dạng library hỗ trợ, truyền qua TLS, không log/echo.
3. Cấp quyền chỉ cho **runtime identity** tải key/version phù hợp.
4. Mount thành file trong thư mục chỉ app đọc; không đưa key vào image/JAR, command-line arguments hoặc config Git.
5. Khởi chạy ứng dụng với user **không phải root**; nếu có thể mount **read-only** và hạn chế quyền file.
6. Spring Security nạp private key thông qua `Resource`/cấu hình hoặc JCA provider được kiểm soát.
7. Log **trạng thái nạp/phiên bản/fingerprint public certificate** khi cần, không log bytes/private key/password.
8. Tự động kiểm thử quyền đọc hợp lệ, fail-closed nếu key không truy cập được, version sai hoặc cert không khớp.
9. Quản lý rotation/restart/reload theo cách mà phiên bản Spring Security và secret provider **thật sự hỗ trợ**.
10. Khi chấm dứt workload, thu hồi credential và dọn file tạm/volume theo lifecycle.

### Vì sao file mount thường tốt hơn environment variable?

Một environment variable có thể bị lộ qua process inspection, chẩn đoán crash, CI logs, actuator env endpoint hoặc việc vô tình in cấu hình. Mount file với quyền POSIX hẹp và read-only giảm một số đường leak và phù hợp với `file:` Resource của Spring Boot. Tuy nhiên **file mount không tự miễn nhiễm** với host root, người có quyền exec vào container, memory dump, backup/snapshot hoặc quy trình debug đọc file.

Không nên coi việc chạy `rm sp-private.key` là phương án xóa chắc chắn trên mọi loại storage có snapshot/layer/SSD. Quản lý lifecycle trong secret manager, quyền truy cập, bản backup và encryption-at-rest quan trọng hơn.

## 7. Quyền Linux: user, group, mode và đường dẫn

Trên Linux, một file private key thông thường (không cần group access) có thể áp quyền `0600` cho user ứng dụng. Nếu được owner chỉ đọc và không cần ghi, có thể cân nhắc `0400`. Thư mục chứa secret phải có quyền traversal cần thiết cho runtime và không mở rộng cho user khác.

~~~bash
# Chỉ là ví dụ vận hành trên máy test, chạy bởi admin có quyền phù hợp.
# File đã được secret provisioning tạo sẵn từ nguồn đáng tin.
chown saml-app:saml-app /run/secrets/sp-signing.key
chmod 0400 /run/secrets/sp-signing.key

# Xem metadata, KHÔNG hiển thị nội dung.
stat -c '%a %U %G %n' /run/secrets/sp-signing.key
~~~

Trong ví dụ owner là `saml-app`, mode `0400` nghĩa **owner read**, không cho group/others. **Lệnh `chmod`/`chown` chỉ phù hợp khi filesystem cho phép**; các secret volumes được quản lý bởi orchestrator có thể read-only và có cơ chế permission riêng. Không chạy chmod trên pod production khi không rõ provider/mount.

**Phân biệt quyền thư mục:** một file `0400` không có ý nghĩa bảo mật như mong muốn nếu kẻ khác có khả năng thay file trong thư mục, thay symlink hoặc mount đè đường dẫn. Hãy hạn chế write với parent directories và chống việc ứng dụng tải key từ path do user gửi.

**Không đưa private key ra terminal:**

- Tránh `cat /run/secrets/sp-signing.key`, `head`, `kubectl get secret -o yaml`, `echo "$PRIVATE_KEY"`, `printenv` và attach file qua ticket.
- Với chẩn đoán, xem `stat`, inode/file mode, owner, trusted mount source, key version và public certificate metadata.
- Nếu cần xác minh cặp key/cert, dùng công cụ tại host kiểm soát và chỉ in kết quả match/không match, không xuất private key.

## 8. Kubernetes: Secret object không tự bảo đảm an toàn hoàn chỉnh

Theo tài liệu Kubernetes, Secret dùng để chứa dữ liệu nhạy cảm nhưng **Base64 chỉ là encoding**, không phải encryption. Secret data trong etcd cần **encryption at rest** được cấu hình; quyền RBAC cho `get/list/watch` phải được giới hạn. Người có quyền tạo Pod mount Secret vẫn có thể đọc giá trị qua Pod trong những điều kiện nhất định.

Kịch bản phổ biến:

~~~text
External secret manager hoặc Kubernetes Secret
             |
          CSI driver / secret volume / controller
             |
          Pod (SAML SP)
          ├─ container spring-app
          │    /run/secrets/saml/signing.key       (read-only)
          │    /run/secrets/saml/signing.crt       (public)
          │    /run/secrets/saml/decryption.key    (read-only)
          │    /run/secrets/saml/decryption.crt    (public)
          └─ container khác: KHÔNG được mount key
~~~

**Lựa chọn ưu tiên theo threat model:** Nếu phải tích hợp external secret manager, có thể dùng CSI Secrets Store driver hoặc Vault Agent Injector theo khả năng nền tảng. Nhưng CSI driver, controller, sync secret và mount behavior phải có policy rõ: một cấu hình **sync sang Kubernetes Secret** lại tạo thêm bản secret trong Kubernetes và etcd, cần quản trị riêng. Không khẳng định CSI tự loại bỏ mọi bản copy.

### 8.1. Trích đoạn cấu hình Pod SecurityContext và secret volume

Đoạn YAML sau là **một phần của Pod template**, không phải Deployment hoàn chỉnh. Nó minh họa một workload không chạy root và chỉ mount secret vào container cần thiết. `defaultMode: 0440` cho phép owner/group read; `fsGroup` có thể giúp nhóm của runtime đọc volume trong môi trường hỗ trợ. Cần test owner/group/mode thực tế của CSI/Secret volume.

~~~yaml
spec:
  serviceAccountName: saml-portal
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
  containers:
    - name: saml-app
      image: registry.example.org/app/saml-sp:1.0.0
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
      volumeMounts:
        - name: saml-keys
          mountPath: /run/secrets/saml
          readOnly: true
  volumes:
    - name: saml-keys
      secret:
        secretName: saml-portal-runtime
        defaultMode: 0440
~~~

**Không copy nguyên snippet và coi là production-ready.** Namespace, RBAC, pod admission, image signature, network policy, resource limits, Seccomp, secret source, controller và writable `/tmp` cho Java/Tomcat nếu cần còn phải cấu hình. `automountServiceAccountToken: false` phù hợp khi app **không cần token service account trong container** để gọi Kubernetes API. Nếu CSI/sidecar phải lấy token để chứng thực external secret store, cần triển khai workload identity và token projection có phạm vi đúng thay vì tắt tùy tiện.

**Rủi ro quyền:** Nếu mount tạo file owner `root` và mode `0400`, process UID 10001 **không đọc được key**. Dùng ownership/group access có chủ đích (`0440` + group phù hợp trên volume hỗ trợ), chứ không mở `0644`. `fsGroup` không bảo đảm mọi CSI driver sẽ tự điều chỉnh ownership; cần xác nhận behavior cụ thể. Một số Kubernetes projected volumes biểu diễn key bằng **symlink** tới phiên bản dữ liệu; khi kiểm mode phải dereference link đúng cách.

### 8.2. Kiểm tra quyền mà không in secret

Trong một container test chạy cùng user với app:

~~~bash
id

# Stat sau khi dereference symlink, không in file contents.
stat -L -c '%a %u %g %n' /run/secrets/saml/signing.key

# Kiểm tra runtime có thể đọc, chỉ in PASS/FAIL.
if test -r /run/secrets/saml/signing.key; then
  printf '%s\n' 'KEY_READABLE_BY_APP=PASS'
else
  printf '%s\n' 'KEY_READABLE_BY_APP=FAIL'
fi
~~~

Nếu `KEY_READABLE_BY_APP=FAIL`, kiểm UID/GID, fsGroup, Secret volume mode, đường dẫn và container mount. **Không sửa bằng cách cho everyone-read**. Nếu attacker có đặc quyền root/exec trên host, chỉ file mode không đủ; cần kết hợp node security và quyền deploy/debug.

### 8.3. Kubernetes RBAC: quyền đọc và quyền chạy Pod

- **Secret `get`:** cho phép đọc một Secret cụ thể; cần giới hạn theo namespace và tên khi khả thi.
- **Secret `list/watch`:** có thể làm lộ nội dung nhiều Secrets; không cấp cho workload bình thường nếu không thật sự cần.
- **Pod create/update/exec:** có thể cho phép mount, thay command hoặc đọc secret theo đường vòng; cần xem quyền này khi review security.
- **Namespace/ServiceAccount:** dùng riêng cho production SP; không dùng service account quá rộng giữa môi trường.
- **Admission policy:** giới hạn privileged pod, host mounts, hostPID, image nguồn lạ và quyền gắn service account.
- **Audit:** audit API secret reads và pod modifications; không giả định log của Kubernetes sẽ cho biết từng lần process đọc file volume. Đối với key tải qua external vault, secret manager audit có thể ghi **fetch** nhưng không ghi mỗi lần local Java dùng key.

## 9. Spring Boot 3.5/Spring Security: nạp khóa từ file secret

Spring Boot hỗ trợ các properties cho SAML Relying Party. Với một SP đăng nhập SAML, phân biệt:

- **SP signing credential:** **private key và public certificate của SP**, dùng SP ký `AuthnRequest`/logout message khi cấu hình yêu cầu.
- **SP decryption credential:** **private key và public certificate của SP**, dùng giải mã `EncryptedAssertion`/`EncryptedID` do IdP gửi.
- **IdP verification credential:** **chỉ public signing certificate của IdP**, dùng verify chữ ký Response/Assertion.
- IdP metadata cũng cung cấp entity ID và các endpoint cần thiết, nếu được lấy từ nguồn đáng tin.

**Ví dụ `src/main/resources/application.yml`:**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: https://idp.example.org/saml/metadata
            signing:
              credentials:
                - private-key-location: file:/run/secrets/saml/signing.key
                  certificate-location: file:/run/secrets/saml/signing.crt
            decryption:
              credentials:
                - private-key-location: file:/run/secrets/saml/decryption.key
                  certificate-location: file:/run/secrets/saml/decryption.crt
~~~

Các đường dẫn này giả định secret provisioning đã tạo các file đúng định dạng/trust; **không tạo file từ khóa thật trong project**. Nếu IdP metadata URI không hoạt động, phải thay bằng nguồn IdP đã được phê duyệt; không tải metadata từ input do người dùng gửi. Nếu IdP chỉ cần SP nhận Response đã ký, không bắt buộc thêm signing/decryption credentials **chỉ vì module SAML được bật**.

**Yêu cầu định dạng:** Các properties dạng private-key-location thường đọc private key từ PEM phù hợp với Spring Security/SAML credential loader (thường PKCS#8). Một PEM encrypted bằng passphrase hoặc PKCS#1 cũ có thể cần chuyển đổi an toàn hoặc custom loader/crypto provider; không tự giả định loader properties hỗ trợ mọi file. **Không chuyển secret vào unencrypted source tree để ứng dụng khởi động được.**

### 9.1. Tệp `pom.xml` cho ứng dụng demo

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>saml-secret-protection</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <repositories>
    <repository>
      <id>shibboleth-releases</id>
      <url>https://build.shibboleth.net/maven/releases</url>
      <snapshots><enabled>false</enabled></snapshots>
    </repository>
  </repositories>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-saml2-service-provider</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Ví dụ `src/main/java/demo/SamlSecretApplication.java`:**

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SamlSecretApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlSecretApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class HomeController {
        @GetMapping("/")
        String home() {
            return "SAML SP is running";
        }
    }
}
~~~

Nếu metadata IdP thực tế và credentials được mount hợp lệ, chạy `mvn spring-boot:run` từ thư mục project. `GET /` trả đúng **SAML SP is running**. Muốn kiểm SSO, cần đăng ký SP entity ID/ACS/cert tại IdP và tạo user test, rồi truy cập `/saml2/authenticate/corporate`. URL ví dụ không phải IdP thật nên ví dụ **không tự hoàn thành đăng nhập**.

Điểm quan trọng: code Java không đọc private key hoặc in secret qua log. Spring Boot/Spring Security cấu hình credentials qua **filesystem Resource** trong một runtime đã được cấp quyền, thay vì hardcode PEM trong Java. Nhưng việc nạp vẫn có plaintext key material trong Java process trong mô hình file-based; phải tiếp tục harden host/container và giới hạn heap/crash dumps.

### 9.2. Thao tác lỗi nên thất bại khi thiếu khóa

Với IdP đòi signed AuthnRequest, nếu app thiếu signing private key/cert, phải fail theo lỗi cấu hình hoặc request signing; không tắt yêu cầu ký ở IdP để “cho chạy”. Với EncryptedAssertion mà SP thiếu decryption key, **không** yêu cầu IdP bỏ mã hóa một cách tự phát; phải kiểm cặp key/cert, secret mount, rotation và compatibility.

**Không log exception nguyên văn kèm key material**: log loại lỗi, registration ID, secret version và certificate fingerprint công khai nếu cần; che paths nhạy cảm nếu chính sách yêu cầu.

## 10. Java 17 độc lập: tạo và dùng private key mà không xuất khóa

Chương trình sau dùng JDK 17 để sinh keypair **trong bộ nhớ**, ký một thông điệp thử và xác minh bằng public key. Nó cố ý **không gọi `getEncoded()` trên private key và không in key**. Ký bằng `SHA256withRSA` trong ví dụ chỉ để minh họa; production phải chọn thuật toán/độ dài theo policy và tính tương thích SAML IdP/SP.

**Tệp `PrivateKeyUsageDemo.java`:**

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;

public class PrivateKeyUsageDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        byte[] message = "SAML request demo".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(pair.getPublic());
        verifier.update(message);
        boolean originalVerified = verifier.verify(signature);

        Signature modifiedVerifier = Signature.getInstance("SHA256withRSA");
        modifiedVerifier.initVerify(pair.getPublic());
        modifiedVerifier.update(
                "tampered SAML request".getBytes(StandardCharsets.UTF_8));
        boolean tamperedVerified = modifiedVerifier.verify(signature);

        System.out.println("originalVerified=" + originalVerified);
        System.out.println("tamperedVerified=" + tamperedVerified);
        System.out.println("privateKeyPrinted=false");
    }
}
~~~

Chạy:

~~~bash
javac PrivateKeyUsageDemo.java
java PrivateKeyUsageDemo
~~~

**Stdout chính xác:**

~~~text
originalVerified=true
tamperedVerified=false
privateKeyPrinted=false
~~~

**Giải thích:** Private key chỉ được truyền cho `Signature.initSign()`; public key dùng `initVerify()`. Một thay đổi ở dữ liệu làm chữ ký không còn hợp lệ. Chương trình không in/serialize raw private key và không kết nối SAML/IdP; **đây không phải trình tạo SAML Signature** và cũng không chứng minh runtime không còn bản sao key trong bộ nhớ. Java heap, debugger hoặc process có đặc quyền vẫn có thể tiếp cận dữ liệu trong những mô hình key exportable. Với hardware-backed key, `PrivateKey` có thể là một handle/provider object thay vì byte array xuất được; cần kiểm chứng integration cụ thể.

### 10.1. Kiểm tra file secret mà không mở nội dung

Trong Linux container chạy cùng UID/GID với ứng dụng:

~~~bash
id
stat -L -c '%a %u %g %n' /run/secrets/saml/signing.key

if test -r /run/secrets/saml/signing.key; then
  printf '%s\n' 'APP_CAN_READ_SIGNING_KEY=PASS'
else
  printf '%s\n' 'APP_CAN_READ_SIGNING_KEY=FAIL'
fi
~~~

**Không có stdout cố định** cho `id`/`stat` vì phụ thuộc runtime. Việc `test -r` chỉ chứng minh file readable theo quyền của process tại thời điểm đó, **không tự chứng minh owner, secret origin hay key validity**. Cần kiểm tra cả file permission, mount read-only, trusted provider và SAML integration tests. Không sử dụng `cat` để debug private key.

### 10.2. Xác minh cặp private key và certificate theo quy trình an toàn

Khi ứng dụng báo key/certificate mismatch, có thể dùng một công cụ nội bộ tại máy kiểm soát để ký một challenge tạm bằng private key và verify bằng **public key trong certificate**. Chỉ log `match=true/false`, certificate public fingerprint và key version; không in private key hay challenge nếu dữ liệu nhạy cảm. Với private key không export được ở HSM/KMS, dùng signing operation của provider tương ứng và kiểm tra public certificate mà IdP đã đăng ký.

Tránh yêu cầu kỹ sư dán key lên website “certificate checker”. Mọi công cụ đọc private key, kể cả tool chẩn đoán, phải có quyền, audit, review và môi trường hạn chế.

## 11. PKCS#12, PEM và passphrase: bảo vệ cả file lẫn mật khẩu

Các định dạng thường gặp:

| Định dạng | Nội dung | Lưu ý |
| --- | --- | --- |
| PEM `BEGIN PRIVATE KEY` | Private key PKCS#8 không mã hóa ở mức file | Secret manager/mount/permissions và encryption at rest là bắt buộc |
| PEM `BEGIN ENCRYPTED PRIVATE KEY` | PKCS#8 encrypted private key | Cần passphrase qua nguồn bí mật **riêng**, loader/provider hỗ trợ giải mã |
| PEM `BEGIN RSA PRIVATE KEY` | PKCS#1 RSA private key (định dạng cũ) | Không tự giả định `private-key-location` trong mọi version hỗ trợ; chuyển đổi ở môi trường tin cậy nếu cần |
| PKCS#12 `.p12/.pfx` | Keystore chứa private key/certificate và bảo vệ bằng password | Password không nên nằm cùng repo/manifest; quản lý quyền cho cả store và password |
| HSM/PKCS#11 handle | Tham chiếu đến key không export được | Cần JCA provider/algorithm support, slot/session và policy |
| X.509 certificate `.crt/.pem` | Public key và metadata certificate | Không phải private key; vẫn cần phân phối đúng/trusted metadata |

**Lỗi thiết kế:** Mã hóa private key bằng passphrase mạnh nhưng để passphrase trong `application.yml` Git cùng với encrypted PEM. Attacker lấy được hai thứ có thể giải mã. Cần dùng secrets backend/workload identity để phân phối password nếu có, đánh giá liệu một công cụ đọc cả keystore và passphrase có quyền vượt quá mức cần thiết hay không.

**Keystore backup:** Nếu private decryption key bị mất hoàn toàn, dữ liệu SAML đã mã hóa cho public key cũ có thể không giải mã lại được. Nếu key là non-exportable, phải có chiến lược HA, backup/replication theo HSM/KMS provider và DR test; không mặc nhiên “backup private key” bằng cách export trái policy.

### Lưu ý về certificate expiry

Ngày hết hạn của X.509 certificate và lifecycle cryptographic key liên quan nhưng không đồng nhất. Một số SAML federation profile dùng certificate trong metadata như **public key container**, không áp PKIX trust chain/hạn như browser TLS; tuy nhiên chính sách tổ chức vẫn nên giám sát certificate validity, thuật toán và chu kỳ rotation. **Không đợi đến khi hết hạn mới chuẩn bị xoay**, cũng không khẳng định mọi SP tự động từ chối certificate khi `NotAfter` qua nếu chưa kiểm tra đúng validator.

## 12. Rotation private keys phải có thời gian overlap

Rotation không chỉ là thay file. Nó liên quan metadata đối tác, request/response còn hiệu lực, caches và mọi node của hệ thống.

### 12.1. Xoay SP signing key

1. Sinh keypair signing mới, private key vào kho bí mật, public certificate mới được kiểm chứng.
2. Thêm public certificate mới vào **SP metadata**/IdP registration bên cạnh key cũ nếu IdP hỗ trợ overlap; xác nhận IdP đã cập nhật trust.
3. Cấp quyền SP workload đọc/new signing credential; kiểm tra các node đã nạp đúng key (nhiều app chỉ nạp lúc startup).
4. Chuyển SP sang ký `AuthnRequest`/logout bằng private key mới.
5. Quan sát IdP verification failures, signing algorithm, response volume và rollback path.
6. Chỉ retire cert/key cũ khi tất cả IdP đã nhận key mới và yêu cầu ký cũ không còn cần xử lý; gỡ secret versions theo policy.

**Đừng đổi signer trước khi IdP tin public certificate mới**. Nếu không, IdP có thể từ chối mọi AuthnRequest mặc dù SP metadata đã được sửa.

### 12.2. Xoay SP decryption key

1. Sinh decryption keypair mới, private key lưu bí mật và public certificate cho IdP.
2. Nạp **new và old decryption private keys** trong thời gian overlap nếu framework/provider hỗ trợ.
3. Công bố/đăng ký public encryption certificate mới ở phía IdP; xác định IdP đang dùng cert nào, vì nhiều IdP chỉ chọn một.
4. Chuyển IdP sang encrypt bằng public cert mới **sau khi SP thực sự có thể decrypt**.
5. Kiểm tra encrypted Assertion bằng cả old/new public certificates trong thời gian chuyển tiếp, trong môi trường test.
6. Khi bảo đảm không còn ciphertext cũ cần xử lý và bên gửi không dùng cert cũ, thu hồi old decryption private key an toàn.

**Khác signing rotation:** Với decryption, bên **nhận** cần giữ private key cũ đủ lâu để đọc ciphertext do bên gửi còn dùng cert cũ. Không thể đơn giản thay cặp khóa trong SP rồi xóa bản cũ ngay. Cần tính cả các message đang bay, metadata cache và ciphertext lưu trữ nếu có.

### 12.3. Quản lý secret versions và rollout

Một định danh version logic:

~~~text
prod/saml/portal/signing/v3      -> active
prod/saml/portal/signing/v2      -> rollover only
prod/saml/portal/decryption/v5   -> active
prod/saml/portal/decryption/v4   -> read-old-ciphertext only
~~~

Việc alias/label version phụ thuộc secret manager. Tách **policy có thể đọc active** khỏi quyền **có thể xoay key**. Theo dõi deployed version trên từng instance; kiểm tra IdP metadata/registration đã cập nhật. Nếu secret volume tự update file, **không tự suy ra Spring đã reload `PrivateKey` trong memory**: nhiều registration được build lúc startup; cần restart/rebuild/refresh có kiểm soát theo version thư viện.

## 13. Audit và monitoring mà không làm lộ private key

**Nên audit:**

- Workload identity nào gọi secret manager/KMS, secret/key/version nào, thời điểm, kết quả allow/deny.
- Ai tạo, sửa, rotate, revoke, thay policy hoặc truy cập phiên bản cũ.
- Quy trình approval, deployment ID, thay đổi IdP metadata, public certificate fingerprint.
- Các lỗi access denied, đột biến số lần đọc/tải, request từ principal hoặc môi trường lạ.
- KMS/HSM signing/decryption operations nếu backend hỗ trợ audit metadata; ngưỡng sử dụng bất thường.
- Việc bật debug/actuator/heap dump hoặc quyền exec vào pod production.

**Không được audit bằng cách in secret value.** Tránh log raw PEM/private bytes, passphrase, `SAMLResponse`, Assertion, session cookie, auth token hay bản copy của secret. Secret manager có thể log **lượt fetch** nhưng không theo dõi mọi lần app đọc file đã mount hoặc sử dụng key đã nạp trong memory; hãy bổ sung host/container telemetry và application-level events có giới hạn.

**Metrics phù hợp:** `saml_signing_key_version` (giá trị version được phép công bố nội bộ), `secret_fetch_errors_total`, `saml_signature_errors_total`, `saml_decryption_errors_total`, thời gian refresh metadata, cert validity warnings. Không để secret version chứa tenant-sensitive identifier đi ra hệ thống metrics công khai nếu chính sách không cho phép.

## 14. Sự cố mất hoặc lộ private key: runbook

Dấu hiệu: private key xuất hiện trong Git/build artifact, một người trái phép đọc secret path, Secret manager cảnh báo access lạ, private key bị sao chép từ pod hoặc forensic chỉ ra khả năng host compromise.

**Quy trình ưu tiên:**

1. **Containment:** thu hồi/bóp quyền secret và credential bị ảnh hưởng, khóa identity/token đánh cắp, cách ly workload/node nếu cần theo incident policy.
2. **Xác định phạm vi:** key thuộc IdP hay SP, signing hay decryption; môi trường/tenant nào, khoảng thời gian lộ, những bên có thể tin key này.
3. **Rotate:** tạo keypair mới **không tái dùng private key cũ**, đưa vào kho bảo vệ; điều phối metadata/certificate với các đối tác.
4. **Revocation of trust:** nếu signing key bị lộ, không giữ overlap dài vô hạn chỉ để tránh downtime; nhanh chóng loại public key cũ khỏi danh sách verification của đối tác theo incident response.
5. **Bảo vệ dữ liệu:** nếu decryption key bị lộ, đánh giá encrypted assertions/ciphertexts đã bị thu thập hoặc lưu trữ, thời hạn/retention và nghĩa vụ thông báo theo policy.
6. **Session assessment:** xác định có cần thu hồi SSO sessions, làm lại xác thực hoặc khôi phục account links; chỉ triển khai sau khi phân tích ảnh hưởng.
7. **Quét mọi bản sao:** repo/history, container image layers, CI logs, config backups, tickets và crash dumps. Việc xóa key khỏi commit mới **không làm key cũ hết giá trị**.
8. **Audit và postmortem:** giữ chứng cứ log có kiểm soát, khắc phục IAM/secret scanning/CI policy và thử lại runbook.

**Điểm không được bỏ qua:** Nếu một private signing key bị lộ, thay cert công khai mới **không vô hiệu hóa khóa cũ** khi IdP vẫn tin cert cũ. Phải phối hợp gỡ trust cũ. Nếu decryption key bị lộ, thay key giúp bảo vệ ciphertext tương lai nhưng không làm bí mật trở lại các ciphertext lịch sử mà attacker đã có.

## 15. Ma trận kiểm thử và kiểm tra trước go-live

| Ca thử | Kết quả đúng |
| --- | --- |
| Runtime được cấp đúng secret read | App nạp signing/decryption key cần thiết mà không log bytes |
| Một service account khác truy cập cùng secret | `AccessDenied`, có log metadata phù hợp |
| Staging identity cố đọc production private key | Từ chối |
| CI build image không có secret | Build thành công, image layers không chứa key |
| Service account chỉ có `get` một Secret | Không `list/watch` toàn namespace nếu không cần |
| Pod thiếu read permission | Startup/SSO fail rõ nguyên nhân; không mở `0644` để chữa |
| File mode/group của projected volume thay đổi | Test `stat -L` và `test -r` bằng đúng runtime UID/GID |
| Debug endpoint cố trả `application.yml` hoặc env secret | Bị chặn/redact theo policy |
| Key/cert không khớp | Startup/credential validation hoặc cryptographic test fail |
| IdP ký Response bằng certificate được tin | SAML verify pass nếu mọi conditions khác đúng |
| IdP signing cert khác nhưng SP vẫn dùng cert cũ | Fail verification, có kế hoạch metadata rotation |
| SP ký AuthnRequest bằng key mới chưa đăng ký IdP | IdP từ chối; không bỏ requirement ký |
| IdP encrypt Assertion bằng cert cũ, SP chỉ giữ private key mới | Decryption fail; overlap phải được khôi phục đúng |
| IdP encrypt bằng new cert, SP có new decryption key | Giải mã thành công nếu signature/conditions cũng đúng |
| Unauthorized secret read trong audit | Alert được bật, không ghi plaintext |
| Key version bị thu hồi | Workload không thể tải version bị thu hồi; instance cũ được xử lý theo runbook |
| Secret manager tạm mất kết nối | Có chính sách timeout/fail-closed hoặc cache có giới hạn đã phê duyệt |
| Backup/restore key hoặc HSM failover | Khôi phục theo quy trình được phép, không export key trái policy |
| Private key bị commit nhầm | Incident, rotate và xóa bản sao, không chỉ xóa commit |
| Login pass nhưng không có quyền | Authorization 403; không liên quan quyền đọc private key |

### Checklist vận hành ngắn

- [ ] Mỗi environment/tenant dùng keys, role và secret paths riêng.
- [ ] Private signing/decryption keys của SP không nằm trong Git, image, log hoặc source properties.
- [ ] Private keys chỉ được cấp cho workload cần **thực sự ký/giải mã**.
- [ ] IdP verification certificate là **public**, lấy qua metadata đáng tin; không yêu cầu IdP private key.
- [ ] Secret backend có IAM/RBAC least privilege, audit, encryption at rest/in transit và lifecycle versions.
- [ ] Runtime chạy quyền thấp; secret volume read-only, file mode/UID/GID đúng, không cho sidecar không cần thiết mount key.
- [ ] Kubernetes RBAC, quyền create/exec pods, etcd encryption và admission policies được kiểm tra.
- [ ] Spring Security credentials đúng role, URL metadata đáng tin và không mở debug endpoint trả secret.
- [ ] Signing/decryption rotation được thử với old/new keys, IdP/SP metadata và cluster rollout.
- [ ] Có runbook revoke, key compromise, disaster recovery, owner/approval và monitoring.

## 16. Bài tập có đáp án kiểm tra

**Bài A – xác định bên giữ khóa.** IdP ký Assertion, SP kiểm tra. Ai cần private key? **IdP**. SP cần gì? **Public signing certificate IdP được tin**. Khi IdP mã hóa Assertion cho SP, ai cần private decryption key? **SP**.

**Bài B – thiết kế least privilege.** Tổ chức có Portal SP production, Payroll SP production và Portal staging. Viết chính sách để Portal prod chỉ đọc `prod/saml/portal/signing` và `prod/saml/portal/decryption`, không thể list mọi secret hoặc đọc key Payroll/staging. Giải thích ai có quyền rotate và cách audit.

**Bài C – Java 17.** Chạy `PrivateKeyUsageDemo.java` và đối chiếu ba dòng stdout. Sửa message ở verifier và giải thích vì sao verification fail. Kiểm tra bằng mắt thường rằng code không gọi `System.out.println(pair.getPrivate())` và không xuất private key ra file.

**Bài D – Kubernetes.** Trên một cluster test được phép, giả lập file mode `0400` owner root với app UID 10001; xác định vì sao app không đọc được. Chuyển sang mô hình group read có `fsGroup` phù hợp và kiểm chứng bằng `stat -L`/`test -r`. **Không thử bằng cách đưa secret thật vào lab**.

**Bài E – Spring Security.** Chạy project demo với IdP test và secret mounts. Cố tình không mount SP signing key trong một môi trường test mà IdP yêu cầu signed AuthnRequest. Ghi loại lỗi, sau đó khôi phục secret mount thay vì bỏ yêu cầu ký.

**Bài F – rotation.** Vẽ các bước chuyển SP decryption key từ K1 sang K2 khi IdP vẫn gửi encrypted Assertion bằng K1. Nêu vì sao SP cần giữ K1 trong overlap, cách test K1/K2, khi nào được thu hồi K1.

**Bài G – incident.** Giả sử private signing key xuất hiện trong CI logs 30 phút. Phân biệt containment, rotate, revoke IdP trust, rà soát bản sao và audit. Nêu vì sao xóa dòng log mà không thay khóa là chưa đủ.

**Đạt bài khi** bạn giải thích được: (1) private/public key đúng vai trò SAML, (2) secret manager khác non-exportable HSM/KMS, (3) least privilege áp dụng cả IAM và pod/file permissions, (4) cấu hình Spring SAML signing/decryption không hardcode secret, (5) signing vs decryption rotation khác nhau, và (6) có thể chạy Java 17, kiểm thử denial và trình bày incident runbook.

## 17. Nguồn tham khảo chính thức

- Spring Boot 3.5 – Spring Security SAML2 Relying Party properties: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- Spring Security – SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – SAML 2.0 Authentication Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – SAML 2.0 Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- OASIS SAML 2.0 Metadata (KeyDescriptor signing/encryption): https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OASIS SAML 2.0 Core (Signature/Encryption): https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- Kubernetes – Good practices for Secrets: https://kubernetes.io/docs/concepts/security/secrets-good-practices/
- Kubernetes – Secrets concepts and volume mounts: https://kubernetes.io/docs/concepts/configuration/secret/
- Kubernetes – Encrypting Secret Data at Rest: https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/
- OWASP – Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP – Key Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html
