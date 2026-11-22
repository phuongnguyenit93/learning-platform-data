# Cache, artifact và tối ưu thời gian build Java

Một pipeline Java có thể mất phần lớn thời gian để tải dependency, biên dịch lại mã không đổi, chạy kiểm thử lặp lại hoặc đóng gói container với những layer luôn bị tạo mới. Khi đội ngũ phát hành thường xuyên, vài phút chậm ở mỗi build sẽ tích lũy thành thời gian chờ lớn và làm giảm tốc độ phản hồi khi sửa lỗi.

Tối ưu build trên Google Cloud cần phân biệt ba việc: **cache** để tránh tính toán hoặc tải lại dữ liệu đã có, **artifact** để lưu và phân phối đầu ra build có phiên bản, và **pipeline** để thực hiện các bước đúng thứ tự với tài nguyên phù hợp. Cloud Build cung cấp môi trường thực thi pipeline; Artifact Registry lưu package và container image; Maven hoặc Gradle quản lý dependency và quá trình build Java. Khi kết hợp đúng, nhóm có thể giảm thời gian build mà vẫn giữ tính tái lập, khả năng kiểm tra và an toàn chuỗi cung ứng phần mềm.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt dependency cache, build cache, Docker layer cache và artifact repository.
- Thiết kế cache cho Maven và Gradle khi build trên Cloud Build.
- Sử dụng Artifact Registry để proxy dependency và lưu package/container image.
- Tổ chức Dockerfile Java theo thứ tự layer giúp tận dụng cache.
- Đo thời gian từng bước và chọn điểm tối ưu có tác động lớn.
- Bảo vệ cache khỏi cache poisoning và không đưa secret vào artifact.
- Tạo artifact có version/digest ổn định, có thể truy vết và promote qua các môi trường.
- Cân bằng tốc độ, chi phí, tính tái lập và bảo mật trong pipeline CI/CD.

## 1. Hiểu đúng cache và artifact

Cache và artifact thường được nhắc cùng nhau nhưng có vòng đời khác nhau.

| Thành phần | Mục đích | Có thể xóa và tạo lại? | Ví dụ |
|---|---|---|---|
| Dependency cache | Giữ thư viện đã tải để không phải tải lại từ upstream | Có, nếu dependency còn truy cập được | Maven local repository, Gradle dependency cache |
| Build cache | Giữ output của task có thể tái sử dụng khi input giống nhau | Có, nếu task có thể chạy lại | Gradle task output cache |
| Docker layer cache | Tái sử dụng layer của image khi instruction và input không đổi | Có, nếu layer có thể build lại | Layer cài JRE hoặc dependency |
| Artifact | Đầu ra đã được build và cần lưu/phân phối | Không nên xem là cache tạm | JAR, WAR, container image |
| Artifact repository | Lưu artifact theo version, quyền và chính sách retention | Quản lý theo vòng đời phát hành | Artifact Registry Maven/Docker repository |

Cache là tối ưu hiệu năng. Artifact là sản phẩm của build và cần có danh tính ổn định để triển khai, kiểm tra hoặc khôi phục.

Một dependency cache bị xóa không làm mất bản phát hành nếu artifact đã được lưu trong repository. Ngược lại, nếu coi cache là nơi duy nhất lưu JAR production, việc cache bị hết hạn hoặc bị ghi đè có thể khiến nhóm không còn bản phát hành đáng tin cậy.

## 2. Đo thời gian build trước khi tối ưu

Đừng bắt đầu bằng cách tăng CPU hoặc bật mọi loại cache. Trước tiên, cần xác định thời gian đang tiêu tốn ở đâu.

Một build Java điển hình có thể gồm:

1. Khởi tạo Cloud Build worker và checkout source.
2. Khởi tạo JDK, Maven/Gradle Wrapper và plugin.
3. Resolve dependency.
4. Compile source và generate code.
5. Chạy unit test và integration test.
6. Package JAR/WAR.
7. Build container image.
8. Push image hoặc package lên Artifact Registry.
9. Tạo provenance, SBOM và thực hiện kiểm tra bảo mật.

Ghi lại duration cho từng bước, số byte tải về, cache hit/miss, CPU, memory, disk I/O và số test chạy. Cloud Build hiển thị thời gian từng build step trong build details; có thể kết hợp log và metric để so sánh giữa các lần chạy.

