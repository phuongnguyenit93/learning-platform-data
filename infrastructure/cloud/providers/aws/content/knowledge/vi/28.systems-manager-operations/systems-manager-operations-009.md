# Parameter Store, hierarchy và kiểm soát quyền cấu hình

> **Chương:** Vận hành với Systems Manager  
> **Module:** CLOUD_PROVIDERS_AWS  
> **Mục tiêu:** thiết kế hệ thống lưu trữ cấu hình tập trung bằng AWS Systems Manager Parameter Store; tổ chức parameter theo hierarchy; kiểm soát quyền đọc, ghi, giải mã và chia sẻ; quản lý version, policy, throughput và vòng đời cấu hình an toàn.

## 1. Bài toán: cấu hình phân tán gây khó vận hành

Một hệ thống bán hàng chạy trên AWS có nhiều thành phần:

- Spring Boot API trên Amazon ECS.
- Worker xử lý message trên Lambda.
- EC2 instances chạy tác vụ nền.
- Pipeline CI/CD deploy qua nhiều môi trường.
- Các service dùng chung endpoint, feature flags, giới hạn timeout và cấu hình kết nối.

Nếu mỗi service giữ cấu hình trong file riêng, biến môi trường hoặc AMI, đội vận hành dễ gặp các vấn đề:

- Một endpoint đổi nhưng chỉ một phần instances được cập nhật.
- Dev và production vô tình dùng nhầm cấu hình.
- Giá trị cũ bị giữ trong container sau deployment.
- Người phát triển có quyền đọc cả cấu hình production dù chỉ cần development.
- Secret bị commit vào Git hoặc in ra log.
- Không biết ai đổi giá trị, đổi lúc nào và có thể quay về version nào.
- Khi scale-out, hàng trăm instances cùng gọi API lấy cấu hình và bị throttling.

AWS Systems Manager Parameter Store cung cấp một kho cấu hình có quản lý, truy cập qua API, tích hợp IAM/KMS và hỗ trợ tổ chức dữ liệu theo đường dẫn phân cấp.

Ví dụ một nhóm parameters:

```text
/shop/dev/api/log-level
/shop/dev/api/request-timeout
/shop/dev/api/payment-endpoint
/shop/prod/api/log-level
/shop/prod/api/request-timeout
/shop/prod/api/payment-endpoint
/shop/prod/api/database-password
/shop/prod/worker/queue-url
```

Ứng dụng chỉ đọc các parameters thuộc môi trường và service mà nó được phép truy cập. Đội platform quản lý naming convention, policies, encryption và access review tập trung.

## 2. Parameter Store là gì và dùng cho việc gì?

Parameter Store là capability của AWS Systems Manager để lưu dữ liệu cấu hình dưới dạng key/value parameters. Ứng dụng và automation có thể tạo, cập nhật, truy xuất và quản lý parameters qua Console, AWS CLI, SDK hoặc API.

Các tình huống phù hợp:

- Application configuration: log level, timeout, endpoint, feature configuration đơn giản.
- Environment-specific settings: dev, staging, production.
- Operational values: AMI ID đã được phê duyệt, release channel, agent version.
- Resource identifiers: VPC/subnet IDs, queue URLs, bucket names.
- Secure configuration: giá trị nhạy cảm cần mã hóa bằng KMS.
- Automation: runbooks, EC2 bootstrap, deployment scripts và CloudFormation.

Parameter Store phù hợp khi cần kho cấu hình tập trung, phân cấp và tích hợp với Systems Manager. Nó không tự động triển khai cấu hình xuống mọi ứng dụng: workload phải có quyền gọi API, cơ chế lấy giá trị, cache/refresh strategy và quy trình xử lý khi parameter thay đổi.

### 2.1. Chọn đúng dịch vụ cho dữ liệu

| Nhu cầu | Dịch vụ nên đánh giá | Lý do |
|---|---|---|
| Cấu hình đơn giản, giá trị nhỏ, đọc qua API | Parameter Store | Hierarchy, IAM, versions và tích hợp Systems Manager |
| Database password/API key cần rotation tự động | AWS Secrets Manager | Quản lý secrets chuyên dụng và rotation integrations |
| Feature flags, dynamic configuration rollout | AWS AppConfig | Deployment strategies, validators, gradual rollout và rollback |
| File cấu hình lớn hoặc artifact | Amazon S3 | Phù hợp object/file, versioning và lifecycle |
| Secret trong Kubernetes workload | AWS Secrets Manager hoặc tích hợp phù hợp của nền tảng | Secret lifecycle và workload integration |

Không lưu database passwords hoặc API keys vào `String`/`StringList`. Với dữ liệu nhạy cảm đơn giản có thể dùng `SecureString`, nhưng nếu cần automatic rotation, cross-account secret lifecycle hoặc quản lý credentials chuyên dụng, AWS khuyến nghị Secrets Manager.

### 2.2. Parameter Store không phải dynamic configuration rollout engine

Ứng dụng đọc một parameter ở startup thường giữ giá trị trong memory cho tới khi đọc lại hoặc restart. Parameter Store không tự gửi push notification tới mọi process đang chạy.

Nếu cần thay đổi cấu hình theo tỷ lệ traffic, validate trước khi publish, gradual deployment hoặc rollback cấu hình, đánh giá AWS AppConfig. Parameter Store vẫn có thể là configuration source cho AppConfig khi kiến trúc hỗ trợ.

## 3. Mô hình parameter và các loại dữ liệu

Mỗi parameter có các thuộc tính chính:

- **Name:** tên duy nhất trong Region, có thể chứa hierarchy path.
- **Value:** giá trị cấu hình.
- **Type:** `String`, `StringList` hoặc `SecureString`.
- **Tier:** `Standard` hoặc `Advanced` (có thể cấu hình Intelligent-Tiering làm default tier).
- **Version:** số version tăng dần khi cập nhật.
- **Description:** mô tả mục đích, owner hoặc change reference.
- **DataType:** loại dữ liệu bổ sung, ví dụ `text`, `aws:ec2:image`, `aws:ssm:...` theo service hỗ trợ.
- **Tags:** metadata để quản trị và phân bổ ownership khi API/service hỗ trợ.

Parameter name, description và metadata không được mã hóa như value của SecureString. Không đặt password, token hoặc PII trong tên, description hay tag.

### 3.1. String

Dùng cho một giá trị đơn:

```text
INFO
https://api.example.internal
3000
true
```

Ví dụ:

```bash
aws ssm put-parameter --region ap-southeast-1 --name "/shop/prod/api/log-level" --type String --value "INFO" --description "Application log level"
```

`String` không cung cấp lớp mã hóa SecureString bằng KMS key có thể chọn và phân quyền decrypt riêng. Parameter Store vẫn bảo vệ dữ liệu lưu trữ/truyền tải theo cơ chế AWS-managed encryption và TLS, nhưng không dùng String cho password, API token, private key hoặc dữ liệu bí mật cần kiểm soát truy cập giải mã.

### 3.2. StringList

Dùng cho danh sách các giá trị phân cách bằng dấu phẩy, không có escaping semantics tổng quát cho mọi kiểu dữ liệu:

```text
subnet-0123456789abcdef0,subnet-0abcdef0123456789
```

Ứng dụng phải parse đúng format. Nếu value cần JSON phức tạp, cấu trúc lồng nhau hoặc escaping rõ ràng, dùng parameter `String` chứa JSON khi tier/data type hỗ trợ, hoặc S3/AppConfig tùy mục đích.

### 3.3. SecureString

Dùng khi value cần được mã hóa bằng AWS KMS:

```bash
aws ssm put-parameter --region ap-southeast-1 --name "/shop/prod/api/partner-token" --type SecureString --key-id alias/shop-prod-parameters --value "REPLACE_WITH_SECRET_VALUE"
```

Khi đọc bằng CLI, chỉ trả plaintext nếu yêu cầu `--with-decryption`:

```bash
aws ssm get-parameter --region ap-southeast-1 --name "/shop/prod/api/partner-token" --with-decryption
```

Không chạy lệnh trên terminal được ghi lại công khai hoặc CI log không được bảo vệ. Tránh đặt secret literal trong shell history, command arguments hoặc pipeline logs. Trong production, dùng secret injection/SDK với temporary credentials và tránh in response object.

