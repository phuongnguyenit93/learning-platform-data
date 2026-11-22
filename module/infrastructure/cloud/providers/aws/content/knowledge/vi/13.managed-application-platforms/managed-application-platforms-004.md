# Cấu hình môi trường, secret và kết nối dữ liệu trong Beanstalk

> **Chương:** Nền tảng ứng dụng quản lý  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hệ sinh thái AWS qua Region/AZ, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; rèn khả năng chọn dịch vụ, triển khai an toàn, giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

**AWS Elastic Beanstalk** giúp triển khai và vận hành ứng dụng web trên các tài nguyên AWS được quản lý theo một môi trường thống nhất. Thay vì tự viết toàn bộ quy trình khởi tạo EC2, cấu hình web server, health monitoring và cập nhật ứng dụng, nhóm phát triển có thể cung cấp mã nguồn/container, lựa chọn nền tảng và khai báo cấu hình môi trường. Tuy nhiên, để ứng dụng kết nối an toàn với database, S3 hay dịch vụ nội bộ, vẫn phải hiểu rõ **environment properties**, **secrets**, **IAM roles**, **networking** và **vòng đời tài nguyên dữ liệu**.

Sau bài này, bạn có thể:

1. Giải thích cấu trúc **application – application version – environment – platform**, các tài nguyên AWS đứng sau một Beanstalk environment.
2. Phân biệt **environment configuration**, **environment properties** và **secret-backed environment variables**.
3. Cấu hình ứng dụng bằng Console, EB CLI, AWS CLI, `.ebextensions` và `.platform` theo đúng thứ tự ưu tiên.
4. Thiết kế việc đọc secret từ **AWS Secrets Manager** và **AWS Systems Manager Parameter Store**, cấp IAM tối thiểu và xử lý rotation.
5. Kết nối ứng dụng Beanstalk với **Amazon RDS độc lập**, bảo vệ kết nối qua VPC, subnet và security group; hiểu rủi ro của database gắn vòng đời môi trường.
6. Tách quyền/cấu hình cho môi trường development, staging và production mà không đưa mật khẩu vào source code hoặc logs.
7. Quan sát environment bằng AWS CLI theo cách **chỉ đọc**, xác định lỗi cấu hình, secret, database, health và network.
8. Đề xuất triển khai, rollback, giám sát, sao lưu và kiểm soát chi phí.

## 1. Kiến trúc một Elastic Beanstalk environment

### 1.1. Những khái niệm cơ bản

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| **Application** | Vùng chứa logic cho các phiên bản và môi trường liên quan | `course-platform` |
| **Application version** | Bản build/source bundle hay artefact triển khai | `v1.4.0` |
| **Environment** | Phiên bản ứng dụng đang chạy cùng cấu hình/tài nguyên AWS | `course-staging`, `course-production` |
| **Platform** | Hệ điều hành, runtime, web/proxy/server và cơ chế deployment | Java on Amazon Linux 2023, Node.js, Docker |
| **Environment configuration** | Option settings cho instances, scaling, network, health và app | Instance type, subnets, health path |
| **Environment properties** | Biến khóa–giá trị có thể đọc từ app runtime | `APP_ENV=staging`, `DB_HOST=db.internal` |
| **Environment secrets** | Biến runtime được khởi tạo từ secret/parameter ARN ở store | `DB_PASSWORD` từ Secrets Manager |
| **Service role** | IAM role để Beanstalk quản lý/giám sát các tài nguyên theo quyền cho phép | Role của dịch vụ |
| **EC2 instance profile** | IAM role mà EC2 instances của environment sử dụng | Quyền tải source, đọc secret, gọi S3 |

Một Beanstalk environment không phải là một “máy chủ ảo Beanstalk” duy nhất. Với mô hình **load-balanced environment** thông thường, AWS có thể quản lý các thành phần như load balancer, Auto Scaling group, EC2 instances, security groups và CloudWatch theo cấu hình, cùng những tài nguyên mà nhóm triển khai cho phép.

~~~mermaid
flowchart TD
    DEV[Developer / CI-CD] --> EB[Elastic Beanstalk Application]
    EB --> VER[Application Version]
    VER --> ENV[Environment: staging / production]
    ENV --> ALB[Load Balancer theo cấu hình]
    ENV --> ASG[Auto Scaling Group]
    ASG --> A[EC2 App instance AZ A]
    ASG --> B[EC2 App instance AZ B]
    ALB --> A
    ALB --> B
    A --> DB[(Amazon RDS external)]
    B --> DB
    A --> S3[(S3)]
    B --> S3
    A --> SEC[Secrets Manager / SSM]
    B --> SEC
    IAM[IAM roles + instance profile] -. Bảo vệ .-> A
    IAM -. Bảo vệ .-> B
    NET[VPC subnets + security groups] -. Giới hạn mạng .-> DB
~~~

Sơ đồ thể hiện **kiến trúc tham khảo**, không phải mọi environment đều tạo đủ các tài nguyên trên. **Single-instance environment** có kiến trúc khác; Beanstalk Standard, Beanstalk Cluster và từng runtime/platform cũng khác về cấu hình hỗ trợ. Bài này tập trung vào **Beanstalk Standard environment trên EC2**, đặc biệt ứng dụng web Java/Spring Boot; cần tra tài liệu tương ứng nếu dùng Beanstalk Cluster hoặc loại platform khác.

### 1.2. AWS quản lý gì, nhóm ứng dụng vẫn phải quản lý gì?

| AWS Elastic Beanstalk hỗ trợ | Nhóm ứng dụng vẫn chịu trách nhiệm |
|---|---|
| Điều phối việc tạo/cập nhật nhiều tài nguyên AWS theo environment configuration | Mã nguồn, dependency, chất lượng release, health endpoints |
| Nền tảng runtime và quy trình deployment được hỗ trợ | Cập nhật platform branch, kiểm thử tương thích, tránh deprecated runtime |
| Tích hợp health monitoring/rolling deployments theo cấu hình | Readiness, request draining, SLO, khả năng chịu lỗi ứng dụng |
| Tích hợp EC2, Auto Scaling, ALB, CloudWatch | IAM least privilege, security groups, VPC routes và database permissions |
| Quản lý cấu hình environment và application versions | Secret lifecycle, rotation, backup/restore, policy kiểm soát thay đổi |
| Hỗ trợ triển khai nhiều môi trường | Tách tài khoản/dữ liệu/quyền, kiểm soát chi phí, compliance |

**Managed platform không thay thế IAM, secrets management hoặc database backup.** Beanstalk có thể triển khai một ứng dụng thành công nhưng endpoint vẫn trả lỗi nếu DB security group chặn kết nối hoặc secret đã bị rotation mà các instances chưa làm mới.

### 1.3. Web server environment và worker environment

- **Web server environment:** phục vụ HTTP/HTTPS request, thường kết hợp load balancer và Auto Scaling cho API/web app.
- **Worker environment:** phù hợp xử lý công việc nền qua queue và daemon/worker mechanism theo khả năng Beanstalk; ứng dụng phải xử lý retry, idempotency và lỗi.
- Cả hai đều có **environment configuration**, nhưng không mặc định có cùng listener, health check, request lifecycle hay queue processing mechanism.

**Ví dụ:** API Java xử lý đăng nhập và yêu cầu khóa học nên chạy web environment, còn xử lý email hoặc tạo báo cáo có thể đi qua queue/worker. Không dùng một web instance lưu file tạm làm nơi giữ dữ liệu lâu dài khi Auto Scaling thay instance.

## 2. Cấu hình môi trường: ba nhóm thiết lập cần phân biệt

### 2.1. Environment configuration

Các option settings quyết định tính chất hạ tầng và runtime:

| Nhóm | Thiết lập thường gặp | Ảnh hưởng |
|---|---|---|
| Compute/Auto Scaling | Instance type, min/max instances, purchase options | Capacity, khả năng mở rộng và chi phí |
| Network | VPC, subnet IDs, public/private placement, security groups | Khả năng truy cập app và data stores |
| Load balancer/health | Loại cân bằng tải, listener, health path, health reporting | Routing, khả năng phát hiện lỗi |
| Deployment | Rolling, immutable, traffic splitting hoặc các cơ chế được hỗ trợ | Mức gián đoạn, rollback |
| Runtime | Java platform, JVM flags, environment properties | Cách app khởi chạy và tiêu thụ tài nguyên |
| Observability | Log streaming, retention, enhanced health | Khả năng phát hiện sự cố và chi phí |

