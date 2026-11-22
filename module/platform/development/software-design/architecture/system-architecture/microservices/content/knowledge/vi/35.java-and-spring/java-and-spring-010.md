# Đóng gói và chứng minh một dịch vụ có thể phát hành độc lập

## 1. Mục tiêu

Trong kiến trúc microservices, một dịch vụ chỉ thực sự độc lập khi nhóm phụ trách có thể **xây dựng, kiểm thử, đóng gói, triển khai, quan sát và quay lui phiên bản của dịch vụ đó mà không cần phát hành đồng bộ toàn bộ hệ thống**.

Đóng gói (packaging) tạo ra một đơn vị triển khai có thể tái tạo và chuyển giao, thường là executable JAR hoặc container image. Chứng minh khả năng phát hành độc lập (independent deployability) cần nhiều hơn việc tạo được file JAR: phải có bằng chứng rằng artifact chạy được trong môi trường mục tiêu, cấu hình và dữ liệu thuộc quyền sở hữu của dịch vụ, hợp đồng tích hợp vẫn tương thích, pipeline chỉ phát hành dịch vụ này, và phiên bản mới có thể được triển khai hoặc rollback an toàn.

Sau bài học này, bạn có thể:

- Phân biệt build artifact với deployable artifact.
- Đóng gói một ứng dụng Spring Boot thành JAR và container image.
- Tách cấu hình môi trường, secret và dependency khỏi image.
- Thiết kế kiểm thử để phát hiện phụ thuộc triển khai giữa các dịch vụ.
- Xây dựng bằng chứng phát hành độc lập bằng contract test, integration test, smoke test và deployment evidence.
- Lập quy trình phát hành, theo dõi và rollback một dịch vụ mà không buộc các dịch vụ khác phải phát hành cùng lúc.

## 2. Independent deployability nghĩa là gì?

Một microservice có thể được triển khai độc lập khi một phiên bản mới của nó có thể được đưa vào production mà không yêu cầu đồng thời thay đổi hoặc khởi động lại các dịch vụ khác. Các dịch vụ khác có thể tiếp tục chạy phiên bản hiện tại trong suốt quá trình triển khai.

Điều này không có nghĩa dịch vụ không có dependency runtime. Một dịch vụ vẫn có thể gọi API, gửi message, truy cập database riêng hoặc sử dụng nền tảng dùng chung. Điểm cốt lõi là **thay đổi và phát hành của dịch vụ không tạo ra yêu cầu release đồng bộ ngoài phạm vi sở hữu của nó**.

### 2.1. Những điều kiện cần có

| Khía cạnh | Dấu hiệu có thể phát hành độc lập |
|---|---|
| Build | Có thể build và test từ repository hoặc module thuộc dịch vụ, không cần build toàn bộ hệ thống |
| Artifact | Tạo được artifact có version, checksum hoặc image digest xác định |
| Runtime | Khởi động bằng cấu hình môi trường, không phụ thuộc file cấu hình bí mật được đóng cứng trong artifact |
| Data ownership | Có quyền sở hữu schema/dữ liệu của mình; thay đổi schema không buộc dịch vụ khác cập nhật cùng lúc |
| API và event | Hợp đồng có versioning hoặc quy tắc tương thích ngược; consumer cũ vẫn hoạt động trong giai đoạn chuyển đổi |
| Deployment | Pipeline có thể phát hành riêng service, không yêu cầu release train đồng bộ |
| Health và rollback | Có health check, quan sát được lỗi và có phiên bản trước để quay lui |

Một container image riêng chưa đủ chứng minh independent deployability. Nếu triển khai image đó vẫn yêu cầu dừng toàn bộ hệ thống, cập nhật database dùng chung theo cách phá vỡ consumer cũ, hoặc phát hành đồng thời nhiều service, thì ranh giới triển khai vẫn chưa độc lập.

### 2.2. Phân biệt ba khái niệm

