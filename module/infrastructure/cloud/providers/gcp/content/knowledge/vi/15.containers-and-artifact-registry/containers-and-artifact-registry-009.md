# Tối ưu image Java bằng multi-stage build và buildpacks

Một nhóm triển khai dịch vụ Java lên Google Kubernetes Engine (GKE) hoặc Cloud Run thường bắt đầu bằng câu hỏi “đóng JAR vào Docker image thế nào?”. Nếu đưa cả JDK, Maven/Gradle, source code, build cache và công cụ debug vào image production, image sẽ mang nhiều thành phần **không cần thiết khi chạy**, khó tối ưu push/pull và có thêm bề mặt cần bảo trì bảo mật.

Hai hướng giải quyết chính:

- **Docker multi-stage build:** biên dịch bằng image chứa JDK/build tools, sau đó **chỉ chuyển artifact** sang image runtime nhỏ hơn.
- **Cloud Native Buildpacks (CNB):** nhận diện Java/Maven/Gradle, xây OCI image có các lớp runtime phù hợp **mà không bắt buộc viết Dockerfile**.

Bài thuộc chương **Container và Artifact Registry** của mô-đun `CLOUD_PROVIDERS_GCP`. Khi kết hợp kiến thức organization/project, IAM, VPC, Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và database, kỹ thuật đóng gói image cần gắn với **bảo vệ tài nguyên, tự động hóa phát hành, độ tin cậy, bảo mật chuỗi cung ứng và chi phí**.

Ví dụ giả định ứng dụng **Java 21, Spring Boot, Maven** có JAR `target/orders-api-1.0.0.jar`. Tên file, project, repository, image tag và các thuộc tính môi trường chỉ dùng minh họa; không chạy lệnh ghi tài nguyên trên project production nếu chưa được phê duyệt.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt build image, runtime image, image layer, tag và digest.
2. Viết Dockerfile **multi-stage** cho ứng dụng Java 21 với runtime non-root.
3. Tối ưu build context bằng `.dockerignore`, caching dependencies và BuildKit.
4. Chọn JRE/distroless hoặc runtime đặc thù dựa trên requirements thực tế.
5. Giải thích Cloud Native Buildpacks và chu trình detect–build–export.
6. Sử dụng `pack` hoặc `gcloud builds submit --pack` để tạo Java image.
7. Lưu images trong Artifact Registry, kiểm tra digest và triển khai Cloud Run/GKE.
8. Bảo vệ pipeline bằng IAM tối thiểu, secrets management và vulnerability scanning.
9. Đo kích thước, tốc độ build/pull, startup, memory và chi phí.
10. Chọn buildpacks hay multi-stage dựa vào điều kiện của nhóm và workload.

## 1. Source code, executable JAR và container runtime

Một dự án Java Maven đơn giản có cấu trúc:

~~~text
orders-api/
├── pom.xml
├── src/
│   ├── main/java/...
│   └── test/java/...
├── Dockerfile
├── .dockerignore
└── project.toml       # Chỉ cần khi dùng buildpacks và muốn cấu hình
~~~

Để build một Spring Boot executable JAR, Maven cần JDK và những dependencies/plugins được `pom.xml` định nghĩa. Nhưng khi chạy JAR, container thường **không cần compiler, Maven hay source**.

~~~mermaid
flowchart LR
    SRC["Source + pom.xml"] --> B["Build stage: Maven + JDK"]
    B --> J["Executable JAR"]
    J --> R["Runtime stage: Java runtime"]
    R --> OCI["OCI image"]
    OCI --> AR["Artifact Registry"]
    AR --> DEP["Cloud Run / GKE / VM"]
~~~

| Thành phần | Khi build | Khi chạy |
| --- | --- | --- |
| **JDK** | Biên dịch và kiểm thử Java | Thường không cần compiler/tooling |
| **Maven/Gradle** | Download dependencies và package artifact | Không cần |
| **JRE/Java runtime** | Có trong JDK | Cần để chạy bytecode |
| **Source/test files** | Cần build/test | Thường không cần |
| **Build cache `~/.m2`/`~/.gradle`** | Tiết kiệm thời gian build | Không cần |
| **Executable JAR** | Đầu ra | Cần |
| **CA certs/native libraries** | Tùy build | Cần nếu ứng dụng dùng TLS/JNI/font/timezone |

**Lưu ý:** không phải `*.jar` nào cũng có thể chạy bằng `java -jar`. Ví dụ cần Spring Boot plugin tạo **executable/fat JAR**; plain library JAR có thể thiếu main manifest hoặc dependencies cần thiết.

## 2. Image layers, tag và digest

Container image gồm các filesystem layers và metadata. Các instruction `COPY`/`RUN` trong Dockerfile có thể tạo layers và được reuse khi đầu vào không đổi.

- **Tag** như `orders-api:v1.2.0` là tên dễ đọc, **có thể gán lại**.
- **Digest** như `orders-api@sha256:<FULL_DIGEST>` định danh nội dung image manifest, phù hợp để deploy artifact đã kiểm thử.
- **Layer cache** tránh xây lại hoặc tải lại những lớp không đổi.
- **Image manifest/index** mô tả image và có thể bao gồm nhiều kiến trúc CPU; digest index có thể khác digest của từng platform.

~~~mermaid
flowchart TD
    A["Application JAR layer"] --> B["Java runtime layer"]
    B --> C["OS base / CA libs"]
    C --> D["Image manifest"]
    D --> E["Digest sha256:..."]
~~~

**“Kích thước image” không chỉ có một số đo.** Kích thước local từ Docker inspect khác với dung lượng nén phải push/pull; registry và node có thể tái sử dụng layers. Cloud Run startup còn phụ thuộc Java class loading, framework, memory, CPU và hoạt động init của ứng dụng, không chỉ kích thước image.

## 3. Anti-pattern: single-stage chứa cả Maven

~~~dockerfile
FROM maven:3.9-eclipse-temurin-21
WORKDIR /workspace
COPY . .
RUN mvn -B -ntp -DskipTests package
EXPOSE 8080
CMD ["java", "-jar", "target/orders-api-1.0.0.jar"]
~~~

