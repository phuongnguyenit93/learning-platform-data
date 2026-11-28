# Phương thức instance, static và phạm vi truy cập được hỗ trợ

Trong Spring AI, một phương thức Java có thể trở thành tool bằng cách gắn annotation `@Tool`. Phương thức đó không bắt buộc phải là `public`, cũng không bắt buộc phải là phương thức instance. Spring AI hỗ trợ phương thức `public`, `protected`, package-private và `private`; phương thức có thể là instance hoặc `static`.

Điều cần quyết định khi thiết kế tool là phương thức có cần trạng thái và dependency của một object hay không, cách ứng dụng tạo hoặc lấy object đó, và nơi đặt lớp chứa phương thức. Phạm vi truy cập được Spring AI hỗ trợ không xóa bỏ các quy tắc truy cập của Java khi ứng dụng khởi tạo lớp, cũng không tự động giải quyết giới hạn reflection của môi trường native image.

Bài học này tập trung vào cách Spring AI xử lý các kiểu phương thức và phạm vi truy cập, cách đăng ký chúng với `ChatClient` hoặc `MethodToolCallback`, cùng những lựa chọn phù hợp khi xây dựng công cụ nghiệp vụ.

## Sau bài học, bạn có thể

- Phân biệt tool được khai báo trên phương thức instance và phương thức `static`.
- Biết các mức truy cập method được Spring AI hỗ trợ.
- Phân biệt visibility của method với khả năng truy cập và khởi tạo class chứa method.
- Chọn cách đăng ký tool phù hợp: truyền tool object qua `ChatClient` hay tạo `MethodToolCallback` trực tiếp.
- Nhận biết yêu cầu reflection khi đóng gói ứng dụng thành GraalVM native image.
- Thiết kế tool dễ kiểm thử, có dependency rõ ràng và không giữ trạng thái request trong biến dùng chung.

## Spring AI hỗ trợ những dạng phương thức nào?

Với cách khai báo annotation, Spring AI có thể tạo tool từ một method được đánh dấu `@Tool`. Theo tài liệu Spring AI 1.0, method đó có thể là:

- **Instance method:** cần một object để thực thi và có thể dùng dependency hoặc trạng thái thuộc instance.
- **Static method:** được gọi trên class, không cần object chứa method để thực thi.
- **Public, protected, package-private hoặc private:** Spring AI có thể tìm và gọi method qua cơ chế reflection.

Class chứa method có thể là class top-level hoặc nested class. Class cũng có thể có phạm vi truy cập khác nhau, miễn là nó truy cập được tại nơi ứng dụng cần khởi tạo hoặc đăng ký tool. Trong Java, class top-level chỉ có thể là `public` hoặc package-private; các mức `private` và `protected` chỉ áp dụng cho nested class.

| Thuộc tính | Các dạng được hỗ trợ | Điều cần lưu ý |
|---|---|---|
| Loại method | Instance, `static` | Instance cần object; static không cần object để gọi |
| Visibility của method | `public`, `protected`, package-private, `private` | Spring AI dùng reflection để thực thi method |
| Class chứa method | Top-level hoặc nested class | Class phải truy cập được tại nơi tạo hoặc đăng ký tool |
| Kiểu trả về | `void` hoặc kiểu có thể serialize | Giá trị trả về được chuyển thành kết quả gửi cho model |
| Tham số | Nhiều kiểu Java thông dụng | Tham số được ánh xạ thành JSON schema; một số kiểu đặc biệt không được hỗ trợ |

Như vậy, một method private vẫn có thể là tool. Tuy nhiên, việc Spring AI có thể gọi method private không có nghĩa mọi class private đều có thể được tạo từ mọi nơi trong mã Java. Hai vấn đề này cần được xem xét riêng.

## Instance method: lựa chọn phổ biến cho tool nghiệp vụ

Instance method phù hợp khi tool cần sử dụng dependency do Spring quản lý, ví dụ repository, service, client HTTP, cấu hình hoặc thành phần nghiệp vụ khác.

Ví dụ, tool tra cứu trạng thái đơn hàng cần gọi `OrderQueryService`:

~~~java
@Component
public class OrderTools {

    private final OrderQueryService orderQueryService;

