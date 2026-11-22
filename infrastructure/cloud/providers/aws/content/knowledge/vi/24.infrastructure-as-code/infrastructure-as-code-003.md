# Dependency, nested stack và cross-stack reference

> **Chương:** Hạ tầng dưới dạng mã  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — khám phá hệ sinh thái AWS qua Region/AZ, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; rèn khả năng chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có giám sát, phục hồi và kiểm soát chi phí.

Một hệ thống AWS thường được chia thành nhiều lớp: mạng, bảo mật, dữ liệu, ứng dụng và quan sát. Một EC2 instance cần VPC và subnet; một application stack cần biết VPC ID; một workload cần security group, IAM role và database endpoint. Khi triển khai bằng Infrastructure as Code (IaC), các quan hệ này phải được biểu diễn thành **dependency graph** rõ ràng.

AWS CloudFormation cung cấp ba cơ chế thường dùng:

- **Implicit dependency:** CloudFormation suy ra thứ tự từ `Ref`, `Fn::GetAtt` và các biểu thức tham chiếu resource.
- **Explicit dependency:** `DependsOn` khai báo quan hệ thứ tự mà template không thể tự suy ra.
- **Stack composition:** nested stacks và cross-stack references chia template thành các đơn vị có ranh giới, outputs và lifecycle phù hợp.

Nếu thiết kế sai, deployment có thể gặp circular dependency, stack update bị khóa bởi export đang được import, nested stack rollback khó truy vết hoặc một thay đổi nhỏ buộc phải deploy nhiều stack theo thứ tự thủ công. Bài học này tập trung vào CloudFormation và cách AWS CDK biểu diễn những quan hệ tương tự.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích dependency graph và thứ tự create/update/delete resource.
2. Phân biệt dependency được suy ra tự động với `DependsOn`.
3. Chia template lớn thành nested stacks theo ranh giới ownership và lifecycle.
4. Truyền outputs từ nested stack về parent bằng `Fn::GetAtt`.
5. Dùng CloudFormation Outputs/Exports và `Fn::ImportValue` giữa các stack độc lập.
6. Hiểu giới hạn Region/account, export immutability và quy trình thay đổi contract.
7. Nhận diện circular dependencies và chọn cách tách resource/stack để phá vòng lặp.
8. Thiết kế deploy order, rollback, deletion và migration khi stack phụ thuộc nhau.
9. Hiểu cross-stack references được AWS CDK tổng hợp như thế nào.
10. Kiểm thử template và dependency graph trước khi triển khai vào AWS.

## 2. Dependency graph trong IaC

Dependency là quan hệ cho biết **một resource cần resource khác sẵn sàng trước khi tạo hoặc cập nhật**. CloudFormation xây dựng directed acyclic graph (DAG) từ các quan hệ này để xác định thứ tự thực thi.

Ví dụ một ứng dụng web:

~~~mermaid
flowchart TD
    VPC["VPC"] --> SUBNET["Private subnet"]
    VPC --> SG["Application security group"]
    SUBNET --> INSTANCE["Application EC2"]
    SG --> INSTANCE
    ROLE["IAM role"] --> PROFILE["Instance profile"]
    PROFILE --> INSTANCE
    DB["Database"] --> APP["Application configuration"]
    INSTANCE --> APP
~~~

Các mũi tên trong sơ đồ có nghĩa **resource ở đầu mũi tên phải sẵn sàng trước resource ở cuối mũi tên**. Đây là cách nhìn logic; CloudFormation có thể tạo những resource không phụ thuộc nhau song song.

### 2.1. Vì sao cần khai báo dependency?

Không khai báo quan hệ đúng có thể khiến:

- Resource được tạo trước khi network attachment hoặc policy cần thiết hoàn tất.
- Application nhận ID/ARN/endpoint không tồn tại hoặc chưa sẵn sàng.
- Update chạy theo thứ tự gây gián đoạn hoặc lỗi validation.
- Delete resource nền trước resource còn đang tham chiếu nó.
- Một stack bị kẹt vì export/import dependency chưa được tháo gỡ.

Dependency graph giúp CloudFormation biết **thứ tự thao tác**, nhưng không bảo đảm application đã sẵn sàng về mặt nghiệp vụ. Ví dụ EC2 instance ở trạng thái `CREATE_COMPLETE` không đồng nghĩa ứng dụng trong instance đã pass health check.

### 2.2. Create, update và delete

CloudFormation tạo resource theo chiều dependency: dependency được tạo trước, resource phụ thuộc được tạo sau. Khi xóa, thứ tự được đảo ngược để resource phụ thuộc được xóa trước dependency.

| Thao tác | Quy tắc khái quát |
| --- | --- |
| Create | Dependency trước, dependent sau |
| Update | Theo graph và loại thay đổi; một số thay đổi có thể replacement |
| Delete | Dependent trước, dependency sau |
| Rollback | CloudFormation đảo ngược các thay đổi đã thực hiện theo khả năng của từng resource |

Một thay đổi có thể yêu cầu replacement resource, tạo ra giai đoạn có cả resource cũ và mới. Hãy đọc Change Set và thuộc tính `Update requires` của resource trước khi deploy.

## 3. Implicit dependency: Ref, GetAtt và Sub

CloudFormation tự suy ra dependency khi một resource tham chiếu resource khác trong thuộc tính của nó.

### 3.1. Ví dụ Ref

~~~yaml
Parameters:
  CloudFrontDistributionArn:
    Type: String
    Description: ARN of the distribution allowed to read this bucket

Resources:
  AppBucket:
    Type: AWS::S3::Bucket

  AppBucketPolicy:
    Type: AWS::S3::BucketPolicy
    Properties:
      Bucket: !Ref AppBucket
      PolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              Service: cloudfront.amazonaws.com
            Condition:
              StringEquals:
                AWS:SourceArn: !Ref CloudFrontDistributionArn
            Action: s3:GetObject
            Resource: !Sub "${AppBucket.Arn}/*"
~~~

Parameter `CloudFrontDistributionArn` nhận ARN của CloudFront distribution được phép truy cập bucket. Condition `AWS:SourceArn` giới hạn service principal vào distribution đó thay vì cho phép mọi CloudFront distribution.

`Bucket: !Ref AppBucket` tạo dependency rõ ràng: bucket phải được tạo trước bucket policy. `!Sub` tham chiếu `AppBucket.Arn` cũng là resource reference và CloudFormation suy ra dependency.

### 3.2. Ref và GetAtt trả về giá trị khác nhau

| Intrinsic function | Giá trị điển hình |
| --- | --- |
| `Ref` | Giá trị mặc định được định nghĩa cho resource, thường là ID hoặc tên |
| `Fn::GetAtt` | Một attribute cụ thể như ARN, DNS name, endpoint hoặc output |
| `Fn::Sub` | Chuỗi được nội suy; reference đến logical ID/attribute tạo dependency |
| `Fn::Join` | Ghép chuỗi; các phần tử có Ref/GetAtt vẫn tạo dependency |

Không giả định `Ref` luôn là ARN. Hãy kiểm tra tài liệu resource type và thuộc tính cần dùng. Ví dụ `Ref` của S3 bucket trả bucket name; ARN phải dùng `!GetAtt Bucket.Arn`.

### 3.3. Ví dụ VPC và subnet

~~~yaml
Resources:
  AppVpc:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: 10.40.0.0/16
      EnableDnsSupport: true
      EnableDnsHostnames: true
      Tags:
        - Key: Name
          Value: app-vpc

  AppSubnet:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref AppVpc
      CidrBlock: 10.40.10.0/24
      AvailabilityZone: !Select
        - 0
        - !GetAZs ""
