# Inventory và quản lý phần mềm trên fleet

Một tổ chức có thể vận hành hàng trăm hoặc hàng nghìn máy chủ EC2, máy chủ tại trung tâm dữ liệu và máy ảo ở môi trường khác. Khi số lượng node tăng lên, việc trả lời các câu hỏi như máy nào đang chạy hệ điều hành nào, đã cài phiên bản agent nào, node nào thiếu phần mềm chuẩn hoặc một ứng dụng đang tồn tại ở những môi trường nào trở nên khó khăn nếu phải đăng nhập và kiểm tra thủ công.

AWS Systems Manager cung cấp hai nhóm năng lực có thể kết hợp để giải quyết bài toán này:

- **Inventory** thu thập và lưu metadata về managed node, phần cứng, hệ điều hành, ứng dụng, package và một số cấu hình liên quan. Nhóm vận hành dùng dữ liệu này để tìm kiếm, đối chiếu và lập báo cáo trên fleet.
- **Distributor, Run Command và State Manager** hỗ trợ phân phối, cài đặt, gỡ bỏ và duy trì phần mềm trên các managed node. Nhóm vận hành có thể triển khai một lần hoặc khai báo trạng thái mong muốn để Systems Manager thực thi theo lịch.

Trong phạm vi hệ sinh thái **CLOUD_PROVIDERS_AWS**, đây là cách đưa việc quản lý phần mềm trên EC2 và máy chủ hybrid vào một quy trình có thể lặp lại, kiểm soát bằng IAM, theo dõi qua trạng thái association và đối chiếu với dữ liệu kiểm toán. Mục tiêu của module là giúp người học chọn dịch vụ AWS, thiết kế và triển khai ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí; Inventory và quản lý phần mềm góp phần duy trì baseline vận hành nhất quán trên toàn fleet.

## 1. Inventory và quản lý phần mềm giải quyết vấn đề gì?

Inventory trả lời câu hỏi **fleet hiện đang có những gì**. Ví dụ, đội vận hành có thể tìm các node đang chạy Amazon Linux, xác định máy nào cài Amazon CloudWatch Agent, so sánh phiên bản Java giữa các môi trường hoặc lập danh sách máy chủ có một package dễ bị ảnh hưởng bởi lỗ hổng.

Quản lý phần mềm trả lời câu hỏi **fleet cần có những gì và làm sao đưa nó tới đúng node**. Ví dụ, nhóm nền tảng có thể chuẩn hóa CloudWatch Agent, SSM Agent hoặc một agent bảo mật; triển khai phiên bản được phê duyệt tới các node có tag phù hợp; sau đó duy trì trạng thái cài đặt bằng State Manager.

Hai năng lực bổ trợ nhau:

| Nhu cầu | Năng lực phù hợp | Kết quả |
|---|---|---|
| Biết node đang cài phần mềm nào | Systems Manager Inventory | Dữ liệu phần mềm đã thu thập để truy vấn |
| Cài một package lên một nhóm node | Distributor kết hợp Run Command | Lệnh cài đặt được gửi tới các managed node mục tiêu |
| Duy trì package ở phiên bản được chỉ định | Distributor kết hợp State Manager association | Association định kỳ thực thi cấu hình cài đặt |
| Phát hiện node lệch baseline | Inventory, truy vấn và báo cáo | Danh sách node cần điều tra hoặc khắc phục |
| Theo dõi kết quả thực thi | Run Command, State Manager và Systems Manager Compliance | Trạng thái lệnh, association và thông tin tuân thủ liên quan |
| Phân tích fleet nhiều account/Region | Resource Data Sync và Amazon S3 | Dữ liệu Inventory tập trung để truy vấn và báo cáo |

Inventory chủ yếu là dữ liệu quan sát được tại thời điểm thu thập. Nó không tự cài đặt phần mềm, không tự sửa cấu hình và cũng không chứng minh một phần mềm đã được tổ chức phê duyệt. Để thực thi trạng thái mong muốn, cần dùng Distributor, Run Command, State Manager hoặc công cụ quản lý cấu hình phù hợp.

## 2. Điều kiện để node xuất hiện trong Systems Manager

Systems Manager quản lý các node đã đăng ký và đáp ứng điều kiện kết nối. Node có thể là EC2 instance hoặc máy chủ hybrid chạy ngoài AWS. Trước khi bật Inventory hay triển khai package, cần xác nhận các điều kiện nền tảng.

### 2.1. SSM Agent

SSM Agent là phần mềm chạy trên node, nhận công việc từ Systems Manager và gửi trạng thái hoặc dữ liệu thu thập về dịch vụ. Agent cần được cài đặt, đang chạy và ở phiên bản tương thích với những tài liệu lệnh được sử dụng. Một số AMI AWS đã cài sẵn agent; các image tự tạo hoặc máy chủ bên ngoài có thể cần cài đặt và cập nhật agent riêng.

Agent cũ, dừng hoạt động hoặc không thể kết nối sẽ khiến node không nhận lệnh đúng hạn, không gửi Inventory mới hoặc hiển thị trạng thái không chính xác. Vì vậy, SSM Agent là một thành phần nền tảng cần được theo dõi như các agent vận hành khác.

### 2.2. IAM và danh tính managed node

Với EC2, gắn instance profile có quyền Systems Manager phù hợp. Chính sách AWS managed policy **AmazonSSMManagedInstanceCore** thường được dùng làm điểm bắt đầu cho quyền cần thiết của managed node; môi trường có yêu cầu đặc biệt có thể dùng policy do tổ chức quản lý với quyền tối thiểu tương ứng.

