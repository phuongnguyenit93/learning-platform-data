# Virtual HSM

> **Chương:** Key storage  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Virtual HSM là gì?

**Virtual HSM (HSM ảo)** là thuật ngữ dùng cho một **môi trường hoặc dịch vụ cung cấp khả năng quản lý và sử dụng khóa theo giao diện HSM nhưng được trừu tượng hóa thành một đơn vị logic**, chẳng hạn một partition, tenant, instance hoặc dịch vụ được tạo trên hạ tầng dùng chung. Chữ “virtual” mô tả **cách phân bổ, trình bày hoặc vận hành tài nguyên**; **không tự chứng minh vật liệu khóa đang được bảo vệ bằng phần cứng chuyên dụng**.

Hai hệ thống đều có thể được quảng bá là “virtual HSM” nhưng có ranh giới an ninh rất khác nhau:

1. Một **partition HSM logic** nằm trên **HSM vật lý**: nhiều ứng dụng/tenant có vùng khóa riêng, nhưng những kiểm soát vật lý và mật mã có thể do phần cứng nền cung cấp.
2. Một **software HSM** chạy trong VM/container: chương trình mô phỏng một số giao diện, ví dụ PKCS#11, và cất key material trong bộ nhớ/đĩa của hệ điều hành. Nó **không trở thành thiết bị chống can thiệp vật lý** chỉ vì tên chứa “HSM”.

Ngoài ra còn có **managed HSM service** và các kiến trúc kết hợp HSM vật lý, phân vùng logic, dịch vụ mạng, phần mềm quản trị và KMS. Có nhà cung cấp dùng “virtual HSM” làm tên sản phẩm riêng. Vì vậy, khi đánh giá một giải pháp, phải hỏi: **mô hình triển khai thực tế là gì, key material nằm trong security boundary nào, ai có thể trích xuất và cơ chế nào thực thi điều đó?**

### Ví dụ mở đầu

Một nền tảng thanh toán có ba tenant cần giữ **private signing key** tách biệt. Thay vì cấp một thiết bị HSM vật lý cho mỗi tenant, đơn vị vận hành tạo ba **logical partitions** trên cụm HSM có hỗ trợ phân tách phù hợp. Mỗi tenant thấy key store và quyền riêng; ứng dụng ký thông qua API hoặc PKCS#11. Tuy nhiên, **một lỗi phân quyền giữa các partition, quyền quản trị hạ tầng quá rộng hoặc sự cố firmware** vẫn có thể ảnh hưởng toàn hệ thống. Logical isolation phải được **kiểm chứng theo mô hình đe dọa và bảo đảm của nhà cung cấp**, không chỉ tin vào số lượng partition.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **virtual HSM, HSM partition, software HSM/emulator, remote HSM, managed HSM và KMS**.
- Nhận diện **hardware security boundary**, nguy cơ từ hypervisor/OS, tenant isolation và quyền quản trị.
- Thiết kế lưu trữ **DEK/KEK, private signing key, HMAC/PSK**, key generation, non-extractability và vòng đời khóa.
- Hiểu giao diện **PKCS#11, JCA/JCE, KMIP, REST/KMS API**, cùng ví dụ **Java 17 sử dụng provider PKCS#11**.
- Đánh giá **HA, backup, disaster recovery, latency, audit, access control, quorum approval** và sự cố.
- Biết vì sao **cùng chức năng `Sign` hoặc `Unwrap` không có nghĩa cùng mức bảo đảm bảo mật**.

## 2. HSM vật lý và HSM ảo khác nhau như thế nào?

**HSM (Hardware Security Module)** là thiết bị/module mật mã được thiết kế để bảo vệ vật liệu khóa và thực hiện một số thao tác trong **ranh giới bảo mật xác định**. HSM có thể có kiểm soát phần cứng, cơ chế phát hiện can thiệp, phân vai vận hành và hạn chế trích xuất khóa, tùy loại thiết bị và cấu hình.

**Virtualization** tạo ra một hoặc nhiều đơn vị sử dụng logic trên hạ tầng nền. Nó có thể áp dụng ở nhiều lớp:

| Mô hình | Điều đang được “ảo hóa” | Key material ở đâu? | Điều không thể suy ra chỉ từ tên |
| --- | --- | --- | --- |
| **HSM vật lý chuyên dụng** | Không nhất thiết có nhiều tenant | Trong thiết bị/HSM boundary theo cấu hình | Mọi khóa đều không xuất được hoặc tất cả API đều đã an toàn |
| **Partition / virtual HSM trên HSM vật lý** | Slot, partition, domain, tenant hoặc crypto service logic | Có thể trong HSM vật lý dùng chung với ranh giới đã công bố | Cách ly vật lý độc lập cho từng tenant |
| **Managed HSM service** | Lớp dịch vụ, vận hành, API và/hoặc partition | Phụ thuộc kiến trúc và bảo đảm dịch vụ cụ thể | Khách hàng sở hữu riêng một thiết bị phần cứng |
| **Remote/network HSM** | API sử dụng từ máy khác | Trong HSM từ xa nếu đây thực sự là thiết bị HSM | Kênh mạng, client IAM và signer không bị lạm dụng |
| **Software HSM / emulator** | Giao diện và đối tượng khóa được mô phỏng bằng phần mềm | RAM/đĩa của VM/container/host, có thể được mã hóa ở trạng thái nghỉ | Chống can thiệp vật lý hoặc non-extractability tương đương HSM |
| **KMS dựa trên HSM** | Truy cập khóa qua API quản lý ở mức cao | Tùy key type và nhà cung cấp; có thể dùng HSM cho root/wrapping | Mọi phép mã hóa dữ liệu đều thực hiện trong HSM |

**Đừng đánh đồng “virtual HSM” với “SoftHSM”.** Các software token như SoftHSM hữu ích cho học tập, phát triển hoặc kiểm thử PKCS#11, nhưng **không tự cung cấp bảo đảm chống trích xuất khi host bị chiếm** như một hardware boundary được đánh giá.

### 2.1. Những câu hỏi xác minh đầu tiên

1. Nhà cung cấp gọi “virtual” cho **partition phần cứng**, **VM chạy phần mềm**, hay **API managed service**?
2. Vật liệu private/secret key có từng xuất hiện ở **host application, hypervisor, disk snapshot hoặc backup không**?
3. Thuộc tính `non-extractable` được **thực thi bởi module nào**, có ngoại lệ export wrapped/backup không?
4. Một quản trị viên host, cloud control plane, KMS admin hoặc HSM security officer có thể làm gì?
5. Sự cô lập tenant được hỗ trợ bằng **cơ chế kỹ thuật và chứng cứ nào**?
6. Mức chứng nhận/assurance được công bố áp dụng cho **phần cứng, firmware, phần mềm, cấu hình, partition và operation nào**?

Nếu không trả lời được, nên đánh dấu những thuộc tính đó là **chưa xác minh**, không mặc định đánh giá sản phẩm là “an toàn như HSM vật lý”.

## 3. Virtual HSM giải quyết nhu cầu gì?

Một hạ tầng HSM vật lý không nhất thiết phải gắn cố định với đúng một ứng dụng. Virtual HSM hoặc partition có thể giúp **phân bổ tài nguyên mật mã** cho nhiều team/tenant mà vẫn cung cấp API quản lý khóa quen thuộc.

### Lợi ích tiềm năng

- **Tách namespace/key store:** tenant A không thấy key handles của tenant B nếu policy/isolation đúng.
- **Phân quyền theo dịch vụ:** team thanh toán chỉ được `Sign`, team lưu trữ chỉ được `Wrap/Unwrap` đối với khóa được cấp.
- **Tái sử dụng hạ tầng:** một cụm HSM vật lý có thể phục vụ nhiều môi trường logic theo năng lực phần cứng.
- **Tự động hóa provisioning:** tạo partition/token, cấp key references, policies, audit và rotation qua API khi được hỗ trợ.
- **Mở rộng vận hành:** HA cluster, các vùng/khu vực được quản trị, backup và giám sát tập trung.
- **Tích hợp dễ hơn:** ứng dụng có thể dùng JCA/JCE, PKCS#11 hoặc KMS client thay vì tự quản raw keys trong file cấu hình.

### Đổi lại là gì?