Dockerfile này chạy được nếu JAR đúng, nhưng môi trường production phải mang thêm Maven, JDK, source, build output và những file không cần thiết. `COPY . .` còn có thể đưa `.git`, `.env`, log hay private key vào image nếu build context không được lọc.

**Không đồng nghĩa dùng JDK image luôn không an toàn**; một số ứng dụng cần tooling/JNI. Vấn đề là nên chủ động quyết định runtime thực sự cần những gì, không mặc định dùng image build để chạy.

## 4. Docker multi-stage với Maven và Java 21

Ví dụ Dockerfile đầy đủ:

~~~dockerfile
# syntax=docker/dockerfile:1

# Stage 1: biên dịch/package
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /workspace

# Đặt descriptor trước source để có thể cache dependencies.
COPY pom.xml ./
RUN --mount=type=cache,target=/root/.m2 \
    mvn -B -ntp dependency:go-offline

COPY src ./src
RUN --mount=type=cache,target=/root/.m2 \
    mvn -B -ntp -DskipTests package

# Stage 2: runtime tối giản, không mang Maven/source.
FROM gcr.io/distroless/java21-debian13:nonroot AS runtime
WORKDIR /app
COPY --from=build /workspace/target/orders-api-1.0.0.jar /app/app.jar
EXPOSE 8080
# Java distroless có entrypoint tương đương "java -jar".
CMD ["/app/app.jar"]
~~~

**Điều kiện:** ví dụ giả định `target/orders-api-1.0.0.jar` là executable JAR thực tế. Nếu dự án có version/artifact name khác, sửa đường dẫn copy theo build output; đừng dùng wildcard bừa khi có nhiều JAR (`-sources.jar`, `-javadoc.jar` hoặc plain/original JAR).

### 4.1. Phân tích từng phần

| Instruction | Mục đích |
| --- | --- |
| `FROM maven:... AS build` | JDK/Maven chỉ có trong build stage |
| `COPY pom.xml` trước source | Khi code thay mà dependencies không thay, cache resolution có thể reuse |
| `--mount=type=cache,target=/root/.m2` | Giữ Maven downloads trong cache của builder thay vì runtime image |
| `mvn ... package` | Tạo JAR; test nên chạy riêng ở CI |
| `FROM gcr.io/distroless/java21-debian13:nonroot` | Java 21 runtime tối giản với non-root user |
| `COPY --from=build` | Chỉ copy artifact cần chạy |
| `CMD ["/app/app.jar"]` | Truyền JAR cho default entrypoint của distroless Java |

**Quan trọng:** image `gcr.io/distroless/java21-debian13` được cấu hình với entrypoint tương đương **`java -jar`**, nên `CMD ["/app/app.jar"]` là đúng. Nếu đổi sang `eclipse-temurin:21-jre`, cần cấu hình kiểu `ENTRYPOINT ["java","-jar","/app/app.jar"]`; đừng áp nguyên `CMD` giữa những base images khác nhau.

### 4.2. Runtime non-root và writable path

Image `:nonroot` chạy process bằng user không phải root. JAR cần quyền đọc phù hợp; file tạm cần lưu ở thư mục được phép, thường là `/tmp` hoặc mounted volume theo runtime. Không nhúng secrets vào JAR và không dùng container filesystem làm nơi lưu dữ liệu nghiệp vụ lâu dài.

### 4.3. EXPOSE không tạo HTTP endpoint

`EXPOSE 8080` chỉ là metadata, **không mở firewall** và không ép Java lắng nghe port đúng. Cloud Run còn có runtime contract về `PORT`; cần cấu hình ứng dụng listen trên `0.0.0.0`, port tương ứng.

### 4.4. Vì sao test bị skip trong Dockerfile?

`-DskipTests` trong ví dụ giúp tách packaging khỏi bước test, **không phải khuyến nghị bỏ kiểm thử**. CI phải có gate như:

~~~bash
mvn -B -ntp verify
docker build -t orders-api:multi-local .
docker run --rm -p 8080:8080 orders-api:multi-local
~~~

Nếu build stage dựa vào generated code/profiles mà `verify` và `package` có hành vi khác nhau, cần thống nhất Maven profiles, environment và dependencies.

## 5. Giảm Docker build context bằng .dockerignore

~~~dockerignore
.git
.github
.idea
.vscode
*.log
.env
.env.*
*.pem
*.key
target/
build/
.gradle/
node_modules/
tmp/
.DS_Store
~~~

Công dụng:

1. Không truyền những file build/test không cần thiết sang builder.
2. Giảm thay đổi build context gây mất cache.
3. Giảm nguy cơ vô tình copy secrets, log và Git history vào layers.

**Không dựa riêng vào `.dockerignore` để bảo vệ secrets.** File đã lộ qua Git/CI logs vẫn có rủi ro. Nếu dùng Maven Wrapper, phải giữ `mvnw` và `.mvn/` cần thiết; ví dụ mục 4 dùng Maven có sẵn trong builder.

## 6. Docker/BuildKit cache giúp giảm thời gian, không nhất thiết giảm image size

Có hai lớp cache:

- **Docker layer cache**: reuse bước `COPY pom.xml` và dependency resolution nếu input không đổi.
- **BuildKit cache mount**: ví dụ `/root/.m2`, giữ downloaded Maven artifacts giữa các lần build trong môi trường builder phù hợp.

~~~mermaid
flowchart TD
    P["pom.xml"] --> D["Resolve dependencies"]
    D --> S["COPY src"]
    S --> C["Package JAR"]
    C --> OUT["Runtime image"]
    CACHE["BuildKit cache mount ~/.m2"] -.-> D
    CACHE -.-> C
~~~

`mvn dependency:go-offline` giúp warm cache nhưng không bảo đảm đã tải toàn bộ plugins/dependencies động trong mọi dự án; `package` có thể vẫn kết nối repository. Cần pin plugin/dependency versions và quản lý repository mirror.

**Lưu ý với CI:** cache mount ở một ephemeral worker không mặc nhiên được chia sẻ giữa hai Cloud Build jobs. Nếu cần cross-build cache, cấu hình remote caching/builder strategy có hỗ trợ; cân nhắc bảo mật và chi phí lưu cache.

Để benchmark công bằng, đo riêng:

- **Cold build:** builder chưa có layer/dependency cache.
- **Warm build:** chỉ sửa một file nguồn, được phép reuse cache.