### Chỉ số nên theo dõi

| Chỉ số | Ý nghĩa |
|---|---|
| Total build duration | Thời gian từ lúc build bắt đầu đến khi hoàn tất |
| Queue/wait time | Thời gian chờ worker hoặc slot build |
| Dependency download time | Thời gian resolve và tải dependency |
| Compile/test duration | Thời gian compile và test |
| Cache hit rate | Tỷ lệ dữ liệu hoặc task được tái sử dụng |
| Image build duration | Thời gian tạo container image |
| Artifact upload duration | Thời gian push package/image |
| Build success rate | Tỷ lệ build hoàn tất thành công |
| Cost per successful build | Chi phí trung bình cho một build thành công |

Ví dụ, nếu build mất 8 phút nhưng 5 phút nằm ở integration test cần khởi tạo database, tăng tốc dependency cache sẽ không giải quyết nút thắt chính. Nếu 3 phút bị dùng để tải Maven dependency từ internet mỗi lần, Artifact Registry remote repository và cache trong build có thể tạo khác biệt rõ rệt.

Hãy đo cả build lạnh (cache rỗng) và build nóng (cache đã có dữ liệu). So sánh nhiều lần để tránh kết luận dựa trên một lần chạy có network hoặc worker bất thường.

## 3. Dependency cache cho Maven

Maven lưu các artifact đã tải trong local repository, mặc định thường là thư mục **.m2/repository** bên trong home của user chạy build. Local repository gồm dependency, plugin và metadata đã resolve.

Khi Cloud Build worker mới được tạo, local repository thường bắt đầu rỗng. Vì vậy, mỗi build có thể phải tải lại dependency nếu không thiết kế cache.

### Chia sẻ local Maven repository giữa các step

Cloud Build chia sẻ thư mục **/workspace** giữa các build step trong cùng một build. Có thể khai báo volume để chia sẻ một đường dẫn khác, ví dụ **/root/.m2**, giữa các step. Volume này tồn tại trong phạm vi build hiện tại; nó không tự tồn tại qua các build độc lập.

Ví dụ Cloud Build cấu hình hai bước Maven cùng dùng volume:

~~~yaml
steps:
  - id: resolve-dependencies
    name: maven:3.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - -ntp
      - dependency:go-offline
    volumes:
      - name: maven-repository
        path: /root/.m2

  - id: verify
    name: maven:3.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - -ntp
      - verify
    volumes:
      - name: maven-repository
        path: /root/.m2
~~~

Bước đầu tải trước dependency và plugin cần thiết; bước sau dùng lại local repository trong cùng build. Goal dependency:go-offline giúp tải trước nhiều dependency nhưng không bảo đảm mọi plugin hoặc dependency được kích hoạt theo profile động đều đã có. Bước verify vẫn cần quyền truy cập repository nếu phát sinh dependency mới.

### Dùng Maven Wrapper

Nên commit Maven Wrapper và cấu hình phiên bản Maven rõ ràng. Build nên chạy bằng **./mvnw** để môi trường local và CI dùng cùng phiên bản Maven.

Ví dụ:

~~~bash
./mvnw -B -ntp verify
~~~

Các tùy chọn:

- **-B:** chạy batch mode, phù hợp với CI.
- **-ntp:** tắt transfer progress để log gọn hơn.
- **verify:** chạy các phase cần thiết trước khi coi artifact đã qua kiểm tra.

Không nên mặc định thêm **-T 1C** vào mọi pipeline. Maven parallel build có thể tăng tốc multi-module project nhưng plugin hoặc test có thể không an toàn khi chạy song song. Hãy benchmark và kiểm tra giới hạn memory/CPU.

### Cache dependency giữa nhiều build

Volume trong Cloud Build chỉ giúp chia sẻ giữa các step của một build. Để tránh tải dependency từ upstream trong mỗi build, có thể dùng Artifact Registry remote repository cho Maven. Remote repository proxy upstream repository như Maven Central và cache các artifact đã lấy về trong Artifact Registry.

Một mô hình phổ biến:

- Remote repository: proxy dependency công khai, giảm phụ thuộc vào upstream và tập trung kiểm soát nguồn tải.
- Standard repository: lưu package nội bộ do tổ chức phát hành.
- Virtual repository: cung cấp một endpoint hợp nhất nhiều repository và điều khiển thứ tự ưu tiên.