- **Shared infrastructure risk:** lỗi firmware, cấu hình hoặc quản trị chung có thể ảnh hưởng nhiều tenant.
- **Phụ thuộc control plane:** identity, provisioner, broker, API gateway và HSM admin trở thành điểm kiểm soát quan trọng.
- **Giới hạn cơ chế riêng theo partition:** một số thuộc tính/key type/operation không giống nhau giữa vendor.
- **Hiệu năng và khả dụng:** crypto operation phải đi qua mạng/provider, có contention, rate limit hoặc quota.
- **Chi phí kiểm chứng:** cần đánh giá vùng tin cậy, hoạt động khôi phục và chứng cứ compliance thay vì chỉ so sánh API.

**Mục tiêu thiết kế không phải “ảo hóa càng nhiều càng tốt” mà là bảo vệ key material và thao tác đúng với mức rủi ro của dữ liệu.**

## 4. Kiến trúc tham khảo của một virtual HSM

~~~mermaid
flowchart TD
    ServiceA[Ứng dụng A / Tenant A] --> Identity[Identity + IAM / approval]
    ServiceB[Ứng dụng B / Tenant B] --> Identity
    Identity --> Broker[HSM client / API gateway / PKCS#11 library]
    Broker --> Transport[mTLS / authenticated channel]
    Transport --> VHA[Virtual partition A]
    Transport --> VHB[Virtual partition B]
    subgraph TrustBoundary["HSM physical/security boundary nếu kiến trúc hỗ trợ"]
        VHA --> KeysA[Private/secret key objects A]
        VHB --> KeysB[Private/secret key objects B]
    end
    Broker --> Audit[Audit và monitoring]
    VHA --> Audit
    VHB --> Audit
    Control[Control plane / security officers] --> VHA
    Control --> VHB
~~~

Sơ đồ là **một kiến trúc có partition logic được phần cứng bảo vệ**; không được áp sơ đồ này cho một VM chỉ chạy software token. Trong mô hình phần mềm, ranh giới chứa `KeysA/KeysB` có thể là **host/VM/container**, nơi hệ điều hành và hypervisor có thể quan sát vật liệu.

### 4.1. Control plane và data plane

**Control plane** quản lý provisioning, tenant/partition, key policy, role, backup, audit config, phiên bản firmware, rotation và lifecycle state. Nó cần quyền quản trị mạnh nhưng **không nên mặc nhiên có quyền ký/giải mã dữ liệu nghiệp vụ**.

**Data plane** thực hiện `GenerateKey`, `Sign`, `Verify`, `Encrypt`, `Decrypt`, `Wrap`, `Unwrap` hoặc một tập operation được nhà cung cấp hỗ trợ. Việc client gọi được API **không có nghĩa thao tác ấy được thực hiện trong HSM**; cần kiểm tra provider selection và key object thực tế.

### 4.2. Điểm kết thúc giao thức bảo mật

Khi application gọi remote HSM qua mạng, cần biết **TLS/mTLS kết thúc ở đâu**. Nếu TLS kết thúc tại gateway không nằm trong hardware boundary, gateway có thể thấy **request metadata và payload được gửi tới đó**, tùy giao thức. Đối với thao tác ký, nội dung được ký có thể qua gateway; với thao tác decrypt, plaintext có thể được trả về ứng dụng.

**Không nên tuyên bố “không bao giờ có plaintext ngoài HSM”** nếu kiến trúc thực sự trả plaintext ra client. Phải phân loại riêng **key material**, **input/output của phép mật mã** và **audit metadata**.

## 5. Security boundary và bảo đảm bảo mật

Đánh giá một virtual HSM nên bắt đầu từ **threat model**, không phải danh sách tính năng.

| Đối thủ/tình huống | Câu hỏi bảo mật | Biện pháp liên quan |
| --- | --- | --- |
| Host VM bị chiếm | Attacker có đọc raw key/keystore/snapshot không? | Hardware-backed boundary thực sự, hạn chế xuất, hardening |
| HSM API credential bị chiếm | Attacker có thể gọi `Sign/Unwrap` trái phép không? | IAM, authorization theo nghiệp vụ, quota, audit |
| Admin control plane lạm quyền | Có thể sửa policy, tạo partition, cấp access không? | Separation of duties, quorum, approval và log độc lập |
| Tenant A tấn công tenant B | Key handles, session, quotas có bị chia sẻ sai không? | Partition isolation, access tests, vendor evidence |
| Mạng bị nghe lén/MITM | Có thể đánh cắp credential hoặc thay request không? | Authenticated transport, mTLS, identity binding |
| Key export/backup bị lộ | Có bản sao secret dưới dạng có thể giải mã không? | Wrapped backup, root protection, custody và restore tests |
| Firmware/provider lỗi | Có thể tạo key yếu hoặc leak qua operation không? | Bản vá, kiểm soát phiên bản, assurance, incident playbook |
| Sự cố vùng/cluster | Khóa còn khả dụng khi HSM node mất không? | Replication/HA theo cơ chế hỗ trợ, DR rehearsal |
| Software HSM trên host bị lấy | Raw key có thể lấy từ RAM/disk không? | Giới hạn dùng software token cho dev/test hoặc threat model phù hợp |

### 5.1. Non-extractable là thuộc tính được thực thi

Một key có thể có **chính sách không xuất được**. Trong PKCS#11, có các thuộc tính như:

- `CKA_PRIVATE`: đối tượng riêng tư, thường cần login phù hợp để truy cập.
- `CKA_SENSITIVE`: hạn chế việc đọc giá trị bí mật của khóa.
- `CKA_EXTRACTABLE`: xác định khả năng trích xuất key material theo semantics và chính sách của token.
- `CKA_NEVER_EXTRACTABLE`, `CKA_ALWAYS_SENSITIVE`: một số chỉ báo thuộc tính/lịch sử do token hỗ trợ.
- `CKA_TOKEN`: đối tượng tồn tại trên token thay vì chỉ trong session.

**Không được suy ra phần cứng chống can thiệp chỉ từ các thuộc tính PKCS#11**: một phần mềm mô phỏng token cũng có thể báo những flags đó, trong khi privileged host vẫn kiểm soát bộ nhớ/tệp chứa key. Bằng chứng mạnh cần ranh giới bảo vệ, implementation và cấu hình thật.

**Không xuất key để thử xem nó có xuất được không đối với khóa production nhạy cảm.** Thử negative path bằng key thử nghiệm và cơ chế API được phê duyệt; xem vendor attestation và thuộc tính.

### 5.2. FIPS 140-2/140-3 và điều kiện đánh giá

Các tiêu chuẩn **FIPS 140** liên quan yêu cầu/bảo đảm cho **cryptographic module** trong phạm vi được đánh giá. Không phải mọi phần của cloud service, gateway, VM hoặc workflow đều nằm trong ranh giới đánh giá.

Một tuyên bố về compliance cần đối chiếu:

1. **Module, phiên bản và cấu hình** nào thực sự nằm trong phạm vi.
2. **Chế độ hoạt động**, firmware/software và cơ chế mật mã được phép.
3. Key generation, key storage, key use và backup đi qua đường nào.
4. Tenant partition có nằm trong **security boundary/assurance** được công bố không.
5. Những yêu cầu của tổ chức ngoài FIPS (IAM, recovery, audit, data authorization) đã được giải quyết chưa.

**HSM được đánh giá không làm toàn bộ ứng dụng tự động đạt chứng nhận.** Tương tự, software HSM dùng thư viện mã hóa có module được đánh giá không tự biến VM thành một hardware HSM.

## 6. Các loại phân tách tenant và giới hạn của virtualization

“Tenant isolation” có thể chỉ một số loại bảo vệ khác nhau:

| Kiểu cách ly | Thứ cần tách | Ví dụ rủi ro nếu sai |
| --- | --- | --- |
| **Namespace** | Tên key, alias, object handle | Tenant A liệt kê khóa tenant B |
| **Authorization** | Vai trò, operation, key usage | Principal A gọi `Sign` trên key B |
| **Crypto object boundary** | Session/token object, persistence | Key handle hoặc context dùng sai partition |
| **Backup/recovery** | Bản sao material và restore credentials | Backup tenant A được restore vào domain B |
| **Audit** | Log theo tenant, quyền đọc metadata | Lộ key ID, actor hoặc pattern giao dịch tenant B |
| **Quota/performance** | Throughput, session count, resource usage | Tenant A gây từ chối dịch vụ cho B |
| **Control plane** | Quyền quản trị partition, policy và provisioning | Admin một tenant sửa policy tenant khác |

### 6.1. Logical isolation không tương đương hardware isolation

Nhiều partition có thể sử dụng chung **chip, firmware, mạng, control plane và root of trust**. Điều này không đồng nghĩa partition không an toàn; nó có nghĩa **cần hiểu phạm vi chia sẻ và failure domain**. Với hệ thống có rủi ro rất cao, có thể cần HSM vật lý riêng, vùng riêng hoặc mô hình custody khác.

### 6.2. Side channels và noisy neighbor

Chia sẻ tài nguyên có thể tạo khác biệt về **latency, throughput, quota và khả năng quan sát**, tùy thiết kế HSM. Các biện pháp của nhà cung cấp có thể giảm rủi ro side-channel, nhưng **không giả định partition hoàn toàn chống mọi kênh phụ**.

Cần đo và giám sát:

- Tải và lỗi theo partition/tenant.
- Thời gian ký/unwrap, session count, rate limiting.
- Khả năng tenant khác ảnh hưởng availability.
- Quy tắc fairness, throttling, capacity reservation.
- Kịch bản firmware update hoặc node failover ảnh hưởng tất cả partition.

## 7. Key storage: key object, slot, token và key version

Trong nhiều triển khai PKCS#11:

- **Slot** đại diện cho vị trí/điểm truy cập token được library công bố; không nhất thiết đúng một thiết bị vật lý.
- **Token** là đối tượng logic chứa các cryptographic objects, metadata và cơ chế login.
- **Session** là ngữ cảnh của client kết nối tới token.
- **Key object/handle** là tham chiếu tới key material hoặc operation-capable object; handle có thể **không ổn định qua session/restart**, tùy provider.
- **Key ID/label** giúp định danh trong token nhưng cần quy ước để tránh trùng lặp.

**Không xem session handle là key ID lâu dài.** Inventory nên lưu **logical key ID + version + provider/partition reference + object identifier được nhà cung cấp bảo đảm đủ ổn định**, đồng thời có quy trình tra cứu/đối chiếu.

### 7.1. Token key khác session key

Một số API cho phép sinh key **chỉ tồn tại trong session** hoặc sinh **persistent token key**. Chính sách lưu trữ, backup và key lifecycle khác nhau rất lớn:

- **Ephemeral/session key:** không cần tồn tại sau khi session kết thúc; có thể được giao thức tạo rồi hủy.
- **Persistent token key:** cần inventory, owner, activation, cryptoperiod, rotation và backup policy rõ.
- **Imported key:** có thể từng xuất hiện ngoài token; provenance không giống key sinh bên trong.
- **Derived key:** có nguồn từ KDF/keying material, cần key separation và policy riêng.

Không kết luận một `KeyGenerator.generateKey()` qua provider PKCS#11 luôn tạo **token key bền vững**; persistence và attributes có thể phụ thuộc cấu hình provider/token và key template.

### 7.2. Quy tắc lưu raw key

Đối với **private signing key hoặc KEK dài hạn**, nếu chính sách đòi hỏi non-extractable, sinh trong security boundary được duyệt và cấm xuất theo khả năng HSM. Với **DEK phục vụ bulk encryption**, một số hệ thống dùng HSM/KMS để tạo **DEK dạng rõ tạm thời ở trusted workload** và wrapped DEK để lưu; trong trường hợp đó raw DEK **đã hiện diện ngoài HSM** theo kiến trúc, cần bảo vệ memory/trace/dump và hạn chế thời gian sống.

**Non-extractable private key không đồng nghĩa plaintext của `Decrypt` sẽ ở lại HSM.** Nếu API trả plaintext cho workload, bảo vệ tài nguyên nghiệp vụ và đường truyền vẫn là điều kiện bắt buộc.

## 8. Giao diện và API: PKCS#11, JCA/JCE, KMIP và KMS API

Virtual HSM có thể được ứng dụng truy cập qua các lớp khác nhau. Đây là sự khác biệt giữa **giao diện** và **bảo đảm về nơi thực thi**.

| Giao diện | Đối tượng phục vụ | Điểm cần kiểm tra |
| --- | --- | --- |
| **PKCS#11** | Token, key objects, sessions, crypto mechanisms | Provider module, slot/token selection, permissions, persistence, mechanism support |
| **JCA/JCE** | Abstraction `KeyStore`, `Signature`, `Cipher`, `KeyGenerator` trong Java | Đúng provider được chọn, không fallback ngoài HSM ngoài ý muốn |
| **KMIP** | Giao thức quản lý key objects/operations ở một số hạ tầng | Profile/implementation thực tế, authentication và semantics |
| **REST/gRPC KMS API** | Managed keys, IAM, audit, wrap/encrypt/sign theo vendor | Key types, state, grants, key version, API có trả raw DEK không |
| **Vendor SDK/CLI** | Operation riêng như partition admin, backup, firmware | Privilege của CLI, audit, environment và version |

### 8.1. Tại sao chỉ gọi `Signature.getInstance(...)` chưa đủ?

Trong Java, nếu không chỉ định provider, JCA có thể chọn một provider phần mềm theo thứ tự ưu tiên. Khi key nằm trong token, một số provider có thể yêu cầu giữ key object thuộc chính provider, trong khi một số thao tác có thể **được thực hiện ngoài HSM** hoặc thất bại do không tương thích.

Để **tránh tự tin sai**, khi thao tác bắt buộc trong HSM cần:

1. Chọn **provider PKCS#11/HSM cụ thể** theo cấu hình được duyệt.
2. Lấy key object qua đúng `KeyStore`/API của provider.
3. Kiểm tra cơ chế `Sign`/`Decrypt` mà token hỗ trợ.
4. Theo dõi **operation ở HSM audit**, không chỉ tên `Signature` của Java.
5. Không dùng `getEncoded()` để lấy private key làm “bằng chứng” đã kết nối token.

### 8.2. Session, login và PIN

Với token yêu cầu login, có thể dùng **PIN hoặc cơ chế xác thực riêng** của nhà cung cấp. PIN là **credential nhạy cảm**, cần được nhập/nhận qua kênh phù hợp, không hard-code trong repository, environment dễ đọc hoặc log.

HSM có thể có **Security Officer, Crypto Officer, Crypto User** hay vai trò riêng. **Vai trò quản trị token không nên đồng nhất với quyền dùng private key để ký**, và việc một credential đăng nhập được không tự cấp quyền truy cập mọi key object.

## 9. Java 17: truy cập một virtual HSM qua PKCS#11

Đoạn mã sau minh họa cách một ứng dụng Java 17 **cấu hình provider SunPKCS11**, mở `KeyStore` kiểu `PKCS11`, lấy **private key handle** từ token và yêu cầu token ký một thông điệp demo. Nó **không sinh khóa và không xuất private key**.

**Điều kiện trước khi chạy:** phải có thư viện PKCS#11 của nhà cung cấp, token/partition được cấu hình và đăng nhập hợp lệ, một **RSA private key đã được provision với alias phù hợp**, cũng như mechanism RSA signing được HSM hỗ trợ. Mã này có thể hoạt động với một software token trong dev, nhưng **không chứng minh hardware isolation**. Một số token khác sử dụng key alias, PIN, cơ chế login và provider-specific configuration khác; điều chỉnh theo tài liệu sản phẩm.

### 9.1. Ví dụ cấu hình provider

~~~text
# pkcs11-demo.cfg — ví dụ minh họa, không phải file có sẵn trong dự án
name = ExampleVirtualToken
library = /opt/vendor/libpkcs11.so
slotListIndex = 0
~~~

Đường dẫn và slot index là **placeholder**, không dùng lại nguyên xi. `slotListIndex=0` là **chỉ số slot do library liệt kê**, không đồng nghĩa partition 0 hay tenant đầu tiên ở mọi thiết bị. Trong production cần lựa chọn token ổn định, kiểm tra danh tính/token serial và tránh trỏ nhầm partition khi topology thay đổi.

### 9.2. Ví dụ mã Java 17

~~~java
import java.io.Console;
import java.nio.charset.StandardCharsets;
import java.security.Key;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.Provider;
import java.security.Security;
import java.security.Signature;
import java.util.Arrays;

public final class VirtualHsmPkcs11Demo {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java VirtualHsmPkcs11Demo <configPath> <keyAlias>");
        }
        String configPath = args[0];
        String keyAlias = args[1];

        // Module jdk.crypto.cryptoki / provider SunPKCS11 phải khả dụng.
        Provider base = Security.getProvider("SunPKCS11");
        if (base == null) {
            throw new IllegalStateException("SunPKCS11 unavailable");
        }
        Provider tokenProvider = base.configure(configPath);
        Security.addProvider(tokenProvider);

        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException("Run from a secure terminal");
        }
        char[] pin = console.readPassword("Token PIN: ");
        if (pin == null) {
            throw new IllegalStateException("PIN required");
        }

        try {
            if (pin.length == 0) {
                throw new IllegalStateException("PIN required");
            }
            KeyStore token = KeyStore.getInstance("PKCS11", tokenProvider);
            token.load(null, pin);

            // Token-specific: nhiều provider dùng null sau login;
            // một số yêu cầu cách lấy key/credential khác.
            Key object = token.getKey(keyAlias, null);
            if (!(object instanceof PrivateKey privateKey)) {
                throw new IllegalStateException(
                        "Alias must refer to an authorized private key");
            }

            // Chỉ định provider để không vô tình dùng software fallback.
            // SHA256withRSA là demo tương thích; với hệ thống mới,
            // xét RSA-PSS hoặc thuật toán khác theo policy/HSM support.
            Signature signer = Signature.getInstance(
                    "SHA256withRSA", tokenProvider);
            signer.initSign(privateKey);

            byte[] message = "Authorized demo message"
                    .getBytes(StandardCharsets.UTF_8);
            signer.update(message);
            byte[] signature = signer.sign();

            // Signature là public output; chỉ ghi metadata tối thiểu.
            System.out.println("Signed via provider: "
                    + tokenProvider.getName());
            System.out.println("Signature bytes: " + signature.length);
            // Không in PIN, raw private key, key.getEncoded() hoặc token.
        } finally {
            Arrays.fill(pin, '\0');
        }
    }
}
~~~

