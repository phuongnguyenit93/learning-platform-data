# Chọn tổ hợp Java, Spring Boot và Spring AI tương thích

> **Chương:** Thiết lập dự án
>
> **Phạm vi:** Spring AI Evaluation & Observability — chuẩn bị môi trường để đánh giá relevance, fact checking, luồng RAG/tool calling và thu thập metrics, traces, token usage, chi phí, độ trễ theo từng phiên bản prompt/model/pipeline.
> **Mốc tham chiếu phiên bản:** 27/11/2026. Khi bắt đầu dự án sau thời điểm này, cần đối chiếu lại tài liệu phát hành chính thức.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **Java, Spring Boot và Spring AI phải được lựa chọn như một tổ hợp**, kể cả khi dự án biên dịch thành công.
2. Chọn được bộ phiên bản phù hợp cho dự án mới, dự án đang dùng Spring Boot 4.1 và dự án duy trì trên Spring Boot 3.5.
3. Quản lý phiên bản bằng **Spring Boot dependency management** và **Spring AI BOM**, đồng thời hiểu giới hạn trách nhiệm của từng bên.
4. Thiết lập Maven hoặc Gradle, model starter, Actuator, Micrometer và tracing để có nền tảng quan sát các request AI.
5. Kiểm chứng cả **build, khởi động, lời gọi model và tín hiệu observability**, rồi ghi lại phiên bản làm baseline cho các phép đánh giá chất lượng.

### Tình huống xuyên suốt

Một nhóm xây chatbot trả lời dựa trên tài liệu nội bộ. Nhóm muốn so sánh hai prompt, hai mô hình và hai cách truy xuất RAG. Mỗi lần chạy cần đo độ chính xác dựa trên ngữ cảnh, độ liên quan, số token, độ trễ và lỗi gọi công cụ. Nếu hôm nay build dùng một tổ hợp dependency còn ngày mai tự động kéo một tổ hợp khác, nhóm rất dễ nhầm lỗi tương thích hoặc thay đổi instrumentation thành sự cải thiện/suy giảm chất lượng mô hình.

Do đó, **lựa chọn và khóa bộ phiên bản là bước đầu tiên của một thí nghiệm có thể lặp lại**.

## 2. Ba lớp tương thích cần kiểm soát

| Lớp | Chức năng | Điều cần xác minh | Triệu chứng khi chọn sai |
|---|---|---|---|
| **Java/JDK** | Trình biên dịch, JVM và các API ngôn ngữ/runtime | Phiên bản JDK tối thiểu của Spring Boot/Spring AI, JDK chạy thực tế, Maven/Gradle toolchain | **UnsupportedClassVersionError**, lỗi toolchain hoặc bytecode |
| **Spring Boot** | Spring Framework, tự cấu hình bean, starters, lifecycle, Actuator, dependency management | Dòng Spring Boot được Spring AI hỗ trợ; tương thích với Gradle/Maven; starter phù hợp với Boot 4 | **NoSuchMethodError**, **ClassNotFoundException**, lỗi auto-configuration |
| **Spring AI** | ChatClient, model/vector-store adapters, advisor, evaluation, tool calling và AI observations | Dòng Spring AI tương ứng với Boot; BOM và các module đều cùng dòng; API thay đổi theo major/minor | Không tạo được ChatModel, lỗi runtime tại advisor/tool, thiếu hoặc đổi metric/span |

Tương thích có nhiều mức:

- **Biên dịch được**: mã nguồn và dependency giải quyết thành công.
- **Khởi động được**: Spring context tạo đủ bean, auto-configuration không xung đột.
- **Chạy đúng chức năng**: có thể gọi model, truy xuất dữ liệu và thực thi tool; tests xác nhận được kết quả.
- **Đo lường được**: metrics/traces phản ánh được các bước quan trọng của request và không rò rỉ dữ liệu nhạy cảm.
- **Tái lập được**: chạy lại cùng bộ nguồn, cấu hình, dependency, tập dữ liệu và mô hình để so sánh đáng tin cậy.

Không nên dùng một lần chạy thành công của **mvn package** hoặc **gradle build** làm bằng chứng duy nhất cho toàn bộ năm mức trên.

## 3. Chọn ma trận phiên bản

Tại mốc 27/11/2026, các dòng Spring AI ổn định và Spring Boot tương ứng có thể lựa chọn như sau:

| Trường hợp | Java nên dùng | Spring Boot | Spring AI | Quyết định |
|---|---|---|---|---|
| **Dự án mới về evaluation/observability** | **21 LTS** | **4.2.0** | **2.1.0** | **Bộ tham chiếu chính của bài học** |
| Dự án đang ở dòng Boot 4.1 | 17 hoặc 21; ưu tiên 21 nếu môi trường cho phép | **4.1.x**, chẳng hạn **4.1.3** | **2.0.x**, chẳng hạn **2.0.3** | Giữ cùng dòng hoặc lên đồng thời Boot 4.2 + AI 2.1 |
| Dự án hiện hữu ở dòng Boot 3.5 | 17 hoặc 21 | **3.5.x**, chẳng hạn **3.5.16** | **1.1.x** | Duy trì để giảm thay đổi; lên Boot 4/AI 2 phải có kế hoạch migration |

**Vì sao chọn Java 21?** Spring AI 2.1 và Spring Boot 4.2 yêu cầu **Java 17 trở lên**; Java 21 là lựa chọn LTS thuận tiện cho nhiều nhóm và công cụ vận hành. Java 17 vẫn hợp lệ theo baseline. JDK mới hơn có thể được Boot hỗ trợ, nhưng phải kiểm tra thêm thư viện phụ thuộc, plugin và môi trường triển khai; không mặc định “JDK càng mới càng tương thích”.

**Giới hạn quan trọng:**

- **Spring AI 2.1.x** dùng **Spring Boot 4.2.x**. Không ghép Spring AI 2.1 với Boot 4.1 chỉ vì cùng major 4.
- **Spring AI 2.0.x** thuộc dòng **Spring Boot 4.1.x** theo ma trận hiện hành của dự án; một số trang hướng dẫn cũ có thể mô tả hỗ trợ Boot 4.0.x. Khi có thông tin khác nhau, ưu tiên ma trận phát hành của đúng nhánh và release notes đang dùng.
- **Spring AI 1.1.x** dùng **Spring Boot 3.5.x**. Không áp dụng ngược mã hướng dẫn Boot 4 (ví dụ tên starter hoặc một số cấu hình tracing) cho nhánh này mà chưa kiểm tra.
- Các bản **SNAPSHOT**, **M** (milestone), **RC** (release candidate) phục vụ thử nghiệm tính năng. Với baseline cần lặp lại, ưu tiên bản **GA** và phiên bản patch xác định rõ.

Tài liệu Spring AI cũng ghi rõ Spring AI 2.1.0 được phát hành ngày **20/11/2026** trên nền **Spring Boot 4.2**; Spring Boot 4.2.0 được phát hành ngày **19/11/2026**. Vì vậy tổ hợp trong hàng đầu là lựa chọn có cơ sở tại thời điểm biên soạn.

### Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Bắt đầu dự án AI"] --> B{"Đang duy trì Boot 3.5?"}
    B -->|Có| C["Chọn Spring AI 1.1.x<br/>Giữ Boot 3.5.x"]
    B -->|Không| D{"Đang cố định Boot 4.1?"}
    D -->|Có| E["Chọn Spring AI 2.0.x<br/>Giữ Boot 4.1.x"]
    D -->|Không| F["Chọn Boot 4.2.x<br/>Spring AI 2.1.x"]
    C --> G["Chọn JDK được hỗ trợ"]
    E --> G
    F --> G
    G --> H["Khóa BOM, plugin, toolchain"]
    H --> I["Build + khởi động + kiểm tra metrics/traces"]
    I --> J["Ghi baseline để chạy evaluation"]
~~~

Không nhất thiết nâng mọi ứng dụng cũ ngay lập tức. Một bản nâng cấp major Spring Boot/Spring AI có thể kéo theo thay đổi Spring Framework, Jakarta/Jackson, auto-configuration, API memory hoặc tool calling. Tách việc nâng nền tảng và việc thay prompt/model thành **hai lần thay đổi đo riêng** sẽ giúp kết luận nguyên nhân chính xác hơn.

## 4. Spring Boot dependency management và Spring AI BOM

**BOM (Bill of Materials)** là tập quản lý phiên bản của một nhóm dependency. Thay vì viết phiên bản riêng trên mọi starter Spring AI, dự án khai báo một BOM rồi để dependency resolver chọn các phiên bản module đã được kiểm thử cùng nhau.

