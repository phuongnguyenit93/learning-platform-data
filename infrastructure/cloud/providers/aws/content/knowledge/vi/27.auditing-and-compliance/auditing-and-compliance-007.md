# Service Catalog và danh mục hạ tầng được phê duyệt

Trong một môi trường AWS có nhiều đội phát triển, mỗi đội có thể cần tạo máy chủ, cơ sở dữ liệu, mạng, bucket lưu trữ hoặc pipeline triển khai. Nếu mỗi đội tự thiết kế và cấp phát tài nguyên theo cách riêng, tổ chức khó bảo đảm cấu hình bảo mật nhất quán, khó truy vết người chịu trách nhiệm và dễ phát sinh chi phí ngoài dự kiến. Ngược lại, nếu mọi yêu cầu đều phải chờ một nhóm vận hành tạo tài nguyên thủ công, tốc độ phát triển sẽ chậm và nhóm vận hành trở thành nút thắt.

AWS Service Catalog giải quyết bài toán này bằng cách cung cấp một danh mục các dịch vụ và mẫu hạ tầng đã được tổ chức chuẩn bị, rà soát và cho phép sử dụng. Người dùng được cấp quyền có thể tự chọn sản phẩm phù hợp và triển khai theo các tham số đã được giới hạn. Nhờ đó, tổ chức chuẩn hóa cách tạo tài nguyên trên AWS, phân quyền theo nhóm, phân phối mẫu dùng chung qua nhiều tài khoản và giữ lại dấu vết phục vụ kiểm toán.

Trong hệ sinh thái **CLOUD_PROVIDERS_AWS**, Service Catalog có thể đóng gói những cấu hình chuẩn cho Region/AZ, IAM, VPC, compute, storage, database, tích hợp và serverless. Catalog là một phần của mô hình quản trị: nó giúp người dùng đi theo con đường đã được phê duyệt, còn IAM, AWS Organizations, AWS Config, CloudTrail và các cơ chế bảo mật khác cung cấp những lớp kiểm soát và bằng chứng bổ sung.

## 1. AWS Service Catalog giải quyết vấn đề gì?

AWS Service Catalog là dịch vụ quản lý danh mục các sản phẩm CNTT được phê duyệt để triển khai trên AWS. Một sản phẩm có thể là một tài nguyên đơn lẻ hoặc một hệ thống gồm nhiều tài nguyên liên kết với nhau. Ví dụ:

- Một bucket S3 đã bật mã hóa, versioning và chặn truy cập công khai.
- Một VPC có subnet công khai và riêng tư, route table, NAT Gateway và security group theo chuẩn.
- Một cụm cơ sở dữ liệu có cấu hình sao lưu, mã hóa, giám sát và tham số kết nối phù hợp.
- Một môi trường ứng dụng gồm compute, load balancer, logging và các thành phần mạng cần thiết.

Nếu không có catalog, mỗi nhóm có thể tự viết template, tự chọn kích thước máy, tự cấu hình quyền hoặc quên gắn tag. Khi catalog được quản trị tốt, nhóm nền tảng có thể phát hành một số mẫu đã kiểm tra, còn nhóm ứng dụng chỉ chọn mẫu, điền tham số được cho phép và triển khai theo quyền đã cấp.

Service Catalog hữu ích khi tổ chức cần:

1. **Chuẩn hóa:** dùng lại template và cấu hình nền tảng đã được rà soát.
2. **Tự phục vụ có kiểm soát:** cho phép đội dự án triển khai mà không cần cấp cho họ toàn bộ quyền quản trị AWS.
3. **Phân phối theo đối tượng:** cung cấp portfolio khác nhau cho nhóm phát triển, dữ liệu, vận hành hoặc môi trường production.
4. **Quản lý vòng đời:** phát hành phiên bản mới, cập nhật sản phẩm đang chạy và ngừng cung cấp phiên bản cũ theo quy trình.
5. **Truy vết:** liên kết sản phẩm, phiên bản, quyền triển khai, tag và sự kiện cấp phát với quy trình kiểm toán.

Service Catalog không tự động biến mọi tài nguyên trong tài khoản thành tài nguyên được phê duyệt. Người dùng vẫn có thể tạo tài nguyên trực tiếp bằng API hoặc dịch vụ AWS khác nếu IAM và các guardrail của tổ chức cho phép. Vì vậy, catalog cần được phối hợp với IAM, Service Control Policies (SCP), AWS Config, CloudTrail và quy trình quản lý thay đổi.

## 2. Các khái niệm cốt lõi

