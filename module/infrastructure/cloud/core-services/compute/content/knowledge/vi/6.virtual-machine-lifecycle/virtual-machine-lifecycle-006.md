# Khóa chống xóa và bảo vệ máy khỏi thao tác ngoài ý muốn

## Mục tiêu bài học

Máy ảo có thể bị xóa nhầm trong lúc dọn dẹp tài nguyên, thay đổi cấu hình, chạy tự động hóa hoặc xử lý sự cố. Với máy chủ production, một thao tác xóa có thể làm gián đoạn dịch vụ, mất dữ liệu chưa sao lưu và kéo theo việc tạo lại nhiều tài nguyên phụ thuộc.

Các nền tảng đám mây cung cấp những cơ chế như deletion protection, termination protection và resource lock để giảm nguy cơ thao tác phá hủy ngoài ý muốn. Những cơ chế này cần được kết hợp với quyền truy cập phù hợp, quy trình thay đổi và backup.

Sau bài học này, bạn có thể:

- Phân biệt khóa chống xóa với các biện pháp bảo vệ dữ liệu và kiểm soát quyền.
- Giải thích phạm vi và giới hạn của deletion protection, termination protection và resource lock.
- Bật, kiểm tra và gỡ khóa theo quy trình có kiểm soát trên các nền tảng đám mây phổ biến.
- Kết hợp bảo vệ ở cấp tài nguyên, IAM/RBAC, hạ tầng dưới dạng mã và quy trình vận hành.
- Lập kế hoạch thay thế hoặc xóa máy ảo an toàn khi thao tác đó thực sự cần thiết.

## 1. Vì sao cần bảo vệ máy ảo?

Trong vòng đời máy ảo, nhóm vận hành thường tạo, khởi động, dừng, thay đổi cấu hình, sao lưu, thay thế và xóa máy. Một số thao tác có thể gây hậu quả lớn nếu chọn nhầm tài nguyên hoặc chạy nhầm lệnh.

Các tình huống thường gặp:

- Người vận hành chọn nhầm máy production khi dọn các máy thử nghiệm đã hết hạn.
- Script tự động xóa máy theo tag hoặc thời gian sống (TTL) nhưng bộ lọc bị cấu hình sai.
- Pipeline triển khai tạo thay thế tài nguyên vì thay đổi thuộc tính không tương thích.
- Nhóm vận hành xóa máy ảo mà không nhận ra boot disk hoặc data disk có chính sách xóa kèm theo.
- Một tài khoản có quyền quá rộng bị sử dụng nhầm hoặc bị xâm phạm.
- Hệ thống autoscaling thu hẹp nhóm máy và chọn nhầm instance cần giữ lại.
- Thao tác khắc phục sự cố bị thực hiện vội vàng, dẫn đến xóa máy hoặc đĩa thay vì dừng dịch vụ.

Bảo vệ máy ảo nhằm giảm xác suất một thao tác nguy hiểm được thực hiện mà không có chủ ý và phê duyệt phù hợp. Cơ chế bảo vệ cần tương xứng với mức độ quan trọng của workload. Máy thử nghiệm tạm thời có thể chỉ cần tag và thời hạn tự hủy; máy production chứa dữ liệu quan trọng cần nhiều lớp kiểm soát hơn.

## 2. Phân biệt các thao tác trong vòng đời

Không phải mọi thao tác ảnh hưởng đến máy ảo đều giống nhau. Trước khi chọn cơ chế bảo vệ, cần xác định hành động nào phải được kiểm soát.

| Thao tác | Kết quả | Rủi ro cần lưu ý |
|---|---|---|
| Stop / Deallocate | Tắt máy, thường vẫn giữ cấu hình và đĩa được giữ lại | Dịch vụ ngừng hoạt động; một số loại tài nguyên hoặc chi phí vẫn có thể tồn tại |
| Restart / Reboot | Khởi động lại hệ điều hành hoặc máy ảo | Gián đoạn ngắn, tiến trình đang chạy bị ảnh hưởng |
| Resize | Thay đổi loại máy hoặc tài nguyên CPU/RAM | Có thể cần dừng máy; cấu hình hoặc khả năng tương thích có thể thay đổi |
| Reimage / Rebuild | Tạo lại hệ điều hành hoặc thay thế máy từ image | Dữ liệu trên đĩa hệ điều hành có thể bị mất |
| Detach disk | Tháo volume khỏi máy | Ứng dụng mất quyền truy cập dữ liệu; có thể gây lỗi hoặc hỏng dữ liệu nếu tháo khi đang ghi |
| Delete / Terminate | Xóa tài nguyên máy ảo | Có thể làm mất máy, IP tạm thời và các tài nguyên phụ thuộc theo chính sách nền tảng |
| Delete disk / snapshot | Xóa dữ liệu lưu trữ hoặc điểm khôi phục | Có thể gây mất dữ liệu không thể phục hồi |

