# Chọn tổ hợp Java, Spring Boot và Spring AI tương thích

Một dự án Spring AI chỉ khởi động ổn định khi JDK, Spring Boot, Spring AI và công cụ build cùng nằm trong các phiên bản được hỗ trợ. Chọn riêng phiên bản mới nhất cho từng thành phần có thể tạo ra một tổ hợp không tương thích: Maven hoặc Gradle không phân giải được dependency, ứng dụng lỗi khi khởi động, hoặc API trong ví dụ không tồn tại ở phiên bản đang cài.

Với module `SPRING_AI_TOOL_CALLING`, cấu hình dự án cần đáp ứng hai mục tiêu. Thứ nhất, các thư viện phải tương thích để ứng dụng Java khởi động và gọi được chat model. Thứ hai, model provider và model cụ thể phải hỗ trợ tool calling để mô hình có thể yêu cầu ứng dụng thực thi các phương thức nghiệp vụ. Việc thêm một starter chỉ kết nối ứng dụng với provider; nó không tự bảo đảm model đang chọn có khả năng gọi công cụ.

## Bốn thành phần cần chọn cùng nhau

Khi tạo dự án, hãy xem xét bốn lớp phiên bản sau:

| Thành phần | Vai trò | Cần kiểm tra |
|---|---|---|
| Java Development Kit (JDK) | Biên dịch và chạy ứng dụng | Phiên bản tối thiểu mà Spring Boot và các thư viện yêu cầu; JDK được dùng bởi IDE, terminal và CI |
| Spring Boot | Nền tảng ứng dụng, auto-configuration và quản lý dependency nền | Nhánh Spring Boot được Spring AI hỗ trợ; phiên bản Spring Framework và build tool đi kèm |
| Spring AI | API chat, model provider, tool calling và các tích hợp AI | Nhánh Spring Boot tương thích, BOM, artifact/starter và thay đổi API giữa các phiên bản |
| Maven hoặc Gradle | Phân giải dependency, biên dịch, kiểm thử và đóng gói | Phiên bản build tool được Spring Boot hỗ trợ và wrapper được commit cùng dự án |

Ngoài bốn thành phần này, cần chọn model provider phù hợp với môi trường. Ví dụ, dự án có thể dùng OpenAI, Anthropic, Google, Amazon Bedrock hoặc Ollama. Mỗi provider có starter và cấu hình riêng; khả năng tool calling cũng cần được xác nhận ở cấp provider và model.

## Ma trận tương thích phiên bản

Các nhánh Spring AI có thể yêu cầu các nhánh Spring Boot khác nhau. Theo tài liệu Spring AI và Spring Boot được kiểm tra ngày **27/11/2026**, có thể dùng ma trận tham khảo sau:

| Nhánh Spring AI | Nhánh Spring Boot tương thích được tài liệu nêu | Yêu cầu Java tối thiểu |
|---|---|---|
| 2.1.x | 4.2.x | Java 17 trở lên |
| 2.0.x | 4.0.x và 4.1.x | Java 17 trở lên |
| 1.0.x | 3.4.x và 3.5.x | Java 17 trở lên |

Với dự án mới theo phiên bản ổn định hiện hành tại thời điểm kiểm tra, có thể bắt đầu bằng **Java 21, Spring Boot 4.2.0 và Spring AI 2.1.0**. Java 17 là mức tối thiểu theo yêu cầu của các nhánh Spring Boot tương ứng; Java 21 được dùng trong ví dụ để tạo một cấu hình JDK hiện đại, đồng thời vẫn nằm trên mức tối thiểu được hỗ trợ.

Nếu dự án hiện hữu đang dùng Spring Boot 4.0.x hoặc 4.1.x, hãy chọn Spring AI 2.0.x theo tài liệu tương ứng. Nếu dự án vẫn ở Spring Boot 3.4.x hoặc 3.5.x, hãy chọn release Spring AI 1.x có tài liệu xác nhận tương thích với nhánh Boot đó. Không nâng riêng Spring AI lên 2.x trong khi giữ nguyên Spring Boot 3.x. Khi chọn một patch release cụ thể, luôn kiểm tra lại trang Project Setup và upgrade notes của đúng release; ma trận có thể thay đổi khi có bản phát hành mới.

Spring Boot 4.2.0 yêu cầu tối thiểu Java 17, hỗ trợ Maven 3.6.3 trở lên và Gradle 8.x từ 8.14 trở lên hoặc Gradle 9.x. Các tích hợp bên thứ ba có thể có yêu cầu cao hơn, vì vậy hãy kiểm tra tài liệu của model provider và các thư viện bổ sung mà dự án sử dụng.