### 3.4. DataType và AMI validation

Parameter có thể dùng data type `aws:ec2:image` cho AMI IDs. Parameter Store có thể xác thực AMI ID theo tích hợp EC2; validation diễn ra bất đồng bộ nên request PutParameter có thể trả về trước khi validation hoàn tất.

Ví dụ:

```bash
aws ssm put-parameter --region ap-southeast-1 --name "/shop/prod/ec2/approved-ami" --type String --data-type aws:ec2:image --value "ami-0123456789abcdef0"
```

Ứng dụng/automation không nên giả định parameter hợp lệ ngay khi API write trả thành công. Kiểm tra trạng thái/giá trị sau khi validation hoàn tất và xử lý validation failure.

## 4. Hierarchy: thiết kế đường dẫn có chủ đích

Hierarchy là cấu trúc tên parameter phân cấp bằng dấu `/`. Ví dụ:

```text
/<organization>/<environment>/<application>/<component>/<setting>
```

Một convention có thể dùng:

```text
/shop/prod/orders-api/database/host
/shop/prod/orders-api/database/port
/shop/prod/orders-api/http/read-timeout
/shop/prod/orders-api/logging/level
/shop/prod/payment-worker/queue/url
/shop/staging/orders-api/database/host
```

Một parameter có thể được đặt ở bất kỳ cấp nào. Parameter Store hỗ trợ tối đa 15 cấp hierarchy. Parameter name phải duy nhất trong một Region; cùng tên ở hai Regions là hai parameters riêng biệt.

### 4.1. Quy tắc thiết kế hierarchy

Một hierarchy tốt nên:

1. Phân biệt account/environment theo boundary quản trị.
2. Phân biệt application/service để giới hạn blast radius.
3. Phân biệt loại dữ liệu: networking, database, logging, feature, security.
4. Đủ ngắn để không vượt giới hạn depth/name.
5. Không encode dữ liệu nhạy cảm trong path.
6. Có owner và naming convention được ghi trong platform documentation.

Ví dụ:

| Path | Ý nghĩa |
|---|---|
| `/shop/dev/orders-api/...` | Cấu hình development cho Orders API |
| `/shop/staging/orders-api/...` | Cấu hình staging |
| `/shop/prod/orders-api/...` | Cấu hình production |
| `/shared/prod/network/...` | Cấu hình shared network |
| `/platform/prod/agents/...` | Cấu hình platform agents |

### 4.2. Chọn account boundary trước hierarchy

Không dùng một hierarchy để thay thế account isolation. Với hệ thống có yêu cầu tách biệt production:

- Production parameters có thể nằm trong production account.
- Shared configuration có thể nằm trong platform account và được chia sẻ có kiểm soát.
- Development account không nên có quyền đọc production SecureString.
- Cross-account sharing chỉ bật cho advanced parameters và cần AWS RAM.
- Mỗi Region có parameter namespace riêng; không giả định parameter tự replicate giữa Regions.

### 4.3. Tránh hierarchy quá rộng

Một path như `/shop` có thể chứa tất cả môi trường, services và secrets. Nếu một role được phép `GetParametersByPath` recursively trên `/shop`, blast radius rất lớn.

Tách path theo application/environment và cấp quyền đúng leaf path. Với dữ liệu nhạy cảm, kết hợp IAM path restrictions với KMS decrypt permissions.

### 4.4. Phân biệt path và tên parameter

Ví dụ:

- Path: `/shop/prod/orders-api/database`
- Parameter name: `/shop/prod/orders-api/database/host`
- Parent path: `/shop/prod/orders-api`
- Full ARN: `arn:aws:ssm:ap-southeast-1:111122223333:parameter/shop/prod/orders-api/database/host`

Khi gọi `GetParametersByPath`, tham số `Path` là hierarchy path; nó không bao gồm tên parameter cuối cùng. Dùng `Recursive=true` nếu cần lấy descendants ở mọi cấp, nhưng phải xem xét kỹ quyền IAM.

## 5. Quy hoạch tên, ownership và tags

Một parameter không nên chỉ có tên dễ nhớ; nó cần owner và mục đích vận hành.

Naming convention ví dụ:

```text
/<business-unit>/<environment>/<application>/<domain>/<setting>
```

Ví dụ:

```text
/commerce/prod/checkout-api/database/host
/commerce/prod/checkout-api/http/connection-timeout-ms
/commerce/prod/checkout-api/feature/new-checkout-enabled
/commerce/dev/checkout-api/logging/level
```

Tags có thể dùng để quản trị:

| Tag | Ví dụ | Mục đích |
|---|---|---|
| `Owner` | `checkout-team` | Đội chịu trách nhiệm |
| `Environment` | `prod` | Phân biệt môi trường |
| `Application` | `checkout-api` | Nhóm ứng dụng |
| `DataClass` | `confidential` | Phân loại dữ liệu |
| `CostCenter` | `CC-420` | Phân bổ chi phí |
| `ManagedBy` | `platform-iac` | Nguồn quản lý cấu hình |

Tags không thay thế IAM path policy hoặc KMS permissions. Không phải mọi Parameter Store API hỗ trợ resource-level tag condition theo cùng cách; kiểm tra authorization reference của action cụ thể trước khi dựa vào tags để bảo vệ dữ liệu.

### 5.1. Không dùng tên parameter làm secret

Tên `/shop/prod/database/admin-password` tiết lộ thông tin về kiến trúc và loại credential. Ưu tiên tên mang tính chức năng nhưng không chứa value/PII, và giới hạn quyền `DescribeParameters`/`GetParametersByPath` nếu metadata cũng nhạy cảm.

### 5.2. Ownership và change request

Mỗi production parameter nên có:

- Owner/team.
- Mục đích và consumer.
- Data classification.
- Change approval nếu ảnh hưởng production.
- KMS key và IAM access model.
- Expected refresh behavior.
- Rollback version/previous value handling.
- Retention/deletion policy nếu là temporary configuration.

## 6. Standard và Advanced tiers

Parameter tier quyết định giới hạn lưu trữ và tính năng. Nó độc lập với throughput setting.

| Thuộc tính | Standard | Advanced |
|---|---:|---:|
| Số parameters tối đa/account/Region | 10.000 | 100.000 |
| Kích thước value tối đa | 4 KB | 8 KB |
| Parameter policies | Không | Có |
| Chia sẻ cross-account qua AWS RAM | Không | Có |
| Số parameter policies tối đa/parameter | 0 | 10 |
| Data types | Hầu hết, trừ một số types như URL/JSON/JSONC | Hỗ trợ đầy đủ các data types được công bố |
| Chuyển tier | Có thể nâng lên Advanced | Không thể hạ xuống Standard |
| Storage charge | Không tính phí Parameter Store cho Standard | Có phí Advanced theo pricing hiện hành |

Các giới hạn và pricing có thể thay đổi; kiểm tra AWS Systems Manager quotas và pricing trước khi thiết kế số lượng lớn.

### 6.1. Khi nào chọn Standard?

- Cấu hình đơn giản, nhỏ hơn 4 KB.
- Không cần parameter policies.
- Không cần chia sẻ cross-account.
- Workload có số lượng parameters trong giới hạn.
- Muốn dùng tier miễn phí của Parameter Store.

### 6.2. Khi nào chọn Advanced?

- Value lớn hơn 4 KB nhưng không vượt 8 KB.
- Cần expiration/no-change notification policies.
- Cần chia sẻ parameter qua AWS RAM.
- Số lượng vượt Standard quota.
- Cần data types chỉ có ở Advanced tier.

Advanced tier có phí. Đừng nâng mọi parameter lên Advanced chỉ vì một vài settings cần policy hoặc sharing.

### 6.3. Intelligent-Tiering

Parameter Store cho phép đặt default parameter tier là Standard, Advanced hoặc Intelligent-Tiering ở account/Region. Với Intelligent-Tiering, Parameter Store tạo Standard khi request đáp ứng giới hạn Standard và tự nâng lên Advanced khi cần tính năng/giới hạn Advanced, ví dụ value vượt 4 KB, parameter policy, cross-account sharing, data type chỉ hỗ trợ Advanced hoặc cần vượt Standard quota. Đây là cách giữ Standard cho cấu hình thông thường nhưng vẫn nâng tier khi request cần; theo dõi Advanced charges và kiểm tra pricing hiện hành.

