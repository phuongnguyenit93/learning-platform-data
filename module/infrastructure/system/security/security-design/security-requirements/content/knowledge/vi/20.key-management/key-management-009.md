# Key recovery

## 1. Phục hồi khóa phải khôi phục cả khả năng sử dụng lẫn ranh giới bảo mật

Một bản backup dữ liệu có thể còn nguyên nhưng không mở được nếu khóa hoặc quyền sử dụng khóa đã mất. Ngược lại, một thao tác phục hồi vội vàng có thể làm dữ liệu đọc lại được bằng cách đưa khóa rõ cho quá nhiều người hoặc khôi phục những quyền trước đó đã bị thu hồi.

**Key recovery** là quy trình khôi phục khả năng sử dụng khóa theo chính sách đã xác định sau một sự kiện làm mất quyền truy cập, hỏng môi trường, mất vật liệu hoặc gián đoạn cơ chế quản lý khóa.

Mục tiêu không nhất thiết là lấy được một file raw key. Với khóa được giữ trong một module hoặc dịch vụ mật mã, kết quả phù hợp có thể là khôi phục operation được phép mà không xuất vật liệu khóa ra ngoài.

Trong thiết kế yêu cầu bảo mật, cần trả lời:

1. Sự kiện nào cần phục hồi và sự kiện nào phải xử lý như compromise?
2. Loại khóa nào cần có khả năng phục hồi, loại nào không được lưu lại trái mục tiêu vòng đời?
3. Những bản dữ liệu nào phụ thuộc khóa và phiên bản nào?
4. Cơ chế backup, trạng thái phục hồi của nền tảng và các điều kiện giới hạn là gì?
5. Ai được kích hoạt, thực hiện, xác nhận và đóng quy trình?
6. Bằng chứng nào xác nhận dịch vụ đã hoạt động đúng trong phạm vi quyền được phép?

Yêu cầu tốt phải giữ đồng thời tính khả dụng, bí mật và toàn vẹn. “Đã thấy key trong giao diện” chưa chứng minh hoàn thành key recovery.

## 2. Phân loại sự cố trước khi chọn hành động

Không phải mọi lỗi Decrypt, Sign hoặc mở keystore đều là mất vật liệu khóa.

| Tình huống | Bản chất cần xác minh | Hướng xử lý có thể phù hợp |
| --- | --- | --- |
| Credential của workload hết hiệu lực | Mất khả năng xác thực với dịch vụ khóa | Khôi phục danh tính/quyền theo phạm vi được cấp |
| Policy hoặc role bị sửa sai | Vật liệu có thể vẫn còn, nhưng operation bị chặn | Đối chiếu thay đổi và khôi phục policy đúng |
| Alias trỏ sai hoặc mất mapping | Chọn sai đối tượng/phiên bản | Phục hồi metadata có thẩm quyền |
| Khóa bị disable hoặc tạm đình chỉ | Một trạng thái vòng đời có thể có chủ đích | Xác minh lý do trước khi xem xét khả năng sử dụng lại |
| Kho hoặc HSM không khả dụng | Hỏng dịch vụ hoặc hạ tầng truy cập | Failover hoặc phục hồi môi trường theo cơ chế hỗ trợ |
| Keystore hoặc vật mang dữ liệu bị hỏng | Mất một bản lưu vật liệu | Restore từ bản bảo vệ phù hợp và đã kiểm tra |
| Đối tượng đang trong cửa sổ có thể phục hồi | Có trạng thái xóa/hủy chưa hoàn tất theo nền tảng | Dùng đúng operation và điều kiện hiện hành |
| Vật liệu bị hủy vĩnh viễn, không còn nguồn hợp lệ | Không còn điều kiện mật mã để mở dữ liệu | Xác định mất khả năng phục hồi, không tạo lời hứa sai |
| Khóa bị lộ hoặc bị sử dụng trái phép | Có thể đã mất thuộc tính bảo mật | Cô lập, đánh giá ảnh hưởng và thay khóa theo kế hoạch sự cố |

Một quy trình tự động bật lại mọi khóa đang bị disable có thể đảo ngược một quyết định bảo mật hợp lệ. Một quy trình tự tạo khóa mới với cùng alias cũng không tạo lại vật liệu đã mã hóa dữ liệu trước đó.

Vì vậy, bước phân loại cần có bằng chứng về trạng thái, lịch sử thay đổi và phụ thuộc nghiệp vụ trước khi thực hiện thao tác phục hồi.

## 3. Khả năng phục hồi phải theo mục đích của khóa

Không nên đặt một chính sách duy nhất “backup và phục hồi mọi private key” cho toàn hệ thống.

