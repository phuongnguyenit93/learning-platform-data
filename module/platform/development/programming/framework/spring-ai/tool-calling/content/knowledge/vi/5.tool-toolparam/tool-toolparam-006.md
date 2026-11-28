# Dependency injection cho lớp chứa công cụ

Một phương thức được đánh dấu **@Tool** có thể gọi dịch vụ nghiệp vụ giống như bất kỳ phương thức Java nào khác. Khi công cụ cần truy vấn kho dữ liệu, gọi API nội bộ hoặc dùng một thành phần xử lý nghiệp vụ, lớp chứa công cụ cần nhận các dependency đó từ Spring. Đây là vai trò của dependency injection (DI).

Trong Spring AI, có thể đăng ký lớp chứa phương thức **@Tool** thành một Spring bean rồi truyền bean đó vào yêu cầu **ChatClient**. Spring quản lý việc tạo đối tượng và nối các dependency; Spring AI dùng đối tượng được cung cấp để công bố tool definition và điều phối lời gọi. Nhờ vậy, lớp tool tập trung vào việc chuyển đầu vào của mô hình thành lời gọi nghiệp vụ, còn dịch vụ nghiệp vụ vẫn được quản lý theo kiến trúc Spring của ứng dụng.

## 1. Mục tiêu và kiến trúc

Sau bài này, bạn có thể:

- Giải thích vì sao lớp chứa công cụ cần được Spring quản lý.
- Dùng constructor injection để đưa service hoặc repository vào lớp tool.
- Đăng ký lớp tool bằng **@Component** hoặc phương thức **@Bean**.
- Tiêm lớp tool vào service điều phối hội thoại và cung cấp nó qua **ChatClient.tools(...)**.
- Thiết kế tool bean không giữ trạng thái theo từng người dùng hoặc từng request.
- Kiểm thử lớp tool độc lập và kiểm tra việc Spring nối dependency.

Ta dùng ví dụ công cụ tra cứu tồn kho theo SKU. Công cụ chỉ đọc số lượng có thể bán và trạng thái tồn kho. Lớp tool gọi một interface nghiệp vụ; implementation của interface dùng repository để đọc dữ liệu.

~~~mermaid
flowchart TD
    U[Người dùng] --> A[InventoryAssistant]
    A --> C[ChatClient]
    C --> M[Mô hình]
    M -->|Tool call: sku| C
    C --> T[InventoryTools]
    T --> S[InventoryQueryService]
    S --> R[ProductRepository]
    R --> D[(Cơ sở dữ liệu)]
    S --> T
    T --> C
    C --> M
    M --> A
    A --> U
~~~

Spring chịu trách nhiệm tạo và nối các bean như **InventoryTools**, **InventoryQueryService** và **ProductRepository**. Spring AI sử dụng đối tượng tool khi xử lý yêu cầu chat. Mô hình chỉ chọn công cụ và tạo đối số; nó không tạo bean, không gọi constructor và không tự truy cập repository.

## 2. Vì sao nên dùng dependency injection?

Giả sử lớp tool tự tạo service bằng từ khóa **new**:

~~~java
public class InventoryTools {

    private final InventoryQueryService inventoryQueryService;

    public InventoryTools(ProductRepository productRepository) {
        this.inventoryQueryService =
            new DefaultInventoryQueryService(productRepository);
    }
}
~~~

Cách viết này khiến lớp tool tự quyết định implementation cần dùng và tự lắp một dependency của nó. Khi service cần thêm cấu hình, cache, transaction hoặc một dependency khác, lớp tool phải tự xây dựng cả chuỗi đối tượng. Việc kiểm thử cũng khó hơn vì không thể dễ dàng thay service bằng mock hoặc fake.

Với DI, lớp tool khai báo rõ dependency qua constructor:

~~~java
public class InventoryTools {

    private final InventoryQueryService inventoryQueryService;

    public InventoryTools(InventoryQueryService inventoryQueryService) {
        this.inventoryQueryService = inventoryQueryService;
    }
}
~~~

Spring tìm bean phù hợp với kiểu **InventoryQueryService**, tạo hoặc lấy instance theo scope đã cấu hình rồi truyền vào constructor. Lớp tool không cần biết implementation được tạo như thế nào.

