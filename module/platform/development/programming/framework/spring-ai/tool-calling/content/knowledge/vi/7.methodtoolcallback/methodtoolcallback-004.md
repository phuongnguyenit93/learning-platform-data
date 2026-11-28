# Chuyển JSON đối số sang tham số Java

`MethodToolCallback` là implementation của `ToolCallback` dùng để biến một phương thức Java thành tool. Khi mô hình chọn tool, nó gửi một chuỗi JSON chứa các đối số. Callback parse chuỗi đó, chuyển từng giá trị thành kiểu Java tương ứng, gọi phương thức bằng reflection và chuyển kết quả thành chuỗi để trả về cho vòng tool calling.

Điểm cốt lõi là **liên kết giữa tên thuộc tính JSON và tên tham số Java**. JSON object không dựa vào thứ tự trường; callback tìm giá trị theo tên tham số rồi đặt giá trị vào đúng vị trí khi gọi method. Vì vậy, schema, tên tham số được giữ trong bytecode và chữ ký phương thức phải nhất quán.

## 1. Luồng chuyển đổi tổng quát

Giả sử ứng dụng cung cấp tool tra cứu tồn kho:

~~~java
public StockView lookupInventory(
        String sku,
        WarehouseCode warehouse,
        Integer minimumQuantity) {
    // Gọi dịch vụ tồn kho
}
~~~

Mô hình có thể trả về arguments:

~~~json
{
  "sku": "SKU-100",
  "warehouse": "HANOI",
  "minimumQuantity": 5
}
~~~

Đây là chuỗi JSON đầu vào của callback, chưa phải lời gọi Java. Luồng chuyển đổi diễn ra như sau:

~~~mermaid
flowchart TD
    A["Model trả về tool call"] --> B["JSON arguments"]
    B --> C["MethodToolCallback.call(...)"]
    C --> D["Parse JSON thành Map"]
    D --> E["Đọc từng tham số của Method"]
    E --> F{"Tham số là ToolContext?"}
    F -->|Có| G["Chèn ToolContext từ ứng dụng"]
    F -->|Không| H["Lấy giá trị theo tên tham số"]
    H --> I["Chuyển về kiểu Java tương ứng"]
    G --> J["Tạo Object[] theo thứ tự tham số"]
    I --> J
    J --> K["Reflection invoke method"]
    K --> L["ToolCallResultConverter"]
    L --> M["Chuỗi tool result"]
~~~

Các bước chính:

1. `ToolCallingManager` tìm callback theo tên tool và gọi `ToolCallback.call(toolInput, toolContext)`.
2. `MethodToolCallback` parse chuỗi JSON thành map các cặp tên thuộc tính và giá trị.
3. Callback đọc các tham số của method đã đăng ký.
4. Với từng tham số, callback lấy giá trị theo tên tham số và chuyển sang kiểu Java tương ứng. Nếu tham số là `ToolContext`, callback nhận context do ứng dụng truyền vào.
5. Callback tạo mảng đối số theo thứ tự khai báo trong method và gọi method bằng reflection.
6. Kết quả method được chuyển thành chuỗi để gửi lại cho mô hình.

Thứ tự thuộc tính trong JSON không quyết định thứ tự tham số Java. Việc ghép dữ liệu dựa trên tên thuộc tính.

## 2. Tạo MethodToolCallback từ một phương thức

`MethodToolCallback` phù hợp khi muốn tạo tool theo cách lập trình, ví dụ đăng ký tool động theo cấu hình hoặc quyền của người dùng.

Ví dụ lớp nghiệp vụ:

~~~java
public enum WarehouseCode {
    HANOI,
    HO_CHI_MINH,
    DA_NANG
}

public record StockView(
    String sku,
    WarehouseCode warehouse,
    int availableQuantity
) {}

@Component
public class InventoryTools {

    private final InventoryService inventoryService;

    public InventoryTools(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    public StockView lookupInventory(
            String sku,
            WarehouseCode warehouse,
            Integer minimumQuantity) {

        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU không được để trống");
        }

        if (minimumQuantity != null && minimumQuantity < 0) {
            throw new IllegalArgumentException("Số lượng tối thiểu phải không âm");
        }

        return inventoryService.lookup(sku, warehouse, minimumQuantity);
    }
}
~~~

