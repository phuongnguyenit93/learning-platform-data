# Quản lý phiên bản và dependency bằng Spring AI BOM

> **Chương:** Thiết lập dự án
>
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — học đánh giá relevance, fact checking, kiểm thử RAG/tool calling và quan sát metrics, traces, token usage, chi phí, độ trễ qua các phiên bản prompt, model, pipeline.
>
> **Mốc phiên bản minh họa:** 27/11/2026. Dùng Java 21, Spring Boot 4.2.0, Spring AI 2.1.0. Khi xây dựng dự án ở thời điểm khác, kiểm tra lại ma trận tương thích trong tài liệu phát hành.

## 1. Mục tiêu học tập và vấn đề thực tế

Sau bài học, bạn có thể:

1. Giải thích **BOM (Bill of Materials)**, **dependency management**, **direct dependency** và **transitive dependency**.
2. Phân biệt vai trò của **Spring AI BOM**, **Spring Boot BOM/parent**, build plugin và Java toolchain.
3. Import Spring AI BOM trong **Maven** và **Gradle**, thêm model/vector-store/test dependencies mà không khai báo phiên bản riêng lẻ.
4. Tìm ra phiên bản dependency thực sự được resolve, phát hiện xung đột giữa BOM, direct declaration và thư viện bên thứ ba.
5. Thiết lập cách nâng cấp, khóa dependency graph và lưu baseline để so sánh chất lượng RAG, tool calling, metrics và traces đáng tin cậy.

**Bối cảnh:** nhóm phát triển trợ lý RAG đo relevance và fact checking trên một bộ 100 câu hỏi chuẩn. Ở lần chạy A, ứng dụng dùng Spring AI 2.1.0; ở lần chạy B, một module vô tình dùng Spring AI 2.0.x. Kết quả có thể khác do API, cách xử lý tool, SDK hoặc instrumentation, nhưng nhóm lại quy sai cho prompt. Một BOM thống nhất giúp giảm rủi ro này và làm rõ **chính xác code đã chạy với những phiên bản nào**.

## 2. Spring AI BOM là gì?

**Spring AI BOM** là một Maven POM có tọa độ:

~~~text
org.springframework.ai:spring-ai-bom:2.1.0
~~~

BOM chứa các **version constraints/managed versions** dành cho những module trong hệ sinh thái Spring AI. Khi project import BOM, có thể khai báo:

~~~xml
<dependency>
    <groupId>org.springframework.ai</groupId>
    <artifactId>spring-ai-starter-model-openai</artifactId>
</dependency>
~~~

Build tool lấy phiên bản của starter từ BOM thay vì buộc bạn ghi `<version>2.1.0</version>` tại từng dependency. Tương tự với các module vector store hoặc test do BOM quản lý.

### BOM làm gì và không làm gì?

| Thành phần | Chức năng | Có tự động thêm vào classpath không? |
|---|---|---|
| **Spring AI BOM** | Quản lý các phiên bản do Spring AI công bố | **Không**; chỉ import BOM chưa có ChatModel/VectorStore |
| **Spring Boot parent/BOM** | Quản lý phiên bản Spring Boot, Spring Framework và các thư viện hạ tầng do Boot hỗ trợ | **Không** nếu chỉ import BOM; parent còn có plugin/build defaults |
| **Spring AI starter** | Kéo module chức năng và auto-configuration liên quan đến provider/integration | **Có**, khi khai báo trong dependencies |
| **Spring AI module** | Cung cấp các API/implementation, có thể cần cấu hình bean thủ công | **Có**, khi khai báo trực tiếp hoặc qua dependency khác |
| **Spring Boot Maven/Gradle plugin** | Đóng gói/chạy ứng dụng và tích hợp build | Không thay thế BOM Spring AI |
| **JDK/toolchain** | Xác định Java dùng để biên dịch/chạy | Không được Spring AI BOM lựa chọn |

**Điểm mấu chốt:** Spring AI BOM là **BOM-only**. Theo tài liệu chính thức, BOM này chỉ mang thông tin quản lý phiên bản, không khai báo plugin và không trực tiếp tham chiếu Spring/Spring Boot. Vì vậy, dùng BOM Spring AI 2.1.0 **không tự nâng** Spring Boot 4.1 lên 4.2.

### Dependency graph trước và sau khi import BOM

~~~mermaid
flowchart TD
  P["Ứng dụng AI"] --> B["Spring Boot dependency management<br/>4.2.0"]
  P --> A["Spring AI BOM<br/>2.1.0"]
  A -.-> M["Quản lý version:<br/>spring-ai-starter-model-openai"]
  A -.-> V["Quản lý version:<br/>spring-ai-starter-vector-store-pgvector"]
  A -.-> T["Quản lý version:<br/>spring-ai-test"]
  B -.-> O["Quản lý version:<br/>Spring Boot Actuator / Micrometer"]
  P --> D["Direct dependencies do ứng dụng chọn"]
  D --> M
  D --> O
  D -.-> V
  D -.-> T
