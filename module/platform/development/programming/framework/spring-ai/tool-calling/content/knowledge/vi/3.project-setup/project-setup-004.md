# Cấu hình thông tin xác thực, endpoint và tên mô hình

Một ứng dụng Spring AI chỉ có thể gửi yêu cầu đến mô hình khi biết **dùng provider nào, xác thực bằng thông tin nào, gửi request đến endpoint nào và chọn model nào**. Bốn thông tin này thường được cấu hình bằng Spring Boot properties, biến môi trường và dependency starter tương ứng.

Với module Spring AI Tool Calling, cấu hình kết nối còn quyết định mô hình có hỗ trợ tool calling hay không. Khi ứng dụng gửi danh sách tool, mô hình chỉ tạo yêu cầu gọi tool; Spring AI và ứng dụng xử lý callback ở phía máy chủ. Vì vậy, cần kiểm tra cả kết nối mô hình lẫn khả năng thực thi tool sau khi cấu hình.

Bài viết dùng OpenAI làm ví dụ chính và giới thiệu Ollama để chạy mô hình cục bộ. Các tên property bên dưới theo cấu trúc Spring AI hiện hành; những phiên bản cũ có thể dùng tên property khác.

## 1. Những thành phần cần cấu hình

Khi chuẩn bị một ứng dụng Spring AI, hãy xác định các thành phần sau:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Provider | Nhà cung cấp hoặc máy chủ phục vụ mô hình | OpenAI, Ollama, dịch vụ tương thích OpenAI |
| Dependency starter | Đưa tích hợp provider vào Spring Boot | **spring-ai-starter-model-openai** |
| Credential | Chứng minh ứng dụng được phép sử dụng dịch vụ | API key |
| Base URL / endpoint | Địa chỉ HTTP mà client gửi request đến | **https://api.openai.com** |
| Model name | Chọn mô hình hoặc deployment cụ thể | **gpt-4o-mini** |
| Model options | Tham số điều khiển request | temperature, giới hạn token |
| ChatClient | Giao diện ứng dụng dùng để gửi prompt và nhận phản hồi | **ChatClient** |
| Tool callbacks | Những thao tác nghiệp vụ mà ứng dụng cho phép mô hình yêu cầu | **InventoryTools** |

Một cấu hình có thể kết nối thành công nhưng vẫn không dùng được tool calling. Nguyên nhân thường là model/provider không hỗ trợ tool calling, tool chưa được truyền vào request hoặc vòng thực thi tool chưa được bật.

## 2. Thêm dependency Spring AI

Spring AI cung cấp starter riêng cho từng provider. Với OpenAI, thêm dependency **spring-ai-starter-model-openai** và dùng Spring AI BOM để quản lý phiên bản đồng bộ.

Ví dụ Maven:

~~~xml
<properties>
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
        <groupId>org.springframework.ai</groupId>
        <artifactId>spring-ai-starter-model-openai</artifactId>
    </dependency>
</dependencies>
~~~

Chọn phiên bản Spring AI tương thích với phiên bản Spring Boot và Java của dự án. Không nên trộn các module Spring AI ở nhiều phiên bản khác nhau. BOM giúp các module dùng cùng một bộ phiên bản.

Nếu dùng Gradle, có thể import BOM theo cách tương tự:

~~~groovy
dependencies {
    implementation platform("org.springframework.ai:spring-ai-bom:2.1.0")
    implementation "org.springframework.ai:spring-ai-starter-model-openai"
}
~~~

Đối với Ollama, thay starter OpenAI bằng:

~~~groovy
implementation "org.springframework.ai:spring-ai-starter-model-ollama"
~~~

Không cần thêm cả hai starter chỉ để thử một provider. Nếu ứng dụng thực sự cần nhiều provider, hãy cấu hình rõ model bean và cơ chế lựa chọn thay vì dựa vào cấu hình mặc định không chủ ý.

## 3. Cấu hình thông tin xác thực

### 3.1. Dùng biến môi trường cho API key

API key là bí mật dùng để xác thực request. Không ghi giá trị thật vào **application.yml**, source code, file cấu hình được commit hoặc prompt.

Tạo biến môi trường **OPENAI_API_KEY**, sau đó tham chiếu biến đó trong cấu hình Spring Boot:

~~~yaml
spring:
  ai:
    openai:
      api-key: ${OPENAI_API_KEY}
~~~

