# Rẽ nhánh theo dữ liệu đã nhập bằng hàm next

Một wizard thường có những bước chỉ cần hỏi trong một số trường hợp. Ví dụ, khi tạo hồ sơ khách hàng, người dùng chọn loại khách hàng là cá nhân hoặc doanh nghiệp. Hồ sơ cá nhân cần thông tin ngày sinh; hồ sơ doanh nghiệp cần mã số thuế. Sau hai nhánh, cả hai đều đi đến bước xác nhận chung.

`ComponentFlow` của Spring Shell 3.x hỗ trợ cách tổ chức này bằng hàm `next`. Mỗi component có thể quyết định component tiếp theo dựa trên dữ liệu vừa nhập. Nhờ vậy, luồng hỏi đáp có thể bỏ qua các bước không liên quan, đi theo nhiều nhánh và hội tụ về một bước dùng chung.

## 1. Luồng mặc định và luồng có điều kiện

Nếu không cấu hình `next`, `ComponentFlow` chạy các component theo thứ tự khai báo trong builder. Ví dụ:

~~~java
ComponentFlow flow = componentFlowBuilder.clone().reset()
        .withStringInput("name")
            .name("Tên")
            .and()
        .withStringInput("email")
            .name("Email")
            .and()
        .withConfirmationInput("confirm")
            .name("Xác nhận")
            .and()
        .build();
~~~

Thứ tự chạy là `name` → `email` → `confirm`. Đây là dạng flow tuyến tính, phù hợp khi mọi người dùng đều phải trả lời cùng một tập câu hỏi.

Khi một component cần quyết định bước kế tiếp, thêm `next(Function<Context, String>)` vào spec:

~~~java
.withStringInput("accountType")
    .name("Loại tài khoản")
    .next(context -> {
        String value = context.getResultValue();
        return "business".equalsIgnoreCase(value)
                ? "businessDetails"
                : "personalDetails";
    })
    .and()
~~~

Hàm nhận context của component vừa hoàn tất và trả về ID của component tiếp theo. ID đó chính là chuỗi đã truyền vào `withStringInput(id)`, `withPathInput(id)`, `withSingleItemSelector(id)` hoặc phương thức `with...` tương ứng.

## 2. Quy tắc của hàm next

`next` có cùng ý nghĩa ở các spec của `StringInput`, `PathInput`, `ConfirmationInput`, `SingleItemSelector` và `MultiItemSelector`. Kiểu context của tham số thay đổi theo component, còn giá trị trả về luôn là `String`.

| Kết quả của next | Hành vi |
|---|---|
| Trả về ID của component đã khai báo | Flow chuyển đến component có ID đó |
| Trả về `null` | Flow dừng tại bước hiện tại |
| Trả về ID không tồn tại | Flow cũng dừng tại bước hiện tại |
| Không cấu hình `next` | Flow tiếp tục theo thứ tự builder đã khai báo |

Điểm cần nhớ:

- ID phải khớp chính xác với ID dùng trong `with...`.
- Component đích phải được khai báo trong cùng builder.
- `next` ghi đè thứ tự tuần tự mặc định cho bước hiện tại.
- Nếu muốn hai nhánh hội tụ, mỗi component cuối nhánh phải trả về cùng một ID.
- Không dùng ID sai chính tả để biểu diễn lỗi nghiệp vụ: ID không tồn tại làm flow dừng, không hiển thị một thông báo lỗi tự động.

## 3. Rẽ nhánh trực tiếp từ SingleItemSelector

Khi người dùng chọn một mục từ danh sách, giá trị của mục được chọn có thể chính là ID của nhánh tiếp theo. Đây là cách gọn để tránh phải phân tích chuỗi tự do.

Ví dụ, map của `selectItems` nhận cặp `tên hiển thị → giá trị item`:

~~~java
Map<String, String> routes = new LinkedHashMap<>();
routes.put("Khách hàng cá nhân", "personalDetails");
routes.put("Khách hàng doanh nghiệp", "businessDetails");
~~~

Trong `next`, đọc item đã chọn qua `getResultItem()`:

~~~java
.withSingleItemSelector("customerType")
    .name("Loại khách hàng")
    .selectItems(routes)
    .next(context -> context.getResultItem()
            .map(item -> item.getItem())
            .orElse(null))
    .and()
~~~

Nếu người dùng chọn “Khách hàng cá nhân”, selector trả item `personalDetails` và flow chuyển đến component có ID đó. Nếu chọn “Khách hàng doanh nghiệp”, flow chuyển đến `businessDetails`.

Mẫu này phù hợp khi số nhánh là hữu hạn và mỗi lựa chọn có thể được xác định trước. Tên hiển thị có thể thay đổi theo ngôn ngữ, còn item nên giữ ID ổn định để điều hướng.

## 4. Ví dụ hoàn chỉnh: hai nhánh và một bước xác nhận chung

Ví dụ sau tạo wizard đăng ký khách hàng. Người dùng chọn loại hồ sơ, nhập dữ liệu riêng của nhánh tương ứng rồi đi đến bước xác nhận.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.stereotype.Component;

@Component
class CustomerRegistrationFlow {

    private final ComponentFlow.Builder componentFlowBuilder;

    CustomerRegistrationFlow(ComponentFlow.Builder componentFlowBuilder) {
        this.componentFlowBuilder = componentFlowBuilder;
    }

    public void run() {
        Map<String, String> routes = new LinkedHashMap<>();
        routes.put("Khách hàng cá nhân", "personalDetails");
        routes.put("Khách hàng doanh nghiệp", "businessDetails");

        ComponentFlow flow = componentFlowBuilder.clone().reset()
                .withSingleItemSelector("customerType")
                    .name("Loại khách hàng")
                    .selectItems(routes)
                    .next(context -> context.getResultItem()
                            .map(item -> item.getItem())
                            .orElse(null))
                    .and()
                .withStringInput("personalDetails")
                    .name("Họ tên và ngày sinh")
                    .next(context -> "review")
                    .and()
                .withStringInput("businessDetails")
                    .name("Tên doanh nghiệp và mã số thuế")
                    .next(context -> "review")
                    .and()
                .withConfirmationInput("review")
                    .name("Xác nhận tạo hồ sơ")
                    .defaultValue(false)
                    .next(context -> null)
                    .and()
                .build();

        ComponentFlow.ComponentFlowResult result = flow.run();

        String selectedRoute =
                result.getContext().get("customerType", String.class);
        String personalDetails =
                result.getContext().get("personalDetails", String.class);
        String businessDetails =
                result.getContext().get("businessDetails", String.class);
        Boolean confirmed =
                result.getContext().get("review", Boolean.class);

        if (Boolean.TRUE.equals(confirmed)) {
            if ("personalDetails".equals(selectedRoute)) {
                // Lưu hồ sơ cá nhân bằng personalDetails.
            }
            else if ("businessDetails".equals(selectedRoute)) {
                // Lưu hồ sơ doanh nghiệp bằng businessDetails.
            }
        }
    }
}
~~~

Luồng thực tế:

~~~text
customerType
    ├── personalDetails ──┐
    └── businessDetails ──┴──> review ──> stop
~~~

Giải thích các điểm điều hướng:

1. `customerType` trả về `personalDetails` hoặc `businessDetails` dựa trên item người dùng chọn.
2. Chỉ component của nhánh được chọn chạy; component còn lại bị bỏ qua.
3. Cả hai component chi tiết đều trả về `review`, nên hai nhánh hội tụ tại cùng một bước.
4. `review` trả về `null` sau khi người dùng xác nhận, vì vậy flow kết thúc.

Trong ví dụ, các component được khai báo theo thứ tự `customerType`, `personalDetails`, `businessDetails`, `review`. Nếu bỏ hai hàm `next` ở các bước chi tiết, flow sẽ tiếp tục theo thứ tự builder và có thể chạy cả hai nhánh. Vì vậy, hãy khai báo rõ đích hội tụ ở cuối mỗi nhánh.