DI mang lại một số lợi ích cụ thể:

- **Tách trách nhiệm:** lớp tool điều phối đầu vào và kết quả; service thực hiện quy tắc nghiệp vụ; repository làm việc với dữ liệu.
- **Dễ thay implementation:** có thể dùng implementation thật trong production và fake hoặc mock trong kiểm thử.
- **Quản lý vòng đời:** Spring quản lý việc tạo, cấu hình, inject và hủy bean theo lifecycle.
- **Dễ cấu hình:** dependency có thể được thay đổi theo môi trường hoặc profile mà không sửa lớp tool.
- **Dễ quan sát:** constructor thể hiện rõ những thành phần mà lớp tool cần để hoạt động.

## 3. Khai báo hợp đồng nghiệp vụ

Trước tiên, định nghĩa kiểu kết quả và interface mà lớp tool sẽ sử dụng. Ví dụ sau chỉ là hợp đồng tối thiểu; trong dự án, hãy dùng model và service hiện có nếu chúng đã cung cấp cùng khả năng:

~~~java
public record InventorySnapshot(
    String sku,
    int availableQuantity,
    boolean available
) {}

public interface InventoryQueryService {
    InventorySnapshot findBySku(String sku);
    // Dùng khi ứng dụng cần giới hạn truy vấn theo tenant đã xác thực.
    InventorySnapshot findBySkuAndTenant(String sku, String tenantId);
}
~~~

Implementation có thể dùng repository:

~~~java
import org.springframework.stereotype.Service;

@Service
public class DefaultInventoryQueryService implements InventoryQueryService {

    private final ProductRepository productRepository;

    public DefaultInventoryQueryService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Override
    public InventorySnapshot findBySku(String sku) {
        Product product = productRepository.findBySku(sku)
            .orElseThrow(() -> new ProductNotFoundException(sku));

        int quantity = product.getAvailableQuantity();
        return new InventorySnapshot(
            product.getSku(),
            quantity,
            quantity > 0
        );
    }

    @Override
    public InventorySnapshot findBySkuAndTenant(String sku, String tenantId) {
        Product product = productRepository.findBySkuAndTenant(sku, tenantId)
            .orElseThrow(() -> new ProductNotFoundException(sku));

        int quantity = product.getAvailableQuantity();
        return new InventorySnapshot(
            product.getSku(),
            quantity,
            quantity > 0
        );
    }
}
~~~

Trong ví dụ này, **@Service** đăng ký implementation thành Spring bean. Spring tiếp tục inject **ProductRepository** vào constructor của service. Khi ứng dụng chạy, chuỗi dependency được nối theo kiểu:

**InventoryTools → InventoryQueryService → ProductRepository**

Interface giúp lớp tool phụ thuộc vào năng lực nghiệp vụ, không phụ thuộc trực tiếp vào lớp lưu trữ. Nếu sau này nguồn dữ liệu chuyển từ database sang một API kho hàng, có thể cung cấp implementation khác của **InventoryQueryService** mà không cần thay đổi hợp đồng tool.

## 4. Đăng ký lớp chứa @Tool thành Spring bean

Lớp chứa công cụ cần được quản lý bởi Spring để dependency injection hoạt động. Với component scanning, cách đơn giản là đánh dấu lớp bằng **@Component**:

~~~java
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;

@Component
public class InventoryTools {

    private final InventoryQueryService inventoryQueryService;

    public InventoryTools(InventoryQueryService inventoryQueryService) {
        this.inventoryQueryService = inventoryQueryService;
    }

    @Tool(
        name = "lookup_inventory",
        description = """
            Tra cứu số lượng tồn kho có thể bán theo mã SKU.
            Dùng khi người dùng hỏi một sản phẩm còn hàng hay còn bao nhiêu.
            Công cụ chỉ đọc dữ liệu tồn kho.
            """
    )
    public String lookupInventory(
            @ToolParam(
                description = "Mã SKU của sản phẩm cần tra cứu, ví dụ SKU-100"
            ) String sku) {

        InventorySnapshot snapshot =
            inventoryQueryService.findBySku(sku);

        return "SKU: " + snapshot.sku()
            + "\nSố lượng có thể bán: " + snapshot.availableQuantity()
            + "\nCòn hàng: " + (snapshot.available() ? "Có" : "Không");
    }
}
~~~