### 9.3. Đọc đoạn mã một cách chính xác

1. **`Security.getProvider("SunPKCS11")` và `configure(...)`:** yêu cầu module/provider tương ứng khả dụng trong JDK và thư viện token được cài đặt. Một số môi trường cần cấu hình module hoặc native library riêng.
2. **`KeyStore.getInstance("PKCS11", tokenProvider)`:** đọc đối tượng khóa do provider/token cung cấp, **không có nghĩa toàn bộ alias đều là private key của tenant hiện tại**; authorization và token selection phải đúng.
3. **`Signature.getInstance(..., tokenProvider)`:** yêu cầu provider đã chỉ định thực hiện operation, hạn chế nguy cơ chọn nhầm provider phần mềm. Cần kiểm tra provider thực tế và HSM audit.
4. **`token.getKey(keyAlias, null)`:** là **cách truy xuất minh họa** có thể khác theo vendor; một số HSM yêu cầu mechanism/login/alias mapping khác.
5. **`SHA256withRSA`:** lựa chọn để minh họa tính tương thích; không khuyến nghị mặc định cho mọi triển khai mới. Với RSA-PSS/Ed25519/ECDSA, chọn mechanism, hash và các tham số theo profile/thiết bị được duyệt.
6. **`pin` là `char[]`:** có thể xóa bản sao trong ứng dụng sau khi dùng; các bản sao trong runtime/native provider và cơ chế nhập console không được bảo đảm xóa hoàn toàn. Không gọi `String` để giữ PIN lâu dài.
7. **Không xuất khóa:** việc có thể gọi `Sign` **không chứng minh private key không thể bị trích xuất bằng mọi quyền khác**; phải kiểm tra key attributes, IAM, provider assurance và negative tests phù hợp.