## 5. Rẽ nhánh bằng dữ liệu StringInput

Không phải lúc nào dữ liệu đầu vào cũng đến từ selector. Với `StringInput`, hàm `next` có thể đọc chuỗi người dùng nhập và chọn nhánh bằng điều kiện:

~~~java
private static String routeEnvironment(String value) {
    if ("prod".equalsIgnoreCase(value)) {
        return "productionSettings";
    }
    if ("dev".equalsIgnoreCase(value)) {
        return "developmentSettings";
    }
    return "invalidEnvironment";
}

// Trong builder:
.withStringInput("environment")
    .name("Môi trường triển khai (dev/prod)")
    .next(context -> routeEnvironment(context.getResultValue()))
    .and()
~~~

Các ID `productionSettings`, `developmentSettings` và `invalidEnvironment` phải được khai báo trong cùng builder. Nhánh `invalidEnvironment` nên là bước xử lý lỗi hoặc hủy riêng, ví dụ hiển thị hướng dẫn rồi kết thúc flow. Không trả về một ID chưa khai báo để thay cho thông báo lỗi.

Vì `StringInput` nhận chuỗi tự do, cần xử lý trường hợp ngoài tập giá trị mong đợi. Khi lựa chọn thuộc một tập giá trị cố định, `SingleItemSelector` thường an toàn và dễ dùng hơn chuỗi tự do vì người dùng chỉ có thể chọn các mục đã khai báo.

## 6. Rẽ nhánh theo câu trả lời xác nhận

`ConfirmationInput` trả về `Boolean`. Có thể dùng kết quả để quyết định đi tiếp hay chuyển sang nhánh hủy:

~~~java
.withConfirmationInput("confirmDelete")
    .name("Bạn có chắc chắn muốn xóa dữ liệu?")
    .defaultValue(false)
    .next(context -> Boolean.TRUE.equals(context.getResultValue())
            ? "performDelete"
            : "cancelDelete")
    .and()
~~~

Hãy khai báo hai ID đích `performDelete` và `cancelDelete` bằng các component phù hợp với quy trình của ứng dụng. Giá trị mặc định `false` giúp tránh xác nhận nhầm khi người dùng chỉ nhấn Enter. Sau khi flow kết thúc, đọc kết quả `confirmDelete` rồi mới gọi service xóa nếu giá trị là `true`. Lambda `next` chỉ quyết định điều hướng; không đặt thao tác xóa dữ liệu bên trong hàm này.

## 7. Lưu và đọc kết quả của các nhánh

Mỗi component có context riêng. Khi flow kết thúc, `ComponentFlow.run()` trả về `ComponentFlowResult`; gọi `getContext()` để lấy context chung của flow:

~~~java
ComponentFlow.ComponentFlowResult result = flow.run();

String customerType =
        result.getContext().get("customerType", String.class);
String email =
        result.getContext().get("email", String.class);
Boolean confirmed =
        result.getContext().get("confirm", Boolean.class);
~~~

`storeResult` trên các spec mặc định là `true`. Khi bật, kết quả của component được lưu vào context chung theo ID truyền cho `with...`. Có thể tắt lưu cho một component bằng `storeResult(false)` nếu kết quả chỉ được dùng trong hàm `next` hoặc handler và không cần đọc sau khi flow kết thúc.

Ví dụ:

~~~java
.withStringInput("temporaryCode")
    .name("Mã xác minh tạm thời")
    .storeResult(false)
    .next(context -> "confirmCode")
    .and()
~~~

Khi cần đọc kết quả sau flow, giữ `storeResult` bật. Nên dùng `get(id, Type.class)` để đọc theo kiểu rõ ràng và tránh ép kiểu thủ công.

## 8. Phân biệt next, preHandler và postHandler

Ba API có mục đích khác nhau:

| API | Thời điểm | Mục đích |
|---|---|---|
| `preHandler(...)` | Trước khi component chạy | Chuẩn bị context, giá trị mặc định hoặc thông báo |
| `postHandler(...)` | Sau khi component chạy | Xử lý kết quả vừa nhập hoặc cập nhật dữ liệu liên quan |
| `next(...)` | Sau khi component hoàn tất | Chọn ID component tiếp theo hoặc dừng flow |

