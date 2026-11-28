# Key destruction – Hủy khóa mật mã an toàn

**Key destruction** (hủy khóa mật mã) là quá trình làm cho **vật liệu khóa bí mật không còn khả năng sử dụng hoặc khôi phục** theo phạm vi hủy đã xác định, đồng thời tạo được bằng chứng về thao tác đó. Khóa có thể là khóa đối xứng, khóa mã hóa dữ liệu (DEK), khóa bọc khóa (KEK), hoặc thành phần **private key** của một cặp khóa bất đối xứng. Trong thực tế, để việc hủy có hiệu lực, cần xử lý cả những bản sao khóa, bản sao lưu, bản sao ở vùng dự phòng, phiên bản được sao chép, khóa lưu tạm hoặc dạng khóa đã được bọc mà vẫn có thể khôi phục.

Trong module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, key destruction nằm ở cuối vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**, nhưng kế hoạch hủy phải được đặt ra ngay từ lúc thiết kế. Hủy đúng giúp giảm khả năng lộ khóa cũ và thực thi chính sách xóa dữ liệu; hủy sai có thể làm **mất dữ liệu vĩnh viễn** hoặc làm gián đoạn chữ ký số, mã hóa, giải mã và khôi phục thảm họa.

> **Cốt lõi:** Xóa một mục trên giao diện quản trị, ngừng sử dụng một khóa hoặc xóa tên định danh khóa **chưa đủ để kết luận khóa đã bị hủy**. Kết luận phải dựa vào trạng thái vật liệu khóa, các bản sao, khả năng khôi phục và bằng chứng thực tế của hệ thống KMS/HSM/kho lưu trữ.

## 1. Phân biệt những thao tác dễ nhầm

| Thao tác | Bản chất | Khả năng sử dụng/khôi phục |
| --- | --- | --- |
| **Disable / Deactivate** (vô hiệu hóa) | Tạm ngăn các lệnh sử dụng một khóa qua hệ thống quản lý. | Thường có thể bật lại; vật liệu khóa vẫn tồn tại. |
| **Revoke** (thu hồi) | Rút hiệu lực tin cậy/quyền sử dụng theo chính sách, ví dụ thu hồi chứng chỉ hoặc gỡ public key khỏi tập khóa tin cậy. | Không nhất thiết xóa vật liệu khóa; hệ thống bên ngoài có thể vẫn cần cập nhật trạng thái thu hồi. |
| **Rotate** (xoay vòng) | Chuyển sang khóa/phiên bản mới cho thao tác mới. | Khóa cũ có thể vẫn cần để giải mã dữ liệu hoặc xác minh chữ ký cũ. |
| **Delete metadata/reference** | Xóa nhãn, alias hoặc bản ghi quản trị. | Không đảm bảo bản sao vật liệu khóa đã biến mất. |
| **Key destruction** (hủy khóa) | Loại bỏ khả năng sử dụng/khôi phục vật liệu khóa trong phạm vi kiểm soát đã xác minh. | Được thiết kế là không thể đảo ngược sau khi hủy hoàn tất. |
| **Cryptographic erasure / crypto-shredding** | Làm dữ liệu mã hóa không thể giải mã bằng cách hủy tất cả khóa có thể mở dữ liệu đó. | Chỉ hiệu quả khi không còn bản sao khóa, đường giải mã khác hoặc dữ liệu rõ cần bảo vệ. |

**Đặc biệt với key pair:** hủy **private key** làm mất khả năng ký/giải mã hoặc thực hiện phép toán bí mật tương ứng. Public key không phải bí mật nên có thể vẫn được lưu để xác minh chữ ký lịch sử, nhưng phải xác định hiệu lực và trạng thái tin cậy theo chính sách. **Hủy private key không tự động thu hồi chứng chỉ hay làm cho mọi chữ ký đã phát hành trở nên không hợp lệ.**

## 2. Vì sao phải hủy khóa?

Hệ thống có thể cần hủy khóa khi:

1. **Hết thời hạn giữ dữ liệu hoặc khóa:** tuân thủ chính sách lưu trữ sau khi các phụ thuộc giải mã/xác minh đã được xử lý.
2. **Thay thế hệ thống hoặc giải thể môi trường:** dừng hoàn toàn workload, ứng dụng, tenant hoặc môi trường thử nghiệm.
3. **Phát hiện khóa bị lộ:** khóa cần được vô hiệu hóa và hạn chế sử dụng ngay, sau đó thu hồi, thay thế và hủy theo kế hoạch ứng phó; không bỏ qua tác động đến dữ liệu cũ.
4. **Xóa dữ liệu bằng mật mã:** hủy một DEK độc lập để khiến phần dữ liệu do DEK đó mã hóa không thể khôi phục qua đường khóa hợp lệ.
5. **Thay đổi thuật toán/chính sách bảo mật:** sau khi di chuyển và kiểm chứng dữ liệu với khóa mới, khóa cũ có thể được hủy.

**Không được hủy chỉ vì đã tạo khóa mới.** Hệ thống thường vẫn có bản mã, bản sao lưu, token, tài liệu được ký hoặc thông điệp lịch sử liên kết với key ID cũ. Cần phân biệt: khóa phục vụ **giải mã** bản mã cũ; public key có thể đủ cho **xác minh** chữ ký cũ, nhưng chữ ký lâu dài còn cần thông tin chứng chỉ và trạng thái tin cậy phù hợp.

## 3. Hủy khóa tác động thế nào tới từng loại khóa?

### 3.1. Khóa đối xứng

Nếu nhiều tệp hoặc bản ghi đều mã hóa bằng một khóa đối xứng duy nhất, việc hủy khóa đó có thể khiến **tất cả** dữ liệu liên quan không thể giải mã. Đây có thể là mục tiêu khi xóa toàn bộ tập dữ liệu, nhưng là lỗi nghiêm trọng nếu một phần dữ liệu vẫn phải lưu giữ.

Do đó nên quản lý **key ID, phiên bản, mục đích và tập dữ liệu phụ thuộc**, tránh tái sử dụng một DEK cho những nhóm dữ liệu có thời hạn xóa khác nhau khi cần hủy riêng lẻ.

### 3.2. Khóa bất đối xứng

- Với khóa dùng để **giải mã** (ví dụ private key RSA-OAEP), hủy private key khi vẫn còn bản mã phụ thuộc sẽ khiến dữ liệu không thể giải mã, trừ khi tồn tại khóa/đường khôi phục khác đã được thiết kế.
- Với khóa dùng để **ký số** (ví dụ Ed25519 hoặc ECDSA), hủy private key ngăn tạo chữ ký mới từ khóa đó. Chữ ký cũ vẫn có thể được xác minh bằng public key, nếu chính sách tin cậy và dữ liệu bằng chứng được lưu phù hợp.
- Với khóa dùng để **thỏa thuận khóa** (ví dụ X25519), hậu quả phụ thuộc giao thức và loại khóa lâu dài/khóa phiên; không nên suy luận rằng hủy một khóa sẽ xóa tất cả bí mật phiên đã được tạo và lưu ở nơi khác.

### 3.3. DEK và KEK trong envelope encryption

**Envelope encryption** thường dùng một **DEK** để mã hóa dữ liệu, sau đó dùng **KEK** (thường được quản lý bởi KMS) để bọc/mã hóa DEK. DEK đã bọc được lưu bên cạnh dữ liệu, trong khi vật liệu KEK được bảo vệ ở lớp quản lý khóa.

~~~mermaid
flowchart TB
    DATA["Dữ liệu rõ"] --> ENC["Mã hóa bằng DEK"]
    DEK["DEK"] --> ENC
    ENC --> CIPHER["Bản mã dữ liệu"]
    DEK --> WRAP["Bọc DEK bằng KEK"]
    KEK["KEK trong KMS/HSM"] --> WRAP
    WRAP --> WDEK["DEK đã bọc"]
    CIPHER --> STORE["Lưu bản mã + DEK đã bọc"]
    WDEK --> STORE
~~~

Hủy **DEK** (và mọi bản sao có khả năng dùng lại) có thể giúp xóa bằng mật mã cho phạm vi dữ liệu của DEK. Hủy **KEK** có thể khiến *nhiều DEK được bọc dưới KEK đó* không thể giải bọc; phạm vi mất dữ liệu vì thế rộng hơn. Nếu DEK vẫn còn ở dạng rõ trong cache, được bọc dưới một KEK khác hoặc được lưu trong bản sao lưu có thể khôi phục, hủy KEK **chưa đủ** để kết luận dữ liệu không thể giải mã.

