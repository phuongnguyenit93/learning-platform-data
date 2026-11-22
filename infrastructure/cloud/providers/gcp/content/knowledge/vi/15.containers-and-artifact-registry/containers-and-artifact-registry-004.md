# Lưu Maven artifacts cho dự án Java bằng Artifact Registry

> **Chương:** Container và Artifact Registry  
> **Bài học:** Lưu Maven artifacts cho dự án Java  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành, theo dõi độ tin cậy cùng chi phí. Một năng lực thiết yếu của quy trình phát hành Java là **lưu trữ, quản lý phiên bản và phân phối những thư viện đã được build**, thay vì sao chép JAR thủ công hoặc build lại cùng một package ở mọi ứng dụng.

**Artifact Registry** hỗ trợ repository theo nhiều định dạng; **Maven-format repositories** lưu JAR, POM và các Java artifacts dùng với Maven hoặc Gradle. Bài thực hành sẽ publish thư viện `order-common` vào một **standard Maven repository**, sau đó để ứng dụng `orders-api` sử dụng lại qua Maven dependency. Ta cũng tìm hiểu xác thực bằng **Application Default Credentials (ADC)**, phân quyền CI/CD, version policy và quản trị dependencies.

**Không nhầm Maven repository với Docker repository**: kho Maven lưu Java packages theo groupId/artifactId/version; kho Docker lưu OCI container images để Cloud Run hoặc GKE triển khai. Cả hai cùng thuộc Artifact Registry nhưng **mỗi repository chỉ có một artifact format**. Publish một JAR lên Maven repository **không tự triển khai** ứng dụng lên Cloud Run.

Mọi project ID, repository, package và service account trong bài là ví dụ. Các lệnh tạo repository, chỉnh IAM, publish, xóa package có thể làm thay đổi hạ tầng và phát sinh phí; chỉ chạy trên **sandbox đã được phê duyệt**.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt Maven artifact, Maven coordinates, POM, repository, version, snapshot và release.
2. Chọn đúng **standard, remote hoặc virtual repository** cho việc publish nội bộ và tải dependencies.
3. Tạo standard Maven repository bằng Console/`gcloud`, chọn location và version policy phù hợp.
4. Cấu hình `pom.xml` để **publish** qua `distributionManagement` và **consume** qua `repositories`.
5. Dùng **Artifact Registry Maven wagon** hoặc **Gradle plugin** với ADC thay vì lưu private key trong mã nguồn.
6. Chạy `mvn deploy` hoặc `gradle publish`, sau đó xác nhận package và version trong Artifact Registry.
7. Dùng thư viện Java nội bộ ở một dự án khác và chẩn đoán trường hợp parent POM/plugin không resolve.
8. Phân quyền Reader/Writer/Admin theo vai trò developer, CI publisher và consumer.
9. Thiết kế quy trình phát hành, tái lập build, quản lý snapshots, cleanup, supply-chain security và chi phí.
10. Khoanh vùng lỗi 401/403/404, protocol `artifactregistry://`, policy mismatch, Maven cache và network.

## 2. Maven artifacts đóng vai trò gì trong kiến trúc Java?

~~~mermaid
flowchart LR
    Git["Git: order-common<br/>Java source"]
    CI["CI: Maven verify<br/>package + test"]
    MavenRepo["Artifact Registry<br/>Maven standard"]
    Consumer["orders-api<br/>Maven dependency"]
    Build["Build ứng dụng<br/>JAR hoặc OCI image"]
    Docker["Artifact Registry<br/>Docker repository"]
    Runtime["Cloud Run / GKE"]
    VM["Compute Engine"]
    Git --> CI
    CI -->|"Writer / publish"| MavenRepo
    MavenRepo -->|"Reader / download"| Consumer
    Consumer --> Build
    Build --> Docker
    Docker --> Runtime
    Build --> VM
~~~

**Các thành phần có nhiệm vụ khác nhau:**

- **Java library**: mã tái sử dụng, ví dụ bộ chuẩn hóa mã đơn hàng, API client hoặc SDK công ty.
- **Maven build**: giải quyết dependency graph, biên dịch, kiểm thử, đóng gói artifact và tạo POM metadata.
- **Maven repository**: nơi có thể truy xuất một package ở một version cụ thể.
- **Docker repository**: nơi lưu container image sau khi ứng dụng được đóng gói với runtime.
- **Cloud Run/GKE**: chạy image; không trực tiếp chạy Maven package trong registry.
- **Compute Engine**: có thể chạy Java JAR bằng systemd hoặc image/instance template; không bắt buộc sử dụng Docker.

### 2.1. Khi nào nên có kho Maven nội bộ?

| Trường hợp | Lợi ích |
|---|---|
| Thư viện chung cho Orders, Billing và Inventory | Mỗi consumer phụ thuộc một version đã kiểm thử |
| SDK nội bộ hoặc client tích hợp API | Tái sử dụng contract có kiểm soát |
| Parent POM hoặc BOM công ty | Quản lý version và quy ước build |
| Thư viện không được công khai | IAM, audit và quyền phát hành nội bộ |
| Pipeline cần artifact tái lập | Lưu GAV và build metadata để rollback |
| Ứng dụng Spring Boot cần lưu JAR trước khi tạo image | Có thể lưu JAR và container ở hai repository format riêng |

Nếu một ứng dụng chỉ có một codebase và luôn build/deploy nguyên image, việc tạo thêm Maven repository riêng **không bắt buộc**. Cần xem xét số lượng consumer và chi phí vận hành.

## 3. Maven coordinates và package layout

Maven thường xác định artifact qua **GAV**:

~~~text
groupId    : com.example.platform
artifactId : order-common
version    : 1.0.0-SNAPSHOT

GAV = com.example.platform:order-common:1.0.0-SNAPSHOT
~~~

| Thuộc tính | Vai trò | Ví dụ |
|---|---|---|
| `groupId` | Namespace của tổ chức | `com.example.platform` |
| `artifactId` | Định danh module | `order-common` |
| `version` | Phiên bản | `1.0.0-SNAPSHOT` |
| `packaging` | Loại artifact | `jar` hoặc `pom` |
| `classifier` | Biến thể file, nếu publish | `sources`, `javadoc` |
| `dependency scope` | Cách consumer sử dụng | `compile`, `runtime`, `test` |

Ví dụ layout một release:

~~~text
com/example/platform/order-common/1.0.0/
  order-common-1.0.0.pom
  order-common-1.0.0.jar
  order-common-1.0.0-sources.jar     (nếu xuất bản)
  order-common-1.0.0-javadoc.jar     (nếu xuất bản)
