# Xây dựng hạ tầng nhiều môi trường bằng CDK Java

Một ứng dụng AWS thường phải chạy qua nhiều môi trường: development để thử nghiệm, staging để kiểm tra tích hợp và production để phục vụ người dùng. Khi mỗi môi trường được tạo thủ công hoặc bằng những template khác nhau, cấu hình dễ lệch nhau: dev có một loại subnet, staging thiếu alarm, production dùng policy khác hoặc một thay đổi bảo mật chỉ được áp dụng ở một account. AWS Cloud Development Kit (AWS CDK) giúp mô tả hạ tầng bằng mã nguồn và tái sử dụng cùng một thiết kế cho nhiều AWS account và Region.

Capstone này xây dựng một CDK application bằng Java và AWS CDK v2. Một cấu trúc ứng dụng được triển khai thành các stack ở nhiều môi trường, mỗi môi trường có account, Region, CIDR, kích thước compute, retention và mức bảo vệ riêng. Bài học đi từ cấu trúc project, cấu hình environment, construct/stack/stage đến bootstrap, cross-account trust, secrets, testing và pipeline promotion. Người học sẽ có thể thiết kế quy trình triển khai lặp lại, có kiểm soát thay đổi và có khả năng rollback.

CDK không phải công cụ thay thế AWS Organizations, IAM governance hay quy trình quản lý thay đổi. CDK tạo CloudFormation templates và triển khai chúng bằng CloudFormation; quyền thực thi cuối cùng vẫn phụ thuộc IAM role, bootstrap permissions, SCP, resource policy và service quota của account đích.

## 1. Mục tiêu capstone

Sau capstone, người học có thể:

- Giải thích quan hệ giữa CDK App, Construct, Stack, Stage và CloudFormation stack.
- Khởi tạo Java CDK v2 project và quản lý dependency bằng Maven.
- Thiết kế cấu hình dev/staging/prod theo account và Region.
- Phân biệt environment-specific stack và environment-agnostic stack.
- Tái sử dụng construct và stack mà vẫn giữ cấu hình riêng cho từng môi trường.
- Tách network, data, application và observability theo ranh giới lifecycle.
- Dùng context lookup có kiểm soát và giữ synthesis repeatable.
- Bootstrap nhiều account/Region bằng modern bootstrap template.
- Thiết lập cross-account deployment trust và quyền CloudFormation execution.
- Bảo vệ secret, IAM role, KMS key và dữ liệu nhạy cảm.
- Xây dựng CDK Pipelines với stage promotion, automated validation và manual approval.
- Kiểm thử CloudFormation template bằng JUnit và CDK Assertions.
- Sử dụng cdk synth, cdk diff, cdk deploy, drift detection và rollback.
- Xây dựng quy trình triển khai an toàn cho nhiều Region.

## 2. Kịch bản kiến trúc

Một công ty có ba môi trường độc lập:

| Môi trường | AWS account | Region | Mục đích |
|---|---|---|---|
| dev | 111111111111 | ap-southeast-1 | Phát triển, thử nghiệm nhanh |
| staging | 222222222222 | ap-southeast-1 | Kiểm thử tích hợp, UAT và performance |
| prod | 333333333333 | ap-southeast-1 | Phục vụ production |
| prod-dr (tùy chọn) | 333333333333 | ap-southeast-2 | Disaster recovery và kiểm thử failover |

Account ID và Region trên chỉ là ví dụ; thay bằng giá trị của tổ chức. Account ID không phải secret, nhưng phải được quản lý như cấu hình deployment để tránh triển khai nhầm đích.

Ứng dụng mẫu gồm:

- VPC với public/private subnets theo nhu cầu.
- Application Load Balancer làm entry point.
- Compute layer (ECS Fargate hoặc Lambda) chạy API.
- DynamoDB hoặc RDS làm data layer.
- S3 lưu asset/log/artifact.
- Secrets Manager lưu credential.
- KMS mã hóa tài nguyên cần customer-managed key.
- CloudWatch log group, alarm và dashboard.

Mỗi môi trường dùng cùng cấu trúc nhưng có tham số khác nhau. Production có thể dùng nhiều AZ hơn, retention dài hơn, deletion protection và alarm nghiêm ngặt hơn. Dev có thể dùng cấu hình nhỏ và cho phép cleanup sau lab.

### 2.1 Sơ đồ triển khai

    Source repository
          |
       CDK Java
          |
       Unit tests
          |
      cdk synth
          |
    Cloud Assembly
          |
       cdk diff
          |
      Dev account
          |
    Smoke/integration tests
          |
     Staging account
          |
    UAT / security review
          |
    Manual approval
          |
      Prod account
          |
    Monitoring / rollback

CDK Pipelines có thể tự động hóa source, synth, asset publishing, cross-account deployment và validation. Mỗi Stage đại diện cho một bản sao ứng dụng trong một environment; trong Stage có thể chứa nhiều stack có dependency.

## 3. Các khái niệm CDK cần nắm

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| App | Root construct và điểm tổng hợp ứng dụng | App |
| Construct | Đơn vị mô hình hóa tài nguyên hoặc nhóm tài nguyên | Bucket, Vpc, construct nội bộ |
| Stack | Đơn vị triển khai CloudFormation | NetworkStack, ApplicationStack |
| Stage | Một bản triển khai logic gồm một hoặc nhiều stack | ApplicationStage cho dev/prod |
| Cloud Assembly | Kết quả synth gồm templates, assets và manifest | cdk.out |
| Bootstrap stack | Tài nguyên hỗ trợ CDK deploy vào account/Region | CDKToolkit |

Một Construct có thể chứa construct khác. Stack là construct đặc biệt tạo CloudFormation template. Stage là construct đặc biệt gom các stack cùng một lần triển khai. cdk synth tạo Cloud Assembly; cdk deploy sử dụng assembly đó để triển khai.

### 3.1 Tách stack theo lifecycle và ownership

Không nên tạo một stack khổng lồ chứa mọi thứ nếu các thành phần có lifecycle khác nhau. Một cách phân chia:

| Stack | Trách nhiệm | Thay đổi thường gặp |
|---|---|---|
| NetworkStack | VPC, subnet, route, endpoints | Thay đổi network/security |
| SecurityStack | KMS, security baseline, shared roles | Governance và encryption |
| DataStack | DynamoDB/RDS/S3/backup | Schema, retention, storage |
| ApplicationStack | ECS/Lambda/API/ALB | Release ứng dụng |
| ObservabilityStack | Log groups, alarms, dashboards | SLO và alert policy |

Stack boundary nên phản ánh ownership, quyền deploy và lifecycle. Nếu hai stack luôn phải thay đổi cùng nhau và phụ thuộc chặt, có thể giữ trong một stack hoặc Stage. Nếu data layer cần lifecycle độc lập với app, tách stack để tránh thay đổi application vô tình thay thế database.

### 3.2 Stack dependency

Trong cùng account và Region, CDK có thể tạo cross-stack references khi stack dùng resource attribute của stack khác. Ví dụ ApplicationStack nhận VPC hoặc security group từ NetworkStack. CDK tạo CloudFormation export/import và sắp xếp dependency.

    NetworkStack
         |
         +---- VPC / Subnets
                    |
              ApplicationStack
                    |
               ALB / Service

Cross-stack reference có thể làm việc xóa/đổi tên resource phức tạp. Không xóa export khi stack khác còn import. Với cross-account hoặc cross-Region, CloudFormation export/import trực tiếp không hoạt động như reference cùng environment; hãy truyền ARN/ID qua cấu hình, SSM Parameter Store, resource sharing (AWS RAM), DNS hoặc pipeline outputs theo thiết kế.

## 4. Tạo Java CDK v2 project

### 4.1 Công cụ

Chuẩn bị:

- JDK LTS tương thích với project, khuyến nghị Java 17 hoặc 21.
- Apache Maven.
- Node.js/npm để cài AWS CDK CLI.
- AWS CLI v2.
- AWS CDK CLI v2.
- Credential/profile có quyền làm việc với account lab.

Khởi tạo project:

    mkdir aws-multi-env
    cd aws-multi-env
    cdk init app --language java

CDK Java dùng package Maven software.amazon.awscdk. AWS CDK v2 gom các service constructs ổn định vào aws-cdk-lib; constructs còn experimental có package riêng. Dùng version chính xác trong pom.xml và cập nhật CLI/runtime có kiểm soát để build repeatable.

