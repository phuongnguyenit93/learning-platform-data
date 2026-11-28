# Rotate key permission

Rotate key permission là quá trình luân chuyển quyền truy cập đối với khóa mật mã theo vòng đời của workload, nhân sự, ứng dụng và chính sách bảo mật. Quá trình có thể gồm cấp quyền mới cho principal hoặc vai trò thay thế, xác minh quyền mới hoạt động đúng, sau đó thu hồi grant cũ. Mục tiêu là duy trì quyền truy cập cần thiết trong khi loại bỏ grant đã lỗi thời, quá rộng hoặc không còn thuộc phạm vi tin cậy.

Trong module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, permission rotation là một phần của access control cho key. Nó liên quan đến danh tính, policy, quyền thao tác, audit và khả năng khôi phục. Cần phân biệt việc luân chuyển quyền với cryptographic key rotation: thay quyền không thay key material; thay key material cũng không tự động loại bỏ principal cũ khỏi policy.

## 1. Rotate key permission là gì?

Quyền truy cập key thường được cấp cho một principal như machine identity, service account, ứng dụng, nhóm vận hành hoặc vai trò quản trị. Một grant có thể cho phép principal thực hiện một số thao tác trên một key resource trong những điều kiện cụ thể.

Permission rotation là việc thay thế hoặc làm mới các grant theo kế hoạch. Ví dụ:

- Một dịch vụ chuyển từ service account cũ sang workload identity mới.
- Một nhóm vận hành thay đổi thành viên và cần thu hồi quyền của nhân sự đã rời nhóm.
- Một ứng dụng được chuyển từ quyền Decrypt rộng sang quyền chỉ áp dụng cho một key và một tenant.
- Một access role cũ được thay bằng role mới có thời hạn và điều kiện chặt hơn.
- Một credential quản trị bị nghi ngờ lộ và các quyền gắn với principal đó phải được thay thế hoặc thu hồi.

Permission rotation không chỉ là đổi tên role hoặc tạo policy version mới. Quá trình cần bảo đảm principal mới thực sự có đúng quyền, principal cũ mất quyền đúng thời điểm và mọi thao tác đều được ghi nhận.

## 2. Phân biệt permission rotation và key rotation

Hai hoạt động thường diễn ra cùng nhau nhưng giải quyết rủi ro khác nhau:

| Hoạt động | Thay đổi | Mục tiêu | Ví dụ |
|---|---|---|---|
| Permission rotation | Principal, role, grant, policy hoặc credential được phép dùng key | Loại bỏ quyền cũ, giảm phạm vi truy cập và duy trì quyền cho workload hợp lệ | Chuyển ứng dụng sang machine identity mới rồi thu hồi identity cũ |
| Cryptographic key rotation | Key material hoặc phiên bản khóa mật mã | Giảm thời gian sử dụng key material, đáp ứng cryptoperiod hoặc xử lý nghi ngờ lộ khóa | Tạo key version mới và mã hóa dữ liệu mới bằng phiên bản đó |
| Credential rotation | Token, password, access key hoặc certificate dùng để chứng minh danh tính | Giảm rủi ro credential bị sao chép hoặc tồn tại quá lâu | Thay client secret và thu hồi secret cũ |

Đổi quyền không làm dữ liệu đã mã hóa bằng key cũ được mã hóa lại. Đổi key material cũng không đảm bảo principal cũ mất quyền nếu policy mới vẫn cho phép principal đó. Một kế hoạch vận hành phải xác định rõ hoạt động nào cần thực hiện và thứ tự phụ thuộc giữa chúng.

## 3. Khi nào cần luân chuyển quyền truy cập key?

Permission rotation có thể được kích hoạt theo lịch hoặc theo sự kiện:

- Workload được triển khai lại, chuyển cluster, namespace, tài khoản dịch vụ hoặc nền tảng.
- Nhân sự thay đổi vai trò, chuyển nhóm hoặc rời tổ chức.
- Một ứng dụng được chia tách thành nhiều dịch vụ với ranh giới quyền riêng.
- Quyền đã cấp không còn phù hợp với chức năng thực tế hoặc vượt quá nhu cầu.
- Credential, token, certificate hoặc máy chạy workload bị nghi ngờ xâm nhập.
- Chính sách bảo mật thay đổi, yêu cầu giảm thời hạn grant hoặc bổ sung điều kiện context.
- Hệ thống chuyển từ static credential sang workload identity hoặc credential ngắn hạn.
- Một key được chuyển sang KMS/HSM, tenant khác hoặc ranh giới quản trị mới.

Không nên chờ đến kỳ rà soát định kỳ nếu đã có sự kiện làm mất niềm tin vào principal hoặc credential. Trong trường hợp khẩn cấp, cần thu hồi quyền bị ảnh hưởng theo quy trình incident response và đánh giá tác động tới workload phụ thuộc.

## 4. Mô hình quyền cần xem xét trước khi rotation

Trước khi thay grant, cần hiểu đầy đủ quyền hiện tại. Một policy thường được đánh giá theo các thành phần:

1. **Principal:** ai hoặc workload nào đang được cấp quyền.
2. **Action:** được thực hiện thao tác gì, chẳng hạn Encrypt, Decrypt, GenerateDataKey, Sign, WrapKey hoặc UnwrapKey.
3. **Resource:** key hoặc nhóm key nào được truy cập.
4. **Condition:** điều kiện về môi trường, tenant, thời gian, nguồn gọi, workload claim hoặc encryption context.
5. **Effect:** cho phép hay từ chối; cần tính cả các policy khác có thể áp dụng.

Quyền hiệu lực có thể là kết quả kết hợp nhiều lớp policy: IAM, key policy, grant, resource policy, session policy, permission boundary hoặc policy của HSM. Xóa một grant chưa chắc đã loại bỏ quyền nếu principal vẫn được cấp quyền qua một đường khác.

~~~mermaid
flowchart TD
    A[Principal yêu cầu key operation] --> B[Identity policy]
    B --> C[Key/resource policy]
    C --> D[Grant và session constraints]
    D --> E[Condition/context]
    E --> F{Quyền hiệu lực cho phép?}
    F -->|Có| G[Thực hiện thao tác]
    F -->|Không| H[Từ chối]
~~~

Khi rà soát, cần kiểm tra cả quyền trực tiếp và quyền kế thừa qua nhóm, role assumption, service account binding hoặc wildcard. Một policy chỉ giới hạn Decrypt trên key cụ thể có thể vẫn bị mở rộng bởi policy khác cho phép kms:* hoặc quyền trên mọi key.

## 5. Nguyên tắc thiết kế permission rotation

Một quy trình tốt tuân theo các nguyên tắc:

- **Least privilege:** quyền mới chỉ gồm action và resource workload thực sự cần.
- **Identity riêng:** tránh chuyển một grant dùng chung từ principal cũ sang một principal tổng quát khác.
- **Thay đổi có thể kiểm chứng:** xác minh grant mới bằng thao tác thực tế và audit log.
- **Thu hồi rõ ràng:** xác định chính xác grant, policy statement, role binding hoặc credential cũ cần loại bỏ.
- **Không để khoảng trống quyền ngoài dự kiến:** phối hợp thời điểm thay đổi với workload và connection/session đang hoạt động.
- **Có khả năng rollback:** giữ policy version hoặc cấu hình trước đó trong thời gian chuyển đổi có kiểm soát.
- **Separation of duties:** người đề xuất, phê duyệt và thực hiện thay đổi nhạy cảm không nên mặc nhiên là cùng một principal.
- **Audit đầy đủ:** ghi người/identity thực hiện, phạm vi thay đổi, lý do, thời điểm và kết quả.

Permission rotation không nên tạo thêm một grant mới có quyền rộng hơn chỉ để tránh gián đoạn. Nếu quyền cũ không rõ ràng, hãy xác định nhu cầu thực tế trước khi tạo quyền thay thế.