Hai cấp quản lý có vai trò khác nhau:

| Thành phần | Quản lý | Không nên kỳ vọng |
|---|---|---|
| Spring Boot parent POM hoặc **spring-boot-dependencies** BOM | Dependency nền Spring, Micrometer, Jackson, testing và nhiều thư viện hạ tầng | Tự chọn đúng Spring AI release cho ứng dụng |
| **org.springframework.ai:spring-ai-bom** | Phiên bản các module/starter nằm trong hệ Spring AI | Tự đổi Spring Boot từ 4.1 lên 4.2, hoặc tự thay JDK/Gradle |
| Java toolchain và Maven/Gradle plugin | Phiên bản JDK biên dịch, quá trình đóng gói/chạy build | Bảo đảm mọi integration bên thứ ba tương thích runtime |

Trong một nhánh dự án, giữ **một phiên bản Spring AI BOM nhất quán**. Không viết trực tiếp bản 2.0.x cho model starter nhưng dùng bản 2.1.x cho vector-store starter nếu không có lý do và kiểm thử cụ thể. Một số lỗi phát sinh không ở source code mà ở class được gọi trong bytecode hoặc cấu trúc bean thay đổi giữa hai dòng.

**Một quy tắc thực hành:** đặt phiên bản **Spring Boot** ở Spring Boot parent/plugin, phiên bản **Spring AI** ở BOM, JDK ở toolchain. Để các starter được quản lý phiên bản tự động, chỉ override khi thực sự cần và đã xác minh tác động.

## 5. Thiết lập mẫu với Maven

Ví dụ sau dùng **Java 21 + Spring Boot 4.2.0 + Spring AI 2.1.0**, bổ sung web endpoint đơn giản và các dependency cần thiết để quan sát lời gọi AI. Mã mẫu chọn OpenAI làm provider để minh họa dependency; bạn có thể thay bằng Ollama hoặc provider phù hợp mà không thay đổi nguyên tắc ma trận phiên bản.

**pom.xml**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>ai-evaluation-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.2.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.ai</groupId>
                <artifactId>spring-ai-bom</artifactId>
                <version>2.1.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <!-- REST endpoint thử nghiệm -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>

        <!-- AI model starter; thay theo provider được chọn -->
        <dependency>
            <groupId>org.springframework.ai</groupId>
            <artifactId>spring-ai-starter-model-openai</artifactId>
        </dependency>

        <!-- Health, metrics, observations -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>

        <!-- Xuất Prometheus metrics -->
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
        </dependency>

        <!-- Traces qua OpenTelemetry/OTLP; cần collector để nhận dữ liệu -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-opentelemetry</artifactId>
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

**Phân tích cấu hình:**

1. **spring-boot-starter-parent:4.2.0** cố định dòng Spring Boot cho build Maven, plugin và dependency management của Boot.
2. **java.version = 21** thống nhất mức Java biên dịch; JDK chạy chương trình vẫn cần được xác minh trong CI/container.
3. **spring-ai-bom:2.1.0** đặt phiên bản cho Spring AI modules; không thêm version lẻ vào **spring-ai-starter-model-openai**.
4. **spring-boot-starter-actuator** tạo hạ tầng metrics/health. **micrometer-registry-prometheus** cho phép xuất metrics qua endpoint Prometheus khi được expose.
5. **spring-boot-starter-opentelemetry** bật tracing dựa trên Micrometer Tracing/OpenTelemetry và cấu hình export OTLP của Spring Boot 4. Để xem span, cần hệ thống thu thập tracing (OpenTelemetry Collector/Jaeger/Tempo hoặc dịch vụ tương đương).

Spring AI có thể phát sinh observations cho ChatClient, ChatModel, Advisors, tool calling và VectorStore khi thành phần tương ứng thực sự được gọi. **Thêm Actuator chưa có nghĩa đã tạo ra trace có thể quan sát trên backend**: cần tracer, cấu hình export, sampling và request chạy thật.

### Vì sao dùng starter khác ở Spring Boot 4?

Spring Boot 4 tổ chức lại một số module/starter. Với Spring MVC, ví dụ trên dùng **spring-boot-starter-webmvc**. Khi mang một đoạn cấu hình cũ từ Boot 3 sang Boot 4, cần kiểm tra starter hiện hành thay vì chỉ thay chữ số phiên bản ở parent.