### 4.2 Cấu trúc project đề xuất

    aws-multi-env/
    ├── cdk.json
    ├── cdk.context.json
    ├── pom.xml
    ├── README.md
    ├── config/
    │   ├── environments.properties
    │   └── feature-matrix.properties
    ├── src/
    │   ├── main/java/com/example/platform/
    │   │   ├── Main.java
    │   │   ├── config/
    │   │   │   └── EnvironmentConfig.java
    │   │   ├── stages/
    │   │   │   └── ApplicationStage.java
    │   │   ├── stacks/
    │   │   │   ├── NetworkStack.java
    │   │   │   ├── DataStack.java
    │   │   │   ├── ApplicationStack.java
    │   │   │   └── ObservabilityStack.java
    │   │   └── constructs/
    │   │       └── ApiService.java
    │   └── test/java/com/example/platform/
    │       ├── NetworkStackTest.java
    │       └── ApplicationStackTest.java
    └── .gitignore

Đây là cách tổ chức tham khảo; project nhỏ có thể ít package hơn. Không đưa credential, private key, password hoặc token vào config file.

### 4.3 Dependency Maven

Trong pom.xml, giữ các dependency ở cùng một dòng version CDK v2 đã kiểm thử:

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awscdk</groupId>
            <artifactId>aws-cdk-lib</artifactId>
            <version>2.273.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.12.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

Version aws-cdk-lib 2.273.0 và JUnit Jupiter 5.12.2 là ví dụ đã pin; chọn version đã kiểm thử với JDK/Maven của project và khóa chúng trong source control. Maven kéo constructs như dependency bắc cầu; nếu khai báo trực tiếp, phải chọn version tương thích với aws-cdk-lib. Chạy mvn test trong CI.

### 4.4 cdk.json

cdk.json khai báo lệnh để CDK CLI chạy Java app. Project do cdk init tạo sẵn cấu hình phù hợp Maven. Giữ cấu hình này trong source control và điều chỉnh theo cấu trúc thực tế thay vì tạo một command khác cho từng môi trường.

cdk.context.json lưu các giá trị context lookup như VPC/subnet/AMI/AZ. Hai file này là một phần trạng thái của CDK app; commit chúng để local và CI synth cùng kết quả.

## 5. Mô hình cấu hình theo môi trường

### 5.1 Cấu hình không phải secret

Các giá trị có thể lưu trong repository:

- Environment name.
- Account ID và Region.
- CIDR/subnet sizing.
- Desired/min/max capacity.
- Log retention.
- Backup retention.
- Deletion protection.
- Feature flags không nhạy cảm.
- Resource tags và naming convention.

Các giá trị không được lưu trong repository:

- AWS access key/secret key.
- Database password.
- API token/private key.
- Credential của third-party.
- Secret connection string.

Secret được lưu trong Secrets Manager hoặc SSM Parameter Store SecureString và được runtime đọc bằng IAM role.

### 5.2 environments.properties

Ví dụ file cấu hình:

    environment.dev.account=111111111111
    environment.dev.region=ap-southeast-1
    environment.dev.vpcCidr=10.10.0.0/16
    environment.dev.logRetentionDays=7
    environment.dev.deletionProtection=false

    environment.staging.account=222222222222
    environment.staging.region=ap-southeast-1
    environment.staging.vpcCidr=10.20.0.0/16
    environment.staging.logRetentionDays=30
    environment.staging.deletionProtection=true

    environment.prod.account=333333333333
    environment.prod.region=ap-southeast-1
    environment.prod.vpcCidr=10.30.0.0/16
    environment.prod.logRetentionDays=365
    environment.prod.deletionProtection=true

CIDR phải được quy hoạch để không overlap với VPC, VPN, Transit Gateway và mạng on-premises. Log retention thực tế phải tuân thủ legal/compliance policy của tổ chức.

### 5.3 EnvironmentConfig trong Java

Một class cấu hình nên bất biến, validate dữ liệu ngay khi load và cung cấp Environment cho Stack:

    package com.example.platform.config;

    import java.util.Locale;
    import software.amazon.awscdk.Environment;

    public final class EnvironmentConfig {
        private final String name;
        private final String account;
        private final String region;
        private final String vpcCidr;
        private final int logRetentionDays;
        private final boolean deletionProtection;

        public EnvironmentConfig(
                String name,
                String account,
                String region,
                String vpcCidr,
                int logRetentionDays,
                boolean deletionProtection) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Environment name is required");
            }
            if (account == null || !account.matches("\\d{12}")) {
                throw new IllegalArgumentException("AWS account must contain 12 digits");
            }
            if (region == null || region.isBlank()) {
                throw new IllegalArgumentException("Region is required");
            }
            if (vpcCidr == null || vpcCidr.isBlank()) {
                throw new IllegalArgumentException("VPC CIDR is required");
            }
            if (logRetentionDays <= 0) {
                throw new IllegalArgumentException("Log retention must be positive");
            }
            this.name = name;
            this.account = account;
            this.region = region;
            this.vpcCidr = vpcCidr;
            this.logRetentionDays = logRetentionDays;
            this.deletionProtection = deletionProtection;
        }

        public Environment toCdkEnvironment() {
            return Environment.builder()
                    .account(account)
                    .region(region)
                    .build();
        }

        public String getName() { return name; }
        public String getAccount() { return account; }
        public String getRegion() { return region; }
        public String getVpcCidr() { return vpcCidr; }
        public int getLogRetentionDays() { return logRetentionDays; }
        public boolean isDeletionProtection() { return deletionProtection; }
        public boolean isProduction() {
            return "prod".equalsIgnoreCase(name)
                    || name.toLowerCase(Locale.ROOT).startsWith("prod-");
        }
    }

Đây là ví dụ rút gọn. Trong project hoàn chỉnh, dùng Properties hoặc thư viện cấu hình để load file, validate CIDR, kiểm tra environment name và từ chối giá trị chưa khai báo. Không fallback âm thầm về production hoặc default profile.

### 5.4 Chọn environment có chủ đích

Một cách chọn environment là dùng system property:

    String target = System.getProperty("targetEnv", "dev");

    if (!environmentConfigs.containsKey(target)) {
        throw new IllegalArgumentException("Unknown targetEnv: " + target);
    }

Lệnh synth/deploy có thể truyền -DtargetEnv=staging qua command chạy app. Với CDK Pipelines, Stage nên được tạo rõ ràng từ các cấu hình đã review thay vì phụ thuộc profile của máy cá nhân.

## 6. Environment-specific và environment-agnostic stacks

### 6.1 Environment-specific stack

Stack được gắn cặp account/Region cụ thể:

    StackProps stackProps = StackProps.builder()
            .env(config.toCdkEnvironment())
            .build();

    new NetworkStack(app, "NetworkDev", config, stackProps);

Khi synth, CDK biết account/Region nên có thể dùng context lookup như Vpc.fromLookup, truy cập danh sách AZ cụ thể và tạo resource có logic phụ thuộc environment. Đây là lựa chọn phù hợp với multi-account deployment có cấu hình rõ.

### 6.2 Environment-agnostic stack

Nếu không chỉ định env, template có thể được synth theo hướng không gắn account/Region cụ thể và triển khai sang nhiều environment. Cách này hữu ích khi stack không cần thông tin environment lúc synth. Tuy nhiên:

- Không dùng logic phụ thuộc stack.account, stack.region hoặc AZ cụ thể.
- Không dùng Vpc.fromLookup cần account/Region cụ thể.
- Một số cross-stack reference/context provider yêu cầu environment cụ thể.
- Không nên trộn template agnostic với giả định về tài nguyên chỉ tồn tại ở một account.

### 6.3 Tránh lấy account ngầm từ profile trên production

CDK có thể lấy CDK_DEFAULT_ACCOUNT và CDK_DEFAULT_REGION từ credential/profile. Cách này thuận tiện khi phát triển local, nhưng synthesis có thể thay đổi theo user/máy/session. Với production, khai báo target account/Region tường minh trong cấu hình đã kiểm soát hoặc Stage pipeline.

Không dùng --profile prod như biện pháp duy nhất để đảm bảo đúng đích nếu Stack đã hard-code một env khác; environment trong Stack có độ ưu tiên cao hơn profile khi synth.

## 7. Xây dựng CDK App và Stage bằng Java

### 7.1 Main.java

App là root của construct tree. Main đọc cấu hình, tạo các Stage và gọi synth:

    package com.example.platform;

    import com.example.platform.config.EnvironmentConfig;
    import com.example.platform.config.EnvironmentConfigLoader;
    import com.example.platform.stages.ApplicationStage;
    import software.amazon.awscdk.App;

    public final class Main {
        public static void main(final String[] args) {
            App app = new App();

            EnvironmentConfig dev = EnvironmentConfigLoader.load("dev");
            EnvironmentConfig staging = EnvironmentConfigLoader.load("staging");
            EnvironmentConfig prod = EnvironmentConfigLoader.load("prod");

            new ApplicationStage(app, "Dev", dev);
            new ApplicationStage(app, "Staging", staging);
            new ApplicationStage(app, "Prod", prod);

            app.synth();
        }
    }

EnvironmentConfigLoader là helper của project để đọc properties và validate. Với CDK Pipelines, Stage thường được khởi tạo bên trong PipelineStack thay vì tạo cả ba stage trong app chạy local. Hai kiểu tổ chức đều hợp lệ; chọn một cách làm rõ deployment target.