## 6. Quy trình rotation theo giai đoạn

Một lần chuyển quyền thông thường có thể chia thành các giai đoạn:

~~~mermaid
flowchart TD
    A[Inventory quyền hiện tại] --> B[Thiết kế principal/policy mới]
    B --> C[Phê duyệt thay đổi]
    C --> D[Cấp grant mới]
    D --> E[Kiểm thử thao tác và audit]
    E --> F{Workload mới hoạt động đúng?}
    F -->|Không| R[Rollback hoặc điều chỉnh]
    F -->|Có| G[Chuyển workload sang identity mới]
    G --> H[Theo dõi kết nối và lỗi]
    H --> I[Thu hồi grant cũ]
    I --> J[Xác minh quyền cũ đã mất]
    J --> K[Đóng hồ sơ và audit]
~~~

**Giai đoạn 1 – Inventory:** liệt kê key resource, principal, grant, policy statement, credential, workload phụ thuộc và thao tác thực tế trong audit log. Phân biệt quyền đang được dùng với quyền tồn tại nhưng không còn nhu cầu.

**Giai đoạn 2 – Thiết kế:** xác định principal mới, action, resource và condition cần thiết. Xem xét thời hạn credential, cơ chế làm mới token và cách ứng dụng nhận identity mới.

**Giai đoạn 3 – Phê duyệt:** ghi nhận lý do, phạm vi, người chịu trách nhiệm, thời gian triển khai, tiêu chí thành công và phương án rollback.

**Giai đoạn 4 – Cấp quyền mới:** thêm grant hoặc policy cho principal mới. Nếu nền tảng hỗ trợ grant có thời hạn, đặt expiration phù hợp với mục đích và thời gian chuyển đổi.

**Giai đoạn 5 – Kiểm thử:** thực hiện đúng thao tác cần thiết trên đúng key trong môi trường phù hợp. Kiểm tra cả trường hợp được phép và trường hợp phải bị từ chối.

**Giai đoạn 6 – Chuyển workload:** cấu hình workload dùng identity mới, cập nhật credential provider và làm mới session theo hướng dẫn nền tảng.

**Giai đoạn 7 – Thu hồi quyền cũ:** sau khi xác nhận workload mới hoạt động ổn định, xóa grant, policy statement hoặc role binding cũ; thu hồi credential cũ nếu cần.

**Giai đoạn 8 – Xác minh:** kiểm tra principal cũ bị từ chối, principal mới chỉ có quyền dự kiến và audit log phản ánh đúng thay đổi.

## 7. Cấp quyền mới trước, thu hồi quyền cũ sau

Với thay đổi không khẩn cấp, mô hình chuyển đổi theo hai pha giúp giảm gián đoạn:

1. Cấp quyền tối thiểu cho principal mới trong phạm vi và thời gian chuyển đổi.
2. Chuyển workload sang principal mới và xác minh các thao tác hợp lệ.
3. Thu hồi grant cũ sau khi workload không còn sử dụng nó.

Trong giai đoạn chuyển tiếp, cả principal cũ và mới có thể cùng được phép. Đây là cửa sổ quyền mở rộng tạm thời, vì vậy cần đặt thời hạn kết thúc, giám sát usage và không để trạng thái kép kéo dài vô hạn.

Nếu credential cũ bị nghi ngờ đã lộ hoặc principal cũ đang bị kẻ tấn công kiểm soát, ưu tiên thu hồi khẩn cấp có thể quan trọng hơn tính liên tục. Khi đó, cần chấp nhận khả năng workload bị gián đoạn, giới hạn network hoặc dừng dịch vụ trong khi cấp identity mới.

Không xóa quyền cũ chỉ dựa vào việc deploy thành công. Cần xác nhận instance, job, worker, batch process và connection pool cũ đã chuyển sang identity mới; một số tiến trình có thể giữ credential trong cache lâu hơn thời gian triển khai.

## 8. Thay đổi policy an toàn và quản lý phiên bản

