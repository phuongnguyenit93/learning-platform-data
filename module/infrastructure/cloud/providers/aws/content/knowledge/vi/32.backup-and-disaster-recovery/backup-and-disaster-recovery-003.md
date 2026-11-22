# Backup policy tập trung và sao lưu liên tài khoản

Trong một tổ chức AWS có nhiều tài khoản, mỗi nhóm ứng dụng có thể tự tạo backup plan, chọn lịch sao lưu và quản lý backup vault theo cách riêng. Cách làm này linh hoạt ở quy mô nhỏ nhưng khó duy trì khi số lượng tài khoản, Region và workload tăng lên. Một tài khoản có thể bị bỏ sót, chính sách lưu giữ có thể không đồng nhất, còn bản sao lưu đặt cùng tài khoản với workload có thể bị ảnh hưởng nếu tài khoản đó bị xâm nhập.

AWS Backup kết hợp với AWS Organizations giúp tổ chức quản lý chính sách sao lưu ở cấp tổ chức, OU hoặc tài khoản. Backup policy tập trung mô tả lịch, quy tắc lưu giữ, Region và lựa chọn tài nguyên; chính sách được kế thừa xuống các tài khoản thành viên. AWS Backup còn hỗ trợ sao chép recovery point sang backup vault ở tài khoản khác, tạo thêm một lớp bảo vệ khi tài khoản nguồn gặp sự cố.

Bài học này thuộc phạm vi CLOUD_PROVIDERS_AWS: thiết kế và vận hành hạ tầng AWS an toàn, có khả năng phục hồi và kiểm soát chi phí. Trọng tâm là cách xây dựng backup policy dùng chung, tổ chức quyền quản trị, cấu hình bản sao liên tài khoản và kiểm chứng khả năng khôi phục. Một chính sách tốt cần bao phủ đúng tài nguyên, đáp ứng RPO/RTO, bảo vệ bản sao và được kiểm tra bằng các lần restore thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt backup plan, backup rule, backup selection, backup vault và backup policy của AWS Organizations.
- Giải thích cách AWS Backup phối hợp với AWS Organizations để quản lý chính sách sao lưu tập trung.
- Thiết kế cấu trúc chính sách theo root, OU và tài khoản, đồng thời hiểu cách kế thừa và ghi đè thuộc tính.
- Xác định vai trò của management account, delegated administrator và tài khoản thành viên.
- Thiết lập luồng sao chép recovery point sang backup vault ở tài khoản khác.
- Phân tích quyền IAM, vault access policy và AWS KMS key policy cần thiết cho bản sao liên tài khoản.
- Xây dựng chiến lược lưu giữ, cô lập bản sao, kiểm thử restore và giám sát chi phí.

## 2. Các khái niệm nền tảng của AWS Backup

### 2.1. Backup plan và backup policy

**Backup plan** là cấu hình sao lưu trong AWS Backup. Một plan chứa một hoặc nhiều rule, trong đó mỗi rule xác định lịch chạy, backup vault đích và vòng đời của recovery point. Rule cũng có thể quy định sao chép recovery point sang vault khác.

**Backup policy** là loại chính sách của AWS Organizations dành cho AWS Backup. Policy mô tả các backup plan và lựa chọn tài nguyên sẽ được áp dụng cho tài khoản thành viên. Khi gắn policy vào root, OU hoặc tài khoản, AWS Organizations tạo chính sách hiệu lực dựa trên cấu hình được kế thừa từ cấp cha và các phần ghi đè ở cấp con.

Có thể hình dung:

- Backup plan là cấu hình xác định workload được sao lưu khi nào và lưu ở đâu.
- Backup policy là cơ chế phân phối và quản lý cấu hình backup plan trên nhiều tài khoản trong tổ chức.

Backup policy giúp chuẩn hóa cách sao lưu. Nó không tự động bảo đảm mọi tài nguyên đều được bảo vệ: tài nguyên phải thuộc phạm vi loại tài nguyên được hỗ trợ, đáp ứng điều kiện selection và nằm trong Region được policy chỉ định.

### 2.2. Backup rule và backup selection

Một backup plan có thể chứa nhiều rule để đáp ứng các mục tiêu khác nhau. Ví dụ:

- Rule hằng ngày giữ bản sao lưu trong thời gian ngắn để phục hồi lỗi vận hành.
- Rule hằng tuần hoặc hằng tháng giữ bản sao lâu hơn để đáp ứng yêu cầu kiểm toán.
- Rule tạo bản sao ở Region khác hoặc tài khoản lưu trữ chuyên dụng.

Backup selection xác định tài nguyên nào được đưa vào plan. Có thể lựa chọn theo loại tài nguyên, ARN hoặc thẻ tài nguyên tùy khả năng hỗ trợ. Một tổ chức thường dùng thẻ để phân loại workload, ví dụ **Backup=Daily**, **Backup=Critical** hoặc **Environment=Production**.

Thẻ chỉ có tác dụng nếu được gắn đúng vào tài nguyên và loại tài nguyên đó hỗ trợ cơ chế lựa chọn tương ứng. Cần quy định tên thẻ, giá trị hợp lệ, người chịu trách nhiệm và cách xử lý tài nguyên chưa được gắn thẻ.