### 7.2 ApplicationStage.java

Stage gom các stack tạo thành một bản triển khai của ứng dụng:

    package com.example.platform.stages;

    import com.example.platform.config.EnvironmentConfig;
    import com.example.platform.stacks.ApplicationStack;
    import com.example.platform.stacks.DataStack;
    import com.example.platform.stacks.NetworkStack;
    import software.amazon.awscdk.Stage;
    import software.amazon.awscdk.StageProps;
    import software.constructs.Construct;

    public final class ApplicationStage extends Stage {
        public ApplicationStage(
                final Construct scope,
                final String id,
                final EnvironmentConfig config) {
            super(scope, id, StageProps.builder()
                    .env(config.toCdkEnvironment())
                    .build());

            NetworkStack network = new NetworkStack(this, "Network", config);
            DataStack data = new DataStack(this, "Data", config);

            ApplicationStack application = new ApplicationStack(
                    this,
                    "Application",
                    config,
                    network.getVpc(),
                    data.getTable());

            application.addDependency(network);
            application.addDependency(data);
        }
    }

Stage có environment mặc định để các stack con kế thừa account/Region. Nếu stack cần environment khác, phải khai báo rõ và cân nhắc vì điều đó làm thay đổi ranh giới triển khai.

### 7.3 NetworkStack.java

Ví dụ tạo VPC với hai AZ và subnet phân tầng:

    package com.example.platform.stacks;

    import com.example.platform.config.EnvironmentConfig;
    import java.util.List;
    import software.amazon.awscdk.Stack;
    import software.amazon.awscdk.StackProps;
    import software.amazon.awscdk.Tags;
    import software.amazon.awscdk.services.ec2.IpAddresses;
    import software.amazon.awscdk.services.ec2.SubnetConfiguration;
    import software.amazon.awscdk.services.ec2.SubnetType;
    import software.amazon.awscdk.services.ec2.Vpc;
    import software.constructs.Construct;

    public final class NetworkStack extends Stack {
        private final Vpc vpc;

        public NetworkStack(
                final Construct scope,
                final String id,
                final EnvironmentConfig config) {
            super(scope, id, StackProps.builder()
                    .description("Network foundation for " + config.getName())
                    .terminationProtection(config.isDeletionProtection())
                    .build());

            this.vpc = Vpc.Builder.create(this, "Vpc")
                    .ipAddresses(IpAddresses.cidr(config.getVpcCidr()))
                    .maxAzs(2)
                    .natGateways(config.isProduction() ? 2 : 1)
                    .subnetConfiguration(List.of(
                            SubnetConfiguration.builder()
                                    .name("public")
                                    .subnetType(SubnetType.PUBLIC)
                                    .cidrMask(24)
                                    .build(),
                            SubnetConfiguration.builder()
                                    .name("application")
                                    .subnetType(SubnetType.PRIVATE_WITH_EGRESS)
                                    .cidrMask(24)
                                    .build(),
                            SubnetConfiguration.builder()
                                    .name("isolated")
                                    .subnetType(SubnetType.PRIVATE_ISOLATED)
                                    .cidrMask(24)
                                    .build()))
                    .build();

            Tags.of(this).add("Environment", config.getName());
            Tags.of(this).add("ManagedBy", "AWS-CDK");
            Tags.of(this).add("Service", "CLOUD_PROVIDERS_AWS");
        }

        public Vpc getVpc() {
            return vpc;
        }
    }

Đây là ví dụ kiến trúc; cần xác nhận API của CDK version đang dùng và sizing CIDR trước khi synth. Hai NAT Gateways ở production giúp giảm phụ thuộc vào một AZ nhưng tăng chi phí. Nếu workload không cần outbound Internet, ưu tiên VPC endpoints và private connectivity phù hợp.

### 7.4 DataStack.java

DataStack có thể tạo DynamoDB table hoặc import một resource đã tồn tại. Ví dụ table có point-in-time recovery và retain policy:

    package com.example.platform.stacks;

    import com.example.platform.config.EnvironmentConfig;
    import software.amazon.awscdk.RemovalPolicy;
    import software.amazon.awscdk.Stack;
    import software.amazon.awscdk.StackProps;
    import software.amazon.awscdk.services.dynamodb.Attribute;
    import software.amazon.awscdk.services.dynamodb.AttributeType;
    import software.amazon.awscdk.services.dynamodb.BillingMode;
    import software.amazon.awscdk.services.dynamodb.PointInTimeRecoverySpecification;
    import software.amazon.awscdk.services.dynamodb.Table;
    import software.constructs.Construct;

    public final class DataStack extends Stack {
        private final Table table;

        public DataStack(
                Construct scope,
                String id,
                EnvironmentConfig config) {
            super(scope, id, StackProps.builder()
                    .terminationProtection(config.isDeletionProtection())
                    .build());

            this.table = Table.Builder.create(this, "Orders")
                    .partitionKey(Attribute.builder()
                            .name("pk")
                            .type(AttributeType.STRING)
                            .build())
                    .sortKey(Attribute.builder()
                            .name("sk")
                            .type(AttributeType.STRING)
                            .build())
                    .billingMode(BillingMode.PAY_PER_REQUEST)
                    .pointInTimeRecoverySpecification(
                            PointInTimeRecoverySpecification.builder()
                                    .pointInTimeRecoveryEnabled(true)
                                    .recoveryPeriodInDays(35)
                                    .build())
                    .deletionProtection(config.isDeletionProtection())
                    .removalPolicy(config.isDeletionProtection()
                            ? RemovalPolicy.RETAIN
                            : RemovalPolicy.DESTROY)
                    .build();
        }

        public Table getTable() {
            return table;
        }
    }

Ở môi trường bật deletion protection, RETAIN bảo vệ dữ liệu khỏi việc xóa stack vô ý, nhưng có nghĩa resource có thể còn tồn tại sau khi stack bị xóa và cần quy trình quản lý riêng. DESTROY chỉ phù hợp với tài nguyên lab/dev có thể tái tạo; không bật auto-delete cho dữ liệu production.

### 7.5 ApplicationStack.java

ApplicationStack nhận các interface từ stack nền tảng:

    package com.example.platform.stacks;

    import com.example.platform.config.EnvironmentConfig;
    import software.amazon.awscdk.Stack;
    import software.amazon.awscdk.services.dynamodb.ITable;
    import software.amazon.awscdk.services.ec2.IVpc;
    import software.constructs.Construct;

    public final class ApplicationStack extends Stack {
        public ApplicationStack(
                Construct scope,
                String id,
                EnvironmentConfig config,
                IVpc vpc,
                ITable ordersTable) {
            super(scope, id);

            // Tạo security group, ECS service hoặc Lambda tại đây.
            // Dùng vpc và ordersTable để kết nối tới resource nền tảng.
            // Chỉ cấp quyền cần thiết cho execution role của ứng dụng.
        }
    }

Đoạn trên minh họa ranh giới dependency, không phải một ứng dụng deploy hoàn chỉnh. Trong implementation thực tế, dùng interface như IVpc/ITable khi construct hỗ trợ để giảm coupling vào concrete construct.

## 8. Tái sử dụng construct và cấu hình theo environment

### 8.1 Dùng props thay vì đọc global context ở mọi nơi

Construct nên nhận dữ liệu qua props/constructor. Ví dụ ApiService nhận VPC, security group, desired count, log retention và secret reference. Điều này giúp test dễ hơn và tránh một construct tự đọc biến môi trường không rõ nguồn.

### 8.2 Dùng feature matrix

| Feature | dev | staging | prod |
|---|---|---|---|
| NAT gateways | 1 | 1 | 2 |
| Multi-AZ database | Không bắt buộc | Có | Có |
| Deletion protection | Tắt | Bật | Bật |
| Log retention | 7 ngày | 30 ngày | Theo compliance |
| Backup retention | Ngắn | Trung bình | Theo RPO/RTO |
| Alarm severity | Warning | Warning/Critical | Critical + escalation |
| Manual approval | Không | UAT | Bắt buộc |

Không tạo quá nhiều nhánh if/else rải rác trong stack. Tập trung khác biệt vào EnvironmentConfig hoặc props cụ thể. Nếu một môi trường có kiến trúc khác hẳn, cân nhắc một Stage/stack riêng thay vì nhồi nhiều cờ vào cùng construct.

### 8.3 Tags và naming

Áp dụng tag chuẩn cho stack/resource:

- Application
- Environment
- Owner
- CostCenter
- DataClassification
- ManagedBy
- Repository

Tên resource cần có prefix/environment nhưng vẫn tuân thủ giới hạn ký tự và tính duy nhất toàn cục của từng service. Tránh tạo tên bucket giống nhau giữa account/Region nếu bucket name toàn cục.

