# CloudFormation template, parameter, output và intrinsic function

> **Chương:** Hạ tầng dưới dạng mã  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hệ sinh thái AWS qua hạ tầng Region/AZ, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless. Người học rèn khả năng chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vai trò của AWS CloudFormation trong Infrastructure as Code (IaC) và vòng đời stack.
2. Đọc và tổ chức một CloudFormation template theo các section chuẩn.
3. Khai báo Parameters có kiểu dữ liệu, giá trị mặc định, constraints và mô tả rõ ràng.
4. Dùng Outputs để công bố resource identifiers và chia sẻ dữ liệu giữa các stacks.
5. Chọn đúng intrinsic function như Ref, GetAtt, Sub, Join, FindInMap, Select, If, ImportValue và các condition functions.
6. Kết hợp pseudo parameters để viết template có thể tái sử dụng giữa accounts, Regions và environments.
7. Phân biệt implicit dependency với DependsOn, và áp dụng DeletionPolicy/UpdateReplacePolicy phù hợp.
8. Sử dụng dynamic references tới Systems Manager Parameter Store và Secrets Manager an toàn.
9. Validate, review change sets, deploy, detect drift và xử lý rollback.
10. Thiết kế template theo nguyên tắc least privilege, bảo vệ dữ liệu và kiểm soát chi phí.

## 1. CloudFormation giải quyết bài toán gì?

**AWS CloudFormation** cho phép mô tả hạ tầng AWS bằng template dạng YAML hoặc JSON. CloudFormation đọc template, tạo stack và điều phối việc tạo, cập nhật hoặc xóa các resources theo dependency graph.

Ví dụ, một ứng dụng cần:

- VPC, subnets và security groups.
- S3 bucket lưu artifacts.
- IAM role cho workload.
- SQS queue để xử lý bất đồng bộ.
- CloudWatch log group và alarms.

Nếu tạo từng resource bằng console, cấu hình có thể khác nhau giữa development, staging và production. Khi lưu template trong source control, team có thể review thay đổi, tái tạo môi trường và triển khai theo quy trình giống code.

~~~mermaid
flowchart LR
    T["YAML / JSON template"] --> V["Validate + lint"]
    V --> C["Change set"]
    C --> R["Review changes"]
    R --> E["Execute"]
    E --> S["CloudFormation stack"]
    S --> A["AWS resources"]
    A --> D["Drift detection"]
    D --> T
~~~

### 1.1. Các khái niệm cốt lõi

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Template** | Bản mô tả hạ tầng dạng YAML/JSON. |
| **Stack** | Tập hợp resources được CloudFormation quản lý từ một template và parameter values. |
| **Resource** | Một AWS resource được khai báo trong section Resources. |
| **Logical ID** | Tên định danh resource bên trong template, ví dụ AppQueue. |
| **Physical ID** | Tên/ID thực tế được AWS service tạo, ví dụ queue URL hoặc bucket name. |
| **Parameter** | Input được truyền khi tạo hoặc cập nhật stack. |
| **Output** | Giá trị stack công bố sau khi triển khai. |
| **Intrinsic function** | Hàm tích hợp để tham chiếu parameters, resources, attributes hoặc tính giá trị lúc deploy. |
| **Change set** | Bản xem trước những thay đổi CloudFormation dự kiến thực hiện. |
| **Drift** | Khác biệt giữa cấu hình thực tế của resource và cấu hình CloudFormation mong muốn. |

### 1.2. Declarative và reconciliation

Template mô tả **trạng thái mong muốn**. Người viết nói resource cần có loại gì và properties ra sao; CloudFormation quyết định thứ tự và API calls cần thực hiện.

Khi update stack, CloudFormation so sánh template mới với stack hiện tại rồi tạo, cập nhật, thay thế hoặc xóa resources. Một số thay đổi property yêu cầu replacement; một số chỉ cập nhật tại chỗ. Phải đọc resource reference và change set trước khi thực thi.

CloudFormation không phải runtime controller liên tục sửa mọi drift ngay lập tức. Nếu ai đó chỉnh resource trực tiếp trong console, drift có thể tồn tại cho đến khi chạy drift detection hoặc thực hiện stack operation.

## 2. Cấu trúc CloudFormation template

Một template có thể có các section sau:

| Section | Bắt buộc? | Mục đích |
| --- | --- | --- |
| AWSTemplateFormatVersion | Không | Version format của template; hiện thường dùng 2010-09-09. |
| Description | Không | Mô tả template. |
| Transform | Không | Áp dụng macro/extension như AWS::LanguageExtensions hoặc AWS::Serverless. |
| Metadata | Không | Metadata cho template hoặc các tools. |
| Parameters | Không | Input lúc tạo/update stack. |
| Rules | Không | Kiểm tra điều kiện hợp lệ giữa parameter values. |
| Mappings | Không | Bảng tra cứu key/value tĩnh. |
| Conditions | Không | Điều kiện quyết định resource/property có được tạo/chọn hay không. |
| Resources | **Có** | Khai báo resources cần quản lý. |
| Outputs | Không | Công bố values từ stack. |

Thứ tự section trong template có thể theo cấu trúc tài liệu để dễ đọc; Resources là section bắt buộc.

### 2.1. Template nhỏ nhất có thể triển khai

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Minimal S3 bucket example

Resources:
  ArtifactsBucket:
    Type: AWS::S3::Bucket
~~~

Logical ID là ArtifactsBucket; Type là AWS::S3::Bucket. Vì chưa khai báo Properties, CloudFormation tạo bucket với cấu hình mặc định của resource provider. Production template nên khai báo encryption, public access block, versioning, lifecycle, logging và retention theo yêu cầu.

### 2.2. Logical ID và physical resource

Logical ID phải duy nhất trong section Resources của một template. Các intrinsic functions tham chiếu resource thường dùng logical ID, không dùng physical ID.

Ví dụ:

~~~yaml
Resources:
  OrdersQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: orders-processing

Outputs:
  QueueUrl:
    Value: !Ref OrdersQueue
~~~

Với AWS::SQS::Queue, Ref trả về queue URL. Với mỗi resource type, Ref có thể trả về một dạng value khác nhau. Đọc trang resource reference để biết chính xác.

Physical name có thể được CloudFormation sinh tự động nếu không đặt tên tường minh. Tên tự sinh giúp tránh collision khi tạo nhiều stacks. Khi hard-code physical name, phải xử lý uniqueness giữa accounts/Regions/environments và có thể gặp khó khăn khi replacement.

## 3. Parameters: input có kiểm soát cho stack

Parameters giúp tái sử dụng cùng template ở nhiều environments. Thay vì sửa file YAML để đổi instance type, environment hoặc CIDR, người triển khai truyền parameter values khi tạo/update stack.

### 3.1. Cấu trúc Parameter

Một parameter thường có:

- Type: kiểu dữ liệu hoặc AWS-specific parameter type.
- Description: giải thích mục đích.
- Default: giá trị mặc định nếu có.
- AllowedValues: danh sách giá trị cho phép.
- AllowedPattern: regex kiểm tra chuỗi.
- MinLength/MaxLength: giới hạn chiều dài.
- MinValue/MaxValue: giới hạn số.
- ConstraintDescription: thông báo khi input không hợp lệ.
- NoEcho: che giá trị trong một số giao diện/hiển thị stack.

Ví dụ:

~~~yaml
Parameters:
  Environment:
    Type: String
    Description: Deployment environment
    Default: dev
    AllowedValues:
      - dev
      - test
      - prod

  VpcCidr:
    Type: String
    Description: IPv4 CIDR block for the VPC
    Default: 10.40.0.0/16
    AllowedPattern: '^([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}$'
    ConstraintDescription: Enter an IPv4 CIDR block such as 10.40.0.0/16.

  QueueRetentionSeconds:
    Type: Number
    Default: 345600
    MinValue: 60
    MaxValue: 1209600
    Description: SQS message retention in seconds
~~~

Regex ở ví dụ chỉ kiểm tra hình dạng chuỗi; nó không xác minh mọi octet và prefix là CIDR hợp lệ. Dùng parameter type/validation phù hợp và validation tools để kiểm tra thêm.

### 3.2. Các parameter types thường dùng

| Type | Khi sử dụng |
| --- | --- |
| String | Tên environment, queue name, CIDR dạng chuỗi. |
| Number | Port, retention seconds, replica count. |
| List<Number> | Danh sách số. |
| CommaDelimitedList | Danh sách chuỗi phân cách bằng dấu phẩy. |
| AWS::EC2::KeyPair::KeyName | Chọn EC2 key pair tồn tại trong account/Region. |
| AWS::EC2::VPC::Id | Chọn VPC hiện có. |
| AWS::EC2::Subnet::Id | Chọn subnet hiện có. |
| AWS::SSM::Parameter::Value<String> | Lấy value từ Systems Manager Parameter Store theo key. |
| AWS::SSM::Parameter::Value<List<String>> | Lấy danh sách values từ Parameter Store. |

AWS-specific parameter types có thể giúp console hiển thị danh sách resources phù hợp trong account/Region. Chúng không tự cấp quyền cho stack và không thay thế IAM.

### 3.3. NoEcho không phải secret vault

NoEcho che parameter value trong một số hiển thị CloudFormation, nhưng **không phải cơ chế quản lý secrets đầy đủ**. Không truyền password/API key dài hạn như parameter thường rồi nghĩ NoEcho đã bảo vệ mọi nơi. Giá trị có thể xuất hiện trong resource properties, logs, metadata hoặc các nơi khác tùy resource/template.

Dùng Secrets Manager hoặc Systems Manager SecureString dynamic references khi resource property cần secret. Không đặt secret trong Outputs, Metadata, Description hoặc template source control.

### 3.4. Parameter file và CLI

Ví dụ file parameters dạng JSON:

~~~json
[
  {
    "ParameterKey": "Environment",
    "ParameterValue": "staging"
  },
  {
    "ParameterKey": "VpcCidr",
    "ParameterValue": "10.40.0.0/16"
  },
  {
    "ParameterKey": "QueueRetentionSeconds",
    "ParameterValue": "86400"
  }
]
~~~

Tạo stack với file parameter:

~~~bash
aws cloudformation create-stack \
  --stack-name orders-infrastructure \
  --template-body file://template.yaml \
  --parameters file://parameters.json \
  --region ap-southeast-1
~~~

Với template lớn hơn giới hạn inline, upload template lên S3 và dùng template URL. Không đưa secret value vào file parameters được commit.

### 3.5. Parameter validation bằng Rules

Rules section có thể kiểm tra nhiều parameters có tương quan với nhau. Ví dụ, nếu chọn environment prod thì parameter MultiAZ phải true:

~~~yaml
Parameters:
  Environment:
    Type: String
    AllowedValues: [dev, test, prod]
  MultiAZ:
    Type: String
    AllowedValues: ['true', 'false']

Rules:
  ProductionRequiresMultiAZ:
    RuleCondition: !Equals [!Ref Environment, prod]
    Assertions:
      - Assert: !Equals [!Ref MultiAZ, 'true']
        AssertDescription: Production requires MultiAZ to be enabled.
~~~

Rules kiểm tra parameter input khi tạo/update stack. Chúng không thay thế Conditions: Rules từ chối input không hợp lệ, còn Conditions điều khiển resource/property trong template.

## 4. Mappings: bảng tra cứu cấu hình tĩnh

Mappings là bảng lookup cố định trong template. Dùng Fn::FindInMap khi cần chọn giá trị theo Region, environment hoặc một dimension tĩnh.

Ví dụ chọn AMI theo Region:

~~~yaml
Mappings:
  RegionAmi:
    ap-southeast-1:
      HVM64: ami-0123456789abcdef0
    ap-northeast-1:
      HVM64: ami-0abcdef1234567890

Parameters:
  InstanceRegion:
    Type: String
    Default: ap-southeast-1
    AllowedValues:
      - ap-southeast-1
      - ap-northeast-1

Resources:
  AppInstance:
    Type: AWS::EC2::Instance
    Properties:
      ImageId: !FindInMap
        - RegionAmi
        - !Ref InstanceRegion
        - HVM64
      InstanceType: t3.micro
~~~

AMI IDs ở ví dụ chỉ là placeholders minh họa, không đảm bảo tồn tại. Production nên lấy AMI từ SSM public parameters hoặc pipeline cập nhật mapping có kiểm soát, vì AMI IDs thay đổi theo Region, architecture và release.

Mapping là dữ liệu tĩnh nằm trong template. Nếu giá trị cần được quản lý động hoặc chia sẻ giữa nhiều teams, cân nhắc Parameter Store, AppConfig hoặc một resource/configuration source phù hợp hơn.

## 5. Conditions: tạo resource theo điều kiện

Conditions được đánh giá khi CloudFormation tạo hoặc cập nhật stack. Chúng thường dựa trên Parameters, pseudo parameters hoặc Mappings; không được tham chiếu trực tiếp resource logical IDs hay resource attributes trong điều kiện.

### 5.1. Khai báo condition

~~~yaml
Parameters:
  Environment:
    Type: String
    AllowedValues: [dev, staging, prod]
    Default: dev

Conditions:
  IsProduction: !Equals [!Ref Environment, prod]
  IsNotDevelopment: !Not
    - !Equals [!Ref Environment, dev]
~~~

### 5.2. Gắn Condition vào resource

~~~yaml
Resources:
  ProductionAlarm:
    Type: AWS::CloudWatch::Alarm
    Condition: IsProduction
    Properties:
      AlarmDescription: Alarm enabled only for production
      Namespace: AWS/SQS
      MetricName: ApproximateNumberOfMessagesVisible
      Statistic: Average
      Period: 60
      EvaluationPeriods: 3
      Threshold: 100
      ComparisonOperator: GreaterThanThreshold
      Dimensions:
        - Name: QueueName
          Value: !GetAtt OrdersQueue.QueueName
~~~

Khi IsProduction false, resource này không được tạo. Nếu update parameter khiến condition chuyển từ true sang false, CloudFormation xóa resource đã gắn condition đó. Vì vậy, không dùng Conditions để ẩn tài nguyên stateful quan trọng mà chưa hiểu hậu quả deletion.

### 5.3. Fn::If và AWS::NoValue

Fn::If chọn một trong hai giá trị khi deploy. AWS::NoValue loại bỏ property tương ứng khỏi resource configuration.

~~~yaml
Parameters:
  EnableDeadLetterQueue:
    Type: String
    AllowedValues: ['true', 'false']
    Default: 'true'

Conditions:
  CreateDlq: !Equals [!Ref EnableDeadLetterQueue, 'true']

Resources:
  OrdersQueue:
    Type: AWS::SQS::Queue
    Properties:
      RedrivePolicy: !If
        - CreateDlq
        - deadLetterTargetArn: !GetAtt OrdersDlq.Arn
          maxReceiveCount: 5
        - !Ref AWS::NoValue

  OrdersDlq:
    Type: AWS::SQS::Queue
    Condition: CreateDlq
~~~

Trong ví dụ thực tế, cần đảm bảo resource property có schema phù hợp với giá trị được chọn và condition của resource phụ thuộc. Có thể dùng Fn::If trong property value hoặc list/object để tùy biến cấu hình.

### 5.4. Condition functions

| Function | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Fn::Equals | So sánh hai values. | !Equals [!Ref Environment, prod] |
| Fn::And | Tất cả điều kiện đều true. | !And [!Condition IsProd, !Condition HasBackup] |
| Fn::Or | Ít nhất một điều kiện true. | !Or [!Condition IsProd, !Condition IsStaging] |
| Fn::Not | Đảo giá trị điều kiện. | !Not [!Condition IsDevelopment] |
| Fn::If | Chọn value theo condition. | !If [IsProd, 30, 7] |

Fn::And và Fn::Or có giới hạn số operands theo CloudFormation reference. Khi condition phức tạp, đặt tên conditions nhỏ và dễ hiểu thay vì lồng nhiều biểu thức khó review.

## 6. Outputs: công bố giá trị sau khi tạo stack

Outputs giúp operator, pipeline hoặc stack khác lấy thông tin từ stack đã triển khai. Các values thường là resource ARN, queue URL, bucket name, endpoint hoặc subnet IDs.

### 6.1. Output cơ bản

~~~yaml
Outputs:
  OrdersQueueUrl:
    Description: URL of the orders processing queue
    Value: !Ref OrdersQueue
  OrdersQueueArn:
    Description: ARN of the orders processing queue
    Value: !GetAtt OrdersQueue.Arn
  DeploymentRegion:
    Description: AWS Region where this stack is deployed
    Value: !Ref AWS::Region
~~~

Output không tạo resource. Nó công bố value mà CloudFormation có thể trả về trong stack details, API hoặc CLI.

### 6.2. Export output để stack khác import

Network stack có thể export VPC ID:

~~~yaml
Outputs:
  VpcId:
    Description: VPC ID shared with application stacks
    Value: !Ref ApplicationVpc
    Export:
      Name: !Sub '${AWS::StackName}-VpcId'
~~~

Application stack import giá trị:

~~~yaml
Parameters:
  NetworkStackName:
    Type: String
Resources:
  AppSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Security group for application
      VpcId:
        Fn::ImportValue:
          Fn::Sub: '${NetworkStackName}-VpcId'
~~~

Export + Fn::ImportValue có các giới hạn quan trọng:

- Export và import chỉ hoạt động trong **cùng AWS account và cùng Region**.
- Export name phải duy nhất trong account/Region.
- Khi stack khác đang import output, stack export không thể bị xóa và exported value không thể bị thay đổi.
- Muốn đổi hoặc xóa export, phải xóa mọi imports trước.
- Output Export Name không được phụ thuộc vào Ref/GetAtt của resource.

Đây là ràng buộc tham chiếu mạnh hữu ích cho network foundation, nhưng cũng tạo coupling giữa stacks. Lập kế hoạch thứ tự cập nhật/xóa stack trước khi thay đổi export.

### 6.3. Fn::GetStackOutput cho cross-account/Region

CloudFormation có Fn::GetStackOutput để tham chiếu output của stack khác mà không cần Export tường minh. Function này hỗ trợ cross-account và cross-Region theo cấu hình/permissions phù hợp, nhưng là **weak reference**: CloudFormation không khóa stack nguồn khỏi bị xóa như Export + ImportValue.

Chỉ dùng khi cần chia sẻ output cross-account/Region và đã thiết kế quyền truy cập, deployment order, failure handling. Với stacks trong cùng account/Region cần bảo vệ referential integrity, Export + ImportValue thường rõ ràng hơn.

### 6.4. Không xuất secret qua Outputs

Không đặt database password, API token hoặc secret value vào Outputs. Output values có thể được đọc bởi principals có quyền xem stack outputs, lưu trong pipeline logs hoặc được chia sẻ với stack khác. Hãy xuất secret ARN/name hoặc reference an toàn nếu consumer cần tự đọc secret bằng IAM role.

## 7. Intrinsic functions: tham chiếu và tính giá trị

Intrinsic functions là các hàm tích hợp mà CloudFormation đánh giá trong quá trình xử lý template/deploy. Chúng cho phép dùng input values, attributes của resources, mappings, conditions và pseudo parameters.

Các hàm có thể xuất hiện ở những vị trí CloudFormation hỗ trợ như resource properties, outputs, metadata và điều kiện. Không phải property nào cũng chấp nhận mọi intrinsic function; kiểm tra resource schema.

### 7.1. Ref và Fn::GetAtt

Ref có hai dạng phổ biến: với Parameter, trả parameter value; với Resource, trả giá trị được resource type định nghĩa, thường là physical ID nhưng không phải lúc nào cũng là ARN.

GetAtt lấy attribute của resource. Attribute names phụ thuộc resource type.

~~~yaml
Resources:
  OrdersQueue:
    Type: AWS::SQS::Queue
  LogsBucket:
    Type: AWS::S3::Bucket

Outputs:
  QueueUrl:
    Value: !Ref OrdersQueue
  QueueArn:
    Value: !GetAtt OrdersQueue.Arn
  BucketName:
    Value: !Ref LogsBucket
  BucketArn:
    Value: !GetAtt LogsBucket.Arn