Default tier ảnh hưởng parameters mới khi request không chỉ định tier. Có thể override tier cho từng parameter bằng PutParameter.

### 6.4. Nâng cấp Standard lên Advanced

Có thể nâng một Standard parameter lên Advanced khi cần tính năng/giới hạn cao hơn. Không thể downgrade Advanced về Standard. Khi thay đổi tier, tính phí và lifecycle cần được xem xét; nếu cần trở lại Standard, phải lập kế hoạch tạo parameter mới và chuyển consumer có kiểm soát.

## 7. Versioning, labels và lịch sử thay đổi

Mỗi lần cập nhật value, Parameter Store tạo version mới. Ví dụ:

| Version | Value | Ý nghĩa |
|---:|---|---|
| 1 | `INFO` | Giá trị ban đầu |
| 2 | `WARN` | Giảm log volume |
| 3 | `DEBUG` | Tạm thời điều tra lỗi |

Parameter history hỗ trợ truy xuất version cũ và metadata thay đổi. Parameter Store giữ tối đa 100 versions cho mỗi parameter; khi vượt giới hạn, version cũ nhất có thể bị loại bỏ theo quy tắc service. Không coi Parameter Store history là archive bất biến hoặc audit ledger dài hạn.

### 7.1. Labels

Labels là tên tùy chỉnh gắn vào một version, ví dụ:

- `current`
- `candidate`
- `stable`
- `rollback`

Một label có thể được di chuyển giữa versions. Điều này giúp consumer hoặc release process tham chiếu version có ý nghĩa, nhưng label không phải immutable pointer.

Ví dụ:

```bash
aws ssm label-parameter-version --region ap-southeast-1 --name "/shop/prod/orders-api/logging/level" --parameter-version 3 --labels stable
```

Không để nhiều deployment pipelines tự ý di chuyển cùng label nếu không có ownership/locking rõ ràng.

### 7.2. Rollback

Có thể rollback bằng cách ghi lại value/version mong muốn thành một version mới. Không giả định version cũ còn tồn tại mãi. Quy trình production nên:

1. Lưu previous value/version trước change.
2. Approval change.
3. Ghi value mới.
4. Kiểm tra consumer đã đọc value mới.
5. Nếu lỗi, ghi lại value trước đó như một version mới.
6. Lưu change reference, operator và timestamp.

### 7.3. GetParameterHistory là dữ liệu nhạy cảm

Parameter history có thể trả cả versions trước đó, bao gồm SecureString values. Khi request bật WithDecryption và principal có quyền `kms:Decrypt`, giá trị SecureString có thể được trả ở dạng plaintext. Phải giới hạn `ssm:GetParameterHistory`. Một principal bị deny GetParameter nhưng được allow GetParameterHistory có thể vẫn đọc current value qua history API theo behavior được AWS mô tả.

Với AWS CLI, `get-parameter-history` có tùy chọn `--with-decryption`; chỉ dùng khi role được phép giải mã và output được bảo vệ.

Vì vậy policy kiểm soát retrieval cần xem cả `GetParameter`, `GetParameters`, `GetParametersByPath` và `GetParameterHistory`.

## 8. IAM: kiểm soát ai được đọc và thay đổi parameter

Parameter Store authorization dựa trên IAM. Principal có thể là IAM role/user, EC2 instance profile, Lambda execution role, ECS task role, CodeBuild service role hoặc service role khác. Ưu tiên Allow hẹp vào đúng parameters/path mà workload cần; tách sensitive parameters sang path riêng để đơn giản hóa access control.

Các actions thường gặp:

| IAM action | Tác dụng |
|---|---|
| `ssm:PutParameter` | Tạo/cập nhật parameter |
| `ssm:GetParameter` | Đọc một parameter |
| `ssm:GetParameters` | Đọc nhiều parameters theo tên |
| `ssm:GetParametersByPath` | Đọc parameters dưới một hierarchy path |
| `ssm:DescribeParameters` | Xem metadata/danh sách parameters |
| `ssm:GetParameterHistory` | Đọc version history |
| `ssm:DeleteParameter` / `ssm:DeleteParameters` | Xóa một hoặc nhiều parameters |
| `ssm:AddTagsToResource` / `ssm:RemoveTagsFromResource` | Quản lý tags |

### 8.1. Cấp quyền theo path

Ví dụ một ECS task role chỉ cần đọc cấu hình của Orders API production:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOrdersApiProductionParameters",
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:GetParametersByPath"
      ],
      "Resource": [
        "arn:aws:ssm:ap-southeast-1:111122223333:parameter/shop/prod/orders-api",
        "arn:aws:ssm:ap-southeast-1:111122223333:parameter/shop/prod/orders-api/*"
      ]
    }
  ]
}
```

Policy này minh họa scope theo ARN. Cần kiểm tra resource ARN và action hỗ trợ resource-level permissions trong IAM Service Authorization Reference. Nếu workload cần `SecureString`, còn phải có `kms:Decrypt` trên đúng KMS key.

### 8.2. Cảnh báo quan trọng: GetParametersByPath recursive

AWS Parameter Store authorizes `GetParametersByPath` theo **path được request**, không đánh giá từng parameter được trả về.

Ví dụ:

- Role có quyền gọi `GetParametersByPath` trên `/shop/prod`.
- Request đặt `Recursive=true`.
- Kết quả có thể chứa `/shop/prod/orders-api/database/password` và các descendants khác.
- Một explicit deny trên parameter ARN con cho một số retrieval actions không tự ngăn API path ancestor trả parameter đó.

Đây là một lỗi IAM dễ bị bỏ sót khi thiết kế hierarchy.

Để chặn một parameter con khỏi recursive path retrieval, phải deny `ssm:GetParametersByPath` trên mọi ancestor path có thể bao gồm parameter đó. Ví dụ muốn bảo vệ `/shop/prod/restricted/db-password`, đánh giá deny trên các path `/shop/prod/restricted`, `/shop/prod`, `/shop` và `/` tùy các path mà principal được phép request.

### 8.3. Deny cả các đường đọc khác

Một chính sách bảo vệ parameter nhạy cảm cần xem tất cả retrieval actions:

- `ssm:GetParameter`
- `ssm:GetParameters`
- `ssm:GetParametersByPath`
- `ssm:GetParameterHistory`

Có thể dùng action pattern `ssm:GetParameter*` để deny các đường đọc bắt đầu bằng GetParameter, nhưng phải kiểm tra policy simulator và không vô tình chặn API cần thiết khác. `GetParameterHistory` có thể trả current version; không để history permission trở thành đường vòng qua deny GetParameter.

Tương tự, xóa một parameter có hai API authorization độc lập: `ssm:DeleteParameter` và `ssm:DeleteParameters`. Nếu cần ngăn xóa, deny cả hai hoặc dùng pattern `ssm:DeleteParameter*` trên resource scope phù hợp.

### 8.4. Ví dụ explicit deny cho path nhạy cảm

Mẫu dưới đây minh họa deny recursive retrieval cho ancestor paths. ARN/resource path phải khớp chính xác request path trong môi trường thực tế:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyRecursiveReadOfRestrictedPaths",
      "Effect": "Deny",
      "Action": "ssm:GetParametersByPath",
      "Resource": [
        "arn:aws:ssm:ap-southeast-1:111122223333:parameter/*",
        "arn:aws:ssm:ap-southeast-1:111122223333:parameter/shop",
        "arn:aws:ssm:ap-southeast-1:111122223333:parameter/shop/prod",
        "arn:aws:ssm:ap-southeast-1:111122223333:parameter/shop/prod/restricted"
      ]
    },
    {
      "Sid": "DenyOtherReadPathsForRestrictedParameter",
      "Effect": "Deny",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:GetParameterHistory"
      ],
      "Resource": "arn:aws:ssm:ap-southeast-1:111122223333:parameter/shop/prod/restricted/db-password"
    }
  ]
}
```

Đây là ví dụ cần kiểm thử và điều chỉnh theo path access thực tế; không copy nguyên xi vào production. Dùng IAM Policy Simulator và test từng API với principal bị giới hạn.