Ở đây có hai loại annotation với hai mục đích khác nhau:

- **@Component** nói với Spring rằng đây là một bean cần được phát hiện và quản lý.
- **@Tool** nói với Spring AI rằng phương thức này có thể được công bố như một công cụ cho mô hình.

Chỉ có **@Tool** không tự động biến lớp thành Spring bean. Ngược lại, một lớp có **@Component** không tự động biến mọi phương thức của nó thành tool. Ta cần cả đăng ký bean và khai báo tool.

Constructor chỉ có một dependency nên không cần annotation **@Autowired** trên constructor. Spring tự sử dụng constructor duy nhất để inject bean phù hợp. Nếu lớp có nhiều constructor, cần thể hiện rõ constructor mà Spring nên dùng hoặc cung cấp cấu hình bean tường minh.

### Dùng @Bean thay cho @Component

Nếu không thể sửa lớp tool, hoặc muốn kiểm soát cách tạo bean trong một lớp cấu hình, có thể khai báo bằng **@Bean**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ToolConfiguration {

    @Bean
    InventoryTools inventoryTools(
            InventoryQueryService inventoryQueryService) {
        return new InventoryTools(inventoryQueryService);
    }
}
~~~

Tham số của phương thức **@Bean** cũng được Spring inject. Spring dùng kết quả trả về làm bean có tên **inventoryTools**. Chọn một cách đăng ký phù hợp cho cùng một lớp. Không vừa đánh dấu lớp bằng **@Component** vừa khai báo thêm một **@Bean** tạo cùng lớp, vì có thể tạo hai bean và gây mơ hồ khi inject.

## 5. Inject lớp tool vào thành phần dùng ChatClient

Lớp tool là một dependency của thành phần điều phối hội thoại. Thành phần này nhận **ChatClient.Builder** và **InventoryTools** qua constructor:

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryAssistant {

    private final ChatClient chatClient;
    private final InventoryTools inventoryTools;

    public InventoryAssistant(
            ChatClient.Builder chatClientBuilder,
            InventoryTools inventoryTools) {
        this.chatClient = chatClientBuilder.build();
        this.inventoryTools = inventoryTools;
    }

    public String answer(String question) {
        return chatClient.prompt()
            .user(question)
            .tools(inventoryTools)
            .call()
            .content();
    }
}
~~~

Trong Spring Boot với cấu hình Spring AI phù hợp, **ChatClient.Builder** được cung cấp qua auto-configuration. Ứng dụng inject builder để tạo **ChatClient** theo cấu hình chung. Nếu dự án tự cấu hình ChatClient, hãy cung cấp builder hoặc bean tương ứng trong lớp cấu hình.

Khi gọi **answer(...)**, đối tượng **inventoryTools** được đưa vào yêu cầu hiện tại thông qua **tools(...)**. Spring AI đọc các phương thức được đánh dấu **@Tool**, tạo definition và liên kết chúng với callback thực thi. Khi mô hình yêu cầu **lookup_inventory**, callback gọi phương thức trên đúng đối tượng đã được cung cấp.

Sơ đồ dependency injection và đăng ký tool có thể tóm tắt:

~~~mermaid
flowchart LR
    B[Spring Container] -->|inject| A[InventoryAssistant]
    B -->|inject| T[InventoryTools]
    B -->|inject| S[InventoryQueryService]
    B -->|inject| R[ProductRepository]
    A -->|tools| T
    T --> S
    S --> R
~~~

Việc inject **InventoryTools** vào **InventoryAssistant** không có nghĩa mô hình được cấp quyền truy cập trực tiếp đến bean. Ứng dụng chủ động chọn tool nào sẽ xuất hiện trong yêu cầu chat và callback thực thi trong tiến trình của ứng dụng.

## 6. Constructor injection, setter injection và field injection

