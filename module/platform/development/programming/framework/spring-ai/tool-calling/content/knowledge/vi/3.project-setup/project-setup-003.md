# Chọn starter và mô hình có hỗ trợ gọi công cụ

Để một ứng dụng Spring AI gọi được công cụ, cần chọn đúng cả thư viện tích hợp nhà cung cấp và mô hình chat. Starter cung cấp implementation `ChatModel` cùng cấu hình tự động cho một nhà cung cấp; mô hình được chọn phải hỗ trợ tool calling ở API và phiên bản đang sử dụng. Sau đó ứng dụng mới đăng ký `ToolCallback` hoặc đối tượng có phương thức `@Tool` để Spring AI chuyển yêu cầu của mô hình thành lời gọi mã ứng dụng.

Ba điều kiện này liên quan nhưng độc lập. Có starter không đồng nghĩa mọi mô hình của nhà cung cấp đều hỗ trợ gọi công cụ. Một mô hình có hỗ trợ tool calling cũng chưa đủ nếu endpoint, API version hoặc integration mà ứng dụng đang dùng không hỗ trợ tính năng đó. Cuối cùng, việc mô hình yêu cầu gọi công cụ không tự cấp quyền thực hiện hành động nghiệp vụ.

## Xác định yêu cầu trước khi chọn

Trước khi thêm dependency, hãy xác định cách ứng dụng sẽ sử dụng công cụ:

- Ứng dụng chỉ cần mô hình yêu cầu một công cụ rồi chờ kết quả, hay cần nhiều lượt gọi liên tiếp để hoàn thành một yêu cầu?
- Có cần một phản hồi chứa nhiều tool call, gọi song song, hoặc ép mô hình chọn một công cụ cụ thể không?
- Công cụ chỉ đọc dữ liệu hay có thể tạo, cập nhật, xóa dữ liệu hoặc gây tác động bên ngoài?
- Dữ liệu có được phép gửi đến dịch vụ mô hình bên ngoài không, hay phải chạy trong hạ tầng riêng?
- Ứng dụng cần thời gian phản hồi, giới hạn chi phí, khu vực lưu trữ và mức độ sẵn sàng như thế nào?

Các câu trả lời này giúp thu hẹp lựa chọn nhà cung cấp và model. Với một bài thực hành đầu tiên, nên bắt đầu bằng một mô hình chat có tài liệu xác nhận hỗ trợ function/tool calling, một công cụ chỉ đọc đơn giản và một tập dữ liệu thử nghiệm không nhạy cảm.

## Bốn lớp cần tương thích

| Lớp | Cần xác nhận | Vì sao cần xác nhận |
| --- | --- | --- |
| Spring Boot và Spring AI | Phiên bản Spring AI tương thích với phiên bản Spring Boot của dự án | Starter và API có thể thay đổi giữa các dòng phiên bản. |
| Starter/provider integration | Integration có hỗ trợ tool calling cho loại API đang sử dụng | Starter tạo `ChatModel`, ánh xạ request/response và truyền định nghĩa công cụ đến nhà cung cấp. |
| Model hoặc deployment | Model cụ thể hỗ trợ tool calling trên endpoint và API version được cấu hình | Tính năng có thể khác nhau giữa các model, deployment hoặc endpoint trong cùng một nhà cung cấp. |
| Công cụ của ứng dụng | Schema đầu vào, callback và chính sách quyền được thiết kế đúng | Mô hình chỉ tạo yêu cầu; ứng dụng chịu trách nhiệm xác thực và thực thi. |

Không nên suy ra khả năng gọi công cụ từ tên nhà cung cấp hoặc tên starter. Hãy kiểm tra ma trận tính năng và tài liệu của đúng model, đúng endpoint và đúng phiên bản integration trước khi quyết định.

## Chọn starter theo nhà cung cấp

Spring AI cung cấp starter riêng cho các integration mô hình. Với Spring AI 1.x, một số artifact thường gặp gồm:

| Nhà cung cấp / môi trường | Maven artifact | Điều cần kiểm tra |
| --- | --- | --- |
| OpenAI | `spring-ai-starter-model-openai` | Model chat và endpoint được chọn có hỗ trợ tool calling; tài khoản có quyền dùng model đó. |
| Azure OpenAI | `spring-ai-starter-model-azure-openai` | Deployment trỏ đến model hỗ trợ tool calling; API version và cấu hình Azure tương thích. |
| Anthropic | `spring-ai-starter-model-anthropic` | Model Claude được chọn có hỗ trợ tool use và integration đang dùng hỗ trợ các tham số cần thiết. |
| Ollama | `spring-ai-starter-model-ollama` | Phiên bản Ollama và model cục bộ cụ thể có hỗ trợ tool calling; khả năng có thể khác nhau giữa các model. |