Một số cấu hình thay đổi nhẹ, nhưng một số thay đổi có thể **thay thế EC2 instances**, rolling update hoặc ảnh hưởng tải. Đừng coi `update-environment` là thao tác tức thời không gián đoạn.

### 2.2. Environment properties

**Environment properties** là các key/value được Beanstalk cung cấp để ứng dụng đọc ở runtime, thường thông qua biến môi trường.

Ví dụ dành cho dữ liệu **không nhạy cảm**:

~~~text
APP_ENV=staging
LOG_LEVEL=INFO
DB_HOST=course-db.cluster-xxxx.ap-southeast-1.rds.amazonaws.com
DB_PORT=5432
DB_NAME=course
S3_BUCKET=course-content-staging
AWS_REGION=ap-southeast-1
~~~

**Không nên đặt trực tiếp** `DB_PASSWORD`, API token, private key hoặc chuỗi kết nối chứa mật khẩu trong plain-text environment settings, repository, EB CLI history hoặc source bundle. Dù environment properties giúp cấu hình linh hoạt, các giá trị có thể xuất hiện ở hệ thống quản trị, process environment, diagnostic output hoặc logs nếu xử lý không cẩn thận.

### 2.3. Secret-backed environment properties

Beanstalk hỗ trợ lấy dữ liệu từ **AWS Secrets Manager** và **SSM Parameter Store** theo cấu hình platform hiện hành. Trong Beanstalk Standard, hai namespace quan trọng:

~~~text
aws:elasticbeanstalk:application:environment
    -> biến môi trường có Value là văn bản cấu hình.

aws:elasticbeanstalk:application:environmentsecrets
    -> biến môi trường có Value là ARN của secret/parameter;
       Beanstalk lấy giá trị thực khi bootstrap instance.
~~~

Các platform version được phát hành từ **26/03/2025** trở đi hỗ trợ tham chiếu secret vào environment variables theo tài liệu AWS. **Không suy đoán một platform version cũ có cùng khả năng**; phải kiểm tra branch/version được environment dùng.

Một số bản platform phát hành từ **13/01/2026** còn hỗ trợ trích **top-level JSON key** từ Secrets Manager ARN, nhưng chỉ khi platform đáp ứng phiên bản hỗ trợ và theo các giới hạn tài liệu.

## 3. Các cách cấu hình và thứ tự ưu tiên

### 3.1. Console, EB CLI, AWS CLI, file cấu hình

| Phương pháp | Dùng cho | Đặc điểm |
|---|---|---|
| **Elastic Beanstalk Console** | Xem/chỉnh environment, runtime variables, monitoring và update policy | Thân thiện để khám phá; dễ phát sinh thay đổi ngoài Git nếu không có quy trình |
| **EB CLI** | Tạo/chọn environment, deploy, xem status, setenv, config | Thuận tiện cho phát triển/nhóm nhỏ |
| **AWS CLI / API** | Tự động hóa tạo/cập nhật option settings, kiểm tra trạng thái | Phù hợp IaC/CD khi có approval, dễ audit |
| **`.ebextensions/*.config`** | Tùy biến **Beanstalk Standard** cùng source bundle | Khai báo YAML/JSON, gắn với phiên bản ứng dụng |
| **Saved configurations** | Lưu mẫu cấu hình environment | Có thứ tự ưu tiên so với file .ebextensions |
| **`.platform/hooks`** | Script tiền/hậu triển khai trên platform Linux được hỗ trợ | Chạy trong quá trình deployment, cần kiểm soát quyền và lỗi |
| **IaC (CloudFormation/CDK/Terraform...)** | Quản lý hạ tầng và khác biệt giữa môi trường | Giúp review, drift detection và lặp lại có kiểm soát |

**Lưu ý phiên bản:** AWS hiện phân biệt **Beanstalk Standard** và **Beanstalk Cluster**. Cơ chế `.ebextensions` trong tài liệu này áp dụng cho Standard; với Cluster, cách cấu hình và nguồn container image có những khác biệt. Không áp file YAML ví dụ ở đây nguyên xi cho Cluster.

### 3.2. Thứ tự precedence trong Standard environment

Với cùng một option:

~~~text
Cao nhất
  1. Thiết lập trực tiếp trên environment qua API/Console/EB CLI
  2. Saved configuration
  3. .ebextensions configuration files
  4. Giá trị mặc định
Thấp nhất
~~~

Ví dụ source bundle có:

~~~yaml
option_settings:
  aws:elasticbeanstalk:application:environment:
    APP_ENV: development
~~~

nhưng environment được cập nhật trực tiếp bằng `eb setenv APP_ENV=production`. Khi đó giá trị trực tiếp có độ ưu tiên **cao hơn**; việc deploy source bundle vẫn chứa `APP_ENV: development` sẽ không tự làm production biến thành development.

**Hệ quả vận hành:** Git chứa cấu hình chưa chắc phản ánh toàn bộ **effective configuration**. Nếu một option “sửa trong .ebextensions không có tác dụng”, kiểm tra environment-level overrides và saved configs. Việc bỏ override phải thông qua `options-to-remove` hoặc cách tương ứng được AWS hỗ trợ, không chỉ xóa dòng khỏi source file.

### 3.3. Cấu trúc source bundle tham khảo

~~~text
course-api/
├── .ebextensions/
│   ├── 00-app-env.config
│   └── 01-secrets.config
├── .platform/
│   ├── hooks/
│   │   └── predeploy/
│   │       └── 10-verify-config.sh
│   └── confighooks/
│       └── postdeploy/
│           └── 20-check-health.sh
├── src/
│   └── ...
├── Procfile
└── build artifact / source code
~~~

Đây là **cấu trúc minh họa**. Không phải runtime nào cũng yêu cầu `Procfile`; vị trí artefact, build và launch command phụ thuộc platform. Thư mục `.platform` có hỗ trợ theo platform và loại hook; **không chạy hook có quyền root** hoặc thay file hệ thống khi chưa rõ lifecycle.

### 3.4. Ví dụ .ebextensions cho biến không nhạy cảm

Tệp giả định `.ebextensions/00-app-env.config`:

~~~yaml
option_settings:
  aws:elasticbeanstalk:application:environment:
    APP_ENV: "staging"
    LOG_LEVEL: "INFO"
    DB_HOST: "course-db.xxxxxx.ap-southeast-1.rds.amazonaws.com"
    DB_PORT: "5432"
    DB_NAME: "course"
    S3_BUCKET: "course-content-staging"
~~~

Đây là **ví dụ để đưa vào bài học**, không phải file đang được tạo trong repository. Tên endpoint RDS và bucket đều giả định. Không hard-code cấu hình production trong bản dùng chung mọi environment; nên dùng giá trị mặc định hợp lý trong Git và override khác biệt bằng IaC/environment configuration được duyệt.

### 3.5. Platform hooks chạy khi nào?

Trên Linux platform được hỗ trợ:

- `.platform/hooks/prebuild`: trước khi thiết lập/build ứng dụng;
- `.platform/hooks/predeploy`: sau bước chuẩn bị, trước khi triển khai ứng dụng đến runtime;
- `.platform/hooks/postdeploy`: sau deployment;
- `.platform/confighooks/...`: chạy trong **configuration deployment** phù hợp khi chỉ đổi settings.

Ví dụ script **không in secret**:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

: "${DB_HOST:?DB_HOST is required}"
: "${DB_PORT:?DB_PORT is required}"
: "${DB_NAME:?DB_NAME is required}"

echo "Required database configuration keys are present."
~~~

**Cảnh báo:** Platform hooks có thể chạy dưới quyền cao, đặc biệt trên Linux. Không bật `set -x` trong hook khi script có truy cập credentials; không echo environment variables, không đưa secret vào command-line arguments hay ghi chúng ra stdout. Một hook lỗi có thể khiến deployment thất bại; hãy kiểm thử trên sandbox.

## 4. Environment properties trong ứng dụng Java/Spring Boot

### 4.1. Đọc biến môi trường mà không gắn với máy cụ thể

Ứng dụng Java có thể dùng `System.getenv("APP_ENV")` hoặc cơ chế externalized configuration của Spring Boot. Ví dụ `application.properties`:

~~~properties
spring.application.name=course-api
server.port=5000

app.environment=${APP_ENV:development}
logging.level.root=${LOG_LEVEL:INFO}

spring.datasource.url=jdbc:postgresql://${DB_HOST}:${DB_PORT:5432}/${DB_NAME}
spring.datasource.username=${DB_USER}
spring.datasource.password=${DB_PASSWORD}
~~~