    public OrderTools(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @Tool(description = "Tra cứu trạng thái của đơn hàng theo mã đơn hàng")
    public OrderStatus getOrderStatus(
            @ToolParam(description = "Mã đơn hàng cần tra cứu") String orderId) {

        return orderQueryService.getStatus(orderId);
    }
}
~~~

Ở đây:

- `OrderTools` là Spring bean, được tạo thông qua dependency injection.
- `getOrderStatus` là instance method, vì vậy nó có thể truy cập field `orderQueryService` của object.
- `@Tool` đánh dấu method là khả năng có thể được model yêu cầu gọi.
- `@ToolParam` mô tả ý nghĩa tham số `orderId`, giúp Spring AI tạo schema đầu vào cho model.

Khi đăng ký tool theo cách khai báo, truyền object đã được Spring tạo vào `ChatClient`:

~~~java
String answer = chatClient.prompt()
        .user("Kiểm tra trạng thái đơn hàng DH-1024")
        .tools(orderTools)
        .call()
        .content();
~~~

Spring AI tạo các `ToolCallback` từ những method có `@Tool` trên object được cung cấp. Vì vậy, khi tool cần repository hoặc service, hãy truyền bean đã được inject dependency thay vì tự tạo object bằng `new` ở nhiều nơi.

### Vì sao instance method thường phù hợp với nghiệp vụ?

Một tool nghiệp vụ thường là adapter mỏng giữa yêu cầu của model và service hiện có. Instance method giúp adapter nhận dependency qua constructor:

~~~java
@Component
public class CustomerTools {

    private final CustomerQueryService customerQueryService;
    private final AccessPolicy accessPolicy;

    public CustomerTools(
            CustomerQueryService customerQueryService,
            AccessPolicy accessPolicy) {
        this.customerQueryService = customerQueryService;
        this.accessPolicy = accessPolicy;
    }

    @Tool(description = "Tra cứu thông tin khách hàng theo mã khách hàng")
    private CustomerSummary findCustomer(
            @ToolParam(description = "Mã khách hàng") String customerId,
            ToolContext toolContext) {

        String userId = (String) toolContext.getContext().get("userId");

        accessPolicy.requireCanViewCustomer(userId, customerId);
        return customerQueryService.getSummary(customerId);
    }
}
~~~

Method `findCustomer` là `private`, nhưng vẫn có thể được Spring AI gọi. Nó sử dụng các dependency của instance để kiểm tra quyền và truy vấn dữ liệu. `ToolContext` mang ngữ cảnh do ứng dụng cung cấp; nó không phải tham số do model tự khai báo trong JSON.

Lưu ý rằng Spring bean mặc định thường có scope singleton. Instance method không có nghĩa mỗi lần gọi tool sẽ có một object mới. Không lưu dữ liệu riêng của người dùng hoặc trạng thái từng request vào field có thể thay đổi của tool bean. Hãy truyền ngữ cảnh theo tham số phù hợp, chẳng hạn `ToolContext`, và để dịch vụ nghiệp vụ kiểm tra quyền ở phía server.

## Static method: phù hợp với thao tác không cần instance

Static method phù hợp khi thao tác là hàm tiện ích độc lập, không cần dependency được inject và không cần trạng thái của object.

Ví dụ một hàm chuẩn hóa mã tham chiếu:

~~~java
public final class ReferenceCodeTools {

    private ReferenceCodeTools() {
    }

    @Tool(description = "Chuẩn hóa mã tham chiếu thành chữ in hoa và loại bỏ khoảng trắng thừa")
    public static String normalizeReference(
            @ToolParam(description = "Mã tham chiếu cần chuẩn hóa") String value) {

        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Mã tham chiếu không được để trống");
        }

        return value.trim().toUpperCase(Locale.ROOT);
    }
}
~~~

Method `normalizeReference` không đọc field của object và không gọi dependency bên ngoài. Kết quả chỉ phụ thuộc vào tham số đầu vào, nên static method có thể là lựa chọn hợp lý cho phép chuyển đổi dữ liệu đơn giản.

Tuy nhiên, không nên biến mọi tool thành static chỉ để tránh tạo bean. Nếu tool cần database, HTTP client, cấu hình, kiểm tra quyền hoặc logic nghiệp vụ, instance method với constructor injection thường dễ quản lý và kiểm thử hơn.

### Đăng ký static method bằng MethodToolCallback

Khi cần tạo callback trực tiếp từ một method, Spring AI cung cấp `MethodToolCallback`. Với static method, không cần cung cấp `toolObject`:

~~~java
Method method = ReflectionUtils.findMethod(
        ReferenceCodeTools.class,
        "normalizeReference",
        String.class
);

if (method == null) {
    throw new IllegalStateException("Không tìm thấy normalizeReference");
}

ToolCallback callback = MethodToolCallback.builder()
        .toolDefinition(
                ToolDefinitions.builder(method)
                        .description("Chuẩn hóa mã tham chiếu")
                        .build()
        )
        .toolMethod(method)
        .build();
~~~

Sau đó có thể truyền callback vào yêu cầu của `ChatClient`:

~~~java
String result = chatClient.prompt()
        .user("Chuẩn hóa mã tham chiếu ab- 1024")
        .toolCallbacks(callback)
        .call()
        .content();
~~~

Trong ví dụ này:

- `toolMethod(method)` chỉ định method Java cần thực thi.
- `toolDefinition(...)` xác định tên, mô tả và schema đầu vào của tool.
- Không có `toolObject(...)` vì method là static.

Nếu method là instance method, builder cần object chứa method:

~~~java
ToolCallback callback = MethodToolCallback.builder()
        .toolDefinition(
                ToolDefinitions.builder(instanceMethod)
                        .description("Tra cứu trạng thái đơn hàng")
                        .build()
        )
        .toolMethod(instanceMethod)
        .toolObject(orderTools)
        .build();
~~~

`MethodToolCallback` hữu ích khi cần tạo callback động, tùy chỉnh tool definition hoặc đăng ký method mà không muốn dựa hoàn toàn vào việc truyền tool object theo cách khai báo. Nếu chỉ cần sử dụng một nhóm method có `@Tool` ổn định, cách truyền bean vào `ChatClient` thường gọn hơn.

## Visibility của method: public không phải điều kiện bắt buộc

Trong Java, visibility quyết định nơi mã nguồn có thể truy cập một member theo quy tắc ngôn ngữ. Spring AI sử dụng reflection để tìm và gọi các method được khai báo làm tool, vì vậy method không bắt buộc phải là public.

### Public

Public method có thể được gọi từ mọi nơi có quyền truy cập class. Cách khai báo này dễ nhận biết khi đọc code và phù hợp nếu method đồng thời là một API công khai của class.

~~~java
@Tool(description = "Lấy tỷ giá của một cặp tiền tệ")
public ExchangeRate getExchangeRate(String currencyPair) {
    return exchangeRateService.find(currencyPair);
}
~~~

### Protected

Protected method có thể được truy cập từ class cùng package và các subclass theo quy tắc Java. Spring AI vẫn hỗ trợ method này làm tool.

~~~java
@Tool(description = "Tra cứu hạn mức giao dịch của khách hàng")
protected TransactionLimit getTransactionLimit(String customerId) {
    return limitService.getLimit(customerId);
}
~~~

### Package-private

Khi không khai báo modifier, method có phạm vi package-private. Mã nguồn trong cùng package có thể truy cập method theo quy tắc Java.

~~~java
@Tool(description = "Kiểm tra trạng thái xác minh khách hàng")
CustomerVerificationStatus getVerificationStatus(String customerId) {
    return verificationService.getStatus(customerId);
}
~~~

Package-private có thể phù hợp khi tool chỉ là chi tiết triển khai của một module và không cần trở thành API công khai của class.

### Private

Private method chỉ được truy cập trực tiếp từ bên trong class khai báo nó theo quy tắc Java. Spring AI vẫn có thể gọi method private thông qua cơ chế reflection.

~~~java
@Tool(description = "Kiểm tra một mã tham chiếu có hợp lệ hay không")
private boolean isReferenceValid(String reference) {
    return reference != null && reference.matches("[A-Z]{2}-\\d{4}");
}
~~~

Private method hữu ích khi muốn giữ chi tiết triển khai bên trong class. Nhưng hãy cân nhắc khả năng bảo trì: một tool private có thể khó được phát hiện khi người đọc chỉ tìm các API public. Mô tả `@Tool` rõ ràng và kiểm thử đăng ký tool giúp làm rõ chủ đích.

| Visibility | Spring AI hỗ trợ làm `@Tool`? | Phạm vi truy cập theo Java |
|---|---|---|
| `public` | Có | Mọi nơi có thể truy cập class |
| `protected` | Có | Cùng package và subclass theo quy tắc Java |
| Package-private | Có | Cùng package |
| `private` | Có | Bên trong class khai báo |