| Thành phần | Ý nghĩa | Câu hỏi quản trị cần trả lời |
|---|---|---|
| **Product** | Một dịch vụ hoặc mẫu hạ tầng có thể triển khai, thường được định nghĩa bằng template CloudFormation hoặc Terraform được Service Catalog hỗ trợ | Template có đáp ứng baseline bảo mật, vận hành và chi phí không? |
| **Product version** | Một phiên bản của template và cấu hình sản phẩm | Phiên bản nào đã được kiểm thử và được phép phát hành? |
| **Portfolio** | Tập hợp product dành cho một nhóm người dùng hoặc mục đích sử dụng | Nhóm nào được xem và triển khai những sản phẩm nào? |
| **Provisioned product** | Một instance của product đã được người dùng triển khai và Service Catalog quản lý vòng đời | Ai tạo, đang chạy phiên bản nào và tài nguyên nào thuộc instance này? |
| **Constraint** | Quy tắc giới hạn cách một product được triển khai trong một portfolio cụ thể | Người dùng được chọn tham số, quyền và cách triển khai đến mức nào? |
| **TagOption** | Cặp key-value được quản lý trong thư viện TagOption của Service Catalog để chuẩn hóa lựa chọn tag | Những giá trị tag nào được phép dùng khi cấp phát sản phẩm? |
| **Principal** | IAM user, group hoặc role được gán quyền truy cập portfolio | Danh tính nào được phép sử dụng catalog? |

### Product và provisioned product không giống nhau

Product là định nghĩa có thể tái sử dụng, chẳng hạn template tạo một bucket S3 theo chuẩn. Khi người dùng triển khai product, Service Catalog tạo một **provisioned product**. Có thể xem product như bản thiết kế và provisioned product như một lần triển khai cụ thể của bản thiết kế đó.

Với product dựa trên CloudFormation, provisioned product thường tương ứng với một CloudFormation stack chứa các tài nguyên được khai báo trong template. Với product dựa trên Terraform, Service Catalog sử dụng cơ chế provisioning tương ứng với loại product đó. Vì vậy, không nên mặc định mọi provisioned product đều là một CloudFormation stack.

Một product có thể được thêm vào nhiều portfolio. Điều này cho phép tổ chức dùng lại cùng một template nhưng phân phối cho các nhóm khác nhau với quyền và constraint riêng. Ví dụ, product tạo môi trường ứng dụng có thể xuất hiện trong portfolio Development và Production; portfolio Production có thể giới hạn tham số chặt hơn và sử dụng launch role khác.

### Portfolio và quyền truy cập

Portfolio là lớp tổ chức và phân phối product. Quản trị viên có thể tạo portfolio theo chức năng, đơn vị, môi trường hoặc cấp độ rủi ro, ví dụ:

- **Developer Sandbox:** các mẫu thử nghiệm với kích thước nhỏ, thời gian sống ngắn và giới hạn chi phí.
- **Application Platform:** VPC, compute, load balancer và logging theo chuẩn của nhóm nền tảng.
- **Data Platform:** bucket, database và pipeline dữ liệu có mã hóa, sao lưu và phân loại dữ liệu.
- **Production Services:** các mẫu đã qua kiểm thử vận hành, có giám sát, sao lưu và yêu cầu phê duyệt thay đổi.

Khi một IAM principal được cấp quyền truy cập portfolio và có các quyền Service Catalog cần thiết, người dùng có thể duyệt và triển khai những product được cung cấp trong portfolio đó. Quyền xem hoặc triển khai catalog vẫn phải được cấp bằng IAM; việc một người biết tên product không đồng nghĩa người đó được phép sử dụng product.

### Product version và vòng đời

Một product có thể có nhiều version để phản ánh thay đổi về template, bản vá, cấu hình bảo mật hoặc kiến trúc. Khi quản trị viên thêm version vào product, version mới được cung cấp cho những người dùng hiện có quyền truy cập product. Việc phát hành version mới không có nghĩa mọi provisioned product đang chạy tự động được cập nhật. Quản trị viên cần xác định cách và thời điểm cập nhật các instance hiện hữu, kiểm thử tác động và theo dõi kết quả.

Quy trình version nên có chủ sở hữu, ghi chú thay đổi, kết quả kiểm thử, ngày phát hành và kế hoạch ngừng hỗ trợ. Nếu phát hiện lỗi nghiêm trọng, quản trị viên có thể ngừng cung cấp version đó cho các lần triển khai mới theo khả năng quản lý version của product, sau đó lập kế hoạch xử lý các instance đang sử dụng version bị ảnh hưởng.

## 3. Cách Service Catalog kiểm soát việc triển khai