## Chọn phiên bản bằng Spring Initializr

Với dự án mới, Spring Initializr tại [start.spring.io](https://start.spring.io) giúp tạo bộ khung build đúng theo các lựa chọn đã khai báo. Một cấu hình khởi đầu cho module này gồm:

1. Chọn Maven hoặc Gradle theo chuẩn của nhóm phát triển. Nếu dự án chưa có quy ước, cả hai đều phù hợp; hãy ưu tiên công cụ mà nhóm có kinh nghiệm vận hành và đã dùng trong CI.
2. Chọn Java 21 hoặc một JDK được nhánh Spring Boot đã chọn hỗ trợ. Kiểm tra cả phiên bản JDK đang chạy ứng dụng lẫn phiên bản dùng để biên dịch.
3. Chọn Spring Boot 4.2.x khi dùng Spring AI 2.1.x.
4. Thêm Spring Web nếu ứng dụng cần cung cấp HTTP endpoint.
5. Chọn đúng tích hợp model provider cần dùng, chẳng hạn OpenAI. Chỉ thêm các starter thực sự cần thiết để tránh kéo theo thư viện không sử dụng.
6. Tải project, mở bằng IDE và kiểm tra build wrapper trước khi bắt đầu viết công cụ nghiệp vụ.

Spring Initializr là điểm khởi đầu hữu ích, nhưng không thay thế việc đọc compatibility matrix. Nếu phải thêm Spring AI vào một dự án có sẵn, hãy giữ nguyên cấu trúc build hiện tại và bổ sung BOM cùng starter tương ứng theo tài liệu Spring AI.

## Quản lý dependency bằng BOM

Spring Boot và Spring AI cung cấp hai BOM có trách nhiệm khác nhau:

- `spring-boot-dependencies` quản lý các dependency thuộc hệ sinh thái Spring Boot và các thư viện nền mà Boot kiểm soát.
- `spring-ai-bom` quản lý các module và starter Spring AI theo cùng một release.

BOM (Bill of Materials) là tập hợp các quy tắc quản lý phiên bản dependency. Khi import BOM, build tool có thể chọn phiên bản đã được kiểm thử cùng release mà không phải khai báo version riêng cho từng artifact. Điều này đặc biệt hữu ích khi dự án dùng nhiều module Spring AI như chat model, embedding, vector store và tool calling.

Không nên khai báo các module Spring AI ở nhiều version khác nhau hoặc tự nâng riêng một dependency nền mà Spring Boot đang quản lý, trừ khi có lý do tương thích đã được kiểm chứng. Việc override tùy tiện có thể tạo ra lỗi runtime như `NoSuchMethodError`, `ClassNotFoundException` hoặc lỗi auto-configuration.

### Ví dụ Maven

Ví dụ dưới đây dùng Spring Boot 4.2.0, Spring AI 2.1.0 và starter OpenAI. Nếu dùng provider khác, thay starter OpenAI bằng starter tương ứng trong tài liệu tích hợp của provider đó.

```xml
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
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.ai</groupId>
        <artifactId>spring-ai-starter-model-openai</artifactId>
    </dependency>
</dependencies>
```

Ở đây, Spring Boot parent cung cấp dependency management và cấu hình build mặc định của Boot. Spring AI BOM quản lý version của starter AI. Hai version được khai báo một lần ở đầu cấu hình, giúp nâng cấp có chủ đích và dễ review hơn.

Nếu dự án không dùng `spring-boot-starter-parent`, có thể import `org.springframework.boot:spring-boot-dependencies` bằng `dependencyManagement` tương tự, sau đó import `spring-ai-bom`. Không import nhiều BOM có quy tắc xung đột mà không kiểm tra thứ tự ưu tiên và dependency tree.

### Ví dụ Gradle Groovy DSL

Với Gradle, có thể import BOM bằng native platform support:

```groovy
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

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.ai:spring-ai-starter-model-openai'
}
```

Boot BOM quản lý các dependency Spring Boot; Spring AI BOM quản lý các artifact AI. `java.toolchain` yêu cầu Gradle dùng JDK 21 để biên dịch, ngay cả khi JDK mặc định của terminal hoặc IDE khác. Hãy bảo đảm máy build có thể tải đúng JDK toolchain hoặc đã cài JDK phù hợp.

Nếu dự án dùng Kotlin DSL (`build.gradle.kts`), cú pháp sẽ khác đôi chút nhưng nguyên tắc import `platform(...)` và chọn một version cho mỗi BOM vẫn giữ nguyên.

## Chọn starter theo model provider

Spring AI tách tích hợp model theo provider. Starter đưa auto-configuration và dependency cần thiết vào ứng dụng. Chỉ thêm starter của provider mà ứng dụng thực sự sử dụng.

| Nhu cầu | Ví dụ starter | Việc cần xác minh |
|---|---|---|
| Dùng OpenAI | `spring-ai-starter-model-openai` | API key, model được chọn và khả năng tool calling của model |
| Dùng Ollama | `spring-ai-starter-model-ollama` | Phiên bản Ollama, model đã tải và khả năng tool calling của model đó |
| Dùng provider khác | Starter do Spring AI công bố cho provider đó | Tên artifact, cấu hình kết nối, xác thực và các tính năng được hỗ trợ |

Không trộn tên artifact của các release khác nhau. Spring AI đã thay đổi cách đặt tên một số starter và module qua các phiên bản lớn; vì vậy hãy sao chép dependency từ tài liệu đúng nhánh, không lấy nguyên cấu hình của một bài hướng dẫn cũ rồi ghép vào BOM mới.

Đối với tool calling, cần xác minh thêm ba điều:

1. Provider tích hợp trong phiên bản Spring AI đã chọn có hỗ trợ tool calling.
2. Model cụ thể đang cấu hình có hỗ trợ chức năng gọi công cụ theo API mà provider cung cấp.
3. Tài khoản, endpoint hoặc chế độ triển khai đang dùng cho phép tính năng đó; một số model hoặc endpoint có giới hạn riêng.

Có thể tạo project thành công nhưng model vẫn không trả về tool call nếu chọn model không hỗ trợ, gửi sai cấu hình hoặc dùng endpoint không cung cấp chức năng này.

## Cấu hình bí mật và môi trường chạy

Không ghi API key trực tiếp vào `application.properties`, `application.yml`, file build hoặc repository. Hãy đưa bí mật vào biến môi trường hoặc secret manager của môi trường chạy.

Ví dụ cấu hình OpenAI trong `application.properties`:

```properties
spring.ai.openai.api-key=${OPENAI_API_KEY}
```

Thiết lập biến môi trường trong PowerShell:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
```

Trên Linux hoặc macOS:

```bash
export OPENAI_API_KEY="your-api-key"
```

Khi chạy trong CI hoặc container, khai báo secret tại nền tảng triển khai. Không in giá trị biến môi trường vào log và không commit file `.env` chứa khóa thật. Nếu dùng Ollama hoặc một model server nội bộ, cấu hình base URL và tên model theo hướng dẫn của provider; không cần tạo API key nếu dịch vụ không yêu cầu.

## Kiểm tra JDK và build tool đang được sử dụng

Một máy có thể cài nhiều JDK cùng lúc. Lệnh `java -version` cho biết Java được gọi từ PATH, nhưng IDE, Maven, Gradle daemon hoặc CI có thể đang dùng JDK khác. Hãy kiểm tra cả môi trường thực thi lẫn cấu hình toolchain.

Với Maven:

```powershell
java -version
.\mvnw.cmd -version
.\mvnw.cmd clean verify
.\mvnw.cmd dependency:tree
```

Với Gradle:

```powershell
java -version
.\gradlew.bat --version
.\gradlew.bat clean test
.\gradlew.bat dependencies
```

Các wrapper `mvnw` và `gradlew` giúp nhóm dùng cùng phiên bản build tool mà không phụ thuộc phiên bản cài toàn cục. Hãy commit wrapper và kiểm tra version của nó trong repository. Với Spring Boot 4.2.0, Maven cần từ 3.6.3; Gradle cần từ 8.14 trong dòng 8.x hoặc dòng 9.x.

Sau khi dependency được phân giải, cần kiểm tra:

- Build hoàn tất với đúng JDK toolchain.
- Dependency tree không có nhiều version Spring AI ngoài dự kiến.
- Application context khởi động được và auto-configuration nhận diện starter.
- Cấu hình provider được nạp mà không lộ API key.
- Một integration test có thể gọi model thật hoặc model test phù hợp và xác nhận tool call được tạo, thực thi, rồi trả kết quả.

Một lần `compile` thành công mới chỉ xác nhận mã nguồn và dependency tương thích ở mức biên dịch. Nó chưa chứng minh thông tin xác thực, mạng, model endpoint hoặc chức năng tool calling hoạt động.

## Cách nhận biết và xử lý lỗi tương thích

| Dấu hiệu | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `UnsupportedClassVersionError` hoặc lỗi class file version | JDK chạy thấp hơn mức mà dependency được biên dịch yêu cầu | Kiểm tra `java -version`, Maven/Gradle JVM, IDE và toolchain |
| `NoSuchMethodError` hoặc `NoClassDefFoundError` | Các module Spring/Spring AI không cùng dòng version hoặc dependency bị override | Xem `dependency:tree` hoặc Gradle dependency report; so sánh BOM và release notes |
| Không tìm thấy artifact | Sai artifact ID, version, repository hoặc cấu hình proxy/mirror | Đối chiếu tên starter trong tài liệu đúng release và kiểm tra Maven Central/mirror |
| Ứng dụng không tạo được ChatModel/ChatClient bean | Thiếu starter, thiếu cấu hình provider hoặc auto-configuration không được kích hoạt | Kiểm tra dependency, properties và log điều kiện auto-configuration |
| Chat trả lời được nhưng không gọi công cụ | Model/endpoint không hỗ trợ tool calling hoặc tool definitions chưa được truyền đúng | Kiểm tra capability của model, provider docs, request/response và cấu hình tool |
| IDE biên dịch được nhưng CI thất bại | JDK, build wrapper hoặc biến môi trường giữa hai môi trường khác nhau | So sánh toolchain, wrapper version và secret/config của CI |

Không nên sửa các lỗi này bằng cách thêm ngẫu nhiên một version cho dependency transitive. Trước tiên, xác định dependency nào kéo phiên bản không mong muốn, rồi điều chỉnh BOM hoặc version của Spring Boot/Spring AI theo ma trận được hỗ trợ.

## Quy trình chọn tổ hợp cho dự án thực tế

Có thể áp dụng quy trình sau mỗi khi khởi tạo hoặc nâng cấp module:

1. **Xác định nhánh Spring Boot đang dùng hoặc cần dùng.** Dự án mới có thể chọn nhánh ổn định mới nhất; dự án đang vận hành cần cân nhắc tương thích của các thư viện và thời gian nâng cấp.
2. **Chọn nhánh Spring AI tương thích.** Đọc Project Setup của Spring AI để xác nhận phiên bản Boot và Java tối thiểu.
3. **Chọn JDK.** Dùng JDK đáp ứng yêu cầu cao nhất trong các dependency; thống nhất phiên bản trong IDE, terminal, toolchain và CI.
4. **Chọn Maven/Gradle và wrapper.** Dùng phiên bản build tool được Boot hỗ trợ, commit wrapper để tái lập build.
5. **Import BOM và thêm đúng provider starter.** Để BOM quản lý version, tránh khai báo riêng lẻ cho từng module AI.
6. **Cấu hình bí mật và endpoint.** Đưa API key vào secret hoặc biến môi trường; xác nhận model thực tế hỗ trợ tool calling.
7. **Build, chạy và kiểm thử.** Xác nhận dependency tree, application context và một luồng gọi công cụ hoàn chỉnh.
8. **Ghi lại quyết định phiên bản.** Lưu các version đã chọn, lý do, tài liệu tham chiếu và cách nâng cấp để thành viên khác tái lập được môi trường.

## Kết luận

Chọn tổ hợp tương thích bắt đầu từ nhánh Spring AI, vì nhánh này xác định dòng Spring Boot mà dự án cần dùng; từ đó mới chọn JDK, build tool và provider starter. Với cấu hình mới theo tài liệu ổn định tại ngày 27/11/2026, Java 21 + Spring Boot 4.2.0 + Spring AI 2.1.0 là một điểm khởi đầu phù hợp. Hãy dùng Spring Boot BOM và Spring AI BOM để quản lý dependency, kiểm tra model có hỗ trợ tool calling, rồi xác minh toàn bộ luồng bằng build và integration test.

## Tài liệu tham khảo

- [Spring AI 2.1 Project Setup](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/get-started/project-setup.html) — yêu cầu Java/Spring Boot, Spring AI BOM và cấu hình Maven/Gradle.
- [Spring AI Getting Started](https://docs.spring.io/spring-ai/reference/getting-started.html) — Spring Initializr, repository và dependency management.
- [Spring AI 1.0 Getting Started](https://docs.spring.io/spring-ai/reference/1.0/getting-started.html) — compatibility của Spring AI 1.0.x với Spring Boot 3.4.x và 3.5.x.
- [Spring Boot 4.2 System Requirements](https://docs.spring.io/spring-boot/system-requirements.html) — yêu cầu Java và phiên bản Maven/Gradle.
- [Spring AI Releases](https://github.com/spring-projects/spring-ai/releases) — trạng thái và ghi chú phát hành của Spring AI.
