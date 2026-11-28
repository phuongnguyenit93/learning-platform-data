# Quản lý BOM và version module

## 1. Bối cảnh: tại sao version lại ảnh hưởng đến tính mô-đun?

Trong một ứng dụng Spring Boot sử dụng **Spring Modulith**, chúng ta tổ chức mã nguồn thành các *application module*, mô tả ranh giới và phụ thuộc giữa các module, phát sự kiện để giảm coupling, đồng thời quan sát những tương tác thực tế qua Spring Boot Actuator, Micrometer metrics và tracing.

Một số vấn đề có vẻ là lỗi kiến trúc nhưng thực chất xuất phát từ **lệch phiên bản thư viện**:

- Thư viện Spring Modulith quan sát module đòi hỏi API Micrometer hoặc Spring Framework không có trong bộ Spring Boot đang chạy.
- Test module graph hoạt động tại thời điểm build, nhưng production thiếu dependency runtime để công bố endpoint Modulith Actuator.
- Event publication registry truy cập bảng cũ sau khi nâng cấp nhưng schema của implementation mới khác trước.
- Một module được build với bộ dependency mới, còn module khác kéo bản cũ qua transitive dependencies.
- Trace không xuất hiện vì thiếu bridge/exporter hoặc vì phiên bản tracing và instrumentation không tương thích.
- Khi nâng cấp Spring Modulith, semantics của *event publication completion* có thể đổi, dẫn đến khác biệt về transaction và cách đọc tình trạng xử lý.

Bài học **Quản lý BOM và version module** thuộc chương **Phiên bản**, nằm trong module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Nội dung giải thích cách chọn Spring Boot và Spring Modulith tương thích, quản lý thư viện cho module graph, Actuator, event metrics, tracing và context propagation, sau đó kiểm chứng kiến trúc cũng như hành vi ứng dụng khi vận hành.

### Kết quả học tập

Sau bài này, người học có thể:

1. Giải thích **BOM (Bill of Materials)** và phân biệt version của build artifact, framework, dependency và application module.
2. Chọn đúng **release train Spring Modulith** theo nhánh Spring Boot đang dùng.
3. Khai báo Spring Boot BOM và Spring Modulith BOM trên **Maven** hoặc **Gradle**, không gắn version riêng cho mỗi Modulith artifact.
4. Tách dependency compile/runtime/test/docs và phân biệt công cụ module graph với tooling observability.
5. Kiểm tra phiên bản **thực sự được resolve**, truy nguyên transitive dependency và quản lý thay đổi có kiểm soát.
6. Thiết kế quy trình nâng cấp bao phủ startup, module verification, documentation, Actuator, event publications, metrics và tracing.

> Ví dụ phiên bản trong bài được kiểm tra theo tài liệu Spring vào **27/11/2026**: Spring Modulith **2.2.0** đã phát hành GA ngày 19/11/2026 và được xây dựng với Spring Boot **4.2** / Spring Framework **7.1**. Ví dụ dưới đây dùng **Spring Boot 4.2.0 + Spring Modulith 2.2.0** làm một cặp nhất quán. Với dự án vẫn ở Spring Boot 3.5, nên xem nhánh Spring Modulith 1.4.x tương ứng trước khi chọn phiên bản; không sao chép máy móc cấu hình 2.2 vào ứng dụng Boot 3.

## 2. Phân biệt bốn khái niệm “version”

Từ “version module” có nhiều ý nghĩa khác nhau trong hệ sinh thái Java:

| Khái niệm | Ví dụ | Ai quản lý? | Tác động |
| --- | --- | --- | --- |
| Phiên bản Spring Boot | 4.2.0 | Parent POM / Boot Gradle plugin / Boot BOM | Spring Framework, Spring Data, Micrometer, thư viện được Boot kiểm thử |
| Phiên bản Spring Modulith | 2.2.0 | `spring-modulith-bom` | API/core/docs/actuator/events/observability của Modulith |
| Phiên bản artifact ứng dụng | `shop-app:1.8.0` | `project.version`, POM, CI/CD | Artifact hoặc container image được phát hành |
| Phiên bản API/domain event của module | `OrderPlacedV2`, `orders-api:2.0` nếu tách JAR | Hợp đồng ứng dụng do nhóm phát triển kiểm soát | Tương thích với listener, dữ liệu đã lưu, hệ thống tích hợp |

**Spring Modulith application module** mặc định là ranh giới kiến trúc phát hiện qua package trong cùng ứng dụng. Nó **không bắt buộc** là một Maven/Gradle subproject và **không tự có một số phiên bản độc lập** chỉ vì là application module.

Ví dụ package:

~~~text
com.example.shop
├── ShopApplication.java
├── orders                <-- application module
│   ├── OrderPlaced.java
│   └── internal/...
├── inventory             <-- application module
│   └── internal/...
└── shipping              <-- application module
    └── internal/...
~~~

Tất cả các package trên có thể cùng nằm trong artifact `shop-app:1.8.0`, cùng một classpath và một bộ Spring Modulith runtime. Nếu tách thành nhiều Gradle/Maven module, đó là quyết định **tổ chức build và phân phối artifact**, không phải điều kiện bắt buộc của Spring Modulith.

