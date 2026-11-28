# Ghi lại phiên bản và điều kiện tái lập các ví dụ

Một ví dụ Spring AI Tool Calling chỉ hữu ích khi người đọc có thể dựng lại môi trường, chạy đúng luồng và hiểu vì sao kết quả có thể khác. Vì vậy, phần thiết lập dự án cần ghi lại cả phiên bản phần mềm lẫn điều kiện thực thi: JDK, Spring Boot, Spring AI, công cụ build, thư viện phụ thuộc, cấu hình mô hình, schema công cụ, dữ liệu đầu vào và các dịch vụ bên ngoài.

Với ứng dụng AI, “chạy lại được” có nhiều mức. Có thể tái lập việc biên dịch và kiểm thử mã nguồn; có thể tái lập việc callback xử lý cùng một đầu vào; nhưng không phải lúc nào cũng có thể buộc một mô hình được cung cấp qua dịch vụ đám mây trả về từng token giống hệt lần trước. Cần ghi rõ mức tái lập mà ví dụ hướng tới để người học biết điều gì được bảo đảm và điều gì phụ thuộc nhà cung cấp mô hình.

## Sau bài học, bạn có thể

- Lập bảng phiên bản cho JDK, Spring Boot, Spring AI, Maven hoặc Gradle và các thành phần quan trọng.
- Khóa phiên bản dependency bằng BOM và wrapper, đồng thời lưu dấu vết các dependency thực tế đã resolve.
- Ghi lại cấu hình runtime, provider, model, prompt, tool schema và dữ liệu thử nghiệm mà không làm lộ bí mật.
- Tách khả năng tái lập build, tái lập logic công cụ và tái lập câu trả lời của mô hình.
- Tạo manifest và bộ dữ liệu mẫu để người khác có thể dựng lại ví dụ một cách có kiểm soát.

## Tái lập một ví dụ có nghĩa là gì?

Một ví dụ Spring AI Tool Calling thường có ít nhất bốn lớp điều kiện:

1. **Môi trường build:** JDK, Maven hoặc Gradle, wrapper, plugin, Spring Boot, Spring AI và các dependency đã resolve.
2. **Môi trường chạy:** hệ điều hành, kiến trúc CPU, encoding, locale, múi giờ, profile, biến môi trường và cấu hình ứng dụng.
3. **Hợp đồng tool calling:** phiên bản mã nguồn, mô tả công cụ, tên phương thức, schema đầu vào, kiểu dữ liệu đầu ra và logic callback.
4. **Môi trường AI và dữ liệu:** provider, model, API version, tham số sinh, prompt, dữ liệu đầu vào, trạng thái database và phản hồi của dịch vụ phụ thuộc.

Nếu chỉ ghi “dùng Spring Boot và Spring AI phiên bản mới nhất”, người khác không thể biết họ đã chạy cùng một ví dụ hay chưa. Một bản cập nhật framework có thể thay đổi API, cách tự động cấu hình, dependency bắc cầu hoặc hành vi chuyển đổi schema.

Cần phân biệt ba mức:

| Mức tái lập | Điều có thể kiểm soát | Ví dụ kiểm chứng |
|---|---|---|
| Build | JDK, wrapper, plugin, dependency và mã nguồn | Cùng commit có thể chạy build và test trong môi trường đã ghi |
| Thực thi nghiệp vụ | Đầu vào, dữ liệu, clock, quyền và dịch vụ phụ thuộc | Cùng yêu cầu gọi tool tạo ra cùng kết quả từ service hoặc fixture |
| Hành vi mô hình | Model, prompt, tham số, schema và provider | Có thể so sánh lựa chọn tool, đối số và kết quả theo tiêu chí; không mặc định giống từng token |

Với mô hình chạy qua API bên ngoài, provider có thể cập nhật hạ tầng hoặc model alias mà không thay đổi mã ứng dụng. Temperature bằng 0 cũng không bảo đảm đầu ra giống tuyệt đối giữa mọi lần gọi. Vì vậy, hãy đặt mục tiêu là tái lập được điều kiện và kiểm chứng được hành vi quan trọng, thay vì hứa hẹn đầu ra văn bản luôn giống từng ký tự.

## Bảng phiên bản tối thiểu

Mỗi ví dụ nên có một bảng phiên bản nằm trong README hoặc file manifest. Bảng phải ghi phiên bản chính xác, nguồn xác định phiên bản và lý do thành phần đó quan trọng.