### 9.4. Một giới hạn quan trọng: mã chạy được ≠ sử dụng HSM thật

Nếu thay thư viện PKCS#11 bằng **software HSM/emulator**, chương trình vẫn có thể chạy. Mục đích của mẫu này là **tích hợp và thao tác đúng provider**, không phải chứng nhận phần cứng. Việc dùng production đòi hỏi **key ceremony, approved generation, non-extractability, quyền hạn, audit, HA và chứng cứ vùng bảo mật**.

**Không dùng đoạn code ký demo để phê duyệt giao dịch thật**: signing service phải kiểm tra user/tenant, nội dung đã chuẩn hóa, approval nghiệp vụ và replay protection **trước khi** gọi HSM `Sign`. HSM chỉ thực hiện phép ký được cho phép bởi IAM/key attributes; nó không hiểu mục đích tài chính của payload.

## 10. Sinh và lưu private key: import khác generate

Hai lựa chọn kiến trúc có tác động rất khác nhau:

| Cách tạo key | Mô hình lưu trữ | Rủi ro chính |
| --- | --- | --- |
| **Generate within hardware-backed HSM partition** | Vật liệu khóa được tạo trong security boundary theo assurance | Sai quyền, firmware, token partition và API misuse |
| **Generate in application rồi import** | Raw private key đã tồn tại trong JVM/host | Bản sao RAM/log/backup trước khi import, thiếu bảo đảm nguồn sinh |
| **Import từ HSM nguồn qua wrapped transfer** | Quá trình chuyển có thể bảo vệ khóa bằng cơ chế vendor | Trust ở HSM nguồn, wrapping protocol, bản sao và import policy |
| **Generate trong software HSM trên VM** | Key lưu dưới cơ chế phần mềm của host/VM | Privileged host, filesystem/snapshot/memory extraction |
| **Derive từ master key hoặc agreement** | Key con sinh từ KDF/key schedule đã duyệt | Key separation, source entropy, truy vết context và cryptoperiod |

Nếu key generation policy yêu cầu **“private signing key được sinh bên trong HSM và không xuất được”**, không thể sinh key với `KeyPairGenerator` trong JVM, import sau đó và đổi metadata thành `HSM_GENERATED`. **Địa điểm tạo ban đầu là một phần provenance, không phải chỉ trạng thái lưu trữ hiện tại**.

### 10.1. Những thuộc tính cần chốt trước khi tạo

- Key type/algorithm/curve/size, ví dụ AES-256, RSA-PSS profile, ECDSA P-256, Ed25519.
- `SIGN`, `VERIFY`, `ENCRYPT`, `DECRYPT`, `WRAP`, `UNWRAP` và mục đích được phép.
- Persistent token key hay session-only object.
- Extractability và cơ chế backup/restore được phép.
- Owner, tenant, partition, environment, key ID/version, cryptoperiod.
- Quyền admin/provisioner, key usage principal và approval/quorum khi cần.
- Audit và evidence nguồn sinh từ provider.

**Không phải mọi HSM ảo đều hỗ trợ mọi thuật toán hoặc thuộc tính.** Nếu token không hỗ trợ AES-GCM, Ed25519 hay RSA-PSS với tham số cần thiết, ứng dụng phải từ chối hoặc dùng kiến trúc/profile khác được duyệt; không fallback bí mật sang software provider.

## 11. Virtual HSM trong vòng đời khóa

**Key lifecycle** gồm các pha tạo, cấp phát, kích hoạt, sử dụng, xoay vòng, ngừng dùng, thu hồi và hủy. Một virtual HSM chỉ là một phần của cơ chế thực thi; trạng thái **ACTIVE** trong inventory và trạng thái **Enabled** của provider có thể khác nhau.

~~~mermaid
flowchart TD
    Need[Key owner xác định purpose / risk] --> Gen[Generate hoặc Import theo policy]
    Gen --> Register[Đăng ký key ID/version + provider reference]
    Register --> Pre[PRE_ACTIVE: approval / IAM / activationAt]
    Pre --> Active[ACTIVE: đúng usage / cryptoperiod]
    Active --> Rotate[Rotation: tạo vật liệu mới]
    Active --> Suspend[Suspend / Revoke nếu có sự cố]
    Rotate --> Retire[Retired: không tạo bảo vệ mới]
    Retire --> Dep[Kiểm tra ciphertext, backup, certificate]
    Suspend --> Incident[Incident response + impact assessment]
    Incident --> Dep
    Dep --> Destroy[Destroy theo retention / crypto-erasure]
    Active --> Audit[Operation audit / quota]
    Destroy --> Audit
~~~

### 11.1. Trạng thái và cryptoperiod

Trong inventory, thường cần:

- `createdAt`: thời điểm tạo hoặc thời điểm provider xác nhận.
- `activationAt`: thời điểm sớm nhất được phép dùng theo policy.
- `newUseUntil`: kết thúc việc **tạo bảo vệ mới**.
- `oldUseUntil`: kết thúc khả năng xử lý dữ liệu cũ khi policy cho phép.
- `suspendedAt/revokedAt`: sự cố hoặc rút quyền.
- `destroyedAt`: bằng chứng hủy theo semantics provider.