~~~

`AppSubnet` phụ thuộc vào `AppVpc` vì `VpcId` tham chiếu VPC. Không cần thêm `DependsOn: AppVpc`; dependency đã tồn tại trong template.

### 3.4. Dependency trong Fn::Sub

`Fn::Sub` có thể tham chiếu:

- Parameter: `${EnvironmentName}`
- Pseudo parameter: `${AWS::Region}`
- Resource logical ID: `${AppBucket}`
- Resource attribute: `${AppBucket.Arn}`
- Variable map được truyền riêng cho `Fn::Sub`.

Tham chiếu logical ID hoặc attribute tạo implicit dependency. Nếu cần giữ nguyên một token dạng biến trong chuỗi, dùng cú pháp escape mà Fn::Sub hỗ trợ thay vì để CloudFormation nội suy nó.

## 4. Explicit dependency với DependsOn

`DependsOn` dùng khi thứ tự cần thiết **không được thể hiện bằng một giá trị Ref/GetAtt**. CloudFormation sẽ chờ resource được chỉ định đạt trạng thái tạo thành công trước khi tạo resource hiện tại.

### 4.1. Ví dụ Internet Gateway attachment

Một route tới Internet Gateway cần gateway được attach vào VPC. Route có thể tham chiếu `InternetGateway` nhưng chưa tham chiếu resource attachment; do đó cần khai báo dependency rõ:

~~~yaml
Resources:
  AppVpc:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: 10.50.0.0/16

  InternetGateway:
    Type: AWS::EC2::InternetGateway

  GatewayAttachment:
    Type: AWS::EC2::VPCGatewayAttachment
    Properties:
      VpcId: !Ref AppVpc
      InternetGatewayId: !Ref InternetGateway

  PublicRouteTable:
    Type: AWS::EC2::RouteTable
    Properties:
      VpcId: !Ref AppVpc

  DefaultInternetRoute:
    Type: AWS::EC2::Route
    DependsOn: GatewayAttachment
    Properties:
      RouteTableId: !Ref PublicRouteTable
      DestinationCidrBlock: 0.0.0.0/0
      GatewayId: !Ref InternetGateway
~~~

Ở đây:

- `GatewayAttachment` tự phụ thuộc VPC và Internet Gateway qua `Ref`.
- `DefaultInternetRoute` tham chiếu route table và gateway.
- `DependsOn: GatewayAttachment` bổ sung thứ tự attach gateway trước khi tạo route.

### 4.2. Khi nào nên dùng DependsOn?

Dùng `DependsOn` khi:

- API yêu cầu một resource attachment/association đã hoàn tất trước resource tiếp theo.
- Một resource cần chờ policy, permission hoặc association được tạo mà không có thuộc tính reference trực tiếp.
- Có quan hệ thứ tự thực tế nhưng không được biểu diễn trong thuộc tính resource.

Không thêm `DependsOn` cho mọi resource. Dependency thừa làm graph cứng hơn, giảm khả năng chạy song song và có thể tạo thứ tự update/delete không cần thiết.

### 4.3. DependsOn không phải readiness check

`DependsOn` chỉ điều phối CloudFormation resource lifecycle. Nó không:

- Chờ application health endpoint trả HTTP 200.
- Chờ database migration hoàn tất.
- Chờ message consumer xử lý hết queue.
- Bảo đảm DNS propagation đã hoàn tất ở mọi resolver.

Với readiness của ứng dụng, dùng health checks, deployment controller, custom resource có timeout/retry phù hợp hoặc pipeline orchestration sau khi stack hoàn tất.

## 5. Nested stack là gì?

**Nested stack** là một CloudFormation stack được tạo và quản lý như một resource bên trong stack cha. Stack cha khai báo resource có type `AWS::CloudFormation::Stack`, trỏ đến template con bằng `TemplateURL` và truyền Parameters.

Nested stack giúp chia một template lớn thành các phần có cấu trúc rõ nhưng vẫn giữ một lifecycle triển khai tổng thể:

~~~mermaid
flowchart TB
    P["Root stack: ProductPlatform"]
    P --> N["Nested stack: Network"]
    P --> S["Nested stack: Security"]
    P --> D["Nested stack: Data"]
    P --> A["Nested stack: Application"]
    N --> V["VPC / Subnets / Routes"]
    S --> I["IAM / Security Groups"]
    D --> R["RDS / DynamoDB"]
    A --> E["ECS / Lambda / API"]
~~~

Ví dụ cách chia:

- `network.yaml`: VPC, subnets, route tables, endpoints.
- `security.yaml`: security groups, IAM roles/policies.
- `data.yaml`: database, subnet groups, parameter groups.
- `application.yaml`: ECS services, Lambda functions, API.
- `root.yaml`: điều phối nested stacks và truyền outputs.

### 5.1. Khi nào nên dùng nested stack?

Nested stack phù hợp khi:

- Template cha lớn và cần chia theo domain/resource group.
- Các resource thường được deploy, update và rollback cùng một đơn vị.
- Team muốn tái sử dụng một template con trong nhiều parent stacks.
- Cần giới hạn số resource/độ phức tạp trong một template.
- Muốn thể hiện quan hệ parent-child rõ trong CloudFormation console và stack events.

Không nên tạo nested stack chỉ để mỗi file có ít dòng. Chọn ranh giới theo **ownership, lifecycle, failure domain và change frequency**.

### 5.2. Nested stack khác stack độc lập

| Đặc điểm | Nested stack | Stack độc lập |
| --- | --- | --- |
| Ownership | Stack cha quản lý child stack resource | Có lifecycle riêng |
| Deploy | Parent update điều phối child | Pipeline/Operator deploy riêng |
| Truyền output | `Fn::GetAtt Child.Outputs.Name` | Export/ImportValue hoặc contract khác |
| Delete | Parent xóa child theo lifecycle mặc định | Phải xử lý dependency và delete riêng |
| Reuse | Template con có thể dùng lại | Stack có thể độc lập theo môi trường/domain |
| Failure | Child failure có thể làm parent update fail/rollback | Lỗi thường giới hạn ở stack được deploy |

Nested stack không phải một cơ chế chia sẻ resource tự do giữa nhiều parent. Một child stack resource thuộc về parent cụ thể; đừng cố quản lý cùng một tài nguyên từ hai stack.

## 6. Tạo nested stack và truyền Parameters

Stack cha tham chiếu template con qua `TemplateURL`. Template thường được lưu trong S3; với pipeline production, nên dùng object key/version bất biến hoặc artifact có checksum để parent luôn trỏ tới đúng phiên bản đã kiểm thử.

### 6.1. Template con: network.yaml

~~~yaml
AWSTemplateFormatVersion: "2010-09-09"
Description: Network resources for the product platform

Parameters:
  VpcCidr:
    Type: String
    Default: 10.60.0.0/16

Resources:
  AppVpc:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: !Ref VpcCidr
      EnableDnsSupport: true
      EnableDnsHostnames: true
      Tags:
        - Key: Name
          Value: product-platform-vpc

  PrivateSubnetA:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref AppVpc
      CidrBlock: 10.60.10.0/24
      AvailabilityZone: !Select
        - 0
        - !GetAZs ""

Outputs:
  VpcId:
    Description: VPC identifier for dependent stacks
    Value: !Ref AppVpc

  PrivateSubnetAId:
    Description: Private subnet identifier
    Value: !Ref PrivateSubnetA