Spring hỗ trợ nhiều cách inject dependency, nhưng constructor injection thường phù hợp nhất với service và lớp tool.

| Cách inject | Đặc điểm | Khuyến nghị |
| --- | --- | --- |
| Constructor injection | Dependency được khai báo rõ; có thể dùng field final; dễ tạo đối tượng trong unit test | Ưu tiên |
| Setter injection | Dependency được gán sau khi tạo đối tượng; hữu ích với dependency thực sự tùy chọn hoặc cần cấu hình lại | Chỉ dùng khi có lý do cụ thể |
| Field injection | Spring gán trực tiếp vào field; dependency khó nhìn thấy từ constructor và khó khởi tạo độc lập | Tránh trong lớp nghiệp vụ |

Ví dụ setter injection:

~~~java
import org.springframework.beans.factory.annotation.Autowired;

@Component
public class InventoryTools {

    private InventoryQueryService inventoryQueryService;

    @Autowired
    public void setInventoryQueryService(
            InventoryQueryService inventoryQueryService) {
        this.inventoryQueryService = inventoryQueryService;
    }
}
~~~

Đoạn mã trên hợp lệ trong một số trường hợp, nhưng dependency không còn bất biến sau khi tạo đối tượng. Với một tool luôn cần service để hoạt động, constructor injection thể hiện ràng buộc này tốt hơn.

Field injection có thể làm lớp trông ngắn hơn, nhưng khi đọc constructor ta không biết lớp cần những dependency nào. Nó cũng khiến việc tạo instance trong unit test phụ thuộc vào reflection hoặc Spring test context. Vì vậy, hãy dùng constructor injection làm lựa chọn mặc định.

## 7. Bean scope và tính an toàn khi chạy đồng thời

Bean Spring mặc định có scope **singleton** trong mỗi application context. Điều này có nghĩa một instance của lớp tool thường được nhiều yêu cầu chat dùng chung. Đây là thiết kế phù hợp nếu lớp tool chỉ giữ các dependency bất biến và không lưu trạng thái của một cuộc hội thoại.

Một lớp tool nên:

- Dùng field **final** cho các dependency được inject.
- Giữ phương thức tool stateless: mỗi lần gọi xử lý dữ liệu đầu vào và trả kết quả.
- Không lưu prompt, lịch sử hội thoại, user ID hay kết quả của request trước vào field có thể thay đổi.
- Không thay đổi một biến dùng chung khi xử lý một tool call.
- Để transaction, cache và đồng bộ dữ liệu do service nghiệp vụ quản lý.

Ví dụ không an toàn:

~~~java
@Component
public class UnsafeInventoryTools {

    private String currentUserId;

    @Tool(description = "Tra cứu tồn kho.")
    public String lookup(String sku) {
        // Gán currentUserId theo request hiện tại rồi truy vấn.
        // Một request đồng thời có thể ghi đè giá trị này.
        return "Kết quả tồn kho";
    }
}
~~~

Vì bean singleton được dùng chung, hai yêu cầu đồng thời có thể ghi đè **currentUserId** của nhau. Điều này có thể dẫn đến truy vấn nhầm phạm vi dữ liệu. Hãy lấy danh tính và quyền từ security context hoặc context của lần thực thi, rồi truyền chúng một cách rõ ràng đến service nghiệp vụ.

Không nên đổi scope sang prototype chỉ để che giấu việc lớp tool đang giữ state theo request. Trước hết hãy thiết kế lớp tool stateless. Chỉ chọn scope khác khi lifecycle thực sự yêu cầu điều đó và đã hiểu cách Spring AI giữ tham chiếu đến callback.

## 8. Phân biệt dependency injection với ToolContext

DI và **ToolContext** giải quyết hai nhu cầu khác nhau:

- **Dependency injection** cung cấp các thành phần mà lớp tool cần để hoạt động, ví dụ **InventoryQueryService**, repository, client nội bộ hoặc bộ kiểm tra nghiệp vụ.
- **ToolContext** mang dữ liệu ngữ cảnh của một lần gọi, ví dụ tenant ID hoặc user ID đã được ứng dụng xác thực.