Với máy chủ ngoài AWS, tạo hybrid activation và đăng ký node thành managed node. Quy trình này sử dụng activation code, activation ID và role phù hợp. Bảo vệ thông tin activation như thông tin xác thực nhạy cảm, giới hạn thời hạn và số lượng đăng ký, đồng thời thu hồi activation không còn sử dụng.

Quyền của node để kết nối với Systems Manager khác với quyền của người vận hành để gọi API. Người vận hành cần IAM policy riêng cho các thao tác như xem Inventory, tạo association, gửi Run Command, quản lý package hoặc cấu hình Resource Data Sync.

### 2.3. Kết nối mạng

Node phải kết nối được tới các endpoint Systems Manager cần thiết trong Region của nó. Kết nối có thể đi qua internet/NAT hoặc VPC interface endpoints theo kiến trúc mạng. Những endpoint như **ssm**, **ssmmessages** và **ec2messages** có yêu cầu phụ thuộc Region, loại node và phiên bản agent; hãy đối chiếu tài liệu AWS cho Region triển khai.

Nếu triển khai package từ Distributor, node còn cần truy cập được nguồn tải package mà quy trình sử dụng, thường bao gồm Amazon S3 hoặc endpoint liên quan. VPC endpoint policy, security group, route, DNS và bucket policy đều có thể làm gián đoạn tải package dù node đã xuất hiện trong danh sách managed nodes.

### 2.4. Kiểm tra trước khi thu thập

Trong Systems Manager Fleet Manager hoặc trang Managed nodes, xác nhận node đã được đăng ký, trạng thái ping là Online, Platform và Agent version được nhận diện. Có thể dùng AWS CLI:

~~~bash
aws ssm describe-instance-information \
  --filters "Key=PingStatus,Values=Online" \
  --query "InstanceInformationList[].{Id:InstanceId,Platform:PlatformName,Version:AgentVersion,Ping:PingStatus}" \
  --output table
~~~

Lệnh này giúp xem các node đang Online mà danh tính hiện tại được phép truy vấn. Nếu node chưa xuất hiện, xử lý SSM Agent, instance profile hoặc hybrid activation và kết nối mạng trước khi điều tra Inventory.

## 3. Systems Manager Inventory thu thập dữ liệu nào?

Inventory thu thập thông tin theo các loại dữ liệu có schema. Một số loại phổ biến:

| Inventory type | Nội dung | Ví dụ sử dụng |
|---|---|---|
| **AWS:InstanceInformation** | Thông tin hệ điều hành, nền tảng, phiên bản agent và metadata node | Tìm node theo platform hoặc agent version |
| **AWS:Application** | Ứng dụng và phần mềm được nhận diện trên node | Tìm máy có Java, agent giám sát hoặc package cụ thể |
| **AWS:Network** | Thông tin network adapter và cấu hình mạng được hỗ trợ | Điều tra khác biệt network giữa các node |
| **AWS:WindowsUpdate** | Thông tin Windows Update được thu thập | Xác định cập nhật Windows hiện diện trên máy |
| **AWS:PatchSummary** | Tóm tắt trạng thái patch liên quan đến Patch Manager | Xem nhanh tình trạng patch của node |
| **AWS:PatchGroup** | Thông tin patch group được gán | Đối chiếu node với baseline patch |
| **AWS:Service** | Dịch vụ hệ điều hành được thu thập trên nền tảng hỗ trợ | Kiểm tra một service có được cài đặt hoặc nhận diện |
| **AWS:WindowsRole** | Windows role được thu thập | Tìm máy Windows đảm nhiệm vai trò nhất định |
| **AWS:File** | Metadata file theo cấu hình Inventory | Kiểm tra sự hiện diện và thuộc tính file được chỉ định |
| **AWS:WindowsRegistry** | Dữ liệu registry theo cấu hình trên Windows | Kiểm kê khóa registry cần theo dõi |
| **Custom:...** | Metadata do tổ chức bổ sung theo schema riêng | Ghi nhận owner ứng dụng, môi trường runtime hoặc mã phát hành |

Các loại dữ liệu khả dụng phụ thuộc hệ điều hành, loại node, phiên bản SSM Agent và tham số cấu hình. Không phải mọi node đều có đủ tất cả inventory type. Ví dụ, Windows Update và Windows Registry chỉ có ý nghĩa với Windows; thông tin package trên Linux có thể khác nhau theo hệ điều hành và package manager.

Inventory lưu các thuộc tính theo schema. Khi schema hoặc tập thuộc tính thay đổi theo nền tảng, nên dùng API **GetInventorySchema** để kiểm tra loại dữ liệu và thuộc tính đang có trước khi xây dựng truy vấn tự động.

Inventory có thể thu thập ứng dụng và package mà agent nhận diện được, nhưng không phải một trình quét bảo mật toàn diện. Phần mềm portable, binary được chép thủ công, container image, dependency nằm trong thư mục ứng dụng hoặc thành phần không được bộ thu thập hỗ trợ có thể không xuất hiện như một ứng dụng đã cài đặt. Cần xác định rõ phạm vi kiểm kê trước khi dùng dữ liệu cho quyết định tuân thủ.

## 4. Bật thu thập Inventory trên fleet

Một cách phổ biến để bật Inventory là tạo State Manager association với SSM document **AWS-GatherSoftwareInventory**. Association xác định document, node mục tiêu, lịch thực thi và tham số. SSM Agent trên các node mục tiêu chạy document theo lịch, sau đó gửi kết quả Inventory về Systems Manager.