`preHandler` và `postHandler` không thay thế điều hướng. Nếu chỉ cần ghi log, chuẩn hóa hoặc kiểm tra kết quả, handler phù hợp hơn. Nếu cần bỏ qua một số bước hoặc chuyển sang nhánh khác, dùng `next`.

Ví dụ gắn handler và điều hướng:

~~~java
.withStringInput("email")
    .name("Email")
    .postHandler(context -> {
        // Ghi nhận hoặc chuẩn hóa kết quả sau khi nhập.
    })
    .next(context -> "review")
    .and()
~~~

## 9. Dùng clone và reset khi tạo flow

Trong ứng dụng Spring, `ComponentFlow.Builder` thường được inject thành bean. Khi tạo một flow mới, nên dùng `clone().reset()` để bắt đầu từ builder sạch:

~~~java
ComponentFlow flow = componentFlowBuilder.clone()
        .reset()
        .withStringInput("name")
            .name("Tên")
            .and()
        .build();
~~~

`clone()` tạo bản sao builder, còn `reset()` xóa các bước đã cấu hình trên bản sao đó. Điều này giúp nhiều lần chạy wizard không vô tình dùng lại các bước của flow trước.

ID component nên duy nhất trong một flow. Nếu hai component dùng chung ID, kết quả lưu trong context có thể ghi đè nhau và việc điều hướng trở nên khó hiểu.

## 10. Cách thiết kế nhánh dễ bảo trì

Khi flow có nhiều nhánh, hãy thiết kế như một đồ thị điều hướng:

- Mỗi component có một ID rõ ràng, phản ánh dữ liệu hoặc nhiệm vụ của bước đó.
- Mỗi giá trị trả về từ `next` phải trỏ đến một ID đã khai báo.
- Đặt các component dùng chung ở cuối các nhánh và cho từng nhánh điều hướng đến đó.
- Dùng selector cho lựa chọn hữu hạn; dùng string input khi cần dữ liệu tự do.
- Tạo một nhánh xử lý riêng cho dữ liệu không hợp lệ thay vì trả một ID không tồn tại.
- Chỉ trả `null` khi muốn kết thúc wizard.
- Không đặt logic nghiệp vụ lớn bên trong lambda `next`; tách hàm định tuyến thành method riêng khi điều kiện phức tạp.

Với nhiều nhánh lồng nhau, nên vẽ sơ đồ trước khi viết builder. Một flow dễ đọc thường có bước lựa chọn, các nhánh ngắn và một hoặc vài bước hội tụ.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Flow dừng ngay sau lựa chọn | `next` trả về `null` | Kiểm tra giá trị trả về và nhánh mong muốn |
| Component kế tiếp không chạy | ID trả về không trùng ID khai báo | So sánh chuỗi trả về với tham số `with...` |
| Nhánh cá nhân vẫn chạy cả bước doanh nghiệp | Bước chi tiết không khai báo `next` hội tụ | Trả về ID bước chung từ cuối mỗi nhánh |
| Bước chung không được gọi | Nhánh trả về ID sai hoặc không khai báo | Khai báo component đích và dùng đúng ID |
| Flow bỏ qua phần xử lý cuối | Một component trả về `null` quá sớm | Chỉ trả `null` tại điểm kết thúc thực sự |
| Kết quả sau flow là `null` | `storeResult(false)` hoặc ID đọc không đúng | Bật lưu kết quả và dùng đúng ID component |
| Rẽ nhánh sai khi người dùng nhập chữ hoa/thường | So sánh chuỗi phân biệt hoa thường | Chuẩn hóa chuỗi hoặc dùng `equalsIgnoreCase` |
| Giá trị nhập tự do tạo ra nhánh không xác định | Không có nhánh mặc định | Kiểm tra dữ liệu và định nghĩa nhánh lỗi |
| Nhiều flow dùng lẫn cấu hình | Dùng lại builder đã được cấu hình trước | Tạo bản sao bằng `clone().reset()` |
| Hai component ghi đè kết quả | Trùng ID | Đặt ID duy nhất trong cùng flow |