Tạo callback bằng builder:

~~~java
@Configuration
public class InventoryToolConfiguration {

    @Bean
    ToolCallback lookupInventoryTool(InventoryTools inventoryTools)
            throws NoSuchMethodException {

        Method method = InventoryTools.class.getMethod(
            "lookupInventory",
            String.class,
            WarehouseCode.class,
            Integer.class
        );

        ToolDefinition definition = ToolDefinitions.builder(method)
            .description("Tra cứu tồn kho theo SKU, kho và số lượng tối thiểu.")
            .build();

        return MethodToolCallback.builder()
            .toolDefinition(definition)
            .toolMethod(method)
            .toolObject(inventoryTools)
            .build();
    }
}
~~~

Ba thành phần quyết định callback hoạt động:

- `toolDefinition` mô tả tên tool, nội dung hướng dẫn mô hình và input schema.
- `toolMethod` là đối tượng phản chiếu `Method` mà callback sẽ gọi.
- `toolObject` là instance chứa method. Với method instance, trường này là bắt buộc; với method static thì có thể bỏ qua.

Trong ví dụ, `inventoryTools` được inject từ Spring container để giữ các dependency và cấu hình mà bean đang sử dụng. Không nên tạo một instance rời bằng `new InventoryTools(...)` nếu lớp cần các service, transaction hoặc proxy do Spring quản lý.

`ToolDefinitions.builder(method)` có thể tạo định nghĩa từ method và cho phép tùy chỉnh mô tả. Nếu tự tạo input schema, các tên thuộc tính trong schema vẫn phải khớp tên tham số mà callback dùng để lấy giá trị.

Sau khi tạo callback, có thể cung cấp nó cho `ChatClient` theo từng request:

~~~java
String answer = chatClient.prompt()
    .user("Kiểm tra SKU-100 tại kho Hà Nội.")
    .tools(lookupInventoryTool)
    .call()
    .content();
~~~

Trong luồng này, `ChatClient` gửi tool definition cho mô hình và vòng tool calling sẽ gọi callback khi mô hình yêu cầu. Đoạn `callback.call(json)` ở các phần sau hữu ích để kiểm thử trực tiếp bước chuyển đổi JSON; ứng dụng thường để `ChatClient` và `ToolCallingAdvisor` điều phối lượt gọi.

## 3. Parse JSON thành map đối số

`ToolCallback.call` nhận `toolInput` là chuỗi JSON. Ví dụ:

~~~java
String toolInput = """
    {
      "sku": "SKU-100",
      "warehouse": "HANOI",
      "minimumQuantity": 5
    }
    """;
~~~

Sau khi parse, dữ liệu có cấu trúc tương đương một map:

~~~java
Map<String, Object> arguments = Map.of(
    "sku", "SKU-100",
    "warehouse", "HANOI",
    "minimumQuantity", 5
);
~~~

Đây là biểu diễn khái niệm. Giá trị trong map có thể là chuỗi, số, boolean, map lồng nhau, list hoặc `null` tùy JSON đầu vào.

JSON đầu vào phải là một object có cú pháp hợp lệ. JSON bị cắt, thiếu dấu ngoặc, gửi mảng ở cấp gốc hoặc gửi văn bản không phải JSON đều có thể khiến bước parse thất bại.

## 4. Ghép thuộc tính JSON với tham số Java

Giả sử method có chữ ký:

~~~java
public StockView lookupInventory(
        String sku,
        WarehouseCode warehouse,
        Integer minimumQuantity) {
    // ...
}
~~~

Callback lấy dữ liệu theo tên tham số:

| Tham số Java | Khóa JSON | Giá trị mẫu | Kiểu đích |
|---|---|---|---|
| `sku` | `sku` | `"SKU-100"` | `String` |
| `warehouse` | `warehouse` | `"HANOI"` | `WarehouseCode` |
| `minimumQuantity` | `minimumQuantity` | `5` | `Integer` |

Sau khi chuyển đổi, callback tạo mảng đối số theo đúng thứ tự method:

~~~java
Object[] methodArguments = {
    "SKU-100",
    WarehouseCode.HANOI,
    Integer.valueOf(5)
};
~~~

