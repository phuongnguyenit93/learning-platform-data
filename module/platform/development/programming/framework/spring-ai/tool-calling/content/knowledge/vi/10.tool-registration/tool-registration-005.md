# Tạo callback từ đối tượng và gom nhóm công cụ

Khi một ứng dụng có nhiều lớp chứa phương thức **@Tool**, có thể chuyển các đối tượng đó thành **ToolCallback** rồi gom chúng thành một nhóm để cung cấp cho mô hình. Spring AI hỗ trợ từng bước: **ToolCallbacks.from(...)** tạo mảng callback từ đối tượng có phương thức tool; **ToolCallbackProvider.from(...)** đóng gói những callback đã có thành một provider; **MethodToolCallbackProvider** tạo provider trực tiếp từ nhiều đối tượng tool.

Việc gom nhóm giúp ứng dụng tổ chức công cụ theo miền nghiệp vụ, chẳng hạn nhóm tồn kho, nhóm đơn hàng hoặc nhóm khách hàng. Khi gửi yêu cầu chat, ứng dụng chọn nhóm phù hợp với tác vụ và quyền của người dùng. Mô hình chỉ nhìn thấy các tool definition trong nhóm được cung cấp cho yêu cầu đó.

## 1. Từ đối tượng chứa @Tool đến ToolCallback

Một lớp Java có thể chứa nhiều phương thức được đánh dấu **@Tool**. Mỗi phương thức cung cấp một khả năng nghiệp vụ và được mô tả bằng tên, mô tả cùng schema đầu vào.

Ví dụ, nhóm tồn kho có hai thao tác chỉ đọc:

~~~java
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;

@Component
public class InventoryTools {

    private final InventoryService inventoryService;