Maven có thể truy cập Artifact Registry thông qua cấu hình repository và cơ chế xác thực phù hợp. Dùng lệnh sau để tạo cấu hình mẫu cho repository đã có:

~~~bash
gcloud artifacts print-settings mvn \
  --project=PROJECT_ID \
  --repository=MAVEN_REPOSITORY \
  --location=LOCATION
~~~

Lệnh in ra các thiết lập Maven cần thiết theo repository và location. Hãy tích hợp cấu hình đó vào POM hoặc Maven settings theo hướng dẫn của Artifact Registry. Không commit access token hoặc mật khẩu vào pom.xml hay settings.xml.

### Khi nào dùng offline mode?

Maven có tùy chọn offline:

~~~bash
./mvnw -o -B verify
~~~

Chỉ dùng khi toàn bộ dependency và plugin cần thiết đã có trong local repository. Nếu cache thiếu một artifact, build sẽ thất bại. Offline mode không phải cách thay thế cho việc quản lý repository và dependency ổn định.

## 4. Dependency cache và build cache trong Gradle

Gradle có nhiều loại cache khác nhau:

- Dependency cache giữ module và artifact đã resolve.
- Build cache giữ output của task có thể tái sử dụng khi input giống nhau.
- Configuration cache giữ kết quả cấu hình build để giảm thời gian configuration ở lần chạy tiếp theo.

Ba cache này giải quyết ba loại công việc khác nhau. Dependency cache không tự làm cho compile task có output cache hit; build cache không thay thế repository lưu dependency; configuration cache có thể giảm thời gian cấu hình nhưng cần plugin và build script tương thích.

### Bật Gradle build cache

Có thể bật build cache bằng command line:

~~~bash
./gradlew --build-cache test bootJar
~~~

Hoặc cấu hình trong gradle.properties:

~~~properties
org.gradle.caching=true
org.gradle.parallel=true
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
~~~

Gradle chỉ tái sử dụng output cho task được hỗ trợ cache và khai báo đầy đủ inputs/outputs. Với custom task, cần dùng annotation và API đúng để Gradle biết task phụ thuộc vào file, property và tool nào. Nếu task đọc biến môi trường nhưng không khai báo input, cache có thể trả output cũ cho một môi trường khác.

### Configuration cache

Configuration cache giúp tránh chạy lại phần configuration của build khi cấu hình không đổi và plugin tương thích.

Thử bật trong một nhánh riêng:

~~~bash
./gradlew --configuration-cache --build-cache test
~~~

Nếu Gradle báo task hoặc plugin chưa tương thích, hãy xử lý vấn đề đó trước khi bật cho toàn bộ pipeline. Không bỏ qua warning chỉ để đạt cache hit.

### Remote build cache

Cloud Build worker thường là môi trường tạm thời. Local Gradle cache trong worker có thể mất sau khi build kết thúc. Để tái sử dụng task output qua nhiều worker/build, cần một remote build cache có giao thức tương thích với Gradle, chẳng hạn Gradle Enterprise/Develocity hoặc một HTTP build cache server được tổ chức vận hành.

Ví dụ cấu hình trong settings.gradle.kts:

~~~kotlin
buildCache {
    remote<HttpBuildCache> {
        url = uri("https://gradle-cache.example.internal/cache/")
        isPush = providers.gradleProperty("trustedBuild").orNull == "true"
    }
}
~~~

Địa chỉ trên là placeholder. Endpoint thực tế cần TLS, xác thực và quyền truy cập được kiểm soát. Chỉ build đáng tin cậy, ví dụ pipeline từ protected branch sau khi kiểm tra, mới nên có quyền ghi cache dùng chung. Build từ pull request không đáng tin cậy có thể chỉ được đọc cache hoặc dùng namespace riêng để tránh cache poisoning.

Artifact Registry Maven repository là nơi cache dependency theo repository protocol; nó không tự động trở thành Gradle task-output build cache. Đừng cấu hình URL Maven repository như một Gradle remote build cache endpoint.

### Dependency locking và verification

Để build có thể tái lập, hãy khóa phiên bản dependency và kiểm tra checksum.

Ví dụ trong Gradle:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Tạo hoặc cập nhật lock file theo quy trình của dự án:

~~~bash
./gradlew dependencies --write-locks
~~~

Gradle dependency verification có thể ghi metadata checksum:

~~~bash
./gradlew --write-verification-metadata sha256 help
~~~

Hãy review và commit các lock/verification metadata thay đổi. Không tự động chấp nhận checksum mới trong mọi build vì điều đó có thể hợp thức hóa một dependency bị thay thế.

## 5. Cloud Build cache: phạm vi tồn tại và chiến lược

Một hiểu lầm phổ biến là Cloud Build volume tự động cache dữ liệu giữa các build. Thực tế:

- **/workspace** được chia sẻ giữa các step của cùng một build.
- Volume khai báo trong Cloud Build cũng được chia sẻ giữa các step gắn volume đó trong cùng build.
- Worker/build mới không mặc nhiên có local filesystem cache từ build trước.
- Artifact Registry và remote build cache là dịch vụ lưu trữ bên ngoài worker, tồn tại theo chính sách riêng.

Vì vậy, hãy thiết kế theo từng tầng:

| Tầng | Cách tận dụng | Phạm vi |
|---|---|---|
| Workspace | Đặt output trung gian hoặc file dùng giữa các step | Một build |
| Named volume | Chia sẻ .m2 hoặc .gradle giữa các step | Một build |
| Artifact Registry remote repo | Cache dependency upstream | Nhiều build |
| Gradle remote build cache | Tái sử dụng output task | Nhiều build |
| Docker registry cache | Tái sử dụng image layer | Nhiều build |
| Artifact Registry standard repo | Lưu package/image phát hành | Theo retention/version |

### Ví dụ pipeline Maven và Docker image

~~~yaml
steps:
  - id: dependencies
    name: maven:3.9-eclipse-temurin-21
    entrypoint: mvn
    args: ["-B", "-ntp", "dependency:go-offline"]
    volumes:
      - name: m2
        path: /root/.m2

  - id: verify
    name: maven:3.9-eclipse-temurin-21
    entrypoint: mvn
    args: ["-B", "-ntp", "verify"]
    volumes:
      - name: m2
        path: /root/.m2

  - id: build-image
    name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - asia-southeast1-docker.pkg.dev/$PROJECT_ID/java-services/checkout:$SHORT_SHA
      - .

images:
  - asia-southeast1-docker.pkg.dev/$PROJECT_ID/java-services/checkout:$SHORT_SHA
~~~

Ví dụ này minh họa volume Maven được chia sẻ giữa hai step và image được push vào Artifact Registry. Cần bảo đảm Cloud Build service account có quyền đọc repository dependency và quyền ghi Docker repository. Tag sử dụng commit SHA để dễ truy vết; với triển khai production, nên ghi nhận digest sau khi push.

Trong pipeline thực tế, có thể gộp bước resolve dependency và verify nếu không có lý do cần tách. Mỗi step bổ sung có overhead khởi tạo và truyền artifact; hãy đo tổng thời gian thay vì tối ưu từng step riêng lẻ.

## 6. Tối ưu Dockerfile Java bằng layer caching

Docker build tạo các layer theo instruction. Khi một instruction và toàn bộ input liên quan không đổi, Docker có thể tái sử dụng layer đã có. Nếu copy toàn bộ source trước khi resolve dependency, một thay đổi nhỏ trong source có thể làm invalidated layer dependency và khiến Maven tải lại thư viện.

### Dockerfile chưa tối ưu

~~~dockerfile
FROM maven:3.9-eclipse-temurin-21
WORKDIR /app
COPY . .
RUN mvn -B -ntp package
~~~

Cách này đơn giản nhưng thay đổi bất kỳ file nào trong build context có thể làm layer COPY thay đổi, dẫn đến chạy lại package và dependency resolution.

### Dockerfile chia layer theo độ ổn định

~~~dockerfile
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /workspace

COPY pom.xml .
COPY .mvn/ .mvn/
COPY mvnw .
RUN chmod +x mvnw && ./mvnw -B -ntp dependency:go-offline

COPY src/ src/
RUN ./mvnw -B -ntp verify

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/target/app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Dependency được resolve trước khi copy source. Khi chỉ sửa file trong src, layer dependency có thể được tái sử dụng. Hãy điều chỉnh đường dẫn JAR và các thư mục resource theo dự án thật.

Tạo file .dockerignore để loại bỏ file không cần thiết:

~~~text
.git
.gradle
.m2
target
build
.idea
*.iml
.env
*.pem
*.key
~~~