## 12. Kiểm thử luồng rẽ nhánh

Nên kiểm tra từng đường đi có thể xảy ra, không chỉ chạy thử nhánh mặc định:

| Dữ liệu đầu vào | Đường đi mong đợi |
|---|---|
| Chọn khách hàng cá nhân | `customerType → personalDetails → review` |
| Chọn khách hàng doanh nghiệp | `customerType → businessDetails → review` |
| Xác nhận `true` | Tiếp tục nhánh đã xác nhận |
| Xác nhận `false` | Đi đến nhánh hủy hoặc kết thúc |
| Giá trị StringInput là `dev` | `developmentSettings` |
| Giá trị StringInput là `prod` | `productionSettings` |
| Giá trị không hợp lệ | `invalidEnvironment` |
| Hàm `next` trả `null` | Flow dừng |
| Hàm `next` trả ID không tồn tại | Flow dừng; cần sửa ID sai |

Nếu lambda chứa logic định tuyến, tách phần quyết định thành method thuần để có thể unit test độc lập:

~~~java
static String routeEnvironment(String value) {
    if ("dev".equalsIgnoreCase(value)) {
        return "developmentSettings";
    }
    if ("prod".equalsIgnoreCase(value)) {
        return "productionSettings";
    }
    return "invalidEnvironment";
}
~~~

Sau đó dùng lại method trong `next`:

~~~java
.next(context -> routeEnvironment(context.getResultValue()))
~~~

Unit test cho `routeEnvironment` xác nhận quy tắc định tuyến. Integration test hoặc kiểm thử tương tác trong terminal xác nhận các component thực sự chạy theo đúng thứ tự và kết quả được lưu đúng ID.

## 13. Bài tập thực hành

Tạo wizard triển khai ứng dụng với yêu cầu:

1. Chọn môi trường: development, staging hoặc production.
2. Nếu chọn development, hỏi có bật debug hay không.
3. Nếu chọn staging, hỏi URL kiểm thử.
4. Nếu chọn production, hỏi người phê duyệt và yêu cầu xác nhận trước khi tiếp tục.
5. Cả ba nhánh hội tụ về bước xem lại cấu hình.
6. Người dùng xác nhận thì đi đến bước hoàn tất; từ chối thì đi đến bước hủy.

Gợi ý ID:

| Component ID | Vai trò |
|---|---|
| `environment` | Chọn môi trường |
| `developmentSettings` | Cấu hình development |
| `stagingSettings` | Cấu hình staging |
| `productionSettings` | Cấu hình production |
| `review` | Xem lại cấu hình |
| `confirm` | Xác nhận triển khai |
| `completed` | Hoàn tất |
| `cancelled` | Hủy triển khai |

Sau khi hoàn thành, kiểm thử cả ba nhánh, trường hợp từ chối xác nhận, kết quả sau flow và tình huống trả về ID không tồn tại.

## Tài liệu tham khảo

- [Spring Shell 3.4.3 – Flow](https://docs.spring.io/spring-shell/reference/3.4/components/flow/index.html)
- [Spring Shell 3.4.3 – Flow Components](https://docs.spring.io/spring-shell/reference/3.4/components/ui/)
- [Spring Shell 3.4.3 API – ComponentFlow.Builder](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/ComponentFlow.Builder.html)
- [Spring Shell 3.4.3 API – StringInputSpec](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/StringInputSpec.html)
- [Spring Shell 3.4.3 API – SingleItemSelectorSpec](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/SingleItemSelectorSpec.html)
- [Spring Shell 3.4.3 API – ConfirmationInputSpec](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/ConfirmationInputSpec.html)
- [Spring Shell 3.4.3 API – ComponentFlow.ComponentFlowResult](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/ComponentFlow.ComponentFlowResult.html)
- [Spring Shell 3.4.3 API – ComponentContext](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/context/ComponentContext.html)
