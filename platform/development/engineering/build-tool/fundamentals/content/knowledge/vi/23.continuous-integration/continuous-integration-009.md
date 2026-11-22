# Build một lần và chuyển đúng artifact qua các môi trường

Trong một quy trình CI/CD, cùng một phiên bản ứng dụng thường đi qua nhiều môi trường: kiểm thử tích hợp, staging, pre-production rồi production. Một nguyên tắc quan trọng là **build artifact một lần, sau đó chuyển chính artifact đó qua các môi trường**. Mỗi môi trường cung cấp cấu hình và secret riêng khi chạy ứng dụng; pipeline không biên dịch hoặc đóng gói lại source chỉ để tạo một file khác cho môi trường tiếp theo.

Ví dụ, commit `a1b2c3d` tạo ra `order-service-2.4.0.jar`. Pipeline kiểm thử chính file JAR này ở staging, rồi đưa cùng file đó lên production. Nếu production build lại từ cùng commit, artifact mới vẫn có thể khác vì JDK, dependency metadata, timestamp, build plugin, biến môi trường hoặc trạng thái repository đã thay đổi.

Mục tiêu của quy trình build once, promote many là giữ mối liên hệ rõ ràng giữa source revision, artifact đã kiểm thử và artifact đang chạy. Điều này giúp giảm khác biệt giữa các môi trường, hỗ trợ rollback và cung cấp bằng chứng để điều tra khi có sự cố.

## 1. Build một lần, promote nhiều lần nghĩa là gì?

Quy trình này tách hai hoạt động:

- **Build:** biến source code và các đầu vào đã kiểm soát thành artifact có version/định danh cụ thể.
- **Promote:** đưa artifact đã tạo và đã xác minh sang giai đoạn hoặc môi trường tiếp theo mà không thay đổi nội dung artifact.

Luồng khái quát:

```text
Source revision
      |
      v
CI build + tests
      |
      v
Immutable artifact
      |
      v
Store in artifact repository
      |
      v
Deploy to test/staging
      |
      v
Verify the same artifact
      |
      v
Promote to production
      |
      v
Run with production configuration
```

Artifact có thể là JAR, WAR, ZIP distribution, native executable hoặc container image. Điều quan trọng là định danh và nội dung của sản phẩm được giữ nguyên trong suốt quá trình promotion.

### 1.1. Không build lại cho từng môi trường

Một cách làm dễ gặp nhưng rủi ro là chạy:

```text
Build for test       -> order-service-test.jar
Build for staging    -> order-service-staging.jar
Build for production -> order-service-prod.jar
```

Ba file có thể được tạo từ cùng source revision nhưng không nhất thiết giống nhau. Chúng có thể khác dependency, build flag, generated resource, timestamp hoặc giá trị cấu hình được nhúng lúc build.

Với build once, pipeline tạo một artifact:

```text
Build once -> order-service-2.4.0.jar
                 |
                 +--> deploy to test
                 |
                 +--> promote to staging
                 |
                 +--> promote to production
```

Mỗi môi trường có thể dùng endpoint, credential, feature flag và giới hạn tài nguyên khác nhau. Những giá trị đó được cung cấp khi triển khai hoặc khi ứng dụng chạy, không cần tạo một JAR riêng cho từng môi trường.

## 2. Vì sao cùng source build lại nhiều lần vẫn có thể tạo artifact khác?

Cùng một commit không đảm bảo mọi lần build tạo cùng byte. Các yếu tố có thể làm artifact thay đổi:

- JDK, compiler, Gradle/Maven hoặc plugin version khác nhau.
- Dependency động, SNAPSHOT hoặc metadata repository thay đổi.
- Generated resource chứa build time, hostname, username hoặc đường dẫn workspace.
- Timestamp và thứ tự file trong archive khác nhau.
- Biến môi trường/profile làm thay đổi nội dung được đóng gói.
- Một task đọc trạng thái bên ngoài mà không khai báo input.
- Build script hoặc dependency được tải từ nguồn không cố định.

Ngay cả khi dự án có reproducible build và hai lần build tạo byte giống nhau, build lại ở mỗi môi trường vẫn tăng chi phí và tạo thêm cơ hội sai lệch. Build once giúp dùng một kết quả đã được tạo và kiểm tra làm đơn vị promotion.

Reproducible build và build once là hai khái niệm bổ sung:

| Khái niệm | Câu hỏi chính |
|---|---|
| Reproducible build | Cùng đầu vào có thể tạo lại artifact giống nhau không? |
| Build once, promote many | Các môi trường có đang chạy đúng artifact đã được build và kiểm tra không? |

Một tổ chức có thể cần cả hai: tạo artifact có thể tái lập, sau đó lưu và promote đúng artifact đó.

## 3. Artifact là đơn vị được chuyển qua pipeline

Artifact là sản phẩm đầu ra được đóng gói và lưu trữ để các bước sau sử dụng. Với Java, thường gặp:

| Artifact | Ví dụ | Cách triển khai thường gặp |
|---|---|---|
| Library JAR | `order-domain-2.4.0.jar` | Publish vào Maven repository để ứng dụng khác dùng |
| Executable JAR | `order-service-2.4.0.jar` | Chạy bằng `java -jar` hoặc script |
| WAR | `order-service-2.4.0.war` | Deploy lên servlet container/application server |
| Distribution ZIP | `order-service-2.4.0.zip` | Giải nén và chạy script trong `bin/` |
| Container image | `registry.example.com/order-service:2.4.0` | Deploy image theo digest hoặc immutable reference |

Artifact nên có định danh duy nhất, gắn với version và source revision. Không nên ghi đè một release đã phát hành bằng nội dung khác nhưng giữ nguyên tọa độ/version.

## 4. Phân biệt artifact, cấu hình môi trường và secret

Để dùng cùng artifact ở nhiều môi trường, cần tách phần bất biến khỏi phần thay đổi theo môi trường.

**Artifact** chứa code đã compile, resource mặc định không nhạy cảm và metadata phát hành.

**Environment configuration** chứa giá trị vận hành theo môi trường, ví dụ database URL, endpoint dịch vụ, feature flag, port và mức log.

**Secret** chứa password, API token, private key hoặc credential. Secret được cấp qua secret manager, biến môi trường bảo vệ hoặc cơ chế mount an toàn khi deploy.

| Loại dữ liệu | Ví dụ | Nơi cung cấp phù hợp |
|---|---|---|
| Code và thư viện | `OrderService.class`, dependency JAR | Artifact |
| Default không nhạy cảm | Tên ứng dụng, giá trị timeout mặc định | Artifact hoặc config mặc định |
| Database endpoint | `jdbc:postgresql://staging-db/...` | Runtime configuration |
| Feature flag | Bật/tắt tính năng theo môi trường | Runtime config/feature management |
| Database password | Mật khẩu kết nối | Secret manager/secret injection |
| Signing key | Private key ký artifact | Hệ thống ký/secret manager, không đóng gói vào JAR |

Nếu URL database hoặc credential được nhúng vào JAR lúc build, mỗi môi trường cần một artifact khác nhau và secret có nguy cơ bị phát hành cùng file. Hãy để ứng dụng đọc cấu hình khi chạy.

### 4.1. Đọc cấu hình qua environment variable

Ví dụ Java đơn giản:

```java
public final class DatabaseSettings {
    public static String jdbcUrl() {
        String value = System.getenv("DATABASE_URL");
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("DATABASE_URL is required");
        }
        return value;
    }
}
```

Khi chạy cùng JAR ở staging:

```bash
DATABASE_URL='jdbc:postgresql://staging-db:5432/orders' \
  java -jar order-service-2.4.0.jar
```

Ở production, cùng JAR được chạy với giá trị do hệ thống triển khai cấp:

```bash
DATABASE_URL='jdbc:postgresql://production-db:5432/orders' \
  java -jar order-service-2.4.0.jar
```

Ví dụ trên minh họa biến môi trường; không nên đặt password thật trực tiếp trong command line vì command/process metadata có thể bị quan sát. Secret nên được cấp bằng cơ chế an toàn của nền tảng.

### 4.2. Dùng file cấu hình ngoài artifact

Ứng dụng cũng có thể nhận đường dẫn cấu hình lúc khởi động:

```bash
java -jar order-service-2.4.0.jar \
  --spring.config.additional-location=file:/etc/order-service/application.yml
```

Đây là ví dụ cho ứng dụng Spring Boot. File cấu hình được mount hoặc cung cấp bởi môi trường triển khai. Cùng artifact có thể dùng các file cấu hình khác nhau ở staging và production.

Không nên sửa trực tiếp nội dung JAR sau khi build để thay config. Nếu cần config ngoài, hãy xác định rõ đường dẫn và precedence của nó trong ứng dụng.