~~~

Đừng mặc định Ref của mọi resource đều trả ARN. Ví dụ Ref của SQS Queue trả queue URL, còn ARN lấy bằng GetAtt. Luôn tra bảng Return values của resource type.

### 7.2. Fn::Sub

Sub thay placeholder trong string bằng parameter, pseudo parameter, logical ID hoặc resource attribute. Đây thường là cách dễ đọc để tạo ARN/URL.

~~~yaml
Outputs:
  QueueArnText:
    Value: !Sub 'arn:${AWS::Partition}:sqs:${AWS::Region}:${AWS::AccountId}:${OrdersQueue.Arn}'
  QueueUrl:
    Value: !Sub 'https://sqs.${AWS::Region}.${AWS::URLSuffix}/${AWS::AccountId}/${OrdersQueue.QueueName}'
~~~

Trong Fn::Sub:

- Placeholder dạng ${Parameter} thay bằng parameter value.
- Placeholder dạng ${LogicalResourceId} tương đương Ref resource.
- Placeholder dạng ${LogicalResourceId.Attribute} tương đương GetAtt.
- Placeholder dạng ${AWS::Region} tham chiếu pseudo parameter.
- Có thể truyền variable map để đặt tên biến hoặc dùng giá trị tính bằng intrinsic function.

~~~yaml
Outputs:
  LogGroupArn:
    Value: !Sub
      - 'arn:${Partition}:logs:${Region}:${Account}:log-group:${Name}'
      - Partition: !Ref AWS::Partition
        Region: !Ref AWS::Region
        Account: !Ref AWS::AccountId
        Name: !Ref ApplicationLogGroup
~~~

Nếu cần hiển thị literal placeholder ${...} mà không muốn Sub thay thế, dùng cú pháp escape của Fn::Sub theo tài liệu AWS. Trong user data, launch template hoặc script, phải kiểm tra thêm cách shell/interpreter tiếp theo xử lý dấu $.

### 7.3. Fn::Join, Fn::Select và Fn::Split

Join nối danh sách values thành string với delimiter. Split biến chuỗi phân cách thành list; Select lấy phần tử theo zero-based index.

~~~yaml
Outputs:
  SubnetListText:
    Value: !Join
      - ','
      - - !Ref PublicSubnetA
        - !Ref PublicSubnetB

Parameters:
  AllowedSubnetIds:
    Type: CommaDelimitedList
    Description: Subnet IDs supplied by deployment pipeline

Resources:
  AppInstance:
    Type: AWS::EC2::Instance
    Properties:
      SubnetId: !Select [0, !Ref AllowedSubnetIds]
~~~

Split cũng có thể kết hợp Select để lấy một phần của string:

~~~yaml
Parameters:
  ObjectPath:
    Type: String
    Default: artifacts/reports/daily.csv

Outputs:
  SecondPathSegment:
    Value: !Select [1, !Split ['/', !Ref ObjectPath]]
~~~

Select không kiểm tra index có vượt phạm vi hay không. Nếu list rỗng hoặc index không tồn tại, stack operation có thể thất bại. Validate parameter values và không hard-code index nếu số phần tử thay đổi. Khi cần nội suy string có nhiều values, Fn::Sub thường dễ đọc hơn Fn::Join.

### 7.4. Fn::FindInMap

FindInMap lấy value trong Mappings theo ba keys: map name, top-level key và second-level key.

~~~yaml
Mappings:
  EnvironmentConfig:
    dev:
      InstanceType: t3.micro
    prod:
      InstanceType: t3.small

Parameters:
  Environment:
    Type: String
    AllowedValues: [dev, prod]

Resources:
  AppInstance:
    Type: AWS::EC2::Instance
    Properties:
      InstanceType: !FindInMap
        - EnvironmentConfig
        - !Ref Environment
        - InstanceType
      ImageId: ami-0123456789abcdef0
~~~

AMI ID chỉ là placeholder minh họa, không đảm bảo tồn tại. Production nên lấy AMI từ SSM public parameters hoặc pipeline cập nhật mapping có kiểm soát, vì AMI IDs thay đổi theo Region, architecture và release.

Mapping là dữ liệu tĩnh nằm trong template. Nếu giá trị cần được quản lý động hoặc chia sẻ giữa nhiều teams, cân nhắc Parameter Store hoặc một configuration source phù hợp hơn.

### 7.5. Fn::GetAZs và Fn::Cidr

GetAZs trả danh sách Availability Zones có trong Region được chỉ định. Nếu truyền chuỗi rỗng, CloudFormation dùng Region hiện tại. Cidr tạo danh sách CIDR blocks con từ một CIDR block gốc.

~~~yaml
Parameters:
  NetworkRegion:
    Type: String
    Default: ''
  VpcCidr:
    Type: String
    Default: 10.40.0.0/16

Outputs:
  FirstAvailabilityZone:
    Value:
      Fn::Select:
        - 0
        - Fn::GetAZs:
            Ref: NetworkRegion

Resources:
  PublicSubnetA:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref ApplicationVpc
      AvailabilityZone: !Select [0, !GetAZs '']
      CidrBlock: !Select
        - 0
        - !Cidr [!Ref VpcCidr, 4, 8]
~~~

Với VPC /16 và 8 bits bổ sung, mỗi subnet là /24. Chỉ dùng index nằm trong danh sách CIDR đã tạo. Số AZ và thứ tự AZ có thể khác giữa accounts do AZ IDs ánh xạ khác nhau sang tên AZ; không giả định mọi account đều có cùng az-a vật lý.

### 7.6. Fn::Base64

Base64 encode string, thường dùng với UserData của EC2:

~~~yaml
Resources:
  AppInstance:
    Type: AWS::EC2::Instance
    Properties:
      ImageId: ami-0123456789abcdef0
      InstanceType: t3.micro
      UserData:
        Fn::Base64: !Sub |
          #!/bin/bash
          echo "Stack=${AWS::StackName}" > /etc/app-stack
~~~

Base64 là encoding, **không phải encryption**. Không đặt credentials/password vào UserData; user data có thể được truy cập qua APIs/instance metadata/logs tùy quyền và cách hệ thống xử lý.

### 7.7. Fn::ImportValue

ImportValue lấy exported output từ stack khác trong cùng account/Region.

~~~yaml
Resources:
  AppSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: App security group
      VpcId:
        Fn::ImportValue:
          Fn::Sub: '${NetworkStackName}-VpcId'
~~~

Dùng long form cho nested intrinsic functions để YAML parser và CloudFormation diễn giải rõ ràng. Short form !ImportValue !Sub ... không hợp lệ trong nhiều cách viết nested tag; ví dụ trên an toàn và dễ đọc.

### 7.8. Condition functions trong resource properties

Có thể kết hợp Equals/And/Or/Not với Condition và If:

~~~yaml
Conditions:
  IsProduction: !Equals [!Ref Environment, prod]
  HasPublicIngress: !And
    - !Condition IsProduction
    - !Equals [!Ref EnablePublicIngress, 'true']

Resources:
  OptionalIngressRule:
    Type: AWS::EC2::SecurityGroupIngress
    Condition: HasPublicIngress
    Properties:
      GroupId: !Ref AppSecurityGroup
      IpProtocol: tcp
      FromPort: 443
      ToPort: 443
      CidrIp: 203.0.113.0/24
~~~

CIDR 203.0.113.0/24 thuộc dải tài liệu minh họa, không dùng làm public client range thực tế. Public ingress cần threat model, source CIDR cụ thể và security review.

## 8. Pseudo parameters: values do CloudFormation cung cấp

Pseudo parameters có sẵn trong mọi template; không cần khai báo trong Parameters.

| Pseudo parameter | Giá trị |
| --- | --- |
| AWS::AccountId | Account ID chứa stack. |
| AWS::Region | Region triển khai stack. |
| AWS::StackName | Tên stack hiện tại. |
| AWS::StackId | ARN của stack hiện tại. |
| AWS::Partition | Partition, ví dụ aws, aws-cn hoặc aws-us-gov. |
| AWS::URLSuffix | DNS suffix phù hợp partition, ví dụ amazonaws.com. |
| AWS::NotificationARNs | Danh sách notification topic ARNs được cấu hình cho stack. |
| AWS::NoValue | Dùng trong Fn::If để bỏ property khỏi resource configuration. |

Ví dụ tạo ARN không hard-code partition/account/Region:

~~~yaml
Outputs:
  QueueArn:
    Value: !Sub 'arn:${AWS::Partition}:sqs:${AWS::Region}:${AWS::AccountId}:${OrdersQueue}'
  StackIdentifier:
    Value: !Ref AWS::StackId
~~~

Dùng AWS::Partition thay vì hard-code arn:aws: khi template cần hoạt động trong commercial, China hoặc GovCloud partitions. Không giả định mọi AWS partition đều dùng cùng URL suffix hoặc service availability.

## 9. Dynamic references: lấy configuration và secret lúc deploy

Dynamic references cho phép template tham chiếu values được quản lý trong Systems Manager Parameter Store hoặc Secrets Manager. CloudFormation resolve reference trong quá trình stack create/update/change set khi cần truyền giá trị tới resource property.

### 9.1. Systems Manager Parameter Store plaintext

Pattern tổng quát:

~~~text
{{resolve:ssm:parameter-name:version}}
~~~

Ví dụ dùng một parameter chứa AMI ID:

~~~yaml
Resources:
  AppInstance:
    Type: AWS::EC2::Instance
    Properties:
      ImageId: '{{resolve:ssm:/golden-images/orders/ami-id:7}}'
      InstanceType: t3.micro
~~~

Với dynamic reference trong Parameters section, SSM dynamic reference cần chỉ định version. Một cách khác là dùng AWS-specific parameter type để CloudFormation lấy parameter value khi tạo stack.

~~~yaml
Parameters:
  GoldenAmi:
    Type: AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>
    Default: /golden-images/orders/ami-id
~~~

### 9.2. Systems Manager SecureString

Pattern:

~~~text
{{resolve:ssm-secure:parameter-name:version}}
~~~