## 3. BOM làm gì và không làm gì?

**BOM (Bill of Materials)** là một POM khai báo tập phiên bản thư viện được quản lý. Khi dự án import BOM, dependency phù hợp có thể được khai báo **không cần viết version ngay trên dependency**.

Ví dụ nguyên tắc:

~~~text
Spring Boot dependency management
 ├── Spring Framework
 ├── Spring Data
 ├── Micrometer / Tracing
 ├── Jackson và các thư viện khác
 └── Spring Boot starters

Spring Modulith BOM
 ├── spring-modulith-starter-core
 ├── spring-modulith-starter-insight
 ├── spring-modulith-actuator
 ├── spring-modulith-observability-api/core
 ├── spring-modulith-starter-jdbc / starter-jpa
 ├── spring-modulith-starter-test
 └── spring-modulith-docs
~~~

Hai BOM giải quyết **hai phạm vi**: Boot quản lý nền tảng Spring/third-party, Modulith giữ các artifact Modulith đồng bộ trong một release train.

### BOM không phải là một dependency runtime

Khi import `spring-modulith-bom`, chúng ta **chưa thêm** Module Actuator, documentation generator hoặc event registry vào ứng dụng. Muốn dùng một tính năng, vẫn phải khai báo dependency artifact tương ứng.

BOM cũng **không**:

- Tự ép mọi dependency về đúng version trong mọi công cụ và mọi tình huống.
- Tự tạo bảng database hoặc migration cho event publication registry.
- Bảo đảm code cũ tương thích API khi nâng cấp major version.
- Chứng minh hai Spring Boot/Spring Modulith release train tương thích với nhau.
- Tự sinh module graph, mở endpoint Actuator hoặc cấu hình OTLP exporter.

Sau khi import BOM, vẫn cần xem **dependency resolution** để biết phiên bản thực tế. Riêng Gradle native `platform(...)` thường dùng version constraints có thể được điều chỉnh bởi dependency graph; `enforcedPlatform(...)` ép chặt hơn và có tác động đến các consumer nếu xuất bản thư viện.

## 4. Chọn cặp Spring Boot và Spring Modulith

Trước khi sửa POM/Gradle, xác định phiên bản Spring Boot hiện tại và nhánh Modulith mà tài liệu chính thức xác nhận tương thích.

| Nhánh tham khảo | Nền tảng tương ứng | Khi nào cân nhắc? |
| --- | --- | --- |
| Spring Modulith **1.4.x** | Được biên dịch với **Spring Boot 3.5**; tài liệu nhánh 1.4 còn liệt kê kiểm thử với các dòng Boot 3.x | Dự án duy trì Spring Boot 3.x |
| Spring Modulith **2.0.x** | Thế hệ chuyển sang **Spring Boot 4.0**, Spring Framework 7 | Dự án ở Boot 4.0 và chưa nâng cao hơn |
| Spring Modulith **2.1.x** | Thế hệ Spring Boot 4, phát hành sau 2.0; xác nhận ma trận release phù hợp | Dự án đang theo release train 2.1 |
| Spring Modulith **2.2.0** | Bản GA 19/11/2026, build với **Spring Boot 4.2 / Framework 7.1** | Ví dụ mới trong bài; đánh giá migration trước khi nâng cấp |

Đây là thông tin định hướng theo **thời điểm bài viết**, không phải phép ánh xạ đảm bảo tất cả phiên bản patch đều tương thích. Với bất kỳ bản cụ thể nào, cần đọc compatibility matrix, release notes và dependency tree của chính bản đó.

**Quy tắc chọn version:**

1. Chốt Spring Boot release train được hỗ trợ và runtime JDK phù hợp.
2. Chọn một Spring Modulith release train tương thích.
3. Chốt **một** phiên bản Spring Modulith BOM cho toàn ứng dụng.
4. Để Boot quản lý các thư viện Spring Framework/Data/Micrometer được Boot hỗ trợ.
5. Tránh gắn version riêng vào `spring-modulith-docs`, `spring-modulith-observability-core` hoặc `spring-modulith-starter-test` khi đã có BOM.
6. Trước khi tăng major/minor, xem release notes, migration, thay đổi về events/observability và schema lưu bền.

> Không trộn trực tiếp Spring Modulith 1.x với 2.x trong cùng classpath. Nâng từ Boot 3/Modulith 1.x sang Boot 4/Modulith 2.x là một đợt thay đổi nền tảng có thể ảnh hưởng API, auto-configuration, serialization và integration tests.

## 5. Maven: khai báo một phiên bản Modulith ở một nơi

### 5.1. Ứng dụng dùng Spring Boot parent POM

