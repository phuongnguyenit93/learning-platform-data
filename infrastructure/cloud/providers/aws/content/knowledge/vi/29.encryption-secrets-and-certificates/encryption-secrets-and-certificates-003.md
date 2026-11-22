# AWS managed key, customer managed key và chiến lược lựa chọn

Trong AWS, mã hóa dữ liệu thường được triển khai thông qua AWS Key Management Service (AWS KMS). Khi một dịch vụ như Amazon EBS, Amazon RDS, Amazon S3 hoặc AWS Secrets Manager cần mã hóa dữ liệu, KMS có thể cung cấp khóa để dịch vụ bảo vệ dữ liệu đó. Câu hỏi thiết kế quan trọng là nên dùng **AWS managed key** do AWS quản lý hay **customer managed key** do tổ chức tạo và kiểm soát.

Lựa chọn này ảnh hưởng đến quyền truy cập, khả năng kiểm toán, luân chuyển khóa, chia sẻ dữ liệu giữa tài khoản, chi phí và trách nhiệm vận hành. Không có một loại khóa phù hợp cho mọi workload. Cần bắt đầu từ yêu cầu bảo mật và cách dịch vụ AWS tích hợp với KMS, sau đó chọn mức độ kiểm soát vừa đủ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt AWS owned key, AWS managed key và customer managed key.
- Giải thích ai tạo, ai quản lý và ai có thể thay đổi chính sách của từng loại khóa.
- Đánh giá tác động của loại khóa đến rotation, quyền truy cập, cross-account, audit và chi phí.
- Chọn loại khóa phù hợp cho một workload AWS và xây dựng quy trình quản lý vòng đời khóa.

## 1. AWS KMS và vai trò của khóa mã hóa

AWS KMS là dịch vụ quản lý khóa mã hóa. KMS kiểm soát việc sử dụng key material và cung cấp các thao tác mật mã thông qua API. Với phần lớn dịch vụ AWS, ứng dụng không cần tự quản lý key material: dịch vụ tích hợp với KMS để mã hóa hoặc giải mã dữ liệu theo quyền được cấp.

Một KMS key là tài nguyên logic trong một AWS account và Region. Key có metadata, key policy, trạng thái, cấu hình và key material tương ứng. Key material là thành phần thực hiện phép mã hóa; với khóa do KMS tạo và quản lý, key material được bảo vệ trong hệ thống KMS và không được trả về cho ứng dụng dưới dạng bản rõ.

Khi dữ liệu lớn hơn giới hạn của thao tác mã hóa trực tiếp bằng KMS, hệ thống thường dùng **envelope encryption**:

1. KMS tạo một data key (DEK), trả về DEK bản rõ và một bản DEK đã được mã hóa bằng KMS key.
2. Ứng dụng hoặc dịch vụ dùng DEK bản rõ để mã hóa dữ liệu tại nơi xử lý.
3. Ứng dụng lưu ciphertext cùng encrypted DEK; sau khi mã hóa, bản DEK rõ được loại khỏi bộ nhớ khi không còn cần thiết.
4. Khi cần giải mã, ứng dụng gửi encrypted DEK đến KMS để lấy lại DEK bản rõ, rồi dùng DEK đó giải mã dữ liệu.

Nhờ cách này, KMS bảo vệ khóa dữ liệu mà không phải nhận toàn bộ nội dung dữ liệu lớn. Các dịch vụ AWS thường che giấu phần lớn quy trình envelope encryption khỏi người dùng.

## 2. Ba loại khóa cần phân biệt

AWS KMS có ba nhóm khóa thường gặp. Trong đó, AWS managed key và customer managed key là hai lựa chọn chính khi thiết kế cách một workload dùng KMS trong tài khoản của mình.

### AWS owned keys

AWS owned keys do AWS sở hữu và quản lý. Chúng không nằm trong AWS account của khách hàng, vì vậy khách hàng không thể xem chúng trong danh sách KMS keys, thay đổi key policy, gắn tag, cấu hình rotation hoặc kiểm soát vòng đời của từng khóa.