### Khi nào cần module RAG hoặc evaluation?

Bài này mới chọn **nền dependency có thể chạy và đo được**. Khi học retrieval, bổ sung vector store starter tương ứng (ví dụ PostgreSQL/PGvector, Redis, Qdrant...) theo đúng tài liệu của Spring AI 2.1. Khi học relevance hoặc fact checking, dùng evaluation API và test dependencies phù hợp cho release đã chốt. Chưa cần lắp toàn bộ provider/vector-store trên classpath trong bước chọn phiên bản; mỗi integration thêm vào có thể tạo bean và rủi ro xung đột riêng.

## 6. Thiết lập tương đương với Gradle

Với Gradle, dùng **Java toolchain** để máy lập trình và CI không phụ thuộc vào JDK ngẫu nhiên đang được trỏ bởi IDE. Ví dụ **build.gradle** dưới đây sử dụng **Gradle native platform** để import cả Spring Boot BOM và Spring AI BOM:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.2.0')
    implementation platform('org.springframework.ai:spring-ai-bom:2.1.0')

    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.ai:spring-ai-starter-model-openai'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-opentelemetry'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Lưu ý:

- Spring Boot 4.2 hỗ trợ **Gradle 8.14+ trong dòng 8.x** và **Gradle 9.x** theo tài liệu hệ thống; dùng **Gradle Wrapper** để dự án và CI chạy cùng bản Gradle.
- Đây là một cách import BOM với **Gradle native platform**. Nếu dự án dùng plugin **io.spring.dependency-management**, hãy chọn một chiến lược quản lý dependency rõ ràng và kiểm tra **dependencyInsight** để tránh override khó phát hiện.
- **implementation platform(...)** áp dụng version constraints theo dependency graph. Khi tách thêm Gradle subproject, phải khai báo BOM/constraints cho các module hoặc cấu hình kế thừa phù hợp; BOM ở project A không tự động quản lý project B.

### Maven hay Gradle?

Chọn công cụ nhóm đang sử dụng ổn định, có wrapper và quy trình CI rõ ràng. Với đánh giá chất lượng AI, yếu tố quan trọng nhất không nằm ở tên build tool mà ở khả năng **lặp lại đúng dependency graph, JDK, test và instrumentation** giữa các lần chạy.

## 7. Cấu hình runtime tối thiểu cho AI observability

Ví dụ **src/main/resources/application.yml** sau dùng với tổ hợp Spring Boot 4.2/Spring AI 2.1. Chỉ định API key qua biến môi trường; model minh họa có thể đổi theo tài khoản/provider.

~~~yaml
spring:
  application:
    name: ai-evaluation-lab
  ai:
    openai:
      api-key: ${OPENAI_API_KEY}
      chat:
        options:
          model: ${OPENAI_CHAT_MODEL:gpt-4.1-mini}
    chat:
      client:
        observations:
          log-prompt: false
          log-completion: false

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"
  tracing:
    sampling:
      probability: 1.0   # Chỉ nên dùng cho môi trường thử nghiệm
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: ${OTEL_TRACES_URL:http://localhost:4318/v1/traces}
~~~

**Các điểm cần hiểu rõ:**

- **spring.ai.openai.api-key** là bí mật; đặt trong environment/secrets manager, tuyệt đối không commit giá trị thật vào bài test, source hoặc log.
- **sampling.probability: 1.0** giúp thu đủ trace trong môi trường lab có lưu lượng thấp. Môi trường thật cần điều chỉnh sampling theo khối lượng và chi phí; mặc định Spring Boot không nhất thiết lấy mẫu 100%.
- **OTEL_TRACES_URL** là địa chỉ OTLP HTTP của collector/backend có thật. Nếu chưa chạy collector, metrics có thể hoạt động nhưng trace chưa hiển thị trên dashboard; exporter có thể thông báo lỗi kết nối.
- **log-prompt/log-completion: false** ngăn việc chủ động thêm toàn bộ nội dung chat vào observations. Ngoài cấu hình Spring AI, phải kiểm soát log của provider SDK, gateway và công cụ quan sát.
- **exposure** chỉ nên mở cho môi trường phát triển hoặc mạng quản trị thích hợp. Endpoint metrics/prometheus có thể tiết lộ thông tin vận hành.

### Endpoint thử nghiệm nhỏ nhất

~~~java
package com.example.aievaluationlab;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AiEvaluationLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(AiEvaluationLabApplication.class, args);
    }
}