Service Catalog phối hợp nhiều lớp kiểm soát. Mỗi lớp giải quyết một câu hỏi khác nhau: ai được dùng catalog, tài nguyên được tạo bằng quyền nào, tham số nào được phép chọn và sự kiện triển khai được gửi đến đâu.

### 3.1. IAM: ai được quản trị và ai được sử dụng?

Nên tách hai nhóm quyền:

- **Catalog administrator:** tạo product và version, quản lý portfolio, gán principal, cấu hình constraint, TagOption và chia sẻ portfolio.
- **End user:** xem các product được cấp quyền, triển khai, cập nhật hoặc chấm dứt provisioned product trong phạm vi được cho phép.

Không cấp quyền quản trị catalog cho mọi người dùng cuối. Nên dùng IAM role theo nhiệm vụ, IAM group hoặc cơ chế danh tính tập trung để cấp quyền cho nhóm. Khi nhân sự chuyển nhóm hoặc rời dự án, quản trị viên chỉ cần điều chỉnh membership hoặc role tương ứng.

Quyền truy cập portfolio và quyền thực thi API Service Catalog là hai phần cần được xem xét cùng nhau. Người dùng cần quyền Service Catalog phù hợp để thực hiện thao tác; quyền truy cập portfolio xác định product nào được phân phối cho principal đó. Ngoài ra, quyền đọc trạng thái tài nguyên qua CloudFormation hoặc dịch vụ liên quan có thể cần thiết để người dùng xem đầy đủ kết quả triển khai.

### 3.2. Launch constraint: dùng IAM role chuyên biệt để tạo tài nguyên

Launch constraint gắn một IAM role với product trong một portfolio. Khi end user triển khai, cập nhật hoặc chấm dứt product, Service Catalog sử dụng role được cấu hình để thực hiện các thao tác provisioning cần thiết.

Mô hình này giúp tách quyền của người dùng khỏi quyền tạo tài nguyên. Ví dụ, một developer có thể được phép triển khai product môi trường ứng dụng nhưng không có quyền tự tạo mọi loại EC2 instance, sửa IAM policy hoặc thay đổi cấu hình mạng tùy ý. Launch role chỉ nên có các action và resource cần thiết cho template của product.

Khi thiết kế launch role:

1. Trust policy phải cho phép dịch vụ Service Catalog assume role.
2. Permission policy phải bao phủ các thao tác CloudFormation hoặc Terraform và những dịch vụ mà product sử dụng.
3. Giới hạn resource ARN, action và điều kiện theo khả năng của từng dịch vụ; tránh cấp quyền quản trị rộng chỉ để làm cho lần triển khai đầu tiên thành công.
4. Xem xét điều kiện bảo vệ confused deputy bằng **aws:SourceAccount** và **aws:SourceArn** theo hướng dẫn hiện hành của AWS.
5. Kiểm thử cả thao tác launch, update và terminate vì role phải đáp ứng vòng đời product.

Launch constraint áp dụng cho quan hệ giữa product và portfolio. Nó không tự động trở thành cấu hình chung cho product trong mọi portfolio. Nếu cùng một product xuất hiện trong nhiều portfolio, mỗi quan hệ cần được xem xét và cấu hình phù hợp.

Launch role cũng không thay thế quyền Service Catalog của end user. Các quyền như triển khai hoặc cập nhật provisioned product phải được cấp cho principal bằng IAM theo đúng mô hình end user; không nên đưa các quyền điều khiển catalog của người dùng vào launch role.

### 3.3. Template constraint: giới hạn tham số người dùng có thể chọn

Template constraint giới hạn các giá trị tham số mà end user được phép nhập khi triển khai product. Ví dụ, một template dùng chung có thể hỗ trợ nhiều loại EC2 instance, nhưng portfolio Development chỉ cho phép loại nhỏ; portfolio Production chỉ cho phép một tập loại instance đã được kiểm thử.

Template constraint giúp tái sử dụng template tổng quát mà vẫn áp dụng quy tắc riêng cho từng portfolio. Có thể giới hạn:

- Loại instance hoặc cấu hình compute.
- CIDR hoặc dải địa chỉ IP.
- Kích thước volume.
- Lựa chọn môi trường hoặc cấu hình dịch vụ.
- Những tham số có ảnh hưởng đến bảo mật và chi phí.

Nên đặt kiểm tra hợp lệ ngay trong template khi quy tắc phải đúng với mọi cách triển khai. Sau đó dùng template constraint để thu hẹp thêm lựa chọn theo portfolio. Cần nhớ rằng template constraint chỉ kiểm soát đường triển khai qua product; nó không ngăn người có quyền phù hợp tạo tài nguyên tương tự trực tiếp bằng API.