    public InventoryTools(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @Tool(
        name = "lookup_inventory",
        description = "Tra cứu số lượng tồn kho có thể bán theo mã SKU."
    )
    public InventoryResult lookupInventory(
            @ToolParam(description = "Mã SKU, ví dụ SKU-100") String sku) {
        return inventoryService.lookup(sku);
    }

    @Tool(
        name = "lookup_warehouse",
        description = "Tra cứu thông tin kho theo mã kho."
    )
    public WarehouseResult lookupWarehouse(
            @ToolParam(description = "Mã kho cần tra cứu") String warehouseCode) {
        return inventoryService.lookupWarehouse(warehouseCode);
    }
}
~~~

**InventoryTools** là đối tượng chứa các phương thức tool. **@Component** đăng ký đối tượng thành Spring bean, còn **@Tool** đánh dấu phương thức mà Spring AI có thể công bố cho mô hình. Spring inject **InventoryService** qua constructor để phương thức gọi nghiệp vụ hiện có.

Ví dụ giả định ứng dụng đã có **InventoryService**, **InventoryResult** và **WarehouseResult**. Đây là các kiểu nghiệp vụ mà phương thức tool sử dụng làm đầu vào hoặc kết quả; chúng không phải thành phần do ToolCallbacks tạo ra.

Một đối tượng có thể chứa một hoặc nhiều phương thức **@Tool**. Mỗi phương thức được chuyển thành một callback riêng. Vì vậy, lớp có hai phương thức tool ở trên sẽ tạo ra hai **ToolCallback**.

## 2. Tạo callback bằng ToolCallbacks.from(...)

Khi đã có đối tượng tool, dùng **ToolCallbacks.from(...)** để tạo mảng callback:

~~~java
import org.springframework.ai.support.ToolCallbacks;
import org.springframework.ai.tool.ToolCallback;

ToolCallback[] inventoryCallbacks =
    ToolCallbacks.from(inventoryTools);
~~~

Phương thức **from(...)** nhận một hoặc nhiều đối tượng nguồn. Với các đối tượng có phương thức **@Tool**, Spring AI tạo callback tương ứng và trả về mảng **ToolCallback[]**.

Có thể truyền nhiều đối tượng trong cùng một lần:

~~~java
ToolCallback[] backOfficeCallbacks =
    ToolCallbacks.from(
        inventoryTools,
        orderTools,
        customerTools
    );
~~~

Trong ví dụ này, callback được tạo từ các phương thức tool có trong ba đối tượng. Mảng kết quả có thể chứa nhiều callback thuộc nhiều miền nghiệp vụ khác nhau. Ứng dụng có thể đưa cả mảng vào một yêu cầu chat hoặc tiếp tục đóng gói chúng thành provider.

**ToolCallbacks.from(...)** là cách thuận tiện khi muốn lấy ngay các callback để kiểm tra, lọc hoặc truyền vào **ChatClient**. Nó không tạo ra một bean Spring mới; nó trả về các callback đã được xây dựng từ các đối tượng được truyền vào.

## 3. Dùng MethodToolCallbackProvider để gom đối tượng

Nếu muốn biểu diễn một nhóm tool như một provider, có thể dùng **MethodToolCallbackProvider**:

~~~java
import org.springframework.ai.tool.ToolCallbackProvider;
import org.springframework.ai.tool.method.MethodToolCallbackProvider;

ToolCallbackProvider inventoryProvider =
    MethodToolCallbackProvider.builder()
        .toolObjects(inventoryTools, warehouseTools)
        .build();
~~~

Phương thức **toolObjects(...)** nhận nhiều đối tượng chứa phương thức **@Tool**. Khi gọi **build()**, provider tạo và cung cấp tập callback tương ứng. Có thể lấy mảng callback từ provider bằng **getToolCallbacks()** nếu cần xử lý từng callback:

~~~java
ToolCallback[] callbacks = inventoryProvider.getToolCallbacks();
~~~

**MethodToolCallbackProvider** phù hợp khi ứng dụng muốn đăng ký một nhóm đối tượng tool theo cách khai báo rõ ràng. Nó thực hiện vai trò tạo callback từ các phương thức được đánh dấu **@Tool** và cung cấp chúng qua giao diện **ToolCallbackProvider**.

## 4. Phân biệt ba API tạo và gom nhóm

Ba API có liên quan nhưng đảm nhiệm các bước khác nhau:

| API | Đầu vào | Kết quả | Khi nên dùng |
| --- | --- | --- | --- |
| **ToolCallbacks.from(...)** | Một hoặc nhiều đối tượng có phương thức **@Tool** | Mảng **ToolCallback[]** | Cần tạo callback trực tiếp để lọc, kiểm tra hoặc truyền cho ChatClient |
| **MethodToolCallbackProvider.builder().toolObjects(...).build()** | Một hoặc nhiều đối tượng có phương thức **@Tool** | **ToolCallbackProvider** | Muốn gom đối tượng tool thành một provider |
| **ToolCallbackProvider.from(...)** | Một mảng hoặc danh sách callback đã tạo | **ToolCallbackProvider** | Muốn gom các callback có sẵn thành một nhóm |

Ví dụ, nếu đã có các callback từ nhiều nguồn, có thể đóng gói chúng bằng factory của interface **ToolCallbackProvider**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.ToolCallbackProvider;

List<ToolCallback> operationsCallbacks =
    new ArrayList<>(Arrays.asList(inventoryCallbacks));
operationsCallbacks.add(orderCallback);
operationsCallbacks.add(customerCallback);

ToolCallbackProvider operationsProvider =
    ToolCallbackProvider.from(operationsCallbacks);
~~~

Factory này nhận các callback đã tồn tại. Nó không quét đối tượng và không tự tìm phương thức **@Tool**. Nếu đầu vào của bạn là các đối tượng chứa phương thức **@Tool**, hãy dùng **ToolCallbacks.from(...)** hoặc **MethodToolCallbackProvider.builder().toolObjects(...)** trước.

## 5. Tạo provider thành Spring bean

Trong ứng dụng Spring, có thể đăng ký từng nhóm tool thành một bean **ToolCallbackProvider**. Spring inject các đối tượng tool đã được quản lý vào phương thức cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ai.tool.ToolCallbackProvider;
import org.springframework.ai.tool.method.MethodToolCallbackProvider;

@Configuration(proxyBeanMethods = false)
public class ToolRegistrationConfiguration {

    @Bean
    ToolCallbackProvider inventoryToolProvider(
            InventoryTools inventoryTools,
            WarehouseTools warehouseTools) {
        return MethodToolCallbackProvider.builder()
            .toolObjects(inventoryTools, warehouseTools)
            .build();
    }