~~~

Template con chỉ xuất những giá trị mà stack khác thực sự cần. Không export mọi resource attribute; outputs là **contract công khai** của template.

### 6.2. Template cha: root.yaml

~~~yaml
AWSTemplateFormatVersion: "2010-09-09"
Description: Root stack for the product platform

Parameters:
  NetworkTemplateUrl:
    Type: String
    Description: Immutable S3 URL for the network template

  ApplicationTemplateUrl:
    Type: String
    Description: Immutable S3 URL for the application template

Resources:
  NetworkStack:
    Type: AWS::CloudFormation::Stack
    Properties:
      TemplateURL: !Ref NetworkTemplateUrl
      TimeoutInMinutes: 20
      Parameters:
        VpcCidr: 10.60.0.0/16
      Tags:
        - Key: Component
          Value: network

  ApplicationStack:
    Type: AWS::CloudFormation::Stack
    Properties:
      TemplateURL: !Ref ApplicationTemplateUrl
      Parameters:
        VpcId: !GetAtt NetworkStack.Outputs.VpcId
        PrivateSubnetId: !GetAtt NetworkStack.Outputs.PrivateSubnetAId

Outputs:
  PlatformVpcId:
    Value: !GetAtt NetworkStack.Outputs.VpcId

  ApplicationEndpoint:
    Value: !GetAtt ApplicationStack.Outputs.ApplicationEndpoint
~~~

`!GetAtt NetworkStack.Outputs.VpcId` tạo dependency giữa `ApplicationStack` và `NetworkStack`. CloudFormation biết phải tạo network nested stack trước khi truyền output cho application stack. Không cần `DependsOn: NetworkStack` thêm lần nữa.

### 6.3. Template con: application.yaml

~~~yaml
AWSTemplateFormatVersion: "2010-09-09"
Description: Application resources that consume network outputs

Parameters:
  VpcId:
    Type: AWS::EC2::VPC::Id
  PrivateSubnetId:
    Type: AWS::EC2::Subnet::Id

Resources:
  AppSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Application security group
      VpcId: !Ref VpcId
      SecurityGroupEgress:
        - IpProtocol: "-1"
          CidrIp: 0.0.0.0/0

  AppNetworkInterface:
    Type: AWS::EC2::NetworkInterface
    Properties:
      SubnetId: !Ref PrivateSubnetId
      GroupSet:
        - !Ref AppSecurityGroup
      Description: Example interface proving subnet and security group dependencies

Outputs:
  NetworkInterfaceId:
    Value: !Ref AppNetworkInterface

  ApplicationEndpoint:
    Description: Placeholder output for the application endpoint
    Value: !Sub "https://example.invalid/${AWS::Region}/app"
~~~

Template này minh họa cách nhận VPC/subnet IDs. Trong application thực tế, subnet sẽ được gắn vào ECS service, EC2 network interface hoặc Lambda VPC configuration; security group cần ingress/egress tối thiểu theo workload. Placeholder endpoint không đại diện một dịch vụ đang chạy.

### 6.4. TemplateURL và artifact management

- Template phải được upload trước khi parent stack tạo hoặc update nested stack.
- Parent role cần quyền đọc template artifact; bucket policy/KMS key policy cũng phải cho phép.
- Trỏ tới versioned, immutable object key để có thể tái tạo deployment.
- Không overwrite cùng một key mà không ghi nhận nội dung/version đã triển khai.
- Giữ artifact đủ lâu để rollback hoặc redeploy phiên bản trước.
- Kiểm tra giới hạn kích thước template và quyền truy cập của CloudFormation khi tải template.

Nếu template nằm trong private S3 bucket, CloudFormation phải có khả năng truy cập object theo cơ chế được hỗ trợ. Một URL có thể mở được trên máy developer không chứng minh CloudFormation service có quyền tải.

## 7. Nested stack Outputs và GetAtt

Nested stack resource trả về các attributes của stack, trong đó có outputs của template con. Parent truy cập chúng bằng dạng:

~~~yaml
!GetAtt NestedStackLogicalId.Outputs.OutputKey
~~~

Ví dụ:

~~~yaml
Parameters:
  VpcId:
    Type: String

Resources:
  AppStack:
    Type: AWS::CloudFormation::Stack
    Properties:
      TemplateURL: https://templates.example.invalid/app.yaml
      Parameters:
        VpcId: !Ref VpcId

  NetworkStack:
    Type: AWS::CloudFormation::Stack
    Properties:
      TemplateURL: https://templates.example.invalid/network.yaml

  WorkerStack:
    Type: AWS::CloudFormation::Stack
    Properties:
      TemplateURL: https://templates.example.invalid/worker.yaml
      Parameters:
        VpcId: !GetAtt NetworkStack.Outputs.VpcId
        ApplicationEndpoint: !GetAtt AppStack.Outputs.ApplicationEndpoint
~~~

`WorkerStack` phụ thuộc cả `NetworkStack` và `AppStack`. Vì vậy, CloudFormation tạo hai stack đó trước rồi mới tạo worker stack.

### 7.1. Output là chuỗi

CloudFormation Outputs có giá trị string. Nếu child stack cần xuất nhiều subnet IDs, có thể nối bằng dấu phẩy và truyền sang parameter dạng list theo schema:

~~~yaml
Outputs:
  PrivateSubnetIds:
    Value: !Join
      - ","
      - - !Ref PrivateSubnetA
        - !Ref PrivateSubnetB
~~~

Parent có thể truyền output string cho child parameter được khai báo là `List<AWS::EC2::Subnet::Id>` nếu giá trị là danh sách comma-delimited hợp lệ. Kiểm tra kiểu parameter và intrinsic function của template thực tế; đừng giả định mọi output tự động trở thành native list.

### 7.2. Truyền Parameters qua nhiều tầng

Khi parent truyền parameter xuống child:

- Parameter type, allowed values và constraints cần khớp contract.
- Default value không nên che việc parent quên truyền một giá trị bắt buộc.
- Tránh truyền secret trực tiếp qua nested stack parameter nếu có thể tham chiếu Secrets Manager/SSM dynamic reference.
- Không đưa credentials hoặc secret vào Outputs; outputs có thể hiển thị trong CloudFormation console/API và deployment logs.

### 7.3. Output contract nên nhỏ và ổn định

Một network stack có thể xuất VPC ID, subnet IDs và security group IDs. Không cần xuất toàn bộ logical resource names hoặc các thuộc tính nội bộ. Contract nhỏ giúp child stack được refactor mà consumer không cần thay đổi.

Đặt tên output có ý nghĩa theo consumer contract, ví dụ `VpcId`, `PrivateSubnetIds`, `DatabaseEndpoint`, thay vì `Value1`, `ResourceA`.

## 8. Cross-stack reference giữa các stack độc lập

Một **cross-stack reference** chia sẻ một output giữa các CloudFormation stacks độc lập. Stack cung cấp output khai báo `Export`; stack tiêu thụ dùng `Fn::ImportValue`.

Khác nested stacks, hai stack này có lifecycle riêng. CloudFormation không tự coi chúng là parent/child, nhưng export/import tạo một dependency contract được AWS quản lý.

### 8.1. Stack cung cấp: network-stack.yaml

~~~yaml
AWSTemplateFormatVersion: "2010-09-09"

Resources:
  SharedVpc:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: 10.70.0.0/16
      EnableDnsSupport: true
      EnableDnsHostnames: true