record QuestionRequest(String question) {}

@RestController
@RequestMapping("/api")
class QuestionController {
    private final ChatClient chatClient;

    QuestionController(ChatClient.Builder builder) {
        this.chatClient = builder.build();
    }

    @PostMapping("/ask")
    String ask(@RequestBody QuestionRequest request) {
        return chatClient.prompt()
                .user(request.question())
                .call()
                .content();
    }
}
~~~

Trong ví dụ, **ChatClient.Builder** được auto-configure khi có một **ChatModel** phù hợp từ starter. Với nhiều ChatModel được đăng ký, cần lựa chọn bean rõ ràng theo cấu hình của dự án; lỗi có thể không liên quan tới độ tương thích phiên bản.

Đây là endpoint để **kiểm chứng hạ tầng**, chưa phải phép đo accuracy hay kiểm thử RAG. Để chấm relevance/factuality, cần thêm tập câu hỏi, ngữ cảnh chuẩn, tiêu chí chấm và pipeline truy xuất/tool tương ứng.

## 8. Kiểm chứng tổ hợp: từ JDK đến trace

Thực hiện tuần tự trên máy phát triển và ít nhất một môi trường CI sạch.

### Bước 1 — Kiểm tra công cụ thực sự đang chạy

~~~bash
java -version
./mvnw -version
# Nếu dùng Gradle:
./gradlew --version
~~~

Trong PowerShell trên Windows, có thể dùng **mvnw.cmd** hoặc **gradlew.bat** thay cho script Unix. Kiểm tra output có đúng **Java 21**, đúng Maven/Gradle Wrapper và đúng đường dẫn JVM. Lệnh **java -version** trong terminal có thể khác Java SDK mà IDE đang dùng.

### Bước 2 — Xác nhận dependency graph và BOM

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom

# Hoặc với Gradle:
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-ai --configuration runtimeClasspath
~~~

Khi đọc kết quả, đối chiếu:

- Spring Boot artifacts thuộc dòng **4.2.x**.
- Các Spring AI starter/module thuộc dòng **2.1.x** (với ví dụ trong bài là **2.1.0**).
- Không có module Spring AI **1.x/2.0.x** bị kéo vào ngoài ý muốn.
- Không có Spring Framework/Jackson/Micrometer được override thủ công thiếu chủ đích.
- Không phải project chỉ build thành công nhờ cache local trong khi CI không lấy được artifact từ Maven Central.

Lệnh **help:effective-pom** của Maven và **dependencies/dependencyInsight** của Gradle là công cụ để kiểm tra kết quả resolve; chúng không thay thế việc chạy ứng dụng.

### Bước 3 — Build và chạy kiểm thử tối thiểu

~~~bash
./mvnw clean verify
./mvnw spring-boot:run

# Hoặc Gradle:
./gradlew clean test bootRun
~~~

Trong một dự án thật, nên chạy **test** và **bootRun** thành các lệnh riêng để thấy rõ lỗi nào xuất hiện trong build, lỗi nào khi khởi động. Với API key chưa được cấp, phép gọi OpenAI sẽ không hoạt động; lỗi xác thực provider cần được phân biệt với lỗi Spring context hoặc dependency.

### Bước 4 — Kiểm tra health, một request thật, metrics

~~~bash
curl http://localhost:8080/actuator/health

curl -X POST http://localhost:8080/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Hãy trả lời ngắn: RAG là gì?"}'

curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/prometheus
~~~

Nếu response từ model trả về thành công, kiểm tra metrics sau khi request kết thúc. Các tên quan sát Spring AI có thể gồm:

| Thành phần | Observation/metric đại diện | Mục đích |
|---|---|---|
| ChatClient | **spring.ai.chat.client** / các series **gen_ai_chat_client_operation_...** | Thời gian đi qua client/advisor pipeline |
| ChatModel | **gen_ai.client.operation** | Thời gian gọi nhà cung cấp model, nhãn provider/model |
| Token usage | **gen_ai.client.token.usage** | Tổng token input/output/total do provider báo về |
| Tool calling | **spring.ai.tool** | Biết tool nào được gọi, thành công/lỗi và thời lượng |
| VectorStore | **db.vector.client.operation** | Độ trễ query/add/upsert/delete của kho vector |