    @Bean
    ToolCallbackProvider orderToolProvider(
            OrderTools orderTools,
            PaymentQueryTools paymentQueryTools) {
        return MethodToolCallbackProvider.builder()
            .toolObjects(orderTools, paymentQueryTools)
            .build();
    }
}
~~~

Sau cấu hình này, ứng dụng có hai nhóm provider: **inventoryToolProvider** và **orderToolProvider**. Mỗi provider gom các callback thuộc cùng một miền chức năng. Các đối tượng tool được Spring tạo và inject dependency theo cấu hình của ứng dụng.

Nếu cần tạo provider từ callback đã được dựng riêng, có thể dùng **ToolCallbackProvider.from(...)** trong phương thức **@Bean**:

~~~java
import org.springframework.ai.tool.ToolCallback;

@Bean
ToolCallbackProvider reportingTools(
        ToolCallback salesReportCallback,
        ToolCallback stockReportCallback) {
    return ToolCallbackProvider.from(
        salesReportCallback,
        stockReportCallback
    );
}
~~~

Chọn cách phù hợp với nguồn callback. Không cần chuyển một provider đã có thành một provider khác nếu mục tiêu chỉ là truyền nó cho **ChatClient**.

## 6. Cung cấp nhóm tool cho ChatClient

**ChatClient** chấp nhận đối tượng chứa phương thức **@Tool**, **ToolCallback**, **ToolCallbackProvider**, mảng hoặc collection của các thành phần này. Có thể truyền provider trực tiếp vào yêu cầu:

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.stereotype.Service;

@Service
public class OperationsAssistant {

    private final ChatClient chatClient;
    private final ToolCallbackProvider inventoryToolProvider;
    private final ToolCallbackProvider orderToolProvider;

    public OperationsAssistant(
            ChatClient.Builder chatClientBuilder,
            ToolCallbackProvider inventoryToolProvider,
            ToolCallbackProvider orderToolProvider) {
        this.chatClient = chatClientBuilder.build();
        this.inventoryToolProvider = inventoryToolProvider;
        this.orderToolProvider = orderToolProvider;
    }

    public String answerInventoryQuestion(String question) {
        return chatClient.prompt()
            .user(question)
            .tools(inventoryToolProvider)
            .call()
            .content();
    }