Hãy chọn visibility theo thiết kế class và phạm vi sử dụng trong mã ứng dụng. Không cần đổi method thành public chỉ để Spring AI nhận diện nó.

## Visibility của class chứa tool

Phạm vi của method và phạm vi của class là hai vấn đề riêng. Dù Spring AI hỗ trợ method private, mã ứng dụng vẫn phải có cách lấy hoặc tạo object nếu method là instance method.

Các dạng class thường gặp:

- **Top-level public class:** có thể được tham chiếu từ package khác nếu package và module cho phép.
- **Top-level package-private class:** chỉ có thể được tham chiếu trực tiếp trong cùng package.
- **Static nested class:** có thể được tham chiếu mà không cần object của lớp bên ngoài; visibility của nested class tuân theo modifier khai báo.
- **Non-static inner class:** cần một instance của lớp bên ngoài để tạo instance của inner class.
- **Private nested class:** chỉ có thể được truy cập trực tiếp từ phạm vi cho phép bên trong lớp bao ngoài; nơi đăng ký tool phải có khả năng tạo hoặc nhận instance hợp lệ.

Ví dụ một static nested class:

~~~java
public class SupportToolContainer {

    @Component
    public static class TicketTools {

        private final TicketQueryService ticketQueryService;

        public TicketTools(TicketQueryService ticketQueryService) {
            this.ticketQueryService = ticketQueryService;
        }

        @Tool(description = "Tra cứu yêu cầu hỗ trợ theo mã")
        private TicketSummary getTicket(String ticketId) {
            return ticketQueryService.getSummary(ticketId);
        }
    }
}
~~~

Static nested class không cần instance của `SupportToolContainer` để tạo. Nếu dùng nested class làm Spring bean, hãy đảm bảo cấu trúc class và component scanning phù hợp với cấu hình ứng dụng. Trong phần lớn dự án, một top-level class riêng cho mỗi nhóm tool thường dễ tìm kiếm và quản lý hơn.

Với instance method, đường đăng ký cần có object:

~~~java
ChatClient chatClient = ChatClient.builder(chatModel)
        .build();

String answer = chatClient.prompt()
        .user("Tra cứu yêu cầu hỗ trợ TK-100")
        .tools(ticketTools)
        .call()
        .content();
~~~

Nếu class không thể được truy cập tại nơi tạo instance, hãy điều chỉnh cấu trúc package/class hoặc cung cấp bean từ một cấu hình có quyền truy cập phù hợp. Việc đổi modifier method không giải quyết được việc class chứa nó không thể được khởi tạo.

## Chọn instance hay static trong tình huống thực tế

| Nhu cầu của tool | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Truy vấn database qua repository | Instance method | Cần dependency được inject |
| Gọi API qua HTTP client | Instance method | Dùng client, cấu hình và timeout do Spring quản lý |
| Kiểm tra quyền hoặc chính sách nghiệp vụ | Instance method | Cần service và ngữ cảnh của ứng dụng |
| Chuẩn hóa chuỗi theo quy tắc cố định | Static method có thể phù hợp | Không cần trạng thái hoặc dependency |
| Chuyển đổi giá trị thuần túy | Static method có thể phù hợp | Đầu ra chỉ phụ thuộc tham số |
| Tạo callback từ method được chọn lúc chạy | `MethodToolCallback` | Có thể chỉ định method và object tường minh |

Một số câu hỏi giúp chọn nhanh:

1. Method có cần repository, service hoặc client được inject không? Nếu có, dùng instance method.
2. Kết quả có phụ thuộc trạng thái của object không? Nếu có, dùng instance method và quản lý trạng thái theo request ở đúng nơi.
3. Method có thực sự là phép tính thuần túy, không phụ thuộc cấu hình hoặc dịch vụ không? Nếu có, static method có thể phù hợp.
4. Tool class có được Spring tạo và quản lý không? Nếu có, truyền bean vào `ChatClient` giúp dependency injection hoạt động đúng.
5. Có cần tạo tool động từ một `java.lang.reflect.Method` không? Nếu có, cân nhắc `MethodToolCallback`.

Không dùng static field để lưu user ID, tenant ID, access token hoặc dữ liệu hội thoại. Static state được chia sẻ giữa các lần gọi và có thể gây rò rỉ dữ liệu giữa người dùng. Với instance bean singleton, cũng không lưu trạng thái request trong field mutable. Cả hai kiểu method đều cần thiết kế an toàn khi nhiều request chạy đồng thời.