Ví dụ tạo association cho các node có tag Environment=production:

~~~bash
aws ssm create-association \
  --name "AWS-GatherSoftwareInventory" \
  --association-name "collect-production-inventory" \
  --targets "Key=tag:Environment,Values=production" \
  --schedule-expression "rate(1 day)"
~~~

Ví dụ trên thu thập Inventory mỗi ngày cho các node khớp tag tại thời điểm association được áp dụng. Có thể chọn lịch ngắn hơn cho fleet cần dữ liệu cập nhật nhanh, nhưng phải cân nhắc tải agent, số lượng node và nhu cầu truy vấn. Inventory là dữ liệu theo chu kỳ; nó không nên được xem như trạng thái tức thời sau mỗi thay đổi trên máy.

### Chọn mục tiêu association

Có thể nhắm mục tiêu theo instance ID, tag hoặc nhóm node được hỗ trợ. Dùng tag giúp mở rộng phạm vi tự động khi node mới được tạo và gắn tag đúng quy ước. Ví dụ:

- Environment=development cho môi trường phát triển.
- Environment=production cho production.
- Application=orders cho fleet của ứng dụng Orders.
- ManagedBy=platform cho node do nhóm nền tảng chịu trách nhiệm.

Tag cần được quản trị thống nhất. Nếu một node thiếu tag hoặc bị gắn nhầm tag, association có thể bỏ sót node hoặc thu thập dữ liệu ngoài phạm vi mong muốn. Kết hợp quy tắc tag với AWS Organizations Tag Policies, quy trình provisioning và kiểm tra định kỳ để giữ phạm vi mục tiêu chính xác.

### Chọn lịch thu thập

Lịch thu thập phụ thuộc tốc độ thay đổi của fleet và mục tiêu kiểm kê:

| Loại fleet | Lịch tham khảo | Lý do |
|---|---|---|
| Production ít thay đổi | Mỗi ngày | Đủ cho báo cáo baseline và rà soát định kỳ |
| Fleet ứng dụng thay đổi thường xuyên | Vài giờ một lần | Giảm khoảng thời gian dữ liệu cũ |
| Máy thử nghiệm tạm thời | Theo vòng đời hoặc lịch ngắn | Hỗ trợ kiểm tra trong thời gian tồn tại |
| Fleet có số lượng node rất lớn | Chia nhóm và giãn lịch | Giảm tải đồng thời và dễ khoanh vùng lỗi |

Các khoảng thời gian trên là gợi ý thiết kế, không phải lịch mặc định bắt buộc của AWS. Hãy thử nghiệm với quy mô nhỏ trước khi áp dụng toàn fleet.

### Kiểm tra association

Sau khi tạo association, theo dõi trạng thái và lần thực thi cuối. Ví dụ:

~~~bash
aws ssm list-associations \
  --association-filter-list "key=AssociationName,value=collect-production-inventory"
~~~

Sau đó dùng **DescribeAssociationExecutions** và **DescribeAssociationExecutionTargets** để điều tra execution theo association. Một association tồn tại không đảm bảo mọi node đã thu thập thành công; cần xem trạng thái execution của từng target và thời điểm dữ liệu mới nhất.

## 5. Truy vấn và đối chiếu dữ liệu Inventory

Có thể xem Inventory trong Systems Manager console hoặc dùng API để truy vấn bằng script. Hai API hữu ích là:

- **GetInventorySchema:** trả về loại Inventory và các thuộc tính có thể truy vấn.
- **GetInventory:** truy vấn Inventory trên nhiều managed node theo filter hoặc aggregation.

Ví dụ liệt kê các node có ứng dụng Amazon CloudWatch Agent:

~~~bash
aws ssm get-inventory \
  --filters "Key=AWS:Application.Name,Values=AmazonCloudWatchAgent,Type=Equal"
~~~

Ví dụ lọc node theo tên nền tảng:

~~~bash
aws ssm get-inventory \
  --filters "Key=AWS:InstanceInformation.PlatformName,Values=Amazon Linux,Type=Equal"
~~~

Tên thuộc tính phải khớp schema của inventory type và giá trị được thu thập thực tế. Nếu truy vấn không trả kết quả, kiểm tra schema, loại node, lịch association và tên phần mềm hiển thị trong dữ liệu trước khi kết luận fleet không có phần mềm đó.

Để xem ứng dụng trên một managed node cụ thể:

~~~bash
aws ssm list-inventory-entries \
  --instance-id "i-0123456789abcdef0" \
  --type-name "AWS:Application"
~~~

Để kiểm tra schema ứng dụng:

~~~bash
aws ssm get-inventory-schema \
  --type-name "AWS:Application"
~~~

### Tìm node thiếu phần mềm chuẩn

Giả sử baseline yêu cầu mọi node thuộc Application=orders phải có Amazon CloudWatch Agent. Có thể thực hiện quy trình:

1. Truy vấn danh sách managed node thuộc fleet Orders.
2. Truy vấn Inventory của ứng dụng Amazon CloudWatch Agent trong cùng phạm vi.
3. Đối chiếu hai tập node theo instance ID.
4. Phân loại node thiếu agent, node có agent nhưng sai phiên bản và node chưa có dữ liệu mới.
5. Dùng Distributor/Run Command hoặc State Manager để khắc phục.
6. Thu thập lại Inventory và xác nhận phiên bản sau triển khai.