Dùng khi cần lấy secure string trong Parameter Store. Secure dynamic reference cần version cụ thể theo cú pháp AWS. Principal thực hiện stack operation cần quyền đọc parameter và quyền decrypt KMS phù hợp.

Không nhầm AWS::SSM::Parameter::Value<String> với một SecureString parameter type. Khi cần secure value, dùng ssm-secure dynamic reference theo đúng resource property được hỗ trợ.

### 9.3. Secrets Manager dynamic reference

Pattern tổng quát:

~~~text
{{resolve:secretsmanager:secret-id:SecretString:json-key:version-stage:version-id}}
~~~

Ví dụ lấy password field trong secret JSON:

~~~yaml
Resources:
  DatabaseInstance:
    Type: AWS::RDS::DBInstance
    Properties:
      Engine: postgres
      MasterUsername: orders_admin
      MasterUserPassword: '{{resolve:secretsmanager:orders/database:SecretString:password}}'
~~~

Đây là ví dụ minh họa property; production phải kiểm tra các properties bắt buộc của DBInstance, engine/version, storage, networking, backup và deletion protection. Stack execution role cần quyền secretsmanager:GetSecretValue và quyền KMS phù hợp khi secret dùng customer managed key.

### 9.4. Rotation và thời điểm resolve

Ưu tiên **versionless reference** khi dùng Secrets Manager rotation để CloudFormation lấy version hiện hành ở lần stack create/update thích hợp. Nhưng lưu ý:

- Chỉ thay đổi secret value trong Secrets Manager **không tự làm CloudFormation cập nhật resource** đang dùng reference.
- CloudFormation resolve lại reference khi resource được tạo hoặc update theo stack operation có liên quan.
- CloudFormation không theo dõi chính xác secret version đã được dùng trước đó như một thuộc tính drift bình thường.
- Nếu resource property không thay đổi, update stack có thể không khiến resource được cập nhật theo secret mới.
- Kiểm tra cách target service nhận/áp dụng credential mới; rotation Lambda và database connection lifecycle là trách nhiệm riêng.

### 9.5. Những giới hạn cần nhớ

- Một stack template hỗ trợ tối đa **60 dynamic references**.
- Không dùng secret dynamic reference trong primary identifier của resource vì plaintext có thể xuất hiện trong resource ID hoặc nơi phát sinh từ identifier.
- Secure dynamic references không được hỗ trợ trong custom resources.
- Dynamic references không được hỗ trợ trong AWS::CloudFormation::Init metadata và EC2 UserData.
- Khi dùng Transform, CloudFormation chuyển literal dynamic reference qua transform và resolve sau đó trong stack operation.
- Không để dynamic reference kết thúc bằng dấu backslash vì CloudFormation không thể resolve đúng.

Dynamic references giảm nguy cơ hard-code secret trong template, nhưng không tự làm mọi resource property trở nên an toàn. Phải kiểm tra service có lưu giá trị sau khi resolve ở đâu, ai đọc được và cách rotation được áp dụng.

## 10. AWS::LanguageExtensions và intrinsic functions mở rộng

Một số intrinsic functions hiện đại yêu cầu transform AWS::LanguageExtensions. Transform mở rộng template trước khi CloudFormation tạo resources.

### 10.1. Fn::ForEach

Fn::ForEach lặp qua một collection và nhân bản template fragment. Function này dùng được trong Conditions, Outputs và Resources; phải khai báo transform.

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::LanguageExtensions

Parameters:
  QueueSuffixes:
    Type: CommaDelimitedList
    Default: billing,inventory,analytics

Resources:
  'Fn::ForEach::Queues':
    - Suffix
    - !Ref QueueSuffixes
    - '${Suffix}Queue':
        Type: AWS::SQS::Queue
        Properties:
          SqsManagedSseEnabled: true
          Tags:
            - Key: Workload
              Value: !Ref AWS::StackName
~~~

Với collection billing, inventory, analytics, transform mở rộng ba resources tương ứng. Mỗi output logical ID phải hợp lệ và duy nhất; giá trị collection phải được chọn để tạo identifier hợp lệ.

Fn::ForEach không làm tăng giới hạn resource/template size: CloudFormation áp quotas trên template sau khi mở rộng. Đừng lạm dụng loop để tạo hàng trăm resources nếu module/nested stack hoặc một AWS service quản lý collection phù hợp hơn.

Khi update stack dùng AWS::LanguageExtensions, hãy gửi lại source template gốc đã được lưu trong source control. Tránh dùng tùy chọn UsePreviousTemplate/--use-previous-template: CloudFormation có thể dùng template đã được transform và giữ các parameter values đã resolve thành literals, khiến thay đổi parameter sau đó không được áp dụng như mong muốn.

### 10.2. Fn::Length

Fn::Length trả số phần tử trong list. Function này hữu ích khi cần kiểm tra hoặc xuất số lượng subnet/targets từ CommaDelimitedList.

~~~yaml
Transform: AWS::LanguageExtensions

Parameters:
  SubnetCidrs:
    Type: CommaDelimitedList
    Default: 10.40.1.0/24,10.40.2.0/24,10.40.3.0/24

Outputs:
  SubnetCount:
    Value:
      Fn::ToJsonString:
        count:
          Fn::Length:
            Ref: SubnetCidrs
~~~

Fn::Length cần AWS::LanguageExtensions transform. Không dùng để thay thế validation rằng CIDR list có các ranges không overlap.

### 10.3. Fn::ToJsonString

ToJsonString chuyển object/list thành JSON string. Có thể dùng khi resource property yêu cầu JSON text nhưng template đang xây object từ parameters/intrinsic functions.

~~~yaml
Transform: AWS::LanguageExtensions

Parameters:
  Environment:
    Type: String
    Default: dev

Outputs:
  RuntimeConfigurationJson:
    Value:
      Fn::ToJsonString:
        environment: !Ref Environment
        region: !Ref AWS::Region
        stack: !Ref AWS::StackName
~~~

Function này hữu ích cho configuration payload; tránh tự ghép JSON bằng Fn::Join vì dễ sai escaping, quote hoặc kiểu dữ liệu.

### 10.4. Fn::GetStackOutput

Function này đọc output từ stack khác mà không cần khai báo Export ở stack nguồn. Có thể dùng cross-account/cross-Region; cross-account cần RoleArn có quyền cloudformation:DescribeStacks và trust policy cho execution role của stack đích.

~~~yaml
Parameters:
  NetworkStackName:
    Type: String
    Default: shared-network

Resources:
  AppSubnetAttachment:
    Type: AWS::EC2::NetworkInterface
    Properties:
      SubnetId:
        Fn::GetStackOutput:
          StackName: !Ref NetworkStackName
          OutputName: PrivateSubnetId
          Region: ap-southeast-1
~~~

Fn::GetStackOutput là **weak reference**: giá trị được resolve tại stack create/update; khi output nguồn đổi/xóa, stack dùng nó không tự động được thông báo/cập nhật. Function này không hỗ trợ cross-partition. Nếu dùng RoleArn, scope cloudformation:DescribeStacks vào đúng stack ARN và giới hạn trust policy.

Không dùng short-form !GetStackOutput khi parameter values chứa short-form functions như !Ref hoặc !Sub; dùng full form Fn::GetStackOutput như ví dụ.

Với cross-account reference, thêm RoleArn và cấu hình role ở account nguồn cho phép cloudformation:DescribeStacks trên stack ARN cụ thể; trust policy phải cho execution role của stack đích AssumeRole. Không dùng Resource: '*' nếu có thể giới hạn vào một stack.

### 10.5. Chọn giữa các function

| Function | Khi dùng |
| --- | --- |
| Ref | Lấy parameter value hoặc resource return value. |
| GetAtt | Lấy resource-specific attribute như ARN, endpoint, queue name. |
| Sub | Tạo string từ parameters/resources/pseudo parameters. |
| Join | Nối list thành string. |
| Select | Chọn phần tử trong list theo index. |
| Split | Tách string thành list. |
| FindInMap | Tra cứu dữ liệu tĩnh. |
| GetAZs | Lấy danh sách AZ trong Region. |
| Cidr | Tính CIDR subnet từ CIDR gốc. |
| Base64 | Encode text, thường dùng với UserData. |
| If / Equals / And / Or / Not | Điều kiện và chọn property/resource. |
| ImportValue | Tham chiếu export cùng account/Region với strong dependency. |
| GetStackOutput | Tham chiếu output stack khác, hỗ trợ cross-account/Region dạng weak reference. |
| ForEach | Nhân bản fragment từ collection với LanguageExtensions. |
| Length / ToJsonString | Đếm list hoặc serialize JSON với LanguageExtensions. |

## 11. Ví dụ end-to-end: SQS queue có tùy chọn DLQ

Template dưới đây kết hợp Parameters, Conditions, Resources, intrinsic functions và Outputs trong một stack có thể triển khai. Queue được mã hóa bằng SQS-managed server-side encryption; DLQ có thể bật/tắt bằng parameter.

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Orders processing queue with an optional dead-letter queue

Parameters:
  Environment:
    Type: String
    Default: dev
    AllowedValues:
      - dev
      - staging
      - prod
    Description: Deployment environment

  QueueRetentionSeconds:
    Type: Number
    Default: 345600
    MinValue: 60
    MaxValue: 1209600
    Description: Source queue message retention in seconds

  EnableDLQ:
    Type: String
    Default: 'true'
    AllowedValues:
      - 'true'
      - 'false'
    Description: Create a dead-letter queue

Conditions:
  CreateDLQ: !Equals [!Ref EnableDLQ, 'true']

Resources:
  OrdersDeadLetterQueue:
    Type: AWS::SQS::Queue
    Condition: CreateDLQ
    Properties:
      MessageRetentionPeriod: 1209600
      SqsManagedSseEnabled: true
      Tags:
        - Key: Environment
          Value: !Ref Environment
        - Key: Purpose
          Value: orders-dead-letter

  OrdersQueue:
    Type: AWS::SQS::Queue
    Properties:
      MessageRetentionPeriod: !Ref QueueRetentionSeconds
      VisibilityTimeout: 60
      SqsManagedSseEnabled: true
      RedrivePolicy: !If
        - CreateDLQ
        - deadLetterTargetArn: !GetAtt OrdersDeadLetterQueue.Arn
          maxReceiveCount: 5
        - !Ref AWS::NoValue
      Tags:
        - Key: Environment
          Value: !Ref Environment
        - Key: Purpose
          Value: orders-processing