## 5. Tạo artifact một lần trong Gradle

Với Gradle Java plugin, task `build` thường tạo JAR và chạy các verification task được nối vào lifecycle. CI có thể tạo artifact sau khi kiểm tra:

```bash
./gradlew clean check build
```

Trong Java plugin, `build` phụ thuộc vào các task verification và assembly tương ứng. Nếu dự án đã cấu hình `check` để bao gồm unit test, integration test, static analysis và kiểm tra artifact, có thể dùng một entry point chuẩn như:

```bash
./gradlew clean build
```

Artifact thường nằm trong:

```text
build/libs/
```

Tên file phụ thuộc project name, version, classifier và archive configuration. Nên lấy đường dẫn từ task output provider thay vì giả định tên file.

### 5.1. Dùng Gradle Application plugin

Nếu tạo ứng dụng có distribution, có thể dùng:

```groovy
plugins {
    id 'application'
}

group = 'com.example'
version = '2.4.0'

application {
    mainClass = 'com.example.orders.Application'
}
```

Tạo distribution:

```bash
./gradlew clean check installDist
```

Distribution được tạo dưới `build/install/` với cấu trúc thường gồm `bin/` và `lib/`. CI có thể lưu nguyên archive distribution làm artifact promotion. Không tạo lại distribution riêng ở mỗi môi trường.

### 5.2. Đóng gói cấu hình mặc định và cấu hình runtime

Resource mặc định không nhạy cảm có thể nằm trong `src/main/resources`. Giá trị riêng môi trường như database URL nên được override từ environment variable hoặc file ngoài.

Không dùng build profile để tạo JAR khác nhau chỉ nhằm thay endpoint production/staging nếu cùng một artifact có thể nhận các giá trị này khi chạy.

## 6. Tạo artifact một lần trong Maven

Với Maven, `package` tạo artifact trong `target/`, còn `verify` chạy các kiểm tra được cấu hình ở các phase trước đó và tại phase verify.

Ví dụ:

```bash
mvn clean verify
```

Artifact JAR thường nằm trong:

```text
target/<artifactId>-<version>.jar
```

Nếu dùng Maven Failsafe cho integration test, chạy `verify` để thực hiện cả phase integration-test và xác nhận kết quả test theo cấu hình plugin.

### 6.1. Publish artifact vào repository

Maven có lifecycle phase `deploy` để publish artifact và metadata lên remote repository đã cấu hình. Thực tế nên tách build/verification khỏi quyền publish, hoặc chỉ chạy deploy sau khi verification thành công.

Ví dụ lệnh publish:

```bash
mvn deploy
```

Trong pipeline, có thể build và verify một lần, sau đó publish chính output đó. Nếu CI chạy lại Maven trong một job khác để publish, cần bảo đảm job dùng đúng artifact đã lưu từ job build, không âm thầm compile/package lại source.

Với Maven multi-module, `install` đưa artifact vào local repository của runner; `deploy` đưa artifact lên remote repository. Chúng có vai trò khác nhau. Local repository không phải nơi promotion chung giữa các môi trường.

### 6.2. Gradle publish

Với `maven-publish`, có thể publish component đã tạo:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example'
version = '2.4.0'