**Virtual HSM không tự áp đặt cùng một state machine cho mọi nền tảng.** Nhiều provider có trạng thái `Enabled/Disabled/PendingDeletion`, có thiết bị hỗ trợ key flags và token state riêng. Nếu một key bị Disabled ở HSM, có thể **mọi API** bị từ chối chứ không có chế độ “decrypt-only”. Ứng dụng phải thiết kế policy xử lý dữ liệu cũ theo những tính năng thực tế được hỗ trợ.

### 11.2. Rotation và alias

Một logical key `invoice-signing` có thể có các version `v4`, `v5`. Khi xoay vòng:

1. Sinh `v5` bằng generator/provider được duyệt.
2. Đăng ký key object reference và policy, đưa `v5` vào pre-active khi cần.
3. Phân phối public key/chứng thư trước nếu verifier cần chuẩn bị.
4. Kích hoạt `v5` và chuyển `primary for sign new`.
5. Ngừng ký mới bằng `v4`; vẫn giữ **public key/chứng thư** để verify lịch sử theo chính sách.
6. Đánh giá khả năng archive và tiêu chí hủy private key cũ.

**Không xem việc đổi alias/label là đã sinh material mới.** Nếu khóa cũ bị lộ, cần vật liệu mới và incident response; đổi tên không làm đối thủ mất bản sao khóa.

## 12. DEK, KEK và envelope encryption với virtual HSM

Một ứng dụng thường cần mã hóa lượng dữ liệu lớn. Đưa toàn bộ plaintext vào HSM để mã hóa từng block không nhất thiết là lựa chọn phù hợp về **throughput, latency và cấu trúc API**.

Một mô hình phổ biến là **envelope encryption**:

1. Sinh **DEK (Data Encryption Key)** có entropy cao, trong nơi được chính sách chấp thuận.
2. Dùng DEK với AEAD như **AES-GCM/ChaCha20-Poly1305** để mã hóa dữ liệu trong workload được ủy quyền.
3. Dùng **KEK (Key Encryption Key)** trong KMS/HSM để **wrap/bảo vệ DEK**.
4. Lưu `ciphertext`, authentication tag, nonce/AAD context, `wrapped DEK`, key reference/version.
5. Khi đọc, kiểm tra tenant/resource authorization rồi mới unwrap đúng version và decrypt/verify AEAD.

~~~mermaid
sequenceDiagram
    participant App as Data service
    participant Policy as IAM / tenant authorization
    participant VHSM as Virtual HSM / KEK
    participant DB as Storage
    App->>Policy: Xin encrypt record tenant A
    Policy-->>App: Cho phép theo resource và purpose
    App->>VHSM: Generate/Wrap DEK theo key-v2
    VHSM-->>App: Wrapped DEK + DEK theo API/profile
    App->>App: AEAD encrypt bằng DEK và nonce an toàn
    App->>DB: Lưu ciphertext + tag + nonce + wrapped DEK + key version
    DB-->>App: Record cũ và key version
    App->>Policy: Kiểm tra quyền read record
    Policy-->>App: Cho phép
    App->>VHSM: Unwrap bằng KEK version đã lưu
    VHSM-->>App: DEK nếu operation được phép
    App->>App: Verify AEAD rồi giải mã
~~~

Sơ đồ minh họa **một kiến trúc có bản DEK rõ tạm thời ở workload**. API thực tế khác nhau; có nền tảng chỉ thực hiện wrap/unwrap trên token, có nền tảng hỗ trợ `GenerateDataKey`, có nền tảng giữ DEK trong HSM và xử lý dữ liệu ở đó. **Không giả định mọi virtual HSM trả DEK dạng rõ**.

### 12.1. Sự khác biệt giữa rewrap và re-encrypt

| Tình huống | Thao tác thường xem xét | Vì sao? |
| --- | --- | --- |
| Rotation KEK định kỳ, DEK không có dấu hiệu lộ | **Rewrap DEK** dưới KEK mới | Có thể không cần mã hóa lại toàn bộ data |
| DEK bị lộ | **DEK mới + re-encrypt dữ liệu** | Rewrap không thay byte DEK đã lộ |
| KEK và wrapped DEK cũ đã bị đối thủ lấy | Đánh giá **DEK mới và re-encrypt**, ngoài rewrap | Bản sao cũ vẫn cho attacker khả năng lấy DEK |
| Key cũ bị xóa nhưng backup còn wrapped DEK | Khả năng restore thất bại | Phải kiểm tra dependency trước destruction |

### 12.2. Nonce uniqueness

HSM sinh một AES key mạnh không bảo đảm AES-GCM an toàn nếu ứng dụng tái sử dụng **cùng cặp (key, nonce)**. Nonce thường không cần bí mật nhưng **không được trùng** trong phạm vi key cho AES-GCM và ChaCha20-Poly1305. Key owner/app team cần quản lý nonce strategy, usage limits, counter/namespace và rotation, đặc biệt khi có nhiều node hoặc rollback VM snapshot.

### 12.3. Quyền dùng key khác quyền đọc dữ liệu

Dù ứng dụng có quyền `Unwrap` trong HSM, nó vẫn phải kiểm tra **tenant, owner, resource và purpose** trước khi trả plaintext. Một virtual HSM không hiểu tất cả quy tắc nghiệp vụ. Không để client gửi `keyId` tùy ý rồi dùng HSM như **decrypt oracle** đối với dữ liệu không thuộc quyền của người gọi.

## 13. Virtual HSM cho chữ ký số và PKI

Một ứng dụng thường muốn giữ **private key ký số** trong HSM nhưng vẫn cung cấp **public key/chứng thư** cho các bên xác minh. Kiến trúc:

~~~mermaid
flowchart LR
    Business[Business authorization: ai được ký tài liệu?] --> Signer[Signing service]
    Signer --> IAM[HSM operation IAM / policy]
    IAM --> VHSM[Virtual HSM giữ private signing key]
    VHSM --> Sig[Signature output]
    Public[Public key / certificate registry] --> Verify[Verifier]
    Sig --> Verify
    Message[Tài liệu đúng byte] --> Verify
    PKI[CA / trust chain / revocation] --> Verify
    Audit[Audit key version + request approval] --> Signer
    Audit --> VHSM
~~~

**Non-extractable** private key giúp giảm khả năng sao chép material, nhưng attacker có quyền gọi HSM `Sign` vẫn có thể **tạo chữ ký giả**. Do đó, signer cần:

- Xác thực workload và caller.
- Kiểm tra **quyền nghiệp vụ, đối tượng được ký và transaction approval**.
- Chuẩn hóa thông điệp/hợp đồng byte trước khi ký để tránh “ký dữ liệu khác với nội dung hiển thị”.
- Giới hạn key usage theo algorithm, tenant, service và cryptoperiod.
- Chống replay/chống ký trùng theo risk model và ghi audit đủ để điều tra.
- Phân phối public key/chứng thư qua **trust binding** rõ ràng.

### 13.1. Public key verification có vòng đời riêng

Sau rotation, private key `v4` có thể không còn được phép ký mới, nhưng public key hoặc chứng thư tương ứng vẫn cần cho **verify chữ ký lịch sử**. Việc xác minh toán học `Signature.verify() == true` **không tự chứng minh giao dịch được ủy quyền** hoặc được tạo trước khi key bị compromise.

Cần xét **certificate chain, key usage/EKU, trạng thái thu hồi CRL/OCSP, trusted timestamp** và quy tắc xác minh lịch sử. Một **key alias HSM hiện trỏ sang v5** không có nghĩa chữ ký cũ phải được kiểm tra bằng public key v5.

### 13.2. Khi private signing key bị nghi lộ

1. Chặn `Sign` mới trên key/version bị ảnh hưởng và cô lập principal.
2. Xác định có **raw key extraction** hay **API misuse** (hai trường hợp có tác động khác nhau).
3. Cập nhật certificate/public-key trust hoặc revocation khi cần.
4. Tạo key mới trong approved boundary, phân phối trust mới.
5. Đánh giá chữ ký đã phát hành trong khoảng sự cố; không chỉ dựa vào phép `Verify`.

**Disable một key trong HSM không tự cập nhật JWKS hoặc CRL cho mọi verifier.**

## 14. Key owner, custodian, IAM và quorum approval

Virtual HSM thay đổi cách cấp tài nguyên, **không xóa trách nhiệm tổ chức**.