Outputs:
  OrdersQueueUrl:
    Description: Queue URL used by application clients
    Value: !Ref OrdersQueue

  OrdersQueueArn:
    Description: Queue ARN used in IAM policies
    Value: !GetAtt OrdersQueue.Arn

  OrdersDLQArn:
    Condition: CreateDLQ
    Description: ARN of the dead-letter queue
    Value: !GetAtt OrdersDeadLetterQueue.Arn

  Environment:
    Description: Environment selected for this stack
    Value: !Ref Environment
~~~

### 11.1. Đọc template theo từng lớp

- Parameters khai báo environment, retention và lựa chọn DLQ.
- Condition CreateDLQ xác định có tạo DLQ hay không.
- OrdersDeadLetterQueue chỉ được tạo khi condition true.
- RedrivePolicy của OrdersQueue dùng Fn::If; khi DLQ tắt, AWS::NoValue loại property khỏi queue configuration.
- GetAtt lấy DLQ ARN; Ref của SQS queue trả queue URL.
- Outputs công bố URL/ARN để application deployment hoặc IAM policy pipeline sử dụng.
- Tags giúp phân loại resources và hỗ trợ cost allocation.

Đây là ví dụ nền tảng. Production cần bổ sung queue policy, KMS customer managed key nếu có yêu cầu, CloudWatch alarms, redrive allow policy khi phù hợp, retention/replay runbook và quyền IAM tối thiểu.

### 11.2. Thử thay đổi parameter

| Environment | EnableDLQ | Kết quả mong đợi |
| --- | --- | --- |
| dev | false | Chỉ tạo OrdersQueue; không có RedrivePolicy. |
| staging | true | Tạo OrdersQueue và OrdersDeadLetterQueue; source queue trỏ tới DLQ. |
| prod | true | Tạo cả hai queues với tags prod; cần review policy/alarms/retention trước khi execute. |

Nếu stack đã tạo với DLQ và update EnableDLQ thành false, CloudFormation sẽ xóa resource OrdersDeadLetterQueue theo Condition. Hãy kiểm tra queue có messages cần giữ lại hay không trước khi thực hiện update.

## 12. Resource dependencies và lifecycle attributes

CloudFormation tạo dependency graph để quyết định thứ tự tạo, cập nhật và xóa resources.

### 12.1. Implicit dependency

Khi property của resource dùng Ref, GetAtt hoặc Sub tham chiếu resource khác, CloudFormation tự xác định dependency.

~~~yaml
Resources:
  AppQueue:
    Type: AWS::SQS::Queue

  OrdersTopic:
    Type: AWS::SNS::Topic

  QueuePolicy:
    Type: AWS::SQS::QueuePolicy
    Properties:
      Queues:
        - !Ref AppQueue
      PolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: sns.amazonaws.com
            Action: sqs:SendMessage
            Resource: !GetAtt AppQueue.Arn
            Condition:
              ArnEquals:
                aws:SourceArn: !Ref OrdersTopic
~~~

QueuePolicy phụ thuộc AppQueue và OrdersTopic do Ref/GetAtt. CloudFormation tạo resources được tham chiếu trước, rồi mới tạo policy; khi xóa, dependency được xử lý theo thứ tự ngược.

### 12.2. DependsOn

Dùng DependsOn khi có dependency về thứ tự nhưng không được thể hiện qua resource property reference.

~~~yaml
Resources:
  InternetGateway:
    Type: AWS::EC2::InternetGateway

  Vpc:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: 10.50.0.0/16

  VpcGatewayAttachment:
    Type: AWS::EC2::VPCGatewayAttachment
    Properties:
      VpcId: !Ref Vpc
      InternetGatewayId: !Ref InternetGateway

  PublicRoute:
    Type: AWS::EC2::Route
    DependsOn: VpcGatewayAttachment
    Properties:
      RouteTableId: !Ref PublicRouteTable
      DestinationCidrBlock: 0.0.0.0/0
      GatewayId: !Ref InternetGateway
~~~

DependsOn có thể nhận một logical ID hoặc list logical IDs. Không thêm DependsOn cho mọi resource một cách máy móc; Ref/GetAtt/Sub đã tạo implicit dependencies. Dùng quá nhiều explicit dependencies làm giảm khả năng parallel deployment.

### 12.3. DeletionPolicy

DeletionPolicy xác định CloudFormation xử lý resource thế nào khi resource bị xóa khỏi template hoặc stack bị xóa.

| Value | Ý nghĩa |
| --- | --- |
| Delete | Xóa resource theo hành vi mặc định của resource type. |
| Retain | Giữ physical resource lại; resource không còn được stack quản lý như trước. |
| Snapshot | Tạo snapshot trước khi xóa, nếu resource type hỗ trợ. |
| RetainExceptOnCreate | Retain trong hầu hết trường hợp, nhưng nếu resource được tạo trong stack operation đầu tiên thất bại thì có thể xóa theo semantics của attribute. |

Ví dụ giữ S3 bucket khi xóa stack:

~~~yaml
Resources:
  AuditBucket:
    Type: AWS::S3::Bucket
    DeletionPolicy: Retain
~~~

Retain có thể tạo orphan resources và tiếp tục phát sinh chi phí. Phải ghi lại ownership, backup, lifecycle và quy trình xóa thủ công khi không còn cần.

### 12.4. UpdateReplacePolicy

Khi thay đổi một property yêu cầu replacement, CloudFormation tạo physical resource mới và xử lý resource cũ theo UpdateReplacePolicy.

~~~yaml
Resources:
  Database:
    Type: AWS::RDS::DBInstance
    DeletionPolicy: Snapshot
    UpdateReplacePolicy: Snapshot
    Properties:
      Engine: postgres
      DBInstanceClass: db.t4g.micro
      AllocatedStorage: 20
      MasterUsername: dbadmin
      MasterUserPassword: '{{resolve:secretsmanager:orders/db:SecretString:password}}'
~~~

Đoạn RDS trên chỉ minh họa attributes và dynamic reference, chưa phải template production hoàn chỉnh. Kiểm tra engine/version, subnet group, security groups, backup, storage encryption, KMS và yêu cầu high availability trước khi triển khai.

DeletionPolicy áp dụng khi xóa resource khỏi stack hoặc xóa stack; UpdateReplacePolicy áp dụng cho physical resource cũ khi replacement. Hai attributes không thay thế backup/PITR hoặc quy trình phục hồi.

### 12.5. CreationPolicy và UpdatePolicy

CreationPolicy có thể khiến CloudFormation chờ signals từ resource (ví dụ Auto Scaling group/EC2) trước khi đánh dấu creation complete. UpdatePolicy kiểm soát cách cập nhật một số resource, ví dụ rolling update cho Auto Scaling group.

Dùng các attributes này khi resource cần bootstrap/health checks trước khi workload được xem là sẵn sàng. Không giả định EC2 instance ở trạng thái CREATE_COMPLETE đồng nghĩa application bên trong đã healthy nếu template không có cơ chế signal/health validation.

## 13. Chia template thành nested stacks và modules

Template lớn nên được chia theo ranh giới ownership/lifecycle, ví dụ network foundation, security baseline, data layer và application workload.

### 13.1. Nested stack

Nested stack là resource AWS::CloudFormation::Stack được tạo bên trong một parent stack. Parent có thể truyền Parameters và đọc child Outputs.

~~~yaml
Resources:
  NetworkNestedStack:
    Type: AWS::CloudFormation::Stack
    Properties:
      TemplateURL: https://example-bucket.s3.ap-southeast-1.amazonaws.com/templates/network.yaml
      Parameters:
        VpcCidr: 10.60.0.0/16
        Environment: !Ref Environment

Outputs:
  NetworkVpcId:
    Value: !GetAtt NetworkNestedStack.Outputs.VpcId
~~~

TemplateURL phải trỏ tới template đã upload lên S3 (hoặc URL được CloudFormation hỗ trợ). Không đặt URL local file:// cho nested stack. Phân quyền truy cập bucket/template và versioning để bảo đảm parent deploy đúng artifact.

### 13.2. Nested stack hay Export/ImportValue?

| Cách tổ chức | Phù hợp khi |
| --- | --- |
| Nested stacks | Các templates thuộc cùng một stack hierarchy, muốn deploy/quản lý cùng parent và truyền outputs giữa các child stacks. |
| Export + ImportValue | Các stacks độc lập cần chia sẻ resource IDs trong cùng account/Region với dependency được CloudFormation bảo vệ. |
| Fn::GetStackOutput | Cần tham chiếu outputs không export, cross-account hoặc cross-Region; chấp nhận weak reference. |
| CloudFormation modules | Muốn đóng gói resource patterns tái sử dụng thành một module được đăng ký trong CloudFormation registry. |

### 13.3. Quy tắc chia module

- Chia theo lifecycle và owner; không chia file chỉ vì template dài.
- Giữ interface nhỏ: parameters đầu vào, outputs rõ ràng.
- Không export mọi resource; chỉ công bố values cần cho consumers.
- Tránh circular dependencies giữa stacks.
- Version hóa nested templates/modules và pin artifact đã review.
- Có thể triển khai lại một module mà không làm mất state resources khác nếu ownership boundary rõ ràng.
## 14. Validate, deploy và cập nhật stack an toàn

Không nên đưa template mới vào production chỉ vì YAML parser chấp nhận file. Cần kiểm tra syntax, resource schemas, security findings, parameter values và tác động của change set.

### 14.1. Kiểm tra cấu trúc với CloudFormation

~~~bash
aws cloudformation validate-template \
  --template-body file://template.yaml \
  --region ap-southeast-1
~~~

ValidateTemplate kiểm tra template theo các quy tắc cấu trúc của dịch vụ và trả thông tin như parameters/capabilities. Nó không thay thế lint/schema checks cho mọi resource property, IAM/security rules hoặc kiểm thử deployment.

### 14.2. Lint template trước khi tạo stack