## 9. Context lookup và tính lặp lại của synthesis

CDK context là key-value data có thể đến từ cdk.json, cdk.context.json, CLI hoặc construct. Context provider có thể tra cứu AZ, VPC, hosted zone, AMI và giá trị account-specific khác.

### 9.1 Vpc.fromLookup

Khi VPC đã được tạo bên ngoài CDK:

    IVpc existingVpc = Vpc.fromLookup(
            this,
            "SharedVpc",
            VpcLookupOptions.builder()
                    .vpcId("vpc-0123456789abcdef0")
                    .build());

Kết quả lookup được cache trong cdk.context.json. File context cần commit để CI và máy developer synth ra cùng template. Nếu xóa cache hoặc refresh context, template có thể thay đổi vì AZ/subnet/AMI đã thay đổi trong account.

### 9.2 Quy trình cập nhật context

1. Xác định lý do cần refresh context.
2. Chạy synth trong account/Region mục tiêu với quyền lookup.
3. Review diff của cdk.context.json.
4. Review CloudFormation template diff.
5. Commit context cùng thay đổi hạ tầng liên quan.
6. Không để pipeline tự lookup bằng credential production rộng quyền.

Không commit secret vào context file. Context lookup không phải kho secret và không thay thế config management.

### 9.3 Context và environment

Lookup yêu cầu environment cụ thể vì CDK phải biết account/Region để truy vấn. Nếu một stack phải triển khai vào nhiều account/Region nhưng không thể gắn env khi synth, hãy thiết kế theo environment-specific Stage hoặc dùng parameter/reference rõ ràng thay vì gọi lookup không xác định.

## 10. Bảo vệ secret, IAM và network

### 10.1 Không đưa secret vào source hoặc CloudFormation template

CDK có kiểu SecretValue để biểu diễn secret reference. Giá trị thật nên nằm trong Secrets Manager hoặc SSM Parameter Store SecureString. Không dùng unsafePlainText cho password/token; không ghi plaintext secret vào properties vì giá trị có thể xuất hiện trong synthesized template, CloudFormation console hoặc logs.

Ví dụ import secret và cấp quyền đọc cho runtime role:

    ISecret databaseSecret = Secret.fromSecretNameV2(
            this,
            "DatabaseSecret",
            "orders/prod/database");

    Role taskRole = Role.Builder.create(this, "ApiTaskRole")
            .assumedBy(new ServicePrincipal("ecs-tasks.amazonaws.com"))
            .build();

    databaseSecret.grantRead(taskRole);

Ứng dụng lấy secret ở runtime bằng SDK và role của task. Không đọc secret trong CDK synthesis rồi nhúng giá trị vào environment variable của Lambda/ECS definition.

### 10.2 Secret reference trong construct

Nếu construct hỗ trợ SecretValue, có thể truyền reference thay vì plaintext:

    SecretValue dbPassword = SecretValue.secretsManager(
            "orders/prod/database",
            SecretsManagerSecretOptions.builder()
                    .jsonField("password")
                    .build());

Chỉ truyền SecretValue vào property được CDK đánh dấu hỗ trợ secret. Nếu construct yêu cầu string thông thường, ưu tiên runtime retrieval. Thay đổi secret trong Secrets Manager không phải lúc nào cũng tự kích hoạt CloudFormation update; ứng dụng nên đọc secret theo runtime và dùng rotation strategy.

### 10.3 IAM least privilege

Phân tách role:

| Role | Chủ thể assume | Quyền |
|---|---|---|
| CDK deploy role | Pipeline account/CLI | Assume deployment role ở target account |
| CloudFormation execution role | CloudFormation | Tạo/cập nhật resource cần thiết |
| Application task role | ECS/Lambda runtime | Đọc secret, truy cập table/bucket được chỉ định |
| Lookup role | CDK CLI | Read-only lookup khi synth |
| Asset publishing role | CDK CLI/pipeline | Upload file assets và container assets |

Không dùng AdministratorAccess làm runtime role. Với bootstrap execution policy, nên dùng customer-managed policy có scope phù hợp với resource mà pipeline được phép quản lý. Quyền triển khai rộng có thể cho phép pipeline tạo IAM role, policy và tài nguyên có ảnh hưởng lớn.

### 10.4 Network boundary

- Application workload chạy trong private subnet nếu không cần inbound public.
- ALB public chỉ mở listener/port cần thiết; target chỉ nhận traffic từ ALB security group.
- Database chỉ nhận traffic từ application security group.
- Dùng VPC endpoints cho S3, ECR, CloudWatch, Secrets Manager và dịch vụ cần thiết khi phù hợp.
- Kiểm tra NAT Gateway cost và egress controls.
- Dùng Network ACL như lớp subnet-level stateless; Security Group là stateful workload boundary chính.
- Dùng VPC Flow Logs và CloudTrail để hỗ trợ audit/troubleshooting.

### 10.5 Mã hóa và dữ liệu

Chọn encryption at rest cho S3, EBS, RDS, DynamoDB, EFS và log destinations theo yêu cầu. Dùng KMS customer-managed key khi cần key policy, audit hoặc tách quyền. Kiểm tra service role, application role và key policy cùng lúc; IAM allow không tự vượt qua explicit deny trong key policy/SCP.

## 11. Bootstrap nhiều account và Region

CDK phải bootstrap từng environment (account, Region) trước khi deploy. Modern bootstrap template tạo các tài nguyên staging như S3 bucket cho file assets, ECR repository cho container assets và IAM roles cho deployment, asset publishing, image publishing và lookup.

### 11.1 Bootstrap pipeline account

Giả sử pipeline nằm ở account 111111111111, Region ap-southeast-1:

    cdk bootstrap aws://111111111111/ap-southeast-1 \
      --profile platform-admin \
      --termination-protection

Pipeline account cũng phải được bootstrap vì CDK Pipelines tạo CodePipeline/CodeBuild và cần publishing/deployment resources.

### 11.2 Bootstrap target account

Staging và production cần trust pipeline account. Ví dụ:

    cdk bootstrap aws://222222222222/ap-southeast-1 \
      --profile staging-admin \
      --trust 111111111111 \
      --trust-for-lookup 111111111111 \
      --cloudformation-execution-policies arn:aws:iam::222222222222:policy/CdkCloudFormationExecutionPolicy \
      --termination-protection

    cdk bootstrap aws://333333333333/ap-southeast-1 \
      --profile prod-admin \
      --trust 111111111111 \
      --trust-for-lookup 111111111111 \
      --cloudformation-execution-policies arn:aws:iam::333333333333:policy/CdkCloudFormationExecutionPolicy \
      --termination-protection

Policy ARN trên là ví dụ; tạo policy theo resource/service mà pipeline cần quản lý và review với security team. Không mặc định dùng AdministratorAccess cho mọi target account.

### 11.3 Bootstrap thêm Region

Nếu triển khai DR ở ap-southeast-2, phải bootstrap account/Region đó:

    cdk bootstrap aws://333333333333/ap-southeast-2 \
      --profile prod-admin \
      --trust 111111111111 \
      --cloudformation-execution-policies arn:aws:iam::333333333333:policy/CdkCloudFormationExecutionPolicy \
      --termination-protection

Bootstrap là theo cặp account/Region. Bootstrap một Region không tự chuẩn bị Region khác.

### 11.4 Trust và lookup trust

- --trust: cho phép account được chỉ định thực hiện deployment vào environment; cần đi kèm --cloudformation-execution-policies.
- --trust-for-lookup: chỉ cho phép account lookup context/read-only, ví dụ CDK app dùng VPC lookup.
- Account thực hiện bootstrap luôn được tin cậy.
- Khi cập nhật trust list của bootstrap stack, phải khai báo lại toàn bộ account cần trust; chỉ thêm account mới có thể loại bỏ các account đã trust trước đó.

Chỉ thêm --trust-for-lookup khi pipeline synthesis thực sự cần lookup tài nguyên trong target account. Nếu mọi thông tin đã được khai báo tường minh và context cache đã được commit, có thể bỏ quyền lookup cross-account.

### 11.5 Bảo vệ bootstrap stack

Bootstrap stack thường có tên CDKToolkit. Không xóa stack này hoặc đổi qualifier khi pipeline đang dùng. Nếu bootstrap stack bị xóa, S3/ECR staging và IAM roles có thể mất, khiến deployment tiếp theo thất bại. Dùng termination protection, quản lý thay đổi bootstrap qua quy trình hạ tầng nền tảng và nâng cấp bằng cdk bootstrap thay vì xóa/tạo lại.

### 11.6 Cross-account artifact encryption

CDK Pipelines triển khai qua account khác cần artifact bucket dùng key phù hợp. Bật crossAccountKeys khi pipeline có deployment cross-account:

    CodePipeline pipeline = CodePipeline.Builder.create(this, "Pipeline")
            .crossAccountKeys(true)
            .synth(synthStep)
            .build();