Outputs:
  SharedVpcId:
    Description: VPC ID consumed by application stacks
    Value: !Ref SharedVpc
    Export:
      Name: !Sub "${AWS::StackName}-SharedVpcId"
~~~

Export name cần duy nhất trong phạm vi account và Region. Dùng stack name/environment/component trong export name để tránh xung đột khi có nhiều môi trường.

### 8.2. Stack tiêu thụ: application-stack.yaml

~~~yaml
Parameters:
  NetworkStackName:
    Type: String
    Description: Name prefix used by the network stack export

Resources:
  AppSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Application access in shared VPC
      VpcId:
        Fn::ImportValue:
          Fn::Sub: "${NetworkStackName}-SharedVpcId"
~~~

Stack tiêu thụ không tạo VPC mới. Nó import giá trị được network stack export. Stack phải nằm **cùng AWS account và cùng Region** với stack cung cấp export.

### 8.3. Export name phải ổn định

Không đổi export name tùy tiện sau khi consumer đã import. Export name là một phần contract; đổi nó tương đương thay đổi interface giữa các stacks.

Một convention có thể dùng:

~~~text
<environment>-<domain>-<contract>-<version>

prod-network-vpc-id-v1
staging-network-private-subnets-v1
dev-security-app-sg-id-v1
~~~

Version trong export name hữu ích khi cần migration song song: tạo export v2, chuyển consumers sang v2, rồi gỡ v1 sau khi không còn importer.

## 9. Giới hạn và lifecycle của ImportValue

`Fn::ImportValue` có các giới hạn quan trọng:

1. Import chỉ hoạt động giữa stacks trong **cùng account và cùng Region**.
2. Export name phải duy nhất trong account/Region.
3. Không thể xóa stack đang export một giá trị nếu giá trị đó còn được stack khác import.
4. Không thể xóa hoặc thay đổi exported output value trong khi có importer phụ thuộc.
5. ImportValue chỉ dùng với export name tĩnh theo các giới hạn intrinsic functions được hỗ trợ; không dùng một giá trị phụ thuộc resource động làm export name.

Đây là lý do cross-stack reference cần được xem là API contract có lifecycle, không chỉ là cách lấy một string.

### 9.1. Điều gì xảy ra khi muốn đổi VPC?

Giả sử:

~~~text
NetworkStack exports: prod-network-vpc-id
ApplicationStack imports: prod-network-vpc-id
WorkerStack imports: prod-network-vpc-id
~~~

Nếu xóa hoặc đổi export ngay, CloudFormation từ chối vì consumer còn sử dụng. Cần chuyển consumer trước rồi mới gỡ export cũ.

### 9.2. Quy trình thay đổi export an toàn

~~~mermaid
flowchart TD
    OLD["Export v1 đang được consumers import"]
    NEW["Tạo export v2 song song"]
    APP["Update consumers sang v2"]
    VERIFY["Kiểm tra không còn importer v1"]
    REMOVE["Gỡ export v1"]
    OLD --> NEW --> APP --> VERIFY --> REMOVE
~~~

Trình tự:

1. Giữ nguyên export v1.
2. Thêm output/export v2 với tên mới, không sửa giá trị v1 đang được import.
3. Deploy stack provider để v1 và v2 cùng tồn tại.
4. Cập nhật từng consumer sang import v2.
5. Xác minh không còn stack nào import v1.
6. Gỡ output/export v1 trong provider stack.

Đây là migration theo kiểu **expand → migrate → contract**. Nếu thay đổi VPC/resource thật, cần thêm kế hoạch chuyển workload/network routes và rollback độc lập; đổi mỗi export string không di chuyển resource đang chạy.

## 10. Circular dependency và cách phá vòng lặp

Dependency graph phải là DAG. Nếu A phụ thuộc B và B lại phụ thuộc A, CloudFormation không thể tìm ra thứ tự tạo hợp lệ.

~~~mermaid
flowchart LR
    A["Resource A"] --> B["Resource B"]
    B --> A
~~~

Ví dụ thường gặp:

- Security group A cần security group B trong ingress rule.
- Security group B lại cần security group A trong ingress rule.
- Hai stacks import outputs của nhau.
- Nested stack con tham chiếu output từ parent theo cách tạo vòng dependency ngược.
- Resource policy tham chiếu ARN của resource mà chính resource đó lại cần policy để được tạo.

### 10.1. Ví dụ security group tạo vòng dependency

Giả sử hai nhóm workload cần mở ingress cho nhau:

~~~yaml
Resources:
  AppSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Application security group
      VpcId: !Ref AppVpc
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 8080
          ToPort: 8080
          SourceSecurityGroupId: !Ref WorkerSecurityGroup

  WorkerSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Worker security group
      VpcId: !Ref AppVpc
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 9000
          ToPort: 9000
          SourceSecurityGroupId: !Ref AppSecurityGroup
~~~

Mỗi security group tham chiếu group còn lại ngay trong resource definition. Điều này có thể tạo vòng dependency vì mỗi group cần group kia trước khi được tạo.

### 10.2. Tách ingress rules thành resource riêng

Tạo hai security groups trước, sau đó tạo ingress rules riêng:

~~~yaml
Resources:
  AppSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Application security group
      VpcId: !Ref AppVpc

  WorkerSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Worker security group
      VpcId: !Ref AppVpc

  AppIngressFromWorker:
    Type: AWS::EC2::SecurityGroupIngress
    Properties:
      GroupId: !Ref AppSecurityGroup
      IpProtocol: tcp
      FromPort: 8080
      ToPort: 8080
      SourceSecurityGroupId: !Ref WorkerSecurityGroup

  WorkerIngressFromApp:
    Type: AWS::EC2::SecurityGroupIngress
    Properties:
      GroupId: !Ref WorkerSecurityGroup
      IpProtocol: tcp
      FromPort: 9000
      ToPort: 9000
      SourceSecurityGroupId: !Ref AppSecurityGroup
~~~

Hai security group có thể được tạo độc lập; ingress resources được tạo sau khi cả hai group tồn tại. Việc tách rule ra resource riêng phá vòng dependency trong ví dụ này.

### 10.3. Cách xử lý vòng dependency ở cấp stack

- Chọn một stack làm **provider** của shared infrastructure; stack khác chỉ consume outputs.
- Tránh export/import hai chiều giữa hai stacks.
- Tách resource dùng chung thành foundation stack có lifecycle rõ.
- Nếu hai resource cần biết ID của nhau, tạo chúng ở cùng stack hoặc tách association/rule thành resource thứ ba.
- Dùng Parameters/Outputs theo một chiều, không tạo parent-child contract quay ngược lên parent.
- Nếu dependency thực sự là runtime discovery, cân nhắc service discovery/configuration store thay cho deployment-time import.

Không thể giải quyết circular dependency bằng cách thêm nhiều `DependsOn`; explicit dependency cũng tạo cạnh trong graph và có thể làm vòng lặp nghiêm trọng hơn.

## 11. Deploy order cho nhiều stacks

Khi dùng các stacks độc lập, pipeline cần hiểu dependency order. CloudFormation chỉ quản lý dependency trong một stack và export/import contract; pipeline chịu trách nhiệm điều phối việc deploy nhiều stacks.

Ví dụ:

~~~mermaid
flowchart TD
    NET["Network stack"] --> SEC["Security stack"]
    NET --> DATA["Data stack"]
    SEC --> APP["Application stack"]
    DATA --> APP
    APP --> OBS["Observability stack"]
~~~

Một thứ tự deploy hợp lý:

1. Network foundation.
2. Security/shared identity.
3. Data layer.
4. Application.
5. Observability/integration resources phụ thuộc application outputs.

