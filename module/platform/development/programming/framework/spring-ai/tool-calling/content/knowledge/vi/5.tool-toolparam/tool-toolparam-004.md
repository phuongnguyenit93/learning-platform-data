# Tham số bắt buộc, tùy chọn và giá trị có thể null

Khi mô hình gọi một tool trong Spring AI, nó gửi các đối số theo schema đầu vào mà ứng dụng cung cấp. Schema cần mô tả rõ tham số nào bắt buộc phải có, tham số nào được phép bỏ qua và giá trị `null` có ý nghĩa gì. Nếu ba khái niệm này bị nhập làm một, ứng dụng có thể hiểu sai yêu cầu, áp dụng mặc định không mong muốn hoặc thực hiện một thao tác cập nhật sai dữ liệu.

Trong Spring AI, `@Tool` khai báo phương thức mà mô hình có thể yêu cầu thực thi; `@ToolParam` mô tả từng tham số, trong đó thuộc tính `required` xác định tham số có bắt buộc xuất hiện trong đầu vào hay không. `required` mặc định là `true`. Khi đặt `required = false`, mô hình có thể bỏ qua thuộc tính đó trong lời gọi tool. Ứng dụng vẫn phải quyết định giá trị bị bỏ qua có ý nghĩa gì và kiểm tra dữ liệu ở thời điểm thực thi.

## 1. Phân biệt ba khái niệm

Ba khái niệm thường gặp có ý nghĩa khác nhau:

| Khái niệm | Ý nghĩa trong đầu vào | Ví dụ |
| --- | --- | --- |
| Bắt buộc (required) | Thuộc tính phải xuất hiện và phải thỏa điều kiện dữ liệu của nghiệp vụ | `customerId` phải có để tìm đơn hàng của khách hàng |
| Tùy chọn (optional) | Thuộc tính có thể không xuất hiện; ứng dụng quy định cách xử lý khi bị bỏ qua | `limit` có thể bỏ qua để dùng giới hạn mặc định |
| Có thể null (nullable) | Thuộc tính có thể xuất hiện với giá trị JSON `null`; ứng dụng quy định ý nghĩa của giá trị này | `deliveryNote: null` có thể biểu thị yêu cầu xóa ghi chú |

Trong JSON, bỏ qua một thuộc tính và truyền thuộc tính với giá trị `null` là hai biểu diễn khác nhau:

```json
{
  "customerId": "C-100"
}
```

```json
{
  "customerId": "C-100",
  "deliveryNote": null
}
```

Ở ví dụ thứ nhất, `deliveryNote` không được gửi. Ở ví dụ thứ hai, thuộc tính được gửi và giá trị của nó là `null`. Với một API cập nhật, ứng dụng có thể quy ước bỏ qua nghĩa là giữ nguyên ghi chú cũ, còn `null` nghĩa là xóa ghi chú. Với một API tìm kiếm, cả hai trường hợp có thể cùng được hiểu là không lọc theo ghi chú. Ý nghĩa phải được định nghĩa theo nghiệp vụ, không thể suy ra chỉ từ kiểu Java.

Một tham số tùy chọn không mặc nhiên là nullable. Ngược lại, một tham số nullable cũng không nhất thiết được phép bỏ qua. Có thể thiết kế tham số bắt buộc nhưng cho phép `null`, hoặc tham số tùy chọn chỉ chấp nhận giá trị cụ thể khi xuất hiện.

## 2. Schema JSON mô tả sự hiện diện và kiểu giá trị

Trong JSON Schema, danh sách `required` mô tả những thuộc tính phải có mặt trong object. Kiểu dữ liệu của thuộc tính mô tả những giá trị được chấp nhận. Hai phần này độc lập.

Ví dụ schema khái niệm cho một tool tìm kiếm đơn hàng:

```json
{
  "type": "object",
  "properties": {
    "customerId": {
      "type": "string",
      "description": "Mã khách hàng cần tra cứu"
    },
    "status": {
      "type": "string",
      "description": "Trạng thái đơn hàng cần lọc; có thể bỏ qua"
    },
    "limit": {
      "type": "integer",
      "description": "Số kết quả tối đa"
    }
  },
  "required": ["customerId"]
}
```