Không so sánh thời gian build lạnh của multi-stage với build ấm của buildpacks rồi kết luận công cụ nào nhanh hơn.

## 7. Nếu dùng Gradle thay Maven

Ý tưởng vẫn là **JDK/Gradle trong build stage, runtime chỉ có Java và JAR**. Ví dụ cho Gradle Groovy DSL có wrapper:

~~~dockerfile
# syntax=docker/dockerfile:1
FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace

COPY gradlew settings.gradle build.gradle ./
COPY gradle ./gradle
RUN chmod +x ./gradlew
RUN --mount=type=cache,target=/root/.gradle \
    ./gradlew --no-daemon dependencies

COPY src ./src
RUN --mount=type=cache,target=/root/.gradle \
    ./gradlew --no-daemon bootJar

FROM gcr.io/distroless/java21-debian13:nonroot
WORKDIR /app
COPY --from=build /workspace/build/libs/orders-api-0.0.1-SNAPSHOT.jar /app/app.jar
EXPOSE 8080
CMD ["/app/app.jar"]
~~~

Dự án Kotlin DSL dùng `settings.gradle.kts`/`build.gradle.kts`; multi-module project cần copy nhiều descriptors/source và dùng đúng path output. Không mặc định mọi Gradle project có task `bootJar`: task này có khi áp dụng Spring Boot plugin.

## 8. Chọn runtime: JDK, JRE, distroless và jlink

| Lựa chọn | Điểm mạnh | Cần lưu ý |
| --- | --- | --- |
| JDK image | Có compiler, diagnostic tools; thuận debug | Nhiều thành phần không cần thiết khi chạy |
| JRE image | Có Java runtime, thường ít thành phần hơn JDK | Kích thước và gói OS tùy base |
| Distroless Java | Thiếu shell/package manager, nonroot variant, giảm bề mặt OS | Debug khó hơn; cần xác minh JNI, font, TLS, timezone |
| `jlink` custom runtime | Chỉ chọn những Java modules cần | Reflection/JNI/dynamic loading có thể làm bỏ sót modules |
| Native image | Có thể cải thiện startup/memory theo workload | Quy trình build và compatibility khác JVM truyền thống |

Distroless image **không có shell mặc định**; đừng dùng:

~~~dockerfile
FROM gcr.io/distroless/java21-debian13:nonroot
COPY app.jar /app/app.jar
CMD ["sh", "-c", "java -jar /app/app.jar"]
~~~

Lệnh trên thường lỗi vì không có `/bin/sh`. Sử dụng dạng JSON/exec của `CMD/ENTRYPOINT` và kiểm tra entrypoint sẵn có của base. Khi cần debug, dùng debug image hoặc công cụ quan sát ngoài container theo chính sách môi trường.

**Image nhỏ không bảo đảm không còn CVE**: Java dependencies nằm trong JAR vẫn cần vá; base distroless cũng cần được cập nhật.

## 9. Layered executable JAR cho Spring Boot

Một fat JAR thường chứa dependencies và code ứng dụng chung trong một file. Nếu chỉ `COPY app.jar`, khi sửa một Java class có thể tạo lại toàn bộ JAR layer.

Spring Boot hỗ trợ **layered JAR**: phân tách những thành phần ít thay đổi (dependencies, loader) khỏi code/resources ứng dụng. Một quy trình tối ưu nâng cao:

1. Cấu hình Spring Boot Maven/Gradle plugin để tạo layered JAR.
2. Trích xuất các lớp qua công cụ được phiên bản Spring Boot hỗ trợ.
3. `COPY` những lớp dependencies trước, application classes sau.
4. Đo hiệu quả layer reuse, push/pull khi chỉ thay một class.

Cú pháp `-Djarmode=...` và layer extraction thay đổi theo phiên bản framework; không sao chép lệnh trích xuất cũ mà không kiểm tra tài liệu plugin đang dùng.

**Buildpacks** có thể tự tối ưu layers cho Java/Spring Boot ở các builder hỗ trợ, nên đây là một tiêu chí đáng thử trước khi tự duy trì Dockerfile layered JAR phức tạp.

## 10. Cloud Native Buildpacks (CNB) là gì?

**Cloud Native Buildpacks** sử dụng builder image chứa các buildpacks để phát hiện và build ứng dụng thành container image tương thích OCI.

~~~mermaid
flowchart LR
    S["Java source + pom.xml/Gradle"] --> DET["Detect"]
    DET --> BUILD["Build"]
    BUILD --> EXPORT["Export image layers"]
    EXPORT --> IMG["OCI image"]
    BUILDER["Builder: buildpacks + run image"] -.-> DET
    BUILDER -.-> BUILD
~~~

| Thành phần | Chức năng |
| --- | --- |
| **Buildpack** | Phát hiện/thực hiện một phần quy trình build/runtime |
| **Builder image** | Gồm buildpacks, thứ tự detection, build/run images |
| **Lifecycle** | Điều phối detect, analyze/restore, build và export |
| **Build image** | Môi trường biên dịch tạm thời |
| **Run image** | Nền runtime của image kết quả |
| **`pack` CLI** | Chạy CNB bằng Docker engine/CI phù hợp |
| **`project.toml`** | Định nghĩa build-time environment và cấu hình dự án |
| **Rebase** | Thay run image layers khi compatible mà không rebuild app layers |

Buildpacks **không loại bỏ dependency management**. Bạn vẫn quản trị JDK version, Maven/Gradle dependencies, builder/run image versions và security updates.

### 10.1. Rebase có giới hạn

`pack rebase` có thể thay run-image layers theo điều kiện tương thích. Nó **không sửa CVE trong JAR dependencies**, không thay Java business logic và không bảo đảm mọi image có thể rebase. Sau rebase cần kiểm thử, scan lại và tạo bản deploy theo digest mới.

### 10.2. Buildpacks khác Dockerfile ở mức nào?

Multi-stage cho phép bạn quyết định mọi `FROM/COPY/RUN/CMD`. Buildpacks để builder/buildpack quyết định nhiều bước, giúp chuẩn hóa nhưng cũng cần pin và review builder. Cả hai đều có thể tạo OCI image và được đưa lên Artifact Registry, Cloud Run hoặc GKE.