- **Buildable:** mã nguồn có thể biên dịch và tạo artifact.
- **Runnable:** artifact có thể khởi động khi được cấp đúng runtime, cấu hình và dependency.
- **Independently deployable:** artifact có thể được phát hành riêng trong khi các consumer và service liên quan vẫn hoạt động với phiên bản hiện tại.

Quy trình kiểm chứng phải đi qua cả ba cấp độ, đặc biệt là cấp độ thứ ba.

## 3. Chuẩn bị ứng dụng Spring Boot

Ví dụ sử dụng một dịch vụ tên `orders-service`, chạy Java 21 và Spring Boot 3.x. Tên package, phiên bản plugin và dependency cần điều chỉnh theo baseline thực tế của dự án; không nên nâng phiên bản nền tảng chỉ để làm theo ví dụ.

Một cấu trúc source code tối thiểu:

```text
orders-service/
├── src/
│   ├── main/
│   │   ├── java/com/example/orders/
│   │   │   ├── OrdersApplication.java
│   │   │   ├── api/
│   │   │   ├── application/
│   │   │   ├── domain/
│   │   │   └── infrastructure/
│   │   └── resources/
│   │       └── application.yml
│   └── test/
│       └── java/com/example/orders/
├── Dockerfile
├── .dockerignore
├── pom.xml
└── README.md
```

Điểm quan trọng không phải tên package mà là artifact của dịch vụ có ranh giới rõ ràng: controller/API, use case, domain và adapter hạ tầng thuộc cùng một đơn vị phát hành. Tránh để quá trình build của service phải lấy source code chưa phát hành từ repository của service khác.

## 4. Đóng gói Spring Boot thành executable JAR

Spring Boot Maven Plugin có thể đóng gói ứng dụng và các dependency cần thiết thành executable JAR.

Ví dụ cấu hình plugin trong `pom.xml`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

Với Maven Wrapper được commit trong repository, có thể build bằng:

```bash
./mvnw clean verify
```

Trên Windows:

```powershell
.\mvnw.cmd clean verify
```

Sau khi build, kiểm tra artifact trong thư mục `target/`:

```bash
ls -lh target/
java -jar target/orders-service-0.0.1-SNAPSHOT.jar
```

Nếu ứng dụng có profile hoặc cấu hình bắt buộc, cung cấp chúng qua environment variable hoặc tham số runtime. Không đưa password, token hay private key vào command được lưu trong log CI.

### 4.1. Build phải tái tạo được

Để có thể phát hành và rollback đáng tin cậy:

1. Pin phiên bản JDK, Maven plugin và dependency quan trọng.
2. Commit Maven Wrapper hoặc Gradle Wrapper cùng cấu hình checksum phù hợp.
3. Dùng lock/dependency constraints khi hệ sinh thái build hỗ trợ.
4. Không phụ thuộc vào file nằm ngoài repository mà pipeline không khai báo.
5. Ghi nhận commit SHA, build number, thời điểm build và version artifact.
6. Lưu kết quả test cùng artifact được tạo ra từ chính lần build đó.

Không nên build lại source ở từng môi trường rồi giả định các artifact là giống nhau. Thực hành tốt là **build một lần, promote cùng một artifact** qua các môi trường; chỉ cấu hình runtime thay đổi.

## 5. Cấu hình runtime không gắn cứng vào artifact

Một service có thể được triển khai ở local, staging và production bằng cùng một image nếu cấu hình môi trường được truyền vào lúc chạy.

Ví dụ `application.yml`:

```yaml
server:
  port: ${SERVER_PORT:8080}

spring:
  application:
    name: orders-service
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
```

Các biến `DB_URL`, `DB_USERNAME`, `DB_PASSWORD` được cấp từ secret/configuration store của môi trường triển khai. Không commit giá trị production vào repository và không bake secret vào Docker image.

Nguyên tắc:

- Image chứa code và runtime dependency, không chứa dữ liệu bí mật.
- Cấu hình không nhạy cảm có thể truyền qua environment variable hoặc config service.
- Secret phải được quản lý bằng secret manager hoặc cơ chế secret của nền tảng.
- Không dùng một profile riêng chứa password thật để đóng gói vào JAR.
- Log không được in password, access token hoặc connection string có credential.

## 6. Đóng gói thành Docker image

Container image giúp chuẩn hóa runtime và tạo đơn vị phát hành có thể gắn tag, lưu registry, triển khai và rollback.

### 6.1. Dockerfile multi-stage

Ví dụ Dockerfile:

```dockerfile
FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace

COPY .mvn/ .mvn/
COPY mvnw pom.xml ./
RUN chmod +x mvnw
RUN ./mvnw -B dependency:go-offline

COPY src ./src
RUN ./mvnw -B clean package -DskipTests

FROM eclipse-temurin:21-jre
WORKDIR /app

RUN useradd --system --uid 10001 appuser
COPY --from=build /workspace/target/orders-service-0.0.1-SNAPSHOT.jar /app/app.jar

USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Trong pipeline thực tế, không nên mặc định bỏ qua test như ví dụ build image trên nếu test chưa chạy ở stage trước. Có thể chạy `./mvnw clean verify` trước, sau đó build image từ artifact đã xác minh. Cần đảm bảo image cuối cùng chứa đúng artifact đã test, tránh build lại một JAR khác trong Docker stage.

Đối với production, pin base image bằng version cụ thể và cân nhắc digest để kiểm soát chính xác nội dung image. Cập nhật base image theo quy trình bảo mật, không dùng tag `latest` làm định danh release.

### 6.2. Loại trừ file không cần thiết

Ví dụ `.dockerignore`:

```text
.git
.idea
.vscode
target/
*.log
.env
.env.*
secrets/
```

Nếu build cần dùng artifact trong `target/`, hãy điều chỉnh quy trình build và `.dockerignore` nhất quán. Tuyệt đối không đưa file secret vào build context.

### 6.3. Build và chạy image

```bash
docker build -t orders-service:1.4.0 .
docker run --rm -p 8080:8080 \
  -e DB_URL='jdbc:postgresql://host.docker.internal:5432/orders' \
  -e DB_USERNAME='orders_app' \
  -e DB_PASSWORD='local-only-secret' \
  orders-service:1.4.0
```

Thông tin đăng nhập trên chỉ minh họa cho môi trường local. Không dùng secret giả lập hoặc password mẫu trong production.

Kiểm tra image:

```bash
docker image inspect orders-service:1.4.0
docker image ls orders-service
```

Khi push lên registry, tag theo release version và có thể thêm tag theo commit SHA:

```bash
docker tag orders-service:1.4.0 registry.example.com/team/orders-service:1.4.0
docker push registry.example.com/team/orders-service:1.4.0
```

Trong manifest triển khai production, ưu tiên tham chiếu image bằng digest thay vì chỉ dùng tag có thể bị ghi đè.

## 7. Health check và khả năng vận hành

Một service không được xem là sẵn sàng chỉ vì process Java đang chạy. Nền tảng triển khai cần phân biệt:

- **Liveness:** ứng dụng còn hoạt động hay đã rơi vào trạng thái không thể tự phục hồi.
- **Readiness:** ứng dụng đã sẵn sàng nhận traffic hay chưa.
- **Startup:** ứng dụng có đủ thời gian khởi động trước khi liveness bắt đầu kiểm tra hay không.

Spring Boot Actuator hỗ trợ health endpoint và Kubernetes probe. Ví dụ cấu hình:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
```

Các endpoint thường dùng:

- `/actuator/health`
- `/actuator/health/liveness`
- `/actuator/health/readiness`

Chỉ expose endpoint phù hợp với chính sách bảo mật. Không công khai toàn bộ actuator endpoint ra internet. Readiness có thể phụ thuộc vào database hoặc dependency bắt buộc để xử lý request; liveness không nên thất bại chỉ vì một dependency bên ngoài tạm thời chậm, nếu điều đó khiến nền tảng restart service liên tục.