Có hai quy tắc cần giữ:

- Tên khóa JSON phải khớp tên tham số Java.
- Vị trí phần tử trong mảng phải khớp thứ tự tham số của method.

JSON object không cần sắp xếp khóa giống chữ ký Java. Ví dụ sau vẫn ánh xạ đúng:

~~~json
{
  "minimumQuantity": 5,
  "warehouse": "HANOI",
  "sku": "SKU-100"
}
~~~

### 4.1. Giữ tên tham số khi biên dịch

Java reflection chỉ đọc được tên tham số có ý nghĩa nếu class được biên dịch với thông tin tên tham số. Nếu thiếu cờ `-parameters`, `Parameter.getName()` có thể trả về tên tổng quát như `arg0`, `arg1` thay vì `sku` hoặc `warehouse`.

Khi đó schema có thể lộ ra các tên khó hiểu, và callback cũng không tìm thấy các khóa `sku`, `warehouse` trong map theo tên tham số mong đợi.

Với Maven, có thể bật lưu tên tham số:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Với Gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Một số cấu hình Spring Boot đã bật tùy chọn này. Dù vậy, hãy kiểm tra cấu hình compiler thực tế của module và xác minh schema được sinh ra. Đừng suy đoán tên tham số chắc chắn được giữ chỉ vì source code có tên biến rõ ràng.

`@ToolParam` dùng để mô tả tham số và khai báo tính bắt buộc; nó không cung cấp thuộc tính đổi tên tham số Java. Hãy đặt tên tham số có ý nghĩa và nhất quán với JSON key.

## 5. Chuyển đổi giá trị sang kiểu Java

Sau khi lấy được giá trị thô từ map, callback chuyển nó sang kiểu khai báo trong method. Kiểu đích được xác định từ metadata của tham số, bao gồm generic type khi có.

### 5.1. Chuỗi, số và boolean

Ví dụ chữ ký:

~~~java
public SearchResult search(
        String keyword,
        Integer page,
        BigDecimal minimumPrice,
        Boolean includeOutOfStock) {
    // ...
}
~~~

JSON arguments:

~~~json
{
  "keyword": "laptop",
  "page": 2,
  "minimumPrice": 15000000.00,
  "includeOutOfStock": false
}
~~~

Các giá trị JSON được chuyển sang kiểu Java tương ứng:

- Chuỗi JSON thành `String`.
- Số nguyên thành kiểu số nguyên phù hợp như `Integer`.
- Số thập phân thành kiểu số như `BigDecimal`.
- Giá trị đúng/sai thành `Boolean`.

Không nên gửi số dưới dạng chuỗi nếu schema khai báo kiểu số. Ví dụ `"2"` khác `2`. Dữ liệu sai kiểu có thể gây lỗi chuyển đổi trước khi method được gọi.

### 5.2. Enum

Giả sử method nhận:

~~~java
public StockView lookup(String sku, WarehouseCode warehouse) {
    // ...
}
~~~

JSON:

~~~json
{
  "sku": "SKU-100",
  "warehouse": "HANOI"
}
~~~

Giá trị `"HANOI"` được chuyển thành `WarehouseCode.HANOI`. Tên enum phải khớp với hằng enum mà ứng dụng khai báo và quy tắc chuyển đổi đang dùng.

Nếu mô hình gửi `"HaNoi"` hoặc `"Hanoi Warehouse"` trong khi enum chỉ có `HANOI`, việc chuyển đổi có thể thất bại. Hãy mô tả các lựa chọn rõ ràng trong input schema và xác thực dữ liệu ở backend.

### 5.3. Object và record lồng nhau

JSON object lồng nhau có thể được chuyển thành record hoặc POJO tương ứng.

Ví dụ kiểu Java:

~~~java
public record QuantityRange(
    Integer minimum,
    Integer maximum
) {}

public record InventoryFilter(
    QuantityRange quantity,
    Boolean includeZeroStock
) {}

public StockView search(String sku, InventoryFilter filter) {
    // ...
}
~~~

JSON arguments:

~~~json
{
  "sku": "SKU-100",
  "filter": {
    "quantity": {
      "minimum": 5,
      "maximum": 30
    },
    "includeZeroStock": false
  }
}
~~~