Một số dịch vụ AWS dùng AWS owned keys để bảo vệ dữ liệu. Dịch vụ chịu trách nhiệm lựa chọn và vận hành khóa. Người dùng thường chỉ cấu hình tính năng mã hóa ở cấp dịch vụ, nếu dịch vụ cung cấp tùy chọn đó.

### AWS managed keys

AWS managed key là KMS key nằm trong AWS account của khách hàng nhưng được một dịch vụ AWS tạo và quản lý thay mặt khách hàng. Ví dụ, Amazon EBS có thể dùng khóa có alias `aws/ebs`; Amazon S3 có thể dùng `aws/s3` khi cấu hình SSE-KMS với AWS managed key.

Bạn có thể xem metadata, key ID, alias, key policy và các sự kiện sử dụng khóa trong những công cụ AWS hỗ trợ. Tuy nhiên, AWS quản lý key policy và key material. Khách hàng không thể tự sửa key policy, tạo hoặc thu hồi grant theo ý mình, đổi lịch rotation, tắt khóa hay lên lịch xóa khóa. AWS managed key thường được tạo tự động khi bạn lần đầu chọn cơ chế mã hóa tương ứng của dịch vụ.

AWS managed key có alias theo dạng `aws/<service>`. Khóa được giới hạn theo account và Region. Khách hàng sử dụng khóa thông qua dịch vụ AWS đã tạo khóa; không nên xem nó như một khóa dùng chung để ứng dụng tùy ý gọi các thao tác mật mã trực tiếp.

AWS quản lý rotation cho AWS managed keys. Khóa đối xứng đủ điều kiện được tự động xoay theo lịch do AWS quy định, thường là mỗi năm; khách hàng không thể tự đặt chu kỳ hoặc yêu cầu xoay theo lịch riêng. Việc xoay key material không làm thay đổi key ID và không yêu cầu người dùng tự mã hóa lại dữ liệu đã được bảo vệ bằng khóa cũ.

### Customer managed keys

Customer managed key (CMK) là KMS key mà khách hàng tạo và quản lý trong tài khoản AWS của mình. Khách hàng kiểm soát key policy, có thể dùng IAM policy để phân quyền khi key policy cho phép, tạo grant, gắn tag, đặt alias, bật hoặc tắt khóa, cấu hình rotation và lên lịch xóa khóa.

Customer managed key phù hợp khi tổ chức cần xác định rõ ai được dùng khóa, dịch vụ nào được phép dùng khóa, tài khoản nào có thể truy cập, hoặc cần bằng chứng kiểm toán theo từng ranh giới dữ liệu. Một CMK có thể được dùng bởi dịch vụ AWS tích hợp với KMS hoặc bởi ứng dụng gọi KMS API, tùy loại khóa và quyền được cấp.

Customer managed keys hỗ trợ nhiều cấu hình hơn AWS managed keys, chẳng hạn khóa đối xứng, khóa bất đối xứng, HMAC, key material do KMS tạo hoặc key material được nhập vào trong những trường hợp được hỗ trợ. Customer managed keys cũng hỗ trợ multi-Region keys nếu workload cần dùng cùng key material logic ở nhiều Region.

## 3. So sánh AWS managed key và customer managed key

| Tiêu chí | AWS managed key | Customer managed key |
|---|---|---|
| Ai tạo | Dịch vụ AWS tạo khi cần | Khách hàng tạo, có thể được dịch vụ hỗ trợ tạo trong một số luồng |
| Ai quản lý key material | AWS | AWS KMS bảo vệ key material; khách hàng kiểm soát cấu hình và quyền sử dụng |
| Key policy | AWS quản lý; khách hàng không chỉnh sửa | Khách hàng kiểm soát |
| IAM policy và grant | Không thể tự cấu hình theo nhu cầu của khách hàng | Có thể dùng theo key policy và mô hình phân quyền của KMS |
| Rotation | AWS quản lý; khách hàng không tùy chỉnh lịch | Có thể bật rotation tự động cho loại khóa đủ điều kiện hoặc quản lý quy trình thay khóa thủ công |
| Tắt hoặc lên lịch xóa | Khách hàng không thể | Khách hàng có thể; cần kiểm soát tác động trước khi thực hiện |
| Tag và alias tùy chỉnh | Không hỗ trợ quản trị như CMK; alias do dịch vụ đặt | Hỗ trợ tag và alias do khách hàng quản lý |
| Truy cập cross-account | Không phải lựa chọn cho chia sẻ quyền dùng khóa cross-account | Có thể cấu hình cross-account nếu dịch vụ và use case hỗ trợ |
| Multi-Region | Không | Có thể tạo multi-Region customer managed key |
| Mức độ vận hành | Thấp | Cao hơn vì khách hàng chịu trách nhiệm về policy, lifecycle và giám sát |
| Chi phí | Không có phí lưu trữ khóa hàng tháng | Có phí khóa hàng tháng và chi phí request theo biểu phí KMS áp dụng |