Những stacks độc lập có thể chạy song song nếu pipeline biết chắc chúng không có dependency ẩn. Đừng chỉ sắp xếp theo tên stack hoặc theo thứ tự file.

### 11.1. Deploy theo Change Set

Trước khi thực thi:

- Validate template và parameters.
- Tạo Change Set cho từng stack.
- Xem resource additions, modifications, replacements và deletions.
- Kiểm tra export/import dependency và nested stack changes.
- Xác nhận replacement của VPC, subnet, database hoặc IAM role có ảnh hưởng gì.
- Thực thi theo dependency order; kiểm tra trạng thái stack trước khi chuyển bước.

Change Set cho biết CloudFormation dự định thay đổi gì, nhưng không thay thế review IAM/security và không dự đoán hoàn hảo mọi runtime behavior.

### 11.2. Rollback nhiều stack

CloudFormation rollback trong phạm vi stack đang được cập nhật. Với nhiều stacks độc lập, pipeline có thể đã deploy thành công provider nhưng consumer deploy thất bại. Cần xác định:

- Provider có thể giữ nguyên output mới mà không gây ảnh hưởng không?
- Có thể rollback consumer về version trước không?
- Export mới có thể giữ lại tạm thời để phục vụ rollback không?
- Có resource replacement hoặc data migration không thể đảo ngược không?
- Có cần forward-fix thay vì rollback database schema/data?

Không mặc định rollback một stack tự động rollback các stacks đã deploy trước đó.

### 11.3. Deploy order khi thay đổi contract

Khi thêm output mới: provider thường deploy trước, rồi consumer. Khi bỏ output cũ: consumer phải ngừng import trước, rồi provider mới xóa export. Hai tình huống có thứ tự khác nhau; pipeline phải mô hình hóa dependency cụ thể.

## 12. Nested stack update, rollback và deletion

Nested stacks có lifecycle gắn với parent. Khi parent được update, CloudFormation có thể cập nhật template/parameters của nested stack; child stack failure có thể làm parent operation thất bại.

### 12.1. Template con thay đổi

Khi sửa child template:

1. Validate child template.
2. Upload artifact mới với key/version rõ ràng.
3. Cập nhật `TemplateURL` trong parent hoặc cập nhật parameter đang trỏ đến artifact mới.
4. Tạo Change Set cho parent để xem nested stack update.
5. Deploy parent và theo dõi stack events cả parent lẫn child.

Không sửa template artifact đã được dùng bởi một deployment nếu muốn giữ khả năng tái tạo. Dùng versioned object key hoặc artifact digest để biết parent đã triển khai đúng nội dung nào.

### 12.2. Theo dõi lỗi nested stack

Khi parent stack báo `UPDATE_ROLLBACK_IN_PROGRESS`, nguyên nhân gốc có thể nằm trong child stack. Kiểm tra:

- Parent stack events để xác định nested stack logical resource bị lỗi.
- Child stack events để tìm resource cụ thể và status reason.
- IAM role, S3 TemplateURL access, parameter validation và quota.
- Resource replacement/deletion policy.
- Những stack operation đang chạy đồng thời hoặc bị khóa.

Đọc event theo timestamp và resource status reason; không chỉ nhìn trạng thái cuối của root stack.

### 12.3. Delete và Retain

Mặc định, xóa parent stack sẽ xóa nested stack resources theo lifecycle CloudFormation. Với dữ liệu cần giữ, cần chọn retention strategy có chủ đích:

- Dùng `DeletionPolicy: Retain` cho resource dữ liệu phù hợp như bucket/table/database khi muốn giữ resource sau khi stack bị xóa.
- Dùng `UpdateReplacePolicy: Retain` khi replacement không được phép xóa resource cũ.
- Lập quy trình chuyển ownership/import resource nếu cần quản lý tiếp sau khi parent bị xóa.

Không áp dụng Retain cho mọi nested stack một cách máy móc. Retain có thể để lại resource ngoài lifecycle quản lý của parent; phải có inventory, owner và cleanup/recovery plan.

### 12.4. Nested stack và rollback dữ liệu

CloudFormation có thể rollback resource configuration, nhưng không tự đảo ngược mọi thay đổi dữ liệu do migration, Lambda custom resource hoặc application deployment tạo ra. Database schema migration cần backward-compatible expand/contract, backup và recovery strategy riêng.

## 13. AWS CDK và cross-stack references

AWS CDK cho phép viết infrastructure bằng ngôn ngữ lập trình và synthesize thành CloudFormation templates. Khi một construct trong stack A tham chiếu resource từ stack B, CDK có thể tạo Outputs/Exports và ImportValue tự động nếu hai stacks có environment tương thích.

### 13.1. Ví dụ CDK tham chiếu giữa stacks

~~~java
public class NetworkStack extends Stack {
    public final IVpc vpc;

    public NetworkStack(
            Construct scope,
            String id,
            StackProps props) {
        super(scope, id, props);

        this.vpc = Vpc.Builder.create(this, "Vpc")
            .maxAzs(2)
            .natGateways(1)
            .build();
    }
}

public class ApplicationStack extends Stack {
    public ApplicationStack(
            Construct scope,
            String id,
            NetworkStack network,
            StackProps props) {
        super(scope, id, props);

        Cluster cluster = Cluster.Builder.create(this, "Cluster")
            .vpc(network.vpc)
            .build();
    }
}
~~~

Ví dụ minh họa CDK for Java; imports và props được lược bớt. `ApplicationStack` sử dụng VPC do `NetworkStack` sở hữu. Khi synthesize, CDK tạo cross-stack reference cần thiết theo cơ chế CloudFormation.

### 13.2. Điều kiện environment

Automatic cross-stack reference phù hợp nhất khi cả hai stacks có account và Region xác định, tương thích. Với stack environment-agnostic hoặc khác account/Region, CDK không thể tự tạo CloudFormation ImportValue xuyên ranh giới đó.

Đối với cross-account/Region, cần contract và cơ chế truyền giá trị phù hợp, ví dụ:

- Pipeline truyền parameter khi deploy.
- SSM Parameter Store hoặc configuration store được chia sẻ theo quyền và phạm vi phù hợp.
- AWS Resource Access Manager (RAM) cho loại resource được hỗ trợ.
- DNS/service discovery hoặc API runtime thay vì deployment-time reference.

Chọn cơ chế theo loại dữ liệu, security boundary và lifecycle; đừng giả định mọi resource ID đều có thể chia sẻ qua RAM hoặc Parameter Store.

### 13.3. CDK NestedStack

CDK có construct `NestedStack` để nhóm resources thành nested CloudFormation stack. Nó hữu ích khi template gần giới hạn kích thước/resource hoặc cần tổ chức theo component; không phải cách mặc định để chia mỗi construct nhỏ thành một stack.

Cross-stack reference giữa các CDK stacks độc lập và reference giữa nested stacks có semantics khác nhau. Kiểm tra synthesized templates để thấy resource `AWS::CloudFormation::Stack`, Outputs và ImportValue thực tế.

### 13.4. Cẩn trọng khi refactor CDK cross-stack reference

CDK có thể sinh export names tự động. Nếu đổi construct ownership hoặc xóa reference, synthesized template có thể muốn xóa export đang được consumer import. Khi đó:

1. Synth cả provider và consumer.
2. So sánh exports/imports trước và sau.
3. Giữ export cũ tạm thời nếu consumer chưa chuyển.
4. Deploy theo thứ tự expand → migrate → contract.
5. Không sửa tay template đã synthesize như giải pháp lâu dài; sửa source CDK và kiểm tra output mới.

