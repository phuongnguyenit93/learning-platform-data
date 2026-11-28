# Role-based key access

Role-based key access là cách kiểm soát quyền truy cập khóa mật mã dựa trên vai trò của danh tính trong hệ thống. Thay vì cấp quyền riêng lẻ cho từng người hoặc từng workload trên từng khóa, tổ chức định nghĩa các vai trò như Key Administrator, Crypto Operator, Auditor và Application Workload, gắn mỗi vai trò với một tập quyền cụ thể rồi cấp vai trò cho danh tính phù hợp trong một phạm vi xác định.

Trong quản lý khóa mật mã, kiểm soát truy cập quyết định ai được tạo, cấu hình, sử dụng, xoay vòng, vô hiệu hóa, khôi phục hoặc hủy khóa. Một sai sót trong phân quyền có thể khiến khóa bị xuất ra ngoài, dữ liệu bị giải mã trái phép, chữ ký bị giả mạo hoặc hoạt động bảo vệ dữ liệu bị gián đoạn. Vì vậy, RBAC phải gắn với vòng đời khóa, mục đích sử dụng, môi trường, mức độ nhạy cảm và trách nhiệm của từng chủ thể.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích mô hình Role-Based Access Control (RBAC) và cách áp dụng vào KMS/HSM.
- Phân biệt danh tính, vai trò, quyền, tài nguyên và phạm vi cấp quyền.
- Thiết kế các vai trò tách biệt giữa quản trị khóa, sử dụng khóa, kiểm toán và vận hành ứng dụng.
- Áp dụng nguyên tắc quyền tối thiểu, mặc định từ chối và phân tách nhiệm vụ.
- Nhận diện các quyền nhạy cảm như export key material, decrypt, sign, rotate, disable và delete.
- Thiết kế quy trình cấp, rà soát, thu hồi và kiểm toán quyền truy cập khóa.
- Kết hợp RBAC với điều kiện theo thuộc tính, danh tính workload, phê duyệt kép và cơ chế bảo vệ của KMS/HSM.

## 2. Vì sao cần kiểm soát quyền truy cập khóa?

Khóa mật mã thường là tài sản có giá trị cao. Người hoặc workload có quyền sử dụng khóa có thể giải mã dữ liệu, tạo chữ ký được hệ thống tin cậy hoặc xác thực thông điệp. Người có quyền quản trị khóa có thể thay đổi chính sách, cấp quyền cho người khác, xoay vòng hoặc vô hiệu hóa khóa. Nếu một danh tính có quá nhiều quyền, một tài khoản bị chiếm đoạt có thể gây ảnh hưởng lớn đến nhiều hệ thống.

Ví dụ, một dịch vụ báo cáo chỉ cần giải mã dữ liệu tổng hợp. Nếu workload này được cấp quyền quản trị toàn bộ key ring hoặc xuất vật liệu khóa, lỗi trong dịch vụ có thể trở thành đường dẫn để lấy khóa và truy cập dữ liệu ngoài phạm vi công việc.

Kiểm soát truy cập khóa cần giải quyết ba câu hỏi:

1. **Ai hoặc workload nào?** Danh tính phải được xác thực rõ ràng, chẳng hạn người dùng qua SSO hoặc workload qua service identity.
2. **Được phép làm gì?** Quyền phải mô tả thao tác cụ thể như xem metadata, mã hóa, giải mã, ký, xoay vòng hoặc thay đổi policy.
3. **Được phép trên tài nguyên nào và trong điều kiện nào?** Phạm vi có thể là một khóa, một nhóm khóa, một dự án, một môi trường hoặc một tenant; điều kiện có thể bao gồm trạng thái thiết bị, mạng, thời gian, mức độ phê duyệt và mục đích sử dụng.

Một quyết định truy cập an toàn phải xét đồng thời danh tính, quyền, tài nguyên và ngữ cảnh của request.

## 3. RBAC là gì?

Role-Based Access Control (RBAC) là mô hình phân quyền trong đó quyền được gom thành các vai trò. Người dùng, nhóm hoặc workload được gán một hay nhiều vai trò. Khi một danh tính thực hiện thao tác, hệ thống xác định các vai trò đang có hiệu lực và kiểm tra xem chúng có chứa quyền cần thiết trên tài nguyên đích hay không.

Các thành phần cơ bản:

| Thành phần | Ý nghĩa | Ví dụ trong quản lý khóa |
|---|---|---|
| Subject / Principal | Danh tính yêu cầu thao tác | Nhân viên vận hành, service account, workload identity |
| Role | Nhóm trách nhiệm có tập quyền xác định | Key Administrator, Crypto Operator, Auditor |
| Permission | Quyền thực hiện một thao tác trên loại tài nguyên | key.decrypt, key.rotate, key.getMetadata |
| Resource | Tài nguyên được bảo vệ | Key, key version, key ring, HSM partition |
| Role assignment / Binding | Liên kết principal với role trong phạm vi | Nhóm vận hành được gán Key Administrator trên project staging |
| Scope | Phạm vi mà role assignment có hiệu lực | Organization, project, key ring, key hoặc environment |

RBAC giúp quản lý quyền nhất quán khi số lượng người, workload và khóa tăng lên. Khi một nhân viên chuyển nhóm, quản trị viên có thể thay đổi vai trò thay vì rà từng quyền rời rạc. Khi một workload ngừng hoạt động, role binding của workload có thể được thu hồi.

RBAC không tự xác minh danh tính. Nó dựa vào hệ thống xác thực như SSO, IAM hoặc workload identity để xác định principal. RBAC cũng không tự giải quyết mọi điều kiện ngữ cảnh; các yêu cầu như chỉ cho phép giải mã từ workload production trong vùng mạng tin cậy có thể cần kết hợp ABAC hoặc policy condition.

## 4. Mô hình quyết định truy cập

Một quyết định RBAC có thể được mô tả như sau:

~~~text
principal = authenticatedIdentity
roles = activeRoles(principal, requestContext)
permissions = permissionsOf(roles)

if permissionFor(request.action, request.resource) is granted
   and allPolicyConditionsAreSatisfied:
    allow
else:
    deny
~~~

Ví dụ, workload billing-api-prod gửi yêu cầu giải mã một data encryption key đã được bọc:

- Principal: billing-api-prod.
- Role: BillingDecryptor.
- Permission: key.decrypt.
- Resource: khóa billing-data-kek-prod.
- Scope: project billing production.
- Điều kiện: workload identity hợp lệ, khóa đang hoạt động cho thao tác giải mã, request thuộc tenant được phép và policy không có quy tắc từ chối.

Nếu workload yêu cầu key.setPolicy hoặc key.export, role BillingDecryptor không có quyền đó nên yêu cầu phải bị từ chối.

> Ghi chú: Đây là mô hình khái niệm. Tên permission, cách kế thừa scope và thứ tự đánh giá policy khác nhau giữa các nền tảng KMS/IAM.

## 5. Thiết kế vai trò cho vòng đời khóa

Không nên tạo một vai trò duy nhất có toàn bộ quyền quản lý và sử dụng khóa. Hãy tách vai trò theo trách nhiệm và thao tác thực tế.

| Vai trò tham khảo | Trách nhiệm | Quyền thường cần | Quyền cần hạn chế |
|---|---|---|---|
| Key Administrator | Tạo khóa, cấu hình metadata, policy, lịch rotation và trạng thái | Tạo key, cập nhật cấu hình, quản lý version, gán policy trong phạm vi được duyệt | Không mặc nhiên được decrypt, sign hoặc export key material |
| Crypto Operator | Thực hiện thao tác mật mã theo nghiệp vụ | Encrypt, decrypt, sign hoặc unwrap theo mục đích được giao | Không thay policy, cấp role hoặc xóa khóa |
| Key Custodian | Quản lý quy trình lưu giữ, backup và khôi phục theo kiểm soát | Thực hiện bước được phê duyệt trong quy trình backup/recovery | Không tự ý dùng khóa cho nghiệp vụ hoặc thay đổi quyền |
| Security Approver | Phê duyệt thay đổi nhạy cảm | Xem đề xuất, phê duyệt hoặc từ chối thao tác theo quy trình | Không tự phê duyệt thay đổi do chính mình khởi tạo |
| Auditor | Kiểm tra cấu hình, quyền và nhật ký | Đọc metadata, policy, role binding và audit log | Không sử dụng khóa, sửa policy hoặc đọc vật liệu khóa |
| Application Workload | Dùng khóa để phục vụ một chức năng ứng dụng | Chỉ các thao tác cần thiết như encrypt hoặc decrypt trên khóa cụ thể | Không quản trị key ring, cấp quyền, export hoặc delete |
| Incident Responder | Xử lý sự cố khóa theo quy trình khẩn cấp | Tạm khóa, thu hồi hoặc thực hiện thao tác ứng cứu được phê duyệt | Quyền khẩn cấp phải giới hạn thời gian, phạm vi và có audit |

Tên vai trò chỉ là ví dụ. Một tổ chức có thể gộp hoặc tách vai trò tùy quy mô, nhưng phải giữ được ranh giới giữa người quản trị policy, workload sử dụng khóa và người kiểm toán.

