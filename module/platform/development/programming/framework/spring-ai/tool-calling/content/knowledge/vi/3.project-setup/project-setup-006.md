# Tách môi trường kiểm thử khỏi tài nguyên sản xuất

Ứng dụng Spring AI có thể nhận yêu cầu gọi tool từ mô hình rồi thực thi yêu cầu đó bằng mã Java hoặc dịch vụ bên ngoài. Vì vậy, một lần chạy thử có thể đọc dữ liệu khách hàng, gửi thông báo, tạo giao dịch hoặc gọi sang một MCP server nếu ứng dụng đang trỏ đến tài nguyên sản xuất. Chỉ đổi tên profile thành `test` không đủ để bảo vệ hệ thống: các kết nối, thông tin xác thực và quyền thực thi cũng phải được tách riêng.

Trong module `SPRING_AI_TOOL_CALLING`, mục tiêu là để mô hình có thể đề nghị gọi công cụ thông qua `@Tool`, `ToolCallback` và schema đầu vào, trong khi ứng dụng giữ quyền kiểm soát thực thi, điều phối nhiều lượt gọi, xác thực quyền, xử lý lỗi và kiểm thử. Môi trường kiểm thử phải phản ánh được luồng đó bằng dữ liệu giả lập hoặc dịch vụ sandbox, đồng thời ngăn mọi thao tác thử nghiệm tác động đến dữ liệu và dịch vụ sản xuất.

## 1. Xác định những tài nguyên cần tách

Hãy lập danh sách các hệ thống mà ứng dụng có thể truy cập. Với một trợ lý nghiệp vụ dùng Spring AI, danh sách thường rộng hơn cơ sở dữ liệu chính:

| Thành phần | Tài nguyên cần tách giữa test và production | Rủi ro nếu dùng chung |
| --- | --- | --- |
| Mô hình và API AI | Project hoặc tài khoản, API key, quota, endpoint và giới hạn chi phí | Lộ dữ liệu thử nghiệm, tiêu thụ quota hoặc chi phí của production |
| Tool nghiệp vụ | API base URL, service account, OAuth scope và quyền thao tác | Tool thử nghiệm có thể đọc hoặc ghi dữ liệu thật |
| Cơ sở dữ liệu | Database/schema, tài khoản kết nối, dữ liệu và quyền | Ghi đè, xóa hoặc làm sai lệch dữ liệu sản xuất |
| RAG và vector store | Collection/index, namespace, credential và tập tài liệu | Tài liệu thử nghiệm lẫn vào tri thức thật hoặc truy xuất nhầm dữ liệu nhạy cảm |
| ChatMemory | Database/schema, bảng hoặc key prefix, khóa phân vùng và thời hạn lưu | Lịch sử của test lẫn vào hội thoại thật hoặc ngược lại |
| MCP | Server endpoint, danh sách tool được phép, credential và quyền của client | Client kiểm thử gọi nhầm tool có tác động thật |
| Hàng đợi và sự kiện | Broker, topic/queue, subscription và credential | Tin nhắn thử nghiệm kích hoạt consumer sản xuất |
| File và cache | Bucket/container, đường dẫn, cache namespace và credential | Ghi đè file, chia sẻ cache hoặc rò rỉ nội dung giữa môi trường |

Không phải dự án nào cũng có đủ các thành phần trên. Tuy nhiên, mỗi kết nối mà tool có thể sử dụng đều cần được phân loại theo môi trường và quyền truy cập. Một tool tưởng như chỉ đọc cũng có thể để lộ dữ liệu nếu nó dùng tài khoản production hoặc truy vấn sai tenant.

## 2. Chọn cấu hình theo Spring profile

Spring Boot hỗ trợ nhiều bộ cấu hình thông qua profile. Có thể dùng `application.yml` làm cấu hình chung, sau đó đặt phần khác nhau vào `application-local.yml`, `application-test.yml` và `application-prod.yml`. Profile được chọn khi khởi động ứng dụng; trên môi trường triển khai, nên để nền tảng chạy ứng dụng cấp giá trị `SPRING_PROFILES_ACTIVE`.

Ví dụ cấu trúc:

```text
src/main/resources/
  application.yml
  application-local.yml
  application-test.yml
  application-prod.yml
```

Đặt môi trường mặc định an toàn cho máy phát triển:

```yaml
# application.yml
spring:
  profiles:
    default: local

app:
  integrations:
    orders:
      mode: stub
```

Ví dụ cấu hình riêng cho kiểm thử:

```yaml
# application-test.yml
app:
  integrations:
    orders:
      mode: stub
    mcp:
      enabled: false
    rag:
      collection: tool-calling-test
    memory:
      namespace: tool-calling-test
```

Các thuộc tính dưới `app.integrations` trong ví dụ là cấu hình do ứng dụng tự định nghĩa; tên và cách bind chúng phụ thuộc vào lớp `@ConfigurationProperties` của dự án. Ý nghĩa cần giữ là test dùng adapter giả lập, tắt hoặc trỏ MCP đến server kiểm thử, đồng thời dùng vùng dữ liệu RAG và memory riêng.

Production nhận endpoint và thông tin xác thực từ môi trường triển khai hoặc secret manager:

```yaml
# application-prod.yml
app:
  integrations:
    orders:
      mode: http
      base-url: ${ORDERS_API_BASE_URL}
    mcp:
      enabled: true
      server-url: ${MCP_SERVER_URL}
    rag:
      collection: ${RAG_PROD_COLLECTION}
    memory:
      namespace: ${CHAT_MEMORY_PROD_NAMESPACE}
```

Không đặt `SPRING_PROFILES_ACTIVE=prod` trong cấu hình dùng chung của repository. Hãy để pipeline hoặc nền tảng triển khai chọn profile. Các biến chứa endpoint production và secret phải được cấp riêng cho workload production. Nếu thiếu biến bắt buộc, ứng dụng nên dừng khởi động với lỗi cấu hình rõ ràng thay vì tự chuyển sang một endpoint mặc định có thể trỏ nhầm môi trường.

Một profile chỉ là cơ chế chọn cấu hình và bean. Nó không phải ranh giới bảo mật độc lập. Quyền truy cập thực tế vẫn do credential, network policy và hệ thống đích quyết định. Vì thế, profile test cần đi kèm credential test không có quyền trên production.

## 3. Tách adapter nghiệp vụ và tool thực thi

Một cách dễ kiểm soát là để lớp tool phụ thuộc vào một interface nghiệp vụ. Mỗi môi trường cung cấp một implementation khác nhau: production dùng adapter gọi dịch vụ thật; local và test dùng adapter giả lập. Phương thức `@Tool` vẫn giữ cùng schema và quy tắc đầu vào ở tất cả môi trường.

Ví dụ interface cho chức năng tra cứu đơn hàng:

```java
public interface OrderGateway {
    OrderStatus findStatus(String orderId, String principalId);
}
```

Adapter production kết nối đến dịch vụ đơn hàng. Endpoint được đọc từ cấu hình bên ngoài:

```java
@Component
@Profile("prod")
class HttpOrderGateway implements OrderGateway {

    private final WebClient client;

    HttpOrderGateway(
            WebClient.Builder builder,
            @Value("${app.integrations.orders.base-url}") String baseUrl) {
        this.client = builder.baseUrl(baseUrl).build();
    }

    @Override
    public OrderStatus findStatus(String orderId, String principalId) {
        return client.get()
                .uri("/orders/{id}/status", orderId)
                .header("X-Principal-Id", principalId)
                .retrieve()
                .bodyToMono(OrderStatus.class)
                .block();
    }
}
```

Adapter local/test trả dữ liệu cố định hoặc lấy từ fixture:

```java
@Component
@Profile({"local", "test"})
class StubOrderGateway implements OrderGateway {

    @Override
    public OrderStatus findStatus(String orderId, String principalId) {
        if (!"TEST-100".equals(orderId)) {
            throw new OrderNotFoundException(orderId);
        }

        return new OrderStatus(orderId, "IN_TRANSIT");
    }
}
```

Tool sử dụng interface chung:

```java
@Component
class OrderTools {

    private final OrderGateway orderGateway;

    OrderTools(OrderGateway orderGateway) {
        this.orderGateway = orderGateway;
    }

    @Tool(description = "Tra cứu trạng thái đơn hàng mà người dùng hiện tại được phép xem")
    OrderStatus getOrderStatus(
            @ToolParam(description = "Mã đơn hàng cần tra cứu") String orderId,
            ToolContext toolContext) {

        Object value = toolContext.getContext().get("principalId");
        if (!(value instanceof String principalId) || principalId.isBlank()) {
            throw new AccessDeniedException("Thiếu danh tính người dùng đã xác thực");
        }

        return orderGateway.findStatus(orderId, principalId);
    }
}
```

Ứng dụng đăng ký `OrderTools` với `ChatClient` theo cơ chế tool của Spring AI:

```java
String answer = chatClient.prompt()
        .user(question)
        .tools(orderTools)
        .toolContext(Map.of("principalId", authenticatedPrincipalId))
        .call()
        .content();
```

Đây là ví dụ minh họa ranh giới giữa tool và dịch vụ nghiệp vụ; các kiểu `OrderStatus`, ngoại lệ, import và cấu hình `WebClient` cần được cung cấp trong dự án. `authenticatedPrincipalId` phải đến từ security context của ứng dụng sau khi xác thực. Không lấy danh tính hoặc quyền hạn từ tham số mà mô hình tự sinh. Dịch vụ đơn hàng vẫn phải xác minh quyền truy cập bản ghi.

Trong ví dụ, `X-Principal-Id` chỉ truyền ngữ cảnh người dùng qua một kết nối dịch vụ đã được xác thực; bản thân header này không phải bằng chứng danh tính. Khi triển khai, cần xác thực ứng dụng gọi bằng OAuth2 client credentials, mTLS hoặc cơ chế service-to-service tương đương. Dịch vụ đích chỉ tin thông tin principal từ một caller đã được xác thực và vẫn tự kiểm tra quyền trên đơn hàng.

Với `local` hoặc `test`, Spring tạo `StubOrderGateway`; với `prod`, Spring tạo `HttpOrderGateway`. Không kích hoạt đồng thời nhiều profile môi trường. Nếu hai implementation cùng được đăng ký mà không có qualifier, ứng dụng thường sẽ lỗi do không thể chọn duy nhất một bean `OrderGateway`; đây là lỗi khởi động cần được phát hiện sớm. Có thể bổ sung kiểm tra cấu hình khi khởi động để từ chối tổ hợp profile không hợp lệ.

Điểm quan trọng là test đang kiểm tra cùng lớp `OrderTools`, cùng schema và cùng bước kiểm tra `ToolContext` như production. Chỉ adapter phía sau interface được thay bằng implementation giả lập. Nhờ vậy, test có thể xác nhận logic điều phối và validation mà không gửi request đến hệ thống thật.

## 4. Cô lập dữ liệu cho RAG và ChatMemory

RAG và bộ nhớ hội thoại thường bị bỏ sót khi thiết kế môi trường. Dù không trực tiếp tạo giao dịch, chúng có thể đưa dữ liệu từ môi trường này sang môi trường khác trong prompt gửi đến mô hình.

**Đối với RAG và vector store:**

- Dùng collection/index hoặc instance riêng cho test. Nếu nền tảng chỉ hỗ trợ namespace, cần xác nhận namespace có phân quyền và credential độc lập; chỉ đổi tên collection trong code không ngăn được một tài khoản có quyền đọc toàn bộ dữ liệu.
- Nạp tài liệu tổng hợp, dữ liệu mẫu hoặc dữ liệu đã được ẩn danh. Không sao chép nguyên tập tài liệu sản xuất vào môi trường test nếu chưa có quy trình phê duyệt và bảo vệ dữ liệu phù hợp.
- Tách khóa truy cập và chính sách cập nhật index. Job nạp tài liệu test không được có quyền xóa hoặc cập nhật index production.
- Kiểm thử trường hợp không tìm thấy tài liệu và trường hợp người dùng không có quyền đọc tài liệu. Không để nội dung trả về từ retrieval tự cấp quyền gọi tool.