## 14. Phân biệt nested stack, cross-stack reference và module

Các khái niệm này thường được dùng cùng nhau nhưng giải quyết những bài toán khác nhau:

| Cơ chế | Mục tiêu | Quan hệ lifecycle | Cách chia sẻ giá trị |
| --- | --- | --- | --- |
| **Nested stack** | Chia một deployment thành template con | Parent quản lý child | `Fn::GetAtt` child Outputs |
| **Cross-stack reference** | Chia các stack độc lập nhưng cần dùng chung output | Mỗi stack có lifecycle riêng; export/import khóa contract | `Export` và `Fn::ImportValue` |
| **CloudFormation module** | Đóng gói resource types/template pattern có thể tái sử dụng | Module được dùng trong template; không tạo parent-child stack chỉ vì là module | Resource properties/outputs theo module schema |
| **CDK construct** | Tái sử dụng abstraction ở source code | Phụ thuộc stack chứa construct | Reference trong construct tree và synthesized template |
| **CDK Stage** | Gom stacks thành một đơn vị trong pipeline/application | Pipeline triển khai theo stage | Cross-stack reference vẫn theo CloudFormation rules |

Đừng nhầm CloudFormation module với nested stack. Module là abstraction/resource type được đăng ký và dùng trong template; nested stack là một stack resource có child template và lifecycle riêng.

## 15. Terraform: dependency và module outputs (đối chiếu)

Trong Terraform, graph cũng được suy ra từ references:

~~~hcl
resource "aws_vpc" "app" {
  cidr_block = "10.80.0.0/16"
}

resource "aws_subnet" "private" {
  vpc_id     = aws_vpc.app.id
  cidr_block = "10.80.10.0/24"
}
~~~

`aws_subnet.private` tham chiếu `aws_vpc.app.id` nên Terraform tự suy ra dependency. Chỉ dùng `depends_on` khi có dependency hành vi không thể biểu diễn qua reference trực tiếp.

Module có thể xuất output:

~~~hcl
output "vpc_id" {
  value = aws_vpc.app.id
}
~~~

Module consumer nhận output thông qua module call. Nếu state nằm ở workspace/backend khác, có thể dùng remote state hoặc data source theo thiết kế, nhưng cần quản lý quyền đọc state và contract/version. Terraform remote state không phải CloudFormation Export/ImportValue và có semantics riêng.

Phần này chỉ đối chiếu khái niệm; các ví dụ CloudFormation/CDK ở trên là trọng tâm bài học.

## 16. Bảo mật và ownership khi chia stack

Chia stack là một quyết định về ownership. Mỗi stack nên có owner, quyền triển khai và phạm vi tài nguyên rõ ràng.

### 16.1. Least privilege cho deploy role

- Dùng deployment role riêng cho từng môi trường hoặc pipeline boundary.
- Chỉ cấp quyền tạo/sửa resource types và phạm vi cần thiết.
- Hạn chế `iam:PassRole` vào các role ứng dụng được phê duyệt.
- Quy định quyền đọc template artifact trong S3 và quyền dùng KMS key.
- Không cấp quyền xóa shared network/data resources cho pipeline ứng dụng nếu không cần.
- Dùng SCP/permission boundary để chặn hành động ngoài sandbox/production guardrail.

Stack dependency không phải security boundary. Một application stack import VPC ID không có nghĩa application role được phép thay đổi VPC; quyền IAM mới quyết định hành động được phép.

### 16.2. Outputs không phải secret store

Không xuất các giá trị như:

- Database password.
- API key hoặc access token.
- Private key, certificate private material.
- Session token hoặc long-lived AWS credentials.

CloudFormation Outputs có thể được đọc qua API/console và có thể xuất hiện trong pipeline logs. Với secret, dùng Secrets Manager hoặc Systems Manager Parameter Store dynamic references và cấp quyền đọc đúng cho workload.

### 16.3. Template artifact và nested stack

- Mã hóa S3 bucket chứa templates theo policy tổ chức.
- Giới hạn quyền upload/overwrite template artifacts.
- Giữ immutable artifact và checksum để truy nguyên deployment.
- Không đưa secret vào template literal, Metadata, Outputs hoặc Parameters không được bảo vệ.
- Xác minh CloudFormation execution role có quyền đọc artifact và KMS key cần thiết.

### 16.4. Stack policy và termination protection

Hai cơ chế này có mục đích khác nhau:

| Cơ chế | Bảo vệ điều gì? | Giới hạn |
| --- | --- | --- |
| **Stack policy** | Chặn một số update actions lên resource được bảo vệ | Không thay IAM; không phải cơ chế bảo vệ mọi delete/console action |
| **Termination protection** | Ngăn xóa toàn bộ stack ngoài ý muốn | Không ngăn mọi update hoặc resource-level change |
| **IAM/SCP** | Giới hạn ai có thể gọi API/action nào | Cần policy đúng và kiểm thử quyền |
| **DeletionPolicy/Retain** | Xác định cách xử lý resource khi stack delete/replacement theo policy | Resource retained có thể mất ownership từ stack |

Với network/data foundation stack, cân nhắc termination protection và quyền xóa hạn chế. Với resources có dữ liệu, cân nhắc DeletionPolicy/backup/retention theo yêu cầu khôi phục.

## 17. Kiểm thử dependency và stack contracts

Một template parse được chưa chắc dependency graph đúng. Cần kiểm tra cả cấu trúc, contract, lifecycle và hành vi deploy.

### 17.1. Các lớp kiểm thử

| Lớp | Công cụ/biện pháp | Điều cần xác minh |
| --- | --- | --- |
| Syntax/schema | `aws cloudformation validate-template`, `cfn-lint` | YAML/JSON, intrinsic functions, resource properties |
| Policy | CloudFormation Guard hoặc policy-as-code | Security baseline, tags, encryption, public access |
| Dependency | Review graph, cfn-lint, Change Set | Implicit/explicit edges, cycles, replacement |
| Contract | Validate outputs/parameters/exports | Output keys, export names, types và consumers |
| Integration | Deploy sandbox stack | Nested stack creation, permissions, runtime resource behavior |
| Lifecycle | Update, rollback, delete tests | Export lock, Retain, resource cleanup và recovery |
| Drift | CloudFormation drift detection | Thay đổi ngoài IaC đối với resource hỗ trợ drift detection |

### 17.2. Validate template

AWS CLI có thể kiểm tra template cơ bản:

~~~bash
aws cloudformation validate-template \
  --template-body file://root.yaml \
  --region ap-southeast-1
~~~

`validate-template` kiểm tra cấu trúc và các yếu tố template mà API hỗ trợ; nó không chứng minh tất cả runtime permissions, service quotas, cross-stack contract hoặc application readiness đều đúng.

### 17.3. Dùng cfn-lint

~~~bash
cfn-lint root.yaml network.yaml application.yaml
~~~

`cfn-lint` giúp phát hiện nhiều lỗi schema/resource property và best-practice issues. Giữ phiên bản lint tool ổn định trong CI để kết quả reproducible; đọc rule findings thay vì bỏ qua toàn bộ warnings.

### 17.4. Dùng Change Set trước update

~~~bash
aws cloudformation create-change-set \
  --stack-name product-network \
  --change-set-name review-network-update \
  --template-body file://network-stack.yaml \
  --change-set-type UPDATE \
  --region ap-southeast-1