Đoạn `pom.xml` dưới đây là **cấu hình mẫu dành cho Boot 4.2.0 / Modulith 2.2.0**, tập trung vào phần quản lý phiên bản:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.2.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>shop-modulith</artifactId>
    <version>1.8.0-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
        <spring-modulith.version>2.2.0</spring-modulith.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.modulith</groupId>
                <artifactId>spring-modulith-bom</artifactId>
                <version>${spring-modulith.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-starter-core</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-starter-insight</artifactId>
            <scope>runtime</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-docs</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Nếu ứng dụng không kế thừa Spring Boot parent, có thể import BOM `org.springframework.boot:spring-boot-dependencies` trong `dependencyManagement`, sau đó import Spring Modulith BOM cùng nhánh. Khi này phải tự quản lý plugin Maven cần thiết vì import BOM **không** có toàn bộ hành vi plugin management của Boot parent.

Trong ví dụ, `spring-modulith-starter-insight` cung cấp tích hợp **Modulith Actuator + Modulith observability** cùng starter Actuator cơ bản. Để xuất trace tới hệ thống ngoài (OTLP/Zipkin) vẫn cần tracing bridge/exporter và cấu hình pipeline phù hợp với Spring Boot version.

### 5.2. Vì sao đặt version ở properties?

Khi tăng `spring-modulith.version` từ `2.2.0` lên một bản patch tương thích, chỉ cần sửa **một chỗ** và chạy bộ xác minh. Nếu từng dependency chứa version riêng, cấu hình dễ rơi vào tình trạng:

~~~xml
<!-- Ví dụ SAI: Modulith artifacts bị lệch thế hệ -->
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-core</artifactId>
    <version>2.2.0</version>
</dependency>
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-docs</artifactId>
    <version>1.4.14</version>
    <scope>test</scope>
</dependency>
~~~

Bản `docs` có thể gọi API cũ trong `core` mới, gây `NoSuchMethodError`, `ClassNotFoundException` hoặc lỗi plugin/test. Đây là **một ví dụ về rủi ro**, không khẳng định cặp artifact cụ thể này nhất định lỗi theo cùng một cách.

### 5.3. Maven multi-module

Trong Maven reactor chứa nhiều module build:

~~~text
shop-parent/pom.xml
shop-parent/orders/pom.xml
shop-parent/shipping/pom.xml
shop-parent/application/pom.xml
~~~

Hãy đặt version Boot/Modulith và `dependencyManagement` ở **parent POM chung** mà các submodule thực sự kế thừa. Submodule chỉ khai báo artifact cần dùng và scope. Nếu một submodule không kế thừa parent, nó **không tự nhận BOM** chỉ vì nằm cạnh thư mục khác trong reactor.

Maven `dependencyManagement` của parent giúp các submodule đồng bộ, nhưng version của chính artifact `orders` hay `shipping` vẫn là quyết định về phát hành ứng dụng/library. Nếu một public API module được xuất bản thành JAR dùng ngoài ứng dụng, cần quản lý semantic versioning cho API đó riêng.

## 6. Gradle: hai cách import BOM, chọn một chiến lược

Spring Boot Gradle hỗ trợ hai đường chính: plugin `io.spring.dependency-management` hoặc Gradle native BOM support qua `platform(...)`. Có thể chọn **một** cách để quản lý dependency rõ ràng, nhất quán.

### 6.1. Cách A — dependency-management plugin

Ví dụ `build.gradle` (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.8.0-SNAPSHOT'

ext['springModulithVersion'] = '2.2.0'

dependencyManagement {
    imports {
        mavenBom "org.springframework.modulith:spring-modulith-bom:${springModulithVersion}"
    }
}

dependencies {
    implementation 'org.springframework.modulith:spring-modulith-starter-core'
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
    testImplementation 'org.springframework.modulith:spring-modulith-docs'
}
~~~

Khi áp dụng plugin dependency management cùng Spring Boot plugin, Boot BOM được import tự động theo phiên bản Boot plugin. `springModulithVersion` là **một** điểm điều chỉnh cho BOM Modulith. Ví dụ version plugin minh họa theo tài liệu Spring Boot 4.2; khi áp dụng vào build thực tế, xác nhận phiên bản Gradle/plugin được hỗ trợ.

### 6.2. Cách B — Gradle native `platform`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
}

group = 'com.example'
version = '1.8.0-SNAPSHOT'

def bootVersion = '4.2.0'
def modulithVersion = '2.2.0'

dependencies {
    implementation platform("org.springframework.boot:spring-boot-dependencies:${bootVersion}")
    implementation platform("org.springframework.modulith:spring-modulith-bom:${modulithVersion}")

    implementation 'org.springframework.modulith:spring-modulith-starter-core'
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    testImplementation platform("org.springframework.boot:spring-boot-dependencies:${bootVersion}")
    testImplementation platform("org.springframework.modulith:spring-modulith-bom:${modulithVersion}")
    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
    testImplementation 'org.springframework.modulith:spring-modulith-docs'
}
~~~

Ở biến thể này, Boot version xuất hiện trong plugin và BOM, vì vậy **phải tăng đồng bộ** khi nâng cấp. Có thể trích version vào `gradle.properties` hoặc version catalog để không phải nhập hai chỗ, nhưng phải hiểu rằng Gradle plugin version và platform version là **hai cơ chế cấu hình khác nhau**.

`platform` tạo **version constraints**, không nhất thiết khóa tuyệt đối các version trong mọi dependency graph. Khi có conflict, sử dụng:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath \
  --dependency org.springframework.modulith
~~~

để kiểm tra **selected version** và nguyên nhân lựa chọn. Chỉ dùng `enforcedPlatform` khi hiểu tác động: nó áp các ràng buộc mạnh hơn và có thể ảnh hưởng downstream consumers của library được publish.

### 6.3. Multi-project Gradle

Trong project có các subproject:

~~~text
settings.gradle
build.gradle
application/build.gradle
orders/build.gradle
shipping/build.gradle
~~~

Cần bảo đảm **từng subproject cần dùng thư viện** đều nhận được dependency management tương ứng (qua convention plugin chung hoặc khai báo `platform` trong configuration phù hợp). Chỉ đặt `platform` ở root project mà các subproject không sử dụng sẽ không tự quản lý phiên bản cho chúng.

Nếu `orders` và `shipping` chỉ là *application modules* được phát hiện qua package, **không cần** tách thành Gradle subproject vì lý do version; tổ chức build dựa trên nhu cầu thực tế.

## 7. Chọn artifact đúng mục đích và đúng scope

Spring Modulith là bộ thư viện theo tính năng; không phải tất cả artifact đều cần nằm trên production classpath.

| Nhu cầu | Artifact tiêu biểu | Scope thường dùng | Vì sao |
| --- | --- | --- | --- |
| Hạ tầng/application module runtime cơ bản | `spring-modulith-starter-core` | `implementation` / compile | API và hạ tầng nền |
| Module graph, verification trong test | Core API + `spring-modulith-starter-test` | Test | Kiểm tra ranh giới package và bootstrap module |
| Sinh tài liệu module graph / canvas | `spring-modulith-docs` | Test | `Documenter` thường chạy trong test/build |
| Expose graph module qua Actuator + observability | `spring-modulith-starter-insight` | Runtime | Tiện ích gộp Actuator và Modulith observation |
| Chỉ expose module Actuator | `spring-modulith-actuator` cùng Boot Actuator | Runtime | Dùng khi không muốn starter Insight |
| Chỉ instrument interaction | `spring-modulith-observability-core` | Runtime | Instrument module boundaries; với tùy biến metric có thể cần API ở compile scope |
| Tùy biến event metrics/observability | `spring-modulith-observability-api` | Compile/implementation | API customization khi ứng dụng gọi trực tiếp |
| Event publication registry dùng JDBC | `spring-modulith-starter-jdbc` | Compile/implementation | Registry + storage/serializer theo mô hình JDBC |
| Event publication registry dùng JPA | `spring-modulith-starter-jpa` | Compile/implementation | Lựa chọn khác cho persistent publication |
| Trace export ngoài tiến trình | Micrometer tracing bridge + exporter được Boot hỗ trợ | Runtime/implementation theo API sử dụng | Nối Observation tới OTLP/Zipkin/collector |
| Prometheus | `micrometer-registry-prometheus` | Runtime | Cung cấp metric endpoint/export tương ứng |

Bảng là **hướng dẫn chọn dependency**. Tên artifact, cách starter kéo transitive dependencies và scope có thể đổi giữa release train; tham khảo Appendix “Spring Modulith modules” của đúng phiên bản dự án.

### 7.1. Những lỗi thường gặp khi khai báo scope

**Sai thứ nhất — chỉ thêm `docs` vào runtime:** sinh module graph thường là tác vụ build/test. Đưa thư viện tài liệu vào production không tự tạo sơ đồ, lại làm nặng classpath.

**Sai thứ hai — chỉ thêm `actuator` vào test:** test có thể kiểm tra kiến trúc, nhưng instance production không có endpoint Modulith nếu thiếu runtime dependency.

**Sai thứ ba — thêm Insight và cả hai nhánh riêng không cần thiết:** starter Insight đã đưa Actuator và observability support theo hướng dẫn chính thức. Trước khi thêm từng artifact một lần nữa, hãy xem dependency graph và tránh cấu hình trùng lặp.

**Sai thứ tư — quên tracing bridge/exporter:** module observation có thể tạo span nội bộ nhưng không đồng nghĩa collector đã nhận trace; phải cấu hình Micrometer Tracing và kênh xuất cho Boot version hiện tại.

**Sai thứ năm — tưởng BOM cài sẵn JDBC registry:** chỉ import BOM không tạo implementation storage hoặc schema cho registry.

### 7.2. Sự khác nhau giữa artifact Modulith 1.x và 2.x

Trong tài liệu Spring Modulith 1.4, artifact `spring-modulith-observability` dùng cho instrumentation trực tiếp. Trong dòng 2.2, tài liệu mô tả `spring-modulith-observability-core` và `spring-modulith-observability-api`, hoặc chọn `spring-modulith-starter-insight`.

Điều này minh họa vì sao không nên sao chép tên artifact từ một tutorial thuộc release train khác. Khi nâng cấp, **đọc tài liệu được version hóa** và xem starter trong BOM mới trước khi sửa dependency.

## 8. BOM và version liên quan đến module graph như thế nào?

Module graph thể hiện quan hệ giữa các **application module**. Công cụ phân tích thường chạy ở **test/build time**, còn module Actuator phải ở **runtime classpath** nếu muốn xem kiến trúc ở instance đang chạy.

Ví dụ kiểm tra kiến trúc và sinh tài liệu:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleDocumentationTests {

    @Test
    void verifyDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }

    @Test
    void generateModuleDiagram() {
        var modules = ApplicationModules.of(ShopApplication.class);
        new Documenter(modules).writeDocumentation();
    }
}
~~~