## 11. Google Cloud Buildpacks cho Java 21

Google Cloud Buildpacks hỗ trợ dự án Java sử dụng Maven hoặc Gradle. Chúng có thể chọn JDK bằng biến build-time `GOOGLE_RUNTIME_VERSION`.

### 11.1. project.toml

Tạo file `project.toml` ở root ứng dụng:

~~~toml
[[build.env]]
name = "GOOGLE_RUNTIME_VERSION"
value = "21"
~~~

Đây là **cấu hình build**, không phải runtime `PORT` của Cloud Run. Không đưa secrets/database passwords vào `project.toml`.

### 11.2. Build local bằng pack

Cần Docker engine/daemon, `pack` CLI và source Maven/Gradle hợp lệ:

~~~bash
pack build orders-api:pack-local \
  --builder=gcr.io/buildpacks/builder:google-24 \
  --env GOOGLE_RUNTIME_VERSION=21
~~~

`gcr.io/buildpacks/builder:google-24` là ví dụ builder của Google Cloud; trước production phải xác minh builder, runtime và version hỗ trợ, đồng thời quản trị digest/bản cập nhật. Khi dùng builder mặc định có thể viết `--builder=gcr.io/buildpacks/builder`.

### 11.3. Chạy thử và kiểm tra

~~~bash
docker image inspect orders-api:pack-local \
  --format '{{.Size}}'

docker run --rm -p 8080:8080 orders-api:pack-local

# Terminal khác, nếu đã bật Spring Boot Actuator:
curl -i http://localhost:8080/actuator/health
~~~

Nếu ứng dụng dùng `/healthz` thay vì Actuator, đổi endpoint test. Kiểm tra HTTP response, logs startup, chứng chỉ TLS/JDBC và tài nguyên memory.

### 11.4. Khi nào Buildpacks phù hợp?

- Spring Boot/Maven/Gradle dùng build pipeline tương đối chuẩn.
- Nhiều nhóm muốn thống nhất build image mà không duy trì hàng chục Dockerfiles.
- Muốn tận dụng layering/rebase và build metadata ở builder phù hợp.
- Cloud Run source deployment là luồng phát hành đơn giản của nhóm.

Các giới hạn: phải hiểu detection logic, builder support, native OS dependencies và entrypoint. Image tạo ra **không mặc nhiên nhỏ nhất hoặc an toàn nhất**, phải đo/scan.

## 12. Cloud Build remote: buildpacks so với Dockerfile

Cloud Build có thể đóng gói source Java bằng buildpacks rồi push Artifact Registry. Ví dụ (repository đích phải đã tồn tại):

~~~bash
gcloud builds submit . \
  --pack image=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:pack-v1 \
  --project=PROJECT_ID
~~~

Cloud Build mặc định dùng `gcr.io/buildpacks/builder` nếu không chỉ builder. Muốn chọn cụ thể:

~~~bash
gcloud builds submit . \
  --pack builder=gcr.io/buildpacks/builder:google-24,image=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:pack-v1 \
  --project=PROJECT_ID
~~~

Đường Dockerfile multi-stage khác:

~~~bash
gcloud builds submit . \
  --tag=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:multi-v1 \
  --project=PROJECT_ID
~~~

| Lệnh | Nguồn chỉ dẫn build | Kết quả |
| --- | --- | --- |
| `gcloud builds submit --pack ...` | Buildpacks/builder/source descriptors | OCI image push lên Artifact Registry |
| `gcloud builds submit --tag ...` | Dockerfile tại build context | OCI image push lên Artifact Registry |
| `gcloud run deploy --source=.` | Buildpacks qua Cloud Build theo tính năng Cloud Run | Build từ source và deploy service |
| `gcloud run deploy --image=...` | Image đã được build/push | Deploy image theo tag/digest được chỉ định |

Tất cả thao tác build/push/deploy thật có thể phát sinh **chi phí Cloud Build, registry storage, network và runtime**. Quyền IAM của build identity và repository phải được chuẩn bị đúng; không chạy trong project chưa có quyền.

### 12.1. Đừng nhầm build cache local với Cloud Build

Cloud Build có worker/CI environment riêng; Docker/BuildKit cache local không tự chia sẻ giữa mọi runs. Buildpacks có cache/lifecycle riêng theo cách Cloud Build dùng builder. Khi quan sát thời gian build, phải đo đúng môi trường và thiết kế cache phù hợp.

## 13. Artifact Registry: lưu và phân phối Java images

**Artifact Registry** lưu images theo project, location, repository và IAM. Cloud Run/GKE có thể pull images qua các identity được phép.

### 13.1. Tạo Docker repository

Chỉ chạy khi project lab được cấp quyền, billing phù hợp và repository chưa tồn tại:

~~~bash
gcloud services enable artifactregistry.googleapis.com \
  --project=PROJECT_ID

gcloud artifacts repositories create java-images \
  --repository-format=docker \
  --location=asia-southeast1 \
  --description="Java application images" \
  --project=PROJECT_ID

gcloud artifacts repositories describe java-images \
  --location=asia-southeast1 \
  --project=PROJECT_ID
~~~

Địa chỉ image:

~~~text
asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:multi-v1
| LOCATION             | PROJECT  | REPO      | IMAGE:TAG
~~~

### 13.2. Build/push bằng Docker local

~~~bash
gcloud auth configure-docker asia-southeast1-docker.pkg.dev

docker build -t orders-api:multi-local .

docker tag orders-api:multi-local \
  asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:multi-v1

docker push \
  asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:multi-v1
~~~

`gcloud auth configure-docker` chỉ cấu hình credential helper, **không cấp quyền IAM**. Identity dùng push cần quyền như `roles/artifactregistry.writer` ở repository đích.

### 13.3. Ghi lại digest sau push

~~~bash
gcloud artifacts docker images list \
  asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api \
  --include-tags \
  --project=PROJECT_ID
~~~

Một image có thể được deploy theo digest:

~~~text
asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api@sha256:FULL_DIGEST
~~~

`FULL_DIGEST` phải được thay bằng digest thật. `:latest` hoặc `:multi-v1` là **tag có thể được gán lại**, không phải định danh bất biến của artifact. Với multi-platform OCI image, hãy nhận biết digest của image index và manifest kiến trúc.