Khi viết script đối chiếu, cần phân biệt ba trường hợp: **không có phần mềm**, **không có bản ghi Inventory**, và **node không còn Online**. Không có bản ghi không đồng nghĩa phần mềm chắc chắn chưa được cài; có thể association chưa chạy, node mất kết nối hoặc bộ thu thập không nhận diện phần mềm.

## 6. Bổ sung custom inventory cho metadata của tổ chức

Inventory tiêu chuẩn không biết mọi thuộc tính nội bộ của doanh nghiệp. Một ứng dụng có thể cần metadata như service owner, application tier, mã release, business unit, runtime hoặc ngày hết hạn hỗ trợ. Có thể bổ sung dữ liệu bằng custom inventory type với tên bắt đầu bằng **Custom:**.

Ví dụ gửi metadata ứng dụng nội bộ tới một managed node:

~~~bash
aws ssm put-inventory \
  --instance-id "i-0123456789abcdef0" \
  --items '[
    {
      "TypeName": "Custom:ApplicationOwnership",
      "SchemaVersion": "1.0",
      "CaptureTime": "2026-11-20T00:00:00Z",
      "Content": [
        {
          "Application": "orders",
          "OwnerTeam": "commerce-platform",
          "Release": "2026.11.3",
          "Tier": "critical"
        }
      ]
    }
  ]'
~~~

Ví dụ trên minh họa cấu trúc dữ liệu; thay instance ID, thời điểm và nội dung bằng dữ liệu thực tế của tổ chức. Tên type và schema cần ổn định để các nhóm có thể truy vấn lâu dài. Nếu thay đổi cấu trúc, hãy lên version schema và giữ khả năng xử lý dữ liệu cũ trong thời gian chuyển đổi.

Custom inventory có thể được gửi bằng API PutInventory hoặc thu thập từ script/tác vụ tự động trên node. Cần kiểm soát ai được phép ghi custom inventory, xác thực nguồn dữ liệu, tránh ghi secret, token hoặc thông tin cá nhân không cần thiết. Metadata do node tự khai báo nên được xem là dữ liệu cần kiểm chứng; không dùng một trường tự khai báo làm bằng chứng duy nhất cho quyết định bảo mật quan trọng.

## 7. Distributor: đóng gói và phân phối phần mềm

AWS Systems Manager Distributor là năng lực quản lý package trong Systems Manager. Quản trị viên có thể sử dụng package do AWS cung cấp hoặc tạo package riêng để phân phối phần mềm, agent và công cụ vận hành tới managed node.

Một package Distributor thường mô tả:

- Tên package và version.
- Hệ điều hành, kiến trúc hoặc nền tảng được hỗ trợ.
- Payload cài đặt và các file phụ trợ.
- Script cài đặt và gỡ bỏ.
- Tham số hoặc điều kiện cần thiết khi cài đặt.
- Thông tin manifest và cấu trúc package theo định dạng Distributor hỗ trợ.

Ví dụ về các phần mềm có thể được quản lý theo cách này là Amazon CloudWatch Agent, agent bảo mật, công cụ backup hoặc tiện ích nội bộ. Cần xác nhận package hỗ trợ đúng OS và kiến trúc của fleet trước khi triển khai.

### Thiết kế package nội bộ

Với phần mềm do tổ chức đóng gói, nên duy trì source artifact có version, checksum, nguồn tải, giấy phép và người phê duyệt. Script cài đặt cần chạy lặp lại an toàn, ghi log đủ để điều tra và trả exit code phù hợp. Script gỡ bỏ phải xử lý được trạng thái package chưa cài hoặc đã được cập nhật, đồng thời tránh xóa dữ liệu ứng dụng ngoài phạm vi.

Quy trình phát hành package nên gồm:

1. Xác minh nguồn và tính toàn vẹn của artifact.
2. Kiểm thử trên từng hệ điều hành và kiến trúc hỗ trợ.
3. Kiểm tra script install/uninstall và quyền cần thiết.
4. Tạo version mới trong Distributor.
5. Thử cài trên nhóm canary.
6. Mở rộng theo từng đợt sau khi theo dõi lỗi.
7. Ghi nhận version được phê duyệt và kế hoạch rollback.

### Package version và vòng đời

Không nên phụ thuộc hoàn toàn vào nhãn latest cho production. Nếu package mới được phát hành, node có thể nhận version khác nhau ở những thời điểm khác nhau tùy lịch và trạng thái kết nối. Với hệ thống quan trọng, hãy pin version đã kiểm thử, phát hành version mới theo đợt và lưu lại phiên bản trước đó để có thể khôi phục.

## 8. Cài đặt phần mềm bằng Run Command

Run Command phù hợp khi cần thực hiện một thao tác có chủ đích trên một hoặc nhiều managed node. Với package Distributor, document **AWS-ConfigureAWSPackage** có thể cài đặt hoặc gỡ bỏ package.

Ví dụ cài Amazon CloudWatch Agent trên các node có tag Application=orders:

~~~bash
aws ssm send-command \
  --document-name "AWS-ConfigureAWSPackage" \
  --targets "Key=tag:Application,Values=orders" \
  --parameters '{"action":["Install"],"name":["AmazonCloudWatchAgent"],"version":["latest"]}' \
  --comment "Install CloudWatch Agent on Orders fleet"
~~~

Đây là ví dụ triển khai nhanh với version latest. Trong production, nên thay bằng version cụ thể đã được kiểm thử và phê duyệt. Việc pin version giúp kết quả có thể tái lập và dễ điều tra khi các node có hành vi khác nhau.