### 5.1. Key Administrator

Key Administrator quản lý cấu hình và vòng đời của khóa. Công việc có thể gồm tạo khóa, chọn thuật toán và mục đích sử dụng, đặt nhãn và metadata, cấu hình rotation, quản lý version, cập nhật policy hoặc lên lịch vô hiệu hóa.

Vai trò này không nên tự động có quyền dùng khóa để giải mã dữ liệu hoặc ký thông điệp. Tách quyền quản trị khỏi quyền sử dụng giúp giảm khả năng một tài khoản bị chiếm đoạt vừa cấp quyền cho chính nó vừa khai thác khóa.

### 5.2. Crypto Operator

Crypto Operator hoặc workload được cấp vai trò tương đương chỉ thực hiện các thao tác mật mã được giao. Một workload mã hóa dữ liệu có thể chỉ cần encrypt; một dịch vụ đọc dữ liệu có thể cần decrypt; một dịch vụ phát hành token có thể cần sign.

Không cấp decrypt chỉ vì workload đã có encrypt. Hai thao tác có thể tạo ra mức độ rủi ro khác nhau. Không cấp sign cho mọi dịch vụ có quyền truy cập metadata của khóa ký. Mỗi thao tác cần được xem xét theo mục đích nghiệp vụ.

### 5.3. Auditor

Auditor cần khả năng quan sát để xác minh ai có quyền gì, policy nào đang áp dụng và thao tác nào đã xảy ra. Auditor thường cần đọc metadata, role assignment, cấu hình key version và audit log. Auditor không cần đọc plaintext key material hoặc thực hiện phép giải mã để hoàn thành nhiệm vụ kiểm toán.

Quyền chỉ đọc không phải lúc nào cũng vô hại. Metadata có thể tiết lộ tên hệ thống, quan hệ tenant, môi trường hoặc cấu trúc bảo vệ dữ liệu. Vì vậy, quyền đọc cũng nên được giới hạn theo phạm vi cần kiểm toán.

### 5.4. Application Workload

Workload cần danh tính riêng, chẳng hạn service account hoặc workload identity gắn với dịch vụ. Không dùng một tài khoản máy dùng chung cho nhiều ứng dụng nếu có thể tách danh tính.

Role của workload nên giới hạn vào:

- Đúng khóa hoặc nhóm khóa mà dịch vụ sử dụng.
- Đúng thao tác mật mã cần cho chức năng.
- Đúng môi trường và tenant.
- Đúng đường gọi và danh tính workload đã xác thực.

Không nhúng credential quản trị KMS vào image, source code hoặc file cấu hình. Ưu tiên cơ chế workload identity để KMS nhận diện workload mà không cần một secret dài hạn dùng chung.

## 6. Phân biệt quyền quản trị và quyền sử dụng khóa

Quyền trên khóa cần được mô tả theo thao tác cụ thể. Một số permission tiêu biểu:

| Nhóm quyền | Ví dụ thao tác | Tác động bảo mật |
|---|---|---|
| Discover / Read metadata | Liệt kê key, đọc metadata, xem trạng thái và version | Tiết lộ thông tin cấu hình và cấu trúc hệ thống |
| Create / Import | Tạo key hoặc nhập key material | Đưa vật liệu mật mã mới vào miền tin cậy |
| Configure | Đặt thuật toán, purpose, rotation, protection level | Thay đổi cách khóa được sử dụng và bảo vệ |
| Encrypt / Wrap | Mã hóa dữ liệu hoặc bọc DEK | Cho phép tạo ciphertext hoặc bảo vệ khóa dữ liệu |
| Decrypt / Unwrap | Giải mã dữ liệu hoặc mở DEK | Có thể làm lộ dữ liệu plaintext |
| Sign | Tạo chữ ký số hoặc MAC | Có thể tạo bằng chứng được hệ thống khác tin cậy |
| Verify | Xác minh chữ ký hoặc MAC | Thường ít nhạy cảm hơn ký nhưng vẫn cần giới hạn tài nguyên |
| Rotate / Create version | Tạo phiên bản khóa mới | Thay đổi phiên bản dùng cho thao tác tương lai |
| Disable / Enable | Vô hiệu hóa hoặc kích hoạt khóa | Có thể làm gián đoạn hoặc khôi phục dịch vụ |
| Set policy / Grant access | Thay policy hoặc cấp quyền | Có thể mở rộng quyền của principal khác |
| Export / Get key material | Xuất vật liệu khóa | Có nguy cơ đưa khóa ra khỏi ranh giới bảo vệ |
| Destroy / Schedule deletion | Hủy hoặc lên lịch hủy khóa | Có thể làm dữ liệu không thể giải mã hoặc chữ ký không thể tạo |