`DB_USER` và `DB_PASSWORD` chỉ được tham chiếu lúc chạy; **không đặt giá trị mật khẩu trong repository**. `server.port=5000` là ví dụ, không phải cổng cố định cho mọi Beanstalk Java platform. Platform reverse proxy, `PORT` và cơ chế launch có thể khác; cần xác minh application port và health check.

### 4.2. Phân biệt key có thể công khai và key phải bảo vệ

| Key | Ví dụ | Cách quản trị khuyến nghị |
|---|---|---|
| `APP_ENV` | `staging` | Plain environment property/IaC |
| `DB_HOST` | Endpoint nội bộ RDS | Plain environment property nếu chính sách cho phép |
| `DB_PORT` | `5432` | Plain environment property |
| `DB_NAME` | `course` | Plain property hoặc secret tùy sensitivity |
| `DB_USER` | User database | Có thể đặt trong Secrets Manager cùng mật khẩu |
| `DB_PASSWORD` | Mật khẩu | Secret-backed property hoặc runtime API |
| `PAYMENT_API_TOKEN` | Token đối tác | Secrets Manager với rotate/revoke |
| `S3_BUCKET` | Bucket dữ liệu | Plain environment property; IAM role kiểm soát |
| `AWS_ACCESS_KEY_ID` | Static key | **Tránh đặt** trong environment; ưu tiên instance role/STS |

**Đừng xem environment variables là một nơi lưu trữ bí mật tuyệt đối.** Chúng có thể được process, thư viện debug, dump hoặc crash reporting đọc được. Giới hạn quyền OS/IAM, không bật debugging ở production và không in config đầy đủ.

### 4.3. Kiểm tra cấu hình ở startup

Ứng dụng nên **fail fast** nếu thiếu biến quan trọng, nhưng không để lỗi in ra giá trị bí mật:

~~~java
public final class DatabaseSettings {
    public static String require(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing required config: " + key);
        }
        return value;
    }

    private DatabaseSettings() {}
}
~~~

Chỉ log **tên key** bị thiếu, không log `System.getenv()` toàn bộ hay JDBC URL có embedded credentials. Giữ health endpoint chỉ xuất trạng thái, không tiết lộ DB hostname, secret names hoặc stack trace.

## 5. Secrets Manager và SSM Parameter Store

### 5.1. Hai phương án sử dụng secret

**Phương án A — Native environment secrets (Beanstalk bootstrap):**

1. Tạo secret trong AWS Secrets Manager hoặc parameter trong SSM Parameter Store.
2. Cấp IAM cho **EC2 instance profile role** để đọc đúng ARN.
3. Cấu hình `aws:elasticbeanstalk:application:environmentsecrets` với tên biến và ARN.
4. Khi instance bootstrap, Beanstalk lấy giá trị secret/parameter và cung cấp cho runtime environment.
5. Ứng dụng đọc như biến môi trường bình thường.

**Phương án B — Ứng dụng gọi Secrets Manager/SSM API trực tiếp:**

1. Gán instance role quyền tối thiểu để truy xuất secret.
2. Ứng dụng dùng AWS SDK với credential chain mặc định, không nhúng access key.
3. Thiết kế cache, TTL/refresh, retry, timeout và xử lý rotation.
4. Không log secret value; giám sát lỗi API/quota/cost.

| Tiêu chí | Native environment secrets | Gọi SDK trực tiếp |
|---|---|---|
| Code ứng dụng | Thường chỉ cần đọc env var | Cần tích hợp SDK và xử lý API |
| Lấy secret | Khi bootstrap và quy trình refresh môi trường | Khi ứng dụng gọi API |
| Rotation | **Không tự cập nhật** env var của instances đang chạy | Có thể chủ động refresh/caching theo thiết kế |
| IAM | EC2 instance profile phải được phép đọc secret | Runtime IAM role phải được phép đọc |
| Độ phức tạp | Ít code nhưng phải quản trị làm mới env | Nhiều code hơn, kiểm soát cập nhật linh hoạt |
| Khả năng lỗi | Bootstrap có thể lỗi nếu ARN/quyền sai | Runtime có thể lỗi khi Secrets Manager/SSM không truy cập được |
| Chi phí | Secret store/API requests và tài nguyên môi trường | Secret store/API requests, cache/call frequency |

**Không chọn native env vars nếu nghiệp vụ đòi secret thay đổi tức thời mà không có quy trình refresh phù hợp.** Ngược lại, với kết nối DB và rotation có kế hoạch, native environment secrets có thể đơn giản khi đã kiểm soát độ trễ đồng bộ.

### 5.2. Ví dụ namespace environmentsecrets

Tệp giả định `.ebextensions/01-secrets.config`:

~~~yaml
option_settings:
  aws:elasticbeanstalk:application:environmentsecrets:
    DB_USER: "arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:aws-lab/course-db-AbCd12:username"
    DB_PASSWORD: "arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:aws-lab/course-db-AbCd12:password"
    PARTNER_API_TOKEN: "arn:aws:ssm:ap-southeast-1:111122223333:parameter/aws-lab/partner-token"
~~~

**Giải thích cẩn trọng:**

- `DB_USER` và `DB_PASSWORD` trong ví dụ dùng **top-level JSON key extraction** từ Secrets Manager, chỉ có trên **platform versions được phát hành từ 13/01/2026** và hỗ trợ tính năng này. Secret JSON giả định có hai key `username` và `password`.
- `PARTNER_API_TOKEN` tham chiếu ARN parameter SSM và nhận giá trị parameter như một biến. **JSON-key extraction không được hỗ trợ với SSM Parameter Store**.
- Secrets Manager ARN thực có **hậu tố ngẫu nhiên** do dịch vụ tạo; chuỗi ví dụ không phải ARN tồn tại.
- Nếu platform chưa hỗ trợ JSON-key extraction, dùng các secrets chứa riêng từng giá trị, hoặc để ứng dụng đọc JSON thông qua AWS SDK và parse an toàn.
- Các platform cũ hơn thời điểm hỗ trợ environment secrets có thể không nhận namespace này.
- **Chỉ lưu ARN/reference**, không đưa secret value thực vào file `.config`.

AWS Console cũng hỗ trợ chọn **Source = Secrets Manager hoặc SSM Parameter Store** cho runtime variable rồi nhập ARN. Khi cấu hình bằng CLI/API, dùng cùng namespace như trên.

### 5.3. Mô hình IAM tối thiểu để Beanstalk đọc secret

Ví dụ IAM identity policy gắn **EC2 instance profile role** của environment:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOneDatabaseSecret",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:aws-lab/course-db-AbCd12"
    },
    {
      "Sid": "ReadOneSSMParameter",
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter"
      ],
      "Resource": "arn:aws:ssm:ap-southeast-1:111122223333:parameter/aws-lab/partner-token"
    }
  ]
}
~~~

Đây là **policy minh họa**; không tự gán cho một IAM role không thuộc quyền quản lý. Nếu secret/parameter dùng **customer-managed KMS key**, còn có thể cần quyền `kms:Decrypt` tương ứng và **KMS key policy** phải cho phép. Một số hệ thống giới hạn thêm VPC endpoint, principal, encryption context hoặc service conditions; kiểm thử tất cả các điều kiện.

**Phân biệt Service role với Instance profile:** khi Beanstalk tự khởi tạo environment variables từ Secrets Manager/SSM trong Standard environment, **EC2 instance profile role** cần quyền lấy secret/parameter theo tài liệu AWS. Cấp quyền đó vào một role chỉ phục vụ Beanstalk service management mà EC2 không sử dụng sẽ không giải quyết lỗi bootstrap.

### 5.4. Secret rotation: dữ liệu không tự đồng bộ

Đây là điểm vận hành quan trọng nhất.

~~~mermaid
sequenceDiagram
    participant SM as Secrets Manager
    participant EB1 as Beanstalk EC2 instance A
    participant EB2 as Beanstalk EC2 instance B
    participant OPS as Operator / Automation
    SM-->>EB1: Bootstrap ban đầu: password v1
    SM-->>EB2: Bootstrap ban đầu: password v1
    OPS->>SM: Rotate secret sang password v2
    Note over EB1,EB2: Instance đang chạy vẫn có thể giữ v1
    OPS->>EB1: Refresh environment / restart app server
    EB1->>SM: Lấy v2 theo cơ chế Beanstalk
    OPS->>EB2: Refresh environment / restart app server
    EB2->>SM: Lấy v2
    Note over EB1,EB2: Hai instance đã dùng v2 sau khi refresh thành công
