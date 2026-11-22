# Triển khai Spring Boot với RDS và Secrets Manager

Bài thực hành xây dựng một REST API bằng Spring Boot kết nối tới PostgreSQL trên Amazon RDS. Database credentials được lưu trong AWS Secrets Manager và được nạp vào Spring Environment khi ứng dụng khởi động. HikariCP quản lý JDBC connection pool; IAM, VPC, security group và TLS bảo vệ đường truy cập.

Bài học thuộc chương **Bài thực hành nền tảng** của module CLOUD_PROVIDERS_AWS. Module khám phá hệ sinh thái AWS từ Region/AZ, IAM, VPC đến compute, storage, database, integration và serverless; người học rèn khả năng chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

- Phân biệt trách nhiệm của Spring Boot, Amazon RDS, AWS Secrets Manager, IAM và VPC.
- Tạo RDS for PostgreSQL trong private subnet và giới hạn kết nối bằng security group.
- Tạo database user riêng cho ứng dụng với quyền tối thiểu.
- Lưu credentials theo JSON secret structure chuẩn cho RDS PostgreSQL.
- Tích hợp Spring Cloud AWS Secrets Manager bằng Spring Boot Config Data import.
- Dùng IAM role/default credentials provider chain thay cho access key nhúng trong source.
- Cấu hình PostgreSQL JDBC, HikariCP và TLS có xác minh chứng chỉ.
- Kiểm thử REST API, database connection và secret retrieval.
- Hiểu rotation, tác động tới connection pool và vai trò của RDS Proxy.
- Chẩn đoán lỗi IAM, DNS, network, TLS, secret format và database authentication.
- Dọn dẹp tài nguyên lab để tránh chi phí không cần thiết.

## 1. Kiến trúc và luồng dữ liệu

Ứng dụng mẫu là REST API quản lý khách hàng. Ứng dụng chạy trong cùng VPC với RDS hoặc được kết nối tới VPC qua một đường mạng riêng được kiểm soát.

~~~mermaid
flowchart TB
    U[Client / REST API] --> APP[Spring Boot application]
    APP --> H[HikariCP / JDBC]
    H --> DB[(Amazon RDS PostgreSQL)]
    APP --> SM[AWS Secrets Manager]
    APP --> IAM[IAM workload role]
    IAM --> SM
    SM --> KMS[AWS KMS encryption]
    subgraph VPC[Application VPC]
      APP
      H
      DB
      EP[Secrets Manager VPC endpoint]
    end
    APP --> EP
    EP --> SM
~~~

**Luồng khởi động:**

1. Spring Boot đọc application.yml.
2. Spring Cloud AWS xử lý spring.config.import và gọi Secrets Manager bằng AWS SDK for Java 2.x.
3. Secrets Manager trả về SecretString dạng JSON.
4. Các key cấp cao nhất trong JSON được thêm vào Spring Environment.
5. Spring Boot resolve db.host, db.username và db.password để cấu hình DataSource.
6. HikariCP tạo connection tới RDS PostgreSQL qua TCP 5432 và TLS.
7. Controller dùng JdbcTemplate để chạy SQL.

Secrets Manager không nằm trên đường đi của mỗi câu SQL. Secret được lấy khi ứng dụng nạp configuration hoặc khi cơ chế reload được bật; không cần gọi Secrets Manager cho từng query.

## 2. Chọn phiên bản và công nghệ

Ví dụ dùng bộ phiên bản tương thích của hệ sinh thái Spring:

| Thành phần | Phiên bản / lựa chọn |
|---|---|
| Java | Java 21 LTS |
| Spring Boot | 4.0.10 |
| Spring Cloud AWS | 4.2.0 |
| AWS SDK | AWS SDK for Java 2.x do BOM quản lý |
| Database | Amazon RDS for PostgreSQL |
| JDBC driver | PostgreSQL JDBC |
| Connection pool | HikariCP (Spring Boot JDBC auto-configuration) |
| Secret | AWS Secrets Manager JSON SecretString |
| Region ví dụ | ap-southeast-1 |

Spring Cloud AWS 4.x thuộc dòng tương thích Spring Boot 4.0.x. Không ghép ngẫu nhiên Spring Cloud AWS 3.x với Spring Boot 4.x hoặc nâng riêng một module AWS SDK mà không kiểm tra BOM. Nếu dự án dùng Spring Boot 4.1.x hoặc patch line khác, kiểm tra compatibility matrix của Spring Cloud AWS trước khi chọn phiên bản. Dùng Spring Cloud AWS BOM để khóa dependency AWSpring ở một bộ đã được kiểm thử cùng nhau.

**Tại sao dùng PostgreSQL?**

- RDS for PostgreSQL hỗ trợ JDBC và TLS.
- Có thể tạo role riêng cho ứng dụng và cấp quyền theo schema/table.
- Secrets Manager có JSON structure chuẩn cho PostgreSQL.
- Có thể áp dụng rotation Lambda, RDS Proxy và IAM authentication trong các bước nâng cao.

## 3. Chuẩn bị tài khoản và môi trường

Bạn cần:

- AWS account có quyền tạo RDS, Secrets Manager, IAM, VPC/security group và EC2 hoặc môi trường chạy ứng dụng.
- AWS CLI v2 đã cài đặt và cấu hình.
- Java 21 và Maven hoặc Maven Wrapper.
- psql hoặc công cụ quản trị PostgreSQL.
- Quyền truy cập mạng riêng tới RDS, ví dụ chạy ứng dụng trong VPC, VPN/Client VPN hoặc môi trường phát triển được kết nối vào VPC.
- Một Region thống nhất cho RDS, secret, IAM role, VPC endpoint và ứng dụng.

Đặt biến ví dụ trong terminal:

~~~bash
export AWS_REGION=ap-southeast-1
export DB_IDENTIFIER=spring-rds-lab
export SECRET_NAME=/lab/spring-rds/db
~~~

PowerShell:

~~~powershell
$env:AWS_REGION = "ap-southeast-1"
$env:AWS_PROFILE = "dev"
$DB_IDENTIFIER = "spring-rds-lab"
$SECRET_NAME = "/lab/spring-rds/db"
~~~

Đăng nhập bằng IAM Identity Center nếu tổ chức sử dụng SSO:

~~~bash
aws configure sso
aws sso login --profile dev
aws sts get-caller-identity --profile dev
export AWS_PROFILE=dev
~~~

PowerShell có thể đặt profile tương ứng bằng biến môi trường AWS_PROFILE = dev để các lệnh AWS CLI tiếp theo dùng đúng phiên SSO.