Các chi tiết có thể thay đổi theo loại key, Region và dịch vụ tích hợp. Luôn kiểm tra tài liệu của dịch vụ đang sử dụng trước khi giả định rằng dịch vụ hỗ trợ mọi tính năng KMS.

## 4. Quyền truy cập: key policy, IAM policy và grant

KMS sử dụng **key policy** làm cơ chế kiểm soát truy cập cốt lõi cho từng KMS key. Key policy xác định principal nào được phép thực hiện thao tác trên khóa. IAM policy có thể cấp quyền cho principal trong tài khoản khi key policy cho phép cơ chế ủy quyền đó. Vì vậy, chỉ gắn một IAM policy cho role chưa chắc đã đủ để role sử dụng được KMS key.

Với customer managed key, hãy xác định rõ các nhóm quyền:

- **Key administrators**: quản lý cấu hình và chính sách khóa. Quyền quản trị không nhất thiết bao gồm quyền dùng khóa để giải mã dữ liệu.
- **Key users**: thực hiện các thao tác mật mã cần thiết như `Encrypt`, `Decrypt` hoặc `GenerateDataKey`.
- **AWS services**: được cấp quyền theo cách tích hợp mà dịch vụ hỗ trợ, thường thông qua key policy hoặc grant.
- **Auditors**: xem cấu hình và sự kiện sử dụng khóa mà không cần quyền giải mã dữ liệu.

Grant là cơ chế ủy quyền linh hoạt cho một số trường hợp, đặc biệt khi dịch vụ AWS cần quyền sử dụng khóa thay mặt tài nguyên. Grant không thay thế yêu cầu thiết kế key policy đúng. Khi thu hồi grant hoặc sửa policy, cần đánh giá các workload đang phụ thuộc vào quyền đó.

Với AWS managed key, AWS giữ quyền kiểm soát key policy. Nếu workload cần một policy riêng, quyền cross-account, hoặc điều kiện truy cập theo principal và encryption context, hãy kiểm tra xem dịch vụ có hỗ trợ customer managed key hay không.

### Encryption context

Encryption context là tập cặp key-value không bí mật được gửi kèm một số thao tác mã hóa của KMS. KMS dùng context như dữ liệu bổ sung được xác thực (authenticated additional data); context không được mã hóa và phải được cung cấp lại chính xác khi giải mã. Tổ chức có thể dùng encryption context trong điều kiện policy để giới hạn việc dùng khóa cho một loại tài nguyên hoặc mục đích cụ thể.

Ví dụ, một ứng dụng có thể gửi context `{"App":"orders","Environment":"prod"}` khi gọi thao tác KMS. Không đưa mật khẩu, token, dữ liệu cá nhân hoặc bí mật vào encryption context vì giá trị này không được thiết kế để giữ bí mật và có thể xuất hiện trong log kiểm toán.

## 5. Rotation và vòng đời khóa

Rotation thay key material được dùng cho các thao tác mã hóa mới trong cùng một KMS key. Khi rotation được KMS hỗ trợ, KMS giữ các phiên bản key material cũ để có thể giải mã ciphertext đã tạo trước đó. Key ID và alias vẫn giữ nguyên. Ứng dụng tiếp tục tham chiếu cùng KMS key, vì vậy thông thường không cần mã hóa lại toàn bộ dữ liệu chỉ vì rotation tự động diễn ra.