~~~

**POM không chỉ là file trang trí.** POM chứa tọa độ, dependencies, metadata và thông tin packaging. Publish JAR mà không có POM phù hợp có thể khiến Maven consumer không giải được dependencies bắc cầu hoặc nhận metadata sai.

### 3.1. Snapshot và release

| Loại | Ví dụ | Ý nghĩa | Thực hành |
|---|---|---|---|
| Snapshot | `1.0.0-SNAPSHOT` | Bản đang phát triển, có thể thay đổi ở lần build tiếp | Dùng dev/test |
| Release | `1.0.0` | Bản được chốt theo quy trình phát hành | Dùng production |
| Pre-release theo quy ước | `1.1.0-rc.1` | Bản ứng viên trước phát hành | Cần chính sách rõ trong nhóm |

Maven 3 dùng **timestamped unique snapshots** khi deploy. Nhiều bản được publish dưới cùng base version `1.0.0-SNAPSHOT` nhưng có timestamp/build number khác; consumer có thể nhận bản cập nhật theo Maven metadata và update policy. **Không dùng snapshot không pin cho một bản production yêu cầu tái lập tuyệt đối.**

### 3.2. Artifact Registry Maven version policy

Artifact Registry hỗ trợ ba chính sách tại thời điểm tạo repository:

- **None**: lưu cả snapshot và release; là mặc định.
- **Snapshot**: chỉ lưu snapshot.
- **Release**: chỉ lưu release.

Có tùy chọn cho phép non-unique snapshot overwrite ở repository Snapshot; Maven 3 nên dùng **unique snapshot versions** để tránh mâu thuẫn cache. Nếu repository có policy Release, `mvn deploy` với version kết thúc bằng `-SNAPSHOT` sẽ bị từ chối cho dù IAM và URL đều đúng.

## 4. Standard, remote và virtual repositories

| Chế độ | Mục đích | Publish JAR nội bộ? |
|---|---|---|
| **Standard** | Kho chủ động lưu package do tổ chức build | **Có** |
| **Remote** | Proxy/cache nguồn upstream như Maven Central | **Không**, dùng cho đọc/cache |
| **Virtual** | Một điểm truy xuất hợp nhất từ nhiều standard/remote upstream | **Không dùng làm đích publish trực tiếp** |

~~~mermaid
flowchart TD
    Dev["Developer / CI publish"]
    Release["Standard: java-release"]
    Snap["Standard: java-snapshot"]
    Remote["Remote: maven-central-cache"]
    Virtual["Virtual: java-dependencies"]
    Apps["Maven / Gradle consumers"]
    Central["Maven Central"]
    Dev --> Release
    Dev --> Snap
    Central --> Remote
    Release --> Virtual
    Snap --> Virtual
    Remote --> Virtual
    Virtual --> Apps
~~~

Trong mô hình doanh nghiệp:

1. **CI publisher** ghi vào standard repository đúng loại version.
2. **Consumer** có thể đọc qua virtual repository nếu upstream và IAM được cấu hình.
3. **Remote Maven Central** tải package từ upstream khi chưa cache và phục vụ lại bản cache khi có.
4. **Virtual** quyết định upstream theo priority khi một tọa độ/version có ở nhiều nguồn.
5. **Dependency confusion** có thể xảy ra khi GAV nội bộ trùng với package từ kho ngoài. Chọn namespace khó bị trùng, kiểm soát priority và thử resolution.

Remote không tự proxy được mọi repository private trong VPC/on-premises; loại upstream và khả năng kết nối phải đáp ứng yêu cầu của dịch vụ. Với mục tiêu học cách publish, bài lab chỉ dùng **standard repository `java-libs-lab`**.

## 5. Chuẩn bị project, API, mạng và IAM

### 5.1. Tham số lab

| Thuộc tính | Giá trị giả định |
|---|---|
| Project chứa repository | `PROJECT_ID` |
| Location | `asia-southeast1` |
| Artifact Registry API | `artifactregistry.googleapis.com` |
| Repository ID | `java-libs-lab` |
| Format / Mode | Maven / Standard |
| Version policy | None (nhận snapshot và release) |
| Maven GAV | `com.example.platform:order-common:1.0.0-SNAPSHOT` |
| Java | JDK 17 |
| Build tool | Maven 3.x, Gradle cho phần mở rộng |
| CI publisher | Service account riêng, có Writer |
| Consumer | Người dùng hoặc workload có Reader |

Đọc trạng thái (không thay đổi tài nguyên):

~~~bash
gcloud auth list
gcloud config get-value project

gcloud services list --enabled \
  --project=PROJECT_ID \
  --filter="NAME:artifactregistry.googleapis.com"

gcloud artifacts repositories list \
  --project=PROJECT_ID \
  --location=asia-southeast1
~~~

Nếu API chưa bật, người quản trị có quyền phù hợp phải bật theo quy trình; không tự cấp Owner để “làm cho chạy”. Với VPC private, còn phải kiểm tra DNS/HTTPS egress hoặc cách truy cập Google APIs được tổ chức thiết kế.

### 5.2. Ma trận IAM theo nhiệm vụ

| Nhóm / identity | Role phù hợp | Scope |
|---|---|---|
| Người hoặc pipeline chỉ download dependency | `roles/artifactregistry.reader` | Maven repository cần đọc |
| CI phát hành thư viện | `roles/artifactregistry.writer` | Standard repository đích |
| Người quản lý package và xóa phiên bản | `roles/artifactregistry.repoAdmin` | Repository phụ trách |
| Người quản lý cấp project và tạo repository | `roles/artifactregistry.admin` | Phạm vi được phê duyệt |

**Repository Writer không đồng nghĩa Repository Administrator.** Người publish phần lớn không cần tạo repository, xóa repository hay sửa IAM của cả project. Pipeline chạy từ project khác phải được cấp quyền **ở repository project**.

### 5.3. Các ranh giới bảo mật

- Không nhúng service account JSON/private key vào `pom.xml` hoặc `build.gradle`.
- Người dùng chỉ tải dependency không cần quyền upload/delete.
- Runtime Cloud Run/GKE/VM không cần Writer nếu đã nhận artifact được build sẵn.
- Bảo vệ repository bằng IAM, TLS và quy trình provenance; đừng suy rằng artifact nội bộ tự an toàn.
- Chi phí lưu trữ, egress, Cloud KMS, logging và CI/CD cần đưa vào dự toán.