publishing {
    publications {
        create('mavenJava', MavenPublication) {
            from components.java
        }
    }

    repositories {
        maven {
            name = 'internal'
            url = uri('https://repo.example.com/releases')
            credentials {
                username = providers.environmentVariable('REPO_USER').orNull
                password = providers.environmentVariable('REPO_TOKEN').orNull
            }
        }
    }
}
```

Sau khi cấu hình, task publish tương ứng có thể đưa artifact và metadata lên repository. URL và credential ở ví dụ là placeholder; secret phải được cấp an toàn trong CI.

Trong mô hình build once, bước publish/promote cần sử dụng đúng output đã qua verification. Không nên thay version hoặc dependency sau khi staging đã kiểm thử artifact.

## 7. Lưu artifact vào nơi có thể truy xuất lại

Artifact không nên chỉ nằm trong workspace tạm của CI. Sau khi build và kiểm tra, pipeline cần lưu sản phẩm ở một nơi có retention và quyền truy cập rõ ràng.

Các lựa chọn thường gặp:

- Maven repository manager như Nexus hoặc Artifactory.
- Package registry của nền tảng source hosting.
- CI artifact storage có retention phù hợp.
- Container registry cho OCI image.
- Object storage có versioning và access control.

Nơi lưu cần hỗ trợ:

- Định danh artifact rõ ràng.
- Download đúng version hoặc digest.
- Kiểm soát quyền publish và read.
- Retention/retention policy phù hợp.
- Checksum hoặc chữ ký.
- Audit log về ai publish và ai tải artifact.

### 7.1. CI artifact storage và artifact repository khác nhau

CI artifact storage thường lưu file đính kèm của một lần chạy pipeline, chẳng hạn test report, log và JAR. Artifact repository chuyên quản lý package theo tọa độ/version, metadata và dependency resolution.

| Đặc điểm | CI artifact storage | Artifact repository |
|---|---|---|
| Định danh | Run/job/build ID | Group/artifact/version/classifier hoặc image digest |
| Mục tiêu | Chia sẻ output giữa các job và lưu bằng chứng pipeline | Phân phối package lâu dài cho consumer/deployment |
| Dependency resolution | Thường không phải chức năng chính | Có metadata và protocol cho package manager |
| Retention | Thường theo thời hạn CI | Theo chính sách release/package |
| Promotion | Có thể tải artifact từ run cụ thể | Có thể promote/copy package giữa repository/stage |

Một pipeline có thể dùng CI artifact storage để chuyển output giữa job, rồi publish vào repository chính thức sau khi verification đạt.

## 8. Định danh artifact bằng version và checksum

Một artifact cần có định danh ổn định. Với Maven coordinates:

```text
groupId:    com.example
artifactId: order-service
version:    2.4.0
classifier: (none)
extension:  jar
```

Artifact path trong Maven repository thường phản ánh groupId, artifactId và version. Ví dụ:

```text
com/example/order-service/2.4.0/order-service-2.4.0.jar
```

Không nên ghi đè nội dung của `2.4.0` sau khi release. Nếu cần sửa code, phát hành version mới như `2.4.1` hoặc version theo chính sách của tổ chức.

### 8.1. Checksum xác nhận nội dung

Tính SHA-256 sau khi build:

```bash
sha256sum build/libs/order-service-2.4.0.jar
```

PowerShell:

```powershell
Get-FileHash .\build\libs\order-service-2.4.0.jar -Algorithm SHA256
```

Khi artifact được tải xuống ở bước deploy, tính lại checksum và so sánh với giá trị đã lưu từ bước build. Nếu khác, dừng promotion và điều tra.

Checksum chứng minh file nhận được có cùng nội dung byte với file đã tính hash. Nó không tự xác minh ai đã tạo artifact; để xác minh nguồn gốc, cần chữ ký hoặc provenance được tin cậy.

### 8.2. Không dùng tag mutable làm định danh duy nhất

Với container image, tag như `latest`, `staging` hoặc `2.4.0` có thể được cập nhật để trỏ sang image khác tùy registry policy. Nếu pipeline deploy chỉ ghi tag, có thể vô tình chạy nội dung khác sau khi tag bị thay đổi.

OCI image digest định danh nội dung image manifest, ví dụ:

```text
registry.example.com/order-service@sha256:<digest>
```

Promotion nên giữ cùng digest. Tag có thể được thêm để con người dễ đọc, nhưng digest là tham chiếu nội dung bất biến hơn.

## 9. Promotion là thay đổi trạng thái, không phải build lại

Promotion là việc cho phép artifact đã được kiểm tra đi tới môi trường tiếp theo hoặc gắn nó với một kênh phát hành. Tùy nền tảng, promotion có thể là:

- Copy artifact từ repository staging sang repository release mà không thay đổi bytes.
- Thay đổi metadata/approval state trong hệ thống phát hành.
- Cập nhật deployment manifest để trỏ tới version/digest đã xác minh.
- Cấp quyền truy cập artifact cho môi trường production.

Khi copy artifact giữa repository, cần xác nhận checksum ở nguồn và đích giống nhau. Một số repository manager hỗ trợ promote repository/build hoặc chuyển package giữa hosted repositories; cơ chế cụ thể phụ thuộc sản phẩm.

Không nên tải source revision rồi chạy `mvn package` hoặc `gradle build` một lần nữa trong bước production deployment. Nếu production cần file khác, cần xem lại ranh giới artifact và runtime configuration.

## 10. Kiểm tra artifact trước khi promotion

Artifact cần qua các kiểm tra phù hợp trước khi được phép promotion.

Các kiểm tra thường gặp:

- Unit test và integration test trong build pipeline.
- Static analysis, dependency/license/security scan.
- Kiểm tra manifest, class, resource và cấu trúc archive.
- Kiểm tra checksum hoặc chữ ký.
- Smoke test trên artifact đã đóng gói.
- Consumer test cho library đã publish.
- Deployment test trên môi trường tương thích.
- Kiểm tra SBOM và provenance theo chính sách.

Điểm quan trọng là test staging phải chạy trên artifact đã lưu, và artifact được promote phải có cùng checksum/digest với file đã test.

### 10.1. Không chỉ test source output

Unit test chạy từ `build/classes` hoặc `target/classes` có thể pass dù JAR thiếu resource hoặc dependency. Vì vậy, nên có một bước chạy thử sản phẩm đã đóng gói khi rủi ro packaging đáng kể.

Ví dụ:

```bash
java -jar build/libs/order-service-2.4.0.jar --self-test
```

Hoặc deploy JAR/WAR/container image vào môi trường staging và gọi health endpoint/luồng nghiệp vụ tối thiểu.

### 10.2. Kiểm thử lại ở môi trường tiếp theo có thay artifact không?

Có thể chạy smoke test ở staging và production-like environment nhiều lần, nhưng luôn sử dụng cùng artifact. Các kiểm tra có thể khác vì cấu hình, dependency service và tải môi trường khác nhau; nội dung package không được thay đổi.

## 11. Cấu hình runtime theo môi trường

Một ứng dụng thường cần các giá trị khác nhau ở mỗi môi trường. Nên thiết kế một cơ chế cấu hình có precedence rõ ràng.

Ví dụ:

```text
Artifact:
  order-service-2.4.0.jar