Đối với customer managed key, rotation tự động được hỗ trợ cho khóa mã hóa đối xứng dùng key material do AWS KMS tạo. Có thể cấu hình chu kỳ rotation từ 90 đến 2.560 ngày; chu kỳ phổ biến mặc định là 365 ngày. Khóa bất đối xứng, HMAC, khóa có key material nhập từ bên ngoài và một số loại custom key store không hỗ trợ automatic rotation theo cùng cơ chế. Các trường hợp này cần quy trình quản lý key material riêng.

Phân biệt hai việc sau:

- **Rotate key material**: KMS giữ nguyên KMS key và quản lý các phiên bản key material để giải mã dữ liệu cũ.
- **Thay KMS key bằng một key khác**: tạo tài nguyên khóa mới, cập nhật workload và thực hiện re-encrypt hoặc re-wrap dữ liệu khi cần. Đây là một thay đổi kiến trúc và cần kế hoạch chuyển đổi.

Với customer managed key, các trạng thái và thao tác lifecycle có ảnh hưởng trực tiếp đến khả năng truy cập dữ liệu:

- **Disable**: các thao tác mật mã bằng khóa bị chặn cho đến khi khóa được bật lại. Dịch vụ phụ thuộc vào khóa có thể ngừng đọc hoặc ghi dữ liệu.
- **Schedule deletion**: KMS đặt thời gian chờ trước khi xóa vĩnh viễn, trong khoảng từ 7 đến 30 ngày. Trong thời gian chờ có thể hủy lịch xóa. Sau khi xóa hoàn tất, dữ liệu chỉ có thể giải mã nếu còn một bản sao khóa hợp lệ khác.
- **Policy hoặc grant thay đổi**: workload có thể mất quyền gọi KMS dù ciphertext vẫn còn nguyên.

Trước khi disable hoặc xóa khóa, cần xác định tài nguyên, snapshot, backup, log, secret và dữ liệu lưu trữ nào đang phụ thuộc vào khóa. Kiểm thử khôi phục dữ liệu từ backup là một phần của quy trình quản lý khóa.

## 6. Cross-account và multi-Region

Nếu dữ liệu được mã hóa bằng customer managed key và cần được một tài khoản AWS khác sử dụng, có thể cấu hình quyền cross-account. Thông thường cần cả hai phía: key policy ở tài khoản sở hữu khóa cho phép principal bên ngoài, và IAM policy ở tài khoản bên ngoài cho phép principal gọi thao tác KMS. Dịch vụ lưu trữ hoặc dịch vụ tiêu thụ dữ liệu cũng phải hỗ trợ mô hình chia sẻ đó.

AWS managed key không phải lựa chọn phù hợp cho use case cross-account vì khách hàng không kiểm soát key policy của khóa đó. Khi cần chia sẻ snapshot EBS, bản sao dữ liệu, tài nguyên hoặc workload giữa tài khoản, hãy xác nhận yêu cầu của dịch vụ và cân nhắc customer managed key.

KMS key thông thường gắn với một Region. Nếu ứng dụng cần xử lý ciphertext ở nhiều Region, customer managed multi-Region key có thể giúp dùng các khóa liên quan với cùng key material và key ID. Mỗi bản primary hoặc replica vẫn có policy, grant, alias và trạng thái quản lý riêng theo Region. Không phải dịch vụ AWS nào cũng hỗ trợ multi-Region keys; cần xác minh trước khi chọn kiến trúc này.

## 7. Chi phí và trách nhiệm vận hành

AWS managed keys giảm công việc quản trị và không có phí lưu trữ khóa hàng tháng. Customer managed keys có phí khóa hàng tháng; các request KMS và tính năng liên quan có thể phát sinh chi phí theo biểu phí, loại khóa và Region. Dịch vụ sử dụng KMS cũng có thể có chi phí riêng.

Khi đánh giá chi phí, không chỉ đếm số lượng khóa. Hãy xem số request mã hóa/giải mã, tần suất tạo data key, số Region, số tài khoản, yêu cầu audit và công sức vận hành. Tách khóa theo từng tài nguyên nhỏ có thể làm tăng chi phí và độ phức tạp. Dùng chung một khóa cho quá nhiều ứng dụng lại làm tăng phạm vi ảnh hưởng nếu policy hoặc khóa bị cấu hình sai.