AWS CloudFormation Linter (cfn-lint) kiểm tra YAML/JSON theo resource provider schemas và các rules bổ sung.

~~~bash
cfn-lint --regions ap-southeast-1 template.yaml
~~~

Có thể truyền nhiều Regions nếu template cần deploy ở nhiều nơi:

~~~bash
cfn-lint --regions ap-southeast-1 ap-northeast-1 template.yaml
~~~

AWS CloudFormation Validate (cfn-validate) là công cụ kiểm tra local khác; nó có thể kiểm tra cấu trúc, references, resource schemas và built-in rules trước khi deploy:

~~~bash
cfn-validate template.yaml
~~~

Các công cụ local không thể mô phỏng mọi điều kiện của account đích, quota, permissions, resource state hoặc service availability. Vẫn phải review change set và kiểm thử trong sandbox.

### 14.3. Tạo change set cho stack mới

Change set hiển thị resources sẽ được tạo/thay đổi trước khi execute:

~~~bash
aws cloudformation create-change-set \
  --stack-name orders-infrastructure \
  --change-set-name orders-infrastructure-first-review \
  --change-set-type CREATE \
  --template-body file://template.yaml \
  --parameters \
    ParameterKey=Environment,ParameterValue=staging \
    ParameterKey=QueueRetentionSeconds,ParameterValue=86400 \
    ParameterKey=EnableDLQ,ParameterValue=true \
  --region ap-southeast-1
~~~

Sau khi tạo, kiểm tra change set:

~~~bash
aws cloudformation describe-change-set \
  --stack-name orders-infrastructure \
  --change-set-name orders-infrastructure-first-review \
  --region ap-southeast-1
~~~

Review resource actions, replacement behavior, parameter values, IAM changes, resource deletion và các warnings. Với stack chứa IAM resources, khai báo capability phù hợp khi tạo change set:

- CAPABILITY_IAM: chấp nhận template có thể tạo IAM resources.
- CAPABILITY_NAMED_IAM: dùng khi template tạo IAM resources có tên tùy chỉnh.
- CAPABILITY_AUTO_EXPAND: dùng trong một số trường hợp macro/transform cần auto expand.

Capability là xác nhận người triển khai đã xem xét tác động IAM/macro; nó không tự cấp permission cho caller hoặc execution role.

### 14.4. Execute change set

Chỉ execute sau khi reviewer xác nhận các thay đổi dự kiến:

~~~bash
aws cloudformation execute-change-set \
  --stack-name orders-infrastructure \
  --change-set-name orders-infrastructure-first-review \
  --region ap-southeast-1
~~~

Theo dõi tiến trình:

~~~bash
aws cloudformation describe-stacks \
  --stack-name orders-infrastructure \
  --region ap-southeast-1

aws cloudformation describe-stack-events \
  --stack-name orders-infrastructure \
  --region ap-southeast-1
~~~

Change set là bản preview, không phải transaction đảm bảo deployment chắc chắn thành công. Resource provider vẫn có thể trả lỗi khi thực thi, quota có thể thay đổi hoặc resource không đạt trạng thái ổn định. Nếu update thất bại, đọc stack events và tạo change set mới sau khi sửa template.

### 14.5. Update stack

Với stack đã tồn tại, dùng ChangeSetType UPDATE và truyền template/parameter changes mới. Dùng UsePreviousValue cho các parameters không đổi nếu CLI/API workflow cần giữ giá trị cũ.

~~~bash
aws cloudformation create-change-set \
  --stack-name orders-infrastructure \
  --change-set-name orders-infrastructure-update-review \
  --change-set-type UPDATE \
  --template-body file://template.yaml \
  --parameters \
    ParameterKey=Environment,UsePreviousValue=true \
    ParameterKey=QueueRetentionSeconds,ParameterValue=172800 \
    ParameterKey=EnableDLQ,UsePreviousValue=true \
  --region ap-southeast-1
~~~

Sau khi review change set, execute bằng lệnh execute-change-set. Không update resources được CloudFormation quản lý bằng console/CLI service trực tiếp, trừ khi có quy trình drift reconciliation rõ ràng.

### 14.6. Rollback và xử lý failure

CloudFormation theo dõi stack operation và thường rollback các thay đổi khi create/update thất bại theo rollback configuration. Khi gặp failure:

1. Mở stack Events và tìm resource đầu tiên có CREATE_FAILED/UPDATE_FAILED/DELETE_FAILED.
2. Đọc StatusReason và request ID; phân loại template error, IAM, quota, dependency hay service stabilization.
3. Kiểm tra resource state và service health.
4. Sửa template/permissions/parameters.
5. Tạo change set mới và review trước khi execute lại.

Không dùng disable rollback như cách sửa lỗi mặc định. Với UPDATE_ROLLBACK_FAILED, dùng ContinueUpdateRollback chỉ sau khi hiểu resource nào không rollback được và chọn resource skip một cách có kiểm soát. Sau recovery, đồng bộ lại template và thực tế.

## 15. Drift detection và kiểm soát thay đổi ngoài CloudFormation

Drift xảy ra khi resource được chỉnh trực tiếp ngoài CloudFormation, khiến cấu hình thực tế khác template/stack parameters.

### 15.1. Detect drift

~~~bash
aws cloudformation detect-stack-drift \
  --stack-name orders-infrastructure \
  --region ap-southeast-1
~~~

Lệnh trả DriftDetectionId. Dùng ID đó để theo dõi kết quả:

~~~bash
aws cloudformation describe-stack-drift-detection-status \
  --stack-drift-detection-id DRIFT-DETECTION-ID \
  --region ap-southeast-1

aws cloudformation describe-stack-resource-drifts \
  --stack-name orders-infrastructure \
  --region ap-southeast-1
~~~

Drift detection chỉ hỗ trợ các resource types/properties có drift support. NOT_CHECKED hoặc IN_SYNC không phải bằng chứng tuyệt đối rằng mọi cấu hình runtime đều đúng.

### 15.2. Quy trình xử lý drift

- Xác định thay đổi ngoài template do ai thực hiện và vì sao.
- So sánh desired state với actual state.
- Nếu thay đổi hợp lệ, cập nhật template/parameters để đưa vào source control.
- Nếu thay đổi không hợp lệ, tạo change set để đưa resource về desired state sau khi review.
- Với resource stateful, đánh giá backup/data impact trước khi sửa hoặc replacement.
- Ghi nhận incident/change record và ngăn thay đổi thủ công lặp lại.

Không dùng CloudFormation để vô tình ghi đè thay đổi production đã được phê duyệt nhưng chưa cập nhật vào template.

## 16. IAM, bảo mật và quản trị stack

### 16.1. CloudFormation execution role

Stack có thể dùng service role để CloudFormation gọi các AWS APIs thay mặt stack. Role này cần quyền tối thiểu cho đúng resource types/actions mà template quản lý.

- Caller tạo/update stack cần quyền CloudFormation tương ứng và quyền iam:PassRole nếu truyền service role.
- Execution role cần permissions tạo/cập nhật/xóa resource.
- Với cross-account references, role có thể cần sts:AssumeRole và cloudformation:DescribeStacks theo phạm vi.
- Không gán AdministratorAccess cho execution role chỉ để làm template deploy thành công.
- Khi sửa IAM policies trong template, review cả quyền mới và quyền bị thu hồi.

### 16.2. IAM resources và capabilities

CloudFormation yêu cầu người triển khai acknowledge khi template có IAM resources. CAPABILITY_IAM/CAPABILITY_NAMED_IAM chỉ là xác nhận đã review; caller và execution role vẫn cần quyền phù hợp.

Không tạo policy Action: '*' Resource: '*' nếu workload chỉ cần một queue, secret, topic hoặc key cụ thể. Dùng logical IDs và ARN từ Ref/GetAtt/Sub để giảm hard-code resource identifiers.

### 16.3. Bảo vệ dữ liệu nhạy cảm

- Không hard-code credentials trong template, Parameters file, Metadata hoặc Outputs.
- Dùng Secrets Manager/SSM SecureString dynamic references ở property được hỗ trợ.
- Giới hạn execution role chỉ đọc đúng secrets/parameters cần thiết.
- Kiểm tra KMS key policy và kms:Decrypt.
- Tránh đưa secret vào UserData, resource primary identifiers, tags hoặc stack events.
- Kiểm soát ai có quyền cloudformation:DescribeStacks/DescribeStackEvents/DescribeChangeSet và đọc template/parameters.
- Lưu template trong source control; tránh lưu resolved secret values trong build artifacts.

NoEcho chỉ che parameter value trong một số hiển thị; không bảo đảm secret không xuất hiện trong resource properties/logs hoặc các hệ thống downstream.

### 16.4. S3, database và tài nguyên stateful

Với S3 buckets, databases, EFS và các resources chứa dữ liệu:

- Xác định DeletionPolicy và UpdateReplacePolicy.
- Bật encryption, versioning/PITR/backup theo RPO/RTO.
- Dùng deletion protection ở database khi cần.
- Thiết kế retention/lifecycle và quy trình phục hồi.
- Kiểm tra replacement trước khi đổi immutable properties.
- Không xóa stack thử nghiệm nếu resources có Retain mà chưa có inventory/owner.

### 16.5. Tags và chi phí

Đặt tags nhất quán, ví dụ Environment, Owner, CostCenter, Application và DataClassification. Kiểm tra resource type nào hỗ trợ stack-level tag propagation và loại nào cần khai báo Tags riêng.

Cost Explorer/Cost and Usage Report có thể dùng tags để phân bổ chi phí. Tính thêm chi phí tài nguyên được Retain, snapshots, logs, NAT gateways, endpoints, KMS keys và resources không bị xóa khi stack delete.

### 16.6. YAML syntax pitfalls