**Deletion protection** hoặc **termination protection** chủ yếu ngăn thao tác xóa máy thông qua các API quản lý được nền tảng bảo vệ. Cơ chế này không mặc nhiên ngăn stop, reboot, resize, thay đổi hệ điều hành, thao tác bên trong guest OS hoặc xóa một volume riêng.

Nếu mục tiêu là bảo vệ dữ liệu, cần thêm backup, snapshot, chính sách lưu giữ và quyền bảo vệ riêng cho disk hoặc snapshot. Nếu mục tiêu là duy trì tính sẵn sàng, cần thêm dự phòng, health check và quy trình failover.

## 3. Các lớp bảo vệ

Một thiết kế tốt thường sử dụng nhiều lớp. Nếu một lớp bị cấu hình sai hoặc bị người có quyền cao vượt qua, các lớp còn lại vẫn có thể giảm thiểu rủi ro.

### 3.1. Bảo vệ ở cấp tài nguyên

Đây là thuộc tính hoặc cờ được gắn trực tiếp vào máy ảo để yêu cầu nền tảng chặn thao tác xóa. Ví dụ:

- AWS EC2 termination protection.
- Azure resource lock loại CanNotDelete.
- Google Compute Engine deletion protection.

Ưu điểm là trạng thái bảo vệ gắn với tài nguyên và thường có thể kiểm tra bằng console, CLI hoặc API. Tuy nhiên, mỗi nền tảng có phạm vi và ngoại lệ riêng. Cần đọc đúng hành vi của dịch vụ đang dùng, đặc biệt khi máy thuộc nhóm autoscaling hoặc được quản lý bởi một dịch vụ cấp cao hơn.

### 3.2. Khóa ở phạm vi nhóm tài nguyên

Một số nền tảng hỗ trợ khóa tại resource group, project hoặc một phạm vi quản lý. Khóa ở phạm vi cha có thể áp dụng cho nhiều tài nguyên con, tùy mô hình của nhà cung cấp.

Cách này hữu ích khi cần bảo vệ đồng thời máy ảo, đĩa và các tài nguyên liên quan. Tuy nhiên, phạm vi khóa rộng có thể cản trở pipeline hợp lệ hoặc thao tác vận hành định kỳ. Cần xác định chính xác tài nguyên nào kế thừa khóa và thử nghiệm trước khi áp dụng trên môi trường production.

### 3.3. Kiểm soát quyền bằng IAM/RBAC

IAM (Identity and Access Management) và RBAC (Role-Based Access Control) xác định ai được phép thực hiện hành động nào.

Một cấu hình tốt nên:

- Cấp quyền theo vai trò và trách nhiệm công việc.
- Tách quyền vận hành thông thường khỏi quyền xóa tài nguyên.
- Chỉ cấp quyền xóa máy, đĩa hoặc snapshot cho nhóm thực sự cần.
- Dùng quyền tạm thời có thời hạn cho thao tác đặc biệt.
- Yêu cầu xác thực mạnh và phê duyệt bổ sung cho tài khoản có quyền cao.
- Rà soát định kỳ tài khoản, service account, role assignment và access key.

Khóa chống xóa ở cấp tài nguyên và IAM bổ sung cho nhau. Một người có quyền thay đổi thuộc tính bảo vệ có thể gỡ khóa rồi xóa máy; vì vậy quyền gỡ khóa cũng cần được kiểm soát.

### 3.4. Guardrail trong Infrastructure as Code

Khi máy ảo được quản lý bằng Terraform hoặc công cụ Infrastructure as Code (IaC), có thể thêm quy tắc để ngăn kế hoạch triển khai vô tình phá hủy tài nguyên.

Ví dụ Terraform:

~~~hcl
resource "aws_instance" "production" {
  ami                    = var.ami_id
  instance_type          = "m6i.large"
  disable_api_termination = true

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Environment = "production"
    ManagedBy   = "terraform"
  }
}
~~~

Trong ví dụ này:

- disable_api_termination bật cơ chế termination protection của EC2.
- lifecycle.prevent_destroy yêu cầu Terraform từ chối kế hoạch có thao tác destroy đối với resource block còn tồn tại trong cấu hình.

prevent_destroy là guardrail của Terraform, không phải khóa của nền tảng cloud. Nếu resource block bị xóa khỏi cấu hình, quy tắc lifecycle đó cũng không còn được áp dụng cho resource trong cấu hình hiện tại. Vì vậy, cần kết hợp review plan, kiểm soát quyền và cơ chế bảo vệ native của nền tảng.

Đối với tài nguyên quan trọng, pipeline nên hiển thị rõ các thao tác destroy/replace và yêu cầu người có thẩm quyền phê duyệt trước khi áp dụng.

### 3.5. Backup và khả năng khôi phục

Khóa chống xóa không phải bản sao lưu. Nó chỉ giảm khả năng thực hiện một loại thao tác quản lý. Nó không bảo vệ dữ liệu khỏi lỗi ứng dụng, mã độc, thao tác xóa file bên trong hệ điều hành, hỏng filesystem, lỗi người dùng có quyền ghi hoặc sự cố vùng.

Cần xác định:

- Dữ liệu nào nằm trên boot disk, data disk, database hay object storage.
- Tần suất backup và thời gian lưu giữ.
- Recovery Point Objective (RPO): mức mất dữ liệu tối đa có thể chấp nhận.
- Recovery Time Objective (RTO): thời gian khôi phục tối đa mong muốn.
- Ai có quyền xóa backup và snapshot.
- Cách kiểm thử khôi phục và xác minh dữ liệu sau phục hồi.

Backup nên được bảo vệ bằng quyền riêng, chính sách lưu giữ và cơ chế chống xóa phù hợp. Nếu backup nằm cùng tài khoản và cùng quyền quản trị với máy nguồn, một tài khoản bị xâm phạm có thể xóa cả hai.

## 4. AWS EC2: termination protection

Amazon EC2 hỗ trợ thuộc tính termination protection cho instance. Khi bật, yêu cầu terminate instance qua các thao tác quản lý thông thường sẽ bị chặn cho đến khi thuộc tính này được tắt.

Bật termination protection bằng AWS CLI:

~~~bash
aws ec2 modify-instance-attribute \
  --instance-id i-0123456789abcdef0 \
  --disable-api-termination
~~~

Kiểm tra trạng thái:

~~~bash
aws ec2 describe-instance-attribute \
  --instance-id i-0123456789abcdef0 \
  --attribute disableApiTermination
~~~

Khi đã được phê duyệt để xóa máy, tắt bảo vệ:

~~~bash
aws ec2 modify-instance-attribute \
  --instance-id i-0123456789abcdef0 \
  --no-disable-api-termination
~~~

Sau đó mới thực hiện thao tác terminate theo quy trình đã duyệt.

Một số điểm cần nhớ:

- Termination protection kiểm soát yêu cầu terminate instance qua API quản lý; nó không phải cơ chế backup dữ liệu.
- Nó không thay thế bảo vệ riêng cho EBS volume, snapshot, Elastic IP hoặc tài nguyên phụ thuộc.
- Với Auto Scaling group, cần cấu hình và hiểu thêm chính sách instance scale-in protection. Termination protection của EC2 không thay thế cơ chế bảo vệ instance khỏi lựa chọn scale-in của Auto Scaling.
- Các dịch vụ AWS có thể quản lý vòng đời instance theo quy tắc riêng. Hãy kiểm tra hành vi của dịch vụ cấp cao hơn trước khi dựa vào cờ bảo vệ.
- Người có quyền phù hợp có thể tắt thuộc tính bảo vệ. Quyền gọi thao tác thay đổi thuộc tính cũng cần được giới hạn.

## 5. Azure: resource locks

Azure cung cấp resource lock để hạn chế thao tác trên tài nguyên Resource Manager. Hai loại khóa phổ biến là:

| Loại khóa | Tác dụng chính | Khi sử dụng |
|---|---|---|
| CanNotDelete | Cho phép đọc và cập nhật theo quyền hiện có nhưng chặn xóa tài nguyên trong phạm vi khóa | Muốn giữ máy ảo hoặc nhóm tài nguyên tồn tại |
| ReadOnly | Chặn thao tác ghi trên tài nguyên trong phạm vi khóa | Muốn hạn chế thay đổi cấu hình trong giai đoạn đặc biệt |