### 2.3. Recovery point và backup vault

Recovery point là bản sao lưu được tạo ra từ một tài nguyên tại một thời điểm. AWS Backup lưu recovery point trong backup vault. Vault là vùng chứa logic dùng để tổ chức, kiểm soát truy cập và áp dụng các cơ chế bảo vệ cho bản sao lưu.

Mỗi vault thuộc một tài khoản và một Region. Một recovery point được tạo ở vault nguồn có thể được sao chép sang vault khác nếu loại tài nguyên và cấu hình hỗ trợ. Vault đích có thể nằm ở Region khác, tài khoản khác hoặc cả hai.

Vault có thể có resource-based access policy để kiểm soát principal nào được phép thực hiện hành động trên vault. AWS Backup Vault Lock có thể áp dụng thời hạn lưu giữ tối thiểu/tối đa và bảo vệ recovery point khỏi thao tác xóa hoặc thay đổi vòng đời trái với cấu hình khóa. Đây là lớp kiểm soát hữu ích khi cần chống sửa đổi hoặc xóa bản sao lưu ngoài ý muốn.

### 2.4. RPO và RTO định hướng chính sách

Trước khi chọn lịch sao lưu, cần xác định:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể chấp nhận mất, tính theo thời gian. RPO 24 giờ thường yêu cầu có bản sao ít nhất mỗi ngày, nhưng còn phụ thuộc thời điểm chạy, thời gian hoàn tất và loại backup.
- **RTO (Recovery Time Objective):** thời gian tối đa chấp nhận để khôi phục dịch vụ. RTO phụ thuộc vào kích thước dữ liệu, quy trình restore, hạ tầng đích, kiểm tra ứng dụng và thao tác chuyển đổi.

Tần suất backup ảnh hưởng trực tiếp đến RPO. Vị trí bản sao, khả năng truy cập, thời gian khởi tạo tài nguyên và quy trình vận hành ảnh hưởng đến RTO. Một lịch backup dày không tự động tạo ra RTO thấp nếu tổ chức chưa từng thử khôi phục.

## 3. Quản lý backup policy tập trung bằng AWS Organizations

### 3.1. Kiến trúc quản trị

Trong AWS Organizations, tài khoản được sắp xếp theo root, OU và account. Backup policy có thể được gắn ở các cấp này:

- Gắn ở root khi quy tắc cần áp dụng rộng cho toàn tổ chức.
- Gắn ở OU khi một nhóm tài khoản có cùng yêu cầu, ví dụ Production, Development hoặc Shared Services.
- Gắn ở account khi cần cấu hình riêng cho một workload hoặc ngoại lệ đã được phê duyệt.

Một kiến trúc phổ biến gồm:

1. Management account quản lý AWS Organizations và bật tích hợp cần thiết với AWS Backup.
2. Một tài khoản được đăng ký làm delegated administrator để nhóm backup quản lý tác vụ tập trung.
3. Backup policy được gắn vào root hoặc OU phù hợp.
4. Các tài khoản thành viên nhận policy hiệu lực và AWS Backup triển khai backup plan trong phạm vi tài khoản đó.
5. Recovery point được tạo trong vault của tài khoản workload, sau đó được sao chép sang vault ở tài khoản lưu trữ riêng.

Delegated administrator giúp tách hoạt động quản trị dịch vụ khỏi management account. Việc ủy quyền không đồng nghĩa mọi người trong tài khoản đó tự động có quyền truy cập mọi tài nguyên; vẫn cần cấu hình IAM, quyền của dịch vụ và phạm vi quản trị phù hợp.

### 3.2. Điều kiện trước khi triển khai

Trước khi tạo policy, xác nhận:

- AWS Organizations đã được cấu hình theo mô hình hỗ trợ tích hợp AWS Backup.
- Trusted access giữa AWS Organizations và AWS Backup đã được bật theo hướng dẫn của dịch vụ.
- Delegated administrator đã được đăng ký nếu tổ chức dùng tài khoản quản trị dịch vụ riêng.
- Các tài khoản thành viên cần bảo vệ đang thuộc đúng OU.
- Region dự kiến sử dụng đã được xác định và các dịch vụ nguồn có hỗ trợ AWS Backup tại Region đó.
- IAM role mà backup selection tham chiếu đã tồn tại hoặc có quy trình tạo role thích hợp trong tài khoản thành viên.
- Backup vault nguồn được chỉ định trong rule đã tồn tại ở từng tài khoản thành viên và Region tương ứng; policy chỉ tham chiếu tên vault, không thay thế bước chuẩn bị vault.
- Backup vault đích, chính sách truy cập vault và KMS key đã được chuẩn bị trước khi kích hoạt copy action.

Không nên triển khai policy diện rộng trước khi thử nghiệm với một OU hoặc tài khoản không quan trọng. Thử nghiệm giúp phát hiện lỗi về role, quyền KMS, lựa chọn tài nguyên và Region mà không tạo ra hàng loạt backup job thất bại.

### 3.3. Gắn policy và kiểm tra chính sách hiệu lực

Quy trình cơ bản:

1. Mở AWS Backup trong tài khoản quản trị dịch vụ hoặc management account theo mô hình đã chọn.
2. Kiểm tra tích hợp AWS Organizations và quyền quản trị.
3. Tạo backup policy với các plan, rule, selection và Region cần thiết.
4. Gắn policy vào root, OU hoặc account mục tiêu.
5. Kiểm tra effective policy của một tài khoản thành viên để xác nhận cấu hình được kế thừa như dự kiến.
6. Xác minh backup plan và backup selection đã xuất hiện trong tài khoản thành viên.
7. Theo dõi backup job đầu tiên và kiểm tra recovery point trong vault.

Effective policy rất quan trọng khi có nhiều cấp chính sách. Nội dung được gắn ở cấp root có thể cung cấp mặc định cho OU; policy cấp OU có thể bổ sung hoặc ghi đè phần được phép; policy cấp account có thể tinh chỉnh cho một tài khoản. Hãy kiểm tra kết quả cuối cùng ở tài khoản đích thay vì chỉ nhìn policy gốc.

## 4. Kế thừa và thiết kế cấu trúc policy

### 4.1. Quy tắc kế thừa

Backup policy của AWS Organizations sử dụng cơ chế kế thừa chính sách. Các toán tử như **@@assign**, **@@append** và **@@remove** giúp kiểm soát cách giá trị ở cấp con tương tác với giá trị cấp cha:

- **@@assign** gán giá trị cho thuộc tính tại cấp policy hiện tại; tùy vị trí, nó có thể thay thế giá trị kế thừa.
- **@@append** thêm giá trị vào danh sách kế thừa, phù hợp khi muốn mở rộng danh sách Region hoặc phạm vi tài nguyên.
- **@@remove** loại bỏ giá trị được kế thừa khỏi danh sách, nếu thuộc tính và ngữ cảnh policy hỗ trợ thao tác này.

Policy ở cấp cha có thể giới hạn các toán tử được phép dùng ở cấp con. Điều này giúp giữ những yêu cầu bắt buộc, chẳng hạn không cho OU con loại bỏ Region lưu trữ hoặc thay đổi thời hạn lưu giữ tối thiểu.

Không nên xem kế thừa như thao tác nối văn bản đơn giản. Cấu trúc JSON và toán tử được hỗ trợ có ý nghĩa đối với từng thuộc tính. Sau mỗi thay đổi, hãy kiểm tra effective policy và kết quả backup plan thực tế.

### 4.2. Ví dụ cấu trúc backup policy

Đoạn JSON dưới đây minh họa một policy rút gọn: tạo backup hằng ngày cho EBS volume trong Region Singapore và lưu recovery point vào vault **OrgDailyVault**. Đây là ví dụ học tập để nhận diện các thành phần; trước khi triển khai cần xác minh loại tài nguyên, IAM role, tên vault và schema policy phù hợp với môi trường thực tế.

~~~json
{
  "plans": {
    "daily-ebs": {
      "regions": {
        "@@assign": ["ap-southeast-1"]
      },
      "rules": {
        "daily": {
          "schedule_expression": {
            "@@assign": "cron(0 17 ? * * *)"
          },
          "start_backup_window_minutes": {
            "@@assign": "60"
          },
          "complete_backup_window_minutes": {
            "@@assign": "180"
          },
          "target_backup_vault_name": {
            "@@assign": "OrgDailyVault"
          },
          "lifecycle": {
            "delete_after_days": {
              "@@assign": "35"
            }
          }
        }
      },
      "selections": {
        "ebs-volumes": {
          "iam_role_arn": {
            "@@assign": "arn:aws:iam::$account:role/AWSBackupDefaultServiceRole"
          },
          "resources": {
            "@@assign": [
              "arn:aws:ec2:*:*:volume/*"
            ]
          }
        }
      }
    }
  }
}
~~~

Trong ví dụ:

- **plans** chứa các backup plan được quản lý tập trung.
- **regions** giới hạn Region mà plan được triển khai.
- **rules** định nghĩa lịch, cửa sổ backup, vault và thời hạn lưu giữ.
- **selections** xác định tài nguyên được bảo vệ và IAM role mà AWS Backup sử dụng.
- **$account** là biến được AWS Organizations thay bằng ID tài khoản thành viên trong quá trình áp dụng policy.

Biểu thức **cron(0 17 ? * * *)** chạy theo UTC. Với múi giờ Việt Nam UTC+7, thời điểm đó tương ứng 00:00 ngày kế tiếp. Khi chọn lịch, hãy quy đổi múi giờ và tránh dồn backup của quá nhiều workload vào cùng một thời điểm.

### 4.3. Tổ chức policy theo tầng

Một cách tổ chức dễ vận hành là:

| Cấp | Nội dung nên quản lý | Ví dụ |
|---|---|---|
| Root | Yêu cầu tối thiểu toàn tổ chức | Region bắt buộc, quy tắc lưu bản sao bảo vệ, chuẩn đặt tên |
| OU Production | Lịch và thời hạn cho hệ thống quan trọng | Backup hằng ngày, lưu 35 ngày, copy sang tài khoản vault |
| OU Development | Lịch tiết kiệm chi phí cho môi trường thử nghiệm | Backup hằng tuần, lưu 14 ngày |
| Account | Ngoại lệ đã được phê duyệt | Workload có yêu cầu RPO thấp hoặc thời hạn lưu giữ riêng |