Không inject một giá trị theo request vào field của singleton tool. Thay vào đó, ứng dụng truyền dữ liệu ngữ cảnh cho lần gọi và phương thức nhận **ToolContext**:

~~~java
import org.springframework.ai.chat.model.ToolContext;

@Tool(description = "Tra cứu tồn kho của sản phẩm trong phạm vi tenant hiện tại.")
public String lookupInventory(
        @ToolParam(description = "Mã SKU cần tra cứu") String sku,
        ToolContext toolContext) {

    String tenantId =
        (String) toolContext.getContext().get("tenantId");

    InventorySnapshot snapshot =
        inventoryQueryService.findBySkuAndTenant(sku, tenantId);

    return "SKU: " + snapshot.sku()
        + "\nSố lượng có thể bán: " + snapshot.availableQuantity();
}
~~~

Ứng dụng có thể cung cấp context cho yêu cầu chat:

~~~java
import java.util.Map;

return chatClient.prompt()
    .user(question)
    .tools(inventoryTools)
    .toolContext(Map.of("tenantId", authenticatedTenantId))
    .call()
    .content();
~~~

**authenticatedTenantId** trong ví dụ phải đến từ phiên đăng nhập hoặc cơ chế xác thực do server kiểm soát. Không lấy tenant ID từ nội dung người dùng rồi xem đó là danh tính đã xác thực. Tham số **sku** là dữ liệu nghiệp vụ mô hình có thể cung cấp; tenant ID là ngữ cảnh đáng tin cậy mà ứng dụng truyền vào. Service vẫn cần kiểm tra người dùng có quyền xem SKU trong tenant đó.

Tham số **ToolContext** là ngữ cảnh thực thi do Spring AI cung cấp; nó không phải một tham số nghiệp vụ mà mô hình phải tạo trong JSON input. Nhờ vậy, schema công cụ vẫn chỉ yêu cầu SKU.

## 9. Kiểm thử lớp tool và cấu hình DI

Constructor injection giúp unit test lớp tool không cần khởi tạo toàn bộ Spring context. Có thể tạo mock cho service, truyền vào constructor rồi gọi phương thức trực tiếp:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

class InventoryToolsTest {

    private final InventoryQueryService inventoryQueryService =
        Mockito.mock(InventoryQueryService.class);

    private final InventoryTools inventoryTools =
        new InventoryTools(inventoryQueryService);

    @Test
    void returnsInventoryForSku() {
        when(inventoryQueryService.findBySku("SKU-100"))
            .thenReturn(new InventorySnapshot("SKU-100", 5, true));

        String result = inventoryTools.lookupInventory("SKU-100");

        assertTrue(result.contains("SKU-100"));
        assertTrue(result.contains("5"));
        verify(inventoryQueryService).findBySku("SKU-100");
    }
}
~~~

Unit test này kiểm tra lớp tool chuyển đầu vào và kết quả từ service như mong đợi. Nó không kiểm tra component scanning hoặc việc Spring tạo bean. Với phần DI, có thể viết một Spring context test nhỏ để xác nhận:

- **InventoryTools** được đăng ký thành bean.
- **InventoryQueryService** có đúng một implementation có thể inject.
- **ProductRepository** được nối vào implementation service.
- **InventoryAssistant** nhận được **ChatClient.Builder** và **InventoryTools**.

Khi có nhiều implementation của cùng interface, Spring có thể không biết bean nào cần inject. Có thể chọn rõ bằng **@Primary**, **@Qualifier** hoặc cấu hình bean phù hợp. Không nên giải quyết sự mơ hồ bằng cách inject một implementation cụ thể vào lớp tool nếu mục tiêu kiến trúc là phụ thuộc vào interface.