## 6. Bước 1 — Tạo standard Maven repository

**Những lệnh dưới đây tạo tài nguyên thật và có thể phát sinh phí. Chỉ chạy trong sandbox.**

### 6.1. Dùng Google Cloud Console

1. Mở **Artifact Registry → Repositories** trong project đã được phê duyệt.
2. Chọn **Create repository**, tên `java-libs-lab`.
3. Chọn **Format: Maven**, **Mode: Standard**.
4. Chọn location `asia-southeast1` hoặc region/multi-region được hỗ trợ.
5. Chọn Maven version policy **None** cho bài lab.
6. Kiểm tra encryption (Google-managed mặc định; CMEK nếu chính sách yêu cầu), labels và cleanup.
7. Tạo repository và đọc lại trường format/mode/location.

### 6.2. Dùng gcloud

~~~bash
gcloud artifacts repositories create java-libs-lab \
  --project=PROJECT_ID \
  --repository-format=maven \
  --location=asia-southeast1 \
  --description="Java Maven package repository for training" \
  --version-policy=none

gcloud artifacts repositories describe java-libs-lab \
  --project=PROJECT_ID \
  --location=asia-southeast1
~~~

Đọc output để xác nhận `format: MAVEN`, mode standard và `mavenConfig` tương ứng. Tùy version/API, các trường có thể biểu diễn khác nhau.

### 6.3. Tách release/snapshot khi lên production

~~~bash
gcloud artifacts repositories create java-libs-snapshot \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --repository-format=maven \
  --version-policy=snapshot

gcloud artifacts repositories create java-libs-release \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --repository-format=maven \
  --version-policy=release
~~~

Đây là mô hình tham khảo; cần thống nhất naming, owner và chính sách bảo quản. **Đừng gắn Writer rộng lên cả release và snapshot repository** nếu pipeline chỉ có nhiệm vụ xuất snapshot.

### 6.4. Đọc URL repository

~~~text
artifactregistry://asia-southeast1-maven.pkg.dev/PROJECT_ID/java-libs-lab
                   └─ location ─┘      project    repository
~~~

Scheme `artifactregistry://` yêu cầu transport helper mà Maven wagon hoặc Gradle plugin hỗ trợ. HTTPS endpoint có thể được dùng với cơ chế authentication khác, nhưng **không tự đổi scheme rồi bỏ phần helper**.

## 7. Bước 2 — Tạo Java library và POM

Ví dụ package `order-common` có một hàm chuẩn hóa order code.

~~~text
order-common/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/platform/OrderCode.java
~~~

### 7.1. Java source

~~~java
package com.example.platform;

import java.util.Locale;
import java.util.Objects;

public final class OrderCode {
    private OrderCode() { }

    public static String normalize(String raw) {
        String value = Objects.requireNonNull(raw, "raw").trim();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("order code must not be empty");
        }
        return value.toUpperCase(Locale.ROOT);
    }
}
~~~

Đây là thư viện thuần Java, không cần Google Cloud API hoặc credential tại runtime.

### 7.2. POM của publisher

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example.platform</groupId>
  <artifactId>order-common</artifactId>
  <version>1.0.0-SNAPSHOT</version>
  <packaging>jar</packaging>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <distributionManagement>
    <snapshotRepository>
      <id>artifact-registry</id>
      <url>artifactregistry://asia-southeast1-maven.pkg.dev/PROJECT_ID/java-libs-lab</url>
    </snapshotRepository>
    <repository>
      <id>artifact-registry</id>
      <url>artifactregistry://asia-southeast1-maven.pkg.dev/PROJECT_ID/java-libs-lab</url>
    </repository>
  </distributionManagement>

  <build>
    <extensions>
      <extension>
        <groupId>com.google.cloud.artifactregistry</groupId>
        <artifactId>artifactregistry-maven-wagon</artifactId>
        <version>2.2.5</version>
      </extension>
    </extensions>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Thay `PROJECT_ID` bằng project thật trước khi chạy. Các version plugin là ví dụ cụ thể phù hợp luồng hướng dẫn, **cần kiểm tra khả năng tương thích với Maven/JDK và release notes hiện hành** khi nâng cấp.

### 7.3. Ba khu vực cấu hình khác nhau

| POM section | Chức năng | Câu hỏi |
|---|---|---|
| `<distributionManagement>` | Định nghĩa nơi `mvn deploy` **upload artifacts** | Publish đi đâu? |
| `<repositories>` | Định nghĩa nơi Maven **download dependencies** | Build tải thư viện từ đâu? |
| `<build><extensions>` | Nạp Maven wagon cho `artifactregistry://` | Maven dùng transport/auth helper nào? |

Một dự án **chỉ consume** không cần `distributionManagement`. Một dự án **publish** mà chỉ có `<repositories>` thường nhận lỗi thiếu deploy repository.

### 7.4. Dùng `print-settings` thay vì đoán XML

~~~bash
gcloud artifacts print-settings mvn \
  --project=PROJECT_ID \
  --repository=java-libs-lab \
  --location=asia-southeast1
~~~

Đây là lệnh **in cấu hình** do Google Cloud gợi ý cho repository tương ứng. Với dự án có POM phức tạp, chèn đúng các đoạn vào `distributionManagement`, `repositories` và `build` sẵn có, không tạo nhiều phần tử cấp gốc cùng tên.

## 8. Bước 3 — Xác thực Maven an toàn

### 8.1. Credential helper và ADC

Artifact Registry Maven wagon có thể lấy thông tin xác thực từ **Application Default Credentials** và ngữ cảnh Google Cloud CLI phù hợp. Ưu tiên:

| Môi trường | Cơ chế nên dùng |
|---|---|
| Laptop lập trình viên | ADC người dùng theo chính sách tổ chức |
| Cloud Shell | Identity hiện có, xác minh quyền thực tế |
| Cloud Build | Service account của build, IAM Reader/Writer phù hợp |
| Compute Engine | Service account gắn VM nếu pipeline build chạy trên VM |
| GKE/Cloud Run workloads | Workload identity hoặc service identity phù hợp |
| CI ngoài Google Cloud | Workload Identity Federation/short-lived credentials |

Kiểm tra:

~~~bash
gcloud auth list
gcloud config get-value project
~~~

Với **máy phát triển cục bộ** và theo quy trình được phê duyệt, có thể tạo ADC:

~~~bash
gcloud auth application-default login
~~~