Giữ policy ở cấp root đơn giản và ổn định. Đưa khác biệt vận hành vào OU theo phân loại workload. Chỉ tạo ngoại lệ ở cấp account khi có lý do rõ ràng, người phê duyệt và thời hạn rà soát.

### 4.4. Quản lý thẻ và lựa chọn tài nguyên

Tag-based selection giúp áp dụng cùng một policy cho nhiều tài nguyên mà không phải liệt kê từng ARN. Ví dụ, nhóm nền tảng có thể yêu cầu workload gắn **Backup=Daily** hoặc **Backup=Critical**. Backup selection sau đó tìm tài nguyên có thẻ phù hợp.

Để tránh bỏ sót:

- Chuẩn hóa chính tả, chữ hoa/thường và giá trị của tag.
- Tích hợp yêu cầu gắn tag vào quy trình tạo tài nguyên bằng Infrastructure as Code.
- Dùng AWS Config hoặc cơ chế kiểm tra nội bộ để phát hiện tài nguyên thiếu tag.
- Xác định rõ cách xử lý tài nguyên có tag sai hoặc chưa có tag.
- Kiểm tra danh sách tài nguyên thực tế được selection đưa vào backup plan.

Không giả định mọi loại tài nguyên đều hỗ trợ tag selection hoặc có cùng hành vi. Kiểm tra ma trận tính năng AWS Backup cho từng loại tài nguyên và Region.

## 5. Sao lưu liên tài khoản

### 5.1. Vì sao cần tài khoản backup riêng?

Nếu backup vault nằm trong cùng tài khoản với workload, một principal bị xâm nhập có quyền cao có thể tìm cách xóa tài nguyên và recovery point trong cùng phạm vi quản trị. Việc sao chép sang tài khoản lưu trữ riêng làm giảm rủi ro một sự cố tại tài khoản nguồn phá hủy luôn bản sao dự phòng.

Một mô hình tham khảo:

- **Workload account:** chạy ứng dụng và tạo recovery point ban đầu.
- **Backup administrator account:** quản lý policy và theo dõi backup job trên nhiều tài khoản.
- **Backup vault account:** sở hữu vault đích, KMS key và chính sách truy cập chặt chẽ.

Tùy quy mô tổ chức, backup administrator và backup vault account có thể là hai tài khoản riêng để phân tách quyền quản trị với quyền sở hữu bản sao. Tài khoản lưu trữ nên có ít người được quyền đăng nhập và thay đổi cấu hình.

### 5.2. Luồng sao chép recovery point

Luồng cơ bản gồm:

1. Backup plan chạy trong tài khoản nguồn và tạo recovery point ở vault nguồn.
2. Rule có copy action chỉ định backup vault đích bằng ARN.
3. AWS Backup kiểm tra quyền sao chép và chính sách truy cập của vault đích.
4. Recovery point được sao chép sang vault thuộc tài khoản đích.
5. Bản sao đích tuân theo cấu hình vòng đời và khóa bảo vệ được áp dụng cho vault đó.

Copy action có thể sao chép trong cùng Region sang tài khoản khác, sang Region khác hoặc kết hợp cả hai nếu loại tài nguyên và tính năng hỗ trợ. Hãy kiểm tra giới hạn của loại tài nguyên cụ thể trước khi thiết kế chuỗi copy.

Sao chép là một tác vụ riêng với backup job ban đầu. Vì vậy cần giám sát trạng thái copy job, thời gian hoàn tất và recovery point tại vault đích. Một backup job thành công ở nguồn không chứng minh bản sao liên tài khoản đã hoàn tất.

### 5.3. Chuẩn bị vault đích

Trước khi bật copy action:

- Tạo backup vault ở đúng tài khoản và Region đích.
- Chọn KMS key phù hợp với yêu cầu mã hóa và chia sẻ liên tài khoản.
- Thiết lập vault access policy chỉ cho phép tài khoản hoặc role nguồn đã xác định sao chép vào vault.
- Bật cấu hình cross-account backup cần thiết trong AWS Backup theo hướng dẫn của dịch vụ.
- Xác nhận tài khoản nguồn và tài khoản đích thuộc cùng AWS Organization, theo điều kiện của tính năng cross-account backup.
- Kiểm tra loại tài nguyên và Region có hỗ trợ sao chép liên tài khoản.

Tên vault có thể giống nhau ở nhiều tài khoản, nhưng ARN phải chỉ đúng Region và account ID đích. Không dùng ARN của vault nguồn trong copy action khi mục tiêu là một tài khoản lưu trữ riêng.

### 5.4. Vault access policy

Vault access policy là resource-based policy gắn trực tiếp vào backup vault đích. Policy này quyết định principal bên ngoài tài khoản vault có thể thực hiện hành động nào trên vault.