~~~

Theo tài liệu AWS, Beanstalk **không tự nhận giá trị mới** trong environment variables khi Secrets Manager/Parameter Store được sửa/rotate. Cần trigger làm mới, chẳng hạn thao tác **UpdateEnvironment** hoặc **RestartAppServer** theo hướng dẫn hiện hành.

**Rủi ro đáng chú ý:** nếu Auto Scaling tạo instance mới sau rotation, instance mới có thể lấy **v2**, trong khi instance cũ còn **v1**. Trong khoảng chuyển tiếp, cùng một environment có **hai giá trị credential**. Với DB password rotation, cần chiến lược cho phép hai credentials hoạt động trong cửa sổ chuyển tiếp hoặc điều phối rotation/refresh an toàn, rồi thu hồi credential cũ sau khi xác nhận toàn bộ instances đã chuyển.

Quy trình rotation gợi ý:

1. Kiểm tra quyền đọc secret, health và phương án rollback.
2. Chuẩn bị cơ chế dual-user/alternating users hoặc mô hình rotation được dịch vụ hỗ trợ để tránh gián đoạn.
3. Rotate/update secret theo workflow được duyệt.
4. Chủ động refresh các Beanstalk instances, giám sát sự khác biệt phiên bản/connection errors.
5. Kiểm tra application health, DB authentication, connection pools và background jobs.
6. Thu hồi quyền/credential cũ sau cửa sổ an toàn.
7. Ghi audit event và cập nhật runbook.

**Không in giá trị cũ/mới để so sánh**, kể cả trong log CI. Có thể đối chiếu secret version metadata hoặc telemetry an toàn được thiết kế riêng.

### 5.5. Không làm lộ secret qua log/CLI/diagnostics

- Không đưa plain password vào `eb setenv DB_PASSWORD=...`, vì shell history và output diagnostics có nguy cơ lộ.
- Hạn chế dùng `eb printenv` hoặc in toàn bộ `describe-configuration-settings` trong CI/chat; chúng có thể tiết lộ environment properties, ARNs và metadata nhạy cảm.
- Không chạy `aws secretsmanager get-secret-value` như một bước kiểm thử và dán kết quả vào issue/chat/log. Khi chỉ cần xác minh secret tồn tại, xem **metadata**, không đọc `SecretString`.
- Không đặt secrets trong `.ebextensions`, `.platform` scripts, `Procfile`, Dockerfile, container image, Git tags hay file backup không mã hóa.
- Cần IAM least privilege, KMS, log retention, access auditing và quy trình xử lý lộ credentials.

## 6. Kết nối Amazon RDS: integrated và external database

### 6.1. Hai mô hình cần phân biệt

Beanstalk hỗ trợ kết hợp với RDS theo hai cách phổ biến:

| Tiêu chí | RDS gắn với Beanstalk environment | RDS độc lập/external |
|---|---|---|
| Mục tiêu | Thực hành, thử nghiệm kết nối dễ hơn | Thường phù hợp production vì vòng đời riêng |
| Tạo tài nguyên | Beanstalk có thể tạo/manage RDS theo cấu hình coupled | Tạo/quản lý RDS độc lập với environment |
| Environment properties | Có thể cung cấp `RDS_HOSTNAME`, `RDS_PORT`, `RDS_DB_NAME`, `RDS_USERNAME`, `RDS_PASSWORD` | **Tự cấu hình** DB endpoint, port, name, credential |
| Vòng đời | Phụ thuộc configuration/deletion policy của environment/coupled DB | Không bị xóa chỉ vì terminate Beanstalk environment |
| Dùng chung giữa blue/green | Khó linh hoạt hơn nếu DB gắn chặt | Có thể dùng cho nhiều environments theo policy và compatibility |
| Rủi ro | Xóa/terminate môi trường có thể ảnh hưởng DB nếu policy không được rà soát | Quản trị backup, network, credential và connection riêng |
| Kiến nghị | Lab/dev hoặc nhu cầu có kiểm soát | Production với backup/DR và ownership riêng |

**Không hiểu “Elastic Beanstalk tự động backup mọi DB”.** RDS có các chính sách snapshot/backup/retention riêng. Khi dùng coupled DB phải kiểm tra **database deletion policy**, tùy chọn retain/snapshot/delete và quy trình decouple. Không xóa environment production nếu chưa xác minh database có bị ảnh hưởng hay không.

### 6.2. RDS coupled: các biến RDS_* được Beanstalk cấp

Trong một cấu hình RDS database gắn environment, Beanstalk có thể cung cấp:

~~~text
RDS_HOSTNAME
RDS_PORT
RDS_DB_NAME
RDS_USERNAME
RDS_PASSWORD
~~~

Đây là các biến phục vụ **mô hình integrated database**; với RDS **external**, đừng chờ Beanstalk tự sinh các biến này.

Một application có thể chuyển từ coupled sang external bằng cách **chuẩn hóa tên biến app dùng**, chẳng hạn `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASSWORD`, sau đó cập nhật environment configuration và secret references. Việc decouple database phải qua quy trình riêng, không chỉ sửa environment property.

### 6.3. RDS external: kiến trúc được khuyến nghị cho production nhiều môi trường

~~~mermaid
flowchart TD
    U[Người dùng] --> LB[ALB của Beanstalk]
    subgraph VPC["Customer VPC"]
      subgraph A["Private app subnet - AZ A"]
        EC2A[Beanstalk app instance A]
      end
      subgraph B["Private app subnet - AZ B"]
        EC2B[Beanstalk app instance B]
      end
      subgraph DBN["Private DB subnets"]
        RDS[(RDS / Aurora Multi-AZ theo nhu cầu)]
      end
    end
    LB --> EC2A
    LB --> EC2B
    EC2A -->|TLS + TCP 5432| RDS
    EC2B -->|TLS + TCP 5432| RDS
    SM[Secrets Manager] -->|Env secrets bootstrap / SDK| EC2A
    SM -->|Env secrets bootstrap / SDK| EC2B
    ROLE[Instance profile IAM] -. Secret access .-> SM
    SG[SG DB: inbound từ SG app] -. Network boundary .-> RDS
~~~

**Quy tắc:** database nằm trong DB subnets phù hợp, thường **không public accessible**; chỉ chấp nhận nguồn từ security group của app trên đúng cổng DB. ALB có security group khác với app instances; đừng dùng SG của ALB làm nguồn inbound DB khi app instances mới là bên mở kết nối.

### 6.4. Kiểm tra routing và security groups

Giả sử PostgreSQL:

~~~text
ALB SG:
  Inbound 443 từ client được phép
  Outbound tới app theo cổng ứng dụng

App SG:
  Inbound từ ALB SG trên cổng backend
  Outbound TCP 5432 tới RDS SG
  Egress tới AWS APIs cần thiết theo VPC routes/endpoints

RDS SG:
  Inbound TCP 5432 từ App SG
  Không mở 0.0.0.0/0 cho PostgreSQL
~~~

Tác động của NACL và route tables cũng cần được xét nếu cấu hình mạng bị giới hạn. App và DB thường cùng VPC, hoặc có peering/Transit Gateway/VPN được quản lý với DNS/routing/SG cho phép. Với private subnet cần gọi Secrets Manager, S3, ECR hay CloudWatch, có thể cần **VPC endpoints hoặc NAT** tùy dịch vụ; không giả định Beanstalk sẽ tự bổ sung mọi đường egress.

### 6.5. Kết nối DB phải xét cả TLS, pooling và timeout

Một ứng dụng Java thường có connection pool (ví dụ HikariCP). Cần:

- **DB endpoint** và DNS đúng Region/VPC.
- **TCP port** và SG/NACL cho phép.
- **TLS** và xác minh chứng chỉ server theo chuẩn RDS/driver, với CA bundle phù hợp.
- Pool size tính theo số EC2 instances tối đa; tránh `(số instances × pool size)` vượt `max_connections` của DB.
- Connection timeout, retry/backoff, failover behavior và transaction boundaries rõ ràng.
- Password rotation phối hợp với connection pool lifecycle, tránh mọi instance cùng mất xác thực.
- Migration schema tương thích blue/green deployments.

**Ví dụ sizing:** environment có 6 EC2 instances, mỗi instance cho pool tối đa 20 connections; riêng nhóm app đã có thể mở đến **120 connections** trước khi tính job nền/DB tooling. Không lấy pool size từ laptop làm tham số production mặc định.