**Chú ý cách đọc:** tên observation trong code/Actuator có thể khác tên time series sau khi được Prometheus chuẩn hóa (ví dụ dấu chấm thành dấu gạch dưới, bổ sung hậu tố **_seconds_count**). Metric chỉ xuất hiện khi luồng tương ứng có chạy; chỉ gửi chat thuần thì không có lý do xuất hiện metric vector query hoặc tool calling.

### Bước 5 — Xem trace end-to-end

Khi collector/backend OTLP đang hoạt động, mở một request **/api/ask** và kiểm tra trace cùng correlation ID của nó:

~~~text
HTTP POST /api/ask
  └─ ChatClient request
      ├─ Advisor(s), nếu có
      ├─ VectorStore query, nếu chạy RAG
      ├─ ChatModel invocation
      └─ Tool execution, nếu model yêu cầu gọi tool
~~~

Sơ đồ biểu diễn **luồng mục tiêu**; cây span thực tế tùy cách gọi API, tính đồng bộ/bất đồng bộ, provider, starter và phiên bản instrumentation. Nếu không thấy span con, kiểm tra sampling, context propagation, cấu hình exporter và liệu nhánh chương trình đó có thực sự chạy.

Với tracing, câu hỏi quan trọng không chỉ là “có trace hay chưa” mà còn là “có thể quy thời gian về đúng bước nào không?”. Đây là cơ sở phân biệt chậm do retrieve, chậm do model, chậm do tool hay overhead nội bộ.

## 9. Tổ hợp phiên bản tác động thế nào đến evaluation và observability?

Spring AI Evaluation & Observability có hai nhóm tín hiệu khác nhau:

**Chất lượng đầu ra (evaluation):**

- **Relevance**: câu trả lời có liên quan câu hỏi và ngữ cảnh truy xuất không?
- **Fact checking / groundedness**: phát biểu có được tài liệu nguồn hỗ trợ không?
- **Độ đúng luồng RAG**: tài liệu phù hợp có được lấy về, metadata/filter có đúng, thông tin được trích có đủ?
- **Độ đúng tool calling**: gọi đúng tool, đúng tham số, xử lý lỗi và giới hạn quyền?

**Vận hành (observability):**

- **Latency**: thời gian end-to-end và theo từng đoạn; phân phối **p50/p95/p99** với đủ mẫu.
- **Token/chi phí**: token input/output, token cache nếu provider báo về, đơn giá theo model và thời điểm.
- **Độ tin cậy**: tỷ lệ lỗi, timeout, retry, lỗi vector DB và external tools.
- **Trace**: liên kết request với advisor, retriever, model, tool và các dịch vụ liên quan.

Tổ hợp phiên bản có thể ảnh hưởng đến **cả hai**:

| Thay đổi | Ảnh hưởng có thể xảy ra | Cách kiểm soát |
|---|---|---|
| Nâng Spring AI 2.0 → 2.1 | API/session/tool calling, instrumentation hoặc metadata response có thể đổi | Đọc upgrade notes; chạy lại regression trên cùng dataset, prompt, model |
| Nâng Spring Boot | Thay đổi auto-configuration, Micrometer/tracing/exporter | Kiểm tra dependency graph, endpoint, span, dashboard |
| Thay JDK | Garbage collection, runtime performance, thread scheduling có thể thay đổi | Ghi JDK thực tế; so sánh latency trong môi trường tương đương |
| Thay model hoặc cấu hình generation | Chất lượng, token usage và độ trễ đổi | Cố định model ID/version khi có thể, temperature và giới hạn tokens |
| Thay embedding/vector store | Retrieval quality, kết quả top-k và latency thay đổi | Cố định embedding model, dimension, corpus/chunking, index version |

**Đặc biệt:** một request “200 OK” không chứng minh câu trả lời là đúng. Metrics và traces cho biết hành trình và hiệu năng; **evaluation dataset cùng tiêu chí chấm** mới giúp đánh giá chất lượng. Mặt khác, kết quả relevance tốt không chứng minh pipeline đáp ứng latency/cost mục tiêu.

### Mẫu biên bản baseline cho một lần chạy