| Loại hoặc mục đích | Nhu cầu thường phải đánh giá | Rủi ro khi chọn chính sách sai |
| --- | --- | --- |
| Khóa giải mã dữ liệu còn retention | Giữ khả năng mở những bản dữ liệu cần đọc | Mất dữ liệu dù backup ciphertext vẫn còn |
| KEK bảo vệ DEK | Khôi phục khả năng tháo bọc cho đúng tập wrapped key | Không mở được nhiều nhóm dữ liệu phụ thuộc |
| Khóa ký dữ liệu mới | Khôi phục dịch vụ theo chính sách ký và trạng thái tin cậy | Kích hoạt lại khóa đáng lẽ đã ngừng hoặc bị compromise |
| Public key/certificate để verify lịch sử | Giữ nguồn tin cậy và metadata kiểm tra phù hợp | Không kiểm tra được hoặc chấp nhận sai chữ ký cũ |
| Khóa riêng TLS | Duy trì hoặc tái thiết lập danh tính dịch vụ theo thiết kế | Khôi phục nhầm danh tính hoặc tạo thêm bản sao không kiểm soát |
| Khóa tạm thời của giao thức | Có thể chủ đích không lưu để phục hồi về sau | Vô tình phá mục tiêu giới hạn dữ liệu lịch sử bị ảnh hưởng |
| Khóa từ mật khẩu người dùng | Cần mật khẩu hoặc một cơ chế phục hồi đã được thiết kế | Hứa reset dữ liệu mà thực tế không có đủ bí mật |

[OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html) phân biệt nhu cầu backup/escrow của khóa phục vụ bí mật dữ liệu với các rủi ro của khóa ký, đồng thời yêu cầu có kế hoạch xử lý compromise. Khi áp dụng, phải xuất phát từ mục đích của từng loại khóa.

Chỉ để kiểm tra một chữ ký cũ không tự cần khôi phục private key ký. Ngược lại, có public key của một cặp mã hóa bất đối xứng không thay được private key cần để giải mã.

## 4. Recovery profile cho một nhóm khóa

Một recovery profile nên mô tả mục tiêu và các điều kiện, không chứa vật liệu thật.

```yaml
logicalKeyGroup: document-wrapping-keys
purpose: recover-read-access-to-retained-documents
owner: document-platform-team
recoveryScope:
  - required-key-versions
  - protected-backup-artifacts
  - resource-mapping
  - runtime-access-policy
targetRtoMinutes: 60
targetDataRpoMinutes: 15
keyDependencyRequirement: all-accepted-retained-ciphertexts
targetEnvironment: isolated-recovery-environment
completion: authorized-application-read-and-negative-access-checks-pass
```

Đây là một ví dụ đặc tả, không phải schema của một nền tảng hay file cần tạo trong dự án. Các mục tiêu 60 phút và 15 phút chỉ minh họa một quyết định sản phẩm/hạ tầng.

Profile cần làm rõ:

- Sự cố nào thuộc phạm vi và sự cố nào có quy trình khác.
- Tập dữ liệu/phiên bản phải đọc lại được.
- Nguồn phục hồi và các phụ thuộc đủ để sử dụng nguồn đó.
- Quyền cần có và nơi được phép dựng môi trường đích.
- Điều kiện xác nhận đúng khóa, đúng policy và đúng hoạt động nghiệp vụ.
- Cách ghi nhận kết quả không đầy đủ hoặc không thể phục hồi.

Không dùng một trường `backupEnabled: true` làm bằng chứng rằng profile này đã được đáp ứng.

## 5. Phục hồi một đồ thị phụ thuộc, không chỉ một object khóa

Với một hệ thống envelope encryption, một đường đọc có thể cần:

```text
Dữ liệu mã hóa + định dạng và metadata
    → wrapped DEK đúng tài nguyên
    → KEK/phiên bản hoặc khả năng sử dụng tương ứng
    → môi trường mật mã hỗ trợ định dạng
    → danh tính được phép gọi operation
    → policy và context có thẩm quyền
    → ứng dụng xác minh rồi đọc dữ liệu theo quyền nghiệp vụ
```

Những thành phần ngoài vật liệu mật mã có thể gồm:

- Key reference, version ID, alias và mapping tài nguyên.
- Thuật toán, phiên bản định dạng và quy tắc encoding/context.
- Provider, module hoặc security domain mà bản backup yêu cầu.
- Credential bootstrap và cơ chế xác thực quản trị/workload.
- Role, policy, network route, endpoint và trust configuration.
- Nguồn dữ liệu hiện hành về thu hồi, ngừng dùng hoặc hạn chế operation.
- Chủ sở hữu và người giữ những thành phần phục hồi.

Một bản backup raw database không nhất thiết mang theo tất cả những phụ thuộc này. Một bản backup kho khóa cũng không nhất thiết bao gồm toàn bộ cấu hình quyền ở tầng ứng dụng.

### Tránh vòng phụ thuộc phục hồi

Không đặt credential duy nhất mở kho backup vào chính kho mà tình huống sự cố giả định đã không truy cập được. Không đặt mọi bản security domain, credential và tài liệu vận hành trên cùng một môi trường có thể mất cùng lúc.

Mục tiêu của việc tách không chỉ là vị trí địa lý. Cần xét quyền quản trị, tài khoản, cơ chế xóa và những danh tính có thể tác động đồng thời nhiều bản.

## 6. Backup dữ liệu và backup khóa phải tương thích theo thời điểm

Ví dụ một hệ thống keystore tự quản lý có timeline:

| Thời điểm | Sự kiện |
| --- | --- |
| 09:00 | Backup keystore, lúc này có phiên bản khóa K1 |
| 09:10 | Tạo K2 và bắt đầu bảo vệ dữ liệu mới bằng K2 |
| 09:20 | Backup dữ liệu, bao gồm các bản ghi cần K2 |
| 09:30 | Mất môi trường giữ keystore hiện hành; chỉ còn bản backup khóa lúc 09:00 |

Nếu không còn một nguồn hợp lệ nào giữ K2, bản dữ liệu lúc 09:20 không thể được đọc đầy đủ chỉ bằng K1. Việc backup dữ liệu thành công không tự khắc phục khoảng trống khóa.