### 8.5. Kiểm thử quyền theo từng retrieval API

Với một principal được cho phép đọc `/shop/prod/orders-api` nhưng bị cấm đọc `/shop/prod/restricted`, hãy kiểm thử:

1. `GetParameter` cho một parameter được phép.
2. `GetParameters` với cả tên được phép và bị cấm.
3. `GetParameterHistory` cho parameter bị cấm.
4. `GetParametersByPath` với `Recursive=false`.
5. `GetParametersByPath` với `Recursive=true` ở từng ancestor path.
6. `WithDecryption=true` cho SecureString.
7. `DescribeParameters` để xác định metadata nào còn nhìn thấy.

Không chỉ kiểm tra một lệnh Console. API, CLI và SDK dùng chung IAM authorization model.

## 9. SecureString và AWS KMS

### 9.1. Cách mã hóa hoạt động

SecureString dùng AWS KMS để mã hóa value. Parameter Store không tự thực hiện thuật toán mã hóa; nó gọi KMS với encryption context gắn parameter ARN.
Parameter Store chỉ hỗ trợ symmetric KMS keys cho SecureString; asymmetric keys không dùng được cho loại parameter này.

- Với Standard SecureString, Parameter Store dùng KMS Encrypt.
- Với Advanced SecureString, Parameter Store dùng envelope encryption và KMS GenerateDataKey.
- Khi đọc có WithDecryption, Parameter Store gọi KMS Decrypt.
- Plaintext được truyền qua TLS trong quá trình request/response.

Encryption context gồm key `PARAMETER_ARN` và value là ARN của parameter. Context này giúp ràng buộc ciphertext với parameter cụ thể và hỗ trợ audit/control trong KMS policies.

### 9.2. Quyền KMS cần thiết

| Hành động | KMS permission thường cần |
|---|---|
| Tạo/cập nhật Standard SecureString | `kms:Encrypt` |
| Tạo/cập nhật Advanced SecureString | `kms:GenerateDataKey` |
| Đọc SecureString có giải mã | `kms:Decrypt` |

Principal cần quyền SSM tương ứng và quyền KMS. IAM policy và KMS key policy phải cùng cho phép thao tác; explicit Deny ở bất kỳ lớp nào sẽ chặn.

### 9.3. AWS managed key hay customer managed key?

Parameter Store có AWS managed key mặc định với alias `aws/ssm`.

Hạn chế quan trọng: AWS managed key `aws/ssm` cho phép IAM principals trong account có thể dùng quyền retrieval phù hợp giải mã SecureString. Không thể thiết kế fine-grained key policy cho AWS managed key đó theo nhu cầu riêng.

Nếu cần phân tách quyền giải mã giữa teams/applications, dùng customer managed KMS key:

- Một key cho production database parameters.
- Một key riêng cho payment credentials.
- Key administrators tách khỏi application operators.
- Task role chỉ có decrypt trên key cần thiết.
- Key policy hạn chế principal và có thể dùng encryption context condition.
- Review grants, key rotation và lifecycle.

### 9.4. Giới hạn quyền decrypt bằng encryption context

Ví dụ policy KMS có thể giới hạn decrypt vào parameter ARN thuộc path ứng dụng:

```json
{
  "Effect": "Allow",
  "Action": "kms:Decrypt",
  "Resource": "arn:aws:kms:ap-southeast-1:111122223333:key/EXAMPLE-KEY-ID",
  "Condition": {
    "StringLike": {
      "kms:EncryptionContext:PARAMETER_ARN": "arn:aws:ssm:ap-southeast-1:111122223333:parameter/shop/prod/orders-api/*"
    }
  }
}
```

Đây là ví dụ điều kiện; cần xác nhận key policy, IAM policy và encryption context thực tế. Không cấp decrypt toàn account nếu workload chỉ cần một nhóm parameters.

### 9.5. Metadata vẫn có thể lộ

SecureString chỉ mã hóa **parameter value**. Name, description, tags và một số metadata không được mã hóa. Vì vậy:

- Không đưa secret value vào name/description/tags.
- Hạn chế DescribeParameters/List access khi metadata cũng nhạy cảm.
- Không in parameter value vào application logs.
- Không expose decrypted response qua metrics, traces hoặc error messages.
- Dùng Secrets Manager nếu cần rotation workflow chuyên dụng.

## 10. Parameter policies: expiration và notification

Parameter policies chỉ có ở Advanced tier. Chúng cho phép gắn policy vào parameter để tự động thực hiện một số hành động theo thời gian.

Các loại policy chính:

| Policy | Hành vi |
|---|---|
| `Expiration` | Xóa parameter tại timestamp đã cấu hình |
| `ExpirationNotification` | Phát notification trước khi parameter hết hạn |
| `NoChangeNotification` | Phát notification nếu parameter không được cập nhật trong khoảng thời gian chỉ định |

Parameter Store enforce policies bằng các lần scan bất đồng bộ/định kỳ. Không coi expiration như scheduler chính xác tới từng giây.

### 10.1. Ví dụ kết hợp policies

Ví dụ parameter tạm thời cần xóa vào cuối năm, thông báo trước 7 ngày và cảnh báo nếu không thay đổi trong 90 ngày:

```json
[
  {
    "Type": "Expiration",
    "Version": "1.0",
    "Attributes": {
      "Timestamp": "2026-12-31T00:00:00.000Z"
    }
  },
  {
    "Type": "ExpirationNotification",
    "Version": "1.0",
    "Attributes": {
      "Before": "7",
      "Unit": "Days"
    }
  },
  {
    "Type": "NoChangeNotification",
    "Version": "1.0",
    "Attributes": {
      "After": "90",
      "Unit": "Days"
    }
  }
]
```

### 10.2. Gắn policy khi tạo parameter

```bash
aws ssm put-parameter --region ap-southeast-1 --name "/shop/prod/temporary/partner-endpoint" --type String --tier Advanced --value "https://partner.example.internal" --policies '[{"Type":"Expiration","Version":"1.0","Attributes":{"Timestamp":"2026-12-31T00:00:00.000Z"}},{"Type":"ExpirationNotification","Version":"1.0","Attributes":{"Before":"7","Unit":"Days"}},{"Type":"NoChangeNotification","Version":"1.0","Attributes":{"After":"90","Unit":"Days"}}]'
```

### 10.3. Cẩn thận khi cập nhật policies

Khi cập nhật parameter policies, danh sách policies mới thay thế danh sách hiện tại. Nếu muốn thêm một policy, phải gửi lại các policies cũ cùng policy mới; nếu chỉ gửi policy mới, các policy trước có thể bị loại bỏ.

### 10.4. Expiration không thay secret rotation

Expiration xóa parameter; nó không tự tạo secret mới hoặc cập nhật consumer. Với password/API credentials cần rotation, dùng Secrets Manager rotation hoặc workflow được thiết kế riêng.

ExpirationNotification/NoChangeNotification có thể phát sự kiện để automation gửi thông báo hoặc mở ticket. Cần cấu hình EventBridge target/permissions nếu muốn xử lý tự động.

## 11. Chia sẻ parameters giữa AWS accounts bằng AWS RAM

Parameter Store hỗ trợ chia sẻ **Advanced parameters** qua AWS Resource Access Manager (RAM). Đây là cách quản lý cấu hình dùng chung cho nhiều accounts mà không phải sao chép thủ công mỗi lần cập nhật.

### 11.1. Điều kiện chia sẻ

- Parameter phải thuộc Advanced tier.
- Account chia sẻ phải là owner của parameter; không thể chia sẻ tiếp một parameter đã được chia sẻ cho mình.
- Consumer accounts có quyền read-only theo RAM managed permission set.
- Consumer không thể update/delete parameter gốc hoặc chia sẻ tiếp cho account thứ ba.
- Có thể chia sẻ với account cụ thể, OU hoặc toàn Organization nếu AWS Organizations sharing được bật.

### 11.2. Chia sẻ SecureString

Nếu chia sẻ SecureString:

- Parameter phải dùng customer managed KMS key.
- AWS managed key `aws/ssm` không thể được chia sẻ cross-account.
- KMS key phải được chia sẻ/cấp quyền riêng cho consumer account.
- IAM permissions và KMS key policy ở cả hai phía phải cho phép đọc/giải mã.
- Không chia sẻ rộng một KMS key nếu chỉ cần một vài parameters.

### 11.3. Consumer đọc parameter

Consumer phải dùng full parameter ARN để truy xuất parameter từ account khác:

```bash
aws ssm get-parameter --region ap-southeast-1 --name "arn:aws:ssm:ap-southeast-1:111122223333:parameter/shared/prod/network/private-subnet-ids"
```

Consumer có thể dùng các quyền read-only do RAM managed permission set cấp. Có permission set cho phép đọc history; chỉ chọn khi consumer thực sự cần.

### 11.4. Khi nào không nên share?

- Mỗi environment cần cấu hình độc lập.
- Parameter chứa credential cần rotation/lifecycle riêng.
- Consumer không cần cùng một nguồn cấu hình.
- Cross-account trust chưa được review.
- KMS key ownership/rotation chưa được thống nhất.

Không dùng parameter sharing như cách né tránh thiết kế account boundary. Chia sẻ phải có owner, consumer list, purpose, KMS policy, review date và quy trình revoke.

## 12. Throughput và throttling

Parameter tier và throughput là hai cấu hình độc lập:

- **Tier** quyết định số lượng, kích thước và feature của parameter.
- **Throughput** quyết định số API transactions mỗi giây mà account/Region có thể xử lý.

### 12.1. Default throughput

Theo quota Parameter Store hiện hành, các API retrieval `GetParameter`, `GetParameters` và `GetParametersByPath` dùng chung quota mặc định 40 transactions/second cho một account/Region. Một API call có thể trả nhiều parameters; billing interaction và TPS transaction là hai khái niệm khác nhau.

Một số API khác có quota riêng, ví dụ PutParameter, DescribeParameters, DeleteParameter và GetParameterHistory.

### 12.2. Higher throughput

Có thể bật higher throughput theo account/Region. Các quota công bố hiện tại cho nhóm retrieval cao hơn, ví dụ:

| API | Default | Higher throughput |
|---|---:|---:|
| GetParameter | Chia sẻ 40 TPS | 10.000 TPS |
| GetParameters | Chia sẻ 40 TPS | 1.000 TPS |
| GetParametersByPath | Chia sẻ 40 TPS | 500 TPS |

Đây là quota tham khảo theo tài liệu hiện hành; kiểm tra Service Quotas/Systems Manager endpoints and quotas của Region trước khi dựa vào chúng. Higher throughput phát sinh thêm phí theo Parameter Store API interactions.

### 12.3. Ví dụ throttling khi scale-out

Một ECS service thường chạy 5 tasks. Mỗi task đọc 12 parameters lúc startup. Khi deployment thay task và autoscaling tăng 50 tasks trong thời gian ngắn, các task mới có thể đồng thời gọi GetParametersByPath. Request burst có thể vượt quota mặc định.

Biểu hiện thường gặp:

- SDK trả `ThrottlingException` hoặc `RateExceeded`.
- Task startup chậm hoặc health check fail.
- Retry làm tăng latency và tiếp tục tạo thêm request.
- Deployment kéo dài dù application code không có lỗi.

### 12.4. Cách giảm throttling

1. Cache parameter values trong process thay vì đọc mỗi HTTP request.
2. Dùng GetParameters/GetParametersByPath để batch các values cần thiết.
3. Phân tán startup/reload calls bằng jitter.
4. Dùng exponential backoff có giới hạn và retry budget.
5. Không gọi DescribeParameters liên tục để discovery.
6. Bật higher throughput nếu workload thực sự cần và đã tính phí.
7. Giới hạn số parameters đọc ở startup; không tải cả root hierarchy.
8. Theo dõi CloudWatch metrics/SDK errors và application latency.

Parameter Store không nên là dependency bị gọi đồng bộ trên mọi request người dùng. Đọc cấu hình ở startup hoặc refresh theo chu kỳ hợp lý thường giảm latency và API usage.

### 12.5. Chi phí higher throughput

Phí higher throughput được tính theo API interactions; một API call trả về nhiều parameters có thể tính nhiều interactions. Tính usage dự kiến theo số parameters trả về, số workloads, refresh cadence và account/Region trước khi bật.

Không nhầm phí Advanced parameter storage với phí higher throughput. Chúng độc lập và có thể cùng phát sinh.

## 13. Đọc parameters theo API và CLI

### 13.1. Đọc một parameter

```bash
aws ssm get-parameter --region ap-southeast-1 --name "/shop/prod/orders-api/logging/level"
```

Với SecureString, thêm `--with-decryption` khi principal có quyền KMS Decrypt.

### 13.2. Đọc nhiều parameters theo tên

```bash
aws ssm get-parameters --region ap-southeast-1 --names "/shop/prod/orders-api/logging/level" "/shop/prod/orders-api/http/read-timeout-ms"
```

API có giới hạn số names trong một request. Với tập lớn, batch theo giới hạn API và xử lý `InvalidParameters` nếu một số tên không tồn tại hoặc không truy cập được.

### 13.3. Đọc theo hierarchy path

```bash
aws ssm get-parameters-by-path --region ap-southeast-1 --path "/shop/prod/orders-api" --recursive --with-decryption
```

- `--path` là path gốc.
- `--recursive` đọc mọi cấp con.
- `--with-decryption` giải mã SecureString nếu IAM/KMS cho phép.
- API phân trang; CLI tự xử lý pagination mặc định nhưng script SDK phải xử lý `NextToken`.
- Không dùng root path `/` cho workload application trừ khi thực sự cần.

Đọc theo path có thể trả nhiều values hơn dự kiến. Kết hợp path design, IAM policies và kiểm thử recursive access.

### 13.4. Xem metadata và version history

```bash
aws ssm describe-parameters --region ap-southeast-1 --parameter-filters "Key=Path,Option=Recursive,Values=/shop/prod/orders-api"
```

```bash
aws ssm get-parameter-history --region ap-southeast-1 --name "/shop/prod/orders-api/logging/level"
```

DescribeParameters trả metadata, không phải API phù hợp để lấy toàn bộ values. History access cần được kiểm soát vì nó có thể expose current và previous versions.

### 13.5. Pagination và giới hạn API

Khi dùng SDK:

- Xử lý NextToken cho GetParametersByPath.
- Không giả định một response chứa toàn bộ hierarchy.
- Kiểm tra InvalidParameters.
- Batch theo API quotas.
- Có timeout và retry policy rõ ràng.
- Không log plaintext values khi debug.

## 14. Tích hợp Parameter Store với workloads

### 14.1. EC2 instance profile

EC2 instance có thể dùng instance profile role để đọc parameters. Không nhúng access key dài hạn vào user data hoặc file cấu hình.

Ví dụ:

1. EC2 instance khởi động.
2. Instance profile cung cấp temporary credentials.
3. Bootstrap script gọi SSM GetParameter.
4. Ứng dụng nhận cấu hình qua file permission hạn chế hoặc environment được bảo vệ.
5. IAM role chỉ được đọc path cần thiết.

User data thường có thể được truy cập qua instance metadata/control plane theo quyền phù hợp; không đặt secret plaintext vào user data.

### 14.2. ECS task role

Với ECS:

- Task execution role dùng cho ECS agent pull image, gửi logs và lấy secrets được khai báo trong task definition.
- Task role dành cho application code gọi Parameter Store API.
- Task role nên giới hạn `ssm:GetParameter*` vào path service cần đọc.
- Nếu đọc SecureString bằng customer-managed KMS key, thêm `kms:Decrypt` với encryption context phù hợp.
- Không cấp quyền đọc toàn bộ `/shop/prod` cho mọi task.

Nếu inject parameter qua task definition, xác minh đúng cơ chế secret/config injection và behavior refresh. Task/container đã chạy không tự cập nhật environment variable khi parameter thay đổi; thường cần task replacement hoặc application refresh mechanism.

### 14.3. Lambda

Lambda function có thể đọc Parameter Store qua SDK hoặc AWS Parameters and Secrets Lambda Extension khi phù hợp.