Trong schema này, `customerId` bắt buộc; `status` và `limit` có thể bị bỏ qua. Vì `status` có kiểu `string`, schema không khẳng định rằng JSON `null` là hợp lệ. Nếu muốn chấp nhận cả chuỗi và `null`, schema theo kiểu JSON Schema có thể mô tả union như sau:

```json
{
  "type": "object",
  "properties": {
    "deliveryNote": {
      "anyOf": [
        { "type": "string" },
        { "type": "null" }
      ]
    }
  },
  "required": []
}
```

Đây là ví dụ minh họa sự khác nhau về mặt schema, không phải cam kết rằng mọi model provider hoặc mọi chế độ structured output đều chấp nhận đúng cấu trúc này. Các provider có thể dùng dialect hoặc ràng buộc schema khác nhau; một số chế độ strict yêu cầu quy tắc đặc biệt đối với thuộc tính tùy chọn. Cần kiểm tra schema thực tế được gửi đến provider và khả năng hỗ trợ của model đang dùng.

Trong Spring AI, có thể đánh dấu một tham số không bắt buộc bằng `@ToolParam(required = false)`. Thuộc tính này điều khiển yêu cầu về sự hiện diện của tham số trong schema được tạo. Nó không tự định nghĩa giá trị mặc định cho nghiệp vụ và cũng không đảm bảo model sẽ gửi JSON `null` khi không có thông tin. Nếu nghiệp vụ cần phân biệt bỏ qua với `null`, phải thiết kế và kiểm tra biểu diễn đầu vào một cách rõ ràng.

## 3. Khai báo tham số bắt buộc và tùy chọn bằng `@ToolParam`

Ví dụ dưới đây cung cấp tool tìm kiếm đơn hàng. `customerId` là bắt buộc; `status` và `limit` là tùy chọn. Khi người gọi bỏ qua `status`, ứng dụng không lọc theo trạng thái. Khi bỏ qua `limit`, ứng dụng dùng giới hạn mặc định 20 kết quả.

```java
import java.util.List;
import java.util.Locale;

import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;

@Component
class OrderSearchTools {

    private final OrderQueryService orderQueryService;

    OrderSearchTools(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @Tool(description = "Tìm các đơn hàng của một khách hàng theo trạng thái tùy chọn")
    List<OrderSummary> searchOrders(
            @ToolParam(description = "Mã khách hàng cần tra cứu")
            String customerId,

            @ToolParam(
                    description = "Trạng thái cần lọc, ví dụ PENDING hoặc SHIPPED; bỏ qua để lấy mọi trạng thái",
                    required = false)
            String status,

            @ToolParam(
                    description = "Số kết quả tối đa; bỏ qua để dùng mặc định 20",
                    required = false)
            Integer limit,

            ToolContext toolContext) {

        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId là bắt buộc");
        }

        Object principalValue = toolContext.getContext().get("principalId");
        if (!(principalValue instanceof String principalId) || principalId.isBlank()) {
            throw new IllegalStateException("Thiếu principal đã xác thực trong ToolContext");
        }

        int effectiveLimit = limit == null ? 20 : limit;
        if (effectiveLimit < 1 || effectiveLimit > 100) {
            throw new IllegalArgumentException("limit phải nằm trong khoảng 1 đến 100");
        }

        String normalizedStatus = normalizeStatus(status);
        return orderQueryService.searchForPrincipal(
                principalId, customerId, normalizedStatus, effectiveLimit);
    }

    private String normalizeStatus(String status) {
        if (status == null || status.isBlank()) {
            return null;
        }
        return status.trim().toUpperCase(Locale.ROOT);
    }
}
```

Trong ví dụ:

- `customerId` không khai báo `required = false`, nên mặc định là bắt buộc. Kiểm tra `null` và chuỗi rỗng ở runtime vẫn cần thiết vì dữ liệu từ model không được xem là đáng tin cậy.
- `status` có thể bị bỏ qua. Tool quy ước `null` hoặc chuỗi trắng đều có nghĩa là không lọc theo trạng thái. Sau khi chuẩn hóa, service cần kiểm tra trạng thái có thuộc tập giá trị hợp lệ hay không.
- `limit` dùng `Integer` thay vì `int`, để biểu diễn trường hợp không có giá trị. Khi `limit == null`, ứng dụng áp dụng mặc định 20. Nếu model truyền `0`, ứng dụng từ chối thay vì âm thầm thay bằng mặc định.
- `ToolContext` mang `principalId` do ứng dụng cung cấp sau xác thực. Giá trị này không phải tham số mà model được phép tự chọn; service cần kiểm tra principal có quyền tra cứu khách hàng đó.

Không nên đặt giá trị mặc định quan trọng chỉ trong mô tả tham số rồi kỳ vọng model luôn điền đúng. Mặc định phải được thực thi trong code hoặc tầng nghiệp vụ. Mô tả chỉ giúp model hiểu cách sử dụng tool; nó không thay thế logic của ứng dụng.

## 4. Kiểu Java và cách xử lý khi thiếu giá trị

Kiểu Java ảnh hưởng trực tiếp đến cách ứng dụng nhận dữ liệu sau khi framework chuyển đổi đối số.

| Kiểu Java | Khi không có giá trị | Lưu ý |
| --- | --- | --- |
| `String` | Có thể nhận `null` tùy cách chuyển đổi đầu vào | Phân biệt chuỗi rỗng, chuỗi trắng và `null` |
| `Integer`, `Long`, `Boolean` | Có thể biểu diễn `null` | Phù hợp hơn kiểu primitive khi tham số là tùy chọn |
| `int`, `long`, `boolean` | Không biểu diễn được `null` | Giá trị mặc định của primitive có thể che khuất việc tham số bị bỏ qua |
| `List<T>` | Có thể nhận `null` hoặc danh sách rỗng tùy đầu vào | Quy định rõ bỏ qua khác với danh sách rỗng như thế nào |
| `enum` | Có thể nhận một giá trị enum hợp lệ hoặc lỗi chuyển đổi | Cần mô tả các lựa chọn và xử lý giá trị không hợp lệ |
| Kiểu ngày giờ | Phụ thuộc định dạng và converter | Chọn định dạng rõ ràng, thường là ISO-8601, và kiểm tra miền giá trị |

Với tham số số lượng tùy chọn, dùng wrapper:

```java
@ToolParam(description = "Số bản ghi tối đa; bỏ qua để dùng 20", required = false)
Integer limit
```

Nếu dùng `int limit`, giá trị `0` có thể xuất hiện khi dữ liệu bị thiếu hoặc được khởi tạo mặc định. Khi đó, code không thể biết model đã yêu cầu 0 hay không gửi giá trị. Wrapper `Integer` giúp biểu diễn rõ trường hợp không có giá trị, nhưng vẫn cần kiểm tra cách binder của phiên bản Spring AI đang dùng xử lý thuộc tính bị bỏ qua và `null`.

Với boolean, `Boolean includeArchived` có thể phân biệt `null` với `false`; `boolean includeArchived` thì không. Ví dụ, nếu bỏ qua nghĩa là dùng cấu hình mặc định còn `false` nghĩa là tắt, wrapper giúp ứng dụng thể hiện được hai trường hợp đó.

Không nên mặc định rằng mọi kiểu generic hoặc `Optional<T>` đều được hỗ trợ như nhau trong schema tool. Cách framework tạo schema và chuyển đổi giá trị phụ thuộc phiên bản, converter và provider. Hãy kiểm tra tool input schema thực tế, sau đó viết test cho cả trường hợp có giá trị và không có thuộc tính.

## 5. Khi nào cần cho phép `null`?

Chỉ cho phép `null` khi nó mang ý nghĩa nghiệp vụ cụ thể. Một số ví dụ:

| Nghiệp vụ | Bỏ qua thuộc tính | Gửi `null` |
| --- | --- | --- |
| Tìm đơn hàng theo ghi chú | Không lọc theo ghi chú | Có thể cũng không lọc; nếu hai trường hợp giống nhau thì không cần hỗ trợ null riêng |
| Cập nhật ghi chú giao hàng | Giữ nguyên ghi chú hiện tại | Xóa ghi chú hiện tại |
| Cập nhật ngày hẹn | Giữ ngày hẹn hiện tại | Xóa ngày hẹn nếu nghiệp vụ cho phép |
| Chọn giới hạn kết quả | Dùng giới hạn mặc định | Thường không cần; nên từ chối hoặc chuẩn hóa theo quy ước rõ ràng |