### 6.6. Kết nối dữ liệu khác ngoài RDS

| Dịch vụ | Dùng cho | Cách kết nối an toàn |
|---|---|---|
| **S3** | File, ảnh, backup, báo cáo | AWS SDK + instance role, bucket policy, VPC endpoint nếu phù hợp |
| **DynamoDB** | Key-value/document NoSQL | SDK + least-privilege IAM, endpoint nếu phù hợp |
| **ElastiCache/Redis** | Cache/session/queue tùy thiết kế | VPC private, SG, TLS/auth nếu hỗ trợ |
| **SQS** | Bất đồng bộ, worker jobs | SDK + instance role; retry, DLQ, idempotency |
| **Secrets Manager/SSM** | Secrets và configuration | IAM/KMS + API hoặc native environment secrets |
| **RDS/Aurora** | Dữ liệu quan hệ | VPC SG, private endpoint, TLS, backup |
| **CloudWatch Logs** | Logs/telemetry | IAM, VPC connectivity, retention và phí |

**Beanstalk không biến các dịch vụ dữ liệu thành cùng một vòng đời** chỉ vì chúng được cấu hình qua environment variables. Chủ sở hữu dữ liệu và cơ chế backup phải được quyết định độc lập.

## 7. Thiết kế dev, staging, production và blue/green

### 7.1. Những gì cần tách

| Thành phần | Development | Staging | Production |
|---|---|---|---|
| Application version | Bản đang thử | Release candidate | Bản được duyệt |
| Beanstalk environment | `course-dev` | `course-staging` | `course-prod` |
| Database | Dữ liệu giả lập, nhỏ | Dữ liệu thử nghiệm phù hợp | Dữ liệu thật, backup/retention |
| Secret ARN | `aws-lab/dev/...` | `aws-lab/staging/...` | `aws-lab/prod/...` |
| IAM role | Chỉ tài nguyên dev | Chỉ staging | Chỉ production |
| Network | Sandbox VPC/subnet | Mô phỏng production | Network chặt, nhiều AZ |
| Logging | Đủ để debug, không log secrets | Theo dõi test | Alert/audit, retention tuân thủ |
| Capacity | Ít, có lịch tắt | Đủ cho thử tải | Theo SLO/peak |
| Change approval | Đơn giản | Review theo nhóm | Quy trình duyệt và rollback |

**Không dùng chung master DB password** giữa các environment. Khi môi trường staging có thể truy cập DB production, một lỗi code hoặc smoke test có thể sửa dữ liệu thật. Tách account/VPC/quyền IAM càng rõ càng giảm rủi ro.

### 7.2. Blue/green và dữ liệu

Beanstalk có cơ chế **environment swap URLs** hoặc quy trình đổi hướng lưu lượng, tùy cấu hình. Mô hình blue/green có hai environments độc lập:

~~~mermaid
flowchart LR
    DNS[DNS / Client] --> BLUE[Blue env - current]
    DNS -. Sau cutover .-> GREEN[Green env - candidate]
    BLUE --> DB[(External RDS)]
    GREEN --> DB
    SM[Secrets Manager] --> BLUE
    SM --> GREEN
~~~

Điểm then chốt:

1. Blue/green phải dùng **secret và quyền đã được kiểm tra** cho cả hai môi trường.
2. Hai phiên bản app cùng nhìn database cần schema changes **backward-compatible** (expand-and-contract).
3. Green phải có SG/network access tới DB và AWS APIs, không chỉ ALB healthy.
4. Tình huống rollback app không tự rollback dữ liệu/schema đã bị thay đổi.
5. Đường cắt lưu lượng qua DNS/URL mapping có thể chịu cache TTL, session và connection draining.
6. Môi trường cũ còn chạy sẽ tiếp tục **phát sinh phí** cho tới khi được dọn theo quy trình.

### 7.3. Triển khai an toàn khi thay environment properties

Một thay đổi như `LOG_LEVEL=DEBUG` thường khác mức ảnh hưởng của đổi VPC/subnets/instance type. Theo tài liệu AWS, một số option changes có thể gây environment update hoặc reprovision instances.

Quy trình:

~~~text
1. Đọc effective configuration của đúng environment.
2. Xác định option nào thay đổi và có đụng secret/DB/network không.
3. Review change plan, chi phí và phương án rollback.
4. Áp dụng staging và thực hiện smoke/integration tests.
5. Quan sát health, 5xx, latency, logs, DB connectivity.
6. Triển khai production bằng rolling/immutable/blue-green phù hợp.
7. Kiểm tra lại config/secret refresh ở toàn bộ instances.
8. Giữ rollback window, sau đó dọn version/environment cũ theo policy.
~~~

## 8. Health, logging, giám sát và khôi phục

### 8.1. Health ở nhiều lớp

Beanstalk có thể báo environment health và tích hợp ALB health checks, nhưng trạng thái environment **Green/Ok** không tự chứng minh các API nghiệp vụ đã đúng.

| Tín hiệu | Cho biết | Chưa chứng minh |
|---|---|---|
| **Environment Status=Ready** | Cấu hình/deployment đạt trạng thái quản lý nhất định | DB query/secret refresh của app thành công |
| **Enhanced health Green/Ok** | Các chỉ báo sức khỏe được hệ thống giám sát đánh giá | Không có lỗi nghiệp vụ hiếm |
| **ALB target healthy** | Health endpoint đủ đáp ứng | Toàn bộ routes hoặc database hoạt động |
| **EC2 running** | Instance tồn tại và chạy | Java process đọc được DB secret |
| **/health 200** | Endpoint đạt điều kiện do app định nghĩa | RTO/RPO, data correctness đã đảm bảo |

Để health endpoint có giá trị, ứng dụng nên phân biệt **liveness** (process còn sống) và **readiness** (có thể nhận traffic), tránh probe quá nặng gây áp lực DB. Nếu readiness luôn kiểm tra DB bằng truy vấn tốn kém, khi DB chậm có thể tạo vòng khuếch đại lỗi.

### 8.2. Logging và CloudWatch

Bật theo nhu cầu:

- Environment logs và platform logs, log streaming tới CloudWatch Logs khi hỗ trợ.
- Java logs có structured fields nhưng không chứa PII/credentials.
- ALB metrics: HTTP 4xx/5xx, latency, healthy hosts, request count.
- EC2 metrics: CPU, memory via agent khi cần, EBS/network, Auto Scaling changes.
- DB metrics: CPU, connection count, latency, storage, failover.
- CloudTrail cho thay đổi cấu hình, quyền IAM/Secrets Manager và hoạt động quản trị khi phù hợp.

**Tránh để thông tin mật bị ghi ra log:** toàn bộ HTTP Authorization headers, DB connection URL chứa credentials, `System.getenv()` và secret value phải được redacted hoặc không log. Phí ingest/retention/log query có thể tăng nhanh nếu bật DEBUG dài hạn.

### 8.3. Backup và phục hồi

- RDS backups, snapshots, PITR/Multi-AZ tùy yêu cầu RPO/RTO.
- S3 versioning/lifecycle nếu file ứng dụng quan trọng.
- Source code, application versions và config/IaC lưu trong repository/artifact store có kiểm soát.
- Secrets Manager rotation/version history và quy trình khôi phục/truy cập khẩn cấp.
- Thử khôi phục một environment mới từ cấu hình đã duyệt và **external database** nếu cần DR.

**Không xem Beanstalk application version hoặc environment snapshot là backup dữ liệu DB.** Vòng đời app và vòng đời dữ liệu phải tách khi yêu cầu phục hồi độc lập.

## 9. Chi phí và rủi ro tài nguyên còn tồn tại

### 9.1. Beanstalk tính phí thế nào?

AWS Elastic Beanstalk giúp điều phối tài nguyên, nhưng chi phí chủ yếu đến từ **các tài nguyên AWS sử dụng bên dưới**, chẳng hạn:

| Thành phần | Nguồn chi phí | Cách hạn chế |
|---|---|---|
| EC2 instances | Giờ chạy, instance type, OS/license, public IPv4 | Right-sizing, Auto Scaling, lịch dọn lab |
| Load balancer | ALB/NLB giờ chạy và lưu lượng/LCU/NLCU theo dịch vụ | Dọn môi trường thử không cần thiết |
| EBS | Dung lượng, IOPS, snapshots | Xem root/data volume còn tồn tại |
| RDS/Aurora | Instance/compute, storage, backup, I/O | External DB với lifecycle, backup/retention rõ |
| Networking | NAT Gateway, data transfer, endpoints | Chọn subnets/route và đo egress |
| Secrets Manager/SSM/KMS | Secret, parameter, API requests, key/requests theo biểu giá | Cache hợp lý, tránh polling dày đặc |
| Logs/monitoring | CloudWatch ingestion, retention, custom metrics | Chọn log level và retention |
| DNS/certificate | Route 53 và các thành phần liên quan | Quản lý tài nguyên domain và certificate |