Điều kiện để coi crypto-shredding có hiệu quả gồm: thuật toán mã hóa đủ mạnh, tất cả khóa giải mã thực tế đã bị hủy, không còn đường khôi phục ngoài ý muốn, và không còn bản rõ cần xóa ở những kho khác. Việc hủy khóa **không xóa bit của bản mã** khỏi ổ đĩa; nó làm mất khả năng giải mã bản mã theo mô hình đe dọa đã xác định.

## 4. Các phương thức hủy và giới hạn

| Nơi giữ khóa | Phương án thường gặp | Điều phải xác minh |
| --- | --- | --- |
| **KMS quản lý** | Vô hiệu hóa, lên lịch xóa/hủy khóa, chờ giai đoạn an toàn rồi xác nhận hủy. | Ý nghĩa trạng thái xóa của nhà cung cấp, thời gian chờ, bản sao vùng khác, khóa do khách hàng nhập, nhật ký và quyền khôi phục trong giai đoạn chờ. |
| **HSM** | Gửi lệnh hủy đối tượng khóa trong phạm vi thiết bị/cluster; quy trình có thể bao gồm zeroization theo thiết kế phần cứng. | Bản sao trong cụm HSM, backup HSM, trạng thái key handle và bằng chứng hủy của nhà cung cấp. |
| **Kho lưu trữ phần mềm** | Xóa an toàn thông qua cơ chế quản lý bí mật, thu hồi quyền và xóa các bản sao liên quan. | Bản sao lưu, snapshots, dump, swap, cache, tệp tạm và các bản sao ngoài kho chính. |
| **Thiết bị/phương tiện lưu trữ** | Sanitization hoặc hủy phương tiện theo yêu cầu áp dụng. | Loại ổ đĩa, tính năng firmware, vùng lưu phụ và quy trình xác minh phù hợp. |

**Lưu ý về xóa bộ nhớ:** ghi đè một biến chứa khóa trong ứng dụng không bảo đảm loại bỏ toàn bộ bản sao do runtime, garbage collector, serialization hoặc hệ điều hành tạo ra. Với yêu cầu cao, ưu tiên hạn chế đưa vật liệu khóa vào bộ nhớ ứng dụng và dùng KMS/HSM có chính sách khóa không được xuất (non-exportable), trong khả năng dịch vụ hỗ trợ.

**Lưu ý về nhà cung cấp:** thao tác “schedule deletion”, “destroy key version”, “disable” hay “purge” có ngữ nghĩa khác nhau tùy nền tảng. Một hệ thống có thể trì hoãn xóa, hỗ trợ hủy lịch trong giai đoạn chờ, có replica hoặc cơ chế riêng cho khóa bên ngoài. Chỉ đánh dấu **DESTROYED** sau khi đã kiểm tra quy trình, bằng chứng và phạm vi bảo đảm thực tế.

## 5. Quy trình hủy khóa có kiểm soát

Việc hủy khóa nên được mô hình hóa như một quy trình nghiệp vụ có phê duyệt, triển khai, kiểm tra và ghi nhận kết quả.

~~~mermaid
flowchart TD
    A["Đề xuất hủy key ID / phiên bản"] --> B["Kiểm kê tất cả dữ liệu và workload phụ thuộc"]
    B --> C{"Còn nhu cầu hợp lệ để dùng khóa?"}
    C -->|Có| D["Giữ trong trạng thái kiểm soát hoặc di chuyển dữ liệu/khóa"]
    D --> B
    C -->|Không| E["Kiểm tra chính sách lưu giữ, legal hold và khôi phục"]
    E --> F{"Đủ điều kiện và phê duyệt?"}
    F -->|Không| H["Dừng quy trình và lưu lý do"]
    F -->|Có| G["Ngừng tạo dữ liệu mới bằng khóa; khóa quyền sử dụng"]
    G --> I["Hủy trên KMS/HSM và xử lý replica/backup theo chính sách"]
    I --> J["Xác minh trạng thái và bằng chứng hủy"]
    J --> K{"Đạt tiêu chí hoàn tất?"}
    K -->|Không| L["Ghi tồn đọng, điều tra và xử lý tiếp"]
    L --> J
    K -->|Có| M["Đánh dấu DESTROYED và lưu chứng cứ kiểm toán"]