Từ tình huống này, dự án có thể đặt một gate:

> Trước khi dùng một phiên bản khóa để chấp nhận dữ liệu bền vững, hệ thống phải đáp ứng điều kiện recoverability đã xác định cho phiên bản đó và những phụ thuộc cần thiết.

Với một dịch vụ khóa quản lý, gate có thể dựa vào thuộc tính durability, replication hoặc cơ chế backup được sản phẩm hỗ trợ. Với keystore tự quản lý, nó có thể cần một bản bảo vệ đã được xác nhận. Không ép mọi nền tảng phải dùng cùng một thao tác sao chép thủ công.

Yêu cầu quan trọng là không có dữ liệu đã chấp nhận nằm ngoài khả năng phục hồi mà sản phẩm đã cam kết, trừ ngoại lệ được ghi nhận rõ theo chính sách.

## 7. RTO và RPO phải đo tới khả năng sử dụng nghiệp vụ

**Recovery Time Objective (RTO)** xác định thời gian mục tiêu để phục hồi khả năng cần thiết sau sự cố theo phạm vi đã chọn. **Recovery Point Objective (RPO)** xác định mức mất dữ liệu theo thời điểm mà hệ thống chấp nhận được trong kế hoạch phục hồi.

Với key recovery, cần tránh hai cách đo thiếu:

- Dừng đồng hồ ngay khi API restore trả một job ID.
- Cho rằng backup khóa còn trong RPO thời gian là đủ dù thiếu một phiên bản cần cho ciphertext được giữ.

Một mốc hoàn tất của dự án có thể cần ứng dụng được phép đọc một tập dữ liệu, principal không có quyền bị từ chối và policy hiện hành được giữ đúng.

### Phân rã thời gian để đánh giá tính khả thi

Một ngân sách giả định cho RTO 60 phút có thể phân bổ:

| Công đoạn | Ngân sách minh họa |
| --- | --- |
| Phát hiện và phân loại | 10 phút |
| Kích hoạt quyền/quy trình phục hồi | 10 phút |
| Chuẩn bị môi trường và kiểm tra nguồn | 15 phút |
| Thực hiện restore hoặc khôi phục operation | 15 phút |
| Kiểm chứng và chuyển trạng thái dịch vụ | 10 phút |

Các con số chỉ là ví dụ lập kế hoạch. Diễn tập phải đo được thời gian thực tế, bao gồm những phụ thuộc như người giữ recovery material không trực hoặc quyền mạng chưa sẵn sàng.

RPO của dữ liệu và điều kiện bao phủ khóa có quan hệ nhưng không giống nhau. Mất một phiên bản khóa nhỏ về kích thước có thể khiến mất khả năng đọc một tập dữ liệu rất lớn.

## 8. Cơ chế nền tảng không thể được suy đoán từ tên “recover”

Các dịch vụ dùng những trạng thái và operation khác nhau. Runbook phải dựa vào đúng sản phẩm, loại khóa, nguồn vật liệu và trạng thái hiện tại.

### Trạng thái có cửa sổ phục hồi