## Reflection và GraalVM native image

Việc gọi method private hoặc method có visibility khác public thường dựa vào reflection. Trong ứng dụng chạy trên JVM thông thường, Spring AI hỗ trợ các method được khai báo làm tool theo các quy tắc đã nêu. Khi biên dịch Ahead-of-Time hoặc tạo GraalVM native image, reflection cần được khai báo để công cụ build biết member nào sẽ được truy cập lúc runtime.

Spring AI cung cấp hỗ trợ AOT cho class chứa method `@Tool` khi class đó là Spring bean, ví dụ được đánh dấu `@Component`. Nếu class không phải Spring bean, cần cung cấp reflection hint tương ứng. Tài liệu Spring AI 1.0 minh họa bằng `@RegisterReflection`:

~~~java
@RegisterReflection(
        memberCategories = MemberCategory.INVOKE_DECLARED_METHODS
)
public class UtilityTools {

    @Tool(description = "Chuẩn hóa mã tham chiếu")
    private static String normalize(String value) {
        return value.trim().toUpperCase(Locale.ROOT);
    }
}
~~~

Các import cụ thể gồm annotation và member category của Spring AOT. Hãy kiểm tra API theo phiên bản Spring Framework/Spring Boot mà dự án đang dùng. Reflection hint cần phù hợp với các method thực sự được gọi; không mở reflection cho toàn bộ classpath nếu chỉ cần một nhóm method.

Nếu ứng dụng chỉ chạy trên JVM, không cần thêm cấu hình native image chỉ vì method có visibility private. Nếu dự án triển khai native image, hãy kiểm tra build AOT và chạy test trên binary native để phát hiện thiếu reflection metadata.

## Giới hạn của chữ ký method

Spring AI hỗ trợ nhiều kiểu tham số và giá trị trả về thông dụng như primitive, POJO, enum, list, array và map. Giá trị trả về phải có thể serialize để gửi về model; method có thể trả về `void` nếu chỉ thực hiện thao tác.

Tuy nhiên, tài liệu Spring AI 1.0 liệt kê một số kiểu chưa được hỗ trợ làm tham số hoặc giá trị trả về của method-based tool:

- `Optional`;
- các kiểu bất đồng bộ như `CompletableFuture` và `Future`;
- các kiểu reactive như `Mono`, `Flux` và `Flow`;
- các kiểu hàm như `Function`, `Supplier` và `Consumer`.

Nếu cần công cụ dựa trên `Function`, `Supplier` hoặc `Consumer`, hãy dùng `FunctionToolCallback` thay vì khai báo chúng như tham số/giá trị trả về của method-based tool. Với dữ liệu có thể vắng mặt, hãy dùng kiểu dữ liệu được schema hỗ trợ cùng `@ToolParam(required = false)` hoặc `@Nullable` thay cho `Optional`.

### @ToolParam không phụ thuộc instance hay static

Dù method là instance hay static, các tham số hiển thị cho model vẫn được mô tả bằng cùng cơ chế schema. Ví dụ:

~~~java
@Tool(description = "Tìm sản phẩm theo mã và ngôn ngữ hiển thị")
public ProductSummary findProduct(
        @ToolParam(description = "Mã SKU chính xác") String sku,
        @ToolParam(description = "Mã ngôn ngữ, ví dụ vi hoặc en", required = false)
        String locale) {

    return productService.findSummary(sku, locale);
}
~~~

Mặc định các tham số là bắt buộc. Có thể đánh dấu tham số không bắt buộc bằng `@ToolParam(required = false)` hoặc `@Nullable`. Mô tả nên nói rõ định dạng, phạm vi giá trị và điều kiện sử dụng. Schema đầu vào là hợp đồng với model; việc validation nghiệp vụ vẫn phải diễn ra trong ứng dụng.

`ToolContext` có thể được truyền vào method để cung cấp dữ liệu nội bộ do ứng dụng xác định. Dữ liệu này không phải trường JSON để model tự gửi. Vì vậy, method có thể dùng `ToolContext` cùng các tham số nghiệp vụ dù nó là instance hay static, miễn là cách đăng ký và chữ ký method phù hợp với phiên bản Spring AI.

## Kiểm thử method-based tool

Kiểm thử nên xác nhận cả việc method được phát hiện lẫn hành vi khi callback thực thi.

