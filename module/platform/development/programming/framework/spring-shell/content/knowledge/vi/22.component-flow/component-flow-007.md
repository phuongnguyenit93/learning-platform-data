# ComponentFlowResult và chuyển dữ liệu về lớp nghiệp vụ

`ComponentFlow` gom nhiều bước nhập liệu thành một luồng tương tác. Sau khi người dùng hoàn tất các bước, `flow.run()` trả về `ComponentFlowResult`. Kết quả này cung cấp một `ComponentContext` để command lấy lại dữ liệu theo ID đã khai báo cho từng component.

Command nên làm nhiệm vụ điều phối: dựng flow, đọc kết quả, kiểm tra người dùng đã xác nhận và ánh xạ dữ liệu sang một request object. Service/use case nhận request object để kiểm tra quy tắc nghiệp vụ và thực hiện thao tác. Cách tổ chức này giữ phần giao diện terminal tách khỏi nghiệp vụ và giúp service có thể được gọi từ REST API, batch hoặc những đầu vào khác.

Bài học dùng API ComponentFlow của Spring Shell 3.1.x, với các ví dụ tương thích mô hình legacy `@ShellMethod`. Nội dung chính là cách đọc `ComponentFlowResult`, lấy dữ liệu đúng kiểu và chuyển dữ liệu về service.

## 1. Luồng dữ liệu từ terminal đến service

Một luồng tạo môi trường có thể hỏi tên môi trường, khu vực triển khai và xác nhận trước khi tạo:

~~~text
Người dùng
   |
   v
ComponentFlow
   |
   +--> StringInput: environmentName
   |
   +--> SingleItemSelector: region
   |
   +--> ConfirmationInput: confirm
   |
   v
flow.run()
   |
   v
ComponentFlowResult
   |
   v
result.getContext()
   |
   v
Command đọc giá trị theo ID
   |
   v
CreateEnvironmentRequest
   |
   v
EnvironmentService.create(request)
   |
   v
Domain / Repository
~~~

`ComponentFlow` quản lý tương tác và điều hướng giữa các component. `ComponentFlowResult` mang kết quả sau khi flow chạy xong. Command chuyển các giá trị đó thành dữ liệu đầu vào có ý nghĩa đối với nghiệp vụ rồi mới gọi service.

## 2. Khai báo ComponentFlow và ID của từng bước

Trong Spring Shell 3.1.x, có thể inject `ComponentFlow.Builder` từ Spring context. Nên clone và reset builder trước khi khai báo một flow mới:

~~~java
ComponentFlow flow = componentFlowBuilder.clone()
        .reset()
        .withStringInput("environmentName")
            .name("Tên môi trường")
            .defaultValue("staging")
            .and()
        .withSingleItemSelector("region")
            .name("Khu vực triển khai")
            .selectItems(regionOptions)
            .and()
        .withConfirmationInput("confirm")
            .name("Tạo môi trường với thông tin trên?")
            .and()
        .build();
~~~

Chuỗi truyền vào `withStringInput(...)`, `withSingleItemSelector(...)` hoặc `withConfirmationInput(...)` là ID của component. ID này vừa nhận diện bước trong flow, vừa là key mặc định để lưu kết quả vào `ComponentContext`.

Ví dụ:

| Khai báo | ID dùng để lấy kết quả |
|---|---|
| `withStringInput("environmentName")` | `"environmentName"` |
| `withSingleItemSelector("region")` | `"region"` |
| `withConfirmationInput("confirm")` | `"confirm"` |
| `withMultiItemSelector("roles")` | `"roles"` |

ID nên duy nhất trong một flow, ổn định và mô tả dữ liệu mà component thu thập. Không dùng nhãn hiển thị như `"Tên môi trường"` làm key nếu ID ngắn như `"environmentName"` đã đủ rõ.

`clone().reset()` tạo builder riêng từ cấu hình đã được inject rồi xóa các bước của flow trước. Cách này tránh để các lần gọi command nối thêm component vào cấu hình dùng chung.

## 3. Chạy flow và nhận ComponentFlowResult