Run Command trả về command ID. Có thể kiểm tra trạng thái tổng thể và trạng thái từng node:

~~~bash
aws ssm list-command-invocations \
  --command-id "COMMAND_ID" \
  --details
~~~

Trạng thái thành công của lệnh cần được xác nhận ở từng node. Một lệnh gửi tới 100 node có thể thành công trên phần lớn fleet nhưng thất bại ở một số node do mất kết nối, thiếu quyền, package không tương thích hoặc hết dung lượng đĩa.

Để gỡ package:

~~~bash
aws ssm send-command \
  --document-name "AWS-ConfigureAWSPackage" \
  --targets "Key=tag:Application,Values=orders" \
  --parameters '{"action":["Uninstall"],"name":["AmazonCloudWatchAgent"]}' \
  --comment "Remove CloudWatch Agent from Orders fleet"
~~~

Trước khi gỡ agent trên production, xác định ảnh hưởng tới logging, monitoring, bảo mật hoặc backup. Cần có kế hoạch thay thế hoặc khôi phục nếu phần mềm đang là thành phần bắt buộc của vận hành.

## 9. State Manager: duy trì trạng thái phần mềm mong muốn

Run Command thực hiện một lần theo yêu cầu. State Manager dùng association để định nghĩa document, tham số, mục tiêu và lịch chạy. Khi association được lên lịch, Systems Manager có thể tiếp tục áp dụng cấu hình cho các node mục tiêu, bao gồm node mới khớp tag khi association được đánh giá.

Ví dụ tạo association để duy trì CloudWatch Agent trên fleet Orders:

~~~bash
aws ssm create-association \
  --name "AWS-ConfigureAWSPackage" \
  --association-name "ensure-orders-cloudwatch-agent" \
  --targets "Key=tag:Application,Values=orders" \
  --parameters '{"action":["Install"],"name":["AmazonCloudWatchAgent"],"version":["latest"]}' \
  --schedule-expression "rate(1 day)"
~~~

Association trên minh họa cơ chế duy trì package. Với production, nên thay latest bằng version cố định và chỉ cập nhật association sau khi version mới được phê duyệt. Nếu cần rollout an toàn, chia fleet theo tag hoặc nhóm canary, theo dõi kết quả rồi mới thay đổi phạm vi.

State Manager association có thể được dùng để:

- Cài hoặc gỡ package.
- Duy trì cấu hình agent.
- Chạy script kiểm tra hoặc cấu hình định kỳ.
- Áp dụng một baseline vận hành cho nhóm node.

### Association và compliance

State Manager ghi nhận trạng thái thực thi của association và có thể cung cấp thông tin compliance liên quan. Quản trị viên nên theo dõi association bị lỗi, node không nhận lệnh, execution quá hạn hoặc node chưa có compliance data.

Một association ở trạng thái Success chỉ cho biết document đã chạy thành công theo cơ chế báo cáo của nó. Điều đó không tự chứng minh toàn bộ ứng dụng hoạt động đúng hoặc package không có lỗ hổng. Cần kết hợp kiểm tra version trong Inventory, health check của ứng dụng, log, metric và quy trình kiểm thử sau triển khai.

## 10. Kết hợp Inventory, Distributor và State Manager

Một quy trình quản lý phần mềm hoàn chỉnh có thể được tổ chức thành vòng lặp:

~~~mermaid
flowchart TD
    A[Managed nodes và SSM Agent] --> B[AWS-GatherSoftwareInventory]
    B --> C[Inventory theo schema]
    C --> D[Truy vấn và đối chiếu baseline]
    D --> E{Có node lệch chuẩn?}
    E -->|Không| F[Theo dõi định kỳ]
    E -->|Có| G[Chọn package và version đã duyệt]
    G --> H[Distributor]
    H --> I[Run Command hoặc State Manager]
    I --> J[Kiểm tra execution và compliance]
    J --> K[Thu thập Inventory lại]
    K --> C
~~~

Ví dụ, baseline của nhóm nền tảng yêu cầu mọi EC2 instance thuộc Application=orders phải có Amazon CloudWatch Agent ở version được phê duyệt. Quy trình sẽ:

1. Thu thập Inventory định kỳ trên fleet Orders.
2. Truy vấn các bản ghi AWS:Application và xác định version agent.
3. So sánh với baseline version được lưu trong quy trình phát hành.
4. Chia node thành nhóm đúng version, thiếu agent, sai version và không có dữ liệu mới.
5. Tạo canary group để thử version mới.
6. Dùng Distributor và State Manager triển khai tới nhóm canary.
7. Kiểm tra trạng thái association, command output, agent health và dữ liệu CloudWatch.
8. Mở rộng rollout theo từng đợt.
9. Thu thập Inventory lại để xác nhận version thực tế.
10. Lưu bằng chứng thay đổi, kết quả và danh sách node ngoại lệ.

Đây là quy trình có thể tự động hóa bằng EventBridge, Lambda hoặc pipeline nội bộ nếu tổ chức cần. Khi tự động hóa, cần giới hạn quyền của role thực thi, chống lặp lệnh, xử lý trạng thái chưa xác định và yêu cầu phê duyệt cho thay đổi production có rủi ro cao.

## 11. Tập trung dữ liệu Inventory trên fleet nhiều account và Region

Trong môi trường AWS Organizations, dữ liệu nằm rải rác ở nhiều account và Region sẽ khó phân tích nếu nhóm kiểm toán phải truy vấn từng nơi. Systems Manager Resource Data Sync có thể đồng bộ Inventory tới Amazon S3 để xây dựng kho dữ liệu tập trung.