Một permission tổng quát như key.admin thường che giấu nhiều quyền có tác động khác nhau. Nếu nền tảng chỉ cung cấp role dựng sẵn, cần đọc kỹ quyền bên trong role đó và kiểm tra xem nó có bao gồm quyền sử dụng, export hoặc thay policy hay không.

Đặc biệt, quyền set policy có thể gián tiếp trao quyền sử dụng khóa. Một principal không có decrypt nhưng có thể sửa policy để tự cấp decrypt vẫn có khả năng đạt được quyền giải mã. Vì vậy, quyền thay policy phải được coi là quyền nhạy cảm và kiểm soát riêng.

## 7. Nguyên tắc quyền tối thiểu

Least privilege yêu cầu mỗi principal chỉ có tập quyền nhỏ nhất đủ để hoàn thành nhiệm vụ. Áp dụng nguyên tắc này theo từng chiều:

- **Principal:** mỗi người và workload có danh tính riêng, tránh tài khoản dùng chung.
- **Operation:** chỉ cấp thao tác cần thiết, ví dụ encrypt thay vì toàn bộ quyền sử dụng.
- **Resource:** giới hạn vào key hoặc key ring cụ thể.
- **Scope:** tách organization, project, environment và tenant.
- **Time:** cấp quyền tạm thời khi công việc chỉ diễn ra trong một khoảng thời gian.
- **Context:** yêu cầu thiết bị, mạng, ticket hoặc phê duyệt phù hợp với thao tác nhạy cảm.

Ví dụ, workload invoice-writer chỉ cần mã hóa DEK cho dữ liệu hóa đơn. Role phù hợp có thể cho phép key.wrap trên một KEK production trong project billing. Workload không cần key.decrypt, key.setPolicy, key.export hoặc key.destroy.

Không cấp quyền rộng chỉ để tránh lỗi permission trong triển khai. Khi request bị từ chối, hãy xác định thao tác và tài nguyên thực sự cần thiết, sau đó cập nhật role hoặc policy có kiểm soát.

## 8. Mặc định từ chối và quyền kế thừa

Một hệ thống quản lý khóa nên áp dụng nguyên tắc default deny: nếu không có rule cho phép rõ ràng và hợp lệ, request bị từ chối. Không coi việc một principal không nằm trong danh sách từ chối là bằng chứng rằng principal đó được phép.

Khi quyền có thể kế thừa từ organization xuống project, key ring và key, cần hiểu rõ phạm vi kế thừa. Một role được gán ở cấp project có thể áp dụng cho tất cả key trong project, kể cả key tạo sau này. Điều này tiện lợi nhưng làm tăng phạm vi ảnh hưởng khi gán nhầm role.

Nên ưu tiên gán role ở phạm vi nhỏ nhất đáp ứng công việc. Dùng role ở cấp project hoặc organization chỉ khi có lý do rõ ràng, owner chịu trách nhiệm và quy trình rà soát phù hợp.

Nếu nền tảng hỗ trợ policy deny, explicit deny thường cần được hiểu và kiểm tra theo quy tắc đánh giá của chính nền tảng. Không giả định mọi KMS có cùng cách xử lý allow, deny, inheritance hoặc policy boundary.

## 9. Phân tách nhiệm vụ (Separation of Duties)

Phân tách nhiệm vụ ngăn một người hoặc một danh tính tự thực hiện toàn bộ chuỗi hành động nhạy cảm. Trong quản lý khóa, một người có thể đề xuất thay đổi policy, người khác phê duyệt, còn workload chuyên trách thực hiện thao tác mật mã.

Ví dụ quy trình thay đổi quyền giải mã cho khóa production:

1. Chủ dịch vụ gửi yêu cầu nêu rõ principal, khóa, thao tác, lý do và thời hạn.
2. Key Administrator chuẩn bị thay đổi role hoặc policy.
3. Security Approver kiểm tra phạm vi, mục đích và rủi ro.
4. Một người có quyền triển khai áp dụng thay đổi.
5. Auditor hoặc hệ thống giám sát kiểm tra audit event sau thay đổi.

Người khởi tạo không nên tự phê duyệt yêu cầu của chính mình. Tài khoản khẩn cấp phải có cơ chế kiểm soát bổ sung và được rà soát sau khi sử dụng.

### 9.1. Dual control và M-of-N