KMS key dùng để mã hóa artifact có chi phí và lifecycle riêng. Xác minh key policy, pipeline role và target deployment roles đều được cấp quyền cần thiết.

## 12. Xây dựng CDK Pipelines bằng Java

CDK Pipelines là construct library cho continuous delivery của CDK application. Pipeline có thể deploy nhiều bản sao của Stage vào các account/Region khác nhau. Một Stage thường chứa nhiều stack thuộc cùng một release.

### 12.1 PipelineStack

Ví dụ rút gọn dùng GitHub connection và Java CDK project:

    package com.example.platform.stacks;

    import java.util.List;
    import software.amazon.awscdk.Stack;
    import software.amazon.awscdk.StackProps;
    import software.amazon.awscdk.pipelines.AddStageOpts;
    import software.amazon.awscdk.pipelines.CodePipeline;
    import software.amazon.awscdk.pipelines.CodePipelineSource;
    import software.amazon.awscdk.pipelines.ConnectionSourceOptions;
    import software.amazon.awscdk.pipelines.ManualApprovalStep;
    import software.amazon.awscdk.pipelines.ShellStep;
    import software.constructs.Construct;

    public final class PipelineStack extends Stack {
        public PipelineStack(Construct scope, String id, StackProps props) {
            super(scope, id, props);

            CodePipeline pipeline = CodePipeline.Builder.create(this, "Pipeline")
                    .crossAccountKeys(true)
                    .synth(ShellStep.Builder.create("Synth")
                            .input(CodePipelineSource.connection(
                                    "my-org/aws-multi-env",
                                    "main",
                                    ConnectionSourceOptions.builder()
                                            .connectionArn(
                                                "arn:aws:codeconnections:ap-southeast-1:111111111111:connection/EXAMPLE")
                                            .build()))
                            .commands(List.of(
                                    "npm install -g aws-cdk@2.273.0",
                                    "mvn test",
                                    "cdk synth"))
                            .build())
                    .build();
        }
    }

Thay organization/repository/branch/connection ARN bằng giá trị thật. AWS CodeStar Connections đã được đổi tên thành AWS CodeConnections; connection mới dùng ARN prefix codeconnections, còn resource cũ dùng codestar-connections vẫn được hỗ trợ. Connection ARN không phải credential, nhưng chỉ cấp quyền truy cập repository cần thiết. CDK CLI cần được cài trong synth environment; Maven compile của Java app được gọi khi CDK synth chạy.

### 12.2 Thêm dev, staging và prod

Trong PipelineStack, tạo Stage từ cấu hình đã load:

    ApplicationStage dev = new ApplicationStage(this, "Dev", devConfig);
    ApplicationStage staging = new ApplicationStage(this, "Staging", stagingConfig);
    ApplicationStage prod = new ApplicationStage(this, "Prod", prodConfig);

    pipeline.addStage(dev);

    pipeline.addStage(staging, AddStageOpts.builder()
            .post(List.of(ShellStep.Builder.create("StagingSmokeTest")
                    .commands(List.of("./scripts/smoke-test.sh staging"))
                    .build()))
            .build());

    pipeline.addStage(prod, AddStageOpts.builder()
            .pre(List.of(ManualApprovalStep.Builder.create("ApproveProduction")
                    .comment("Review staging test results and change plan")
                    .build()))
            .build());

Thứ tự Stage thể hiện promotion path. Staging smoke test chạy sau khi deploy staging; manual approval chạy trước khi pipeline promote sang production.

### 12.3 Automated validation và manual approval

Các bước validation nên gồm:

- Unit test và CDK assertions trước synth.
- Template/security scan sau synth.
- cdk diff hoặc CloudFormation change set review.
- Smoke test sau dev/staging deployment.
- Integration test với dependency thật ở staging.
- Manual approval trước production.
- Post-deploy health check và alarm verification.

Manual approval cần có người chịu trách nhiệm và tiêu chí chấp nhận rõ. Không dùng approval như cách bỏ qua automated test hoặc policy validation.

### 12.4 Self-mutating pipeline

CDK Pipelines mặc định có thể tự cập nhật định nghĩa pipeline khi source thay đổi. Commit và push source trước lần deploy đầu tiên của PipelineStack; pipeline self-mutation sẽ lấy code từ repository và có thể ghi đè cấu hình chưa commit. Khi phát triển pipeline, hiểu rõ selfMutation và execution mode để tránh hai lần deploy đồng thời tác động cùng stack.

### 12.5 Stage và Region promotion

Có thể thêm Stage ở account/Region khác nhau:

    ApplicationStage prodPrimary =
            new ApplicationStage(this, "ProdPrimary", prodPrimaryConfig);
    ApplicationStage prodDr =
            new ApplicationStage(this, "ProdDr", prodDrConfig);

Chỉ triển khai DR khi data replication, DNS failover, secret replication, KMS key, service quota và operational runbook đã sẵn sàng. Hai stack ở hai Region không tự động đồng bộ database hoặc object data chỉ vì cùng được định nghĩa trong một CDK app.

## 13. Kiểm thử CDK Java

Một CDK application cần được kiểm tra ở nhiều lớp: Java unit tests cho logic cấu hình, CDK Assertions cho CloudFormation template, static policy checks cho bảo mật và deployment tests cho hành vi thật của AWS resources.

### 13.1 Unit test cấu hình

Kiểm tra constructor từ chối account ID sai, Region rỗng, CIDR không hợp lệ và retention không hợp lệ. Việc fail sớm giúp tránh synth một template cho target không đúng.

Ví dụ loader đọc properties:

    package com.example.platform.config;

    import java.io.IOException;
    import java.io.InputStream;
    import java.nio.file.Files;
    import java.nio.file.Path;
    import java.util.Properties;

    public final class EnvironmentConfigLoader {
        private EnvironmentConfigLoader() {}

        public static EnvironmentConfig load(String name) {
            Properties properties = new Properties();
            Path path = Path.of("config", "environments.properties");

            try (InputStream input = Files.newInputStream(path)) {
                properties.load(input);
            } catch (IOException error) {
                throw new IllegalStateException("Cannot load environment config", error);
            }

            String prefix = "environment." + name + ".";
            String account = require(properties, prefix + "account");
            String region = require(properties, prefix + "region");
            String cidr = require(properties, prefix + "vpcCidr");
            int retention = Integer.parseInt(require(
                    properties,
                    prefix + "logRetentionDays"));
            String deletionProtectionValue = require(
                    properties,
                    prefix + "deletionProtection");
            if (!"true".equalsIgnoreCase(deletionProtectionValue)
                    && !"false".equalsIgnoreCase(deletionProtectionValue)) {
                throw new IllegalArgumentException(
                        "deletionProtection must be true or false");
            }
            boolean deletionProtection = Boolean.parseBoolean(deletionProtectionValue);

            return new EnvironmentConfig(
                    name, account, region, cidr, retention, deletionProtection);
        }

        private static String require(Properties properties, String key) {
            String value = properties.getProperty(key);
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException("Missing configuration: " + key);
            }
            return value.trim();
        }
    }

Loader nằm trong package com.example.platform.config và cần các import java.io.InputStream, java.io.IOException, java.nio.file.Files, java.nio.file.Path và java.util.Properties. Bổ sung validation CIDR và kiểm tra account/Region allowlist trong implementation. Với pipeline, file config nên được lấy từ commit đang build; không đọc config tùy ý từ máy người chạy.

### 13.2 CDK Assertions

Ví dụ kiểm tra VPC và subnet:

    package com.example.platform;

    import com.example.platform.config.EnvironmentConfig;
    import com.example.platform.stacks.NetworkStack;
    import java.util.Map;
    import org.junit.jupiter.api.Test;
    import software.amazon.awscdk.App;
    import software.amazon.awscdk.assertions.Template;

    public class NetworkStackTest {
        @Test
        void createsExpectedNetworkResources() {
            App app = new App();
            EnvironmentConfig config = new EnvironmentConfig(
                    "test",
                    "111111111111",
                    "ap-southeast-1",
                    "10.10.0.0/16",
                    7,
                    false);

            NetworkStack stack = new NetworkStack(app, "Network", config);
            Template template = Template.fromStack(stack);

            template.resourceCountIs("AWS::EC2::VPC", 1);
            template.resourceCountIs("AWS::EC2::Subnet", 6);
            template.hasResourceProperties(
                    "AWS::EC2::VPC",
                    Map.of("CidrBlock", "10.10.0.0/16"));
        }
    }

Số subnet trong test phụ thuộc maxAzs và subnetConfiguration. Nếu thay đổi kiến trúc, cập nhật expectation có chủ đích. Không snapshot toàn bộ template cho mọi test; ưu tiên assertion tập trung vào security, encryption, network isolation, deletion policy và critical properties.

### 13.3 Kiểm thử security policy

Có thể dùng:

- cdk-nag để kiểm tra các rule bảo mật và compliance trong construct tree.
- CloudFormation Guard hoặc policy-as-code scanner để kiểm tra template.
- IAM policy review để phát hiện wildcard action/resource không cần thiết.
- Dependency/image scanner cho code và container assets.
- AWS Config/Security Hub ở account đích để kiểm tra trạng thái runtime.

CDK synth thành công không có nghĩa thiết kế an toàn. Static policy test nên chạy trước khi pipeline promote.

### 13.4 Integration tests

Unit test không tạo resource thật. Integration test nên chạy trong account sandbox hoặc staging để xác minh:

- VPC/subnet/route thực sự được tạo.
- ECS/Lambda truy cập được dependency.
- KMS key policy cho phép workload đúng role.
- Secret rotation không làm gián đoạn ứng dụng.
- Alarm và log group nhận dữ liệu.
- Backup/restore hoặc failover hoạt động.

Integration test có thể tốn chi phí và tạo resource lâu dài; cần tag, TTL/cleanup và giới hạn account.

## 14. Quy trình synth, diff và deploy

### 14.1 Các lệnh thường dùng

    cdk ls
    cdk synth NetworkStack
    cdk diff NetworkStack --profile dev
    cdk deploy NetworkStack --profile dev
    cdk deploy ApplicationStack --profile dev

Tên stack phải khớp stack ID được sinh trong App/Stage. Với Stage pipeline, deployment thường do CDK Pipelines điều khiển. Khi deploy local, chỉ chỉ định stack/environment dự kiến; tránh dùng cdk deploy --all khi app có cả production và dev stacks.

### 14.2 Synth

cdk synth tạo CloudFormation templates và Cloud Assembly. Review:

- Resource types và logical IDs.
- IAM policy và trust relationship.
- Public access, security group ingress/egress.
- Encryption, KMS key và bucket policy.
- Retention, backup, deletion policy và termination protection.
- Parameters/outputs và cross-stack references.
- Asset size, Docker image và file asset manifest.

Template synth là bằng chứng quan trọng để review trước khi thay đổi AWS.

### 14.3 Diff

cdk diff so sánh template hiện tại với template mới để hiển thị resource sẽ thêm, sửa hoặc xóa. Đọc kỹ thay đổi replacement, deletion, IAM policy broadening, subnet/route, database, encryption key và retention.

Với production, dùng CloudFormation change set/pipeline review để kiểm tra kế hoạch cập nhật. Một diff đơn giản không thay thế đánh giá tác động dữ liệu, downtime hoặc service quota.

### 14.4 Deploy có kiểm soát

- Dùng credential ngắn hạn qua IAM Identity Center/assume role hoặc pipeline role.
- Kiểm tra caller identity và target account/Region trước deployment.
- Yêu cầu approval khi thay đổi có rủi ro cao.
- Dùng cdk deploy --require-approval broadening để yêu cầu phê duyệt khi quyền IAM được mở rộng.
- Giới hạn quyền deploy theo environment.
- Lưu template, Cloud Assembly, diff và deployment execution ID.

### 14.5 Không dùng deploy làm cơ chế quản lý secret

Không truyền password qua command line, shell history hoặc CDK context. Không ghi secret vào CloudFormation parameter plaintext. Runtime nên đọc secret từ Secrets Manager/SSM bằng role riêng.

## 15. Quản lý drift, update và rollback

### 15.1 CloudFormation drift

Drift xảy ra khi resource thực tế bị sửa ngoài CloudFormation/CDK, ví dụ console change, CLI update hoặc service automation. CloudFormation drift detection chỉ kiểm tra resource/property được hỗ trợ và không phát hiện mọi thay đổi runtime.

Quy trình xử lý:

1. Chạy drift detection trên stack.
2. Xác định resource/property bị lệch.
3. Tìm actor và lý do thay đổi qua CloudTrail/change history.
4. Quyết định đưa thay đổi vào code hay khôi phục trạng thái theo template.
5. Synth/diff lại trước khi deploy.

Không tự động overwrite drift mà chưa biết vì sao thay đổi được thực hiện; có thể làm mất hotfix hoặc thay đổi cần thiết.

### 15.2 CloudFormation rollback

Khi stack update thất bại, CloudFormation có thể rollback về trạng thái trước đó. Xem stack events và resource status để xác định resource đầu tiên thất bại. Một số lỗi do custom resource, quota, IAM hoặc replacement không thể sửa chỉ bằng cách retry.

### 15.3 Rollback ứng dụng và dữ liệu

Rollback infrastructure không đồng nghĩa rollback data. Khi đổi schema database hoặc format S3, cần migration backward-compatible:

- Expand: thêm field/table/index mới mà phiên bản cũ vẫn chạy được.
- Migrate: chuyển dữ liệu theo batch và kiểm tra completeness.
- Switch: deploy code mới đọc/ghi schema mới.
- Contract: chỉ xóa schema cũ sau khi không còn consumer.

Với release rủi ro cao, dùng canary/blue-green hoặc traffic shifting thay vì thay toàn bộ workload cùng lúc.

### 15.4 RemovalPolicy và termination protection

RemovalPolicy.RETAIN giữ resource sau khi stack bị xóa; DESTROY xóa resource theo CloudFormation lifecycle nếu service hỗ trợ. Termination protection ngăn xóa toàn stack ngoài ý muốn. Hai cơ chế khác nhau và nên được cấu hình riêng cho production data, network và bootstrap stack.

Không dựa vào termination protection để bảo vệ từng resource; cũng không dựa vào RemovalPolicy để bảo vệ toàn bộ stack.

## 16. Multi-Region và disaster recovery

### 16.1 Cùng code, cấu hình riêng theo Region

Một Stage có thể deploy vào Region khác nếu dịch vụ và construct hỗ trợ. Tuy nhiên, không phải resource nào cũng có behavior giống nhau giữa các Region:

- Service availability và feature parity.
- AZ count và subnet capacity.
- Instance type/quota.
- KMS key và secret scope.
- Domain/certificate/DNS.
- Data replication và consistency.
- Pricing và data transfer.

Kiểm tra AWS service availability và quota trước khi đưa Region mới vào pipeline.

### 16.2 Phân loại dữ liệu và RPO/RTO

| Kiểu dữ liệu | Chiến lược DR gợi ý |
|---|---|
| Stateless compute | Re-deploy bằng CDK tại Region DR |
| S3 objects | Cross-Region Replication nếu phù hợp |
| DynamoDB | Global Tables hoặc backup/restore theo RPO |
| RDS | Cross-Region read replica hoặc snapshot copy |
| Secrets Manager | Secret replication và key access |
| KMS | Tạo key riêng tại Region DR, thiết kế policy tương ứng |
| DNS | Health check/failover policy và runbook |

RPO là lượng dữ liệu có thể mất; RTO là thời gian mục tiêu để khôi phục. CDK chỉ tạo resource/configuration, không tự đảm bảo replication, failover hay consistency.

### 16.3 Cross-Region references

CloudFormation exports/imports thông thường gắn với cùng account và Region. Nếu cần chia sẻ thông tin giữa Region, cân nhắc SSM Parameter Store, DNS, resource replication, pipeline outputs hoặc cơ chế cross-region reference được CDK hỗ trợ và hiểu rõ giới hạn. Tránh tạo dependency ngược khiến một Region không thể deploy độc lập khi Region kia gặp sự cố.

### 16.4 DR drill

Thực hiện diễn tập định kỳ:

1. Kiểm tra stack và bootstrap resources ở Region DR.
2. Xác minh image, secret, KMS, network và service quota.
3. Khôi phục data từ replica/backup.
4. Chạy smoke/integration tests.
5. Chuyển DNS/traffic theo runbook.
6. Đo RTO/RPO thực tế.
7. Fail back hoặc tiếp tục vận hành ở Region DR theo kế hoạch.

## 17. Cost governance và resource lifecycle

CDK tạo hạ tầng; cost phụ thuộc resource, traffic, storage, data transfer và thời gian tồn tại. Hãy thiết kế cost control ngay trong cấu hình:

- Tag owner, environment, cost center và application.
- NAT Gateway, KMS key, load balancer, EKS cluster và log ingestion có thể tạo chi phí liên tục.
- Đặt retention cho log và lifecycle cho S3.
- Chọn NAT/VPC endpoint theo traffic pattern.
- Dùng instance sizing và autoscaling phù hợp.
- Dùng deletion protection/retain ở production và cleanup policy ở dev.
- Tạo AWS Budgets/Cost Anomaly Detection và alarm theo environment.
- Tách account giúp phân bổ cost và giới hạn blast radius.

Dev environment có thể tự động tắt compute ngoài giờ hoặc xóa stack lab có TTL. Không tự động xóa network/data/shared resource mà không có ownership và approval.

## 18. Case study: nền tảng đơn hàng ba môi trường