Ví dụ rút gọn dưới đây minh họa việc cho phép tài khoản nguồn chỉ định sao chép recovery point vào vault đích:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:root"
      },
      "Action": "backup:CopyIntoBackupVault",
      "Resource": "*"
    }
  ]
}
~~~

**111122223333** là account ID giả định của tài khoản nguồn. Trong môi trường thật, cần thay bằng account ID hoặc principal cụ thể theo mô hình quản trị. Có thể thu hẹp quyền vào role chuyên dùng cho AWS Backup thay vì cấp cho toàn bộ principal trong tài khoản nguồn, nếu thiết kế IAM và luồng dịch vụ hỗ trợ.

Resource-based policy ở vault đích chỉ là một phần của kiểm soát truy cập. Principal thực hiện copy còn cần identity policy phù hợp ở tài khoản nguồn; AWS Backup service role cần quyền thao tác với tài nguyên; và KMS key policy phải cho phép các thao tác mã hóa/giải mã cần thiết. Một policy cho phép **backup:CopyIntoBackupVault** không tự cấp quyền sử dụng KMS key.

### 5.5. KMS và mã hóa bản sao

AWS Backup mã hóa recovery point theo cơ chế của loại tài nguyên và cấu hình vault. Khi sao chép liên tài khoản, cần xem xét KMS key của recovery point nguồn và KMS key dùng cho bản sao đích.

Các nguyên tắc quan trọng:

- Ưu tiên customer managed KMS key ở tài khoản lưu trữ khi cần kiểm soát chính sách khóa và quyền truy cập liên tài khoản.
- Cấu hình key policy và IAM policy để AWS Backup cùng các role được chỉ định có quyền sử dụng key theo yêu cầu của luồng copy/restore.
- Kiểm tra key ở đúng Region; KMS key là tài nguyên theo Region.
- Theo dõi trạng thái key, lịch xoay vòng, quyền quản trị và quy trình phục hồi khi key bị vô hiệu hóa.
- Không xóa KMS key còn cần thiết để giải mã recovery point. Bản sao lưu có thể tồn tại nhưng không thể khôi phục nếu mất quyền hoặc key cần dùng.

Một số loại tài nguyên có quy tắc mã hóa và copy riêng. Không suy rộng rằng mọi recovery point đều có thể đổi key theo cùng một cách. Hãy kiểm tra hướng dẫn mã hóa của loại tài nguyên đó và thử restore từ bản sao đích.

## 6. Bảo vệ bản sao lưu khỏi bị xóa hoặc sửa đổi

### 6.1. Phân tách quyền

Tài khoản workload nên có quyền tạo backup theo policy nhưng không nên có quyền quản trị vault lưu trữ ở tài khoản khác. Tài khoản vault nên giới hạn quyền xóa recovery point, thay đổi vault policy, quản lý KMS key và vô hiệu hóa cơ chế bảo vệ.

Có thể phân tách vai trò:

- Backup operator theo dõi job và xử lý lỗi thông thường.
- Backup administrator quản lý policy và phạm vi tài khoản.
- Security administrator quản lý quyền, kiểm soát truy cập và giám sát thay đổi.
- Recovery operator thực hiện restore theo quy trình đã phê duyệt.

Tách quyền giúp giảm khả năng một credential bị lộ vừa xóa workload, vừa xóa được mọi bản sao.

### 6.2. AWS Backup Vault Lock

AWS Backup Vault Lock giúp áp dụng các giới hạn lưu giữ cho recovery point trong vault. Khi cấu hình, cần xác định:

- Thời hạn lưu giữ tối thiểu.
- Thời hạn lưu giữ tối đa nếu tổ chức cần giới hạn.
- Chế độ khóa phù hợp với yêu cầu quản trị.
- Quy trình kiểm tra trước khi khóa ở chế độ nghiêm ngặt.

Vault Lock có thể giúp bảo vệ recovery point trước thao tác xóa hoặc rút ngắn thời hạn lưu giữ trái với quy tắc. Ở chế độ Compliance, sau khi thời gian thử nghiệm cấu hình kết thúc và khóa có hiệu lực, việc thay đổi hoặc gỡ khóa bị hạn chế rất nghiêm ngặt. Vì vậy phải thử nghiệm thời hạn, kiểm tra yêu cầu pháp lý và đánh giá chi phí trước khi bật chế độ này cho vault sản xuất.

### 6.3. Logical air-gapped vault

Với workload quan trọng, tổ chức có thể đánh giá AWS Backup logically air-gapped vault như một lựa chọn lưu trữ cách ly. Tính năng này cung cấp lớp bảo vệ bổ sung cho recovery point và có thể hỗ trợ chia sẻ hoặc khôi phục theo các cơ chế được dịch vụ hỗ trợ.

Không nên đưa tính năng này vào kiến trúc chỉ vì tên gọi. Hãy xác minh loại tài nguyên, Region, mô hình chia sẻ, yêu cầu mã hóa, thời gian khôi phục và chi phí. Thực hiện restore thử nghiệm để chắc chắn bản sao cách ly đáp ứng RTO.

### 6.4. Bảo vệ tài khoản lưu trữ

Tài khoản vault cần được bảo vệ như một thành phần hạ tầng trọng yếu:

- Bật MFA cho người dùng có quyền truy cập tương tác.
- Dùng role tạm thời và hạn chế credential dài hạn.
- Giới hạn principal được phép sửa vault policy hoặc KMS key policy.
- Ghi nhận thay đổi qua CloudTrail và gửi log tới nơi lưu trữ có quyền quản trị độc lập.
- Phát hiện thao tác xóa vault, recovery point, key hoặc thay đổi quyền bất thường.
- Duy trì quy trình break-glass được kiểm soát và kiểm tra định kỳ.

## 7. Ví dụ thiết kế: sao lưu workload Production sang tài khoản vault

### 7.1. Bối cảnh

Một công ty có nhiều tài khoản AWS theo OU. Ứng dụng Production chạy ở **ap-southeast-1**, sử dụng EC2 và EBS. Nhóm nền tảng muốn áp dụng lịch backup thống nhất, lưu bản sao tại tài khoản ứng dụng trong 35 ngày và giữ một bản sao ở tài khoản vault riêng.

Các tài khoản minh họa:

| Tài khoản | Vai trò |
|---|---|
| **111122223333** | Workload Production |
| **444455556666** | Backup vault account |
| **777788889999** | Backup administrator account |

Các ID trên chỉ là giá trị giả định. Kiến trúc thực tế phải thay bằng account ID trong AWS Organizations của tổ chức.

### 7.2. Thiết kế chính sách

Nhóm nền tảng tạo OU Production và gắn backup policy với các thuộc tính:

- Region: **ap-southeast-1**.
- Selection: EBS volume thuộc phạm vi Production hoặc có tag backup theo chuẩn.
- Lịch: hằng ngày.
- Vault nguồn: **OrgDailyVault** trong tài khoản workload.
- Lưu giữ nguồn: 35 ngày.
- Copy action: sao chép recovery point sang vault đích trong tài khoản **444455556666**.
- Lưu giữ đích: theo yêu cầu phục hồi và chính sách lưu trữ của tổ chức.

Policy được triển khai trước ở một tài khoản thử nghiệm. Nhóm kiểm tra effective policy, backup plan được tạo, danh sách EBS volume được chọn và backup job đầu tiên. Sau khi xác nhận, policy mới được áp dụng cho toàn OU Production.

### 7.3. Cấu hình tài khoản vault

Trong tài khoản **444455556666**, nhóm bảo mật:

1. Tạo vault **ProductionArchiveVault** tại **ap-southeast-1**.
2. Tạo hoặc chọn customer managed KMS key theo yêu cầu mã hóa.
3. Gắn vault access policy cho phép principal của tài khoản nguồn sao chép vào vault.
4. Cấu hình quyền IAM và KMS cần thiết cho AWS Backup.
5. Áp dụng Vault Lock nếu yêu cầu lưu giữ bất biến đã được phê duyệt.
6. Bật giám sát thay đổi vault, key và recovery point.

Copy action trong backup rule cần trỏ tới ARN dạng:

~~~text
arn:aws:backup:ap-southeast-1:444455556666:backup-vault:ProductionArchiveVault
~~~

ARN trên chỉ minh họa cấu trúc: dịch vụ, Region, account ID, loại tài nguyên và tên vault. Hãy kiểm tra ARN thực tế trong tài khoản đích trước khi đưa vào policy.

### 7.4. Theo dõi và xác minh

Sau khi chạy:

1. Kiểm tra backup job ở tài khoản nguồn có trạng thái hoàn tất.
2. Kiểm tra copy job có hoàn tất riêng biệt.
3. Mở tài khoản vault và xác nhận recovery point xuất hiện đúng vault, Region và thời gian.
4. Kiểm tra encryption key và vòng đời của recovery point.
5. Thực hiện restore thử nghiệm từ bản sao trong tài khoản vault.
6. Ghi lại thời gian khôi phục, các bước thủ công và lỗi phát sinh để so sánh với RTO.

Chỉ khi bản sao đích có thể khôi phục và ứng dụng hoạt động sau restore, tổ chức mới có bằng chứng rằng chuỗi backup liên tài khoản đáp ứng mục tiêu phục hồi.

## 8. Kiểm thử khôi phục và vận hành liên tục

### 8.1. Backup thành công chưa đủ

Backup job thành công chỉ cho biết dịch vụ đã hoàn thành tác vụ tạo bản sao theo trạng thái của job. Nó không chứng minh ứng dụng có thể khởi động, dữ liệu nhất quán hoặc người vận hành có đủ quyền để restore trong tình huống khẩn cấp.

Một kế hoạch kiểm thử cần xác minh:

- Recovery point có tồn tại và thuộc đúng tài khoản, Region, vault.
- Role phục hồi có thể truy cập recovery point và KMS key.
- Tài nguyên được khôi phục có cấu hình mạng, IAM và phụ thuộc cần thiết.
- Dữ liệu ứng dụng có thể đọc và đáp ứng kiểm tra nhất quán.
- Thời gian restore và bước chuyển đổi đáp ứng RTO.
- Quy trình có thể thực hiện khi tài khoản nguồn không khả dụng.

### 8.2. Kiểm thử theo loại tài nguyên