Một environment bị **terminate** không bảo đảm mọi tài nguyên bên ngoài do ứng dụng tạo đã được xóa. Với **RDS external**, DB được thiết kế để **tồn tại độc lập** và tiếp tục phát sinh phí — đây là lợi ích về an toàn dữ liệu, nhưng cũng phải có trách nhiệm quản trị ngân sách.

### 9.2. Tagging và budget

Ví dụ tags:

~~~text
Project=course-platform
Environment=staging
Owner=team-cloud
ManagedBy=iac
CostCenter=training
DeleteAfter=2026-12-01
~~~

Dùng AWS Cost Explorer/Budgets và chính sách tagging/quản trị của tổ chức. **Budget alert không tự ngăn mọi khoản phí**, và không nên coi tag `DeleteAfter` là tác vụ tự xóa nếu không có automation do tổ chức triển khai.

## 10. Thực hành 1 — Đọc cấu hình Beanstalk bằng AWS CLI

> **Mục tiêu:** xác nhận một Beanstalk environment sandbox có thật, đọc metadata, platform, health và phần option settings **không nhạy cảm** mà không thay đổi cấu hình. Không cần tạo environment hoặc RDS để hoàn thành lab cốt lõi. Một số lệnh quản trị có thể trả về biến môi trường chứa secret; **không in toàn bộ configuration hoặc upload kết quả thô** khi chưa kiểm tra.

### 10.1. Xác minh danh tính và Region

Ví dụ Bash/AWS CloudShell:

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

aws sts get-caller-identity --profile "$AWS_PROFILE"
aws elasticbeanstalk describe-applications \
  --region ap-southeast-1 \
  --query 'Applications[].{Name:ApplicationName,Created:DateCreated}' \
  --output table
~~~

Nếu CloudShell có credentials đăng nhập sẵn và không có profile `aws-lab-dev`, bỏ dòng `export AWS_PROFILE=...` và tham số `--profile` tương ứng. Chỉ sử dụng account được cấp phép.

### 10.2. Xem environments và platform

~~~bash
APP=course-api
REGION=ap-southeast-1

aws elasticbeanstalk describe-environments \
  --application-name "$APP" \
  --region "$REGION" \
  --query 'Environments[].{Name:EnvironmentName,ID:EnvironmentId,Status:Status,Health:Health,Version:VersionLabel,Platform:PlatformArn}' \
  --output table
~~~

Nếu application chưa tồn tại, kết quả có thể rỗng; không tự tạo trên production. Đối với platform đang dùng, xem trường `PlatformArn`/`SolutionStackName` và kiểm tra khả năng hỗ trợ environment secrets, runtime và platform updates.

### 10.3. Đọc một số option settings an toàn

Tránh xuất toàn bộ output của `describe-configuration-settings` vì có thể chứa environment properties. Chỉ truy vấn namespace autoscaling:

~~~bash
ENV=course-staging

aws elasticbeanstalk describe-configuration-settings \
  --application-name "$APP" \
  --environment-name "$ENV" \
  --region "$REGION" \
  --query "ConfigurationSettings[].OptionSettings[?Namespace=='aws:autoscaling:asg'].{Option:OptionName,Value:Value}" \
  --output table
~~~

**Không dùng** `--output json` với toàn bộ `OptionSettings` rồi dán lên chat hoặc lưu log pipeline. Nếu cần audit environment secrets, chỉ xem namespace/option names và **không in `Value`**:

~~~bash
aws elasticbeanstalk describe-configuration-settings \
  --application-name "$APP" \
  --environment-name "$ENV" \
  --region "$REGION" \
  --query "ConfigurationSettings[].OptionSettings[?Namespace=='aws:elasticbeanstalk:application:environmentsecrets'].OptionName" \
  --output text
~~~

Ngay cả **tên variable** cũng có thể tiết lộ đặc điểm hệ thống; chỉ chia sẻ trong nhóm có thẩm quyền.

### 10.4. Xem health và recent events

~~~bash
aws elasticbeanstalk describe-environments \
  --application-name "$APP" \
  --environment-names "$ENV" \
  --region "$REGION" \
  --query 'Environments[].{Status:Status,Health:Health,HealthStatus:HealthStatus,URL:CNAME}' \
  --output table

aws elasticbeanstalk describe-events \
  --application-name "$APP" \
  --environment-name "$ENV" \
  --region "$REGION" \
  --max-records 10 \
  --query 'Events[].{Time:EventDate,Level:Severity,Message:Message}' \
  --output table
~~~

**Cảnh báo:** Event messages có thể chứa thông tin cấu hình của ứng dụng (tùy tình huống). Không công khai dữ liệu thô nếu có địa chỉ nội bộ, user identifiers hoặc giá trị nhạy cảm. Khi enhanced health không bật, một số trường có thể không có dữ liệu.

### 10.5. Xem metadata Secret mà không đọc secret value

Nếu có quyền và ARN thuộc sandbox:

~~~bash
SECRET_ARN="arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:aws-lab/course-db-AbCd12"

aws secretsmanager describe-secret \
  --secret-id "$SECRET_ARN" \
  --region "$REGION" \
  --query '{Name:Name,ARN:ARN,RotationEnabled:RotationEnabled,LastChangedDate:LastChangedDate}' \
  --output json
~~~

Lệnh này **không lấy `SecretString`**. Nếu người gọi không có `secretsmanager:DescribeSecret`, lỗi `AccessDenied` có thể là hành vi đúng theo least privilege. Không đòi cấp `GetSecretValue` chỉ để hoàn thành bài xem metadata.

### 10.6. Xem RDS và security groups có liên quan

Nếu được cấp quyền đọc RDS:

~~~bash
DB_ID=course-db-staging

aws rds describe-db-instances \
  --db-instance-identifier "$DB_ID" \
  --region "$REGION" \
  --query 'DBInstances[].{Id:DBInstanceIdentifier,Engine:Engine,Status:DBInstanceStatus,MultiAZ:MultiAZ,PubliclyAccessible:PubliclyAccessible,Port:Endpoint.Port,VpcSGs:VpcSecurityGroups[].VpcSecurityGroupId}' \
  --output json
~~~

Kiểm tra `PubliclyAccessible`, VPC security groups, port và high availability. Kết quả không đảm bảo SG đã cho phép đúng App SG; kiểm tra inbound rule theo quy trình nếu có quyền. **Không mở port DB ra `0.0.0.0/0` để sửa timeout.**

## 11. Thực hành 2 — Ví dụ thay cấu hình có kiểm soát (không bắt buộc chạy)

> Chỉ thực thi khi có **Beanstalk Standard environment sandbox** của chính bạn, quyền thay đổi đã được phê duyệt và kế hoạch rollback. `update-environment` có thể gây restart hoặc rolling replacement; thao tác có thể phát sinh chi phí. Các ID và ARN dưới đây đều là ví dụ, không phải tài nguyên thật.

### 11.1. Cập nhật biến không nhạy cảm bằng EB CLI

Trong thư mục source ứng dụng đã được cấu hình EB CLI, với môi trường sandbox đang được chọn đúng:

~~~bash
# VÍ DỤ CÓ TÁC ĐỘNG - KHÔNG CHẠY TRÊN PRODUCTION
eb setenv APP_ENV=staging LOG_LEVEL=INFO
~~~

**Không dùng `eb setenv DB_PASSWORD=...`** để giải quyết secret management. Tham số lệnh và biến môi trường có thể bị log hoặc lưu trong lịch sử shell.

Kiểm tra environment health, application logs và thử một API smoke test sau khi cập nhật. Nếu cấu hình được quản lý bằng IaC, ưu tiên thay đổi qua pipeline được duyệt thay vì thay trực tiếp rồi phát sinh drift.

### 11.2. Cập nhật ARN secret qua AWS CLI

Một file `secret-options.json` minh họa (chỉ ARN/reference, không chứa secret value):

~~~json
[
  {
    "Namespace": "aws:elasticbeanstalk:application:environmentsecrets",
    "OptionName": "DB_PASSWORD",
    "Value": "arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:aws-lab/course-db-AbCd12:password"
  }
]
~~~