Không đưa credential, file môi trường production hoặc private key vào build context. Nếu build cần secret, dùng cơ chế secret mount của builder hoặc truyền credential qua secret manager theo thiết kế pipeline; không dùng Docker ARG hoặc ENV để nhúng secret vào image layer.

### BuildKit registry cache

Nếu builder sử dụng Docker BuildKit/buildx, có thể lưu cache image layer trong Artifact Registry để build worker mới tải cache từ lần trước.

Ví dụ:

~~~bash
docker buildx build \
  --cache-from=type=registry,ref=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-services/checkout:buildcache \
  --cache-to=type=registry,ref=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-services/checkout:buildcache,mode=max \
  --tag=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-services/checkout:COMMIT_SHA \
  --push .
~~~

Cần dùng builder có hỗ trợ buildx/BuildKit và quyền Artifact Registry phù hợp. Cache image và image phát hành có tag riêng. Không dùng tag buildcache làm phiên bản triển khai production. Với pipeline chạy đồng thời, cần cân nhắc việc nhiều build cùng ghi một cache reference; có thể tách cache theo branch hoặc dùng quy tắc cập nhật có kiểm soát.

## 7. Artifact Registry: proxy dependency và lưu artifact phát hành

Artifact Registry là nơi lưu trữ, quản lý và phân phối package hoặc container image. Với Java, có thể dùng Maven repository format để lưu package nội bộ và proxy dependency từ upstream.

### Ba loại repository thường dùng

| Loại | Vai trò | Ví dụ |
|---|---|---|
| Standard | Lưu artifact do tổ chức publish | com.company:checkout:1.4.0 |
| Remote | Proxy và cache artifact từ upstream | Maven Central |
| Virtual | Hợp nhất nhiều repository thành một endpoint | Ưu tiên repository nội bộ trước remote |

Một mô hình triển khai:

~~~text
Maven / Gradle build
        |
        v
Artifact Registry virtual repository
        |
        +---- Internal standard repository
        |
        +---- Maven Central remote repository
        |
        v
Dependency được resolve
        |
        v
Compile / test / package
        |
        v
Artifact Registry standard repository
        |
        +---- Maven package
        |
        +---- Container image
~~~

Virtual repository giúp tập trung cấu hình endpoint và ưu tiên nguồn package. Cần cấu hình priority rõ ràng để package nội bộ không bị thay thế bởi package cùng tọa độ từ upstream không đáng tin cậy.

### Publish Maven package

Khi build thành công, Maven có thể publish package bằng phase deploy:

~~~bash
./mvnw -B -ntp deploy
~~~

POM cần cấu hình distributionManagement trỏ tới Maven repository trong Artifact Registry và cơ chế xác thực phù hợp. Có thể dùng lệnh sau để in cấu hình mẫu:

~~~bash
gcloud artifacts print-settings mvn \
  --project=PROJECT_ID \
  --repository=MAVEN_RELEASES \
  --location=LOCATION
~~~

Artifact được định danh bằng groupId, artifactId và version. Không ghi đè release version đã phát hành. Dùng version mới cho mỗi release; nếu dùng SNAPSHOT trong quá trình phát triển, cần hiểu rõ metadata và hành vi cập nhật của snapshot repository.

### Publish Gradle artifact

Với Gradle Maven Publish plugin, cấu hình publication và repository theo chuẩn của dự án. Lệnh in cấu hình Artifact Registry:

~~~bash
gcloud artifacts print-settings gradle \
  --project=PROJECT_ID \
  --repository=GRADLE_RELEASES \
  --location=LOCATION
~~~

Sau đó publish theo task của dự án:

~~~bash
./gradlew publish
~~~

Tách quyền đọc dependency khỏi quyền publish package. Pipeline build từ pull request không nên có quyền ghi vào repository release.

## 8. Quản lý artifact theo version và digest

Một artifact phát hành cần có định danh ổn định. Với Java package, định danh thường gồm group, artifact và version. Với container image, digest SHA-256 là định danh nội dung chính xác; tag chỉ là tên tham chiếu có thể thay đổi tùy chính sách repository.

Ví dụ image:

~~~text
asia-southeast1-docker.pkg.dev/my-project/java-services/checkout:8f3a2c1
asia-southeast1-docker.pkg.dev/my-project/java-services/checkout@sha256:...
~~~