Kiến trúc tham khảo:

~~~mermaid
flowchart LR
    A[Account ứng dụng A] --> D[Systems Manager Inventory]
    B[Account ứng dụng B] --> E[Systems Manager Inventory]
    C[Account ứng dụng C] --> F[Systems Manager Inventory]
    D --> G[Resource Data Sync]
    E --> G
    F --> G
    G --> H[Amazon S3 trung tâm]
    H --> I[Amazon Athena]
    I --> J[Amazon QuickSight hoặc báo cáo]
~~~

Resource Data Sync có thể gom dữ liệu từ nhiều Region và hỗ trợ mô hình nhiều account theo AWS Organizations khi được cấu hình đúng. Quản trị viên cần thiết lập trusted access và quyền cần thiết cho mô hình tổ chức, chọn account/OU và Region nguồn, cấu hình đích S3, đồng thời kiểm tra phạm vi dữ liệu được đồng bộ.

### Thiết kế kho dữ liệu

Khi đưa Inventory vào S3:

- Chọn bucket và prefix riêng cho dữ liệu Systems Manager.
- Bật mã hóa phù hợp, hạn chế quyền đọc và ghi theo account hoặc role.
- Thiết lập lifecycle và retention theo chính sách kiểm toán.
- Kiểm soát quyền truy cập dữ liệu nhạy cảm như tên phần mềm nội bộ, đường dẫn file hoặc metadata ứng dụng.
- Dùng Athena để truy vấn và QuickSight hoặc công cụ BI để trình bày xu hướng.
- Theo dõi độ trễ đồng bộ và lỗi delivery để tránh báo cáo dựa trên dữ liệu cũ.

S3 Resource Data Sync là bản tập trung để phân tích; nó không thay thế trạng thái gốc của managed node trong Systems Manager. Cần giữ thông tin account, Region, instance ID và thời điểm capture để truy nguyên dữ liệu về nguồn.

Ví dụ, tổ chức có thể tạo báo cáo:

- Số lượng node theo hệ điều hành, account, Region và môi trường.
- Tỷ lệ node có SSM Agent ở version được hỗ trợ.
- Số node cài agent giám sát hoặc agent bảo mật.
- Phân bố version runtime theo ứng dụng.
- Danh sách node có Inventory quá cũ.
- Các package xuất hiện trên production nhưng chưa có trong baseline.

## 12. Bảo mật và kiểm toán khi quản lý phần mềm

Inventory có thể chứa tên ứng dụng, version, thông tin hệ điều hành, cấu hình mạng, đường dẫn file và metadata do tổ chức tự bổ sung. Những thông tin này giúp kiểm toán nhưng cũng có thể tiết lộ cấu trúc nội bộ. Hãy quản lý dữ liệu theo nguyên tắc least privilege.

### Tách vai trò

Một mô hình phân quyền tham khảo:

| Vai trò | Nhiệm vụ | Quyền nên giới hạn |
|---|---|---|
| Fleet operator | Xem node và Inventory | Quyền đọc đúng account/Region hoặc nhóm phụ trách |
| Software publisher | Tạo và phát hành package | Quản lý package và version trong phạm vi được giao |
| Deployment operator | Gửi Run Command hoặc quản lý association | Chỉ chạy document đã duyệt và nhắm đúng tag/instance |
| Auditor | Đọc dữ liệu và bằng chứng | Không có quyền cài đặt hoặc thay đổi package |
| Central data analyst | Truy vấn dữ liệu S3 tập trung | Chỉ đọc prefix và dataset được cấp quyền |

Không nên dùng một role quản trị toàn quyền cho cả người tạo package, người phê duyệt và người triển khai production. Với thay đổi quan trọng, tách quyền phát hành và quyền triển khai giúp tăng khả năng kiểm soát.

### Bảo vệ artifact và script

Package cài đặt có thể thực thi với quyền cao trên node. Chỉ phân phối artifact từ nguồn đáng tin cậy, xác minh tính toàn vẹn, giới hạn quyền ghi package và bảo vệ script. Không nhúng mật khẩu, access key, token hoặc private key trong payload, command parameter hay log.

### Ghi nhận hoạt động

CloudTrail ghi nhận các thao tác API quản trị như tạo association, gửi command, quản lý package và cấu hình đồng bộ. Run Command và State Manager cung cấp trạng thái thực thi; có thể cấu hình output về Amazon S3 hoặc CloudWatch Logs để lưu log chi tiết. Trên node, log của SSM Agent giúp điều tra lỗi thực thi hoặc kết nối.

Với kiểm toán, nên lưu:

- Người hoặc role tạo và thay đổi association.
- Document, tham số, target và lịch thực thi.
- Package name, version, nguồn artifact và người phê duyệt.
- Command ID, association execution ID và trạng thái từng node.
- Inventory trước và sau rollout.
- Các ngoại lệ, quyết định chấp nhận rủi ro và bằng chứng khắc phục.

## 13. Chi phí và hiệu năng ở quy mô lớn

Systems Manager Inventory không chỉ là câu chuyện bật một document. Khi fleet lớn, số lần thực thi, kích thước dữ liệu, số lượng thuộc tính và tần suất đồng bộ đều ảnh hưởng tới vận hành và chi phí liên quan.

Các nguyên tắc thực tế:

1. Thu thập đúng loại dữ liệu cần thiết. Không bật kiểm kê file hoặc registry diện rộng nếu không có mục đích rõ ràng.
2. Chọn lịch dựa trên tốc độ thay đổi và thời gian chấp nhận dữ liệu cũ.
3. Chia fleet thành nhóm để tránh hàng nghìn node chạy document cùng thời điểm.
4. Dùng tag và OU để kiểm soát phạm vi.
5. Theo dõi S3 storage, request, Athena scan và thời gian lưu trữ của dữ liệu đồng bộ.
6. Lưu log ở mức đủ điều tra nhưng tránh phát sinh dữ liệu không cần thiết.
7. Theo dõi association execution và command concurrency để phát hiện backlog.

Nếu cần tăng tần suất thu thập, hãy xác định câu hỏi vận hành nào cần dữ liệu mới hơn. Một báo cáo license hoặc inventory hàng tuần có thể không cần lịch vài phút một lần. Ngược lại, một quy trình kiểm soát agent trên production có thể cần lịch ngắn hơn và có kiểm tra bổ sung sau triển khai.

## 14. Tình huống thực tế: chuẩn hóa agent trên fleet ứng dụng

Một doanh nghiệp có ba account: Development, Staging và Production. Mỗi account có nhiều EC2 instance thuộc các ứng dụng khác nhau. Nhóm nền tảng yêu cầu mọi node production phải có SSM Agent và Amazon CloudWatch Agent; các agent cần nằm trong phiên bản được kiểm thử.

Thiết kế vận hành:

1. Tất cả EC2 instance sử dụng instance profile phù hợp và được đăng ký làm managed node.
2. Node được gắn tag Application, Environment, OwnerTeam và ManagedBy.
3. Association AWS-GatherSoftwareInventory thu thập metadata theo lịch cho từng fleet.
4. Resource Data Sync đưa Inventory tới S3 trung tâm để báo cáo đa account.
5. Nhóm nền tảng phát hành version CloudWatch Agent qua Distributor.
6. State Manager association cài version đã duyệt lên nhóm canary.
7. Sau khi xác minh metric, log và trạng thái agent, rollout tới Staging rồi Production.
8. Inventory được thu thập lại và đối chiếu với baseline.
9. Các node lỗi được phân loại theo nguyên nhân: offline, sai quyền, lỗi tải package, không tương thích OS hoặc lỗi cài đặt.
10. Auditor có thể truy lại thay đổi thông qua CloudTrail, association execution, command output và Inventory snapshot.

Sơ đồ rollout:

~~~mermaid
flowchart TD
    A[Phát hành package version mới] --> B[Kiểm thử trên canary]
    B --> C{Health check đạt?}
    C -->|Không| D[Dừng rollout và điều tra]
    C -->|Có| E[Triển khai Staging]
    E --> F{Staging đạt?}
    F -->|Không| D
    F -->|Có| G[Triển khai theo đợt Production]
    G --> H[Thu thập Inventory sau rollout]
    H --> I[Đối chiếu baseline và lưu bằng chứng]
~~~

Thiết kế này giúp nhóm vận hành biết phần mềm nào đang chạy, version nào được phê duyệt và node nào cần xử lý. Nó cũng tạo ra đường lui: nếu version mới gây lỗi, nhóm có thể dừng rollout, dùng version trước đó theo quy trình package và xác nhận trạng thái sau khi khôi phục.

## 15. Xử lý sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Node không xuất hiện trong Inventory | Node chưa đăng ký, SSM Agent dừng, thiếu IAM hoặc mất kết nối | Kiểm tra Managed nodes, Agent status, instance profile và endpoint |
| Association tồn tại nhưng không có dữ liệu mới | Target không khớp, lịch chưa tới, document lỗi hoặc agent không online | Xem association execution và execution target |
| Inventory thiếu một loại dữ liệu | Hệ điều hành không hỗ trợ, tham số thu thập chưa bật hoặc phần mềm không được nhận diện | Kiểm tra schema, platform và cấu hình document |
| GetInventory trả về rỗng | Sai filter key/value, dữ liệu chưa thu thập hoặc node nằm ở Region khác | Kiểm tra schema, thời điểm capture và Region |
| Package install thất bại | Sai version, OS/architecture không tương thích, thiếu quyền hoặc không tải được artifact | Xem command invocation, output và SSM Agent log |
| Package cài thành công nhưng không có trong Inventory | Inventory chưa chạy lại hoặc bộ thu thập không nhận diện package | Chạy/đợi association Inventory và kiểm tra package trực tiếp theo nền tảng |
| State Manager association báo lỗi liên tục | Tham số sai, document không tương thích hoặc role không đủ quyền | Kiểm tra association status, execution output và IAM |
| Node mới không nhận cấu hình | Tag chưa đúng, node chưa Online hoặc association target không bao phủ node | Kiểm tra tag, managed node status và association target |
| Dữ liệu S3 không cập nhật | Resource Data Sync, bucket policy, KMS hoặc Region cấu hình sai | Kiểm tra sync status, CloudTrail, bucket policy và key policy |
| Rollout ảnh hưởng một phần fleet | Khác biệt OS, kiến trúc, quyền hoặc dung lượng giữa node | Phân nhóm theo platform, xem lỗi từng invocation và dừng rollout theo đợt |

Khi điều tra, luôn phân biệt lỗi thu thập Inventory với lỗi triển khai phần mềm. Hai quy trình có document, execution và log khác nhau; việc một quy trình thành công không chứng minh quy trình còn lại cũng thành công.

## 16. Những hiểu lầm cần tránh