Policy của key là cấu hình nhạy cảm. Nên quản lý policy dưới dạng thay đổi có phiên bản và có khả năng xem lại:

- Lưu policy mong muốn trong hệ thống quản lý cấu hình được kiểm soát.
- Review diff để xác định principal, action, resource và condition được thêm/xóa.
- Dùng kiểm tra tự động để phát hiện wildcard, quyền quản trị trong runtime và quyền cross-environment.
- Áp dụng thay đổi theo đợt hoặc môi trường trước khi triển khai rộng.
- Lưu bản policy trước và sau cùng metadata phê duyệt.
- Kiểm tra policy hiệu lực sau khi cập nhật, vì policy ở nhiều lớp có thể tương tác.

Ví dụ minh họa diff khái niệm:

~~~diff
- principal: workload://prod/legacy-invoice
- actions: [Encrypt, Decrypt, CreateGrant]
- resource: key://prod/*
+ principal: workload://prod/invoice-api-v2
+ actions: [Decrypt]
+ resource: key://prod/invoice-data
+ condition:
+   environment: production
+   purpose: invoice-read
~~~

Đây chỉ là minh họa cách thu hẹp quyền. Cú pháp policy thực tế phụ thuộc KMS/IAM provider. Không triển khai một diff dạng này nếu chưa xác định CreateGrant có được workload cũ sử dụng hay không và workload mới có thật sự chỉ cần Decrypt không.

Nếu nền tảng hỗ trợ policy versioning, cần biết phiên bản nào đang có hiệu lực và cách rollback. Rollback policy không nên khôi phục một quyền đã bị thu hồi vì lý do sự cố bảo mật nếu chưa có phê duyệt incident response.

## 9. Permission rotation với KMS và HSM

KMS có thể quản lý grant, key policy và quyền IAM ở lớp dịch vụ. HSM có thể quản lý user, role, partition, session, key object attribute và quyền thao tác theo thiết bị. Cơ chế cụ thể khác nhau theo nhà cung cấp.

Khi rotation quyền trong KMS:

- Kiểm tra cả IAM policy và key policy; một lớp có thể cấp hoặc giới hạn quyền của lớp còn lại.
- Kiểm tra grant đang hoạt động và principal được ủy quyền tạo grant.
- Thu hồi grant cũ theo grant ID hoặc cơ chế tương đương.
- Xác minh thời gian lan truyền policy và hành vi credential/session đã cấp.
- Theo dõi audit event cho CreateGrant, RevokeGrant, PutKeyPolicy hoặc thao tác tương ứng.

Khi rotation quyền trong HSM:

- Xác định client, token, partition và role đang được dùng.
- Tạo hoặc cấp credential mới theo quy trình quản trị HSM.
- Gán quyền object tối thiểu cho thao tác cần thiết.
- Kiểm thử bằng đúng provider/PKCS#11 library và key object trên thiết bị.
- Thu hồi credential hoặc quyền của client cũ.
- Kiểm tra session đăng nhập cũ và audit log của HSM.

Không giả định thu hồi IAM grant sẽ tự động kết thúc một phiên HSM đã đăng nhập, hoặc thay đổi policy KMS sẽ lập tức vô hiệu hóa mọi credential/session đã cấp. Cần kiểm tra semantics và thời gian hiệu lực của đúng nền tảng.

## 10. Ví dụ: chuyển quyền của một Java workload

Giả sử dịch vụ invoice-api hiện dùng machine identity cũ invoice-service-v1. Dịch vụ cần quyền Decrypt trên key invoice-data để đọc dữ liệu. Nhóm vận hành chuyển sang identity mới invoice-service-v2.

| Bước | Principal v1 | Principal v2 | Kiểm tra |
|---|---|---|---|
| Trước thay đổi | Có Decrypt | Chưa có quyền | Ghi nhận audit và workload đang hoạt động |
| Cấp quyền mới | Có Decrypt | Được cấp Decrypt đúng key | Kiểm thử positive/negative |
| Chuyển workload | Có thể còn grant nhưng không còn được workload mới dùng | Workload mới dùng v2 | Xác nhận request log ghi principal v2 |
| Thu hồi | Bị xóa grant | Có Decrypt | Request từ v1 phải bị từ chối |
| Hoàn tất | Không còn quyền | Chỉ giữ quyền cần thiết | Kiểm tra policy hiệu lực và audit |