Tag commit SHA giúp truy tìm source commit, nhưng digest mới xác định chính xác nội dung image. Khi promote image từ staging sang production, nên triển khai cùng digest đã kiểm thử thay vì build lại image ở mỗi môi trường.

Một luồng phát hành:

1. Build từ commit đã xác định.
2. Chạy test, scan và kiểm tra policy.
3. Push image hoặc package vào Artifact Registry.
4. Ghi nhận version, digest, build ID và source commit.
5. Tạo SBOM và provenance theo khả năng pipeline.
6. Promote artifact đã kiểm tra sang môi trường tiếp theo.
7. Triển khai theo digest và lưu lại kết quả.

Không dùng tag mutable như latest làm định danh duy nhất cho production release. Nếu tag bị trỏ sang nội dung khác, khó chứng minh môi trường đang chạy đúng artifact đã được kiểm thử.

## 9. Reproducible build và tính toàn vẹn chuỗi cung ứng

Build nhanh chỉ có ý nghĩa nếu kết quả có thể tin cậy. Một build tái lập được cần kiểm soát các đầu vào:

- Commit source và trạng thái repository.
- Phiên bản JDK, Maven/Gradle Wrapper và plugin.
- Phiên bản dependency và repository nguồn.
- Base image và builder image.
- Biến môi trường ảnh hưởng đến output.
- Locale, timezone và timestamp nếu chúng làm thay đổi artifact.

### Pin toolchain

Dùng Maven Wrapper hoặc Gradle Wrapper và cố định phiên bản JDK qua toolchain hoặc builder image. Với container image, nên pin base image bằng digest khi yêu cầu tái lập cao.

Ví dụ Maven Wrapper properties nên xác định distribution URL và checksum của distribution. Gradle Wrapper cũng hỗ trợ distribution checksum. Không dựa vào phiên bản công cụ cài sẵn ngẫu nhiên trên worker.

### SBOM và provenance

SBOM (Software Bill of Materials) mô tả các thành phần có trong artifact. Provenance ghi lại nguồn và quy trình tạo artifact, chẳng hạn source, builder và thông tin build. Các dữ liệu này hỗ trợ điều tra lỗ hổng, audit và xác minh artifact được tạo từ pipeline đáng tin cậy.

Cloud Build và Artifact Registry có thể tích hợp với các khả năng provenance, Artifact Analysis và kiểm soát chuỗi cung ứng tùy cấu hình dự án. Hãy lưu metadata build và gắn nó với digest của image hoặc version package.

### Cache không phải nguồn sự thật

Cache có thể bị xóa, cũ hoặc bị ghi bởi build không đáng tin cậy. Không dùng cache làm nơi lưu release duy nhất. Với remote cache dùng chung:

- Phân quyền read và write riêng.
- Chỉ trusted pipeline được ghi cache dùng chung.
- Dùng TLS và xác thực cho cache server.
- Không lưu credential hoặc secret trong cache output.
- Tách cache theo branch, trust level hoặc toolchain khi cần.
- Có thể xóa cache và build lại từ nguồn dependency/artifact đã được kiểm soát.

Cache poisoning xảy ra khi output không đáng tin được đưa vào cache dùng chung và build khác tái sử dụng. Build từ fork hoặc pull request bên ngoài không nên được cấp quyền ghi cache mà protected branch tin cậy sử dụng.

## 10. Tối ưu Maven và Gradle ngoài cache

Cache chỉ giải quyết một phần thời gian build. Một số kỹ thuật khác:

### Maven

- Dùng Maven Wrapper và phiên bản dependency/plugin cố định.
- Tách unit test nhanh khỏi integration test cần hạ tầng.
- Dùng multi-module build có dependency graph rõ ràng.
- Chỉ chạy module cần thiết khi thay đổi không ảnh hưởng toàn bộ project, nếu cấu trúc build cho phép.
- Dùng Maven parallel build sau khi xác minh plugin và test an toàn.
- Tránh chạy lại package ở nhiều step nếu có thể truyền artifact giữa các step.
- Dùng dependency:go-offline để prefetch trong build có cấu trúc phù hợp.

### Gradle

- Dùng build cache và configuration cache khi task/plugin tương thích.
- Khai báo task inputs/outputs đầy đủ để cache hit chính xác.
- Dùng incremental compilation và incremental annotation processing nếu plugin hỗ trợ.
- Dùng parallel execution cho các project độc lập.
- Giới hạn worker theo CPU và memory thực tế.
- Dùng dependency locking và verification để tránh resolve version không ổn định.
- Không bật configuration cache diện rộng trước khi kiểm tra plugin và build script.