- Execution role cần SSM permissions và KMS decrypt nếu cần.
- Extension có cache và TTL; cân nhắc cache invalidation/refresh.
- Không gọi Parameter Store ở mọi invocation nếu có thể cache.
- Cân nhắc cold start, concurrency burst và default throughput.
- Không trả secret values trong function response hoặc log.

### 14.4. Systems Manager Automation và Run Command

Parameters có thể được tham chiếu trong SSM documents/runbooks, giúp automation tái sử dụng cấu hình. Khi document nhận parameter name từ input, kiểm tra người gọi có thể truyền path ngoài scope hay không. Giới hạn IAM role của Automation/managed node theo đúng path.

### 14.5. CloudFormation dynamic references

CloudFormation hỗ trợ dynamic references tới Parameter Store trong một số resource properties:

```yaml
Resources:
  AppLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: /shop/prod/orders-api
      RetentionInDays: "{{resolve:ssm:/shop/prod/logging/retention-days}}"
```

Dynamic reference được resolve trong quá trình stack operation; nó không phải subscription khiến resource tự cập nhật mỗi khi parameter thay đổi. Một số resource/service integrations có giới hạn riêng; kiểm tra CloudFormation dynamic reference support và permissions.

Với SecureString dynamic references, CloudFormation có giới hạn hỗ trợ theo resource/property và cách dùng. Không giả định mọi SecureString có thể được tham chiếu trong mọi resource. Dùng Secrets Manager dynamic references khi use case và resource hỗ trợ, hoặc cấp runtime role để application đọc secret.

### 14.6. Parameter Store trong CodeBuild/CI

Build/deploy roles có thể đọc build configuration từ Parameter Store. Tách:

- Build-time configuration không nhạy cảm.
- Deployment-time configuration.
- Runtime SecureString.
- Credentials cần rotation.

Không đưa SecureString plaintext vào build logs, artifacts hoặc cache. Hạn chế build role đọc production values nếu build chỉ cần compile/test.

## 15. Quản lý cấu hình thay đổi an toàn

### 15.1. Quy trình change

Một quy trình production nên:

1. Xác định parameter, owner, consumer và impact.
2. Review value/schema và change request.
3. Kiểm tra IAM/KMS permissions.
4. Ghi version mới.
5. Validate parameter value ở consumer/staging.
6. Rollout hoặc refresh consumer theo deployment strategy.
7. Monitor error rate/latency và config version.
8. Rollback nếu có regression.
9. Ghi lại operator, timestamp, version và approval.

### 15.2. Không thay đổi schema value tùy tiện

Nếu một parameter đang là JSON mà ứng dụng kỳ vọng field `timeoutMs`, đổi sang cấu trúc khác có thể làm tất cả consumers lỗi cùng lúc. Dùng schema version hoặc parameter name mới khi cần thay đổi contract lớn.

### 15.3. Refresh và cache strategy

| Pattern | Ưu điểm | Trade-off |
|---|---|---|
| Read at startup | Ít API calls, config ổn định trong process | Cần restart/rollout để nhận giá trị mới |
| Periodic refresh | Nhận thay đổi mà không restart | Có độ trễ và API usage |
| Cache with TTL | Giảm latency/API calls | Có thể dùng stale value trong TTL |
| Read every request | Nhận giá trị mới nhanh | Tăng latency, throttling và dependency coupling |

Đặt TTL theo mức độ nhạy cảm của cấu hình. Không cache secrets vô thời hạn nếu rotation/lifecycle yêu cầu refresh.

### 15.4. Parameter Store và AppConfig

Dùng Parameter Store cho key/value configuration có cấu trúc đơn giản. Dùng AppConfig khi cần:

- Validate configuration trước deployment.
- Canary/linear deployment strategy.
- Gradual rollout theo tỷ lệ hoặc target.
- Automatic rollback dựa trên CloudWatch alarms.
- Feature flags và dynamic configuration.
- Application-level polling/agent integration.

Hai dịch vụ có thể kết hợp; không buộc mọi config phải đi qua một service duy nhất.

## 16. Infrastructure as Code cho Parameter Store

### 16.1. Tạo parameter bằng CloudFormation

CloudFormation resource `AWS::SSM::Parameter` phù hợp với cấu hình không nhạy cảm có thể quản lý cùng infrastructure. Ví dụ:

```yaml
Resources:
  OrdersApiLogLevel:
    Type: AWS::SSM::Parameter
    Properties:
      Name: /shop/prod/orders-api/logging/level
      Type: String
      Tier: Standard
      Description: Log level for Orders API
      Value: INFO
      Tags:
        Owner: orders-team
        Environment: prod
        ManagedBy: cloudformation
```

Resource này tạo String/StringList theo schema CloudFormation hỗ trợ; không dùng nó để lưu plaintext secrets hoặc giả định nó tạo SecureString. Quản lý SecureString bằng cơ chế phù hợp như API/CLI/SDK và customer-managed KMS key, hoặc tham chiếu secret theo integration được hỗ trợ.

### 16.2. Dynamic reference tới SecureString

Trong resource properties được CloudFormation hỗ trợ, có thể dùng secure dynamic reference:

```yaml
Resources:
  SomeSupportedResource:
    Type: AWS::SomeService::Resource
    Properties:
      CredentialValue: "{{resolve:ssm-secure:/shop/prod/integration/api-token:3}}"
```

Đây là cú pháp minh họa; thay bằng resource/property thực sự hỗ trợ secure dynamic references. CloudFormation chỉ resolve khi stack operation chạy; thay parameter không tự động cập nhật resource đang tồn tại. Hạn chế sử dụng ở những nơi plaintext có thể xuất hiện trong resource state, outputs hoặc logs.

### 16.3. Drift và ownership

Nếu parameter được quản lý bằng CloudFormation nhưng operator sửa trực tiếp qua Console/CLI, stack có thể bị drift. Cần chọn một source of truth:

- Infrastructure as Code quản lý naming, description, type, tier và non-secret values.
- Secrets Manager/secure workflow quản lý secret values.
- CI/CD pipeline thực hiện changes có approval.
- CloudTrail ghi lại API activity để audit operator.
- Drift detection và periodic reconciliation phát hiện thay đổi ngoài pipeline.

Không để CloudFormation, Terraform, manual console và runtime application cùng ghi một parameter mà không có ownership rõ ràng.

## 17. AWS CLI: tạo, cập nhật và kiểm tra parameters

> Các lệnh bên dưới có cả read-only và mutating operations. Chạy trên account/Region được phép; thay sample paths/values bằng dữ liệu lab. Không dùng secret thật trong command line hoặc shell history.

### 17.1. Tạo Standard String

```bash
aws ssm put-parameter --region ap-southeast-1 --name "/shop/dev/orders-api/logging/level" --type String --tier Standard --value "INFO" --description "Orders API log level"
```

### 17.2. Cập nhật parameter

```bash
aws ssm put-parameter --region ap-southeast-1 --name "/shop/dev/orders-api/logging/level" --type String --value "WARN" --overwrite
```

Kết quả trả version mới. Khi cập nhật, kiểm tra parameter type, tier, policies và consumer compatibility.

### 17.3. Tạo Advanced parameter với policy

```bash
aws ssm put-parameter --region ap-southeast-1 --name "/shop/dev/temporary/test-endpoint" --type String --tier Advanced --value "https://test.example.internal" --policies '[{"Type":"NoChangeNotification","Version":"1.0","Attributes":{"After":"60","Unit":"Days"}}]'
```

### 17.4. Đọc một SecureString

```bash
aws ssm get-parameter --region ap-southeast-1 --name "/shop/prod/orders-api/database/password" --with-decryption
```

Chỉ chạy với role được cấp quyền đọc và decrypt. Không paste output plaintext vào ticket/chat/log.

### 17.5. Đọc path với phân trang

```bash
aws ssm get-parameters-by-path --region ap-southeast-1 --path "/shop/dev/orders-api" --recursive --with-decryption --max-results 10
```

CLI có thể tự paginate; khi viết script SDK, lặp NextToken đến khi hết kết quả. Giới hạn path để không tải nhầm cấu hình/secret của service khác.

### 17.6. Xem history

```bash
aws ssm get-parameter-history --region ap-southeast-1 --name "/shop/dev/orders-api/logging/level"
```