## 8. Chiến lược lựa chọn

Hãy trả lời các câu hỏi sau trước khi chọn loại khóa:

1. Dịch vụ AWS có hỗ trợ AWS managed key, customer managed key hay cả hai cho tính năng đang dùng?
2. Có yêu cầu kiểm soát key policy, quyền dùng khóa hoặc encryption context riêng không?
3. Dữ liệu có cần chia sẻ giữa AWS accounts hoặc xử lý ở nhiều Region không?
4. Có yêu cầu kiểm toán, phân tách nhiệm vụ, tag để phân bổ chi phí hoặc bằng chứng quản lý vòng đời khóa không?
5. Tổ chức có đủ quy trình và người chịu trách nhiệm cho rotation, policy, cảnh báo, backup và deletion không?

### Khi nên chọn AWS managed key

Chọn AWS managed key khi dịch vụ hỗ trợ nó và các điều kiện sau phù hợp:

- Mã hóa mặc định của dịch vụ đã đáp ứng yêu cầu bảo mật và tuân thủ.
- Không cần tự chỉnh key policy hoặc chia sẻ quyền sử dụng khóa cho tài khoản khác.
- Không cần lịch rotation riêng, tag quản trị hoặc quyền tắt/xóa khóa.
- Muốn giảm số lượng quyết định và công việc vận hành liên quan đến khóa.

Ví dụ: một môi trường thử nghiệm dùng EBS encryption với `aws/ebs`, hoặc một workload đơn giản dùng tùy chọn AWS managed key mà dịch vụ cung cấp. Đây là lựa chọn hợp lý nếu yêu cầu nội bộ không đòi hỏi quyền kiểm soát bổ sung.

### Khi nên chọn customer managed key

Chọn customer managed key khi có một hoặc nhiều yêu cầu sau:

- Cần kiểm soát principal và dịch vụ nào được phép dùng khóa.
- Cần cấp quyền cross-account hoặc thiết kế ranh giới bảo mật riêng.
- Cần rotation theo lịch tổ chức, tag, alias hoặc quy trình lifecycle riêng.
- Cần tách quyền quản trị khóa khỏi quyền vận hành ứng dụng.
- Cần kiểm toán chi tiết và chứng minh quyền sử dụng khóa theo workload hoặc nhóm dữ liệu.
- Cần multi-Region key trong một kiến trúc được dịch vụ hỗ trợ.

Ví dụ: hệ thống thanh toán production cần key policy giới hạn quyền giải mã cho một số role; nhóm bảo mật quản trị khóa, nhóm ứng dụng chỉ được gọi các thao tác cần thiết; dữ liệu được chia sẻ cross-account theo một quy trình được phê duyệt. Customer managed key tạo ra ranh giới kiểm soát phù hợp cho trường hợp này.

### Ma trận quyết định nhanh

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Mã hóa đơn giản theo cấu hình sẵn của dịch vụ | AWS managed key | Ít vận hành, AWS quản lý policy và rotation |
| Chính sách quyền truy cập riêng | Customer managed key | Khách hàng kiểm soát key policy và grant |
| Dùng khóa cho workload ở tài khoản khác | Customer managed key | Có thể cấu hình cross-account khi dịch vụ hỗ trợ |
| Phân tách khóa theo ứng dụng hoặc phân loại dữ liệu | Customer managed key | Quản lý quyền, tag và audit theo ranh giới |
| Không có yêu cầu kiểm soát bổ sung | AWS managed key | Tránh độ phức tạp không cần thiết |
| Cần multi-Region key | Customer managed key | Hỗ trợ primary và replica theo Region |

Ma trận này là điểm khởi đầu. Tài liệu của dịch vụ AWS và yêu cầu kiểm soát nội bộ vẫn là căn cứ quyết định cuối cùng.

## 9. Ví dụ tạo và cấu hình customer managed key