### 3.4. Các constraint khác

AWS Service Catalog hỗ trợ một số loại constraint khác nhau. Khả năng áp dụng có thể phụ thuộc loại product và cách triển khai.

| Loại constraint | Công dụng | Ví dụ |
|---|---|---|
| **Launch** | Chọn IAM role mà Service Catalog sử dụng để provisioning | Product database dùng role chỉ có quyền tạo và quản lý database cần thiết |
| **Template** | Giới hạn tham số đầu vào | Portfolio Production chỉ cho phép một số cấu hình instance đã duyệt |
| **Notification** | Gửi thông báo về sự kiện stack qua Amazon SNS | Nhóm vận hành nhận thông báo khi triển khai product thất bại |
| **Stack Set** | Cấu hình triển khai product trên nhiều account và Region bằng CloudFormation StackSets | Phân phối baseline logging hoặc tài nguyên dùng chung tới nhiều account |
| **Tag Update** | Kiểm soát khả năng cập nhật tag sau khi product đã được cấp phát | Cho phép quy trình vận hành bổ sung tag owner hoặc cost center theo quy định |

Constraint được gắn vào product trong portfolio. Vì thế, cần kiểm tra đúng portfolio mà người dùng thực sự sử dụng, không chỉ kiểm tra template gốc hoặc một portfolio thử nghiệm.

## 4. Chuẩn hóa tag bằng TagOption

Tag giúp xác định chủ sở hữu, môi trường, ứng dụng, trung tâm chi phí và mức phân loại dữ liệu. Nếu mỗi nhóm tự đặt tên key và value, dữ liệu phân bổ chi phí và truy vấn tài nguyên sẽ thiếu nhất quán. Ví dụ, cùng ý nghĩa môi trường nhưng có thể xuất hiện các tag **Environment**, **environment**, **Env** với value **production**, **prod** hoặc **prd**.

Service Catalog cung cấp TagOption library để quản trị viên định nghĩa các cặp key-value được phép dùng. Một TagOption là dữ liệu quản lý trong Service Catalog, không phải AWS tag ngay khi được tạo. Khi gắn TagOption vào product hoặc portfolio và người dùng triển khai product, Service Catalog tổng hợp các lựa chọn liên quan rồi áp dụng tag tương ứng lên provisioned product.

Ví dụ, portfolio có các TagOption:

| Key | Giá trị được định nghĩa |
|---|---|
| **Environment** | dev, test, prod |
| **CostCenter** | CC100, CC200 |
| **DataClassification** | public, internal, confidential |
| **OwnerTeam** | platform, payments, analytics |

Khi product được gắn các TagOption này, người dùng có thể phải chọn giá trị phù hợp trong quá trình triển khai. Nếu một key chỉ có một giá trị, Service Catalog có thể tự áp dụng giá trị đó. Khi cùng key có nhiều giá trị được gắn ở portfolio và product, tập giá trị khả dụng được tổng hợp theo quy tắc của TagOption; quản trị viên cần tránh cấu hình xung đột khiến giá trị tag không còn hợp lệ.

TagOption đặc biệt hữu ích để chuẩn hóa tag trên các provisioned product CloudFormation. AWS Service Catalog hiện không hỗ trợ TagOptions cho product Terraform Open Source hoặc Terraform Cloud, vì vậy cần kiểm tra loại product trước khi thiết kế quy trình tagging.

TagOption giúp người dùng chọn trong một tập giá trị được quản trị, nhưng tổ chức vẫn nên dùng thêm cơ chế tag governance phù hợp. AWS Organizations Tag Policies có thể giúp chuẩn hóa key, cách viết và value cho các dịch vụ được hỗ trợ; IAM condition hoặc SCP có thể chặn một số thao tác thiếu tag khi API hỗ trợ điều kiện tương ứng; AWS Config có thể phát hiện tài nguyên thiếu hoặc sai tag. Không nên giả định chỉ cần tạo TagOption là mọi tài nguyên trong tài khoản đều có tag bắt buộc.

## 5. Chia sẻ catalog giữa nhiều AWS account

Trong mô hình nhiều account, nhóm nền tảng có thể quản lý product tại một account trung tâm rồi phân phối portfolio tới các account thành viên.