    public String answerOrderQuestion(String question) {
        return chatClient.prompt()
            .user(question)
            .tools(orderToolProvider)
            .call()
            .content();
    }
}
~~~

Trong mỗi phương thức, ứng dụng chọn provider phù hợp với câu hỏi. Yêu cầu tra cứu tồn kho nhận nhóm tồn kho; yêu cầu về đơn hàng nhận nhóm đơn hàng. Mô hình chỉ có thể yêu cầu gọi các công cụ được cung cấp trong yêu cầu tương ứng.

Cũng có thể truyền nhiều nhóm vào cùng một yêu cầu khi tác vụ cần phối hợp nhiều miền:

~~~java
return chatClient.prompt()
    .user("Kiểm tra tồn kho SKU-100 và trạng thái đơn hàng ORD-200.")
    .tools(inventoryToolProvider, orderToolProvider)
    .call()
    .content();
~~~

Khi cần nhiều nhóm cùng lúc, hãy kiểm tra toàn bộ tập callback cuối cùng để bảo đảm tên tool không trùng nhau và các thao tác đều phù hợp với quyền hiện tại.

## 7. Nhóm mặc định và nhóm theo từng yêu cầu

Có hai phạm vi phổ biến để cung cấp công cụ cho **ChatClient**:

| Phạm vi | API | Đặc điểm |
| --- | --- | --- |
| Theo từng yêu cầu | **ChatClient.prompt().tools(...)** | Công cụ được thêm cho lần gọi hiện tại |
| Mặc định của client | **ChatClient.builder(...).defaultTools(...)** | Công cụ có sẵn cho các yêu cầu được tạo từ client đó |

Ví dụ đăng ký nhóm công cụ mặc định:

~~~java
ChatClient inventoryClient = ChatClient.builder(chatModel)
    .defaultTools(inventoryToolProvider)
    .build();
~~~

Với Spring AI 2.1, các tool được thêm bằng **tools(...)** ở cấp request được nối với các tool mặc định của client. Tập công cụ cuối cùng là hợp của hai nguồn này. Do đó, không nên giả định rằng gọi **tools(...)** sẽ loại bỏ mọi tool đã được khai báo trong **defaultTools(...)**.

Tool mặc định được chia sẻ cho các request của client được tạo từ builder đó. Chỉ đưa vào đây những công cụ phù hợp với mọi request trong phạm vi client. Các công cụ có quyền cao, thao tác ghi hoặc chỉ phù hợp với một nhóm người dùng nên được chọn theo từng request sau khi ứng dụng kiểm tra quyền.

## 8. Tổ chức nhóm theo miền nghiệp vụ

Gom nhóm nên phản ánh cách ứng dụng phân chia nghiệp vụ và quyền truy cập. Một cấu trúc có thể là:

~~~mermaid
flowchart TD
    A[ToolCallbackProvider] --> B[Nhóm tồn kho]
    A --> C[Nhóm đơn hàng]
    A --> D[Nhóm khách hàng]
    B --> E[InventoryTools]
    B --> F[WarehouseTools]
    C --> G[OrderTools]
    C --> H[PaymentQueryTools]
    D --> I[CustomerProfileTools]
    D --> J[CustomerSupportTools]
~~~

Một số nguyên tắc hữu ích:

- Nhóm những tool có cùng miền dữ liệu hoặc mục đích nghiệp vụ.
- Giữ tên tool duy nhất trong tập được gửi đến mô hình.
- Không đưa quá nhiều công cụ không liên quan vào một request.
- Tách nhóm đọc dữ liệu khỏi nhóm có thể thay đổi trạng thái nếu quyền khác nhau.
- Chọn nhóm dựa trên tác vụ và quyền đã xác thực ở phía server.
- Tránh tạo provider toàn cục chứa mọi công cụ nếu nhiều request không cần cùng một tập quyền.

Nhóm tool là cách tổ chức và cung cấp callback. Bản thân provider không thay thế authorization. Nếu **OrderTools** chứa phương thức xem đơn hàng, service vẫn cần xác minh người dùng có quyền xem đơn hàng cụ thể đó.

## 9. Kiểm tra tên trùng và tập callback

Tên tool là định danh mô hình dùng khi gửi yêu cầu gọi. Trong một tập tool được cung cấp cho mô hình, mỗi tên phải duy nhất. Nếu hai đối tượng có phương thức cùng công bố tên **lookup_status**, mô hình không có cách phân biệt chính xác callback mà ứng dụng dự định chọn.

Có thể kiểm tra tên sau khi tạo callback:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.ai.support.ToolCallbacks;
import org.springframework.ai.tool.ToolCallback;

List<ToolCallback> callbacks =
    Arrays.asList(ToolCallbacks.from(inventoryTools, orderTools));

Map<String, Long> nameCounts = callbacks.stream()
    .map(callback -> callback.getToolDefinition().name())
    .collect(Collectors.groupingBy(Function.identity(), Collectors.counting()));

List<String> duplicateNames = nameCounts.entrySet().stream()
    .filter(entry -> entry.getValue() > 1)
    .map(Map.Entry::getKey)
    .toList();

if (!duplicateNames.isEmpty()) {
    throw new IllegalStateException(
        "Tên tool bị trùng: " + duplicateNames
    );
}
~~~

Việc kiểm tra nên thực hiện trên tập cuối cùng sau khi đã hợp nhất các nhóm. Hai provider riêng có thể không trùng tên khi xét độc lập nhưng lại trùng khi được đưa vào cùng một request.

Ngoài tên, nên kiểm tra mô tả và schema:

- Mô tả có nói đúng hành vi mà callback thực thi không?
- Trường bắt buộc và tùy chọn có phù hợp với khả năng xác định dữ liệu không?
- Schema có tương thích với DTO hoặc tham số của phương thức không?
- Callback có gọi đúng service và trả kết quả đã được giới hạn không?

## 10. Phân quyền trước khi chọn nhóm

Việc đưa provider vào request quyết định những công cụ nào được công bố cho mô hình trong lượt đó. Vì vậy, ứng dụng nên chọn nhóm sau khi đã xác định người dùng và mục đích nghiệp vụ.

Ví dụ, nhân viên hỗ trợ có thể được phép tra cứu hồ sơ và trạng thái đơn hàng, trong khi thao tác hoàn tiền chỉ dành cho vai trò được cấp quyền. Ứng dụng có thể chọn nhóm công cụ đọc cho yêu cầu thông thường:

~~~java
public String answer(
        String question,
        AuthenticatedUser user) {

    if (user.hasAuthority("ORDER_READ")) {
        return chatClient.prompt()
            .user(question)
            .tools(orderReadToolProvider)
            .call()
            .content();
    }

    return "Bạn không có quyền tra cứu đơn hàng.";
}
~~~

Đây chỉ là lớp chọn tập công cụ. Trong **OrderService**, vẫn cần kiểm tra quyền trên từng đơn hàng để tránh truy cập chéo dữ liệu. Không lấy vai trò hoặc tenant ID từ nội dung do mô hình tạo. Ngữ cảnh bảo mật cần đến từ phiên xác thực của ứng dụng và có thể được truyền vào tool qua **ToolContext**.

Với công cụ có tác động phụ, hãy cân nhắc xác nhận của người dùng, phê duyệt hoặc chính sách riêng trước khi callback thực thi. Việc không công bố một callback trong request là một lớp giới hạn khả năng lựa chọn của mô hình; kiểm tra quyền tại service vẫn là ranh giới thực thi.

## 11. Phân biệt ToolCallbackProvider và ToolCallbackResolver

Hai thành phần này thường xuất hiện cùng nhau nhưng có trách nhiệm khác:

| Thành phần | Trách nhiệm |
| --- | --- |
| **ToolCallbackProvider** | Cung cấp một tập callback thông qua **getToolCallbacks()** |
| **ToolCallbackResolver** | Tìm callback theo tên tool tại thời điểm cần phân giải |

Thông thường, ứng dụng truyền trực tiếp callback hoặc provider qua **ChatClient.tools(...)** hoặc **defaultTools(...)**. Khi cần phân giải tên động từ nguồn khác, Spring AI sử dụng **ToolCallbackResolver**. Resolver mặc định có thể sử dụng các bean **ToolCallback** và provider được đăng ký trong application context.

Không cần tự triển khai resolver chỉ để gom vài đối tượng tool tĩnh. Dùng **MethodToolCallbackProvider** hoặc **ToolCallbackProvider.from(...)** là đủ cho nhóm callback đã biết trước. Chỉ tạo resolver riêng khi có nhu cầu thực sự như tra cứu công cụ từ registry, nguồn dữ liệu động hoặc dịch vụ từ xa.

Từ Spring AI 2.0, cách khai báo bean **Function** trần rồi phân giải bằng tên qua **toolNames(...)** đã bị loại bỏ. Với function hoặc method reference, hãy tạo **FunctionToolCallback** tường minh và đăng ký callback/provider tương ứng.

## 12. Kiểm thử việc tạo và gom nhóm callback

Nên kiểm thử cả bước tạo callback lẫn việc cung cấp nhóm cho ChatClient:

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Một đối tượng có một phương thức @Tool | Tạo đúng một callback với tên mong đợi |
| Một đối tượng có nhiều phương thức @Tool | Tất cả phương thức hợp lệ được chuyển thành callback |
| Nhiều đối tượng được truyền vào from(...) | Callback từ các đối tượng đều xuất hiện |
| Provider được tạo từ toolObjects(...) | Provider trả về tập callback dự kiến |
| Provider được tạo từ callback có sẵn | Không mất callback khi đóng gói |
| Hai nhóm được hợp nhất | Không có tên tool trùng nhau |
| Request không có quyền | Nhóm công cụ nhạy cảm không được cung cấp |
| Request có quyền | Chỉ nhóm được phép xuất hiện trong tool set |

Ví dụ unit test kiểm tra callback:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.ai.support.ToolCallbacks;
import org.springframework.ai.tool.ToolCallback;

class InventoryToolRegistrationTest {