| Vai trò | Trách nhiệm | Không nên mặc nhiên có |
| --- | --- | --- |
| **Key owner** | Purpose, cryptoperiod, policy, rotation/revocation và rủi ro | Raw private key, `Sign/Decrypt` vô hạn |
| **HSM custodian/operator** | Partition, firmware, backup, key generation theo approval | Quyền ký giao dịch hoặc đọc plaintext nghiệp vụ |
| **Security administrator** | IAM baseline, separation of duties, sự cố và controls | Khả năng tự sửa mọi audit và cấp quyền cho chính mình |
| **Application key user** | `Sign/Wrap/Unwrap` theo operation và resource hợp lệ | `DeleteKey`, `ExportKey`, thay partition policy |
| **Data owner** | Phân loại dữ liệu, quyền đọc và retention | Được cấp trực tiếp private signing key |
| **Auditor** | Xem metadata, chứng cứ và kiểm tra controls | Export secret hoặc thực hiện `Decrypt` |

### 14.1. Separation of duties

Một người vừa có quyền **tạo partition**, **sửa IAM**, **tạo root key**, **xuất backup** và **xóa audit** có thể vô hiệu nhiều lớp kiểm soát. Cần tách các vai trò với **least privilege**.

Đối với thao tác nhạy cảm như **root KEK export/import, thay chính sách cho phép export, khôi phục backup chứa key, hủy vĩnh viễn**, có thể yêu cầu **quorum approval M-of-N** cùng Security/Key owner/Data governance theo risk tier. Nhưng **quorum workflow phải được enforce ở đường API thật**; hai nút “Approve” trên UI không ngăn admin có credential trực tiếp bỏ qua.

### 14.2. Break-glass khi có sự cố

Nếu một service đang ký giả, đường **containment khẩn cấp** có thể phải disable/revoke quyền `Sign` ngay theo runbook, không chờ quorum cho **hủy vĩnh viễn key**. Quyền khẩn cấp cần **phạm vi hẹp, TTL, audit, hậu kiểm và phân quyền rõ**. Không dùng lý do khẩn cấp để tự ý xuất private key hoặc xóa KEK khi backup còn phụ thuộc.

### 14.3. Identity mapping

Một service account có thể truy cập partition qua client certificate hoặc token credential. Nếu service account bị chiếm, key vật lý có thể chưa bị trích xuất nhưng attacker có thể dùng API. Hãy kiểm tra **identity thực tế, mTLS binding, token PIN/IAM scope, key usage và transaction authorization**, đồng thời theo dõi anomaly trong audit.

## 15. High availability, backup và disaster recovery

HSM thường phục vụ thao tác quan trọng liên tục, nên việc “giữ key không xuất được” phải đi cùng **khả năng khôi phục và tính sẵn sàng**.

### 15.1. HA và replication

Một cụm HSM có thể có:

- Nhiều node phục vụ signing/wrapping.
- Đồng bộ key objects hoặc cơ chế backup/restore theo vendor.
- Kết nối riêng, load balancing, health check và failover.
- State/role/token management và phiên bản firmware tương thích.

**Không giả định key objects sẽ tự xuất hiện trên node khác** vì cả hai node cùng một tên partition. Cần xác minh có **replication, import/restore được hỗ trợ và consistency policy** đúng như thiết kế.

### 15.2. Backup key material

Backup là lĩnh vực đặc biệt nhạy cảm:

- **Hardware-backed HSM:** có thể cung cấp backup bị wrap/bảo vệ bằng cơ chế vendor, domain key hoặc HSM-to-HSM secure migration. Dùng **đúng cơ chế chính thức** được đánh giá.
- **Software HSM:** có thể có database/file chứa key material được mã hóa ở trạng thái nghỉ, nhưng host/snapshot và khóa bảo vệ file phải được đánh giá; sao chép VM image có thể sao chép dữ liệu nhạy cảm.
- **Non-extractable key:** có thể không export raw material, song **backup/migration** có thể có semantics riêng. Không đồng nhất "không export raw" với "không thể phục hồi trong cụm".
- **Root/recovery key:** có thể có **dual control, split knowledge hoặc threshold recovery** tùy yêu cầu; không coi 2-of-3 approval là tương đương 2-of-3 secret shares.

### 15.3. Kiểm thử DR không làm lộ bí mật

Đừng chỉ kiểm tra backup file có tồn tại. Cần thực hiện **restore rehearsal** trong môi trường được phê duyệt, kiểm tra:

1. Đúng key ID/version và owner/partition.
2. Các key flags, object attributes và permissions sau restore.
3. Có thể **unwrap DEK cũ** hoặc **verify chữ ký cũ** theo policy không.
4. Không tạo key copy ngoài vùng được phép.
5. Audit và key inventory có thể đối chiếu trạng thái phục hồi.
6. Có thể đáp ứng RTO/RPO đã thống nhất không.

**Xóa KEK hoặc partition trước khi kiểm tra backup có thể khiến hàng loạt ciphertext không thể đọc.** Ngược lại, backup chứa root secret mà không có access controls là một đường trích xuất key nguy hiểm.

## 16. Hiệu năng, độ trễ và vận hành cụm virtual HSM

Phần mềm, mạng và HSM có chi phí khác nhau:

- **Local JCA AES-GCM** trên CPU có thể xử lý dữ liệu lớn với độ trễ thấp.
- **Network HSM/KMS** cần round trip, cơ chế xác thực và có thể có rate limit/quota.
- **RSA/ECDSA/Ed25519 signing** qua HSM phù hợp nhiều bài toán cần private key non-extractable, nhưng throughput phụ thuộc model/algorithm/partition.
- **Bulk encryption** có thể ưu tiên envelope encryption: HSM chỉ wrap/unwrap DEK, ứng dụng mã hóa dữ liệu bằng AEAD trong trusted memory.

### 16.1. Các metric vận hành

| Chỉ số | Cần quan tâm |
| --- | --- |
| `signLatencyP95/P99` | Ký giao dịch có đáp ứng SLA không? |
| `unwrapLatency` | Đọc dữ liệu phụ thuộc HSM có bị nghẽn không? |
| `sessionsInUse` | Session pool đang bão hòa? |
| `operationRate` | Có tiến tới quota/capacity limit? |
| `authFailureRate` | PIN/credential sai hay có brute-force? |
| `partitionIsolationAlerts` | Cross-tenant access hoặc quota abuse? |
| `replicationLag` | Key version mới đã sẵn sàng ở mọi node? |
| `keyStateMismatch` | Inventory ACTIVE nhưng HSM disabled? |
| `backupRestoreResult` | Khả năng khôi phục thực tế? |

Không đặt một **con số TPS hoặc latency cố định** cho “virtual HSM nói chung”; phải benchmark đúng **hardware/virtualization mode, region, algorithm, key size, concurrent sessions, provider và network topology**.

### 16.2. Tránh fallback gây hạ cấp bảo mật

Nếu HSM timeout, **không âm thầm chuyển sang ký bằng private key PEM trong JVM** để giữ throughput. Chính sách phải xác định fail-closed, retry/idempotency, timeout, circuit breaker và DR route được phê duyệt.

Với signing/payment operation có tác động lớn, fallback không được kiểm soát có thể phá hủy toàn bộ ý nghĩa của việc giữ key trong HSM.

## 17. Key inventory và bằng chứng nguồn gốc của HSM ảo

Một record key inventory tốt cần giúp tổ chức trả lời **key nằm trong partition nào, thuộc ai, version gì, sinh ở đâu, được dùng khi nào và ai được phép thao tác**.

### 17.1. Metadata mẫu

~~~json
{
  "keyId": "invoice-signing",
  "keyVersion": "v5",
  "keyClass": "ASYMMETRIC_PRIVATE",
  "algorithm": "RSA-PSS",
  "purpose": ["SIGN"],
  "ownerTeam": "invoice-security",
  "tenantScope": "production/tenant-a",
  "storageType": "HARDWARE_BACKED_PARTITION",
  "providerRef": "hsm://example/partition-a/keys/invoice-v5",
  "partitionRef": "partition-a",
  "generationMethod": "GENERATED_WITHIN_PROVIDER",
  "exportPolicy": "NON_EXTRACTABLE",
  "providerEvidenceRef": "provider-key-generation-731",
  "lifecycleState": "PRE_ACTIVE",
  "createdAt": "2026-11-28T02:00:00Z",
  "activationAt": "2026-12-01T00:00:00Z",
  "newUseUntil": "2027-06-01T00:00:00Z",
  "policyRevision": 12,
  "approvalRef": "KEY-CHANGE-205",
  "auditRef": "hsm-key-activity-00142"
}
~~~

Đây là **schema minh họa**, không phải định dạng API chuẩn của một sản phẩm. Những giá trị như `HARDWARE_BACKED_PARTITION`, `NON_EXTRACTABLE` và `GENERATED_WITHIN_PROVIDER` **chỉ được ghi như khẳng định đã xác minh nếu có evidence từ provider/assurance thích hợp**.