[Azure Key Vault soft-delete](https://learn.microsoft.com/en-us/azure/key-vault/general/soft-delete-overview) cho phép phục hồi những đối tượng còn trong thời gian giữ theo cấu hình. Tài liệu cũng nêu rằng phục hồi một vault không tự phục hồi mọi tích hợp như role assignment hoặc subscription liên quan. Vì vậy, tìm lại được vault chưa chứng minh workload đã có quyền dùng khóa đúng.

[Google Cloud KMS](https://cloud.google.com/kms/docs/destroy-restore) phân biệt key version đang chờ hủy với vật liệu đã bị hủy. Việc hủy lịch trong cửa sổ được hỗ trợ khác với tạo lại vật liệu sau khi đã hủy; key ID hoặc version number còn tồn tại không tự đồng nghĩa material còn dùng được. Trường hợp re-import vật liệu đã nhập có điều kiện riêng và cần đúng vật liệu gốc.

### Giới hạn khi vật liệu đã mất

[AWS KMS về xóa khóa](https://docs.aws.amazon.com/kms/latest/developerguide/deleting-keys.html) phân biệt hủy lịch xóa trước khi hoàn tất với khóa đã xóa. Những trường hợp replica hoặc imported material phải được xét theo điều kiện riêng của dịch vụ; không được mặc định có một nút khôi phục chung cho mọi khóa đã bị xóa vĩnh viễn.

Từ đó, yêu cầu của dự án nên có bảng trạng thái thực tế và thời hạn phản ứng. Không sao chép một con số thời gian giữ của nhà cung cấp thành giả định cho mọi môi trường; cần đọc cấu hình có hiệu lực của tài nguyên thuộc phạm vi.

### Có tên khóa không phải có khóa cũ

Tạo một khóa ngẫu nhiên mới rồi dùng lại tên hoặc alias không làm nó giải mã được ciphertext cũ. Mục tiêu phục hồi phải xác định vật liệu hoặc khả năng mật mã tương ứng, không chỉ sự tồn tại của một tên logic.

Nếu không còn nguồn phục hồi được phép và đủ điều kiện, phải ghi nhận trung thực dữ liệu không thể mở. Không đánh dấu thành công bằng việc thay dữ liệu rỗng hoặc bỏ qua bản ghi lỗi.

## 9. Backup được bảo vệ, HSM và security domain

Một khóa không cho ứng dụng xuất raw material vẫn có thể có cơ chế phục hồi được nền tảng hỗ trợ. Điều này không cho phép tự tạo một đường xuất rõ để thay thế cơ chế đó.

Ví dụ, [Azure Managed HSM backup/restore](https://learn.microsoft.com/en-us/azure/key-vault/managed-hsm/backup-restore) mô tả bản backup được bảo vệ gắn với security domain. Tài liệu cũng chỉ rõ full restore có thể thay thế nội dung hiện hành và yêu cầu môi trường nguồn/đích phù hợp. Đây là điều kiện của sản phẩm cụ thể, không phải thuộc tính chung của mọi HSM.

Một profile backup của dự án nên xác định:

- Loại backup: toàn kho, từng khóa, từng phiên bản hay một cơ chế bảo vệ khác.
- Những metadata và quyền nào thực sự được backup.
- Môi trường nào có thể nhận bản backup đó.
- Cơ chế xác minh nguồn gốc, tính toàn vẹn và tính đầy đủ.
- Nơi giữ vật liệu mở backup và những người có quyền sử dụng.
- Hành vi khi restore vào một nơi đã có dữ liệu hoặc key mới hơn.

Không kết luận “backup an toàn” chỉ vì file có phần mở rộng riêng hoặc trông như dữ liệu ngẫu nhiên. Cần xác nhận cơ chế, quyền và phụ thuộc.

### Không bỏ sót vật liệu bảo vệ bản backup

Nếu backup được bảo vệ bằng một miền mật mã riêng, miền đó là phụ thuộc cấp cao. Một blob backup còn nguyên có thể không đủ nếu thiếu vật liệu mở hoặc môi trường tương thích.

Mục tiêu là duy trì khả năng phục hồi mà không làm xuất hiện một bản raw key trên máy cá nhân, kênh hỗ trợ hoặc nơi lưu tạm ngoài inventory.

## 10. Quorum, dual control và người giữ vật liệu

Các cơ chế nhiều bên có thể giúp giảm quyền tập trung, nhưng phải phân biệt:

- **Dual control:** một hành động cần nhiều chủ thể tham gia hoặc phê duyệt theo quy trình/quyền hệ thống.
- **Threshold recovery:** cơ chế mật mã yêu cầu đủ số thành phần hợp lệ để khôi phục một khả năng.
- **Tách trách nhiệm:** người phê duyệt, người vận hành và người kiểm chứng không có quyền mặc định giống nhau.

Một sản phẩm có thể kết hợp các cơ chế này. Ví dụ, [security domain của Azure Managed HSM](https://learn.microsoft.com/en-us/azure/key-vault/managed-hsm/security-domain) có cơ chế quorum cho vật liệu phục hồi và yêu cầu bảo vệ những khóa liên quan. Việc mất đủ phụ thuộc có thể làm mất khả năng disaster recovery, còn có đủ vật liệu có thể tạo quyền rất rộng.

Trong một thiết kế giả định 2-trong-3, không nên để cả ba thành phần nằm trên cùng tài khoản hoặc cùng một thiết bị mà một người có thể lấy hết. Cũng cần đánh giá trường hợp một hoặc nhiều người giữ vắng mặt, rời tổ chức hoặc mất vật mang dữ liệu.

Không tự cắt một chuỗi key thành ba đoạn rồi gọi đó là secret sharing. Nếu cần threshold scheme, phải dùng cơ chế được chọn và kiểm chứng theo nền tảng hoặc thư viện phù hợp.

### Quy trình con người phải tồn tại được khi hệ thống chính lỗi

Danh sách người giữ, thông tin liên hệ và cách xác minh họ cần được cập nhật. Nhưng không ghi giá trị recovery secret hoặc nội dung share trong ticket, lịch làm việc hay tài liệu liên hệ.

Một quy trình có ba chữ ký trong ticket nhưng một tài khoản kỹ thuật vẫn có thể tự phục hồi toàn bộ chưa chắc đạt mục tiêu nhiều bên. Bằng chứng phải xét đường thực thi thực sự, không chỉ mẫu biểu.

## 11. Quyền phục hồi và break-glass

Quyền phục hồi có thể rộng hơn quyền vận hành bình thường. Nó cần được giới hạn theo vụ việc, tài nguyên, operation, thời gian và môi trường.

Một ma trận trách nhiệm minh họa:

| Vai trò | Trách nhiệm | Không tự suy ra quyền |
| --- | --- | --- |
| Chủ sở hữu dữ liệu/dịch vụ | Xác định tập dữ liệu và mục tiêu cần phục hồi | Đọc raw key hoặc tự sửa mọi policy |
| Người phê duyệt sự kiện | Xác nhận phạm vi và điều kiện kích hoạt | Giữ mọi recovery secret |
| Người thực hiện | Dùng cơ chế phục hồi theo kế hoạch | Công khai hoặc xuất vật liệu tùy ý |
| Người giữ thành phần phục hồi | Thực hiện phần tham gia được giao | Tự mở rộng tài nguyên đích |
| Người kiểm chứng | Xác nhận quyền và kết quả nghiệp vụ | Mặc định đọc toàn bộ dữ liệu thật |
| Người đối chiếu audit | Kiểm tra dấu vết và việc đóng quyền | Duy trì quyền khẩn cấp vô thời hạn |

Break-glass không phải một mật khẩu quản trị dùng chung được ghi trong README. Nó cần có cách xác thực đủ mạnh theo rủi ro, nguồn truy cập được kiểm soát và dấu vết đối chiếu.

Sau khi hoàn thành hoặc hủy sự kiện, phải thu hồi quyền tạm, dọn session/capability liên quan theo khả năng nền tảng và xác nhận không còn một đường truy cập rộng hơn policy bình thường.

Nếu quy trình không thể audit trực tuyến vì kênh chính mất, cần có phương án ghi nhận được bảo vệ và đối chiếu về sau. “Không có audit nên tạm không ghi gì” không nên là hành vi mặc định của một operation nhạy cảm.

## 12. Runbook phải có các bước dừng an toàn

Một runbook có thể được phân rã như sau:

1. **Nhận diện sự cố:** xác định dịch vụ, tài nguyên, triệu chứng và phạm vi ảnh hưởng.
2. **Phân loại trạng thái:** phân biệt mất quyền, mất môi trường, trạng thái vòng đời và compromise.
3. **Xác nhận phạm vi được cấp:** chốt tập khóa, dữ liệu, đích và người tham gia.
4. **Kiểm tra khả năng phục hồi:** xác minh nguồn, phiên bản, tính toàn vẹn và phụ thuộc còn đủ.
5. **Chuẩn bị môi trường cách ly:** cấu hình danh tính, mạng, provider, trust và giới hạn output.
6. **Thực hiện operation được nền tảng hỗ trợ:** theo dõi trạng thái tới khi hoàn tất thực sự.
7. **Đối chiếu policy hiện hành:** không làm sống lại quyền hoặc khóa đã bị loại khỏi phạm vi sử dụng.
8. **Kiểm chứng chức năng và quyền âm:** dùng dữ liệu tổng hợp/được cấp trong phạm vi cần thiết.
9. **Khôi phục dịch vụ theo kế hoạch:** chuyển trạng thái hoạt động khi đủ gate, không chỉ khi object xuất hiện.
10. **Đóng sự kiện:** thu hồi quyền tạm, đối chiếu artifact và ghi nhận kết quả cùng giới hạn.

Từng bước cần có điều kiện dừng. Ví dụ, backup sai tenant, thiếu context bắt buộc hoặc đích restore có trạng thái chưa được kiểm kê phải được xem là vấn đề cần giải quyết, không bỏ qua để chạy tiếp.

Runbook cũng cần nêu các tác dụng của thao tác phục hồi. Một lệnh full restore có thể làm mất trạng thái hiện hành; phải biết đang khôi phục vào tài nguyên nào và có thể ảnh hưởng những khóa nào khác.

## 13. Giữ policy hiện hành khi phục hồi trạng thái lịch sử

Backup thường phản ánh một thời điểm trước sự cố. Từ thời điểm đó tới hiện tại, tổ chức có thể đã:

- Thu hồi một principal hoặc một quyền.
- Ngừng dùng một phiên bản khóa để ký/mã hóa mới.
- Đánh dấu khóa compromised.
- Chuyển ownership hoặc phạm vi tenant.
- Kết thúc retention của một nhóm dữ liệu.
- Xóa dữ liệu hoặc khóa theo một chính sách có chủ đích.

Phục hồi snapshot cũ không nên tự đảo ngược các quyết định đó.

Trong thiết kế dự án, cần có nguồn trạng thái hiện hành hoặc cơ chế đối chiếu phù hợp, được bảo vệ và có thể tiếp cận trong kịch bản sự cố. Sau restore, quyền ở control plane, data plane và ứng dụng cần được xác nhận theo trạng thái được phép hiện tại.

### Không làm sống lại dữ liệu đã bị loại bỏ có chủ đích

Nếu một mục tiêu vòng đời dựa vào việc loại bỏ khả năng giải mã, những bản backup còn có thể phục hồi material phải nằm trong phân tích đó. Ngược lại, quy trình recovery không nên âm thầm đưa khả năng giải mã đã bị loại bỏ trở lại hoạt động.

Điều này cần được giải quyết ở thiết kế retention, backup và sự kiện xóa; không thể xử lý chỉ bằng việc xóa một entry sau khi khôi phục xong toàn kho.

## 14. Mất khả dụng khác với lộ khóa

Khi một máy giữ keystore hỏng nhưng không có dấu hiệu lộ vật liệu, restore đúng bản bảo vệ có thể là một hướng phục hồi phù hợp. Khi private key đã bị sao chép hoặc quyền dùng khóa đã bị lạm dụng, phục hồi chính khóa đó không tự khôi phục tính bí mật hay sự tin cậy.

Một kế hoạch xử lý compromise có thể cần:

- Cô lập operation hoặc principal bị ảnh hưởng.
- Xác định dữ liệu, chữ ký, phiên bản và hệ thống phụ thuộc.
- Cấp vật liệu mới theo chính sách, thay mapping và phân phối trust mới khi cần.
- Rewrap hoặc mã hóa lại dữ liệu theo mục tiêu thực tế.
- Giữ một khả năng xử lý dữ liệu cũ trong vùng kiểm soát nếu được phép và cần thiết.
- Đối chiếu ảnh hưởng lịch sử và các nghĩa vụ vận hành liên quan.

Không tự bật lại một signing key đã bị đánh dấu compromised chỉ để dịch vụ hết lỗi. Việc tiếp tục verify dữ liệu lịch sử và việc cho phép ký dữ liệu mới là hai quyết định khác nhau.

Nếu cần dùng khóa cũ để chuyển dữ liệu, phạm vi operation và môi trường phải được xác định riêng; không biến một đường phục hồi hạn chế thành quyền production rộng như trước sự cố.

## 15. Kiểm chứng đúng khóa và đúng dịch vụ

Bằng chứng hoàn tất nên kết hợp nhiều mức:

| Mức | Điều cần xác nhận |
| --- | --- |
| Vật liệu/khả năng mật mã | Đối tượng được phục hồi tương ứng với phiên bản và mục đích cần thiết |
| Metadata | Mapping tài nguyên, version, context và định dạng phù hợp |
| Policy | Principal hợp lệ dùng được, principal ngoài phạm vi không dùng được |
| Ứng dụng | Một luồng cần khóa thực sự hoạt động theo hợp đồng |
| Dữ liệu | Những nhóm ciphertext thuộc yêu cầu có thể được mở đúng và kiểm tra toàn vẹn |
| Vận hành | Audit, quyền tạm, artifact và thời gian đạt mục tiêu đã được đối chiếu |

### Không in khóa ra để so sánh

Có thể dùng một tập ciphertext kiểm thử đã biết cùng ngữ cảnh và kết quả kỳ vọng, hoặc cơ chế xác nhận phù hợp nền tảng. Không cần công khai byte khóa để chứng minh chúng khớp.

Nếu cần một phép thử ký để xác nhận private key, thông điệp thử và giao thức phải được thiết kế để không trở thành một token, lệnh hoặc thông điệp nghiệp vụ có thể sử dụng thật. Việc verify chữ ký lịch sử không tự cần phục hồi private key.

Metadata hay fingerprint được phép ghi phải được chọn theo loại khóa và khả năng nền tảng. Không mặc định có thể xuất mọi symmetric key để tính một fingerprint riêng.

### Không chỉ thử đường thành công

Phải thử người không có quyền, tenant khác, operation bị cấm và policy đã bị thu hồi. Một môi trường restore mở dữ liệu thành công nhưng cấp Decrypt cho mọi workload không đạt mục tiêu bảo mật.

Nếu tập dữ liệu kiểm tra chỉ bao phủ một phiên bản mới, không được suy rằng mọi backup lịch sử đã được hỗ trợ. Phạm vi lấy mẫu và phần kiểm kê toàn bộ phụ thuộc phải được ghi rõ.

## 16. Môi trường diễn tập và tích hợp với ứng dụng

Diễn tập key recovery nên dùng tài nguyên thử, dữ liệu tổng hợp hoặc dữ liệu được cấp đúng phạm vi. Các thao tác có thể phá hủy hoặc ghi đè không nên được thực hiện trên khóa thật chỉ để có bằng chứng.

Môi trường cách ly cần kiểm soát:

- Danh tính và tài khoản đích.
- Kênh mạng tới dịch vụ khóa, storage và đối tác.
- Khả năng gửi email, webhook hoặc chạy job nghiệp vụ thật.
- Quyền dump/debug và nơi ghi log.
- Artifact được sinh ra và người có thể lấy chúng.
- Thời gian tồn tại cùng điều kiện cleanup.

Khôi phục một database có thể kích hoạt tác vụ nền nếu ứng dụng được khởi chạy nguyên cấu hình production. Vì vậy, khả năng đọc lại không được đánh đổi bằng việc gửi dữ liệu hoặc sự kiện thật tới một đích ngoài phạm vi thử.

### Ứng dụng không cần một API công khai “recover mọi khóa”

Một luồng điều phối logic có thể được mô tả:

```text
executeApprovedRecovery(caseRef, targetRef):
    case = resolveAuthorizedRecoveryCase(caseRef)
    target = resolveApprovedTarget(case, targetRef)

    incidentState = classifyFromTrustedEvidence(case)
    plan = selectSupportedRecoveryPlan(incidentState, case.keyProfile)
    verifyRecoveryDependencies(plan, case, target)
    verifyScopeAndRequiredParticipants(case, plan)

    result = performSupportedRecoveryOperation(plan, target)
    waitForActualCompletionAccordingToContract(result)

    reconcileWithCurrentKeyAndAccessPolicy(case, target)
    verifyCryptographicAndApplicationBehavior(case, target)
    recordEvidenceWithoutKeyMaterial(case, result)

    closeTemporaryAccessAndArtifactsAccordingToPlan(case)
```

Đây là mã giả về trách nhiệm, không phải một API vendor hoặc triển khai để tự động vượt mọi kiểm soát. `caseRef` và `targetRef` phải được giải quyết trong danh mục đã cấp quyền; chúng không phải đường dẫn hoặc URL tùy ý mà caller được phép phục hồi.

## 17. Hành vi khi phục hồi không hoàn tất

Một quy trình có thể thất bại vì thiếu dependency, bản backup sai hoặc hỏng, không đủ người tham gia, nền tảng không hỗ trợ trạng thái hiện tại hoặc thao tác chưa hoàn thành.

Kết quả phải mô tả được:

- Phần nào đã làm và trạng thái nào còn lại.
- Những tài nguyên nào đã thay đổi.
- Dữ liệu nào chưa thể đọc theo phạm vi yêu cầu.
- Quyền tạm hoặc artifact nào còn cần xử lý.
- Có thể tiếp tục, phải dựng lại đích hay không còn nguồn phục hồi.

Không đánh dấu hoàn tất vì một số bản ghi đọc được. Không chuyển sang plaintext, dùng một khóa cố định hoặc tạo khóa mới để che việc ciphertext cũ không mở được.

Nếu có lỗi giữa chừng, việc rollback cũng phải xét tác dụng cụ thể của operation và trạng thái hiện hành. Không mặc định mọi restore có thể đảo ngược bằng một lệnh chung.

Response hoặc báo cáo công khai không cần chứa key material, recovery share, PIN, credential quản trị hay nội dung dữ liệu thật. Kênh chẩn đoán cần reason code, định danh artifact phù hợp và quyền đọc riêng.

## 18. Mẫu yêu cầu bảo mật có thể nghiệm thu

| ID | Yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| KEY-REC-01 | Mỗi nhóm khóa có mục đích, sự kiện phục hồi và giới hạn được xác định | Recovery profile phân biệt quyền, material, nền tảng và compromise |
| KEY-REC-02 | Tập ciphertext cần giữ được bao phủ bởi khóa/phiên bản và metadata có thể phục hồi | Đối chiếu inventory dữ liệu, key dependency và các mốc backup |
| KEY-REC-03 | RTO và RPO có điểm đo cùng tiêu chí nghiệp vụ cụ thể | Báo cáo diễn tập đo tới operation/luồng ứng dụng đã định |
| KEY-REC-04 | Backup dùng cơ chế bảo vệ được hỗ trợ, không tạo đường xuất rõ ngoài policy | Kiểm tra artifact, quyền mở, security domain và môi trường đích |
| KEY-REC-05 | Credential bootstrap và phụ thuộc phục hồi không bị khóa trong cùng điểm lỗi duy nhất | Diễn tập mất môi trường chính mà không dựa vào phụ thuộc đã mất |
| KEY-REC-06 | Quyền phục hồi giới hạn theo sự kiện, operation, tài nguyên và thời gian | Kiểm tra principal hợp lệ/không hợp lệ cùng việc đóng quyền |
| KEY-REC-07 | Quorum hoặc dual control có hiệu lực ở đường thực thi nếu profile yêu cầu | Thử thiếu người/thành phần và kiểm tra không có đường một chủ thể vượt qua |
| KEY-REC-08 | Trạng thái xóa/hủy và cửa sổ phục hồi được lấy từ đúng nền tảng/tài nguyên | Kiểm tra cảnh báo, thời hạn và operation được hỗ trợ trên tài nguyên thử |
| KEY-REC-09 | Restore không làm sống lại quyền hoặc khóa bị loại khỏi policy hiện hành | Đối chiếu snapshot với dữ liệu thu hồi/ngừng dùng có thẩm quyền |
| KEY-REC-10 | Khóa compromised không được tự đưa lại vào hoạt động như khóa an toàn | Diễn tập nhánh compromise và kiểm tra operation/phạm vi sử dụng |
| KEY-REC-11 | Hoàn tất yêu cầu kiểm tra cả mật mã, ứng dụng, quyền âm và phạm vi dữ liệu | Bằng chứng theo từng mức, không chỉ object key hoặc job ID |
| KEY-REC-12 | Audit và báo cáo không chứa raw key, recovery secret hoặc dữ liệu nhạy cảm ngoài policy | Kiểm tra log, ticket, artifact và báo cáo bằng giá trị thử có thể nhận diện |
| KEY-REC-13 | Thất bại hoặc phục hồi từng phần được ghi nhận trung thực, không fallback yếu | Gây lỗi dependency/backup trong diễn tập và đối chiếu trạng thái còn lại |
| KEY-REC-14 | Runbook và người giữ vật liệu được cập nhật khi hệ thống thay đổi | Kiểm tra bàn giao, thay nhân sự, đổi provider và diễn tập định kỳ theo policy |

Các yêu cầu là ví dụ cho một dự án. Giá trị mục tiêu, nền tảng, danh tính, tập dữ liệu và người chịu trách nhiệm cần được chốt trước khi dùng làm gate chính thức.

## 19. Kịch bản chấp nhận minh họa

### 19.1. Mất quyền workload nhưng vật liệu còn nguyên

```text
Given:
  Vật liệu và trạng thái khóa vẫn phù hợp policy.
  Workload không thực hiện được operation do thay đổi quyền đã được xác minh.

When:
  Thực hiện kế hoạch phục hồi quyền được cấp cho sự kiện.

Then:
  Workload thực hiện được đúng operation trên đúng tài nguyên.
  Principal ngoài phạm vi vẫn bị từ chối.
  Không xuất raw key chỉ để giải quyết lỗi quyền.
```

### 19.2. Restore dữ liệu có phiên bản khóa mới hơn bản backup khóa

```text
Given:
  Backup dữ liệu thử chứa bản ghi cần K2.
  Một nguồn backup khóa chỉ chứa K1.

When:
  Kiểm tra khả năng phục hồi theo kế hoạch.

Then:
  Khoảng thiếu K2 được phát hiện rõ.
  Không coi alias cùng tên hoặc khóa mới tạo là vật liệu thay thế.
  Chỉ đánh dấu hoàn tất khi có nguồn hợp lệ đủ đáp ứng phạm vi yêu cầu.
```

### 19.3. Không đủ thành phần recovery

```text
Given:
  Profile thử yêu cầu một ngưỡng thành phần hoặc số chủ thể cụ thể.
  Tình huống diễn tập chưa có đủ điều kiện đó.

When:
  Thử thực hiện đường phục hồi trong phạm vi được phép.

Then:
  Không khôi phục được khả năng vượt quá quyền được cấp.
  Không có một credential dùng chung âm thầm bỏ qua cơ chế nhiều bên.
  Trạng thái chưa đủ điều kiện được ghi nhận mà không lộ share hoặc secret.
```

### 19.4. Backup chứa quyền đã bị thu hồi

```text
Given:
  Backup thử được tạo trước khi principal P bị thu hồi.
  Chính sách hiện hành không cho P dùng khóa.

When:
  Restore vào môi trường diễn tập theo kế hoạch.

Then:
  Quy trình đối chiếu policy giữ P ngoài phạm vi được phép.
  Hoạt động cần thiết của principal hợp lệ vẫn được kiểm chứng.
  Không kết luận an toàn chỉ vì nội dung backup đã được khôi phục nguyên trạng.
```

### 19.5. Vật liệu không còn có thể phục hồi

```text
Given:
  Trên tài nguyên thử, trạng thái và các nguồn còn lại không đủ để phục hồi material cần thiết.

When:
  Đánh giá kết quả theo profile.

Then:
  Kết quả ghi nhận không thể mở tập dữ liệu tương ứng bằng những nguồn hiện có.
  Không đưa một giá trị giả hoặc dữ liệu rỗng vào như kết quả thành công.
  Báo cáo nêu giới hạn và hành động tiếp theo theo quy trình sự cố.
```

### 19.6. Khóa đã bị đánh dấu compromised

```text
Given:
  Một key thử còn có thể restore nhưng trạng thái hiện hành là compromised.

When:
  Thực hiện đánh giá kế hoạch phục hồi.

Then:
  Không tự kích hoạt lại quyền ký/mã hóa mới như trước sự cố.
  Nhánh thay khóa và xử lý dữ liệu cũ đi theo phạm vi đã phê duyệt.
  Khả năng vận hành lại được phân biệt với việc đã khôi phục an toàn.
```

## 20. Ma trận bằng chứng và điều kiện hoàn tất

| Bằng chứng | Điều có thể xác nhận | Điều chưa chứng minh một mình |
| --- | --- | --- |
| Có backup artifact | Một nguồn đã được lưu | Nguồn đó đủ phiên bản, mở được và đáng tin |
| API trả job ID | Nền tảng đã nhận yêu cầu | Restore đã hoàn tất hoặc ứng dụng dùng được |
| Key xuất hiện ở đích | Có một object/khả năng tại đích | Đúng material, đúng policy và đúng phụ thuộc dữ liệu |
| Một ciphertext thử mở được | Luồng mật mã cụ thể hoạt động | Mọi phiên bản và mọi bản lưu trong retention đều được bao phủ |
| Principal hợp lệ dùng được | Một đường cấp quyền đang hoạt động | Principal không hợp lệ và quyền cũ đã bị chặn |
| Audit có sự kiện | Có dấu vết trong nguồn đã quan sát | Mọi operation ngoài nền tảng cũng đã được ghi nhận |
| Đạt thời gian restore kỹ thuật | Một công đoạn nằm trong ngân sách | RTO nghiệp vụ đã đạt tới mốc hoàn tất đã định |
| Cleanup tác vụ | Một tập artifact/quyền tạm đã xử lý | Không còn bản sao hoặc session nào ngoài inventory |

Một kết quả hoàn tất nên ghi rõ case ID, profile, tài nguyên thử, mốc backup, phiên bản liên quan, trạng thái job, kiểm tra quyền và thời gian đo được. Những dữ liệu này phải được chọn để hỗ trợ đối chiếu mà không biến báo cáo thành nơi lưu bí mật.

Nếu chỉ đạt một phần phạm vi, kết quả cần phản ánh đúng phần đó. Không dùng từ “recover thành công” chung chung khi một nhóm backup lịch sử hoặc một tenant chưa được kiểm tra đủ.

## 21. Duy trì khả năng phục hồi trong vòng đời hệ thống

Khả năng recovery có thể giảm dần khi thêm phiên bản khóa, đổi provider, thay người giữ vật liệu hoặc thay cơ chế xác thực. Một lần diễn tập thành công không bảo đảm những phụ thuộc mới vẫn được bao phủ.

Khi thay đổi cây khóa, retention hoặc định dạng dữ liệu, nhóm cần cập nhật mapping và nguồn phục hồi. Khi thu hồi quyền hoặc xử lý compromise, cần bảo đảm backup lịch sử không thể âm thầm đưa quyền cũ trở lại. Khi chuyển nhân sự, cần bàn giao quyền, vị trí vật mang dữ liệu và trách nhiệm mà không sao chép secret qua kênh không được phép.

Thiết kế key recovery đạt mục tiêu khi có đủ nguồn và quyền để khôi phục chức năng được cam kết, kiểm chứng được đúng dữ liệu/khóa và giữ nguyên giới hạn bảo mật hiện hành. Điều không thể phục hồi phải được xác định trung thực; điều có thể phục hồi phải được diễn tập mà không tạo thêm một đường chiếm quyền hoặc rò rỉ vật liệu.