Không phải mọi loại tài nguyên có cùng quy trình restore. EBS volume có thể cần gắn vào EC2 instance; RDS cần kiểm tra endpoint, parameter group và kết nối ứng dụng; DynamoDB cần xác minh bảng, quyền và dữ liệu; EFS cần xác minh mount target và quyền truy cập.

Hãy xây dựng runbook riêng cho từng nhóm workload. Runbook nên chỉ rõ tài khoản thực hiện, Region, vault, recovery point, KMS key, role, hạ tầng đích, bước kiểm tra và tiêu chí kết thúc.

### 8.3. AWS Backup restore testing

Với loại tài nguyên được hỗ trợ, có thể dùng AWS Backup restore testing để lên lịch kiểm tra khôi phục. Kế hoạch restore testing xác định tần suất kiểm tra, phạm vi recovery point và cách đánh giá kết quả. Cần kiểm tra loại tài nguyên, Region và cấu hình được hỗ trợ trước khi đưa vào vận hành.

Restore testing nên chạy trong tài khoản hoặc VPC thử nghiệm có kiểm soát. Đặt giới hạn tài nguyên và dọn dẹp theo quy trình để tránh phát sinh chi phí ngoài dự kiến. Không dùng dữ liệu nhạy cảm trong môi trường thử nghiệm nếu chưa có biện pháp bảo vệ tương ứng.

### 8.4. Giám sát backup và copy job

Nên theo dõi ít nhất:

- Backup job thất bại, bị hủy hoặc chạy quá thời gian dự kiến.
- Copy job thất bại hoặc không tạo được recovery point ở vault đích.
- Tài nguyên nằm ngoài backup selection.
- Thay đổi backup policy, backup plan, selection hoặc vault policy.
- Thay đổi KMS key, key policy hoặc trạng thái key.
- Recovery point sắp hết hạn hoặc không đáp ứng thời hạn lưu giữ.
- Restore test thất bại hoặc vượt RTO.

AWS Backup cung cấp trạng thái job và khả năng tích hợp với các dịch vụ giám sát, sự kiện AWS. Có thể dùng EventBridge để định tuyến sự kiện job tới SNS, Lambda hoặc hệ thống xử lý sự cố. CloudTrail giúp truy vết hoạt động quản trị và thay đổi quyền. Cần kiểm tra luồng cảnh báo bằng một tình huống thử nghiệm, không chỉ dựa vào việc rule đã được tạo.

## 9. Chi phí và tối ưu

### 9.1. Các thành phần chi phí

Chi phí của kiến trúc backup có thể bao gồm:

- Dung lượng backup được lưu trong vault nguồn và vault đích.
- Các bản sao liên Region hoặc liên tài khoản.
- Phí lưu trữ theo lớp hoặc loại recovery point của từng dịch vụ.
- Chi phí truy xuất, restore hoặc chuyển dữ liệu nếu dịch vụ áp dụng.
- Chi phí KMS và các thành phần hỗ trợ liên quan.
- Tài nguyên tạm được tạo trong quá trình restore testing.

Một recovery point được sao chép tạo thêm dữ liệu lưu trữ ở đích. Việc giữ bản sao trong nhiều tài khoản và Region tăng khả năng phục hồi nhưng cũng tăng chi phí. Hãy tính chi phí theo số lượng tài nguyên, tần suất, thời hạn lưu giữ, tỷ lệ thay đổi dữ liệu và số bản sao.

### 9.2. Chính sách lưu giữ theo mức độ quan trọng

Không nên áp dụng thời hạn dài nhất cho mọi tài nguyên. Có thể phân nhóm:

| Nhóm workload | Ví dụ lịch | Mục tiêu lưu giữ |
|---|---|---|
| Production quan trọng | Hằng ngày và bản sao định kỳ | Đáp ứng yêu cầu khôi phục và kiểm toán |
| Production tiêu chuẩn | Hằng ngày | Phục hồi lỗi vận hành phổ biến |
| Development/Test | Hằng tuần hoặc trước mốc thay đổi | Giảm chi phí nhưng vẫn hỗ trợ khôi phục cần thiết |
| Dữ liệu cần lưu lâu | Theo lịch riêng và yêu cầu pháp lý | Đáp ứng thời hạn lưu trữ được phê duyệt |

Các lịch trên là ví dụ thiết kế. Tần suất và thời hạn phải được xác định theo RPO/RTO, quy định dữ liệu, khả năng hỗ trợ của loại tài nguyên và giá AWS hiện hành.

### 9.3. Kiểm soát tăng trưởng dữ liệu

Để kiểm soát chi phí:

- Loại bỏ selection không còn cần thiết sau khi workload được ngừng hoạt động.
- Rà soát backup plan trùng lặp giữa policy tổ chức và plan cục bộ.
- Đặt lifecycle rõ ràng cho recovery point nguồn và bản sao đích.
- Đánh giá việc dùng cold storage khi loại tài nguyên và thời gian lưu giữ hỗ trợ.
- Theo dõi dung lượng theo tài khoản, Region và vault.
- Dùng AWS Cost Explorer, AWS Budgets và báo cáo chi phí để phát hiện xu hướng bất thường.