`ShopApplication` là class entrypoint giả định. Dependency `spring-modulith-docs` phải có trong test classpath khi sử dụng `Documenter`; kết quả được sinh ra ở build folder theo cấu hình Spring Modulith.

Khi nâng phiên bản Modulith, cần so sánh:

- `ApplicationModules.verify()` còn chạy và báo cấu trúc đúng không?
- Package nào được phát hiện là module, có thay đổi quy tắc detection không?
- Module graph/canvas có thêm hoặc mất ranh giới, dependency, event listener nào không?
- File tài liệu sinh ra có còn cùng định dạng và vị trí mong đợi của pipeline không?
- Actuator ở runtime có trả graph tương ứng với **cùng artifact commit** mà test đã xác nhận không?

**Graph là kiểm tra kiến trúc**, không phải trace runtime. Một thay đổi version có thể tác động khả năng phát hiện module hoặc cách documenter xuất tài liệu, nên phải đưa bài test graph vào quy trình nâng cấp chứ không chỉ kiểm tra ứng dụng startup.

## 9. BOM và version liên quan đến Actuator, metrics, tracing

Luồng quan sát trong ứng dụng minh họa:

~~~mermaid
flowchart LR
    M[Spring Modulith module boundaries] --> O[Modulith observability instrumentation]
    O --> R[Micrometer Observation]
    R --> S[Micrometer Tracing bridge]
    S --> E[Exporter OTLP / Zipkin]
    E --> B[Trace backend]
    R --> A[Micrometer metrics]
    A --> P[Actuator / Prometheus]