`ComponentFlow.run()` trả về `ComponentFlow.ComponentFlowResult`. Gọi `getContext()` để lấy context chứa kết quả đã lưu:

~~~java
ComponentFlow.ComponentFlowResult result = flow.run();
ComponentContext<?> values = result.getContext();
~~~

`ComponentFlowResult` cung cấp `getContext()`; các component không trả về một request object nghiệp vụ hoàn chỉnh. `ComponentContext` là cấu trúc key/value, hỗ trợ:

- `get(key)`: lấy giá trị theo key.
- `get(key, Class<T>)`: lấy giá trị và ép về kiểu mong muốn.
- `containsKey(key)`: kiểm tra key có tồn tại.
- `put(key, value)`: thêm hoặc thay một giá trị trong context.
- `stream()`: duyệt các cặp key/value.

Ví dụ đọc ba kết quả:

~~~java
String environmentName =
        values.get("environmentName", String.class);
String regionCode =
        values.get("region", String.class);
Boolean confirmed =
        values.get("confirm", Boolean.class);
~~~

`get(key, Class<T>)` chỉ giúp lấy giá trị theo kiểu. Nó không thay thế kiểm tra dữ liệu hợp lệ. Giá trị có thể là `null` nếu component chưa chạy, key không được lưu hoặc kết quả rỗng; hãy kiểm tra trước khi tạo request.

## 4. Vì sao kết quả được lưu theo ID?

Các spec của ComponentFlow có `storeResult(boolean)`. Mặc định `storeResult(true)`, nghĩa là kết quả từ component được lưu vào `ComponentContext` bằng key là ID truyền vào builder.

Ví dụ:

~~~java
.withStringInput("environmentName")
    .name("Tên môi trường")
    .storeResult(true)
    .and()
~~~

Với cấu hình mặc định, có thể bỏ `.storeResult(true)`:

~~~java
.withStringInput("environmentName")
    .name("Tên môi trường")
    .and()
~~~

Nếu đặt `.storeResult(false)`, component vẫn chạy và tạo context riêng, nhưng flow không tự đưa kết quả đó vào context chung. Command không thể lấy kết quả này qua `result.getContext()`; nếu cần xử lý riêng, hãy dùng handler của component. Khi command cần đọc kết quả bằng `result.getContext().get("environmentName", String.class)`, hãy giữ `storeResult(true)`.

| Cấu hình | Kết quả |
|---|---|
| Không gọi `storeResult(...)` | Mặc định lưu kết quả vào context chung |
| `.storeResult(true)` | Lưu kết quả theo ID |
| `.storeResult(false)` | Không tự lưu kết quả theo ID |

Đừng nhầm ID component với tên property trong request object. Ví dụ `"environmentName"` là key giao tiếp giữa flow và command; sau khi đọc xong, command có thể ánh xạ nó sang `request.name()`.

## 5. Lấy kết quả có kiểm tra key và kiểu

Khi flow có điều hướng có điều kiện, không phải component nào cũng chắc chắn chạy. Hãy kiểm tra key trước khi đọc:

~~~java
ComponentContext<?> values = result.getContext();

if (!values.containsKey("environmentName")) {
    return "Chưa nhận được tên môi trường.";
}

String environmentName =
        values.get("environmentName", String.class);

if (environmentName == null || environmentName.isBlank()) {
    return "Tên môi trường không được để trống.";
}
~~~

Nên dùng hằng số cho ID nếu flow lớn hoặc được dùng ở nhiều vị trí:

~~~java
private static final String ENVIRONMENT_NAME = "environmentName";
private static final String REGION = "region";
private static final String CONFIRM = "confirm";
~~~

Hằng số giúp tránh lỗi gõ sai key giữa nơi khai báo và nơi đọc kết quả. Khi refactor một flow, có thể cập nhật ID tại một chỗ.

## 6. Ví dụ đầy đủ: lấy dữ liệu rồi gọi service

Giả sử command cần tạo môi trường triển khai. Flow hỏi tên, khu vực và xác nhận. Service chỉ được gọi khi người dùng chọn xác nhận.