**Inventory tự cài phần mềm.** Inventory chỉ thu thập metadata. Dùng Distributor và Run Command hoặc State Manager để triển khai package.

**Không có bản ghi Inventory nghĩa là phần mềm không tồn tại.** Có thể dữ liệu chưa được thu thập, node mất kết nối hoặc phần mềm không thuộc phạm vi nhận diện.

**Run Command duy trì cấu hình vĩnh viễn.** Run Command thực hiện thao tác theo yêu cầu. Dùng State Manager association khi cần duy trì cấu hình theo lịch.

**Association Success chứng minh ứng dụng khỏe mạnh.** Nó chỉ phản ánh kết quả thực thi document theo cơ chế báo cáo. Cần health check, metric, log và kiểm thử ứng dụng.

**Mọi phần mềm đều xuất hiện trong AWS:Application.** Inventory chỉ ghi nhận dữ liệu mà bộ thu thập hỗ trợ và có thể nhận diện. Binary portable hoặc phần mềm tùy biến có thể cần custom inventory.

**Version latest phù hợp cho mọi môi trường.** Production cần version đã kiểm thử, pin rõ ràng và có kế hoạch rollback.

**Có Resource Data Sync là dữ liệu luôn mới nhất.** Sync phụ thuộc lịch thu thập, thời điểm gửi dữ liệu và quá trình đồng bộ tới S3. Báo cáo phải thể hiện thời điểm capture.

**Managed node Online đồng nghĩa mọi lệnh sẽ thành công.** Quyền IAM, kết nối tải package, tương thích hệ điều hành và dung lượng đĩa vẫn có thể khiến lệnh thất bại.

## 17. Checklist triển khai Inventory và quản lý phần mềm

- [ ] Managed node đã đăng ký và có trạng thái Online.
- [ ] SSM Agent được cài đặt, chạy ổn định và có phiên bản được hỗ trợ.
- [ ] Instance profile hoặc hybrid activation có quyền tối thiểu cần thiết.
- [ ] Node kết nối được tới endpoint Systems Manager và nguồn package.
- [ ] Tag mục tiêu được chuẩn hóa và phản ánh đúng owner/application/environment.
- [ ] AWS-GatherSoftwareInventory association có target và lịch phù hợp.
- [ ] Schema và loại Inventory cần thiết đã được kiểm tra.
- [ ] Truy vấn phân biệt được node không có phần mềm với node thiếu dữ liệu.
- [ ] Package Distributor có version, nguồn artifact và script install/uninstall được kiểm thử.
- [ ] Run Command thử trên canary trước khi triển khai toàn fleet.
- [ ] State Manager association pin version production và có lịch rõ ràng.
- [ ] Có kiểm tra sau cài đặt bằng Inventory, health check, metric và log.
- [ ] Resource Data Sync, S3, KMS và Athena được bảo vệ theo least privilege nếu dùng tập trung dữ liệu.
- [ ] CloudTrail và command/association output được lưu đủ để kiểm toán.
- [ ] Có quy trình rollback, xử lý node offline và quản lý ngoại lệ.

## 18. Ghi nhớ

Systems Manager Inventory cung cấp góc nhìn về phần mềm và cấu hình đang tồn tại trên managed node. Distributor đóng gói và phân phối package; Run Command thực hiện thao tác theo yêu cầu; State Manager duy trì trạng thái mong muốn bằng association; Resource Data Sync tập trung dữ liệu Inventory để phân tích fleet nhiều account và Region.

Để quản lý phần mềm đáng tin cậy, hãy bắt đầu từ danh tính managed node, SSM Agent và kết nối mạng; thu thập Inventory theo lịch phù hợp; xác định baseline có chủ sở hữu; triển khai package theo version đã kiểm thử; theo dõi trạng thái từng node; rồi thu thập lại dữ liệu để xác nhận kết quả. Kết hợp IAM, CloudTrail, log thực thi và kho dữ liệu tập trung sẽ giúp tổ chức kiểm soát thay đổi, truy vết và duy trì fleet AWS an toàn hơn.

## Tài liệu tham khảo

- [Working with Inventory in AWS Systems Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-inventory.html)
- [Configuring Inventory Collection](https://docs.aws.amazon.com/systems-manager/latest/userguide/inventory-collection.html)
- [Querying Inventory Data](https://docs.aws.amazon.com/systems-manager/latest/userguide/inventory-query.html)
- [Working with Custom Inventory](https://docs.aws.amazon.com/systems-manager/latest/userguide/inventory-custom.html)
- [Creating Resource Data Sync for Inventory](https://docs.aws.amazon.com/systems-manager/latest/userguide/inventory-create-resource-data-sync.html)
- [What is Distributor?](https://docs.aws.amazon.com/systems-manager/latest/userguide/distributor.html)
- [Creating a Distributor Package](https://docs.aws.amazon.com/systems-manager/latest/userguide/distributor-working-with-packages-create.html)
- [Installing or Updating Packages](https://docs.aws.amazon.com/systems-manager/latest/userguide/distributor-working-with-packages-deploy.html)
- [Working with Run Command](https://docs.aws.amazon.com/systems-manager/latest/userguide/run-command.html)
- [Working with State Manager Associations](https://docs.aws.amazon.com/systems-manager/latest/userguide/state-manager-associations.html)
- [Setting Up AWS Systems Manager for EC2 Instances](https://docs.aws.amazon.com/systems-manager/latest/userguide/setup-instance-permissions.html)
- [Setting Up AWS Systems Manager for Hybrid and Multicloud Environments](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-managedinstances.html)