### Chạy test hiệu quả

- Chạy unit test độc lập song song khi có thể.
- Dùng test selection hoặc module-level test khi thay đổi không ảnh hưởng toàn bộ hệ thống.
- Giữ integration test đại diện cho dependency thực tế.
- Tách test flaky và xử lý nguyên nhân thay vì retry vô hạn.
- Dùng service emulator hoặc test container phù hợp để giảm thời gian khởi tạo hạ tầng, nhưng vẫn có kiểm thử integration với dịch vụ thật theo lịch.
- Lưu test report và log để không phải chạy lại chỉ nhằm tìm lỗi đã xảy ra.

### Chọn worker và tài nguyên Cloud Build

Nếu build CPU-bound, tăng CPU có thể giảm compile time. Nếu build memory-bound, tăng memory hoặc điều chỉnh JVM heap có thể giảm GC và OOM. Nếu build bị giới hạn bởi download, cải thiện repository/cache có thể hiệu quả hơn việc dùng worker lớn hơn.

Cloud Build cho phép chọn machine type và dung lượng disk theo cấu hình build. Hãy thử trên một số build đại diện, so sánh cost per successful build và queue time trước khi thay đổi mặc định cho toàn tổ chức.

## 11. Ví dụ thiết kế pipeline Java hoàn chỉnh

Một pipeline tham khảo cho dịch vụ Spring Boot:

~~~text
Commit / Pull Request
        |
        v
Checkout + xác định JDK/Wrapper
        |
        v
Resolve dependencies qua Artifact Registry
        |
        v
Compile + unit tests
        |
        v
Integration tests
        |
        v
Package JAR
        |
        v
Build container image với layer cache
        |
        v
Scan + SBOM + provenance
        |
        v
Push Artifact Registry
        |
        v
Promote cùng digest sang staging
        |
        v
Canary / verify / promote production
~~~

Các nguyên tắc chính:

- Pull request chỉ có quyền đọc dependency và cache cần thiết.
- Protected branch hoặc release pipeline mới có quyền publish package/image.
- Artifact version gắn với commit và digest.
- Build cache chỉ được chia sẻ giữa những build có cùng trust boundary.
- Kết quả test, scan và provenance gắn với artifact đã tạo.
- Deploy staging và production dùng cùng artifact digest.

Một pipeline không nhất thiết phải chia mỗi thao tác thành một step riêng. Tách step khi cần isolation, cache mount, quyền riêng hoặc khả năng retry độc lập; nếu không, overhead khởi tạo container có thể làm build chậm hơn.

## 12. Đo lường hiệu quả sau khi tối ưu

Sau mỗi thay đổi, so sánh với baseline:

| Trước/sau | Điều cần kiểm tra |
|---|---|
| Build lạnh | Có thể build thành công khi cache rỗng không? |
| Build nóng | Cache có giảm thời gian thực tế không? |
| Cache hit rate | Có tăng nhưng không làm output sai không? |
| Artifact digest | Có ổn định với cùng source/toolchain/input không? |
| Test results | Có giữ nguyên coverage và chất lượng kiểm thử không? |
| Failure rate | Cache miss, timeout hoặc race có làm build dễ thất bại hơn không? |
| Cost | Tiết kiệm thời gian có đáng với chi phí remote cache/worker lớn hơn không? |
| Security | PR không tin cậy có thể ghi cache hoặc publish artifact không? |

Một số mục tiêu đo lường nội bộ có thể là giảm 30% median build duration, giữ build success rate không giảm và không tăng tỷ lệ artifact bị thay đổi sau publish. Mục tiêu cần dựa trên baseline của dự án, không dùng con số chung cho mọi nhóm.