### 6.1. Request object

Định nghĩa một request object thể hiện dữ liệu đầu vào của use case:

~~~java
public record CreateEnvironmentRequest(
        String name,
        String regionCode) {
}
~~~

Request object không cần phụ thuộc `ComponentFlow`, `ComponentContext` hoặc JLine. Nó chỉ chứa dữ liệu nghiệp vụ mà service cần.

### 6.2. Command tạo flow và ánh xạ dữ liệu

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.shell.component.context.ComponentContext;
import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class EnvironmentCommands {

    private static final String ENVIRONMENT_NAME = "environmentName";
    private static final String REGION = "region";
    private static final String CONFIRM = "confirm";

    private final ComponentFlow.Builder componentFlowBuilder;
    private final EnvironmentService environmentService;

    public EnvironmentCommands(
            ComponentFlow.Builder componentFlowBuilder,
            EnvironmentService environmentService) {
        this.componentFlowBuilder = componentFlowBuilder;
        this.environmentService = environmentService;
    }

    @ShellMethod(
            key = "environment create",
            value = "Tạo môi trường bằng các bước tương tác.")
    public String create() {

        Map<String, String> regionOptions = new LinkedHashMap<>();
        regionOptions.put("Việt Nam - Hà Nội", "VN-HAN");
        regionOptions.put("Việt Nam - Hồ Chí Minh", "VN-SGN");
        regionOptions.put("Singapore", "SG");

        ComponentFlow flow = componentFlowBuilder.clone()
                .reset()
                .withStringInput(ENVIRONMENT_NAME)
                    .name("Tên môi trường")
                    .defaultValue("staging")
                    .and()
                .withSingleItemSelector(REGION)
                    .name("Khu vực triển khai")
                    .selectItems(regionOptions)
                    .and()
                .withConfirmationInput(CONFIRM)
                    .name("Xác nhận tạo môi trường?")
                    .and()
                .build();

        ComponentFlow.ComponentFlowResult result = flow.run();
        ComponentContext<?> values = result.getContext();

        Boolean confirmed = values.get(CONFIRM, Boolean.class);
        if (!Boolean.TRUE.equals(confirmed)) {
            return "Đã hủy thao tác tạo môi trường.";
        }

        String name = values.get(ENVIRONMENT_NAME, String.class);
        String regionCode = values.get(REGION, String.class);

        if (name == null || name.isBlank()) {
            return "Tên môi trường không được để trống.";
        }
        if (regionCode == null || regionCode.isBlank()) {
            return "Bạn chưa chọn khu vực triển khai.";
        }

        CreateEnvironmentRequest request =
                new CreateEnvironmentRequest(name.trim(), regionCode);

        Environment created = environmentService.create(request);
        return "Đã tạo môi trường " + created.getName()
                + " tại khu vực " + created.getRegionCode() + ".";
    }
}
~~~

Trong ví dụ này, `regionOptions` là map có key để hiển thị và value là mã khu vực. Khi đọc key `"region"` từ context, command nhận giá trị đã chọn để đưa vào request. Nếu muốn xử lý đối tượng lựa chọn đầy đủ trong callback, có thể dùng `SingleItemSelectorContext.getResultItem()` hoặc `getValue()`.

### 6.3. Service nhận request và thực hiện nghiệp vụ

~~~java
import java.util.Set;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EnvironmentService {

    private final EnvironmentRepository environmentRepository;

    public EnvironmentService(EnvironmentRepository environmentRepository) {
        this.environmentRepository = environmentRepository;
    }

    @Transactional
    public Environment create(CreateEnvironmentRequest request) {
        if (request == null || request.name() == null || request.name().isBlank()) {
            throw new IllegalArgumentException(
                    "Tên môi trường không được để trống.");
        }
        String normalizedName = request.name().trim();

        if (request.regionCode() == null
                || !Set.of("VN-HAN", "VN-SGN", "SG").contains(request.regionCode())) {
            throw new IllegalArgumentException("Khu vực triển khai không hợp lệ.");
        }
        if (environmentRepository.existsByName(normalizedName)) {
            throw new IllegalStateException(
                    "Môi trường đã tồn tại: " + normalizedName);
        }

        Environment environment = new Environment(
                normalizedName, request.regionCode());
        return environmentRepository.save(environment);
    }
}
~~~