Ví dụ với một thao tác cập nhật, hợp đồng đầu vào có thể quy ước:

```json
{
  "orderId": "ORD-100",
  "deliveryNote": "Giao tại quầy lễ tân"
}
```

Nghĩa là thay ghi chú bằng nội dung mới.

```json
{
  "orderId": "ORD-100"
}
```

Nghĩa là giữ nguyên ghi chú.

```json
{
  "orderId": "ORD-100",
  "deliveryNote": null
}
```

Nghĩa là xóa ghi chú. Đây là hợp đồng nghiệp vụ minh họa; chỉ dùng cách biểu diễn này khi schema của provider, lớp chuyển đổi và tool runtime đều bảo toàn được khác biệt giữa thuộc tính bị bỏ qua và thuộc tính có giá trị `null`.

Nếu framework hoặc provider làm cho cả hai trường hợp cùng được chuyển thành Java `null`, phương thức tool nhận tham số đơn lẻ sẽ không đủ thông tin để phân biệt. Khi đó, thiết kế một thao tác có trạng thái tường minh sẽ an toàn hơn. Ví dụ dùng `noteAction` với các giá trị `KEEP`, `SET`, `CLEAR`, và chỉ yêu cầu `deliveryNote` khi action là `SET`:

```java
@Tool(description = "Cập nhật ghi chú giao hàng của đơn hàng")
UpdateResult updateDeliveryNote(
        @ToolParam(description = "Mã đơn hàng") String orderId,
        @ToolParam(description = "Chọn KEEP để giữ, SET để thay, CLEAR để xóa")
        String noteAction,
        @ToolParam(description = "Ghi chú mới; chỉ cung cấp khi noteAction là SET", required = false)
        String deliveryNote) {

    if (noteAction == null || noteAction.isBlank()) {
        throw new IllegalArgumentException("noteAction là bắt buộc");
    }

    return switch (noteAction) {
        case "KEEP" -> orderService.keepDeliveryNote(orderId);
        case "SET" -> {
            if (deliveryNote == null || deliveryNote.isBlank()) {
                throw new IllegalArgumentException("deliveryNote phải có nội dung khi chọn SET");
            }
            yield orderService.setDeliveryNote(orderId, deliveryNote.trim());
        }
        case "CLEAR" -> orderService.clearDeliveryNote(orderId);
        default -> throw new IllegalArgumentException("noteAction không hợp lệ");
    };
}
```

Đoạn mã minh họa cách biểu diễn ý định rõ ràng; các kiểu `UpdateResult` và phương thức service là thành phần của ứng dụng. Trước khi gọi một tool cập nhật, ứng dụng còn phải kiểm tra danh tính, quyền trên đơn hàng, trạng thái hiện tại và yêu cầu xác nhận nếu quy trình nghiệp vụ quy định.

## 6. Mặc định, validation và an toàn khi thực thi

Schema là hợp đồng để model tạo đối số. Nó giúp giảm lỗi định dạng nhưng không thay thế kiểm tra ở ứng dụng. Tool có thể được gọi với giá trị sai, thiếu, vượt giới hạn hoặc không phù hợp với trạng thái hiện tại của dữ liệu.

Khi thiết kế một tham số, cần xác định:

1. Có bắt buộc xuất hiện không?
2. Nếu bị bỏ qua, ứng dụng dùng giá trị mặc định nào hoặc bỏ qua bộ lọc nào?
3. Nếu có mặt với `null`, có được chấp nhận không và mang ý nghĩa gì?
4. Nếu là chuỗi rỗng, chuỗi trắng, số 0 hoặc danh sách rỗng thì xử lý ra sao?
5. Giá trị có giới hạn độ dài, miền số, tập enum hoặc định dạng ngày giờ nào?
6. Tham số có ảnh hưởng đến quyền truy cập hoặc tác động ghi dữ liệu không?

Một số nguyên tắc thực hành:

- **Kiểm tra tham số bắt buộc ở runtime.** Không chỉ dựa vào `required = true`. Kiểm tra `null`, rỗng, định dạng và các điều kiện nghiệp vụ.
- **Áp dụng mặc định ở phía ứng dụng.** Ví dụ `limit == null ? 20 : limit`; không giao quyền chọn giới hạn an toàn cho mô hình.
- **Giới hạn đầu vào.** Đặt ngưỡng cho số lượng phần tử, độ dài chuỗi, khoảng thời gian và số kết quả trả về để tránh truy vấn quá lớn.
- **Chuẩn hóa có kiểm soát.** Trim chuỗi, chuẩn hóa mã hoặc enum theo quy tắc xác định. Không âm thầm sửa giá trị khiến ý định người dùng thay đổi.
- **Xác thực quyền độc lập với schema.** Nếu tool cần `principalId`, tenant hoặc role, hãy lấy từ ngữ cảnh xác thực do ứng dụng cung cấp như `ToolContext`, không để model tự truyền danh tính có quyền.
- **Không thực hiện một phần ngoài ý muốn.** Với tool cập nhật, kiểm tra toàn bộ đầu vào và điều kiện trước khi ghi. Dùng transaction hoặc cơ chế idempotency phù hợp khi có retry.
- **Trả lỗi có thể xử lý.** Phân biệt đầu vào không hợp lệ, không có quyền, không tìm thấy dữ liệu và lỗi hệ thống. Không đưa stack trace hoặc secret vào nội dung trả về cho model.

Nếu dùng Bean Validation hoặc validator riêng, hãy gọi validation ở ranh giới thực thi tool hoặc trong service nghiệp vụ. Không mặc định rằng mọi annotation như `@NotNull`, `@Size` hay `@Min` tự động được chuyển thành JSON Schema của tool. Hãy xác nhận hành vi schema generator trong phiên bản đang dùng.

## 7. Kiểm thử schema và các trường hợp biên

Nên kiểm thử cả schema được công bố cho model lẫn hành vi runtime. Một test gọi trực tiếp phương thức Java có thể kiểm tra validation và mặc định, nhưng không chứng minh rằng schema được tạo ra đã đánh dấu đúng thuộc tính bắt buộc. Ngược lại, test schema không chứng minh service từ chối được dữ liệu sai.

| Trường hợp | Dữ liệu đầu vào | Kết quả cần xác minh |
| --- | --- | --- |
| Đủ tham số bắt buộc | Có `customerId` hợp lệ | Tool tiếp tục xử lý |
| Thiếu tham số bắt buộc | Không có `customerId` | Provider/framework từ chối theo schema hoặc tool validation từ chối ở runtime |
| Bỏ qua tham số tùy chọn | Không có `limit` | Ứng dụng áp dụng mặc định đã định nghĩa |
| Giá trị tùy chọn hợp lệ | `limit = 10` | Tool dùng đúng giá trị 10 |
| Giá trị vượt giới hạn | `limit = 1000` | Tool từ chối, không tự chạy truy vấn quá lớn |
| Tham số chuỗi rỗng | `status = " "` | Xử lý theo quy ước đã công bố, ví dụ coi là không lọc hoặc từ chối |
| Truyền `null` | `deliveryNote = null` | Được chấp nhận và thực hiện đúng ý nghĩa null nếu schema/runtime hỗ trợ |
| Thuộc tính bị bỏ qua | Không gửi `deliveryNote` | Giữ nguyên giá trị nếu hợp đồng quy định như vậy |
| Giá trị enum không hợp lệ | `status = "UNKNOWN"` | Bị từ chối với lỗi đầu vào rõ ràng |
| Không có quyền | Principal không được xem đơn hàng | Tool không trả dữ liệu và không thực hiện ghi |

Ví dụ unit test cho mặc định và giới hạn:

```java
@Test
void usesDefaultLimitWhenLimitIsOmitted() {
    ToolContext context = new ToolContext(Map.of("principalId", "test-user"));
    tools.searchOrders("C-100", null, null, context);

    verify(orderQueryService).searchForPrincipal("test-user", "C-100", null, 20);
}

@Test
void rejectsLimitOutsideAllowedRange() {
    ToolContext context = new ToolContext(Map.of("principalId", "test-user"));
    assertThatThrownBy(() -> tools.searchOrders("C-100", null, 1000, context))
            .isInstanceOf(IllegalArgumentException.class);

    verifyNoInteractions(orderQueryService);
}
```