### 18.1 Yêu cầu

Một doanh nghiệp xây dựng Orders API phục vụ website và mobile app. API nhận đơn hàng, đọc/ghi DynamoDB, lưu file hóa đơn vào S3 và phát event cho hệ thống downstream. Tổ chức yêu cầu:

- Dev, staging và prod chạy ở account riêng.
- Mỗi môi trường có network isolation.
- Staging gần giống production để test.
- Production có deletion protection, backup, log retention và alarm.
- Deploy từ source repository qua pipeline.
- Production chỉ được cập nhật sau khi staging smoke test và reviewer approval thành công.
- Có Region DR và runbook khôi phục.

### 18.2 Thiết kế stack

| Stack | Resource | Ghi chú |
|---|---|---|
| NetworkStack | VPC, public/private/isolated subnets, endpoints | Mỗi account tự quản |
| SecurityStack | KMS keys, IAM roles, security baseline | Policy theo environment |
| DataStack | DynamoDB table, S3 bucket, backup | Production retain/PITR |
| ApplicationStack | ALB, ECS Fargate service, task role | Image digest theo release |
| ObservabilityStack | Log groups, alarms, dashboard | Retention theo policy |

Stage của mỗi environment tạo các stack trên và truyền resource references trong cùng account/Region. PipelineStack nằm ở tooling/dev account; target account staging/prod trust pipeline account qua bootstrap.

### 18.3 Environment matrix

| Setting | Dev | Staging | Prod |
|---|---|---|---|
| VPC CIDR | 10.10.0.0/16 | 10.20.0.0/16 | 10.30.0.0/16 |
| AZ | 2 | 2 | 2 |
| NAT | 1 | 1 | 2 hoặc endpoints theo traffic |
| ECS desired count | 1 | 2 | Theo load test/SLO |
| DynamoDB | On-demand | On-demand | Theo capacity/cost model |
| PITR | Bật theo nhu cầu | Bật | Bật |
| Deletion protection | Tắt | Bật | Bật |
| Log retention | 7 ngày | 30 ngày | Theo compliance |
| Deploy approval | Không | UAT | Bắt buộc |

Các giá trị là ví dụ để thảo luận, không phải sizing production. Dùng load test, availability target, traffic forecast và cost model để chọn thông số thật.

### 18.4 Deployment path

1. Developer tạo pull request.
2. CI chạy Maven tests, CDK assertions, cdk synth và security scan.
3. Pipeline triển khai Dev.
4. Smoke test kiểm tra health endpoint, IAM access và DynamoDB/S3 path.
5. Pipeline triển khai Staging.
6. Integration/UAT test chạy trên dữ liệu synthetic.
7. Reviewer xem diff, test results, security findings và approve production.
8. Pipeline triển khai Prod theo change set.
9. Post-deploy smoke test và CloudWatch alarms xác nhận health.
10. Nếu lỗi vượt threshold, rollback application version và mở incident.

### 18.5 Acceptance criteria

- Ba Stage synth ra stack với account/Region đúng.
- Không có secret plaintext trong source, context hoặc synthesized template.
- Production resource có encryption, backup, retain policy và termination protection phù hợp.
- IAM task role chỉ truy cập đúng table, bucket và secret.
- Pipeline chỉ deploy staging/prod sau bootstrap trust.
- Staging tests pass trước manual approval.
- Production deployment có audit trail, change set và rollback plan.
- DR Region có data replication, secret/key access và runbook được test.

## 19. Lab A: tạo CDK Java app cho dev và staging

### Mục tiêu

Khởi tạo project Java CDK v2, tạo EnvironmentConfig, Stage và NetworkStack dùng chung cho hai môi trường.

### Bước 1: khởi tạo

    mkdir aws-multi-env-lab
    cd aws-multi-env-lab
    cdk init app --language java

Xác minh Java/Maven/CDK CLI:

    java -version
    mvn -version
    cdk --version

### Bước 2: tạo cấu hình

Tạo environments.properties với hai account sandbox và Region lab. Dùng CIDR không trùng với VPC hiện hữu. Không ghi access key hoặc password vào file.

### Bước 3: tạo EnvironmentConfig

1. Viết class bất biến.
2. Validate account ID, Region, CIDR và retention.
3. Viết EnvironmentConfigLoader.
4. Viết unit test cho trường hợp hợp lệ và invalid input.

### Bước 4: tạo Stage và Stack

1. Tạo NetworkStack với VPC và subnet.
2. Tạo ApplicationStage nhận EnvironmentConfig.
3. Tạo hai Stage Dev và Staging.
4. Thêm environment account/Region cho từng Stage.
5. Thêm tags và termination protection cho staging nếu phù hợp.

### Bước 5: test và synth

    mvn test
    cdk ls
    cdk synth

Review Cloud Assembly, xác nhận hai environment có cấu hình đúng và không có secret. Chưa deploy cho đến khi account/Region và bootstrap đã được kiểm tra.

## 20. Lab B: bootstrap và deploy cross-account

### Mục tiêu

Chuẩn bị pipeline account và target account, cấu hình trust và triển khai stack thử nghiệm qua account boundary.

### Bước 1: xác minh caller identity

    aws sts get-caller-identity --profile platform-admin
    aws sts get-caller-identity --profile staging-admin

Xác minh account ID thực tế khớp với môi trường đã khai báo.

### Bước 2: bootstrap pipeline account

    cdk bootstrap aws://111111111111/ap-southeast-1 \
      --profile platform-admin \
      --termination-protection

### Bước 3: bootstrap target account

    cdk bootstrap aws://222222222222/ap-southeast-1 \
      --profile staging-admin \
      --trust 111111111111 \
      --cloudformation-execution-policies arn:aws:iam::222222222222:policy/CdkCloudFormationExecutionPolicy \
      --termination-protection

Thay account/policy ARN bằng giá trị sandbox thật. Policy phải được tạo và review trước. Không dùng AdministratorAccess chỉ để làm lab nhanh nếu có thể cấp policy tối thiểu phù hợp.

### Bước 4: diff và deploy

    cdk diff NetworkStack --profile staging-admin
    cdk deploy NetworkStack --profile staging-admin

Kiểm tra CloudFormation stack, VPC/subnet, tags và CloudTrail events. Sau đó deploy application stack nếu lab đã định nghĩa.

### Bước 5: kiểm tra trust và cleanup

1. Xác minh pipeline account có thể assume deployment role.
2. Xác minh một principal không được trust bị AccessDenied.
3. Xác nhận bootstrap stack có termination protection.
4. Xóa stack lab nếu không còn dùng; giữ bootstrap stack cho các lab tiếp theo.

## 21. Lab C: tạo CDK Pipeline có approval cho production

### Mục tiêu

Tạo CodePipeline bằng CDK Pipelines, deploy dev → staging → prod và yêu cầu manual approval trước production.

### Bước 1: tạo source connection

1. Tạo AWS CodeConnections connection tới repository.
2. Hoàn tất OAuth/installation ở source provider.
3. Lưu connection ARN trong pipeline configuration.
4. Không lưu token cá nhân trong source code.

### Bước 2: tạo PipelineStack

1. Tạo CodePipeline với ShellStep synth.
2. Cài AWS CDK CLI cùng version đã khóa với project trong synth environment.
3. Chạy Maven tests.
4. Chạy cdk synth.
5. Bật crossAccountKeys nếu deploy cross-account.

### Bước 3: thêm Stage

1. Tạo ApplicationStage Dev.
2. Thêm post step smoke test.
3. Tạo ApplicationStage Staging.
4. Thêm integration test/UAT.
5. Tạo ApplicationStage Prod.
6. Thêm ManualApprovalStep ở pre steps của Prod.

### Bước 4: triển khai pipeline

1. Commit và push source.
2. Bootstrap pipeline account và target accounts.
3. Deploy PipelineStack lần đầu bằng profile/role có quyền.
4. Xác minh self-mutation và source revision.
5. Tạo một thay đổi nhỏ trong app và theo dõi promotion qua các Stage.

### Bước 5: kiểm thử gate

Thử để staging test thất bại và xác nhận pipeline không promote. Sau đó sửa test, chạy lại và xác nhận production chỉ tiếp tục sau approval. Lưu execution ID, commit SHA và deployment history.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Một CDK environment được xác định bởi hai giá trị nào?

**Đáp án:** AWS account và AWS Region.

**Câu 2.** CDK App, Construct, Stack và Stage khác nhau thế nào?

**Đáp án:** App là root; Construct mô hình hóa tài nguyên; Stack tạo CloudFormation template; Stage gom một hoặc nhiều stack thành một bản triển khai environment.

**Câu 3.** Vì sao nên tách NetworkStack và ApplicationStack?

**Đáp án:** Hai lớp có ownership/lifecycle và quyền thay đổi khác nhau; tách giúp giảm blast radius và quản lý dependency rõ hơn.