Callback chuyển object `filter` thành `InventoryFilter`; object `quantity` bên trong trở thành `QuantityRange`. Các thuộc tính con được ánh xạ theo tên và kiểu tương ứng.

Với record, nên giữ tên component rõ ràng và dùng cấu trúc dữ liệu có thể serialize/deserialize bằng Jackson. Với POJO, kiểm tra tên thuộc tính, constructor và cấu hình Jackson phù hợp.

### 5.4. List và generic type

Ví dụ method:

~~~java
public List<StockView> lookupMany(List<String> skus) {
    // ...
}
~~~

JSON:

~~~json
{
  "skus": ["SKU-100", "SKU-200", "SKU-300"]
}
~~~

Callback cần giữ thông tin generic `List<String>` để chuyển từng phần tử thành chuỗi. Nếu chỉ biết kiểu raw `List`, thông tin kiểu phần tử sẽ không đầy đủ.

Spring AI sử dụng kiểu tham số tổng quát khi chuyển đổi để xử lý các cấu trúc như danh sách object hoặc map lồng nhau. Dù chuyển đổi thành công, ứng dụng vẫn phải giới hạn số phần tử, kiểm tra từng mã và kiểm soát kích thước kết quả.

## 6. ToolContext được chèn riêng

`ToolContext` không phải đối số do mô hình tạo ra. Đây là dữ liệu ngữ cảnh do ứng dụng cung cấp để method dùng nội bộ, chẳng hạn tenant ID, user ID, request metadata hoặc thông tin phiên đã xác thực.

Ví dụ method:

~~~java
public StockView lookupInventory(
        String sku,
        WarehouseCode warehouse,
        ToolContext toolContext) {

    String tenantId = (String) toolContext.getContext().get("tenantId");

    if (tenantId == null || tenantId.isBlank()) {
        throw new AccessDeniedException("Thiếu tenant hợp lệ");
    }

    return inventoryService.lookup(tenantId, sku, warehouse);
}
~~~

Khi gọi callback trực tiếp, ứng dụng truyền context:

~~~java
String result = lookupInventoryTool.call(
    """
    {
      "sku": "SKU-100",
      "warehouse": "HANOI"
    }
    """,
    new ToolContext(Map.of("tenantId", authenticatedTenantId))
);
~~~

Trong quá trình build đối số, `MethodToolCallback` nhận diện tham số có kiểu `ToolContext` và chèn context được truyền vào. Nó không tìm khóa `toolContext` trong JSON arguments.

Do đó:

- `ToolContext` không xuất hiện trong input schema của mô hình.
- Tenant ID và user ID phải lấy từ security context hoặc nguồn server-side đáng tin cậy.
- Backend vẫn phải kiểm tra quyền trước khi truy cập dữ liệu.
- Không đưa bí mật, token hoặc quyền hạn vào JSON arguments để mô hình tự điền.

Nếu method có tham số `ToolContext` nhưng callback được gọi mà không có context cần thiết, quá trình thực thi có thể thất bại. Hãy bảo đảm đường gọi luôn truyền context hợp lệ khi method yêu cầu.

## 7. Gọi method bằng reflection và chuyển kết quả

Sau khi tạo đủ đối số, callback dùng `Method.invoke(...)` để gọi method trên instance đã đăng ký. Với method instance, target là `toolObject`; với method static, không cần instance.

`MethodToolCallback` cần chuyển object kết quả thành chuỗi để gửi lại cho mô hình. Mặc định, `DefaultToolCallResultConverter` sử dụng Jackson để serialize kết quả.

Ví dụ kết quả:

~~~json
{
  "sku": "SKU-100",
  "warehouse": "HANOI",
  "availableQuantity": 18
}
~~~

Nếu ứng dụng cần định dạng kết quả khác, Spring AI cho phép cấu hình `ToolCallResultConverter` tùy chỉnh thông qua builder hoặc metadata tương ứng.

Cần giữ kết quả gọn và có ý nghĩa nghiệp vụ. Không trả về toàn bộ entity chứa thông tin nhạy cảm hoặc quan hệ dữ liệu không cần thiết. Chỉ trả về các trường mà mô hình cần để hoàn thành yêu cầu.