Chỉ sau khi kiểm tra platform hỗ trợ top-level JSON extraction (nếu dùng `:password`), IAM role, KMS policy và secret metadata, mới cân nhắc lệnh:

~~~bash
# VÍ DỤ CÓ TÁC ĐỘNG - CHỈ KHI ĐÃ ĐƯỢC DUYỆT
aws elasticbeanstalk update-environment \
  --application-name "$APP" \
  --environment-name "$ENV" \
  --option-settings file://secret-options.json \
  --region "$REGION"
~~~

Thao tác này **không tạo secret**; secret phải đã tồn tại và có quyền đọc. Cần lưu ý cách AWS xử lý một môi trường đang update, thứ tự ưu tiên cấu hình và vòng đời instance. Không thay đổi cùng lúc nhiều option nhạy cảm khi thiếu khả năng phân biệt nguyên nhân lỗi.

### 11.3. Kiểm tra sau thay đổi và rollback

1. Xem status môi trường và events, tránh hiển thị secret values.
2. Kiểm tra application health, DB connectivity (qua endpoint app an toàn), ALB 5xx và logs đã redacted.
3. Nếu update thất bại vì IAM/ARN/KMS, kiểm tra **EC2 instance profile** trước.
4. Nếu thay đổi làm ứng dụng lỗi, quay về previous configuration/ARN theo kế hoạch; thao tác rollback cũng có thể gây restart/update.
5. Đảm bảo instances mới/cũ đã đồng bộ secret nếu vừa rotation.
6. Dọn lab đúng phạm vi; **không terminate external RDS** nếu dữ liệu cần giữ.

Không có bước “chạy xong thì xóa secret/DB bằng lệnh nhanh” trong bài lab vì điều đó có nguy cơ làm mất dữ liệu hoặc ảnh hưởng tài nguyên chung. Việc hủy môi trường/tài nguyên cần dựa vào ownership và policy được tổ chức duyệt.

## 12. Chẩn đoán sự cố theo tầng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra an toàn |
|---|---|---|
| Thay `.ebextensions` nhưng biến không đổi | Option bị override bởi environment-level hoặc saved config | Đối chiếu precedence và effective settings (không in secret) |
| File `.ebextensions/*.config` không có hiệu lực | Sai vị trí, sai đuôi `.config`, YAML invalid hoặc không phải Standard | Xem packaging, platform mode và events |
| Environment update kéo dài hoặc reprovision EC2 | Thay option ảnh hưởng resource lifecycle | Xem change scope, events, health và rolling policy |
| Ứng dụng không thấy `DB_PASSWORD` | Namespace sai, platform chưa hỗ trợ, ARN/KMS/IAM lỗi | Kiểm tra platform version, secret metadata và instance profile |
| Secret rotate rồi một số instances DB auth lỗi | Cũ/mới secret value cùng tồn tại, chưa refresh | Đối chiếu rotation/instance replacement events, refresh theo kế hoạch |
| `AccessDenied` khi lấy secret | Thiếu `secretsmanager:GetSecretValue`/`ssm:GetParameter`/`kms:Decrypt` | Kiểm tra role, resource ARN, key policy và condition |
| `DB_HOST` resolve được nhưng TCP timeout | RDS SG chặn, NACL/route/VPC sai | Kiểm tra source SG app, port DB, networking |
| DB báo invalid password | Secret khác user, rotation chưa đồng bộ, account/Region sai | Kiểm tra secret reference, rotation state, không in credential |
| DB báo too many connections | Pool size × số instances vượt khả năng DB | Đo connections/pool, right-size, xem RDS Proxy nếu phù hợp |
| App trả 503 nhưng environment vẫn Healthy | Health endpoint không đại diện luồng thật, dependency lỗi | Kiểm tra ALB targets, app logs, DB/API downstream |
| EB CLI hiển thị dữ liệu nhạy cảm trong diagnostics | Công cụ/ứng dụng in toàn bộ config/env | Ngừng chia sẻ log, rotate secret nếu đã lộ, redaction |
| Deploy mới nhưng config vẫn cũ | Precedence, bản build chưa chứa .ebextensions hoặc configuration update chưa hoàn tất | Xem version, packaging, events và config sources |
| Blue/green rollback code nhưng vẫn lỗi dữ liệu | Database migration không tương thích | Áp expand-and-contract schema, backup/restore và rollout plan |
| Sau terminate còn chi phí RDS | DB là external hoặc retention giữ tài nguyên | Kiểm tra Cost Explorer, DB ownership và deletion policy |
| Không kết nối Secrets Manager từ private subnet | Thiếu NAT/VPC endpoint hoặc DNS/SG endpoint | Kiểm tra VPC egress, PrivateLink endpoint và IAM |

### 12.1. Quy trình chẩn đoán ngắn

~~~text
1. Xác nhận AWS account, Region, application, environment, platform.
2. Kiểm tra environment status/health/events.
3. Xem cấu hình effective và precedence mà KHÔNG in secret.
4. Kiểm tra namespace environment / environmentsecrets, version support.
5. Kiểm tra EC2 instance profile IAM, secret ARN/parameter ARN, KMS policy.
6. Kiểm tra VPC/subnets/security groups, DNS và đường tới RDS/Secrets Manager.
7. Kiểm tra TLS, DB credential rotation, connection pool, database health.
8. Quan sát app logs đã redacted, ALB/EC2/RDS metrics.
9. Sửa đúng lớp lỗi, smoke test và đánh giá ảnh hưởng.
10. Có rollback, backup và trách nhiệm dọn tài nguyên sau lab.
~~~

## 13. Tình huống thiết kế: nền tảng đăng ký khóa học

### 13.1. Bài toán

Một nhóm xây ứng dụng **Spring Boot** có API quản lý khóa học:

- Traffic tăng khi mở đăng ký, cần load-balanced environment và tối thiểu hai AZ.
- Dữ liệu nghiệp vụ ở **PostgreSQL trên RDS** phải được giữ sau khi thay môi trường.
- Ứng dụng upload tài liệu lên **S3**, kết nối tới dịch vụ thông báo qua API token.
- Secret phải nằm trong Secrets Manager/SSM, không vào repository hoặc environment properties dạng plain text.
- Cần staging và production tách quyền, audit, CloudWatch logs, backup và kiểm soát chi phí.
- Định kỳ rotate mật khẩu DB, không được làm tất cả instances mất kết nối cùng lúc.

### 13.2. Thiết kế tham khảo

| Thành phần | Lựa chọn | Giải thích |
|---|---|---|
| Application | Một app, ít nhất staging/prod environments | Cùng code, khác config |
| Compute | Beanstalk Standard, load-balanced, Auto Scaling nhiều AZ | Đủ capacity, thay instance an toàn |
| App config | `APP_ENV`, `DB_HOST`, `DB_PORT`, `DB_NAME` | Biến không nhạy cảm, quản trị rõ nguồn |
| Secrets | `DB_USER`/`DB_PASSWORD` trong Secrets Manager, API token trong SSM/Secrets Manager | Không lưu plaintext trong source |
| Secret access | EC2 instance profile chỉ cho đọc ARNs môi trường tương ứng | Least privilege |
| Database | RDS external trong private DB subnets, Multi-AZ theo RTO/RPO | Tách vòng đời khỏi app environment |
| Network | App instances private, SG App → SG DB đúng cổng | Giảm bề mặt tấn công |
| API ingress | ALB HTTPS với cert hợp lệ và health checks | Bảo vệ client, quan sát target health |
| S3 | S3 private bucket + IAM role/bucket policy phù hợp | Không dùng static AWS credentials |
| Rotations | Controlled refresh, dual credentials/zero-downtime plan | Tránh instances cũ/mới dùng password khác |
| Logging | Redacted logs, CloudWatch metrics/events | Chẩn đoán, audit, alerts |
| Recovery | RDS backup/restore test, deploy rollback/blue-green | Data durability và availability |
| Cost | Right-sizing, tagging, Budgets, dọn environments lab | Kiểm soát phí EC2/RDS/NAT/ALB |

### 13.3. Câu hỏi phân tích