| Nhóm thông tin | Ví dụ ghi nhận |
|---|---|
 Platform | JDK **21**, Spring Boot **4.2.0**, Spring AI **2.1.0**, Maven/Gradle Wrapper version |
 Source | Git commit, phiên bản cấu hình build và artifact/container digest |
 Experiment | Dataset version, evaluator/rubric version, prompt template revision |
 Model | Provider, model ID, generation parameters, ngày chạy, cấu hình API |
 RAG/tool | Embedding model, vector index/corpus snapshot, top-k, filters, tool schema revision |
 Observability | Sampling rate, collector/backend version, tên metric và retention |
 Kết quả | Relevance, fact-check pass rate, tool success rate, latency p50/p95, tokens/request, chi phí ước tính |

Không gắn **user ID, câu hỏi nhạy cảm hoặc toàn văn prompt** vào metric label có cardinality thấp. Traces/logs nếu chứa ngữ cảnh hoặc nội dung model phải được kiểm soát quyền truy cập và thời gian lưu. Token usage là **lượng token nhà cung cấp trả về hoặc phép đo có hỗ trợ**; chi phí cần phép tính thêm với giá theo model, chưa thể suy ra tự động từ một con số latency.

## 10. Lỗi thường gặp và cách khoanh vùng

| Biểu hiện | Nguyên nhân cần nghĩ đến | Hướng xử lý |
|---|---|---|
 **UnsupportedClassVersionError** | JVM chạy có bytecode level thấp hơn bản đã build | Kiểm tra **java -version** ở IDE, CI, Docker và runtime; thống nhất JDK/toolchain |
 **NoSuchMethodError** hoặc **NoClassDefFoundError** | Runtime trộn version Spring Framework, Boot, AI hoặc thư viện transitive | Xem Maven dependency tree/Gradle dependencyInsight; loại bỏ override ngoài ý muốn |
 Không có **ChatClient.Builder** hoặc ChatModel bean | Thiếu starter, cấu hình provider sai hoặc tồn tại nhiều model beans | Kiểm tra starter chính xác, auto-configuration conditions và cấu hình API |
 Dùng mã starter đời cũ mà không khởi động được | Mẫu hướng dẫn dành cho Spring AI 1.0/Boot 3 | Đối chiếu tên starter hiện tại; ví dụ **spring-ai-starter-model-openai** |
 **/actuator/prometheus** trả 404 | Thiếu registry hoặc chưa expose endpoint | Kiểm tra Actuator, **micrometer-registry-prometheus**, cấu hình exposure |
 Có metrics nhưng không thấy trace | Chưa có tracing starter/collector, sampling hoặc endpoint OTLP sai | Kiểm tra **spring-boot-starter-opentelemetry**, exporter và collector |
 Không thấy metric token hoặc tool/vector | Provider không trả usage hoặc code chưa đi qua nhánh tương ứng | Gọi một request đủ điều kiện, kiểm tra model integration và phiên bản tài liệu |
 Metrics bị tăng đột ngột sau nâng cấp | Instrumentation, tên meter hoặc đơn vị/nhãn thay đổi | So sánh semantic convention, dashboards, số liệu trước/sau trên cùng workload |
 Kết quả quality lệch bất thường | Prompt/model/corpus đổi cùng lúc với dependency | Đối chiếu baseline manifest; tách từng yếu tố và chạy lại dataset chuẩn |

### Một ví dụ chẩn đoán

Giả sử nhóm thay Spring AI 2.0.3 bằng 2.1.0 nhưng giữ Boot 4.1.3. Maven vẫn có thể resolve dependency, song khi khởi động xuất hiện lỗi bean hoặc method. Hướng xử lý đúng là **đối chiếu ma trận tương thích và nâng Boot lên 4.2.x đồng bộ với AI 2.1.x**, sau đó kiểm tra lại dependency graph và request thật. Không nên kết luận prompt mới “làm chatbot chậm” khi hạ tầng đang ở tổ hợp chưa được hỗ trợ.

## 11. Quy trình lựa chọn cho dự án thực tế