Với mục tiêu chống xóa máy ảo, CanNotDelete thường phù hợp hơn ReadOnly. ReadOnly có thể chặn cả những thao tác cập nhật hợp lệ và gây ảnh hưởng đến hoạt động vận hành.

Ví dụ tạo khóa CanNotDelete cho một VM bằng Azure CLI:

~~~bash
az lock create \
  --name protect-prod-vm \
  --lock-type CanNotDelete \
  --resource-group rg-prod \
  --resource-name vm-prod-01 \
  --resource-type Microsoft.Compute/virtualMachines
~~~

Liệt kê khóa trong resource group:

~~~bash
az lock list --resource-group rg-prod --output table
~~~

Khi cần xóa máy sau phê duyệt, người có quyền quản lý lock có thể gỡ khóa:

~~~bash
az lock delete \
  --name protect-prod-vm \
  --resource-group rg-prod
~~~

Sau khi gỡ khóa, thực hiện xóa máy theo quy trình thay đổi đã duyệt.

Lưu ý khi dùng Azure locks:

- Khóa ở resource group có thể được kế thừa bởi tài nguyên con; khóa ở một VM chỉ có phạm vi tại resource đó và không tự động bảo vệ mọi tài nguyên liên quan.
- Nếu cần bảo vệ cả VM, disk và các tài nguyên quan trọng khác, phải xác định phạm vi lock và kiểm tra tài nguyên nào được kế thừa.
- Resource lock hoạt động ở lớp quản lý Azure Resource Manager. Nó không ngăn người dùng có quyền trong hệ điều hành xóa file hoặc sửa dữ liệu bên trong VM.
- Khóa có thể ảnh hưởng đến automation, resize, cập nhật hoặc các thao tác ghi hợp lệ. Hãy thử trên môi trường không production và lập danh sách ngoại lệ vận hành trước.
- Người có quyền quản lý khóa vẫn có thể xóa khóa. Cần kiểm soát quyền tạo, sửa và xóa lock.

## 6. Google Compute Engine: deletion protection

Google Compute Engine hỗ trợ deletion protection cho VM. Khi bật thuộc tính này, thao tác xóa instance bị chặn cho đến khi protection được tắt.

Bật deletion protection:

~~~bash
gcloud compute instances update vm-prod-01 \
  --deletion-protection
~~~

Kiểm tra cấu hình instance:

~~~bash
gcloud compute instances describe vm-prod-01 \
  --zone asia-southeast1-b
~~~

Trong kết quả, kiểm tra trường deletionProtection.

Khi đã được phê duyệt để xóa:

~~~bash
gcloud compute instances update vm-prod-01 \
  --no-deletion-protection \
  --zone asia-southeast1-b
~~~

Sau đó mới thực hiện lệnh xóa instance.

Cần lưu ý:

- Deletion protection áp dụng cho instance được cấu hình; không mặc nhiên bảo vệ mọi disk, snapshot hoặc tài nguyên khác.
- Cần giới hạn quyền cập nhật thuộc tính deletion protection và quyền xóa instance.
- Nếu VM thuộc một nhóm được quản lý hoặc quy trình tự động hóa, hãy kiểm tra cách dịch vụ cấp cao hơn xử lý việc thay thế và xóa instance.
- Bảo vệ VM không thay thế backup cho dữ liệu trên boot disk hoặc persistent disk.

## 7. Chọn phạm vi bảo vệ phù hợp

Không nên bật cùng một loại khóa cho mọi tài nguyên mà không xem xét cách chúng được vận hành. Cần cân bằng giữa mức độ bảo vệ và khả năng thực hiện thay đổi hợp lệ.

| Loại máy | Cơ chế gợi ý | Lý do |
|---|---|---|
| Máy production chạy dịch vụ quan trọng | Deletion/termination protection, IAM hạn chế quyền xóa, backup và quy trình phê duyệt | Hậu quả xóa nhầm lớn |
| Máy chủ cơ sở dữ liệu | Bảo vệ VM và disk, backup có lưu giữ, quyền xóa tách biệt | Cần bảo vệ cả compute lẫn dữ liệu |
| Máy bastion hoặc máy quản trị | Bảo vệ xóa, MFA, quyền truy cập chặt và audit | Mất máy có thể ảnh hưởng đường quản trị |
| Máy staging | Bảo vệ theo thời hạn phát hành hoặc giai đoạn kiểm thử | Cần giữ ổn định trong đợt kiểm thử nhưng vẫn có thể dọn định kỳ |
| Máy development dùng ngắn hạn | Tag owner/expiry và chính sách dọn dẹp có kiểm soát | Có thể chấp nhận tự động xóa sau thời hạn |
| Instance trong autoscaling group | Bảo vệ ở cấp nhóm và chính sách scale-in phù hợp | Vòng đời instance do bộ điều phối quản lý |