Test environment:
  DATABASE_URL -> test database
  PAYMENT_API  -> mock/test endpoint
  LOG_LEVEL    -> DEBUG

Staging environment:
  DATABASE_URL -> staging database
  PAYMENT_API  -> staging endpoint
  LOG_LEVEL    -> INFO

Production environment:
  DATABASE_URL -> production database
  PAYMENT_API  -> production endpoint
  LOG_LEVEL    -> WARN
```

Các giá trị được cung cấp bởi deployment platform, environment variable, mounted configuration hoặc configuration service.

### 11.1. Tránh profile build tạo artifact riêng

Maven profiles hoặc Gradle properties có thể ảnh hưởng build. Chúng phù hợp khi cần chọn toolchain, bật plugin hoặc cấu hình quy trình build theo mục đích. Nhưng nếu profile chỉ thay endpoint/credential của môi trường, nó có thể khiến artifact khác nhau theo môi trường.

Ví dụ không nên dùng profile để nhúng database URL production vào resource lúc package:

```xml
<profiles>
  <profile>
    <id>production</id>
    <properties>
      <database.url>jdbc:postgresql://prod-db/orders</database.url>
    </properties>
  </profile>
</profiles>
```

Nếu resource được lọc bằng property này trong build, JAR production sẽ khác JAR staging. Hãy ưu tiên để ứng dụng đọc `DATABASE_URL` lúc chạy hoặc nhận file cấu hình ngoài.

### 11.2. Secret không thuộc artifact

Không đóng gói password, token, private key hoặc credential vào JAR, WAR, Docker image layer hay file cấu hình version control. Secret cần được cung cấp từ secret manager hoặc hệ thống triển khai và có quyền truy cập tối thiểu.

Nếu secret bị đưa vào artifact, việc đổi môi trường hoặc xóa secret khỏi source sau đó không xóa giá trị đã phát hành trong package cũ. Cần thu hồi secret và phát hành lại theo quy trình bảo mật phù hợp.

## 12. Database migration và tương thích giữa các phiên bản

Build once không có nghĩa mọi thứ trong môi trường đều giống nhau. Database schema, message format và dịch vụ phụ thuộc có thể khác giữa staging và production.

Khi promote artifact, cần xác nhận migration tương thích:

- Migration được version hóa và đi cùng release hoặc được quản lý bởi công cụ riêng.
- Thứ tự chạy migration được kiểm soát.
- Migration tương thích với ứng dụng đang chạy trong giai đoạn rolling deployment.
- Có kế hoạch rollback hoặc forward-fix nếu migration không thể đảo ngược.
- Staging sử dụng schema gần với production để phát hiện vấn đề trước khi promote.

Với triển khai rolling/blue-green, có thể cần chiến lược expand-and-contract:

1. Thêm cột/bảng mới mà phiên bản cũ vẫn hoạt động.
2. Deploy phiên bản mới dùng cấu trúc mới.
3. Chuyển traffic và quan sát.
4. Sau khi không còn instance cũ, loại bỏ cấu trúc cũ ở một release sau.

Điều này giúp tránh việc một artifact mới yêu cầu schema thay đổi phá vỡ các instance cũ đang phục vụ.

## 13. Artifact promotion với container image

Nhiều ứng dụng Java được đóng gói thành container image. Trong trường hợp này, build once cần giữ nguyên image digest qua các môi trường.

Ví dụ quy trình:

```text
Source + Dockerfile + dependencies
               |
               v
       Build image once
               |
               v
       Push to registry
               |
               v
       Record image digest
               |
               v
       Deploy same digest to staging
               |
               v
       Verify and approve
               |
               v
       Deploy same digest to production