Không giảm thời hạn lưu giữ chỉ để xử lý vượt ngân sách khi chưa đánh giá tác động đến yêu cầu phục hồi hoặc tuân thủ.

## 10. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ gắn policy ở root nhưng không kiểm tra effective policy | Tài khoản con có thể nhận cấu hình khác dự kiến | Kiểm tra effective policy và backup plan tại tài khoản thành viên |
| Dùng tag nhưng tài nguyên không có tag hoặc sai giá trị | Tài nguyên bị bỏ khỏi selection | Chuẩn hóa tag và kiểm tra danh sách tài nguyên được chọn |
| Backup role không tồn tại hoặc thiếu quyền | Backup job thất bại | Tạo role đúng trust policy và quyền tối thiểu cho loại tài nguyên |
| Vault đích chưa cho phép copy | Copy job thất bại dù backup nguồn thành công | Kiểm tra vault access policy và IAM policy của principal nguồn |
| KMS key không cho phép thao tác cần thiết | Không thể copy hoặc restore recovery point | Kiểm tra key policy, IAM policy, Region và trạng thái key |
| Nhầm backup job với copy job | Không phát hiện bản sao ngoài tài khoản chưa được tạo | Theo dõi hai loại job và xác nhận recovery point tại vault đích |
| Cho phép tài khoản nguồn quản trị vault đích | Kẻ tấn công ở nguồn có thể tác động bản sao | Tách tài khoản, giới hạn quyền và xem xét Vault Lock |
| Bật Vault Lock nghiêm ngặt mà chưa thử nghiệm | Khó sửa cấu hình lưu giữ khi phát hiện sai | Thử nghiệm, rà soát pháp lý và phê duyệt trước khi khóa |
| Chưa từng restore | Không biết thời gian và tính nhất quán của dữ liệu | Lập lịch restore test và ghi nhận RTO thực tế |
| Chọn lịch theo giờ địa phương nhưng quên UTC | Backup chạy lệch thời điểm hoặc dồn tải | Quy đổi cron sang UTC và phân tán lịch chạy |

## 11. Checklist triển khai backup policy tập trung và liên tài khoản

### Trước khi triển khai

1. Phân loại workload theo mức độ quan trọng, RPO và RTO.
2. Xác định tài khoản, OU và Region cần được bảo vệ.
3. Kiểm tra loại tài nguyên có được AWS Backup hỗ trợ ở Region mục tiêu.
4. Chuẩn hóa tag và selection.
5. Xác định management account, delegated administrator và backup vault account.
6. Thiết kế lịch, lifecycle, vault và copy action.
7. Chuẩn bị IAM role, vault access policy và KMS key policy.
8. Đánh giá yêu cầu Vault Lock và thời hạn lưu giữ.

### Trong khi triển khai

1. Bật trusted access và cấu hình delegated administrator nếu cần.
2. Thử policy trên một OU hoặc tài khoản giới hạn.
3. Kiểm tra effective policy và backup plan được tạo.
4. Kiểm tra backup selection có đúng tài nguyên.
5. Chạy backup job và xác nhận recovery point ở vault nguồn.
6. Chạy copy job và xác nhận recovery point ở vault đích.
7. Kiểm tra mã hóa, quyền truy cập và lifecycle ở cả hai phía.

### Sau khi triển khai

1. Lên lịch restore test theo mức độ quan trọng của workload.
2. Theo dõi backup job, copy job và thay đổi policy.
3. Rà soát tài nguyên chưa được backup hoặc không còn thuộc selection.
4. Kiểm tra quyền truy cập vault và KMS key định kỳ.
5. Đối chiếu chi phí thực tế với ngân sách và thời hạn lưu giữ.
6. Cập nhật runbook khi thay đổi tài khoản, Region, loại tài nguyên hoặc yêu cầu phục hồi.

## 12. Kết luận

Backup policy tập trung giúp tổ chức áp dụng quy tắc sao lưu nhất quán trên nhiều tài khoản AWS thông qua AWS Organizations. Bằng cách tổ chức policy theo root, OU và account, nhóm nền tảng có thể chuẩn hóa lịch, Region, selection và thời hạn lưu giữ, đồng thời dùng effective policy để xác nhận cấu hình cuối cùng ở từng tài khoản.

Sao lưu liên tài khoản tạo thêm lớp bảo vệ khi tài khoản workload bị xâm nhập hoặc gặp sự cố nghiêm trọng. Để luồng copy hoạt động, cần chuẩn bị vault đích, vault access policy, IAM role và KMS key phù hợp; sau đó theo dõi copy job độc lập với backup job nguồn. Tách quyền quản trị và bảo vệ vault giúp giảm khả năng một sự cố ở tài khoản nguồn phá hủy bản sao dự phòng.

Một chiến lược backup chỉ đáng tin cậy khi tổ chức khôi phục được dữ liệu và ứng dụng trong thời gian mục tiêu. Vì vậy, hãy kết hợp policy tập trung, bản sao ở tài khoản riêng, kiểm soát lưu giữ, giám sát liên tục và restore testing định kỳ để biến backup thành năng lực phục hồi có thể kiểm chứng.