AWS Service Catalog hỗ trợ chia sẻ portfolio theo account-to-account hoặc thông qua AWS Organizations. Với chia sẻ dạng tham chiếu, portfolio được nhập ở account nhận và giữ đồng bộ với portfolio gốc. Product và constraint do account nguồn quản lý sẽ được cập nhật theo thay đổi ở nguồn; quản trị viên account nhận có thể cấp quyền cho principal cục bộ và, tùy mô hình, bổ sung cấu hình cục bộ trong portfolio riêng.

Có thể chia sẻ tới:

- Một AWS account cụ thể.
- Một Organizational Unit (OU).
- Toàn bộ organization.

Chia sẻ qua AWS Organizations phù hợp khi tổ chức có cấu trúc OU rõ ràng. Ví dụ, portfolio Production có thể được chia sẻ tới OU Production; portfolio thử nghiệm chỉ chia sẻ tới OU Sandbox. Việc sử dụng OU giúp quyền truy cập portfolio đi theo cấu trúc quản lý account của tổ chức.

Một số điểm cần kiểm tra khi chia sẻ:

1. Tích hợp AWS Organizations phải được bật cho Service Catalog; thao tác bật quyền tích hợp thuộc management account.
2. Việc chia sẻ tới organization node được thực hiện bởi management account hoặc delegated administrator đã đăng ký phù hợp.
3. Portfolio import và chia sẻ cần được thiết kế theo Region; việc chia sẻ tham chiếu không đồng nghĩa portfolio tự xuất hiện ở mọi Region.
4. Khi account được chuyển sang OU khác, quyền truy cập portfolio có thể thay đổi theo phạm vi chia sẻ của OU đích.
5. Không thể chia sẻ lại một shared resource theo cách tùy ý; cần thiết kế rõ account nguồn, account phân phối và account tiêu thụ.

Chia sẻ portfolio dạng tham chiếu khác với triển khai một bản sao catalog. Nếu muốn phân phối bản sao cấu hình tới nhiều account, có thể cân nhắc CloudFormation StackSets để triển khai các tài nguyên catalog cần thiết. Với bản sao, thay đổi ở nguồn cần được triển khai lại theo quy trình tương ứng. Chọn mô hình nào cần dựa trên yêu cầu về quyền sở hữu, khả năng tùy biến tại account nhận và cách cập nhật.

## 6. Quy trình xây dựng danh mục hạ tầng được phê duyệt

Một catalog có giá trị khi mỗi product có tiêu chí chấp nhận, chủ sở hữu và vòng đời rõ ràng. Quy trình tham khảo dưới đây phù hợp với nhóm nền tảng quản lý nhiều dịch vụ AWS.

### Bước 1: Xác định nhu cầu và tiêu chuẩn

Thu thập nhu cầu từ các nhóm sử dụng, sau đó xác định baseline cho từng product. Với một product lưu trữ dữ liệu, tiêu chuẩn có thể gồm mã hóa, chặn truy cập công khai, versioning, tag phân loại dữ liệu, logging và chính sách lưu giữ. Với product compute, tiêu chuẩn có thể gồm AMI được phê duyệt, security group, subnet, logging, quyền instance profile và giới hạn kích thước.

Mỗi product cần xác định:

- Chủ sở hữu kỹ thuật và nhóm hỗ trợ.
- Nhóm người dùng, account và Region được phép triển khai.
- Các tham số được phép thay đổi.
- Quyền IAM cần thiết và giới hạn chi phí.
- Yêu cầu backup, logging, monitoring, mã hóa và cập nhật.
- Tiêu chí kiểm thử, quy trình phê duyệt và thời hạn rà soát.

### Bước 2: Đóng gói template

Tạo template CloudFormation hoặc loại template Terraform mà Service Catalog hỗ trợ. Template nên thể hiện rõ tài nguyên, phụ thuộc, tham số, output và các cấu hình bảo mật mặc định. Dùng parameter validation để loại bỏ đầu vào không hợp lệ ngay từ template.

Ví dụ rút gọn dưới đây tạo một bucket S3 có mã hóa phía máy chủ, bật versioning và chặn truy cập công khai. Trong môi trường cần quản lý khóa tập trung, tổ chức có thể thay cấu hình mã hóa mẫu bằng AWS KMS key được phê duyệt và bổ sung quyền key policy tương ứng.

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Approved S3 bucket baseline for application data

Parameters:
  Environment:
    Type: String
    AllowedValues:
      - dev
      - test
      - prod
    Default: dev
  DataClassification:
    Type: String
    AllowedValues:
      - internal
      - confidential
    Default: internal