Đối với máy production, có thể áp dụng kết hợp:

1. Bật cơ chế chống xóa native trên VM.
2. Bảo vệ riêng các disk hoặc snapshot quan trọng.
3. Giới hạn quyền terminate/delete và quyền gỡ khóa.
4. Yêu cầu review khi IaC plan có thao tác destroy hoặc replace.
5. Duy trì backup độc lập và kiểm thử phục hồi.
6. Ghi lại người thực hiện, lý do, thời điểm và kết quả của mọi lần thay đổi trạng thái bảo vệ.

## 8. Quy trình xóa máy ảo có kiểm soát

Khóa chống xóa không có nghĩa là máy sẽ không bao giờ được xóa. Máy cũ, máy lỗi hoặc máy cần thay thế vẫn phải được thu hồi theo quy trình. Một quy trình tốt làm rõ lý do, phạm vi và khả năng khôi phục trước khi gỡ khóa.

~~~mermaid
flowchart TD
    A["Yêu cầu xóa hoặc thay thế VM"] --> B["Xác minh đúng tài nguyên và owner"]
    B --> C["Kiểm tra workload, phụ thuộc và dữ liệu"]
    C --> D["Xác nhận backup và phương án rollback"]
    D --> E["Review / phê duyệt thay đổi"]
    E --> F["Tạm gỡ khóa theo quyền được cấp"]
    F --> G["Xóa VM hoặc thực hiện thay thế"]
    G --> H["Xác minh trạng thái disk, IP và tài nguyên liên quan"]
    H --> I["Cập nhật inventory, audit và ticket"]
~~~

Các bước cần thực hiện:

1. **Xác minh định danh:** kiểm tra account/project/subscription, region/zone, tên máy, ID, môi trường và owner. Không chỉ dựa vào tên hiển thị.
2. **Kiểm tra phụ thuộc:** xác định máy đang phục vụ traffic nào, có gắn load balancer, disk, IP, monitoring hoặc job nào không.
3. **Đánh giá dữ liệu:** xác nhận dữ liệu cần giữ, backup gần nhất, khả năng restore và thời gian lưu giữ.
4. **Chọn hành động:** stop, detach, rebuild, replace hay delete. Chọn thao tác ít ảnh hưởng nhất đáp ứng mục tiêu.
5. **Phê duyệt:** yêu cầu người có thẩm quyền xác nhận tài nguyên và thời điểm thực hiện. Với hệ thống quan trọng, nên có người thứ hai review.
6. **Gỡ bảo vệ tạm thời:** chỉ người có quyền phù hợp mới được tắt deletion protection hoặc xóa resource lock. Ghi lại lý do và thời hạn.
7. **Thực hiện và xác minh:** kiểm tra kết quả của thao tác, trạng thái disk, IP, backup và tài nguyên phụ thuộc.
8. **Khôi phục guardrail:** nếu máy vẫn tồn tại hoặc đã tạo máy thay thế, bật lại bảo vệ cho tài nguyên mới theo baseline.
9. **Ghi nhận:** cập nhật inventory, ticket, log thay đổi và thông tin về tài nguyên đã thu hồi.

Đối với thay thế máy production, nên triển khai máy mới từ image/template đã kiểm thử, kiểm tra health check, chuyển traffic theo từng bước rồi mới xóa máy cũ. Cách này tạo cơ hội rollback nếu máy mới không hoạt động đúng.

## 9. Audit và phát hiện thay đổi bất thường

Một cơ chế bảo vệ chỉ có ích khi tổ chức biết trạng thái của nó và phát hiện được lúc nó bị gỡ.

Nên theo dõi:

- Máy production nào chưa bật deletion/termination protection.
- Resource lock nào đã bị xóa hoặc thay đổi.
- Ai đã thay đổi thuộc tính bảo vệ, IAM role hoặc policy.
- Yêu cầu xóa VM, disk, snapshot và backup.
- Thao tác destroy/replace trong pipeline IaC.
- Các thay đổi ngoài quy trình hoặc ngoài khung giờ đã duyệt.