~~~

Các bước cần thực hiện:

1. **Định danh khóa:** ghi rõ key ID, phiên bản, thuật toán, usage (encrypt/decrypt/sign/verify/derive), chủ sở hữu, môi trường, tenant, vị trí và trạng thái.
2. **Phân tích phụ thuộc:** xác định dữ liệu nào được mã hóa trực tiếp/bọc khóa bằng khóa đó; ứng dụng nào vẫn dùng; bản sao nào có thể phục hồi; các khóa được liên kết qua rewrap, replica và backup. Đảm bảo không còn tác vụ bất đồng bộ hay tiến trình cũ sử dụng khóa.
3. **Xác nhận điều kiện hủy:** kiểm tra hạn lưu giữ dữ liệu, yêu cầu pháp lý/điều tra, hợp đồng, khả năng phục hồi, bản sao dự phòng, và thời điểm ngắt quyền sử dụng.
4. **Phê duyệt và phân tách trách nhiệm:** áp dụng nguyên tắc **least privilege**; người yêu cầu, người phê duyệt và người thực hiện có thể là các vai trò riêng theo mức độ rủi ro. Với khóa quan trọng, yêu cầu hai người kiểm tra khi chính sách quy định.
5. **Chặn việc sử dụng mới:** ngừng ghi bản mã/chữ ký mới bằng khóa cũ, cập nhật key alias, cấu hình ứng dụng, cache và quyền gọi API. Nếu có sự cố lộ khóa, ưu tiên cô lập/vô hiệu hóa ngay.
6. **Thực hiện thao tác hủy:** theo API/chế độ KMS/HSM hoặc quy trình xử lý vật liệu khóa; kiểm tra cả bản sao, vùng dự phòng, khóa nhập, khóa xuất và các nhánh khôi phục đang thuộc phạm vi hủy. Với bản sao lưu bất biến, cần chính sách quản lý vòng đời và hạn lưu giữ rõ ràng, ghi nhận rủi ro tồn dư trong thời gian chờ.
7. **Xác minh và đóng hồ sơ:** xác nhận trạng thái cuối cùng bằng nguồn tin cậy, kiểm tra khả năng sử dụng theo phương pháp an toàn phù hợp, đối chiếu kiểm kê bản sao và lưu bằng chứng hoàn tất. Không “thử giải mã” bằng cách khôi phục khóa đã được hủy; có thể kiểm tra điều kiện tiên quyết bằng môi trường thử nghiệm trước thao tác thật.

Một quy trình có thể kết thúc ở trạng thái **PENDING_DELETION** hoặc **PARTIALLY_DESTROYED**, không được tự báo hoàn tất nếu vẫn còn bản sao có thể dùng. Thời hạn chờ, bản sao lưu và điều kiện kiểm soát thực tế quyết định thời điểm ghi nhận hoàn tất.

## 6. Ví dụ thiết kế: xóa dữ liệu của một tenant

Giả sử hệ thống SaaS có ba tenant A, B, C. Mỗi tenant có **DEK riêng**; các DEK được bọc dưới KEK do KMS quản lý. Tenant B yêu cầu xóa toàn bộ dữ liệu trong phạm vi có thể xóa.

**Thiết kế khóa:**

| Thành phần | Cách dùng |
| --- | --- |
| **DEK-A** | Mã hóa dữ liệu tenant A. |
| **DEK-B** | Mã hóa dữ liệu tenant B. |
| **DEK-C** | Mã hóa dữ liệu tenant C. |
| **KEK-1** | Bọc DEK-A, DEK-B, DEK-C; chỉ có hệ thống được cấp quyền mới được giải bọc. |

Nếu hủy **KEK-1** để xóa B thì có thể làm A và C không giải mã được dữ liệu. Nếu chỉ xóa tệp chứa **DEK-B đã bọc**, nhưng trong backup hoặc bộ nhớ của dịch vụ vẫn còn bản sao có thể dùng của DEK-B, việc xóa bằng mật mã chưa hoàn tất.