~~~

Các thành phần thuộc nhiều nhóm phụ thuộc khác nhau:

1. **Spring Modulith BOM:** quản lý artifact core, observability instrumentation và Actuator extension.
2. **Spring Boot dependency management:** quản lý Boot starters, Spring Framework, Micrometer và nhiều thư viện phụ trợ theo bộ được Boot kiểm thử.
3. **Phụ thuộc kênh xuất:** bridge/exporter/registry dành cho backend quan sát bạn chọn.
4. **Cấu hình runtime:** sampling, endpoint collector, bảo mật Actuator và executor để context propagation có ích.

Đừng cố sửa lỗi “không thấy trace” bằng cách đặt version mới nhất cho từng thư viện Micrometer. Trước hết kiểm tra: có span được tạo không, sampling có bật không, tracing bridge/exporter có xuất hiện trên runtime classpath không, collector có nhận dữ liệu không và backend có lưu được không.

### 9.1. Module Actuator

Khi dùng Insight hoặc Modulith Actuator, ứng dụng có thể công bố endpoint `/actuator/modulith` nếu Actuator và endpoint được enable/expose phù hợp.

Ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,modulith
~~~

Endpoint cần được bảo vệ theo chính sách vận hành. Một lần ứng dụng khởi động thành công chưa chứng minh endpoint được expose; cần gọi endpoint thật và xem danh sách application module.

### 9.2. Event metrics

Ở nhánh Modulith 2.2, tài liệu chính thức mô tả những metric liên quan đến event publication, ví dụ:

- `module.events.published`: bộ đếm publications.
- `module.events.published.<moduleIdentifier>.<simpleEventTypeName>`: bộ đếm theo từng loại event và module.

Tên metric được chuẩn hóa khi xuất sang Prometheus hoặc hệ thống giám sát khác. Những metric này thuộc phiên bản/trang tài liệu cụ thể; khi nâng cấp, kiểm tra meter names và tags thực tế trước khi chỉnh dashboard.

Không đặt `eventId`, `orderId` hoặc `traceId` làm metric label vì cardinality lớn. Có thể lưu chúng trong structured logs hoặc span attributes có chính sách dữ liệu thích hợp.

### 9.3. Context propagation

Async listener chạy trên thread khác; khi thay đổi Spring Framework, Micrometer hoặc executor, hành vi truyền context có thể khác. Test cần đối chiếu:

- Trace/span context trên thread request và thread listener.
- Propagation qua `@Async`, executor và optional task decorator.
- `eventId` còn ổn định qua retry/restart hay không.
- Không vô tình truyền transaction hoặc security context ngoài chính sách.

Trace span không thay thế bằng chứng publication đã completed. Version của runtime observability quan trọng, nhưng semantics completion còn phụ thuộc Spring Modulith events và transaction manager.

## 10. Nâng cấp event publication registry phải tính tới dữ liệu

Một application module có thể phát sự kiện trong transaction; listener ở module khác xử lý sau commit. Nếu dùng **persistent event publication registry**, publication đang chờ hoàn tất có thể được lưu bền, nên nâng cấp thư viện không chỉ là đổi dependency version.

~~~mermaid
sequenceDiagram
    participant O as orders
    participant R as Publication registry
    participant L as shipping listener
    O->>R: Ghi nhận publication
    O->>O: Commit transaction nguồn
    R-->>L: Listener nhận event sau commit
    L->>L: Thực hiện side effect
    L-->>R: Đánh dấu completion khi thành công
~~~

Sơ đồ là mô hình logic; thứ tự ghi và transaction cụ thể do implementation quyết định.