Có thể dùng audit log của nhà cung cấp, event rule, policy compliance hoặc hệ thống SIEM để phát hiện thay đổi. Cảnh báo cần có thông tin tài nguyên, danh tính thực hiện, hành động, thời điểm và đường dẫn runbook xử lý.

Nên rà soát trạng thái bảo vệ theo lịch và sau mỗi lần triển khai lớn. Một dashboard có thể phân loại theo môi trường, owner, mức độ quan trọng và trạng thái guardrail. Các tag như Environment=production hoặc Criticality=high giúp phân loại, nhưng tag chỉ có tác dụng bảo vệ khi được kết hợp với policy hoặc automation có kiểm soát.

## 10. Các giới hạn và hiểu nhầm thường gặp

**Cho rằng khóa chống xóa bảo vệ dữ liệu:** khóa không ngăn lỗi ghi dữ liệu, mã độc, xóa file trong guest OS hoặc hỏng filesystem. Cần backup và kiểm thử restore.

**Cho rằng VM được bảo vệ thì disk cũng được bảo vệ:** disk có thể là tài nguyên độc lập và có chính sách vòng đời riêng. Hãy kiểm tra delete behavior của boot disk và data disk, đồng thời bảo vệ disk/snapshot quan trọng.

**Cho rằng người có quyền quản trị không thể gỡ khóa:** nhiều cơ chế cho phép người có quyền thích hợp tắt protection hoặc xóa lock. Phải giới hạn cả quyền gỡ guardrail.

**Bật ReadOnly cho mọi thứ:** khóa chỉ đọc có thể chặn thao tác cập nhật hợp lệ, gây lỗi cho agent, pipeline và quy trình vận hành. Với mục tiêu chống xóa, hãy cân nhắc khóa chỉ chống xóa trước.

**Quên autoscaling và dịch vụ quản lý:** nhóm máy được quản lý có thể có cơ chế scale-in, thay thế hoặc thu hồi riêng. Kiểm tra chính sách của bộ điều phối thay vì chỉ dựa vào thuộc tính trên từng VM.

**Dùng IaC guardrail như lớp bảo vệ duy nhất:** prevent_destroy giúp ngăn một số kế hoạch Terraform nhưng không chặn thao tác xóa trực tiếp qua console hoặc API. Cần có guardrail ở lớp cloud và kiểm soát quyền.

**Gỡ khóa rồi quên bật lại:** sau bảo trì hoặc thay thế, trạng thái bảo vệ có thể bị bỏ quên. Hãy đưa bước khôi phục guardrail vào checklist và kiểm tra tự động.

**Xem snapshot là backup hoàn chỉnh:** snapshot có thể không nhất quán với ứng dụng đang ghi dữ liệu nếu không phối hợp freeze/quiesce hoặc cơ chế backup phù hợp. Kiểm thử restore ở cấp ứng dụng.

## 11. Checklist bảo vệ máy production

- [ ] Máy đã được phân loại môi trường, mức độ quan trọng và owner.
- [ ] Deletion/termination protection đã bật và được kiểm tra bằng API/CLI.
- [ ] Disk và snapshot quan trọng có chính sách bảo vệ riêng.
- [ ] IAM/RBAC giới hạn quyền xóa VM, disk, snapshot và quyền gỡ khóa.
- [ ] Quyền quản trị nhạy cảm yêu cầu xác thực mạnh và được rà soát.
- [ ] IaC plan có thao tác destroy/replace cần review và phê duyệt.
- [ ] Backup đáp ứng RPO/RTO và đã kiểm thử phục hồi.
- [ ] Có quy trình break-glass cho trường hợp khẩn cấp, kèm audit.
- [ ] Có cảnh báo khi protection hoặc resource lock bị thay đổi.
- [ ] Có checklist gỡ khóa, thực hiện thay đổi và bật lại guardrail.
- [ ] Chính sách autoscaling và dịch vụ quản lý đã được kiểm tra.
- [ ] Inventory phản ánh đúng trạng thái bảo vệ hiện tại.

Khóa chống xóa giúp giảm nguy cơ mất máy do thao tác quản lý ngoài ý muốn. Để bảo vệ workload thực sự, hãy kết hợp guardrail ở cấp tài nguyên, quyền IAM/RBAC, kiểm soát thay đổi bằng IaC, audit và backup độc lập. Khi cần xóa hoặc thay thế, xác minh đúng tài nguyên, đánh giá dữ liệu và phụ thuộc, phê duyệt thao tác, gỡ khóa tạm thời rồi khôi phục chính sách bảo vệ sau khi hoàn tất.