**Đối với ChatMemory:**

- Tách database/schema hoặc tối thiểu là bảng và namespace có phân quyền riêng. Conversation ID phải được tạo và kiểm tra ở phía ứng dụng.
- Dùng tài khoản database test chỉ có quyền trên vùng lưu trữ test. Không cho ứng dụng test dùng connection string production với lý do chỉ ghi vào một prefix khác.
- Xóa dữ liệu sau test hoặc đặt thời hạn lưu ngắn. Tránh lưu token, secret, thông tin cá nhân không cần thiết và payload tool có chứa dữ liệu nhạy cảm.
- Kiểm thử hai conversation độc lập để bảo đảm lịch sử không bị trộn. Kiểm thử cả tình huống không tìm thấy memory để ứng dụng không lấy nhầm cuộc trò chuyện khác.

Nếu RAG hoặc ChatMemory được cung cấp qua MCP resource hay một dịch vụ từ xa, endpoint và credential của dịch vụ đó cũng phải được tách. Một server MCP test có thể cung cấp dữ liệu giả lập; không cấu hình MCP client test kết nối đến server production chỉ để tiết kiệm công dựng môi trường.

## 5. Tách MCP và danh sách tool được phép

MCP giúp ứng dụng kết nối đến server công bố tools, resources hoặc prompts. Một MCP client trong môi trường kiểm thử có thể khám phá tool và đưa callback tương ứng vào luồng `ChatClient`. Nếu client dùng nhầm endpoint production, một bài test có thể gọi đúng tool thật với tham số thử nghiệm.

Nên áp dụng các nguyên tắc sau:

1. **Mỗi môi trường có endpoint riêng.** Local/test dùng MCP server chạy cục bộ, server giả lập hoặc sandbox được cấp riêng. Production chỉ nhận endpoint từ cấu hình triển khai production.
2. **Allowlist tool theo tác vụ.** Chỉ đưa các tool cần thiết vào `ToolCallbackProvider` hoặc danh sách callback của request. Không tự động công bố toàn bộ tool mà server trả về nếu ứng dụng không cần dùng chúng.
3. **Tách credential và scope.** Token của MCP client test chỉ có quyền trên tài nguyên test. Không tái sử dụng token production trong file cấu hình hoặc pipeline test.
4. **Giới hạn tác động.** Cấu hình timeout, giới hạn kích thước kết quả và giới hạn số vòng gọi. Các tool có thể ghi dữ liệu nên dùng fixture, sandbox hoặc implementation giả lập trong test.
5. **Kiểm tra server trước khi dùng.** Xác minh danh tính server, transport, chứng thư hoặc cơ chế xác thực phù hợp. Không xem tên tool và mô tả do server trả về là bằng chứng server đáng tin cậy.

Ví dụ, môi trường test có thể tắt MCP từ xa và đăng ký tool giả lập trong ứng dụng. Một bài kiểm thử contract riêng có thể khởi chạy MCP server test để xác nhận client khám phá đúng tên tool, schema và kết quả. Việc kiểm thử với MCP server production không cần thiết để xác minh contract.

Khi tích hợp MCP tools vào Spring AI, các callback từ MCP client có thể được truyền cho `ChatClient` cùng với callback nội bộ. Cách khởi tạo `McpSyncClient`, `McpAsyncClient`, provider và transport thay đổi theo phiên bản Spring AI và starter được sử dụng; hãy khóa phiên bản và đối chiếu API tương ứng. Dù dùng API nào, endpoint và danh sách tool phải được chọn từ cấu hình môi trường, không để nội dung do mô hình tạo ra thay đổi địa chỉ server hoặc credential.

## 6. Quản lý API key và quyền truy cập

Môi trường test cần danh tính riêng cho từng hệ thống tích hợp. Một API key AI dùng cho thử nghiệm không nên có cùng project, quota hoặc quyền truy cập dữ liệu với key production. Tương tự, tài khoản của tool nghiệp vụ, vector store, MCP client, database và message broker cần quyền tối thiểu.

Các quy tắc thực hành:

- Không commit API key, access token, mật khẩu hoặc private key vào Git, kể cả trong `application-test.yml` hay file `.env` mẫu chứa giá trị thật.
- Dùng biến môi trường, secret manager hoặc cơ chế cấp secret của nền tảng triển khai. File mẫu chỉ chứa tên biến và giá trị giả.
- Dùng credential test có thể thu hồi độc lập. Nếu một key bị lộ, việc thu hồi không làm gián đoạn production.
- Giới hạn scope theo đúng tác vụ. Tool tra cứu chỉ cần quyền đọc; tool tạo yêu cầu chỉ cần quyền tạo loại yêu cầu được phép.
- Không đưa secret vào prompt, `ToolContext` nếu tool không cần, lịch sử hội thoại hoặc log. `ToolContext` là nơi truyền dữ liệu tin cậy cho lần thực thi, nhưng không phải kho bí mật.
- Đặt quota và cảnh báo chi phí cho project AI test. Với kiểm thử tự động, ưu tiên mock `ChatModel` hoặc model giả lập để tránh gọi nhà cung cấp ở mỗi lần chạy.

Một pipeline có thể dùng secret store riêng cho test và production. Quyền đọc secret production chỉ được cấp cho workload production; runner CI không nên có quyền lấy secret production chỉ vì nó có quyền chạy test.

## 7. Ngăn kết nối nhầm sang production

Phân tách cấu hình cần được củng cố bằng kiểm soát ở tầng hạ tầng. Nếu một biến môi trường bị cấu hình nhầm, mạng và credential vẫn phải ngăn ứng dụng test truy cập hệ thống sản xuất.

- **Network policy:** runner và workload test chỉ được kết nối đến database, API, broker, vector store và MCP server test. Chặn egress đến các dải địa chỉ hoặc endpoint production khi có thể.
- **DNS và endpoint:** dùng hostname khác nhau, dễ nhận diện theo môi trường. Không dùng một hostname chung rồi dựa vào path hoặc tham số do ứng dụng tự chọn để phân biệt test và prod.
- **Identity:** tài khoản test không được cấp quyền trên project, subscription, database hoặc tenant production. Tách cả quyền đọc vì dữ liệu đọc được vẫn có thể bị đưa vào prompt hoặc log.
- **Dữ liệu:** ưu tiên dữ liệu tổng hợp. Nếu phải dùng dữ liệu sao chép đã ẩn danh, cần có quy trình kiểm tra khả năng tái nhận diện, giới hạn người truy cập và thời hạn lưu.
- **Tác động bên ngoài:** email, SMS, webhook, thanh toán và thông báo trong test nên được chuyển đến hộp thư, số điện thoại, endpoint hoặc sandbox giả lập. Không để bài test gửi thông báo thật cho khách hàng.
- **Quan sát:** log và trace cần ghi môi trường, tên tool, thời gian, mã tương quan và trạng thái thực thi. Che dữ liệu nhạy cảm và không ghi toàn bộ prompt hoặc kết quả tool một cách mặc định.

Đặc biệt với tool có tác động ghi, có thể bổ sung cơ chế xác nhận hoặc phê duyệt ở tầng ứng dụng. Dù mô hình yêu cầu gọi tool thành công, dịch vụ nghiệp vụ vẫn phải kiểm tra quyền, trạng thái và điều kiện trước khi thực hiện thao tác.

## 8. Chiến lược kiểm thử theo từng lớp

Không phải bài kiểm thử nào cũng cần gọi mô hình thật hoặc truy cập mọi dịch vụ. Chia kiểm thử theo mục tiêu giúp nhanh chóng phát hiện lỗi cấu hình và giữ cho môi trường test an toàn.

| Lớp kiểm thử | Thành phần sử dụng | Điều cần xác minh |
| --- | --- | --- |
| Unit test | Tool class, fake gateway, dữ liệu fixture | Schema/validation, xử lý tham số sai, phân quyền và kết quả tool |
| Application integration test | Spring context với profile `test`, adapter giả lập, model mock | Bean đúng profile, callback được đăng ký, điều phối kết quả và lỗi |
| Contract test | MCP server test hoặc API sandbox | Endpoint, schema, kiểu dữ liệu, timeout và ánh xạ lỗi |
| RAG/Memory integration test | Vector store và memory test riêng | Phân vùng dữ liệu, truy xuất, khôi phục hội thoại và xóa dữ liệu |
| Acceptance test | Toàn bộ ứng dụng trên môi trường staging cô lập | Luồng người dùng hoàn chỉnh, quyền, log, retry và tác động nghiệp vụ |