Ví dụ service còn kiểm tra tên trùng và ghi dữ liệu trong transaction. Những quy tắc này cần được bảo vệ ở service để các caller khác cũng nhận được cùng hành vi. Command chỉ thu thập input và chuyển nó thành request.

## 7. Kết quả của selector đơn và selector nhiều lựa chọn

### 7.1. SingleItemSelector

`withSingleItemSelector(id)` hiển thị danh sách để người dùng chọn một mục. Với `selectItems(Map<String, String>)`, key là nhãn hiển thị và value là giá trị được chọn:

~~~java
Map<String, String> options = new LinkedHashMap<>();
options.put("Quản trị viên", "ADMIN");
options.put("Người vận hành", "OPERATOR");
options.put("Người xem", "VIEWER");

ComponentFlow flow = componentFlowBuilder.clone().reset()
        .withSingleItemSelector("role")
            .name("Chọn vai trò")
            .selectItems(options)
            .and()
        .build();
~~~

Đọc kết quả đã lưu:

~~~java
ComponentContext<?> values = flow.run().getContext();
String roleCode = values.get("role", String.class);
~~~

Trong callback `next(...)`, context của selector có `getResultItem()` trả về `Optional` của item đã chọn. Ví dụ tài liệu Spring Shell dùng `ctx.getResultItem().get().getItem()` để lấy item và dùng giá trị đó làm ID bước tiếp theo. Hãy kiểm tra `Optional` trước khi gọi `get()` nếu lựa chọn có thể không tồn tại.

### 7.2. MultiItemSelector

`withMultiItemSelector(id)` cho phép chọn nhiều mục. Danh sách lựa chọn được cung cấp bằng `List<SelectItem>`:

~~~java
import java.util.List;
import org.springframework.shell.component.flow.SelectItem;

List<SelectItem> roleOptions = List.of(
        SelectItem.of("Quản trị viên", "ADMIN"),
        SelectItem.of("Người vận hành", "OPERATOR"),
        SelectItem.of("Người xem", "VIEWER"));

ComponentFlow flow = componentFlowBuilder.clone().reset()
        .withMultiItemSelector("roles")
            .name("Chọn các vai trò")
            .selectItems(roleOptions)
            .max(3)
            .and()
        .build();
~~~

Context của multi selector cung cấp `getResultValues()` để lấy danh sách giá trị đã chọn. Khi dùng flow storage, kết quả của component được lưu theo ID `"roles"` trong context chung:

~~~java
ComponentContext<?> values = flow.run().getContext();
List<?> selected = values.get("roles", List.class);
List<String> roleCodes = selected.stream()
        .map(String.class::cast)
        .toList();
~~~

Vì `List.class` không giữ được generic type lúc chạy, đoạn code chuyển từng phần tử về `String`. Sau đó có thể đưa `roleCodes` vào request object. Hãy xử lý trường hợp danh sách rỗng theo quy tắc nghiệp vụ của ứng dụng.

## 8. Dùng next để điều hướng có điều kiện

Thứ tự mặc định của các component là thứ tự khai báo trong builder. Có thể dùng `next(...)` để chọn component tiếp theo bằng cách trả về ID của nó. Nếu trả `null` hoặc một ID không tồn tại, flow dừng tại bước hiện tại.

Ví dụ, chỉ hỏi cấu hình nâng cao nếu người dùng xác nhận:

~~~java
ComponentFlow flow = componentFlowBuilder.clone().reset()
        .withConfirmationInput("advanced")
            .name("Bạn có muốn cấu hình nâng cao?")
            .next(context ->
                    Boolean.TRUE.equals(context.getResultValue())
                            ? "advancedOptions"
                            : "summary")
            .and()
        .withStringInput("advancedOptions")
            .name("Thông số nâng cao")
            .and()
        .withStringInput("summary")
            .name("Ghi chú cuối cùng")
            .and()
        .build();