Một service có thể deploy độc lập cần tối thiểu:

- Log có cấu trúc, có correlation/trace ID khi xử lý request liên dịch vụ.
- Metric về request rate, error rate, latency và resource usage.
- Health/readiness endpoint.
- Timeout, retry có giới hạn và circuit breaker phù hợp cho lời gọi mạng.
- Thông tin version/build trong log hoặc endpoint info để nhận diện phiên bản đang chạy.

## 8. Giữ ranh giới dữ liệu để tránh release đồng bộ

Database dùng chung với schema bị nhiều service tùy ý đọc/ghi là một trong các nguyên nhân phổ biến khiến microservice không thể phát hành độc lập.

### 8.1. Service sở hữu dữ liệu của mình

`orders-service` nên sở hữu dữ liệu đơn hàng và quy tắc thay đổi schema của phần dữ liệu đó. Service khác không nên ghi trực tiếp vào bảng nội bộ của orders; nếu cần thông tin, hãy dùng API hoặc event đã công bố.

Có thể cùng sử dụng một cụm database vật lý, nhưng quyền sở hữu logic, schema, migration và quyền truy cập phải rõ ràng. Tách database vật lý không tự động bảo đảm độc lập nếu các service vẫn phải thay đổi cùng nhau.

### 8.2. Migration tương thích ngược

Không triển khai migration phá vỡ consumer cũ trong cùng một bước release. Dùng chiến lược expand-and-contract:

1. **Expand:** thêm cột hoặc bảng mới theo cách phiên bản đang chạy vẫn hoạt động.
2. **Dual compatibility:** ứng dụng có thể đọc/ghi theo cấu trúc cũ và mới trong giai đoạn chuyển tiếp khi cần.
3. **Migrate:** backfill dữ liệu, chuyển dần logic sang cấu trúc mới.
4. **Switch:** xác nhận phiên bản đang chạy không còn phụ thuộc cấu trúc cũ.
5. **Contract:** xóa cột/bảng cũ ở một release sau, khi không còn consumer sử dụng.

Migration phải được version hóa, review và chạy có kiểm soát. Rollback ứng dụng không nhất thiết đồng nghĩa rollback database; migration đã chạy cần có chiến lược tương thích và khôi phục dữ liệu riêng.

## 9. API và event phải tương thích giữa các phiên bản

Một service chỉ deploy độc lập nếu consumer hiện tại vẫn làm việc được khi provider nâng cấp.

### 9.1. Thay đổi API an toàn

Các thay đổi thường ít rủi ro hơn:

- Thêm field response optional mà consumer cũ bỏ qua được.
- Thêm endpoint mới.
- Thêm giá trị mặc định hoặc hành vi mới không làm thay đổi ý nghĩa cũ.
- Tăng giới hạn theo cách không phá vỡ client hiện hữu.

Các thay đổi có nguy cơ breaking:

- Xóa hoặc đổi tên field đang được consumer sử dụng.
- Đổi kiểu dữ liệu hoặc ý nghĩa field.
- Làm một field optional trở thành required.
- Đổi semantics, mã lỗi hoặc quy tắc authorization.
- Thay đổi thứ tự/ý nghĩa message mà consumer dựa vào.

Với breaking change, dùng versioning và giai đoạn chuyển đổi: công bố contract mới, cho consumer migrate, theo dõi traffic cũ, rồi mới loại bỏ contract cũ.

### 9.2. Event schema

Event nên có tên và schema rõ ràng, ví dụ `OrderCreated`. Khi thêm field, ưu tiên field optional có default hoặc cách xử lý tương thích. Không giả định mọi consumer được nâng cấp cùng lúc; message cũ có thể vẫn nằm trong queue sau khi producer đã release.