Không cấp history permission chỉ vì tiện debug; history có thể làm lộ current/previous values.

### 17.7. Xóa parameter

```bash
aws ssm delete-parameter --region ap-southeast-1 --name "/shop/dev/temporary/test-endpoint"
```

DeleteParameter là mutating operation. Xóa parameter có thể làm consumer lỗi khi đọc; xác minh dependency và approval trước khi chạy. Với nhiều parameters, DeleteParameters có API semantics/authorization riêng.

### 17.8. Kiểm tra higher throughput setting

```bash
aws ssm get-service-setting --region ap-southeast-1 --setting-id "arn:aws:ssm:ap-southeast-1:111122223333:servicesetting/ssm/parameter-store/high-throughput-enabled"
```

Đây là lệnh read-only để xem setting. Việc bật higher throughput qua UpdateServiceSetting làm thay đổi billing và throughput behavior; chỉ thực hiện sau capacity/cost review.

## 18. Troubleshooting Parameter Store

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| AccessDenied khi GetParameter | Thiếu ssm:GetParameter hoặc resource ARN sai | IAM policy, Region/account, parameter ARN |
| SecureString không decrypt được | Thiếu kms:Decrypt hoặc KMS key policy deny | Key policy, grants, encryption context |
| GetParametersByPath trả quá nhiều values | Path quá rộng và Recursive=true | Thu hẹp path, kiểm tra ancestor path IAM |
| Explicit deny parameter con nhưng vẫn thấy qua path | Authorization dựa trên request path, không từng returned parameter | Deny GetParametersByPath trên ancestor paths |
| GetParameterHistory đọc được value bị deny | History API là retrieval path riêng | Deny ssm:GetParameterHistory và kiểm tra KMS decrypt |
| ParameterNotFound | Sai Region/path/name hoặc parameter đã hết hạn/xóa | Region, full name, history/CloudTrail |
| Parameter tier vượt quota | Đã đạt Standard/Advanced quota | DescribeParameters, quotas và tier strategy |
| Parameter value quá lớn | Vượt 4 KB Standard hoặc 8 KB Advanced | Chuyển Advanced nếu phù hợp hoặc dùng S3/AppConfig |
| Parameter policies không chạy | Parameter không phải Advanced hoặc policy JSON sai | Tier, policy schema, async scan/event delivery |
| ExpirationNotification không thấy | EventBridge/notification target chưa cấu hình hoặc scan chưa tới | EventBridge rule, target permissions, policy attributes |
| PutParameter throttled | Quota ghi mặc định bị vượt | Backoff, reduce writes, higher throughput |
| GetParameter throttled lúc scale-out | Burst đọc đồng thời | Cache, batch, jitter, higher throughput |
| RAM consumer không đọc được | Chưa share/accept hoặc thiếu KMS permission | RAM resource share, full ARN, key policy |
| Shared SecureString không decrypt | AWS managed key hoặc CMK chưa share | Dùng customer managed key và share riêng qua KMS |
| App dùng config cũ | Cache/environment variable không refresh | TTL, reload mechanism, task/instance restart |
| Parameter thay đổi nhưng CloudFormation resource không đổi | Dynamic reference chỉ resolve khi stack operation | Update stack/rollout resource theo quy trình |
| AMI ID chưa hợp lệ ngay sau PutParameter | DataType validation bất đồng bộ | Chờ validation và kiểm tra kết quả |
| Parameter name/metadata bị lộ | Name/description/tags không mã hóa | Giảm metadata nhạy cảm và giới hạn Describe access |

### 18.1. Runbook: task ECS không đọc được production parameter

1. Xác nhận task đang chạy trong đúng account/Region.
2. Xác nhận application dùng task role; không nhầm execution role.
3. Xác định full parameter ARN và path.
4. Kiểm tra IAM `ssm:GetParameter*` resource scope.
5. Nếu dùng `GetParametersByPath`, kiểm tra request path và Recursive flag.
6. Nếu SecureString, kiểm tra KMS key ARN, key state, key policy và `kms:Decrypt`.
7. Nếu KMS condition dùng encryption context, xác nhận `PARAMETER_ARN` khớp.
8. Kiểm tra parameter type/tier và parameter có còn tồn tại không.
9. Kiểm tra throttling/retry và API quotas.
10. Không log plaintext; ghi request ID/error code và xử lý bằng role được phép.

### 18.2. Runbook: cấu hình production bị thay đổi ngoài kế hoạch

1. Lấy CloudTrail event `PutParameter`, `DeleteParameter` hoặc `LabelParameterVersion`.
2. Xác định principal, assumed role, source IP, user agent, account, Region và event time.
3. Lấy parameter history nếu role được phép.
4. Xác định consumers và config refresh/cache behavior.
5. Nếu cần rollback, ghi value đã phê duyệt thành version mới.
6. Kiểm tra IAM policy/tag/role changes liên quan.
7. Ghi change ticket, approval và post-incident evidence.
8. Review quyền `ssm:PutParameter`, `ssm:DeleteParameter*` và pipeline ownership.

## 19. Bài tập tình huống và đáp án

### Bài 1 — Thiết kế hierarchy

Một hệ thống có Orders API và Payment Worker ở dev/staging/prod. Hãy đề xuất hierarchy.

**Đáp án:** Có thể dùng `/shop/<environment>/<application>/<domain>/<setting>`, ví dụ `/shop/prod/orders-api/database/host` và `/shop/prod/payment-worker/queue/url`. Tách account boundaries cho production khi yêu cầu bảo mật cần.

### Bài 2 — Chọn parameter type

Một endpoint công khai và một database password cần lưu trong Parameter Store. Chọn type nào?

**Đáp án:** Endpoint dùng String; database password dùng SecureString với customer-managed KMS key nếu cần phân quyền decrypt chi tiết. Nếu cần rotation tự động, đánh giá Secrets Manager.

### Bài 3 — Standard hay Advanced?

Một parameter value 6 KB và cần expiration policy. Chọn tier nào?

**Đáp án:** Advanced vì Standard giới hạn 4 KB và không hỗ trợ parameter policies; Advanced hỗ trợ value tối đa 8 KB.

### Bài 4 — Downgrade tier

Parameter đã được nâng lên Advanced, sau đó value giảm còn 1 KB. Có thể downgrade về Standard không?

**Đáp án:** Không. Advanced không downgrade được. Nếu cần Standard, tạo parameter mới, migrate consumer và retire parameter cũ theo change process.

### Bài 5 — GetParametersByPath security

Role bị deny `/shop/prod/restricted/password` nhưng được phép recursive read `/shop/prod`. Có thể vẫn đọc password không?

**Đáp án:** Có. GetParametersByPath authorization dựa trên path request. Cần deny action này trên ancestor paths có thể chứa parameter restricted, và kiểm thử bằng IAM simulator/API.

### Bài 6 — GetParameterHistory

Một role bị deny GetParameter nhưng có GetParameterHistory. Có rủi ro gì?

**Đáp án:** GetParameterHistory có thể trả current parameter version, bao gồm SecureString nếu có quyền decrypt. Cần kiểm soát history API và KMS decrypt.

### Bài 7 — SecureString và KMS

Ứng dụng có ssm:GetParameter nhưng nhận AccessDenied khi đọc SecureString với decryption. Kiểm tra gì?

**Đáp án:** KMS Decrypt permission, KMS key policy/grants, key state và encryption context. SSM read permission không tự cấp quyền decrypt.

### Bài 8 — AWS managed key

Hai teams trong cùng account cần quyền decrypt SecureString khác nhau. Dùng default aws/ssm key có phù hợp không?

**Đáp án:** Không phù hợp cho fine-grained separation vì AWS managed key cho IAM principals trong account quyền decrypt rộng theo behavior mặc định. Dùng customer-managed KMS keys với key policy và encryption context.

### Bài 9 — Parameter policy

Một temporary endpoint cần xóa sau 30 ngày và thông báo trước 5 ngày. Cần tier/policy nào?

**Đáp án:** Advanced tier với Expiration và ExpirationNotification. Policy enforcement bất đồng bộ; không dùng nó làm timer chính xác hoặc secret rotation.

### Bài 10 — Policy overwrite