~~~

`next(...)` chỉ điều khiển bước tương tác tiếp theo. Nó không tự quyết định nghiệp vụ có được phép thực hiện hay không. Sau `flow.run()`, command vẫn phải đọc kết quả xác nhận và áp dụng quy tắc trước khi gọi service.

Đặc biệt, flow dừng sớm không đồng nghĩa người dùng đã xác nhận thao tác nghiệp vụ. Hãy dùng một giá trị Boolean riêng như `"confirm"` nếu cần ghi nhận quyết định đó.

## 9. Xác nhận trước khi chuyển dữ liệu sang service

Với thao tác ghi dữ liệu hoặc có tác động khó đảo ngược, hãy thêm `ConfirmationInput` ở cuối flow và đặt mặc định là từ chối:

~~~java
.withConfirmationInput("confirm")
    .name("Xác nhận áp dụng cấu hình?")
    .defaultValue(false)
    .and()
~~~

Sau khi flow chạy:

~~~java
Boolean confirmed = result.getContext()
        .get("confirm", Boolean.class);

if (!Boolean.TRUE.equals(confirmed)) {
    return "Không thực hiện thay đổi.";
}

configurationService.apply(request);
~~~

Chỉ giá trị `Boolean.TRUE` mới cho phép gọi service. Nếu key không tồn tại hoặc giá trị là `null`, command dừng lại. Không coi việc flow kết thúc, thiếu input hoặc không có key là đồng ý.

## 10. Xử lý dữ liệu thiếu và validation

`ComponentFlow` thu thập dữ liệu tương tác; nó không thay thế validation nghiệp vụ. Sau khi đọc context:

1. Kiểm tra các key bắt buộc bằng `containsKey`.
2. Kiểm tra giá trị `null`, chuỗi rỗng và danh sách rỗng.
3. Chuẩn hóa dữ liệu ở ranh giới command nếu phù hợp, ví dụ trim khoảng trắng.
4. Tạo request object có kiểu dữ liệu rõ ràng.
5. Gọi service để kiểm tra quy tắc nghiệp vụ và trạng thái dữ liệu.

Ví dụ:

~~~java
import java.util.Set;

if (!values.containsKey("environmentName")
        || !values.containsKey("region")) {
    return "Thông tin tạo môi trường chưa đầy đủ.";
}

String name = values.get("environmentName", String.class);
String region = values.get("region", String.class);

if (name == null || name.isBlank()) {
    return "Tên môi trường không hợp lệ.";
}
if (!Set.of("VN-HAN", "VN-SGN", "SG").contains(region)) {
    return "Khu vực triển khai không hợp lệ.";
}
~~~

Kiểm tra ở command giúp thông báo sớm và dễ hiểu cho người dùng. Service vẫn phải xác thực dữ liệu vì caller khác có thể không đi qua ComponentFlow.

## 11. Không đặt nghiệp vụ vào callback của flow

Callback `next(...)`, `preHandler(...)` và `postHandler(...)` phục vụ điều hướng hoặc xử lý trạng thái của component. Không nên biến chúng thành nơi tạo bản ghi, gửi email hoặc gọi dịch vụ bên ngoài.

Ví dụ nên dùng callback để quyết định bước tiếp theo:

~~~java
.withConfirmationInput("includeDetails")
    .name("Có nhập thông tin chi tiết?")
    .next(context ->
            Boolean.TRUE.equals(context.getResultValue())
                    ? "details"
                    : "confirm")
    .and()
~~~

Sau khi flow hoàn tất, command gom dữ liệu thành request và gọi service một lần:

~~~java
CreateEnvironmentRequest request =
        new CreateEnvironmentRequest(name, regionCode);

environmentService.create(request);
~~~

Cách này giúp luồng UI dễ thay đổi mà không làm phân tán transaction hoặc quy tắc nghiệp vụ qua nhiều callback.