```

Ví dụ build và push:

```bash
docker build -t registry.example.com/order-service:2.4.0 .
docker push registry.example.com/order-service:2.4.0
```

Sau khi push, lấy digest từ registry/build output theo công cụ đang dùng. Khi deploy, ưu tiên tham chiếu:

```text
registry.example.com/order-service@sha256:<digest>
```

Không build lại image từ Dockerfile ở mỗi môi trường. Nếu build lại, base image tag, package repository, build arguments hoặc layer cache có thể thay đổi.

### 13.1. Config không nên được nhúng vào image theo môi trường

Docker image nên chứa ứng dụng và dependency cần thiết. Endpoint, secret và cấu hình riêng môi trường nên được cung cấp khi tạo container qua environment variable, secret mount, config map hoặc cơ chế tương ứng của nền tảng.

Ví dụ:

```bash
docker run --rm \
  -e DATABASE_URL='jdbc:postgresql://staging-db:5432/orders' \
  registry.example.com/order-service@sha256:<digest>
```

Ví dụ chỉ minh họa cách truyền biến không nhạy cảm; không đưa password thật vào command line hoặc image. Dùng secret injection của nền tảng.

## 14. Provenance, SBOM và chữ ký artifact

Khi artifact được chuyển qua nhiều môi trường, cần biết nó được tạo từ đâu và có bị thay đổi không.

**Provenance** mô tả nguồn gốc artifact: source revision, build system, workflow, builder identity và các đầu vào liên quan.

**SBOM (Software Bill of Materials)** liệt kê thành phần phần mềm/dependency có trong sản phẩm hoặc được sử dụng để tạo sản phẩm theo phạm vi của công cụ.

**Chữ ký artifact** giúp xác minh artifact được ký bởi identity/key được tin cậy và nội dung không bị thay đổi sau khi ký.

Một pipeline có thể:

1. Build artifact từ commit cụ thể.
2. Tạo SBOM.
3. Tạo provenance/attestation gắn với digest artifact.
4. Scan dependency và artifact.
5. Ký artifact hoặc image theo chính sách.
6. Lưu artifact và metadata.
7. Xác minh chữ ký/provenance trước khi deploy production.

Không nên ký lại một artifact sau mỗi môi trường nếu chữ ký được dùng để xác định nội dung phát hành. Nếu có metadata promotion riêng, lưu metadata đó bên ngoài artifact và gắn với digest.

## 15. Rollback bằng artifact đã phát hành

Nếu production gặp sự cố, rollback nên trỏ về artifact version/digest trước đó đã được lưu và kiểm thử. Không nên build lại commit cũ trong lúc sự cố đang diễn ra nếu artifact đã phát hành vẫn còn sẵn.

Ví dụ:

```text
Production hiện tại: order-service 2.4.1 (digest X)
Phiên bản trước:     order-service 2.4.0 (digest Y)

Rollback:
  Deploy lại đúng digest Y