- Quote String values như 'true'/'false' nếu parameter Type là String; để boolean true/false không quote khi property schema yêu cầu Boolean.
- Dùng Number cho numeric parameter và truyền giá trị phù hợp; tránh quote hoặc stringify không cần thiết khiến template khó đọc.
- Quote các strings có ký tự đặc biệt, dấu hai chấm, dấu # hoặc nội dung có thể bị YAML parser diễn giải như syntax.
- Khi intrinsic functions lồng nhau, ưu tiên full form Fn::... nếu short-form tags gây lỗi parser hoặc không được hỗ trợ.
- Tên property phân biệt chữ hoa/thường; đối chiếu chính xác resource specification.
- Logical IDs phải ổn định, hợp lệ và duy nhất; tránh tạo tên động khó dự đoán nếu không cần thiết.
- CloudFormation YAML có custom tags như !Ref, !GetAtt, !Sub; một YAML parser generic có thể báo lỗi nếu không biết các tags này.
- Không dùng template anchors/aliases hoặc YAML features mà CloudFormation không hỗ trợ; giữ template theo subset được tài liệu CloudFormation chấp nhận.

Nếu một template parse được bằng editor nhưng CloudFormation báo lỗi, kiểm tra lại YAML tag syntax, indentation, resource property names và nested intrinsic function forms.

## 17. Những sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Template hợp lệ về YAML là deploy được.” | YAML syntax chỉ là một lớp kiểm tra; còn resource schemas, IAM, quota, references và runtime service behavior. |
| “Resources là section tùy chọn.” | Resources là section bắt buộc trong CloudFormation template. |
| “Ref luôn trả ARN.” | Ref trả value theo từng resource type; SQS queue Ref trả queue URL, ARN lấy bằng GetAtt. |
| “GetAtt có thể lấy mọi thuộc tính.” | Chỉ các attributes được resource provider công bố mới dùng được. |
| “Parameters thay thế được secret manager.” | Parameter thường là stack input; secrets nên lưu trong Secrets Manager/SSM SecureString và dùng dynamic references ở nơi được hỗ trợ. |
| “NoEcho bảo vệ secret khỏi mọi nơi.” | NoEcho chỉ che một số hiển thị; secret vẫn có thể lộ trong resource properties, outputs hoặc logs. |
| “Mapping tự cập nhật theo AMI mới.” | Mappings là dữ liệu tĩnh trong template; phải cập nhật hoặc dùng Parameter Store/AMI pipeline. |
| “Condition chỉ ẩn resource mà không xóa.” | Khi condition chuyển false trong update, resource đã gắn condition có thể bị xóa. |
| “Fn::If false trả null.” | AWS::NoValue dùng để loại property khỏi resource configuration. |
| “Select tự kiểm tra list index.” | Index ngoài phạm vi có thể làm stack operation thất bại. |
| “GetAZs trả cùng tên AZ vật lý ở mọi account.” | AZ names có thể ánh xạ khác nhau giữa accounts; dùng AZ IDs khi cần đồng bộ physical AZ. |
| “Base64 là encryption.” | Base64 chỉ encoding, không bảo mật dữ liệu. |
| “Export + ImportValue dùng được cross-Region.” | Chỉ cùng account/Region; cross-account/Region cân nhắc Fn::GetStackOutput. |
| “Có thể xóa stack đang có imports.” | Stack xuất Export không thể bị xóa hoặc thay output cho tới khi consumers bỏ imports. |
| “Fn::GetStackOutput tạo strong dependency.” | Đây là weak reference, không khóa stack nguồn khỏi bị xóa. |
| “Dynamic reference tự cập nhật resource sau secret rotation.” | CloudFormation chỉ resolve khi resource được tạo/update theo stack operation liên quan. |
| “Fn::ForEach chạy mà không cần Transform.” | Phải khai báo AWS::LanguageExtensions. |
| “DependsOn cần cho mọi resource.” | Ref/GetAtt/Sub tạo implicit dependency; DependsOn chỉ dùng khi thứ tự không thể suy ra từ properties. |
| “DeletionPolicy Retain là backup.” | Retain giữ resource, không tạo backup hoặc kiểm chứng khả năng restore. |
| “UpdateReplacePolicy kiểm soát việc xóa stack.” | Attribute này xử lý resource cũ khi replacement; DeletionPolicy xử lý deletion theo stack/template. |
| “Change set đảm bảo deployment thành công.” | Change set là preview; resource provider vẫn có thể lỗi trong quá trình thực thi. |
| “Drift detection kiểm tra mọi property của mọi resource.” | Chỉ resource types/properties có drift support mới được so sánh. |
| “Tạo resource bằng console vẫn được CloudFormation tự quản lý.” | Thay đổi ngoài stack có thể tạo drift hoặc resource unmanaged. |
| “Stack UPDATE_COMPLETE chứng minh ứng dụng healthy.” | CloudFormation theo dõi resource provisioning; cần application health checks và alarms riêng. |
| “Stack-level tags chắc chắn tới mọi resource.” | Tag propagation phụ thuộc resource type; kiểm tra và khai báo Tags riêng khi cần. |

## 18. Bài tập thực hành có đáp án gợi ý

### Bài tập 1 — Parameter cho nhiều environments

**Đề:** Một template cần triển khai dev, staging và prod với cùng resource types nhưng instance size khác nhau.

**Đáp án:** Dùng Parameter Environment có AllowedValues; dùng Mappings + FindInMap cho giá trị tĩnh hoặc parameterized values theo pipeline. Với config thay đổi thường xuyên, cân nhắc Parameter Store/AppConfig.

### Bài tập 2 — Ref trả queue ARN hay URL?

**Đề:** IAM policy cần ARN của SQS queue, nhưng template đang dùng Value: !Ref OrdersQueue.

**Đáp án:** Ref của AWS::SQS::Queue trả queue URL. Dùng !GetAtt OrdersQueue.Arn để lấy ARN.

### Bài tập 3 — Bật/tắt DLQ

**Đề:** Dev không cần DLQ, production cần DLQ; muốn dùng cùng template.

**Đáp án:** Khai báo parameter EnableDLQ, Condition CreateDLQ, gắn Condition cho DLQ resource và dùng Fn::If/AWS::NoValue cho RedrivePolicy. Trước khi tắt DLQ ở stack đã có, kiểm tra dữ liệu đang nằm trong queue.

### Bài tập 4 — Chia CIDR VPC

**Đề:** VPC có CIDR /16, muốn tạo bốn subnet /24.

**Đáp án:** Fn::Cidr với số CIDR là 4 và số bits bổ sung là 8. Dùng Select với index hợp lệ để gán mỗi subnet block.

### Bài tập 5 — Chia sẻ VPC giữa hai stacks

**Đề:** Network stack tạo VPC, application stack cần VPC ID trong cùng account/Region.

**Đáp án:** Network stack export output VPC ID; application stack dùng Fn::ImportValue. Trước khi xóa/đổi export, dùng list-imports để tìm và gỡ mọi consumers.

### Bài tập 6 — Cross-account output

**Đề:** Application stack ở account B cần subnet ID từ network stack account A.

**Đáp án:** Export/ImportValue không hỗ trợ cross-account. Dùng Fn::GetStackOutput với RoleArn ở account A có cloudformation:DescribeStacks trên stack ARN cụ thể và trust policy cho execution role của account B.

### Bài tập 7 — Secret trong RDS template

**Đề:** Không muốn database password xuất hiện trong template Git.

**Đáp án:** Lưu secret trong Secrets Manager, dùng dynamic reference ở MasterUserPassword nếu resource property hỗ trợ, cấp quyền GetSecretValue/KMS cho stack execution role và không đưa secret vào Outputs. Thiết kế rotation riêng.

### Bài tập 8 — Secret đã rotate nhưng database chưa đổi password

**Đề:** Secrets Manager AWSCURRENT đổi, nhưng DB instance vẫn dùng password cũ.

**Đáp án:** Dynamic reference không tự cập nhật resource khi secret value đổi. Phải có resource/stack update phù hợp hoặc rotation integration được dịch vụ hỗ trợ; kiểm tra connection pool và target database state.

### Bài tập 9 — Fn::Sub literal

**Đề:** UserData cần chứa literal string ${HOME} của shell nhưng Fn::Sub đang thay placeholder.

**Đáp án:** Escape placeholder theo cú pháp Fn::Sub và kiểm tra shell nhận được string đúng. Không để shell variable bị CloudFormation hiểu nhầm thành parameter/resource reference.

### Bài tập 10 — Condition chuyển từ true sang false

**Đề:** Stack đã tạo ProductionAlarm với Condition IsProduction. Update Environment thành dev.

**Đáp án:** Resource gắn condition false có thể bị xóa. Đánh giá deletion/retention trước khi thay parameter; không dùng Condition để bảo vệ stateful resource nếu chưa thiết kế lifecycle.

### Bài tập 11 — Template cần tạo nhiều queues

**Đề:** Có 8 queues cùng cấu trúc, muốn tránh lặp YAML.

**Đáp án:** Có thể dùng AWS::LanguageExtensions + Fn::ForEach với CommaDelimitedList. Kiểm tra logical IDs sau expansion, quotas và template readability.

### Bài tập 12 — Resource phải tạo sau gateway attachment

**Đề:** Public route phải được tạo sau VPC gateway attachment, nhưng properties không tham chiếu attachment.

**Đáp án:** Dùng DependsOn cho VpcGatewayAttachment. Không thêm DependsOn nếu dependency đã được thể hiện bằng Ref/GetAtt/Sub.

### Bài tập 13 — Thay đổi instance type gây replacement

**Đề:** Change set báo resource cần replacement; dữ liệu local trên instance có thể mất.

**Đáp án:** Review replacement, snapshot/backup, DeletionPolicy và UpdateReplacePolicy. Nếu state cần tồn tại, tách state sang managed storage và có migration/rollback plan.

### Bài tập 14 — Stack drift

**Đề:** Một operator chỉnh security group rule trực tiếp trong console.

**Đáp án:** Chạy detect-stack-drift, đọc resource drift details, xác định thay đổi có được phê duyệt không. Nếu hợp lệ, cập nhật template; nếu không, tạo change set đưa resource về desired state.

### Bài tập 15 — Change set có IAM role

**Đề:** Template tạo IAM role có custom name và policy.

**Đáp án:** Dùng CAPABILITY_NAMED_IAM khi tạo stack/change set, review principal/actions/resources và execution role. Capability acknowledgement không thay quyền IAM thực tế.