## 10. Lỗi thường gặp khi cấu hình dependency injection

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không tìm thấy bean cho constructor | Implementation chưa được đăng ký hoặc nằm ngoài component scan | Kiểm tra **@Service**, **@Repository**, **@Component** và package scan |
| Có nhiều bean cùng kiểu | Nhiều implementation cùng implement interface | Chọn bằng **@Primary** hoặc **@Qualifier** |
| Lớp tool không được tìm thấy | Chưa đăng ký thành Spring bean | Thêm **@Component** hoặc khai báo **@Bean** |
| Phương thức không xuất hiện trong danh sách tool | Thiếu **@Tool** hoặc đối tượng không được truyền vào yêu cầu | Kiểm tra annotation và **ChatClient.tools(...)** |
| Dependency bị null | Tạo đối tượng bằng **new** bên ngoài Spring hoặc dùng field injection sai cách | Để Spring tạo bean và dùng constructor injection |
| Dữ liệu người dùng bị lẫn giữa các request | Bean singleton lưu state có thể thay đổi | Bỏ state theo request khỏi field; dùng context của lần gọi |
| Inject nhầm implementation | Có nhiều bean cùng kiểu và không có quy tắc chọn | Kiểm tra qualifier hoặc cấu hình primary |

Khi ứng dụng khởi động thất bại vì không tìm được dependency, hãy đọc phần đầu của lỗi tạo bean để xác định constructor và kiểu bean đang thiếu. Đừng thêm annotation một cách ngẫu nhiên; kiểm tra chuỗi dependency từ lớp tool xuống service và repository.

## 11. Nguyên tắc thiết kế

1. **Một lớp tool nên phụ thuộc vào service nghiệp vụ.** Hạn chế gọi repository trực tiếp từ lớp tool nếu truy vấn cần quy tắc nghiệp vụ hoặc được dùng ở nhiều nơi.
2. **Ưu tiên interface ở ranh giới nghiệp vụ.** Điều này giúp thay implementation và kiểm thử dễ hơn.
3. **Dùng constructor injection.** Khai báo dependency bằng field final và không tự tạo service bằng new.
4. **Đăng ký bean một lần.** Chọn component scanning hoặc cấu hình @Bean cho một instance có vai trò đó.
5. **Giữ tool bean stateless.** Không lưu dữ liệu theo người dùng hoặc hội thoại trong field của singleton.
6. **Tách dependency khỏi ngữ cảnh request.** Service là dependency dài hạn; tenant và user ID là dữ liệu của lần gọi, phải lấy từ nguồn đáng tin cậy.
7. **Giữ quyền thực thi trong ứng dụng.** Tool definition giúp mô hình biết cách yêu cầu gọi; service và lớp bảo mật mới xác minh quyền và thực hiện nghiệp vụ.

## Bài thực hành

Tạo lớp **CustomerTools** có phương thức chỉ đọc để tra cứu tên và trạng thái tài khoản khách hàng theo mã khách hàng.

Yêu cầu:

- Định nghĩa interface **CustomerQueryService** với phương thức tra cứu.
- Tạo implementation service và đăng ký bằng **@Service**.
- Đăng ký **CustomerTools** bằng **@Component** và inject service qua constructor.
- Đánh dấu phương thức tra cứu bằng **@Tool** và mô tả mã khách hàng bằng **@ToolParam**.
- Inject **CustomerTools** vào một assistant service và truyền qua **ChatClient.tools(...)**.
- Viết unit test dùng mock service để kiểm tra kết quả và Spring context test để xác nhận wiring.
- Nếu dữ liệu khách hàng phân vùng theo tenant, lấy tenant từ ngữ cảnh đã xác thực và kiểm tra quyền ở service.

Khi hoàn thành, hãy kiểm tra xem có lớp nào tự tạo dependency bằng **new**, tool bean có giữ state theo request hay không và mọi đường truy cập dữ liệu có đi qua kiểm tra quyền hay không.

## Ghi nhớ

Lớp chứa **@Tool** vẫn là một thành phần của ứng dụng Spring. Hãy đăng ký nó thành bean bằng **@Component** hoặc **@Bean**, inject service qua constructor và cung cấp bean cho **ChatClient.tools(...)**. Spring quản lý dependency và lifecycle; Spring AI công bố công cụ và điều phối callback; service nghiệp vụ thực hiện truy vấn và xác minh quyền. Giữ tool bean stateless để các request đồng thời không chia sẻ nhầm dữ liệu ngữ cảnh.

## Tài liệu tham khảo

- [Spring AI Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring Framework Reference — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework Reference — Component Scanning](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)