Resources:
  ApplicationDataBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketEncryption:
        ServerSideEncryptionConfiguration:
          - ServerSideEncryptionByDefault:
              SSEAlgorithm: AES256
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        IgnorePublicAcls: true
        BlockPublicPolicy: true
        RestrictPublicBuckets: true
      VersioningConfiguration:
        Status: Enabled
      Tags:
        - Key: Environment
          Value: !Ref Environment
        - Key: DataClassification
          Value: !Ref DataClassification

Outputs:
  BucketName:
    Description: Name of the provisioned data bucket
    Value: !Ref ApplicationDataBucket
~~~

Đây chỉ là ví dụ về baseline tối thiểu, không phải template production hoàn chỉnh. Trước khi phát hành, cần đánh giá yêu cầu về KMS, bucket policy, access logging, lifecycle, replication, backup, quyền truy cập dữ liệu và quy định lưu giữ của tổ chức.

### Bước 3: Kiểm thử và phê duyệt version

Triển khai template trong account thử nghiệm và kiểm tra cả đường đi thành công lẫn lỗi. Xác minh tài nguyên thực tế khớp thiết kế, quyền không vượt quá nhu cầu, tag được áp dụng, log có thể truy xuất và thao tác terminate/update có hành vi dự kiến.

Nên lưu lại phiên bản template, commit hoặc artifact nguồn, kết quả kiểm thử, người phê duyệt và ghi chú thay đổi. Khi product được phát hành, thông tin version cần giúp người vận hành xác định chính xác cấu hình nào đã tạo ra provisioned product.

### Bước 4: Tạo product và portfolio

Đưa template đã được phê duyệt vào Service Catalog dưới dạng product. Tạo version có mô tả dễ hiểu, sau đó thêm product vào portfolio phù hợp. Có thể tái sử dụng cùng một product ở nhiều portfolio để tránh duy trì nhiều bản template gần giống nhau.

### Bước 5: Cấu hình quyền và constraint

Gán principal phù hợp cho portfolio. Tạo launch role có quyền tối thiểu cần thiết và gắn launch constraint cho từng product-portfolio association. Thêm template constraint để giới hạn tham số theo nhóm người dùng. Cấu hình notification constraint nếu nhóm vận hành cần nhận sự kiện provisioning qua SNS; dùng Stack Set constraint khi yêu cầu triển khai sản phẩm theo nhiều account và Region.

### Bước 6: Gắn TagOption và chia sẻ

Định nghĩa bộ tag thống nhất, gắn TagOption vào portfolio hoặc product khi loại product hỗ trợ. Chia sẻ portfolio tới account hoặc OU theo mô hình quản trị. Sau khi chia sẻ, xác minh principal ở account nhận nhìn thấy đúng product, chỉ có lựa chọn được phép và không có quyền ngoài phạm vi.

### Bước 7: Theo dõi, rà soát và cải tiến

Theo dõi trạng thái provisioned product, sự kiện CloudFormation hoặc Terraform, thông báo SNS và CloudTrail. Dùng AWS Config hoặc Security Hub để kiểm tra cấu hình thực tế theo các control phù hợp. Định kỳ rà soát product không còn chủ sở hữu, version lỗi thời, portfolio chia sẻ quá rộng, role dư quyền và provisioned product không còn cần thiết.

## 7. Ví dụ: phát hành product bucket dữ liệu cho nhiều nhóm

Giả sử tổ chức có ba nhóm: Analytics, Payments và Platform. Nhóm Platform sở hữu template bucket chuẩn. Nhóm Analytics cần bucket chứa dữ liệu nội bộ; nhóm Payments cần bucket cho dữ liệu nhạy cảm với yêu cầu mã hóa bằng KMS và quyền truy cập chặt hơn.

Một cách thiết kế có thể là:

1. Platform tạo product **Application Data Bucket** từ template đã rà soát và phát hành các version theo quy trình.
2. Tạo portfolio **Data Platform** và thêm product vào portfolio.
3. Tạo launch role cho product, chỉ cho phép thao tác cần thiết trên các tài nguyên liên quan.
4. Thêm TagOption cho **OwnerTeam**, **Environment**, **CostCenter** và **DataClassification**.
5. Tạo portfolio hoặc constraint phù hợp cho từng mức phân loại dữ liệu. Với Payments, chỉ cho phép lựa chọn và cấu hình đáp ứng tiêu chuẩn dữ liệu nhạy cảm.
6. Chia sẻ portfolio tới các OU hoặc account đích bằng AWS Organizations.
7. Cấp portfolio access cho IAM role của Analytics và Payments.
8. Ghi nhận sự kiện triển khai qua CloudTrail; dùng AWS Config để kiểm tra encryption, public access block và các yêu cầu cấu hình khác.

Sơ đồ luồng quản trị:

~~~mermaid
flowchart TD
    A[Nhóm nền tảng xác định baseline] --> B[Template được kiểm thử và phê duyệt]
    B --> C[Product và product version]
    C --> D[Portfolio theo nhóm hoặc môi trường]
    D --> E[IAM principal và launch constraint]
    E --> F[End user triển khai provisioned product]
    F --> G[CloudTrail, Config và thông báo vận hành]
    G --> H[Rà soát, cập nhật version và cải tiến]
~~~

Trong ví dụ này, Analytics và Payments có thể dùng chung product gốc nhưng nhận portfolio hoặc constraint khác nhau. Nếu hai nhóm có yêu cầu kiến trúc khác hẳn nhau, nhóm Platform nên cân nhắc tách product để dễ kiểm thử và chịu trách nhiệm. Không nên tạo nhiều portfolio chỉ để che giấu sự khác biệt chưa được mô hình hóa trong template.

## 8. Bằng chứng kiểm toán cần lưu

Một danh mục được phê duyệt phải cho phép trả lời các câu hỏi: ai được phép triển khai, product nào đã được duyệt, phiên bản nào được sử dụng, tài nguyên nào được tạo và cấu hình thực tế có tuân thủ hay không.

| Câu hỏi kiểm toán | Bằng chứng nên thu thập |
|---|---|
| Ai được phép xem và triển khai product? | IAM policy, danh sách principal của portfolio, cấu hình IAM Identity Center hoặc role liên quan |
| Product nào được phê duyệt? | Product ID, portfolio, mô tả, chủ sở hữu, version, template nguồn và hồ sơ phê duyệt |
| Người dùng đã triển khai product nào? | Provisioned product record, product version, thời điểm triển khai và định danh principal |
| Quyền tạo tài nguyên có bị giới hạn không? | Launch constraint, trust policy, permission policy và kết quả rà soát quyền |
| Tham số nào được phép? | Template, parameter validation và template constraint gắn với portfolio |
| Tài nguyên thuộc nhóm hoặc chi phí nào? | TagOption, tag thực tế, owner, environment, cost center và báo cáo chi phí |
| Ai thay đổi catalog hoặc quyền chia sẻ? | CloudTrail events, lịch sử thay đổi, change request và người phê duyệt |
| Tài nguyên thực tế có tuân thủ baseline? | AWS Config evaluation, Security Hub findings, log triển khai và kết quả khắc phục |

CloudTrail giúp truy vết thao tác API và thay đổi quản trị; AWS Config giúp đánh giá cấu hình tài nguyên theo rule; Security Hub có thể tổng hợp phát hiện bảo mật từ các nguồn tích hợp. Các công cụ này bổ sung cho Service Catalog: catalog mô tả con đường triển khai được tổ chức cung cấp, còn công cụ kiểm toán giúp xác minh ai đã thao tác và tài nguyên thực tế có đáp ứng yêu cầu hay không.

Không nên chỉ lưu ảnh chụp màn hình của trang portfolio. Bằng chứng nên có định danh tài nguyên, thời gian, principal, version và nguồn sự kiện để có thể đối chiếu lại. Với thay đổi quan trọng, liên kết sự kiện AWS với ticket hoặc change request của tổ chức.

## 9. Rủi ro thường gặp và cách xử lý

### Cấp quyền quá rộng cho launch role

Nếu launch role có quyền quản trị toàn tài khoản, người dùng có thể gián tiếp tạo ra tài nguyên hoặc thay đổi vượt quá mục đích của product. Hãy rà soát action và resource theo template, tách role theo product hoặc nhóm product có cùng nhu cầu, rồi kiểm thử với quyền tối thiểu.

### Cho rằng có catalog là đã chặn mọi cách tạo tài nguyên

Service Catalog quản lý việc phân phối và triển khai product. Nếu IAM vẫn cho phép người dùng gọi trực tiếp EC2, RDS, S3 hoặc các API khác, họ có thể tạo tài nguyên ngoài catalog. Dùng IAM, SCP và các guardrail khác để xác định đường tạo tài nguyên được phép; dùng Config để phát hiện sai lệch còn lại.

### Product được phát hành nhưng không có chủ sở hữu

Template cũ có thể chứa AMI, tham số hoặc cấu hình không còn phù hợp. Mỗi product cần owner, lịch rà soát, quy trình phát hành version và đầu mối hỗ trợ. Nên có kế hoạch thông báo và xử lý các provisioned product đang dùng version cũ.

### Nhầm lẫn giữa phát hành version và cập nhật instance