### 13.4. Phân quyền theo vai trò

| Danh tính | Quyền cần xem xét | Lý do |
| --- | --- | --- |
| Cloud Build service account | Artifact Registry Writer tại repo | Push image |
| Cloud Run service agent/GKE node pull identity | Artifact Registry Reader khi cần | Pull image |
| CI/CD deployer | Quyền tạo revision/deploy và quyền `iam.serviceAccounts.actAs` khi có runtime SA | Phát hành |
| Runtime service account | IAM nghiệp vụ như Secret Manager, Storage, Pub/Sub | Chạy app, không cần Writer |
| Auditor | Đọc image metadata và vulnerability findings | Security review |

Danh tính **pull image** có thể khác danh tính chạy **Java application**. Quyền cụ thể còn phụ thuộc same-project/cross-project và kiến trúc Cloud Run/GKE.

## 14. Triển khai Java image lên Cloud Run

Với digest đã test và repository hợp lệ:

~~~bash
gcloud run deploy orders-api \
  --image=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api@sha256:FULL_DIGEST \
  --region=asia-southeast1 \
  --service-account=orders-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --port=8080 \
  --project=PROJECT_ID
~~~

**Lệnh có tác động thật**: tạo hoặc cập nhật Cloud Run service, cần IAM và có thể phát sinh phí. Service account giả định `orders-runtime` phải tồn tại, được quyền sử dụng bởi deployer và có quyền nghiệp vụ tối thiểu.

### 14.1. Cloud Run inject PORT

Cloud Run tự cung cấp biến `PORT` và yêu cầu ingress container listen trên `0.0.0.0` và đúng port. Ví dụ Spring Boot:

~~~properties
server.address=0.0.0.0
server.port=${PORT:8080}
management.endpoint.health.probes.enabled=true
~~~

`EXPOSE 8080` là image metadata, **không tự buộc ứng dụng lắng nghe**. Nếu app bind `127.0.0.1` hoặc bỏ qua `PORT`, revision có thể không khởi động để nhận requests.

### 14.2. Deploy trực tiếp từ source bằng buildpacks

~~~bash
gcloud run deploy orders-api \
  --source=. \
  --region=asia-southeast1 \
  --no-allow-unauthenticated \
  --project=PROJECT_ID
~~~

Cloud Run source deployment mặc định dùng **Google Cloud Buildpacks/Cloud Build**, rồi triển khai image build được. Cách này tiện lợi nhưng vẫn là **một build mới**. Nếu doanh nghiệp yêu cầu promotion chính xác **cùng digest** từ staging sang production, build một lần rồi deploy theo digest thường dễ audit hơn.

## 15. Triển khai image lên GKE

Kubernetes Deployment tham chiếu image từ Artifact Registry:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: orders-api
          image: asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api@sha256:FULL_DIGEST
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 5
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              memory: "1Gi"
~~~

Ví dụ giả định Spring Boot Actuator có endpoint readiness phù hợp. Nếu readiness URL không tồn tại, Pod có thể không nhận traffic dù JVM đang chạy. Còn cần Kubernetes Service, namespace, IAM/image pull quyền, networking, network policy và deployment controls theo cluster.

**Java memory:** heap là một phần bộ nhớ process; metaspace, stack và native memory cũng dùng memory. Đặt `-Xmx` sát `1Gi` limit có thể gây `OOMKilled`.

## 16. Multi-stage và Buildpacks: khi nào dùng?

| Tiêu chí | Docker multi-stage | Buildpacks |
| --- | --- | --- |
| Cần Dockerfile | Có | Thường không |
| Kiểm soát OS/runtime | Rất chi tiết | Theo builder/run image |
| Thư viện native/JNI đặc thù | Dễ điều chỉnh từng package | Có thể cần custom builder |
| Java/Spring Boot tiêu chuẩn | Phải bảo trì Dockerfile | Dễ bắt đầu |
| Caching | Layers, BuildKit, remote cache | CNB lifecycle/cache |
| Layered JAR | Cấu hình thủ công khi cần | Có thể có layering theo builder |
| Rebase run image | Thường rebuild/công cụ khác | Có thể rebase nếu compatible |
| Pin/rebuild/update base | Nhóm tự chịu trách nhiệm | Nhóm phải theo dõi builder/run image updates |
| Debug runtime | Tùy base; distroless khó debug | Tùy runtime image |
| OCI deployment | Cloud Run/GKE/VM | Cloud Run/GKE/VM |
| Image size | Có thể nhỏ, không bảo đảm nhỏ nhất | Có thể hiệu quả, không bảo đảm |

**Chọn Buildpacks** nếu dự án Java/Maven/Gradle tiêu chuẩn, muốn chuẩn hóa CI/CD và giảm maintenance Dockerfile. **Chọn multi-stage** nếu cần kiểm soát rõ native packages, distroless, runtime flags và image composition. Cả hai đều cần scan, test, pin dependencies và giám sát.

## 17. Reproducibility và bảo mật chuỗi cung ứng

### 17.1. Pin versions, cập nhật có kiểm soát

Các tag `maven:3.9-eclipse-temurin-21`, `gcr.io/distroless/java21-debian13:nonroot` và `gcr.io/buildpacks/builder:google-24` có thể cập nhật. Production nên:

1. Ghi Git commit SHA, builder version/digest, Java version, dependency lock và image digest.
2. Pin builder/base by **digest** theo chính sách release đã duyệt.
3. Pin Maven/Gradle plugin/dependency versions, tránh dynamic versions khi cần reproducibility.
4. Quản lý Maven repository mirror/chữ ký/checksum theo yêu cầu supply chain.
5. **Cập nhật base/JDK định kỳ**. Pin digest nhưng không bao giờ vá cũng là rủi ro.

### 17.2. Không truyền secret qua Docker build args

Ví dụ xấu:

~~~dockerfile
ARG MAVEN_PASSWORD
RUN echo "$MAVEN_PASSWORD" > /root/.m2/settings.xml
~~~

Secret có thể lộ trong build history, cache hoặc logs. Đối với Maven private repository, dùng BuildKit secrets hoặc secret injection được CI hỗ trợ:

~~~dockerfile
RUN --mount=type=secret,id=maven_settings,target=/root/.m2/settings.xml \
    mvn -B -ntp -DskipTests package