## 12. Dùng ComponentFlow.Builder trong Spring

Spring Shell Boot tự cấu hình `ComponentFlow.Builder` cho ứng dụng sử dụng các component tương tác. Có thể inject builder qua constructor:

~~~java
private final ComponentFlow.Builder componentFlowBuilder;

public EnvironmentCommands(
        ComponentFlow.Builder componentFlowBuilder) {
    this.componentFlowBuilder = componentFlowBuilder;
}
~~~

Builder có các phương thức cấu hình terminal, resource loader và template executor. Khi dùng builder do auto-configuration cung cấp, các thành phần này được cấu hình theo môi trường shell. Nếu tự tạo builder hoặc cấu hình flow độc lập, hãy cung cấp `Terminal`, `ResourceLoader` và `TemplateExecutor` phù hợp trước khi build.

API builder còn có `clone()`, `reset()` và `build()`:

| Phương thức | Mục đích |
|---|---|
| `clone()` | Tạo bản sao builder hiện tại |
| `reset()` | Xóa các bước đã khai báo trong builder |
| `withStringInput(id)` | Thêm bước nhập chuỗi |
| `withPathInput(id)` | Thêm bước nhập đường dẫn |
| `withConfirmationInput(id)` | Thêm bước xác nhận |
| `withSingleItemSelector(id)` | Thêm bước chọn một mục |
| `withMultiItemSelector(id)` | Thêm bước chọn nhiều mục |
| `build()` | Tạo ComponentFlow |

## 13. Kiểm thử việc chuyển dữ liệu về service

Nên kiểm tra cả dữ liệu được đọc từ context và hành vi của service:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Người dùng nhập tên và chọn khu vực hợp lệ | Request có đúng tên và mã khu vực |
| Người dùng xác nhận | Service được gọi với request đã tạo |
| Người dùng từ chối | Service không được gọi |
| Component bị bỏ qua bởi `next(...)` | Key của bước đó không được giả định là có dữ liệu |
| `storeResult(false)` | Key không tự xuất hiện trong context chung |
| Giá trị chuỗi rỗng | Command hoặc service từ chối theo validation |
| Selector không có lựa chọn | Command xử lý giá trị thiếu, không gọi service với dữ liệu rỗng |
| Multi selector không chọn mục nào | Request nhận danh sách rỗng hoặc command từ chối theo quy tắc |

Có thể tách phần ánh xạ context thành một phương thức thuần:

~~~java
CreateEnvironmentRequest toRequest(ComponentContext<?> values) {
    String name = values.get("environmentName", String.class);
    String region = values.get("region", String.class);

    if (name == null || name.isBlank()) {
        throw new IllegalArgumentException("Tên môi trường là bắt buộc.");
    }
    if (region == null || region.isBlank()) {
        throw new IllegalArgumentException("Khu vực là bắt buộc.");
    }

    return new CreateEnvironmentRequest(name.trim(), region);
}
~~~

Unit test cho phương thức này không cần terminal. Integration test cho command kiểm tra flow được chạy, dữ liệu được lấy đúng key và service chỉ được gọi khi xác nhận hợp lệ.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `getContext().get("name")` trả `null` | ID trong builder khác key lúc đọc hoặc `storeResult(false)` | Dùng cùng ID và giữ `storeResult(true)` |
| Không thấy dữ liệu của bước cuối | Flow dừng trước bước đó theo `next(...)` | Kiểm tra nhánh điều hướng và `containsKey` |
| Lấy sai kiểu dữ liệu | Đọc selector hoặc confirmation như `String` | Dùng đúng kiểu đã lưu, ví dụ `Boolean.class` hoặc `String.class` |
| Dữ liệu hiển thị khác giá trị service nhận | Nhầm nhãn hiển thị với item/value của selector | Dùng giá trị được chọn từ context, không tự suy ra từ label |
| Mỗi lần chạy command lại xuất hiện thêm bước cũ | Tái sử dụng builder mà không clone/reset | Dùng `componentFlowBuilder.clone().reset()` |
| Service được gọi dù người dùng từ chối | Chỉ kiểm tra flow đã chạy xong, không kiểm tra Boolean | Chỉ gọi service khi `Boolean.TRUE.equals(confirmed)` |
| Validation chỉ nằm trong command | Caller khác bỏ qua ComponentFlow | Đưa quy tắc nghiệp vụ vào service/domain |
| Callback gây side effect nhiều lần | Đặt ghi dữ liệu trong `next` hoặc handler | Giữ callback cho điều hướng; gọi service sau `run()` |
| Flow chờ input trong script tự động | Dùng component tương tác ở chế độ không có terminal input | Dùng command options cho non-interactive hoặc batch |