Dual control yêu cầu ít nhất hai người độc lập tham gia một hành động nhạy cảm. M-of-N yêu cầu một số lượng người tối thiểu trong một nhóm được chỉ định cùng tham gia hoặc cung cấp phần kiểm soát cần thiết.

Các cơ chế này thường phù hợp với:

- Thay đổi policy cho khóa gốc hoặc khóa quan trọng.
- Xuất, nhập hoặc khôi phục key material theo quy trình đặc biệt.
- Hủy khóa có tác động lớn.
- Mở quyền truy cập khẩn cấp vào miền khóa production.

RBAC xác định ai có thể tham gia từng bước; dual control bổ sung điều kiện cần nhiều người độc lập. Hai cơ chế hỗ trợ nhau nhưng không thay thế nhau. Một role có tên Approver không bảo đảm quy trình có độc lập nếu cùng một người có thể tự cấp role đó cho mình.

## 10. RBAC kết hợp ABAC và policy condition

RBAC phân quyền dựa trên vai trò. Attribute-Based Access Control (ABAC) đánh giá thêm thuộc tính của principal, resource, action và môi trường. Kết hợp hai mô hình giúp quyền vừa dễ quản lý vừa đủ chi tiết.

Ví dụ:

- RBAC: principal có role ProductionDecryptor.
- Thuộc tính principal: workload identity là billing-api-prod.
- Thuộc tính resource: key có tag environment=production và data-domain=billing.
- Thuộc tính request: action là decrypt, request có tenant hợp lệ.
- Thuộc tính môi trường: request đến từ workload runtime được tin cậy.

Chỉ cho phép khi role đúng và mọi điều kiện cần thiết đều đạt. Tag hoặc attribute dùng trong policy phải được bảo vệ; nếu workload có thể tự sửa tag để mở rộng quyền, điều kiện ABAC có thể bị vô hiệu hóa.

Policy ví dụ dưới đây chỉ minh họa ý tưởng:

~~~yaml
role: ProductionDecryptor
permissions:
  - action: key.decrypt
    resource: key/billing-data-kek-prod
conditions:
  principal:
    workload_identity: billing-api-prod
  resource:
    environment: production
    data_domain: billing
  request:
    tenant_must_match: true
    approved_purpose: invoice-read
effect: allow
default: deny
~~~

Trong triển khai thực tế, dùng cú pháp policy và cơ chế condition của nền tảng. Không sao chép ví dụ này như policy có thể áp dụng trực tiếp vào một nhà cung cấp cụ thể.

## 11. Phạm vi role assignment

Role có thể được gán ở nhiều cấp:

| Phạm vi | Ví dụ | Điểm cần cân nhắc |
|---|---|---|
| Organization | Nhóm quản trị bảo mật toàn tổ chức | Tác động rộng; số principal cần giữ rất nhỏ |
| Project / Account | Nhóm vận hành KMS của một dự án | Phù hợp quản trị tài nguyên theo team hoặc hệ thống |
| Key ring / Collection | Nhóm khóa cho một ứng dụng hoặc miền dữ liệu | Giới hạn phạm vi tốt hơn cấp project |
| Individual key | Một khóa dùng cho nghiệp vụ cụ thể | Kiểm soát chính xác nhưng cần quản lý nhiều binding |
| Key version | Phiên bản khóa cụ thể | Hữu ích khi cần giới hạn thao tác theo phiên bản, nếu nền tảng hỗ trợ |

Không phải nền tảng nào cũng hỗ trợ role assignment ở tất cả các cấp. Cần kiểm tra cách nền tảng áp dụng inheritance, policy boundary và resource hierarchy.

Đặt tên role và binding theo trách nhiệm và phạm vi, ví dụ billing-prod-decryptor hoặc security-key-auditor. Tên cần giúp người vận hành nhận ra owner, môi trường và mục đích mà không tiết lộ secret.

## 12. Quy trình cấp quyền truy cập khóa

Một quy trình cấp quyền tốt bắt đầu từ nhu cầu nghiệp vụ và kết thúc bằng bằng chứng kiểm tra:

1. **Xác định chủ thể:** người dùng, nhóm hoặc workload nào cần truy cập? Danh tính đã được quản lý bởi hệ thống xác thực nào?
2. **Xác định tài nguyên:** khóa nào, key ring nào, project nào và môi trường nào?
3. **Xác định thao tác:** cần đọc metadata, encrypt, decrypt, sign, rotate hay quản trị policy?
4. **Xác định lý do và thời hạn:** nhiệm vụ nào yêu cầu quyền này, ai là owner, khi nào quyền hết hiệu lực?
5. **Chọn role phù hợp:** dùng role hiện có nếu tập quyền vừa đủ; nếu tạo role mới, ghi rõ permission và owner.
6. **Kiểm tra xung đột nhiệm vụ:** người đề xuất, phê duyệt và triển khai có đáp ứng quy tắc độc lập không?
7. **Gán role trong scope nhỏ nhất:** tránh binding ở cấp cao hơn nhu cầu.
8. **Kiểm tra bằng danh tính thực:** xác minh thao tác được phép hoạt động và thao tác ngoài phạm vi bị từ chối.
9. **Ghi audit:** lưu ai yêu cầu, ai duyệt, ai thực hiện, role nào, resource nào và thời hạn nào.
10. **Đặt lịch rà soát:** quyền tạm thời phải được thu hồi; quyền dài hạn cần được xem lại định kỳ.

Không gửi key material qua ticket hoặc kênh phê duyệt để chứng minh nhu cầu. Chỉ sử dụng key ID, resource path và metadata không bí mật.

## 13. Ví dụ: RBAC cho KMS trong hệ thống thanh toán

Giả sử hệ thống thanh toán có ba workload: payment-api, settlement-worker và reporting-service. Các dịch vụ sử dụng KEK để bảo vệ DEK theo mô hình envelope encryption.

Thiết kế role tham khảo:

| Principal | Role | Quyền trên khóa | Mục đích |
|---|---|---|---|
| payment-api-prod | PaymentEncryptor | encrypt hoặc wrap | Bọc DEK khi ghi dữ liệu thanh toán |
| settlement-worker-prod | SettlementDecryptor | decrypt hoặc unwrap | Mở DEK cho quy trình đối soát |
| reporting-service-prod | ReportingDecryptor | decrypt trên key riêng và phạm vi dữ liệu báo cáo | Đọc dữ liệu đã được phê duyệt |
| kms-admin-team | Key Administrator | Tạo key, cấu hình rotation, quản lý metadata và policy theo quy trình | Vận hành vòng đời khóa |
| security-audit-team | Key Auditor | Đọc policy, metadata và audit log | Kiểm toán quyền và hoạt động |

Không cấp quyền giải mã toàn bộ cho payment-api chỉ vì dịch vụ này có quyền bọc DEK. Reporting cũng không nên dùng chung danh tính với settlement. Việc tách principal cho phép thu hồi hoặc điều chỉnh một workload mà không ảnh hưởng tất cả dịch vụ.

Luồng xử lý:

1. payment-api-prod xác thực bằng workload identity.
2. KMS kiểm tra role binding và policy của KEK.
3. KMS cho phép thao tác wrap/encrypt trong phạm vi được cấp.
4. Ciphertext và encrypted DEK được lưu theo thiết kế dữ liệu.
5. Khi settlement cần đọc dữ liệu, settlement-worker-prod xác thực riêng và yêu cầu unwrap/decrypt.
6. KMS đánh giá quyền và ghi audit event cho thao tác.
7. Auditor rà soát role assignment, hoạt động và các quyền bất thường.

> Ghi chú: Ví dụ không quy định một sản phẩm KMS cụ thể. Một số nền tảng dùng tên wrap/unwrap, nền tảng khác biểu diễn thao tác tương đương bằng encrypt/decrypt.

## 14. Quyền truy cập trong môi trường HSM

HSM thường có các miền quản trị và sử dụng mật mã riêng. Tùy sản phẩm, HSM có thể phân biệt security officer, crypto officer, user, partition administrator hoặc client application. Các vai trò này không nhất thiết tương ứng một-một với role trong IAM.

Khi thiết kế RBAC cho HSM:

- Tách quyền quản trị thiết bị, partition và policy khỏi quyền thực hiện phép mật mã.
- Dùng partition hoặc security domain để cô lập nhóm khóa và ứng dụng khi phù hợp.
- Giới hạn thao tác export/import theo cơ chế bảo vệ và phê duyệt đặc biệt.
- Bảo vệ thông tin xác thực của HSM và token quản trị như credential có độ nhạy cảm cao.
- Áp dụng dual control hoặc quorum cho thao tác ảnh hưởng lớn nếu HSM hỗ trợ.
- Ghi nhận và giám sát hoạt động quản trị cũng như hoạt động mật mã.

Không giả định việc lưu khóa trong HSM tự động làm cho mọi thao tác an toàn. Một workload có quyền gọi decrypt vẫn có thể yêu cầu HSM giải mã dữ liệu trái phép nếu policy và ứng dụng không giới hạn đúng mục đích.

## 15. Quản lý role và thay đổi nhân sự