Các ví dụ test giả định `tools` và `orderQueryService` đã được khởi tạo bằng fixture hoặc mock phù hợp. Có thể bổ sung kiểm thử schema bằng cách lấy tool callback/schema đã đăng ký và xác nhận `customerId` nằm trong danh sách required, còn `status` và `limit` thì không. API truy cập schema cụ thể phụ thuộc cách tạo callback và phiên bản Spring AI.

Với trường hợp nullable, cần có test ở tầng chuyển đổi đầu vào để xác nhận framework giữ được sự khác nhau giữa thuộc tính vắng mặt và thuộc tính có giá trị `null`. Nếu không thể kiểm chứng điều đó qua provider đang dùng, hãy sử dụng tham số hành động tường minh như `KEEP`, `SET`, `CLEAR`.

## 8. Cách viết mô tả tham số để model chọn đúng

Mô tả của `@ToolParam` là tín hiệu quan trọng giúp model biết khi nào cần cung cấp tham số. Một mô tả tốt nêu rõ mục đích, đơn vị, định dạng, tập giá trị và ý nghĩa khi bỏ qua.

Mô tả chưa đủ rõ:

```java
@ToolParam(description = "Trạng thái", required = false)
String status
```

Mô tả rõ hơn:

```java
@ToolParam(
        description = "Trạng thái đơn hàng cần lọc. Chỉ nhận PENDING, SHIPPED hoặc DELIVERED. Bỏ qua tham số để tìm ở mọi trạng thái.",
        required = false)
String status
```

Với tham số ngày giờ, ghi rõ múi giờ và định dạng, ví dụ “Thời điểm bắt đầu theo ISO-8601 có offset”. Với tiền, ghi rõ đơn vị tiền tệ và kiểu số. Với danh sách, nêu số phần tử tối đa và ý nghĩa của danh sách rỗng. Tránh mô tả chung chung như “giá trị tùy chọn” mà không nói ứng dụng làm gì khi không có giá trị.

Mô tả càng rõ thì model càng có cơ hội tạo đầu vào đúng, nhưng mô tả không phải rào chắn bảo mật. Mọi giá trị vẫn phải được xác thực và phân quyền ở ứng dụng.

## 9. Quy trình thiết kế tham số cho một tool

Khi tạo một tool mới, hãy thực hiện theo trình tự sau:

1. Viết hợp đồng nghiệp vụ bằng ngôn ngữ đơn giản: tool làm gì, ai được dùng, đầu vào nào cần thiết và có tác động gì.
2. Liệt kê tham số và phân loại từng tham số là bắt buộc, tùy chọn hay nullable.
3. Định nghĩa riêng ý nghĩa của bỏ qua, `null`, chuỗi rỗng, số 0 và danh sách rỗng.
4. Dùng kiểu Java biểu diễn được trạng thái cần thiết; ưu tiên wrapper cho tham số số hoặc boolean tùy chọn.
5. Khai báo `@ToolParam` với `required` và mô tả chính xác.
6. Viết logic mặc định, chuẩn hóa và validation trong ứng dụng hoặc service.
7. Kiểm tra schema thực tế được gửi cho provider và xác nhận khả năng hỗ trợ nullable/optional của chế độ đang dùng.
8. Kiểm thử cả đầu vào hợp lệ, thiếu trường, null, rỗng, vượt giới hạn và trường hợp không có quyền.

Trong Spring AI, `@ToolParam(required = false)` là cách khai báo một tham số có thể vắng mặt trong lời gọi tool. Phần còn lại của hợp đồng — giá trị mặc định, ý nghĩa của `null`, giới hạn dữ liệu và quyền thực thi — phải được thiết kế rõ trong ứng dụng. Khi schema, kiểu Java và quy tắc nghiệp vụ thống nhất, mô hình có thể đề nghị tool chính xác hơn và ứng dụng có thể xử lý yêu cầu một cách dự đoán được.