Ví dụ sau tạo một KMS key đối xứng để bảo vệ dữ liệu của ứng dụng đơn hàng production. Lệnh chỉ tạo khóa và alias; trước khi đưa vào workload thực tế, cần rà soát key policy, IAM policy, quyền của dịch vụ và quy trình vận hành.

```bash
# Tạo customer managed key đối xứng với key material do KMS tạo.
aws kms create-key \
  --description "KMS key for orders production" \
  --key-spec SYMMETRIC_DEFAULT \
  --key-usage ENCRYPT_DECRYPT \
  --origin AWS_KMS

# Thay <key-id> bằng KeyId trong kết quả create-key.
aws kms create-alias \
  --alias-name alias/orders-prod \
  --target-key-id <key-id>

# Bật automatic rotation cho khóa đủ điều kiện.
aws kms enable-key-rotation --key-id <key-id>

# Kiểm tra trạng thái rotation.
aws kms get-key-rotation-status --key-id <key-id>
```

Trong môi trường production, không đưa key ID hoặc ARN cố định vào nhiều nơi nếu có thể tham chiếu alias phù hợp. Quản lý quyền bằng least privilege; tách quyền quản trị khóa khỏi quyền sử dụng khóa; ghi nhận owner, mục đích, môi trường và ngày rà soát trong tag hoặc hệ thống quản lý tài sản. Chỉ cấp `Decrypt` cho principal thực sự cần giải mã.

## 10. Tình huống thực tế

### Tình huống A: mã hóa volume cho môi trường phát triển

Một nhóm phát triển tạo EC2 instance và bật EBS encryption. Nhóm không có yêu cầu chia sẻ snapshot giữa tài khoản, không cần key policy riêng và muốn giảm công việc vận hành. Nếu chính sách tổ chức cho phép, AWS managed key `aws/ebs` là lựa chọn phù hợp. Nhóm vẫn cần kiểm tra cấu hình mã hóa mặc định của account và Region.

### Tình huống B: dữ liệu production cần phân quyền riêng

Một ứng dụng lưu thông tin đơn hàng trong dịch vụ hỗ trợ SSE-KMS. Bộ phận bảo mật cần kiểm soát role nào được giải mã dữ liệu và muốn xem hoạt động sử dụng khóa theo ranh giới ứng dụng. Customer managed key cho phép định nghĩa key policy, tag và quy trình kiểm toán phù hợp hơn. Nhóm vận hành phải theo dõi policy, rotation và trạng thái khóa để tránh gián đoạn.

### Tình huống C: chia sẻ snapshot giữa hai tài khoản

Tài khoản nguồn tạo snapshot mã hóa bằng customer managed key. Tài khoản đích cần copy snapshot và tạo volume từ bản copy. Nhóm phải cấu hình quyền sử dụng khóa ở tài khoản nguồn, quyền IAM ở tài khoản đích và làm theo yêu cầu chia sẻ snapshot của EBS. Nếu snapshot dùng AWS managed key, khách hàng không thể sửa key policy để cấp quyền cross-account theo cách này; cần thiết kế lại bằng customer managed key và quy trình copy phù hợp.

### Tình huống D: ứng dụng chạy ở nhiều Region

Một ứng dụng cần đọc ciphertext ở hai Region trong kịch bản phục hồi thảm họa. Nếu dịch vụ và quy trình ứng dụng hỗ trợ, multi-Region customer managed key có thể giảm công việc đồng bộ key material. Nhóm vẫn phải quản lý policy, grant, alias và trạng thái ở từng Region, đồng thời kiểm thử quy trình failover và khôi phục.

## 11. Những lỗi thiết kế thường gặp