`gcloud auth login` và `gcloud auth application-default login` **có thể quản lý các ngữ cảnh credentials khác nhau**. Một người nhìn thấy account đúng ở `gcloud auth list` vẫn có thể khiến Maven dùng identity khác. Trong CI không tương tác, **không chạy lệnh login dành cho con người**; sử dụng service identity/federation.

Không in hoặc dán access token vào log chỉ để kiểm tra. Thử lệnh đọc repository hoặc build một package không nhạy cảm rồi phân tích HTTP status.

### 8.2. Wagon và plugin resolution

Ví dụ Maven wagon:

~~~xml
<build>
  <extensions>
    <extension>
      <groupId>com.google.cloud.artifactregistry</groupId>
      <artifactId>artifactregistry-maven-wagon</artifactId>
      <version>2.2.5</version>
    </extension>
  </extensions>
</build>
~~~

Nếu project tham chiếu **parent POM private** hoặc cần resolve **plugin dependencies** từ Artifact Registry trước khi Maven đọc POM dự án, sử dụng core extension `.mvn/extensions.xml`:

~~~xml
<extensions xmlns="http://maven.apache.org/EXTENSIONS/1.0.0"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://maven.apache.org/EXTENSIONS/1.0.0
            http://maven.apache.org/xsd/core-extensions-1.0.0.xsd">
  <extension>
    <groupId>com.google.cloud.artifactregistry</groupId>
    <artifactId>artifactregistry-maven-wagon</artifactId>
    <version>2.2.5</version>
  </extension>
</extensions>
~~~

Core extension được nạp sớm, nên Maven có thể đọc parent POM từ `artifactregistry://`. Không cần thêm core extension cho mọi project đơn giản; chọn đúng một cách quản trị phù hợp để tránh cấu hình trùng lặp không cần thiết.

### 8.3. Tránh JSON service account keys dài hạn

Google Cloud có cơ chế tương thích cho công cụ chỉ hỗ trợ username/password qua HTTPS và key dạng JSON, nhưng **khóa dài hạn có rủi ro lộ**. Đừng đưa chúng vào `pom.xml`, `settings.xml` được commit, code, Dockerfile hoặc CI log. Nếu bất khả kháng, lưu ở hệ quản lý secret được duyệt với rotation/revocation và quyền tối thiểu. **Credential helper + short-lived identity** là mặc định được ưu tiên.

## 9. Bước 4 — Build và publish thư viện

Trong thư mục `order-common`:

~~~bash
java -version
mvn -version

# Biên dịch, test và đóng gói.
mvn clean verify

# Publish qua distributionManagement vào repository Maven.
mvn deploy
~~~

Với `1.0.0-SNAPSHOT` và policy `None`, Maven publish các tệp JAR/POM cùng metadata phiên bản theo cơ chế Maven. Đừng dùng `-DskipTests` để che lỗi build; chỉ bỏ qua test khi pipeline đã có tầng kiểm thử khác được phê duyệt.

Tệp được tạo tại máy build:

~~~text
target/order-common-1.0.0-SNAPSHOT.jar
~~~

Trong repository, Maven 3 có thể dùng **timestamped unique snapshot filenames**. Lệnh `mvn deploy` không nhất thiết để lại file y hệt tên trong máy local tại đường dẫn lưu trữ server.

### 9.1. Kiểm tra package và versions

~~~bash
gcloud artifacts packages list \
  --project=PROJECT_ID \
  --repository=java-libs-lab \
  --location=asia-southeast1

gcloud artifacts versions list \
  --project=PROJECT_ID \
  --repository=java-libs-lab \
  --location=asia-southeast1 \
  --package=com.example.platform:order-common
~~~

Kỳ vọng có package dạng `groupId:artifactId` và ít nhất một version ứng với artifact đã publish. Có thể dùng Console để xem versions/files. Nếu không thấy gì, xác nhận đúng project/location/repository và IAM trước khi publish lần nữa.

### 9.2. Chuyển sang phát hành release

Khi có phiên bản đã được duyệt, đổi POM:

~~~xml
<groupId>com.example.platform</groupId>
<artifactId>order-common</artifactId>
<version>1.0.0</version>
~~~

Nếu production có kho tách biệt, `distributionManagement/repository` phải trỏ **release standard repo**, còn `snapshotRepository` trỏ **snapshot standard repo**. Lab dùng `java-libs-lab` có policy None nên cả hai URL cùng một nơi.

**Không được giả định đổi tên JAR thành `1.0.0` là đủ**. POM, GAV, build metadata và consumer dependency phải khớp. Không tái sử dụng version release cho một nội dung mới, để tránh cache/provenance mâu thuẫn.

### 9.3. Publish artifact ngoại sinh với deploy-file

Nếu một JAR đã được build ngoài Maven, và có POM phù hợp:

~~~bash
mvn deploy:deploy-file \
  -Durl=artifactregistry://asia-southeast1-maven.pkg.dev/PROJECT_ID/java-libs-lab \
  -DrepositoryId=artifact-registry \
  -Dfile=dist/order-common-1.0.0.jar \
  -DpomFile=dist/pom.xml
~~~

Yêu cầu file đã tồn tại, Maven wagon được nạp, metadata POM đúng và principal có Writer. Ví dụ không khuyến khích publish “JAR không rõ nguồn” chỉ bằng cách tạo một POM giả để vượt kiểm tra.

## 10. Bước 5 — Consumer tải dependency nội bộ

Giả sử `orders-api` cần `order-common:1.0.0-SNAPSHOT`. Thêm vào `pom.xml` của consumer:

~~~xml
<repositories>
  <repository>
    <id>company-maven</id>
    <url>artifactregistry://asia-southeast1-maven.pkg.dev/PROJECT_ID/java-libs-lab</url>
    <releases><enabled>true</enabled></releases>
    <snapshots><enabled>true</enabled></snapshots>
  </repository>
</repositories>

<dependencies>
  <dependency>
    <groupId>com.example.platform</groupId>
    <artifactId>order-common</artifactId>
    <version>1.0.0-SNAPSHOT</version>
  </dependency>
</dependencies>
~~~

Consumer cũng cần **Artifact Registry Maven wagon** trong `<build><extensions>` hoặc `.mvn/extensions.xml`, cùng **Reader IAM**. `distributionManagement` không bắt buộc nếu consumer chỉ tải dependency.

Mã sử dụng:

~~~java
package com.example.orders;

import com.example.platform.OrderCode;

public class OrdersApp {
    public static void main(String[] args) {
        System.out.println(OrderCode.normalize(" od-123 "));
    }
}
~~~

Thử:

~~~bash
mvn -U clean verify
mvn dependency:tree
~~~

`-U` yêu cầu Maven kiểm tra cập nhật snapshots/metadata, hữu ích nếu phiên bản snapshot mới chưa được tải. Production nên dùng version release **pin rõ** và kiểm soát dependency graph.

### 10.1. Tại sao build trên laptop được nhưng CI không được?

Maven giữ cache trong `~/.m2/repository`. Một developer có artifact đã tải từ trước nên vẫn compile thành công dù CI mới khởi tạo không có quyền Reader. Tránh suy từ “máy tôi chạy được” rằng repository/IAM đều đúng.

Kiểm tra build trên môi trường mới/CI, xác minh chính xác dependency GAV và danh tính thực. **Đừng xóa toàn bộ cache ở máy dùng chung** nếu chỉ đang chẩn đoán một artifact.

### 10.2. Nếu POM có private parent

Maven cần resolve `<parent>` từ sớm trước khi đọc phần extension trong POM con. Nếu lỗi:

~~~text
Non-resolvable parent POM
Unsupported repository transport artifactregistry
~~~

Hãy kiểm tra **core extension trong `.mvn/extensions.xml`**, repository URL, Reader IAM và GAV của parent. Không đưa parent POM private lên Maven Central công khai chỉ để build thành công.

## 11. Publish/consume Maven artifacts bằng Gradle

Artifact Registry hỗ trợ Maven-format packages được tạo từ **Gradle Maven Publish** và plugin xác thực của Google Cloud.

### 11.1. Ví dụ `build.gradle` Groovy DSL

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
    id 'com.google.cloud.artifactregistry.gradle-plugin' version '2.2.5'
}

group = 'com.example.platform'
version = '1.0.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
    maven {
        url "artifactregistry://asia-southeast1-maven.pkg.dev/PROJECT_ID/java-libs-lab"
    }
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
    repositories {
        maven {
            url "artifactregistry://asia-southeast1-maven.pkg.dev/PROJECT_ID/java-libs-lab"
        }
    }
}
~~~

Thao tác minh họa:

~~~bash
./gradlew clean test
./gradlew publish
~~~

Trong Windows PowerShell dùng wrapper tương ứng `gradlew.bat publish` nếu dự án có wrapper. Không giả định Gradle được cài hoặc wrapper tồn tại nếu chưa tạo dự án.

### 11.2. Những điểm khác Maven

- `repositories` của Gradle để **đọc dependencies**.
- `publishing.repositories` để **upload artifacts**.
- `publications` xác định nội dung xuất bản từ `components.java`; thiếu publication có thể khiến lệnh publish không gửi JAR/POM mong muốn.
- Plugin `com.google.cloud.artifactregistry.gradle-plugin` hỗ trợ protocol/auth.
- Nếu dùng private plugin trong giai đoạn cấu hình, `settings.gradle` hoặc `init.gradle` có thể cần nạp plugin/helper khác so với `build.gradle`.

**Không cho Maven và Gradle cùng tự ý publish lên cùng GAV release**. Chỉ định một pipeline sở hữu version và metadata.

## 12. CI/CD và IAM service account

### 12.1. Luồng build và deploy

~~~mermaid
flowchart LR
    Git["Git commit + PR review"] --> CI["Cloud Build / CI<br/>test + package"]
    CI -->|"Writer"| Maven["Maven standard<br/>order-common"]
    Maven -->|"Reader"| App["orders-api build"]
    App --> Image["Build OCI image"]
    Image --> Docker["Docker repository"]
    Docker --> Run["Cloud Run / GKE"]
    App --> VM["Compute Engine<br/>nếu chạy JAR"]
~~~

**Tách quyền theo giai đoạn**:

| Giai đoạn | Identity | Quyền |
|---|---|---|
| Build và publish thư viện | CI publisher SA | Writer trên Maven standard repo |
| Build consumer | CI consumer SA | Reader trên Maven/remote/virtual repos cần dùng |
| Build/push container | Image builder SA | Quyền push trên Docker repository |
| Deploy Cloud Run/GKE | Deployer SA | Quyền deploy/runtime tương ứng |
| Vận hành ứng dụng | Runtime SA | Chỉ quyền dịch vụ dữ liệu, **không cần Maven Writer** |

**Cloud Build service account có thể khác nhau theo project và cấu hình trigger**. Không hardcode account mặc định. Xác định account chạy build thật, rồi cấp quyền tối thiểu trên repository chứa artifact, kể cả khi build nằm ở project khác.

### 12.2. Ví dụ cấp Writer trên đúng repository

Lệnh này **thay đổi IAM** và chỉ chạy khi được phê duyệt:

~~~bash
gcloud artifacts repositories add-iam-policy-binding java-libs-lab \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --member=serviceAccount:ci-publisher@PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/artifactregistry.writer
~~~

Service account trên là **placeholder**, phải tồn tại thật. Đọc policy sau thay đổi:

~~~bash
gcloud artifacts repositories get-iam-policy java-libs-lab \
  --project=PROJECT_ID \
  --location=asia-southeast1
~~~

CI ở một project khác không tự có quyền trên repository project. Người sở hữu Artifact Registry quyết định IAM scope.

### 12.3. Phát hành có thể audit và rollback

Một release pipeline có thể gồm:

1. Pull request, code review và protected branch.
2. CI với JDK/Maven/Gradle version được chuẩn hóa.
3. Unit/integration tests, lint, SCA/dependency/license review.
4. Tạo SBOM hoặc provenance metadata khi được yêu cầu.
5. Publish snapshots từ nhánh thử nghiệm vào snapshot repo.
6. Chốt release từ commit/tag đã được phê duyệt, publish đúng release repository.
7. Ghi **GAV, source SHA, build ID, checksum** và người phê duyệt.
8. Consumer pin version, chạy compatibility tests rồi build container image nếu cần.
9. Triển khai trên Cloud Run/GKE/Compute Engine với health checks, monitoring và rollback.

**Maven deploy thành công không có nghĩa artifact đã qua kiểm tra bảo mật**. Registry không thay CI security gates. Đừng tuyên bố Maven package tự động được vulnerability scanning như Docker image; phạm vi hỗ trợ của từng tính năng Artifact Analysis phải kiểm tra riêng.

## 13. Remote Maven Central và virtual repository

### 13.1. Remote cache giải quyết việc gì?

Remote repository có thể sử dụng Maven Central làm upstream. Khi yêu cầu một version lần đầu, Artifact Registry tải và cache artifact từ upstream; những lần sau có thể trả từ cache. Lợi ích:

- Endpoint truy cập dependency do doanh nghiệp quản lý.
- Dễ đặt policy truy cập, quan sát và chuẩn hóa cấu hình consumer.
- Giảm một số phụ thuộc vào mạng bên ngoài khi artifact đã cache.

**Một package được cache không tự được “chứng nhận an toàn”**. Vẫn cần dependency review và cập nhật theo CVE/advisory.

### 13.2. Virtual làm gì?

Virtual repository cung cấp một endpoint đọc để truy cập nhiều standard/remote upstream. Khi cùng GAV có ở nhiều nơi, **upstream priority** ảnh hưởng nguồn được chọn. Nếu tên package private bị đăng lên public repository với cùng version, thiết kế ưu tiên sai có thể gây **dependency confusion**.

Checklist:

1. Dùng namespace nội bộ được quản lý rõ.
2. Đặt thứ tự upstream để package nội bộ được ưu tiên phù hợp.
3. Chỉ cho quản trị viên thay đổi virtual upstream/priority.
4. Kiểm thử dependency resolution và khóa version.
5. Không dùng virtual repository như đích publish các artifact nội bộ.

### 13.3. Maven Central Super POM

Khi muốn Maven dùng remote Artifact Registry thay cho Maven Central mặc định, hướng dẫn Google Cloud đưa ví dụ cấu hình repository id **`central`** để override URL kế thừa từ Maven Super POM. Nếu không, Maven có thể tiếp tục tải trực tiếp từ Maven Central dù có remote proxy.

Với build plugins, còn có **`<pluginRepositories>`** và yêu cầu nạp wagon sớm. Không chỉ chỉnh `<repositories>` rồi suy tất cả plugin dependencies cũng đi qua virtual endpoint.

## 14. Quản lý version và nguồn gốc artifact

### 14.1. Quy tắc phát hành

| Quy tắc | Vì sao |
|---|---|
| Không tái sử dụng version release cho nội dung mới | Tránh cache/provenance mâu thuẫn |
| Chỉ build từ commit/tag được kiểm soát | Truy vết được artifact |
| Pin dependency/plug-in versions | Tăng khả năng tái lập |
| Không deploy SNAPSHOT tràn lan vào production | Version có thể trôi qua builds |
| Lưu phiên bản còn phục vụ rollback | Tránh tình huống cleanup phá quy trình ứng cứu |
| Quản trị cả transitive dependencies | Một thư viện có thể mang nhiều thư viện khác |
| Có release notes và compatibility tests | Hạn chế breaking changes |
| Bảo vệ quyền Writer | Tránh upload artifact trái phép |

### 14.2. Kịch bản lỗi do version không nhất quán

Giả sử `order-common:1.0.0` được phát hành rồi đội dự án lại thay JAR mà không tăng version. Một consumer có bản cũ trong `~/.m2`, một CI mới nhận bản khác. Cả hai nghĩ đang dùng cùng version nhưng behavior khác nhau. Điều tra sự cố rất khó.

Giải pháp: **phát hành version mới**, không chỉnh nội dung release đã công bố, kiểm tra checksum/GAV và ghi release provenance. Nếu cần rollback ứng dụng, pin về **version cũ** đã được lưu và kiểm thử.

### 14.3. Maven local cache và reproducibility

Maven cache giúp build nhanh hơn nhưng có thể che lỗi IAM/cấu hình:

- Build offline thành công không chứng minh registry đang hoạt động.
- Snapshot cũ trong cache có thể khác snapshot mới.
- Lỗi tải artifact trước đó có thể được Maven cache, cần kiểm tra refresh `-U`.
- Dùng builds sạch có kiểm soát để xác nhận môi trường CI thực sự resolve package đúng nguồn.

Không xóa toàn bộ local Maven repository trên máy dùng chung khi chưa xác định tác động.

## 15. Bảo mật supply chain, audit và quyền truy cập

Artifact Registry là **nơi lưu trữ**, không phải thay thế toàn bộ quy trình tin cậy phần mềm.

- **Source trust:** kiểm tra PR, branch protection, review.
- **Build trust:** CI dùng container/toolchain tin cậy, không chứa long-lived secret.
- **Dependency trust:** pin versions, SCA, license checks, kiểm tra nguồn upstream.
- **Artifact identity:** ghi GAV, checksums, provenance/SBOM khi cần.
- **Publication control:** Writer chỉ dành cho build được phê duyệt.
- **Consumption control:** Reader scope phù hợp cho service và CI.
- **Deployment control:** image digest/version được phê duyệt, pipeline deployment riêng.
- **Auditing:** theo dõi IAM changes, package publish/delete và repository settings.

Không đưa thông tin nhạy cảm như customer data, credentials hoặc signing private keys vào JAR được publish; ngay cả private Maven repo cũng có thể có nhiều readers hơn dự kiến.

## 16. Quản trị chi phí và cleanup

### 16.1. Chi phí hình thành từ đâu?

| Nhóm | Ví dụ |
|---|---|
| Storage | JAR/POM, nhiều phiên bản snapshot/release |
| Download/network | Tải dependency từ location khác hoặc ra Internet |
| Remote cache | Các bản được cache từ Maven Central |
| CI compute | Build/test/package/dependency scanning |
| CMEK nếu dùng | Cloud KMS key/crypto operations |
| Logging/Monitoring | Audit log, metric và retention |

Dùng **Cloud Billing Reports** và **Artifact Registry pricing** để xem dữ liệu theo project/location/SKU. Không giả định repository rỗng và repository chứa hàng nghìn snapshot có chi phí giống nhau.

### 16.2. Cleanup policies

Với repository có nhiều versions, tổ chức có thể dùng **cleanup policies** (conditional delete, keep most recent, v.v.):

1. Liệt kê các version đang được consumers hoặc deployment sử dụng.
2. Thiết lập retention riêng cho snapshot và release.
3. Sử dụng **dry run** để xem tác động trước khi xóa.
4. Giữ lại những version cần rollback/audit.
5. Cân nhắc remote cache và các consumers đang dùng version cũ.
6. Rà lại kết quả sau policy chạy, cảnh báo nếu repository tăng bất thường.

**Xóa Maven package/version có thể không hoàn tác được**. Không tự động xóa mọi artifact quá 7 ngày trong một repository chứa release production.

### 16.3. Thu hồi tài nguyên lab

Nếu đã tự tạo repository `java-libs-lab` và xác minh không có consumer khác, lệnh xóa (có tác động, có thể mất dữ liệu) là:

~~~bash
gcloud artifacts repositories delete java-libs-lab \
  --project=PROJECT_ID \
  --location=asia-southeast1
~~~

Không chạy lệnh nếu repository thực sự đang được shared hoặc chứa package cần giữ. Sau đó xác nhận qua list/read, kiểm tra phí storage/CI/network và tài nguyên IAM, build artifacts khác nếu đã tạo.

## 17. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `401 Unauthorized` | Token thiếu/hết hạn, helper chưa hoạt động | ADC, wagon/plugin, refresh credentials |
| `403 Permission Denied` | Đúng identity nhưng thiếu Reader/Writer | IAM repository, principal thực tế |
| `404 Not Found` | Sai project/location/repo/GAV hoặc visibility | `repositories describe`, `packages/versions list` |
| `mvn deploy` báo thiếu repository | Chỉ có `<repositories>`, thiếu `distributionManagement` | Đặt đúng repository/snapshotRepository |
| `Unsupported transport protocol artifactregistry` | Maven wagon không được nạp | `build extensions` hoặc core extension |
| `Non-resolvable parent POM` | Parent cần tải trước khi nạp POM extension | `.mvn/extensions.xml` |
| Snapshot publish bị từ chối | Version policy Release | Dùng snapshot repo đúng |
| Release publish bị từ chối | Version policy Snapshot | Dùng release repo đúng |
| Gradle publish không có JAR/POM | Thiếu Maven publication | Kiểm tra `publishing.publications` |
| Dev build được, CI fail | Credentials/cache khác nhau | Xem CI service account và clean build |
| Ứng dụng không thấy version mới | Maven local cache/update policy | `mvn -U`, phiên bản và metadata |
| Dependency tải trực tiếp Maven Central | Remote/virtual config chưa override central | Cấu hình `central` và pluginRepositories |
| CI không truy cập endpoint | DNS/TLS/proxy/egress bị hạn chế | Kiểm tra HTTPS network và cert trust |
| Package không ở repository dự kiến | POM URL sai hoặc project default sai | Đọc `distributionManagement`/CLI flags |
| Cleanup làm mất release cũ | Retention quá ngắn, chưa kiểm tra consumers | Dry run và quy trình rollback |
| Maven repo không nhận Docker image | Mỗi repository có một format | Tạo Docker repo riêng |

### 17.1. Quy trình điều tra một lỗi `403`

1. Xác định yêu cầu là **publish** hay **download**.
2. Ghi lại project, location, repository và GAV thực tế.
3. Xác định identity mà Maven/Gradle dùng qua ADC/CI service account, không suy từ Git username.
4. Kiểm tra IAM trên **repository** và quyền kế thừa: Writer cho publish, Reader cho consume.
5. Kiểm tra wagon/Gradle plugin, credentials và cấu hình network.
6. Đối chiếu version policy, package metadata và lỗi chi tiết.
7. Thử lại trên sandbox; sửa đúng quyền thiếu thay vì cấp `Owner` hoặc `Artifact Registry Admin` rộng.

### 17.2. Auth lỗi khác network lỗi thế nào?

- **Timeout/DNS/TLS handshake:** tìm vấn đề kết nối, proxy, CA certificates, network/egress.
- **401/403:** thường xảy ra khi endpoint đã nhận yêu cầu nhưng auth/policy từ chối.
- **404:** xác định lại resource name, GAV, URL và visibility, đừng tự suy package không tồn tại.
- **Conflict/version validation:** xem chính sách snapshot/release hoặc phiên bản đã xuất bản.

**Không bao giờ đăng JSON key, bearer token, `settings.xml` có password hoặc secret của CI lên ticket công khai.**

## 18. Case study: RetailOne quản lý thư viện Java dùng chung

**Bối cảnh:** `RetailOne` có thư viện nội bộ `com.retailone.platform:order-common` dùng cho hai dịch vụ:

- `orders-api` chạy trên Cloud Run.
- `billing-worker` chạy trên Compute Engine.
- Build pipelines nằm trong project CI riêng.
- Artifacts lưu trong project `retail-build-prod`.
- Production phải dùng version release, có khả năng rollback và kiểm toán.

### 18.1. Thiết kế đề xuất

~~~mermaid
flowchart TD
    Source["Git: order-common"]
    Build["CI verify, SCA, versioning"]
    Snap["Maven standard: snapshot"]
    Release["Maven standard: release"]
    Virtual["Virtual: java-dependencies"]
    Remote["Remote: Maven Central"]
    C1["orders-api build"]
    C2["billing-worker build"]
    Container["Docker repository"]
    CloudRun["Cloud Run"]
    VM["Compute Engine"]
    Source --> Build
    Build --> Snap
    Build --> Release
    Release --> Virtual
    Remote --> Virtual
    Virtual --> C1
    Virtual --> C2
    C1 --> Container
    Container --> CloudRun
    C2 --> VM
~~~

Quy tắc:

1. Snapshot dùng cho tích hợp và thử nghiệm.
2. Release chỉ được publish qua CI SA có Writer trên release repository.
3. Consumers chỉ có Reader qua standard/virtual repository cần thiết.
4. CI lưu GAV, source commit, checksum, dependency graph và test results.
5. `orders-api` build container image rồi push sang Docker repository riêng.
6. Cloud Run runtime không cần Writer lên Maven repo; Compute Engine không cần lưu private key của publisher.
7. Cleanup snapshots theo hạn dùng; giữ release versions đang được triển khai/rollback.

### 18.2. Sự cố đổi interface của thư viện

Giả sử `order-common:1.1.0` xóa một public method mà Billing Worker đang dùng. Nếu đội publish lại dưới GAV `1.0.0`, một số builds dùng cache cũ, một số builds nhận code mới; CI khó tái lập. Cách đúng là **phát hành version mới**, ghi breaking changes và chạy compatibility tests cho cả consumers.

### 18.3. Bằng chứng cho một release hợp lệ

| Câu hỏi | Cần kiểm tra |
|---|---|
| Source commit nào? | SHA/tag và build provenance |
| Tests đã pass? | CI report |
| Artifact có đúng GAV? | POM + repository version |
| Người nào có quyền Writer? | IAM policy ở repo |
| Consumer lấy đúng release? | Maven dependency tree và build log |
| Image triển khai đúng? | Docker digest + revision |
| Có thể rollback? | Version cũ còn, đã test restore/redeploy |
| Chi phí phù hợp? | Billing + cleanup dry run |

## 19. Bài tập thực hành và tự đánh giá