Ví dụ kiểm tra ứng dụng khởi động với profile test:

```java
@SpringBootTest
@ActiveProfiles("test")
class ToolCallingEnvironmentTest {

    @Autowired
    OrderGateway orderGateway;

    @Test
    void testProfileUsesStubOrderGateway() {
        OrderStatus status =
                orderGateway.findStatus("TEST-100", "test-user");

        assertThat(status.status()).isEqualTo("IN_TRANSIT");
    }
}
```

Test này minh họa rằng profile `test` dùng dữ liệu cố định từ `StubOrderGateway`. Tên record accessor trong assertion cần khớp với kiểu `OrderStatus` của dự án. Có thể thêm một kiểm tra cấu hình để xác nhận không có bean kết nối HTTP production trong application context test.

Với luồng tool calling nhiều lượt, nên có một kịch bản tích hợp kiểm tra các bước sau:

1. Người dùng hỏi về một đơn hàng test. Mô hình hoặc model giả lập phát ra yêu cầu gọi `getOrderStatus` với mã đơn hàng trong fixture.
2. Ứng dụng xác thực người dùng, truyền `principalId` tin cậy qua `ToolContext` và gọi tool.
3. Tool gọi `StubOrderGateway`; test xác nhận không có HTTP request ra ngoài.
4. Kết quả tool được đưa trở lại chuỗi thông điệp để mô hình tạo câu trả lời.
5. Nếu người dùng yêu cầu tạo giao dịch, tool ghi phải kiểm tra quyền và điều kiện. Test xác nhận chỉ adapter sandbox nhận lệnh và retry không tạo bản ghi trùng.

Ngoài luồng thành công, cần kiểm thử thiếu quyền, mã đơn hàng không hợp lệ, tool timeout, MCP server mất kết nối, RAG không có tài liệu, memory không có lịch sử và lỗi khi lưu kết quả. Mỗi trường hợp phải cho kết quả xác định và không được âm thầm chuyển sang endpoint production.

## 9. Checklist trước khi chạy kiểm thử

Trước khi chạy integration test hoặc acceptance test, hãy xác nhận các điểm sau:

- [ ] Profile đang hoạt động là `test` hoặc profile sandbox được chỉ định.
- [ ] Adapter nghiệp vụ được chọn là fake/stub hoặc sandbox, không phải adapter production.
- [ ] Không có API key, database credential hoặc token production trong môi trường runner.
- [ ] API AI test dùng project/key riêng, hoặc model được mock cho bài test không cần gọi nhà cung cấp.
- [ ] RAG collection và ChatMemory namespace/database là vùng test độc lập.
- [ ] MCP client trỏ đến server test hoặc bị tắt; tool allowlist chỉ chứa chức năng cần kiểm thử.
- [ ] Database, queue, bucket, webhook và dịch vụ thông báo đều là tài nguyên test.
- [ ] Network policy chặn runner test truy cập endpoint production.
- [ ] Dữ liệu test là dữ liệu tổng hợp hoặc đã được xử lý theo chính sách dữ liệu.
- [ ] Log không chứa secret, prompt nhạy cảm hoặc payload tool không cần thiết.
- [ ] Test có bước dọn dữ liệu và không để lại tác động ngoài dự kiến.

Việc tách môi trường chỉ hoàn chỉnh khi cấu hình ứng dụng, adapter, credential, dữ liệu và mạng cùng chỉ đến tài nguyên đúng môi trường. Khi đó, nhóm phát triển có thể kiểm tra schema, callback, điều phối nhiều lượt, quyền và xử lý lỗi của Spring AI một cách lặp lại được, trong khi hệ thống production vẫn được bảo vệ bởi các ranh giới truy cập độc lập.