## 8. Các lỗi thường gặp trong quá trình chuyển đổi

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| JSON parse thất bại | Chuỗi arguments sai cú pháp hoặc không phải JSON object | Kiểm tra raw tool input, schema và model/provider |
| Không tìm thấy giá trị theo tên | JSON key khác tên tham số Java hoặc thiếu thông tin tên tham số trong bytecode | Bật `-parameters`, kiểm tra schema và chữ ký method |
| Sai kiểu dữ liệu | Gửi chuỗi thay cho số, object sai cấu trúc hoặc enum không hợp lệ | Sửa mô tả/schema và xác thực kiểu |
| Tham số bắt buộc bị thiếu | Mô hình bỏ qua key hoặc schema khai báo sai required | Khai báo required đúng và kiểm tra null trước khi dùng |
| Primitive nhận null | Tham số kiểu `int`, `boolean` không thể chứa null khi key bị bỏ qua | Dùng wrapper cho tham số có thể vắng mặt; giữ primitive cho giá trị bắt buộc |
| Method không thể được gọi | Sai target object, method không tương thích hoặc reflection không truy cập được | Kiểm tra `toolMethod`, `toolObject` và quyền truy cập |
| Method ném exception | Quy tắc nghiệp vụ hoặc hệ thống phụ trợ từ chối | Xử lý exception và trả lỗi đã làm sạch |

### 8.1. Thiếu tham số và primitive

Nếu một key không có trong JSON, giá trị tra cứu có thể là `null`. Kiểu wrapper như `Integer` và `Boolean` có thể biểu diễn null; kiểu nguyên thủy như `int` và `boolean` thì không.

Vì vậy, nếu tham số có thể bị bỏ qua, hãy dùng wrapper và đặt `required = false`:

Mặc định, Spring AI xem các tham số method là bắt buộc. Có thể khai báo tùy chọn bằng `@ToolParam(required = false)` hoặc `@Nullable`. Khai báo này ảnh hưởng input schema mà mô hình nhìn thấy; nó không thay thế việc xử lý giá trị thiếu trong method.

~~~java
public SearchResult search(
        String keyword,
        @ToolParam(
            description = "Trang kết quả, mặc định là trang 1",
            required = false
        )
        Integer page) {

    int safePage = page == null ? 1 : Math.max(page, 1);
    return searchService.search(keyword, safePage);
}
~~~

Đừng chỉ dựa vào schema để bảo đảm mô hình gửi đủ trường. Backend phải xử lý trường thiếu và giá trị ngoài phạm vi.

### 8.2. Xử lý exception

Khi method nghiệp vụ ném exception, lỗi từ lời gọi reflection có thể được Spring AI bọc trong `ToolExecutionException`. `ToolExecutionExceptionProcessor` quyết định đưa thông báo lỗi về cho mô hình để nó giải thích/thử bước khác hay ném lỗi lên caller.

Không nên để thông báo lỗi chứa SQL, stack trace, tên máy chủ, token hoặc dữ liệu nhạy cảm được gửi vào hội thoại. Hãy ánh xạ lỗi thành mã và thông báo an toàn. Với lỗi phân quyền, không cho phép mô hình thử lại bằng cách tự thay tenant hoặc user ID.

Nếu cần điều khiển cách xử lý lỗi, cấu hình `ToolExecutionExceptionProcessor` phù hợp với chính sách của ứng dụng. Các lỗi xác thực, lỗi nghiệp vụ và lỗi hạ tầng có thể cần cách phản hồi khác nhau.

## 9. Kiểm thử quá trình chuyển đổi JSON sang Java

Kiểm thử nên xác minh việc ánh xạ và thực thi, không chỉ xác minh JSON có cú pháp đúng.

| Trường hợp | Điều cần kiểm tra |
|---|---|
| Chuỗi hợp lệ | JSON key được ánh xạ đúng vào `String` |
| Số nguyên | Số JSON được chuyển thành kiểu số mong đợi |
| Enum hợp lệ | Giá trị được chuyển thành đúng enum constant |
| Enum không hợp lệ | Callback báo lỗi và không gọi service |
| Object lồng nhau | Record/POJO và các trường con được chuyển đổi đúng |
| List generic | Từng phần tử có đúng kiểu |
| JSON đảo thứ tự key | Vẫn ánh xạ đúng theo tên |
| Key bị thiếu | Wrapper nhận null và backend xử lý theo hợp đồng |
| ToolContext | Context được chèn riêng, không lấy từ JSON |
| Method ném lỗi | Lỗi được chuyển qua cơ chế exception processor |
| Result conversion | Kết quả method được serialize thành chuỗi mong muốn |