~~~

Đây chỉ là Dockerfile instruction, cần secret `maven_settings` do pipeline cung cấp qua kênh được phê duyệt. Không hardcode credentials trong build source, Dockerfile hoặc `project.toml`.

### 17.3. SBOM và vulnerability scanning

**Artifact Analysis** cung cấp tính năng container vulnerability scanning trong Artifact Registry khi được bật/cấu hình. Một số buildpacks sinh **SBOM** theo builder, nhưng không được giả định image nào cũng có SBOM đầy đủ.

Quy trình:

- Scan **image cuối cùng**, gồm cả OS layers và Java dependencies.
- Xem CVE severity, availability của bản vá, phạm vi exploit và release policy.
- Khi CVE từ base image, update/rebuild hoặc rebase nếu compatible.
- Khi CVE từ JAR library, update dependency và build lại.
- Lưu source commit, provenance, scan result, SBOM và image digest.
- Kiểm tra phí/cơ chế kích hoạt scanning; **không mặc định mọi repo đã bật auto scan**.

**Distroless không xóa vulnerabilities trong Spring/Jackson/Log4j**. Giảm package OS là một phần nhỏ của security hygiene.

### 17.4. Runtime identity

- Chạy non-root khi phù hợp; writable paths phải được kiểm tra.
- Dùng ADC, Workload Identity Federation hoặc runtime service account; tránh JSON service-account key.
- Chỉ cấp IAM cho Cloud Storage, Pub/Sub, Secret Manager hoặc Cloud SQL thật sự dùng.
- Bảo vệ image pull/deploy identities riêng với app service account.
- Không đưa token, private key, `.env` hoặc PII vào image/logs.

## 18. CI/CD: build một lần, triển khai cùng digest

~~~mermaid
flowchart TD
    COMMIT["Git commit SHA"] --> TEST["Unit/integration tests"]
    TEST --> BUILD["Multi-stage hoặc Buildpacks"]
    BUILD --> SCAN["Scan + SBOM/provenance"]
    SCAN --> PUSH["Push Artifact Registry"]
    PUSH --> DIGEST["Ghi image digest"]
    DIGEST --> STG["Deploy staging theo digest"]
    STG --> SMOKE["Smoke/performance test"]
    SMOKE --> APPROVE{"Release gate đạt?"}
    APPROVE -->|Có| PROD["Deploy production cùng digest"]
    APPROVE -->|Không| STOP["Dừng release và xử lý lỗi"]
    PROD --> MON["Monitoring, rollback nếu cần"]
~~~

Checklist:

- `mvn verify` hoặc Gradle tests chạy trước packaging nếu Dockerfile skip tests.
- CI identity có quyền push nhưng không tự có quyền production admin.
- PR không tin cậy không được sử dụng credentials production.
- Promotion sử dụng **same digest**, không rebuild với dynamic tag.
- Giữ revision/digest cũ làm rollback.
- Có approval, audit logs và scan gate.

**Rebase không sửa dependency của ứng dụng:** thay run-image layers compatible chưa vá những JAR chứa CVE; phải cập nhật Maven/Gradle dependencies rồi build lại.

## 19. Đo kết quả: size, thời gian, startup và memory

| Metric | Cách lấy | Điều cần hiểu |
| --- | --- | --- |
| Local size | `docker image inspect --format '{{.Size}}' IMAGE` | Không nhất thiết bằng bytes nén khi pull |
| Layer history | `docker history --no-trunc IMAGE` | Lớp nào đổi, có lộ build commands không |
| Cold build | Build trong môi trường cache rỗng | Chi phí build ban đầu |
| Warm build | Build lại sau sửa code nhỏ | Cache hit thực |
| Push/pull time | Build/registry/runtime logs | Network, compressed layers và cache |
| Startup/ready | Cloud Run revision/GKE logs | Java/framework init |
| First request latency | HTTP smoke test có timestamp | Trải nghiệm khi vừa ready |
| CPU/memory | JVM/Cloud Monitoring metrics | Runtime efficiency |
| CVE findings | Artifact Analysis/scanner | Rủi ro base/app |
| Cost | Billing Reports | Build, registry, network, runtime |

### 19.1. Benchmark có kiểm soát

Dùng **cùng commit, JDK 21, CPU architecture, builder machine size, memory và network conditions**. Đo cold/warm builds riêng, chạy nhiều lần và ghi thông tin cache.

| Thước đo | Single-stage | Multi-stage | Buildpacks |
| --- | --- | --- | --- |
| Image size | Tự đo | Tự đo | Tự đo |
| Cold build time | Tự đo | Tự đo | Tự đo |
| Warm build time | Tự đo | Tự đo | Tự đo |
| Push duration | Tự đo | Tự đo | Tự đo |
| Startup to ready | Tự đo | Tự đo | Tự đo |
| Memory | Tự đo | Tự đo | Tự đo |
| Critical CVEs | Tự scan | Tự scan | Tự scan |

**Không tự khẳng định image nhỏ hơn 70% hoặc cold-start nhanh gấp đôi** khi chưa đo. Tác động thay đổi theo frameworks, dependencies, base images và runtime.

## 20. Troubleshooting

| Triệu chứng | Nguyên nhân | Kiểm tra |
| --- | --- | --- |
| `COPY --from=build ...jar` lỗi | Sai JAR path/version | `target/`, Maven plugin, build logs |
| `no main manifest attribute` | JAR không executable | Spring Boot packaging/plugin |
| `UnsupportedClassVersionError` | Java runtime cũ hơn compile version | JDK release/target vs JRE |
| `sh: not found` | Distroless không có shell | JSON-form CMD/ENTRYPOINT |
| `Permission denied` | Nonroot không đọc/ghi path | File permissions, writable paths |
| Cloud Run not ready | App không listen `0.0.0.0:$PORT` hoặc startup lâu | Logs, Spring Boot port/host |
| `OOMKilled`/137 | Heap + native memory vượt limit | JVM memory, pod/Cloud Run limits |
| TLS/JNI lỗi sau đổi base | Thiếu certificate/native lib/timezone | Runtime dependencies/integration tests |
| Buildpacks không detect | Sai source root/`pom.xml` | Detection logs và builder support |
| Buildpacks chọn sai Java | Thiếu `GOOGLE_RUNTIME_VERSION` | `project.toml`/build logs |
| `pack build` local lỗi | Docker daemon/builder pull/architecture | Engine, credentials, network |
| Artifact Registry push `403` | Auth/IAM Writer hoặc repo URL sai | Configure Docker, IAM, repo |
| Cloud Run pull image lỗi | Digest sai, cross-project IAM | Service agent/Reader, image URL |
| CI build chậm | Cache chưa reuse hoặc `COPY . .` quá sớm | Layer order, cache mounts |
| Startup chậm dù image nhỏ | Java classpath/framework/DB init | JVM profiling, metrics |
| Scan có nhiều CVEs | App dependencies hoặc base cũ | SBOM, update JAR/runtime |