Consumer cần xử lý event idempotent khi hệ thống có thể giao message nhiều lần. Version schema và kiểm tra compatibility trong CI giúp phát hiện thay đổi nguy hiểm trước khi deploy.

## 10. Kiểm thử để chứng minh service có thể phát hành riêng

Không một loại test đơn lẻ nào chứng minh được independent deployability. Cần kết hợp các tầng kiểm thử.

| Loại kiểm thử | Câu hỏi cần trả lời |
|---|---|
| Unit test | Quy tắc domain/use case có đúng không? |
| Spring slice test | Controller, repository hoặc cấu hình Spring có hoạt động đúng trong phạm vi nhỏ không? |
| Integration test | Service có làm việc với database, broker hoặc adapter thật/giả lập đúng cách không? |
| Contract test | Consumer hiện tại có tiếp tục tương thích với API/event của provider không? |
| Migration test | Schema mới có nâng cấp được và không phá phiên bản đang chạy không? |
| Container test | Image có khởi động, nhận cấu hình và expose health endpoint đúng không? |
| Smoke test | Sau deploy, endpoint quan trọng có phản hồi đúng không? |
| Rollback test | Có thể quay về artifact trước mà không làm mất tính tương thích dữ liệu không? |

### 10.1. Integration test với Testcontainers

Testcontainers cho phép kiểm tra service với dependency thực tế trong container thay vì chỉ dựa vào mock. Ví dụ với PostgreSQL, test có thể xác minh migration, repository query và transaction behavior.

Nguyên tắc:

- Khởi tạo database/container cho test.
- Chạy migration như pipeline production.
- Kiểm tra các truy vấn quan trọng và constraint.
- Dọn dữ liệu sau test hoặc dùng database cô lập.
- Không để test phụ thuộc database production hay dữ liệu dùng chung.

### 10.2. Consumer-driven contract test

Contract test giúp provider thay đổi mà không phải yêu cầu mọi consumer release đồng thời. Consumer mô tả phần API/event mà nó thực sự sử dụng; provider pipeline xác minh phiên bản mới vẫn đáp ứng contract đó.

Contract test không thay thế integration test hoặc end-to-end test. Nó tập trung vào ranh giới giao tiếp và phát hiện breaking change sớm.

## 11. Pipeline CI/CD độc lập cho một service

Pipeline của `orders-service` nên có thể chạy khi có thay đổi trong repository/service này và phát hành đúng artifact của nó.

Một luồng tham khảo:

```text
Commit / Pull Request
        |
        v
Compile + Static Analysis
        |
        v
Unit + Integration + Contract Tests
        |
        v
Build Executable JAR
        |
        v
Build Container Image
        |
        v
Scan Dependencies / Image + Generate SBOM
        |
        v
Push Versioned Image to Registry
        |
        v
Deploy to Staging
        |
        v
Smoke Test + Health Verification
        |
        v
Approval / Progressive Production Rollout
        |
        v
Monitor + Record Release Evidence
```

Pipeline cần bảo đảm:

1. Chỉ build và deploy service được chọn, không ép toàn bộ microservices release cùng lúc.
2. Chạy test và contract verification trước khi phát hành.
3. Gắn version hoặc commit SHA duy nhất cho artifact.
4. Lưu image digest và SBOM để truy xuất nguồn gốc.
5. Promote cùng một image qua staging và production.
6. Dùng cấu hình/secret của từng môi trường tại thời điểm deploy.
7. Chờ readiness và smoke test trước khi tăng traffic.
8. Ghi lại deployment event, người/phê duyệt nếu quy trình yêu cầu, và kết quả sau deploy.

Nếu pipeline hiện tại luôn build toàn bộ repository monolith hoặc bắt buộc deploy tất cả service trong một release train, cần tách pipeline theo service boundary hoặc tạo deployment unit riêng trước khi tuyên bố đã đạt independent deployability.

## 12. Chiến lược triển khai an toàn