1. Vì sao `DB_PASSWORD` không nên đặt trong `.ebextensions` dưới namespace environment thông thường?
2. Trong môi trường load-balanced nhiều EC2 instances, điều gì xảy ra sau khi secret rotate nhưng chưa refresh đồng loạt?
3. Nếu muốn database sống tiếp sau khi terminate environment, nên dùng RDS mô hình nào?
4. `DB_HOST` tồn tại nhưng request DB timeout: bạn kiểm tra DNS, SG hay secret trước?
5. Vì sao gán `AdministratorAccess` cho Beanstalk service role không phải là giải pháp đúng cho mọi `AccessDenied` ở EC2 instance?
6. Vì sao Blue/green deployment cần kiểm tra backward compatibility của database schema?
7. Nếu tăng từ 2 lên 8 instances, DB connection pool có thể gây vấn đề gì?
8. Nếu environment-level option override `.ebextensions`, bạn nên sửa ở đâu để không tạo drift?
9. Khi AWS CLI chỉ cần xem secret metadata, vì sao không nên gọi `GetSecretValue`?
10. Một environment bị xóa có thể còn những tài nguyên nào đang tính phí?
11. Những Platform versions nào hỗ trợ environment secrets và JSON key extraction, và vì sao phải xác minh version thật?
12. Nếu Beanstalk health Green nhưng người dùng đăng nhập thất bại, cần thêm metric hoặc kiểm thử gì?

**Gợi ý ngắn:**

1. Plaintext config có nguy cơ lộ và khó rotate; tham chiếu secret store.
2. Instances mới/cũ có thể giữ hai password; cần kế hoạch refresh và dual credentials.
3. External/decoupled RDS được quản lý độc lập với environment.
4. Kiểm tra đường mạng, SG, port và DNS trước; mã 401/DB auth mới tập trung credential.
5. Role, IAM resource policy, permissions boundary/SCP và service context phải đúng trách nhiệm; mở quyền rộng làm tăng rủi ro.
6. Phiên bản app cũ phải đọc được schema trong cửa sổ rollback.
7. Tổng DB connections vượt giới hạn; tính theo max instances × pool size.
8. Review nguồn cấu hình ưu tiên cao và quản trị thay đổi qua IaC/pipeline; không chỉ sửa file.
9. Metadata đủ để kiểm tra tồn tại/rotation, đọc value làm tăng rủi ro rò rỉ.
10. RDS external, EBS, snapshots, NAT, ALB, S3/logs, domain/metrics.
11. Secrets env var trên platform release từ 26/03/2025; JSON-key extraction từ 13/01/2026 với giới hạn; phải xác minh platform.
12. Cần test nghiệp vụ, app logs đã redacted, DB/KMS/secrets telemetry, ALB 5xx và traces.

## 14. Những hiểu lầm cần tránh

**“Elastic Beanstalk chỉ là EC2 với nút deploy.”** Chưa đầy đủ. Nó quản lý environment configuration và điều phối nhiều tài nguyên/lifecycle; tuy vậy đội phát triển vẫn phải vận hành ứng dụng và dữ liệu.

**“Mọi environment variables của Beanstalk đều là secrets được mã hóa.”** Sai. Plain environment properties không phải nơi quản trị bí mật tương đương Secrets Manager; phải phân biệt hai namespaces.

**“Đặt Secret ARN vào namespace environment thông thường là Beanstalk tự đọc giá trị.”** Sai. Namespace `aws:elasticbeanstalk:application:environment` sẽ cung cấp một string thông thường. Để Beanstalk tự fetch secret vào biến, cần `aws:elasticbeanstalk:application:environmentsecrets` trên platform hỗ trợ.

**“Secret rotation sẽ tự cập nhật tất cả đang chạy.”** Sai. Native environment secrets được fetch trong bootstrap/refresh; rotation không tự đồng bộ mọi instance.

**“Chỉ cần gán IAM quyền cho service role.”** Sai. Với native secret-backed env vars trên Standard environment, kiểm tra **EC2 instance profile role** và KMS policy.

**“RDS gắn với Beanstalk luôn được giữ khi xóa environment.”** Sai. Vòng đời coupled RDS phụ thuộc cấu hình/deletion policy; production nên cân nhắc external/decoupled database.

**“Sửa .ebextensions thì override mọi thứ.”** Sai. Cấu hình trực tiếp trên environment và saved configs có mức ưu tiên cao hơn.

**“Kết nối DB thất bại chỉ có thể do mật khẩu.”** Sai. DNS, subnet, security groups, TLS, database state và connection limits đều có thể gây lỗi.

**“Beanstalk health Green là đủ để chứng minh nghiệp vụ đúng.”** Sai. Cần SLO, application health, synthetic checks, metrics và logs của DB/ứng dụng.

**“Không phải tạo thêm tài nguyên vì Beanstalk miễn phí.”** Sai. Tài nguyên AWS bên dưới và các dịch vụ tích hợp có thể tính phí.

## 15. Checklist trước khi triển khai production

### Cấu hình

- [ ] Đã xác nhận **Beanstalk Standard hay Cluster**, platform branch/version, runtime compatibility.
- [ ] Có chiến lược môi trường dev/staging/prod và phân tách dữ liệu/quyền rõ ràng.
- [ ] Đã kiểm tra thứ tự precedence giữa direct options, saved config, `.ebextensions` và defaults.
- [ ] Environment properties chỉ chứa thông tin phù hợp, không hard-code mật khẩu.
- [ ] Secret references dùng `environmentsecrets` trên platform hỗ trợ hoặc SDK retrieval theo thiết kế.
- [ ] Có IAM least privilege cho **instance profile**, KMS key policy và network path đến secret store.
- [ ] Có cơ chế secret rotation và refresh, xét tình huống old/new values cùng tồn tại.
- [ ] Hooks/scripts không in secrets hoặc chạy lệnh không được duyệt.

### Kết nối dữ liệu và vận hành

- [ ] RDS data lifecycle tách khỏi Beanstalk app khi yêu cầu giữ lâu dài.
- [ ] App SG ↔ DB SG, TCP port, DNS và network routing được kiểm thử.
- [ ] DB TLS, connection pool, timeout, backup và failover đáp ứng SLO.
- [ ] Dịch vụ S3/DynamoDB/SQS dùng IAM role, không nhúng access key.
- [ ] Health checks, CloudWatch logs/metrics/alerts và retention được cấu hình.
- [ ] Đã diễn tập smoke test, staged rollout, rollback và schema compatibility.
- [ ] Có backup/restore plan được kiểm thử, kể cả sau khi terminate một app environment.
- [ ] Có tags, budgets, Cost Explorer và lịch dọn tài nguyên thí nghiệm.
- [ ] CLI/CI logs không xuất `SecretString`, plain env values hoặc access credentials.

**Kết quả mong đợi:** Bạn biết khai báo một Beanstalk environment có cấu hình rõ nguồn, truyền dữ liệu nhạy cảm bằng secret store đúng cách, xây kết nối RDS private an toàn và điều phối deployment/rotation để tránh gián đoạn. Bạn có thể xác minh cấu hình bằng CLI mà không để lộ secret, đồng thời giải thích tác động tới khả năng phục hồi và chi phí.

## Tài liệu AWS chính thức

- [AWS Elastic Beanstalk: Environment configuration](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/command-options.html)
- [Configuration options for Beanstalk Standard environments](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/command-options-general.html)
- [Environment variables and other software settings](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/environments-cfg-softwaresettings.html)
- [Advanced customization with .ebextensions](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/ebextensions.html)
- [Setting configuration options after environment creation](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/environment-configuration-methods-after.html)
- [Elastic Beanstalk platform hooks](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/platforms-linux-extend.hooks.html)
- [Using Elastic Beanstalk with Secrets Manager and SSM Parameter Store](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/AWSHowTo.secrets.html)
- [Fetch secrets into Elastic Beanstalk environment variables](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/AWSHowTo.secrets.env-vars.html)
- [Elastic Beanstalk integration with RDS databases](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/using-features.managing.db.html)
- [Using Elastic Beanstalk with Amazon RDS](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/AWSHowTo.RDS.html)
- [AWS Elastic Beanstalk pricing](https://aws.amazon.com/elasticbeanstalk/pricing/)
- [AWS Secrets Manager pricing](https://aws.amazon.com/secrets-manager/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)

> **Lưu ý áp dụng:** Tất cả account IDs, ARN, RDS endpoint, tên environment, IAM role và giá trị cấu hình trong ví dụ đều giả định. AWS thay đổi platform releases, tích hợp secret, điều kiện IAM và bảng giá theo thời gian/Region. Trước khi triển khai hoặc cập nhật production, hãy xác minh tài liệu AWS và environment thực tế, thử nghiệm trên sandbox, bảo vệ dữ liệu và thực hiện quy trình phê duyệt thay đổi.