## 15. Quy trình triển khai

1. Xác định các trường dữ liệu cần thu thập và component phù hợp cho từng trường.
2. Chọn ID duy nhất cho từng bước; dùng cùng ID khi lấy dữ liệu.
3. Clone và reset `ComponentFlow.Builder`, sau đó khai báo các component theo thứ tự.
4. Dùng `next(...)` nếu cần rẽ nhánh; trả `null` để kết thúc flow khi phù hợp.
5. Chạy `flow.run()` và lấy `ComponentFlowResult.getContext()`.
6. Kiểm tra key, lấy dữ liệu bằng `get(key, Class<T>)` và xử lý giá trị thiếu.
7. Kiểm tra xác nhận trước mọi thao tác có side effect.
8. Ánh xạ giá trị thành request object độc lập với Spring Shell.
9. Gọi service để validation, áp dụng quy tắc nghiệp vụ và thực hiện transaction.
10. Kiểm thử các nhánh hoàn tất, từ chối, thiếu dữ liệu và flow dừng sớm.

## 16. Tổng kết

`ComponentFlow.run()` trả về `ComponentFlowResult`; gọi `getContext()` để lấy `ComponentContext` chứa kết quả theo ID của từng component. Các spec lưu kết quả vào context chung theo ID mặc định, trừ khi cấu hình `storeResult(false)`. Dùng `containsKey` và `get(key, Class<T>)` để kiểm tra và đọc giá trị có kiểu rõ ràng.

Sau khi đọc kết quả, command nên kiểm tra dữ liệu, xác nhận người dùng và ánh xạ các giá trị vào request object. Service nhận request để kiểm tra quy tắc nghiệp vụ và thực hiện thao tác. Giữ callback của flow cho việc điều hướng, không đặt side effect nghiệp vụ vào đó. Cách phân chia này giúp ComponentFlow tập trung vào tương tác terminal, còn lớp nghiệp vụ độc lập với giao diện nhập liệu.

## Tài liệu tham khảo

- [Spring Shell 3.1.6 Reference Documentation — Flow](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html) — mục 8.1 Flow, thứ tự component, điều hướng bằng `next` và `ComponentFlowResult`.
- [ComponentFlow API 3.1.x](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/component/flow/ComponentFlow.html) — `builder()` và `run()`.
- [ComponentFlowResult API 3.1.x](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/component/flow/ComponentFlow.ComponentFlowResult.html) — `getContext()`.
- [ComponentContext API 3.1.x](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/component/context/ComponentContext.html) — `get`, `containsKey`, `put`, `stream` và `toTemplateModel`.
- [ComponentFlow.Builder API 3.1.x](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/component/flow/ComponentFlow.Builder.html) — clone, reset, các bước input và build.
- [StringInputSpec API 3.1.x](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/component/flow/StringInputSpec.html) — `defaultValue`, `storeResult` và `next`.
- [SingleItemSelectorSpec API 3.1.x](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/component/flow/SingleItemSelectorSpec.html) — danh sách lựa chọn, `storeResult` và điều hướng.
- [MultiItemSelectorSpec API 3.1.x](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/component/flow/MultiItemSelectorSpec.html) — danh sách nhiều lựa chọn, giới hạn số mục và kết quả.
- [ConfirmationInputSpec API 3.1.x](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/component/flow/ConfirmationInputSpec.html) — giá trị mặc định, `storeResult` và điều hướng sau xác nhận.