Parameter có Expiration và NoChangeNotification. Operator cập nhật chỉ gửi một ExpirationNotification policy. Rủi ro?

**Đáp án:** Danh sách policy mới có thể thay thế policies hiện tại. Phải gửi lại tất cả policies muốn giữ cùng policy mới.

### Bài 11 — Shared parameter

Account A muốn share SecureString với Account B. Điều kiện quan trọng?

**Đáp án:** Advanced parameter, customer-managed KMS key và chia sẻ KMS key riêng qua KMS. Dùng AWS RAM; consumer đọc bằng full parameter ARN và read-only.

### Bài 12 — Throttling

50 ECS tasks cùng khởi động và đọc 10 parameters mỗi task. Có nguy cơ gì?

**Đáp án:** Burst retrieval có thể vượt default 40 TPS shared quota. Dùng cache, batch, jitter, retry budget hoặc higher throughput sau khi tính phí.

### Bài 13 — App vẫn dùng giá trị cũ

Parameter đã cập nhật nhưng ECS task vẫn dùng value trước đó. Tại sao?

**Đáp án:** Task đã chạy có thể cache value hoặc environment variable lúc startup. Cần application refresh/TTL hoặc replace tasks; Parameter Store không push update tới process.

### Bài 14 — CloudFormation dynamic reference

Parameter được dùng trong CloudFormation dynamic reference. Khi parameter đổi, resource có tự cập nhật không?

**Đáp án:** Không. Reference được resolve trong stack operation. Cần update stack/resource hoặc rollout theo quy trình.

### Bài 15 — DataType AMI

PutParameter với `aws:ec2:image` trả thành công nhưng AMI chưa thể sử dụng ngay. Tại sao?

**Đáp án:** Validation data type diễn ra bất đồng bộ. Cần kiểm tra trạng thái/kết quả validation trước khi dùng value.

### Bài 16 — Xóa parameter

Một parameter có nhiều consumers. Operator muốn DeleteParameter để dọn cấu hình cũ. Cần làm gì?

**Đáp án:** Xác định consumers, logs/CloudTrail, deployment references, IAM roles và approval; migrate consumers trước rồi mới xóa. DeleteParameter có thể làm runtime lỗi ngay khi consumer cần đọc.

### Bài 17 — Version labels

Release pipeline dùng label stable trỏ vào version 4. Một pipeline khác di chuyển label sang version 5. Rủi ro?

**Đáp án:** Label có thể được di chuyển giữa versions; không phải immutable pointer. Cần một owner/lock/change control cho labels và ghi release metadata.

### Bài 18 — Secret rotation

Database password cần tự động rotate mỗi 30 ngày và ứng dụng phải nhận credential mới. Parameter Store có phải lựa chọn mặc định?

**Đáp án:** Không. AWS Secrets Manager phù hợp hơn cho credentials cần automatic rotation. Nếu dùng Parameter Store, phải tự thiết kế rotation, consumer refresh, rollback và audit workflow.

### Bài 19 — IAM history path

Một developer chỉ cần đọc log level nhưng được cấp `ssm:GetParameter*` trên `/shop/prod/*`. Có vấn đề gì?

**Đáp án:** Wildcard quá rộng, bao gồm nhiều retrieval APIs và có thể đọc cả parameter history/path khác. Thu hẹp resource ARN tới path cụ thể và cấp đúng actions.

### Bài 20 — Config thay đổi theo phần trăm traffic

Một team muốn rollout feature flag cho 5% users, theo dõi alarm và tự rollback. Parameter Store có đủ không?

**Đáp án:** Parameter Store là key/value store; không cung cấp toàn bộ deployment strategy đó. Đánh giá AWS AppConfig cho gradual rollout, validators và alarm-based rollback.

## 20. Checklist production cho Parameter Store

1. **Use case:** dữ liệu là config, secret, feature flag hay file/artifact?
2. **Service choice:** Parameter Store, Secrets Manager, AppConfig hay S3 phù hợp nhất?
3. **Hierarchy:** naming convention, environment/application/domain và depth không vượt 15?
4. **Account/Region:** production isolation, Region coverage và replication strategy?
5. **Type:** String/StringList/SecureString và DataType đúng?
6. **Tier:** Standard/Advanced/Intelligent-Tiering đã chọn theo quota/features/cost?
7. **Size:** value nằm trong giới hạn 4 KB/8 KB tương ứng?
8. **IAM:** Get/Put/Delete/History/Describe actions có least privilege?
9. **Recursive path:** GetParametersByPath ancestor paths đã được kiểm soát?
10. **KMS:** customer-managed key, key policy, encryption context và decrypt roles?
11. **Metadata:** name/description/tags không chứa secrets hoặc PII?
12. **Versioning:** rollback, labels và retention history có quy trình?
13. **Policies:** expiration/no-change notifications đã hiểu async semantics?
14. **Sharing:** AWS RAM principals, consumer permissions và KMS sharing?
15. **Throughput:** default TPS, burst, higher throughput và API interaction cost?
16. **Caching:** startup/TTL/refresh strategy phù hợp?
17. **Workload role:** EC2 instance profile, ECS task role, Lambda execution role?
18. **CloudFormation:** dynamic reference limitations và resource refresh behavior?
19. **CI/CD:** build role không đọc production secrets nếu không cần?
20. **Audit:** CloudTrail events, change approval và owner metadata?
21. **Monitoring:** AccessDenied, throttling, API errors, stale config và expiration events?
22. **Testing:** IAM policy simulator và tests với mọi retrieval APIs?
23. **Recovery:** previous value/version và rollback process đã được diễn tập?
24. **Deletion:** consumer inventory và approval trước DeleteParameter?
25. **Cost:** Advanced storage, higher throughput, KMS và cross-account usage?

**Ghi nhớ cuối bài:** Parameter Store giúp tổ chức cấu hình tập trung theo hierarchy và cấp quyền theo IAM. Thiết kế an toàn phải kết hợp path naming, account boundary, retrieval API controls, KMS encryption, version/policy lifecycle và throughput planning. Đặc biệt, recursive GetParametersByPath và GetParameterHistory là các đường truy xuất cần được kiểm soát riêng. Dùng Secrets Manager cho credentials cần rotation, AppConfig cho rollout cấu hình có kiểm soát, và kiểm thử quyền bằng chính role mà workload sẽ sử dụng.

## Tài liệu AWS chính thức

- [AWS Systems Manager Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html)
- [Parameter Store reference](https://docs.aws.amazon.com/systems-manager/latest/userguide/what-is-a-parameter.html)
- [Working with parameter hierarchies](https://docs.aws.amazon.com/systems-manager/latest/userguide/sysman-paramstore-hierarchies.html)
- [Restricting access to specific parameters and paths](https://docs.aws.amazon.com/systems-manager/latest/userguide/ps-restrict-parameter-access.html)
- [Setting up Parameter Store and IAM permissions](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-setting-up.html)
- [Choosing parameter tiers](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-advanced-parameters.html)
- [Specifying a default parameter tier](https://docs.aws.amazon.com/systems-manager/latest/userguide/ps-default-tier.html)
- [Parameter data types](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-data-types.html)
- [Assigning parameter policies](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-policies.html)
- [Managing Parameter Store throughput](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-throughput.html)
- [Systems Manager endpoints and quotas](https://docs.aws.amazon.com/general/latest/gr/ssm.html)
- [Encrypting SecureString parameters with AWS KMS](https://docs.aws.amazon.com/systems-manager/latest/userguide/secure-string-parameter-kms-encryption.html)
- [Restricting SecureString decryption](https://docs.aws.amazon.com/systems-manager/latest/userguide/ps-restrict-decryption.html)
- [Working with shared parameters](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-shared-parameters.html)
- [Parameter Store data protection](https://docs.aws.amazon.com/systems-manager/latest/userguide/data-protection.html)
- [AWS Systems Manager pricing](https://aws.amazon.com/systems-manager/pricing/)
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)
- [AWS AppConfig](https://docs.aws.amazon.com/appconfig/latest/userguide/what-is-appconfig.html)
- [CloudFormation dynamic references](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references.html)
- [AWS::SSM::Parameter CloudFormation resource](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ssm-parameter.html)
- [AWS Pricing Calculator](https://calculator.aws/)