| Thành phần | Cần ghi | Vì sao cần ghi |
|---|---|---|
| Java | Phiên bản JDK đầy đủ và nhà cung cấp JDK | Ảnh hưởng bytecode, compiler và runtime |
| Spring Boot | Phiên bản release đầy đủ | Quyết định dependency được quản lý và auto-configuration |
| Spring AI | Phiên bản release đầy đủ | Quyết định API Tool, ToolCallback, ToolContext và tích hợp model |
| Maven hoặc Gradle | Phiên bản wrapper | Tránh phụ thuộc công cụ cài toàn máy |
| Build plugin | Phiên bản plugin quan trọng | Tránh thay đổi hành vi compile, test và đóng gói |
| Dependency | Phiên bản thực tế đã resolve | Phát hiện xung đột hoặc thay đổi dependency bắc cầu |
| Model provider | Tên provider, endpoint, region và API version nếu có | Kết nối đúng dịch vụ và giao thức |
| Model | Model snapshot hoặc định danh version cụ thể | Phân biệt snapshot cố định với alias có thể được cập nhật |
| Dữ liệu và dịch vụ phụ thuộc | Phiên bản schema, migration, fixture hoặc stub | Đảm bảo đầu vào nghiệp vụ tương đương |

Một bộ phiên bản minh họa có thể dùng Java 21, Spring Boot 3.4.4, Spring AI 1.0.0 và Maven 3.9.9. Đây là ví dụ về cách ghi các phiên bản release cụ thể, không phải khuyến nghị nâng cấp cho mọi dự án. Khi áp dụng, hãy kiểm tra ma trận tương thích của phiên bản Spring AI đã chọn, sau đó ghi lại chính xác bộ phiên bản đã build thành công.

Không dùng các giá trị mơ hồ như `latest`, `RELEASE`, `SNAPSHOT`, version range hoặc tag container có thể thay đổi trong một ví dụ cần tái lập. Nếu phải dùng snapshot trong quá trình phát triển, hãy ghi cả timestamp hoặc commit nhận diện artifact, repository tải về và thời điểm sử dụng.

## Quản lý phiên bản Spring Boot và Spring AI bằng BOM

Spring Boot quản lý một tập dependency tương thích thông qua dependency management. Spring AI cung cấp BOM riêng để quản lý phiên bản các module Spring AI cùng một bộ. Khai báo BOM giúp các starter và module Spring AI sử dụng cùng một release, tránh gán version riêng lẻ cho từng artifact.

Ví dụ Maven dưới đây khóa phiên bản Spring Boot và Spring AI. Bộ phiên bản minh họa ở đây là Java 21, Spring Boot 3.4.4 và Spring AI 1.0.0; trước khi dùng trong dự án thật, cần xác minh chúng phù hợp với ma trận hỗ trợ của dự án.

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.4.4</version>
    <relativePath/>
</parent>

<properties>
    <java.version>21</java.version>
    <spring-ai.version>1.0.0</spring-ai.version>
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
        <groupId>org.springframework.ai</groupId>
        <artifactId>spring-ai-starter-model-openai</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Dependency starter ở trên là ví dụ dùng OpenAI chat model. Nếu bài thực hành dùng provider hoặc module khác, thay starter bằng artifact tương ứng trong cùng release Spring AI. Không trộn module milestone, snapshot và stable trong cùng một ví dụ nếu chưa có lý do và kiểm tra tương thích rõ ràng.

Một số nguyên tắc quản lý dependency:

- Khai báo version ở một nơi thông qua parent hoặc BOM, tránh lặp version trong từng dependency.
- Không tự ghi đè một dependency do Spring Boot hoặc Spring AI BOM quản lý nếu chưa hiểu tác động tương thích.
- Ghi rõ version của plugin build nếu plugin đó không được parent quản lý.
- Không dùng dependency version range trong ví dụ cần tái lập.
- Kiểm tra dependency tree sau khi thay BOM hoặc starter để phát hiện hai phiên bản cùng một thư viện.
- Commit file cấu hình build và wrapper vào repository để người khác dùng đúng công cụ.

### Nếu dự án dùng Gradle

Gradle có thể import BOM bằng plugin quản lý dependency hoặc native platform. Ví dụ Kotlin DSL sau dùng phiên bản minh họa tương tự:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.4.4"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.0.1"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