### 10.1. Một thay đổi phiên bản đáng kiểm tra

Trong **Spring Modulith 2.2**, thông báo phát hành chính thức cho biết việc **đánh dấu event publication completed tham gia vào transaction của listener theo mặc định**. Nhờ đó, phần thay đổi nghiệp vụ của listener và việc ghi completion cùng thành công hoặc cùng rollback. Bản này cũng phân biệt publication **failed** với **abandoned**.

Nếu ứng dụng cũ có monitoring/quy trình retry dựa trên trạng thái publication trước đây, cần đọc migration notes, xem lại các query và thử tình huống transaction rollback. Không giả định rằng event registry trong mọi bản Spring Modulith có cùng mô hình trạng thái.

### 10.2. Checklist nâng cấp registry

- Xác nhận implementation registry đang dùng: JDBC, JPA, MongoDB hay giải pháp khác.
- Kiểm tra schema initialization hoặc migration theo release target. Không sao chép SQL của release khác.
- Xác nhận event serializer tương thích với payload đang lưu; lưu ý đổi cấu trúc record hoặc Jackson version.
- Kiểm tra trạng thái publication chưa hoàn tất trước nâng cấp và cơ chế retry/resubmission.
- Dùng test transaction fail tại thời điểm listener xử lý, sau đó kiểm tra side effect và completion.
- Bảo đảm listener **idempotent**; completion bền vững không tự mang đến bảo đảm exactly-once.
- Nếu triển khai rolling upgrade nhiều instance khác phiên bản, đánh giá khả năng cả hai cùng đọc/ghi cùng registry schema và event format.

**Ví dụ sự cố:** listener đã ghi yêu cầu giao hàng nhưng tiến trình dừng trước lúc trạng thái hoàn tất được lưu, sau đó publication được phát lại. Một listener idempotent và unique constraint theo event/business key giúp tránh hai yêu cầu giao hàng. Cách xử lý phải được xác nhận bằng test ở release target.

## 11. Xem version thực sự được resolve

Khai báo POM/Gradle thể hiện **ý định**, còn dependency tree thể hiện **kết quả** sau khi xét BOM, transitive dependencies và version constraints.

### 11.1. Với Maven

Chạy trong dự án có cấu hình Maven:

~~~bash
./mvnw help:effective-pom
./mvnw dependency:tree -Dincludes=org.springframework.modulith
./mvnw dependency:tree -Dincludes=io.micrometer
./mvnw dependency:tree -Dincludes=org.springframework
~~~

Lệnh `effective-pom` giúp xem dependency management đã kế thừa và plugin config; `dependency:tree` cho biết dependency được resolve và phạm vi hiện tại. Nếu dự án không có Maven Wrapper, dùng `mvn` với Maven phiên bản được hỗ trợ.

Cần lưu ý `dependency:tree -Dincludes=org.springframework.modulith` lọc theo group; kiểm tra thêm toàn bộ tree khi cần tìm thư viện kéo transitive dependencies bất thường.

### 11.2. Với Gradle

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath \
    --dependency spring-modulith-observability-core
./gradlew dependencyInsight --configuration runtimeClasspath \
    --dependency micrometer-tracing
~~~

Trên Windows, dùng `gradlew.bat` hoặc cách gọi wrapper phù hợp shell. `dependencyInsight` giải thích vì sao một version được chọn, ví dụ do transitive dependency, platform constraint hoặc explicit version.

### 11.3. Các dấu hiệu lệch cần phát hiện

| Hiện tượng | Khả năng | Hướng kiểm tra |
| --- | --- | --- |
| `NoSuchMethodError` / `NoClassDefFoundError` | Thư viện build và runtime không cùng thế hệ | Xem runtimeClasspath, transitive dependencies và version được resolve |
| `Documenter` không tải được | Thiếu docs ở test scope hoặc API docs/core lệch | Xem testRuntimeClasspath, BOM và import |
| Modulith Actuator không xuất hiện | Thiếu Insight/Actuator runtime hoặc endpoint không expose | Dependency tree và Actuator configuration |
| Trace spans không ra backend | Thiếu bridge/exporter hoặc exporter config | Xem classpath, sampling và collector |
| Registry không đọc được publication | Schema/serializer không còn phù hợp | Migration notes và dữ liệu fixture từ bản cũ |
| Một module build dùng bản mới, submodule khác dùng bản cũ | BOM chỉ được khai báo ở một project | Xem effective POM hoặc từng Gradle subproject |
| Test qua nhưng production lỗi | Dependency có ở test scope mà thiếu runtime scope | So sánh testRuntimeClasspath với runtimeClasspath |

**Quy tắc thực tế:** chẩn đoán phải dựa trên classpath hoặc artifact đã deploy. IDE hiển thị một phiên bản không bảo đảm Docker image hoặc JAR production đang chạy đúng phiên bản đó.

## 12. Quản lý phiên bản trong codebase nhiều module

Nếu ứng dụng có nhiều nhóm phát triển, việc thống nhất version cần được thực thi bằng build convention thay vì chỉ có hướng dẫn bằng văn bản.

### Maven reactor

~~~text
shop-parent (dependencyManagement)
├── orders (parent = shop-parent)
├── inventory (parent = shop-parent)
├── shipping (parent = shop-parent)
└── application (parent = shop-parent)
~~~