~~~mermaid
flowchart TD
    A["Build/deploy thất bại"] --> B{"JAR build được?"}
    B -->|Không| C["Maven/Gradle/JDK logs"]
    B -->|Có| D{"Image artifact/runtime đúng?"}
    D -->|Không| E["COPY, CMD/ENTRYPOINT, platform"]
    D -->|Có| F{"docker run local được?"}
    F -->|Không| G["Java, permissions, libraries"]
    F -->|Có| H{"Push/pull Artifact Registry được?"}
    H -->|Không| I["IAM, registry URL, digest"]
    H -->|Có| J{"Cloud Run/GKE ready?"}
    J -->|Không| K["PORT, probe, memory, IAM, VPC"]
    J -->|Có| L["Theo dõi SLO và chi phí"]
~~~

## 21. Chi phí và vòng đời images

| Thành phần | Chi phí tiềm năng |
| --- | --- |
| **Cloud Build** | Build time, máy build, số lần thực hiện |
| **Artifact Registry** | Image/layer storage, data transfer và operations |
| **Cloud Run** | CPU/memory, request, concurrency, min instances, billing model |
| **GKE** | Node/cluster resources, image pulls/autoscaling |
| **Network** | Truyền dữ liệu giữa locations và services |
| **Artifact Analysis** | Scanning theo tính năng và cấu hình |
| **Logging/Monitoring** | Logs, metrics và lưu trữ |

**Image nhỏ không tự làm Cloud Run bill giảm cùng phần trăm**. Runtime CPU/memory, request duration và application behavior vẫn quyết định phần lớn chi phí ứng dụng.

### 21.1. Cleanup và rollback

- Quản lý tags theo release/commit, lưu digest đang triển khai.
- Dùng Artifact Registry cleanup policies để dọn artifacts không còn sử dụng.
- Không xóa digest vẫn được Cloud Run revision/GKE deployment/rollback plan tham chiếu.
- Kiểm tra untagged images và registry storage theo kỳ.
- Sau lab, chỉ xóa resource khi đã xác nhận không workload nào phụ thuộc.

## 22. Tình huống tổng hợp: Orders API

Nhóm Commerce có dịch vụ Spring Boot Java 21 chạy trên Cloud Run, gọi Cloud SQL, Pub/Sub và Cloud Storage. Nhóm muốn pipeline bảo trì đơn giản, runtime non-root và release có thể tái hiện.

| Nhu cầu | Giải pháp đáng thử |
| --- | --- |
| Maven/Spring Boot chuẩn | Google Cloud Buildpacks |
| Runtime tối giản và custom dependencies | Multi-stage + distroless |
| CI/CD nhiều môi trường | Build một lần, deploy cùng digest |
| Secrets và DB credentials | Runtime identity/Secret Manager |
| Vulnerability policy | Artifact Analysis + Maven dependency scanning |
| Rollback | Cloud Run revisions và image digests |
| Cost review | Build time, image storage, startup, runtime bill |

**Bài thực hành đánh giá:**

1. Chạy `mvn -B -ntp verify` cho cùng commit.
2. Build multi-stage, ghi image size, digest, duration.
3. Build bằng `pack` với `GOOGLE_RUNTIME_VERSION=21` và ghi dữ liệu tương tự.
4. Chạy cùng HTTP smoke tests locally.
5. Push hai images lên cùng Artifact Registry region; lấy digest thực.
6. Deploy hai Cloud Run test services private có cùng cấu hình CPU/memory/concurrency.
7. Đo startup, p95 latency, errors, memory, TLS/JDBC.
8. Scan, kiểm tra SBOM và vulnerabilities.
9. Chọn phương án dựa trên **bằng chứng + khả năng bảo trì**.
10. Dọn test services/images an toàn sau khi không còn sử dụng.

Nếu Buildpacks cho image lớn hơn chút nhưng dễ vận hành và runtime tương đương, nhóm có thể chọn Buildpacks. Nếu cần JNI/OS packages đặc biệt, multi-stage có thể phù hợp hơn. **Không có một giải pháp luôn thắng.**

## 23. Bài tập tự kiểm tra

**Câu 1.** Vì sao single-stage Maven image có thể không phù hợp production?

*Đáp án:* Mang compiler, build tools, cache và source không cần khi chạy.

**Câu 2.** Vì sao `COPY pom.xml` nên đặt trước `COPY src`?

*Đáp án:* Để dependency cache được reuse khi chỉ sửa code.

**Câu 3.** BuildKit `--mount=type=cache,target=/root/.m2` có đưa Maven cache vào runtime image không?

*Đáp án:* Không. Đây là cache của builder, không phải artifact được copy.

**Câu 4.** Với Java distroless base, vì sao `CMD ["/app/app.jar"]` đúng?

*Đáp án:* Image có entrypoint tương đương `java -jar`; CMD cung cấp JAR.

**Câu 5.** Vì sao `CMD ["sh","-c","..."]` có thể lỗi trên distroless?

*Đáp án:* Image không có shell mặc định.

**Câu 6.** `EXPOSE 8080` đủ cho Cloud Run ready không?

*Đáp án:* Không, app cần listen `0.0.0.0` và đúng `PORT`.

**Câu 7.** Buildpacks biết đây là Maven app bằng cách nào?

*Đáp án:* Builder detection dựa trên source descriptor như `pom.xml`.

**Câu 8.** Chọn Java 21 cho Google Cloud Buildpacks bằng gì?

*Đáp án:* `GOOGLE_RUNTIME_VERSION=21` trong build env/`project.toml`.