~~~

Các đường nét đứt biểu thị **quản lý phiên bản**. Một thư viện chỉ thực sự có trong dependency graph khi project hoặc một dependency khác yêu cầu nó. Chẳng hạn, import BOM không tự cài PGvector, không tạo kết nối cơ sở dữ liệu và không kích hoạt metrics/traces.

## 3. Chọn dòng BOM đúng với Spring Boot

Tại mốc 27/11/2026, ma trận tương thích chính thức của Spring AI là:

| Spring AI BOM | Spring Boot | Java tối thiểu | Khi nào dùng |
|---|---|---|---|
| **2.1.x** (ví dụ 2.1.0) | **4.2.x** (ví dụ 4.2.0) | **17** | Dự án mới theo dòng 2.1 |
| **2.0.x** | **4.1.x** | Kiểm tra yêu cầu của release tương ứng | Dự án duy trì trên Boot 4.1 |
| **1.1.x** | **3.5.x** | Kiểm tra yêu cầu của release tương ứng | Dự án hiện hữu chưa chuyển lên Boot 4 |

Java 21 LTS là lựa chọn thực hành của bài, còn yêu cầu tối thiểu cho Spring AI **2.1.x là Java 17**. Chọn cùng một dòng release cho **BOM, starter, API sử dụng và test utilities**; không nên dùng API của 2.1 rồi ép một starter về 2.0.x.

**Lưu ý về bản phát hành:** trong bài, `2.1.0` là **GA/release ổn định**, còn `2.1.1-SNAPSHOT` là phiên bản đang phát triển. Spring AI GA có trên **Maven Central**, thường không cần repository bổ sung. Chỉ cấu hình snapshot/milestone repository nếu đang chủ đích thử nghiệm nhánh đó; không dùng snapshot làm baseline kết quả evaluation dài hạn khi chưa có quy trình tái lập riêng.

Ví dụ một bộ không đúng hướng:

~~~text
Spring Boot: 4.1.x
Spring AI BOM: 2.1.0
spring-ai-starter-model-openai: 2.1.0
~~~

BOM chỉ thống nhất **hai dependency AI** với nhau, không biến tổ hợp Boot 4.1 + AI 2.1 thành tổ hợp được hỗ trợ. Hãy nâng Boot lên dòng **4.2.x** hoặc giữ Spring AI ở dòng phù hợp với Boot 4.1.

## 4. Maven: dùng Spring Boot parent và import Spring AI BOM

Đây là cách ngắn gọn, rõ ràng cho một ứng dụng Spring Boot dùng Maven.