Một quy trình phù hợp cần: ngừng phát sinh dữ liệu B; kiểm kê tất cả bản mã, DEK-B ở mọi hình thức và các bản sao có khả năng khôi phục; hủy quyền sử dụng và mọi đường khôi phục DEK-B theo chính sách; xóa dữ liệu rõ/bản mã và bản sao lưu theo phạm vi được phép; xác minh không có tác động đến A/C; lưu bằng chứng. Nếu hệ thống cần xóa độc lập theo tenant, nên thiết kế **ranh giới khóa tương ứng với ranh giới xóa**, chẳng hạn mỗi tenant có KEK riêng hoặc cơ chế quản lý DEK độc lập với đường khôi phục được kiểm soát.

**Quan hệ với retention:** Nếu bản sao lưu bất biến chưa hết thời hạn lưu giữ, hệ thống cần chính sách rõ về việc cô lập, khóa quyền khôi phục, quản lý ngày hết hạn và ghi nhận rằng quá trình xóa có thể chưa hoàn thành trên tất cả phương tiện. Không tuyên bố xóa vĩnh viễn chỉ dựa vào việc xóa dữ liệu tại cơ sở dữ liệu hoạt động.

## 7. Ví dụ quy tắc vận hành dạng giả mã

Giả mã minh họa cho một dịch vụ điều phối hủy khóa, **không phải API của một KMS cụ thể**:

~~~text
function requestKeyDestruction(keyId, expectedVersion, requester):
    assert requester.hasPermission("request-key-destruction")
    key = keyInventory.load(keyId, expectedVersion)
    assert key is not null

    dependencies = dependencyCatalog.findActiveUsersAndCiphertexts(key)
    if dependencies.notEmpty():
        return BLOCKED("Key still required by active data or workloads")

    if retentionPolicy.requiresKey(key) or legalHold.applies(key):
        return BLOCKED("Retention or legal hold")

    approval = approvalWorkflow.request(key, requester)
    if not approval.isGranted():
        return PENDING_APPROVAL

    disableNewUses(key)
    deletionOperation = keyProvider.scheduleDestruction(key)

    audit.log({
        keyId: key.id,
        version: key.version,
        action: "DESTRUCTION_REQUESTED",
        operationId: deletionOperation.id,
        actor: requester.id,
        approvalId: approval.id
    })

    return PENDING_DELETION

function reconcileDestruction(keyId, version):
    evidence = keyProvider.getVerifiedDestructionEvidence(keyId, version)
    replicas = replicaInventory.checkRelevantCopies(keyId, version)

    if evidence.confirmed and replicas.allResolved:
        keyInventory.markDestroyed(keyId, version)
        audit.log({keyId: keyId, version: version, action: "DESTROYED"})
        return DESTROYED

    return PENDING_VERIFICATION
~~~

Giả mã thể hiện điểm quan trọng: **yêu cầu hủy** và **hủy đã xác minh** là hai sự kiện khác nhau. Hệ thống cần xử lý lỗi, chậm đồng bộ, tác vụ lặp và quyền truy cập thay đổi giữa các bước. Trong triển khai thật, chính sách hủy và bằng chứng của nhà cung cấp là nguồn quyết định trạng thái.

## 8. Kiểm toán: cần chứng minh điều gì?

Một hồ sơ key destruction hữu ích cần có:

- **Nhận dạng:** key ID, phiên bản, nguồn sinh khóa, loại khóa, usage, môi trường, phạm vi tenant và owner.
- **Lý do và căn cứ:** hết hạn, kết thúc dịch vụ, đáp ứng yêu cầu xóa, sự cố bảo mật, mã yêu cầu/ticket, kiểm tra retention/legal hold.
- **Kiểm tra tác động:** danh mục dữ liệu/bản mã, ứng dụng, khóa bọc, bản sao vùng khác, bản sao lưu, mục tiêu khôi phục.
- **Phê duyệt:** người yêu cầu, người duyệt, quyền hạn, thời điểm và tài liệu chính sách áp dụng.
- **Thao tác và trạng thái:** vô hiệu hóa, lên lịch xóa, hủy bản sao, thời điểm hoàn tất, mã giao dịch/trạng thái API.
- **Bằng chứng xác minh:** log/audit trail từ KMS/HSM, kết quả đối soát replica, xác nhận danh sách công việc tồn đọng đã khép lại; ngoại lệ và chủ thể chấp nhận rủi ro nếu có.