```

Rollback chỉ an toàn nếu ứng dụng và database schema tương thích. Nếu migration đã xóa/đổi dữ liệu không thể đảo ngược, có thể cần forward-fix hoặc quy trình phục hồi dữ liệu thay vì chỉ đổi artifact.

Giữ artifact cũ theo retention policy đủ dài để phục vụ rollback và điều tra. Không ghi đè version cũ trong repository.

## 16. Kiểm soát promotion giữa các môi trường

Mỗi môi trường có thể có gate riêng:

| Giai đoạn | Kiểm tra/điều kiện thường gặp |
|---|---|
| Build | Compile, unit test, static analysis, package |
| Artifact verification | Kiểm tra nội dung, checksum, chữ ký, SBOM |
| Integration/test | Integration test và contract test trên artifact đã đóng gói |
| Staging | Smoke test, migration rehearsal, kiểm tra cấu hình và observability |
| Approval | Review kết quả, change record hoặc phê duyệt theo chính sách |
| Production | Deploy cùng digest/version, health/readiness và theo dõi sau phát hành |

Promotion gate có thể kiểm tra metadata và kết quả test liên kết với artifact digest. Không nên chỉ kiểm tra tên version vì cùng tên tag có thể bị ghi đè nếu repository không áp dụng immutability.

## 17. Ví dụ pipeline tổng quát

Pseudocode dưới đây minh họa cách tách build và deploy:

```text
JOB: build
  checkout source revision
  setup pinned JDK and build tool
  run clean verification
  create application artifact
  inspect archive
  run packaged-artifact smoke test
  calculate SHA-256
  upload artifact + checksum + reports

JOB: deploy-staging
  download artifact from build job
  verify SHA-256
  inject staging configuration/secrets
  deploy exact artifact
  run staging smoke/integration checks
  record approval evidence

JOB: deploy-production
  download same artifact by immutable ID/digest
  verify SHA-256 again
  inject production configuration/secrets
  deploy exact artifact
  run health/readiness checks
  record deployed version/digest
```

Điểm quan trọng:

- Job deploy không checkout source rồi chạy build lại.
- Artifact được lấy từ một build ID/version/digest cụ thể.
- Checksum được xác minh sau mỗi lần chuyển nếu file đi qua storage/copy boundary.
- Cấu hình và secret được cấp riêng theo môi trường.
- Kết quả test/staging được liên kết với cùng artifact identity.

## 18. Ví dụ dùng CI artifact giữa các job

Tên action/task cụ thể phụ thuộc nền tảng CI, nhưng logic có thể biểu diễn như sau:

```yaml
jobs:
  build:
    steps:
      - checkout
      - setup-java
      - run: ./gradlew clean build
      - run: sha256sum build/libs/order-service-2.4.0.jar > artifact.sha256
      - upload-artifact:
          path: |
            build/libs/order-service-2.4.0.jar
            artifact.sha256

  deploy-staging:
    needs: build
    steps:
      - download-artifact
      - run: sha256sum --check artifact.sha256
      - run: deploy-to-staging order-service-2.4.0.jar

  deploy-production:
    needs: deploy-staging
    steps:
      - download-same-build-artifact
      - run: sha256sum --check artifact.sha256
      - run: deploy-to-production order-service-2.4.0.jar