## 13. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nhầm volume Cloud Build là cache giữa các build | Worker mới vẫn tải lại dependency | Dùng Artifact Registry remote repo hoặc remote build cache |
| Chỉ cache dependency nhưng kỳ vọng compile nhanh hơn | Compile task vẫn chạy lại | Dùng Gradle build cache hoặc tối ưu task |
| Dùng Artifact Registry Maven như Gradle build cache | Giao thức không tương thích | Tách repository dependency và Gradle remote build cache |
| Copy toàn bộ source trước khi resolve dependency trong Dockerfile | Source thay đổi làm mất cache dependency layer | Copy file build descriptor trước |
| Cache không có key theo toolchain/lockfile | Có thể tái sử dụng output sai môi trường | Khóa đầu vào và dùng cache key phù hợp |
| Build không tin cậy được ghi remote cache | Cache poisoning | Tách quyền ghi cache theo trust boundary |
| Ghi secret vào Docker layer hoặc cache | Credential có thể bị lộ qua image/cache | Dùng secret mount và loại secret khỏi build context |
| Publish lại cùng release version | Artifact có thể thay đổi nội dung nhưng giữ version | Dùng version bất biến và ghi nhận digest |
| Chỉ dùng tag latest | Không xác định chính xác artifact triển khai | Deploy bằng digest |
| Tăng worker size mà không đo | Chi phí tăng nhưng bottleneck không đổi | Profile từng build step trước |

## 14. Checklist tối ưu build Java trên GCP

- [ ] Có baseline cho build lạnh, build nóng và duration từng step.
- [ ] JDK, Maven/Gradle Wrapper và builder image được pin phiên bản.
- [ ] Dependency version được kiểm soát; Gradle có lock/verification metadata khi phù hợp.
- [ ] Maven local repository hoặc Gradle dependency cache được dùng hiệu quả.
- [ ] Artifact Registry remote repository proxy dependency upstream khi phù hợp.
- [ ] Cloud Build workspace/volume chỉ được kỳ vọng chia sẻ trong phạm vi một build.
- [ ] Gradle build cache/configuration cache được bật sau khi kiểm tra task/plugin.
- [ ] Remote build cache có TLS, auth, phân quyền read/write và trust boundary.
- [ ] Dockerfile chia layer theo độ ổn định; .dockerignore loại bỏ file không cần thiết.
- [ ] Docker BuildKit registry cache dùng reference riêng với image release.
- [ ] Artifact Registry lưu package/image có version và chính sách retention.
- [ ] Artifact đã kiểm thử được promote qua môi trường bằng cùng digest.
- [ ] SBOM/provenance/scan được gắn với artifact theo khả năng pipeline.
- [ ] Secret không nằm trong source, Docker layer, log hoặc cache.
- [ ] Đã so sánh thời gian, success rate và cost sau tối ưu.

## Kết luận

Tối ưu thời gian build Java trên GCP cần phối hợp đúng các lớp cache và nơi lưu artifact. Maven/Gradle dependency cache giảm tải thư viện; Gradle build cache giảm thực thi task có input không đổi; Docker layer cache giảm thời gian tạo image; Artifact Registry proxy dependency và lưu package/image đã phát hành. Cloud Build workspace và volume hỗ trợ chia sẻ trong một build, còn tái sử dụng giữa nhiều build cần remote repository hoặc remote cache phù hợp. Khi pin toolchain, khóa dependency, bảo vệ cache và triển khai bằng artifact digest, nhóm có thể tăng tốc pipeline mà vẫn giữ tính tái lập và độ tin cậy của chuỗi cung ứng phần mềm.

## Tài liệu tham khảo

- [Cloud Build documentation](https://docs.cloud.google.com/build/docs)
- [Cloud Build: Build configuration file schema](https://docs.cloud.google.com/build/docs/build-config-file-schema)
- [Cloud Build: Use volumes](https://docs.cloud.google.com/build/docs/configuring-builds/pass-data-between-steps)
- [Artifact Registry overview](https://docs.cloud.google.com/artifact-registry/docs/overview)
- [Artifact Registry: Remote repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/remote-overview)
- [Artifact Registry: Virtual repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/virtual-overview)
- [Artifact Registry: Maven packages](https://docs.cloud.google.com/artifact-registry/docs/java)
- [Artifact Registry: Configure Gradle](https://docs.cloud.google.com/artifact-registry/docs/java/gradle)
- [Gradle: Build Cache](https://docs.gradle.org/current/userguide/build_cache.html)
- [Gradle: Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Gradle: Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Maven: Local repository](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Docker: Build cache optimization](https://docs.docker.com/build/cache/optimize/)
- [Docker: Cache backends](https://docs.docker.com/build/cache/backends/)
- [SLSA: Provenance](https://slsa.dev/spec/v1.1/provenance)