**pom.xml**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>ai-quality-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.2.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>21</java.version>
        <spring-ai.version>2.1.0</spring-ai.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.ai</groupId>
                <artifactId>spring-ai-bom</artifactId>
                <version>${spring-ai.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <!-- Provider AI, được Spring AI BOM quản lý version -->
        <dependency>
            <groupId>org.springframework.ai</groupId>
            <artifactId>spring-ai-starter-model-openai</artifactId>
        </dependency>

        <!-- Hỗ trợ các bài test ứng dụng AI -->
        <dependency>
            <groupId>org.springframework.ai</groupId>
            <artifactId>spring-ai-test</artifactId>
            <scope>test</scope>
        </dependency>

        <!-- Hạ tầng metrics của Spring Boot -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
            <scope>runtime</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

**Cách đọc POM:**

1. `<parent>` kế thừa cấu hình dependency và plugin management của **Spring Boot 4.2.0**.
2. `<spring-ai.version>2.1.0</spring-ai.version>` là **một điểm thay đổi phiên bản Spring AI** cho cả dự án.
3. `<dependencyManagement>` import Spring AI BOM bằng `<type>pom</type>` và `<scope>import</scope>`; hai thuộc tính này có ý nghĩa **chỉ trong dependencyManagement**.
4. `<dependencies>` mới chọn starter, test module và hạ tầng thực sự dùng. Không viết `<version>` trên các dependency đã được BOM quản lý.
5. `spring-ai-test` ở `test` scope để không kéo tiện ích kiểm thử vào runtime; Actuator và Prometheus được Spring Boot quản lý version.

Đây là **định nghĩa dependency/build**, không phải ứng dụng chạy được ngay: để gọi model cần thêm mã gọi `ChatClient`, biến môi trường `OPENAI_API_KEY`, mạng và quyền truy cập provider. Để có traces cần thêm tracing starter, exporter và backend thích hợp; chỉ có Actuator/Prometheus chưa đủ.

### Thêm PGvector cho luồng RAG

Khi bước thực hành mở rộng sang retrieval, thêm starter do cùng BOM quản lý:

~~~xml
<dependency>
    <groupId>org.springframework.ai</groupId>
    <artifactId>spring-ai-starter-vector-store-pgvector</artifactId>
</dependency>
~~~

Việc thêm PGvector còn đòi hỏi **PostgreSQL đã bật extension vector**, cấu hình kết nối, một `EmbeddingModel` thích hợp và thiết lập schema/index tương ứng. BOM **không tạo database**, không bảo đảm embedding dimension khớp cột vector và không kiểm tra relevance cho bạn.

### Thêm tracing để quan sát RAG/tool calling

Với Spring Boot 4.2, có thể bổ sung:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-opentelemetry</artifactId>
</dependency>
~~~

Sau đó cấu hình OTLP exporter, collector/backend và sampling theo tài liệu Spring Boot. Version của tracing starter thuộc **Spring Boot management**, không thuộc Spring AI BOM; metrics/spans chỉ xuất hiện với các thao tác có instrumentation và thật sự được thực thi.

## 5. Maven khi công ty có parent POM riêng

Maven cho phép **một parent trực tiếp**. Nếu ứng dụng đã bắt buộc kế thừa parent POM nội bộ, không thể khai báo thêm `spring-boot-starter-parent` làm parent thứ hai. Thay vào đó, import **hai BOM** phù hợp:

~~~xml
<!-- Ví dụ một phần trong POM có parent công ty -->
<properties>
    <spring-boot.version>4.2.0</spring-boot.version>
    <spring-ai.version>2.1.0</spring-ai.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.ai</groupId>
            <artifactId>spring-ai-bom</artifactId>
            <version>${spring-ai.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Trường hợp này **không kế thừa cấu hình build/plugin** của `spring-boot-starter-parent`. Cần kiểm tra phiên bản compiler, test runner, packaging và **spring-boot-maven-plugin** trong parent công ty hoặc `pluginManagement` của dự án. Một BOM dependency không điều khiển phiên bản plugin build.

### Maven multi-module: parent khác aggregator

Ví dụ nhóm có các module `api`, `rag-core`, `eval-tests`:

~~~text
ai-quality-platform/               (pom; parent chung)
├── pom.xml                         (dependencyManagement import BOM)
├── api/pom.xml                      (chọn model starter)
├── rag-core/pom.xml                 (chọn vector store starter)
└── eval-tests/pom.xml               (chọn spring-ai-test)
~~~

Các module con chỉ được kế thừa `dependencyManagement` nếu **thực sự khai báo parent POM tương ứng**. Có mặt trong phần `<modules>` của một aggregator **không đủ để tự thừa kế** BOM.

Ví dụ POM con:

~~~xml
<parent>
    <groupId>com.example</groupId>
    <artifactId>ai-quality-platform</artifactId>
    <version>1.0.0-SNAPSHOT</version>
</parent>

<artifactId>rag-core</artifactId>

<dependencies>
    <dependency>
        <groupId>org.springframework.ai</groupId>
        <artifactId>spring-ai-starter-vector-store-pgvector</artifactId>
    </dependency>
</dependencies>
~~~

Khi BOM được khai báo đúng trong parent, module con không cần lặp lại Spring AI BOM. Phải tránh một module con tự override Spring AI starter xuống dòng 2.0 trong khi các module khác đang dùng dòng 2.1.

## 6. Gradle: import Spring AI BOM qua native platform

Gradle có **native BOM support**. Trong một ứng dụng Spring Boot 4.2 dùng Groovy DSL, có thể import cả Boot BOM và Spring AI BOM:

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
}

group = 'com.example'
version = '1.0.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

def springAiVersion = '2.1.0'

dependencies {
    // Native BOM support: quản lý dependency Boot và Spring AI
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.2.0')
    implementation platform("org.springframework.ai:spring-ai-bom:${springAiVersion}")

    implementation 'org.springframework.ai:spring-ai-starter-model-openai'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
    testImplementation 'org.springframework.ai:spring-ai-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Giải thích:**

- Plugin `org.springframework.boot` hỗ trợ các tác vụ build/packaging của Boot; ở chiến lược **native platform**, khai báo **Boot BOM** tường minh để quản lý dependency.
- `implementation platform(...)` đưa các khuyến nghị phiên bản vào Gradle dependency resolution; starter giữ dạng versionless.
- `testImplementation` mang dependency chỉ dùng khi biên dịch/chạy test. Với cấu hình Java plugin thông thường, test classpath kế thừa các dependency `implementation`.
- `java.toolchain` cố định Java compiler/runtime toolchain cần thiết cho build; hãy dùng **Gradle Wrapper** và kiểm tra version Gradle tương thích với dòng Boot.

### Một cách khác: io.spring.dependency-management

Spring Boot cũng hỗ trợ Gradle plugin `io.spring.dependency-management`. Khi plugin này được áp dụng cùng Spring Boot Gradle plugin, nó có thể tự import **Spring Boot BOM** từ version của plugin Boot; sau đó bạn import thêm Spring AI BOM trong `dependencyManagement`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.ai:spring-ai-bom:2.1.0'
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.ai:spring-ai-starter-model-openai'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Hai ví dụ thể hiện **hai chiến lược hợp lệ**; trong một module, chọn chiến lược rõ ràng và đọc kết quả `dependencyInsight`. Không bê nguyên cả hai cách vào một build rồi giả định mọi BOM sẽ có cùng quy tắc ưu tiên.

### platform và enforcedPlatform có gì khác?

| Gradle notation | Ý nghĩa | Hệ quả |
|---|---|---|
| `platform("...:spring-ai-bom:2.1.0")` | Đưa managed versions thành **constraints/khuyến nghị** | Một phiên bản khác có thể được chọn do xung đột hoặc constraint mạnh hơn |
| `enforcedPlatform("...:spring-ai-bom:2.1.0")` | Ràng buộc phiên bản BOM chặt hơn bằng **strict constraints** | Hạn chế resolve phiên bản khác, có thể tạo conflict và lan ràng buộc đến consumer |

Với ứng dụng thông thường, bắt đầu từ **platform** và kiểm tra resolved graph. `enforcedPlatform` không nên được thêm máy móc vào một **library được publish**, vì ràng buộc mạnh của nó có thể ảnh hưởng dependency resolution của ứng dụng tiêu thụ library.

**BOM khác version catalog/lockfile:** version catalog giúp tập trung tọa độ dependency; BOM tham gia quản lý và giải quyết phiên bản; dependency locking ghi **phiên bản đã resolve** theo configuration. Ba cơ chế bổ sung cho nhau, không hoàn toàn thay thế nhau.

## 7. Phiên bản thực sự được chọn nằm ở dependency graph

Một dự án có thể khai báo `spring-ai-bom:2.1.0` mà vẫn resolve một library khác kỳ vọng. Vì vậy cần phân biệt **phiên bản được yêu cầu** và **phiên bản thực tế**.

### Direct dependency và transitive dependency

~~~text
ai-quality-lab
├── spring-ai-starter-model-openai          (direct)
│   ├── spring-ai-openai                   (transitive)
│   └── ... OpenAI SDK / Spring AI modules (transitive)
├── spring-boot-starter-actuator            (direct)
│   └── ... Micrometer / Boot modules      (transitive)
└── spring-ai-test                          (direct; test scope)
~~~

Đây là **sơ đồ khái niệm**, không phải kết quả `dependency:tree` đã chạy. Danh sách module và các đường phụ thuộc cụ thể thay đổi theo release. `spring-ai-bom` sẽ xuất hiện trong phần quản lý version, không phải một JAR runtime.

### Với Maven

~~~bash
# Xem toàn bộ cây dependency
./mvnw dependency:tree

# Chỉ tập trung các artifacts Spring AI
./mvnw dependency:tree -Dincludes=org.springframework.ai

# Xem POM hiệu lực sau khi kế thừa parent và import BOM
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
~~~

Khi dùng PowerShell, nếu shell xử lý bất thường các đối số `-D...`, hãy đặt đối số đó trong dấu nháy. Điều quan trọng là **đọc kết quả** và tìm đúng group/artifact/version, không chỉ dựa vào thông báo `BUILD SUCCESS`.

### Với Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-ai-starter-model-openai --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-ai --configuration runtimeClasspath

# Kiểm tra classpath của test khi cần
./gradlew dependencies --configuration testRuntimeClasspath
~~~

`dependencyInsight` giải thích **vì sao** Gradle chọn version, gồm nguồn constraints, conflict resolution và version được yêu cầu. Nên lưu bản tóm tắt resolved graph vào kết quả CI cùng commit/build ID.

### Một ví dụ về xung đột

Giả sử dự án import Spring AI BOM **2.1.0** nhưng khai báo trực tiếp:

~~~xml
<!-- Cấu hình nên tránh trong thí nghiệm chuẩn -->
<dependency>
    <groupId>org.springframework.ai</groupId>
    <artifactId>spring-ai-starter-model-openai</artifactId>
    <version>2.0.3</version>
</dependency>
~~~

Trong Maven, version ghi trực tiếp trên dependency có thể thắng managed version, khiến project dùng starter 2.0.3 bên cạnh module AI 2.1.x khác. Đây là một ví dụ **dependency drift**: BOM tồn tại nhưng không còn bảo đảm mọi module đồng dòng.

Với Gradle `platform`, các constraints là khuyến nghị; Gradle có thể chọn phiên bản khác khi graph chứa phiên bản/constraint xung đột. Do đó **không suy quy tắc của Maven sang Gradle**; luôn xem resolved graph bằng công cụ tương ứng.

### Nhiều BOM cùng quản lý một artifact

Khi import nhiều BOM, ví dụ Boot, AI, cloud SDK hoặc tổ chức nội bộ, phải xem **version nào thắng**. Maven quy định trong các **import BOM ngang cấp cùng quản lý một artifact** mà POM không override trực tiếp thì **BOM khai báo trước thắng**. Managed dependency trực tiếp trong POM hiện tại có độ ưu tiên riêng. Với Gradle, cơ chế resolution dựa trên constraints và conflict rules, không đơn giản là BOM viết trước thắng.

Nguyên tắc phòng lỗi: chỉ override khi có yêu cầu tương thích hoặc bảo mật rõ ràng, đưa override vào review và test; không thêm version thủ công để “sửa nhanh” một lỗi dependency mà không hiểu nguyên nhân.

## 8. Chọn dependency theo mục tiêu evaluation/observability

Không phải ứng dụng nào cũng cần tất cả starter. Mỗi adapter bổ sung có thể kéo theo SDK, bean và cấu hình riêng.

| Nhu cầu | Dependency/nhóm được chọn | Người quản lý version chính | Điều kiện ngoài dependency |
|---|---|---|---|
| Gọi LLM OpenAI | `spring-ai-starter-model-openai` | Spring AI BOM | API key và model thực tế |
| Dùng Ollama local | `spring-ai-starter-model-ollama` (thay/hoặc chọn có chủ đích) | Spring AI BOM | Server Ollama và model đã tải |
| Truy xuất PGvector | `spring-ai-starter-vector-store-pgvector` | Spring AI BOM | Postgres, extension, embedding/index |
| Viết test/evaluator | `spring-ai-test` ở test scope | Spring AI BOM | Dataset, rubric, expected outcome |
| Health và metrics | `spring-boot-starter-actuator` | Spring Boot BOM/parent | Bật endpoint/export phù hợp |
| Xuất Prometheus | `micrometer-registry-prometheus` | Spring Boot BOM/parent | Scrape endpoint và bảo vệ truy cập |
| Tracing OTLP | `spring-boot-starter-opentelemetry` (Boot 4.2) | Spring Boot BOM/parent | Tracer, sampling, collector/backend |

Với **relevance/fact checking**, BOM chỉ giữ API evaluator/test support ở dòng version dự kiến; chất lượng phép đo còn phụ thuộc **tập dữ liệu, tiêu chí chấm, ngữ cảnh truy xuất, câu trả lời chuẩn và evaluator model**. Không nên kỳ vọng một BOM giúp câu trả lời đúng hơn ngay lập tức.

Với **RAG**, dependency đồng dòng giúp tránh lệch API advisor/vector store, nhưng không kiểm soát chất lượng embedding, chunking, top-k, filter hoặc phiên bản chỉ mục. Với **tool calling**, BOM giúp thống nhất runtime API/tool integration, trong khi correctness vẫn cần kiểm tra **schema đầu vào, quyền thực thi, tham số tool và failure handling**.

Với **observability**, framework version có thể làm thay đổi **tên/semantics của observation, span hoặc metric**, nhất là khi Micrometer, Spring AI hoặc provider SDK được nâng. Token count có thể thiếu nếu provider không trả usage; **chi phí** cần bảng giá model theo thời gian và phép tính bổ sung. Nếu dashboard bất ngờ mất một metric sau nâng cấp, kiểm tra dependency và instrumentation trước khi kết luận AI pipeline ngừng hoạt động.

## 9. Khóa môi trường để thí nghiệm có thể tái lập

**BOM là điểm xuất phát, không phải bằng chứng duy nhất về tính tái lập.** Có thể có dependency ngoài phạm vi BOM, transitive upgrade, build plugin, JDK, native library hoặc service bên ngoài không thay đổi cùng nhịp với BOM.

### Những gì cần lưu cùng mỗi lần evaluation

| Nhóm | Trường nên ghi |
|---|---|
| Source/build | Git commit, JDK runtime, Maven/Gradle Wrapper version, build timestamp/artifact digest |
| Dependency | Spring Boot version, Spring AI BOM version, resolved dependency graph/lockfile |
| Dữ liệu | Dataset snapshot, nhãn ground truth, phiên bản evaluator/rubric |
| Prompt/model | Prompt template revision, model/provider ID, generation parameters |
| RAG/tool | Embedding model, chunking, vector index/corpus, top-k/filter, tool schemas |
| Observability | Metrics/span conventions, sampling, collector/backend, timeout/retry config |
| Kết quả | Relevance/factuality, tool success, token input/output, latency p50/p95, giá ước tính |

**Maven:** nên dùng wrapper, phiên bản release cố định, lưu POM hiệu lực/cây dependency trong CI và dùng Maven Enforcer hoặc cơ chế kiểm tra tương đương nếu cần kiểm soát dependency convergence. Một `pom.xml` có BOM vẫn có thể resolve dependency ngoài dự kiến do override hoặc transitive dependency.

**Gradle:** ngoài wrapper và BOM, có thể bật **dependency locking** nếu cần tái lập resolved versions:

~~~groovy
// Trong build.gradle; bổ sung có chủ đích theo policy nhóm
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau đó tạo/cập nhật lock state trong workflow kiểm soát phiên bản, ví dụ:

~~~bash
./gradlew dependencies --write-locks
~~~

Đưa lockfile được sinh vào version control, kiểm tra diff và không cập nhật lockfile trong cùng một commit thay prompt trừ khi đó là chủ đích thí nghiệm. Khi thêm module Gradle mới, phải bảo đảm các configuration của module đó có BOM/constraints và policy locking tương ứng.

### CI kiểm chứng dependency và chất lượng

~~~mermaid
flowchart LR
    A["Checkout commit"] --> B["JDK + Wrapper"]
    B --> C["Resolve BOM + dependency graph"]
    C --> D{"Version hợp lệ?"}
    D -->|Không| E["Fail build / điều tra conflict"]
    D -->|Có| F["Build + unit/integration tests"]
    F --> G["Run evaluation dataset"]
    G --> H["Collect metrics/traces"]
    H --> I["Lưu baseline + so sánh regression"]
~~~

Để kiểm chứng runtime thật, cần integration tests phù hợp và các dịch vụ liên quan (mock provider, local model, testcontainer hoặc môi trường đã quản lý). Một số evaluator gọi LLM sẽ có tính không xác định và phát sinh chi phí; nên tách **test deterministic** chạy mọi commit khỏi **evaluation tốn chi phí** có lịch/quota hoặc gate riêng.

## 10. Nâng Spring AI BOM an toàn

Ví dụ nhóm nâng từ Spring AI **2.0.x** trên Spring Boot **4.1.x** lên AI **2.1.0** trên Boot **4.2.0**:

1. **Lưu baseline trước nâng cấp:** dependency graph, dataset, prompt revision, model, vector index, các metric chính.
2. **Đọc release notes/migration guide:** xác định breaking changes API, auto-configuration, memory/tool calling, SDK và instrumentation.
3. **Cập nhật tổ hợp đồng bộ:** Boot 4.2.x, Spring AI BOM 2.1.0, JDK và build plugin được hỗ trợ.
4. **Kiểm tra dependency resolution:** không còn module 2.0.x bị ép trực tiếp; phân tích mọi override.
5. **Kiểm tra chức năng:** khởi động context, ChatModel/provider, RAG retrieval, tool invocation, exception/retry.
6. **Kiểm tra quan sát:** endpoint metrics, các meter/span đã dự kiến, sampling, token usage và export path.
7. **Chạy lại dataset** trên cùng điều kiện và ghi kết quả; đánh dấu rõ nếu đồng thời đổi prompt/model/corpus.

Không kết luận “nâng BOM làm relevance tăng” chỉ từ một lần chạy có nhiều biến thay đổi. Cần so sánh có kiểm soát và phân biệt ảnh hưởng của nền tảng với stochasticity của model/evaluator.

### Quy tắc thay đổi một biến chính

Giả sử muốn đánh giá prompt P1 so với P2:

~~~text
Baseline A: Boot 4.2.0 + AI BOM 2.1.0 + model M + corpus C + prompt P1
Compare  B: Boot 4.2.0 + AI BOM 2.1.0 + model M + corpus C + prompt P2
~~~

Chỉ thay prompt để dễ quy kết tác động. Nếu đồng thời muốn nâng Spring AI, làm một thí nghiệm nền tảng riêng có changelog, rồi mới thử prompt.

## 11. Sự cố phổ biến và cách xử lý

| Hiện tượng | Khả năng gây ra | Kiểm tra/khắc phục |
|---|---|---|
 Import BOM nhưng thiếu `ChatModel` | BOM không tạo starter; thiếu model starter hoặc cấu hình provider | Xem `dependencies`, điều kiện auto-configuration, thông tin xác thực |
 Maven báo thiếu version cho artifact | Artifact chưa được BOM nào quản lý, import sai scope/type hoặc parent/child không kế thừa | Xem effective POM; xác nhận `<type>pom</type>` + `<scope>import</scope>` |
 `NoSuchMethodError`, `ClassNotFoundException` | Có module Spring AI/Boot SDK khác phiên bản tương thích | Xem dependency tree/insight, gỡ version override trái dòng |
 Boot 4.1 + AI BOM 2.1 | Lệch ma trận tương thích giữa hai release | Chọn Boot 4.2.x với AI 2.1 hoặc Boot 4.1.x với AI 2.0.x |
 Gradle resolve khác BOM mong đợi | `platform` chỉ khuyến nghị, có constraint/version mạnh hơn | Chạy `dependencyInsight`, kiểm tra resolution strategy và constraints |
 Maven parent công ty khiến plugin lỗi | Import Boot BOM không quản lý plugin build | Chốt compiler/test/Boot Maven plugin trong `pluginManagement` |
 Chạy trên IDE được nhưng CI lỗi | Java runtime/Wrapper/repository khác nhau | Kiểm tra JDK path, Wrapper, proxy/mirror và resolved graph |
 Có Actuator nhưng không có trace | Chưa cấu hình tracing exporter/collector, sampling hoặc chưa có request phù hợp | Xác minh tracing starter, backend, logs exporter và span |
 Mất metric sau nâng cấp | Instrumentation/semantic convention đổi hoặc nhánh chưa chạy | So sánh metrics thực tế, release notes, sampling và dashboard mapping |
 Chất lượng RAG giảm sau nâng BOM | Có thể thay API, index, prompt, model hoặc dữ liệu đồng thời | Cố định các biến, so sánh baseline và truy vết từng bước |

### Đừng khắc phục bằng cách thêm `version` ngẫu nhiên

Nếu lỗi xảy ra khi resolve dependency, việc ghi `<version>...</version>` bên cạnh từng starter hoặc ép `strictly` trong Gradle có thể che mất lỗi gốc. Hãy kiểm tra trước: **BOM đang là bản nào? Boot bản nào? Có những dependency override nào? Artifact thực tế được chọn là bản nào?** Sau khi biết nguyên nhân, mới quyết định sửa parent/BOM, exclude hoặc override có kiểm soát.

## 12. Bài thực hành có hướng dẫn

**Mục tiêu:** tạo hai cấu hình dependency hợp lệ và một tình huống xung đột có thể quan sát.

### Phần A — Cấu hình chuẩn

1. Tạo Maven hoặc Gradle project với Java 21, Boot 4.2.0, AI BOM 2.1.0 như ví dụ.
2. Thêm `spring-ai-starter-model-openai`, Actuator, `spring-ai-test` (test scope).
3. Chạy `dependency:tree` hoặc `dependencyInsight`; ghi Spring AI module versions và các dependency runtime chính.
4. Tạo ít nhất một test khởi động Spring context trong môi trường có cấu hình provider phù hợp; với kiểm thử offline, có thể dùng mock/test double theo API của release.
5. Lưu kết quả kiểm tra dependency graph cùng commit hash làm baseline.

**Điều kiện đạt:** tất cả Spring AI module được dùng thuộc cùng dòng 2.1.x dự kiến; không có phiên bản cũ bị ép ngoài chủ đích; build/test đạt trong môi trường đã cấu hình.

### Phần B — Tìm conflict có chủ đích

Trong một **nhánh thí nghiệm tạm**, thêm version `2.0.3` vào riêng `spring-ai-starter-model-openai` trong Maven (hoặc một explicit version/constraint xung đột tương ứng trong Gradle). Kiểm tra:

- POM/Gradle vẫn import BOM phiên bản gì?
- Resolved version thực tế của starter và module AI thay đổi thế nào?
- Khi bỏ override, dependency graph có trở về baseline không?
- Vì sao kết quả `compile` riêng lẻ chưa đủ chứng minh tính tương thích?

**Khôi phục cấu hình chuẩn sau thực hành** và không giữ nhánh cố ý lệch version trong baseline của ứng dụng.

### Phần C — Gắn với thí nghiệm chất lượng

Tạo manifest ngắn bên cạnh kết quả evaluation:

~~~yaml
experiment_id: rag-baseline-v1
java: "21"
spring_boot: "4.2.0"
spring_ai_bom: "2.1.0"
build_tool: "maven-wrapper"
dataset_revision: "qa-set-01"
prompt_revision: "prompt-01"
model_id: "provider-model-version"
embedding_model: "embedding-model-version"
index_revision: "corpus-snapshot-01"
metrics:
  - relevance
  - fact_check_pass_rate
  - tool_success_rate
  - latency_p95
  - input_output_tokens
~~~

Các giá trị `model_id`, `dataset_revision` và `index_revision` trong manifest là **chỗ điền dữ liệu thực tế**, không phải tên model đã được xác minh. Khi chạy lần mới, giữ nguyên những trường không thuộc phạm vi thay đổi và ghi lại sự khác biệt.

### Câu hỏi tự kiểm tra

1. Vì sao chỉ import `spring-ai-bom` chưa đủ để tự tạo một `ChatModel`?
2. Tại sao Spring AI BOM 2.1.0 không bảo đảm chạy an toàn với Boot 4.1?
3. Trong Maven, khác biệt giữa `<dependencyManagement>` và `<dependencies>` là gì?
4. Vì sao version khai báo trong `platform` của Gradle có thể khác version cuối cùng?
5. Nếu một module con nằm trong `<modules>` nhưng không kế thừa parent BOM, hệ quả nào có thể xảy ra?
6. Để so sánh p95 và fact checking qua hai lần nâng cấp, ngoài BOM còn phải chốt những điều kiện nào?

**Gợi ý trả lời:** (1) BOM quản lý version, không thêm dependency; (2) ma trận yêu cầu Boot 4.2; (3) quản lý version khác khai báo dependency thực dùng; (4) có conflict/constraints khác; (5) module con phải tự quản lý version hoặc kế thừa đúng parent; (6) cố định JDK, provider/model, prompt, dataset, corpus/index, workload, instrumentation và môi trường.

## 13. Checklist trước khi đưa vào dự án

- [ ] Version **Spring AI BOM** là release có chủ đích và tương thích với **Spring Boot**.
- [ ] BOM được import đúng ở Maven `dependencyManagement` hoặc Gradle `platform`/dependency-management plugin.
- [ ] Chỉ khai báo các starter/module cần thiết, để BOM quản lý version mặc định của chúng.
- [ ] Các module con dùng cùng chính sách version; không trộn API 2.0.x và 2.1.x ngoài chủ đích.
- [ ] Version build plugins, JDK và wrapper đã được chốt riêng.
- [ ] Đã xem **resolved dependency graph** sau mỗi thay đổi BOM/parent.
- [ ] Test scope, runtime scope và các tích hợp provider/vector store được phân biệt rõ.
- [ ] Metrics, traces, evaluator dataset và cấu hình model được ghi cùng baseline.
- [ ] Mọi override và quyết định nâng cấp có lý do, review và kiểm chứng regression.

## Tài liệu tham khảo

1. [Spring AI — Project Setup, nhánh 2.1](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/get-started/project-setup.html): Java/Boot requirements, Maven Central và cú pháp Spring AI BOM; trang nhánh snapshot có liên kết tới bản **2.1.0** ổn định.
2. [Spring AI — Releases/Compatibility Matrix](https://github.com/spring-projects/spring-ai): ma trận Spring AI 2.1.x ↔ Spring Boot 4.2.x, 2.0.x ↔ 4.1.x, 1.1.x ↔ 3.5.x.
3. [Spring AI — Modules and Starters](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/reference/modules.html): danh sách artifact Spring AI của dòng 2.1.
4. [Spring AI — PGvector](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/integrations/vector-stores/pgvector.html): starter `spring-ai-starter-vector-store-pgvector` và prerequisites.
5. [Spring Boot — Managing Dependencies (Gradle)](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html): import Boot BOM, `platform`, `enforcedPlatform` và plugin dependency-management.
6. [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): import BOM, dependency mediation, transitive dependencies và cách ưu tiên managed versions.
7. [Gradle — Platforms](https://docs.gradle.org/current/userguide/platforms.html) và [Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): native BOM constraints, `platform`/ `enforcedPlatform` và lockfiles.
8. [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/), [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html), [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): kiểm chứng tín hiệu metrics/traces sau khi thêm dependency.

> **Ghi nhớ:** Spring AI BOM giúp **đồng bộ phiên bản của các module Spring AI**. Để phép đánh giá relevance, fact checking, RAG/tool calling, latency và chi phí có thể tái lập, cần kết hợp BOM với **đúng dòng Spring Boot, dependency graph đã kiểm tra, JDK/build tool cố định và baseline thí nghiệm đầy đủ**.