Version mới được thêm vào catalog không đồng nghĩa các instance đang chạy được cập nhật ngay. Quản trị viên cần lập kế hoạch update provisioned product, đánh giá thay đổi có phá vỡ tương thích hay không và theo dõi kết quả sau cập nhật.

### Chia sẻ portfolio sai phạm vi

Chia sẻ tới toàn organization có thể rộng hơn nhu cầu. Hãy chọn OU hoặc account đích theo nguyên tắc least privilege, rà soát delegated administrator, kiểm tra quyền ở account nhận và đánh giá lại khi account được di chuyển giữa các OU.

### TagOption xung đột hoặc bị xem là cơ chế bắt buộc toàn tài khoản

Giá trị TagOption cần được quản trị nhất quán giữa portfolio và product. Cần kiểm tra các key trùng lặp, giá trị giao nhau và loại product có hỗ trợ TagOption. Đối với yêu cầu tag áp dụng trên tài nguyên được tạo ngoài catalog, dùng thêm Tag Policies, IAM/SCP condition và AWS Config theo mức hỗ trợ của dịch vụ.

### Xóa product nhưng quên provisioned product đang chạy

Gỡ product khỏi portfolio có thể ngăn các lần triển khai mới, nhưng provisioned product đã được tạo trước đó vẫn có thể tiếp tục chạy. Trước khi ngừng product, cần lập danh sách instance hiện hữu, xác định owner, quyết định cập nhật, di chuyển hoặc terminate và đánh giá ảnh hưởng dữ liệu.

## 10. Checklist trước khi công bố một product

- [ ] Product có mục đích, owner, nhóm hỗ trợ và phạm vi Region/account rõ ràng.
- [ ] Template đã được rà soát về IAM, network, encryption, backup, logging, monitoring và chi phí.
- [ ] Parameter có validation; constraint theo portfolio đã được kiểm thử.
- [ ] Launch role có trust policy đúng và quyền tối thiểu cần thiết.
- [ ] Product version có mô tả, nguồn template và kết quả kiểm thử.
- [ ] Portfolio chỉ cấp cho principal và nhóm người dùng phù hợp.
- [ ] TagOption hoặc cơ chế tag thay thế đáp ứng yêu cầu phân loại và phân bổ chi phí.
- [ ] Chia sẻ cross-account đúng OU/account và đã xác minh ở phía nhận.
- [ ] CloudTrail, AWS Config, SNS hoặc hệ thống giám sát liên quan có thể cung cấp bằng chứng cần thiết.
- [ ] Có quy trình cập nhật version, xử lý instance cũ và ngừng hỗ trợ product.

## 11. Ghi nhớ

AWS Service Catalog biến các mẫu hạ tầng đã được tổ chức chuẩn bị thành một danh mục tự phục vụ có kiểm soát. Product mô tả thứ có thể triển khai; version quản lý thay đổi; portfolio phân phối product theo nhóm; principal xác định người dùng; constraint giới hạn cách triển khai; launch role tách quyền provisioning khỏi quyền cá nhân; TagOption chuẩn hóa lựa chọn tag.

Để danh mục thực sự hỗ trợ kiểm toán và tuân thủ, tổ chức cần duy trì vòng đời product, giới hạn quyền bằng IAM và guardrail cấp tổ chức, phân phối portfolio đúng phạm vi account/OU, đồng thời đối chiếu sự kiện CloudTrail và trạng thái tài nguyên qua AWS Config hoặc công cụ bảo mật liên quan. Catalog tạo ra con đường chuẩn; các lớp quản trị và giám sát xác minh rằng hạ tầng được triển khai và vận hành theo chuẩn đó.

## Tài liệu tham khảo

- [Overview of AWS Service Catalog](https://docs.aws.amazon.com/servicecatalog/latest/adminguide/what-is_concepts.html)
- [Using AWS Service Catalog Constraints](https://docs.aws.amazon.com/servicecatalog/latest/adminguide/constraints.html)
- [AWS Service Catalog Launch Constraints](https://docs.aws.amazon.com/servicecatalog/latest/adminguide/constraints-launch.html)
- [AWS Service Catalog TagOption Library](https://docs.aws.amazon.com/servicecatalog/latest/adminguide/tagoptions.html)
- [Sharing a Portfolio](https://docs.aws.amazon.com/servicecatalog/latest/adminguide/catalogs_portfolios_sharing_how-to-share.html)
- [Granting Access to Users](https://docs.aws.amazon.com/servicecatalog/latest/adminguide/catalogs_portfolios_users.html)
- [Launching a Product](https://docs.aws.amazon.com/servicecatalog/latest/userguide/enduser-launch.html)