aws cloudformation describe-change-set \
  --stack-name product-network \
  --change-set-name review-network-update \
  --region ap-southeast-1
~~~

Đây là lệnh minh họa cho stack đã tồn tại và parameters/capabilities đã được cấu hình phù hợp. Nếu template cần IAM capabilities hoặc parameters, bổ sung đúng options theo template. Không thực thi Change Set cho đến khi review resource replacement/deletion và dependency impact.

### 17.5. Tìm consumer của export

~~~bash
aws cloudformation list-imports \
  --export-name prod-network-SharedVpcId \
  --region ap-southeast-1
~~~

`list-imports` giúp xác định stack nào đang import export name. Chạy trước khi định xóa/đổi export; kiểm tra đúng account và Region đang thao tác.

### 17.6. Kiểm thử lifecycle, không chỉ create

Một stack contract test nên kiểm tra:

1. Create provider stack và consumer stack.
2. Xác nhận consumer nhận đúng output.
3. Update provider theo cách không đổi contract.
4. Thử thay contract trong sandbox để xác nhận importer lock được phát hiện.
5. Chuyển consumer sang export v2.
6. Gỡ export v1 sau khi không còn imports.
7. Delete consumer trước provider.
8. Xác minh retained resources có owner và recovery path.

Không chạy các thử nghiệm xóa hoặc replacement destructive trên shared production stacks.

## 18. Case study: network foundation và application stacks

### 18.1. Bối cảnh

Một nền tảng có nhiều ứng dụng trong cùng AWS account/Region:

~~~text
Network foundation:
  VPC, public/private subnets, route tables, VPC endpoints

Security foundation:
  Shared security groups, baseline IAM policies

Application A:
  ECS service, ALB, application task role

Application B:
  Lambda functions, API Gateway, execution role
~~~

Network thay đổi ít; ứng dụng deploy thường xuyên. Vì vậy, network và application có thể là các stacks độc lập, chia sẻ outputs theo contract một chiều.

### 18.2. Kiến trúc dependency

~~~mermaid
flowchart TD
    N["Network foundation stack"]
    S["Security foundation stack"]
    A["Application A stack"]
    B["Application B stack"]
    N --> A
    N --> B
    S --> A
    S --> B
~~~

Network stack export VPC/subnet IDs. Security stack export security group IDs hoặc role ARNs khi thực sự cần chia sẻ. Application stacks import những output cần thiết và không sở hữu resource nền.

### 18.3. Quy trình triển khai lần đầu

1. Upload và validate templates.
2. Deploy network foundation.
3. Deploy security foundation.
4. Kiểm tra exports và outputs.
5. Deploy application A/B theo pipeline; hai app có thể chạy song song nếu không phụ thuộc nhau.
6. Chạy smoke tests và xác minh resources trong đúng account/Region.

### 18.4. Thêm một private subnet mới

Giả sử network team muốn thêm subnet:

- Cập nhật network stack để tạo subnet mới.
- Thêm output versioned hoặc cập nhật output contract nếu consumer cần danh sách subnet mới.
- Nếu export đang được import và giá trị phải đổi, dùng migration contract thay vì sửa trực tiếp output bị khóa.
- Cập nhật application stacks theo từng consumer.
- Xác minh route table, network ACL, security group và VPC endpoint behavior.

Nếu output `PrivateSubnetIds` là một comma-delimited list và list thay đổi, CloudFormation có thể không cho đổi exported value trong khi còn importer. Dùng export v2 hoặc chuyển sang contract/configuration store khác nếu cần thay đổi độc lập.

### 18.5. Xóa một ứng dụng

Khi xóa application A:

1. Dừng traffic hoặc drain workload theo deployment plan.
2. Xóa application stack.
3. Kiểm tra application resources và dependencies đã được gỡ.
4. Giữ network/security foundation nếu còn ứng dụng khác sử dụng.
5. Chỉ xóa export/resource nền sau khi không còn consumers.

Không xóa network stack chỉ vì một application stack được retire.

## 19. Troubleshooting dependency và cross-stack reference

| Triệu chứng | Nguyên nhân thường gặp | Cách điều tra |
| --- | --- | --- |
| **Circular dependency** | Hai resource tham chiếu lẫn nhau hoặc `DependsOn` tạo cạnh ngược | Vẽ graph; tách association/ingress/policy thành resource thứ ba |
| **Export cannot be deleted** | Có stack vẫn import export | Dùng `list-imports`, chuyển consumers rồi mới xóa |
| **Export cannot be modified** | Giá trị output đang được import | Thêm export version mới và migration theo từng consumer |
| **No export named ... found** | Sai tên, sai account/Region hoặc provider chưa deploy | So sánh Export Name chính xác và deploy order |
| **Nested stack template URL error** | Template chưa upload, URL sai hoặc CloudFormation không có quyền đọc | Kiểm tra S3 object, role, bucket policy và KMS |
| **Nested stack parameter validation failed** | Parent truyền sai type/value hoặc child parameter constraints không khớp | Đối chiếu Parameters/AllowedValues và stack events |
| **UPDATE_ROLLBACK_IN_PROGRESS** | Resource update hoặc child stack thất bại | Mở parent events rồi kiểm tra child stack events |
| **Resource already exists** | Stack khác hoặc thao tác ngoài IaC đã tạo resource cùng tên | Xác minh ownership, import/adopt resource theo quy trình |
| **Delete stack blocked** | Export importer, termination protection hoặc resource dependency còn tồn tại | Kiểm tra imports, protection, retained resources và resource events |
| **Change Set shows replacement** | Thuộc tính thay đổi yêu cầu replacement | Đánh giá downtime, data migration và `UpdateReplacePolicy` |
| **CDK export removal failure** | Refactor làm synthesize bỏ export đang được stack khác dùng | So sánh synthesized templates; giữ export tạm thời và migrate consumer |
| **Dependency order appears wrong** | Thiếu implicit reference hoặc explicit dependency cần thiết | Kiểm tra resource property và `DependsOn`; phân biệt resource completion với app readiness |

### 19.1. Quy trình điều tra nhanh

1. Xác định stack operation và logical resource bị lỗi.
2. Đọc CloudFormation Events theo timestamp, từ lỗi đầu tiên.
3. Với nested stack, mở child stack events.
4. Kiểm tra dependency edge, Parameters, Outputs và export/import names.
5. Kiểm tra account/Region, IAM execution role, artifact access và quota.
6. Tạo Change Set sau khi sửa để xem impact trước khi thực thi.

Không chỉ sửa trạng thái cuối cùng. Tìm lỗi đầu tiên trong event stream; các lỗi sau thường là hệ quả của rollback.

## 20. Bài tập củng cố

### Bài 1 — Implicit dependency

Một EC2 instance có thuộc tính `SubnetId: !Ref PrivateSubnet`. CloudFormation có cần `DependsOn: PrivateSubnet` không?

**Gợi ý:** không. `Ref` đã tạo implicit dependency.

### Bài 2 — Khi nào dùng DependsOn?

Một route tham chiếu Internet Gateway ID nhưng phải chờ gateway attachment hoàn tất. Cần biểu diễn quan hệ nào?

**Gợi ý:** dùng `DependsOn` tới VPC gateway attachment vì route không tham chiếu attachment resource.

### Bài 3 — Nested stack output

Parent stack cần VPC ID do child network stack tạo. Dùng intrinsic function nào?

**Gợi ý:** `Fn::GetAtt` tới attribute `Outputs.VpcId` của nested stack resource.

### Bài 4 — Export/import Region