### Bài tập 16 — CloudFormation rollback thất bại

**Đề:** Stack ở UPDATE_ROLLBACK_FAILED.

**Đáp án:** Đọc Events/StatusReason, tìm resource không rollback được, khôi phục dependency/permission/service state. Dùng ContinueUpdateRollback có kiểm soát, chỉ skip resource khi hiểu hậu quả và sau đó đồng bộ lại template.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** CloudFormation template thường dùng những định dạng nào?  
**Đáp án:** YAML hoặc JSON.

**Câu 2.** Section nào bắt buộc trong template?  
**Đáp án:** Resources.

**Câu 3.** Stack là gì?  
**Đáp án:** Tập hợp resources được CloudFormation quản lý từ một template và parameter values.

**Câu 4.** Logical ID khác Physical ID thế nào?  
**Đáp án:** Logical ID là định danh trong template; Physical ID là resource identifier thực tế được AWS service tạo.

**Câu 5.** Parameters dùng để làm gì?  
**Đáp án:** Nhận input khi tạo/update stack để tái sử dụng template.

**Câu 6.** AllowedValues có tác dụng gì?  
**Đáp án:** Giới hạn parameter vào một tập giá trị cho phép.

**Câu 7.** NoEcho có phải secret vault không?  
**Đáp án:** Không; chỉ che một số hiển thị, không bảo đảm secret không lộ ở nơi khác.

**Câu 8.** AWS::SSM::Parameter::Value<String> dùng để làm gì?  
**Đáp án:** Lấy parameter value từ Systems Manager Parameter Store theo key.

**Câu 9.** Mappings phù hợp với loại dữ liệu nào?  
**Đáp án:** Lookup data tĩnh trong template, ví dụ config theo Region/environment.

**Câu 10.** Function nào tra cứu Mappings?  
**Đáp án:** Fn::FindInMap.

**Câu 11.** Conditions có thể tham chiếu resource attributes không?  
**Đáp án:** Không; condition dựa trên parameters, pseudo parameters, mappings và conditions khác.

**Câu 12.** Khi condition của resource chuyển false trong update, điều gì có thể xảy ra?  
**Đáp án:** Resource có thể bị xóa khỏi stack.

**Câu 13.** AWS::NoValue dùng khi nào?  
**Đáp án:** Trong Fn::If để loại property khỏi resource configuration.

**Câu 14.** Outputs dùng để làm gì?  
**Đáp án:** Công bố resource identifiers/values sau khi stack triển khai.

**Câu 15.** Ref của SQS queue trả về gì?  
**Đáp án:** Queue URL; ARN lấy bằng GetAtt.

**Câu 16.** Fn::GetAtt dùng để làm gì?  
**Đáp án:** Lấy resource-specific attribute như ARN, queue name hoặc endpoint.

**Câu 17.** Fn::Sub có ưu điểm gì?  
**Đáp án:** Thay placeholder trong string bằng parameters, pseudo parameters, resource IDs hoặc attributes.

**Câu 18.** Fn::Select dùng index bắt đầu từ số mấy?  
**Đáp án:** Zero-based index, bắt đầu từ 0.

**Câu 19.** Fn::GetAZs trả gì?  
**Đáp án:** Danh sách Availability Zones trong Region được chỉ định.

**Câu 20.** Fn::Cidr làm gì?  
**Đáp án:** Tạo danh sách CIDR subnet từ CIDR block gốc.

**Câu 21.** Base64 có mã hóa bí mật không?  
**Đáp án:** Không; Base64 chỉ là encoding.

**Câu 22.** Fn::ImportValue hỗ trợ cross-Region không?  
**Đáp án:** Không; chỉ cùng account và Region.

**Câu 23.** Khi stack khác import một Export, stack nguồn có thể bị xóa không?  
**Đáp án:** Không cho tới khi mọi imports được gỡ bỏ.

**Câu 24.** Fn::GetStackOutput khác ImportValue thế nào?  
**Đáp án:** Không cần Export, hỗ trợ cross-account/Region nhưng là weak reference.

**Câu 25.** Fn::ForEach cần Transform nào?  
**Đáp án:** AWS::LanguageExtensions.

**Câu 26.** Fn::Length và Fn::ToJsonString thuộc nhóm nào?  
**Đáp án:** Intrinsic functions được hỗ trợ qua AWS::LanguageExtensions.

**Câu 27.** Dynamic reference có tự cập nhật resource khi secret rotate không?  
**Đáp án:** Không; CloudFormation resolve khi resource được tạo/update theo stack operation liên quan.

**Câu 28.** Dynamic reference template hỗ trợ tối đa bao nhiêu references?  
**Đáp án:** 60 cho mỗi stack template.

**Câu 29.** DependsOn cần khi nào?  
**Đáp án:** Khi cần chỉ định thứ tự dependency mà Ref/GetAtt/Sub không tự thể hiện.

**Câu 30.** DeletionPolicy Retain làm gì?  
**Đáp án:** Giữ physical resource khi resource bị xóa khỏi stack hoặc stack bị xóa; resource có thể trở thành unmanaged.

**Câu 31.** UpdateReplacePolicy áp dụng khi nào?  
**Đáp án:** Khi resource bị replacement trong stack update, áp dụng lên physical resource cũ.

**Câu 32.** Change set có tự thực thi thay đổi không?  
**Đáp án:** Không; cần execute change set sau khi review.

**Câu 33.** cfn-lint giúp gì?  
**Đáp án:** Kiểm tra templates theo CloudFormation schemas và rules, phát hiện invalid properties/references và common issues.

**Câu 34.** Drift detection có kiểm tra mọi resource/property không?  
**Đáp án:** Không; chỉ những resource types/properties được hỗ trợ.

**Câu 35.** Vì sao nên dùng CloudFormation execution role least privilege?  
**Đáp án:** Giới hạn quyền mà CloudFormation có thể sử dụng để tạo/cập nhật/xóa resources, giảm blast radius.

## 20. Checklist production và tài liệu tham khảo

### 20.1. Checklist trước production

1. Template nằm trong source control, có owner, version và review history.
2. Logical IDs ổn định; parameters có type, description, constraints và defaults hợp lý.
3. Mappings chỉ chứa dữ liệu tĩnh; dữ liệu thay đổi thường xuyên lấy từ parameter/config service phù hợp.
4. Conditions không vô tình xóa stateful resources khi parameter đổi.
5. Outputs công bố đúng values; không đưa secrets vào Outputs.
6. Export names duy nhất; có inventory consumers trước khi thay đổi/xóa exports.
7. Intrinsic functions dùng đúng resource return values và đúng vị trí schema hỗ trợ.
8. Pseudo parameters được dùng thay cho hard-code account/Region/partition khi có thể.
9. Dynamic references dùng đúng pattern, permissions, version/rotation strategy và không nằm trong primary identifiers.
10. AWS::LanguageExtensions/Fn::ForEach được khai báo transform và kiểm tra expanded template quotas.
11. Dependencies dùng implicit references trước; DependsOn chỉ dùng khi cần.
12. DeletionPolicy/UpdateReplacePolicy được xác định cho database, buckets, storage và resources stateful.
13. Nested stacks/modules có interface nhỏ, artifact versioned và không tạo circular dependencies.
14. ValidateTemplate, cfn-lint hoặc cfn-validate chạy trong CI.
15. Change set được review; replacement, IAM changes, resource deletion và quota được kiểm tra.
16. CloudFormation execution role và iam:PassRole được giới hạn least privilege.
17. Tags, encryption, logging, backups/PITR, deletion protection và retention đáp ứng policy.
18. Drift detection và reconciliation có lịch vận hành.
19. Rollback, recovery và resource import/replacement có runbook.
20. Cost review tính cả retained resources, snapshots, NAT, endpoints, logs, KMS và downstream dependencies.

### 20.2. Kết luận

CloudFormation template là bản mô tả trạng thái hạ tầng mong muốn. Parameters giúp một template phục vụ nhiều environments; Mappings và Conditions chọn cấu hình; Outputs công bố các giá trị cần thiết; intrinsic functions kết nối các phần của template và tham chiếu tài nguyên lúc deploy.

Khi thiết kế production, phải xem template cùng với IAM execution role, resource lifecycle, change sets, dynamic references, drift detection và quy trình rollback. Một template có thể deploy thành công nhưng vẫn thiếu backup, quyền least privilege, monitoring hoặc application readiness. Hãy kiểm tra cả cấu hình resource lẫn cách team vận hành stack qua nhiều lần update.

### 20.3. Tài liệu AWS chính thức

- [CloudFormation template sections](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-anatomy.html) — cấu trúc template, Resources, Parameters, Outputs, Mappings, Conditions và Transform.
- [Parameters syntax](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/parameters-section-structure.html) — parameter types, constraints và references.
- [Outputs syntax](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/outputs-section-structure.html) — outputs và export names.
- [Intrinsic function reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/intrinsic-function-reference.html) — danh sách functions và vị trí được hỗ trợ.
- [Fn::GetAtt](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/intrinsic-function-reference-getatt.html) — resource attributes.
- [Fn::Sub](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/intrinsic-function-reference-sub.html) — string substitution và variable map.
- [Condition functions](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/intrinsic-function-reference-conditions.html) — Equals, And, Or, Not và If.
- [Fn::ForEach](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/intrinsic-function-reference-foreach.html) — loop expansion và LanguageExtensions.
- [Fn::GetStackOutput](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/intrinsic-function-reference-getstackoutput.html) — cross-account/Region stack outputs.
- [Cross-stack exports and imports](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-exports.html) — Export, ImportValue và list-imports.
- [Dynamic references](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references.html) — Parameter Store/Secrets Manager references và limitations.
- [Secrets Manager dynamic references](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references-secretsmanager.html) — versionless references và rotation behavior.
- [CloudFormation best practices](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html) — quản lý stack, credentials và change sets.
- [Create a change set](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets-create.html) — preview stack changes.
- [Validate with cfn-lint](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cfn-lint.html) — local schema/rule validation.
- [Validate stack deployments](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/validate-stack-deployments.html) — deployment validation và change set review.
- [DependsOn attribute](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-dependson.html) — explicit resource dependencies.