extra["springAiVersion"] = "1.0.0"

dependencyManagement {
    imports {
        mavenBom(
            "org.springframework.ai:spring-ai-bom:${property("springAiVersion")}"
        )
    }
}

dependencies {
    implementation("org.springframework.ai:spring-ai-starter-model-openai")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Hãy chọn Maven hoặc Gradle theo cấu trúc dự án và dùng wrapper tương ứng. Không duy trì hai cấu hình build khác nhau cho cùng một bài thực hành nếu không có yêu cầu cụ thể, vì điều đó tạo thêm một nguồn sai lệch cần kiểm tra.

## Dùng wrapper để cố định công cụ build

Wrapper giúp người học không phải tự cài đúng phiên bản Maven hoặc Gradle trước khi chạy dự án. Repository cần chứa các file wrapper và cấu hình phân phối phiên bản.

Với Maven, commit các file như:

- `mvnw` và `mvnw.cmd`;
- thư mục `.mvn/wrapper/`, gồm `maven-wrapper.properties` và các file wrapper cần thiết.

Trong `maven-wrapper.properties`, cấu hình `distributionUrl` trỏ đến một bản Maven cụ thể. Khi hạ tầng hỗ trợ, ghi cả checksum phân phối để kiểm tra nội dung tải về. Với Gradle, commit `gradlew`, `gradlew.bat`, thư mục `gradle/wrapper/` và cấu hình `distributionUrl` cùng checksum nếu có.

Chạy lệnh qua wrapper thay vì dựa vào lệnh cài toàn máy:

~~~bash
# Linux hoặc macOS
./mvnw -version
./mvnw -B -ntp clean verify

# Windows PowerShell hoặc Command Prompt
.\mvnw.cmd -version
.\mvnw.cmd -B -ntp clean verify
~~~

Đối với Gradle:

~~~bash
# Linux hoặc macOS
./gradlew --version
./gradlew clean test

# Windows
.\gradlew.bat --version
.\gradlew.bat clean test
~~~

Kết quả `-version` hoặc `--version` cần được lưu trong log build hoặc manifest. Wrapper cố định phiên bản công cụ build; nó không tự cố định JDK, dependency, plugin, model provider hoặc dữ liệu bên ngoài. Các thành phần đó cần được khai báo riêng.

## Ghi lại dependency thực tế đã resolve

BOM cho biết phiên bản được quản lý, nhưng khi cần điều tra một build cụ thể, hãy lưu danh sách dependency thực tế. Dependency bắc cầu có thể đến từ nhiều module và có thể bị điều chỉnh bởi dependency management hoặc quy tắc resolution.

Với Maven, có thể xuất dependency tree:

~~~bash
./mvnw -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -DoutputFile=target/dependency-tree.txt
~~~

Trên Windows, dùng `mvnw.cmd` thay cho `./mvnw`. File dependency tree giúp xác định module nào kéo một thư viện vào và phiên bản cuối cùng được chọn. Có thể lưu nó như artifact của CI hoặc đính kèm vào báo cáo phiên bản của lần phát hành ví dụ.

Với Gradle, có thể bật dependency locking để lưu các phiên bản đã resolve:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau khi bật locking, resolve các cấu hình cần thiết và ghi lock state:

~~~bash
./gradlew dependencies --write-locks
~~~

Gradle còn hỗ trợ dependency verification để kiểm tra checksum hoặc chữ ký artifact. Với dự án cần kiểm soát chuỗi cung ứng phần mềm, hãy lưu metadata xác minh cùng repository và cập nhật chúng qua quy trình review.

Maven và Gradle có cơ chế quản lý dependency khác nhau. Dù dùng công cụ nào, cần lưu ý rằng một file dependency tree là bằng chứng về lần resolve đã xảy ra; bản thân nó không thay thế cấu hình version, wrapper, plugin và repository cần thiết để tái tạo lần resolve đó.

## Cố định môi trường chạy

Cùng một mã nguồn có thể hoạt động khác nhau khi runtime hoặc cấu hình khác nhau. Hãy ghi các thông tin sau cho ví dụ:

- JDK vendor và version đầy đủ, không chỉ ghi “Java 21”.
- Hệ điều hành, kiến trúc CPU và image/container nếu dùng.
- Locale, timezone và encoding mặc định.
- Spring profile đang kích hoạt.
- Các biến môi trường ảnh hưởng tới hành vi ứng dụng, chỉ ghi tên và giá trị không nhạy cảm.
- Cấu hình database, phiên bản schema và migration đã áp dụng.
- Các cổng, endpoint hoặc dịch vụ phụ thuộc có liên quan tới bài thực hành.

Để giảm khác biệt giữa máy, có thể đặt timezone và encoding rõ ràng khi chạy ứng dụng hoặc trong container. Nếu ví dụ xử lý ngày giờ, hãy truyền `Clock` vào dịch vụ nghiệp vụ để test có thể dùng một thời điểm cố định thay vì gọi đồng hồ hệ thống ở nhiều nơi.

Nếu dùng Docker, hãy ghi image cùng tag và digest. Tag như `latest` có thể trỏ tới image khác vào lần tải sau; digest nhận diện nội dung image cụ thể. Cũng cần ghi kiến trúc image khi build phụ thuộc kiến trúc CPU.

## Ghi lại provider và model cho ví dụ Tool Calling

Tool calling chịu ảnh hưởng bởi model provider và cấu hình sinh. Trong file cấu hình, có thể tách API key và tên model thành biến môi trường:

~~~yaml
spring:
  ai:
    openai:
      api-key: ${OPENAI_API_KEY}
      chat:
        options:
          model: ${OPENAI_MODEL}
          temperature: 0
~~~

Không commit API key thật vào Git, README, log hoặc fixture. Người học tạo biến môi trường riêng theo hướng dẫn của dự án hoặc dùng secret manager của môi trường chạy.

Ngoài cấu hình trên, manifest của ví dụ cần ghi:

- Provider và endpoint hoặc region đã dùng.
- API version nếu provider có khái niệm này.
- Model ID chính xác; ưu tiên snapshot/version cố định nếu nhà cung cấp hỗ trợ.
- Thời điểm chạy và thông tin nhận diện model mà provider trả về, nếu có.
- Temperature, top-p, giới hạn token, seed nếu provider và model hỗ trợ, tool choice và chế độ gọi tool song song nếu được cấu hình.
- Prompt hệ thống và prompt người dùng đã chuẩn hóa, hoặc mã phiên bản của prompt.
- Danh sách tool được cung cấp, tên, mô tả, schema JSON và phiên bản mã callback.
- Request ID hoặc trace ID do provider trả về để truy vết khi cần.

Tên như `latest` hoặc một alias thân thiện có thể được nhà cung cấp ánh xạ sang model mới. Nếu chỉ có alias, hãy ghi rõ alias, thời điểm gọi và model version thực tế nếu response metadata cung cấp. Không giả định alias giữ nguyên hành vi theo thời gian.

Temperature bằng 0 có thể giảm tính ngẫu nhiên trong một số cấu hình nhưng không tạo ra bảo đảm đầu ra bất biến. Provider có thể thay đổi hạ tầng, model, thuật toán phục vụ hoặc cách xử lý tool call. Khi cần tái lập một lỗi, hãy lưu request và response đã loại bỏ thông tin nhạy cảm, đồng thời ghi provider metadata và thời điểm chạy.

## Ghi lại hợp đồng công cụ

Đối với Spring AI Tool Calling, chỉ ghi phiên bản framework là chưa đủ. Mô hình nhìn thấy mô tả và schema của các công cụ; thay đổi nhỏ ở tên, mô tả hoặc kiểu tham số có thể làm thay đổi cách mô hình lựa chọn và tạo đối số.

Ví dụ, công cụ tra cứu đơn hàng có thể được khai báo như sau:

~~~java
@Component
class OrderTools {

    private final OrderQueryService orderQueryService;

    OrderTools(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @Tool(description = "Tra cứu trạng thái của một đơn hàng mà khách hàng hiện tại được phép xem")
    public OrderStatus getOrderStatus(
            @ToolParam(description = "Mã đơn hàng cần tra cứu") String orderId,
            ToolContext toolContext) {

        String customerId =
                (String) toolContext.getContext().get("customerId");

        return orderQueryService.getStatusForCustomer(orderId, customerId);
    }
}
~~~

Để người khác hiểu và kiểm tra cùng hợp đồng, hãy lưu hoặc tạo được các thông tin:

1. Tên tool và mô tả chính xác tại thời điểm chạy.
2. JSON schema đầu vào, gồm kiểu dữ liệu, trường bắt buộc và ràng buộc.
3. Cấu trúc kết quả mà callback trả về.
4. Commit chứa implementation của tool và dịch vụ nghiệp vụ được gọi.
5. Quyền và ngữ cảnh được truyền qua ToolContext.
6. Ví dụ đầu vào hợp lệ, đầu vào thiếu hoặc sai định dạng, và kết quả mong đợi.

Nếu schema được Spring AI tạo tự động từ annotation, hãy kiểm tra schema thực tế đã gửi cho model thay vì chỉ dựa vào ý định của người viết mã. Việc đổi tên tham số, mô tả, kiểu dữ liệu hoặc annotation có thể ảnh hưởng đến hợp đồng mà model nhận được.

ToolContext thường mang dữ liệu do ứng dụng xác định như customerId, tenantId hoặc correlation id. Ghi lại tên các trường và nguồn tạo ra chúng; không ghi giá trị bí mật hoặc dữ liệu cá nhân thật vào tài liệu công khai. Dữ liệu phân quyền vẫn phải được kiểm tra trong dịch vụ nghiệp vụ.

## Chuẩn hóa dữ liệu và dịch vụ phụ thuộc

Ví dụ có thể gọi database, hệ thống vận chuyển, API thanh toán hoặc dịch vụ nội bộ. Nếu những nguồn này thay đổi giữa các lần chạy, kết quả cũng có thể thay đổi dù model và mã nguồn không đổi.

Để kiểm soát:

- Dùng dữ liệu fixture nhỏ, có tên và phiên bản rõ ràng.
- Ghi lại migration hoặc schema database cần áp dụng trước khi chạy.
- Dùng mock server hoặc stub response cho test cần kết quả ổn định.
- Cố định thời gian bằng Clock được inject vào dịch vụ.
- Cố định random seed khi thư viện hỗ trợ và khi tính ngẫu nhiên thuộc phần mã do ứng dụng kiểm soát.
- Ghi rõ các dịch vụ thật được gọi trong bài thực hành và dữ liệu mà chúng có thể thay đổi.
- Không dùng tài khoản production hoặc dữ liệu khách hàng thật làm fixture.

Một điểm cần tách bạch: mock một dịch vụ ngoài giúp tái lập phản hồi của dịch vụ đó, nhưng không kiểm tra được kết nối thật với nhà cung cấp. Vì vậy, nên có test dùng stub cho hành vi xác định và một nhóm integration test riêng cho kết nối thật, có giới hạn và điều kiện chạy rõ ràng.

## Tạo manifest cho mỗi ví dụ

Một file manifest nhỏ giúp người học không phải suy luận phiên bản từ nhiều nơi. Ví dụ dưới đây là mẫu tài liệu; thay các giá trị `REPLACE_...` bằng giá trị thực tế đã dùng. Không đưa secret vào file này.

~~~yaml
example:
  id: tool-calling-order-status
  source:
    gitCommit: "REPLACE_WITH_COMMIT"
    workingTreeClean: "REPLACE_WITH_TRUE_OR_FALSE"
  runtime:
    javaVendor: "REPLACE_WITH_JDK_VENDOR"
    javaVersion: "REPLACE_WITH_FULL_JDK_VERSION"
    os: "REPLACE_WITH_OS_AND_VERSION"
    architecture: "REPLACE_WITH_ARCH"
    locale: "vi_VN"
    timezone: "Asia/Ho_Chi_Minh"
    encoding: "UTF-8"
  build:
    tool: "Maven"
    wrapperVersion: "3.9.9"
    springBoot: "3.4.4"
    springAi: "1.0.0"
    dependencyTree: "artifacts/dependency-tree.txt"
  ai:
    provider: "REPLACE_WITH_PROVIDER"
    endpointOrRegion: "REPLACE_WITH_ENDPOINT_OR_REGION"
    apiVersion: "REPLACE_IF_APPLICABLE"
    modelId: "REPLACE_WITH_MODEL_SNAPSHOT_OR_ALIAS"
    modelVersionFromResponse: "REPLACE_IF_AVAILABLE"
    temperature: 0
    topP: "RECORD_IF_CONFIGURED"
    maxTokens: "RECORD_IF_CONFIGURED"
    seed: "RECORD_IF_SUPPORTED"
    promptRevision: "REPLACE_WITH_PROMPT_REVISION"
    toolSchemaRevision: "REPLACE_WITH_SCHEMA_REVISION"
  tools:
    - name: "getOrderStatus"
      sourceCommit: "REPLACE_WITH_COMMIT"
      inputFixture: "fixtures/order-status-request.json"
      expectedResult: "fixtures/order-status-result.json"
  externalDependencies:
    databaseMigration: "REPLACE_WITH_MIGRATION_VERSION"
    externalServices: "Stubbed shipping API"
  execution:
    command: "./mvnw -B -ntp clean verify"
    executedAt: "REPLACE_WITH_ISO_8601_TIMESTAMP"
    result: "PASS_OR_FAIL"
~~~

Manifest có thể đặt trong thư mục ví dụ hoặc được tạo như artifact của CI. Nên thống nhất một schema manifest cho toàn bộ module để các bài học có thể được so sánh và cập nhật nhất quán.

Không ghi API key, access token, cookie, mật khẩu database, dữ liệu cá nhân hoặc toàn bộ payload production. Nếu cần tham chiếu một secret, chỉ ghi tên biến môi trường hoặc tên secret trong secret manager, chẳng hạn `OPENAI_API_KEY`, không ghi giá trị.

## Quy trình chạy lại một ví dụ

Một quy trình có thể được dùng trong README của mỗi bài:

1. Checkout đúng Git commit hoặc tag của ví dụ.
2. Cài JDK phù hợp và xác nhận bằng `java -version`.
3. Dùng wrapper trong repository; xác nhận phiên bản bằng `./mvnw -version` hoặc `./gradlew --version`.
4. Cấu hình các biến môi trường cần thiết theo file mẫu, không đưa secret vào source control.
5. Khởi tạo database và áp dụng đúng migration hoặc nạp fixture đã ghi.
6. Chạy test không cần provider trước để kiểm tra logic nghiệp vụ và callback.
7. Nếu bài có gọi model thật, cấu hình provider/model đã ghi trong manifest và chạy integration test tương ứng.
8. Lưu log, dependency tree, manifest thực tế và kết quả test để người khác đối chiếu.

Một số lệnh hữu ích khi dùng Git và Maven:

~~~bash
git rev-parse HEAD
git status --short
java -version
./mvnw -version
./mvnw -B -ntp clean verify
./mvnw -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -DoutputFile=target/dependency-tree.txt
~~~

Trên Windows, thay `./mvnw` bằng `mvnw.cmd`. Nếu working tree có thay đổi chưa commit, ghi rõ những file đã thay đổi vì Git commit không đại diện đầy đủ cho trạng thái mã nguồn được chạy.

## Kiểm thử để biết phần nào đã tái lập được

Không nên dùng một lần gọi model thành công làm bằng chứng rằng toàn bộ ví dụ đã tái lập. Hãy chia kiểm thử theo ranh giới:

**Unit test dịch vụ nghiệp vụ:** Gọi trực tiếp service với dữ liệu cố định để kiểm tra quy tắc trạng thái, quyền truy cập và kết quả. Các test này không cần model provider.

**Test callback và schema:** Kiểm tra tên tool, mô tả, tham số bắt buộc, kiểu dữ liệu, dữ liệu trả về và cách xử lý đầu vào sai. Nếu schema được framework tạo, kiểm tra schema thực tế được tạo.

**Test lớp điều phối:** Dùng model giả hoặc phản hồi đã ghi nhận để kiểm tra ứng dụng xử lý đúng một yêu cầu gọi tool, nhiều yêu cầu, tool không được phép, kết quả lỗi và trường hợp model trả lời mà không gọi tool.

**Test tích hợp với model thật:** Chạy có kiểm soát trên provider và model đã ghi trong manifest. Kiểm tra tiêu chí như tool được chọn thuộc tập cho phép, đối số hợp lệ, quyền được thực thi và kết quả nghiệp vụ chính xác. Tránh chỉ so sánh toàn bộ câu trả lời theo chuỗi tuyệt đối.

**Test tích hợp với dịch vụ ngoài:** Dùng stub cho test lặp lại thường xuyên; dành test kết nối thật cho môi trường phù hợp và ghi lại thời điểm, endpoint, dữ liệu thử nghiệm.

Có thể lưu một bộ fixture đã làm sạch gồm input hội thoại, danh sách tool/schema, tool call do model trả về, kết quả callback và câu trả lời cuối. Replay tool call đã lưu giúp kiểm tra callback và lớp điều phối. Nó không chứng minh rằng model sẽ tự chọn cùng tool khi nhận lại câu hỏi; muốn đánh giá việc lựa chọn, vẫn cần test model và kiểm tra theo tiêu chí.

## Xử lý khác biệt giữa các lần chạy

Khi một ví dụ chạy khác với tài liệu, hãy so sánh theo thứ tự:

- Git commit và trạng thái working tree có giống nhau không?
- JDK, wrapper và phiên bản build tool có giống nhau không?
- Spring Boot, Spring AI, plugin và dependency tree có giống nhau không?
- Profile, locale, timezone và biến môi trường có giống nhau không?
- Database, fixture, migration, thời gian và phản hồi dịch vụ ngoài có giống nhau không?
- Provider, endpoint, model snapshot, API version và tham số sinh có giống nhau không?
- Prompt, tool description, schema và implementation callback có thay đổi không?

Một số dấu hiệu thường gặp:

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không tìm thấy class hoặc method sau khi cập nhật | Module hoặc API không tương thích | So sánh Spring Boot, Spring AI và dependency tree |
| Ứng dụng không tạo được ChatModel bean | Thiếu starter, cấu hình provider hoặc dependency bị lệch | Kiểm tra starter, profile và auto-configuration report |
| Model không chọn tool như ví dụ | Model, prompt, mô tả hoặc schema khác | So sánh request, tool schema và model metadata |
| Callback nhận đối số sai hoặc thiếu | Schema chưa rõ hoặc model tạo dữ liệu không hợp lệ | Kiểm tra JSON schema và validation ở ứng dụng |
| Test cho kết quả khác theo thời gian | Clock, database hoặc API ngoài thay đổi | Dùng Clock cố định, fixture và stub |
| Build khác nhau giữa máy | JDK, wrapper, plugin hoặc dependency resolve khác | So sánh version output và dependency tree |

Khi nâng cấp phiên bản, thay đổi có kiểm soát từng nhóm: cập nhật Spring Boot hoặc Spring AI, kiểm tra ma trận tương thích, resolve dependency, chạy test, cập nhật manifest rồi mới chuyển sang thay đổi khác. Ghi ngày nâng cấp, lý do, thay đổi API và kết quả kiểm chứng để người học biết ví dụ đang dùng bộ phiên bản nào.

## Checklist trước khi công bố ví dụ

- [ ] Đã ghi Git commit hoặc tag và trạng thái working tree.
- [ ] Đã khóa JDK, Spring Boot, Spring AI và Maven/Gradle wrapper.
- [ ] Đã lưu cấu hình build và dependency tree hoặc lockfile phù hợp.
- [ ] Đã ghi provider, endpoint, model ID, API version và tham số sinh.
- [ ] Đã ghi prompt, tool description, schema và phiên bản callback.
- [ ] Đã cố định fixture, migration, clock và dịch vụ ngoài cần thiết.
- [ ] Đã tách test nghiệp vụ, test callback, test điều phối và test model thật.
- [ ] Đã loại bỏ secret và dữ liệu cá nhân khỏi tài liệu, log và fixture.
- [ ] Đã ghi lệnh chạy lại và kết quả kiểm thử thực tế.
- [ ] Đã nêu rõ phần nào tái lập được và phần nào còn phụ thuộc provider.

## Ghi nhớ khi thiết lập dự án

Một ví dụ có thể tái lập cần mô tả chính xác trạng thái đã chạy: mã nguồn nào, JDK nào, framework và dependency nào, cấu hình nào, model nào, tool schema nào và dữ liệu nào. BOM và wrapper giúp kiểm soát phiên bản; manifest và fixture giúp lưu lại điều kiện; test theo từng ranh giới giúp xác định phần nào hoạt động ổn định.

Với Spring AI Tool Calling, hãy đặc biệt lưu lại model metadata và schema tool tại thời điểm thực thi. Khi provider thay đổi model hoặc cách phục vụ, bạn vẫn có thể tái hiện phần xử lý nghiệp vụ, replay callback và so sánh hành vi theo tiêu chí rõ ràng. Đó là nền tảng để ví dụ có thể được học, kiểm tra và bảo trì qua nhiều lần cập nhật.