### 17.2. Quan hệ giữa logical key và provider object

Không dùng `alias=current` làm bằng chứng về key version. Alias có thể đổi trong rotation; còn ciphertext/chữ ký lịch sử cần key ID/version đúng. Provider object handle cũng có thể thay đổi qua session/restart. Inventory phải có **quy tắc ánh xạ được quản lý và có thể kiểm tra**.

### 17.3. Audit không được chứa raw key

Audit nên ghi `principal`, `tenant`, `operation`, `keyId/version`, `partition`, `policyRevision`, `result`, timestamp và correlation ID; **không ghi private key/DEK/KEK, PIN, PSK, plaintext hay bearer token**. Cần bảo vệ cả metadata vì nó có thể tiết lộ cấu trúc hệ thống, hành vi khách hàng hoặc quyền của một tenant.

## 18. Kiểm toán, compliance và kiểm chứng thực tế

Một bản giới thiệu sản phẩm ghi “HSM-backed” chưa đủ để đóng hồ sơ an toàn. Cần kết hợp **tài liệu/bằng chứng từ vendor**, cấu hình triển khai, kiểm tra API và audit thời gian chạy.

### 18.1. Những câu hỏi kiểm toán

| Hạng mục | Câu hỏi/kiểm tra |
| --- | --- |
| **Security boundary** | Private key được tạo và lưu trong boundary cụ thể nào? |
| **Certification** | Module/phiên bản/chế độ/key type có nằm trong phạm vi bảo đảm công bố? |
| **Isolation** | Tenant khác có nhìn thấy key metadata/object hoặc gọi operation không? |
| **IAM** | Chủ thể chỉ được phép thao tác theo key usage, purpose và environment? |
| **Admin separation** | Ai có quyền tạo partition, backup, import/export, thay policy và xóa key? |
| **Audit** | Operation và state transition có traceable, chống sửa và tách quyền? |
| **Rotation** | Có sinh vật liệu mới, cập nhật key version và đọc được dữ liệu cũ? |
| **Recovery** | Restore có kiểm thử và giữ nguyên quyền/attributes không? |
| **Incident** | Có thể revoke nhanh, phát hiện stale token/cache và giám sát hành vi bất thường? |
| **Fallback** | HSM lỗi có dẫn tới chuyển sang software key không được duyệt? |

### 18.2. Negative tests

Kiểm tra có thể thực hiện bằng **key thử nghiệm và tài khoản quyền tối thiểu**, không dùng raw key production:

- Tenant A không thể liệt kê/truy cập key của tenant B.
- Key user không thể export private key hoặc đổi permissions.
- Key operator không thể ký tài liệu nghiệp vụ nếu không được cấp `Sign`.
- Chữ ký không được tạo khi key pre-active, revoked hoặc hết sign period.
- Client không thể chọn sai partition chỉ bằng cách đổi key label.
- Thao tác `Sign/Unwrap` thiếu quyền bị từ chối tại HSM/API, không chỉ tại UI.
- HSM unavailable không làm phần mềm fallback tới private key file.
- Key mới restore không tự động Active khi approval/inventory chưa hợp lệ.
- Audit cho thấy **provider object/key version thật**, không chỉ alias yêu cầu.

**Một bài test đọc `getEncoded()==null` không tự chứng minh chống trích xuất ở cấp phần cứng.** Các thuộc tính và key assurance cần được đánh giá theo provider security boundary thực tế.

## 19. Tình huống thực tế: di chuyển signing key từ file PEM sang virtual HSM

Giả sử tổ chức đang ký hóa đơn bằng **private key trong file PEM** trên server. Mục tiêu là chuyển sang **virtual HSM có partition được hardware-backed** để giảm nguy cơ sao chép private key và phân vai vận hành.

### Giai đoạn A — Thiết kế và phân loại

**Key owner** xác định yêu cầu `SIGN`, thuật toán, cryptoperiod, certificate chain, issuer, verifier và thời hạn lưu hóa đơn. **Security** đánh giá threat model: host bị chiếm, dịch vụ ký bị lạm dụng, operator đặc quyền và việc khôi phục khi cụm HSM lỗi.

Phải xác minh dịch vụ virtual HSM thực sự có **hardware-backed boundary**, cơ chế non-extractability và khả năng hỗ trợ signature algorithm đã phê duyệt. Nếu chỉ là **software HSM trong VM**, không nên tuyên bố đã giải quyết rủi ro copy key từ host tương đương thiết bị phần cứng.

### Giai đoạn B — Sinh khóa mới trong boundary

Phương án ưu tiên cho key mới có yêu cầu non-extractable là **generate trong partition HSM được duyệt**, lưu provider key reference và key version vào inventory. **Không nhập private PEM cũ** rồi đánh dấu “generated inside HSM”; nó đã từng có bản sao ngoài boundary. Nếu cần import để duy trì tính tương thích, ghi đúng provenance và thời hạn chuyển đổi.

### Giai đoạn C — Thay ứng dụng ký

Signing service dùng JCA/PKCS#11 hoặc vendor SDK theo capability. Trước mỗi `Sign`, kiểm tra **quyền nghiệp vụ, tenant, nội dung chuẩn hóa và trạng thái key**. Audit ghi **actual key ID/version** và kết quả, không log private key.

### Giai đoạn D — Chuyển đổi trust

Public key/chứng thư mới được phân phối qua kênh được tin. Nếu dùng JWT/JWKS, verifier cần biết `kid`/issuer/key version phù hợp và cache policy. Không bỏ public key cũ quá sớm khi còn chữ ký/token lịch sử hợp lệ cần xác minh. Khi ký số theo PKI, xét cả **CA chain, certificate validity, CRL/OCSP và trusted timestamps**.

### Giai đoạn E — Rotation, sự cố và phục hồi

Khi signing key cũ đã hết quyền ký mới, chuyển primary sang key trong virtual HSM. Kiểm tra cả **signing continuity, verifier acceptance, backup, HA failover và incident response**. Nếu private PEM cũ có nguy cơ bị lộ, phải đánh giá **revocation và chữ ký giả có thể đã được tạo**, không chỉ đổi key mới.

### Lỗi thường gặp khi di chuyển

**Lỗi 1 — Sai provider:** Java vẫn gọi `Signature` từ software provider vì không chỉ định provider/token, làm mất ý nghĩa kiến trúc. Cần kiểm tra HSM audit và provider selection.

**Lỗi 2 — Sai partition:** client dùng slot index mặc định sau một lần thay topology, ký bằng key tenant khác hoặc gặp lỗi. Cần identity/token selection ổn định và access controls.

**Lỗi 3 — Quyền `Sign` quá rộng:** private key ở trong HSM nhưng service nhận bất kỳ payload nào và ký. Attacker chiếm API vẫn tạo chữ ký hợp lệ. Cần business authorization.

**Lỗi 4 — Thiếu DR:** cụm HSM primary lỗi, bản backup chưa từng restore; chữ ký gián đoạn. Cần capacity/recovery rehearsal và xem xét key replication theo vendor.