    @Test
    void createsCallbacksFromToolObject() {
        InventoryService inventoryService = Mockito.mock(InventoryService.class);
        InventoryTools inventoryTools = new InventoryTools(inventoryService);

        ToolCallback[] callbacks = ToolCallbacks.from(inventoryTools);

        Set<String> names = Arrays.stream(callbacks)
            .map(callback -> callback.getToolDefinition().name())
            .collect(Collectors.toSet());

        assertEquals(2, callbacks.length);
        assertTrue(names.contains("lookup_inventory"));
        assertTrue(names.contains("lookup_warehouse"));
    }
}
~~~

Trong Spring context test, có thể xác minh provider được đăng ký và chứa đúng callback. Với kiểm thử tích hợp ChatClient, hãy quan sát tool definition được gửi trong request và xác nhận callback tương ứng thực sự được gọi khi mô hình yêu cầu. Không chỉ kiểm tra câu trả lời cuối vì mô hình có thể diễn đạt cùng một dữ kiện theo nhiều cách.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Mảng callback rỗng | Đối tượng không có phương thức **@Tool** hợp lệ | Kiểm tra annotation và đối tượng được truyền vào |
| Không inject được đối tượng tool | Lớp chưa được Spring quản lý hoặc thiếu bean dependency | Đăng ký **@Component** hoặc **@Bean** |
| Provider không chứa đủ callback | Chỉ truyền một số đối tượng vào **toolObjects(...)** | Kiểm tra danh sách đối tượng đầu vào |
| Mô hình gọi nhầm công cụ | Tên hoặc mô tả trùng lặp, quá chung | Đặt tên duy nhất và mô tả rõ mục đích |
| Lỗi tên trùng khi gộp nhóm | Hai nhóm riêng có cùng tool name | Kiểm tra tên trên tập callback cuối cùng |
| Tool không có trong request | Chưa truyền provider vào **tools(...)** hoặc **defaultTools(...)** | Kiểm tra đường đi từ provider đến ChatClient |
| Công cụ nhạy cảm xuất hiện ngoài dự kiến | Đăng ký quá nhiều tool mặc định | Chọn provider theo từng request và quyền người dùng |

## Bài thực hành

Tạo hai nhóm callback cho một ứng dụng bán hàng:

**Nhóm khách hàng**

- **CustomerProfileTools**: tra cứu hồ sơ khách hàng.
- **CustomerSupportTools**: tra cứu yêu cầu hỗ trợ.

**Nhóm đơn hàng**

- **OrderQueryTools**: tra cứu trạng thái đơn hàng.
- **DeliveryQueryTools**: tra cứu tình trạng giao hàng.

Yêu cầu:

1. Đăng ký từng đối tượng tool thành Spring bean và inject service qua constructor.
2. Dùng **MethodToolCallbackProvider.builder().toolObjects(...)** để tạo hai provider.
3. Inject provider vào assistant service.
4. Chọn nhóm khách hàng hoặc đơn hàng theo nội dung và quyền của request.
5. Kiểm tra tên tool không trùng khi hai nhóm được cung cấp đồng thời.
6. Viết test xác nhận mỗi provider trả về đúng các callback.
7. Đảm bảo service vẫn kiểm tra quyền trên từng khách hàng và đơn hàng.

Sau khi hoàn thành, hãy tự trả lời: **ToolCallbacks.from(...)** khác **ToolCallbackProvider.from(...)** ở đâu? Khi nào nên dùng **MethodToolCallbackProvider**? Vì sao không nên cung cấp toàn bộ công cụ cho mọi yêu cầu chat?

## Ghi nhớ

**ToolCallbacks.from(...)** chuyển một hoặc nhiều đối tượng có phương thức **@Tool** thành mảng callback. **MethodToolCallbackProvider.builder().toolObjects(...)** gom các đối tượng tool thành một provider. **ToolCallbackProvider.from(...)** đóng gói các callback đã tạo thành một provider. Sau đó, ứng dụng truyền provider vào **ChatClient.tools(...)** hoặc **defaultTools(...)** theo phạm vi phù hợp. Hãy tổ chức nhóm theo miền nghiệp vụ, giữ tên duy nhất và chọn nhóm dựa trên quyền đã xác thực; service vẫn chịu trách nhiệm kiểm tra quyền khi thực thi.

## Tài liệu tham khảo

- [Spring AI Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [ToolCallbacks API](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/support/ToolCallbacks.html)
- [MethodToolCallbackProvider.Builder API](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/method/MethodToolCallbackProvider.Builder.html)
- [ToolCallbackProvider API](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/tool/ToolCallbackProvider.html)