**Câu 9.** Deploy from source khác deploy digest như thế nào?

*Đáp án:* Source deployment phát sinh build; digest deployment dùng đúng artifact đã build/test.

**Câu 10.** `:latest` có bất biến không?

*Đáp án:* Không. Digest phù hợp hơn để pin image.

**Câu 11.** Distroless có xóa mọi lỗ hổng Java không?

*Đáp án:* Không. App dependencies và runtime vẫn cần scan/vá.

**Câu 12.** CNB rebase có tự sửa Spring dependency không?

*Đáp án:* Không, rebase chỉ thay compatible run image layers.

**Câu 13.** Runtime app service account cần Artifact Registry Writer để chạy không?

*Đáp án:* Thường không; push identity cần Writer, pull identity cần Reader khi áp dụng.

**Câu 14.** Local image 100 MB có chắc push nhanh gấp đôi image 200 MB không?

*Đáp án:* Không, compression/cache/network quyết định thêm.

**Câu 15.** Image nhỏ có chắc cold start nhanh không?

*Đáp án:* Không, JVM init, dependencies và resource allocation cũng ảnh hưởng.

**Câu 16.** JNI driver lỗi khi chuyển sang distroless, xử lý thế nào?

*Đáp án:* Kiểm tra OS/native dependencies và chọn runtime đáp ứng đúng workload.

**Câu 17.** Vì sao không đặt secret vào Docker `ARG`?

*Đáp án:* Có thể lộ qua build history, cache hoặc logs; dùng secret mounts.

**Câu 18.** Khi nào nên thử Buildpacks trước?

*Đáp án:* Java/Maven/Gradle chuẩn và muốn giảm bảo trì Dockerfile, nhưng vẫn cần benchmark/scan.

## 24. Checklist trước production

- [ ] Chốt Java version, Maven/Gradle/plugin/dependencies; chạy tests trong CI.
- [ ] Multi-stage chỉ copy runtime artifact, không mang Maven/Gradle/source/cache.
- [ ] `.dockerignore` loại file thừa và những tệp có thể chứa secrets.
- [ ] Cache hoạt động ở môi trường build thật; không giả định CI nodes chia sẻ cache.
- [ ] Java compile target tương thích Java runtime.
- [ ] Non-root, filesystem, certificates/JNI/timezone đáp ứng yêu cầu.
- [ ] Distroless CMD/ENTRYPOINT dạng exec phù hợp; không cần shell.
- [ ] Java listen đúng `0.0.0.0:$PORT` trên Cloud Run.
- [ ] Builder/base images được pin và có lịch update security.
- [ ] Secrets không nằm trong image layers, Docker build args hoặc source.
- [ ] Artifact Registry repo/location/IAM Writer/Reader đã xác minh.
- [ ] Image cuối được scan; SBOM/provenance có khi policy yêu cầu.
- [ ] Staging/production dùng **cùng digest đã kiểm thử**.
- [ ] Có smoke test, readiness, CPU/memory/latency metrics và rollback.
- [ ] Đã đo cold/warm build, push/pull, startup, vulnerabilities và chi phí.
- [ ] Có retention/cleanup không làm mất artifact rollback.
- [ ] Có budget và owner cho project lab/CI/CD.

## 25. Những điểm cần nhớ

- **Multi-stage** tách build tools/JDK khỏi runtime và chỉ copy artifact cần chạy.
- **Buildpacks** tự detect Maven/Gradle, tạo OCI image theo builder, giảm nhu cầu tự duy trì Dockerfile.
- **.dockerignore, layer ordering và BuildKit cache** giúp tăng hiệu quả build, không tự bảo đảm runtime nhanh.
- **Distroless Java** có entrypoint `java -jar` và thiếu shell mặc định; kiểm tra CMD/non-root/OS dependencies.
- **Image nhỏ không tự đồng nghĩa an toàn hơn, cold start nhanh hơn hoặc bill thấp hơn**.
- **Artifact Registry** lưu images với IAM/location; tag để đặt tên, **digest** để phát hành bất biến.
- **Build once, test, scan, promote same digest** tăng khả năng truy vết và rollback.
- **SBOM, scanning, cập nhật dependencies/base/JDK** vẫn cần cho cả Dockerfile và Buildpacks.
- **Chi phí** gồm build, storage, transfer, scanning và runtime, không chỉ số MB của JAR.

Khi triển khai Java lên GKE, Compute Engine hoặc Cloud Run, hãy hỏi: **“Image cuối có đúng những gì ứng dụng cần chạy? Nếu chỉ sửa code, bước nào phải build lại? Builder/JDK/CVEs được quản lý ra sao? Production có đúng digest đã qua kiểm thử không?”** Multi-stage và Buildpacks cung cấp hai cách khác nhau để giải quyết cùng bài toán đóng gói có kiểm soát.

## Tài liệu tham khảo chính thức

- [Docker multi-stage builds](https://docs.docker.com/build/building/multi-stage/)
- [Docker build cache optimization](https://docs.docker.com/build/cache/optimize/)
- [Docker Build secrets](https://docs.docker.com/build/building/secrets/)
- [Google Cloud Buildpacks overview](https://cloud.google.com/docs/buildpacks/overview)
- [Building Java with Google Cloud Buildpacks](https://cloud.google.com/docs/buildpacks/java)
- [Build application with buildpacks](https://cloud.google.com/docs/buildpacks/build-application)
- [Use a specific builder](https://cloud.google.com/docs/buildpacks/use-a-specific-builder)
- [Cloud Build: Build container images](https://cloud.google.com/build/docs/building/build-containers)
- [Cloud Run: Deploy from source](https://cloud.google.com/run/docs/deploying-source-code)
- [Cloud Run: Container runtime contract](https://cloud.google.com/run/docs/container-contract)
- [Artifact Registry: Push and pull images](https://cloud.google.com/artifact-registry/docs/docker/pushing-and-pulling)
- [Artifact Analysis and vulnerability scanning](https://cloud.google.com/artifact-registry/docs/analysis)
- [Distroless Java runtime README](https://github.com/GoogleContainerTools/distroless/blob/main/java/README.md)
- [Cloud Native Buildpacks documentation](https://buildpacks.io/docs/)
- [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing)