Network stack ở `ap-southeast-1` export VPC ID. Application stack ở `ap-southeast-2` có thể dùng `Fn::ImportValue` không?

**Gợi ý:** không. CloudFormation exports/imports chỉ hoạt động trong cùng account và Region.

### Bài 5 — Export đang được import

Bạn muốn xóa export v1 nhưng hai application stacks vẫn import nó. Trình tự an toàn là gì?

**Gợi ý:** tạo export v2, deploy provider, migrate consumers sang v2, xác minh không còn imports v1 rồi mới xóa v1.

### Bài 6 — Circular security groups

Hai security groups tham chiếu nhau trong ingress rules. Làm sao phá vòng dependency?

**Gợi ý:** tạo hai groups trước; khai báo mỗi ingress rule thành resource `AWS::EC2::SecurityGroupIngress` riêng.

### Bài 7 — Chọn nested stack hay stack độc lập

Network foundation được nhiều application teams dùng và deploy theo lịch riêng. Nên chọn nested stack hay stack độc lập?

**Gợi ý:** stack độc lập với exports/contract một chiều thường phù hợp hơn vì network có ownership và lifecycle riêng.

### Bài 8 — TemplateURL

Parent stack update nhưng nested stack báo không tải được template. Hãy nêu ba điểm cần kiểm tra.

**Gợi ý:** S3 object/URL, quyền đọc của CloudFormation execution role, bucket/KMS policy và artifact version.

### Bài 9 — CDK cross-stack ref

Một CDK stack ở account A/Region X tham chiếu trực tiếp VPC resource trong stack ở account B/Region Y. CDK có tự tạo `Fn::ImportValue` không?

**Gợi ý:** không. Dùng explicit cross-account/Region integration contract như pipeline parameters, configuration store hoặc resource sharing được hỗ trợ.

### Bài 10 — Delete order

Application stack import VPC ID từ network stack. Stack nào nên được xóa trước?

**Gợi ý:** application consumer trước, network provider sau khi không còn imports.

### Bài 11 — Retain

Parent stack bị xóa nhưng database cần giữ lại. Cần cân nhắc cơ chế nào và rủi ro gì?

**Gợi ý:** `DeletionPolicy: Retain`; sau đó phải xác định owner, backup/recovery và cách quản lý resource đã retained.

### Bài 12 — Change Set

Change Set cho thấy thay đổi subnet CIDR yêu cầu replacement. Những câu hỏi nào cần review trước deploy?

**Gợi ý:** subnet mới có thay ID không, workload/network routes/security rules có bị gián đoạn không, data/ENI dependencies ra sao, rollback và migration thế nào.

## 21. Checklist thiết kế production

- [ ] Dependency graph không có cycle; các cạnh implicit được tạo từ Ref/GetAtt/Sub khi phù hợp.
- [ ] `DependsOn` chỉ được thêm khi có thứ tự thật mà intrinsic references không thể biểu diễn.
- [ ] Không dùng dependency ordering như application readiness/health check.
- [ ] Nested stack được chia theo ownership, lifecycle, failure domain và change frequency.
- [ ] Parent/child Parameters có type, constraints và default rõ ràng.
- [ ] Child Outputs nhỏ, ổn định và không chứa secret.
- [ ] TemplateURL trỏ đến artifact immutable, có checksum/version và quyền đọc phù hợp.
- [ ] Cross-stack references có provider/consumer direction rõ ràng.
- [ ] Export names duy nhất, ổn định và có naming convention theo environment/domain/version.
- [ ] Không cố import cross-account hoặc cross-Region bằng Fn::ImportValue.
- [ ] Có migration plan expand → migrate → contract trước khi thay đổi export đang được sử dụng.
- [ ] Pipeline deploy stacks theo dependency order và hỗ trợ Change Set review.
- [ ] Rollback được thiết kế theo từng stack; không giả định multi-stack transaction.
- [ ] Nested stack events và child stack failures có runbook điều tra.
- [ ] Stack policy, termination protection, DeletionPolicy và IAM/SCP được dùng đúng mục đích.
- [ ] Secrets nằm trong Secrets Manager/SSM; không xuất secret trong Outputs.
- [ ] Template được validate bằng CloudFormation/cfn-lint/policy checks.
- [ ] Có integration test trong sandbox cho IAM, networking, quotas và lifecycle quan trọng.
- [ ] Có drift detection/ownership process cho thay đổi ngoài IaC.
- [ ] Có owner, retention, backup và cleanup plan cho retained resources.

## 22. Ghi nhớ

1. **Dependency graph** cho CloudFormation biết thứ tự create/update/delete; các resource không phụ thuộc nhau có thể được xử lý song song.
2. **Implicit dependencies** thường được suy ra từ `Ref`, `Fn::GetAtt` và `Fn::Sub`; dùng `DependsOn` cho quan hệ thứ tự không thể biểu diễn bằng reference.
3. **Nested stack** chia một deployment thành parent/child templates có lifecycle liên kết; parent truyền parameters và đọc child outputs qua `Fn::GetAtt`.
4. **Cross-stack reference** dùng `Export` và `Fn::ImportValue` cho stacks độc lập trong cùng account/Region. Export đang được import không thể bị xóa hoặc thay đổi.
5. Khi đổi contract, dùng migration **expand → migrate → contract**: thêm version mới, chuyển consumers, rồi mới gỡ version cũ.
6. Circular dependency cần sửa cấu trúc graph; thêm `DependsOn` không phá được vòng lặp.
7. AWS CDK có thể tự tạo cross-stack exports/imports trong environment tương thích; hãy review synthesized templates khi refactor.
8. Stack boundaries là quyết định về ownership, security và lifecycle; không chia stack chỉ để tách file.

Thiết kế stack tốt giúp deploy theo thứ tự có thể dự đoán, tái sử dụng shared infrastructure, giảm phạm vi thay đổi và quản lý contract an toàn trong suốt vòng đời hệ thống.

### Tài liệu chính thức

- [AWS CloudFormation User Guide](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/Welcome.html) — khái niệm và vận hành CloudFormation.
- [DependsOn attribute](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-attribute-dependson.html) — explicit resource dependencies.
- [Ref intrinsic function](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/intrinsic-function-reference-ref.html) — tham chiếu parameter/resource.
- [Fn::GetAtt intrinsic function](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/intrinsic-function-reference-getatt.html) — lấy resource attributes.
- [Fn::Sub intrinsic function](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/intrinsic-function-reference-sub.html) — string substitution và references.
- [Nested stacks](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-nested-stacks.html) — tạo và quản lý nested stacks.
- [Outputs section](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/outputs-section-structure.html) — outputs và exports.
- [Fn::ImportValue](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/intrinsic-function-reference-importvalue.html) — cross-stack import constraints.
- [CloudFormation stack updates](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks.html) — update, Change Sets và lifecycle.
- [CloudFormation stack policies](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/protect-stack-resources.html) — bảo vệ resources khi update.
- [CloudFormation drift detection](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html) — phát hiện thay đổi ngoài template.
- [AWS CDK guide](https://docs.aws.amazon.com/cdk/v2/guide/home.html) — CDK constructs, stacks và synthesis.
- [AWS CDK cross-stack references](https://docs.aws.amazon.com/cdk/v2/guide/resources.html#resources_cross_stack) — reference giữa các stacks.
- [cfn-lint](https://github.com/aws-cloudformation/cfn-lint) — lint CloudFormation templates.
- [CloudFormation Guard](https://github.com/aws-cloudformation/cloudformation-guard) — policy-as-code cho templates.