1. **Xác định mục tiêu:** tạo mới hay duy trì; cần RAG, evaluation, tool calling, tracing, Prometheus hay chỉ chạy thử.
2. **Chọn dòng Spring AI theo Boot:** dùng bảng chính thức của đúng release; nếu giữ Boot 3.5, chọn AI 1.1.x; nếu dự án mới, dùng AI 2.1/Boot 4.2 tại mốc bài viết.
3. **Chốt JDK/toolchain:** ưu tiên Java 21 cho lab; kiểm tra JDK của CI/container và phiên bản build tool hỗ trợ.
4. **Khai báo BOM và starters:** import Boot dependency management cùng Spring AI BOM; chỉ thêm các model, store, Actuator và tracing thực sự cần.
5. **Kiểm chứng:** compile, test, startup, một model call, Actuator metrics, OTLP trace; nếu có RAG/tool thì kiểm tra riêng từng nhánh.
6. **Lưu baseline:** ghi phiên bản, dataset, model, prompt, index và cấu hình quan sát; đo latency/cost/quality với điều kiện nhất quán.
7. **Nâng cấp có kiểm soát:** đọc release/upgrade notes, thay một nhóm biến mỗi lần và chạy regression trước khi so sánh với baseline.

### Checklist tự kiểm tra

- [ ] Tôi biết rõ phiên bản **JDK runtime**, không chỉ cấu hình source compatibility.
- [ ] Spring AI và Spring Boot nằm trên **hai dòng được công bố tương thích**.
- [ ] Tôi dùng BOM và không vô tình trộn nhiều phiên bản Spring AI.
- [ ] Model starter, vector-store starter (nếu có) và API sử dụng khớp release.
- [ ] Một lời gọi AI chạy được và có ít nhất metrics phù hợp sau request.
- [ ] Khi cần tracing, collector hoạt động và trace có thể tương quan với request.
- [ ] Tôi có **baseline** để phân biệt thay đổi framework với thay đổi prompt/model/pipeline.

## 12. Câu hỏi tự luyện

1. Dự án đang chạy Spring Boot **3.5.x** và chưa có kế hoạch migration. Bạn chọn dòng Spring AI nào? Vì sao không chỉ thay AI lên 2.1?
2. Spring AI BOM giải quyết phần nào của dependency graph? Nó có tự đổi phiên bản Spring Boot parent hay không?
3. Tại sao đã gọi thành công endpoint chatbot vẫn có thể không thấy **db.vector.client.operation**?
4. Một nhóm báo “sau nâng cấp, p95 tăng 25% nhưng relevance tăng 4 điểm”. Bạn cần thu thập những thông tin nào trước khi quy kết do model?
5. Trình bày ba kiểm tra độc lập chứng minh dự án không chỉ biên dịch được mà còn sẵn sàng cho **evaluation và observability**.

**Gợi ý đối chiếu:** (1) AI 1.1.x cho Boot 3.5.x; (2) BOM quản lý các module AI, Boot do dependency management riêng quản lý; (3) chưa chạy vector query hoặc không có instrumentation phù hợp; (4) phải giữ nguyên dataset, prompt, model, index, workload và kiểm tra dependency/instrumentation; (5) dependency graph + request thực tế + metrics/traces + baseline.

## Tài liệu tham khảo chính thức

- [Spring AI — Project Setup, phiên bản 2.1](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/get-started/project-setup.html): yêu cầu Java/Boot và cách dùng BOM (nội dung chuẩn cho dòng 2.1; khi sử dụng thực tế chọn trang phiên bản GA).
- [Spring AI — Releases và ma trận tương thích trong repository chính thức](https://github.com/spring-projects/spring-ai): bảng Spring AI 2.1.x ↔ Boot 4.2.x, 2.0.x ↔ Boot 4.1.x và 1.1.x ↔ Boot 3.5.x.
- [Spring AI 2.1.0 GA — thông báo ngày 20/11/2026](https://spring.io/blog/2026/11/20/spring-ai-2-1-0-GA-available-now/): baseline Spring Boot 4.2 và lưu ý nâng cấp.
- [Spring Boot 4.2 — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): JDK, Maven và Gradle được hỗ trợ.
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): metric/span của ChatClient, ChatModel, Advisor, tool calling và VectorStore.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) và [Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Actuator, Prometheus, Micrometer Tracing và OTLP.
- [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): các khái niệm RelevancyEvaluator và FactCheckingEvaluator; kiểm tra API chính xác theo release trước khi viết code.

> **Kết luận học tập:** Chốt **Java + Spring Boot + Spring AI + BOM + instrumentation** như một đơn vị phiên bản. Chỉ bắt đầu so sánh relevance, fact checking, RAG/tool calling, tokens, chi phí và độ trễ sau khi đơn vị đó đã được kiểm chứng và ghi làm baseline.