**Không ghi vật liệu khóa bí mật, DEK dạng rõ hoặc bản dump private key** vào nhật ký kiểm toán. Nhật ký nên được bảo vệ chống sửa đổi, có kiểm soát truy cập và thời hạn lưu giữ theo chính sách. Quyền thực hiện hủy cần tách khỏi quyền xem/sửa hồ sơ kiểm toán nếu phù hợp mô hình phân quyền.

## 9. Các lỗi thường gặp

| Sai lầm | Hậu quả | Biện pháp |
| --- | --- | --- |
| Hủy khóa ngay sau rotate | Không thể giải mã bản mã hoặc khôi phục backup cũ. | Xác minh phụ thuộc, di chuyển dữ liệu và cửa sổ hỗ trợ trước khi hủy. |
| Gỡ key alias rồi tuyên bố đã xóa | Key material vẫn có thể tồn tại dưới key ID khác hoặc trong backup. | Xác minh đúng đối tượng, phiên bản và tất cả bản sao thực tế. |
| Hủy KEK dùng chung cho nhiều tenant | Xóa ngoài ý muốn dữ liệu tenant khác. | Thiết kế ranh giới khóa theo phạm vi dữ liệu cần xóa; phân tích blast radius. |
| Chỉ xóa bản mã mà giữ nguyên khóa | Dữ liệu từ snapshots/bản sao khác còn có thể giải mã. | Kết hợp data deletion với quản lý khóa và đường phục hồi. |
| Chỉ hủy khóa hiện hành, bỏ qua backup/replica | Khóa vẫn có thể phục hồi từ nguồn khác. | Kiểm kê toàn bộ bản sao và nêu rõ ngoại lệ có kiểm soát. |
| Đánh dấu DESTROYED ngay khi gọi API xóa | Nhà cung cấp vẫn đang trong thời gian chờ, có thể khôi phục. | Theo dõi trạng thái cuối cùng và xác minh bằng chứng hủy. |
| Không giữ thông tin public key/chứng chỉ cần cho chữ ký cũ | Khó xác minh tài liệu, log hoặc giao dịch lịch sử. | Phân biệt private key bí mật với thông tin xác minh công khai và yêu cầu lưu giữ. |
| Không giới hạn quyền hủy khóa | Người có quyền quá rộng có thể gây mất dữ liệu hàng loạt. | Phân quyền tối thiểu, phê duyệt, separation of duties, cảnh báo thao tác nhạy cảm. |
| Không có kế hoạch xử lý khóa bị lộ | Kẻ tấn công tiếp tục dùng khóa khi chờ hủy. | Ngừng sử dụng/thu hồi theo quy trình ứng phó ngay, sau đó hoàn thiện hủy có kiểm chứng. |

## 10. Câu hỏi tự kiểm tra

1. Khóa đang ở trạng thái **DISABLED** có được xem là **DESTROYED** chưa? Vì sao?
2. Khi hủy một private key để ký số, các chữ ký đã phát hành trước đó có tự mất hiệu lực không?
3. Một KEK bọc DEK cho 100 tenant. Hủy KEK để đáp ứng yêu cầu xóa của một tenant có thể gây tác động gì?
4. Nếu KMS báo đã lên lịch hủy nhưng backup HSM vẫn chứa khóa, đội vận hành có thể khẳng định hủy hoàn tất không?
5. Những thông tin nào cần nằm trong hồ sơ kiểm toán để chứng minh khóa đã bị hủy theo đúng chính sách?

**Ghi nhớ:** Hủy khóa là quyết định có thể không đảo ngược. Trước khi hủy cần xác định **ai có quyền hủy, dữ liệu nào phụ thuộc, vật liệu khóa còn ở đâu, khi nào hết nhu cầu sử dụng, chứng cứ nào chứng minh đã hủy**. Chỉ khi kiểm soát được các câu hỏi này, key destruction mới góp phần bảo đảm tính bí mật mà không phá vỡ tính sẵn sàng và khả năng kiểm toán của hệ thống.