Spring Boot thay **${OPENAI_API_KEY}** bằng giá trị từ môi trường khi khởi động ứng dụng. Nếu biến chưa được khai báo và không có giá trị mặc định, ứng dụng thường không thể phân giải placeholder và sẽ báo lỗi cấu hình. Đây là dấu hiệu hữu ích để phát hiện thiếu secret sớm.

Có hai cách phổ biến để cung cấp giá trị:

**Cách 1: dùng tên biến riêng rồi tham chiếu trong YAML**

~~~powershell
$env:OPENAI_API_KEY = "<API_KEY>"
.\mvnw.cmd spring-boot:run
~~~

**Cách 2: dùng trực tiếp tên biến môi trường theo quy tắc relaxed binding của Spring Boot**

~~~powershell
$env:SPRING_AI_OPENAI_API_KEY = "<API_KEY>"
.\mvnw.cmd spring-boot:run
~~~

Trong cách thứ hai, Spring Boot ánh xạ biến môi trường **SPRING_AI_OPENAI_API_KEY** thành property **spring.ai.openai.api-key**; không cần khai báo lại giá trị key trong YAML.

Với Linux hoặc macOS, có thể đặt biến trong phiên terminal:

~~~bash
export OPENAI_API_KEY="<API_KEY>"
./mvnw spring-boot:run
~~~

Các lệnh trên chỉ thiết lập biến cho tiến trình terminal hiện tại và những tiến trình con của nó. Khi chạy trong IDE, Docker, Kubernetes hoặc CI/CD, cần cấu hình biến trong môi trường chạy tương ứng.

### 3.2. Lưu secret theo môi trường

| Môi trường | Cách cấp credential phù hợp |
|---|---|
| Máy phát triển | Biến môi trường trong terminal hoặc cấu hình Run/Debug của IDE |
| CI/CD | Secret store của nền tảng pipeline |
| Docker Compose | Secret hoặc biến môi trường được inject khi chạy container |
| Kubernetes | Kubernetes Secret, kết hợp RBAC và chính sách truy cập |
| Production trên cloud | Secret manager hoặc vault của nền tảng |

Không đưa API key vào Git, ảnh chụp màn hình, log khởi động hoặc thông báo lỗi. Nếu một key đã bị commit hoặc lộ trong log, hãy thu hồi/rotate key tại provider và cập nhật secret mới trong môi trường chạy.

Một file **.env** không tự động được Spring Boot đọc trong cấu hình mặc định. Nếu nhóm dùng file này, phải có công cụ hoặc cơ chế cấu hình riêng để nạp biến vào tiến trình. Không nên giả định rằng đặt **.env** cạnh **pom.xml** là ứng dụng đã nhận được secret.

### 3.3. Phạm vi và quyền của API key

Một credential nên có quyền tối thiểu cần thiết cho ứng dụng. Nếu provider hỗ trợ giới hạn project, workspace, model hoặc ngân sách, hãy cấu hình giới hạn phù hợp.

Không truyền API key qua:

- Prompt hoặc **ToolContext**.
- Tham số do người dùng gửi đến controller.
- JSON input schema của tool.
- Tool result trả về mô hình.
- Log request/response ở môi trường production.

API key phục vụ kết nối provider thuộc cấu hình hạ tầng của ứng dụng. **ToolContext** chỉ dành cho dữ liệu ngữ cảnh server-side cần truyền đến callback nghiệp vụ; không phải nơi lưu credential kết nối mô hình.

## 4. Cấu hình endpoint và base URL

### 4.1. Phân biệt base URL với API path

**base-url** xác định địa chỉ máy chủ mà client kết nối đến. API path là phần đường dẫn cho thao tác cụ thể, ví dụ endpoint chat completion.

Với OpenAI, Spring AI mặc định dùng base URL **https://api.openai.com** và chat completions path **/v1/chat/completions**. Có thể cấu hình base URL dùng chung:

~~~yaml
spring:
  ai:
    openai:
      base-url: https://api.openai.com
~~~

Hoặc ghi đè riêng endpoint của chat model:

~~~yaml
spring:
  ai:
    openai:
      chat:
        base-url: ${OPENAI_CHAT_BASE_URL:https://api.openai.com}
~~~

**spring.ai.openai.chat.base-url** có độ ưu tiên cao hơn **spring.ai.openai.base-url** đối với chat model. Cấu hình riêng hữu ích khi chat model và embedding model dùng các endpoint hoặc tài khoản khác nhau.

Không ghép tùy tiện cả base URL và API path. Ví dụ, nếu client đã tự nối **/v1/chat/completions** mà cấu hình base URL cũng chứa toàn bộ path này, request có thể đi đến URL sai hoặc bị lặp path. Hãy đối chiếu base URL và đường dẫn chat completions mà client/provider sử dụng trong tài liệu đúng phiên bản.

### 4.2. Kết nối đến OpenAI-compatible endpoint

Một số dịch vụ tự host hoặc gateway cung cấp API tương thích giao thức OpenAI. Có thể dùng OpenAI starter nếu endpoint đó hỗ trợ đúng API mà client gửi.

Ví dụ cấu hình một endpoint nội bộ:

~~~yaml
spring:
  ai:
    openai:
      chat:
        base-url: ${AI_GATEWAY_BASE_URL}
        api-key: ${AI_GATEWAY_API_KEY}
        model: ${AI_GATEWAY_MODEL}
~~~

Các biến trên phải được cung cấp trong môi trường chạy. Với endpoint tương thích OpenAI, cần xác minh:

- Đường dẫn chat completions mà gateway hỗ trợ.
- Cơ chế xác thực và header bắt buộc.
- Model ID mà gateway chấp nhận.
- Định dạng tool call và tool result.
- Các tham số request được gateway hỗ trợ.

Tương thích endpoint không có nghĩa mọi tính năng đều giống nhau. Gateway có thể hỗ trợ chat text nhưng không hỗ trợ tool calling, structured output hoặc một số model options.

### 4.3. Endpoint trong Docker và môi trường mạng

Địa chỉ **localhost** luôn được hiểu từ góc nhìn của tiến trình đang chạy. Nếu ứng dụng Spring nằm trong container, **localhost** là chính container ứng dụng đó.

Ví dụ, khi Spring Boot và Ollama chạy trong hai container thuộc cùng Docker Compose network, ứng dụng thường cần dùng hostname dịch vụ:

~~~yaml
spring:
  ai:
    ollama:
      base-url: http://ollama:11434
~~~

Trong đó **ollama** là tên service trên Docker network. Khi ứng dụng chạy trực tiếp trên máy host, **http://localhost:11434** có thể là địa chỉ phù hợp.

Khi kết nối qua proxy hoặc HTTPS nội bộ, cần cấu hình DNS, certificate và truststore đúng cách. Không tắt xác minh TLS để khắc phục tạm lỗi chứng chỉ trong môi trường production.

## 5. Chọn tên mô hình

### 5.1. Model name là định danh provider hiểu

Tên mô hình là định danh mà provider dùng để chọn model hoặc deployment xử lý request. Ví dụ:

~~~yaml
spring:
  ai:
    openai:
      chat:
        model: gpt-4o-mini
~~~

Giá trị này phải khớp với model ID mà tài khoản và endpoint hiện tại được phép truy cập. Với một số dịch vụ được quản lý, trường model có thể yêu cầu deployment name do người vận hành tạo thay vì tên model công khai.

Không nên dùng tên hiển thị trong dashboard nếu API yêu cầu một định danh khác. Khi đổi provider, cần kiểm tra lại model name vì hai provider có thể đặt tên khác nhau cho model tương đương.

### 5.2. Chọn model theo khả năng cần dùng

Với module Tool Calling, model cần hỗ trợ tool calling theo giao thức của provider. Trước khi chọn, kiểm tra:

- Có hỗ trợ tool/function calling không?
- Có hỗ trợ nhiều tool call trong một lượt không?
- Có thể trả về đúng định dạng đối số mà provider yêu cầu không?
- Có giới hạn context và output phù hợp với prompt và tool result không?
- Có hỗ trợ structured output hoặc JSON Schema nếu ứng dụng cần không?
- Có sẵn trong tài khoản, project, khu vực và endpoint đang sử dụng không?

Model trả lời văn bản tốt chưa chắc đã hỗ trợ tool calling. Ngay cả khi provider có tính năng này, không phải model nào trong catalog cũng hỗ trợ như nhau.

### 5.3. Model options phụ thuộc provider

Các tham số như **temperature**, **max-tokens**, **max-completion-tokens**, **top-p** hoặc **response-format** có thể khác nhau theo provider và model.

Không sao chép nguyên bộ options từ một model sang model khác. Ví dụ, một số model suy luận không chấp nhận **temperature**; một số model dùng tham số giới hạn output token khác với model hội thoại thông thường. Nếu provider trả lỗi 400, hãy kiểm tra tên option, kiểu dữ liệu và khả năng hỗ trợ của model đã chọn.

Chỉ cấu hình các options thực sự cần thiết. Bắt đầu với cấu hình mặc định, sau đó điều chỉnh dựa trên kết quả kiểm thử và yêu cầu sản phẩm.

## 6. Ví dụ cấu hình OpenAI hoàn chỉnh

Một cấu hình cơ bản trong **src/main/resources/application.yml**:

~~~yaml
spring:
  ai:
    model:
      chat: openai
    openai:
      api-key: ${OPENAI_API_KEY}
      base-url: ${OPENAI_BASE_URL:https://api.openai.com}
      chat:
        model: ${OPENAI_CHAT_MODEL:gpt-4o-mini}
~~~

Trong cấu hình này:

- **spring.ai.model.chat** chọn provider chat model cho auto-configuration.
- **spring.ai.openai.api-key** nhận credential từ biến môi trường.
- **spring.ai.openai.base-url** cho phép đổi endpoint mà không sửa mã nguồn.
- **spring.ai.openai.chat.model** chọn model ID.
- Giá trị sau dấu **:** trong placeholder là giá trị mặc định nếu biến môi trường chưa có.

Đối với OpenAI-compatible gateway, có thể dùng **spring.ai.openai.chat.base-url** và **spring.ai.openai.chat.api-key** để ghi đè riêng cấu hình chat. Chỉ dùng giá trị mặc định cho base URL khi muốn kết nối OpenAI thật.

Ví dụ chạy ứng dụng trên Windows PowerShell:

~~~powershell
$env:OPENAI_API_KEY = "<API_KEY>"
$env:OPENAI_CHAT_MODEL = "gpt-4o-mini"
$env:SPRING_PROFILES_ACTIVE = "openai"
.\mvnw.cmd spring-boot:run
~~~

Nếu dùng profile **openai**, hãy đặt phần cấu hình provider trong **application-openai.yml**. Không cần lặp lại các giá trị secret trong cả hai file.

## 7. Ví dụ dùng Ollama để chạy model cục bộ

Ollama cho phép chạy model trên máy cá nhân hoặc máy chủ nội bộ. Với tích hợp Ollama native, Spring AI dùng starter riêng và cấu hình riêng:

~~~groovy
dependencies {
    implementation "org.springframework.ai:spring-ai-starter-model-ollama"
}
~~~

Ví dụ **application.yml**:

~~~yaml
spring:
  ai:
    model:
      chat: ollama
    ollama:
      base-url: ${OLLAMA_BASE_URL:http://localhost:11434}
      chat:
        model: ${OLLAMA_CHAT_MODEL:qwen3}
~~~

Trước khi chạy ứng dụng, cần cài và khởi động Ollama, đồng thời tải model đã chọn theo hướng dẫn của Ollama:

~~~bash
ollama pull qwen3
ollama serve
~~~

Nếu Ollama chạy ở một máy khác, thay **OLLAMA_BASE_URL** bằng địa chỉ có thể truy cập từ máy chạy Spring Boot. Trong Docker network, dùng tên service hoặc hostname tương ứng thay vì mặc định **localhost**.

Không phải mọi model cục bộ đều hỗ trợ tool calling. Hãy xác nhận model có hỗ trợ tính năng này trong phiên bản Ollama đang dùng, rồi chạy thử một tool call đơn giản. Có thể dùng OpenAI starter với OpenAI-compatible endpoint của Ollama, nhưng khi đó cần cấu hình base URL, model và credential theo chế độ tương thích đó; không trộn lẫn property của Ollama native với property của OpenAI client.

## 8. Tổ chức cấu hình theo môi trường

Một ứng dụng thường có nhiều môi trường: local, test, staging và production. Nên giữ cấu hình không nhạy cảm trong file cấu hình, còn secret được inject từ môi trường hoặc secret manager.

Ví dụ **application-openai.yml**:

~~~yaml
spring:
  ai:
    model:
      chat: openai
    openai:
      api-key: ${OPENAI_API_KEY}
      base-url: ${OPENAI_BASE_URL:https://api.openai.com}
      chat:
        model: ${OPENAI_CHAT_MODEL:gpt-4o-mini}
~~~

Ví dụ **application-ollama.yml**:

~~~yaml
spring:
  ai:
    model:
      chat: ollama
    ollama:
      base-url: ${OLLAMA_BASE_URL:http://localhost:11434}
      chat:
        model: ${OLLAMA_CHAT_MODEL:qwen3}
~~~

Chọn profile khi chạy ứng dụng:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "openai"
.\mvnw.cmd spring-boot:run
~~~

Hoặc:

~~~bash
SPRING_PROFILES_ACTIVE=ollama ./mvnw spring-boot:run
~~~

Profile giúp chọn bộ cấu hình phù hợp với môi trường. Tuy nhiên, profile không phải cơ chế bảo mật; secret vẫn cần được cấp từ nguồn an toàn.

Trong Spring AI hiện hành, **spring.ai.model.chat** chọn cấu hình provider chat model được auto-configure. Khi nâng cấp từ phiên bản cũ, hãy kiểm tra lại tên property. Chẳng hạn, cấu hình model OpenAI cũ có thể dùng **spring.ai.openai.chat.options.model**, trong khi cấu hình hiện hành dùng **spring.ai.openai.chat.model**. Với Ollama cũng có khác biệt tương tự giữa **chat.options.model** và **chat.model**. Không nên đổi tên property chỉ dựa trên một ví dụ tìm thấy trên mạng mà chưa đối chiếu phiên bản đang dùng.

## 9. Kết nối ChatClient với tool calling

Sau khi starter và thông tin kết nối hợp lệ, Spring Boot có thể auto-configure **ChatModel** và **ChatClient.Builder**. Ứng dụng có thể tạo một **ChatClient** dùng chung:

~~~java
@Configuration
class AiClientConfiguration {

    @Bean
    ChatClient chatClient(ChatClient.Builder builder) {
        return builder
            .defaultSystem("""
                Bạn là trợ lý hỗ trợ tra cứu nghiệp vụ.
                Chỉ dùng công cụ được cung cấp khi cần dữ liệu nghiệp vụ.
                """)
            .build();
    }
}
~~~

Một tool nghiệp vụ có thể được cung cấp theo từng request:

~~~java
@Service
class InventoryAssistant {

    private final ChatClient chatClient;
    private final InventoryTools inventoryTools;

    InventoryAssistant(
            ChatClient chatClient,
            InventoryTools inventoryTools) {
        this.chatClient = chatClient;
        this.inventoryTools = inventoryTools;
    }

    String answer(String question, String authenticatedTenantId) {
        return chatClient.prompt()
            .user(question)
            .tools(inventoryTools)
            .toolContext(Map.of("tenantId", authenticatedTenantId))
            .call()
            .content();
    }
}
~~~

**authenticatedTenantId** phải đến từ principal hoặc security context đã xác thực. Không lấy tenant ID từ câu hỏi của người dùng hoặc để mô hình tự sinh ra. Phương thức tool vẫn phải kiểm tra quyền truy cập trước khi gọi service.

**ChatClient** hiện hành tự đăng ký **ToolCallingAdvisor** để xử lý tool call trong advisor chain. Có thể tắt cơ chế auto-registration bằng cấu hình **spring.ai.chat.client.tool-calling.enabled=false**; khi tắt, tool definition vẫn có thể được gửi cho model nhưng ứng dụng phải tự điều khiển việc thực thi. Nếu gọi trực tiếp **ChatModel** ở mức thấp, hãy kiểm tra API của phiên bản đang dùng: đường gọi này có thể chỉ trả về tool call để ứng dụng tự xử lý vòng lặp.

Không nên đưa tool ghi dữ liệu hoặc thao tác nhạy cảm thành default tool dùng chung cho mọi request. Chỉ cung cấp những tool mà người dùng hiện tại được phép sử dụng.

## 10. Kiểm tra cấu hình sau khi khởi động

Không nên chỉ dựa vào việc ứng dụng khởi động thành công để kết luận kết nối mô hình đã hoạt động. Một quy trình kiểm tra ngắn giúp phát hiện lỗi sớm:

1. Xác nhận đúng starter và phiên bản Spring AI đã được resolve.
2. Xác nhận profile mong muốn đã được kích hoạt.
3. Kiểm tra biến môi trường credential có sẵn trong đúng tiến trình chạy ứng dụng.
4. Xác nhận base URL, API path, DNS, proxy và TLS.
5. Xác nhận model ID hoặc deployment name tồn tại và được cấp quyền.
6. Gửi một prompt đơn giản để xác minh request/response.
7. Gửi một prompt yêu cầu sử dụng tool đọc dữ liệu thử nghiệm để xác minh tool calling.
8. Kiểm tra log không làm lộ API key, dữ liệu cá nhân hoặc tool arguments nhạy cảm.

Có thể phân loại một số lỗi thường gặp như sau:

| Triệu chứng | Nguyên nhân cần kiểm tra |
|---|---|
| 401 Unauthorized | API key thiếu, sai, hết hạn hoặc bị cấu hình override bởi chat-specific key |
| 403 Forbidden | Key không có quyền với project, model hoặc deployment |
| 404 Not Found | Sai base URL, API path, model ID hoặc deployment name |
| 400 Bad Request | Model không hỗ trợ option đã gửi, schema sai hoặc request không tương thích |
| Connection refused / timeout | Sai hostname/port, service chưa chạy, DNS, firewall, proxy hoặc container dùng nhầm **localhost** |
| 429 Too Many Requests | Hạn mức request/token, quota hoặc rate limit của provider |
| Model trả lời nhưng không gọi tool | Model không hỗ trợ tool calling, tool chưa được truyền vào request hoặc vòng thực thi tool đã bị tắt |

Không log toàn bộ request và response ở production nếu chúng có thể chứa secret, dữ liệu người dùng hoặc đối số nghiệp vụ. Khi cần chẩn đoán, ưu tiên log request ID, provider, model, thời gian xử lý và mã lỗi đã được làm sạch.

## 11. Kiểm thử mà không phụ thuộc API thật

Unit test và integration test thông thường không nên gọi API thật ở mỗi lần chạy. Request thật có thể phát sinh chi phí, phụ thuộc mạng, quota và trạng thái provider.

Có thể chia kiểm thử thành ba lớp:

| Lớp kiểm thử | Mục tiêu | Cách thực hiện |
|---|---|---|
| Kiểm tra cấu hình | Property được bind, profile đúng, bean được tạo | **@SpringBootTest** với cấu hình test và credential giả |
| Kiểm thử luồng ứng dụng | Prompt được gửi, tool được chọn và callback được gọi đúng | Mock **ChatModel** hoặc dùng model giả lập |
| Smoke test với provider | Credential, endpoint và model ID thực sự hoạt động | Chạy riêng theo profile hoặc pipeline có secret |

Smoke test cần được kích hoạt có chủ ý, tránh chạy trong mọi unit test. Nên dùng một request nhỏ, một model phù hợp và giới hạn tần suất để kiểm soát chi phí.

Khi kiểm thử tool calling, hãy xác minh cả hai phần: model trả về tool call có tên/đối số đúng và callback được thực thi với context do ứng dụng cấp. Kiểm thử thêm trường hợp thiếu quyền, sai đối số, timeout và lỗi provider.

## 12. Checklist trước khi tích hợp vào môi trường thật

- [ ] Dependency starter khớp với provider và phiên bản Spring AI.
- [ ] Spring AI BOM được dùng để đồng bộ phiên bản các module.
- [ ] API key lấy từ biến môi trường hoặc secret manager.
- [ ] Không có secret trong Git, prompt, log hoặc tool schema.
- [ ] Base URL và API path khớp với endpoint thật.
- [ ] Model ID hoặc deployment name đã được xác minh.
- [ ] Model hỗ trợ tool calling và các tính năng ứng dụng cần dùng.
- [ ] Model options tương thích với model đã chọn.
- [ ] Profile môi trường được kích hoạt đúng.
- [ ] **ChatClient** và vòng thực thi tool được cấu hình như mong muốn.
- [ ] Tool chỉ được cung cấp cho request có quyền phù hợp.
- [ ] Có timeout, retry hợp lý, logging đã làm sạch và smoke test riêng.

## Tài liệu tham khảo

- [Spring AI — OpenAI Chat](https://docs.spring.io/spring-ai/reference/api/chat/openai-chat.html): dependency starter, API key, base URL, chat model, options và tool calling.
- [Spring AI — Ollama Chat](https://docs.spring.io/spring-ai/reference/api/chat/ollama-chat.html): cấu hình server Ollama, model cục bộ và OpenAI API compatibility.
- [Spring AI — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html): auto-configuration của **ChatClient**, **ToolCallingAdvisor** và cách truyền tool theo request.
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): định nghĩa tool, callback, **ToolContext** và thực thi công cụ.

Tên property, starter và hành vi auto-configuration có thể thay đổi theo phiên bản. Luôn đối chiếu tài liệu cùng phiên bản Spring AI đang được quản lý trong BOM của dự án.