Ví dụ unit test callback trực tiếp:

~~~java
@Test
void mapsJsonArgumentsToMethodParameters() throws Exception {
    InventoryTools target = mock(InventoryTools.class);

    StockView expected = new StockView(
        "SKU-100",
        WarehouseCode.HANOI,
        18
    );

    when(target.lookupInventory(
            "SKU-100",
            WarehouseCode.HANOI,
            5
        ))
        .thenReturn(expected);

    Method method = InventoryTools.class.getMethod(
        "lookupInventory",
        String.class,
        WarehouseCode.class,
        Integer.class
    );

    ToolCallback callback = MethodToolCallback.builder()
        .toolDefinition(ToolDefinitions.builder(method)
            .description("Tra cứu tồn kho")
            .build())
        .toolMethod(method)
        .toolObject(target)
        .build();

    callback.call("""
        {
          "minimumQuantity": 5,
          "warehouse": "HANOI",
          "sku": "SKU-100"
        }
        """);

    verify(target).lookupInventory(
        "SKU-100",
        WarehouseCode.HANOI,
        5
    );
}
~~~

Ví dụ trên kiểm tra rằng thứ tự key JSON không ảnh hưởng kết quả ánh xạ. Khi viết test thực tế, cần dùng đúng method, target object và schema của dự án; nếu method cần `ToolContext`, hãy truyền context trong lời gọi `callback.call(json, toolContext)`.

Ngoài unit test callback, nên có integration test với `ChatClient` và model giả lập để xác minh tool definition được gửi đi, callback được chọn đúng, arguments được chuyển đổi và tool result được đưa trở lại hội thoại.

## 10. Giới hạn và lưu ý khi thiết kế method

`MethodToolCallback` dành cho các method đồng bộ có tham số và kết quả có thể biểu diễn bằng schema/JSON. Một số kiểu không được hỗ trợ làm tham số hoặc kiểu trả về của method tool, gồm:

- `Optional`: dùng `@Nullable` hoặc `@ToolParam(required = false)` thay thế.
- Kiểu bất đồng bộ như `CompletableFuture` hoặc `Future`.
- Kiểu reactive như `Mono`, `Flux` hoặc `Flow`.
- Kiểu functional như `Function`, `Supplier` hoặc `Consumer`.

Các kiểu này không có biểu diễn input/output phù hợp với hợp đồng JSON của method tool trong cơ chế này. Nếu cần xử lý bất đồng bộ hoặc reactive, hãy thiết kế adapter đồng bộ phù hợp hoặc dùng cơ chế tool callback chuyên biệt.

Nên giữ method tool mỏng: nhận đối số, xác thực, lấy context cần thiết và gọi service nghiệp vụ. Không đưa toàn bộ logic nghiệp vụ vào reflection callback. Điều đó giúp service vẫn kiểm thử được độc lập và có thể được tái sử dụng từ REST API, job hoặc luồng khác.

## Tài liệu tham khảo

- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): ToolCallback, MethodToolCallback, input schema, ToolContext, result conversion, giới hạn kiểu và xử lý exception.
- [Spring AI — MethodToolCallback API](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/tool/method/MethodToolCallback.html): builder và các phương thức call.
- [Java Reflection — Parameter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html): thông tin tên và kiểu của tham số được phản chiếu.
- [Java Compiler — -parameters](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): tùy chọn lưu tên tham số trong file class.

JSON arguments là hợp đồng dữ liệu đầu vào của tool. Khi tên thuộc tính, schema, kiểu Java và context được thống nhất, MethodToolCallback có thể chuyển dữ liệu thành lời gọi method có kiểm soát; ứng dụng vẫn phải xác thực và xử lý lỗi trước khi để thao tác nghiệp vụ tác động đến hệ thống.