**Câu 4.** Environment-specific stack có lợi thế gì?

**Đáp án:** CDK biết account/Region lúc synth nên dùng được context lookup và logic phụ thuộc environment.

**Câu 5.** Hạn chế của environment-agnostic stack là gì?

**Đáp án:** Không thể dùng các lookup/logic cần account, Region hoặc AZ cụ thể khi synth.

**Câu 6.** Vì sao phải commit cdk.context.json?

**Đáp án:** Context lookup được cache; commit file giúp local và CI dùng cùng giá trị, tránh template thay đổi bất ngờ.

**Câu 7.** CDK bootstrap tạo những loại tài nguyên nào?

**Đáp án:** S3 staging bucket, ECR repository và IAM roles hỗ trợ deployment, asset publishing, image publishing và lookup.

**Câu 8.** Vì sao phải bootstrap từng account/Region?

**Đáp án:** Bootstrap resources được tạo trong từng environment; bootstrap một Region không chuẩn bị Region khác.

**Câu 9.** --trust khác --trust-for-lookup thế nào?

**Đáp án:** --trust cấp quyền deployment cross-account; --trust-for-lookup chỉ cấp quyền lookup/read-only context.

**Câu 10.** Khi cập nhật bootstrap trust list, cần lưu ý gì?

**Đáp án:** Phải khai báo lại toàn bộ account cần trust; nếu chỉ thêm account mới, account cũ có thể bị loại khỏi danh sách.

**Câu 11.** Vì sao không nên xóa CDKToolkit stack?

**Đáp án:** Stack chứa S3/ECR staging và IAM roles mà pipeline cần; xóa có thể làm deployment tiếp theo thất bại.

**Câu 12.** Vì sao CDK Pipelines dùng crossAccountKeys?

**Đáp án:** Để mã hóa artifact bucket bằng KMS khi pipeline deploy cross-account; cần tính thêm chi phí key.

**Câu 13.** CDK Pipelines Stage đại diện cho điều gì?

**Đáp án:** Một bản triển khai ứng dụng gồm một hoặc nhiều stack trong một environment.

**Câu 14.** ManualApprovalStep nên đặt ở đâu trước production?

**Đáp án:** Trong pre steps của production Stage để approval diễn ra trước khi deploy stack.

**Câu 15.** Vì sao phải commit/push trước lần deploy đầu tiên của self-mutating pipeline?

**Đáp án:** Pipeline tự cập nhật theo source repository; code chưa commit có thể bị pipeline bỏ qua hoặc ghi đè.

**Câu 16.** Vì sao không dùng SecretValue.unsafePlainText cho password?

**Đáp án:** Plaintext có thể xuất hiện trong source, synthesized template hoặc CloudFormation console.

**Câu 17.** Template.fromStack dùng để làm gì?

**Đáp án:** Tạo đối tượng CDK Assertions từ CloudFormation template synth của stack để kiểm thử resource và properties.

**Câu 18.** cdk diff có thay thế change set review production không?

**Đáp án:** Không. Diff là công cụ phát hiện thay đổi; production vẫn cần review change set, replacement, deletion và tác động dữ liệu.

**Câu 19.** CloudFormation drift detection có phát hiện mọi thay đổi runtime không?

**Đáp án:** Không. Chỉ phát hiện resource/property được hỗ trợ; cần kết hợp CloudTrail và kiểm tra vận hành.

**Câu 20.** Vì sao rollback infrastructure không đủ khi database schema đã thay đổi?

**Đáp án:** Data migration có thể không đảo ngược; cần migration backward-compatible, backup và kế hoạch rollback dữ liệu riêng.

## 23. Checklist production readiness

- [ ] Account ID và Region của mọi Stage đã được xác minh.
- [ ] Cấu hình environment được validate và không fallback âm thầm.
- [ ] CDK CLI, aws-cdk-lib và constructs versions được khóa tương thích.
- [ ] cdk.json và cdk.context.json được commit.
- [ ] Stack boundaries phản ánh ownership/lifecycle.
- [ ] Cross-stack references chỉ dùng trong account/Region phù hợp.
- [ ] CIDR không overlap với mạng hiện hữu.
- [ ] Public/private/isolated subnet và routing được review.
- [ ] IAM roles theo least privilege.
- [ ] Secret nằm trong Secrets Manager/SSM, không trong source/template.
- [ ] KMS key policy và runtime roles được kiểm thử.
- [ ] Production data có backup/PITR/retention phù hợp.
- [ ] RemovalPolicy và termination protection được cấu hình rõ.
- [ ] Resource tags có owner, environment và cost center.
- [ ] Bootstrap từng account/Region đã hoàn tất.
- [ ] Bootstrap stack có termination protection.
- [ ] Cross-account trust và CloudFormation execution policy đã review.
- [ ] Bootstrap qualifier và stack lifecycle được bảo vệ.
- [ ] Pipeline artifact encryption/crossAccountKeys được cấu hình nếu cần.
- [ ] Pipeline source connection được giới hạn quyền.
- [ ] Pipeline synth chạy Maven tests và cdk synth.
- [ ] CDK assertions và security/policy scans pass.
- [ ] Dev/staging smoke/integration tests pass.
- [ ] Production manual approval có owner và tiêu chí.
- [ ] Change set/diff được review trước production.
- [ ] Drift detection và CloudTrail audit có owner.
- [ ] Rollback application và data migration được kiểm thử.
- [ ] Multi-Region replication, KMS, secrets và DNS failover được kiểm tra.
- [ ] RPO/RTO có mục tiêu và DR drill định kỳ.
- [ ] Cost budget, alarms và cleanup policy được thiết lập.

## 24. Tài liệu tham khảo chính thức

1. [Working with the AWS CDK in Java](https://docs.aws.amazon.com/cdk/v2/guide/work-with-cdk-java.html) — khởi tạo project, Maven và Java idioms.
2. [AWS CDK projects](https://docs.aws.amazon.com/cdk/v2/guide/projects.html) — cấu trúc project Java và cdk.json.
3. [Environments for the AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/environments.html) — khái niệm account/Region.
4. [Configure environments to use with the AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/configure-env.html) — environment-specific và environment-agnostic stacks.
5. [Context values and the AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/context.html) — context lookup và repeatable synthesis.
6. [Bootstrap your environment for use with the AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping-env.html) — modern bootstrap resources và roles.
7. [Customize AWS CDK bootstrapping](https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping-customizing.html) — trust và execution policies.
8. [cdk bootstrap command reference](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-bootstrap.html) — bootstrap CLI options.
9. [Deploying AWS CDK applications](https://docs.aws.amazon.com/cdk/v2/guide/deploy.html) — credentials, bootstrap và deployment.
10. [CDK Pipelines](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.pipelines-readme.html) — Java pipeline, Stage, ShellStep và approval.
11. [Testing AWS CDK applications](https://docs.aws.amazon.com/cdk/v2/guide/testing.html) — unit tests và assertions.
12. [CDK Assertions](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.assertions-readme.html) — Template, Match và resource assertions.
13. [SecretValue Java API](https://docs.aws.amazon.com/cdk/api/v2/java/software/amazon/awscdk/SecretValue.html) — secret references và tránh plaintext.
14. [Get a value from AWS Secrets Manager](https://docs.aws.amazon.com/cdk/v2/guide/get-secrets-manager-value.html) — import/reference secret trong CDK.
15. [AWS CDK Construct Library](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib-readme.html) — constructs, props và secret handling.
16. [Amazon VPC Construct Library](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2-readme.html) — VPC, subnet và fromLookup.
17. [CDK Pipelines cross-account deployment](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.pipelines-readme.html) — crossAccountKeys và target environments.
18. [AWS CDK CLI reference](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd.html) — synth, diff, deploy và destroy.
19. [AWS CloudFormation drift detection](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html) — phát hiện drift.
20. [AWS CDK best practices](https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html) — cấu trúc app, constructs và lifecycle.
21. [DynamoDB Table.Builder Java API](https://docs.aws.amazon.com/cdk/api/v2/java/software/amazon/awscdk/services/dynamodb/Table.Builder.html) — cấu hình table và point-in-time recovery specification.
22. [AWS CodeConnections](https://docs.aws.amazon.com/dtconsole/latest/userguide/welcome-connections.html) — tạo và quản lý connection tới repository.

---

**Kết luận:** CDK Java giúp chuẩn hóa hạ tầng nhiều môi trường bằng cách dùng chung construct/stack và truyền cấu hình account/Region một cách có chủ đích. Một capstone production-ready cần nhiều hơn code tạo resource: phải có bootstrap/trust đúng, IAM least privilege, secret management, context repeatability, test template, pipeline promotion, approval, drift handling, rollback và DR. Hãy synth và review trước mỗi deployment, triển khai tuần tự từ dev qua staging tới production, đồng thời giữ data migration và recovery plan độc lập với rollback CloudFormation.