- **Chọn customer managed key cho mọi tài nguyên mà không có yêu cầu cụ thể**: làm tăng số lượng khóa, chi phí và việc vận hành. Hãy xác định ranh giới bảo mật cần có trước khi tách khóa.
- **Cho rằng IAM policy luôn đủ để cấp quyền KMS**: key policy vẫn là cơ chế kiểm soát cốt lõi. Kiểm tra cả key policy và IAM policy khi xử lý lỗi `AccessDenied`.
- **Dùng AWS managed key cho use case cross-account**: khách hàng không kiểm soát key policy của loại khóa này. Chọn customer managed key nếu dịch vụ yêu cầu quyền chia sẻ khóa.
- **Disable hoặc schedule deletion mà chưa tìm dependency**: thao tác có thể làm ứng dụng mất khả năng giải mã. Kiểm tra snapshot, backup, log, secret và dữ liệu lưu trữ trước khi thay đổi.
- **Nhầm rotation với thay khóa**: rotation giữ nguyên KMS key và các phiên bản key material cần cho giải mã; thay KMS key là dự án chuyển đổi riêng.
- **Đưa dữ liệu bí mật vào encryption context**: encryption context không phải nơi lưu secret. Chỉ dùng giá trị định danh không nhạy cảm.
- **Tin rằng mọi dịch vụ đều hỗ trợ mọi tính năng KMS**: kiểm tra tài liệu dịch vụ về loại khóa, cross-account, multi-Region và cách cấp quyền trước khi triển khai.

## 12. Checklist vận hành customer managed key

Trước khi đưa khóa vào production, hãy xác nhận:

- [ ] Có owner chịu trách nhiệm và mục đích sử dụng được ghi nhận.
- [ ] Key policy và IAM policy áp dụng nguyên tắc least privilege.
- [ ] Quyền quản trị, quyền sử dụng và quyền kiểm toán được phân tách hợp lý.
- [ ] Dịch vụ AWS được cấp quyền theo đúng hướng dẫn tích hợp.
- [ ] Rotation được cấu hình nếu loại khóa hỗ trợ; trường hợp không hỗ trợ có quy trình thay key material hoặc thay khóa.
- [ ] CloudTrail và các cảnh báo cần thiết được cấu hình để theo dõi hoạt động quản trị và sử dụng khóa.
- [ ] Có quy trình xử lý khi khóa bị disable, policy thay đổi hoặc grant bị thu hồi.
- [ ] Có quy trình rà soát dependency trước khi schedule deletion.
- [ ] Đã kiểm thử khôi phục dữ liệu và backup trong môi trường phù hợp.
- [ ] Cross-account và multi-Region đã được kiểm thử nếu workload có sử dụng.

## Kết luận

AWS managed key phù hợp khi cấu hình mã hóa do dịch vụ cung cấp đã đáp ứng yêu cầu và tổ chức muốn giảm công việc quản trị khóa. Customer managed key phù hợp khi cần kiểm soát policy, quyền sử dụng, chia sẻ cross-account, rotation, tag, audit hoặc lifecycle. AWS owned keys là lựa chọn do AWS quản lý hoàn toàn trong một số dịch vụ và không cung cấp quyền kiểm soát trực tiếp cho khách hàng.

Hãy chọn khóa dựa trên yêu cầu của dữ liệu và workload, kiểm tra khả năng hỗ trợ của dịch vụ AWS, rồi thiết kế quyền và vòng đời khóa cùng với quy trình vận hành. Khóa được quản lý tốt phải luôn sẵn sàng cho workload hợp lệ, đồng thời chỉ cho đúng principal thực hiện đúng thao tác.

## Tài liệu tham khảo

- [AWS KMS concepts](https://docs.aws.amazon.com/kms/latest/developerguide/concepts.html)
- [AWS managed keys](https://docs.aws.amazon.com/kms/latest/developerguide/concepts.html#aws-managed-key)
- [Customer managed keys](https://docs.aws.amazon.com/kms/latest/developerguide/concepts.html#customer-mgn-key)
- [Rotating AWS KMS keys](https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html)
- [Key policies in AWS KMS](https://docs.aws.amazon.com/kms/latest/developerguide/key-policies.html)
- [Grants in AWS KMS](https://docs.aws.amazon.com/kms/latest/developerguide/grants.html)
- [Multi-Region keys](https://docs.aws.amazon.com/kms/latest/developerguide/multi-region-keys-overview.html)
- [Encryption context](https://docs.aws.amazon.com/kms/latest/developerguide/encrypt_context.html)
- [AWS Key Management Service pricing](https://aws.amazon.com/kms/pricing/)