Có thể sử dụng rolling deployment, canary hoặc blue-green tùy nền tảng. Dù chọn cách nào, cần có tiêu chí dừng và rollback cụ thể.

### 12.1. Rolling deployment

Thay dần instance cũ bằng instance mới. Readiness probe bảo đảm instance mới chỉ nhận traffic khi đã sẵn sàng. Cần kiểm tra khả năng tương thích giữa phiên bản cũ và mới trong giai đoạn cả hai cùng chạy.

### 12.2. Canary deployment

Chuyển một tỷ lệ nhỏ traffic sang phiên bản mới, theo dõi error rate, latency và business metric trước khi tăng dần tỷ lệ. Nếu vượt ngưỡng, dừng rollout và chuyển traffic về phiên bản ổn định.

### 12.3. Blue-green deployment

Duy trì hai môi trường/version song song, xác minh green rồi chuyển traffic từ blue sang green. Phương án này cần kiểm soát session, dữ liệu và chi phí tài nguyên.

### 12.4. Rollback

Rollback ứng dụng bằng cách triển khai lại image digest đã biết là ổn định, không build lại source cũ một cách tùy tiện. Trước khi rollback cần xác minh schema/data thay đổi vẫn tương thích với phiên bản cũ.

Rollback plan cần nêu rõ:

- Phiên bản/image digest sẽ quay về.
- Ngưỡng lỗi hoặc điều kiện kích hoạt rollback.
- Ai hoặc automation có quyền dừng rollout.
- Cách khôi phục traffic và kiểm tra readiness.
- Cách xử lý migration đã thực hiện.
- Bằng chứng sau rollback: health, error rate, latency và nghiệp vụ quan trọng.

## 13. Bằng chứng cần lưu để chứng minh independent deployability

Một tuyên bố “service deploy độc lập” nên dựa trên bằng chứng có thể kiểm tra lại, không chỉ dựa trên việc pipeline xanh.

| Nhóm bằng chứng | Nội dung cần lưu |
|---|---|
| Source | Repository, commit SHA, branch/tag, version |
| Build | JDK/build tool version, build ID, kết quả build |
| Artifact | JAR checksum, image tag và immutable digest |
| Supply chain | Dependency/image scan, SBOM, nguồn base image |
| Tests | Unit, integration, contract, migration và smoke test result |
| Compatibility | Contract version, consumer compatibility result, schema migration plan |
| Deployment | Service name, environment, deployment ID, image digest, thời điểm |
| Runtime | Readiness/liveness, log, metric, trace và error rate sau rollout |
| Recovery | Phiên bản rollback, thao tác đã thực hiện và kết quả xác minh |

Ví dụ release record tối thiểu:

```text
Service: orders-service
Release: 1.4.0
Commit: <git-sha>
Artifact: registry.example.com/team/orders-service@sha256:<digest>
Build: <ci-build-id>
Tests: unit=PASS, integration=PASS, contract=PASS
Migration: compatible-expand
Environment: staging
Deployment: <deployment-id>
Smoke test: PASS
Rollback target: <previous-image-digest>
```

Các giá trị trong dấu ngoặc nhọn là placeholder, phải thay bằng dữ liệu thực tế từ pipeline. Không ghi release record với trạng thái PASS nếu chưa có kết quả kiểm thử hoặc deployment tương ứng.

## 14. Quy trình thực hành từ đầu đến cuối

Dùng checklist sau cho một lần phát hành thử nghiệm:

1. Xác nhận service có repository/module và owner rõ ràng.
2. Chạy `./mvnw clean verify`; lưu kết quả test.
3. Tạo executable JAR và kiểm tra có thể chạy bằng `java -jar`.
4. Build container image từ artifact đã xác minh.
5. Chạy image bằng cấu hình môi trường riêng, không nhúng secret.
6. Kiểm tra health/readiness và log khởi động.
7. Chạy integration test với database/broker tương ứng.
8. Chạy contract test với các consumer contract hiện hành.
9. Kiểm tra migration tương thích với phiên bản cũ trong giai đoạn rollout.
10. Push image versioned và lưu digest.
11. Deploy riêng service lên staging, không phát hành các service khác.
12. Chạy smoke test, theo dõi error rate và latency.
13. Xác minh có thể dừng rollout và quay lại image trước.
14. Lưu release record cùng artifact, test result và deployment evidence.