Parent quản lý Boot/Modulith versions. Các module không nên tự nâng Modulith theo lịch riêng nếu cuối cùng được đóng vào **một** ứng dụng. Nếu library khác dùng Spring Modulith API và được phát hành riêng, cần công bố những version được hỗ trợ rõ ràng.

### Gradle multi-project

~~~text
settings.gradle
build-logic/                 # convention plugins
orders/
inventory/
shipping/
application/
~~~

Dùng convention plugin ở `build-logic` hoặc cấu hình chung có chủ đích để inject cùng BOM cho các subproject cần sử dụng. Gradle version catalog (`libs.versions.toml`) có thể chứa version Boot plugin và Modulith BOM, nhưng **version catalog không tự áp dụng một platform**; mỗi project vẫn phải khai báo dependencies/convention phù hợp.

### Version của domain event

Một tên event như `OrderPlaced` là kiểu dữ liệu nghiệp vụ, không phải phiên bản thư viện. Nếu chỉ dùng Spring application events trong cùng JVM, producer và consumer thường được deploy cùng một artifact. Tuy nhiên, khi dùng persistent registry hoặc broker, **payload có thể sống qua nhiều lần triển khai**; đổi field/serializer có thể phá khả năng deserialize sự kiện cũ.

Có thể áp dụng chính sách:

1. Giữ event ID và contract ổn định trong một khoảng tương thích.
2. Khi thay đổi không tương thích, dùng `OrderPlacedV2` hoặc schema version được công bố.
3. Kiểm thử deserialize các publication đang tồn từ phiên bản trước.
4. Chỉ loại bỏ consumer/serializer cũ khi đã xử lý hoặc chuyển đổi dữ liệu cũ.
5. Không dùng mỗi phiên bản Spring Modulith làm phiên bản domain event.

## 13. Quy trình nâng cấp có kiểm soát

Giả sử ứng dụng hiện dùng Spring Boot 3.5 và Spring Modulith 1.4, cần đánh giá chuyển sang Boot 4.2 và Modulith 2.2.

~~~mermaid
flowchart TD
    A[Kiểm kê Boot/Modulith/JDK và dependencies] --> B[Đọc compatibility + release notes]
    B --> C[Chọn target release train và BOM]
    C --> D[Đổi BOM / plugin versions]
    D --> E[Resolve dependency tree]
    E --> F[Compile + tests + ApplicationModules.verify]
    F --> G[So sánh module docs/graph]
    G --> H[Kiểm thử events/registry/serialization]
    H --> I[Deploy staging với backend thật]
    I --> J[Actuator + metrics + tracing + listener test]
    J --> K{Đạt acceptance criteria?}
    K -- Có --> L[Phát hành theo quy trình]
    K -- Không --> M[Điều tra, sửa, kiểm tra lại]
~~~

### Trình tự đề xuất

**Bước 1 — kiểm kê hiện trạng.** Chốt phiên bản JDK, Boot, Modulith, Gradle/Maven, Micrometer, event registry implementation, database schema và release đang chạy. Lưu dependency tree cùng artifact/image digest làm baseline.

**Bước 2 — đánh giá tương thích.** Đọc release notes các bản trung gian và tài liệu version hóa. Với nâng cấp Boot major, xem thay đổi Spring Framework, Jakarta APIs, Jackson và auto-configuration. Với Modulith, chú ý module detection, docs, events, metrics và transaction completion.

**Bước 3 — thay đổi một cách có kiểm soát.** Chỉ sửa một cặp version Boot + Modulith và các API cần migration, giảm số override thư viện. Đừng trộn thêm refactor nghiệp vụ không liên quan trong cùng đợt nếu không cần.

**Bước 4 — kiểm tra build graph.** Kiểm tra Maven effective POM / Gradle dependencyInsight. Mọi Modulith artifact trên runtime/test classpath phải tương thích, không tồn tại nhánh 1.x lẫn với 2.x.

**Bước 5 — chạy kiểm tra kiến trúc.** `ApplicationModules.verify()`, module tests và sinh tài liệu. So sánh thay đổi module graph/canvas để phát hiện dependency bất thường do refactor hoặc thay đổi cách nhận diện.

**Bước 6 — kiểm tra events.** Thử phát event trong transaction, rollback, xử lý async, retry, restart với outstanding publications. Xác nhận schema, serializer, completion và idempotency.

**Bước 7 — kiểm tra observability.** Mở `/actuator/modulith`, xem event metrics, trace module interaction, thử context propagation qua executor và xác nhận backend OTLP/Prometheus nhận dữ liệu thật.

**Bước 8 — phát hành.** Deploy cùng artifact được kiểm thử trên staging; lưu release report, kế hoạch rollback và xác định có cần migration dữ liệu không thể đảo ngược hay không.

## 14. Một bài test kiểm chứng phiên bản theo góc nhìn Modulith

Một bộ kiểm thử tối thiểu gồm ba mặt:

### Kiến trúc

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureTests {

    @Test
    void moduleBoundariesAreValid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

### Tài liệu

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class DocumentationTests {

    @Test
    void generateModuleDocs() {
        new Documenter(ApplicationModules.of(ShopApplication.class))
            .writeDocumentation();
    }
}
~~~

### Vận hành

- Khởi động ứng dụng với phiên bản đã chọn trên staging.
- Xác nhận `/actuator/modulith` hiển thị module và dependency như tài liệu đã sinh, nếu endpoint được bật.
- Gửi một request phát `OrderPlaced`, đối chiếu eventId giữa publisher và listener.
- Xác nhận log, event metrics và trace backend nhận tín hiệu, nhận thức rằng context async có thể tạo trace riêng.
- Nếu có registry, kiểm tra publication được hoàn tất sau xử lý, lỗi listener không bị đánh dấu thành công và retry không nhân đôi side effect.

Hai test Java trên dùng `ShopApplication` giả định; cần project thực tế, JUnit và dependencies tương ứng. Chúng là ví dụ để đưa vào dự án, không phải một project Java hoàn chỉnh tự chạy.

## 15. Bài thực hành lựa chọn BOM

**Tình huống:** nhóm phát triển có ứng dụng đơn hàng với modules `orders`, `payments` và `shipping`. Ứng dụng cần phát tài liệu module graph trong CI, expose module Actuator ở staging, ghi event metrics và xuất trace qua OTLP.

### Phần A — cấu hình

Tạo **hai cấu hình độc lập** để so sánh trên nhánh thử nghiệm:

- Một cấu hình Maven với Spring Boot parent và import Modulith BOM.
- Một cấu hình Gradle sử dụng native platforms hoặc dependency-management plugin.

Khai báo starter core, Insight runtime, starter test và docs test. Nếu sử dụng event registry, chọn JDBC hoặc JPA phù hợp và bổ sung dependency. Chạy dependency tree để xác minh selected versions.

### Phần B — đổi phiên bản có lỗi

Giả lập một build cấu hình version `spring-modulith-docs` khác release train với core. Quan sát dependencyInsight/tree trước khi chạy test, sau đó sửa bằng BOM thống nhất. Mục đích là học **cách phát hiện và giải thích** lệch phiên bản, không cần cố tình đợi ứng dụng lỗi ở runtime.

### Phần C — xác nhận các khả năng

Sinh graph, chạy module verification, kiểm tra Modulith Actuator. Gửi một event bất đồng bộ, xem metric publication và trace sau khi listener chạy. Thử có và không có context propagation để hiểu vì sao một event có thể xuất hiện trong nhiều trace.

### Phần D — đánh giá nâng cấp

Đọc release notes của Spring Modulith 2.2 và mô tả tác động của mặc định completion trong transaction listener, trạng thái failed/abandoned, version schema/serializer và chính sách retry. Đề xuất ma trận test trước khi chuyển artifact lên production.

### Checklist hoàn thành

- [ ] Xác định rõ Spring Boot release train và Spring Modulith release train tương thích.
- [ ] Có một nguồn quản lý version Modulith BOM duy nhất cho toàn ứng dụng.
- [ ] Dependency compile/runtime/test/docs được khai báo phù hợp.
- [ ] Runtime và test dependency tree cho thấy version Modulith thống nhất.
- [ ] Không tự ghi đè Micrometer/Spring Framework versions nếu thiếu lý do và test tương thích.
- [ ] `ApplicationModules.verify()` chạy, module documentation được sinh và có thể so sánh.
- [ ] Actuator/module graph được kiểm tra trên instance đã deploy.
- [ ] Metrics và traces được xác minh trên backend quan sát thực tế.
- [ ] Nếu dùng registry, transaction completion/retry/serialization được kiểm tra với target release.
- [ ] Có ghi nhận kết quả test, artifact digest, version và kế hoạch rollback.

## 16. Tài liệu tham khảo và cách tiếp tục kiểm tra phiên bản

Các nguồn dưới đây là tài liệu chính thức nên kiểm tra **lại tại thời điểm nâng cấp**, vì release train và artifact có thể thay đổi:

1. [Spring Modulith – Reference Documentation](https://docs.spring.io/spring-modulith/reference/): BOM, danh mục artifact và phiên bản chính thức.
2. [Spring Modulith – Spring Boot Compatibility & Appendix](https://docs.spring.io/spring-modulith/reference/appendix.html): ma trận và danh mục cấu hình theo phiên bản.
3. [Spring Modulith – Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): Insight starter, Actuator, module spans, event metrics.
4. [Spring Modulith – Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html): Documenter, module graph, Application Module Canvas.
5. [Spring Boot – Dependency Management](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html): dependency-management plugin và Gradle native BOM.
6. [Spring Modulith 2.2 GA – Release announcement (19/11/2026)](https://spring.io/blog/2026/11/19/spring-modulith-2-2-ga-2-1-3-and-2-0-10-released/): thay đổi completion, publication status và nền tảng.

**Kết quả mong đợi:** nhóm phát triển kiểm soát được phiên bản Spring Boot, Spring Modulith và các thư viện quan sát như một bộ tương thích; module graph, Actuator, event metrics, tracing và publication registry tiếp tục hoạt động đúng sau nâng cấp, đồng thời mọi thay đổi được chứng minh bằng dependency tree và kiểm thử trên môi trường thật.