Không tạo access key dài hạn chỉ để hoàn thành lab nếu có thể dùng SSO hoặc IAM role. Không đặt access key, database password hay secret JSON vào Git.

## 4. Thiết kế mạng trước khi tạo database

RDS nên ở private subnet và không nhận kết nối trực tiếp từ internet.

~~~mermaid
flowchart TB
    subgraph VPC["VPC 10.20.0.0/16"]
      subgraph PUB["Public subnet (chỉ khi cần app host/bastion)"]
        EC2[EC2 app host / SSM]
      end
      subgraph PRIV["Private database subnets"]
        RDS[(RDS PostgreSQL)]
      end
      EP[Interface endpoint: Secrets Manager]
    end
    EC2 -->|TCP 5432| RDS
    EC2 -->|HTTPS 443| EP
    EP --> SM[AWS Secrets Manager]
~~~

### 4.1. Security group

Tạo hai security group riêng:

| Security group | Inbound | Outbound |
|---|---|---|
| sg-spring-app | Không cần inbound nếu quản trị qua Systems Manager Session Manager | TCP 5432 tới sg-rds; HTTPS 443 tới endpoint hoặc AWS service |
| sg-rds-postgres | TCP 5432, source là sg-spring-app | Theo nhu cầu mặc định của VPC |

Không cấu hình inbound PostgreSQL từ 0.0.0.0/0. Không dùng public IP của máy cá nhân làm giải pháp lâu dài cho database. Security group tham chiếu security group khác giúp policy theo workload thay vì phụ thuộc IP động.

### 4.2. Kết nối Secrets Manager từ private subnet

Nếu ứng dụng ở private subnet không có NAT/egress tới public AWS endpoint, tạo interface VPC endpoint cho Secrets Manager:

- Service name: com.amazonaws.ap-southeast-1.secretsmanager.
- Bật Private DNS.
- Chọn subnet trong các Availability Zone cần dùng.
- Gắn endpoint security group cho phép TCP 443 từ sg-spring-app.
- Có thể dùng endpoint policy để giới hạn secret được phép truy cập.

Nếu dùng EC2 private subnet để quản trị bằng Session Manager, cần các VPC endpoint hoặc đường egress phù hợp cho Systems Manager. Không nhầm endpoint Secrets Manager với endpoint RDS: ứng dụng kết nối database bằng endpoint DNS của RDS qua security group.

### 4.3. Ma trận luồng mạng

| Nguồn | Đích | Port | Mục đích |
|---|---|---:|---|
| Spring Boot host | RDS endpoint | 5432/TCP | JDBC PostgreSQL |
| Spring Boot host | Secrets Manager endpoint | 443/TCP | Nạp secret |
| Rotation Lambda | RDS endpoint | 5432/TCP | Kiểm tra/cập nhật password |
| Rotation Lambda | Secrets Manager endpoint | 443/TCP | Đọc và cập nhật secret |
| Operator | EC2 app host | Qua SSM | Quản trị không mở SSH inbound |



## 5. Tạo RDS for PostgreSQL

Trong AWS Console:

1. Mở Amazon RDS, chọn đúng Region.
2. Chọn Databases → Create database.
3. Chọn Standard create để chủ động cấu hình mạng, backup, encryption và availability.
4. Engine: PostgreSQL. Chọn engine version còn được AWS hỗ trợ tại Region.
5. DB instance identifier: spring-rds-lab.
6. Master username: ví dụ dbadmin.
7. Chọn Manage master credentials in AWS Secrets Manager để RDS quản lý master password; không tự đặt password trong source hoặc file cấu hình ứng dụng.
8. Chọn VPC của lab, DB subnet group chứa private subnets ở ít nhất hai Availability Zone và Public access = No. DB subnet group phải đáp ứng yêu cầu AZ của RDS ngay cả khi lab chọn Single-AZ.
9. Chọn security group sg-rds-postgres.
10. Bật storage encryption. Chọn KMS key theo policy của tổ chức.
11. Với lab có thể dùng Single-AZ và class nhỏ phù hợp quota/budget. Production cần đánh giá Multi-AZ, backup retention, maintenance window, storage autoscaling và failover.
12. Tạo database và đợi trạng thái Available.

Sau khi RDS sẵn sàng, ghi lại DB instance identifier, endpoint DNS, port PostgreSQL (mặc định 5432), database name dự kiến appdb và ARN của master secret do RDS quản lý.

Không dùng master account trong ứng dụng. Master secret chỉ dành cho thao tác quản trị database và bootstrap role.

### 5.1. Xác nhận endpoint bằng AWS CLI

~~~bash
aws rds describe-db-instances \
  --db-instance-identifier "$DB_IDENTIFIER" \
  --region "$AWS_REGION" \
  --query "DBInstances[0].{Status:DBInstanceStatus,Endpoint:Endpoint.Address,Port:Endpoint.Port,Public:PubliclyAccessible,Encrypted:StorageEncrypted}" \
  --output table
~~~

Kiểm tra Public là False, Encrypted là True và trạng thái là available. Nếu endpoint chưa có hoặc DB đang creating, đợi trước khi tiếp tục.

## 6. Tạo database và user riêng cho ứng dụng

Dùng master secret được RDS quản lý để kết nối qua một máy quản trị nằm trong VPC hoặc qua VPN/SSM tunnel. Không mở database ra internet chỉ để chạy psql.

Tạo role và database riêng. Password dưới đây là placeholder; thay bằng một mật khẩu ngẫu nhiên mạnh và lưu cùng giá trị đó vào secret ở bước tiếp theo. Không commit giá trị thật vào file SQL hoặc Git.

~~~sql
-- Chạy bằng tài khoản quản trị RDS.
CREATE ROLE app_user LOGIN;
CREATE DATABASE appdb;
~~~

Sau khi tạo role, đặt password bằng prompt tương tác của psql hoặc công cụ quản trị được phê duyệt; không lưu password trong SQL script hay terminal history. Ghi lại giá trị trong password manager an toàn để dùng cùng giá trị khi tạo secret. Mở một kết nối psql mới tới database appdb, sau đó tạo bảng và cấp quyền runtime:

~~~sql
CREATE TABLE customers (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

GRANT CONNECT ON DATABASE appdb TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE customers
TO app_user;

GRANT USAGE, SELECT
ON SEQUENCE customers_id_seq
TO app_user;
~~~

Ý nghĩa:

- app_user chỉ là database login cho ứng dụng.
- app_user không phải owner của database hoặc schema.
- Ứng dụng chỉ có quyền CRUD trên bảng customers và quyền cần thiết trên sequence.
- Không cấp SUPERUSER, CREATEDB, CREATEROLE hoặc quyền quản trị cho ứng dụng.

Nếu cần migration schema, dùng migration role riêng (Flyway/Liquibase) trong deployment pipeline. Không mở rộng quyền runtime của app_user chỉ để Hibernate tự tạo bảng. Với lab này, schema được tạo thủ công và ứng dụng chỉ thực hiện CRUD.

## 7. Lưu application credentials trong Secrets Manager

Tạo secret cho app_user, tách biệt với master secret do RDS quản lý. JSON structure dùng các key chuẩn cho PostgreSQL:

~~~json
{
  "engine": "postgres",
  "host": "spring-rds-lab.xxxxx.ap-southeast-1.rds.amazonaws.com",
  "username": "app_user",
  "password": "REPLACE_WITH_THE_SAME_RANDOM_PASSWORD",
  "dbname": "appdb",
  "port": 5432,
  "dbInstanceIdentifier": "spring-rds-lab"
}
~~~

Thay endpoint và password bằng giá trị thật của môi trường. dbInstanceIdentifier giúp Secrets Manager nhận diện database khi cấu hình rotation qua Console. Các key JSON phân biệt chữ hoa/chữ thường.

Lưu nội dung vào file cục bộ db-secret.json có quyền truy cập giới hạn. File này chỉ là phương tiện nhập liệu tạm thời, không đưa vào source control.

Tạo secret:

~~~bash
aws secretsmanager create-secret \
  --name "$SECRET_NAME" \
  --description "Application credentials for Spring RDS lab" \
  --secret-string file://db-secret.json \
  --region "$AWS_REGION"
~~~

Không truyền password trực tiếp trong tham số --secret-string vì shell history, process list và log có thể làm lộ giá trị. Sau khi tạo thành công, xóa file chứa secret khỏi nơi làm việc hoặc cất trong vùng bảo vệ được tổ chức phê duyệt. Nếu dùng Windows, kiểm soát ACL của file trước khi xóa.

Xác nhận metadata mà không in SecretString ra terminal:

~~~bash
aws secretsmanager describe-secret \
  --secret-id "$SECRET_NAME" \
  --region "$AWS_REGION" \
  --query "{Name:Name,ARN:ARN,RotationEnabled:RotationEnabled,KmsKeyId:KmsKeyId}"
~~~

Secrets Manager mã hóa secret bằng KMS. Nếu không chỉ định customer managed key, dịch vụ dùng AWS managed key phù hợp. Với secret dùng customer managed KMS key, policy của caller phải cho phép decrypt qua Secrets Manager.

### 7.1. Version và staging label

Secrets Manager quản lý version của secret. Các staging label thường gặp:

- AWSCURRENT: version hiện hành, ứng dụng thường đọc version này.
- AWSPREVIOUS: version trước đó, hữu ích cho kiểm tra/rollback có kiểm soát.
- AWSPENDING: version đang trong quá trình rotation.

Không tự gán staging label tùy tiện khi Lambda rotation đang chạy. Một rotation hoàn chỉnh mới chuyển AWSCURRENT sang version đã kiểm thử.

## 8. IAM: cấp quyền đọc đúng secret

Workload role của ứng dụng chỉ cần đọc secret dành cho app_user. Không cấp quyền quản trị Secrets Manager cho ứng dụng.

Ví dụ IAM policy (thay account ID và ARN/prefix theo môi trường):

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadSpringRdsApplicationSecret",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:/lab/spring-rds/db-*"
    }
  ]
}
~~~

Nếu secret dùng customer managed KMS key, bổ sung quyền kms:Decrypt giới hạn vào đúng key, và có thể giới hạn bằng condition kms:ViaService cho Secrets Manager tại Region tương ứng. Không cấp kms:Decrypt trên mọi key.

Gắn policy vào:

- EC2 instance profile nếu app chạy trên EC2.
- ECS task role nếu app chạy trên ECS/Fargate (không nhầm với task execution role).
- EKS workload role qua EKS Pod Identity hoặc IRSA nếu app chạy trên EKS.

Với máy phát triển, dùng IAM Identity Center profile và quyền tạm thời. AWS SDK for Java 2.x/Spring Cloud AWS dùng default credentials provider chain để tìm credential; không cần đặt access key trong application.yml.

### 8.1. Xác minh quyền bằng policy simulation hoặc log

Nếu ứng dụng nhận AccessDeniedException, kiểm tra đúng IAM role, secretsmanager:GetSecretValue trên đúng secret ARN, Region, KMS key policy và VPC endpoint policy.

## 9. Tạo dự án Spring Boot

Có thể tạo project bằng Spring Initializr hoặc tạo Maven project tương đương. Chọn Java 21, Spring Boot 4.0.10, Maven, Spring Web MVC, Spring JDBC, Spring Boot Actuator, PostgreSQL Driver và Spring Cloud AWS Secrets Manager starter.

Ví dụ pom.xml rút gọn:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.10</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-rds-secrets-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>io.awspring.cloud</groupId>
                <artifactId>spring-cloud-aws-dependencies</artifactId>
                <version>4.2.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-starter-secrets-manager</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Cloud AWS BOM quản lý phiên bản các module AWSpring. Không tự gắn một phiên bản khác cho starter Secrets Manager nếu không có lý do và kiểm thử tương thích.

Cấu trúc source:

~~~text
src/
  main/
    java/com/example/springrds/
      SpringRdsSecretsApplication.java
      CustomerController.java
    resources/
      application.yml
~~~

## 10. Cấu hình Spring Boot nạp secret từ Secrets Manager

Tạo src/main/resources/application.yml:

~~~yaml
spring:
  application:
    name: spring-rds-secrets-lab
  config:
    import: "aws-secretsmanager:/lab/spring-rds/db?prefix=db."
  cloud:
    aws:
      region:
        static: ap-southeast-1
  datasource:
    url: "jdbc:postgresql://${db.host}:${db.port}/${db.dbname}?sslmode=verify-full&sslrootcert=${RDS_CA_BUNDLE_PATH}"
    username: "${db.username}"
    password: "${db.password}"
    driver-class-name: org.postgresql.Driver
    hikari:
      maximum-pool-size: 5
      minimum-idle: 1
      connection-timeout: 30000
      validation-timeout: 5000
      pool-name: SpringRdsPool
  sql:
    init:
      mode: never

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
~~~

Giải thích:

- spring.config.import yêu cầu Spring Cloud AWS tải secret trước khi tạo các bean cần cấu hình database.
- ?prefix=db. thêm prefix vào tất cả key JSON, tránh đụng tên với property khác trong ứng dụng.
- db.host, db.port, db.dbname, db.username, db.password được resolve từ JSON secret.
- Không dùng optional: cho secret bắt buộc để ứng dụng fail-fast nếu không đọc được credential.
- spring.cloud.aws.region.static phải khớp Region chứa secret.
- RDS_CA_BUNDLE_PATH là đường dẫn tới RDS CA bundle trên host chạy app.
- sslmode=verify-full mã hóa kết nối và xác minh certificate chain cùng hostname. Không hạ xuống disable để chữa lỗi kết nối.
- HikariCP quản lý pool; pool size phải phù hợp max_connections, số replica ứng dụng và workload.
- Chỉ expose health/info. Không expose actuator env, configprops, beans hoặc endpoint nhạy cảm công khai.

### 10.1. Tải RDS CA bundle

Tải bundle CA chính thức từ AWS và đặt tại một đường dẫn được bảo vệ trên máy chạy ứng dụng:

~~~bash
curl -o global-bundle.pem \
  https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
~~~

Ví dụ biến môi trường trên Linux:

~~~bash
export RDS_CA_BUNDLE_PATH=/opt/certs/global-bundle.pem
~~~

PowerShell:

~~~powershell
$env:RDS_CA_BUNDLE_PATH = "C:\certs\global-bundle.pem"
~~~

Không đặt CA bundle vào secret. Đây là chứng chỉ CA công khai, nhưng cần có quy trình cập nhật khi AWS thay đổi CA. Đường dẫn trong JDBC URL phải tồn tại và process của Java phải có quyền đọc file.


## 11. Viết Spring Boot application và REST API

### 11.1. Application entry point

Tạo SpringRdsSecretsApplication.java:

~~~java
package com.example.springrds;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SpringRdsSecretsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SpringRdsSecretsApplication.class, args);
    }
}
~~~

### 11.2. Controller dùng JdbcTemplate

Tạo CustomerController.java:

~~~java
package com.example.springrds;

import java.time.OffsetDateTime;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private static final RowMapper<Customer> CUSTOMER_MAPPER =
            (rs, rowNum) -> new Customer(
                    rs.getLong("id"),
                    rs.getString("name"),
                    rs.getString("email"),
                    rs.getObject("created_at", OffsetDateTime.class)
            );

    private final JdbcTemplate jdbcTemplate;

    public CustomerController(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @GetMapping
    public List<Customer> findAll() {
        return jdbcTemplate.query(
                """
                SELECT id, name, email, created_at
                FROM customers
                ORDER BY id
                """,
                CUSTOMER_MAPPER
        );
    }

    @PostMapping
    public Customer create(@RequestBody CreateCustomerRequest request) {
        Long id = jdbcTemplate.queryForObject(
                """
                INSERT INTO customers(name, email)
                VALUES (?, ?)
                RETURNING id
                """,
                Long.class,
                request.name(),
                request.email()
        );

        return jdbcTemplate.queryForObject(
                """
                SELECT id, name, email, created_at
                FROM customers
                WHERE id = ?
                """,
                CUSTOMER_MAPPER,
                id
        );
    }

    public record CreateCustomerRequest(String name, String email) {
    }

    public record Customer(
            long id,
            String name,
            String email,
            OffsetDateTime createdAt
    ) {
    }
}
~~~

Điểm quan trọng:

- JdbcTemplate lấy connection từ DataSource do Spring Boot auto-configure.
- Không truyền username/password vào từng query.
- Prepared statement dùng placeholder ?, tránh ghép chuỗi SQL từ input người dùng.
- Tên bảng và quyền truy cập đã được chuẩn bị trước; runtime user không cần quyền quản trị schema.


## 12. Chạy ứng dụng và kiểm thử kết nối

### 12.1. Chuẩn bị môi trường AWS credentials

Nếu chạy ứng dụng từ máy phát triển, đăng nhập SSO bằng profile có quyền đọc đúng secret. Máy phát triển cũng phải có network route tới private RDS (VPN/Client VPN/Direct Connect hoặc tunnel được kiểm soát). Nếu không có đường mạng riêng, chạy app trong EC2/ECS thuộc VPC thay vì bật public access cho RDS.

Linux/macOS:

~~~bash
export AWS_PROFILE=dev
export AWS_REGION=ap-southeast-1
export RDS_CA_BUNDLE_PATH=/opt/certs/global-bundle.pem
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
$env:AWS_PROFILE = "dev"
$env:AWS_REGION = "ap-southeast-1"
$env:RDS_CA_BUNDLE_PATH = "C:\certs\global-bundle.pem"
.\mvnw.cmd spring-boot:run
~~~

Trên EC2/ECS/EKS, ưu tiên IAM role gắn với workload. Không cần AWS_ACCESS_KEY_ID hoặc AWS_SECRET_ACCESS_KEY trong environment của production.

### 12.2. Kiểm tra health

~~~bash
curl http://localhost:8080/actuator/health
~~~

Kết quả thành công thường có trạng thái UP. Nếu health indicator database được bật, phần db cũng phải ở trạng thái hoạt động. Không expose chi tiết health ra internet nếu response có thể tiết lộ cấu trúc nội bộ.

### 12.3. Tạo customer

~~~bash
curl -X POST http://localhost:8080/api/customers \
  -H "Content-Type: application/json" \
  -d '{"name":"Nguyen An","email":"an@example.com"}'
~~~

PowerShell:

~~~powershell
$body = @{
  name = "Nguyen An"
  email = "an@example.com"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/customers" -ContentType "application/json" -Body $body
~~~

### 12.4. Đọc danh sách customer

~~~bash
curl http://localhost:8080/api/customers
~~~

Kết quả trả về phải có record vừa tạo. Có thể kiểm tra trực tiếp bằng psql:

~~~sql
SELECT id, name, email, created_at
FROM customers
ORDER BY id;
~~~

Xác minh ứng dụng kết nối bằng đúng database role:

~~~sql
SELECT current_user, current_database();
~~~

Kết quả cần thể hiện current_user = app_user, current_database = appdb, không phải master account.


## 13. Chạy ứng dụng trong AWS thay vì kết nối trực tiếp từ laptop

Một cấu hình lab an toàn hơn là chạy Spring Boot trên EC2 trong cùng VPC:

1. Tạo EC2 instance trong subnet phù hợp và gắn sg-spring-app.
2. Gắn instance profile có AmazonSSMManagedInstanceCore và policy đọc secret /lab/spring-rds/db.
3. Không mở inbound SSH nếu dùng Systems Manager Session Manager.
4. Đảm bảo EC2 phân giải được RDS endpoint và kết nối TCP 5432 tới sg-rds-postgres.
5. Đảm bảo EC2 gọi được Secrets Manager qua interface endpoint hoặc NAT/egress.
6. Đưa JAR tới EC2 qua S3/private artifact store hoặc quy trình deployment.
7. Đặt RDS_CA_BUNDLE_PATH trỏ tới CA bundle trên EC2.
8. Khởi chạy java -jar bằng service account riêng, log ra CloudWatch Logs và restart policy phù hợp.

Với ECS/Fargate, dùng task role để đọc secret và task security group để kết nối RDS. Với EKS, dùng EKS Pod Identity hoặc IRSA. Không gắn quyền Secrets Manager vào node role dùng chung nếu có thể giới hạn ở workload role.




## 14. Cơ chế nạp secret: Config Import hay gọi SDK trực tiếp?

Spring Cloud AWS 4.2.0 cung cấp hai cách thường dùng:

| Cách | Khi phù hợp | Lưu ý |
|---|---|---|
| Config Import qua spring.config.import | Secret là application configuration như DB username/password | Nạp secret vào Spring Environment; đơn giản cho DataSource auto-configuration |
| Inject SecretsManagerClient | Secret được đọc theo nghiệp vụ hoặc cần kiểm soát thời điểm lấy | Tự quản lý parse JSON, cache, refresh và xử lý lỗi |

Spring Cloud AWS tự cấu hình SecretsManagerClient bean khi starter được thêm vào. Có thể inject client để gọi API imperatively, nhưng không nên viết một lệnh GetSecretValue cho mỗi request hoặc mỗi query database.

AWS SDK for Java 2.x khuyến nghị cache secret ở client side để giảm latency và số API request. Nếu tự triển khai caching, cần xác định TTL, hành vi khi cache hết hạn, retry và cách phản ứng khi rotation.

Với lab này, Config Import được chọn vì username/password là cấu hình cần thiết để tạo DataSource.

## 15. Rotation: cập nhật password mà không để lộ secret

Secrets Manager hỗ trợ rotation cho database secret bằng Lambda function hoặc managed rotation tùy loại secret.

### 15.1. Bật rotation cho application user

Trong Secrets Manager Console:

1. Mở secret /lab/spring-rds/db.
2. Chọn Rotation configuration → Edit rotation.
3. Bật automatic rotation.
4. Chọn schedule phù hợp, ví dụ 30 ngày, và rotation window theo yêu cầu vận hành. Lịch rotation được tính theo UTC; đồng bộ với maintenance window và lịch deployment của ứng dụng.
5. Chọn rotation Lambda template phù hợp với RDS PostgreSQL.
6. Với database secret, xác nhận các field engine, host, username, password, dbname, port và dbInstanceIdentifier là đúng.
7. Đảm bảo Lambda rotation chạy trong VPC có route tới RDS.
8. Security group của RDS phải cho phép inbound 5432 từ security group của Lambda rotation.
9. Lambda phải gọi được Secrets Manager; dùng VPC endpoint hoặc đường egress phù hợp.
10. Thực hiện rotation thử, xem trạng thái và CloudWatch Logs của Lambda.

Rotation function thực hiện các bước theo giao thức createSecret, setSecret, testSecret, finishSecret. Chỉ chuyển AWSCURRENT sau khi credential mới đã được kiểm thử.

### 15.2. Single-user và alternating-users

| Chiến lược | Cách hoạt động | Đánh đổi |
|---|---|---|
| Single user | Cập nhật password của cùng một database user và secret | Đơn giản; có khoảng thời gian ngắn giữa lúc DB đổi password và secret được cập nhật |
| Alternating users | Tạo user clone, luân phiên cập nhật credential giữa hai user | Tăng khả năng sẵn sàng khi app lấy secret trong lúc rotation; cần secret quản trị (masterarn) để clone user |

Với single-user rotation, các database connection đang mở không bị đóng chỉ vì password đổi. Tuy nhiên, connection mới tạo bằng password cũ có thể bị từ chối trong thời gian chuyển đổi. Retry có backoff giúp giảm lỗi tạm thời.

Alternating-users rotation phù hợp với ứng dụng cần high availability, nhưng cần quản lý quyền hai user đồng nhất. Amazon RDS Proxy không hỗ trợ chiến lược alternating users; kiểm tra giới hạn này trước khi chọn kiến trúc proxy.

### 15.3. Kiểm tra version sau rotation

Sau khi rotation hoàn tất, kiểm tra metadata version mà không in secret ra log:

~~~bash
aws secretsmanager list-secret-version-ids \
  --secret-id "$SECRET_NAME" \
  --region "$AWS_REGION" \
  --query "Versions[].{VersionId:VersionId,Stages:VersionStages,CreatedDate:CreatedDate}"
~~~

AWSCURRENT phải gắn với version mới đã được rotation test thành công. Không tự động đọc AWSPREVIOUS làm fallback cho production nếu chưa có quy trình xác thực và rollback rõ ràng.

## 16. Làm mới Spring DataSource sau khi secret đổi

Một điểm dễ nhầm: rotation trong Secrets Manager không đồng nghĩa HikariCP tự thay username/password trong một DataSource đã được tạo.

- Config Import nạp secret để xây dựng Spring Environment và DataSource.
- Connection pool đã mở có thể tiếp tục dùng các session hiện tại.
- Khi pool cần tạo connection mới, nếu DataSource vẫn giữ password cũ, kết nối mới có thể thất bại.
- Cần có kế hoạch refresh/restart DataSource hoặc dùng kiến trúc proxy để tách vòng đời credential khỏi ứng dụng.

Spring Cloud AWS hỗ trợ PropertySource reload. Mặc định reload bị tắt. Có hai chiến lược chính:

- refresh: refresh các bean ConfigurationProperties hoặc RefreshScope theo cơ chế Spring Cloud Context. Không giả định mọi bean bất kỳ, đặc biệt Hikari DataSource, tự được thay thế.
- restart_context: graceful restart toàn bộ Spring ApplicationContext, tạo lại các bean và DataSource với configuration mới.

Để dùng reload, cần thêm các dependency tương ứng như Spring Boot Actuator, Spring Cloud Commons và Spring Cloud Context theo tài liệu phiên bản:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-commons</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-context</artifactId>
</dependency>
~~~

Cấu hình minh họa:

~~~yaml
spring:
  cloud:
    aws:
      secretsmanager:
        reload:
          strategy: restart_context
          period: 1m
~~~

restart_context yêu cầu bật và expose Actuator restart endpoint theo hướng dẫn Spring Cloud AWS. Đây là endpoint có ảnh hưởng lớn tới ứng dụng: không expose công khai; nếu sử dụng, giới hạn ở management network, xác thực mạnh và audit. Với nhiều replica, cần rolling/restart có kiểm soát để tránh đồng loạt ngắt service.

Ví dụ phần cấu hình Actuator khi chủ động chọn restart_context:

~~~yaml
management:
  endpoint:
    restart:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,restart
~~~

Không áp dụng cấu hình expose restart trên interface public. Dùng management port/network riêng và security policy giới hạn operator được phép gọi.

Đối với lab, cách đơn giản nhất sau khi rotation thành công là restart ứng dụng:

~~~bash
# Dừng process Spring Boot bằng cơ chế quản lý process/service.
# Sau đó khởi động lại ứng dụng để DataSource đọc AWSCURRENT mới.
java -jar target/spring-rds-secrets-lab-0.0.1-SNAPSHOT.jar
~~~

Trong production, thiết kế quy trình rotation và refresh trước khi bật lịch rotation tự động. Không chờ tới khi password đổi mới phát hiện connection pool đang giữ credential cũ.

## 17. Khi nào nên dùng Amazon RDS Proxy?

RDS Proxy là lớp proxy database có connection pooling và quản lý kết nối giữa ứng dụng với RDS. Proxy có thể lấy database credentials từ Secrets Manager thông qua IAM role được gắn cho proxy.

Có hai mô hình IAM quan trọng:

1. **Standard IAM authentication:** ứng dụng xác thực tới proxy bằng IAM; proxy sử dụng credential trong Secrets Manager để xác thực tới database. Đây là cách giữ secret DB ở phía proxy thay vì để ứng dụng đọc password database.
2. **End-to-end IAM authentication:** IAM được dùng từ ứng dụng qua proxy tới database; mô hình này không cần Secrets Manager secret cho DB credential theo cách standard secret-based authentication.

Khi dùng RDS Proxy:

- Ứng dụng kết nối tới proxy endpoint thay vì DB instance endpoint.
- Trong standard IAM authentication, proxy cần IAM role có secretsmanager:GetSecretValue trên secret tương ứng. End-to-end IAM không dùng secret DB theo mô hình này.
- Ứng dụng cần quyền rds-db:connect cho proxy resource ID và database user khi dùng IAM authentication.
- Kết nối IAM tới proxy phải dùng TLS.
- Kiểm tra engine family, Region, quota, session pinning và giới hạn tương thích của RDS Proxy.
- Đo pool size, connection borrow latency và số connection thực tế trước khi tăng tải.

RDS Proxy không phải yêu cầu bắt buộc cho mọi ứng dụng nhỏ. Cân nhắc khi có nhiều application replica, burst connection, Lambda/serverless, hoặc cần giảm connection pressure lên database. Nếu ứng dụng tự nạp password từ Secrets Manager và kết nối thẳng RDS, bạn vẫn phải xử lý rotation và refresh DataSource ở phía ứng dụng.

## 18. Bảo mật production

### 18.1. Database và network

- RDS đặt trong private subnet; PubliclyAccessible = false.
- Chỉ mở TCP 5432 từ application security group hoặc proxy security group.
- Bật storage encryption bằng KMS.
- Dùng backup retention phù hợp RPO/RTO.
- Bật Multi-AZ khi yêu cầu availability cần thiết.
- Dùng TLS verify-full với CA bundle được cập nhật.
- Không đưa endpoint/password vào log hoặc exception message trả về client.

### 18.2. Secrets Manager và IAM

- Một secret riêng cho từng ứng dụng/môi trường/database user.
- IAM policy chỉ cho phép GetSecretValue trên secret cần thiết.
- Phân biệt role quản trị/rotation với role runtime.
- Không cấp secretsmanager:* cho ứng dụng.
- Không log SecretString, password hoặc object chứa credential.
- Dùng customer managed KMS key nếu cần kiểm soát key policy, audit và chia sẻ cross-account.
- Theo dõi CloudTrail cho các API Secrets Manager quan trọng.
- Không dùng secret master credential làm credential runtime.

### 18.3. Spring Boot và Actuator

- Không đưa secret vào application.yml, source code, image, CI log hoặc application log.
- Không bật debug log cho request/response Secrets Manager trong production nếu có nguy cơ lộ payload.
- Không expose Actuator env, configprops, heapdump, threaddump hoặc restart endpoint công khai.
- Dùng authentication và authorization cho REST API.
- Validate request, dùng prepared statements và xử lý lỗi SQL không tiết lộ schema nội bộ.
- Dùng Hikari pool size có giới hạn; không để tổng connection từ mọi replica vượt khả năng RDS.
- Tách database migration role khỏi runtime role.

## 19. Monitoring và vận hành

Theo dõi ở cả lớp ứng dụng, network và database.

| Lớp | Chỉ số / log | Mục đích |
|---|---|---|
| Spring Boot | Request latency, HTTP 5xx, actuator health | Phát hiện lỗi API |
| HikariCP | Active, idle, pending connections, acquisition timeout | Phát hiện pool cạn |
| RDS PostgreSQL | CPU, FreeableMemory, DatabaseConnections, storage, latency | Đánh giá sức khỏe DB |
| Secrets Manager | AccessDenied, throttling, rotation status | Đảm bảo secret đọc/rotate được |
| Rotation Lambda | Duration, error, timeout, log của bốn bước rotation | Phát hiện rotation thất bại |
| VPC | Flow Logs, endpoint policy, DNS resolution | Điều tra lỗi network |

Một số query hữu ích trong PostgreSQL:

~~~sql
SELECT current_user, current_database(), inet_server_addr(), inet_server_port();

SELECT
    datname,
    usename,
    application_name,
    client_addr,
    state
FROM pg_stat_activity
WHERE usename = 'app_user';

SELECT
    a.usename,
    a.client_addr,
    s.ssl,
    s.version,
    s.cipher
FROM pg_stat_activity a
JOIN pg_stat_ssl s ON s.pid = a.pid
WHERE a.usename = 'app_user';
~~~

Không ghi query chứa dữ liệu cá nhân hoặc credential vào log nếu không cần. Dùng CloudWatch alarms cho CPU/storage/connection pressure, application error rate và rotation failures. Thiết lập runbook để xác định nhanh lỗi thuộc IAM, Secrets Manager, DNS, security group, TLS hay database.

## 20. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| ConfigDataLocationNotFoundException | Secret name/ARN sai hoặc secret không tồn tại | Kiểm tra spring.config.import, Region và secret name |
| AccessDeniedException khi startup | Role thiếu secretsmanager:GetSecretValue | Kiểm tra workload role, secret ARN, resource policy và endpoint policy |
| KMSAccessDeniedException | Secret dùng customer managed key nhưng role/key policy thiếu quyền | Kiểm tra kms:Decrypt, key policy và kms:ViaService |
| Unable to load credentials | Chưa đăng nhập SSO, sai profile hoặc workload thiếu role | Kiểm tra aws sts get-caller-identity, IAM role và credential chain |
| Unable to find region | Thiếu AWS_REGION/region provider hoặc cấu hình không đúng | Đặt spring.cloud.aws.region.static và Region đúng |
| Timeout tới RDS | Route, security group, NACL hoặc DNS sai | Kiểm tra endpoint resolve, TCP 5432, source/destination SG và VPC route |
| Connection refused | Sai port/endpoint hoặc DB chưa Available | Kiểm tra describe-db-instances, port 5432 và DB status |
| password authentication failed | Secret và DB role không cùng password hoặc app đang dùng version cũ | Kiểm tra AWSCURRENT, DB user và trạng thái rotation |
| relation customers does not exist | Chưa tạo schema hoặc kết nối nhầm database | Kiểm tra current_database() và chạy SQL DDL bằng migration/admin role |
| permission denied for table | App user thiếu grant | Cấp đúng SELECT/INSERT/UPDATE/DELETE và quyền sequence |
| PKIX path building failed | Thiếu CA bundle hoặc trust store không đúng | Tải RDS CA bundle chính thức, kiểm tra path và quyền đọc |
| Hostname verification failed | JDBC URL không dùng đúng RDS endpoint hoặc chứng chỉ không khớp | Dùng endpoint DNS do RDS cấp và sslmode=verify-full |
| Hikari connection timeout | Pool hết connection hoặc DB chậm | Kiểm tra active/pending, query latency, max pool và max_connections |
| Lỗi sau rotation | DataSource/Hikari còn giữ password cũ | Reload/restart context có kiểm soát hoặc dùng RDS Proxy |
| Rotation Lambda timeout | Lambda không vào được DB/Secrets Manager | Kiểm tra VPC, route, Lambda SG, RDS SG, endpoint/NAT và timeout |
| Rotation testSecret thất bại | DB user không có quyền tối thiểu hoặc secret JSON sai | Kiểm tra engine, host, port, dbname, username và quyền query test |
| Secret không đổi sau rotation | Rotation chưa hoàn tất hoặc Lambda lỗi | Kiểm tra Rotation status, CloudWatch Logs và staging labels |


## 21. Bài tập mở rộng

### Bài tập A — Thử quyền tối thiểu

1. Thu hồi tạm quyền INSERT khỏi app_user.
2. Gọi API POST.
3. Quan sát lỗi database và log ứng dụng.
4. Cấp lại đúng quyền INSERT.
5. Gọi lại API và xác nhận thành công.

Mục tiêu: hiểu khác biệt giữa quyền AWS IAM và quyền SQL của database user. IAM cho phép đọc secret không đồng nghĩa database role có quyền thao tác bảng.

### Bài tập B — Rotation

1. Bật single-user rotation cho application secret.
2. Thực hiện rotation ngay trong môi trường lab.
3. Kiểm tra version mới có AWSCURRENT.
4. Kiểm thử connection mới.
5. Restart Spring Boot để DataSource nạp credential mới.
6. So sánh lỗi/latency trước và sau khi pool được tạo lại.

Mục tiêu: quan sát vòng đời secret, database password và connection pool.

### Bài tập C — Thêm RDS Proxy

1. Tạo RDS Proxy cho PostgreSQL.
2. Gắn Secrets Manager secret và IAM role cho proxy.
3. Cấu hình IAM authentication cho client connection.
4. Cập nhật JDBC endpoint sang proxy.
5. Đo số connection trên RDS và latency khi tăng số client.

Mục tiêu: hiểu pooling ở lớp proxy và cách tách credential database khỏi application runtime.

### Bài tập D — Kiểm thử network isolation

1. Xác nhận RDS không public.
2. Thử kết nối từ máy ngoài VPC không có VPN/tunnel.
3. Xác nhận kết nối bị chặn.
4. Kết nối từ application host trong VPC.
5. Kiểm tra Flow Logs hoặc security group để giải thích kết quả.

Mục tiêu: chứng minh network boundary được thiết kế có chủ đích, không chỉ dựa vào password.

## 22. Câu hỏi tự kiểm tra

1. Vì sao không nên dùng RDS master user trong Spring Boot?
2. Secrets Manager giải quyết vấn đề nào mà application.yml không giải quyết được?
3. spring.config.import làm gì trong vòng đời Spring Boot?
4. Vì sao JSON secret nên có host, port, dbname, username, password và engine?
5. ?prefix=db. giúp tránh vấn đề gì?
6. Vì sao secret bắt buộc không nên được import bằng optional: trong production?
7. secretsmanager:GetSecretValue khác quyền SQL SELECT như thế nào?
8. Vì sao IAM role của ECS task khác execution role?
9. Tại sao RDS nên nằm trong private subnet?
10. Security group của RDS nên nhận inbound từ đâu?
11. VPC interface endpoint cho Secrets Manager giải quyết vấn đề gì?
12. Vì sao dùng TLS verify-full thay cho kết nối không mã hóa?
13. HikariCP quản lý connection ra sao?
14. Vì sao không nên đặt pool size lớn tùy ý?
15. Khi rotation đổi password, các database session đang mở có bị ngắt ngay không?
16. Vì sao DataSource đã tạo không tự động nhận password mới chỉ vì secret đổi?
17. Single-user rotation và alternating-users rotation khác nhau thế nào?
18. Vì sao alternating users cần một secret quản trị trong nhiều trường hợp?
19. AWSCURRENT, AWSPREVIOUS và AWSPENDING có ý nghĩa gì?
20. RDS Proxy giúp giải quyết vấn đề connection/credential nào?
21. Standard IAM authentication của RDS Proxy khác end-to-end IAM như thế nào?
22. Vì sao không nên expose Actuator env hoặc restart công khai?
23. Khi AccessDeniedException xảy ra, cần kiểm tra những policy nào?
24. Làm thế nào phân biệt lỗi network timeout với lỗi database authentication?
25. Những tài nguyên nào cần xóa sau khi hoàn thành lab?

## 23. Checklist trước khi đưa lên production

- [ ] RDS ở private subnet và không public.
- [ ] Database storage được mã hóa và backup retention phù hợp.
- [ ] Security group chỉ cho phép app/proxy kết nối TCP 5432.
- [ ] Database runtime user không có quyền admin.
- [ ] Secret có JSON structure đúng và version AWSCURRENT hợp lệ.
- [ ] Secret được mã hóa bằng KMS theo policy.
- [ ] Workload role chỉ có quyền đọc đúng secret.
- [ ] Ứng dụng dùng default credentials provider chain hoặc workload identity.
- [ ] Không có credential trong source, image, CI log hoặc application log.
- [ ] JDBC dùng TLS và xác minh hostname/certificate.
- [ ] Hikari pool size được tính theo số replica và DB capacity.
- [ ] Rotation Lambda có network path tới RDS và Secrets Manager.
- [ ] Đã kiểm thử rotation cùng hành vi refresh DataSource.
- [ ] Actuator chỉ expose endpoint cần thiết và có kiểm soát truy cập.
- [ ] Có CloudWatch metrics/alarms và CloudTrail audit.
- [ ] Có retry/backoff và runbook cho rotation/DB failover.
- [ ] Đã đánh giá RDS Proxy hoặc IAM database authentication khi phù hợp.
- [ ] Đã kiểm thử backup restore và failover.
- [ ] Có quy trình xoay CA bundle và kiểm tra TLS.
- [ ] Có cost budget, tag và lifecycle cho tài nguyên lab/temporary.

## 24. Dọn dẹp tài nguyên lab

Lab có thể phát sinh chi phí RDS instance/storage, Secrets Manager secret, KMS, VPC endpoint/NAT, EC2, CloudWatch Logs và Lambda rotation. Sau khi hoàn tất:

1. Dừng Spring Boot app và xóa artifact tạm nếu không cần.
2. Xóa EC2 app host hoặc môi trường compute tạm.
3. Xóa RDS Proxy nếu đã tạo.
4. Xóa RDS DB instance theo chính sách snapshot của bạn. Chỉ dùng --skip-final-snapshot nếu đây là dữ liệu lab có thể bỏ.
5. Xóa rotation Lambda/role nếu chỉ dùng cho lab và không còn secret nào tham chiếu.
6. Xóa secret application theo recovery window phù hợp; không force-delete nếu không hiểu hậu quả.
7. Xóa VPC endpoint/security group/role riêng được tạo cho lab khi không còn tài nguyên phụ thuộc.
8. Xóa file db-secret.json và kiểm tra .gitignore/Git history để chắc chắn không có password bị commit.

Ví dụ xóa secret với recovery window:

~~~bash
aws secretsmanager delete-secret \
  --secret-id "$SECRET_NAME" \
  --recovery-window-in-days 7 \
  --region "$AWS_REGION"
~~~

Xóa database bằng CLI chỉ sau khi đã xác nhận dữ liệu không cần giữ:

~~~bash
aws rds delete-db-instance \
  --db-instance-identifier "$DB_IDENTIFIER" \
  --skip-final-snapshot \
  --delete-automated-backups \
  --region "$AWS_REGION"
~~~

Không chạy lệnh xóa trong production hoặc tài khoản dùng chung. Nếu cần giữ dữ liệu, tạo final snapshot và xác minh snapshot đã hoàn tất trước khi xóa DB.

## Kết luận

Một ứng dụng Spring Boot kết nối Amazon RDS an toàn không chỉ cần JDBC URL và password. Cần thiết kế đồng thời network boundary, IAM identity, secret lifecycle, TLS, database privilege và connection pool.

Spring Cloud AWS Secrets Manager starter giúp đưa JSON secret vào Spring Environment thông qua spring.config.import; AWSpring dùng AWS SDK for Java 2.x và default credentials provider chain để lấy secret. Amazon RDS cung cấp database endpoint và TLS, còn HikariCP quản lý các connection được tái sử dụng. IAM role giới hạn ứng dụng chỉ đọc secret cần thiết, security group giới hạn luồng TCP 5432, và Secrets Manager rotation cập nhật credential theo lịch.

Điểm vận hành quan trọng nhất là rotation không tự động thay đổi một Hikari DataSource đã tạo. Hãy thiết kế refresh/restart DataSource hoặc cân nhắc RDS Proxy/IAM authentication để giảm việc ứng dụng trực tiếp quản lý database password. Trước khi production, kiểm thử rotation, failover, TLS, IAM denial, restore và chi phí end-to-end.

## Tài liệu tham khảo chính thức

- [Spring Cloud AWS 4.2.0 Reference Documentation](https://docs.awspring.io/spring-cloud-aws/docs/4.2.0/reference/html/index.html)
- [Spring Cloud AWS Secrets Manager integration](https://docs.awspring.io/spring-cloud-aws/docs/4.2.0/reference/html/index.html#secrets-manager-integration)
- [Spring Cloud AWS BOM and starter dependencies](https://docs.awspring.io/spring-cloud-aws/docs/4.2.0/reference/html/index.html#getting-started)
- [Spring Boot 4.0.10 documentation](https://docs.spring.io/spring-boot/4.0/)
- [Spring Boot externalized configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [AWS SDK for Java 2.x Secrets Manager examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_secrets-manager_code_examples.html)
- [Create and connect to RDS for PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_GettingStarted.CreatingConnecting.PostgreSQL.html)
- [RDS PostgreSQL SSL/TLS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html)
- [RDS PostgreSQL certificate bundle](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html)
- [JSON structure of Secrets Manager database secrets](https://docs.aws.amazon.com/secretsmanager/latest/userguide/reference_secret_json_structure.html)
- [Connect to SQL databases using Secrets Manager credentials and JDBC](https://docs.aws.amazon.com/secretsmanager/latest/userguide/retrieving-secrets_jdbc.html)
- [Secrets Manager best practices](https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html)
- [Single-user rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/tutorials_rotation-single.html)
- [Alternating-users rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/tutorials_rotation-alternating.html)
- [Rotation strategies](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotation-strategy.html)
- [Automatic rotation for RDS database secrets](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_turn-on-for-db.html)
- [Rotation schedules and UTC windows](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_schedule.html)
- [Troubleshoot Secrets Manager rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/troubleshoot_rotation.html)
- [RDS Proxy concepts](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.howitworks.html)
- [Create an RDS Proxy](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-creating.html)
- [Connect to a database through RDS Proxy](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-connecting.html)
- [IAM database authentication for RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.html)
- [IAM authentication for RDS Proxy](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-iam-setup.html)
- [AWS Secrets Manager pricing](https://aws.amazon.com/secrets-manager/pricing/)
- [Amazon RDS for PostgreSQL pricing](https://aws.amazon.com/rds/postgresql/pricing/)
- [Amazon RDS Proxy pricing](https://aws.amazon.com/rds/proxy/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)