Chỉ khi các bước trên được thực hiện thành công và không cần phát hành đồng bộ service khác, mới có cơ sở kết luận service đã chứng minh được khả năng deploy độc lập trong phạm vi đã kiểm tra.

## 15. Những lỗi thường gặp

### Đóng gói được JAR nhưng không chạy được ở môi trường khác

Nguyên nhân thường là cấu hình, file hoặc dependency bị lấy từ máy developer. Khắc phục bằng build tái tạo được, cấu hình runtime tách biệt và kiểm thử container trong môi trường gần production.

### Image có secret hoặc cấu hình production

Điều này tạo rủi ro lộ credential và buộc phải build image mới khi đổi môi trường. Hãy chuyển secret sang secret manager và cấu hình sang runtime.

### Service dùng chung database theo kiểu phụ thuộc bảng nội bộ

Một migration có thể phá nhiều service và buộc release đồng thời. Hãy thiết lập data ownership, API/event contract và migration expand-contract.

### Breaking API hoặc event schema

Provider release mới làm consumer cũ lỗi dù consumer chưa thay đổi. Hãy kiểm tra contract trong CI, version hóa breaking change và duy trì giai đoạn tương thích.

### Build lại image cho từng môi trường

Các môi trường có thể chạy binary khác nhau dù cùng version. Hãy build một lần, lưu digest và promote chính artifact đó.

### Không có rollback thực tế

Có thể deploy phiên bản mới nhưng không thể quay lui vì schema đã bị phá vỡ hoặc artifact cũ không còn. Hãy lưu immutable artifact và thiết kế migration tương thích nhiều phiên bản.

### Chỉ kiểm tra process, không kiểm tra readiness

Container đang chạy không đồng nghĩa service xử lý request được. Hãy sử dụng readiness/liveness đúng mục đích và smoke test sau deploy.

## 16. Checklist hoàn tất

- [ ] Service có build pipeline riêng.
- [ ] Executable JAR được tạo và chạy được.
- [ ] Container image được version hóa và định danh bằng digest.
- [ ] Image không chứa secret hoặc cấu hình môi trường cố định.
- [ ] Cấu hình runtime được cấp từ môi trường triển khai.
- [ ] Health, readiness và liveness hoạt động đúng.
- [ ] Unit và integration test chạy độc lập.
- [ ] Contract test xác minh consumer hiện tại vẫn tương thích.
- [ ] Database migration không buộc service khác release cùng lúc.
- [ ] Pipeline có thể deploy service mà không phát hành toàn bộ hệ thống.
- [ ] Cùng một artifact được promote qua các môi trường.
- [ ] Có smoke test và tiêu chí theo dõi sau deploy.
- [ ] Có artifact/version trước đó và quy trình rollback khả thi.
- [ ] Release evidence có thể truy xuất từ commit đến deployment.

## 17. Kết luận

Đóng gói là bước tạo ra một deployable artifact; independent deployability là thuộc tính của toàn bộ ranh giới dịch vụ, dữ liệu, hợp đồng giao tiếp và quy trình vận hành. Với Java và Spring, executable JAR và Docker image tạo nền tảng kỹ thuật, nhưng bằng chứng quan trọng nhất là service có thể được build, test, promote, deploy, theo dõi và rollback riêng trong khi các consumer và service khác tiếp tục hoạt động.

Một microservice chỉ thực sự độc lập khi thay đổi của nó có thể đi qua một vòng đời phát hành riêng, có kiểm soát và có thể truy xuất bằng chứng — không chỉ khi nó có một container riêng.