Pseudocode kiểm tra ở phía ứng dụng:

~~~java
// Pseudocode: API cụ thể phụ thuộc KMS SDK.
Identity identity = workloadIdentityProvider.currentIdentity();

if (!identity.subject().equals("workload://prod/invoice-service-v2")) {
    throw new SecurityException("Unexpected workload identity");
}

KmsClient kms = kmsClientFactory.forIdentity(identity);
byte[] plaintextDataKey = kms.decrypt(
        invoiceKey,
        encryptedDataKey,
        authenticatedContext);
~~~

Ứng dụng không nên tự coi chuỗi subject do nó đọc được là bằng chứng xác thực. SDK hoặc identity provider phải xác minh credential; KMS phải kiểm tra principal thực tế theo policy. Kiểm tra trong ứng dụng chỉ là lớp bảo vệ bổ sung và không thay thế authorization tại KMS.

Sau khi chuyển đổi, cần kiểm tra audit log từ KMS cho thấy request mới được gắn với identity v2. Sau khi thu hồi v1, thực hiện một yêu cầu kiểm thử có kiểm soát để xác nhận v1 bị từ chối.

## 11. Thu hồi quyền khẩn cấp

Nếu principal hoặc credential bị xâm nhập, không nhất thiết phải chờ cấp quyền thay thế hoàn tất. Quy trình khẩn cấp có thể gồm:

1. Xác định principal và key resource có khả năng bị ảnh hưởng.
2. Disable credential, revoke grant hoặc deny principal theo cơ chế nền tảng.
3. Chặn workload hoặc giới hạn network nếu cần để ngăn yêu cầu mới.
4. Kiểm tra session/token còn hiệu lực và thu hồi hoặc chờ hết hạn theo mức rủi ro.
5. Tạo identity/credential mới từ nguồn tin cậy sau khi xử lý nguyên nhân xâm nhập.
6. Cấp quyền tối thiểu cho workload sạch và xác minh bằng thao tác thực tế.
7. Kiểm tra audit log để xác định các key operation đã xảy ra.
8. Đánh giá xem plaintext key/data key có thể đã bị lấy hay không; nếu có, cân nhắc cryptographic key rotation và re-encryption riêng.

Thu hồi quyền ngăn principal thực hiện thao tác mới khi policy đã có hiệu lực. Nó không thể xóa bản plaintext data key hoặc dữ liệu đã được giải mã mà attacker đã lấy trước đó. Nếu có khả năng key material đã bị lộ, cần đánh giá riêng việc thay key và mã hóa lại dữ liệu.

## 12. Kiểm thử quyền mới và quyền đã thu hồi

Không chỉ kiểm tra rằng workload mới có thể thực hiện thao tác mong muốn. Cần kiểm tra cả các trường hợp phải bị từ chối:

- Principal mới được phép dùng đúng key resource và action.
- Principal mới bị từ chối khi truy cập key của môi trường khác.
- Principal mới bị từ chối với action quản trị như ScheduleDeletion hoặc PutKeyPolicy.
- Principal cũ bị từ chối sau khi grant đã thu hồi và thời gian propagation đã qua.
- Token hết hạn hoặc sai audience không được chấp nhận.
- Workload khác cùng cluster không thể mượn danh tính của workload mới.
- Context sai tenant hoặc purpose không được dùng để vượt policy.

Kiểm thử phải chạy với danh tính thật hoặc test principal tương đương trong môi trường được kiểm soát. Không dùng key production hoặc dữ liệu nhạy cảm thật để thử policy rộng nếu không có phê duyệt và kế hoạch an toàn.

## 13. Audit và bằng chứng hoàn tất

Một lần permission rotation cần có hồ sơ đủ để người khác xác minh:

- Principal và grant trước thay đổi.
- Principal, action, resource và condition mới.
- Lý do thay đổi, người yêu cầu, người phê duyệt và người thực hiện.
- Thời điểm cấp quyền mới, thời điểm chuyển workload và thời điểm thu hồi quyền cũ.
- Kết quả kiểm thử positive và negative.
- Audit event của KMS/HSM hoặc IAM cho từng thay đổi.
- Kết quả xác minh principal cũ không còn quyền hiệu lực.
- Policy version cuối cùng và phương án rollback đã đóng hoặc được giữ theo yêu cầu.

Không ghi token, private key hoặc plaintext data key vào hồ sơ. Audit nên lưu định danh principal và metadata thao tác, không lưu bí mật xác thực.

## 14. Rủi ro và lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Thêm quyền mới nhưng quên thu hồi quyền cũ | Quyền tích lũy, tăng bề mặt tấn công | Có deadline thu hồi và xác minh policy hiệu lực |
| Thu hồi quyền cũ trước khi workload mới sẵn sàng | Gián đoạn dịch vụ hoặc không thể đọc dữ liệu | Kiểm thử identity mới và lập kế hoạch chuyển đổi |
| Chỉ sửa IAM policy mà quên key policy/grant | Principal cũ vẫn có quyền qua lớp khác | Đánh giá effective permission trên mọi lớp policy |
| Cấp quyền wildcard để tránh lỗi vận hành | Workload có thể truy cập nhiều key ngoài nhu cầu | Giới hạn action/resource/condition cụ thể |
| Không kiểm tra token/session cache | Credential cũ vẫn có thể hoạt động | Kiểm tra TTL, revocation, propagation và session semantics |
| Dùng chung principal mới cho nhiều workload | Mất khả năng truy vết và thu hồi độc lập | Cấp identity riêng theo workload |
| Rollback policy cũ sau sự cố | Khôi phục quyền đã bị thu hồi vì rủi ro | Yêu cầu phê duyệt bảo mật trước rollback |
| Nhầm permission rotation với key rotation | Key material hoặc quyền cũ vẫn tồn tại | Lập kế hoạch riêng cho identity, grant và key version |
| Không thử negative case | Không phát hiện quyền ngoài dự kiến | Kiểm thử cả allow và deny |
| Không có audit evidence | Khó chứng minh quyền cũ đã bị loại bỏ | Lưu policy diff, approval và audit event |

## 15. Checklist triển khai

- [ ] Xác định rõ đây là permission rotation, credential rotation hay cryptographic key rotation.
- [ ] Lập inventory principal, key resource, action, grant, policy và workload phụ thuộc.
- [ ] Xác định quyền hiệu lực qua IAM, key policy, grant, session và điều kiện context.
- [ ] Thiết kế principal mới và cấp đúng quyền tối thiểu.
- [ ] Phê duyệt policy diff và thời gian chuyển đổi.
- [ ] Cấp quyền mới trước trong trường hợp chuyển đổi có kiểm soát.
- [ ] Kiểm thử thao tác được phép và các thao tác phải bị từ chối.
- [ ] Chuyển workload và xác minh request sử dụng identity mới.
- [ ] Thu hồi grant, role binding, credential và session cũ theo semantics của nền tảng.
- [ ] Xác minh principal cũ không còn quyền hiệu lực sau thời gian propagation.
- [ ] Lưu audit event, policy version, người phê duyệt và kết quả kiểm thử.
- [ ] Đánh giá riêng việc thay key material nếu có nghi ngờ lộ khóa hoặc plaintext data key.

Rotate key permission giúp quyền truy cập khóa luôn gắn với đúng workload và nhu cầu hiện tại. Quy trình an toàn cần kiểm kê quyền hiệu lực, cấp quyền mới có kiểm soát, xác minh hoạt động, thu hồi grant cũ và lưu bằng chứng audit; đồng thời xử lý cryptographic key rotation riêng khi key material có nguy cơ bị lộ.