Tên artifact có thể khác ở các dòng Spring AI cũ. Nếu dự án đang dùng phiên bản trước 1.x, hãy tra đúng tài liệu của phiên bản đó thay vì sao chép tên starter 1.x. Không trộn starter từ nhiều dòng phiên bản trong cùng một ứng dụng.

### Lựa chọn khởi đầu đề xuất

Với ứng dụng thử nghiệm cần kiểm chứng luồng gọi công cụ nhanh, có thể bắt đầu bằng OpenAI starter và một model chat được tài liệu của nhà cung cấp xác nhận hỗ trợ function calling. Cách này có cấu hình tương đối trực tiếp: API key, model ID và một `ChatClient` được tạo từ `ChatModel` tự động cấu hình.

Nếu hệ thống đang vận hành trên Azure, cần quản trị deployment tập trung hoặc có yêu cầu về mạng và danh tính trong Azure, hãy chọn Azure OpenAI starter. Nếu dữ liệu phải ở trong hạ tầng riêng, có thể đánh giá Ollama, nhưng phải thử chính model cục bộ dự kiến triển khai; việc Ollama hỗ trợ tool calling không có nghĩa mọi model tải về đều hỗ trợ. Với Anthropic, cần xác nhận model cụ thể có tool use và endpoint đang sử dụng đáp ứng yêu cầu của ứng dụng.

## Quản lý phiên bản bằng Spring AI BOM

Hãy dùng Spring AI BOM để các dependency trong cùng hệ sinh thái có phiên bản đồng bộ. Ví dụ Maven dưới đây minh họa cách thêm OpenAI starter; giá trị phiên bản cần được chọn theo ma trận tương thích Spring Boot và Spring AI của dự án.

```xml
<properties>
    <spring-ai.version>YOUR_COMPATIBLE_SPRING_AI_VERSION</spring-ai.version>
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
```

Với Gradle Kotlin DSL, ý tưởng tương đương:

```kotlin
dependencies {
    implementation(platform("org.springframework.ai:spring-ai-bom:$springAiVersion"))
    implementation("org.springframework.ai:spring-ai-starter-model-openai")
}
```

Không tự đặt một phiên bản riêng cho starter nếu BOM đã quản lý phiên bản. Khi nâng Spring AI, cần nâng BOM và kiểm tra lại API, starter name, thuộc tính cấu hình cũng như khả năng tool calling của provider integration.

## Cấu hình model và thông tin xác thực

Ví dụ cấu hình OpenAI trong `application.yml`:

```yaml
spring:
  ai:
    openai:
      api-key: ${OPENAI_API_KEY}
      chat:
        options:
          model: ${OPENAI_CHAT_MODEL}
          temperature: 0.2
```

`OPENAI_API_KEY` là biến môi trường chứa khóa API. `OPENAI_CHAT_MODEL` là model ID mà tài khoản và endpoint đang sử dụng được phép gọi, đồng thời phải hỗ trợ tool calling. Có thể đặt model ID trong cấu hình môi trường để chuyển model giữa môi trường phát triển, kiểm thử và triển khai mà không sửa mã Java.

Ví dụ thiết lập biến môi trường trong PowerShell:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
$env:OPENAI_CHAT_MODEL = "your-tool-capable-chat-model"
```

Không đưa API key vào Git, file cấu hình dùng chung, log hoặc ảnh chụp màn hình. Trong môi trường triển khai, lấy khóa từ secret manager hoặc cơ chế quản lý bí mật của nền tảng. Nếu dùng Azure OpenAI, Anthropic hoặc Ollama, hãy sử dụng nhóm thuộc tính kết nối tương ứng với starter đã chọn; không sao chép nguyên cấu hình `spring.ai.openai` sang provider khác.

Model ID phải là định danh được endpoint chấp nhận. Với Azure OpenAI, giá trị cấu hình thường liên quan đến tên deployment do tổ chức tạo, không nhất thiết trùng tên model gốc. Với Ollama, cần bảo đảm model đã được tải và runtime đang lắng nghe tại địa chỉ mà ứng dụng cấu hình.

## Tạo ChatClient từ starter

Khi starter và cấu hình hợp lệ, Spring Boot tự cấu hình một `ChatModel` cho provider. Có thể tạo `ChatClient` từ builder được Spring AI cung cấp:

```java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class AiConfiguration {

    @Bean
    ChatClient chatClient(ChatClient.Builder builder) {
        return builder.build();
    }
}
```

Nếu ứng dụng có nhiều `ChatModel`, hãy cấu hình rõ model nào được dùng để tạo từng `ChatClient`, tránh phụ thuộc vào lựa chọn bean mặc định không chủ ý. Cũng nên giữ cấu hình provider ở ngoài lớp nghiệp vụ để có thể thay đổi endpoint hoặc model mà không phải sửa logic công cụ.

## Kiểm chứng model có gọi được công cụ

Một lần chat trả về văn bản thành công chưa chứng minh tool calling hoạt động. Hãy thực hiện một phép thử có callback được kiểm soát để xác nhận cả ba việc: định nghĩa công cụ được gửi đến model, callback thực sự được thực thi và kết quả callback được đưa trở lại hội thoại.

Ví dụ một công cụ chỉ đọc:

```java
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;