## 20. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm phù hợp |
| --- | --- | --- |
| Gọi VM chạy SoftHSM là HSM vật lý | Đánh giá sai khả năng chống trích xuất | Xác minh hardware boundary và bảo đảm provider |
| Coi partition logic là phần cứng riêng hoàn toàn | Bỏ qua shared failure domain | Mô tả rõ tenant isolation và hạ tầng dùng chung |
| Dựa vào `CKA_EXTRACTABLE=false` trong emulator | Không phát hiện host có thể đọc keystore | Threat model host/hypervisor và key origin evidence |
| Sinh private key trong JVM rồi import, ghi HSM-generated | Sai provenance, bản sao có thể vẫn ở host | Sinh trong HSM nếu policy yêu cầu và ghi đúng source |
| HSM non-extractable nên bỏ IAM `Sign` | Attacker dùng API ký giả | Business authorization và operation audit |
| Gọi JCA không chỉ định provider | Provider phần mềm có thể được chọn | Explicit provider và verify HSM operation |
| Hard-code PIN trong source/config | Lộ credential HSM | Secure input/credential mechanism, role separation |
| Dùng slot index tùy ý cho tenant | Trỏ sai token/partition | Stable token selection và negative tests |
| Ghi key handle của session làm ID vĩnh viễn | Mất mapping sau reconnect | Logical key/version và stable provider reference |
| Không phân biệt token vs session key | Key không tồn tại sau restart hoặc backup sai | Persistent object attributes và lifecycle |
| HSM timeout thì fallback sang file PEM | Hạ cấp security boundary | Fail-closed/DR route đã duyệt |
| Xóa KEK khi backup còn DEK được bọc | Mất khả năng giải mã | Inventory phụ thuộc, rewrap/restore trước destroy |
| Rewrap DEK đã bị lộ rồi coi an toàn | DEK cũ vẫn bị đối thủ dùng | DEK mới và re-encrypt khi cần |
| Không xét nonce policy khi mã hóa AES-GCM | Có thể dùng lại (key, nonce) | Nonce uniqueness và usage limits |
| Một HSM partition có mọi tenant quyền admin chung | Cross-tenant misuse | SoD và IAM/tenant isolation |
| Không audit trạng thái/provider/version | Không xác định nguồn sự cố | Provider logs + immutable inventory events |
| Coi FIPS của HSM áp dụng cho mọi app/gateway | Sai phạm vi tuân thủ | Xác minh boundary, operation và mode thực tế |
| Dùng backup VM/software token như bản backup HSM | Tạo thêm secret copy không được kiểm soát | Vendor backup/escrow và DR controls |
| Không test restore/failover | Gián đoạn dịch vụ khi hỏng node | Rehearsal, RTO/RPO và quorum khi cần |
| Loại bỏ public key cũ ngay sau rotation signer | Không verify được chữ ký lịch sử | Retention/trust policy với chứng cứ thời gian |

## 21. Checklist triển khai virtual HSM

- [ ] Đã xác định **virtual HSM là hardware partition, managed service hay software emulator**?
- [ ] Có bằng chứng rõ về **security boundary, key origin, exportability và phạm vi assurance/certification**?
- [ ] Đã threat-model **host/hypervisor, control plane, HSM API principal, tenant isolation, backup và network**?
- [ ] Private signing key/KEK cần non-extractable được **sinh trong vùng được duyệt**, không mặc định import là tương đương?
- [ ] Các **algorithm, mechanisms, key types, key sizes/curves** và PKCS#11 token capabilities đã kiểm thử?
- [ ] Có tách **Security Officer, HSM operator, key owner, key user, data owner và auditor**?
- [ ] IAM/HSM policy áp dụng **least privilege** và ngăn `Sign/Unwrap/Export/Delete` trái phép ở nơi thực thi?
- [ ] Việc thay root/trust/export/delete có **quorum approval/separation of duties** theo risk tier khi cần?
- [ ] Đã bảo vệ **credential/PIN, mTLS channel, token selection và session lifecycle**?
- [ ] Ứng dụng JCA/JCE chỉ định đúng provider và không fallback sang software key trái policy?
- [ ] Key inventory lưu **logical key ID/version, partition/provider ref, owner, usage, source, state, cryptoperiod và audit evidence**?
- [ ] Đã phân biệt persistent token key, session key, imported key và derived key?
- [ ] DEK/KEK có kế hoạch **envelope encryption, wrapped DEK, key reference, tenant/AAD và nonce strategy**?
- [ ] Với ký số, có **business authorization, public key/certificate distribution, rotation và verification lịch sử**?
- [ ] Có **HA, replication, backup, restore test, RTO/RPO**, cùng chính sách xử lý mất cụm HSM?
- [ ] Trong sự cố, có thể **chặn operation nhanh** và phân biệt API abuse với raw key compromise?
- [ ] HSM audit và application audit cho biết **actual key version, principal, operation, tenant và kết quả**, không log raw secret?
- [ ] Đã làm **negative tests cross-tenant, export-denied, permission-denied, revoked/pre-active và no-fallback**?
- [ ] Đã benchmark **latency, throughput, sessions, noisy-neighbor contention** và quota với workload thật?
- [ ] Thuộc tính tuân thủ được kiểm tra theo **module/mode/version** chứ không chỉ brochure?
- [ ] Kế hoạch migrate/rotation có xét **backup và dữ liệu phụ thuộc**, không xóa key cũ quá sớm?

## 22. Câu hỏi tự kiểm tra

**1. Virtual HSM có phải lúc nào cũng là HSM phần cứng không?**  
Không. Thuật ngữ này có thể chỉ partition logic trên phần cứng, dịch vụ managed hoặc trình mô phỏng phần mềm. Phải xác minh ranh giới bảo vệ thực tế.

**2. SoftHSM hỗ trợ PKCS#11 có đủ bảo đảm non-extractability trước host admin không?**  
Không tự đủ. Nó có thể mô phỏng thuộc tính và API token, nhưng key material ở môi trường phần mềm/host vẫn thuộc mô hình rủi ro khác HSM chống can thiệp vật lý.

**3. Tại sao private signing key không xuất được vẫn có thể bị lạm dụng?**  
Vì attacker có credential và quyền `Sign` có thể yêu cầu HSM ký dữ liệu trái phép mà không cần biết byte private key.

**4. Giao diện PKCS#11 có chứng minh thao tác thực hiện trong HSM vật lý không?**  
Không. Cùng giao diện có thể do software token hoặc hardware-backed provider triển khai; cần bằng chứng key origin và operation/assurance đúng boundary.

**5. Vì sao dùng `Signature.getInstance("SHA256withRSA")` không chỉ định provider có thể nguy hiểm?**  
JCA có thể chọn provider khác theo thứ tự ưu tiên. Nếu yêu cầu HSM bắt buộc, phải chọn provider tương ứng và xác minh operation thực tế.

**6. Có nên lưu session key handle của PKCS#11 làm key ID vĩnh viễn?**  
Không. Handle/session có thể không ổn định; inventory cần logical key ID/version và provider object reference phù hợp.

**7. Khi thay KEK, chỉ cần đổi alias sang key mới là hoàn tất rotation không?**  
Không. Cần sinh vật liệu mới, chuyển thao tác mới, rewrap DEK/backup và kiểm tra dependencies; alias chỉ là tham chiếu.

**8. Khi DEK bị lộ, rewrap dưới KEK trong virtual HSM có đủ khắc phục không?**  
Không. DEK cũ vẫn lộ; cần đánh giá DEK mới và re-encrypt dữ liệu, cũng như các bản ciphertext có thể đã bị thu thập.

**9. Vì sao phải test backup/restore dù HSM hỗ trợ HA?**  
Vì node HA không đồng nghĩa đã có backup hợp lệ, đúng version/permissions hoặc có khả năng khôi phục sau sự cố lớn.

**10. FIPS của HSM có tự chứng minh toàn bộ gateway, ứng dụng và workflow tuân thủ không?**  
Không. Phạm vi đánh giá chỉ áp dụng cho module/cấu hình/operation tương ứng; IAM, backup, audit và authorization của ứng dụng vẫn phải kiểm chứng.

**11. Với một virtual HSM dùng chung, làm sao giảm rủi ro tenant A truy cập khóa B?**  
Áp dụng partition/namespace isolation, IAM và operation-level access controls, xác thực token selection, negative tests, audit và bảo vệ quyền quản trị chung.

**12. Nếu HSM không sẵn sàng, có nên fallback sang private key lưu trong file để ký tiếp không?**  
Không được tự động làm vậy nếu policy yêu cầu HSM. Cần chiến lược availability/DR được duyệt hoặc fail-closed theo mức rủi ro.

## Ghi nhớ

**Virtual HSM là cách trừu tượng hóa và phân bổ dịch vụ/quyền quản lý khóa theo các đơn vị logic; “ảo” không tự nói lên key material được bảo vệ bằng phần cứng hay phần mềm.** Một virtual HSM có thể là **partition hardware-backed**, một dịch vụ **managed HSM** hoặc **software token/emulator** với mô hình rủi ro khác nhau. Thiết kế đúng phải chứng minh **security boundary, key origin, non-extractability, tenant isolation và quyền HSM/KMS tại nơi thực thi**, chứ không chỉ kiểm tra tên sản phẩm hay việc API PKCS#11 chạy được. Trong toàn bộ key lifecycle, cần kết hợp **Key owner, IAM/quorum, key inventory, cryptoperiod, activation, rotation, revocation, backup/DR và audit**; đồng thời phân biệt **DEK/KEK trong envelope encryption, private signing key/PKI, HMAC/PSK và khóa phiên**. Giá trị cốt lõi của Virtual HSM là **cung cấp một ranh giới bảo vệ phù hợp, có thể kiểm chứng và vận hành được** cho các khóa quan trọng — không phải thay một file chứa secret bằng một cái tên nghe an toàn hơn.