### Bài 1 — Đặt đúng artifact

Bạn có hai output: `order-common-1.0.0.jar` (thư viện Java) và OCI image `orders-api:1.0.0` (để chạy Cloud Run). **Nên lưu vào repository format nào?** Giải thích vì sao không đặt cả hai vào cùng repo.

### Bài 2 — Maven GAV

Project có:

~~~xml
<groupId>com.example.payments</groupId>
<artifactId>risk-sdk</artifactId>
<version>2.3.1</version>
<packaging>jar</packaging>
~~~

**Hãy viết** GAV, ví dụ `<dependency>` mà consumer cần và đường dẫn layout Maven chuẩn của JAR.

### Bài 3 — Snapshot bị từ chối

Developer publish `1.4.0-SNAPSHOT` vào repository `Release` và nhận lỗi. Vì sao? Có nên bỏ suffix `-SNAPSHOT` chỉ để vượt lỗi dù chưa qua kiểm thử/phê duyệt không?

### Bài 4 — CI nhận `403`

Developer có quyền upload trên laptop, Cloud Build publisher báo 403. Cần xác định **service account thực sự chạy CI**, ADC, quyền Writer và scope repository nào? Vì sao không nên dùng JSON key trong `pom.xml`?

### Bài 5 — Parent POM trong private Maven repo

Consumer dùng `<parent>` trỏ đến `com.example.platform:company-parent:3.0.0`, wagon nằm ở `<build><extensions>` nhưng Maven fail khi đọc parent. Thiếu gì? Vì sao `.mvn/extensions.xml` có thể giúp?

### Bài 6 — Một endpoint cho internal + public dependencies

Doanh nghiệp muốn CI truy cập Maven Central qua cache và thư viện nội bộ qua một endpoint. Hãy vẽ **standard + remote + virtual**, mô tả upstream priority và rủi ro dependency confusion.

### Bài 7 — Cleanup không phá rollback

Kho có hàng nghìn snapshots, team dự định xóa tất cả artifacts quá 7 ngày. Những version release nào có thể phải giữ? Hãy viết chính sách cleanup có **dry run** và cơ chế kiểm tra consumers.

### Bài 8 — Điều tra consumer không thấy package

Đội đã publish `com.example.platform:order-common:1.0.0` nhưng một CI mới báo missing dependency. Hãy liệt kê thứ tự kiểm tra: **GAV → project/location/repo → package/versions → Reader IAM → repositories → wagon/core extension → Maven cache → network**.

### Bài 9 — Kiểm soát supply chain

Một virtual repository trả về public package trùng GAV với thư viện nội bộ. Hãy chỉ ra rủi ro và đề xuất thay đổi về namespace, upstream priority, permissions và release provenance.

## 20. Checklist vận hành

- [ ] Đã phân biệt Maven package với OCI image và chọn đúng repository format.
- [ ] Đã chọn location, mode, version policy, IAM owner và naming convention phù hợp.
- [ ] Đã định nghĩa GAV/packaging/POM hợp lệ và version chiến lược.
- [ ] Đã cấp **Reader** cho consumer, **Writer** cho CI publisher, Admin/RepoAdmin chỉ cho người cần.
- [ ] Đã xác minh ADC/service account Maven/Gradle sử dụng.
- [ ] Không lưu service account JSON key/token trong mã nguồn, image hoặc build logs.
- [ ] Publisher có `distributionManagement` đúng đích; consumer có `repositories` phù hợp.
- [ ] Maven wagon hoặc Gradle helper được nạp, core extension có sẵn nếu cần resolve parent/plugins.
- [ ] Đã chạy `mvn verify` hoặc `gradle test` trước publish.
- [ ] Đã xác nhận package/versions bằng `gcloud artifacts packages/versions list`.
- [ ] Consumer khác có thể tải đúng version và build độc lập.
- [ ] Đã tách snapshot/release và không tái sử dụng version release cho nội dung mới.
- [ ] Remote/virtual upstream priorities được kiểm soát nếu dùng proxy dependencies.
- [ ] Đã lưu commit SHA, build ID, checksum và test results để audit/rollback.
- [ ] Đã có dependency scan/SBOM và không xem registry là công cụ duy nhất bảo đảm an toàn.
- [ ] Cleanup policies được dry run, giữ đủ bản phục vụ rollback/audit.
- [ ] Đã theo dõi truy cập, tăng trưởng dung lượng, thay đổi IAM và chi phí.
- [ ] Nếu triển khai Cloud Run/GKE, pipeline tạo OCI image và push Docker repository riêng.

## 21. Tài liệu tham khảo chính thức

Các phiên bản plugin, cách xác thực và tính năng repository có thể thay đổi. Trước khi triển khai thật, kiểm tra:

- [Artifact Registry — Get started with Java packages](https://docs.cloud.google.com/artifact-registry/docs/java)
- [Quickstart: Store Java packages](https://docs.cloud.google.com/artifact-registry/docs/java/store-java)
- [Configure authentication for Maven and Gradle](https://docs.cloud.google.com/artifact-registry/docs/java/authentication)
- [Manage Java packages](https://docs.cloud.google.com/artifact-registry/docs/java/manage-packages)
- [Create standard repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/create-repos)
- [Remote repository overview](https://docs.cloud.google.com/artifact-registry/docs/repositories/remote-overview)
- [Virtual repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/virtual-repo)
- [Artifact Registry access control](https://docs.cloud.google.com/artifact-registry/docs/access-control)
- [Repository cleanup policies](https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy)
- [Integrate Cloud Build](https://docs.cloud.google.com/artifact-registry/docs/configure-cloud-build)
- [Maven POM reference](https://maven.apache.org/pom.html)
- [Maven settings reference](https://maven.apache.org/settings.html)
- [Gradle Maven Publish plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing)

**Điểm cần nhớ:** Lưu Maven artifacts trong Artifact Registry giúp các dự án Java có **thư viện được version hóa, chia sẻ theo quyền và phát hành có thể kiểm toán**. Bắt đầu với standard Maven repository, cấu hình đúng **đường publish và đường dependency**, dùng **credential helper + IAM tối thiểu**, sau đó xác minh bằng một consumer độc lập. Khi mở rộng, cần tách snapshot/release, quản trị remote/virtual upstream, lưu build provenance, kiểm soát cleanup và chi phí. Với ứng dụng chạy trên Cloud Run/GKE, Maven artifact là **đầu vào build**, còn **OCI image** cần được lưu trong Docker repository riêng.