@Component
class DemoCatalogTools {

    @Tool(description = "Tra cứu tên sản phẩm theo mã SKU")
    public String findProductName(
            @ToolParam(description = "Mã SKU cần tra cứu") String sku) {
        if (!"SKU-100".equals(sku)) {
            return "Không tìm thấy sản phẩm";
        }
        return "Bàn phím cơ thử nghiệm";
    }
}
```

Đăng ký công cụ trong một yêu cầu `ChatClient`:

```java
String answer = chatClient.prompt()
    .user("Hãy tra cứu tên sản phẩm có mã SKU-100 rồi trả lời tôi.")
    .tools(demoCatalogTools)
    .call()
    .content();
```

Trong ví dụ này, `demoCatalogTools` là bean được inject vào service chứa đoạn gọi `ChatClient`. Các import và API cụ thể cần khớp với phiên bản Spring AI của dự án. Khi kiểm thử, nên dùng một callback có thể quan sát số lần gọi hoặc mock service phía sau callback; không chỉ kiểm tra câu trả lời có nhắc đến tên sản phẩm.

Mô hình có quyền quyết định có cần gọi công cụ hay không dựa trên yêu cầu và mô tả công cụ. Vì vậy, một câu prompt không rõ ràng hoặc không cần dữ liệu từ công cụ có thể khiến model trả lời trực tiếp. Để kiểm chứng, hãy yêu cầu một thông tin chỉ callback thử nghiệm mới cung cấp và xác nhận callback đã được gọi.

## Tiêu chí đánh giá model trước khi chốt

| Tiêu chí | Câu hỏi đánh giá | Cách kiểm tra |
| --- | --- | --- |
| Tool calling cơ bản | Model có tạo tool call theo schema đã cung cấp không? | Gọi một công cụ chỉ đọc với tham số đơn giản. |
| Chất lượng tham số | Model có điền đúng kiểu, trường bắt buộc và giá trị giới hạn không? | Thử đầu vào tự nhiên có nhiều cách diễn đạt và trường dễ nhầm. |
| Nhiều công cụ | Model có chọn đúng công cụ khi có nhiều mô tả gần nhau không? | Đăng ký hai công cụ có mục đích khác nhau và thử nhiều yêu cầu. |
| Nhiều lượt | Model có dùng kết quả công cụ trước để quyết định bước tiếp theo không? | Thiết kế một kịch bản cần tra cứu rồi mới tính toán hoặc tổng hợp. |
| Khả năng song song | Provider, model và integration có hỗ trợ nhiều tool call trong một phản hồi không? | Kiểm tra tài liệu và chạy thử; không suy ra từ việc hỗ trợ một tool call. |
| Schema nâng cao | Có hỗ trợ các kiểu dữ liệu và ràng buộc schema mà ứng dụng cần không? | Thử schema thực tế, bao gồm trường tùy chọn, enum và cấu trúc lồng nhau. |
| Vận hành | Độ trễ, chi phí, giới hạn tốc độ và độ ổn định có đáp ứng không? | Đo trên tập yêu cầu đại diện và môi trường gần với triển khai. |
| Quyền riêng tư | Dữ liệu gửi đến provider có đáp ứng chính sách tổ chức không? | Đối chiếu hợp đồng, vùng xử lý dữ liệu và chính sách nội bộ. |

Model tốt cho hội thoại thông thường chưa chắc là model phù hợp cho luồng tool calling. Cần đánh giá trên các công cụ, schema và câu hỏi gần với nghiệp vụ thực tế. Nếu ứng dụng cần nhiều tool call, schema phức tạp hoặc kết quả ổn định, hãy đưa các tình huống đó vào bộ kiểm thử lựa chọn model.

## Các lỗi thường gặp khi cấu hình

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy starter hoặc dependency | Artifact name không đúng dòng Spring AI đang dùng hoặc BOM chưa được cấu hình | Đối chiếu đúng tài liệu phiên bản; dùng BOM và starter cùng dòng. |
| Không tạo được `ChatModel` hoặc `ChatClient.Builder` | Starter thiếu, cấu hình provider chưa hợp lệ hoặc auto-configuration không được kích hoạt | Kiểm tra dependency, cấu hình endpoint, API key và điều kiện auto-configuration. |
| Gọi chat thường thành công nhưng không có tool call | Model/deployment không hỗ trợ, endpoint không hỗ trợ, công cụ chưa được gắn vào request hoặc prompt không cần công cụ | Kiểm tra ma trận hỗ trợ, đúng model ID/API version, đăng ký `.tools(...)` và thử prompt yêu cầu dữ liệu chỉ công cụ có. |
| Provider từ chối request có tools | Schema hoặc tham số không tương thích, model không hỗ trợ tính năng, hoặc API version sai | Đọc lỗi trả về, giản lược schema để cô lập nguyên nhân và đối chiếu giới hạn của provider. |
| Không xác thực được | API key sai, thiếu quyền, endpoint hoặc deployment không đúng | Kiểm tra secret, quyền truy cập, địa chỉ endpoint và tên deployment; không ghi khóa vào log. |
| Ứng dụng gọi công cụ nhiều lần ngoài dự kiến | Prompt không rõ, mô tả công cụ trùng lặp hoặc kết quả công cụ không đủ để mô hình kết thúc | Làm rõ mô tả, chuẩn hóa kết quả và giới hạn số vòng gọi ở tầng điều phối. |

Khi model trả lời bằng văn bản thay vì tool call, không nên kết luận ngay provider bị lỗi. Trước hết xác nhận callback có được cung cấp trong chính request, mô tả công cụ có dễ hiểu, yêu cầu có thật sự cần công cụ và model có hỗ trợ tool calling trên endpoint hiện tại hay không.

## Kiểm soát quyền ngay từ bước chọn công cụ

Starter và model quyết định cách ứng dụng giao tiếp với nhà cung cấp. Chúng không phải lớp phân quyền nghiệp vụ. Chỉ đăng ký những công cụ cần thiết cho từng luồng; không đưa callback quản trị hoặc callback có quyền rộng vào mọi yêu cầu.

Với công cụ đọc dữ liệu, callback phải xác định người dùng và tenant từ ngữ cảnh đáng tin cậy do ứng dụng truyền vào. Với công cụ có tác động phụ như tạo đơn, hủy giao dịch hoặc gửi thông báo, cần kiểm tra quyền ở service, xác nhận hành động khi nghiệp vụ yêu cầu và bảo vệ thao tác lặp bằng idempotency phù hợp. Không dùng prompt, mô tả công cụ hay JSON Schema làm cơ chế bảo mật.

## Quy trình chọn và xác nhận cấu hình

1. Chốt phiên bản Spring Boot và chọn dòng Spring AI tương thích.
2. Chọn provider dựa trên yêu cầu triển khai, quyền riêng tư, chi phí và độ trễ.
3. Thêm đúng starter của provider và quản lý phiên bản bằng Spring AI BOM.
4. Chọn model hoặc deployment có tài liệu xác nhận hỗ trợ tool calling trên endpoint sẽ sử dụng.
5. Cấu hình API key, endpoint và model ID qua biến môi trường hoặc secret manager.
6. Tạo `ChatClient` và gắn một callback thử nghiệm chỉ đọc.
7. Kiểm chứng callback được thực thi và kết quả quay lại hội thoại; thử cả tham số sai, lỗi service và trường hợp người dùng thiếu quyền.
8. Đo chất lượng, độ trễ và chi phí trên các kịch bản nghiệp vụ trước khi chốt model cho môi trường triển khai.

Khi hoàn thành các bước này, dự án có nền tảng tương thích để triển khai các công cụ nghiệp vụ. Việc chọn đúng starter giúp Spring AI kết nối với provider; việc chọn đúng model bảo đảm provider có thể nhận yêu cầu tool calling; còn tính đúng đắn và an toàn của thao tác vẫn do ứng dụng kiểm soát.