- **Kiểm thử đăng ký:** xác nhận method có `@Tool` được tạo thành callback và tên tool không bị trùng trong tập tool của request.
- **Kiểm thử visibility:** kiểm tra các method public, protected, package-private hoặc private cần dùng có thể được Spring AI gọi trong cấu hình dự án.
- **Kiểm thử instance:** xác nhận callback dùng đúng object và dependency đã được inject.
- **Kiểm thử static:** xác nhận callback thực thi mà không cần truyền `toolObject`.
- **Kiểm thử schema:** xác nhận tên tham số, mô tả, kiểu dữ liệu và trạng thái required/optional đúng như dự kiến.
- **Kiểm thử đồng thời:** xác nhận tool không dùng mutable state dùng chung để giữ dữ liệu của từng request.
- **Kiểm thử AOT:** nếu phát hành native image, chạy kiểm thử trên binary native để phát hiện thiếu reflection hint.

Một test tập trung cho instance method có thể kiểm tra rằng service được gọi đúng một lần với mã đầu vào:

~~~java
@Test
void shouldLookupOrderThroughInjectedService() {
    when(orderQueryService.getStatus("DH-1024"))
            .thenReturn(OrderStatus.SHIPPED);

    OrderStatus result = orderTools.getOrderStatus("DH-1024");

    assertThat(result).isEqualTo(OrderStatus.SHIPPED);
    verify(orderQueryService).getStatus("DH-1024");
}
~~~

Test service trực tiếp xác minh logic nghiệp vụ. Ngoài ra, nên có test callback hoặc integration test để xác nhận Spring AI thực sự tạo và gọi tool theo schema. Không nên xem unit test gọi method Java trực tiếp là bằng chứng đầy đủ rằng reflection, schema và đăng ký tool đều hoạt động.

## Những lỗi thiết kế thường gặp

**Cho rằng method bắt buộc phải public.** Spring AI hỗ trợ nhiều mức truy cập. Hãy chọn visibility theo thiết kế class, rồi kiểm thử đường đăng ký thực tế.

**Dùng static method để gọi dependency được quản lý bởi Spring.** Static method không có instance để nhận constructor injection. Hãy dùng instance method và inject service qua constructor.

**Dùng private class rồi cố khởi tạo từ package khác.** Spring AI có thể gọi method private, nhưng Java vẫn áp dụng quy tắc truy cập class. Hãy đảm bảo class có thể được tạo hoặc bean có thể được inject tại nơi đăng ký.

**Truyền object mới thay cho bean đã inject.** Nếu tool cần repository hoặc client, `new ToolClass()` có thể bỏ qua dependency injection. Hãy truyền bean được Spring quản lý.

**Lưu dữ liệu người dùng vào static field hoặc field mutable của singleton.** Nhiều request có thể dùng chung object. Truyền ngữ cảnh theo request và giữ tool bean stateless.

**Dùng chữ ký method không được hỗ trợ.** Không dùng `Optional`, `Mono` hoặc `CompletableFuture` làm tham số/giá trị trả về của method-based tool theo danh sách giới hạn của Spring AI 1.0. Chọn kiểu dữ liệu tuần tự hóa được hoặc callback theo Function API.

**Quên reflection metadata khi tạo native image.** Một method hoạt động trên JVM có thể không được gọi nếu native image thiếu hint. Kiểm tra AOT và đăng ký reflection theo yêu cầu.

## Ghi nhớ khi thiết kế

Spring AI cho phép method `@Tool` là instance hoặc static, đồng thời hỗ trợ các mức truy cập public, protected, package-private và private. Instance method phù hợp với tool nghiệp vụ cần dependency injection; static method phù hợp với thao tác độc lập không cần trạng thái object. Method private vẫn có thể được gọi qua reflection, nhưng class chứa method phải truy cập được tại nơi ứng dụng khởi tạo hoặc đăng ký tool.

Hãy chọn cấu trúc class, cách đăng ký callback và visibility theo trách nhiệm của tool. Với dự án chạy native image, bổ sung và kiểm tra reflection metadata. Với mọi kiểu method, giữ logic nghiệp vụ trong service phù hợp, xác thực đầu vào và quyền ở phía ứng dụng, rồi kiểm thử cả method lẫn callback mà model sẽ sử dụng.

## Tài liệu tham khảo

- [Spring AI 1.0 Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/1.0/api/tools.html)
- [Spring AI Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)