Role assignment là dữ liệu có vòng đời. Khi nhân viên chuyển nhóm, nghỉ việc hoặc thay đổi trách nhiệm, quyền truy cập khóa phải được cập nhật cùng quy trình offboarding hoặc chuyển vai trò. Với workload, khi dịch vụ được thay thế hoặc ngừng chạy, danh tính và binding tương ứng cần được thu hồi.

Quy trình quản lý role cần bao gồm:

- **Joiner:** tạo danh tính, xác định nhóm và cấp role theo công việc đã được phê duyệt.
- **Mover:** rà soát quyền cũ, thu hồi quyền không còn cần và cấp role mới.
- **Leaver:** vô hiệu hóa danh tính, thu hồi role binding, token và quyền truy cập liên quan.
- **Workload lifecycle:** tạo danh tính riêng khi triển khai, cập nhật binding khi đổi service, thu hồi khi workload ngừng hoạt động.
- **Temporary access:** tự động hết hạn hoặc có ticket và owner chịu trách nhiệm thu hồi.

Không chỉ xóa người dùng khỏi một nhóm rồi giả định mọi quyền đã biến mất. Cần kiểm tra role binding trực tiếp, nhóm lồng nhau, quyền kế thừa, service account key, token và các cơ chế truy cập ngoại lệ.

## 16. Rà soát quyền định kỳ

Access review xác nhận mỗi role assignment vẫn cần thiết, đúng owner và đúng scope. Lịch rà soát tùy mức độ rủi ro; quyền quản trị, quyền export, quyền decrypt diện rộng và quyền thay policy cần được xem xét thường xuyên hơn quyền đọc metadata có phạm vi hẹp.

Trong mỗi đợt rà soát, cần kiểm tra:

1. Principal còn tồn tại và còn thuộc đúng team hoặc workload không?
2. Role có chứa permission vượt nhu cầu hiện tại không?
3. Binding có được gán ở scope quá rộng không?
4. Có quyền trực tiếp và quyền kế thừa tạo ra tổng quyền lớn hơn dự kiến không?
5. Có role hoặc binding không có owner, không có lý do hoặc không có thời hạn không?
6. Có tài khoản dùng chung hoặc credential dài hạn không được quản lý không?
7. Có quyền nhạy cảm được cấp tạm thời nhưng chưa thu hồi không?
8. Có principal nào vừa có thể thay policy, tự cấp quyền và sử dụng khóa không?

Kết quả review cần ghi lại quyết định giữ, giảm, thay đổi hoặc thu hồi quyền, người xác nhận và thời điểm hoàn tất.

## 17. Kiểm toán và giám sát hoạt động truy cập

Audit log cần ghi lại tối thiểu:

- Principal đã xác thực và role hoặc policy context có liên quan.
- Hành động được yêu cầu, resource và scope.
- Thời điểm, request ID và kết quả allow/deny.
- Lý do từ chối hoặc policy condition không thỏa mãn nếu nền tảng cung cấp.
- Người yêu cầu, phê duyệt và thực hiện thay đổi role hoặc policy.
- Thay đổi trạng thái khóa, version, lịch rotation và policy.

Không ghi plaintext key material, secret xác thực hoặc dữ liệu giải mã vào audit log. Log cần được bảo vệ khỏi sửa đổi và chỉ cho phép nhóm phù hợp đọc.

Một số tín hiệu đáng chú ý:

- Workload đột ngột gọi decrypt hoặc sign với tần suất tăng cao.
- Principal truy cập khóa ngoài giờ hoặc từ môi trường không mong đợi.
- Role binding được mở rộng ở cấp project hoặc organization.
- Một principal tự cấp thêm quyền cho chính mình.
- Nhiều lần truy cập bị từ chối liên tiếp hoặc có hành động trên khóa ngoài mục đích.
- Thao tác disable, delete, export hoặc thay policy không có yêu cầu thay đổi tương ứng.
- Danh tính cũ tiếp tục sử dụng khóa sau khi đã chuyển giao hoặc ngừng hoạt động.

Giám sát cần liên kết alert với owner và quy trình phản ứng để có thể thu hồi quyền hoặc khóa kịp thời.

## 18. Xử lý truy cập khẩn cấp

Một số sự cố đòi hỏi quyền tạm thời vượt quá vai trò thông thường, chẳng hạn vô hiệu hóa khóa bị nghi ngờ lộ hoặc khôi phục dịch vụ sau lỗi KMS. Cơ chế break-glass có thể đáp ứng nhu cầu này nhưng phải được thiết kế chặt chẽ.

Một quy trình break-glass nên có:

- Danh tính khẩn cấp riêng, được bảo vệ và không dùng trong công việc thường ngày.
- Phạm vi quyền và loại thao tác được giới hạn.
- Phê duyệt độc lập khi điều kiện cho phép; nếu tình huống cần hành động ngay, yêu cầu hậu kiểm trong thời hạn rõ ràng.
- Thời gian hiệu lực ngắn và tự động thu hồi quyền.
- Cảnh báo tức thời khi danh tính khẩn cấp được sử dụng.
- Audit log bất biến hoặc được bảo vệ độc lập.
- Rà soát nguyên nhân, thao tác và quyền đã dùng sau sự cố.

Không dùng tài khoản break-glass làm tài khoản quản trị dự phòng hằng ngày. Quyền khẩn cấp phải được thử nghiệm định kỳ để đảm bảo có thể sử dụng khi cần nhưng không trở thành đường truy cập thường trực.

## 19. Những sai lầm thường gặp

- Gán một role quản trị toàn quyền cho tất cả kỹ sư vì dễ vận hành.
- Dùng chung một service account cho nhiều workload khiến không thể giới hạn hoặc quy trách nhiệm riêng.
- Cho phép workload decrypt chỉ vì nó đã có encrypt.
- Gán role ở cấp organization trong khi nhu cầu chỉ liên quan một key ring.
- Không rà soát quyền kế thừa từ nhóm hoặc project.
- Để Key Administrator đồng thời tự cấp quyền, phê duyệt và sử dụng khóa nhạy cảm.
- Cho Auditor quyền gọi phép giải mã để kiểm tra dữ liệu dù audit metadata đã đủ.
- Cho phép principal sửa policy và tự cấp permission nhạy cảm mà không có kiểm soát độc lập.
- Bỏ quên role binding của nhân viên chuyển nhóm hoặc workload đã ngừng hoạt động.
- Dùng quyền khẩn cấp lâu dài và không giám sát việc sử dụng.
- Chỉ kiểm tra trường hợp allow mà không kiểm tra các thao tác ngoài phạm vi có bị deny hay không.

Các lỗi này thường xuất phát từ việc thiết kế role theo chức danh chung chung thay vì theo thao tác, tài nguyên và trách nhiệm thực tế.

## 20. Checklist thiết kế và vận hành RBAC cho key

- [ ] Mỗi người dùng và workload có danh tính riêng, được xác thực đáng tin cậy.
- [ ] Vai trò phản ánh trách nhiệm cụ thể trong vòng đời khóa.
- [ ] Permission được tách theo thao tác: metadata, encrypt, decrypt, sign, rotate, policy, export và destroy.
- [ ] Quyền quản trị được tách khỏi quyền sử dụng khóa.
- [ ] Mỗi role chỉ có quyền tối thiểu cần thiết.
- [ ] Role assignment được giới hạn ở scope nhỏ nhất phù hợp.
- [ ] Mặc định từ chối khi không có quyền cho phép rõ ràng.
- [ ] Quyền kế thừa và quyền từ nhóm lồng nhau được kiểm tra.
- [ ] Có phân tách nhiệm vụ và phê duyệt độc lập cho thao tác nhạy cảm.
- [ ] Workload identity được ưu tiên thay cho credential quản trị dùng chung.
- [ ] Role tạm thời có thời hạn và quy trình tự động hoặc rõ ràng để thu hồi.
- [ ] Có access review định kỳ và quy trình joiner/mover/leaver.
- [ ] Audit log ghi nhận allow, deny, thay đổi policy và thao tác vòng đời khóa.
- [ ] Có cảnh báo cho quyền bất thường và thao tác nhạy cảm.
- [ ] Break-glass có giới hạn, giám sát, hậu kiểm và thu hồi.
- [ ] Đã kiểm thử cả thao tác được phép lẫn thao tác phải bị từ chối.

## Kết luận

Role-based key access giúp tổ chức quản lý quyền trên khóa theo trách nhiệm thay vì cấp quyền rời rạc cho từng danh tính. Một thiết kế an toàn tách vai trò quản trị, sử dụng mật mã, kiểm toán và ứng dụng; đồng thời giới hạn permission theo thao tác, resource, scope và thời gian. RBAC cần đi cùng default deny, least privilege, separation of duties, rà soát định kỳ và audit log. Với thao tác nhạy cảm, có thể bổ sung ABAC, phê duyệt kép và quyền khẩn cấp có kiểm soát. Khi áp dụng trên KMS hoặc HSM, phải hiểu đúng cơ chế role, policy và quyền kế thừa của nền tảng để đảm bảo mỗi principal chỉ có thể thực hiện những thao tác khóa cần thiết cho công việc của mình.