```

Đây là YAML minh họa, không phải cấu hình copy/paste cho một CI vendor cụ thể. Cú pháp upload/download và cách truyền file giữa job phải theo nền tảng đang dùng. Cần bảo đảm `deploy-production` tải đúng artifact của job build ban đầu, không tải một file mới nhất theo tên chung hoặc chạy lại build.

### 18.1. Dùng build ID hoặc artifact digest

Không nên deploy bằng cách tìm “artifact mới nhất” trong một thư mục dùng chung. Hai pipeline chạy đồng thời có thể ghi đè hoặc chọn nhầm file.

Hãy liên kết artifact với:

- CI run/build ID.
- Source commit.
- Release version.
- SHA-256 hoặc OCI digest.
- Repository coordinates.

Deployment record nên ghi ít nhất version/digest và môi trường đã triển khai.

## 19. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm phù hợp |
|---|---|---|
| Build lại ở staging và production | Artifact có thể khác dù cùng source commit | Build một lần, lưu artifact và promote đúng file |
| Dùng profile để nhúng endpoint/secret | Mỗi môi trường nhận JAR khác nhau; secret có thể lọt vào package | Cấp runtime config và secret khi deploy |
| Deploy tag `latest` | Tag có thể trỏ sang image khác theo thời gian | Deploy theo immutable digest |
| Ghi đè release version | Cùng version nhưng nội dung thay đổi, gây khó truy vết | Release version bất biến; phát hành version mới khi sửa |
| Chỉ lưu artifact trong workspace tạm | Không thể truy xuất lại sau khi job kết thúc | Lưu vào CI artifact storage/repository có retention |
| Test source nhưng không test artifact | Có thể bỏ sót lỗi đóng gói/runtime | Chạy smoke/consumer test trên artifact đã tạo |
| Copy artifact nhưng không kiểm tra checksum | File có thể bị thay đổi hoặc lấy nhầm | Tính và xác minh digest ở mỗi boundary quan trọng |
| Job production tự checkout rồi package | Tạo một artifact mới không phải artifact đã test | Download artifact từ build job theo ID/digest |
| Không lưu provenance/SBOM | Khó xác định source/dependency đã tạo sản phẩm | Lưu metadata và attestation gắn với digest |
| Rollback bằng cách build commit cũ | Có thể tạo output khác artifact cũ đã phát hành | Dùng lại artifact cũ đã lưu và xác minh |
| Chỉ đổi artifact mà bỏ qua database migration | Ứng dụng có thể không tương thích schema | Quản lý migration và compatibility theo release |

## 20. Quy trình thiết kế build-once promotion cho dự án Java

Có thể áp dụng các bước sau:

1. **Xác định artifact phát hành:** JAR, WAR, distribution hay container image; định nghĩa version/digest.
2. **Tách cấu hình môi trường:** endpoint, feature flag và secret được cấp lúc deploy/runtime.
3. **Cố định đầu vào build:** source revision, JDK/toolchain, wrapper, plugin và dependency.
4. **Chạy verification:** compile, unit/integration test, static analysis và kiểm tra cần thiết.
5. **Đóng gói một lần:** tạo artifact từ build đã xác minh.
6. **Kiểm tra artifact:** archive layout, manifest, dependency, smoke test và metadata.
7. **Tạo bằng chứng:** checksum, chữ ký, SBOM và provenance theo yêu cầu.
8. **Lưu artifact bất biến:** CI artifact storage hoặc package/container registry.
9. **Deploy staging bằng artifact đã lưu:** xác minh checksum/digest trước khi triển khai.
10. **Kiểm thử staging:** dùng cấu hình staging và ghi kết quả gắn với artifact identity.
11. **Promote sau approval:** giữ nguyên artifact/digest, chỉ thay trạng thái hoặc deployment target.
12. **Deploy production:** cấp config/secret production, kiểm tra health và ghi nhận version/digest.
13. **Giữ khả năng rollback:** lưu artifact trước đó và đánh giá tương thích schema/data.

## 21. Ví dụ thực tế cho ứng dụng Spring Boot

Giả sử CI tạo:

```text
order-service-2.4.0.jar
SHA-256: <recorded-digest>
Source commit: a1b2c3d
```

Artifact được lưu vào repository release hoặc CI artifact storage. Ở staging:

```bash
java -jar order-service-2.4.0.jar \
  --spring.config.additional-location=file:/etc/order-service/staging.yml
```

File `staging.yml` chứa endpoint staging và tham chiếu secret được cấp bởi môi trường. Sau khi smoke test và integration test đạt, pipeline promote cùng JAR sang production:

```bash
java -jar order-service-2.4.0.jar \
  --spring.config.additional-location=file:/etc/order-service/production.yml
```

JAR không thay đổi. Chỉ cấu hình runtime và các dịch vụ mà ứng dụng kết nối khác nhau. Deployment record lưu version, digest, commit và thời điểm triển khai.

## 22. Kết luận

Build một lần và chuyển đúng artifact qua các môi trường giúp mọi giai đoạn của CI/CD kiểm tra và triển khai cùng một sản phẩm. CI tạo artifact từ source revision và toolchain đã kiểm soát, chạy test/verification, kiểm tra nội dung, tính checksum và lưu vào nơi có thể truy xuất lại. Các bước staging và production tải đúng artifact theo version hoặc digest, xác minh nội dung rồi triển khai.

Khác biệt giữa môi trường nên được thể hiện bằng runtime configuration và secret injection. Không nên build lại hoặc sửa trực tiếp JAR/image để nhúng endpoint và credential riêng. Với container, dùng image digest để giữ đúng nội dung; với Maven/Gradle artifact, dùng tọa độ version bất biến và checksum để xác nhận file.

Khi kết hợp artifact immutability, kiểm thử trên package đã đóng gói, provenance, approval gate và kế hoạch rollback, pipeline có thể chứng minh rõ source nào tạo ra sản phẩm nào và chính sản phẩm đó đã được chuyển tới môi trường đang chạy.
